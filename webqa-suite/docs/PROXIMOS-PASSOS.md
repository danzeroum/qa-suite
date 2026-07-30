# Continuidade — o que existe, o que falta, e as regras que não estão no código

Documento de passagem para quem assume o projeto. Não repete o que os outros
docs já explicam: aponta para eles, diz **onde o trabalho parou** e registra as
decisões que um leitor do código sozinho não teria como deduzir.

Base deste documento: `main` em `3272077` (pós OS-23 e OS-27).

A verificação da própria suíte tem hoje **338 testes coletados**; num ambiente
limpo o resultado é **335 passed / 3 skipped**. Os 3 skips são de
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

### 4.1 Painel de estabilidade (OS-24, já especificada)

Gerar `report/estabilidade.html` a partir de `docs/lgpd-estabilidade.json`,
espelhando `docs/qa-suite design brief/referencia/estabilidade.html`.

Pontos de atenção que a spec já cobre e que é fácil errar: o `alvo_sha256`
**mudou** (o fixture ganhou quatro violações), então a sequência reinicia e a
página precisa dizer *"o alvo mudou de identidade"* com o histórico preservado;
entradas `ci`/`local` aparecem rebaixadas, nunca removidas; e o número de
violações do alvo na narrativa vem interpolado do contrato (hoje 11), nunca
literal.

Reuse a montagem do gerador do relatório (folha, header, footer) — um único
ponto de verdade visual.

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

### 4.3 `seguranca` Fase C — sondagem ativa

Desenhada em `SEGURANCA.md §7`, **não implementada de propósito**. Sondar
`/.git/HEAD`, `/.env`, o `.map` da Fase B; seguir sublinks; baixar arquivos
extras. Exige `WEBQA_ACTIVE_PROBES_AUTHORIZED=1`, rate-limit, user-agent
identificável e **audit log** ao acionar o gate.

Construir capacidade intrusiva antes de haver alvo autorizado é YAGNI com peso
ético. **Não comece isto sem autorização escrita do dono de um alvo.**

### 4.4 LGPD Fase 2 — travada por decisão de arquitetura

Canário de consentimento e detecção de CMP. Destravada por **10 noites `vps`
consecutivas** sem flake de infraestrutura. Hoje: 0/10.

### 4.5 LGPD Fase 3 — backlog

Global Privacy Control (`Sec-GPC: 1`) e heurísticas de fingerprinting.

---

## 5. Como trabalhar aqui

1. **Branch por ordem de serviço**, PR contra `main`, `quality-gate` verde antes
   do merge. Squash no merge.
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
make vps-smoke         # valida a VPS antes de agendar o cron

python scripts/estabilidade.py --recompute   # auditoria do ledger, sem gravar
```
