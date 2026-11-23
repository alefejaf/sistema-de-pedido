"""Validação ESTÁTICA e FUNCIONAL dos workflows de publicação e dos modelos de ruleset.

Nada aqui chama GitHub, GHCR ou TrueNAS. Os testes:
  * leem os YAMLs e verificam as garantias de segurança (guarda, aprovação,
    permissões mínimas, secrets só depois da aprovação, concorrência, SHA pinning);
  * EXECUTAM de verdade os scripts de guarda (bash) com entradas válidas e hostis;
  * conferem que os modelos de ruleset exigem exatamente os checks que o ci.yml produz.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

RAIZ = Path(__file__).resolve().parent.parent
WF = RAIZ / ".github" / "workflows"
PUBLICAR = WF / "docker-publish.yml"
ROLLBACK = WF / "rollback-producao.yml"
CI = WF / "ci.yml"
RULESETS = RAIZ / "docs" / "github"
REPO = "alefejaf/sistema-de-pedido"
TODOS = [PUBLICAR, ROLLBACK, CI]


def carregar(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def gatilhos(d: dict) -> dict:
    g = d.get(True) if True in d else d.get("on")  # PyYAML lê 'on' como True
    return g if isinstance(g, dict) else {k: None for k in ([g] if isinstance(g, str) else g)}


def passos(job: dict):
    return job.get("steps", [])


def fecho_needs(jobs: dict, nome: str) -> set:
    visto, fila = set(), list(_lista(jobs[nome].get("needs")))
    while fila:
        j = fila.pop()
        if j not in visto:
            visto.add(j)
            fila += _lista(jobs[j].get("needs"))
    return visto


def _lista(v):
    return [] if v is None else ([v] if isinstance(v, str) else list(v))


def texto_sem_comentarios(p: Path) -> str:
    return "\n".join(re.sub(r"\s+#.*$", "", l) for l in p.read_text(encoding="utf-8").splitlines()
                     if not l.lstrip().startswith("#"))


# --------------------------------------------------------------------------
# Regras gerais (valem para TODOS os workflows)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("arq", TODOS, ids=lambda p: p.name)
def test_toda_action_externa_esta_fixada_por_sha(arq):
    for m in re.finditer(r"^\s*-?\s*uses:\s*(\S+)", texto_sem_comentarios(arq), flags=re.M):
        ref = m.group(1)
        if ref.startswith("./"):
            continue
        assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref), f"{arq.name}: action sem SHA fixo: {ref}"


@pytest.mark.parametrize("arq", TODOS, ids=lambda p: p.name)
def test_sha_pinning_mantem_comentario_com_a_versao(arq):
    for l in arq.read_text(encoding="utf-8").splitlines():
        if re.search(r"uses:\s*\S+@[0-9a-f]{40}", l):
            assert re.search(r"#\s*v\d", l), f"{arq.name}: falta '# vN' ao lado do SHA: {l.strip()}"


@pytest.mark.parametrize("arq", TODOS, ids=lambda p: p.name)
def test_nenhum_run_interpola_expressoes_do_github(arq):
    """'${{ ... }}' dentro de run: permite injeção de comando (ex.: nome de branch).
    Tudo deve entrar por env: e ser lido como variável de shell."""
    for nome, job in carregar(arq)["jobs"].items():
        for p in passos(job):
            assert "${{" not in p.get("run", ""), f"{arq.name}/{nome}: run com interpolação: {p.get('name')}"


@pytest.mark.parametrize("arq", TODOS, ids=lambda p: p.name)
def test_nenhum_gatilho_perigoso(arq):
    g = gatilhos(carregar(arq))
    for proibido in ("pull_request_target", "workflow_run", "schedule", "issue_comment", "repository_dispatch"):
        assert proibido not in g


@pytest.mark.parametrize("arq", TODOS, ids=lambda p: p.name)
def test_permissao_global_e_somente_leitura(arq):
    assert carregar(arq)["permissions"] == {"contents": "read"}


# --------------------------------------------------------------------------
# docker-publish.yml
# --------------------------------------------------------------------------
def test_publicar_gatilhos_somente_push_master_e_dispatch():
    g = gatilhos(carregar(PUBLICAR))
    assert set(g) == {"push", "workflow_dispatch"}
    assert g["push"] == {"branches": ["master"]}
    assert not g["workflow_dispatch"]  # sem inputs que alterem o que é publicado


def test_publicar_guarda_e_o_primeiro_e_todo_job_depende_dele():
    jobs = carregar(PUBLICAR)["jobs"]
    assert list(jobs)[0] == "guarda"
    for nome in jobs:
        if nome != "guarda":
            assert "guarda" in fecho_needs(jobs, nome), f"job '{nome}' pode rodar sem passar pela guarda"


def test_publicar_exige_testes_antes_de_publicar():
    jobs = carregar(PUBLICAR)["jobs"]
    assert jobs["testes"]["uses"] == "./.github/workflows/ci.yml"
    assert "testes" in _lista(jobs["publicar"]["needs"])


def test_publicar_job_de_publicacao_exige_environment_production():
    job = carregar(PUBLICAR)["jobs"]["publicar"]
    env = job["environment"]
    assert (env["name"] if isinstance(env, dict) else env) == "production"


def _segredos_usados(texto: str):
    return set(re.findall(r"secrets\.(\w+)", texto)) - {"GITHUB_TOKEN"}


@pytest.mark.parametrize("arq,job_ok", [(PUBLICAR, "publicar"), (ROLLBACK, "rollback")], ids=["publicar", "rollback"])
def test_secrets_de_producao_so_existem_no_job_aprovado(arq, job_ok):
    d = carregar(arq)
    for nome, job in d["jobs"].items():
        usados = _segredos_usados(yaml.safe_dump(job))
        if nome == job_ok:
            assert usados == {"TAILSCALE_AUTHKEY", "TRUENAS_SSH_KEY"}
            env = job["environment"]
            assert (env["name"] if isinstance(env, dict) else env) == "production"
        else:
            assert usados == set(), f"{arq.name}: job '{nome}' referencia secrets antes da aprovação: {usados}"


def test_publicar_permissao_de_escrita_em_pacotes_so_no_job_aprovado():
    jobs = carregar(PUBLICAR)["jobs"]
    for nome, job in jobs.items():
        perms = job.get("permissions", {})
        if nome == "publicar":
            assert perms == {"contents": "read", "packages": "write"}
        else:
            assert "write" not in json.dumps(perms), f"job '{nome}' com permissão de escrita"
    assert jobs["guarda"]["permissions"] == {}


def test_publicar_mantem_tags_por_sha_e_latest_com_rastreabilidade():
    job = carregar(PUBLICAR)["jobs"]["publicar"]
    build = next(p for p in passos(job) if p.get("id") == "build")
    assert build["with"]["push"] is True
    tags = build["with"]["tags"]
    assert "${{ env.IMAGE }}:${{ github.sha }}" in tags and "${{ env.IMAGE }}:latest" in tags
    assert "org.opencontainers.image.revision=${{ github.sha }}" in build["with"]["labels"]
    assert carregar(PUBLICAR)["env"]["IMAGE"] == "ghcr.io/alefejaf/sistema-de-pedido"


def test_publicar_registra_commit_imagem_digest_e_versao_anterior():
    job = carregar(PUBLICAR)["jobs"]["publicar"]
    nomes = [p["name"] for p in passos(job)]
    assert "Registrar versao anterior do :latest" in nomes
    resumo = next(p for p in passos(job) if p["name"].startswith("Registrar publicacao"))
    for campo in ("SHA", "DIGEST", "ANTERIOR_DIGEST", "GITHUB_STEP_SUMMARY"):
        assert campo in resumo["run"] or campo in json.dumps(resumo.get("env", {}))
    assert nomes.index("Registrar versao anterior do :latest") < nomes.index("Build e Push")  # antes de sobrescrever


def test_publicar_confere_que_o_commit_ainda_e_o_topo_da_master_antes_de_publicar():
    nomes = [p["name"] for p in passos(carregar(PUBLICAR)["jobs"]["publicar"])]
    assert nomes.index("Confirmar que este commit ainda e o topo da master") < nomes.index("Build e Push")


@pytest.mark.parametrize("arq,job,marco", [
    (PUBLICAR, "publicar", "Build e Push"),
    (ROLLBACK, "rollback", "Reapontar :latest para o digest verificado"),
], ids=["publicar", "rollback"])
def test_falha_segura_credenciais_verificadas_antes_de_qualquer_alteracao(arq, job, marco):
    """Environment inexistente é criado pelo GitHub sem proteção e sem secrets. Se os secrets
    ficarem só no environment, o passo abaixo aborta ANTES de publicar/reapontar."""
    nomes = [p["name"] for p in passos(carregar(arq)["jobs"][job])]
    verif = next(n for n in nomes if n.startswith("Verificar credenciais de producao"))
    assert nomes.index(verif) < nomes.index("Login no GHCR") < nomes.index(marco)
    passo = next(p for p in passos(carregar(arq)["jobs"][job]) if p["name"] == verif)
    assert "exit 1" in passo["run"] and "set -euo pipefail" in passo["run"]
    # não pode imprimir o valor dos secrets
    assert not re.search(r'echo[^\n]*\$\{?(TAILSCALE_AUTHKEY|TRUENAS_SSH_KEY)', passo["run"].replace(':-', ''))


def test_resumos_trazem_referencia_imutavel_e_aviso_de_que_retag_nao_garante_execucao():
    pub = PUBLICAR.read_text(encoding="utf-8")
    rol = ROLLBACK.read_text(encoding="utf-8")
    assert "${IMAGE}@${DIGEST}" in pub and "NAO prova que o container" in pub
    assert "${IMAGE}@${DIGEST}" in rol and "NAO garante que o TrueNAS passara a executar a imagem anterior" in rol


def test_publicar_deploy_so_depois_do_build_e_push():
    nomes = [p["name"] for p in passos(carregar(PUBLICAR)["jobs"]["publicar"])]
    assert nomes.index("Build e Push") < nomes.index("Instalar Tailscale") < nomes.index("Deploy no TrueNAS")


def test_concorrencia_unica_entre_publicar_e_rollback_sem_cancelar():
    a, b = carregar(PUBLICAR)["concurrency"], carregar(ROLLBACK)["concurrency"]
    assert a == b == {"group": "producao-sistema-de-pedido", "cancel-in-progress": False}


def test_comando_de_deploy_preservado_igual_ao_original():
    """O TrueNAS continua recebendo exatamente a mesma chamada de antes."""
    for arq in (PUBLICAR, ROLLBACK):
        t = arq.read_text(encoding="utf-8")
        assert 'sudo -n /usr/bin/midclt call app.pull_images ${TRUENAS_APP}' in t
        d = carregar(arq)
        job = d["jobs"]["publicar" if arq == PUBLICAR else "rollback"]
        assert job["env"] == {"TRUENAS_HOST": "100.74.190.91", "TRUENAS_USER": "truenas_admin",
                              "TRUENAS_APP": "sistema-de-pedido"}


def test_chave_ssh_e_removida_do_runner_ao_final():
    for arq, nome in ((PUBLICAR, "publicar"), (ROLLBACK, "rollback")):
        ultimo = passos(carregar(arq)["jobs"][nome])[-1]
        assert ultimo["if"] == "always()" and "rm -f ~/.ssh/truenas_key" in ultimo["run"]


# --------------------------------------------------------------------------
# rollback-producao.yml
# --------------------------------------------------------------------------
def test_rollback_so_dispatch_manual_com_entradas_obrigatorias():
    d = carregar(ROLLBACK)
    g = gatilhos(d)
    assert set(g) == {"workflow_dispatch"}
    inputs = g["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"sha", "confirmacao"} and all(i["required"] for i in inputs.values())


def test_rollback_cadeia_guarda_verificacao_aprovacao():
    jobs = carregar(ROLLBACK)["jobs"]
    assert list(jobs) == ["guarda", "verificar-imagem", "rollback"]
    assert fecho_needs(jobs, "rollback") == {"guarda", "verificar-imagem"}
    assert fecho_needs(jobs, "verificar-imagem") == {"guarda"}
    assert jobs["verificar-imagem"]["permissions"] == {"contents": "read", "packages": "read"}
    assert jobs["rollback"]["permissions"] == {"contents": "read", "packages": "write"}


def test_rollback_nao_reconstroi_imagem_nem_roda_docker_build():
    t = texto_sem_comentarios(ROLLBACK)
    assert "build-push-action" not in t
    assert not re.search(r"docker\s+build(?!x)", t), "rollback não pode reconstruir imagem"
    assert not re.search(r"imagetools\s+create(?!.*@)", t) or "${IMAGE}@${DIGEST}" in t
    assert "imagetools create" in t and '"${IMAGE}@${DIGEST}"' in t  # reaponta por digest imutável


# --------------------------------------------------------------------------
# ci.yml continua inofensivo e reutilizável
# --------------------------------------------------------------------------
def test_ci_aceita_workflow_call_sem_secrets_e_sem_publicar():
    d = carregar(CI)
    assert "workflow_call" in gatilhos(d)
    t = texto_sem_comentarios(CI)
    assert "secrets." not in t and "packages: write" not in t and "push: true" not in t


# --------------------------------------------------------------------------
# Execução REAL dos scripts de guarda
# --------------------------------------------------------------------------
def _bash():
    candidatos = [os.environ.get("BASH"), r"C:\Program Files\Git\bin\bash.exe", shutil.which("bash")]
    for c in candidatos:
        if c and Path(c).exists():
            try:
                r = subprocess.run([c, "-c", "echo ok"], capture_output=True, text=True, timeout=20)
                if r.stdout.strip() == "ok":
                    return c
            except Exception:
                continue
    return None


BASH = _bash()
precisa_bash = pytest.mark.skipif(BASH is None, reason="bash não disponível")


def _rodar_guarda(arq: Path, job: str, env_extra: dict, cwd: Path):
    d = carregar(arq)
    passo = next(p for p in passos(d["jobs"][job]) if p.get("run"))
    env = {"PATH": os.environ.get("PATH", ""), **{k: str(v) for k, v in env_extra.items()}}
    return subprocess.run([BASH, "-c", passo["run"]], env=env, cwd=cwd, capture_output=True, text=True, timeout=30)


def _env_publicar(**kw):
    base = {"REPO": REPO, "REF": "refs/heads/master", "EVENT": "push"}
    base.update(kw)
    return base


@precisa_bash
@pytest.mark.parametrize("ref,evento", [
    ("refs/heads/master", "push"),
    ("refs/heads/master", "workflow_dispatch"),
])
def test_guarda_publicar_libera_somente_master(tmp_path, ref, evento):
    r = _rodar_guarda(PUBLICAR, "guarda", _env_publicar(REF=ref, EVENT=evento), tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


@precisa_bash
@pytest.mark.parametrize("ref,evento", [
    ("refs/heads/desenvolvimento", "workflow_dispatch"),   # o risco real: dispatch fora da master
    ("refs/heads/desenvolvimento", "push"),
    ("refs/heads/master-evil", "workflow_dispatch"),
    ("refs/heads/feature/x", "workflow_dispatch"),
    ("refs/tags/v1.0", "push"),
    ("refs/pull/7/merge", "pull_request"),
    ("refs/heads/master", "pull_request"),
    ("refs/heads/master", "schedule"),
    ("refs/heads/master", "repository_dispatch"),
    ("", "workflow_dispatch"),
])
def test_guarda_publicar_bloqueia_todo_o_resto(tmp_path, ref, evento):
    r = _rodar_guarda(PUBLICAR, "guarda", _env_publicar(REF=ref, EVENT=evento), tmp_path)
    assert r.returncode != 0
    assert "::error::" in r.stdout


@precisa_bash
def test_guarda_publicar_bloqueia_repositorio_diferente(tmp_path):
    r = _rodar_guarda(PUBLICAR, "guarda", _env_publicar(REPO="outro/sistema-de-pedido"), tmp_path)
    assert r.returncode != 0 and "Repositorio inesperado" in r.stdout


@precisa_bash
def test_guarda_publicar_nao_executa_nome_de_branch_malicioso(tmp_path):
    marcador = tmp_path / "PWNED"
    ref = f"refs/heads/x$(touch {marcador.as_posix()})"
    r = _rodar_guarda(PUBLICAR, "guarda", _env_publicar(REF=ref, EVENT="workflow_dispatch"), tmp_path)
    assert r.returncode != 0
    assert not marcador.exists(), "injeção de comando via nome de branch!"


SHA_OK = "a" * 40


def _env_rollback(**kw):
    base = {"REPO": REPO, "REF": "refs/heads/master", "SHA_ALVO": SHA_OK, "CONFIRMACAO": "ROLLBACK"}
    base.update(kw)
    return base


@precisa_bash
def test_guarda_rollback_aceita_entrada_valida(tmp_path):
    r = _rodar_guarda(ROLLBACK, "guarda", _env_rollback(), tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


@precisa_bash
@pytest.mark.parametrize("campo,valor", [
    ("REF", "refs/heads/desenvolvimento"),
    ("REF", "refs/heads/outra"),
    ("REPO", "outro/repo"),
    ("SHA_ALVO", "1f81184"),                     # curto
    ("SHA_ALVO", "A" * 40),                      # maiúsculas
    ("SHA_ALVO", "a" * 41),
    ("SHA_ALVO", "a" * 39 + "g"),                 # não hexadecimal
    ("SHA_ALVO", ""),
    ("SHA_ALVO", "latest"),
    ("CONFIRMACAO", "rollback"),
    ("CONFIRMACAO", "ROLLBACK "),
    ("CONFIRMACAO", ""),
    ("CONFIRMACAO", "sim"),
])
def test_guarda_rollback_bloqueia_entradas_invalidas(tmp_path, campo, valor):
    r = _rodar_guarda(ROLLBACK, "guarda", _env_rollback(**{campo: valor}), tmp_path)
    assert r.returncode != 0
    assert "::error::" in r.stdout


@precisa_bash
def test_guarda_rollback_nao_executa_injecao_pelo_campo_sha(tmp_path):
    marcador = tmp_path / "PWNED"
    sha = SHA_OK + f"; touch {marcador.as_posix()}"
    r = _rodar_guarda(ROLLBACK, "guarda", _env_rollback(SHA_ALVO=sha), tmp_path)
    assert r.returncode != 0
    assert not marcador.exists()


@precisa_bash
def test_script_de_verificacao_de_protecoes_tem_sintaxe_valida():
    r = subprocess.run([BASH, "-n", str(RAIZ / "scripts" / "verificar_protecoes_github.sh")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# --------------------------------------------------------------------------
# Modelos de ruleset
# --------------------------------------------------------------------------
def _ruleset(nome):
    return json.loads((RULESETS / nome).read_text(encoding="utf-8"))


def _nomes_dos_jobs_do_ci():
    return {j["name"] for j in carregar(CI)["jobs"].values()}


def test_ruleset_master_exige_exatamente_os_checks_que_o_ci_produz():
    rs = _ruleset("ruleset-master.json")
    regra = next(r for r in rs["rules"] if r["type"] == "required_status_checks")
    exigidos = {c["context"] for c in regra["parameters"]["required_status_checks"]}
    assert exigidos == _nomes_dos_jobs_do_ci() == {
        "Testes automatizados (pytest)", "Validar build da imagem Docker (sem publicar)"}
    assert {c["integration_id"] for c in regra["parameters"]["required_status_checks"]} == {15368}  # GitHub Actions


def test_ruleset_master_regras_obrigatorias_e_sem_bypass():
    rs = _ruleset("ruleset-master.json")
    tipos = {r["type"] for r in rs["rules"]}
    assert {"deletion", "non_fast_forward", "pull_request", "required_status_checks"} <= tipos
    assert rs["bypass_actors"] == []
    assert rs["conditions"]["ref_name"] == {"include": ["refs/heads/master"], "exclude": []}
    assert rs["target"] == "branch"


def test_rulesets_do_repositorio_entram_desativadas_por_seguranca():
    """Importar ativa de primeira poderia trancar a própria master; o guia manda ativar
    depois de conferir os nomes dos checks."""
    for nome in ("ruleset-master.json", "ruleset-desenvolvimento.json"):
        assert _ruleset(nome)["enforcement"] == "disabled"


def test_ruleset_pr_nao_exige_aprovacao_de_outra_pessoa_conta_unica():
    rs = _ruleset("ruleset-master.json")
    pr = next(r for r in rs["rules"] if r["type"] == "pull_request")["parameters"]
    assert pr["required_approving_review_count"] == 0   # com 1 mantenedor, >=1 travaria todo merge
    assert pr["dismiss_stale_reviews_on_push"] is True


def test_ruleset_desenvolvimento_protege_so_contra_exclusao_e_force_push():
    rs = _ruleset("ruleset-desenvolvimento.json")
    assert {r["type"] for r in rs["rules"]} == {"deletion", "non_fast_forward"}
    assert rs["conditions"]["ref_name"]["include"] == ["refs/heads/desenvolvimento"]


def test_rulesets_ficam_versionaveis_apesar_do_gitignore_de_json():
    saida = subprocess.run(["git", "check-ignore", "-q", "docs/github/ruleset-master.json"], cwd=RAIZ)
    assert saida.returncode == 1, "docs/github/*.json está sendo ignorado pelo .gitignore"


# --------------------------------------------------------------------------
# Falha segura de credenciais (execução real do passo)
# --------------------------------------------------------------------------
@precisa_bash
@pytest.mark.parametrize("arq,job", [(PUBLICAR, "publicar"), (ROLLBACK, "rollback")], ids=["publicar", "rollback"])
@pytest.mark.parametrize("faltando", ["TAILSCALE_AUTHKEY", "TRUENAS_SSH_KEY", "AMBOS"])
def test_credenciais_ausentes_abortam_e_presentes_passam(tmp_path, arq, job, faltando):
    passo = next(p for p in passos(carregar(arq)["jobs"][job]) if p["name"].startswith("Verificar credenciais"))
    base = {"PATH": os.environ.get("PATH", ""), "TAILSCALE_AUTHKEY": "segredo-a", "TRUENAS_SSH_KEY": "segredo-b"}
    ok = subprocess.run([BASH, "-c", passo["run"]], env=base, cwd=tmp_path, capture_output=True, text=True)
    assert ok.returncode == 0 and "segredo" not in ok.stdout + ok.stderr   # nunca exibe o valor
    ruim = dict(base)
    for k in (["TAILSCALE_AUTHKEY", "TRUENAS_SSH_KEY"] if faltando == "AMBOS" else [faltando]):
        ruim[k] = ""
    r = subprocess.run([BASH, "-c", passo["run"]], env=ruim, cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode != 0 and "::error::" in r.stdout
