# Camada GUI — qualidade não funcional da interface renderizada

Contrato da dimensão `gui`: o que ela mede, o que ela **não** mede, e as cercas
que ela não cruza. Leia antes de escrever qualquer coisa em `checks/gui/`.

Base deste documento: `main` @ `2e15aec` (pós #80).

> **Nota epistêmica (vale para toda a dimensão).**
> Esta camada **instrumenta a interface**; ela não julga se a pessoa entendeu.
> Uma falha aqui **prova** um defeito de interface — um alvo de toque de 16 px é
> pequeno demais em qualquer contexto, e uma barra fixa que cobre o foco cobre o
> foco de todo mundo. Passar **não certifica** usabilidade: geometria conforme
> não é pessoa atendida, e satisfação, confiança, carga cognitiva e clareza de
> rótulo continuam exigindo os humanos do §5.
>
> É a mesma disciplina que a dimensão `lgpd` já pratica (`docs/LGPD.md`), pelo
> mesmo motivo: um número que se deixa ler como selo vira selo.

---

## 0. Estado: EM CONSTRUÇÃO — OS‑40 a OS‑50 entregues

`checks/gui/` existe e tem dez arquivos de check. Este documento continua sendo
**contrato**, não descrição: ele diz o que pode ser construído e sob que
condições, e o que já foi construído está registrado na tabela `Concluído` da
fila de OS — que é o lugar onde essa contagem envelhece bem, porque muda a cada
entrega.

> **Esta linha esteve errada por nove OSs.** Ela dizia "PLANEJADA — nenhuma linha
> de código" e "`checks/gui/` **não existe**" enquanto catorze módulos de `webqa/`,
> dez arquivos de check e vinte orçamentos já estavam em `main`. Corrigida na
> OS‑50, como carona declarada. Não é detalhe de forma: o §2.10 da casa manda
> desconfiar do código quando prosa e código discordam, e uma prosa que nega a
> existência do código treina quem lê a ignorar a prosa — que é o jeito mais
> barato de um contrato deixar de valer.

O catálogo priorizado e a especificação dos dez primeiros testes estão em
[`GUI-CATALOGO.md`](GUI-CATALOGO.md). A fila executável está em
[`handoff/ordens-de-servico/OS-gui-fila.md`](handoff/ordens-de-servico/OS-gui-fila.md).

Escrever o contrato antes do código é decisão registrada da casa
(`PROXIMOS-PASSOS.md §2.10`): a redação é o momento em que a intenção e a
implementação são confrontadas, e vários defeitos deste projeto apareceram
enquanto alguém redigia, não enquanto depurava. As cercas do §2 foram escritas
**antes** da arquitetura do §3 exatamente por isso — e cortaram itens do catálogo
que pareciam bons no papel.

---

## 1. Diagnóstico da suíte atual

Levantamento feito pelo **conteúdo** dos arquivos, não pelo nome. Todo `arquivo:linha`
abaixo foi conferido.

### 1.1 O que já existe

| Dimensão | Onde | O que cobre de fato | Nível | O que NÃO enxerga |
|---|---|---|---|---|
| `frontend` (render) | `checks/frontend/test_rendering.py` | FCP, LCP, CLS, DCL, peso transferido, console limpo — uma página, um viewport (o default do Playwright), rede e CPU sem restrição. Precisão importa aqui: os **únicos `PerformanceObserver`** são `largest-contentful-paint` e `layout-shift` (`:30-35`); FCP e DCL vêm de `getEntriesByType` lido **depois** da janela, dentro da callback (`:37-43`) | sistema | INP, TBT, TTI, long tasks, FPS, memória; qualquer viewport que não o default |
| `frontend` (estático) | `test_html_quality.py`, `test_assets.py` | doctype, `lang`, charset, `<title>`, `meta viewport`, peso do HTML, contagem de CSS/JS, scripts bloqueantes, `img` com dimensões | integração | tudo que só existe depois do CSS aplicado |
| `ux` (a11y) | `checks/ux/test_acessibilidade.py` | axe‑core 4.9.1 (SHA‑384 verificado em `webqa/axe.py:21-24`) na **home**, contagem por impacto; `img[alt]` e rótulo de input por sopa | sistema | teclado, reflow, zoom, movimento, alvo de toque, tema escuro, páginas internas |
| `ux` (heurísticas) | `test_heuristicas_nielsen.py` | `<title>`, favicon, 404 com link de saída, input tipado, link descritivo, botão de envio | integração | tudo que é comportamento (feedback, recuperação, estado) |
| `ux` (AI) | `test_arquitetura_informacao.py` | h1 único, saltos de heading, `<nav>` rotulado, sitemap/robots, `<main>` | integração | jornada: caminho esperado × real, becos sem saída |
| `functional` | `test_links.py`, `test_forms.py` + `webqa/navegacao.py` | crawler educado, formulários (método, HTTPS, autocomplete) | sistema | estados de formulário (erro, carregando, vazio) |
| `acceptance` | `features/*.feature` | 3 cenários passivos (idioma, conteúdo, 404) | aceitação | cenário com critério **quantitativo** de usabilidade |
| `seguranca` + `backend` | `checks/seguranca/*`, `test_security_headers.py` | CSP presente, clickjacking, HSTS, nosniff, mixed content, SRI, cookies, segredos, SVG, EXIF, sourcemap | integração | **qualidade** da CSP (`unsafe-inline`, Trusted Types) |
| `lgpd` | `checks/lgpd/*` | consentimento prévio, PII em trânsito, transparência, terceiros, retenção | sistema | interação com o banner e DSAR — e isso é decisão de gate, não código faltando |
| compatibilidade | `webqa/navegador.py:24`, fixture `browser` | matriz chromium/firefox/webkit por `WEBQA_BROWSER_ENGINES`, fail‑closed | infraestrutura | matriz de **viewport**, tema, `forced-colors`, RTL |

### 1.2 As lacunas

| Lacuna | Por que passou batido | Custo de deixá‑la aberta | Automatizável? |
|---|---|---|---|
| Foco visível, ordem de tabulação, foco obscurecido | exigem **caminhar** pela página; a suíte só lia sopa | teclado é a via primária de quem não usa mouse; WCAG 2.4.11 é critério **novo** da 2.2 e ninguém o cobre | sim, integralmente |
| Reflow a 320 px e zoom de texto a 200 % | exigem contexto com viewport próprio | 1.4.10 e 1.4.4 são AA; um alvo pode passar em tudo que a suíte mede hoje e ser inutilizável no celular | sim |
| Tamanho de alvo de toque | exige geometria (`bounding_box`) | 2.5.8 é critério **novo** da 2.2, AA | sim, com a exceção de espaçamento da própria norma |
| Contraste em tema escuro e `forced-colors` | o axe roda uma vez, no tema que o navegador trouxer | metade dos usuários pode estar vendo o tema que ninguém mediu | sim |
| `prefers-reduced-motion` | nunca emulado | 2.3.3; movimento não suprimido é barreira vestibular real | sim |
| INP, TBT, long tasks | `VITALS_JS` observa só LCP e `layout-shift` | LCP bom com INP ruim é a assinatura clássica de página que *parece* rápida | sim (chromium) |
| Rede degradada e CPU limitada | nenhuma emulação CDP na suíte | orçamento medido em fibra não descreve o usuário | sim (chromium) |
| Resiliência a falha de API, offline, sem JS | inexistente | tela branca sob 500 é o pior defeito de interface que existe, e nada o pega | sim, por interceptação **no cliente** |
| Regressão visual e consistência de tokens | inexistente | mudança visual não intencional passa despercebida | parcialmente — ver §3.4 |
| Usabilidade quantitativa (TSR, ToT, cliques) | a aceitação é qualitativa | sem número não há tendência, e sem tendência não há regressão detectável | sim, para o **sintético**; o humano é §5 |

### 1.3 O que **parece** lacuna e não é

Escrever isto é metade do valor do diagnóstico: um catálogo que propõe o que já
existe infla a contagem sem informação nova, que é exatamente o argumento com que
`checks/seguranca/test_headers_e_conteudo.py:5-11` justifica o próprio recorte.

- **Meta viewport** — já em `checks/frontend/test_html_quality.py:45`. A lacuna
  real é diferente: aquele check faz `grep` por `width=device-width` e **não**
  acusa `user-scalable=no` nem `maximum-scale=1`, que é o que bloqueia zoom.
- **`alt` de imagem e rótulo de input** — já em `checks/ux/test_acessibilidade.py:55,63`.
- **Contraste** — o axe **já** o avalia, mas de forma **opaca**: a suíte só conta
  violações por impacto, nunca nomeia a regra, nunca fixa razão e nunca roda num
  segundo tema. A lacuna é a nomeação e a variação, não a checagem.
- **Matriz de engines** — **já existe** (`webqa/navegador.py:24` +
  `.github/workflows/compatibilidade.yml`). A camada `gui` a **reusa**; construir
  uma segunda seria duplicar a régua.
- **SRI** — coberto três vezes (`lgpd/test_terceiros.py:78` reprova,
  `seguranca/test_arquivos_e_metadados.py:191` informa, e a própria injeção do
  axe verifica hash). Não entra.
- **Clickjacking e cookies** — `checks/backend/test_security_headers.py:25,39` e
  `checks/seguranca/test_cookies.py`. Não entram.

---

## 2. Fronteiras que esta camada não cruza

### 2.1 Passivo × ativo: onde exatamente fica o clique

A fronteira da casa é **ética, não técnica** (`PROXIMOS-PASSOS.md §2.7`).

O critério **não** é "emite requisição nova" — e é importante dizer isso com
precisão, porque a formulação ingênua é falsa e se refuta em trinta segundos de
DevTools: `hover` dispara *prefetch* em bibliotecas de pré‑carregamento, rolagem
dispara *lazy‑load* de imagem, e redimensionar dispara `srcset` e *media query*
que baixam outros arquivos. Interação **provoca** requisição, sim.

O critério correto é o que `webqa/gates.py:12` já usa para decidir o que precisa
de autorização: **escrever no sistema do alvo**. E a pergunta que separa os dois
lados é: *o alvo estaria entregando isto a qualquer visitante que fizesse a mesma
coisa?*

| Ação | Passivo por quê |
|---|---|
| `keyboard.press("Tab")`, `focus()`, `hover()` | qualquer visitante que passa o mouse provoca o mesmo *prefetch*. É leitura que o alvo oferece |
| `new_context(viewport=…)`, `emulate_media(color_scheme=…, reduced_motion=…)` | é o mesmo carregamento de sempre, com outra preferência declarada. O `srcset` que vier é o que o alvo escolheu servir àquele viewport |
| rolagem | dispara *lazy‑load* — que é exatamente o que acontece quando alguém lê a página |
| `getComputedStyle`, `getBoundingClientRect`, árvore de acessibilidade | leitura pura, nada sai |
| `page.route(...)` devolvendo 500 / timeout / JSON truncado | a interceptação é **no cliente**: o alvo recebe **menos** requisições, nunca mais, e nunca uma que ele não tenha oferecido |
| `context.set_offline(True)`, `java_script_enabled=False` | configuração do nosso navegador |
| emulação CDP de rede e CPU | idem |

Nenhuma das ações acima **escreve**: não cria registro, não submete dado, não
altera estado do alvo. É isso que as mantém deste lado da linha — não a contagem
de GETs.

**Exige `WEBQA_ACTIVE_PROBES_AUTHORIZED=1`** (`webqa/gates.py:12,121-131`, que
nomeia literalmente "submeter formulário, clicar em banner"):

- clicar em "aceitar"/"recusar" num banner de consentimento;
- submeter qualquer formulário;
- exercer direito de titular pela interface;
- qualquer clique que **navegue** ou **envie**.

**Fora do escopo, com ou sem gate** (`ESCOPO-EAP.md:28`): injetar payload de XSS,
fuzzing de campo, qualquer coisa ofensiva. O que a camada faz em segurança de
interface é **passivo por parsing** — ler a diretiva da CSP que já veio no
cabeçalho, não testá‑la com carga.

### 2.2 As guardas da casa que constrangem esta camada

Cada uma é imposta por um teste, não por combinação. A coluna da direita é o que
**não** pode ser proposto.

| # | Regra | Onde está encarnada | O que a camada não pode fazer |
|---|---|---|---|
| 1 | Marcador não registrado é erro de coleta | `pytest.ini:4` (`--strict-markers`), bloco `:5-15` | usar `@pytest.mark.gui` antes da linha existir. As descrições ali são **ASCII sem acento** — seguir a forma |
| 2 | Literal de caminho sensível banido em `checks/` | `tests/test_fase_c_travada.py:42-44,146-160` | escrever `/.git`, `/.env`, `/backup.zip`, `/.DS_Store`, `/wp-config`, `/.htpasswd` em código de check — nem como exemplo. Docstring e comentário seguem livres: explicar não é fazer |
| 3 | Símbolo de sondagem banido em `checks/` | `tests/test_fase_c_travada.py:47-49,194-198` | nomear helper `sondar_*`, `probe_*`, `seguir_sublinks`, `baixar_extras`. Um `sondar_viewport` reprova o CI |
| 4 | Prefixo `test` proibido em biblioteca | `tests/test_convencoes.py:30-41,50-75` | helper em `webqa/`, `scripts/` ou `fixture_target/` chamado `testar_*`, `testes_*` ou `teste_*`. O pytest coleta por `test*`, não `test_*` |
| 5 | Nenhum check consome `require_active_probes` hoje | `tests/test_fase_c_travada.py:314-326` | o primeiro check que o consumir **altera esse teste**, num PR que diga isso — e o arquivo é protegido por CODEOWNERS |
| 6 | `report/` nunca é versionado | `.gitignore:1-4,19`; R8 | guardar linha de base visual de alvo real em `report/` **ou** em qualquer lugar versionado (§3.4) |
| 7 | `sanitize_text` é a borda de escrita **de texto** | `webqa/sanitize.py:156`; `webqa/report.py:236-238` varre a string já serializada | supor que uma captura de tela está sanitizada. Ela não está — não existe mascarador de pixel. É o R19 |
| 8 | `browser_page` é de sessão e compartilhada | `conftest.py:200-205`; preço registrado em `ARQUITETURA.md:55` | mudar viewport, tema ou movimento nela. Toda variação abre contexto próprio, no molde de `network_log` (`conftest.py:338-349`) |
| 9 | Ausência nunca vira zero | `PROXIMOS-PASSOS.md §2.1`; `webqa/metricas.py:26-45` recusa `None` | tratar elemento não renderizado como `0 px`, ou linha de base ausente como aprovação |
| 10 | `error` ≠ `failed` | `PROXIMOS-PASSOS.md §2.2`; `webqa/report.py:157-162` | contar contexto que não abriu como achado. É o teste **não tendo acontecido** |
| 11 | Cor nunca é o único portador de significado | `PROXIMOS-PASSOS.md §2.5`; `report_html.py:380-383` (severidade é **inline e tipográfica**, porque a folha não tem classe para ela) | inventar semáforo para diff visual. E note a simetria: isto é, ao mesmo tempo, **critério que a camada testa no alvo** (WCAG 1.4.1) |
| 12 | Folha de estilo congelada byte a byte | `PROXIMOS-PASSOS.md §2.4`; `tests/test_report_html.py:257-259`; `tests/test_estabilidade_html.py:181-187` reprova classe sem regra na folha | criar classe CSS. Compor com as existentes (`.fora-escopo`, `.chip-neutro`, `.chip-dim`) ou usar estilo inline, como a severidade faz |
| 13 | Métrica nova vai ao JSON; seção nova no HTML é design | `webqa/report.py:222-232` — "acrescentar seção ali é iteração de DESIGN, não de instrumentação" | renderizar tríptico de diff no `summary.html` sem OS de design, `make audita-design` e entrada em `tests/test_derivadores_ligados.py:31-35` |
| 14 | `Finding` só aceita severidade `alta/media/baixa` e fase `A/B/C` | `webqa/dominio.py:76-79` | construir `Finding` na dimensão `gui`. Os checks daqui seguem o padrão de `ux`/`frontend`: assert simples + `metricas.registrar` |
| 15 | Verificação **e** validação no mesmo PR | `PROXIMOS-PASSOS.md §5.2` | entregar check sem unidade em `tests/` sobre dado fabricado |
| 16 | "A garantia existe, a ligação não" | `PROXIMOS-PASSOS.md §2.10`; `tests/test_derivadores_ligados.py` | propor chave de configuração sem teste que prove que **algum check a lê**. Threshold que ninguém lê é exatamente essa classe de defeito |
| 17 | Loopback prova a lógica, nunca a fronteira | `PROXIMOS-PASSOS.md §2.11` | dar por provado, contra o alvo fixture (`127.0.0.1`, isento de etiqueta), qualquer comportamento que dependa de rede pública |
| 18 | C901 máx. 8 e linha 110 na biblioteca | `pyproject.toml:41-51`; `checks/**` tem isenção em `:56` | esconder o algoritmo de geometria dentro do check para escapar do gate. Ele vive em `webqa/`, decomposto — que é também onde ele fica testável sem navegador |
| 19 | axe‑core está pinado com hash | `webqa/axe.py:21-24` (movido para lá na OS‑45; era privado no check) | subir a versão do axe dentro de uma OS desta camada. O SHA‑384 é controle de segurança, não número de versão. Mapear critério→regra só depois de confirmar que a regra existe na 4.9.1 |
| 20 | `mutacao.yml` exige ambiente sem gate | `.github/workflows/mutacao.yml` | depender de variável de gate ligada para o teste passar |

### 2.3 Consequências operacionais — três que custam caro

**a) A dupla dimensão `lgpd` tem preço, e o preço é a sequência do ledger.**

