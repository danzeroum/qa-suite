"""Métricas DO ALVO medidas na execução — registradas passem ou falhem os testes.

Até aqui, TTFB/FCP/LCP/CLS existiam apenas dentro da mensagem do `assert`: quando
o teste passava, o número medido era descartado. Um veredito binário não diz se o
TTFB ficou em 90ms ou em 790ms contra um orçamento de 800ms — e é justamente essa
diferença que separa "folgado" de "à beira de estourar". Sem o número, comparar
alvos ou observar tendência entre execuções é impossível.

Separação de papéis, deliberada:

* este módulo registra **medida** — o que o alvo entregou;
* o teste continua dono do **veredito** — o orçamento de config.yaml.

Registrar não afrouxa nem endurece limite nenhum. Estado de módulo é aceitável
aqui pelo mesmo motivo que em webqa/report.py: o ciclo de vida é a sessão pytest,
e quem consome (scripts/campanha.py) lê o artefato, não a memória.
"""
from __future__ import annotations

# Nomes canônicos das medidas. O sufixo carrega a unidade porque o consolidado é
# lido por humanos, e "ttfb: 412" sem unidade convida ao erro de interpretação.
# `cls` não tem sufixo: é adimensional por definição do Web Vitals.
_MEDIDAS: dict[str, float] = {}


def registrar(nome: str, valor: float | None) -> None:
    """Guarda uma medida do alvo.

    `None` NÃO entra. Métrica que o navegador não emitiu (LCP em página sem
    conteúdo candidato, FCP em documento sem pintura) é ausência, e ausência não
    é zero: gravada como 0 ela apareceria no consolidado como "instantâneo",
    puxando a mediana para baixo e transformando falta de dado em elogio ao alvo.
    Ausência precisa aparecer como amostra que falta — é o que o consolidador lê.

    Valor não numérico é descartado em silêncio pelo mesmo motivo que o
    inventário ilegível não derruba o relatório: instrumentação não pode ser a
    causa de uma execução perdida.
    """
    if valor is None:
        return
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return
    _MEDIDAS[nome] = round(numero, 3)


def coletadas() -> dict[str, float]:
    """Cópia das medidas da execução — consumida por webqa/report.py."""
    return dict(_MEDIDAS)


def limpar() -> None:
    """Zera o registro. Existe para os testes da própria suíte não vazarem
    medida de um caso para o outro."""
    _MEDIDAS.clear()
