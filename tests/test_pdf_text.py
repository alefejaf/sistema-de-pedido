"""grade_app.pdf_text: leitura de PDF e leitura de cabeçalho/total do pedido.

Todos os PDFs aqui são gerados na hora por ``synth.py`` (dados fictícios).
"""
import pytest

from grade_app.pdf_text import (
    dividir_pedidos,
    extrair_data_emissao,
    extrair_loja,
    extrair_texto_pdfs,
    extrair_total_pedido,
    montar_codigo_loja,
    texto_pdf_parece_codificado,
)
from synth import (
    ArquivoFake,
    Item,
    cabecalho_costa,
    cabecalho_fort,
    numerar,
    pedido_texto,
    texto_para_pdf_bytes,
)


# --------------------------------------------------------------------------
# dividir_pedidos
# --------------------------------------------------------------------------
def _itens():
    return numerar([Item("MACA GALA KG", 10, 5.5, "KG"), Item("KIWI 600G", 20, 7.25)])


def test_dividir_pedidos_separa_varios_pedidos():
    texto = pedido_texto("100001", "ULT01-PLANDF", _itens()) + pedido_texto("100002/L", "ULT02-GAMA", _itens())
    pedidos = dividir_pedidos(texto)
    assert [n for n, _ in pedidos] == ["100001", "100002/L"]


def test_dividir_pedidos_junta_paginas_repetidas_do_mesmo_pedido():
    p = pedido_texto("100001", "ULT01-PLANDF", _itens())
    pedidos = dividir_pedidos(p + p)
    assert len(pedidos) == 1
    assert pedidos[0][0] == "100001"


def test_dividir_pedidos_nao_junta_pedidos_diferentes_nao_consecutivos():
    a = pedido_texto("1", "ULT01-PLANDF", _itens())
    b = pedido_texto("2", "ULT02-GAMA", _itens())
    assert [n for n, _ in dividir_pedidos(a + b + a)] == ["1", "2", "1"]


def test_dividir_pedidos_texto_sem_pedido():
    assert dividir_pedidos("qualquer coisa sem cabeçalho") == []
    assert dividir_pedidos("") == []


def test_dividir_pedidos_remove_nulos():
    texto = "PEDIDO DE COMPRAS 55\x00\nlinha"
    assert dividir_pedidos(texto)[0][0] == "55"


# --------------------------------------------------------------------------
# extrair_loja
# --------------------------------------------------------------------------
@pytest.mark.parametrize("codigo", ["ULT01-PLANDF", "ULT08-ARAP", "ULT15-SOLNA", "BIG20-TAGC1", "BIG21-CNB12"])
def test_extrair_loja_codigo_ult_big(codigo):
    bloco = pedido_texto("1", codigo, _itens())
    assert extrair_loja(bloco) == codigo


def test_extrair_loja_ignora_cep():
    bloco = "PEDIDO DE COMPRAS 1\nCEP72-123\nULT03-COL LOJA\n"
    assert extrair_loja(bloco) == "ULT03-COL"


def test_extrair_loja_costa():
    bloco = "PEDIDO DE COMPRAS 1\n" + "\n".join(cabecalho_costa("TAGUATINGA"))
    assert extrair_loja(bloco) == "COSTA-TAGUATINGA"


def test_extrair_loja_costa_nome_composto():
    bloco = "PEDIDO DE COMPRAS 1\n" + "\n".join(cabecalho_costa("SANTA MARIA"))
    assert extrair_loja(bloco) == "COSTA-SANTA-MARIA"


def test_extrair_loja_costa_texto_em_uma_linha():
    bloco = "PEDIDO DE COMPRAS 1 COSTA MULTICANAL S/A LOJA VALPARAISO R. SOCIAL XPTO"
    assert extrair_loja(bloco) == "COSTA-VALPARAISO"


def test_extrair_loja_fort():
    bloco = "PEDIDO DE COMPRAS 1\n" + "\n".join(cabecalho_fort("66", "VALPARAISO"))
    assert extrair_loja(bloco) == "FORT66-VALPARAISO"


def test_extrair_loja_fort_texto_em_uma_linha():
    bloco = "PEDIDO DE COMPRAS 1 DF-FORT ATACAD 138 TAGUATINGA ENDEREÇO QUALQUER"
    assert extrair_loja(bloco) == "FORT138-TAGUATINGA"


