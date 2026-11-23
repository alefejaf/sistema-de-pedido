"""Atalhos para montar o pipeline completo (texto -> base -> grade -> Excel)
nos testes, sempre com DE/PARA fictício ou com as configs do repositório."""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import List, Optional

import openpyxl
import pandas as pd

from grade_app import config
from grade_app.excel_export import gerar_excel, gerar_excel_nota_final
from grade_app.processing import (
    calcular_total_pedido_dia,
    extrair_base,
    gerar_controle_extracao,
    gerar_grade,
    gerar_pendencias_depara,
    gerar_resumo_pedidos,
    gerar_validacoes,
)

COL_LOJAS = ["Código PDF", "Nome da loja", "Coluna da grade", "Usar preço referência"]
COL_PRODS = ["Nome do produto no PDF", "Nome oficial na grade", "Unidade"]


def depara_lojas(*linhas) -> pd.DataFrame:
    """depara_lojas(("ULT01-PLANDF", "LOJA A", "PLAN"), ("ULT02-GAMA", "LOJA B", "GAM", "SIM"))"""
    dados = [list(l) + [""] * (4 - len(l)) for l in linhas]
    return config.preparar_depara_lojas(pd.DataFrame(dados, columns=COL_LOJAS))


def depara_produtos(*linhas) -> pd.DataFrame:
    """depara_produtos(("MACA GALA KG", "MACA GALA KG", "KG"), ...)"""
    return config.preparar_depara_produtos(pd.DataFrame([list(l) for l in linhas], columns=COL_PRODS))


@dataclass
class Resultado:
    texto: str
    base: pd.DataFrame
    controle: pd.DataFrame
    validacoes: pd.DataFrame
    nota_final: pd.DataFrame
    resumo: pd.DataFrame
    total_dia: float
    pend_lojas: pd.DataFrame
    pend_produtos: pd.DataFrame
    colunas: List[str]
    lojas: pd.DataFrame
    produtos: pd.DataFrame
    config_grade: pd.DataFrame

    def excel_nota_final(self, cliente="TESTE") -> bytes:
        return gerar_excel_nota_final(self.nota_final, self.base, self.total_dia, cliente)

    def excel_completo(self) -> bytes:
        return gerar_excel(self.base, self.nota_final, self.validacoes, self.lojas, self.produtos,
                           self.resumo, self.config_grade, self.controle)

    @property
    def criticos(self) -> int:
        v = self.validacoes
        return int((v["Severidade"] == "CRÍTICO").sum()) if not v.empty else 0

    @property
    def atencoes(self) -> int:
        v = self.validacoes
        return int((v["Severidade"] == "ATENÇÃO").sum()) if not v.empty else 0


def processar(texto: str, lojas: pd.DataFrame, produtos: pd.DataFrame,
              cliente_id: str = "ultrabox", config_grade: Optional[pd.DataFrame] = None) -> Resultado:
    """Replica, na mesma ordem, o que app.py faz depois de ler o PDF."""
    cfg = config.preparar_config_grade(config_grade, cliente_id)
    cfg = config.incluir_colunas_lojas_na_config(cfg, lojas, cliente_id)
    colunas = config.obter_colunas_grade(cfg, cliente_id)
    base = extrair_base(texto, lojas, produtos)
    controle = gerar_controle_extracao(texto, base)
    validacoes = gerar_validacoes(base, controle)
    nota = gerar_grade(base, colunas)
    resumo = gerar_resumo_pedidos(base)
    total = calcular_total_pedido_dia(base)
    pl, pp = gerar_pendencias_depara(base)
    return Resultado(texto, base, controle, validacoes, nota, resumo, total, pl, pp, colunas, lojas, produtos, cfg)


def abrir_xlsx(dados: bytes) -> openpyxl.Workbook:
    return openpyxl.load_workbook(io.BytesIO(dados))
