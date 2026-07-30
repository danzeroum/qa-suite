# Brief de Design — WebQA Suite: Relatório de Qualidade & Painéis

**De:** CEO/Arquitetura da suíte · **Para:** Design
**Repositório de referência:** https://github.com/danzeroum/qa-suite
**Prioridade:** Relatório (P0) → Painel de Estabilidade (P1) → Inventário de Terceiros (P1) → Identidade mínima (P2)

---

## 1. O produto, em um parágrafo

A WebQA Suite é uma ferramenta open-source em Python que audita **qualquer aplicação web** de fora para dentro (caixa-preta): performance de backend, qualidade de frontend, UX/acessibilidade, funcionalidades e — a dimensão mais sensível — **conformidade LGPD observável** (rastreadores antes do consentimento, dados pessoais em URLs, política de privacidade, cookies com prazo excessivo). Ela roda no terminal e em CI; **tudo que um humano vê dela são os artefatos HTML/JSON que você vai desenhar**. Hoje o `summary.html` é um HTML utilitário gerado por código, sem projeto de design. Este brief muda isso.

## 2. O que será desenhado (escopo)

1. **`summary.html` — o Relatório de Qualidade** (P0). Documento único, estático, gerado a cada execução. É o entregável que um engenheiro anexa num ticket, um DPO lê numa auditoria e um gestor abre de um link de CI.
2. **Painel de Estabilidade** (P1). Visualização do "caderno de bordo" (`docs/lgpd-estabilidade.json`): a sequência de noites limpas rumo a 10/10 que destrava a Fase 2 de testes.
3. **Inventário de Terceiros** (P1). Seção/página a partir de `report/terceiros.json`: quem recebe dados dos visitantes do site auditado — insumo direto para ROPA/DPA de um DPO.
4. **Identidade mínima** (P2). Marca simples (wordmark + ícone), paleta e tipografia documentadas — o suficiente para relatório, README e futura página do projeto falarem a mesma língua. Não é um projeto de branding completo.

## 3. Públicos e cenários reais de uso

- **Engenheiro/dev (uso diário):** acabou de rodar a suíte, quer em segundos saber *o que falhou e por quê*, copiar a mensagem de erro e ir corrigir. Lê no desktop, muitas vezes em tema escuro, às vezes via link de artefato de CI.
- **DPO/jurídico (uso quinzenal):** precisa do panorama LGPD e do inventário de terceiros para trabalhar conformidade. Não lê stacktrace; lê "o site dispara Google Analytics antes do consentimento (Art. 8º §4)". Provável que **imprima ou exporte PDF**.
- **Gestor/CEO (uso mensal):** quer a fotografia: quantas dimensões saudáveis, tendência, e o estado da sequência de estabilidade. 30 segundos de atenção.
- **Cliente do auditor (eventual):** o relatório pode ser encaminhado a quem contratou a auditoria — precisa parecer profissional e autoexplicativo sem ninguém ao lado apresentando.

O mesmo documento serve aos quatro. A hierarquia visual precisa fazer a triagem: fotografia primeiro, dimensões depois, detalhe técnico por último (progressive disclosure).

## 4. Dados disponíveis (fonte da verdade — nada além disso existe)

O design consome três JSONs. Não inventar métricas que eles não têm.

**`summary.json`** (por execução):
- `generated_at` (data/hora), `duration_s` (duração total)
- `by_dimension`: contagem de `passed / failed / skipped` por dimensão
- `results[]`: cada teste com `test` (id técnico, ex.: `checks/lgpd/test_consentimento.py::test_sem_trackers_antes_do_consentimento`), `dimension`, `outcome`, `duration_s`, `detail` (mensagem de falha/skip, já sanitizada — nunca contém dado pessoal), `browser` (bool)
- `DIMENSION_NOTES`: notas fixas por dimensão (ver §7, honestidade epistêmica)

**`terceiros.json`:** lista de hosts de terceiros contactados no carregamento, com nº de requisições e tipos de recurso (script, imagem, xhr...). Sem paths, sem query strings — por política de privacidade da própria suíte.

**`lgpd-estabilidade.json`** (o ledger): entradas `{generated_at, alvo_sha256, browser_total, infra_flakes, streak, origem}`. `origem` ∈ `vps | ci | local`; **só `vps` conta para a sequência**; a meta é `streak = 10`.

As **7 dimensões**: `backend`, `frontend`, `ux`, `functional`, `acceptance`, `lgpd`, `verification` (+ `load`, raro). Alguns testes pertencem a duas (ex.: acessibilidade = `ux` + `lgpd`, por força da LBI); no agrupamento aparecem uma vez, mas o design pode sinalizar a dupla pertença.

## 5. Semântica de estados — o coração do design

Há **quatro estados**, não dois, e o erro clássico é achatar tudo em verde/vermelho:

