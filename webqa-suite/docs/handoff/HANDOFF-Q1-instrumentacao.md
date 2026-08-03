# Handoff — Fatia Q1: instrumentação de qualidade

**Repositório:** `danzeroum/qa-suite` · **Base:** `main` @ `67a8bfe` · **Diretório de trabalho:** `webqa-suite/`

Bem-vindo(a). Este documento é auto-contido: te dá o motivo do trabalho, a evidência
que o justifica, o que mudar linha a linha, como provar que a mudança morde, e o que
**não** fazer. Leia até a seção 7 antes de escrever código — metade do valor deste
handoff está no que foi descartado.

---

## 0. O trabalho em uma frase

Os testes deste repositório são bons. **Ninguém está medindo se são suficientes** —
e quando medimos, apareceram quatro buracos concretos. Esta fatia instala os
instrumentos e tapa os buracos. Não há feature nova aqui.

---

## 1. A regra que não se negocia

Herda inteira do `docs/handoff/FASE-C-HANDOFF.md`. Repetindo o essencial, porque
esta fatia toca o motor de sondagem:

1. **Detectar e reportar, nunca explorar.** Nada nesta fatia pode ler corpo de
   resposta, seguir redirect, ampliar a lista curada ou afrouxar um gate.
2. **Escopo fechado.** Nenhum teste desta fatia toca rede real. O padrão do repo é
   `httpx.MockTransport` + `getaddrinfo` dublado.
3. **Se um PR seu enfraquecer uma invariante, o PR está errado — não o teste que o
   reprovou.**

Uma regra nova, específica desta fatia:

4. **Teste de mutação altera a lógica dos gates de propósito.** O job que o roda
   nunca pode ter `WEBQA_DISCOVERY_AUTHORIZED` nem `WEBQA_ACTIVE_PROBES_AUTHORIZED`
   no ambiente. Ver Q5.

---

## 2. Como reproduzir tudo que está aqui

Não acredite nos números deste documento. Rode:

```bash
git clone https://github.com/danzeroum/qa-suite
cd qa-suite/webqa-suite
pip install -r requirements.txt
python -m playwright install chromium

make verify                        # a suíte se auto-verificando (deve ficar verde)

# cobertura (pytest-cov ainda não está no requirements — instale à mão para conferir)
pip install pytest-cov radon
pytest tests -m verification --cov=webqa --cov-report=term

# complexidade
ruff check webqa checks scripts fixture_target \
  --select C901 --config "lint.mccabe.max-complexity=8" --output-format=concise
```

Para o teste de mutação, use o harness do **Apêndice B** deste documento.

---

## 3. O que foi medido (e o que os números querem dizer)

### 3.1 Cobertura de código: **77%** de `webqa/`

Medido sob `pytest tests -m verification`, que é exatamente o gate `quality-gate`
do CI — o job que bloqueia merge.

| Módulo | Cobertura | Nota |
|---|---:|---|
| `gates.py`, `audit.py`, `config.py`, `rede.py`, `navegacao.py` | 100% | a trava da Fase C está coberta |
| `escopo.py` | 97% | |
| `estabilidade_html.py` | 99% | |
| `telemetria_fasec.py` | 97% | |
| `etiqueta.py` | 94% | |
| `sondagem.py` | 83% | o que falta é `main()` (linhas 365–399) |
| `llm.py` | 82% | |
| `report_html.py` | 76% | |
| `http_utils.py` | 65% | |
| `sanitize.py` | 64% | |
| `auth.py` | 60% | |
| `dominio.py` | 58% | |
| `trackers.py` | 54% | |
| `report.py` | 52% | |
| `metricas.py` | **7%** | alimenta o campo `metricas` do `summary.json` |
| `report_style.py` | 0% | é contrato visual verbatim, não lógica — ignorar |

**O viés que o número esconde.** O gate roda **só a população `verification`**. Todo
caminho exercitado por `checks/` contra um alvo publicado aparece descoberto. O
segundo job do CI (`validate-target`, `pytest -m "not load"`) exercita esses
caminhos e **não produz número de cobertura nenhum**. Existem duas execuções; a que
cobre mais é a que não mede. É isso que Q4 corrige.

### 3.2 Complexidade ciclomática: média **A (3,99)**, com cauda

`radon cc` sobre 207 blocos. Índice de manutenibilidade: nenhum arquivo abaixo de A.
Ou seja, o código é simples na média — isto não é um problema estrutural.

A cauda medida pelo `ruff --select C901 --config "lint.mccabe.max-complexity=8"`
(11 achados no repo inteiro; note que o mccabe do ruff conta um pouco mais baixo
que o radon):

| Arquivo | Função | CC |
|---|---|---:|
| `webqa/sondagem.py:289` | `sondar` | 10 |
| `webqa/dominio.py:321` | `metadados_exif` | 9 |
| `webqa/etiqueta.py:151` | `PoliteFetcher.preparar` | 9 |
| `checks/functional/test_links.py:43` | `test_links_internos_sem_quebrados` | 10 |
| `checks/lgpd/test_retencao_observavel.py:32` | `_duracao_em_dias` | 9 |
| `scripts/campanha.py:523` | `render_markdown` | **19** |
| `scripts/estabilidade.py:496` | `main` | 17 |
| `scripts/audita_design.py:405` | `main` | 11 |
| `scripts/audita_design.py:128` | `criterio_zero_requisicao_externa` | 9 |
| `scripts/campanha.py:402` | `por_dimensao` | 9 |
| `fixture_target/servir.py:242` | `do_GET` | 12 |

