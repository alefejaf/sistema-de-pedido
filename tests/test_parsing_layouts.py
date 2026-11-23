"""Regressão dos layouts de linha de produto (grade_app.parsing).

Cada layout abaixo existe porque algum PDF real o exigiu (ver docstrings de
``parsing.py``). Os testes usam linhas SINTÉTICAS no mesmo formato.

Regressão importante: o commit 1f81184 trocou o ``1`` fixo depois da
embalagem por ``\\d{1,3}`` para suportar caixas ("CX 18", "CX 24", "CX 9") da
Euro Company. ``test_caixa_multiunidade_*`` impede a volta desse defeito.
"""
import pytest

from grade_app.parsing import (
    contar_indicios_produtos,
    contar_itens_indicios_bloco,
    extrair_linhas_produtos,
    limpar_produto_original,
    normalizar_embalagem,
    produto_pdf_parece_valido,
)
from synth import LAYOUTS, Item, numerar, pedido_texto, total_itens


def _itens_variados():
    return numerar([
        Item("MACA GALA KG", 10, 5.50, "KG"),
        Item("KIWI 600G", 20, 7.25, "UN"),
        Item("AMEIXA 500G", 12, 3.10, "UN"),
        Item("UVA THOMPSON 500G", 1500, 0.99, "UN"),   # milhar (1.500,00)
    ])


def _resumo(itens_extraidos):
    return [
        (i["Produto original"], i["Embalagem"], i["Quantidade"], i["Preço unitário"], i["Valor do item"])
        for i in itens_extraidos
    ]


# --------------------------------------------------------------------------
# Todos os layouts devolvem exatamente os mesmos itens
# --------------------------------------------------------------------------
@pytest.mark.parametrize("layout", LAYOUTS)
def test_layout_extrai_todos_os_itens(layout):
    itens = _itens_variados()
    bloco = pedido_texto("1", "ULT01-PLANDF", itens, layout=layout)
    extraidos = extrair_linhas_produtos(bloco)
    esperado = [(i.produto, i.embalagem, i.quantidade, i.preco, i.valor) for i in itens]
    assert _resumo(extraidos) == esperado


@pytest.mark.parametrize("layout", LAYOUTS)
def test_layout_soma_dos_itens_confere_com_total(layout):
    itens = _itens_variados()
    bloco = pedido_texto("1", "ULT01-PLANDF", itens, layout=layout)
    soma = sum(i["Valor do item"] for i in extrair_linhas_produtos(bloco))
    assert soma == pytest.approx(total_itens(itens))


@pytest.mark.parametrize("layout", LAYOUTS)
def test_layout_itens_esperados_batem_com_itens(layout):
    """O contador de 'itens esperados' (usado na validação) tem que concordar
    com a extração; senão o controle de extração acusaria falso CRÍTICO."""
    itens = _itens_variados()
    bloco = pedido_texto("1", "ULT01-PLANDF", itens, layout=layout)
    assert contar_itens_indicios_bloco(bloco) == len(itens)


@pytest.mark.parametrize("layout", [
    "multilinha", "linha_unica", "horizontal",
    pytest.param("visual", marks=pytest.mark.xfail(
        strict=True,
        reason="LIMITAÇÃO CONHECIDA: contar_indicios_produtos não pontua o layout 'visual' "
               "(linha única sem Cod Forn). Só afeta a escolha entre PyMuPDF e pdfplumber; "
               "a extração em si funciona. Se corrigirem, remova este xfail.",
    )),
])
def test_layout_indicios_para_escolha_do_motor_de_pdf(layout):
    itens = _itens_variados()
    bloco = pedido_texto("1", "ULT01-PLANDF", itens, layout=layout)
    assert contar_indicios_produtos(bloco) >= len(itens)


# --------------------------------------------------------------------------
# Regressão Euro Company: caixa multi-unidade
# --------------------------------------------------------------------------
@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("mult", [1, 9, 12, 18, 24, 100])
def test_caixa_multiunidade_nao_zera_a_extracao(layout, mult):
    itens = numerar([Item("AMENDOA CRUA BDJ 150G COMPANY", 6, 12.40, "CX", multiplicador=mult)])
    bloco = pedido_texto("1", "ULT01-PLANDF", itens, layout=layout)
    extraidos = extrair_linhas_produtos(bloco)
    assert len(extraidos) == 1, f"layout={layout} CX {mult}: nenhuma linha extraída"
    assert extraidos[0]["Embalagem"] == "CX"
    assert extraidos[0]["Quantidade"] == 6.0
    assert extraidos[0]["Valor do item"] == pytest.approx(74.40)


def test_regressao_regex_antiga_com_digito_fixo_falharia():
    """Documenta o defeito corrigido: a regex antiga (``\\s*1``) não casava
    com 'CX 18'. Se alguém reverter a correção, este teste e o anterior caem."""
    import re

    antiga = re.compile(r"(UN|UND|KG|CX|FD)\s*1\s+\d")
    assert antiga.search("CX 18 6,00") is None
    from grade_app.parsing import LINHA_PRODUTO_VISUAL_RE

    linha = "7001 AMENDOA CRUA CX 18 6,00 12,4000 74,40 74,40"
    assert LINHA_PRODUTO_VISUAL_RE.search(linha) is not None


