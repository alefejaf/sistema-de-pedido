# Proteções da master e publicação controlada (Etapa 4A)

Este documento descreve **como configurar o GitHub** e **como ativar com segurança** o
novo fluxo de publicação. Nada aqui foi aplicado: as configurações do GitHub dependem
de você (interface web) e os workflows só entram em vigor quando chegarem à `master`
por Pull Request aprovado.

## 1. Diagnóstico do estado ANTES desta etapa (leitura via API, 23/11/2026)

| Item | Estado | Risco |
|---|---|---|
| Proteção da `master` / rulesets | **nenhuma** | qualquer push ou force push altera a produção |
| Environments | **nenhum** | não existe ponto de aprovação |
| `docker-publish.yml` | push na `master` → build → `:latest` → `app.pull_images` no TrueNAS, **sem testes e sem aprovação** | merge = deploy |
| `workflow_dispatch` | roda em **qualquer branch**; publicaria código de desenvolvimento como `:latest` | deploy acidental |
| Secrets `TAILSCALE_AUTHKEY`, `TRUENAS_SSH_KEY` | nível de **repositório** | qualquer workflow que os cite os recebe |
| Actions de terceiros | tag móvel (`@v4`) | cadeia de suprimentos |
| `allow_auto_merge` / `delete_branch_on_merge` | `false` / `false` | já corretos (não mude) |
| Permissão padrão dos workflows | `read`; Actions não aprovam PRs | já corretos |
| **Webhook `share.streamlit.io/hook`** (evento push) | ativo desde 06/08; recebeu inclusive o push de `desenvolvimento` (HTTP 200) | **segundo caminho de deploy, fora do GitHub** |

Plano da conta: a API não informa (`plan: null`). O repositório é **público**, e para repositórios
públicos o GitHub oferece, em qualquer plano, rulesets, aprovação obrigatória em
Environments, restrição de branches de deploy e secrets por environment. Confirme na
tela ao configurar; **se o repositório virar privado num plano gratuito, a aprovação
do Environment deixa de existir e o portão desaparece em silêncio**. Nesse caso reavalie
antes de publicar qualquer coisa.

## 2. O que foi preparado (somente na `desenvolvimento`, local)

| Arquivo | Função |
|---|---|
| `.github/workflows/docker-publish.yml` | **versão protegida** (substitui a atual quando chegar à master) |
| `.github/workflows/rollback-producao.yml` | rollback por SHA conhecido, com aprovação |
| `.github/workflows/ci.yml` | + `workflow_call` e actions fixadas por SHA |
| `docs/github/ruleset-master.json` | modelo de ruleset da master (importável, **desativado**) |
| `docs/github/ruleset-desenvolvimento.json` | modelo contra exclusão/force push na `desenvolvimento` |
| `scripts/verificar_protecoes_github.sh` | auditoria **somente leitura** das proteções |
| `tests/test_workflows_publicacao.py` | 78 testes estáticos e funcionais dos workflows e rulesets |
| `.gitignore` | exceção `!docs/github/*.json` (o `*.json` global os ignorava) |

### Como o novo `docker-publish.yml` funciona

```
push na master ─► guarda ─► testes (ci.yml, no commit exato) ─► publicar (PAUSA: aguarda aprovação)
                                                                   │ aprovado
                                                                   ├─ confere que o commit ainda é o topo da master
                                                                   ├─ login GHCR, registra o :latest anterior (digest)
                                                                   ├─ build e push  :<sha>  e  :latest
                                                                   ├─ resumo do run (commit, imagem, digest, anterior)
                                                                   └─ Tailscale + SSH + app.pull_images (igual a hoje)
```

* `guarda`: sem permissões e sem secrets. Recusa tudo que não seja `refs/heads/master`
  (também `workflow_dispatch` em outra branch), repositório diferente e eventos não previstos.
  Todo job depende dele, então nada de build/push/secrets roda fora da `master`.
