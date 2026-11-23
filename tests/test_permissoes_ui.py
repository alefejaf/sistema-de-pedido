"""Interface (streamlit.testing.v1.AppTest): login e permissões por perfil.

Roda ``app.py`` de verdade, com o Google Sheets simulado (``planilha_fake``) e
configs/ em pasta temporária. Nenhuma credencial, nenhuma rede, nenhum dado
real.
"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import FileUploader

from conftest import SENHAS
from grade_app import config, google_sheets
from synth import Item, numerar, pedido_texto, texto_para_pdf_bytes

pytestmark = pytest.mark.ui

APP = str(Path(__file__).resolve().parent.parent / "app.py")
SUPORTA_UPLOAD = hasattr(FileUploader, "upload")


def _novo_app():
    at = AppTest.from_file(APP, default_timeout=60)
    return at


def _sessao(at, perfil, cliente=None, usuario="u.teste"):
    at.session_state["autenticado"] = True
    at.session_state["usuario"] = usuario
    at.session_state["nome"] = "Nome Teste"
    at.session_state["perfil"] = perfil
    if cliente:
        at.session_state["cliente_atual"] = cliente
    return at


def _fazer_login(at, login, senha):
    at.run()
    at.text_input[0].set_value(login)
    at.text_input[1].set_value(senha)
    at.button[0].click()
    at.run()
    return at


def _todos_logs(planilha):
    return planilha.worksheet("logs").linhas


def _textos(elementos):
    return [e.value for e in elementos]


# --------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------
def test_sem_login_so_mostra_formulario_de_acesso(planilha_fake):
    at = _novo_app().run()
    assert not at.exception
    assert [t.label for t in at.text_input] == ["Usuário", "Senha"]
    assert "Escolha o cliente" not in " ".join(_textos(at.markdown))
    assert not at.session_state["autenticado"] if "autenticado" in at.session_state else True


@pytest.mark.parametrize("login,perfil", [
    ("admin.teste", "admin"), ("user.teste", "usuario"), ("view.teste", "visualizador"),
])
def test_login_valido_abre_o_sistema_e_registra_log(planilha_fake, login, perfil):
    at = _fazer_login(_novo_app(), login, SENHAS[login])
    assert not at.exception
    assert at.session_state["autenticado"] is True
    assert at.session_state["perfil"] == perfil
    assert any("Escolha o cliente" in m for m in _textos(at.markdown))
    eventos = [(l[1], l[3], l[4]) for l in _todos_logs(planilha_fake)]
    assert (login, "login_sucesso", "sucesso") in eventos


def test_senha_errada_nao_entra_e_loga_falha(planilha_fake):
    at = _fazer_login(_novo_app(), "admin.teste", "senha-errada")
    assert "Usuário ou senha inválidos." in _textos(at.error)
    assert not at.session_state["autenticado"] if "autenticado" in at.session_state else True
    logs = _todos_logs(planilha_fake)
    assert logs[-1][3:5] == ["login_falha", "falha"] and logs[-1][5] == "senha_invalida"


def test_usuario_inativo_nao_entra_e_loga_evento_proprio(planilha_fake):
    at = _fazer_login(_novo_app(), "inativo.teste", SENHAS["inativo.teste"])
    assert "Usuário ou senha inválidos." in _textos(at.error)
    assert _todos_logs(planilha_fake)[-1][3] == "usuario_inativo"


def test_usuario_inexistente_nao_entra(planilha_fake):
    at = _fazer_login(_novo_app(), "fantasma", "x")
    assert "Usuário ou senha inválidos." in _textos(at.error)
    assert _todos_logs(planilha_fake)[-1][5] == "usuario_nao_encontrado"


def test_mensagem_de_erro_nao_revela_se_o_usuario_existe(planilha_fake):
    a = _fazer_login(_novo_app(), "admin.teste", "errada")
    b = _fazer_login(_novo_app(), "fantasma", "errada")
    assert _textos(a.error) == _textos(b.error)


def test_nenhuma_senha_e_gravada_nos_logs(planilha_fake):
    _fazer_login(_novo_app(), "admin.teste", "SenhaSecretaDigitada-777")
    _fazer_login(_novo_app(), "user.teste", SENHAS["user.teste"])
    texto_logs = " ".join(str(c) for linha in _todos_logs(planilha_fake) for c in linha)
    assert "SenhaSecretaDigitada-777" not in texto_logs
    assert SENHAS["user.teste"] not in texto_logs


def test_master_entra_mesmo_com_planilha_fora_do_ar(monkeypatch, master_secrets):
    def fora_do_ar():
        raise RuntimeError("sheets fora do ar")

    monkeypatch.setattr(google_sheets, "_planilha", fora_do_ar)
    google_sheets.carregar_usuarios.clear()
    at = _novo_app()
    at.secrets["master"] = dict(master_secrets["master"])
    at.run()
    assert any("Só a conta master" in w for w in _textos(at.warning))
    at.text_input[0].set_value("master.teste")
    at.text_input[1].set_value("Senha-Master-123")
    at.button[0].click()
    at.run()
    assert at.session_state["perfil"] == "admin"


def test_usuario_comum_nao_entra_com_planilha_fora_do_ar(monkeypatch, planilha_fake, master_secrets):
    monkeypatch.setattr(google_sheets, "_planilha", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    google_sheets.carregar_usuarios.clear()
    at = _novo_app()
    at.secrets["master"] = dict(master_secrets["master"])
    at.run()
    at.text_input[0].set_value("user.teste")
    at.text_input[1].set_value(SENHAS["user.teste"])
    at.button[0].click()
    at.run()
    assert "Usuário ou senha inválidos." in _textos(at.error)


def test_sem_planilha_e_sem_master_bloqueia_tudo(monkeypatch):
    monkeypatch.setattr(google_sheets, "_planilha", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    google_sheets.carregar_usuarios.clear()
    at = _novo_app().run()
    assert any("nenhuma conta master" in e for e in _textos(at.error))
    assert len(at.text_input) == 0  # nem formulário aparece


def test_logout_limpa_a_sessao_e_registra(planilha_fake):
    at = _fazer_login(_novo_app(), "user.teste", SENHAS["user.teste"])
    sair = [b for b in at.sidebar.button if b.label == "Sair"][0]
    sair.click()
    at.run()
    assert "autenticado" not in at.session_state or not at.session_state["autenticado"]
    assert _todos_logs(planilha_fake)[-1][3] == "logout"


# --------------------------------------------------------------------------
# Tela inicial: só admin vê o gerenciamento de usuários
# --------------------------------------------------------------------------
@pytest.mark.parametrize("perfil,ve_painel", [("admin", True), ("usuario", False), ("visualizador", False)])
def test_painel_de_usuarios_so_para_admin(planilha_fake, perfil, ve_painel):
    at = _sessao(_novo_app(), perfil).run()
    assert not at.exception
    ha_painel = any("Gerenciar usuários" in m for m in _textos(at.markdown))
    assert ha_painel is ve_painel


def test_home_lista_os_cinco_clientes(planilha_fake):
    at = _sessao(_novo_app(), "usuario").run()
    rotulos = [b.label for b in at.button]
    for nome in ["ULTRABOX", "BIGBOX", "COSTA", "FORT", "EURO COMPANY"]:
        assert f"Abrir {nome}" in rotulos


def test_admin_cria_usuario_pelo_painel_com_hash_e_log(planilha_fake):
    at = _sessao(_novo_app(), "admin", usuario="admin.teste").run()
    campo = {t.label: t for t in at.text_input}
    campo["Usuário (login)"].set_value("criado.pelo.painel")
    campo["Nome"].set_value("Criado Painel")
    campo["Senha"].set_value("SenhaNova-42")
    campo["Confirmar senha"].set_value("SenhaNova-42")
    [b for b in at.button if b.label == "Adicionar usuário"][0].click()
    at.run()
    linhas = planilha_fake.worksheet("usuarios").linhas
    nova = next(l for l in linhas if l[0] == "criado.pelo.painel")
    assert nova[2] != "SenhaNova-42" and len(nova[2]) == 64 and len(nova[3]) == 32  # hash + salt, nunca texto puro
    assert nova[4] == "usuario" and nova[5] == "SIM"
    assert "usuario_criado" in [l[3] for l in _todos_logs(planilha_fake)]


def test_admin_nao_cria_usuario_duplicado_nem_com_senhas_diferentes(planilha_fake):
    at = _sessao(_novo_app(), "admin", usuario="admin.teste").run()
    campo = {t.label: t for t in at.text_input}
    campo["Usuário (login)"].set_value("user.teste")
    campo["Nome"].set_value("Duplicado")
    campo["Senha"].set_value("a")
    campo["Confirmar senha"].set_value("a")
    antes = len(planilha_fake.worksheet("usuarios").linhas)
    [b for b in at.button if b.label == "Adicionar usuário"][0].click()
    at.run()
    assert any("Já existe um usuário" in e for e in _textos(at.error))
    assert len(planilha_fake.worksheet("usuarios").linhas) == antes

    campo = {t.label: t for t in at.text_input}
    campo["Usuário (login)"].set_value("outro.login")
    campo["Nome"].set_value("X")
    campo["Senha"].set_value("a")
    campo["Confirmar senha"].set_value("b")
    [b for b in at.button if b.label == "Adicionar usuário"][0].click()
    at.run()
    assert any("não coincidem" in e for e in _textos(at.error))
    assert len(planilha_fake.worksheet("usuarios").linhas) == antes


# --------------------------------------------------------------------------
# Página do cliente: edição de configuração por perfil
# --------------------------------------------------------------------------
@pytest.mark.parametrize("perfil", ["admin", "usuario"])
def test_perfis_editores_salvam_configuracao_automaticamente(planilha_fake, perfil):
    at = _sessao(_novo_app(), perfil, "ultrabox").run()
    assert not at.exception
    assert config.caminho_config_cliente("ultrabox").exists()
    assert any("salva automaticamente" in s for s in _textos(at.success))
    assert "config_salva" in [l[3] for l in _todos_logs(planilha_fake)]
    assert "🔄 Restaurar padrão inicial deste cliente" in [b.label for b in at.button]


def test_visualizador_nao_grava_configuracao_nem_ve_restaurar(planilha_fake):
    at = _sessao(_novo_app(), "visualizador", "ultrabox").run()
    assert not at.exception
    assert not config.caminho_config_cliente("ultrabox").exists()          # nada gravado em disco
    assert not config.CONFIG_DIR.exists() or list(config.CONFIG_DIR.iterdir()) == []
    assert "config_salva" not in [l[3] for l in _todos_logs(planilha_fake)]  # nada logado
    assert not any("salva automaticamente" in s for s in _textos(at.success))
    assert "🔄 Restaurar padrão inicial deste cliente" not in [b.label for b in at.button]
    assert any("Perfil visualizador" in i for i in _textos(at.info))


def test_visualizador_pode_baixar_a_configuracao_atual_mas_nao_o_resto(planilha_fake):
    at = _sessao(_novo_app(), "visualizador", "ultrabox").run()
    # única exportação disponível sem PDF: a configuração (somente leitura)
    assert len(at.get("download_button")) == 1


def test_visualizador_nao_consegue_gravar_nem_depois_de_varias_interacoes(planilha_fake):
    at = _sessao(_novo_app(), "visualizador", "costa").run()
    for _ in range(3):
        at.run()
    assert not config.CONFIG_DIR.exists() or list(config.CONFIG_DIR.iterdir()) == []


def test_cliente_e_isolado_cada_um_grava_o_proprio_arquivo(planilha_fake):
    _sessao(_novo_app(), "usuario", "costa").run()
    _sessao(_novo_app(), "usuario", "fort").run()
    nomes = sorted(p.name for p in config.CONFIG_DIR.glob("*.xlsx"))
    assert nomes == ["config_costa.xlsx", "config_fort.xlsx"]


@pytest.mark.parametrize("cliente", ["ultrabox", "bigbox", "costa", "fort", "eurocompany"])
def test_pagina_de_cada_cliente_abre_sem_erro(planilha_fake, cliente):
    at = _sessao(_novo_app(), "usuario", cliente).run()
    assert not at.exception
    assert config.CLIENTES[cliente]["nome"] in at.title[0].value


def test_trocar_cliente_volta_para_a_tela_inicial(planilha_fake):
    at = _sessao(_novo_app(), "usuario", "ultrabox").run()
    [b for b in at.button if "Trocar cliente" in b.label][0].click()
    at.run()
    assert any("Escolha o cliente" in m for m in _textos(at.markdown))


# --------------------------------------------------------------------------
# Com PDF: downloads por perfil
# --------------------------------------------------------------------------
def _pdf_ultrabox():
    itens = numerar([Item("MACA GALA", 10, 5.5, "KG"), Item("KIWI 600G", 20, 7.25)])
    return texto_para_pdf_bytes(pedido_texto("100001", "ULT01-PLANDF", itens, layout="horizontal"))


def _abrir_com_pdf(perfil):
    at = _sessao(_novo_app(), perfil, "ultrabox").run()
    sub = [u for u in at.sidebar.get("file_uploader")][0]
    sub.upload("pedido_sintetico.pdf", _pdf_ultrabox(), "application/pdf")
    at.run()
    return at


@pytest.mark.skipif(not SUPORTA_UPLOAD, reason="esta versão do Streamlit não tem FileUploader.upload no AppTest")
@pytest.mark.parametrize("perfil,baixa", [("admin", True), ("usuario", True), ("visualizador", False)])
def test_download_dos_excels_por_perfil(planilha_fake, perfil, baixa):
    at = _abrir_com_pdf(perfil)
    assert not at.exception, at.exception
    rotulos = [d.proto.label for d in at.get("download_button")]
    tem_nota = any("Baixar NOTA FINAL" in r for r in rotulos)
    tem_completo = any("Excel completo" in r for r in rotulos)
    assert tem_nota is baixa and tem_completo is baixa
    if not baixa:
        assert any("não tem permissão para baixar" in i for i in _textos(at.info))


@pytest.mark.skipif(not SUPORTA_UPLOAD, reason="esta versão do Streamlit não tem FileUploader.upload no AppTest")
def test_pdf_correto_mostra_metricas_e_sem_criticos(planilha_fake):
    at = _abrir_com_pdf("usuario")
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Pedidos lidos"] == "1"
    assert metricas["Linhas extraídas"] == "2"
    assert metricas["Críticos"] == "0"
    assert any("sem inconsistências relevantes" in s for s in _textos(at.success))


@pytest.mark.skipif(not SUPORTA_UPLOAD, reason="esta versão do Streamlit não tem FileUploader.upload no AppTest")
def test_pdf_ilegivel_mostra_erro_em_vez_de_quebrar(planilha_fake):
    at = _sessao(_novo_app(), "usuario", "ultrabox").run()
    at.sidebar.get("file_uploader")[0].upload("lixo.pdf", b"nao e pdf", "application/pdf")
    at.run()
    assert any("Não consegui ler o PDF" in e for e in _textos(at.error))


# --------------------------------------------------------------------------
# Comportamentos de gravação automática (caracterização / achados)
# --------------------------------------------------------------------------
def test_cada_execucao_da_tela_de_editor_gera_backup_caracterizacao(planilha_fake, monkeypatch):
    """ACHADO (risco operacional): para perfis editores, render_editores() grava
    a config E cria um backup a CADA execução da página (qualquer clique, upload
    de PDF, etc.), mesmo sem edição. Como só os 10 backups mais recentes são
    mantidos, o histórico 'útil' é varrido por 10 interações. Este teste fixa o
    comportamento atual; se for corrigido (salvar só quando houver edição),
    atualize-o."""
    from datetime import datetime, timedelta

    class Relogio:
        n = 0

        @classmethod
        def now(cls):
            cls.n += 1
            return datetime(2026, 1, 1) + timedelta(seconds=cls.n)

    monkeypatch.setattr(config, "datetime", Relogio)
    at = _sessao(_novo_app(), "usuario", "ultrabox").run()
    for _ in range(6):
        at.run()
    backups = list(config.BACKUP_CONFIG_DIR.glob("config_ultrabox_*.xlsx"))
    assert len(backups) >= 6  # um backup por execução, sem nenhuma edição do usuário


def test_config_salva_ilegivel_e_sobrescrita_pelo_padrao_caracterizacao(planilha_fake):
    """ACHADO (risco de perda de dados): se o config_<cliente>.xlsx salvo ficar
    ilegível, o app cai para o padrão do código E, por ser editor, grava esse
    padrão por cima na mesma execução (o arquivo corrompido vai para o backup,
    que roda a cada execução e some após 10). Só o perfil visualizador evita."""
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    arq = config.caminho_config_cliente("fort")
    arq.write_bytes(b"arquivo corrompido")
    at = _sessao(_novo_app(), "visualizador", "fort").run()
    assert arq.read_bytes() == b"arquivo corrompido"        # visualizador não toca

    at = _sessao(_novo_app(), "usuario", "fort").run()
    assert arq.read_bytes() != b"arquivo corrompido"        # editor sobrescreve com o padrão
    l, _, _ = config.carregar_config_excel(arq, "fort")
    assert "FORT66-VALPARAISO" in list(l["Código PDF"])
    assert any(b.read_bytes() == b"arquivo corrompido" for b in config.BACKUP_CONFIG_DIR.glob("config_fort_*.xlsx"))
