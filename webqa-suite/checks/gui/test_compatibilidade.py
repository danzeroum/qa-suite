"""O mesmo layout em chromium, firefox e webkit — ou três layouts diferentes?

A matriz de engines já existia (`webqa/navegador.py`,
`.github/workflows/compatibilidade.yml`, 05:23 UTC) e provava **uma** coisa: que
a dimensão `browser` roda nas três. Rodar nas três não é ser compatível nas três.
Uma página pode montar em todas e ficar quebrada em uma — e é sempre a que quem
desenvolveu não usa.

**A comparação acontece DENTRO do corpo do teste**, com as engines abertas lado a
lado (`motores_gui`). Não é preferência de estilo: o nodeid tem de ser único para
o contrato do alvo fixture funcionar, e `browser` — que é parametrizado por
engine — daria um teste por engine, cada um sem material para comparar nada.

**Só marcos DECLARADOS** (`data/gui-perfis.yaml`). Antialiasing, arredondamento
de sub-pixel e métricas de fonte diferem por engine; comparar todas as caixas
produziria dezenas de divergências de 1px que não são defeito, e o sinal
verdadeiro — o cabeçalho que só no WebKit cobre o conteúdo — morreria no ruído.

**Menos de duas engines é skip, nunca "passou".** Comparar uma engine consigo
mesma é sempre verde, e esse verde seria indistinguível do verde legítimo.

**Duas decisões vieram da matriz real, não do projeto.** Rodando chromium ×
firefox contra o alvo fabricado, a primeira versão acusou dois falsos positivos,
e os dois viraram regra:

* **só geometria HORIZONTAL.** `y` e `altura` acumulam as métricas de fonte da
  página inteira — o `body` mediu 1776px no Chromium e 1797px no Firefox, 21px de
  diferença sem nada estar quebrado. Um limiar que absorvesse isso não pegaria
  defeito nenhum;
* **exceção de JS reprova; erro de console abranda.** O Chromium registra
  `net::ERR_NAME_NOT_RESOLVED` para o domínio `.invalid` do alvo e o Firefox não
  registra nada: o recurso falhou nas duas, só uma resolveu contar. Comparar
  strings de console mede verbosidade tanto quanto mede quebra. `pageerror` não
  tem esse problema — é o script da página lançando, e isso é comportamento.

Estes dois checks ficam **fora do contrato 1:1**: o desfecho contra o alvo
fabricado depende de QUAIS engines estão instaladas na máquina, e isso é
ambiente. Mesmo critério da OS-46 — o contrato reprova por regressão, nunca por
ambiente.
"""
import pytest

from webqa import metricas
from webqa.compatibilidade import (
    JS_MARCOS,
    ausentes_de,
    caixas_de,
    carregar_marcos,
    divergencias,
    erros_exclusivos,
    motivo_de_pular,
    pode_comparar,
)
from webqa.sanitize import sanitize_text
from webqa.viewports import opcoes_de_contexto

pytestmark = [pytest.mark.gui, pytest.mark.browser]

# Erros de console tardios (recurso que falha depois do load) chegariam fora da
# janela e apareceriam como exclusivos da engine mais lenta — que é ruído, não
# incompatibilidade.
_JANELA_MS = 2_000


@pytest.fixture(scope="module")
def coleta_por_engine(motores_gui, settings, perfis_gui):
    """Carrega o alvo UMA vez em cada engine disponível e guarda o que viu.

    Uma coleta para os dois checks: abrir três engines e navegar em cada uma é a
    parte cara, e pagá-la duas vezes ainda traria o risco de as duas execuções
    discordarem num alvo dinâmico. Mesma doutrina de `caminhada_de_foco` (OS-43).

    Viewport FIXO (`desktop`) de propósito: o que se compara aqui é engine contra
    engine, e variar a largura junto misturaria as duas perguntas. A largura é
    assunto de `checks/gui/test_responsividade.py`.
    """
    marcos = carregar_marcos()
    caixas, erros, avulsos = {}, {}, {}
    for engine, navegador in motores_gui["abertos"].items():
        contexto = navegador.new_context(
            **opcoes_de_contexto(perfis_gui["desktop"], engine=engine,
                                 user_agent=settings.user_agent))
        try:
            pagina = contexto.new_page()
            # Dois baldes, e a separação é o que impede este check de medir
            # verbosidade: `pageerror` é o script da PÁGINA lançando exceção
            # (comportamento), console é o navegador relatando o que quis
            # (relato). Ver `webqa/compatibilidade.py::erros_exclusivos`.
            excecoes: list[str] = []
            console: list[str] = []
            pagina.on("console",
                      lambda m, c=console: c.append(sanitize_text(m.text)[:200])
                      if m.type == "error" else None)
            pagina.on("pageerror",
                      lambda e, c=excecoes: c.append(sanitize_text(str(e))[:200]))
            pagina.goto(settings.target_url, wait_until="load", timeout=60_000)
            pagina.wait_for_timeout(_JANELA_MS)
            caixas[engine] = caixas_de(pagina.evaluate(JS_MARCOS, list(marcos)))
            erros[engine] = tuple(excecoes)
            avulsos[engine] = tuple(console)
        finally:
            contexto.close()
    return {"marcos": marcos, "caixas": caixas, "erros": erros, "console": avulsos,
            "ausentes": motores_gui["ausentes"]}


