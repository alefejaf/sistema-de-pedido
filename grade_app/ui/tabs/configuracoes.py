"""Aba CONFIGURACOES: editores DE/PARA + ordem da grade, e pendencias do PDF atual.

Os editores e os botoes de salvar/restaurar/adicionar pendencia ficam
escondidos quando pode_editar=False (perfil visualizador) — o usuario ainda
ve os dados, mas em modo somente leitura.
"""
import streamlit as st

from ... import google_sheets
from ...config import (
    remover_linhas_vazias_config,
    incluir_colunas_lojas_na_config,
    obter_colunas_grade,
    salvar_config_cliente,
    gerar_excel_config,
    criar_config_padrao_cliente,
    criar_config_grade_padrao,
    limpar_estado_editores,
    mesclar_depara_lojas,
    mesclar_depara_produtos,
)


def _salvar_e_logar(cliente_id, lojas, produtos, config_grade):
    """Salva a configuração do cliente (com backup automático, ver
    grade_app.config._fazer_backup_config) e registra o evento na aba
    `logs` do Google Sheets."""
    caminho = salvar_config_cliente(cliente_id, lojas, produtos, config_grade)
    google_sheets.registrar_log(
        st.session_state.get("usuario", ""),
        st.session_state.get("nome", ""),
        "config_salva",
        "sucesso",
        f"cliente={cliente_id}",
    )
    return caminho


