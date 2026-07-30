"""VERIFICAÇÃO da etiqueta de campanha (OS-25).

**Nenhum teste toca rede.** O `robots.txt` é fabricado, os status são
fabricados, e `getaddrinfo` é dublado quando a distinção local × terceiro
importa. A validação de verdade é a campanha na VPS contra sites públicos.

O que se protege aqui é ético, não funcional: a suíte não deve ser CAPAZ de
rastrear onde o dono pediu para não rastrear, nem de insistir depois de o
servidor pedir para parar. Etiqueta é invariante estrutural, não instrução no
manual — quem escreve um alvo novo no `campanha.yaml` não precisa lembrar de
nada.
"""
from __future__ import annotations

import socket

import pytest

from webqa.etiqueta import (
    STATUS_DE_RECUO,
    PoliteFetcher,
    motivo_do_recuo,
    resposta_pede_recuo,
)

pytestmark = pytest.mark.verification

ROBOTS_SIMPLES = """
User-agent: *
Disallow: /admin
Disallow: /interno/
Crawl-delay: 2
"""

# Caso real e traiçoeiro: robots SEM grupo `*`. O RobotFileParser do stdlib
# levanta AttributeError em crawl_delay() aqui, porque default_entry é None.
ROBOTS_SO_ESPECIFICO = """
User-agent: Googlebot
Disallow: /nada
"""


class _Resposta:
    def __init__(self, status=200, text=""):
        self.status_code, self.text = status, text


def _fetcher(resposta=None, erro=None, ua="WebQA-Suite/1.0 (+contato)"):
    chamadas = []

    def get(url, **kwargs):
        chamadas.append((url, kwargs))
        if erro is not None:
            raise erro
        return resposta if resposta is not None else _Resposta(200, ROBOTS_SIMPLES)

    f = PoliteFetcher(ua, timeout_s=7.0, get=get)
    f.chamadas = chamadas       # o teste inspeciona o que saiu
    return f


def _publico(monkeypatch, ip="93.184.216.34"):
    """Faz qualquer host resolver para IP público — logo, terceiro."""
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p, *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, p))])


def _local(monkeypatch, ip="127.0.0.1"):
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p, *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, p))])


# ---------- robots.txt: o que é proibido fica proibido ----------

def test_caminho_proibido_e_bloqueado_e_o_permitido_segue(monkeypatch):
    _publico(monkeypatch)
    f = _fetcher()
    assert f.preparar("https://alvo.example/").permitido

    assert f.pode_acessar("https://alvo.example/") is True
    assert f.pode_acessar("https://alvo.example/sobre") is True
    assert f.pode_acessar("https://alvo.example/admin") is False
    assert f.pode_acessar("https://alvo.example/interno/x") is False
    assert f.motivo_do_bloqueio("https://alvo.example/admin") == "robots.txt proíbe /admin"


def test_crawl_delay_do_alvo_e_respeitado(monkeypatch):
    _publico(monkeypatch)
    assert _fetcher().preparar("https://alvo.example/").crawl_delay_s == 2.0


def test_robots_e_lido_por_parse_e_nunca_por_read(monkeypatch):
    """`rp.read()` usa `urllib` SEM timeout: um host que aceita a conexão e não
    responde travaria a campanha inteira, sem log e sem fim."""
    _publico(monkeypatch)
    f = _fetcher()
    f.preparar("https://alvo.example/")

    url, kwargs = f.chamadas[0]
    assert url == "https://alvo.example/robots.txt"
    assert kwargs["timeout"] == 7.0, "o timeout do settings tem de chegar ao GET"

    # Busca no ast, não no texto: o módulo EXPLICA em comentário por que não usa
    # `rp.read()`, e um grep ingênuo acusaria a própria explicação.
    import ast
    from pathlib import Path

    arvore = ast.parse((Path(__file__).resolve().parent.parent / "webqa" / "etiqueta.py"
                        ).read_text(encoding="utf-8"))
    chamadas = {no.func.attr for no in ast.walk(arvore)
                if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)}
    assert "read" not in chamadas, "RobotFileParser.read() usa urllib sem timeout"
    assert "parse" in chamadas, "o robots tem de ser lido por parse do texto já baixado"


def test_crawl_delay_nao_lanca_quando_robots_so_tem_agente_especifico(monkeypatch):
    """Bug conhecido do stdlib: sem grupo `*`, `crawl_delay()` levanta
    AttributeError. Deixar propagar derrubaria a campanha por causa do robots
    de UM alvo, com um traceback que não fala de etiqueta."""
    _publico(monkeypatch)
    f = _fetcher(_Resposta(200, ROBOTS_SO_ESPECIFICO))
    veredito = f.preparar("https://alvo.example/")

    assert veredito.permitido
    assert veredito.crawl_delay_s == 0.0
    assert f.pode_acessar("https://alvo.example/qualquer") is True


# ---------- robots inacessível: disallow temporário, não erro ----------

@pytest.mark.parametrize("status", [500, 502, 503])
def test_robots_com_erro_de_servidor_pula_o_alvo(monkeypatch, status):
    """Não conseguir ler a política de alguém não é licença para ignorá-la."""
    _publico(monkeypatch)
    veredito = _fetcher(_Resposta(status)).preparar("https://alvo.example/")

    assert veredito.bloqueado
    assert str(status) in veredito.motivo
    assert "pulado" in veredito.motivo or "recuo" in veredito.motivo


