import pandas as pd
import numpy as np
from datetime import datetime

# --- CONFIGURAÇÕES ---
CSV_PATH = r"d:\cartoon brasil\TCC\GERAÇÃO XG XGA\PLANILHA PREENCHIMENTO DE XG E XGA.csv"

def load_and_clean_data(filepath):
    """
    Carrega o arquivo (CSV ou Excel) de forma ultra-robusta.
    Lida com objetos de upload do Streamlit e caminhos locais.
    """
    try:
        df = None
        # Obtém o nome real do arquivo se for um FileUploader do Streamlit, senão usa a string do caminho
        filename = getattr(filepath, 'name', str(filepath))
        is_excel = filename.lower().endswith(('.xlsx', '.xls'))
        
        if is_excel:
            df = pd.read_excel(filepath, header=None)
        else:
            # Tenta CSV com os separadores e encodings mais comuns
            # Reseta o ponteiro se for um arquivo aberto (Streamlit)
            if hasattr(filepath, 'seek'): filepath.seek(0)
            
            for sep in [';', ',']:
                try:
                    df = pd.read_csv(filepath, sep=sep, header=None, encoding='latin1', on_bad_lines='skip')
                    if len(df.columns) >= 9: break # Sucesso se encontrou as colunas necessárias
                    if hasattr(filepath, 'seek'): filepath.seek(0)
                except:
                    if hasattr(filepath, 'seek'): filepath.seek(0)
                    continue
            
            # Se ainda não deu certo, tenta sniffing ou fallback
            if df is None or len(df.columns) < 9:
                if hasattr(filepath, 'seek'): filepath.seek(0)
                try:
                    df = pd.read_csv(filepath, sep=None, header=None, engine='python', encoding='latin1')
                except:
                    return "Erro: Formato de arquivo não suportado ou colunas insuficientes. Use Excel (.xlsx) ou CSV com 9+ colunas."

        if df is None or df.empty:
            return "Erro: O arquivo está vazio."

        # LOCALIZAR A LINHA DE CABEÇALHO (Onde está escrito "Rodada")
        header_idx = -1
        # Procura nas primeiras 10 linhas
        for i in range(min(10, len(df))):
            row_str = " ".join(df.iloc[i].astype(str).tolist())
            if "Rodada" in row_str:
                header_idx = i
                break
        
        # Se achou o cabeçalho, corta o "lixo" acima dele
        if header_idx != -1:
            df = df.iloc[header_idx + 1:].reset_index(drop=True)
        else:
            # Se não achou "Rodada", tenta pular a primeira linha por padrão (comportamento antigo)
            if "Head-to-Head" in str(df.iloc[0, 0]):
                df = df.iloc[1:].reset_index(drop=True)

        # Selecionar Colunas Relevantes baseadas na posição detectada:
        # Index 0: Rodada | 2: Data | 4: Time Casa | 5: xG Casa | 6: Placar | 7: xG Visitante | 8: Time Visitante
        if len(df.columns) < 9:
             return f"Erro: A planilha tem apenas {len(df.columns)} colunas. São necessárias pelo menos 9."

        df = df[[0, 2, 4, 5, 6, 7, 8]].copy()
        df.columns = ['Rodada', 'Data', 'Mandante', 'xG_Casa', 'Placar', 'xG_Visitante', 'Visitante']
        
        # --- LIMPEZA DE DADOS SEGUROS ---
        # 1. Remover apenas onde Mandante ou Visitante é vazio ou é o próprio cabeçalho
        df = df.dropna(subset=['Mandante', 'Visitante'])
        df = df[~df['Mandante'].astype(str).str.contains('Time|Casa|Mandante', na=False)].reset_index(drop=True)
        
        # 2. Converter Data
        df['Data'] = pd.to_datetime(df['Data'], errors='coerce')
        # Remove apenas se nem a Rodada nem a Data existirem (garante que não pegamos o lixo do rodapé)
        df = df.dropna(subset=['Data', 'Rodada'], how='all').reset_index(drop=True)
        
        # 3. Converter Números (xG) - Trocar vírgula por ponto de forma segura
        def clean_float(val):
            try:
                if pd.isna(val) or val == '': return np.nan
                if isinstance(val, str):
                    s = val.replace(',', '.').strip()
                    return float(s) if s else np.nan
                return float(val)
            except:
                return np.nan

        df['xG_Casa'] = df['xG_Casa'].apply(clean_float)
        df['xG_Visitante'] = df['xG_Visitante'].apply(clean_float)
        
        # 4. Processar Placar (Separar Gols) - Mantendo NaNs para jogos futuros
        def split_placar(placar_str):
            try:
                if not isinstance(placar_str, str): return np.nan, np.nan
                # Verifica se contém o traço separador (comum ou especial)
                if not any(sep in placar_str for sep in ['-', '–']): return np.nan, np.nan
                
                p = placar_str.replace('–', '-').replace(' ', '')
                parts = p.split('-')
                if len(parts) == 2:
                    return int(parts[0]), int(parts[1])
                return np.nan, np.nan
            except:
                return np.nan, np.nan

        df[['Gols_Casa', 'Gols_Visitante']] = df['Placar'].apply(lambda x: pd.Series(split_placar(x)))
        
        # Ordenação por DATA (Regra de Ouro) e Rodada
        df.sort_values(by=['Data', 'Rodada'], ascending=[True, True], inplace=True)
        
        # Garantir Rodada como Inteiro
        df['Rodada'] = pd.to_numeric(df['Rodada'], errors='coerce')
        df.dropna(subset=['Rodada'], inplace=True)
        df['Rodada'] = df['Rodada'].astype(int)
        
        return df

    except Exception as e:
        return f"Erro ao processar arquivo: {str(e)}"

