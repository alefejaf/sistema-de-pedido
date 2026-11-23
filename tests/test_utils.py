"""grade_app.utils: normalização de texto e números no padrão brasileiro."""
import pytest

from grade_app.utils import br_numero_para_float, eh_sim, formatar_moeda_br, normalizar


@pytest.mark.parametrize("entrada,esperado", [
    ("1.234,56", 1234.56),
    ("0,00", 0.0),
    ("15,0000", 15.0),
    ("1.404,00", 1404.0),
    ("R$ 2.496,70", 2496.70),
    ("-12,50", -12.5),
    ("", 0.0),
    (None, 0.0),
    (float("nan"), 0.0),
    ("abc", 0.0),
    (7, 7.0),
    (3.5, 3.5),
])
def test_br_numero_para_float(entrada, esperado):
    assert br_numero_para_float(entrada) == pytest.approx(esperado)


@pytest.mark.parametrize("entrada,esperado", [
    (1234.5, "R$ 1.234,50"),
    (0, "R$ 0,00"),
    ("2.496,70", "R$ 2.496,70"),
    (1000000, "R$ 1.000.000,00"),
])
def test_formatar_moeda_br(entrada, esperado):
    assert formatar_moeda_br(entrada) == esperado


@pytest.mark.parametrize("entrada,esperado", [
    ("Maçã  Fuji", "MACA FUJI"),
    ("  ult01-plandf ", "ULT01 PLANDF"),
    ("Amêndoa/Torrada", "AMENDOA TORRADA"),
    (None, ""),
    (float("nan"), ""),
    ("", ""),
    (123, "123"),
])
def test_normalizar(entrada, esperado):
    assert normalizar(entrada) == esperado


@pytest.mark.parametrize("valor", ["SIM", "sim", "S", "x", "1", "True", "yes", " Sim "])
def test_eh_sim_verdadeiros(valor):
    assert eh_sim(valor) is True


@pytest.mark.parametrize("valor", ["", "NAO", "não", "0", None, "talvez", float("nan")])
def test_eh_sim_falsos(valor):
    assert eh_sim(valor) is False
