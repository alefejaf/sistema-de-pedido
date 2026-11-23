"""Conciliação de valores ponta a ponta.

Regra de ouro do sistema: *o que sai no Excel tem que fechar com o total do
PDF*. Aqui conferimos a cadeia inteira (PDF real -> texto -> base ->
controle de extração -> grade -> Excel recalculado).
"""
import pytest

from grade_app.excel_export import gerar_excel_nota_final
from grade_app.pdf_text import extrair_texto_pdfs
from helpers import abrir_xlsx, depara_lojas, depara_produtos, processar
from synth import ArquivoFake, Item, LAYOUTS, numerar, pedido_texto, texto_para_pdf_bytes, total_itens
from xlsx_eval import avaliar, linha_por_rotulo, valor

LOJAS = depara_lojas(("ULT01-PLANDF", "LOJA A", "PLAN"), ("ULT02-GAMA", "LOJA B", "GAM"),
                     ("ULT03-COL", "LOJA C", "SOB"))
PRODS = depara_produtos(
    ("MACA GALA KG", "MACA GALA KG", "KG"),
    ("KIWI 600G", "KIWI 600G", "UN"),
    ("AMEIXA 500G", "AMEIXA 500G", "UN"),
    ("UVA THOMPSON 500G", "UVA THOMPSON 500G", "UN"),
)


def _itens(escala=1):
    return numerar([
        Item("MACA GALA KG", 10 * escala, 5.50, "KG"),
        Item("KIWI 600G", 20 * escala, 7.25),
        Item("AMEIXA 500G", 12 * escala, 3.10),
        Item("UVA THOMPSON 500G", 1500 * escala, 0.99),
    ])


def _tres_lojas(layout="multilinha"):
    return (
        pedido_texto("1001", "ULT01-PLANDF", _itens(1), layout=layout)
        + pedido_texto("1002", "ULT02-GAMA", _itens(2), layout=layout)
        + pedido_texto("1003", "ULT03-COL", _itens(3), layout=layout)
    )


# --------------------------------------------------------------------------
# PDF -> base -> controle
# --------------------------------------------------------------------------
@pytest.mark.parametrize("layout", LAYOUTS)
def test_controle_de_extracao_fecha_em_todos_os_layouts(layout):
    r = processar(_tres_lojas(layout), LOJAS, PRODS)
    assert list(r.controle["Status"]) == ["OK", "OK", "OK"]
    assert (r.controle["Diferença"].abs() < 0.005).all()
    assert (r.controle["Itens esperados no PDF"] == r.controle["Itens extraídos"]).all()
    assert r.criticos == 0


@pytest.mark.parametrize("layout", LAYOUTS)
def test_total_do_dia_e_soma_dos_totais_dos_pdfs(layout):
    r = processar(_tres_lojas(layout), LOJAS, PRODS)
    esperado = total_itens(_itens(1)) + total_itens(_itens(2)) + total_itens(_itens(3))
    assert r.total_dia == pytest.approx(esperado)


def test_pipeline_com_pdf_real_gerado_fecha_valores():
    pdf = texto_para_pdf_bytes(_tres_lojas("horizontal"))
    texto = extrair_texto_pdfs([ArquivoFake(pdf)])
    r = processar(texto, LOJAS, PRODS)
    assert r.criticos == 0
    assert r.total_dia == pytest.approx(total_itens(_itens(1)) + total_itens(_itens(2)) + total_itens(_itens(3)))


def test_valor_do_item_igual_quantidade_vezes_preco():
    r = processar(_tres_lojas(), LOJAS, PRODS)
    assert (r.base["Diferença item"].abs() < 0.01).all()


def test_item_nao_extraido_e_detectado_pelo_controle():
    """Se uma linha de produto estragar (formato desconhecido), o total e a
    contagem de itens têm que denunciar — o sistema não pode falhar calado."""
    texto = pedido_texto("1001", "ULT01-PLANDF", _itens(1), layout="horizontal")
    linhas = texto.splitlines()
    idx = next(i for i, l in enumerate(linhas) if "KIWI 600G" in l)
    linhas[idx] = "LINHA ILEGIVEL KIWI 600G ???"
    r = processar("\n".join(linhas), LOJAS, PRODS)
    assert r.controle["Status"].iloc[0] == "CRÍTICO"
    assert r.criticos >= 1
    assert r.controle["Itens extraídos"].iloc[0] == 3
    assert r.controle["Diferença"].iloc[0] == pytest.approx(20 * 7.25)


def test_pedido_sem_nenhum_item_extraido_e_critico():
    texto = "PEDIDO DE COMPRAS 5\nULT01-PLANDF\n1.000,00 Valor total do pedido\n"
    r = processar(texto, LOJAS, PRODS)
    assert r.controle["Status"].iloc[0] == "CRÍTICO"
    assert "nenhum item foi extraído" in r.controle["Alerta"].iloc[0]


def test_pedido_sem_total_com_itens_e_critico():
    r = processar(pedido_texto("1", "ULT01-PLANDF", _itens(), incluir_total=False), LOJAS, PRODS)
    assert r.controle["Status"].iloc[0] == "CRÍTICO"
    assert "Total do pedido não foi identificado" in r.controle["Alerta"].iloc[0]


# --------------------------------------------------------------------------
# Grade -> Excel recalculado
# --------------------------------------------------------------------------
def _nota_ws(r):
    return abrir_xlsx(r.excel_nota_final())["NOTA_FINAL"]


