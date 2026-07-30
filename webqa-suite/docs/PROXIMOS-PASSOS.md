# Continuidade — o que existe, o que falta, e as regras que não estão no código

Documento de passagem para quem assume o projeto. Não repete o que os outros
docs já explicam: aponta para eles, diz **onde o trabalho parou** e registra as
decisões que um leitor do código sozinho não teria como deduzir.

Base deste documento: `main` em `3272077` (pós OS-23 e OS-27).

A verificação da própria suíte tem hoje **607 testes coletados**; num ambiente
limpo o resultado é **604 passed / 3 skipped**. Os 3 skips são de
`tests/test_report_dogfooding.py`, que exige uma execução real de `make campanha`
para ter o que auditar — o número de coleta e o de aprovação só coincidem depois
dela. Confundir os dois faz ambiente saudável parecer defeituoso.

Os valores acima envelhecem a cada OS que acrescenta teste. Quem for citá-los
recalcula em vez de copiar:

```bash
pytest -m verification tests --collect-only -q | tail -1   # coletados
make verify                                                # passed / skipped
```

---

## 1. O que ler primeiro, nesta ordem

Esta é a **entrada única**: se um documento do projeto não está listado abaixo,
ele não precisa ser lido antes de começar.

| # | Doc | Responde |
|---|---|---|
| 0 | **este documento** | onde o trabalho parou e as regras que o código não explica |
| 1 | [`README.md`](../README.md) | como rodar, níveis de teste, rastreabilidade |
| 2 | [`ARQUITETURA.md`](ARQUITETURA.md) | camadas: `checks/` só conhece fixtures, detalhe vive em `webqa/` |
| 3 | [`RISCOS.md`](RISCOS.md) | riscos numerados (R7, R8… citados em código e commits) |
| 4 | [`ESCOPO-EAP.md`](ESCOPO-EAP.md) | o que está dentro e **fora** do escopo; EAP alinhada às pastas |
| 5 | [`LGPD.md`](LGPD.md) | dimensão de privacidade, ledger, critério de saída da Fase 1 |
| 6 | [`SEGURANCA.md`](SEGURANCA.md) | dimensão de segurança em 3 fases, DDD, veredito sobre pareceres |
| 7 | [`CAMPANHA.md`](CAMPANHA.md) | nível sistema da própria suíte contra alvos reais |
| 8 | [`VPS.md`](VPS.md) | ambiente oficial da métrica, cron, smoke |
| 9 | [`design-audit.md`](design-audit.md) + `docs/qa-suite design brief/referencia/` | laudo do pacote de design e o contrato visual navegável |

`RISCOS.md` e `ESCOPO-EAP.md` subiram para o começo: os riscos são citados por
número (R7, R8…) em comentários de código e mensagens de commit, e ler esses
números depois dos docs de dimensão obriga a voltar atrás.

Consulta, não leitura de entrada:

| Doc | Quando abrir |
|---|---|
| [`LLM.md`](LLM.md) | contrato da camada de sumário por LLM local — leia antes de tocar em `webqa/llm.py` |
| [`PLANO-TESTE-alvo-autenticado.md`](PLANO-TESTE-alvo-autenticado.md) | roteiro de campanha contra alvo com Basic Auth, na VPS — 6 fases, com a verificação de vazamento como gate |
| [`TELEMETRIA.md`](TELEMETRIA.md) | o que a telemetria coleta, sobre quê, e as duas linhas que ela não cruza |
| [`RECOMENDACOES.md`](RECOMENDACOES.md) | rastrear uma prática de engenharia até onde ela é coberta |
| [`dimensao-seguranca-consolidado.md`](dimensao-seguranca-consolidado.md) | histórico da consolidação da dimensão `seguranca` |
| [`handoff/`](handoff/) | material da passagem original (brief de design, ordens de serviço abertas) |

**Antes de abrir código, rode `make verify` e `make fixture`.** Ver a suíte
funcionando e o alvo fabricado reprovando de propósito muda a leitura dos checks:
sem isso, as docstrings parecem abstratas.

Depois disso, leia **um** check de cada dimensão. Eles seguem o mesmo formato:
docstring dizendo *por que o teste existe e o que a falha prova*, não o que o
código faz.

---

