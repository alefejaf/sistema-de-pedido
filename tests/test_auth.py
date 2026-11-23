"""grade_app.auth + grade_app.google_sheets: autenticação, perfis e logs.

O Google Sheets é SIMULADO (``planilha_fake`` em conftest.py): o código real
de ``google_sheets.py`` roda contra uma planilha em memória. Nenhum teste usa
credencial, rede ou a planilha real; ``_cliente_gspread`` (que abriria a
conexão real) é bloqueado de propósito.
"""
import pytest

from grade_app import auth, google_sheets
from conftest import SENHAS


@pytest.fixture(autouse=True)
def _nunca_conectar_no_google_real(monkeypatch):
    def _proibido():
        raise AssertionError("Teste tentou abrir conexão REAL com o Google Sheets!")

    monkeypatch.setattr(google_sheets, "_cliente_gspread", _proibido)


# --------------------------------------------------------------------------
# Hash de senha
# --------------------------------------------------------------------------
def test_hash_e_deterministico_para_mesma_senha_e_salt():
    salt = auth.gerar_salt()
    assert auth.gerar_hash_senha("abc", salt) == auth.gerar_hash_senha("abc", salt)


def test_hash_muda_com_salt_e_com_senha():
    s1, s2 = auth.gerar_salt(), auth.gerar_salt()
    assert s1 != s2 and len(s1) == 32
    assert auth.gerar_hash_senha("abc", s1) != auth.gerar_hash_senha("abc", s2)
    assert auth.gerar_hash_senha("abc", s1) != auth.gerar_hash_senha("abd", s1)


def test_hash_e_pbkdf2_sha256_200k_iteracoes():
    import hashlib

    salt = "00" * 16
    esperado = hashlib.pbkdf2_hmac("sha256", b"senha", bytes.fromhex(salt), 200_000).hex()
    assert auth.gerar_hash_senha("senha", salt) == esperado
    assert len(esperado) == 64


def test_hash_nao_contem_a_senha():
    h = auth.gerar_hash_senha("MinhaSenhaSecreta", auth.gerar_salt())
    assert "MinhaSenhaSecreta" not in h


def test_verificar_senha():
    salt = auth.gerar_salt()
    h = auth.gerar_hash_senha("certa", salt)
    assert auth._verificar_senha("certa", salt, h) is True
    assert auth._verificar_senha("errada", salt, h) is False
    assert auth._verificar_senha("certa", salt, " " + h + " ") is True  # espaços da planilha
    assert auth._verificar_senha("certa", "salt-nao-hex", h) is False   # nunca levanta
    assert auth._verificar_senha("certa", salt, "") is False


# --------------------------------------------------------------------------
# Matriz de permissões
# --------------------------------------------------------------------------
@pytest.mark.parametrize("perfil,editar,baixar,admin", [
    ("admin", True, True, True),
    ("usuario", True, True, False),
    ("visualizador", False, False, False),
    ("", False, False, False),
    ("ADMIN", False, False, False),      # perfil é sensível a caixa nas funções
    ("superuser", False, False, False),
    (None, False, False, False),
])
def test_matriz_de_permissoes(perfil, editar, baixar, admin):
    assert auth.pode_editar_configuracoes(perfil) is editar
    assert auth.pode_baixar_arquivos(perfil) is baixar
    assert auth.eh_admin(perfil) is admin


def test_so_admin_gerencia_usuarios_e_visualizador_nao_escreve_nada():
    assert [p for p in auth.PERFIS_VALIDOS if auth.eh_admin(p)] == ["admin"]
    assert [p for p in auth.PERFIS_VALIDOS if not auth.pode_editar_configuracoes(p)] == ["visualizador"]


# --------------------------------------------------------------------------
# _autenticar (usuários da planilha)
# --------------------------------------------------------------------------
def _usuarios(planilha_fake):
    return auth._carregar_usuarios()


@pytest.mark.parametrize("login,perfil", [
    ("admin.teste", "admin"), ("user.teste", "usuario"), ("view.teste", "visualizador"),
])
def test_login_correto_devolve_nome_e_perfil(planilha_fake, login, perfil):
    dados, motivo = auth._autenticar(login, SENHAS[login], _usuarios(planilha_fake))
    assert motivo == "login_sucesso"
    assert dados["perfil"] == perfil and dados["nome"]


def test_senha_errada(planilha_fake):
    dados, motivo = auth._autenticar("admin.teste", "errada", _usuarios(planilha_fake))
    assert dados is None and motivo == "senha_invalida"


def test_usuario_inexistente(planilha_fake):
    assert auth._autenticar("fantasma", "x", _usuarios(planilha_fake)) == (None, "usuario_nao_encontrado")


