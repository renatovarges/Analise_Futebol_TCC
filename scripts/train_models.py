"""
scripts/train_models.py — treina o modelo final de produção (seção 17).

Diferente do backtest (que refita a cada rodada só para MEDIR desempenho),
este script treina UMA VEZ com todos os dados disponíveis até hoje e exporta
os coeficientes em JSON puro — a app em produção faz a conta com numpy, sem
precisar de scikit-learn/scipy no deploy (ver requirements-dev.txt).

Uso:
    python scripts/build_dataset.py
    python scripts/train_models.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import numpy as np
import pandas as pd

from modeling.models import (
    COLUNA_GOLS_PROPRIOS, COLUNA_GOLS_SOFRIDOS,
    FEATURES_CURADAS_2MAIS_GOLS, FEATURES_CURADAS_SG, _matriz,
)
from modeling.shrinkage import K_VALIDADO

ARTIFACTS_DIR = BASE_DIR / ".." if False else BASE_DIR / "artifacts"


def _distribuicao_probabilidade(mu: np.ndarray, alvo_2mais: bool) -> dict:
    if alvo_2mais:
        p0 = np.exp(-mu)
        p1 = mu * np.exp(-mu)
        p = np.clip(1 - p0 - p1, 0, 1)
    else:
        p = np.clip(np.exp(-mu), 0, 1)
    return {
        "p10": round(float(np.percentile(p, 10)), 4),
        "p25": round(float(np.percentile(p, 25)), 4),
        "p50": round(float(np.percentile(p, 50)), 4),
        "p75": round(float(np.percentile(p, 75)), 4),
        "p90": round(float(np.percentile(p, 90)), 4),
    }


def _treinar_poisson(df: pd.DataFrame, coluna_gols: str, features: list[str], alvo_2mais: bool) -> dict:
    from sklearn.linear_model import PoissonRegressor
    from sklearn.preprocessing import StandardScaler

    X = _matriz(df, features)
    y = df[coluna_gols].fillna(0).to_numpy()
    scaler = StandardScaler().fit(X)
    modelo = PoissonRegressor(alpha=1.0, max_iter=1000)
    modelo.fit(scaler.transform(X), y)

    mu_treino = modelo.predict(scaler.transform(X))
    colunas_matriz = features + ["mando_casa"]
    return {
        "features": colunas_matriz,
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "coef": modelo.coef_.tolist(),
        "intercept": float(modelo.intercept_),
        "faixas_probabilidade": _distribuicao_probabilidade(mu_treino, alvo_2mais),
    }


def main() -> None:
    df = pd.read_parquet(ARTIFACTS_DIR / "dataset.parquet")

    modelo_ataque = _treinar_poisson(df, COLUNA_GOLS_PROPRIOS, FEATURES_CURADAS_2MAIS_GOLS, alvo_2mais=True)
    modelo_defesa = _treinar_poisson(df, COLUNA_GOLS_SOFRIDOS, FEATURES_CURADAS_SG, alvo_2mais=False)

    ultima_partida = int(df["date_unix"].max())
    hash_execucao = hashlib.sha256(
        json.dumps({"linhas": len(df), "ultima_partida": ultima_partida,
                    "temporadas": sorted(df["temporada"].unique().tolist()),
                    "coef_ataque": modelo_ataque["coef"], "coef_defesa": modelo_defesa["coef"]},
                   sort_keys=True).encode()
    ).hexdigest()[:16]

    metadata = {
        "versao_modelo": "poisson-v1",
        "versao_dataset": "v1",
        "treinado_em": pd.Timestamp.utcnow().isoformat(),
        "ultima_partida_usada_unix": ultima_partida,
        "ultima_partida_usada_data": pd.Timestamp(ultima_partida, unit="s", tz="UTC").strftime("%Y-%m-%d"),
        "linhas_treino": int(len(df)),
        "temporadas_treino": sorted(df["temporada"].unique().tolist()),
        "k_shrinkage": K_VALIDADO,
        "hash_execucao": hash_execucao,
        "escolhido_por": (
            "backtest walk-forward 126 folds (2023-2026): Poisson teve o menor Brier Score "
            "e melhor calibração nos dois alvos entre baseline, logística L2/elastic net e "
            "gradient boosting — ver artifacts/evaluation_summary.json. A vantagem sobre a "
            "baseline é MODESTA e não passou no teste de significância a 95% (IC da diferença "
            "de Brier inclui zero nos dois alvos — ver artifacts/validacao_poisson.json). "
            "Poisson foi escolhido por robustez estrutural (deriva P(2+gols) e P(SG) da mesma "
            "distribuição, sem mistura posterior com score heurístico), estabilidade do "
            "ranking (correlação de Spearman ~0,91 sob reamostragem do treino) e simplicidade "
            "interpretável — não por vantagem preditiva grande comprovada."
        ),
        "modelo_ataque_gols_marcados": modelo_ataque,
        "modelo_defesa_gols_sofridos": modelo_defesa,
    }

    with (ARTIFACTS_DIR / "model_metadata.json").open("w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"Modelo final treinado com {len(df)} linhas ({metadata['temporadas_treino']}).")
    print(f"hash_execucao={hash_execucao}  ultima_partida={metadata['ultima_partida_usada_data']}")
    print(f"Salvo em {ARTIFACTS_DIR / 'model_metadata.json'}")


if __name__ == "__main__":
    main()
