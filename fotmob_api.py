"""
fotmob_api.py — camada de acesso a dados (FotMob).

Substitui o SofaScore como fonte da temporada atual. Motivo: em outubro de 2026
o SofaScore passou a devolver 403 para qualquer cliente que não seja um
navegador (inclusive a `soccerdata`, mesmo de IP residencial).

Acesso: o FotMob entrega a página de cada jogo e da liga como HTML comum, com
todos os números embutidos em JSON (`__NEXT_DATA__`). Não há API privada, chave,
cookie nem disfarce de navegador — é a mesma página que qualquer pessoa abre.
Por isso a coleta é educada: uma requisição por vez, pausa entre jogos, e só os
jogos novos são baixados (o cache em disco guarda os já coletados).

O registro de saída tem o MESMO formato do antigo `sofascore_api._monta_jogo`,
então analytics_engine, data_processor e as artes não mudam.

Diferenças de dado em relação ao SofaScore (medidas jogo a jogo, ver docs):
  · o xG é de outro fornecedor — tem outra escala; não misturar fontes na
    mesma temporada (por isso a temporada inteira é coletada aqui);
  · "gols evitados pelo goleiro" não vem pronto: é calculado como
    xGOT sofrido − gols sofridos.
"""
from __future__ import annotations

import gzip
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import streamlit as st

from sofascore_api import _deduplicar_eventos, _num, normalize_team_name  # noqa: F401

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / ".cache"
SITE = "https://www.fotmob.com"

# Brasileirão Série A. Para outra liga, o id aparece na URL do FotMob.
LIGA_ID = 268
LIGA_SLUG = "serie-a"
TEMPORADA = 2026

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
PAUSA_ENTRE_JOGOS = 0.4        # segundos — cortesia com o servidor
SALVAR_A_CADA = 25             # jogos baixados entre gravações do cache

_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


# ---------------------------------------------------------------------------
# REDE
# ---------------------------------------------------------------------------

ULTIMO_ERRO = ""     # motivo da última falha de rede, para mensagens claras


def _baixar(url: str, tentativas: int = 3) -> str | None:
    """Texto da página, ou None se não foi possível (após novas tentativas)."""
    global ULTIMO_ERRO
    for i in range(tentativas):
        espera = 2.0 * (i + 1)
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": _UA, "Accept-Language": "en",
                "Accept-Encoding": "gzip",
            })
            with urllib.request.urlopen(req, timeout=30) as r:
                bruto = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    bruto = gzip.decompress(bruto)
                return bruto.decode("utf-8")
        except urllib.error.HTTPError as e:
            ULTIMO_ERRO = f"HTTP {e.code}"
            if e.code in (429, 503):          # servidor pedindo calma
                espera = 15.0 * (i + 1)
        except Exception as e:
            ULTIMO_ERRO = type(e).__name__
        if i < tentativas - 1:
            time.sleep(espera)
    return None


def _next_data(html: str | None) -> dict | None:
    if not html:
        return None
    m = _NEXT_DATA.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# CALENDÁRIO
# ---------------------------------------------------------------------------

def _url_liga() -> str:
    return f"{SITE}/leagues/{LIGA_ID}/overview/{LIGA_SLUG}"


def _evento_do_calendario(m: dict) -> dict:
    st_ = m.get("status") or {}
    placar = re.match(r"\s*(\d+)\s*-\s*(\d+)", st_.get("scoreStr") or "")
    try:
        data = int(datetime.fromisoformat(
            st_["utcTime"].replace("Z", "+00:00")).timestamp())
    except (KeyError, ValueError):
        data = 0
    return {
        "id": int(m["id"]),
        "round": int(m.get("roundName") or m.get("round") or 0),
        "home": m["home"]["name"],
        "away": m["away"]["name"],
        "terminado": bool(st_.get("finished")) and not st_.get("cancelled"),
        "cancelado": bool(st_.get("cancelled")),
        "date_unix": data,
        "gols": (int(placar.group(1)), int(placar.group(2))) if placar else None,
        # O pageUrl do calendário identifica o PAR de times (ida e volta dividem
        # a mesma página); só /match/{id} devolve o jogo certo.
        "url": f"{SITE}/match/{int(m['id'])}",
    }


