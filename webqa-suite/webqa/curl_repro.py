"""Comando `curl` reproduzível por achado da Fase C — ergonomia de triagem.

Quem recebe o achado quer confirmá-lo em um comando, sem reconstruir o que o
motor fez. Esta função gera esse `curl` — e ele respeita os invariantes do motor:

* **HEAD** por padrão; **GET `Range: bytes=0-0`** (`-r 0-0`) quando o achado foi
  confirmado por esse fallback (HEAD deu 405). `-s -o /dev/null`: não despeja
  corpo — detectar, nunca explorar, também no comando de reprodução.
* **IP pinado só no `--resolve host:porta:IP`, NUNCA na URL.** A URL é a lógica
  (hostname), então o TLS/SNI continua contra o host, exatamente como o probe.
  IP cru numa URL (`https://IP/...`) é o que isto existe para evitar.

Função pura sobre `Finding` + IP; sem I/O. NÃO é um novo probe — é texto.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from webqa.dominio import Finding


def curl_de(finding: Finding, ip_pinado: str) -> str:
    """`curl` que reproduz o probe do achado: HEAD (ou GET Range se foi 405),
    com `--resolve` casando o IP pinado + SNI pelo hostname. Nunca IP na URL."""
    partes = urlsplit(finding.recurso)
    host = partes.hostname or ""
    porta = partes.port or (443 if partes.scheme == "https" else 80)
    resolve = f"--resolve {host}:{porta}:{ip_pinado}"
    if finding.metodo == "GET(range)":
        return f"curl -s -o /dev/null -r 0-0 {resolve} {finding.recurso}"
    return f"curl -s -o /dev/null -I {resolve} {finding.recurso}"
