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
    "Apresenta forte produção ofensiva em casa, com 1,85 de xG, 5,7 chutes no alvo e "
    "3,3 grandes chances por jogo, e enfrenta um São Paulo que cede 1,75 de xGA fora, "
    "sofreu 6 gols e ainda não teve SG. É um dos cruzamentos ofensivos mais completos "
    "da rodada.",

    "Marcou 8 gols nos últimos três jogos fora e produz 1,80 de xG por partida. O "
    "Grêmio, adversário, tem números defensivos sólidos — o destaque nasce "
    "principalmente da força ofensiva própria, não da fragilidade do rival.",

    "Sua produção ofensiva recente é apenas intermediária, com 1,10 de xG por jogo, mas "
    "enfrenta um Remo que sofreu 9 gols em casa, cede 70% de conversão e não teve SG no "
    "recorte. O destaque nasce principalmente da vulnerabilidade adversária.",

    "Cede apenas 0,78 de xG e 2,1 chutes no alvo por jogo em casa, contra um "
    "Internacional que marcou só 2 gols fora e produz 0,85 de xG. Um dos melhores "
    "cruzamentos da rodada para SG.",
]

INSTRUCOES = """Você é um analista técnico de futebol especializado em leitura de desempenho \
ofensivo e defensivo para Fantasy Game (Cartola FC), escrevendo os parágrafos de destaque \
que acompanham a tabela de xG/xGA entregue a alunos de um curso de análise.

SEU PAPEL
Seu trabalho NÃO é descrever os números da tabela — é fazer a leitura de analista: cruzar a \
força de um setor com a fragilidade (ou força) do adversário no eixo oposto, e explicar POR \
QUE este time está entre os destaques da rodada. Um leitor precisa entender o raciocínio só \
lendo o parágrafo, sem olhar a tabela.

COMO RACIOCINAR ANTES DE ESCREVER
Nível 1 — FORÇA PRÓPRIA: este time tem números fortes por mérito próprio no eixo analisado?
Nível 2 — ADVERSÁRIO: o rival no eixo oposto tem uma vulnerabilidade clara, ou impõe \
resistência real?
Nível 3 — O ARGUMENTO NÃO PRECISA SER PERFEITO. Três justificativas são igualmente válidas \
— escolha a que os números realmente sustentam:
  · CRUZAMENTO — força própria E fragilidade do adversário apontam na mesma direção (maior \
    confiança).
  · FORÇA PRÓPRIA — números de mérito próprio excepcionais, mesmo com adversário competente \
    ou sem números frágeis. Nunca descarte um destaque forte só porque o rival não é fraco.
  · FRAGILIDADE DO ADVERSÁRIO — números próprios apenas medianos, mas o rival é claramente \
    vulnerável no eixo oposto. O destaque nasce principalmente do adversário — deixe isso \
    explícito.
O campo "diagnostico_confronto" do dossiê já classificou isso: "convergencia" = cruzamento; \
"merito_proprio" = força própria; "oportunidade_pelo_adversario" = fragilidade do \
adversário; "dupla_limitacao" / "equilibrio_com_ressalva" = nenhum dos dois lados sustenta \
um destaque forte, escreva com ressalva. RESPEITE essa classificação — não decida sozinho \
olhando só a posição no ranking; "nivel_absoluto" (baixa/moderada/alta/muito_alta) define a \
intensidade do tom.

HIERARQUIA DE MÉTRICAS — nem todo número pesa igual, escolha os que melhor contam a história
- Ofensivo, em ordem: xg_medio (principal) > grandes_chances (chances realmente perigosas, \
  não é enfeite — diferencia dois ataques que finalizam igual mas criam chances desiguais) \
  > chutes_alvo (volume) > gols (resultado, varia muito em poucos jogos) > jogos_sem_marcar \
  (alerta se alto) > conversao (trate com cautela — muito alta pode ser insustentável, muito \
  baixa pode ser azar ou boa atuação do goleiro rival; nunca conclua força/fraqueza só por \
  ela, e sempre no contexto do volume de chutes).
- Defensivo, em ordem: xga_medio (principal) > grandes_chances_cedidas > \
  chutes_alvo_cedidos > gols_sofridos (resultado, pode divergir do processo) > clean_sheets \
  > conversao_cedida (mesma cautela do lado ofensivo).
- PROCESSO x RESULTADO: se gols_sofridos parecer discrepante do que xga_medio sugere, pode \
  mencionar essa divergência (processo melhor ou pior que o resultado recente) — não chame \
  uma defesa de sólida só porque sofreu poucos gols, nem de frágil só porque sofreu muitos, \
  sem checar se xGA confirma.

DENSIDADE DE NÚMEROS
Use de 2 a 5 números por parágrafo — os que melhor sustentam o argumento, não todos os \
disponíveis. Sempre pelo menos um número do PRÓPRIO time; inclua um ou mais do ADVERSÁRIO \
no eixo oposto sempre que isso reforçar o raciocínio (defesa dele, se o destaque é \
ofensivo; ataque dele, se é defensivo) — só descreva a fragilidade/força do adversário sem \
número quando o argumento do time já for FORÇA PRÓPRIA e isso deixar a frase mais limpa. \
Contagens pequenas soltas na prosa ("sofreu 3 gols", "não teve SG em 2 jogos") contam como \
fato corrido, não como uma das métricas principais do argumento.

REGRAS INEGOCIÁVEIS
1. Use SOMENTE números presentes no dossiê daquele time. Não calcule, não arredonde, não \
   estime, não infira. Se um número não está no dossiê, ele não existe.
2. Não invente contexto externo: nada de lesões, escalações, tabela, sequência de \
   vitórias, momento psicológico, técnico ou clássico, "grande fase", "vem crescendo". Só \
   o que está no dossiê. Prefira "apresenta bons números no recorte analisado" a qualquer \
   afirmação de tendência não comprovada pelos dados.
3. Um fator do PRÓPRIO time e, quando aplicável (ver DENSIDADE DE NÚMEROS acima), um fator \
   do ADVERSÁRIO no eixo oposto. Um destaque ofensivo cita o ataque dele contra a defesa do \
   adversário; um destaque defensivo cita a defesa dele contra o ataque do adversário. \
   Nunca misture os eixos.
4. TAMANHO: entre 30 e 70 palavras, em 1 a 3 frases. Denso e técnico, não telegráfico nem \
   inflado com números redundantes.
5. CALIBRE A PROMESSA À CONFIABILIDADE DO EIXO. Isto não é estilo, é honestidade — medido \
   por backtest real (AUC≈0,60 nos dois eixos, vantagem sobre a taxa-base pequena):
   - Eixo DEFENSIVO: pode falar em "cenário favorável para não sofrer gol", "boa \
     expectativa de SG", "sustenta o destaque", "um dos melhores cruzamentos da rodada \
     para SG" — nunca "SG garantido" ou "SG certo".
   - Eixo OFENSIVO: NUNCA prometa gol. Fale de CENÁRIO, PRODUÇÃO e ARGUMENTOS ESTATÍSTICOS, \
     não de resultado certo. Nunca "vai marcar", "tende a balançar a rede", "gol provável", \
     "gol garantido", "marca com facilidade", "não oferece risco".
6. NÃO EXPLIQUE O QUE É xG/xGA no parágrafo — a explicação já está na interface, uma vez \
   só, fora do texto. Escreva só "1,71 de xG", sem parênteses explicando o termo.
7. "SG" tem linguagem natural e pode variar: "não sofrer gol", "ter SG", "boa expectativa \
   de SG", "não teve SG", "conquistou SG", "ainda não conquistou SG" — todas são aceitáveis, \
   escolha a que soar menos repetitiva ao lado das outras frases da rodada.
8. O campo "veredito" define o tom do fechamento e é obrigatório respeitá-lo:
   - MUITO_FAVORAVEL / FAVORAVEL → tom confirmatório, mas SEM as frases banidas abaixo.
   - NEUTRO → tom neutro, sem promessa, confronto equilibrado.
   - RESSALVA → uma ressalva curta e natural (não "entretanto, tornando o cenário possível \
     mas menos seguro" — isso é longo demais; algo como "ainda assim, o adversário tem \
     números que pedem cautela").
   - ALTA_EXIGENCIA → deixe claro que o adversário impõe dificuldade real, em poucas palavras.
9. PROIBIDO, em qualquer frase: "vale destacar", "é importante ressaltar", "é válido \
   mencionar", "nesse contexto"/"neste contexto", "diante desse cenário", "surge como", \
   "se apresenta como", "desponta", "vem demonstrando", "potencializa", "fator \
   determinante", "não apenas", "não é apenas", "compondo um cenário propício", "SG \
   garantido", "não oferece risco" e qualquer variação genérica que sirva para qualquer time.
10. Escreva em português do Brasil. Decimais com vírgula (1,71 e não 1.71).
11. Não abra o parágrafo com o nome do próprio time em destaque — ele já aparece no \
    card. Comece pelo verbo, pelo número ou por "Diante de"/"Com"/"Contra".
12. Varie a estrutura entre os parágrafos — se dois times da mesma rodada abrirem com a \
    mesma construção, um controle automático detecta e substitui o parágrafo. Alterne \
    ordem (próprio primeiro vs. adversário primeiro), verbo de abertura e conector.
13. Sem títulos, sem marcadores, sem emoji, sem aspas. Só o parágrafo corrido.
14. NÃO USE GERUNDISMO. Evite construções com "vem + gerúndio", "está + gerúndio", "segue \
    + gerúndio" ou equivalentes. Prefira verbos diretos: "produz", "cede", "permite", \
    "cria", "impõe".
15. GOLEIRO x SG: não confunda "boa possibilidade de SG" com "boa possibilidade de \
    pontuação do goleiro em defesas". Se a defesa cede muitos chutes no alvo mas o \
    adversário converte pouco, é um cenário de potencial de defesas mesmo com SG incerto \
    — pode mencionar essa distinção quando os números do dossiê sustentarem.
16. Antes de finalizar cada parágrafo, confira mentalmente: a frase deixa claro se o \
    destaque é por CRUZAMENTO, FORÇA PRÓPRIA ou FRAGILIDADE DO ADVERSÁRIO? Consigo sustentar \
    cada número citado com um campo do dossiê? Não estou exagerando a certeza?

17. Além do parágrafo, declare em "fatos_usados" QUAIS campos do dossiê você usou e de
    QUE LADO cada um veio: "sujeito":"proprio" para números do dicionário "numeros_proprios"
    do time analisado, "sujeito":"adversario" para números de "numeros_adversario". Declare
    só os campos cujo VALOR realmente aparece escrito no parágrafo. Um validador automático
    confere cada declaração contra o dossiê, o tamanho, a contagem de números e as frases
    banidas — falha em qualquer checagem derruba o parágrafo e ele é substituído por um
    parágrafo determinístico.

VOCABULÁRIO DO DOSSIÊ
- xg_medio / xga_medio: média por jogo no recorte
- gols / gols_sofridos: total no recorte
- conversao / conversao_cedida: gols por chute no alvo, em %
- chutes_alvo / chutes_alvo_cedidos: média por jogo
- grandes_chances / grandes_chances_cedidas: média de oportunidades claras por jogo
- clean_sheets: jogos sem sofrer gol (SG conquistado)
- jogos_sem_marcar: jogos em que não marcou
- xg_piso_todos: produziu MAIS QUE esse valor em TODOS os jogos do recorte
- xga_piso_todos: CEDEU mais que esse valor em TODAS as partidas (fragilidade constante)
- xga_teto_todos: NÃO cedeu mais que esse valor em nenhum jogo (solidez constante)
- gols_evitados_goleiro: defesas do goleiro acima (+) ou abaixo (-) do esperado por jogo
- superlativos: liderança real dentro do grupo de mando na rodada — use quando houver, \
  é o que faz o texto soar como análise

EXEMPLOS DE VOZ (referência de estilo, não de conteúdo — os números abaixo são de outra \
rodada e não devem ser reaproveitados):
""" + "\n\n".join(f"— {e}" for e in EXEMPLOS_REFERENCIA) + """

SAÍDA
Responda em JSON:
{"paragrafos": [{"chave": "<chave do dossiê>", "texto": "<parágrafo>",
                 "fatos_usados": [{"campo": "<chave em numeros_proprios ou numeros_adversario>",
                                    "sujeito": "proprio ou adversario"}]}]}
Um item por time do dossiê, na mesma ordem. "fatos_usados" precisa ter pelo menos um
item "proprio"; inclua "adversario" sempre que o parágrafo citar um número do lado dele."""


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
        # Leitura anterior à redação: impede que o texto confunda posição no
        # ranking com força absoluta e identifica de onde nasce a expectativa.
        "diagnostico_confronto": d.get("diagnostico", {}),
        "probabilidade": d.get("probabilidade"),
        "faixa_expectativa": d.get("faixa_expectativa"),
        "confianca_modelo": d.get("confianca_modelo"),
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
    """
    Todas as grafias plausíveis de um valor numérico do dossiê.

    Inclui o valor absoluto: "gols_evitados_goleiro" negativo vira, na
    prosa, "0,51 gol por jogo ABAIXO do esperado" — o sinal já está na
    palavra "abaixo", repetir o "-" seria estranho. Sem isso, todo número
    negativo do dossiê disparava alerta de "sem origem" por engano.
    """
    formas = set()
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return formas
    for candidato in (v, abs(v)):
        if candidato == int(candidato):
            formas.add(str(int(candidato)))
        for casas in (0, 1, 2):
            s = f"{candidato:.{casas}f}"
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
#
# Reescrito em 2026-08-06 para o padrão compacto: no máximo duas métricas
# numéricas no total (uma do próprio time, uma opcional do adversário), no
# máximo duas frases curtas, 25-45 palavras. A explicação de "o que é xG"
# sai daqui — fica uma vez só na interface (app.py), não repetida em cada
# parágrafo. "Conquistar SG" vira "ter SG" / "não sofrer gol".
# ---------------------------------------------------------------------------