**Detalhe que muda a decisão:** com `max-complexity = 10`, **nenhuma função de
`webqa/` é pega** — só `scripts/`. Um gate a 10 não vigia o motor. Por isso Q3 usa 8.

### 3.3 Estrutura de dependência: **saudável, e já fiscalizada**

Grafo interno de `webqa/`, levantado por AST:

```
folhas (zero deps internas): config, gates, http_utils, metricas,
                             navegacao, rede, report_style, sanitize, trackers
audit   → sanitize                 dominio → sanitize
auth    → rede, sanitize           escopo  → auth, rede
llm     → rede                     telemetria_fasec → sanitize
etiqueta→ auth, rede               report_html → report_style, trackers
estabilidade_html → report_html, report_style
report  → auth, config, dominio, metricas, report_html, sanitize
sondagem→ audit, dominio, gates
```

**Zero ciclos de import.** Fan-in máximo `sanitize` (5) — a sanitização na base do
grafo é exatamente onde deveria estar, num produto cuja invariante é "achado nasce
mascarado". Fan-out máximo `report` (6).

E já há fiscalização automatizada, escrita à mão:
- `tests/test_convencoes.py` — proíbe por AST que módulo de sondagem importe `llm`;
  exige `fase=` nomeado em toda chamada a `find_secrets`.
- `tests/test_fronteira_de_rede.py` — registro `FRONTEIRAS_DE_REDE`; falha se um
  módulo consumir a fronteira de rede sem estar registrado, nomeando o teste que
  exercita o ramo.

Isso é `import-linter` (contratos *forbidden* e *layers*) feito à mão, e cada guarda
tem teste provando que morde caso plantado. **Nada a fazer nesta fatia.** Fica como
backlog: generalizar de casos para propriedade (aciclicidade + contrato de camadas).

### 3.4 Mutação: **88,5%** em `escopo.py`, **59,8%** em `sondagem.py`

Medido com o harness do Apêndice B (operadores: comparadores, `and`/`or`, `not`,
booleanos, constantes numéricas).

| Módulo | Mutantes viáveis | Mortos | Sobreviveram | Score |
|---|---:|---:|---:|---:|
| `webqa/escopo.py` | 26 | 23 | 3 | **88,5%** |
| `webqa/sondagem.py` | 82 | 49 | 33 | **59,8%** |

Os sobreviventes que importam, e que geram Q1, Q2 e Q6:

| Onde | Mutação | Por que sobreviveu |
|---|---|---|
| `escopo.py:76` e `:112` | `@dataclass(frozen=True)` → `frozen=False` | **nenhum teste tenta reatribuir campo** |
| `sondagem.py:365–399` | várias | `main()` não é chamado por teste nenhum |
| `sondagem.py:274` | `200 <= status < 300` → `<= 300` | nenhum teste fixa a borda superior do 2xx |
| `sondagem.py:218` | `443 if https else 80` → `444` | nenhum teste usa porta não-padrão nem `http` |

---

## 4. Mapa do que você vai tocar

| Arquivo | CODEOWNERS? | O que muda |
|---|---|---|
| `tests/test_escopo.py` | não | +2 testes (Q1) |
| `webqa/sondagem.py` | não | `main()` (Q2) |
| `tests/test_sondagem.py` | não | +4 testes (Q2, Q6) |
| `pyproject.toml` | não | `C901` + `per-file-ignores` (Q3) |
| `requirements.txt` | não | `pytest-cov` (Q4) |
| `.github/workflows/ci.yml` | não | `--cov` nos dois jobs (Q4) |
| `.github/workflows/mutacao.yml` | não | arquivo novo (Q5) |
| `scripts/mutar.py` | não | arquivo novo (Q5) |

**Nada nesta fatia está sob CODEOWNERS.** Os quatro caminhos protegidos
(`webqa/gates.py`, `webqa/escopo.py`, `webqa/data/caminhos-sensiveis.yaml`,
`tests/test_fase_c_travada.py`) permanecem intocados. Isso é de propósito: se você
se pegar precisando editar um deles, **pare e reveja** — provavelmente você está
resolvendo o problema no lugar errado.

Atenção especial: **`webqa/escopo.py` é CODEOWNERS, mas `tests/test_escopo.py` não
é.** Q1 mexe só no teste.

---

## 5. Os seis itens

### Q1 · Imutabilidade das dataclasses de governança — **prioridade máxima**

**O problema.** `EntradaEscopo` e `Escopo` são `@dataclass(frozen=True)`. Trocar para
`frozen=False` e a suíte inteira continua verde. Um registro de autorização mutável
em memória anula a premissa da Fase C: o escopo tem de ser uma foto congelada no
carregamento. A garantia hoje é *implícita no decorator* — e mutante adora garantia
implícita.

**A prova.**
```
webqa/escopo.py:76  (truth)  sobreviveu   # @dataclass(frozen=True) → False
webqa/escopo.py:112 (truth)  sobreviveu
```

**Onde.** `tests/test_escopo.py`, ao final do arquivo. O módulo já tem a fixture
autouse `_sem_dns_real` e o helper `_escrever(tmp_path, origem=...)` — use-os.

**O que fazer.** Dois testes, e os **dois** são necessários:

