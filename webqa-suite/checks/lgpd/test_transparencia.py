"""Transparência: política acessível, direitos do titular e canal do encarregado.

LGPD Art. 9º (informação clara sobre o tratamento), Art. 18 (direitos do titular)
e Art. 41 (indicação do encarregado com identidade e canal de contato públicos).

Transparência é obrigação, não melhoria: ausência de política REPROVA. O que a
suíte não faz é julgar a qualidade jurídica do texto — verifica que ele existe,
está alcançável e menciona o que a lei manda mencionar.
"""
import re
import unicodedata
from urllib.parse import urljoin

import pytest
from bs4 import BeautifulSoup

pytestmark = pytest.mark.lgpd

_MIN_CHARS_POLITICA = 1500

# Termos em pt e en: "privacy policy" vale tanto quanto "política de privacidade".
_FORTE = re.compile(r"(?i)privacidade|privacy")
_FRACO = re.compile(r"(?i)pol[ií]tica|policy|termos|terms|legal")

# Direitos do Art. 18 e seus equivalentes usuais em inglês (texto já sem acento).
_DIREITOS = {
    "acesso": ("acesso", "access"),
    "correção": ("correcao", "corrigir", "retificacao", "correction", "rectification"),
    "eliminação": ("eliminacao", "exclusao", "excluir", "apagar", "deletion", "erasure"),
    "portabilidade": ("portabilidade", "portability"),
    "revogação": ("revogacao", "revogar", "retirar o consentimento", "withdraw"),
}
_MIN_DIREITOS = 3

_ENCARREGADO = ("encarregado", "dpo", "data protection officer", "protecao de dados")
_EMAIL_NO_TEXTO = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _sem_acento(texto: str) -> str:
    normal = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normal if not unicodedata.combining(c)).lower()


def encontrar_link_politica(soup, base: str) -> str | None:
    """URL absoluta da política, ou None. Função pura — verificada em tests/.

    Dois níveis de confiança: "privacidade/privacy" no texto ou no href vence
    "política/terms/legal", que só entra se não houver candidato forte.
    """
    fortes, fracos = [], []
    for a in soup.find_all("a", href=True):
        alvo = f"{a.get_text(' ', strip=True)} {a['href']}"
        if _FORTE.search(alvo):
            fortes.append(a["href"])
        elif _FRACO.search(alvo):
            fracos.append(a["href"])
    candidatos = fortes or fracos
    return urljoin(base, candidatos[0]) if candidatos else None


def e_pdf(url: str, content_type: str) -> bool:
    return "pdf" in (content_type or "").lower() or url.lower().split("?")[0].endswith(".pdf")


@pytest.fixture(scope="module")
def link_politica(soup, home_response) -> str | None:
    return encontrar_link_politica(soup, str(home_response.url))


@pytest.fixture(scope="module")
def politica(link_politica, client):
    """(url, soup, texto) da política — pula quando não é HTML analisável."""
    if not link_politica:
        pytest.skip("Sem link de política na home (reprovado em test_politica_acessivel).")
    try:
        resp = client.get(link_politica)
    except Exception as exc:
        pytest.skip(f"Política inacessível ({type(exc).__name__}) — ver test_politica_acessivel.")
    if resp.status_code != 200:
        pytest.skip(f"Política respondeu {resp.status_code} — ver test_politica_acessivel.")

    if e_pdf(link_politica, resp.headers.get("content-type", "")):
        pytest.skip(
            "Política publicada em PDF: fora do alcance deste parser (só HTML). "
            "Limite conhecido — avalie manualmente. PDF também prejudica leitor "
            "de tela (LBI Art. 63) e a 'linguagem clara e acessível' do Art. 9º."
        )

    doc = BeautifulSoup(resp.text, "lxml")
    return link_politica, doc, doc.get_text(" ", strip=True)


def test_politica_acessivel(link_politica, client):
    """Existe link para a política e ele leva a um documento de fato."""
    assert link_politica, (
        "Nenhum link de política de privacidade encontrado no HTML da home. "
        "Informar o titular sobre o tratamento é obrigação (LGPD Art. 9º), "
        "não item de roadmap."
    )
    resp = client.get(link_politica)
    assert resp.status_code == 200, (
        f"Link da política responde {resp.status_code} — política inalcançável "
        "equivale a política inexistente para o titular."
    )
    tipo = resp.headers.get("content-type", "").lower()
    if e_pdf(link_politica, tipo):
        pytest.skip(
            "Política em PDF: link existe e responde 200, mas o conteúdo está fora "
            "do alcance do parser (só HTML) — avalie manualmente."
        )
    if "html" not in tipo:
        pytest.skip(f"Política servida como '{tipo}': parser HTML não avalia o conteúdo.")

    texto = BeautifulSoup(resp.text, "lxml").get_text(" ", strip=True)
    assert len(texto) > _MIN_CHARS_POLITICA, (
        f"Política com apenas {len(texto)} chars de texto útil "
        f"(< {_MIN_CHARS_POLITICA}) — provável página vazia, placeholder ou "
        "conteúdo carregado só por JS."
    )


def test_direitos_do_titular(politica):
    """A política menciona ao menos 3 dos direitos do Art. 18."""
    _, _, texto = politica
    normalizado = _sem_acento(texto)
    presentes = [d for d, termos in _DIREITOS.items() if any(t in normalizado for t in termos)]
    ausentes = [d for d in _DIREITOS if d not in presentes]
    assert len(presentes) >= _MIN_DIREITOS, (
        f"Política menciona apenas {len(presentes)} direito(s) do titular "
        f"({presentes or 'nenhum'}); ausentes: {ausentes}. "
        "O Art. 18 exige informar acesso, correção, eliminação, portabilidade e "
        "revogação do consentimento."
    )


def test_canal_encarregado(politica):
    """Encarregado (DPO) identificado E com canal de contato na própria página."""
    url, doc, texto = politica
    normalizado = _sem_acento(texto)
    mencionado = [t for t in _ENCARREGADO if t in normalizado]
    assert mencionado, (
        f"A política ({url}) não menciona encarregado/DPO. O Art. 41 §1º exige "
        "identidade e informações de contato divulgadas publicamente."
    )

    tem_mailto = bool(doc.find("a", href=re.compile(r"(?i)^mailto:")))
    tem_email = bool(_EMAIL_NO_TEXTO.search(texto))
    tem_formulario = bool(doc.find("form"))
    assert tem_mailto or tem_email or tem_formulario, (
        "Encarregado citado, mas sem canal de contato na página (nenhum mailto:, "
        "e-mail no texto ou formulário). Art. 41 §1º — canal é parte da obrigação. "
        "O endereço encontrado NÃO é reproduzido neste relatório (minimização)."
    )
