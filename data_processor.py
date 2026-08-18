"""
data_processor.py — lógica de negócio da plataforma.

Fonte de dados: SofaScore (via sofascore_api.py).

A FootyStats foi abandonada como fonte analítica em 2026-08-04: o xG dela é
explicado em 91% apenas pelo número de chutes, e perdia para "chutes no alvo"
na previsão de gols. Ver o cabeçalho de sofascore_api.py para os números.
"""
import pandas as pd
from sofascore_api import fetch_all_matches


# ---------------------------------------------------------------------------
# RODADAS / CONFRONTOS
# ---------------------------------------------------------------------------

def get_rodadas_disponiveis() -> list[int]:
    """Retorna lista de todas as rodadas disponíveis na API (1-38)."""
    matches = fetch_all_matches()
    return sorted(set(m["game_week"] for m in matches))


def resumo_calendario(matches: list[dict], agora_unix: int | None = None) -> dict:
    """Resumo sem confundir partidas adiadas com a próxima rodada da agenda."""
    import time
    agora = int(agora_unix or time.time())
    por_rodada = {}
    for m in matches:
        if m.get("game_week", 0) > 0:
            por_rodada.setdefault(m["game_week"], []).append(m)

    completas = [r for r, jogos in por_rodada.items()
                 if len(jogos) == 10 and all(j["status"] == "complete" for j in jogos)]
    futuros = [m for m in matches
               if m["status"] != "complete" and int(m.get("date_unix") or 0) >= agora]
    if futuros:
        proxima = min(futuros, key=lambda m: m["date_unix"])["game_week"]
    else:
        incompletas = [r for r, jogos in por_rodada.items()
                       if any(j["status"] != "complete" for j in jogos)]
        proxima = min(incompletas, default=max(por_rodada, default=1))
    return {
        "total": len(matches),
        "completos": sum(m["status"] == "complete" for m in matches),
        "agendados": sum(m["status"] != "complete" for m in matches),
        "ultima_rod": max(completas, default=0),
        "proxima_rod": proxima,
    }


def get_confrontos_rodada(rodada_num: int) -> list[dict]:
    """Retorna os confrontos de uma rodada com mandante, visitante e status."""
    matches = fetch_all_matches()
    confrontos = []
    for m in matches:
        if m["game_week"] == rodada_num:
            confrontos.append({
                "Mandante":  m["home_name"],
                "Visitante": m["away_name"],
                "Status":    m["status"],
                "Rodada":    rodada_num,
            })
    return confrontos


# ---------------------------------------------------------------------------
# CÁLCULO DE MÉTRICAS
# ---------------------------------------------------------------------------

