"""Crawler funcional: links internos não podem estar quebrados (nível: sistema).

Limitado por config (crawl.max_pages) para respeitar o alvo — teste é
diagnóstico, não ataque.

Três disciplinas de etiqueta, e nenhuma é opcional (`webqa/etiqueta.py`,
`docs/CAMPANHA.md §etiqueta`):

* **sequencial.** Uma página por vez, sempre. O laço abaixo é síncrono de
  propósito: paralelizar o crawl transformaria diagnóstico em rajada. Os assets
  de UMA página seguem carregando em paralelo pelo navegador — isso é
  comportamento de visitante e não é crawl;
* **robots.txt.** Caminho que o dono do alvo pediu para não rastrear é pulado
  com motivo, e os permitidos seguem. Alvo de rede local (o fixture) é isento:
  é nosso e fabricado;
* **recuo.** `429`/`503` encerram o crawl daquele alvo na hora. Reinsistir
  depois de o servidor pedir para parar é cortesia virando ataque lento.
"""
import time
from urllib.parse import urljoin, urlparse

import pytest

from webqa.auth import origem_de
from webqa.etiqueta import PoliteFetcher, motivo_do_recuo, resposta_pede_recuo
from webqa.sanitize import safe_url

pytestmark = pytest.mark.functional


def _internal_links(soup, base, host):
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(base + "/", href).split("#")[0]
        if urlparse(url).netloc == host:
            seen.add(url)
    return seen


def test_links_internos_sem_quebrados(client, soup, settings, credencial):
    host = urlparse(settings.target_url).netloc
    fila = list(_internal_links(soup, settings.target_url, host))[: settings.crawl_max_pages]

    # A credencial vai junto SÓ para a origem do alvo (`webqa/auth.py`): sem ela,
    # o `robots.txt` de um alvo protegido responde 401 e esta dimensão inteira
    # deixava de produzir veredito. Terceiro alcançado no crawl segue anônimo.
    fetcher = PoliteFetcher(settings.user_agent, timeout_s=settings.timeout_s,
                            credencial=credencial,
                            origem_do_alvo=origem_de(settings.target_url))
    veredito = fetcher.preparar(settings.target_url)
    if veredito.bloqueado:
        pytest.skip(f"crawl não autorizado pelo alvo: {veredito.motivo}")

    quebrados, pulados = [], []
    for indice, url in enumerate(fila):
        if not fetcher.pode_acessar(url):
            pulados.append(f"{safe_url(url)} — {fetcher.motivo_do_bloqueio(url)}")
            continue
        # Uma página por vez, com o intervalo que o próprio alvo pediu. O sleep
        # fica ENTRE requisições, nunca antes da primeira: cortesia não é atraso
        # gratuito.
        if indice and veredito.crawl_delay_s:
            time.sleep(veredito.crawl_delay_s)
        try:
            resp = client.head(url)
            if resp.status_code >= 405:  # HEAD não suportado
                resp = client.get(url)
        except Exception as exc:
            quebrados.append((safe_url(url), f"erro: {type(exc).__name__}"))
            continue
        if resposta_pede_recuo(resp.status_code):
            # Encerra o crawl DESTE alvo. Não é link quebrado — é o servidor
            # dizendo para parar, e a resposta correta é parar.
            pulados.append(f"{safe_url(url)} — {motivo_do_recuo(resp.status_code)}")
            break
        if resp.status_code >= 400:
            quebrados.append((safe_url(url), resp.status_code))

    if pulados and not quebrados:
        pytest.xfail(
            f"{len(pulados)} caminho(s) não rastreados por etiqueta, e nenhum link "
            "quebrado entre os permitidos: " + "; ".join(pulados[:5]))
    assert not quebrados, (
        f"{len(quebrados)} links internos quebrados:\n"
        + "\n".join(f"  {u} -> {s}" for u, s in quebrados)
        + ("" if not pulados
           else f"\nNão rastreados por etiqueta ({len(pulados)}): " + "; ".join(pulados[:5]))
    )


def test_links_externos_declarados_com_seguranca(soup):
    """target=_blank sem rel=noopener é risco (tab-nabbing)."""
    problematicos = [
        a.get("href", "?")[:80]
        for a in soup.find_all("a", href=True)
        if a.get("target") == "_blank" and "noopener" not in " ".join(a.get("rel", []))
    ]
    assert not problematicos, (
        f"{len(problematicos)} links _blank sem rel=noopener: {problematicos[:5]}"
    )
