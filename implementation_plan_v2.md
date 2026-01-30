# Plano de Implementação: Melhorias Visuais e Evidências

## Objetivos
1.  **Exportação PNG (Alta Resolução):** Permitir que o usuário baixe as tabelas de análise (Mandantes e Visitantes) como imagens PNG de alta qualidade, prontas para compartilhamento.
2.  **Relatório de Evidências:** Exibir (e possivelmente exportar) a lista detalhada dos jogos que foram usados para calcular as médias de cada time, garantindo transparência total.

## 1. Exportação PNG (O Desafio Visual)
O Streamlit exibe HTML interativo. Para gerar um PNG, precisamos renderizar a tabela como uma imagem no backend Python.
**Solução Ténica:** Usar `matplotlib` para desenhar a tabela.
- Criar uma função `gerar_tabela_png(dataframe, titulo)`.
- Estilizar com cores escuras (Dark Mode) para combinar com a interface.
- Configurar DPI alto (ex: 300) para garantir "altíssima resolução".
- Adicionar botão `st.download_button` que recebe o buffer de bytes da imagem.

## 2. Relatório de Evidências (O "Drill-Down")
Visualizar *quais* jogos entraram na média.
**Layout Desajado:** Cards ou Grid mostrando o confronto (ex: CHA x VIT) e abaixo a lista de jogos considerados para cada um.
**Alterações no Código:**
*   **`data_processor.py`**: A função `calcular_metricas` deve retornar NÃO APENAS os números finais, mas também o DataFrame `recorte` (os jogos usados).
*   **`app.py`**:
    *   Coletar esses históricos durante o loop de análise.
    *   Criar uma nova seção visual "Detalhamento / Evidências".
    *   Formatá-los conforme o exemplo do usuário: "Adversário | Placar | xG | xGA".

## Estrutura de Mudanças

### `data_processor.py`
- Alterar assinatura de return de `calcular_metricas`. Agora retorna tupla: `(stats_dict, jogos_df)`.

### `app.py`
- Adaptar chamadas para desempacotar `stats, historico`.
- **UI Tabelas**: Adicionar botão de download de PNG abaixo de cada tabela.
- **UI Evidências**: Criar uma nova área expansível ou separada para mostrar o grid de evidências.

## Bibliotecas Necessárias
- `matplotlib` (já instalada no script padrão, mas confirmar).
