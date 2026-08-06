"""
modeling/shrinkage.py — encolhimento em direção à média da liga (seção 4).

    media_ajustada = (n / (n + k)) * media_equipe + (k / (n + k)) * media_liga

k é sempre um parâmetro explícito passado por quem chama — nunca uma
constante escondida aqui.

K_VALIDADO = 2.0 foi escolhido em 2026-08-06 por grade de busca (k em
{1,2,4,6,8,12,16}) usando o backtest walk-forward real do modelo vencedor
(Poisson) nas 4 temporadas disponíveis (scripts/run_backtest.py + grade
ad-hoc). k=1 e k=2 empataram tecnicamente no Brier Score (diferença dentro
do ruído do bootstrap, IC95 de ~0,011); k=2 foi escolhido entre os dois por
ter o melhor erro de calibração no alvo ofensivo (ECE 0,0132 vs 0,0154) e
por encolher um pouco mais os casos de amostra ínfima (0-1 jogo), sem custo
prático de desempenho. Valores acima de 4 pioram os dois alvos de forma
consistente — shrinkage forte demais está apagando sinal real.
"""
from __future__ import annotations

K_VALIDADO = 2.0


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
    direção à liga pela amostra geral disponível. Só então aplica o
    encolhimento específico do mando sobre essa base.

    Temporada anterior (item 4 da cadeia, seção 4) é uma decisão TOMADA, não
    pendente: scripts/build_dataset.py constrói cada temporada em separado
    (reseta amostra_geral=0 a cada virada de ano) de propósito — o
    Brasileirão troca ~20% do elenco entre temporadas (acesso/rebaixamento),
    então herdar força de 2025 para o início de 2026 misturaria sinal de
    times que nem estão mais na Série A. O shrinkage cobre o início de
    temporada puxando para a média da LIGA (que já reflete o nível da
    divisão naquele ano), não para o histórico do time no ano anterior.
    """
    base = encolher(media_geral, n_geral, media_liga, k)
    if media_mesmo_mando is None or n_mesmo_mando <= 0:
        return base
    peso_mando = n_mesmo_mando / (n_mesmo_mando + k)
    return peso_mando * media_mesmo_mando + (1 - peso_mando) * base
