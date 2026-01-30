# Plano de Refinamento: Lógica de Data Estrita

## O Erro Conceitual
A tentativa anterior de filtrar por `Rodada < Rodada Alvo` foi rejeitada corretamente pelo usuário.
**Motivo:** Se a Rodada 3 for antecipada e jogada ANTES da Rodada 2, ela DEVE entrar na análise da Rodada 2. O dado existe no passado cronológico e deve ser usado.

## A Solução Correta (Regra de Ouro)
1. Identificar a **Data do Confronto Alvo** (ex: o jogo da Rodada 2 acontece dia 18/02).
2. O histórico do time deve considerar **TODOS** os jogos realizados ESTRITAMENTE ANTES dessa data (ex: `Data_Jogo < 18/02`).
3. Se um jogo da Rodada 3 aconteceu dia 12/02, ele É válido (`12/02 < 18/02`) e DEVE entrar.
4. Se um jogo da Rodada 9 aconteceu dia 01/04, ele NÃO é válido (`01/04 > 18/02`) e NÃO entra.

## Ação em Código (`data_processor.py`)
- **Remover** o parâmetro `rodada_absoluta`.
- **Reforçar** a comparação de datas.
    - O problema anterior (onde jogos futuros entravam) sugeria que a comparação `Data < Data` estava falhando.
    - **Diagnóstico:** As datas no DataFrame podem estar contendo horas (00:00:00) ou serem strings mal formatadas.
    - **Correção:** Garantir que TANTO a data do limite QUANTO as datas do DataFrame sejam convertidas para `datetime` limpo antes da comparação.

## Teste de Validação
- Jogo R2 (Athletico x Corinthians, 18/02).
- Jogo R3 (Athletico x Santos, 12/02).
- Se analisamos a R2: O jogo da R3 DEVE entrar (pois 12/02 < 18/02).
- Jogo R9 (Flu x Corinthians, 01/04).
- Se analisamos a R2: O jogo da R9 NÃO deve entrar.

Vamos executar essa limpeza lógica agora.