## 2. Regras da casa que o código não explica sozinho

Estas foram decididas ao longo do projeto e custaram caro. Violá-las por
desconhecimento é o risco mais provável de quem chega agora.

### 2.1 Ausência nunca vira zero, e não avaliado nunca vira PASS

Métrica que o navegador não emitiu **não** é `0 ms`; corpo acima do teto **não**
é "sem segredo"; alvo não medido **não** é alvo conforme. Zero num relatório de
performance é elogio, e elogiar por falta de dado é o pior erro que estes
documentos podem cometer.

Onde isso está encarnado: `webqa/metricas.py::registrar`, `dominio.Corpo.avaliavel`,
`campanha.resumo`, e os `xfail` de "não avaliado" nos checks de `seguranca`.

### 2.2 `error` não é `failed`

Falha **fora** do corpo do teste (fixture, navegador, rede) é o teste **não ter
acontecido** — não é veredito sobre o alvo. Não soma em achados, não ganha cor
de estado, e tem seção própria no relatório.

Isso nasceu de um defeito real: erros de setup sumiam do `summary.json`, e uma
noite com o Chromium inalcançável era classificada como **limpa** pelo ledger —
a métrica de confiança inflava exatamente quando a infraestrutura quebrava.

### 2.3 Bump obrigatório de `CLASSIFICADOR_VERSAO`

Todo PR que mude **como** uma execução é julgada (regex de infra, critério de
`limpa`, o que conta como teste de navegador) precisa incrementar
`CLASSIFICADOR_VERSAO` em `scripts/estabilidade.py`. Entradas de versão com
defeito conhecido entram em quarentena: **não contam, não zeram, não são
apagadas**. Ver `LGPD.md §versão do classificador`.

### 2.4 A folha de estilo é congelada byte a byte

`webqa/report_style.py::ESTILO_CANONICO` é cópia literal do bloco `<style>` da
referência (15.515 B, idêntico nos seis arquivos do designer). **Divergência é
regressão, não melhoria.** Há teste fixando a igualdade.

Consequência prática: quando o design precisa de algo que a folha não tem
(rótulo de severidade, seção de erros de infra), **componha com as classes
existentes** (`.fora-escopo`, `.chip-neutro`) ou use o estilo inline que a
referência usa — nunca invente classe nem token de cor.

### 2.5 Cor nunca é o único portador de significado

Quatro estados, cada um com **forma + rótulo textual**. Severidade é
**tipográfica**. Um segundo semáforo dentro de `failed` some na impressão em
preto e branco, que é justamente quando o laudo circula.

### 2.6 `sanitize.py` é a borda de escrita

Tudo que a suíte persiste passa por `sanitize_text` — mensagem de falha, motivo
de skip, erro de console. PII **e** credenciais. As expressões que detectam são
as que mascaram: ponto único de verdade.

E a invariante mais dura do projeto: **é impossível instanciar um `Finding` com
segredo em claro** — a sanitização acontece no construtor. Não é regra que cada
check lembra de seguir; é impossibilidade estrutural.

### 2.7 Passivo × ativo é fronteira ética, não técnica

Analisar o que o navegador já baixou é passivo. Sondar caminho que o servidor
não ofereceu (`/.git/`, `.env`, um `.map`) é **intrusão sem autorização** e exige
`WEBQA_ACTIVE_PROBES_AUTHORIZED=1`. Há teste que lê o código-fonte dos checks da
Fase B e reprova se aparecer `httpx`, `urlopen` ou `page.goto`.

### 2.8 O contrato do alvo fixture é 1:1

`fixture_target/esperado.json` lista os FAILs que a suíte **deve** produzir
contra o alvo fabricado — hoje **11**, mais **6** exclusões com motivo escrito.
Nem a mais (reprovaria alvo conforme) nem a menos (check que parou de detectar).

Quando uma regra **não pode** ser exercida pelo fixture, ela vai para
`fora_do_contrato` **com o motivo** e ganha teste de unidade. Fingir que o
fixture a exercita dá confiança falsa justamente na regra mais fácil de errar.

### 2.9 `report/` nunca é versionado

Artefato de execução carrega host e trecho de erro do alvo (Risco R8). Vale para
`report/`, `report/campanha/` e `docker/report-campanha/`.