`checks/ux/test_acessibilidade.py:24` declara `[ux, lgpd, browser]` porque no
Brasil acessibilidade em sítio é obrigação legal (LBI, Lei 13.146/2015, Art. 63).
O argumento vale igual para os checks de foco, reflow e contraste desta camada.

Mas o noturno da VPS roda `python -m pytest -m lgpd` (`docker/entrypoint.sh:93`).
Todo check que reivindique `lgpd` **entra no ledger de estabilidade**, e sua
oscilação zera a sequência de dez noites que destrava a LGPD Fase 2 — sequência
que hoje está em 0/10 (`PROXIMOS-PASSOS.md §4.4`).

> **Decisão registrada:** na Fase 1 os checks de `gui` são **só `gui`**. A dupla
> dimensão é reavaliada quando a sequência estiver estável. Herdar o marcador por
> analogia jurídica, sem calcular o efeito no ledger, seria trocar uma linha de
> relatório pelo travamento de uma fase inteira.

**b) Parametrizar muda o nodeid, e o nodeid é o contrato do alvo fixture.**

`conftest.py:107-115` explica que a fixture `browser` **não** é parametrizada
quando há uma engine só, de propósito: assim o nodeid fica `::test_x` e não
`::test_x[chromium]`, "preservando o contrato 1:1 do alvo fixture
(`esperado.json`, §2.8) sem tocá‑lo".

