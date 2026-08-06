"""Regex e heuristicas de parsing das linhas de produto dos 4 layouts TOTVS
(Ultrabox/Bigbox linha unica e quebrada, Costa/Fort layout horizontal)."""
import re
from typing import Dict, List, Tuple

from .utils import normalizar, br_numero_para_float


NUMERO_BR_RE = r"\d{1,3}(?:\.\d{3})*,\d{2}"

PRECO_4_RE = r"\d{1,5},\d{4}"

# Exemplo TOTVS com código: 1.404,0040[360255] 1.404,003,9000360,00KG 1MACA GAL
LINHA_PRODUTO_RE = re.compile(
    rf"(?P<valor_item>{NUMERO_BR_RE})\s*\d{{0,5}}\[(?P<cod_produto>\d+)\]\s*"
    rf"(?:(?P<valor_item_repetido>{NUMERO_BR_RE})\s*)?"
    rf"(?P<preco_unitario>{PRECO_4_RE})\s*"
    rf"(?P<quantidade>\d{{1,6}}(?:\.\d{{3}})*,\d{{2}})\s*"
    rf"(?P<embalagem>UN|UND|KG|CX|FD)\s*1\s*(?P<produto>.+)$",
    flags=re.I,
)

# Fallback para linhas raras sem [código], exemplo: 145,80145,8016,20009,00KG 1PINHA KG7966
LINHA_PRODUTO_SEM_COD_RE = re.compile(
    rf"(?P<valor_item>{NUMERO_BR_RE})\s*"
    rf"(?:(?P<valor_item_repetido>{NUMERO_BR_RE})\s*)?"
    rf"(?P<preco_unitario>{PRECO_4_RE})\s*"
    rf"(?P<quantidade>\d{{1,6}}(?:\.\d{{3}})*,\d{{2}})\s*"
    rf"(?P<embalagem>UN|UND|KG|CX|FD)\s*1\s*(?P<produto>.+)$",
    flags=re.I,
)

# Layout visual em linha única, comum em alguns pedidos Big Box:
# 7966 PINHA KG KG 1 6,00 16,2000 97,20 97,20
LINHA_PRODUTO_VISUAL_RE = re.compile(
    rf"^(?:(?P<cod_forn>\d+\[\d+\])\s+)?"
    rf"(?P<codigo_item_loja>\d{{3,8}})\s+"
    rf"(?P<produto>.+?)\s+"
    rf"(?P<embalagem>UN|UND|KG|CX|FD)\s*1\s+"
    rf"(?P<quantidade>{NUMERO_BR_RE})\s+"
    rf"(?P<preco_unitario>{PRECO_4_RE})\s+"
    rf"(?P<valor_item>{NUMERO_BR_RE})"
    rf"(?:\s+(?P<custo_bruto>{NUMERO_BR_RE}))?\s*$",
    flags=re.I,
)

# Layout horizontal Costa/Fort/Consinco/TOTVS:
# 17[569712] 0,00 CAQUI RAMA UN 1 50,00 4,5000 225,00 225,00 ...
# 635219 0,00 GENGIBRE KG - KG 1 14,00 6,5000 91,00 91,00 ...
# 50[379494] 0,00 31109 UVA PTA UN 1 20,00 8,7000 174,00 174,00 ...
LINHA_PRODUTO_HORIZONTAL_RE = re.compile(
    rf"^(?P<cod_forn>(?:\d+\[\d+\]|\d{{3,8}}))\s+"
    rf"(?P<qtd_canc>{NUMERO_BR_RE})\s+"
    rf"(?P<produto>.+?)\s+"
    rf"(?P<embalagem>UN|UND|KG|CX|FD)\s*1\s+"
    rf"(?P<quantidade>{NUMERO_BR_RE})\s+"
    rf"(?P<preco_unitario>{PRECO_4_RE})\s+"
    rf"(?P<valor_item>{NUMERO_BR_RE})\s+"
    rf"(?P<custo_bruto>{NUMERO_BR_RE})(?:\s+.*)?$",
    flags=re.I,
)

def normalizar_embalagem(embalagem: str) -> str:
    """Uniformiza a embalagem do item: 'UND' é tratado como sinônimo de 'UN'."""
    emb = str(embalagem or "").upper()
    return "UN" if emb == "UND" else emb