* `testes`: reexecuta pytest + build Docker no commit exato. Se falhar, o pedido de aprovação nem aparece.
* `publicar` (`environment: production`): só começa **depois** da aprovação. É o único job com
  `packages: write` e o único que referencia os secrets.
* Concorrência `producao-sistema-de-pedido` (compartilhada com o rollback), `cancel-in-progress: false`:
  nunca há dois deploys ao mesmo tempo e uma publicação em andamento não é cancelada.
* Tags `:<sha>` (imutável) e `:latest` preservadas, mais labels OCI `revision`/`source`.
* **Falha segura de credenciais:** o primeiro passo do job aprovado (antes de login, build ou push) aborta se
  `TAILSCALE_AUTHKEY`/`TRUENAS_SSH_KEY` vierem vazios. Motivo: o `GITHUB_TOKEN` **não consegue consultar** se o
  Environment está protegido, e um Environment inexistente é criado pelo GitHub **sem proteção e sem secrets**.
  Esse passo só vira uma proteção real quando os secrets existem **apenas** no environment (seção 3.2); enquanto
  também existirem no repositório, ele não detecta um environment criado por acidente. A proteção principal
  continua sendo criar e verificar o environment **antes** do merge (seção 3.1 e `verificar_protecoes_github.sh`).
* Nada em `app.py`, `grade_app/`, `configs/`, `Dockerfile` ou volumes foi alterado.

Pequenas mudanças no deploy (sem mudar o comando do TrueNAS): `-o BatchMode=yes -o ConnectTimeout=20`
no ssh, host/usuário/app em variáveis do job e remoção da chave SSH ao final.

## 3. Configuração no GitHub (interface web), nesta ordem

> Faça tudo **antes** de abrir o PR para a master. Depois de cada passo, rode
> `bash scripts/verificar_protecoes_github.sh` (só leitura).

### 3.1 Environment `production` (o portão de aprovação)

`Settings → Environments → New environment` → nome exato **`production`**:

* **Required reviewers**: marque e adicione `alefejaf`.
* **Prevent self-review**: **desmarcado** (ver 3.1.1). Com um único administrador, marcado, ninguém conseguiria aprovar.
* **Allow administrators to bypass configured protection rules**: **desmarcado**.
* **Wait timer**: 0.
* **Deployment branches and tags** → *Selected branches and tags* → **Add** → `master`.
  (Segunda camada: mesmo que a guarda do workflow falhasse, o GitHub recusa outra branch.)

> **Crítico:** se o workflow citar `environment: production` e o environment **não existir**, o GitHub o
> cria **sem nenhuma proteção** e o job segue sem aprovação. Por isso o environment tem que existir
> e estar configurado **antes** do primeiro merge (o script de verificação acusa FALHA se não estiver).

#### 3.1.1 Repositório com um único administrador: como configurar a aprovação

Com uma só pessoa, a aprovação é um **portão de confirmação deliberada**, não uma segregação de funções. Ela
protege contra **acidente** (merge, dispatch ou clique errado), mas **não** contra uma conta comprometida:
quem controla a sua conta aprova o próprio deploy. Configuração recomendada:

| Opção | Valor | Por quê |
|---|---|---|
| Required reviewers | `alefejaf` | o job fica pausado até você clicar *Approve and deploy* |
| Prevent self-review | **desmarcado** | marcado, o autor do push não pode aprovar e o fluxo trava para sempre |
| Allow administrators to bypass | **desmarcado** | o administrador não pode pular a pausa |
| Aprovações exigidas no PR da ruleset | **0** | `>=1` impediria todo merge (você não aprova o próprio PR) |
| Deployment branches | só `master` | segunda barreira além da guarda do workflow |

Para ter **dois pares de olhos de verdade**, adicione uma segunda conta de confiança como *Required reviewer*,
marque *Prevent self-review* e passe `required_approving_review_count` para 1 na ruleset. Até lá, proteja a conta
(2FA com chave de segurança) e mantenha o *Reject* como padrão para qualquer aprovação que você não reconheça.

