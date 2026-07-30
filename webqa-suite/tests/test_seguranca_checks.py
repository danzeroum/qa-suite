"""VERIFICAÇÃO das Fases A e B da dimensão `seguranca` (docs/SEGURANCA.md §5-6).

Dois níveis, e a divisão não é estética. O alvo fixture é servido por
`http://127.0.0.1`, e três regras da Fase A **não podem ser exercidas ali sem
inventar a violação**:

* mixed content — em página `http` nada é conteúdo misto;
* `Secure` em cookie — o navegador nem aceita o atributo fora de https;
* cabeçalho de terceiro — o único terceiro do fixture é um `.invalid` que nunca
  responde, então não há resposta para inspecionar.

Elas estão declaradas em `fora_do_contrato` no `esperado.json` e cobertas aqui,
por unidade, com log de rede fabricado. Fingir que o fixture as exercita seria
pior que não testá-las: daria confiança falsa sobre a regra mais fácil de errar.
"""
from __future__ import annotations

import pytest

# Importado como MÓDULO, nunca `from ... import test_*`: um nome `test_` no
# namespace deste arquivo seria coletado como teste daqui, e aí o check rodaria
# pedindo a fixture `network_log` de verdade — subindo navegador contra o alvo
# configurado no meio da bateria de verificação, que é offline por definição.
from checks.seguranca import test_arquivos_e_metadados as fase_b
from webqa.dominio import (
    Recurso,
    achados_de,
    assinatura,
    find_secrets,
    limpar_achados,
    metadados_exif,
    metadados_pdf,
    sourcemap_referenciado,
    svg_executavel,
)
from webqa.trackers import NetworkLog

pytestmark = pytest.mark.verification

AKIA = "AKIAIOSFODNN7EXAMPLE"
JWT = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
       "dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk")
PEM = "-----BEGIN PRIVATE KEY-----\nMIIE\n-----END PRIVATE KEY-----"
GITHUB = "ghp_" + "z" * 36


class _Resposta:
    def __init__(self, url, status=200, headers=None, corpo=b""):
        self.url, self.status, self.headers, self._corpo = url, status, headers or {}, corpo

    def body(self):
        return self._corpo


def _log(url_alvo, respostas=(), cookies=()) -> NetworkLog:
    recursos = tuple(Recurso.de_resposta(r, url_alvo) for r in respostas)
    return NetworkLog(url=url_alvo, requests=(), cookies=tuple(cookies), recursos=recursos)


# ---------- find_secrets ----------

@pytest.mark.parametrize("segredo,rotulo", [
    (AKIA, "AWS_ACCESS_KEY_ID"), (JWT, "JWT"), (PEM, "PEM_PRIVATE_KEY"),
    (GITHUB, "GITHUB_TOKEN"),
])
def test_find_secrets_detecta_os_formatos_da_fase_a(segredo, rotulo):
    achados = find_secrets(f"var k = '{segredo}';", "https://a/app.js")
    assert [a.tipo for a in achados] == [f"segredo:{rotulo}"]
    assert achados[0].fase == "A" and achados[0].severidade == "alta"
    assert segredo not in achados[0].evidencia


def test_find_secrets_nao_falsa_positiva_em_sha256():
    sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert find_secrets(f'{{"build": "{sha}"}}', "https://a/meta.json") == []


def test_find_secrets_em_texto_limpo_e_vazio():
    assert find_secrets("function soma(a, b) { return a + b; }", "https://a/x.js") == []


# ---------- Mixed content (o fixture não consegue exercer) ----------

def _mixed(log) -> list[str]:
    """Mesma regra do check: só recurso http:// numa página https://."""
    if not log.url.lower().startswith("https://"):
        return []
    return [r.url for r in log.recursos if r.scheme == "http"]


def test_mixed_content_detectado_em_pagina_https():
    log = _log("https://alvo.example/", [
        _Resposta("http://cdn.terceiro.example/a.js"),
        _Resposta("https://alvo.example/ok.js"),
    ])
    assert _mixed(log) == ["http://cdn.terceiro.example/a.js"]