| Estado | Significado real | Direção visual |
|---|---|---|
| `passed` | Conforme no que é observável | Positivo, mas discreto — passar é o esperado, não uma festa |
| `failed` | **Prova de não conformidade** — achado real, acionável | Máximo destaque; é o conteúdo mais valioso do relatório |
| `xfail` | Alerta informativo: sinal de maturidade ausente, sem obrigação legal direta (ex.: sem `security.txt`) | Terceira cor clara — **não pode parecer nem falha nem sucesso** |
| `skipped` | Não aplicável ou ambiente sem recurso (ex.: página sem formulários; Chromium ausente) | Neutro, apagado, mas com o motivo sempre legível |

Regras duras: (a) **cor nunca é o único canal** — todo estado tem ícone/rótulo textual (daltonismo, impressão P&B); (b) `xfail` não entra na conta de "falhas" em nenhum número agregado; (c) a mensagem de `detail` de uma falha é o item mais importante da linha — as mensagens foram escritas para ensinar ("CLS 0.31 — a página 'pula' durante o carregamento (meta: 0.1)") e merecem tipografia de leitura, não fonte mono espremida.

No **painel de estabilidade**, a distinção paralela: *flake de infraestrutura* (equipamento falhou → zera a sequência) ≠ *falha determinística* (o site auditado reprovou → a sequência **avança**). O design precisa tornar essa distinção óbvia, porque ela é contraintuitiva: barras vermelhas de conformidade convivendo com uma sequência verde de estabilidade é o estado normal e saudável do sistema.

## 6. Arquitetura de informação do relatório (P0)

Ordem de leitura proposta (desafie se tiver razão melhor, mas justifique):

1. **Cabeçalho-fotografia:** identidade, alvo auditado (pode ser hash/apelido — nunca exibir URL com query), data/hora, duração, veredito agregado por dimensão em cards ou faixa compacta.
2. **Dimensão LGPD** ganha tratamento próprio dentro da grade — é a razão de muitos leitores abrirem o documento — **sempre acompanhada da nota epistêmica (§7)**.
3. **Achados (failed) em primeiro plano:** lista priorizada, agrupável por dimensão, cada item com id do teste, mensagem `detail` completa e, quando houver no texto, a referência legal (Art. 8º, Art. 46...) destacável.
4. **Alertas (xfail)** em bloco próprio, visualmente subordinado aos achados.
5. **Tabela completa** (todos os resultados, incluindo passed/skipped) em acordeão/detalhe expansível — presente, mas fora do caminho.
6. **Rodapé técnico:** versão da suíte, comando executado, link do projeto.

Estados vazios importam: execução 100% verde (o relatório não pode parecer quebrado — "nenhuma não conformidade observável encontrada" é um resultado que o cliente emoldura), execução só de verificação (sem alvo), execução sem navegador (metade dos testes skipped — explicar em uma linha o porquê e o comando que resolve).

## 7. Tom e honestidade epistêmica (inegociável)

A suíte tem uma ética explícita e o design é parte dela:

- **A nota epistêmica é elemento de primeira classe, não letra miúda:** *"Falha PROVA não conformidade; passar NÃO certifica conformidade — base legal, contratos com operadores e governança interna não são observáveis por HTTP."* Ela precisa estar visualmente ligada à dimensão LGPD e sobreviver à impressão. É proibido qualquer selo, badge ou linguagem visual que insinue "certificado LGPD" ou "aprovado".
- **Sem gamificação enganosa:** a sequência 10/10 pode (deve) ser satisfatória de acompanhar, mas sem troféus, confetes ou dopamina barata — o público é técnico/jurídico e o assunto é conformidade legal.
- **Falha não é vergonha:** o relatório existe para encontrar problemas; o tom visual dos achados é "aqui está o que corrigir", não alarme catastrófico. Nada de caveiras, vermelho-sangue em tela cheia ou linguagem de pânico.
- Voz dos microtextos: português claro, direto, tecnicamente preciso, sem jargão de marketing. Os textos das mensagens vêm do código e não podem ser reescritos pelo design — o design os *apresenta*.

## 8. Restrições técnicas (dogfooding: o relatório passa na própria bateria)

Esta é a restrição que torna o projeto interessante — **o `summary.html` será auditado pela própria suíte**, então o design entrega já conforme:

