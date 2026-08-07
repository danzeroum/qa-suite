# Contrato de Régua — v1

> **O `WEBQA_CONSUMER_CONTRACT.md` diz o que este consumidor promete à suíte.**
> **Este documento diz o que uma suíte precisa entregar para ser consumível.**

A assimetria era o buraco. Havia um contrato escrito, normativo e fiscalizado — e ele cobria
apenas um lado. Do outro lado não havia onde um defeito da régua aparecer, e defeito sem lugar
onde aparecer é indistinguível de ausência de defeito. Os cinco itens abaixo são o outro lado.

Uma suíte entra neste projeto por **ficha** (`harness/suites/<nome>.yaml`, validada por
`harness/schemas/suite-registry.schema.json`) e por **pin** (o caminho declarado em `pin_source`).
Não por código. Se acrescentar uma régua exigir editar um fiscal, a padronização não aconteceu.

## Por que a v1 é fechada

Um contrato de rastreabilidade não-rastreável seria a ironia que este molde já foi, até o ADR-015
lhe dar versão. A v1 é fechada por `contract-manifest.json`: cada arquivo do contrato entra lá com
seu `sha256`, e `ci/audit_suites.py` confere. A âncora é o **digest**, não o nome da pasta — pela
mesma razão que `target.lock` guarda `manifest_sha` além da tag, e que o `README` de
`harness/releases/` repete: tag é ponteiro móvel; digest não é.

### O que o contrato fixa, e o que ele deliberadamente não fixa

O manifesto fixa o **texto normativo**, o **envelope de laudo**, o **schema do próprio manifesto**
e o **motor de mutação**. Ele **não** fixa `harness/schemas/suite-registry.schema.json`, e a
ausência é uma decisão, não um esquecimento.

O contrato governa a interface **suíte ↔ consumidor**: o que a régua entrega. O **registro** é
como *este* consumidor anota o lado dele — outro projeto consumindo a mesma régua teria registro
com outra forma, e continuaria honrando a contract-v1 integralmente. Fixar o registro aqui
confundiria as duas coisas: qualquer evolução na maneira de *declarar* uma suíte passaria a exigir
versão nova do **contrato**, como se a promessa da régua tivesse mudado quando só a nossa ficha
mudou.

O registro não fica desprotegido por isso: `ADR-030-A2` e `ADR-030-A3` travam por ponteiro os
campos que importam (`env_prefix` obrigatório, `contract_version` como enum fechado), a prova de
mutação exige que essas travas mordam, e ele segue sob `CODEOWNERS`.

Acrescentar uma sexta cláusula é a **v2**, nunca uma edição da v1. O schema trava isso com
`minItems: 5` e `maxItems: 5` — sem a trava, o contrato mudaria de conteúdo sem mudar de nome, e
uma ficha que declara `contract_version: v1` passaria a prometer outra coisa sem que ninguém
tivesse decidido nada.

---

## Cláusula 1 — pin de fonte única

A versão exata da régua mora em **um** arquivo, e a ficha declara **onde**, jamais **qual**.

É o ADR-003 aplicado à classe inteira em vez de a uma régua só. `pin_source` é caminho; o schema
proíbe URL no campo, porque um endereço ali restataria a origem da régua num arquivo sob
`harness/`, que o `ADR-008-A5` já recusa por outro motivo e pela mesma lógica.

Espelho é tolerado **apenas** onde já declarado e **sob igualdade verificada** — hoje,
`tests/qa/config.yaml:standard_version`, conferido por `ci/validate_metadata.py` (I2/I3).

> Falha como: ficha que restata versão, ou `pin_source` que não resolve ⇒ achado bloqueante.

## Cláusula 2 — release com manifesto

A régua publica versões **ancoráveis**: uma release com manifesto, cujo digest o consumidor possa
guardar. Generaliza o que `ci/mold_release.py` faz para o molde.

`release.anchored: false` é resposta **legítima e cara**: exige um `gap` aberto cobrindo esta
cláusula. Sem o gap, o fiscal reprova. *"Ainda não"* declarado é dívida com data; *"ainda não"*
calado é a lacuna que ninguém volta a olhar.

