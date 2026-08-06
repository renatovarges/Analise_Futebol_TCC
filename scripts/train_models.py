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


def _treinar_poisson(df: pd.DataFrame, coluna_gols: str, features: list[str]) -> dict:
    from sklearn.linear_model import PoissonRegressor
    from sklearn.preprocessing import StandardScaler

    X = _matriz(df, features)
    y = df[coluna_gols].fillna(0).to_numpy()
    scaler = StandardScaler().fit(X)
    modelo = PoissonRegressor(alpha=1.0, max_iter=1000)
    modelo.fit(scaler.transform(X), y)

    colunas_matriz = features + ["mando_casa"]
    return {
        "features": colunas_matriz,
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "coef": modelo.coef_.tolist(),
        "intercept": float(modelo.intercept_),
    }


def main() -> None:
    df = pd.read_parquet(ARTIFACTS_DIR / "dataset.parquet")

    modelo_ataque = _treinar_poisson(df, COLUNA_GOLS_PROPRIOS, FEATURES_CURADAS_2MAIS_GOLS)
    modelo_defesa = _treinar_poisson(df, COLUNA_GOLS_SOFRIDOS, FEATURES_CURADAS_SG)

    metadata = {
        "versao_modelo": "poisson-v1",
        "treinado_em": pd.Timestamp.utcnow().isoformat(),
        "linhas_treino": int(len(df)),
        "temporadas_treino": sorted(df["temporada"].unique().tolist()),
        "k_shrinkage": K_VALIDADO,
        "escolhido_por": (
            "backtest walk-forward 126 folds (2023-2026): Poisson venceu baseline, "
            "logística L2/elastic net e gradient boosting nos dois alvos em Brier, "
            "LogLoss, ROC AUC e erro de calibração — ver artifacts/evaluation_summary.json"
        ),
        "modelo_ataque_gols_marcados": modelo_ataque,
        "modelo_defesa_gols_sofridos": modelo_defesa,
    }

    with (ARTIFACTS_DIR / "model_metadata.json").open("w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"Modelo final treinado com {len(df)} linhas ({metadata['temporadas_treino']}).")
    print(f"Salvo em {ARTIFACTS_DIR / 'model_metadata.json'}")


if __name__ == "__main__":
    main()
