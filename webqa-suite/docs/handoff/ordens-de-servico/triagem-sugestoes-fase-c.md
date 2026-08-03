# Triagem — sugestões dos analistas para a Fase C

Base: `main` @ `67a8bfe` (Fase C fechada: C1a #42, C1b f1 #43, C1c #44, C1b f2 #45).
Critério de aceite, na ordem: **(1)** a alegação sobre o código é verdadeira?
**(2)** respeita os invariantes — *detectar, nunca explorar* · HEAD-only ·
stdlib-first · escopo por origem exata · determinístico/auditável · nada sai da
máquina? **(3)** cabe em `sondagem.py` ou é outra ferramenta?

Regra de ouro: sugestão elegante que fura o **(2)** é rejeitada, por melhor que
seja a engenharia. Muitas destas furam.

---

## TIER 1 — ACEITAR (correção/segurança, respeitam os invariantes)

### 1.1 — Stream no fallback GET do 405 (OOM / auto-DoS / quebra de contrato)
**Verificado, e é o achado mais grave da rodada.** A C1b fatia 2 (#45) faz `GET`
com `Range: bytes=0-0` no 405. Servidor hostil que **ignora o Range** responde
`200` com o corpo inteiro — `client.get()` materializa 5 GB na memória e derruba
o motor, **violando "nunca baixa o recurso"**. Correção de custo ~zero: trocar
por `client.stream("GET", …)`, ler só os headers, fechar sem iterar o corpo.
→ **Emitir OS C1d (fatia 1), prioridade máxima.** Só `sondagem.py`.

### 1.2 — Teto no backoff (429/503 sem limite → falso "inconclusivo" por tempo)
**Procede.** Backoff exponencial sem teto nem limite de tentativas: alvo que
responde `429` constante faz o motor dormir minutos e trava o run. Fixar
`MAX_BACKOFF_S` e `MAX_RETRIES`; estourou → conta `falhas_rede`, marca `erro`,
segue. O piso invariante de rate-limit **não** pode ser abaixado pelo cálculo.
→ **OS C1d (fatia 1).**

### 1.3 — Circuit breaker por falhas consecutivas
**Alinhado.** Complementa 1.2: N falhas seguidas (timeout pós-retry, 429/403 de
WAF) → `abortado_por="circuit-breaker"`, `inconclusivo=True`. Honestidade do run
parcial — mesma família de "ausência de análise nunca é atestado".
→ **OS C1d (fatia 1).**

### 1.4 — Contador executados vs. esperados < limiar → inconclusivo (R-C16)
**Aceito, invariante central.** Se menos de ~90% dos caminhos curados foram
efetivamente sondados (abort, timeout, infra), o run é `inconclusivo` e o
pipeline falha. Fecha "falha parcial que parece sucesso" — o mesmo erro do
navegador morto lido como "noite limpa" no ledger.
→ **OS C1d (fatia 1).**

### 1.5 — Contexto do fallback no AuditLog
**Baixo custo, alinhado ao "auditável".** A linha do `GET(range)` recebe
`contexto="fallback_405_head_nao_permitido"` para o auditor humano não ler o GET
como exploração arbitrária. A requisição-fantasma do soft-404 dinâmico (C2) tem
a mesma exigência: nenhum probe invisível no log.
→ **OS C1d (fatia 1).**

### 1.6 — Diagnóstico em `posse-divergente` (sem abrir demais)
**Aceito.** Hoje o abort é correto mas raso. `verificar_posse` já virou
`frozenset` na C1c — expor `esperados`/`atuais`/`divergentes` no motivo do abort
dá triagem a takeover/rebind sem alterar a política de bloqueio.
→ **OS C1d (fatia 1).**

### 1.7 — Refatoração por extração (isolar as superfícies de perigo)
**Aceito como higiene, não como feature.** Extrair `avaliar_resposta_em_finding`
(pura, testável sem mock), `executar_fallback_get` (a única exceção ao HEAD-only,
num lugar só que o CODEOWNER audita) e `calcular_espera_backoff` (o piso
invariante isolado). Não muda lógica; reduz custo cognitivo de auditoria.
→ **Junto da C1d**, pois 1.1/1.2 já tocam essas mesmas funções.

### 1.8 — Testes deterministas de rede/tempo (respx + freezegun) e resolver injetável
**Aceito com ressalva stdlib-first.** O valor — mockar 405→200, timeout, e
avançar o relógio sem dormir de verdade — é real e a C1d precisa dele. Mas antes
de somar dependência de teste, checar se o `MockTransport`/`getaddrinfo` dublado
já em uso cobre; só trazer `respx`/`freezegun` se faltar. Injeção de `client`/
`log`/resolver já existe (é como #42–#44 testaram sem rede) — reusar.

### 1.9 — `content_type_esperado` no veredito (falso positivo de forced browsing)
**Já resolvido na C1b fatia 1 (#43).** `_e_soft_404` passou a cortar quando o
tipo esperado está vazio e o recebido é HTML. Vários analistas "descobriram" o
que já está na `main`. O refino de *rebaixar severidade* + marcar "verificar
manualmente" quando `text/html` onde se espera `text/plain` é incremento válido
→ pode entrar na C2 (reporting), não é bug aberto.

---

## TIER 2 — JÁ FEITO ou JÁ NA FILA (não reabrir)

- **soft-404 dinâmico (baseline fantasma), --multi-alvo, procedencia no output,
  teste-sistema com os canários, ciclo de vida do finding** → já são a **C2**
  (OS emitida, fatias 1 e 2). Não duplicar.
- **posse por DNS-TXT/.well-known** → **C2 fatia 2**, como *alternativa* ao pino
  de IP da C1c, nunca substituição.
- **saída results.json + SARIF, filtrar por severidade, exportar CSV** →
  reporting; entram na **C2 fatia 2** (SARIF) / backlog (CSV/filtro).
- **run_id serializável no ResultadoSondagem** → o `run_id` uuid entrou na C1b
  fatia 1 (#43); expor `to_dict()` estável é incremento pequeno → backlog C2.
- **carregar_caminhos_por_tag / subconjuntos por stack** → é a poda curada da
  **C2 fatia 2** (aceitos `.env.local`, `docker-compose.yml`, `.map`).

---

## TIER 3 — REJEITAR (furam o invariante 2 — por princípio, não por esforço)

- **Sondagem adaptativa / probes condicionais / expansão ao achar `/.git/HEAD`**
  → quebra **determinismo/reprodutibilidade** (dois runs no mesmo alvo dariam
  superfícies diferentes) e degenera a lista curada em wordlist. **Não.**
- **Triagem/classificação de risco por LLM sobre metadados do finding** →
  `test_convencoes` **proíbe `sondagem.py` importar `llm`**; e a doutrina "nada
  sai da máquina" não abre exceção "só telemetria". Se algum dia, é módulo
  separado gated, não o motor. **Fora do módulo.**
- **Correlação/threat-chaining elevando severidade a "crítico/takeover"** →
  inferência que extrapola o observável; vira laudo especulativo. A severidade é
  do caminho curado, decidida por humano. **Não.**
- **Fingerprint passivo de WAF/CDN e "delatores" (X-Powered-By, Server, cookies
  BIGip) virando Finding** → muda a natureza de "arquivo exposto não-linkado"
  para reconhecimento de infra; e suprimir/ajustar finding por "parece WAF" é
  **falso-negativo por design**. Registrar header no AuditLog para leitura humana
  é ok; **gerar Finding a partir disso, não.**
- **Descoberta de APIs/Swagger/GraphQL com introspecção baixando "primeiras
  centenas de bytes"** → lê corpo (mesmo que parcial, é conteúdo, não existência)
  e `/openapi.json`, `/graphql` são **públicos por design** → ruído. **Não** —
  já rejeitado na triagem anterior (`/docs`, `/openapi.json`, `/redoc`).
- **Emitir Issue no GitHub automático a cada finding alto** → acopla o motor a
  serviço externo com token; é orquestração de CI, produto vizinho, não
  `sondagem.py`. Pode viver num passo separado do pipeline. **Fora do módulo.**
- **Job cron de "obsolescência" comparando com wordlists públicas externas** →
  puxa fonte externa para dentro do ciclo curado; a curadoria é ato humano
  deliberado. Alerta manual por PR, sim; **fetch automático de wordlist, não.**
- **Health-check / canary de egresso a `ifconfig.me` etc.** → requisição a host
  **fora do escopo autorizado** a cada run — fura escopo por origem exata. O R-C16
  se resolve pelo contador 1.4 (interno), sem bater em terceiro. **Não** o canary;
  **sim** o contador.

---

## TIER 4 — DEFER (valor real, peso alto, sem urgência)

- **Hash/lock da lista curada (`_CAMINHOS_SENSIVEIS_HASH` estilo lock file)** →
  boa defesa de governança, mas o CODEOWNERS + validação de carregamento já
  cobrem o caminho principal; pesa manutenção do hash a cada PR. Reavaliar se a
  lista crescer muito.
- **Provenance criptográfica Ed25519 do finding** → valor para SOC2/ISO; o
  AuditLog append-only já dá trilha. Defer.
- **Sanitização/veto de env vars sensíveis no processo (`WEBQA_STRICT_ENV`)** →
  útil, mas é política de infra/CI; se entrar, na camada de gates, não no motor.
- **timeout granular do httpx (connect/read/write separados)** → melhoria real de
  resiliência; entra de carona quando a C1d mexer no cliente (1.1). Baixo risco.
- **Mapeamento MITRE/OWASP como campo `padroes` no YAML** → metadado de
  compliance, backward-compatible; toca `caminhos-sensiveis.yaml` (CODEOWNERS) e
  o template do relatório. Entra na C2 fatia 2 se couber, senão backlog.
- **Comando `curl` reproduzível por finding (`to_curl()`)** → boa ergonomia de
  triagem; reporting, entra depois da C2 estabilizar o formato do finding.

---

## Duas notas de precisão (o que NÃO existe no repo — se copiado verbatim, quebra)

Vários trechos citam APIs inexistentes: `AuditLog._entradas`/`url_mascarada`,
`network_log`, `resolver.dns_lookup`, `TelemetriaFaseC().registrar_run` (o
`telemetria_fasec.py` expõe `filtrar`/`serializar`). São ilustrativos — a
integração certa passa pelos allowlists já construídos
(`CAMPOS_DA_TELEMETRIA_FASE_C`), nunca inventando API. E: **ambos** os IPs de
teste RFC 5737 respondem `is_private=True` no 3.11 — irrelevante, porque a posse
compara igualdade de conjuntos, não localidade.

---

## Ordem de execução resultante

1. **C1d fatia 1** (URGENTE) — stream no 405 (anti-OOM), teto de backoff,
   circuit breaker, contador executados/esperados→inconclusivo (R-C16), contexto
   no AuditLog, diagnóstico de posse-divergente, extração das 3 funções puras,
   testes deterministas. **Só `sondagem.py`.**
2. **C2 fatia 1** — soft-404 dinâmico, canários (A.4), procedencia, --multi-alvo.
3. **C2 fatia 2 (CODEOWNERS)** — posse DNS-TXT, SARIF, baseline.yaml, poda curada,
   + MITRE/OWASP se couber.
4. **Backlog/defer** — Tier 4.

## Pendências do dono (não-código)
Apagar `danzeroum-patch-1/-2`; assinar commits para frente; portão do escopo do
`docker.danzeroum.com`. Required check: já feito pelo ruleset.
