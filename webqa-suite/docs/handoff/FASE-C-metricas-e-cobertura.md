# Fase C — Cobertura de testes e métricas de operação (não-sensível)

> Análise. Não altera o repo. Duas metas: (1) maximizar a cobertura de testes da
> Fase C; (2) extrair o máximo de métricas/dados de operação — **sem dado
> sensível** — para uma visão holística da aplicação testada. Ancorada no que já
> existe: `webqa/metricas.py`, `scripts/telemetria.py`, `report.py`
> (`summary.json`).

## 0. A restrição que amarra as duas metas

O pedido tem um teto explícito: **holístico, sem dado sensível**. No repo isso já é
disciplina estrutural, não boa vontade — `telemetria.py` agrega só `summary.json`
(nunca corpo), troca alvo nominal por `alvo_sha256`, tem `anonimizar_agregado`, e o
`summary.json` sai por `mascarar_valores_registrados`. A Fase C **herda esse
contrato**: a camada de métrica é uma nova *borda de escrita* e tem de nascer
sanitizada, do mesmo jeito que o `Finding` nasce sanitizado e a credencial nasce
registrada para mascaramento.

Consequência de desenho (o item que trava a garantia): um **allowlist**
`CAMPOS_DA_TELEMETRIA_FASE_C` — irmão do `CAMPOS_DO_PROMPT` que já barra o que vai
para a LLM — listando **só** campos agregados (contagens, tempos, razões, flags).
`recurso`, `evidencia`, `remediacao`, URL com query, corpo: nunca. Com um teste de
não-vazamento irmão de `test_vazamento_de_credencial.py` que planta um segredo num
achado e prova que ele não aparece no `telemetria.json`. **Sem esse allowlist +
teste, nada de métrica nova de Fase C entra.**

---

## PARTE A — Maximizar a cobertura de testes

### A.1 Verificação × Validação, em cada artefato
Aplicar os dois eixos a cada peça: *verificação* (está correto?) e *validação* (faz
o que deveria?). Ex.: o `escopo.py` — verificação: origem exata reprova `cdn.`/`www.`;
validação: a allowlist de fato impede um probe fora do escopo num run real. Um
detector que só tem verificação (o teste passa) mas nunca teve a validação (nunca
pegou uma violação plantada) **não está provado** — é a regra da casa, e ela é o
multiplicador de cobertura mais barato que existe aqui.

### A.2 Os quatro níveis, mapeados à Fase C

| Nível | O que cobre na Fase C | Estado / lacuna |
|---|---|---|
| **Unidade** | Cada invariante isolada: escopo origem-exata, gates `skip`-not-`fail` e só `"1"`, `remediacao` sanitizada + anti-markup, `verificar_posse` divergência, `audit` masking/anti-injection, finding por status puro | Bom (C0a–C0c já têm). Lacuna: **property-based** no loader de `caminhos-sensiveis.yaml` (campos/enum/teto) e no corte de query da auditoria |
| **Integração** | Fiação `escopo+gate+audit+sondagem`; consumidor de fronteira registrado (§2.11); `summary.json` carrega os campos; `find_secrets(fase="C")` propaga a fase | Parcial. Lacuna: teste de **contrato** do `summary.json` (schema estável, aditivo) e do allowlist de telemetria |
| **Sistema** | Run completo contra `fixture_target` com exposições plantadas (`/.git/HEAD`, `/.env`, backup) → detecção ponta a ponta, HEAD-only, escopo-locked, rate-limited | **Lacuna maior**: expandir `fixture_target/` com iscas de exposição para o run de sistema exercitar detecção de verdade (hoje a trava impede o motor; os specs `xfail` seguram o contrato até C1) |
| **Aceitação** | Os critérios das HU-C1..C4 como testes executáveis (achou `.env` → finding alta com remediação; fora do escopo → não executa; C2 recusa produção) | Traduzir cada critério de aceite do plano num teste nomeado |

### A.3 Técnicas que aumentam cobertura com pouco esforço
- **Mutação como prática de primeira classe.** O ciclo "planta violação → o teste
  morde → remove" já aparece nos check-ins; formalizá-lo (um alvo `make mutar-fasec`
  que aplica mutações conhecidas e exige que cada uma derrube o teste certo)
  transforma "verde" em "provado".
