"""Padronizacao (DE/PARA + fuzzy match), validacoes, controle de extracao e
geracao da grade/NOTA FINAL a partir da base extraida do PDF."""
from typing import Dict, List, Tuple

import pandas as pd

try:
    from rapidfuzz import fuzz, process
except Exception:  # pragma: no cover
    fuzz = None
    process = None

from .utils import normalizar, eh_sim
from .parsing import extrair_linhas_produtos, contar_itens_indicios_bloco
from .pdf_text import dividir_pedidos, extrair_loja, extrair_total_pedido, extrair_data_emissao, texto_pdf_parece_codificado
from .config import preparar_depara_lojas


def calcular_total_pedido_dia(base: pd.DataFrame) -> float:
    """Calcula o valor total do PDF do dia, somando cada pedido/loja uma única vez."""
    if base is None or base.empty:
        return 0.0
    if "Total do pedido PDF" in base.columns and base["Total do pedido PDF"].fillna(0).gt(0).any():
        resumo = base.groupby(["Número do pedido", "Código loja PDF"], dropna=False)["Total do pedido PDF"].max()
        return float(resumo.sum())
    if "Valor do item" in base.columns:
        return float(base["Valor do item"].fillna(0).sum())
    return 0.0

def gerar_controle_extracao(texto_pdf: str, base: pd.DataFrame) -> pd.DataFrame:
    """Gera uma auditoria pedido a pedido para flagrar item/pedido que não foi capturado."""
    pedidos = dividir_pedidos(texto_pdf)
    registros = []
    if base is not None and not base.empty:
        contagem_base = base.groupby("Número do pedido").size().to_dict()
        total_calc_base = base.groupby("Número do pedido")["Valor do item"].sum().to_dict()
    else:
        contagem_base = {}
        total_calc_base = {}

    for numero_pedido, bloco in pedidos:
        loja = extrair_loja(bloco)
        total_pdf = extrair_total_pedido(bloco)
        data_emissao = extrair_data_emissao(bloco)
        itens_indicios = contar_itens_indicios_bloco(bloco)
        itens_extraidos = int(contagem_base.get(numero_pedido, 0))
        total_extraido = float(total_calc_base.get(numero_pedido, 0.0))
        diferenca = float(total_pdf - total_extraido)
        status = "OK"
        alerta = ""
        if total_pdf <= 0 and itens_extraidos > 0:
            status = "CRÍTICO"
            alerta = "Total do pedido não foi identificado no PDF; não é possível validar 100% a extração."
        elif itens_extraidos == 0 and (itens_indicios > 0 or total_pdf > 0):
            status = "CRÍTICO"
            alerta = "Pedido encontrado no PDF, mas nenhum item foi extraído."
        elif itens_indicios > itens_extraidos:
            status = "CRÍTICO"
            alerta = f"Possível item não extraído: PDF indica {itens_indicios} itens e a base tem {itens_extraidos}."
        elif abs(diferenca) > 0.10:
            status = "CRÍTICO"
            alerta = "Total do pedido não bate com a soma dos itens extraídos."
        elif itens_indicios == 0 and itens_extraidos == 0:
            status = "ATENÇÃO"
            alerta = "Pedido sem indício de item; conferir se a página está correta."

        registros.append({
            "Status": status,
            "Número do pedido": numero_pedido,
            "Data emissão": data_emissao,
            "Código loja PDF": loja,
            "Itens esperados no PDF": itens_indicios,
            "Itens extraídos": itens_extraidos,
            "Total PDF": total_pdf,
            "Total itens extraídos": total_extraido,
            "Diferença": diferenca,
            "Alerta": alerta,
        })

    if not registros:
        cols = [
            "Status", "Número do pedido", "Data emissão", "Código loja PDF",
            "Itens esperados no PDF", "Itens extraídos", "Total PDF",
            "Total itens extraídos", "Diferença", "Alerta",
        ]
        texto_bruto = str(texto_pdf or "")
        if texto_bruto.strip():
            if texto_pdf_parece_codificado(texto_bruto):
                alerta = "PDF com texto codificado/incompatível: a extração veio com códigos (cid:...). Gere/baixe novamente o PDF do pedido ou use outro arquivo exportado pelo sistema."
            else:
                alerta = "Nenhum pedido de compras foi reconhecido no arquivo. Confirme se o PDF enviado é realmente um pedido TOTVS/Consinco."
            return pd.DataFrame([["CRÍTICO", "", "", "", 0, 0, 0.0, 0.0, 0.0, alerta]], columns=cols)
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(registros)