def _n(v: float, casas: int = 2) -> str:
    return f"{v:.{casas}f}".replace(".", ",")


def _mando(m: str) -> str:
    """'casa' → 'em casa'; 'fora' → 'fora de casa'."""
    return "em casa" if m == "casa" else "fora de casa"


def _maiuscula(s: str) -> str:
    return s[0].upper() + s[1:] if s else s


# ── Abertura: o único número do PRÓPRIO time ────────────────────────────────
_ABERTURAS_PROPRIO_OF = [
    "Produz {xg} de xG {mando}",
    "Chega com {xg} de xG {mando}",
    "Vem de {xg} de xG por jogo {mando}",
    "A produção de {xg} de xG {mando}",
    "Soma {xg} de xG {mando}",
]
_ABERTURAS_PROPRIO_DEF = [
    "Cede {xga} de xG por jogo {mando}",
    "Tem cedido {xga} de xG {mando}",
    "Segura a defesa em {xga} de xG cedido {mando}",
    "Vem permitindo {xga} de xG {mando}",
    "Mantém {xga} de xG cedido {mando}",
]

_CONECTORES = ["e enfrenta", "contra", "diante de", "e encara"]
_CONECTORES_ENCONTRA = ["encontra", "esbarra em", "tem pela frente"]


def _fator_adversario_of(adv_f: dict, rng: random.Random) -> str | None:
    """Uma fraqueza defensiva do adversário — com número, ou não (metade das vezes)."""
    numericos = []
    if adv_f.get("chutes_alvo_cedidos"):
        numericos.append(f"que permitiu {_n(adv_f['chutes_alvo_cedidos'], 1)} chutes no alvo por jogo")
    if adv_f.get("conversao_cedida"):
        numericos.append(f"que cedeu {adv_f['conversao_cedida']}% de conversão")
    if adv_f.get("gols_sofridos"):
        numericos.append(f"que sofreu {adv_f['gols_sofridos']} gols no recorte")
    qualitativos = [
        "que sofre bastante", "que cede espaço no último terço",
        "que tem levado sustos na defesa", "que ainda não achou solidez atrás",
    ]
    if adv_f.get("clean_sheets", 0) == 0:
        qualitativos.append("que não teve nenhum SG recente")
    if numericos and (not qualitativos or rng.random() < 0.5):
        return rng.choice(numericos)
    return rng.choice(qualitativos)


