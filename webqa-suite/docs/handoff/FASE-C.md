# Fase C — Sondagem Ativa Autorizada (plano de desenvolvimento)

> Status: **PROPOSTA para revisão**. Nada aqui está implementado. Enquanto este
> documento não for aprovado pelos analistas e a governança de C0 não for
> cumprida, a Fase C permanece travada por `tests/test_fase_c_travada.py` (OS-36),
> e é assim que deve ser.

## 0. Princípio reitor (a única coisa que não é negociável)

O próprio código já nomeia o que a Fase C é: *"a linha que separa auditoria de
intrusão"* (`docs/SEGURANCA.md §1`). A tese deste plano é que **o que fica de um
lado ou de outro dessa linha não é a técnica — é a autorização e o escopo.**
Pedir `/.git/HEAD` ao próprio servidor, com autorização escrita e para descobrir
uma exposição antes que um atacante o faça, é higiene defensiva. Pedir a mesma
coisa a um host de terceiro é intrusão. A técnica é idêntica; o que muda é o
alvo.

Disso decorrem três invariantes que o plano trata como **estruturais** (caminho
que não existe), no mesmo molde do `Finding` que sanitiza no construtor e da
credencial que nasce registrada para mascaramento:

1. **Escopo fechado por lista de propriedade.** A Fase C só toca hosts declarados
   num `escopo-autorizado.yaml` versionado. Host fora da lista não é "pulado com
   aviso": não existe caminho no programa que fabrique uma requisição ativa para
   ele. Igual à página órfã do fixture — a ausência é a garantia.
2. **Detectar e reportar, nunca explorar.** A Fase C prova que um recurso sensível
   está *exposto* e para ali. Ela **não** reconstrói repositório a partir de
   `.git`, não coleta segredos de um `.env` encontrado, não baixa dump inteiro.
   Achou `200 OK` em `/.env`? O laudo diz "exposto, severidade alta, corrija" — e
   o corpo não é lido além do mínimo para confirmar o tipo.
3. **Autorização é opt-in duplo e datado.** Gate técnico (`WEBQA_ACTIVE_PROBES_AUTHORIZED=1`)
   **e** registro de autorização escrita por alvo, com data e responsável. Um sem
   o outro não roda.

Se qualquer PR da Fase C enfraquecer uma dessas três, o PR está errado — não o
teste que o reprovou.

## 1. Escopo

### Dentro (o que a Fase C passa a fazer)
- **Descoberta de conteúdo não linkado** (forced browsing) de uma lista *curada e
  limitada* de caminhos sensíveis, contra alvos do escopo autorizado: metadados
  de VCS (`/.git/…`), arquivos de configuração/ambiente (`.env`, `.env.*`),
  backups (`*.bak`, `*.zip`, `*.sql`), swaps de editor (`.swp`, `~`), artefatos
  de CI/deploy expostos, `.DS_Store`, source maps não referenciados.
- **Interação ativa** para os testes que exigem escrita/estado, sempre em alvo
  próprio: submissão de formulário (segurança de formulário), aceitar/recusar
  banner de consentimento e exercer direito de titular (fluxos LGPD que hoje só
  têm bateria passiva — ver `checks/lgpd/`).

### Fora (não é Fase C, e não entra por ela)
- Força bruta de credencial, bypass de autenticação, enumeração de usuários.
- **Exploração** de qualquer achado (git-dump, harvest de segredo, leitura de
  dump completo, SSRF via metadados de nuvem — que `webqa/rede.py` já recusa).
- Qualquer escrita destrutiva, geração de carga (isso é o outro gate,
  `WEBQA_LOAD_AUTHORIZED`), ou fuzzing de payload de injeção.
- Qualquer host fora do `escopo-autorizado.yaml`. Em especial, os alvos de
  terceiro da campanha (`campanha.yaml`: example/wikipedia/mozilla) **nunca**
  entram na Fase C — a etiqueta passiva deles fica exatamente como está.

## 2. Pré-requisitos de autorização (a trava)

Antes de qualquer sub-capacidade, C0 constrói a trava:

- **`escopo-autorizado.yaml`** (novo): lista de origens próprias, cada uma com
  `autorizado_por`, `data`, `evidencia` (link/hash do aceite). Carregado por um
  módulo `webqa/escopo.py` que expõe `esta_no_escopo(url) -> bool`.