def test_protocol_relative_herda_https_e_nao_e_mixed_content():
    """Caso da OS: `//host/x.js` numa página https é BAIXADO como https.

    Uma verificação ingênua por "a URL começa com http" acusaria — e este é o
    falso positivo mais provável da regra, porque o HTML fonte diz `//host`.
    O que se observa é a REQUISIÇÃO resolvida, e ela já vem com o esquema herdado.
    """
    log = _log("https://alvo.example/", [_Resposta("https://cdn.terceiro.example/x.js")])
    assert _mixed(log) == []


def test_alvo_http_nao_tem_mixed_content():
    log = _log("http://127.0.0.1:8000/", [_Resposta("http://127.0.0.1:8000/a.js")])
    assert _mixed(log) == []


# ---------- Cookies (regras que o fixture http não exerce) ----------

def _samesite_none_sem_secure(cookies) -> list[str]:
    return [c["name"] for c in cookies
            if str(c.get("sameSite", "")).lower() == "none" and not c.get("secure")]


def test_samesite_none_sem_secure_reprova():
    cookies = [{"name": "sid", "sameSite": "None", "secure": False}]
    assert _samesite_none_sem_secure(cookies) == ["sid"]


def test_samesite_none_com_secure_passa():
    cookies = [{"name": "sid", "sameSite": "None", "secure": True}]
    assert _samesite_none_sem_secure(cookies) == []


def test_samesite_lax_sem_secure_nao_e_o_caso_desta_regra():
    """`Lax` sem `Secure` é outra conversa — esta regra é só sobre `None`."""
    cookies = [{"name": "tema", "sameSite": "Lax", "secure": False}]
    assert _samesite_none_sem_secure(cookies) == []


# ---------- Cabeçalho de terceiro ----------

def test_terceiro_executavel_sem_nosniff_e_identificado():
    log = _log("https://alvo.example/", [
        _Resposta("https://cdn.terceiro.example/a.js", 200,
                  {"Content-Type": "application/javascript"}),
        _Resposta("https://cdn.terceiro.example/b.js", 200,
                  {"Content-Type": "application/javascript",
                   "X-Content-Type-Options": "nosniff"}),
    ])
    pelados = [r.url for r in log.de_terceiros()
               if r.content_type == "application/javascript"
               and r.cabecalho("x-content-type-options") != "nosniff"]
    assert pelados == ["https://cdn.terceiro.example/a.js"]


def test_asset_de_origem_nao_entra_na_regra_de_terceiro():
    log = _log("https://alvo.example/", [
        _Resposta("https://www.alvo.example/app.js", 200,
                  {"Content-Type": "application/javascript"})])
    assert log.de_terceiros() == []
    assert len(log.de_origem()) == 1


# ---------- Fase B: magic bytes, SVG, metadados, sourcemap ----------

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
PDF = b"%PDF-1.7\n/Author (Fulano)\n/Creator (Word)\n"


def test_png_renomeado_para_jpg_e_detectado():
    """Caso da OS: extensão mente, magic bytes não."""
    assert assinatura(PNG) == "png"
    assert assinatura(PNG) != "jpeg", "extensão .jpg não muda o que o arquivo é"


def test_arquivo_integro_casa_com_a_extensao():
    assert assinatura(JPEG) == "jpeg"
    assert assinatura(PDF) == "pdf"


def test_formato_desconhecido_nao_acusa():
    """Texto, JS e JSON não têm assinatura — e ausência não é divergência."""
    assert assinatura(b"function x(){}") == ""
    assert assinatura(b"") == ""
    assert assinatura(None) == ""


@pytest.mark.parametrize("svg,motivo", [
    (b'<svg onload="x()"></svg>', "handler on*= inline"),
    (b"<svg><script>alert(1)</script></svg>", "<script> embutido"),
    (b'<svg><a xlink:href="javascript:alert(1)"/></svg>', "href javascript:"),
    (b'<svg><a href=" javascript:x"/></svg>', "href javascript:"),
])
def test_svg_executavel_detectado(svg, motivo):
    assert motivo in svg_executavel(svg)


def test_svg_limpo_passa():
    assert svg_executavel(b'<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>') == []


def test_svg_com_palavra_script_em_texto_nao_falsa_positiva():
    """`<text>script</text>` é conteúdo, não elemento executável."""
    assert svg_executavel(b"<svg><text>script</text></svg>") == []


def test_metadados_pdf_detecta_presenca_sem_ler_valor():
    achados = metadados_pdf(PDF)
    assert achados == {"autoria", "ferramenta"}
    assert "Fulano" not in str(achados), "só a presença é reportada"


