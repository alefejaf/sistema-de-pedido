"""grade_app.excel_export e geração do Excel de configuração."""
import io

import pandas as pd
import pytest

from grade_app import config
from grade_app.excel_export import gerar_excel, gerar_excel_nota_final
from helpers import abrir_xlsx, depara_lojas, depara_produtos, processar
from synth import Item, numerar, pedido_texto
from xlsx_eval import avaliar, linha_por_rotulo

LOJAS = depara_lojas(("ULT01-PLANDF", "LOJA A", "PLAN"), ("ULT02-GAMA", "LOJA B", "GAM"))
PRODS = depara_produtos(("MACA GALA KG", "MACA GALA KG", "KG"), ("KIWI 600G", "KIWI 600G", "UN"))


def _resultado():
    itens = numerar([Item("MACA GALA KG", 10, 5.5, "KG"), Item("KIWI 600G", 20, 7.25)])
    return processar(pedido_texto("1", "ULT01-PLANDF", itens) + pedido_texto("2", "ULT02-GAMA", itens), LOJAS, PRODS)


# --------------------------------------------------------------------------
# NOTA FINAL
# --------------------------------------------------------------------------
def test_nota_final_estrutura_das_linhas():
    ws = abrir_xlsx(_resultado().excel_nota_final())["NOTA_FINAL"]
    assert ws["A1"].value == "TOTAL DE ITENS"       # linha 1: contagens
    assert ws["A2"].value == "Produto"               # linha 2: cabeçalho
    assert [ws.cell(row=r, column=1).value for r in (3, 4)] == ["KIWI 600G", "MACA GALA KG"]  # produtos
    cab = [c.value for c in ws[1]]
    assert "STATUS" in cab
    assert any(c.value == "DIGITAÇÃO" for c in ws[2])


def test_nota_final_formulas_apontam_para_as_celulas_certas():
    r = _resultado()
    ws = abrir_xlsx(r.excel_nota_final())["NOTA_FINAL"]
    cols = {ws.cell(row=2, column=c).value: c for c in range(1, ws.max_column + 1)}
    total_letra = ws.cell(row=3, column=cols["TOTAL"]).column_letter
    assert ws.cell(row=3, column=cols["TOTAL"]).value.startswith("=SUM(B3:")
    assert ws.cell(row=3, column=cols["TOTAL"]).value.endswith("3)")
    preco_col = next(c for c in range(1, ws.max_column + 1) if ws.cell(row=1, column=c).value == "PREÇO")
    assert ws.cell(row=2, column=preco_col).value.startswith(f"=SUMPRODUCT({total_letra}3:{total_letra}4,")


def test_nota_final_valores_recalculados_batem_com_dataframe():
    r = _resultado()
    ws = abrir_xlsx(r.excel_nota_final())["NOTA_FINAL"]
    esperado = r.nota_final.set_index("Produto")
    cols = {ws.cell(row=2, column=c).value: c for c in range(1, ws.max_column + 1)}
    for linha in (3, 4):
        produto = ws.cell(row=linha, column=1).value
        for loja in ("PLAN", "GAM"):
            assert ws.cell(row=linha, column=cols[loja]).value == esperado.loc[produto, loja]
        preco_col = next(c for c in range(1, ws.max_column + 1) if ws.cell(row=1, column=c).value == "PREÇO")
        assert ws.cell(row=linha, column=preco_col).value == pytest.approx(esperado.loc[produto, "PREÇO"])


def test_nota_final_tem_lista_de_status_e_formatacao_condicional():
    ws = abrir_xlsx(_resultado().excel_nota_final())["NOTA_FINAL"]
    validacoes = ws.data_validations.dataValidation
    assert len(validacoes) == 1
    lista = validacoes[0].formula1
    for opcao in ("OK", "NÃO TEM", "VAI CHEGAR"):
        assert opcao in lista
    assert len(ws.conditional_formatting) >= 1
    assert ws.freeze_panes == "B3"


def test_nota_final_sem_nenhum_produto_com_quantidade_nao_quebra():
    vazio = pd.DataFrame(columns=["Produto", "PLAN", "TOTAL", "PREÇO"])
    wb = abrir_xlsx(gerar_excel_nota_final(vazio, pd.DataFrame(), 0.0, "X"))
    assert "NOTA_FINAL" in wb.sheetnames


def test_nota_final_estrutura_inesperada_gera_so_cabecalho():
    df = pd.DataFrame({"Produto": ["A"], "X": [1]})  # sem TOTAL/PREÇO
    ws = abrir_xlsx(gerar_excel_nota_final(df, pd.DataFrame()))["NOTA_FINAL"]
    assert ws["A2"].value == "Produto"


def test_nota_final_numero_de_lojas_variavel():
    """Funciona com 1 loja ou com todas as 25 colunas padrão."""
    base_cols = config.GRADE_COLS_PADRAO
    df = pd.DataFrame([["MACA", *[1] * len(base_cols), len(base_cols), 2.0]],
                      columns=["Produto", *base_cols, "TOTAL", "PREÇO"])
    ws = abrir_xlsx(gerar_excel_nota_final(df, pd.DataFrame()))["NOTA_FINAL"]
    assert avaliar(ws, ws.cell(row=3, column=len(base_cols) + 2)) == len(base_cols)


