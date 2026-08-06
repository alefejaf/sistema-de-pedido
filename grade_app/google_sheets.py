"""Conexão com a planilha Google Sheets usada para login e logs de acesso.

Credenciais (conta de serviço do Google Cloud) e o ID da planilha vêm de
`st.secrets` — nunca do código. Veja `.streamlit/secrets.toml.example` para
o formato esperado das chaves `[gcp_service_account]` e `[google_sheets]`.

Aba `usuarios`: usuario | nome | senha_hash | salt | perfil | ativo
Aba `logs`:     data_hora | usuario | nome | evento | status | detalhe
"""
from datetime import datetime
from typing import List, Dict

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

ABA_USUARIOS = "usuarios"
ABA_LOGS = "logs"
_CAMPOS_LOG = ["data_hora", "usuario", "nome", "evento", "status", "detalhe"]

# Ordem fixa das colunas da aba `usuarios` (usada para achar/atualizar linhas).
_COL_USUARIO = 1
_COL_NOME = 2
_COL_SENHA_HASH = 3
_COL_SALT = 4
_COL_PERFIL = 5
_COL_ATIVO = 6


@st.cache_resource(show_spinner=False)
def _cliente_gspread() -> gspread.Client:
    info = dict(st.secrets["gcp_service_account"])
    # Se secrets.toml usar string literal (aspas simples) para private_key,
    # o "\n" chega aqui como texto literal (\ + n) em vez de quebra de linha
    # de verdade — normaliza os dois formatos para não depender de qual
    # tipo de aspas a pessoa usou ao colar a chave.
    if "private_key" in info:
        info["private_key"] = info["private_key"].replace("\\n", "\n")
    credenciais = Credentials.from_service_account_info(info, scopes=_SCOPES)
    return gspread.authorize(credenciais)


def _planilha() -> gspread.Spreadsheet:
    sheet_id = st.secrets["google_sheets"]["sheet_id"]
    return _cliente_gspread().open_by_key(sheet_id)


@st.cache_data(ttl=60, show_spinner=False)
def carregar_usuarios() -> List[Dict]:
    """Lê todas as linhas da aba `usuarios`. Propaga exceção se a planilha
    estiver inacessível — quem decide o que fazer com isso é `auth.py`."""
    aba = _planilha().worksheet(ABA_USUARIOS)
    return aba.get_all_records()


def adicionar_usuario(usuario: str, nome: str, senha_hash: str, salt: str, perfil: str, ativo: str = "SIM") -> None:
    """Acrescenta uma linha na aba `usuarios`. Não verifica duplicidade —
    quem chama (a UI) já garante que o login não existe antes de chamar."""
    aba = _planilha().worksheet(ABA_USUARIOS)
    aba.append_row([usuario, nome, senha_hash, salt, perfil, ativo], value_input_option="RAW")
    carregar_usuarios.clear()


def atualizar_status_usuario(usuario: str, ativo: str) -> None:
    """Atualiza a coluna `ativo` da linha do usuário. Levanta ValueError se
    o usuário não existir na planilha."""
    aba = _planilha().worksheet(ABA_USUARIOS)
    celula = aba.find(usuario, in_column=_COL_USUARIO)
    if celula is None:
        raise ValueError(f"Usuário '{usuario}' não encontrado na planilha.")
    aba.update_cell(celula.row, _COL_ATIVO, ativo)
    carregar_usuarios.clear()


def redefinir_senha_usuario(usuario: str, senha_hash: str, salt: str) -> None:
    """Atualiza senha_hash e salt da linha do usuário. Levanta ValueError se
    o usuário não existir na planilha."""
    aba = _planilha().worksheet(ABA_USUARIOS)
    celula = aba.find(usuario, in_column=_COL_USUARIO)
    if celula is None:
        raise ValueError(f"Usuário '{usuario}' não encontrado na planilha.")
    aba.update_cell(celula.row, _COL_SENHA_HASH, senha_hash)
    aba.update_cell(celula.row, _COL_SALT, salt)
    carregar_usuarios.clear()


def registrar_log(usuario: str, nome: str, evento: str, status: str, detalhe: str = "") -> None:
    """Acrescenta uma linha na aba `logs`. Nunca levanta exceção — login e
    logout não podem ser bloqueados por uma falha de log."""
    try:
        aba = _planilha().worksheet(ABA_LOGS)
        aba.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            usuario,
            nome,
            evento,
            status,
            detalhe,
        ], value_input_option="RAW")
    except Exception:
        pass