Um check parametrizado por viewport produz `::test_x[mobile]`,
`::test_x[desktop]`… e **cada um** precisa constar de
`fixture_target/esperado.json::devem_falhar`.

> **Decisão registrada:** a iteração de viewport acontece **dentro do corpo do
> teste**, acumulando ofensores e reprovando uma vez, com a lista por viewport na
> mensagem. Um nodeid por check. Parametrização fica reservada aos casos em que
> os vereditos são genuinamente independentes — e aí os ids entram no contrato,
> um a um, na mesma OS.

**c) Mexer no conteúdo do alvo fixture reinicia a sequência do ledger — e existe
uma janela de ouro que está aberta agora.**

`fixture_target/servir.py::identidade()` faz hash de `HOME`, `POLITICA`,
`APP_JS`, `MIME_TROCADO`, `SVG_EXECUTAVEL`, `BUNDLE_JS` e dos cookies. Trocar
qualquer um muda `alvo_sha256`, e a caminhada do ledger reinicia com a nota
"o alvo mudou de identidade".

A consequência operacional é aritmética simples, e ela tem prazo:
**a sequência está hoje em 0/10** (`PROXIMOS-PASSOS.md §4.4`). Zerar zero custa
nada. Zerar 8/10 custa oito noites de espera para destravar a LGPD Fase 2.

> **Decisão registrada:** a OS que acrescenta as violações de GUI ao alvo fixture
> — armadilha de foco, alvo de 16 px, animação infinita, long task no `APP_JS`,
> endpoint que responde 500 — é a **primeira da fila**, e faz tudo de uma vez.
> Não é preferência de ordenação: é o cálculo acima, e ele precisa estar escrito
> na própria OS, senão alguém a adia para a Fase 2 achando que é detalhe e paga
> o preço quando a sequência já estiver correndo.
>
> Onde der, as violações entram como **páginas novas** servidas fora das
> constantes que `identidade()` observa — o mesmo tratamento que as iscas da
> Fase C já recebem (`fixture_target/servir.py`, `ISCAS_FASE_C`). O que não
> couber em página nova (long task precisa estar no `APP_JS` que a home carrega)
> entra junto, na mesma OS, e paga o reinício uma vez só.

---

## 3. Arquitetura proposta

### 3.1 Árvore de diretórios (delta)

