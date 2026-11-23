"""Quais clientes o sistema REALMENTE suporta, e como cada um é lido.

Clientes declarados em ``grade_app.config.CLIENTES``: ultrabox, bigbox, costa,
fort e eurocompany. O parser de linhas é o mesmo para todos; o que muda por
cliente é (a) como a LOJA aparece no cabeçalho do PDF, (b) o layout de linha
usado pelo fornecedor, (c) o DE/PARA padrão e (d) as colunas da grade.

Estes testes comprovam, com PDFs sintéticos, o ciclo completo de cada cliente.
"""
import re
from pathlib import Path

import pandas as pd
import pytest

from grade_app import config
from grade_app.pdf_text import extrair_loja, extrair_texto_pdfs
from grade_app.processing import padronizar_produtos
from helpers import processar
from synth import (
    ArquivoFake, Item, cabecalho_costa, cabecalho_fort, numerar, pedido_texto, texto_para_pdf_bytes,
)

RAIZ = Path(__file__).resolve().parent.parent
CLIENTES_DECLARADOS = ["ultrabox", "bigbox", "costa", "fort", "eurocompany"]


def test_lista_de_clientes_declarados():
    """Se alguém adicionar/remover cliente, este teste obriga a atualizar a suíte."""
    assert list(config.CLIENTES) == CLIENTES_DECLARADOS


@pytest.mark.parametrize("cid", CLIENTES_DECLARADOS)
def test_metadados_do_cliente(cid):
    c = config.CLIENTES[cid]
    assert {"nome", "icone", "subtitulo", "descricao", "grade_cols"} <= set(c)
    assert c["grade_cols"], "cliente sem colunas de grade"
    assert len(c["grade_cols"]) == len(set(c["grade_cols"])), "coluna de grade repetida"
    assert config.slug_cliente(cid) == cid


@pytest.mark.parametrize("cid", CLIENTES_DECLARADOS)
def test_config_padrao_carrega_sem_arquivo_salvo(cid):
    lojas, prods, grade = config.carregar_config(None, cid)
    assert not lojas.empty and not prods.empty
    assert list(grade["Coluna da grade"]) == config.CLIENTES[cid]["grade_cols"]


@pytest.mark.parametrize("cid", CLIENTES_DECLARADOS)
def test_lojas_do_depara_padrao_apontam_para_colunas_da_grade(cid):
    lojas, _ = config.criar_config_padrao_cliente(cid)
    grade = set(config.CLIENTES[cid]["grade_cols"])
    fora = sorted(set(lojas["Coluna da grade"]) - grade)
    if cid == "bigbox":
        pytest.xfail(f"ACHADO: BB-VIPIRES -> VIPIRES não está nas colunas padrão do Bigbox ({fora}); "
                     "a config salva do cliente já a inclui manualmente.")
    assert fora == []


# --------------------------------------------------------------------------
# Configs empacotadas no repositório (seed da imagem Docker)
# --------------------------------------------------------------------------
def test_so_quatro_clientes_tem_config_empacotada_eurocompany_nao():
    """ACHADO: Euro Company NÃO tem configs/config_eurocompany.xlsx no repositório.
    Ele roda com o DE/PARA padrão do código (config.criar_produtos_padrao_eurocompany)
    e qualquer edição fica só no volume de produção."""
    existentes = {p.stem.replace("config_", "") for p in (RAIZ / "configs").glob("config_*.xlsx")}
    assert existentes == {"ultrabox", "bigbox", "costa", "fort"}
    assert "eurocompany" not in existentes


@pytest.mark.parametrize("cid", ["ultrabox", "bigbox", "costa", "fort"])
def test_config_empacotada_e_legivel_e_completa(cid):
    lojas, prods, grade = config.carregar_config_excel(RAIZ / "configs" / f"config_{cid}.xlsx", cid)
    assert not lojas.empty and not prods.empty and not grade.empty
    assert (lojas["Código PDF"].astype(str).str.strip() != "").all()
    assert (lojas["Coluna da grade"].astype(str).str.strip() != "").all()
    # toda loja cadastrada tem coluna na CONFIG_GRADE do próprio arquivo
    assert set(lojas["Coluna da grade"].str.upper()) <= set(grade["Coluna da grade"])


