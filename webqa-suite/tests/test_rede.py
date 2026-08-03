"""VERIFICAÇÃO: o decisor de localidade (`webqa/rede.py`), agora por dentro.

`test_fronteira_de_rede.py` prova que NINGUÉM consome a distinção local × público
sem exercitar o ramo público, e que cada consumidor de fato discrimina. É a
guarda de fora. O que faltava — e que o último check-in registrou como dívida —
é a guarda de dentro: `ip_e_local` e `host_e_local` tinham cobertura só indireta,
pelos três consumidores, e cada consumidor fixa UM lado da fronteira. Um erro nos
casos de borda do próprio decisor (a ordem do `0.0.0.0`, a exceção do serviço de
metadados, a exigência de TODOS os IPs) atravessaria os três em silêncio.

Aqui não sai rede: `ip_e_local` recebe objeto `ipaddress`, e as portas que tocam
`getaddrinfo` (`host_e_local`, `ips_de`) recebem um dublê — mesma técnica de
`tests/test_fronteira_de_rede.py`. As bordas provadas são as que a docstring do
módulo promete e que a implementação decide em uma linha cada — exatamente onde
"prosa e código discordam em silêncio" (regra da casa §2.10) faria mais estrago.
"""
from __future__ import annotations

import ipaddress
import socket

import pytest

from webqa import rede

pytestmark = pytest.mark.verification


def _resolve_para(monkeypatch, *ips: str) -> None:
    """Dubla `getaddrinfo` para devolver os IPs dados — nenhuma consulta real sai.

    Aceita vários porque a regra de `host_e_local` é sobre o CONJUNTO: um host
    que resolve para privado E público é terceiro, e só se prova isso dando os
    dois ao resolvedor.
    """
    infos = [
        (socket.AF_INET6 if ":" in ip else socket.AF_INET,
         socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 0))
        for ip in ips
    ]
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p, *a, **k: infos)


def _falha_ao_resolver(monkeypatch) -> None:
    def _erro(*_a, **_k):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", _erro)


# ---------- ip_e_local: os quatro veredictos "local" ----------

@pytest.mark.parametrize("endereco", [
    "127.0.0.1",        # loopback IPv4
    "::1",              # loopback IPv6
    "10.0.0.5",         # privado (classe A)
    "192.168.1.10",     # privado (classe C)
    "172.16.0.1",       # privado (classe B, a que mais escapa de allowlist manual)
    "fd00::1",          # ULA — o "privado" do IPv6
    "169.254.42.7",     # link-local: é desta rede, e NÃO é o metadados
    "fe80::1",          # link-local IPv6
])
def test_enderecos_desta_rede_sao_locais(endereco):
    assert rede.ip_e_local(ipaddress.ip_address(endereco)) is True


@pytest.mark.parametrize("endereco", [
    "93.184.216.34",    # example.com — público
    "8.8.8.8",          # público
    "1.1.1.1",          # público
    "2001:4860:4860::8888",  # público IPv6
])
def test_enderecos_publicos_nao_sao_locais(endereco):
    assert rede.ip_e_local(ipaddress.ip_address(endereco)) is False


def test_zero_a_zero_e_curinga_de_escuta_nao_destino():
    """`0.0.0.0` responde True a `is_private`, e mesmo assim NÃO é local.

    É o caso que a docstring do módulo isola: `is_unspecified` tem de ser
    checado ANTES de `is_private`, senão o curinga de escuta viraria "esta rede"
    e a senha (ou a chamada à LLM) sairia achando que fica em casa. Se alguém
    reordenar as duas checagens, este teste é quem reprova.
    """
    assert rede.ip_e_local(ipaddress.ip_address("0.0.0.0")) is False
    assert rede.ip_e_local(ipaddress.ip_address("::")) is False


@pytest.mark.parametrize("endereco", ["169.254.169.254", "fd00:ec2::254"])
def test_metadados_de_nuvem_nao_e_local(endereco):
    """O IP do serviço de metadados é link-local, logo passaria pela fronteira —
    mas é um serviço do PROVEDOR, não esta máquina. Aceitá-lo cumpriria a letra
    da regra violando o propósito: é o alvo clássico de SSRF, e "é local" aqui
    seria a afirmação falsa mais perigosa que o módulo pode fazer.
    """
    assert rede.ip_e_local(ipaddress.ip_address(endereco)) is False


def test_metadados_de_nuvem_esta_no_conjunto_como_ip_nao_como_texto():
    """Sentinela: a exclusão vale por VALOR de IP, não por casar string.

    `169.254.169.254` e `169.254.169.0254` (octeto com zero à esquerda) são o
    mesmo endereço; a defesa tem de morar no espaço de IP, onde `ipaddress` já
    normalizou, e não numa comparação de texto que uma variação de grafia furaria.
    """
    assert ipaddress.ip_address("169.254.169.254") in rede.METADADOS_DE_NUVEM


# ---------- host_e_local: o conjunto, não o representante ----------

def test_host_que_so_resolve_para_local_e_local(monkeypatch):
    _resolve_para(monkeypatch, "127.0.0.1")
    assert rede.host_e_local("fixture.interno", 8080) is True


def test_host_que_so_resolve_para_publico_nao_e_local(monkeypatch):
    _resolve_para(monkeypatch, "93.184.216.34")
    assert rede.host_e_local("exemplo.com", 443) is False


def test_host_com_ip_local_E_publico_e_tratado_como_terceiro(monkeypatch):
    """A regra é TODOS, não algum. Quem escolhe qual IP usar é o SO, e garantia
    que depende de sorte não é garantia — então basta um IP público para o host
    inteiro contar como terceiro (o lado seguro nos dois usos da fronteira).
    """
    _resolve_para(monkeypatch, "10.0.0.5", "93.184.216.34")
    assert rede.host_e_local("dns-rebinding.example", 80) is False


