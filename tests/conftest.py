from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import pytest

CACHE_ATUAL = BASE_DIR / ".cache" / "sofascore_325_87678.json"


@pytest.fixture(scope="session")
def jogos_reais() -> list[dict]:
    with CACHE_ATUAL.open(encoding="utf-8") as f:
        return json.load(f)


def _jogo(
    id_, game_week, date_unix, home, away,
    status="complete", home_goals=1, away_goals=0,
    home_xg=1.0, away_xg=0.8, home_sot=4, away_sot=3,
    home_big_chances=2.0, away_big_chances=1.0,
    home_shots=10.0, away_shots=8.0, home_shots_box=6.0, away_shots_box=5.0,
    home_touches_box=15.0, away_touches_box=12.0,
    home_xg_jogada=0.7, home_xg_bola_parada=0.2, home_xg_contra_ataque=0.1,
    away_xg_jogada=0.6, away_xg_bola_parada=0.15, away_xg_contra_ataque=0.05,
) -> dict:
    base = {
        "id": id_, "game_week": game_week, "status": status, "date_unix": date_unix,
        "home_name": home, "away_name": away,
        "home_goals": home_goals if status == "complete" else None,
        "away_goals": away_goals if status == "complete" else None,
    }
    if status != "complete":
        for c in ("home_xg", "away_xg", "home_sot", "away_sot"):
            base[c] = None
        return base
    base.update({
        "home_xg": home_xg, "away_xg": away_xg, "home_sot": home_sot, "away_sot": away_sot,
        "home_big_chances": home_big_chances, "away_big_chances": away_big_chances,
        "home_shots": home_shots, "away_shots": away_shots,
        "home_shots_box": home_shots_box, "away_shots_box": away_shots_box,
        "home_touches_box": home_touches_box, "away_touches_box": away_touches_box,
        "home_xg_jogada": home_xg_jogada, "home_xg_bola_parada": home_xg_bola_parada,
        "home_xg_contra_ataque": home_xg_contra_ataque, "home_pen_goals": 0,
        "away_xg_jogada": away_xg_jogada, "away_xg_bola_parada": away_xg_bola_parada,
        "away_xg_contra_ataque": away_xg_contra_ataque, "away_pen_goals": 0,
    })
    return base


@pytest.fixture
def jogo_factory():
    return _jogo


@pytest.fixture
def temporada_sintetica(jogo_factory):
    """
    8 rodadas de 2 times fixos (A manda sempre, B visita sempre — simplifica
    a asserção de mando) + um time recém-promovido (C) que só entra na
    rodada 6 com 1 jogo só. Datas em ordem crescente e coerentes com
    game_week (sem remarcação aqui — testes de remarcação usam fixture própria).
    """
    dia = 86400
    t0 = 1_700_000_000
    jogos = []
    for r in range(1, 8):
        jogos.append(jogo_factory(1000 + r, r, t0 + r * 7 * dia, "TimeA", "TimeB",
                                  home_goals=2, away_goals=1, home_xg=1.5, away_xg=0.9))
    # time recem-promovido: só 1 jogo, na rodada 6
    jogos.append(jogo_factory(2000, 6, t0 + 6 * 7 * dia + dia, "TimeC", "TimeB",
                              home_goals=0, away_goals=3, home_xg=0.4, away_xg=2.1))
    return jogos


@pytest.fixture
def jogos_com_remarcacao(jogo_factory):
    """
    Rodada 3 rotulada, mas jogada MUITO depois (dia 200) — enquanto rodadas
    4 a 8 acontecem nas datas normais. Testa que o corte por data_unix (não
    por game_week) impede vazamento.

    Inclui um segundo confronto (TimeX x TimeY) na rodada 3 na data NORMAL,
    só para dar a detectar_remarcadas() uma mediana de rodada 3 que reflita
    a data esperada — com um confronto só, a mediana seria o próprio outlier
    e ele nunca se destacaria dos "colegas" da mesma rodada.
    """
    dia = 86400
    t0 = 1_700_000_000
    jogos = [
        jogo_factory(1, 1, t0 + 1 * dia, "TimeA", "TimeB", home_goals=1, away_goals=0),
        jogo_factory(2, 2, t0 + 8 * dia, "TimeA", "TimeB", home_goals=2, away_goals=1),
        # rodada 3: remarcada, jogada só no dia 200 (bem depois das rodadas 4-8)
        jogo_factory(3, 3, t0 + 200 * dia, "TimeA", "TimeB", home_goals=3, away_goals=0),
        # colegas de rodada 3 na data normal, para a mediana ficar em ~15 dias
        jogo_factory(30, 3, t0 + 15 * dia, "TimeX", "TimeY", home_goals=1, away_goals=1),
        jogo_factory(31, 3, t0 + 15 * dia, "TimeM", "TimeN", home_goals=0, away_goals=2),
        jogo_factory(4, 4, t0 + 22 * dia, "TimeA", "TimeB", home_goals=0, away_goals=0),
        jogo_factory(5, 5, t0 + 29 * dia, "TimeA", "TimeB", home_goals=1, away_goals=1),
    ]
    return jogos
