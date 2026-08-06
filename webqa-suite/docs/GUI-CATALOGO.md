# Catálogo da camada GUI — testes priorizados e especificação dos dez primeiros

Companheiro de [`GUI.md`](GUI.md), que é o contrato. Aqui está **o que medir** e
**como**. Leia o contrato primeiro: várias propostas óbvias foram cortadas por
cercas que só ele explica.

Base: `main` @ `2e15aec`. Estado: **planejado, nada em código.**

---

## 0. Como ler este catálogo

**Nível** — os da casa (`README.md §Níveis de teste e V&V`): `U` unidade/componente,
`I` integração, `S` sistema/E2E, `A` aceitação, `E` especializado.

**Severidade** — do achado no alvo, não do trabalho: `C` crítica (barreira de
acesso ou perda de função), `A` alta (degradação séria), `M` média (fricção).
Não confundir com a severidade de `Finding`, que pertence a `seguranca` e cujo
vocabulário a dimensão `gui` não usa (`GUI.md §3.5`).

**Frequência** — `PR` (smoke bloqueante contra o alvo fixture), `N` (noturno),
`RC` (release candidate contra alvo real), `D` (sob demanda).

**Estado** — o vocabulário **existente** do laudo, sem invenção:
`failed` / `xfail` / `skipped` / `error`. O que cada um significa aqui está em
`GUI.md §4.2`.

**Ferramenta** — só o que já está em `requirements.txt`. Nenhum item deste
catálogo introduz dependência: é restrição do projeto, e `PROXIMOS-PASSOS.md:585`
já registra `Pillow`, `piexif`, `pypdf` e `python-magic` como rejeitadas com
fundamento. Onde uma ferramenta externa seria natural, o §4 diz qual e por que
não entrou.

---

## 1. Catálogo priorizado — 28 itens

### 1.1 `GUI-RESP` — viewport, reflow, responsividade

| ID | Cenário | Nível | Métrica | Ferramenta | Sev | Freq |
|---|---|---|---|---|---|---|
| GUI-RESP-01 | Sem rolagem horizontal a 320 CSS px (WCAG 1.4.10) | S | `scrollWidth − clientWidth`; lista de elementos que extravasam | Playwright, contexto próprio | C | PR |
| GUI-RESP-02 | `meta viewport` não bloqueia zoom (`user-scalable=no`, `maximum-scale<2`) | I | presença das diretivas bloqueantes | BeautifulSoup — complementa `frontend/test_html_quality.py:45`, que só faz `grep` de `width=device-width` | A | PR |
| GUI-RESP-03 | Interativos não se sobrepõem em nenhum viewport da matriz | S | pares com interseção > 30 % da menor caixa | Playwright + `webqa/geometria.py` | A | N |
| GUI-RESP-04 | CLS medido **por viewport** (hoje só no default) | S | CLS por viewport | reuso de `VITALS_JS` | A | N |
| GUI-RESP-05 | Navegação principal utilizável em mobile (visível, ou gatilho que abre por clique **e** por teclado) | S | booleano por viewport | Playwright | A | N |

> **RESP‑03/04/05 e GUI‑COMPAT‑01/02 entregues na OS‑48**, com três
> decisões que só a execução revelou:
>
> * **o alvo precisou de `meta viewport`.** Sem ele, a emulação móvel do Chromium
>   dá à página o viewport de layout de fallback de 980px, e NENHUMA media query
>   abaixo disso chega a valer — a família inteira de checks por viewport mediria
>   o layout de desktop achando que mediu o de celular. É a mesma lição que fez
>   `reflow_aa` nascer sem emulação, agora aplicada ao alvo em vez do perfil;
> * **GUI‑COMPAT‑01 compara só o eixo HORIZONTAL.** `y` e `altura` acumulam as
>   métricas de fonte da página inteira: medido, o `body` do alvo fabricado dá
>   1776px no Chromium e 1797px no Firefox — 21px sem nada quebrado;
> * **GUI‑COMPAT‑02 tem dois pesos.** Exceção de JavaScript exclusiva reprova
>   (comportamento); erro de console exclusivo abranda para `xfail` (relato — o
>   Chromium loga falha de rede que o Firefox cala).

### 1.2 `GUI-FOCO` — foco e teclado

| ID | Cenário | Nível | Métrica | Ferramenta | Sev | Freq |
|---|---|---|---|---|---|---|
| GUI-FOCO-01 | Indicador de foco visível em todo elemento focável (WCAG 2.4.7) | S | nº de paradas sem diferença de estilo com/sem foco | Playwright + `webqa/foco.py` | C | PR |
| GUI-FOCO-02 | Ordem de tabulação segue a ordem visual (WCAG 2.4.3) | S | nº de inversões geométricas na sequência | `webqa/foco.py` + `geometria.py` | A | PR |
| GUI-FOCO-03 | Foco não obscurecido por barra fixa (WCAG 2.4.11 — **nova na 2.2**) | S | nº de paradas cobertas > 25 % | Playwright `elementFromPoint` | A | PR |
| GUI-FOCO-04 | Todo interativo visível é alcançável por Tab; sem armadilha de foco | S | inalcançáveis; ciclo que não escapa | `webqa/foco.py`: teto de 200 Tabs + sonda `Shift+Tab` e cobertura (§3.3) | C | N |
| GUI-FOCO-05 | Atalho para o conteúdo principal (skip link) presente e funcional (WCAG 2.4.1) | S | existe e leva o foco ao destino | Playwright | M | N |

### 1.3 `GUI-CONTR` — contraste e tema

| ID | Cenário | Nível | Métrica | Ferramenta | Sev | Freq |
|---|---|---|---|---|---|---|
| GUI-CONTR-01 | Contraste de texto em tema escuro (WCAG 1.4.3) | S | pares abaixo de 4,5:1 (3:1 para texto grande) | axe `color-contrast` + `emulate_media(color_scheme=dark)` | C | PR |
| GUI-CONTR-02 | Contraste em estados hover/focus/active/disabled — o axe mede o estado de repouso | I | pares em estado abaixo do mínimo | `webqa/contraste.py` sobre estilo computado | A | N |
| GUI-CONTR-03 | `forced-colors: active` não apaga informação | S | elementos com fundo/borda perdidos | `emulate_media(forced_colors=…)` | M | N |
| GUI-CONTR-04 | Consistência de tokens: nº de cores, famílias e tamanhos distintos em uso ≤ teto | S | contagens distintas | `evaluate(getComputedStyle)` agregado | M | RC |

### 1.4 `GUI-MOV` — movimento

| ID | Cenário | Nível | Métrica | Ferramenta | Sev | Freq |
|---|---|---|---|---|---|---|
| GUI-MOV-01 | `prefers-reduced-motion: reduce` respeitado (WCAG 2.3.3) | S | animações ativas > 0,2 s ou infinitas sob a preferência | `emulate_media` + `document.getAnimations()` | A | PR |
| GUI-MOV-02 | Nenhum conteúdo pisca acima de 3 Hz (WCAG 2.3.1) | S | transições de luminância por segundo | amostragem por `requestAnimationFrame` | C | N |
| GUI-MOV-03 | Carrossel/auto‑rotação tem pausa acessível (WCAG 2.2.2) | S | existe controle de pausa alcançável por teclado | Playwright | M | RC |

### 1.5 `GUI-TIPO` — texto e zoom

| ID | Cenário | Nível | Métrica | Ferramenta | Sev | Freq |
|---|---|---|---|---|---|---|
| GUI-TIPO-01 | Zoom de texto a 200 % sem perda de conteúdo (WCAG 1.4.4) | S | texto do `main` presente; elementos clipados | Playwright, viewport lógico reduzido | A | PR |
| GUI-TIPO-02 | Espaçamento de texto ajustado não corta conteúdo (WCAG 1.4.12) | S | clipping após injeção do CSS da norma | `add_style_tag` com a folha canônica do critério | M | N |
| GUI-TIPO-03 | Zoom a 400 % (320 px lógicos) — o teto da 1.4.10 | S | overflow e clipping | Playwright | A | D |

### 1.6 `GUI-ALVO` — alvo de toque

