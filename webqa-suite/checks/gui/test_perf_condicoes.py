"""A página serve para quem não tem fibra?

GUI-PERF-02 (pintura sob rede lenta) e GUI-PERF-03 (bloqueio sob CPU lenta).
Core Web Vitals e ISO 25010 (eficiência de desempenho sob condição declarada).

`checks/frontend/test_rendering.py` mede FCP e LCP, e `test_interatividade.py`
mede TBT — os três na rede do runner: fibra de datacenter, CPU ociosa. É a
condição em que **nenhum visitante está**. Um alvo que pinta em 70ms ali pode
levar três segundos e meio num celular em 3G, e as duas medidas são verdadeiras
porque medem coisas diferentes. Este arquivo mede a segunda.

**O que a falha PROVA**, e é diferente da do irmão de fibra: existe trabalho —
bytes bloqueantes ou computação síncrona — cujo custo é invisível na máquina de
quem desenvolve e severo na de quem usa. É a classe de defeito que só um perfil
degradado encontra, porque em laboratório ela não existe.

**O veredito é condicionado ao ambiente, e isso está declarado.** Mesma doutrina
da OS-46: a régua fica, o peso do veredito muda. Só sob `WEBQA_ORIGEM=vps`
(`docs/VPS.md`) o estouro reprova; fora dele é `xfail` com o motivo escrito, e a
medida vai ao laudo dos dois jeitos. É também por isso que estes nodeids estão
em `fora_do_contrato`: o contrato do alvo fixture reprova quando um check para de
detectar, e um teste cujo desfecho depende do ambiente reprovaria por ambiente.

**O `xfail` é em RUNTIME, nunca decorator.** `xfail_strict` transformaria o
desfecho `XPASS` — que é o que um alvo conforme produz aqui — em falha, e o smoke
da OS-44 quebraria contra a página conforme. O decorator declara antes de medir;
esta família só sabe depois.
"""
import os

import pytest

from webqa import metricas
from webqa.rede_simulada import (
    ENV_PERFIL,
    SemCDP,
    avaliar_bloqueio,
    avaliar_pintura,
    estrangular,
    perfil_de_rede,
    resumo_da_condicao,
)
from webqa.vitals_interacao import (
    JANELA_PADRAO_MS,
    VITALS_INTERACAO_JS,
    medidas_de,
    resumo_de_tarefas,
    veredito_e_duro,
)

pytestmark = [pytest.mark.gui, pytest.mark.browser]


@pytest.fixture(scope="module")
def sob_degradacao(contexto_gui_modulo, settings, perfis_gui, perfis_de_rede):
    """UMA carga estrangulada, alimentando os dois vereditos deste arquivo.

    Partilhada pela mesma razão que a caminhada de foco é: a observação é CARA —
    sob 3G a carga leva segundos — e os dois checks perguntam coisas diferentes
    sobre **a mesma** carga. Repeti-la daria dois números medidos em instantes
    diferentes, e a diferença entre eles seria ruído apresentado como sinal.

    Contexto PRÓPRIO, do `contexto_gui_modulo`, e nunca `browser_page`: o
    estrangulamento vive na sessão CDP daquele par (contexto, página) e morre com
    ele. Aplicado à página de sessão, faria `checks/frontend/test_rendering.py`
    medir LCP sob 3G sem declarar isso — o R20 em versão rede, e o pior tipo de
    número errado, porque nada fica vermelho.
    """
    perfil = perfil_de_rede(os.environ.get(ENV_PERFIL), perfis_de_rede)
    # Perfil móvel, e não desktop: 3G com tela de celular é a condição que existe
    # em campo. Emparelhar rede ruim com viewport de desktop mediria uma
    # combinação que quase ninguém vive.
    pagina = contexto_gui_modulo(viewport=perfis_gui["mobile"])
    try:
        # ANTES do goto, e antes do init script: emulação ligada depois da carga
        # mede uma página que já baixou tudo em fibra, e nenhum resultado
        # denuncia a inversão — o teste simplesmente passa.
        estrangular(pagina, perfil)
    except SemCDP as exc:
        pytest.skip(str(exc))

    from checks.frontend.test_rendering import VITALS_JS

    pagina.add_init_script(VITALS_INTERACAO_JS)
    # Prazo generoso: sob 1638 kbps uma folha bloqueante de 600KB sozinha leva
    # ~3s, e o prazo de 60s dos irmãos de fibra viraria flake de ambiente.
    pagina.goto(settings.target_url, wait_until="load", timeout=120_000)
    vitals = pagina.evaluate(VITALS_JS) or {}
    # Interação NEUTRA, como na OS-46: `Tab` move o foco e não aciona nada, então
    # não é sondagem ativa e dispensa WEBQA_ACTIVE_PROBES_AUTHORIZED.
    pagina.keyboard.press("Tab")
    medidas = medidas_de(
        pagina.evaluate("(ms) => window.__webqa_interacao(ms)", JANELA_PADRAO_MS))
    return {"perfil": perfil, "vitals": vitals, "medidas": medidas}