def montar_item_produto(codigo_produto, produto, embalagem, quantidade, preco_unitario, valor_item, linha_original) -> Dict:
    """Monta o dicionário de 1 item no formato comum às 5 estratégias de parsing.

    Centraliza a normalização de embalagem e a conversão de número BR -> float
    que antes se repetiam, quase idênticas, em cada estratégia.
    """
    return {
        "Código produto PDF": codigo_produto,
        "Produto original": produto,
        "Embalagem": normalizar_embalagem(embalagem),
        "Quantidade": br_numero_para_float(quantidade),
        "Preço unitário": br_numero_para_float(preco_unitario),
        "Valor do item": br_numero_para_float(valor_item),
        "Linha original PDF": linha_original,
    }


def produto_pdf_parece_valido(produto: str) -> bool:
    produto_norm = normalizar(produto)
    if not produto_norm or not re.search(r"[A-Z]", produto_norm):
        return False
    invalidos = [
        "EANS", "TOTAIS", "OBSERVACOES", "DADOS ADICIONAIS", "VALOR TOTAL DO PEDIDO",
        "ADVERTENCIA P RECEBIMENTO", "PRAZO PARA PAGAMENTO", "DATA DA EMISSAO",
        "PREVISAO DE ENTREGA", "PESO TOTAL PEDIDO", "VOLUME TOTAL PEDIDO",
    ]
    return not any(p in produto_norm for p in invalidos)

def linha_e_inicio_item_horizontal(linha: str):
    """Retorna match quando a linha é início de item no layout Costa/Fort."""
    linha_limpa = re.sub(r"\s+", " ", str(linha or "").strip())
    if not linha_limpa or linha_limpa.upper().startswith("EANS"):
        return None
    if "TOTAIS" in linha_limpa.upper() or "VALOR TOTAL DO PEDIDO" in linha_limpa.upper():
        return None
    return LINHA_PRODUTO_HORIZONTAL_RE.match(linha_limpa)

