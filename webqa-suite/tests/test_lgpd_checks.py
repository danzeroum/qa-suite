"""VERIFICAÇÃO da bateria LGPD: os checks reprovam e aprovam o que devem?

Separação V&V levada a sério: checks/lgpd/ VALIDA um alvo real; este arquivo
VERIFICA os checks contra alvos FABRICADOS, sem rede. É aqui que moram os casos
de borda que, se errados, reprovam alvo conforme e queimam a credibilidade da
bateria — allowlist, action relativo, política em PDF, www vs sem-www e Expires
no passado.

Os testes dos checks são importados com prefixo "_" para que o pytest não os
recolete neste módulo.
"""
import httpx
import pytest
from bs4 import BeautifulSoup

from checks.lgpd.test_consentimento import (
    test_sem_cookies_nao_essenciais_pre_aceite as _check_cookies_pre_aceite,
)
from checks.lgpd.test_consentimento import (
    test_sem_trackers_antes_do_consentimento as _check_sem_trackers,
)
from checks.lgpd.test_pii_transito import test_forms_pii_post_https as _check_forms_pii
from checks.lgpd.test_pii_transito import test_pii_em_query_string as _check_pii_query
from checks.lgpd.test_pii_transito import test_referrer_policy as _check_referrer
from checks.lgpd.test_retencao_observavel import _duracao_em_dias
from checks.lgpd.test_retencao_observavel import test_cookies_expiracao as _check_cookies_exp
from checks.lgpd.test_retencao_observavel import test_permissions_policy as _check_permissions
from checks.lgpd.test_terceiros import test_inventario_terceiros as _check_inventario
from checks.lgpd.test_terceiros import test_sri_scripts_externos as _check_sri
from checks.lgpd.test_transparencia import e_pdf, encontrar_link_politica
from webqa.trackers import LoggedRequest, NetworkLog

pytestmark = pytest.mark.verification


# ---------- Duplos de teste (fixtures fabricadas) ----------

class _FakeSettings:
    def __init__(self, allowlist=(), target_url="https://alvo.com"):
        self.lgpd_allowed_third_parties = list(allowlist)
        self.target_url = target_url


class _FakeResponse:
    def __init__(self, *, text="", status_code=200, headers=None, url="https://alvo.com/"):
        self.text = text
        self.status_code = status_code
        self.headers = httpx.Headers(headers or [])
        self.url = url


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _log(requests=(), cookies=()):
    return NetworkLog(url="https://alvo.com/", requests=tuple(requests), cookies=tuple(cookies))


def _falha(fn, *args) -> str:
    """Executa o check esperando FAIL e devolve a mensagem."""
    with pytest.raises(AssertionError) as exc:
        fn(*args)
    return str(exc.value)


def _pulado(fn, *args) -> str:
    with pytest.raises(pytest.skip.Exception) as exc:
        fn(*args)
    return str(exc.value)


def _informativo(fn, *args) -> str:
    """Executa o check esperando xfail (sinal, não infração)."""
    with pytest.raises(pytest.xfail.Exception) as exc:
        fn(*args)
    return str(exc.value)


# ---------- OS-02: consentimento ----------

_GA = LoggedRequest("https://region1.google-analytics.com/g/collect", "xhr")
_APP = LoggedRequest("https://cdn.alvo.com/app.js", "script")


def test_pagina_estatica_sem_terceiros_passa():
    log = _log([LoggedRequest("https://alvo.com/", "document"), _APP])
    _check_sem_trackers(log, _FakeSettings())
    _check_cookies_pre_aceite(log)


def test_ga_no_load_reprova_citando_o_host():
    msg = _falha(_check_sem_trackers, _log([_GA]), _FakeSettings())
    assert "google-analytics" in msg and "Art. 7º I" in msg


def test_host_na_allowlist_nunca_reprova():
    _check_sem_trackers(_log([_GA]), _FakeSettings(["google-analytics.com"]))


def test_cookie_de_sessao_do_alvo_nao_reprova():
    _check_cookies_pre_aceite(_log(cookies=[{"name": "sessionid"}, {"name": "csrftoken"}]))


def test_cookie_de_analytics_reprova():
    msg = _falha(_check_cookies_pre_aceite, _log(cookies=[{"name": "_ga"}, {"name": "sessionid"}]))
    assert "_ga" in msg and "sessionid" not in msg


def test_familia_ga4_e_clarity_sao_detectadas():
    for nome in ("_ga_ABC123", "_hjSessionUser_1", "_clck", "_ttp"):
        assert nome in _falha(_check_cookies_pre_aceite, _log(cookies=[{"name": nome}]))


