import streamlit as st
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh

# -----------------------------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Dashboard Evento - Fornecedores",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# INJEÇÃO DE ESTILO CUSTOMIZADO (Clean UI)
# -----------------------------------------------------------------------------
def inject_custom_css():
    st.markdown("""
        <style>
        header, [data-testid="stHeader"] {
            visibility: hidden;
            height: 0% !important;
            padding: 0px !important;
        }
        .block-container { 
            padding-top: 1.5rem !important; 
            padding-bottom: 1rem !important; 
            max-width: 95% !important; 
        }
        [data-testid="stMetricValue"] { 
            font-size: 28px !important; 
            font-weight: bold; 
        }
        [data-testid="stMetric"] { 
            background-color: var(--secondary-background-color); 
            padding: 15px; 
            border-radius: 8px; 
            border: 1px solid rgba(128, 128, 128, 0.2); 
            box-shadow: 2px 2px 10px rgba(0,0,0,0.05); 
            min-height: 145px !important;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        [data-testid="stMetric"] > div {
            margin-top: auto;
            margin-bottom: auto;
        }
        </style>
    """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# CARREGAMENTO E SANEAMENTO DOS DADOS (Data Ingestion & Normalization)
# -----------------------------------------------------------------------------
#@st.cache_data(ttl=900)
def load_data():
    """
    Realiza a ingestão e sanitização das dimensões e fatos.
    Garante o alinhamento de tipos e nomenclatura para evitar Data Loss no JOIN.
    """
    meta_fornec = pd.read_excel("data/meta_fornecedor.xlsx")
    meta_sup = pd.read_excel("data/meta_supervisor.xlsx")
    fat = pd.read_excel("data/fat_total_day.xlsx")
    
    # 1. Normalização preventiva de nomenclatura das COLUNAS
    for df in [meta_fornec, meta_sup, fat]:
        df.columns = [str(col).strip().lower() for col in df.columns]
    
    # Normalização da chave de fornecedor e meta_supervisor
    if 'cod_fornec' in meta_fornec.columns:
        meta_fornec.rename(columns={'cod_fornec': 'codfornec'}, inplace=True)
    if 'meta_supervisor' in meta_sup.columns:
        meta_sup.rename(columns={'meta_supervisor': 'meta'}, inplace=True)
    
    # 2. Alinhamento da Chave Filial
    if 'uf_filial' in fat.columns:
        fat.rename(columns={'uf_filial': 'filial'}, inplace=True)
    elif 'codfilial' in fat.columns:
        fat.rename(columns={'codfilial': 'filial'}, inplace=True)
        
    if 'filial' in meta_fornec.columns:
        meta_fornec['filial'] = meta_fornec['filial'].astype(str).str.strip().str.upper()
    if 'filial' in fat.columns:
        fat['filial'] = fat['filial'].astype(str).str.strip().str.upper()
        
    # 3. Alinhamento da Chave Supervisor
    if 'nm_supervisor' in meta_sup.columns:
        meta_sup['nm_supervisor'] = meta_sup['nm_supervisor'].astype(str).str.strip().str.upper()
    
    if 'nm_supervisor' not in fat.columns:
        fat['nm_supervisor'] = 'SEM SUPERVISOR'
    else:
        fat['nm_supervisor'] = fat['nm_supervisor'].astype(str).str.strip().str.upper()
        
    # Casting explícito numérico e string
    meta_fornec['codfornec'] = meta_fornec['codfornec'].astype(str).str.strip()
    fat['codfornec'] = fat['codfornec'].astype(str).str.strip()
        
    meta_fornec['meta'] = pd.to_numeric(meta_fornec['meta'], errors='coerce').fillna(0)
    meta_sup['meta'] = pd.to_numeric(meta_sup['meta'], errors='coerce').fillna(0)
    fat['total_valor_pedido'] = pd.to_numeric(fat['total_valor_pedido'], errors='coerce').fillna(0)
    fat['total_valor_venda'] = pd.to_numeric(fat['total_valor_venda'], errors='coerce').fillna(0)
        
    return meta_fornec, meta_sup, fat

# -----------------------------------------------------------------------------
# PROCESSAMENTO DE DADOS (Transformations)
# -----------------------------------------------------------------------------
def process_data(meta_fornec, meta_sup, fat):
    """
    Gera três níveis distintos de agregação (Grãos) para o Dashboard.
    """
    # --- PIPELINE 1: Visão Filial vs Fornecedor ---
    fat_agg_filial = fat.groupby(['filial', 'codfornec'])[['total_valor_pedido', 'total_valor_venda']].sum().reset_index()
    df_fornec = pd.merge(meta_fornec, fat_agg_filial, on=['filial', 'codfornec'], how='left')
    
    df_fornec['total_valor_pedido'] = df_fornec['total_valor_pedido'].fillna(0)
    df_fornec['total_valor_venda'] = df_fornec['total_valor_venda'].fillna(0)
    
    df_fornec['pct_atingimento'] = np.where(
        df_fornec['meta'] > 0, 
        df_fornec['total_valor_pedido'] / df_fornec['meta'], 
        0
    )
    
    df_visao_filial = df_fornec[['filial', 'fornecedores', 'meta', 'total_valor_pedido', 'total_valor_venda', 'pct_atingimento']].copy()
    df_visao_filial.columns = ['Filial', 'Fornecedor', 'Meta', 'Valor Pedido', 'Valor Venda', '% Atingimento']
    df_visao_filial = df_visao_filial[df_visao_filial['Meta'] > 0]
    
    # --- PIPELINE 2: Visão Ranking de Supervisores ---
    fat_agg_sup = fat.groupby(['filial', 'nm_supervisor'])[['total_valor_pedido', 'total_valor_venda']].sum().reset_index()
    df_sup = pd.merge(fat_agg_sup, meta_sup, on='nm_supervisor', how='left')
    df_sup['meta'] = df_sup['meta'].fillna(0)
    
    df_sup['pct_atingimento'] = np.where(
        df_sup['meta'] > 0, 
        df_sup['total_valor_pedido'] / df_sup['meta'], 
        0
    )
    
    df_visao_sup = df_sup[['filial', 'nm_supervisor', 'meta', 'total_valor_pedido', 'total_valor_venda', 'pct_atingimento']].copy()
    df_visao_sup.columns = ['Filial', 'Supervisor', 'Meta', 'Valor Pedido', 'Valor Venda', '% Atingimento']
    df_visao_sup = df_visao_sup[df_visao_sup['Meta'] > 0]

    # --- PIPELINE 3: Visão Executiva Resumida por Filial (NOVO) ---
    # Utilizamos os dados já filtrados e consolidados da visão Fornecedor
    # para garantir que o macro "bata" perfeitamente com o micro.
    df_visao_resumo = df_visao_filial.groupby('Filial')[['Meta', 'Valor Pedido', 'Valor Venda']].sum().reset_index()
    
    # Recálculo matemático mandatório da métrica não-aditiva
    df_visao_resumo['% Atingimento'] = np.where(
        df_visao_resumo['Meta'] > 0, 
        df_visao_resumo['Valor Pedido'] / df_visao_resumo['Meta'], 
        0
    )
    
    return df_visao_filial, df_visao_sup, df_visao_resumo

# -----------------------------------------------------------------------------
# RENDERIZAÇÃO E INTERFACE GRÁFICA
# -----------------------------------------------------------------------------
def main():
    st_autorefresh(interval=60000, limit=500, key="data_refresh")
    inject_custom_css()
    
    st.title("📦 Acompanhamento de Metas e Performance")
    st.markdown("Monitoramento consolidado de Captação, Faturamento e Força de Vendas")
    st.divider()

    try:
        meta_fornec, meta_sup, fat = load_data()
        df_visao_filial, df_visao_sup, df_visao_resumo = process_data(meta_fornec, meta_sup, fat)
    except Exception as e:
        st.error(f"⚠️ Erro de I/O ou Parse. Verifique os arquivos em 'data/'. Log: {e}")
        return

    # --- CARDS EXECUTIVOS (KPIs Globais Absolutos) ---
    # Alteração Arquitetural: Lendo diretamente do Dataframe bruto (SSOT) para ignorar os filtros de "Possui Meta"
    meta_total = meta_fornec['meta'].sum()
    pedido_total = fat['total_valor_pedido'].sum()
    venda_total = fat['total_valor_venda'].sum()
    
    pct_geral = (pedido_total / meta_total) if meta_total > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Meta Total (Evento)", f"R$ {meta_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    with col2:
        st.metric("Total Captação (Pedidos)", f"R$ {pedido_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    with col3:
        st.metric("Faturamento Efetivado", f"R$ {venda_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    with col4:
        delta_color = "normal" if pct_geral >= 1 else "inverse"
        st.metric("% Atingimento Global", f"{pct_geral * 100:.2f}%", delta=f"{(pct_geral - 1) * 100:.2f}% vs Meta", delta_color=delta_color)

    st.divider()

    # --- ESTRUTURA DE ABAS ---
    tab_resumo, tab_filial, tab_sup = st.tabs([
        "🌎 Resumo Geral", 
        "🏢 Performance por Fornecedor", 
        "👔 Ranking de Supervisores"
    ])

    # Configuração de Colunas Comum
    column_config_base = {
        "Filial": st.column_config.TextColumn("Filial/UF"),
        "Valor Pedido": st.column_config.NumberColumn("Valor Pedido", format="R$ %.2f"),
        "Valor Venda": st.column_config.NumberColumn("Valor Venda", format="R$ %.2f"),
        "% Atingimento": st.column_config.ProgressColumn(
            "% Atingimento",
            help="Barra de progresso: (Valor Pedido / Meta)",
            format="%.2f",
            min_value=0,
            max_value=1.5,
        )
    }

    # ABA 1 (NOVA): RESUMO EXECUTIVO POR FILIAL
    with tab_resumo:
        col_config_resumo = column_config_base.copy()
        col_config_resumo.update({
            "Meta": st.column_config.NumberColumn("Meta", format="R$ %.2f")
        })
        
        st.dataframe(
            df_visao_resumo.sort_values(by='% Atingimento', ascending=False), 
            use_container_width=True, 
            hide_index=True,
            column_config=col_config_resumo
        )

    # ABA 2: PERFORMANCE FILIAL/FORNECEDOR
    with tab_filial:
        col_config_filial = column_config_base.copy()
        col_config_filial.update({
            "Fornecedor": st.column_config.TextColumn("Fornecedor"),
            "Meta": st.column_config.NumberColumn("Meta", format="R$ %.2f")
        })
        
        lista_filiais_f = ["Todas"] + sorted(df_visao_filial['Filial'].dropna().unique().tolist())
        filtro_filial_f = st.selectbox("Filtrar por Filial/UF (Fornecedores):", options=lista_filiais_f, index=0, key='sel_filial')
        
        df_view_filial = df_visao_filial if filtro_filial_f == "Todas" else df_visao_filial[df_visao_filial['Filial'] == filtro_filial_f]
            
        st.dataframe(
            df_view_filial.sort_values(by=['% Atingimento', 'Meta'], ascending=[False, False]), 
            use_container_width=True, 
            hide_index=True,
            column_config=col_config_filial
        )

    # ABA 3: RANKING DE SUPERVISORES
    with tab_sup:
        col_config_sup = column_config_base.copy()
        col_config_sup.update({
            "Supervisor": st.column_config.TextColumn("Nome do Supervisor"),
            "Meta": st.column_config.NumberColumn("Meta", format="R$ %.2f")
        })
        
        lista_filiais_s = ["Todas"] + sorted(df_visao_sup['Filial'].dropna().unique().tolist())
        filtro_filial_s = st.selectbox("Filtrar por Filial/UF (Supervisores):", options=lista_filiais_s, index=0, key='sel_sup')
        
        df_view_sup = df_visao_sup if filtro_filial_s == "Todas" else df_visao_sup[df_visao_sup['Filial'] == filtro_filial_s]
        
        df_view_sup = df_view_sup.sort_values(by=['% Atingimento', 'Valor Pedido'], ascending=[False, False]).reset_index(drop=True)
        df_view_sup.index = df_view_sup.index + 1
        
        st.dataframe(
            df_view_sup, 
            use_container_width=True, 
            hide_index=False,
            column_config=col_config_sup
        )

if __name__ == "__main__":
    main()