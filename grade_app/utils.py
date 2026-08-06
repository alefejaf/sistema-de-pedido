"""Utilitarios genericos: normalizacao de texto/numero, sem dependencia de UI."""
import re
import unicodedata

import pandas as pd


SIM_VALUES = {"SIM", "S", "YES", "Y", "TRUE", "1", "X"}

def eh_sim(valor: object) -> bool:
    return normalizar(valor) in SIM_VALUES

def normalizar(txt: object) -> str:
    """Normaliza texto para comparação robusta."""
    if txt is None or (isinstance(txt, float) and pd.isna(txt)):
        return ""
    txt = str(txt).upper().strip()
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    txt = re.sub(r"[^A-Z0-9]+", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt

def br_numero_para_float(valor: object) -> float:
    """Converte número brasileiro 1.234,56 para float."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    s = str(valor).strip()
    s = re.sub(r"[^0-9,.-]", "", s)
    if not s:
        return 0.0
    # Formato brasileiro: ponto milhar, vírgula decimal.
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0

def formatar_moeda_br(valor: object) -> str:
    """Formata número em moeda brasileira para exibição no Streamlit."""
    valor = br_numero_para_float(valor)
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
