"""
narratives/phrase_validator.py — validação de associação completa (seção 3
da revisão de 2026-08-06).

A checagem antiga (narrative_engine.verificar_numeros) só confirma que um
número aparece EM ALGUM LUGAR do dossiê — não verifica se está atribuído ao
lado certo (time analisado vs adversário), à direção certa (produzido vs
cedido) nem ao recorte certo (mesmo mando vs geral). Este módulo fecha esse
buraco para o caminho de IA, que é o único onde o erro pode acontecer de
verdade: o motor Python (_redigir_python) monta a frase lendo diretamente
dos dicionários certos por construção — não tem como ele confundir os
lados, porque cada metade da frase é montada por uma função que só recebe
UM dos dois dicionários (proprio OU adversario_fatos). Isso é verificado por
teste dedicado em tests/test_evidence_grounding.py, não por este validador.

Para o caminho de IA, o contrato mudou: cada parágrafo agora vem acompanhado
de "fatos_usados" — uma lista de {campo, sujeito} que a própria IA declara
ter usado. Este módulo confere:
  1. cada fato declarado existe de fato no dossiê, no lado (sujeito) certo;
  2. todo número que aparece no texto bate com o VALOR de algum fato
     declarado — não mais "qualquer número do dossiê inteiro";
  3. existe pelo menos um fato "proprio" e um "adversario" (regra 3 do
     prompt: todo parágrafo cruza os dois lados);
  4. o tom do texto não contradiz o veredito/eixo (regra 4/8 do prompt).
"""
from __future__ import annotations

import re

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")


def _formas_aceitas(valor) -> set[str]:
    formas = set()
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return formas
    if v == int(v):
        formas.add(str(int(v)))
    for casas in (0, 1, 2):
        s = f"{v:.{casas}f}"
        formas.add(s)
        formas.add(s.replace(".", ","))
    return formas


# ---------------------------------------------------------------------------
# 1/2/3 — ATRIBUIÇÃO: campo + sujeito + presença dos dois lados
# ---------------------------------------------------------------------------

def checar_atribuicao(fatos_usados: list[dict], dossie: dict) -> tuple[list[str], set[str]]:
    """
    Retorna (problemas, valores_autorizados). valores_autorizados só contém
    as formas numéricas dos fatos que passaram na checagem — é isso que
    checar_numeros_no_texto() usa, não o dossiê inteiro.
    """
    problemas: list[str] = []
    autorizados: set[str] = set()
    sujeitos_vistos = set()

    if not fatos_usados:
        return (["nenhum fato declarado (fatos_usados vazio ou ausente)"], autorizados)

    for f in fatos_usados:
        campo, sujeito = f.get("campo"), f.get("sujeito")
        if sujeito not in ("proprio", "adversario"):
            problemas.append(f"sujeito inválido: {sujeito!r} (campo {campo!r})")
            continue
        fonte = dossie.get("proprio" if sujeito == "proprio" else "adversario_fatos", {})
        if campo not in fonte:
            problemas.append(f"campo {campo!r} não existe no lado {sujeito!r} do dossiê")
            continue
        sujeitos_vistos.add(sujeito)
        autorizados |= _formas_aceitas(fonte[campo])

    if "proprio" not in sujeitos_vistos:
        problemas.append("nenhum fato do próprio time declarado — regra 3 exige cruzar os dois lados")
    if "adversario" not in sujeitos_vistos:
        problemas.append("nenhum fato do adversário declarado — regra 3 exige cruzar os dois lados")

    return problemas, autorizados


def checar_numeros_no_texto(texto: str, autorizados: set[str], dossie: dict) -> list[str]:
    """Todo número do texto precisa bater com um fato DECLARADO E VALIDADO — não com o dossiê inteiro."""
    texto_sem_nomes = texto
    for nome in (dossie.get("time"), dossie.get("adversario")):
        if nome:
            texto_sem_nomes = texto_sem_nomes.replace(nome, " ")

    inteiros_livres = set(range(0, 12))
    suspeitos = []
    for m in _NUM_RE.finditer(texto_sem_nomes):
        bruto = m.group()
        norm = bruto.replace(",", ".")
        if bruto in autorizados or norm in autorizados:
            continue
        try:
            v = float(norm)
        except ValueError:
            continue
        if v == int(v) and int(v) in inteiros_livres:
            continue
        suspeitos.append(f"número {bruto!r} sem fato declarado que o sustente")
    return suspeitos


