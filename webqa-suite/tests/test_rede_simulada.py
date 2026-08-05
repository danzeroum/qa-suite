"""VERIFICAÇÃO: a emulação de rede/CPU traduz o perfil certo e não vaza (OS-50).

Três perguntas, e a ordem é a do risco:

1. **a conversão está certa?** `downloadThroughput` do CDP é em BYTES por
   segundo e o perfil é declarado em kbps. Passar kbps direto emula uma rede
   OITO vezes mais rápida do que a declarada — e nada fica vermelho: o check
   roda, mede, e relata um alvo saudável sob uma condição que nunca aconteceu.
   É o defeito mais caro deste módulo porque é silencioso;
2. **a configuração sem sentido morre na porta?** Banda negativa, `cpu_fator`
   abaixo de 1 e nome com typo têm de falhar onde a mensagem ainda sabe qual
   chave está errada. Um typo que caísse no default produziria "rodou sem
   estrangular e passou";
3. **o estrangulamento morre com o contexto?** É o R20 em versão rede. Contexto
   estrangulado que contaminasse o vizinho faria `checks/frontend/` medir LCP sob
   3G sem declarar — número errado sem nada ficar vermelho.

A prova (3) é comportamental e roda em navegador, mas **sem rede**: um laço
computacional em `about:blank` basta, e a razão entre os tempos é o próprio
fator de throttling. A regra da casa de `tests/` ser livre de rede continua
valendo (mesma construção de `tests/test_gui_fixtures.py`).
"""
import pytest
import yaml

from webqa.rede_simulada import (
    COMANDO_CPU,
    COMANDO_REDE,
    PERFIL_PADRAO,
    PerfilDeRede,
    SemCDP,
    avaliar_bloqueio,
    avaliar_pintura,
    carregar_perfis_de_rede,
    estrangular,
    parametros_de_cpu,
    parametros_de_rede,
    perfil_de_rede,
)

pytestmark = pytest.mark.verification

_REFERENCIA = PerfilDeRede(nome="ref", download_kbps=1638.4, upload_kbps=750,
                           latencia_ms=150, cpu_fator=4)


def _yaml(tmp_path, corpo: dict):
    caminho = tmp_path / "perfis.yaml"
    caminho.write_text(yaml.safe_dump({"rede": corpo}), encoding="utf-8")
    return caminho


_MINIMO = {"download_kbps": 1000, "upload_kbps": 500, "latencia_ms": 100, "cpu_fator": 2}


# ---------- 1. a conversão ----------

def test_kbps_vira_bytes_por_segundo_e_nao_o_proprio_numero():
    """O erro clássico deste comando, derivado à mão: 1638.4 kbps = 1638400 bits/s
    = 204800 bytes/s. Passar 1638.4 emularia uma rede 8× mais rápida."""
    assert _REFERENCIA.download_bytes_por_s == pytest.approx(204800.0)
    assert _REFERENCIA.upload_bytes_por_s == pytest.approx(93750.0)


def test_parametros_de_rede_entregam_bytes_e_nao_kbps():
    """A tradução no ponto de uso, e não só na propriedade — é o dicionário que
    vai ao navegador que precisa estar certo."""
    p = parametros_de_rede(_REFERENCIA)
    assert p["downloadThroughput"] == pytest.approx(204800.0)
    assert p["uploadThroughput"] == pytest.approx(93750.0)
    assert p["latency"] == 150
    assert p["offline"] is False, (
        "`offline` verdadeiro faria este check virar o de perda de conexão da "
        "OS-47 — outra medida com este nome")


def test_parametros_de_cpu_usam_o_fator_declarado():
    assert parametros_de_cpu(_REFERENCIA) == {"rate": 4}


def test_perfil_de_referencia_do_repositorio_e_o_preset_movel_do_lighthouse():
    """A régua é herdada, não inventada: número próximo do Lighthouse produziria
    medidas que só conversam consigo mesmas."""
    perfil = carregar_perfis_de_rede()[PERFIL_PADRAO]
    assert (perfil.download_kbps, perfil.latencia_ms, perfil.cpu_fator) == (1638.4, 150.0, 4.0)


