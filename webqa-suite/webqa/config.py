"""Carrega config.yaml e permite sobreposição via variáveis de ambiente WEBQA_*.

Testabilidade (atributo de qualidade): a configuração é um objeto puro,
injetável, sem estado global escondido — qualquer teste pode construir a sua.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    target_url: str
    timeout_s: float
    user_agent: str
    crawl_max_pages: int
    crawl_same_host_only: bool
    load_requests: int
    load_concurrency: int
    thresholds: dict[str, float] = field(default_factory=dict)

    def threshold(self, name: str) -> float:
        return float(self.thresholds[name])


def _env_override(name: str, default: Any) -> Any:
    value = os.environ.get(f"WEBQA_{name.upper()}")
    return value if value is not None else default


def load_settings(path: Path | None = None) -> Settings:
    path = path or ROOT / "config.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    thresholds = dict(raw.get("thresholds", {}))
    for key in list(thresholds):
        thresholds[key] = float(_env_override(key, thresholds[key]))

    http = raw.get("http", {})
    crawl = raw.get("crawl", {})
    burst = raw.get("load_burst", {})

    return Settings(
        target_url=str(_env_override("target_url", raw.get("target_url", ""))).rstrip("/"),
        timeout_s=float(http.get("timeout_s", 15)),
        user_agent=str(http.get("user_agent", "WebQA-Suite/1.0")),
        crawl_max_pages=int(crawl.get("max_pages", 15)),
        crawl_same_host_only=bool(crawl.get("same_host_only", True)),
        load_requests=int(burst.get("requests", 30)),
        load_concurrency=int(burst.get("concurrency", 10)),
        thresholds=thresholds,
    )
