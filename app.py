import streamlit as st
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh

# -----------------------------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA (Deve ser o primeiro comando Streamlit)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Dashboard Evento de Vendas",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# INJEÇÃO DE ESTILO CUSTOMIZADO (Clean UI / UX)
# -----------------------------------------------------------------------------
def inject_custom_css():
    """
    Injeta CSS customizado para ocultar cabeçalhos padrão do Streamlit
    e estilizar os KPIs de forma corporativa.
    """
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
@st.cache_data(ttl=300)
def load_data():
    """
    Carrega as dimensões e tabelas fato a partir do diretório local.
    Normaliza todas as colunas para minúsculo para mitigar quebras do Oracle.
    """
    dim_rca = pd.read_excel("data/dim_rca.xlsx")
    dim_tv = pd.read_excel("data/dim_televendas.xlsx")
    meta_rca = pd.read_excel("data/meta_rca.xlsx")
    meta_tv = pd.read_excel("data/meta_televendas.xlsx")
    fat = pd.read_excel("data/fat_total_day.xlsx")
    
    # Normalização preventiva de nomenclatura de colunas (Case Insensitive)
    for df in [dim_rca, dim_tv, meta_rca, meta_tv, fat]:
        df.columns = [col.lower() for col in df.columns]
        
    # Saneamento de tipos
    meta_rca['meta'] = pd.to_numeric(meta_rca['meta'], errors='coerce').fillna(0)
    meta_tv['meta'] = pd.to_numeric(meta_tv['meta'], errors='coerce').fillna(0)
    fat['valor_venda'] = pd.to_numeric(fat['valor_venda'], errors='coerce').fillna(0)
    
    return dim_rca, dim_tv, meta_rca, meta_tv, fat

# -----------------------------------------------------------------------------
# PROCESSAMENTO DE DADOS (Business Intelligence Logic)
# -----------------------------------------------------------------------------
def process_data(dim_rca, dim_tv, meta_rca, meta_tv, fat):
    # --- Pipeline RCA ---
    fat_rca = fat.groupby('cod_rca')['valor_venda'].sum().reset_index()
    df_rca = pd.merge(meta_rca, dim_rca, left_on='cod_rca', right_on='codigo_rca', how='left')
    df_rca = pd.merge(df_rca, fat_rca, on='cod_rca', how='left')
    df_rca['valor_venda'] = df_rca['valor_venda'].fillna(0)
    df_rca['pct_atingimento'] = np.where(df_rca['meta'] > 0, df_rca['valor_venda'] / df_rca['meta'], 0)
    
    df_rca_final = df_rca[['filial', 'nm_rca', 'meta', 'valor_venda', 'pct_atingimento']].copy()
    df_rca_final.columns = ['Filial', 'Nome', 'Meta', 'Valor Venda', '% Atingimento']

    # --- Pipeline Televendas ---
    fat_tv = fat.groupby('cod_televendas')['valor_venda'].sum().reset_index()
    df_tv = pd.merge(meta_tv, dim_tv, left_on='cod_televenda', right_on='codigo_televendas', how='left')
    df_tv = pd.merge(df_tv, fat_tv, left_on='cod_televenda', right_on='cod_televendas', how='left')
    df_tv['valor_venda'] = df_tv['valor_venda'].fillna(0)
    df_tv['pct_atingimento'] = np.where(df_tv['meta'] > 0, df_tv['valor_venda'] / df_tv['meta'], 0)
    
    df_tv_final = df_tv[['filial', 'nm_televendas', 'meta', 'valor_venda', 'pct_atingimento']].copy()
    df_tv_final.columns = ['Filial', 'Nome', 'Meta', 'Valor Venda', '% Atingimento']
    
    return df_rca_final, df_tv_final

