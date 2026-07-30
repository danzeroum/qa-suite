# Arquitetura da WebQA Suite (modelo C4)

## Nível 1 — Contexto

```
[Engenheiro de Qualidade] --usa--> (WebQA Suite) --HTTP/HTTPS--> [Aplicação Web Alvo]
                                        |--Chromium (Playwright)--> [Renderização real]
                                        |--gera--> [report/summary.{json,html}]
[Pipeline CI/CD] --executa--> (WebQA Suite)
```

A suíte é uma ferramenta de diagnóstico externo ("caixa-preta"): avalia qualquer
aplicação web apenas pelo que ela expõe via HTTP e pelo que renderiza no navegador.

## Nível 2 — Containers

| Container | Tecnologia | Responsabilidade |
|---|---|---|
| Runner de testes | pytest | orquestra execução, marcadores por dimensão |
| Biblioteca `webqa/` | Python puro + httpx | config, cliente HTTP, métricas, relatório |
| Checks HTTP | httpx + BeautifulSoup | backend, HTML, UX estática, funcional |
| Checks de navegador | Playwright/Chromium | Web Vitals, console, axe-core (a11y) |
| Carga | Locust | throughput e latência com usuários simulados |
| Relatório | plugin pytest próprio | `report/summary.json` + `summary.html` |

## Nível 3 — Componentes (webqa/)

- `config.py` — `Settings` imutável; thresholds = orçamentos de qualidade.
- `http_utils.py` — `timed_get` (TTFB por streaming), `percentiles`, `burst` assíncrono.
- `report.py` — hooks pytest que consolidam resultados por dimensão (um teste pode
  contar em mais de uma; agrupa na primeira declarada) e publicam as notas
  epistêmicas de cada dimensão no artefato.
- `sanitize.py` — ponto único de verdade sobre PII: as mesmas regexes **mascaram**
  (`sanitize_text`) e **detectam** (`find_pii`).
- `trackers.py` — `TRACKER_DOMAINS`, `is_tracker` e o contrato `NetworkLog`
  (requisições + cookies observados num contexto de navegador virgem).
- `gates.py` — guardas de autorização independentes: carga × sondagem ativa.

## Atributos de qualidade (-ilities) da própria suíte

| Atributo | Como é atendido |
|---|---|
| Testabilidade | `Settings` injetável, funções puras, verificação em `tests/` |
| Manutenibilidade | um arquivo por tema; checks só dependem de fixtures |
| Escalabilidade | novos checks = novos arquivos; nenhum acoplamento entre eles |
| Performance | resposta da home reutilizada por fixture de sessão (1 GET p/ N testes) |
| Segurança | não armazena credenciais; bandit no CI; rajada com concorrência limitada |
| Portabilidade | Python 3.11+, sem dependência de SO |

## Leis da arquitetura — trade-offs explícitos ("toda decisão tem seu preço")

| Decisão | Ganho | Preço pago |
|---|---|---|
| Caixa-preta via HTTP | funciona com **qualquer** stack | não enxerga causas internas (só sintomas) |
| Fixture única da home | não martela o alvo | testes compartilham o mesmo instante de medição |
| Playwright opcional (skip) | roda em ambientes sem navegador | cobertura menor quando ausente |
| Thresholds em YAML | ajustável por contexto | exige calibração consciente por produto |
| axe-core via CDN | sempre atualizado, repo leve | requer rede; falha vira skip explicado |
| `network_log` em contexto virgem por módulo | consentimento medido sem herança de estado | um carregamento a mais do alvo por módulo |
| Bateria LGPD 100% passiva na Fase 1 | zero risco jurídico de intrusão | não verifica se "recusar" recusa de fato (Fase 2) |
| Allowlist de terceiros em config | decisão documentada do controlador vence a heurística | allowlist mal preenchida silencia o teste |

"Uma decisão só pode ser avaliada em relação ao seu contexto": os limiares
padrão seguem Web Vitals/indústria, mas **devem** ser recalibrados para o seu produto.