def _fator_adversario_def(adv_f: dict, rng: random.Random) -> str | None:
    """Uma ameaça ofensiva do adversário — com número, ou não (metade das vezes)."""
    numericos = []
    if adv_f.get("conversao"):
        numericos.append(f"que converteu {adv_f['conversao']}% dos chutes no alvo")
    if adv_f.get("chutes_alvo"):
        numericos.append(f"que finalizou {_n(adv_f['chutes_alvo'], 1)} vezes no alvo por jogo")
    if adv_f.get("gols"):
        numericos.append(f"que marcou {adv_f['gols']} gols no recorte")
    qualitativos = [
        "que cria bastante perigo", "que mostra eficiência na conclusão",
        "que chega embalado ofensivamente", "que tem levado perigo com frequência",
    ]
    if adv_f.get("gols", 0) >= 4:
        qualitativos.append("que balançou as redes com frequência")
    if numericos and (not qualitativos or rng.random() < 0.5):
        return rng.choice(numericos)
    return rng.choice(qualitativos)


# ── Fecho: sem número, tom preso ao veredito, sem clichê ────────────────────
_FECHOS_OF = {
    "MUITO_FAVORAVEL": [
        "É um dos cenários mais favoráveis da rodada para o ataque.",
        "Poucos confrontos são tão propícios para criar chances nesta rodada.",
        "O confronto reforça o {time} entre os destaques ofensivos da rodada.",
    ],
    "FAVORAVEL": [
        "O confronto mantém o {time} entre as boas expectativas ofensivas da rodada.",
        "O cenário ofensivo pesa a favor, mas dois gols não são certeza.",
        "É um dos cenários mais interessantes para o ataque nesta rodada.",
    ],
    "NEUTRO": [
        "O confronto é equilibrado, sem favorito claro para nenhum dos lados.",
        "Não há vantagem clara para nenhum dos lados aqui.",
    ],
    "RESSALVA": [
        "Ainda assim, o adversário tem números que pedem cautela.",
        "O cenário é positivo, mas o adversário reduz essa segurança.",
    ],
    "ALTA_EXIGENCIA": [
        "O adversário, porém, impõe um teste real para esse ataque.",
        "É um confronto de alta exigência para criar chances aqui.",
    ],
}
_FECHOS_DEF = {
    "MUITO_FAVORAVEL": [
        "É um dos cenários mais seguros da rodada para não sofrer gol.",
        "Poucos confrontos favorecem tanto o SG nesta rodada.",
        "O confronto reforça o {time} entre os destaques defensivos da rodada.",
    ],
    "FAVORAVEL": [
        "O cenário defensivo favorece o {time} na busca pelo SG.",
        "É um cenário favorável, embora sem garantia de SG.",
        "O confronto mantém o {time} entre as boas expectativas defensivas da rodada.",
    ],
    "NEUTRO": [
        "O confronto é equilibrado, sem garantia clara de SG.",
        "Não há vantagem clara para nenhum dos lados aqui.",
    ],
    "RESSALVA": [
        "Ainda assim, o ataque adversário tem números que pedem atenção.",
        "O cenário é positivo, mas o adversário reduz essa segurança.",
    ],
    "ALTA_EXIGENCIA": [
        "O ataque adversário, porém, impõe risco real a essa defesa.",
        "É um confronto de alta exigência para manter o SG aqui.",
    ],
}


