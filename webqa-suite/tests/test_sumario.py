"""VERIFICAÇÃO do anexo assistido (docs/LLM.md, OS-24 v2).

**Nenhum teste toca rede nem runtime local.** O `Protocol ResumidorLLM` existe
para isto: um fake que devolve string satisfaz o contrato inteiro, e o montador
é exercido de ponta a ponta sem modelo nenhum.

O que se protege aqui não é o texto do sumário — esse é probabilístico e não se
testa. É o contorno determinístico dele: quem pode ser gravado, quando nada
deve ser gravado, e o que a suíte marca quando o modelo se comporta mal.
"""
from __future__ import annotations

import json

import pytest

from scripts import sumario
from webqa import gates
from webqa.llm import (
    PREFIXO_OMISSAO,
    PREFIXO_REVISAR,
    TETO_ACHADOS,
    achados_para_prompt,
)

pytestmark = pytest.mark.verification


class ResumidorFake:
    """Devolve texto fixo e GUARDA o que recebeu — é assim que se inspeciona o
    payload sem subir runtime."""

    def __init__(self, texto: str = "Dois achados graves na dimensão seguranca."):
        self.texto = texto
        self.recebido: list[dict] = []

    def resumir(self, resultados: list[dict]) -> str:
        self.recebido = achados_para_prompt(resultados)
        return self.texto


SUMMARY = [
    {"test": "checks/a.py::t_ok", "dimension": "backend", "estado": "passed", "detail": ""},
    {"test": "checks/b.py::t_seg", "dimension": "seguranca", "estado": "failed",
     "severidade": "alta", "fase_seguranca": "A", "detail": "credencial exposta"},
    {"test": "checks/c.py::t_lgpd", "dimension": "lgpd", "estado": "failed",
     "detail": "tracker antes do aceite"},
    {"test": "checks/d.py::t_infra", "dimension": "ux", "estado": "error",
     "detail": "Chromium indisponível"},
]


