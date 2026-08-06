# Como implantar — Gerador Automático de Grade Multi-Cliente v2.4

## Objetivo

Rodar um único sistema para vários clientes, sem misturar configurações de loja, produto e ordem da grade.

## Clientes disponíveis

- **ULTRABOX**
- **BIGBOX**
- **COSTA**
- **FORT**

Cada cliente tem uma página própria dentro do sistema.

## O que mudou na v1.9

Agora as configurações são persistentes. Quando o usuário edita:

- **DE/PARA Lojas**
- **DE/PARA Produtos**
- **Ordem e visibilidade da NOTA FINAL**
- **Lojas sem DE/PARA**
- **Produtos sem DE/PARA**

O sistema salva em arquivo próprio do cliente dentro da pasta `configs`.

Exemplo:

```text
configs/config_ultrabox.xlsx
configs/config_bigbox.xlsx
configs/config_costa.xlsx
configs/config_fort.xlsx
```

## Passo a passo

### 1. Parar a versão anterior

No CMD onde o sistema está rodando:

```cmd
CTRL + C
```

### 2. Baixar e extrair a nova versão

Extraia o ZIP da versão 2.3 em uma nova pasta.

### 3. Entrar na pasta do sistema

```cmd
cd caminho\da\pasta\gerador_grade_bigbox_ultrabox_v2_3
```

### 4. Ativar o ambiente virtual

Se já existir `venv`:

```cmd
venv\Scripts\activate
```

Se não existir:

```cmd
python -m venv venv
venv\Scripts\activate
```

### 5. Instalar dependências

```cmd
pip install -r requirements.txt
```

### 6. Configurar o acesso (login via Google Sheets) — só na primeira implantação desta versão

O login agora é feito por uma planilha Google Sheets (aba `usuarios`), não
mais direto no `secrets.toml`. Passo a passo:

1. Crie uma planilha Google Sheets com duas abas:
   - `usuarios`: colunas `usuario | nome | senha_hash | salt | perfil | ativo`
   - `logs`: colunas `data_hora | usuario | nome | evento | status | detalhe`
