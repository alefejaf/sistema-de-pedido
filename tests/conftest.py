"""Fixtures compartilhadas.

Garantias de segurança da suíte (valem para TODOS os testes, automaticamente):

* ``_isolar_dados_reais``  - redireciona ``configs/`` e ``backups_config/`` para
  uma pasta temporária; nenhum teste consegue gravar nos DE/PARA reais.
* ``_bloquear_rede``       - qualquer conexão de rede externa falha na hora
  (nunca chega ao Google Sheets real nem a qualquer outro serviço).
* ``_configs_do_repo_intactos`` - no fim da sessão confere (SHA-256) que os
  .xlsx de configuração versionados não mudaram.
"""
from __future__ import annotations

import hashlib
import socket
import sys
from pathlib import Path
from typing import Dict, List

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))


# ---------------------------------------------------------------------------
# Proteções automáticas
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _bloquear_rede(monkeypatch):
    """Falha se algo tentar abrir conexão com host que não seja local."""
    real_connect = socket.socket.connect

    def connect_guard(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in ("127.0.0.1", "::1", "localhost") and not str(host).startswith("/"):
            raise RuntimeError(f"Rede bloqueada nos testes: tentativa de conectar em {address!r}")
        return real_connect(self, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect_guard)


@pytest.fixture(autouse=True)
def _isolar_dados_reais(tmp_path, monkeypatch):
    """Aponta configs/ e backups_config/ para tmp_path em todos os testes."""
    from grade_app import config

    cfg_dir = tmp_path / "configs"
    bkp_dir = tmp_path / "backups_config"
    monkeypatch.setattr(config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(config, "BACKUP_CONFIG_DIR", bkp_dir)
    return cfg_dir, bkp_dir


def _hash_arquivos(arquivos) -> Dict[str, str]:
    return {
        str(p.relative_to(RAIZ)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(arquivos)
    }


@pytest.fixture(scope="session", autouse=True)
def _configs_do_repo_intactos():
    arquivos = list((RAIZ / "configs").glob("*.xlsx")) + [RAIZ / "config_padrao.xlsx"]
    antes = _hash_arquivos(arquivos)
    yield
    depois = _hash_arquivos(arquivos)
    assert antes == depois, "Os testes alteraram arquivos de configuração do repositório!"
    assert not (RAIZ / "backups_config").exists() or not any((RAIZ / "backups_config").iterdir()), (
        "Os testes gravaram em backups_config/ real!"
    )


# ---------------------------------------------------------------------------
# Google Sheets simulado (em memória)
# ---------------------------------------------------------------------------
class FakeCelula:
    def __init__(self, row: int, col: int):
        self.row, self.col = row, col


class FakeWorksheet:
    """Imita o mínimo de gspread.Worksheet usado por google_sheets.py."""

    def __init__(self, cabecalho: List[str], linhas: List[list] | None = None):
        self.cabecalho = cabecalho
        self.linhas: List[list] = [list(l) for l in (linhas or [])]
        self.falhar_em_append = False

    def get_all_records(self):
        return [dict(zip(self.cabecalho, l)) for l in self.linhas]

    def append_row(self, valores, value_input_option=None):
        if self.falhar_em_append:
            raise RuntimeError("falha simulada de escrita")
        self.linhas.append(list(valores))

    def find(self, valor, in_column=None):
        for idx, linha in enumerate(self.linhas, start=2):  # linha 1 = cabeçalho
            col = (in_column or 1) - 1
            if col < len(linha) and str(linha[col]) == str(valor):
                return FakeCelula(idx, col + 1)
        return None

    def update_cell(self, row, col, valor):
        self.linhas[row - 2][col - 1] = valor


class FakeSpreadsheet:
    def __init__(self, usuarios: FakeWorksheet, logs: FakeWorksheet):
        self._abas = {"usuarios": usuarios, "logs": logs}

    def worksheet(self, nome: str) -> FakeWorksheet:
        if nome not in self._abas:
            raise KeyError(f"aba inexistente: {nome}")
        return self._abas[nome]


CAB_USUARIOS = ["usuario", "nome", "senha_hash", "salt", "perfil", "ativo"]
CAB_LOGS = ["data_hora", "usuario", "nome", "evento", "status", "detalhe"]

# Senhas fictícias usadas SÓ nos testes.
SENHAS = {
    "admin.teste": "Senha-Admin-123",
    "user.teste": "Senha-User-123",
    "view.teste": "Senha-View-123",
    "inativo.teste": "Senha-Inativo-123",
    "perfil.ruim": "Senha-Ruim-123",
}


def _linha(auth, login, nome, perfil, ativo="SIM"):
    salt = "ab" * 16
    return [login, nome, auth.gerar_hash_senha(SENHAS[login], salt), salt, perfil, ativo]


@pytest.fixture
def planilha_fake(monkeypatch):
    """Substitui a planilha real por uma em memória e limpa o cache do app.

    Exercita o código REAL de ``grade_app.google_sheets`` contra o fake,
    sem nenhuma credencial e sem rede.
    """
    from grade_app import auth, google_sheets

    usuarios = FakeWorksheet(CAB_USUARIOS, [
        _linha(auth, "admin.teste", "Admin Teste", "admin"),
        _linha(auth, "user.teste", "Usuario Teste", "usuario"),
        _linha(auth, "view.teste", "Visualizador Teste", "visualizador"),
        _linha(auth, "inativo.teste", "Inativo Teste", "usuario", ativo="NAO"),
        _linha(auth, "perfil.ruim", "Perfil Ruim", "superuser"),
    ])
    logs = FakeWorksheet(CAB_LOGS)
    planilha = FakeSpreadsheet(usuarios, logs)

    def _planilha_fake():
        return planilha

    monkeypatch.setattr(google_sheets, "_planilha", _planilha_fake)
    google_sheets.carregar_usuarios.clear()
    yield planilha
    google_sheets.carregar_usuarios.clear()


@pytest.fixture
def master_secrets(monkeypatch):
    """Define uma conta master fictícia em st.secrets."""
    import streamlit as st

    from grade_app import auth

    salt = "cd" * 16
    secrets = {
        "master": {
            "usuario": "master.teste",
            "nome": "Master Teste",
            "salt": salt,
            "senha_hash": auth.gerar_hash_senha("Senha-Master-123", salt),
            "perfil": "admin",
        }
    }
    monkeypatch.setattr(st, "secrets", secrets, raising=False)
    return secrets
