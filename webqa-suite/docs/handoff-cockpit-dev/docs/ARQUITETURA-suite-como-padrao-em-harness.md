# A WebQA Suite como padrão consumido por uma harness

**Estado deste documento:** exploração de arquitetura. Nada aqui está implementado.

Este documento descreve **um contexto de uso que hoje não existe**: a `qa-suite` como
padrão instalável, consumido por muitos projetos, invocado por uma harness de agentes.
O repositório atual é uma suíte que audita **um** alvo configurável — não um pacote
distribuído. A diferença entre os dois é o assunto daqui.

Nada neste documento deve ser lido como descrição do repositório em `main`. A seção 9
lista, item a item, o que já existe e o que precisaria ser construído.

---

## 1. Por que o contexto muda tudo

Hoje a suíte é clonada e executada contra um alvo declarado em `config.yaml`. Um
repositório, um alvo por vez, uma pessoa operando.

No contexto proposto, três coisas mudam ao mesmo tempo:

| | Hoje | No contexto da harness |
|---|---|---|
| Quantos projetos | 1 | N |
| Quem invoca | pessoa, via `make` | agente, via harness |
| O que se compara | nada — há um só laudo | laudos entre projetos |

A terceira é a que impõe as regras. Comparar laudos entre projetos só é honesto se
todos foram produzidos pela **mesma régua**, e se cada laudo disser **qual régua**
usou. Tudo neste documento decorre disso.

---

## 2. Os dois trabalhos da suíte

A distinção mais importante do documento, e a que não está explícita no repositório
atual. A suíte faz duas coisas com naturezas opostas:

### Trabalho A — auditar o alvo publicado

Mede o site que está no ar: latência, cabeçalhos de segurança, terceiros carregados,
acessibilidade, exposição de arquivos sensíveis. É a população `checks/`.

**Precisa de contexto do projeto:** endereço do alvo, autorização documentada, limites
aceitáveis. Um galpão e uma creche não têm o mesmo critério; um blog e um internet
banking também não.

### Trabalho B — vigiar os testes do projeto

Lê o código do repositório, encontra todos os testes que existem, classifica por nível
(unidade, integração, sistema, aceitação) e reconcilia com a última execução. É o
cockpit.

**Não precisa de contexto nenhum.** Lê o código por AST, sem importar módulo, sem
executar nada, sem saber qual framework o projeto usa. Aponta para uma pasta e ele
responde.

> **Consequência de projeto:** o Trabalho B é genuinamente agnóstico e pode rodar em
> qualquer repositório desde o primeiro dia. O Trabalho A exige um contrato de
> configuração e autorização por projeto. Uma harness que trate os dois como a mesma
> coisa vai pedir autorização de sondagem para rodar um inventário de testes — e o
> operador aprende a aprovar sem ler.

---

## 3. O que pertence ao padrão e o que pertence ao projeto

A regra de fronteira, em uma frase: **o projeto contribui configuração e autorização,
nunca código de verificação.**

| Artefato | Padrão (uma cópia, versionada) | Projeto (uma por repositório) |
|---|---|---|
| `webqa/` — motor, sanitização, gates, escopo | ✅ | |
| `checks/` — as dimensões de qualidade | ✅ | |
| `tests/` — a verificação da própria suíte | ✅ | |
| `data/caminhos-sensiveis.yaml` — lista curada | ✅ **e imutável pelo projeto** | |
| `pytest.ini` — marcadores/dimensões | ✅ | |
| CODEOWNERS | ✅ | não sobrevive a cópia |
| `config.yaml` — alvo e thresholds | template `.example` | ✅ valores |
| `escopo-autorizado.yaml` — autorização Fase C | template `.example` | ✅ obrigatório |
| `campanha.yaml` — alvos passivos | template | ✅ opcional |
| `report/` — laudo produzido | | ✅ efêmero |

### Por que a lista curada não pode ser do projeto

`data/caminhos-sensiveis.yaml` é o que a sondagem procura em cada alvo. Ela tem teto
(`MAX_CAMINHOS = 200`) imposto no carregador, campos obrigatórios validados, e está
sob CODEOWNERS.

Se cada projeto tiver uma cópia editável, três coisas acontecem em sequência: alguém
remove uma linha que estava dando trabalho; a suíte para de procurar aquilo naquele
projeto; **o laudo continua dizendo "nenhum achado"**. Não há erro, não há aviso — o
resultado é indistinguível de um projeto seguro.

Uma trava que o vigiado pode desligar em silêncio não é uma trava. Este é o argumento
central contra copiar a suíte para dentro de cada repositório.