### 2.10 Prosa × código: quando discordam, desconfie do código

O docstring dizia "função auxiliar" e o pytest coletou como teste. O comentário
dizia "folga de 20%" e a saída imprimiu **19%**. O doc dizia "remove
identificação de alvo" e o campo `origens` levava o host no caminho do arquivo.

Três vezes o mesmo padrão, e nas três **a prosa estava certa**. Não é coincidência:
a prosa é escrita com a intenção à vista, o código é escrito com a implementação
à vista — e é a implementação que erra em silêncio, porque ninguém relê uma
f-string no meio de uma lista.

Consequência prática, em duas regras:

1. **Quando o texto e o comportamento divergirem, comece corrigindo o código.**
   Ajustar a prosa para casar com o bug é a saída rápida e apaga a única
   evidência de que havia bug.
2. **Escrever a documentação é um detector.** As três armadilhas acima
   apareceram enquanto alguém redigia — não enquanto depurava. Foi assim também
   com o `.gitignore` inexistente, com o `IGNORECASE` que transformava toda
   falha em falso flake, e com as quatro colisões de numeração de OS, que só
   ficaram visíveis quando a tabela do registro foi escrita. Documentar não é
   cerimônia aqui; é o momento em que a intenção e o código são confrontados.

As três estão fixadas em `tests/test_convencoes.py` e `tests/test_telemetria.py`
— reintroduzir qualquer uma reprova a suíte. Antes da OS-32 elas viviam só em
comentário, e comentário não reprova ninguém.

#### A extensão: teste × coisa testada

O padrão reincidiu **na própria OS que o registrou**. Na OS-33, `motivos_do_zero`
tinha testes de derivação verdes enquanto o bloco **não estava interpolado** no
template: a função calculava certo, os testes conferiam o retorno, e a página
saía sem os três motivos. Suíte verde sobre função morta.

É a mesma forma do D6, em que o `quality-gate` ficava verde sem exercer o
contrato do alvo: **a garantia existia, a ligação não.**

> **Teste que só exercita a derivação é verde sobre função morta.** Todo
> derivador de conteúdo para página gerada precisa de um par: um teste do
> **retorno** (verificação) e um que renderiza a página inteira e procura o
> texto no HTML final (validação).

`tests/test_derivadores_ligados.py` faz isso mecanicamente para os dois
geradores: substitui cada derivador por uma sentinela e exige que ela apareça na
página. A lista de derivadores é **explícita** de propósito — extraí-la do
template faria a cobertura encolher junto com a interpolação removida, fechando
o furo no papel e deixando-o aberto na página.

Um cuidado que decorre disso: **vazio legítimo e não-interpolado são
indistinguíveis no HTML.** `_bloco_do_zero` devolve `""` quando a sequência está
viva, e `_achados` devolve seção vazia num laudo verde — os dois casos produzem
a mesma ausência de texto que uma interpolação apagada produziria. A sentinela é
o que separa os dois, e há teste para cada um.

#### A classe: "a garantia existe, a ligação não"

Três instâncias, e a assinatura é sempre a mesma — **um teste afirma algo sobre
uma peça sem atravessar o caminho que a usa de verdade:**

| Instância | A garantia | A ligação que faltava |
|---|---|---|
| **D6** | `quality-gate` verde a cada push | sem Chromium, os 4 testes do contrato **pulavam**; o job aprovava sem exercer o R7 que existe para cobrir |
| **#31 / OS-33** | `motivos_do_zero` testado e correto | o bloco **não estava interpolado**; a página saía sem os três motivos |
| **#35 / OS-35** | "`--painel` não escreve no ledger" | conferido por **md5 depois da execução** — nada dizia da próxima linha que alguém acrescentasse |

**Heurística de detecção**, para achar a quarta antes que ela morda:

> Pergunte de cada garantia: *o teste percorre o caminho real, ou só a peça?*
> Se ele monta a peça à mão, chama a função direto ou confere o resultado
> depois, a ligação está fora da cobertura. Suspeite especialmente quando o
> teste **confirma um estado** ("o arquivo não mudou", "o job ficou verde") em
> vez de **exercer um caminho**.

O remédio tem uma ordem de preferência, do mais forte ao mais fraco:

