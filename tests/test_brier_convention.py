from __future__ import annotations

import numpy as np

from modeling.validation import brier_score


def _ganho_brier(y_real, prob_baseline, prob_modelo):
    """Mesma fórmula usada em scripts/validar_poisson.py e em toda a documentação."""
    return brier_score(y_real, prob_baseline) - brier_score(y_real, prob_modelo)


def test_ganho_positivo_quando_modelo_e_melhor():
    y = np.array([1, 0, 1, 1, 0])
    baseline_ruim = np.array([0.5, 0.5, 0.5, 0.5, 0.5])   # erro maior
    modelo_bom = np.array([0.9, 0.1, 0.9, 0.9, 0.1])       # erro menor (acerta o padrão)
    assert brier_score(y, modelo_bom) < brier_score(y, baseline_ruim)
    assert _ganho_brier(y, baseline_ruim, modelo_bom) > 0


def test_ganho_negativo_quando_baseline_e_melhor():
    y = np.array([1, 0, 1, 1, 0])
    baseline_boa = np.array([0.9, 0.1, 0.9, 0.9, 0.1])
    modelo_ruim = np.array([0.5, 0.5, 0.5, 0.5, 0.5])
    assert brier_score(y, modelo_ruim) > brier_score(y, baseline_boa)
    assert _ganho_brier(y, baseline_boa, modelo_ruim) < 0


def test_ganho_zero_quando_empate():
    y = np.array([1, 0, 1, 0])
    mesmas_probs = np.array([0.6, 0.4, 0.6, 0.4])
    assert _ganho_brier(y, mesmas_probs, mesmas_probs) == 0.0


def test_artefato_real_usa_a_convencao_ganho_brier_positivo_quando_poisson_e_melhor():
    """
    Regressão do achado de 2026-08-06: o Poisson tem Brier menor que a
    baseline nos dois alvos (0,2219<0,2233 e 0,1981<0,1995) — então
    ganho_brier tem que ser POSITIVO nos artefatos reais, e a chave tem que
    se chamar "ganho_brier" (não "diferenca", que não deixava claro o sinal).
    """
    import json
    from pathlib import Path

    caminho = Path(__file__).resolve().parent.parent / "artifacts" / "validacao_poisson.json"
    with caminho.open(encoding="utf-8") as f:
        dados = json.load(f)

    for alvo in ("alvo_2mais_gols", "alvo_sg"):
        assert "ganho_brier_medio" in dados[alvo]
        assert "diferenca_media_brier" not in dados[alvo]
        assert dados[alvo]["ganho_brier_medio"] > 0, (
            f"{alvo}: Poisson tem Brier menor que a baseline (medido), "
            f"então ganho_brier_medio precisa ser positivo pela convenção do projeto"
        )
        # a convenção documentada no próprio artefato, por alvo
        assert "baseline" in dados[alvo]["convencao"] and "modelo" in dados[alvo]["convencao"]