# ---------- 2. fail-closed na porta ----------

def test_latencia_zero_e_valida(tmp_path):
    """Rede perfeita é condição legítima — serve de perfil de controle. Recusá-la
    confundiria "sem latência" com "sem valor declarado", e é por isso que o
    mínimo de `latencia_ms` é 0 e o de `cpu_fator` é 1."""
    caminho = _yaml(tmp_path, {"controle": {**_MINIMO, "latencia_ms": 0}})
    assert carregar_perfis_de_rede(caminho)["controle"].latencia_ms == 0.0


def test_banda_negativa_e_erro_nomeando_a_chave(tmp_path):
    """Banda negativa o CDP traduz para "sem limite": a emulação silenciosamente
    não acontece e o check aprova fibra achando que mediu 3G."""
    caminho = _yaml(tmp_path, {"ruim": {**_MINIMO, "download_kbps": -1}})
    with pytest.raises(ValueError) as erro:
        carregar_perfis_de_rede(caminho)
    assert "download_kbps" in str(erro.value) and "ruim" in str(erro.value)


def test_cpu_abaixo_de_um_e_erro(tmp_path):
    """`rate` menor que 1 pediria ao navegador que rodasse MAIS RÁPIDO que a
    máquina — um perfil que não emula nada e cujo nome diz que emula."""
    caminho = _yaml(tmp_path, {"ruim": {**_MINIMO, "cpu_fator": 0.5}})
    with pytest.raises(ValueError, match="cpu_fator"):
        carregar_perfis_de_rede(caminho)


def test_chave_ausente_e_erro_dizendo_qual(tmp_path):
    incompleto = {k: v for k, v in _MINIMO.items() if k != "latencia_ms"}
    caminho = _yaml(tmp_path, {"ruim": incompleto})
    with pytest.raises(ValueError, match="latencia_ms"):
        carregar_perfis_de_rede(caminho)


def test_valor_nao_numerico_e_erro(tmp_path):
    caminho = _yaml(tmp_path, {"ruim": {**_MINIMO, "download_kbps": "rapido"}})
    with pytest.raises(ValueError, match="não é número"):
        carregar_perfis_de_rede(caminho)