def test_usuario_inativo_nao_entra_mesmo_com_senha_certa(planilha_fake):
    dados, motivo = auth._autenticar("inativo.teste", SENHAS["inativo.teste"], _usuarios(planilha_fake))
    assert dados is None and motivo == "usuario_inativo"


def test_perfil_invalido_nao_entra(planilha_fake):
    dados, motivo = auth._autenticar("perfil.ruim", SENHAS["perfil.ruim"], _usuarios(planilha_fake))
    assert dados is None and motivo == "perfil_invalido"


def test_ativo_aceita_sim_em_qualquer_caixa(planilha_fake):
    planilha_fake.worksheet("usuarios").update_cell(3, 6, " sim ")  # user.teste
    google_sheets.carregar_usuarios.clear()
    dados, _ = auth._autenticar("user.teste", SENHAS["user.teste"], _usuarios(planilha_fake))
    assert dados is not None


def test_perfil_na_planilha_e_normalizado_para_minusculas(planilha_fake):
    planilha_fake.worksheet("usuarios").update_cell(2, 5, "ADMIN")
    google_sheets.carregar_usuarios.clear()
    dados, _ = auth._autenticar("admin.teste", SENHAS["admin.teste"], _usuarios(planilha_fake))
    assert dados["perfil"] == "admin"


@pytest.mark.parametrize("campo_col", [3, 4])  # senha_hash, salt
def test_usuario_sem_hash_ou_salt_nunca_entra(planilha_fake, campo_col):
    planilha_fake.worksheet("usuarios").update_cell(3, campo_col, "")
    google_sheets.carregar_usuarios.clear()
    dados, motivo = auth._autenticar("user.teste", "", _usuarios(planilha_fake))
    assert dados is None and motivo == "senha_invalida"


def test_senha_vazia_nao_entra(planilha_fake):
    assert auth._autenticar("user.teste", "", _usuarios(planilha_fake))[0] is None


def test_nome_vazio_usa_o_login(planilha_fake):
    planilha_fake.worksheet("usuarios").update_cell(3, 2, "")
    google_sheets.carregar_usuarios.clear()
    dados, _ = auth._autenticar("user.teste", SENHAS["user.teste"], _usuarios(planilha_fake))
    assert dados["nome"] == "user.teste"


def test_login_e_sensivel_a_caixa(planilha_fake):
    assert auth._autenticar("ADMIN.TESTE", SENHAS["admin.teste"], _usuarios(planilha_fake))[0] is None


def test_planilha_inacessivel_devolve_none_e_loga_motivo(monkeypatch, capsys):
    def boom():
        raise RuntimeError("sheets fora do ar")

    monkeypatch.setattr(google_sheets, "_planilha", boom)
    google_sheets.carregar_usuarios.clear()
    assert auth._carregar_usuarios() is None
    assert "sheets fora do ar" in capsys.readouterr().out


def test_linhas_sem_usuario_sao_ignoradas(planilha_fake):
    planilha_fake.worksheet("usuarios").append_row(["", "Sem Login", "x", "y", "usuario", "SIM"])
    google_sheets.carregar_usuarios.clear()
    assert "" not in auth._carregar_usuarios()


# --------------------------------------------------------------------------
# Conta master
# --------------------------------------------------------------------------
def test_master_entra_com_senha_certa(master_secrets):
    master = auth._carregar_master()
    dados = auth._autenticar_master("master.teste", "Senha-Master-123", master)
    assert dados == {"nome": "Master Teste", "perfil": "admin"}


@pytest.mark.parametrize("login,senha", [("master.teste", "errada"), ("outro", "Senha-Master-123"), ("", "")])
def test_master_rejeita_credenciais_erradas(master_secrets, login, senha):
    assert auth._autenticar_master(login, senha, auth._carregar_master()) is None


def test_master_ausente_nos_secrets():
    assert auth._carregar_master() is None
    assert auth._autenticar_master("x", "y", None) is None


def test_master_sem_hash_ou_salt_nao_entra(master_secrets):
    master = dict(master_secrets["master"], senha_hash="")
    assert auth._autenticar_master("master.teste", "Senha-Master-123", master) is None


def test_master_com_perfil_invalido_vira_admin_caracterizacao(master_secrets):
    """CARACTERIZAÇÃO: perfil inválido/ausente na conta master cai para 'admin'
    (fail-open, ao contrário dos usuários da planilha que são recusados). É
    intencional ('nunca trancar o admin para fora'), mas vale saber."""
    m = dict(master_secrets["master"], perfil="qualquer")
    assert auth._autenticar_master("master.teste", "Senha-Master-123", m)["perfil"] == "admin"
    m2 = dict(master_secrets["master"], perfil="visualizador")
    assert auth._autenticar_master("master.teste", "Senha-Master-123", m2)["perfil"] == "visualizador"