@pytest.mark.parametrize("cid", ["ultrabox", "bigbox", "costa", "fort"])
def test_config_empacotada_sem_chave_duplicada_com_destinos_diferentes(cid):
    from grade_app.utils import normalizar

    _, prods, _ = config.carregar_config_excel(RAIZ / "configs" / f"config_{cid}.xlsx", cid)
    destinos = {}
    for pdf, ofi in zip(prods["Nome do produto no PDF"], prods["Nome oficial na grade"]):
        destinos.setdefault(normalizar(pdf), set()).add(str(ofi).upper())
    conflitos = {k: v for k, v in destinos.items() if k and len(v) > 1}
    assert conflitos == {}


# Os códigos de loja cadastrados têm que ser "alcançáveis" pela extração do PDF.
def _cabecalho_para(codigo):
    if codigo.startswith("COSTA-"):
        return cabecalho_costa(codigo[len("COSTA-"):].replace("-", " "))
    m = re.match(r"FORT(\d+)-(.*)", codigo)
    if m:
        return cabecalho_fort(m.group(1), m.group(2).replace("-", " "))
    return None  # ULT/BIG: o próprio código aparece no cabeçalho


@pytest.mark.parametrize("cid", CLIENTES_DECLARADOS)
def test_todo_codigo_de_loja_padrao_e_extraivel_do_pdf(cid):
    lojas, _ = config.criar_config_padrao_cliente(cid)
    inalcancaveis = []
    for codigo in lojas["Código PDF"]:
        cab = _cabecalho_para(codigo)
        bloco = pedido_texto("1", codigo, [], cabecalho=cab)
        if extrair_loja(bloco) != codigo:
            inalcancaveis.append(codigo)
    if inalcancaveis:
        pytest.xfail(
            f"ACHADO: códigos cadastrados que extrair_loja() nunca produz: {inalcancaveis}. "
            "O regex exige o formato LLL99-XXX (ex.: ULT01-PLANDF); 'BB-VIPIRES' não casa. "
            "Pode ser código morto OU o PDF real traz outro formato - conferir com um PDF real."
        )


# --------------------------------------------------------------------------
# DE/PARA de produtos: cada entrada precisa resolver para si mesma
# --------------------------------------------------------------------------
@pytest.mark.parametrize("cid", [
    "eurocompany",
    pytest.param("ultrabox", marks=pytest.mark.xfail(strict=True, reason="MACA GALA sombreia MACA GALA 1KG (default)")),
    pytest.param("bigbox", marks=pytest.mark.xfail(strict=True, reason="MACA GALA sombreia MACA GALA 1KG (default)")),
    pytest.param("costa", marks=pytest.mark.xfail(strict=True, reason="MACA GALA sombreia MACA GALA 1KG (default)")),
    pytest.param("fort", marks=pytest.mark.xfail(strict=True, reason="MACA GALA sombreia MACA GALA 1KG (default)")),
])
def test_cada_produto_do_depara_padrao_resolve_para_o_proprio_oficial(cid):
    _, prods = config.criar_config_padrao_cliente(cid)
    prods = config.preparar_depara_produtos(prods)
    out = padronizar_produtos(pd.DataFrame({"Produto original": prods["Nome do produto no PDF"].tolist()}), prods)
    esperado = prods["Nome oficial na grade"].str.upper().tolist()
    assert out["Produto padronizado"].tolist() == esperado
    assert set(out["Método padronização"]) == {"DE/PARA"}


