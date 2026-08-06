"""VERIFICAÇÃO: a aritmética da jornada, sobre grafos fabricados (OS-51).

Sem navegador e sem rede: o núcleo de `webqa/jornada.py` recebe grafo e rótulos e
decide. É o que permite fixar as bordas que um alvo real quase nunca oferece —
empate de caminhos ótimos, destino inalcançável, página sem link nenhum.

A borda que mais importa aqui é a do **empate de ótimos**: quando há dois
caminhos mínimos distintos, escolher qualquer um dos dois tem de dar excedente
ZERO. Um comparador que olhasse a SEQUÊNCIA puniria a jornada por ter escolhido
o ótimo "errado" — e não existe ótimo errado.
"""
import pytest
import yaml

from webqa.jornada import (
    Resultado,
    Tarefa,
    afinidade,
    arestas_com_rotulo,
    avaliar_cliques,
    avaliar_tempo,
    becos,
    caminho_otimo,
    carregar_tarefas,
    escolher_proximo,
    excedente,
    grafo_de,
    palavras,
    reconhece_destino,
    saidas,
    tarefa_de,
)

pytestmark = pytest.mark.verification

# a → b → d ; a → c → d   (dois caminhos mínimos de 2 cliques até `d`)
GRAFO_EMPATE = {
    "a": (("b", "por b"), ("c", "por c")),
    "b": (("d", "chegar"),),
    "c": (("d", "chegar"),),
    "d": (),
}
# a → b → c   (caminho único)
GRAFO_LINHA = {"a": (("b", "meio"),), "b": (("c", "fim"),), "c": ()}


def _tarefa(**extra) -> Tarefa:
    base = dict(nome="t", procura=("fim",), marco="Fim", cliques_extras_max=0, tot_ms=1000)
    return Tarefa(**{**base, **extra})


# ---------- BFS ----------

def test_caminho_unico_e_encontrado_inteiro():
    assert caminho_otimo(GRAFO_LINHA, "a", frozenset({"c"})) == ("a", "b", "c")


def test_origem_que_ja_e_o_destino_custa_zero_clique():
    assert caminho_otimo(GRAFO_LINHA, "a", frozenset({"a"})) == ("a",)


def test_empate_de_otimos_devolve_um_deles_com_o_mesmo_comprimento():
    caminho = caminho_otimo(GRAFO_EMPATE, "a", frozenset({"d"}))
    assert caminho is not None and len(caminho) == 3
    assert caminho in (("a", "b", "d"), ("a", "c", "d"))


def test_destino_inalcancavel_devolve_none_e_nao_levanta():
    """Alvo inalcançável é o ACHADO (TSR=0), não um erro do medidor. Levantar
    exceção viraria `error` — o teste não tendo acontecido — quando na verdade
    ele aconteceu e a resposta é 'não dá para chegar'."""
    assert caminho_otimo(GRAFO_LINHA, "a", frozenset({"z"})) is None


def test_bfs_escolhe_o_curto_mesmo_com_um_longo_disponivel():
    grafo = {"a": (("b", ""), ("z", "")), "b": (("z", ""),), "z": ()}
    assert caminho_otimo(grafo, "a", frozenset({"z"})) == ("a", "z")


# ---------- excedente ----------

@pytest.mark.parametrize("percorrido", [("a", "b", "d"), ("a", "c", "d")])
def test_qualquer_um_dos_otimos_empatados_da_excedente_zero(percorrido):
    """A borda que dá nome ao arquivo."""
    otimo = caminho_otimo(GRAFO_EMPATE, "a", frozenset({"d"}))
    assert excedente(percorrido, otimo) == 0


def test_volta_desnecessaria_conta_como_excedente():
    otimo = caminho_otimo(GRAFO_EMPATE, "a", frozenset({"d"}))
    assert excedente(("a", "b", "a", "c", "d"), otimo) == 2


def test_sem_otimo_nao_ha_excedente():
    assert excedente(("a", "b"), None) is None


def test_excedente_nunca_e_negativo():
    """Percurso mais curto que o ótimo é impossível pelo grafo; se aparecer, é
    defeito de medição — e medição defeituosa não pode virar crédito."""
    assert excedente(("a",), ("a", "b", "c")) == 0


# ---------- becos ----------

def test_pagina_sem_link_nenhum_e_beco():
    """A borda está do lado do ACHADO: "não achei link" e "não há link" são a
    mesma coisa para quem está lá."""
    assert becos(GRAFO_LINHA, "a") == ("c",)


def test_pagina_que_so_aponta_para_si_e_beco():
    grafo = {"a": (("b", ""),), "b": (("b", ""),)}
    assert becos(grafo, "a") == ("b",)


def test_hub_com_dois_destinos_nao_e_beco():
    assert becos(GRAFO_EMPATE, "a") == ("d",), "só `d` é folha; `b` e `c` levam adiante"


def test_a_entrada_nunca_conta_como_beco():
    """Beco é propriedade de página em que se ENTRA clicando. Contar a entrada
    reprovaria todo documento único servido como alvo — por exemplo a política de
    privacidade apontada direto, que é o alvo do smoke da OS-44."""
    assert becos({"a": ()}, "a") == ()


def test_saidas_ignora_auto_link():
    assert saidas({"x": (("x", ""), ("y", ""))}, "x") == ("y",)


