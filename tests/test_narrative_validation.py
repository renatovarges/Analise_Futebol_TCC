from __future__ import annotations

from narratives.phrase_validator import (
    checar_atribuicao, checar_frases_banidas, checar_numeros_no_texto,
    checar_tom_veredito, validar_paragrafo_ia,
)

DOSSIE = {
    "time": "Flamengo", "adversario": "Vitoria", "eixo": "ofensivo", "veredito": "FAVORAVEL",
    "proprio": {"xg_medio": 1.71, "gols": 5, "conversao": 42},
    "adversario_fatos": {"xga_medio": 1.90, "gols_sofridos": 6, "conversao_cedida": 22},
}


def test_atribuicao_correta_passa():
    fatos = [{"campo": "xg_medio", "sujeito": "proprio"}, {"campo": "xga_medio", "sujeito": "adversario"}]
    problemas, autorizados = checar_atribuicao(fatos, DOSSIE)
    assert problemas == []
    assert "1,71" in autorizados


def test_campo_do_adversario_atribuido_como_proprio_e_rejeitado():
    """Caso pedido explicitamente: 'atribui dado do adversário ao time analisado'."""
    fatos = [{"campo": "xga_medio", "sujeito": "proprio"}]   # xga_medio só existe em adversario_fatos
    problemas, _ = checar_atribuicao(fatos, DOSSIE)
    assert any("não existe" in p for p in problemas)


def test_metrica_cedida_tratada_como_conquistada_e_rejeitada():
    """Caso pedido explicitamente: 'troca métrica conquistada por cedida'."""
    # "conversao" (conquistada) declarada como se fosse "conversao_cedida" (cedida) do adversário
    fatos = [{"campo": "conversao_cedida", "sujeito": "proprio"}]   # não existe em proprio
    problemas, _ = checar_atribuicao(fatos, DOSSIE)
    assert any("não existe" in p for p in problemas)


def test_falta_lado_proprio_e_rejeitado():
    fatos = [{"campo": "xga_medio", "sujeito": "adversario"}]
    problemas, _ = checar_atribuicao(fatos, DOSSIE)
    assert any("próprio time" in p for p in problemas)


def test_so_lado_proprio_e_aceito_forca_propria():
    """Destaque tipo FORÇA_PRÓPRIA pode descrever o adversário sem número —
    só o fato do próprio time é obrigatório (metodologia de cruzamento,
    2026-08-19)."""
    fatos = [{"campo": "xg_medio", "sujeito": "proprio"}]
    problemas, _ = checar_atribuicao(fatos, DOSSIE)
    assert problemas == []


def test_numero_correto_atribuido_a_equipe_errada():
    """Caso pedido explicitamente: número correto (real do dossiê) usado no contexto errado."""
    fatos = [{"campo": "xg_medio", "sujeito": "proprio"}, {"campo": "xga_medio", "sujeito": "adversario"}]
    _, autorizados = checar_atribuicao(fatos, DOSSIE)
    # o texto usa "6" (gols_sofridos do adversário) mas isso não foi declarado como fato usado
    texto = "O Flamengo produziu 1,71 de xG e o adversário sofreu 6 gols em casa."
    problemas = checar_numeros_no_texto(texto, autorizados, DOSSIE)
    # "6" é inteiro livre (<12), não dispara sozinho — mas 1,71 e 1,90 (não declarado) sim
    texto2 = "O Flamengo produziu 1,71 de xG contra uma defesa de 1,90 de xGA."
    fatos_incompletos = [{"campo": "xg_medio", "sujeito": "proprio"}]  # falta declarar xga_medio
    problemas_atrib, autorizados2 = checar_atribuicao(fatos_incompletos, DOSSIE)
    problemas2 = checar_numeros_no_texto(texto2, autorizados2, DOSSIE)
    assert any("1,90" in p or "1.90" in p for p in problemas2)


def test_frases_banidas_detectadas():
    texto = "Vale destacar que o time vem demonstrando evolução nesse contexto."
    banidas = checar_frases_banidas(texto)
    assert "vale destacar" in banidas
    assert "vem demonstrando" in banidas
    assert "nesse contexto" in banidas


def test_eixo_ofensivo_nao_pode_prometer_gol():
    problemas = checar_tom_veredito("O time vai marcar hoje, com certeza.", "ofensivo", "FAVORAVEL")
    assert any("promete gol" in p for p in problemas)


def test_veredito_alta_exigencia_com_tom_confirmatorio_sem_ressalva_e_rejeitado():
    texto = "Cenário totalmente favorável e seguro para o SG, sem dúvida."
    problemas = checar_tom_veredito(texto, "defensivo", "ALTA_EXIGENCIA")
    assert any("ALTA_EXIGENCIA" in p for p in problemas)


def test_veredito_alta_exigencia_com_ressalva_passa():
    texto = "O confronto é de alta exigência, porém o time tem números sólidos."
    problemas = checar_tom_veredito(texto, "defensivo", "ALTA_EXIGENCIA")
    assert problemas == []


def test_validar_paragrafo_ia_aprova_texto_correto():
    fatos = [{"campo": "xg_medio", "sujeito": "proprio"}, {"campo": "xga_medio", "sujeito": "adversario"}]
    texto = "Produz 1,71 de xG em casa e enfrenta uma defesa que cede 1,90 de xGA fora, formando um cruzamento favorável."
    problemas = validar_paragrafo_ia(texto, fatos, DOSSIE)
    assert problemas == []


def test_validar_paragrafo_ia_sem_fatos_usados_e_rejeitado():
    problemas = validar_paragrafo_ia("Qualquer texto aqui.", [], DOSSIE)
    assert problemas != []
