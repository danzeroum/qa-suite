# Campanha: a suíte contra alvos reais, N vezes

A campanha é o **nível sistema da própria suíte**. `tests/` verifica unidades
contra dados fabricados; a campanha valida o conjunto contra alvos que ninguém
controla — que mudam de resposta entre duas requisições, exigem identificação do
cliente, e às vezes simplesmente recusam atender.

```bash
make campanha                    # 3 alvos × 3 repetições, conforme campanha.yaml
python scripts/campanha.py --repeticoes 5
python scripts/campanha.py --campanha outro.yaml --saida /tmp/campanha
```

Saída em `report/campanha/`: `consolidado.md` (leitura humana), `consolidado.json`
(consumo por ferramenta) e o `summary.json` bruto de cada execução em
`<host>/run<N>/`. Tudo sob `report/`, que é ignorado pelo git — resultado de
campanha não é versionável (Risco R8: artefato carrega host e trecho de erro do
alvo).

## O que ela mede, e por que em dois eixos

**Tempo do alvo** — TTFB, download total, FCP, LCP, CLS, DOMContentLoaded, peso
da página: o que o usuário do alvo sente.

**Tempo da suíte** — quanto custa medir aquilo. Suíte que leva quatro minutos por
alvo não roda a cada commit, e suíte que não roda não protege nada. O consolidado
traz o tempo somado por dimensão e o top-5 de testes mais lentos.

Confundir os dois é o erro mais fácil de cometer aqui: `duration_s` de um teste é
tempo da SUÍTE, não latência do alvo.

## Mediana e pior caso, sempre os dois

Toda métrica sai com mediana **e** pior caso. A mediana sozinha faz alvo
intermitente parecer saudável; o pior caso é o que o usuário azarado viveu. Pelo
mesmo motivo, ausência de amostra aparece como ausência: FCP que o navegador não
emitiu não vira `0 ms`, porque zero, num relatório de performance, é elogio.

## Estabilidade do veredito

O eixo que só existe porque repetimos. Um teste que dá **2×passed 1×failed** não
tem média — tem um problema, e ele aparece marcado com o placar, nunca agregado
num percentual. Teste que *desaparece* de uma repetição conta como instável
(`1×ausente`): sumir da coleta é instabilidade tanto quanto trocar de veredito.

Instabilidade não é veredito sobre o alvo. É dívida da suíte ou variação real do
alvo, e as duas precisam ser investigadas antes de o número virar laudo.

`error` é a quarta distinção, ao lado de passed/failed/xfail/skipped: falha FORA
do corpo do teste (fixture, navegador, rede). Não é veredito sobre o alvo — é o
teste **não tendo acontecido** — e por isso não se soma a `failed`.

## Garantias operacionais

* **Passiva por construção.** A campanha aborta se `WEBQA_LOAD_AUTHORIZED`
  estiver setado no ambiente — presença, não valor, então `=0` também aborta. E
  nunca propaga a variável ao pytest que ela dispara. Para carga autorizada
  existe `pytest -m load`, que é outra coisa.
* **Crawl reduzido** (`crawl_max_pages: 5` por alvo) e **pausa mínima de 10s**
  entre execuções — a pausa é piso, não default: configuração não a reduz.
* **Saída isolada** por alvo × repetição via `WEBQA_REPORT_DIR`, sem o que a
  execução seguinte sobrescreveria a amostra da anterior.
* **Um alvo fora do ar não derruba a campanha**: entra como inacessível, com o
  motivo, e as outras medidas se preservam. O código de saída é ≠0 só se
  **todos** falharem.
* **Código de saída fala da CAMPANHA, não da conformidade dos alvos.** Alvo
  reprovado é dado; não é erro de execução.

## Papéis dos alvos

Os três alvos default não são uma amostra aleatória — cada um responde uma
pergunta diferente:

| Papel | Pergunta |
|---|---|
| **controle** (`example.com`) | Página mínima e estável. Se ela oscilar, o problema é da suíte ou da rede local, não do alvo. É a régua. |
| **real pesado** (`www.wikipedia.org`) | A suíte aguenta um alvo grande, com i18n e muitos assets? |
| **falso-positivo** (`www.mozilla.org`) | Alvo maduro, com CSP e consentimento próprios. O que ele reprovar é candidato a falso-positivo da SUÍTE. É aqui que a campanha critica a própria régua. |

## Robot policy do alvo {#etiqueta}

