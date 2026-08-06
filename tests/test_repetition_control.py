from __future__ import annotations

from narratives.repetition_control import ControleRepeticao


def test_abertura_repetida_e_detectada():
    """As 4 primeiras palavras (a 'abertura') são idênticas nos dois textos — só o resto muda."""
    c = ControleRepeticao()
    c.checar("k1", "Combina bons números ofensivos em casa.", "A", "B")
    c.registrar("k1", "Combina bons números ofensivos em casa.", "A", "B")
    problemas = c.checar("k2", "Combina bons números ofensivos fora, com outro time.", "C", "D")
    assert any("abertura repetida" in p for p in problemas)


def test_estrutura_quase_identica_com_numeros_diferentes_e_detectada():
    c = ControleRepeticao()
    t1 = "Produz 1,50 de xG e 5 chutes no alvo por jogo em casa."
    t2 = "Produz 2,10 de xG e 7 chutes no alvo por jogo em casa."
    c.checar("k1", t1, "A", "B")
    c.registrar("k1", t1, "A", "B")
    problemas = c.checar("k2", t2, "C", "D")
    assert any("estrutura quase idêntica" in p for p in problemas)


def test_textos_bem_diferentes_nao_disparam_falso_positivo():
    c = ControleRepeticao()
    t1 = "Produz 1,50 de xG por jogo em casa."
    t2 = "Sofreu apenas 1 gol nas últimas partidas fora de casa, com defesa sólida."
    c.checar("k1", t1, "A", "B")
    c.registrar("k1", t1, "A", "B")
    problemas = c.checar("k2", t2, "C", "D")
    assert problemas == []


def test_verbo_repetido_alem_do_limite_e_sinalizado():
    c = ControleRepeticao(max_repeticoes_verbo=2)
    frases = ["Registra bom momento em casa.", "Registra solidez fora.", "Registra números fortes hoje."]
    times = [("A", "B"), ("C", "D"), ("E", "F")]
    problemas_ultima = []
    for (texto, (t, adv)) in zip(frases, times):
        problemas_ultima = c.checar(f"k-{t}", texto, t, adv)
        c.registrar(f"k-{t}", texto, t, adv)
    assert any("já usado" in p for p in problemas_ultima)


def test_reset_limpa_historico():
    c = ControleRepeticao()
    c.checar("k1", "Combina bons números.", "A", "B")
    c.registrar("k1", "Combina bons números.", "A", "B")
    c.reset()
    problemas = c.checar("k2", "Combina bons números.", "A", "B")
    assert problemas == []
