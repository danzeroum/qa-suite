# Handoff — Cockpit final de testes (webqa-suite)

Pacote para o desenvolvedor incorporar a frente **D** (`scripts/cockpit.py --html`).
Base do plano: `main` @ `67a8bfe` (pós #68 / C3). Design system: paleta de `referencia/summary.html`.

## O que é cada arquivo

| Arquivo | Papel |
|---|---|
| `Cockpit - Protótipos v2.dc.html` | **Spec visual navegável** — as 11 telas. Abra no navegador (precisa de `support.js` e `uploads/catalogo.json` ao lado). É O desenho; o código deve espelhá-lo. |
| `support.js` | Runtime do protótipo (só para abrir o HTML; **não** vai para `webqa/`). |
| `uploads/catalogo.json` | Saída real do `--json` (763 testes/848 casos, `67a8bfe`). É o exemplo contra o qual validar (dogfooding). |
| `OS-27-cockpit-html.md` | **Contrato**: bloco XML colável, tokens, invariantes, esquema de emissão, aceite e testes. |
| `docs/PLANO-DESENVOLVIMENTO-consolidado.md` | Sequência das frentes A–E e a fotografia medida (§2). Origem dos números das telas de gestão. |
| `docs/ARQUITETURA-suite-como-padrao-em-harness.md` | Frente E (prospectiva) — dois trabalhos, fronteira, modos, comparabilidade. Origem da tela Governança. |
| `docs/HANDOFF-Q1-instrumentacao.md` | Instrumentação (cobertura/mutação/complexidade) + harness de mutação (apêndice B). Origem da tela O motor. |

## Como abrir o protótipo
`support.js` e `uploads/catalogo.json` precisam estar ao lado do `.dc.html`. Abra o `.dc.html`
num navegador (ou sirva a pasta: `python -m http.server`). O tweak `cenario: sem-run` e `modo: *`
demonstram os estados degradados que o gerador precisa reproduzir.

## Onde no repositório
- Gerador: `webqa-suite/scripts/cockpit.py` (+ `scripts/catalogo.py`), alvo `make cockpit` → emite
  `report/cockpit.html` e `report/cockpit.json`.
- **Não** copie `support.js` nem o `.dc.html`: são a spec, não o produto. O HTML final é gerado por
  `cockpit.py` com os mesmos tokens (de `referencia/summary.html`).
- Nenhum caminho CODEOWNERS é tocado por D1k–D6k (só A3 toca, fora desta frente).

## O prompt (padrão dev) para colar numa LLM ou executar

```xml
<lang>Python 3.11 stdlib (scripts/cockpit.py, subcomando --html; a leitura AST que produz --json é D1k)</lang>
<task>Emitir report/cockpit.html (arquivo único, offline) + report/cockpit.json de UMA leitura, espelhando o protótipo de 11 telas do handoff.</task>
<context>Spec visual: "Cockpit - Protótipos v2.dc.html". Contrato: OS-27-cockpit-html.md. Exemplo real: uploads/catalogo.json (763 testes/848 casos, 67a8bfe). Tokens: referencia/summary.html. Gerador ainda não está no repo (D1k = incorporá-lo).</context>
<rules>
- Pense passo a passo.
- Arquivo único, zero requisição externa; nenhuma contagem digitada no template — tudo do JSON.
- Um montador por tela: montar_{mapa,populacoes,niveis,dimensoes,catalogo,leitura,execucao,regua,motor,entrega,governanca,laudo,diff}.
- Invariantes: populações alvo/suite nunca somadas; não-executado e não-medido nunca viram 0/verde — são estado nomeado; cor cromática só para estado de teste; comparavel=null sem carimbo completo.
</rules>
<aceite>
- catalogo.json real → 763/848 interpolados; grep por número mágico no template falha.
- <pre> do Laudo/tela dev == json.dumps do --json; procedencia+carimbo são as 2 primeiras chaves.
- Blocos D5k ausentes → O motor renderiza "não instrumentada" nomeada, nunca 0%/barra verde. Íntegro sem JS.
</aceite>
<testes>
- sem-run → laudo "não há veredito a relatar"; nenhum verde/vermelho no HTML.
- cobertura_codigo/mutacao/complexidade ausentes → "sem medição" por bloco, jamais 0%.
- durações [0.1,0.1,0.1,9.9] → outlier=1 por Tukey; mediana antes da média; vírgula decimal.
- grau 2 com N sem docstring → nota "N sem contrato não aparecem neste grau".
</testes>
<recomendacao>
- Separe verificação (catálogos sintéticos de borda) de validação (dogfooding contra catalogo.json real + protótipo lado a lado).
- Clean code: um montador puro (catalogo, run) → bloco; arquitetura "módulo novo = função nova".
</recomendacao>
```

## Sequência da frente D
`D1k` incorporar gerador + `make cockpit` + testes de convenção (**bloqueia o resto**) →
`D2k+D4k` selo de modo + incomparabilidade → `D5k` blocos opcionais (depende de B3/B4/B5) →
`D3k` procedência como espinha → `D6k` `caminhos_sensiveis_hash` no laudo (serialização do `ResultadoSondagem`).

## Fora de escopo
Dark mode; comparador entre projetos (frente E — `[project.scripts]`, pacote versionado); trilho só-ícones.
