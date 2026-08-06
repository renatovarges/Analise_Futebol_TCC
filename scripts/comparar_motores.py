"""
scripts/comparar_motores.py — comparação em modo espelho, motor antigo x novo
(seção 9 da revisão de 2026-08-06).

Roda analisar_rodada_legado() (z-score + potencialização, aposentado) e
analisar_rodada() (Poisson, produção) sobre as MESMAS rodadas já disputadas
da temporada atual, e compara contra o resultado real (gols marcados/sofridos
de verdade naquela rodada — já aconteceu, não é previsão).

Uso:
    python scripts/comparar_motores.py
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
warnings.filterwarnings("ignore")

import data_processor
import analytics_engine
from sofascore_api import fetch_all_matches

ARTIFACTS_DIR = BASE_DIR / "artifacts"
N_JOGOS, TIPO_FILTRO, TOP_N = 3, "POR_MANDO", 6


def _resultado_real(todos: list[dict], rodada: int) -> dict[str, dict]:
    """{time: {"gols": int, "sofridos": int}} para os jogos JÁ DISPUTADOS da rodada."""
    saida = {}
    for j in todos:
        if j["game_week"] != rodada or j["status"] != "complete":
            continue
        saida[j["home_name"]] = {"gols": j["home_goals"], "sofridos": j["away_goals"]}
        saida[j["away_name"]] = {"gols": j["away_goals"], "sofridos": j["home_goals"]}
    return saida


def _acerto_top_n(ranking: list[dict], resultado_real: dict, alvo: str, n: int) -> tuple[int, int]:
    top = ranking[:n]
    acertos = 0
    validos = 0
    for d in top:
        real = resultado_real.get(d["time"])
        if real is None:
            continue
        validos += 1
        if alvo == "2mais" and real["gols"] >= 2:
            acertos += 1
        elif alvo == "sg" and real["sofridos"] == 0:
            acertos += 1
    return acertos, validos


def main() -> None:
    todos = fetch_all_matches()
    rodadas_completas = sorted({j["game_week"] for j in todos if j["status"] == "complete"})
    # começa depois de ter histórico mínimo para os dois motores calcularem algo
    amostra = [r for r in rodadas_completas if r >= 8]

    linhas = []
    for r in amostra:
        confrontos = data_processor.get_confrontos_rodada(r)
        confrontos_completos = [c for c in confrontos if c["Status"] == "complete"]
        if len(confrontos_completos) < 3:
            continue
        try:
            novo = analytics_engine.analisar_rodada(confrontos, r, N_JOGOS, TIPO_FILTRO, top_n=TOP_N)
            antigo = analytics_engine.analisar_rodada_legado(confrontos, r, N_JOGOS, TIPO_FILTRO, top_n=TOP_N)
        except Exception as e:
            print(f"  rodada {r}: erro ({type(e).__name__}: {e}), pulando")
            continue

        real = _resultado_real(todos, r)

        linha = {"rodada": r}
        for eixo, alvo, chave_lista in (("ofensivo", "2mais", "todos_ofensivos"), ("defensivo", "sg", "todos_defensivos")):
            for n in (3, 5, 6):
                a_nov, v_nov = _acerto_top_n(novo[chave_lista], real, alvo, n)
                a_ant, v_ant = _acerto_top_n(antigo[chave_lista], real, alvo, n)
                linha[f"{eixo}_top{n}_novo"] = (a_nov, v_nov)
                linha[f"{eixo}_top{n}_antigo"] = (a_ant, v_ant)

        # principais mudanças de posição para o mesmo time no mesmo eixo
        mudancas = []
        for eixo, chave_lista in (("ofensivo", "todos_ofensivos"), ("defensivo", "todos_defensivos")):
            pos_novo = {d["time"]: d["posicao"] for d in novo[chave_lista]}
            pos_antigo = {d["time"]: d["posicao"] for d in antigo[chave_lista]}
            for time in pos_novo:
                if time in pos_antigo:
                    delta = pos_antigo[time] - pos_novo[time]
                    if abs(delta) >= 5:
                        mudancas.append({"time": time, "eixo": eixo,
                                         "pos_antigo": pos_antigo[time], "pos_novo": pos_novo[time]})
        linha["mudancas_grandes"] = mudancas
        linhas.append(linha)
        print(f"  rodada {r}: ok ({len(mudancas)} mudanças grandes de posição)")

    def _somar(chave):
        a = sum(l[chave][0] for l in linhas)
        v = sum(l[chave][1] for l in linhas)
        return a, v, round(a / v, 4) if v else None

    resumo = {"n_rodadas_comparadas": len(linhas), "rodadas": [l["rodada"] for l in linhas]}
    for eixo in ("ofensivo", "defensivo"):
        for n in (3, 5, 6):
            a_nov, v_nov, taxa_nov = _somar(f"{eixo}_top{n}_novo")
            a_ant, v_ant, taxa_ant = _somar(f"{eixo}_top{n}_antigo")
            resumo[f"{eixo}_top{n}"] = {
                "novo": {"acertos": a_nov, "n": v_nov, "taxa": taxa_nov},
                "antigo": {"acertos": a_ant, "n": v_ant, "taxa": taxa_ant},
            }

    total_mudancas = sum(len(l["mudancas_grandes"]) for l in linhas)
    resumo["total_mudancas_grandes_posicao"] = total_mudancas
    resumo["detalhe_por_rodada"] = linhas

    with (ARTIFACTS_DIR / "comparacao_motores.json").open("w", encoding="utf-8") as f:
        json.dump(resumo, f, ensure_ascii=False, indent=2)

    print(f"\n{len(linhas)} rodadas comparadas")
    for eixo in ("ofensivo", "defensivo"):
        for n in (3, 5, 6):
            d = resumo[f"{eixo}_top{n}"]
            print(f"  {eixo} top{n}: novo={d['novo']['taxa']} ({d['novo']['acertos']}/{d['novo']['n']})  "
                  f"antigo={d['antigo']['taxa']} ({d['antigo']['acertos']}/{d['antigo']['n']})")
    print(f"  mudanças grandes de posição (>=5): {total_mudancas}")
    print(f"\nSalvo em {ARTIFACTS_DIR / 'comparacao_motores.json'}")


if __name__ == "__main__":
    main()
