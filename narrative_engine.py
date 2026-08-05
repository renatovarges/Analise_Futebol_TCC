"""
narrative_engine.py — Camada 2: redação dos parágrafos.

Recebe os dossiês fechados do analytics_engine e devolve o texto. Três
implementações intercambiáveis:

    · openai   — usa a chave da OpenAI
    · claude   — usa a chave da Anthropic
    · python   — engine local, sem chave, sempre disponível

O dossiê é a única fonte de números. Depois da geração, verificar_numeros()
confere cada número do texto contra os fatos do dossiê e sinaliza qualquer
valor que não tenha origem nos dados.
"""
from __future__ import annotations

import json
import random
import re

# ---------------------------------------------------------------------------
# EXEMPLOS DE REFERÊNCIA
# ---------------------------------------------------------------------------
# Estes são os parágrafos escritos à mão pelo analista. São a definição de voz
# do material — vão para o prompt como referência de estilo, nunca de conteúdo.

EXEMPLOS_REFERENCIA = [
    "Apresenta um perfil defensivo consistente em casa, com 1,10 de XGA, apenas 2 gols "
    "sofridos e 22% de conversão cedida. O Remo, entretanto, marcou 5 gols fora e "
    "apresenta boa eficiência, tornando o SG possível, mas menos seguro do que os "
    "números isolados do Mirassol sugerem.",

    "Os números defensivos do Palmeiras são bons, mas são desafiados pelos bons números "
    "ofensivos do Vitória, que tem o maior número de gols marcados entre os mandantes "
    "nos últimos três jogos.",

    "Sofreu apenas 1 gol e conquistou dois SGs nos últimos três jogos fora, permitindo "
    "somente 9% de conversão aos adversários. O confronto, porém, é de alta exigência, "
    "porque o Internacional marcou 7 gols e produziu pelo menos 1,46 de xG em todas as "
    "partidas recentes em casa.",

    "Combina 1,71 de xG com 5 gols marcados e 42% de conversão em casa. O Bahia não "
    "conquistou SG fora, sofreu 6 gols e cedeu 6,3 chutes no alvo por partida, formando "
    "um cruzamento favorável ao ataque tricolor.",

    "Apresenta um dos cruzamentos ofensivos mais completos da rodada. Produziu mais de "
    "1,50 de xG em todos os jogos recentes em casa e enfrenta um Remo que cedeu mais de "
    "1,70 de xG em todas as partidas fora, além de permitir 6,7 chutes no alvo por jogo "
    "e não conquistar nenhum SG.",
]

