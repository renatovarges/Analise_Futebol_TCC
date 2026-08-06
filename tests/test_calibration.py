from __future__ import annotations

import numpy as np

from modeling.calibration import ajustar_platt, aplicar_platt


def test_platt_e_monotonico():
    """Calibração Platt não pode inverter a ordem das probabilidades brutas."""
    rng = np.random.default_rng(0)
    prob_bruta = np.clip(rng.normal(0.4, 0.15, 300), 0.01, 0.99)
    y = (rng.random(300) < prob_bruta).astype(int)

    modelo = ajustar_platt(y, prob_bruta)
    ordenado = np.sort(prob_bruta)
    calibrado = aplicar_platt(modelo, ordenado)
    assert np.all(np.diff(calibrado) >= -1e-9)   # não-decrescente


def test_platt_ajustado_so_com_treino_nao_usa_teste():
    """Contrato: quem chama ajustar_platt só pode passar y/prob do CONJUNTO DE TREINO."""
    import inspect
    assinatura = inspect.signature(ajustar_platt)
    nomes = list(assinatura.parameters)
    assert nomes == ["y_treino", "prob_bruta_treino"]   # nome do parâmetro documenta o contrato


def test_platt_saida_sempre_entre_0_e_1():
    rng = np.random.default_rng(1)
    prob_bruta = np.clip(rng.normal(0.3, 0.2, 200), 0.001, 0.999)
    y = (rng.random(200) < 0.3).astype(int)
    modelo = ajustar_platt(y, prob_bruta)
    saida = aplicar_platt(modelo, prob_bruta)
    assert (saida >= 0).all() and (saida <= 1).all()