### Se um projeto precisar de uma verificação própria

Ela vira proposta ao padrão, com dimensão declarada no `pytest.ini`, e passa a valer
para todos. Não vira arquivo solto no repositório do cliente.

O motivo não é burocrático: se cada projeto tiver checks próprios, o número que o
cockpit produz deixa de ser comparável entre projetos — e comparabilidade é a única
razão de existir um padrão.

---

## 4. Declarada, não copiada

As duas formas parecem iguais na árvore de diretórios e são opostas na prática.

**Copiada** — o código da suíte vive dentro do repositório do projeto:

```
projeto/
  src/
  tests/
    test_meu_produto.py
    webqa/                     ← código da suíte, editável por quem tem acesso ao projeto
      checks/
      data/caminhos-sensiveis.yaml
```

**Declarada** — o código vive fora; o projeto aponta para uma versão:

```
projeto/
  src/
  tests/
    test_meu_produto.py        ← testes do projeto (a suíte LÊ, nunca edita)
    qa/
      config.yaml              ← alvo + thresholds
      escopo-autorizado.yaml   ← autorização documentada
  requirements-qa.txt          ← webqa-suite==1.4.0
```

Na forma declarada a suíte **mora em `tests/`** no sentido operacional — é lá que ela
é invocada e é lá que ficam os arquivos dela — mas o código não é editável por quem
trabalha no projeto, e a versão está registrada.

---

## 5. Layout de referência

### 5.1 O padrão

```
danzeroum/qa-suite/
  webqa-suite/
    webqa/                       motor
    checks/                      dimensões de qualidade (julgam o alvo)
    tests/                       verificação da suíte
    data/caminhos-sensiveis.yaml lista curada — CODEOWNERS
    pytest.ini                   marcadores canônicos
    config.yaml.example
    escopo-autorizado.yaml.example
  docker/
  .github/
    CODEOWNERS
    workflows/
      ci.yml                     verificação do próprio padrão
      auditar.yml                reutilizável (workflow_call) — NÃO EXISTE HOJE
  action.yml                     composite action — NÃO EXISTE HOJE
```

### 5.2 Um projeto consumidor

```
projeto-cliente/
  src/
  tests/
    test_meu_produto.py
    qa/
      config.yaml
      escopo-autorizado.yaml     só se o projeto usar Fase C
  .github/workflows/qa.yml
  harness/                       opcional; ver §6
```

### 5.3 A harness

```
harness/
  harness.yaml                   manifesto: quais agentes, quais gates, quais escopos
  agents/
    developer/    AGENT.md  inputs.md  outputs.md
    reviewer/     AGENT.md  ...
    tester/       AGENT.md  ...
    documenter/   AGENT.md  ...
  prompts/
  runs/                          registro bruto por execução
  reports/                       consolidado (inclui os laudos da suíte)
  policies/                      ÍNDICE apontando para gates executáveis — ver §7
```

---

## 6. Como a harness invoca a suíte

Quatro modos, com naturezas de risco diferentes. A harness precisa distingui-los —
tratá-los como um só é o erro de governança mais provável nesta arquitetura.

| Modo | O que faz | Toca a rede? | Exige autorização? | Agente pode disparar sozinho? |
|---|---|---|---|---|
| **1. Inventário** | lê o código, produz o catálogo de testes | não | não | ✅ sim |
| **2. Passivo** | roda `checks/` contra o alvo (GET normais) | sim | escopo declarado | ⚠️ com alvo já configurado |
| **3. Carga** | rajada de requisições (`-m load`) | sim | `WEBQA_LOAD_AUTHORIZED` | ❌ não |
| **4. Sondagem ativa** | Fase C: pede recursos não linkados | sim | `WEBQA_DISCOVERY_AUTHORIZED` + escopo + prova de posse | ❌ **nunca** |

### Modo 1 — inventário (o mais barato e o mais seguro)

```yaml
# harness/agents/tester/AGENT.md → passo declarado
- id: inventario-de-testes
  comando: "webqa cockpit --raiz . --saida harness/reports/cockpit.html"
  rede: nao
  gates: []
```

Não precisa de alvo, de autorização nem de rede. Pode rodar a cada commit, em qualquer
repositório, inclusive nos que não usam a suíte para mais nada.

### Modo 2 — auditoria passiva

```yaml
- id: auditoria-passiva
  comando: "webqa auditar --config tests/qa/config.yaml -m 'not load'"
  rede: sim
  gates: [alvo-declarado]
```

### Modos 3 e 4 — nunca pelo agente

