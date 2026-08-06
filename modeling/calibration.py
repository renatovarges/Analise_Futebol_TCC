"""
modeling/calibration.py — calibração pós-hoc das probabilidades (seção 7).

Platt scaling: ajusta logit(p_calibrada) = a*p_bruta + b por regressão
logística 1-D. Escolhido em vez de isotonic regression porque cada fold de
treino do walk-forward tem só algumas centenas de linhas — isotonic com
poucos pontos tende a ficar em degraus e overfitar; Platt, sendo paramétrico
com 2 parâmetros, generaliza melhor nessa escala de amostra.

O calibrador é ajustado com as previsões IN-SAMPLE do próprio conjunto de
treino (nunca com o conjunto de teste da rodada) — mantém a ordem temporal:
o calibrador de uma rodada nunca viu o resultado dela.
"""
from __future__ import annotations

import numpy as np


def ajustar_platt(y_treino: np.ndarray, prob_bruta_treino: np.ndarray):
    from sklearn.linear_model import LogisticRegression

    X = prob_bruta_treino.reshape(-1, 1)
    modelo = LogisticRegression(max_iter=1000)
    modelo.fit(X, y_treino)
    return modelo


def aplicar_platt(modelo, prob_bruta: np.ndarray) -> np.ndarray:
    return modelo.predict_proba(prob_bruta.reshape(-1, 1))[:, 1]