| ID | Cenário | Nível | Métrica | Ferramenta | Sev | Freq |
|---|---|---|---|---|---|---|
| GUI-ALVO-01 | Alvo ≥ 24×24 px CSS, com as exceções da norma (WCAG 2.5.8 — **nova na 2.2**) | S | % abaixo do mínimo; menor alvo encontrado | Playwright `bounding_box` + `webqa/geometria.py` | A | PR |
| GUI-ALVO-02 | Espaçamento entre alvos pequenos: círculo de 24 px sem interseção | S | pares em conflito | `webqa/geometria.py` | M | N |

### 1.7 `GUI-ESTADO` — estado, feedback, cor

| ID | Cenário | Nível | Métrica | Ferramenta | Sev | Freq |
|---|---|---|---|---|---|---|
| GUI-ESTADO-01 | Informação não depende só de cor (WCAG 1.4.1) — **heurístico, e declarado como tal** | S | elementos que diferem do irmão só em cor, sem texto/ícone/forma | `evaluate` comparativo | M | N |
| GUI-ESTADO-02 | Ação produz resposta perceptível em < 1 s (Nielsen H1) | S | latência até mudança de DOM, `aria-busy` ou navegação | MutationObserver | A | N |
| GUI-ESTADO-03 | Estado desabilitado é distinguível **e** anunciável (`disabled`/`aria-disabled`, não só opacidade) | I | controles cinzas sem atributo | Playwright | M | N |
| GUI-ESTADO-04 | Estado vazio e estado de carregamento existem e não são tela em branco | S | `main` com texto em cada estado | galeria do fixture + alvo real | M | RC |

### 1.8 `GUI-COMPAT` — compatibilidade entre engines

| ID | Cenário | Nível | Métrica | Ferramenta | Sev | Freq |
|---|---|---|---|---|---|---|
| GUI-COMPAT-01 | Geometria do layout não diverge além da tolerância entre chromium/firefox/webkit | S | desvio das caixas dos marcos principais | matriz **existente** (`webqa/navegador.py:24`) | A | N |
| GUI-COMPAT-02 | Sem erro de console exclusivo de uma engine | S | erros por engine | reuso da coleta de `test_rendering.py` | M | N |

### 1.9 `GUI-PERF` — desempenho percebido

| ID | Cenário | Nível | Métrica | Ferramenta | Sev | Freq |
|---|---|---|---|---|---|---|
| GUI-PERF-01 | INP aproximado, TBT e long tasks | S | `gui_inp_ms`, `gui_tbt_ms`, `gui_long_tasks_n` | `PerformanceObserver('longtask','event')` — chromium; skip instruído nas demais | C | PR |
| GUI-PERF-02 | Pintura sob rede 3G, com **orçamento próprio** | S | `gui_fcp_ms_rede_lenta`, `gui_lcp_ms_rede_lenta` | CDP `Network.emulateNetworkConditions` (chromium; skip nomeado nas demais) | A | PR |
| GUI-PERF-03 | Bloqueio sob CPU 4× mais lenta, com **orçamento próprio** | S | `gui_tbt_ms_cpu_lento` | CDP `Emulation.setCPUThrottlingRate` | A | PR |
| GUI-PERF-04 | Jank de rolagem | S | % de quadros acima de 32 ms | amostragem por `requestAnimationFrame` | M | N |
| GUI-PERF-05 | Crescimento de heap em navegação repetida | E | % de crescimento após 5 idas e voltas | CDP `Performance.getMetrics` | M | RC |

> **Renumeração declarada (OS-50).** O que era um item só — "CWV sob rede 3G **e**
> CPU 4× mais lenta" — virou **dois**, porque a implementação mostrou que são dois
> vereditos com correções diferentes: bytes bloqueantes se resolvem dividindo a
> folha, e trabalho síncrono se resolve fatiando o script. Um `failed` que
> misturasse os dois não diria por onde começar. Em consequência, jank de rolagem
> foi de `-03` para `-04` e heap de `-04` para `-05`. A renumeração foi conferida
> antes: nenhum dos dois está implementado e **nenhum documento, código ou laudo
> os referencia** — o custo é estas duas linhas. O projeto já colidiu numeração
> duas vezes (`docs/PROXIMOS-PASSOS.md §4.1`), e é por isso que a conferência veio
> antes da edição, e não depois.

### 1.10 `GUI-RESIL` — resiliência da interface

| ID | Cenário | Nível | Métrica | Ferramenta | Sev | Freq |
|---|---|---|---|---|---|---|
| GUI-RESIL-01 | API respondendo 500 → erro compreensível e acionável, sem tela branca nem stack trace | S | mensagem presente; termos técnicos vazados; erros de console | `page.route` (interceptação **no cliente**, passiva) | C | PR |
| GUI-RESIL-02 | Timeout e JSON truncado → degradação sem laço de repetição infinito | S | requisições ao mesmo endpoint na janela | `route.fulfill`/`abort` | A | N |
| GUI-RESIL-03 | Offline após a carga → indicação de estado; volta do online recupera | S | feedback presente; recuperação | `context.set_offline` | M | N |
| GUI-RESIL-04 | Sem JavaScript: conteúdo principal legível. Sem CSS: ordem de leitura íntegra | S | texto do `main`; ordem do DOM | `java_script_enabled=False`; bloqueio de CSS por `route` | M | RC |

### 1.11 `GUI-JORN` — usabilidade quantitativa

| ID | Cenário | Nível | Métrica | Ferramenta | Sev | Freq |
|---|---|---|---|---|---|---|
| GUI-JORN-01 | Jornada BDD instrumentada: TSR e cliques além do caminho ótimo | A | `gui_jornada_tsr_*`, `gui_jornada_cliques_*`, `gui_jornada_excedente_*` | pytest‑bdd + `webqa/jornada.py` (BFS sobre o grafo do crawl) | A | PR |
| GUI-JORN-03 | ToT: tempo de tarefa, contra orçamento próprio | A | `gui_jornada_tot_ms_*` | o mesmo percurso, cronometrado — cenário PRÓPRIO porque tempo é ambiente | M | PR |
| GUI-JORN-02 | Becos sem saída: página em que se entra e de onde só se sai voltando | S | `gui_jornada_becos_n` | grafo `origem→destino` que `webqa/navegacao.py::percorrer` já produz | A | PR |

> **Numeração declarada (OS-51).** O ToT nasceu como parte do GUI‑JORN‑01 e virou
> **GUI‑JORN‑03** na implementação, por uma razão que só aparece ao codar: TSR e
> cliques são determinísticos contra o alvo fabricado e ToT é **tempo**, logo
> ambiente. Compartilhando nodeid, o desfecho do conjunto passaria a depender do
> ambiente — e nenhuma das medidas determinísticas poderia entrar no contrato 1:1.
> A separação não é de arrumação: é o que permite duas delas serem contratuais.
> Conferido antes de renumerar: `GUI-JORN-03` não existia e ninguém o referencia.

### 1.12 `GUI-VIS` — regressão visual

| ID | Cenário | Nível | Métrica | Ferramenta | Sev | Freq |
|---|---|---|---|---|---|---|
| GUI-VIS-01 | Página estável contra a linha de base, por viewport (alvo **fabricado**) | E | % de blocos divergentes | Playwright `screenshot` + `webqa/imagem.py` (zlib + struct) | A | N |
| GUI-VIS-02 | Estados de componente estáveis (galeria do fixture) | U/I | % por componente | `locator.screenshot()` | M | N |

### 1.13 `GUI-SEC` — segurança e privacidade de interface

| ID | Cenário | Nível | Métrica | Ferramenta | Sev | Freq |
|---|---|---|---|---|---|---|
| GUI-SEC-01 | **Qualidade** da CSP: `unsafe-inline`/`unsafe-eval` em `script-src`, Trusted Types declarado | I | diretivas fracas | parsing do cabeçalho — complementa `backend/test_security_headers.py:33`, que só checa existência | A | N |
| GUI-SEC-02 | PII visível em claro no DOM renderizado (CPF, e‑mail, telefone) | S | ocorrências por tipo | `webqa/sanitize.py::find_pii` sobre o texto renderizado | A | N |

### 1.14 `GUI-EXPL` — exploratório assistido

| ID | Cenário | Nível | Métrica | Ferramenta | Sev | Freq |
|---|---|---|---|---|---|---|
| GUI-EXPL-01 | LLM **local** analisa a jornada **já coletada** e propõe fricções para triagem humana | E | achados triados — nunca veredito | `webqa/llm.py` + gate `WEBQA_LLM_ENABLED` | M | D |