O gate é uma variável de ambiente. Um agente com permissão ampla no shell pode
exportá-la. Ver §7.

---

## 7. Governança: o ponto que a arquitetura de harness costuma errar

### 7.1 Política em markdown não morde

A suíte já tem políticas, e elas são **executáveis**:

| Política | Onde é fiscalizada | Como |
|---|---|---|
| Sondagem exige opt-in | `webqa/gates.py` | variável de ambiente, fail-closed |
| Host fora do escopo não é tocado | `webqa/escopo.py` | comparação de origem exata |
| Alvo não pode ter sido reapontado | `escopo.verificar_posse` | snapshot de IP no carregamento |
| Motor de sondagem não conhece IA | `tests/test_convencoes.py` | varredura de AST |
| Todo consumidor de rede é registrado | `tests/test_fronteira_de_rede.py` | varredura de AST + registro |
| Achado nasce mascarado | `webqa/dominio.py` | sanitização no construtor |

Um `harness/policies/forbidden-actions.md` **não substitui nenhuma delas**. É a
diferença entre uma placa de "proibido fumar" e um detector ligado ao alarme: a placa
depende de alguém ler e obedecer.

**Regra proposta:** `harness/policies/` é um **índice**, não a política. Cada entrada
aponta para o teste ou gate que a fiscaliza, e uma entrada sem apontamento é um
lembrete — nunca uma garantia. Formato sugerido:

```markdown
## Sondagem ativa exige autorização documentada
Fiscalizado por: webqa/gates.py::require_discovery
Provado por:     tests/test_gates.py, tests/test_fase_c_travada.py
Falha como:      fail-closed (skip do teste; erro na CLI)
```

### 7.2 O ambiente do agente nunca tem os gates

Este é o requisito não negociável desta arquitetura.

Os gates da suíte são variáveis de ambiente:

```
WEBQA_DISCOVERY_AUTHORIZED       descoberta read-only (Fase C, C1)
WEBQA_ACTIVE_PROBES_AUTHORIZED   sondagem com escrita (C2)
WEBQA_LOAD_AUTHORIZED            teste de carga
WEBQA_ACTIVE_PROBES_KILL         parada de emergência
```

Um agente com shell pode exportar qualquer uma delas. `allowed-paths.md` não impede
isso, porque a trava não é de arquivo.

**Requisito:** o runner do agente roda com ambiente limpo, sempre. Os modos 3 e 4 só
existem em jobs separados, disparados por pessoa, com o ambiente montado ali.

```yaml
# harness.yaml
runtime:
  env_allowlist: [PATH, HOME, LANG]      # nada de WEBQA_*
  env_denylist_prefix: ["WEBQA_"]
  fail_on_denied_env: true               # aborta se encontrar, não apenas ignora
```

O `fail_on_denied_env` importa: ignorar silenciosamente uma variável proibida esconde
o erro de configuração que o controle existe para revelar.

### 7.3 A pergunta que a harness tem de responder antes de agir

Um agente que propõe editar `data/caminhos-sensiveis.yaml` está propondo alterar o
padrão de todos os projetos a partir do repositório de um cliente. A harness precisa
tratar caminhos do padrão como **somente leitura**, categoricamente — não por
convenção de pasta, mas porque o código nem está ali (§4).

---

## 8. Versionamento e comparabilidade

### 8.1 O laudo carimba a régua

A suíte pode ser agnóstica a projeto e a versão de harness. **O laudo nunca é.**

Suponha:

- Projeto A rodou a suíte v1.2, que procurava 5 tipos de arquivo exposto → *0 achados*
- Projeto B rodou a suíte v1.6, que procura 40 tipos → *0 achados*

Os dois laudos dizem a mesma frase e afirmam coisas diferentes. Colocá-los lado a lado
numa planilha de comparação produz um número falso, sem que ninguém perceba.

**Requisito:** todo artefato produzido carrega a procedência do padrão. O cockpit já
emite esse bloco (repositório, ramo, commit, data da leitura) — hoje é um detalhe de
cabeçalho; nesta arquitetura vira campo obrigatório de qualquer comparação.

```json
{
  "padrao": {
    "nome": "webqa-suite",
    "versao": "1.4.0",
    "commit": "67a8bfe",
    "caminhos_sensiveis_hash": "sha256:…"
  },
  "projeto": { "repositorio": "projeto-cliente", "commit": "a1b2c3d" },
  "modo": "passivo",
  "gates_ativos": []
}
```