def test_bloco_rede_vazio_e_erro(tmp_path):
    caminho = tmp_path / "vazio.yaml"
    caminho.write_text("viewports: {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="nenhum perfil de rede"):
        carregar_perfis_de_rede(caminho)


def test_typo_no_nome_reprova_e_lista_os_validos_inteiros():
    """A lista inteira, e não "nome inválido": quem errou precisa ver o que
    podia ter escrito, senão o erro custa uma segunda execução para descobrir."""
    perfis = {"3g_rapido": _REFERENCIA, "controle": PerfilDeRede("controle", 1, 1, 0, 1)}
    with pytest.raises(ValueError) as erro:
        perfil_de_rede("3g_rapdio", perfis)
    mensagem = str(erro.value)
    assert "3g_rapdio" in mensagem
    for valido in perfis:
        assert valido in mensagem, f"o erro não nomeia o perfil válido {valido!r}"


def test_nome_ausente_cai_no_padrao_e_nao_em_erro():
    perfis = {PERFIL_PADRAO: _REFERENCIA}
    assert perfil_de_rede(None, perfis) is _REFERENCIA
    assert perfil_de_rede("  ", perfis) is _REFERENCIA


# ---------- avaliadores puros ----------

def test_pintura_nao_medida_nao_vira_problema():
    """Ausência nunca vira zero nem veredito (`webqa/metricas.py`)."""
    assert avaliar_pintura(None, None, fcp_max=1800, lcp_max=2500) == []


def test_pintura_no_limite_exato_passa():
    """Comparador `>`: no valor exato o orçamento ainda está cumprido."""
    assert avaliar_pintura(1800, 2500, fcp_max=1800, lcp_max=2500) == []
    assert len(avaliar_pintura(1801, 2501, fcp_max=1800, lcp_max=2500)) == 2


def test_pintura_reporta_qual_dos_dois_estourou():
    problemas = avaliar_pintura(100, 9999, fcp_max=1800, lcp_max=2500)
    assert len(problemas) == 1 and "LCP" in problemas[0]


def test_bloqueio_no_limite_exato_passa():
    assert avaliar_bloqueio(200, tbt_max=200) == []
    assert avaliar_bloqueio(200.1, tbt_max=200) != []


# ---------- 3. a fronteira dos comandos ----------

def _ofensores_de_cdp(raiz) -> list[str]:
    """Arquivos sob `raiz` que pronunciam CDP por conta própria.

    Função separada — e não corpo do teste — para que a guarda possa ser
    exercitada contra um caso PLANTADO. Guarda que nunca reprovou nada é
    decoração, e a única forma de saber que esta reprova é fazê-la reprovar.
    """
    proibidos = (COMANDO_REDE, COMANDO_CPU, "Network.emulate", "setCPUThrottlingRate",
                 "new_cdp_session")
    ofensores = []
    for caminho in sorted(raiz.rglob("*.py")):
        texto = caminho.read_text(encoding="utf-8")
        for termo in proibidos:
            if termo in texto:
                ofensores.append(f"{caminho.name}: {termo}")
    return ofensores


def test_nenhum_check_pronuncia_comando_de_cdp():
    """Guarda estrutural, na lição de `_contextos_de_gui`.

    Detalhe de navegador espalhado por `checks/` diverge no primeiro campo novo,
    e a divergência aparece como um check estrangulando e o outro não — que é
    indistinguível, no laudo, de dois alvos com desempenho diferente.
    """
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    assert not _ofensores_de_cdp(raiz / "checks"), (
        "check falando CDP direto em vez de passar por webqa/rede_simulada.py: "
        f"{_ofensores_de_cdp(raiz / 'checks')}")


def test_a_guarda_de_cdp_pega_um_plantado(tmp_path):
    """O caso que motivou a guarda, plantado e pego."""
    (tmp_path / "test_plantado.py").write_text(
        f'sessao.send("{COMANDO_CPU}", {{"rate": 4}})\n', encoding="utf-8")
    # `in`, e não igualdade com uma lista de um item: o comando completo CONTÉM
    # o termo curto (`Emulation.setCPUThrottlingRate` ⊃ `setCPUThrottlingRate`),
    # então uma linha plantada casa com dois termos proibidos. A sobreposição é
    # de propósito — a guarda pega tanto o comando completo quanto o pedaço que
    # sobreviveria a um recorte — e cobrar contagem exata aqui fixaria um detalhe
    # da lista de termos em vez do comportamento que importa.
    ofensores = _ofensores_de_cdp(tmp_path)
    assert f"test_plantado.py: {COMANDO_CPU}" in ofensores


def test_engine_sem_cdp_levanta_erro_proprio():
    """`SemCDP` e não `Exception` genérica: o check precisa distinguir "esta
    engine não sabe estrangular" de "o alvo caiu". Confundir os dois faria uma
    queda do alvo sair do laudo como `skip` — o falso verde silencioso."""
    class _ContextoSemCDP:
        def new_cdp_session(self, _pagina):
            raise NotImplementedError("CDP is only supported in Chromium")

    class _Pagina:
        context = _ContextoSemCDP()

    with pytest.raises(SemCDP) as erro:
        estrangular(_Pagina(), _REFERENCIA)
    assert "chromium" in str(erro.value).lower()


def test_estrangular_habilita_a_rede_antes_de_emular():
    """`Network.emulateNetworkConditions` sem `Network.enable` é ignorado por
    alguns alvos do protocolo — a emulação não acontece e nada avisa."""
    enviados = []

    class _Sessao:
        def send(self, comando, params=None):
            enviados.append(comando)

    class _Contexto:
        def new_cdp_session(self, _pagina):
            return _Sessao()

    class _Pagina:
        context = _Contexto()

    estrangular(_Pagina(), _REFERENCIA)
    assert enviados[0] == "Network.enable"
    assert enviados[1:] == [COMANDO_REDE, COMANDO_CPU]