def test_pdf_sem_metadado_nao_acusa():
    assert metadados_pdf(b"%PDF-1.7\n1 0 obj\n") == set()


def test_arquivo_corrompido_nao_derruba_o_parser():
    """Limite que importa: parser que 'chuta' numa bateria de segurança é pior
    que parser nenhum."""
    for lixo in (b"\xff\xd8", b"\xff\xd8\xff\xe1\x00\x02", b"\xff\xd8" + b"\xff" * 40):
        assert metadados_exif(lixo) == set()
    assert metadados_exif(b"nem jpeg e") == set()
    assert metadados_exif(None) == set()


def test_exif_gps_do_alvo_fixture_e_detectado():
    """O JPEG do fixture é construído em stdlib — aqui se prova que ele exerce
    mesmo a violação, e não só parece exercer."""
    from fixture_target.servir import FOTO_GPS, JPEG_BASE
    assert metadados_exif(FOTO_GPS) == {"gps"}
    assert metadados_exif(JPEG_BASE) == set(), "a base limpa não pode acusar"


@pytest.mark.parametrize("corpo,esperado", [
    (b"var a=1;\n//# sourceMappingURL=app.js.map", "app.js.map"),
    (b"var a=1;\n//@ sourceMappingURL=/static/b.map", "/static/b.map"),
    (b"var a=1;", ""),
])
def test_sourcemap_referenciado(corpo, esperado):
    assert sourcemap_referenciado(corpo) == esperado


# ---------- Fase B: os achados chegam ao relatório como DADO ----------
#
# Os checks acima verificam os DETECTORES; estes verificam o que os checks fazem
# com o que detectaram. É a diferença que a OS-28 fechou: antes o achado era a
# string da mensagem de assert, e severidade/fase não existiam como dado — o
# relatório renderizava pelo caminho de retrocompatibilidade, sem selo.
#
# `test_formato_real_corresponde_a_extensao` está em `fora_do_contrato` (o
# fixture não planta binário disfarçado), então esta é a ÚNICA cobertura da
# emissão dele. Sem ela, a regra mais fácil de errar ficaria sem rede.


class _NoFalso:
    def __init__(self, nodeid):
        self.nodeid = nodeid


class _RequestFalso:
    """Só o que os checks usam: `request.node.nodeid`."""

    def __init__(self, nodeid):
        self.node = _NoFalso(nodeid)


def _achados_do_check(check, log, nodeid):
    """Roda o check e devolve os Findings que ele registrou.

    O check REPROVA por construção (é o que se está testando), então o
    AssertionError é esperado e engolido — o que importa é o que ficou
    registrado, não a mensagem.
    """
    limpar_achados()
    try:
        check(log, _RequestFalso(nodeid))
    except AssertionError:
        pass
    return achados_de(nodeid)


def test_svg_executavel_emite_finding_alta():
    log = _log("http://alvo.test", [
        _Resposta("http://alvo.test/logo.svg", headers={"content-type": "image/svg+xml"},
                  corpo=b'<svg onload="x()"></svg>'),
    ])
    achados = _achados_do_check(fase_b.test_svg_sem_conteudo_executavel, log, "svg::x")
    assert len(achados) == 1
    achado = achados[0]
    assert (achado.severidade, achado.fase, achado.tipo) == ("alta", "B", "svg-executavel")
    assert "handler on*= inline" in achado.evidencia


def test_exif_gps_emite_finding_alta_sem_reproduzir_a_coordenada():
    """A coordenada não pode existir no achado — nem mascarada, nem em claro.

    `metadados_exif` devolve o rótulo 'gps', nunca o valor, então não há o que
    mascarar. Este teste fixa isso: se alguém um dia passar o EXIF bruto como
    evidência "para dar mais contexto", o achado passaria a carregar a
    localização — e a suíte reencenaria a exposição que veio apontar.
    """
    from fixture_target.servir import FOTO_GPS

    log = _log("http://alvo.test", [
        _Resposta("http://alvo.test/foto.jpg", headers={"content-type": "image/jpeg"},
                  corpo=FOTO_GPS),
    ])
    achados = _achados_do_check(fase_b.test_imagens_sem_coordenada_de_gps, log, "gps::x")
    assert len(achados) == 1
    achado = achados[0]
    assert (achado.severidade, achado.fase, achado.tipo) == ("alta", "B", "exif-gps")
    assert not achado.contem_segredo_em_claro
    # Nenhum byte do EXIF viaja no achado: a evidência é uma AFIRMAÇÃO sobre o
    # arquivo, não um trecho dele.
    assert FOTO_GPS.decode("latin-1")[:64] not in achado.evidencia


