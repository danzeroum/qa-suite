"""VERIFICAÇÃO do escopo (a trava da Fase C). Sem rede: yaml em tmp e getaddrinfo dublado.

O que se prova aqui é a fronteira que a Revisão 3 fixou: autorizar `alvo.com` NÃO
autoriza `www.alvo.com` nem `cdn.alvo.com`. Um detector de escopo que casasse por
sufixo ou reusasse `mesma_origem` passaria em quase tudo e só falharia contra alvo
real — o modo de falha que este arquivo existe para impedir.
"""
from __future__ import annotations

import socket
from datetime import date, timedelta
from pathlib import Path

import pytest

from webqa import escopo

pytestmark = pytest.mark.verification

RAIZ = Path(__file__).resolve().parent.parent


def _dubla_getaddrinfo(monkeypatch, *ips: str) -> None:
    """Faz `getaddrinfo` devolver exatamente estes IPs — nenhuma consulta sai.

    Mesma técnica de `tests/test_fronteira_de_rede.py`: é o único jeito de
    exercitar a prova de posse (snapshot no carregamento e re-resolução) sem
    tocar a rede.
    """
    infos = [
        (socket.AF_INET6 if ":" in ip else socket.AF_INET,
         socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))
        for ip in ips
    ]
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p, *a, **k: infos)


def _falha_getaddrinfo(monkeypatch) -> None:
    def _erro(*_a, **_k):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", _erro)


@pytest.fixture(autouse=True)
def _sem_dns_real(monkeypatch):
    """Nenhuma consulta DNS real sai destes testes (regra da casa).

    O carregamento agora resolve para o snapshot de posse; sem este dublê, cada
    `carregar` bateria em DNS de verdade. Default: resolução falha → snapshot
    vazio. Os testes de posse instalam o próprio dublê antes de `carregar`,
    sobrescrevendo este (o último `setattr` no mesmo monkeypatch vence).
    """
    _falha_getaddrinfo(monkeypatch)


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


# ---------- prova de posse por IP (R-C6): takeover de subdomínio ----------
#
# TDD: o teste de divergência (o takeover) vem primeiro — é o modo de falha que
# a função existe para pegar. Um snapshot que só foi visto "bater" nunca provou
# que detecta a troca de dono.

def test_divergencia_de_ip_e_detectada_como_takeover(tmp_path, monkeypatch):
    """Snapshot num IP, host agora aponta para outro → posse recusada.

    É o caso R-C6: entre autorizar o host e sondá-lo, o DNS foi reapontado para
    infra de terceiro. Sondar assim atingiria quem não autorizou; a divergência
    tem de abortar, nunca passar batido."""
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7")           # baseline no carregamento
    esc = escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br"))
    _dubla_getaddrinfo(monkeypatch, "198.51.100.9")          # host trocou de dono
    assert esc.verificar_posse("meusite.exemplo.br") == frozenset()


def test_posse_ok_quando_o_ip_bate(tmp_path, monkeypatch):
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7")
    esc = escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br"))
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7")           # mesmo IP na re-verificação
    assert esc.verificar_posse("meusite.exemplo.br") == frozenset({"203.0.113.7"})


def test_falha_de_resolucao_agora_e_nao_posse_sem_excecao(tmp_path, monkeypatch):
    """Host resolvia no carregamento, agora não resolve → não-posse, sem
    exceção crua subindo. Na dúvida, o lado seguro é recusar o probe."""
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7")
    esc = escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br"))
    _falha_getaddrinfo(monkeypatch)
    assert esc.verificar_posse("meusite.exemplo.br") == frozenset()


def test_snapshot_grava_os_ips_no_carregamento(tmp_path, monkeypatch):
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7")
    esc = escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br"))
    assert esc.ips_no_carregamento["meusite.exemplo.br"] == frozenset({"203.0.113.7"})


def test_host_que_nao_resolveu_no_carregamento_nao_afirma_posse(tmp_path, monkeypatch):
    """Sem baseline (não resolveu no carregamento), `verificar_posse` recusa
    mesmo que agora resolva — posse se prova contra um snapshot, não do nada."""
    _falha_getaddrinfo(monkeypatch)                          # carrega sem baseline
    esc = escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br"))
    assert esc.ips_no_carregamento["meusite.exemplo.br"] == frozenset()
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7")
    assert esc.verificar_posse("meusite.exemplo.br") == frozenset()