# ---------- rótulo ----------

def test_afinidade_ignora_acento_e_caixa():
    assert afinidade("Política de PRIVACIDADE", ("politica", "privacidade")) == 1.0


def test_afinidade_de_rotulo_longo_que_contem_a_procura_e_alta():
    """Rótulo longo não pode ser punido por ser longo: a fração é sobre as
    palavras da PROCURA, não sobre as do rótulo."""
    assert afinidade("Leia nossa politica de privacidade e os termos",
                     ("politica", "privacidade")) == 1.0


def test_palavras_curtas_nao_discriminam():
    assert "de" not in palavras("de a e politica")


def test_escolhe_o_rotulo_mais_parecido():
    links = (("/x", "Sobre nós"), ("/y", "Politica de privacidade"))
    assert escolher_proximo(links, ("politica", "privacidade"), frozenset()) == "/y"


def test_empate_de_rotulo_resolve_pela_ordem_da_pagina():
    """A ordem em que a pessoa lê — e o que torna a caminhada reproduzível."""
    links = (("/primeiro", "Contato"), ("/segundo", "Contato"))
    assert escolher_proximo(links, ("contato",), frozenset()) == "/primeiro"


def test_sem_rotulo_afim_a_pessoa_desiste():
    """Desistir é resultado (TSR=0), não erro."""
    assert escolher_proximo((("/x", "Sobre"),), ("contato",), frozenset()) is None


def test_link_ja_visitado_nao_e_reescolhido():
    links = (("/y", "Contato"), ("/z", "Contato e suporte"))
    assert escolher_proximo(links, ("contato",), frozenset({"/y"})) == "/z"


# ---------- reconhecer a chegada ----------

def test_mencao_num_link_nao_e_chegada():
    """A regressão que a medição pegou: a home CITA o destino num rótulo, e a
    primeira versão a dava como destino — TSR=1 com zero cliques."""
    home = '<html><head><title>Loja</title></head><body><h1>Loja</h1>' \
           '<a href="/p">Politica de Privacidade</a></body></html>'
    assert reconhece_destino("Politica de Privacidade", home) is False


def test_cabecalho_da_pagina_de_destino_e_chegada():
    destino = '<html><head><title>Politica</title></head><body>' \
              '<h1>Politica de Privacidade</h1></body></html>'
    assert reconhece_destino("Politica de Privacidade", destino) is True


def test_reconhecer_ignora_acento():
    assert reconhece_destino("Politica", "<h1>Política</h1>") is True


# ---------- arestas com rótulo ----------

def test_aresta_carrega_o_rotulo_do_link():
    html = '<a href="/destino">Fale conosco</a>'
    arestas = arestas_com_rotulo(html, "http://alvo/", "alvo")
    assert arestas == (("http://alvo/destino", "Fale conosco"),)


def test_grafo_de_delega_as_arestas_e_nao_as_inventa():
    class _P:
        url, html = "u", ""
    assert grafo_de([_P()], lambda p: (("v", "r"),)) == {"u": (("v", "r"),)}


# ---------- avaliadores e configuração ----------

def test_cliques_dentro_do_teto_nao_reprovam():
    r = Resultado(tarefa=_tarefa(cliques_extras_max=1), percorrido=("a", "b", "c"),
                  otimo=("a", "c"))
    assert avaliar_cliques(r) == []


def test_cliques_acima_do_teto_dizem_quantos_e_contra_o_que():
    r = Resultado(tarefa=_tarefa(cliques_extras_max=0), percorrido=("a", "b", "c"),
                  otimo=("a", "c"))
    problemas = avaliar_cliques(r)
    assert len(problemas) == 1 and "menor caminho" in problemas[0]


def test_tempo_no_limite_exato_passa():
    assert avaliar_tempo(Resultado(tarefa=_tarefa(tot_ms=1000), tot_ms=1000)) == []
    assert avaliar_tempo(Resultado(tarefa=_tarefa(tot_ms=1000), tot_ms=1000.1)) != []


def test_tsr_e_binario():
    assert Resultado(tarefa=_tarefa()).tsr == 1
    assert Resultado(tarefa=_tarefa(), motivo_da_parada="desistiu").tsr == 0


def test_tarefa_desconhecida_e_erro_listando_as_validas():
    tarefas = {"a": _tarefa(nome="a"), "b": _tarefa(nome="b")}
    with pytest.raises(ValueError) as erro:
        tarefa_de("c", tarefas)
    for valida in tarefas:
        assert valida in str(erro.value)


def test_tarefa_sem_campo_obrigatorio_e_erro_nomeando_o_campo(tmp_path):
    caminho = tmp_path / "p.yaml"
    caminho.write_text(yaml.safe_dump(
        {"jornadas": [{"nome": "t", "procura": ["x"], "marco": "m"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="cliques_extras_max"):
        carregar_tarefas(caminho)


def test_bloco_de_jornadas_vazio_e_erro(tmp_path):
    caminho = tmp_path / "p.yaml"
    caminho.write_text("viewports: {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="nenhuma jornada"):
        carregar_tarefas(caminho)


def test_as_tarefas_do_repositorio_carregam():
    tarefas = carregar_tarefas()
    assert "encontrar a política de privacidade" in tarefas
