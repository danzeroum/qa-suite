"""VERIFICAÇÃO: o axe-core só entra na página se for o axe-core esperado.

O par versão+hash é controle de SEGURANÇA. A suíte injeta script de terceiro no
DOM da página sob teste; um CDN comprometido teria execução arbitrária ali. A
verificação existe para isso, e a distinção que ela precisa manter é fina:

* **rede indisponível** é ausência de medida — o chamador pula, com motivo;
* **hash divergente** é o CDN entregando outra coisa. Tratar isso como "não deu
  para medir" esconderia exatamente o evento que a verificação detecta.

Sem rede: o cliente é dublado.
"""
import hashlib

import pytest

from webqa.axe import (
    AXE_CDN,
    AXE_SHA384,
    baixar_axe_verificado,
    resumo_de_violacoes,
    violacoes_por_impacto,
)

pytestmark = pytest.mark.verification

_CONTEUDO = b"// axe-core de mentira, mas com hash proprio\n"


class _ClienteFalso:
    def __init__(self, conteudo=_CONTEUDO, status=200):
        self._conteudo = conteudo
        self._status = status
        self.pedidos = []

    def get(self, url):
        self.pedidos.append(url)
        return _RespostaFalsa(self._conteudo, self._status)


class _RespostaFalsa:
    def __init__(self, conteudo, status):
        self.content = conteudo
        self.text = conteudo.decode("utf-8")
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


# ---------- Integridade ----------

def test_hash_divergente_e_erro_e_o_script_nao_e_injetado(monkeypatch):
    """O caso que dá nome ao módulo: o CDN entregou outra coisa.

    `AssertionError`, e não skip: o chamador em `checks/` re-levanta
    `AssertionError` de propósito e só transforma OUTRAS exceções em skip. Se
    isto virasse skip, um CDN comprometido apareceria no laudo como "não foi
    possível medir acessibilidade" — e ninguém investigaria.
    """
    with pytest.raises(AssertionError) as erro:
        baixar_axe_verificado(_ClienteFalso())
    assert "Integridade do axe-core FALHOU" in str(erro.value)
    assert "NÃO foi injetado" in str(erro.value)


def test_hash_correto_devolve_o_texto(monkeypatch):
    monkeypatch.setattr("webqa.axe.AXE_SHA384", hashlib.sha384(_CONTEUDO).hexdigest())
    assert baixar_axe_verificado(_ClienteFalso()) == _CONTEUDO.decode("utf-8")


def test_erro_de_rede_sobe_como_erro_de_rede():
    """Não vira `AssertionError`: o chamador precisa distinguir os dois para
    escolher entre pular e reprovar."""
    with pytest.raises(RuntimeError):
        baixar_axe_verificado(_ClienteFalso(status=503))


def test_baixa_a_versao_pinada():
    """Subir a versão sem subir o hash tem de reprovar, e o único jeito de isso
    valer é a URL ser fixa e conferida."""
    cliente = _ClienteFalso()
    with pytest.raises(AssertionError):
        baixar_axe_verificado(cliente)
    assert cliente.pedidos == [AXE_CDN]
    assert "4.9.1" in AXE_CDN, "a versão é pinada na URL"
    assert len(AXE_SHA384) == 96, "sha384 em hex tem 96 caracteres"


# ---------- Leitura do resultado ----------

def test_filtra_por_impacto():
    resultado = {"violations": [{"id": "a", "impact": "serious"},
                                {"id": "b", "impact": "minor"},
                                {"id": "c", "impact": "serious"}]}
    assert [v["id"] for v in violacoes_por_impacto(resultado, "serious")] == ["a", "c"]


def test_resultado_sem_violacoes_nao_estoura():
    assert violacoes_por_impacto({}, "serious") == []


def test_resumo_traz_regra_seletor_e_a_razao_medida():
    """"Contraste insuficiente" sem os números não diz quanto falta — e quem
    corrige precisa saber se erra por pouco ou por muito."""
    violacoes = [{
        "id": "color-contrast",
        "nodes": [{
            "target": [".aviso-tema"],
            "any": [{"data": {"contrastRatio": 1.62, "fgColor": "#3a3a3a",
                              "bgColor": "#222222", "expectedContrastRatio": "4.5:1"}}],
        }],
    }]
    texto = resumo_de_violacoes(violacoes)
    assert "color-contrast — 1 nó(s), ex.: .aviso-tema" in texto
    assert "razão 1.62:1" in texto
    assert "#3a3a3a sobre #222222" in texto


def test_resumo_sem_dados_de_contraste_nao_inventa_numero():
    violacoes = [{"id": "label", "nodes": [{"target": ["#email"]}]}]
    texto = resumo_de_violacoes(violacoes)
    assert "label — 1 nó(s), ex.: #email" in texto
    assert "razão" not in texto


def test_resumo_trunca_dizendo_quantos_ficaram():
    violacoes = [{"id": f"regra-{i}", "nodes": []} for i in range(15)]
    assert "e mais 5" in resumo_de_violacoes(violacoes, teto=10)
