"""Barra lateral: conta logada, upload de PDF/configuracao e opcoes de seguranca operacional."""
import streamlit as st

from ..auth import logout
from ..config import caminho_config_cliente

_ROTULO_PERFIL = {
    "admin": "Administrador",
    "usuario": "Usuário",
    "visualizador": "Visualizador (somente leitura)",
}


def _render_conta():
    nome = st.session_state.get("nome", "")
    perfil = st.session_state.get("perfil", "")
    st.caption(f"👤 {nome} — {_ROTULO_PERFIL.get(perfil, perfil)}")
    if st.button("Sair", key="botao_logout", use_container_width=True):
        logout()
    st.divider()


def render_sidebar(cliente_id, cliente_nome, cliente_slug):
    """Renderiza a barra lateral e retorna (pdf_files, config_file, bloquear_criticos)."""
    with st.sidebar:
        _render_conta()
        st.success(f"Cliente selecionado: {cliente_nome}")
        st.header("1) Arquivos")
        pdf_files = st.file_uploader(
            f"PDF de pedido TOTVS - {cliente_nome} (até 5 arquivos)",
            type=["pdf"], accept_multiple_files=True, key=f"pdf_{cliente_slug}",
        )
        config_file = st.file_uploader(
            f"Configuração DE/PARA {cliente_nome} opcional (.xlsx)", type=["xlsx"], key=f"config_{cliente_slug}",
        )
        config_salva_path = caminho_config_cliente(cliente_id)
        if config_salva_path.exists():
            st.caption(f"Usando configuração salva deste cliente ({config_salva_path.name}).")
        else:
            st.caption("Ainda não existe configuração salva para este cliente. Ao editar a aba CONFIGURAÇÕES, o sistema salvará automaticamente.")
        if pdf_files and len(pdf_files) > 5:
            st.warning("Você enviou mais de 5 PDFs. O sistema vai processar apenas os 5 primeiros para manter a rotina rápida.")
        st.divider()
        st.header("2) Segurança operacional")
        bloquear_criticos = st.checkbox("Bloquear NOTA FINAL quando houver validação crítica", value=False, key=f"bloquear_{cliente_slug}")
        st.caption("Recomendado: usar a nota apenas depois de conferir as validações.")
        st.divider()
        if st.button("Voltar para tela inicial", key=f"voltar_{cliente_slug}"):
            st.session_state.pop("cliente_atual", None)
            st.rerun()
    return pdf_files, config_file, bloquear_criticos
