"""
sofascore_api.py — camada de acesso a dados (SofaScore).

Substitui a FootyStats como fonte analítica. Motivo, medido no Brasileirão 2026:

    teste                                   FootyStats   SofaScore
    R² do xG explicado só por nº de chutes       0,914       0,339
    coef. variação do xG por chute               0,156       0,482
    correlação xG × gols                         0,199       0,427
    correlação chutes no alvo × gols             0,476       0,410

O xG da FootyStats é praticamente `0,095 × chutes + 0,18` — um contador de
finalização disfarçado. O do SofaScore discrimina qualidade de chance de
verdade (pênalti 0,79 · contra-ataque 0,17 · escanteio 0,06) e é o único dos
dois que supera "chutes no alvo" na previsão de gols.

Acesso: API não documentada, sem chave. O bloqueio de Cloudflare é resolvido
pela biblioteca `soccerdata`, que usa um cliente TLS compatível.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / ".cache"
API = "https://api.sofascore.com/api/v1"

# Brasileirão Série A 2026. Para outra liga/temporada, ver os IDs no site.
TOURNAMENT_ID = 325
SEASON_ID = 87678
LIGA_SOCCERDATA = "BRA-Serie A"
TEMPORADA_SOCCERDATA = "2026"

# ---------------------------------------------------------------------------
# NOMES
# ---------------------------------------------------------------------------
# O SofaScore usa grafias próprias. Aqui elas viram os nomes canônicos que os
# escudos e o restante da plataforma já esperam.
TEAM_NAME_MAP = {
    "Palmeiras": "Palmeiras",
    "Flamengo": "Flamengo",
    "Athletico": "Athletico PR",
    "Athletico Paranaense": "Athletico PR",
    "Fluminense": "Fluminense",
    "Bahia": "Bahia",
    "Red Bull Bragantino": "Bragantino",
    "Bragantino": "Bragantino",
    "Cruzeiro": "Cruzeiro",
    "Botafogo": "Botafogo",
    "Corinthians": "Corinthians",
    "Atlético Mineiro": "Atletico MG",
    "Atletico Mineiro": "Atletico MG",
    "Coritiba": "Coritiba",
    "São Paulo": "Sao Paulo",
    "Sao Paulo": "Sao Paulo",
    "Vitória": "Vitoria",
    "Vitoria": "Vitoria",
    "Mirassol": "Mirassol",
    "Santos": "Santos",
    "Internacional": "Internacional",
    "Grêmio": "Gremio",
    "Gremio": "Gremio",
    "Vasco da Gama": "Vasco",
    "Vasco": "Vasco",
    "Remo": "Remo",
    "Chapecoense": "Chapecoense",
}


def normalize_team_name(name: str) -> str:
    """Nome canônico a partir de qualquer grafia do SofaScore."""
    if not name:
        return name
    if name in TEAM_NAME_MAP:
        return TEAM_NAME_MAP[name]
    alvo = name.lower()
    for k, v in TEAM_NAME_MAP.items():
        if k.lower() in alvo or alvo in k.lower():
            return v
    return name


# ---------------------------------------------------------------------------
# CLIENTE
# ---------------------------------------------------------------------------

_cliente = None


def _sofa():
    """Cliente do soccerdata — é ele que atravessa o Cloudflare."""
    global _cliente
    if _cliente is None:
        import soccerdata as sd
        _cliente = sd.Sofascore(leagues=LIGA_SOCCERDATA,
                                seasons=TEMPORADA_SOCCERDATA)
    return _cliente


def _get(url: str, tentativas: int = 3) -> dict | None:
    for i in range(tentativas):
        try:
            return json.loads(_sofa().get(url).read())
        except Exception:
            if i == tentativas - 1:
                return None
            time.sleep(1.5 * (i + 1))
    return None


# ---------------------------------------------------------------------------
# LEITURA DAS ESTATÍSTICAS
# ---------------------------------------------------------------------------

def _num(v):
    """'6' · '65%' · '10/19 (53%)' → primeiro número como float."""
    if v is None:
        return None
    m = re.match(r"-?\d+\.?\d*", str(v))
    return float(m.group()) if m else None


# rótulo do SofaScore → chave interna
STATS_QUERIDAS = {
    "Expected goals":            "xg",
    "Expected goals on target":  "xgot",
    "Total shots":               "chutes",
    "Shots on target":           "sot",
    "Shots inside box":          "chutes_area",
    "Shots outside box":         "chutes_fora_area",
    "Blocked shots":             "chutes_bloqueados",
    "Big chances":               "grandes_chances",
    "Big chances missed":        "grandes_chances_perdidas",
    "Big chances scored":        "grandes_chances_convertidas",
    "Touches in penalty area":   "toques_area",
    "Ball possession":           "posse",
    "Corner kicks":              "escanteios",
    "Goalkeeper saves":          "defesas_goleiro",
    "Goals prevented":           "gols_evitados",
    "Total saves":               "defesas_totais",
}


def _stats_do_jogo(event_id: int) -> dict:
    """Estatísticas agregadas do jogo, já com os dois lados separados."""
    d = _get(f"{API}/event/{event_id}/statistics")
    saida = {}
    if not d:
        return saida
    for periodo in d.get("statistics", []):
        if periodo.get("period") != "ALL":
            continue
        for grupo in periodo.get("groups", []):
            for item in grupo.get("statisticsItems", []):
                chave = STATS_QUERIDAS.get(item.get("name"))
                if chave and chave not in saida:
                    saida[chave] = (_num(item.get("home")), _num(item.get("away")))
    return saida


# Situações do SofaScore agrupadas em famílias analíticas.
FAMILIA_SITUACAO = {
    "regular":            "jogada",
    "assisted":           "jogada",
    "fast-break":         "contra_ataque",
    "corner":             "bola_parada",
    "set-piece":          "bola_parada",
    "free-kick":          "bola_parada",
    "throw-in-set-piece": "bola_parada",
    "penalty":            "penalti",
    "own-goal":           "outros",
}


def _shotmap_do_jogo(event_id: int) -> dict:
    """
    Abre o shotmap chute a chute.

    É a fonte mais rica que temos: cada finalização vem com xG próprio,
    situação (jogada, contra-ataque, bola parada, pênalti) e parte do corpo.
    Permite responder de ONDE vem o perigo de um time e por ONDE uma defesa
    está sendo furada — coisa que nenhuma média agregada mostra.
    """
    d = _get(f"{API}/event/{event_id}/shotmap")
    vazio = {"pen_goals": 0, "xg_jogada": 0.0, "xg_bola_parada": 0.0,
             "xg_contra_ataque": 0.0, "xg_penalti": 0.0,
             "chutes_jogada": 0, "chutes_bola_parada": 0, "n_chutes": 0}
    saida = {"casa": dict(vazio), "fora": dict(vazio)}
    if not d:
        return saida

    for c in d.get("shotmap", []):
        lado = "casa" if c.get("isHome") else "fora"
        s = saida[lado]
        fam = FAMILIA_SITUACAO.get(c.get("situation"), "jogada")
        xg = c.get("xg") or 0.0

        s["n_chutes"] += 1
        if fam == "penalti":
            s["xg_penalti"] += xg
            if c.get("shotType") == "goal":
                s["pen_goals"] += 1
        elif fam == "bola_parada":
            s["xg_bola_parada"] += xg
            s["chutes_bola_parada"] += 1
        elif fam == "contra_ataque":
            s["xg_contra_ataque"] += xg
            s["chutes_jogada"] += 1
        else:
            s["xg_jogada"] += xg
            s["chutes_jogada"] += 1

    for lado in ("casa", "fora"):
        for k in ("xg_jogada", "xg_bola_parada", "xg_contra_ataque", "xg_penalti"):
            saida[lado][k] = round(saida[lado][k], 3)
    return saida


# ---------------------------------------------------------------------------
# COLETA
# ---------------------------------------------------------------------------

def _eventos_da_temporada(season_id: int | None = None) -> list[dict]:
    """Todos os jogos da temporada — disputados e futuros."""
    sid = season_id or SEASON_ID
    eventos, vistos = [], set()
    for rota in ("last", "next"):
        for pagina in range(0, 12):
            d = _get(f"{API}/unique-tournament/{TOURNAMENT_ID}"
                     f"/season/{sid}/events/{rota}/{pagina}")
            if not d:
                break
            novos = d.get("events", [])
            for e in novos:
                if e["id"] not in vistos:
                    vistos.add(e["id"])
                    eventos.append(e)
            if not d.get("hasNextPage"):
                break
    return eventos


def _monta_jogo(e: dict, stats: dict, shot: dict) -> dict:
    """Um evento do SofaScore no formato que a plataforma consome."""
    terminado = e.get("status", {}).get("type") == "finished"

    def par(chave, casa=True):
        v = stats.get(chave)
        if not v:
            return None
        return v[0] if casa else v[1]

    j = {
        "id":         e["id"],
        "game_week":  int((e.get("roundInfo") or {}).get("round") or 0),
        "status":     "complete" if terminado else "incomplete",
        "date_unix":  e.get("startTimestamp", 0),
        "home_name":  normalize_team_name(e["homeTeam"]["name"]),
        "away_name":  normalize_team_name(e["awayTeam"]["name"]),
        "home_goals": e.get("homeScore", {}).get("current") if terminado else None,
        "away_goals": e.get("awayScore", {}).get("current") if terminado else None,
    }
    if not terminado:
        for c in ("home_xg", "away_xg", "home_sot", "away_sot"):
            j[c] = None
        return j

    # nomes mantidos compatíveis com o restante da plataforma
    j["home_xg"] = par("xg", True)
    j["away_xg"] = par("xg", False)
    j["home_sot"] = int(par("sot", True) or 0)
    j["away_sot"] = int(par("sot", False) or 0)

    # campos novos, indisponíveis na FootyStats
    for interno, chave in (
        ("xgot", "xgot"), ("shots", "chutes"), ("shots_box", "chutes_area"),
        ("shots_out_box", "chutes_fora_area"), ("shots_blocked", "chutes_bloqueados"),
        ("big_chances", "grandes_chances"),
        ("big_chances_missed", "grandes_chances_perdidas"),
        ("touches_box", "toques_area"), ("possession", "posse"),
        ("corners", "escanteios"), ("gk_saves", "defesas_goleiro"),
        ("goals_prevented", "gols_evitados"),
    ):
        j[f"home_{interno}"] = par(chave, True)
        j[f"away_{interno}"] = par(chave, False)

    # decomposição do perigo por tipo de jogada (vem do shotmap)
    for lado, pref in (("casa", "home"), ("fora", "away")):
        s = shot.get(lado, {})
        for k in ("pen_goals", "xg_jogada", "xg_bola_parada", "xg_contra_ataque",
                  "xg_penalti", "chutes_jogada", "chutes_bola_parada"):
            j[f"{pref}_{k}"] = s.get(k, 0)
    return j


# ---------------------------------------------------------------------------
# CACHE EM DISCO
# ---------------------------------------------------------------------------

# Temporadas anteriores — usadas para ampliar a base de validação do motor.
# Não entram na análise da rodada, só no backtest.
SEASONS_HISTORICAS = {
    "2025": 72034,
    "2024": 58766,
    "2023": 48982,
    "2022": 40557,
}


def _arquivo_cache(season_id: int | None = None) -> Path:
    sid = season_id or SEASON_ID
    return CACHE_DIR / f"sofascore_{TOURNAMENT_ID}_{sid}.json"


def coletar_temporada(forcar: bool = False, progresso=None,
                      season_id: int | None = None) -> list[dict]:
    """
    Coleta a temporada inteira. Jogos já disputados e coletados antes não são
    baixados de novo — o cache em disco guarda cada um pelo id.
    """
    CACHE_DIR.mkdir(exist_ok=True)
    sid = season_id or SEASON_ID
    arq = _arquivo_cache(sid)

    antigos = {}
    if arq.exists() and not forcar:
        try:
            antigos = {j["id"]: j for j in json.loads(arq.read_text("utf-8"))}
        except Exception:
            antigos = {}

    eventos = _eventos_da_temporada(sid)

    # SofaScore/Cloudflare às vezes bloqueia o IP de quem chama (comum em
    # servidores de nuvem, como o Streamlit Cloud). Sem isso, uma falha de
    # rede zerava a temporada inteira, sobrescrevendo o cache bom com vazio.
    if not eventos and antigos:
        return list(antigos.values())

    jogos, baixados = [], 0
    pendentes = [e for e in eventos
                 if e.get("status", {}).get("type") == "finished"
                 and e["id"] not in antigos]
    total = len(pendentes)

    for e in eventos:
        eid = e["id"]
        terminado = e.get("status", {}).get("type") == "finished"

        # cache só é aproveitado se o jogo guardado já tem os campos novos
        if terminado and eid in antigos and "home_xg_jogada" in antigos[eid]:
            jogos.append(antigos[eid])
            continue
        if not terminado:
            jogos.append(_monta_jogo(e, {}, {}))
            continue

        stats = _stats_do_jogo(eid)
        shot = _shotmap_do_jogo(eid)
        jogos.append(_monta_jogo(e, stats, shot))
        baixados += 1
        if progresso and total:
            progresso(baixados / total,
                      f"Baixando jogo {baixados} de {total}...")

    arq.write_text(json.dumps(jogos, ensure_ascii=False), "utf-8")
    return jogos


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_all_matches(_v: int = 1) -> list[dict]:
    """Interface que a plataforma consome (mesmo contrato do módulo antigo)."""
    return coletar_temporada()


def limpar_cache_disco() -> bool:
    arq = _arquivo_cache()
    if arq.exists():
        arq.unlink()
        return True
    return False