# -----------------------------------------------------------------------------
# CONSOLIDAÇÃO POR FILIAL (New Feature)
# -----------------------------------------------------------------------------
def get_branch_performance(df_rca, df_tv):
    """
    Consolida as metas e faturamentos de ambos os canais de forma agrupada por filial.
    """
    # Agrega canais de forma isolada
    branch_rca = df_rca.groupby('Filial')[['Meta', 'Valor Venda']].sum().reset_index()
    branch_tv = df_tv.groupby('Filial')[['Meta', 'Valor Venda']].sum().reset_index()
    
    # Merge das estruturas geográficas
    df_branch = pd.merge(branch_rca, branch_tv, on='Filial', how='outer', suffixes=('_rca', '_tv')).fillna(0)
    
    # Soma ponderada dos canais
    df_branch['Meta'] = df_branch['Meta_rca'] + df_branch['Meta_tv']
    df_branch['Valor Venda'] = df_branch['Valor Venda_rca'] + df_branch['Valor Venda_tv']
    
    # Cálculo preciso de atingimento da filial
    df_branch['% Atingimento'] = np.where(
        df_branch['Meta'] > 0, 
        df_branch['Valor Venda'] / df_branch['Meta'], 
        0
    )
    
    # Ordenação decrescente por atingimento
    return df_branch[['Filial', 'Meta', 'Valor Venda', '% Atingimento']].sort_values(by='% Atingimento', ascending=False)

# -----------------------------------------------------------------------------
# RENDERIZAÇÃO E INTERFACE GRÁFICA
# -----------------------------------------------------------------------------
def main():
    # Autorefresh a cada 60 segundos
    st_autorefresh(interval=60000, limit=500, key="data_refresh")
    inject_custom_css()
    
    st.title("🚀 Cockpit do Evento de Vendas")
    st.markdown("Acompanhamento *Intraday* de Faturamento e Atingimento de Metas")
    st.divider()

    try:
        dim_rca, dim_tv, meta_rca, meta_tv, fat = load_data()
        df_rca_final, df_tv_final = process_data(dim_rca, dim_tv, meta_rca, meta_tv, fat)
    except Exception as e:
        st.error(f"Erro na ingestão de dados. Verifique a pasta 'data/'. Detalhe: {e}")
        return

    # --- CARDS EXECUTIVOS ---
    meta_total = df_rca_final['Meta'].sum() + df_tv_final['Meta'].sum()
    venda_total = fat['valor_venda'].sum() 
    pct_geral = (venda_total / meta_total) if meta_total > 0 else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Meta Total", f"R$ {meta_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    with col2:
        st.metric("Faturamento Realizado", f"R$ {venda_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    with col3:
        delta_color = "normal" if pct_geral >= 1 else "inverse"
        st.metric("% Atingimento Geral", f"{pct_geral * 100:.2f}%", delta=f"{(pct_geral - 1) * 100:.2f}% vs Meta", delta_color=delta_color)

    st.divider()

    # --- ESTRUTURA DE ABAS (Adicionada a Aba de Filiais) ---
    tab_rca, tab_tv, tab_filial = st.tabs([
        "📊 Performance RCA", 
        "🎧 Performance Televendas", 
        "🏢 Performance por Filial"
    ])

    # Configuração de Colunas do Dataframe
    column_config = {
        "Filial": st.column_config.NumberColumn("Filial", format="%d"),
        "Meta": st.column_config.NumberColumn("Meta", format="R$ %.2f"),
        "Valor Venda": st.column_config.NumberColumn("Valor Venda", format="R$ %.2f"),
        "% Atingimento": st.column_config.ProgressColumn(
            "% Atingimento",
            help="Barra de progresso do atingimento da meta",
            format="%.2f",
            min_value=0,
            max_value=1.5,
        )
    }

    with tab_rca:
        st.subheader("Força de Vendas Externa (RCA)")
        st.dataframe(
            df_rca_final.sort_values(by='% Atingimento', ascending=False), 
            use_container_width=True, 
            hide_index=True,
            column_config=column_config
        )

    with tab_tv:
        st.subheader("Vendas Internas (Televendas)")
        st.dataframe(
            df_tv_final.sort_values(by='% Atingimento', ascending=False), 
            use_container_width=True, 
            hide_index=True,
            column_config=column_config
        )

    # Nova Aba: Performance por Filial Consolidada
    with tab_filial:
        st.subheader("Consolidado de Metas e Vendas por Filial")
        df_filial_final = get_branch_performance(df_rca_final, df_tv_final)
        st.dataframe(
            df_filial_final, 
            use_container_width=True, 
            hide_index=True,
            column_config=column_config
        )

if __name__ == "__main__":
    main()