def _deduplicar_calendario(eventos: list[dict]) -> list[dict]:
    """Remarcações aparecem como dois ids para o mesmo confronto: fica o que
    foi disputado (ou, na falta, o não cancelado, ou o mais recente)."""
    por_confronto: dict[tuple, dict] = {}
    for e in eventos:
        chave = (e["round"], normalize_team_name(e["home"]), normalize_team_name(e["away"]))
        atual = por_confronto.get(chave)
        rank = (e["terminado"], not e["cancelado"], e["date_unix"], e["id"])
        if atual is None or rank > (atual["terminado"], not atual["cancelado"],
                                    atual["date_unix"], atual["id"]):
            por_confronto[chave] = e
    return list(por_confronto.values())


def _eventos_da_temporada() -> list[dict]:
    """Os 380 jogos da temporada, ou [] se a resposta não for íntegra
    (resposta parcial nunca pode substituir uma temporada completa em cache)."""
    d = _next_data(_baixar(_url_liga()))
    try:
        brutos = d["props"]["pageProps"]["fixtures"]["allMatches"]
    except (TypeError, KeyError):
        return []
    eventos = _deduplicar_calendario([_evento_do_calendario(m) for m in brutos])
    if len(eventos) != 380 or len({e["round"] for e in eventos}) != 38:
        return []
    return eventos


# ---------------------------------------------------------------------------
# DETALHES DO JOGO
# ---------------------------------------------------------------------------

# chave do FotMob → chave interna (mesmos nomes do registro antigo)
STATS_QUERIDAS = {
    "expected_goals":           "xg",
    "expected_goals_on_target": "xgot",
    "ShotsOnTarget":            "sot",
    "total_shots":              "chutes",
    "shots_inside_box":         "chutes_area",
    "shots_outside_box":        "chutes_fora_area",
    "blocked_shots":            "chutes_bloqueados",
    "big_chance":               "grandes_chances",
    "big_chance_missed_title":  "grandes_chances_perdidas",
    "touches_opp_box":          "toques_area",
    "BallPossesion":            "posse",
    "corners":                  "escanteios",
    "keeper_saves":             "defesas_goleiro",
}

FAMILIA_SITUACAO = {
    "RegularPlay":       "jogada",
    "FastBreak":         "contra_ataque",
    "FromCorner":        "bola_parada",
    "SetPiece":          "bola_parada",
    "FreeKick":          "bola_parada",
    "ThrowInSetPiece":   "bola_parada",
    "Penalty":           "penalti",
}


def _stats_do_jogo(content: dict) -> dict:
    """Estatísticas agregadas do jogo: {chave_interna: (casa, fora)}."""
    saida = {}
    try:
        grupos = content["stats"]["Periods"]["All"]["stats"]
    except (TypeError, KeyError):
        return saida
    for grupo in grupos:
        for item in grupo.get("stats", []):
            chave = STATS_QUERIDAS.get(item.get("key"))
            valores = item.get("stats") or []
            if not chave or chave in saida or len(valores) != 2 or None in valores:
                continue
            saida[chave] = (_num(valores[0]), _num(valores[1]))
    return saida


