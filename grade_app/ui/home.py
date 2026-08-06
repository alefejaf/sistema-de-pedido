"""Tela inicial: escolha do cliente."""
import streamlit as st

from ..auth import eh_admin, logout
from ..config import APP_NAME, CLIENTES
from .admin_usuarios import render as render_admin_usuarios
from .styles import aplicar_estilo_global

_ROTULO_PERFIL = {
    "admin": "Administrador",
    "usuario": "Usuário",
    "visualizador": "Visualizador (somente leitura)",
}


def exibir_tela_inicial():
    """Tela inicial de escolha do cliente."""
    st.set_page_config(page_title=APP_NAME, page_icon="📦", layout="wide")
    aplicar_estilo_global()
    with st.sidebar:
        nome = st.session_state.get("nome", "")
        perfil = st.session_state.get("perfil", "")
        st.caption(f"👤 {nome} — {_ROTULO_PERFIL.get(perfil, perfil)}")
        if st.button("Sair", key="botao_logout_home", use_container_width=True):
            logout()
    st.title("📦 Gerador Automático de Grade")
    st.caption("Escolha o cliente para abrir uma página isolada com PDF, DE/PARA e configuração própria.")

    st.markdown("## Escolha o cliente")
    c1, c2, c3, c4 = st.columns(4)
    colunas = [c1, c2, c3, c4]
    for col, (cliente_id, cfg) in zip(colunas, CLIENTES.items()):
        with col:
            with st.container(border=True):
                st.markdown(f"### {cfg['icone']} {cfg['nome']}")
                st.markdown(f'<p class="grade-card-subtitulo">{cfg["subtitulo"]}</p>', unsafe_allow_html=True)
                st.caption(cfg["descricao"])
                if st.button(f"Abrir {cfg['nome']}", key=f"btn_cliente_{cliente_id}", use_container_width=True):
                    st.session_state["cliente_atual"] = cliente_id
                    st.rerun()

    if eh_admin(st.session_state.get("perfil", "")):
        st.divider()
        render_admin_usuarios()

    st.divider()
    st.markdown("### Como funciona")
    st.write(
        "Cada cliente roda separado: upload do PDF, configuração DE/PARA, ordem de lojas, "
        "produtos e downloads ficam direcionados para o cliente escolhido. Isso evita misturar "
        "configuração de Ultrabox, Bigbox, Costa e Fort."
    )