```python
# ---------- a autorização é uma foto congelada, não um objeto editável ----------

def test_toda_dataclass_do_escopo_e_congelada():
    """Guarda estrutural: modelo novo aqui nasce imutável, sem depender de lembrança.

    Testar `EntradaEscopo` e `Escopo` uma a uma protege o que existe hoje. Varrer o
    módulo protege o que alguém acrescentar amanhã — é o mesmo padrão de
    test_convencoes.py e test_fronteira_de_rede.py.
    """
    import dataclasses
    import inspect

    mutaveis = [
        nome for nome, obj in vars(escopo).items()
        if inspect.isclass(obj) and dataclasses.is_dataclass(obj)
        and obj.__module__ == escopo.__name__
        and not obj.__dataclass_params__.frozen
    ]
    assert not mutaveis, (
        f"dataclass mutável em webqa/escopo.py: {mutaveis}. A autorização é um "
        "snapshot do carregamento; objeto editável em memória anula a prova de posse.")


def test_entrada_e_escopo_recusam_reatribuicao(tmp_path):
    """Comportamento, não declaração: o `frozen=True` acima é verdade em runtime."""
    from dataclasses import FrozenInstanceError

    esc = escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br"))
    entrada = esc.entradas[0]

    with pytest.raises(FrozenInstanceError):
        entrada.origem = "https://invasor.exemplo.br"
    with pytest.raises(FrozenInstanceError):
        esc.entradas = ()
```

**Por que os dois.** A varredura prova que o decorator está *declarado*; a
reatribuição prova que o comportamento é o esperado. Sozinha, cada uma troca uma
garantia implícita por outra.

**Armadilhas — leia antes de escrever.** Três versões deste teste circularam em
revisão e **nenhuma funcionava**:

1. `EntradaEscopo(url=..., data=...)` — **não existe campo `url`**. Os campos são
   `origem`, `autorizado_por`, `data`, `evidencia`, `ambiente`, e todos os cinco
   são obrigatórios.
2. `pytest.raises(TypeError)` — dataclass congelada levanta **`FrozenInstanceError`**,
   que é subclasse de `AttributeError`, nunca de `TypeError`.
3. Pior: construir o objeto **dentro** do `with pytest.raises(...)`. A construção
   com kwargs errados levanta `TypeError` antes da reatribuição, o `raises` captura,
   **o teste passa verde — e passaria verde com `frozen=False` também**. Verificado
   em execução. É a pior categoria de teste que existe: dá a sensação de buraco
   tapado sem tapar nada.

**Aceite.**
- `make verify` verde.
- Trocar manualmente `frozen=True` → `frozen=False` em `webqa/escopo.py:76` faz
  `test_toda_dataclass_do_escopo_e_congelada` **e**
  `test_entrada_e_escopo_recusam_reatribuicao` falharem. Reverta depois.
- Rodar o harness do Apêndice B em `webqa/escopo.py` sobe o score de 88,5% para
  **100%** (os outros 2 sobreviventes são `_PORTA_HTTPS = 443` → 444, equivalente
  sob `getaddrinfo` dublado; documente como tal).

---

### Q2 · Contrato de erro da CLI — **prioridade alta**

**O problema.** Duas coisas ao mesmo tempo:

*(a)* Nenhum teste do repositório chama `sondagem.main()`. Zero. É a interface que
a pessoa realmente digita.

*(b)* Mais grave, e descoberto ao rodar a CLI de verdade: **o caminho de erro mais
comum termina em traceback.** `require_escopo` e `require_discovery` (em
`webqa/gates.py`) chamam `pytest.skip()`, que fora de um teste levanta a exceção
`Skipped` sem tratamento:

```
$ python -m webqa.sondagem --alvo https://naoautorizado.exemplo --executar
...
  File "webqa/gates.py", line 115, in require_escopo
    pytest.skip(
Skipped: [gate:escopo] https://naoautorizado.exemplo fora do escopo autorizado —
adicione o host ao escopo com autorização documentada antes de sondá-lo.
```

A mensagem existe, é bem escrita, e **nunca chega ao usuário** — chega uma pilha de
chamadas com a mensagem no rodapé.

**O que NÃO fazer.** Não capture `Skipped` importando `_pytest.outcomes` — é API
privada. E não toque `webqa/gates.py`: é CODEOWNERS, e o `pytest.skip` está correto
para o uso dele (dentro de testes, ausência de autorização é skip, não fail).

**O que fazer.** `main()` pré-checa os mesmos predicados, que são puros e não
importam pytest: `discovery_authorized()` (já checado, linhas 386–390) e
`escopo.esta_no_escopo(alvo)` (falta). Os gates dentro de `sondar` continuam como
defesa em profundidade e simplesmente nunca são alcançados pela CLI.

Em `webqa/sondagem.py`, dentro de `main()`, logo após o bloco `if not
discovery_authorized():` (por volta da linha 390):

```python
    if not escopo.esta_no_escopo(args.alvo):
        print(f"Alvo fora do escopo autorizado: {args.alvo}. Adicione o host ao "
              f"{args.escopo} com autorização documentada. Nada foi enviado.")
        return 2
```

Use código de saída **2** (distinto do 1 de "sem opt-in"): quem roda em script
precisa distinguir "faltou variável de ambiente" de "alvo errado".

**Onde testar.** `tests/test_sondagem.py`. O arquivo já tem tudo de que você
precisa: fixture autouse `_ambiente_limpo`, helper `_escopo_valido(tmp_path,
monkeypatch)`, `_resolve_para`, e `ALVO = "https://alvo-fixture.exemplo"`.

**Os três testes:**

