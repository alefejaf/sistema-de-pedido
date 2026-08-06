"""Leitura de PDF (PyMuPDF/pdfplumber), cache por conteudo do arquivo e
divisao do texto extraido em blocos de pedido."""
import os
import re
import tempfile
from typing import Dict, List, Tuple

import streamlit as st

from .utils import normalizar, br_numero_para_float
from .parsing import contar_indicios_produtos


def texto_pdf_parece_codificado(texto: str) -> bool:
    """Identifica extração ruim de PDF, quando o texto vem como (cid:0), (cid:1) etc.

    Isso costuma acontecer quando o PDF usa fonte/codificação interna que o extrator
    não consegue mapear para letras normais. Nesse caso o sistema não deve tentar
    montar grade silenciosamente; ele precisa avisar o usuário.
    """
    texto = str(texto or "")
    if not texto.strip():
        return False
    qtd_cid = len(re.findall(r"\(cid:\d+\)", texto))
    if qtd_cid >= 20:
        return True
    proporcao_cid = qtd_cid / max(len(texto.split()), 1)
    return qtd_cid >= 8 and proporcao_cid > 0.10

@st.cache_data(show_spinner=False)
def _extrair_texto_pdf_bytes(pdf_bytes: bytes, nome_arquivo: str) -> Dict:
    """Extrai o texto de 1 PDF a partir dos bytes (cacheável por conteúdo).

    Separado de extrair_texto_pdf de propósito: o Streamlit cacheia esta
    função pelo conteúdo do arquivo, então reabrir/editar as tabelas de
    CONFIGURAÇÕES não força reprocessar o(s) PDF(s) do zero a cada rerun.
    """
    candidatos: List[Tuple[str, str]] = []
    erros_motor: Dict[str, str] = {}
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        # Tentativa 1: PyMuPDF costuma manter melhor a sequência da tabela TOTVS.
        try:
            import fitz
            doc = fitz.open(tmp_path)
            texto_paginas = []
            for i, page in enumerate(doc, start=1):
                texto_paginas.append(f"\n--- PAGINA {i} ---\n{page.get_text('text') or ''}")
            candidatos.append(("PyMuPDF", "\n".join(texto_paginas)))
        except Exception as exc:
            erros_motor["PyMuPDF"] = str(exc)

        # Tentativa 2: pdfplumber, útil em outros layouts.
        try:
            import pdfplumber
            texto_paginas = []
            with pdfplumber.open(tmp_path) as pdf:
                for i, page in enumerate(pdf.pages, start=1):
                    texto = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
                    texto_paginas.append(f"\n--- PAGINA {i} ---\n{texto}")
            candidatos.append(("pdfplumber", "\n".join(texto_paginas)))
        except Exception as exc:
            erros_motor["pdfplumber"] = str(exc)
    finally:
        # Sempre limpa o arquivo temporário, mesmo se algum motor falhar.
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    if not candidatos:
        return {"ok": False, "arquivo": nome_arquivo, "erros_motor": erros_motor}

    # Escolhe o texto com mais sinais de linha de produto.
    candidatos_validos = []
    for nome, texto in candidatos:
        score = contar_indicios_produtos(texto)
        pedidos = len(re.findall(r"PEDIDO\s*DE\s*COMPRAS\s*\d+/?[A-Z]?", texto, flags=re.I))
        codificado = texto_pdf_parece_codificado(texto)
        # Penaliza texto codificado quando outro motor trouxe pedidos/itens legíveis.
        penalidade = 100000 if codificado and pedidos == 0 and score == 0 else 0
        candidatos_validos.append((score, pedidos, -penalidade, nome, texto, codificado))

    candidatos_validos.sort(key=lambda x: (x[0], x[1], x[2], len(x[4])), reverse=True)
    melhor_score, melhores_pedidos, _, melhor_nome, melhor_texto, melhor_codificado = candidatos_validos[0]

    return {
        "ok": True,
        "texto": melhor_texto,
        "arquivo": nome_arquivo,
        "motor_usado": melhor_nome,
        "indicios_produto": melhor_score,
        "pedidos_identificados_no_texto": melhores_pedidos,
        "texto_codificado_cid": bool(melhor_codificado),
        "tamanho_texto": len(melhor_texto),
        "erros_motor": erros_motor,
    }

