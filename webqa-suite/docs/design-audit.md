# Laudo de auditoria — pacote de design (§12)

**Veredito: LIBERADO**

Gerado por `scripts/audita_design.py` (dogfooding: a suíte auditando o contrato visual do relatório que ela mesma vai gerar). Este laudo **não corrige** os arquivos do designer — correção é iteração de design.

Comando: `python scripts/audita_design.py --suite`

## Estático

| Critério | componentes.html | estabilidade.html | summary-parcial.html | summary-sem-navegador.html | summary-verde.html | summary.html |
|---|---|---|---|---|---|---|
| lang="pt-BR" | PASS | PASS | PASS | PASS | PASS | PASS |
| h1 único | PASS | PASS | PASS | PASS | PASS | PASS |
| headings sem saltos | PASS | PASS | PASS | PASS | PASS | PASS |
| zero requisição externa | PASS | PASS | PASS | PASS | PASS | PASS |
| funciona sem JS | PASS | PASS | PASS | PASS | PASS | PASS |
| sem vazamento da capa | PASS | PASS | PASS | PASS | PASS | PASS |
| @media print | PASS | PASS | PASS | PASS | PASS | PASS |
| tema escuro | PASS | PASS | PASS | PASS | PASS | PASS |
| nota epistêmica | N.A. | N.A. | PASS | PASS | PASS | PASS |
| 4 estados sem cor | N.A. | N.A. | PASS | PASS | PASS | PASS |
| < 300 KB | PASS | PASS | PASS | PASS | PASS | PASS |
| tokens §11.5 | PASS | N.A. | N.A. | N.A. | N.A. | N.A. |

## Acessibilidade automatizada (axe, via bateria da suíte)

| Arquivo | Resultado | Evidência |
|---|---|---|
| `componentes.html` | PASS | axe sem violações críticas nem sérias |
| `estabilidade.html` | PASS | axe sem violações críticas nem sérias |
| `summary-parcial.html` | PASS | axe sem violações críticas nem sérias |
| `summary-sem-navegador.html` | PASS | axe sem violações críticas nem sérias |
| `summary-verde.html` | PASS | axe sem violações críticas nem sérias |
| `summary.html` | PASS | axe sem violações críticas nem sérias |

## Achados fora do §12 (informativo, não bloqueia)

| Teste da bateria | Arquivos | Atribuição |
|---|---|---|
| `test_fcp` | 6/6 auditados | defeito da SUÍTE: `VITALS_JS` lê `performance.getEntriesByType('paint')` em t=0 e só resolve a promise 1500ms depois — se o paint não estava registrado no instante da leitura, `fcp` fica `null` para sempre. Confirmado com navegador que as entradas existem (FCP 120ms em summary.html). Não é lentidão da página nem defeito do design. |
| `test_ajuda_no_erro_pagina_404_amigavel` | 6/6 auditados | artefato do ARRANJO: o `SimpleHTTPRequestHandler` do auditor não tem página 404 amigável. Um pacote de arquivos estáticos não tem handler de erro — critério não se aplica ao entregável. |

Nenhum destes reprova o pacote: os critérios do §12 estão nas tabelas acima. Um laudo que confunde artefato do arranjo com defeito do entregável faz o designer perseguir fantasma.

## Evidências dos critérios estáticos

### `componentes.html`

- **lang="pt-BR"** — PASS: lang="pt-BR"
- **h1 único** — PASS: h1 único: "Especificação de componentes"
- **headings sem saltos** — PASS: 9 headings, sem saltos
- **zero requisição externa** — PASS: nenhum recurso externo
- **funciona sem JS** — PASS: conteúdo íntegro sem JS
- **sem vazamento da capa** — PASS: sem x-dc, helmet ou support.js
- **@media print** — PASS: @media print com @page e break-inside
- **tema escuro** — PASS: prefers-color-scheme + gancho data-tema
- **nota epistêmica** — N.A.: critério é dos relatórios de execução
- **4 estados sem cor** — N.A.: critério é dos relatórios de execução
- **< 300 KB** — PASS: 47 KB (orçamento 300 KB)
- **tokens §11.5** — PASS: 23 tokens em custom properties

### `estabilidade.html`