```python
# ---------- o contrato de erro da CLI (a interface que a pessoa digita) ----------

def test_cli_dry_run_e_o_padrao_e_nao_toca_a_rede(tmp_path, monkeypatch, capsys):
    """Sem --executar, a CLI planeja e sai 0 — nenhum cliente HTTP é criado."""
    ...  # monkeypatch em sondagem._cliente_padrao para explodir se chamado
    assert sondagem.main([...]) == 0
    assert "[dry-run]" in capsys.readouterr().out


def test_cli_sem_opt_in_recusa_com_mensagem_e_sai_1(tmp_path, monkeypatch, capsys):
    """Sem WEBQA_DISCOVERY_AUTHORIZED, a CLI explica e sai 1 — sem traceback."""
    ...
    assert sondagem.main([..., "--executar"]) == 1
    assert "não autorizada" in capsys.readouterr().out


def test_cli_alvo_fora_do_escopo_nao_vaza_traceback(tmp_path, monkeypatch, capsys):
    """REGRESSÃO: hoje isto termina em `Skipped` cru na cara do usuário."""
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    ...
    assert sondagem.main(["--alvo", "https://outro.exemplo", ..., "--executar"]) == 2
    saida = capsys.readouterr().out
    assert "fora do escopo" in saida
    assert "Traceback" not in saida
```

**Escreva o terceiro primeiro, veja-o falhar** (vai falhar com `Skipped`
escapando), e só então aplique a correção em `main()`. É a prova por mutação natural
deste item.

**Aceite.**
- Os três passam.
- Rodar a CLI à mão com alvo fora do escopo imprime uma linha e sai 2.
- Cobertura de `webqa/sondagem.py` sobe de 83% para ≥ 95%.
- No harness de mutação, os sobreviventes das linhas 365–399 desaparecem.

**Nota de priorização, para você entender o peso.** Uma revisão anterior classificou
isto como "bypass de governança": *se um mutante apagar o `if not
discovery_authorized()` do `main()`, a CLI sondaria sem opt-in*. **Isso está errado**
— `sondar()` chama `require_discovery()` internamente. O mutante causaria exceção,
não probe silencioso. O risco real é de contrato de erro e usabilidade, não de
segurança. Não trate como incidente.

---

### Q3 · Gate de complexidade via ruff — **prioridade média**

**Por que ruff e não radon/xenon.** `ruff` já está no `requirements.txt`, no
`Makefile` e no CI. O `mccabe` vem embutido. Zero dependência nova.

**Por que limiar 8 e não 10.** Medido: a 10, **nenhuma função de `webqa/` é pega**.
Um gate que passa limpo no motor não vigia nada.

**O que fazer.** Em `pyproject.toml`, no `[tool.ruff.lint]` já existente:

```toml
[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "C901"]

[tool.ruff.lint.mccabe]
max-complexity = 8
```

E nos `per-file-ignores` já existentes, uma isenção **datada e justificada** para o
que não é biblioteca:

```toml
[tool.ruff.lint.per-file-ignores]
# ... entradas existentes ...
# C901: dívida conhecida FORA da biblioteca. `scripts/` e `fixture_target/` são
# ferramenta e alvo fabricado, não o motor. A isenção existe para o gate nascer
# verde e vigiar `webqa/` desde hoje, não para eternizar `render_markdown` (CC 19).
# Backlog: refatorar scripts/campanha.py::render_markdown e remover esta linha.
"scripts/**" = ["C901"]
"fixture_target/**" = ["C901"]
"checks/**" = ["B017", "BLE001", "S110", "S112", "C901"]
```

**O que sobra reprovando em `webqa/`:** `sondar` (10), `metadados_exif` (9),
`preparar` (9). Três opções, nesta ordem de preferência:

1. `sondar` — resolve sozinho quando você extrair `avaliar_resposta_em_finding()`,
   `executar_fallback_get()` e `calcular_espera_backoff()`, que **já estão na fila
   de refactor** (PR C1e do roadmap da Fase C). Se aquele PR vier antes, este item
   nasce verde.
2. `metadados_exif` e `preparar` — 1 ponto acima do limiar cada. Micro-refactor
   (extrair um `if` aninhado) resolve.
3. Se nenhum couber agora: `# noqa: C901` **com comentário explicando por quê e um
   TODO nomeado**. Nunca `# noqa` mudo.

**Aceite.** `ruff check webqa checks tests scripts fixture_target` verde no CI, com
o gate ativo em `webqa/`. Adicionar de propósito um `if/elif` a mais em `sondar`
reprova o lint.

---

### Q4 · Cobertura de código nos dois jobs — **prioridade média**

**O problema.** Não há `pytest-cov` em lugar nenhum: nem `requirements.txt`, nem
`pyproject.toml`, nem `pytest.ini`, nem `Makefile`, nem os workflows. O número
existe (77%) mas ninguém o vê, e ele pode cair a qualquer PR sem sinal.

**Cuidado — um erro que circulou em revisão.** Três pareceres afirmaram que "o
cockpit já calcula cobertura por população, esforço zero". **Não calcula.** O
cockpit mede *cobertura de execução de testes* (quantos dos 763 testes catalogados
foram coletados por um run). Cobertura de **código** — quais linhas de `webqa/`
foram atingidas — é outra métrica, vem do `coverage.py`, e não está instrumentada.
As duas compartilham a palavra "cobertura" e mais nada. Não risque este item.

**O que fazer.**

`requirements.txt` — adicione junto do bloco de qualidade da suíte:
```
# medição da própria suíte: sem isto o número de cobertura existe mas ninguém o vê
pytest-cov>=5.0
```