def _colunas(ws):
    """cabeçalho (linha 2) -> índice de coluna (1-based).

    Layout da NOTA_FINAL: linha 1 = contagens + rótulo "PREÇO"; linha 2 =
    cabeçalhos, EXCETO a célula PREÇO, que na linha 2 guarda a fórmula do total
    do pedido (SUMPRODUCT). Por isso o rótulo PREÇO é lido da linha 1."""
    cols = {ws.cell(row=2, column=c).value: c for c in range(1, ws.max_column + 1)}
    for c in range(1, ws.max_column + 1):
        if ws.cell(row=1, column=c).value == "PREÇO":
            cols["PREÇO"] = c
    return cols


def test_total_da_grade_igual_total_das_quantidades_da_base():
    r = processar(_tres_lojas(), LOJAS, PRODS)
    assert r.nota_final["TOTAL"].sum() == pytest.approx(r.base["Quantidade"].sum())


def test_excel_total_por_produto_recalculado_fecha_com_a_grade():
    r = processar(_tres_lojas(), LOJAS, PRODS)
    ws = _nota_ws(r)
    cols = _colunas(ws)
    for linha in range(3, ws.max_row + 1):
        produto = ws.cell(row=linha, column=1).value
        esperado = r.nota_final.set_index("Produto").loc[produto, "TOTAL"]
        assert avaliar(ws, ws.cell(row=linha, column=cols["TOTAL"])) == pytest.approx(esperado)


def test_excel_total_do_pedido_igual_soma_dos_pdfs_quando_precos_sao_iguais():
    """SUMPRODUCT(TOTAL; PREÇO) da NOTA_FINAL == soma dos totais dos PDFs."""
    r = processar(_tres_lojas(), LOJAS, PRODS)
    ws = _nota_ws(r)
    cols = _colunas(ws)
    total_excel = avaliar(ws, ws.cell(row=2, column=cols["PREÇO"]))
    assert total_excel == pytest.approx(r.total_dia)


def test_excel_contagem_de_itens_por_loja():
    r = processar(_tres_lojas(), LOJAS, PRODS)
    ws = _nota_ws(r)
    cols = _colunas(ws)
    assert ws.cell(row=1, column=1).value == "TOTAL DE ITENS"
    for loja in ("PLAN", "GAM", "SOB"):
        assert avaliar(ws, ws.cell(row=1, column=cols[loja])) == 4  # 4 produtos com qtd > 0


def test_excel_abas_por_loja_fecham_com_o_total_de_cada_pdf():
    r = processar(_tres_lojas(), LOJAS, PRODS)
    wb = abrir_xlsx(r.excel_nota_final())
    esperado = {"PLAN": total_itens(_itens(1)), "GAM": total_itens(_itens(2)), "SOB": total_itens(_itens(3))}
    for aba, total in esperado.items():
        ws = wb[aba]
        linha = linha_por_rotulo(ws, "TOTAL PEDIDO")
        assert linha is not None
        assert avaliar(ws, ws.cell(row=linha, column=3)) == pytest.approx(total)


def test_excel_nota_final_omite_produtos_sem_quantidade():
    """Produto cadastrado mas ausente do PDF não aparece na NOTA FINAL limpa."""
    itens = numerar([Item("MACA GALA KG", 10, 5.5, "KG")])
    r = processar(pedido_texto("1", "ULT01-PLANDF", itens), LOJAS, PRODS)
    ws = _nota_ws(r)
    produtos = [ws.cell(row=i, column=1).value for i in range(3, ws.max_row + 1)]
    assert produtos == ["MACA GALA KG"]


def test_diferenca_de_preco_entre_lojas_nota_final_usa_um_preco_so():
    """CARACTERIZAÇÃO / RISCO CONHECIDO: a NOTA FINAL tem UM preço por produto
    (o primeiro das lojas normais). Se as lojas vieram com preços diferentes, o
    total em Excel (SUMPRODUCT) NÃO bate com a soma dos totais dos PDFs. O
    sistema avisa com a validação ATENÇÃO 'Produto com preços diferentes'."""
    a = numerar([Item("MACA GALA KG", 10, 5.0, "KG")])
    b = numerar([Item("MACA GALA KG", 10, 6.0, "KG")])
    r = processar(pedido_texto("1", "ULT01-PLANDF", a) + pedido_texto("2", "ULT02-GAMA", b), LOJAS, PRODS)
    assert "Produto com preços diferentes" in set(r.validacoes["Tipo"])
    ws = _nota_ws(r)
    cols = _colunas(ws)
    total_excel = avaliar(ws, ws.cell(row=2, column=cols["PREÇO"]))
    assert r.total_dia == pytest.approx(110.0)       # 50 + 60 (soma dos PDFs)
    assert total_excel == pytest.approx(100.0)       # 20 x 5,00 (preço único)
    assert total_excel != pytest.approx(r.total_dia)


def test_excel_completo_tem_as_abas_de_conferencia_e_valores_da_base():
    r = processar(_tres_lojas(), LOJAS, PRODS)
    wb = abrir_xlsx(r.excel_completo())
    for aba in ["NOTA_FINAL", "BASE_LIMPA", "VALIDACOES", "RESUMO_PEDIDOS", "CONTROLE_EXTRACAO",
                "DE_PARA_LOJAS", "DE_PARA_PRODUTOS", "CONFIG_GRADE", "LEIA-ME"]:
        assert aba in wb.sheetnames
    ws = wb["BASE_LIMPA"]
    cab = [c.value for c in ws[1]]
    i_valor = cab.index("Valor do item")
    soma = sum(ws.cell(row=r_, column=i_valor + 1).value for r_ in range(2, ws.max_row + 1))
    assert soma == pytest.approx(r.base["Valor do item"].sum())


def test_resumo_pedidos_diferenca_zero_quando_fecha():
    r = processar(_tres_lojas(), LOJAS, PRODS)
    assert (r.resumo["Diferença"].abs() < 0.005).all()
    assert r.resumo["Total_PDF"].sum() == pytest.approx(r.total_dia)
