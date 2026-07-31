# Fase C — Revisão 2 (segunda rodada de avaliação Pareto)

> Adendo a `docs/FASE-C.md` + `docs/FASE-C-revisao-1.md`. Cada item foi conferido
> contra o código real antes de entrar. As análises seguem sendo bom moinho de
> hipóteses e péssima fonte sobre o código (ver §A). **Nenhum trecho das análises
> deve ser colado literalmente.**

## A. Correções de fato (reposicionam várias sugestões)

1. **`httpx` é síncrono** na suíte (`make_client → httpx.Client`). O único `async`
   está no `burst()` do teste de *carga* (marcador `load`, fora da Fase C). Logo
   "circuit breaker via `asyncio.timeout`" está errado no mecanismo: usar o
   `timeout=` do httpx + orçamento de relógio no laço síncrono.
2. **Sem `pytest-xdist` e sem `pre-commit`** no repo; a suíte é sequencial por
   desenho. "Lock de auditoria para workers paralelos" e "o projeto já usa
   pre-commit" partem de premissa falsa. Invariante da casa é *teste* (detector por
   AST), não hook externo.
3. **Ancorados e corretos** (elevam a sugestão): `Finding.__post_init__` sanitiza
   `evidencia` e `recurso`; existem `TETO_CORPO_BYTES=512_000`, `Corpo.avaliavel`,
   `ler_corpo` (devolve `None`, nunca parcial, ao truncar), `mesma_origem`/
   `_raiz_do_host`, `sourcemap_referenciado` e `find_secrets`.

## B. Incorporado ao plano (por PR)

### PR-C0a — governança
- **B2.1 — CODEOWNERS estende a `data/caminhos-sensiveis.yaml`.** Fecha "lista de
  caminhos weaponizada via PR" (R-C12): cada item novo exige `procedencia` e
  revisão de code owner.

### PR-C0b — `escopo.py` / gates / fronteira
- **B2.2 — Split do gate.** `WEBQA_DISCOVERY_AUTHORIZED=1` para C1 (descoberta
  read-only) e `WEBQA_ACTIVE_PROBES_AUTHORIZED=1` **reservado a C2** (escrita/
  interação). Novo `require_discovery()` ao lado de `require_active_probes()`, no
  idioma que o `gates.py` já pratica ("intrusões de natureza diferente"). Autorizar
  descoberta não autoriza escrita — reforça o "sem C2 em produção".
- **B2.3 — `require_escopo(url)` como gate ortogonal.** Escopo e autorização são
  controles independentes; ambos disparam. `pytest.skip` (não `fail`) fora do
  escopo. Torna "esqueci de checar o escopo" impossível por fluxo.
- **B2.4 — Ponto único de verdade para host.** `esta_no_escopo` delega a
  `dominio.mesma_origem` a comparação de host e a `rede.ips_de` o snapshot de IP
  (que ancora R-C6/R-C7). Não reimplementa parse de host.
- **B2.5 — Recusa de C2 em `ambiente=producao` testada já aqui** (não junto do
  PR-C2). Fecha R-GRAVE-4: a invariante nasce com detector antes de a capacidade
  existir.
- **B2.6 — `dry-run-surface.json` como evidência.** `--dry-run` (default) emite a
  superfície ordenada `{host, caminho, categoria, severidade_esperada}`; ela é
  comitada no PR-C0d e o diff dela é o que o analista assina.

### PR-C0c — modelo e auditoria
- **B2.7 — `Finding.remediacao` sanitizado.** No `__post_init__`, ao lado das
  sanitizações que já existem:
  ```python
  object.__setattr__(self, "remediacao", sanitize_text(str(self.remediacao)))
  if self.fase == "C" and not self.remediacao.strip():
      raise ValueError(f"Finding de Fase C exige remediação: {self.recurso}")
  ```
  (Vazio em A/B é intencional — comentar no código. `remediacao` herda o
  mascaramento; sem isso, uma URL com `?token=` na remediação escaparia.)
- **B2.8 — `webqa/audit.py` como módulo próprio.** `AuditLog(run_id, escopo_hash)`
  injetável em `sondagem`; SRP como o `gates.py`, e o teste de não-vazamento vira
  trivial (injeta um `AuditLog` falso). A linha passa por: mascaramento por valor
  (`auth.py`) → supressão de query-string sensível → **escape de caracteres de
  controle** (`\r`, `\n`, `\t`) e truncamento de campo longo (anti log-injection).
  Timestamp timezone-aware (`datetime.now(timezone.utc)`).

### PR-C1a — `sondagem.py`
- **B2.9 — Zero corpo, estrutural.** `TETO_CORPO_FASE_C = 0` + assert; se algum dia
  houver leitura, passa por `ler_corpo` (herda teto/mascaramento), nunca constrói
  `Corpo` direto.
- **B2.10 — "Veredito sobre nada" (Corpo.avaliavel).** 2xx cuja natureza não se
  confirma → finding "exposição provável — confirmar manualmente", severidade
  média, **nunca omitido**.
