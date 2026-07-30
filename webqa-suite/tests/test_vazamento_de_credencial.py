"""VERIFICAÇÃO (nível sistema): a senha NUNCA chega ao arquivo escrito.

Este é o aceite da OS-37, e ele é deliberadamente um **grep na saída**, não uma
inspeção de código. A garantia que interessa não é "chamamos a função de
mascarar" — é "o byte não está lá". Toda a diferença entre as duas aparece no dia
em que alguém acrescenta um campo ao `summary` e esquece de sanitizá-lo.

Por isso o teste exercita a BORDA DE ESCRITA de verdade (`pytest_sessionfinish`),
com a senha plantada em todo campo que um laudo carrega, e relê o arquivo do
disco.

`test_a_varredura_tem_dentes` é o par obrigatório: sem ele, uma varredura que
virasse no-op deixaria os outros testes verdes. Um detector que nunca detectou
nada não está provado — mesma lição de `test_convencoes.py`.
"""
import json

import pytest

from webqa import auth, report, sanitize

pytestmark = pytest.mark.verification

USUARIO = "operador-de-teste"
SENHA = 'S3nh4"com&especiais<>'


class _ParametrosDeInvocacao:
    args = ("-m", "lgpd")


class _ConfigFalsa:
    invocation_params = _ParametrosDeInvocacao()


class _SessaoFalsa:
    config = _ConfigFalsa()


@pytest.fixture
def laudo(tmp_path, monkeypatch):
    """`report/` desviado para tmp — nenhum teste escreve no relatório real.

    Os dois desvios são necessários: `REPORT_DIR` é resolvido em tempo de IMPORT
    (`report.py`), então um `setenv` tardio sozinho não o alcança.
    """
    monkeypatch.setenv("WEBQA_REPORT_DIR", str(tmp_path))
    monkeypatch.setattr(report, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(report, "_RESULTS", [])
    sanitize.esquecer_valores_sensiveis()
    yield tmp_path
    sanitize.esquecer_valores_sensiveis()


def _plantar_senha_em_todo_campo(monkeypatch):
    """A senha em cada caminho por onde ela poderia chegar ao disco."""
    cred = auth.Credencial(usuario=USUARIO, senha=SENHA)
    monkeypatch.setattr(report, "_alvo_observado",
                        lambda: f"https://{USUARIO}:{SENHA}@alvo.example")
    monkeypatch.setattr(report, "_RESULTS", [
        {
            "test": "checks/backend/test_http_basics.py::test_home",
            "dimension": "backend", "dimensions": ["backend"], "browser": False,
            "outcome": "failed", "estado": "failed", "fase": "call", "duration_s": 0.4,
            "detail": f"401 ao usar a senha {SENHA} — header Authorization: {cred.cabecalho_basic}",
        },
    ])
    return cred


def test_summary_json_escrito_nao_contem_a_senha(laudo, monkeypatch):
    cred = _plantar_senha_em_todo_campo(monkeypatch)

    report.pytest_sessionfinish(_SessaoFalsa(), 1)

    bruto = (laudo / "summary.json").read_text(encoding="utf-8")
    assert SENHA not in bruto
    for variante in auth.variantes_da_senha(USUARIO, SENHA):
        assert variante not in bruto, f"variante vazou no summary.json: {variante!r}"
    assert cred.cabecalho_basic.split()[1] not in bruto, "o blob base64 do header vazou"
    # A varredura não pode ter invalidado o documento.
    json.loads(bruto)


def test_summary_html_escrito_nao_contem_a_senha(laudo, monkeypatch):
    """O HTML escapa `"` e `&` — é por isso que as variantes escapadas existem."""
    _plantar_senha_em_todo_campo(monkeypatch)

    report.pytest_sessionfinish(_SessaoFalsa(), 1)

    bruto = (laudo / "summary.html").read_text(encoding="utf-8")
    assert SENHA not in bruto
    for variante in auth.variantes_da_senha(USUARIO, SENHA):
        assert variante not in bruto, f"variante vazou no summary.html: {variante!r}"


def test_a_varredura_tem_dentes(laudo, monkeypatch):
    """Sem o registro, a MESMA senha atravessa — prova que o teste acima mede algo.

    Irmão de `test_a_guarda_pega_o_caso_que_a_motivou`: uma varredura que virasse
    no-op deixaria os dois testes anteriores verdes e a garantia oca.
    """
    monkeypatch.setattr(report, "_RESULTS", [
        {
            "test": "checks/x.py::t", "dimension": "backend", "dimensions": ["backend"],
            "browser": False, "outcome": "failed", "estado": "failed", "fase": "call",
            "duration_s": 0.1, "detail": f"a senha crua {SENHA} sem registro",
        },
    ])
    sanitize.esquecer_valores_sensiveis()   # ninguém construiu Credencial

    report.pytest_sessionfinish(_SessaoFalsa(), 1)

    # A forma ESCAPADA para JSON, não a crua: `json.dumps` transforma `"` em
    # `\"`. É precisamente por isto que `variantes_da_senha` registra as formas
    # escapadas — procurar só o valor cru no arquivo serializado seria teatro,
    # e falharia justamente com as senhas boas, que têm caractere especial.
    assert json.dumps(SENHA)[1:-1] in (laudo / "summary.json").read_text(encoding="utf-8")


def test_toda_escrita_do_relatorio_passa_pela_varredura():
    """Guarda estrutural: um `summary_v2.json` futuro não pode nascer sem varredura.

    Lê o FONTE de `webqa/report.py` e exige `mascarar_valores_registrados` no
    argumento de todo `write_text`. É a diferença entre a garantia valer hoje e
    valer no próximo campo que alguém acrescentar.
    """
    import ast
    import inspect

    arvore = ast.parse(inspect.getsource(report))
    escritas = [
        no for no in ast.walk(arvore)
        if isinstance(no, ast.Call)
        and isinstance(no.func, ast.Attribute)
        and no.func.attr == "write_text"
    ]
    assert escritas, "nenhuma escrita encontrada — o detector perdeu o alvo"
    for no in escritas:
        argumento = ast.dump(no.args[0]) if no.args else ""
        assert "mascarar_valores_registrados" in argumento, (
            f"escrita sem varredura por valor na linha {no.lineno} de webqa/report.py"
        )


def test_sumario_recebe_detail_ja_varrido(laudo, monkeypatch):
    """`scripts/sumario.py` não precisa re-sanitizar — e este teste é o porquê.

    Ele lê o `summary.json`, que já sai varrido daqui. Re-sanitizar lá duplicaria
    o ponto único de verdade e divergiria dele com o tempo (contrato fixado em
    tests/test_sumario.py).
    """
    _plantar_senha_em_todo_campo(monkeypatch)
    report.pytest_sessionfinish(_SessaoFalsa(), 1)

    from scripts.sumario import carregar_resultados

    for achado in carregar_resultados(laudo):
        assert SENHA not in achado.get("detail", "")
