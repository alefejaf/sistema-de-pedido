"""Constantes de clientes e persistencia da configuracao DE/PARA por cliente."""
import io
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import streamlit as st

from .utils import eh_sim, normalizar


APP_NAME = "Gerador Automático de Grade Multi-Cliente"

GRADE_COLS_PADRAO = [
    "P.PARK", "AGUA.C", "S.SEB", "SOB", "ARAP", "ITA", "PLAN", "AGUA.L",
    "BRAZ", "SANT-M", "ESTRU", "SAMB", "BRASI", "ADE", "SOB II", "GAM",
    "SOL.NAC", "VIPIRES", "REC", "VIA-P", "CNB12", "SANT", "T-CENTRO",
    "CEI", "T.SUL",
]

CLIENTES = {
    "ultrabox": {
        "nome": "ULTRABOX",
        "icone": "🟦",
        "subtitulo": "Grade padrão Ultrabox / TOTVS",
        "descricao": "Use esta página para PDFs das lojas Ultrabox. Mantém a ordem operacional atual das 25 colunas.",
        "grade_cols": GRADE_COLS_PADRAO,
    },
    "bigbox": {
        "nome": "BIGBOX",
        "icone": "🟨",
        "subtitulo": "Grade padrão Big Box / TOTVS",
        "descricao": "Use esta página para pedidos Big Box. Configuração de lojas e produtos separada da Ultrabox.",
        "grade_cols": ["T-CENTRO", "CNB12", "SANT", "REC", "VIA-P", "CEI", "T.SUL"],
    },
    "costa": {
        "nome": "COSTA",
        "icone": "🟩",
        "subtitulo": "Grade padrão Costa / TOTVS",
        "descricao": "Use esta página para o cliente Costa. Cadastre aqui o DE/PARA próprio de lojas e produtos.",
        "grade_cols": ["TAG", "S.MARIA", "ADE", "VALP", "TAQ", "UNIEURO", "LUZ"],
    },
    "fort": {
        "nome": "FORT",
        "icone": "🟥",
        "subtitulo": "Grade padrão Fort / TOTVS",
        "descricao": "Use esta página para o cliente Fort. Cadastre aqui o DE/PARA próprio de lojas e produtos.",
        "grade_cols": ["F66-VALP", "F75-CEI", "F87-PLAN", "F138-TAG", "F175-CEI", "F775-REC"],
    },
}

def obter_cliente(cliente_id: str) -> Dict:
    """Retorna metadados do cliente selecionado."""
    return CLIENTES.get(cliente_id, CLIENTES["ultrabox"])

def slug_cliente(cliente_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(cliente_id).lower()).strip("_") or "cliente"

# Caminho absoluto relativo à raiz do projeto (pasta que contém o app.py), não
# ao diretório de execução nem à pasta deste módulo: evita criar/perder a pasta
# configs/ quando o app é iniciado de outro lugar ou quando este arquivo se move
# dentro do pacote.
CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"

# Mesma lógica de caminho absoluto do CONFIG_DIR acima, para não depender do
# diretório de execução.
BACKUP_CONFIG_DIR = Path(__file__).resolve().parent.parent / "backups_config"
MAX_BACKUPS_POR_CLIENTE = 10