def test_robots_inacessivel_por_excecao_pula_o_alvo_sem_estourar(monkeypatch):
    _publico(monkeypatch)
    veredito = _fetcher(erro=TimeoutError("sem resposta")).preparar("https://alvo.example/")

    assert veredito.bloqueado
    assert "TimeoutError" in veredito.motivo
    assert "inacessível" in veredito.motivo


def test_sem_robots_publicado_tudo_e_permitido(monkeypatch):
    """404 é o host RESPONDENDO que não há política — diferente de não responder."""
    _publico(monkeypatch)
    f = _fetcher(_Resposta(404, "not found"))
    veredito = f.preparar("https://alvo.example/")

    assert veredito.permitido
    assert f.pode_acessar("https://alvo.example/admin") is True


def test_alvo_nao_preparado_nao_pode_ser_acessado(monkeypatch):
    """Perguntar antes de ler a política é o mesmo que não ter política."""
    _publico(monkeypatch)
    assert _fetcher().pode_acessar("https://alvo.example/") is False


# ---------- recuo ----------

@pytest.mark.parametrize("status", STATUS_DE_RECUO)
def test_status_de_recuo_reconhecido(status):
    assert resposta_pede_recuo(status)
    assert str(status) in motivo_do_recuo(status)


@pytest.mark.parametrize("status", [200, 301, 404, 500])
def test_status_que_nao_pede_recuo(status):
    assert not resposta_pede_recuo(status)


def test_recuo_ja_no_robots_bloqueia_o_alvo(monkeypatch):
    _publico(monkeypatch)
    veredito = _fetcher(_Resposta(429)).preparar("https://alvo.example/")
    assert veredito.bloqueado and "recuo (429)" in veredito.motivo


# ---------- isenção do alvo controlado ----------

@pytest.mark.parametrize("ip", ["127.0.0.1", "192.168.0.10", "10.1.2.3"])
def test_alvo_de_rede_local_e_isento_e_nao_consulta_robots(monkeypatch, ip):
    """O fixture é nosso e fabricado. Pedir licença a nós mesmos é cerimônia —
    e cerimônia ensina a ignorar a regra."""
    _local(monkeypatch, ip)
    f = _fetcher()
    veredito = f.preparar(f"http://{ip}:8000/")

    assert veredito.permitido and veredito.isento
    assert f.chamadas == [], "não pode haver requisição de robots.txt para alvo local"
    assert f.pode_acessar(f"http://{ip}:8000/admin") is True


def test_host_publico_entra_na_disciplina(monkeypatch):
    _publico(monkeypatch)
    f = _fetcher()
    f.preparar("https://alvo.example/")
    assert [u for u, _ in f.chamadas] == ["https://alvo.example/robots.txt"]


def test_host_que_nao_resolve_nao_e_tratado_como_local(monkeypatch):
    """Na dúvida, etiqueta a mais. Host irresolvível não vira alvo controlado."""
    def falha(*a, **k):
        raise socket.gaierror("nao resolve")
    monkeypatch.setattr(socket, "getaddrinfo", falha)

    f = _fetcher()
    assert f.isento("https://alvo.example/") is False


def test_robots_consultado_uma_vez_por_host(monkeypatch):
    """Perguntar de novo a cada página seria a própria etiqueta virando tráfego."""
    _publico(monkeypatch)
    f = _fetcher()
    for _ in range(4):
        f.preparar("https://alvo.example/pagina")
    assert len(f.chamadas) == 1


# ---------- guarda de carga ----------

def test_campanha_aborta_antes_de_qualquer_requisicao_se_carga_autorizada():
    """A guarda é de AMBIENTE e roda antes do primeiro byte sair."""
    from scripts.campanha import ENV_CARGA, CampanhaAbortada, verificar_ambiente_passivo

    verificar_ambiente_passivo({})           # ambiente limpo: não levanta
    for valor in ("1", "0", ""):
        with pytest.raises(CampanhaAbortada, match="passiva"):
            verificar_ambiente_passivo({ENV_CARGA: valor})


# ---------- sequencialidade do crawl ----------

def test_crawl_entre_paginas_e_sequencial_por_construcao():
    """Prova estrutural: o crawler não conhece paralelismo nenhum.

    Uma página por vez é o que a etiqueta serializa. Os assets de UMA página
    seguem carregando em paralelo pelo navegador — isso é comportamento de
    visitante, é o que a métrica precisa medir, e está fora deste critério.
    """
    from pathlib import Path

    fonte = (Path(__file__).resolve().parent.parent
             / "checks" / "functional" / "test_links.py").read_text(encoding="utf-8")
    for paralelo in ("asyncio", "gather", "ThreadPool", "concurrent.futures",
                     "multiprocessing", "AsyncClient"):
        assert paralelo not in fonte, (
            f"o crawl precisa ser sequencial e o módulo menciona {paralelo!r}: "
            "paralelizar transformaria diagnóstico em rajada contra o alvo.")
