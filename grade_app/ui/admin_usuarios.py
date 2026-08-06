"""Painel de administração de usuários (aba `usuarios` do Google Sheets).

Só é chamado para perfil admin (ver grade_app.auth.eh_admin). Permite ver os
usuários cadastrados, adicionar um novo, ativar/desativar e redefinir senha
— tudo sem precisar abrir a planilha nem rodar script no terminal. A senha
nunca é guardada em texto puro: o hash+salt é calculado aqui e só o
resultado vai para a planilha.
"""
import streamlit as st

from .. import google_sheets
from ..auth import PERFIL_USUARIO, PERFIS_VALIDOS, gerar_hash_senha, gerar_salt


def _carregar_usuarios_admin():
    try:
        return google_sheets.carregar_usuarios()
    except Exception:
        return None


def _registrar_log_admin(evento: str, detalhe: str) -> None:
    google_sheets.registrar_log(
        st.session_state.get("usuario", ""),
        st.session_state.get("nome", ""),
        evento,
        "sucesso",
        detalhe,
    )


def render() -> None:
    st.markdown("### 👤 Gerenciar usuários")
    st.caption("Cadastro de login/senha da aba `usuarios` do Google Sheets — visível só para o perfil admin.")

    registros = _carregar_usuarios_admin()
    if registros is None:
        st.warning("Não foi possível carregar a lista de usuários da planilha agora. Tente novamente em instantes.")
        return

    logins_existentes = {str(r.get("usuario", "")).strip() for r in registros if str(r.get("usuario", "")).strip()}

    with st.expander(f"Usuários cadastrados ({len(registros)})"):
        if registros:
            tabela = [
                {
                    "usuario": r.get("usuario", ""),
                    "nome": r.get("nome", ""),
                    "perfil": r.get("perfil", ""),
                    "ativo": r.get("ativo", ""),
                }
                for r in registros
            ]
            st.dataframe(tabela, use_container_width=True, hide_index=True)
        else:
            st.caption("Nenhum usuário cadastrado ainda.")

    with st.expander("➕ Adicionar novo usuário"):
        perfis_ordenados = sorted(PERFIS_VALIDOS)
        with st.form("form_add_usuario", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                novo_login = st.text_input("Usuário (login)")
                novo_nome = st.text_input("Nome")
                nova_senha = st.text_input("Senha", type="password")
            with c2:
                novo_perfil = st.selectbox("Perfil", perfis_ordenados, index=perfis_ordenados.index(PERFIL_USUARIO))
                novo_ativo = st.selectbox("Ativo", ["SIM", "NAO"], index=0)
                confirmar_senha = st.text_input("Confirmar senha", type="password")
            enviar = st.form_submit_button("Adicionar usuário", use_container_width=True)

        if enviar:
            login_normalizado = novo_login.strip()
            if not login_normalizado or not novo_nome.strip():
                st.error("Preencha usuário e nome.")
            elif login_normalizado in logins_existentes:
                st.error(f"Já existe um usuário com o login '{login_normalizado}'.")
            elif not nova_senha:
                st.error("A senha não pode ser vazia.")
            elif nova_senha != confirmar_senha:
                st.error("As senhas não coincidem.")
            else:
                salt = gerar_salt()
                senha_hash = gerar_hash_senha(nova_senha, salt)
                try:
                    google_sheets.adicionar_usuario(
                        login_normalizado, novo_nome.strip(), senha_hash, salt, novo_perfil, novo_ativo,
                    )
                    _registrar_log_admin("usuario_criado", f"novo usuario: {login_normalizado}")
                    st.success(f"Usuário '{login_normalizado}' adicionado.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Não foi possível salvar na planilha: {exc}")

    if not registros:
        return

    with st.expander("🔧 Ativar/desativar ou redefinir senha"):
        opcoes = [r.get("usuario", "") for r in registros if str(r.get("usuario", "")).strip()]
        selecionado = st.selectbox("Usuário", opcoes, key="admin_usuario_selecionado")
        dados_sel = next((r for r in registros if str(r.get("usuario", "")).strip() == selecionado), None)

        if dados_sel:
            ativo_atual = str(dados_sel.get("ativo", "")).strip().upper()
            st.caption(f"Nome: {dados_sel.get('nome', '')} — Perfil: {dados_sel.get('perfil', '')} — Ativo: {ativo_atual}")

            col_a, col_b = st.columns(2)
            with col_a:
                novo_status = "NAO" if ativo_atual == "SIM" else "SIM"
                rotulo_botao = "Desativar usuário" if ativo_atual == "SIM" else "Ativar usuário"
                if st.button(rotulo_botao, key="botao_toggle_ativo", use_container_width=True):
                    try:
                        google_sheets.atualizar_status_usuario(selecionado, novo_status)
                        _registrar_log_admin("usuario_atualizado", f"{selecionado} -> ativo={novo_status}")
                        st.success("Status atualizado.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Não foi possível atualizar: {exc}")

            with col_b:
                with st.form("form_redefinir_senha"):
                    nova_senha_reset = st.text_input("Nova senha", type="password")
                    redefinir = st.form_submit_button("Redefinir senha", use_container_width=True)
                if redefinir:
                    if not nova_senha_reset:
                        st.error("Digite a nova senha.")
                    else:
                        salt = gerar_salt()
                        senha_hash = gerar_hash_senha(nova_senha_reset, salt)
                        try:
                            google_sheets.redefinir_senha_usuario(selecionado, senha_hash, salt)
                            _registrar_log_admin("usuario_atualizado", f"senha redefinida: {selecionado}")
                            st.success("Senha redefinida.")
                        except Exception as exc:
                            st.error(f"Não foi possível redefinir: {exc}")
