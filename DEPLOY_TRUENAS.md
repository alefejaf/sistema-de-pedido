# Deploy no TrueNAS SCALE — Gerador Automático de Grade Multi-Cliente

Este guia documenta a implantação via Docker no seu TrueNAS SCALE (Docker/Apps),
acessado inicialmente só pela sua rede Tailscale. Ele **não substitui** a
versão que já roda no Streamlit Community Cloud — as duas podem coexistir,
apontando para a mesma planilha Google Sheets de login ou para planilhas
separadas, como você preferir.

Nada de código foi alterado para esta implantação: `app.py`, `grade_app/` e
`requirements.txt` são exatamente os mesmos usados no Community Cloud. Só
foram adicionados `Dockerfile`, `.dockerignore` e `.env.example`.

## 1. Como gerar a imagem Docker

Na raiz do projeto (onde está o `Dockerfile`):

```bash
docker build -t sistema-pedido:latest .
```

Isso instala as dependências de `requirements.txt` sem modificá-lo, copia
`app.py`, `grade_app/`, `configs/` (com os `.xlsx` atuais como dado inicial —
serão sobrepostos pelo volume persistente, ver seção 5) e `config_padrao.xlsx`.

Para builds reproduzíveis com data/versão, pode marcar com uma tag adicional:

```bash
docker build -t sistema-pedido:$(date +%Y%m%d) -t sistema-pedido:latest .
```

## 2. Como executar localmente (teste antes de subir no TrueNAS)

Antes de qualquer coisa, copie o modelo de secrets e preencha com valores
reais (ou, para um teste rápido sem Google Sheets, só a seção `[master]` —
veja `.streamlit/secrets.toml.example` para o passo a passo completo):

```bash
mkdir -p ./_dados_locais/configs ./_dados_locais/backups_config
cp .streamlit/secrets.toml.example ./_dados_locais/secrets.toml
# edite ./_dados_locais/secrets.toml com os valores reais
```

Suba o container:

```bash
docker run -d --name sistema-pedido \
  -p 8501:8501 \
  -v "$(pwd)/_dados_locais/secrets.toml:/app/.streamlit/secrets.toml:ro" \
  -v "$(pwd)/_dados_locais/configs:/app/configs" \
  -v "$(pwd)/_dados_locais/backups_config:/app/backups_config" \
  --restart unless-stopped \
  sistema-pedido:latest
```

Acesse http://localhost:8501 e faça login. `_dados_locais/` é só para teste
local — não vai para o Git (adicione ao seu `.gitignore` local se quiser).

## 3. Porta utilizada

- **8501** dentro do container (`--server.port=8501`, `--server.address=0.0.0.0`).
- Mapeie para a porta que preferir no host/TrueNAS com `-p <porta_host>:8501`.
  Como o acesso é só via Tailscale por enquanto, não é necessário expor a
  porta na rede local/Internet — restrinja ao IP do Tailscale se o Docker
  host permitir (`-p 100.x.x.x:8501:8501`, usando o IP Tailscale da própria
  máquina) ou controle o acesso pelas ACLs do Tailscale.

## 4. Variáveis de ambiente necessárias

O login e as credenciais do Google **não** usam variável de ambiente — vêm
de `st.secrets`, lido do arquivo `/app/.streamlit/secrets.toml` dentro do
container (por isso ele precisa ser montado como volume/bind mount, nunca
copiado para dentro da imagem). Veja o mapeamento completo de campos em
`.streamlit/secrets.toml.example`.

`.env.example` traz variáveis **opcionais** de ajuste do próprio Streamlit
(fuso horário, headless mode) — não são obrigatórias, pois os mesmos valores
de porta/endereço já vêm fixos no `ENTRYPOINT` do Dockerfile.

## 5. Volumes necessários

| Volume no container | Conteúdo | Por quê é necessário |
|---|---|---|
| `/app/.streamlit/secrets.toml` (arquivo, `:ro`) | Credenciais de login (Google Service Account, sheet_id, conta master) | Nunca deve ir para a imagem; sem ele o login fica bloqueado |
| `/app/configs` | `config_<cliente>.xlsx` — DE/PARA de lojas/produtos e ordem da grade, editável pela aba CONFIGURAÇÕES | Dado de trabalho real. Sem volume, toda edição feita pelos usuários se perde ao recriar o container (a imagem já vem com os `.xlsx` atuais como seed inicial — o volume assume a partir daí) |
| `/app/backups_config` | Backups automáticos (até 10 por cliente) gerados antes de cada gravação em `configs/` | Sem volume, perde-se o histórico de segurança a cada redeploy |

Não é necessário volume para PDFs enviados (são processados em memória/
arquivo temporário e descartados) nem para os Excels baixados pelo usuário
(gerados em memória e entregues via download, nunca gravados em disco).