1. **impossibilidade estrutural** — o `Finding` sanitiza no construtor, e não há
   outro jeito de existir um. Só serve quando há ponto único de estrangulamento;
2. **fronteira no fonte** — teste que lê o código do caminho e reprova o que não
   pode aparecer (a Fase B sem `httpx`, o painel sem escrita);
3. **prova por tentativa** — armadilha que explode no ato, em vez de conferir
   depois;
4. **conferência de estado** — o mais fraco. Vale como complemento, nunca sozinho.

Em `--painel` as três últimas foram usadas juntas, porque a primeira não cabia:
**Python não tem ponto único de estrangulamento para escrita em arquivo**. Dizer
isso em vez de prometer "impossível" é parte da regra — garantia superestimada é
irmã da métrica que infla.

Detalhe do ambiente que mudou o desenho do teste e vale para quem escrever o
próximo: **este container roda como root, e `chmod 0444` não impede escrita
nenhuma.** Um teste que só conferisse permissão daria garantia falsa — a própria
classe de defeito, dentro do PR que a fecha. A armadilha de escrita é
independente de permissão por isso.

Uma nota sobre a primeira: o pytest coleta por `test*`, **não** por `test_*`.
`testes_lentos` e `testar_alvo` entram na coleta, e em código português esse
prefixo aparece sem querer. A guarda checa o prefixo que o pytest usa de fato.

---

## 3. Onde o trabalho parou

### 3.1 Pronto e mergeado

- **LGPD Fase 1** — seis pacotes passivos (consentimento, PII em trânsito,
  transparência, terceiros, retenção observável, acréscimos regulatórios).
- **`seguranca` Fases A e B** — 13 checks passivos sobre a `network_log`
  enriquecida; value objects `Finding`/`Recurso`.
- **Relatório** — `summary.json` + `summary.html` conforme o pacote de design
  liberado, com estado `error`, faixa de métricas e severidade/fase.
- **Campanha** — nível sistema contra alvos reais, consolidado com mediana e
  pior caso, instabilidade entre repetições.
- **Ledger de estabilidade** — com quarentena por versão de classificador.
- **Runtime VPS** — `docker compose` com os serviços `estabilidade` (tem a
  caneta) e `campanha` (não tem).
- **CI** — `quality-gate` em todo push/PR; validação contra alvo real é manual.

### 3.2 Bloqueado por ambiente, não por código

Nada disto pôde ser exercido no ambiente de desenvolvimento usado até aqui.
**Confirme cada um na VPS antes de confiar no que está escrito:**

1. **Primeiro `docker compose build`** — a imagem nunca foi construída de fato
   (não havia daemon Docker na sessão). O entrypoint foi validado contra um
   remoto git local, cobrindo segredo ausente, caminho feliz, non-fast-forward
   com rebase, dedup no mesmo dia e timeout de readiness.
2. **`make vps-smoke`** — passos 1 e 3 rodaram para valer; 2, 4 e 5 foram
   exercitados com um `docker` stubado.
3. **`make campanha-vps`** — o aceite da OS-19 (FCP/LCP/CLS preenchidos nos 3
   alvos) **não foi verificado**. No ambiente de dev o Chromium não alcança
   alvos externos: o proxy aceita a conexão e reseta o CONNECT. Por isso a
   campanha real mediu só TTFB e download total.
4. **`scripts/vps_smoke.sh --com-campanha`** (passo 6) — testado com stub nos
   dois caminhos, nunca com Docker real.
5. **Primeira noite `vps`** — a sequência está em **0/10**, com a única entrada
   (`ci`, de 2026-07-30) em quarentena v1. Ela só sai do zero quando o cron
   rodar sob o classificador v2.

Além disso, na UI do GitHub: tornar `quality-gate` um **check obrigatório**, e
apagar as branches mergeadas e a `claude/ci-gate-negative-test-jnf111` (o proxy
git das sessões recusava deleção de ref).

### 3.3 Um número que engana

A campanha contra alvos reais mediu `example.com` (controle, página mínima)
**mais lento** que `mozilla.org` (48 KB), e TTFB ≈ download total nos três
alvos. Isso não descreve os alvos: descreve o caminho. O egresso passava por um
proxy que re-termina TLS e aparentemente bufferiza a resposta.