def render_editores(cliente_id, cliente_nome, cliente_slug, lojas_inicial, produtos_inicial, config_grade_inicial, pode_editar=True):
    """Renderiza DE/PARA lojas/produtos + ordem da grade; salva automaticamente
    quando pode_editar=True (perfil visualizador só visualiza, sem salvar).

    Retorna (lojas, produtos, config_grade, colunas_grade) prontos para o resto da tela.
    """
    st.subheader("Configurações editáveis")
    if pode_editar:
        st.info("Você pode ajustar o DE/PARA de lojas, DE/PARA de produtos e a ordem/visibilidade da NOTA FINAL direto aqui. Para adicionar loja, inclua uma nova linha no DE/PARA Lojas. Para ocultar/excluir da NOTA FINAL, desmarque Mostrar na configuração da grade ou remova a linha que não será usada.")
    else:
        st.info("Perfil visualizador: você pode ver o DE/PARA e a ordem da grade, mas não pode editar nem salvar alterações aqui.")

    st.markdown("### DE/PARA Lojas")
    lojas_editadas = st.data_editor(
        lojas_inicial,
        use_container_width=True,
        height=360,
        num_rows="dynamic" if pode_editar else "fixed",
        disabled=not pode_editar,
        key=f"editor_depara_lojas_{cliente_slug}",
        column_config={
            "Código PDF": st.column_config.TextColumn("Código PDF", help="Ex.: ULT01-PLANDF"),
            "Nome da loja": st.column_config.TextColumn("Nome da loja", help="Nome completo para conferência"),
            "Coluna da grade": st.column_config.TextColumn("Coluna da grade", help="Coluna onde a loja aparece na nota final. Pode usar uma coluna nova, ex.: NOVA.LOJA."),
            "Usar preço referência": st.column_config.SelectboxColumn("Usar preço referência", options=["", "SIM"], help="Marque SIM na loja cujo preço deve sair na coluna PREÇO da NOTA FINAL. Ex.: ULT24-PBRASI."),
        },
    )

    st.markdown("### Ordem e visibilidade da NOTA FINAL")
    st.caption("Padrão: 25 lojas na ordem operacional. Para ocultar/excluir da NOTA FINAL, desmarque Mostrar. Para adicionar uma nova coluna/loja, crie uma nova linha ou cadastre a coluna no DE/PARA Lojas.")
    config_grade_editada = st.data_editor(
        config_grade_inicial,
        use_container_width=True,
        height=330,
        num_rows="dynamic" if pode_editar else "fixed",
        disabled=not pode_editar,
        key=f"editor_config_grade_{cliente_slug}",
        column_config={
            "Posição": st.column_config.NumberColumn("Posição", min_value=1, step=1),
            "Coluna da grade": st.column_config.TextColumn("Coluna da grade", help="Nome da coluna na NOTA FINAL. Pode ser padrão ou uma nova loja."),
            "Mostrar": st.column_config.CheckboxColumn("Mostrar"),
        },
    )

    st.markdown("### DE/PARA Produtos")
    produtos_editados = st.data_editor(
        produtos_inicial,
        use_container_width=True,
        height=420,
        num_rows="dynamic" if pode_editar else "fixed",
        disabled=not pode_editar,
        key=f"editor_depara_produtos_{cliente_slug}",
        column_config={
            "Nome do produto no PDF": st.column_config.TextColumn("Nome do produto no PDF", help="Nome como aparece no PDF TOTVS"),
            "Nome oficial na grade": st.column_config.TextColumn("Nome oficial na grade", help="Nome padronizado que vai sair na NOTA FINAL"),
            "Unidade": st.column_config.SelectboxColumn("Unidade", options=["UN", "KG", "CX", "FD", "UND", ""], help="Unidade oficial do produto"),
        },
    )

    lojas, produtos = remover_linhas_vazias_config(lojas_editadas, produtos_editados)
    config_grade = incluir_colunas_lojas_na_config(config_grade_editada, lojas, cliente_id)
    colunas_grade = obter_colunas_grade(config_grade, cliente_id)

    if pode_editar:
        # Salva automaticamente toda edição feita na aba CONFIGURAÇÕES.
        # O arquivo fica separado por cliente, evitando misturar Ultrabox, Bigbox, Costa e Fort.
        caminho_salvo = _salvar_e_logar(cliente_id, lojas, produtos, config_grade)
        st.success(f"Configuração de {cliente_nome} salva automaticamente. Na próxima abertura será carregada deste arquivo: {caminho_salvo}")
    st.caption("Colunas visíveis na NOTA FINAL: " + " | ".join(colunas_grade))

    def _botao_baixar_config(container):
        with container:
            st.download_button(
                "⬇️ Baixar configuração atualizada",
                data=gerar_excel_config(lojas, produtos, config_grade, cliente_nome),
                file_name=f"configuracao_de_para_{cliente_slug}_atualizada.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

    if pode_editar:
        c_cfg1, c_cfg2 = st.columns([1, 1])
        _botao_baixar_config(c_cfg1)
        with c_cfg2:
            if st.button("🔄 Restaurar padrão inicial deste cliente", key=f"restaurar_padrao_{cliente_slug}", use_container_width=True):
                lojas_padrao, produtos_padrao = criar_config_padrao_cliente(cliente_id)
                config_padrao = criar_config_grade_padrao(cliente_id)
                _salvar_e_logar(cliente_id, lojas_padrao, produtos_padrao, config_padrao)
                limpar_estado_editores(cliente_slug)
                st.success("Configuração padrão restaurada e salva.")
                st.rerun()
    else:
        _botao_baixar_config(st.container())

    return lojas, produtos, config_grade, colunas_grade


def render_pendencias_placeholder():
    """Mensagem exibida antes de qualquer PDF ser enviado."""
    st.info("Suba um PDF na barra lateral para o sistema apontar aqui as lojas e produtos que ainda não têm DE/PARA cadastrado.")


def render_pendencias(cliente_id, cliente_slug, lojas, produtos, config_grade, lojas_pend, produtos_pend, pode_editar=True):
    """Mostra lojas/produtos ainda sem DE/PARA encontrados no PDF atual."""
    st.subheader("Pendências encontradas neste PDF")
    if lojas_pend.empty and produtos_pend.empty:
        st.success("Nenhuma loja ou produto pendente neste PDF.")
        return
    if not pode_editar:
        st.info("Perfil visualizador: você pode ver as pendências, mas não pode cadastrá-las aqui.")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Lojas sem DE/PARA")
        if lojas_pend.empty:
            st.success("Nenhuma loja pendente.")
        else:
            lojas_pend_edit = lojas_pend.copy()
            if "Usar preço referência" not in lojas_pend_edit.columns:
                lojas_pend_edit["Usar preço referência"] = ""
            lojas_pend_edit = st.data_editor(
                lojas_pend_edit,
                use_container_width=True,
                num_rows="dynamic" if pode_editar else "fixed",
                disabled=not pode_editar,
                key=f"editor_pend_lojas_{cliente_slug}",
                column_config={
                    "Código PDF": st.column_config.TextColumn("Código PDF"),
                    "Nome da loja": st.column_config.TextColumn("Nome da loja", help="Preencha o nome da loja para conferência."),
                    "Coluna da grade": st.column_config.TextColumn("Coluna da grade", help="Ex.: REC, CNB12, T-CENTRO, LOJA 01."),
                    "Usar preço referência": st.column_config.SelectboxColumn("Usar preço referência", options=["", "SIM"]),
                },
            )
            if pode_editar:
                st.caption("Preencha a coluna da grade e clique em salvar. Essa loja ficará gravada apenas para este cliente.")
                if st.button("➕ Adicionar lojas pendentes e salvar", key=f"add_lojas_pend_{cliente_slug}", use_container_width=True):
                    faltando_coluna = lojas_pend_edit[lojas_pend_edit["Coluna da grade"].astype(str).str.strip().eq("")]
                    if not faltando_coluna.empty:
                        st.warning("Preencha a coluna da grade das lojas pendentes antes de salvar.")
                    else:
                        lojas_novas = mesclar_depara_lojas(lojas, lojas_pend_edit)
                        config_nova = incluir_colunas_lojas_na_config(config_grade, lojas_novas, cliente_id)
                        _salvar_e_logar(cliente_id, lojas_novas, produtos, config_nova)
                        limpar_estado_editores(cliente_slug)
                        st.success("Lojas pendentes adicionadas e salvas na configuração deste cliente.")
                        st.rerun()
    with c2:
        st.markdown("#### Produtos sem DE/PARA")
        if produtos_pend.empty:
            st.success("Nenhum produto pendente.")
        else:
            produtos_pend_edit = st.data_editor(
                produtos_pend,
                use_container_width=True,
                num_rows="dynamic" if pode_editar else "fixed",
                disabled=not pode_editar,
                key=f"editor_pend_produtos_{cliente_slug}",
                column_config={
                    "Nome do produto no PDF": st.column_config.TextColumn("Nome do produto no PDF"),
                    "Nome oficial na grade": st.column_config.TextColumn("Nome oficial na grade", help="Como o item deve sair na NOTA FINAL."),
                    "Unidade": st.column_config.SelectboxColumn("Unidade", options=["UN", "KG", "CX", "FD", "UND", ""]),
                },
            )
            if pode_editar:
                st.caption("Ajuste o nome oficial, se necessário, e clique em salvar. Esse produto ficará gravado apenas para este cliente.")
                if st.button("➕ Adicionar produtos pendentes e salvar", key=f"add_produtos_pend_{cliente_slug}", use_container_width=True):
                    faltando_nome = produtos_pend_edit[produtos_pend_edit["Nome oficial na grade"].astype(str).str.strip().eq("")]
                    if not faltando_nome.empty:
                        st.warning("Preencha o nome oficial dos produtos pendentes antes de salvar.")
                    else:
                        produtos_novos = mesclar_depara_produtos(produtos, produtos_pend_edit)
                        _salvar_e_logar(cliente_id, lojas, produtos_novos, config_grade)
                        limpar_estado_editores(cliente_slug)
                        st.success("Produtos pendentes adicionados e salvos na configuração deste cliente.")
                        st.rerun()