- **Arquivo único e estático:** um `.html` com CSS embutido. **Zero requisições externas** — sem Google Fonts, sem CDN de ícones, sem analytics (a suíte que caça trackers não pode ter tracker). Tipografia via *system font stack* ou, no máximo, uma fonte em `@font-face`/base64 se o ganho justificar o peso.
- **Orçamento de peso:** o HTML final gerado deve ficar confortavelmente abaixo de 300 KB (limite que a suíte impõe aos auditados).
- **Acessibilidade WCAG sem violações críticas/sérias (axe):** contraste AA no mínimo, `lang="pt-BR"`, um único `h1`, hierarquia de headings sem saltos, HTML semântico (`main`, `nav`, `header`, `footer`, `section`), imagens/ícones com `alt` ou `aria-hidden`, foco visível, navegável por teclado.
- **Sem JavaScript obrigatório:** interações (expandir/recolher, filtros por dimensão) devem funcionar com HTML/CSS (`<details>`, `:target`) ou degradar perfeitamente sem JS. O documento precisa ser íntegro impresso em papel.
- **Impressão/PDF é cenário de primeira classe** para o público DPO: prever folha de estilo de impressão.
- **Dark mode** via `prefers-color-scheme` é desejável (público dev), desde que os quatro estados permaneçam distinguíveis nos dois temas.
- O template será implementado como string Python que interpola dados — evitar construções que dependam de build de frontend. Layout com CSS moderno (grid/flex) sem frameworks.

## 9. Painel de Estabilidade (P1) — conteúdo

Um leigo recebeu esta explicação do sistema: *"toda noite um robô inspeciona um site de teste cheio de erros conhecidos; um auditor confere se o equipamento funcionou; dez noites limpas seguidas liberam a próxima fase"*. O painel deve contar exatamente essa história para quem chega sem contexto: progresso atual (`N/10`), linha do tempo das últimas noites (limpa / flake / origem não-oficial), o que zera e o que não zera (uma frase), origem de cada entrada (`vps` conta; `ci`/`local` aparecem como informativas, visualmente rebaixadas) e o marco: o que acontece ao chegar em 10 ("Fase 2 destravada").

## 10. Inventário de Terceiros (P1) — conteúdo

Tabela/cartões: host, nº de requisições, tipos de recurso, e uma marcação para hosts que constam da lista de rastreadores conhecidos vs. terceiros neutros (CDN próprio, etc.). Título honesto: "Quem recebeu requisições do navegador ao carregar a página" — sem acusar, sem absolver. É material de trabalho de DPO: precisa copiar/colar bem e imprimir melhor.

## 11. Entregáveis do designer

1. **Direção visual** (1 página): conceito, paleta com tokens nomeados (incl. os 4 estados nos 2 temas, com pares de contraste verificados), tipografia com escala, e o racional — espera-se **um ponto de vista**, não um tema de dashboard genérico.
2. **Layout de alta fidelidade do relatório**: desktop (~1200px), leitura móvel (~380px) e versão impressa, cobrindo os estados: execução com achados; 100% verde; sem navegador (skips em massa); execução parcial (1 dimensão só).
3. **Painel de estabilidade e inventário de terceiros** em alta fidelidade (podem ser seções do mesmo documento ou páginas irmãs — proposta sua).
4. **Wordmark/ícone** simples + regras mínimas de uso.
5. **Especificação para dev**: tokens em CSS custom properties, espaçamentos, e os componentes anotados (card de dimensão, linha de resultado, bloco de nota epistêmica, timeline do ledger). Entrega ideal: um HTML estático de referência dos componentes — vira quase diretamente o template Python.

**Formatos:** Figma (ou equivalente com inspeção) + export PDF; o HTML de referência se topar o item 5 ideal.

## 12. Critérios de aceite do design

- Os 4 estados distinguíveis sem cor (P&B/daltonismo) nos dois temas.
- Nota epistêmica presente, legível e visualmente vinculada à dimensão LGPD em todas as variações, inclusive impressa.
- Um engenheiro encontra o primeiro `failed` e sua mensagem completa em ≤ 5 segundos a partir da abertura.
- Um leigo entende o painel de estabilidade sem explicação oral (teste com alguém de fora).
- O HTML de referência (ou o layout, se aferível) passa em: axe sem críticas/sérias, `h1` único, headings sem saltos, zero requisição externa, contraste AA.
- Nenhum elemento visual sugere certificação, selo ou aprovação legal.

## 13. Fora de escopo

Website/landing do projeto, design da CLI/terminal, e-mails, apresentações, dashboards históricos multi-execução (o dado é por execução; tendências são fase futura), e qualquer feature que exija backend/JS obrigatório.

## 14. Referências no repositório

- `webqa/report.py` — gerador atual do HTML (o "antes") e os campos reais
- `docs/LGPD.md` e `docs/RISCOS.md` — a ética do produto, critérios FAIL/xfail, a emenda da sequência
- `config.yaml` — os orçamentos de qualidade que o relatório exibe
- `fixture_target/` — alvo de teste não conforme: rodar a suíte contra ele gera um `summary.json` realista e cheio de achados para popular os layouts (pedir ao time um export, ou gerar com `pytest -m lgpd` apontando para o fixture)

**Dúvidas e propostas de mudança de escopo:** direto comigo (CEO/Arquitetura). Divergências bem argumentadas contra este brief são bem-vindas — inclusive sobre a ordem de leitura do §6.