def extrair_texto_pdf(uploaded_file) -> str:
    """Lê todas as páginas de 1 PDF e escolhe a extração com mais itens TOTVS.

    Em alguns PDFs, o pdfplumber lê o cabeçalho, mas quebra a tabela de itens.
    Por isso o sistema compara pdfplumber x PyMuPDF e usa o texto com maior
    quantidade de sinais de produto. A extração pesada fica cacheada por
    conteúdo do arquivo em _extrair_texto_pdf_bytes.
    """
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    data = uploaded_file.read()
    nome_arquivo = getattr(uploaded_file, "name", "pedido.pdf")

    resultado = _extrair_texto_pdf_bytes(data, nome_arquivo)

    if not resultado["ok"]:
        detalhe = "; ".join(f"{motor}: {erro}" for motor, erro in resultado["erros_motor"].items())
        msg = "Não consegui ler o PDF. Verifique se o arquivo não está digitalizado como imagem."
        if detalhe:
            msg += f" Detalhe técnico: {detalhe}"
        st.session_state["debug_pdf_parser"] = {"arquivo": nome_arquivo, "erros_motor": resultado["erros_motor"]}
        raise RuntimeError(msg)

    # Guarda informações para diagnóstico na tela.
    st.session_state["debug_pdf_parser"] = {
        "arquivo": resultado["arquivo"],
        "motor_usado": resultado["motor_usado"],
        "indicios_produto": resultado["indicios_produto"],
        "pedidos_identificados_no_texto": resultado["pedidos_identificados_no_texto"],
        "texto_codificado_cid": resultado["texto_codificado_cid"],
        "tamanho_texto": resultado["tamanho_texto"],
        "erros_motor": resultado["erros_motor"],
    }
    st.session_state["debug_texto_pdf"] = resultado["texto"][:20000]

    return resultado["texto"]

def extrair_texto_pdfs(uploaded_files) -> str:
    """Lê de 1 até 5 PDFs de pedido e concatena tudo em um único texto.

    O restante do sistema continua igual: dividir_pedidos() identifica todos os
    pedidos no texto combinado. Isso permite jogar vários PDFs do mesmo cliente
    no mesmo processamento sem mudar o layout visual do sistema.
    """
    if uploaded_files is None:
        return ""
    if not isinstance(uploaded_files, list):
        uploaded_files = [uploaded_files]

    arquivos = uploaded_files[:5]
    textos = []
    detalhes = []
    for idx, arquivo in enumerate(arquivos, start=1):
        nome_arquivo = getattr(arquivo, "name", f"pedido_{idx}.pdf")
        texto = extrair_texto_pdf(arquivo)
        debug = dict(st.session_state.get("debug_pdf_parser", {}))
        debug["arquivo"] = nome_arquivo
        debug["ordem_upload"] = idx
        detalhes.append(debug)
        textos.append(f"\n\n--- ARQUIVO PDF {idx}: {nome_arquivo} ---\n" + texto)

    texto_completo = "\n".join(textos)
    st.session_state["debug_pdf_parser"] = {
        "arquivos_lidos": len(arquivos),
        "limite_maximo_pdfs": 5,
        "pedidos_identificados_no_texto": len(re.findall(r"PEDIDO\s*DE\s*COMPRAS\s*\d+/?[A-Z]?", texto_completo, flags=re.I)),
        "indicios_produto": contar_indicios_produtos(texto_completo),
        "texto_codificado_cid": texto_pdf_parece_codificado(texto_completo),
        "detalhe_arquivos": detalhes,
        "tamanho_texto": len(texto_completo),
    }
    st.session_state["debug_texto_pdf"] = texto_completo[:30000]
    return texto_completo

def dividir_pedidos(texto: str) -> List[Tuple[str, str]]:
    """Divide o PDF em pedidos e junta páginas repetidas do mesmo pedido.

    Alguns clientes vêm com número no formato 440332/L, outros vêm apenas
    numérico, como 19859544. Em pedidos com mais de uma página, o cabeçalho
    repete o mesmo número; por isso o sistema junta blocos consecutivos iguais.
    """
    texto = texto.replace("\x00", " ")
    padrao = re.compile(r"PEDIDO\s+DE\s+COMPRAS\s+([0-9]+(?:/[A-Z])?)", flags=re.I)
    matches = list(padrao.finditer(texto))
    segmentos = []
    for i, match in enumerate(matches):
        inicio = match.start()
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(texto)
        segmentos.append((match.group(1).upper(), texto[inicio:fim]))

    pedidos: List[Tuple[str, str]] = []
    for numero, bloco in segmentos:
        if pedidos and pedidos[-1][0] == numero:
            pedidos[-1] = (numero, pedidos[-1][1] + "\n" + bloco)
        else:
            pedidos.append((numero, bloco))
    return pedidos

def montar_codigo_loja(prefixo: str, nome: str, numero: str = "") -> str:
    """Monta um código estável para lojas sem código ULT/BIG no PDF."""
    nome_norm = normalizar(nome).replace(" ", "-")
    prefixo = normalizar(prefixo).replace(" ", "")
    numero = re.sub(r"\D+", "", str(numero or ""))
    if numero:
        return f"{prefixo}{numero}-{nome_norm}".strip("-")
    return f"{prefixo}-{nome_norm}".strip("-")

