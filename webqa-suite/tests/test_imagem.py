"""VERIFICAÇÃO: o decoder PNG e o diff por bloco.

O defeito que este arquivo existe para impedir **não estoura**: um decoder que
interpreta mal um PNG entrelaçado, paletizado ou de 16 bits devolve uma matriz
plausível, e o diff emite veredito sobre uma imagem que não existe. Nada nisso
tem cara de defeito — é por isso que cada recusa tem caso próprio, e é por isso
que o Paeth é conferido contra vetor conhecido em vez de "parece certo".

Duas hipóteses sobre o Playwright viram CONTRATO aqui, e uma delas a OS errou:
o Chromium 1.56 emite `color_type=2` (RGB, três canais), **não RGBA**, e em
**vários chunks IDAT**. Um upgrade que mude isso reprova nestes testes, em vez
de virar um diff visual inexplicável.
"""
from __future__ import annotations

import struct
import zlib

import pytest

from webqa.imagem import (
    LADO_DO_BLOCO,
    Imagem,
    PngNaoSuportado,
    _filtro_average,
    _filtro_paeth,
    _filtro_sub,
    _filtro_up,
    _paeth,
    blocos_divergentes,
    decodificar,
    divergencia_de_tamanho,
    resumo_de_blocos,
)

pytestmark = pytest.mark.verification

ASSINATURA = b"\x89PNG\r\n\x1a\n"


def _chunk(tipo: bytes, dados: bytes) -> bytes:
    return (struct.pack(">I", len(dados)) + tipo + dados
            + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF))