- **B2.11 — Heurística de `Content-Type` (anti soft-404).** Cada caminho curado tem
  `content_type_esperado`; `text/html` onde se espera o arquivo cru → inconclusivo,
  não finding alto. Lê só o header (respeita HEAD-only). Fecha R-C14.
- **B2.12 — Schema do dado curado estrutural.** Carregador impõe `MAX_CAMINHOS`,
  `CATEGORIAS_VALIDAS` (frozenset) e campos obrigatórios (`path`, `categoria`,
  `severidade`, `remediacao`, `procedencia`) — arquivo fora do schema **falha ao
  carregar**. Testado estendendo `test_config.py`.
- **B2.13 — Orçamento de relógio por host + 429.** Teto absoluto por host (abre o
  "circuit breaker", aborta o resto do alvo, `status=timeout` na auditoria) via
  `timeout=` do httpx no laço síncrono; 429/503 encerram o alvo (backoff adaptativo
  antes do abort é polimento opcional).

### Testes — ancorar no que existe (idioma da casa)
- Caso 500 com header secreto plantado → `test_vazamento_de_credencial.py` (R-C8).
- Piso de rate-limit (`config=0` não zera) → `test_etiqueta.py`.
- Convenções da Fase C por AST (sondagem não importa `llm`; consumidor de fronteira
  registrado; check ativo usa o gate) → `test_convencoes.py`.
- `escopo` no registro `FRONTEIRAS_DE_REDE` → `test_fronteira_de_rede.py`.
- Congelamento da fronteira `sourcemap_referenciado` (nada baixa o `.map` sem gate)
  → teste dedicado curto.
- Teste negativo da campanha (host de terceiro reprova `esta_no_escopo`), fixture
  lendo `campanha.yaml`.
- Specs `xfail(strict=True)` da dimensão ativa no `summary.json` antes da
  implementação → `test_sumario.py` / `test_seguranca_checks.py`.

## C. Rejeitado ou redimensionado (com motivo)

- **Cache de probes (pickle) — rejeitado.** Cria `.webqa-cache/` com respostas
  serializadas (pickle = risco de desserialização, o bandit acusa) e a própria
  superfície de "cache poisoning por vhost" que a análise depois lista como risco;
  resolve um não-problema (dezenas de HEADs sob `MAX_CAMINHOS`). Default seguro é
  **não cachear**.
- **`asyncio.timeout` / lock de auditoria por xdist — rejeitado no mecanismo.**
  Stack síncrono, sem xdist. Nota: "se entrar xdist, um arquivo de auditoria por
  worker (pid no nome)". Não construir agora.
- **DoH obrigatório e ranges de GitHub Pages em `rede.py` — redimensionado.** DoH
  adiciona egresso a resolver de terceiro (contra local-only/stdlib-first) para
  ameaça de nicho → opcional para alta garantia. CDN compartilhada é *classificação
  de escopo* (site estático em infra de terceiro tem pouco sinal para forced
  browsing), não faixa de IP cravada no módulo de fronteira local.
- **Double-mask de `find_secrets` — não é gap.** `find_secrets` sobre `evidencia`
  já mascarada devolver vazio é o resultado desejado — já é o que
  `contem_segredo_em_claro` prova.
- **Sandbox-as-a-Service (C2) — aceito como forma do B.4, não como Pareto de
  agora.** Entra quando C2 for retomado.
- **Drift de dependências / `WEBQA_SCOPE_FILE` — orthogonal/clarificação.** Drift é
  hardening do repo inteiro, fora do escopo deste plano. Path do escopo via
  env/secret já está implícito no B.8 (escopo real fora do repo público); é config,
  não "gate".
- **Fingerprint de WAF / auditoria cega / diff em C1 / alerta no PR — nice-to-have
  C3.** Aceitos como refinamento de baixa prioridade; o mascaramento já é por
  valor, então o risco de "mascara parcial" da auditoria cega é menor que o
  alegado.

## D. Riscos novos consolidados
- **R-C11 — ban de IP por rate-limit agressivo** → dobrado no R-C9 (runner dedicado
  de segurança, egresso restrito) + 429 aborta o alvo.
- **R-C12 — lista de caminhos weaponizada via PR** → B2.1 (CODEOWNERS no arquivo de
  dados + procedência obrigatória).
- **R-C13 — cache poisoning** → eliminado por não haver cache (§C).
- **R-C14 — soft-404 vira falso positivo alto** → B2.11 (heurística de Content-Type).
- **R-C15 — log-injection via resposta** → B2.8 (escape de controle na auditoria).

## E. Sequência de PRs (inalterada na forma; itens absorvidos)
`C0a → C0b → C0c → C0d → C1a`, com os itens B2.* dentro dos PRs já previstos.
Nenhum PR novo; governança (C0) segue precedendo qualquer sondagem, e a inversão
assinada de `test_fase_c_travada.py` (C0d) continua o único ato que abre a trava.
