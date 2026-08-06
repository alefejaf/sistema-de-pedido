"""Autenticação, perfis de acesso e log de acesso via Google Sheets.

Usuários e senhas vêm de uma planilha Google Sheets (aba `usuarios`), lida
via `grade_app.google_sheets`. As credenciais do Google (conta de serviço) e
o ID da planilha vêm de `st.secrets` — nunca hardcoded nem commitados no
código. A senha em si nunca é guardada; só o hash PBKDF2-HMAC-SHA256 com
salt. Veja `.streamlit/secrets.toml.example` para o formato esperado e
`scripts/gerar_hash_senha.py` para gerar o hash+salt de uma senha nova.

Existe também uma conta master opcional (seção `[master]` em `st.secrets`),
independente do Google Sheets: ela continua funcionando mesmo se a planilha
estiver fora do ar, para nunca deixar o administrador trancado para fora.
"""
import hashlib
import hmac
import os
from typing import Dict, Optional, Tuple

import streamlit as st

from . import google_sheets

PERFIL_ADMIN = "admin"
PERFIL_USUARIO = "usuario"
PERFIL_VISUALIZADOR = "visualizador"
PERFIS_VALIDOS = {PERFIL_ADMIN, PERFIL_USUARIO, PERFIL_VISUALIZADOR}

_PBKDF2_ITERACOES = 200_000


def pode_editar_configuracoes(perfil: str) -> bool:
    """Só o perfil visualizador fica sem permissão de editar/salvar DE/PARA."""
    return perfil in (PERFIL_ADMIN, PERFIL_USUARIO)


def pode_baixar_arquivos(perfil: str) -> bool:
    """Só o perfil visualizador fica sem permissão de baixar Excel/diagnóstico."""
    return perfil in (PERFIL_ADMIN, PERFIL_USUARIO)


def eh_admin(perfil: str) -> bool:
    """Só o perfil admin pode gerenciar usuários (aba usuarios do Sheets)."""
    return perfil == PERFIL_ADMIN


def gerar_salt() -> str:
    return os.urandom(16).hex()


def gerar_hash_senha(senha: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", senha.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERACOES
    ).hex()


def _verificar_senha(senha: str, salt: str, hash_armazenado: str) -> bool:
    try:
        calculado = gerar_hash_senha(senha, salt)
        return hmac.compare_digest(calculado, str(hash_armazenado).strip())
    except Exception:
        return False


def _carregar_master() -> Optional[dict]:
    """Lê a conta master de st.secrets (seção [master]). None se não
    configurada. Essa conta funciona mesmo com o Google Sheets fora do ar."""
    try:
        return dict(st.secrets["master"])
    except Exception:
        return None


def _autenticar_master(login: str, senha: str, master: Optional[dict]) -> Optional[dict]:
    if not master:
        return None
    if login != str(master.get("usuario", "")).strip():
        return None
    salt = str(master.get("salt", "")).strip()
    hash_armazenado = str(master.get("senha_hash", "")).strip()
    if not salt or not hash_armazenado or not _verificar_senha(senha, salt, hash_armazenado):
        return None
    perfil = str(master.get("perfil", "")).strip().lower() or PERFIL_ADMIN
    if perfil not in PERFIS_VALIDOS:
        perfil = PERFIL_ADMIN
    return {"nome": master.get("nome") or login, "perfil": perfil}


def _carregar_usuarios() -> Optional[Dict[str, dict]]:
    """Lê os usuários da planilha Google Sheets. None se a planilha estiver
    inacessível (Sheets fora do ar, secrets ausentes, sem permissão etc.)."""
    try:
        registros = google_sheets.carregar_usuarios()
    except Exception:
        return None
    usuarios = {}
    for linha in registros:
        login = str(linha.get("usuario", "")).strip()
        if login:
            usuarios[login] = linha
    return usuarios