2. No [Google Cloud Console](https://console.cloud.google.com/), crie/use um
   projeto, ative as APIs **Google Sheets API** e **Google Drive API**, e
   crie uma **Service Account** com uma **chave JSON**.
3. Compartilhe a planilha com o e-mail da Service Account (`client_email`
   do JSON) dando permissão de **Editor**.
4. Copie o modelo de secrets e preencha com os dados da chave JSON e o ID
   da planilha:
   ```cmd
   copy .streamlit\secrets.toml.example .streamlit\secrets.toml
   ```
   Edite `.streamlit\secrets.toml` preenchendo `[gcp_service_account]` com
   os campos do JSON baixado e `[google_sheets] sheet_id` com o ID da
   planilha (veja os comentários no próprio arquivo de exemplo).
5. Gere o hash+salt de cada senha:
   ```cmd
   python scripts\gerar_hash_senha.py
   ```
   Cole os valores impressos (`salt` e `senha_hash`) nas colunas
   correspondentes da aba `usuarios`, junto com `usuario`, `nome`, `perfil`
   (`admin`, `usuario` ou `visualizador`) e `ativo` (`SIM` para liberar o
   acesso).
6. **Conta master (opcional)**: existe uma seção `[master]` em
   `secrets.toml` com um login que funciona mesmo se a planilha do Google
   Sheets estiver fora do ar — serve para o administrador nunca ficar
   trancado para fora do sistema. Para trocar a senha dessa conta, gere um
   novo `salt`/`senha_hash` com `python scripts\gerar_hash_senha.py` e cole
   em `[master]` no `secrets.toml`.

`.streamlit\secrets.toml` é local e não deve ser enviado ao Git — no
Streamlit Community Cloud, cole o mesmo conteúdo no painel do app em
**Settings → Secrets** em vez de subir o arquivo.

### 7. Rodar o sistema

```cmd
streamlit run app.py
```

Na primeira tela, faça login com um dos usuários configurados no passo 6.

## Operação recomendada

### Primeiro uso por cliente

1. Abra o cliente na tela inicial.
2. Suba de 1 até 5 PDFs reais de pedido.
3. Confira a aba **VALIDAÇÕES**.
4. Se houver lojas ou produtos sem cadastro, vá em **CONFIGURAÇÕES**.
5. No final da aba, edite as pendências e clique em **Adicionar e salvar**.
6. Rode o PDF novamente.
7. Use a NOTA FINAL apenas quando as validações críticas estiverem resolvidas.

### Próximos usos

1. Abra o mesmo cliente.
2. Suba de 1 até 5 PDFs.
3. O sistema já carrega automaticamente a configuração salva daquele cliente.
4. Gere a NOTA FINAL.

## Backup da configuração

Mesmo com salvamento automático, é recomendado baixar a configuração atualizada de tempos em tempos pelo botão:

**Baixar configuração atualizada**

Esse arquivo serve para backup ou para levar a configuração para outro computador.

## Segurança operacional

Antes de usar a NOTA FINAL, conferir:

- **Críticos = 0**
- **Controle de extração = OK**
- **Diferença entre Total PDF e Total extraído = R$ 0,00**
- Nenhuma loja sem DE/PARA
- Nenhum produto sem cadastro

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


## Atualização v2.3 — operação com até 5 PDFs

Na lateral do sistema, o campo **PDF de pedido TOTVS/Consinco** agora permite selecionar vários arquivos.

Uso recomendado:

1. Selecione o cliente correto na tela inicial.
2. Suba de **1 até 5 PDFs** do mesmo cliente.
3. Confira **Pedidos lidos**, **Linhas extraídas**, **VALIDAÇÕES** e **CONTROLE_EXTRACAO**.
4. Se aparecer alerta de arquivo incompatível, remova o PDF errado e suba novamente apenas os PDFs de pedido.
5. Baixe a **NOTA FINAL**.

Observação: se forem enviados mais de 5 PDFs, o sistema processará somente os 5 primeiros para manter a performance.

## Atualização v2.4 — acesso restrito (login), perfis e log

- O sistema agora pede login antes de liberar qualquer tela (veja o passo 6
  do passo a passo acima para configurar usuários/senhas).
- Perfis: **admin** e **usuario** têm acesso completo; **visualizador**
  processa PDF mas não edita/salva DE/PARA em CONFIGURAÇÕES nem baixa
  arquivos.
- Toda tentativa de login (certa ou errada), usuário inativo e todo logout
  ficam registrados na aba `logs` da planilha Google Sheets (data/hora,
  usuário, nome, evento, status, detalhe) — a senha nunca é gravada, nem no
  log nem em nenhum outro lugar (só o hash com salt fica na aba `usuarios`).
- Se a planilha do Google Sheets estiver inacessível (sem configurar os
  Secrets, sem permissão de acesso, fora do ar), o sistema mostra um aviso
  pedindo para tentar novamente em vez de liberar o uso sem login.

## Segurança das credenciais

- **`secrets.toml` nunca deve subir para o GitHub.** O arquivo real (com
  chaves e senhas de verdade) fica só na sua máquina e no painel do
  Streamlit Cloud — o `.gitignore` já bloqueia o commit dele. Só o
  `.streamlit/secrets.toml.example` (com valores fictícios) vai para o
  repositório.
- **No Streamlit Community Cloud**, cole o conteúdo do `secrets.toml` (com
  os valores reais) em **App → Settings → Secrets**. Não existe upload de
  arquivo — é colar o texto TOML direto nesse painel.
- **Compartilhamento da planilha:** o Google Sheets só é acessível pelo
  sistema depois que você compartilhar a planilha (botão "Compartilhar")
  com o e-mail da Service Account (`client_email` da chave JSON) dando
  permissão de **Editor**. Sem isso, o gspread recebe erro de permissão e
  o login fica bloqueado.
- **O arquivo `.json` da Service Account não deve ficar guardado dentro do
  projeto** (nem em pastas soltas no computador). Depois de copiar os
  campos dele para `secrets.toml`, apague o `.json` baixado — ele não é
  necessário depois disso, e qualquer `.json` seria bloqueado pelo
  `.gitignore` mesmo assim, mas é mais seguro não deixá-lo por aí.
