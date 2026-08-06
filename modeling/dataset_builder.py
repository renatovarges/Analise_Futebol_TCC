"""
modeling/dataset_builder.py — dataset longitudinal equipe-partida (seção 3).

Uma linha por equipe por partida. Toda variável de uma linha é calculada
SOMENTE com partidas anteriores à partida-alvo — e "anterior" aqui significa
date_unix estritamente menor, nunca game_week menor.

Por quê data e não rodada: a auditoria (2026-08-06) achou 4 partidas cuja
data real não bate com a rodada rotulada (reagendamentos — ver
modeling/data_quality.py:detectar_remarcadas). Cortar por game_week deixaria
uma dessas partidas (Bahia x Chapecoense, rotulada rodada 4 mas jogada 142
dias depois da mediana da rodada 4) contaminar o histórico de rodadas
intermediárias com um resultado que, na vida real, ainda não tinha
acontecido. Cortar por date_unix elimina esse vazamento por construção,
não importa o que o rótulo de rodada diga.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean

import pandas as pd

from modeling.shrinkage import K_PROVISORIO, encolher_em_cadeia

JANELAS = (3, 5, 10)
EWMA_ALPHA = 0.30
AMOSTRA_MINIMA_TEMPORADA = 3   # abaixo disso: "recém-promovido ou pouco histórico"

# Campos brutos extraídos por lado. Cada tupla é
# (nome_no_evento, campo_home_no_sofascore, campo_away_no_sofascore).
_CAMPOS_LADO = [
    ("gols", "home_goals", "away_goals"),
    ("gols_sp", None, None),   # calculado (gols - pen_goals), ver _extrair_evento
    ("xg", "home_xg", "away_xg"),
    ("sot", "home_sot", "away_sot"),
    ("chutes", "home_shots", "away_shots"),
    ("chutes_area", "home_shots_box", "away_shots_box"),
    ("toques_area", "home_touches_box", "away_touches_box"),
    ("grandes_chances", "home_big_chances", "away_big_chances"),
    ("xg_jogada", "home_xg_jogada", "away_xg_jogada"),
    ("xg_parada", "home_xg_bola_parada", "away_xg_bola_parada"),
    ("xg_contra", "home_xg_contra_ataque", "away_xg_contra_ataque"),
]


@dataclass
class Evento:
    """Uma partida na perspectiva de UMA equipe — própria produção e cedida."""
    partida_id: int
    time: str
    adversario: str
    mando: str          # "casa" | "fora"
    game_week: int
    date_unix: int
    # produção própria (None = dado ausente na origem, nunca 0 fingido)
    proprio: dict = field(default_factory=dict)
    # o que foi cedido ao adversário nesta partida
    cedido: dict = field(default_factory=dict)
    gols_marcados: int | None = None
    gols_sofridos: int | None = None


def _n(v):
    return None if v is None else v


def _extrair_evento(j: dict, time: str) -> Evento:
    casa = j["home_name"] == time
    p, o = ("home", "away") if casa else ("away", "home")
    adv = j[f"{o}_name"]

    proprio, cedido = {}, {}
    for nome, campo_h, campo_a in _CAMPOS_LADO:
        if nome == "gols_sp":
            gp = j.get(f"{p}_goals")
            pen_p = j.get(f"{p}_pen_goals")
            proprio[nome] = None if gp is None else gp - (pen_p or 0)
            go = j.get(f"{o}_goals")
            pen_o = j.get(f"{o}_pen_goals")
            cedido[nome] = None if go is None else go - (pen_o or 0)
            continue
        campo_prop = campo_h if casa else campo_a
        campo_ced = campo_a if casa else campo_h
        proprio[nome] = _n(j.get(campo_prop))
        cedido[nome] = _n(j.get(campo_ced))

    return Evento(
        partida_id=j["id"], time=time, adversario=adv,
        mando="casa" if casa else "fora",
        game_week=j.get("game_week", 0), date_unix=j.get("date_unix", 0),
        proprio=proprio, cedido=cedido,
        gols_marcados=j.get(f"{p}_goals"), gols_sofridos=j.get(f"{o}_goals"),
    )


def construir_eventos(jogos: list[dict]) -> dict[str, list[Evento]]:
    """Eventos completos, por equipe, ordenados por DATA REAL (não rodada)."""
    completos = [j for j in jogos if j["status"] == "complete"]
    por_time: dict[str, list[Evento]] = {}
    for j in completos:
        for lado in ("home_name", "away_name"):
            time = j[lado]
            por_time.setdefault(time, []).append(_extrair_evento(j, time))
    for time in por_time:
        por_time[time].sort(key=lambda e: e.date_unix)
    return por_time


# ---------------------------------------------------------------------------
# JANELAS MÓVEIS (só sobre eventos ESTRITAMENTE anteriores)
# ---------------------------------------------------------------------------

def _media_janela(anteriores: list[Evento], grupo: str, campo: str, n: int | None) -> tuple[float | None, int]:
    """Média de um campo (proprio/cedido) nos últimos n eventos anteriores. n=None = temporada toda."""
    fonte = anteriores if n is None else anteriores[-n:]
    vals = [getattr(e, grupo)[campo] for e in fonte if getattr(e, grupo)[campo] is not None]
    if not vals:
        return None, 0
    return mean(vals), len(vals)


def _ewma(anteriores: list[Evento], grupo: str, campo: str, alpha: float = EWMA_ALPHA) -> float | None:
    vals = [getattr(e, grupo)[campo] for e in anteriores if getattr(e, grupo)[campo] is not None]
    if not vals:
        return None
    acc = vals[0]
    for v in vals[1:]:
        acc = alpha * v + (1 - alpha) * acc
    return acc


def _liga_media(todos_eventos: list[Evento], grupo: str, campo: str, ate_date_unix: int) -> float:
    """
    Média da liga inteira até (exclusive) uma data — para a base do shrinkage.
    Não é a média histórica fixa: é a média conhecida NAQUELE MOMENTO, para não
    vazar informação do fim da temporada para o início.
    """
    vals = [getattr(e, grupo)[campo] for e in todos_eventos
            if e.date_unix < ate_date_unix and getattr(e, grupo)[campo] is not None]
    return mean(vals) if vals else 0.0


_CAMPOS_FEATURE = [n for n, _, _ in _CAMPOS_LADO]


def _linha_features(
    time: str, alvo: Evento, historico_time: list[Evento],
    todos_eventos_liga: list[Evento], k: float,
) -> dict:
    """Todas as features de UMA equipe para UMA partida-alvo, com corte por data."""
    anteriores = [e for e in historico_time if e.date_unix < alvo.date_unix]
    anteriores_mesmo_mando = [e for e in anteriores if e.mando == alvo.mando]

    linha: dict = {
        "partida_id": alvo.partida_id, "time": time, "adversario": alvo.adversario,
        "mando": alvo.mando, "game_week": alvo.game_week, "date_unix": alvo.date_unix,
        "amostra_geral": len(anteriores), "amostra_mesmo_mando": len(anteriores_mesmo_mando),
        "recem_promovido_ou_pouco_historico": len(anteriores) < AMOSTRA_MINIMA_TEMPORADA,
    }

    if anteriores:
        dt_dias = (alvo.date_unix - anteriores[-1].date_unix) / 86400
        linha["dias_descanso"] = round(dt_dias, 1)
    else:
        linha["dias_descanso"] = None

    for grupo, sufixo in (("proprio", ""), ("cedido", "_ced")):
        for campo in _CAMPOS_FEATURE:
            liga_media = _liga_media(todos_eventos_liga, grupo, campo, alvo.date_unix)
            for n in JANELAS:
                media_geral, n_geral = _media_janela(anteriores, grupo, campo, n)
                media_mando, n_mando = _media_janela(anteriores_mesmo_mando, grupo, campo, n)
                valor = encolher_em_cadeia(
                    media_mando, n_mando, media_geral, n_geral, liga_media, k,
                )
                linha[f"{campo}{sufixo}_j{n}"] = round(valor, 4)
            media_temp, n_temp = _media_janela(anteriores, grupo, campo, None)
            linha[f"{campo}{sufixo}_temporada"] = (
                round(encolher_em_cadeia(None, 0, media_temp, n_temp, liga_media, k), 4)
            )
            ewma = _ewma(anteriores, grupo, campo)
            linha[f"{campo}{sufixo}_ewma"] = (
                round(encolher_em_cadeia(None, 0, ewma, len(anteriores), liga_media, k), 4)
                if ewma is not None else round(liga_media, 4)
            )

    # rótulos (só existem porque a partida já aconteceu — nunca entram como feature)
    linha["alvo_2mais_gols"] = None if alvo.gols_marcados is None else int(alvo.gols_marcados >= 2)
    linha["alvo_sg"] = None if alvo.gols_sofridos is None else int(alvo.gols_sofridos == 0)
    linha["gols_marcados"] = alvo.gols_marcados
    linha["gols_sofridos"] = alvo.gols_sofridos
    return linha


def construir_dataset(jogos: list[dict], k: float = K_PROVISORIO, temporada: str | None = None) -> pd.DataFrame:
    """
    Monta o dataset longitudinal equipe-partida de uma temporada.

    k usa o provisório (modeling/shrinkage.K_PROVISORIO) até o backtest
    (scripts/run_backtest.py) validar o valor final — ver docstring de
    shrinkage.py. Repetir esta chamada com outro k depois de validado.
    """
    por_time = construir_eventos(jogos)
    todos_eventos = [e for lst in por_time.values() for e in lst]

    linhas = []
    for time, historico in por_time.items():
        for alvo in historico:
            linha = _linha_features(time, alvo, historico, todos_eventos, k)
            if temporada is not None:
                linha["temporada"] = temporada
            linhas.append(linha)

    df = pd.DataFrame(linhas)
    if not df.empty:
        df = df.sort_values(["date_unix", "time"]).reset_index(drop=True)
    return df


def forca_adversario(df: pd.DataFrame) -> pd.DataFrame:
    """
    Anexa a cada linha a força do ADVERSÁRIO na mesma partida, lendo as
    features que já foram calculadas (com o mesmo corte por data) para a
    linha do adversário naquela partida. Roda depois de construir_dataset
    porque precisa das duas linhas da partida já prontas.
    """
    idx = df.set_index(["partida_id", "time"])
    campos_adv = [c for c in df.columns if c.endswith(("_j3", "_j5", "_j10", "_temporada", "_ewma"))]

    saida = []
    for _, row in df.iterrows():
        try:
            adv_row = idx.loc[(row["partida_id"], row["adversario"])]
        except KeyError:
            saida.append({f"adv_{c}": None for c in campos_adv})
            continue
        saida.append({f"adv_{c}": adv_row[c] for c in campos_adv})

    adv_df = pd.DataFrame(saida, index=df.index)
    return pd.concat([df, adv_df], axis=1)