> **Por que a LLM não clica.** `tests/test_convencoes.py:209-224` reprova módulo
> de sondagem que importe a camada de LLM, com o fundamento: "a IA processa
> achados já produzidos, não participa de agir contra o alvo". Um agente que
> executa objetivo aberto no navegador é exatamente o que a regra recusa. O
> exploratório desta camada, portanto, lê o grafo de jornada e os eventos que a
> suíte já registrou. Mudar isso seria mudar a regra, num PR que diga isso.

---

## 2. Como a ordem foi decidida

Um critério, em uma frase, no espírito de `SEGURANCA.md §8.1`:

> **Vem primeiro o que é barreira de acesso, determinístico e mensurável sem
> autorização adicional.**

Barreira de acesso porque foco e reflow impedem alguém de usar o produto, não o
incomodam. Determinístico porque um smoke de PR que oscila é um smoke que a
equipe aprende a ignorar — e a suíte inteira existe contra o verde falso.
Mensurável sem autorização porque tudo que precisa de gate depende de decisão
humana que não está no caminho crítico.

Foi esse critério que empurrou a regressão visual para a Fase 2 apesar do valor
alto: linha de base que não existe no primeiro run não pode reprovar, e para
alvo real ela não é versionável (R19).

---

## 3. Especificação dos dez primeiros

**Convenções comuns.** Marcador `[gui, browser]` — só `gui` na dimensão, pela
decisão registrada em `GUI.md §2.3a`. Limiares por `settings.threshold("gui_…")`,
chaves planas (`webqa/config.py:32-33`). Toda medida por `metricas.registrar`,
que descarta `None` — ausência não é zero. Nenhum teste parametrizado: a iteração
acontece **dentro do corpo**, um nodeid por check (`GUI.md §2.3b`). Fixture nova
`contexto_gui(**opcoes)`, que abre `browser.new_context(...)` próprio e fecha no
`finally`, no molde de `network_log` (`conftest.py:338-349`) — **nenhum destes toca
`browser_page`**. Cada check ganha unidade em `tests/` sobre dado fabricado e
contraparte que reprova de propósito em `fixture_target/paginas_gui/`.

> **Captura de tela é condicional, em toda spec abaixo.** Onde se lê "captura"
> na lista de artefatos, leia: *sempre contra o alvo fabricado; contra alvo real
> só sob `WEBQA_GUI_SCREENSHOTS=1`*. `webqa/sanitize.py` mascara texto e **não
> existe mascarador de pixel** — é o R19, e a decisão está em `GUI.md §3.5`. A
> evidência primária desta camada é **texto**: seletor, caixa e valor medido. É
> ela que vai para o ticket; a imagem só ajuda a ver. `evidencias.capturar(...)`
> encapsula a condição — nenhum check a repete, e há teste provando que sem a
> variável nenhum PNG de alvo não fabricado chega ao disco.

---

### 3.1 `checks/gui/test_reflow.py::test_sem_rolagem_horizontal_em_320px`

**1. Objetivo e norma.** WCAG 2.2 **1.4.10 Reflow** (AA): conteúdo apresentável a
320 CSS px de largura sem exigir rolagem em duas dimensões. É a largura de um
telefone pequeno com zoom de 400 % — e é onde produtos "responsivos" costumam
quebrar sem que ninguém veja.

**2. Pré‑condições e fixtures.** `contexto_gui(viewport=perfil("reflow_aa"))`,
lido de `data/gui-perfis.yaml`. Aguardar `load` **e** `document.fonts.ready`:
fonte que chega tarde muda a largura do texto, e medir antes dela é medir outra
página.

**3. Passos.** Abrir o alvo no contexto de 320 px → esperar fontes → medir
`document.scrollingElement.scrollWidth − clientWidth` → coletar os elementos cujo
`getBoundingClientRect().right > innerWidth`, com seletor e largura → conferir que
o texto do `main` continua presente (nada colapsou para `display:none`).

**4. Asserções e métricas.** `overflow <= threshold("gui_overflow_x_px")`; lista
de extravasantes vazia. Registra `gui_overflow_x_px` e `gui_extravasantes_n`.

**5. Artefatos.** Captura de página inteira a 320 px; JSON com seletor, caixa e
largura de cada ofensor. A lista é o que torna o achado acionável — a imagem
ajuda, mas o seletor é o que vai para o ticket.

**6. Aprovação.** `failed` acima do limiar. Alvo com tabela larga ou mapa
declarado no YAML como exceção vira `xfail` com o motivo escrito — exceção
declarada, nunca silenciosa.

**7. Flakiness e mitigação.** Baixa. Duas fontes reais: imagem sem `max-width`
chegando depois do `load` (mitigada pela espera de fontes e por `networkidle`) e
barra de rolagem que consome largura (mitigada medindo `clientWidth`, que já a
exclui).

**8. YAML.**
```yaml
thresholds:
  gui_overflow_x_px: 0
# data/gui-perfis.yaml
viewports:
  reflow_aa: {width: 320, height: 640, mobile: true}
```

**9. Pseudocódigo.**
```python
pytestmark = [pytest.mark.gui, pytest.mark.browser]

def test_sem_rolagem_horizontal_em_320px(contexto_gui, settings, perfis):
    pagina = contexto_gui(viewport=perfis.viewport("reflow_aa"))
    pagina.goto(settings.target_url, wait_until="load", timeout=60_000)
    pagina.evaluate("document.fonts.ready")
    medida = pagina.evaluate(JS_OVERFLOW)        # webqa/geometria.py — puro do lado JS
    metricas.registrar("gui_overflow_x_px", medida["overflow"])
    metricas.registrar("gui_extravasantes_n", len(medida["extravasantes"]))
    evidencias.capturar(pagina, request.node.nodeid, "reflow-320")
    limite = settings.threshold("gui_overflow_x_px")
    assert medida["overflow"] <= limite, (
        f"A 320 CSS px a página rola {medida['overflow']:.0f}px na horizontal "
        f"(limite {limite:.0f}) — WCAG 1.4.10.\n"
        + resumo_de_extravasantes(medida["extravasantes"][:8]))
```

---

### 3.2 `checks/gui/test_reflow.py::test_zoom_200_nao_perde_conteudo`

**1. Objetivo e norma.** WCAG 2.2 **1.4.4 Resize Text** (AA): texto ampliável até
200 % sem perda de conteúdo ou funcionalidade.

**2. Pré‑condições.** `contexto_gui(viewport=desktop, device_scale_factor=2)` com
viewport lógico pela metade — a forma de emular zoom sem depender de atalho de
navegador, que o Playwright não expõe de modo estável entre engines.

**3. Passos.** Medir, no viewport normal, o conjunto de textos visíveis do `main`
e a presença dos marcos (nav, main, footer, botões primários) → reabrir com zoom
→ medir de novo → comparar: texto que sumiu, marco que sumiu, elemento clipado
(`scrollHeight > clientHeight` com `overflow: hidden`).

**4. Asserções e métricas.** Nenhum marco desaparecido; nenhum texto do `main`
perdido; clipping zero. Registra `gui_zoom200_perdidos_n`.

**5. Artefatos.** Capturas dos dois estados, lado a lado no diretório de
evidências; JSON do diff de marcos.

**6. Aprovação.** `failed` se marco ou texto sumiu. `xfail` se só houve clipping
em elemento decorativo (sem texto).

**7. Flakiness e mitigação.** Média — é o mais sensível dos dez. Conteúdo lazy que
só aparece ao rolar produziria "texto perdido" falso: mitigação é rolar a página
inteira nos **dois** estados antes de medir, e comparar conjuntos de texto
normalizado (colapsando espaço), nunca posições.

**8. YAML.** `thresholds.gui_zoom_perdidos_max: 0`.

**9. Pseudocódigo.**
```python
def test_zoom_200_nao_perde_conteudo(contexto_gui, settings, perfis):
    normal = _inventario(contexto_gui(viewport=perfis.viewport("desktop")), settings)
    ampliado = _inventario(contexto_gui(viewport=perfis.meio("desktop"),
                                        device_scale_factor=2), settings)
    perdidos = normal.textos - ampliado.textos
    marcos_sumidos = normal.marcos - ampliado.marcos
    metricas.registrar("gui_zoom200_perdidos_n", len(perdidos) + len(marcos_sumidos))
    assert not marcos_sumidos and not perdidos, (
        "A 200% de zoom o conteúdo abaixo deixou de estar disponível "
        "(WCAG 1.4.4):\n" + resumo(marcos_sumidos, perdidos))
```

