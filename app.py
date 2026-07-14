import streamlit as st
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh

# Configuração da página (deve ser o primeiro comando Streamlit)
st.set_page_config(
    page_title="Dashboard TOTAL Day",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# INJEÇÃO DE ESTILO CUSTOMIZADO (Clean UI / UX)
# -----------------------------------------------------------------------------
def inject_custom_css():
    """
    Injeta CSS customizado no frontend do Streamlit para ocultar elementos
    padrões e estilizar os cartões de métrica de forma profissional.
    """
    st.markdown("""
        <style>
        /* Oculta a barra superior padrão (menu sanduíche, botão deploy e gap de espaço) */
        header, [data-testid="stHeader"] {
            visibility: hidden;
            height: 0% !important;
            padding: 0px !important;
        }
        
        /* Ajuste de padding: otimiza o espaço vertical da tela operacional */
        .block-container { 
            padding-top: 1.5rem !important; 
            padding-bottom: 1rem !important; 
            max-width: 95% !important; 
        }
        
        /* Estilização Avançada dos Cartões de KPI (Agnóstico ao Tema Dark/Light) */
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
            min-height: 145px !important; /* Fix: Garante simetria visual */
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        
        /* Alinhamento vertical interno do cartão */
        [data-testid="stMetric"] > div {
            margin-top: auto;
            margin-bottom: auto;
        }
        
        /* Centralização vertical de logos no cabeçalho */
        .logo-container {
            display: flex;
            align-items: center;
            height: 100%;
        }
        </style>
    """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 1. DATA INGESTION & CACHING (Performance Tuning)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=300)
def load_data():
    # Carregamento das Dimensões
    dim_rca = pd.read_excel("data/dim_rca.xlsx")
    dim_tv = pd.read_excel("data/dim_televendas.xlsx")
    
    # Carregamento das Metas
    meta_rca = pd.read_excel("data/meta_rca.xlsx")
    meta_tv = pd.read_excel("data/meta_televendas.xlsx")
    
    # Carregamento das Vendas
    fat = pd.read_excel("data/fat_total_day.xlsx")
    
    # ---> ADICIONE ESTAS LINHAS AQUI <---
    # Normalizar os nomes das colunas para minúsculas para evitar erros com o Oracle
    dim_rca.columns = [col.lower() for col in dim_rca.columns]
    dim_tv.columns = [col.lower() for col in dim_tv.columns]
    meta_rca.columns = [col.lower() for col in meta_rca.columns]
    meta_tv.columns = [col.lower() for col in meta_tv.columns]
    fat.columns = [col.lower() for col in fat.columns]
    # -----------------------------------
    
    # Garantir tipagem correta
    meta_rca['meta'] = pd.to_numeric(meta_rca['meta'], errors='coerce').fillna(0)
    meta_tv['meta'] = pd.to_numeric(meta_tv['meta'], errors='coerce').fillna(0)
    fat['valor_venda'] = pd.to_numeric(fat['valor_venda'], errors='coerce').fillna(0)
    
    return dim_rca, dim_tv, meta_rca, meta_tv, fat

# -----------------------------------------------------------------------------
# 2. DATA TRANSFORMATION & MODELING (Business Logic)
# -----------------------------------------------------------------------------
def process_data(dim_rca, dim_tv, meta_rca, meta_tv, fat):
    
    # --- Modelo RCA ---
    # 1. Agregar Faturamento por RCA
    fat_rca = fat.groupby('cod_rca')['valor_venda'].sum().reset_index()
    
    # 2. Join Meta com Dimensão para pegar o Nome
    df_rca = pd.merge(meta_rca, dim_rca, left_on='cod_rca', right_on='codigo_rca', how='left')
    
    # 3. Join com Faturamento Realizado
    df_rca = pd.merge(df_rca, fat_rca, on='cod_rca', how='left')
    df_rca['valor_venda'] = df_rca['valor_venda'].fillna(0)
    
    # 4. Cálculo de Atingimento (Data Quality: Prevenção de divisão por zero)
    df_rca['pct_atingimento'] = np.where(
        df_rca['meta'] > 0, 
        df_rca['valor_venda'] / df_rca['meta'], 
        0
    )
    
    # 5. Seleção e renomeação de colunas para o UI
    df_rca_final = df_rca[['filial', 'nm_rca', 'meta', 'valor_venda', 'pct_atingimento']].copy()
    df_rca_final.columns = ['Filial', 'Nome', 'Meta', 'Valor Venda', '% Atingimento']


    # --- Modelo Televendas ---
    # 1. Agregar Faturamento por Televendas
    fat_tv = fat.groupby('cod_televendas')['valor_venda'].sum().reset_index()
    
    # 2. Join Meta com Dimensão
    # Nota: Ajustado para refletir 'cod_televenda' no arquivo de meta vs 'codigo_televendas' na dimensão
    df_tv = pd.merge(meta_tv, dim_tv, left_on='cod_televenda', right_on='codigo_televendas', how='left')
    
    # 3. Join com Faturamento Realizado
    # Nota: Assumindo que a chave de merge seja 'cod_televenda' com 'cod_televendas'
    df_tv = pd.merge(df_tv, fat_tv, left_on='cod_televenda', right_on='cod_televendas', how='left')
    df_tv['valor_venda'] = df_tv['valor_venda'].fillna(0)
    
    # 4. Cálculo de Atingimento
    df_tv['pct_atingimento'] = np.where(
        df_tv['meta'] > 0, 
        df_tv['valor_venda'] / df_tv['meta'], 
        0
    )
    
    # 5. Seleção e renomeação de colunas
    df_tv_final = df_tv[['filial', 'nm_televendas', 'meta', 'valor_venda', 'pct_atingimento']].copy()
    df_tv_final.columns = ['Filial', 'Nome', 'Meta', 'Valor Venda', '% Atingimento']
    
    return df_rca_final, df_tv_final

# -----------------------------------------------------------------------------
# 3. UI EXECUTIVA & RENDERIZAÇÃO
# -----------------------------------------------------------------------------
def main():

    st_autorefresh(interval=60000, limit=500, key="data_refresh")

    inject_custom_css()

    st.title("🚀 Cockpit TOTAL Day")
    st.markdown("Acompanhamento de Faturamento e Atingimento de Metas")
    st.divider()

    # Executa a pipeline de dados
    try:
        dim_rca, dim_tv, meta_rca, meta_tv, fat = load_data()
        df_rca_final, df_tv_final = process_data(dim_rca, dim_tv, meta_rca, meta_tv, fat)
    except Exception as e:
        st.error(f"Erro na ingestão de dados. Verifique os arquivos na pasta 'data/'. Detalhe técnico: {e}")
        return

    # --- KPIs GERAIS (Cards) ---
    meta_total = df_rca_final['Meta'].sum() + df_tv_final['Meta'].sum()
    # Para o faturamento geral, somamos a fato crua para não perder nada por possíveis falhas de cadastro (Orphan Records)
    venda_total = fat['valor_venda'].sum() 
    pct_geral = (venda_total / meta_total) if meta_total > 0 else 0

    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Meta Total", f"R$ {meta_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    with col2:
        st.metric("Valor Venda Total", f"R$ {venda_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    with col3:
        # Lógica de cor baseada no atingimento
        delta_color = "normal" if pct_geral >= 1 else "inverse"
        st.metric("% Atingimento Geral", f"{pct_geral * 100:.2f}%", delta=f"{(pct_geral - 1) * 100:.2f}% vs Meta", delta_color=delta_color)

    st.divider()

    # --- TABELAS GRANULARES ---
    # Configuração de formatação visual das DataFrames no Streamlit
    column_config = {
        "Filial": st.column_config.NumberColumn("Filial", format="%d"),
        "Meta": st.column_config.NumberColumn("Meta", format="R$ %.2f"),
        "Valor Venda": st.column_config.NumberColumn("Valor Venda", format="R$ %.2f"),
        "% Atingimento": st.column_config.ProgressColumn(
            "% Atingimento",
            help="Barra de progresso do atingimento da meta",
            format="%.2f",
            min_value=0,
            max_value=1.5, # Capa o visual da barra em 150% para não quebrar a escala
        )
    }

    tab_rca, tab_tv = st.tabs(["📊 Performance RCA", "🎧 Performance Televendas"])

    with tab_rca:
        st.subheader("Acompanhamento - Força de Vendas Externa (RCA)")
        # Ordenação por atingimento (Do melhor para o pior)
        st.dataframe(
            df_rca_final.sort_values(by='% Atingimento', ascending=False), 
            use_container_width=True, 
            hide_index=True,
            column_config=column_config
        )

    with tab_tv:
        st.subheader("Acompanhamento - Vendas Internas (Televendas)")
        # Ordenação por atingimento
        st.dataframe(
            df_tv_final.sort_values(by='% Atingimento', ascending=False), 
            use_container_width=True, 
            hide_index=True,
            column_config=column_config
        )

if __name__ == "__main__":
    main()