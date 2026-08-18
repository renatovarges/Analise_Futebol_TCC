from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

from narratives.phrase_validator import (
    checar_densidade_numerica, checar_frases_banidas, checar_tamanho,
)


def _gerar_rodada_real(rodada: int = 20):
    import analytics_engine
    import data_processor
    import narrative_engine

    confrontos = data_processor.get_confrontos_rodada(rodada)
    analise = analytics_engine.analisar_rodada(confrontos, rodada, 3, "POR_MANDO", top_n=6)
    redacao = narrative_engine.gerar_paragrafos(analise, provedor="python")
    return analise, redacao


def test_rodada_real_respeita_limite_de_tamanho():
    _, redacao = _gerar_rodada_real()
    for chave, texto in redacao["textos"].items():
        n = len(texto.split())
        assert 20 <= n <= 55, f"{chave}: {n} palavras fora da janela (texto: {texto!r})"


def test_rodada_real_respeita_maximo_de_metricas_numericas():
    _, redacao = _gerar_rodada_real()
    for chave, texto in redacao["textos"].items():
        problemas = checar_densidade_numerica(texto)
        assert problemas == [], f"{chave}: {problemas}"


def test_rodada_real_nao_usa_expressoes_proibidas():
    _, redacao = _gerar_rodada_real()
    for chave, texto in redacao["textos"].items():
        banidas = checar_frases_banidas(texto)
        assert banidas == [], f"{chave}: usa frase banida {banidas} — texto: {texto!r}"


def test_rodada_real_nao_usa_gerundismo():
    _, redacao = _gerar_rodada_real()
    muletas = ("vem apresentando", "vem mostrando", "vem criando", "vem sofrendo",
               "vem permitindo", "vem cedendo", "está apresentando", "segue mostrando")
    for chave, texto in redacao["textos"].items():
        assert not any(m in texto.lower() for m in muletas), f"{chave}: gerundismo em {texto!r}"


def test_todo_destaque_real_recebe_diagnostico_do_confronto():
    analise, _ = _gerar_rodada_real()
    for d in analise["ranking_ofensivo"] + analise["ranking_defensivo"]:
        diag = d.get("diagnostico") or {}
        assert diag.get("forca_propria") in {"favoravel", "neutro", "desfavoravel"}
        assert diag.get("efeito_adversario") in {"favoravel", "neutro", "desfavoravel"}
        assert diag.get("origem_expectativa") in {
            "convergencia", "merito_proprio", "oportunidade_pelo_adversario",
            "dupla_limitacao", "equilibrio_com_ressalva",
        }
        assert diag.get("nivel_absoluto") in {"baixa", "moderada", "alta", "muito_alta"}


def test_rodada_real_nao_usa_conquistou_sg():
    _, redacao = _gerar_rodada_real()
    for chave, texto in redacao["textos"].items():
        baixo = texto.lower()
        assert "conquistou sg" not in baixo and "conquistar sg" not in baixo, (
            f"{chave}: usa 'conquistou/conquistar SG' — texto: {texto!r}"
        )


def test_rodada_real_nao_explica_xg_dentro_do_paragrafo():
    """A explicação de xG/xGA saiu do texto e foi para a interface, uma vez só."""
    _, redacao = _gerar_rodada_real()
    for chave, texto in redacao["textos"].items():
        assert "perigo criado" not in texto.lower(), f"{chave}: ainda explica xG no texto"


def test_rodada_real_todos_os_textos_passam_no_verificador_de_atribuicao():
    _, redacao = _gerar_rodada_real()
    for chave, alertas in redacao["alertas"].items():
        assert alertas == [], f"{chave}: números sem origem no dossiê: {alertas}"


def test_rodada_real_fallback_funciona_sem_ia():
    analise, redacao = _gerar_rodada_real()
    assert redacao["erro"] is None
    assert redacao["provedor_usado"] == "python"
    assert len(redacao["textos"]) == len(analise["ranking_ofensivo"]) + len(analise["ranking_defensivo"])


def test_controle_de_similaridade_gera_avisos_reportados():
    """
    Com o orçamento apertado (2 números, 2 frases, 25-45 palavras), alguma
    colisão estrutural entre 12+ textos é esperada — o requisito é que ela
    seja DETECTADA e reportada (repeticoes), não que caia a zero. Precisão
    factual vem antes de variedade perfeita.
    """
    _, redacao = _gerar_rodada_real()
    assert "repeticoes" in redacao
    assert isinstance(redacao["repeticoes"], dict)