---

### 3.3 `checks/gui/test_foco.py::test_indicador_de_foco_visivel`

**1. Objetivo e norma.** WCAG 2.2 **2.4.7 Focus Visible** (AA). Quem navega por
teclado precisa saber onde está; `outline: none` sem substituto é a regressão de
CSS mais comum que existe.

**2. Pré‑condições.** `contexto_gui()` padrão + `webqa/foco.py::caminhar`, que
devolve uma `Caminhada` com as `Parada`s (seletor, caixa e estilo computado com e
sem foco). **Uma caminhada, três vereditos** (3.3, 3.4 e 3.5 a consomem) — mesma
economia que `home_response` faz para as dimensões HTTP.

A caminhada **para de três maneiras**, e as três são término normal do laço:

| Como para | O que significa |
|---|---|
| a parada repete a primeira | deu a volta na ordem de tabulação (comportamento do Chromium) |
| `ler_foco()` devolve `None` | o foco saiu do documento — fim natural |
| o teto de 200 Tabs estoura | ou é armadilha, ou é fim de ordem: quem decide são os discriminadores abaixo |

**O terceiro caso é o que exige julgamento**, e ele tem dois discriminadores,
nessa ordem de prioridade:

1. **sonda `Shift+Tab`** (`voltar_tab`, injetada) — um toque só, no ponto de
   estagnação. Se o foco **solta** e vai para o elemento anterior, a caminhada
   tinha chegado ao fim da ordem; se **volta ao mesmo elemento**, algo o prende.
   É evidência comportamental, por isso vem primeiro;
2. **cobertura** — o inventário de focáveis (`focaveis`, também injetado, vindo
   de `JS_ALVOS_DE_TOQUE`). Estagnar com focáveis por visitar é armadilha;
   estagnar tendo visitado todos, fim de ordem.

**Por que os dois, e não só a cobertura.** A cobertura sozinha não separa nada
quando a armadilha está no **último** focável — que é exatamente o caso da
plantada em `/gui/estados`: não sobra ninguém por visitar, e os dois casos ficam
idênticos. A cobertura pega a armadilha do meio da página; a sonda pega a do fim.
A validação da OS‑56 descobriu isso do jeito caro: o conserto por cobertura,
sozinho, **apagava** a detecção da armadilha plantada.

**Fim de ordem é término NORMAL — os três vereditos rodam.** Não é skip: tratá‑lo
como ausência de medida trocaria um falso positivo por um falso silêncio, e os
três critérios de foco continuariam sem medir nada na engine afetada. Só
`armadilha` interrompe (`pytest.fail` na fixture, WCAG 2.1.2).

**Sem sonda e sem inventário a caminhada NÃO afirma armadilha.** Coletor que
falhou é ausência de medida, e ausência de medida não vira acusação — acusar
errado é o defeito que a OS‑56 consertou. Ver `docs/GUI.md §Diferenças por
engine` para o comportamento de plataforma que motivou tudo isto.

**3. Passos.** Esperar `networkidle` (widget que rouba foco no load falsearia a
primeira parada) → caminhar → em cada parada, ler `outline`, `box-shadow`,
`border`, `background-color` e `text-decoration` do elemento focado, e os mesmos
do estado sem foco → marcar "invisível" quando **nenhum** difere.

**4. Asserções e métricas.** `invisiveis <= threshold("gui_foco_invisivel_max")`.
Registra `gui_foco_paradas_n` e `gui_foco_invisivel_n`.

**5. Artefatos.** Captura do elemento focado (`locator.screenshot`) para cada
ofensor, até um teto; JSON da sequência completa.

**6. Aprovação.** Limiar 0. Um único controle sem foco visível já quebra a cadeia
de navegação.

**7. Flakiness e mitigação.** Baixa a média. Transição CSS no foco faz a leitura
pegar o estado intermediário: mitigação é `wait_for_timeout(150)` após cada Tab.
Foco dentro de `iframe` de terceiro sai da caminhada e é **declarado** no laudo,
não ignorado em silêncio.

**8. YAML.** `thresholds.gui_foco_invisivel_max: 0`.

**9. Pseudocódigo.**
```python
def test_indicador_de_foco_visivel(caminhada_de_foco, settings, request):
    invisiveis = [p for p in caminhada_de_foco if not p.estilo_muda_com_foco]
    metricas.registrar("gui_foco_paradas_n", len(caminhada_de_foco))
    metricas.registrar("gui_foco_invisivel_n", len(invisiveis))
    for parada in invisiveis[:5]:
        evidencias.capturar_elemento(parada, request.node.nodeid)
    assert len(invisiveis) <= settings.threshold("gui_foco_invisivel_max"), (
        f"{len(invisiveis)} controles não mudam de aparência ao receber foco "
        "(WCAG 2.4.7) — quem navega por teclado não sabe onde está:\n"
        + "\n".join(f"  {p.seletor}" for p in invisiveis[:10]))
```

---

### 3.4 `checks/gui/test_foco.py::test_ordem_de_tabulacao_segue_a_ordem_visual`

**1. Objetivo e norma.** WCAG 2.2 **2.4.3 Focus Order** (A): a ordem de navegação
preserva significado e operabilidade.

**2. Pré‑condições.** A mesma `caminhada_de_foco`.

**3. Passos.** Para cada par consecutivo de paradas, comparar as caixas: uma
**inversão** é quando a parada seguinte começa acima da anterior por mais que a
altura de uma linha, **ou** está na mesma faixa horizontal e à esquerda (em
documento LTR; a regra espelha em `dir=rtl`). Ignorar pares em contêineres
diferentes com sobreposição vertical — coluna lateral não é inversão.

**4. Asserções e métricas.** `inversoes <= threshold("gui_foco_inversoes_max")`.
Registra `gui_foco_inversoes_n`.

**5. Artefatos.** JSON dos pares invertidos com seletor e caixa dos dois lados.

**6. Aprovação.** Limiar **2** na Fase 1, não 0 — a heurística geométrica tem
falso positivo conhecido em layout de grade, e um smoke que reprova por decisão de
layout legítima seria desligado pela equipe na segunda semana. O limiar aperta
quando houver medição contra alvos reais.

**7. Flakiness e mitigação.** Média, e ela é **de método**, não de execução: a
geometria não conhece a intenção do layout. Mitigações: tolerância de uma
linha; ignorar pares em contêineres irmãos; e o limiar folgado acima. A
alternativa — comparar com a ordem do DOM — é pior: `order` do flexbox e
`grid-area` desacoplam DOM de visual legitimamente, e é justamente esse
descolamento que o critério existe para pegar.

**8. YAML.** `thresholds.gui_foco_inversoes_max: 2`.

**9. Pseudocódigo.**
```python
def test_ordem_de_tabulacao_segue_a_ordem_visual(caminhada_de_foco, settings, direcao):
    inversoes = geometria.inversoes_de_leitura(
        [p.caixa for p in caminhada_de_foco], direcao=direcao)   # puro -> tests/
    metricas.registrar("gui_foco_inversoes_n", len(inversoes))
    assert len(inversoes) <= settings.threshold("gui_foco_inversoes_max"), (
        f"{len(inversoes)} saltos na ordem de tabulação contra a ordem visual "
        "(WCAG 2.4.3):\n" + resumo_de_inversoes(caminhada_de_foco, inversoes))
```

---

### 3.5 `checks/gui/test_foco.py::test_foco_nao_obscurecido`

**1. Objetivo e norma.** WCAG **2.4.11 Focus Not Obscured (Minimum)** (AA) —
**critério novo da 2.2**, e o mais fácil de violar sem perceber: basta um cabeçalho
`position: sticky` e um `scroll-margin` esquecido.

**2. Pré‑condições.** A mesma caminhada.

**3. Passos.** Em cada parada, rolar o elemento para a viewport (é o que o
navegador faz) → obter a caixa → amostrar pontos numa grade 3×3 dentro dela →
`document.elementFromPoint` em cada ponto → contar os pontos em que o elemento
retornado não é o focado nem descendente dele → converter em fração coberta.