INSTRUCOES = """Você é um analista de futebol especializado em Cartola FC. Escreve os \
parágrafos de destaque que acompanham a tabela de xG/xGA entregue a alunos de um curso \
de análise.

TAREFA
Para cada time do dossiê, escreva UM parágrafo de 2 a 3 frases explicando por que ele é \
destaque da rodada no eixo indicado (ofensivo ou defensivo).

REGRAS INEGOCIÁVEIS
1. Use SOMENTE números presentes no dossiê daquele time. Não calcule, não arredonde, não \
   estime, não infira. Se um número não está no dossiê, ele não existe.
2. Não invente contexto externo: nada de lesões, escalações, tabela, sequência de \
   vitórias, momento psicológico, técnico ou clássico. Só o que está no dossiê.
3. Todo parágrafo cruza os dois lados: os números do próprio time E os números do \
   adversário no eixo oposto. Um destaque ofensivo cita o ataque dele contra a defesa do \
   adversário; um destaque defensivo cita a defesa dele contra o ataque do adversário. \
   Nunca misture os eixos.
4. CALIBRE A PROMESSA À CONFIABILIDADE DO EIXO. Isto não é estilo, é honestidade:
   - Eixo DEFENSIVO (confiabilidade alta, validado em 10 rodadas): pode afirmar.
     "cenário favorável ao SG", "defesa consistente", "poucas chances cedidas".
   - Eixo OFENSIVO (confiabilidade baixa, diferença dentro da margem de erro):
     NUNCA prometa gol. Fale de CENÁRIO e de CRIAÇÃO DE CHANCES, não de
     resultado. Escreva "cruzamento favorável ao ataque", "cenário propício
     para criar", "encontra uma defesa vulnerável" — e nunca "vai marcar",
     "tende a balançar a rede" ou "gol provável".

5. EXPLIQUE O JARGÃO NA PRIMEIRA VEZ que usar, de forma curta e natural.
   "1,71 de xG (o equivalente a criar quase dois gols em chances claras)".
   Prefira "chances claras", "finalizações de dentro da área", "toques na área"
   a siglas. Use xGA no máximo uma vez por parágrafo, sempre com contexto.

6. NO MÁXIMO DOIS NÚMEROS POR FRASE. O material vira áudio, e quem ouve não
   retém três números seguidos. Se tiver três fatos, quebre em duas frases.

7. QUANDO O DOSSIÊ TROUXER, use o material que explica o COMO, não só o quanto:
   - "perigo_bola_parada_pct" alto: o time depende de bola parada
   - "perigo_contra_ataque_pct" alto: cria em transição
   - "sofre_bola_parada_pct" alto no adversário: vulnerabilidade explorável
   - "gols_evitados_goleiro" positivo: o goleiro está segurando acima do normal
     (atenção: isso pode estar mascarando uma defesa pior do que parece)
   Isso é o que diferencia análise de leitura de tabela.

8. O campo "veredito" define o tom do fechamento e é obrigatório respeitá-lo:
   - cruzamento muito favorável / favorável → tom confirmatório ("formando um cruzamento \
     favorável", "cenário claramente propício")
   - cruzamento equilibrado → tom neutro, sem promessa
   - bons números próprios, mas com ressalva → use adversativa ("entretanto", "porém") e \
     deixe claro que o confronto reduz a segurança dos números isolados
   - confronto de alta exigência → deixe explícito que o adversário impõe dificuldade real
9. Escreva em português do Brasil. Decimais com vírgula (1,71 e não 1.71).
10. Não abra o parágrafo com o nome do próprio time em destaque — ele já aparece no \
    card. Comece pelo verbo ou pelo perfil ("Combina...", "Apresenta...", "Sofreu...").
11. Varie a estrutura entre os parágrafos. Se todos abrirem igual, o material denuncia \
    automação. Alterne: perfil primeiro e veredito no fim; veredito primeiro e números \
    depois; consistência da série antes das médias.
12. Sem títulos, sem marcadores, sem emoji, sem aspas. Só o parágrafo corrido.

VOCABULÁRIO DO DOSSIÊ
- xg_medio / xga_medio: média por jogo no recorte
- gols / gols_sofridos: total no recorte
- conversao / conversao_cedida: gols por chute no alvo, em %
- chutes_alvo / chutes_alvo_cedidos: média por jogo
- clean_sheets: jogos sem sofrer gol (SG conquistado)
- jogos_sem_marcar: jogos em que não marcou
- xg_piso_todos: produziu MAIS QUE esse valor em TODOS os jogos do recorte
- xga_piso_todos: CEDEU mais que esse valor em TODAS as partidas (fragilidade constante)
- xga_teto_todos: NÃO cedeu mais que esse valor em nenhum jogo (solidez constante)
- superlativos: liderança real dentro do grupo de mando na rodada — use quando houver, \
  é o que faz o texto soar como análise

EXEMPLOS DE VOZ (referência de estilo, não de conteúdo — os números abaixo são de outra \
rodada e não devem ser reaproveitados):
""" + "\n\n".join(f"— {e}" for e in EXEMPLOS_REFERENCIA) + """

SAÍDA
Responda em JSON: {"paragrafos": [{"chave": "<chave do dossiê>", "texto": "<parágrafo>"}]}
Um item por time do dossiê, na mesma ordem."""


# ---------------------------------------------------------------------------
# PREPARAÇÃO DO DOSSIÊ PARA O MODELO
# ---------------------------------------------------------------------------

def chave_dossie(d: dict) -> str:
    return f"{d['eixo']}|{d['time']}"


def _enxugar(d: dict) -> dict:
    """Versão compacta do dossiê — só o que a redação precisa ver."""
    return {
        "chave":       chave_dossie(d),
        "time":        d["time"],
        "eixo":        d["eixo"],
        "posicao_ranking": d["posicao"],
        "mando":       d["mando"],
        "adversario":  d["adversario"],
        "mando_adversario": d["mando_adversario"],
        "veredito":    d["veredito_texto"],
        "numeros_proprios":    d["proprio"],
        "numeros_adversario":  d["adversario_fatos"],
        "superlativos":            [s["texto"] for s in d["superlativos"]],
        "superlativos_adversario": [s["texto"] for s in d["superlativos_adversario"]],
        # por que o time está nesta posição — as três frentes da análise
        "razoes_da_posicao": d.get("razoes", []),
        "faixa": d.get("faixa_nome"),
    }