`www.wikipedia.org` responde **403 a User-Agent genérico** e documenta a
exigência de identificação com contato (<https://w.wiki/4wJS>). Por isso o alvo
declara `user_agent` próprio em `campanha.yaml`, injetado via `WEBQA_USER_AGENT`.

Cumprir a política do alvo é o comportamento correto de uma suíte que prega
respeito ao sistema sob teste. Mascarar o cliente como navegador para furar a
política seria o oposto — e a suíte perderia a autoridade moral de cobrar
conformidade de quem ela mede.

### Etiqueta é invariante estrutural, não instrução

A disciplina mora em `webqa/etiqueta.py` e vale para **todo alvo que não seja
rede local**. Quem acrescenta um alvo ao `campanha.yaml` não precisa lembrar de
nada: o runner já se comporta.

| Regra | Comportamento |
|---|---|
| **`robots.txt` antes de tocar no alvo** | baixado com `httpx` e `timeout` do settings, lido por `RobotFileParser.parse` sobre o texto já baixado |
| **caminho proibido** | pulado com `robots.txt proíbe /x`; os permitidos seguem |
| **`Crawl-delay`** | respeitado entre páginas, quando declarado |
| **`429` / `503`** | encerra aquele alvo **nesta execução**, sem reinsistir |
| **crawl entre páginas** | sequencial, uma por vez |
| **User-Agent** | sempre identificável e com contato, mesmo sem `user_agent` no yaml |
| **alvo de rede local** | isento — é nosso, fabricado e controlado |

Quatro decisões que custaram para descobrir e que **não** devem ser desfeitas:

**`rp.read()` está proibido.** O `RobotFileParser` do stdlib busca o arquivo com
`urllib`, **sem timeout**. Um host que aceita a conexão e nunca responde travaria
a campanha inteira — sem log, sem fim e sem culpado aparente. Baixamos com
`httpx` (que tem timeout) e passamos o texto a `parse`. Há teste que percorre o
`ast` do módulo e reprova se alguém voltar ao `read()`.

**`crawl_delay()` pode levantar `AttributeError`.** Acontece quando o `robots.txt`
só traz grupos de agentes específicos e nenhum `*`: o `default_entry` fica `None`.
Deixar propagar derrubaria a campanha por causa do robots de um único alvo, com
um traceback que não fala de etiqueta. O fallback é `0.0`.

**`robots.txt` ilegível é *disallow* temporário, não erro.** 5xx, timeout ou
conexão recusada → o alvo é **pulado com motivo**. Não conseguir ler a política de
alguém não é licença para ignorá-la. E não é defeito da campanha, então também
não reprova a execução. `404` é o contrário: o host respondeu dizendo que não há
política, e aí tudo é permitido.

**A isenção do fixture é por IP resolvido** (`webqa/rede.py`), nunca por string.
`localhost.qualquercoisa.com` resolve para IP público; casar texto de URL seria
ilusão de controle. Host que não resolve conta como terceiro — na dúvida,
etiqueta a mais.

### O que a etiqueta NÃO serializa

Carregar **uma** página dispara CSS, JS e imagens em paralelo. Isso é o que um
visitante faz, é o que as métricas de renderização precisam medir, e está fora
do escopo da etiqueta. O que se percorre uma de cada vez é o **crawl entre
páginas**.

Confundir os dois levaria a serializar assets — que não incomoda ninguém e
destruiria justamente a medida de FCP/LCP que a campanha existe para produzir.

### Alvo não medido nunca some do consolidado

Alvo que recuou, foi bloqueado por `robots.txt` ou ficou inacessível entra na
tabela de métricas com **"não medido"** em toda a linha, mais uma entrada na
seção de inacessíveis com o motivo.

Omitir a coluna faria alvo que pediu recuo e alvo que passou ficarem
indistinguíveis — e **alvo ausente é lido como alvo sem problema**, que é o pior
engano possível num consolidado. É a regra 2.1 aplicada ao nível de sistema:
ausência nunca vira aprovação.

## Limite conhecido: navegador atrás de proxy

Ambiente cujo egresso externo só existe via proxy HTTP entrega as métricas de
rede (TTFB, total) mas **não** as de renderização: o Chromium não alcança alvos
externos, e os testes `browser` entram como `error`. O consolidado diz "não
medido" nessas linhas em vez de inventar número.

Não é defeito da campanha nem do alvo. Para medir FCP/LCP/CLS é preciso um
ambiente com saída direta — a VPS oficial (`docs/VPS.md`), por exemplo.
