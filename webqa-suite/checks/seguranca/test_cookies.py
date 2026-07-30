"""Fase A — atributos de segurança dos cookies observados.

Ver `docs/SEGURANCA.md` §5. Complementa a dimensão `lgpd`, que olha RETENÇÃO
(quanto tempo o cookie dura); aqui se olha PROTEÇÃO (quem consegue ler e enviar).
São perguntas diferentes sobre o mesmo objeto, e nenhuma responde a outra.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.seguranca, pytest.mark.browser]

# Cookie de sessão/autenticação pelo nome — heurística conservadora e auditável.
# Errar para menos aqui é melhor que reprovar um cookie de preferência de tema.
NOMES_SENSIVEIS = ("session", "sess", "sid", "auth", "token", "jwt", "login", "remember")


def _sensivel(nome: str) -> bool:
    minusculo = nome.lower()
    return any(marca in minusculo for marca in NOMES_SENSIVEIS)


def test_samesite_none_sempre_com_secure(network_log):
    """`SameSite=None` sem `Secure` — FAIL, e o mais inequívoco desta bateria.

    `SameSite=None` autoriza o cookie a viajar em requisição de terceiro; sem
    `Secure` ele viaja também em claro. A combinação é rejeitada por navegadores
    modernos, então além de insegura ela simplesmente NÃO FUNCIONA — o alvo tem
    um cookie que acredita estar enviando e não está.
    """
    ofensores = [c.get("name", "?") for c in network_log.cookies
                 if str(c.get("sameSite", "")).lower() == "none" and not c.get("secure")]
    assert not ofensores, (
        f"Cookie(s) com SameSite=None e sem Secure: {sorted(ofensores)}. "
        "Combinação inválida: trafega em claro e é descartada por navegadores "
        "modernos — risco e defeito funcional no mesmo atributo."
    )


def test_cookies_de_sessao_sao_httponly(network_log):
    """Cookie de sessão legível por JavaScript — FAIL.

    Sem `HttpOnly`, qualquer XSS na página lê a sessão e a exfiltra. É a diferença
    entre um XSS que desfigura e um XSS que assume a conta.
    """
    sensiveis = [c for c in network_log.cookies if _sensivel(str(c.get("name", "")))]
    if not sensiveis:
        pytest.skip("Nenhum cookie de sessão/autenticação identificado pelo nome.")
    expostos = [c.get("name") for c in sensiveis if not c.get("httpOnly")]
    assert not expostos, (
        f"Cookie(s) de sessão sem HttpOnly: {sorted(expostos)} — legíveis por "
        "JavaScript, logo exfiltráveis por qualquer XSS na página."
    )


def test_cookies_de_sessao_sao_secure(network_log):
    """`Secure` em cookie de sessão. Só faz sentido cobrar de alvo https."""
    if not network_log.url.lower().startswith("https://"):
        pytest.skip("Alvo servido por http:// — `Secure` não é exigível "
                    "(o navegador nem aceitaria o atributo).")
    sensiveis = [c for c in network_log.cookies if _sensivel(str(c.get("name", "")))]
    if not sensiveis:
        pytest.skip("Nenhum cookie de sessão/autenticação identificado pelo nome.")
    expostos = [c.get("name") for c in sensiveis if not c.get("secure")]
    assert not expostos, (
        f"Cookie(s) de sessão sem Secure: {sorted(expostos)} — podem ser enviados "
        "por http em um downgrade, expondo a sessão em claro."
    )


def test_cookies_declaram_samesite(network_log):
    """`SameSite` ausente — xfail, não FAIL.

    Navegadores atuais assumem `Lax` por omissão, então o risco concreto é baixo;
    declarar explicitamente é maturidade, e é assim que entra no relatório.
    """
    if not network_log.cookies:
        pytest.skip("Nenhum cookie definido no carregamento.")
    sem_declaracao = [c.get("name") for c in network_log.cookies
                      if not str(c.get("sameSite", "")).strip()]
    if sem_declaracao:
        pytest.xfail(
            f"{len(sem_declaracao)} cookie(s) sem SameSite explícito: "
            f"{sorted(sem_declaracao)[:5]}. O navegador assume Lax; declarar remove "
            "a dependência do padrão de cada fornecedor."
        )