- **Parametrização/property-based** onde o espaço é combinatório: lista de caminhos
  (cada item: campos obrigatórios, categoria ∈ enum, teto), heurística de
  Content-Type (esperado × recebido → finding/inconclusivo), redirect (`3xx` vira
  finding, nunca seguido), `.env` vazio (`200 + Content-Length: 0` = exposição),
  soft-404 (corpus de páginas de erro estilizadas → nenhum falso positivo alto).
- **Specs `xfail(strict=True)` antes do motor** — fixam o contrato de C1 no
  `test_sumario.py`/`test_seguranca_checks.py` e viram falha automática se alguém
  implementar fora do fluxo. Cobertura da *ausência*, no idioma do
  `test_fase_c_travada.py`.
- **SAST + convenção estática** — `bandit` já roda sobre `webqa`; somar detectores
  AST em `test_convencoes.py` (sondagem não importa `llm`; todo check ativo passa
  pelo gate; `find_secrets` sempre com `fase="C"` na sondagem) cobre invariantes que
  teste de runtime não pega.

### A.4 Matriz risco → nível (para fechar lacunas)
Para cada risco catalogado, garantir ≥1 nível cobrindo e a mutação que o prova:
R-C6 (takeover) → unidade (`verificar_posse` divergência) ✔; R-C8/C15 (vazamento/
log-injection) → unidade (audit) ✔ + **sistema** (resposta 500 com segredo plantado)
✘; R-C14 (soft-404) → unidade (Content-Type) parcial + **corpus** ✘; R-C16 (run
parcial) → integração (contador executado×esperado) ✘; escopo-escape por redirect →
sistema ✘. Os ✘ são o backlog de teste priorizado.

---

## PARTE B — Métricas e dados de operação (holístico, não-sensível)

### B.1 Princípio: agregado por alvo-hasheado, nunca o dado
Tudo que a Fase C emite passa por: **contagem/tempo/razão/flag**, chaveado por
`alvo_sha256`, aditivo (schema velho renderiza igual), mascarado, e filtrado pelo
allowlist. O motor registra via `metricas.registrar("fasec.<nome>", valor)` → cai no
`summary.json` → `telemetria.py` agrega. Zero corpo, zero URL-com-query, zero
`evidencia`.

### B.2 Taxonomia de métricas de Fase C (todas agregadas, não-sensíveis)

**Cobertura (a visão "quanto da aplicação foi olhada"):**
- `caminhos_sondados` / `caminhos_esperados` por alvo (o contador do R-C16).
- `% alvos-no-escopo cobertos` por ciclo; `tamanho_da_dry_run_surface`.
- `categorias_cobertas` (vcs/config/backup/editor/…) — quantas das curadas foram exercidas.

**Achados (a visão "o que se encontrou"), só contagem:**
- por **categoria**, por **severidade**, por **ambiente** (`producao`/`homologacao`).
- `novos` / `resolvidos` / `persistentes` (diff entre runs) — a série temporal.
- Nunca o `recurso`/URL do achado no artefato agregado; a contagem é o dado.

**Respeito ao alvo / operação (a visão "como se sondou"):**
- `requisicoes_por_alvo`, `intervalo_medio` vs `piso`, nº `429`/`503`, `aborts_por_alvo`.
- `kill_switch_acionado` (flag/contagem), `tempo_por_alvo` (percentis — reusa
  `_percentis`/`ranking_de_lentos` que já existem), `timeouts`.

**Governança / estado (a visão "sob que autoridade"):**
- gates ligados (booleans), `escopo_hash`, `n_entradas_de_escopo`,
  distribuição por `ambiente`, `n_linhas_de_auditoria`, `posse_divergente` (contagem
  de takeover flag — R-C6).

**Confiabilidade (a visão "posso confiar neste run?"):**
- `run_inconclusivo` quando `executado < esperado` (R-C16 — falha de infra que
  parece "zero findings = tudo seguro"), `falhas_de_resolucao`, `taxa_de_flake`
  (reusa `flake_por_teste`).

### B.3 Observabilidade: os três sinais, adaptados
- **Eventos estruturados** = a auditoria JSONL + `summary.json` como fonte de
  verdade (não log com segredo).
- **Métricas** = `telemetria.json` agregado (o que `telemetria.py` já monta),
  acrescido das dimensões da Fase C **como dimensão à parte** — run ativo não
  contamina o veredito passivo.
- **"Traces" leves** = tempo por alvo/percentis já existentes. Um painel holístico
  é derivação do `telemetria.json`, não uma fonte nova.

