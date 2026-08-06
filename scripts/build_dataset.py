"""
scripts/build_dataset.py — monta o dataset longitudinal multi-temporada.

Uso:
    python scripts/build_dataset.py

Lê todos os arquivos de cache em .cache/sofascore_*.json (cada um é uma
temporada), constrói o dataset equipe-partida de cada uma SEPARADAMENTE
(elenco muda muito entre temporadas no Brasileirão — não faz sentido rolar
uma janela de "últimos 3 jogos" atravessando a virada de ano), depois
concatena tudo e salva em artifacts/dataset.parquet.

Reprodutível: mesma entrada (mesmos arquivos de cache) produz sempre a
mesma saída, porque construir_dataset() não tem nenhuma fonte de
aleatoriedade.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import pandas as pd

from modeling.dataset_builder import construir_dataset, forca_adversario
from modeling.data_quality import relatorio_qualidade
from sofascore_api import SEASONS_HISTORICAS, SEASON_ID

CACHE_DIR = BASE_DIR / ".cache"
ARTIFACTS_DIR = BASE_DIR / "artifacts"

# season_id -> rótulo de temporada
_ROTULO_POR_SEASON_ID = {v: k for k, v in SEASONS_HISTORICAS.items()}
_ROTULO_POR_SEASON_ID[SEASON_ID] = "2026"


def _rotulo_da_temporada(arquivo: Path) -> str:
    # sofascore_325_87678.json -> season_id 87678
    season_id = int(arquivo.stem.split("_")[-1])
    return _ROTULO_POR_SEASON_ID.get(season_id, str(season_id))


def main() -> None:
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    arquivos = sorted(CACHE_DIR.glob("sofascore_*.json"))
    if not arquivos:
        raise SystemExit(f"Nenhum cache encontrado em {CACHE_DIR}")

    partes = []
    qualidade_por_temporada = {}
    for arq in arquivos:
        rotulo = _rotulo_da_temporada(arq)
        with arq.open(encoding="utf-8") as f:
            jogos = json.load(f)

        rel = relatorio_qualidade(jogos)
        qualidade_por_temporada[rotulo] = {
            "total_partidas": rel["total_partidas"],
            "partidas_completas": rel["partidas_completas"],
            "partidas_invalidas_schema": rel["partidas_invalidas_schema"],
            "ids_duplicados": len(rel["ids_duplicados"]),
            "partidas_remarcadas": len(rel["partidas_remarcadas"]),
        }

        df_temp = construir_dataset(jogos, temporada=rotulo)
        if df_temp.empty:
            print(f"  {rotulo}: 0 partidas completas, pulando")
            continue
        df_temp = forca_adversario(df_temp)
        partes.append(df_temp)
        print(f"  {rotulo}: {len(df_temp)} linhas ({rel['partidas_completas']} partidas completas)")

    df = pd.concat(partes, ignore_index=True)
    df = df.sort_values(["temporada", "date_unix", "time"]).reset_index(drop=True)

    saida = ARTIFACTS_DIR / "dataset.parquet"
    df.to_parquet(saida, index=False)

    resumo = {
        "linhas_totais": len(df),
        "colunas_totais": len(df.columns),
        "temporadas": sorted(df["temporada"].unique().tolist()),
        "linhas_por_temporada": df["temporada"].value_counts().to_dict(),
        "taxa_alvo_2mais_gols": round(float(df["alvo_2mais_gols"].mean()), 4),
        "taxa_alvo_sg": round(float(df["alvo_sg"].mean()), 4),
        "qualidade_por_temporada": qualidade_por_temporada,
    }
    with (ARTIFACTS_DIR / "dataset_resumo.json").open("w", encoding="utf-8") as f:
        json.dump(resumo, f, ensure_ascii=False, indent=2)

    print(f"\nDataset salvo em {saida}")
    print(f"  {resumo['linhas_totais']} linhas, {resumo['colunas_totais']} colunas")
    print(f"  temporadas: {resumo['temporadas']}")
    print(f"  taxa 2+ gols: {resumo['taxa_alvo_2mais_gols']:.1%}  |  taxa SG: {resumo['taxa_alvo_sg']:.1%}")


if __name__ == "__main__":
    main()
