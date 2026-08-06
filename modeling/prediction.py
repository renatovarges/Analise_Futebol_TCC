"""
modeling/prediction.py — inferência em produção (seção 17).

Só numpy — sem scikit-learn/scipy no runtime do Streamlit Cloud (ver
requirements-dev.txt). Os coeficientes vêm de artifacts/model_metadata.json,
gerado por scripts/train_models.py.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

from modeling.dataset_builder import construir_eventos, features_confronto_futuro

BASE_DIR = Path(__file__).resolve().parent.parent
METADATA_PATH = BASE_DIR / "artifacts" / "model_metadata.json"


@lru_cache(maxsize=1)
def carregar_metadata() -> dict:
    if not METADATA_PATH.exists():
        raise FileNotFoundError(
            "artifacts/model_metadata.json não existe. Rode: "
            "python scripts/build_dataset.py && python scripts/train_models.py"
        )
    with METADATA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _mu_poisson(modelo: dict, linha: dict) -> float:
    x = np.array([linha.get(c, 0.0) if c != "mando_casa" else float(linha["mando"] == "casa")
                  for c in modelo["features"]], dtype=float)
    x = np.nan_to_num(x, nan=0.0)
    mean = np.array(modelo["scaler_mean"])
    scale = np.array(modelo["scaler_scale"])
    scale = np.where(scale == 0, 1.0, scale)
    xs = (x - mean) / scale
    log_mu = float(np.dot(xs, modelo["coef"])) + modelo["intercept"]
    return math.exp(max(min(log_mu, 30), -30))   # clip contra overflow


def _contribuicoes(modelo: dict, linha: dict, top_n: int = 4) -> list[dict]:
    """Contribuição local de cada feature para o log(mu) — coef × valor padronizado."""
    mean = np.array(modelo["scaler_mean"])
    scale = np.array(modelo["scaler_scale"])
    scale = np.where(scale == 0, 1.0, scale)
    saida = []
    for i, campo in enumerate(modelo["features"]):
        if campo == "mando_casa":
            continue
        valor = linha.get(campo)
        if valor is None:
            continue
        xs = (valor - mean[i]) / scale[i]
        contrib = modelo["coef"][i] * xs
        saida.append({"metrica": campo, "valor": round(float(valor), 3), "contribuicao": round(float(contrib), 4)})
    saida.sort(key=lambda d: -abs(d["contribuicao"]))
    return saida[:top_n]


def _p_2mais_gols(mu: float) -> float:
    mu = max(mu, 1e-6)
    p0 = math.exp(-mu)
    p1 = mu * math.exp(-mu)
    return max(0.0, min(1.0, 1 - p0 - p1))


def _p_sg(mu_sofridos: float) -> float:
    mu_sofridos = max(mu_sofridos, 1e-6)
    return max(0.0, min(1.0, math.exp(-mu_sofridos)))


def _faixa_expectativa(p: float, faixas: dict) -> str:
    """
    Rótulo derivado da DISTRIBUIÇÃO OBSERVADA das probabilidades do modelo no
    treino (artifacts/model_metadata.json → faixas_probabilidade), não de
    corte arbitrário. p abaixo do p50 histórico = "baixa", até o p75 =
    "moderada", até o p90 = "alta", acima = "muito alta".
    """
    if p < faixas["p50"]:
        return "expectativa baixa"
    if p < faixas["p75"]:
        return "expectativa moderada"
    if p < faixas["p90"]:
        return "expectativa alta"
    return "expectativa muito alta"


def _confianca(linha: dict) -> float:
    """
    Confiança separada da probabilidade (seção 16): função de cobertura de
    amostra, não do quão extrema a probabilidade prevista é. Uma equipe com
    p alta e 2 jogos de amostra tem confiança baixa; o índice de confiança
    reflete isso mesmo quando a probabilidade prevista é alta.
    """
    n = linha.get("amostra_geral", 0)
    n_mando = linha.get("amostra_mesmo_mando", 0)
    base = min(1.0, math.sqrt(n / 10))
    bonus_mando = min(0.15, n_mando * 0.03)
    return round(min(1.0, base + bonus_mando), 3)


def prever_confronto(mandante: str, visitante: str, rodada_num: int, date_unix: int,
                      partida_id: int, jogos: list[dict]) -> dict:
    """
    Previsão de produção para um confronto: P(2+ gols) e P(SG) calibradas
    pelo modelo, para os dois lados, com evidências rastreáveis.
    """
    meta = carregar_metadata()
    por_time = construir_eventos(jogos)
    todos_eventos = [e for lst in por_time.values() for e in lst]

    linhas = features_confronto_futuro(
        mandante, visitante, rodada_num, date_unix, partida_id, por_time, todos_eventos,
    )

    saida = {}
    for papel, time, adversario in (("mandante", mandante, visitante), ("visitante", visitante, mandante)):
        linha = linhas[papel]
        mu_ataque = _mu_poisson(meta["modelo_ataque_gols_marcados"], linha)
        mu_defesa = _mu_poisson(meta["modelo_defesa_gols_sofridos"], linha)

        p_ataque = _p_2mais_gols(mu_ataque)
        p_defesa = _p_sg(mu_defesa)
        saida[time] = {
            "equipe": time, "adversario": adversario,
            "mando": linha["mando"],
            "gols_esperados": round(mu_ataque, 2),
            "gols_esperados_sofridos": round(mu_defesa, 2),
            "probabilidade_2_mais_gols": round(p_ataque, 3),
            "probabilidade_sg": round(p_defesa, 3),
            "faixa_ataque": _faixa_expectativa(p_ataque, meta["modelo_ataque_gols_marcados"]["faixas_probabilidade"]),
            "faixa_defesa": _faixa_expectativa(p_defesa, meta["modelo_defesa_gols_sofridos"]["faixas_probabilidade"]),
            "confianca": _confianca(linha),
            "amostra_disponivel": linha["amostra_geral"],
            "amostra_mesmo_mando": linha["amostra_mesmo_mando"],
            "recem_promovido_ou_pouco_historico": linha["recem_promovido_ou_pouco_historico"],
            "fatores_ataque": _contribuicoes(meta["modelo_ataque_gols_marcados"], linha),
            "fatores_defesa": _contribuicoes(meta["modelo_defesa_gols_sofridos"], linha),
        }
    return saida
