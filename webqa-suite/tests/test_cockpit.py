"""VERIFICAÇÃO do cockpit HTML (D1k) — os invariantes de honestidade das telas.

Catálogos sintéticos alimentam os montadores puros; nada de rede nem repo. O
princípio central (1ª heurística de Nielsen): o vazio — de execução E de medição
— tem aparência própria, nunca ausência que se leia como aprovação.
"""
from __future__ import annotations

import json

import pytest

from scripts.cockpit import (
    TOKENS,
    _num,
    estado_do_ambiente,
    montar_dimensoes,
    montar_laudo,
    montar_leitura,
    montar_mapa,
    montar_motor,
    montar_populacoes,
    montar_regua,
    render_html,
)

pytestmark = pytest.mark.verification

_CROMATICAS = (TOKENS["passed"], TOKENS["failed"], TOKENS["xfail"])


def _teste(nodeid, populacao="suite", estado="nao-executado", **kw):
    base = {"nodeid": nodeid, "arquivo": nodeid.split("::")[0],
            "funcao": nodeid.split("::")[-1], "linha": 1, "populacao": populacao,
            "nivel": "unidade", "dimensoes": [], "atributos": [], "casos": 1,
            "xfail": False, "xfail_strict": False, "skipif": False,
            "veredito_condicional": 0, "origem": "ast", "garante": "",
            "estado": estado, "duracao_s": 0.0}
    base.update(kw)
    return base


def _catalogo(testes, **agregados_extra):
    ag = {"populacoes": {}, "niveis": {}, "estados": {}, "por_dimensao": {},
          "por_arquivo": {}, "duracao_suite": {}, "duracao_alvo": {}, "casos": len(testes),
          "condicionais": 0, "gherkin": 0, "sem_contrato": 0}
    ag.update(agregados_extra)
    executados = sum(1 for t in testes if t["estado"] != "nao-executado")
    return {"procedencia": {"repositorio": "", "commit": "abc1234", "assunto": "", "ramo": "main"},
            "agregados": ag,
            "reconciliacao": {"executados": executados,
                              "nunca_vistos": len(testes) - executados, "orfaos": []},
            "testes": testes}


def test_populacoes_nunca_somadas():
    cat = _catalogo([_teste("checks/a.py::t1", "alvo", "passed"),
                     _teste("tests/b.py::t2", "suite")],
                    populacoes={"alvo": 1, "suite": 1})
    html = montar_populacoes(cat, {})
    assert "1" in html and "deliberadamente ausente" in html
    # nenhuma linha "Total" que some as duas populações:
    assert "Total</td>" not in html and ">2<" not in html


def test_mapa_tem_celula_vazada_para_nao_executado():
    cat = _catalogo([_teste("checks/a.py::t1", "alvo", "passed"),
                     _teste("tests/b.py::t2", "suite", "nao-executado")])
    html = montar_mapa(cat, {})
    assert "cel vazia" in html                      # não-executado presente, tracejado
    assert 'aria-label="tests/b.py::t2 — não executado"' in html


def test_xfail_nao_entra_em_conta_de_falha():
    """xfail sintético não é contado como reprovação em lugar nenhum."""
    cat = _catalogo([_teste("tests/a.py::t", "suite", "xfail")],
                    estados={"xfail": 1})
    html = render_html(cat, {})
    # Nenhuma célula pintada de FALHA (o xfail vira sua própria cor, não carmim):
    assert f"background:{TOKENS['failed']}" not in html
    assert f"background:{TOKENS['xfail']}" in html   # o xfail existe, com sua cor


def test_sem_run_laudo_nao_ha_veredito_e_sem_cor():
    cat = _catalogo([_teste("checks/a.py::t1", "alvo"),
                     _teste("tests/b.py::t2", "suite")])
    laudo = montar_laudo(cat, {})
    assert "veredito a relatar" in laudo             # "Não há veredito a relatar"
    html = render_html(cat, {})
    # Nenhuma CÉLULA pintada com cor de estado (o hex vive na folha de estilo, mas
    # nenhum `background:<cor>` de estado sai num run vazio).
    for cor in _CROMATICAS:
        assert f"background:{cor}" not in html, f"célula pintada {cor} sem execução"


