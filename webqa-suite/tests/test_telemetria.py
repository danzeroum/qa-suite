"""VERIFICAÇÃO da telemetria operacional (OS-31).

Sem rede e sem dependência externa: os `summary.json` são fabricados em
`tmp_path`, que é onde as bordas interessantes (flake contra o mesmo alvo,
alternância entre alvos diferentes) são testáveis de fato.

A telemetria é um produto de dados sobre a PRÓPRIA suíte. As duas invariantes
que estes testes protegem são de privacidade, não de aritmética:

* **agregado versionável nunca carrega alvo nominal** — `anonimizar_agregado`
  é obrigatório antes de qualquer saída que possa ser publicada;
* **`--calibrar` nunca escreve no `config.yaml`** — um limiar que se ajusta
  sozinho ao que mediu converge para aprovar tudo.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.telemetria import (
    agregar,
    anonimizar_agregado,
    carregar_summaries,
    distribuicao_por_check,
    flake_por_teste,
    main,
    ranking_de_lentos,
    sha_do_alvo,
    sugerir_thresholds,
)

pytestmark = pytest.mark.verification

RAIZ = Path(__file__).resolve().parent.parent
ALVO_A = "https://example.com"
ALVO_B = "https://www.mozilla.org"


def _res(test, estado="passed", duracao=0.5, dimension="backend"):
    return {"test": test, "dimension": dimension, "estado": estado,
            "outcome": estado, "duration_s": duracao, "detail": ""}


def _summary(alvo, results, metricas=None):
    return {"generated_at": "2026-07-30 03:00:00", "alvo": alvo,
            "results": results, "metricas": metricas or {}}


def _escrever(raiz: Path, host: str, n: int, summary: dict) -> None:
    destino = raiz / host / f"run{n}"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "summary.json").write_text(json.dumps(summary), encoding="utf-8")


# ---------- leitura ----------

def test_varre_summaries_e_anota_a_origem(tmp_path):
    """Número sem procedência não é auditável: quem lê a mediana precisa poder
    voltar ao arquivo que a produziu."""
    _escrever(tmp_path, "example.com", 1, _summary(ALVO_A, [_res("a.py::t")]))
    _escrever(tmp_path, "example.com", 2, _summary(ALVO_A, [_res("a.py::t")]))

    summaries = carregar_summaries(tmp_path)
    assert len(summaries) == 2
    assert all("_origem" in s for s in summaries)


def test_artefato_truncado_nao_derruba_a_conta(tmp_path):
    _escrever(tmp_path, "example.com", 1, _summary(ALVO_A, [_res("a.py::t")]))
    quebrado = tmp_path / "example.com" / "run2"
    quebrado.mkdir(parents=True)
    (quebrado / "summary.json").write_text("{isto não é json", encoding="utf-8")

    assert len(carregar_summaries(tmp_path)) == 1


# ---------- corte 1: lentos ----------

def test_ranking_de_lentos_por_mediana():
    summaries = [
        _summary(ALVO_A, [_res("lento.py::t", duracao=9.0), _res("rapido.py::t", duracao=0.1)]),
        _summary(ALVO_A, [_res("lento.py::t", duracao=11.0), _res("rapido.py::t", duracao=0.3)]),
    ]
    ranking = ranking_de_lentos(summaries)
    assert ranking[0]["test"] == "lento.py::t"
    assert ranking[0]["mediana"] == 10.0
    assert ranking[-1]["test"] == "rapido.py::t"


def test_percentil_nao_e_inventado_com_amostra_pequena():
    """Dizer 'p95 de duas amostras' seria dar precisão que o dado não tem."""
    poucas = ranking_de_lentos([_summary(ALVO_A, [_res("a.py::t", duracao=1.0)])])[0]
    assert "p95" not in poucas and poucas["n"] == 1

    muitas = ranking_de_lentos([_summary(ALVO_A, [_res("a.py::t", duracao=float(i))])
                            for i in range(1, 9)])[0]
    assert "p75" in muitas and "p95" in muitas


# ---------- corte 2: flake ----------

def test_alternancia_contra_o_mesmo_alvo_e_flake():
    summaries = [
        _summary(ALVO_A, [_res("oscila.py::t", "passed")]),
        _summary(ALVO_A, [_res("oscila.py::t", "failed")]),
        _summary(ALVO_A, [_res("oscila.py::t", "passed")]),
    ]
    flake = flake_por_teste(summaries)
    assert len(flake) == 1
    assert flake[0]["test"] == "oscila.py::t"
    assert flake[0]["alvo_sha256"] == sha_do_alvo(ALVO_A)
    assert flake[0]["passed"] == 2 and flake[0]["falhou"] == 1


def test_teste_estavel_nao_aparece_no_ranking():
    summaries = [_summary(ALVO_A, [_res("firme.py::t", "passed")]) for _ in range(4)]
    assert flake_por_teste(summaries) == []


def test_veredito_diferente_entre_ALVOS_nao_e_flake():
    """É comportamento do alvo, não da suíte.

    Um site que reprova e outro que passa não são a suíte oscilando — é a mesma
    distinção que dá sentido ao ledger de estabilidade.
    """
    summaries = [
        _summary(ALVO_A, [_res("check.py::t", "passed")]),
        _summary(ALVO_B, [_res("check.py::t", "failed")]),
    ]
    assert flake_por_teste(summaries) == []


def test_error_isolado_nao_e_flake():
    """Flake exige ALTERNÂNCIA, não incidente. Um `error` sem nenhum `passed` do
    mesmo teste contra o mesmo alvo é uma falha — pode ser infraestrutura, pode
    ser o alvo — mas não é instabilidade."""
    summaries = [_summary(ALVO_A, [_res("quebrado.py::t", "error")]) for _ in range(3)]
    assert flake_por_teste(summaries) == []


def test_error_alternando_com_passed_conta():
    summaries = [
        _summary(ALVO_A, [_res("infra.py::t", "passed")]),
        _summary(ALVO_A, [_res("infra.py::t", "error")]),
    ]
    assert [f["test"] for f in flake_por_teste(summaries)] == ["infra.py::t"]


def test_skip_e_xfail_nao_contam_como_flake():
    """Pular por ausência de formulário na página não é instabilidade."""
    summaries = [
        _summary(ALVO_A, [_res("opcional.py::t", "passed")]),
        _summary(ALVO_A, [_res("opcional.py::t", "skipped")]),
        _summary(ALVO_A, [_res("opcional.py::t", "xfail")]),
    ]
    assert flake_por_teste(summaries) == []


# ---------- corte 3: distribuição ----------

def test_check_que_reprova_em_alvo_e_candidato_a_falso_positivo():
    summaries = [
        _summary(ALVO_A, [_res("severo.py::t", "passed")]),
        _summary(ALVO_B, [_res("severo.py::t", "failed")]),
    ]
    linha = next(x for x in distribuicao_por_check(summaries) if x["test"] == "severo.py::t")
    assert linha["reprovou_em"] == 1
    assert linha["candidato_a_falso_positivo"] is True


def test_check_que_passa_em_tudo_e_candidato_a_check_morto():
    summaries = [_summary(f"https://alvo{i}.example", [_res("frouxo.py::t", "passed")])
                 for i in range(3)]
    linha = distribuicao_por_check(summaries)[0]
    assert linha["alvos"] == 3
    assert linha["candidato_a_check_morto"] is True


def test_passar_em_dois_alvos_nao_basta_para_suspeitar():
    """Base insuficiente não vira suspeita — é a regra 2.1 aplicada aqui:
    ausência de evidência não é evidência."""
    summaries = [_summary(f"https://alvo{i}.example", [_res("novo.py::t", "passed")])
                 for i in range(2)]
    assert distribuicao_por_check(summaries)[0]["candidato_a_check_morto"] is False


# ---------- anonimização ----------

def test_agregado_anonimo_nao_contem_nome_de_alvo():
    """A invariante que permite versionar ou publicar o agregado."""
    summaries = [_summary(ALVO_A, [_res("a.py::t")]),
                 _summary(ALVO_B, [_res("a.py::t")])]
    nominal = agregar(summaries)
    assert "mozilla.org" in json.dumps(nominal), "o nominal DEVE ter o nome (é local)"

    anonimo = json.dumps(anonimizar_agregado(nominal), ensure_ascii=False)
    for nome in ("mozilla", "example.com", "https://"):
        assert nome not in anonimo, f"{nome!r} vazou para o agregado anônimo"
    assert sha_do_alvo(ALVO_B) in anonimo, "o sha agrupa sem nomear e deve ficar"


def test_anonimizacao_remove_origens_porque_o_caminho_carrega_o_host(tmp_path):
    """`report/campanha/www.mozilla.org/run1/` tem o host no nome do diretório —
    um campo de rastreabilidade que reintroduz o nome anularia o resto."""
    _escrever(tmp_path, "www.mozilla.org", 1, _summary(ALVO_B, [_res("a.py::t")]))
    dados = agregar(carregar_summaries(tmp_path))
    assert "mozilla" in json.dumps(dados)

    assert "origens" not in anonimizar_agregado(dados)
    assert "mozilla" not in json.dumps(anonimizar_agregado(dados))


def test_anonimizar_nao_muda_os_cortes():
    """Anonimizar tira identificação, não informação: os três cortes seguem."""
    summaries = [_summary(ALVO_A, [_res("a.py::t", "passed")]),
                 _summary(ALVO_A, [_res("a.py::t", "failed")])]
    nominal = agregar(summaries)
    anonimo = anonimizar_agregado(nominal)
    for corte in ("ranking_de_lentos", "flake", "distribuicao_por_check", "metricas"):
        assert anonimo[corte] == nominal[corte]
    assert anonimo["anonimizado"] is True


# ---------- calibração ----------

def test_calibrar_nao_escreve_no_config(tmp_path, capsys):
    """Limiar que se ajusta sozinho ao que mediu converge para aprovar tudo."""
    config = RAIZ / "config.yaml"
    antes = hashlib.md5(config.read_bytes()).hexdigest() if config.exists() else None

    for n in range(1, 6):
        _escrever(tmp_path, "example.com", n,
                  _summary(ALVO_A, [_res("a.py::t")], {"ttfb_ms": 100.0 * n}))

    assert main(["--campanha", str(tmp_path), "--saida", str(tmp_path / "t.json"),
                 "--calibrar"]) == 0
    saida = capsys.readouterr().out
    assert "ttfb_ms" in saida
    assert "NADA foi escrito" in saida

    depois = hashlib.md5(config.read_bytes()).hexdigest() if config.exists() else None
    assert antes == depois, "config.yaml foi tocado pela calibração"


def test_sugestao_diz_quando_nao_ha_amostra():
    linhas = "\n".join(sugerir_thresholds({"metricas": {}}))
    assert "sem amostra suficiente" in linhas or "Nenhuma métrica" in linhas


def test_sugestao_aplica_folga_sobre_o_p75():
    dados = {"metricas": {"sha": {"ttfb_ms": {"p75": 100.0}}}}
    linhas = "\n".join(sugerir_thresholds(dados))
    assert "120" in linhas, "p75 × 1.20 deveria sugerir 120"


# ---------- CLI ----------

def test_sem_summaries_sai_com_erro_claro_e_sem_stacktrace(tmp_path, capsys):
    vazio = tmp_path / "campanha"
    vazio.mkdir()
    assert main(["--campanha", str(vazio), "--saida", str(tmp_path / "t.json")]) == 1
    erro = capsys.readouterr().err
    assert "nenhum summary.json" in erro
    assert "Traceback" not in erro


def test_diretorio_inexistente_sai_com_erro_claro(tmp_path, capsys):
    assert main(["--campanha", str(tmp_path / "nao-existe"),
                 "--saida", str(tmp_path / "t.json")]) == 1
    assert "não existe" in capsys.readouterr().err


def test_fluxo_completo_gera_os_tres_cortes(tmp_path):
    _escrever(tmp_path, "example.com", 1,
              _summary(ALVO_A, [_res("a.py::t", "passed", 2.0)], {"ttfb_ms": 90.0}))
    _escrever(tmp_path, "example.com", 2,
              _summary(ALVO_A, [_res("a.py::t", "failed", 3.0)], {"ttfb_ms": 110.0}))
    _escrever(tmp_path, "www.mozilla.org", 1,
              _summary(ALVO_B, [_res("a.py::t", "passed", 1.0)], {"ttfb_ms": 200.0}))
    saida = tmp_path / "telemetria.json"

    assert main(["--campanha", str(tmp_path), "--saida", str(saida)]) == 0
    dados = json.loads(saida.read_text(encoding="utf-8"))
    assert dados["execucoes"] == 3
    assert dados["ranking_de_lentos"] and dados["flake"] and dados["distribuicao_por_check"]
    assert dados["flake"][0]["alvo_sha256"] == sha_do_alvo(ALVO_A)


def test_flag_anonimo_grava_sem_nome(tmp_path):
    _escrever(tmp_path, "www.mozilla.org", 1, _summary(ALVO_B, [_res("a.py::t")]))
    saida = tmp_path / "anon.json"

    assert main(["--campanha", str(tmp_path), "--saida", str(saida), "--anonimo"]) == 0
    assert "mozilla" not in saida.read_text(encoding="utf-8")


# ---------- fronteira de dado ----------

def test_telemetria_so_le_chaves_agregadas():
    """Prova estrutural: nenhum caminho aqui toca corpo, PII ou header.

    A borda de escrita já sanitiza o `detail`, e a telemetria nem o lê — opera
    sobre `test`, `dimension`, `estado` e `duration_s`. Este teste existe para
    que um acréscimo futuro precise passar por ele.
    """
    fonte = (RAIZ / "scripts" / "telemetria.py").read_text(encoding="utf-8")
    for proibido in ('"detail"', "['detail']", '"headers"', '"cookies"',
                     "ler_corpo", "httpx", "requests"):
        assert proibido not in fonte, (
            f"telemetria não pode alcançar {proibido!r}: ela agrega o que já foi "
            "gravado, e ampliar o que ela lê amplia o que ela pode vazar.")
