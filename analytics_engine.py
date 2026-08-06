"""
analytics_engine.py — camada de análise: dossiês, tabelas e ranking exibidos.

PRODUÇÃO: analisar_rodada() deriva o RANKING do modelo Poisson validado por
backtest walk-forward (modeling/prediction.py — ver artifacts/
evaluation_summary.json e artifacts/validacao_poisson.json para os números
reais e reproduzíveis). Este arquivo continua responsável por montar as
séries históricas, os superlativos descritivos e o dossiê que alimenta a
narrativa — só não decide mais a ORDEM do ranking nem o veredito por conta
própria.

AUDITORIA: analisar_rodada_legado() é o motor ANTIGO (z-score por pool da
própria rodada + termo de "potencialização" — produto dos z-scores quando
mesmo sinal, zero quando sinal oposto). Foi aposentado da produção em
2026-08-06 porque (a) a normalização só entre os ~10 mandantes/visitantes da
rodada é instável — um valor extremo de UM time deslocava o z-score de
TODOS os outros — e (b) a interação descontínua não tinha sustentação
estatística testável. Os números de desempenho abaixo descrevem ESSE motor
antigo, medidos quando ele ainda estava em produção — não descrevem
analisar_rodada() atual. Mantido só como baseline de comparação em
scripts/comparar_motores.py.

O QUE FOI MEDIDO DO MOTOR ANTIGO (Brasileirão 2026, 205 jogos, backtest
fora da amostra, ANTES da aposentadoria):

  · terço superior do ranking DEFENSIVO conquista SG em 34-39% dos jogos,
    contra 13-21% do terço inferior (média da liga: 25%).
  · terço superior do ranking OFENSIVO marca 1,20-1,44 gols contra 1,09-1,27
    do inferior (média 1,25).
  · gols marcados praticamente não preveem gols futuros (r≈0,02); métricas
    territoriais (toques e chutes na área) preveem melhor — motivo pelo
    qual o dataset do modelo novo (modeling/dataset_builder.py) também
    prioriza essas métricas territoriais nas features curadas.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from data_processor import _calcular_metricas
from sofascore_api import fetch_all_matches

# ---------------------------------------------------------------------------
# PARÂMETROS
# ---------------------------------------------------------------------------

JANELA_CURTA = 3      # o "momento"
JANELA_LONGA = 10     # o lastro
PESO_CURTA = 0.58     # momento pesa mais, mas não manda sozinho

# Pesos das métricas, proporcionais ao poder preditivo medido no backtest.
# Gol pesa pouco de propósito: gol passado quase não prevê gol futuro.
PESOS_ATAQUE = {
    "sot":      0.26,   # melhor preditor de GOL (+0,34 no teste de produto)
    "toques":   0.24,   # melhor preditor de xG (r=0,36)
    "area":     0.22,   # chutes de dentro da área
    "xg":       0.16,   # xG real do SofaScore
    "gols":     0.08,   # sinal fraco, mas é o objetivo do jogo
    "sem_marcar": -0.04,
}
PESOS_DEFESA = {
    "gs":        -0.26,  # melhor preditor de SG (+26pp)
    "xga":       -0.24,
    "sot_ced":   -0.20,
    "area_ced":  -0.18,
    "gc_ced":    -0.12,
}

# Composição do índice final. O terceiro termo é a potencialização.
#
# Recalibrado em 2026-08-05 por varredura em 4 temporadas (2023-2026, 79
# rodadas, ~1.600 casos), medindo o lift real do top 6 contra o resto nos
# alvos que o produto entrega (2+ gols no ataque, SG na defesa) — não mais
# contra xG. Duas tentativas de regressão logística (multivariada e por
# métrica isolada) pioraram os pesos INDIVIDUAIS das métricas em validação
# cruzada deixando uma temporada de fora — mantidos como estavam. Mas a
# varredura revelou que os dois eixos pedem uma composição DIFERENTE das
# três frentes, e isso sim melhorou:
#
#   eixo        só próprio   + cruzamento (mix testado)   ganho
#   ofensivo    +3,7pp       +12,1pp (0,35/0,30/0,35)     cruzamento é o motor
#   defensivo   +7,0pp       +9,0pp  (0,55/0,25/0,20)      próprio é o motor
#
# No ataque, força isolada quase não discrimina (2+ gols é raro e ruidoso);
# é o cruzamento com a fragilidade do adversário que separa o destaque real
# do time que só "parece" forte na tabela. Na defesa é o oposto: segurar SG
# depende sobretudo da própria solidez — o ataque adversário estar fraco
# ajuda pouco.
MIX_PROPRIO_OF, MIX_ADVERSARIO_OF, MIX_INTERACAO_OF = 0.35, 0.30, 0.35
MIX_PROPRIO_DEF, MIX_ADVERSARIO_DEF, MIX_INTERACAO_DEF = 0.55, 0.25, 0.20

K_CONVERSAO = 5.0
MAX_EMPATES_SUPERLATIVO = 1

# Diferença de índice abaixo da qual duas posições são indistinguíveis.
# Com ~210 amostras, diferenças menores que isso estão dentro do ruído.
LIMIAR_EMPATE_TECNICO = 0.12

LIMIAR_ADV_FRACO, LIMIAR_ADV_MEDIO, LIMIAR_ADV_FORTE = -0.50, 0.30, 0.90
LIMIAR_PROPRIO_ALTO = 0.80

VEREDITOS = {
    "MUITO_FAVORAVEL": "cruzamento muito favorável",
    "FAVORAVEL":       "cruzamento favorável",
    "NEUTRO":          "cruzamento equilibrado",
    "RESSALVA":        "bons números próprios, mas com ressalva no confronto",
    "ALTA_EXIGENCIA":  "confronto de alta exigência",
}


# ---------------------------------------------------------------------------
# EXTRAÇÃO POR JOGO
# ---------------------------------------------------------------------------

def _lado(j: dict, time: str) -> dict:
    """Um jogo na perspectiva de um time."""
    casa = j["home_name"] == time
    p, o = ("home", "away") if casa else ("away", "home")
    g = lambda k, pref: j.get(f"{pref}_{k}")
    gp = g("goals", p) or 0
    gs = g("goals", o) or 0
    return {
        "mando": "casa" if casa else "fora",
        "rodada": j.get("game_week", 0), "quando": j.get("date_unix", 0),
        "adv": j[f"{o}_name"], "placar": f"{gp}x{gs}",
        # ofensivo
        "gols": gp, "gols_sp": gp - (g("pen_goals", p) or 0),
        "xg": g("xg", p) or 0.0, "sot": g("sot", p) or 0,
        "area": g("shots_box", p) or 0, "toques": g("touches_box", p) or 0,
        "chutes": g("shots", p) or 0, "gc": g("big_chances", p) or 0,
        "sem_marcar": 1 if gp == 0 else 0,
        # de onde veio o perigo
        "xg_jogada": g("xg_jogada", p) or 0.0,
        "xg_parada": g("xg_bola_parada", p) or 0.0,
        "xg_contra": g("xg_contra_ataque", p) or 0.0,
        # defensivo
        "gs": gs, "xga": g("xg", o) or 0.0, "sot_ced": g("sot", o) or 0,
        "area_ced": g("shots_box", o) or 0, "gc_ced": g("big_chances", o) or 0,
        "sg": 1 if gs == 0 else 0,
        "xga_jogada": g("xg_jogada", o) or 0.0,
        "xga_parada": g("xg_bola_parada", o) or 0.0,
        "xga_contra": g("xg_contra_ataque", o) or 0.0,
        # goleiro
        "gols_evitados": g("goals_prevented", p) or 0.0,
    }


def _historico(time: str, rodada: int, mando: str, todos: list[dict]) -> list[dict]:
    """Jogos anteriores do time naquele mando, do mais antigo ao mais recente."""
    out = []
    for j in todos:
        if j["status"] != "complete" or j["game_week"] >= rodada:
            continue
        if mando == "casa" and j["home_name"] != time:
            continue
        if mando == "fora" and j["away_name"] != time:
            continue
        out.append(_lado(j, time))
    out.sort(key=lambda x: x["quando"])
    return out


# ---------------------------------------------------------------------------
# BASELINE DA LIGA — para a expectativa neutra do ajuste por adversário
# ---------------------------------------------------------------------------

def _baseline(rodada: int, todos: list[dict]) -> dict:
    """
    Força de cada time por mando, como razão contra a média da liga.
    1,00 = na média. 1,30 = 30% acima.
    """
    comp = [j for j in todos if j["status"] == "complete" and j["game_week"] < rodada]
    prod, ced = defaultdict(lambda: defaultdict(list)), defaultdict(lambda: defaultdict(list))
    for j in comp:
        h, a = j["home_name"], j["away_name"]
        hx, ax = j.get("home_xg") or 0.0, j.get("away_xg") or 0.0
        prod[h]["casa"].append(hx); ced[h]["casa"].append(ax)
        prod[a]["fora"].append(ax); ced[a]["fora"].append(hx)

    lig_casa = [j.get("home_xg") or 0.0 for j in comp]
    lig_fora = [j.get("away_xg") or 0.0 for j in comp]
    m_casa = sum(lig_casa) / max(1, len(lig_casa))
    m_fora = sum(lig_fora) / max(1, len(lig_fora))

    atk, dfs = {}, {}
    for t in set(prod) | set(ced):
        atk[t], dfs[t] = {}, {}
        for mando, base_p, base_c in (("casa", m_casa, m_fora), ("fora", m_fora, m_casa)):
            p, c = prod[t][mando], ced[t][mando]
            atk[t][mando] = (sum(p) / len(p) / base_p) if p and base_p else 1.0
            dfs[t][mando] = (sum(c) / len(c) / base_c) if c and base_c else 1.0
    return {"m_casa": m_casa, "m_fora": m_fora, "atk": atk, "def": dfs}


def _residuos(serie: list[dict], mando: str, b: dict) -> dict:
    """
    Quanto o time fez acima do que um time MÉDIO faria contra aqueles
    adversários. A expectativa é neutra de propósito: se ela usasse a força do
    próprio time, o resíduo mediria só "superou a si mesmo" e cancelaria
    justamente a qualidade que queremos medir.
    """
    ra, rd = [], []
    for g in serie:
        adv, m_adv = g["adv"], ("fora" if mando == "casa" else "casa")
        base_atk = b["m_casa"] if mando == "casa" else b["m_fora"]
        base_def = b["m_fora"] if mando == "casa" else b["m_casa"]
        esp_xg = base_atk * b["def"].get(adv, {}).get(m_adv, 1.0)
        esp_xga = base_def * b["atk"].get(adv, {}).get(m_adv, 1.0)
        ra.append(g["xg"] - esp_xg)
        rd.append(g["xga"] - esp_xga)
    n = max(1, len(ra))
    return {"atk": sum(ra) / n, "def": sum(rd) / n}


# ---------------------------------------------------------------------------
# PERFIL DO TIME
# ---------------------------------------------------------------------------

@dataclass
class Perfil:
    nome: str
    adversario: str
    mando: str
    serie: list[dict]
    stats: dict                      # métricas da tabela (compatibilidade)
    medias: dict = field(default_factory=dict)
    residuo: dict = field(default_factory=dict)
    z_ataque: float = 0.0
    z_defesa: float = 0.0
    confianca: float = 1.0
    superlativos_of: list = field(default_factory=list)
    superlativos_def: list = field(default_factory=list)

    @property
    def mando_plural(self):
        return "mandantes" if self.mando == "casa" else "visitantes"


def _media_janelas(serie: list[dict], chave: str) -> float:
    """Combina a janela curta (momento) com a longa (lastro)."""
    if not serie:
        return 0.0
    curta = serie[-JANELA_CURTA:]
    longa = serie[-JANELA_LONGA:]
    mc = sum(g[chave] for g in curta) / len(curta)
    ml = sum(g[chave] for g in longa) / len(longa)
    return PESO_CURTA * mc + (1 - PESO_CURTA) * ml


def _perfil_metricas(serie: list[dict]) -> dict:
    chaves = ["sot", "toques", "area", "xg", "gols", "sem_marcar", "chutes", "gc",
              "gs", "xga", "sot_ced", "area_ced", "gc_ced", "sg",
              "xg_jogada", "xg_parada", "xg_contra",
              "xga_jogada", "xga_parada", "xga_contra", "gols_evitados"]
    m = {k: _media_janelas(serie, k) for k in chaves}
    n = max(1, len(serie))
    ult = serie[-JANELA_CURTA:]
    nu = max(1, len(ult))
    # regularidade: repetir o padrão vale mais que um pico isolado
    m["freq_marcou"] = sum(1 for g in ult if g["gols"] > 0) / nu
    m["freq_sg"] = sum(1 for g in ult if g["sg"]) / nu
    m["freq_xg_alto"] = sum(1 for g in ult if g["xg"] >= 1.2) / nu
    m["freq_xga_baixo"] = sum(1 for g in ult if g["xga"] <= 1.0) / nu
    m["jogos"] = len(serie)
    m["jogos_recentes"] = len(ult)
    # de onde vem / por onde sofre
    tot_of = m["xg_jogada"] + m["xg_parada"] + m["xg_contra"]
    tot_df = m["xga_jogada"] + m["xga_parada"] + m["xga_contra"]
    m["pct_parada_of"] = m["xg_parada"] / tot_of if tot_of > 0.05 else 0.0
    m["pct_contra_of"] = m["xg_contra"] / tot_of if tot_of > 0.05 else 0.0
    m["pct_parada_def"] = m["xga_parada"] / tot_df if tot_df > 0.05 else 0.0
    m["pct_contra_def"] = m["xga_contra"] / tot_df if tot_df > 0.05 else 0.0
    return m


# ---------------------------------------------------------------------------
# Z-SCORES POR POOL DE MANDO
# ---------------------------------------------------------------------------

def _z(vals: list[float]) -> list[float]:
    n = len(vals)
    if n == 0:
        return []
    mu = sum(vals) / n
    dp = math.sqrt(sum((v - mu) ** 2 for v in vals) / n)
    return [0.0] * n if dp < 1e-9 else [(v - mu) / dp for v in vals]


_METRICAS_SUPERLATIVO = [
    ("sot", True, "of", "a maior média de chutes no alvo entre os {grupo}"),
    ("toques", True, "of", "o maior volume de toques na área entre os {grupo}"),
    ("area", True, "of", "o maior número de finalizações de dentro da área entre os {grupo}"),
    ("xg", True, "of", "o maior xG entre os {grupo}"),
    ("gols", True, "of", "o maior número de gols marcados entre os {grupo}"),
    ("xga", False, "def", "o menor xGA entre os {grupo}"),
    ("gs", False, "def", "o menor número de gols sofridos entre os {grupo}"),
    ("sot_ced", False, "def", "a menor média de chutes no alvo cedidos entre os {grupo}"),
    ("area_ced", False, "def", "o menor número de finalizações cedidas na área entre os {grupo}"),
    ("gc_ced", False, "def", "o menor número de grandes chances cedidas entre os {grupo}"),
]


def _calcular_pool(pool: list[Perfil], n_alvo: int) -> None:
    if not pool:
        return
    bruto = {}
    for chave in set(list(PESOS_ATAQUE) + list(PESOS_DEFESA)):
        bruto[chave] = [p.medias.get(chave, 0.0) for p in pool]
    z = {k: _z(v) for k, v in bruto.items()}

    # resíduo ajustado por adversário entra como reforço
    z_res_a = _z([p.residuo.get("atk", 0.0) for p in pool])
    z_res_d = _z([-p.residuo.get("def", 0.0) for p in pool])
    # regularidade entra como reforço
    z_reg_a = _z([p.medias.get("freq_xg_alto", 0.0) for p in pool])
    z_reg_d = _z([p.medias.get("freq_xga_baixo", 0.0) for p in pool])

    for i, p in enumerate(pool):
        p.confianca = min(1.0, math.sqrt(max(0, p.medias.get("jogos", 0)) / max(1, n_alvo)))
        base_a = sum(w * z[k][i] for k, w in PESOS_ATAQUE.items())
        base_d = sum(w * z[k][i] for k, w in PESOS_DEFESA.items())
        # 70% métricas brutas · 20% ajuste por adversário · 10% regularidade
        p.z_ataque = p.confianca * (0.70 * base_a + 0.20 * z_res_a[i] + 0.10 * z_reg_a[i])
        p.z_defesa = p.confianca * (0.70 * base_d + 0.20 * z_res_d[i] + 0.10 * z_reg_d[i])

    _marcar_superlativos(pool)


def _marcar_superlativos(pool: list[Perfil]) -> None:
    if len(pool) < 3:
        return
    grupo = pool[0].mando_plural
    for chave, maior, eixo, molde in _METRICAS_SUPERLATIVO:
        vals = [p.medias.get(chave, 0.0) for p in pool]
        alvo = max(vals) if maior else min(vals)
        lideres = [p for p in pool if abs(p.medias.get(chave, 0.0) - alvo) < 1e-9]
        if len(lideres) > MAX_EMPATES_SUPERLATIVO + 1:
            continue
        lideres = [p for p in lideres if p.confianca >= 0.99]
        for p in lideres:
            item = {"metrica": chave, "valor": round(alvo, 2),
                    "texto": molde.format(grupo=grupo),
                    "compartilhado": len(lideres) > 1}
            (p.superlativos_of if eixo == "of" else p.superlativos_def).append(item)


# ---------------------------------------------------------------------------
# CRUZAMENTO — a terceira frente
# ---------------------------------------------------------------------------

def _potencializacao(z_proprio: float, z_frag_adv: float) -> float:
    """
    Força e fraqueza que se potencializam mutuamente.

    Só é acionada quando as duas apontam para o mesmo lado:
      ataque forte × defesa frágil  -> soma mais que a soma (bônus)
      ataque fraco × defesa sólida  -> afunda mais que a soma (penalidade)
      forças opostas                -> zero, uma anula a outra
    """
    if z_proprio > 0 and z_frag_adv > 0:
        return z_proprio * z_frag_adv
    if z_proprio < 0 and z_frag_adv < 0:
        return -abs(z_proprio * z_frag_adv)
    return 0.0


def _classificar(z_proprio: float, z_adv_oposto: float) -> str:
    if z_adv_oposto > LIMIAR_ADV_FORTE:
        return "ALTA_EXIGENCIA"
    if z_adv_oposto > LIMIAR_ADV_MEDIO:
        return "RESSALVA"
    if z_adv_oposto <= LIMIAR_ADV_FRACO:
        return "MUITO_FAVORAVEL" if z_proprio >= LIMIAR_PROPRIO_ALTO else "FAVORAVEL"
    return "FAVORAVEL" if z_proprio >= LIMIAR_PROPRIO_ALTO else "NEUTRO"


@dataclass
class Cruzamento:
    atacante: Perfil
    defensor: Perfil
    indice_of: float
    indice_def: float
    decomp_of: dict
    decomp_def: dict
    veredito_of: str
    veredito_def: str


def _cruzar(atacante: Perfil, defensor: Perfil) -> Cruzamento:
    frag_def = -defensor.z_defesa          # fragilidade defensiva do adversário
    fraq_atk = -atacante.z_ataque          # fraqueza ofensiva do adversário

    pot_of = _potencializacao(atacante.z_ataque, frag_def)
    pot_def = _potencializacao(defensor.z_defesa, fraq_atk)

    d_of = {
        "proprio":   MIX_PROPRIO_OF * atacante.z_ataque,
        "adversario": MIX_ADVERSARIO_OF * frag_def,
        "potencializacao": MIX_INTERACAO_OF * pot_of,
    }
    d_def = {
        "proprio":   MIX_PROPRIO_DEF * defensor.z_defesa,
        "adversario": MIX_ADVERSARIO_DEF * fraq_atk,
        "potencializacao": MIX_INTERACAO_DEF * pot_def,
    }
    return Cruzamento(
        atacante=atacante, defensor=defensor,
        indice_of=sum(d_of.values()), indice_def=sum(d_def.values()),
        decomp_of=d_of, decomp_def=d_def,
        veredito_of=_classificar(atacante.z_ataque, defensor.z_defesa),
        veredito_def=_classificar(defensor.z_defesa, atacante.z_ataque),
    )


# ---------------------------------------------------------------------------
# RAZÕES — por que o time está nessa posição
# ---------------------------------------------------------------------------

def _motor_dominante(decomp: dict, eixo: str) -> str:
    """Qual das três frentes explica melhor a posição."""
    chave = max(decomp, key=lambda k: abs(decomp[k]))
    if chave == "potencializacao":
        return ("força própria e fragilidade do adversário se potencializam"
                if decomp[chave] > 0 else
                "fraqueza própria e solidez do adversário se somam contra")
    if chave == "proprio":
        forte = decomp[chave] > 0
        if eixo == "of":
            return "entra pelo próprio desempenho ofensivo" if forte \
                else "penalizado pelo próprio desempenho ofensivo"
        return "entra pelo próprio desempenho defensivo" if forte \
            else "penalizado pelo próprio desempenho defensivo"
    forte = decomp[chave] > 0
    if eixo == "of":
        return "entra principalmente pela fragilidade da defesa adversária" if forte \
            else "prejudicado pela solidez da defesa adversária"
    return "entra principalmente pela fraqueza do ataque adversário" if forte \
        else "prejudicado pela força do ataque adversário"


def _razoes(p: Perfil, adv: Perfil, decomp: dict, eixo: str) -> list[str]:
    """
    O que explica a posição, em linguagem de análise — não repetindo os
    números da decomposição, que já vão separados no dossiê.
    """
    out = [_motor_dominante(decomp, eixo)]
    m = p.medias
    if eixo == "of":
        if m.get("pct_parada_of", 0) >= 0.35:
            out.append(f"depende de bola parada ({m['pct_parada_of']*100:.0f}% do perigo criado)")
        if m.get("pct_contra_of", 0) >= 0.25:
            out.append(f"perigo vem muito de contra-ataque ({m['pct_contra_of']*100:.0f}%)")
        if m.get("freq_xg_alto", 0) >= 0.99:
            out.append("produziu volume alto de perigo em todos os jogos recentes")
        if adv.medias.get("pct_parada_def", 0) >= 0.35:
            out.append(f"adversário sofre muito em bola parada "
                       f"({adv.medias['pct_parada_def']*100:.0f}% do que cede)")
    else:
        if m.get("pct_parada_def", 0) >= 0.35:
            out.append(f"vulnerável em bola parada ({m['pct_parada_def']*100:.0f}% do que cede)")
        if m.get("pct_contra_def", 0) >= 0.25:
            out.append(f"sofre em transição ({m['pct_contra_def']*100:.0f}% em contra-ataque)")
        if m.get("freq_sg", 0) >= 0.66:
            out.append("segurou SG na maioria dos jogos recentes")
        ge = m.get("gols_evitados", 0.0)
        if ge >= 0.25:
            out.append(f"goleiro vem salvando acima do esperado (+{ge:.2f} gols evitados/jogo)")
        elif ge <= -0.25:
            out.append(f"goleiro vem abaixo do esperado ({ge:.2f} gols evitados/jogo)")
    return out


# ---------------------------------------------------------------------------
# DOSSIÊS
# ---------------------------------------------------------------------------

def _fatos_of(p: Perfil) -> dict:
    m, st = p.medias, p.stats
    f = {
        "xg_medio": round(m["xg"], 2), "gols": st["GP"],
        "conversao": round(st["CONV_CONQ"]),
        "chutes_alvo": round(m["sot"], 1),
        "chutes_area": round(m["area"], 1),
        "toques_area": round(m["toques"], 1),
        "grandes_chances": round(m["gc"], 1),
        "jogos_sem_marcar": st["SG_CED"], "jogos": st["Jogos"],
        "mando": p.mando,
    }
    if m.get("pct_parada_of"):
        f["perigo_bola_parada_pct"] = round(m["pct_parada_of"] * 100)
    if m.get("pct_contra_of"):
        f["perigo_contra_ataque_pct"] = round(m["pct_contra_of"] * 100)
    serie = [g["xg"] for g in p.serie[-JANELA_CURTA:]]
    if serie:
        piso = math.floor(min(serie) / 0.10) * 0.10
        if piso >= 0.80:
            f["xg_piso_todos"] = round(piso, 2)
    return f


def _fatos_def(p: Perfil) -> dict:
    m, st = p.medias, p.stats
    f = {
        "xga_medio": round(m["xga"], 2), "gols_sofridos": st["GS"],
        "conversao_cedida": round(st["CONV_CED"]),
        "chutes_alvo_cedidos": round(m["sot_ced"], 1),
        "chutes_area_cedidos": round(m["area_ced"], 1),
        "grandes_chances_cedidas": round(m["gc_ced"], 1),
        "clean_sheets": st["SG_CONQ"], "jogos": st["Jogos"], "mando": p.mando,
    }
    if m.get("pct_parada_def"):
        f["sofre_bola_parada_pct"] = round(m["pct_parada_def"] * 100)
    if m.get("pct_contra_def"):
        f["sofre_contra_ataque_pct"] = round(m["pct_contra_def"] * 100)
    ge = m.get("gols_evitados", 0.0)
    if abs(ge) >= 0.15:
        f["gols_evitados_goleiro"] = round(ge, 2)
    serie = [g["xga"] for g in p.serie[-JANELA_CURTA:]]
    if serie:
        teto = math.ceil(max(serie) / 0.10) * 0.10
        if teto <= 1.30:
            f["xga_teto_todos"] = round(teto, 2)
    return f


def _rotulos(p: Perfil) -> list[str]:
    return [f"{g['placar']} vs {g['adv']} (R{g['rodada']})"
            for g in p.serie[-JANELA_CURTA:]]


def _dossie(c: Cruzamento, pos: int, eixo: str) -> dict:
    if eixo == "ofensivo":
        p, adv, idx = c.atacante, c.defensor, c.indice_of
        decomp, ver = c.decomp_of, c.veredito_of
        proprio, adv_fatos = _fatos_of(p), _fatos_def(adv)
        sup, sup_adv = p.superlativos_of, adv.superlativos_def
    else:
        p, adv, idx = c.defensor, c.atacante, c.indice_def
        decomp, ver = c.decomp_def, c.veredito_def
        proprio, adv_fatos = _fatos_def(p), _fatos_of(adv)
        sup, sup_adv = p.superlativos_def, adv.superlativos_of
    return {
        "eixo": eixo, "posicao": pos, "time": p.nome, "adversario": adv.nome,
        "mando": p.mando, "mando_adversario": adv.mando,
        "indice": round(idx, 3), "veredito": ver, "veredito_texto": VEREDITOS[ver],
        "confianca": round(p.confianca, 2),
        "proprio": proprio, "adversario_fatos": adv_fatos,
        "superlativos": sup, "superlativos_adversario": sup_adv,
        "jogos_proprio": _rotulos(p), "jogos_adversario": _rotulos(adv),
        # novos: a explicação do ranking
        "decomposicao": {k: round(v, 3) for k, v in decomp.items()},
        "razoes": _razoes(p, adv, decomp, "of" if eixo == "ofensivo" else "def"),
    }


def _marcar_faixas(lista: list[dict]) -> None:
    """
    Agrupa o ranking em faixas de confiança.

    Com ~210 amostras de backtest, posições vizinhas quase sempre estão dentro
    do ruído — dizer "3º é melhor que 4º" seria falso rigor. Em vez de marcar
    pares empatados (o que marcaria quase tudo e não informaria nada), o
    ranking é cortado onde existe um salto real e cada time recebe a faixa a
    que pertence.
    """
    if not lista:
        return
    idx = [d["indice"] for d in lista]
    n = len(idx)
    media = sum(idx) / n
    dp = math.sqrt(sum((v - media) ** 2 for v in idx) / n) or 1.0
    # um salto só é real se for grande perto da dispersão de toda a rodada
    limiar = max(LIMIAR_EMPATE_TECNICO, 0.45 * dp)

    faixa, nomes = 1, ["destaque claro", "grupo intermediário", "grupo inferior"]
    for i, d in enumerate(lista):
        if i > 0 and (lista[i - 1]["indice"] - d["indice"]) >= limiar:
            faixa = min(faixa + 1, len(nomes))
        d["faixa"] = faixa
        d["faixa_nome"] = nomes[faixa - 1]
        # segue disponível para quem quiser o par a par
        viz = [abs(d["indice"] - lista[k]["indice"])
               for k in (i - 1, i + 1) if 0 <= k < n]
        d["empate_tecnico"] = min(viz, default=99) < limiar


# ---------------------------------------------------------------------------
# ENTRADA PRINCIPAL
# ---------------------------------------------------------------------------

# Confiabilidade do MODELO POISSON, medida por backtest walk-forward real em
# 4 temporadas (2023-2026), 126 rodadas, 2530 observações equipe-partida —
# ver artifacts/evaluation_summary.json e artifacts/validacao_poisson.json,
# reproduzíveis via scripts/run_backtest.py e scripts/validar_poisson.py.
#
# Honestidade obrigatória (revisão de 2026-08-06): a vantagem de calibração
# média do Poisson sobre uma baseline simples (taxa da liga por mando) é
# PEQUENA e NÃO passou no teste de significância a 95% — o intervalo de
# confiança da diferença de Brier Score inclui zero nos dois alvos. O que É
# real e mensurável é a capacidade de RANQUEAR: entre os 3/5/6 times mais
# bem colocados pelo modelo numa rodada, a taxa de acerto fica
# consistentemente acima da média da própria rodada.
CONFIABILIDADE = {
    "defensivo": {
        "nivel": "moderada",
        "texto": "Backtest walk-forward, 126 rodadas (2023-2026): entre os 3 times "
                 "mais bem colocados no ranking defensivo de cada rodada, a taxa de "
                 "SG fica cerca de 11 pontos percentuais acima da média da própria "
                 "rodada (top 5: +10pp; top 6: +10pp). A vantagem de calibração média "
                 "sobre a taxa-base da liga é pequena e não é estatisticamente "
                 "significativa a 95% — o modelo ajuda a ordenar quem tem cenário "
                 "mais favorável, não garante SG.",
    },
    "ofensivo": {
        "nivel": "moderada",
        "texto": "Backtest walk-forward, 126 rodadas (2023-2026): entre os 3 times "
                 "mais bem colocados no ranking ofensivo de cada rodada, a taxa de "
                 "2 ou mais gols fica cerca de 13 pontos percentuais acima da média "
                 "da própria rodada (top 5: +11pp; top 6: +10pp). A capacidade de "
                 "discriminação é limitada (AUC≈0,60) e a vantagem de calibração "
                 "média sobre a taxa-base da liga não é estatisticamente "
                 "significativa a 95% — o alvo é volume de gol, não marcar ao menos "
                 "uma vez.",
    },
}


def analisar_rodada_legado(confrontos: list[dict], rodada_num: int, n_jogos: int,
                           tipo_filtro: str, top_n: int = 6) -> dict:
    """
    Motor ORIGINAL (z-score + potencialização por sinal). Mantido só como
    baseline de auditoria (seção 9 da revisão de 2026-08-06) — comparação em
    modo espelho contra o modelo Poisson em scripts/comparar_motores.py. NÃO
    é chamado pela produção: app.py usa analisar_rodada(), que deriva o
    ranking do modelo preditivo validado por backtest.
    """
    top_n = max(5, min(7, top_n))
    todos = fetch_all_matches()
    base = _baseline(rodada_num, todos)

    mandantes, visitantes = [], []
    for c in confrontos:
        for nome, papel, mando, lista, adv in (
            (c["Mandante"], "home", "casa", mandantes, c["Visitante"]),
            (c["Visitante"], "away", "fora", visitantes, c["Mandante"]),
        ):
            st, _ = _calcular_metricas(nome, rodada_num, n_jogos, tipo_filtro, papel)
            serie = _historico(nome, rodada_num, mando, todos)
            if not serie:
                continue
            p = Perfil(nome=nome, adversario=adv, mando=mando, serie=serie, stats=st)
            p.medias = _perfil_metricas(serie)
            p.residuo = _residuos(serie[-JANELA_LONGA:], mando, base)
            lista.append(p)

    _calcular_pool(mandantes, JANELA_LONGA)
    _calcular_pool(visitantes, JANELA_LONGA)

    cruz = []
    for m in mandantes:
        v = next((x for x in visitantes if x.nome == m.adversario), None)
        if v:
            cruz.append(_cruzar(m, v))
            cruz.append(_cruzar(v, m))

    ofs = sorted(cruz, key=lambda c: -c.indice_of)
    defs = sorted(cruz, key=lambda c: -c.indice_def)
    todos_of = [_dossie(c, i + 1, "ofensivo") for i, c in enumerate(ofs)]
    todos_def = [_dossie(c, i + 1, "defensivo") for i, c in enumerate(defs)]
    _marcar_faixas(todos_of)
    _marcar_faixas(todos_def)

    return {
        "rodada": rodada_num, "n_jogos": n_jogos, "tipo_filtro": tipo_filtro,
        "janela_curta": JANELA_CURTA, "janela_longa": JANELA_LONGA,
        "ranking_ofensivo": todos_of[:top_n],
        "ranking_defensivo": todos_def[:top_n],
        "todos_ofensivos": todos_of, "todos_defensivos": todos_def,
        "confiabilidade": CONFIABILIDADE,
    }


# ---------------------------------------------------------------------------
# MOTOR DE PRODUÇÃO — ranking pelo modelo Poisson validado (seção 8/9)
# ---------------------------------------------------------------------------
# Substitui a normalização feita só entre os ~10 mandantes/visitantes da
# própria rodada (instável: um valor extremo de UM time mudava o z-score de
# TODOS os outros) e a interação descontínua "produto dos z-scores se mesmo
# sinal, zero se sinal oposto" por probabilidades calibradas por backtest
# walk-forward em 4 temporadas (modeling/, ver artifacts/evaluation_summary.json
# e artifacts/validacao_poisson.json). A vantagem de Brier Score sobre uma
# baseline por liga+mando é MODESTA e não passou no teste de significância a
# 95% — não é "muito mais preciso"; é estruturalmente mais correto (deriva
# P(2+gols) e P(SG) de uma única distribuição, sem misturar índices
# heurísticos) e mais estável (Spearman ~0,91 sob reamostragem do treino).

ROTULOS_FEATURE_MODELO = {
    "xg": "xG produzido", "sot": "chutes no alvo", "chutes_area": "finalizações na área",
    "toques_area": "toques na área", "grandes_chances": "grandes chances criadas",
    "xg_ced": "xG cedido", "sot_ced": "chutes no alvo cedidos",
    "chutes_area_ced": "finalizações cedidas na área", "grandes_chances_ced": "grandes chances cedidas",
}


def _rotulo_feature(campo: str) -> str:
    base = campo.replace("adv_", "").rsplit("_j", 1)[0].rsplit("_temporada", 1)[0].rsplit("_ewma", 1)[0]
    lado = "do adversário" if campo.startswith("adv_") else "próprio"
    return f"{ROTULOS_FEATURE_MODELO.get(base, base)} ({lado})"


def _razoes_modelo(fatores: list[dict], eixo: str) -> list[str]:
    """Razões da posição, faladas em português, a partir da contribuição real do modelo."""
    razoes = []
    for f in fatores[:2]:
        direcao = "pesa a favor" if f["contribuicao"] > 0 else "pesa contra"
        razoes.append(f"{_rotulo_feature(f['metrica'])} {direcao} da previsão (valor {f['valor']})")
    return razoes


def _classificar_por_probabilidade(p_propria: float, p_adv_eixo_oposto: float,
                                   faixas_propria: dict, faixas_adv: dict) -> str:
    """
    Mesma semântica de veredito do motor antigo (seção 8/9 pedem preservar o
    vocabulário da interface), agora derivada de faixas de percentil da
    distribuição real do modelo (artifacts/model_metadata.json), não de
    constantes arbitrárias como o LIMIAR_ADV_FORTE=0,90 do motor antigo.
    """
    adv_forte = p_adv_eixo_oposto >= faixas_adv["p75"]
    adv_fraco = p_adv_eixo_oposto <= faixas_adv["p25"]
    propria_alta = p_propria >= faixas_propria["p75"]
    if adv_forte:
        return "RESSALVA" if propria_alta else "ALTA_EXIGENCIA"
    if adv_fraco:
        return "MUITO_FAVORAVEL" if propria_alta else "FAVORAVEL"
    return "FAVORAVEL" if propria_alta else "NEUTRO"


def _dossie_modelo(p: Perfil, adv: Perfil, pred: dict, pred_adv: dict, faixas: dict,
                   pos: int, eixo: str) -> dict:
    if eixo == "ofensivo":
        proprio, adv_fatos = _fatos_of(p), _fatos_def(adv)
        sup, sup_adv = p.superlativos_of, adv.superlativos_def
        prob, faixa_prob = pred["probabilidade_2_mais_gols"], pred["faixa_ataque"]
        prob_adv_oposto = pred_adv["probabilidade_sg"]
        faixas_propria, faixas_adv = faixas["ataque"], faixas["defesa"]
        fatores = pred["fatores_ataque"]
    else:
        proprio, adv_fatos = _fatos_def(p), _fatos_of(adv)
        sup, sup_adv = p.superlativos_def, adv.superlativos_of
        prob, faixa_prob = pred["probabilidade_sg"], pred["faixa_defesa"]
        prob_adv_oposto = pred_adv["probabilidade_2_mais_gols"]
        faixas_propria, faixas_adv = faixas["defesa"], faixas["ataque"]
        fatores = pred["fatores_defesa"]

    veredito = _classificar_por_probabilidade(prob, prob_adv_oposto, faixas_propria, faixas_adv)
    return {
        "eixo": eixo, "posicao": pos, "time": p.nome, "adversario": adv.nome,
        "mando": p.mando, "mando_adversario": adv.mando,
        "indice": round(prob, 3),                          # agora é a probabilidade calibrada, não z-score
        "probabilidade": round(prob, 3), "faixa_expectativa": faixa_prob,
        "confianca_modelo": pred["confianca"],
        "veredito": veredito, "veredito_texto": VEREDITOS[veredito],
        "confianca": round(p.confianca, 2),                 # confiança por amostra (compat. narrativa)
        "proprio": proprio, "adversario_fatos": adv_fatos,
        "superlativos": sup, "superlativos_adversario": sup_adv,
        "jogos_proprio": _rotulos(p), "jogos_adversario": _rotulos(adv),
        "decomposicao": {f["metrica"]: f["contribuicao"] for f in fatores},
        "razoes": _razoes_modelo(fatores, eixo),
    }


def analisar_rodada(confrontos: list[dict], rodada_num: int, n_jogos: int,
                    tipo_filtro: str, top_n: int = 6) -> dict:
    """
    Motor de produção. O RANKING vem do modelo Poisson validado
    (modeling/prediction.py); as tabelas de "últimos N jogos" e os
    superlativos continuam calculados como antes — são conteúdo
    DESCRITIVO, não a base do ranking (ver app.py para o aviso na
    interface, seção 10 da revisão de 2026-08-06).
    """
    from modeling.prediction import carregar_metadata, prever_confronto

    top_n = max(5, min(7, top_n))
    todos = fetch_all_matches()
    base = _baseline(rodada_num, todos)
    meta = carregar_metadata()
    faixas = {
        "ataque": meta["modelo_ataque_gols_marcados"]["faixas_probabilidade"],
        "defesa": meta["modelo_defesa_gols_sofridos"]["faixas_probabilidade"],
    }

    mandantes, visitantes = [], []
    for c in confrontos:
        for nome, papel, mando, lista, adv in (
            (c["Mandante"], "home", "casa", mandantes, c["Visitante"]),
            (c["Visitante"], "away", "fora", visitantes, c["Mandante"]),
        ):
            st, _ = _calcular_metricas(nome, rodada_num, n_jogos, tipo_filtro, papel)
            serie = _historico(nome, rodada_num, mando, todos)
            if not serie:
                continue
            p = Perfil(nome=nome, adversario=adv, mando=mando, serie=serie, stats=st)
            p.medias = _perfil_metricas(serie)
            p.residuo = _residuos(serie[-JANELA_LONGA:], mando, base)
            lista.append(p)

    # superlativos continuam por pool de mando — são fato descritivo
    # ("maior xG entre os mandantes da rodada"), não entram no ranking.
    _calcular_pool(mandantes, JANELA_LONGA)
    _calcular_pool(visitantes, JANELA_LONGA)

    dossies_of, dossies_def = [], []
    for m in mandantes:
        v = next((x for x in visitantes if x.nome == m.adversario), None)
        if not v:
            continue
        jogo_raw = next(
            (j for j in todos if j.get("game_week") == rodada_num
             and j.get("home_name") == m.nome and j.get("away_name") == v.nome),
            None,
        )
        if jogo_raw is None:
            continue
        pred = prever_confronto(m.nome, v.nome, rodada_num, jogo_raw["date_unix"], jogo_raw["id"], todos)
        pred_m, pred_v = pred[m.nome], pred[v.nome]

        dossies_of.append((m, v, pred_m, pred_v))   # ataque do mandante
        dossies_of.append((v, m, pred_v, pred_m))   # ataque do visitante
        dossies_def.append((m, v, pred_m, pred_v))  # defesa do mandante
        dossies_def.append((v, m, pred_v, pred_m))  # defesa do visitante

    ofs = sorted(dossies_of, key=lambda t: -t[2]["probabilidade_2_mais_gols"])
    defs = sorted(dossies_def, key=lambda t: -t[2]["probabilidade_sg"])
    todos_of = [_dossie_modelo(p, adv, pred, pred_adv, faixas, i + 1, "ofensivo")
                for i, (p, adv, pred, pred_adv) in enumerate(ofs)]
    todos_def = [_dossie_modelo(p, adv, pred, pred_adv, faixas, i + 1, "defensivo")
                for i, (p, adv, pred, pred_adv) in enumerate(defs)]
    _marcar_faixas(todos_of)
    _marcar_faixas(todos_def)

    return {
        "rodada": rodada_num, "n_jogos": n_jogos, "tipo_filtro": tipo_filtro,
        "janela_curta": JANELA_CURTA, "janela_longa": JANELA_LONGA,
        "ranking_ofensivo": todos_of[:top_n],
        "ranking_defensivo": todos_def[:top_n],
        "todos_ofensivos": todos_of, "todos_defensivos": todos_def,
        "confiabilidade": CONFIABILIDADE,
        "modelo": {
            "versao": meta["versao_modelo"], "treinado_em": meta["treinado_em"],
            "hash_execucao": meta["hash_execucao"],
        },
    }