def _escrever_summary(tmp_path, resultados) -> None:
    (tmp_path / "summary.json").write_text(
        json.dumps({"results": resultados}, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def relatorio(tmp_path, monkeypatch):
    """`WEBQA_REPORT_DIR` apontado para tmp — nenhum teste escreve em report/ real."""
    monkeypatch.setenv("WEBQA_REPORT_DIR", str(tmp_path))
    monkeypatch.setattr(sumario, "report_dir", lambda: tmp_path)
    return tmp_path


# ---------- Gate: desligado não gera, não falha, não toca o laudo ----------

def test_gate_off_nao_gera_nada_e_sai_zero(relatorio, monkeypatch):
    monkeypatch.delenv(gates.LLM_ENV, raising=False)
    _escrever_summary(relatorio, SUMMARY)
    antes = (relatorio / "summary.json").read_bytes()

    assert sumario.main([]) == 0
    assert not (relatorio / sumario.NOME_DO_ARQUIVO).exists()
    assert (relatorio / "summary.json").read_bytes() == antes, "o laudo foi tocado"


def test_gate_off_nem_resolve_endpoint(relatorio, monkeypatch):
    """Gate fechado tem de sair ANTES de qualquer efeito — nada instanciado."""
    monkeypatch.delenv(gates.LLM_ENV, raising=False)

    def explode(*a, **k):                      # pragma: no cover - não deve rodar
        raise AssertionError("gate fechado não pode tocar o runtime")
    monkeypatch.setattr(sumario, "ResumidorLocal", explode)
    monkeypatch.setattr(sumario, "runtime_disponivel", explode)

    assert sumario.main([]) == 0


# ---------- Runtime ausente: exit 0 barato, não a espera do POST ----------

def test_runtime_ausente_sai_zero_sem_chamar_o_modelo(relatorio, monkeypatch, capsys):
    monkeypatch.setenv(gates.LLM_ENV, "1")
    _escrever_summary(relatorio, SUMMARY)
    monkeypatch.setattr(sumario, "runtime_disponivel", lambda *a, **k: False)

    def explode(*a, **k):                      # pragma: no cover - não deve rodar
        raise AssertionError("não se monta prompt sem runtime de pé")
    monkeypatch.setattr(sumario, "gerar", explode)

    assert sumario.main([]) == 0
    assert not (relatorio / sumario.NOME_DO_ARQUIVO).exists()
    assert "runtime local não respondeu" in capsys.readouterr().out


def test_health_check_e_curto_o_bastante_para_nao_travar():
    """A etapa é opcional; opcional que trava dois minutos deixa de ser opcional."""
    from webqa.llm import TIMEOUT_HEALTH_S

    assert TIMEOUT_HEALTH_S <= 2.0


def test_endpoint_recusado_sai_zero_com_motivo(relatorio, monkeypatch, capsys):
    """Veto de endpoint é erro de configuração do operador — dizer qual vale mais
    que sair calado, mas ainda assim não derruba nada."""
    monkeypatch.setenv(gates.LLM_ENV, "1")
    _escrever_summary(relatorio, SUMMARY)

    def recusa(*a, **k):
        raise ValueError("envio para nuvem fora de escopo: teste")
    monkeypatch.setattr(sumario, "ResumidorLocal", recusa)

    assert sumario.main([]) == 0
    assert "endpoint recusado" in capsys.readouterr().out
    assert not (relatorio / sumario.NOME_DO_ARQUIVO).exists()


# ---------- Borda: laudo 100% verde ----------

def test_sem_achados_nao_gera_sumario(relatorio, monkeypatch, capsys):
    """Laudo verde é RESULTADO, não erro — e um sumário de "nenhum achado"
    convidaria o modelo a afirmar conformidade por ausência."""
    monkeypatch.setenv(gates.LLM_ENV, "1")
    _escrever_summary(relatorio, [
        {"test": "checks/a.py::t_ok", "dimension": "backend", "estado": "passed"},
        {"test": "checks/b.py::t_pulado", "dimension": "ux", "estado": "skipped"},
    ])
    assert sumario.main([]) == 0
    assert not (relatorio / sumario.NOME_DO_ARQUIVO).exists()
    assert "nada a resumir" in capsys.readouterr().out


def test_summary_ausente_nao_e_erro(relatorio, monkeypatch):
    monkeypatch.setenv(gates.LLM_ENV, "1")
    assert sumario.main([]) == 0
    assert not (relatorio / sumario.NOME_DO_ARQUIVO).exists()


# ---------- Payload: o que chega (e o que não chega) ao modelo ----------

def test_passed_ausente_e_detail_nao_re_sanitizado():
    """O `detail` já nasce sanitizado no report.py. Segunda sanitização aqui
    duplicaria o ponto único de verdade e divergiria dele com o tempo."""
    fake = ResumidorFake()
    sumario.gerar(SUMMARY, fake)

    testes = {a["test"] for a in fake.recebido}
    assert "checks/a.py::t_ok" not in testes, "passed chegou ao modelo"
    assert len(fake.recebido) == 3
    entregue = next(a for a in fake.recebido if a["test"].endswith("t_seg"))
    assert entregue["detail"] == "credencial exposta", "o detail foi reescrito no caminho"


def test_ordem_failed_error_xfail_antes_do_teto():
    """Com mais de 80 achados, o corte tem de sacrificar o menos urgente.

    `error` vem antes de `xfail` de propósito: teste que NÃO ACONTECEU esconde
    infraestrutura quebrada, e é esse o defeito que este projeto mais pagou caro.
    """
    muitos = (
        [{"test": f"c/x.py::x{i}", "dimension": "ux", "estado": "xfail"} for i in range(60)]
        + [{"test": f"c/x.py::e{i}", "dimension": "ux", "estado": "error"} for i in range(50)]
        + [{"test": f"c/x.py::f{i}", "dimension": "seguranca", "estado": "failed"}
           for i in range(30)]
    )
    achados = achados_para_prompt(muitos)

    # 30 failed + 50 error preenchem o teto exatamente; os 60 xfail ficam fora.
    assert len(achados) == TETO_ACHADOS
    estados = [a["estado"] for a in achados]
    assert estados[:30] == ["failed"] * 30
    assert estados[30:] == ["error"] * 50
    assert "xfail" not in estados, "xfail ocupou espaço que era de failed/error"


def test_ordem_e_estavel_dentro_do_mesmo_estado():
    achados = achados_para_prompt(
        [{"test": f"c/x.py::t{i}", "dimension": "ux", "estado": "failed"} for i in range(5)])
    assert [a["test"] for a in achados] == [f"c/x.py::t{i}" for i in range(5)]


# ---------- Guardas sobre a saída do modelo ----------

def test_linguagem_de_certificacao_e_marcada_e_preservada():
    fake = ResumidorFake("O site está conforme e aprovado, seguranca e lgpd revisadas.")
    saida = sumario.gerar(SUMMARY, fake)
    assert saida.startswith(PREFIXO_REVISAR)
    assert "conforme" in saida and "aprovado" in saida
    assert fake.texto in saida, "marcar não é descartar"


def test_dimensao_com_failed_ausente_do_texto_e_marcada():
    """O risco de um modelo não é só afirmar demais — é calar.

    Sumário que fala de três dimensões e ignora a quarta parece completo, e a
    ausência não deixa marca sozinha. Aqui deixa.
    """
    fake = ResumidorFake("Achados relevantes na dimensão seguranca; comece por ali.")
    saida = sumario.gerar(SUMMARY, fake)
    assert saida.startswith(PREFIXO_OMISSAO.format(dimensoes="lgpd"))
    assert fake.texto in saida


def test_guardas_nao_empilham_marcacao():
    """Regressão de um defeito que só a validação ponta a ponta pegou.

    A guarda de linguagem morava em DOIS lugares (`ResumidorLocal.resumir` e
    `gerar`). O prefixo dela contém "aprovado" e "conforme" — as próprias
    palavras que ela procura — então a segunda passada casava consigo mesma e
    marcava de novo. O teste com fake não via: o fake não aplicava guarda
    nenhuma. Hoje a guarda mora só em `gerar`, e é idempotente por cima disso.
    """
    fake = ResumidorFake("O site está conforme e aprovado; seguranca e lgpd revisadas.")
    uma_vez = sumario.gerar(SUMMARY, fake)
    assert uma_vez.count(PREFIXO_REVISAR) == 1

    class JaGuardado:
        def resumir(self, _resultados: list[dict]) -> str:
            return uma_vez

    assert sumario.gerar(SUMMARY, JaGuardado()).count(PREFIXO_REVISAR) == 1


def test_resumidor_local_devolve_texto_cru():
    """A guarda é do orquestrador. Se `resumir` guardasse, uma implementação
    alternativa do `Protocol` ficaria sem proteção — a garantia viraria
    'cada impl que lembre', que é o oposto de invariante."""
    from pathlib import Path

    fonte = (Path(__file__).resolve().parent.parent / "webqa" / "llm.py").read_text("utf-8")
    corpo = fonte.split("    def resumir(self, resultados: list[dict]) -> str:")[-1]
    assert "aplicar_guarda_de_linguagem(" not in corpo
    assert "aplicar_guarda_de_omissao(" not in corpo


def test_texto_que_cobre_tudo_passa_intacto():
    fake = ResumidorFake("Há achados em seguranca e em lgpd; ambos precisam de ação.")
    assert sumario.gerar(SUMMARY, fake) == fake.texto


def test_xfail_sozinho_nao_dispara_guarda_de_omissao():
    """Só `failed` obriga menção: `xfail` é sinal de maturidade e pode
    legitimamente ficar fora de um sumário executivo."""
    resultados = [{"test": "c/a.py::t", "dimension": "lgpd", "estado": "xfail"}]
    fake = ResumidorFake("Um alerta menor, sem veredito de não conformidade.")
    assert sumario.gerar(resultados, fake) == fake.texto


def test_modelo_mudo_nao_vira_arquivo(relatorio, monkeypatch):
    monkeypatch.setenv(gates.LLM_ENV, "1")
    _escrever_summary(relatorio, SUMMARY)
    monkeypatch.setattr(sumario, "runtime_disponivel", lambda *a, **k: True)
    monkeypatch.setattr(sumario, "gerar", lambda *a, **k: "")
    monkeypatch.setattr(sumario, "ResumidorLocal",
                        lambda **k: ResumidorFake(""))

    assert sumario.main([]) == 0
    assert not (relatorio / sumario.NOME_DO_ARQUIVO).exists()


def test_falha_do_modelo_nao_derruba_a_etapa(relatorio, monkeypatch, capsys):
    """`try/except` amplo é seguro AQUI porque estamos fora do hook do laudo:
    não há nada a engolir além desta etapa opcional."""
    monkeypatch.setenv(gates.LLM_ENV, "1")
    _escrever_summary(relatorio, SUMMARY)
    monkeypatch.setattr(sumario, "runtime_disponivel", lambda *a, **k: True)
    monkeypatch.setattr(sumario, "ResumidorLocal", lambda **k: ResumidorFake())

    def explode(*a, **k):
        raise RuntimeError("modelo travou")
    monkeypatch.setattr(sumario, "gerar", explode)

    assert sumario.main([]) == 0
    assert "modelo falhou" in capsys.readouterr().out


# ---------- Documento final ----------

def test_caminho_feliz_grava_rotulado_sem_tocar_o_laudo(relatorio, monkeypatch):
    monkeypatch.setenv(gates.LLM_ENV, "1")
    _escrever_summary(relatorio, SUMMARY)
    antes = (relatorio / "summary.json").read_bytes()
    monkeypatch.setattr(sumario, "runtime_disponivel", lambda *a, **k: True)
    monkeypatch.setattr(
        sumario, "ResumidorLocal",
        lambda **k: ResumidorFake("Achados em seguranca e lgpd exigem ação imediata."))

    assert sumario.main([]) == 0
    conteudo = (relatorio / sumario.NOME_DO_ARQUIVO).read_text(encoding="utf-8")
    assert "NÃO é veredito" in conteudo
    assert "A fonte da verdade é `summary.json`" in conteudo
    assert "Achados em seguranca e lgpd" in conteudo
    assert (relatorio / "summary.json").read_bytes() == antes
    assert not (relatorio / "summary.html").exists()


def test_cabecalho_fica_no_arquivo_e_fora_do_prompt():
    """Rótulo e timestamp são para o humano. No prompt seriam contexto gasto sem
    informação de achado — e o modelo não precisa saber a hora."""
    fake = ResumidorFake("Achados em seguranca e lgpd.")
    sumario.gerar(SUMMARY, fake)
    serializado = json.dumps(fake.recebido, ensure_ascii=False)
    for termo in ("NÃO é veredito", "gerado em", "endpoint", "modelo:"):
        assert termo not in serializado


def test_sumario_md_esta_coberto_pelo_gitignore():
    """Artefato de execução contra alvo real — R8. `report/` já cobre, e este
    teste existe para que uma mudança no gitignore não descubra o arquivo."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent.parent
    linhas = (raiz / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert any(linha.strip() in ("report/", "webqa-suite/report/") for linha in linhas)