def test_eurocompany_cada_produto_tem_as_duas_variantes_de_nome_no_pdf():
    """O fornecedor já trocou o texto do nome entre lotes; cada produto tem de
    ter 2 variantes mapeando para o mesmo oficial (exceto os de variante única)."""
    prods = config.criar_produtos_padrao_eurocompany()
    por_oficial = prods.groupby("Nome oficial na grade")["Nome do produto no PDF"].count()
    com_uma_variante = sorted(por_oficial[por_oficial < 2].index)
    assert com_uma_variante == sorted([
        "ABACAXI NATURAL 30G", "MANGA NATURAL 30G", "MIX DE AMENDOIM 200G",
        "MIX DE FRUTAS ENERGIA 40G", "MIX DE FRUTAS FUNCIONAL 40G",
        "MIX DE FRUTAS SAUDE 40G", "MIX DE FRUTAS TROPICAL 40G",
    ])
    assert (prods["Unidade"] == "CX").all()


# --------------------------------------------------------------------------
# Ciclo completo por cliente (PDF sintético real -> Excel) com a config PADRÃO
# --------------------------------------------------------------------------
def _config_padrao(cid):
    lojas, prods, grade = config.carregar_config(None, cid)
    return config.preparar_depara_lojas(lojas), config.preparar_depara_produtos(prods), grade


def _rodar(cid, texto):
    lojas, prods, grade = _config_padrao(cid)
    pdf = texto_para_pdf_bytes(texto)
    lido = extrair_texto_pdfs([ArquivoFake(pdf)])
    return processar(lido, lojas, prods, cid, grade)


def _itens_frutas(mult=1):
    return numerar([
        Item("MACA GALA", 10, 5.50, "KG"),
        Item("KIWI 600G", 20, 7.25),
        Item("UVA THOMPSON", 8, 9.90),
    ])


CASOS_FRUTAS = {
    # cid: (lista de (código, coluna esperada), layout, função cabeçalho)
    "ultrabox": ([("ULT01-PLANDF", "PLAN"), ("ULT02-GAMA", "GAM")], "multilinha", None),
    "bigbox": ([("BIG20-TAGC1", "T-CENTRO"), ("BIG21-CNB12", "CNB12")], "visual", None),
    "costa": ([("COSTA-TAGUATINGA", "TAG"), ("COSTA-SANTA-MARIA", "S.MARIA")], "horizontal", "costa"),
    "fort": ([("FORT66-VALPARAISO", "F66-VALP"), ("FORT138-TAGUATINGA", "F138-TAG")], "horizontal", "fort"),
}


def _cabecalho(tipo, codigo):
    if tipo == "costa":
        return cabecalho_costa(codigo[len("COSTA-"):].replace("-", " "))
    if tipo == "fort":
        m = re.match(r"FORT(\d+)-(.*)", codigo)
        return cabecalho_fort(m.group(1), m.group(2).replace("-", " "))
    return None


@pytest.mark.parametrize("cid", list(CASOS_FRUTAS))
def test_ciclo_completo_por_cliente(cid):
    lojas_cols, layout, tipo = CASOS_FRUTAS[cid]
    texto = ""
    for n, (codigo, _col) in enumerate(lojas_cols, start=1):
        texto += pedido_texto(str(5000 + n), codigo, _itens_frutas(), layout=layout,
                              cabecalho=_cabecalho(tipo, codigo))
    r = _rodar(cid, texto)

    assert r.criticos == 0, r.validacoes.to_string()
    assert r.atencoes == 0, r.validacoes.to_string()
    assert list(r.controle["Status"]) == ["OK"] * len(lojas_cols)
    # cada loja caiu na coluna certa da grade
    g = r.nota_final.set_index("Produto")
    for _codigo, col in lojas_cols:
        assert g.loc["MACA GALA KG", col] == 10
        assert g.loc["KIWI 600G", col] == 20
    assert g["TOTAL"].sum() == pytest.approx(2 * (10 + 20 + 8))
    # as colunas da nota final são as do cliente, na ordem, mais as que o DE/PARA
    # de lojas acrescenta (configuracoes.py:99 faz o mesmo no app). No Bigbox o
    # DE/PARA padrão traz BB-VIPIRES -> coluna VIPIRES (ver achado acima).
    extras = ["VIPIRES"] if cid == "bigbox" else []
    assert r.colunas == config.CLIENTES[cid]["grade_cols"] + extras
    # a nota final em Excel abre e tem as abas das lojas
    from helpers import abrir_xlsx

    wb = abrir_xlsx(r.excel_nota_final())
    assert wb.sheetnames[0] == "NOTA_FINAL"
    for _codigo, col in lojas_cols:
        assert col in wb.sheetnames