```
webqa-suite/
├── config.yaml                    # + chaves PLANAS em thresholds: (§3.3)
├── conftest.py                    # + fixtures: contexto_gui, viewports_gui, axe_js
├── data/
│   └── gui-perfis.yaml            # dados NÃO escalares: viewports, máscaras, mapa WCAG
├── checks/
│   └── gui/                       # dimensão `gui` — sem submarcadores
│       ├── __init__.py
│       ├── test_reflow.py             # 320px, zoom 200%
│       ├── test_foco.py               # visível, ordem, não obscurecido, escape
│       ├── test_alvos.py              # tamanho e espaçamento de alvo de toque
│       ├── test_preferencias.py       # tema escuro, reduced-motion, forced-colors
│       ├── test_interatividade.py     # INP, TBT, long tasks, feedback <1s
│       ├── test_responsividade.py     # matriz viewport × engine, CLS por viewport
│       ├── test_resiliencia.py        # 5xx, timeout, malformado, offline, sem JS
│       ├── test_jornada.py            # TSR, ToT, cliques, becos sem saída
│       ├── test_visual.py             # regressão visual (Fase 2)
│       └── test_interface_segura.py   # CSP forte, autocomplete, PII no DOM
├── webqa/
│   ├── viewports.py               # matriz por env, fail-closed (doutrina de navegador.py)
│   ├── geometria.py               # box, interseção, alvo de toque, obstrução
│   ├── contraste.py               # razão WCAG a partir de cor computada
│   ├── foco.py                    # caminhada de foco: ordem, visibilidade, armadilha
│   ├── vitals_interacao.py        # JS de INP/TBT/long task (irmão de VITALS_JS)
│   ├── rede_simulada.py           # perfis CDP; chromium-only com skip instruído
│   ├── imagem.py                  # PNG -> blocos, diff por bloco (zlib + struct)
│   ├── referencia_visual.py       # ciclo de vida da linha de base
│   ├── jornada.py                 # cronômetro, passos, grafo esperado × real
│   └── evidencias.py              # captura sanitizada + expurgo
├── tests/                         # verificação (marker `verification`) de CADA módulo
└── fixture_target/
    ├── baseline/                  # linha de base VERSIONADA — só do alvo fabricado
    └── paginas_gui/               # páginas que reprovam de propósito
```

### 3.2 Módulos e responsabilidades

A lei é `ARQUITETURA.md:44` e `conftest.py:3-5`: **`checks/gui/` só conhece
fixtures; todo detalhe vive em `webqa/`.** Aqui isso tem uma consequência prática
que vale além da estética — o gate de complexidade `C901 max-complexity = 8`
(`pyproject.toml:46-51`) vale para `webqa/` e é **dispensado** em `checks/**`
(`:56`). Um algoritmo de geometria escrito dentro do check escaparia do gate; o
mesmo algoritmo em `webqa/geometria.py` é obrigado a se decompor — e, decomposto,
fica testável sem navegador, sobre caixas fabricadas.

Todo módulo novo em `webqa/` é **puro**: recebe estrutura de dados (lista de
caixas, par de cores, sequência de paradas de foco) e devolve veredito. O
Playwright fica nas fixtures. É o que permite a verificação em `tests/` rodar
sem Chromium — e, portanto, contar para o piso de cobertura de 78 % do
`quality-gate`.

### 3.3 Contratos de configuração

Três lugares, e a divisão não é arbitrária.

**a) `config.yaml`, bloco `thresholds:` — só NÚMERO, e chave PLANA.**

Duas restrições, e as duas são do código, não de estilo:

- **Plana.** `Settings` é dataclass congelado com `thresholds: dict[str, float]` e
  o acessor `threshold(nome)` (`webqa/config.py:18-33`). Não há acesso aninhado, e
  o override por ambiente só funciona sobre chave plana (`:36-38,45-47`).
  `settings.gui.foco.invisivel_max` seria inventar uma API que não existe.
- **Numérica.** `load_settings` faz `float()` em **toda** chave do bloco
  (`webqa/config.py:45-47`). Logo `gui_alvo_toque_px: 24` funciona, e
  `exigir_skip_link: true` **estoura no carregamento**. A partição é, portanto,
  obrigatória e não opcional:

| Tipo de contrato | Onde vive | Exemplo |
|---|---|---|
| orçamento numérico | `config.yaml::thresholds` | `gui_inp_ms: 200` |
| chave/valor não numérico, lista, mapa | `data/gui-perfis.yaml` | viewports, máscaras, mapa WCAG, vocabulário de erro |
| booleano de política | `data/gui-perfis.yaml` | `exigir_skip_link: true` |
| decisão da execução | variável de ambiente | `WEBQA_VIEWPORTS`, `WEBQA_GUI_SCREENSHOTS` |

Booleano em `thresholds` só caberia como `0`/`1` float — e uma flag disfarçada de
orçamento é a primeira coisa que alguém lê errado. Vai para o YAML de perfis.

```yaml
thresholds:
  # …as existentes…
  gui_alvo_toque_px: 24          # WCAG 2.5.8 AA
  gui_alvo_toque_meta_px: 44     # meta de plataforma — abaixo disto é ALERTA, não achado
  gui_overflow_x_px: 0           # WCAG 1.4.10 a 320 CSS px
  gui_foco_invisivel_max: 0      # WCAG 2.4.7
  gui_foco_obscurecido_max: 0    # WCAG 2.4.11 (nova na 2.2)
  gui_contraste_min: 4.5         # WCAG 1.4.3 texto normal
  gui_contraste_min_grande: 3.0  # WCAG 1.4.3 texto grande
  gui_animacoes_sob_rm_max: 0    # WCAG 2.3.3
  gui_tbt_ms: 200
  gui_inp_ms: 200
  gui_long_tasks_max: 5
  gui_feedback_ms: 1000          # Nielsen H1: resposta perceptível
  gui_lcp_ms_rede_lenta: 4000    # orçamento PRÓPRIO — não é o lcp_ms de fibra
  gui_console_erros_pos_falha_max: 3
  gui_diff_blocos_pct: 0.5
  gui_tot_ms: 15000
  gui_cliques_excedentes_max: 2
```

Cada chave acima precisa, na OS que a introduz, de um teste que prove que **algum
check a lê** — regra 16 do §2.2. Chave órfã é a classe de defeito
"a garantia existe, a ligação não".

**b) `data/gui-perfis.yaml` — dado não escalar, versionado.**

Precedente: `data/caminhos-sensiveis.yaml`, protegido por CODEOWNERS
(`.github/CODEOWNERS`).

```yaml
viewports:
  # `mobile` e `desktop` no PR; a matriz completa no noturno.
  mobile:    {width: 390,  height: 844,  mobile: true, touch: true}
  tablet:    {width: 820,  height: 1180}
  desktop:   {width: 1366, height: 768}
  ultrawide: {width: 2560, height: 1080}
  reflow_aa: {width: 320,  height: 640, mobile: true}   # WCAG 1.4.10

mascaras:
  # Regiões voláteis excluídas do diff visual. Seletor CSS, nunca coordenada:
  # coordenada envelhece a cada mudança de layout e falha em silêncio.
  - "[data-testid=relogio]"
  - ".carrossel"

wcag:
  # Mapa critério -> teste. É o insumo do VPAT/ACR do §6, e existe para que
  # ninguém precise deduzir cobertura a partir de nome de arquivo.
  "1.4.3": [GUI-CONTR-01, GUI-CONTR-02]
  "1.4.4": [GUI-TIPO-01]
  "1.4.10": [GUI-RESP-01]
  "2.3.3": [GUI-MOV-01]
  "2.4.3": [GUI-FOCO-02]
  "2.4.7": [GUI-FOCO-01]
  "2.4.11": [GUI-FOCO-03]
  "2.5.8": [GUI-ALVO-01]
```

