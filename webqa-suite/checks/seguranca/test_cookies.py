"""Fase A — atributos de segurança dos cookies observados.

Ver `docs/SEGURANCA.md` §5. Complementa a dimensão `lgpd`, que olha RETENÇÃO
(quanto tempo o cookie dura); aqui se olha PROTEÇÃO (quem consegue ler e enviar).
São perguntas diferentes sobre o mesmo objeto, e nenhuma responde a outra.

Severidade **média** nos três FAILs daqui, e a diferença para os `alta` da
dimensão é o que separa risco realizado de risco condicionado: cookie sem
`HttpOnly` só vira incidente se houver um XSS; sem `Secure`, só num downgrade.
São pré-condições que a bateria não observa. Chamar isso de alta esvaziaria o
rótulo justamente onde ele precisa significar "aja hoje" — ver §8 do desenho.

**O valor do cookie nunca entra em nada.** Os checks leem `name` e os atributos
booleanos; o valor sequer é lido do log. Não é regra de estilo: cookie de sessão
É a credencial, e reproduzi-la num laudo entrega a conta junto com o diagnóstico.
"""
from __future__ import annotations

import pytest

from webqa.dominio import Finding, registrar_achados

pytestmark = [pytest.mark.seguranca, pytest.mark.browser]

# Cookie de sessão/autenticação pelo nome — heurística conservadora e auditável.
# Errar para menos aqui é melhor que reprovar um cookie de preferência de tema.
NOMES_SENSIVEIS = ("session", "sess", "sid", "auth", "token", "jwt", "login", "remember")


def _sensivel(nome: str) -> bool:
    minusculo = nome.lower()
    return any(marca in minusculo for marca in NOMES_SENSIVEIS)


def _achado(nome: str, tipo: str, evidencia: str) -> Finding:
    """Finding de cookie: identificado por NOME, nunca por valor.

    `recurso` recebe `cookie:<nome>` em vez de uma URL porque é isso que
    identifica o achado — a mesma página serve todos os cookies, e apontar a URL
    diria ao leitor onde olhar sem dizer o que corrigir.
    """
    return Finding(tipo=tipo, recurso=f"cookie:{nome}", severidade="media",
                   evidencia=evidencia, fase="A")


def test_samesite_none_sempre_com_secure(network_log, request):
    """`SameSite=None` sem `Secure` — FAIL, e o mais inequívoco desta bateria.

    `SameSite=None` autoriza o cookie a viajar em requisição de terceiro; sem
    `Secure` ele viaja também em claro. A combinação é rejeitada por navegadores
    modernos, então além de insegura ela simplesmente NÃO FUNCIONA — o alvo tem
    um cookie que acredita estar enviando e não está.
    """
    achados = [_achado(c.get("name", "?"), "cookie-samesite-none-sem-secure",
                       "SameSite=None declarado sem Secure")
               for c in network_log.cookies
               if str(c.get("sameSite", "")).lower() == "none" and not c.get("secure")]

    registrar_achados(request.node.nodeid, achados)
    assert not achados, (
        f"{len(achados)} cookie(s) com SameSite=None e sem Secure:\n  "
        + "\n  ".join(str(a) for a in achados[:5])
        + "\nCombinação inválida: trafega em claro e é descartada por navegadores "
          "modernos — risco e defeito funcional no mesmo atributo."
    )


def test_cookies_de_sessao_sao_httponly(network_log, request):
    """Cookie de sessão legível por JavaScript — FAIL.

    Sem `HttpOnly`, qualquer XSS na página lê a sessão e a exfiltra. É a diferença
    entre um XSS que desfigura e um XSS que assume a conta.
    """
    sensiveis = [c for c in network_log.cookies if _sensivel(str(c.get("name", "")))]
    if not sensiveis:
        pytest.skip("Nenhum cookie de sessão/autenticação identificado pelo nome.")
    achados = [_achado(c.get("name", "?"), "cookie-sessao-sem-httponly",
                       "cookie de sessão sem HttpOnly")
               for c in sensiveis if not c.get("httpOnly")]

    registrar_achados(request.node.nodeid, achados)
    assert not achados, (
        f"{len(achados)} cookie(s) de sessão sem HttpOnly:\n  "
        + "\n  ".join(str(a) for a in achados[:5])
        + "\nLegíveis por JavaScript, logo exfiltráveis por qualquer XSS na página."
    )


def test_cookies_de_sessao_sao_secure(network_log, request):
    """`Secure` em cookie de sessão. Só faz sentido cobrar de alvo https."""
    if not network_log.url.lower().startswith("https://"):
        pytest.skip("Alvo servido por http:// — `Secure` não é exigível "
                    "(o navegador nem aceitaria o atributo).")
    sensiveis = [c for c in network_log.cookies if _sensivel(str(c.get("name", "")))]
    if not sensiveis:
        pytest.skip("Nenhum cookie de sessão/autenticação identificado pelo nome.")
    achados = [_achado(c.get("name", "?"), "cookie-sessao-sem-secure",
                       "cookie de sessão sem Secure em alvo https")
               for c in sensiveis if not c.get("secure")]

    registrar_achados(request.node.nodeid, achados)
    assert not achados, (
        f"{len(achados)} cookie(s) de sessão sem Secure:\n  "
        + "\n  ".join(str(a) for a in achados[:5])
        + "\nPodem ser enviados por http em um downgrade, expondo a sessão em claro."
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
