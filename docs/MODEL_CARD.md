# Model Card — Poisson v1

## Finalidade

Estimar, para cada equipe de cada confronto de uma rodada do Brasileirão:

- `probabilidade_2_mais_gols` — P(a equipe marca 2 ou mais gols nesta partida)
- `probabilidade_sg` — P(a equipe não sofre gol nesta partida, "SG")

Essas duas probabilidades ordenam os rankings "Melhores ataques" e "Melhores defesas" exibidos na plataforma. O modelo **não** prevê o placar exato, não estima a probabilidade de vitória/empate/derrota, e não incorpora informação de escalação, lesões, suspensões ou troca de treinador — usa exclusivamente o histórico de partidas já disputadas.

## Fonte dos dados

SofaScore (API interna, não documentada, sem chave — ver `sofascore_api.py`), Campeonato Brasileiro Série A, temporadas **2023, 2024, 2025 e 2026** (2026 parcial, 205 de 380 jogos disputados até a data de treinamento).

## Variáveis utilizadas (resumo — dicionário completo em `DATA_DICTIONARY.md`)

**Modelo de ataque** (18 variáveis + mando): xG, chutes no alvo, finalizações na área, toques na área e grandes chances — cada uma em duas janelas (últimos 3 jogos e média da temporada), tanto do lado **próprio** quanto **cedidas pelo adversário**. Mais dias de descanso e tamanho de amostra disponível.

**Modelo de defesa**: espelho do modelo de ataque, trocando "produzido" por "cedido" e "adversário produz" por "adversário cede".

Lista exata de colunas em `artifacts/model_metadata.json` → `features`.

## Metodologia

1. **Dataset longitudinal equipe-partida** (`modeling/dataset_builder.py`): uma linha por equipe por partida, features calculadas só com partidas **anteriores por data real** (`date_unix`), nunca por rótulo de rodada — ver `BACKTEST.md` para o motivo (partidas remarcadas).
2. **Shrinkage** (`modeling/shrinkage.py`): toda média de equipe é uma combinação ponderada por amostra entre mesmo-mando → geral da equipe → média da liga naquele momento, com `k=2.0` (validado por grade de busca, seção correspondente em `BACKTEST.md`).
3. **Modelo**: regressão de Poisson (`sklearn.linear_model.PoissonRegressor`, `alpha=1.0`), uma para gols marcados (ataque) e uma para gols sofridos (defesa). Ver fórmula abaixo.
4. **Sem calibração adicional**: testamos recalibração Platt por cima do Poisson e o resultado **piorou** Brier, LogLoss, AUC e ECE nos dois alvos — mantido o Poisson puro (ver `BACKTEST.md`).

## Formulação matemática

Para cada modelo (ataque e defesa), separadamente:

```
log(μ) = intercepto + Σᵢ coefᵢ · zᵢ
zᵢ = (xᵢ − médiaᵢ) / desvioᵢ                    (padronização StandardScaler, ajustada só no treino)
μ  = exp(log(μ))                                 (taxa esperada de gols — link function do Poisson)
```

**P(2 ou mais gols)**, a partir de μ do modelo de ataque:

```
P(0) = e^(−μ)
P(1) = μ · e^(−μ)
P(2+) = 1 − P(0) − P(1)
```

**P(SG)**, a partir de μ_sofridos do modelo de defesa:

```
P(SG) = P(adversário marca 0) = P(0) = e^(−μ_sofridos)
```

Ambas as fórmulas são testadas contra a definição matemática direta em `tests/test_predictions.py::test_formula_p_2mais_gols_e_1_menos_p0_menos_p1` e `::test_formula_p_sg_e_p_zero`.

**Mando** entra como variável binária (`mando_casa`) dentro do próprio vetor de features — não há ajuste separado por mando depois; é o modelo que aprende o efeito.

**Força do adversário** entra via as colunas `adv_*` (o que o adversário produz/cede, na mesma janela) — não há mistura posterior com nenhum score heurístico separado (o antigo mecanismo de "potencialização por sinal de z-score" foi removido da produção, ver seção 8 de `BACKTEST.md`).

**Pouco histórico**: equipes com `amostra_geral` baixa (início de temporada, recém-promovido) têm suas features fortemente encolhidas em direção à média da liga pelo shrinkage (passo 2) — o modelo em si não trata isso de forma especial além disso; a *confiança* exibida na interface (separada da probabilidade) é o que sinaliza esse caso ao usuário (`modeling/prediction.py::_confianca`).

## Validação temporal

Walk-forward real: 126 folds, cada um treinado só com dados de data anterior à rodada testada, nunca embaralhado. Ver `BACKTEST.md` para o procedimento completo e todos os números.

## Métricas (resumo — completo em `BACKTEST.md`)

| | ataque (2+ gols) | defesa (SG) |
|---|---|---|
| Brier Score | 0,2219 | 0,1981 |
| ROC AUC | 0,599 | 0,614 |
| Diferença de Brier vs. baseline | +0,0009 (IC95 inclui zero) | +0,0014 (IC95 inclui zero) |
| Lift top 3 sobre a taxa-base da rodada | +13,3pp | +11,4pp |
| Estabilidade do ranking (Spearman sob reamostragem) | 0,909 | 0,908 |

## Limitações (honestas, não suavizadas)

- **AUC ≈ 0,60** é capacidade de discriminação **limitada**. Não é "alta precisão".
- A vantagem de calibração média sobre uma baseline simples (taxa da liga por mando) **não é estatisticamente significativa a 95%** nos dois alvos — o intervalo de confiança da diferença de Brier Score inclui zero.
- O modelo não sabe de escalação, lesão, suspensão, técnico novo ou qualquer informação de última hora.
- Grandes chances (`grandes_chances`) tem ~4,4% de ausência nos dados de origem — tratado como ausente, nunca como zero, mas ainda assim reduz um pouco a amostra efetiva dessa feature específica.
- O corte por temporada no shrinkage (item 4 da cadeia da seção 4) não herda força do ano anterior — times recém-promovidos começam sempre próximos da média da liga, mesmo que o histórico de Série B sugerisse algo diferente (decisão deliberada, não uma lacuna — ver `modeling/shrinkage.py`).
- A comparação "modo espelho" contra o motor antigo (`artifacts/comparacao_motores.json`) usa o modelo **final**, treinado com dados que incluem as próprias rodadas comparadas — não é uma estimativa livre de viés de otimismo. A estimativa correta e livre desse viés é o backtest walk-forward.

## Quando o modelo é menos confiável

- Times com poucos jogos disputados na temporada (início de campeonato, recém-promovidos) — sinalizado pelo campo `confianca`, que fica baixo nesses casos independentemente da probabilidade prevista.
- Rodadas com muitas partidas remarcadas/adiadas próximas à data de análise.
- Qualquer cenário fora do padrão histórico do Brasileirão (mudança de formato de disputa, interrupção de temporada, etc.) — o modelo não tem mecanismo para detectar isso sozinho.

## Versão e retreinamento

- **Versão do modelo**: `poisson-v1`
- **Versão do dataset**: `v1`
- **Retreinar**: `python scripts/build_dataset.py && python scripts/train_models.py` (ou `python scripts/atualizar_rodada.py`, que inclui os dois passos). Cada execução grava `treinado_em`, `ultima_partida_usada_data` e `hash_execucao` em `artifacts/model_metadata.json` — confira esses três campos para saber a idade e a proveniência do modelo em produção.

## Desempenho por temporada

Ver tabela completa em `BACKTEST.md`, seção "Desempenho por temporada".
