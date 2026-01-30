import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.image as mpimg
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
import matplotlib.colors as mcolors
import pandas as pd
import os
import unicodedata

from pathlib import Path

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
# Usando Pathlib para garantir que os caminhos funcionem em Windows e Linux (Streamlit Cloud)
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
LOGOS_DIR = ASSETS_DIR / "logos"
TEAMS_DIR = ASSETS_DIR / "teams"

# --- CARREGAR FONTE ---
try:
    font_files = [f for f in os.listdir(FONTS_DIR) if f.lower().endswith(('.ttf', '.otf'))]
    if font_files:
        font_path = FONTS_DIR / font_files[0]
        prop = fm.FontProperties(fname=font_path)
    else:
        prop = fm.FontProperties(family='sans-serif', weight='bold')
except Exception:
    prop = fm.FontProperties(family='sans-serif', weight='normal') # Usando normal para evitar o "muito negrito"

# --- CONFIGURAÇÕES DE ESTILO ---
COLOR_BG = "#F5F5F5"
COLOR_HEADER_BG = "#1A4D2E"
COLOR_HEADER_TEXT = "#FFFFFF"
COLOR_TABLE_HEADER_BG = "#000000"
COLOR_TABLE_HEADER_TEXT = "#FFFFFF"
CMAP_RYG = mcolors.LinearSegmentedColormap.from_list("RYG", ["#ff6666", "#ffff99", "#66cc66"])

COLOR_RULES_MANDANTE = {
    'GP': True, 'SG ced': True, 'XG casa': True, 'XGA fora': True, 'SG conq': True, 'GS': True
}
COLOR_RULES_VISITANTE = {
    'GP': False, 'SG ced': True, 'XG fora': False, 'XGA casa': False, 'SG conq': True, 'GS': False
}

def get_conditional_color(value, column_values, higher_is_better=True):
    try:
        valid_values = [float(v) for v in column_values if pd.notna(v) and str(v).replace('.','',1).isdigit()]
        if not valid_values: return "#FFFFFF"
        val = float(value)
        min_v, max_v = min(valid_values), max(valid_values)
        if max_v == min_v: return "#FFFF99"
        norm = (val - min_v) / (max_v - min_v)
        if not higher_is_better: norm = 1 - norm
        return mcolors.rgb2hex(CMAP_RYG(norm))
    except (ValueError, TypeError):
        return "#FFFFFF"

def sanitize_name(name):
    """Remove acentos e espaços para compatibilidade com arquivos."""
    if not name: return ""
    import unicodedata
    n = unicodedata.normalize('NFKD', str(name)).encode('ASCII', 'ignore').decode('ASCII')
    return n.lower().replace(" ", "_").replace("-", "_")

def get_team_logo_path(team_name):
    """Busca o escudo do time de forma flexível."""
    if not team_name: return None
    
    # 1. Tentar Match Direto no Mapa (Suporta nomes truncados da planilha)
    MAPA_SIMPLIFICADO = {
        "atletico_m": "atletico_mg", "atletico": "atletico_mg", 
        "botafogo": "botafogo", "chapeco": "chapecoense",
        "bragant": "red_bull_bragantino", "red_bull": "red_bull_bragantino",
        "vasco": "vasco", "vitoria": "vitoria", "gremio": "gremio", "palmeiras": "palmeiras",
        "flamengo": "flamengo", "fluminense": "fluminense", "sao_paulo": "sao_paulo",
        "santos": "santos", "cruzeiro": "cruzeiro", "bahia": "bahia", "inter": "internacional",
        "corinth": "corinthians", "coritiba": "coritiba", "mirassol": "mirassol",
        "remo": "remo", "athletico": "athletico-pr"
    }
    
    sanitized = sanitize_name(team_name)
    
    # Verifica se algum termo do mapa está contido no nome do time
    for key, filename in MAPA_SIMPLIFICADO.items():
        if key in sanitized:
            path = TEAMS_DIR / f"{filename}.png"
            if path.exists(): return str(path)

    # 2. Tentativa por nome sanitizado direto
    path = TEAMS_DIR / f"{sanitized}.png"
    if path.exists(): return str(path)
    
    # Debug no console do Streamlit
    print(f"[LOG] Escudo não encontrado para: {team_name} (Sanitizado: {sanitized})")
    return None