def _itens_euro():
    return numerar([
        Item("AMENDOA CRUA BDJ 150G COMPANY", 6, 12.40, "CX", multiplicador=18),
        Item("CASTANHA CAJU COMPANY TOR/SALG 100G", 4, 9.30, "CX", multiplicador=24),
        Item("MIX DE AMENDOIM EUROCOMPANY 200G", 10, 6.10, "CX", multiplicador=9),
        Item("UVA PASSAS COMPANY BRANCA 200G", 3, 4.75, "CX", multiplicador=12),
    ])


@pytest.mark.parametrize("layout", ["multilinha", "linha_unica", "visual", "horizontal"])
def test_euro_company_ciclo_completo_com_caixas_multiunidade(layout):
    """Regressão do commit 1f81184: caixas 'CX 18/24/9/12' zeravam a extração."""
    texto = (
        pedido_texto("9001", "ULT01-PLANDF", _itens_euro(), layout=layout)
        + pedido_texto("9002", "BIG20-TAGC1", _itens_euro(), layout=layout)
    )
    r = _rodar("eurocompany", texto)
    assert len(r.base) == 8
    assert r.criticos == 0, r.validacoes.to_string()
    assert set(r.base["Método padronização"]) == {"DE/PARA"}
    assert set(r.base["Unidade"]) == {"CX"}
    assert set(r.base["Embalagem"]) == {"CX"}
    assert set(r.base["Produto padronizado"]) == {
        "AMENDOA CRUA 150G", "CASTANHA DE CAJU TORRADA COM SAL 100G",
        "MIX DE AMENDOIM 200G", "UVA PASSA BRANCA 200G",
    }
    g = r.nota_final.set_index("Produto")
    assert g.loc["AMENDOA CRUA 150G", "PLAN"] == 6
    assert g.loc["AMENDOA CRUA 150G", "T-CENTRO"] == 6
    assert r.controle["Total PDF"].sum() == pytest.approx(r.total_dia)


def test_euro_company_aceita_a_variante_antiga_do_nome_do_produto():
    itens = numerar([
        Item("AMEIXA SECA COMPANY S/CAROCO 200G", 5, 8.0, "CX", multiplicador=18),
        Item("AMEIXA SECA BDJ 200G COMPANY", 7, 8.0, "CX", multiplicador=18, seq=2, cod=100002),
    ])
    r = _rodar("eurocompany", pedido_texto("1", "ULT01-PLANDF", itens, layout="multilinha"))
    assert set(r.base["Produto padronizado"]) == {"AMEIXA SECA S/CAROCO 200G"}
    assert r.nota_final.set_index("Produto").loc["AMEIXA SECA S/CAROCO 200G", "PLAN"] == 12


def test_euro_company_loja_nova_vira_pendencia_nao_erro_silencioso():
    """A descrição do cliente diz: lojas novas aparecem em Pendências."""
    r = _rodar("eurocompany", pedido_texto("1", "ULT77-NOVAXX", _itens_euro(), layout="multilinha"))
    assert r.criticos >= 1
    assert "ULT77-NOVAXX" in list(r.pend_lojas["Código PDF"])


def test_ultrabox_e_euro_compartilham_o_cadastro_de_lojas():
    lojas_u, _ = config.criar_config_padrao_cliente("ultrabox")
    lojas_e, _ = config.criar_config_padrao_cliente("eurocompany")
    pd.testing.assert_frame_equal(lojas_u, lojas_e)


def test_cliente_desconhecido_cai_no_padrao_ultrabox():
    assert config.obter_cliente("inexistente")["nome"] == "ULTRABOX"