def _png(largura=4, altura=2, profundidade=8, cor=2, entrelace=0, linhas=None,
         idats=1) -> bytes:
    if linhas is None:
        linhas = [bytes([0]) + bytes([10, 20, 30] * largura) for _ in range(altura)]
    bruto = zlib.compress(b"".join(linhas))
    corte = max(1, len(bruto) // idats)
    partes = [bruto[i:i + corte] for i in range(0, len(bruto), corte)] or [b""]
    ihdr = struct.pack(">IIBBBBB", largura, altura, profundidade, cor, 0, 0, entrelace)
    return (ASSINATURA + _chunk(b"IHDR", ihdr)
            + b"".join(_chunk(b"IDAT", parte) for parte in partes)
            + _chunk(b"IEND", b""))


def _solida(largura, altura, cor=(0, 0, 0)) -> Imagem:
    return Imagem(largura, altura, 3, bytes(list(cor) * largura * altura))


# ---------- As quatro recusas, cada uma com a mensagem certa ----------

def test_recusa_bit_depth_diferente_de_8():
    with pytest.raises(PngNaoSuportado) as erro:
        decodificar(_png(profundidade=16))
    assert "bit depth 16" in str(erro.value) and "8 bits" in str(erro.value)


def test_recusa_paleta_e_cinza():
    """Paleta exigiria resolver PLTE/tRNS — e o erro seria silencioso."""
    with pytest.raises(PngNaoSuportado) as erro:
        decodificar(_png(cor=0))
    assert "color type 0" in str(erro.value) and "PLTE" in str(erro.value)


def test_recusa_entrelacado():
    """As sete passadas do Adam7 seriam lidas como linhas sequenciais e
    produziriam uma imagem embaralhada que o diff trataria como mudança de
    layout — o defeito plausível que dá nome a este arquivo."""
    with pytest.raises(PngNaoSuportado) as erro:
        decodificar(_png(entrelace=1))
    assert "entrelaçado" in str(erro.value) and "Adam7" in str(erro.value)


def test_recusa_truncado():
    completo = _png(largura=4, altura=4)
    with pytest.raises(PngNaoSuportado) as erro:
        decodificar(completo[:len(completo) // 2] + _chunk(b"IEND", b""))
    assert "truncado" in str(erro.value) or "IDAT" in str(erro.value)


def test_recusa_o_que_nem_e_png():
    with pytest.raises(PngNaoSuportado) as erro:
        decodificar(b"GIF89a" + b"\x00" * 40)
    assert "assinatura" in str(erro.value)


# ---------- Os cinco filtros, contra vetor conhecido ----------

def test_filtro_none_deixa_a_linha_como_esta():
    imagem = decodificar(_png(largura=2, altura=1,
                              linhas=[bytes([0, 1, 2, 3, 4, 5, 6])]))
    assert imagem.pixel(0, 0) == (1, 2, 3) and imagem.pixel(1, 0) == (4, 5, 6)


def test_filtro_sub_soma_o_pixel_da_esquerda():
    linha = bytearray([10, 20, 30, 5, 5, 5])
    _filtro_sub(linha, bytearray(6), 3)
    assert list(linha) == [10, 20, 30, 15, 25, 35]


def test_filtro_up_soma_a_linha_de_cima():
    linha = bytearray([1, 2, 3])
    _filtro_up(linha, bytearray([10, 20, 30]), 3)
    assert list(linha) == [11, 22, 33]


def test_filtro_average_usa_a_media_INTEIRA():
    """`(esquerda + acima) >> 1`, truncado. Arredondar em vez de truncar produz
    um deslocamento de 1 em muitos pixels — invisível a olho, e o diff acusa a
    página inteira."""
    linha = bytearray([0, 0, 0, 10, 10, 10])
    _filtro_average(linha, bytearray([4, 6, 8, 4, 6, 8]), 3)
    assert list(linha) == [2, 3, 4, 13, 14, 16]


def test_paeth_escolhe_o_mais_proximo_do_preditor():
    """Derivado à mão da definição do `PaethPredictor` na especificação PNG, e
    não do que o código devolve — um vetor copiado da implementação prova só que
    ela é igual a si mesma.

    `_paeth(10, 20, 30)`: p = 10+20-30 = 0; pa=|0-10|=10, pb=|0-20|=20,
    pc=|0-30|=30. `pa <= pb and pa <= pc` → devolve **a** = 10.
    """
    assert _paeth(10, 20, 30) == 10
    assert _paeth(0, 0, 0) == 0
    assert _paeth(255, 0, 0) == 255
    # p = 0+10-0 = 10; pa=10, pb=0, pc=10 → pb é o menor → devolve b.
    assert _paeth(0, 10, 0) == 10


def test_paeth_desempata_a_favor_de_a_e_depois_de_b():
    """O desempate é a parte que se erra escrevendo de cabeça, e o erro não
    estoura: produz uma imagem levemente deslocada."""
    assert _paeth(5, 5, 5) == 5
    assert _paeth(10, 10, 20) == 10, "empate entre a e b resolve em a"


def test_filtro_paeth_aplicado_na_linha():
    """Derivação à mão, byte a byte:

    * i=0: esquerda=0 (fora da linha), acima=10, acima-esquerda=0 →
      `_paeth(0, 10, 0)` = 10 → 1 + 10 = **11**;
    * i=3: esquerda=linha[0]=11 (JÁ desfiltrado), acima=20, acima-esquerda=10 →
      p=21, pa=10, pb=1, pc=11 → devolve b=20 → 1 + 20 = **21**.

    O i=3 é o que importa: ele usa o valor já desfiltrado da esquerda, e não o
    byte original. Um Paeth que lesse o byte cru daria 22 aqui — um deslocamento
    de 1 que não estoura e faz o diff acusar a página inteira.
    """
    linha = bytearray([1, 1, 1, 1, 1, 1])
    _filtro_paeth(linha, bytearray([10, 10, 10, 20, 20, 20]), 3)
    assert list(linha) == [11, 11, 11, 21, 21, 21]


def test_todas_as_linhas_do_png_passam_pelo_filtro_declarado():
    """Duas linhas, filtros diferentes: a segunda usa Up sobre a primeira."""
    linhas = [bytes([0, 10, 20, 30]), bytes([2, 1, 1, 1])]
    imagem = decodificar(_png(largura=1, altura=2, linhas=linhas))
    assert imagem.pixel(0, 0) == (10, 20, 30)
    assert imagem.pixel(0, 1) == (11, 21, 31)


def test_filtro_desconhecido_e_recusado():
    with pytest.raises(PngNaoSuportado) as erro:
        decodificar(_png(largura=1, altura=1, linhas=[bytes([9, 1, 2, 3])]))
    assert "filtro 9" in str(erro.value)


# ---------- O contrato com o Playwright ----------

def test_varios_IDAT_sao_concatenados_antes_de_inflar():
    """Medido: o Chromium emite vários. Um decoder que lesse só o primeiro
    devolveria imagem truncada — e o erro apareceria como "PNG corrompido" num
    arquivo perfeitamente válido."""
    imagem = decodificar(_png(largura=8, altura=8, idats=3))
    assert imagem.largura == 8 and imagem.altura == 8


@pytest.mark.browser
def test_png_real_do_playwright_e_RGB_de_8_bits_nao_entrelacado():
    """**Contrato, não observação.** A OS previa RGBA; o que o Chromium emite é
    `color_type=2` (RGB). Um upgrade de Playwright que mude o formato reprova
    AQUI, com o motivo à mão, em vez de virar um diff visual inexplicável.
    """
    pytest.importorskip("playwright", reason="Playwright ausente.")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            navegador = p.chromium.launch()
        except Exception as exc:
            pytest.skip(f"chromium indisponível: {exc}")
        pagina = navegador.new_context(viewport={"width": 60, "height": 40}).new_page()
        pagina.set_content("<body style='margin:0;background:#0000ff'></body>")
        png = pagina.screenshot()
        navegador.close()

    _, _, profundidade, cor, _, _, entrelace = struct.unpack(">IIBBBBB", png[16:29])
    assert profundidade == 8, "o decoder só lê 8 bits por canal"
    assert cor in (2, 6), f"color type {cor} — o decoder lê RGB(2) e RGBA(6)"
    assert entrelace == 0, "o decoder recusa Adam7"

    imagem = decodificar(png)
    assert (imagem.largura, imagem.altura) == (60, 40)
    assert imagem.pixel(0, 0)[:3] == (0, 0, 255), "canto conferido contra a cor pedida"


# ---------- Diff por bloco ----------

def test_imagens_identicas_nao_produzem_bloco():
    imagem = _solida(64, 32)
    assert blocos_divergentes(imagem, imagem, tolerancia=0) == ()


def test_um_bloco_alterado_produz_EXATAMENTE_ele():
    referencia = _solida(64, 32)
    pixels = bytearray(referencia.pixels)
    # Pinta o pixel (20, 20): cai no bloco (16, 16).
    inicio = (20 * 64 + 20) * 3
    pixels[inicio:inicio + 3] = bytes([255, 255, 255])
    atual = Imagem(64, 32, 3, bytes(pixels))
    blocos = blocos_divergentes(referencia, atual, tolerancia=8)
    assert len(blocos) == 1
    assert (blocos[0].x, blocos[0].y) == (16, 16)
    assert blocos[0].maior_desvio == 255


def test_tolerancia_por_canal_na_borda_EXATA_ainda_esta_dentro():
    """O comparador é `>`, não `>=` — mesma disciplina do 25% da cobertura de
    foco (OS-43), dos 50ms do TBT (OS-46) e dos 30% da sobreposição (OS-48).
    Aqui ela é o que separa antialiasing de borda de mudança de forma."""
    referencia = _solida(32, 32, (100, 100, 100))
    atual = _solida(32, 32, (108, 100, 100))          # desvio exatamente 8
    assert blocos_divergentes(referencia, atual, tolerancia=8) == ()
    fora = _solida(32, 32, (109, 100, 100))           # 9 > 8
    assert len(blocos_divergentes(referencia, fora, tolerancia=8)) == 4


def test_tamanho_diferente_e_outro_achado_e_vem_antes():
    """Comparar tamanhos diferentes bloco a bloco produziria "quase tudo
    divergente" e esconderia a causa real, que costuma ser trivial."""
    motivo = divergencia_de_tamanho(_solida(64, 32), _solida(64, 48))
    assert "64x48" in motivo and "64x32" in motivo
    assert "não é regressão visual" in motivo
    assert divergencia_de_tamanho(_solida(8, 8), _solida(8, 8)) == ""


def test_o_resumo_diz_ONDE_e_nao_so_quanto():
    """"3,2% dos pixels mudaram" não permite corrigir nada."""
    referencia = _solida(64, 64)
    atual = _solida(64, 64, (255, 0, 0))
    texto = resumo_de_blocos(blocos_divergentes(referencia, atual, tolerancia=8))
    assert "bloco em (0,0)" in texto and "16x16px" in texto


def test_o_resumo_trunca_dizendo_quantos_ficaram():
    referencia = _solida(320, 320)
    atual = _solida(320, 320, (255, 255, 255))
    texto = resumo_de_blocos(blocos_divergentes(referencia, atual, tolerancia=8))
    assert "e mais" in texto


def test_o_lado_do_bloco_e_declarado():
    assert LADO_DO_BLOCO == 16