def _calcular_metricas(
    team_name: str,
    rodada_alvo: int,
    n_jogos: int,
    tipo_filtro: str,
    mando_role: str,          # 'home' ou 'away'
) -> tuple[dict, list[dict]]:
    """
    Calcula todas as métricas de um time para os últimos N jogos no mando correto.

    Retorna:
        stats  : dict com GP, GS, XG, XGA, CHUT_AG_CONQ, CHUT_AG_CED,
                 CONV_CONQ, CONV_CED, SG_CONQ, SG_CED, GC_CONQ, GC_CED, Jogos
        recorte: lista de dicts dos jogos usados (para evidências)
    """
    matches = fetch_all_matches()

    # Apenas jogos completos ANTERIORES à rodada alvo
    historico = [
        m for m in matches
        if m["status"] == "complete"
        and m["game_week"] < rodada_alvo
        and (m["home_name"] == team_name or m["away_name"] == team_name)
    ]

    # Mais recente primeiro
    historico.sort(key=lambda x: x["date_unix"], reverse=True)

    # Filtro por mando (se selecionado)
    if tipo_filtro == "POR_MANDO":
        if mando_role == "home":
            historico = [m for m in historico if m["home_name"] == team_name]
        else:
            historico = [m for m in historico if m["away_name"] == team_name]

    recorte = historico[:n_jogos]

    zeros = {
        "GP": 0, "GS": 0, "XG": 0.0, "XGA": 0.0,
        "CHUT_AG_CONQ": 0.0, "CHUT_AG_CED": 0.0,
        "CONV_CONQ": 0.0, "CONV_CED": 0.0,
        "SG_CONQ": 0, "SG_CED": 0,
        "GC_CONQ": 0.0, "GC_CED": 0.0, "Jogos": 0,
    }
    if not recorte:
        return zeros, []

    gp = gs = sg_conq = sg_ced = 0
    xg_sum = xga_sum = 0.0
    sot_conq_sum = sot_ced_sum = 0.0
    sot_conq_n = sot_ced_n = 0
    gc_conq_sum = gc_ced_sum = 0.0
    gc_conq_n = gc_ced_n = 0

    for m in recorte:
        is_home = (m["home_name"] == team_name)

        _gp  = m["home_goals"] if is_home else m["away_goals"]
        _gs  = m["away_goals"] if is_home else m["home_goals"]
        _xg  = m["home_xg"]   if is_home else m["away_xg"]
        _xga = m["away_xg"]   if is_home else m["home_xg"]
        _sot_conq = m["home_sot"] if is_home else m["away_sot"]
        _sot_ced  = m["away_sot"] if is_home else m["home_sot"]
        # Grandes chances: finalizações de qualidade clara (SofaScore).
        # ~96% de cobertura — trata ausência como dado faltante, não zero.
        _gc_conq = m.get("home_big_chances") if is_home else m.get("away_big_chances")
        _gc_ced  = m.get("away_big_chances") if is_home else m.get("home_big_chances")

        gp  += _gp  or 0
        gs  += _gs  or 0
        xg_sum  += _xg  or 0.0
        xga_sum += _xga or 0.0

        if _sot_conq is not None:
            sot_conq_sum += _sot_conq
            sot_conq_n   += 1
        if _sot_ced is not None:
            sot_ced_sum += _sot_ced
            sot_ced_n   += 1
        if _gc_conq is not None:
            gc_conq_sum += _gc_conq
            gc_conq_n   += 1
        if _gc_ced is not None:
            gc_ced_sum += _gc_ced
            gc_ced_n   += 1

        if _gs == 0:
            sg_conq += 1
        if _gp == 0:
            sg_ced += 1

    n = len(recorte)
    avg_sot_conq = sot_conq_sum / sot_conq_n if sot_conq_n else 0.0
    avg_sot_ced  = sot_ced_sum  / sot_ced_n  if sot_ced_n  else 0.0
    avg_gc_conq  = gc_conq_sum  / gc_conq_n  if gc_conq_n  else 0.0
    avg_gc_ced   = gc_ced_sum   / gc_ced_n   if gc_ced_n   else 0.0
    conv_conq = (gp / sot_conq_sum * 100) if sot_conq_sum > 0 else 0.0
    conv_ced  = (gs / sot_ced_sum  * 100) if sot_ced_sum  > 0 else 0.0

    stats = {
        "GP": gp,
        "GS": gs,
        "XG":  xg_sum  / n,
        "XGA": xga_sum / n,
        "CHUT_AG_CONQ": avg_sot_conq,
        "CHUT_AG_CED":  avg_sot_ced,
        "CONV_CONQ": conv_conq,
        "CONV_CED":  conv_ced,
        "SG_CONQ": sg_conq,
        "SG_CED":  sg_ced,
        "GC_CONQ": avg_gc_conq,
        "GC_CED":  avg_gc_ced,
        "Jogos": n,
    }
    return stats, recorte


# ---------------------------------------------------------------------------
# CONSTRUÇÃO DOS 4 DATAFRAMES
# ---------------------------------------------------------------------------