**Não cite esses números como característica dos alvos.** Refaça a campanha na
VPS antes de usá-los para qualquer coisa.

---

## 4. Próximos passos, em ordem de dependência

### 4.1 Painel de estabilidade — FEITO (OS-26)

```bash
make painel     # report/estabilidade.html a partir de docs/lgpd-estabilidade.json
```

> A spec circulou como "OS-24" enquanto a trilha de LLM já usava esse número
> (`OS-24 v2`, `scripts/sumario.py`). Renumerada para **OS-26** aqui para que não
> existam duas OS-24 diferentes no histórico.

`webqa/estabilidade_html.py` reusa `ESTILO_CANONICO` byte a byte e **não inventa
classe nenhuma** — as 42 que a referência usa já existiam na folha. A regra do
ledger continua em `scripts/estabilidade.py::caminhada`, ponto único: o painel
recebe a caminhada pronta e só rotula. Duas implementações da mesma regra
divergiriam justamente no número que a página exibe como verdade.

O que o gerador garante, com teste: troca de `alvo_sha256` reinicia a sequência e
diz *"o alvo mudou de identidade"* preservando o histórico; entradas `ci`/`local`
aparecem rebaixadas e nunca removidas; o número de violações vem interpolado do
contrato, nunca literal; e ledger vazio produz página válida e explicativa —
instalação nova não pode parecer defeito.

**`--painel` nunca escreve no ledger**, em nenhuma combinação de flags. É leitura
mais renderização, então é seguro no GitHub, onde nada pode tocar o arquivo.

**O zero é explicado, não só exibido** (OS-33). Quando a sequência está em zero, a
página lista os motivos DERIVADOS do ledger — nenhuma noite do ambiente oficial,
entradas em quarentena, alvo com identidade nova, flake na última noite contada.
São cumulativos: o ledger real hoje tem três ao mesmo tempo, e mostrar só o
primeiro esconderia que corrigir a origem não bastaria para a contagem começar.
Zero por "ainda não houve noite oficial" e zero por "flake ontem" são situações
opostas — a primeira é normal, a segunda é infraestrutura quebrando — e o mesmo
dígito representa as duas.

### 4.2 `Finding` em toda a dimensão `seguranca` — FEITO (OS-28 e OS-29)

Dívida encerrada. **Todo** check que reprova na dimensão constrói `Finding` e
registra com `dominio.registrar_achados(request.node.nodeid, achados)`; nenhum
achado de `seguranca` chega ao laudo pelo caminho de retrocompatibilidade. A
tabela de severidades é `SEGURANCA.md §8.1` — decidir severidade em revisão de
PR sem registrar ali vira memória, e memória não sobrevive à próxima pessoa.

Os checks que **informam** (sourcemap, SRI, autoria, `nosniff` de terceiro,
`SameSite` ausente) seguem `xfail` e não produzem achado: alerta com selo de
severidade seria um segundo semáforo dentro do estado, o que a regra 2.5 evita.
Há teste lendo o corpo dessas funções e reprovando se alguma construir `Finding`.

O caminho de retrocompatibilidade do template **permanece** — agora só para
summary histórico, e há teste que o exercita com dado sintético. Removê-lo faria
todo relatório antigo mudar de forma.

### 4.2b Sumário por LLM local — FEITO (OS-23 v2 e OS-24 v2)

Contrato em [`LLM.md`](LLM.md). A trilha está fechada: abstração, gate
`WEBQA_LLM_ENABLED`, veto de endpoint (`webqa/llm.py`) e a etapa que os usa
(`scripts/sumario.py`, `make sumario`).

```bash
WEBQA_LLM_ENABLED=1 make sumario   # depois do pytest; sem gate ou sem runtime, não gera nada
```

Quatro invariantes que é fácil desfazer sem perceber — todas com teste:

- **o veto é por IP resolvido**, nunca por string (`LLM.md §2.1`, que também
  registra por que o IMDS é recusado apesar de link-local e por que `0.0.0.0` é
  checado antes de `is_private`);
- **`passed` não entra no prompt**, e `detail` **não** é re-sanitizado — já nasce
  sanitizado no `report.py`, e duplicar a borda cria a ilusão de duas defesas
  onde há uma só;
