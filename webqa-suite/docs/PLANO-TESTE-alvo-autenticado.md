# Plano de Teste — Alvo autenticado `docker.danzeroum.com`

Roteiro executável para o desenvolvedor rodar a bateria completa contra um
ambiente de teste protegido por HTTP Basic Auth (nginx), na VPS onde o Chromium
tem egresso real. Cada fase traz comandos e critérios de aceite.

---

## ⚠️ Segurança da credencial — leia antes de tudo

- A credencial vive **somente em variável de ambiente na VPS**, nunca em arquivo
  versionado, nunca em mensagem/chat, nunca no `config.yaml`.
- Use um **usuário de teste descartável**, com escopo mínimo, revogado ao fim.
- A credencial que circulou por canais não-seguros deve ser **rotacionada** após
  o teste — trate qualquer senha que saiu do ambiente como comprometida.
- **Fase 4 (verificação de vazamento) é obrigatória** antes de qualquer laudo
  sair da VPS. Um relatório de segurança que vaza a própria credencial de acesso
  é o pior resultado possível.

---

## Perfil do alvo e postura

| Item | Decisão |
|---|---|
| Alvo | `https://docker.danzeroum.com/` — ambiente de TESTE do próprio dono |
| Entrada | nginx HTTP Basic Auth |
| Fase C (sondagem ativa) | **Autorizada** (alvo é do dono) mas **conscientemente DESLIGADA** |
| Modo | Exploração **passiva autenticada** — navega só o que a app oferece |
| Carga | Desligada (`WEBQA_LOAD_AUTHORIZED` nunca setado) |
| Ambiente de execução | VPS (Chromium com egresso real; o ambiente de dev tem proxy que zera Web Vitals) |

**Passivo autenticado ≠ Fase C.** Passivo autenticado navega as telas internas
seguindo apenas links/botões presentes no DOM. Nunca adivinha URL, nunca sonda
`/admin` sem link, nunca `/.git`. Isso permanece Fase C, permanece desligado.

---

## Pré-requisitos de implementação

