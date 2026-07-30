# WebQA Suite — Testes genéricos de qualidade para qualquer aplicação web (HTTP)

Conjunto de testes automatizados em **Python (pytest)** que avalia **qualquer aplicação web**
apontando apenas a URL alvo. Cobre, em profundidade:

- **Backend**: latência (TTFB, p50/p95/p99), throughput sob carga, compressão, cache,
  cabeçalhos de segurança, tratamento de erros, observabilidade.
- **Frontend**: qualidade do HTML/CSS/JS, recursos bloqueantes, peso de página,
  renderização real via navegador (Core Web Vitals: FCP, LCP, CLS), erros de console.
- **UX**: heurísticas de Nielsen, arquitetura de informação, acessibilidade (axe-core / WCAG).
- **Funcional**: links quebrados (crawler), formulários, fluxo de aceitação em BDD
  (Given/When/Then).

## Uso rápido

```bash
pip install -r requirements.txt
python -m playwright install chromium   # para os testes de renderização/acessibilidade

# alvo por variável de ambiente (ou edite config.yaml)
export WEBQA_TARGET_URL="https://example.com"

pytest                          # tudo
pytest -m backend               # só backend
pytest -m "frontend or ux"      # frontend + UX
pytest -m "not browser"         # sem navegador (só HTTP puro)
pytest -m acceptance            # cenários BDD de aceitação
```

Ao final, um relatório consolidado é gravado em `report/summary.json` e
`report/summary.html` (plugin próprio em `webqa/report.py`).

### Teste de carga (opcional, mais pesado)

```bash
pytest -m load                              # rajada leve embutida (httpx assíncrono)
locust -f loadtest/locustfile.py --host "$WEBQA_TARGET_URL"   # carga real com Locust
```

## Estrutura (EAP do repositório)

```
webqa-suite/
├── config.yaml            # alvo, limites (thresholds) e orçamentos de performance
├── conftest.py            # fixtures compartilhadas + plugin de relatório
├── webqa/                 # biblioteca de apoio (config, http, métricas, relatório)
├── checks/
│   ├── backend/           # performance, segurança, cache/compressão, observabilidade
│   ├── frontend/          # qualidade de HTML/CSS/JS e renderização (Playwright)
│   ├── ux/                # heurísticas de Nielsen, arquitetura de informação, a11y
│   ├── functional/        # links, formulários
│   └── acceptance/        # BDD (pytest-bdd) — validação de aceitação
├── loadtest/              # cenário Locust
├── tests/                 # testes DA PRÓPRIA SUÍTE (verificação)
└── docs/                  # arquitetura (C4), riscos, escopo/EAP, recomendações
```

## Níveis de teste e V&V

Seguindo a separação clássica **Verificação × Validação**:

| Nível | Onde | Pergunta respondida |
|---|---|---|
| Unidade | `tests/` | **Verificação** — a suíte está construída corretamente? |
| Integração | `checks/backend`, `checks/frontend` | O alvo integra HTTP, cache, assets corretamente? |
| Sistema | `checks/ux`, `checks/functional` | O sistema, ponta a ponta, se comporta bem no navegador? |
| Aceitação | `checks/acceptance` (BDD Given/When/Then) | **Validação** — é o que o usuário precisa? |

Cada nível foca **limites, riscos e áreas de maior complexidade**: percentis de
latência (não médias), orçamentos de peso de página, hierarquia de headings,
violações WCAG críticas primeiro.

## Rastreabilidade das recomendações aplicadas

| Prática recomendada | Onde é coberta |
|---|---|
| Verificação e Validação | `tests/` (verificação) vs `checks/` (validação); tabela acima |
| Níveis de Teste (unidade→aceitação, foco em limites e riscos) | estrutura de `checks/` por nível + thresholds em `config.yaml` |
| TDD/BDD (Given/When/Then) | `checks/acceptance/` com pytest-bdd |
| Análise Estática e SAST | CI (`.github/workflows/ci.yml`): ruff + bandit; headers de segurança em `checks/backend/test_security_headers.py` |
| Escopo e EAP | `docs/ESCOPO-EAP.md` (declaração de escopo + EAP alinhada às pastas) |
| Gerenciamento de Riscos | `docs/RISCOS.md` (probabilidade × impacto × resposta) |
| Usabilidade Heurística (Nielsen) | `checks/ux/test_heuristicas_nielsen.py` |
| Arquitetura de Informação | `checks/ux/test_arquitetura_informacao.py` |
| Design Centrado no Usuário | acessibilidade + Core Web Vitals medem a experiência real (`checks/ux/test_acessibilidade.py`, `checks/frontend/test_rendering.py`) |
| Atributos de Qualidade (-ilities) | performance (`test_performance.py`), segurança (`test_security_headers.py`), disponibilidade (`test_http_basics.py`), testabilidade (a própria suíte), documentados em `docs/ARQUITETURA.md` |
| Observabilidade (logging/tracing/monitoramento) | `checks/backend/test_observability.py` |
| Segurança por Design (LGPD/GDPR, privilégio mínimo) | headers, cookies `Secure/HttpOnly/SameSite`, ausência de vazamento de stack trace |
| DevOps e Automação (CI/CD) | `.github/workflows/ci.yml` roda lint + verificação + suíte |
| Leis da Arquitetura (trade-offs explícitos) | `docs/ARQUITETURA.md` — seção de decisões e preços pagos |
| Documentação C4 | `docs/ARQUITETURA.md` (Contexto, Container, Componente) |

## Configuração

Tudo é dirigido por `config.yaml` (sobreponível por variáveis `WEBQA_*`):

```yaml
target_url: "https://example.com"
thresholds:
  ttfb_ms: 800          # limite de Time To First Byte
  p95_ms: 1500          # p95 de latência sob rajada leve
  page_weight_kb: 3000  # orçamento de peso total da página
  lcp_ms: 2500          # Largest Contentful Paint ("bom" segundo Web Vitals)
  cls: 0.1              # Cumulative Layout Shift
  max_console_errors: 0
```

Os limites são **orçamentos de qualidade**: ajuste-os ao contexto do seu produto —
"uma decisão só pode ser avaliada em relação ao seu contexto".