def test_host_fora_do_escopo_nao_tem_posse(tmp_path, monkeypatch):
    """Host que não está no escopo nunca tem posse — não há baseline para ele."""
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7")
    esc = escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br"))
    assert esc.verificar_posse("outro-host.exemplo.br") == frozenset()


def test_posse_distingue_ip_parcialmente_coincidente(tmp_path, monkeypatch):
    """Conjunto que só coincide em parte é divergência: um IP novo no round-robin
    é exatamente o vetor de takeover que a igualdade estrita pega."""
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7", "203.0.113.8")
    esc = escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br"))
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7", "198.51.100.9")
    assert esc.verificar_posse("meusite.exemplo.br") == frozenset()


# ---------- G7: verificar_posse_detalhada distingue as 4 causas de "sem posse" ----------
#
# Hoje takeover, host não listado, snapshot vazio e falha de resolução agora são
# o MESMO frozenset() — um rótulo para quatro causas. A detalhada dá o motivo para
# o log do run (a sondagem o consome; escopo NÃO importa audit — fronteira §2.11).

def test_detalhada_posse_ok_devolve_ips_e_motivo_vazio(tmp_path, monkeypatch):
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7")
    esc = escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br"))
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7")
    assert esc.verificar_posse_detalhada("meusite.exemplo.br") == (
        frozenset({"203.0.113.7"}), "")


def test_detalhada_takeover(tmp_path, monkeypatch):
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7")
    esc = escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br"))
    _dubla_getaddrinfo(monkeypatch, "198.51.100.9")            # host reapontado
    assert esc.verificar_posse_detalhada("meusite.exemplo.br") == (frozenset(), "takeover")


def test_detalhada_host_nao_listado(tmp_path, monkeypatch):
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7")
    esc = escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br"))
    assert esc.verificar_posse_detalhada("outro-host.exemplo.br") == (
        frozenset(), "nao-listado")


def test_detalhada_sem_baseline(tmp_path, monkeypatch):
    """Host listado, mas não resolveu no carregamento (snapshot vazio) — não é
    takeover: nunca houve baseline contra o que comparar."""
    _falha_getaddrinfo(monkeypatch)                            # carrega sem baseline
    esc = escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br"))
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7")             # agora resolve
    assert esc.verificar_posse_detalhada("meusite.exemplo.br") == (
        frozenset(), "sem-baseline")


def test_detalhada_resolucao_falhou_agora(tmp_path, monkeypatch):
    """Resolveu no carregamento, agora não resolve — distinto de takeover."""
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7")
    esc = escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br"))
    _falha_getaddrinfo(monkeypatch)
    assert esc.verificar_posse_detalhada("meusite.exemplo.br") == (
        frozenset(), "resolucao-falhou")


def test_verificar_posse_mantem_assinatura_frozenset(tmp_path, monkeypatch):
    """A assinatura pública NÃO muda: quem chama continua lendo vazio = sem posse."""
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7")
    esc = escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br"))
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7")
    assert esc.verificar_posse("meusite.exemplo.br") == frozenset({"203.0.113.7"})
    _dubla_getaddrinfo(monkeypatch, "198.51.100.9")
    assert esc.verificar_posse("meusite.exemplo.br") == frozenset()


# ---------- C2 fatia 2b: posse por DNS-TXT (alternativa ao pino de IP, CDN) ----------

_VERIF_DNS_TXT = ('    verificacao:\n'
                  '      tipo: "dns_txt"\n'
                  '      valor: "webqa-ownership=abc123"\n')


def _dubla_txt(monkeypatch, *tokens: str) -> None:
    monkeypatch.setattr("webqa.escopo.txt_de", lambda h: frozenset(tokens))


