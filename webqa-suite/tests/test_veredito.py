"""VERIFICAÇÃO do veredito do processo (frente E, E3).

O defeito tem DUAS formas, e as duas bancadas deste arquivo reproduzem cada uma
contra a suíte de verdade. A raiz é a mesma: **o código de saída do pytest não
tem como expressar o terceiro estado.**

* **exit 0 sem ter medido** — alvo no ar, nenhum navegador, os checks de `gui`
  pulam com motivo e o pytest sai **0**. Uma guarda que lesse aquele 0 concluiria
  "medi e está bom" sobre uma dimensão inteira que não rodou. É a lição do D6.
* **exit 1 sem ter medido** — alvo fora do ar: 58 checks viram `error` (a fixture
  estourou no setup) e QUATRO viram `failed`, porque os de pytest-bdd fazem a
  requisição dentro do próprio corpo e o ConnectError cai na fase `call`. O pytest
  sai 1, indistinguível de uma violação real, e quem contasse desfechos leria
  "4 violações" sobre um alvo que ninguém alcançou.

A segunda forma é a que a primeira redação deste arquivo não previa, e ela foi
MEDIDA aqui: é por isso que o preflight virou sinal explícito de sessão em vez de
inferência sobre a contagem.

**O par exit/laudo é o teste.** Não basta o código de saída estar certo: o laudo
que acompanha aquele exit precisa dizer a mesma coisa, porque o consumidor lê o
laudo e a guarda lê o exit. Aqui os dois são cobrados juntos, e a única razão de
eles não poderem divergir é estrutural — `webqa/report.py` carimba o veredito
chamando a MESMA função que `webqa-veredicto` usa para decidir o código.

**A bancada** (`test_a_bancada_do_alvo_fora_do_ar…`) roda a suíte de verdade contra
um alvo que não existe, em subprocesso, e confere o laudo REAL. Laudo fabricado
prova a tradução; só a bancada prova que o defeito medido produz o veredito certo.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from webqa.veredito import (
    CONFIG_INVALIDA,
    INDETERMINADO,
    SEM_VIOLACAO,
    VIOLACAO,
    avaliar,
    main,
)

pytestmark = pytest.mark.verification

RAIZ = Path(__file__).resolve().parent.parent


def laudo(*estados: str) -> dict:
    """Um summary com um resultado por estado pedido — a forma mínima que importa."""
    return {"results": [{"test": f"checks/x.py::t{i}", "estado": e, "outcome": e,
                         "dimension": "gui", "fase": "call"}
                        for i, e in enumerate(estados)]}


# ---------- Os três estados, e o quarto ----------

def test_alvo_limpo_sai_zero():
    v = avaliar(laudo("passed", "passed"))
    assert v.codigo == SEM_VIOLACAO
    assert not v.inconclusivo


def test_o_zero_nao_diz_conforme():
    """R10 escrito no MOTIVO, não só na documentação: quem lê o veredito não leu o doc."""
    v = avaliar(laudo("passed"))
    assert "não certifica" in v.motivo.lower() or "NÃO certifica" in v.motivo


def test_violacao_real_sai_dez():
    v = avaliar(laudo("passed", "failed"))
    assert v.codigo == VIOLACAO
    assert not v.inconclusivo


def test_tudo_pulado_sai_vinte():
    """O DEFEITO: com o alvo fora do ar o preflight derruba tudo em skip e o
    pytest sai 0. Aqui isso é indeterminado, e indeterminado bloqueia."""
    v = avaliar(laudo("skipped", "skipped", "skipped"))
    assert v.codigo == INDETERMINADO
    assert v.inconclusivo


def test_laudo_sem_nenhum_resultado_sai_vinte():
    """0 caminhos, 0 achados: a forma exata do "verde por não olhar"."""
    assert avaliar({"results": []}).codigo == INDETERMINADO


def test_erro_de_infraestrutura_sai_vinte():
    """`error` é o teste NÃO TENDO ACONTECIDO — não é veredito sobre o alvo."""
    v = avaliar(laudo("passed", "error"))
    assert v.codigo == INDETERMINADO


def test_laudo_ausente_ou_ilegivel_sai_trinta(tmp_path):
    """Laudo que não existe é CONFIGURAÇÃO. Nunca 0: 'não achei o laudo' saindo
    verde é o mesmo defeito uma camada acima."""
    assert main(["--laudo", str(tmp_path / "nao-existe.json"), "--quieto"]) == CONFIG_INVALIDA
    ruim = tmp_path / "summary.json"
    ruim.write_text("{isto não é json", encoding="utf-8")
    assert main(["--laudo", str(ruim), "--quieto"]) == CONFIG_INVALIDA


def test_laudo_de_outra_coisa_sai_trinta(tmp_path):
    """JSON válido que não é um summary desta suíte: legível, e ainda assim inútil."""
    outro = tmp_path / "summary.json"
    outro.write_text('{"alguma": "coisa"}', encoding="utf-8")
    assert main(["--laudo", str(outro), "--quieto"]) == CONFIG_INVALIDA


# ---------- As bordas da doutrina ----------

def test_xfail_nunca_vira_violacao():
    """xfail é AMBIENTE (origem declarada, engine instalada, tempo). Exportá-lo como
    achado transformaria "não afirmei" em "defeito medido"."""
    assert avaliar(laudo("passed", "xfail")).codigo == SEM_VIOLACAO


def test_xfail_sozinho_nao_conta_como_medicao():
    """E o outro lado: xfail também não prova que se mediu. Sem nenhum passed nem
    failed, o veredito é indeterminado — não 'sem violação'."""
    assert avaliar(laudo("xfail", "xfail")).codigo == INDETERMINADO


def test_skip_nunca_vira_violacao():
    """skip é NÃO AVALIADO. Não é conforme, e também não é achado."""
    assert avaliar(laudo("passed", "skipped")).codigo == SEM_VIOLACAO


def test_violacao_vence_indeterminacao_quando_a_sessao_mediu():
    """A ordem das perguntas é a decisão.

    Uma violação observada é observação, e não deixa de ser porque outra coisa não
    pôde ser medida. Rebaixá-la a indeterminado esconderia um achado real atrás de
    um problema de ambiente — e o problema de ambiente é o mais fácil de arrumar.

    O `passed` na amostra é o que torna a sessão medida: sem nenhum desfecho
    completo a conclusão é outra, e é o teste abaixo.
    """
    assert avaliar(laudo("passed", "failed", "error", "skipped")).codigo == VIOLACAO


def test_sessao_sem_nenhum_desfecho_completo_e_indeterminada():
    """A borda que a bancada revelou, e que a contagem sozinha erra.

    Contra uma porta fechada, os checks de pytest-bdd fazem a requisição DENTRO do
    corpo: o ConnectError cai na fase `call` e o laudo os registra como `failed`.
    Ler só a contagem produziria "violações" sobre um alvo que ninguém alcançou.
    Sem um único desfecho completo, um `failed` não se distingue do erro de
    infraestrutura que produziu os outros.
    """
    assert avaliar(laudo("failed", "error", "error")).codigo == INDETERMINADO


def test_o_preflight_reprovado_vence_qualquer_contagem():
    """E o sinal explícito, que não depende de inferência nenhuma.

    "O alvo foi alcançado?" é estado de SESSÃO. Com o preflight reprovado, nem um
    laudo cheio de `passed` seria veredito sobre o alvo — e é por isso que esta
    pergunta vem antes de todas as outras.
    """
    laudo_ = laudo("passed", "passed", "failed")
    laudo_["preflight"] = {"alcancado": False, "motivo": "ConnectError: connection refused"}
    v = avaliar(laudo_)
    assert v.codigo == INDETERMINADO
    assert v.inconclusivo
    assert "primeiro GET" in v.motivo


def test_o_preflight_alcancado_nao_atrapalha():
    """O outro lado: alvo alcançado devolve a decisão à contagem, onde ela mora."""
    laudo_ = laudo("passed", "failed")
    laudo_["preflight"] = {"alcancado": True, "motivo": "HTTP 200"}
    assert avaliar(laudo_).codigo == VIOLACAO


def test_conforme_e_indeterminado_nao_compartilham_codigo():
    """A propriedade que a entrega inteira existe para ter."""
    assert SEM_VIOLACAO != INDETERMINADO
    codigos = {SEM_VIOLACAO, VIOLACAO, INDETERMINADO, CONFIG_INVALIDA}
    assert len(codigos) == 4


def test_os_codigos_nao_colidem_com_os_do_pytest():
    """Escolha declarada: pytest usa 0–5 e os dois comandos correm no mesmo
    pipeline. Um código repetido faria quem lê o log atribuir ao pytest um veredito
    que é deste comando."""
    for codigo in (VIOLACAO, INDETERMINADO, CONFIG_INVALIDA):
        assert codigo > 5


# ---------- O par exit/laudo ----------

@pytest.mark.parametrize("estados,esperado", [
    (("passed",), SEM_VIOLACAO),
    (("failed",), VIOLACAO),
    (("skipped",), INDETERMINADO),
])
def test_o_exit_e_o_campo_do_laudo_saem_da_mesma_conta(tmp_path, estados, esperado):
    """Se laudo e exit fossem calculados em dois lugares, a primeira divergência
    entre eles seria justamente a que ninguém veria."""
    v = avaliar(laudo(*estados))
    caminho = tmp_path / "summary.json"
    caminho.write_text(json.dumps(laudo(*estados)), encoding="utf-8")
    assert main(["--laudo", str(caminho), "--quieto"]) == esperado == v.codigo
    assert v.inconclusivo == (esperado == INDETERMINADO)


# ---------- A bancada ----------

def test_a_bancada_do_alvo_fora_do_ar_sai_vinte_com_inconclusivo(tmp_path):
    """O defeito MEDIDO, ponta a ponta: alvo fora do ar → 0 medições → exit 20.

    Roda a suíte de verdade em subprocesso contra uma porta fechada. O pytest sai
    **0** (é o defeito, e ele continua ali de propósito — nada do exit do pytest
    mudou); o laudo que ele deixa diz `inconclusivo: true`; e `webqa-veredicto`
    sobre esse laudo sai 20.

    A seleção é `-m "not browser"` para não depender de Chromium: o que se exercita
    aqui é o preflight, e ele derruba a sessão inteira antes de qualquer navegador.
    """
    env = {
        **os.environ,
        "WEBQA_TARGET_URL": "http://127.0.0.1:9",   # porta 9 (discard): fechada por convenção
        "WEBQA_REPORT_DIR": str(tmp_path),
        "NO_PROXY": "*", "no_proxy": "*",
    }
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-m", "not browser and not load",
         "-p", "no:cacheprovider", "-q", "checks"],
        cwd=RAIZ, env=env, capture_output=True, text=True, timeout=900,
    )
    resumo = tmp_path / "summary.json"
    assert resumo.exists(), f"a suíte não deixou laudo.\n{proc.stdout[-2000:]}"
    dados = json.loads(resumo.read_text(encoding="utf-8"))

    # A bancada só vale se NENHUM check tiver completado contra o alvo. `failed`
    # aqui NÃO é medição: contra a porta fechada, os checks de pytest-bdd fazem a
    # requisição dentro do corpo e o ConnectError cai na fase `call`. É exatamente
    # a armadilha que o preflight explícito existe para desarmar.
    completos = [r for r in dados["results"] if r.get("estado") == "passed"]
    assert not completos, (
        f"a bancada só vale se nada tiver completado, e {len(completos)} check(s) passaram. "
        f"A porta 9 respondeu?")
    assert dados["preflight"]["alcancado"] is False, dados.get("preflight")
    assert dados["inconclusivo"] is True, dados.get("veredito")
    assert main(["--laudo", str(resumo), "--quieto"]) == INDETERMINADO

    # A ARMADILHA, medida: há `failed` neste laudo. Quem contasse desfechos leria
    # "violações" — achados sobre um alvo que ninguém alcançou. O veredito sai 20
    # apesar deles, e é essa discordância entre a contagem e o veredito que prova
    # que o preflight está decidindo.
    assert any(r["estado"] == "failed" for r in dados["results"]), (
        "a bancada perdeu o que ela tem de mais valioso: sem nenhum `failed` no laudo, "
        "ela não distingue o veredito pelo preflight de um veredito por contagem.")

    # E o exit do pytest segue exatamente onde estava: 1, porque houve falhas.
    # É a razão de existir desta entrega — o código do pytest não tem como expressar
    # o terceiro estado: 1 aqui é indistinguível de 1 numa violação de verdade, e 0
    # numa sessão toda pulada é indistinguível de 0 num alvo limpo. Se um dia esta
    # asserção quebrar, alguém mexeu no exit do pytest, e `make verify`, o ledger e
    # o `|| true` do entrypoint mudaram de significado junto.
    assert proc.returncode == 1, (
        f"o pytest saiu {proc.returncode}. O veredito do processo é do webqa-veredicto; "
        f"mexer no exit do pytest muda o significado de toda guarda que já o lê.")


def test_a_bancada_de_tudo_pulado_sai_vinte_com_o_pytest_em_zero(tmp_path):
    """O outro lado da mesma cegueira, e o que dá nome ao defeito: **exit 0**.

    Alvo NO AR (o fixture), seleção de navegador, e nenhum navegador instalado: os
    checks pulam com motivo, o pytest sai **0**, e uma guarda que lesse aquele 0
    concluiria "medi e está bom" sobre uma dimensão inteira que não rodou. É a
    lição do D6, que já custou um `quality-gate` verde sem ter conferido nada.

    O preflight aqui SUCEDE — é o que separa esta bancada da anterior. O que torna
    o run indeterminado não é o alvo estar fora, é ninguém ter medido.
    """
    from fixture_target.servir import AlvoFixture

    vazio = tmp_path / "sem-navegador"
    vazio.mkdir()
    with AlvoFixture() as alvo:
        env = {
            **os.environ,
            "WEBQA_TARGET_URL": alvo.url,
            "WEBQA_REPORT_DIR": str(tmp_path),
            "NO_PROXY": "*", "no_proxy": "*",
            # Sem navegador algum onde procurar: os checks de browser pulam com motivo.
            "PLAYWRIGHT_BROWSERS_PATH": str(vazio),
            "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1",
        }
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-m", "gui and not load",
             "-p", "no:cacheprovider", "-q", "checks"],
            cwd=RAIZ, env=env, capture_output=True, text=True, timeout=1800,
        )

    resumo = tmp_path / "summary.json"
    assert resumo.exists(), f"a suíte não deixou laudo.\n{proc.stdout[-2000:]}"
    dados = json.loads(resumo.read_text(encoding="utf-8"))

    assert proc.returncode == 0, (
        f"a bancada só vale se o pytest sair 0 (é o defeito), e ele saiu {proc.returncode}.\n"
        f"{proc.stdout[-2000:]}")
    # Nem preflight houve: sem navegador, os checks de `gui` pulam na fixture do
    # browser ANTES de alguém pedir o alvo. É o caso em que o sinal explícito não
    # existe, e é exatamente o que a regra de contagem cobre — nenhum desfecho
    # completo é indeterminado, com ou sem preflight registrado. Se esta bancada
    # exigisse o bloco, ela provaria a mesma coisa que a anterior.
    assert "preflight" not in dados, (
        f"esta bancada é sobre NINGUÉM CHEGAR A MEDIR, e o preflight rodou "
        f"({dados.get('preflight')}). A seleção mudou?")
    assert not [r for r in dados["results"] if r["estado"] in ("passed", "failed")], (
        "algum check mediu: sem isso a bancada não reproduz o verde por ausência.")
    assert dados["inconclusivo"] is True, dados.get("veredito")
    assert main(["--laudo", str(resumo), "--quieto"]) == INDETERMINADO