def test_pintura_sob_rede_lenta(sob_degradacao, settings):
    """GUI-PERF-02: FCP e LCP sob 3G, contra orçamento próprio de rede lenta."""
    perfil, vitals = sob_degradacao["perfil"], sob_degradacao["vitals"]
    fcp, lcp = vitals.get("fcp"), vitals.get("lcp")

    # Registro ANTES de qualquer veredito: `pytest.xfail` levanta na hora, e uma
    # medida registrada depois dele nunca chegaria ao laudo. Medida e veredito
    # são coisas diferentes — `None` o registrador descarta, porque pintura não
    # observada não é pintura instantânea.
    metricas.registrar("gui_fcp_ms_rede_lenta", fcp)
    metricas.registrar("gui_lcp_ms_rede_lenta", lcp)

    problemas = avaliar_pintura(
        fcp, lcp,
        fcp_max=settings.threshold("gui_fcp_ms_rede_lenta"),
        lcp_max=settings.threshold("gui_lcp_ms_rede_lenta"),
    )
    medido = (f"Medido: FCP {'não medido' if fcp is None else f'{fcp:.0f}ms'}, "
              f"LCP {'não medido' if lcp is None else f'{lcp:.0f}ms'}.")
    detalhe = "\n".join([*(f"  {p}" for p in problemas), medido,
                         resumo_da_condicao(perfil)])

    if problemas and not veredito_e_duro(os.environ.get("WEBQA_ORIGEM")):
        pytest.xfail(
            "Orçamento de rede lenta estourado FORA do ambiente oficial — a máquina "
            "compartilhada influencia a medida. Declare WEBQA_ORIGEM=vps para que "
            f"isto reprove.\n{detalhe}")
    assert not problemas, (
        "Pintura sob rede lenta acima do orçamento no ambiente oficial — em fibra "
        f"este alvo é rápido, e é por isso que só esta medida o encontra:\n{detalhe}")

    if fcp is None and lcp is None:
        # Passar aqui anunciaria cobertura de pintura que não houve. Não é
        # ausência de lentidão: é ausência de medida (docs/GUI.md §2.2, regra 9).
        pytest.xfail(
            "Nem FCP nem LCP foram emitidos pelo navegador sob a condição degradada — "
            f"pintura NÃO medida. Ausência de medida não é rapidez.\n"
            f"{resumo_da_condicao(perfil)}")


def test_bloqueio_sob_cpu_lenta(sob_degradacao, settings):
    """GUI-PERF-03: TBT sob CPU ×4, contra orçamento próprio de CPU lenta."""
    perfil, medidas = sob_degradacao["perfil"], sob_degradacao["medidas"]

    if not medidas.suporta_longtask:
        pytest.skip(
            "Long Tasks API indisponível nesta engine — TBT NÃO foi medido sob CPU "
            "lenta. Engine sem a API não é aprovação.")

    metricas.registrar("gui_tbt_ms_cpu_lento", medidas.tbt_ms)
    metricas.registrar("gui_long_tasks_n_cpu_lento", medidas.long_tasks_n)

    problemas = avaliar_bloqueio(
        medidas.tbt_ms, tbt_max=settings.threshold("gui_tbt_ms_cpu_lento"))
    medido = (f"Medido: TBT {medidas.tbt_ms:.0f}ms em {medidas.long_tasks_n} tarefas "
              f"longas (janela de {JANELA_PADRAO_MS}ms após um Tab).")
    detalhe = "\n".join([*(f"  {p}" for p in problemas), medido,
                         resumo_da_condicao(perfil),
                         "Tarefas mais caras:", resumo_de_tarefas(medidas.tarefas)])

    if problemas and not veredito_e_duro(os.environ.get("WEBQA_ORIGEM")):
        pytest.xfail(
            "Orçamento de CPU lenta estourado FORA do ambiente oficial — o número é "
            "ruído provável de máquina compartilhada, não achado sobre o alvo. "
            f"Declare WEBQA_ORIGEM=vps para que isto reprove.\n{detalhe}")
    assert not problemas, (
        "Bloqueio sob CPU lenta acima do orçamento no ambiente oficial — trabalho "
        "síncrono que a máquina de quem desenvolve absorve e a de quem usa não:\n"
        f"{detalhe}")