O `caminhos_sensiveis_hash` fecha o buraco de §3: se dois laudos têm a mesma versão do
padrão e hashes de lista diferentes, alguém editou a lista. Isso deixa de ser
invisível.

### 8.2 Política de atualização

- **Projetos declaram versão exata** (`==`), não faixa. A superfície do que a suíte
  procura é dado de segurança; ela não deve mudar sozinha entre dois runs.
- **Subir de versão é decisão versionada**, num PR do projeto, com o laudo anterior e
  o novo lado a lado.
- **A harness pode propor a subida**; nunca executá-la sozinha.

### 8.3 Uma agregação que passa a ser possível

Com a procedência carimbada, o cockpit ganha uma divisão nova e honesta:

- **catálogo** → do padrão, idêntico para todos
- **execução** → por projeto

E aí "cobertura de execução" vira comparável entre clientes pela primeira vez:
*"no projeto A rodaram 91 dos 91 checks; no B, 38 de 91."* Isso não é adaptação do que
existe — é capacidade nova, e ela só aparece porque a régua é única.

---

## 9. O que existe hoje e o que não existe

Tabela de honestidade. Sem ela este documento vira especificação fantasma.

| Peça | Estado |
|---|---|
| Motor parametrizado por `config.yaml` + `WEBQA_*` | ✅ existe |
| `escopo-autorizado.yaml` separado do código | ✅ existe |
| Gates fail-closed por variável de ambiente | ✅ existe |
| Lista curada com teto e CODEOWNERS | ✅ existe |
| Políticas executáveis (AST, fronteira de rede) | ✅ existe |
| Cockpit lendo qualquer repositório por AST | ✅ existe (fora do repo, ainda não incorporado) |
| Bloco de procedência no artefato | ⚠️ parcial — só no cockpit, e não normativo |
| Duas populações separadas (`checks/` × `tests/`) | ✅ existe |
| **Entrypoint instalável (`[project.scripts]`)** | ❌ **não existe** |
| **Pacote publicável / versionado** | ❌ não existe |
| **Workflow reutilizável (`workflow_call`)** | ❌ não existe |
| **`caminhos_sensiveis_hash` no laudo** | ❌ não existe |
| **Contrato de erro da CLI** | ❌ não existe — hoje sai traceback |

A peça que destrava todas as outras é o **entrypoint instalável**. Sem ele,
"declarar a suíte" é impossível na prática e "instalar em `tests/`" só pode significar
copiar — que é o cenário que este documento existe para evitar.

O trabalho está listado no plano de instrumentação como **Q2** (contrato de erro da
CLI). Ele é pequeno, e é pré-requisito de tudo aqui.

---

## 10. Riscos desta arquitetura

| # | Risco | Mitigação |
|---|---|---|
| **H1** | Agente exporta um gate e dispara sondagem ativa | ambiente do agente com denylist `WEBQA_*` e `fail_on_denied_env` |
| **H2** | Projeto copia a suíte em vez de declarar; lista curada é editada | laudo carrega `caminhos_sensiveis_hash`; divergência é achado, não silêncio |
| **H3** | Laudos de versões diferentes comparados como iguais | procedência obrigatória; agregação recusa misturar versões |
| **H4** | Política vira markdown e para de morder | `policies/` é índice; entrada sem apontamento para gate é lembrete, não garantia |
| **H5** | Harness cacheia índice do repositório e serve dado velho | a suíte é sem estado entre execuções por desenho; se houver cache, ele carrega o hash do que indexou e se invalida sozinho |
| **H6** | Check específico de um cliente entra no repositório dele | fronteira do §3: projeto contribui config e autorização, nunca código |
| **H7** | Agente propõe subir a versão do padrão e o faz sozinho | subida de versão é PR do projeto, com laudo anterior e novo lado a lado |

---

## 11. Glossário

- **Padrão** — o repositório `qa-suite`, versionado, com CODEOWNERS. Uma cópia.
- **Projeto consumidor** — repositório que declara o padrão como dependência e fornece
  config e autorização.
- **Harness** — camada que orquestra agentes sobre um projeto. Consome a suíte; não a
  contém.
- **Gate** — trava fail-closed por variável de ambiente. Ausência de autorização não é
  defeito do alvo: vira skip nos testes, erro claro na CLI.
- **Procedência** — o carimbo de qual régua produziu um laudo: versão do padrão,
  commit, hash da lista curada.
- **Modo** — inventário, passivo, carga ou sondagem ativa. Naturezas de risco
  diferentes; a harness precisa distingui-los.
- **População** — `checks/` julga o alvo; `tests/` verifica a suíte. As duas nunca se
  somam num mesmo número.