def test_motor_sem_medicao_e_nomeado_nunca_zero():
    cat = _catalogo([_teste("tests/a.py::t", "suite")])
    html = montar_motor(cat, {})           # run sem 'medicoes'
    assert html.count("não instrumentada") == 3      # 3 blocos D5k, todos nomeados
    assert "0%" not in html                           # ausência nunca vira 0%


def test_motor_cobertura_por_banda_e_vies():
    cat = _catalogo([_teste("tests/a.py::t", "suite")])
    run = {"medicoes": {"cobertura_codigo": {
        "total": 62.0, "vies": "gate roda só verification",
        "por_arquivo": {"webqa/metricas.py": 7.0, "webqa/gates.py": 100.0}}}}
    html = montar_motor(cat, run)
    assert "62%" in html and "ruim" in html            # total <70 sinalizado
    assert "Viés" in html and "verification" in html
    assert "webqa/metricas.py" in html and "7%" in html


def test_motor_mutacao_por_modulo_e_sobreviventes():
    cat = _catalogo([_teste("tests/a.py::t", "suite")])
    run = {"medicoes": {"mutacao": {"por_modulo": {
        "webqa/escopo.py": {"score": 97.1, "sobreviventes": 1},
        "webqa/report.py": {"score": 59.8, "sobreviventes": 33}}}}}
    html = montar_motor(cat, run)
    assert "webqa/escopo.py" in html and "97,1%" in html
    assert "59,8%" in html and "ruim" in html          # <70 em vermelho
    assert "33" in html                                 # sobreviventes explícitos


def test_motor_complexidade_cauda_e_limiar():
    cat = _catalogo([_teste("tests/a.py::t", "suite")])
    run = {"medicoes": {"complexidade": {"teto": 8, "cauda": [
        {"func": "metadados_exif", "arquivo": "webqa/dominio.py", "cc": 9}]}}}
    html = montar_motor(cat, run)
    assert "metadados_exif" in html and ">9<" in html
    assert "Teto 8" in html and "não vigiaria o motor" in html


def test_regua_pendente_e_incomparavel_sem_carimbo():
    cat = _catalogo([_teste("tests/a.py::t", "suite")])
    html = montar_regua(cat, {})                      # sem padrao_versao/hash
    assert "pendente" in html
    assert "Incomparável" in html                     # comparavel=null nomeado


def test_regua_incomparabilidade_nomeia_cada_eixo_faltante():
    """D4k: nunca célula vazia — cada eixo ausente é NOMEADO."""
    cat = _catalogo([_teste("tests/a.py::t", "suite")])
    html = montar_regua(cat, {})                      # nada carimbado, leitura única
    assert "versão do padrão" in html
    assert "hash da lista curada" in html
    assert "2º projeto" in html


def test_selo_de_modo_mostra_a_escada_e_marca_inventario():
    """D2k: os 4 modos aparecem em escada; a leitura corrente (inventário) marcada."""
    cat = _catalogo([_teste("tests/a.py::t", "suite")])
    html = montar_regua(cat, dict(estado_do_ambiente({})))   # ambiente limpo
    for rotulo in ("Inventário", "Passivo", "Carga", "Sondagem ativa"):
        assert rotulo in html
    assert "esta leitura" in html
    assert "Nenhum gate de rede" in html              # ambiente limpo = sereno


def test_selo_arma_alarme_com_gate_de_rede_ativo():
    """Cor cromática só significa: o alarme vermelho veste SÓ com gate de rede."""
    cat = _catalogo([_teste("tests/a.py::t", "suite")])
    limpo = montar_regua(cat, dict(estado_do_ambiente({})))
    assert f"border-left:4px solid {TOKENS['failed']}" not in limpo   # sereno, sem alarme
    armado = montar_regua(cat, dict(estado_do_ambiente(
        {"WEBQA_DISCOVERY_AUTHORIZED": "1"})))
    assert "Gate de rede ATIVO" in armado
    assert "WEBQA_DISCOVERY_AUTHORIZED" in armado


def test_leitura_grau2_declara_sem_contrato():
    testes = [_teste("tests/a.py::t_com", "suite", garante="Garante X."),
              _teste("tests/a.py::t_sem", "suite")]
    cat = _catalogo(testes, sem_contrato=1)
    html = montar_leitura(cat, {})
    assert "sem contrato não aparecem neste grau" in html
    assert "Garante X." in html                       # grau 2 mostra os com contrato


