# Dimensão LGPD — Fase 1 (bateria passiva)

Conformidade de privacidade **observável de fora**, por caixa-preta, apontando só a URL.

> **Nota epistêmica (vale para toda a dimensão).**
> Uma falha aqui **prova** não conformidade. Passar **não certifica** conformidade:
> base legal, contrato com operador, ROPA, prazos internos de retenção e governança
> não são observáveis por HTTP. A mesma nota está no código
> (`webqa/report.py::DIMENSION_NOTES`) e aparece no `report/summary.html` — quem lê
> o relatório não leu este documento.

```bash
make lgpd            # dimensão completa (usa navegador)
make lgpd-passivo    # só HTTP, sem Playwright
```

## Escopo da Fase 1: tudo é passivo

A bateria **carrega e observa**. Não clica em "aceitar", não recusa banner, não
submete formulário, não exerce direito de titular. Isso é decisão de arquitetura,
não limitação técnica: interagir com o sistema de um terceiro é intrusão de outra
natureza — pode criar registro de titular no alvo.

### Dois gates independentes (`webqa/gates.py`)

| Gate | Autoriza | Estado na Fase 1 |
|---|---|---|
| `WEBQA_LOAD_AUTHORIZED=1` | gerar carga (risco de disponibilidade) | em uso (`-m load`) |
| `WEBQA_ACTIVE_PROBES_AUTHORIZED=1` | sondagem **ativa**: submeter formulário, interagir com banner, exercer direito | **criado, não usado** |

Separados de propósito: autorizar carga não pode autorizar escrita no sistema do
alvo. O gate de sondagem ativa nasce antes do primeiro teste ativo porque guarda
criada junto com a funcionalidade nasce frouxa.

## Pacotes de trabalho entregues

| OS | Arquivo | O que verifica | Artigos |
|---|---|---|---|
| 01 | `webqa/trackers.py`, fixture `network_log`, `webqa/gates.py` | infraestrutura da dimensão | — |
| 02 | `checks/lgpd/test_consentimento.py` | tracker e cookie de analytics **antes** de qualquer aceite | 7º I, 8º §4 |
| 03 | `checks/lgpd/test_pii_transito.py` | PII em query string, Referrer-Policy, formulário pessoal em POST+HTTPS | 6º VII/VIII, 46 |
| 04 | `checks/lgpd/test_transparencia.py` | política alcançável, direitos do titular, canal do encarregado | 9º, 18, 41 |
| 05 | `checks/lgpd/test_terceiros.py` | inventário de terceiros (ROPA), SRI, fontes em CDN | 5º I, 37, 39, 46 |
| 06 | `checks/lgpd/test_retencao_observavel.py` | vida útil de cookie, Permissions-Policy, security.txt | 15, 16, 48 |
| 06 | `checks/ux/test_acessibilidade.py` | acessibilidade também como obrigação legal | LBI Art. 63 |

### Retenção **é** parcialmente observável

"Retenção não se testa por fora" é meia verdade. A vida útil declarada de um
cookie (`Max-Age`/`Expires`) **é** política de retenção publicada no protocolo:
cookie de 730 dias declara intenção de retenção por 730 dias. O que não se observa
é o prazo de retenção no banco do controlador — e esse limite está dito na nota
epistêmica, não escondido.

### Acessibilidade conta em duas dimensões

Os testes axe-core levam `[ux, lgpd, browser]`. No Brasil, site acessível é
obrigação legal (Lei 13.146/2015, Art. 63), não só boa experiência. O relatório
conta o teste nas **duas** dimensões e agrupa na primeira declarada (`ux`) —
`webqa/report.py` resolve a ordem por `item.iter_markers()`, que preserva a ordem
de declaração (`report.keywords` não preserva).

## Critério de FAIL vs xfail (único e auditável)

**FAIL** — obrigação legal inequívoca **e** observável:

- tracker disparando antes do consentimento; cookie `_ga`/`_fbp`/`_hj*` no primeiro load;
- ausência de link de política de privacidade; política sem os direitos do Art. 18; sem canal do encarregado;
- PII em query string; formulário com dado pessoal em GET ou fora de HTTPS;
- cookie com vida útil acima de 400 dias;
- script de terceiro sem SRI;
- Referrer-Policy **declarada** e permissiva (escolher vazar é decisão, não omissão).

**xfail informativo** — sinal de maturidade, sem obrigação direta:

- ausência de Referrer-Policy, Permissions-Policy, security.txt;
- fontes carregadas de CDN externo (Google Fonts);
- mais de 5 cookies de finalidade não identificável no primeiro load;
- cookie entre 180 e 400 dias.

**skip** — a suíte não tem como avaliar: política em PDF (parser é de HTML),
página sem formulários, ausência de `Set-Cookie`.

**Sempre PASS** — `test_inventario_terceiros`: é insumo de ROPA/DPA, informa e não
julga (a suíte não conhece os contratos de operador do controlador).

## Falsos positivos tratados