def _shotmap_do_jogo(content: dict, id_casa: int) -> dict:
    """Decomposição do perigo chute a chute — de onde vem o xG de cada time."""
    vazio = {"pen_goals": 0, "xg_jogada": 0.0, "xg_bola_parada": 0.0,
             "xg_contra_ataque": 0.0, "xg_penalti": 0.0,
             "chutes_jogada": 0, "chutes_bola_parada": 0, "n_chutes": 0}
    saida = {"casa": dict(vazio), "fora": dict(vazio)}
    for c in (content.get("shotmap") or {}).get("shots", []):
        if c.get("isOwnGoal"):
            continue
        s = saida["casa" if c.get("teamId") == id_casa else "fora"]
        fam = FAMILIA_SITUACAO.get(c.get("situation"), "jogada")
        xg = c.get("expectedGoals") or 0.0

        s["n_chutes"] += 1
        if fam == "penalti":
            s["xg_penalti"] += xg
            if c.get("eventType") == "Goal":
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


def _detalhes(ev: dict) -> tuple[dict, dict] | None:
    """(stats, shotmap) do jogo, ou None se a página não trouxe o xG — um jogo
    sem xG não é utilizável (média com zero falso envenenaria o ranking)."""
    d = _next_data(_baixar(ev["url"]))
    try:
        pp = d["props"]["pageProps"]
        content = pp["content"]
        id_casa = pp["general"]["homeTeam"]["id"]
        id_pagina = pp["general"]["matchId"]
    except (TypeError, KeyError):
        return None
    # Trava de integridade: página de outro jogo nunca entra como dado deste.
    if str(id_pagina) != str(ev["id"]):
        return None
    stats = _stats_do_jogo(content)
    if "xg" not in stats or "sot" not in stats:
        return None
    return stats, _shotmap_do_jogo(content, id_casa)


# ---------------------------------------------------------------------------
# REGISTRO NO FORMATO DA PLATAFORMA
# ---------------------------------------------------------------------------

def _jogo_base(ev: dict, completo: bool) -> dict:
    gols = ev["gols"] if completo and ev["gols"] else (None, None)
    return {
        "id":         ev["id"],
        "game_week":  ev["round"],
        "status":     "complete" if completo else "incomplete",
        "date_unix":  ev["date_unix"],
        "home_name":  normalize_team_name(ev["home"]),
        "away_name":  normalize_team_name(ev["away"]),
        "home_goals": gols[0],
        "away_goals": gols[1],
    }


def _jogo_incompleto(ev: dict) -> dict:
    j = _jogo_base(ev, False)
    for c in ("home_xg", "away_xg", "home_sot", "away_sot"):
        j[c] = None
    if ev["cancelado"]:          # adiado/cancelado: não conta como "em atraso"
        j["cancelado"] = True
    return j


def _monta_jogo(ev: dict, stats: dict, shot: dict) -> dict:
    j = _jogo_base(ev, True)

    def par(chave, casa=True):
        v = stats.get(chave)
        return None if not v else (v[0] if casa else v[1])

    j["home_xg"], j["away_xg"] = par("xg", True), par("xg", False)
    j["home_sot"] = int(par("sot", True) or 0)
    j["away_sot"] = int(par("sot", False) or 0)

    for interno, chave in (
        ("xgot", "xgot"), ("shots", "chutes"), ("shots_box", "chutes_area"),
        ("shots_out_box", "chutes_fora_area"), ("shots_blocked", "chutes_bloqueados"),
        ("big_chances", "grandes_chances"),
        ("big_chances_missed", "grandes_chances_perdidas"),
        ("touches_box", "toques_area"), ("possession", "posse"),
        ("corners", "escanteios"), ("gk_saves", "defesas_goleiro"),
    ):
        j[f"home_{interno}"] = par(chave, True)
        j[f"away_{interno}"] = par(chave, False)

    # gols evitados pelo goleiro = xGOT sofrido − gols sofridos
    for lado, adv in (("home", "away"), ("away", "home")):
        xgot_sofrido = j.get(f"{adv}_xgot")
        j[f"{lado}_goals_prevented"] = (
            round(xgot_sofrido - (j[f"{adv}_goals"] or 0), 2)
            if xgot_sofrido is not None else None
        )

    for lado, pref in (("casa", "home"), ("fora", "away")):
        s = shot.get(lado, {})
        for k in ("pen_goals", "xg_jogada", "xg_bola_parada", "xg_contra_ataque",
                  "xg_penalti", "chutes_jogada", "chutes_bola_parada"):
            j[f"{pref}_{k}"] = s.get(k, 0)
    return j


