"""Avaliador mínimo das fórmulas que o sistema escreve nos Excels.

O XlsxWriter grava fórmulas SEM valor em cache; por isso ``openpyxl`` com
``data_only=True`` devolveria ``None``. Para conciliar valores nos testes sem
depender de Excel/LibreOffice, este módulo recalcula as únicas funções que o
sistema usa: ``SUM``, ``COUNTIF(intervalo;">0")`` e ``SUMPRODUCT``.

Se o sistema passar a usar outra função, ``avaliar`` levanta
``NotImplementedError`` e o teste falha de forma explícita (em vez de passar
em silêncio).
"""
from __future__ import annotations

import re
from typing import List

from openpyxl.utils import range_boundaries
from openpyxl.worksheet.worksheet import Worksheet


def _celulas(ws: Worksheet, intervalo: str) -> List:
    min_col, min_row, max_col, max_row = range_boundaries(intervalo.replace("$", ""))
    return [
        ws.cell(row=r, column=c)
        for r in range(min_row, max_row + 1)
        for c in range(min_col, max_col + 1)
    ]


def _numero(ws: Worksheet, cel) -> float:
    v = avaliar(ws, cel)
    if v in (None, ""):
        return 0.0
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    return 0.0  # texto (ex.: "R$") conta como 0, igual ao Excel em SUMPRODUCT


def avaliar(ws: Worksheet, cel):
    """Valor da célula; se for fórmula, recalcula (recursivamente)."""
    v = cel.value
    if not (isinstance(v, str) and v.startswith("=")):
        return v
    f = v[1:].strip()

    m = re.fullmatch(r"SUM\(([A-Z]+\d+:[A-Z]+\d+)\)", f)
    if m:
        return sum(_numero(ws, c) for c in _celulas(ws, m.group(1)))

    m = re.fullmatch(r'COUNTIF\(([A-Z]+\d+:[A-Z]+\d+),">0"\)', f)
    if m:
        return sum(1 for c in _celulas(ws, m.group(1)) if _numero(ws, c) > 0)

    m = re.fullmatch(r"SUMPRODUCT\(([A-Z]+\d+:[A-Z]+\d+),\s*([A-Z]+\d+:[A-Z]+\d+)\)", f)
    if m:
        a, b = _celulas(ws, m.group(1)), _celulas(ws, m.group(2))
        assert len(a) == len(b), "SUMPRODUCT com intervalos de tamanhos diferentes"
        return sum(_numero(ws, x) * _numero(ws, y) for x, y in zip(a, b))

    raise NotImplementedError(f"Fórmula não suportada pelo avaliador de testes: {v}")


def valor(ws: Worksheet, endereco: str):
    return avaliar(ws, ws[endereco])


def linha_por_rotulo(ws: Worksheet, rotulo: str, coluna: int = 1):
    """Número da linha cuja coluna ``coluna`` é igual a ``rotulo``."""
    for r in range(1, ws.max_row + 1):
        if ws.cell(row=r, column=coluna).value == rotulo:
            return r
    return None
