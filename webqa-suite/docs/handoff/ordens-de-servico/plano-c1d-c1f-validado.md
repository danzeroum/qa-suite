# Plano C1d–C1f + C2 — validado contra o código (`main` @ 67a8bfe)

Cada gap abaixo foi conferido na fonte real (`sondagem.py`, `dominio.py`,
`escopo.py`) em 2026-08-03. Substitui a seção C1d da triagem anterior
(`triagem-sugestoes-fase-c.md`), que continha duas alucinações herdadas.

---

## 0. Correção ao registro anterior (alucinação em cadeia, confirmada)

| Afirmava (triagem `cc014d10`) | Código real em `67a8bfe` | Veredito |
|---|---|---|
| "stream no 405 / anti-OOM — `client.get()` materializa 5 GB" | `sondagem.py` já usa `client.stream("GET", …)` sem iterar (≤1 byte) | **já feito (#45)** |
| "teto no backoff — sem limite trava o run" | `TETO_BACKOFF_S=30.0`, `BACKOFF_FATOR=4` já existem | **já feito (#45)** |
| "run < 90% dos caminhos → inconclusivo" | `inconclusivo` já exige 100% (`executado < esperado`) + `falhas_rede`/`recuos`/`abortado_por` | **rejeitar — 90% é MAIS FRACO** |

O gap real de resiliência **não é o teto do backoff** (existe) — **é o abort**
(não existe). Isso é o G1, e muda o conteúdo do C1e.

---

## 1. Gaps confirmados no código (prova + esforço)

### Motor `sondagem.py` / `dominio.py` — NÃO-CODEOWNERS

- **G1 — circuit breaker ausente.** No laço, `_PedeRecuo` faz
  `recuos+=1; recuos_seguidos+=1; continue` — nunca `break`. 200 caminhos em 429
  permanente = dorme o run inteiro (com teto por probe) e termina inconclusivo
  igual. `recuos_seguidos` só desacelera. → abortar após N recuos/erros seguidos.
- **G2 — IPv6 quebra a URL pinada.** `_url_pinada` monta
  `f"{scheme}://{ip}:{porta}{caminho}"`; IP v6 vira `https://2001:db8::1:443/…`
  malformado → `_FALHA_DE_REDE` silencioso. E `sorted(ips_pinados)[0]` escolhe
  família por ordem lexicográfica (não-determinística). → colchetes em v6 +
  escolha determinística de família.
- **G3 — `procedencia` órfã.** `CaminhoSensivel.procedencia` é carregada das 5
  entradas do YAML e **nunca chega ao `Finding`** (o dataclass em `dominio.py`
  nem tem o campo; o `return Finding(…)` a omite). Valor de compliance
  (OWASP WSTG-CONF-004, CWE-538/527) já existe no dado, só falta propagar.
- **G4 — abortos de governança fora do AuditLog.** `posse-divergente` retorna
  ANTES de `log` ser criado (o `log = log or AuditLog(...)` vem depois da checagem
  de posse); `kill-switch` faz `break` sem `registrar`. → criar/receber o log
  antes dos portões e registrar os dois abortos.
- **G5 — descarte soft-404 silencioso.** `if _e_soft_404(...): return None` sem
  evento; o log mostra `status=200` sem finding e sem dizer por quê. →
  `evento="descartado:soft-404"`.
- **G6 — timeout único.** `TIMEOUT_S=10.0` escalar em `_cliente_padrao`; host
  inacessível come o orçamento. → `httpx.Timeout(connect=…, read=…)`.

### Escopo `escopo.py` — CODEOWNERS ⚠

- **G7 — `verificar_posse` colapsa 4 causas em um rótulo.** Devolve `frozenset()`
  para: host não listado, snapshot vazio (não resolveu no carregamento),
  divergência (takeover/rebind) e falha de resolução agora. A própria docstring
  lista as 4 — o retorno não distingue. → diagnóstico por causa no log; **IPs
  nunca vão ao laudo/Finding**, só à trilha de auditoria.

---

## 2. OS prontas (padrão da casa — specs xfail → mutação → PR)

### PR C1d — correção, menor diff, vai sozinho

```xml
<lang>Python 3.11 + httpx + pytest (webqa/sondagem.py, webqa/dominio.py; NÃO-CODEOWNERS)</lang>
<task>Corrigir dois defeitos de falha silenciosa: G2 (IPv6 quebra a URL pinada) e G3 (procedencia curada nunca chega ao Finding).</task>
<context>_url_pinada monta f"{scheme}://{ip}:{porta}{path}" — IP v6 vira URL malformada e sorted(ips)[0] escolhe família por ordem lexicográfica. Finding (dominio.py) não tem campo procedencia; sondar_caminho o omite embora CaminhoSensivel o carregue do YAML.</context>
<rules>
- Pense passo a passo antes de responder.
- G2: colchetes em literal IPv6 na URL pinada; escolha de IP determinística e explícita por família (não sorted() lexicográfico). Host/SNI seguem o hostname; TLS jamais desligado.
- G3: adicionar procedencia (opcional, default "") ao Finding com a MESMA sanitização dos outros campos; propagar caminho.procedencia no return. Campo opcional → A/B sem procedencia continuam válidos.
- esperado.json e os 3 portões intactos; sem rede real (MockTransport + getaddrinfo dublado).
</rules>
<aceite>
- Alvo dual-stack com IPv6 primeiro → probe conecta a URL bem-formada (colchetes), sem _FALHA_DE_REDE.
- Finding de Fase C carrega a procedencia da entrada curada; Finding sem procedencia (A/B) continua válido.
- Escolha de família é determinística e testável (mesmo conjunto de IPs → mesmo IP pinado).
</aceite>
<testes>
- getaddrinfo dublado devolve {v6, v4}; sem o fix o probe falha, com o fix conecta (prova por mutação).
- plantar Finding(fase="C") sem procedencia no template antigo → teste do campo reprova; com propagação → passa.
- CaminhoSensivel com procedencia="OWASP WSTG-CONF-004" → aparece no Finding, sanitizada.
</testes>
<recomendacao>
- Separe verificação (mock: IPv6/procedencia reintroduzidos reprovam) de validação (dogfooding contra o fixture).
</recomendacao>
```

### PR C1e — resiliência + auditoria (mesma região do laço)

```xml
<lang>Python 3.11 + httpx + pytest (webqa/sondagem.py; NÃO-CODEOWNERS)</lang>
<task>G1 circuit-breaker (abortar, não só desacelerar), G5 evento de descarte soft-404, G4 registrar abortos de governança no AuditLog, G6 timeout granular; + extrair 3 funções puras (higiene) na mesma região.</task>
<context>recuos_seguidos só faz backoff e continue (nunca break); posse-divergente retorna antes do log existir; kill-switch dá break sem registrar; descarte soft-404 é return None mudo; TIMEOUT_S é escalar.</context>
<rules>
- Pense passo a passo antes de responder.
- G1: MAX_RECUOS_SEGUIDOS (const) → abortado_por="circuit-breaker"; N erros de rede seguidos idem. Piso de rate-limit e teto de backoff invariantes.
- G4: criar/receber o AuditLog ANTES dos portões e registrar posse-divergente e kill-switch (sem expor IP).
- G5: log com evento="descartado:soft-404". G6: httpx.Timeout(connect, read, write, pool) respeitando o piso.
- (higiene) extrair avaliar_resposta_em_finding (pura), executar_fallback_get (a única exceção ao HEAD-only, isolada) e calcular_espera_backoff (piso invariante) — sem mudar lógica.
</rules>
<aceite>
- 200 caminhos em 429 permanente → aborta em MAX_RECUOS_SEGUIDOS com abortado_por="circuit-breaker", inconclusivo=True.
- AuditLog contém as linhas de posse-divergente e kill-switch; nenhum IP em claro.
- Descarte soft-404 gera evento no log; avaliar_resposta_em_finding testável sem mockar httpx.
</testes>
<testes>
- recuos_seguidos == MAX → break com circuit-breaker (mutação: remover o break → run dorme demais, teste de tempo reprova).
- abort por kill-switch → 1 linha no log; sem o registrar → teste reprova.
- calcular_espera_backoff nunca abaixo do piso nem acima do teto.
</testes>
<recomendacao>
- Cubra unidade (funções puras) e sistema (laço aborta): as funções extraídas são o nível que faltava para testar o veredito sem rede.
</recomendacao>
```

### PR C1f — diagnóstico de posse (escopo.py, CODEOWNERS ⚠)

```xml
<lang>Python 3.11 stdlib + pytest (webqa/escopo.py; CODEOWNERS — revisão do dono)</lang>
<task>G7: verificar_posse distingue as 4 causas do frozenset vazio (host não listado, snapshot vazio, divergência/takeover, falha de resolução) para diagnóstico, sem alterar a POLÍTICA de bloqueio nem expor IPs no laudo.</task>
<context>verificar_posse hoje retorna frozenset() para 4 causas com um rótulo só; a docstring já as lista. O contrato de retorno (frozenset de IPs pinados quando há posse) não pode mudar — a C1c depende dele.</context>
<rules>
- Pense passo a passo antes de responder.
- Manter o retorno frozenset[str] (posse) / frozenset() (sem posse); o diagnóstico sai por canal separado (motivo estruturado consumido pelo abort), não trocando o tipo.
- IPs e detalhe de rede NUNCA vão ao Finding/laudo — só ao AuditLog/motivo do abort.
- Política de bloqueio idêntica: qualquer causa continua abortando o alvo.
</rules>
<aceite>
- Cada uma das 4 causas produz um motivo distinto e legível no abort/log; o comportamento de bloqueio é o mesmo de antes.
- posse válida → mesmo frozenset de IPs de hoje (C1c intacta); nenhum IP no laudo.
</aceite>
<testes>
- host ausente → motivo "nao-listado"; snapshot vazio → "sem-baseline"; atuais≠baseline → "divergencia"; getaddrinfo falha → "sem-resolucao".
- posse ok → frozenset idêntico ao atual (sem regressão da C1c).
</testes>
<recomendacao>
- Separe verificação (as 4 causas, getaddrinfo dublado) de validação (abort real mostra o motivo certo).
</recomendacao>
```

---

## 3. Rejeições (furam invariante — confirmadas no código)

- **Probes adaptativos/condicionais** — quebram `executado × esperado` (denominador
  móvel) e o determinismo. Não.
- **Triagem por LLM** — `test_convencoes` proíbe `sondagem.py` importar `llm` (por AST). Não.
- **Canary de egresso externo** (`ifconfig.me`) — host fora do escopo. Pré-check, se
  algum dia, é `HEAD /` no próprio alvo já autorizado.
- **Correlação auto-escalando severidade a "crítico/takeover"** — laudo especulativo;
  severidade é do caminho curado. Só como anotação/agrupamento.
- **WAF fingerprint → Finding** — falso-negativo por design. Header no AuditLog, ok; Finding, não.
- **Swagger/GraphQL lendo corpo** — quebra corpo-zero; `/openapi.json` público por design.
  Exceção estreita: existence-probe HEAD na lista curada.
- **respx/freezegun** — contra stdlib-first; `MockTransport` + `dormir` injetado +
  `getaddrinfo` dublado já cobrem em ms.
- **Contradição entre analistas:** um quer `GH_TOKEN` no job, outro quer abortar se
  existir → fica a sanitização (job de segurança sem secret de deploy); auto-issue
  vive em passo separado do pipeline, com token próprio mínimo.

---

## 4. Ordem de execução e itens já enfileirados

```
PR C1d (G2 IPv6 + G3 procedencia) — correção, menor diff, sozinho
PR C1e (G1 breaker + G5 + G4 + G6 + extração) — resiliência/auditoria
PR C1f (G7) — CODEOWNERS, revisão do dono
C2 (CODEOWNERS, já na fila) — soft-404 dinâmico · canários (A.4) · --multi-alvo ·
    baseline.yaml · SARIF · posse DNS-TXT · poda curada · +MITRE/OWASP se couber
    (obs.: G3 torna o campo `padroes` MITRE redundante — reusar procedencia)
Backlog/defer — G8 hash-lock da lista · correlação-como-anotação ·
    to_curl(--resolve p/ casar IP pinado+SNI) · ResultadoSondagem.to_dict()
```

**Balanço do lote (~35 sugestões):** ~9 já feitas (2 não percebidas pela triagem
anterior), 7 gaps reais (G1–G7), ~6 defer, ~6 furam invariante. Os dois bugs
concretos (IPv6, procedencia órfã) vieram de um único analista que leu o repo.

## 5. Pendências do dono (não-código)
Apagar `danzeroum-patch-1`/`-2`; assinar commits para frente (Unverified é
cosmético — nunca reescrever história, o ruleset bloqueia force-push); portão do
escopo do `docker.danzeroum.com`. Required check: já feito pelo ruleset.