def test_formato_divergente_emite_finding_media():
    """Severidade média, e a distinção importa: validação ausente é sintoma,
    não prova de execução. Alta fica com o que executa (SVG) ou expõe dado
    pessoal (GPS) — senão 'alta' deixa de significar alguma coisa."""
    log = _log("http://alvo.test", [
        _Resposta("http://alvo.test/foto.jpg", headers={"content-type": "image/jpeg"},
                  corpo=PNG),
    ])
    achados = _achados_do_check(fase_b.test_formato_real_corresponde_a_extensao, log, "fmt::x")
    assert len(achados) == 1
    achado = achados[0]
    assert (achado.severidade, achado.fase, achado.tipo) == ("media", "B", "formato-divergente")
    assert "conteúdo é png" in achado.evidencia


def test_alvo_conforme_nao_registra_achado_nenhum():
    """O outro lado do contrato: sem violação, nenhum Finding é registrado.

    Um check que registra achado quando não há transformaria o relatório num
    gerador de ruído — e a seção de achados é justamente o que se lê primeiro.
    """
    log = _log("http://alvo.test", [
        _Resposta("http://alvo.test/ok.svg", headers={"content-type": "image/svg+xml"},
                  corpo=b'<svg><rect/></svg>'),
        _Resposta("http://alvo.test/ok.jpg", headers={"content-type": "image/jpeg"},
                  corpo=JPEG),
    ])
    limpar_achados()
    fase_b.test_svg_sem_conteudo_executavel(log, _RequestFalso("limpo::svg"))
    fase_b.test_imagens_sem_coordenada_de_gps(log, _RequestFalso("limpo::gps"))
    fase_b.test_formato_real_corresponde_a_extensao(log, _RequestFalso("limpo::fmt"))
    assert achados_de("limpo::svg") == []
    assert achados_de("limpo::gps") == []
    assert achados_de("limpo::fmt") == []


def test_xfail_da_fase_b_nao_produz_finding():
    """Sourcemap, SRI e autoria informam — e alerta não ganha selo de severidade.

    Registrar Finding num caminho de xfail poria severidade numa linha que o
    relatório conta como ALERTA, criando um segundo semáforo dentro do estado.
    O §8 do desenho evita exatamente isso; aqui a decisão vira teste.
    """
    from pathlib import Path
    fonte = (Path(__file__).resolve().parent.parent
             / "checks" / "seguranca" / "test_arquivos_e_metadados.py"
             ).read_text(encoding="utf-8")
    for nome in ("test_metadados_de_autoria_removidos_na_publicacao",
                 "test_sourcemaps_nao_referenciados_em_producao",
                 "test_assets_de_terceiro_declaram_sri"):
        corpo = fonte.split(f"def {nome}(")[1].split("\ndef ")[0]
        assert "Finding(" not in corpo, f"{nome} é xfail: não pode construir Finding"
        assert "registrar_achados" not in corpo, f"{nome} é xfail: não pode registrar achado"


def test_fase_b_nao_faz_requisicao_nova():
    """Prova estrutural: o módulo da Fase B não conhece cliente HTTP nenhum.

    A regra "nenhum download novo" (docs/SEGURANCA.md §6) é fácil de violar sem
    querer — basta alguém importar httpx para "só conferir se o .map existe".
    Aqui isso reprova antes de chegar a um alvo.
    """
    from pathlib import Path
    fonte = (Path(__file__).resolve().parent.parent
             / "checks" / "seguranca" / "test_arquivos_e_metadados.py"
             ).read_text(encoding="utf-8")
    for proibido in ("httpx", "requests.", "urllib.request", "page.goto", "urlopen"):
        assert proibido not in fonte, (
            f"Fase B não pode fazer requisição nova, e o módulo menciona {proibido!r}. "
            "Buscar recurso que o navegador não pediu é sondagem — Fase C, atrás do gate.")