def test_dns_txt_aprova_com_token_exato_mesmo_ip_rotacionado(tmp_path, monkeypatch):
    """CDN: IP rotaciona (seria takeover na posse por IP), mas o token TXT prova
    posse — aprova, pinando nos IPs ATUAIS (o pino de conexão da C1c permanece)."""
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7")                 # snapshot
    esc = escopo.carregar(_escrever(tmp_path, "https://cdn.exemplo.br", extra=_VERIF_DNS_TXT))
    _dubla_getaddrinfo(monkeypatch, "198.51.100.9")                # IP rotacionou
    _dubla_txt(monkeypatch, "webqa-ownership=abc123")
    assert esc.verificar_posse_detalhada("cdn.exemplo.br") == (frozenset({"198.51.100.9"}), "")


def test_dns_txt_recusa_sem_token(tmp_path, monkeypatch):
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7")
    esc = escopo.carregar(_escrever(tmp_path, "https://cdn.exemplo.br", extra=_VERIF_DNS_TXT))
    _dubla_txt(monkeypatch, "outra-coisa=1")
    assert esc.verificar_posse_detalhada("cdn.exemplo.br") == (frozenset(), "dns-txt-ausente")


def test_dns_txt_igualdade_exata_nao_substring(tmp_path, monkeypatch):
    """Token do alvo como SUBSTRING de outro TXT não basta — igualdade exata."""
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7")
    esc = escopo.carregar(_escrever(tmp_path, "https://cdn.exemplo.br", extra=_VERIF_DNS_TXT))
    _dubla_txt(monkeypatch, "x-webqa-ownership=abc123-y")          # token embutido
    assert esc.verificar_posse_detalhada("cdn.exemplo.br") == (frozenset(), "dns-txt-ausente")


def test_dns_txt_sem_resolucao_de_ip_e_resolucao_falhou(tmp_path, monkeypatch):
    """Mesmo com TXT, sem IP atual não há onde pinar → resolucao-falhou."""
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7")
    esc = escopo.carregar(_escrever(tmp_path, "https://cdn.exemplo.br", extra=_VERIF_DNS_TXT))
    _falha_getaddrinfo(monkeypatch)
    _dubla_txt(monkeypatch, "webqa-ownership=abc123")
    assert esc.verificar_posse_detalhada("cdn.exemplo.br") == (frozenset(), "resolucao-falhou")


def test_sem_dns_txt_mantem_posse_por_ip(tmp_path, monkeypatch):
    """Entrada sem verificacao dns_txt segue na posse por IP (takeover reprova)."""
    _dubla_getaddrinfo(monkeypatch, "203.0.113.7")
    esc = escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br"))
    _dubla_getaddrinfo(monkeypatch, "198.51.100.9")
    assert esc.verificar_posse_detalhada("meusite.exemplo.br") == (frozenset(), "takeover")


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


# ---------- Q1a: a autorização é uma foto congelada, não um objeto editável ----------

def test_toda_dataclass_do_escopo_e_congelada():
    """Guarda estrutural: modelo novo aqui nasce imutável, sem depender de lembrança.

    Testar `EntradaEscopo`/`Escopo` uma a uma protege o que existe hoje; varrer o
    módulo protege o que alguém acrescentar amanhã — mesmo padrão de
    test_convencoes.py e test_fronteira_de_rede.py."""
    import dataclasses
    import inspect

    mutaveis = [
        nome for nome, obj in vars(escopo).items()
        if inspect.isclass(obj) and dataclasses.is_dataclass(obj)
        and obj.__module__ == escopo.__name__
        and not obj.__dataclass_params__.frozen
    ]
    assert not mutaveis, (
        f"dataclass mutável em webqa/escopo.py: {mutaveis}. A autorização é um "
        "snapshot do carregamento; objeto editável em memória anula a prova de posse.")


def test_entrada_e_escopo_recusam_reatribuicao(tmp_path):
    """Comportamento, não só declaração: o `frozen=True` é verdade em runtime."""
    from dataclasses import FrozenInstanceError

    esc = escopo.carregar(_escrever(tmp_path, "https://meusite.exemplo.br"))
    entrada = esc.entradas[0]                       # construído FORA do raises

    with pytest.raises(FrozenInstanceError):
        entrada.origem = "https://invasor.exemplo.br"
    with pytest.raises(FrozenInstanceError):
        esc.entradas = ()
