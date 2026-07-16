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
@st.cache_data(ttl=900)
def load_data():
    """
    Carrega as dimensões e tabelas fato a partir do diretório local.
    Normaliza todas as colunas (lower + strip) para mitigar quebras do Oracle.
    """
    dim_rca = pd.read_excel("data/dim_rca.xlsx")
    dim_tv = pd.read_excel("data/dim_televendas.xlsx")
    meta_rca = pd.read_excel("data/meta_rca.xlsx")
    meta_tv = pd.read_excel("data/meta_televendas.xlsx")
    fat = pd.read_excel("data/fat_total_day.xlsx")
    
    # Normalização preventiva extrema de nomenclatura (Data Quality)
    for df in [dim_rca, dim_tv, meta_rca, meta_tv, fat]:
        # Strip remove espaços acidentais no início ou fim do nome da coluna
        df.columns = [str(col).strip().lower() for col in df.columns]
        
        # Data Quality: Força a tipagem de 'filial' para string
        if 'filial' in df.columns:
            df['filial'] = df['filial'].astype(str)
            
    # Saneamento de tipos numéricos
    meta_rca['meta'] = pd.to_numeric(meta_rca['meta'], errors='coerce').fillna(0)
    meta_tv['meta'] = pd.to_numeric(meta_tv['meta'], errors='coerce').fillna(0)
    fat['valor_venda'] = pd.to_numeric(fat['valor_venda'], errors='coerce').fillna(0)
    
    # Prevenção de quebra: verifica se a coluna valor_pedido foi extraída com sucesso
    if 'valor_pedido' in fat.columns:
        fat['valor_pedido'] = pd.to_numeric(fat['valor_pedido'], errors='coerce').fillna(0)
    else:
        fat['valor_pedido'] = 0.0
    
    return dim_rca, dim_tv, meta_rca, meta_tv, fat

# -----------------------------------------------------------------------------
# PROCESSAMENTO DE DADOS (Business Intelligence Logic)
# -----------------------------------------------------------------------------
def process_data(dim_rca, dim_tv, meta_rca, meta_tv, fat):
    # --- Pipeline RCA ---
    # Agrega simultaneamente as duas métricas financeiras (venda e pedido)
    fat_rca = fat.groupby('cod_rca')[['valor_venda', 'valor_pedido']].sum().reset_index()
    
    # 1. Utiliza dim_rca como tabela base
    df_rca = dim_rca.copy()
    
    # 2. Remove a coluna 'filial' da meta_rca antes do merge para evitar conflitos
    meta_rca_merge = meta_rca[['cod_rca', 'meta']] if 'filial' in meta_rca.columns else meta_rca
    
    # 3. Joins
    df_rca = pd.merge(df_rca, meta_rca_merge, left_on='codigo_rca', right_on='cod_rca', how='left')
    df_rca = pd.merge(df_rca, fat_rca, left_on='codigo_rca', right_on='cod_rca', how='left')
    
    # 4. Tratamento Numérico
    df_rca['meta'] = df_rca['meta'].fillna(0)
    df_rca['valor_venda'] = df_rca['valor_venda'].fillna(0)
    df_rca['valor_pedido'] = df_rca['valor_pedido'].fillna(0)
    
    # REGRA DE NEGÓCIO DA CAMPANHA: Atingimento % focado estritamente no VALOR PEDIDO
    df_rca['pct_atingimento'] = np.where(df_rca['meta'] > 0, df_rca['valor_pedido'] / df_rca['meta'], 0)
    
    # 5. Filtro de Origem (Apenas perfil RCA)
    if 'origem' in df_rca.columns:
        df_rca = df_rca[df_rca['origem'].astype(str).str.strip().str.upper() == 'RCA']
    
    if 'supervisor' not in df_rca.columns:
        df_rca['supervisor'] = 'N/A'
    else:
        df_rca['supervisor'] = df_rca['supervisor'].fillna('Sem Supervisor')
        
    df_rca_final = df_rca[['filial', 'nm_rca', 'supervisor', 'meta', 'valor_pedido', 'valor_venda', 'pct_atingimento']].copy()
    df_rca_final.columns = ['Filial', 'Nome', 'Supervisor', 'Meta', 'Valor Pedido', 'Valor Venda', '% Atingimento']

    # --- Pipeline Televendas ---
    if 'origem_pedido' in fat.columns:
        fat_tv_raw = fat[fat['origem_pedido'].astype(str).str.strip().str.upper() == 'TELEMARKETING']
    else:
        fat_tv_raw = fat
        
    fat_tv = fat_tv_raw.groupby('cod_televendas')[['valor_venda', 'valor_pedido']].sum().reset_index()
    
    df_tv = pd.merge(meta_tv, dim_tv, left_on='cod_televenda', right_on='codigo_televendas', how='left')
    df_tv = pd.merge(df_tv, fat_tv, left_on='cod_televenda', right_on='cod_televendas', how='left')
    
    df_tv['valor_venda'] = df_tv['valor_venda'].fillna(0)
    df_tv['valor_pedido'] = df_tv['valor_pedido'].fillna(0)
    
    # REGRA DE NEGÓCIO DA CAMPANHA: Atingimento % focado estritamente no VALOR PEDIDO
    df_tv['pct_atingimento'] = np.where(df_tv['meta'] > 0, df_tv['valor_pedido'] / df_tv['meta'], 0)
    
    df_tv_final = df_tv[['filial', 'nm_televendas', 'meta', 'valor_pedido', 'valor_venda', 'pct_atingimento']].copy()
    df_tv_final.columns = ['Filial', 'Nome', 'Meta', 'Valor Pedido', 'Valor Venda', '% Atingimento']
    
    return df_rca_final, df_tv_final