### 3.2 Secrets no environment (recomendado)

`Settings → Environments → production → Environment secrets`: crie `TAILSCALE_AUTHKEY` e `TRUENAS_SSH_KEY`
com os mesmos valores. **Não apague os do repositório ainda**; apague só depois do primeiro deploy
aprovado com sucesso. Ganho: só jobs que passaram pela aprovação enxergam os secrets, e a falha segura de
credenciais (seção 2) passa a funcionar como rede de proteção contra um environment criado sem proteção.

### 3.3 Rulesets

`Settings → Rules → Rulesets → New ruleset → Import a ruleset` → escolha o arquivo:

1. `docs/github/ruleset-desenvolvimento.json` → revise → *Enforcement status: **Active*** → Create.
   (Impede apagar ou forçar push na `desenvolvimento`.)
2. `docs/github/ruleset-master.json` → entra como **Disabled**. Revise e, na regra *Require status checks*,
   confirme que os dois checks aparecem **exatamente** assim (são os nomes dos jobs do `ci.yml`):

   | Check obrigatório | Origem |
   |---|---|
   | `Testes automatizados (pytest)` | job `testes` do `ci.yml` |
   | `Validar build da imagem Docker (sem publicar)` | job `docker-build` do `ci.yml` |

   Ambos com a fonte *GitHub Actions*. Só depois mude para **Active**.

O que a ruleset da master faz: PR obrigatório (0 aprovações, pois é conta única; threads
resolvidas; aprovação antiga descartada em novo push), checks obrigatórios, bloqueio de
exclusão e de force push, **sem nenhum ator de bypass**. Auto-merge já está desligado no
repositório (`allow_auto_merge=false`; não ligue).
`strict_required_status_checks_policy` ficou `false` de propósito: a publicação reexecuta os testes
no commit exato da master, então não há necessidade de exigir a branch atualizada a cada PR.

### 3.4 Ajustes opcionais de segurança

* `Settings → Actions → General → Fork pull request workflows`: *Require approval for all outside collaborators*.
* Com **todas** as actions já fixadas por SHA, dá para ligar *Require actions to be pinned to a full-length commit SHA*.
* Habilitar *Secret scanning* e *Push protection* (hoje desativados).

## 4. Evitar bloqueio acidental da própria master

* Importe a ruleset **desativada**, confira os nomes dos checks, depois ative.
* Nunca renomeie os jobs `testes` / `docker-build` do `ci.yml` sem atualizar a ruleset (um teste da suíte
  compara os dois e falha se divergirem). Check inexistente = PR eterno em *Expected — Waiting*.
* Não clique em **Delete branch** ao mesclar o PR (a `desenvolvimento` é permanente; a ruleset a protege).
* **Saída de emergência** (ex.: CI fora do ar e correção urgente): `Settings → Rules → Rulesets → Proteger master
  → Enforcement: Disabled`, mescle, e **reative na mesma hora**. Registre o motivo. O dono do repositório
  sempre consegue editar a ruleset; por isso não há bypass embutido.
* Aprovação do Environment sem revisor disponível = o job fica esperando (seguro; nada é publicado).

## 5. Plano para ativar o primeiro workflow protegido sem deploy não autorizado

O arquivo executado num push é o **do próprio commit enviado**. Logo, o merge que traz o workflow novo já
roda o workflow novo (com a aprovação), não o antigo.

