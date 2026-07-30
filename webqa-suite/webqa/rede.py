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
