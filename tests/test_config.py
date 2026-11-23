"""Persistência da configuração DE/PARA por cliente (configs/ e backups_config/).

A fixture autouse ``_isolar_dados_reais`` (conftest) aponta CONFIG_DIR e
BACKUP_CONFIG_DIR para uma pasta temporária, então nada aqui toca os dados
reais do repositório.
"""
import time

import pandas as pd
import pytest

from grade_app import config
from helpers import depara_lojas, depara_produtos


def _cfg(sufixo=""):
    lojas = depara_lojas(("ULT01-PLANDF", "LOJA A" + sufixo, "PLAN"))
    prods = depara_produtos(("MACA GALA KG", "MACA GALA KG", "KG"))
    grade = config.criar_config_grade_padrao("ultrabox")
    return lojas, prods, grade


def test_diretorios_de_teste_estao_isolados(_isolar_dados_reais):
    cfg_dir, bkp_dir = _isolar_dados_reais
    assert config.CONFIG_DIR == cfg_dir
    assert "configs" in str(cfg_dir) and str(cfg_dir).startswith(str(cfg_dir.parent))
    assert config.CONFIG_DIR.parent != config.Path(config.__file__).resolve().parent.parent


def test_primeira_gravacao_cria_arquivo_e_nao_faz_backup():
    caminho = config.salvar_config_cliente("ultrabox", *_cfg())
    assert caminho.exists() and caminho.name == "config_ultrabox.xlsx"
    assert not config.BACKUP_CONFIG_DIR.exists() or list(config.BACKUP_CONFIG_DIR.iterdir()) == []


def test_ida_e_volta_de_salvar_e_carregar():
    lojas, prods, grade = _cfg()
    config.salvar_config_cliente("ultrabox", lojas, prods, grade)
    assert config.existe_config_salva_cliente("ultrabox")
    l2, p2, g2 = config.carregar_config(None, "ultrabox")
    assert list(l2["Código PDF"]) == ["ULT01-PLANDF"]
    assert list(p2["Nome oficial na grade"]) == ["MACA GALA KG"]
    assert "PLAN" in list(g2["Coluna da grade"])


def test_config_salva_tem_prioridade_sobre_a_padrao():
    config.salvar_config_cliente("costa", *_cfg())
    l, _, _ = config.carregar_config(None, "costa")
    assert list(l["Código PDF"]) == ["ULT01-PLANDF"]  # e não os COSTA-* padrão


def test_upload_manual_tem_prioridade_sobre_a_salva():
    config.salvar_config_cliente("ultrabox", *_cfg())
    outro = config.gerar_excel_config(
        depara_lojas(("ULT09-OUTRA", "X", "SOB")), depara_produtos(("P", "P", "UN")), None, "T")
    import io

    l, _, _ = config.carregar_config(io.BytesIO(outro), "ultrabox")
    assert list(l["Código PDF"]) == ["ULT09-OUTRA"]


def test_upload_invalido_cai_para_a_config_salva(monkeypatch):
    config.salvar_config_cliente("ultrabox", *_cfg())
    import io

    avisos = []
    monkeypatch.setattr(config.st, "warning", lambda m, *a, **k: avisos.append(m))
    l, _, _ = config.carregar_config(io.BytesIO(b"nao e um xlsx"), "ultrabox")
    assert list(l["Código PDF"]) == ["ULT01-PLANDF"]
    assert avisos and "Não consegui ler a configuração enviada" in avisos[0]


def test_config_salva_corrompida_cai_para_o_padrao(monkeypatch):
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config.caminho_config_cliente("fort").write_bytes(b"lixo")
    avisos = []
    monkeypatch.setattr(config.st, "warning", lambda m, *a, **k: avisos.append(m))
    l, _, _ = config.carregar_config(None, "fort")
    assert "FORT66-VALPARAISO" in list(l["Código PDF"])
    assert avisos and "configuração salva" in avisos[0]


def test_segunda_gravacao_gera_backup_com_o_conteudo_anterior(monkeypatch):
    config.salvar_config_cliente("ultrabox", *_cfg(" v1"))
    # garante timestamp diferente nos nomes de backup
    monkeypatch.setattr(config, "datetime", _RelogioFalso())
    config.salvar_config_cliente("ultrabox", *_cfg(" v2"))
    backups = list(config.BACKUP_CONFIG_DIR.glob("config_ultrabox_*.xlsx"))
    assert len(backups) == 1
    l_bkp, _, _ = config.carregar_config_excel(backups[0], "ultrabox")
    assert list(l_bkp["Nome da loja"]) == ["LOJA A v1"]
    l_atual, _, _ = config.carregar_config(None, "ultrabox")
    assert list(l_atual["Nome da loja"]) == ["LOJA A v2"]


class _RelogioFalso:
    """Substitui config.datetime para cada chamada devolver um instante novo."""

    _n = 0

    @classmethod
    def now(cls):
        from datetime import datetime, timedelta

        cls._n += 1
        return datetime(2026, 1, 1, 10, 0, 0) + timedelta(seconds=cls._n)