def _autenticar(login: str, senha: str, usuarios: Dict[str, dict]) -> Tuple[Optional[dict], str]:
    """Retorna (dados, motivo). dados = {'nome', 'perfil'} se a senha bater,
    senão None e motivo indica o evento a logar (nunca a senha)."""
    dados = usuarios.get(login)
    if not dados:
        return None, "usuario_nao_encontrado"

    ativo = str(dados.get("ativo", "")).strip().upper()
    if ativo != "SIM":
        return None, "usuario_inativo"

    salt = str(dados.get("salt", "")).strip()
    hash_armazenado = str(dados.get("senha_hash", "")).strip()
    if not salt or not hash_armazenado or not _verificar_senha(senha, salt, hash_armazenado):
        return None, "senha_invalida"

    perfil = str(dados.get("perfil", "")).strip().lower()
    if perfil not in PERFIS_VALIDOS:
        return None, "perfil_invalido"

    return {"nome": dados.get("nome") or login, "perfil": perfil}, "login_sucesso"


def _renderizar_tela_login(usuarios: Optional[Dict[str, dict]], master: Optional[dict]) -> None:
    st.set_page_config(page_title="Login - Gerador de Grade", page_icon="🔒", layout="centered")
    st.title("🔒 Acesso restrito")
    st.caption("Entre com seu usuário e senha para abrir o Gerador Automático de Grade.")
    if usuarios is None:
        st.warning(
            "Não foi possível conectar à planilha de usuários no momento. "
            "Só a conta master consegue entrar enquanto isso."
        )

    with st.form("form_login"):
        login = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar", use_container_width=True)

    if not entrar:
        return

    login_normalizado = login.strip()

    dados_master = _autenticar_master(login_normalizado, senha, master)
    if dados_master is not None:
        st.session_state["autenticado"] = True
        st.session_state["usuario"] = login_normalizado
        st.session_state["nome"] = dados_master["nome"]
        st.session_state["perfil"] = dados_master["perfil"]
        google_sheets.registrar_log(login_normalizado, dados_master["nome"], "login_sucesso", "sucesso", "conta master")
        st.rerun()
        return

    dados, motivo = _autenticar(login_normalizado, senha, usuarios or {})

    if dados is None:
        st.error("Usuário ou senha inválidos.")
        evento = "usuario_inativo" if motivo == "usuario_inativo" else "login_falha"
        google_sheets.registrar_log(login_normalizado or "(vazio)", "", evento, "falha", motivo)
        return

    st.session_state["autenticado"] = True
    st.session_state["usuario"] = login_normalizado
    st.session_state["nome"] = dados["nome"]
    st.session_state["perfil"] = dados["perfil"]
    google_sheets.registrar_log(login_normalizado, dados["nome"], "login_sucesso", "sucesso")
    st.rerun()


def exigir_login() -> None:
    """Bloqueia o restante do app até o usuário se autenticar.

    Deve ser a primeira chamada de main(). Se já autenticado, retorna sem
    emitir nenhum comando Streamlit, mantendo o st.set_page_config do
    restante do app como o primeiro comando da execução. Se a planilha do
    Google Sheets estiver inacessível E não houver conta master configurada,
    mostra uma mensagem amigável e nunca libera o sistema. Se houver conta
    master configurada, ela consegue entrar mesmo com o Sheets fora do ar.
    """
    if st.session_state.get("autenticado"):
        return

    usuarios = _carregar_usuarios()
    master = _carregar_master()

    if usuarios is None and master is None:
        st.set_page_config(page_title="Login - Gerador de Grade", page_icon="🔒", layout="centered")
        st.title("🔒 Acesso restrito")
        st.error(
            "Não foi possível conectar à planilha de usuários e nenhuma conta "
            "master está configurada. Avise o administrador."
        )
        st.stop()

    _renderizar_tela_login(usuarios, master)
    st.stop()


def logout() -> None:
    """Registra o logout, limpa a sessão (autenticação + cliente ativo) e reinicia."""
    google_sheets.registrar_log(
        st.session_state.get("usuario", ""),
        st.session_state.get("nome", ""),
        "logout",
        "sucesso",
    )
    for chave in ["autenticado", "usuario", "nome", "perfil", "cliente_atual"]:
        st.session_state.pop(chave, None)
    st.rerun()
