# Fase C — Revisão 3 (rodada final de avaliação Pareto)

> Adendo a `docs/FASE-C.md` + `-revisao-1.md` + `-revisao-2.md`. Conferido contra o
> código. Esta é a **última rodada de revisão**: os retornos caíram (ver §E), e o
> gargalo agora é executar o C0, não somar mais Pareto. **Nenhum trecho das
> análises deve ser colado literalmente.**

## A. Correções de fato (uma delas corrige a própria Revisão 2)

1. **`mesma_origem` é casamento EXATO após tirar só o `www.`** (`_raiz_do_host`).
   `cdn.alvo.com`/`api.alvo.com` são terceiros; só `www.alvo.com == alvo.com`.
   → As análises que temiam "subdomínio entra no escopo por reuso de
   `mesma_origem`" erram no fato, mas a conclusão certa é outra: **o escopo NÃO
   usa `mesma_origem`** (ela dobra `www`↔apex, bom para asset de 1ª parte na Fase
   A, ruim para autorização). Escopo usa **origem exata via `auth.origem_de`**,
   host a host. **Corrige o B2.4.**
2. **`make_client` seta `follow_redirects=True`** e é cliente de sessão com
   credencial. `sondagem` **não o reusa**: cliente próprio, stateless,
   `follow_redirects=False`. (Default do httpx é `False`; o override é do
   `make_client`.)
3. **`parece_html`/`assinatura` recebem `bytes`** — ferramentas de corpo (Fase B).
   Soft-404 na Fase C é **só de header** (`cabecalho()`), nunca corpo.
4. **`find_secrets(…, fase="A")` tem default** — fase errada silenciosa. Tornar
   `fase` obrigatório fecha na assinatura.

## B. Incorporado (por PR)

### PR-C0b (fatiado em C0b-i gates / C0b-ii escopo)
- **B3.1 — Escopo por origem exata (`auth.origem_de`), não `mesma_origem`.** Teste:
  `cdn.x.com` e `www.x.com` reprovam quando só `x.com` está listado. Cada host
  autorizado é listado explicitamente (a prova de posse TXT do R-C6 é por hostname).
- **B3.2 — `require_discovery()` + `require_escopo()`** com docstrings no rigor do
  gate `WEBQA_LLM_ENABLED` (o mais completo do `gates.py`), e a narrativa de
  abertura do módulo atualizada de "dois gates" para a lista completa. Mensagens de
  skip com prefixo `[gate:discovery]` / `[gate:escopo]` / `[gate:active_probes]`.
- **B3.3 — `KILL_ENV="WEBQA_ACTIVE_PROBES_KILL"` + `kill_switch_active()`** no
  `gates.py` (o kill-switch citado no plano nunca fora ligado).
- **B3.4 — Testes negativos dos três gates atuais** em `test_gates.py` antes de
  somar dois; e `require_escopo` provado como `skip` (não `fail`).
- **B3.5 — `escopo` no registro `FRONTEIRAS_DE_REDE`** de `test_fronteira_de_rede.py`
  (comparando `esta_no_escopo` × `origem_de` para o mesmo par).
- **B3.6 — Teste AST de congelamento do `sourcemap_referenciado`** (nada baixa o
  `.map` fora do gate) — a invariante já está no docstring, faltava o detector.
- **B3.7 — Cabeçalho em `test_fase_c_travada.py`** listando quais assertions serão
  invertidas em C0d × quais permanecem — é o que o analista assina no sign-off.

### PR-C0c (modelo / auditoria)
- **B3.8 — `find_secrets` com `fase` obrigatório** (remove o default `"A"`;
  atualização mecânica dos chamadores A/B por grep).
- **B3.9 — Anti-markup na `remediacao`** do dado curado: carregador rejeita `<`
  (`sanitize_text` é anti-segredo, não anti-XSS) e o `report_html` escapa no render.
- **B3.10 — Auditoria: `sanitize_text(url)` antes de gravar + supressão da
  query-string** para caminhos curados (query em `/.git/HEAD` é suspeita por
  definição).
- **B3.11 — Pré-checagem de ambiente (opcional, `WEBQA_STRICT_ENV=1`)**: aborta se
  token sensível (`AWS_ACCESS_KEY_ID`, `GH_TOKEN`, …) estiver no ambiente do job —
  trava em código, complementa o R-C9 (job de privilégio mínimo).

