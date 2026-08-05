"""Tema claro × escuro — a pré-checagem que impede o teste de fingir cobertura.

O check de contraste no escuro (`checks/gui/test_preferencias.py`) tem um modo
de falha silencioso e específico: **num alvo sem tema escuro, o navegador
renderiza o tema claro de novo**. O axe roda, não acha nada de novo, e o teste
PASSA — anunciando cobertura de um tema que nunca foi medido.

É a regra 9 de `docs/GUI.md §2.2` ("não avaliado nunca vira PASS") no seu pior
formato, porque aqui o verde é indistinguível do verde legítimo. Daí a
pré-checagem existir e ser obrigatória: sem ela o check é pior que ausente.

**Limite declarado.** A comparação é do fundo do `<body>`. Um alvo que mude
apenas a COR DO TEXTO no escuro, mantendo o fundo, é lido aqui como "sem tema
escuro" e o check pula. É falso negativo conhecido, e a escolha é deliberada:
o fundo é o sinal mais estável (a cor do texto varia por elemento, e comparar
"algum elemento mudou" acusaria qualquer página com `:hover` ou foco), e pular
com motivo é honesto — enquanto medir o tema errado e passar não é.

Somente stdlib.
"""
from __future__ import annotations

# Fundo do `<body>`. `rgba(0, 0, 0, 0)` (transparente) é o que o navegador
# devolve quando ninguém pintou o body — e é um valor legítimo de comparação:
# transparente no claro e `#222` no escuro É uma mudança de tema.
JS_FUNDO_DO_BODY = "() => getComputedStyle(document.body).backgroundColor"


def implementa_tema_escuro(fundo_claro: str, fundo_escuro: str) -> bool:
    """O alvo pinta o fundo de outra cor sob `prefers-color-scheme: dark`?

    Normaliza espaço porque o mesmo valor pode voltar como `rgb(34,34,34)` ou
    `rgb(34, 34, 34)` conforme a engine — e uma diferença de formatação seria
    lida como mudança de tema, invertendo justamente o veredito que esta função
    existe para dar.
    """
    return _normalizar(fundo_claro) != _normalizar(fundo_escuro)


def _normalizar(cor: str) -> str:
    return "".join((cor or "").split()).lower()


def motivo_de_pular(fundo: str) -> str:
    """Mensagem do skip — diz o que foi medido, não só que não deu."""
    return (f"O alvo não implementa tema escuro: o fundo do body é {fundo} nos dois "
            "esquemas. Medir aqui seria rodar o axe no tema claro pela segunda vez "
            "e anunciar cobertura de um tema que não existe. "
            "Limite conhecido: alvo que mude só a cor do TEXTO no escuro também cai "
            "aqui — ver webqa/tema.py.")
