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
ARQ_META_FORN = DATA_DIR / "meta fornecedor filial.xlsx"
ABA_META_FORN = "Planilha1"
ARQ_META_SUP = DATA_DIR / "meta_supervisor.xlsx"
ARQ_META_GER = DATA_DIR / "meta_gerente.xlsx"
ARQ_META_RCA = DATA_DIR / "meta_rca.xlsx"

TODAS = "Todas"
OUTROS = "OUTROS"
INTERVALO_ATUALIZACAO = 60
ALTURA_CARD = 125

# A meta é definida por praça; PI e MA agrupam duas filiais de venda cada.
FILIAL_PARA_PRACA = {"2": "PI", "6": "PI", "4": "MA", "5": "MA"}
ROTULO_PRACA = {
    "1": "CE 01",
    "3": "CE 03",
    "PI": "PI (02/06)",
    "MA": "MA (04/05)",
    "7": "BA (07)",
    "9": "PE (09)",
}

COLUNAS_VALOR = ['total_valor_pedido', 'total_valor_venda']
# Fornecedores cujas vendas não contam na apuração de gerentes (só nessa aba)
FORNECEDORES_FORA_GERENTE = {"789429"}


# -----------------------------------------------------------------------------
# FORMATAÇÃO
# -----------------------------------------------------------------------------
def format_moeda_br(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_pct_br(valor, casas=1, sinal=False):
    texto = f"{valor * 100:{'+' if sinal else ''}.{casas}f}"
    return texto.replace(".", ",")


def rotulo_praca(praca):
    return ROTULO_PRACA.get(praca, praca)


def coluna_moeda(label):
    # "localized" segue o idioma do navegador (pt-BR: 1.234,56); step fixa 2 casas
    return st.column_config.NumberColumn(label, format="localized", step=0.01)


COLUNA_ATINGIMENTO = st.column_config.ProgressColumn(
    "Atingimento (Pedido / Meta)", format="percent", min_value=0, max_value=1.5
)
COLUNA_POSICAO = st.column_config.NumberColumn("Pos.", width="small")
CONFIG_VALORES = {
    "Meta": coluna_moeda("Meta (R$)"),
    "Valor Pedido": coluna_moeda("Pedido Digitado (R$)"),
    "Valor Venda": coluna_moeda("Pedido Faturado (R$)"),
    "% Atingimento": COLUNA_ATINGIMENTO,
}


# -----------------------------------------------------------------------------
# CARREGAMENTO E SANEAMENTO DOS DADOS
# -----------------------------------------------------------------------------
def _texto(serie):
    return serie.astype(str).str.strip().str.upper().str.replace(r"\.0$", "", regex=True)


def _numero(df, coluna):
    return pd.to_numeric(df.get(coluna, 0), errors='coerce').fillna(0)


@st.cache_data(max_entries=2)
def load_data(mtime_vendas, mtime_meta_forn, mtime_meta_sup, mtime_meta_ger, mtime_meta_rca):
    # Os mtimes só compõem a chave do cache: o Excel é relido apenas quando o arquivo muda.
    vendas = pd.read_excel(ARQ_VENDAS)
    meta_forn = pd.read_excel(ARQ_META_FORN, sheet_name=ABA_META_FORN)
    meta_sup = pd.read_excel(ARQ_META_SUP)
    meta_ger = pd.read_excel(ARQ_META_GER)
    meta_rca = pd.read_excel(ARQ_META_RCA)

    for df in [vendas, meta_forn, meta_sup, meta_ger, meta_rca]:
        df.columns = [str(col).strip().lower() for col in df.columns]

    vendas.rename(columns={'uf_filial': 'filial'}, inplace=True)
    vendas['filial'] = _texto(vendas['filial'])
    vendas['praca'] = vendas['filial'].map(FILIAL_PARA_PRACA).fillna(vendas['filial'])
    vendas['codfornec'] = _texto(vendas['codfornec'])
    vendas['cod_supervisor'] = _texto(vendas['cod_supervisor'])
    vendas['cod_gerente'] = _texto(vendas['cod_gerente'])
    vendas['cod_rca'] = _texto(vendas['cod_rca'])
    for col in COLUNAS_VALOR:
        vendas[col] = _numero(vendas, col)

    meta_forn.rename(columns={'cod_filial': 'praca', 'cod_fornecedor': 'codfornec'}, inplace=True)
    meta_forn['praca'] = _texto(meta_forn['praca'])
    meta_forn['codfornec'] = _texto(meta_forn['codfornec'])
    meta_forn['fornecedor'] = meta_forn['fornecedor'].astype(str).str.strip()
    meta_forn['grupo'] = meta_forn['grupo'].astype(str).str.strip()
    meta_forn['meta'] = _numero(meta_forn, 'meta')

    meta_sup.rename(columns={
        'cod_filial': 'praca',
        'supervisores': 'nm_supervisor',
        'meta supervisão': 'meta'
    }, inplace=True)
    meta_sup['praca'] = _texto(meta_sup['praca'])
    meta_sup['cod_supervisor'] = _texto(meta_sup['cod_supervisor'])
    meta_sup['meta'] = _numero(meta_sup, 'meta')

    meta_ger.rename(columns={
        'cod_filial': 'filial',
        'gerente': 'nm_gerente',
        'meta gerente': 'meta'
    }, inplace=True)
    meta_ger['filial'] = _texto(meta_ger['filial'])
    meta_ger['praca'] = meta_ger['filial'].map(FILIAL_PARA_PRACA).fillna(meta_ger['filial'])
    meta_ger['cod_gerente'] = _texto(meta_ger['cod_gerente'])
    meta_ger['nm_gerente'] = meta_ger['nm_gerente'].astype(str).str.strip()
    meta_ger['meta'] = _numero(meta_ger, 'meta')

    meta_rca.rename(columns={'cod_filial': 'praca', 'meta_rca': 'meta'}, inplace=True)
    meta_rca['praca'] = _texto(meta_rca['praca'])
    meta_rca['cod_rca'] = _texto(meta_rca['cod_rca'])
    meta_rca['nm_rca'] = meta_rca['nm_rca'].astype(str).str.strip()
    meta_rca['meta'] = _numero(meta_rca, 'meta')

    return vendas, meta_forn, meta_sup, meta_ger, meta_rca


# -----------------------------------------------------------------------------
# PROCESSAMENTO DE DADOS
# -----------------------------------------------------------------------------
def _atingimento(df):
    df['% Atingimento'] = np.where(df['Meta'] > 0, df['Valor Pedido'] / df['Meta'], 0)
    return df


def _renomear_valores(df):
    return df.rename(columns={
        'meta': 'Meta',
        'total_valor_pedido': 'Valor Pedido',
        'total_valor_venda': 'Valor Venda',
    })


def apurar_fornecedores(vendas, meta_forn):
    # Fornecedor sem meta na praça cai em OUTROS daquela praça.
    foco = meta_forn.loc[meta_forn['codfornec'] != OUTROS, ['praca', 'codfornec']].assign(foco=True)
    vendas = vendas.merge(foco, on=['praca', 'codfornec'], how='left')
    vendas['codfornec_apurado'] = np.where(vendas['foco'].notna(), vendas['codfornec'], OUTROS)

    apurado = (
        vendas.groupby(['praca', 'codfornec_apurado'])[COLUNAS_VALOR].sum()
        .reset_index().rename(columns={'codfornec_apurado': 'codfornec'})
    )
    df = meta_forn.merge(apurado, on=['praca', 'codfornec'], how='outer')
    df[['meta'] + COLUNAS_VALOR] = df[['meta'] + COLUNAS_VALOR].fillna(0)
    df['fornecedor'] = df['fornecedor'].fillna(OUTROS)
    df['grupo'] = df['grupo'].fillna(OUTROS)
    df.loc[df['codfornec'] == OUTROS, 'fornecedor'] = 'Outros fornecedores'

    df = _atingimento(_renomear_valores(df))
    df['Filial'] = df['praca'].map(rotulo_praca)
    return df.rename(columns={'grupo': 'Grupo', 'fornecedor': 'Fornecedor', 'codfornec': 'Cód. Forn'})


def apurar_filiais(vendas, meta_forn):
    meta = meta_forn.groupby('praca')['meta'].sum()
    apurado = vendas.groupby('praca')[COLUNAS_VALOR].sum()
    df = pd.concat([meta, apurado], axis=1).fillna(0).reset_index()
    df = _atingimento(_renomear_valores(df))
    df['Filial'] = df['praca'].map(rotulo_praca)
    return df


def apurar_supervisores(vendas, meta_sup):
    apurado = vendas.groupby(['praca', 'cod_supervisor'])[COLUNAS_VALOR].sum().reset_index()
    df = meta_sup.merge(apurado, on=['praca', 'cod_supervisor'], how='left')
    df[COLUNAS_VALOR] = df[COLUNAS_VALOR].fillna(0)
    df['nm_supervisor'] = df['nm_supervisor'].fillna('SEM SUPERVISOR')
    df = _atingimento(_renomear_valores(df))
    df = df[df['Meta'] > 0].copy()
    df['Filial'] = df['praca'].map(rotulo_praca)
    return df.rename(columns={'cod_supervisor': 'Cód. Sup', 'nm_supervisor': 'Supervisor'})


def apurar_gerentes(vendas, meta_ger):
    # Gerente vende em mais de uma filial: a apuração soma pelo código, e a filial é a do cadastro de meta.
    vendas = vendas[~vendas['codfornec'].isin(FORNECEDORES_FORA_GERENTE)]
    apurado = vendas.groupby('cod_gerente')[COLUNAS_VALOR].sum().reset_index()
    df = meta_ger.merge(apurado, on='cod_gerente', how='left')
    df[COLUNAS_VALOR] = df[COLUNAS_VALOR].fillna(0)
    df = _atingimento(_renomear_valores(df))
    df['Filial'] = df['praca'].map(rotulo_praca)

    sem_meta = vendas[~vendas['cod_gerente'].isin(meta_ger['cod_gerente'])]
    pedido_sem_meta = sem_meta.groupby('cod_gerente')['total_valor_pedido'].sum()
    pedido_sem_meta = pedido_sem_meta[pedido_sem_meta != 0].sort_values(ascending=False)

    df = df.rename(columns={'cod_gerente': 'Cód. Ger', 'nm_gerente': 'Gerente'})
    return df, pedido_sem_meta


def apurar_rcas(vendas, meta_rca):
    # Só RCAs com meta; como o gerente, soma o pedido de todas as filiais pelo código.
    meta_rca = meta_rca[meta_rca['meta'] > 0]
    apurado = vendas.groupby('cod_rca')[COLUNAS_VALOR].sum().reset_index()
    df = meta_rca.merge(apurado, on='cod_rca', how='left')
    df[COLUNAS_VALOR] = df[COLUNAS_VALOR].fillna(0)
    df = _atingimento(_renomear_valores(df))
    df['Filial'] = df['praca'].map(rotulo_praca)
    return df.rename(columns={'cod_rca': 'Cód. RCA', 'nm_rca': 'RCA'})


def consolidar_por_fornecedor(df_forn):
    df = df_forn.groupby(['Grupo', 'Fornecedor'])[['Meta', 'Valor Pedido', 'Valor Venda']].sum().reset_index()
    return _atingimento(df)


# -----------------------------------------------------------------------------
# COMPONENTES DE UI
# -----------------------------------------------------------------------------
def filtrar_praca(df, praca):
    return df if praca == TODAS else df[df['praca'] == praca]


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
    return (barras + linha_meta).properties(height=alt.Step(28))


def tabela(df, colunas, config_extra=None):
    st.dataframe(
        df,
        width='stretch',
        hide_index=True,
        column_order=colunas,
        column_config={**CONFIG_VALORES, "Pos.": COLUNA_POSICAO, **(config_extra or {})},
    )


def cards_kpi(df_filiais_view):
    pedido_total = df_filiais_view['Valor Pedido'].sum()
    venda_total = df_filiais_view['Valor Venda'].sum()
    meta_total = df_filiais_view['Meta'].sum()
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
        vendas, meta_forn, meta_sup, meta_ger, meta_rca = load_data(
            mtime_vendas,
            ARQ_META_FORN.stat().st_mtime,
            ARQ_META_SUP.stat().st_mtime,
            ARQ_META_GER.stat().st_mtime,
            ARQ_META_RCA.stat().st_mtime,
        )
        df_rca = apurar_rcas(vendas, meta_rca)
        df_filiais = apurar_filiais(vendas, meta_forn)
        df_forn = apurar_fornecedores(vendas, meta_forn)
        df_ger, pedido_ger_sem_meta = apurar_gerentes(vendas, meta_ger)
        df_sup = apurar_supervisores(vendas, meta_sup)
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

    pracas = [p for p in ROTULO_PRACA if p in set(df_filiais['praca'])]
    pracas += sorted(set(df_filiais['praca']) - set(pracas))
    praca = st.segmented_control(
        "Filial",
        options=[TODAS] + pracas,
        default=TODAS,
        required=True,
        format_func=rotulo_praca,
        key="filtro_filial",
    )

    df_filiais_view = filtrar_praca(df_filiais, praca)
    cards_kpi(df_filiais_view)

    tab_filial, tab_forn, tab_ger, tab_sup, tab_rca = st.tabs(
        [
            ":material/storefront: Filiais",
            ":material/factory: Fornecedores",
            ":material/supervisor_account: Gerentes",
            ":material/groups: Supervisores",
            ":material/badge: RCA",
        ],
        key="aba_ativa",
    )

    with tab_filial:
        if praca == TODAS:
            st.altair_chart(grafico_atingimento(df_filiais, "Filial"), width='stretch')
        tabela(
            com_ranking(df_filiais_view, ['% Atingimento', 'Valor Pedido']),
            ["Pos.", "Filial", "Meta", "Valor Pedido", "Valor Venda", "% Atingimento"],
        )

    with tab_forn:
        # Opções vêm da base inteira para a seleção continuar válida ao trocar de filial
        fornecedores = sorted(set(df_forn['Fornecedor']) - {'Outros fornecedores'}) + ['Outros fornecedores']
        selecionados = st.multiselect(
            "Fornecedor",
            options=fornecedores,
            placeholder="Todos os fornecedores",
            key="filtro_fornecedor",
        )

        df_forn_view = filtrar_praca(df_forn, praca)
        if selecionados:
            df_forn_view = df_forn_view[df_forn_view['Fornecedor'].isin(selecionados)]

        if df_forn_view.empty:
            st.info("Nenhum dos fornecedores selecionados tem meta ou venda nesta filial.")
        else:
            consolidado = consolidar_por_fornecedor(df_forn_view)
            st.altair_chart(grafico_atingimento(consolidado, "Fornecedor"), width='stretch')

            st.markdown("**Por filial**" if praca == TODAS else f"**{rotulo_praca(praca)}**")
            tabela(
                com_ranking(df_forn_view, ['% Atingimento', 'Valor Pedido']),
                ["Pos.", "Filial", "Grupo", "Fornecedor", "Meta", "Valor Pedido", "Valor Venda", "% Atingimento"],
            )

    with tab_ger:
        df_ger_view = com_ranking(filtrar_praca(df_ger, praca), ['% Atingimento', 'Valor Pedido'])
        if df_ger_view.empty:
            st.info("Nenhum gerente com meta cadastrada para esta filial.")
        else:
            st.altair_chart(grafico_atingimento(df_ger_view, "Gerente"), width='stretch')
            tabela(
                df_ger_view,
                ["Pos.", "Filial", "Cód. Ger", "Gerente", "Meta", "Valor Pedido", "Valor Venda", "% Atingimento"],
                {"Cód. Ger": st.column_config.TextColumn("Código")},
            )
        st.caption(
            "O pedido de cada gerente soma todas as filiais em que ele vendeu; "
            "o filtro de filial usa a filial do cadastro de meta. "
            f"Vendas do fornecedor {', '.join(sorted(FORNECEDORES_FORA_GERENTE))} não entram nesta aba."
        )
        if not pedido_ger_sem_meta.empty:
            codigos = ", ".join(pedido_ger_sem_meta.index)
            st.caption(
                f":material/info: {format_moeda_br(pedido_ger_sem_meta.sum())} em pedidos de gerentes "
                f"sem meta cadastrada (códigos {codigos}) não entram nesta aba."
            )

    with tab_sup:
        df_sup_view = com_ranking(filtrar_praca(df_sup, praca), ['% Atingimento', 'Valor Pedido'])
        if df_sup_view.empty:
            st.info("Nenhum supervisor com meta cadastrada para esta filial.")
        else:
            st.altair_chart(grafico_atingimento(df_sup_view, "Supervisor"), width='stretch')
            tabela(
                df_sup_view,
                ["Pos.", "Filial", "Cód. Sup", "Supervisor", "Meta", "Valor Pedido", "Valor Venda", "% Atingimento"],
                {"Cód. Sup": st.column_config.TextColumn("Código")},
            )

    with tab_rca:
        df_rca_view = com_ranking(filtrar_praca(df_rca, praca), ['% Atingimento', 'Valor Pedido'])
        if df_rca_view.empty:
            st.info("Nenhum RCA com meta cadastrada para esta filial.")
        else:
            bateram = int((df_rca_view['% Atingimento'] >= 1).sum())
            sem_pedido = int((df_rca_view['Valor Pedido'] <= 0).sum())
            st.markdown(
                f"**{bateram} de {len(df_rca_view)}** RCAs já bateram a meta · "
                f"**{sem_pedido}** ainda sem pedido"
            )
            tabela(
                df_rca_view,
                ["Pos.", "Filial", "Cód. RCA", "RCA", "Meta", "Valor Pedido", "Valor Venda", "% Atingimento"],
                {"Cód. RCA": st.column_config.TextColumn("Código")},
            )
        st.caption(
            "Exibe apenas RCAs com meta cadastrada. O pedido de cada RCA soma todas as filiais "
            "em que ele vendeu; o filtro de filial usa a filial do cadastro de meta."
        )


def main():
    st.title(":material/monitoring: Performance Comercial")
    st.caption("Pedidos digitados e faturados cruzados com as metas do evento.")
    painel()


if __name__ == "__main__":
    main()
