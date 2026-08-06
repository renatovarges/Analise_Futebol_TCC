from __future__ import annotations

import subprocess
import sys
import time
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).resolve().parent.parent


def test_execucao_completa_de_uma_rodada_real():
    """Confrontos -> ranking pelo modelo -> narrativa -> roteiro, com dados reais."""
    import data_processor
    import analytics_engine
    import narrative_engine

    confrontos = data_processor.get_confrontos_rodada(20)
    assert confrontos

    analise = analytics_engine.analisar_rodada(confrontos, 20, 3, "POR_MANDO", top_n=6)
    assert len(analise["ranking_ofensivo"]) == 6
    assert len(analise["ranking_defensivo"]) == 6
    assert "modelo" in analise

    redacao = narrative_engine.gerar_paragrafos(analise, provedor="python")
    assert redacao["erro"] is None
    assert len(redacao["textos"]) == 12

    roteiro = narrative_engine.montar_roteiro(analise, redacao["textos"])
    assert "RODADA 20" in roteiro.upper() or "20" in roteiro


def test_narrativa_com_ia_indisponivel_usa_fallback_python():
    import analytics_engine
    import data_processor
    import narrative_engine

    confrontos = data_processor.get_confrontos_rodada(20)
    analise = analytics_engine.analisar_rodada(confrontos, 20, 3, "POR_MANDO", top_n=5)

    redacao = narrative_engine.gerar_paragrafos(analise, provedor="openai", api_key=None)
    assert redacao["erro"] == "Chave de API não informada."
    assert redacao["provedor_usado"] == "python (fallback)"
    assert len(redacao["textos"]) == 10


def test_retorno_invalido_da_ia_cai_para_fallback(monkeypatch):
    import analytics_engine
    import data_processor
    import narrative_engine

    confrontos = data_processor.get_confrontos_rodada(20)
    analise = analytics_engine.analisar_rodada(confrontos, 20, 3, "POR_MANDO", top_n=5)

    def _quebrado(*a, **k):
        raise ValueError("JSON inválido simulado")

    monkeypatch.setattr(narrative_engine, "_redigir_openai", _quebrado)
    redacao = narrative_engine.gerar_paragrafos(
        analise, provedor="openai", api_key="chave-falsa-para-teste", modelo="gpt-4o",
    )
    assert redacao["provedor_usado"] == "python (fallback)"
    assert redacao["erro"] is not None
    assert len(redacao["textos"]) == 10


def test_streamlit_inicializa_sem_erro():
    """Sobe o app.py headless e confere HTTP 200 + ausência do banner de erro próprio do app."""
    porta = 8597
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.headless", "true", "--server.port", str(porta)],
        cwd=str(BASE_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        import urllib.request
        html = ""
        for _ in range(20):
            time.sleep(1)
            try:
                with urllib.request.urlopen(f"http://localhost:{porta}", timeout=2) as r:
                    if r.status == 200:
                        html = r.read().decode("utf-8", errors="ignore")
                        break
            except Exception:
                continue
        assert html, "Streamlit não respondeu HTTP 200 a tempo"
        assert "erro inesperado" not in html.lower()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_geracao_de_arte_principal_nao_quebra():
    import data_processor
    import graphic_renderer

    confrontos = data_processor.get_confrontos_rodada(20)
    df_b1, df_b2, df_b3, df_b4, evidence_list = data_processor.build_analysis_dataframes(
        confrontos, 20, 3, "POR_MANDO",
    )
    assert not df_b1.empty
    caminho = graphic_renderer.generate_infographic(df_b1, df_b2, df_b3, df_b4, 20, 3, "POR_MANDO")
    assert caminho is not None
    assert Path(caminho).exists()
