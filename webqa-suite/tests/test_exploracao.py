"""VERIFICAÇÃO: o código julga a LLM, e não o contrário (OS-55).

Sobre saída de LLM **fabricada** — o CI não exige modelo local. É o que torna a
regra desta peça verificável: "a LLM apresenta, o código julga" só é regra se o
julgamento roda sem a LLM.

As quatro classes de rejeição têm mensagens distintas de propósito. Dizer "tipo
inválido" quando a página também é fantasma mandaria quem lê consertar a coisa
errada.
"""
import ast

import pytest

from webqa.exploracao import (
    TIPOS_DE_FRICCAO,
    Friccao,
    Rejeitada,
    carregar_personas,
    julgar,
    montar_prompt,
    paginas_do,
    snapshot_de,
    triar,
)

pytestmark = pytest.mark.verification

GRAFO = {"http://a/": (("http://a/p", "Privacidade"), ("http://a/p", "Politica")),
         "http://a/p": ()}
TEXTOS = {"http://a/": "Loja", "http://a/p": "Politica de Privacidade"}
SNAPSHOT = snapshot_de(GRAFO, TEXTOS)


def _bruta(**extra):
    base = {"pagina": "http://a/", "tipo": "rotulo_ambiguo",
            "descricao": "dois rótulos levam ao mesmo destino",
            "evidencia": "Privacidade"}
    return {**base, **extra}


# ---------- as quatro classes ----------

def test_friccao_bem_formada_passa():
    resultado = julgar(_bruta(), SNAPSHOT, persona="literal")
    assert isinstance(resultado, Friccao)
    assert resultado.persona == "literal" and resultado.tipo == "rotulo_ambiguo"


def test_pagina_fantasma_e_alucinacao():
    """A porta que dá nome à peça: fricção sobre página que o crawl não visitou
    é invenção, não observação."""
    r = julgar(_bruta(pagina="http://a/inventada"), SNAPSHOT)
    assert isinstance(r, Rejeitada) and r.classe == "alucinacao"
    assert "não visitou" in r.motivo and "inventada" in r.motivo


def test_tipo_fora_do_vocabulario_reprova():
    r = julgar(_bruta(tipo="confuso"), SNAPSHOT)
    assert isinstance(r, Rejeitada) and r.classe == "tipo_invalido"
    assert "vocabulário fechado" in r.motivo


def test_descricao_que_certifica_reprova():
    """DIVERGE de `webqa/llm.py` de propósito: lá o texto que certifica é MARCADO
    (é prosa para gente ler); aqui é REJEITADO, porque fricção é dado que alguém
    vai triar, e uma que certifica não é triável."""
    r = julgar(_bruta(descricao="o site está conforme garantido em WCAG"), SNAPSHOT)
    assert isinstance(r, Rejeitada) and r.classe == "certificacao"


def test_evidencia_ausente_do_insumo_e_alucinacao():
    """Sem trecho que a sustente, a fricção é afirmação sobre nada."""
    r = julgar(_bruta(evidencia="Fale conosco"), SNAPSHOT)
    assert isinstance(r, Rejeitada) and r.classe == "alucinacao"
    assert "não aparece no insumo" in r.motivo


def test_as_quatro_mensagens_sao_distintas():
    motivos = {julgar(b, SNAPSHOT).motivo for b in (
        _bruta(pagina="http://x/"), _bruta(tipo="z"),
        _bruta(descricao="está certificado"), _bruta(evidencia="nada disso"))}
    assert len(motivos) == 4


@pytest.mark.parametrize("campo", ["pagina", "tipo", "descricao", "evidencia"])
def test_campo_faltando_reprova_nomeando_o_campo(campo):
    r = julgar(_bruta(**{campo: ""}), SNAPSHOT)
    assert isinstance(r, Rejeitada) and campo in r.motivo


def test_saida_que_nem_e_objeto_reprova():
    assert julgar("uma frase solta", SNAPSHOT).classe == "malformada"


def test_triagem_separa_e_nao_descarta_em_silencio():
    """A taxa de alucinação é ela própria um dado sobre o modelo."""
    aceitas, rejeitadas = triar([_bruta(), _bruta(pagina="http://z/")], SNAPSHOT)
    assert len(aceitas) == 1 and len(rejeitadas) == 1


def test_lista_vazia_e_resposta_valida():
    assert triar([], SNAPSHOT) == ([], [])


# ---------- o insumo ----------

def test_snapshot_e_deterministico():
    """Mesma entrada, mesmo prompt. Sem isso a diferença entre duas saídas seria
    atribuída ao modelo quando veio da ordem de um dicionário."""
    assert snapshot_de(GRAFO, TEXTOS) == snapshot_de(dict(reversed(list(GRAFO.items()))),
                                                    TEXTOS)


def test_snapshot_traz_as_paginas_e_os_rotulos():
    assert paginas_do(SNAPSHOT) == {"http://a/", "http://a/p"}
    assert SNAPSHOT["paginas"][0]["links"][0]["rotulo"] in ("Politica", "Privacidade")