def add_image(ax, path, x, y, zoom=0.1, zorder=10):
    if not path or not Path(path).exists(): 
        print(f"[LOG] Falha ao carregar imagem no path: {path}")
        return
    try:
        img = mpimg.imread(path)
        ab = AnnotationBbox(OffsetImage(img, zoom=zoom), (x, y), frameon=False, xycoords='axes fraction', zorder=zorder)
        ax.add_artist(ab)
    except Exception as e:
        print(f"[LOG] Erro ao abrir imagem {path}: {e}")

def generate_infographic(df_mandante, df_visitante, rodada_num, n_jogos, tipo_filtro):
    m_col = 'XG casa' if 'XG casa' in df_mandante.columns else 'xG casa'
    v_col = 'XGA casa' if 'XGA casa' in df_visitante.columns else 'xGA casa'
    
    df_mandante = df_mandante.sort_values(m_col, ascending=False).reset_index(drop=True)
    df_visitante = df_visitante.sort_values(v_col, ascending=True).reset_index(drop=True)
    
    # Aumentei a altura para 20 e DPI para 400 para nitidez máxima
    fig, ax = plt.subplots(figsize=(12, 19))
    bg_path = os.path.join(LOGOS_DIR, "background.png")
    if os.path.exists(bg_path):
        ax.imshow(mpimg.imread(bg_path), extent=[0, 1, 0, 1], aspect='auto', zorder=-1)
    else:
        fig.patch.set_facecolor(COLOR_BG)
    ax.set_axis_off()

    # Fundo (Background)
    bg_path = LOGOS_DIR / "background.png"
    if bg_path.exists():
        try:
            ax.imshow(mpimg.imread(str(bg_path)), extent=[0, 1, 0, 1], aspect='auto', zorder=-1)
        except Exception as e:
            print(f"[LOG] Erro ao carregar fundo: {e}")
            fig.patch.set_facecolor(COLOR_BG)
    else:
        print(f"[LOG] Fundo não encontrado em: {bg_path}")
        fig.patch.set_facecolor(COLOR_BG)

    header_y = 0.94
    ax.add_patch(plt.Rectangle((0.2, header_y - 0.02), 0.6, 0.04, color=COLOR_HEADER_BG, transform=ax.transAxes))
    ax.text(0.5, header_y, f"ANÁLISE XG E XGA – RODADA {rodada_num}", ha="center", va="center", color="white", fontproperties=prop, fontsize=24, transform=ax.transAxes)

    # Logos do Cabeçalho - Ajustados para nomes sanitizados
    logo_tcc_path = str(LOGOS_DIR / "logo_tcc.png")
    add_image(ax, logo_tcc_path, 0.1, header_y, zoom=0.07, zorder=15)
    add_image(ax, logo_tcc_path, 0.9, header_y, zoom=0.07, zorder=15)

    def draw_table(df, start_y, is_mandante):
        cols = ["TIME", "GP", "SG ced", "XG", "XGA", "SG conq", "GS", "ADV"]
        if is_mandante:
            cols[0], cols[3], cols[4], cols[7] = "CASA", "XG casa", "XGA fora", "FORA"
            inner_cols = ["MANDANTE", "GP", "SG ced", m_col, 'xGA fora' if 'xGA fora' in df.columns else 'XGA fora', "SG conq", "GS", "VISITANTE"]
            df_v = df[inner_cols].copy()
        else:
            cols[0], cols[3], cols[4], cols[7] = "FORA", "XG fora", "XGA casa", "CASA"
            inner_cols = ["VISITANTE", "GP", "SG ced", 'xG fora' if 'xG fora' in df.columns else 'XG fora', v_col, "SG conq", "GS", "MANDANTE"]
            df_v = df[inner_cols].copy()

        # Spacing e proporções
        row_h, col_w, x_s = 0.033, [0.1, 0.08, 0.08, 0.12, 0.12, 0.12, 0.08, 0.1], 0.09
        curr_y = start_y - 0.03
        
        # Legenda Centralizada Dinâmica em Única Linha
        filtro_desc = "por mando" if tipo_filtro == 'POR_MANDO' else "gerais"
        legenda_txt = f"{n_jogos} rodadas {filtro_desc}  |  GP - gols pró  |  sg cedido  |  sg conquistado  |  gols sofridos"
        # Tabela Mandante (GP... GS) | Tabela Visitantes (GP... GS)
        # Removido a palavra "últimos" conforme pedido
        
        ax.text(0.5, curr_y + row_h + 0.008, legenda_txt, ha="center", va="bottom", color="#444444", fontproperties=prop, fontsize=10, transform=ax.transAxes)

        # Header com bordas mais grossas
        curr_x = x_s
        for i, col in enumerate(cols):
            ax.add_patch(plt.Rectangle((curr_x, curr_y), col_w[i], row_h, color=COLOR_TABLE_HEADER_BG, ec="white", lw=2.5, transform=ax.transAxes, zorder=3))
            ax.text(curr_x + col_w[i]/2, curr_y + row_h/2, col, ha="center", va="center", color="white", fontproperties=prop, fontsize=14, weight=500, transform=ax.transAxes, zorder=4)
            curr_x += col_w[i]

        column_data = {i: df_v.iloc[:, i].tolist() for i in range(1, 7)}
        rules = COLOR_RULES_MANDANTE if is_mandante else COLOR_RULES_VISITANTE

        for _, row in df_v.iterrows():
            curr_y -= row_h
            curr_x = x_s
            items = list(row.values)
            for i, val in enumerate(items):
                bg = "#FFFFFF"
                if 1 <= i <= 6:
                    bg = get_conditional_color(val, column_data[i], rules.get(cols[i], True))
                
                ax.add_patch(plt.Rectangle((curr_x, curr_y), col_w[i], row_h, color=bg, ec="black", lw=0.5, transform=ax.transAxes))
                
                if i == 0 or i == 7:
                    logo = get_team_logo_path(val)
                    if logo:
                        # Ajuste fino de zoom: Global 0.035, com exceção para times com logos "altos"
                        team_zoom = 0.032 if val in ["São Paulo", "Fluminense"] else 0.035
                        add_image(ax, logo, curr_x + col_w[i]/2, curr_y + row_h/2, zoom=team_zoom, zorder=3)
                    else:
                        ax.text(curr_x + col_w[i]/2, curr_y + row_h/2, str(val)[:10], ha="center", va="center", fontproperties=prop, fontsize=12, transform=ax.transAxes)
                else:
                    # Formatação final:
                    # GP (1) e GS (6) -> Números INTEIROS (sem vírgula/ponto)
                    # xG (3) e xGA (4) -> 2 casas decimais
                    if isinstance(val, (float, int)):
                        if i in [1, 6]:
                            txt = str(int(val))
                        elif i in [3, 4]:
                            txt = f"{val:.2f}"
                        else:
                            txt = str(val)
                    else:
                        txt = str(val)
                    ax.text(curr_x + col_w[i]/2, curr_y + row_h/2, txt, ha="center", va="center", fontproperties=prop, fontsize=14, weight=500, transform=ax.transAxes)
                curr_x += col_w[i]
        return curr_y

    # Layout Vertical Ajustado (Subi tudo para dar espaço na base)
    y_pos = draw_table(df_mandante, 0.88, True) 
    draw_table(df_visitante, y_pos - 0.06, False) 

    # Rodapé
    footer_h = 0.035
    ax.add_patch(plt.Rectangle((0, 0), 1, footer_h, color=COLOR_HEADER_BG, transform=ax.transAxes, zorder=20))
    ax.text(0.5, footer_h/2, "MATERIAL EXCLUSIVO DO TCC", ha="center", va="center", color="white", fontproperties=prop, fontsize=14, transform=ax.transAxes, zorder=21)
    
    logo_tcc_branca = str(LOGOS_DIR / "logo_tcc_branco.png")
    add_image(ax, logo_tcc_branca, 0.1, footer_h/2, zoom=0.045, zorder=25)
    add_image(ax, logo_tcc_branca, 0.9, footer_h/2, zoom=0.045, zorder=25)
    
    out = str(BASE_DIR / f"Analise_R{rodada_num}.png")
    plt.savefig(out, dpi=400, bbox_inches='tight') # DPI aumentado para 400
    plt.close()
    return out