def test_dimensoes_derivam_dos_markers_presentes():
    cat = _catalogo([_teste("checks/a.py::t", "alvo", dimensoes=["frontend"])],
                    por_dimensao={"frontend": {"total": 1, "nao-executado": 1}})
    html = montar_dimensoes(cat, {})
    assert "frontend" in html
    assert "seguranca" not in html                    # dimensão sem teste não aparece


def test_num_usa_virgula_decimal():
    assert _num(1.5, 1) == "1,5"
    assert _num(9.9, 3) == "9,900"
    assert _num(1000) == "1.000"                      # milhar com ponto, pt-BR


def test_espinha_de_procedencia_presente_e_do_json():
    """D3k: a régua (repo@commit · ramo · modo) fica fixa no topo, vinda do JSON —
    trocar o commit troca a espinha (nenhum literal digitado)."""
    cat = _catalogo([_teste("tests/a.py::t", "suite")])
    cat["procedencia"] = {"repositorio": "danzeroum/qa-suite", "commit": "deadbee",
                          "ramo": "main", "assunto": ""}
    html = render_html(cat, dict(estado_do_ambiente({})))
    assert 'class="espinha"' in html
    assert "danzeroum/qa-suite@deadbee" in html
    assert "ramo main" in html and "modo inventario" in html
    # espinha é do JSON: outro commit → outra espinha
    cat["procedencia"]["commit"] = "f00ba12"
    assert "f00ba12" in render_html(cat, {})


def test_laudo_abre_com_a_regua_antes_de_qualquer_numero():
    """D3k: a procedência é a primeira frase do laudo — a régua antes do número."""
    cat = _catalogo([_teste("tests/a.py::t", "suite")])
    cat["procedencia"] = {"repositorio": "", "commit": "abc1234", "ramo": "dev", "assunto": ""}
    laudo = montar_laudo(cat, dict(estado_do_ambiente({})))
    pos_regua = laudo.find("Régua desta leitura")
    pos_numero = laudo.find("O catálogo lista")
    assert 0 <= pos_regua < pos_numero          # régua vem ANTES do número
    assert "abc1234" in laudo and "modo inventario" in laudo


def test_espinha_arma_com_gate_de_rede():
    """A espinha também denuncia gate de rede ativo (cor cromática só significa)."""
    cat = _catalogo([_teste("tests/a.py::t", "suite")])
    limpa = render_html(cat, dict(estado_do_ambiente({})))
    assert 'class="espinha alarme-espinha"' not in limpa   # a regra existe no CSS; a classe não é aplicada
    armada = render_html(cat, dict(estado_do_ambiente({"WEBQA_LOAD_AUTHORIZED": "1"})))
    assert 'class="espinha alarme-espinha"' in armada and "WEBQA_LOAD_AUTHORIZED" in armada


def test_html_e_offline_e_arquivo_unico():
    """Convenção da casa: zero requisição externa, nada de asset por URL."""
    import re
    cat = _catalogo([_teste("checks/a.py::t1", "alvo", "passed"),
                     _teste("tests/b.py::t2", "suite")])
    html = render_html(cat, {})
    assert not re.search(r'(src|href)="https?://', html), "asset externo no cockpit"
    assert "<script src=" not in html and "<link " not in html
    assert html.startswith("<!doctype html>") and html.rstrip().endswith("</html>")


def test_arquitetura_um_montador_por_tela():
    """'Módulo novo = função nova': cada tela do contrato tem seu montador puro."""
    import scripts.cockpit as ck
    for nome in ("mapa", "populacoes", "niveis", "dimensoes", "catalogo", "leitura",
                 "execucao", "regua", "motor", "entrega", "governanca", "laudo", "diff"):
        assert callable(getattr(ck, f"montar_{nome}")), f"falta montar_{nome}"


def test_pre_do_laudo_e_parse_igual_ao_catalogo():
    import html as H
    import re
    cat = _catalogo([_teste("tests/a.py::t", "suite")])
    laudo = montar_laudo(cat, {})
    bruto = re.search(r"<pre class=\"json\">(.*?)</pre>", laudo, re.S).group(1)
    assert json.loads(H.unescape(bruto)) == cat       # <pre> == o catálogo, após parse