### PR-C0d (abertura da trava)
- **B3.12 — `dry-run-surface.json` como `@dataclass(frozen=True)`** serializado por
  `dataclasses.asdict` (diff determinístico), com `SURFACE_SCHEMA` asserido; **gerado
  só do `escopo-…yaml.example`**, com teste de que nenhum host real vazou (R-G5,
  extensão do R-C10).

### PR-C1a (`sondagem.py`)
- **B3.13 — Cliente próprio, stateless, `follow_redirects=False`; `3xx` = finding
  (média), nunca seguido.** Fecha escape de escopo por redirect e contaminação de
  sessão.
- **B3.14 — Finding por status puro** (200 = exposição), nunca consulta `avaliavel`
  — trata `.env` vazio (`200 + Content-Length: 0`) como exposição. Refina B2.10.
- **B3.15 — Soft-404 só por header** via `cabecalho()` (Content-Type esperado +
  `CF-Cache-Status`/`Via`), com nota-âncora de que `parece_html`/`assinatura` são
  Fase B. Refina B2.11.
- **B3.16 — Kill-switch no laço interno** (aborta o host corrente, registra o
  evento) — mesmo mecanismo do abort por 429/503, não só na entrada do teste.
- **B3.17 — Contador executado × esperado → run `inconclusivo` em execução
  parcial** (R-C16: falha de infra que parece "zero findings = tudo seguro").
- **B3.18 — Campo opcional `padroes` (MITRE ATT&CK / OWASP ASVS)** no dado curado,
  exportado no laudo → findings mapeáveis a compliance. Backward-compatible.
- **B3.19 — `to_curl()` por finding reproduz o HEAD** (existência), não um GET de
  corpo — mantém "detectar-e-reportar" no ticket de remediação.

### C3 (backlog opcional)
- Relatório de obsolescência do dado curado (cron mensal que abre issue; nunca
  adiciona caminho sozinho).

## C. Rejeitado ou redimensionado
- **Hash de integridade da lista cravado no código — rejeitado.** Redundante:
  CODEOWNERS (B2.1) + git já dão integridade; um PR malicioso atualizaria o hash
  junto. O controle real é a revisão, não o hash autoreferente.
- **Retry com backoff — redimensionado.** Falha transitória → caminho
  `inconclusivo` e contado (alimenta B3.17). Retry é mais requisição no alvo,
  contra o respeito a ele.
- **`assinatura()` no `Range: 0-0` — rejeitado.** Reintroduz leitura de corpo,
  contra o zero-corpo (B2.9). Soft-404 fica só por header.
- **Canary de egresso a `ifconfig.me` — redimensionado.** Troca por contador
  interno (B3.17) / canary contra host do próprio escopo — não abre egresso a
  terceiro.
- **Warning "C2 sem C1" — baixa prioridade.** Os gates são ortogonais de
  propósito; acoplar mesmo por warning é ruído. Ordem operacional, não segurança.

## D. Riscos consolidados desta rodada
- **R-C16** — execução parcial vira falso "seguro" → B3.17 (contador → inconclusivo).
- **R-C-redirect** — redirect leva probe fora do escopo → B3.13.
- **R-C-vazio** — `.env` vazio (200) lido como ausência → B3.14 (status puro).
- **R-G5** — `dry-run-surface.json` público vaza alvos → B3.12 (gerado do `.example`).

## E. Fecho da revisão
Três rodadas trouxeram, em ordem decrescente: mudanças de premissa (escopo
estrutural, takeover de subdomínio, split de gate) → refinamentos com âncora →
sobretudo correção de alucinação e ajuste fino. O plano está **sobre-especificado
em relação a uma única linha de código de sondagem que ainda não existe**. Uma
quarta rodada renderia mais correção-de-LLM do que plano. O próximo passo de maior
valor não é mais Pareto — é **executar o C0** (governança, zero sondagem) e deixar
os detectores, provados por violação plantada, dizerem o resto. A trava
(`test_fase_c_travada.py`) segue fechada até C0a–C0d entrarem com a inversão
assinada.