def extrair_loja(bloco: str) -> str:
    # Códigos como ULT01-PLANDF, ULT08-ARAP, ULT15-SOLNA, BIG20-TAGC1.
    candidatos = re.findall(r"\b[A-Z]{2,5}\d{2,3}-[A-Z0-9]+(?:-[A-Z0-9]+)?\b", bloco.upper())
    candidatos = [c for c in candidatos if not c.startswith("CEP")]
    if candidatos:
        return candidatos[0]

    linhas = [re.sub(r"\s+", " ", l.strip().upper()) for l in str(bloco or "").splitlines() if l.strip()]

    # Cliente Costa: em PyMuPDF costuma vir em duas linhas:
    # COSTA MULTICANAL S/A / LOJA TAGUATINGA
    for idx, linha in enumerate(linhas):
        if "COSTA MULTICANAL" in linha:
            for prox in linhas[idx + 1: idx + 5]:
                m = re.search(r"\bLOJA\s+(?P<loja>[A-Z0-9 .\-/]+)$", prox)
                if m:
                    return montar_codigo_loja("COSTA", m.group("loja"))

    # Cliente Fort: em PyMuPDF costuma vir em uma linha:
    # DF-FORT ATACAD 66 VALPARAISO
    for linha in linhas[:40]:
        m = re.search(r"DF[-\s]*FORT\s+ATACAD\s+(?P<num>\d{1,4})\s+(?P<loja>[A-Z0-9 .\-/]+)$", linha)
        if m:
            return montar_codigo_loja("FORT", m.group("loja"), m.group("num"))

    texto = re.sub(r"\s+", " ", bloco.upper())

    # Fallback Costa quando o texto vier todo em uma linha.
    m = re.search(
        r"COSTA\s+MULTICANAL\s+S/A\s+LOJA\s+(?P<loja>.+?)(?:\s+R\.\s*SOCIAL|\s+R\s+SOCIAL|\s+SUED|\s+ENDERE[CÇ]O|\s+TELEFONE|\s+BAIRRO|\s+CIDADE|\s+CNPJ|$)",
        texto,
        flags=re.I,
    )
    if m:
        return montar_codigo_loja("COSTA", m.group("loja"))

    # Fallback Fort quando o texto vier todo em uma linha.
    m = re.search(
        r"DF[-\s]*FORT\s+ATACAD\s+(?P<num>\d{1,4})\s+(?P<loja>.+?)(?:\s+R\.\s*SOCIAL|\s+R\s+SOCIAL|\s+SUED|\s+ENDERE[CÇ]O|\s+TELEFONE|\s+BAIRRO|\s+CIDADE|\s+CNPJ|$)",
        texto,
        flags=re.I,
    )
    if m:
        return montar_codigo_loja("FORT", m.group("loja"), m.group("num"))

    return ""

def extrair_data_emissao(bloco: str) -> str:
    m = re.search(r"(\d{2}/\d{2}/\d{4})\s*Data\s+da\s+emiss", bloco, flags=re.I)
    if m:
        return m.group(1)
    datas = re.findall(r"\b\d{2}/\d{2}/\d{4}\b", bloco)
    return datas[0] if datas else ""

def extrair_total_pedido(bloco: str) -> float:
    """Extrai o total do pedido em diferentes ordens de texto do TOTVS.

    Dependendo do motor de PDF, o total pode sair como:
    - 2.496,70 Valor total do pedido
    - Valor total do pedido 2.496,70
    - Valor total do pedido / 2.496,70 na linha seguinte
    - linha TOTAIS com valores no rodapé da tabela
    """
    numero_re = r"\d{1,3}(?:\.\d{3})*,\d{2}"

    padroes = [
        rf"(?P<valor>{numero_re})\s*Valor\s+total\s+do\s+pedido",
        rf"Valor\s+total\s+do\s+pedido\s*(?P<valor>{numero_re})",
        rf"Valor\s+total\s+do\s+pedido\s*\n\s*(?P<valor>{numero_re})",
    ]
    for padrao in padroes:
        m = re.search(padrao, bloco, flags=re.I)
        if m:
            return br_numero_para_float(m.group("valor"))

    # Fallback: em alguns PDFs o rodapé da tabela traz algo como
    # 400,00 2.496,70 2.496,70 TOTAIS. Pega o maior valor próximo de TOTAIS.
    m = re.search(rf"((?:{numero_re}\s*){{2,5}})\s*TOTAIS", bloco, flags=re.I)
    if m:
        valores = [br_numero_para_float(x) for x in re.findall(numero_re, m.group(1))]
        if valores:
            return max(valores)

    m = re.search(rf"PEDIDO[^\n]*?(?P<valor>{numero_re})\s*Valor", bloco, flags=re.I)
    return br_numero_para_float(m.group("valor")) if m else 0.0
