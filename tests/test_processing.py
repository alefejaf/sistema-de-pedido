"""grade_app.processing: DE/PARA (lojas e produtos), validações, grade e pendências."""
import pandas as pd
import pytest

from grade_app import config
from grade_app.processing import (
    calcular_total_pedido_dia,
    extrair_base,
    gerar_grade,
    gerar_pendencias_depara,
    gerar_resumo_pedidos,
    gerar_validacoes,
    padronizar_produtos,
)
from helpers import depara_lojas, depara_produtos, processar
from synth import Item, numerar, pedido_texto

LOJAS = depara_lojas(("ULT01-PLANDF", "LOJA A", "PLAN"), ("ULT02-GAMA", "LOJA B", "GAM"))
PRODS = depara_produtos(
    ("MACA GALA KG", "MACA GALA KG", "KG"),
    ("KIWI 600G", "KIWI 600G", "UN"),
    ("AMEIXA 500G", "AMEIXA 500G", "UN"),
)


def _itens():
    return numerar([Item("MACA GALA KG", 10, 5.5, "KG"), Item("KIWI 600G", 20, 7.25), Item("AMEIXA 500G", 12, 3.1)])


def _validacoes(texto, lojas=LOJAS, prods=PRODS):
    r = processar(texto, lojas, prods)
    return r, set(r.validacoes["Tipo"])


# --------------------------------------------------------------------------
# DE/PARA de lojas
# --------------------------------------------------------------------------
def test_depara_loja_preenche_nome_e_coluna():
    texto = pedido_texto("1", "ULT01-PLANDF", _itens())
    base = extrair_base(texto, LOJAS, PRODS)
    assert set(base["Coluna da grade"]) == {"PLAN"}
    assert set(base["Nome da loja"]) == {"LOJA A"}


def test_depara_loja_ignora_acento_caixa_e_pontuacao():
    lojas = depara_lojas(("ult01-plandf", "LOJA A", "PLAN"))
    base = extrair_base(pedido_texto("1", "ULT01-PLANDF", _itens()), lojas, PRODS)
    assert set(base["Coluna da grade"]) == {"PLAN"}


def test_loja_sem_depara_gera_critico_e_pendencia():
    r, tipos = _validacoes(pedido_texto("1", "ULT09-NOVA", _itens()))
    assert "Loja sem DE/PARA" in tipos
    assert r.criticos > 0
    assert list(r.pend_lojas["Código PDF"]) == ["ULT09-NOVA"]


# --------------------------------------------------------------------------
# DE/PARA de produtos
# --------------------------------------------------------------------------
def test_produto_exato_usa_depara():
    base = extrair_base(pedido_texto("1", "ULT01-PLANDF", _itens()), LOJAS, PRODS)
    assert set(base["Método padronização"]) == {"DE/PARA"}
    assert set(base["Score produto"]) == {100}


def test_produto_sem_cadastro_vira_critico_e_pendencia():
    itens = numerar([Item("PRODUTO TOTALMENTE NOVO XYZ", 5, 2.0)])
    r, tipos = _validacoes(pedido_texto("1", "ULT01-PLANDF", itens))
    assert "Produto sem cadastro" in tipos
    assert list(r.pend_produtos["Nome do produto no PDF"]) == ["PRODUTO TOTALMENTE NOVO XYZ"]
    assert r.base["Método padronização"].iloc[0] == "SEM CADASTRO"
    assert r.base["Produto padronizado"].iloc[0] == "PRODUTO TOTALMENTE NOVO XYZ"


def test_depara_substitui_nome_pelo_oficial_e_unidade_em_maiuscula():
    prods = depara_produtos(("UVA VITO", "uva vitoria 500g", "un"))
    itens = numerar([Item("UVA VITO", 4, 9.9)])
    base = extrair_base(pedido_texto("1", "ULT01-PLANDF", itens), LOJAS, prods)
    assert base["Produto padronizado"].iloc[0] == "UVA VITORIA 500G"
    assert base["Unidade"].iloc[0] == "UN"


def test_produto_fuzzy_aceito_acima_de_82():
    prods = depara_produtos(("MACA FUJI KG", "MACA FUJI KG", "KG"))
    df = pd.DataFrame({"Produto original": ["MACA FUJII KG"]})
    out = padronizar_produtos(df, prods)
    assert out["Método padronização"].iloc[0] == "FUZZY"
    assert out["Produto padronizado"].iloc[0] == "MACA FUJI KG"
    assert out["Score produto"].iloc[0] >= 82


