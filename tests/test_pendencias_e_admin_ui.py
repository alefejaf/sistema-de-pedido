"""UI: aba Pendências (cadastro de loja/produto novos vindos do PDF) e ações do
painel admin (ativar/desativar usuário, redefinir senha)."""
import pytest
from streamlit.testing.v1.element_tree import FileUploader

from conftest import SENHAS
from grade_app import auth, config, google_sheets
from synth import Item, numerar, pedido_texto, texto_para_pdf_bytes
from test_permissoes_ui import _novo_app, _sessao, _textos, _todos_logs

pytestmark = pytest.mark.ui
SUPORTA_UPLOAD = hasattr(FileUploader, "upload")
pula_sem_upload = pytest.mark.skipif(not SUPORTA_UPLOAD, reason="AppTest sem FileUploader.upload")


def _pdf(codigo_loja="ULT01-PLANDF", produto="PRODUTO NOVO TESTE 123"):
    itens = numerar([Item("MACA GALA", 10, 5.5, "KG"), Item(produto, 4, 3.0)])
    return texto_para_pdf_bytes(pedido_texto("100001", codigo_loja, itens, layout="horizontal"))


def _abrir(perfil, pdf, cliente="ultrabox"):
    at = _sessao(_novo_app(), perfil, cliente).run()
    at.sidebar.get("file_uploader")[0].upload("p.pdf", pdf, "application/pdf")
    at.run()
    return at


def _botao(at, trecho):
    achados = [b for b in at.button if trecho in b.label]
    return achados[0] if achados else None


@pula_sem_upload
def test_produto_novo_aparece_como_pendencia_e_critico(planilha_fake):
    at = _abrir("usuario", _pdf())
    assert not at.exception
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Pendências de cadastro"] == "1"
    assert int(metricas["Críticos"]) >= 1
    assert any("validações críticas" in e for e in _textos(at.error))


@pula_sem_upload
def test_adicionar_produto_pendente_grava_e_zera_a_pendencia(planilha_fake):
    at = _abrir("usuario", _pdf())
    _botao(at, "Adicionar produtos pendentes").click()
    at.run()
    assert not at.exception
    _, prods, _ = config.carregar_config(None, "ultrabox")
    assert "PRODUTO NOVO TESTE 123" in set(prods["Nome do produto no PDF"])
    assert "config_salva" in [l[3] for l in _todos_logs(planilha_fake)]
    # depois de salvo, o mesmo PDF já não tem pendência de produto
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Pendências de cadastro"] == "0"
    assert metricas["Críticos"] == "0"


@pula_sem_upload
def test_loja_pendente_sem_coluna_da_grade_nao_e_salva(planilha_fake):
    at = _abrir("usuario", _pdf(codigo_loja="ULT77-NOVAXX"))
    antes, _, _ = config.carregar_config(None, "ultrabox")
    _botao(at, "Adicionar lojas pendentes").click()
    at.run()
    assert any("Preencha a coluna da grade" in w for w in _textos(at.warning))
    depois, _, _ = config.carregar_config(None, "ultrabox")
    assert "ULT77-NOVAXX" not in set(depois["Código PDF"])
    assert list(antes["Código PDF"]) == list(depois["Código PDF"])


@pula_sem_upload
def test_visualizador_ve_pendencias_mas_nao_tem_botoes_de_cadastro(planilha_fake):
    at = _abrir("visualizador", _pdf())
    assert _botao(at, "Adicionar produtos pendentes") is None
    assert _botao(at, "Adicionar lojas pendentes") is None
    assert any("não pode cadastrá-las" in i for i in _textos(at.info))
    assert not config.CONFIG_DIR.exists() or list(config.CONFIG_DIR.iterdir()) == []