- **processo separado**, nunca `pytest_sessionfinish`. Um `try/except` amplo no
  hook que escreve o laudo reencena o pior defeito deste projeto (erro de setup
  engolido virando "noite limpa" com navegador morto). Fora do hook, capturar é
  seguro — a lição é a separação de processo, não a proibição de capturar;
- **duas guardas sobre a saída**, e a segunda é a menos óbvia: além da linguagem
  de certificação, um detector de **omissão** marca o sumário que deixou uma
  dimensão com `failed` fora do texto. O risco de um modelo não é só afirmar
  demais — é calar, e ausência não deixa marca sozinha.

O que **não** foi feito: validação com runtime local de verdade. Tudo aqui é
verificação com modelo fake, sem rede. Rodar `make sumario` contra o alvo
fixture com um Ollama de pé continua pendente — é o análogo, nesta trilha, do
§3.2: exercitado com dublê, não confirmado no ambiente real.

### 4.3 `seguranca` Fase C — sondagem ativa (TRAVADA, e a trava é testada)

Desenhada em `SEGURANCA.md §7`, **não implementada de propósito**. Sondar
`/.git/HEAD`, `/.env`, o `.map` da Fase B; seguir sublinks; baixar arquivos
extras. Exige `WEBQA_ACTIVE_PROBES_AUTHORIZED=1`, rate-limit, user-agent
identificável e **audit log** ao acionar o gate.

Construir capacidade intrusiva antes de haver alvo autorizado é YAGNI com peso
ético. **Não comece isto sem autorização escrita do dono de um alvo.**

**A trava deixou de ser promessa** (OS-36, `tests/test_fase_c_travada.py`). O que
se testa ali é a **recusa**, nunca a ação — nenhuma linha de sondagem foi escrita
e nenhuma requisição sai:

* um detector varre o `ast` de `checks/` inteiro e reprova literal de caminho
  sensível (`/.git`, `/.env`, `/backup.zip`, `/.DS_Store`, `/wp-config`,
  `/.htpasswd`) fora de docstring — comentário e documentação seguem livres,
  porque explicar não é fazer;
* os símbolos da Fase C (`follow_sublinks`, `probe_path`, `fetch_map`…) são
  verificados como **ausentes**: a ausência é intencional, e se um aparecer,
  alguém começou;
* nenhum check consome `require_active_probes()` hoje, e isso também é teste — o
  dia em que consumir, o teste muda junto, num PR que diga isso;
* matriz 2×2 dos gates: autorizar carga **nunca** autoriza sondagem.

Os três detectores foram provados contra violação plantada. Um detector que
nunca detectou nada não está provado — e a trava, sem isso, dependeria de
vigilância humana, que é justamente o que este projeto substitui por invariante
estrutural.

### 4.3-bis Acesso autenticado — a porta abriu, a sondagem não (OS-37)

`WEBQA_BASIC_AUTH_USER`/`_PASS` fazem a suíte passar por um Basic Auth de nginx,
no cliente HTTP e no navegador. Três coisas que quem for mexer aqui precisa saber
antes de tocar no código, porque nenhuma delas é dedutível lendo só as chamadas:

* **a autenticação é presa a origem + esquema, não ao cliente.** Parece
  burocracia até lembrar que o mesmo `client` de sessão busca o axe-core na
  Cloudflare e segue o link da política de privacidade. Um `httpx.BasicAuth`
  comum mandaria a senha do operador para os dois — e para o `http://` puro do
  `test_http_redireciona_para_https`. Ver `webqa/auth.py::pode_enviar_credencial`.
* **a senha é mascarada por VALOR, e em todas as formas escapadas.** Varrer o
  `summary.json` procurando o valor cru falharia justamente com as senhas boas:
  `json.dumps` escapa aspas, `html.escape` escapa `&<>`. Por isso
  `variantes_da_senha` registra seis formas, e a varredura acontece sobre a
  string já serializada — o que faz um campo novo nascer coberto.
* **o aceite é grep na saída**, não inspeção de chamada
  (`tests/test_vazamento_de_credencial.py`), com um teste que prova que a
  varredura tem dentes e uma guarda AST sobre toda escrita do relatório.

