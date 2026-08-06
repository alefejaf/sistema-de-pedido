"""CSS e paleta visual compartilhada por toda a interface.

Reaproveita a mesma paleta ja usada nos arquivos Excel exportados
(fmt_header, fmt_crit, fmt_warn, fmt_ok em excel_export.py), para a tela web
e a planilha gerada terem a mesma identidade visual.
"""
import streamlit as st

COR_MARCA = "#1F4E78"
COR_MARCA_ESCURA = "#15385A"
COR_OK_BG = "#D9EAD3"
COR_OK_FG = "#1E7B34"
COR_ATENCAO_BG = "#FFF2CC"
COR_ATENCAO_FG = "#8A6D00"
COR_CRITICO_BG = "#F4CCCC"
COR_CRITICO_FG = "#A61C1C"

_CSS = f"""
<style>
h1, h2, h3 {{
    color: {COR_MARCA_ESCURA};
}}
div[data-testid="stMetric"] {{
    background: rgba(31, 78, 120, 0.06);
    border: 1px solid rgba(31, 78, 120, 0.18);
    border-radius: 10px;
    padding: 0.7rem 1rem;
}}
div[data-testid="stMetricLabel"] {{
    color: {COR_MARCA_ESCURA};
}}
.grade-card-subtitulo {{
    color: #333;
    font-weight: 600;
    margin-bottom: 0.15rem;
}}
</style>
"""


def aplicar_estilo_global():
    """Injeta o CSS compartilhado. Chamar uma vez por tela renderizada."""
    st.markdown(_CSS, unsafe_allow_html=True)


def rotulo_severidade(valor: str) -> str:
    """Prefixa um indicador colorido por emoji, coerente com o Excel exportado.

    Usado só para exibicao em tela (copia do dado); nao altera o valor
    original usado nas planilhas exportadas nem em nenhuma outra logica.
    """
    valor_norm = str(valor or "").strip().upper()
    if valor_norm == "CRÍTICO":
        return "🔴 CRÍTICO"
    if valor_norm == "ATENÇÃO":
        return "🟡 ATENÇÃO"
    if valor_norm == "OK":
        return "🟢 OK"
    return valor