# ---------------------------------------------------------------------------
# 4 — TOM vs VEREDITO / EIXO
# ---------------------------------------------------------------------------

_LINGUAGEM_PROMESSA_GOL = (
    "vai marcar", "vai balançar", "balançar a rede", "gol provável", "tende a marcar",
    "deve marcar", "vai fazer gol", "gol garantido", "marca com facilidade",
)

_LINGUAGEM_CONFIRMATORIA = (
    "favorável", "propício", "consistente", "seguro", "sólido", "confortável",
)

_LINGUAGEM_RESSALVA = ("porém", "entretanto", "contudo", "no entanto", "apesar")

_LINGUAGEM_ALTA_EXIGENCIA = ("alta exigência", "exigência real", "dificuldade real", "confronto duro")


def checar_tom_veredito(texto: str, eixo: str, veredito: str) -> list[str]:
    """
    Regra 4 do prompt: o eixo ofensivo nunca promete gol (confiabilidade
    baixa, medida no backtest — AUC~0,60, diferença dentro do IC95 contra a
    baseline). Regra 8: o veredito define o tom, então ALTA_EXIGENCIA não
    pode soar confirmatório e MUITO_FAVORAVEL/FAVORAVEL não pode soar cheio
    de ressalva sem nenhum sinal de confiança.
    """
    problemas = []
    baixo = texto.lower()

    if eixo == "ofensivo":
        achados = [p for p in _LINGUAGEM_PROMESSA_GOL if p in baixo]
        if achados:
            problemas.append(f"eixo ofensivo promete gol (proibido): {achados}")

    if veredito == "ALTA_EXIGENCIA":
        confirma_demais = [p for p in _LINGUAGEM_CONFIRMATORIA if p in baixo]
        tem_alerta = any(p in baixo for p in _LINGUAGEM_ALTA_EXIGENCIA) or "porém" in baixo or "mas" in baixo
        if confirma_demais and not tem_alerta:
            problemas.append(
                f"veredito ALTA_EXIGENCIA mas o texto usa linguagem confirmatória sem "
                f"nenhuma ressalva: {confirma_demais}"
            )

    if veredito in ("MUITO_FAVORAVEL", "FAVORAVEL"):
        tem_confirmacao = any(p in baixo for p in _LINGUAGEM_CONFIRMATORIA) or "cruzamento" in baixo
        if not tem_confirmacao:
            problemas.append(
                f"veredito {veredito} mas o texto não usa nenhuma linguagem confirmatória"
            )

    return problemas


# ---------------------------------------------------------------------------
# 6/13 — FRASES BANIDAS (clichê / linguagem de IA genérica)
# ---------------------------------------------------------------------------

FRASES_BANIDAS = (
    "vale destacar", "é importante ressaltar", "é válido mencionar",
    "nesse contexto", "neste contexto", "diante desse cenário", "diante deste cenário",
    "surge como", "se apresenta como", "desponta", "vem demonstrando",
    "potencializa ainda mais", "potencializa", "pode ser um fator determinante",
    "fator determinante", "não apenas", "não é apenas",
)


def checar_frases_banidas(texto: str) -> list[str]:
    baixo = texto.lower()
    return [f for f in FRASES_BANIDAS if f in baixo]


# ---------------------------------------------------------------------------
# ENTRADA ÚNICA
# ---------------------------------------------------------------------------

def validar_paragrafo_ia(texto: str, fatos_usados: list[dict], dossie: dict) -> list[str]:
    """Todas as checagens de um parágrafo vindo de IA. Lista vazia = aprovado."""
    problemas, autorizados = checar_atribuicao(fatos_usados, dossie)
    problemas += checar_numeros_no_texto(texto, autorizados, dossie)
    problemas += checar_tom_veredito(texto, dossie.get("eixo", ""), dossie.get("veredito", ""))
    problemas += [f"frase banida: {p!r}" for p in checar_frases_banidas(texto)]
    return problemas


def validar_paragrafo_fallback(texto: str, dossie: dict) -> list[str]:
    """
    O motor Python é correto por construção quanto a ATRIBUIÇÃO (ver docstring
    do módulo) — aqui só checa tom/veredito e frases banidas, que são
    propriedades de REDAÇÃO, não de origem do dado.
    """
    problemas = checar_tom_veredito(texto, dossie.get("eixo", ""), dossie.get("veredito", ""))
    problemas += [f"frase banida: {p!r}" for p in checar_frases_banidas(texto)]
    return problemas