def build_analysis_dataframes(
    confrontos: list[dict],
    rodada_num: int,
    n_jogos: int,
    tipo_filtro: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict]]:
    """
    Constrói os 4 DataFrames para os blocos do infográfico e a lista de evidências.

    Bloco 1 — Ofensiva do Mandante  (time joga em CASA)
    Bloco 2 — Defensiva do Visitante (time joga FORA)
    Bloco 3 — Ofensiva do Visitante  (time joga FORA)
    Bloco 4 — Defensiva do Mandante  (time joga em CASA)

    Estrutura dos DFs (GC = grandes chances, adicionado 2026-08-05 — entra ao
    lado de CHUT_AG por ser a mesma família (volume de perigo criado/cedido),
    mas filtrado por qualidade de chance em vez de volume bruto de chute):
      df_b1: [MANDANTE, SG_CED, CHUT_AG_CONQ, GC_CONQ, CONV_CONQ, GP, XG]
      df_b2: [XGA, GS, CONV_CED, GC_CED, CHUT_AG_CED, SG_CONQ, VISITANTE]
      df_b3: [VISITANTE, SG_CED, CHUT_AG_CONQ, GC_CONQ, CONV_CONQ, GP, XG]
      df_b4: [XGA, GS, CONV_CED, GC_CED, CHUT_AG_CED, SG_CONQ, MANDANTE]
    """
    rows_b1, rows_b2, rows_b3, rows_b4 = [], [], [], []
    evidence_list = []

    for c in confrontos:
        mandante  = c["Mandante"]
        visitante = c["Visitante"]

        stats_mand, jogos_mand = _calcular_metricas(mandante,  rodada_num, n_jogos, tipo_filtro, "home")
        stats_vis,  jogos_vis  = _calcular_metricas(visitante, rodada_num, n_jogos, tipo_filtro, "away")

        # Bloco 1: ataque do mandante jogando em casa
        rows_b1.append({
            "MANDANTE":     mandante,
            "SG_CED":       stats_mand["SG_CED"],
            "CHUT_AG_CONQ": stats_mand["CHUT_AG_CONQ"],
            "GC_CONQ":      stats_mand["GC_CONQ"],
            "CONV_CONQ":    stats_mand["CONV_CONQ"],
            "GP":           stats_mand["GP"],
            "XG":           stats_mand["XG"],
        })

        # Bloco 2: defesa do visitante jogando fora
        rows_b2.append({
            "XGA":          stats_vis["XGA"],
            "GS":           stats_vis["GS"],
            "CONV_CED":     stats_vis["CONV_CED"],
            "GC_CED":       stats_vis["GC_CED"],
            "CHUT_AG_CED":  stats_vis["CHUT_AG_CED"],
            "SG_CONQ":      stats_vis["SG_CONQ"],
            "VISITANTE":    visitante,
        })

        # Bloco 3: ataque do visitante jogando fora
        rows_b3.append({
            "VISITANTE":    visitante,
            "SG_CED":       stats_vis["SG_CED"],
            "CHUT_AG_CONQ": stats_vis["CHUT_AG_CONQ"],
            "GC_CONQ":      stats_vis["GC_CONQ"],
            "CONV_CONQ":    stats_vis["CONV_CONQ"],
            "GP":           stats_vis["GP"],
            "XG":           stats_vis["XG"],
        })

        # Bloco 4: defesa do mandante jogando em casa
        rows_b4.append({
            "XGA":         stats_mand["XGA"],
            "GS":          stats_mand["GS"],
            "CONV_CED":    stats_mand["CONV_CED"],
            "GC_CED":      stats_mand["GC_CED"],
            "CHUT_AG_CED": stats_mand["CHUT_AG_CED"],
            "SG_CONQ":     stats_mand["SG_CONQ"],
            "MANDANTE":    mandante,
        })

        evidence_list.append({
            "mandante_nome":  mandante,
            "visitante_nome": visitante,
            "jogos_mandante": jogos_mand,   # histórico em casa
            "jogos_visitante": jogos_vis,   # histórico fora
        })

    df_b1 = pd.DataFrame(rows_b1)
    df_b2 = pd.DataFrame(rows_b2)
    df_b3 = pd.DataFrame(rows_b3)
    df_b4 = pd.DataFrame(rows_b4)

    if df_b1.empty:
        return df_b1, df_b2, df_b3, df_b4, evidence_list

    # Ordenar par B1+B2 por XG do mandante (maior xG ofensivo no topo)
    idx_b12 = df_b1.sort_values("XG", ascending=False).index
    df_b1 = df_b1.loc[idx_b12].reset_index(drop=True)
    df_b2 = df_b2.loc[idx_b12].reset_index(drop=True)

    # Ordenar par B3+B4 por XGA do mandante (defesa do mandante: menor XGA no topo)
    idx_b34 = df_b4.sort_values("XGA", ascending=True).index
    df_b3 = df_b3.loc[idx_b34].reset_index(drop=True)
    df_b4 = df_b4.loc[idx_b34].reset_index(drop=True)

    return df_b1, df_b2, df_b3, df_b4, evidence_list
