"""Terceiros: inventário (insumo de ROPA/DPA), integridade de script e IP em CDN.

Todo terceiro carregado pela página recebe, no mínimo, o IP e o User-Agent do
visitante — dado pessoal (Art. 5º I) tratado por um operador que precisa estar
mapeado e contratado (Art. 39). A suíte não sabe quais contratos existem, então
INFORMA o inventário em vez de reprovar: o artefato é insumo do registro de
operações de tratamento, não veredito.

O que reprova aqui é integridade: script de terceiro sem SRI pode ser trocado e
passar a exfiltrar formulário — a mesma exigência que a suíte cumpre ao injetar
o axe-core com hash verificado.
"""
import json
import time
from collections import Counter, defaultdict

import pytest

from webqa.report import report_dir
from webqa.sanitize import sanitize_text
from webqa.trackers import host_of

pytestmark = [pytest.mark.lgpd, pytest.mark.browser]

_FONTES_EXTERNAS = ("fonts.googleapis.com", "fonts.gstatic.com")


def _base(host: str) -> str:
    """Host sem 'www.' — www.alvo.com e alvo.com são o mesmo controlador."""
    host = (host or "").lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def _e_primeira_parte(host: str, alvo: str) -> bool:
    """True para o próprio alvo e seus subdomínios (mesmo controlador)."""
    host, alvo = _base(host), _base(alvo)
    return bool(host) and (host == alvo or host.endswith("." + alvo))


def test_inventario_terceiros(network_log, settings):
    """Grava report/terceiros.json com quem a página contactou. SEMPRE PASSA."""
    alvo = host_of(network_log.url) or host_of(settings.target_url)

    contagem: Counter[str] = Counter()
    tipos: dict[str, set[str]] = defaultdict(set)
    for req in network_log.requests:
        host = host_of(req.url)
        if not host or _e_primeira_parte(host, alvo):
            continue
        contagem[host] += 1
        tipos[host].add(req.resource_type)

    terceiros = [
        {
            "host": sanitize_text(host),
            "requests": qtd,
            "resource_types": sorted(tipos[host]),
        }
        # Volume primeiro: quem recebe mais requisições recebe mais dado.
        for host, qtd in sorted(contagem.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    inventario = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "target_host": sanitize_text(alvo),
        "third_party_count": len(terceiros),
        "third_parties": terceiros,
        "aviso": (
            "Inventário informativo (insumo de ROPA/DPA, Art. 37/39): cada host "
            "recebe IP e User-Agent do visitante. Não é veredito de conformidade."
        ),
    }
    (report_dir() / "terceiros.json").write_text(
        json.dumps(inventario, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    assert True, "inventário é informativo por decisão de arquitetura"


def test_sri_scripts_externos(soup, network_log, settings):
    """Script de terceiro exige integrity + crossorigin (SRI)."""
    alvo = host_of(network_log.url) or host_of(settings.target_url)
    sem_sri = []
    for script in soup.find_all("script", src=True):
        src = script["src"]
        host = host_of(src) if "//" in src else ""
        if not host or _e_primeira_parte(host, alvo):
            continue  # relativo/primeira parte: fora do risco de CDN comprometido
        if not (script.get("integrity") and script.get("crossorigin") is not None):
            faltando = "integrity" if not script.get("integrity") else "crossorigin"
            sem_sri.append(f"{src} (sem {faltando})")

    assert not sem_sri, (
        f"{len(sem_sri)} script(s) de terceiro sem Subresource Integrity: {sem_sri[:5]}"
        "\nCDN comprometido executa código arbitrário na página e pode exfiltrar "
        "formulários (Art. 46 — segurança). Fixe a versão e publique o hash."
    )


def test_fonts_cdn_recebem_ip(network_log, settings):
    """Fontes servidas por CDN externo entregam o IP do visitante ao terceiro."""
    hosts = {
        h for h in network_log.hosts()
        if any(h == f or h.endswith("." + f) for f in _FONTES_EXTERNAS)
    }
    if hosts:
        pytest.xfail(
            f"Fontes carregadas de CDN externo: {sorted(hosts)}. Cada visitante "
            "entrega IP e User-Agent ao terceiro sem escolha (Art. 5º I) — houve "
            "condenação nesse cenário na Europa (Google Fonts, LG München 2022). "
            "Sinal informativo: auto-hospedar a fonte remove o tratamento."
        )