**4. Asserções e métricas.** Fração coberta ≤ 25 % em toda parada
(`gui_foco_obscurecido_max`). Registra `gui_foco_obscurecido_n` e a pior fração.

**5. Artefatos.** Captura da viewport com o elemento focado, para cada ofensor.

**6. Aprovação.** Limiar 0 ofensores; a tolerância está na fração de 25 %, que é
a leitura literal do critério ("não inteiramente oculto" no nível mínimo).

**7. Flakiness e mitigação.** Baixa. Risco real: banner de consentimento cobrindo
tudo e produzindo dezenas de ofensores — o que **não** é falso positivo, é o
achado, e a mensagem deve nomear o elemento que cobre para o leitor entender de
imediato.

**8. YAML.** `thresholds.gui_foco_obscurecido_max: 0`.

**9. Pseudocódigo.**
```python
def test_foco_nao_obscurecido(caminhada_de_foco, settings):
    obscurecidos = [(p, p.fracao_coberta) for p in caminhada_de_foco
                    if p.fracao_coberta > 0.25]
    metricas.registrar("gui_foco_obscurecido_n", len(obscurecidos))
    assert len(obscurecidos) <= settings.threshold("gui_foco_obscurecido_max"), (
        f"{len(obscurecidos)} elementos ficam cobertos ao receber foco "
        "(WCAG 2.4.11) — o cursor de teclado desaparece atrás de outro elemento:\n"
        + "\n".join(f"  {p.seletor} coberto por {p.cobridor} ({f:.0%})"
                    for p, f in obscurecidos[:10]))
```

---

### 3.6 `checks/gui/test_alvos.py::test_area_minima_de_toque`

**1. Objetivo e norma.** WCAG **2.5.8 Target Size (Minimum)** (AA) —
**critério novo da 2.2**: 24×24 CSS px, com exceções de espaçamento, equivalente,
inline e essencial. A meta de 44 px das plataformas é mais exigente e entra como
**alerta**, não como reprovação: cobrar norma que não existe desgasta a bateria.

**2. Pré‑condições.** `contexto_gui(viewport=perfil("mobile"), is_mobile=True,
has_touch=True)`. Rolar a página inteira antes de medir — conteúdo lazy não
medido é conteúdo não avaliado, e não avaliado nunca vira aprovado.

**3. Passos.** Coletar interativos visíveis → `bounding_box` de cada — do
elemento **clicável**, não do ícone interno, porque a área de toque costuma vir do
`padding` do pai → aplicar as exceções: *inline* (link dentro de bloco de texto),
*equivalente* (existe outro controle ≥ 24 px para a mesma ação na página) e
*espaçamento* (círculo de 24 px centrado no alvo sem interseção com o círculo do
vizinho) → classificar em ofensor, alerta (24–44 px) ou conforme.

**4. Asserções e métricas.** Zero ofensores. Registra `gui_alvo_menor_px`,
`gui_alvo_abaixo_min_n` e `gui_alvo_abaixo_meta_n`.

**5. Artefatos.** JSON com seletor, caixa, exceção aplicada (ou nenhuma);
captura mobile de página inteira.

**6. Aprovação.** `failed` para ofensor sem exceção. `xfail` quando houver
apenas alertas — informa sem reprovar.

**7. Flakiness e mitigação.** Baixa. Riscos: medir o `<svg>` em vez do `<a>` (o
código sobe até o ancestral clicável); e elemento com `transform: scale`, cujo
`bounding_box` já vem transformado — que é o correto, porque é o que o dedo
encontra.

**8. YAML.**
```yaml
thresholds:
  gui_alvo_toque_px: 24
  gui_alvo_toque_meta_px: 44
```

**9. Pseudocódigo.**
```python
def test_area_minima_de_toque(contexto_gui, settings, perfis):
    pagina = contexto_gui(viewport=perfis.viewport("mobile"), has_touch=True)
    pagina.goto(settings.target_url, wait_until="load")
    rolar_ate_o_fim(pagina)
    caixas = pagina.evaluate(JS_INTERATIVOS_COM_CAIXA)
    laudo = geometria.classificar_alvos(          # puro: exceções da norma -> tests/
        caixas, minimo=settings.threshold("gui_alvo_toque_px"),
        meta=settings.threshold("gui_alvo_toque_meta_px"))
    metricas.registrar("gui_alvo_menor_px", laudo.menor)
    metricas.registrar("gui_alvo_abaixo_min_n", len(laudo.ofensores))
    if not laudo.ofensores and laudo.alertas:
        pytest.xfail(f"{len(laudo.alertas)} alvos entre 24 e 44px — atendem a "
                     "WCAG 2.5.8 mas ficam abaixo da meta das plataformas.")
    assert not laudo.ofensores, (
        f"{len(laudo.ofensores)} alvos de toque abaixo de 24x24 CSS px sem "
        "exceção aplicável (WCAG 2.5.8):\n" + resumo(laudo.ofensores[:10]))
```

---

### 3.7 `checks/gui/test_preferencias.py::test_contraste_em_tema_escuro`

**1. Objetivo e norma.** WCAG **1.4.3 Contrast (Minimum)** (AA), sob
`prefers-color-scheme: dark`. **Complementa** — não repete —
`checks/ux/test_acessibilidade.py`, que roda o axe uma vez, no tema que o
navegador trouxer. Uma régua, dois temas.

**2. Pré‑condições.** `contexto_gui(color_scheme="dark")`. O axe vem de
`_fetch_axe_verified`, à época privado no check de acessibilidade — hoje `baixar_axe_verificado` em `webqa/axe.py:27`, movido pela OS‑45 —
a OS que introduz este teste move a função para `webqa/` e a importa dos dois
lugares, preservando versão pinada e verificação de SHA‑384.

**3. Passos.** Abrir no tema claro e ler o `background-color` computado do `body`
→ abrir no escuro e ler de novo → **se forem iguais, o alvo não implementa tema
escuro: pular com motivo**. Sem essa checagem, o axe mediria o tema claro pela
segunda vez e o teste passaria fingindo cobertura — o pior desfecho possível
(`GUI.md §2.2`, regra 9). Havendo tema, injetar o axe e rodar
`axe.run(..., {runOnly: ['color-contrast']})`.

**4. Asserções e métricas.** Violações sérias e críticas dentro dos limiares
`a11y_serious_max` / `a11y_critical_max` **já existentes** — a mesma régua do tema
claro. Registra `gui_contraste_violacoes_dark_n`.

**5. Artefatos.** JSON das violações (seletor, par de cores, razão medida) +
captura no tema escuro.

**6. Aprovação.** Limiares existentes. `skipped` com motivo quando não há tema
escuro.

**7. Flakiness e mitigação.** Baixa. Alternância de tema por JavaScript após o
load (em vez de por `@media`) mudaria a leitura: mitigação é medir após
`networkidle` e uma espera curta.

**8. YAML.** Nenhuma chave nova — reusa `a11y_critical_max` e `a11y_serious_max`.

**9. Pseudocódigo.**
```python
def test_contraste_em_tema_escuro(contexto_gui, settings, axe_js):
    claro = _fundo_do_body(contexto_gui(color_scheme="light"), settings)
    pagina = contexto_gui(color_scheme="dark")
    pagina.goto(settings.target_url, wait_until="load")
    if _fundo_do_body_de(pagina) == claro:
        pytest.skip("O alvo não implementa tema escuro — não há segundo tema a medir.")
    pagina.add_script_tag(content=axe_js)          # versão pinada, SHA-384 conferido
    r = pagina.evaluate("async () => await axe.run(document, "
                        "{runOnly: ['color-contrast']})")
    serias = [v for v in r["violations"] if v.get("impact") == "serious"]
    metricas.registrar("gui_contraste_violacoes_dark_n", len(serias))
    assert len(serias) <= settings.threshold("a11y_serious_max"), (
        "Contraste insuficiente no tema escuro (WCAG 1.4.3):\n" + resumo_axe(serias))
```

---

### 3.8 `checks/gui/test_preferencias.py::test_reduced_motion_respeitado`

**1. Objetivo e norma.** WCAG **2.3.3 Animation from Interactions** (AAA) e a boa
prática de plataforma: quem declarou `prefers-reduced-motion: reduce` tem motivo
— desconforto vestibular é sintoma físico, não preferência estética.

