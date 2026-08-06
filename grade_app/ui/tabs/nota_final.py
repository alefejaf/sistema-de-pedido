"""Aba NOTA FINAL: grade pronta para digitacao/conferencia do pedido."""
from datetime import datetime

import streamlit as st

from ...utils import eh_sim, formatar_moeda_br


def render_sem_pdf():
    st.info("Suba de 1 até 5 PDFs de pedido de compras TOTVS para gerar a NOTA FINAL.")
    st.markdown("""
    **Fluxo esperado:**
    1. Subir de 1 até 5 PDFs do TOTVS/Consinco.
    2. Conferir a aba **VALIDAÇÕES**.
    3. Ajustar o **DE/PARA** na aba **CONFIGURAÇÕES**, se necessário.
    4. Baixar a **NOTA FINAL** em Excel para digitar/conferir o pedido.
    5. Ajustar **ordem/ocultação de lojas** na aba **CONFIGURAÇÕES**, se precisar.
    """)


def render(cliente_slug, lojas, nota_final, colunas_grade, total_pedido_dia, criticos,
           bloquear_criticos, nota_final_bytes, excel_completo_bytes, pode_baixar=True):
    titulo_col, total_col = st.columns([3, 1])
    with titulo_col:
        st.subheader("NOTA FINAL para digitação do pedido")
    with total_col:
        st.metric("Total do pedido do dia", formatar_moeda_br(total_pedido_dia))
    st.caption("Esta é a grade limpa para usar na digitação/conferência: produtos nas linhas, lojas nas colunas, total e preço em R$.")
    lojas_preco_ref = lojas[lojas["Usar preço referência"].apply(eh_sim)]["Código PDF"].astype(str).tolist() if "Usar preço referência" in lojas.columns else []
    if lojas_preco_ref:
        st.caption("Preço referência aplicado: " + ", ".join(lojas_preco_ref))
    nota_column_config = {"PREÇO": st.column_config.NumberColumn("PREÇO", format="R$ %.2f")}
    for col in colunas_grade + ["TOTAL"]:
        if col in nota_final.columns:
            nota_column_config[col] = st.column_config.NumberColumn(col, format="%.2f")
    st.dataframe(nota_final, use_container_width=True, height=540, column_config=nota_column_config)
    c1, c2 = st.columns(2)
    with c1:
        if not pode_baixar:
            st.info("Seu perfil (visualizador) não tem permissão para baixar arquivos.")
        elif bloquear_criticos and criticos > 0:
            st.warning("Download da NOTA FINAL bloqueado por validação crítica. Corrija o DE/PARA ou desmarque a trava no menu lateral.")
        else:
            st.download_button(
                "⬇️ Baixar NOTA FINAL para digitar pedido",
                data=nota_final_bytes,
                file_name=f"nota_final_{cliente_slug}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    with c2:
        if pode_baixar:
            st.download_button(
                "⬇️ Baixar Excel completo com conferências",
                data=excel_completo_bytes,
                file_name=f"grade_completa_{cliente_slug}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.info("Seu perfil (visualizador) não tem permissão para baixar arquivos.")
