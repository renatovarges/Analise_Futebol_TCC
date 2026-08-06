"""
modeling/validation.py — validação temporal walk-forward e métricas (seção 6).

O corte de vazamento já acontece dentro de cada linha (dataset_builder.py usa
date_unix da própria partida como corte de histórico). O que este módulo
garante é a segunda camada: o MODELO em si só pode ser treinado com linhas
cuja data é anterior à rodada que está sendo prevista — senão o modelo
"aprende" um coeficiente calibrado com o resultado que está tentando prever.

Walk-forward: agrupa por (temporada, game_week), ordena os grupos pela data
mínima de cada um, e a cada passo treina com tudo que veio antes e testa no
grupo seguinte. Nunca embaralha.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

MINIMO_TREINO = 60   # linhas mínimas de treino para o fold entrar na avaliação


@dataclass
class Fold:
    temporada: str
    rodada: int
    date_min: int
    idx_treino: np.ndarray
    idx_teste: np.ndarray


def gerar_folds(df: pd.DataFrame, minimo_treino: int = MINIMO_TREINO) -> list[Fold]:
    grupos = (
        df.groupby(["temporada", "game_week"])["date_unix"]
        .min().reset_index().sort_values("date_unix")
    )
    folds = []
    for _, g in grupos.iterrows():
        idx_teste = df.index[
            (df["temporada"] == g["temporada"]) & (df["game_week"] == g["game_week"])
        ].to_numpy()
        idx_treino = df.index[df["date_unix"] < g["date_unix"]].to_numpy()
        if len(idx_treino) < minimo_treino or len(idx_teste) == 0:
            continue
        folds.append(Fold(
            temporada=g["temporada"], rodada=int(g["game_week"]), date_min=int(g["date_unix"]),
            idx_treino=idx_treino, idx_teste=idx_teste,
        ))
    return folds


# ---------------------------------------------------------------------------
# MÉTRICAS
# ---------------------------------------------------------------------------

@dataclass
class ResultadoFold:
    temporada: str
    rodada: int
    mando: np.ndarray
    y_real: np.ndarray
    y_prob: np.ndarray


def brier_score(y_real: np.ndarray, y_prob: np.ndarray) -> float:
    return float(np.mean((y_prob - y_real) ** 2))


def log_loss_seguro(y_real: np.ndarray, y_prob: np.ndarray, eps: float = 1e-7) -> float:
    p = np.clip(y_prob, eps, 1 - eps)
    return float(-np.mean(y_real * np.log(p) + (1 - y_real) * np.log(1 - p)))


def curva_calibracao(y_real: np.ndarray, y_prob: np.ndarray, n_faixas: int = 5) -> list[dict]:
    """Divide em quantis de probabilidade prevista e compara com a taxa real observada."""
    if len(y_prob) < n_faixas * 5:
        n_faixas = max(2, len(y_prob) // 10) or 1
    ordem = np.argsort(y_prob)
    faixas = np.array_split(ordem, n_faixas)
    saida = []
    for f in faixas:
        if len(f) == 0:
            continue
        saida.append({
            "n": int(len(f)),
            "prob_media_prevista": round(float(y_prob[f].mean()), 4),
            "taxa_real_observada": round(float(y_real[f].mean()), 4),
        })
    return saida


def erro_calibracao_esperado(curva: list[dict]) -> float:
    """ECE ponderado pelo tamanho de cada faixa."""
    n_total = sum(c["n"] for c in curva) or 1
    return round(sum(c["n"] * abs(c["prob_media_prevista"] - c["taxa_real_observada"])
                      for c in curva) / n_total, 4)


def roc_auc(y_real: np.ndarray, y_prob: np.ndarray) -> float | None:
    from sklearn.metrics import roc_auc_score
    if len(set(y_real.tolist())) < 2:
        return None
    return float(roc_auc_score(y_real, y_prob))


def pr_auc(y_real: np.ndarray, y_prob: np.ndarray) -> float | None:
    from sklearn.metrics import average_precision_score
    if len(set(y_real.tolist())) < 2:
        return None
    return float(average_precision_score(y_real, y_prob))


def bootstrap_ic_brier(resultados: list[ResultadoFold], n_boot: int = 1000, seed: int = 42) -> tuple[float, float]:
    """
    IC 95% do Brier Score por bootstrap AGRUPADO POR RODADA — reamostra
    rodadas inteiras, não observações soltas, para não fingir independência
    entre os dois times do mesmo confronto (seção 6).
    """
    rng = np.random.default_rng(seed)
    n_folds = len(resultados)
    if n_folds == 0:
        return (float("nan"), float("nan"))
    scores = []
    for _ in range(n_boot):
        escolhidos = rng.integers(0, n_folds, size=n_folds)
        y_real = np.concatenate([resultados[i].y_real for i in escolhidos])
        y_prob = np.concatenate([resultados[i].y_prob for i in escolhidos])
        scores.append(brier_score(y_real, y_prob))
    return (round(float(np.percentile(scores, 2.5)), 4), round(float(np.percentile(scores, 97.5)), 4))


def taxa_acerto_top_n(df_rodada: pd.DataFrame, coluna_prob: str, coluna_alvo: str, n: int) -> float | None:
    """Entre os N times com maior probabilidade prevista NA RODADA, qual fração bateu o alvo de verdade."""
    if len(df_rodada) < n:
        return None
    top = df_rodada.nlargest(n, coluna_prob)
    return float(top[coluna_alvo].mean())


def lift_top_n(df_rodada: pd.DataFrame, coluna_prob: str, coluna_alvo: str, n: int) -> float | None:
    taxa_top = taxa_acerto_top_n(df_rodada, coluna_prob, coluna_alvo, n)
    taxa_media = df_rodada[coluna_alvo].mean()
    if taxa_top is None or taxa_media == 0:
        return None
    return round(taxa_top - taxa_media, 4)


def avaliar(resultados: list[ResultadoFold], previsoes_por_rodada: list[pd.DataFrame],
            coluna_prob: str, coluna_alvo: str) -> dict:
    y_real = np.concatenate([r.y_real for r in resultados]) if resultados else np.array([])
    y_prob = np.concatenate([r.y_prob for r in resultados]) if resultados else np.array([])

    curva = curva_calibracao(y_real, y_prob)
    ic_lo, ic_hi = bootstrap_ic_brier(resultados)

    tops = {}
    for n in (3, 5, 6):
        lifts = [lift_top_n(df, coluna_prob, coluna_alvo, n) for df in previsoes_por_rodada]
        lifts = [l for l in lifts if l is not None]
        tops[f"lift_top{n}"] = round(float(np.mean(lifts)), 4) if lifts else None
        taxas = [taxa_acerto_top_n(df, coluna_prob, coluna_alvo, n) for df in previsoes_por_rodada]
        taxas = [t for t in taxas if t is not None]
        tops[f"taxa_top{n}"] = round(float(np.mean(taxas)), 4) if taxas else None

    return {
        "n_observacoes": int(len(y_real)),
        "n_rodadas": len(resultados),
        "brier_score": round(brier_score(y_real, y_prob), 4) if len(y_real) else None,
        "brier_ic95": [ic_lo, ic_hi],
        "log_loss": round(log_loss_seguro(y_real, y_prob), 4) if len(y_real) else None,
        "roc_auc": round(roc_auc(y_real, y_prob), 4) if roc_auc(y_real, y_prob) is not None else None,
        "pr_auc": round(pr_auc(y_real, y_prob), 4) if pr_auc(y_real, y_prob) is not None else None,
        "erro_calibracao_esperado": erro_calibracao_esperado(curva),
        "curva_calibracao": curva,
        "taxa_base_real": round(float(y_real.mean()), 4) if len(y_real) else None,
        **tops,
    }
