# Etapa 3 — Testes automatizados e CI isolado

Branch: `desenvolvimento` (a `master` e o `docker-publish.yml` **não foram tocados**).
Nenhum arquivo de código do sistema (`app.py`, `grade_app/`), `Dockerfile`,
`requirements.txt`, `configs/` ou `config_padrao.xlsx` foi alterado.

## 1. Arquivos criados / modificados

**Modificado (1):** `.gitignore` — +7 linhas ignorando artefatos de cobertura
(`.coverage`, `coverage.xml`, `htmlcov/`, `resultado-testes.xml`).

**Criados:**

| Arquivo | Função |
|---|---|
| `.github/workflows/ci.yml` | CI: testes (Python 3.11) + build Docker **sem publicar** + 2 smoke tests |
| `pytest.ini` | configuração do pytest |
| `.coveragerc` | cobertura (linhas + ramos) |
| `requirements-dev.txt` | pytest, pytest-cov, PyYAML (não vão para a imagem Docker) |
| `tests/` (17 arquivos) | suíte — ver `tests/README.md` |
| `docs/ETAPA3_TESTES_E_CI.md` | este documento |

## 2. O que o CI faz (e não faz)

* Gatilhos: `pull_request`, push em `desenvolvimento`, manual. **Não** roda em push na `master`.
* `permissions: contents: read`. **Nenhum** `secrets.*`, login em registry, Tailscale, SSH ou TrueNAS.
* Job `testes`: Python 3.11 (= imagem), `pytest --cov --cov-fail-under=85`, anexa relatórios.
* Job `docker-build`: `push: false` + `load: true` (imagem fica só no runner);
  smoke 1 roda o app **dentro da imagem, sem rede e sem secrets** e exige que o
  acesso fique bloqueado; smoke 2 confere `/_stcore/health`.
* `tests/test_guardas_do_repositorio.py` falha se o `ci.yml` ganhar publicação,
  secrets ou permissão de escrita.

## 3. Clientes realmente suportados

Cinco, todos exercitados ponta a ponta com PDF sintético: **Ultrabox, Bigbox,
Costa, Fort e Euro Company**. O parser de itens é único; o que muda por cliente é
o cabeçalho da loja (ULT/BIG: código no PDF; Costa: `COSTA MULTICANAL … LOJA X`;
Fort: `DF-FORT ATACAD n LOJA`), o DE/PARA e as colunas da grade.

**Euro Company** é suportada: layout de linha igual ao dos demais, com caixas
`CX 18/24/9/12` (regressão do commit `1f81184`), lojas ULT/BIG compartilhadas com
Ultrabox, 43 entradas de produto (todas resolvem para si mesmas). Diferença
importante: **não existe `configs/config_eurocompany.xlsx` no repositório** — roda
com o padrão do código e qualquer edição fica só no volume de produção.

## 4. Achados (todos documentados em testes, nada foi corrigido)

| # | Achado | Gravidade | Teste |
|---|---|---|---|
| 1 | **`MACA GALA 1KG` nunca é usada** em Bigbox/Costa/Fort (config empacotada) e nos padrões do código: `MACA GALA` vem antes e vence a busca por substring. O item sai como `MACA GALA KG`. | Média (afeta nome/unidade na grade) | `xfail` em `test_processing.py`, `test_clientes_suportados.py` |
| 2 | **A tela de edição grava config + cria backup a cada execução** (qualquer clique/upload) para admin/usuário. Como só 10 backups são mantidos, o histórico útil é varrido em 10 interações. | Média | `test_cada_execucao_da_tela_de_editor_gera_backup_caracterizacao` |
| 3 | **Config salva ilegível é sobrescrita pelo padrão** na mesma execução (por um editor). O arquivo corrompido vai ao backup, que rota rápido (item 2). Visualizador não grava. | Média | `test_config_salva_ilegivel_e_sobrescrita_pelo_padrao_caracterizacao` |
| 4 | `BB-VIPIRES` (DE/PARA padrão) **nunca é extraído**: `extrair_loja` exige `LLL99-XXX`. Pode ser código morto ou o PDF real ter outro formato — conferir com PDF real. | Baixa/Verificar | `xfail` |
| 5 | Preços diferentes entre lojas: a NOTA FINAL usa **um preço por produto**; o total do Excel (`SUMPRODUCT`) deixa de bater com a soma dos PDFs (o sistema avisa com ATENÇÃO). | Baixa (já sinalizado) | `test_diferenca_de_preco_entre_lojas_...` |
| 6 | `contar_indicios_produtos` não pontua o layout "visual"; só afeta a escolha entre PyMuPDF/pdfplumber. | Baixa | `xfail` |
| 7 | Itens 100% idênticos (produto/emb/qtd/preço/valor) no mesmo pedido são colapsados pela deduplicação; o controle de extração sinaliza CRÍTICO. | Baixa | caracterização |
| 8 | Conta master com perfil inválido vira `admin` (fail-open, diferente dos usuários da planilha). | Baixa/informativo | caracterização |
| 9 | `st.success(...)` seguido de `st.rerun()` (restaurar padrão, adicionar pendências): a mensagem nunca aparece. | Cosmético | comentário no teste |
| 10 | **Dependências sem versão fixa**: a imagem de hoje resolve `streamlit 1.67 / pandas 3.1.1`; a documentação de agosto citava `pandas 3.0.5`. O código já emite avisos de depreciação (`use_container_width`, `fillna("")` com `float64`, `drop(inplace=True)`) que viram erro em versões futuras. | **Alta (risco futuro)** | avisos na suíte |
| 11 | Auditoria anterior: push na `master` = deploy; `workflow_dispatch` vale para qualquer branch (**não alterado nesta etapa**). | Alta | etapa 4 |

## 5. Validação de que os testes detectam defeitos

Teste de mutação manual em cópia temporária: 12 defeitos injetados (reverter a
correção Euro, visualizador baixando/editando, inativo logando, hash sempre
aceito, tolerância do total, fórmula `SUMPRODUCT`, total do dia duplicado,
limite de backups, backup removido, prioridade de preço, senha no log) →
**12/12 detectados**.

## 6. Como reverter esta etapa

Nada foi commitado nem publicado. Para descartar: `git checkout -- .gitignore`
e remover `tests/ docs/ pytest.ini .coveragerc requirements-dev.txt
.github/workflows/ci.yml`. Nenhum dado de produção foi tocado.
