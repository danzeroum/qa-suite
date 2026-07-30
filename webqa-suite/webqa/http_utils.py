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

from .config import Settings


def make_client(settings: Settings) -> httpx.Client:
    return httpx.Client(
        timeout=settings.timeout_s,
        follow_redirects=True,
        headers={"User-Agent": settings.user_agent},
        http2=True,
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

    async with httpx.AsyncClient(
        timeout=settings.timeout_s,
        follow_redirects=True,
        headers={"User-Agent": settings.user_agent},
    ) as client:

        async def one() -> None:
            async with sem:
                start = time.perf_counter()
                resp = await client.get(url)
                resp.raise_for_status()
                latencies.append((time.perf_counter() - start) * 1000)

        await asyncio.gather(*(one() for _ in range(settings.load_requests)))
    return latencies
