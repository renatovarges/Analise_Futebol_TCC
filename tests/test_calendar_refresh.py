from __future__ import annotations

from data_processor import resumo_calendario
import sofascore_api
from sofascore_api import _deduplicar_eventos


def _evento(id_, rodada, casa, fora, status, data):
    return {
        "id": id_,
        "roundInfo": {"round": rodada},
        "homeTeam": {"name": casa},
        "awayTeam": {"name": fora},
        "status": {"type": status},
        "startTimestamp": data,
    }


def test_remarcacao_nao_aumenta_temporada_para_mais_de_380():
    eventos = []
    for rodada in range(1, 39):
        for jogo in range(10):
            eventos.append(_evento(
                rodada * 100 + jogo, rodada, f"Casa {rodada}-{jogo}",
                f"Fora {rodada}-{jogo}", "notstarted", rodada * 1000 + jogo,
            ))
    antigo = _evento(99901, 4, "Bahia", "Chapecoense", "notstarted", 100)
    substituto = _evento(99902, 4, "Bahia", "Chapecoense", "finished", 200)
    eventos.extend((antigo, substituto))

    limpos = _deduplicar_eventos(eventos)

    # Os dez confrontos sintéticos + Bahia x Chapecoense são distintos; apenas
    # o ID antigo da remarcação desaparece.
    assert len(limpos) == 381
    bahia = [e for e in limpos if e["homeTeam"]["name"] == "Bahia"]
    assert [e["id"] for e in bahia] == [99902]


def test_proxima_rodada_ignora_partida_antiga_adiada(jogo_factory):
    jogos = []
    for rodada in (21, 22):
        for n in range(10):
            jogos.append(jogo_factory(
                rodada * 100 + n, rodada, 1000 + rodada * 100 + n,
                f"Casa{rodada}-{n}", f"Fora{rodada}-{n}", status="complete",
            ))
    jogos.append(jogo_factory(201, 2, 500, "A", "B", status="incomplete"))
    jogos.append(jogo_factory(2301, 23, 5000, "C", "D", status="incomplete"))

    resumo = resumo_calendario(jogos, agora_unix=4000)

    assert resumo["ultima_rod"] == 22
    assert resumo["proxima_rod"] == 23


def test_calendario_consulta_as_38_rotas_por_rodada(monkeypatch):
    chamadas = []

    def fake_get(url):
        rodada = int(url.rsplit("/", 1)[-1])
        chamadas.append(rodada)
        return {"events": [
            _evento(rodada * 100 + n, rodada, f"C{n}", f"F{n}", "notstarted", rodada)
            for n in range(10)
        ]}

    monkeypatch.setattr(sofascore_api, "_get", fake_get)
    eventos = sofascore_api._eventos_da_temporada()

    assert chamadas == list(range(1, 39))
    assert len(eventos) == 380


def test_resposta_parcial_da_api_nao_substitui_cache_integro(monkeypatch):
    def fake_get(url):
        rodada = int(url.rsplit("/", 1)[-1])
        return {"events": [_evento(rodada, rodada, "A", "B", "notstarted", rodada)]} if rodada < 38 else None

    monkeypatch.setattr(sofascore_api, "_get", fake_get)
    assert sofascore_api._eventos_da_temporada() == []