def get_confrontos_rodada(df, rodada_alvo):
    """
    Retorna lista de confrontos da rodada alvo.
    """
    rodada_df = df[df['Rodada'] == int(rodada_alvo)].copy()
    confrontos = []
    for _, row in rodada_df.iterrows():
        confrontos.append({
            'Mandante': row['Mandante'],
            'Visitante': row['Visitante'],
            'Data_Jogo': row['Data']
        })
    return confrontos

def calcular_metricas(df, time, data_limite, n_jogos, filtro_mando, is_mandante_na_analise):
    """
    Calcula as métricas para um time, baseando-se no histórico ANTERIOR à data_limite.
    
    Args:
        df: DataFrame completo
        time: Nome do time
        data_limite: Data do jogo atual (calcula apenas com jogos < data_limite)
        n_jogos: Quantidade de jogos para análise
        filtro_mando: 'TODOS' ou 'POR_MANDO'
        is_mandante_na_analise: Se o time é mandante no jogo que estamos analisando agora
    """
    
    # Conversão rigorosa para comparação segura (apenas DATA, sem hora)
    if isinstance(data_limite, pd.Timestamp):
        data_limite = data_limite.date()
    elif isinstance(data_limite, str):
        try:
            data_limite = pd.to_datetime(data_limite).date()
        except:
            pass # Mantém como está se falhar, mas deve falhar na comp
            
    # Garantir que a coluna Data seja datetime.date para comparação
    # (Isso é feito melhor vetorizado antes, mas aqui garantimos caso-a-caso)
    df_datas = df['Data'].dt.date
    
    # 1. Filtrar jogos DO TIME e ANTERIORES à data limite
    mask_time = (df['Mandante'] == time) | (df['Visitante'] == time)
    # A REGRA DE OURO: Apenas a CROLOLOGIA importa.
    # Se Data_Histórico < Data_Limite, o jogo entra.
    mask_data = df_datas < data_limite
    
    historico = df[mask_time & mask_data].copy()
    
    # Apenas jogos com PLACAR preenchido entram no cálculo das estatísticas
    historico.dropna(subset=['Gols_Casa', 'Gols_Visitante'], inplace=True)
    
    # Ordenar: Mais recente primeiro
    historico.sort_values(by='Data', ascending=False, inplace=True)
    
    # 2. Aplicar Filtro de Mando (Se necessário)
    if filtro_mando == 'POR_MANDO':
        if is_mandante_na_analise:
            # Se o time vai jogar em casa, olhamos histórico EM CASA
            historico = historico[historico['Mandante'] == time]
        else:
            # Se o time vai jogar fora, olhamos histórico FORA
            historico = historico[historico['Visitante'] == time]
            
    # 3. Pegar os últimos N jogos
    recorte = historico.head(n_jogos).copy()
    
    if len(recorte) == 0:
        return {
            'GP': 0.0, 'GS': 0.0, 'SG_Conq': 0.0, 'SG_Ced': 0.0, 
            'xG': 0.0, 'xGA': 0.0, 'Jogos': 0
        }, pd.DataFrame()

    # 4. Calcular Métricas
    stats = {'GP': 0, 'GS': 0, 'SG_Conq': 0, 'SG_Ced': 0, 'xG_soma': 0.0, 'xGA_soma': 0.0, 'Jogos': len(recorte)}
    
    for _, row in recorte.iterrows():
        # Definir papéis no histórico
        if row['Mandante'] == time:
            gols_pro = row['Gols_Casa']
            gols_sofridos = row['Gols_Visitante']
            xg_pro = row['xG_Casa']
            xg_contra = row['xG_Visitante']
        else:
            gols_pro = row['Gols_Visitante']
            gols_sofridos = row['Gols_Casa']
            xg_pro = row['xG_Visitante']
            xg_contra = row['xG_Casa']
            
        stats['GP'] += gols_pro
        stats['GS'] += gols_sofridos
        stats['xG_soma'] += xg_pro
        stats['xGA_soma'] += xg_contra
        
        # SG Conquistado: Não sofri gols (GS = 0)
        if gols_sofridos == 0:
            stats['SG_Conq'] += 1
            
        # SG Cedido: Não fiz gols (GP = 0) -> "Cedi" o clean sheet pro adversário
        if gols_pro == 0:
            stats['SG_Ced'] += 1

    # Normalizar médias
    qtd_jogos = len(recorte)
    stats['xG'] = stats['xG_soma'] / qtd_jogos if qtd_jogos > 0 else 0.0
    stats['xGA'] = stats['xGA_soma'] / qtd_jogos if qtd_jogos > 0 else 0.0
    
    return stats, recorte

