"""Classificação de endereço por IP RESOLVIDO — nunca por string.

Nasceu no veto de endpoint da camada de LLM (OS-23) e foi extraído aqui quando a
etiqueta de campanha (OS-25) precisou da mesma pergunta: *este host é a máquina
local / rede controlada, ou é sistema de terceiro?*

Duas respostas diferentes dependem dela, e as duas são éticas:

* a LLM só pode falar com runtime local — nada sai da máquina;
* a campanha só deve etiqueta (robots.txt, recuo, sequencialidade) a **terceiro**;
  contra o alvo fixture, que é nosso e fabricado, a disciplina seria cerimônia.

Casar `localhost` ou `127.` no texto da URL é ilusão de controle: qualquer
hostname pode resolver para IP público, e é assim que um "alvo local" vira
tráfego contra sistema alheio sem ninguém perceber. Aqui resolve-se primeiro e
julga-se o endereço.

Somente stdlib.
"""
from __future__ import annotations

import ipaddress
import socket
import struct

# Endereço do serviço de metadados das nuvens (AWS, GCP, Azure, DigitalOcean).
# É link-local — logo passaria por "rede local" — mas NÃO é esta máquina: é um
# serviço do provedor. Aceitá-lo cumpriria a letra da fronteira violando o
# propósito dela.
METADADOS_DE_NUVEM = frozenset({
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("fd00:ec2::254"),
})

PORTA_PADRAO = {"http": 80, "https": 443}


def ips_de(host: str, porta: int) -> list:
    """IPs que o host resolve, via `getaddrinfo`. Lista vazia é erro de quem chama."""
    infos = socket.getaddrinfo(host, porta, proto=socket.IPPROTO_TCP)
    vistos = []
    for info in infos:
        endereco = info[4][0]
        ip = ipaddress.ip_address(endereco.split("%")[0])   # tira zona de link-local
        if ip not in vistos:
            vistos.append(ip)
    return vistos


def ip_e_local(ip) -> bool:
    """O endereço é da máquina ou da rede local — e não um serviço de provedor.

    `is_unspecified` é checado ANTES de `is_private` porque em `ipaddress` o
    `0.0.0.0` está em `0.0.0.0/8` e responde `True` a `is_private`. Endereço não
    especificado não é destino: é curinga de escuta.
    """
    if ip.is_unspecified or ip in METADADOS_DE_NUVEM:
        return False
    return bool(ip.is_loopback or ip.is_private or ip.is_link_local)


def host_e_local(host: str, porta: int = 80) -> bool:
    """Todos os IPs do host são locais? Host que não resolve conta como NÃO local.

    Exige **todos**, não algum: um host que devolve um IP privado e um público é
    tratado como terceiro. Quem escolhe qual usar é o sistema operacional, e uma
    garantia que depende de sorte não é garantia.

    Na dúvida, "não local" é o lado seguro nos dois usos: a LLM recusa enviar, e
    a campanha aplica etiqueta a mais em vez de a menos.
    """
    if not host:
        return False
    try:
        ips = ips_de(host, porta)
    except OSError:
        return False
    return bool(ips) and all(ip_e_local(ip) for ip in ips)


# ---------- consulta DNS TXT (prova de posse por DNS-TXT, R-C6 alternativa) ----------
#
# stdlib não resolve TXT via `getaddrinfo` (só A/AAAA) e o projeto é stdlib-first
# (sem dnspython). Então a consulta TXT é DNS cru por UDP ao resolvedor do
# sistema. Usada SÓ pela prova de posse por DNS-TXT do escopo; nos testes é
# dublada (nenhuma consulta real sai). Qualquer defeito vira `OSError`, que o
# chamador lê como 'sem TXT' — jamais silêncio que se pareça com posse.

_QTYPE_TXT = 16
_QCLASS_IN = 1


def _nameserver_do_sistema() -> str:
    """Primeiro `nameserver` de /etc/resolv.conf. OSError se não houver."""
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as f:
            for linha in f:
                partes = linha.split()
                if len(partes) >= 2 and partes[0] == "nameserver":
                    return partes[1]
    except OSError:
        pass
    raise OSError("sem nameserver em /etc/resolv.conf")


def _montar_consulta_txt(host: str) -> bytes:
    # Cabeçalho: id fixo (UDP one-shot), flags=recursão desejada, 1 pergunta.
    cabecalho = struct.pack(">HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0)
    qname = b"".join(struct.pack("B", len(r)) + r.encode("idna")
                     for r in host.rstrip(".").split(".")) + b"\x00"
    return cabecalho + qname + struct.pack(">HH", _QTYPE_TXT, _QCLASS_IN)


def _pular_nome(resposta: bytes, i: int) -> int:
    """Avança o cursor por um NAME DNS (labels ou ponteiro de compressão)."""
    while True:
        if i >= len(resposta):
            raise OSError("resposta DNS truncada")
        tamanho = resposta[i]
        if tamanho & 0xC0 == 0xC0:      # ponteiro de compressão: 2 bytes, encerra
            return i + 2
        if tamanho == 0:                # fim do nome
            return i + 1
        i += 1 + tamanho


def _parse_txt(resposta: bytes) -> frozenset[str]:
    """Extrai as strings TXT de uma resposta DNS. OSError se malformada."""
    if len(resposta) < 12:
        raise OSError("resposta DNS curta demais")
    qd, an = struct.unpack(">HH", resposta[4:8])
    i = 12
    for _ in range(qd):                 # pula as perguntas
        i = _pular_nome(resposta, i) + 4
    textos: set[str] = set()
    for _ in range(an):
        i = _pular_nome(resposta, i)
        if i + 10 > len(resposta):
            raise OSError("registro DNS truncado")
        tipo, _classe, _ttl, rdlength = struct.unpack(">HHIH", resposta[i:i + 10])
        i += 10
        fim = i + rdlength
        if fim > len(resposta):
            raise OSError("RDATA DNS truncado")
        if tipo == _QTYPE_TXT:          # RDATA = strings de tamanho-prefixado
            partes, j = [], i
            while j < fim:
                n = resposta[j]
                partes.append(resposta[j + 1:j + 1 + n].decode("utf-8", "replace"))
                j += 1 + n
            textos.add("".join(partes))
        i = fim
    return frozenset(textos)


def txt_de(host: str, timeout_s: float = 3.0) -> frozenset[str]:
    """Registros TXT de `host` como conjunto de strings; consulta DNS crua (UDP).

    Só a prova de posse por DNS-TXT usa isto. OSError (sem nameserver, timeout,
    resposta malformada) sobe para o chamador, que o lê como 'sem TXT'.
    """
    servidor = _nameserver_do_sistema()
    consulta = _montar_consulta_txt(host)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout_s)
        s.sendto(consulta, (servidor, 53))
        resposta = s.recv(4096)
    return _parse_txt(resposta)