`.github/workflows/ci.yml` — **os dois jobs**, e é esse o ponto:

```yaml
# job quality-gate, linha ~70
      - name: Verificação (unidade, sem alvo externo)
        run: pytest tests -m verification --cov=webqa --cov-report=term --cov-fail-under=75

# job validate-target, linha ~107
      - name: Suíte completa (sem carga)
        run: pytest -m "not load" --cov=webqa --cov-report=term
```

**Por que só o primeiro tem `--cov-fail-under`.** O `quality-gate` é determinístico
(não depende de alvo externo), então um piso ali é justo. O `validate-target`
depende de um site publicado responder; um piso ali transformaria instabilidade de
rede em reprovação de PR. Ele mede e reporta, não trava — e é justamente o número
que hoje ninguém tem.

**Por que 75 e não 77.** O medido é 77%; 75 dá dois pontos de folga para não
reprovar PR por arredondamento. Suba o piso quando Q2 entregar (a cobertura de
`sondagem.py` vai de 83% para ~95%).

**Aceite.** Os dois jobs imprimem cobertura. Apagar um teste de `test_escopo.py` faz
o `quality-gate` reprovar por `--cov-fail-under`.

---

### Q5 · Job de mutação escopado — **prioridade média**

**Por que não `mutmut`/`cosmic-ray`.** Dependência nova, e rodar mutação nos 3.073
statements do repo é caro e inútil. O harness do Apêndice B tem ~60 linhas de
stdlib, roda `escopo.py` em ~1 min e `sondagem.py` em ~4 min.

**Por que escopado.** Os módulos que concentram governança e execução são quatro:
`escopo.py`, `gates.py`, `sondagem.py`, `sanitize.py`. É onde sobreviver dói.

**O que fazer.**
1. Copie o harness do Apêndice B para `scripts/mutar.py`.
2. Alvo no `Makefile`:
   ```make
   # Mutação escopada na superfície de segurança. NAO roda no PR (lento);
   # roda no noturno e a mao. Ver docs/handoff/HANDOFF-Q1-instrumentacao.md §Q5.
   mutar: ; python scripts/mutar.py . webqa/escopo.py tests/test_escopo.py tests/test_fase_c_travada.py
   ```
3. Workflow novo `.github/workflows/mutacao.yml`, agendado, **com o ambiente
   explicitamente limpo**:

```yaml
      - name: Mutação escopada (superfície de segurança)
        env:
          WEBQA_DISCOVERY_AUTHORIZED: ""
          WEBQA_ACTIVE_PROBES_AUTHORIZED: ""
          WEBQA_LOAD_AUTHORIZED: ""
        run: |
          test -z "$WEBQA_DISCOVERY_AUTHORIZED" || { echo "gate setado no job de mutação"; exit 1; }
          python scripts/mutar.py . webqa/escopo.py tests/test_escopo.py
          python scripts/mutar.py . webqa/gates.py  tests/test_gates.py
```

**Por que a trava de ambiente.** Mutação **altera a lógica dos gates de propósito**.
Um mutante que inverta `discovery_authorized()` roda com a suíte inteira. Na prática
a fixture autouse `_ambiente_limpo` (em `tests/test_sondagem.py`) já apaga as
variáveis, mas ela é local a um arquivo de teste, e a mutação pode atingir a própria
lógica que a fixture exercita. Explicitar no job custa três linhas de YAML e fecha a
janela.

*(Uma revisão sugeriu que `pytest-xdist` poderia vazar variáveis entre workers. Não
pode — workers do xdist são processos separados. A trava vale pelo motivo acima, não
por esse.)*

**Aceite.** Job roda e publica o score. Meta declarada: **zero sobreviventes** em
`escopo.py` e `gates.py`; sobrevivente equivalente (ex.: constante que os dublês
tornam irrelevante) é aceito **com justificativa no PR**, nunca em silêncio.

---

### Q6 · Testes de borda do motor — **prioridade média**

Dois mutantes sobreviveram em código **coberto** — não é ausência de teste, é
ausência de asserção.

**(a) Borda superior do 2xx.** `webqa/sondagem.py:274`:
```python
if not (200 <= status < 300):
    return None
```
Mutar `<` para `<=` sobrevive: nenhum teste distingue 299 de 300. Um 300 (Multiple
Choices) viraria achado de exposição.

```python
@pytest.mark.parametrize("status,vira_finding", [(299, True), (300, False)])
def test_borda_superior_do_2xx(tmp_path, monkeypatch, status, vira_finding):
    """299 é achado, 300 não é — a borda é fechada em cima."""
```

**(b) Porta não-padrão no IP pinning.** `webqa/sondagem.py:218`:
```python
porta = partes.port or (443 if partes.scheme == "https" else 80)
```
Sobrevive à mutação: nenhum teste usa porta explícita nem `http`. Um alvo
`https://host:8443` nunca foi exercitado.

```python
def test_probe_preserva_porta_nao_padrao_na_url_pinada(tmp_path, monkeypatch):
    """Alvo com porta explícita conecta no IP pinado NAQUELA porta."""
```

**Contexto importante para não errar o diagnóstico.** Uma revisão chamou (b) de
"bypass de escopo: a porta é ignorada na validação". **Não é.** Verificado:
`origem_de("https://x.com:8443/a")` devolve `https://x.com:8443`, e é essa string
que `esta_no_escopo` compara. A porta entra na autorização. O gap é só na
`_url_pinada`, e é gap de teste de borda.

