"""Gerador de pedidos SINTÉTICOS no estilo TOTVS/Consinco.

Todos os nomes, lojas, preços e quantidades aqui são FICTÍCIOS. Este módulo
existe para que os testes nunca dependam de PDFs comerciais reais (o
repositório é público). Os formatos de linha reproduzem os layouts que o
parser em ``grade_app/parsing.py`` reconhece.

Uso típico::

    itens = [Item("MACA GALA KG", 10, 5.50)]
    texto = pedido_texto("100001", "ULT01-PLANDF", itens, layout="multilinha")
    pdf_bytes = texto_para_pdf_bytes(texto)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

LAYOUTS = ("multilinha", "linha_unica", "visual", "horizontal")


@dataclass
class Item:
    produto: str
    quantidade: float
    preco: float
    embalagem: str = "UN"
    multiplicador: int = 1  # o "1" de "UN 1"; 18/24/9 nas caixas Euro Company
    cod: int = 100001
    seq: int = 1

    @property
    def valor(self) -> float:
        return round(self.quantidade * self.preco, 2)


def brn(valor: float, casas: int = 2) -> str:
    """Formata número no padrão brasileiro: 1.234,56."""
    s = f"{valor:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def total_itens(itens: Iterable[Item]) -> float:
    return round(sum(i.valor for i in itens), 2)


# ---------------------------------------------------------------------------
# Linhas de item por layout
# ---------------------------------------------------------------------------
def _item_multilinha(i: Item) -> List[str]:
    return [
        brn(i.valor),
        f"{i.seq}[{i.cod}]",
        brn(i.valor),
        brn(i.preco, 4),
        brn(i.quantidade),
        f"{i.embalagem}  {i.multiplicador}",
        i.produto,
        str(7000 + i.seq),
        "EANs: 7890000000017",
    ]


def _item_linha_unica(i: Item) -> List[str]:
    # valor + seq[cod] + valor repetido + preço + qtd + emb + mult + produto
    return [
        f"{brn(i.valor)} {i.seq}[{i.cod}] {brn(i.valor)} {brn(i.preco, 4)} "
        f"{brn(i.quantidade)} {i.embalagem} {i.multiplicador} {i.produto}",
        "EANs: 7890000000017",
    ]


def _item_visual(i: Item) -> List[str]:
    return [
        f"{7000 + i.seq} {i.produto} {i.embalagem} {i.multiplicador} "
        f"{brn(i.quantidade)} {brn(i.preco, 4)} {brn(i.valor)} {brn(i.valor)}",
        "EANs: 7890000000017",
    ]


def _item_horizontal(i: Item, continuacao: Optional[str] = None) -> List[str]:
    linhas = [
        f"{i.seq}[{i.cod}] 0,00 {i.produto} {i.embalagem} {i.multiplicador} "
        f"{brn(i.quantidade)} {brn(i.preco, 4)} {brn(i.valor)} {brn(i.valor)}",
    ]
    if continuacao:
        linhas.append(continuacao)
    linhas.append("EANs: 7890000000017")
    return linhas


_BUILDERS = {
    "multilinha": _item_multilinha,
    "linha_unica": _item_linha_unica,
    "visual": _item_visual,
    "horizontal": _item_horizontal,
}


# ---------------------------------------------------------------------------
# Cabeçalhos por tipo de cliente
# ---------------------------------------------------------------------------
def cabecalho_loja(codigo_loja: str, data: str = "15/08/2026") -> List[str]:
    """Cabeçalho para lojas com código no PDF (Ultrabox/Bigbox/Euro Company):
    ULT01-PLANDF, BIG20-TAGC1 etc."""
    return [
        "Fornecedor: FORNECEDOR FICTICIO LTDA",
        f"{codigo_loja} LOJA FICTICIA",
        f"{data} Data da emissão",
    ]


def cabecalho_costa(loja: str, data: str = "15/08/2026") -> List[str]:
    return [
        "Fornecedor: FORNECEDOR FICTICIO LTDA",
        "COSTA MULTICANAL S/A",
        f"LOJA {loja}",
        f"{data} Data da emissão",
    ]


def cabecalho_fort(numero: str, loja: str, data: str = "15/08/2026") -> List[str]:
    return [
        "Fornecedor: FORNECEDOR FICTICIO LTDA",
        f"DF-FORT ATACAD {numero} {loja}",
        f"{data} Data da emissão",
    ]


def pedido_texto(
    numero: str,
    codigo_loja: str,
    itens: List[Item],
    layout: str = "multilinha",
    total: Optional[float] = None,
    cabecalho: Optional[List[str]] = None,
    incluir_total: bool = True,
    continuacoes: Optional[dict] = None,
) -> str:
    """Monta o texto de UM pedido (como se viesse do extrator de PDF).

    ``total`` permite forçar um total diferente da soma (para testar a
    conciliação). ``continuacoes`` mapeia índice do item -> texto da linha
    de continuação do nome (só layout horizontal).
    """
    if layout not in _BUILDERS:
        raise ValueError(f"layout desconhecido: {layout}")
    linhas = [f"PEDIDO DE COMPRAS {numero}"]
    linhas += cabecalho if cabecalho is not None else cabecalho_loja(codigo_loja)
    linhas.append("Cod Forn Seq Produtos Qtde Valor Unit. Valor Total")
    for idx, item in enumerate(itens):
        if layout == "horizontal":
            linhas += _item_horizontal(item, (continuacoes or {}).get(idx))
        else:
            linhas += _BUILDERS[layout](item)
    if incluir_total:
        t = total_itens(itens) if total is None else total
        linhas.append(f"{brn(t)} {brn(t)} TOTAIS")
        linhas.append(f"{brn(t)} Valor total do pedido")
    return "\n".join(linhas) + "\n"


def numerar(itens: List[Item]) -> List[Item]:
    """Dá seq/cod sequenciais e únicos (evita deduplicação indevida)."""
    for n, it in enumerate(itens, start=1):
        it.seq = n
        it.cod = 100000 + n
    return itens


# ---------------------------------------------------------------------------
# PDF real (PyMuPDF) a partir do texto
# ---------------------------------------------------------------------------
def texto_para_pdf_bytes(texto: str, linhas_por_pagina: int = 45) -> bytes:
    """Gera um PDF de verdade (uma linha de texto por linha do PDF)."""
    import fitz  # PyMuPDF

    doc = fitz.open()
    linhas = texto.splitlines()
    for ini in range(0, max(len(linhas), 1), linhas_por_pagina):
        page = doc.new_page(width=595, height=842)
        y = 40
        for linha in linhas[ini:ini + linhas_por_pagina]:
            page.insert_text((30, y), linha, fontsize=8, fontname="helv")
            y += 14
    dados = doc.tobytes()
    doc.close()
    return dados


class ArquivoFake:
    """Imita o UploadedFile do Streamlit (read/seek/name)."""

    def __init__(self, dados: bytes, nome: str = "pedido_sintetico.pdf"):
        import io

        self._buf = io.BytesIO(dados)
        self.name = nome

    def read(self, *a):
        return self._buf.read(*a)

    def seek(self, *a):
        return self._buf.seek(*a)
