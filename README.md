# Gerador Automático de Grade Multi-Cliente — v2.4

Sistema em Python + Streamlit para transformar PDF TOTVS em NOTA FINAL/grade Excel.

## Novo na v2.4 — acesso restrito (login via Google Sheets) e perfis

- O sistema agora exige **login** antes de liberar qualquer tela.
- Usuários ficam cadastrados numa planilha **Google Sheets** (aba
  `usuarios`); as credenciais do Google (conta de serviço) e o ID da
  planilha ficam em `st.secrets` (nunca no código nem no Git) — veja a
  seção **Configurando o acesso (login)** abaixo.
- Três perfis de acesso:
  - **admin** e **usuario**: acesso completo (processar PDF, baixar Excel,
    editar/salvar DE/PARA em CONFIGURAÇÕES).
  - **visualizador**: processa PDF e visualiza os dados, mas a aba
    CONFIGURAÇÕES fica somente leitura (sem salvar/restaurar/adicionar
    pendência) e os botões de download de Excel/diagnóstico ficam
    bloqueados.
- Botão **Sair** na barra lateral encerra a sessão.
- Todo login/tentativa de login/usuário inativo/logout fica registrado na
  aba `logs` da planilha (data/hora, usuário, nome, evento, status,
  detalhe) — a senha nunca é gravada no log.

## Novo na v2.3

- Permite subir **de 1 até 5 PDFs de pedido** no mesmo processamento.
- Junta todos os pedidos encontrados nos PDFs enviados e gera uma única **NOTA FINAL**.
- Mantém o design da versão anterior; a alteração foi somente na lógica/codificação.
- Adiciona validação para arquivo incompatível ou texto não reconhecido, incluindo casos em que o PDF vem com caracteres codificados.
- Mantém os modelos de extração para **Ultrabox, Bigbox, Costa e Fort**.

## Base da v1.9

- As alterações feitas em **CONFIGURAÇÕES** agora ficam **salvas automaticamente** no computador.
- Cada cliente tem um arquivo próprio de configuração:
  - `configs/config_ultrabox.xlsx`
  - `configs/config_bigbox.xlsx`
  - `configs/config_costa.xlsx`
  - `configs/config_fort.xlsx`
- O sistema carrega automaticamente a configuração salva do cliente na próxima abertura.
- As telas de **Lojas sem DE/PARA** e **Produtos sem DE/PARA** agora permitem editar a pendência e clicar em **Adicionar e salvar**.
- O cadastro salvo fica separado por cliente, evitando misturar loja/produto de Ultrabox, Bigbox, Costa e Fort.

## Como usar

1. Rode o sistema e faça **login** com seu usuário/senha.
2. Na tela inicial, escolha o cliente: **ULTRABOX**, **BIGBOX**, **COSTA** ou **FORT**.
3. Suba o PDF TOTVS daquele cliente.
4. Ajuste a aba **CONFIGURAÇÕES**, se necessário (perfil visualizador só consulta).
5. O sistema salva automaticamente o DE/PARA daquele cliente (exceto para o perfil visualizador).
6. Se aparecer **Loja sem DE/PARA** ou **Produto sem DE/PARA**, edite a pendência no final da aba **CONFIGURAÇÕES** e clique em **Adicionar e salvar**.
7. Confira **VALIDAÇÕES** e **CONTROLE_EXTRACAO**.
8. Baixe a **NOTA FINAL** para digitação do pedido (perfis admin/usuario).

## Como rodar no Windows

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Antes do primeiro uso, configure o acesso — veja a seção abaixo.

## Configurando o acesso (login via Google Sheets)

O sistema lê os usuários de uma planilha Google Sheets; as credenciais do
Google e o ID da planilha ficam em `st.secrets`, nunca no código. Passo a
passo completo em `COMO_IMPLANTAR.md` (seção 6); resumo:

1. Crie a planilha com as abas `usuarios` e `logs` (colunas descritas em
   `.streamlit/secrets.toml.example`).
2. Crie uma Service Account no Google Cloud, ative as APIs Sheets e Drive,
   compartilhe a planilha com o `client_email` da conta como Editor.
3. Copie o modelo: `.streamlit/secrets.toml.example` → `.streamlit/secrets.toml`
   (esse arquivo é local/privado, já está no `.gitignore`, nunca vai para o Git)
   e preencha com os dados da chave JSON e o `sheet_id`.
4. Gere o salt+hash de cada senha:
   ```cmd
   python scripts/gerar_hash_senha.py
   ```
   Digite a senha (não aparece na tela) e cole os valores impressos nas
   colunas `salt` e `senha_hash` do usuário na aba `usuarios`, junto com
   `perfil` (`admin`, `usuario` ou `visualizador`) e `ativo` (`SIM`).
