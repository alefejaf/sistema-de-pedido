#!/usr/bin/env bash
# Verificação SOMENTE LEITURA das proteções de publicação do repositório.
#
# Não altera nada: só faz GET na API do GitHub (gh api). Use ANTES de mesclar o
# workflow protegido na master e sempre que mudar configurações.
#
# Uso:   bash scripts/verificar_protecoes_github.sh [dono/repositorio]
# Saída: OK / FALHA / AVISO por item. Código de saída = número de FALHAs (0 = tudo certo).
set -u
REPO="${1:-alefejaf/sistema-de-pedido}"
BRANCH="master"
ENV_NAME="production"
CHECKS=("Testes automatizados (pytest)" "Validar build da imagem Docker (sem publicar)")

falhas=0; avisos=0
ok()     { printf '  [ OK    ] %s\n' "$1"; }
falha()  { printf '  [ FALHA ] %s\n' "$1"; falhas=$((falhas + 1)); }
aviso()  { printf '  [ AVISO ] %s\n' "$1"; avisos=$((avisos + 1)); }
# Devolve a resposta SÓ se a chamada der certo. Em erro (404, sem permissão...) o gh
# imprime o corpo do erro no stdout; sem este filtro isso viraria um "OK" falso.
api() {
  local saida
  saida="$(gh api "$@" 2>/dev/null)" || return 1
  printf '%s' "$saida"
}

command -v gh >/dev/null 2>&1 || { echo "gh (GitHub CLI) nao encontrado"; exit 99; }
gh auth status >/dev/null 2>&1 || { echo "gh nao autenticado (gh auth login)"; exit 99; }

echo "Repositorio: $REPO   (somente leitura)"
echo
echo "1) Ruleset/branch protection ATIVA na $BRANCH"
tipos="$(api "repos/$REPO/rules/branches/$BRANCH" --jq '[.[].type] | join(",")' || true)"
if [ -z "$tipos" ]; then
  falha "nenhuma regra ativa na $BRANCH (ruleset ausente ou em 'disabled')"
else
  for t in deletion non_fast_forward pull_request required_status_checks; do
    case ",$tipos," in *",$t,"*) ok "regra '$t' ativa" ;; *) falha "regra '$t' AUSENTE" ;; esac
  done
  contextos="$(api "repos/$REPO/rules/branches/$BRANCH" \
    --jq '[.[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context] | join("|")' || true)"
  for c in "${CHECKS[@]}"; do
    case "|$contextos|" in *"|$c|"*) ok "check obrigatorio: $c" ;; *) falha "check NAO exigido: $c" ;; esac
  done
fi

echo
echo "2) Bypass nas rulesets"
ids="$(api "repos/$REPO/rulesets" --jq '.[].id' || true)"
if [ -z "$ids" ]; then
  aviso "nenhuma ruleset cadastrada"
else
  for id in $ids; do
    nome="$(api "repos/$REPO/rulesets/$id" --jq '.name')"
    n="$(api "repos/$REPO/rulesets/$id" --jq '.bypass_actors | length')"
    enf="$(api "repos/$REPO/rulesets/$id" --jq '.enforcement')"
    if [ "${n:-0}" = "0" ]; then ok "ruleset '$nome' ($enf): sem atores de bypass"
    else aviso "ruleset '$nome' ($enf): $n ator(es) com bypass"; fi
  done
fi

echo
echo "3) Environment '$ENV_NAME' (portao de aprovacao)"
env_json="$(api "repos/$REPO/environments/$ENV_NAME" || true)"
if [ -z "$env_json" ]; then
  falha "environment '$ENV_NAME' NAO existe. ATENCAO: se o workflow rodar assim, o GitHub o cria SEM protecao e a publicacao segue sem aprovacao."