def test_extrair_loja_nao_identificada_retorna_vazio():
    assert extrair_loja("PEDIDO DE COMPRAS 1\nsem loja nenhuma aqui") == ""


def test_montar_codigo_loja():
    assert montar_codigo_loja("FORT", "RECANT EMAS", "775") == "FORT775-RECANT-EMAS"
    assert montar_codigo_loja("COSTA", "LUZIANIA") == "COSTA-LUZIANIA"


# --------------------------------------------------------------------------
# data e total
# --------------------------------------------------------------------------
def test_extrair_data_emissao_rotulada():
    assert extrair_data_emissao("15/08/2026 Data da emissão\n01/01/2020") == "15/08/2026"


def test_extrair_data_emissao_fallback_primeira_data():
    assert extrair_data_emissao("algo 02/03/2025 algo") == "02/03/2025"


def test_extrair_data_emissao_ausente():
    assert extrair_data_emissao("sem data") == ""


@pytest.mark.parametrize("bloco,esperado", [
    ("2.496,70 Valor total do pedido", 2496.70),
    ("Valor total do pedido 2.496,70", 2496.70),
    ("Valor total do pedido\n2.496,70", 2496.70),
    ("400,00 2.496,70 2.496,70 TOTAIS", 2496.70),  # fallback: maior valor perto de TOTAIS
    ("sem total nenhum", 0.0),
])
def test_extrair_total_pedido_variacoes_de_texto(bloco, esperado):
    assert extrair_total_pedido(bloco) == pytest.approx(esperado)


# --------------------------------------------------------------------------
# texto codificado (cid:)
# --------------------------------------------------------------------------
def test_texto_codificado_detectado():
    assert texto_pdf_parece_codificado(" ".join(f"(cid:{i})" for i in range(30))) is True


def test_texto_normal_nao_e_codificado():
    assert texto_pdf_parece_codificado("PEDIDO DE COMPRAS 1 texto normal") is False
    assert texto_pdf_parece_codificado("") is False


# --------------------------------------------------------------------------
# PDF real (gerado) -> texto
# --------------------------------------------------------------------------
def test_extrair_texto_pdfs_le_pdf_real_e_preserva_conteudo():
    texto_original = pedido_texto("100001", "ULT01-PLANDF", _itens(), layout="horizontal")
    pdf = texto_para_pdf_bytes(texto_original)
    assert pdf.startswith(b"%PDF")
    lido = extrair_texto_pdfs([ArquivoFake(pdf, "a.pdf")])
    assert "PEDIDO DE COMPRAS 100001" in lido
    assert "ULT01-PLANDF" in lido
    assert "MACA GALA KG" in lido
    assert "ARQUIVO PDF 1: a.pdf" in lido


def test_extrair_texto_pdfs_aceita_ate_5_arquivos():
    arqs = [
        ArquivoFake(texto_para_pdf_bytes(pedido_texto(str(i), "ULT01-PLANDF", _itens())), f"{i}.pdf")
        for i in range(1, 8)
    ]
    lido = extrair_texto_pdfs(arqs)
    assert "ARQUIVO PDF 5:" in lido
    assert "ARQUIVO PDF 6:" not in lido  # 6º e 7º são ignorados (limite documentado)


def test_extrair_texto_pdfs_sem_arquivos():
    assert extrair_texto_pdfs(None) == ""
    assert extrair_texto_pdfs([]) == ""


def test_extrair_texto_pdfs_pdf_invalido_levanta_erro_amigavel():
    with pytest.raises(RuntimeError, match="Não consegui ler o PDF"):
        extrair_texto_pdfs([ArquivoFake(b"isto nao e um pdf", "x.pdf")])


def test_pdf_multipagina_mantem_pedido_unico():
    itens = numerar([Item(f"PRODUTO TESTE {n:02d}", 2, 1.5) for n in range(1, 40)])
    texto = pedido_texto("777", "ULT01-PLANDF", itens, layout="horizontal")
    pdf = texto_para_pdf_bytes(texto, linhas_por_pagina=20)
    lido = extrair_texto_pdfs([ArquivoFake(pdf)])
    assert "--- PAGINA 3 ---" in lido
    assert [n for n, _ in dividir_pedidos(lido)] == ["777"]