- **Reúso da fronteira existente.** Nada de casar string: a decisão de "este host
  é meu" passa por `webqa/rede.py` quando aplicável, e a comparação de origem por
  `webqa/auth.origem_de` (que já normaliza porta e descarta userinfo). A Fase C
  vira um **quarto consumidor** da fronteira de rede — logo entra no registro de
  `tests/test_fronteira_de_rede.py::FRONTEIRAS_DE_REDE` com o teste que prova o
  ramo "fora do escopo".
- **Gate.** `gates.require_active_probes()` já existe e faz `skip` quando o opt-in
  falta. A Fase C o consome; sem o gate, os testes ativos nem coletam.
- **Regra herdada.** "Nunca banco, gov ou serviço com anti-automação" (hoje em
  `campanha.yaml`) sobe para verificação: um alvo no escopo que aparente ser um
  desses reprova o carregamento do escopo, não só avisa.

## 3. Requisitos

### 3.1 Histórias de usuário (formato INVEST, com critérios de aceite)

- **HU-C1 — Descobrir exposição de VCS/config.** *Como* operador de segurança do
  meu próprio site, *quero* que a suíte detecte `/.git`, `.env` e backups
  acessíveis, *para* corrigir a exposição antes que alguém a encontre.
  *Aceite:* dado um alvo no escopo com `/.env` respondendo 200, o laudo registra
  um `Finding` severidade alta, fase=C, com a URL e o motivo; dado o mesmo alvo
  sem `/.env` (404), nenhum finding é criado; dado um alvo fora do escopo, a
  descoberta **não executa** e o laudo diz por quê.
- **HU-C2 — Testar o fluxo de consentimento de verdade.** *Como* controlador,
  *quero* aceitar e recusar o banner e observar o que dispara em cada caso, *para*
  provar que o consentimento prévio é respeitado. *Aceite:* com o gate ligado e o
  alvo no escopo, a suíte executa os dois caminhos em contextos virgens e reporta
  divergência; com o gate desligado, os testes fazem `skip` com instrução.
- **HU-C3 — Não poder rodar fora do escopo.** *Como* responsável, *quero* que seja
  **impossível** apontar a Fase C para um host que não autorizei. *Aceite:* uma
  URL fora do `escopo-autorizado.yaml` faz a coleta abortar com mensagem única; um
  teste com alvo plantado fora do escopo prova a recusa.
- **HU-C4 — Rastrear tudo.** *Como* auditor, *quero* um log do que a Fase C pediu,
  quando e sob qual autorização. *Aceite:* cada requisição ativa gera linha de
  auditoria (URL, método, timestamp, alvo, id da autorização) e nenhuma linha
  vaza segredo (reúso do mascaramento por valor de `webqa/auth.py`).

### 3.2 Requisitos não funcionais
- **Segurança:** escopo fechado (§2); detectar-e-reportar (§0.2); sem exfiltração;
  mascaramento de credencial reaproveitado; auditoria imutável por execução.
- **Performance/respeito ao alvo:** rate limit configurável (piso de intervalo
  entre requisições ativas), `HEAD` antes de `GET` onde possível, teto de
  caminhos por alvo, `429/503` encerram o alvo sem reinsistência (mesma etiqueta
  da campanha), kill-switch por variável de ambiente.
- **Observabilidade:** fase e severidade como **dado** no `summary.json` (não como
  texto), para o consolidado e a estabilidade lerem sem regex.
- **Usabilidade do laudo:** todo achado da Fase C traz a remediação, não só o
  sintoma. "Exposto" sem "como fechar" é meio laudo.
- **Escalabilidade/manutenção:** stdlib-first como o resto de `webqa/`; a lista de
  caminhos é dado versionado e curado, com procedência, nunca um wordlist gigante
  colado sem revisão.

## 4. Arquitetura

Módulos novos, todos plugando no que já existe:

- `webqa/escopo.py` — carrega e valida `escopo-autorizado.yaml`; `esta_no_escopo`.
- `webqa/sondagem.py` — o motor de descoberta *read-only*: recebe alvo + lista
  curada, aplica rate limit/etiqueta, e devolve `Finding`s. Não conhece HTTP
  diretamente: usa o cliente de sessão e o `PoliteFetcher` já existentes.
- `checks/seguranca/test_exposicao_ativa.py` — consome `sondagem` sob gate.
- `checks/lgpd/test_consentimento_ativo.py`, `test_dsar.py` — interação ativa.
- Extensão do `Finding` (`webqa/dominio.py`) para carregar `fase` e `remediacao`
  como campos, se ainda não os tiver na forma necessária.