# -----------------------------------------------------------------------------
# CONSOLIDAÇÃO GEOGRÁFICA (Filial) 
# -----------------------------------------------------------------------------
def get_branch_performance(dim_rca, meta_rca, fat):
    """
    Consolida o faturamento e meta global por filial (Baseado no Pedido).
    """
    df_meta = meta_rca.groupby('filial')['meta'].sum().reset_index() if 'filial' in meta_rca.columns else pd.DataFrame(columns=['filial', 'meta'])
    df_meta.rename(columns={'meta': 'Meta'}, inplace=True)
    
    fat_rca = fat.groupby('cod_rca')[['valor_venda', 'valor_pedido']].sum().reset_index()
    df_v_rca = pd.merge(dim_rca[['codigo_rca', 'filial']], fat_rca, left_on='codigo_rca', right_on='cod_rca', how='left').fillna({'valor_venda': 0, 'valor_pedido': 0})
    
    df_venda = df_v_rca.groupby('filial')[['valor_venda', 'valor_pedido']].sum().reset_index()
    df_venda.rename(columns={'valor_venda': 'Valor Venda', 'valor_pedido': 'Valor Pedido'}, inplace=True)
    
    df_branch = pd.merge(df_meta[['filial', 'Meta']], df_venda[['filial', 'Valor Pedido', 'Valor Venda']], on='filial', how='outer').fillna(0)
    
    # REGRA DE NEGÓCIO DA CAMPANHA: Atingimento % focado estritamente no VALOR PEDIDO
    df_branch['% Atingimento'] = np.where(df_branch['Meta'] > 0, df_branch['Valor Pedido'] / df_branch['Meta'], 0)
    
    df_branch.rename(columns={'filial': 'Filial'}, inplace=True)
    df_branch['Filial'] = df_branch['Filial'].astype(str)
    
    return df_branch[['Filial', 'Meta', 'Valor Pedido', 'Valor Venda', '% Atingimento']].sort_values(by='% Atingimento', ascending=False)

# -----------------------------------------------------------------------------
# CONSOLIDAÇÃO HIERÁRQUICA (Supervisor)
# -----------------------------------------------------------------------------
def get_supervisor_performance(df_rca):
    """Consolida as metas e pedidos através de agregação por Supervisor."""
    df_sup = df_rca.groupby('Supervisor')[['Meta', 'Valor Pedido', 'Valor Venda']].sum().reset_index()
    
    # REGRA DE NEGÓCIO DA CAMPANHA: Atingimento % focado estritamente no VALOR PEDIDO
    df_sup['% Atingimento'] = np.where(df_sup['Meta'] > 0, df_sup['Valor Pedido'] / df_sup['Meta'], 0)
    
    return df_sup.sort_values(by='% Atingimento', ascending=False)

