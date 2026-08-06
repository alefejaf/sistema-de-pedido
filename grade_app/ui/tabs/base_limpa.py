"""Aba BASE LIMPA: base extraida, resumo por pedido e controle de extracao."""
import streamlit as st

from ..styles import rotulo_severidade


def render(base, resumo, controle_extracao):
    st.subheader("Base limpa extraída do PDF")
    base_column_config = {
        "Preço unitário": st.column_config.NumberColumn("Preço unitário", format="R$ %.2f"),
        "Valor do item": st.column_config.NumberColumn("Valor do item", format="R$ %.2f"),
        "Valor calculado": st.column_config.NumberColumn("Valor calculado", format="R$ %.2f"),
        "Diferença item": st.column_config.NumberColumn("Diferença item", format="R$ %.2f"),
        "Total do pedido PDF": st.column_config.NumberColumn("Total do pedido PDF", format="R$ %.2f"),
    }
    st.dataframe(base, use_container_width=True, height=520, column_config=base_column_config)
    st.subheader("Resumo por pedido")
    st.dataframe(resumo, use_container_width=True)
    st.subheader("Controle de extração pedido a pedido")
    st.caption("Este controle compara itens esperados no PDF x itens extraídos e total do PDF x soma dos itens. Serve para pegar item que não foi lido.")
    controle_exibicao = controle_extracao.copy()
    if "Status" in controle_exibicao.columns:
        controle_exibicao["Status"] = controle_exibicao["Status"].map(rotulo_severidade)
    controle_config = {
        "Total PDF": st.column_config.NumberColumn("Total PDF", format="R$ %.2f"),
        "Total itens extraídos": st.column_config.NumberColumn("Total itens extraídos", format="R$ %.2f"),
        "Diferença": st.column_config.NumberColumn("Diferença", format="R$ %.2f"),
    }
    st.dataframe(controle_exibicao, use_container_width=True, column_config=controle_config)
