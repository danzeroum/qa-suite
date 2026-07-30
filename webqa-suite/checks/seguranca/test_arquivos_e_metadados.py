"""Fase B — o que os arquivos baixados revelam além do que serviam para servir.

Ver `docs/SEGURANCA.md` §6. Opera sobre corpos **já baixados** por `ler_corpo`:
nenhum download novo acontece aqui. Recurso que não está na `network_log`
simplesmente não foi navegado, e ir buscá-lo é sondagem — Fase C, atrás do gate.

É o que separa esta bateria de um scanner: um scanner pergunta ao servidor o que
ele não ofereceu; aqui só se lê o que ele já entregou ao visitante.
"""
from __future__ import annotations

import pytest

from webqa.dominio import (
    assinatura,
    ler_corpo,
    metadados_exif,
    metadados_pdf,
    sourcemap_referenciado,
    svg_executavel,
)

pytestmark = [pytest.mark.seguranca, pytest.mark.browser]

# Extensão declarada → formato que o conteúdo deveria ter.
FORMATO_POR_EXTENSAO = {
    ".pdf": "pdf", ".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg",
    ".gif": "gif", ".zip": "zip", ".webp": "webp",
}


def _extensao(url: str) -> str:
    caminho = url.split("?")[0].split("#")[0]
    ponto = caminho.rfind(".")
    return caminho[ponto:].lower() if ponto > caminho.rfind("/") else ""


def _corpos(network_log, sufixos=None, tipos=None):
    """(recurso, corpo) dos que casam por extensão OU content-type, já lidos."""
    for recurso in network_log.recursos:
        if recurso.status >= 400:
            continue
        casa = ((sufixos and _extensao(recurso.url) in sufixos)
                or (tipos and recurso.content_type in tipos))
        if casa:
            yield recurso, ler_corpo(recurso)


def test_formato_real_corresponde_a_extensao(network_log):
    """Magic bytes × extensão declarada — FAIL.

    O nome do arquivo é declaração de quem o subiu; os primeiros bytes são o que
    ele é. Divergência indica upload sem validação de tipo no servidor — a porta
    por onde entra arquivo executável disfarçado de imagem.
    """
    divergentes, nao_avaliados = [], []
    for recurso, corpo in _corpos(network_log, sufixos=set(FORMATO_POR_EXTENSAO)):
        if not corpo.avaliavel:
            nao_avaliados.append(f"{recurso.url} ({corpo.motivo})")
            continue
        esperado = FORMATO_POR_EXTENSAO[_extensao(recurso.url)]
        real = assinatura(corpo.dados)
        if real and real != esperado:
            divergentes.append(f"{recurso.url}: extensão diz {esperado}, conteúdo é {real}")

    if nao_avaliados and not divergentes:
        pytest.xfail("Não avaliado: " + "; ".join(nao_avaliados[:3]))
    assert not divergentes, (
        f"{len(divergentes)} arquivo(s) com formato divergente da extensão:\n  "
        + "\n  ".join(divergentes[:5]))


def test_svg_sem_conteudo_executavel(network_log):
    """SVG com `<script>`, `on*=` ou `href javascript:` — FAIL.

    SVG não é imagem inerte: é documento com DOM. Servido a partir do próprio
    domínio, executa no contexto de origem do alvo — é XSS armazenado com cara
    de avatar.
    """
    executaveis = []
    for recurso, corpo in _corpos(network_log, sufixos={".svg"},
                                  tipos={"image/svg+xml"}):
        if not corpo.avaliavel:
            continue
        motivos = svg_executavel(corpo.dados)
        if motivos:
            executaveis.append(f"{recurso.url}: {', '.join(motivos)}")
    assert not executaveis, (
        f"{len(executaveis)} SVG(s) com conteúdo executável:\n  "
        + "\n  ".join(executaveis[:5])
        + "\nSVG servido do próprio domínio executa no contexto de origem do alvo.")