def test_produto_fuzzy_baixo_gera_atencao_nao_critico():
    # Score entre 82 e 91 => ATENÇÃO "Produto com nome divergente".
    prods = depara_produtos(("MORANGO 250G BANDEJA", "MORANGO 250G", "UN"))
    itens = numerar([Item("MORANGO 250 BAND", 3, 8.0)])
    r = processar(pedido_texto("1", "ULT01-PLANDF", itens), LOJAS, prods)
    metodo = r.base["Método padronização"].iloc[0]
    if metodo == "FUZZY" and r.base["Score produto"].iloc[0] < 92:
        assert "Produto com nome divergente" in set(r.validacoes["Tipo"])
        sev = r.validacoes[r.validacoes["Tipo"] == "Produto com nome divergente"]["Severidade"].iloc[0]
        assert sev == "ATENÇÃO"


def test_produto_muito_diferente_nao_casa_por_fuzzy():
    prods = depara_produtos(("MACA FUJI KG", "MACA FUJI KG", "KG"))
    out = padronizar_produtos(pd.DataFrame({"Produto original": ["CASTANHA DO PARA"]}), prods)
    assert out["Método padronização"].iloc[0] == "SEM CADASTRO"


def test_depara_vazio_nao_quebra():
    out = padronizar_produtos(pd.DataFrame({"Produto original": ["QUALQUER"]}), depara_produtos())
    assert out["Método padronização"].iloc[0] == "SEM CADASTRO"


def test_ordem_do_depara_importa_padrao_curto_sombreia_o_longo():
    """CARACTERIZAÇÃO de comportamento atual: a busca por substring devolve o
    PRIMEIRO padrão que casa. Um padrão curto ('MACA GALA') listado antes de
    um longo ('MACA GALA 1KG') impede o longo de ser usado."""
    prods = depara_produtos(
        ("MACA GALA", "MACA GALA KG", "KG"),
        ("MACA GALA 1KG", "MACA GALA 1KG", "UN"),
    )
    out = padronizar_produtos(pd.DataFrame({"Produto original": ["MACA GALA 1KG"]}), prods)
    assert out["Produto padronizado"].iloc[0] == "MACA GALA KG"  # atual (provavelmente indesejado)

    invertido = depara_produtos(
        ("MACA GALA 1KG", "MACA GALA 1KG", "UN"),
        ("MACA GALA", "MACA GALA KG", "KG"),
    )
    out2 = padronizar_produtos(pd.DataFrame({"Produto original": ["MACA GALA 1KG"]}), invertido)
    assert out2["Produto padronizado"].iloc[0] == "MACA GALA 1KG"


# --------------------------------------------------------------------------
# Validações
# --------------------------------------------------------------------------
def test_pedido_correto_nao_tem_criticos_nem_atencoes():
    r, tipos = _validacoes(pedido_texto("1", "ULT01-PLANDF", _itens()))
    assert tipos == {"Sem inconsistência crítica"}
    assert r.criticos == 0 and r.atencoes == 0


def test_preco_zerado_e_critico():
    itens = numerar([Item("MACA GALA KG", 10, 0.0, "KG")])
    _, tipos = _validacoes(pedido_texto("1", "ULT01-PLANDF", itens, total=0.0))
    assert "Preço zerado" in tipos


def test_total_ausente_no_pdf_e_critico():
    _, tipos = _validacoes(pedido_texto("1", "ULT01-PLANDF", _itens(), incluir_total=False))
    assert "Total do pedido não identificado" in tipos


def test_total_divergente_e_critico():
    _, tipos = _validacoes(pedido_texto("1", "ULT01-PLANDF", _itens(), total=999.99))
    assert "Total divergente" in tipos


def test_total_dentro_da_tolerancia_de_10_centavos_passa():
    itens = _itens()
    total_ok = sum(i.valor for i in itens)
    _, tipos = _validacoes(pedido_texto("1", "ULT01-PLANDF", itens, total=total_ok + 0.09))
    assert "Total divergente" not in tipos


def test_total_acima_da_tolerancia_falha():
    itens = _itens()
    total_ok = sum(i.valor for i in itens)
    _, tipos = _validacoes(pedido_texto("1", "ULT01-PLANDF", itens, total=total_ok + 0.11))
    assert "Total divergente" in tipos


def test_pedido_duplicado_em_lojas_diferentes():
    a = pedido_texto("1", "ULT01-PLANDF", _itens())
    b = pedido_texto("2", "ULT02-GAMA", _itens())
    # mesmo número 1 reaparece, agora na loja GAMA (não consecutivo => não é "página repetida")
    c = pedido_texto("1", "ULT02-GAMA", _itens())
    _, tipos = _validacoes(a + b + c)
    assert "Pedido duplicado" in tipos