**c) Variáveis de ambiente — decisão da EXECUÇÃO, não propriedade do alvo.**

Mesma doutrina de `WEBQA_BROWSER_ENGINES` (`webqa/navegador.py:9-12`):

- `WEBQA_VIEWPORTS` — lista por vírgula; **fail‑closed**, nome desconhecido é
  `ValueError`, nunca filtro silencioso. Um typo no noturno não pode degenerar em
  "rodou zero viewports e passou".
- `WEBQA_GUI_BASELINE_DIR` — onde vive a linha de base de alvo real (§3.4).
- `WEBQA_GUI_SCREENSHOTS=1` — opt‑in explícito para capturar tela de alvo **não
  fabricado**. Desligado por padrão, pelo R19 (§3.5). Fail‑closed como os gates:
  só a string exata `"1"` liga.

### 3.4 Linha de base visual — três vias, e por que não uma

A palavra "baseline" já tem dono neste repositório: `webqa/baseline.py:1-18` é o
ciclo de vida de `Finding` da Fase C (novo / reaberto / persistente /
desaparecido). Aqui se diz **linha de base visual**, e o módulo se chama
`referencia_visual.py`, para ninguém supor que aquele arquivo serve para
screenshot. Ele não serve: é função pura sobre `Finding` + dicionário de YAML.

O que **se reusa** dele é a **semântica**, que é boa e já provada:

| Estado | Significado | Efeito |
|---|---|---|
| novo | página/viewport sem linha de base | **skip explicado** ("rode `make referencia-visual`") — nunca PASS |
| divergente acima da tolerância | mudou e ninguém aprovou | **reprova** |
| divergente abaixo | ruído de renderização | silencia, mas registra a medida |
| desaparecido | a página sumiu do crawl | **não** apaga o arquivo: vira revisão manual |

**Onde cada linha de base mora:**

| Linha de base de | Onde | Versionada? | Por quê |
|---|---|---|---|
| `fixture_target/` | `fixture_target/baseline/<engine>/<pagina>-<viewport>.png` | **sim** | conteúdo fabricado, sem PII, host inexistente, determinístico. É a única que pode. Precedente: `fixture_target/esperado.json` já é contrato versionado |
| perfis e tolerâncias | `data/gui-perfis.yaml` | sim | são números e nomes, não imagem |
| alvo real | `WEBQA_GUI_BASELINE_DIR`, default sob `report/` | **nunca** | R8 + R19. Precedente do volume fora da árvore: `docker/report-campanha/` (`.gitignore:19`), que existe justamente "para a campanha não poder sujar o `git status` da VPS" |

**E a consequência que precisa estar escrita, senão alguém "conserta" versionando
o PNG:** sob `report/`, no CI, a linha de base **expira em 7 dias** junto com o
artefato (`ci.yml`, `retention-days: 7`). Comparação visual de alvo real,
portanto, só existe dentro dessa janela — na prática, comparar uma execução com a
imediatamente anterior. Persistência de verdade exige `WEBQA_GUI_BASELINE_DIR`
apontando para fora da árvore, no disco da VPS, exatamente como
`docker/report-campanha/` faz. Isso é limitação assumida, não defeito a corrigir:
o preço de versionar a alternativa é publicar pixel de alvo real num repositório
público.

**Manifesto de procedência.** Cada linha de base carrega, ao lado,
`manifest.yaml` com engine, revisão do Playwright, viewport, tema e sha do commit
que a aprovou. Sem isso, uma captura de Firefox vira régua de Chromium e o diff
acusa diferença de renderização como regressão do alvo. Divergência de
procedência é **não avaliado**, nunca PASS (regra 9).

**Como o diff é feito, sem dependência nova.** O PNG do Playwright é
não‑entrelaçado; `zlib.decompress` + `struct` (stdlib) dão os bytes. A métrica
primária **não** é pixel a pixel: é a **fração de blocos 16×16** cujo erro médio
por canal ultrapassa um delta. Isso mata o falso positivo de antialiasing e de
sub‑pixel rendering sem SSIM nem LPIPS — que exigiriam `numpy`/`Pillow`, já
rejeitadas com fundamento registrado (`PROXIMOS-PASSOS.md:585`).

O decoder é **fail‑closed**: PNG entrelaçado, paletizado ou com profundidade
diferente de 8 bits levanta erro nomeando o motivo, e o check vira `error` — nunca
`passed`. Decodificar errado em silêncio devolveria uma matriz plausível e um
veredito visual sobre imagem que não existe, que é a pior falha disponível nesta
peça. O aceite completo está em [`GUI-CATALOGO.md §4.1`](GUI-CATALOGO.md).

**E a decisão que sustenta tudo isto:** *o veredito primário da camada é
geometria e CSS computado, não pixel.* Um botão pequeno demais é pequeno em
qualquer fonte; uma cor com contraste 3,1:1 é insuficiente em qualquer
antialiasing. O diff de pixel é o **complemento**, roda contra o alvo fabricado,
com máscara e tolerância declaradas — e por isso não vira o R18 que ele poderia
ser.

### 3.5 Artefatos e integração com o laudo

**Quatro pontos de integração**, e todos precisam sair no mesmo PR do primeiro
check — senão a dimensão existe no `pytest` e não existe no relatório:

1. `pytest.ini`, bloco `markers` — descrição em ASCII sem acento, como as demais;
2. `webqa/report.py::DIMENSIONS` (`:27-30`) — sem isto os resultados agrupam como
   `other`;
3. `webqa/report.py::DIMENSION_NOTES` (`:34-41`) — a nota epistêmica do topo
   deste documento, em uma linha. Quem lê o laudo não leu este contrato;
4. `webqa/report_html.py::OBSERVACOES` (`:90-96`) — a observação do card.

**O que vai para onde:**

| Artefato | Destino | Regra |
|---|---|---|
| veredito por teste | `summary.json::results` + card da dimensão no HTML | caminho normal, nada novo |
| medidas (`gui_inp_ms`, `gui_contraste_pior`, `gui_alvo_menor_px`…) | `summary.json::metricas`, via `metricas.registrar` | ausência é chave ausente, nunca zero |
| **lista de ofensores** (seletor + caixa + valor medido) | mensagem do assert, sanitizada | **é a evidência primária**, e é o que vai para o ticket |
| captura de tela | `report/evidencias/<nodeid>/`, com entrada `evidencias: [...]` no `summary.json` | **do alvo fabricado, sempre. De alvo real, só com `WEBQA_GUI_SCREENSHOTS=1`** — ver abaixo |
| trace / HAR | idem, só sob falha, e só sob o mesmo opt‑in | texto embutido passa por `sanitize_text` + `mascarar_valores_registrados` **antes** de tocar o disco |

