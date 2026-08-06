from __future__ import annotations

from modeling.dataset_builder import construir_dataset, construir_eventos


def test_partida_remarcada_nao_vaza_para_rodada_anterior_na_vida_real(jogos_com_remarcacao):
    """
    Regressão do achado da auditoria de 2026-08-06: rodada 3 rotulada mas
    jogada no dia 200 (bem depois das rodadas 4 e 5, que aconteceram nos
    dias 22 e 29). Cortar por game_week incluiria essa partida no histórico
    da rodada 4 (3 < 4); cortar por date_unix não.
    """
    eventos = construir_eventos(jogos_com_remarcacao)["TimeA"]
    # eventos anteriores à partida da "rodada 4" (dia 22) pela DATA real
    alvo_rodada4 = next(e for e in eventos if e.partida_id == 4)
    anteriores = [e for e in eventos if e.date_unix < alvo_rodada4.date_unix]
    ids_anteriores = {e.partida_id for e in anteriores}

    assert 3 not in ids_anteriores, (
        "vazamento: a partida remarcada (rotulada rodada 3, jogada no dia 200) "
        "entrou no histórico da rodada 4 (jogada no dia 22)"
    )
    assert ids_anteriores == {1, 2}


def test_dataset_nunca_usa_a_propria_partida_como_historico(jogos_com_remarcacao):
    df = construir_dataset(jogos_com_remarcacao, temporada="teste")
    linha_alvo = df[(df["partida_id"] == 4) & (df["time"] == "TimeA")].iloc[0]
    # amostra_geral não pode contar a própria partida 4
    eventos = construir_eventos(jogos_com_remarcacao)["TimeA"]
    total_antes_por_data = sum(
        1 for e in eventos
        if e.date_unix < next(x.date_unix for x in eventos if x.partida_id == 4)
    )
    assert linha_alvo["amostra_geral"] == total_antes_por_data


def test_dataset_nao_embaralha_e_respeita_ordem_por_data(jogos_reais):
    df = construir_dataset(jogos_reais, temporada="2026")
    assert df["date_unix"].is_monotonic_increasing or (
        df.sort_values(["date_unix", "time"])["date_unix"].tolist() == df["date_unix"].tolist()
    )


def test_features_futuras_nao_dependem_de_resultado_proprio(jogos_com_remarcacao):
    """features_confronto_futuro nunca lê gols da própria partida-alvo (ela nem tem resultado ainda)."""
    from modeling.dataset_builder import construir_eventos, features_confronto_futuro

    por_time = construir_eventos(jogos_com_remarcacao)
    todos = [e for lst in por_time.values() for e in lst]
    linhas = features_confronto_futuro("TimeA", "TimeB", 99, 1_700_000_000 + 999 * 86400, 9999, por_time, todos)
    assert "gols_marcados" not in linhas["mandante"] or linhas["mandante"].get("gols_marcados") is None