O próximo passo é a **OS-38** (passivo autenticado): explorar a área logada
seguindo só o que a aplicação oferece. A Fase C segue desligada — e agora por
escolha, não por falta de autorização, o que é uma distinção que o registro de OS
guarda explicitamente.

### 4.4 LGPD Fase 2 — travada por decisão de arquitetura

Canário de consentimento e detecção de CMP. Destravada por **10 noites `vps`
consecutivas** sem flake de infraestrutura. Hoje: 0/10.

### 4.5 LGPD Fase 3 — backlog

Global Privacy Control (`Sec-GPC: 1`) e heurísticas de fingerprinting.

---

## 5. Como trabalhar aqui

1. **Branch por ordem de serviço**, PR contra `main`, `quality-gate` verde antes
   do merge.

   **Squash** é o default, e vale para PR isolado. **Pilha de PRs encadeados usa
   merge commit**, do topo da base para cima: squash gera sha novo, o commit em
   que o PR seguinte se baseou deixa de existir na história, e o merge dele passa
   a arrastar conteúdo duplicado para resolver à mão. Merge commit preserva o
   encadeamento.

   Procedimento da pilha, na ordem:

   1. mergeie o PR de baixo;
   2. **reaponte o próximo para `main` à mão** — o retarget automático do GitHub
      não é confiável aqui (na pilha #20→#22 ele não ocorreu em nenhum dos dois,
      e uma das chamadas de reaponte expirou e precisou de segunda tentativa);
   3. **confirme o novo `base` LENDO o estado do PR**, não pelo retorno da
      chamada que pediu a mudança — a chamada pode responder e não ter aplicado;
   4. só então mergeie, e repita.

   Precedente: **#20 → #21 → #22** (OS-27/28/29). O #20 entrou com merge commit,
   `c869a28` ficou em `main`, e a pilha seguiu encadeada até o fim. Ao terminar,
   confira o resultado em `main` (`git merge-base --is-ancestor <sha> origin/main`
   para cada commit da pilha), não só a resposta de cada merge.
2. **Verificação × validação separadas.** Verificação: unidade sobre dado
   fabricado, sem rede, em `tests/`. Validação: execução real contra o alvo
   fixture ou contra alvo externo. As duas entram no PR.
3. **Teste antes do check**, quando der. O caso do segredo fake foi escrito
   antes do detector.
4. **Comentário explica o porquê**, nunca o quê. Se o comentário parafraseia o
   código, apague-o.
5. **stdlib primeiro.** `Pillow`, `piexif`, `pypdf` e `python-magic` foram
   rejeitadas com fundamento registrado. Dependência nova precisa de justificativa
   no PR. E dependência que **determina o ambiente de teste** vai pinada com o
   porquê ao lado: `playwright` fixa a revisão do Chromium, então faixa aberta
   ali faz testes de navegador virarem skip explicado — verde no CI, contrato do
   fixture não conferido. Pin é config explícita (12-Factor); subir de versão
   vira decisão versionada em vez de acidente de data de build.
6. **Quando o alvo fixture não conseguir exercer uma regra**, declare em
   `fora_do_contrato` com motivo e cubra por unidade.
7. **Quando encontrar um defeito fora do escopo da OS**, reporte-o no PR mesmo
   que não o conserte. Os três defeitos mais graves deste projeto foram achados
   assim — e dois deles falseavam a métrica de confiança para o lado otimista.

---

## 6. Comandos que você vai usar

```bash
make verify            # verificação da própria suíte (o que o CI roda)
make lint && make sast # ruff + bandit, mesmos comandos do CI
make lgpd              # dimensão de privacidade contra o alvo configurado
make seguranca         # dimensão de segurança
make fixture           # sobe o alvo fabricado em porta efêmera
make campanha          # nível sistema: alvos reais × N, consolidado
make audita-design     # gate do pacote de design (§12)
make estabilidade      # classifica a execução e grava o ledger
make sumario           # anexo assistido por IA local (desligado por padrão)
make painel            # report/estabilidade.html a partir do ledger (só lê)
make telemetria        # agrega campanhas já executadas (não faz requisição)
make vps-smoke         # valida a VPS antes de agendar o cron

python scripts/estabilidade.py --recompute   # auditoria do ledger, sem gravar
```
