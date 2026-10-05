"""Testes da camada de dados do FotMob — offline (amostra real salva em tests/fixtures)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import fotmob_api

FIXTURE = Path(__file__).parent / "fixtures" / "fotmob_flamengo_mirassol.json"


@pytest.fixture(scope="module")
def jogo_real() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _ev(id_, rodada=1, casa="Flamengo", fora="Mirassol", terminado=True,
        cancelado=False, data=1000, gols=(2, 0)):
    return {"id": id_, "round": rodada, "home": casa, "away": fora,
            "terminado": terminado, "cancelado": cancelado, "date_unix": data,
            "gols": gols if terminado else None, "url": f"https://x/{id_}"}


# --- leitura das estatísticas -------------------------------------------------

def test_stats_do_jogo_real(jogo_real):
    s = fotmob_api._stats_do_jogo(jogo_real["content"])
    assert s["xg"] == (1.91, 0.70)
    assert s["sot"] == (4.0, 2.0)
    assert s["grandes_chances"] == (5.0, 2.0)
    assert s["toques_area"] == (23.0, 19.0)
    assert s["chutes_area"] == (12.0, 5.0)
    assert s["xgot"] == (1.89, 0.21)


def test_shotmap_soma_o_xg_do_time(jogo_real):
    id_casa = jogo_real["general"]["homeTeam"]["id"]
    stats = fotmob_api._stats_do_jogo(jogo_real["content"])
    shot = fotmob_api._shotmap_do_jogo(jogo_real["content"], id_casa)
    for lado, idx in (("casa", 0), ("fora", 1)):
        s = shot[lado]
        total = s["xg_jogada"] + s["xg_bola_parada"] + s["xg_contra_ataque"] + s["xg_penalti"]
        assert total == pytest.approx(stats["xg"][idx], abs=0.02)
    assert shot["casa"]["xg_contra_ataque"] > 0      # o chute FastBreak foi lido
    assert shot["casa"]["pen_goals"] == 0


# --- compatibilidade com o formato antigo -------------------------------------

def test_registro_tem_os_mesmos_campos_do_formato_antigo(jogo_real, jogos_reais):
    antigo = next(j for j in jogos_reais if j["status"] == "complete")
    stats = fotmob_api._stats_do_jogo(jogo_real["content"])
    shot = fotmob_api._shotmap_do_jogo(jogo_real["content"], jogo_real["general"]["homeTeam"]["id"])
    novo = fotmob_api._monta_jogo(_ev(1), stats, shot)
    assert set(novo) == set(antigo)


def test_gols_evitados_e_xgot_sofrido_menos_gols_sofridos(jogo_real):
    stats = fotmob_api._stats_do_jogo(jogo_real["content"])
    novo = fotmob_api._monta_jogo(_ev(1, gols=(2, 0)), stats, fotmob_api._shotmap_do_jogo(
        jogo_real["content"], jogo_real["general"]["homeTeam"]["id"]))
    assert novo["home_goals_prevented"] == pytest.approx(0.21 - 0)      # goleiro da casa
    assert novo["away_goals_prevented"] == pytest.approx(1.89 - 2)      # goleiro visitante


def test_nomes_dos_times_viram_os_canonicos():
    for bruto, canonico in (("Atlético-MG", "Atletico MG"), ("RB Bragantino", "Bragantino"),
                            ("Athletico Paranaense", "Athletico PR"), ("São Paulo", "Sao Paulo"),
                            ("Vasco da Gama", "Vasco"), ("Grêmio", "Gremio")):
        assert fotmob_api.normalize_team_name(bruto) == canonico


# --- calendário ---------------------------------------------------------------

def test_remarcacao_prefere_o_jogo_disputado_ao_cancelado():
    cancelado = _ev(1, terminado=False, cancelado=True, data=100)
    disputado = _ev(2, terminado=True, data=200)
    assert [e["id"] for e in fotmob_api._deduplicar_calendario([cancelado, disputado])] == [2]
    assert [e["id"] for e in fotmob_api._deduplicar_calendario([disputado, cancelado])] == [2]


def test_calendario_incompleto_nao_e_aceito(monkeypatch):
    brutos = [{"id": i, "round": str(i // 10 + 1), "roundName": i // 10 + 1,
               "home": {"name": f"C{i}"}, "away": {"name": f"F{i}"},
               "status": {"finished": False}, "pageUrl": f"/m/{i}"} for i in range(379)]
    html = ('<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps({"props": {"pageProps": {"fixtures": {"allMatches": brutos}}}})
            + "</script>")
    monkeypatch.setattr(fotmob_api, "_baixar", lambda url, tentativas=3: html)
    assert fotmob_api._eventos_da_temporada() == []


# --- coleta e cache -----------------------------------------------------------

@pytest.fixture
def cache_temporario(tmp_path, monkeypatch):
    monkeypatch.setattr(fotmob_api, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(fotmob_api, "PAUSA_ENTRE_JOGOS", 0)
    return tmp_path / f"fotmob_{fotmob_api.LIGA_ID}_{fotmob_api.TEMPORADA}.json"


def test_falha_em_um_jogo_nao_vira_zero_falso_e_nao_perde_os_outros(
        cache_temporario, jogo_real, monkeypatch):
    eventos = [_ev(1, casa="Flamengo", fora="Mirassol"), _ev(2, casa="Bahia", fora="Santos")]
    ok = (fotmob_api._stats_do_jogo(jogo_real["content"]),
          fotmob_api._shotmap_do_jogo(jogo_real["content"], jogo_real["general"]["homeTeam"]["id"]))
    monkeypatch.setattr(fotmob_api, "_eventos_da_temporada", lambda: eventos)
    monkeypatch.setattr(fotmob_api, "_detalhes", lambda ev: ok if ev["id"] == 1 else None)

    with pytest.raises(RuntimeError, match="1 jogo"):
        fotmob_api.coletar_temporada(exigir_api=True)

    salvo = {j["id"]: j for j in json.loads(cache_temporario.read_text("utf-8"))}
    assert salvo[1]["status"] == "complete" and salvo[1]["home_xg"] == 1.91
    assert salvo[2]["status"] == "incomplete" and salvo[2]["home_xg"] is None


def test_calendario_fora_do_ar_preserva_cache_existente(cache_temporario, monkeypatch):
    cache_temporario.write_text(json.dumps([{"id": 7, "status": "complete"}]), "utf-8")
    monkeypatch.setattr(fotmob_api, "_eventos_da_temporada", lambda: [])

    with pytest.raises(RuntimeError, match="preservados"):
        fotmob_api.coletar_temporada(exigir_api=True)
    assert fotmob_api.coletar_temporada() == [{"id": 7, "status": "complete"}]
    assert json.loads(cache_temporario.read_text("utf-8")) == [{"id": 7, "status": "complete"}]


def test_jogo_ja_coletado_nao_e_baixado_de_novo(cache_temporario, jogo_real, monkeypatch):
    ev = _ev(1)
    stats = fotmob_api._stats_do_jogo(jogo_real["content"])
    shot = fotmob_api._shotmap_do_jogo(jogo_real["content"], jogo_real["general"]["homeTeam"]["id"])
    cache_temporario.write_text(json.dumps([fotmob_api._monta_jogo(ev, stats, shot)]), "utf-8")

    chamadas = []
    monkeypatch.setattr(fotmob_api, "_eventos_da_temporada", lambda: [ev])
    monkeypatch.setattr(fotmob_api, "_detalhes", lambda e: chamadas.append(e["id"]))

    jogos = fotmob_api.coletar_temporada()
    assert chamadas == [] and jogos[0]["home_xg"] == 1.91


# --- página do jogo certo -----------------------------------------------------

def _pagina_html(jogo_real: dict) -> str:
    corpo = {"props": {"pageProps": {"general": jogo_real["general"], "content": jogo_real["content"]}}}
    return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(corpo) + "</script>"


def test_url_do_jogo_usa_o_id_e_nao_a_pagina_do_confronto():
    ev = fotmob_api._evento_do_calendario({
        "id": "5103412", "round": "5", "roundName": 5,
        "home": {"name": "Bahia"}, "away": {"name": "Vitória"},
        "status": {"finished": True, "scoreStr": "2 - 1", "utcTime": "2026-03-11T22:00:00Z"},
        "pageUrl": "/matches/vitoria-vs-bahia/20jpec#5103412",    # página do PAR (ida e volta)
    })
    assert ev["url"] == "https://www.fotmob.com/match/5103412"


def test_pagina_de_outro_jogo_e_rejeitada(jogo_real, monkeypatch):
    """Regressão: o endereço do confronto devolvia o jogo da volta no lugar da ida."""
    monkeypatch.setattr(fotmob_api, "_baixar", lambda url, tentativas=3: _pagina_html(jogo_real))
    assert fotmob_api._detalhes(_ev(5103394)) is not None      # a página É deste jogo
    assert fotmob_api._detalhes(_ev(999999)) is None           # a página é de outro jogo
