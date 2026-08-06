import streamlit as st
import traceback

st.set_page_config(page_title="Análise xG/xGA Brasileirão", layout="wide")

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import gc

    import data_processor
    import graphic_renderer
    import analytics_engine
    import narrative_engine
    from sofascore_api import fetch_all_matches

    # ── ESTILO ────────────────────────────────────────────────────────────
    st.markdown("""
    <style>
        .stTable { font-family: 'Arial', sans-serif; }
        .metric-box { border:1px solid #ddd; padding:10px; border-radius:5px;
                      background:#f9f9f9; text-align:center; }
        .metric-header { font-size:.8em; color:#666; font-weight:bold; }
        .metric-value  { font-size:1.2em; font-weight:bold; }
        .good    { color:#2e7d32; }
        .bad     { color:#c62828; }
        .neutral { color:#f57f17; }
    </style>
    """, unsafe_allow_html=True)

    # ── SIDEBAR ───────────────────────────────────────────────────────────
    st.sidebar.header("⚙️ Configurações")

    if st.sidebar.button("🔄 Atualizar dados da API"):
        fetch_all_matches.clear()
        with st.sidebar:
            with st.spinner("Buscando dados atualizados..."):
                matches_fresh = fetch_all_matches()
        completos   = [m for m in matches_fresh if m["status"] == "complete"]
        agendados   = [m for m in matches_fresh if m["status"] != "complete"]
        ultima_rod  = max((m["game_week"] for m in completos), default=0)
        proxima_rod = min((m["game_week"] for m in agendados), default=0)
        # Salva no session_state para exibir persistentemente após o rerun
        st.session_state["ultima_atualizacao"] = {
            "total":       len(matches_fresh),
            "completos":   len(completos),
            "agendados":   len(agendados),
            "ultima_rod":  ultima_rod,
            "proxima_rod": proxima_rod,
        }
        st.rerun()

    # Exibe confirmação da última atualização (persiste entre reruns)
    if "ultima_atualizacao" in st.session_state:
        u = st.session_state["ultima_atualizacao"]
        st.sidebar.success("✅ Dados atualizados com sucesso!")
        st.sidebar.markdown(f"""
| | |
|---|---|
| 📦 Total de jogos | **{u['total']}** |
| ✅ Jogos completos | **{u['completos']}** |
| 🕐 Jogos agendados | **{u['agendados']}** |
| 🏁 Última rodada completa | **Rodada {u['ultima_rod']}** |
| 📅 Próxima rodada | **Rodada {u['proxima_rod']}** |
""")

    with st.sidebar.expander("ℹ️ Sobre os filtros"):
        st.markdown("""
        **Filtro POR MANDO** (recomendado): usa apenas os últimos N jogos
        de cada time no mesmo papel que terá na próxima rodada
        (mandante → histórico em casa; visitante → histórico fora).

        **TODOS OS JOGOS**: considera os últimos N jogos independentemente
        do mando, útil quando um time tem poucos jogos no mando.
        """)

    st.sidebar.divider()
    st.sidebar.subheader("📋 Parâmetros")

    # Carrega rodadas disponíveis da API
    with st.spinner("Carregando calendário da API..."):
        rodadas = data_processor.get_rodadas_disponiveis()

    rodada_sel = st.sidebar.selectbox(
        "Rodada para análise",
        rodadas,
        index=min(17, len(rodadas) - 1),   # padrão: rodada 18 (índice 17)
    )

    n_jogos = st.sidebar.number_input(
        "Recorte (N últimos jogos)", min_value=1, max_value=10, value=3
    )

    tipo_filtro = st.sidebar.radio(
        "Tipo de filtro",
        ["POR_MANDO", "TODOS"],
        index=0,
        format_func=lambda x: "Por mando" if x == "POR_MANDO" else "Todos os jogos",
    )

    # ── DESTAQUES DA RODADA ───────────────────────────────────────────────
    st.sidebar.divider()
    st.sidebar.subheader("🎯 Destaques da rodada")

    top_n = st.sidebar.slider(
        "Times por ranking", min_value=5, max_value=7, value=6,
        help="Quantos ataques e quantas defesas entram nos rankings.",
    )

    provedor = st.sidebar.radio(
        "Motor de redação",
        ["openai", "claude", "python"],
        index=0,
        format_func=lambda x: {
            "openai": "OpenAI (chave própria)",
            "claude": "Claude (chave própria)",
            "python": "Python local (sem chave)",
        }[x],
        help="O motor analítico é sempre o mesmo. Isto muda apenas quem escreve "
             "os parágrafos — troque à vontade e compare os textos.",
    )

    def _do_secrets(nome: str) -> str:
        """Lê secrets.toml tolerando arquivo ausente ou campo em branco."""
        try:
            return str(st.secrets.get(nome, "") or "").strip()
        except Exception:
            return ""

    api_key, modelo = None, None
    if provedor in ("openai", "claude"):
        pref = {"openai": "OPENAI", "claude": "ANTHROPIC"}[provedor]
        segredo = f"{pref}_API_KEY"

        api_key = _do_secrets(segredo) or None
        if api_key:
            st.sidebar.success(f"🔑 Chave carregada do `secrets.toml`")
        else:
            api_key = st.sidebar.text_input(
                "Chave de API", type="password",
                help=f"Para não colar toda rodada, preencha {segredo} em "
                     f".streamlit/secrets.toml e reinicie o app.",
            ) or None
        # Quais modelos a conta tem liberados — perguntado ao provedor, não
        # chutado. A lista fica em sessão para não repetir a consulta.
        cache_modelos = f"modelos_{provedor}"
        if st.sidebar.button("🔍 Buscar modelos da minha conta",
                             disabled=not api_key, width="stretch"):
            try:
                with st.spinner("Consultando..."):
                    st.session_state[cache_modelos] = narrative_engine.listar_modelos(
                        provedor, api_key
                    )
            except Exception as e:
                st.sidebar.error(f"Não consegui consultar: {type(e).__name__}: {e}")

        disponiveis = st.session_state.get(cache_modelos)
        # Modelo fixado no secrets.toml vence o padrão do código.
        padrao = _do_secrets(f"{pref}_MODELO") or narrative_engine.MODELOS_PADRAO[provedor]
        if disponiveis:
            if padrao not in disponiveis:
                disponiveis = [padrao] + disponiveis
            modelo = st.sidebar.selectbox(
                "Modelo", disponiveis, index=disponiveis.index(padrao),
                help=f"{len(disponiveis)} modelos de texto liberados na sua conta, "
                     "do mais recente ao mais antigo.",
            )
        else:
            modelo = st.sidebar.text_input(
                "Modelo", value=padrao,
                help="Clique em buscar acima para listar os da sua conta.",
            )

        timeout = st.sidebar.slider(
            "Limite de tempo (segundos)", min_value=60, max_value=600,
            value=int(narrative_engine.TIMEOUT_PADRAO), step=30,
            help="Se o modelo não responder nesse tempo, o app desiste e usa a "
                 "engine Python. Modelos '-pro' pensam antes de escrever e podem "
                 "precisar de 300s ou mais.",
        )
    else:
        timeout = narrative_engine.TIMEOUT_PADRAO

    # ── TÍTULO ────────────────────────────────────────────────────────────
    st.title(f"⚽ Análise xG/xGA — Rodada {rodada_sel}")

    filtro_label = "por mando" if tipo_filtro == "POR_MANDO" else "gerais"
    st.caption(f"Dados: SofaScore (Brasileirão 2026)")
    st.info(
        "🎯 **Ranking calculado pelo modelo preditivo** (probabilidade calibrada por "
        "backtest em 4 temporadas). A tabela de análise abaixo mostra o **recorte "
        f"descritivo** que você escolheu — **{n_jogos} últimos jogos {filtro_label}** — "
        "que é diferente do que o modelo usa internamente (várias janelas combinadas). "
        "Os dois são úteis: a tabela mostra a forma recente time a time; o ranking "
        "decide quem entra nos destaques.",
        icon="ℹ️",
    )

    # ── CONFRONTOS DA RODADA ──────────────────────────────────────────────
    with st.spinner(f"Buscando confrontos da rodada {rodada_sel}..."):
        confrontos = data_processor.get_confrontos_rodada(rodada_sel)

    if not confrontos:
        st.info(f"Nenhum confronto encontrado para a Rodada {rodada_sel}.")
        st.stop()

    st.subheader(f"📅 Confrontos — Rodada {rodada_sel}")
    cols_conf = st.columns(2)
    for i, c in enumerate(confrontos):
        status_icon = "✅" if c["Status"] == "complete" else "🕐"
        cols_conf[i % 2].markdown(f"{status_icon} **{c['Mandante']}** × {c['Visitante']}")

    # ── CÁLCULO DOS 4 BLOCOS ──────────────────────────────────────────────
    st.divider()
    with st.spinner("Calculando métricas..."):
        df_b1, df_b2, df_b3, df_b4, evidence_list = data_processor.build_analysis_dataframes(
            confrontos, rodada_sel, n_jogos, tipo_filtro
        )

    if df_b1.empty:
        st.warning("Não há histórico suficiente para calcular as métricas desta rodada.")
        st.stop()

    # ── PRÉVIA DAS TABELAS ────────────────────────────────────────────────
    st.subheader("📊 Análise Ofensiva do Mandante")
    st.dataframe(df_b1, width="stretch")

    st.subheader("📊 Análise Defensiva do Visitante")
    st.dataframe(df_b2, width="stretch")

    st.subheader("📊 Análise Ofensiva do Visitante")
    st.dataframe(df_b3, width="stretch")

    st.subheader("📊 Análise Defensiva do Mandante")
    st.dataframe(df_b4, width="stretch")

    # ── DESTAQUES DA RODADA ───────────────────────────────────────────────
    st.divider()
    st.header("🎯 Destaques da Rodada")
    st.caption(
        "Ranking calculado cruzando os números do próprio time com os do adversário "
        "no eixo oposto. Mandantes são comparados com mandantes e visitantes com "
        "visitantes, para que um bom desempenho fora de casa não seja apagado pelo "
        "viés de mando."
    )

    ROTULOS = {
        "xg_medio": "xG médio", "xga_medio": "xGA médio",
        "gols": "Gols marcados", "gols_sofridos": "Gols sofridos",
        "gols_por_jogo": "Gols por jogo", "gs_por_jogo": "Gols sofridos por jogo",
        "conversao": "Conversão", "conversao_cedida": "Conversão cedida",
        "chutes_alvo": "Chutes no alvo/jogo",
        "chutes_alvo_cedidos": "Chutes no alvo cedidos/jogo",
        "clean_sheets": "SGs conquistados", "jogos_sem_marcar": "Jogos sem marcar",
        "xg_piso": "Menor xG da série", "xg_teto": "Maior xG da série",
        "xga_piso": "Menor xGA da série", "xga_teto": "Maior xGA da série",
        "xg_piso_todos": "Produziu mais de (todos os jogos)",
        "xga_piso_todos": "Cedeu mais de (todas as partidas)",
        "xga_teto_todos": "Não cedeu mais de (nenhum jogo)",
        "marcou_em_todos": "Marcou em todos", "sofreu_em_todos": "Sofreu em todos",
        "nao_sofreu_em_nenhum": "Não sofreu em nenhum",
        "sequencia_sem_sofrer": "Sequência sem sofrer",
        "max_gols_jogo": "Máx. gols num jogo", "max_gs_jogo": "Máx. gols sofridos num jogo",
        "jogos": "Jogos no recorte", "mando": "Mando",
        # novos — vindos do SofaScore
        "chutes_area": "Finalizações na área/jogo",
        "chutes_area_cedidos": "Finalizações cedidas na área/jogo",
        "toques_area": "Toques na área/jogo",
        "grandes_chances": "Grandes chances/jogo",
        "grandes_chances_cedidas": "Grandes chances cedidas/jogo",
        "perigo_bola_parada_pct": "Perigo criado em bola parada",
        "perigo_contra_ataque_pct": "Perigo criado em contra-ataque",
        "sofre_bola_parada_pct": "Perigo sofrido em bola parada",
        "sofre_contra_ataque_pct": "Perigo sofrido em contra-ataque",
        "gols_evitados_goleiro": "Gols evitados pelo goleiro/jogo",
    }

    BADGE = {
        "MUITO_FAVORAVEL": "🟢", "FAVORAVEL": "🟢", "NEUTRO": "🟡",
        "RESSALVA": "🟠", "ALTA_EXIGENCIA": "🔴",
    }

    def _tabela_fatos(fatos: dict) -> str:
        linhas = ["| | |", "|---|---|"]
        for k, v in fatos.items():
            if k in ("mando", "jogos"):
                continue
            rot = ROTULOS.get(k, k)
            if isinstance(v, bool):
                v = "sim" if v else "não"
            elif isinstance(v, float):
                v = f"{v:.2f}".replace(".", ",")
            linhas.append(f"| {rot} | **{v}** |")
        return "\n".join(linhas)

    def _render_card(d: dict, textos: dict, alertas: dict):
        chave = narrative_engine.chave_dossie(d)
        badge = BADGE.get(d["veredito"], "⚪")
        eixo = "ATAQUE" if d["eixo"] == "ofensivo" else "DEFESA"

        st.markdown(
            f"#### {d['posicao']}º · {d['time']} "
            f"<small>({d['mando']}) × {d['adversario']}</small>",
            unsafe_allow_html=True,
        )
        prob = d.get("probabilidade", d["indice"])
        st.caption(
            f"{badge} {d['veredito_texto']}  ·  **{prob:.0%}**  ·  "
            f"{d.get('faixa_expectativa', '')}  ·  "
            f"confiança {d.get('confianca_modelo', d['confianca']):.0%}"
        )

        # Por que este time está nesta posição — os fatores de maior peso no modelo.
        if d.get("razoes"):
            st.markdown("  ·  ".join(f"*{r}*" for r in d["razoes"][:2]))

        # Parágrafo pronto para o Canva — st.code traz botão de cópia nativo.
        st.code(textos.get(chave, "—"), language=None, wrap_lines=True)

        avisos = alertas.get(chave) or []
        if avisos:
            st.warning(
                f"⚠️ Número(s) sem origem no dossiê: **{', '.join(avisos)}**. "
                "Confira antes de publicar."
            )
        if d["confianca"] < 0.99:
            st.info(
                f"ℹ️ Amostra incompleta: {d['proprio']['jogos']} jogo(s) no recorte. "
                "A probabilidade foi encolhida em direção à média da liga."
            )

        with st.expander("🔍 Números que sustentam a análise"):
            dec = d.get("decomposicao") or {}
            if dec:
                st.markdown("**Fatores de maior peso na previsão do modelo**")
                for campo, contrib in sorted(dec.items(), key=lambda kv: -abs(kv[1]))[:4]:
                    st.markdown(f"- `{campo}`: {contrib:+.3f}")
                st.caption(
                    "Contribuição de cada variável para o log da taxa esperada de gols "
                    "(regressão de Poisson) — positivo empurra a probabilidade para cima, "
                    "negativo para baixo. Não é probabilidade em si, é peso relativo."
                )
                st.divider()
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**{d['time']}** — {eixo.lower()} em {d['mando']}")
                st.markdown(_tabela_fatos(d["proprio"]))
                if d["superlativos"]:
                    st.markdown("**Destaques na rodada:**")
                    for s in d["superlativos"]:
                        st.markdown(f"- {s['texto']} (`{s['valor']}`)")
                st.markdown("**Jogos usados:**")
                for j in d["jogos_proprio"]:
                    st.markdown(f"- {j}")
            with c2:
                eixo_adv = "defesa" if d["eixo"] == "ofensivo" else "ataque"
                st.markdown(f"**{d['adversario']}** — {eixo_adv} em {d['mando_adversario']}")
                st.markdown(_tabela_fatos(d["adversario_fatos"]))
                if d["superlativos_adversario"]:
                    st.markdown("**Destaques na rodada:**")
                    for s in d["superlativos_adversario"]:
                        st.markdown(f"- {s}")
                st.markdown("**Jogos usados:**")
                for j in d["jogos_adversario"]:
                    st.markdown(f"- {j}")
        st.divider()

    assinatura = (rodada_sel, n_jogos, tipo_filtro, top_n, provedor, modelo)
    if st.session_state.get("destaques_assinatura") != assinatura:
        st.session_state.pop("destaques", None)

    if st.button("✨ GERAR DESTAQUES E ANÁLISES", width="stretch", type="primary"):
        aviso = ""
        if provedor != "python":
            aviso = (f"  ·  desiste em {int(timeout)}s e usa a engine Python"
                     f"{'  ·  modelos -pro costumam levar 1 a 3 minutos' if '-pro' in (modelo or '') else ''}")
        with st.spinner(f"Calculando índices e redigindo os parágrafos...{aviso}"):
            analise = analytics_engine.analisar_rodada(
                confrontos, rodada_sel, n_jogos, tipo_filtro, top_n=top_n
            )
            redacao = narrative_engine.gerar_paragrafos(
                analise, provedor=provedor, api_key=api_key, modelo=modelo,
                timeout=timeout,
            )
            st.session_state["destaques"] = (analise, redacao)
            st.session_state["destaques_assinatura"] = assinatura

    if "destaques" in st.session_state:
        analise, redacao = st.session_state["destaques"]
        textos, alertas = redacao["textos"], redacao["alertas"]

        if redacao["erro"]:
            st.error(
                f"Não foi possível usar **{provedor}** — caiu para a engine Python.\n\n"
                f"Detalhe: `{redacao['erro']}`"
            )
        else:
            st.success(
                f"Textos redigidos por: **{redacao['provedor_usado']}**"
                f"  ·  {redacao.get('segundos', 0):.0f}s"
            )

        total_avisos = sum(len(v) for v in alertas.values())
        if total_avisos:
            st.warning(
                f"⚠️ O verificador encontrou **{total_avisos}** número(s) sem origem "
                "no dossiê. Estão sinalizados nos cards correspondentes."
            )
        else:
            st.caption("✅ Verificador de números: todos os valores têm origem nos dados.")

        aba_of, aba_def, aba_audio = st.tabs(
            ["⚔️ Melhores ataques", "🛡️ Melhores defesas", "🎙️ Roteiro do áudio"]
        )
        def _render_ranking(lista, eixo):
            conf = (analise.get("confiabilidade") or {}).get(eixo)
            if conf:
                caixa = st.success if conf["nivel"] == "alta" else st.warning
                caixa(f"**Confiabilidade {conf['nivel']}.** {conf['texto']}")
            faixa_atual = None
            for d in lista:
                if d.get("faixa") and d["faixa"] != faixa_atual:
                    faixa_atual = d["faixa"]
                    st.markdown(f"##### {d['faixa_nome'].upper()}")
                _render_card(d, textos, alertas)

        with aba_of:
            _render_ranking(analise["ranking_ofensivo"], "ofensivo")
        with aba_def:
            _render_ranking(analise["ranking_defensivo"], "defensivo")
        with aba_audio:
            roteiro = narrative_engine.montar_roteiro(analise, textos)
            st.code(roteiro, language=None, wrap_lines=True)
            st.download_button(
                "⬇️ BAIXAR ROTEIRO (.txt)", roteiro,
                file_name=f"Roteiro_R{rodada_sel}.txt", mime="text/plain",
            )

        with st.expander("📋 Ranking completo dos 20 times (conferência)"):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Ofensivo**")
                st.dataframe(
                    [{"#": d["posicao"], "Time": d["time"], "Mando": d["mando"],
                      "Adversário": d["adversario"], "P(2+ gols)": f"{d['probabilidade']:.0%}",
                      "Confiança": f"{d.get('confianca_modelo', d['confianca']):.0%}"}
                     for d in analise["todos_ofensivos"]],
                    width="stretch", hide_index=True,
                )
            with c2:
                st.markdown("**Defensivo**")
                st.dataframe(
                    [{"#": d["posicao"], "Time": d["time"], "Mando": d["mando"],
                      "Adversário": d["adversario"], "P(SG)": f"{d['probabilidade']:.0%}",
                      "Confiança": f"{d.get('confianca_modelo', d['confianca']):.0%}"}
                     for d in analise["todos_defensivos"]],
                    width="stretch", hide_index=True,
                )

    # ── GERAÇÃO DAS ARTES PNG ─────────────────────────────────────────────
    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        if st.button("🖼️ GERAR TABELA PRINCIPAL", width="stretch"):
            with st.spinner("Gerando PNG Principal (alta qualidade)..."):
                try:
                    plt.close('all')
                    gc.collect()
                    out_path = graphic_renderer.generate_infographic(
                        df_b1, df_b2, df_b3, df_b4,
                        rodada_sel, n_jogos, tipo_filtro
                    )
                    if out_path:
                        st.success("Arte gerada! ✅")
                        st.image(out_path)
                        with open(out_path, "rb") as f:
                            st.download_button(
                                "⬇️ BAIXAR PNG (300 DPI)",
                                f,
                                file_name=f"Analise_R{rodada_sel}.png",
                                mime="image/png",
                            )
                    plt.close('all')
                    gc.collect()
                except Exception as e:
                    st.error(f"Erro ao gerar arte: {e}")
                    st.code(traceback.format_exc())

    with col2:
        if st.button("📋 GERAR PAINEL DE EVIDÊNCIAS", width="stretch"):
            with st.spinner("Gerando Painel de Evidências..."):
                try:
                    plt.close('all')
                    gc.collect()
                    ev_path = graphic_renderer.generate_evidence_grid(
                        evidence_list, rodada_sel, n_jogos, tipo_filtro
                    )
                    if ev_path:
                        st.success("Evidências geradas! ✅")
                        st.image(ev_path)
                        with open(ev_path, "rb") as f:
                            st.download_button(
                                "⬇️ BAIXAR EVIDÊNCIAS (300 DPI)",
                                f,
                                file_name=f"Evidencias_R{rodada_sel}.png",
                                mime="image/png",
                            )
                    plt.close('all')
                    gc.collect()
                except Exception as e:
                    st.error(f"Erro ao gerar evidências: {e}")
                    st.code(traceback.format_exc())

except Exception as e:
    st.error(f"⚠️ Erro inesperado: {e}")
    st.code(traceback.format_exc())