def _redigir_python(dossies: list[dict]) -> dict[str, str]:
    """
    Redação local, sem API. Determinística e auditável linha a linha.

    Estrutura fixa: frase 1 funde o único número do próprio time com um
    fator do adversário (numérico ou não — nunca os dois numéricos fazem o
    texto passar de duas métricas); frase 2 fecha o tom conforme o veredito,
    sem repetir número nenhum.
    """
    saida = {}
    for d in dossies:
        rng = random.Random(f"{d['time']}|{d['eixo']}|{d['posicao']}")
        ofensivo = d["eixo"] == "ofensivo"
        prop, adv_f = d["proprio"], d["adversario_fatos"]
        adv, ver, time = d["adversario"], d["veredito"], d["time"]
        mando_prop, mando_adv = _mando(prop["mando"]), _mando(adv_f["mando"])

        # ── Frase 1 — próprio + adversário, no máximo 2 números ────────────
        # 4 esqueletos genuinamente diferentes (não só troca de verbo dentro
        # do mesmo molde) — precisa disso porque o controle de repetição
        # compara a frase com números e nomes mascarados: dois textos que só
        # trocam o verbo de abertura ficam com o MESMO esqueleto mascarado e
        # colidem sempre. Achado real ao testar a rodada 20 (2026-08-06):
        # similaridade de até 1,00 entre times diferentes com só 2 moldes.
        fator_adv = (_fator_adversario_of(adv_f, rng) if ofensivo
                     else _fator_adversario_def(adv_f, rng))
        xg_ou_xga = _n(prop["xg_medio"] if ofensivo else prop["xga_medio"])
        verbo_proprio = "de xG" if ofensivo else "de xG cedido"
        artigo_defesa = "uma defesa do" if ofensivo else "um ataque do"

        # Nota: fator_adv sempre começa com "que ..." (oração relativa) — só
        # pode ser encaixado depois de um substantivo (adv sozinho, ou
        # artigo_defesa+adv). Um esqueleto anterior colocava "que..." direto
        # após o nome do time sem verbo principal na oração — quebrava a
        # gramática (regressão pega ao testar a rodada 20, corrigida aqui).
        esqueleto = rng.randrange(5)
        if esqueleto == 0:
            abertura = rng.choice(_ABERTURAS_PROPRIO_OF if ofensivo else _ABERTURAS_PROPRIO_DEF)
            abertura = abertura.format(xg=xg_ou_xga, xga=xg_ou_xga, mando=mando_prop)
            conector = rng.choice(_CONECTORES)
            f1 = f"{abertura} {conector} um {adv} {fator_adv} {mando_adv}."
        elif esqueleto == 1:
            f1 = (f"{_maiuscula(artigo_defesa)} {adv} {fator_adv} {mando_adv}, mas o {time} "
                  f"soma {xg_ou_xga} {verbo_proprio} {mando_prop}.")
        elif esqueleto == 2:
            f1 = (f"Diante de um {adv} {fator_adv} {mando_adv}, o {time} chega com "
                  f"{xg_ou_xga} {verbo_proprio} {mando_prop}.")
        elif esqueleto == 3:
            f1 = (f"Com {xg_ou_xga} {verbo_proprio} {mando_prop}, o {time} "
                  f"{rng.choice(_CONECTORES_ENCONTRA)} {artigo_defesa} {adv} "
                  f"{fator_adv} {mando_adv}.")
        else:
            f1 = (f"O {time} soma {xg_ou_xga} {verbo_proprio} {mando_prop}, num confronto "
                  f"contra um {adv} {fator_adv} {mando_adv}.")
        f1 = _maiuscula(f1)

        # ── Frase 2 — fecho por veredito, sem número ────────────────────────
        banco = _FECHOS_OF if ofensivo else _FECHOS_DEF
        fecho = rng.choice(banco.get(ver, banco["NEUTRO"]))
        f2 = fecho.format(time=time)

        saida[chave_dossie(d)] = f"{f1} {f2}"
    return saida