# --------------------------------------------------------------------------
# google_sheets contra a planilha simulada
# --------------------------------------------------------------------------
def test_carregar_usuarios_le_todas_as_linhas(planilha_fake):
    regs = google_sheets.carregar_usuarios()
    assert [r["usuario"] for r in regs][:3] == ["admin.teste", "user.teste", "view.teste"]


def test_adicionar_usuario_aparece_na_proxima_leitura(planilha_fake):
    assert "novo.teste" not in {r["usuario"] for r in google_sheets.carregar_usuarios()}
    google_sheets.adicionar_usuario("novo.teste", "Novo", "h", "s", "usuario", "SIM")
    assert "novo.teste" in {r["usuario"] for r in google_sheets.carregar_usuarios()}  # cache invalidado


def test_atualizar_status_desativa_e_reativa(planilha_fake):
    google_sheets.atualizar_status_usuario("user.teste", "NAO")
    assert {r["usuario"]: r["ativo"] for r in google_sheets.carregar_usuarios()}["user.teste"] == "NAO"
    google_sheets.atualizar_status_usuario("user.teste", "SIM")
    assert {r["usuario"]: r["ativo"] for r in google_sheets.carregar_usuarios()}["user.teste"] == "SIM"


def test_redefinir_senha_troca_hash_e_salt_e_novo_login_funciona(planilha_fake):
    salt = auth.gerar_salt()
    google_sheets.redefinir_senha_usuario("user.teste", auth.gerar_hash_senha("NovaSenha-9", salt), salt)
    usuarios = auth._carregar_usuarios()
    assert auth._autenticar("user.teste", "NovaSenha-9", usuarios)[0] is not None
    assert auth._autenticar("user.teste", SENHAS["user.teste"], usuarios)[0] is None


@pytest.mark.parametrize("funcao,args", [
    (google_sheets.atualizar_status_usuario, ("fantasma", "NAO")),
    (google_sheets.redefinir_senha_usuario, ("fantasma", "h", "s")),
])
def test_alterar_usuario_inexistente_levanta_valueerror(planilha_fake, funcao, args):
    with pytest.raises(ValueError, match="não encontrado"):
        funcao(*args)


def test_registrar_log_acrescenta_linha_com_campos_na_ordem(planilha_fake):
    google_sheets.registrar_log("u", "Nome", "login_sucesso", "sucesso", "det")
    linha = planilha_fake.worksheet("logs").linhas[-1]
    assert linha[1:] == ["u", "Nome", "login_sucesso", "sucesso", "det"]
    assert len(linha[0]) == 19  # "YYYY-MM-DD HH:MM:SS"


def test_registrar_log_nunca_levanta_excecao(planilha_fake):
    planilha_fake.worksheet("logs").falhar_em_append = True
    google_sheets.registrar_log("u", "n", "e", "s")  # não pode quebrar login/logout


def test_registrar_log_sem_planilha_nao_levanta(monkeypatch):
    monkeypatch.setattr(google_sheets, "_planilha", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    google_sheets.registrar_log("u", "n", "e", "s")


def test_senha_gerada_para_novo_usuario_e_compativel_com_o_login(planilha_fake):
    """Ciclo do painel admin: gerar salt+hash -> gravar na planilha -> logar."""
    salt = auth.gerar_salt()
    google_sheets.adicionar_usuario("ciclo.teste", "Ciclo", auth.gerar_hash_senha("S3nha!", salt), salt, "usuario", "SIM")
    dados, motivo = auth._autenticar("ciclo.teste", "S3nha!", auth._carregar_usuarios())
    assert motivo == "login_sucesso" and dados["perfil"] == "usuario"


def test_script_gerar_hash_senha_produz_par_compativel(monkeypatch, capsys):
    import importlib.util
    from pathlib import Path

    caminho = Path(__file__).resolve().parent.parent / "scripts" / "gerar_hash_senha.py"
    spec = importlib.util.spec_from_file_location("gerar_hash_senha", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod.getpass, "getpass", lambda *_: "SenhaDoScript-1")
    mod.main()
    saida = capsys.readouterr().out
    salt = next(l.split("=")[1].strip() for l in saida.splitlines() if l.startswith("salt"))
    hsh = next(l.split("=")[1].strip() for l in saida.splitlines() if l.startswith("senha_hash"))
    assert auth._verificar_senha("SenhaDoScript-1", salt, hsh)
    assert "SenhaDoScript-1" not in saida


def test_script_gerar_hash_senha_recusa_confirmacao_diferente(monkeypatch, capsys):
    import importlib.util
    from pathlib import Path

    caminho = Path(__file__).resolve().parent.parent / "scripts" / "gerar_hash_senha.py"
    spec = importlib.util.spec_from_file_location("gerar_hash_senha2", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    respostas = iter(["a", "b"])
    monkeypatch.setattr(mod.getpass, "getpass", lambda *_: next(respostas))
    mod.main()
    assert "não coincidem" in capsys.readouterr().out