def _contabilidade(coleta) -> str:
    """A linha que faz a soma fechar no artefato do noturno.

    Sem ela, uma engine que não abriu simplesmente não aparece — e o laudo de
    compatibilidade fica indistinguível entre "as três concordaram" e "só uma
    rodou". A conta é declarada em toda mensagem, passe ou falhe.
    """
    presentes = sorted(coleta["caixas"])
    ausentes = coleta["ausentes"]
    linha = f"Engines medidas: {presentes or 'nenhuma'} ({len(presentes)})."
    if ausentes:
        linha += (f" NÃO medidas ({len(ausentes)}): "
                  + "; ".join(f"{engine} — {motivo}" for engine, motivo in sorted(ausentes.items()))
                  + ". Instale com `python -m playwright install <engine>`.")
    return linha


def _exigir_duas(coleta) -> None:
    metricas.registrar("gui_compat_engines_n", len(coleta["caixas"]))
    metricas.registrar("gui_compat_engines_ausentes_n", len(coleta["ausentes"]))
    if not pode_comparar(coleta["caixas"]):
        pytest.skip(motivo_de_pular(coleta["caixas"]) + " " + _contabilidade(coleta))


def test_geometria_dos_marcos_nao_diverge_entre_engines(coleta_por_engine, settings):
    """GUI-COMPAT-01: as caixas dos marcos declarados batem entre as engines.

    Duas famílias de achado, e a segunda é a grave: desvio de posição (o marco
    existe em todas e está em lugar diferente) e AUSÊNCIA (o marco não existe em
    alguma). A ausência não produz desvio de pixel nenhum — sem contá-la à parte,
    a comparação diria "tudo dentro da tolerância" sobre uma página que perdeu a
    navegação inteira numa engine.
    """
    _exigir_duas(coleta_por_engine)
    tolerancia = settings.threshold("gui_compat_tolerancia_px")

    faltas = ausentes_de(coleta_por_engine["caixas"])
    desvios = divergencias(coleta_por_engine["caixas"], tolerancia_px=tolerancia)
    metricas.registrar("gui_compat_divergencias_n", len(desvios) + len(faltas))

    assert not faltas, (
        f"{len(faltas)} marco(s) declarado(s) não existem em alguma engine — quem usa "
        f"aquela engine não vê o elemento:\n"
        + "\n".join(f"  {marco} — ausente em {list(engines)}" for marco, engines in faltas.items())
        + f"\n{_contabilidade(coleta_por_engine)}")
    assert not desvios, (
        f"{len(desvios)} divergência(s) de geometria acima de {tolerancia:.0f}px entre "
        f"engines:\n" + "\n".join(f"  {d}" for d in desvios[:10])
        + f"\n{_contabilidade(coleta_por_engine)}"
        + "\nSó os marcos declarados em data/gui-perfis.yaml entram: comparar todo "
          "elemento produziria dezenas de diferenças de 1px de antialiasing e o sinal "
          "verdadeiro morreria no ruído.")


def test_sem_erro_de_console_exclusivo_de_uma_engine(coleta_por_engine):
    """GUI-COMPAT-02: nenhum erro aparece em uma engine só.

    **Exclusivo**, não "quantos". Erro que aparece nas três é defeito do alvo e já
    tem dono: `checks/frontend/test_rendering.py::test_console_sem_erros_js`.
    Cobrá-lo de novo aqui faria o mesmo defeito aparecer duas vezes no laudo, e a
    correção de um apagaria o outro.

    Dois pesos, medidos nesta OS: **exceção de JavaScript exclusiva reprova**
    (comportamento — o script da página quebra numa engine e não na outra);
    **erro de console exclusivo abranda** (relato — engines discordam sobre o que
    vale registrar, e o Chromium loga falha de rede que o Firefox cala).
    """
    _exigir_duas(coleta_por_engine)
    excecoes = erros_exclusivos(coleta_por_engine["erros"])
    console = erros_exclusivos(coleta_por_engine["console"])
    metricas.registrar("gui_compat_erros_exclusivos_n",
                       sum(len(v) for v in excecoes.values()))
    metricas.registrar("gui_compat_console_exclusivo_n",
                       sum(len(v) for v in console.values()))

    assert not excecoes, (
        "Exceção de JavaScript que só UMA engine lança — o script da página quebra "
        "naquela engine e em nenhuma outra, e quem a usa é o único a sofrer:\n"
        + _listar(excecoes) + f"\n{_contabilidade(coleta_por_engine)}")

    if console:
        # Sinal, não prova. Medido nesta OS: o Chromium registra
        # `net::ERR_NAME_NOT_RESOLVED` para o domínio `.invalid` do alvo
        # fabricado e o Firefox não registra nada — o recurso falhou nas duas,
        # só uma resolveu contar. Reprovar por isso mediria verbosidade.
        pytest.xfail(
            "Erro de console exclusivo de uma engine — pode ser recurso que só ela "
            "não carrega, ou só ela relatando o que as outras calam:\n"
            + _listar(console) + f"\n{_contabilidade(coleta_por_engine)}")


def _listar(por_engine, teto: int = 5) -> str:
    return "\n".join(f"  {engine}: " + " | ".join(itens[:teto])
                     for engine, itens in sorted(por_engine.items()))
