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
- Autenticação em fluxos logados (extensível, mas não incluso).
- Pentest ofensivo (fuzzing, injeção ativa) — apenas verificações passivas.
- Avaliação subjetiva de estética/conteúdo (exige humano).

## EAP (Work Breakdown Structure)

A EAP está **alinhada 1:1 com as entregas reais do código** (pastas do repositório):

```
1. WebQA Suite
├── 1.1 Fundação ................. webqa/ (config, http_utils, report), conftest.py
├── 1.2 Backend .................. checks/backend/ (5 módulos)
├── 1.3 Frontend ................. checks/frontend/ (3 módulos)
├── 1.4 UX ....................... checks/ux/ (3 módulos)
├── 1.5 Funcional ................ checks/functional/ (2 módulos)
├── 1.6 Aceitação (BDD) .......... checks/acceptance/
├── 1.7 Carga .................... loadtest/ + marcador @load
├── 1.8 Verificação da suíte ..... tests/
├── 1.9 DevOps ................... .github/workflows/ci.yml, Makefile
└── 1.10 Documentação ............ docs/ (arquitetura C4, riscos, escopo, recomendações)
```

**Modelo de gestão recomendado**: híbrido — escopo/EAP e riscos formais (acima)
com evolução iterativa dos checks (cada novo check é um incremento pequeno,
testado e integrado via CI). Adequado porque os requisitos de qualidade mudam
com frequência (novas métricas Web Vitals, novas regras WCAG), mas o núcleo é estável.