**2. Pré‑condições.** `contexto_gui(reduced_motion="reduce")`.

**3. Passos.** Abrir → esperar `networkidle` e mais 1 s (animação única de
carregamento termina nesse intervalo, e contá‑la seria falso positivo) →
`document.getAnimations()` → filtrar as **ativas** (`playState === 'running'`) com
iterações infinitas **ou** tempo restante acima de 1 s → coletar também
`scroll-behavior: smooth` no `html` e `<video autoplay>` sem `muted`.

**4. Asserções e métricas.** Zero animações longas ativas sob a preferência
(`gui_animacoes_sob_rm_max`). Registra `gui_animacoes_sob_rm_n`.

**5. Artefatos.** JSON com nome da animação, alvo, duração e iterações.

**6. Aprovação.** Limiar 0 para infinitas; animação entre 0,2 s e 1 s vira
`xfail` na Fase 1.

**7. Flakiness e mitigação.** Baixa a média. O risco é temporal: medir cedo pega
a animação de entrada. Mitigação é a janela acima e o filtro por tempo restante,
não por duração declarada — uma animação de 10 s que já rodou 9,5 s não é
problema.

**8. YAML.** `thresholds.gui_animacoes_sob_rm_max: 0`.

**9. Pseudocódigo.**
```python
def test_reduced_motion_respeitado(contexto_gui, settings):
    pagina = contexto_gui(reduced_motion="reduce")
    pagina.goto(settings.target_url, wait_until="networkidle")
    pagina.wait_for_timeout(1_000)
    ativas = pagina.evaluate(JS_ANIMACOES_LONGAS_ATIVAS)
    metricas.registrar("gui_animacoes_sob_rm_n", len(ativas))
    assert len(ativas) <= settings.threshold("gui_animacoes_sob_rm_max"), (
        f"{len(ativas)} animações seguem rodando com prefers-reduced-motion: reduce "
        "(WCAG 2.3.3):\n" + resumo_de_animacoes(ativas[:10]))
```

---

### 3.9 `checks/gui/test_interatividade.py::test_tbt_long_tasks_e_inp`

**1. Objetivo e norma.** Core Web Vitals (INP ≤ 200 ms é "bom"; TBT é o proxy de
laboratório) e ISO 25010 (eficiência de desempenho). Fecha a lacuna mais cara do
`VITALS_JS` atual, que observa só LCP e `layout-shift`
(`checks/frontend/test_rendering.py:26-46`).

**2. Pré‑condições.** Chromium (`longtask` não existe em WebKit) — nas demais
engines, **skip com instrução**, como a fixture `browser` faz. `contexto_gui()`
próprio, e o JS registrado por `add_init_script` **antes** do `goto`, com a mesma
disciplina que `tests/test_vitals_js.py` já fixa para o irmão: observers
registrados fora da callback, com `buffered: true`; **toda leitura dentro da
callback**; `null` inicial, nunca zero.

**3. Passos.** Registrar observers `longtask` e `event` → `goto` → após o load,
uma interação neutra e que não navega (`Tab`, ou `hover` no primeiro botão) →
janela de 2 s → coletar: TBT = Σ(duração − 50) das tarefas acima de 50 ms na
janela de carga; long tasks = contagem; INP ≈ maior `event.duration`.

**4. Asserções e métricas.** `gui_tbt_ms`, `gui_long_tasks_n`, `gui_inp_ms`
contra os limiares. Todas registradas passem ou falhem os asserts.

**5. Artefatos.** Trace do Playwright (`tracing.start/stop`) apenas em caso de
falha — trace de execução verde é peso morto no artefato.

**6. Aprovação.** No ambiente oficial (VPS, `docs/VPS.md`) o estouro é `failed`.
No CI é `xfail` com o motivo escrito. A distinção vai no laudo; afrouxar o limiar
para caber na máquina mais barulhenta seria o R5 se realizando.

**7. Flakiness e mitigação.** **Alta — a maior dos dez.** Máquina compartilhada
faz TBT oscilar por fatores fora do alvo. Três mitigações, e nenhuma é retry:
(a) veredito duro só no ambiente oficial; (b) `metricas.registrar` sempre, para o
consolidado da campanha mostrar mediana e pior caso em vez de uma amostra; (c) a
oscilação vai para o ledger de `scripts/estabilidade.py`, que é o mecanismo da
casa para separar veredito de flake. Um `@retry` esconderia exatamente o sinal
que o ledger existe para medir.

**8. YAML.**
```yaml
thresholds:
  gui_tbt_ms: 200
  gui_inp_ms: 200
  gui_long_tasks_max: 5
```

**9. Pseudocódigo.**
```python
def test_tbt_long_tasks_e_inp(contexto_gui, settings, engine, request):
    if engine != "chromium":
        pytest.skip(f"long task / event timing não disponível em {engine} — "
                    "métrica não medida (não é aprovação).")
    pagina = contexto_gui()
    pagina.add_init_script(VITALS_INTERACAO_JS)      # webqa/vitals_interacao.py
    pagina.goto(settings.target_url, wait_until="load", timeout=60_000)
    pagina.keyboard.press("Tab")                     # interação neutra, não navega
    m = pagina.evaluate("() => window.__webqa_interacao(2000)")
    for chave in ("gui_tbt_ms", "gui_inp_ms", "gui_long_tasks_n"):
        metricas.registrar(chave, m[chave])          # None é descartado, não vira 0
    if m["gui_inp_ms"] is None:
        pytest.xfail("Nenhum evento de interação registrado na janela — "
                     "INP não medido; ausência não é rapidez.")
    duro = os.environ.get("WEBQA_ORIGEM") == "vps"
    problemas = avaliar_orcamento(m, settings)        # puro -> tests/
    if problemas and not duro:
        pytest.xfail("Orçamento de interação estourado em ambiente não oficial "
                     f"(ruído de CI): {problemas}")
    assert not problemas, "\n".join(problemas)
```

**10. Como ficou (OS‑46) — três desvios deste esboço, e o motivo de cada um.**

* **Suporte detectado em runtime, não pelo nome da engine.** O esboço pulava
  comparando `engine != "chromium"`. O check pergunta a
  `PerformanceObserver.supportedEntryTypes` o que existe. Uma lista de engines
  escrita hoje envelhece em silêncio: quando o Firefox implementar `longtask`, a
  suíte pularia dizendo que a API não existe — e "não medido" viraria permanente
  sem nada ficar vermelho.
* **A ordem dos vereditos: estouro antes de ausência.** O esboço pulava (`xfail`)
  quando o INP não fosse medido, ANTES de olhar o orçamento. Um alvo que trava
  660ms sairia do laudo como "não medi a interação". A ausência de INP só decide
  quando não há nada mais grave a dizer — e aí sim vira `xfail`, porque passar
  anunciaria cobertura de INP que não houve.
* **`first-input` ao lado de `event`.** A Event Timing API descarta eventos
  abaixo do `durationThreshold` (mínimo 16ms). Um `Tab` numa página saudável
  custa ~16ms e cai na borda: sem `first-input`, que ignora o limiar, o check
  pularia SEMPRE contra alvo conforme, e "não medido" ficaria indistinguível de
  "não suportado". Medido na sonda: 16ms na página conforme, 112–120ms no alvo
  fabricado.

E um item do aceite que **não** foi cumprido como escrito: o nodeid ficou em
`fora_do_contrato`, não em `devem_falhar`. Um desfecho condicionado a
`WEBQA_ORIGEM` faz o contrato reprovar por AMBIENTE em toda execução fora da VPS
— e o contrato 1:1 existe para reprovar por regressão. Mesma navalha da OS‑45
(rede externa), mesmo critério: o contrato só aceita check cujo desfecho contra o
fixture dependa exclusivamente do que o fixture serve.

---

### 3.10 `checks/gui/test_resiliencia.py::test_falha_de_api_produz_erro_acionavel`

**1. Objetivo e norma.** Nielsen **H9** (ajudar a reconhecer, diagnosticar e
recuperar‑se de erros) e **H1** (visibilidade do estado); ISO 25010, tolerância a
falhas. Tela branca sob 500 é o pior defeito de interface que existe, e nada na
suíte o pega hoje.