# --------------------------------------------------------------------------
# Abas por loja
# --------------------------------------------------------------------------
def test_aba_da_loja_so_tem_itens_com_quantidade_positiva():
    itens = numerar([Item("MACA GALA KG", 10, 5.5, "KG"), Item("KIWI 600G", 0, 7.25)])
    r = processar(pedido_texto("1", "ULT01-PLANDF", itens, total=55.0), LOJAS, PRODS)
    ws = abrir_xlsx(r.excel_nota_final())["PLAN"]
    produtos = [ws.cell(row=i, column=1).value for i in range(2, ws.max_row + 1)]
    assert "KIWI 600G" not in produtos
    assert "MACA GALA KG" in produtos


def test_nome_da_aba_da_loja_e_sanitizado_e_limitado_a_31_caracteres():
    lojas = depara_lojas(("ULT01-PLANDF", "LOJA", "A/B:C?[x]*" + "Z" * 40))
    itens = numerar([Item("MACA GALA KG", 10, 5.5, "KG")])
    r = processar(pedido_texto("1", "ULT01-PLANDF", itens), lojas, PRODS)
    nomes = abrir_xlsx(r.excel_nota_final()).sheetnames
    aba = [n for n in nomes if n != "NOTA_FINAL"][0]
    assert len(aba) <= 31
    assert not any(ch in aba for ch in "\\*?:/[]")


def test_sem_base_nao_cria_abas_de_loja():
    wb = abrir_xlsx(gerar_excel_nota_final(pd.DataFrame(columns=["Produto", "TOTAL", "PREÇO"]), pd.DataFrame()))
    assert wb.sheetnames == ["NOTA_FINAL"]


# --------------------------------------------------------------------------
# Excel completo
# --------------------------------------------------------------------------
def test_excel_completo_leia_me_e_abas_de_conferencia():
    wb = abrir_xlsx(_resultado().excel_completo())
    ws = wb["VALIDACOES"]
    assert [c.value for c in ws[1]][:3] == ["Severidade", "Tipo", "Número do pedido"]
    assert ws.max_row >= 2
    assert wb["CONTROLE_EXTRACAO"].max_row == 3  # cabeçalho + 2 pedidos


def test_excel_completo_sem_controle_de_extracao():
    r = _resultado()
    dados = gerar_excel(r.base, r.nota_final, r.validacoes, r.lojas, r.produtos, r.resumo, r.config_grade, None)
    # Sem controle, o sistema mantém a aba (vazia) em vez de quebrar.
    wb = abrir_xlsx(dados)
    assert "CONTROLE_EXTRACAO" in wb.sheetnames
    assert wb["CONTROLE_EXTRACAO"].max_row <= 1


# --------------------------------------------------------------------------
# Excel de configuração (DE/PARA) - ida e volta
# --------------------------------------------------------------------------
def test_excel_config_ida_e_volta_preserva_depara_e_grade():
    lojas, prods, grade = config.carregar_config(None, "ultrabox")
    lojas = config.preparar_depara_lojas(lojas)
    prods = config.preparar_depara_produtos(prods)
    grade = config.preparar_config_grade(grade, "ultrabox")
    dados = config.gerar_excel_config(lojas, prods, grade, "ULTRABOX")
    l2, p2, g2 = config.carregar_config_excel(io.BytesIO(dados), "ultrabox")
    pd.testing.assert_frame_equal(l2.reset_index(drop=True), lojas.reset_index(drop=True))
    pd.testing.assert_frame_equal(p2.reset_index(drop=True), prods.reset_index(drop=True))
    assert list(g2["Coluna da grade"]) == list(grade["Coluna da grade"])
    assert abrir_xlsx(dados).sheetnames == ["DE_PARA_LOJAS", "DE_PARA_PRODUTOS", "CONFIG_GRADE", "LEIA-ME"]


def test_excel_config_descarta_linhas_totalmente_vazias():
    lojas = pd.DataFrame([["ULT01-PLANDF", "A", "PLAN", ""], ["", "", "", ""]], columns=config.preparar_depara_lojas(None).columns)
    prods = pd.DataFrame([["X", "X", "UN"], ["", "", ""]], columns=config.preparar_depara_produtos(None).columns)
    dados = config.gerar_excel_config(lojas, prods, None, "T")
    l2, p2, _ = config.carregar_config_excel(io.BytesIO(dados))
    assert len(l2) == 1 and len(p2) == 1


def test_config_antiga_sem_aba_config_grade_ainda_carrega():
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        pd.DataFrame([["ULT01-PLANDF", "A", "PLAN"]], columns=["Código PDF", "Nome da loja", "Coluna da grade"]).to_excel(w, sheet_name="DE_PARA_LOJAS", index=False)
        pd.DataFrame([["X", "X", "UN"]], columns=["Nome do produto no PDF", "Nome oficial na grade", "Unidade"]).to_excel(w, sheet_name="DE_PARA_PRODUTOS", index=False)
    lojas, prods, grade = config.carregar_config_excel(io.BytesIO(buf.getvalue()), "bigbox")
    assert list(grade["Coluna da grade"]) == config.CLIENTES["bigbox"]["grade_cols"]
    assert "Usar preço referência" in lojas.columns