# -----------------------------------------------------------------------------
# RENDERIZAÇÃO E INTERFACE GRÁFICA
# -----------------------------------------------------------------------------
def main():
    # Autorefresh a cada 60 segundos
    st_autorefresh(interval=60000, limit=500, key="data_refresh")
    inject_custom_css()
    
    st.title("🚀 Cockpit do Evento de Vendas")
    st.markdown("Acompanhamento *Intraday* de Captação, Faturamento e Atingimento de Metas")
    st.divider()

    try:
        dim_rca, dim_tv, meta_rca, meta_tv, fat = load_data()
        df_rca_final, df_tv_final = process_data(dim_rca, dim_tv, meta_rca, meta_tv, fat)
    except Exception as e:
        st.error(f"Erro na ingestão de dados. Verifique a estrutura da pasta 'data/'. Detalhe técnico: {e}")
        return

    # --- CARDS EXECUTIVOS ---
    meta_total = meta_rca['meta'].sum() 
    pedido_total = fat['valor_pedido'].sum() 
    venda_total = fat['valor_venda'].sum() 
    
    # REGRA DE NEGÓCIO: O Atingimento Geral Macroeconómico passa a refletir a Captação (Pedidos)
    pct_geral = (pedido_total / meta_total) if meta_total > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Meta Total", f"R$ {meta_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    with col2:
        st.metric("Total Pedido", f"R$ {pedido_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    with col3:
        st.metric("Faturamento Realizado", f"R$ {venda_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    with col4:
        delta_color = "normal" if pct_geral >= 1 else "inverse"
        st.metric("% Atingimento Geral", f"{pct_geral * 100:.2f}%", delta=f"{(pct_geral - 1) * 100:.2f}% vs Meta", delta_color=delta_color)

    st.divider()

    # --- ESTRUTURA DE ABAS ---
    tab_rca, tab_tv, tab_filial, tab_supervisor = st.tabs([
        "📊 Performance RCA", 
        "🎧 Performance Televendas", 
        "🏢 Performance por Filial",
        "👔 Performance por Supervisor"
    ])

    column_config = {
        "Filial": st.column_config.TextColumn("Filial"),
        "Meta": st.column_config.NumberColumn("Meta", format="R$ %.2f"),
        "Valor Pedido": st.column_config.NumberColumn("Valor Pedido", format="R$ %.2f"),
        "Valor Venda": st.column_config.NumberColumn("Valor Venda", format="R$ %.2f"),
        "% Atingimento": st.column_config.ProgressColumn(
            "% Atingimento",
            help="Barra de progresso de atingimento focada no Valor Pedido",
            format="%.2f",
            min_value=0,
            max_value=1.5,
        )
    }

    # --- ABA 1: RCA ---
    with tab_rca:
        st.subheader("Força de Vendas Externa (RCA)")
        
        df_rca_view = df_rca_final[df_rca_final['Meta'] >= 15000].copy()
        
        lista_filiais_rca = ["Todas"] + sorted(df_rca_view['Filial'].unique().tolist())
        filtro_rca = st.selectbox("Filtrar Filial (RCA):", options=lista_filiais_rca, index=0, key="filtro_tab_rca")
        
        if filtro_rca == "Todas":
            df_rca_filtrado = df_rca_view
        else:
            df_rca_filtrado = df_rca_view[df_rca_view['Filial'] == filtro_rca]
            
        st.dataframe(
            df_rca_filtrado.sort_values(by='% Atingimento', ascending=False), 
            use_container_width=True, 
            hide_index=True,
            column_config=column_config
        )

    # --- ABA 2: TELEVENDAS ---
    with tab_tv:
        st.subheader("Vendas Internas (Televendas)")
        
        lista_filiais_tv = ["Todas"] + sorted(df_tv_final['Filial'].unique().tolist())
        filtro_tv = st.selectbox("Filtrar Filial (Televendas):", options=lista_filiais_tv, index=0, key="filtro_tab_tv")
        
        if filtro_tv == "Todas":
            df_tv_filtrado = df_tv_final
        else:
            df_tv_filtrado = df_tv_final[df_tv_final['Filial'] == filtro_tv]
            
        st.dataframe(
            df_tv_filtrado.sort_values(by='% Atingimento', ascending=False), 
            use_container_width=True, 
            hide_index=True,
            column_config=column_config
        )

    # --- ABA 3: CONSOLIDADO POR FILIAL ---
    with tab_filial:
        st.subheader("Consolidado de Metas, Pedidos e Vendas por Filial")
        
        df_filial_final = get_branch_performance(dim_rca, meta_rca, fat)
        
        lista_filiais_geral = ["Todas"] + sorted(df_filial_final['Filial'].unique().tolist())
        filtro_filial = st.selectbox("Visualizar Filial Específica:", options=lista_filiais_geral, index=0, key="filtro_tab_consolidado")
        
        if filtro_filial == "Todas":
            df_filial_filtrado = df_filial_final
        else:
            df_filial_filtrado = df_filial_final[df_filial_final['Filial'] == filtro_filial]
            
        st.dataframe(
            df_filial_filtrado, 
            use_container_width=True, 
            hide_index=True,
            column_config=column_config
        )

    # --- ABA 4: CONSOLIDADO POR SUPERVISOR ---
    with tab_supervisor:
        st.subheader("Consolidado de Equipes por Supervisor (RCA)")
        df_sup_final = get_supervisor_performance(df_rca_final)
        
        lista_supervisores = ["Todos"] + sorted(df_sup_final['Supervisor'].unique().tolist())
        filtro_sup = st.selectbox("Visualizar Supervisor Específico:", options=lista_supervisores, index=0, key="filtro_tab_supervisor")
        
        if filtro_sup == "Todos":
            df_sup_filtrado = df_sup_final
        else:
            df_sup_filtrado = df_sup_final[df_sup_final['Supervisor'] == filtro_sup]
            
        st.dataframe(
            df_sup_filtrado, 
            use_container_width=True, 
            hide_index=True,
            column_config=column_config
        )

if __name__ == "__main__":
    main()