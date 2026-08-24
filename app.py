import streamlit as st
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
import os

# -----------------------------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA E ARQUITETURA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Dashboard - Performance Comercial",
    page_icon="📊",
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
@st.cache_data(ttl=900)
def load_data():
    """
    Ingestão e sanitização das bases de vendas e metas dimensionais.
    Garante integridade referencial aplicando Type Casting estrito.
    """
    # 1. Leitura dos Arquivos (SSOT)
    df_fatos = pd.read_excel("data/vadas_validade_9_meses.xlsx")
    df_meta_sup = pd.read_excel("data/meta_supervisor.xlsx")
    
    # 2. Normalização de Nomenclatura das Colunas (Lower case)
    df_fatos.columns = [str(col).strip().lower() for col in df_fatos.columns]
    df_meta_sup.columns = [str(col).strip().lower() for col in df_meta_sup.columns]
    
    # 3. Renomeação de Colunas Dimensionais para Padronização
    df_meta_sup.rename(columns={
        'cod_filial': 'filial',
        'supervisores': 'nm_supervisor',
        'meta supervisão': 'meta'
    }, inplace=True)
    
    if 'uf_filial' in df_fatos.columns:
        df_fatos.rename(columns={'uf_filial': 'filial'}, inplace=True)
        
    # 4. Type Casting: Chaves de Join
    for df in [df_fatos, df_meta_sup]:
        df['filial'] = df['filial'].astype(str).str.strip().str.upper()
        df['cod_supervisor'] = df['cod_supervisor'].astype(str).str.strip()
        
    # 5. Type Casting: Fatos Financeiros
    df_fatos['total_valor_pedido'] = pd.to_numeric(df_fatos.get('total_valor_pedido', 0), errors='coerce').fillna(0)
    df_fatos['total_valor_venda'] = pd.to_numeric(df_fatos.get('total_valor_venda', 0), errors='coerce').fillna(0)
    df_meta_sup['meta'] = pd.to_numeric(df_meta_sup.get('meta', 0), errors='coerce').fillna(0)
    
    return df_fatos, df_meta_sup

# -----------------------------------------------------------------------------
# PROCESSAMENTO DE DADOS (Transformations & Aggregations)
# -----------------------------------------------------------------------------
def process_data(df_fatos, df_meta_sup):
    """
    Gera dois níveis distintos de agregação (Grãos) para o Dashboard.
    """
    # --- PIPELINE 1: Visão Ranking de Supervisores (Integração Fato-Dimensão) ---
    df_sup_fatos = df_fatos.groupby(['filial', 'cod_supervisor'])[['total_valor_pedido', 'total_valor_venda']].sum().reset_index()
    df_sup = pd.merge(df_sup_fatos, df_meta_sup, on=['filial', 'cod_supervisor'], how='left')
    
    df_sup['meta'] = df_sup['meta'].fillna(0)
    df_sup['nm_supervisor'] = df_sup['nm_supervisor'].fillna('SEM SUPERVISOR')
    
    df_sup['pct_atingimento'] = np.where(
        df_sup['meta'] > 0, 
        df_sup['total_valor_venda'] / df_sup['meta'], 
        0
    )
    
    df_sup = df_sup[['filial', 'cod_supervisor', 'nm_supervisor', 'meta', 'total_valor_pedido', 'total_valor_venda', 'pct_atingimento']]
    df_sup.columns = ['Filial', 'Cód. Sup', 'Supervisor', 'Meta', 'Valor Pedido', 'Valor Venda', '% Atingimento']

    # --- PIPELINE 2: Visão Executiva Resumida por Filial ---
    df_resumo = df_fatos.groupby('filial')[['total_valor_pedido', 'total_valor_venda']].sum().reset_index()
    df_resumo['pct_conversao'] = np.where(
        df_resumo['total_valor_pedido'] > 0, 
        df_resumo['total_valor_venda'] / df_resumo['total_valor_pedido'], 
        0
    )
    df_resumo.columns = ['Filial', 'Valor Pedido', 'Valor Venda', '% Conversão']
    
    return df_sup, df_resumo

