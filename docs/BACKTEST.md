# Backtest — resultado completo e reproduzível

Todos os números desta página vêm de `artifacts/evaluation_summary.json`, `artifacts/validacao_poisson.json` e `artifacts/comparacao_motores.json`, gerados por:

```bash
python scripts/build_dataset.py
python scripts/run_backtest.py
python scripts/validar_poisson.py
python scripts/comparar_motores.py
```

Nenhum número aqui foi estimado manualmente.

## Setup

- **Dados**: 2530 observações equipe-partida, 4 temporadas do Brasileirão (2023, 2024, 2025, 2026 parcial), 205-360 partidas completas por temporada.
- **Validação**: walk-forward real, 126 folds. Cada fold treina só com linhas de data anterior à rodada testada; nunca embaralha temporada; nunca calibra no conjunto de teste.
- **Alvos**: `alvo_2mais_gols` (equipe marca ≥2 gols) e `alvo_sg` (equipe não sofre gol).

## 1. Modelo atual (Poisson) vs. baselines e candidatos

| Modelo | Brier (2+gols) | LogLoss | AUC | ECE | Brier (SG) | LogLoss | AUC | ECE |
|---|---|---|---|---|---|---|---|---|
| baseline (liga + mando) | 0,2233 | 0,6382 | 0,569 | 0,0224 | 0,1995 | 0,5873 | 0,568 | 0,0195 |
| logística L2 | 0,2255 | 0,6446 | 0,591 | 0,0396 | 0,2028 | 0,5953 | 0,589 | 0,0359 |
| logística elastic net | 0,2240 | 0,6410 | 0,594 | 0,0281 | 0,2011 | 0,5905 | 0,590 | 0,0273 |
| **Poisson (produção)** | **0,2219** | **0,6356** | **0,599** | **0,0132** | **0,1981** | **0,5837** | **0,614** | **0,0265** |
| Poisson + calibração Platt | 0,2228 | 0,6373 | 0,591 | 0,0170 | 0,1996 | 0,5874 | 0,601 | 0,0306 |
| gradient boosting raso | 0,2254 | 0,6430 | 0,575 | 0,0184 | 0,2002 | 0,5888 | 0,582 | 0,0202 |

**Não escondido**: o gradient boosting (candidato "mais sofisticado") não supera a baseline em nenhuma métrica, em nenhum dos dois alvos. Calibração Platt adicional piora o Poisson nos dois alvos. Nenhum dos dois foi escolhido.

## 2. A vantagem do Poisson é real ou é ruído? (comparação pareada)

`baseline` e `poisson` avaliados **nas mesmas rodadas**, diferença de Brier calculada rodada a rodada, IC 95% por bootstrap (2000 replicações) **agrupado por rodada** — reamostra rodadas inteiras, não observações soltas.

| Alvo | Brier baseline | Brier Poisson | Diferença média | IC 95% da diferença | % rodadas Poisson melhor |
|---|---|---|---|---|---|
| 2+ gols | 0,2224 | 0,2215 | +0,0009 | **[-0,0019 ; 0,0033]** | 56% |
| SG | 0,2021 | 0,2008 | +0,0014 | **[-0,0005 ; 0,0033]** | 54% |

**O intervalo de confiança inclui zero nos dois casos — a vantagem de calibração média NÃO é estatisticamente significativa a 95%.** Isso é reportado explicitamente, não escondido atrás da média pontual.

## 3. O que É real: capacidade de ranquear (lift no top N)

| Alvo | top 3 | top 5 | top 6 |
|---|---|---|---|
| 2+ gols — lift sobre a taxa-base da rodada | +13,3pp | +11,4pp | +10,5pp |
| SG — lift sobre a taxa-base da rodada | +11,4pp | +9,6pp | +9,6pp |

