"""Guardas de segurança do próprio repositório (que é PÚBLICO).

Impedem regressões que expõem dados: PDFs comerciais, chaves privadas,
secrets, e que o CI (ci.yml) publique imagem/faça deploy ou use credenciais
de produção.
"""
import re
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


def _arquivos_versionados():
    try:
        saida = subprocess.run(
            ["git", "ls-files", "-z"], cwd=RAIZ, capture_output=True, check=True,
        ).stdout.decode("utf-8", "replace")
    except Exception:
        pytest.skip("não é um checkout git")
    return [RAIZ / p for p in saida.split("\0") if p]


def _texto(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def test_nenhum_pdf_versionado():
    """Documentos comerciais reais nunca podem entrar num repositório público."""
    pdfs = [p.name for p in _arquivos_versionados() if p.suffix.lower() == ".pdf"]
    assert pdfs == [], f"PDFs versionados: {pdfs}"


def test_nenhum_arquivo_de_segredo_versionado():
    proibidos = []
    for p in _arquivos_versionados():
        rel = p.relative_to(RAIZ).as_posix()
        if rel == ".streamlit/secrets.toml" or (p.name.startswith(".env") and p.name != ".env.example"):
            proibidos.append(rel)
        if p.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
            proibidos.append(rel)
    assert proibidos == []


def test_nenhuma_chave_privada_real_no_repositorio():
    """Aceita só o placeholder do secrets.toml.example."""
    achados = []
    for p in _arquivos_versionados():
        if p.suffix.lower() in {".xlsx", ".png", ".jpg", ".pdf"}:
            continue
        for m in re.finditer(r"-----BEGIN [A-Z ]*PRIVATE KEY-----(.{0,80})", _texto(p), flags=re.S):
            if "SUA_CHAVE_PRIVADA_AQUI" not in m.group(1) and "..." not in m.group(1):
                achados.append(p.relative_to(RAIZ).as_posix())
    assert achados == []


def test_tokens_conhecidos_nao_aparecem():
    padroes = [r"ghp_[A-Za-z0-9]{30,}", r"gho_[A-Za-z0-9]{30,}", r"tskey-[A-Za-z0-9-]{20,}",
               r"AKIA[0-9A-Z]{16}", r"AIza[0-9A-Za-z_-]{35}"]
    achados = []
    for p in _arquivos_versionados():
        if p.suffix.lower() in {".xlsx", ".png", ".jpg", ".pdf"}:
            continue
        t = _texto(p)
        achados += [f"{p.name}:{pat}" for pat in padroes if re.search(pat, t)]
    assert achados == []


def test_dockerignore_continua_excluindo_segredos_e_testes_de_dados():
    di = _texto(RAIZ / ".dockerignore")
    for item in [".streamlit/secrets.toml", ".env", "*.json"]:
        assert item in di


def test_gitignore_continua_protegendo_segredos():
    gi = _texto(RAIZ / ".gitignore")
    for item in [".streamlit/secrets.toml", ".env", "backups_config/"]:
        assert item in gi


def test_dockerfile_nao_copia_testes_nem_secrets_para_a_imagem():
    df = _texto(RAIZ / "Dockerfile")
    copias = [l for l in df.splitlines() if l.strip().upper().startswith("COPY")]
    assert copias, "Dockerfile sem COPY?"
    for linha in copias:
        assert "tests" not in linha and ".streamlit" not in linha and ".env" not in linha


# --------------------------------------------------------------------------
# CI: tem que ser inofensivo
# --------------------------------------------------------------------------
CI = RAIZ / ".github" / "workflows" / "ci.yml"


def _ci():
    """Texto do ci.yml SEM comentários (os comentários citam 'TrueNAS', 'login'
    etc. justamente para dizer que o workflow NÃO faz isso)."""
    assert CI.exists(), "ci.yml não encontrado"
    linhas = []
    for l in _texto(CI).splitlines():
        if l.lstrip().startswith("#"):
            continue
        linhas.append(re.sub(r"\s+#.*$", "", l))
    return "\n".join(linhas)


def test_ci_existe_e_roda_em_pull_request():
    yaml = pytest.importorskip("yaml")
    dados = yaml.safe_load(_ci())
    gatilhos = dados.get(True) or dados.get("on")  # PyYAML lê 'on' como True
    assert "pull_request" in gatilhos


def test_ci_nao_publica_nem_faz_deploy():
    t = _ci()
    proibido = [
        r"push:\s*true", r"packages:\s*write", r"docker/login-action", r"docker login",
        r"ghcr\.io/alefejaf", r"tailscale", r"ssh\s", r"\bssh-", r"midclt", r"truenas",
        r"docker push", r"app\.pull_images", r"TRUENAS_SSH_KEY", r"TAILSCALE_AUTHKEY",
    ]
    achados = [p for p in proibido if re.search(p, t, flags=re.I)]
    assert achados == [], f"ci.yml contém operações proibidas: {achados}"


def test_ci_nao_usa_nenhum_secret():
    assert "secrets." not in _ci().replace("${{ secrets.GITHUB_TOKEN }}", "")


def test_ci_tem_permissoes_somente_leitura():
    yaml = pytest.importorskip("yaml")
    dados = yaml.safe_load(_ci())
    assert dados["permissions"] == {"contents": "read"}


def test_ci_nao_dispara_em_push_na_master():
    yaml = pytest.importorskip("yaml")
    dados = yaml.safe_load(_ci())
    gatilhos = dados.get(True) or dados.get("on")
    push = gatilhos.get("push") if isinstance(gatilhos, dict) else None
    if push:
        assert "master" not in (push.get("branches") or [])