**Enquanto estiver aqui.** Este é também o lugar do bug de **IPv6** achado antes:
`sorted(ips_pinados)[0]` ordena **strings**, então num host dual-stack pode eleger o
IPv6, e `f"{scheme}://{ip}:{porta}"` monta `https://2001:db8::1:443/.env` — URL
malformada, que vira `_FALHA_DE_REDE` silenciosa. Se o PR C1d do roadmap da Fase C
ainda não tiver entrado, o teste de borda de porta e o de IPv6 são o mesmo PR: mesma
função, mesma falta de cobertura de borda. Escolha determinística por
`ipaddress.ip_address(x).version`, nunca por ordenação de string.

---

## 6. Ordem de PRs

Pequenos e separados, no idioma da casa (spec `xfail(strict=True)` → implementação →
prova por mutação → PR).

| PR | Conteúdo | Arquivos | Tamanho |
|---|---|---|---|
| **Q1a** | Imutabilidade das dataclasses | `tests/test_escopo.py` | ~30 linhas, 1 arquivo |
| **Q1b** | Contrato de erro da CLI | `webqa/sondagem.py`, `tests/test_sondagem.py` | ~50 linhas |
| **Q1c** | `pytest-cov` + `--cov` nos dois jobs | `requirements.txt`, `ci.yml` | ~5 linhas |
| **Q1d** | Gate `C901` limiar 8 + resolver os 3 de `webqa/` | `pyproject.toml` (+ refactor) | variável |
| **Q1e** | Harness + workflow de mutação | `scripts/mutar.py`, `mutacao.yml`, `Makefile` | ~80 linhas |
| **Q1f** | Bordas: 2xx, porta não-padrão, IPv6 | `webqa/sondagem.py`, `tests/test_sondagem.py` | ~40 linhas |

**Q1a primeiro e sozinho**: é o menor diff, fecha a única quebra de invariante de
segurança do lote, e não depende de nada.

**Q1d por último entre os de configuração**: ele depende de você ter decidido o que
fazer com `sondar` (refatorar ou `# noqa` justificado), e essa decisão fica melhor
depois que Q1b já mexeu no arquivo.

---

## 7. O que **não** fazer

Estas sugestões apareceram em revisão e foram descartadas com motivo. Estão aqui
para você não reintroduzi-las de boa-fé.

| Sugestão | Por que não |
|---|---|
| Script que cruza cobertura com `data/caminhos-sensiveis.yaml` | O arquivo tem **5 entradas**. Cem linhas de script para 5 itens tem ROI negativo. |
| `radon`/`xenon` no CI | Dependência nova para o que o `ruff` já faz embutido. |
| `vulture` para complexidade | `vulture` detecta código morto, não complexidade. Métricas trocadas. |
| `.pre-commit-config.yaml` para o C901 | O repo não tem pre-commit. Deixa de ser "uma linha" e vira arquivo + dependência novos. Backlog. |
| Golden master / snapshot do `stdout` da CLI | Congelaria também a listagem dos caminhos curados. Como `caminhos-sensiveis.yaml` é CODEOWNERS e muda de propósito, todo PR de governança passaria a mexer num `.txt` de snapshot. Acopla artefato de governança a artefato de UX. Prefira assert sobre exit code + substring. |
| Teste de append-only do `AuditLog` | **Já existe**: `tests/test_audit_fase_c.py:66::test_append_only_em_arquivo`. E `AuditLog.linhas` já devolve `tuple`. |
| Teste de "escopo recusa entrada sem data" | `data` é campo obrigatório de `EntradaEscopo` e `carregar()` faz `a["data"]` direto. Impossível construir sem. |
| Probes adaptativos / expansão condicional da lista | Quebra o invariante `executado × esperado` (denominador móvel) e degenera a lista curada em wordlist dinâmica. |
| Triagem de achados por LLM | `tests/test_convencoes.py:212::test_modulo_de_sondagem_nao_importa_llm` proíbe por AST. |
| Canary de egresso em `ifconfig.me` | Host **fora** do `escopo-autorizado.yaml`. Se quiser pré-check de rede, faça `HEAD /` no próprio alvo. |
| Limiar de 90% de caminhos sondados para marcar inconclusivo | `ResultadoSondagem.inconclusivo` já exige **100%**. O limiar proposto é mais fraco que o atual. |

E os nomes que **não existem** no repositório, apesar de terem aparecido em
pareceres: `requirements-dev.txt`, `.coveragerc`, `make test-fasec`,
`TETO_CORPO_FASE_C`, `EscopoAutorizado`, `data_autorizacao`, `escopo.hosts_alvo`,
`gerar_relatorio`, `dry-run-surface.json`, binário `webqa` no PATH. Não há
`[project.scripts]` no `pyproject.toml` — a CLI é `python -m webqa.sondagem`.
E `origem_de` mora em **`webqa/auth.py:59`**, não em `escopo.py`.

---

## 8. Apêndice A — blocos padronizados, um por PR

Cole em outra LLM ou entregue como spec mínima.