def test_host_que_nao_resolve_conta_como_nao_local(monkeypatch):
    """Falha de resolução é "não local", nunca exceção que sobe: na dúvida a LLM
    recusa enviar e a campanha aplica etiqueta a mais. O erro cai no lado seguro.
    """
    _falha_ao_resolver(monkeypatch)
    assert rede.host_e_local("nao-existe.invalido", 80) is False


def test_host_vazio_e_nao_local_sem_tocar_o_resolvedor(monkeypatch):
    """Host vazio nem chega a `getaddrinfo`: se chegar, o dublê explode e o teste
    reprova — provando que o curto-circuito acontece antes da rede."""
    def _nao_deve_ser_chamado(*_a, **_k):
        raise AssertionError("host vazio não pode chegar a getaddrinfo")

    monkeypatch.setattr(socket, "getaddrinfo", _nao_deve_ser_chamado)
    assert rede.host_e_local("", 80) is False


# ---------- ips_de: higiene do que volta do resolvedor ----------

def test_ips_de_remove_a_zona_do_link_local(monkeypatch):
    """`getaddrinfo` devolve `fe80::1%eth0`; `ipaddress` recusa a zona. Se o
    corte do `%` sumir, um endereço link-local legítimo viraria exceção e o host
    cairia para "não local" pelo motivo errado — falso negativo silencioso."""
    _resolve_para(monkeypatch, "fe80::1%eth0")
    ips = rede.ips_de("host.local", 80)
    assert ips == [ipaddress.ip_address("fe80::1")]


def test_ips_de_deduplica_preservando_ordem(monkeypatch):
    """Famílias/portas repetidas em `getaddrinfo` não podem inflar a lista: quem
    consome (`host_e_local`) itera sobre ela, e duplicata só custa trabalho."""
    _resolve_para(monkeypatch, "10.0.0.1", "10.0.0.1", "10.0.0.2")
    assert rede.ips_de("host.local", 80) == [
        ipaddress.ip_address("10.0.0.1"),
        ipaddress.ip_address("10.0.0.2"),
    ]


# ---------- C2 fatia 2b: resolvedor DNS TXT raw (posse por DNS-TXT) ----------
#
# Parser escrito à mão é onde bug de rede vira vazamento de garantia (posse
# aceitando token errado). Prova-se com pacote forjado e socket dublado — sem rede.

import struct  # noqa: E402 — local a esta seção, como o resto usa dublês


def _qname(host: str) -> bytes:
    return b"".join(struct.pack("B", len(r)) + r.encode() for r in host.split(".")) + b"\x00"


def _resposta_txt(host: str, *textos: str) -> bytes:
    """Resposta DNS TXT válida: header + pergunta + respostas com ponteiro de nome
    (0xC00C → offset 12) e RDATA de string tamanho-prefixada."""
    header = struct.pack(">HHHHHH", 0x1234, 0x8180, 1, len(textos), 0, 0)
    pergunta = _qname(host) + struct.pack(">HH", 16, 1)
    corpo = b""
    for t in textos:
        tb = t.encode()
        rdata = struct.pack("B", len(tb)) + tb
        corpo += struct.pack(">HHHIH", 0xC00C, 16, 1, 0, len(rdata)) + rdata
    return header + pergunta + corpo


def test_montar_consulta_txt_pede_txt_in():
    q = rede._montar_consulta_txt("cdn.exemplo.br")
    assert q[-4:] == struct.pack(">HH", 16, 1)      # QTYPE=TXT(16), QCLASS=IN(1)
    assert b"\x03cdn" in q


def test_parse_txt_extrai_a_string():
    pkt = _resposta_txt("cdn.exemplo.br", "webqa-ownership=abc123")
    assert rede._parse_txt(pkt) == frozenset({"webqa-ownership=abc123"})


def test_parse_txt_multiplos_registros():
    pkt = _resposta_txt("a.b", "t1=x", "t2=y")
    assert rede._parse_txt(pkt) == frozenset({"t1=x", "t2=y"})


def test_parse_txt_resposta_curta_levanta_oserror():
    with pytest.raises(OSError):
        rede._parse_txt(b"\x00\x01\x02")


def test_parse_txt_rdata_truncado_levanta_oserror():
    with pytest.raises(OSError):
        rede._parse_txt(_resposta_txt("a.b", "t=x")[:-2])


def test_txt_de_com_socket_dublado(monkeypatch):
    """txt_de ponta a ponta sem rede: nameserver e socket UDP dublados."""
    monkeypatch.setattr(rede, "_nameserver_do_sistema", lambda: "127.0.0.1")
    enviado = {}

    class _FakeSock:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def settimeout(self, t):
            pass

        def sendto(self, dados, destino):
            enviado["destino"] = destino

        def recv(self, n):
            return _resposta_txt("cdn.exemplo.br", "webqa-ownership=abc123")

    monkeypatch.setattr(socket, "socket", _FakeSock)
    assert rede.txt_de("cdn.exemplo.br") == frozenset({"webqa-ownership=abc123"})
    assert enviado["destino"] == ("127.0.0.1", 53)


def test_txt_de_sem_nameserver_levanta_oserror(monkeypatch):
    def _sem():
        raise OSError("sem nameserver")
    monkeypatch.setattr(rede, "_nameserver_do_sistema", _sem)
    with pytest.raises(OSError):
        rede.txt_de("cdn.exemplo.br")
