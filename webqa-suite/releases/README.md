# releases/ — a raiz de confiança das versões do padrão

Cada arquivo aqui é o manifesto de uma release: `vX.Y.Z.manifesto.json`, emitido e conferido por
[`../scripts/publicar_release.py`](../scripts/publicar_release.py), cobrado por
`../tests/test_release.py`.

O contrato do manifesto mora no emissor, não num schema separado: só stdlib, e um único lugar
que sabe emitir e conferir. Schema num arquivo à parte que ninguém valida seria decoração — a
mesma classe de defeito que este diretório existe para fechar.

## Por que existe

O consumidor declara a régua por **versão** (`webqa-suite==1.0.0`, `auditar.yml@v1.0.0`). Para
que "versão" signifique algo verificável, ela precisa de uma âncora que **não seja a própria
tag**: tag é ponteiro móvel, e ponteiro móvel não ancora nada. Sem manifesto, *"continua sendo o
que eu instalei"* é indemonstrável — que é exatamente o gap `GAP-QA-TAG` que o consumidor tinha
declarado contra este repositório.

## Por que na árvore Git, e não como asset da release

Um asset é editável depois de publicado e a edição não deixa rastro no histórico. Um arquivo na
árvore do commit taggeado é endereçado por hash junto com todo o resto: **mover a tag muda o
manifesto que se encontra no destino**, e o digest guardado do outro lado deixa de conferir. É o
que transforma "a tag foi movida" de evento invisível em falha.

## O manifesto declara o PAI, e isso é deliberado

`commit_sha` é o commit **cujo conteúdo foi validado** — o pai do commit de release. Um arquivo
não pode conter o hash do commit que o contém; declarar o pai é a formulação honesta. O elo que
fecha o buraco é `publicar_release.py --verificar`, que exige que o commit de release **não mude
nada além deste manifesto**: sem isso, conteúdo não validado entraria na versão sob a bandeira de
uma validação que rodou no pai.

## A trava que impede a versão de mentir

A versão do pacote é **dinâmica**, vinda de `webqa.__version__` (`pyproject.toml`,
`tool.setuptools.dynamic`). Uma tag `vX.Y.Z` cortada numa árvore cujo `__version__` não seja
`X.Y.Z` produziria um wheel com **outro** número — e dois conteúdos diferentes passariam a
reivindicar a mesma versão. O publicador recusa antes de criar qualquer ref:

```
publicar_release.py --versao 1.0.0 --commit <sha>
  ├─ a árvore de <sha> declara __version__ == 1.0.0?   senão: recusa
  ├─ a tag v1.0.0 já existe?                            se sim: recusa
  ├─ o manifesto já está na árvore de <sha>?            se sim: recusa
  ├─ emite releases/v1.0.0.manifesto.json
  ├─ commit de release (só o manifesto) + tag LOCAL
  └─ --verificar sobre esses objetos, ANTES de qualquer push
```

Qualquer passo vermelho e nenhuma ref nasce. Tag que aponta para commit sem manifesto não é
release parcial — é **ausência de release**.

## E depois da tag, o bump

Cortada a tag, `main` **precisa** sair de `X.Y.Z`. Enquanto não sair, dois conteúdos distintos —
o taggeado e a ponta — dizem ter a mesma versão, e a comparabilidade de laudos que a versão existe
para dar deixa de valer sem que nada fique vermelho. `tests/test_release.py` cobra isso: o
`__version__` da ponta não pode ser igual ao da última release publicada.

## O que o manifesto ancora

| campo | o que ancora |
|---|---|
| `commit_sha` | o conteúdo validado (o pai do commit de release) |
| `tree_digest` | *esta árvore é aquela árvore*, sem confiar na tag (`git archive` canônico) |
| `catalogo.caminhos_sensiveis_hash` | a lista curada que a sondagem aplica — lista encurtada em segredo produz "nenhum achado" indistinguível de alvo seguro |
| `catalogo.checks_hash` | o catálogo de checks: quais dimensões, quais nodeids. Dois laudos "0 achados" sob catálogos diferentes não se comparam |
| `mordida` | se as travas desta release foram provadas mordendo (entrega 5). `pendente` **com motivo** enquanto a autoprova não existir |

`mordida.estado` só admite `pendente` e `aprovada`. Um enum com `reprovada` criaria a categoria
"release publicada com autoprova vermelha" — categoria que, existindo, será usada.