def test_muitos_cookies_desconhecidos_apenas_informam():
    cookies = [{"name": f"custom{i}"} for i in range(6)]
    assert "não identificável" in _informativo(_check_cookies_pre_aceite, _log(cookies=cookies))


# ---------- OS-03: PII em trânsito ----------

def test_href_com_email_reprova_com_url_mascarada():
    html = '<a href="/contato?email=x@y.com">fale</a>'
    msg = _falha(_check_pii_query, _soup(html), _FakeResponse())
    assert "x@y.com" not in msg  # o dado do titular NUNCA volta no relatório
    assert "[params ocultos]" in msg and "email" in msg


def test_cpf_em_query_de_recurso_reprova():
    html = '<img src="https://cdn.alvo.com/p.png?u=529.982.247-25">'
    msg = _falha(_check_pii_query, _soup(html), _FakeResponse())
    assert "529" not in msg and "cpf" in msg


def test_pagina_sem_pii_em_url_passa():
    html = '<a href="/produtos?pagina=2">itens</a><img src="/logo.png">'
    _check_pii_query(_soup(html), _FakeResponse())


def test_referrer_policy_por_header_e_por_meta():
    forte = _FakeResponse(headers=[("referrer-policy", "strict-origin-when-cross-origin")])
    _check_referrer(forte, _soup(""))
    _check_referrer(_FakeResponse(), _soup('<meta name="referrer" content="no-referrer">'))


def test_referrer_policy_ausente_apenas_informa():
    assert "Sem Referrer-Policy" in _informativo(_check_referrer, _FakeResponse(), _soup(""))


def test_referrer_policy_permissiva_reprova():
    resp = _FakeResponse(headers=[("referrer-policy", "unsafe-url")])
    assert "unsafe-url" in _falha(_check_referrer, resp, _soup(""))


def test_form_newsletter_em_get_reprova_citando_action():
    html = '<form action="/newsletter" method="get"><input name="email"></form>'
    msg = _falha(_check_forms_pii, _soup(html), _FakeResponse())
    assert "/newsletter" in msg and "method=get" in msg


def test_action_relativo_resolvido_antes_de_validar_https():
    """Action relativo herda o https da página — não pode reprovar."""
    html = '<form action="assinar" method="post"><input name="email"></form>'
    _check_forms_pii(_soup(html), _FakeResponse(url="https://alvo.com/blog/post"))


def test_action_relativo_em_pagina_http_reprova():
    html = '<form action="assinar" method="post"><input name="email"></form>'
    msg = _falha(_check_forms_pii, _soup(html), _FakeResponse(url="http://alvo.com/"))
    assert "HTTPS" in msg


def test_form_sem_campo_pessoal_e_pulado():
    html = '<form action="/busca"><input name="q"></form>'
    assert "campo pessoal" in _pulado(_check_forms_pii, _soup(html), _FakeResponse())


def test_pagina_sem_formularios_e_pulado():
    assert "sem formulários" in _pulado(_check_forms_pii, _soup("<p>oi</p>"), _FakeResponse())


# ---------- OS-04: transparência ----------

def test_politica_em_portugues_e_localizada():
    html = '<a href="/privacidade">Política de Privacidade</a>'
    assert encontrar_link_politica(_soup(html), "https://alvo.com/") == "https://alvo.com/privacidade"


def test_politica_em_ingles_e_reconhecida():
    html = '<a href="/legal/pp">Privacy Policy</a>'
    assert encontrar_link_politica(_soup(html), "https://alvo.com/") == "https://alvo.com/legal/pp"


def test_candidato_forte_vence_o_fraco():
    html = '<a href="/termos">Termos de uso</a><a href="/pp">privacidade</a>'
    assert encontrar_link_politica(_soup(html), "https://alvo.com/").endswith("/pp")


def test_home_sem_link_de_politica():
    assert encontrar_link_politica(_soup('<a href="/sobre">Sobre</a>'), "https://alvo.com/") is None


def test_pdf_detectado_por_extensao_e_por_content_type():
    assert e_pdf("https://alvo.com/pp.pdf", "application/octet-stream")
    assert e_pdf("https://alvo.com/pp?x=1", "application/pdf")
    assert not e_pdf("https://alvo.com/pp", "text/html; charset=utf-8")


# ---------- OS-05: terceiros ----------

def _inventario(tmp_path, monkeypatch, requests):
    monkeypatch.setattr("webqa.report.REPORT_DIR", tmp_path)
    _check_inventario(_log(requests), _FakeSettings())
    import json
    return json.loads((tmp_path / "terceiros.json").read_text(encoding="utf-8"))


def test_alvo_sem_terceiros_gera_inventario_vazio(tmp_path, monkeypatch):
    dados = _inventario(tmp_path, monkeypatch, [LoggedRequest("https://alvo.com/", "document")])
    assert dados["third_party_count"] == 0 and dados["third_parties"] == []


