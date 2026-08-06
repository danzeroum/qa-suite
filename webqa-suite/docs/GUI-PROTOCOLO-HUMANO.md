# Protocolo de sessão moderada — o que a automação não alcança

Este documento é **executável por quem nunca leu uma linha desta suíte**. Se em
algum ponto ele exigir entender código, é defeito dele.

> **Por que ele existe.** A camada `gui` mede o que o navegador mostra —
> geometria, CSS computado, tempo. Ela não julga se a pessoa **entendeu**.
> Satisfação, confiança, carga cognitiva e clareza de rótulo continuam exigindo
> gente, e `docs/GUI.md` declara isso desde a primeira linha. Este protocolo é o
> que torna essa ressalva acionável em vez de decorativa.

---

## 0. O que você precisa antes de começar

| Item | Onde está |
|---|---|
| Roteiro de tarefas | `checks/acceptance/features/jornada_usabilidade.feature` — **os cenários são o roteiro** |
| Pauta de observação | `data/gui-perfis.yaml`, bloco `conformidade.exige_humano` |
| Ficha da sessão | modelo em `docs/exemplos/sessao-modelo.yaml` |
| Termo de consentimento | §2 deste documento |

**O roteiro não é reescrito aqui, e isso é de propósito.** Os cenários foram
escritos na OS-51 para serem executados por uma pessoa **e** por um robô, com as
mesmas palavras. Reescrevê-los neste documento produziria duas versões que
divergem na primeira edição — e a comparabilidade entre TSR humano e sintético,
que é o produto inteiro, morreria aí. Abra a feature e leia dela.

Mesma regra para a pauta: os cinco critérios vêm do mapa **por referência**.
Copiá-los para cá seria uma contagem em prosa sem guarda que a confira.

---

## 1. Quem convidar, e quantas

**Cinco participantes por perfil** encontram a maior parte dos problemas de
usabilidade — é o número de Nielsen, e vale como piso, não como meta. O que
importa mais que o N é a **variedade de perfil**: alguém que usa teclado, alguém
que usa leitor de tela, alguém que nunca viu o produto.

Não convide colegas de time. Quem conhece o produto não consegue não saber.

---

## 2. Consentimento — leia em voz alta, e registre

> Vou pedir que você use este site enquanto pensa em voz alta. **Não é você que
> está sendo testado — é o site.** Não existe resposta errada, e se algo não
> funcionar, isso é exatamente o que eu preciso ver.
>
> Vou registrar apenas: suas **iniciais**, seu perfil de uso, o que você fez em
> cada tarefa e o que você disse. **Não registro seu nome.** A gravação, se você
> autorizar, serve só para eu conferir minhas anotações, e é apagada em até
> **30 dias**. Você pode parar a qualquer momento, sem explicar por quê, e pode
> pedir que eu apague tudo o que já registrei.
>
> Posso gravar a tela e o áudio?

Registre na ficha: `finalidade`, `retencao_dias`, `expurgo`, `gravacao`, `data`.
O consolidador **recusa a sessão** sem esses cinco campos — sessão sem prazo e
forma de expurgo declarados é coleta que ninguém consegue auditar depois. Ele
também calcula a data-limite do expurgo e a grava, para ninguém guardar de
cabeça.

---

## 3. O que dizer, e o que não dizer

| Diga | Nunca diga |
|---|---|
| "Pense em voz alta." | "Clique ali no menu." |
| "O que você espera que aconteça?" | "Está vendo o botão azul?" |
| "O que você está procurando agora?" | "Isso está no rodapé." |
| "Pode continuar." | "Quase — tenta de novo." |
| *(silêncio)* | *(qualquer coisa dita para preencher o silêncio)* |

**A regra que resume todas:** se a sua frase contém um substantivo da interface
que a pessoa ainda não disse, você guiou. Anote a vontade de ajudar — ela é o
achado. Quando você sente vontade de apontar o caminho, é porque o caminho não
está aparecendo, e é isso que a sessão veio medir.

**Silêncio é dado.** Conte até dez antes de intervir.

> **Esta seção vale para o bloco de TAREFAS (§5), e só para ele.** No bloco de
> observação (§6) você **aponta** para um elemento e pergunta sobre ele — é uma
> sondagem dirigida, feita depois das tarefas, e apontar ali não contamina nada
> porque já não há tarefa a resolver.
>
> A distinção é a coisa que mais se erra: durante a tarefa, apontar entrega a
> resposta e destrói a medida; depois dela, apontar é a única forma de perguntar
> sobre um elemento específico. Se você misturar os dois blocos, o SEQ e o TSR da
> tarefa deixam de valer — anote e descarte aquela tarefa.

---

## 4. Condução

**Duração total: 45 minutos.** Se passar de 60, encerre — cansaço vira ruído e
os últimos dados valem menos que o desconforto de quem ficou.

| Bloco | Tempo | O que fazer |
|---|---|---|
| Acolhimento e consentimento | 5 min | §2, em voz alta |
| Contexto | 3 min | "Como você costuma comprar online?" — sem falar do site |
| **Tarefas** | 20 min | um cenário por vez, §5 |
| Pauta de observação | 10 min | §6 |
| Fechamento | 7 min | SUS (§7), agradecimento, dúvidas |

### Encerrar uma tarefa

Encerre quando qualquer um acontecer:

1. a pessoa **concluiu**;
2. a pessoa **desistiu** — e desistir é resultado, anote `concluiu: false`;
3. passaram **5 minutos** na mesma tarefa;
4. a pessoa demonstrou desconforto real.

