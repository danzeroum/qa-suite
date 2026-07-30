"""Fase A — cabeçalhos por ASSET, mixed content e tipo declarado × real.

Ver `docs/SEGURANCA.md` §5. Tudo aqui é passivo: opera sobre o que o navegador
já baixou (`network_log.recursos`), sem uma requisição nova sequer.

O recorte deliberado é **por asset, não pelo HTML principal**. Os cabeçalhos do
documento já são cobertos por `checks/backend/test_security_headers.py`, e
repetir a mesma asserção aqui inflaria a contagem sem informação nova. O que
nenhuma outra dimensão vê é o script de terceiro pelado servido dentro de uma
página blindada — o elo fraco de uma cadeia que parece forte.

Os checks que reprovam emitem `Finding` (docs/SEGURANCA.md §8); o que informa
segue `xfail` e não produz achado. Severidade **alta** nos dois FAILs daqui pelo
mesmo critério: em ambos o risco se realiza no navegador do titular sem depender
de nenhuma outra condição — o conteúdo adulterado em trânsito já chegou, e o
executável mal declarado já está sendo interpretado.
"""
from __future__ import annotations

import pytest

from webqa.dominio import Finding, ler_corpo, parece_html, registrar_achados

pytestmark = [pytest.mark.seguranca, pytest.mark.browser]

# Tipos que o navegador EXECUTA ou interpreta com poder — é neles que a ausência
# de cabeçalho tem consequência, e não numa imagem.
EXECUTAVEIS = ("application/javascript", "text/javascript", "application/x-javascript",
               "module", "application/json", "text/html")


def _executaveis(recursos) -> list:
    return [r for r in recursos if r.content_type in EXECUTAVEIS and r.status < 400]


def test_assets_de_terceiro_declaram_nosniff(network_log):
    """`X-Content-Type-Options: nosniff` em asset executável de terceiro.

    xfail e não FAIL: a ausência é maturidade do TERCEIRO, e o controlador do
    alvo muitas vezes não manda no servidor dele. O que ele pode fazer — e o
    relatório informa — é escolher outro fornecedor ou hospedar localmente.
    """
    terceiros = [r for r in _executaveis(network_log.recursos) if not r.from_origin]
    if not terceiros:
        pytest.skip("Nenhum asset executável de terceiro foi carregado.")
    pelados = [r.url for r in terceiros if r.cabecalho("x-content-type-options") != "nosniff"]
    if pelados:
        pytest.xfail(
            f"{len(pelados)} asset(s) executáveis de terceiro sem "
            f"X-Content-Type-Options: nosniff — {pelados[:3]}. Sinal de maturidade "
            "do fornecedor; sem obrigação legal direta sobre o alvo."
        )


def test_sem_mixed_content(network_log, request):
    """Asset `http://` numa página `https://` — FAIL sem atenuante.

    Vale só quando o alvo é https: num alvo http NADA é mixed content, e cobrar
    isso ali seria inventar violação. URL protocol-relative (`//host/x.js`) herda
    o esquema da página, então nunca é mixed content — e é justamente o caso em
    que uma verificação ingênua por "começa com http" erra.
    """
    if not network_log.url.lower().startswith("https://"):
        pytest.skip("Alvo servido por http:// — mixed content não é aplicável.")
    achados = [Finding(tipo="mixed-content", recurso=r.url, severidade="alta",
                       evidencia=f"carregado por {r.scheme}:// numa página https://",
                       fase="A")
               for r in network_log.recursos if r.scheme == "http"]

    registrar_achados(request.node.nodeid, achados)
    assert not achados, (
        f"{len(achados)} recurso(s) carregados por http:// numa página https:// "
        f"(mixed content):\n  " + "\n  ".join(str(a) for a in achados[:5])
        + "\nO conteúdo trafega em claro e pode ser adulterado em trânsito, "
          "anulando o TLS da página."
    )


def test_tipo_declarado_corresponde_ao_conteudo(network_log, request):
    """`Content-Type` que mente sobre o corpo — FAIL.

    O caso que importa: um `.js` devolvido como página HTML (fallback de erro,
    SPA mal configurada). O servidor declara executável o que é documento, ou o
    contrário — e o navegador decide sozinho o que fazer com isso.

    Corpo acima do teto vira "não avaliado", nunca PASS: teto de memória não é
    atestado de conformidade (docs/SEGURANCA.md §2.4).
    """
    javascripts = [r for r in network_log.recursos
                   if r.status < 400
                   and (r.content_type in ("application/javascript", "text/javascript")
                        or r.url.split("?")[0].endswith(".js"))]
    if not javascripts:
        pytest.skip("Nenhum recurso JavaScript no carregamento.")

    achados, nao_avaliados = [], []
    for recurso in javascripts:
        corpo = ler_corpo(recurso)
        if not corpo.avaliavel:
            nao_avaliados.append(f"{recurso.url} ({corpo.motivo})")
            continue
        declarado = recurso.content_type or "sem Content-Type"
        declarado_js = recurso.content_type in ("application/javascript", "text/javascript")
        # A evidência é o PAR (declarado, observado) — nunca um trecho do corpo.
        # Um pedaço de HTML no laudo seria conteúdo do alvo republicado sem
        # necessidade: o par já é a prova, e é tudo o que o leitor precisa.
        if parece_html(corpo.dados):
            achados.append(Finding(
                tipo="tipo-declarado-divergente", recurso=recurso.url, severidade="alta",
                evidencia=f"corpo é HTML, servido como {declarado}", fase="A"))
        elif recurso.url.split("?")[0].endswith(".js") and not declarado_js:
            achados.append(Finding(
                tipo="tipo-declarado-divergente", recurso=recurso.url, severidade="alta",
                evidencia=f"extensão .js servida como {declarado}", fase="A"))

    if nao_avaliados and not achados:
        pytest.xfail("Não avaliado (corpo acima do teto ou indisponível): "
                     + "; ".join(nao_avaliados[:3]))
    registrar_achados(request.node.nodeid, achados)
    assert not achados, (
        f"{len(achados)} recurso(s) com tipo declarado divergente do conteúdo:\n  "
        + "\n  ".join(str(a) for a in achados[:5])
        + "\nServidor mentindo sobre o tipo faz o navegador adivinhar — e adivinhar "
          "é onde mora o content-sniffing malicioso."
    )