def padronizar_lojas(base: pd.DataFrame, depara_lojas: pd.DataFrame) -> pd.DataFrame:
    base = base.copy()
    lojas = preparar_depara_lojas(depara_lojas)
    lojas["_key"] = lojas["Código PDF"].map(normalizar)
    mapa_nome = dict(zip(lojas["_key"], lojas["Nome da loja"].fillna("")))
    mapa_coluna = dict(zip(lojas["_key"], lojas["Coluna da grade"].fillna("")))
    mapa_preco_ref = dict(zip(lojas["_key"], lojas["Usar preço referência"].fillna("")))
    base["_loja_key"] = base["Código loja PDF"].map(normalizar)
    base["Nome da loja"] = base["_loja_key"].map(mapa_nome).fillna("")
    base["Coluna da grade"] = base["_loja_key"].map(mapa_coluna).fillna("")
    base["Usar preço referência"] = base["_loja_key"].map(mapa_preco_ref).fillna("")
    base.drop(columns=["_loja_key"], inplace=True)
    return base

def padronizar_produtos(base: pd.DataFrame, depara_produtos: pd.DataFrame) -> pd.DataFrame:
    base = base.copy()
    produtos = depara_produtos.copy()
    produtos.columns = [str(c).strip() for c in produtos.columns]
    for col in ["Nome do produto no PDF", "Nome oficial na grade", "Unidade"]:
        if col not in produtos.columns:
            produtos[col] = ""
    produtos["_padrao_norm"] = produtos["Nome do produto no PDF"].map(normalizar)
    padroes = produtos["_padrao_norm"].dropna().tolist()
    mapa = {
        row["_padrao_norm"]: (row["Nome oficial na grade"], row.get("Unidade", ""))
        for _, row in produtos.iterrows()
        if row.get("_padrao_norm", "")
    }

    oficiais, unidades, scores, metodos = [], [], [], []
    for produto in base["Produto original"].fillna(""):
        p_norm = normalizar(produto)
        achou = None
        score = 0
        metodo = "SEM CADASTRO"

        for padrao in padroes:
            if padrao and (padrao in p_norm or p_norm in padrao):
                achou = padrao
                score = 100
                metodo = "DE/PARA"
                break

        if achou is None and process is not None and padroes:
            candidato = process.extractOne(p_norm, padroes, scorer=fuzz.token_set_ratio)
            if candidato and candidato[1] >= 82:
                achou = candidato[0]
                score = int(candidato[1])
                metodo = "FUZZY"

        if achou:
            oficial, unidade = mapa.get(achou, (produto, ""))
            oficiais.append(str(oficial).upper())
            unidades.append(str(unidade).upper())
            scores.append(score)
            metodos.append(metodo)
        else:
            oficiais.append(str(produto).upper())
            unidades.append("")
            scores.append(0)
            metodos.append("SEM CADASTRO")

    base["Produto padronizado"] = oficiais
    base["Unidade"] = unidades
    base["Score produto"] = scores
    base["Método padronização"] = metodos
    return base