def criar_config_padrao() -> Tuple[pd.DataFrame, pd.DataFrame]:
    lojas = pd.DataFrame([
        # Códigos observados no PDF TOTVS e aliases usuais
        ["ULT01-PLANDF", "ULTRABOX PLANALTINA", "PLAN", ""],
        ["ULT01-PLAN", "ULTRABOX PLANALTINA", "PLAN", ""],
        ["ULT02-GAMA", "ULTRABOX GAMA", "GAM", ""],
        ["ULT03-COL", "ULTRABOX COLORADO SOBRADINHO", "SOB", ""],
        ["ULT04-SSEB", "ULTRABOX SAO SEBASTIAO", "S.SEB", ""],
        ["ULT05-PLJK", "ULTRABOX POLO JK", "SANT-M", ""],
        ["ULT06-SOB", "ULTRABOX SOBRADINHO", "SOB", ""],
        ["ULT07-ADE", "ULTRABOX AGUAS CLARAS ADE", "ADE", ""],
        ["ULT08-ARAP", "ULTRABOX ARAPOANGA", "ARAP", ""],
        ["ULT09-ESTRUT", "ULTRABOX ESTRUTURAL", "ESTRU", ""],
        ["ULT10-ESTR", "ULTRABOX ESTRUTURAL", "ESTRU", ""],
        ["ULT10-BRAZ", "ULTRABOX BRAZLANDIA", "BRAZ", ""],
        ["ULT18-BRAZL", "ULTRABOX BRAZLANDIA", "BRAZ", ""],
        ["ULT11-ITAPOA", "ULTRABOX ITAPOA", "ITA", ""],
        ["ULT12-SOBII", "ULTRABOX SOBRADINHO II", "SOB II", ""],
        ["ULT12-SAOSEB", "ULTRABOX SAO SEBASTIAO", "S.SEB", ""],
        ["ULT13-AGLIND", "ULTRABOX AGUAS LINDAS", "AGUA.L", ""],
        ["ULT13-RECEMA", "ULTRABOX RECANTO DAS EMAS", "REC", ""],
        ["ULT14-SOLNA", "ULTRABOX SOL NASCENTE", "SOL.NAC", ""],
        ["ULT14-AGUASL", "ULTRABOX AGUAS LINDAS", "AGUA.L", ""],
        ["ULT15-SOLNA", "ULTRABOX SOL NASCENTE", "SOL.NAC", ""],
        ["ULT16-PPARK", "ULTRABOX PARANOA PARK", "P.PARK", ""],
        ["ULT16-PRPARK", "ULTRABOX PARANOA PARK", "P.PARK", ""],
        ["ULT17-SAMAMB", "ULTRABOX SAMAMBAIA SUL", "SAMB", ""],
        ["ULT18-REC", "ULTRABOX RECANTO DAS EMAS", "REC", ""],
        ["ULT19-VIAPARK", "ULTRABOX VIA-PARK", "VIA-P", ""],
        ["ULT20-VIAP", "ULTRABOX VIA-PARK", "VIA-P", ""],
        ["BIG20-TAGC1", "BIG BOX TAGUATINGA CENTRO", "T-CENTRO", ""],
        ["BIG21-CNB12", "BIG BOX CNB12", "CNB12", ""],
        ["ULT21-CNB12", "BIG BOX CNB12", "CNB12", ""],
        ["BIG22-SANT", "BIG BOX SANTA MARIA", "SANT", ""],
        ["ULT22-SANT", "ULTRABOX SANTA MARIA", "SANT", ""],
        ["ULT23-SMARIA", "ULTRABOX SANTA MARIA", "SANT", ""],
        ["ULT23-AGUAC", "ULTRABOX AGUAS CLARAS", "AGUA.C", ""],
        ["ULT24-PBRASI", "ULTRABOX BRASILINHA", "BRASI", "SIM"],
        ["BB-VIPIRES", "BIG BOX VICENTE PIRES", "VIPIRES", ""],
        ["ULT25-PLANGO", "ULTRABOX PLANALTINA GO", "PLAN", ""],
    ], columns=["Código PDF", "Nome da loja", "Coluna da grade", "Usar preço referência"])

    produtos = pd.DataFrame([
        ["AMEIXA 500G", "AMEIXA 500G", "UN"],
        ["AMEIXA IMPORTA", "AMEIXA IMPORTADA KG", "KG"],
        ["BROCOLIS AME", "BROCOLIS AMERICANO", "UN"],
        ["CAQUI RAMA", "CAQUI RAMA FORTE 500G", "UN"],
        ["KIWI 600G", "KIWI 600G", "UN"],
        ["KIWI KG", "KIWI KG", "KG"],
        ["KIWI SUNGOLD", "KIWI SUNGOLD ZESPRI 320G", "UN"],
        ["LARANJA BAHIA", "LARANJA BAHIA KG", "KG"],
        ["LIMA DA PERSIA", "LIMA DA PERSIA KG", "KG"],
        ["MACA FUJI", "MACA FUJI KG", "KG"],
        ["MACA GALA", "MACA GALA KG", "KG"],
        ["MACA RED", "MACA RED KG", "KG"],
        ["MACA VERDE", "MACA VERDE KG", "KG"],
        ["MACAS PACOTE", "MACAS PACOTE 1KG", "UN"],
        ["MELAO AMAREL", "MELAO AMARELO KG", "KG"],
        ["MELAO REI", "MELAO REI KG", "KG"],
        ["MELAO SAPO", "MELAO SAPO KG", "KG"],
        ["PEPINO JAPO", "PEPINO JAPONES KG", "KG"],
        ["PERA WILLIANS", "PERA WILLIANS KG", "KG"],
        ["PIMENTAO AMARELO KG", "PIMENTAO AMARELO KG", "KG"],
        ["PIMENTAO AMA", "PIMENTAO AMARELO KG", "KG"],
        ["PIMENTAO VERMELHO KG", "PIMENTAO VERMELHO KG", "KG"],
        ["UVA CRINSON", "UVA CRIMSON 500G", "UN"],
        ["UVA JUBILEE", "UVA JUBILEE 500G", "UN"],
        ["UVA NIAGARA", "UVA NIAGARA 500G", "UN"],
        ["UVA THOMPSON", "UVA THOMPSON 500G", "UN"],
        ["UVA VITORIA", "UVA VITORIA 500G", "UN"],
        ["UVA VITO", "UVA VITORIA 500G", "UN"],
        ["LIMAO SICIL", "LIMAO SICILIANO KG", "KG"],
        ["PIMENTAO VER", "PIMENTAO VERMELHO KG", "KG"],
        ["SALSAO", "SALSAO UND", "UN"],
        ["UVA BENITAKA", "UVA BENITAKA 500G", "UN"],
        ["MELAO GALIA", "MELAO GALIA KG", "KG"],
        ["PESSEGO IMPO", "PESSEGO IMPORTADO KG", "KG"],
        ["PINHA KG", "PINHA KG", "KG"],
        # Produtos observados nos modelos Costa/Fort. Mantém como sugestão inicial; o usuário pode editar por cliente.
        ["CAQUI RAMA FORTE 500G", "CAQUI RAMA FORTE 500G", "UN"],
        ["CAQUI 500G RAMA FORTE", "CAQUI RAMA FORTE 500G", "UN"],
        ["KIWI GREEN 600G", "KIWI GREEN 600G", "UN"],
        ["LARANJA LIMA", "LARANJA LIMA", "UN"],
        ["MACA GALA 1KG", "MACA GALA 1KG", "UN"],
        ["MACA MEU LANCHINHO 1KG", "MACA MEU LANCHINHO 1KG", "UN"],
        ["MACA NAC KG", "MACA NACIONAL KG", "KG"],
        ["MAMAO PAPAIA 1.5KG", "MAMAO PAPAIA 1.5KG", "UN"],
        ["MELAO AMARELO KG", "MELAO AMARELO KG", "KG"],
        ["MELANCIA BABY KG", "MELANCIA BABY KG", "KG"],
        ["MORANGO 250G", "MORANGO 250G", "UN"],
        ["PERA ROCHA 500G", "PERA ROCHA 500G", "UN"],
        ["PIMENTA 60G BICO DOCE", "PIMENTA BICO DOCE 60G", "UN"],
        ["PIMENTA 60G DEDO DE MOCA", "PIMENTA DEDO DE MOCA 60G", "UN"],
        ["PIMENTA 60G MALAGUETA", "PIMENTA MALAGUETA 60G", "UN"],
        ["TANGERINA 500G", "TANGERINA 500G", "UN"],
        ["TOMATE 180G SWEET GRAPE", "TOMATE SWEET GRAPE 180G", "UN"],
        ["UVA BCA LANCHINHO 500G S/SEMENTE", "UVA BRANCA LANCHINHO 500G S/SEMENTE", "UN"],
        ["UVA PTA LANCHINHO 500G S/SEMENTE", "UVA PRETA LANCHINHO 500G S/SEMENTE", "UN"],
        ["UVA PTA NIAGARA NAT 500G C/SEMENTE", "UVA NIAGARA 500G C/SEMENTE", "UN"],
        ["UVA BLACK 500G", "UVA BLACK 500G", "UN"],
        ["CPRA ALHO GRANEL KG", "ALHO GRANEL KG", "KG"],
        ["GENGIBRE KG", "GENGIBRE KG", "KG"],
    ], columns=["Nome do produto no PDF", "Nome oficial na grade", "Unidade"])
    return lojas, produtos