# Guarda a implementação anterior apenas para auditoria. A definição abaixo
# passa a ser o motor de produção e elimina a escolha aleatória de evidência.
_redigir_python_aleatorio = _redigir_python


def _leitura_padrao(d: dict) -> dict:
    """Compatibilidade com dossiês antigos e testes sintéticos."""
    diag = d.get("diagnostico") or {}
    if diag:
        return diag
    ver = d.get("veredito", "NEUTRO")
    return {
        "forca_propria": "favoravel" if ver in ("MUITO_FAVORAVEL", "FAVORAVEL") else "neutro",
        "efeito_adversario": "desfavoravel" if ver in ("RESSALVA", "ALTA_EXIGENCIA") else "neutro",
        "origem_expectativa": "merito_proprio" if ver in ("MUITO_FAVORAVEL", "FAVORAVEL") else "equilibrio_com_ressalva",
        "nivel_absoluto": "alta" if ver == "MUITO_FAVORAVEL" else "moderada",
    }


def _descricao_propria(eixo: str, nivel: str) -> str:
    if eixo == "ofensivo":
        return {
            "favoravel": "a produção própria pesa a favor",
            "neutro": "a produção própria fica próxima do padrão",
            "desfavoravel": "a produção própria limita a projeção",
        }[nivel]
    return {
        "favoravel": "a solidez própria pesa a favor",
        "neutro": "o desempenho defensivo fica próximo do padrão",
        "desfavoravel": "a defesa própria limita a segurança",
    }[nivel]