5. **No Streamlit Community Cloud**: não suba `secrets.toml` — cole o mesmo
   conteúdo (com os valores reais) no painel do app em **Settings → Secrets**.

Sem isso configurado (ou se a planilha ficar inacessível), o sistema mostra
uma mensagem clara pedindo para tentar novamente, em vez de liberar o uso
sem login — a não ser que a conta master (seção `[master]` em
`secrets.toml`) esteja configurada, já que ela é independente do Google
Sheets e continua entrando mesmo com a planilha fora do ar.

## Arquivos

- `app.py`: ponto de entrada — tela inicial, abas e orquestração da UI Streamlit. Continua sendo o arquivo que você roda (`streamlit run app.py`); a lógica de negócio foi organizada em módulos dentro de `grade_app/` para ficar mais fácil de manter.
  - `grade_app/utils.py`: normalização de texto/número, sem depender de UI.
  - `grade_app/config.py`: clientes, DE/PARA e persistência de configuração por cliente.
  - `grade_app/parsing.py`: regex e heurísticas dos 4 layouts de PDF (Ultrabox/Bigbox/Costa/Fort).
  - `grade_app/pdf_text.py`: leitura de PDF (PyMuPDF/pdfplumber) e divisão em pedidos.
  - `grade_app/processing.py`: padronização, validações, controle de extração e geração da grade.
  - `grade_app/excel_export.py`: geração dos arquivos Excel (NOTA FINAL e relatório completo).
  - `grade_app/ui/`: telas Streamlit — `home.py` (tela inicial), `sidebar.py` (upload/opções), `styles.py` (CSS/paleta compartilhada) e `tabs/` (uma aba por arquivo: `nota_final.py`, `base_limpa.py`, `validacoes.py`, `configuracoes.py`).
  - `grade_app/auth.py`: login, hash de senha com salt (PBKDF2-HMAC-SHA256), perfis de acesso.
  - `grade_app/google_sheets.py`: conexão com o Google Sheets (gspread) — leitura de usuários e escrita de logs.
- `scripts/gerar_hash_senha.py`: gera o salt+hash de uma senha para colar na aba `usuarios` do Google Sheets.
- `.streamlit/secrets.toml.example`: modelo do arquivo de credenciais (o real, `secrets.toml`, não é commitado).
- `requirements.txt`: dependências.
- `config_padrao.xlsx`: configuração padrão inicial.
- `configs/`: pasta criada automaticamente para salvar configurações por cliente.
- `COMO_IMPLANTAR.md`: passo a passo de implantação.

## Observação importante

A partir da v1.9, não é obrigatório baixar e subir manualmente a configuração a cada uso. O botão de download continua disponível apenas como backup ou para enviar a configuração para outro computador.

## Atualização v2.2 — modelos Costa e Fort

Esta versão mantém o design da v2.1 e altera apenas a lógica de extração.

Melhorias:

- Aceita pedidos com número sem letra final, exemplo `19859544`.
- Junta páginas repetidas do mesmo pedido antes da validação.
- Identifica lojas Costa no padrão `COSTA MULTICANAL S/A LOJA <NOME>`.
- Identifica lojas Fort no padrão `DF-FORT ATACAD <NÚMERO> <NOME>`.
- Lê o layout horizontal/quebrado usado nos PDFs Costa/Fort.
- Captura complementos do produto em linhas seguintes, como `FORTE`, `500G`, `GRANEL KG`, `LANCHINHO 1KG`, `C/SEMENTE`.
- Mantém o controle de extração por pedido comparando total do PDF x total extraído.

Arquivos de configuração iniciais incluídos:

- `configs/config_costa.xlsx`
- `configs/config_fort.xlsx`
- `configs/config_bigbox.xlsx`
- `configs/config_ultrabox.xlsx`

Se você copiar configurações antigas por cima da pasta `configs`, confira se Costa e Fort continuam com os códigos novos de loja.


## Atualização v2.3 — upload múltiplo e proteção contra PDF incompatível

Esta versão mantém o visual/design da versão anterior e altera apenas a codificação.

Melhorias:

- Campo de PDF agora aceita **até 5 arquivos** por vez.
- O sistema concatena os textos extraídos e processa todos os pedidos encontrados.
- Se o usuário enviar mais de 5 PDFs, apenas os 5 primeiros serão processados para não deixar o sistema lento.
- Quando o PDF não é reconhecido como pedido, o sistema gera alerta crítico em **VALIDAÇÕES** em vez de falhar sem explicação.
- Quando o texto vier codificado/incompatível, o sistema acusa o problema no **CONTROLE_EXTRACAO**.