def criar_config_padrao_cliente(cliente_id: str = "ultrabox") -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Cria configurações iniciais separadas por cliente.

    A lógica de leitura do PDF é a mesma para todos. O que muda por cliente é
    o DE/PARA de lojas, a ordem das colunas e, quando necessário, o DE/PARA
    de produtos. O usuário pode editar tudo na aba CONFIGURAÇÕES e baixar um
    arquivo próprio para cada cliente.
    """
    lojas_base, produtos_base = criar_config_padrao()
    cid = slug_cliente(cliente_id)

    if cid == "ultrabox":
        # Mantém o padrão operacional atual. Deixa também códigos Big conhecidos,
        # pois alguns PDFs podem vir misturados no mesmo lote.
        return lojas_base.copy(), produtos_base.copy()

    if cid == "bigbox":
        codigos = {"BIG20-TAGC1", "BIG21-CNB12", "BIG22-SANT", "BB-VIPIRES"}
        aliases = {"ULT21-CNB12", "ULT22-SANT"}
        lojas = lojas_base[lojas_base["Código PDF"].astype(str).str.upper().isin(codigos | aliases)].copy()
        if lojas.empty:
            lojas = pd.DataFrame(columns=["Código PDF", "Nome da loja", "Coluna da grade", "Usar preço referência"])
        return lojas, produtos_base.copy()

    if cid == "costa":
        # Códigos extraídos do cabeçalho: COSTA MULTICANAL S/A LOJA <NOME>.
        lojas = pd.DataFrame([
            ["COSTA-TAGUATINGA", "COSTA TAGUATINGA", "TAG", ""],
            ["COSTA-SANTA-MARIA", "COSTA SANTA MARIA", "S.MARIA", ""],
            ["COSTA-ADE", "COSTA ADE", "ADE", ""],
            ["COSTA-VALPARAISO", "COSTA VALPARAISO", "VALP", ""],
            ["COSTA-TAQUARI", "COSTA TAQUARI", "TAQ", ""],
            ["COSTA-UNIEURO", "COSTA UNIEURO", "UNIEURO", ""],
            ["COSTA-LUZIANIA", "COSTA LUZIANIA", "LUZ", ""],
        ], columns=["Código PDF", "Nome da loja", "Coluna da grade", "Usar preço referência"])
        return lojas, produtos_base.copy()

    if cid == "fort":
        # Códigos extraídos do cabeçalho: DF-FORT ATACAD <NÚMERO> <NOME>.
        lojas = pd.DataFrame([
            ["FORT66-VALPARAISO", "FORT 66 VALPARAISO", "F66-VALP", ""],
            ["FORT75-CEILANDIA", "FORT 75 CEILANDIA", "F75-CEI", ""],
            ["FORT87-PLANALTINA", "FORT 87 PLANALTINA", "F87-PLAN", ""],
            ["FORT138-TAGUATINGA", "FORT 138 TAGUATINGA", "F138-TAG", ""],
            ["FORT175-CEILANDIA", "FORT 175 CEILANDIA", "F175-CEI", ""],
            ["FORT775-RECANT-EMAS", "FORT 775 RECANTO DAS EMAS", "F775-REC", ""],
        ], columns=["Código PDF", "Nome da loja", "Coluna da grade", "Usar preço referência"])
        return lojas, produtos_base.copy()

    return lojas_base.copy(), produtos_base.copy()

@st.cache_data(show_spinner=False)
def ler_config_padrao_cache(cliente_id: str = "ultrabox"):
    return criar_config_padrao_cliente(cliente_id)

def preparar_depara_lojas(df: pd.DataFrame) -> pd.DataFrame:
    """Garante colunas mínimas do DE/PARA de lojas para edição no site."""
    colunas = ["Código PDF", "Nome da loja", "Coluna da grade", "Usar preço referência"]
    if df is None or df.empty:
        df = pd.DataFrame(columns=colunas)
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    tinha_coluna_preco_ref = "Usar preço referência" in df.columns
    for col in colunas:
        if col not in df.columns:
            df[col] = ""
    df = df[colunas]
    df = df.fillna("")
    if not tinha_coluna_preco_ref:
        df.loc[df["Código PDF"].map(normalizar).eq("ULT24 PBRASI"), "Usar preço referência"] = "SIM"
    df["Usar preço referência"] = df["Usar preço referência"].apply(lambda x: "SIM" if eh_sim(x) else "")
    return df

def preparar_depara_produtos(df: pd.DataFrame) -> pd.DataFrame:
    """Garante colunas mínimas do DE/PARA de produtos para edição no site."""
    if df is None or df.empty:
        df = pd.DataFrame(columns=["Nome do produto no PDF", "Nome oficial na grade", "Unidade"])
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    for col in ["Nome do produto no PDF", "Nome oficial na grade", "Unidade"]:
        if col not in df.columns:
            df[col] = ""
    df = df[["Nome do produto no PDF", "Nome oficial na grade", "Unidade"]]
    df = df.fillna("")
    return df

def criar_config_grade_padrao(cliente_id: str = "ultrabox") -> pd.DataFrame:
    """Configuração padrão da ordem/visibilidade das lojas na NOTA FINAL por cliente."""
    grade_cols = obter_cliente(cliente_id).get("grade_cols", GRADE_COLS_PADRAO)
    return pd.DataFrame({
        "Posição": list(range(1, len(grade_cols) + 1)),
        "Coluna da grade": grade_cols,
        "Mostrar": [True] * len(grade_cols),
    })

def preparar_config_grade(df: pd.DataFrame, cliente_id: str = "ultrabox") -> pd.DataFrame:
    """Garante config de ordem/visibilidade das colunas da nota final.

    A configuração é dinâmica: o usuário pode adicionar, ocultar ou remover lojas.
    Quando não houver configuração, o sistema usa o padrão operacional do cliente.
    """
    if df is None or df.empty:
        df = criar_config_grade_padrao(cliente_id)
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    for col in ["Posição", "Coluna da grade", "Mostrar"]:
        if col not in df.columns:
            if col == "Posição":
                df[col] = range(1, len(df) + 1)
            elif col == "Mostrar":
                df[col] = True
            else:
                df[col] = ""
    df = df[["Posição", "Coluna da grade", "Mostrar"]].fillna("")
    df["Posição"] = pd.to_numeric(df["Posição"], errors="coerce")
    df["Mostrar"] = df["Mostrar"].apply(lambda x: True if x is True or eh_sim(x) else False)
    df["Coluna da grade"] = df["Coluna da grade"].astype(str).str.strip().str.upper()
    df = df[df["Coluna da grade"].ne("")].copy()
    if df["Posição"].isna().any():
        max_pos = int(df["Posição"].dropna().max()) if not df["Posição"].dropna().empty else 0
        for idx in df[df["Posição"].isna()].index:
            max_pos += 1
            df.at[idx, "Posição"] = max_pos
    df = df.drop_duplicates(subset=["Coluna da grade"], keep="first")
    return df.sort_values(["Posição", "Coluna da grade"]).reset_index(drop=True)

def incluir_colunas_lojas_na_config(config_grade: pd.DataFrame, depara_lojas: pd.DataFrame, cliente_id: str = "ultrabox") -> pd.DataFrame:
    """Inclui automaticamente na CONFIG_GRADE as colunas criadas no DE/PARA Lojas.

    Assim, para adicionar uma nova loja, basta cadastrar o código PDF e a nova
    coluna no DE/PARA Lojas; ela aparece na NOTA FINAL. Para ocultar/excluir da
    visualização, desmarque Mostrar na CONFIG_GRADE.
    """
    cfg = preparar_config_grade(config_grade, cliente_id)
    lojas = preparar_depara_lojas(depara_lojas)
    if lojas.empty:
        return cfg
    existentes = set(cfg["Coluna da grade"].astype(str).str.upper())
    novas = []
    max_pos = int(cfg["Posição"].max()) if not cfg.empty else 0
    for col in lojas["Coluna da grade"].dropna().astype(str).str.strip().str.upper().unique():
        if col and col not in existentes:
            max_pos += 1
            novas.append({"Posição": max_pos, "Coluna da grade": col, "Mostrar": True})
            existentes.add(col)
    if novas:
        cfg = pd.concat([cfg, pd.DataFrame(novas)], ignore_index=True)
    return preparar_config_grade(cfg, cliente_id)

def obter_colunas_grade(config_grade: pd.DataFrame, cliente_id: str = "ultrabox") -> List[str]:
    """Retorna a lista de colunas visíveis da NOTA FINAL, respeitando ordem e ocultação."""
    cfg = preparar_config_grade(config_grade, cliente_id)
    cols = cfg[cfg["Mostrar"].eq(True)]["Coluna da grade"].astype(str).tolist()
    return cols if cols else obter_cliente(cliente_id).get("grade_cols", GRADE_COLS_PADRAO).copy()

def remover_linhas_vazias_config(lojas: pd.DataFrame, produtos: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Remove linhas completamente vazias antes de usar os DE/PARA."""
    lojas = preparar_depara_lojas(lojas)
    produtos = preparar_depara_produtos(produtos)
    lojas = lojas[lojas[["Código PDF", "Nome da loja", "Coluna da grade", "Usar preço referência"]].astype(str).apply(lambda r: any(x.strip() for x in r), axis=1)].reset_index(drop=True)
    produtos = produtos[produtos[["Nome do produto no PDF", "Nome oficial na grade", "Unidade"]].astype(str).apply(lambda r: any(x.strip() for x in r), axis=1)].reset_index(drop=True)
    return lojas, produtos