def test_loja_nao_identificada_no_pdf():
    texto = pedido_texto("1", "", _itens(), cabecalho=["Fornecedor: X", "sem codigo de loja"])
    _, tipos = _validacoes(texto)
    assert "Loja não identificada no PDF" in tipos


def test_precos_diferentes_entre_lojas_sem_referencia_gera_atencao():
    a = numerar([Item("MACA GALA KG", 10, 5.5, "KG")])
    b = numerar([Item("MACA GALA KG", 10, 6.0, "KG")])
    r, tipos = _validacoes(pedido_texto("1", "ULT01-PLANDF", a) + pedido_texto("2", "ULT02-GAMA", b))
    assert "Produto com preços diferentes" in tipos
    assert r.criticos == 0 and r.atencoes == 1


def test_precos_diferentes_com_loja_referencia_unica_nao_alerta():
    lojas = depara_lojas(("ULT01-PLANDF", "A", "PLAN", "SIM"), ("ULT02-GAMA", "B", "GAM"))
    a = numerar([Item("MACA GALA KG", 10, 5.5, "KG")])
    b = numerar([Item("MACA GALA KG", 10, 6.0, "KG")])
    r = processar(pedido_texto("1", "ULT01-PLANDF", a) + pedido_texto("2", "ULT02-GAMA", b), lojas, PRODS)
    tipos = set(r.validacoes["Tipo"])
    assert "Produto com preços diferentes" not in tipos
    assert "Preço referência divergente" not in tipos


def test_duas_lojas_referencia_com_precos_diferentes_alerta():
    lojas = depara_lojas(("ULT01-PLANDF", "A", "PLAN", "SIM"), ("ULT02-GAMA", "B", "GAM", "SIM"))
    a = numerar([Item("MACA GALA KG", 10, 5.5, "KG")])
    b = numerar([Item("MACA GALA KG", 10, 6.0, "KG")])
    r = processar(pedido_texto("1", "ULT01-PLANDF", a) + pedido_texto("2", "ULT02-GAMA", b), lojas, PRODS)
    assert "Preço referência divergente" in set(r.validacoes["Tipo"])


def test_pdf_sem_itens_gera_critico():
    r = processar("texto qualquer sem pedidos", LOJAS, PRODS)
    assert r.base.empty
    assert r.criticos == 1
    assert "Nenhum pedido de compras foi reconhecido" in r.validacoes["Detalhe"].iloc[0]


def test_pdf_codificado_cid_gera_critico_especifico():
    texto = " ".join(f"(cid:{i})" for i in range(40))
    r = processar(texto, LOJAS, PRODS)
    assert r.criticos == 1
    assert "codificado" in r.validacoes["Detalhe"].iloc[0]


def test_validacoes_de_base_vazia_com_controle_none():
    v = gerar_validacoes(pd.DataFrame(), None)
    assert v["Severidade"].iloc[0] == "CRÍTICO"


# --------------------------------------------------------------------------
# Grade (NOTA FINAL)
# --------------------------------------------------------------------------
def test_grade_pivota_quantidade_por_loja_e_soma_total():
    r = processar(pedido_texto("1", "ULT01-PLANDF", _itens()) + pedido_texto("2", "ULT02-GAMA", _itens()), LOJAS, PRODS)
    g = r.nota_final.set_index("Produto")
    assert g.loc["MACA GALA KG", "PLAN"] == 10 and g.loc["MACA GALA KG", "GAM"] == 10
    assert g.loc["KIWI 600G", "TOTAL"] == 40
    assert list(g.columns) == r.colunas + ["TOTAL", "PREÇO"]


def test_grade_soma_quantidades_do_mesmo_produto_na_mesma_loja():
    itens = numerar([Item("MACA GALA KG", 10, 5.5, "KG"), Item("MACA GALA KG", 4, 5.5, "KG")])
    r = processar(pedido_texto("1", "ULT01-PLANDF", itens), LOJAS, PRODS)
    assert r.nota_final.set_index("Produto").loc["MACA GALA KG", "PLAN"] == 14


def test_grade_ignora_coluna_nao_visivel_mas_mantem_na_base():
    cfg = pd.DataFrame({"Posição": [1], "Coluna da grade": ["PLAN"], "Mostrar": [True]})
    base = extrair_base(pedido_texto("1", "ULT02-GAMA", _itens()), LOJAS, PRODS)
    g = gerar_grade(base, ["PLAN"])
    assert g["TOTAL"].sum() == 0  # GAM não está na grade
    assert len(base) == 3        # mas os itens continuam na base