def _descricao_adversario(eixo: str, efeito: str, adversario: str) -> str:
    if eixo == "ofensivo":
        return {
            "favoravel": f"a defesa do {adversario} favorece a criação",
            "neutro": f"a defesa do {adversario} não produz desvio relevante",
            "desfavoravel": f"a defesa do {adversario} impõe resistência",
        }[efeito]
    return {
        "favoravel": f"o ataque do {adversario} oferece pouca pressão",
        "neutro": f"o ataque do {adversario} não produz desvio relevante",
        "desfavoravel": f"o ataque do {adversario} impõe risco",
    }[efeito]


def _conclusao_diagnostico(eixo: str, origem: str, nivel: str, efeito_adv: str) -> str:
    alta = nivel in ("alta", "muito_alta")
    if eixo == "ofensivo":
        textos = {
            "convergencia": ("Os dois lados sustentam uma expectativa ofensiva alta."
                              if alta else "Os dois lados favorecem o ataque, mas a expectativa absoluta ainda é moderada."),
            "merito_proprio": ("A expectativa nasce principalmente da força do próprio ataque, apesar da resistência rival."
                               if efeito_adv == "desfavoravel" else
                               "A expectativa nasce principalmente da força do próprio ataque, sem ajuda relevante do adversário."),
            "oportunidade_pelo_adversario": "A oportunidade nasce mais da fragilidade adversária do que da força do próprio ataque.",
            "dupla_limitacao": "A posição relativa na rodada não transforma este confronto em uma expectativa ofensiva forte.",
            "equilibrio_com_ressalva": "Os sinais se compensam e deixam uma expectativa ofensiva condicionada.",
        }
    else:
        textos = {
            "convergencia": ("Os dois lados sustentam uma expectativa alta de SG."
                              if alta else "Os dois lados favorecem o SG, mas a expectativa absoluta ainda é moderada."),
            "merito_proprio": ("A expectativa de SG nasce principalmente da solidez da própria defesa, apesar da exigência rival."
                               if efeito_adv == "desfavoravel" else
                               "A expectativa de SG nasce principalmente da solidez da própria defesa, sem ajuda relevante do adversário."),
            "oportunidade_pelo_adversario": "A oportunidade de SG nasce mais da limitação adversária do que da segurança da própria defesa.",
            "dupla_limitacao": "A posição relativa na rodada não transforma este confronto em um cenário defensivo seguro.",
            "equilibrio_com_ressalva": "Os sinais se compensam e deixam a expectativa de SG condicionada.",
        }
    return textos[origem]


