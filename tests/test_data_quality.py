from __future__ import annotations

from modeling.data_quality import (
    cobertura_por_time, detectar_duplicatas, detectar_remarcadas,
    relatorio_qualidade, validar_partida,
)


def test_zero_ids_duplicados_nos_dados_reais(jogos_reais):
    dup = detectar_duplicatas(jogos_reais)
    assert dup.ids_duplicados == []


def test_detecta_id_duplicado_sintetico(jogo_factory):
    jogos = [
        jogo_factory(1, 1, 1_700_000_000, "A", "B"),
        jogo_factory(1, 1, 1_700_000_000, "A", "B"),   # mesmo id, de propósito
    ]
    dup = detectar_duplicatas(jogos)
    assert 1 in dup.ids_duplicados


def test_partida_incompleta_e_valida_por_definicao(jogo_factory):
    j = jogo_factory(9, 9, 1_700_000_000, "A", "B", status="incomplete")
    v = validar_partida(j)
    assert v.valido is True
    assert v.campos_ausentes_criticos == []   # não se cobra estatística de jogo que não aconteceu


def test_partida_completa_sem_grande_chance_fica_so_com_ausencia_parcial(jogo_factory):
    j = jogo_factory(9, 9, 1_700_000_000, "A", "B", home_big_chances=None, away_big_chances=None)
    v = validar_partida(j)
    assert v.valido is True
    assert "home_big_chances" in v.campos_ausentes_parciais
    assert v.campos_ausentes_criticos == []   # grande chance é PARCIAL, não derruba a partida


def test_ausencia_nao_vira_zero(jogo_factory):
    """Contrato central da seção 2.1: None fica None até o pipeline de shrinkage decidir o que fazer."""
    j = jogo_factory(9, 9, 1_700_000_000, "A", "B", home_big_chances=None)
    assert j["home_big_chances"] is None
    assert j["home_big_chances"] != 0


def test_detecta_remarcada_sintetica(jogos_com_remarcacao):
    remarcadas = detectar_remarcadas(jogos_com_remarcacao, limiar_dias=10)
    ids = {r.partida_id for r in remarcadas}
    assert 3 in ids   # a partida jogada no dia 200, rotulada rodada 3


def test_remarcadas_reais_batem_com_a_auditoria(jogos_reais):
    """Regressão: a auditoria de 2026-08-06 achou exatamente 4 partidas remarcadas nesta base."""
    remarcadas = detectar_remarcadas(jogos_reais)
    assert len(remarcadas) == 4
    ids = {r.partida_id for r in remarcadas}
    assert 16390771 in ids   # Bahia x Chapecoense, rodada 4 jogada em julho


def test_cobertura_por_time_reflete_amostra_real(jogos_reais):
    cobertura = cobertura_por_time(jogos_reais)
    assert len(cobertura) == 20
    for c in cobertura.values():
        assert c.partidas_completas == c.partidas_casa + c.partidas_fora
        assert 0.0 <= c.pct_campos_criticos_completos <= 1.0


def test_relatorio_qualidade_consolida_tudo(jogos_reais):
    rel = relatorio_qualidade(jogos_reais)
    assert rel["total_partidas"] == 384
    assert rel["partidas_completas"] == 205
    assert rel["partidas_invalidas_schema"] == 0
    assert rel["times_cobertura_alta"] == 20