# -----------------------------------------------------------------------------
# RENDERIZAÇÃO E INTERFACE GRÁFICA (UI)
# -----------------------------------------------------------------------------
def main():
    st_autorefresh(interval=60000, limit=500, key="data_refresh")
    inject_custom_css()
    
    st.title("📊 Monitoramento de Performance Comercial")
    st.markdown("Acompanhamento de pedidos vs faturamento cruzado com metas de supervisão.")
    st.divider()

    try:
        df_fatos, df_meta_sup = load_data()
        df_sup, df_resumo = process_data(df_fatos, df_meta_sup)
    except Exception as e:
        st.error(f"⚠️ Erro de I/O ao ler os arquivos da pasta 'data/'. Detalhe técnico: {e}")
        return

    # --- CARDS EXECUTIVOS (KPIs Globais) ---
    pedido_total = df_fatos['total_valor_pedido'].sum()
    venda_total = df_fatos['total_valor_venda'].sum()
    gap_faturamento = pedido_total - venda_total
    
    pct_geral = (venda_total / pedido_total) if pedido_total > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Volume Pedido", f"R$ {pedido_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    with col2:
        st.metric("Faturamento Efetivado", f"R$ {venda_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    with col3:
        st.metric("Gap de Faturamento", f"R$ {gap_faturamento:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    with col4:
        delta_color = "normal" if pct_geral >= 1 else "inverse"
        st.metric("% Conversão Global", f"{pct_geral * 100:.2f}%", 
                  delta=f"{(pct_geral - 1) * 100:.2f}% Gap", delta_color=delta_color)

    st.divider()

    # --- ESTRUTURA DE ABAS ---
    tab_resumo, tab_sup = st.tabs([
        "🌎 Resumo por Filial", 
        "👔 Força de Vendas (Supervisores)"
    ])

    # Configuração de Colunas Comum
    column_config_base = {
        "Filial": st.column_config.TextColumn("Filial/UF"),
        "Valor Pedido": st.column_config.NumberColumn("Valor Pedido", format="R$ %.2f"),
        "Valor Venda": st.column_config.NumberColumn("Valor Venda", format="R$ %.2f")
    }

    # ABA 1: RESUMO EXECUTIVO
    with tab_resumo:
        col_config_resumo = column_config_base.copy()
        col_config_resumo.update({
            "% Conversão": st.column_config.ProgressColumn(
                "Conversão (Faturado/Pedido)", format="%.2f", min_value=0, max_value=1.0
            )
        })
        st.dataframe(
            df_resumo.sort_values(by='% Conversão', ascending=False), 
            use_container_width=True, hide_index=True, column_config=col_config_resumo
        )

    # ABA 2: RANKING DE SUPERVISORES
    with tab_sup:
        col_config_sup = column_config_base.copy()
        col_config_sup.update({
            "Cód. Sup": st.column_config.TextColumn("Código"),
            "Supervisor": st.column_config.TextColumn("Nome do Supervisor"),
            "Meta": st.column_config.NumberColumn("Meta", format="R$ %.2f"),
            "% Atingimento": st.column_config.ProgressColumn(
                "Atingimento da Meta (Real vs Meta)", format="%.2f", min_value=0, max_value=1.5
            )
        })
        
        filiais_sup = ["Todas"] + sorted(df_sup['Filial'].dropna().unique().tolist())
        sel_filial_sup = st.selectbox("Filtrar por Filial/UF (Supervisores):", options=filiais_sup, index=0, key='sel_sup')
        df_view_sup = df_sup if sel_filial_sup == "Todas" else df_sup[df_sup['Filial'] == sel_filial_sup]
        
        df_view_sup = df_view_sup.sort_values(by=['% Atingimento', 'Valor Venda'], ascending=[False, False]).reset_index(drop=True)
        df_view_sup.index = df_view_sup.index + 1
        
        st.dataframe(
            df_view_sup, 
            use_container_width=True, hide_index=False, column_config=col_config_sup
        )
        
    st.divider()
    
    # --- EXPORTAÇÃO DE DADOS (Observabilidade e Distribuição) ---
    st.subheader("Data Pipeline - Distribuição")
    if st.button("💾 Exportar Performance de Supervisores para a Rede"):
        try:
            target_dir = r"\\192.168.0.*\Arquivos de Usuarios\Compras"
            os.makedirs(target_dir, exist_ok=True)
            export_path = os.path.join(target_dir, "export_performance_supervisores.csv")
            
            df_sup.to_csv(export_path, index=False, sep=';', decimal=',')
            st.success(f"Snapshot processado e salvo com sucesso no diretório de destino: `{export_path}`")
        except Exception as e:
            st.error(f"Falha de permissão (I/O) ao tentar escrever no diretório da rede. Detalhe técnico: {e}")

if __name__ == "__main__":
    main()