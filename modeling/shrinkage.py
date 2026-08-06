"""
modeling/shrinkage.py — encolhimento em direção à média da liga (seção 4).

    media_ajustada = (n / (n + k)) * media_equipe + (k / (n + k)) * media_liga

k é sempre um parâmetro explícito passado por quem chama — nunca uma
constante escondida aqui. O valor de k é escolhido em scripts/run_backtest.py
por validação (grade de valores, escolhido pelo Brier Score fora da amostra),
não por achismo. Antes dessa validação rodar, K_PROVISORIO serve só para
destravar o desenvolvimento do dataset e dos modelos — não é o valor final
e todo código que o usa deve dizer isso explicitamente.
"""
from __future__ import annotations

K_PROVISORIO = 4.0  # substituído pelo k validado assim que o backtest rodar


def encolher(media_equipe: float | None, n: int, media_liga: float, k: float) -> float:
    """n=0 (ou média ausente) devolve a média da liga pura; n grande se aproxima da equipe."""
    if media_equipe is None or n <= 0:
        return media_liga
    peso_equipe = n / (n + k)
    return peso_equipe * media_equipe + (1 - peso_equipe) * media_liga


def encolher_em_cadeia(
    media_mesmo_mando: float | None, n_mesmo_mando: int,
    media_geral: float | None, n_geral: int,
    media_liga: float, k: float,
) -> float:
    """
    Cadeia de fallback da seção 4: mesmo mando -> geral da equipe -> liga.

    Não pula direto para a média da liga só porque falta amostra no mesmo
    mando — primeiro empresta força do histórico geral da equipe (mesmo
    elenco/sistema, só sem separar por mando), e encolhe ESSE resultado em
    direção à liga pela amostra geral disponível. Só then aplica o encolhimento
    específico do mando sobre essa base.

    Temporada anterior (item 4 da cadeia, seção 4) ainda não entra aqui: o
    dataset builder hoje trabalha com uma temporada por vez. Ver TODO em
    dataset_builder.py — entra quando o backtest multi-temporada (seção 6)
    passar a alimentar séries de mais de um ano por equipe.
    """
    base = encolher(media_geral, n_geral, media_liga, k)
    if media_mesmo_mando is None or n_mesmo_mando <= 0:
        return base
    peso_mando = n_mesmo_mando / (n_mesmo_mando + k)
    return peso_mando * media_mesmo_mando + (1 - peso_mando) * base