```xml
<lang>Python 3.11 + pytest</lang>
<task>Provar que EntradaEscopo e Escopo são imutáveis (Q1a): varredura estrutural de dataclasses + reatribuição real.</task>
<context>
webqa/escopo.py:76 e :112 são @dataclass(frozen=True); mutar para frozen=False sobrevive à suíte.
Campos de EntradaEscopo: origem, autorizado_por, data, evidencia, ambiente — todos obrigatórios. NÃO existe `url`.
tests/test_escopo.py já tem fixture autouse `_sem_dns_real` e helper `_escrever(tmp_path, origem=...)`.
webqa/escopo.py é CODEOWNERS; tests/test_escopo.py NÃO é. Só o teste muda.
</context>
<rules>
- Pense passo a passo antes de responder.
- Construa o objeto FORA do bloco `pytest.raises` — dentro, um TypeError de kwarg errado faz o teste passar em falso.
- A exceção é `dataclasses.FrozenInstanceError`, nunca TypeError.
</rules>
<aceite>
- Trocar frozen=True por False em webqa/escopo.py faz os DOIS testes falharem.
- Uma dataclass nova sem frozen=True no módulo também reprova.
</aceite>
<testes>
- entrada.origem = "https://invasor.exemplo.br" → FrozenInstanceError.
- Classe mutável plantada no módulo → a varredura acusa pelo nome.
</testes>
<recomendacao>
- Separe verificação (o decorator está declarado?) de validação (a reatribuição falha em runtime?).
</recomendacao>
```

```xml
<lang>Python 3.11 + pytest</lang>
<task>Fazer a CLI de sondagem falhar com mensagem em vez de traceback quando o alvo está fora do escopo (Q1b), e cobrir main() com três testes.</task>
<context>
`python -m webqa.sondagem --alvo X --executar` com X fora do escopo termina em `Skipped:` cru:
require_escopo/require_discovery (webqa/gates.py) usam pytest.skip(), que fora de teste levanta exceção.
webqa/gates.py é CODEOWNERS — NÃO alterar. A correção é pré-checar em main().
Predicados puros disponíveis: gates.discovery_authorized() e escopo.esta_no_escopo(url).
tests/test_sondagem.py tem `_ambiente_limpo` (autouse), `_escopo_valido`, `ALVO`.
</context>
<rules>
- Pense passo a passo antes de responder.
- Não importar `_pytest.outcomes` (API privada). Pré-checar, não capturar.
- Exit codes distintos: 1 = sem opt-in, 2 = fora do escopo.
- Escreva o teste de regressão ANTES da correção e veja-o falhar.
</rules>
<aceite>
- Alvo fora do escopo: sai 2, imprime "fora do escopo", stdout sem "Traceback".
- --dry-run continua saindo 0 sem criar cliente HTTP.
- Cobertura de webqa/sondagem.py ≥ 95%.
</aceite>
<testes>
- main([...,"--executar"]) sem WEBQA_DISCOVERY_AUTHORIZED → 1.
- main(["--alvo","https://outro.exemplo",...,"--executar"]) com escopo válido de outro host → 2.
</testes>
<recomendacao>
- Cubra unidade e aceitação: o contrato aqui é a saída de terminal, não o objeto de retorno.
</recomendacao>
```

```xml
<lang>Python 3.11 + pytest + httpx</lang>
<task>Fechar as bordas do motor que a mutação expôs (Q1f): limite superior do 2xx, porta não-padrão e escolha de família de IP.</task>
<context>
sondagem.py:274 `if not (200 <= status < 300)` — mutar `<`→`<=` sobrevive: nenhum teste separa 299 de 300.
sondagem.py:218 `porta = partes.port or (443 if https else 80)` — sobrevive: nenhum teste usa porta explícita.
sondagem.py:320 `ip_pinado = sorted(ips_pinados)[0]` ordena STRINGS: dual-stack pode eleger IPv6, e
_url_pinada monta `https://2001:db8::1:443/...` sem colchetes → URL malformada → falha silenciosa.
Testes usam httpx.MockTransport e getaddrinfo dublado; nenhuma rede real.
</context>
<rules>
- Pense passo a passo antes de responder.
- Escolha de família por `ipaddress.ip_address(x).version`, nunca por ordenação de string.
- A URL registrada no AuditLog continua sendo a lógica (hostname), não o IP.
</rules>
<aceite>
- 299 vira Finding; 300 não vira.
- Alvo https://host:8443 conecta no IP pinado na porta 8443.
- Host dual-stack elege IPv4; forçando só IPv6, a URL sai com colchetes.
</aceite>
<testes>
- parametrize [(299, True), (300, False)] sobre o status devolvido pelo MockTransport.
- getaddrinfo dublado devolvendo ['2001:db8::1','203.0.113.7'] → probe usa o IPv4.
</testes>
<recomendacao>
- Analise os limites: as três falhas são de borda, não de caminho feliz.
</recomendacao>
```

---

## 9. Apêndice B — harness de mutação (`scripts/mutar.py`)

Stdlib pura. Planta um defeito por vez, roda a suíte, restaura o arquivo. Foi com
ele que os números da seção 3.4 foram medidos.

```python
"""Harness mínimo de mutação: planta um defeito por vez e vê se a suíte morde.

Uso:  python scripts/mutar.py . webqa/escopo.py tests/test_escopo.py

Escopado de propósito: rodar mutação nos 3.073 statements do repo é caro e inútil.
O alvo é a superfície de segurança — escopo, gates, sondagem, sanitize.

ATENÇÃO: isto ALTERA a lógica dos gates de propósito. Nunca rode com
WEBQA_DISCOVERY_AUTHORIZED ou WEBQA_ACTIVE_PROBES_AUTHORIZED no ambiente.
"""
from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

CMP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
       ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.In: ast.NotIn, ast.NotIn: ast.In}


