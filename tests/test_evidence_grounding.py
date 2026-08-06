from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

import narrative_engine


def _dossie_sintetico(eixo="ofensivo"):
    """
    Valores de proprio e adversario_fatos propositalmente bem distintos e
    identificáveis, para provar que o motor Python nunca troca os lados.
    proprio/adversario_fatos têm o formato certo para o eixo: quando eixo é
    "ofensivo", proprio é um dicionário OFENSIVO (produzido por _fatos_of) e
    adversario_fatos é DEFENSIVO (produzido por _fatos_def) — e vice-versa
    para "defensivo". É a mesma forma que analytics_engine._dossie_modelo
    monta de verdade.
    """
    ofensivo_marcado = {
        "xg_medio": 1.11, "gols": 11, "conversao": 11,
        "chutes_alvo": 1.1, "chutes_area": 1.1, "toques_area": 1.1,
        "grandes_chances": 1.1, "jogos_sem_marcar": 0, "jogos": 5, "mando": "casa",
    }
    defensivo_marcado = {
        "xga_medio": 9.99, "gols_sofridos": 99, "conversao_cedida": 99,
        "chutes_alvo_cedidos": 9.9, "chutes_area_cedidos": 9.9,
        "grandes_chances_cedidas": 9.9, "clean_sheets": 0, "jogos": 5, "mando": "fora",
    }
    if eixo == "ofensivo":
        proprio, adversario_fatos = ofensivo_marcado, defensivo_marcado
    else:
        proprio, adversario_fatos = defensivo_marcado, ofensivo_marcado

    return {
        "eixo": eixo, "posicao": 1, "time": "TimeProprio", "adversario": "TimeAdversario",
        "mando": "casa", "mando_adversario": "fora",
        "veredito": "FAVORAVEL", "veredito_texto": "cruzamento favorável",
        "confianca": 1.0,
        "proprio": proprio, "adversario_fatos": adversario_fatos,
        "superlativos": [], "superlativos_adversario": [],
        "jogos_proprio": ["1x0 vs X (R1)"], "jogos_adversario": ["0x1 vs Y (R1)"],
    }


def test_numeros_do_proprio_time_nao_vazam_para_frase_do_adversario():
    """
    O motor Python monta f1 (próprio time) só a partir de d['proprio'] e f2
    (adversário) só a partir de d['adversario_fatos'] — nunca deveriam se
    misturar. Prova concreta: os valores "marcadores" (11, 99) de cada lado
    não podem aparecer na metade errada da frase.
    """
    dossies = [_dossie_sintetico("ofensivo"), _dossie_sintetico("defensivo")]
    textos = narrative_engine._redigir_python(dossies)
    for d in dossies:
        chave = narrative_engine.chave_dossie(d)
        texto = textos[chave]
        # marcador exclusivo de cada lado: "99" só existe nos números do
        # lado que tiver defensivo_marcado (gols_sofridos/conversao_cedida),
        # "11" só no lado com ofensivo_marcado — não é fixo por eixo, é
        # fixo por QUAL DICIONÁRIO tem o valor, então funciona nos dois eixos.
        marcador_adversario = "99" if "99" in str(d["adversario_fatos"].values()) else "11"
        # heurística: a primeira metade da frase (até o nome do adversário
        # aparecer) é sobre o próprio time
        pos_adv = texto.find(d["adversario"])
        metade_propria = texto[:pos_adv] if pos_adv > 0 else texto
        assert marcador_adversario not in metade_propria, (
            f"vazou dado do adversário ({marcador_adversario}) pro lado próprio: {texto}"
        )


def test_verificar_numeros_aprova_texto_gerado_pelo_proprio_motor():
    dossies = [_dossie_sintetico("ofensivo"), _dossie_sintetico("defensivo")]
    textos = narrative_engine._redigir_python(dossies)
    for d in dossies:
        chave = narrative_engine.chave_dossie(d)
        alertas = narrative_engine.verificar_numeros(textos[chave], d)
        assert alertas == [], f"motor Python gerou número sem origem: {alertas} em {textos[chave]!r}"


def test_valor_negativo_com_linguagem_direcional_nao_dispara_alerta():
    """Regressão do falso-positivo achado em 2026-08-06: 'abaixo do esperado' + valor absoluto."""
    d = _dossie_sintetico("defensivo")
    d["proprio"]["gols_evitados_goleiro"] = -0.51
    texto = "Vem sendo prejudicado pelo goleiro, 0,51 gol por jogo abaixo do esperado."
    alertas = narrative_engine.verificar_numeros(texto, d)
    assert "0,51" not in alertas and "0.51" not in alertas


def test_formas_aceitas_inclui_absoluto_e_sinal():
    formas = narrative_engine._formas_aceitas(-0.51)
    assert "0,51" in formas and "-0,51" in formas