### B.4 Alinhamento estratégico (OKR): métrica de resultado, não de tarefa
A visão holística só vira valor se as métricas conectarem a um resultado, não à
atividade. O anti-padrão a evitar: "rodamos a Fase C em N alvos" é *entrega*, não
Key Result. KR é o efeito:

- **Objetivo:** reduzir a superfície de exposição própria e **provar** a redução.
- **KR-1:** % de exposições de severidade alta remediadas em ≤ *N* dias (do diff
  entre runs: achado→resolvido).
- **KR-2:** tempo médio de remediação (mesma série temporal).
- **KR-3:** cobertura = % de alvos-no-escopo efetivamente sondados por ciclo.
- **KR-4 (confiabilidade):** taxa de `run_inconclusivo` ≤ *X*% — sem isso, os
  outros KRs mentem (run parcial infla "zero exposições").

### B.5 O contrato dos dados como API (summary.json / telemetria.json)
Esses artefatos **são** a API de observabilidade — trate-os como contrato:
- **Nomes estáveis e autoexplicativos**, `schema_version`, mudanças **aditivas**
  (o `summary.json` já promete "summary antigo renderiza igual").
- **Enums** para `categoria`/`severidade`/`ambiente` (agrupamento sem surpresa).
- **Feedback informativo**: `run_inconclusivo` diz *por quê* (parcial? resolução?),
  não só um booleano mudo.
- **Anti-padrões a barrar:** vazar internals/segredo no payload (o allowlist
  resolve), nomes de campo instáveis, e "over-fetch" — telemetria que carrega o
  dado sensível "por via das dúvidas". O default é o mínimo agregado.

### B.6 Onde plugar (concreto, sem inventar módulo)
`metricas.registrar("fasec.*", …)` → `summary.json` → `telemetria.py`
(`metricas_agregadas`/`distribuicao_por_check` estendidos com as dimensões da Fase C,
sempre via `alvo_sha256`/`anonimizar_agregado`). Somar `CAMPOS_DA_TELEMETRIA_FASE_C`
(allowlist) + teste de não-vazamento. Documentar em `docs/TELEMETRIA.md` a dimensão
ativa. Nenhuma fonte nova; a Fase C só alimenta o pipeline que já existe.

---

## Recomendações aplicadas (com fonte)

[RECOMENDAÇÃO] Verificação e Validação: separe V&V — verificação (está correto?) e
validação (é o que deveria fazer?) — e aplique ambos em cada nível. Aqui: todo
detector de Fase C precisa da validação por violação plantada, não só do verde.
_Fonte: Garantia e Controle de Qualidade — Jeniffer Deus_

[RECOMENDAÇÃO] Níveis de Teste: exija cobertura em unidade, integração, sistema e
aceitação, com foco em limites, riscos e maior complexidade. Priorize as lacunas ✘
da matriz A.4 (sistema contra fixture com exposição plantada; contrato do summary).
_Fonte: Garantia e Controle de Qualidade — Jeniffer Deus_

[RECOMENDAÇÃO] Observabilidade: verifique se há logging, tracing e monitoramento que
permitam entender o comportamento interno e achar gargalos — aqui, sem dado
sensível: eventos estruturados (auditoria/summary), métricas agregadas por
alvo-hasheado, tempo por alvo.
_Fonte: Arquitetura de Softwares — Adriano Carezzato_

[RECOMENDAÇÃO] Observabilidade (Logs/Métricas/Traces): inclua requisitos de logs
estruturados com contexto, métricas de desempenho e tracing de requisições — no caso
da Fase C, o "contexto" é agregado e mascarado, nunca o corpo ou a URL-com-query.
_Fonte: Projeto e Arquitetura de APIs — Rafael Lachi / Weber Ress_

[RECOMENDAÇÃO] API Design Principles: avalie o `summary.json`/`telemetria.json` como
contrato — nomes estáveis e autoexplicativos, schema versionado e aditivo, enums para
categoria/severidade, e feedback informativo (o inconclusivo diz por quê).
_Fonte: Projeto e Arquitetura de APIs — Rafael Lachi / Weber Ress_

[RECOMENDAÇÃO] OKR e Alinhamento Estratégico: verifique se as métricas conectam a
Key Results quantitativos e orientados a resultado (exposições remediadas, tempo de
remediação, cobertura), não à entrega/tarefa ("rodamos a Fase C" não é KR).
_Fonte: Métricas na Gestão de Projetos de Software — Raphael Donaire Albino_