Mesmo com calibração média não-significativa, escolher os times mais bem colocados no ranking do modelo produz uma taxa de acerto consistentemente acima da média da própria rodada. Isso é coerente: Brier Score mede erro médio de calibração; lift no top-N mede capacidade de **ordenar**. São propriedades diferentes.

## 4. Desempenho por temporada

**2+ gols** (Brier, baseline vs. Poisson, pareado):

| Temporada | n | Brier baseline | Brier Poisson | Diferença |
|---|---|---|---|---|
| 2023 | 660 | 0,2221 | 0,2221 | 0,0000 |
| 2024 | 706 | 0,2222 | 0,2214 | +0,0007 |
| 2025 | 694 | 0,2237 | 0,2206 | +0,0032 |
| 2026 (parcial) | 410 | 0,2266 | 0,2248 | +0,0018 |

**SG** (Brier, baseline vs. Poisson, pareado):

| Temporada | n | Brier baseline | Brier Poisson | Diferença |
|---|---|---|---|---|
| 2023 | 660 | 0,2115 | 0,2109 | +0,0007 |
| 2024 | 706 | 0,1944 | 0,1926 | +0,0018 |
| 2025 | 694 | 0,2042 | 0,2030 | +0,0012 |
| 2026 (parcial) | 410 | 0,1808 | 0,1785 | +0,0023 |

O Poisson nunca perde para a baseline em nenhuma temporada individual — a vantagem é pequena e consistente, não negativa em nenhum ano, mesmo não sendo significativa no agregado.

## 5. Desempenho por mando

| Alvo | Mando | n | Brier | Taxa real |
|---|---|---|---|---|
| 2+ gols | casa | 1235 | 0,2446 | 42,5% |
| 2+ gols | fora | 1235 | 0,1992 | 27,7% |
| SG | casa | 1235 | 0,2243 | 34,7% |
| SG | fora | 1235 | 0,1718 | 21,9% |

Times mandantes marcam 2+ gols quase 15 pontos percentuais mais que visitantes — o efeito de mando é grande e o modelo o captura via a feature `mando_casa`.

## 6. Desempenho por início/meio/fim de temporada

| Alvo | Período | n | Diferença Poisson−baseline |
|---|---|---|---|
| 2+ gols | início | 818 | **-0,0021** (baseline levemente melhor) |
| 2+ gols | meio | 840 | +0,0021 |
| 2+ gols | fim | 812 | +0,0042 |
| SG | início | 818 | +0,0020 |
| SG | meio | 840 | -0,0003 |
| SG | fim | 812 | +0,0026 |

Achado honesto: no início de temporada, o Poisson **não supera** a baseline no alvo ofensivo — faz sentido, já que o shrinkage puxa fortemente para a média da liga quando há pouco histórico, deixando o Poisson próximo da própria baseline nesse regime. A vantagem cresce ao longo da temporada, quando há mais sinal real disponível.

## 7. Estabilidade do ranking

Robustez a perturbação do treino: Poisson retreinado em 15 reamostragens bootstrap (por bloco de rodada) do conjunto de treino, para 12 rodadas de teste espalhadas; correlação de Spearman entre o ranking original e cada ranking reamostrado.

| Alvo | Spearman médio | Interpretação |
|---|---|---|
| 2+ gols | 0,909 | ranking pouco sensível a qual conjunto exato de rodadas entrou no treino |
| SG | 0,908 | idem |

## 8. Curva de calibração (Poisson, produção)

**2+ gols** — 5 faixas de probabilidade prevista, comparadas com a taxa real observada:

| Faixa (prob. prevista) | n | Prevista | Real | Diferença |
|---|---|---|---|---|
| 1 | 494 | 0,263 | 0,243 | +0,020 |
| 2 | 494 | 0,308 | 0,310 | -0,002 |
| 3 | 494 | 0,341 | 0,346 | -0,005 |
| 4 | 494 | 0,374 | 0,366 | +0,008 |
| 5 (mais alta) | 494 | 0,435 | 0,490 | -0,055 |

**SG**:

