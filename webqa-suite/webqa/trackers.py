"""Identificação de rastreadores de terceiros e contrato da observação de rede.

Base legal do teste: LGPD Art. 7º I e 8º §4 — tratamento fundado em consentimento
exige consentimento prévio, livre e específico. Um tracker que dispara ANTES de
qualquer interação com o banner trata dado pessoal (IP, ID de dispositivo) sem
base legal declarada.

Ponto único de verdade sobre "o que é rastreador": os testes de checks/lgpd/ não
mantêm listas próprias. Somente stdlib — sem dependências novas.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit

# Domínios de rastreamento/publicidade de uso corrente. Lista deliberadamente
# curta e auditável: falso positivo em bateria regulatória custa credibilidade,
# então só entram domínios cuja finalidade primária é medir/publicitar.
TRACKER_DOMAINS = frozenset(
    {
        "google-analytics.com",
        "googletagmanager.com",
        "doubleclick.net",
        "connect.facebook.net",
        "hotjar.com",
        "hotjar.io",
        "clarity.ms",
        "mixpanel.com",
        "segment.com",
        "segment.io",
        "amplitude.com",
        "criteo.com",
        "criteo.net",
        "taboola.com",
        "tiktok.com",
    }
)


def host_of(url: str) -> str:
    """Host em minúsculas de uma URL http(s); "" para data:, blob:, about:blank."""
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https"):
        return ""
    return (parsed.hostname or "").lower().rstrip(".")


def _normalize_domain(domain: str) -> str:
    """Normaliza entrada de lista: minúscula, sem espaços, sem '*.' nem 'www.'."""
    domain = domain.strip().lower().rstrip(".")
    for prefix in ("*.", "www."):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    return domain


def host_matches(host: str, domain: str) -> bool:
    """True se `host` é o próprio domínio ou um subdomínio dele.

    Casamento por sufixo de rótulo (nunca por substring): "meugoogle-analytics.com"
    não casa com "google-analytics.com".
    """
    domain = _normalize_domain(domain)
    if not host or not domain:
        return False
    return host == domain or host.endswith("." + domain)


def is_tracker(url: str, allowlist: Iterable[str] = ()) -> bool:
    """True se a URL aponta para um rastreador conhecido e não liberado.

    A allowlist VENCE a lista de rastreadores: é a decisão documentada do
    controlador (ex.: tag gerenciada com consentimento fora do escopo do teste),
    e o teste não pode ser mais esperto que a decisão registrada em config.yaml.
    """
    host = host_of(url)
    if not host:
        return False
    if any(host_matches(host, allowed) for allowed in allowlist):
        return False
    return any(host_matches(host, domain) for domain in TRACKER_DOMAINS)


@dataclass(frozen=True)
class LoggedRequest:
    """Uma requisição observada durante o carregamento do alvo."""

    url: str
    resource_type: str


@dataclass(frozen=True)
class NetworkLog:
    """Contrato da fixture `network_log` — consumido por checks/lgpd/.

    Imutável de propósito: dois testes que compartilham o log de um módulo não
    podem interferir um no outro (isolamento sem custo de nova navegação).
    """

    url: str
    requests: tuple[LoggedRequest, ...]
    cookies: tuple[dict, ...]

    def hosts(self) -> list[str]:
        """Hosts http(s) únicos contactados, em ordem de primeiro contato."""
        seen: dict[str, None] = {}
        for req in self.requests:
            host = host_of(req.url)
            if host:
                seen.setdefault(host, None)
        return list(seen)

    def trackers(self, allowlist: Iterable[str] = ()) -> list[LoggedRequest]:
        allowlist = tuple(allowlist)
        return [r for r in self.requests if is_tracker(r.url, allowlist)]

    def tracker_hosts(self, allowlist: Iterable[str] = ()) -> list[str]:
        """Hosts ofensores únicos, ordenados — mensagem de falha estável."""
        return sorted({host_of(r.url) for r in self.trackers(allowlist)})

    def cookie_names(self) -> list[str]:
        return [str(c.get("name", "")) for c in self.cookies]