def test_grade_preco_normal_tem_prioridade_sobre_referencia():
    lojas = depara_lojas(("ULT01-PLANDF", "A", "PLAN", "SIM"), ("ULT02-GAMA", "B", "GAM"))
    a = numerar([Item("MACA GALA KG", 10, 5.0, "KG")])   # referência
    b = numerar([Item("MACA GALA KG", 10, 6.0, "KG")])   # normal
    r = processar(pedido_texto("1", "ULT01-PLANDF", a) + pedido_texto("2", "ULT02-GAMA", b), lojas, PRODS)
    assert r.nota_final.set_index("Produto").loc["MACA GALA KG", "PREÇO"] == pytest.approx(6.0)


def test_grade_usa_preco_da_referencia_se_nao_ha_loja_normal_com_o_produto():
    lojas = depara_lojas(("ULT01-PLANDF", "A", "PLAN", "SIM"), ("ULT02-GAMA", "B", "GAM"))
    a = numerar([Item("KIWI 600G", 10, 7.0)])
    r = processar(pedido_texto("1", "ULT01-PLANDF", a), lojas, PRODS)
    assert r.nota_final.set_index("Produto").loc["KIWI 600G", "PREÇO"] == pytest.approx(7.0)


def test_grade_ordenada_por_produto():
    r = processar(pedido_texto("1", "ULT01-PLANDF", _itens()), LOJAS, PRODS)
    nomes = list(r.nota_final["Produto"])
    assert nomes == sorted(nomes)


def test_grade_vazia():
    g = gerar_grade(pd.DataFrame(), ["A", "B"])
    assert list(g.columns) == ["Produto", "A", "B", "TOTAL", "PREÇO"] and g.empty


# --------------------------------------------------------------------------
# Resumo e pendências
# --------------------------------------------------------------------------
def test_resumo_pedidos_por_loja():
    r = processar(pedido_texto("1", "ULT01-PLANDF", _itens()), LOJAS, PRODS)
    linha = r.resumo.iloc[0]
    assert linha["Itens"] == 3
    assert linha["Quantidade_Total"] == 42
    assert linha["Diferença"] == pytest.approx(0.0)


def test_pendencias_vazias_quando_tudo_cadastrado():
    r = processar(pedido_texto("1", "ULT01-PLANDF", _itens()), LOJAS, PRODS)
    assert r.pend_lojas.empty and r.pend_produtos.empty


def test_pendencias_de_base_vazia():
    pl, pp = gerar_pendencias_depara(pd.DataFrame())
    assert pl.empty and pp.empty


def test_total_pedido_dia_soma_cada_pedido_uma_vez():
    a = pedido_texto("1", "ULT01-PLANDF", _itens())
    b = pedido_texto("2", "ULT02-GAMA", _itens())
    base = extrair_base(a + b, LOJAS, PRODS)
    total_um = sum(i.valor for i in _itens())
    assert calcular_total_pedido_dia(base) == pytest.approx(2 * total_um)


def test_total_pedido_dia_sem_total_no_pdf_soma_itens():
    texto = pedido_texto("1", "ULT01-PLANDF", _itens(), incluir_total=False)
    base = extrair_base(texto, LOJAS, PRODS)
    assert calcular_total_pedido_dia(base) == pytest.approx(sum(i.valor for i in _itens()))


def test_total_pedido_dia_base_vazia():
    assert calcular_total_pedido_dia(pd.DataFrame()) == 0.0
    assert calcular_total_pedido_dia(None) == 0.0


# --------------------------------------------------------------------------
# Configuração padrão: sombreamento nas configs empacotadas (achado da auditoria)
# --------------------------------------------------------------------------
@pytest.mark.xfail(
    strict=True,
    reason="ACHADO: nas configs de bigbox/costa/fort o padrão 'MACA GALA' vem ANTES de "
           "'MACA GALA 1KG', então a segunda entrada nunca é usada (ver "
           "test_ordem_do_depara_importa_...). Corrigir exige alterar dados de configuração "
           "em produção; por isso só fica documentado aqui. Remova o xfail após corrigir.",
)
@pytest.mark.parametrize("cliente", ["bigbox", "costa", "fort"])
def test_config_empacotada_maca_gala_1kg_e_alcancavel(cliente):
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    _, prods, _ = config.carregar_config_excel(raiz / "configs" / f"config_{cliente}.xlsx", cliente)
    out = padronizar_produtos(pd.DataFrame({"Produto original": ["MACA GALA 1KG"]}), prods)
    assert out["Produto padronizado"].iloc[0] == "MACA GALA 1KG"
