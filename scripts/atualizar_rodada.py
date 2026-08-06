"""
scripts/atualizar_rodada.py — orquestrador único da rotina semanal (seção 8).

    1. atualiza os dados (SofaScore)
    2. valida a base (modeling/data_quality.py)
    3. reconstrói as variáveis (scripts/build_dataset.py)
    4. retreina o modelo só com jogos anteriores (scripts/train_models.py —
       o corte por data já garante isso, ver dataset_builder.py)
    5. gera as previsões da rodada (analytics_engine.analisar_rodada)
    6. constrói as evidências (parte do dossiê do passo 5)
    7. gera e valida as frases (narrative_engine.gerar_paragrafos)
    8. produz o roteiro em texto (as artes PNG continuam sob demanda na UI
       do Streamlit — geração de imagem é interativa por natureza, não faz
       sentido gerar 20 PNGs toda rodada sem o analista escolher)

Uso:
    python scripts/atualizar_rodada.py                 # próxima rodada com confrontos
    python scripts/atualizar_rodada.py --rodada 22
    python scripts/atualizar_rodada.py --rodada 22 --n-jogos 3 --filtro POR_MANDO

Não edita nenhum arquivo de código — é a única coisa que precisa rodar a
cada rodada nova.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
warnings.filterwarnings("ignore")


def _passo(n: int, titulo: str) -> None:
    print(f"\n{'='*70}\nPASSO {n}/8 — {titulo}\n{'='*70}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rodada", type=int, default=None)
    ap.add_argument("--n-jogos", type=int, default=3)
    ap.add_argument("--filtro", default="POR_MANDO", choices=["POR_MANDO", "TODOS"])
    ap.add_argument("--top-n", type=int, default=6)
    ap.add_argument("--provedor", default="python", choices=["python", "openai", "claude"])
    args = ap.parse_args()

    # 1. ATUALIZAR DADOS ----------------------------------------------------
    _passo(1, "Atualizando dados do SofaScore")
    from sofascore_api import fetch_all_matches, coletar_temporada
    # forcar=False (mesmo comportamento do botão "Atualizar dados da API" da
    # UI): jogos completos já em cache não são baixados de novo, só os jogos
    # novos desde a última rodada — muito mais rápido, e o fallback de
    # emergência (rede indisponível) continua ativo.
    fetch_all_matches.clear()
    jogos = coletar_temporada(forcar=False)
    print(f"  {len(jogos)} partidas na base ({sum(1 for j in jogos if j['status']=='complete')} completas)")

    # 2. VALIDAR A BASE -------------------------------------------------------
    _passo(2, "Validando qualidade dos dados")
    from modeling.data_quality import relatorio_qualidade
    rel = relatorio_qualidade(jogos)
    print(f"  partidas inválidas (esquema): {rel['partidas_invalidas_schema']}")
    print(f"  ids duplicados: {len(rel['ids_duplicados'])}")
    print(f"  confrontos duplicados: {len(rel['confrontos_duplicados'])}")
    print(f"  partidas remarcadas: {len(rel['partidas_remarcadas'])}")
    print(f"  cobertura: {rel['times_cobertura_alta']} alta / "
          f"{rel['times_cobertura_media']} média / {rel['times_cobertura_baixa']} baixa")
    if rel["partidas_invalidas_schema"] or rel["ids_duplicados"]:
        print("  [AVISO] problemas de qualidade encontrados — considere investigar antes de prosseguir.")

    # 3. RECONSTRUIR O DATASET ------------------------------------------------
    _passo(3, "Reconstruindo o dataset longitudinal (todas as temporadas)")
    import scripts.build_dataset as build_dataset
    build_dataset.main()

    # 4. RETREINAR O MODELO ---------------------------------------------------
    _passo(4, "Retreinando o modelo (só com jogos já disputados)")
    import scripts.train_models as train_models
    train_models.main()

    # 5/6. PREVISÕES + EVIDÊNCIAS ---------------------------------------------
    _passo(5, "Gerando previsões e evidências da rodada")
    import data_processor
    import analytics_engine

    rodada = args.rodada
    if rodada is None:
        rodadas = data_processor.get_rodadas_disponiveis()
        agendadas = [j["game_week"] for j in jogos if j["status"] != "complete"]
        rodada = min(agendadas) if agendadas else max(rodadas)
    print(f"  rodada alvo: {rodada}")

    confrontos = data_processor.get_confrontos_rodada(rodada)
    if not confrontos:
        print(f"  [ERRO] nenhum confronto encontrado para a rodada {rodada}. Abortando.")
        sys.exit(1)

    analise = analytics_engine.analisar_rodada(
        confrontos, rodada, args.n_jogos, args.filtro, top_n=args.top_n,
    )
    print(f"  modelo usado: {analise['modelo']['versao']} (hash {analise['modelo']['hash_execucao']})")
    print(f"  {len(analise['todos_ofensivos'])} times no ranking ofensivo, "
          f"{len(analise['todos_defensivos'])} no defensivo")

    # 7. FRASES + VALIDAÇÃO ----------------------------------------------------
    _passo(6, "Gerando e validando as frases")
    import narrative_engine
    redacao = narrative_engine.gerar_paragrafos(analise, provedor=args.provedor)
    n_fallback_item = sum(1 for f in redacao["fontes"].values() if "fallback" in f)
    n_repeticao_nao_resolvida = sum(1 for v in redacao["repeticoes"].values() if v)
    print(f"  provedor usado: {redacao['provedor_usado']}  ({redacao['segundos']}s)")
    print(f"  parágrafos substituídos por fallback (validação de IA falhou): {n_fallback_item}")
    print(f"  repetições não resolvidas: {n_repeticao_nao_resolvida}")
    if redacao["erro"]:
        print(f"  [AVISO] {redacao['erro']}")

    # 8. RELATÓRIO -------------------------------------------------------------
    _passo(7, "Montando o roteiro")
    roteiro = narrative_engine.montar_roteiro(analise, redacao["textos"])
    saida_dir = BASE_DIR / "artifacts"
    saida_dir.mkdir(exist_ok=True)
    caminho_roteiro = saida_dir / f"roteiro_rodada_{rodada}.txt"
    caminho_roteiro.write_text(roteiro, encoding="utf-8")
    print(f"  roteiro salvo em {caminho_roteiro}")

    _passo(8, "Concluído")
    print(
        "  Artes PNG (tabela principal e painel de evidências) continuam geradas sob "
        "demanda na interface do Streamlit — abra o app, confira o ranking desta rodada "
        "e clique nos botões de gerar imagem para os confrontos que for publicar."
    )
    print(f"\nRodada {rodada} pronta para revisão.")


if __name__ == "__main__":
    main()