Nos casos 2, 3 e 4 diga: *"Obrigada, isso já me diz o que eu precisava. Vamos
para a próxima."* Não explique como se fazia — ainda não. Se ela perguntar,
responda no fechamento.

---

## 5. As tarefas

Abra `jornada_usabilidade.feature` e leia o **nome do cenário** como cartão de
tarefa. Hoje são quatro; três viram tarefa de sessão:

| Cenário | Como você lê para a pessoa |
|---|---|
| *O visitante encontra a política de privacidade* | "Encontre a política de privacidade deste site." |
| *O visitante procura como falar com a loja* | "Você quer falar com alguém da loja. Encontre como." |
| *O visitante conclui a tarefa no tempo previsto* | não é tarefa: é o cronômetro das outras |

> *Nenhuma página deixa o visitante sem saída* também não vira tarefa — é uma
> propriedade do site que o crawler mede melhor que uma pessoa. Está na feature
> porque o robô a executa; aqui ela aparece como **pauta de observação**: anote
> se a pessoa ficou presa em alguma página.

**Por tarefa, anote:** concluiu (sim/não), segundos, cliques, e o **SEQ logo em
seguida** — antes de passar adiante, enquanto a impressão está fresca:

> "De 1 a 7, quão fácil foi essa tarefa? 1 é muito difícil, 7 é muito fácil."

Se a pessoa não responder, **deixe em branco**. Em branco significa "não medi";
um zero seria um valor fora da escala lido como "muito difícil".

---

## 6. Pauta de observação — os cinco que a máquina não julga

Os IDs abaixo vêm de `data/gui-perfis.yaml`, bloco `conformidade.exige_humano`.
Cada um tem, no próprio mapa, o motivo de exigir gente. Pergunte assim:

| Critério | Pergunte / observe |
|---|---|
| **1.1.1** Conteúdo não textual | aponte uma imagem: "o que esta imagem está te dizendo?" — o `alt` existe (a máquina confere); se ele **descreve**, só você sabe |
| **1.3.1** Informação e relações | "sem olhar, me diga o que tem nesta página" — a estrutura corresponde ao sentido? |
| **2.4.6** Cabeçalhos e rótulos | aponte um rótulo: "o que você espera encontrar aqui?" |
| **3.3.2** Rótulos ou instruções | num formulário: "o que este campo quer de você?" |
| **4.1.2** Nome, função, valor | com leitor de tela, se houver: o controle se anuncia pelo que faz? |

Cada desencontro vira **achado**, com severidade de Nielsen:

| | |
|---|---|
| **0** | não é problema |
| **1** | cosmético — corrigir se sobrar tempo |
| **2** | menor — prioridade baixa |
| **3** | maior — prioridade alta |
| **4** | catástrofe — corrigir antes de publicar |

Severidade é sobre **impacto na tarefa**, não sobre o quanto incomodou você.

---

## 7. SUS — dez afirmações, escala de 1 a 5

Leia cada uma e peça um número de 1 (discordo totalmente) a 5 (concordo
totalmente). **Na ordem**, sem pular: a escala é validada como conjunto.

1. Eu usaria este site com frequência.
2. Achei o site desnecessariamente complexo.
3. Achei o site fácil de usar.
4. Precisaria de ajuda de alguém para usar este site.
5. As partes do site funcionam bem juntas.
6. Há coisas demais inconsistentes neste site.
7. A maioria das pessoas aprenderia a usar isto rapidamente.
8. Achei o site atrapalhado de usar.
9. Me senti confiante usando o site.
10. Precisei aprender muita coisa antes de conseguir usar.

**Não interprete o número no meio da sessão.** SUS 68 é a média da literatura, e
**não** é "68% de aprovação" — o consolidador calcula; você só coleta.

---

## 8. Depois da sessão

```bash
python scripts/consolida_sessao.py minha-sessao.yaml
```

Saem métricas com `fonte=humano` e os mesmos nomes das automatizadas
(`gui_jornada_tsr_*`, `gui_jornada_tot_ms_*`), mais os achados ordenados por
severidade, em `report/sessao/`.

**Comparáveis, jamais confundíveis.** As duas fontes vão lado a lado; somá-las
numa média inventaria um terceiro número que não descreve nem uma coisa nem
outra. Se o TSR humano for menor que o sintético, o robô achou um caminho que a
pessoa não achou — e isso é achado de rótulo, não erro de medição.

Apague a gravação no prazo. A data-limite está no JSON.

---

## 9. Ensaio antes da primeira sessão

Rode o protocolo inteiro **com você mesma no papel da participante**, em voz alta
e cronometrado, antes de convidar alguém. É a única leitura que pega pergunta que
guia, tarefa que não cabe no tempo e passo que só faz sentido para quem escreveu.

O ensaio deste documento (OS-54, contra o alvo fabricado) achou três coisas antes
de qualquer pessoa ser convidada:

1. a contradição entre §3 e §6 sobre apontar — consertada com a nota do §3;
2. a home oferece **dois links diferentes para o mesmo destino** ("Privacidade" e
   "Politica de Privacidade"), e uma pessoa os lê como dois lugares. Virou achado
   de severidade 2 no modelo de ficha;
3. a tarefa "falar com a loja" termina em **desistência**, não em conclusão — e
   foi o que confirmou que `concluiu: false` precisa ser tão fácil de anotar
   quanto `true`. Desistir é resultado.

Se o seu ensaio não achar nada, provavelmente você leu em silêncio.
