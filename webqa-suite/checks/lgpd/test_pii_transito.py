"""PII em trânsito: dado pessoal não pode viajar em URL nem sair do domínio.

Riscos cobertos:
* Query string com CPF/e-mail vaza para log de servidor, proxy, CDN e histórico
  do navegador — e para o header Referer de TODO terceiro carregado na página
  (Art. 6º VII e VIII, Art. 46).
* Formulário com campo pessoal em GET põe o dado na URL; sem HTTPS, põe na rede.

Método: 100% PASSIVO — lê o HTML entregue. Nenhum formulário é submetido
(sondagem ativa exige WEBQA_ACTIVE_PROBES_AUTHORIZED, Fase 2).
"""
import re
from urllib.parse import urljoin

import pytest

from webqa.sanitize import find_pii, safe_url

pytestmark = pytest.mark.lgpd

# Parâmetro cujo NOME já denuncia o conteúdo, mesmo que o valor não case regex
# (ex.: ?cpf=00000000000 de teste, ?email=<vazio-no-render>).
_PARAM_PESSOAL = re.compile(r"(?i)[?&](cpf|e-?mail|telefone|phone|celular)=([^&#\s]+)")

# Campos de formulário que carregam dado pessoal (name/id).
_CAMPO_PESSOAL = re.compile(r"(?i)(nome|e-?mail|cpf|telefone|phone|celular)")

_REFERRER_ACEITAVEIS = {
    "no-referrer",
    "same-origin",
    "strict-origin",
    "strict-origin-when-cross-origin",
}


def _urls_da_pagina(soup) -> list[str]:
    urls = [a.get("href") for a in soup.find_all(href=True)]
    urls += [t.get("src") for t in soup.find_all(src=True)]
    return [u for u in urls if u and not u.startswith(("javascript:", "data:", "#"))]


def test_pii_em_query_string(soup, home_response):
    """Nenhum link/recurso da home carrega dado pessoal na query string."""
    base = str(home_response.url)
    ofensores = []
    for url in _urls_da_pagina(soup):
        absoluta = urljoin(base, url)
        tipos = find_pii(absoluta)
        param = _PARAM_PESSOAL.search(absoluta)
        if param:
            tipos = sorted(set(tipos) | {param.group(1).lower()})
        if tipos:
            # safe_url remove a query INTEIRA: o relatório mostra onde está o
            # problema sem reproduzir o dado do titular.
            ofensores.append(f"{safe_url(absoluta)} ({', '.join(tipos)})")

    ofensores = sorted(set(ofensores))
    assert not ofensores, (
        f"{len(ofensores)} URL(s) com dado pessoal na query string "
        f"(vaza para logs, CDN, histórico e Referer de terceiros): {ofensores[:5]}"
        "\nCorreção: mover o dado para o corpo de um POST ou usar identificador opaco."
    )


def test_referrer_policy(home_response, soup):
    """Sem política de referrer, cada terceiro carregado recebe a URL completa."""
    valor = home_response.headers.get("referrer-policy", "").strip().lower()
    if not valor:
        meta = soup.find("meta", attrs={"name": re.compile(r"(?i)^referrer$")})
        valor = (meta.get("content", "") if meta else "").strip().lower()

    if not valor:
        pytest.xfail(
            "Sem Referrer-Policy (header nem meta): o navegador aplica o default "
            "do fabricante e a URL completa pode ir para terceiros. Sinal de "
            "maturidade — não é obrigação legal direta."
        )

    # Declarada é diferente de ausente: escolher explicitamente uma política
    # permissiva (unsafe-url) é decisão de vazar, e isso reprova.
    politicas = {p.strip() for p in valor.split(",") if p.strip()}
    assert politicas & _REFERRER_ACEITAVEIS, (
        f"Referrer-Policy '{valor}' expõe a URL de origem a terceiros. "
        f"Use uma de: {sorted(_REFERRER_ACEITAVEIS)}."
    )


def test_forms_pii_post_https(soup, home_response):
    """Formulário com campo pessoal exige POST e action em HTTPS."""
    forms = soup.find_all("form")
    if not forms:
        pytest.skip("Página sem formulários — nada a avaliar aqui.")

    base = str(home_response.url)
    avaliados, problemas = 0, []
    for form in forms:
        campos = [
            c for c in form.find_all(("input", "textarea", "select"))
            if _CAMPO_PESSOAL.search(f"{c.get('name', '')} {c.get('id', '')}")
        ]
        if not campos:
            continue
        avaliados += 1
        # Action vazio/relativo resolve contra a URL da página: só assim dá para
        # afirmar o esquema de verdade.
        destino = urljoin(base, form.get("action") or "")
        metodo = (form.get("method") or "get").strip().lower()
        rotulo = safe_url(destino)
        if metodo != "post":
            problemas.append(f"{rotulo}: method={metodo} põe o dado na URL")
        if not destino.lower().startswith("https://"):
            problemas.append(f"{rotulo}: action fora de HTTPS")

    if not avaliados:
        pytest.skip("Nenhum formulário com campo pessoal (nome/e-mail/CPF/telefone).")

    assert not problemas, (
        f"Formulários com dado pessoal mal configurados (Art. 46 — segurança): {problemas[:5]}"
    )