def test_www_e_sem_www_sao_primeira_parte(tmp_path, monkeypatch):
    requests = [
        LoggedRequest("https://www.alvo.com/", "document"),
        LoggedRequest("https://alvo.com/a.css", "stylesheet"),
        LoggedRequest("https://cdn.alvo.com/app.js", "script"),
        LoggedRequest("data:image/png;base64,AA", "image"),
    ]
    assert _inventario(tmp_path, monkeypatch, requests)["third_parties"] == []


def test_inventario_ordena_por_volume(tmp_path, monkeypatch):
    requests = [
        LoggedRequest("https://alvo.com/", "document"),
        LoggedRequest("https://b.com/1.js", "script"),
        LoggedRequest("https://c.com/1.png", "image"),
        LoggedRequest("https://c.com/2.png", "image"),
        LoggedRequest("https://c.com/x", "xhr"),
    ]
    terceiros = _inventario(tmp_path, monkeypatch, requests)["third_parties"]
    assert [t["host"] for t in terceiros] == ["c.com", "b.com"]
    assert terceiros[0]["requests"] == 3
    assert terceiros[0]["resource_types"] == ["image", "xhr"]


def test_jquery_de_cdn_sem_integrity_reprova():
    html = '<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>'
    msg = _falha(_check_sri, _soup(html), _log(), _FakeSettings())
    assert "jquery" in msg and "integrity" in msg


def test_script_de_terceiro_com_sri_passa():
    html = ('<script src="https://code.jquery.com/j.js" integrity="sha384-abc" '
            'crossorigin="anonymous"></script>')
    _check_sri(_soup(html), _log(), _FakeSettings())


def test_script_relativo_e_de_subdominio_nao_exigem_sri():
    html = '<script src="/app.js"></script><script src="https://cdn.alvo.com/b.js"></script>'
    _check_sri(_soup(html), _log(), _FakeSettings())


# ---------- OS-06: retenção observável ----------

def test_max_age_de_dois_anos_reprova_citando_dias():
    resp = _FakeResponse(headers=[("set-cookie", "_ga=x; Max-Age=63072000; Path=/")])
    assert "730 dias" in _falha(_check_cookies_exp, resp)


def test_expires_no_passado_e_delecao_e_passa():
    resp = _FakeResponse(
        headers=[("set-cookie", "old=; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/")]
    )
    _check_cookies_exp(resp)


def test_expires_malformado_tratado_como_sessao():
    resp = _FakeResponse(headers=[("set-cookie", "a=1; Expires=amanha-de-manha")])
    _check_cookies_exp(resp)
    assert _duracao_em_dias("a=1; Expires=amanha-de-manha") is None
    assert _duracao_em_dias("a=1; Max-Age=nao-sou-numero") is None


def test_cookie_de_sessao_nao_reprova():
    _check_cookies_exp(_FakeResponse(headers=[("set-cookie", "sessionid=x; HttpOnly; Path=/")]))


def test_multiplos_set_cookie_sao_todos_avaliados():
    resp = _FakeResponse(
        headers=[
            ("set-cookie", "sessionid=x; Path=/"),
            ("set-cookie", "_ga=y; Max-Age=63072000"),
            ("set-cookie", "_fbp=z; Max-Age=86400000"),  # ~1000 dias
        ]
    )
    msg = _falha(_check_cookies_exp, resp)
    assert "_ga" in msg and "_fbp" in msg and "sessionid" not in msg


def test_faixa_intermediaria_apenas_informa():
    resp = _FakeResponse(headers=[("set-cookie", "pref=1; Max-Age=17280000")])  # 200 dias
    assert "200 dias" in _informativo(_check_cookies_exp, resp)


def test_max_age_tem_precedencia_sobre_expires():
    header = "a=1; Max-Age=60; Expires=Wed, 01 Jan 2098 00:00:00 GMT"
    assert _duracao_em_dias(header) == pytest.approx(60 / 86400)


def test_sem_set_cookie_e_pulado():
    assert "Nenhum Set-Cookie" in _pulado(_check_cookies_exp, _FakeResponse())


def test_permissions_policy_completa_passa():
    resp = _FakeResponse(
        headers=[("permissions-policy", "geolocation=(), camera=(), microphone=()")]
    )
    _check_permissions(resp)


def test_permissions_policy_ausente_ou_parcial_informa():
    assert "Sem Permissions-Policy" in _informativo(_check_permissions, _FakeResponse())
    parcial = _FakeResponse(headers=[("permissions-policy", "geolocation=()")])
    msg = _informativo(_check_permissions, parcial)
    assert "camera" in msg and "microphone" in msg
