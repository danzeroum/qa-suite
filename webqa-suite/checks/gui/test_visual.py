"""Regressão visual contra a linha de base — e as três cercas que a tornam usável.

Pixel-diff é a técnica mais fácil de ligar e a mais fácil de tornar inútil. Três
decisões separam este check de um gerador de vermelho:

1. **o assunto é FABRICADO e sem texto.** Métrica de fonte varia entre sistema
   operacional, versão de engine e fontes instaladas; um diff sobre texto
   renderizado é loteria entre o local e o CI — verde numa máquina, vermelho na
   outra, sem nada ter mudado no alvo. As páginas do contrato visual são formas
   sólidas alinhadas ao pixel;
2. **o veredito é por BLOCO, e o laudo diz ONDE.** "3,2% dos pixels mudaram" não
   permite corrigir nada. A mensagem nomeia as coordenadas dos blocos;
3. **referência ausente é SKIP com instrução, nunca PASS.** No primeiro run não
   há o que comparar, e passar aí anunciaria estabilidade que ninguém mediu.

**A borda de evidência (R19).** Pixel não passa por `webqa/sanitize.py`, e tela
de aplicação real exibe dado de quem estava logado. Por isso a mitigação
registrada é NÃO COLETAR: sem `WEBQA_GUI_SCREENSHOTS=1`, nenhum PNG de alvo
não-fabricado chega ao disco — e `webqa/evidencias.py` é quem decide, não a boa
vontade de quem escreve o próximo check.

**Decoder fail-closed.** PNG entrelaçado, paletizado, de profundidade diferente
de 8 bits ou truncado levanta `PngNaoSuportado`, e o check vira **`error`** — o
teste não aconteceu. Nunca `passed`: veredito visual sobre decodificação errada
é o pior defeito possível desta peça, porque nada nele tem cara de defeito.
"""
from urllib.parse import urlsplit

import pytest

from webqa import metricas
from webqa.auth import origem_de
from webqa.evidencias import alvo_fabricado
from webqa.imagem import (
    PngNaoSuportado,
    blocos_divergentes,
    decodificar,
    divergencia_de_tamanho,
    resumo_de_blocos,
)
from webqa.referencia_visual import (
    carregar,
    carregar_paginas,
    existe,
    motivo_de_pular,
    problemas_do_manifesto,
)

pytestmark = [pytest.mark.gui, pytest.mark.browser]


def _capturar(contexto_gui, settings, perfis_gui, pagina_visual, seletor=""):
    """Abre a variação e devolve os bytes do PNG — sem tocar o disco.

    A captura fica em MEMÓRIA por decisão, não por conveniência: o caminho que
    grava é o de `make referencia-visual`, e ele é explícito. Um check que
    gravasse "só para depurar" seria o vazamento do R19 entrando pela porta dos
    fundos.
    """
    pagina = contexto_gui(viewport=perfis_gui[pagina_visual.viewport])
    # ORIGEM, e não `target_url`: as páginas do contrato visual são caminhos
    # absolutos do alvo fabricado, e concatená-las a uma URL que já tem caminho
    # (`.../privacidade`) produziria `/privacidade/gui/visual` — um 404 que o
    # diff leria como "a página inteira mudou". É a mesma correção da OS-47.
    url = origem_de(settings.target_url).rstrip("/") + pagina_visual.caminho
    pagina.goto(url, wait_until="load", timeout=60_000)
    if seletor:
        return pagina.locator(seletor).screenshot()
    return pagina.screenshot()


def _comparar(atual: bytes, referencia: bytes, *, tolerancia: int):
    """Decodifica os dois lados e devolve (motivo_de_tamanho, blocos)."""
    imagem_atual = decodificar(atual)
    imagem_referencia = decodificar(referencia)
    tamanho = divergencia_de_tamanho(imagem_referencia, imagem_atual)
    if tamanho:
        return tamanho, ()
    return "", blocos_divergentes(imagem_referencia, imagem_atual, tolerancia=tolerancia)


def _sem_paginas() -> None:
    pytest.skip("Nenhuma página no contrato visual (`data/gui-perfis.yaml::visual`). "
                "Regressão visual só é versionável contra alvo FABRICADO — captura de "
                "alvo real não passa pela borda de sanitização (R19).")