def extrair_base(texto_pdf: str, depara_lojas: pd.DataFrame, depara_produtos: pd.DataFrame) -> pd.DataFrame:
    registros: List[Dict] = []
    pedidos = dividir_pedidos(texto_pdf)
    for numero_pedido, bloco in pedidos:
        loja = extrair_loja(bloco)
        total = extrair_total_pedido(bloco)
        data_emissao = extrair_data_emissao(bloco)
        linhas = extrair_linhas_produtos(bloco)
        for item in linhas:
            registros.append({
                "Número do pedido": numero_pedido,
                "Código loja PDF": loja,
                "Data emissão": data_emissao,
                "Total do pedido PDF": total,
                **item,
            })

    base = pd.DataFrame(registros)
    if base.empty:
        return base
    base = padronizar_lojas(base, depara_lojas)
    base = padronizar_produtos(base, depara_produtos)
    base["Valor calculado"] = base["Quantidade"] * base["Preço unitário"]
    base["Diferença item"] = base["Valor do item"] - base["Valor calculado"]
    ordem = [
        "Número do pedido", "Data emissão", "Código loja PDF", "Nome da loja", "Coluna da grade", "Usar preço referência",
        "Código produto PDF", "Produto original", "Produto padronizado", "Unidade", "Embalagem",
        "Quantidade", "Preço unitário", "Valor do item", "Valor calculado", "Diferença item",
        "Total do pedido PDF", "Método padronização", "Score produto", "Linha original PDF",
    ]
    return base[ordem]

def obter_base_preco_referencia(base: pd.DataFrame) -> pd.DataFrame:
    """Filtra linhas das lojas marcadas como referência de preço."""
    if base.empty or "Usar preço referência" not in base.columns:
        return pd.DataFrame(columns=base.columns)
    return base[base["Usar preço referência"].apply(eh_sim) & base["Preço unitário"].gt(0)].copy()

