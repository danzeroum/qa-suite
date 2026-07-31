"""VERIFICAÇÃO do escopo (a trava da Fase C). Sem rede: yaml em tmp e getaddrinfo dublado.

O que se prova aqui é a fronteira que a Revisão 3 fixou: autorizar `alvo.com` NÃO
autoriza `www.alvo.com` nem `cdn.alvo.com`. Um detector de escopo que casasse por
sufixo ou reusasse `mesma_origem` passaria em quase tudo e só falharia contra alvo
real — o modo de falha que este arquivo existe para impedir.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from webqa import escopo

pytestmark = pytest.mark.verification

RAIZ = Path(__file__).resolve().parent.parent


def _escrever(tmp_path, origem="https://meusite.exemplo.br", ambiente="homologacao",
              data=None, extra="") -> Path:
    data = data or date.today().isoformat()
    p = tmp_path / "escopo-autorizado.yaml"
    p.write_text(
        "alvos:\n"
        f"  - origem: \"{origem}\"\n"
        "    autorizado_por: \"analista\"\n"
        f"    data: \"{data}\"\n"
        "    evidencia: \"pr#42\"\n"
        f"    ambiente: \"{ambiente}\"\n"
        f"{extra}",
        encoding="utf-8")
    return p


# ---------- a fronteira que importa: origem EXATA ----------

def test_origem_exata_esta_no_escopo(tmp_path):
    esc = escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br"))
    assert esc.esta_no_escopo("https://meusite.exemplo.br/qualquer/caminho")


def test_www_e_subdominio_reprovam_quando_so_o_apex_esta_listado(tmp_path):
    """O coração da B3.1: apex autorizado não estende a www nem a cdn."""
    esc = escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br"))
    assert not esc.esta_no_escopo("https://www.meusite.exemplo.br/")
    assert not esc.esta_no_escopo("https://cdn.meusite.exemplo.br/")
    assert not esc.esta_no_escopo("https://api.meusite.exemplo.br/")


def test_host_de_terceiro_reprova(tmp_path):
    esc = escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br"))
    assert not esc.esta_no_escopo("https://evil.example.com/")


# ---------- C2 proibida em produção ----------

def test_producao_nao_permite_escrita(tmp_path):
    esc = escopo.carregar(_escrever(tmp_path, ambiente="producao"))
    assert esc.esta_no_escopo("https://meusite.exemplo.br/")
    assert not esc.permite_escrita("https://meusite.exemplo.br/")


def test_homologacao_permite_escrita(tmp_path):
    esc = escopo.carregar(_escrever(tmp_path, ambiente="homologacao"))
    assert esc.permite_escrita("https://meusite.exemplo.br/")


# ---------- fail-fast no carregamento ----------

def test_arquivo_ausente_bloqueia(tmp_path):
    with pytest.raises(FileNotFoundError):
        escopo.carregar(tmp_path / "nao-existe.yaml")


def test_sem_alvos_reprova(tmp_path):
    p = tmp_path / "vazio.yaml"
    p.write_text("alvos: []\n", encoding="utf-8")
    with pytest.raises(ValueError):
        escopo.carregar(p)


def test_data_futura_reprova(tmp_path):
    amanha = (date.today() + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError):
        escopo.carregar(_escrever(tmp_path, data=amanha))


def test_ambiente_invalido_reprova(tmp_path):
    with pytest.raises(ValueError):
        escopo.carregar(_escrever(tmp_path, ambiente="prod"))


def test_http_reprova_exige_https(tmp_path):
    with pytest.raises(ValueError):
        escopo.carregar(_escrever(tmp_path, "http://meusite.exemplo.br"))


def test_origem_nao_canonica_reprova(tmp_path):
    # porta padrão explícita: origem_de a remove, então a entrada não é canônica
    with pytest.raises(ValueError):
        escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br:443"))


def test_gov_e_bloqueado(tmp_path):
    with pytest.raises(ValueError):
        escopo.carregar(_escrever(tmp_path, "https://orgao.gov.br"))


def test_origem_duplicada_reprova(tmp_path):
    p = tmp_path / "dup.yaml"
    entrada = ('  - origem: "https://a.exemplo.br"\n'
               '    autorizado_por: "x"\n'
               f'    data: "{date.today().isoformat()}"\n'
               '    evidencia: "e"\n'
               '    ambiente: "sandbox"\n')
    p.write_text("alvos:\n" + entrada + entrada, encoding="utf-8")
    with pytest.raises(ValueError):
        escopo.carregar(p)


# ---------- congelamento (TOCTOU) ----------

def test_hash_congelado_muda_com_o_conteudo(tmp_path):
    h1 = escopo.carregar(_escrever(tmp_path, "https://a.exemplo.br")).hash_congelado
    h2 = escopo.carregar(_escrever(tmp_path, "https://b.exemplo.br")).hash_congelado
    assert h1 != h2 and len(h1) == 64


# ---------- os alvos de TERCEIRO da campanha nunca entram no escopo ----------

def test_alvos_de_terceiro_da_campanha_reprovam_escopo(tmp_path):
    """Invariante do §C do plano, agora com prova: a campanha passiva é de
    terceiros e não pode ser sondada ativamente."""
    import yaml
    campanha = yaml.safe_load((RAIZ / "campanha.yaml").read_text(encoding="utf-8"))
    esc = escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br"))
    for alvo in campanha["alvos"]:
        assert not esc.esta_no_escopo(alvo["url"]), (
            f"{alvo['url']} é alvo passivo de terceiro — nunca deve estar no escopo ativo")