def montar_payload(analise: dict) -> list[dict]:
    """Dossiês dos destaques das duas listas, na ordem do ranking."""
    return [_enxugar(d) for d in analise["ranking_ofensivo"] + analise["ranking_defensivo"]]


# ---------------------------------------------------------------------------
# VERIFICADOR DE NÚMEROS
# ---------------------------------------------------------------------------

# Números pequenos aparecem naturalmente na prosa ("nos últimos três jogos",
# "2 gols"), então só cobramos origem de valores que parecem estatística.
_INTEIROS_LIVRES = set(range(0, 12))

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")


def _formas_aceitas(valor) -> set[str]:
    """Todas as grafias plausíveis de um valor numérico do dossiê."""
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


def _coletar_valores(obj, acc: set[str]) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            _coletar_valores(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _coletar_valores(v, acc)
    elif isinstance(obj, bool):
        return
    elif isinstance(obj, (int, float)):
        acc |= _formas_aceitas(obj)
    elif isinstance(obj, str):
        for m in _NUM_RE.finditer(obj):
            acc |= _formas_aceitas(m.group().replace(",", "."))


def verificar_numeros(texto: str, dossie: dict) -> list[str]:
    """
    Confere se todo número do parágrafo tem origem no dossiê.

    Devolve a lista de números sem origem. Lista vazia = texto auditado.
    """
    permitidos: set[str] = set()
    _coletar_valores(dossie.get("proprio", {}), permitidos)
    _coletar_valores(dossie.get("adversario_fatos", {}), permitidos)
    _coletar_valores(dossie.get("superlativos", []), permitidos)
    _coletar_valores(dossie.get("superlativos_adversario", []), permitidos)

    # Nome de clube não é alegação estatística. Sem isso, um time com dígito
    # no nome (Time12, Grêmio 1903) geraria alerta a cada parágrafo.
    for nome in (dossie.get("time"), dossie.get("adversario")):
        if nome:
            texto = texto.replace(nome, " ")

    suspeitos = []
    for m in _NUM_RE.finditer(texto):
        bruto = m.group()
        norm = bruto.replace(",", ".")
        if bruto in permitidos or norm in permitidos:
            continue
        try:
            f = float(norm)
        except ValueError:
            continue
        # inteiro pequeno em prosa comum não é alegação estatística
        if f == int(f) and int(f) in _INTEIROS_LIVRES:
            continue
        suspeitos.append(bruto)
    return suspeitos


# ---------------------------------------------------------------------------
# ENGINE PYTHON (sem API)
# ---------------------------------------------------------------------------

def _n(v: float, casas: int = 2) -> str:
    return f"{v:.{casas}f}".replace(".", ",")


_POR_EXTENSO = {1: "um", 2: "dois", 3: "três", 4: "quatro", 5: "cinco",
                6: "seis", 7: "sete", 8: "oito", 9: "nove", 10: "dez"}


def _mando(m: str) -> str:
    """'casa' → 'em casa'; 'fora' → 'fora de casa'."""
    return "em casa" if m == "casa" else "fora de casa"


def _gols(n: int) -> str:
    return f"{n} gol" if n == 1 else f"{n} gols"


def _gols_part(n: int, radical: str) -> str:
    """Concorda o particípio com o número: '1 gol marcado' / '5 gols marcados'."""
    return f"{n} gol {radical}o" if n == 1 else f"{n} gols {radical}os"


def _maiuscula(s: str) -> str:
    return s[0].upper() + s[1:] if s else s


# Os fragmentos vêm em duas naturezas, e misturá-las quebra a frase:
#   nominais — sintagmas que podem ser enfileirados ("1,71 de xG", "5 gols")
#   clausais — orações com verbo próprio, que exigem frase inteira
#              ("produziu mais de 1,50 de xG em todos os jogos")

def _perfil_ofensivo(f: dict) -> tuple[list[str], list[str]]:
    # Território primeiro: finalização de dentro da área e toque na área foram
    # os melhores preditores no backtest, e são mais concretos que sigla.
    nom = []
    if f.get("chutes_area"):
        nom.append(f"{_n(f['chutes_area'], 1)} finalizações de dentro da área por jogo")
    nom.append(f"{_n(f['xg_medio'])} de xG (o perigo criado por jogo)")
    if f.get("chutes_alvo"):
        nom.append(f"{_n(f['chutes_alvo'], 1)} chutes no alvo por jogo")
    if f.get("gols"):
        nom.append(_gols_part(f["gols"], "marcad"))
    if f.get("conversao"):
        nom.append(f"{f['conversao']}% de conversão")

    cla = []
    if f.get("xg_piso_todos"):
        cla.append(f"criou mais de {_n(f['xg_piso_todos'])} de xG "
                   f"em todos os jogos do recorte")
    if f.get("marcou_em_todos"):
        cla.append("marcou em todas as partidas do recorte")
    if (f.get("perigo_bola_parada_pct") or 0) >= 35:
        cla.append(f"tira {f['perigo_bola_parada_pct']}% do perigo que cria "
                   f"de bola parada")
    if (f.get("perigo_contra_ataque_pct") or 0) >= 25:
        cla.append(f"cria {f['perigo_contra_ataque_pct']}% do perigo em "
                   f"contra-ataque")
    return nom, cla


def _perfil_defensivo(f: dict) -> tuple[list[str], list[str]]:
    gs = f.get("gols_sofridos", 0)
    sofridos = _gols_part(gs, "sofrid")
    nom = [f"{_n(f['xga_medio'])} de xGA",
           f"apenas {sofridos}" if gs <= 2 else sofridos]
    cs = f.get("clean_sheets", 0)
    if cs:
        plural = "s" if cs > 1 else ""
        nom.append(f"{_POR_EXTENSO.get(cs, cs)} SG{plural} conquistado{plural}")
    if f.get("conversao_cedida"):
        nom.append(f"{f['conversao_cedida']}% de conversão cedida")
    if f.get("chutes_alvo_cedidos"):
        nom.append(f"{_n(f['chutes_alvo_cedidos'], 1)} chutes no alvo cedidos por partida")

    cla = []
    if f.get("xga_teto_todos"):
        cla.append(f"não cedeu mais de {_n(f['xga_teto_todos'])} de xG em nenhum jogo")
    if f.get("nao_sofreu_em_nenhum"):
        cla.append("não sofreu gol em nenhuma das partidas do recorte")
    if (f.get("sofre_bola_parada_pct") or 0) >= 35:
        cla.append(f"leva {f['sofre_bola_parada_pct']}% do perigo que sofre "
                   f"em bola parada")
    if (f.get("sofre_contra_ataque_pct") or 0) >= 25:
        cla.append(f"sofre {f['sofre_contra_ataque_pct']}% do perigo em transição")
    ge = f.get("gols_evitados_goleiro")
    if ge and ge >= 0.25:
        cla.append(f"tem sido segurado pelo goleiro, que evita {_n(ge)} gol "
                   f"por jogo acima do esperado")
    elif ge and ge <= -0.25:
        cla.append(f"vem sendo prejudicado pelo goleiro, {_n(abs(ge))} gol por "
                   f"jogo abaixo do esperado")
    return nom, cla


def _fragilidades_defensivas(f: dict) -> list[str]:
    """Orações sobre a defesa adversária — o que a torna vulnerável."""
    frs = []
    if f.get("xga_piso_todos"):
        frs.append(f"cedeu mais de {_n(f['xga_piso_todos'])} de xG em todas as partidas")
    if f.get("clean_sheets", 0) == 0:
        frs.append("não conquistou nenhum SG")
    if f.get("gols_sofridos"):
        frs.append(f"sofreu {_gols(f['gols_sofridos'])}")
    if f.get("chutes_alvo_cedidos"):
        frs.append(f"permitiu {_n(f['chutes_alvo_cedidos'], 1)} chutes no alvo por jogo")
    if f.get("conversao_cedida"):
        frs.append(f"viu os adversários converterem {f['conversao_cedida']}% das finalizações")
    return frs


def _ameacas_ofensivas(f: dict) -> list[str]:
    """Orações sobre o ataque adversário — o que o torna perigoso."""
    frs = []
    if f.get("xg_piso_todos"):
        frs.append(f"produziu pelo menos {_n(f['xg_piso_todos'])} de xG em todos os jogos")
    if f.get("gols"):
        frs.append(f"marcou {_gols(f['gols'])}")
    if f.get("conversao"):
        frs.append(f"converteu {f['conversao']}% dos chutes no alvo")
    if f.get("chutes_alvo"):
        frs.append(f"finalizou {_n(f['chutes_alvo'], 1)} vezes no alvo por partida")
    return frs


def _juntar(frs: list[str]) -> str:
    if not frs:
        return ""
    if len(frs) == 1:
        return frs[0]
    return ", ".join(frs[:-1]) + " e " + frs[-1]


_ABERTURAS_OF = [
    "Combina {frs} {mando}.",
    "Produz {frs} nos últimos jogos {mando}.",
    "Chega à rodada com {frs} {mando}.",
    "Reúne {frs} atuando {mando}.",
    "Sustenta {frs} no recorte {mando}.",
]
_ABERTURAS_DEF = [
    "Apresenta um perfil defensivo consistente {mando}, com {frs}.",
    "Registra {frs} {mando}.",
    "Vem de {frs} atuando {mando}.",
    "Mantém {frs} no recorte {mando}.",
    "Soma {frs} {mando}.",
]
# Quando existe fato de consistência, ele abre o parágrafo — é a construção
# mais forte, e é a que o analista usa nos exemplos de referência.
_ABERTURAS_CONSISTENCIA = [
    "{cla} {mando}, somando {frs}.",
    "{cla} {mando}. Soma ainda {frs}.",
    "{cla} {mando}, com {frs}.",
]
_ABERTURA_TOPO_OF = [
    "Apresenta um dos cruzamentos ofensivos mais completos da rodada.",
    "É um dos cruzamentos ofensivos mais completos entre os destaques da rodada.",
]
_ABERTURA_TOPO_DEF = [
    "Apresenta um dos cruzamentos defensivos mais seguros da rodada.",
    "É um dos cenários defensivos mais favoráveis entre os destaques da rodada.",
]

# Fechos separados por eixo. O defensivo pode afirmar — foi validado em 10
# rodadas (SG em 37% contra 17%). O ofensivo fala de CENÁRIO e de CRIAÇÃO,
# nunca de gol: a diferença medida ficou dentro da margem de erro, e prometer
# gol seria vender o que o modelo não entrega.
_FECHOS_OF = {
    "MUITO_FAVORAVEL": [
        "formando um dos cruzamentos ofensivos mais favoráveis da rodada.",
        "compondo um cenário propício para criar chances.",
    ],
    "FAVORAVEL": [
        "formando um cruzamento favorável ao ataque.",
        "o que desenha um cenário propício para criar.",
    ],
    "NEUTRO": [
        "o que mantém o confronto equilibrado.",
        "deixando o cenário em aberto.",
    ],
}
_FECHOS_DEF = {
    "MUITO_FAVORAVEL": [
        "formando um cenário claramente favorável ao SG.",
        "compondo um dos quadros defensivos mais seguros da rodada.",
    ],
    "FAVORAVEL": [
        "formando um cenário favorável ao SG.",
        "o que desenha um quadro defensivo propício.",
    ],
    "NEUTRO": [
        "o que mantém o confronto equilibrado.",
        "deixando o cenário em aberto.",
    ],
}


def _redigir_python(dossies: list[dict]) -> dict[str, str]:
    """Redação local, sem API. Determinística e auditável linha a linha."""
    saida = {}
    for d in dossies:
        rng = random.Random(f"{d['time']}|{d['eixo']}|{d['posicao']}")
        ofensivo = d["eixo"] == "ofensivo"
        prop, adv_f = d["proprio"], d["adversario_fatos"]
        adv, ver = d["adversario"], d["veredito"]
        mando_prop, mando_adv = _mando(prop["mando"]), _mando(adv_f["mando"])

        nominais, clausais = (_perfil_ofensivo(prop) if ofensivo
                              else _perfil_defensivo(prop))
        contra = (_fragilidades_defensivas(adv_f) if ofensivo
                  else _ameacas_ofensivas(adv_f))
        sup = [s["texto"] for s in d["superlativos"]]
        sup_adv = [s["texto"] for s in d["superlativos_adversario"]]

        # ── Abertura ───────────────────────────────────────────────────────
        topo = d["posicao"] <= 2 and ver in ("MUITO_FAVORAVEL", "FAVORAVEL")
        if topo:
            base = _ABERTURA_TOPO_OF if ofensivo else _ABERTURA_TOPO_DEF
            verbo = "Produz" if ofensivo else "Registra"
            f1 = (f"{rng.choice(base)} {verbo} "
                  f"{_juntar(nominais[:3])} {mando_prop}.")
        elif clausais and rng.random() < 0.7:
            f1 = rng.choice(_ABERTURAS_CONSISTENCIA).format(
                cla=_maiuscula(clausais[0]), mando=mando_prop,
                frs=_juntar(nominais[:2]),
            )
        else:
            moldes = _ABERTURAS_OF if ofensivo else _ABERTURAS_DEF
            f1 = rng.choice(moldes).format(
                frs=_juntar(nominais[:3]), mando=mando_prop
            )

        # O superlativo vira oração própria — pendurado por vírgula, parece
        # estar descrevendo o número anterior. No topo o parágrafo já tem
        # frases suficientes, então é omitido.
        if sup and not topo:
            # Evita repetir o verbo que já abriu o parágrafo.
            opcoes = [f"Tem ainda {sup[0]}.", f"Registra também {sup[0]}.",
                      f"É ainda o time com {sup[0]}."]
            primeiro = f1.split(maxsplit=1)[0].rstrip(".,")
            opcoes = [o for o in opcoes if not o.startswith(primeiro)] or opcoes
            f1 += " " + rng.choice(opcoes)

        # ── Cruzamento ─────────────────────────────────────────────────────
        trecho = _juntar(contra[:3])
        if sup_adv and rng.random() < 0.6:
            extra = f"tem {sup_adv[0]}"
            trecho = f"{trecho}, e {extra}" if trecho else extra

        if ver == "ALTA_EXIGENCIA":
            f2 = (f"O confronto, porém, é de alta exigência: o {adv} {trecho} "
                  f"{mando_adv}.")
        elif ver == "RESSALVA":
            alvo = "o cenário ofensivo" if ofensivo else "o SG"
            f2 = (f"O {adv}, entretanto, {trecho} {mando_adv}, tornando {alvo} "
                  f"possível, mas menos seguro do que os números isolados sugerem.")
        else:
            banco = _FECHOS_OF if ofensivo else _FECHOS_DEF
            fecho = rng.choice(banco.get(ver, banco["NEUTRO"]))
            f2 = f"O {adv} {trecho} {mando_adv}, {fecho}"

        saida[chave_dossie(d)] = f"{f1} {f2}"
    return saida


# ---------------------------------------------------------------------------
# ADAPTADORES DE API
# ---------------------------------------------------------------------------

_SCHEMA = {
    "type": "object",
    "properties": {
        "paragrafos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "chave": {"type": "string"},
                    "texto": {"type": "string"},
                },
                "required": ["chave", "texto"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["paragrafos"],
    "additionalProperties": False,
}


def _prompt_usuario(payload: list[dict], analise: dict) -> str:
    conf = analise.get("confiabilidade") or {}
    aviso = ""
    for eixo in ("defensivo", "ofensivo"):
        c = conf.get(eixo)
        if c:
            aviso += f"\n  · eixo {eixo}: confiabilidade {c['nivel'].upper()} — {c['texto']}"
    return (
        f"Rodada {analise['rodada']} do Brasileirão. As métricas combinam os "
        f"últimos {analise.get('janela_curta', 3)} jogos (peso maior) com os "
        f"últimos {analise.get('janela_longa', 10)}, sempre no mesmo mando.\n"
        f"\nCONFIABILIDADE MEDIDA (respeite ao calibrar as afirmações):{aviso}\n\n"
        f"Escreva um parágrafo para cada um dos {len(payload)} times abaixo.\n\n"
        f"DOSSIÊ:\n{json.dumps(payload, ensure_ascii=False, indent=1)}"
    )


def _parse(bruto: str) -> dict[str, str]:
    """Extrai o JSON da resposta, tolerando cercas de código."""
    txt = bruto.strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```(?:json)?\s*", "", txt)
        txt = re.sub(r"\s*```$", "", txt)
    dados = json.loads(txt)
    return {p["chave"]: p["texto"].strip() for p in dados["paragrafos"]}


def _e_incompativel_com_chat(e: Exception) -> bool:
    """
    A OpenAI tem dois endpoints. Os modelos mais recentes só atendem em
    /v1/responses e recusam /v1/chat/completions com 404 'not a chat model'.
    """
    msg = str(e).lower()
    return any(t in msg for t in (
        "not a chat model", "v1/responses", "not supported in the v1/chat",
        "use the responses api",
    ))


def _texto_da_resposta(r) -> str:
    """Extrai o texto de um objeto da Responses API."""
    texto = getattr(r, "output_text", None)
    if texto:
        return texto
    partes = []
    for item in getattr(r, "output", []) or []:
        for bloco in getattr(item, "content", []) or []:
            t = getattr(bloco, "text", None)
            if t:
                partes.append(t)
    return "".join(partes)


def _redigir_openai(payload, analise, api_key, modelo, timeout: float) -> dict[str, str]:
    from openai import OpenAI

    # max_retries=0 é essencial: o padrão do SDK é 2, então uma requisição
    # lenta viraria três esperas seguidas do tamanho do timeout, sem aviso
    # na tela. Aqui uma tentativa que estourar o tempo falha na hora e cai
    # para a engine Python.
    client = OpenAI(api_key=api_key, timeout=timeout, max_retries=0)
    prompt = _prompt_usuario(payload, analise)

    # Caminho 1: Chat Completions (modelos da linha gpt-4 e vários gpt-5).
    try:
        resp = client.chat.completions.create(
            model=modelo,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": INSTRUCOES},
                {"role": "user", "content": prompt},
            ],
        )
        return _parse(resp.choices[0].message.content)
    except Exception as e:
        if not _e_incompativel_com_chat(e):
            raise

    # Caminho 2: Responses API (modelos que só atendem lá).
    base = dict(model=modelo, instructions=INSTRUCOES, input=prompt,
                max_output_tokens=16000)
    try:
        r = client.responses.create(**base, text={"format": {"type": "json_object"}})
    except Exception:
        # SDK ou modelo sem suporte ao modo JSON — o formato já é pedido no
        # prompt e _parse() tolera cercas de código.
        r = client.responses.create(**base)
    return _parse(_texto_da_resposta(r))


def _redigir_claude(payload, analise, api_key, modelo, timeout: float) -> dict[str, str]:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=0)
    base = dict(
        model=modelo,
        max_tokens=16000,
        system=INSTRUCOES,
        messages=[{"role": "user", "content": _prompt_usuario(payload, analise)}],
    )
    try:
        # Saída estruturada: mais confiável, mas só existe em SDKs recentes.
        resp = client.messages.create(
            **base,
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": _SCHEMA},
            },
        )
    except TypeError:
        # SDK antigo não conhece output_config — o JSON é pedido no prompt e
        # _parse() tolera cercas de código.
        resp = client.messages.create(**base)

    if getattr(resp, "stop_reason", None) == "refusal":
        raise RuntimeError("A API recusou a requisição.")
    texto = next((b.text for b in resp.content if b.type == "text"), "")
    return _parse(texto)