No TrueNAS SCALE, crie dois datasets (ex.: `apps/sistema-pedido/configs` e
`apps/sistema-pedido/backups_config`) e aponte os bind mounts do app para
eles, mais um terceiro caminho (ou um "Config Secret" da própria interface,
se preferir) só para o `secrets.toml`.

## 6. Como atualizar o sistema

1. Atualize o código-fonte (`git pull` ou copie os arquivos novos).
2. Rebuild da imagem:
   ```bash
   docker build -t sistema-pedido:latest .
   ```
3. Recrie o container preservando os mesmos volumes (os dados em `configs/`
   e `backups_config/` não são afetados pelo rebuild, pois vivem fora da
   imagem):
   ```bash
   docker stop sistema-pedido && docker rm sistema-pedido
   docker run -d --name sistema-pedido \
     -p 8501:8501 \
     -v /caminho/secrets.toml:/app/.streamlit/secrets.toml:ro \
     -v /caminho/configs:/app/configs \
     -v /caminho/backups_config:/app/backups_config \
     --restart unless-stopped \
     sistema-pedido:latest
   ```
   No TrueNAS Apps, isso normalmente é "Update Image" + restart do app pela
   própria interface, mantendo os mounts configurados.

## 7. Como fazer rollback

Se você marcou a imagem anterior com uma tag antes de atualizar (ver seção
1, ex. `sistema-pedido:20260810`), o rollback é reapontar o container para
essa tag:

```bash
docker stop sistema-pedido && docker rm sistema-pedido
docker run -d --name sistema-pedido \
  -p 8501:8501 \
  -v /caminho/secrets.toml:/app/.streamlit/secrets.toml:ro \
  -v /caminho/configs:/app/configs \
  -v /caminho/backups_config:/app/backups_config \
  --restart unless-stopped \
  sistema-pedido:20260810
```

Como `configs/` e `backups_config/` ficam fora da imagem, o rollback de
código não afeta os dados — só volta a versão do app. Se precisar também
reverter um dado de configuração ruim, restaure o `.xlsx` correspondente a
partir de `backups_config/` (ver seção 10).

## 8. Como verificar logs

```bash
docker logs sistema-pedido            # logs acumulados
docker logs -f sistema-pedido         # acompanhar em tempo real
docker logs --tail 100 sistema-pedido # últimas 100 linhas
```

Erros de login/Google Sheets aparecem no log com o prefixo `[auth] Falha ao
conectar na planilha de usuarios: ...` (ver `grade_app/auth.py`). No
TrueNAS Apps, os logs também ficam disponíveis na aba do app na interface.

## 9. Como verificar o healthcheck

O Dockerfile define um `HEALTHCHECK` que chama `GET /_stcore/health` a cada
30s. Para consultar o status:

```bash
docker inspect --format='{{.State.Health.Status}}' sistema-pedido
docker inspect sistema-pedido | grep -A 20 '"Health"'
```

Ou diretamente, de dentro da rede Tailscale:

```bash
curl -f http://<host>:8501/_stcore/health
```

Resposta `ok` com HTTP 200 = saudável. O TrueNAS Apps também mostra esse
status (verde/vermelho) na listagem de apps.

## 10. Como fazer backup dos dados persistentes

Os únicos dados que precisam de backup são os volumes `configs/` e
`backups_config/` (o app já mantém até 10 backups automáticos por cliente
dentro de `backups_config/`, mas isso não substitui um backup externo).

- **Snapshot ZFS (recomendado no TrueNAS)**: crie uma snapshot task no
  dataset usado por `configs/` (e opcionalmente `backups_config/`), com a
  frequência que preferir (diária é suficiente, dado o baixo volume de
  escrita).
- **Cópia manual**:
  ```bash
  tar -czf backup_configs_$(date +%Y%m%d).tar.gz -C /caminho configs backups_config
  ```
- Restaurar é o inverso: copiar os `.xlsx` de volta para o dataset/volume
  montado em `configs/` e recriar o container (ele lê automaticamente na
  próxima inicialização — `grade_app/config.py:carregar_config`).

## Observações desta implantação

- **Sem migração de banco de dados**: o sistema continua usando arquivos
  Excel locais para configuração, como hoje. O PostgreSQL 18 do seu TrueNAS
  não é usado por este app — ver a auditoria original para a análise de por
  que isso não traz benefício claro no estado atual do sistema.
- **`requirements.txt` não foi alterado** (continua com `>=`, sem versões
  travadas) para não divergir da versão do Streamlit Community Cloud. No
  build local de validação desta implantação, a resolução atual instalou
  `pandas==3.0.5`; o roundtrip de leitura/escrita de configuração foi
  testado e funcionou normalmente, mas se quiser reprodutibilidade
  garantida entre rebuilds, considere travar versões exatas num arquivo
  separado (ex. `requirements.lock.txt`) usado só na imagem Docker, sem
  tocar no `requirements.txt` original.
