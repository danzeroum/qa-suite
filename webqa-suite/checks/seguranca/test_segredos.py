"""Fase A — credenciais expostas nos corpos servidos pelo próprio alvo.

Ver `docs/SEGURANCA.md` §5. O escopo é deliberadamente **primeira parte**: uma
chave num bundle de terceiro é problema do terceiro e o controlador não tem como
removê-la; uma chave no `app.js` do próprio alvo é dele, e é acionável hoje.

Contrato inviolável: o valor NUNCA aparece. `find_secrets` devolve `Finding`, e
`Finding` sanitiza a evidência no construtor — não há caminho por onde a chave
chegue ao relatório (docs/SEGURANCA.md §2.2, `webqa/dominio.py`).
"""
from __future__ import annotations

import pytest

from webqa.dominio import find_secrets, ler_corpo, registrar_achados, texto_do_corpo

pytestmark = [pytest.mark.seguranca, pytest.mark.browser]

# Onde credencial costuma vazar: código e configuração servidos ao cliente.
TIPOS_VARRIDOS = ("application/javascript", "text/javascript", "application/x-javascript",
                  "application/json", "text/json")


def _varreveis(network_log) -> list:
    return [r for r in network_log.recursos
            if r.from_origin and r.status < 400
            and (r.content_type in TIPOS_VARRIDOS
                 or r.url.split("?")[0].endswith((".js", ".json", ".map")))]


def test_sem_credenciais_em_js_e_json_de_origem(network_log, request):
    """Credencial servida ao navegador é credencial pública — FAIL.

    Qualquer visitante lê o bundle. Uma chave ali não está "escondida no código":
    está publicada, e a única correção é rotacioná-la e movê-la para o servidor.
    """
    recursos = _varreveis(network_log)
    if not recursos:
        pytest.skip("Nenhum JS/JSON de primeira parte no carregamento.")

    achados, nao_avaliados = [], []
    for recurso in recursos:
        corpo = ler_corpo(recurso)
        if not corpo.avaliavel:
            # Não analisado NÃO é limpo. Declarar é o mínimo honesto.
            nao_avaliados.append(f"{recurso.url} ({corpo.motivo})")
            continue
        achados += find_secrets(texto_do_corpo(corpo), recurso.url, fase="A")

    if nao_avaliados and not achados:
        pytest.xfail(
            f"{len(nao_avaliados)} recurso(s) não avaliados — ausência de achado aqui "
            "não é ausência de segredo: " + "; ".join(nao_avaliados[:3]))

    # O relatório precisa da severidade e da fase como DADO, não como texto
    # da mensagem de assert (ver webqa/dominio.py::registrar_achados).
    registrar_achados(request.node.nodeid, achados)
    altas = [a for a in achados if a.severidade == "alta"]
    assert not achados, (
        f"{len(achados)} credencial(is) expostas em recursos do próprio alvo "
        f"({len(altas)} de severidade alta):\n  "
        + "\n  ".join(str(a) for a in achados[:8])
        + "\nO valor está mascarado de propósito: republicá-lo no relatório "
          "reencenaria o vazamento. Rotacione a credencial antes de removê-la do "
          "código — ela já foi servida a todos os visitantes."
    )