# ---------------------------------------------------------------------------
# ENTRADA PRINCIPAL
# ---------------------------------------------------------------------------

MODELOS_PADRAO = {"openai": "gpt-4o", "claude": "claude-opus-5"}

# Famílias que não servem para redação (imagem, áudio, embeddings, etc.).
_NAO_TEXTO = (
    "embed", "tts", "whisper", "dall-e", "moderation", "audio", "realtime",
    "image", "transcribe", "search", "similarity", "davinci", "babbage",
    "ada", "curie", "codex", "sora", "guard",
    # -instruct é modelo de completação (endpoint legado v1/completions),
    # não de chat: recusa a requisição com 404.
    "instruct",
    # ponteiro móvel: o modelo por trás muda sem aviso e o estilo do texto
    # mudaria no meio da temporada.
    "chat-latest",
)


def listar_modelos(provedor: str, api_key: str) -> list[str]:
    """
    Pergunta à conta do usuário quais modelos ela tem liberados.

    Devolve apenas os que servem para gerar texto, do mais recente ao mais
    antigo. Levanta exceção se a chave for inválida — quem chama trata.
    """
    if provedor == "openai":
        from openai import OpenAI
        brutos = [(m.id, getattr(m, "created", 0)) for m in OpenAI(api_key=api_key).models.list()]
    elif provedor == "claude":
        import anthropic
        brutos = [(m.id, 0) for m in anthropic.Anthropic(api_key=api_key).models.list()]
    else:
        return []

    uteis = [(i, c) for i, c in brutos
             if not any(t in i.lower() for t in _NAO_TEXTO)]
    uteis.sort(key=lambda x: (-x[1], x[0]))
    return [i for i, _ in uteis]