def gerar_excel_config(lojas: pd.DataFrame, produtos: pd.DataFrame, config_grade: pd.DataFrame = None, cliente_nome: str = "") -> bytes:
    """Gera um arquivo Excel somente com as configurações DE/PARA editadas no site."""
    lojas, produtos = remover_linhas_vazias_config(lojas, produtos)
    config_grade = preparar_config_grade(config_grade)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        lojas.to_excel(writer, sheet_name="DE_PARA_LOJAS", index=False)
        produtos.to_excel(writer, sheet_name="DE_PARA_PRODUTOS", index=False)
        config_grade.to_excel(writer, sheet_name="CONFIG_GRADE", index=False)
        pd.DataFrame([
            [APP_NAME],
            [f"Cliente: {cliente_nome}" if cliente_nome else "Cliente não informado"],
            ["Arquivo de configuração DE/PARA."],
            ["Edite as lojas e produtos no próprio site ou nesta planilha e faça upload novamente."],
            ["Coluna da grade deve usar exatamente os nomes da nota final: P.PARK, AGUA.C, SOB, ARAP etc."],
            ["Use 'Usar preço referência' = SIM na loja que deve mandar o preço oficial da NOTA FINAL."],
            ["Na aba CONFIG_GRADE você pode ocultar lojas e mudar a posição das colunas da NOTA FINAL."],
        ]).to_excel(writer, sheet_name="LEIA-ME", index=False, header=False)

        workbook = writer.book
        fmt_header = workbook.add_format({"bold": True, "font_color": "white", "bg_color": "#1F4E78", "border": 1, "align": "center"})
        fmt_text = workbook.add_format({"border": 1})
        for sheet_name, df in [("DE_PARA_LOJAS", lojas), ("DE_PARA_PRODUTOS", produtos), ("CONFIG_GRADE", config_grade)]:
            ws = writer.sheets[sheet_name]
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, max(len(df), 1), max(len(df.columns) - 1, 0))
            for col_idx, col_name in enumerate(df.columns):
                ws.write(0, col_idx, col_name, fmt_header)
                width = min(max(len(str(col_name)) + 8, 18), 42)
                if len(df) > 0:
                    width = min(max(df[col_name].astype(str).map(len).max() + 3, width), 48)
                ws.set_column(col_idx, col_idx, width, fmt_text)
        ws = writer.sheets["LEIA-ME"]
        ws.set_column(0, 0, 120)
    return output.getvalue()