def limpar_fragmento_continuacao_produto(linha: str) -> str:
    """Limpa linhas de continuação do nome do produto no layout horizontal."""
    s = re.sub(r"\s+", " ", str(linha or "").strip().upper())
    if not s:
        return ""
    # Remove marcas/embalagens genéricas, mas preserva medidas e descrições.
    s = re.sub(r"\b(SILVESTRIN|SILVESTRE|SILVENTRIN|SUED|NATUA)\b", " ", s)
    s = re.sub(r"\b(PC|BDJ|BAND|BJA|UN|UND)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def linha_continuacao_produto_valida(linha: str) -> bool:
    """Decide se uma linha após o item deve entrar no nome do produto."""
    raw = re.sub(r"\s+", " ", str(linha or "").strip().upper())
    if not raw:
        return False
    if raw.startswith("EANS"):
        return False
    if re.fullmatch(r"\d{3,13}", raw):
        return False
    if re.fullmatch(NUMERO_BR_RE, raw) or re.fullmatch(PRECO_4_RE, raw):
        return False
    if raw.startswith("REF") or raw.startswith("--- PAGINA"):
        return False
    ruido = [
        "PEDIDO DE COMPRAS", "FORNECEDOR", "DADOS PARA FATURAMENTO", "R SOCIAL",
        "ENDERECO", "ENDEREÇO", "TELEFONE", "BAIRRO", "CIDADE", "CNPJ", "CEP",
        "INSCRICAO", "INSCRIÇÃO", "ENDERECO PARA", "ENDEREÇO PARA", "TRANSPORTADOR",
        "COD FORN", "SEQ PRODUTOS", "QTDE", "VALOR", "QTD CANC", "CUSTO", "DESC",
        "ADVERTENCIA", "ADVERTÊNCIA", "OBSERVACOES", "OBSERVAÇÕES", "PRAZO",
        "DATA DA EMISSAO", "DATA DA EMISSÃO", "PREVISAO", "PREVISÃO", "PESO TOTAL",
        "VOLUME TOTAL", "CONDIÇÃO", "CONDICAO", "JUSTIFICATIVA", "APROVACAO", "APROVAÇÃO",
        "TOTVS", "CONSINCO", "REL PED", "RELPED", "XML", "EMAIL", "E MAIL",
        "COSTA MULTICANAL", "SDB COMERCIO", "COMERCIO DE ALIMENTOS", "EMPREEND",
        "AGRO NEGOCIO", "AGRO NEGOCIOS", "LOJA ", "QUADRA", "RODOVIA", "AVENIDA",
        "BRASILIA", "GOIAS", "VALPARAISO", "LUZIANIA", "TAGUATINGA", "SETOR",
        "AREA", "CONJUNTO", "PARQUE", "NORTE", "SUL", "LTDA", "S/A",
        "CAUB", "GALPAO", "GARAGE", "RIACHO", "FUNDO", "INDUSTRIAL",
        "ECONOMICO", "AGUAS CLARAS", "SANTA MARIA", "RECANTO", "EMAS",
    ]
    if re.fullmatch(r"\d{5,}(?:/[A-Z])?", raw):
        return False
    if re.fullmatch(r"\(?\d{2}\)?\d{7,9}", raw.replace(" ", "")):
        return False
    raw_norm = normalizar(raw)
    if any(r in raw_norm for r in [normalizar(x) for x in ruido]):
        return False
    limpo = limpar_fragmento_continuacao_produto(raw)
    if not limpo:
        return False
    if re.fullmatch(r"[-_/.,]+", limpo):
        return False
    return bool(re.search(r"[A-Z]", limpo) or re.search(r"\d+(?:G|KG|ML|L)\b", limpo))

def montar_produto_horizontal(produto_linha: str, continuacoes: List[str]) -> str:
    """Monta nome mais completo do item horizontal, preservando descrição útil."""
    produto = re.sub(r"^\d{3,8}\s+", "", str(produto_linha or "").strip().upper())
    produto = re.sub(r"\s+-\s*$", "", produto).strip()
    partes = [produto]
    for linha in continuacoes:
        if linha_continuacao_produto_valida(linha):
            frag = limpar_fragmento_continuacao_produto(linha)
            if frag and normalizar(frag) not in {normalizar(p) for p in partes}:
                partes.append(frag)
    combinado = " ".join(partes)
    combinado = re.sub(r"\s+", " ", combinado).strip()
    return limpar_produto_original(combinado)

def obter_continuacoes_produto_ate_eans(linhas: List[str], inicio: int) -> Tuple[List[str], str]:
    """Coleta complemento do produto até EANs e retorna também código interno se houver."""
    continuacoes: List[str] = []
    codigo_item = ""
    j = inicio
    while j < len(linhas):
        prox = re.sub(r"\s+", " ", str(linhas[j] or "").strip())
        if not prox:
            j += 1
            continue
        if linha_e_inicio_item_horizontal(prox):
            break
        if prox.upper().startswith("EANS"):
            break
        # Proteção caso o PDF venha sem EANs entre itens.
        if (
            re.fullmatch(NUMERO_BR_RE, prox)
            and j + 4 < len(linhas)
            and re.fullmatch(NUMERO_BR_RE, linhas[j + 1])
            and re.fullmatch(PRECO_4_RE, linhas[j + 2])
            and re.fullmatch(NUMERO_BR_RE, linhas[j + 3])
        ):
            break
        if re.fullmatch(r"\d{3,13}", prox) and not codigo_item:
            codigo_item = prox
        if linha_continuacao_produto_valida(prox):
            continuacoes.append(prox)
        j += 1
    return continuacoes, codigo_item

def extrair_linhas_produtos_horizontal(linhas: List[str]) -> List[Dict]:
    """Extrai itens do layout horizontal usado nos PDFs Costa e Fort."""
    itens: List[Dict] = []
    for idx, linha in enumerate(linhas):
        m = linha_e_inicio_item_horizontal(linha)
        if not m:
            continue
        gd = m.groupdict()
        continuacoes = []
        j = idx + 1
        while j < len(linhas):
            prox = re.sub(r"\s+", " ", linhas[j].strip())
            if linha_e_inicio_item_horizontal(prox):
                break
            if prox.upper().startswith("EANS"):
                break
            # Continua atravessando cabeçalho de página quando o produto quebra a página.
            if linha_continuacao_produto_valida(prox):
                continuacoes.append(prox)
            j += 1

        produto = montar_produto_horizontal(gd["produto"], continuacoes)
        if not produto_pdf_parece_valido(produto):
            continue
        itens.append(montar_item_produto(
            gd.get("cod_forn") or "", produto, gd["embalagem"],
            gd["quantidade"], gd["preco_unitario"], gd["valor_item"],
            " | ".join([re.sub(r"\s+", " ", linha.strip())] + continuacoes[:6]),
        ))
    return itens

def contar_itens_horizontal_layout(bloco: str) -> int:
    linhas = [re.sub(r"\s+", " ", l.strip()) for l in str(bloco or "").splitlines() if l.strip()]
    return sum(1 for l in linhas if linha_e_inicio_item_horizontal(l))

def limpar_produto_original(produto: str) -> str:
    produto = produto.strip().upper()
    produto = re.sub(r"\s+", " ", produto)
    # Remove pedaços de código colados no final sem perder medidas úteis como 500G, 600G, 320G e 1KG.
    produto = re.sub(r"(500G|600G|320G|1KG|KG|UND|UN)\d{1,5}$", r"\1", produto)
    produto = re.sub(r"\bKG\d{1,5}$", "KG", produto)
    produto = re.sub(r"\bK\d{1,5}$", "KG", produto)
    produto = re.sub(r"\s*-?\s*REF:?\s*\d+.*$", "", produto)
    produto = re.sub(r"\s*-\s*$", "", produto)
    produto = re.sub(r"\s+", " ", produto).strip()
    return produto

def extrair_linhas_produtos(bloco: str) -> List[Dict]:
    """Extrai produtos do bloco do pedido TOTVS.

    Suporta dois layouts de texto extraído:
    - Linha única: valor + código + preço + quantidade + unidade + produto.
    - Multilinha: cada campo vem em uma linha separada, que é o caso do texto
      enviado no diagnóstico:
        300,00
        2[696349]
        300,00
        15,0000
        20,00
        UN  1
        AMEIXA 500G
        8523
        EANs: ...
    """
    linhas_extraidas: List[Dict] = []

    linhas = [re.sub(r"\s+", " ", l.strip()) for l in bloco.splitlines() if l.strip()]

    # 0) Layout horizontal Costa/Fort/Consinco: item na linha e descrição quebrando abaixo.
    linhas_extraidas.extend(extrair_linhas_produtos_horizontal(linhas))

    # 1) Tentativa para PDFs onde a tabela sai em uma única linha.
    for linha in bloco.splitlines():
        linha_limpa = re.sub(r"\s+", " ", linha.strip())
        if not linha_limpa:
            continue
        linha_upper = linha_limpa.upper()
        if linha_upper.startswith("EANS"):
            continue
        if "TOTAIS" in linha_upper or "VALOR TOTAL DO PEDIDO" in linha_upper:
            continue
        if not re.search(r"(UN|UND|KG|CX|FD)\s*1", linha_limpa, flags=re.I):
            continue

        # Layout visual esquerda->direita, inclusive item sem Cod Forn/Seq, ex.:
        # 7966 PINHA KG KG 1 6,00 16,2000 97,20 97,20
        match_visual = LINHA_PRODUTO_VISUAL_RE.search(linha_limpa)
        if match_visual and produto_pdf_parece_valido(match_visual.group("produto")):
            gd = match_visual.groupdict()
            linhas_extraidas.append(montar_item_produto(
                gd.get("codigo_item_loja") or gd.get("cod_forn") or "",
                limpar_produto_original(gd["produto"]), gd["embalagem"],
                gd["quantidade"], gd["preco_unitario"], gd["valor_item"], linha_limpa,
            ))
            continue

        match = LINHA_PRODUTO_RE.search(linha_limpa)
        if not match:
            match = LINHA_PRODUTO_SEM_COD_RE.search(linha_limpa)
        if not match:
            continue

        gd = match.groupdict()
        if not produto_pdf_parece_valido(gd["produto"]):
            continue
        linhas_extraidas.append(montar_item_produto(
            gd.get("cod_produto") or "", limpar_produto_original(gd["produto"]), gd["embalagem"],
            gd["quantidade"], gd["preco_unitario"], gd.get("valor_item_repetido") or gd["valor_item"], linha_limpa,
        ))

    # 2) Tentativa para o layout quebrado em várias linhas.
    seq_re = re.compile(r"^(?P<seq>\d+)\[(?P<cod>\d+)\]$")
    unidade_re = re.compile(r"^(?P<emb>UN|UND|KG|CX|FD)\s*1$", flags=re.I)

    i = 0
    while i <= len(linhas) - 7:
        l0, l1, l2, l3, l4, l5, l6 = linhas[i:i+7]
        m_seq = seq_re.fullmatch(l1)
        m_un = unidade_re.fullmatch(l5)

        if not (
            re.fullmatch(NUMERO_BR_RE, l0)
            and m_seq
            and re.fullmatch(NUMERO_BR_RE, l2)
            and re.fullmatch(PRECO_4_RE, l3)
            and re.fullmatch(NUMERO_BR_RE, l4)
            and m_un
        ):
            i += 1
            continue

        produto = l6.strip()

        # Evita capturar cabeçalho/rodapé como produto.
        if not produto_pdf_parece_valido(produto):
            i += 1
            continue

        # Produto costuma vir seguido pelo código interno e por complementos até EANs.
        continuacoes, codigo_item_loja = obter_continuacoes_produto_ate_eans(linhas, i + 7)

        produto_completo = montar_produto_horizontal(produto, continuacoes)
        linha_original = " | ".join(linhas[i:i+8] + continuacoes[:6])
        linhas_extraidas.append(montar_item_produto(
            codigo_item_loja or m_seq.group("cod"), produto_completo, m_un.group("emb"),
            l4, l3, l2, linha_original,
        ))
        i += 7

    # 3) Layout quebrado sem Cod Forn/Seq.
    # Caso real: o item PINHA KG pode vir assim, sem linha 17[600315]:
    # 97,20 / 97,20 / 16,2000 / 6,00 / KG 1 / PINHA KG / 7966
    i = 0
    while i <= len(linhas) - 6:
        l0, l1, l2, l3, l4, l5 = linhas[i:i+6]
        m_un = unidade_re.fullmatch(l4)
        if not (
            re.fullmatch(NUMERO_BR_RE, l0)
            and re.fullmatch(NUMERO_BR_RE, l1)
            and re.fullmatch(PRECO_4_RE, l2)
            and re.fullmatch(NUMERO_BR_RE, l3)
            and m_un
            and produto_pdf_parece_valido(l5)
        ):
            i += 1
            continue

        continuacoes, codigo_item_loja = obter_continuacoes_produto_ate_eans(linhas, i + 6)

        produto_completo = montar_produto_horizontal(l5, continuacoes)
        linha_original = " | ".join(linhas[i:i+7] + continuacoes[:6])
        linhas_extraidas.append(montar_item_produto(
            codigo_item_loja, produto_completo, m_un.group("emb"),
            l3, l2, l1, linha_original,
        ))
        i += 6

    # 4) Layout quebrado sem o segundo valor repetido:
    # 97,20 / 16,2000 / 6,00 / KG 1 / PINHA KG / 7966
    i = 0
    while i <= len(linhas) - 5:
        l0, l1, l2, l3, l4 = linhas[i:i+5]
        m_un = unidade_re.fullmatch(l3)
        if not (
            re.fullmatch(NUMERO_BR_RE, l0)
            and re.fullmatch(PRECO_4_RE, l1)
            and re.fullmatch(NUMERO_BR_RE, l2)
            and m_un
            and produto_pdf_parece_valido(l4)
        ):
            i += 1
            continue

        continuacoes, codigo_item_loja = obter_continuacoes_produto_ate_eans(linhas, i + 5)

        produto_completo = montar_produto_horizontal(l4, continuacoes)
        linha_original = " | ".join(linhas[i:i+6] + continuacoes[:6])
        linhas_extraidas.append(montar_item_produto(
            codigo_item_loja, produto_completo, m_un.group("emb"),
            l2, l1, l0, linha_original,
        ))
        i += 5

    # Remove duplicidades quando as duas estratégias capturam o mesmo item.
    dedup = []
    vistos = set()
    for item in linhas_extraidas:
        chave = (
            normalizar(item.get("Produto original", "")),
            item.get("Embalagem", ""),
            round(float(item.get("Quantidade", 0) or 0), 4),
            round(float(item.get("Preço unitário", 0) or 0), 4),
            round(float(item.get("Valor do item", 0) or 0), 4),
        )
        if chave not in vistos:
            vistos.add(chave)
            dedup.append(item)
    return dedup

def contar_indicios_produtos(texto: str) -> int:
    """Conta sinais de linhas de produto no layout TOTVS.

    O PDF do TOTVS pode sair de duas formas:
    1) Produto em uma linha: valor + código + preço + qtd + unidade + produto.
    2) Produto quebrado em várias linhas, como:
       300,00 / 2[696349] / 300,00 / 15,0000 / 20,00 / UN 1 / AMEIXA 500G.
    Essa contagem ajuda o sistema a escolher entre pdfplumber e PyMuPDF.
    """
    if not texto:
        return 0
    padrao_com_codigo = re.compile(r"\[\d{3,}\].{0,120}(?:UN|UND|KG|CX|FD)\s*1", flags=re.I | re.S)
    padrao_sem_codigo = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}\s*\d{1,5},\d{4}\s*\d{1,6}(?:\.\d{3})*,\d{2}\s*(?:UN|UND|KG|CX|FD)\s*1", flags=re.I | re.S)

    score_linha_unica = len(padrao_com_codigo.findall(texto)) + len(padrao_sem_codigo.findall(texto))

    linhas = [re.sub(r"\s+", " ", l.strip()) for l in texto.splitlines() if l.strip()]
    score_multilinha = 0
    seq_re = re.compile(r"^\d+\[\d+\]$")
    unidade_re = re.compile(r"^(?:UN|UND|KG|CX|FD)\s*1$", flags=re.I)
    for i in range(len(linhas) - 6):
        janela = linhas[i:i+7]
        if (re.fullmatch(NUMERO_BR_RE, janela[0]) and
            seq_re.fullmatch(janela[1]) and
            re.fullmatch(NUMERO_BR_RE, janela[2]) and
            re.fullmatch(PRECO_4_RE, janela[3]) and
            re.fullmatch(NUMERO_BR_RE, janela[4]) and
            unidade_re.fullmatch(janela[5])):
            score_multilinha += 1

    score_horizontal = 0
    try:
        score_horizontal = contar_itens_horizontal_layout(texto)
    except Exception:
        score_horizontal = 0

    return score_linha_unica + score_multilinha + score_horizontal