# --------------------------------------------------------------------------
# Casos reais documentados em parsing.py (strings sintéticas equivalentes)
# --------------------------------------------------------------------------
def test_formato_colado_do_totvs():
    """Exemplo do docstring: números colados, sem espaços entre os campos."""
    bloco = "PEDIDO DE COMPRAS 1\n1.404,0040[360255] 1.404,003,9000360,00KG 1MACA GAL\n"
    itens = extrair_linhas_produtos(bloco)
    assert len(itens) == 1
    assert itens[0]["Quantidade"] == 360.0
    assert itens[0]["Preço unitário"] == pytest.approx(3.90)
    assert itens[0]["Valor do item"] == pytest.approx(1404.0)


def test_item_sem_codigo_pinha_kg_layout_quebrado():
    """PINHA KG vem sem a linha seq[cod] (caso real citado no código)."""
    bloco = "\n".join([
        "PEDIDO DE COMPRAS 1", "Valor Unit.",
        "97,20", "97,20", "16,2000", "6,00", "KG 1", "PINHA KG", "7966",
        "EANs: 7890000000017",
    ])
    itens = extrair_linhas_produtos(bloco)
    assert len(itens) == 1
    assert itens[0]["Produto original"] == "PINHA KG"
    assert itens[0]["Valor do item"] == pytest.approx(97.20)


def test_item_sem_codigo_e_sem_valor_repetido():
    bloco = "\n".join([
        "PEDIDO DE COMPRAS 1", "Valor Unit.",
        "97,20", "16,2000", "6,00", "KG 1", "PINHA KG", "7966", "EANs: 1",
    ])
    itens = extrair_linhas_produtos(bloco)
    assert len(itens) == 1 and itens[0]["Quantidade"] == 6.0


def test_horizontal_junta_continuacao_do_nome():
    itens = numerar([Item("CAQUI RAMA", 50, 4.50, "UN")])
    bloco = pedido_texto("1", "COSTA-TAG", itens, layout="horizontal", continuacoes={0: "FORTE 500G"})
    extraidos = extrair_linhas_produtos(bloco)
    assert extraidos[0]["Produto original"] == "CAQUI RAMA FORTE 500G"


def test_horizontal_continuacao_ruido_nao_entra_no_nome():
    itens = numerar([Item("GENGIBRE KG -", 14, 6.50, "KG")])
    bloco = pedido_texto("1", "COSTA-TAG", itens, layout="horizontal",
                         continuacoes={0: "TAGUATINGA SETOR NORTE"})
    extraidos = extrair_linhas_produtos(bloco)
    assert extraidos[0]["Produto original"] == "GENGIBRE KG"


def test_und_e_normalizado_para_un():
    assert normalizar_embalagem("UND") == "UN"
    assert normalizar_embalagem("kg") == "KG"
    assert normalizar_embalagem(None) == ""


def test_linhas_de_rodape_nao_viram_item():
    bloco = "\n".join([
        "PEDIDO DE COMPRAS 1",
        "1.000,00 1.000,00 TOTAIS",
        "EANs: 7890000000017",
        "1.000,00 Valor total do pedido",
    ])
    assert extrair_linhas_produtos(bloco) == []


def test_bloco_vazio():
    assert extrair_linhas_produtos("") == []
    assert contar_indicios_produtos("") == 0
    assert contar_itens_indicios_bloco("") == 0


def test_deduplicacao_mesma_linha_em_duas_estrategias():
    """Uma linha capturada por mais de uma estratégia não pode duplicar o item."""
    itens = numerar([Item("MACA GALA KG", 10, 5.5, "KG")])
    bloco = pedido_texto("1", "ULT01-PLANDF", itens, layout="horizontal")
    assert len(extrair_linhas_produtos(bloco)) == 1


def test_itens_identicos_em_pedido_sao_colapsados_limitacao_conhecida():
    """CARACTERIZAÇÃO (não é desejo): dois itens com produto/emb/qtd/preço/
    valor idênticos viram um só pela deduplicação. Na prática o controle de
    extração (itens esperados x extraídos) sinaliza CRÍTICO nesse caso."""
    a = Item("MACA GALA KG", 10, 5.5, "KG", seq=1, cod=100001)
    b = Item("MACA GALA KG", 10, 5.5, "KG", seq=2, cod=100002)
    bloco = pedido_texto("1", "ULT01-PLANDF", [a, b], layout="multilinha")
    assert len(extrair_linhas_produtos(bloco)) == 1
    assert contar_itens_indicios_bloco(bloco) == 2


@pytest.mark.parametrize("texto,valido", [
    ("MACA GALA KG", True),
    ("EANs: 123", False),
    ("TOTAIS", False),
    ("123456", False),
    ("", False),
    ("VALOR TOTAL DO PEDIDO", False),
])
def test_produto_pdf_parece_valido(texto, valido):
    assert produto_pdf_parece_valido(texto) is valido


@pytest.mark.parametrize("entrada,esperado", [
    ("maca gala kg1234", "MACA GALA KG"),
    ("UVA 500G123", "UVA 500G"),
    ("PRODUTO - REF: 99887", "PRODUTO"),
    ("  PRODUTO   COM   ESPACOS ", "PRODUTO COM ESPACOS"),
])
def test_limpar_produto_original(entrada, esperado):
    assert limpar_produto_original(entrada) == esperado