**2. Escopo e fronteira.** A interceptação acontece **no cliente**
(`page.route`): o alvo recebe **menos** requisições, nunca mais, e nunca uma que
ele não tenha oferecido. É passivo pelo critério de `GUI.md §2.1` e **não exige
gate**. A fronteira está escrita aqui porque um leitor apressado veria "simular
500" e pensaria em sondagem ativa.

**3. Pré‑condições.** Descoberta passiva dos endpoints XHR/fetch de **mesma
origem** a partir da carga normal, reusando o que `network_log` já coleta
(`webqa/trackers.py::NetworkLog`). Terceiro nunca é interceptado — mesma
disciplina de respeito a terceiros da bateria LGPD. Sem XHR observável:
`skipped` com motivo.

**4. Passos.** Para o endpoint de maior volume (teto de 3): novo contexto →
`route` devolvendo 500 → `goto` → janela de observação de 5 s → avaliar o DOM
final: (a) `main` tem texto? (b) existe elemento visível, novo em relação à carga
saudável, com vocabulário de erro? (c) esse elemento contém termo técnico
proibido? (d) quantos erros novos no console? (e) quantas requisições ao mesmo
endpoint na janela (laço de repetição)?

**5. Asserções e métricas.** Página não em branco; mensagem presente; nenhum termo
de `gui_termos_proibidos`; erros de console ≤ `gui_console_erros_pos_falha_max`;
requisições ao endpoint ≤ 5. Registra `gui_resil_console_n` e
`gui_resil_tentativas_n`.

**6. Artefatos.** Console sanitizado, lista de requisições ao endpoint, e o texto
do elemento de erro — sanitizado. Captura pós‑falha **condicional**: esta é a
spec de maior risco de PII do conjunto, porque tela de erro de aplicação real
costuma exibir dado de quem estava logado. Sem `WEBQA_GUI_SCREENSHOTS=1`, o
achado se sustenta inteiro no texto e nos seletores.

**7. Aprovação.** `failed` para tela branca ou stack trace vazado — os dois são
inequívocos. A ausência de mensagem, isoladamente, é `xfail` na Fase 1: a
heurística de "vocabulário de erro" é fraca em alvo internacionalizado, e reprovar
com heurística fraca custa a credibilidade da bateria inteira — o mesmo argumento
que `webqa/sanitize.py:29-34` usa para recusar detecção por entropia.

**8. Flakiness e mitigação.** Média. Riscos: SPA com repetição exponencial
legítima (mitigado pela janela fixa e pelo teto em YAML) e endpoint escolhido que
não alimenta a tela principal (mitigado por escolher o de maior volume e listar,
no laudo, qual foi interceptado).

**9. YAML.**
```yaml
thresholds:
  gui_console_erros_pos_falha_max: 3
  gui_resil_tentativas_max: 5
# data/gui-perfis.yaml
resiliencia:
  termos_proibidos: ["Traceback", "NullPointer", "undefined is not",
                     "500 Internal", "SQLSTATE", "Exception in"]
  vocabulario_de_erro: ["erro", "falha", "indisponível", "tente novamente",
                        "error", "failed", "unavailable", "try again"]
```

**10. Pseudocódigo.**
```python
def test_falha_de_api_produz_erro_acionavel(contexto_gui, settings, endpoints_xhr,
                                            perfis, request):
    if not endpoints_xhr:
        pytest.skip("Alvo sem chamadas XHR/fetch de mesma origem observáveis.")
    alvo_xhr = endpoints_xhr[0]                 # o de maior volume
    pagina = contexto_gui()
    tentativas = contar_requisicoes(pagina, alvo_xhr)
    pagina.route(alvo_xhr, lambda rota: rota.fulfill(status=500, body="{}"))
    pagina.goto(settings.target_url, wait_until="load", timeout=60_000)
    pagina.wait_for_timeout(5_000)
    laudo = resiliencia.avaliar(pagina, perfis.resiliencia())   # puro -> tests/
    metricas.registrar("gui_resil_console_n", laudo.erros_console)
    metricas.registrar("gui_resil_tentativas_n", tentativas())
    evidencias.capturar(pagina, request.node.nodeid, "pos-falha-500")
    assert not laudo.tela_branca, (
        f"Com {alvo_xhr} respondendo 500, a página ficou sem conteúdo principal "
        "— o visitante vê tela branca e não sabe o que aconteceu (Nielsen H9).")
    assert not laudo.termos_vazados, (
        f"A mensagem de erro expõe detalhe técnico: {laudo.termos_vazados}.")
    if not laudo.mensagem_visivel:
        pytest.xfail("Nenhuma mensagem de erro reconhecível após a falha da API. "
                     "Sinal, não prova: a heurística de vocabulário é fraca em "
                     "alvo internacionalizado.")
    assert laudo.erros_console <= settings.threshold("gui_console_erros_pos_falha_max")
```

**11. Como ficou (OS‑47) — quatro checks, e a partição do contrato.**

Um check por modo de falha, **nunca parametrizado**: o contrato é por nodeid
exato, e `::test_x[500]` não sobrevive a alguém reordenar a lista. A partição foi
escrita antes de codar e confirmada na validação — ela segue o DESFECHO, não o
assunto, e é por isso que quatro checks do mesmo arquivo caem em lados opostos:

| Check | Modo | Contra o fixture | Contrato |
|---|---|---|---|
| `test_erro_500_na_api_nao_vaza_detalhe_tecnico` | 500 com corpo HTML | **failed** — `SyntaxError: Unexpected token '<'` na tela | `devem_falhar` |
| `test_json_truncado_nao_vaza_detalhe_tecnico` | 200 cortado no meio | **failed** — `SyntaxError: Unterminated string in JSON` | `devem_falhar` |
| `test_api_que_nao_responde_avisa_o_visitante` | pedido pendente na janela | **xfail** — silêncio | `fora_do_contrato` |
| `test_perda_de_conexao_e_comunicada` | `set_offline` após a carga | **xfail** — silêncio | `fora_do_contrato` |

Três desvios do esboço acima, todos vindos da execução:

* **a origem, e não a `target_url`.** Comparar o endpoint com a URL inteira do
  alvo descartava a própria API como "terceiro" quando o alvo é uma página
  interna (`/gui/resiliente` × `/gui/api/pedidos`), e os três checks pulavam
  dizendo que não havia o que interceptar. A comparação é com `origem_de(...)`.
* **offline só depois da carga ASSENTADA.** Cortar a rede no instante do `load`
  invertia o resultado: o evento disparava, a página conforme mostrava o aviso, e
  o `fetch` que ainda estava no ar resolvia com sucesso e SOBRESCREVIA o aviso. O
  check acusava de silêncio uma página que tinha avisado. "A conexão caiu com a
  página aberta" e "caiu no meio da carga" são cenários diferentes.
* **erros de console contados contra a carga saudável.** O alvo fabricado produz
  três numa carga limpa (tracker sem DNS, `.js` servido como HTML). Cobrá‑los
  aqui seria cobrar deste check o defeito de outro.

E duas adições ao alvo fabricado, feitas de uma vez só com o custo conferido
(sequência do ledger em 0/10, logo reinício de graça): um segundo consumidor da
mesma API com `catch(e => elemento.textContent = e)` — o anti‑padrão que produz a
classe `failed`, sem o qual os quatro checks terminariam em `xfail` e nenhum
entraria no contrato — e a página CONFORME `/gui/resiliente`, em `paginas_gui/`
(fora de `identidade()`, custo zero), que é onde os quatro são vistos **passando**.

---

## 4. O que ficou fora, e por quê

