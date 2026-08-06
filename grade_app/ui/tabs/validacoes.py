"""Aba VALIDACOES: alertas automaticos e diagnostico tecnico do PDF."""
import streamlit as st

from ..styles import rotulo_severidade


def render(validacoes, controle_extracao, pode_baixar=True):
    st.subheader("Validações automáticas")
    validacoes_exibicao = validacoes.copy()
    if "Severidade" in validacoes_exibicao.columns:
        validacoes_exibicao["Severidade"] = validacoes_exibicao["Severidade"].map(rotulo_severidade)
    st.dataframe(validacoes_exibicao, use_container_width=True, height=420)
    with st.expander("Controle de extração pedido a pedido", expanded=True):
        controle_exibicao = controle_extracao.copy()
        if "Status" in controle_exibicao.columns:
            controle_exibicao["Status"] = controle_exibicao["Status"].map(rotulo_severidade)
        st.dataframe(controle_exibicao, use_container_width=True)
    with st.expander("Diagnóstico técnico do PDF"):
        debug = st.session_state.get("debug_pdf_parser", {})
        if debug:
            st.json(debug)
        texto_debug = st.session_state.get("debug_texto_pdf", "")
        if texto_debug:
            if pode_baixar:
                st.download_button(
                    "⬇️ Baixar texto extraído para diagnóstico",
                    data=texto_debug.encode("utf-8", errors="ignore"),
                    file_name="diagnostico_texto_extraido_pdf.txt",
                    mime="text/plain",
                )
            else:
                st.info("Seu perfil (visualizador) não tem permissão para baixar arquivos.")
            st.text_area("Prévia do texto extraído", texto_debug[:6000], height=320)
