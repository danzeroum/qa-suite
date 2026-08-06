# Ordens de Serviço — camada GUI (não funcional de interface) — estado e fila

Base: `main` @ `2e15aec` (pós #80, `E5: comparador entre laudos`).
Contratos: [`docs/GUI.md`](../../GUI.md) (cercas, arquitetura, CI, governança) e
[`docs/GUI-CATALOGO.md`](../../GUI-CATALOGO.md) (28 itens + especificação dos dez
primeiros).

Numeração: **OS‑38 é a maior registrada** no repositório; esta trilha começa em
**OS‑40**, deixando 39 livre para uma OS em voo. O projeto já colidiu numeração
duas vezes (`docs/PROXIMOS-PASSOS.md §4.1`, duas OS‑24) — a folga é barata.

---

## Concluído

| OS | PR | Commit | Entrega |
|---|---|---|---|
| OS‑40 | #84 | `554754e` | violações de GUI no alvo fabricado, de uma vez só (custo do ledger declarado) |
| OS‑41 | #85 | `4527f81` | dimensão `gui` de ponta a ponta, `webqa/viewports.py`, contexto isolado |
| OS‑42 | #86 | `783b50b` | `webqa/geometria.py`: reflow, zoom 200%, alvo de toque com as exceções da 2.5.8 |
| OS‑43 | #87 | `ae71d21` | `webqa/foco.py`: a caminhada de foco e os três critérios que ela sustenta |
| OS‑44 | #88 | `29c1814` | `webqa/movimento.py` + smoke de GUI no `quality-gate` com aferição própria |
| OS‑45 | #89 | `dee1199` | `webqa/tema.py` + `webqa/axe.py`: contraste em tema escuro, com pré‑checagem |
| OS‑46 | #90 | `7c6b357` | `webqa/vitals_interacao.py`: TBT, long tasks e INP aproximado |
| OS‑47 | #91 | `906a6ac` | `webqa/degradacao.py`: 500, sem resposta, JSON truncado e perda de conexão |
| OS‑48 | #92 | `15d67ce` | `webqa/compatibilidade.py` + `webqa/menu.py`: matriz viewport × engine no noturno |
| OS‑56 | #92 | `15d67ce` | `webqa/foco.py`: fim de ordem ≠ armadilha — o falso positivo de foco no Firefox |
| OS‑49 | #93 | `cd16e9f` | `webqa/imagem.py` + `evidencias.py` + `referencia_visual.py`: contrato visual |
| OS‑50 | #94 | `2381493` | `webqa/rede_simulada.py`: pintura sob 3G e bloqueio sob CPU ×4, por CDP |
| OS‑57 | #95 | `e1553ad` | `scripts/afere_ancoras.py`: guarda bidirecional das âncoras `arquivo:linha`, com cobertura declarada |
| OS‑51 | #96 | `3db5aeb` | `webqa/jornada.py`: TSR, cliques excedentes, becos e ToT sobre o grafo do crawl |
| OS‑52 | #97 #98 | `f0f75aa` `9783fdf` | `webqa/i18n.py`: forced-colors, RTL e expansão ×1,5, mais a guarda de coletores órfãos |
| OS‑53 | #99 | `29873b1` | `webqa/conformidade.py`: SARIF de GUI, VPAT parcial e PDF executivo |
| OS‑54 | #100 | `934608d` | `docs/GUI-PROTOCOLO-HUMANO.md` + `webqa/sessao.py`: protocolo de sessão moderada |
| OS‑55 | #101 | `cb71789` | `webqa/exploracao.py`: fricções por LLM local sobre material já coletado |

A linha da OS‑55 foi preenchida **depois** do squash, e não podia ser de outro
jeito: o commit de um squash não existe enquanto o PR não é mergeado. Nas
demais, quem preencheu foi a OS seguinte, de carona; a última não tem seguinte,
então precisa de um commit próprio — ou o `—` fica lá para sempre passando por
"não entregue".

**A fila original FECHA aqui.** OS‑40 a OS‑55, mais as duas que nasceram de
execução e não de planejamento: a **OS‑56** (do run real da matriz da OS‑48) e a
**OS‑57** (das âncoras que derivaram duas vezes em três OSs). Dezessete ordens.

O que sobra não é código: são as **pendências do dono** no fim deste documento —
decisões que precisam de alvo, agenda ou máquina. Uma fila que fecha declarando o
que ficou fora é o oposto de uma que fecha em silêncio.

**Por que a OS‑56 aparece aqui e não na fila abaixo.** Ela não foi planejada: nasceu
do run real da matriz da OS‑48, que acusou três `error` do Firefox em `test_foco.py`.
Conserto de defeito achado por execução entra no PR que o expôs — separar em PR
próprio faria a OS‑48 mergear sabidamente quebrada numa engine. A numeração pulou
para 56 porque 50‑55 já estão reservadas na fila abaixo, e recontar OS já custou
caro duas vezes (`docs/PROXIMOS-PASSOS.md §4.1`).

---

### Coreografia de drenagem — a regra que custou um rebase para aprender

A política da casa é **squash**. Um squash-merge cria em `main` um commit
**novo**, sem laço de ancestralidade com a pilha que ele resume — e essa é a
consequência que morde: depois do squash, a ponta antiga da branch continua
descendendo dos commits **pré‑squash**, então a base comum entre branch e `main`
recua para antes da OS que acabou de entrar, e o GitHub tenta remesclar o que já
está lá. O sintoma é um `405 Pull Request has merge conflicts` numa branch cujo
conteúdo você acabou de conferir como idêntico a `main` mais a OS da vez.

> **Regra permanente.** Depois de todo squash, a sincronização da branch é
> **sempre**
> `git rebase --onto origin/main <ponta-mergeada> <ponta-nova>`,
> com `range-diff` provando `=` em cada commit. **Nunca** `reset --hard` para uma
> ponta pré‑squash: ela parece certa (o conteúdo bate) e traz a ancestralidade
> errada junto.

Aprendida na drenagem da OS‑50 (#94), onde o ciclo curto — uma OS de ponta a
ponta antes de abrir a seguinte — fez a surpresa custar **um** rebase em vez de
três.

---

## Sequência e dependências

```
Fase 1 — fundação e geometria
  OS-40 (alvo fixture: violações de GUI)   ← PRIMEIRA, e o motivo é aritmético
     └── OS-41 (dimensão gui + fixtures de contexto + viewports)
            ├── OS-42 (geometria: reflow, zoom, alvo de toque)
            └── OS-43 (foco: os três checks de teclado)
                   └── OS-44 (movimento + smoke no quality-gate)

Fase 2 — variação e adversidade
  OS-45 (contraste em tema escuro; _fetch_axe_verified movido para webqa/)
  OS-46 (INP/TBT/long tasks)
  OS-47 (resiliência: 500, timeout, malformado, offline)
  OS-48 (matriz viewport × engine no noturno)
  OS-49 (evidências + linha de base visual contra o fixture)   ← depende de OS-40

Fase 3 — maturidade
  OS-50 (rede degradada e CPU limitada, CDP)
  OS-51 (jornada quantitativa: TSR/ToT/cliques nos cenários BDD)
  OS-52 (i18n/RTL, zoom 400%, espaçamento de texto)
  OS-53 (evidência de conformidade: SARIF de GUI, PDF executivo, VPAT parcial)
  OS-54 (protocolo humano — piloto)
  OS-55 (GUI-EXPL-01: LLM local sobre jornada já coletada)
```

---

> **Âncoras dentro de ordens já emitidas.** Os blocos `xml` abaixo são o registro
> do que foi **pedido**, e o texto do pedido não se reescreve. As âncoras
> `arquivo:linha` dentro deles são exceção declarada: elas são ponteiro de
> navegação, não afirmação sobre o passado, e um ponteiro quebrado não ajuda
> ninguém. Quando o alvo se desloca, o número é atualizado e a frase fica
> intacta; quando o alvo **deixa de existir**, o número é removido e a menção
> vira "(à época, linha N)" — inventar um número novo para algo que sumiu seria
> a mentira que `scripts/afere_ancoras.py` existe para impedir.

## Fila (ordem de execução)

### OS‑40 — violações de GUI no alvo fixture — **PRIMEIRA, e o motivo tem prazo**

A sequência do ledger está **hoje em 0/10** (`PROXIMOS-PASSOS.md §4.4`).
`fixture_target/servir.py::identidade()` faz hash de `HOME`, `APP_JS` e dos
cookies; mudá‑los zera a caminhada. **Zerar zero custa nada; zerar 8/10 custa oito
noites** de espera para destravar a LGPD Fase 2. Por isso esta OS vem antes de
qualquer check, e faz **todas** as mudanças de fixture de uma vez.

```xml
<lang>Python 3.11 + stdlib (http.server) — fixture_target/servir.py; sem dependência nova</lang>
<task>Acrescentar ao alvo fabricado, DE UMA VEZ, as violações que os dez primeiros checks de GUI precisam detectar: armadilha de foco, controle sem foco visível, ordem de tabulação invertida, alvo de toque de 16px, overflow horizontal a 320px, animação infinita, long task no APP_JS e um endpoint XHR que responde 500.</task>
<context>identidade() faz sha256 de HOME, POLITICA, APP_JS, MIME_TROCADO, SVG_EXECUTAVEL, BUNDLE_JS e dos cookies; qualquer mudança altera alvo_sha256 e reinicia a caminhada de scripts/estabilidade.py. As iscas da Fase C (ISCAS_FASE_C) já vivem FORA de identidade() por esse motivo, e o mesmo padrão vale aqui. A sequência oficial está em 0/10, então o custo do reinício é zero AGORA e cresce depois. O conteúdo é construído em memória e legível no diff (regra do fixture: nada de binário opaco).</context>
<rules>
- Pense passo a passo antes de responder.
- O que couber em PÁGINA NOVA vai para paginas_gui/ e fica FORA de identidade(); só o que precisa estar na home (long task no APP_JS) entra nas constantes hasheadas.
- Uma OS só: nenhuma violação de GUI é adiada para depois, sob pena de segundo reinício.
- stdlib apenas; conteúdo em memória, legível no diff.
- Nada de literal de caminho sensível (tests/test_fase_c_travada.py:42-44) e nada de símbolo de sondagem.
- O cálculo do reinício vai ESCRITO no corpo do PR e num comentário ao lado de identidade().
</rules>
<aceite>
- `make fixture` sobe e serve as páginas novas; cada uma reprova o check correspondente quando ele existir.
- identidade() muda EXATAMENTE UMA VEZ neste PR; tests/test_fixture_target.py continua verde.
- As páginas de GUI que não precisam estar na home não entram em identidade() — há teste fixando isso, como o que já fixa as iscas da Fase C.
- O contrato 1:1 (esperado.json) segue coerente: nenhuma entrada nova ainda, porque nenhum check de gui existe — e o PR diz isso.
</aceite>
<testes>
- tests/test_fixture_target.py: as páginas novas respondem 200 e o conteúdo esperado está lá.
- tests/test_fixture_target.py: identidade() NÃO observa paginas_gui/ (prova por mutação: alterar uma página nova não muda o sha).
- tests/test_alvo_fixture.py continua com o contrato atual intacto.
</testes>
<recomendacao>
- Escreva a violação e o teste que a lê no mesmo commit. Uma página que "reprova de propósito" e que nenhum check lê é página morta — e vira o defeito §2.10 dentro do PR que o previne.
</recomendacao>
```

**Estimativa** 3 · **Depende de** nada.

---

### OS‑41 — dimensão `gui`: integração no laudo, fixtures de contexto, viewports

```xml
<lang>Python 3.11 + pytest + Playwright 1.56.0 — pytest.ini, webqa/report.py, webqa/report_html.py, webqa/viewports.py, conftest.py, data/gui-perfis.yaml</lang>
<task>Criar a dimensão `gui` de ponta a ponta — marcador, laudo, nota epistêmica — mais a fixture de contexto isolado e a matriz de viewports. Nenhum check ainda.</task>
<context>Dimensão só aparece no laudo se estiver em report.py::DIMENSIONS (27-30); fora dela agrupa como `other`. --strict-markers (pytest.ini:4) transforma marcador não registrado em erro de coleta, e as descrições ali são ASCII sem acento. browser_page é de sessão e compartilhada com checks/frontend/test_rendering.py (conftest.py:200-205): mexer em viewport ou tema nela contamina as Web Vitals das outras dimensões (R20). O molde de contexto virgem é o network_log (conftest.py:338-349). A doutrina de matriz por env, fail-closed, é webqa/navegador.py:24-48. load_settings faz float() em TODA chave de thresholds (config.py:45-47), então booleano não cabe lá.</context>
<rules>
- Pense passo a passo antes de responder.
- Quatro pontos de integração no MESMO PR: pytest.ini (markers), report.py::DIMENSIONS, report.py::DIMENSION_NOTES, report_html.py::OBSERVACOES. Faltando um, a dimensão existe no pytest e não no laudo.
- SEM submarcadores (a11y/perf/visual): a casa rejeitou seguranca_passiva/seguranca_ativa (docs/SEGURANCA.md §189-197). Eixo é prefixo de arquivo, não marcador.
- contexto_gui abre browser.new_context(...) e fecha no finally. NENHUM check de gui toca browser_page.
- WEBQA_VIEWPORTS é fail-closed: nome desconhecido é ValueError, nunca filtro silencioso.
- thresholds só recebe NÚMERO; viewports, máscaras, mapa WCAG e booleanos vão para data/gui-perfis.yaml.
- Nada em webqa/ com prefixo de coleta `test` (tests/test_convencoes.py:50-75) nem nome de sondagem.
</rules>
<aceite>
- `pytest -m gui` coleta (zero testes) sem erro de marcador; typo no marcador reprova.
- Um resultado sintético com dimensão `gui` aparece no card do summary.html com a observação e a nota epistêmica — verificado renderizando a página, não só chamando a função.
- WEBQA_VIEWPORTS="mobil" (typo) levanta ValueError nomeando os válidos.
- contexto_gui devolve página em contexto novo e o fecha; browser_page permanece com viewport default após o teste.
</aceite>
<testes>
- tests/test_viewports.py: fail-closed, ordem e unicidade preservadas, default = mobile+desktop.
- tests/test_report_html.py: dimensão `gui` renderiza com nota; ESTILO_CANONICO segue idêntico e nenhuma classe nova aparece.
- tests/test_gui_fixtures.py: contexto_gui não altera browser_page (prova por leitura do viewport depois).
</testes>
<recomendacao>
- A nota epistêmica de DIMENSION_NOTES é uma linha e é o que impede o laudo de virar selo. Copie o espírito da nota de `lgpd`: o que a falha prova, e o que passar NÃO certifica.
</recomendacao>
```

**Estimativa** 5 · **Depende de** OS‑40 (para o smoke ter o que reprovar).

---

### OS‑42 — geometria: reflow a 320 px, zoom 200 %, alvo de toque

```xml
<lang>Python 3.11 + Playwright — webqa/geometria.py, checks/gui/test_reflow.py, checks/gui/test_alvos.py</lang>
<task>Implementar GUI-RESP-01 (reflow 320px), GUI-TIPO-01 (zoom 200%) e GUI-ALVO-01 (alvo de toque >= 24px com as exceções da norma), com o algoritmo puro em webqa/geometria.py.</task>
<context>Specs completas em docs/GUI-CATALOGO.md §3.1, §3.2 e §3.6. As exceções da 2.5.8 (inline, equivalente, espaçamento) são o miolo do algoritmo e a fonte de falso positivo se ignoradas. C901 max-complexity = 8 vale em webqa/ e é dispensado em checks/** (pyproject.toml:46-56) — o algoritmo vive na biblioteca, decomposto, e fica testável sem navegador sobre caixas fabricadas. Medir o elemento CLICÁVEL, não o ícone interno: a área de toque costuma vir do padding do ancestral.</context>
<rules>
- Pense passo a passo antes de responder.
- Iteração de viewport DENTRO do corpo do teste — um nodeid por check (conftest.py:105-113 explica por quê: o contrato de esperado.json é por nodeid exato).
- Esperar document.fonts.ready antes de medir largura; rolar a página inteira antes de medir alvos (conteúdo lazy não medido é não avaliado, nunca aprovado).
- Alvo entre 24 e 44px é xfail (alerta), não failed: 44 é meta de plataforma, não norma.
- Toda medida por metricas.registrar; None é descartado, ausência não vira zero.
- Captura de tela só via evidencias.capturar (condicional — GUI.md §3.5). A evidência primária é seletor + caixa + valor.
</rules>
<aceite>
- Contra o fixture (OS-40): os três reprovam, com a lista de ofensores na mensagem.
- Contra um alvo conforme: os três passam.
- As entradas novas estão em fixture_target/esperado.json::devem_falhar com os nodeids exatos.
- gui_overflow_x_px, gui_alvo_menor_px e gui_zoom200_perdidos_n aparecem em summary.json::metricas.
</aceite>
<testes>
- tests/test_geometria.py: exceções da 2.5.8 sobre caixas fabricadas (inline, equivalente, espaçamento), incluindo os casos de borda em que a exceção NÃO se aplica.
- tests/test_geometria.py: alvo com transform:scale é medido pela caixa transformada.
- Validação: execução real contra o fixture, com os nodeids batendo com o contrato.
</testes>
<recomendacao>
- Escreva primeiro o caso da exceção que você acha improvável. As três exceções da 2.5.8 são onde um check ingênuo produz falso positivo em massa — e falso positivo em bateria de acessibilidade custa a credibilidade da bateria inteira.
</recomendacao>
```

**Estimativa** 5 · **Depende de** OS‑40, OS‑41.

---

### OS‑43 — foco: uma caminhada, três vereditos

```xml
<lang>Python 3.11 + Playwright — webqa/foco.py, checks/gui/test_foco.py</lang>
<task>Implementar a caminhada de foco e os três checks que a consomem: GUI-FOCO-01 (indicador visível, WCAG 2.4.7), GUI-FOCO-02 (ordem de tabulação vs ordem visual, 2.4.3) e GUI-FOCO-03 (foco não obscurecido, 2.4.11 — critério NOVO da 2.2).</task>
<context>Specs em docs/GUI-CATALOGO.md §3.3, §3.4 e §3.5. Uma caminhada alimenta os três, pela mesma economia que home_response faz nas dimensões HTTP. Teto de 200 Tabs: armadilha de foco vira falha explicada, nunca travamento. A heurística de inversão geométrica tem falso positivo conhecido em layout de grade — daí o limiar de 2, não 0, na Fase 1. Comparar com a ordem do DOM seria pior: `order` do flexbox e grid-area desacoplam DOM de visual legitimamente, e é esse descolamento que o critério existe para pegar.</context>
<rules>
- Pense passo a passo antes de responder.
- Uma fixture de caminhada, três testes que a consomem — não três caminhadas.
- Ler estilo 150ms depois de cada Tab (transição CSS no foco falsearia a leitura).
- Foco dentro de iframe de terceiro sai da caminhada e é DECLARADO no laudo, nunca ignorado em silêncio.
- gui_foco_inversoes_max = 2 na Fase 1, com o motivo do limiar folgado escrito na docstring.
- Nenhum retry: oscilação vai para o ledger de scripts/estabilidade.py.
</rules>
<aceite>
- Contra o fixture: armadilha de foco vira falha com mensagem (não travamento); controle sem outline reprova o 2.4.7; barra fixa cobrindo o foco reprova o 2.4.11.
- gui_foco_paradas_n, gui_foco_invisivel_n, gui_foco_inversoes_n e gui_foco_obscurecido_n em summary.json::metricas.
- Nodeids novos em esperado.json.
</aceite>
<testes>
- tests/test_foco.py: inversões de leitura sobre sequências de caixas fabricadas, LTR e RTL, incluindo o caso de coluna lateral que NÃO é inversão.
- tests/test_foco.py: caminhada que cicla sem escapar é detectada pelo teto e reportada como armadilha.
- tests/test_foco.py: fração coberta calculada sobre grade 3x3 fabricada.
</testes>
<recomendacao>
- O 2.4.11 é o mais barato de acertar e o mais fácil de violar sem perceber: basta um cabeçalho sticky e um scroll-margin esquecido. Vale escrever a mensagem nomeando o elemento QUE COBRE — sem isso, quem lê o achado não sabe por onde começar.
</recomendacao>
```

**Estimativa** 5 · **Depende de** OS‑40, OS‑41.

---

### OS‑44 — movimento + smoke de GUI no `quality-gate`

```xml
<lang>Python 3.11 + Playwright + GitHub Actions — checks/gui/test_preferencias.py, .github/workflows/ci.yml</lang>
<task>Implementar GUI-MOV-01 (prefers-reduced-motion respeitado, WCAG 2.3.3) e ligar o smoke de GUI ao job quality-gate, rodando contra o alvo fixture.</task>
<context>Spec em docs/GUI-CATALOGO.md §3.8. O quality-gate hoje roda `pytest tests -m verification` com piso de cobertura 78% e já instala Chromium (ci.yml) — a infraestrutura existe. O smoke de GUI é determinístico porque o alvo é fabricado, em loopback, sem rede pública: flake zero é exigível. compatibilidade.yml (05:23 UTC) já sobe o fixture e exporta WEBQA_TARGET_URL — é o padrão a copiar.</context>
<rules>
- Pense passo a passo antes de responder.
- Contar só animação ATIVA (playState === 'running') com iterações infinitas ou tempo RESTANTE acima de 1s — animação de 10s que já rodou 9,5s não é problema.
- Janela: networkidle + 1s. Medir antes disso pega a animação de entrada.
- O smoke NÃO toca alvo externo: sobe o fixture, como compatibilidade.yml faz.
- Carga nunca entra (`-m "gui and not load"`), e WEBQA_LOAD_AUTHORIZED continua ausente.
</rules>
<aceite>
- Contra o fixture: a animação infinita reprova sob reduced_motion=reduce.
- quality-gate roda os checks de GUI contra o fixture e reprova quando um deles reprova (prova por violação plantada).
- Tempo do job não cresce mais que ~2 min.
- Sem Chromium o smoke PULA com instrução — nunca passa em silêncio.
</aceite>
<testes>
- tests/test_gui_preferencias.py: filtro de animações sobre lista fabricada (infinita, restante > 1s, restante < 1s, pausada).
- Prova por mutação no CI: violação plantada no fixture reprova o job (um gate que nunca reprovou não está provado — é a lição do D6).
</testes>
<recomendacao>
- Confira que o smoke reprova ANTES de comemorar que ele passa. O defeito mais caro deste projeto foi um job verde que não exercia o contrato que ele existia para cobrir.
</recomendacao>
```

**Estimativa** 3 · **Depende de** OS‑42, OS‑43.

---

## Fase 2 — variação e adversidade

| OS | Entrega | Aceite resumido | Est. | Depende de |
|---|---|---|---|---|
| **OS‑45** | GUI‑CONTR‑01: contraste em tema escuro. Move `_fetch_axe_verified` do check de acessibilidade (à época, linha 26) para `webqa/`, importado pelos dois lugares | versão pinada e SHA‑384 preservados; alvo sem tema escuro **pula com motivo** (a pré‑checagem compara o fundo computado claro × escuro — sem ela o axe mediria o tema claro de novo e o teste passaria fingindo cobertura) | 5 | OS‑41 |
| ~~**OS‑46**~~ | ~~GUI‑PERF‑01: INP, TBT, long tasks (`webqa/vitals_interacao.py`)~~ | **entregue.** Duas correções ao aceite escrito, achadas na execução: (a) o nodeid ficou em `fora_do_contrato`, não em `devem_falhar` — veredito condicionado a `WEBQA_ORIGEM` é ambiente, e o contrato 1:1 só aceita desfecho que dependa do que o fixture serve; (b) o suporte a `longtask` é detectado **em runtime** (`supportedEntryTypes`), não pelo nome da engine — a lista de engines envelhece e mente | 5 | OS‑41 |
| ~~**OS‑47**~~ | ~~GUI‑RESIL‑01/02/03: 500, timeout, JSON truncado, offline~~ | **entregue**, com a partição do contrato declarada ANTES de codar e confirmada na validação: 500 e JSON truncado → `failed` (a home despeja o objeto de erro cru na tela) e entram em `devem_falhar`; sem resposta e offline → `xfail` (silêncio) e ficam fora, com motivo. Duas correções vindas da execução: a origem é `origem_de(target_url)`, não a URL inteira (alvo em página interna descartava a própria API como "terceiro"), e o offline só depois da carga ASSENTADA — cortar a rede no instante do `load` deixava o `fetch` no ar sobrescrever o aviso que a página já tinha mostrado | 5 | OS‑40, OS‑41 |
| ~~**OS‑48**~~ | ~~GUI‑RESP‑03/04/05, GUI‑COMPAT‑01/02: matriz viewport × engine no noturno~~ | **entregue.** Slot estendido (dois passos novos no mesmo job), nenhum cron criado. Partição: RESP‑03 e RESP‑05 em `devem_falhar` (chromium puro, o fixture os exerce); COMPAT‑01/02 fora, porque o desfecho depende de QUAIS engines estão instaladas. Resolve a pendência da OS‑41: perfil móvel em Firefox roda como largura sem emulação, com a nota no laudo. Uma descoberta cara: sem `meta viewport` no alvo, a emulação móvel dá a ele o viewport de fallback de 980px e NENHUMA media query abaixo disso vale — a família por viewport inteira mediria desktop achando que mediu celular | 5 | OS‑41 |
| ~~**OS‑49**~~ | ~~`webqa/evidencias.py` + `webqa/imagem.py` + `webqa/referencia_visual.py` + GUI‑VIS‑01/02 contra o fixture~~ | **entregue.** Decoder fail-closed com as quatro recusas testadas; diff por bloco 16×16 com tolerância por canal; referência versionada só de página FABRICADA e SEM TEXTO, com manifesto de procedência. Três achados da execução: o Playwright emite RGB (`color_type=2`), **não RGBA** como a OS previa, e em vários IDAT — as duas viraram contrato em teste; e o smoke da OS‑44 pegou que o check media as páginas do contrato visual seja qual for a `target_url`, reprovando contra a página conforme — passou a exigir a RAIZ do alvo | 8 | OS‑40, OS‑48 |

## Fase 3 — maturidade

| OS | Entrega | Aceite resumido | Est. | Depende de |
|---|---|---|---|---|
| ~~**OS‑50**~~ | ~~`webqa/rede_simulada.py`: CWV sob 3G e CPU 4× (GUI‑PERF‑02/03)~~ | **entregue.** Perfil `3g_rapido` = preset móvel padrão do Lighthouse, herdado e não inventado; fail‑closed no nome; skip nomeando a incapacidade de CDP, nunca lista de engines. Ambos os nodeids ficam **fora do contrato** por dois motivos independentes (desfecho por `WEBQA_ORIGEM` e por engine com CDP), então `devem_falhar` segue em 23. Uma descoberta que mudou o desenho: **o bloqueio da home é `while (Date.now() < fim)` — prazo de RELÓGIO, imune a throttling de CPU** (medido: 363ms sob ×4 contra 357ms livre), então a violação de referência teve de nascer COMPUTACIONAL em `/gui/pesado`, invisível sem throttle e severa com ele. GUI‑PERF‑02 virou dois itens no catálogo, e jank/heap deslocaram para ‑04/‑05 | 5 | OS‑46 |
| **OS‑51** | `webqa/jornada.py` + GUI‑JORN‑01/02 + `features/jornada_usabilidade.feature` | TSR/ToT/cliques nos **mesmos** cenários BDD que o protocolo humano usa — é o que torna as réguas comparáveis; becos sem saída lidos do grafo que `percorrer()` já produz | 8 | OS‑48 |
| ~~**OS‑51**~~ | ~~`webqa/jornada.py` + GUI‑JORN‑01/02 + `features/jornada_usabilidade.feature`~~ | **entregue.** Os cenários são os mesmos que a OS‑54 leva para a sessão moderada — todo passo executável por uma pessoa lendo em voz alta, nenhum falando de grafo ou BFS. O percurso IMITA a pessoa (lê rótulos e segue o que parece levar à tarefa); o caminho ótimo é a RÉGUA, não o percurso — a diferença entre os dois é o preço do rótulo ruim. Contrato 23 → 25 (k=2): TSR=0 e becos entram; ToT fica fora por ser tempo, e ganhou CENÁRIO PRÓPRIO por isso. **Nenhuma mudança de fixture foi precisa** — os dois becos (`/privacidade`, `/gui/estados`) e a tarefa sem rota já existiam, então o ledger custou zero (streak conferida em 0/10 antes, mesmo assim). Duas correções vindas da medição: o reconhecimento de chegada varria o texto inteiro e dava a home como destino porque ela CITA o destino num rótulo (TSR=1 com zero cliques), e o smoke da OS‑44 pegou que alvo de uma página só reprovava por não ter rota — virou skip instruído | 8 | OS‑48 |
| **OS‑52** | GUI‑TIPO‑02/03, GUI‑RESP i18n/RTL, GUI‑CONTR‑03 (`forced-colors`) | página RTL fabricada reprova quando o layout quebra; zoom 400 % sob demanda | 5 | OS‑48 |
| **OS‑53** | Evidência de conformidade: exportador SARIF de GUI, PDF executivo, VPAT parcial | exportador é função **pura** lendo `summary.json` (a dimensão `gui` não constrói `Finding` — `dominio.py:76-79`); PDF por `page.pdf()` do Chromium, zero dep; mapa critério→teste vem de `data/gui-perfis.yaml`, nunca digitado no template | 5 | OS‑45..49 |
| **OS‑54** | Protocolo humano — rodada piloto | roteiro, consentimento com prazo de retenção declarado e expurgo executado, SUS/SEQ, e a ponte achado→backlog com severidade Nielsen | 5 | OS‑51 |
| ~~**OS‑57**~~ | ~~`scripts/afere_ancoras.py` + `data/ancoras.yaml`: mecanizar a conferência das âncoras `arquivo:linha`~~ | **entregue.** Guarda bidirecional sobre documentos AUDITADOS, cobertura declarada por documento (`auditado`/`pendente`/`congelado`, todos com motivo) e placar de pendentes impresso em toda execução. Tranche 1 (GUI.md, GUI‑CATALOGO.md, OS‑gui‑fila.md, PROXIMOS‑PASSOS.md): **85 âncoras conferidas, 10 mentiam** e foram corrigidas no mesmo PR. Duas descobertas do desenho: 21 das 91 âncoras eram citadas a partir de raízes implícitas (`ARQUITETURA.md:44` de `docs/`) e teriam sido ignoradas como "inexistentes", deixando um buraco de 23% com a guarda parecendo completa; e o `PROXIMOS-PASSOS.md` não tem âncora `arquivo:linha` NENHUMA — cita por `§seção`, então o risco dele é ser citado, não citar | 5 | — |
| ~~**OS‑54**~~ | ~~Protocolo humano — rodada piloto~~ | **PROTOCOLO entregue; a RODADA é pendência do dono.** O roteiro NÃO reescreve os cenários: aponta para `jornada_usabilidade.feature`, porque duas versões divergiriam na primeira edição e a comparabilidade entre TSR humano e sintético — que foi o produto da OS‑51 — morreria aí. A pauta vem dos cinco `exige_humano` do mapa por referência. Consentimento com finalidade, retenção e expurgo obrigatórios (o consolidador RECUSA sem eles) e transcrição por `sanitize_text` antes do disco. Ensaio cronometrado achou três coisas antes de convidar alguém, uma delas uma contradição do próprio documento entre §3 e §6 sobre apontar | 5 | OS‑51 |
| ~~**OS‑55**~~ | ~~GUI‑EXPL‑01: LLM local sobre a jornada já coletada~~ | **entregue.** A LLM apresenta, o CÓDIGO julga — e o julgamento é mecânico: página ∈ grafo, tipo ∈ vocabulário fechado, evidência = trecho literal do insumo. Fricção que cita página inexistente morre como alucinação. Validador escrito ANTES do prompt, de propósito. Fricção fica FORA do SARIF (doutrina da OS‑53: achado é `failed` medido) e fora do contrato (não-determinística por natureza). A doutrina de `tests/test_convencoes.py:209-224` virou ARQUITETURA: o módulo não importa navegador nem cliente HTTP, então não tem como agir contra o alvo. Fail-closed em duas portas com mensagens distintas, sem caída para API externa. O alvo fabricado expôs um erro meu: eu preservava a URL crua no insumo, e ele serve `/newsletter?email=...` — PII mora em URL também | 8 | OS‑51 |

---

## Pendências do dono (não‑código)

- **Rodar o piloto da OS‑54.** O protocolo está pronto e ensaiado; a sessão com
  gente é decisão de quem tem o alvo e a agenda. O que ela precisa:
  **cinco participantes por perfil** (piso de Nielsen, não meta), com variedade
  deliberada — alguém que use teclado, alguém que use leitor de tela, alguém que
  nunca viu o produto —, **ninguém do time** (quem conhece não consegue não
  saber), **45 minutos** por sessão e um lugar para guardar a gravação com
  expurgo em **30 dias**. Prometer a sessão executada num PR seria o VPAT que
  promete; ela entra aqui, onde pendência de dono mora.

- **Decidir sobre a dimensão dupla `gui + lgpd`.** Acessibilidade é obrigação
  legal (LBI Art. 63) e `checks/ux/test_acessibilidade.py:24` já reivindica as
  duas dimensões. Estender isso aos checks de GUI os coloca no noturno
  (`docker/entrypoint.sh:93` roda `pytest -m lgpd`) e sujeita a sequência de dez
  noites à oscilação deles. A recomendação registrada em `GUI.md §2.3a` é **não**
  na Fase 1, e reavaliar quando a sequência estiver estável. É decisão sua.
- **Autorizar (ou não) o clique em banner de consentimento.** Está atrás de
  `WEBQA_ACTIVE_PROBES_AUTHORIZED=1` e fora desta trilha. O primeiro check que o
  consumir altera `tests/test_fase_c_travada.py:314-326`, que é protegido por
  CODEOWNERS.
- **Confirmar o orçamento de tempo do `quality-gate`.** O smoke de GUI acrescenta
  minutos ao job que roda em todo push.
- **Definir onde vive `WEBQA_GUI_BASELINE_DIR` na VPS**, se a comparação visual
  de alvo real for desejada — sob `report/` ela expira em 7 dias com o artefato.
