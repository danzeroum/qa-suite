# Telemetria operacional — dados sobre a PRÓPRIA suíte

`scripts/telemetria.py` agrega várias execuções de campanha para responder três
perguntas que uma execução sozinha não responde: **o que custa caro**, **o que
oscila** e **que check é suspeito**.

```bash
make campanha                       # produz os summary.json (várias vezes, ao longo do tempo)
make telemetria                     # agrega em report/telemetria.json
python scripts/telemetria.py --calibrar   # sugere limiares; NUNCA escreve no config.yaml
python scripts/telemetria.py --anonimo    # agregado sem alvo nominal (o único publicável)
```

## Não coleta nada novo

Esta é a fronteira que dá tranquilidade para o resto: a telemetria **não faz uma
requisição sequer**, não acrescenta campo ao `summary.json` e não instrumenta
nada. Ela lê artefatos que a suíte já gravou e conta.

Se um dia ela precisar de um dado que não existe, o caminho é acrescentar o campo
no `report.py` — sob a mesma borda de sanitização de sempre — e não abrir uma
segunda porta de coleta ao lado da primeira.

## O que se coleta, sobre quê, para quê, e onde fica

| Dado | Sobre | Finalidade | Retido onde |
|---|---|---|---|
| `test`, `dimension` | a **suíte** (nosso código) | identificar o check | `report/` (local) e agregado anônimo |
| `estado` (`passed`/`failed`/`xfail`/`skipped`/`error`) | veredito da suíte | flake e distribuição | idem |
| `duration_s` | custo de medir | ranking de lentos | idem |
| `metricas` (TTFB, LCP, CLS, peso) | o **alvo**, agregado | calibrar limiares | idem |
| `alvo` (host por extenso) | o alvo | leitura humana local | **só** `report/`, ignorado pelo git |
| `alvo_sha256` | o alvo | agrupar sem nomear | agregado anônimo |

`report/` é ignorado pelo git (R8) e nunca versionado. É por isso que o agregado
local pode carregar o host: ele não sai da máquina de quem rodou.

## As duas linhas que não se cruzam

**Nunca dado pessoal.** A telemetria opera sobre `test`, `dimension`, `estado` e
`duration_s` — quatro campos que descrevem a *suíte*, não titulares. Ela **nem
lê** o `detail`, embora ele já nasça sanitizado na borda de escrita. Corpo de
resposta, cabeçalho, cookie e IP não passam por nenhum caminho deste módulo, e há
teste estrutural que reprova se alguém acrescentar acesso a eles.

Minimização levada a sério significa não coletar o que não se usa — não
"coletar e mascarar depois".

**Nunca alvo nominal em artefato versionado ou publicado.** `anonimizar_agregado`
é obrigatório antes de qualquer saída que possa sair da máquina. Ele remove o
host e mantém o `alvo_sha256`, que agrupa sem nomear — a mesma decisão que o
ledger de estabilidade já tinha tomado.

Duas sutilezas que o teste fixa:

* a remoção é **por exclusão do campo**, não por mascaramento parcial. `mo****.org`
  seria reversível para quem conhece o conjunto de alvos, que são três e estão
  num yaml público;
* `origens` também sai. O caminho do artefato é
  `report/campanha/www.mozilla.org/run1/summary.json` — um campo de
  rastreabilidade que reintroduz o host anularia todo o resto.

## Os três cortes

### 1. Testes lentos

Mediana, p75, p95 e pior caso de `duration_s` por teste. Suíte que leva quatro
minutos por alvo não roda a cada commit, e suíte que não roda não protege nada.

Percentil exige **4 amostras**. Abaixo disso sai só mediana e pior caso: dizer
"p95 de duas execuções" seria dar precisão que o dado não tem.

### 2. Flake

Alternância de veredito **contra o mesmo `alvo_sha256`**.

Duas exclusões deliberadas, e cada uma protege o significado da métrica:

* **veredito diferente entre alvos não é flake.** Um site que reprova e outro que
  passa não são a suíte oscilando — é comportamento de alvo. É a mesma distinção
  que dá sentido ao ledger de estabilidade;
* **incidente isolado não é flake.** Um `error` sem nenhum `passed` do mesmo teste
  contra o mesmo alvo é uma falha — pode ser infraestrutura, pode ser o alvo —
  mas não é instabilidade. Chamar tudo de flake faria a métrica perder a única
  coisa que ela sabe dizer.

`skipped` e `xfail` ficam fora: pular por ausência de formulário na página é o
alvo sendo diferente, não a suíte tremendo.

### 3. Distribuição por check

Como cada check se comporta **entre** alvos. Duas suspeitas saem daqui, e nenhuma
é veredito — são candidatos a olhar:

* **candidato a falso positivo** — reprovou em algum alvo maduro. É exatamente o
  papel do alvo `falso-positivo` no `campanha.yaml`: é aqui que a campanha
  critica a própria régua;
* **candidato a check morto** — passou em **todos** os alvos, com base de pelo
  menos três. Pode estar certo; pode ter parado de detectar. Quem responde a
  segunda pergunta é o contrato 1:1 do alvo fixture; aqui só se levanta a
  suspeita. Com dois alvos não se suspeita de nada — ausência de evidência não é
  evidência.

## `--calibrar` sugere, nunca aplica

Imprime um diff comentado: limiar atual, limiar sugerido (p75 observado + 20% de
folga) e a direção da mudança. **O `config.yaml` nunca é escrito**, e há teste que
compara o md5 antes e depois.

A guarda importa mais que a conveniência. Um processo que ajusta o próprio limiar
a partir do que mediu **converge para aprovar tudo**: mede um alvo lento, afrouxa
o orçamento, e na próxima o alvo lento passa. A sugestão sai em texto justamente
para obrigar um humano a decidir se o alvo melhorou ou se o orçamento estava
errado — são coisas diferentes, e só quem conhece o produto sabe qual é.

A folga de 20% também não é número mágico: limiar colado no p75 reprova um quarto
das execuções saudáveis; folgado demais não reprova nada.

## Rastreabilidade

Cada agregado local registra `origens`: o caminho relativo de todo `summary.json`
que entrou na conta. Número sem procedência não é auditável — quem lê "mediana
4,2 s" precisa poder voltar ao arquivo que a produziu.

Artefato truncado ou ilegível é **pulado**, não fatal: um `summary.json` cortado
pela metade não pode derrubar a leitura dos outros nove.

## Sem dados, sem número

Nenhum `summary.json` sob `report/campanha/` → mensagem clara e **exit ≠ 0**, sem
stacktrace. Telemetria de nada não é telemetria vazia: é ausência de base, e
dizer isso é melhor que imprimir zeros.
