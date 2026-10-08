import logging
from datetime import datetime
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Performance Comercial",
    page_icon="📊",
    layout="wide",
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("total_day")

DATA_DIR = Path(__file__).parent / "data"
ARQ_VENDAS = DATA_DIR / "vadas.xlsx"
ARQ_META_SUP = DATA_DIR / "meta_supervisor.xlsx"
TODAS = "Todas"
INTERVALO_ATUALIZACAO = 60
ALTURA_CARD = 125


# -----------------------------------------------------------------------------
# FORMATAÇÃO
# -----------------------------------------------------------------------------
def format_moeda_br(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_pct_br(valor, casas=1, sinal=False):
    texto = f"{valor * 100:{'+' if sinal else ''}.{casas}f}"
    return texto.replace(".", ",")


def coluna_moeda(label):
    # "localized" segue o idioma do navegador (pt-BR: 1.234,56); step fixa 2 casas
    return st.column_config.NumberColumn(label, format="localized", step=0.01)


COLUNA_ATINGIMENTO = st.column_config.ProgressColumn(
    "Atingimento (Pedido / Meta)", format="percent", min_value=0, max_value=1.5
)
COLUNA_POSICAO = st.column_config.NumberColumn("Pos.", width="small")


# -----------------------------------------------------------------------------
# CARREGAMENTO E SANEAMENTO DOS DADOS
# -----------------------------------------------------------------------------
@st.cache_data(max_entries=2)
def load_data(mtime_vendas, mtime_meta):
    # Os mtimes só compõem a chave do cache: o Excel é relido apenas quando o arquivo muda.
    df_fatos = pd.read_excel(ARQ_VENDAS)
    df_meta_sup = pd.read_excel(ARQ_META_SUP)

    df_fatos.columns = [str(col).strip().lower() for col in df_fatos.columns]
    df_meta_sup.columns = [str(col).strip().lower() for col in df_meta_sup.columns]

    df_meta_sup.rename(columns={
        'cod_filial': 'filial',
        'supervisores': 'nm_supervisor',
        'meta supervisão': 'meta'
    }, inplace=True)

    if 'uf_filial' in df_fatos.columns:
        df_fatos.rename(columns={'uf_filial': 'filial'}, inplace=True)

    for df in [df_fatos, df_meta_sup]:
        df['filial'] = df['filial'].astype(str).str.strip().str.upper()
        df['cod_supervisor'] = df['cod_supervisor'].astype(str).str.strip()

    if 'fornecedor' in df_fatos.columns:
        df_fatos['fornecedor'] = df_fatos['fornecedor'].astype(str).str.strip()

    if 'cod_rca' in df_fatos.columns:
        df_fatos['cod_rca'] = df_fatos['cod_rca'].astype(str).str.strip()
        df_fatos['nm_rca'] = df_fatos['nm_rca'].astype(str).str.strip()

    df_fatos['total_valor_pedido'] = pd.to_numeric(df_fatos.get('total_valor_pedido', 0), errors='coerce').fillna(0)
    df_fatos['total_valor_venda'] = pd.to_numeric(df_fatos.get('total_valor_venda', 0), errors='coerce').fillna(0)
    df_meta_sup['meta'] = pd.to_numeric(df_meta_sup.get('meta', 0), errors='coerce').fillna(0)

    return df_fatos, df_meta_sup


# -----------------------------------------------------------------------------
# PROCESSAMENTO DE DADOS
# -----------------------------------------------------------------------------
def process_data(df_fatos, df_meta_sup):
    # --- PIPELINE 1: Ranking de Supervisores ---
    df_sup_fatos = df_fatos.groupby(['filial', 'cod_supervisor'])[['total_valor_pedido', 'total_valor_venda']].sum().reset_index()

    df_sup = pd.merge(df_meta_sup, df_sup_fatos, on=['filial', 'cod_supervisor'], how='left')

    df_sup['meta'] = df_sup['meta'].fillna(0)
    df_sup['nm_supervisor'] = df_sup['nm_supervisor'].fillna('SEM SUPERVISOR')
    df_sup['total_valor_pedido'] = df_sup['total_valor_pedido'].fillna(0)
    df_sup['total_valor_venda'] = df_sup['total_valor_venda'].fillna(0)

    df_sup['pct_atingimento'] = np.where(
        df_sup['meta'] > 0,
        df_sup['total_valor_pedido'] / df_sup['meta'],
        0
    )

    df_sup = df_sup[['filial', 'cod_supervisor', 'nm_supervisor', 'meta', 'total_valor_pedido', 'total_valor_venda', 'pct_atingimento']]
    df_sup.columns = ['Filial', 'Cód. Sup', 'Supervisor', 'Meta', 'Valor Pedido', 'Valor Venda', '% Atingimento']
    df_sup = df_sup[df_sup['Meta'] > 0].copy()

    # --- PIPELINE 2: Resumo por Filial ---
    df_resumo_fatos = df_fatos.groupby('filial')[['total_valor_pedido', 'total_valor_venda']].sum().reset_index()
    df_meta_filial = df_meta_sup.groupby('filial')['meta'].sum().reset_index()

    df_resumo = pd.merge(df_meta_filial, df_resumo_fatos, on='filial', how='left')
    df_resumo['meta'] = df_resumo['meta'].fillna(0)
    df_resumo['total_valor_pedido'] = df_resumo['total_valor_pedido'].fillna(0)
    df_resumo['total_valor_venda'] = df_resumo['total_valor_venda'].fillna(0)

    df_resumo['pct_atingimento'] = np.where(
        df_resumo['meta'] > 0,
        df_resumo['total_valor_pedido'] / df_resumo['meta'],
        0
    )

    df_resumo = df_resumo[['filial', 'meta', 'total_valor_pedido', 'total_valor_venda', 'pct_atingimento']]
    df_resumo.columns = ['Filial', 'Meta', 'Valor Pedido', 'Valor Venda', '% Atingimento']
    df_resumo = df_resumo[df_resumo['Meta'] > 0].copy()

    # --- PIPELINE 3: Fornecedor ---
    df_forn = df_fatos.groupby(['fornecedor', 'filial'])[['total_valor_pedido', 'total_valor_venda']].sum().reset_index()
    df_forn = df_forn[['filial', 'fornecedor', 'total_valor_pedido', 'total_valor_venda']]
    df_forn.columns = ['Filial', 'Fornecedor', 'Valor Pedido', 'Valor Venda']

    # --- PIPELINE 4: RCA ---
    colunas_rca = ['Filial', 'Cód. RCA', 'RCA', 'Supervisor', 'Valor Pedido', 'Valor Venda']
    if 'cod_rca' in df_fatos.columns:
        df_rca = df_fatos.groupby(['filial', 'cod_rca', 'nm_rca', 'nm_supervisor'])[['total_valor_pedido', 'total_valor_venda']].sum().reset_index()
        df_rca.columns = colunas_rca
    else:
        df_rca = pd.DataFrame(columns=colunas_rca)

    return df_sup, df_resumo, df_forn, df_rca


# -----------------------------------------------------------------------------
# COMPONENTES DE UI
# -----------------------------------------------------------------------------
def filtrar_filial(df, filial):
    return df if filial == TODAS else df[df['Filial'] == filial]


def com_ranking(df, ordenar_por):
    df = df.sort_values(by=ordenar_por, ascending=False).reset_index(drop=True)
    df.insert(0, 'Pos.', range(1, len(df) + 1))
    return df


def grafico_atingimento(df, categoria):
    base = alt.Chart(df).encode(
        y=alt.Y(f"{categoria}:N", sort="-x", title=None),
        x=alt.X("% Atingimento:Q", title="Atingimento da meta", axis=alt.Axis(format="%")),
    )
    barras = base.mark_bar(cornerRadiusEnd=4).encode(
        color=alt.when(alt.datum["% Atingimento"] >= 1)
        .then(alt.value("#2E7D32"))
        .otherwise(alt.value("#8C9BAB")),
        tooltip=[
            alt.Tooltip(f"{categoria}:N"),
            alt.Tooltip("% Atingimento:Q", format=".1%"),
            alt.Tooltip("Valor Pedido:Q", format=",.2f"),
            alt.Tooltip("Meta:Q", format=",.2f"),
        ],
    )
    linha_meta = (
        alt.Chart(pd.DataFrame({"meta": [1.0]}))
        .mark_rule(strokeDash=[4, 4], color="#C62828")
        .encode(x="meta:Q")
    )
    return (barras + linha_meta).properties(height=alt.Step(32))


def cards_kpi(df_resumo_view):
    pedido_total = df_resumo_view['Valor Pedido'].sum()
    venda_total = df_resumo_view['Valor Venda'].sum()
    meta_total = df_resumo_view['Meta'].sum()
    pct = (pedido_total / meta_total) if meta_total > 0 else 0

    # Altura fixa: só o card de atingimento tem delta, e sem isso ele fica mais alto que os demais
    estilo_card = {"border": True, "height": ALTURA_CARD}
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Volume Pedido", format_moeda_br(pedido_total), **estilo_card)
    col2.metric("Faturamento Efetivado", format_moeda_br(venda_total), **estilo_card)
    col3.metric("Meta Total", format_moeda_br(meta_total), **estilo_card)
    col4.metric(
        "Atingimento (Pedidos / Meta)",
        f"{format_pct_br(pct)}%",
        delta=f"{format_pct_br(pct - 1, sinal=True)} p.p. vs meta",
        delta_color="normal",
        **estilo_card,
    )


# -----------------------------------------------------------------------------
# PAINEL (reexecutado sozinho a cada INTERVALO_ATUALIZACAO segundos)
# -----------------------------------------------------------------------------
@st.fragment(run_every=INTERVALO_ATUALIZACAO)
def painel():
    try:
        mtime_vendas = ARQ_VENDAS.stat().st_mtime
        mtime_meta = ARQ_META_SUP.stat().st_mtime
        df_fatos, df_meta_sup = load_data(mtime_vendas, mtime_meta)
        df_sup, df_resumo, df_forn, df_rca = process_data(df_fatos, df_meta_sup)
    except FileNotFoundError as e:
        logger.exception("Arquivo de dados ausente")
        st.error(f"Arquivo não encontrado: **{Path(e.filename).name}**. Verifique a pasta `data/`.")
        return
    except Exception:
        logger.exception("Falha ao carregar ou processar as bases")
        st.error(
            "Não foi possível carregar os dados. Verifique se as planilhas em `data/` "
            "estão no layout esperado — o detalhe técnico foi registrado no log."
        )
        return

    atualizado_em = datetime.fromtimestamp(mtime_vendas).strftime("%d/%m/%Y às %H:%M")
    st.caption(f":material/schedule: Dados de vendas atualizados em {atualizado_em} · a tela recarrega a cada {INTERVALO_ATUALIZACAO}s")

    filiais = sorted(df_fatos['filial'].dropna().unique().tolist(), key=lambda f: (len(f), f))
    filial = st.segmented_control(
        "Filial", options=[TODAS] + filiais, default=TODAS, required=True, key="filtro_filial"
    )

    df_resumo_view = filtrar_filial(df_resumo, filial)
    if df_resumo_view.empty:
        st.info(
            f"A filial {filial} não tem meta cadastrada, então não há indicadores de atingimento. "
            "Os valores dela aparecem nas abas de RCA e Fornecedores."
        )
    else:
        cards_kpi(df_resumo_view)

    tab_resumo, tab_sup, tab_rca, tab_forn = st.tabs(
        [
            ":material/storefront: Resumo por Filial",
            ":material/groups: Supervisores",
            ":material/badge: RCA",
            ":material/factory: Fornecedores",
        ],
        key="aba_ativa",
    )

    with tab_resumo:
        st.dataframe(
            df_resumo_view.sort_values(by='% Atingimento', ascending=False),
            width='stretch',
            hide_index=True,
            column_config={
                "Filial": st.column_config.TextColumn("Filial"),
                "Meta": coluna_moeda("Meta (R$)"),
                "Valor Pedido": coluna_moeda("Pedido Digitado (R$)"),
                "Valor Venda": coluna_moeda("Pedido Faturado (R$)"),
                "% Atingimento": COLUNA_ATINGIMENTO,
            },
        )

    with tab_sup:
        df_view_sup = com_ranking(filtrar_filial(df_sup, filial), ['% Atingimento', 'Valor Pedido'])
        if not df_view_sup.empty:
            st.altair_chart(grafico_atingimento(df_view_sup, "Supervisor"), width='stretch')
        st.dataframe(
            df_view_sup,
            width='stretch',
            hide_index=True,
            column_config={
                "Pos.": COLUNA_POSICAO,
                "Filial": st.column_config.TextColumn("Filial"),
                "Cód. Sup": st.column_config.TextColumn("Código"),
                "Supervisor": st.column_config.TextColumn("Supervisor"),
                "Meta": coluna_moeda("Meta (R$)"),
                "Valor Pedido": coluna_moeda("Pedido Digitado (R$)"),
                "Valor Venda": coluna_moeda("Pedido Faturado (R$)"),
                "% Atingimento": COLUNA_ATINGIMENTO,
            },
        )

    with tab_rca:
        st.dataframe(
            com_ranking(filtrar_filial(df_rca, filial), 'Valor Pedido'),
            width='stretch',
            hide_index=True,
            column_config={
                "Pos.": COLUNA_POSICAO,
                "Filial": st.column_config.TextColumn("Filial"),
                "Cód. RCA": st.column_config.TextColumn("Código"),
                "RCA": st.column_config.TextColumn("RCA"),
                "Supervisor": st.column_config.TextColumn("Supervisor"),
                "Valor Pedido": coluna_moeda("Pedido Digitado (R$)"),
                "Valor Venda": coluna_moeda("Pedido Faturado (R$)"),
            },
        )

    with tab_forn:
        st.dataframe(
            com_ranking(filtrar_filial(df_forn, filial), 'Valor Pedido'),
            width='stretch',
            hide_index=True,
            column_config={
                "Pos.": COLUNA_POSICAO,
                "Filial": st.column_config.TextColumn("Filial"),
                "Fornecedor": st.column_config.TextColumn("Fornecedor"),
                "Valor Pedido": coluna_moeda("Pedido Digitado (R$)"),
                "Valor Venda": coluna_moeda("Pedido Faturado (R$)"),
            },
        )


def main():
    st.title(":material/monitoring: Performance Comercial")
    st.caption("Pedidos digitados e faturados cruzados com as metas do evento.")
    painel()


if __name__ == "__main__":
    main()
