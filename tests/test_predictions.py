from __future__ import annotations

import math

import pytest

from modeling.prediction import _p_2mais_gols, _p_sg, carregar_metadata, prever_confronto


def test_formula_p_2mais_gols_e_1_menos_p0_menos_p1():
    """P(X>=2) = 1 - P(X=0) - P(X=1), X ~ Poisson(mu). Confere contra a definição direta."""
    for mu in (0.3, 0.8, 1.2, 1.9, 3.0):
        p0 = math.exp(-mu)
        p1 = mu * math.exp(-mu)
        esperado = 1 - p0 - p1
        assert _p_2mais_gols(mu) == pytest.approx(esperado, abs=1e-9)


def test_formula_p_sg_e_p_zero():
    """P(SG) = P(adversário marcar zero) = P(X=0), X ~ Poisson(mu_sofridos)."""
    for mu in (0.3, 0.8, 1.2, 1.9, 3.0):
        assert _p_sg(mu) == pytest.approx(math.exp(-mu), abs=1e-9)


def test_p_2mais_gols_cresce_com_mu():
    valores = [_p_2mais_gols(mu) for mu in (0.2, 0.5, 1.0, 1.5, 2.5)]
    assert valores == sorted(valores)


def test_p_sg_decresce_com_mu():
    valores = [_p_sg(mu) for mu in (0.2, 0.5, 1.0, 1.5, 2.5)]
    assert valores == sorted(valores, reverse=True)


def test_probabilidades_sempre_em_0_1():
    for mu in (0.0, 0.001, 5.0, 50.0, 500.0):
        assert 0.0 <= _p_2mais_gols(mu) <= 1.0
        assert 0.0 <= _p_sg(mu) <= 1.0


def test_metadata_tem_os_dois_modelos_com_coeficientes():
    meta = carregar_metadata()
    for chave in ("modelo_ataque_gols_marcados", "modelo_defesa_gols_sofridos"):
        m = meta[chave]
        assert len(m["coef"]) == len(m["features"])
        assert len(m["scaler_mean"]) == len(m["features"])
        assert len(m["scaler_scale"]) == len(m["features"])
        assert isinstance(m["intercept"], float)


def test_prever_confronto_e_reproduzivel(jogos_reais):
    """Mesma entrada, mesmo resultado — sem aleatoriedade escondida na inferência."""
    futuro = next(j for j in jogos_reais if j["status"] != "complete")
    r1 = prever_confronto(futuro["home_name"], futuro["away_name"], futuro["game_week"],
                          futuro["date_unix"], futuro["id"], jogos_reais)
    r2 = prever_confronto(futuro["home_name"], futuro["away_name"], futuro["game_week"],
                          futuro["date_unix"], futuro["id"], jogos_reais)
    assert r1 == r2


def test_prever_confronto_probabilidades_plausiveis(jogos_reais):
    futuro = next(j for j in jogos_reais if j["status"] != "complete")
    r = prever_confronto(futuro["home_name"], futuro["away_name"], futuro["game_week"],
                         futuro["date_unix"], futuro["id"], jogos_reais)
    for time, d in r.items():
        assert 0.0 <= d["probabilidade_2_mais_gols"] <= 1.0
        assert 0.0 <= d["probabilidade_sg"] <= 1.0
        assert 0.0 <= d["confianca"] <= 1.0
        assert d["gols_esperados"] >= 0
        assert d["gols_esperados_sofridos"] >= 0


def test_confianca_baixa_para_time_com_pouco_historico(jogos_com_remarcacao):
    from modeling.prediction import _confianca
    assert _confianca({"amostra_geral": 0, "amostra_mesmo_mando": 0}) < 0.3
    assert _confianca({"amostra_geral": 20, "amostra_mesmo_mando": 10}) > 0.9