def test_snapshot_so_leva_desfechos_que_falharam():
    laudo = {"results": [
        {"dimension": "gui", "test": "t::a", "outcome": "failed", "detail": "x"},
        {"dimension": "gui", "test": "t::b", "outcome": "passed", "detail": "y"},
        {"dimension": "lgpd", "test": "t::c", "outcome": "failed", "detail": "z"}]}
    testes = [d["teste"] for d in snapshot_de(GRAFO, TEXTOS, laudo)["desfechos"]]
    assert testes == ["t::a"]


# ---------- o prompt ----------

def test_o_prompt_lista_o_vocabulario_fechado():
    prompt = montar_prompt(SNAPSHOT, "literal", "procura a palavra exata")
    for tipo in TIPOS_DE_FRICCAO:
        assert tipo in prompt
    assert "Zero fricções é uma resposta válida" in prompt


def test_o_prompt_proibe_navegar_e_certificar():
    prompt = montar_prompt(SNAPSHOT, "p", "t")
    assert "NÃO pode navegar" in prompt and "certificado" in prompt


# ---------- personas ----------

def test_personas_do_repositorio_carregam():
    personas = carregar_personas()
    assert "literal" in personas and personas["literal"].strip()


def test_personas_vazias_reprovam(tmp_path):
    caminho = tmp_path / "p.yaml"
    caminho.write_text("personas: {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="nenhuma persona"):
        carregar_personas(caminho)


# ---------- a convenção que sustenta a doutrina ----------

def test_exploracao_nao_importa_navegacao_nem_rede():
    """A doutrina da casa como ARQUITETURA: a IA processa achados já produzidos e
    não participa de agir contra o alvo. Este módulo não tem como navegar porque
    não tem como alcançar a rede — e isto é o que prova."""
    from pathlib import Path as _P
    fonte = (_P(__file__).resolve().parent.parent / "webqa" / "exploracao.py")
    arvore = ast.parse(fonte.read_text(encoding="utf-8"))
    modulos = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            modulos.update(a.name.split(".")[0] for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            modulos.add(no.module.split(".")[0])
    proibidos = {"playwright", "httpx", "requests", "urllib", "socket", "http"}
    assert not (modulos & proibidos), (
        f"exploracao.py importa {modulos & proibidos} — o insumo é snapshot "
        f"serializado, e poder alcançar a rede é poder agir contra o alvo")
    assert "navegacao" not in modulos


# ---------- a borda de PII, e o script ----------

def _script():
    import sys
    from pathlib import Path as _P
    sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
    import scripts.explora_jornada as modulo
    return modulo


def test_pii_no_insumo_nao_chega_ao_prompt():
    """O alvo fabricado serve `/newsletter?email=joao@exemplo.com`: **PII mora em
    URL também**, e em query string é onde ela mais mora. A primeira versão
    preservava a URL crua com o argumento de que ela é a chave da validação — e o
    argumento era falso, porque o snapshot que vai ao prompt é o MESMO que vai ao
    validador. Sanitizar os dois lados juntos não quebra chave nenhuma."""
    import json as _json
    bruto = {"paginas": [{"url": "http://a/n?email=joao@exemplo.com",
                          "titulo": "contato de maria@exemplo.com",
                          "links": [{"para": "http://a/x?e=jose@exemplo.com",
                                     "rotulo": "escreva para ana@exemplo.com"}]}],
             "desfechos": [{"teste": "t", "desfecho": "failed",
                            "detalhe": "falhou para pedro@exemplo.com"}]}
    limpo = _json.dumps(_script().sanitizar_snapshot(bruto), ensure_ascii=False)
    for endereco in ("joao@", "maria@", "jose@", "ana@", "pedro@"):
        assert endereco not in limpo, f"{endereco} atravessou a borda até o prompt"


def test_a_validacao_continua_funcionando_sobre_o_insumo_sanitizado():
    """O medo que motivou o erro acima: sanitizar a URL faria toda fricção virar
    alucinação. Não faz — porque os dois lados são o mesmo snapshot."""
    limpo = _script().sanitizar_snapshot(
        {"paginas": [{"url": "http://a/n?email=joao@exemplo.com", "titulo": "t",
                      "links": []}], "desfechos": []})
    pagina = limpo["paginas"][0]["url"]
    resultado = julgar({"pagina": pagina, "tipo": "beco", "descricao": "sem saída",
                        "evidencia": "t"}, limpo)
    assert isinstance(resultado, Friccao)


def test_sem_gate_o_script_para_nomeando_a_variavel(monkeypatch, tmp_path, capsys):
    """Fail-closed que não degrada: sem o opt-in não há execução, e a mensagem
    diz qual variável exportar."""
    monkeypatch.delenv("WEBQA_LLM_ENABLED", raising=False)
    vazio = tmp_path / "s.json"
    vazio.write_text('{"paginas": [], "desfechos": []}', encoding="utf-8")
    assert _script().main([str(vazio)]) == 2
    assert "WEBQA_LLM_ENABLED" in capsys.readouterr().err


def test_o_script_nao_tem_caida_para_api_externa():
    """`webqa/llm.py` recusa endpoint público por invariante; um script que
    contornasse isso desfaria a invariante do lado de fora."""
    from pathlib import Path as _P
    fonte = (_P(__file__).resolve().parent.parent / "scripts" / "explora_jornada.py")
    texto = fonte.read_text(encoding="utf-8")
    assert "NÃO há caída para API externa" in texto
    assert "openai.com" not in texto and "anthropic.com" not in texto