else
  ok "environment '$ENV_NAME' existe"
  revisores="$(api "repos/$REPO/environments/$ENV_NAME" \
    --jq '[.protection_rules[] | select(.type=="required_reviewers") | .reviewers | length] | add // 0')"
  if [ "${revisores:-0}" -ge 1 ]; then ok "revisores obrigatorios: $revisores"; else falha "SEM revisores obrigatorios (nada pede aprovacao)"; fi
  custom="$(api "repos/$REPO/environments/$ENV_NAME" --jq '.deployment_branch_policy.custom_branch_policies // false')"
  if [ "$custom" = "true" ]; then
    pol="$(api "repos/$REPO/environments/$ENV_NAME/deployment-branch-policies" --jq '[.branch_policies[].name] | sort | join(",")' || true)"
    if [ "$pol" = "$BRANCH" ]; then ok "deploy permitido somente da branch: $pol"; else falha "branches permitidas no environment: '${pol:-nenhuma}' (esperado: $BRANCH)"; fi
  else
    falha "environment aceita QUALQUER branch (configure 'Selected branches' = $BRANCH)"
  fi
  bypass="$(api "repos/$REPO/environments/$ENV_NAME" --jq '.can_admins_bypass')"
  if [ "$bypass" = "false" ]; then ok "administradores NAO podem pular a aprovacao"; else aviso "administradores podem pular a aprovacao (desmarque 'Allow administrators to bypass')"; fi
  se="$(api "repos/$REPO/environments/$ENV_NAME" --jq '[.protection_rules[] | select(.type=="required_reviewers") | .prevent_self_review] | any')"
  [ "$se" = "true" ] && aviso "'Prevent self-review' ligado: com um unico mantenedor ninguem consegue aprovar" || ok "auto-aprovacao permitida (conta unica)"
fi

echo
echo "4) Secrets de producao"
env_secrets="$(api "repos/$REPO/environments/$ENV_NAME/secrets" --jq '[.secrets[].name] | sort | join(",")' || true)"
repo_secrets="$(api "repos/$REPO/actions/secrets" --jq '[.secrets[].name] | sort | join(",")' || true)"
for s in TAILSCALE_AUTHKEY TRUENAS_SSH_KEY; do
  case ",$env_secrets," in *",$s,"*) ok "$s esta no environment '$ENV_NAME'" ;;
    *) case ",$repo_secrets," in
         *",$s,"*) aviso "$s esta no REPOSITORIO (visivel a qualquer workflow); recomendado mover para o environment" ;;
         *) falha "$s nao encontrado" ;;
       esac ;;
  esac
done

echo
echo "5) Configuracoes do repositorio"
[ "$(api "repos/$REPO" --jq '.allow_auto_merge')" = "false" ] && ok "auto-merge desativado" || falha "auto-merge ATIVO"
[ "$(api "repos/$REPO" --jq '.delete_branch_on_merge')" = "false" ] && ok "nao apaga a branch apos o merge" || aviso "apaga a branch automaticamente apos o merge (desenvolvimento seria removida)"
[ "$(api "repos/$REPO/actions/permissions/workflow" --jq '.default_workflow_permissions')" = "read" ] && ok "permissao padrao dos workflows: somente leitura" || falha "permissao padrao dos workflows NAO e read"
[ "$(api "repos/$REPO/actions/permissions/workflow" --jq '.can_approve_pull_request_reviews')" = "false" ] && ok "Actions nao aprovam PRs" || aviso "Actions podem aprovar PRs"

echo
echo "6) Versao do docker-publish.yml que esta na $BRANCH"
conteudo="$(api "repos/$REPO/contents/.github/workflows/docker-publish.yml?ref=$BRANCH" --jq '.content' | tr -d '\n' | base64 -d 2>/dev/null || true)"
if printf '%s' "$conteudo" | grep -q "environment:"; then ok "master ja tem a versao PROTEGIDA (com environment)"
else aviso "master ainda tem a versao ANTIGA (push na master publica e implanta SEM aprovacao)"; fi

echo
echo "7) Outros caminhos de deploy (verificacao manual)"
hooks="$(api "repos/$REPO/hooks" --jq '[.[] | select(.config.url | test("streamlit"))] | length' || echo 0)"
if [ "${hooks:-0}" -ge 1 ]; then aviso "webhook do Streamlit Community Cloud ativo: um push na branch que o app acompanha o REIMPLANTA, fora deste portao. Confira a branch em share.streamlit.io"; else ok "nenhum webhook do Streamlit"; fi

echo
echo "Resumo: $falhas falha(s), $avisos aviso(s)"
exit "$falhas"
