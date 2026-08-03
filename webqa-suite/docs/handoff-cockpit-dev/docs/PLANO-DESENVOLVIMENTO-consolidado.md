# Plano de desenvolvimento consolidado

**Base medida:** `main` @ `67a8bfe` (pós PR #45) · **Diretório:** `webqa-suite/`

Este documento consolida cinco frentes que nasceram de análises separadas e hoje
competem pelo mesmo backlog. Ele existe porque as frentes se cruzam: o item que
destrava a distribuição da suíte é o mesmo que fecha um defeito da CLI, e o gate de
complexidade que vigia o motor depende de um refactor já previsto na Fase C.

**Relação com os documentos existentes.** Não substitui `docs/PROXIMOS-PASSOS.md`,
que continua sendo a entrada única de quem assume o projeto. Este aqui é o **plano
de execução**: o que fazer, em que ordem, com a prova de por quê. Quando os dois
divergirem, `PROXIMOS-PASSOS.md` manda sobre *regras da casa*; este manda sobre
*sequência de trabalho*.

**Aviso de escopo.** As frentes A a D descrevem trabalho sobre o repositório como ele
é. A frente E descreve um contexto de uso que **ainda não existe** e está marcada como
tal. Nada da frente E deve ser lido como descrição do estado atual.

---

## 1. Como reproduzir todo número deste documento

Não acredite nas tabelas. Rode:

```bash
cd qa-suite/webqa-suite
pip install -r requirements.txt
python -m playwright install chromium

make verify                              # a suíte se auto-verificando

pip install pytest-cov radon             # ainda NÃO estão no requirements
pytest tests -m verification --cov=webqa --cov-report=term
python -m radon cc webqa checks scripts -a -s
ruff check webqa checks tests scripts fixture_target \
  --select C901 --config "lint.mccabe.max-complexity=8" --output-format=concise
```

Mutação: harness no apêndice B do `HANDOFF-Q1-instrumentacao.md`.
Catálogo de testes: `scripts/cockpit.py` (ver frente D).

Os números envelhecem a cada PR. Quem citar, recalcula.

---

## 2. A fotografia medida

### 2.1 Catálogo de testes

Leitura estática por AST de `checks/` e `tests/`, sem importar módulo:

| | Quantidade |
|---|---:|
| Funções de teste | **763** |
| Casos coletáveis (com `@parametrize` expandido) | **848** |
| População `checks/` — julga o alvo | 91 |
| População `tests/` — verifica a suíte | 672 |
| Arquivos varridos | 59 |
| Testes com docstring (contrato escrito) | 376 de 763 |
| Testes de veredito condicional (`pytest.xfail` no corpo) | 22 |
| Testes gerados por Gherkin (invisíveis ao AST de Python) | 1 |

Por nível, derivado de evidência no código (`acceptance` → aceitação;
`browser`/`load` → sistema; arquivo em `checks/` → integração; resto → unidade):

| Nível | Testes | % |
|---|---:|---:|
| Unidade | 666 | 87,3 |
| Integração | 58 | 7,6 |
| Sistema | 38 | 5,0 |
| **Aceitação** | **1** | **0,1** |

### 2.2 Cobertura de código: **77%** de `webqa/`

Medida sob `pytest tests -m verification`, que é o gate `quality-gate` do CI.

**100%:** `gates.py`, `audit.py`, `config.py`, `rede.py`, `navegacao.py`
**97–99%:** `escopo.py`, `estabilidade_html.py`, `telemetria_fasec.py`
**76–94%:** `etiqueta.py`, `sondagem.py` (83), `llm.py`, `report_html.py`
**52–65%:** `http_utils.py`, `sanitize.py`, `auth.py`, `dominio.py`, `trackers.py`, `report.py`
**7%:** `metricas.py`
**0%:** `report_style.py` — contrato visual verbatim, não é lógica; exclusão honesta

**O viés que o número esconde:** o gate roda só a população `verification`. Todo
caminho exercitado por `checks/` aparece descoberto. O segundo job (`validate-target`,
`pytest -m "not load"`) exercita esses caminhos e **não emite cobertura nenhuma**.
Existem duas execuções; a que cobre mais é a que não mede.

### 2.3 Complexidade ciclomática: média **A (3,99)**

207 blocos, índice de manutenibilidade sem nenhum arquivo abaixo de A. O código é
simples na média — isto não é problema estrutural. A cauda, por `ruff` com limiar 8:

| Arquivo | Função | CC |
|---|---|---:|
| `scripts/campanha.py:523` | `render_markdown` | **19** |
| `scripts/estabilidade.py:496` | `main` | 17 |
| `fixture_target/servir.py:242` | `do_GET` | 12 |
| `scripts/audita_design.py:405` | `main` | 11 |
| `webqa/sondagem.py:289` | `sondar` | 10 |
| `checks/functional/test_links.py:43` | `test_links_internos_sem_quebrados` | 10 |
| `webqa/dominio.py:321` | `metadados_exif` | 9 |
| `webqa/etiqueta.py:151` | `preparar` | 9 |
| `checks/lgpd/test_retencao_observavel.py:32` | `_duracao_em_dias` | 9 |
| `scripts/audita_design.py:128` | `criterio_zero_requisicao_externa` | 9 |
| `scripts/campanha.py:402` | `por_dimensao` | 9 |

**Decisão que os números impõem:** com `max-complexity = 10`, **nenhuma função de
`webqa/` é pega** — só `scripts/`. Um gate a 10 não vigia o motor.

### 2.4 Estrutura de dependências: **zero ciclos**

```
folhas: config, gates, http_utils, metricas, navegacao, rede,
        report_style, sanitize, trackers
audit → sanitize                dominio → sanitize
auth  → rede, sanitize          escopo  → auth, rede
llm   → rede                    telemetria_fasec → sanitize
etiqueta → auth, rede           report_html → report_style, trackers
estabilidade_html → report_html, report_style
report → auth, config, dominio, metricas, report_html, sanitize
sondagem → audit, dominio, gates
```

Fan-in máximo `sanitize` (5) — a sanitização na base do grafo é onde deveria estar,
num produto cuja invariante é "achado nasce mascarado". Fan-out máximo `report` (6).

Já há fiscalização automatizada: `test_convencoes.py` (proíbe por AST que sondagem
importe `llm`; exige `fase=` nomeado em `find_secrets`) e `test_fronteira_de_rede.py`
(registro `FRONTEIRAS_DE_REDE`; reprova consumidor não registrado). É `import-linter`
feito à mão, com prova de que cada guarda morde.

**Nada a fazer nesta rodada.** Backlog: generalizar de casos para propriedade
(aciclicidade + contrato de camadas).

### 2.5 Mutação

| Módulo | Viáveis | Mortos | Sobreviveram | Score |
|---|---:|---:|---:|---:|
| `webqa/escopo.py` | 26 | 23 | 3 | **88,5%** |
| `webqa/sondagem.py` | 82 | 49 | 33 | **59,8%** |

O repositório já *pratica* mutação — em 8 lugares, todos sobre os **detectores** (cada
guarda de AST tem um teste plantando violação e verificando que morde). O código de
produção não era mutado até esta medição.

### 2.6 Tipos de teste entregues

Contra o mapa de referência: **16 de 20 categorias**, sendo 11 completas.

| Família | Categoria | Estado |
|---|---|---|
| Funcionais | Unitários | ✅ 666 |
| | Integração | ✅ 58 |
| | Sistema | ✅ 38 |
| | Aceitação | ⚠️ 1 cenário |
| | **Regressão** | ❌ ausente |
| Não-funcionais | Performance | ✅ |
| | Carga | ⚠️ rajada leve (30 req / 10 conc.) |
| | **Estresse** | ⛔ fora de escopo por desenho |
| | Segurança | ✅ 16 + motor Fase C |
| | Usabilidade | ✅ 16 |
| | **Compatibilidade** | ❌ só Chromium |
| | Confiabilidade | ✅ ledger de estabilidade |
| Manutenção | Fumaça | ✅ |
| | Sanidade | ✅ `make verify` |
| | **Confirmação** | ❌ ausente |
| | Instalação | ✅ `vps_smoke.sh` + `docker/` |
| Métricas | **Cobertura** | ❌ não instrumentada |
| | Mutação | ⚠️ só sobre detectores |
| Estática | **Complexidade** | ❌ não instrumentada |
| | Dependências | ✅ e acima da média |

**As ausências não são aleatórias.** Duas causas:
*falta de memória entre execuções* explica regressão e confirmação; *falta de
instrumentação* explica cobertura e complexidade. Estresse é decisão de escopo
(uma suíte cujo lema é "detectar, nunca explorar" não embute gerador de tráfego
capaz de derrubar o alvo). Compatibilidade é o único gap sem justificativa
arquitetural — Playwright já traz os três engines.

---

## 3. Defeitos abertos, com prova

Cinco. Todos verificados em execução, nenhum é hipótese.

### D1 · IPv6 quebra a URL pinada — falha silenciosa

`sondagem.py:320` faz `sorted(ips_pinados)[0]` sobre **strings**. Num host dual-stack
a ordenação lexicográfica pode eleger o IPv6, e `_url_pinada` (`:221`) monta
`f"{scheme}://{ip}:{porta}"` sem colchetes:

```python
sorted(['2001:db8::1', '93.184.216.34'])[0]  → '2001:db8::1'
→ https://2001:db8::1:443/.env   # malformado
```

Vira `_FALHA_DE_REDE`, marca o run inconclusivo, e não diz por quê.

### D2 · `procedencia` é campo órfão

Preenchido nas 5 entradas de `data/caminhos-sensiveis.yaml` (OWASP WSTG-CONF-004,
CWE-538, CWE-527), carregado em `CaminhoSensivel`, e **nunca chega ao `Finding`**.
O valor de compliance já existe no dado curado; falta propagar.

### D3 · A CLI termina em traceback no caminho de erro mais comum

```
$ python -m webqa.sondagem --alvo https://naoautorizado.exemplo --executar
  File "webqa/gates.py", line 115, in require_escopo
    pytest.skip(...)
Skipped: [gate:escopo] https://naoautorizado.exemplo fora do escopo autorizado…
```

`require_escopo` e `require_discovery` usam `pytest.skip()`, que fora de um teste
levanta `Skipped` sem tratamento. A mensagem existe, é boa, e nunca chega ao usuário.

**Não é bypass de governança.** `sondar()` chama `require_discovery()` internamente —
defesa em profundidade funciona. O risco é contrato de erro e usabilidade.

### D4 · Dataclasses de governança sem prova de imutabilidade

Mutar `@dataclass(frozen=True)` → `frozen=False` em `escopo.py:76` e `:112` sobrevive
à suíte inteira. Um registro de autorização mutável em memória anula a premissa da
Fase C: o escopo tem de ser foto congelada no carregamento.

### D5 · Abortos e descartes não deixam rastro

- `posse-divergente` retorna **antes** de o `AuditLog` existir
- `kill-switch` sai do laço sem registrar
- descarte por soft-404 faz `return None` — o log mostra `status=200`, não nasce
  finding, e não há linha dizendo por quê (bug ou heurística?)

---

## 4. As frentes

### Frente A — Fase C: correção e resiliência do motor

| ID | O que | Arquivos | CODEOWNERS |
|---|---|---|---|
| **A1** | D1 (IPv6 + escolha de família por `ip_address().version`) e D2 (`procedencia` → `Finding` → `report.py`) | `sondagem.py`, `dominio.py`, `report.py` | não |
| **A2** | Circuit breaker (N recuos/erros consecutivos → `abortado_por="circuit-breaker"`); `evento="descartado:soft-404"`; registrar abortos no `AuditLog` (criar log **depois de `require_escopo`, antes de `verificar_posse`**); `httpx.Timeout` granular | `sondagem.py`, `audit.py` | não |
| **A3** | `verificar_posse` distingue as 4 causas hoje colapsadas em `frozenset()` vazio (takeover, host não listado, snapshot vazio, resolução falhou) | `escopo.py` | ⚠️ **sim** |
| **A4** | Extrair funções puras de `sondar`: `avaliar_resposta_em_finding`, `executar_fallback_get`, `calcular_espera_backoff` | `sondagem.py` | não |

**A2 exige um método novo no `AuditLog`.** `registrar()` pede `url`/`metodo`, e a
docstring do módulo fixa "uma linha por requisição ativa". Aborto não é requisição:
precisa de `registrar_evento()` separado, com a docstring atualizada.

**A3 não pode importar `webqa.audit`.** `escopo.py` já é o quarto consumidor da
fronteira de rede; um import novo quebraria `test_fronteira_de_rede.py`. O motivo do
aborto sai por canal separado, consumido por `sondagem`.

**A4 fica por último de propósito.** Ele move as mesmas linhas que a prova por mutação
de A2 vai cobrir; juntar os dois torna o diff de correção indistinguível do de higiene.

### Frente B — Instrumentação de qualidade

| ID | O que | Esforço |
|---|---|---|
| **B1** | D4: varredura dinâmica de dataclasses do módulo **+** um teste de reatribuição real | ~30 linhas, 1 arquivo |
| **B2** | D3: `main()` pré-checa `escopo.esta_no_escopo(alvo)` (predicado puro, sem pytest); 3 testes de contrato de erro | ~50 linhas |
| **B3** | `C901` no `[tool.ruff.lint]` com `max-complexity = 8` + `per-file-ignores` datado para `scripts/`, `checks/`, `fixture_target/` | 5 linhas + refactor |
| **B4** | `pytest-cov` no `requirements.txt`; `--cov` nos **dois** jobs; `--cov-fail-under=75` só no determinístico | 5 linhas |
| **B5** | `scripts/mutar.py` + workflow agendado com **ambiente explicitamente limpo** | ~80 linhas |
| **B6** | Bordas: 2xx em 299/300 (`sondagem.py:274`), porta não-padrão no IP pinning (`:218`) | ~20 linhas |

**Armadilhas de B1** — três versões deste teste circularam em revisão e nenhuma
funcionava:

1. `EntradaEscopo(url=…)` — **não existe campo `url`**. São `origem`,
   `autorizado_por`, `data`, `evidencia`, `ambiente`, todos obrigatórios.
2. `pytest.raises(TypeError)` — dataclass congelada levanta **`FrozenInstanceError`**,
   subclasse de `AttributeError`.
3. Construir o objeto **dentro** do `with pytest.raises(...)` — a construção com
   kwargs errados levanta `TypeError` antes da reatribuição, o `raises` captura,
   **o teste passa verde e continuaria passando com `frozen=False`**. Verificado em
   execução.

**Por que B3 usa 8 e não 10:** medido, a 10 nenhuma função de `webqa/` é pega. Sobram
três a 8 — `sondar` (10), `metadados_exif` (9), `preparar` (9). `sondar` resolve
sozinho quando A4 entrar.

**Por que B4 põe piso só no primeiro job:** `quality-gate` é determinístico;
`validate-target` depende de site publicado responder. Piso lá transformaria
instabilidade de rede em reprovação de PR.

**Por que o ambiente limpo em B5:** mutação **altera a lógica dos gates de propósito**.
Um mutante que inverta `discovery_authorized()` roda com a suíte inteira. A fixture
autouse `_ambiente_limpo` já apaga as variáveis, mas é local a um arquivo de teste, e
a mutação pode atingir a própria lógica que a fixture exercita.

```yaml
env:
  WEBQA_DISCOVERY_AUTHORIZED: ""
  WEBQA_ACTIVE_PROBES_AUTHORIZED: ""
  WEBQA_LOAD_AUTHORIZED: ""
run: |
  test -z "$WEBQA_DISCOVERY_AUTHORIZED" || { echo "gate setado no job de mutação"; exit 1; }
```

### Frente C — Tipos de teste ausentes

| ID | O que | Por quê |
|---|---|---|
| **C1** | **Regressão**: `baseline.json` versionado por alvo; run compara e emite "achados novos desde o último baseline" | sem isso não há como distinguir "sempre esteve quebrado" de "quebrou ontem" |
| **C2** | **Confirmação**: reexecutar apenas o que falhou no baseline, para confirmar correção | mesma raiz de C1 — cai junto |
| **C3** | **Compatibilidade**: parametrizar a fixture de navegador em `conftest.py:116` por engine (`chromium`, `firefox`, `webkit`), com skip honesto por engine ausente | único gap sem justificativa arquitetural; Playwright já traz os três |
| **C4** | **Aceitação**: ampliar `checks/acceptance/features/` — hoje 1 cenário para 666 unitários | é o único nível que responde "faz o que deveria?" |
| — | **Estresse** | ⛔ **fora de escopo, declarado.** `test_performance.py:32` já diz: rajada leve; para carga real, ferramenta dedicada. Registrar em `ESCOPO-EAP.md` como exclusão consciente, não como pendência |

**C1 e C2 mudam uma propriedade do sistema.** A suíte é hoje deliberadamente **sem
estado entre execuções** — virtude de desenho. Baseline introduz memória. A forma de
introduzir sem perder a virtude: o baseline é **artefato versionado no repositório do
projeto** (revisável em PR), não cache implícito. Um achado só some do laudo se alguém
aprovar a mudança do baseline.

**C3 tem custo de tempo de CI**, não de código: três engines triplicam a duração da
dimensão browser. Recomendo `chromium` no PR e a matriz completa no noturno.

### Frente D — Cockpit de testes

O cockpit existe e funciona (leitura por AST de qualquer repositório, reconciliação
com `report/summary.json`, HTML autocontido), mas **ainda não está no repositório**.

| ID | O que | Depende de |
|---|---|---|
| **D1k** | Incorporar `scripts/cockpit.py` + `scripts/catalogo.py`, alvo `make cockpit`, testes de convenção | nada |
| **D2k** | **Selo de modo + `gates_ativos`**: os 4 modos (inventário, passivo, carga, sondagem ativa) já existem na suíte; o painel não os mostra. `gates_ativos: []` sereno; gate ativo ruidoso | nada |
| **D3k** | **Procedência como espinha**: `repo/ramo/commit` sai de linha de cabeçalho e vira campo estrutural de qualquer agregado | nada |
| **D4k** | **Estado de incomparabilidade**: quando faltam eixos, o painel diz **qual** dos motivos, nunca célula vazia | nada |
| **D5k** | Blocos opcionais no JSON (`cobertura_codigo`, `mutacao`, `complexidade`) com degradação honesta — ausência nunca vira zero | B3, B4, B5 |
| **D6k** | `caminhos_sensiveis_hash` no laudo | serialização do `ResultadoSondagem` (backlog Fase C) |

**Por que D2k vem antes de D3k**, contra a intuição: o eixo de risco é propriedade de
**qualquer** execução, inclusive de um projeto só, e é o de maior consequência de
segurança. Misturar os modos é o erro que faz o operador aprender a aprovar sem ler.

**Por que D4k não pode esperar multi-projeto:** a incomparabilidade não depende de
haver muitos projetos, depende de haver eixos que faltam — o que já acontece hoje.
Um painel que mostra célula vazia onde falta dado convida o leitor a preencher a
lacuna mentalmente. É o "verde por omissão" que o painel inteiro existe para impedir.

**Contra um erro que circulou em revisão:** o cockpit mede *cobertura de execução de
testes* (quantos dos 763 rodaram). **Não mede cobertura de código.** As duas
compartilham a palavra e mais nada. B4 continua sendo trabalho real.

### Frente E — A suíte como padrão distribuível ⚠️ prospectivo

**Nada desta frente existe.** Está aqui porque muda a prioridade de B2 — o entrypoint
é pré-requisito de tudo abaixo.

| ID | O que | Estado |
|---|---|---|
| **E1** | `[project.scripts]` no `pyproject.toml` — entrypoint estável | ❌ não existe |
| **E2** | Pacote versionado e publicável | ❌ |
| **E3** | Workflow reutilizável (`workflow_call`) / composite action | ❌ |
| **E4** | Procedência obrigatória no laudo: `padrao.versao`, `commit`, `caminhos_sensiveis_hash`, `modo`, `gates_ativos` | ❌ |
| **E5** | Comparador entre projetos, que recusa alinhar laudos de réguas diferentes | ❌ |

**A regra de fronteira, se esta frente for adiante:** o projeto consumidor contribui
**configuração e autorização, nunca código de verificação**. `data/caminhos-sensiveis.yaml`
não pode ser editável pelo projeto — a proteção de CODEOWNERS não viaja com cópia de
pasta, e uma lista editada em silêncio produz "0 achados" indistinguível de um alvo
seguro.

Detalhamento completo em `ARQUITETURA-suite-como-padrao-em-harness.md`.

---

## 5. Sequência consolidada

Ordem por dependência e por risco, não por frente.

| # | PR | Conteúdo | Bloqueia |
|---|---|---|---|
| 1 | **A1** | IPv6 + `procedencia` órfã | — |
| 2 | **B1** | Imutabilidade das dataclasses (D4) | — |
| 3 | **B2** | Contrato de erro da CLI (D3) | **E1–E5** |
| 4 | **A2** | Circuit breaker, log de descarte e abortos, timeout granular (D5) | — |
| 5 | **B4** | `--cov` nos dois jobs | D5k |
| 6 | **B3** | `C901` limiar 8 | D5k |
| 7 | **D1k** | Cockpit no repositório | D2k–D6k |
| 8 | **D2k + D4k** | Selo de modo e estado de incomparabilidade | — |
| 9 | **B6** | Bordas do motor (2xx, porta) | — |
| 10 | **A4** | Extração de funções puras de `sondar` | fecha B3 em `webqa/` |
| 11 | **B5** | Job de mutação escopado | D5k |
| 12 | **A3** | Diagnóstico de posse ⚠️ CODEOWNERS | — |
| 13 | **C3** | Compatibilidade multi-engine | — |
| 14 | **C1 + C2** | Baseline e confirmação | — |
| 15 | **D3k** | Procedência como espinha | E4 |
| 16 | **C4** | Ampliar aceitação | — |

**Racional dos três primeiros.** A1 é pura correção (dois defeitos que causam falha
silenciosa hoje) e o menor diff — merece ir sozinho. B1 fecha a única quebra de
invariante de segurança do lote e não depende de nada. B2 sobe para o terceiro lugar
porque é o único item que destrava uma frente inteira.

**Nenhum dos PRs 1 a 11 toca CODEOWNERS.** Os quatro caminhos protegidos
(`webqa/gates.py`, `webqa/escopo.py`, `data/caminhos-sensiveis.yaml`,
`tests/test_fase_c_travada.py`) só aparecem em A3. Se você se pegar precisando editar
um deles antes disso, **pare e reveja** — provavelmente o problema está sendo resolvido
no lugar errado.

---

## 6. Riscos novos registrados

Numeração continua a de `docs/RISCOS.md`.

| ID | Risco | Mitigação |
|---|---|---|
| **R-Q1** | Cobertura de 77% cai sem sinal a cada PR | B4 com `--cov-fail-under` |
| **R-Q2** | Score de mutação regride e ninguém percebe | B5; meta declarada de zero sobreviventes em `escopo.py` e `gates.py`, com sobrevivente equivalente **justificado no PR**, nunca em silêncio |
| **R-Q3** | Job de mutação com gate no ambiente dispara tráfego real | denylist `WEBQA_*` + `fail_on_denied_env` no job |
| **R-Q4** | Baseline (C1) vira cache implícito e achado some do laudo | baseline é artefato versionado, revisável em PR; achado só sai com aprovação |
| **R-Q5** | Matriz de 3 engines triplica o tempo de CI e o time desliga a dimensão | `chromium` no PR, matriz completa só no noturno |
| **R-Q6** | Cockpit mostra célula vazia e o leitor lê como aprovação | D4k: ausência sempre nomeia o motivo |
| **R-Q7** | Laudos de versões diferentes comparados como iguais | E4; agregação recusa misturar versões |

---

## 7. O que **não** fazer

Descartado com motivo, para não ser reintroduzido de boa-fé.

| Item | Por quê |
|---|---|
| Probes adaptativos / expansão condicional da lista curada | quebra o invariante `executado × esperado` (denominador móvel) e degenera a lista em wordlist dinâmica |
| Triagem de achados por LLM | `tests/test_convencoes.py:212::test_modulo_de_sondagem_nao_importa_llm` proíbe por AST |
| Canary de egresso em `ifconfig.me` | host fora do `escopo-autorizado.yaml`. Se quiser pré-check, `HEAD /` no próprio alvo |
| Limiar de 90% de caminhos sondados para "inconclusivo" | `ResultadoSondagem.inconclusivo` já exige **100%** — o proposto é mais fraco |
| `radon`/`xenon` no CI | dependência nova para o que o `ruff` já faz embutido |
| `vulture` para complexidade | `vulture` detecta código morto; métricas trocadas |
| `.pre-commit-config.yaml` só para o C901 | repo não tem pre-commit; deixa de ser "uma linha" e vira arquivo + dependência novos |
| Golden master do `stdout` da CLI | congelaria a listagem dos caminhos curados; todo PR de governança passaria a mexer num `.txt` de snapshot |
| Script cruzando cobertura com `caminhos-sensiveis.yaml` | o arquivo tem **5 entradas**; 100 linhas de script para 5 itens tem ROI negativo |
| Teste de append-only do `AuditLog` | **já existe**: `tests/test_audit_fase_c.py:66` |
| Teste de "escopo recusa entrada sem data" | `data` é obrigatório em `EntradaEscopo` e `carregar()` faz `a["data"]` direto — impossível construir sem |
| `respx` + `freezegun` | contra stdlib-first; `MockTransport` + `dormir` injetado + `getaddrinfo` dublado já cobrem, em milissegundos |
| Cache/`state/` de índice de repositório | a suíte é sem estado entre execuções por desenho; se houver cache, carrega o hash do que indexou e se invalida sozinho |
| Correlação elevando severidade automaticamente a "crítico" | laudo especulativo; severidade vem do caminho curado, decidida por humano. Aceito como anotação, nunca auto-escalonamento |
| WAF fingerprint virando `Finding` | falso-negativo por design. Header no `AuditLog`, ok; `Finding`, não |

### Identificadores que não existem no repositório

Apareceram em pareceres de revisão. Verificados um a um:

`requirements-dev.txt` · `.coveragerc` · `make test-fasec` · `TETO_CORPO_FASE_C` ·
`EscopoAutorizado` · `data_autorizacao` · `escopo.hosts_alvo` · `gerar_relatorio` ·
`dry-run-surface.json` · binário `webqa` no PATH

Correções úteis: a CLI é `python -m webqa.sondagem` (não há `[project.scripts]`);
`origem_de` mora em **`webqa/auth.py:59`**, não em `escopo.py`; a classe é
`EntradaEscopo` com campo `data`; o atributo é `entradas`, e já é `tuple`.

---

## 8. Glossário

- **Cobertura de código** — quais linhas de `webqa/` uma execução atinge. Vem do
  `coverage.py`. **Não instrumentada** hoje.
- **Cobertura de execução de testes** — quantos dos 763 testes catalogados um run
  coletou. Vem do cockpit. Métrica **diferente**, apesar do nome parecido.
- **Score de mutação** — % de defeitos plantados que a suíte reprova. Mede a força das
  asserções; cobertura mede só se a linha foi visitada.
- **Mutante sobrevivente** — defeito plantado com a suíte ainda verde. Ou falta teste,
  ou falta asserção, ou o mutante é *equivalente* — e essa terceira hipótese precisa
  ser argumentada, não presumida.
- **População `verification`** (`tests/`) — verifica a própria suíte. Falha aqui é bug
  na ferramenta.
- **População de checks** (`checks/`) — valida o alvo auditado. Falha aqui é achado
  sobre o alvo. **As duas nunca se somam.**
- **Modo** — inventário (rede: não), passivo, carga, sondagem ativa. Naturezas de
  risco diferentes; a UI e a harness precisam distingui-los.
- **Gate** — trava fail-closed por variável de ambiente. Ausência de autorização não é
  defeito do alvo: vira skip nos testes, e (após B2) erro claro na CLI.
- **CODEOWNERS** — `webqa/gates.py`, `webqa/escopo.py`, `data/caminhos-sensiveis.yaml`,
  `tests/test_fase_c_travada.py`. Exigem revisão nomeada.