# --- BLOCO DE LEITURA E VALIDAÇÃO ---
if __name__ == "__main__":
    df = load_and_clean_data(CSV_PATH)
    
    if isinstance(df, str):
        print(df) # Erro
    else:
        print("=== DADOS CARREGADOS (Últimos 5 registros ordenados por data) ===")
        print(df.head(5))
        
        # Teste Rápido: Rodada 2
        rodada_test = 2
        confrontos = get_confrontos_rodada(df, rodada_test)
        
        if len(confrontos) > 0:
            jogo_teste = confrontos[0]
            print(f"\n=== TESTE DE CÁLCULO ===")
            print(f"Jogo: {jogo_teste['Mandante']} x {jogo_teste['Visitante']} (Data: {jogo_teste['Data_Jogo']})")
            
            # Recorte Últimos 3 (Exemplo)
            stats_mand = calcular_metricas(df, jogo_teste['Mandante'], jogo_teste['Data_Jogo'], 3, 'POR_MANDO', True)
            stats_vis = calcular_metricas(df, jogo_teste['Visitante'], jogo_teste['Data_Jogo'], 3, 'POR_MANDO', False)
            
            print(f"\nStats {jogo_teste['Mandante']} (Casa):")
            print(stats_mand)
            
            print(f"\nStats {jogo_teste['Visitante']} (Fora):")
            print(stats_vis)
        else:
            print(f"Nenhum confronto encontrado para rodada {rodada_test}")