def gerar_validacoes(base: pd.DataFrame, controle_extracao: pd.DataFrame = None) -> pd.DataFrame:
    cols = ["Severidade", "Tipo", "Número do pedido", "Código loja PDF", "Produto", "Detalhe", "Valor"]
    val = []

    if controle_extracao is not None and not controle_extracao.empty:
        for _, row in controle_extracao[controle_extracao["Status"].isin(["CRÍTICO", "ATENÇÃO"])].iterrows():
            val.append([
                row["Status"],
                "Controle de extração",
                row["Número do pedido"],
                row["Código loja PDF"],
                "",
                row["Alerta"],
                f"Esperado: {row['Itens esperados no PDF']} | Extraído: {row['Itens extraídos']} | Dif.: R$ {row['Diferença']:.2f}",
            ])

    if base.empty:
        if not val:
            val.append(["CRÍTICO", "PDF sem itens", "", "", "", "Nenhuma linha de produto foi extraída do PDF.", ""])
        return pd.DataFrame(val, columns=cols)


    for _, row in base[base["Código loja PDF"].fillna("").eq("")].iterrows():
        val.append(["CRÍTICO", "Loja não identificada no PDF", row["Número do pedido"], "", "", "O sistema não conseguiu localizar o código da loja no bloco do pedido.", ""])

    for _, row in base[base["Coluna da grade"].fillna("").eq("")].iterrows():
        val.append(["CRÍTICO", "Loja sem DE/PARA", row["Número do pedido"], row["Código loja PDF"], "", "Cadastre o código da loja na aba DE_PARA_LOJAS.", row["Código loja PDF"]])

    for _, row in base[base["Método padronização"].eq("SEM CADASTRO")].iterrows():
        val.append(["CRÍTICO", "Produto sem cadastro", row["Número do pedido"], row["Código loja PDF"], row["Produto original"], "Cadastre o produto na aba DE_PARA_PRODUTOS.", row["Produto original"]])

    for _, row in base[base["Preço unitário"].fillna(0).le(0)].iterrows():
        val.append(["CRÍTICO", "Preço zerado", row["Número do pedido"], row["Código loja PDF"], row["Produto original"], "Preço unitário igual a zero.", row["Preço unitário"]])

    total_zero = base.groupby(["Número do pedido", "Código loja PDF"], dropna=False)["Total do pedido PDF"].max().reset_index()
    for _, row in total_zero[total_zero["Total do pedido PDF"].fillna(0).le(0)].iterrows():
        val.append(["CRÍTICO", "Total do pedido não identificado", row["Número do pedido"], row["Código loja PDF"], "", "O sistema não conseguiu localizar o total do pedido no PDF. Sem esse total, não dá para garantir que todos os itens foram puxados.", row["Total do pedido PDF"]])

    dup = base.groupby(["Número do pedido", "Código loja PDF"]).size().reset_index(name="Itens")
    pedidos_duplicados = dup[dup.duplicated(["Número do pedido"], keep=False)]
    for _, row in pedidos_duplicados.iterrows():
        val.append(["CRÍTICO", "Pedido duplicado", row["Número do pedido"], row["Código loja PDF"], "", "Mesmo número de pedido apareceu em mais de uma loja/bloco.", row["Itens"]])

    resumo_total = base.groupby(["Número do pedido", "Código loja PDF"], dropna=False).agg(
        Total_PDF=("Total do pedido PDF", "max"),
        Total_Calculado=("Valor do item", "sum"),
    ).reset_index()
    resumo_total["Diferença"] = resumo_total["Total_PDF"] - resumo_total["Total_Calculado"]
    for _, row in resumo_total[resumo_total["Diferença"].abs().gt(0.10)].iterrows():
        val.append(["CRÍTICO", "Total divergente", row["Número do pedido"], row["Código loja PDF"], "", f"Total PDF {row['Total_PDF']:.2f} x soma itens {row['Total_Calculado']:.2f}.", row["Diferença"]])

    for _, row in base[(base["Método padronização"].eq("FUZZY")) & (base["Score produto"].lt(92))].iterrows():
        val.append(["ATENÇÃO", "Produto com nome divergente", row["Número do pedido"], row["Código loja PDF"], row["Produto original"], f"Produto padronizado por similaridade baixa: {row['Score produto']}%.", row["Produto padronizado"]])

    # Validação de preço: se houver loja marcada como referência, ela manda no preço da NOTA FINAL.
    # Assim, divergências em outras lojas são ignoradas para não travar a rotina.
    base_preco_ref = obter_base_preco_referencia(base)
    existe_preco_ref = not base_preco_ref.empty
    if existe_preco_ref:
        precos_ref = base_preco_ref.groupby("Produto padronizado")["Preço unitário"].nunique().reset_index(name="Qtd preços referência")
        for _, row in precos_ref[precos_ref["Qtd preços referência"].gt(1)].iterrows():
            detalhes = base_preco_ref[base_preco_ref["Produto padronizado"].eq(row["Produto padronizado"])][["Código loja PDF", "Preço unitário"]].drop_duplicates()
            detalhe_txt = "; ".join(f"{r['Código loja PDF']}: R$ {r['Preço unitário']:.2f}" for _, r in detalhes.iterrows())
            val.append(["ATENÇÃO", "Preço referência divergente", "", "", row["Produto padronizado"], "Há mais de uma loja marcada como referência com preços diferentes para o mesmo produto.", detalhe_txt])
    else:
        precos = base[base["Preço unitário"].gt(0)].groupby("Produto padronizado")["Preço unitário"].nunique().reset_index(name="Qtd preços")
        for _, row in precos[precos["Qtd preços"].gt(1)].iterrows():
            detalhes = base[base["Produto padronizado"].eq(row["Produto padronizado"])][["Código loja PDF", "Preço unitário"]].drop_duplicates()
            detalhe_txt = "; ".join(f"{r['Código loja PDF']}: R$ {r['Preço unitário']:.2f}" for _, r in detalhes.iterrows())
            val.append(["ATENÇÃO", "Produto com preços diferentes", "", "", row["Produto padronizado"], "Conferir se a diferença de preço é correta ou marque uma loja referência de preço no DE/PARA Lojas.", detalhe_txt])

    if not val:
        val.append(["OK", "Sem inconsistência crítica", "", "", "", "Base validada sem alertas relevantes.", ""])
    return pd.DataFrame(val, columns=cols)

