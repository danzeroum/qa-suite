"""axe-core: obtenção verificada e resumo de violações.

Vive em `webqa/` porque **dois** checks o consomem — a acessibilidade do tema
claro (`checks/ux/test_acessibilidade.py`) e o contraste do tema escuro
(`checks/gui/test_preferencias.py`). Duas cópias do par versão+hash
divergiriam no primeiro dia em que alguém atualizasse uma delas, e a divergência
apareceria como um check injetando 4.9.1 e o outro 4.10 — com a régua mudando
de lugar entre dois testes que o laudo apresenta lado a lado.

**O hash é controle de segurança, não número de versão.** A versão é fixada e o
SHA-384 conferido ANTES da injeção: um CDN comprometido não roda script
arbitrário no DOM da página sob teste. Divergência de hash é ERRO, nunca skip —
skip aqui transformaria comprometimento de CDN em "não deu para medir".

Somente stdlib (`hashlib`); o cliente HTTP vem por parâmetro.
"""
from __future__ import annotations

import hashlib

# Versão FIXADA + hash SHA-384 verificado antes de injetar (SRI manual).
AXE_CDN = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.9.1/axe.min.js"
AXE_SHA384 = ("b91444cffa692592290e122db68c9b6953d29714"
              "bb3457b5b423a41f741597e1f778cd9a2fdd1ad78d32cd829887c4c0")


def baixar_axe_verificado(client) -> str:
    """Baixa o axe-core e valida integridade; falha de hash é ERRO, não skip.

    A distinção importa: rede indisponível é ausência de medida (o chamador
    pula, com motivo). Hash divergente é o CDN entregando outra coisa — e tratar
    isso como "não deu para medir" esconderia exatamente o evento que a
    verificação existe para detectar.
    """
    resposta = client.get(AXE_CDN)
    resposta.raise_for_status()
    digest = hashlib.sha384(resposta.content).hexdigest()
    assert digest == AXE_SHA384, (
        f"Integridade do axe-core FALHOU (sha384 {digest[:16]}… != esperado) — "
        "possível comprometimento do CDN; script NÃO foi injetado."
    )
    return resposta.text


def violacoes_por_impacto(resultado: dict, impacto: str) -> list[dict]:
    """Violações do `axe.run` com o impacto pedido (`critical`, `serious`…)."""
    return [v for v in (resultado.get("violations") or []) if v.get("impact") == impacto]


def resumo_de_violacoes(violacoes, teto: int = 10) -> str:
    """Regra, quantos nós e o primeiro seletor — o suficiente para agir.

    O `data` do axe traz o par de cores e a razão medida quando a regra é
    `color-contrast`; ele entra porque "contraste insuficiente" sem os números
    não diz quanto falta, e quem corrige precisa saber se erra por pouco ou por
    muito.
    """
    linhas = []
    for violacao in violacoes[:teto]:
        nos = violacao.get("nodes") or []
        alvo = ""
        if nos:
            alvos = nos[0].get("target") or []
            alvo = str(alvos[0]) if alvos else ""
        linhas.append(f"  {violacao.get('id')} — {len(nos)} nó(s)"
                      + (f", ex.: {alvo}" if alvo else ""))
        detalhe = _detalhe_de_contraste(nos[0] if nos else {})
        if detalhe:
            linhas.append(f"      {detalhe}")
    if len(violacoes) > teto:
        linhas.append(f"  … e mais {len(violacoes) - teto}")
    return "\n".join(linhas)


def _detalhe_de_contraste(no: dict) -> str:
    """Par de cores e razão medida, quando o nó os traz."""
    for grupo in ("any", "all", "none"):
        for verificacao in no.get(grupo) or []:
            dados = verificacao.get("data") or {}
            if "contrastRatio" in dados:
                return (f"razão {dados['contrastRatio']}:1 "
                        f"(texto {dados.get('fgColor')} sobre {dados.get('bgColor')}, "
                        f"exigido {dados.get('expectedContrastRatio')})")
    return ""