| OS | Estado | O que destrava |
|---|---|---|
| **OS-37** — HTTP Basic Auth (credencial por env, sanitização por valor) | ✅ em `main` (PR #35) | Fases 0, 1, 3, 4 e 5 |
| **OS-38** — exploração passiva autenticada (crawl por proveniência de DOM, guarda AST) | ⏳ registrada, **não implementada** | Fase 2 |

**Rodar em duas ondas.** Com a OS-37 em `main`, o dev já executa Fases 0, 1, 3, 4
e 5 e entrega um laudo autenticado rico — a bateria passiva inteira roda contra a
área logada da home. A **Fase 2** (navegação pelas telas internas descobertas por
link) só existe depois da OS-38; até lá, a superfície coberta é a da página
autenticada de entrada e do que ela carrega, não a do site interno inteiro.

Alternativa: implementar a OS-38 antes e rodar o plano completo de uma vez.

---

## Variáveis de ambiente (base de todas as fases)

```bash
export WEBQA_TARGET_URL="https://docker.danzeroum.com/"
export WEBQA_BASIC_AUTH_USER="<usuario-de-teste>"
export WEBQA_BASIC_AUTH_PASS="<senha-no-ambiente-nunca-em-arquivo>"

# NÃO definir — mantêm Fase C e carga desligadas:
# WEBQA_ACTIVE_PROBES_AUTHORIZED
# WEBQA_LOAD_AUTHORIZED
```

Definir **só uma** das duas variáveis de auth é erro de configuração: a suíte
aborta nomeando a que falta, em vez de cair para anônimo em silêncio.

---

## Fase 0 — Pré-voo

Prova que o ambiente funciona e que a credencial entra, sem medir nada ainda.

```bash
# 0.1 Smoke da VPS: Chromium com egresso, DNS, suíte sobe
make vps-smoke

# 0.2 Preflight SEM credencial → deve orientar, não cascatear falha
env -u WEBQA_BASIC_AUTH_USER -u WEBQA_BASIC_AUTH_PASS \
  pytest -m backend -k http_basics    # espera "alvo exige autenticação"

# 0.3 Credencial ERRADA → mensagem própria, distinta da anterior
WEBQA_BASIC_AUTH_PASS="errada-de-proposito" \
  pytest -m backend -k http_basics    # espera "recusou a credencial informada (401)"

# 0.4 Login VÁLIDO → passa da porta (200, não 401)
pytest -m backend -k http_basics      # espera 2xx na home autenticada
```

**Aceite Fase 0**
- Smoke 5/5 (ou passos equivalentes) verde.
- Sem credencial → mensagem orientada `defina WEBQA_BASIC_AUTH_*`, **zero** falha
  de teste (a suíte para antes de medir, não depois de reprovar).
- Credencial errada → mensagem **diferente**, dizendo que foi recusada.
- Com credencial → home autenticada responde 2xx; a suíte passou da porta.

---

## Fase 1 — Bateria passiva: anônima × autenticada

Rodar **duas vezes** e comparar. A diferença entre os laudos mostra quanto da
aplicação só existe após o login.

### Passada A — anônima (linha de base)

```bash
env -u WEBQA_BASIC_AUTH_USER -u WEBQA_BASIC_AUTH_PASS \
  WEBQA_REPORT_DIR=report/anon \
  pytest -m "not load and not verification"
```

> Contra alvo protegido, esta passada **para no preflight** — que é o resultado
> honesto: sem credencial não há o que medir. A linha de base útil aqui é a
> própria mensagem de orientação. Se o alvo tiver alguma rota pública, ela mede
> essa rota; não force.

### Passada B — autenticada (bateria completa)

```bash
WEBQA_REPORT_DIR=report/auth pytest -m backend      # TTFB, cache, compressão, headers
WEBQA_REPORT_DIR=report/auth pytest -m frontend     # HTML/assets/Web Vitals reais (Chromium)
WEBQA_REPORT_DIR=report/auth pytest -m ux           # WCAG + arquitetura de informação
WEBQA_REPORT_DIR=report/auth pytest -m lgpd         # cookies de sessão REAIS, trackers, terceiros
WEBQA_REPORT_DIR=report/auth pytest -m seguranca    # segredos em JS interno, MIME, Fase A+B
WEBQA_REPORT_DIR=report/auth pytest -m functional   # links e formulários internos
```

Ou tudo de uma vez:
```bash
WEBQA_REPORT_DIR=report/auth pytest -m "not load and not verification"
```

**Onde a área logada rende mais**
- `lgpd`: cookie de sessão real → flags `HttpOnly`/`Secure`/`SameSite` auditáveis (só existem após login).
- `seguranca`: JS de painel interno costuma ter mais segredos esquecidos que a landing.
- `frontend`: Web Vitals das telas internas, medidos de verdade (Chromium com egresso).

**Aceite Fase 1**
- Passada B gera laudo em `report/auth` sem erro fatal.
- Todo `error`/`skipped` traz motivo legível; nenhum PASS silencioso.
- Nenhuma métrica de renderização "não medida" (prova de que o Chromium alcançou
  o alvo — se aparecer, é ambiente, refazer na VPS). No ensaio local o
  `summary.json` trouxe `ttfb_ms`, `fcp_ms`, `lcp_ms`, `cls`, `dcl_ms` e
  `page_kb` preenchidos; ausência de qualquer um deles na VPS é sinal de
  ambiente, não do alvo.
- Sete dimensões representadas em `by_dimension` — **menos `functional`**, pelo
  limite do `robots.txt` descrito abaixo.
### ⚠️ Limite conhecido: a dimensão `functional` fica cega no alvo real

`PoliteFetcher` (OS-27) busca o `robots.txt` **anonimamente** — só com
`User-Agent`, sem credencial. Atrás de Basic Auth isso responde **401**, e a
regra da camada de etiqueta é: política ilegível → alvo pulado. Verificado
contra o alvo de verdade:

```
$ python -c "from webqa.etiqueta import PoliteFetcher; \
    print(PoliteFetcher('WebQA-Suite/1.0', 20).preparar('https://docker.danzeroum.com/').motivo)"
robots.txt respondeu HTTP 401 — alvo pulado
```

Consequência prática: **`checks/functional/test_links.py` pula o crawl inteiro**
contra qualquer alvo público protegido por Basic Auth. Não é falha e não é
defeito do alvo — é a etiqueta funcionando como projetada, já que não conseguir
ler a política de alguém não é licença para ignorá-la. Mas significa que a
dimensão `functional` **não produz veredito** nesta campanha.

Isso não aparece no alvo fixture local: loopback é isento de etiqueta por
decisão de IP resolvido, então lá o crawl roda e passa — e um ensaio local
sozinho daria a impressão errada.

**Não contornar por conta própria.** Deixar o crawl anônimo ler `robots.txt` de
um host protegido, ou pular a consulta, é decisão de arquitetura, não de
execução. O caminho certo é a **OS-38** passar a credencial ao `PoliteFetcher`
para a origem do próprio alvo — legítimo, porque o alvo é do dono — sob a mesma
política de origem+esquema da OS-37. Registrar como achado no retorno.

---

## Fase 2 — Exploração passiva autenticada (OS-38) — **bloqueada até a OS-38**

Navega as telas internas seguindo só links/botões do DOM, com **proveniência**
de cada URL registrada.

```bash
WEBQA_REPORT_DIR=report/auth pytest -m "seguranca or lgpd" --crawl-autenticado
# (flag/rota conforme a OS-38 implementar; ver docs da OS)
```

**Aceite Fase 2**
- Cada URL visitada tem origem registrada ("link em X") — **nenhuma adivinhada**.
- Página órfã (sem link apontando para ela) NÃO é visitada.
- Todos os checks passivos rodam contra as páginas internas descobertas.
- Laudo resultante é mais rico que o da Fase 1 isolada.

---

## Fase 3 — Sumário assistido por IA local (opcional)

Só se houver runtime LLM local (Ollama) na VPS. Nada sai da máquina.

```bash
export WEBQA_LLM_ENABLED=1
WEBQA_REPORT_DIR=report/auth python scripts/sumario.py
```

**Aceite Fase 3**
- `report/auth/sumario.md` gerado, rotulado "não é veredito".
- Sem Ollama → exit 0 em ≤2s, laudo determinístico intacto (sem sumário).
- O sumário nunca usa linguagem de certificação (guarda determinística ativa).

---

## Fase 4 — Verificação de vazamento (OBRIGATÓRIA)

**Não pular. É gate.** Antes de qualquer laudo sair da VPS.

> **Leia antes de rodar:** um `grep -ri "authorization"` genérico **acusa laudo
> limpo**. A sanitização preserva de propósito o NOME do cabeçalho e destrói só o
> VALOR — `Authorization: [AUTHORIZATION]` é o resultado correto, não um
> vazamento. O nome ajuda a localizar o achado; o valor é que não pode existir.
> Os gates abaixo procuram o **valor**.

```bash
# 1. A SENHA, em qualquer forma — o gate que mais importa. Deve sair VAZIO.
grep -rF "$WEBQA_BASIC_AUTH_PASS" report/

# 2. Valor de Basic não mascarado (base64 de verdade, não o rótulo). VAZIO.
grep -riE "basic [A-Za-z0-9+/]{8,}={0,2}" report/

# 3. Credencial embutida em URL (user:pass@host). VAZIO.
grep -rE '//[^/[:space:]"]+:[^/[:space:]"]+@' report/

# 4. INSPEÇÃO (não é gate): o que sobrou de `authorization` no laudo.
#    Só pode aparecer com o valor já substituído — [AUTHORIZATION] ou [SENHA].
grep -rhio "authorization[^,;\"<]*" report/ | sort -u
```

**Aceite Fase 4 (bloqueante)**
- Gates **1, 2 e 3** retornam VAZIO.
- Gate 4 mostra apenas ocorrências com valor já mascarado.
- Se qualquer gate 1–3 retornar algo: laudo contaminado → **NÃO entregar** →
  reportar ao arquiteto; a OS-37 tem um furo de sanitização a investigar.

> Os três gates foram exercidos nos dois sentidos durante a OS-37 (laudo limpo →
> 0; contaminação plantada → 1). Gate que nunca disparou não está provado.

---

## Fase 5 — Confirmação da fronteira (a Fase C ficou desligada?)

```bash
# Prova que nada ativo foi acionado nem vazou para o código:
pytest tests/test_fase_c_travada.py            # OS-36: guarda de AST verde
echo "[${WEBQA_ACTIVE_PROBES_AUTHORIZED}]"     # deve imprimir []
```

**Aceite Fase 5**
- `WEBQA_ACTIVE_PROBES_AUTHORIZED` nunca esteve setado durante a campanha.
- Teste de fronteira (OS-36) verde: nenhum caminho sensível, nenhuma geração de
  URL no código — passivo por construção.

---

## Checklist final antes de entregar o laudo

- [ ] Fase 0: login válido, preflight orientado, credencial errada distinguida
- [ ] Fase 1: laudo autenticado gerado, sem métrica "não medida"
- [ ] Fase 2: proveniência de URL registrada, zero URL adivinhada *(só após OS-38)*
- [ ] Fase 3: sumário (se Ollama) rotulado, ou ausência graciosa
- [ ] **Fase 4: gates 1–3 VAZIOS (bloqueante)**
- [ ] Fase 5: Fase C confirmadamente desligada, guarda AST verde
- [ ] Credencial de teste **rotacionada/revogada** após a rodada
- [ ] Rede da VPS **fechada** de volta após o teste

---

## O que o arquiteto valida no review (ordem)

1. **Fase 4 primeiro** — credencial nunca em nenhum artefato. Gate: se falhar, o resto não conta.
2. **Proveniência das URLs** (OS-38) — nada adivinhado; tudo veio do DOM.
3. **Fase C desligada** — env nunca setado; teste AST (OS-36) verde.
4. **Achados fazem sentido** — autenticado > anônimo; cada não-avaliado com motivo; cada segredo mascarado.

---

## Dependências e limites honestos

- **OS-37 está em `main`** (PR #35); **OS-38 não** — a Fase 2 fica para a segunda onda.
- Chromium só mede com egresso real → **rodar na VPS**, nunca no ambiente de dev
  com proxy (lá os Web Vitals nascem "não medidos").
- Este alvo é ambiente de teste do dono → a Fase C poderia ser ligada, mas a
  decisão é mantê-la desligada nesta campanha (passivo autenticado só).
- A suíte **não** manda a credencial para terceiro nem por `http://` claro
  (`webqa/auth.py::pode_enviar_credencial`): se o alvo redirecionar para outra
  origem, o acesso lá será anônimo — e isso aparece como 401/erro no laudo, não
  como senha vazada. É o comportamento desejado.