class Coletor(ast.NodeVisitor):
    """Todos os pontos mutáveis. Identidade estável: (tipo, linha, coluna, índice)."""

    def __init__(self):
        self.pontos = []

    def visit_Compare(self, n):
        for i, op in enumerate(n.ops):
            if type(op) in CMP:
                self.pontos.append(("cmp", n.lineno, n.col_offset, i))
        self.generic_visit(n)

    def visit_BoolOp(self, n):
        self.pontos.append(("bool", n.lineno, n.col_offset, 0))
        self.generic_visit(n)

    def visit_UnaryOp(self, n):
        if isinstance(n.op, ast.Not):
            self.pontos.append(("not", n.lineno, n.col_offset, 0))
        self.generic_visit(n)

    def visit_Constant(self, n):
        if isinstance(n.value, bool):
            self.pontos.append(("truth", n.lineno, n.col_offset, 0))
        elif isinstance(n.value, (int, float)):
            self.pontos.append(("num", n.lineno, n.col_offset, 0))
        self.generic_visit(n)


class Mutador(ast.NodeTransformer):
    def __init__(self, alvo):
        self.alvo = alvo
        self.feito = False

    def _e(self, n, k, i=0):
        return (not self.feito) and (k, n.lineno, n.col_offset, i) == self.alvo

    def visit_Compare(self, n):
        self.generic_visit(n)
        for i, op in enumerate(n.ops):
            if self._e(n, "cmp", i) and type(op) in CMP:
                n.ops[i] = CMP[type(op)]()
                self.feito = True
        return n

    def visit_BoolOp(self, n):
        self.generic_visit(n)
        if self._e(n, "bool"):
            n.op = ast.Or() if isinstance(n.op, ast.And) else ast.And()
            self.feito = True
        return n

    def visit_UnaryOp(self, n):
        self.generic_visit(n)
        if self._e(n, "not"):
            self.feito = True
            return n.operand
        return n

    def visit_Constant(self, n):
        if self._e(n, "truth"):
            self.feito = True
            return ast.Constant(not n.value)
        if self._e(n, "num"):
            self.feito = True
            return ast.Constant(n.value + 1)
        return n


def rodar(raiz, arquivo, testes):
    orig = pathlib.Path(raiz) / arquivo
    fonte = orig.read_text(encoding="utf-8")
    c = Coletor()
    c.visit(ast.parse(fonte))

    vivos, mortos, invalidos = [], 0, 0
    try:
        for p in c.pontos:
            m = Mutador(p)
            novo = m.visit(ast.parse(fonte))
            if not m.feito:
                invalidos += 1
                continue
            try:
                codigo = ast.unparse(ast.fix_missing_locations(novo))
            except Exception:
                invalidos += 1
                continue
            orig.write_text(codigo, encoding="utf-8")
            r = subprocess.run(
                [sys.executable, "-m", "pytest", *testes, "-x", "-q", "--no-header",
                 "-p", "no:cacheprovider"],
                cwd=raiz, capture_output=True, timeout=300)
            if r.returncode == 0:
                vivos.append((p[0], p[1]))   # suíte passou COM o defeito: sobreviveu
            else:
                mortos += 1
    finally:
        orig.write_text(fonte, encoding="utf-8")   # restaura SEMPRE, inclusive em Ctrl-C
    return len(c.pontos), mortos, vivos, invalidos


if __name__ == "__main__":
    raiz, arquivo, *testes = sys.argv[1:]
    n, mortos, vivos, inv = rodar(raiz, arquivo, testes)
    viaveis = mortos + len(vivos)
    print(f"\n{arquivo}: {n} pontos, {viaveis} viáveis, {mortos} mortos, "
          f"{len(vivos)} SOBREVIVERAM → score {100 * mortos / max(viaveis, 1):.1f}%")
    for k, linha in vivos:
        print(f"   sobreviveu: {arquivo}:{linha}  ({k})")
    raise SystemExit(1 if vivos else 0)
```

**Antes de commitar**, ajuste ao idioma da casa: `ruff check scripts/mutar.py` e
`bandit -q -c pyproject.toml -r scripts`. O `subprocess.run` com lista de argumentos
(nunca `shell=True`) é o que mantém o bandit quieto.

---

## 10. Glossário mínimo

- **Cobertura de código** — quais linhas de `webqa/` uma execução atinge. Vem do
  `coverage.py`. **Não instrumentada** hoje.
- **Cobertura de execução de testes** — quantos dos 763 testes catalogados um run
  coletou. Vem do cockpit. Métrica **diferente**, apesar do nome parecido.
- **Score de mutação** — % de defeitos plantados que a suíte reprova. Mede a força
  das asserções; cobertura mede só se a linha foi visitada.
- **Mutante sobrevivente** — defeito plantado com a suíte ainda verde. Ou falta
  teste, ou falta asserção, ou o mutante é *equivalente* (não muda comportamento
  observável) — e essa terceira hipótese precisa ser **argumentada**, não presumida.
- **População `verification`** (`tests/`) — testes que verificam a própria suíte.
  Falha aqui é bug na ferramenta.
- **População de checks** (`checks/`) — testes que validam o alvo auditado. Falha
  aqui é achado sobre o alvo. **As duas nunca se somam.**
- **CODEOWNERS** — `webqa/gates.py`, `webqa/escopo.py`,
  `data/caminhos-sensiveis.yaml`, `tests/test_fase_c_travada.py`. Exigem revisão
  nomeada. Nenhum é tocado por esta fatia.