Bateria regulatória que reprova alvo conforme perde credibilidade. Casos cobertos
em `tests/test_lgpd_checks.py` (verificação, sem rede):

| Caso | Comportamento |
|---|---|
| host em `lgpd.allowed_third_parties` | nunca reprova — decisão documentada do controlador vence a heurística |
| `action` relativo em página HTTPS | resolvido com `urljoin` antes de validar o esquema |
| política publicada em PDF | skip explicando o limite |
| `www.alvo.com` vs `alvo.com` vs `cdn.alvo.com` | primeira parte (mesmo controlador) |
| `Expires` no passado (deleção de cookie) | passa |
| `Expires` malformado | tratado como cookie de sessão (na dúvida, a favor do alvo) |
| `meugoogle-analytics.com.br` | não é tracker (casamento por rótulo, não por substring) |
| cookie de sessão do alvo (`sessionid`) | não reprova |

## Privacidade da própria suíte

O detector de PII **é** o mascarador: `webqa/sanitize.py` é ponto único de verdade
(`find_pii` usa as mesmas regexes de `sanitize_text`). Se um padrão entra, passa a
ser detectado e mascarado no mesmo commit. URLs ofensoras vão ao relatório via
`safe_url` (query inteira removida); cookies são reportados só por **nome**;
o e-mail do encarregado é detectado e **não** reproduzido. `report/` é ignorado
pelo Git.

## Critério de saída da Fase 1 (ledger de estabilidade)

"Estável em produção" precisa ser um número verificável, não uma impressão.
`scripts/estabilidade.py` lê o `report/summary.json`, classifica a execução e
mantém o ledger versionado `docs/lgpd-estabilidade.json`:

```bash
make estabilidade                          # execução local: entra como informativa
python scripts/estabilidade.py --dry-run   # classifica sem gravar (uso do smoke-test)
WEBQA_ORIGEM=vps python scripts/estabilidade.py   # só no container oficial
```

A distinção que dá sentido à métrica:

| Sinal | Exemplo | Efeito na sequência |
|---|---|---|
| **Flake de infra** | `TimeoutError`, `TargetClosed`, `net::ERR_*`, Chromium ausente | **zera** |
| **FAIL determinístico** | tracker antes do consentimento, cookie de 730 dias, violação axe | **não zera** — a suíte funcionou; quem está errado é o alvo |
| Execução sem teste de navegador | `pytest -m "lgpd and not browser"` | ignorada (não conta nem zera) |

Cada entrada registra `{generated_at, dia_utc, origem, alvo_sha256,
browser_total, infra_flakes, streak}`. `generated_at` é a chave de
deduplicação: rodar o script duas vezes no mesmo summary não infla a sequência.
Ao atingir **10 dias consecutivos sem flake**, o script imprime
`FASE 2 DESTRAVADA`.

### Só o ambiente oficial move a métrica

> **Emenda de arquitetura — 2026-07-30.** O ambiente oficial deixou de ser o
> runner do GitHub e passou a ser o **container Docker da VPS**, com imagem
> fixada por digest — mais controlado que um runner hospedado, que troca a
> versão da imagem base sob os pés. Três consequências:
>
> 1. a origem não é mais **detectada** (`GITHUB_ACTIONS`), é **declarada** em
>    `WEBQA_ORIGEM`, injetada somente no container oficial;
> 2. a sequência **recomeçou do zero**: o streak mede a interação infra × alvo,
>    e a infra mudou. A entrada `ci` existente fica no ledger como histórico;
> 3. papéis separados — GitHub é CI de código, VPS é o **único escritor** do
>    ledger. O noturno do GitHub foi removido: dois escritores no mesmo arquivo
>    é conflito de push às 3h da manhã. Ver [`VPS.md`](VPS.md).

`origem` vale `vps`, `ci` ou `local`; valor ausente ou desconhecido degrada para
`local`. A sequência é **recalculada do histórico inteiro** a cada rodada:

| Regra | Por quê |
|---|---|
| Só entradas `origem: "vps"` contam | execução fora do ambiente oficial não é evidência de estabilidade dele; entradas `ci` e `local` ficam no ledger para auditoria, mas **não avançam nem zeram** |
| No máximo **uma por dia UTC**, valendo a primeira | dez execuções num dia não são dez dias estáveis |
| Origem desconhecida (`banana`, vazio, campo ausente) = `local` | **fail-safe**: erro de digitação no compose jamais pode inflar a métrica de confiança. No pior caso ela deixa de contar, nunca conta errado |

A saída informa a fonte: `streak 3/10 (vps, 3 dias distintos)`, mais uma nota de
histórico quando há entradas `ci` anteriores à emenda.

Recalcular em vez de incrementar a partir da última entrada tem um motivo: o
valor gravado passa a ser **derivável e auditável** — há teste que recomputa
sobre o ledger versionado, e outro que prova que **remover o histórico `ci` não
altera o número** (o histórico não contamina nem sustenta a conta).

