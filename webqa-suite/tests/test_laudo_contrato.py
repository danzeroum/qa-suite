"""VERIFICAÇÃO do envelope de laudo do Contrato de Régua (frente E, E4).

O consumidor emitia `schema_version: 1.0` sem `verdict`, e por isso INFERIA o que
o laudo significava. Inferência não é laudo. Faltava também o *fingerprint*: sem
`(name, version, commit, catalog_hash, schema_version)` dois laudos não são
comparáveis, e a diferença entre um "0 achados" e outro não significa nada.

**O que estes testes travam, em ordem de importância:**

1. o envelope valida contra o `report.schema.json` da **contract-v1**, na cópia
   pinada por digest em `contrato/contract-v1/` — não contra uma leitura nossa dele;
2. os três estados produzem envelopes coerentes, e a coerência é cobrada nas duas
   direções que o schema trava (`suite_not_installed`/`error` só podem ser
   `inconclusivo`; `conforme` só pode acompanhar `result: ok`);
3. `xfailed` e `skipped` **nunca** viram achado — a borda mais cara da doutrina;
4. o envelope é **aditivo**: nenhum campo do summary desapareceu, e nenhum teste
   existente de report precisou ser editado para "caber".
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from webqa.laudo import SCHEMA_VERSION, fingerprint, montar

pytestmark = pytest.mark.verification

RAIZ = Path(__file__).resolve().parent.parent
CONTRATO = RAIZ / "contrato" / "contract-v1"


def summary(*estados: str, veredito: str = "", motivo: str = "porque sim") -> dict:
    """Um summary como `webqa/report.py` o monta, reduzido ao que o envelope lê."""
    from webqa.veredito import avaliar

    base = {
        "alvo": "https://exemplo.invalid",
        "dimension_notes": {"lgpd": "falha PROVA; passar NÃO certifica"},
        "results": [{"test": f"checks/x.py::t{i}", "estado": e, "outcome": e,
                     "dimension": "gui", "fase": "call", "detail": "" if e == "passed" else "d"}
                    for i, e in enumerate(estados)],
    }
    v = avaliar(base)
    base["veredito"] = {"estado": veredito or v.estado,
                        "motivo": motivo, "codigo_de_saida": v.codigo}
    base["inconclusivo"] = v.inconclusivo
    return base


def envelope(*estados: str, **kw) -> dict:
    return montar(summary(*estados, **kw),
                  catalog_hash="sha256:" + "a" * 64, commit="abc1234")


# ---------- A cópia pinada do contrato ----------

def test_o_contrato_pinado_confere_com_o_digest_declarado():
    """A cópia é consumida POR PIN, e o pin é o que a torna auditável.

    Sem esta conferência, `contrato/` seria uma cópia editável do que a régua tem
    de cumprir — a régua escrevendo a própria prova, que é o modo de falha que o
    contrato inteiro existe para negar.
    """
    procedencia = json.loads((CONTRATO / "PROCEDENCIA.json").read_text(encoding="utf-8"))
    for nome, dados in procedencia["arquivos"].items():
        medido = hashlib.sha256((CONTRATO / nome).read_bytes()).hexdigest()
        assert medido == dados["sha256"], (
            f"{nome} divergiu do digest declarado. Ou o contrato mudou sob os pés, ou alguém "
            f"editou a cópia — e as duas leituras pedem reações diferentes.")


def test_dois_arquivos_do_contrato_sao_os_mesmos_do_manifesto_do_consumidor():
    """A âncora forte: dois destes digests são os que o `contract-manifest.json` do
    consumidor declara. Se um dia divergirem, a régua está cumprindo outro contrato."""
    procedencia = json.loads((CONTRATO / "PROCEDENCIA.json").read_text(encoding="utf-8"))
    fixados = [n for n, d in procedencia["arquivos"].items() if d["no_manifesto_do_consumidor"]]
    assert sorted(fixados) == ["SUITE_CONTRACT.md", "report.schema.json"]


# ---------- O envelope valida ----------

@pytest.fixture(scope="module")
def validador():
    """O validador do envelope, contra o schema PINADO — nunca contra uma paráfrase."""
    jsonschema = pytest.importorskip("jsonschema", reason="jsonschema não instalado")
    referencing = pytest.importorskip("referencing")

    esquema = json.loads((CONTRATO / "report.schema.json").read_text(encoding="utf-8"))
    procedencia = json.loads((CONTRATO / "provenance.schema.json").read_text(encoding="utf-8"))
    # O envelope compõe a procedência por `$ref` relativo, e o registro é montado a
    # partir do `$id` do próprio arquivo pinado — resolver a referência por rede
    # buscaria o schema de OUTRO commit do consumidor, e a validação passaria a
    # falar de um contrato que não é o que está fixado aqui.
    registro = referencing.Resource.from_contents(procedencia) @ referencing.Registry()
    return jsonschema.Draft202012Validator(esquema, registry=registro)


@pytest.mark.parametrize("estados", [("passed", "passed"), ("passed", "failed"),
                                     ("skipped", "skipped"), ("passed", "error")])
def test_o_envelope_valida_contra_o_schema_do_contrato(validador, estados):
    erros = sorted(validador.iter_errors(envelope(*estados)), key=str)
    assert not erros, [f"{list(e.path)}: {e.message}" for e in erros]


def test_o_envelope_declara_schema_version_1_3(validador):
    """1.3 é a versão que EXIGE `verdict`. Declarar-se 1.0 com o campo, ou 1.3 sem
    ele, é o que o schema trava nas duas direções — a versão precisa dizer o que o
    laudo contém."""
    env = envelope("passed")
    assert env["schema_version"] == SCHEMA_VERSION == "1.3"
    assert "verdict" in env


# ---------- Os três estados ----------

@pytest.mark.parametrize("estados,veredito,resultado", [
    (("passed", "passed"), "conforme", "ok"),
    (("passed", "failed"), "nao_conforme", "findings"),
    (("skipped", "skipped"), "inconclusivo", "error"),
])
def test_os_tres_estados_saem_coerentes(estados, veredito, resultado):
    env = envelope(*estados)
    assert env["verdict"] == veredito
    assert env["result"] == resultado


def test_conforme_so_acompanha_result_ok():
    """A trava que vale contra o gesto deliberado, e não só contra o descuido."""
    for estados in [("passed", "failed"), ("skipped",), ("passed", "error")]:
        env = envelope(*estados)
        if env["verdict"] == "conforme":
            assert env["result"] == "ok"


def test_inconclusivo_viaja_no_envelope():
    """O booleano que o consumidor usa para não tratar "não medi" como "medi e passou"."""
    assert envelope("skipped")["summary"]["inconclusivo"] is True
    assert envelope("passed")["summary"]["inconclusivo"] is False


def test_a_nota_epistemica_sobrevive_ao_envelopamento():
    """R10 viaja com o veredito. Um envelope que só levasse `conforme` faria o
    consumidor ler a palavra sem a ressalva que a régua sempre imprimiu."""
    env = envelope("passed")
    assert "NÃO certifica" in env["summary"]["nota_epistemica"]
    assert env["summary"]["notas_por_dimensao"]["lgpd"]


# ---------- A borda mais cara ----------

def test_xfail_e_skip_nunca_viram_achado():
    """xfail é AMBIENTE, skip é NÃO-AVALIADO. Exportá-los transformaria "não
    afirmei" em "defeito medido" — a mentira mais cara que um laudo pode contar,
    porque tem a forma de uma evidência."""
    env = envelope("passed", "xfail", "skipped")
    assert env["findings"] == []


def test_error_nao_vira_achado_mas_vira_inconclusivo():
    """A terceira distinção: o teste NÃO TENDO ACONTECIDO não é achado nem aprovação."""
    env = envelope("passed", "error")
    assert env["findings"] == []
    assert env["verdict"] == "inconclusivo"


def test_so_failed_vira_achado():
    env = envelope("passed", "failed", "xfail", "skipped", "error")
    assert [f["id"] for f in env["findings"]] == ["checks/x.py::t1"]


def test_a_medida_registra_o_que_o_veredito_nao_exporta():
    """Medida ≠ veredito. `skipped` e `xfail` aparecem na contagem porque
    ACONTECERAM, e não em `findings` porque não são achado. Ausência nunca vira
    zero: estado que não ocorreu não tem chave."""
    contagem = envelope("passed", "xfail", "skipped")["summary"]["por_estado"]
    assert contagem == {"passed": 1, "xfail": 1, "skipped": 1}
    assert "failed" not in contagem


# ---------- Fingerprint ----------

def test_o_fingerprint_tem_os_cinco_campos():
    fp = fingerprint("sha256:" + "b" * 64, "deadbee")
    assert sorted(fp) == ["catalog_hash", "commit", "name", "schema_version", "version"]
    assert all(fp.values()), fp


def test_o_fingerprint_do_envelope_e_o_mesmo_do_summary():
    """`catalog_hash` é o nome GERAL do que a procedência chama de
    `sensitive_paths_hash`: o contrato nomeia a categoria, não o caso."""
    env = envelope("passed")
    fp = fingerprint("sha256:" + "a" * 64, "abc1234")
    assert env["standard"]["name"] == fp["name"]
    assert env["standard"]["version"] == fp["version"]
    assert env["standard"]["commit"] == fp["commit"]
    assert env["standard"]["sensitive_paths_hash"] == fp["catalog_hash"]
    assert env["schema_version"] == fp["schema_version"]


def test_catalogo_ausente_e_nomeado_nunca_vazio(monkeypatch):
    """String vazia passaria por qualquer comparação de igualdade com outra string
    vazia — dois laudos "sem catálogo" pareceriam da mesma régua."""
    from webqa import report

    monkeypatch.setattr(report, "REPORT_DIR", report.REPORT_DIR)
    hash_ = report._catalog_hash()
    assert hash_ and (hash_.startswith("sha256:") or hash_ == "UNAVAILABLE")


# ---------- Aditividade ----------

def test_o_summary_nao_perdeu_nada(tmp_path, monkeypatch):
    """Envelope ADITIVO: quem já lia `results`, `by_dimension` e `metricas` continua
    lendo. Nenhum teste existente de report foi editado para caber num schema."""
    from webqa import report

    monkeypatch.setattr(report, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(report, "_RESULTS", [
        {"test": "checks/x.py::t", "dimension": "gui", "dimensions": ["gui"], "browser": False,
         "outcome": "passed", "estado": "passed", "fase": "call", "duration_s": 0.1,
         "detail": ""}])

    class SessaoFalsa:
        class config:
            class invocation_params:
                args = ()

    report.pytest_sessionfinish(SessaoFalsa(), 0)
    dados = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    for chave in ("generated_at", "duration_s", "alvo", "comando", "by_dimension",
                  "dimension_notes", "metricas", "results"):
        assert chave in dados, f"o summary perdeu `{chave}` — isto não é aditivo"
    for chave in ("veredito", "inconclusivo", "fingerprint"):
        assert chave in dados, f"o summary não ganhou `{chave}`"
    assert (tmp_path / "laudo.json").exists(), "o envelope do contrato não foi emitido"


def test_o_laudo_emitido_valida(tmp_path, monkeypatch, validador):
    """Ponta a ponta: o arquivo que a suíte REALMENTE escreve satisfaz o contrato."""
    from webqa import report

    monkeypatch.setattr(report, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(report, "_RESULTS", [
        {"test": "checks/x.py::t", "dimension": "gui", "dimensions": ["gui"], "browser": False,
         "outcome": "failed", "estado": "failed", "fase": "call", "duration_s": 0.1,
         "detail": "algo reprovou"}])

    class SessaoFalsa:
        class config:
            class invocation_params:
                args = ()

    report.pytest_sessionfinish(SessaoFalsa(), 1)
    laudo = json.loads((tmp_path / "laudo.json").read_text(encoding="utf-8"))
    erros = sorted(validador.iter_errors(laudo), key=str)
    assert not erros, [f"{list(e.path)}: {e.message}" for e in erros]
    assert laudo["verdict"] == "nao_conforme"


def test_pii_plantada_nao_chega_ao_envelope(tmp_path, monkeypatch):
    """Sanitize continua na borda de ESCRITA, e o envelope nasce coberto por isso.

    O detalhe de um check reprovado vai para `findings[].summary`; se a borda não
    valesse para o arquivo novo, o laudo seria um caminho de vazamento inaugurado
    justamente pela entrega que promete rastreabilidade.
    """
    from webqa import report
    from webqa.sanitize import registrar_valor_sensivel

    registrar_valor_sensivel("s3nh4-super-secreta", "SENHA")
    monkeypatch.setattr(report, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(report, "_RESULTS", [
        {"test": "checks/x.py::t", "dimension": "gui", "dimensions": ["gui"], "browser": False,
         "outcome": "failed", "estado": "failed", "fase": "call", "duration_s": 0.1,
         "detail": "falhou com a senha s3nh4-super-secreta no corpo"}])

    class SessaoFalsa:
        class config:
            class invocation_params:
                args = ()

    report.pytest_sessionfinish(SessaoFalsa(), 1)
    bruto = (tmp_path / "laudo.json").read_text(encoding="utf-8")
    assert "s3nh4-super-secreta" not in bruto, "a senha plantada chegou ao envelope"