TIMEOUT_PADRAO = 180.0   # segundos por tentativa


def gerar_paragrafos(
    analise: dict,
    provedor: str = "python",
    api_key: str | None = None,
    modelo: str | None = None,
    timeout: float = TIMEOUT_PADRAO,
) -> dict:
    """
    Redige os parágrafos dos destaques da rodada.

    Retorna:
        {
          "textos":     {chave: parágrafo},
          "alertas":    {chave: [números sem origem no dossiê]},
          "provedor_usado": str,
          "segundos":   float,        # quanto durou a geração
          "erro":       str | None,   # preenchido quando houve queda para o fallback
        }
    """
    import time

    dossies = analise["ranking_ofensivo"] + analise["ranking_defensivo"]
    payload = montar_payload(analise)
    erro = None
    usado = provedor
    t0 = time.monotonic()

    if provedor in ("openai", "claude") and api_key:
        fn = _redigir_openai if provedor == "openai" else _redigir_claude
        alvo = modelo or MODELOS_PADRAO[provedor]
        try:
            textos = fn(payload, analise, api_key, alvo, timeout)
            faltando = [chave_dossie(d) for d in dossies if not textos.get(chave_dossie(d))]
            if faltando:
                raise ValueError(f"resposta incompleta: {len(faltando)} parágrafo(s)")
        except Exception as e:
            gasto = time.monotonic() - t0
            if "timeout" in type(e).__name__.lower() or "timed out" in str(e).lower():
                erro = (f"[modelo: {alvo}] O modelo não respondeu em {gasto:.0f}s. "
                        f"Modelos '-pro' são bem mais lentos: aumente o limite de "
                        f"tempo na barra lateral ou escolha um modelo sem '-pro'.")
            else:
                erro = f"[modelo: {alvo}] {type(e).__name__}: {e}"
            textos = _redigir_python(dossies)
            usado = "python (fallback)"
    else:
        if provedor in ("openai", "claude"):
            erro = "Chave de API não informada."
            usado = "python (fallback)"
        textos = _redigir_python(dossies)

    alertas = {
        chave_dossie(d): verificar_numeros(textos.get(chave_dossie(d), ""), d)
        for d in dossies
    }
    return {"textos": textos, "alertas": alertas, "provedor_usado": usado,
            "segundos": round(time.monotonic() - t0, 1), "erro": erro}