def gerar_grade(base: pd.DataFrame, grade_cols: List[str]) -> pd.DataFrame:
    if base.empty:
        return pd.DataFrame(columns=["Produto"] + grade_cols + ["TOTAL", "PREÇO"])
    base_ok = base.copy()
    base_ok["Coluna da grade"] = base_ok["Coluna da grade"].fillna("")
    # Mantém itens sem loja/produto na base, mas a grade só soma colunas conhecidas.
    pivo = pd.pivot_table(
        base_ok[base_ok["Coluna da grade"].isin(grade_cols)],
        index="Produto padronizado",
        columns="Coluna da grade",
        values="Quantidade",
        aggfunc="sum",
        fill_value=0,
    )
    for col in grade_cols:
        if col not in pivo.columns:
            pivo[col] = 0
    pivo = pivo[grade_cols]
    pivo["TOTAL"] = pivo.sum(axis=1)

    # Regra do preço: prioriza os preços de lojas normais. O preço da loja de referência
    # só é utilizado se o produto não tiver preço em nenhuma das lojas normais.
    base_normal = base_ok[~base_ok["Usar preço referência"].apply(eh_sim) & base_ok["Preço unitário"].gt(0)]
    base_ref = base_ok[base_ok["Usar preço referência"].apply(eh_sim) & base_ok["Preço unitário"].gt(0)]

    precos_normais = base_normal.groupby("Produto padronizado")["Preço unitário"].first()
    precos_ref = base_ref.groupby("Produto padronizado")["Preço unitário"].first()

    # Une as séries priorizando precos_normais e usando precos_ref como fallback para itens ausentes nas normais
    precos_final = precos_normais.combine_first(precos_ref)
    pivo["PREÇO"] = pivo.index.map(precos_final).fillna(0)
    pivo = pivo.reset_index().rename(columns={"Produto padronizado": "Produto"})
    pivo = pivo.sort_values("Produto").reset_index(drop=True)
    return pivo

def gerar_resumo_pedidos(base: pd.DataFrame) -> pd.DataFrame:
    if base.empty:
        return pd.DataFrame()
    resumo = base.groupby(["Número do pedido", "Código loja PDF", "Nome da loja", "Coluna da grade"], dropna=False).agg(
        Itens=("Produto original", "count"),
        Quantidade_Total=("Quantidade", "sum"),
        Total_PDF=("Total do pedido PDF", "max"),
        Total_Itens=("Valor do item", "sum"),
    ).reset_index()
    resumo["Diferença"] = resumo["Total_PDF"] - resumo["Total_Itens"]
    return resumo

def gerar_pendencias_depara(base: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Monta sugestões de cadastro para lojas e produtos que ainda não estão no DE/PARA."""
    if base.empty:
        return pd.DataFrame(columns=["Código PDF", "Nome da loja", "Coluna da grade"]), pd.DataFrame(columns=["Nome do produto no PDF", "Nome oficial na grade", "Unidade"])

    lojas_pend = base[base["Coluna da grade"].fillna("").eq("")][["Código loja PDF"]].drop_duplicates().copy()
    if lojas_pend.empty:
        lojas_pend = pd.DataFrame(columns=["Código PDF", "Nome da loja", "Coluna da grade"])
    else:
        lojas_pend = lojas_pend.rename(columns={"Código loja PDF": "Código PDF"})
        lojas_pend["Nome da loja"] = ""
        lojas_pend["Coluna da grade"] = ""
        lojas_pend = lojas_pend[["Código PDF", "Nome da loja", "Coluna da grade"]]

    prod_pend = base[base["Método padronização"].eq("SEM CADASTRO")][["Produto original", "Embalagem"]].drop_duplicates().copy()
    if prod_pend.empty:
        prod_pend = pd.DataFrame(columns=["Nome do produto no PDF", "Nome oficial na grade", "Unidade"])
    else:
        prod_pend = prod_pend.rename(columns={"Produto original": "Nome do produto no PDF", "Embalagem": "Unidade"})
        prod_pend["Nome oficial na grade"] = prod_pend["Nome do produto no PDF"]
        prod_pend = prod_pend[["Nome do produto no PDF", "Nome oficial na grade", "Unidade"]]
    return lojas_pend.reset_index(drop=True), prod_pend.reset_index(drop=True)

