"""
scripts/run_backtest.py — backtest walk-forward reproduzível (seção 6).

Uso:
    python scripts/build_dataset.py      # se artifacts/dataset.parquet não existir
    python scripts/run_backtest.py

Treina cada candidato SÓ com linhas anteriores a cada rodada, prevê a rodada
seguinte, avança. Nunca embaralha, nunca calibra ou seleciona modelo olhando
o resultado da própria rodada testada. Salva artifacts/evaluation_summary.json
com os números reais — o que entra em BACKTEST.md vem só daqui, não de
estimativa manual.
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
warnings.filterwarnings("ignore")

import pandas as pd

from modeling.models import candidatos_para
from modeling.validation import ResultadoFold, avaliar, gerar_folds

ARTIFACTS_DIR = BASE_DIR / "artifacts"
ALVOS = ("alvo_2mais_gols", "alvo_sg")


def rodar_para_alvo(df: pd.DataFrame, alvo: str, folds) -> dict:
    candidatos = candidatos_para(alvo)
    saida = {}
    for nome, spec in candidatos.items():
        t0 = time.time()
        resultados, previsoes_por_rodada = [], []
        falhas = 0
        for fold in folds:
            df_treino = df.loc[fold.idx_treino]
            df_teste = df.loc[fold.idx_teste]
            try:
                estado = spec["ajustar"](df_treino)
                probs = spec["prever"](estado, df_teste)
            except Exception as e:
                falhas += 1
                continue
            y_real = df_teste[alvo].to_numpy()
            resultados.append(ResultadoFold(
                temporada=fold.temporada, rodada=fold.rodada,
                mando=df_teste["mando"].to_numpy(), y_real=y_real, y_prob=probs,
            ))
            df_rodada = df_teste[["time", "mando", "temporada", "game_week"]].copy()
            df_rodada["prob"] = probs
            df_rodada[alvo] = y_real
            previsoes_por_rodada.append(df_rodada)

        metricas = avaliar(resultados, previsoes_por_rodada, "prob", alvo)
        metricas["familia"] = spec["familia"]
        metricas["segundos"] = round(time.time() - t0, 1)
        metricas["folds_com_falha"] = falhas
        saida[nome] = metricas
        print(f"    {nome:24s} brier={metricas['brier_score']}  "
              f"logloss={metricas['log_loss']}  auc={metricas['roc_auc']}  "
              f"ece={metricas['erro_calibracao_esperado']}  "
              f"({metricas['segundos']}s, {falhas} falhas)")

    # também avalia por mando e por temporada, para o modelo vencedor
    return saida


def avaliar_por_recorte(df: pd.DataFrame, alvo: str, folds, nome_candidato: str) -> dict:
    from modeling.models import candidatos_para
    from modeling.validation import avaliar

    spec = candidatos_para(alvo)[nome_candidato]
    linhas = []
    for fold in folds:
        df_treino = df.loc[fold.idx_treino]
        df_teste = df.loc[fold.idx_teste]
        try:
            estado = spec["ajustar"](df_treino)
            probs = spec["prever"](estado, df_teste)
        except Exception:
            continue
        tmp = df_teste[["time", "mando", "temporada", "game_week", "amostra_geral"]].copy()
        tmp["prob"] = probs
        tmp["real"] = df_teste[alvo].to_numpy()
        linhas.append(tmp)
    todas = pd.concat(linhas, ignore_index=True)

    por_temporada = {}
    for temp, g in todas.groupby("temporada"):
        por_temporada[temp] = {
            "n": len(g),
            "brier": round(float(((g["prob"] - g["real"]) ** 2).mean()), 4),
            "taxa_real": round(float(g["real"].mean()), 4),
        }
    por_mando = {}
    for mando, g in todas.groupby("mando"):
        por_mando[mando] = {
            "n": len(g),
            "brier": round(float(((g["prob"] - g["real"]) ** 2).mean()), 4),
            "taxa_real": round(float(g["real"].mean()), 4),
        }
    return {"por_temporada": por_temporada, "por_mando": por_mando}


def main() -> None:
    caminho = ARTIFACTS_DIR / "dataset.parquet"
    if not caminho.exists():
        raise SystemExit("Rode antes: python scripts/build_dataset.py")
    df = pd.read_parquet(caminho)

    folds = gerar_folds(df)
    print(f"Folds válidos (walk-forward): {len(folds)}")
    print(f"  primeiro: {folds[0].temporada} rodada {folds[0].rodada}")
    print(f"  último:   {folds[-1].temporada} rodada {folds[-1].rodada}")

    resultado_geral = {}
    for alvo in ALVOS:
        print(f"\n=== {alvo} ===")
        resultado_geral[alvo] = rodar_para_alvo(df, alvo, folds)

    # recorte por temporada/mando do melhor candidato de cada alvo (por Brier)
    detalhe_vencedor = {}
    for alvo in ALVOS:
        candidatos_ord = sorted(
            resultado_geral[alvo].items(),
            key=lambda kv: kv[1]["brier_score"] if kv[1]["brier_score"] is not None else 9,
        )
        melhor = candidatos_ord[0][0]
        detalhe_vencedor[alvo] = {
            "candidato": melhor,
            **avaliar_por_recorte(df, alvo, folds, melhor),
        }

    ARTIFACTS_DIR.mkdir(exist_ok=True)
    saida = {
        "gerado_em": pd.Timestamp.utcnow().isoformat(),
        "n_folds": len(folds),
        "resultados": resultado_geral,
        "detalhe_melhor_candidato": detalhe_vencedor,
    }
    with (ARTIFACTS_DIR / "evaluation_summary.json").open("w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)

    print(f"\nSalvo em {ARTIFACTS_DIR / 'evaluation_summary.json'}")


if __name__ == "__main__":
    main()