# ---------------------------------------------------------------------------
# ROTEIRO DO ÁUDIO
# ---------------------------------------------------------------------------

def montar_roteiro(analise: dict, textos: dict[str, str]) -> str:
    """Texto corrido na ordem do ranking, para a gravação do áudio."""
    n = analise["n_jogos"]
    filtro = ("no mesmo mando" if analise["tipo_filtro"] == "POR_MANDO"
              else "independente do mando")
    linhas = [
        f"ANÁLISE DA RODADA {analise['rodada']}",
        f"Recorte: últimos {n} jogos de cada time, {filtro}.",
        "",
        "=" * 60,
        "MELHORES ATAQUES DA RODADA",
        "=" * 60,
        "",
    ]
    for d in analise["ranking_ofensivo"]:
        k = chave_dossie(d)
        linhas.append(f"{d['posicao']}º — {d['time'].upper()} ({d['mando']}) "
                      f"vs {d['adversario']}")
        linhas.append(textos.get(k, ""))
        linhas.append("")

    linhas += ["=" * 60, "MELHORES DEFESAS DA RODADA", "=" * 60, ""]
    for d in analise["ranking_defensivo"]:
        k = chave_dossie(d)
        linhas.append(f"{d['posicao']}º — {d['time'].upper()} ({d['mando']}) "
                      f"vs {d['adversario']}")
        linhas.append(textos.get(k, ""))
        linhas.append("")
    return "\n".join(linhas)