O relatório (`webqa/report*.py`) ganha a coluna/seção de Fase C. O ledger de
estabilidade (`docs/VPS.md`) trata run com Fase C como **dimensão à parte** — não
se mistura veredito passivo com ativo na mesma métrica.

## 5. Faseamento (para revisão incremental)

Cada fase é um PR (ou conjunto pequeno) que os analistas aprovam antes da próxima.

- **C0 — Governança e trava (nenhuma sondagem ainda).** `escopo.py`,
  `escopo-autorizado.yaml`, wiring do gate, log de auditoria, e a **inversão
  deliberada de `test_fase_c_travada.py`**: o teste que hoje prova a *ausência* da
  capacidade passa a provar que ela **só existe sob escopo+gate**. Essa inversão é
  o momento em que a trava estrutural é aberta — exige sign-off explícito (§7).
- **C1 — Descoberta read-only.** `sondagem.py` + `test_exposicao_ativa.py`, lista
  curada e limitada, rate limit, kill-switch, `HEAD`-first, detectar-e-reportar.
- **C2 — Interação ativa (primeiras escritas).** Consentimento e DSAR em alvo
  próprio; contextos virgens; idempotência onde possível; segundo checkpoint de
  revisão porque é a primeira vez que a suíte escreve no alvo.
- **C3 — Consolidação e campanha própria.** Integração ao relatório, `campanha`
  restrita ao escopo autorizado, dimensão separada no ledger.

## 6. Salvaguardas técnicas (resumo)
Rate limit com piso; backoff e encerramento em `429/503`; `WEBQA_ACTIVE_PROBES_KILL`
como parada de emergência; `--dry-run` que lista o que *seria* pedido sem pedir;
auditoria por execução; mascaramento de credencial reaproveitado; teto de caminhos
por alvo; recusa dura fora do escopo; nenhuma leitura de corpo além do mínimo para
classificar o tipo do achado.

## 7. Governança — o que os analistas assinam
- **Antes de C0:** aprovação deste plano e do `escopo-autorizado.yaml` inicial
  (só hosts comprovadamente `danzeroum`).
- **Abertura da trava (C0):** revisão específica da inversão de
  `test_fase_c_travada.py` — é a única mudança que remove uma invariante de
  segurança do projeto, então tem revisor nomeado e não entra por squash silencioso.
- **Antes de C2:** revisão das primeiras escritas (idempotência, reversibilidade,
  log).
- **Contínuo:** toda adição à lista de caminhos e ao escopo é PR com procedência.

## 8. Riscos (estilo `docs/RISCOS.md`)
- **R-C1 — Escopo furado (probe em host de terceiro).** *Mitig.:* escopo estrutural
  + teste de recusa com alvo plantado + reúso da fronteira de rede.
- **R-C2 — Achado vira exploração.** *Mitig.:* detectar-e-reportar como contrato de
  módulo; teste que prova que o corpo não é lido além do limite.
- **R-C3 — Vazamento de segredo no laudo.** *Mitig.:* mascaramento por valor já
  existente, estendido ao log de auditoria; teste de vazamento (irmão de
  `test_vazamento_de_credencial.py`).
- **R-C4 — Ruído/carga no alvo próprio.** *Mitig.:* rate limit, `HEAD`-first, teto,
  kill-switch, backoff.
- **R-C5 — Trava reaberta sem revisão.** *Mitig.:* inversão do teste de trava é
  checkpoint de governança nomeado.

## 9. Definition of Done
- As três invariantes do §0 têm cada uma um teste que reprova quando violada
  (detector provado com violação plantada, como o resto da suíte).
- `ruff` e `bandit` limpos; verificação verde; escopo-refusal e rate-limit cobertos
  sem tocar rede.
- Laudo mostra fase+severidade+remediação como dado.
- Autorização escrita registrada para cada alvo do escopo.

---

## Recomendações aplicadas (para a avaliação dos analistas)

[RECOMENDAÇÃO] Histórias de Usuário: avaliar se as histórias de usuário (HU-C1..C4)
seguem INVEST — Independente, Negociável, Valiosa, Estimável, Pequena, Testável — e
se cada uma tem critérios de aceitação bem definidos.
_Fonte: Engenharia de Requisitos em Sistemas de Informações — Enock Godoy de Souza_

[RECOMENDAÇÃO] Requisitos Não Funcionais: verificar explicitamente os RNF de
performance, segurança, usabilidade e escalabilidade (§3.2) e apontar gaps entre o
que o plano promete e os SLAs/limiares que a implementação vai precisar honrar.
_Fonte: Engenharia de Requisitos em Sistemas de Informações — Enock Godoy de Souza_
