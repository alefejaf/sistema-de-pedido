import streamlit as st

from grade_app.auth import exigir_login, pode_editar_configuracoes, pode_baixar_arquivos
from grade_app.config import (
    APP_NAME,
    obter_cliente,
    slug_cliente,
    carregar_config,
    preparar_depara_lojas,
    preparar_depara_produtos,
    preparar_config_grade,
)
from grade_app.pdf_text import extrair_texto_pdfs
from grade_app.processing import (
    extrair_base,
    gerar_controle_extracao,
    gerar_validacoes,
    gerar_grade,
    gerar_resumo_pedidos,
    gerar_pendencias_depara,
    calcular_total_pedido_dia,
)
from grade_app.excel_export import gerar_excel, gerar_excel_nota_final
from grade_app.ui.home import exibir_tela_inicial
from grade_app.ui.sidebar import render_sidebar
from grade_app.ui.styles import aplicar_estilo_global
from grade_app.ui.tabs import configuracoes as aba_configuracoes
from grade_app.ui.tabs import nota_final as aba_nota_final
from grade_app.ui.tabs import base_limpa as aba_base_limpa
from grade_app.ui.tabs import validacoes as aba_validacoes


def main():
    exigir_login()

    perfil = st.session_state.get("perfil", "")
    pode_editar = pode_editar_configuracoes(perfil)
    pode_baixar = pode_baixar_arquivos(perfil)

    cliente_id = st.session_state.get("cliente_atual", "")
    if not cliente_id:
        exibir_tela_inicial()
        return

    cliente = obter_cliente(cliente_id)
    cliente_nome = cliente["nome"]
    cliente_slug = slug_cliente(cliente_id)

    st.set_page_config(page_title=f"{APP_NAME} - {cliente_nome}", page_icon="📦", layout="wide")
    aplicar_estilo_global()
    topo1, topo2 = st.columns([4, 1])
    with topo1:
        st.title(f"📦 {cliente['icone']} Grade {cliente_nome}")
        st.caption("Transforma PDF TOTVS em NOTA FINAL/grade Excel com produtos nas linhas, lojas nas colunas, total e preço.")
    with topo2:
        if st.button("⬅️ Trocar cliente", use_container_width=True):
            st.session_state.pop("cliente_atual", None)
            st.rerun()

    pdf_files, config_file, bloquear_criticos = render_sidebar(cliente_id, cliente_nome, cliente_slug)

    lojas_inicial, produtos_inicial, config_grade_inicial = carregar_config(config_file, cliente_id)
    lojas_inicial = preparar_depara_lojas(lojas_inicial)
    produtos_inicial = preparar_depara_produtos(produtos_inicial)
    config_grade_inicial = preparar_config_grade(config_grade_inicial, cliente_id)

    tab_nota, tab_base, tab_valid, tab_config = st.tabs(["NOTA FINAL", "BASE LIMPA", "VALIDAÇÕES", "CONFIGURAÇÕES"])

    # A aba CONFIGURAÇÕES ganha duas sub-abas: Cadastro (DE/PARA + ordem da
    # grade, preenchida já aqui) e Pendências (só fica pronta depois que o PDF
    # é processado mais abaixo, mas o espaço já é reservado agora).
    with tab_config:
        subtab_cadastro, subtab_pendencias = st.tabs(["Cadastro", "Pendências"])
        with subtab_cadastro:
            lojas, produtos, config_grade, colunas_grade = aba_configuracoes.render_editores(
                cliente_id, cliente_nome, cliente_slug, lojas_inicial, produtos_inicial, config_grade_inicial,
                pode_editar,
            )

    if not pdf_files:
        with tab_nota:
            aba_nota_final.render_sem_pdf()
        with subtab_pendencias:
            aba_configuracoes.render_pendencias_placeholder()
        return

    try:
        with st.spinner("Lendo PDF(s), aplicando DE/PARA e gerando NOTA FINAL..."):
            texto = extrair_texto_pdfs(pdf_files)
            base = extrair_base(texto, lojas, produtos)
            controle_extracao = gerar_controle_extracao(texto, base)
            validacoes = gerar_validacoes(base, controle_extracao)
            nota_final = gerar_grade(base, colunas_grade)
            resumo = gerar_resumo_pedidos(base)
            total_pedido_dia = calcular_total_pedido_dia(base)
            lojas_pend, produtos_pend = gerar_pendencias_depara(base)
            excel_completo_bytes = gerar_excel(base, nota_final, validacoes, lojas, produtos, resumo, config_grade, controle_extracao)
            nota_final_bytes = gerar_excel_nota_final(nota_final, base, total_pedido_dia, cliente_nome)
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    criticos = int((validacoes["Severidade"] == "CRÍTICO").sum()) if not validacoes.empty else 0
    atencoes = int((validacoes["Severidade"] == "ATENÇÃO").sum()) if not validacoes.empty else 0
    pedidos = base["Número do pedido"].nunique() if not base.empty else 0
    itens = len(base)
    pendencias = len(lojas_pend) + len(produtos_pend)

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Pedidos lidos", pedidos)
    k2.metric("Linhas extraídas", itens)
    k3.metric("Críticos", criticos)
    k4.metric("Atenções", atencoes)
    k5.metric("Pendências de cadastro", pendencias)

    if criticos > 0:
        st.error("Existem validações críticas. Confira a aba VALIDAÇÕES antes de usar a NOTA FINAL.")
    elif atencoes > 0:
        st.warning("Existem pontos de atenção. A NOTA FINAL foi gerada, mas vale conferir.")
    else:
        st.success("NOTA FINAL gerada sem inconsistências relevantes.")

    with tab_nota:
        aba_nota_final.render(
            cliente_slug, lojas, nota_final, colunas_grade, total_pedido_dia, criticos,
            bloquear_criticos, nota_final_bytes, excel_completo_bytes, pode_baixar,
        )

    with tab_base:
        aba_base_limpa.render(base, resumo, controle_extracao)

    with tab_valid:
        aba_validacoes.render(validacoes, controle_extracao, pode_baixar)

    with subtab_pendencias:
        aba_configuracoes.render_pendencias(
            cliente_id, cliente_slug, lojas, produtos, config_grade, lojas_pend, produtos_pend, pode_editar,
        )


if __name__ == "__main__":
    main()