> Falha como: `anchored: false` sem gap correspondente, ou `manifest_sha` que não bate ⇒ achado.

## Cláusula 3 — envelope de laudo com três estados

O laudo declara **`conforme`**, **`nao_conforme`** ou **`inconclusivo`**.

O terceiro estado é a cláusula inteira. Hoje, quando a suíte não está instalada, o passo emite
`::warning::` e sai **0** — *"não consegui medir"* e *"medi e está bom"* saem com a mesma cor, e a
cor mais barata vence por hábito. Um verde que significa "não olhei" encerra a investigação com a
convicção de quem olhou.

O envelope é `harness/schemas/report.schema.json` na versão **1.3**, **aditiva**: um laudo `1.0`
segue válido sem `verdict`, e nenhuma evidência existente vira inválida por uma versão nova de
schema — o idioma que `provenance.schema.json` já usa em `1.1` e `1.2`. É o que permite a qa-suite
seguir emitindo `1.0` enquanto o gap `envelope` está aberto, sem que o contrato precise mentir.

O schema trava as duas direções: `suite_not_installed` e `error` **só** podem ser `inconclusivo`;
`conforme` **só** pode acompanhar `result: ok`. Sem a segunda, a trava valeria contra o descuido e
nunca contra o gesto deliberado.

> Falha como: laudo que não distingue os três estados, ou `verdict` incoerente com `result` ⇒
> achado, e o runner traduz `inconclusivo` para não-conforme perante o CI.

## Cláusula 4 — fingerprint de comparabilidade

Todo laudo carrega `(name, version, commit, catalog_hash, schema_version)`.

Sem os cinco, dois laudos não são comparáveis e a diferença entre eles não significa nada.
`catalog_hash` generaliza o `sensitive_paths_hash` da procedência: é o digest da lista curada que a
régua aplica — a lista da qa-suite, o léxico de uma suíte de privacidade. Hashes divergentes na
**mesma** versão significam lista editada, que é precisamente o que a cláusula existe para revelar.

Fingerprints diferentes produzem **`not_comparable`** — nunca uma comparação silenciosa.

> Falha como: campo de fingerprint ausente ⇒ achado; fingerprints distintos comparados como iguais
> ⇒ achado.

## Cláusula 5 — autoprova de mordida, declarada no manifesto

Cada cláusula acima declara, em `contract-manifest.json`, **como seria negada** e **qual achado**
isso deve produzir.

`ci/audit_suites.py` aplica a mutação declarada, exige o achado específico, e **reprova a si
mesmo** (`FISCAL-SEM-AUTOPROVA`) se qualquer cláusula chegar sem mutação canônica. É o padrão do
CP-030 virado sobre o contrato: um fiscal que não sabe como seria negado não sabe se está
funcionando.

Exigir o achado **específico**, e não apenas "algum vermelho", é o que impede a autoprova de ser
satisfeita por um erro não relacionado — o modo de falha que `harness/policies/prova-de-mutacao.md`
descreve como *o acordo entre a mutação e a asserção que pode não ser sobre o mundo*.

O motor que aplica essas mutações é `harness/suite-contract/mutation-engine/`, **consumido por pin**
(`sha256` no manifesto), nunca copiado. Uma cópia local poderia ter um operador enfraquecido, e a
prova passaria a dizer "todas mordem" sem erro nem aviso — o selo falso que é pior que fiscal
nenhum, porque encerra a investigação.

> Falha como: cláusula sem `canonical_mutation` ⇒ o próprio fiscal sai 1, antes de julgar suite
> alguma.

---

Fiscalizado por: `ci/audit_suites.py`, `harness/schemas/suite-registry.schema.json`, `harness/schemas/suite-contract-manifest.schema.json`, `harness/schemas/report.schema.json`
Declarado em: `harness/change-proposals/CP-041-contrato-de-regua.yaml`
Falha como: cláusula sem asserção resolvível, ou sem mutação canônica declarada, ⇒ exit 1 com o fiscal reprovando a si mesmo.
