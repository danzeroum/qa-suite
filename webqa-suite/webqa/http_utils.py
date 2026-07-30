"""Utilitários HTTP compartilhados: cliente, medição de latência e percentis.

Foco em LIMITES e RISCOS: medimos percentis (p50/p95/p99), não médias —
médias escondem exatamente as caudas que degradam a experiência do usuário.
"""
from __future__ import annotations

import asyncio
import statistics
import time
from dataclasses import dataclass

import httpx

from .auth import Credencial, credencial_do_ambiente, origem_de, pode_enviar_credencial
from .config import Settings


class AutenticacaoDeOrigem(httpx.Auth):
    """Basic Auth que só vai para a origem do alvo, e só sob transporte seguro.

    Existe porque `httpx.BasicAuth` anexa `Authorization` em TODA requisição do
    cliente — e este cliente é de sessão, compartilhado por checks que buscam o
    axe-core num CDN, seguem o link da política de privacidade (com frequência em
    outro domínio) e batem no alvo em `http://` puro para conferir o
    redirecionamento. Com `BasicAuth`, a senha do operador iria para a Cloudflare
    e trafegaria em claro na rede.

    A decisão de enviar mora em `webqa.auth.pode_enviar_credencial` — aqui só se
    obedece, para que a política seja a mesma no httpx e no Playwright.
    """

    def __init__(self, credencial: Credencial, origem: str) -> None:
        self._credencial = credencial
        self._origem = origem

    def auth_flow(self, request):
        if pode_enviar_credencial(str(request.url), self._origem):
            request.headers["Authorization"] = self._credencial.cabecalho_basic
        yield request

    def __repr__(self) -> str:
        return f"AutenticacaoDeOrigem(origem={self._origem!r})"


def autenticacao_do_alvo(settings: Settings) -> httpx.Auth | None:
    """Autenticação a usar contra o alvo, ou None quando o acesso é anônimo."""
    credencial = credencial_do_ambiente()
    if credencial is None:
        return None
    return AutenticacaoDeOrigem(credencial, origem_de(settings.target_url))


def make_client(settings: Settings) -> httpx.Client:
    return httpx.Client(
        timeout=settings.timeout_s,
        follow_redirects=True,
        headers={"User-Agent": settings.user_agent},
        http2=True,
        auth=autenticacao_do_alvo(settings),
    )


@dataclass
class Timing:
    status: int
    ttfb_ms: float
    total_ms: float
    size_bytes: int


def timed_get(client: httpx.Client, url: str) -> Timing:
    """GET com medição de TTFB (primeiro byte) e tempo total via streaming."""
    start = time.perf_counter()
    with client.stream("GET", url) as resp:
        first_chunk_at = None
        size = 0
        for chunk in resp.iter_bytes():
            if first_chunk_at is None:
                first_chunk_at = time.perf_counter()
            size += len(chunk)
        end = time.perf_counter()
    ttfb = ((first_chunk_at or end) - start) * 1000
    return Timing(resp.status_code, ttfb, (end - start) * 1000, size)


def percentiles(samples_ms: list[float]) -> dict[str, float]:
    if not samples_ms:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
    ordered = sorted(samples_ms)

    def pct(p: float) -> float:
        k = max(0, min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1))))
        return ordered[k]

    return {
        "p50": statistics.median(ordered),
        "p95": pct(95),
        "p99": pct(99),
    }


async def burst(settings: Settings, url: str) -> list[float]:
    """Rajada leve e controlada: mede latências sob concorrência limitada."""
    sem = asyncio.Semaphore(settings.load_concurrency)
    latencies: list[float] = []

    # A mesma autenticação do cliente síncrono: sem isto, a rajada bateria
    # anônima num alvo protegido e mediria a latência da página de 401.
    async with httpx.AsyncClient(
        timeout=settings.timeout_s,
        follow_redirects=True,
        headers={"User-Agent": settings.user_agent},
        auth=autenticacao_do_alvo(settings),
    ) as client:

        async def one() -> None:
            async with sem:
                start = time.perf_counter()
                resp = await client.get(url)
                resp.raise_for_status()
                latencies.append((time.perf_counter() - start) * 1000)

        await asyncio.gather(*(one() for _ in range(settings.load_requests)))
    return latencies
