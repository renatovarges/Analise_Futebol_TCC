# Dicionário de dados

## 1. Registro bruto de partida (`sofascore_api.py::_monta_jogo`)

Um dict por partida, disputada ou agendada.

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | int | id da partida no SofaScore (chave primária) |
| `game_week` | int | rodada rotulada pelo SofaScore — **pode não bater com a data real** em caso de reagendamento; nunca usar para cortar histórico, só para exibição/agrupamento |
| `status` | "complete" \| "incomplete" | se a partida já aconteceu |
| `date_unix` | int | timestamp Unix da partida — **fonte de verdade para ordem cronológica** |
| `home_name` / `away_name` | str | nomes já normalizados (`normalize_team_name`) |
| `home_goals` / `away_goals` | int \| None | gols no fim do jogo; `None` se `status != "complete"` |
| `home_xg` / `away_xg` | float \| None | xG do SofaScore |
| `home_sot` / `away_sot` | int \| None | chutes no alvo |
| `home_xgot`/`away_xgot`, `home_shots`/`away_shots`, `home_shots_box`/`away_shots_box`, `home_shots_out_box`/`away_shots_out_box`, `home_shots_blocked`/`away_shots_blocked` | float \| None | detalhamento de finalizações |
| `home_big_chances` / `away_big_chances` | float \| None | grandes chances — **~4,4% de ausência** nos dados completos, tratado como ausente, nunca como zero |
| `home_big_chances_missed` / `away_big_chances_missed` | float \| None | grandes chances desperdiçadas |
| `home_touches_box` / `away_touches_box` | float \| None | toques na área |
| `home_possession` / `away_possession` | float \| None | posse de bola (%) |
| `home_corners` / `away_corners` | float \| None | escanteios |
| `home_gk_saves` / `away_gk_saves` | float \| None | defesas do goleiro |
| `home_goals_prevented` / `away_goals_prevented` | float \| None | gols evitados pelo goleiro (xG sofrido − gols sofridos) |
| `home_pen_goals` / `away_pen_goals` | int | gols de pênalti |
| `home_xg_jogada` / `away_xg_jogada` | float | xG de jogada aberta |
| `home_xg_bola_parada` / `away_xg_bola_parada` | float | xG de bola parada |
| `home_xg_contra_ataque` / `away_xg_contra_ataque` | float | xG de contra-ataque |
| `home_chutes_jogada`/`away_chutes_jogada`, `home_chutes_bola_parada`/`away_chutes_bola_parada` | int | contagem de chutes por tipo de jogada |

Ausência = `None`, sempre. Nunca `0` disfarçado.

## 2. Validação (`modeling/data_quality.py`)

| Tipo | Campo/função | Regra |
|---|---|---|
| Esquema obrigatório | `CAMPOS_OBRIGATORIOS` | `id, game_week, status, date_unix, home_name, away_name` — ausência aqui invalida a partida |
| Esquema crítico (completa) | `CAMPOS_CRITICOS_COMPLETA` | gols, xG, chutes, chutes no alvo, finalizações/toques na área — ausência não invalida a partida, mas conta na cobertura |
| Esquema parcial | `CAMPOS_CRITICOS_PARCIAIS` | grandes chances (cobertura ~96%) |
| Duplicidade | `detectar_duplicatas` | por `id` repetido e por `(home, away, mesmo dia)` com ids diferentes |
| Remarcação | `detectar_remarcadas` | desvio > 10 dias da mediana de data da própria `game_week` |
| Cobertura | `cobertura_por_time` | por equipe: partidas completas, casa/fora, % campos críticos preenchidos, nível (alta ≥10 jogos e ≥95% campos / média ≥5 e ≥85% / baixa) |

## 3. Dataset longitudinal (`modeling/dataset_builder.py::construir_dataset`)

Uma linha por **equipe por partida completa**. Colunas:

### Identificação e contexto