def caminho_config_cliente(cliente_id: str) -> Path:
    """Caminho local onde a configuração persistente do cliente fica salva."""
    return CONFIG_DIR / f"config_{slug_cliente(cliente_id)}.xlsx"

def carregar_config_excel(arquivo, cliente_id: str = "ultrabox") -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Lê um arquivo de configuração Excel, aceitando planilhas antigas sem CONFIG_GRADE."""
    lojas = pd.read_excel(arquivo, sheet_name="DE_PARA_LOJAS")
    produtos = pd.read_excel(arquivo, sheet_name="DE_PARA_PRODUTOS")
    try:
        config_grade = pd.read_excel(arquivo, sheet_name="CONFIG_GRADE")
    except Exception:
        config_grade = criar_config_grade_padrao(cliente_id)
    return preparar_depara_lojas(lojas), preparar_depara_produtos(produtos), preparar_config_grade(config_grade, cliente_id)

def existe_config_salva_cliente(cliente_id: str) -> bool:
    """Indica se já existe configuração salva para o cliente no computador."""
    return caminho_config_cliente(cliente_id).exists()

def carregar_config_salva_cliente(cliente_id: str = "ultrabox") -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Carrega a configuração persistente do cliente, quando existir."""
    return carregar_config_excel(caminho_config_cliente(cliente_id), cliente_id)