1. **Pré-requisitos (3.1 a 3.3) feitos e verificados**: `verificar_protecoes_github.sh` com 0 FALHA.
2. Conferir em `share.streamlit.io` qual branch o app do Streamlit acompanha (seção 7).
3. *(com sua autorização)* commit + push **na `desenvolvimento`**. Só o `ci.yml` roda; o `docker-publish.yml` não dispara fora da master.
4. *(com sua autorização)* PR `desenvolvimento → master`. Os 2 checks são obrigatórios. Mescle **sem** apagar a branch.
5. O merge dispara o fluxo novo: `guarda ✓ → testes ✓ → publicar: "Waiting for review"`.
6. **Primeira vez: clique em *Reject*.** Nenhuma imagem é publicada, nenhum deploy ocorre, `:latest`
   permanece em `1f81184`. As proteções ficam ativas na master. (As diferenças em relação à master atual são só
   testes/CI/docs, que nem entram na imagem; mesmo aprovando, o app seria idêntico.)
7. Rodar o script de verificação: deve mostrar "master já tem a versão PROTEGIDA".
8. Em outro momento, janela controlada: *Run workflow* na `master` e **Approve** para validar o caminho feliz
   (e, se tudo certo, remover os secrets de nível de repositório).
9. Teste do portão (opcional, seguro): *Run workflow* escolhendo a branch `desenvolvimento` → deve falhar na `guarda` em segundos.

## 6. Rollback

Alvo = qualquer commit já publicado (tag `:<sha>`). Versão em produção hoje: `1f81184fead92399135a93cc0f72f8c8db40081b`.

1. Descubra o SHA: resumo do run de publicação (linha *`:latest` anterior*) ou
   `gh api users/alefejaf/packages/container/sistema-de-pedido/versions --jq '.[].metadata.container.tags'`.
2. `Actions → Rollback da producao → Run workflow` (branch **master**): `sha` = 40 caracteres, `confirmacao` = `ROLLBACK`
   (ou `gh workflow run rollback-producao.yml --ref master -f sha=<sha> -f confirmacao=ROLLBACK`).
3. `verificar-imagem` confirma que a imagem existe e mostra o **digest**; confira e **aprove** o job `rollback`.
4. O `:latest` é reapontado **por digest** (imutável, sem rebuild) e o TrueNAS recebe `app.pull_images`.
5. **Confirme no TrueNAS qual imagem está realmente em execução** (ver 6.1). Só então considere o rollback concluído.
6. Dados (`configs/`, `backups_config/`) **não são tocados**: o rollback troca só o código. Para reverter uma
   configuração ruim use `backups_config/` ou o snapshot ZFS.

### 6.1 Limite importante: reapontar o `:latest` NÃO garante que o TrueNAS rode a imagem anterior

O workflow só consegue (a) reapontar a tag no GHCR e (b) pedir `app.pull_images`. Isso **não prova** que o
container passou a usar a imagem desejada, porque:

* o app pode estar **fixado** em outra tag/digest (nesse caso mexer em `:latest` não muda nada);
* o `app.pull_images` baixa a imagem, mas **pode não recriar o container**; sem recriar, continua rodando a versão antiga;
* o host pode manter a imagem em cache ou o app pode usar uma política de pull que não revalida a tag;
* o comando não informa se o app voltou saudável.

**Verificação manual obrigatória após qualquer publicação ou rollback** (somente leitura, no TrueNAS):

```
sudo midclt call app.query '[["name","=","sistema-de-pedido"]]'          # imagem/tag configurada e estado
sudo docker ps --filter name=sistema-de-pedido --format '{{.Names}} {{.Image}} {{.Status}}'
sudo docker inspect <container> --format '{{.Image}}'                      # id da imagem em execução
sudo docker image inspect <imagem> --format '{{json .RepoDigests}}'        # compare com o digest do resumo do run
```

O digest em execução deve ser igual ao **Digest / Referência imutável** do resumo do run. Se não for, o rollback
**não** foi efetivado; a saída manual é editar a imagem do app no TrueNAS para a tag `:<sha>` desejada (ou
`@sha256:<digest>`) e reiniciar o app pela interface.

### 6.2 Estratégia-alvo: implantar por SHA/digest imutável (pendente de validação no TrueNAS)