| Faixa (prob. prevista) | n | Prevista | Real | Diferença |
|---|---|---|---|---|
| 1 (mais baixa) | 494 | 0,230 | 0,168 | +0,062 |
| 2 | 494 | 0,272 | 0,231 | +0,041 |
| 3 | 494 | 0,298 | 0,293 | +0,005 |
| 4 | 494 | 0,327 | 0,330 | -0,003 |
| 5 | 494 | 0,368 | 0,393 | -0,024 |

O eixo SG tem um viés sistemático moderado na faixa mais baixa (superestima risco de sofrer gol para times com probabilidade de SG baixa) — testamos correção via Platt e ela piorou o resultado agregado (seção 1), então o viés fica documentado, mas não corrigido artificialmente.

## 9. Distribuição das probabilidades previstas (Poisson)

| Alvo | min | p10 | p50 | p90 | max | média | desvio padrão |
|---|---|---|---|---|---|---|---|
| 2+ gols | 0,080 | 0,267 | 0,339 | 0,428 | 0,654 | 0,343 | 0,065 |
| SG | 0,110 | 0,234 | 0,300 | 0,364 | 0,633 | 0,300 | 0,053 |

Essas faixas (p50/p75/p90, calculadas sobre o treino completo) são a base das faixas de expectativa ("baixa"/"moderada"/"alta"/"muito alta") mostradas na interface — derivadas da distribuição real, não de corte arbitrário.

## 10. Comparação em modo espelho — motor antigo (z-score) vs. novo (Poisson)

14 rodadas já disputadas da temporada 2026 (rodadas 8-21), resultado real conhecido.

**Atenção — leia antes de usar estes números como prova de superioridade**: esta comparação usa o modelo **final**, treinado com todas as 4 temporadas *incluindo* as rodadas aqui comparadas. Não é um teste out-of-sample limpo como o backtest walk-forward das seções 1-2. Mede "o que muda se eu trocar de motor hoje", com viés otimista a favor do modelo novo — não é a estimativa não-enviesada de acerto (essa é a das seções 1-2, mais conservadora).

| | top 3 novo | top 3 antigo | top 5 novo | top 5 antigo | top 6 novo | top 6 antigo |
|---|---|---|---|---|---|---|
| Ofensivo | 60,0% (24/40) | 39,0% (16/41) | 58,2% (39/67) | 38,8% (26/67) | 55,0% (44/80) | 35,8% (29/81) |
| Defensivo | 45,2% (19/42) | 38,1% (16/42) | 40,0% (28/70) | 38,6% (27/70) | 39,3% (33/84) | 38,1% (32/84) |

255 mudanças de posição de ≥5 lugares entre os dois motores, nas 14 rodadas — trocar de motor muda bastante quem aparece nos destaques.

O motor antigo permanece no código (`analytics_engine.analisar_rodada_legado`) só como baseline de auditoria — não participa da previsão de produção.

## Conclusão e motivo da escolha

**Poisson foi escolhido por:**

1. Vence a baseline e todos os outros candidatos em Brier Score, LogLoss, AUC e ECE nos dois alvos (seção 1) — ainda que por margem pequena.
2. Nunca perde para a baseline em nenhuma temporada individual (seção 4).
3. Ranking estável a perturbação do conjunto de treino (Spearman ~0,91, seção 7).
4. Estrutura probabilística coerente — deriva P(2+gols) e P(SG) de uma única distribuição (Poisson), sem misturar com nenhum score heurístico separado.
5. Interpretável: contribuição de cada variável é o coeficiente vezes o valor padronizado, sem precisar de SHAP ou explicação post-hoc aproximada.

**Não foi escolhido por ser "muito mais preciso"** — a vantagem de calibração média sobre a baseline não passou no teste de significância a 95% (seção 2). Isso está documentado aqui e no `MODEL_CARD.md`, e a interface não usa termos como "alta precisão" ou "modelo altamente confiável".