Duas honestidades: `WEBQA_ORIGEM` é declaração do ambiente, não prova
criptográfica — quem tem push no repositório pode escrever o que quiser no
ledger; a barreira existe contra descuido, não contra falsificação deliberada
(isso exigiria assinar a entrada com credencial que só o runner oficial tem).
E a deduplicação por `generated_at` ignora a origem: se uma execução for
registrada localmente, aquela chave já está ocupada.

### O alvo fixture (`fixture_target/`)

A medição roda contra um **alvo fabricado e congelado**, nunca contra um site
alheio. Medir estabilidade contra produção mistura dois sinais: se o site muda, a
suíte "flaka" sem que nada tenha piorado — e ainda geraria tráfego automatizado
diário contra terceiros.

```bash
make fixture          # sobe o alvo em porta efêmera e imprime a URL
```

Violações que ele contém de propósito: GTM antes do consentimento, cookie `_ga`
com `Max-Age` de 730 dias, `?email=` em `href`, formulário GET/HTTP com campo de
e-mail, script de CDN sem SRI e imagem sem `alt`. Em transparência ele é
**conforme** — o contrato precisa provar os dois lados, senão um check que
reprova tudo passaria por "funcionando".

`fixture_target/esperado.json` é o contrato: a lista exata de FAILs que a
dimensão deve produzir. `tests/test_alvo_fixture.py` sobe o alvo, roda
`pytest -m lgpd` em subprocesso e compara — **nem a mais** (check reprovando
alvo conforme) **nem a menos** (check que parou de detectar e ninguém notou).
É o risco R7 aplicado à dimensão: sem esse contrato, um check quebrado tornaria
a medição de estabilidade uma mentira estável.

Limites declarados: o "CDN sem SRI" aponta para um domínio `.invalid`
(RFC 2606, nunca resolve) porque o check lê o **atributo** do HTML; e o único
contato com host externo é um `fetch` abortável para o domínio do tracker — o
teste depende do **registro da requisição**, nunca da resposta, e funciona
offline. Os dois testes de axe-core ficam **fora do contrato**: dependem de
baixar a biblioteca de um CDN, logo não são determinísticos.

### O noturno (container da VPS) e o smoke-test do GitHub

O noturno oficial roda no **container Docker da VPS** — sobe o fixture, confere o
contrato, roda a dimensão, classifica com `WEBQA_ORIGEM=vps` e commita o ledger.
Operação, agendamento e segredo estão em [`VPS.md`](VPS.md).

`.github/workflows/estabilidade.yml` sobreviveu como **smoke-test sem escrita**
(`workflow_dispatch` + `--dry-run`): descartar a capacidade de diagnosticar o
pipeline pelo GitHub seria jogar fora diagnóstico de graça — ele perdeu a caneta,
não os olhos. Um passo depois do dry-run **falha** se o ledger tiver sido tocado,
para que a garantia não dependa de boa vontade.

Nos dois ambientes o passo da dimensão roda tolerando falha: contra um alvo não
conforme a execução **reprova por definição** (7 FAILs de contrato). O código de
saída do pytest não diz nada sobre estabilidade — quem decide é o classificador,
lendo o `summary.json`. Falha do noturno, por si só, não zera a sequência.

Três decisões que valem registro:

- **A URL do alvo nunca entra no ledger** — só o `sha256`. O digest é chave de
  agrupamento, não segredo: o espaço de URLs é pequeno e enumerável.
- **A identidade do fixture vem do que ele SERVE** (`--alvo-fixture`), não da
  URL: a porta é efêmera e muda a cada noite; ancorar na URL zeraria a sequência
  todo dia e a Fase 2 nunca destravaria. Mexer num comentário não muda a
  identidade; mexer numa violação muda — e aí a sequência recomeça, porque o
  alvo passou a ser outro.
- **A sequência é por alvo**: se o `alvo_sha256` muda, ela reinicia. Nove
  execuções limpas contra um alvo mais uma contra outro não são dez execuções
  limpas contra nada.
- **Nada no GitHub commita o ledger** (`contents: read` nos dois workflows): o
  passo em `ci.yml` e o smoke-test rodam com `--dry-run`. O único escritor é o
  container da VPS, com deploy key montada como volume somente-leitura.

O `detail` de cada resultado passou a ser gravado também para **skip**: sem o
motivo, "Sem imagens na página" (resultado legítimo) seria indistinguível de
"Chromium indisponível" (flake). Continua sanitizado na borda de escrita.

## Backlog

**Fase 2** (destravada com **10 noites `vps` consecutivas** sem flake de infra;
entradas `ci` anteriores à emenda de 2026-07-30 são histórico e não contam)

- canário de consentimento: aceitar/recusar banner e comparar antes/depois — exige `WEBQA_ACTIVE_PROBES_AUTHORIZED=1`;
- detecção de CMPs (OneTrust, Cookiebot, Osano) e verificação de que "recusar" recusa de fato.

**Fase 3**

- Global Privacy Control: enviar `Sec-GPC: 1` e medir se os trackers reduzem;
- heurística de fingerprinting (canvas, `AudioContext`, enumeração de fontes).