def _evidencia_estrutural_defensiva(d: dict) -> str | None:
    """Escolhe a evidência de processo que mais favoreceu a defesa no modelo."""
    dec = d.get("decomposicao") or {}
    fatos = d["proprio"]
    candidatos = []
    regras = (
        ("grandes_chances_ced", "grandes_chances_cedidas", "{v} grandes chances cedidas por jogo"),
        ("sot_ced", "chutes_alvo_cedidos", "{v} chutes no alvo permitidos por jogo"),
        ("chutes_area_ced", "chutes_area_cedidos", "{v} finalizações na área cedidas por jogo"),
    )
    for prefixo, campo_fato, molde in regras:
        contribuicoes = [v for k, v in dec.items() if k.startswith(prefixo)]
        # No modelo de gols sofridos, contribuição negativa favorece a defesa.
        favor = -min(contribuicoes, default=0.0)
        if favor > 0 and fatos.get(campo_fato) is not None:
            candidatos.append((favor, molde.format(v=_n(fatos[campo_fato], 1))))
    return max(candidatos, default=(0, None), key=lambda x: x[0])[1]


def _redigir_python(dossies: list[dict]) -> dict[str, str]:
    """Redige a conclusão do diagnóstico, sem sortear a leitura dos dados."""
    saida = {}
    for d in dossies:
        eixo = d["eixo"]
        prop = d["proprio"]
        diag = _leitura_padrao(d)
        valor = _n(prop["xg_medio"] if eixo == "ofensivo" else prop["xga_medio"])
        metrica = "xG" if eixo == "ofensivo" else "xG cedido"
        mando = _mando(prop["mando"])
        proprio = _descricao_propria(eixo, diag["forca_propria"])
        adversario = _descricao_adversario(eixo, diag["efeito_adversario"], d["adversario"])
        evidencia = _evidencia_estrutural_defensiva(d) if eixo == "defensivo" else None
        apoio = f", com {evidencia}" if evidencia else ""
        f1 = f"Registra {valor} de {metrica} {mando}; {proprio}{apoio}, enquanto {adversario}."
        f2 = _conclusao_diagnostico(
            eixo, diag["origem_expectativa"], diag["nivel_absoluto"],
            diag["efeito_adversario"],
        )
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
                    "fatos_usados": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "campo": {"type": "string"},
                                "sujeito": {"type": "string", "enum": ["proprio", "adversario"]},
                            },
                            "required": ["campo", "sujeito"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["chave", "texto", "fatos_usados"],
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


def _parse(bruto: str) -> tuple[dict[str, str], dict[str, list[dict]]]:
    """Extrai o JSON da resposta, tolerando cercas de código."""
    txt = bruto.strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```(?:json)?\s*", "", txt)
        txt = re.sub(r"\s*```$", "", txt)
    dados = json.loads(txt)
    textos = {p["chave"]: p["texto"].strip() for p in dados["paragrafos"]}
    fatos = {p["chave"]: p.get("fatos_usados", []) for p in dados["paragrafos"]}
    return textos, fatos


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


def _redigir_openai(payload, analise, api_key, modelo, timeout: float) -> tuple[dict[str, str], dict[str, list]]:
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


def _redigir_claude(payload, analise, api_key, modelo, timeout: float) -> tuple[dict[str, str], dict[str, list]]:
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

    Cada parágrafo de IA é validado individualmente (atribuição completa,
    tom vs veredito, frases banidas — narratives/phrase_validator.py) e,
    fora do padrão, substituído SÓ NAQUELE ITEM pelo motor Python — não
    descarta a rodada inteira por causa de um parágrafo problemático.
    Depois disso, um controle de repetição (narratives/repetition_control.py)
    passa pela rodada inteira na ordem do ranking e tenta re-substituir por
    Python qualquer parágrafo de IA estruturalmente repetido.

    Retorna:
        {
          "textos":     {chave: parágrafo},
          "alertas":    {chave: [números sem origem no dossiê]},        # checagem antiga, mantida
          "problemas_ia": {chave: [motivos da substituição, se houve]},  # novo
          "repeticoes":  {chave: [avisos de repetição não resolvidos]},  # novo
          "fontes":      {chave: "ia" | "python (fallback item)" | "python"},
          "provedor_usado": str,
          "segundos":   float,
          "erro":       str | None,
        }
    """
    import time

    from narratives.phrase_validator import validar_paragrafo_ia, validar_paragrafo_fallback
    from narratives.repetition_control import ControleRepeticao

    dossies = analise["ranking_ofensivo"] + analise["ranking_defensivo"]
    payload = montar_payload(analise)
    erro = None
    usado = provedor
    t0 = time.monotonic()
    problemas_ia: dict[str, list[str]] = {}
    fontes: dict[str, str] = {}

    if provedor in ("openai", "claude") and api_key:
        fn = _redigir_openai if provedor == "openai" else _redigir_claude
        alvo = modelo or MODELOS_PADRAO[provedor]
        try:
            textos, fatos = fn(payload, analise, api_key, alvo, timeout)
            faltando = [chave_dossie(d) for d in dossies if not textos.get(chave_dossie(d))]
            if faltando:
                raise ValueError(f"resposta incompleta: {len(faltando)} parágrafo(s)")

            precisam_fallback = []
            for d in dossies:
                k = chave_dossie(d)
                probs = validar_paragrafo_ia(textos[k], fatos.get(k, []), d)
                if probs:
                    problemas_ia[k] = probs
                    precisam_fallback.append(d)
                else:
                    fontes[k] = "ia"

            if precisam_fallback:
                substitutos = _redigir_python(precisam_fallback)
                for d in precisam_fallback:
                    k = chave_dossie(d)
                    textos[k] = substitutos[k]
                    fontes[k] = "python (fallback item)"
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
            fontes = {chave_dossie(d): "python (fallback)" for d in dossies}
    else:
        if provedor in ("openai", "claude"):
            erro = "Chave de API não informada."
            usado = "python (fallback)"
        textos = _redigir_python(dossies)
        fontes = {chave_dossie(d): "python" for d in dossies}

    # controle de repetição: passa pela rodada inteira, na ordem do ranking,
    # e tenta trocar por Python qualquer item de IA que colidiu com um
    # anterior. Itens já vindos do Python só são reportados — recair no
    # mesmo motor não resolveria a colisão.
    controle = ControleRepeticao()
    repeticoes: dict[str, list[str]] = {}
    for d in dossies:
        k = chave_dossie(d)
        texto = textos.get(k, "")
        probs = controle.checar(k, texto, d["time"], d["adversario"])
        if probs and fontes.get(k) == "ia":
            substituto = _redigir_python([d])[k]
            probs_novo = controle.checar(k, substituto, d["time"], d["adversario"])
            textos[k] = substituto
            fontes[k] = "python (fallback repetição)"
            if probs_novo:
                repeticoes[k] = probs_novo
        elif probs:
            repeticoes[k] = probs
        controle.registrar(k, textos[k], d["time"], d["adversario"])

    # frases banidas / tom-vs-veredito, aplicado a TODO texto final,
    # independente da origem — rede de segurança final.
    for d in dossies:
        k = chave_dossie(d)
        extra = validar_paragrafo_fallback(textos[k], d)
        if extra:
            problemas_ia.setdefault(k, []).extend(extra)

    alertas = {
        chave_dossie(d): verificar_numeros(textos.get(chave_dossie(d), ""), d)
        for d in dossies
    }
    return {"textos": textos, "alertas": alertas, "problemas_ia": problemas_ia,
            "repeticoes": repeticoes, "fontes": fontes, "provedor_usado": usado,
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
