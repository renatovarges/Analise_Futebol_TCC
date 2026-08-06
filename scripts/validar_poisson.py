"""
scripts/validar_poisson.py — a vantagem do Poisson sobre a baseline é real ou
é ruído amostral? (seção 1 da revisão de 2026-08-06)

Diferente de run_backtest.py (que avalia cada candidato separadamente), este
script compara Poisson E baseline NAS MESMAS rodadas, par a par, e bootstrapa
o GANHO — não duas médias soltas. Isso responde a pergunta certa: "nesta
mesma rodada, o Poisson errou menos que a baseline, ou foi só sorte de
amostra".

CONVENÇÃO DE SINAL (única, usada em todo o projeto — scripts, artifacts/*.json,
docs/BACKTEST.md, docs/MODEL_CARD.md):

    ganho_brier = brier_baseline − brier_modelo

    positivo → o modelo (Poisson) errou MENOS que a baseline (modelo melhor)
    negativo → a baseline errou MENOS que o modelo (baseline melhor)
    zero     → empate

Brier Score é erro (menor é melhor), então "ganho" tem que ser
"o que eu tirei de erro" = erro_de_quem_eu_comparo − erro_do_modelo. Testado
em tests/test_brier_convention.py.

Uso:
    python scripts/validar_poisson.py
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from modeling.models import candidatos_para
from modeling.validation import gerar_folds

ARTIFACTS_DIR = BASE_DIR / "artifacts"
ALVOS = ("alvo_2mais_gols", "alvo_sg")


def _prever_fold(spec, df_treino, df_teste):
    estado = spec["ajustar"](df_treino)
    return spec["prever"](estado, df_teste)


def _brier_por_rodada(y_real: np.ndarray, y_prob: np.ndarray) -> float:
    return float(np.mean((y_prob - y_real) ** 2))


def ganho_brier_pareado(df: pd.DataFrame, alvo: str, folds) -> dict:
    cand = candidatos_para(alvo)
    baseline_spec, poisson_spec = cand["baseline_liga_mando"], cand["poisson"]

    linhas = []
    for fold in folds:
        df_treino, df_teste = df.loc[fold.idx_treino], df.loc[fold.idx_teste]
        y_real = df_teste[alvo].to_numpy()
        p_base = _prever_fold(baseline_spec, df_treino, df_teste)
        p_pois = _prever_fold(poisson_spec, df_treino, df_teste)

        brier_base = _brier_por_rodada(y_real, p_base)
        brier_pois = _brier_por_rodada(y_real, p_pois)
        linhas.append({
            "temporada": fold.temporada, "rodada": fold.rodada, "date_min": fold.date_min,
            "n": len(y_real),
            "brier_baseline": brier_base, "brier_poisson": brier_pois,
            "ganho_brier": brier_base - brier_pois,   # positivo = poisson melhor (ver docstring do módulo)
            "y_real": y_real, "p_base": p_base, "p_pois": p_pois,
            "mando": df_teste["mando"].to_numpy(), "time": df_teste["time"].to_numpy(),
            "game_week": df_teste["game_week"].to_numpy(),
        })

    ganhos = np.array([l["ganho_brier"] for l in linhas])
    rng = np.random.default_rng(42)
    n = len(ganhos)
    boot = np.array([ganhos[rng.integers(0, n, size=n)].mean() for _ in range(2000)])
    ic_lo, ic_hi = np.percentile(boot, [2.5, 97.5])
    p_valor_unicaudal = float(np.mean(boot <= 0))   # fração de replicações em que o Poisson NÃO venceria

    # desempenho por terço da temporada (posição relativa dentro de cada temporada)
    por_temporada_rodadas = {}
    for l in linhas:
        por_temporada_rodadas.setdefault(l["temporada"], []).append(l["rodada"])
    terco_de = {}
    for temp, rodadas in por_temporada_rodadas.items():
        rmin, rmax = min(rodadas), max(rodadas)
        largura = max(1, (rmax - rmin + 1) / 3)
        for r in rodadas:
            pos = (r - rmin) / largura
            terco_de[(temp, r)] = "inicio" if pos < 1 else ("meio" if pos < 2 else "fim")

    def _agrupar(chave_fn):
        grupos = {}
        for l in linhas:
            chave = chave_fn(l)
            grupos.setdefault(chave, []).append(l)
        saida = {}
        for chave, ls in grupos.items():
            yb = np.concatenate([x["y_real"] for x in ls])
            pb = np.concatenate([x["p_base"] for x in ls])
            pp = np.concatenate([x["p_pois"] for x in ls])
            saida[chave] = {
                "n": int(len(yb)),
                "brier_baseline": round(_brier_por_rodada(yb, pb), 4),
                "brier_poisson": round(_brier_por_rodada(yb, pp), 4),
                "ganho_brier": round(_brier_por_rodada(yb, pb) - _brier_por_rodada(yb, pp), 4),
            }
        return saida

    por_temporada = _agrupar(lambda l: l["temporada"])
    por_mando = {}
    for l in linhas:
        for m in ("casa", "fora"):
            mask = l["mando"] == m
            if mask.sum() == 0:
                continue
            por_mando.setdefault(m, {"y": [], "pb": [], "pp": []})
            por_mando[m]["y"].append(l["y_real"][mask])
            por_mando[m]["pb"].append(l["p_base"][mask])
            por_mando[m]["pp"].append(l["p_pois"][mask])
    por_mando_final = {}
    for m, d in por_mando.items():
        y, pb, pp = np.concatenate(d["y"]), np.concatenate(d["pb"]), np.concatenate(d["pp"])
        por_mando_final[m] = {
            "n": int(len(y)),
            "brier_baseline": round(_brier_por_rodada(y, pb), 4),
            "brier_poisson": round(_brier_por_rodada(y, pp), 4),
            "ganho_brier": round(_brier_por_rodada(y, pb) - _brier_por_rodada(y, pp), 4),
        }

    por_terco = _agrupar(lambda l: terco_de[(l["temporada"], l["rodada"])])

    # distribuição das probabilidades previstas (poisson)
    todas_p_pois = np.concatenate([l["p_pois"] for l in linhas])
    dist = {
        "min": round(float(todas_p_pois.min()), 4), "max": round(float(todas_p_pois.max()), 4),
        "media": round(float(todas_p_pois.mean()), 4), "desvio_padrao": round(float(todas_p_pois.std()), 4),
        "p10": round(float(np.percentile(todas_p_pois, 10)), 4),
        "p50": round(float(np.percentile(todas_p_pois, 50)), 4),
        "p90": round(float(np.percentile(todas_p_pois, 90)), 4),
    }

    return {
        "convencao": "ganho_brier = brier_baseline - brier_modelo (positivo = modelo melhor)",
        "n_rodadas": len(linhas), "n_observacoes": int(sum(l["n"] for l in linhas)),
        "brier_medio_baseline": round(float(np.mean([l["brier_baseline"] for l in linhas])), 4),
        "brier_medio_poisson": round(float(np.mean([l["brier_poisson"] for l in linhas])), 4),
        "ganho_brier_medio": round(float(ganhos.mean()), 4),
        "ganho_brier_ic95": [round(float(ic_lo), 4), round(float(ic_hi), 4)],
        "fracao_rodadas_poisson_melhor": round(float(np.mean(ganhos > 0)), 3),
        "p_valor_unicaudal_bootstrap": round(p_valor_unicaudal, 4),
        "por_temporada": por_temporada,
        "por_mando": por_mando_final,
        "por_terco_temporada": por_terco,
        "distribuicao_probabilidades_poisson": dist,
        "_linhas_para_estabilidade": linhas,
    }


def estabilidade_ranking(df: pd.DataFrame, alvo: str, folds, n_reps: int = 15) -> dict:
    """
    Robustez do ranking a perturbação da amostra de treino: para uma amostra
    de rodadas, retreina o Poisson em N reamostragens bootstrap (por
    temporada, não por linha solta) do treino e mede a correlação de Spearman
    entre o ranking de probabilidade original e cada ranking reamostrado.
    Correlação média perto de 1 = ranking estável; perto de 0 = frágil.
    """
    from scipy.stats import spearmanr

    spec = candidatos_para(alvo)["poisson"]
    rng = np.random.default_rng(7)
    amostra_folds = folds[::max(1, len(folds) // 12)][:12]   # ~12 rodadas espalhadas

    correlacoes = []
    for fold in amostra_folds:
        df_treino, df_teste = df.loc[fold.idx_treino], df.loc[fold.idx_teste]
        if len(df_teste) < 4:
            continue
        p_original = _prever_fold(spec, df_treino, df_teste)

        temporadas_treino = df_treino["temporada"].unique()
        for _ in range(n_reps):
            partes = []
            for t in temporadas_treino:
                bloco = df_treino[df_treino["temporada"] == t]
                rodadas_unicas = bloco["game_week"].unique()
                escolhidas = rng.choice(rodadas_unicas, size=len(rodadas_unicas), replace=True)
                for r in escolhidas:
                    partes.append(bloco[bloco["game_week"] == r])
            df_boot = pd.concat(partes, ignore_index=True) if partes else df_treino
            try:
                p_boot = _prever_fold(spec, df_boot, df_teste)
            except Exception:
                continue
            rho, _ = spearmanr(p_original, p_boot)
            if not np.isnan(rho):
                correlacoes.append(rho)

    return {
        "n_pares_avaliados": len(correlacoes),
        "spearman_medio": round(float(np.mean(correlacoes)), 3) if correlacoes else None,
        "spearman_p10": round(float(np.percentile(correlacoes, 10)), 3) if correlacoes else None,
        "interpretacao": (
            "correlação média entre o ranking original e o ranking obtido reamostrando "
            "o treino por temporada (bootstrap em blocos de rodada) — mede o quanto a "
            "ORDEM prevista depende de quais rodadas específicas entraram no treino"
        ),
    }


def main() -> None:
    df = pd.read_parquet(ARTIFACTS_DIR / "dataset.parquet")
    folds = gerar_folds(df)

    saida = {"gerado_em": pd.Timestamp.utcnow().isoformat(), "n_folds": len(folds)}
    for alvo in ALVOS:
        print(f"=== {alvo} ===")
        r = ganho_brier_pareado(df, alvo, folds)
        linhas_raw = r.pop("_linhas_para_estabilidade")
        print(f"  brier baseline={r['brier_medio_baseline']}  poisson={r['brier_medio_poisson']}  "
              f"ganho_brier={r['ganho_brier_medio']}  IC95={r['ganho_brier_ic95']}  "
              f"poisson melhor em {r['fracao_rodadas_poisson_melhor']:.0%} das rodadas  "
              f"p(ganho<=0)={r['p_valor_unicaudal_bootstrap']}")

        est = estabilidade_ranking(df, alvo, folds)
        print(f"  estabilidade do ranking (spearman médio): {est['spearman_medio']}")
        r["estabilidade_ranking"] = est
        saida[alvo] = r

    with (ARTIFACTS_DIR / "validacao_poisson.json").open("w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)
    print(f"\nSalvo em {ARTIFACTS_DIR / 'validacao_poisson.json'}")


if __name__ == "__main__":
    main()
