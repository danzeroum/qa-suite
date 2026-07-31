"""Área autenticada: mais superfície para os mesmos checks passivos (OS-38).

A landing page de um produto é revisada por muita gente. O painel interno, não —
e é lá que costuma sobrar chave de API em JavaScript, endpoint de serviço interno
e comentário com credencial de homologação. A bateria passiva não muda aqui; o
que muda é **quanto** ela enxerga, porque agora enxerga as telas que só existem
depois do login.

A disciplina do percurso vive em `webqa/navegacao.py` e é provada em
`tests/test_navegacao_autenticada.py`: cada página visitada carrega a
PROVENIÊNCIA do endereço que levou até ela, e página que ninguém linkou não é
alcançada. Adivinhar rota é Fase C, e continua desligada.

Sem credencial no ambiente, `paginas_internas` traz só a entrada (ou nada, se a
etiqueta bloqueou) e estes checks pulam com motivo — ausência de análise nunca
vira atestado de segurança.
"""
import pytest

from webqa.dominio import Finding, find_secrets, registrar_achados
from webqa.navegacao import ENTRADA
from webqa.sanitize import safe_url

pytestmark = [pytest.mark.seguranca, pytest.mark.browser]


def _internas(paginas):
    """Só as páginas alcançadas por link — a entrada já é auditada em outros checks."""
    return [p for p in paginas if p.veio_de_link and p.status == 200]


def test_paginas_internas_sem_segredo_em_claro(paginas_internas, request):
    """Segredo em tela interna é o achado que a bateria anônima nunca veria.

    Mesmo motor do `sanitize` das outras fases (ponto único de verdade): o valor
    é reportado MASCARADO — republicá-lo reencenaria o risco que o check existe
    para apontar.
    """
    internas = _internas(paginas_internas)
    if not internas:
        pytest.skip(
            "Nenhuma página interna alcançada por link — sem credencial, sem área "
            "logada, ou a etiqueta do alvo bloqueou o percurso.")

    achados = []
    for pagina in internas:
        achados.extend(find_secrets(pagina.html, safe_url(pagina.url), fase="A"))

    registrar_achados(request.node.nodeid, achados)
    assert not achados, (
        f"{len(achados)} segredo(s) em página interna:\n"
        + "\n".join(f"  {a.tipo} em {a.recurso} — {a.evidencia}" for a in achados[:5]))


def test_toda_pagina_interna_veio_de_um_link(paginas_internas, request):
    """A fronteira passivo-autenticado × Fase C, verificável no laudo.

    Não é redundante com o teste de unidade: lá a disciplina é provada sobre
    aplicação fabricada; aqui a afirmação é sobre a execução REAL — nenhum
    endereço apareceu sem que outra página visitada o tivesse oferecido.

    A reprovação vira `Finding` de severidade ALTA, e não uma lista de strings,
    porque endereço fabricado contra alvo de terceiro é sondagem: se algum dia
    acontecer, o laudo tem de carregar isso com peso, fase e valor sanitizado —
    não como uma mensagem de assert que o relatório recebe sem classificação.
    """
    if not paginas_internas:
        pytest.skip("Percurso autenticado não produziu páginas (ver motivo da etiqueta).")

    conhecidas = {p.url for p in paginas_internas}
    achados = []
    for pagina in paginas_internas:
        if pagina.origem == ENTRADA:
            continue
        procedencia = pagina.origem.removeprefix("link em ")
        if procedencia not in conhecidas:
            achados.append(Finding(
                tipo="navegacao:endereco-sem-proveniencia",
                recurso=safe_url(pagina.url),
                severidade="alta",
                evidencia=f"visitada sem link de origem entre as páginas vistas "
                          f"(alegou vir de {safe_url(procedencia)})",
                fase="A"))

    registrar_achados(request.node.nodeid, achados)
    assert not achados, (
        "Página visitada cuja origem não é outra página visitada — endereço "
        "fabricado, e isso é sondagem:\n"
        + "\n".join(f"  {a.recurso} — {a.evidencia}" for a in achados))
