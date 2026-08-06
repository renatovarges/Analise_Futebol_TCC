"""
modeling/data_quality.py — validação e qualidade dos dados brutos do SofaScore.

Este módulo NUNCA transforma ausência em zero. Ele classifica cada partida e
cada campo, para que dataset_builder.py decida o que fazer com cada caso —
descartar, marcar como indisponível, ou (só dentro do pipeline estatístico)
imputar com método declarado.

Não depende de pandas: opera sobre a lista de dicts que sofascore_api.py já
devolve, para poder ser usado tanto no dataset builder quanto em testes leves.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import median

# ---------------------------------------------------------------------------
# ESQUEMA
# ---------------------------------------------------------------------------

# Campos que uma partida PRECISA ter, sempre (independente de status).
CAMPOS_OBRIGATORIOS = (
    "id", "game_week", "status", "date_unix", "home_name", "away_name",
)

# Campos que uma partida COMPLETA precisa ter para entrar no dataset preditivo.
# Ausência aqui não vira zero — a partida fica marcada como indisponível
# para as métricas que dependem desses campos, mas outras métricas dela
# continuam utilizáveis.
CAMPOS_CRITICOS_COMPLETA = (
    "home_goals", "away_goals",
    "home_xg", "away_xg",
    "home_shots", "away_shots",
    "home_sot", "away_sot",
    "home_shots_box", "away_shots_box",
    "home_touches_box", "away_touches_box",
)

# Campos de cobertura mais baixa e conhecida (~96%, ver sofascore_api.py) —
# entram na dimensão de cobertura, mas não derrubam a partida inteira.
CAMPOS_CRITICOS_PARCIAIS = (
    "home_big_chances", "away_big_chances",
)


@dataclass
class ValidacaoPartida:
    valido: bool
    partida_id: int
    motivo: str | None = None
    campos_ausentes_obrigatorios: list[str] = field(default_factory=list)
    campos_ausentes_criticos: list[str] = field(default_factory=list)
    campos_ausentes_parciais: list[str] = field(default_factory=list)


def validar_partida(j: dict) -> ValidacaoPartida:
    """
    Valida uma partida contra o esquema mínimo.

    Uma partida "incomplete" (ainda não jogada) é válida por definição — ela
    simplesmente não tem estatísticas ainda. Só marcamos inválida uma partida
    completa com buracos no esquema básico (id, nomes, data), porque isso
    indica falha de coleta, não ausência normal de dado.
    """
    pid = j.get("id", -1)
    faltando_obrig = [c for c in CAMPOS_OBRIGATORIOS if j.get(c) in (None, "")]
    if faltando_obrig:
        return ValidacaoPartida(
            valido=False, partida_id=pid, motivo="esquema básico incompleto",
            campos_ausentes_obrigatorios=faltando_obrig,
        )

    if j.get("status") != "complete":
        return ValidacaoPartida(valido=True, partida_id=pid)

    faltando_crit = [c for c in CAMPOS_CRITICOS_COMPLETA if j.get(c) is None]
    faltando_parc = [c for c in CAMPOS_CRITICOS_PARCIAIS if j.get(c) is None]
    return ValidacaoPartida(
        valido=True, partida_id=pid,
        campos_ausentes_criticos=faltando_crit,
        campos_ausentes_parciais=faltando_parc,
    )


# ---------------------------------------------------------------------------
# DUPLICIDADES
# ---------------------------------------------------------------------------

@dataclass
class RelatorioDuplicatas:
    ids_duplicados: list[int]
    confrontos_duplicados: list[tuple]   # (home, away, dia) com >1 id distinto


def detectar_duplicatas(jogos: list[dict]) -> RelatorioDuplicatas:
    """
    Duas checagens independentes:
      1. mesmo id do SofaScore aparecendo mais de uma vez na lista (bug de
         coleta/merge de cache);
      2. mesmo confronto (mandante, visitante, mesmo dia) com ids diferentes
         — sintoma de reagendamento salvo duas vezes com identidades distintas.
    """
    por_id = defaultdict(list)
    for j in jogos:
        por_id[j["id"]].append(j)
    ids_dup = [i for i, lst in por_id.items() if len(lst) > 1]

    por_confronto = defaultdict(set)
    for j in jogos:
        dia = j["date_unix"] // 86400
        chave = (j["home_name"], j["away_name"], dia)
        por_confronto[chave].add(j["id"])
    confrontos_dup = [k for k, ids in por_confronto.items() if len(ids) > 1]

    return RelatorioDuplicatas(ids_duplicados=ids_dup, confrontos_duplicados=confrontos_dup)


# ---------------------------------------------------------------------------
# PARTIDAS REMARCADAS / FORA DE SEQUÊNCIA
# ---------------------------------------------------------------------------

@dataclass
class PartidaRemarcada:
    partida_id: int
    game_week: int
    home_name: str
    away_name: str
    desvio_dias: float


def detectar_remarcadas(jogos: list[dict], limiar_dias: float = 10.0) -> list[PartidaRemarcada]:
    """
    Sinaliza partidas cuja data real está muito longe da data mediana da sua
    própria rodada (game_week) — sintoma de reagendamento (adiamento por
    clima, luto, mando judicial, etc.).

    Isto é só DIAGNÓSTICO. A prevenção de vazamento temporal no dataset NÃO
    depende de game_week: dataset_builder.py corta o histórico pela data real
    (date_unix) de cada partida, não pelo rótulo da rodada. Rótulo de rodada
    errado não causa vazamento ali; aqui ele só é reportado para o usuário
    entender por que a cobertura de uma rodada específica parece baixa.
    """
    completos = [j for j in jogos if j["status"] == "complete"]
    por_rodada = defaultdict(list)
    for j in completos:
        por_rodada[j["game_week"]].append(j["date_unix"])

    medianas = {gw: median(datas) for gw, datas in por_rodada.items()}

    fora = []
    for j in completos:
        med = medianas[j["game_week"]]
        desvio = abs(j["date_unix"] - med) / 86400
        if desvio > limiar_dias:
            fora.append(PartidaRemarcada(
                partida_id=j["id"], game_week=j["game_week"],
                home_name=j["home_name"], away_name=j["away_name"],
                desvio_dias=round(desvio, 1),
            ))
    return fora


# ---------------------------------------------------------------------------
# COBERTURA POR EQUIPE
# ---------------------------------------------------------------------------

@dataclass
class CoberturaTime:
    time: str
    partidas_completas: int
    partidas_casa: int
    partidas_fora: int
    pct_campos_criticos_completos: float
    pct_grandes_chances_disponivel: float
    nivel: str    # "alta" | "media" | "baixa"


def _nivel_cobertura(n_partidas: int, pct_campos: float) -> str:
    if n_partidas >= 10 and pct_campos >= 0.95:
        return "alta"
    if n_partidas >= 5 and pct_campos >= 0.85:
        return "media"
    return "baixa"


def cobertura_por_time(jogos: list[dict]) -> dict[str, CoberturaTime]:
    """Cobertura de dados por equipe — usada para calibrar a confiança exibida."""
    completos = [j for j in jogos if j["status"] == "complete"]
    times = sorted({j["home_name"] for j in completos} | {j["away_name"] for j in completos})

    saida = {}
    for time in times:
        proprios = [j for j in completos if j["home_name"] == time or j["away_name"] == time]
        casa = sum(1 for j in proprios if j["home_name"] == time)
        fora = len(proprios) - casa

        total_campos = total_ok = total_gc = total_gc_ok = 0
        for j in proprios:
            for c in CAMPOS_CRITICOS_COMPLETA:
                total_campos += 1
                if j.get(c) is not None:
                    total_ok += 1
            for c in CAMPOS_CRITICOS_PARCIAIS:
                total_gc += 1
                if j.get(c) is not None:
                    total_gc_ok += 1

        pct_campos = (total_ok / total_campos) if total_campos else 0.0
        pct_gc = (total_gc_ok / total_gc) if total_gc else 0.0
        saida[time] = CoberturaTime(
            time=time, partidas_completas=len(proprios),
            partidas_casa=casa, partidas_fora=fora,
            pct_campos_criticos_completos=round(pct_campos, 3),
            pct_grandes_chances_disponivel=round(pct_gc, 3),
            nivel=_nivel_cobertura(len(proprios), pct_campos),
        )
    return saida


# ---------------------------------------------------------------------------
# RELATÓRIO CONSOLIDADO
# ---------------------------------------------------------------------------

def relatorio_qualidade(jogos: list[dict]) -> dict:
    """Um relatório único, pensado para logging/artifacts, não para o dataset em si."""
    completos = [j for j in jogos if j["status"] == "complete"]
    validacoes = [validar_partida(j) for j in jogos]
    invalidas = [v for v in validacoes if not v.valido]
    dup = detectar_duplicatas(jogos)
    remarcadas = detectar_remarcadas(jogos)
    cobertura = cobertura_por_time(jogos)

    niveis = defaultdict(int)
    for c in cobertura.values():
        niveis[c.nivel] += 1

    return {
        "total_partidas": len(jogos),
        "partidas_completas": len(completos),
        "partidas_invalidas_schema": len(invalidas),
        "ids_duplicados": dup.ids_duplicados,
        "confrontos_duplicados": dup.confrontos_duplicados,
        "partidas_remarcadas": [
            {"id": r.partida_id, "rodada": r.game_week, "confronto": f"{r.home_name} x {r.away_name}",
             "desvio_dias": r.desvio_dias}
            for r in remarcadas
        ],
        "times_cobertura_alta": niveis["alta"],
        "times_cobertura_media": niveis["media"],
        "times_cobertura_baixa": niveis["baixa"],
        "cobertura_por_time": {t: vars(c) for t, c in cobertura.items()},
    }