def test_mantem_no_maximo_10_backups_por_cliente(monkeypatch):
    monkeypatch.setattr(config, "datetime", _RelogioFalso())
    for i in range(15):
        config.salvar_config_cliente("ultrabox", *_cfg(f" {i}"))
    backups = sorted(config.BACKUP_CONFIG_DIR.glob("config_ultrabox_*.xlsx"))
    assert len(backups) == config.MAX_BACKUPS_POR_CLIENTE == 10
    # os que sobram são os MAIS RECENTES
    nomes_loja = []
    for b in backups:
        l, _, _ = config.carregar_config_excel(b, "ultrabox")
        nomes_loja.append(l["Nome da loja"].iloc[0])
    assert "LOJA A 0" not in nomes_loja and "LOJA A 13" in nomes_loja


def test_backup_de_um_cliente_nao_apaga_o_de_outro(monkeypatch):
    monkeypatch.setattr(config, "datetime", _RelogioFalso())
    for i in range(13):
        config.salvar_config_cliente("ultrabox", *_cfg(f" {i}"))
    for i in range(3):
        config.salvar_config_cliente("costa", *_cfg(f" {i}"))
    assert len(list(config.BACKUP_CONFIG_DIR.glob("config_ultrabox_*.xlsx"))) == 10
    assert len(list(config.BACKUP_CONFIG_DIR.glob("config_costa_*.xlsx"))) == 2


def test_clientes_tem_arquivos_independentes():
    config.salvar_config_cliente("ultrabox", *_cfg(" U"))
    config.salvar_config_cliente("costa", *_cfg(" C"))
    lu, _, _ = config.carregar_config(None, "ultrabox")
    lc, _, _ = config.carregar_config(None, "costa")
    assert lu["Nome da loja"].iloc[0] == "LOJA A U" and lc["Nome da loja"].iloc[0] == "LOJA A C"


def test_salvar_inclui_colunas_novas_das_lojas_na_grade():
    lojas = depara_lojas(("ULT01-PLANDF", "A", "PLAN"), ("ULT99-NOVA", "N", "NOVA"))
    prods = depara_produtos(("X", "X", "UN"))
    config.salvar_config_cliente("ultrabox", lojas, prods, config.criar_config_grade_padrao("ultrabox"))
    _, _, grade = config.carregar_config(None, "ultrabox")
    assert "NOVA" in list(grade["Coluna da grade"])
    assert grade.loc[grade["Coluna da grade"] == "NOVA", "Mostrar"].iloc[0]


def test_slug_cliente_e_seguro_para_nome_de_arquivo():
    assert config.slug_cliente("../../etc/passwd") == "etc_passwd"
    assert config.slug_cliente("Euro Company") == "euro_company"
    assert config.slug_cliente("") == "cliente"
    assert config.caminho_config_cliente("../x").parent == config.CONFIG_DIR


# --------------------------------------------------------------------------
# Config da grade (ordem / visibilidade)
# --------------------------------------------------------------------------
def test_config_grade_oculta_colunas_desmarcadas_e_respeita_ordem():
    df = pd.DataFrame({"Posição": [2, 1, 3], "Coluna da grade": ["B", "a", "C"], "Mostrar": [True, True, False]})
    assert config.obter_colunas_grade(df, "ultrabox") == ["A", "B"]


def test_config_grade_sem_nenhuma_visivel_volta_ao_padrao_do_cliente():
    df = pd.DataFrame({"Posição": [1], "Coluna da grade": ["A"], "Mostrar": [False]})
    assert config.obter_colunas_grade(df, "costa") == config.CLIENTES["costa"]["grade_cols"]


def test_config_grade_remove_duplicadas_e_posiciona_sem_posicao():
    df = pd.DataFrame({"Posição": [1, None, 2], "Coluna da grade": ["A", "B", "A"], "Mostrar": [True] * 3})
    out = config.preparar_config_grade(df)
    assert list(out["Coluna da grade"]) == ["A", "B"]
    assert out["Posição"].notna().all()


def test_mesclar_depara_lojas_nao_duplica_e_atualiza():
    atual = depara_lojas(("ULT01-PLANDF", "A", "PLAN"))
    novas = depara_lojas(("ult01-plandf", "A NOVA", "PLAN"), ("ULT02-GAMA", "B", "GAM"))
    out = config.mesclar_depara_lojas(atual, novas)
    assert len(out) == 2
    assert out[out["Código PDF"].str.upper() == "ULT01-PLANDF"]["Nome da loja"].iloc[0] == "A NOVA"


def test_mesclar_depara_produtos_ignora_linhas_sem_nome():
    atual = depara_produtos(("MACA", "MACA", "KG"))
    novos = depara_produtos(("", "X", "UN"), ("KIWI", "KIWI", "UN"))
    out = config.mesclar_depara_produtos(atual, novos)
    assert list(out["Nome do produto no PDF"]) == ["MACA", "KIWI"]


def test_preco_referencia_legado_ult24_pbrasi_recebe_sim_quando_coluna_nao_existe():
    df = pd.DataFrame([["ULT24-PBRASI", "BRASILINHA", "BRASI"]], columns=["Código PDF", "Nome da loja", "Coluna da grade"])
    out = config.preparar_depara_lojas(df)
    assert out["Usar preço referência"].iloc[0] == "SIM"