def _exigir_alvo_fabricado(settings) -> None:
    """Duas condições, e a segunda foi o smoke da OS-44 que exigiu.

    **Fabricado**, porque a referência versionada retrata páginas que só o
    fixture serve: compará-la com a captura de outro alvo produziria "tudo
    divergente" sobre duas páginas que nunca foram a mesma. (Não é a mesma
    pergunta de `pode_gravar_png`, que decide se um PNG chega ao disco.)

    **E a RAIZ do alvo.** Este check é do CONTRATO do alvo fabricado, não da
    página apontada — ele mede `/gui/visual*` seja qual for a `target_url`. Com
    `WEBQA_TARGET_URL` apontando para uma página específica, quem está medindo
    quer AQUELA página, e um veredito sobre outra é ruído. Foi exatamente isso
    que aconteceu: o smoke da OS-44 aponta para `/privacidade`, e este check
    reprovava lá — acusando de falso positivo contra a página conforme uma
    divergência que é do contrato visual e que ele plantou de propósito.
    """
    if not alvo_fabricado(settings.target_url):
        pytest.skip(
            f"Contrato visual é do alvo FABRICADO; {settings.target_url} não é ele. "
            "Referência versionada retrata páginas que só o fixture serve, e captura "
            "de alvo real não é versionável (R19: pixel não passa pela borda de "
            "sanitização). Linha de base de alvo real vive fora da árvore, em "
            "WEBQA_GUI_BASELINE_DIR.")
    caminho = urlsplit(settings.target_url).path.strip("/")
    if caminho:
        pytest.skip(
            f"WEBQA_TARGET_URL aponta para /{caminho}, e o contrato visual mede as "
            "páginas do alvo fabricado (`/gui/visual*`), não a página apontada. "
            "Rode contra a raiz do alvo para exercê-lo.")


def test_paginas_estaveis_contra_a_linha_de_base(contexto_gui, settings, perfis_gui):
    """GUI-VIS-01: cada variação declarada bate com a referência versionada."""
    paginas = carregar_paginas()
    if not paginas:
        _sem_paginas()
    _exigir_alvo_fabricado(settings)

    tolerancia = int(settings.threshold("gui_visual_tolerancia_canal"))
    divergentes, ausentes, problemas = [], [], []
    for visual in paginas:
        artefato = visual.artefato()
        if not existe(artefato):
            ausentes.append(motivo_de_pular(artefato))
            continue
        problemas += [f"{artefato.identidade}: {p}" for p in problemas_do_manifesto(artefato)]
        atual = _capturar(contexto_gui, settings, perfis_gui, visual)
        try:
            tamanho, blocos = _comparar(atual, carregar(artefato), tolerancia=tolerancia)
        except PngNaoSuportado as erro:
            # `error`, não `failed`: o teste NÃO ACONTECEU. Transformar isto em
            # reprovação diria que o alvo mudou, quando o que houve foi a suíte
            # não conseguir ler a imagem.
            raise RuntimeError(
                f"Decoder recusou o PNG de {artefato.identidade}: {erro}") from erro
        metricas.registrar(f"gui_visual_blocos_{visual.viewport}_n", len(blocos))
        if tamanho:
            divergentes.append(f"  [{artefato.identidade}] {tamanho}")
        elif blocos:
            divergentes.append(f"  [{artefato.identidade}] {len(blocos)} bloco(s):\n"
                               + resumo_de_blocos(blocos))

    assert not problemas, (
        "A procedência da linha de base não está declarada:\n  " + "\n  ".join(problemas))
    assert not divergentes, (
        f"{len(divergentes)} variação(ões) divergem da linha de base versionada — a "
        f"tolerância por canal é {tolerancia}, e o diff é por bloco de 16x16px para "
        "dizer ONDE mudou:\n" + "\n".join(divergentes)
        + "\nSe a mudança for intencional, regrave com `make referencia-visual` "
          "(o manifesto de procedência é reescrito junto).")
    if ausentes:
        pytest.skip(" | ".join(ausentes))


def test_componentes_estaveis_contra_a_linha_de_base(contexto_gui, settings, perfis_gui):
    """GUI-VIS-02: os componentes declarados, um a um.

    Recorte por componente e não pela página inteira porque a pergunta é outra:
    a página inteira responde "algo mudou"; o componente responde "o botão
    mudou". Quando os dois reprovam juntos, a segunda mensagem é a que vai para
    o ticket.
    """
    paginas = [p for p in carregar_paginas() if p.componentes]
    if not paginas:
        pytest.skip("Nenhum componente declarado em `visual.paginas[].componentes`.")
    _exigir_alvo_fabricado(settings)

    tolerancia = int(settings.threshold("gui_visual_tolerancia_canal"))
    divergentes, ausentes = [], []
    for visual in paginas:
        for componente in visual.componentes:
            artefato = visual.artefato(componente)
            if not existe(artefato):
                ausentes.append(motivo_de_pular(artefato))
                continue
            atual = _capturar(contexto_gui, settings, perfis_gui, visual, componente)
            try:
                tamanho, blocos = _comparar(atual, carregar(artefato), tolerancia=tolerancia)
            except PngNaoSuportado as erro:
                raise RuntimeError(
                    f"Decoder recusou o PNG de {artefato.identidade}: {erro}") from erro
            if tamanho or blocos:
                divergentes.append(f"  [{artefato.identidade}] "
                                   + (tamanho or f"{len(blocos)} bloco(s)"))

    metricas.registrar("gui_visual_componentes_divergentes_n", len(divergentes))
    assert not divergentes, (
        "Componente(s) divergem da linha de base:\n" + "\n".join(divergentes)
        + "\nRegrave com `make referencia-visual` se a mudança for intencional.")
    if ausentes:
        pytest.skip(" | ".join(ausentes))