Os workflows **já** publicam `:<sha>`, registram o digest e fazem o rollback **por digest**. O que ainda é transitório
é o último passo: o TrueNAS continua consumindo a tag móvel `:latest`. O desenho preferido, **não implementado
porque depende de validação**, é:

1. o TrueNAS App configurado com `ghcr.io/alefejaf/sistema-de-pedido@sha256:<digest>` (ou `:<sha>`), nunca `:latest`;
2. o deploy passa a **atualizar a imagem do app** para o digest publicado (e a recriar o container) em vez de só
   baixar `:latest`; o rollback seria a mesma operação com o digest anterior;
3. o workflow lê de volta a imagem em execução e **falha** se o digest não for o esperado.

Pré-requisitos a validar (primeiro na homologação, Etapa 4B, nunca direto na produção): que tipo de app é o
`sistema-de-pedido` (catálogo ou *custom app*), se `app.update`/`app.pull_images` aceita o formato por digest, se
recria o container e o que o `sudoers` do usuário de deploy permite executar. Até essa validação, **trate o rollback
automatizado como parcial** e confirme sempre pela seção 6.1.

## 7. Pendências de investigação (nada abaixo foi alterado)

### 7.1 Webhook do Streamlit Community Cloud — PENDENTE DE INVESTIGAÇÃO (não modificado)

| Campo | Valor observado (somente leitura, 23/11/2026) |
|---|---|
| Destino | `https://share.streamlit.io/hook` |
| Evento | `push` (qualquer branch) |
| Criado em | 06/08/2026 (hook id `662197548`) |
| Entregas recentes | 2, ambas HTTP 200; a última referente ao push de `desenvolvimento` (`784d1cb`) |

Por que importa: **é um segundo caminho de deploy**, fora do `docker-publish.yml`, do Environment `production` e da
ruleset. A ruleset limita *quem consegue gravar* na `master`, mas não impede que o Streamlit reimplante a branch que
ele acompanha. Se o app do Streamlit usar os mesmos dados/planilha de produção, um merge reimplanta esse app **sem
nenhuma aprovação**.

A investigar (por você, em `share.streamlit.io` → app → *Settings*; eu não tenho acesso nem devo alterar o hook):

1. Esse app ainda está em uso ou é legado (a produção hoje é o TrueNAS)?
2. Qual **branch** ele acompanha (`master`? `desenvolvimento`?) e qual arquivo principal?
3. De onde vêm os *Secrets* dele (mesma planilha de usuários/logs de produção?) e quem tem acesso?
4. Se for legado: desativar/excluir o app e, só depois, remover o webhook em `Settings → Webhooks`.
   Se for usado: decidir se deve acompanhar uma branch própria ou ficar atrás de outra proteção.

Enquanto isso, `scripts/verificar_protecoes_github.sh` mostra um AVISO permanente. O push desta etapa na
`desenvolvimento` também notifica esse webhook (como todo push); o código do app não muda neste commit.

### 7.2 TrueNAS (não consultado; depende de você)

Confirmar, em modo leitura: tag/digest com que o app está configurado, se `app.pull_images` recria o container, tipo do
app (catálogo ou custom), e permissões do `sudoers` do usuário de deploy. Resultado define a seção 6.2.

### 7.3 Endurecimentos futuros (fora desta etapa)

* **Chave de host SSH**: o deploy mantém `StrictHostKeyChecking=no` (como hoje, dentro do Tailscale). Para fixar,
  rode `ssh-keyscan` a partir da sua máquina e me passe a impressão digital.
* **Tailscale**: a action recomenda cliente OAuth no lugar de *auth key* (nós efêmeros e com tag).
* **IP do TrueNAS** e usuário SSH aparecem em arquivo público (já era assim); mover para variáveis do environment.
* **Validação ponta a ponta**: o fluxo completo não pode ser executado sem publicar de verdade. A confiança vem de
  `actionlint`, dos testes (incluindo execução real das guardas com entradas hostis) e do passo 6 do plano da seção 5 (*Reject*).