| Coluna | Descrição |
|---|---|
| `partida_id`, `time`, `adversario`, `mando` (casa/fora), `game_week`, `date_unix`, `temporada` | identificação |
| `amostra_geral` | nº de partidas anteriores (por data) da equipe, qualquer mando |
| `amostra_mesmo_mando` | idem, só no mesmo mando da partida-alvo |
| `recem_promovido_ou_pouco_historico` | `amostra_geral < 3` |
| `dias_descanso` | dias desde a partida anterior da equipe; `None` se não há partida anterior |

### Features (por métrica, ver seção 4)

Para cada métrica base (gols, gols sem pênalti, xG, chutes no alvo, chutes, finalizações na área, toques na área, grandes chances, xG por tipo de jogada) e para **próprio** (produzido) e **cedido**:

| Sufixo | Janela |
|---|---|
| `_j3` | últimos 3 jogos (com shrinkage em cadeia mesmo-mando→geral→liga, k=2,0) |
| `_j5` | últimos 5 jogos |
| `_j10` | últimos 10 jogos |
| `_temporada` | todos os jogos da temporada até a data |
| `_ewma` | média móvel exponencial (α=0,30) |

Exemplo: `xg_j3` (xG produzido, últimos 3 jogos, com shrinkage), `sot_ced_temporada` (chutes no alvo cedidos, temporada toda).

Após `forca_adversario()`/`features_confronto_futuro()`, toda coluna acima ganha uma equivalente `adv_<coluna>` — os mesmos números, só que do adversário daquela partida específica.

### Alvos (rótulos — só existem para partidas já disputadas)

| Coluna | Descrição |
|---|---|
| `alvo_2mais_gols` | 1 se a equipe marcou ≥2 gols nessa partida, senão 0 |
| `alvo_sg` | 1 se a equipe não sofreu gol nessa partida, senão 0 |
| `gols_marcados`, `gols_sofridos` | contagem bruta (usada para treinar o Poisson, que modela contagem, não o rótulo binário) |

## 4. Features curadas usadas pelo modelo (`modeling/models.py`)

Não é o dataset inteiro (235 colunas seriam multicolineares demais para ~2500 linhas) — curadoria mantém só janela curta (`_j3`, momento) + janela longa (`_temporada`, lastro), próprio e cedido, mais o espelho do adversário:

**Ataque**: `xg`, `sot`, `chutes_area`, `toques_area`, `grandes_chances` (próprio, `_j3` e `_temporada`) + `xg_ced`, `sot_ced`, `chutes_area_ced`, `grandes_chances_ced` (do adversário, `_j3` e `_temporada`) + `dias_descanso`, `amostra_geral`, `mando_casa`.

**Defesa**: espelho exato, trocando produzido por cedido.

## 5. Saída do modelo (`modeling/prediction.py::prever_confronto`)

| Campo | Descrição |
|---|---|
| `probabilidade_2_mais_gols`, `probabilidade_sg` | probabilidades calibradas pelo Poisson |
| `gols_esperados`, `gols_esperados_sofridos` | μ do Poisson (gols esperados) |
| `faixa_ataque`, `faixa_defesa` | "expectativa baixa/moderada/alta/muito alta", derivada dos percentis reais da distribuição do modelo (não corte arbitrário) |
| `confianca` | 0-1, função de amostra disponível — **separada** da probabilidade |
| `fatores_ataque`, `fatores_defesa` | top-4 features por `|contribuição|` = coeficiente × valor padronizado |

## 6. Dossiê para narrativa (`analytics_engine.py::_dossie_modelo`)

| Campo | Descrição |
|---|---|
| `probabilidade`, `faixa_expectativa`, `confianca_modelo` | do modelo (seção 5) |
| `veredito` | MUITO_FAVORAVEL / FAVORAVEL / NEUTRO / RESSALVA / ALTA_EXIGENCIA — por percentil da probabilidade própria e do eixo oposto do adversário |
| `proprio`, `adversario_fatos` | fatos descritivos (tabela de N últimos jogos, ver seção 3 de `data_processor.py`) — **descritivos, não usados para calcular a probabilidade** |
| `razoes` | 2 frases geradas a partir de `fatores_ataque`/`fatores_defesa` |
| `superlativos`, `superlativos_adversario` | destaques descritivos ("maior xG entre os mandantes") |