# ---------------------------------------------------------------------------
# CACHE EM DISCO + COLETA
# ---------------------------------------------------------------------------

def _arquivo_cache() -> Path:
    return CACHE_DIR / f"fotmob_{LIGA_ID}_{TEMPORADA}.json"


def _ler_cache() -> dict[int, dict]:
    arq = _arquivo_cache()
    if not arq.exists():
        return {}
    try:
        return {j["id"]: j for j in json.loads(arq.read_text("utf-8"))}
    except Exception:
        return {}


def _gravar_cache(por_id: dict[int, dict], ordem: list[int]) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    _arquivo_cache().write_text(
        json.dumps([por_id[i] for i in ordem], ensure_ascii=False), "utf-8")


def coletar_temporada(forcar: bool = False, progresso=None,
                      exigir_api: bool = False) -> list[dict]:
    """
    Coleta a temporada inteira. Jogo já disputado e já coletado não é baixado
    de novo (forcar=True baixa tudo outra vez).

    Um jogo só entra como "complete" se a página trouxe o xG. Se falhar, ele
    fica como estava (cache antigo) ou incompleto — nunca com zero falso — e é
    tentado de novo na próxima atualização. Tudo que foi baixado com sucesso é
    gravado a cada SALVAR_A_CADA jogos, então uma queda no meio não perde o
    trabalho já feito.
    """
    antigos = _ler_cache()
    eventos = _eventos_da_temporada()

    if not eventos:
        if exigir_api:
            raise RuntimeError(
                "O FotMob não respondeu com o calendário completo. Os dados locais "
                "foram preservados, mas não foi possível confirmar uma atualização."
            )
        return list(antigos.values())

    ordem = [e["id"] for e in eventos]
    por_id = {}
    pendentes = []
    for e in eventos:
        velho = antigos.get(e["id"])
        if velho and velho["status"] == "complete" and not forcar and "home_xg_jogada" in velho:
            por_id[e["id"]] = velho
        elif e["terminado"]:
            por_id[e["id"]] = velho or _jogo_incompleto(e)
            pendentes.append(e)
        else:
            por_id[e["id"]] = _jogo_incompleto(e)

    falhas, baixados = [], 0
    for e in pendentes:
        det = _detalhes(e)
        if det is None:
            falhas.append(e)
        else:
            por_id[e["id"]] = _monta_jogo(e, *det)
            baixados += 1
            if baixados % SALVAR_A_CADA == 0:
                _gravar_cache(por_id, ordem)
        if progresso and pendentes:
            progresso((baixados + len(falhas)) / len(pendentes),
                      f"Baixando jogo {baixados + len(falhas)} de {len(pendentes)}...")
        time.sleep(PAUSA_ENTRE_JOGOS)

    # grava também quando só mudou o calendário (ex.: jogo adiado/cancelado)
    if baixados or not antigos or [por_id[i] for i in ordem] != list(antigos.values()):
        _gravar_cache(por_id, ordem)

    if falhas and exigir_api:
        raise RuntimeError(
            f"{len(falhas)} jogo(s) não puderam ser baixados do FotMob "
            f"({baixados} foram atualizados e salvos; último erro: {ULTIMO_ERRO or 'página inesperada'}). "
            f"Tente de novo em alguns minutos."
        )
    return [por_id[i] for i in ordem]


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_all_matches(_v: int = 1) -> list[dict]:
    """Interface que a plataforma consome (mesmo contrato do módulo antigo)."""
    return coletar_temporada()


def atualizar_temporada() -> list[dict]:
    """Atualização explícita, sem mascarar falha de rede como sucesso."""
    jogos = coletar_temporada(forcar=False, exigir_api=True)
    fetch_all_matches.clear()
    return jogos
