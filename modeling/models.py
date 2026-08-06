"""
modeling/models.py — candidatos comparados no backtest (seção 5).

Cada candidato implementa a mesma interface:
    ajustar(X_treino, y_treino) -> estado
    prever_proba(estado, X_teste) -> np.ndarray de probabilidades

FEATURES_CURADAS existe porque o dataset tem 5 janelas por métrica
(j3/j5/j10/temporada/ewma) mais as mesmas 5 do adversário — jogar tudo cru
num modelo linear com ~2500 linhas é multicolinearidade garantida. A curadoria
mantém só o par MOMENTO (j3, o que mudou recentemente) + LASTRO (temporada,
a base mais estável), próprio e cedido, mais o espelho do adversário — a
mesma lógica de "curta pesa mais, longa dá lastro" que o motor antigo já
usava, só que agora com o peso decidido pelo modelo em vez de uma constante
fixa (PESO_CURTA=0,58 do analytics_engine.py antigo).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

_METRICAS_OFENSIVAS = ["xg", "sot", "chutes_area", "toques_area", "grandes_chances"]
_METRICAS_DEFENSIVAS = ["xg", "sot", "chutes_area", "grandes_chances"]  # cedido

FEATURES_CURADAS_2MAIS_GOLS = (
    [f"{m}_j3" for m in _METRICAS_OFENSIVAS] +
    [f"{m}_temporada" for m in _METRICAS_OFENSIVAS] +
    [f"adv_{m}_ced_j3" for m in _METRICAS_DEFENSIVAS] +
    [f"adv_{m}_ced_temporada" for m in _METRICAS_DEFENSIVAS] +
    ["dias_descanso", "amostra_geral"]
)

FEATURES_CURADAS_SG = (
    [f"{m}_ced_j3" for m in _METRICAS_DEFENSIVAS] +
    [f"{m}_ced_temporada" for m in _METRICAS_DEFENSIVAS] +
    [f"adv_{m}_j3" for m in _METRICAS_OFENSIVAS] +
    [f"adv_{m}_temporada" for m in _METRICAS_OFENSIVAS] +
    ["dias_descanso", "amostra_geral"]
)

COLUNA_GOLS_PROPRIOS = "gols_marcados"
COLUNA_GOLS_SOFRIDOS = "gols_sofridos"


def _matriz(df: pd.DataFrame, features: list[str]) -> np.ndarray:
    X = df[features].copy()
    X["mando_casa"] = (df["mando"] == "casa").astype(float)
    return X.fillna(0.0).to_numpy(dtype=float)


@dataclass
class Candidato:
    nome: str
    familia: str   # "baseline" | "poisson" | "logistica" | "arvore"


# ---------------------------------------------------------------------------
# 1. BASELINE — média da liga por mando, sem nenhuma outra feature
# ---------------------------------------------------------------------------

def baseline_ajustar(df_treino: pd.DataFrame, alvo: str) -> dict:
    return {
        "casa": df_treino.loc[df_treino["mando"] == "casa", alvo].mean(),
        "fora": df_treino.loc[df_treino["mando"] == "fora", alvo].mean(),
        "geral": df_treino[alvo].mean(),
    }


def baseline_prever(estado: dict, df_teste: pd.DataFrame) -> np.ndarray:
    return np.array([
        estado.get(m, estado["geral"]) if not pd.isna(estado.get(m, np.nan)) else estado["geral"]
        for m in df_teste["mando"]
    ])


# ---------------------------------------------------------------------------
# 2/3. LOGÍSTICA — L2 (ridge) e elastic net
# ---------------------------------------------------------------------------

def _logistica_ajustar(df_treino: pd.DataFrame, alvo: str, features: list[str], penalty: str):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    X = _matriz(df_treino, features)
    y = df_treino[alvo].to_numpy()
    scaler = StandardScaler().fit(X)
    Xs = scaler.transform(X)

    # SEM class_weight="balanced": ele reponderaria a função de perda e
    # deixaria predict_proba() de refletir a probabilidade real — bom para
    # ranking/classificação, ruim para probabilidade calibrada, que é o que
    # este produto entrega. 28-35% de taxa positiva não é desbalanceamento
    # que justifique o trade-off.
    kwargs = dict(max_iter=2000)
    if penalty == "l2":
        modelo = LogisticRegression(penalty="l2", C=1.0, **kwargs)
    else:
        modelo = LogisticRegression(penalty="elasticnet", solver="saga", C=0.5,
                                     l1_ratio=0.5, **kwargs)
    modelo.fit(Xs, y)
    return {"modelo": modelo, "scaler": scaler, "features": features}


def logistica_l2_ajustar(df_treino, alvo, features):
    return _logistica_ajustar(df_treino, alvo, features, "l2")


def logistica_elasticnet_ajustar(df_treino, alvo, features):
    return _logistica_ajustar(df_treino, alvo, features, "elasticnet")


def logistica_prever(estado: dict, df_teste: pd.DataFrame) -> np.ndarray:
    X = _matriz(df_teste, estado["features"])
    Xs = estado["scaler"].transform(X)
    return estado["modelo"].predict_proba(Xs)[:, 1]


# ---------------------------------------------------------------------------
# 4. POISSON — modela gols esperados (mu), deriva P(alvo) da distribuição
# ---------------------------------------------------------------------------

def poisson_ajustar(df_treino: pd.DataFrame, coluna_gols: str, features: list[str]) -> dict:
    from sklearn.linear_model import PoissonRegressor
    from sklearn.preprocessing import StandardScaler

    X = _matriz(df_treino, features)
    y = df_treino[coluna_gols].fillna(0).to_numpy()
    scaler = StandardScaler().fit(X)
    modelo = PoissonRegressor(alpha=1.0, max_iter=1000)
    modelo.fit(scaler.transform(X), y)
    return {"modelo": modelo, "scaler": scaler, "features": features}


def poisson_prever_2mais_gols(estado: dict, df_teste: pd.DataFrame) -> np.ndarray:
    """P(gols >= 2) = 1 - P(0) - P(1), com gols ~ Poisson(mu)."""
    X = _matriz(df_teste, estado["features"])
    mu = estado["modelo"].predict(estado["scaler"].transform(X))
    mu = np.clip(mu, 1e-6, None)
    p0 = np.exp(-mu)
    p1 = mu * np.exp(-mu)
    return 1 - p0 - p1


def poisson_prever_sg(estado: dict, df_teste: pd.DataFrame) -> np.ndarray:
    """P(SG) = P(gols sofridos == 0) = P(0), com gols_sofridos ~ Poisson(mu)."""
    X = _matriz(df_teste, estado["features"])
    mu = estado["modelo"].predict(estado["scaler"].transform(X))
    mu = np.clip(mu, 1e-6, None)
    return np.exp(-mu)


# ---------------------------------------------------------------------------
# 4b. POISSON + CALIBRAÇÃO PLATT — mesma previsão bruta, recalibrada (seção 7)
# ---------------------------------------------------------------------------

def poisson_calibrado_ajustar(df_treino: pd.DataFrame, alvo: str, coluna_gols: str,
                               features: list[str], prever_bruta) -> dict:
    from modeling.calibration import ajustar_platt

    base = poisson_ajustar(df_treino, coluna_gols, features)
    prob_bruta_treino = prever_bruta(base, df_treino)
    calibrador = ajustar_platt(df_treino[alvo].to_numpy(), prob_bruta_treino)
    return {**base, "calibrador": calibrador, "prever_bruta": prever_bruta}


def poisson_calibrado_prever(estado: dict, df_teste: pd.DataFrame) -> np.ndarray:
    from modeling.calibration import aplicar_platt

    prob_bruta = estado["prever_bruta"](estado, df_teste)
    return aplicar_platt(estado["calibrador"], prob_bruta)


# ---------------------------------------------------------------------------
# 5. GRADIENT BOOSTING — raso e regularizado de propósito
# ---------------------------------------------------------------------------

def gbm_ajustar(df_treino: pd.DataFrame, alvo: str, features: list[str]) -> dict:
    from sklearn.ensemble import HistGradientBoostingClassifier

    X = _matriz(df_treino, features)
    y = df_treino[alvo].to_numpy()
    # complexidade deliberadamente contida: profundidade 3, poucas iterações,
    # regularização L2 e early stopping — não é para ganhar o backtest à
    # força bruta, é para ver se não-linearidade ajuda de verdade.
    modelo = HistGradientBoostingClassifier(
        max_depth=3, max_iter=150, learning_rate=0.05,
        l2_regularization=1.0, early_stopping=True,
        validation_fraction=0.2, n_iter_no_change=10,
        random_state=42,
    )
    modelo.fit(X, y)
    return {"modelo": modelo, "features": features}


def gbm_prever(estado: dict, df_teste: pd.DataFrame) -> np.ndarray:
    X = _matriz(df_teste, estado["features"])
    return estado["modelo"].predict_proba(X)[:, 1]


# ---------------------------------------------------------------------------
# REGISTRO
# ---------------------------------------------------------------------------
# alvo: "alvo_2mais_gols" | "alvo_sg"

def candidatos_para(alvo: str) -> dict[str, dict]:
    features = FEATURES_CURADAS_2MAIS_GOLS if alvo == "alvo_2mais_gols" else FEATURES_CURADAS_SG
    coluna_gols = COLUNA_GOLS_PROPRIOS if alvo == "alvo_2mais_gols" else COLUNA_GOLS_SOFRIDOS
    poisson_prever = poisson_prever_2mais_gols if alvo == "alvo_2mais_gols" else poisson_prever_sg

    return {
        "baseline_liga_mando": {
            "ajustar": lambda df: baseline_ajustar(df, alvo),
            "prever": baseline_prever,
            "familia": "baseline",
        },
        "logistica_l2": {
            "ajustar": lambda df: logistica_l2_ajustar(df, alvo, features),
            "prever": logistica_prever,
            "familia": "logistica",
        },
        "logistica_elasticnet": {
            "ajustar": lambda df: logistica_elasticnet_ajustar(df, alvo, features),
            "prever": logistica_prever,
            "familia": "logistica",
        },
        "poisson": {
            "ajustar": lambda df: poisson_ajustar(df, coluna_gols, features),
            "prever": poisson_prever,
            "familia": "poisson",
        },
        "poisson_calibrado": {
            "ajustar": lambda df: poisson_calibrado_ajustar(df, alvo, coluna_gols, features, poisson_prever),
            "prever": poisson_calibrado_prever,
            "familia": "poisson",
        },
        "gbm_regularizado": {
            "ajustar": lambda df: gbm_ajustar(df, alvo, features),
            "prever": gbm_prever,
            "familia": "arvore",
        },
    }