@pula_sem_upload
def test_restaurar_padrao_volta_ao_depara_inicial_e_registra_log(planilha_fake):
    at = _sessao(_novo_app(), "usuario", "costa").run()
    # grava uma config diferente da padrão e restaura
    from helpers import depara_lojas, depara_produtos

    config.salvar_config_cliente("costa", depara_lojas(("COSTA-X", "X", "TAG")), depara_produtos(("P", "P", "UN")),
                                 config.criar_config_grade_padrao("costa"))
    at.run()
    _botao(at, "Restaurar padrão inicial").click()
    at.run()
    lojas, _, _ = config.carregar_config(None, "costa")
    assert "COSTA-TAGUATINGA" in set(lojas["Código PDF"])
    assert "COSTA-X" not in set(lojas["Código PDF"])
    assert "config_salva" in [l[3] for l in _todos_logs(planilha_fake)]
    # OBS (UX do app): a mensagem "Configuração padrão restaurada e salva." é
    # emitida logo antes de st.rerun(), então nunca chega a aparecer na tela.


# --------------------------------------------------------------------------
# Painel admin: ativar/desativar e redefinir senha
# --------------------------------------------------------------------------
def _admin(planilha_fake):
    return _sessao(_novo_app(), "admin", usuario="admin.teste").run()


def _selecionar_usuario(at, login):
    at.selectbox(key="admin_usuario_selecionado").set_value(login)
    at.run()


def test_admin_desativa_e_reativa_usuario_e_efeito_no_login(planilha_fake):
    at = _admin(planilha_fake)
    _selecionar_usuario(at, "user.teste")
    _botao(at, "Desativar usuário").click()
    at.run()
    estado = {l[0]: l[5] for l in planilha_fake.worksheet("usuarios").linhas}
    assert estado["user.teste"] == "NAO"
    google_sheets.carregar_usuarios.clear()
    assert auth._autenticar("user.teste", SENHAS["user.teste"], auth._carregar_usuarios())[1] == "usuario_inativo"
    assert any("usuario_atualizado" == l[3] and "ativo=NAO" in l[5] for l in _todos_logs(planilha_fake))

    _selecionar_usuario(at, "user.teste")
    _botao(at, "Ativar usuário").click()
    at.run()
    assert {l[0]: l[5] for l in planilha_fake.worksheet("usuarios").linhas}["user.teste"] == "SIM"


def test_admin_redefine_senha_e_a_antiga_deixa_de_funcionar(planilha_fake):
    at = _admin(planilha_fake)
    _selecionar_usuario(at, "user.teste")
    campo = [t for t in at.text_input if t.label == "Nova senha"][0]
    campo.set_value("SenhaRedefinida-55")
    _botao(at, "Redefinir senha").click()
    at.run()
    google_sheets.carregar_usuarios.clear()
    usuarios = auth._carregar_usuarios()
    assert auth._autenticar("user.teste", "SenhaRedefinida-55", usuarios)[0] is not None
    assert auth._autenticar("user.teste", SENHAS["user.teste"], usuarios)[0] is None
    linha = next(l for l in planilha_fake.worksheet("usuarios").linhas if l[0] == "user.teste")
    assert "SenhaRedefinida-55" not in linha  # só hash e salt na planilha


def test_admin_redefinir_senha_vazia_e_recusado(planilha_fake):
    at = _admin(planilha_fake)
    _selecionar_usuario(at, "user.teste")
    antes = [l[:] for l in planilha_fake.worksheet("usuarios").linhas]
    _botao(at, "Redefinir senha").click()
    at.run()
    assert any("Digite a nova senha" in e for e in _textos(at.error))
    assert planilha_fake.worksheet("usuarios").linhas == antes


def test_falha_de_escrita_na_planilha_vira_mensagem_e_nao_quebra(planilha_fake, monkeypatch):
    def quebrar(*a, **k):
        raise RuntimeError("quota excedida")

    monkeypatch.setattr(google_sheets, "atualizar_status_usuario", quebrar)
    at = _admin(planilha_fake)
    _selecionar_usuario(at, "user.teste")
    _botao(at, "Desativar usuário").click()
    at.run()
    assert not at.exception
    assert any("Não foi possível atualizar" in e for e in _textos(at.error))