- **lang="pt-BR"** — PASS: lang="pt-BR"
- **h1 único** — PASS: h1 único: "Painel de Estabilidade"
- **headings sem saltos** — PASS: 7 headings, sem saltos
- **zero requisição externa** — PASS: nenhum recurso externo
- **funciona sem JS** — PASS: conteúdo íntegro sem JS; 1 script(s) progressivo(s)
- **sem vazamento da capa** — PASS: sem x-dc, helmet ou support.js
- **@media print** — PASS: @media print com @page e break-inside
- **tema escuro** — PASS: prefers-color-scheme + gancho data-tema
- **nota epistêmica** — N.A.: critério é dos relatórios de execução
- **4 estados sem cor** — N.A.: critério é dos relatórios de execução
- **< 300 KB** — PASS: 26 KB (orçamento 300 KB)
- **tokens §11.5** — N.A.: critério é da especificação de componentes

### `summary-parcial.html`

- **lang="pt-BR"** — PASS: lang="pt-BR"
- **h1 único** — PASS: h1 único: "Relatório de Qualidade"
- **headings sem saltos** — PASS: 8 headings, sem saltos
- **zero requisição externa** — PASS: nenhum recurso externo
- **funciona sem JS** — PASS: conteúdo íntegro sem JS; 1 script(s) progressivo(s)
- **sem vazamento da capa** — PASS: sem x-dc, helmet ou support.js
- **@media print** — PASS: @media print com @page e break-inside
- **tema escuro** — PASS: prefers-color-scheme + gancho data-tema
- **nota epistêmica** — PASS: contém "não certifica conformidade" (linha 298)
- **4 estados sem cor** — PASS: 4 estados com forma+rótulo, com legenda
- **< 300 KB** — PASS: 46 KB (orçamento 300 KB)
- **tokens §11.5** — N.A.: critério é da especificação de componentes

### `summary-sem-navegador.html`

- **lang="pt-BR"** — PASS: lang="pt-BR"
- **h1 único** — PASS: h1 único: "Relatório de Qualidade"
- **headings sem saltos** — PASS: 7 headings, sem saltos
- **zero requisição externa** — PASS: nenhum recurso externo
- **funciona sem JS** — PASS: conteúdo íntegro sem JS; 1 script(s) progressivo(s)
- **sem vazamento da capa** — PASS: sem x-dc, helmet ou support.js
- **@media print** — PASS: @media print com @page e break-inside
- **tema escuro** — PASS: prefers-color-scheme + gancho data-tema
- **nota epistêmica** — PASS: contém "não certifica conformidade" (linha 298)
- **4 estados sem cor** — PASS: 4 estados com forma+rótulo, com legenda
- **< 300 KB** — PASS: 64 KB (orçamento 300 KB)
- **tokens §11.5** — N.A.: critério é da especificação de componentes

### `summary-verde.html`

- **lang="pt-BR"** — PASS: lang="pt-BR"
- **h1 único** — PASS: h1 único: "Relatório de Qualidade"
- **headings sem saltos** — PASS: 6 headings, sem saltos
- **zero requisição externa** — PASS: nenhum recurso externo
- **funciona sem JS** — PASS: conteúdo íntegro sem JS; 1 script(s) progressivo(s)
- **sem vazamento da capa** — PASS: sem x-dc, helmet ou support.js
- **@media print** — PASS: @media print com @page e break-inside
- **tema escuro** — PASS: prefers-color-scheme + gancho data-tema
- **nota epistêmica** — PASS: contém "não certifica conformidade" (linha 298)
- **4 estados sem cor** — PASS: 4 estados com forma+rótulo, com legenda
- **< 300 KB** — PASS: 58 KB (orçamento 300 KB)
- **tokens §11.5** — N.A.: critério é da especificação de componentes

### `summary.html`

- **lang="pt-BR"** — PASS: lang="pt-BR"
- **h1 único** — PASS: h1 único: "Relatório de Qualidade"
- **headings sem saltos** — PASS: 8 headings, sem saltos
- **zero requisição externa** — PASS: nenhum recurso externo
- **funciona sem JS** — PASS: conteúdo íntegro sem JS; 1 script(s) progressivo(s)
- **sem vazamento da capa** — PASS: sem x-dc, helmet ou support.js
- **@media print** — PASS: @media print com @page e break-inside
- **tema escuro** — PASS: prefers-color-scheme + gancho data-tema
- **nota epistêmica** — PASS: contém "não certifica conformidade" (linha 327)
- **4 estados sem cor** — PASS: 4 estados com forma+rótulo, com legenda
- **< 300 KB** — PASS: 68 KB (orçamento 300 KB)
- **tokens §11.5** — N.A.: critério é da especificação de componentes

## Bloqueios

Nenhum. Critérios bloqueantes (`lang`, `h1` único, requisição externa, JS obrigatório, vazamento da capa, axe crítico) aprovados em todos os entregáveis — a OS-15 está liberada para começar.
