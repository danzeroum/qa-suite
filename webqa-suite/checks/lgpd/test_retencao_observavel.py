"""Retenção observável, privilégio mínimo de permissões e canal de incidente.

Correção de uma premissa comum: "retenção não é testável de fora" é apenas
parcialmente verdadeiro. A VIDA ÚTIL DE UM COOKIE é política de retenção
declarada no protocolo (Max-Age/Expires) — logo, observável e testável.
Cookie de 2 anos declara intenção de retenção por 2 anos (Art. 15/16: dado
eliminado ao fim do tratamento).

Também aqui, dois acréscimos regulatórios de custo zero:
* Permissions-Policy — privilégio mínimo observável (negar câmera, microfone e
  geolocalização por default).
* security.txt (RFC 9116) — canal público de reporte apoia o dever de comunicar
  incidente à ANPD e aos titulares (Art. 48).
"""
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

import pytest

pytestmark = pytest.mark.lgpd

# 400 dias é o teto que os navegadores já aplicam ao Max-Age; declarar mais que
# isso é, ao mesmo tempo, ineficaz e declaração de retenção indefinida.
_LIMITE_DIAS_FALHA = 400
# Acima de 180 dias sem finalidade declarada é sinal, não infração provada.
_LIMITE_DIAS_AVISO = 180

_PERMISSOES_SENSIVEIS = ("geolocation", "camera", "microphone")


def _duracao_em_dias(header: str) -> float | None:
    """Vida útil declarada no Set-Cookie, em dias.

    None = cookie de sessão (sem Max-Age/Expires, ou data ilegível — na dúvida,
    a favor do alvo: não se reprova por cabeçalho que não se consegue ler).
    Valor <= 0 = deleção de cookie, tratada como sessão.
    """
    partes = [p.strip() for p in header.split(";")[1:]]
    max_age = expires = None
    for parte in partes:
        chave, _, valor = parte.partition("=")
        chave = chave.strip().lower()
        if chave == "max-age":
            try:
                max_age = float(valor.strip())
            except ValueError:
                max_age = None
        elif chave == "expires":
            try:
                data = parsedate_to_datetime(valor.strip())
            except (TypeError, ValueError):
                continue
            if data is None:
                continue
            if data.tzinfo is None:
                data = data.replace(tzinfo=UTC)
            expires = (data - datetime.now(UTC)).total_seconds()

    # RFC 6265: Max-Age tem precedência sobre Expires.
    segundos = max_age if max_age is not None else expires
    if segundos is None or segundos <= 0:
        return None
    return segundos / 86400


def _nome_do_cookie(header: str) -> str:
    return header.split("=", 1)[0].strip() or "cookie-sem-nome"


def test_cookies_expiracao(home_response):
    """Nenhum cookie declara vida útil além do teto de 400 dias."""
    cabecalhos = home_response.headers.get_list("set-cookie")
    if not cabecalhos:
        pytest.skip("Nenhum Set-Cookie na home — nada a avaliar.")

    excessivos, longos = [], []
    for header in cabecalhos:
        dias = _duracao_em_dias(header)
        if dias is None:  # sessão ou deleção: sem retenção declarada
            continue
        rotulo = f"{_nome_do_cookie(header)} ({dias:.0f} dias)"
        if dias > _LIMITE_DIAS_FALHA:
            excessivos.append(rotulo)
        elif dias >= _LIMITE_DIAS_AVISO:
            longos.append(rotulo)

    assert not excessivos, (
        f"Cookie(s) com vida útil acima de {_LIMITE_DIAS_FALHA} dias: {excessivos}. "
        "Retenção deve terminar com a finalidade (Art. 15/16) e os navegadores já "
        "truncam o prazo — a declaração é ineficaz e indica retenção indefinida."
    )
    if longos:
        pytest.xfail(
            f"Cookie(s) entre {_LIMITE_DIAS_AVISO} e {_LIMITE_DIAS_FALHA} dias: {longos}. "
            "Prazo longo não é infração por si — confronte com a finalidade declarada "
            "na política."
        )


def test_permissions_policy(home_response):
    """Privilégio mínimo observável: negar sensores por default."""
    header = home_response.headers.get("permissions-policy") or home_response.headers.get(
        "feature-policy", ""
    )
    if not header:
        pytest.xfail(
            "Sem Permissions-Policy: câmera, microfone e geolocalização ficam "
            "disponíveis a qualquer script (inclusive de terceiro) até o navegador "
            "pedir permissão. Sinal de maturidade — privilégio mínimo por default."
        )

    baixo = header.lower()
    ausentes = [p for p in _PERMISSOES_SENSIVEIS if p not in baixo]
    if ausentes:
        pytest.xfail(
            f"Permissions-Policy presente, mas sem diretiva para: {ausentes}. "
            f"Recomendado: 'geolocation=(), camera=(), microphone=()'. Header atual: {header[:200]}"
        )


def test_security_txt(client, home_response):
    """Canal público de reporte de vulnerabilidade (RFC 9116)."""
    base = str(home_response.url)
    tentativas = [
        urljoin(base, "/.well-known/security.txt"),
        urljoin(base, "/security.txt"),  # local legado, ainda aceito na prática
    ]
    for url in tentativas:
        try:
            resp = client.get(url)
        except Exception:
            continue
        if resp.status_code == 200 and "contact:" in resp.text.lower():
            return

    pytest.xfail(
        "Sem /.well-known/security.txt com campo 'Contact:' (RFC 9116). Um canal "
        "público de reporte encurta o tempo entre descoberta e correção — apoio "
        "direto ao dever de comunicar incidente (Art. 48). Sinal, não obrigação."
    )
