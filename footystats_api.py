"""
FootyStats API — camada de acesso a dados.
Todas as chamadas são cacheadas por 1h para evitar repetição durante a sessão.
"""
import requests
import streamlit as st

FOOTYSTATS_BASE = "https://api.football-data-api.com"
BRASILEIRAO_2026_ID = 16544

# Mapeia nomes vindos da API para os nomes canônicos usados nos logos/filtros
TEAM_NAME_MAP = {
    # Nomes completos → simplificado
    "CR Flamengo": "Flamengo",
    "SE Palmeiras": "Palmeiras",
    "SC Internacional": "Internacional",
    "Grêmio FB Porto Alegrense": "Gremio",
    "São Paulo FC": "Sao Paulo",
    "EC Vitória": "Vitoria",
    "Cruzeiro EC": "Cruzeiro",
    "EC Bahia": "Bahia",
    "Fluminense FC": "Fluminense",
    "Botafogo FR": "Botafogo",
    "Sport Club Corinthians Paulista": "Corinthians",
    "Club de Regatas Vasco da Gama": "Vasco",
    "Santos FC": "Santos",
    "Clube Atlético Mineiro": "Atletico MG",
    "Club Athletico Paranaense": "Athletico PR",
    "Coritiba FC": "Coritiba",
    "Chapecoense": "Chapecoense",
    "Red Bull Bragantino": "Bragantino",
    "Mirassol FC": "Mirassol",
    "Clube do Remo": "Remo",
    # Nomes curtos da API (home_name / away_name nos matches)
    "Flamengo": "Flamengo",
    "Palmeiras": "Palmeiras",
    "Internacional": "Internacional",
    "Grêmio": "Gremio",
    "Gremio": "Gremio",
    "São Paulo": "Sao Paulo",
    "Sao Paulo": "Sao Paulo",
    "Vitória": "Vitoria",
    "Vitoria": "Vitoria",
    "Cruzeiro": "Cruzeiro",
    "Bahia": "Bahia",
    "Fluminense": "Fluminense",
    "Botafogo": "Botafogo",
    "Corinthians": "Corinthians",
    "Vasco da Gama": "Vasco",
    "Vasco": "Vasco",
    "Santos": "Santos",
    "Atlético Mineiro": "Atletico MG",
    "Atletico MG": "Atletico MG",
    "Atlético PR": "Athletico PR",
    "Athletico PR": "Athletico PR",
    "Coritiba": "Coritiba",
    "Chapecoense": "Chapecoense",
    "Bragantino": "Bragantino",
    "Mirassol": "Mirassol",
    "Remo": "Remo",
}


def normalize_team_name(name: str) -> str:
    """Retorna o nome canônico do time a partir de qualquer variação da API."""
    if not name:
        return name
    if name in TEAM_NAME_MAP:
        return TEAM_NAME_MAP[name]
    # Busca parcial case-insensitive como fallback
    name_lower = name.lower()
    for key, val in TEAM_NAME_MAP.items():
        if key.lower() in name_lower:
            return val
    return name


def _get_api_key() -> str:
    try:
        return st.secrets["FOOTYSTATS_API_KEY"]
    except Exception:
        # fallback para desenvolvimento local
        return "d998af6614a9e86daaef060a3c689e3dce87e1aa4a0b92ad93a4f35ff12ae58e"


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_all_matches(season_id: int = BRASILEIRAO_2026_ID) -> list[dict]:
    """
    Retorna todos os jogos da temporada (completos e agendados).
    Cada jogo é um dict normalizado com os campos que a plataforma usa.
    """
    key = _get_api_key()
    resp = requests.get(
        f"{FOOTYSTATS_BASE}/league-matches",
        params={"key": key, "season_id": season_id},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success"):
        raise ValueError(f"FootyStats erro: {payload.get('message', 'desconhecido')}")

    matches = []
    for m in payload["data"]:
        complete = m.get("status") == "complete"
        home_sot = m.get("team_a_shotsOnTarget", -1)
        away_sot = m.get("team_b_shotsOnTarget", -1)
        matches.append({
            "id": m["id"],
            "game_week": int(m.get("game_week", 0)),
            "status": m.get("status", "incomplete"),
            "date_unix": m.get("date_unix", 0),
            "home_name": normalize_team_name(m.get("home_name", "")),
            "away_name": normalize_team_name(m.get("away_name", "")),
            # Resultados (None quando jogo não foi disputado)
            "home_goals": int(m["homeGoalCount"]) if complete else None,
            "away_goals": int(m["awayGoalCount"]) if complete else None,
            "home_xg":    float(m["team_a_xg"])   if complete else None,
            "away_xg":    float(m["team_b_xg"])   if complete else None,
            # -1 = dado não disponível
            "home_sot": int(home_sot) if complete and home_sot != -1 else None,
            "away_sot": int(away_sot) if complete and away_sot != -1 else None,
        })
    return matches
