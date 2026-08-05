"""
graphic_renderer.py — geração dos infográficos em PNG.
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.image as mpimg
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from matplotlib.patches import FancyBboxPatch, Ellipse
import matplotlib.colors as mcolors
import pandas as pd
import os
import unicodedata
from pathlib import Path
from PIL import Image, ImageFilter
import numpy as np
import streamlit as st
import gc

# ---------------------------------------------------------------------------
# CAMINHOS E CONSTANTES
# ---------------------------------------------------------------------------
BASE_DIR   = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"

COLOR_BG               = "#F5F5F5"
COLOR_HEADER_BG        = "#1A4D2E"
COLOR_HEADER_TEXT      = "#FFFFFF"
COLOR_TABLE_HEADER_BG  = "#000000"
COLOR_TABLE_HEADER_TXT = "#FFFFFF"

CMAP_RYG = mcolors.LinearSegmentedColormap.from_list(
    "RYG", ["#ff6666", "#ffff99", "#66cc66"]
)

# Regras de cor por bloco (True = mais alto → mais verde)
#
# GC (grandes chances) foi adicionada em 2026-08-05, ao lado de CHUT.AG por
# ser a mesma família — perigo criado/cedido — mas filtrada por qualidade de
# chance em vez de volume bruto de chute. Layout de 14 colunas (7 por bloco).
#
# B1 — Análise Ofensiva do MANDANTE (cols 1-6)
COLOR_RULES_B1 = {
    1: False,  # SG ced       — mais = pior  (não marcou)
    2: True,   # CHUT.AG conq — mais = melhor (atacou mais)
    3: True,   # GC conq      — mais = melhor (criou mais chances claras)
    4: True,   # CONV conq    — mais = melhor (eficiente)
    5: True,   # GP           — mais = melhor
    6: True,   # XG           — mais = melhor
}
# B2 — Análise Defensiva do VISITANTE (cols 7-12) — lógica INVERTIDA
# "Verde para o que é bom para o MANDANTE nessa perspectiva"
COLOR_RULES_B2 = {
    7:  True,  # XGA fora    — visitante cedeu mais → mais verde para mandante
    8:  True,  # GS          — visitante sofreu mais → mais verde para mandante
    9:  True,  # CONV ced    — adversário do visitante foi mais eficiente → verde
    10: True,  # GC ced      — visitante cedeu mais chances claras → verde p/ mandante
    11: True,  # CHUT.AG ced — visitante sofreu mais chutes → verde para mandante
    12: False, # SG conq     — visitante teve mais clean sheets → pior para mandante
}
# B3 — Análise Ofensiva do VISITANTE (cols 1-6) — lógica INVERTIDA
COLOR_RULES_B3 = {
    1: True,   # SG ced       — visitante não marcou mais → verde para mandante
    2: False,  # CHUT.AG conq — visitante chutou mais → pior para mandante
    3: False,  # GC conq      — visitante criou mais chances claras → pior p/ mandante
    4: False,  # CONV conq    — visitante mais eficiente → pior para mandante
    5: False,  # GP           — visitante marcou mais → pior para mandante
    6: False,  # XG fora      — visitante gerou mais perigo → pior para mandante
}
# B4 — Análise Defensiva do MANDANTE (cols 7-12)
COLOR_RULES_B4 = {
    7:  False, # XGA          — mais = pior (sofreu mais perigo)
    8:  False, # GS           — mais = pior
    9:  False, # CONV ced     — mais = pior (adversário eficiente)
    10: False, # GC ced       — mais = pior (cedeu mais chances claras)
    11: False, # CHUT.AG ced  — mais = pior (sofreu mais chutes)
    12: True,  # SG conq      — mais = melhor (clean sheets)
}

# ---------------------------------------------------------------------------
# FONTE
# ---------------------------------------------------------------------------
font_path = ASSETS_DIR / "fonts" / "Decalotype-Bold.otf"
try:
    if font_path.exists():
        fm.fontManager.addfont(str(font_path))
        prop = fm.FontProperties(fname=str(font_path))
    else:
        prop = fm.FontProperties(family='sans-serif', weight='bold')
except Exception:
    prop = fm.FontProperties(family='sans-serif', weight='bold')

prop_small = fm.FontProperties(fname=str(font_path) if font_path.exists() else None,
                                family='sans-serif', weight='bold', size=9)

# ---------------------------------------------------------------------------
# HELPERS DE IMAGEM
# ---------------------------------------------------------------------------

def get_image_from_disk(key: str):
    SPECIAL_MAP = {
        "logo_background":      ASSETS_DIR / "logos" / "background.png",
        "logo_logo_tcc":        ASSETS_DIR / "logos" / "logo_tcc.png",
        "logo_logo_tcc_branco": ASSETS_DIR / "logos" / "logo_tcc_branco.png",
    }
    path = None
    if key in SPECIAL_MAP:
        path = SPECIAL_MAP[key]
    elif key.startswith("team_"):
        path = ASSETS_DIR / "teams" / (key.replace("team_", "") + ".png")
    else:
        path = ASSETS_DIR / "teams" / f"{key}.png"
    try:
        return Image.open(path) if (path and path.exists()) else None
    except Exception:
        return None


def sanitize_name(name: str) -> str:
    if not name:
        return ""
    n = unicodedata.normalize('NFKD', str(name)).encode('ASCII', 'ignore').decode('ASCII')
    return n.lower().replace(" ", "_").replace("-", "_").strip("_")


def get_team_logo_path(team_name: str):
    if not team_name:
        return None
    # Ordem importa: mais específico primeiro
    MAPA = {
        "atletico_pr":       "athletico_pr",
        "athletico":         "athletico_pr",
        "atletico_m":        "atletico_mg",
        "atletico":          "atletico_mg",
        "botafogo":          "botafogo",
        "chapeco":           "chapecoense",
        "bragant":           "red_bull_bragantino",
        "red_bull":          "red_bull_bragantino",
        "vasco":             "vasco",
        "vitoria":           "vitoria",
        "gremio":            "gremio",
        "palmeiras":         "palmeiras",
        "flamengo":          "flamengo",
        "fluminense":        "fluminense",
        "sao_paulo":         "sao_paulo",
        "santos":            "santos",
        "cruzeiro":          "cruzeiro",
        "bahia":             "bahia",
        "inter":             "internacional",
        "corinth":           "corinthians",
        "coritiba":          "coritiba",
        "mirassol":          "mirassol",
        "remo":              "remo",
    }
    s = sanitize_name(team_name)
    for key, filename in MAPA.items():
        if key in s:
            path = ASSETS_DIR / "teams" / f"{filename}.png"
            if path.exists():
                return f"team_{filename}"
    return None


@st.cache_resource(show_spinner=False)
def _process_image_with_shadow(image_key: str, zoom_factor: float):
    img = get_image_from_disk(image_key)
    if img is None:
        return None
    try:
        original_w, original_h = img.size   # referência: mantém o tamanho de exibição
        # Trabalha com uma cópia reduzida para economizar memória.
        # Os escudos aparecem pequenos na arte, então 256px basta e evita
        # que ~140 logos em alta resolução estourem a RAM do Streamlit Cloud.
        WORK_MAX = 256
        if max(img.size) > WORK_MAX:
            img = img.convert("RGBA")
            img.thumbnail((WORK_MAX, WORK_MAX), Image.LANCZOS)
        work_w, work_h = img.size
        padding = int(max(work_w, work_h) * 0.2)
        new_size = (work_w + 2*padding, work_h + 2*padding)

        img_padded = Image.new("RGBA", new_size, (0, 0, 0, 0))
        img_padded.paste(img, (padding, padding), img)

        alpha = img_padded.getchannel('A')
        shadow_layer = Image.new("RGBA", new_size, (0, 0, 0, 0))
        black_mask   = Image.new("L", new_size, 100)
        shadow_layer.putalpha(
            Image.composite(black_mask, Image.new("L", new_size, 0), alpha)
        )
        shadow_blurred = shadow_layer.filter(ImageFilter.GaussianBlur(radius=5))

        final_img = Image.new("RGBA", new_size, (0, 0, 0, 0))
        final_img.paste(shadow_blurred, (5, 5), shadow_blurred)
        final_img.paste(img_padded, (0, 0), img_padded)

        scale  = original_w / new_size[0]
        zoom_f = zoom_factor * scale * 1.5
        return np.array(final_img), zoom_f
    except Exception:
        return None


def add_image(ax, key_or_img, x: float, y: float, zoom: float = 0.1, zorder: int = 10):
    if isinstance(key_or_img, str):
        result = _process_image_with_shadow(key_or_img, zoom)
        if result is None:
            return
        img, zoom = result
    else:
        img = key_or_img
    if img is None:
        return
    try:
        ab = AnnotationBbox(
            OffsetImage(img, zoom=zoom, resample=True),
            (x, y), frameon=False, xycoords='axes fraction', zorder=zorder
        )
        ax.add_artist(ab)
    except Exception:
        pass


def get_conditional_color(value, column_values, higher_is_better: bool = True) -> str:
    try:
        valid = []
        for v in column_values:
            try:
                valid.append(float(v))
            except (TypeError, ValueError):
                pass
        if not valid:
            return "#FFFFFF"
        val = float(value)
        lo, hi = min(valid), max(valid)
        if hi == lo:
            return "#FFFF99"
        norm = (val - lo) / (hi - lo)
        if not higher_is_better:
            norm = 1.0 - norm
        return mcolors.rgb2hex(CMAP_RYG(norm))
    except (TypeError, ValueError):
        return "#FFFFFF"


def _fmt(val, col_idx: int) -> str:
    """Formata um valor numérico conforme o tipo da coluna."""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return str(val)
    if col_idx in (1, 5, 8, 12):     # SG_ced, GP, GS, SG_conq → inteiro
        return str(int(round(v)))
    if col_idx in (2, 3, 10, 11):    # CHUT.AG, GC → 1 decimal
        return f"{v:.1f}"
    if col_idx in (4, 9):            # CONV % → percentual
        return f"{v:.0f}%"
    if col_idx in (6, 7):            # XG, XGA → 2 decimais
        return f"{v:.2f}"
    return str(val)


# ---------------------------------------------------------------------------
# INFOGRÁFICO PRINCIPAL — 4 BLOCOS
# ---------------------------------------------------------------------------

def generate_infographic(
    df_b1: pd.DataFrame,
    df_b2: pd.DataFrame,
    df_b3: pd.DataFrame,
    df_b4: pd.DataFrame,
    rodada_num: int,
    n_jogos: int,
    tipo_filtro: str,
) -> str:
    """
    Gera o PNG principal com os 4 blocos de análise.
    Retorna o caminho do arquivo salvo.
    """
    FIG_W, FIG_H = 16, 22
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    # Fundo
    bg = get_image_from_disk("logo_background")
    if bg:
        ax.imshow(bg, extent=[0, 1, 0, 1], aspect='auto', zorder=0)
    else:
        fig.patch.set_facecolor(COLOR_BG)

    # ── CABEÇALHO ──────────────────────────────────────────────────────────
    hdr_y, hdr_h = 0.968, 0.034          # barra do título mais grossa
    ax.add_patch(plt.Rectangle(
        (0.13, hdr_y - hdr_h/2), 0.74, hdr_h,
        color=COLOR_HEADER_BG, transform=ax.transAxes, zorder=5
    ))
    ax.text(0.5, hdr_y, "ANÁLISE DEFENSIVA E OFENSIVA",
            ha="center", va="center", color="white",
            fontproperties=prop, fontsize=24, transform=ax.transAxes, zorder=6)
    add_image(ax, "logo_logo_tcc", 0.07, hdr_y, zoom=0.065, zorder=8)
    add_image(ax, "logo_logo_tcc", 0.93, hdr_y, zoom=0.065, zorder=8)

    # ── SUBTÍTULO ──────────────────────────────────────────────────────────
    filtro_desc = "POR MANDO" if tipo_filtro == "POR_MANDO" else "TODOS OS JOGOS"
    ax.text(0.5, 0.938,
            f"ÚLTIMOS {n_jogos} JOGOS \"{filtro_desc}\"  |  RODADA {rodada_num}",
            ha="center", va="center", color="#222222",
            fontproperties=prop, fontsize=14, transform=ax.transAxes, zorder=6)

    # ── LEGENDA ────────────────────────────────────────────────────────────
    legenda = (
        "GP = Gols Pró  ·  GS = Gols Sofridos  ·  SG ced = Jogos sem marcar  ·  "
        "SG conq = Clean Sheets  ·  CHUT.AG = Média de chutes no alvo  ·  "
        "GRANDES CHANCES = Finalizações de qualidade clara  ·  "
        "CONVERSÃO = Eficiência (Gols ÷ Chutes no alvo × 100)"
    )
    ax.text(0.5, 0.924, legenda,
            ha="center", va="center", color="#555555",
            fontproperties=prop, fontsize=9, transform=ax.transAxes, zorder=6)

    # ── LAYOUT DE COLUNAS ──────────────────────────────────────────────────
    # 14 colunas: [logo_esq, SG_ced, CHUT_conq, GC_conq, CONV_conq, GP, XG,
    #              XGA, GS, CONV_ced, GC_ced, CHUT_ced, SG_conq, logo_dir]
    # GC (grandes chances) entra ao lado de CHUT.AG — mesma família de perigo
    # criado/cedido, mas filtrada por qualidade em vez de volume bruto. Fica
    # em coluna "medium" (não "narrow") porque o cabeçalho é escrito por
    # extenso ("GRANDES CHANCES"), mais longo que os das colunas vizinhas.
    X0 = 0.020
    # Proporções: logo=1.2, narrow=0.78, medium=1.0
    #   2×logo + 4×narrow + 8×medium  →  total 0.960
    _u = 0.960 / (2*1.2 + 4*0.78 + 8*1.0)
    COL_W = [
        1.2*_u,  0.78*_u, 1.0*_u, 1.0*_u, 1.0*_u, 0.78*_u, 1.0*_u,
        1.0*_u,  0.78*_u, 1.0*_u, 1.0*_u, 1.0*_u, 0.78*_u, 1.2*_u,
    ]
    COL_X = [X0]
    for w in COL_W[:-1]:
        COL_X.append(COL_X[-1] + w)

    B1_W = sum(COL_W[:7])
    B2_W = sum(COL_W[7:])
    B1_CX = X0 + B1_W / 2
    B2_CX = X0 + B1_W + B2_W / 2

    ROW_H      = 0.035    # altura das linhas de dados — distribuição equilibrada
    HDR_ROW_H  = 0.030    # cabeçalho compacto, proporcional à fonte
    PILL_H     = 0.020    # pílula de título compacta
    PILL_PAD   = 0.020    # margem horizontal dentro do bloco
    PILL_GAP   = 0.007    # respiro entre a pílula e o cabeçalho da tabela

    # ── FUNÇÃO INTERNA: desenha um par de blocos ───────────────────────────
    def draw_pair(df_left, df_right, y_top,
                  title_left, title_right,
                  headers_left, headers_right,
                  left_logo_col, right_logo_col,
                  color_rules_left, color_rules_right):
        """
        Desenha um par de blocos (esq + dir) a partir de y_top.
        Retorna y_bottom (posição após a última linha de dados).
        """
        n_rows = len(df_left)

        # — Pílulas de título — (retângulo simples, sem padding extra do FancyBbox)
        pill_y = y_top - PILL_H / 2
        for cx, title, bw in [(B1_CX, title_left, B1_W), (B2_CX, title_right, B2_W)]:
            pw = bw - 2 * PILL_PAD
            p = FancyBboxPatch(
                (cx - pw/2, pill_y - PILL_H/2), pw, PILL_H,
                boxstyle="round,pad=0.0,rounding_size=0.006",
                linewidth=0, facecolor=COLOR_HEADER_BG,
                transform=ax.transAxes, zorder=5
            )
            ax.add_patch(p)
            ax.text(cx, pill_y, title,
                    ha="center", va="center", color="white",
                    fontproperties=prop, fontsize=11,
                    transform=ax.transAxes, zorder=6)

        # — Cabeçalhos das colunas — (com gap após a pílula para não encostar)
        # Cada cabeçalho é um texto simples (fonte padrão) ou uma tupla
        # (texto, fonte) quando precisa de tamanho reduzido — caso do
        # "GRANDES CHANCES", escrito por extenso e mais longo que os vizinhos.
        hdr_y_bot = y_top - PILL_H - PILL_GAP - HDR_ROW_H
        for i, (hdr, cw, cx) in enumerate(zip(headers_left + headers_right, COL_W, COL_X)):
            hdr_txt, hdr_fs = hdr if isinstance(hdr, tuple) else (hdr, 10.5)
            ax.add_patch(plt.Rectangle(
                (cx, hdr_y_bot), cw, HDR_ROW_H,
                color=COLOR_TABLE_HEADER_BG, ec="white", lw=1.2,
                transform=ax.transAxes, zorder=3
            ))
            ax.text(cx + cw/2, hdr_y_bot + HDR_ROW_H/2, hdr_txt,
                    ha="center", va="center", color="white",
                    fontproperties=prop, fontsize=hdr_fs,
                    linespacing=1.1, multialignment='center',
                    transform=ax.transAxes, zorder=4)

        # Regras combinadas do par
        combined_rules = {**color_rules_left, **color_rules_right}

        # Pré-calcular dados de cada coluna para normalização de cores
        col_data = {}
        for j in range(1, 7):
            col_data[j]   = df_left.iloc[:, j].tolist()
        for j in range(6):
            col_data[j+7] = df_right.iloc[:, j].tolist()

        # — Linhas de dados —
        data_top = hdr_y_bot

        for r in range(n_rows):
            left_row  = df_left.iloc[r]
            right_row = df_right.iloc[r]
            ry = data_top - (r + 1) * ROW_H

            # Montar valores na ordem das 14 colunas
            vals = [
                left_row[left_logo_col],          # 0  logo esq
                left_row["SG_CED"],               # 1
                left_row["CHUT_AG_CONQ"],         # 2
                left_row["GC_CONQ"],              # 3
                left_row["CONV_CONQ"],            # 4
                left_row["GP"],                   # 5
                left_row["XG"],                   # 6
                right_row["XGA"],                 # 7
                right_row["GS"],                  # 8
                right_row["CONV_CED"],            # 9
                right_row["GC_CED"],              # 10
                right_row["CHUT_AG_CED"],         # 11
                right_row["SG_CONQ"],             # 12
                right_row[right_logo_col],        # 13 logo dir
            ]

            for i, (val, cw, cx) in enumerate(zip(vals, COL_W, COL_X)):
                if i in (0, 13):
                    bg = "#FFFFFF"
                else:
                    bg = get_conditional_color(
                        val, col_data.get(i, []),
                        combined_rules.get(i, True)
                    )

                ax.add_patch(plt.Rectangle(
                    (cx, ry), cw, ROW_H,
                    color=bg, ec="black", lw=0.35,
                    transform=ax.transAxes, zorder=2
                ))

                if i in (0, 13):
                    logo_key = get_team_logo_path(str(val))
                    if logo_key:
                        add_image(ax, logo_key, cx + cw/2, ry + ROW_H/2,
                                  zoom=0.035, zorder=4)   # escudos maiores
                    else:
                        ax.text(cx + cw/2, ry + ROW_H/2, str(val)[:9],
                                ha="center", va="center",
                                fontproperties=prop, fontsize=9,
                                transform=ax.transAxes, zorder=4)
                else:
                    txt = _fmt(val, i)
                    fs  = 15 if i in (5, 6, 7, 8) else 14  # números maiores
                    ax.text(cx + cw/2, ry + ROW_H/2, txt,
                            ha="center", va="center",
                            fontproperties=prop, fontsize=fs,
                            transform=ax.transAxes, zorder=4)

        y_bottom = data_top - n_rows * ROW_H

        # — Divisor central (separa mandante × visitante)
        # Vai de y_bottom até a base do cabeçalho (não entra na pílula)
        center_x = COL_X[7]
        ax.plot([center_x, center_x],
                [y_bottom, hdr_y_bot],
                color='#000000', lw=2.8, solid_capstyle='butt',
                transform=ax.transAxes, zorder=20)
        # Retraçar borda branca entre XG casa e XGA fora no cabeçalho
        # (o divisor preto dos dados pode cobrir; garantimos a linha branca)
        ax.plot([center_x, center_x],
                [hdr_y_bot, hdr_y_bot + HDR_ROW_H],
                color='white', lw=1.4, solid_capstyle='butt',
                transform=ax.transAxes, zorder=21)

        return y_bottom

    # ── PAR SUPERIOR: B1 + B2 ─────────────────────────────────────────────
    y_top1  = 0.910
    y_bot1  = draw_pair(
        df_b1, df_b2, y_top1,
        "ANÁLISE OFENSIVA DO MANDANTE",
        "ANÁLISE DEFENSIVA DO VISITANTE",
        ["CASA",  "SG\nced", "CHUT.AG\nCONQ.", ("GRANDES CHANCES\nconq.", 7.5),
         "CONVERSÃO\nconq.", "GP", "XG\ncasa"],
        ["XGA\nfora", "GS",  "CONVERSÃO\nced.", ("GRANDES CHANCES\ncedidas", 7.5),
         "CHUT.AG\nCED.", "SG\nconq", "FORA"],
        "MANDANTE", "VISITANTE",
        color_rules_left=COLOR_RULES_B1,
        color_rules_right=COLOR_RULES_B2,
    )

    # ── PAR INFERIOR: B3 + B4 ─────────────────────────────────────────────
    y_top2  = y_bot1 - 0.018   # gap entre os pares (respiro equilibrado)
    draw_pair(
        df_b3, df_b4, y_top2,
        "ANÁLISE OFENSIVA DO VISITANTE",
        "ANÁLISE DEFENSIVA DO MANDANTE",
        ["FORA",  "SG\nced", "CHUT.AG\nCONQ.", ("GRANDES CHANCES\nconq.", 7.5),
         "CONVERSÃO\nconq.", "GP", "XG\nfora"],
        ["XGA\ncasa", "GS",  "CONVERSÃO\nced.", ("GRANDES CHANCES\ncedidas", 7.5),
         "CHUT.AG\nCED.", "SG\nconq", "CASA"],
        "VISITANTE", "MANDANTE",
        color_rules_left=COLOR_RULES_B3,
        color_rules_right=COLOR_RULES_B4,
    )

    # ── RODAPÉ ────────────────────────────────────────────────────────────
    footer_h = 0.038
    ax.add_patch(plt.Rectangle(
        (0, 0), 1, footer_h,
        color=COLOR_HEADER_BG, transform=ax.transAxes, zorder=10
    ))
    ax.text(0.5, footer_h/2, "MATERIAL EXCLUSIVO DO TCC",
            ha="center", va="center", color="white",
            fontproperties=prop, fontsize=13,
            transform=ax.transAxes, zorder=11)
    add_image(ax, "logo_logo_tcc_branco", 0.1, footer_h/2, zoom=0.044, zorder=12)
    add_image(ax, "logo_logo_tcc_branco", 0.9, footer_h/2, zoom=0.044, zorder=12)

    out = str(BASE_DIR / f"Analise_R{rodada_num}.png")
    plt.savefig(out, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    gc.collect()
    return out


# ---------------------------------------------------------------------------
# GRADE DE EVIDÊNCIAS
# ---------------------------------------------------------------------------

def generate_evidence_grid(
    evidence_list: list[dict],
    rodada_num: int,
    n_jogos: int,
    tipo_filtro: str,
) -> str:
    """
    Gera o painel de evidências (últimos N jogos de cada time pelo mando correto).
    Cada célula mostra: xG_home | placar | xG_away  com logos dos times.

    Recebe evidence_list com dicts:
        { mandante_nome, visitante_nome,
          jogos_mandante: [lista de dicts de jogo],
          jogos_visitante: [lista de dicts de jogo] }
    """
    FIG_W, FIG_H = 14, 23
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')
    aspect = FIG_H / FIG_W

    bg = get_image_from_disk("logo_background")
    if bg:
        ax.imshow(bg, extent=[0, 1, 0, 1], aspect='auto', zorder=0)
    else:
        ax.add_patch(plt.Rectangle((0,0), 1, 1, color=COLOR_BG,
                                   transform=ax.transAxes, zorder=0))

    # — Cabeçalho —
    hdr_h = 0.038
    ax.add_patch(plt.Rectangle(
        (0.14, 0.947), 0.72, hdr_h,
        color=COLOR_HEADER_BG, transform=ax.transAxes, zorder=2
    ))
    ax.text(0.5, 0.947 + hdr_h/2,
            f"EVIDÊNCIAS TABELA XG E XGA – RODADA {rodada_num}",
            ha="center", va="center", color=COLOR_HEADER_TEXT,
            fontproperties=prop, fontsize=17, transform=ax.transAxes, zorder=3)
    add_image(ax, "logo_logo_tcc", 0.08, 0.966, zoom=0.068, zorder=4)
    add_image(ax, "logo_logo_tcc", 0.92, 0.966, zoom=0.068, zorder=4)

    filtro_txt = "POR MANDO" if tipo_filtro == "POR_MANDO" else "TODOS OS JOGOS"
    ax.text(0.5, 0.930,
            f"ÚLTIMOS {n_jogos} JOGOS  |  {filtro_txt}",
            ha="center", va="center", color="#333333",
            fontproperties=prop, fontsize=13, transform=ax.transAxes, zorder=3)

    # — Grade 2×5 —
    START_X = 0.04
    START_Y = 0.908
    BLK_W   = 0.455
    BLK_H   = 0.163
    GAP_X   = 0.02
    GAP_Y   = 0.010

    prop_bold = fm.FontProperties(
        fname=str(font_path) if font_path.exists() else None,
        family='sans-serif', weight='bold', size=10
    )

    for i, evid in enumerate(evidence_list[:10]):
        row = i // 2
        col = i % 2
        bx  = START_X + col * (BLK_W + GAP_X)
        by  = START_Y - (row + 1) * BLK_H - row * GAP_Y

        mand_nome = evid["mandante_nome"]
        vis_nome  = evid["visitante_nome"]

        # Borda do bloco
        ax.add_patch(plt.Rectangle(
            (bx, by), BLK_W, BLK_H,
            fill=False, ec="black", lw=1.4,
            transform=ax.transAxes, zorder=1
        ))

        # — Título do bloco —
        title_h = 0.030
        ax.add_patch(plt.Rectangle(
            (bx, by + BLK_H - title_h), BLK_W, title_h,
            color=COLOR_HEADER_BG, transform=ax.transAxes, zorder=5
        ))
        cx_blk = bx + BLK_W / 2
        title_y = by + BLK_H - title_h/2

        logo_mand = get_team_logo_path(mand_nome)
        logo_vis  = get_team_logo_path(vis_nome)

        ell_d_x = 0.046
        ell_d_y = ell_d_x / aspect
        shd_ox  = 0.0018
        shd_oy  = shd_ox / aspect

        for side_x, lkey in [(cx_blk - 0.043, logo_mand), (cx_blk + 0.043, logo_vis)]:
            ax.add_patch(Ellipse((side_x + shd_ox, title_y - shd_oy),
                                 ell_d_x, ell_d_y,
                                 color='#888', alpha=0.5,
                                 transform=ax.transAxes, zorder=6))
            ax.add_patch(Ellipse((side_x, title_y), ell_d_x, ell_d_y,
                                 color='white',
                                 transform=ax.transAxes, zorder=7))
            if lkey:
                add_image(ax, lkey, side_x, title_y, zoom=0.025, zorder=8)

        ax.text(cx_blk, title_y, "X",
                ha="center", va="center", color="white",
                fontproperties=prop, fontsize=14,
                transform=ax.transAxes, zorder=8)

        # — Dois painéis internos (mandante | visitante) —
        inner_h = BLK_H - title_h
        div_x   = bx + BLK_W / 2
        ax.plot([div_x, div_x], [by, by + inner_h],
                color='black', lw=1.0, alpha=0.7,
                transform=ax.transAxes, zorder=3)

        for panel_idx, (jogos, team_nome, px, is_home_panel) in enumerate([
            (evid["jogos_mandante"], mand_nome, bx,               True),
            (evid["jogos_visitante"], vis_nome, bx + BLK_W/2,     False),
        ]):
            sec_w  = BLK_W / 2
            margin = 0.024

            xg_left_x  = px + margin
            xg_right_x = px + sec_w - margin
            placar_x   = px + sec_w / 2
            logo_L_x   = placar_x - 0.040
            logo_R_x   = placar_x + 0.040

            # Sub-cabeçalho: xG | PLACAR | xG
            sub_hdr_y  = by + inner_h - 0.012
            sub_hdr_h  = 0.016
            ax.add_patch(plt.Rectangle(
                (px + 0.004, sub_hdr_y - sub_hdr_h/2), sec_w - 0.008, sub_hdr_h,
                color='black', transform=ax.transAxes, zorder=5
            ))
            ax.text(xg_left_x,  sub_hdr_y, "xG",     ha="center", va="center",
                    fontproperties=prop_bold, color="white", fontsize=8.5,
                    transform=ax.transAxes, zorder=6)
            ax.text(placar_x,   sub_hdr_y, "PLACAR", ha="center", va="center",
                    fontproperties=prop_bold, color="white", fontsize=8.5,
                    transform=ax.transAxes, zorder=6)
            ax.text(xg_right_x, sub_hdr_y, "xG",     ha="center", va="center",
                    fontproperties=prop_bold, color="white", fontsize=8.5,
                    transform=ax.transAxes, zorder=6)

            avail_h = inner_h - 0.030
            step    = avail_h / 3.0
            slot_y0 = sub_hdr_y - 0.014

            for idx, jogo in enumerate(jogos[:3]):
                ly = slot_y0 - idx * step - step / 2

                # Linha divisória entre rodadas
                if idx < 2:
                    div_game_y = slot_y0 - (idx + 1) * step
                    ax.plot([bx, bx + BLK_W], [div_game_y, div_game_y],
                            color='black', lw=1.0,
                            transform=ax.transAxes, zorder=20)

                hg = jogo.get("home_goals", 0) or 0
                ag = jogo.get("away_goals", 0) or 0
                hx = jogo.get("home_xg",   0.0) or 0.0
                ax_v = jogo.get("away_xg",  0.0) or 0.0

                placar_str = f"{hg} - {ag}"
                xg_l_str   = f"{hx:.2f}"
                xg_r_str   = f"{ax_v:.2f}"

                ax.text(xg_left_x,  ly, xg_l_str,   ha="center", va="center",
                        fontproperties=prop, fontsize=9.5, color="black",
                        transform=ax.transAxes, zorder=5)
                ax.text(xg_right_x, ly, xg_r_str,   ha="center", va="center",
                        fontproperties=prop, fontsize=9.5, color="black",
                        transform=ax.transAxes, zorder=5)
                ax.text(placar_x,   ly, placar_str,  ha="center", va="center",
                        fontproperties=prop, fontsize=11, color="black",
                        transform=ax.transAxes, zorder=5)

                # Logos das equipes do jogo histórico
                lc_w = 0.038
                lc_h = lc_w / aspect
                for lx, lkey_team in [
                    (logo_L_x, get_team_logo_path(jogo.get("home_name", ""))),
                    (logo_R_x, get_team_logo_path(jogo.get("away_name", ""))),
                ]:
                    ax.add_patch(Ellipse((lx + shd_ox, ly - shd_oy),
                                        lc_w, lc_h,
                                        color='black', alpha=0.4,
                                        transform=ax.transAxes, zorder=4))
                    ax.add_patch(Ellipse((lx, ly), lc_w, lc_h,
                                        color='white',
                                        transform=ax.transAxes, zorder=5))
                    if lkey_team:
                        add_image(ax, lkey_team, lx, ly, zoom=0.021, zorder=6)

    # — Rodapé —
    footer_h = 0.030
    ax.add_patch(plt.Rectangle(
        (0, 0), 1, footer_h,
        color=COLOR_HEADER_BG, transform=ax.transAxes, zorder=10
    ))
    ax.text(0.5, footer_h/2, "MATERIAL EXCLUSIVO DO TCC – EVIDÊNCIAS",
            ha="center", va="center", color=COLOR_HEADER_TEXT,
            fontproperties=prop, fontsize=12,
            transform=ax.transAxes, zorder=11)
    add_image(ax, "logo_logo_tcc_branco", 0.1, footer_h/2, zoom=0.044, zorder=12)
    add_image(ax, "logo_logo_tcc_branco", 0.9, footer_h/2, zoom=0.044, zorder=12)

    out = str(BASE_DIR / f"Evidencias_R{rodada_num}.png")
    plt.savefig(out, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    gc.collect()
    return out
