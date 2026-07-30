# Declaração de Escopo e EAP

## Declaração de escopo

**Objetivo**: suíte genérica e automatizada em Python que avalia funcionalidade,
performance, UX e segurança de transporte de **qualquer aplicação web** acessível
via HTTP, produzindo relatório consolidado e executável em CI/CD.

**Dentro do escopo**
1. Diagnóstico caixa-preta via HTTP(S) e navegador (Chromium).
2. Métricas de backend (TTFB, percentis, cache, compressão, headers, observabilidade externa).
3. Métricas de frontend (HTML/CSS/JS, Web Vitals, console, peso de página).
4. UX automatizável (heurísticas de Nielsen, arquitetura de informação, WCAG/axe).
5. Funcional básico (links, formulários) + aceitação BDD.
6. Carga: rajada leve embutida + cenário Locust.

**Fora do escopo (anti-scope-creep — mudanças exigem decisão explícita)**
- Testes caixa-branca/unitários do código do alvo.
- Autenticação em **fluxo logado** (formulário de login, sessão, CSRF, MFA).
  A extensão prevista aqui foi exercida em parte pela OS-37: **HTTP Basic Auth
  na entrada** passou para DENTRO do escopo (`webqa/auth.py`, credencial só por
  ambiente). Basic Auth é um cabeçalho, não um fluxo — não há formulário a
  preencher nem sessão a manter, e por isso cabe na natureza caixa-preta da
  suíte sem torná-la um robô de navegação. Fluxo logado segue fora.
- Pentest ofensivo (fuzzing, injeção ativa) — apenas verificações passivas.
- Avaliação subjetiva de estética/conteúdo (exige humano).

## EAP (Work Breakdown Structure)

A EAP está **alinhada 1:1 com as entregas reais do código** (pastas do repositório):

```
1. WebQA Suite
├── 1.1 Fundação ................. webqa/ (config, http_utils, auth, report), conftest.py
├── 1.2 Backend .................. checks/backend/ (5 módulos)
├── 1.3 Frontend ................. checks/frontend/ (3 módulos)
├── 1.4 UX ....................... checks/ux/ (3 módulos)
├── 1.5 Funcional ................ checks/functional/ (2 módulos)
├── 1.6 Aceitação (BDD) .......... checks/acceptance/
├── 1.7 Carga .................... loadtest/ + marcador @load
├── 1.8 LGPD (Fase 1, passiva) ... checks/lgpd/ (5 módulos) + webqa/trackers.py, gates.py
├── 1.9 Verificação da suíte ..... tests/
├── 1.10 DevOps .................. .github/workflows/{ci,estabilidade}.yml, Makefile
├── 1.11 Documentação ............ docs/ (arquitetura C4, riscos, escopo, LGPD, recomendações)
├── 1.12 Segurança (Fases A e B) . checks/seguranca/ (4 módulos) + webqa/dominio.py
│                                  (value objects Finding/Recurso)
├── 1.13 Alvo fixture ............ fixture_target/ (servir.py + esperado.json)
├── 1.14 Ferramental ............. scripts/ (estabilidade, campanha, audita_design,
│                                  vps_smoke) + campanha.yaml
├── 1.15 Runtime da VPS .......... docker/ (Dockerfile, compose.yml, entrypoint.sh)
└── 1.16 Contrato visual ......... webqa/report_html.py, report_style.py +
                                   docs/qa-suite design brief/referencia/
```

**1.8 — Fase 1 apenas** (bateria passiva). Canário de consentimento, detecção de
CMP, Global Privacy Control e heurística de fingerprinting são Fase 2/3, listadas
como backlog em `docs/LGPD.md`; entram depois que a infraestrutura de `network_log`
estiver estável em produção.

**1.12 — Fases A e B apenas** (passivas). A Fase C (sondagem ativa) está
**desenhada e deliberadamente não implementada** em `docs/SEGURANCA.md §7`: ela
sonda caminhos que o servidor não ofereceu, o que exige
`WEBQA_ACTIVE_PROBES_AUTHORIZED=1` e autorização escrita do dono de um alvo.
Note que isso **não** contradiz "pentest ofensivo" estar fora do escopo acima:
a Fase C é sondagem autorizada e com rate-limit, não fuzzing nem injeção — e
segue fora do escopo enquanto não houver alvo autorizado.

**1.13/1.14/1.15 nasceram depois da redação original** desta EAP, junto com a
medição de estabilidade e o runtime da VPS. Estão listados aqui porque a EAP só
vale como mapa se acompanhar as pastas — uma EAP que declara alinhamento 1:1 e
omite quatro entregas é pior que EAP nenhuma: ela dá confiança falsa de que o
mapa está completo.

**Modelo de gestão recomendado**: híbrido — escopo/EAP e riscos formais (acima)
com evolução iterativa dos checks (cada novo check é um incremento pequeno,
testado e integrado via CI). Adequado porque os requisitos de qualidade mudam
com frequência (novas métricas Web Vitals, novas regras WCAG), mas o núcleo é estável.