def test_imagens_sem_coordenada_de_gps(network_log):
    """EXIF-GPS numa imagem publicada — FAIL.

    Coordenada é dado pessoal sensível por consequência: revela onde a foto foi
    tirada, e em foto de pessoa revela onde a pessoa estava. Só a PRESENÇA é
    reportada; a suíte não extrai o valor (minimização — docs/SEGURANCA.md §6).
    """
    com_gps = []
    for recurso, corpo in _corpos(network_log, sufixos={".jpg", ".jpeg"},
                                  tipos={"image/jpeg"}):
        if corpo.avaliavel and "gps" in metadados_exif(corpo.dados):
            com_gps.append(recurso.url)
    assert not com_gps, (
        f"{len(com_gps)} imagem(ns) publicadas com coordenada GPS no EXIF: "
        f"{com_gps[:5]}. A coordenada NÃO é reproduzida aqui de propósito — "
        "republicá-la reencenaria a exposição. Remova o EXIF na publicação.")


def test_metadados_de_autoria_removidos_na_publicacao(network_log):
    """Autor/ferramenta em imagem ou PDF — xfail.

    Identifica quem produziu e com quê (útil para reconhecimento de alvo), mas
    não localiza ninguém: é higiene de publicação, não violação.
    """
    com_autoria = []
    for recurso, corpo in _corpos(network_log,
                                  sufixos={".jpg", ".jpeg", ".pdf"},
                                  tipos={"image/jpeg", "application/pdf"}):
        if not corpo.avaliavel:
            continue
        achados = metadados_exif(corpo.dados) | metadados_pdf(corpo.dados)
        if achados - {"gps"}:
            com_autoria.append(f"{recurso.url} ({', '.join(sorted(achados - {'gps'}))})")
    if com_autoria:
        pytest.xfail(
            f"{len(com_autoria)} arquivo(s) publicados com metadado de autoria: "
            f"{com_autoria[:5]}. Só a presença é reportada; o valor não é lido.")


def test_sourcemaps_nao_referenciados_em_producao(network_log):
    """`//# sourceMappingURL` num bundle — xfail, e o `.map` NÃO é baixado.

    A referência entrega o caminho do código-fonte. Confirmar se o `.map` está
    publicado exigiria uma requisição que o navegador não fez — sondagem, logo
    Fase C, atrás de `WEBQA_ACTIVE_PROBES_AUTHORIZED`. O relatório aponta o
    caminho e para aí.
    """
    referencias = []
    for recurso, corpo in _corpos(network_log, sufixos={".js"},
                                  tipos={"application/javascript", "text/javascript"}):
        if not corpo.avaliavel:
            continue
        mapa = sourcemap_referenciado(corpo.dados)
        if mapa:
            referencias.append(f"{recurso.url} → {mapa}")
    if referencias:
        pytest.xfail(
            f"{len(referencias)} bundle(s) referenciando sourcemap: {referencias[:5]}. "
            "O .map NÃO foi baixado (seria sondagem — Fase C). Se ele estiver "
            "publicado, entrega o código-fonte original.")


def test_assets_de_terceiro_declaram_sri(network_log, soup):
    """`integrity` em script/link de terceiro — xfail.

    Sem SRI, o alvo executa o que o CDN mandar hoje e o que mandar amanhã. Lê o
    ATRIBUTO do HTML, não a resposta: a violação existe mesmo com o CDN fora do ar.
    """
    externos = []
    for tag in soup.find_all(["script", "link"]):
        origem = tag.get("src") or tag.get("href") or ""
        if not origem.startswith(("http://", "https://")):
            continue
        if tag.name == "link" and "stylesheet" not in (tag.get("rel") or []):
            continue
        if not tag.get("integrity"):
            externos.append(origem)
    if externos:
        pytest.xfail(
            f"{len(externos)} recurso(s) de terceiro sem atributo integrity (SRI): "
            f"{externos[:5]}. Sem SRI, alteração no CDN executa no seu domínio.")