def _fazer_backup_config(cliente_id: str) -> None:
    """Copia o config atual do cliente para backups_config/ antes de ser
    sobrescrito, com nome cliente+data+hora. Mantém só os
    MAX_BACKUPS_POR_CLIENTE backups mais recentes desse cliente — não mexe
    no arquivo de config em si, só faz a cópia de segurança."""
    path_atual = caminho_config_cliente(cliente_id)
    if not path_atual.exists():
        return  # nada para fazer backup na primeira vez que o cliente salva

    BACKUP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    slug = slug_cliente(cliente_id)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = BACKUP_CONFIG_DIR / f"config_{slug}_{timestamp}.xlsx"
    shutil.copy2(path_atual, destino)

    backups_cliente = sorted(BACKUP_CONFIG_DIR.glob(f"config_{slug}_*.xlsx"), reverse=True)
    for backup_antigo in backups_cliente[MAX_BACKUPS_POR_CLIENTE:]:
        backup_antigo.unlink(missing_ok=True)


def salvar_config_cliente(cliente_id: str, lojas: pd.DataFrame, produtos: pd.DataFrame, config_grade: pd.DataFrame) -> Path:
    """Salva automaticamente a configuração editada no próprio computador.

    Cada cliente tem um arquivo independente em configs/config_<cliente>.xlsx.
    Isso permite fechar o sistema e abrir depois sem perder DE/PARA de lojas,
    DE/PARA de produtos e ordem/visibilidade da NOTA FINAL. Antes de
    sobrescrever, guarda uma cópia de backup do arquivo anterior (ver
    _fazer_backup_config).
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _fazer_backup_config(cliente_id)
    cliente_nome = obter_cliente(cliente_id).get("nome", slug_cliente(cliente_id).upper())
    lojas, produtos = remover_linhas_vazias_config(lojas, produtos)
    config_grade = incluir_colunas_lojas_na_config(config_grade, lojas, cliente_id)
    path = caminho_config_cliente(cliente_id)
    path.write_bytes(gerar_excel_config(lojas, produtos, config_grade, cliente_nome))
    return path

def limpar_estado_editores(cliente_slug: str):
    """Remove o estado dos editores para forçar recarregamento após salvar/mesclar pendências."""
    for key in [
        f"editor_depara_lojas_{cliente_slug}",
        f"editor_config_grade_{cliente_slug}",
        f"editor_depara_produtos_{cliente_slug}",
        f"editor_pend_lojas_{cliente_slug}",
        f"editor_pend_produtos_{cliente_slug}",
    ]:
        st.session_state.pop(key, None)

def mesclar_depara_lojas(lojas_atual: pd.DataFrame, lojas_novas: pd.DataFrame) -> pd.DataFrame:
    """Adiciona/atualiza lojas pendentes no cadastro, evitando duplicidade por Código PDF."""
    atual = preparar_depara_lojas(lojas_atual)
    novas = preparar_depara_lojas(lojas_novas)
    novas = novas[novas["Código PDF"].astype(str).str.strip().ne("")].copy()
    if novas.empty:
        return atual
    combinado = pd.concat([atual, novas], ignore_index=True)
    combinado["_key"] = combinado["Código PDF"].map(normalizar)
    combinado = combinado[combinado["_key"].ne("")]
    combinado = combinado.drop_duplicates(subset=["_key"], keep="last").drop(columns=["_key"])
    return preparar_depara_lojas(combinado)

def mesclar_depara_produtos(produtos_atual: pd.DataFrame, produtos_novos: pd.DataFrame) -> pd.DataFrame:
    """Adiciona/atualiza produtos pendentes no cadastro, evitando duplicidade por nome do PDF."""
    atual = preparar_depara_produtos(produtos_atual)
    novos = preparar_depara_produtos(produtos_novos)
    novos = novos[novos["Nome do produto no PDF"].astype(str).str.strip().ne("")].copy()
    if novos.empty:
        return atual
    combinado = pd.concat([atual, novos], ignore_index=True)
    combinado["_key"] = combinado["Nome do produto no PDF"].map(normalizar)
    combinado = combinado[combinado["_key"].ne("")]
    combinado = combinado.drop_duplicates(subset=["_key"], keep="last").drop(columns=["_key"])
    return preparar_depara_produtos(combinado)

def carregar_config(upload_config, cliente_id: str = "ultrabox") -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Carrega configuração na seguinte prioridade:
    1) Arquivo enviado manualmente no upload;
    2) Configuração salva automaticamente para o cliente;
    3) Configuração padrão do sistema.
    """
    if upload_config is not None:
        try:
            return carregar_config_excel(upload_config, cliente_id)
        except Exception as exc:
            st.warning(f"Não consegui ler a configuração enviada. Usando configuração salva/padrão do cliente selecionado. Erro: {exc}")

    if existe_config_salva_cliente(cliente_id):
        try:
            return carregar_config_salva_cliente(cliente_id)
        except Exception as exc:
            st.warning(f"Não consegui ler a configuração salva deste cliente. Usando padrão inicial. Erro: {exc}")

    lojas, produtos = ler_config_padrao_cache(cliente_id)
    return preparar_depara_lojas(lojas), preparar_depara_produtos(produtos), criar_config_grade_padrao(cliente_id)