**A evidência primária desta camada é texto, não imagem — e isso é decisão, não
acaso.** `webqa/sanitize.py` mascara texto; **não existe mascarador de pixel**, e
supor o contrário é o R19. Por isso a hierarquia da casa ("não coletar > mascarar
> reter pouco") é aplicada no topo:

> **Decisão registrada:** por padrão, contra alvo **real**, a camada `gui`
> **não captura tela**. A evidência é geometria (caixa medida), seletor CSS e
> texto sanitizado — que é o que torna o achado acionável de qualquer modo. A
> captura de pixel é sempre feita contra o `fixture_target` (conteúdo fabricado,
> sem titular), e contra alvo real **apenas** sob `WEBQA_GUI_SCREENSHOTS=1`, com
> aviso de PII no laudo e o expurgo de 7 dias herdado do artefato de CI.
>
> Consequência que as especificações têm de atravessar: onde
> [`GUI-CATALOGO.md §3`](GUI-CATALOGO.md) lista captura como artefato, ela é
> **condicional**. Uma mitigação declarada aqui e não atravessada lá seria
> exatamente a classe de defeito "a garantia existe, a ligação não"
> (`PROXIMOS-PASSOS.md §2.10`) — e a OS que introduzir `webqa/evidencias.py`
> precisa de um teste que prove que, sem a variável, nenhum PNG de alvo não
> fabricado chega ao disco.

**O que NÃO entra agora:** renderizar as evidências no `summary.html`. Isso é
iteração de **design**, não de instrumentação (`webqa/report.py:222-232`), e
exigiria OS própria, `make audita-design` verde e entrada em
`tests/test_derivadores_ligados.py::DERIVADORES_SUMMARY:31-35`. O JSON é livre;
o HTML tem contrato.

**Nota sobre `Finding`.** A dimensão `gui` **não** o constrói: `fase` só aceita
`A/B/C` e `severidade` só `alta/media/baixa` (`webqa/dominio.py:76-79`), e essas
faixas pertencem ao vocabulário de `seguranca`. Os checks daqui reprovam com
assert simples, como `ux` e `frontend` fazem. Consequência aceita: achado de GUI
não aparece na seção de achados numerados nem no SARIF por esse caminho — o §6
descreve o exportador próprio, que lê o `summary.json`.

### 3.6 Isolamento, paralelismo e sanitização

**Contexto novo por variação.** A lição do `network_log` — "cookie ou
consentimento herdado de um teste anterior faria o alvo parecer conforme, o pior
falso negativo possível" (`conftest.py:200-205`) — vale idêntica para
`prefers-color-scheme` e viewport herdados. Toda variação abre
`browser.new_context(...)` e o fecha no `finally`. **Nenhum check de `gui` toca
`browser_page`**, que é de sessão e alimenta as Web Vitals de
`checks/frontend/test_rendering.py`. É o R20.

Preço: um carregamento a mais do alvo por variação. É o mesmo preço que
`ARQUITETURA.md:59` já registra para o `network_log`, e a resposta é a mesma —
medir sem contaminar vale o GET extra.

**Paralelismo: nenhum intra‑alvo, além do que já existe.** O crawler é sequencial
de propósito (`checks/functional/test_links.py:9-16`), e paralelizar variações de
viewport transformaria diagnóstico em rajada contra o mesmo host. Quem paraleliza
é a campanha, por alvo e repetição.

**Timeout e retry.** Os 60 s do `goto` existente. **Retry não entra nos checks**:
oscilação vai para o ledger de `scripts/estabilidade.py`, que é o mecanismo da
casa para separar veredito de flake. Um `@retry` esconderia exatamente o sinal que
o ledger existe para medir.

**Chromium‑only com skip honesto.** Emulação CDP (rede, CPU, memória) não existe
em Firefox e WebKit. Ali o teste **pula com instrução**, nunca passa — a mesma
regra da fixture `browser` para engine sem binário (`conftest.py:180-182`).

### Diferenças por engine — o que já custou caro

Conhecimento de PLATAFORMA, não de um teste: mora aqui porque envelhece devagar e
porque quem tropeçar nele de novo vai procurar no contrato, não numa spec.

**1. O Firefox não devolve o foco ao documento no fim da ordem de tabulação.**

* **Sintoma** — três `error` (não `failed`) em `checks/gui/test_foco.py`, só no
  Firefox, dizendo *"Armadilha de foco: em 200 Tabs o foco nunca voltou ao
  início, girando entre 1 elemento(s)"*. Chromium e WebKit passam pelo mesmo alvo
  sem acusar nada.
* **Causa** — no Chromium, depois do último elemento focável o Tab **dá a volta**
  e o foco reentra no documento. No Firefox/Linux ele vai para a interface do
  navegador (barra de endereços), e `document.activeElement` **congela no último
  focável** e não muda mais. Rastro medido: passos 1–15 percorrem os mesmos 15
  elementos, na mesma ordem, nas duas engines; do 16 ao 200 o Firefox repete o
  último. Não há defeito nenhum no alvo.
* **Por que virou `error` e não `failed`** — o veredito de armadilha mora numa
  *fixture* (`paradas`), e falha de fixture é erro de setup: os três critérios de
  foco nem chegam a rodar naquela engine. Verde não fica, mas medida também não.
* **Discriminador** — sonda `Shift+Tab` no ponto de estagnação, com prioridade,
  mais cobertura do inventário de focáveis (`GUI-CATALOGO.md §3.3`). Fim de
  ordem **solta** o foco; armadilha devolve ao mesmo elemento. A cobertura
  sozinha não basta: com a armadilha no último focável não sobra ninguém por
  visitar e os dois casos ficam idênticos.
* **Onde** — achado pelo run real da matriz na OS‑48 (o gatilho temporário que a
  produziu), consertado na OS‑56.

**2. O Firefox recusa `is_mobile`.** O perfil móvel roda ali como **largura sem
emulação** (`is_mobile`/`has_touch` omitidos), e a nota acompanha o laudo dizendo
o que **não** foi exercido — comportamento de toque. Pular o perfil apagaria da
matriz a combinação "engine alternativa × tela estreita", que é onde a
incompatibilidade de layout mais aparece (`webqa/viewports.py`, OS‑48).

**3. `longtask` e Event Timing só existem no Chromium.** Detectado em runtime por
`PerformanceObserver.supportedEntryTypes`, nunca por lista de engines: lista
envelhece em silêncio e passaria a mentir no dia em que o Firefox implementar
(`webqa/vitals_interacao.py`, OS‑46).

**4. Emulação de rede e de CPU é do CDP, logo Chromium apenas.** O Playwright não
expõe estrangulamento neutro entre engines: `set_offline` liga e desliga, e não há
meio‑termo. Estrangular no cliente (`route` com espera) atrasaria o corpo da
resposta mas não o *handshake*, e portanto não mediria latência — o número sairia
otimista sem nada avisar. A sessão CDP que não abre vira **skip nomeando a
incapacidade**, jamais uma lista de engines escrita à mão
(`webqa/rede_simulada.py`, OS‑50).

**A regra que os quatro compartilham:** capacidade se **pergunta ao navegador**, e
diferença de engine vira skip nomeado ou nota no laudo — nunca um veredito sobre
o alvo.

### Régua sob condição degradada — o que não se compara com o quê

Orçamento de fibra e orçamento de rede lenta são **grandezas diferentes com o
mesmo nome**, e trocá‑los é o erro barato desta camada: cobrar `lcp_ms` (2500 ms)
de uma medida sob 3G reprovaria toda página do mundo, e cobrar
`gui_lcp_ms_rede_lenta` de uma medida de fibra aprovaria qualquer coisa. As
chaves são separadas **mesmo quando o número coincide**, porque o que precisa
poder divergir é o regime, não o valor de hoje — e porque reusar a chave faria
uma edição mover os dois regimes de uma vez, em silêncio.

Isso diverge do precedente do GUI‑RESP‑04, que **reusa** `cls` de propósito, e a
divergência tem critério: CLS é adimensional e independe da condição — o layout
salta ou não salta em qualquer largura. FCP, LCP e TBT são **tempo**, e tempo sob
3G não é a mesma grandeza que tempo sob fibra.

O estrangulamento vive na sessão CDP do par (contexto, página) e **morre com o
contexto** — é o R20 em versão rede. Aplicado à página de sessão, faria
`checks/frontend/test_rendering.py` medir LCP sob 3G sem declarar: o LCP sairia
péssimo, o alvo estaria intacto, e nada ficaria vermelho.

**Sanitização.** Texto passa pela borda de escrita. **Imagem não passa** — e o
documento diz isso em voz alta, porque a alternativa é uma falsa sensação de
cobertura. A mitigação é a hierarquia da casa aplicada no topo: *não coletar >
mascarar*. Captura de alvo real é opt‑in, vive em `report/` (ignorado pelo Git,
expurgo de 7 dias no artefato de CI) e nunca vira linha de base versionada.

---

## 4. Estratégia de execução no CI/CD

### 4.1 Quatro perfis

| Perfil | Onde | O que roda | Determinismo |
|---|---|---|---|
| **PR / commit** | `ci.yml`, job `quality-gate` | verificação da suíte (como hoje) **+ smoke `gui` contra o alvo fixture**: reflow, zoom, foco (3), alvo de toque, contraste, movimento | total — alvo fabricado, loopback, sem rede pública. Flake zero tolerado |
| **Noturno** | `compatibilidade.yml` (05:23 UTC, slot **existente**) | matriz `WEBQA_BROWSER_ENGINES=chromium,firefox,webkit` × `WEBQA_VIEWPORTS` completo; a11y profunda; tema escuro; rede degradada; resiliência; linha de base visual do fixture | alto — ainda contra o fixture |
| **Release candidate** | `workflow_dispatch` + `make campanha` | bateria completa contra alvo real, 3 repetições; comparação de medidas via `webqa/comparador.py`; laudo executivo | médio — alvo externo; instabilidade entre repetições é reportada, não escondida |
| **Sob demanda** | `workflow_dispatch` | zoom 400 %, memória, jornada quantitativa longa, análise por LLM local da jornada já coletada | baixo — saída é triagem humana, nunca veredito |

Os três slots de cron já estão ocupados e coordenados — 03h (noturno da VPS),
04:17 (mutação), 05:23 (compatibilidade). A camada `gui` **estende o slot de
compatibilidade**, que já existe para exatamente isto, em vez de inventar um
quarto horário.

### 4.2 Portões de qualidade

**Reprova (`failed`):** critério WCAG A/AA medido e violado; orçamento de
interação estourado no ambiente oficial; linha de base visual divergente acima da
tolerância; tela branca ou stack trace sob falha de API.

**Informa (`xfail`):** alvo de toque entre 24 e 44 px (atende a norma, não atende
a meta de plataforma); sinal de maturidade ausente sem obrigação legal direta;
orçamento de interação estourado **no CI** e não na VPS.

**Pula com motivo (`skipped`):** linha de base inexistente; engine sem suporte a
CDP; alvo sem tema escuro; alvo sem chamada XHR observável. Nenhum destes vira
aprovação.

**Não aconteceu (`error`):** contexto que não abriu, navegador indisponível. Não
é veredito sobre o alvo, e tem seção própria no laudo.

A distinção CI × VPS merece uma frase própria, porque é onde a tentação mora: em
máquina de CI ruidosa, TBT e INP oscilam. A resposta **não** é afrouxar o
threshold — é declarar que o orçamento vale como veredito no ambiente oficial
(`docs/VPS.md`) e como alerta no CI, com a diferença escrita no laudo. Threshold
afrouxado em silêncio é o R5 se realizando.

### 4.3 Política de nova linha de base

1. Mudança **intencional** de interface atualiza o PNG **no mesmo PR** da mudança.
   O diff aparece no review — que é o ponto: alguém humano olha para a imagem.
2. `make referencia-visual` regrava e carimba o manifesto (engine, revisão do
   Playwright, viewport, tema, sha).
3. Vermelho por mudança intencional não aprovada é **vermelho legítimo**. O
   atalho é regravar, nunca subir `gui_diff_blocos_pct`.
4. Regravação em massa (mais de N arquivos num PR) exige justificativa escrita no
   corpo do PR. Aprovar cem imagens de uma vez é não olhar nenhuma — e é assim
   que uma suíte visual deixa de valer alguma coisa (R18).
5. Linha de base **desaparecida** não é apagada automaticamente. Vira revisão
   manual, exatamente como o achado desaparecido da Fase C.

---

## 5. Limites da automação e protocolo com pessoas

### 5.1 O que a automação não pode decidir

Não é modéstia: cada item abaixo tem uma razão técnica, e ela precisa estar
escrita para que ninguém tente automatizar o inautomatizável e produza um número
que engana.

1. **Satisfação, confiança e carga cognitiva.** Não têm manifestação no DOM.
   SUS, UMUX‑LITE, SEQ e NASA‑TLX são instrumentos com pessoas respondendo;
   qualquer proxy automatizado seria um número inventado com aparência de medida.
2. **Clareza de linguagem.** A camada detecta que *existe* mensagem de erro e que
   ela não vaza `Traceback`. Se ela é compreensível para o público daquele
   produto — se "falha na validação do payload" ajuda alguém — só uma pessoa do
   público responde.
3. **Acessibilidade real com tecnologia assistiva.** O axe cobre parcela dos
   critérios WCAG; o restante é semântico ou contextual. O que a camada pode
   fazer é ler a **árvore de acessibilidade** do Playwright e afirmar
   nome/papel/estado. Isso é **proxy do que um leitor de tela anunciaria**, e
   proxy não é a coisa: NVDA, JAWS e VoiceOver têm comportamentos próprios, e a
   experiência de escuta e navegação por landmark não se deduz da árvore.
4. **Heurísticas de julgamento.** H2 (correspondência com o mundo real), H4
   (consistência com convenções) e H8 (estética e minimalismo) não têm sinal
   objetivo confiável. `RECOMENDACOES.md:16-19` já registrava esse limite; aqui
   ele ganha método.
5. **Adequação ao contexto de uso.** ISO 9241‑11 define usabilidade *para
   usuários específicos, objetivos específicos, contexto específico*. A suíte não
   conhece nenhum dos três.

### 5.2 Protocolo complementar

Executado por release maior, ou quando a camada automatizada acusar regressão
que ela não sabe explicar.

**Participantes.** 5 a 8 por perfil, mínimo dois perfis: (a) pessoa nova no
domínio, (b) pessoa que usa tecnologia assistiva de fato. Cinco participantes por
perfil já revelam a maior parte dos problemas de severidade alta; o que muda com
mais gente é a cauda, não o topo.

**Tarefas.** 4 a 6, espelhando **as mesmas jornadas dos cenários BDD**
(`checks/acceptance/features/`). Essa correspondência é deliberada: TSR e ToT
humanos e sintéticos passam a ser lidos na mesma régua, e a divergência entre eles
vira informação — jornada que o robô completa em 3 s e a pessoa não completa é o
achado mais valioso que este protocolo produz.

**Métricas.** Por tarefa: TSR (concluiu?), ToT (quanto tempo), erros e
recuperações, SEQ (1–7, logo após). Por sessão: SUS ou UMUX‑LITE. Consolidação em
SUM quando houver série. Sessões moderadas, remotas, com gravação **só** mediante
consentimento específico e informado, prazo de retenção declarado e expurgo
executado — a suíte cobra isso dos alvos e não teria como não cumprir.

**Como o achado vira backlog.** Cada achado ganha severidade Nielsen (0–4),
frequência observada (quantos participantes tropeçaram) e a jornada afetada.
Severidade ≥ 3 entra na mesma fila de achados dos automatizados, com o mesmo
ciclo de vida: se não tratado, reaparece e reprova o RC seguinte. O qualitativo
recebendo o tratamento do quantitativo é o que impede o relatório de usabilidade
de virar PDF que ninguém abre.

### 5.3 Como o resultado humano NÃO volta

Achado humano **não** vira threshold. A tentação — "as pessoas acharam lento,
baixa o `gui_inp_ms` para 120" — troca uma observação rica por um número que
perdeu o contexto que o gerava. O que volta para a suíte é **um teste novo**,
quando o achado tem manifestação objetiva ("o botão de confirmar fica abaixo da
dobra em 390 px"), ou **nada**, quando não tem — e nesse caso o achado vive no
backlog de produto, que é onde ele pertence.

---

## 6. Governança e evidência de conformidade

### 6.1 Mapa artefato → norma

| Regime | O que esta camada evidencia | Artefato | O que ela **não** prova |
|---|---|---|---|
| **WCAG 2.2 → VPAT/ACR** | critérios 1.4.1, 1.4.3, 1.4.4, 1.4.10, 2.1.1, 2.3.3, 2.4.1, 2.4.3, 2.4.7, 2.4.11, 2.5.8 com resultado por página, engine e viewport; mapa critério→teste versionado em `data/gui-perfis.yaml` | JSON por critério + SARIF + capturas | cobertura parcial da norma. Critério semântico e de linguagem exige o §5. Um ACR é assinado por humano; isto é **evidência que contribui** para a declaração dele |
| **LGPD / GDPR** | acessibilidade como obrigação legal (LBI Art. 63); PII não exposta na renderização; minimização aplicada à própria evidência (captura opt‑in, expurgo declarado) | `summary.json` + evidências | base legal, contrato com operador e ROPA seguem inobserváveis (`docs/LGPD.md`) |
| **ISO 25010** | usabilidade (operabilidade, proteção contra erro, acessibilidade), eficiência de desempenho percebida, confiabilidade (tolerância a falha de interface), compatibilidade | painel de medidas com série histórica | qualidade **em uso** (satisfação, ausência de risco) só via §5 |
| **ISO 9241‑11** | eficácia (TSR) e eficiência (ToT, cliques excedentes) das jornadas, sintéticas e humanas na mesma régua | série no consolidado da campanha | contexto de uso real |
| **ISO 27001** | evidência contínua de qualidade de CSP, ausência de PII em claro na interface, `autocomplete` correto em campo sensível | SARIF por release + procedência do laudo | evidência técnica pontual; não substitui SGSI |
| **ISO 42001** | para o item exploratório: LLM **local**, gate explícito, "a LLM apresenta, o código julga", detector de omissão sobre a saída (`docs/LLM.md`) | log de triagem + o próprio contrato de `webqa/llm.py` | o exploratório nunca emite veredito, por desenho |

### 6.2 Formatos

- **JSON** (`summary.json`) — máquina, ingestão por GRC. Já existe.
- **SARIF** — a aba Security do GitHub. `webqa/sarif.py` hoje serializa `Finding`,
  e a dimensão `gui` não constrói `Finding` (§3.5). O exportador de GUI é função
  nova e **pura**, lendo o `summary.json` e emitindo `ruleId` = ID do catálogo,
  `level` derivado do estado. Sem tocar o exportador existente.
- **HTML de arquivo único** — o laudo atual, sem requisição externa, com tema
  escuro e `@media print`. Já existe.
- **PDF executivo por release** — gerado do `summary.html` por `page.pdf()` do
  Chromium já instalado. **Zero dependência nova**, e a nota epistêmica vai na
  capa, não no rodapé.
- **Manifesto de linhas de base** — trilha de auditoria de quem aprovou qual
  aparência, quando e com qual navegador.

### 6.3 O que a evidência não prova

Esta seção existe pelo mesmo motivo que `DIMENSION_NOTES` existe: quem lê o
artefato não leu o contrato. Um pacote de evidências desta camada, por completo
que seja, sustenta a frase *"os critérios automatizáveis X, Y e Z foram medidos
em tais páginas, engines e viewports, com estes resultados"*. Ele **não** sustenta
*"o produto é acessível"* nem *"o produto é usável"*. A primeira frase é
verificável; a segunda é uma declaração de conformidade que uma pessoa assina, com
o §5 no meio. Reportar a segunda a partir dos artefatos da primeira é o R21.

---

## 7. Riscos que esta camada introduz

Registrados na matriz de `docs/RISCOS.md` — aqui só o índice, para não duplicar
o que envelhece em dois lugares:

- **R18** — linha de base visual instável (fonte, antialiasing, revisão do
  navegador) reprovando alvo conforme, e treinando a equipe a aprovar imagem sem
  olhar.
- **R19** — captura de tela de alvo real com PII em pixel, que `sanitize_text`
  não alcança.
- **R20** — check de GUI alterando viewport ou tema no `browser_page` de sessão e
  contaminando as Web Vitals das demais dimensões.
- **R21** — laudo de GUI lido como certificado de usabilidade.

---

## 8. Roadmap em três fases

Resumo. O backlog executável, com critérios de aceite e dependências, está em
[`handoff/ordens-de-servico/OS-gui-fila.md`](handoff/ordens-de-servico/OS-gui-fila.md).

**Fase 1 — fundação e geometria (OS‑40 a OS‑44).** Começa pelo alvo fixture, e a
ordem não é arbitrária: é o cálculo do §2.3c. Depois, os quatro pontos de
integração do §3.5, as fixtures de contexto isolado, `webqa/geometria.py`,
`webqa/foco.py`, `webqa/viewports.py`, e os sete primeiros checks — reflow, zoom,
os três de foco, alvo de toque e movimento. Todos passivos, determinísticos e
exercitáveis contra o alvo fabricado. Ao final, o smoke entra no `quality-gate`,
com prova por violação plantada.

**Fase 2 — variação e adversidade (OS‑45 a OS‑49).** Contraste em tema escuro,
INP/TBT/long tasks, resiliência a falha de API, matriz viewport × engine no
noturno, e as evidências mais a linha de base visual contra o fixture.

**Fase 3 — maturidade (OS‑50 a OS‑55).** Rede degradada e CPU limitada, jornada
quantitativa com TSR/ToT nos mesmos cenários BDD que o protocolo humano usa,
i18n/RTL e zoom 400 %, evidência de conformidade (exportador SARIF de GUI, PDF
executivo, VPAT parcial), protocolo humano piloto, e a análise por LLM local
**da jornada já coletada** — nunca a LLM agindo contra o alvo, que
`tests/test_convencoes.py:209-224` proíbe com fundamento.
