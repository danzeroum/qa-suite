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
make estabilidade                       # ou: python scripts/estabilidade.py
python scripts/estabilidade.py --dry-run   # classifica sem gravar (uso do CI)
```

A distinção que dá sentido à métrica:

| Sinal | Exemplo | Efeito na sequência |
|---|---|---|
| **Flake de infra** | `TimeoutError`, `TargetClosed`, `net::ERR_*`, Chromium ausente | **zera** |
| **FAIL determinístico** | tracker antes do consentimento, cookie de 730 dias, violação axe | **não zera** — a suíte funcionou; quem está errado é o alvo |
| Execução sem teste de navegador | `pytest -m "lgpd and not browser"` | ignorada (não conta nem zera) |

Cada entrada registra `{generated_at, alvo_sha256, browser_total, infra_flakes,
streak}`. `generated_at` é a chave: rodar o script duas vezes no mesmo summary
não infla a sequência. Ao atingir **10 execuções consecutivas sem flake**, o
script imprime `FASE 2 DESTRAVADA`.

Três decisões que valem registro:

- **A URL do alvo nunca entra no ledger** — só o `sha256`. O digest é chave de
  agrupamento, não segredo: o espaço de URLs é pequeno e enumerável.
- **A sequência é por alvo**: se o `alvo_sha256` muda, ela reinicia. Nove
  execuções limpas contra um alvo mais uma contra outro não são dez execuções
  limpas contra nada.
- **O CI não commita o ledger** (`contents: read`): o passo em `ci.yml` roda com
  `--dry-run` e publica o número como artefato. Avançar a sequência é ato
  deliberado de quem roda a validação.

O `detail` de cada resultado passou a ser gravado também para **skip**: sem o
motivo, "Sem imagens na página" (resultado legítimo) seria indistinguível de
"Chromium indisponível" (flake). Continua sanitizado na borda de escrita.

## Backlog

**Fase 2** (destravada quando o ledger atingir 10 execuções consecutivas sem flake)

- canário de consentimento: aceitar/recusar banner e comparar antes/depois — exige `WEBQA_ACTIVE_PROBES_AUTHORIZED=1`;
- detecção de CMPs (OneTrust, Cookiebot, Osano) e verificação de que "recusar" recusa de fato.

**Fase 3**

- Global Privacy Control: enviar `Sec-GPC: 1` e medir se os trackers reduzem;
- heurística de fingerprinting (canvas, `AudioContext`, enumeração de fontes).
