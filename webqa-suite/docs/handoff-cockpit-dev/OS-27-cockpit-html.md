# OS-27 — Cockpit final de testes: `scripts/cockpit.py --html`

Estado: **pronta para o dev** · trilha DESIGN, frente D (D1k–D6k) · base pós-#68 (C3 mergeado)
Spec **visual**: `docs/qa-suite design brief/Cockpit - Protótipos v2.dc.html` (11 telas — navegar antes de codar).
Spec **de dados**: a tela **Contrato de dados** do próprio protótipo, replicada em §Esquema abaixo.
Dados de exemplo: `uploads/catalogo.json` (real, 763 testes / 848 casos, `67a8bfe`).

> Substitui a OS-27 anterior (que cobria 7 telas, antes de *A régua*, *Entre leituras* e das 3 telas
> de gestão). O protótipo agora tem 11 telas + selo de modo + cenários (`sem-run`) — este documento
> traduz **todas** em contrato. Bloqueio conhecido: o gerador (`scripts/cockpit.py`/`catalogo.py`)
> existe fora do repo e ainda não foi fornecido — D1k é incorporá-lo; as demais dependem dele.

```xml
<lang>Python 3.11 stdlib (scripts/cockpit.py, subcomando --html; a leitura AST que produz --json é D1k e NÃO muda de contrato aqui)</lang>
<task>Emitir report/cockpit.html (arquivo único, offline) e report/cockpit.json a partir da MESMA leitura, espelhando o protótipo v2: 11 telas, modo leitura graduado, selo de modo, estado de incomparabilidade, blocos opcionais D5k com degradação honesta.</task>
<context>O protótipo é a spec: telas, textos-moldura e comportamento estão em "Cockpit - Protótipos v2.dc.html". O JSON é fonte única — o HTML é outra veste; nenhuma frase/contagem digitada, tudo interpolado. Regras da casa: arquivo único, zero requisição externa, paleta própria clara (tokens em referencia/summary.html), @media print. As telas de gestão (Entrega, Governança) leem plano/arquitetura versionados no repo, não o catálogo.</context>
<rules>
- Tokens exatos (referencia/summary.html — nenhum tom novo): fundo #F5F3EF · papel #FFFFFF · tinta #1C2228 · apagado #4A5560 · linha #DED9D1 · acento/well #EDF2F7 · passed #2F6B4F · xfail/atenção #8A5800 · failed #9E2222 · skipped #5C6670 · acento/nao-executado(texto) #1E5A8A · vazio-pequeno #E7E2D9 · tracejado #B8B1A6. Escala fechada: 11/12/13.5/15/19/27 + 34 numérico. Mono = ui-monospace; contratos (docstrings) em serif Charter/Georgia; resto sans de sistema.
- Invariantes de honestidade (nenhuma tela viola): populações alvo/suite NUNCA se somam; não-executado NUNCA some por padrão (célula tracejada #B8B1A6 ≥9px, sólida #E7E2D9 abaixo); xfail nunca entra em conta de falha; ausência de MEDIÇÃO (D5k) é estado nomeado, nunca 0/verde; cor cromática é EXCLUSIVA de estado de teste (o alarme vermelho do modo só veste quando há gate de rede ativo); nenhum selo/percentual de aprovação; comparavel=null sem carimbo completo.
- 11 telas, nav lateral por seções (o todo / o instrumento / as partes / sob que régua / gestão da suíte / para o desenvolvedor / para quem aprova):
  1 Visão geral — tese + linha-resumo mono + mapa (1 célula=1 caso, por população) + duas populações + níveis e dimensões como GRADE DE CÉLULAS (1=1 teste) + 4 cartões epistêmicos.
  2 Execução & descritiva — tri-números, mediana/média/p95/desvio/n/total por população, outliers por Tukey (Q3+1,5·IQR), órfãos, sinais só-do-AST.
  3 O motor & maturidade (D5k) — cobertura de código por banda + viés, mutação por módulo, complexidade (cauda + decisão limiar 8), dependências, maturidade 16/20 por família. Topo: firewall "cobertura de código ≠ cobertura de execução".
  4 Catálogo — chips derivados + busca; linha abre ficha lateral sem perder filtros.
  5 Modo leitura — graus 1 arquivos → 2 só docstrings (declara "N sem contrato não aparecem neste grau") → 3 completo; clicar arquivo foca-o no grau 3.
  6 A régua · modo — selo dos 4 modos (escada de gravidade) + gates_ativos + carimbo (commit/modo/gates ao vivo; padrao_versao/hash "pendente") + comparabilidade (estado dominante = incomparável, motivo NOMEADO; nunca célula vazia).
  7 Entrega & saúde — defeitos abertos com prova, sequência de PRs por dependência com selo CODEOWNERS, frentes (E = prospectivo), riscos, "não fazer".
  8 Governança & fronteira — dois trabalhos (A audita alvo / B vigia testes), fronteira padrão×projeto (lista curada imutável), políticas executáveis vs markdown, modos + ambiente do agente sem gates.
  9 Contrato de dados (dev) — arquitetura do gerador (montar_* por tela), esquema de emissão, degradação honesta, telas×dados, CLI/make.
  10 Laudo — 4 blocos de prosa serif derivada + <pre> == o --json.
  11 Entre leituras — novos/removidos/vereditos que viraram/contratos reescritos; 1 leitura só → vazio honesto. + Módulos (regra de corte: muda O QUE = módulo; muda COMO = apresentação).
- Conteúdo íntegro sem JS: as telas existem no HTML (nav por âncoras/:target); JS inline só MELHORA (filtros, graus, região viva do mapa, demos). Sem JS, catálogo mostra tudo e graus viram âncoras.
- Estados obrigatórios: sem-run (tudo nao-executado; laudo "não há veredito a relatar"; aviso no trilho); filtro sem resultado; diff sem base; comparabilidade sem 2º projeto; blocos D5k ausentes → "sem medição" nomeado. Dimensões derivam dos markers presentes; rótulos pt-BR do protótipo; decimais com vírgula.
- A11y: células do mapa focáveis (tabindex=0, aria-label "nodeid — veredito") → UMA região aria-live; chips aria-pressed; foco ocre 2px; h1 único por tela.
</rules>
<aceite>
- report/cockpit.html do catalogo.json real: 763/848 interpolados; mapa com vazados dominantes; descritiva do alvo "sem execução"; régua em modo inventário, gates_ativos []; comparabilidade em vazio honesto; blocos D5k ausentes → O motor em "não instrumentada" nomeada (NÃO zero).
- Nenhum literal de contagem no template (grep por número mágico falha); trocar o JSON troca TODAS as frases das telas 1–6, 9–11.
- <pre> do Laudo e da tela dev == json.dumps do --json (byte-comparável após parse); procedencia+carimbo são as 2 primeiras chaves; comparavel=null enquanto padrao_versao/hash forem null.
- Impresso em P&B: os 5 estados de teste distinguíveis sem cor (sólido/vazado/riscado/rótulo). Arquivo único <400KB, zero requisição externa, axe sem críticas/sérias; JS desligado mantém as 11 telas legíveis/ancoráveis.
</aceite>
<testes>
- Catálogo sintético 2 testes (1 alvo passou, 1 suíte nao-executado) → populações não somadas; célula vazada presente; xfail sintético fora de soma de falha.
- Cenário sem-run → laudo "não há veredito a relatar"; nenhum musgo/carmim no HTML.
- Grau 2 com N sem docstring → nota "N sem contrato não aparecem neste grau"; grau 3 os mostra.
- Marker novo no pytest.ini do fixture → linha nova em Dimensões sem tocar o gerador; dimensão sem testes ausente.
- Durações [0.1,0.1,0.1,9.9] → outlier=1 por Tukey; mediana antes da média; vírgula decimal.
- cobertura_codigo/mutacao/complexidade ausentes → O motor renderiza "sem medição" por bloco; NENHUM 0% nem barra verde vazia. Presentes → tabelas populadas; score<70 em vermelho.
- carimbo sem padrao_versao/hash → tela dev e régua mostram "pendente"; comparavel=null; nenhuma comparação entre projetos emitida.
</testes>
<recomendacao>
- Um montador por tela recebendo (catalogo, run) → bloco: montar_mapa, _populacoes, _niveis, _dimensoes, _catalogo, _leitura, _execucao, _regua, _motor, _entrega, _governanca, _laudo, _diff. É a arquitetura "módulo novo = função nova" da tela Módulos.
- Separe verificação (catálogos sintéticos de borda, sem repo) de validação (dogfooding contra catalogo.json real + protótipo lado a lado, diff visual ~zero).
- UX: 1ª heurística de Nielsen é o invariante central — estado sempre visível; o vazio (de execução E de medição) tem aparência própria, nunca ausência.
</recomendacao>
```

## Sequência da frente D (do plano consolidado, §5)
`D1k` incorporar cockpit.py/catalogo.py + `make cockpit` + testes de convenção (**bloqueia D2k–D6k**) →
`D2k+D4k` selo de modo + estado de incomparabilidade → `D5k` blocos opcionais (depende de B3/B4/B5) →
`D3k` procedência como espinha (E4) → `D6k` `caminhos_sensiveis_hash` no laudo (serialização do `ResultadoSondagem`).

## Fora desta OS (registrado)
Dark mode (paleta própria exigiria decisão de design); comparador entre projetos de verdade (frente E —
`[project.scripts]`, pacote versionado); trilho só-ícones. As telas Entrega/Governança são spec de gestão
navegável; se virarem geradas, leem plano/arquitetura versionados, não o catálogo.
