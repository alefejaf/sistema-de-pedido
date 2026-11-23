# Testes automatizados

Suíte `pytest` do Gerador de Grade. **Não precisa de internet, de credenciais
nem de nenhum PDF real**: tudo é sintético e o Google Sheets é simulado.

## Como rodar

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements-dev.txt

pytest                            # tudo (~2 min; ~35 s sem os testes de UI)
pytest -m "not ui"                # só lógica, sem AppTest (rápido)
pytest -m ui                      # só interface (AppTest)
pytest --cov --cov-report=term-missing   # com cobertura
pytest tests/test_parsing_layouts.py -v  # um arquivo
```

## O que cada arquivo cobre

| Arquivo | Cobre |
|---|---|
| `test_utils.py` | normalização de texto, número BR, moeda, `eh_sim` |
| `test_pdf_text.py` | leitura de PDF real (gerado), divisão em pedidos, loja, data, total, PDF codificado |
| `test_parsing_layouts.py` | **regressão dos 4 layouts de linha de produto**, caixas multi-unidade (Euro Company), formatos colados |
| `test_processing.py` | DE/PARA de lojas e produtos (exato, fuzzy, sem cadastro), todas as validações, grade, preço referência, pendências |
| `test_conciliacao.py` | PDF → base → controle → grade → Excel **recalculado** fecha com o total do PDF |
| `test_excel_export.py` | estrutura/fórmulas/abas dos Excels e ida-e-volta do Excel de configuração |
| `test_config.py` | salvar/carregar DE/PARA, backups (máx. 10), prioridade upload > salvo > padrão |
| `test_auth.py` | hash PBKDF2, matriz de permissões, usuários/inativos/perfis, conta master, `google_sheets` contra planilha simulada |
| `test_permissoes_ui.py` | `app.py` real via `AppTest`: login, perfis, o que cada perfil grava/baixa |
| `test_pendencias_e_admin_ui.py` | aba Pendências e painel admin (ativar/desativar, redefinir senha) |
| `test_clientes_suportados.py` | os 5 clientes (Ultrabox, Bigbox, Costa, Fort, Euro Company) ponta a ponta |
| `test_guardas_do_repositorio.py` | repositório público: sem PDF/segredo/chave; `ci.yml` não publica nem usa secrets |

Apoio: `synth.py` (gerador de pedidos sintéticos e PDF), `helpers.py` (pipeline
completo), `xlsx_eval.py` (recalcula `SUM`/`COUNTIF`/`SUMPRODUCT`, já que o
XlsxWriter não grava valores em cache), `conftest.py` (fixtures e proteções).

## Proteções automáticas (valem para todo teste)

1. `configs/` e `backups_config/` são redirecionados para uma pasta temporária
   — nenhum teste grava nos DE/PARA reais.
2. Conexões de rede para fora de `localhost` falham imediatamente.
3. No fim da sessão confere-se o SHA-256 de `configs/*.xlsx` e
   `config_padrao.xlsx`: se algum mudar, a suíte falha.
4. `google_sheets._planilha` é trocado por uma planilha em memória e
   `_cliente_gspread` (conexão real) é proibido nos testes de autenticação.

## Regras para novos testes

* **Nunca** coloque PDF/planilha comercial real no repositório (ele é
  público). Gere com `synth.py` ou anonimize (loja `ULT99-TESTE`, produtos
  fictícios, valores inventados). `test_guardas_do_repositorio.py` barra PDFs.
* Ao corrigir um defeito de extração, **adicione primeiro** um teste de
  regressão em `test_parsing_layouts.py` (e confirme que ele falha sem a
  correção).
* `xfail(strict=True)` marca um **defeito conhecido**: o teste documenta o
  comportamento errado e *falha* quando alguém o corrige, lembrando de remover o
  `xfail`. Hoje há 12 (todos descritos em `docs/ETAPA3_TESTES_E_CI.md`).