def contar_itens_indicios_bloco(bloco: str) -> int:
    """Conta quantos itens parecem existir no pedido antes da extração.

    Agora considera três sinais:
    1. Sequência/código do fornecedor: 17[600315]
    2. Linhas EANs: que aparecem abaixo de quase todo item
    3. Produtos sem código/seq no início, como PINHA KG, que podem sair sem 17[xxxx]

    Isso evita erro silencioso: se algum item não for capturado, a validação acusa
    diferença por quantidade esperada ou, no mínimo, por total do pedido.
    """
    if not bloco:
        return 0

    area = bloco
    m_ini = re.search(r"Valor\s+Unit\.\s*", bloco, flags=re.I)
    if m_ini:
        area = bloco[m_ini.end():]
    m_fim = re.search(r"\bTOTAIS\b", area, flags=re.I)
    if m_fim:
        area = area[:m_fim.start()]

    linhas = [re.sub(r"\s+", " ", l.strip()) for l in area.splitlines() if l.strip()]
    qtd_seq = sum(1 for l in linhas if re.fullmatch(r"\d+\[\d+\]", l))
    qtd_eans = sum(1 for l in linhas if l.upper().startswith("EANS:"))

    unidade_re = re.compile(r"^(?:UN|UND|KG|CX|FD)\s*1$", flags=re.I)
    produto_sem_seq = 0

    # Padrão quebrado sem Cod Forn/Seq:
    # 97,20 / 97,20 / 16,2000 / 6,00 / KG 1 / PINHA KG / 7966
    for i in range(len(linhas) - 5):
        if (
            re.fullmatch(NUMERO_BR_RE, linhas[i])
            and re.fullmatch(NUMERO_BR_RE, linhas[i + 1])
            and re.fullmatch(PRECO_4_RE, linhas[i + 2])
            and re.fullmatch(NUMERO_BR_RE, linhas[i + 3])
            and unidade_re.fullmatch(linhas[i + 4])
        ):
            produto = linhas[i + 5]
            produto_norm = normalizar(produto)
            if re.search(r"[A-Z]", produto_norm) and not produto_norm.startswith("EANS"):
                produto_sem_seq += 1

    # Padrão visual em linha única, da esquerda para direita:
    # 7966 PINHA KG KG 1 6,00 16,2000 97,20 97,20
    numero = NUMERO_BR_RE
    linha_visual_re = re.compile(
        rf"^(?:\d+\[\d+\]\s+)?\d{{3,8}}\s+.+?\s+(?:UN|UND|KG|CX|FD)\s*1\s+{numero}\s+{PRECO_4_RE}\s+{numero}",
        flags=re.I,
    )
    qtd_linha_visual = sum(1 for l in linhas if linha_visual_re.search(l))
    qtd_horizontal = contar_itens_horizontal_layout(area)

    return max(qtd_horizontal, qtd_seq, produto_sem_seq, qtd_eans, qtd_linha_visual)
