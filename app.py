import streamlit as st
import pandas as pd
import data_processor
import graphic_renderer
import os

# --- DEBUG DE DEPLOY RADICAL ---
import os
from pathlib import Path
import streamlit as st

def deploy_check():
    print(f"=== CONFERÊNCIA DE ASSETS (BASE64) ===")
    try:
        from image_data import IMAGES
        count = len(IMAGES)
        print(f"SUCESSO: Banco de imagens carregado com {count} chaves.")
        if count == 0:
            print("AVISO: O banco de imagens IMAGES está VAZIO!")
        else:
            # Lista as primeiras 5 chaves para confirmar o padrão
            sample = list(IMAGES.keys())[:5]
            print(f"Amostra de chaves: {sample}")
    except ImportError:
        print("ERRO CRÍTICO: Arquivo 'image_data.py' não encontrado no servidor!")
    except Exception as e:
        print(f"ERRO AO CARREGAR IMAGENS: {e}")

deploy_check()
# --- FIM DEBUG ---

# --- SISTEMA DE AUTENTICAÇÃO (PIN) ---
def check_password():
    """Retorna True se o usuário digitou o PIN correto."""
    def password_entered():
        if st.session_state["pin"] == st.secrets.get("ACCESS_PIN", "1234"):
            st.session_state["authenticated"] = True
            del st.session_state["pin"] # Limpa o PIN da memória
        else:
            st.session_state["authenticated"] = False

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        # Tela de Login
        st.markdown("<h1 style='text-align: center;'>🔒 Acesso Restrito</h1>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            st.text_input("Digite o PIN de 4 dígitos", type="password", on_change=password_entered, key="pin")
            if "authenticated" in st.session_state and not st.session_state["authenticated"]:
                 if "pin" not in st.session_state: # Se o PIN foi deletado mas a auth falhou antes
                    st.error("❌ PIN incorreto! Tente novamente.")
        return False
    return True

if not check_password():
    st.stop() # Interrompe a execução do app se não estiver autenticado

# Configuração da Página - Modo Wide para caber as tabelas
st.set_page_config(page_title="Análise xG/xGA Brasileirão", layout="wide")

# Título e Estilo
st.title("⚽ Análise xG/xGA - Brasileirão 2026")
st.markdown("""
<style>
    .stTable {font-family: 'Arial', sans-serif;}
    .metric-box {
        border: 1px solid #ddd;
        padding: 10px;
        border-radius: 5px;
        background-color: #f9f9f9;
        text-align: center;
    }
    .metric-header {font-size: 0.8em; color: #666; font-weight: bold;}
    .metric-value {font-size: 1.2em; font-weight: bold;}
    
    /* Cores das métricas */
    .good {color: #2e7d32;} /* Verde */
    .bad {color: #c62828;} /* Vermelho */
    .neutral {color: #f57f17;} /* Laranja */
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR: CONFIGURAÇÕES E UPLOAD ---
st.sidebar.header("📂 Arquivo e Filtros")

# Upload de Arquivo
uploaded_file = st.sidebar.file_uploader("Carregar Planilha (CSV ou Excel)", type=['csv', 'xlsx'])

# Se não tiver upload, mostra aviso
if uploaded_file is not None:
    # 1. Carregar Dados
    df = data_processor.load_and_clean_data(uploaded_file)
    
    if isinstance(df, str): # Erro retornado como string
        st.error(df)
    else:
        st.sidebar.success(f"Dados carregados: {len(df)} jogos encontrados.")
        
        # 2. Filtros
        st.sidebar.divider()
        st.sidebar.subheader("⚙️ Parâmetros da Análise")
        
        # Rodadas Disponíveis (Apenas as que tem jogos no CSV)
        rodadas_disponiveis = sorted(df['Rodada'].unique().tolist())
        
        # Tenta selecionar a última rodada disponível por padrão
        idx_padrao = len(rodadas_disponiveis) - 1 if rodadas_disponiveis else 0
        rodada_selecionada = st.sidebar.selectbox("Rodada Alvo", rodadas_disponiveis, index=idx_padrao)
        
        n_jogos = st.sidebar.number_input("Recorte (N Jogos)", min_value=1, max_value=20, value=3)
        
        tipo_filtro = st.sidebar.radio("Tipo de Filtro", ["POR_MANDO", "TODOS"], index=0, help="POR_MANDO: Mandante vê jogos em casa, Visitante vê jogos fora.\nTODOS: Considera todos os jogos recentes.")
        
        # 3. Processamento Principal
        confrontos = data_processor.get_confrontos_rodada(df, rodada_selecionada)
        
        if not confrontos:
            st.warning(f"Sem jogos encontrados para a Rodada {rodada_selecionada}.")
        else:
            st.subheader(f"📊 Análise - Rodada {rodada_selecionada}")
            st.info(f"Filtro Aplicado: Últimos **{n_jogos}** jogos ({'Considerando Mando' if tipo_filtro == 'POR_MANDO' else 'Geral'})")
            
            # Listas para montar os DataFrames finais
            dados_tabela_mandante = []
            dados_tabela_visitante = []
            
            progress_bar = st.progress(0)
            
            for i, confronto in enumerate(confrontos):
                mandante = confronto['Mandante']
                visitante = confronto['Visitante']
                data_jogo = confronto['Data_Jogo']
                
                # CÁLCULOS
                # Para Tabela Superior (Mandante)
                stats_mandante_ataque, _ = data_processor.calcular_metricas(df, mandante, data_jogo, n_jogos, tipo_filtro, is_mandante_na_analise=True)
                stats_visitante_defesa, _ = data_processor.calcular_metricas(df, visitante, data_jogo, n_jogos, tipo_filtro, is_mandante_na_analise=False)
                
                row_mand = {
                    "MANDANTE": mandante,
                    "GP": stats_mandante_ataque['GP'],
                    "SG ced": stats_mandante_ataque['SG_Ced'],
                    "xG casa": float(stats_mandante_ataque['xG']), # Mantendo float para o renderer
                    "xGA fora": float(stats_visitante_defesa['xGA']), # Mantendo float para o renderer
                    "SG conq": stats_visitante_defesa['SG_Conq'],
                    "GS": stats_visitante_defesa['GS'],
                    "VISITANTE": visitante
                }
                dados_tabela_mandante.append(row_mand)
                
                # Para Tabela Inferior (Visitante)
                stats_visitante_ataque, _ = data_processor.calcular_metricas(df, visitante, data_jogo, n_jogos, tipo_filtro, is_mandante_na_analise=False)
                stats_mandante_defesa, _ = data_processor.calcular_metricas(df, mandante, data_jogo, n_jogos, tipo_filtro, is_mandante_na_analise=True)
                
                row_vis = {
                    "VISITANTE": visitante,
                    "GP": stats_visitante_ataque['GP'],
                    "SG ced": stats_visitante_ataque['SG_Ced'],
                    "xG fora": float(stats_visitante_ataque['xG']), # Mantendo float para o renderer
                    "xGA casa": float(stats_mandante_defesa['xGA']), # Mantendo float para o renderer
                    "SG conq": stats_mandante_defesa['SG_Conq'],
                    "GS": stats_mandante_defesa['GS'],
                    "MANDANTE": mandante
                }
                dados_tabela_visitante.append(row_vis)
                
                progress_bar.progress((i + 1) / len(confrontos))
            
            # --- RENDERIZAÇÃO ---
            df_view_mand = pd.DataFrame(dados_tabela_mandante)
            df_view_vis = pd.DataFrame(dados_tabela_visitante)
            
            st.subheader(f"🏠 Análise Mandantes")
            st.dataframe(df_view_mand, hide_index=True, use_container_width=True)
            
            st.subheader(f"✈️ Análise Visitantes")
            st.dataframe(df_view_vis, hide_index=True, use_container_width=True)

            # --- ARTE FINAL ---
            st.markdown("---")
            if st.button("GERAR ARTE FINAL"):
                with st.spinner("Gerando PNG..."):
                    try:
                        # DEBUG: Mostrar tipos e formas antes da chamada
                        print(f"DEBUG: df_view_mand shape: {df_view_mand.shape}")
                        print(f"DEBUG: df_view_vis shape: {df_view_vis.shape}")
                        
                        output_path = graphic_renderer.generate_infographic(df_view_mand, df_view_vis, rodada_selecionada, n_jogos, tipo_filtro)
                        
                        if output_path:
                            st.success("Arte gerada!")
                            st.image(output_path, width='stretch')
                            with open(output_path, "rb") as file:
                                st.download_button("⬇️ BAIXAR PNG", file, f"Analise_R{rodada_selecionada}.png", "image/png")
                    except NameError as e:
                        st.error(f"❌ ERRO DE NOME (NameError): {e}")
                        st.info("Verifique se todas as variáveis estão definidas. Veja os logs para detalhes.")
                        print(f"ERROR: NameError in app.py: {e}")
                    except Exception as e:
                        st.error(f"❌ Erro ao gerar arte final: {type(e).__name__} - {e}")
                        import traceback
                        st.code(traceback.format_exc())
else:
    st.info("Aguardando upload do CSV...")