| Proposta | Por que não entra | O que entra no lugar |
|---|---|---|
| **Storybook / teste de componente isolado** | a suíte é caixa‑preta contra uma URL e não vê o fonte da interface do alvo (`ARQUITETURA.md:12-13`, `ESCOPO-EAP.md:34`) | galeria de estados servida por `fixture_target/paginas_gui/`, no padrão que `scripts/audita_design.py` já usa: servidor local + pytest contra arquivos. É "nível componente" possível numa suíte caixa‑preta |
| **Leitor de tela real (NVDA/JAWS/VoiceOver)** | não roda em CI Linux headless, e o comportamento é específico de cada leitor | árvore de acessibilidade do Playwright (nome, papel, estado) — **proxy declarado**, não substituto (`GUI.md §5.1`) |
| **SUS, SEQ, satisfação, sucesso real de tarefa** | exigem pessoas respondendo | protocolo do `GUI.md §5.2`, com as mesmas jornadas dos cenários BDD para as réguas coincidirem |
| **Pixel‑diff como veredito primário** | converte deriva de fonte e revisão de navegador em PR vermelho, e treina a equipe a aprovar imagem sem olhar (R18) | veredito por geometria e CSS computado; diff por bloco só contra o alvo fabricado, com máscara e tolerância declaradas |
| **Pillow, pixelmatch, numpy, Percy** | dependência nova; `Pillow` **já foi rejeitada com fundamento registrado** (`PROXIMOS-PASSOS.md:585`) | `zlib` + `struct` sobre o PNG do Playwright, diff por bloco 16×16 — com a ressalva abaixo, que é condição de aceite, não detalhe |
| **Lighthouse** | dependência de runtime Node, e — mais importante — **score de Lighthouse não é usabilidade**. Tratar os dois como sinônimo é o erro que esta camada existe para não cometer | medição direta de INP/TBT/long tasks pelos observers do próprio navegador |
| **Injeção de XSS, fuzzing de formulário** | pentest ofensivo está fora do escopo (`ESCOPO-EAP.md:28`) | GUI‑SEC‑01: leitura **passiva** das diretivas da CSP que já vieram no cabeçalho |
| **Clique em banner de consentimento, DSAR pela interface** | escreve no sistema do alvo; exige `WEBQA_ACTIVE_PROBES_AUTHORIZED=1` (`webqa/gates.py:121-131`) | nada na Fase 1. Fica no backlog, atrás do gate — e o primeiro check que o consumir altera `tests/test_fase_c_travada.py:314-326`, num PR que diga isso |
| **Fluxo logado (formulário de login, sessão, MFA)** | fora do escopo (`ESCOPO-EAP.md:19-24`); Basic Auth está dentro, formulário está fora | área autenticada por Basic Auth, via `paginas_internas` |
| **Dispositivo real, notch, teclado virtual, Safari de verdade** | emulação é emulação; WebKit ≠ Safari | emulação declarada como tal no laudo, para ninguém ler aprovação emulada como aprovação em dispositivo |
| **LLM executando objetivo aberto no navegador** | `tests/test_convencoes.py:209-224` — "a IA processa achados já produzidos, não participa de agir contra o alvo" | GUI‑EXPL‑01: análise da jornada **já coletada** |

### 4.1 A ressalva do decoder PNG — condição de aceite, não detalhe

Ler PNG com `zlib` + `struct` é viável porque o Playwright emite RGBA de 8 bits,
não entrelaçado. Mas "viável no caso que testei" é exatamente a premissa que
produz o pior defeito possível nesta peça: **decodificar errado em silêncio**. Um
decoder que interpreta mal um PNG entrelaçado (Adam7), paletizado ou de
profundidade diferente de 8 bits não estoura — ele devolve uma matriz plausível,
e o diff visual emite veredito sobre uma imagem que não existe.

> **Aceite obrigatório da OS que introduzir `webqa/imagem.py`:** o decoder é
> **fail‑closed**. Bit depth ≠ 8, `color type` fora de RGB/RGBA, ou
> `interlace method` ≠ 0 levantam erro com mensagem que nomeia o motivo, e o
> check correspondente vira **`error`** (o teste não aconteceu), nunca `passed`.
> Há caso de teste com PNG entrelaçado fabricado — um detector que nunca detectou
> nada não está provado.

> **Cumprido na OS‑49, com uma hipótese CORRIGIDA.** O aceite acima previa que
> o Playwright emite RGBA; medido, o Chromium 1.56 emite **`color_type=2` (RGB,
> três canais)** — e em **vários chunks IDAT**, o que derrubaria um decoder que
> lesse só o primeiro. As duas viraram teste com navegador
> (`tests/test_imagem.py::test_png_real_do_playwright_e_RGB_de_8_bits_nao_entrelacado`),
> que é o que transforma a hipótese em contrato: um upgrade que mude o formato
> reprova ali, com o motivo à mão, em vez de virar um diff visual inexplicável.
> As quatro recusas têm caso próprio, incluindo o PNG entrelaçado fabricado.

Duas consequências para a estimativa da OS: o *unfiltering* do PNG tem cinco
tipos por linha (None, Sub, Up, Average, Paeth) e não cabe numa função sob
`C901 max-complexity = 8` (`pyproject.toml:46-51`) — são umas quatro ou cinco
funções, e é bom que sejam, porque cada filtro fica testável isoladamente contra
vetor conhecido. E o gate de complexidade vale em `webqa/`, que é onde o módulo
mora — escondê‑lo no check para escapar dele seria contornar a guarda, não
cumpri‑la.

### 4.2 Bloqueio por relógio × por trabalho — o alvo precisa poder reagir

Descoberto medindo, na OS‑50, e vale para qualquer alvo que alguém queira
exercitar com throttling de CPU.

O bloqueio plantado na home do alvo fabricado é `while (Date.now() < fim)`: um
laço com prazo de **relógio**. Emular CPU quatro vezes mais lenta reduz
instruções por segundo — não o relógio. O laço sai no mesmo instante, a tarefa
dura os mesmos 110 ms, e a degradação **não tem efeito nenhum**. Medido: TBT de
**363 ms sob CPU ×4 contra 357 ms sem throttle**, 2% de diferença.

O perigo não é o número errado, é o número *plausível*: um check de CPU lenta
apontado para essa página relata "a degradação não mudou nada" e está certo pelo
motivo errado — ele mediu um alvo que **não pode reagir ao que ele emula**. Quem
lê conclui que o alvo é robusto.

> **Consequência para toda OS que emular CPU:** a violação de referência precisa
> ser **computacional** — trabalho de quantidade fixa, cujo tempo escala com a
> velocidade da máquina. `/gui/pesado` faz isso, e o resultado é a propriedade
> que torna a família interessante: **invisível sem throttle (TBT 0, nenhuma
> tarefa longa) e severa sob ×4 (TBT ~1300 ms em dez tarefas longas)**. É a
> classe de defeito que passa em toda medição de laboratório e falha na mão de
> quem usa — a razão de a família existir.

O dimensionamento é apertado dos dois lados e a janela é estreita por aritmética:
com fator fixo em 4, o bloco precisa ficar **abaixo** de 50 ms sem throttle e bem
**acima** de 50 ms com ele, o que o confina a 21–50 ms na máquina de referência.
O grau de liberdade que sobra é a **contagem** de blocos, não o tamanho de cada
um. Máquina muito mais rápida encolhe o bloco e pode apagar o sinal — limite
conhecido, e o motivo de o veredito duro desta família só existir sob
`WEBQA_ORIGEM=vps`, onde a máquina é uma só e conhecida.

### 4.3 Zoom 400% — **coberto**, não implementado (OS-52)

A WCAG 1.4.10 define reflow a **320 CSS px**, e a nota da própria norma diz que
isso equivale a uma viewport de 1280 px a **400% de zoom**. O
`checks/gui/test_reflow.py::test_sem_rolagem_horizontal_em_320px` (OS‑42) já mede
essa largura — o perfil `reflow_aa` de `data/gui-perfis.yaml` é 320×640 — e a
docstring dele já afirma a equivalência. Um check de "zoom 400%" mediria a mesma
coisa com outro nome, e seria a **primeira duplicação da trilha em 12 OSs**.

> **Conferido antes de implementar, e é esse o barato que vale a nota.** A
> conferência custou uma leitura; a duplicação custaria um check a manter para
> sempre, dois números com o mesmo significado no laudo e a dúvida, daqui a um
> ano, sobre qual dos dois é o certo quando discordarem.

**O vizinho que pareceria sobrar, e por que ele também não entra.** A 1.4.10 tem
outra metade — "sem perda de informação ou funcionalidade" —, e a suíte só mede
perda a **200%** (`test_zoom_200_nao_perde_conteudo`, viewport de 683 px). Medir
perda a 320 px seria cobertura nova de verdade. Foi recusado mesmo assim:
`perdidos_entre` acusaria toda navegação que colapsa **legitimamente** em tela
estreita — menu que vira hambúrguer, coluna secundária que desce —, que é
território do **GUI‑RESP‑05**. Seria gerador de falso positivo, e falso positivo
em bateria de acessibilidade custa a credibilidade da bateria inteira.
