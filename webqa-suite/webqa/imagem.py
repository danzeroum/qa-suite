"""PNG lido com `zlib` e `struct`, e o diff por bloco — sem dependência nova.

`Pillow` foi rejeitada com fundamento registrado (`PROXIMOS-PASSOS.md §5`), e o
que a suíte precisa de um PNG é pequeno: dimensões e os bytes dos pixels. O
caro não é ler — é **não ler errado**.

**Por que o decoder é FAIL-CLOSED, e por que isso é aceite e não detalhe.**
Um decoder que interpreta mal um PNG entrelaçado (Adam7), paletizado ou de
profundidade diferente de 8 bits **não estoura**: ele devolve uma matriz
plausível. O diff então emite veredito sobre uma imagem que não existe — e o
veredito parece normal. É o pior defeito possível desta peça, porque nada nele
tem cara de defeito. Daí cada recusa levantar `PngNaoSuportado` com o motivo
nomeado, e daí haver caso de teste para cada uma: detector que nunca detectou
nada não está provado.

**Duas hipóteses sobre o Playwright, medidas e não supostas.** A OS previa RGBA;
o que o Chromium 1.56 emite é **`color_type=2` (RGB, três canais)**, e em
**vários chunks IDAT** — um decoder que lesse só o primeiro devolveria imagem
truncada, silenciosamente. As duas viraram teste (`tests/test_imagem.py`), que é
o que transforma a hipótese em contrato: um upgrade de Playwright que mude o
formato reprova ali, em vez de virar um diff visual inexplicável.

**Diff por bloco, não por pixel.** Pixel a pixel, uma diferença de 1/255 num
canto conta igual a um botão que sumiu; e a lista de ofensores fica com milhares
de linhas que ninguém lê. O bloco de 16×16 responde a pergunta útil — **onde**
a página mudou — e a tolerância por canal absorve o antialiasing sem absorver
mudança de forma.

Somente stdlib (`zlib`, `struct`).
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

ASSINATURA = b"\x89PNG\r\n\x1a\n"

# Só truecolor. Os canais são a única coisa que o diff precisa saber, e paleta
# exigiria resolver PLTE — outro formato, outra classe de erro silencioso.
CANAIS_POR_COR = {2: 3, 6: 4}
PROFUNDIDADE_ACEITA = 8
SEM_ENTRELACE = 0

# Lado do bloco do diff. 16 é grande o bastante para uma mudança de forma cair
# inteira dentro de poucos blocos e pequeno o bastante para localizá-la.
LADO_DO_BLOCO = 16


class PngNaoSuportado(ValueError):
    """O PNG existe mas não é do formato que este decoder sabe ler.

    Erro, e nunca decodificação por melhor esforço: o chamador transforma isto
    em `error` no laudo (o teste não aconteceu), que é diferente de `failed` (o
    alvo está errado) e muito diferente de `passed`.
    """


@dataclass(frozen=True)
class Imagem:
    """Bitmap cru: os bytes já desfiltrados, em ordem de varredura."""

    largura: int
    altura: int
    canais: int
    pixels: bytes

    def pixel(self, x: int, y: int) -> tuple[int, ...]:
        inicio = (y * self.largura + x) * self.canais
        return tuple(self.pixels[inicio:inicio + self.canais])


# ---------- Leitura ----------


def decodificar(dados: bytes) -> Imagem:
    """PNG → `Imagem`. Levanta `PngNaoSuportado` em tudo que não souber ler."""
    if not dados.startswith(ASSINATURA):
        raise PngNaoSuportado("não é PNG: assinatura ausente nos 8 primeiros bytes")
    largura, altura, canais = _ler_ihdr(dados)
    bruto = zlib.decompress(_juntar_idat(dados))
    esperado = altura * (1 + largura * canais)
    if len(bruto) != esperado:
        raise PngNaoSuportado(
            f"PNG truncado ou corrompido: {len(bruto)} bytes após inflar, "
            f"{esperado} esperados para {largura}x{altura} com {canais} canais")
    return Imagem(largura, altura, canais, _desfiltrar(bruto, largura, altura, canais))


def _ler_ihdr(dados: bytes) -> tuple[int, int, int]:
    if len(dados) < 33 or dados[12:16] != b"IHDR":
        raise PngNaoSuportado("PNG sem IHDR no lugar esperado")
    largura, altura, profundidade, cor, _comp, _filtro, entrelace = struct.unpack(
        ">IIBBBBB", dados[16:29])
    if profundidade != PROFUNDIDADE_ACEITA:
        raise PngNaoSuportado(
            f"bit depth {profundidade} não suportado — este decoder lê apenas 8 bits "
            "por canal. Decodificar assim mesmo devolveria uma matriz plausível e "
            "errada, e o diff daria veredito sobre uma imagem que não existe")
    if cor not in CANAIS_POR_COR:
        raise PngNaoSuportado(
            f"color type {cor} não suportado — apenas 2 (RGB) e 6 (RGBA). "
            "Paleta e cinza exigiriam resolver PLTE/tRNS, e o erro seria silencioso")
    if entrelace != SEM_ENTRELACE:
        raise PngNaoSuportado(
            f"PNG entrelaçado (Adam7, interlace={entrelace}) não suportado — as sete "
            "passadas seriam lidas como linhas sequenciais e produziriam uma imagem "
            "embaralhada que o diff trataria como mudança de layout")
    return largura, altura, CANAIS_POR_COR[cor]


def _juntar_idat(dados: bytes) -> bytes:
    """TODOS os IDAT, concatenados antes de inflar.

    Medido: o Chromium emite vários. Um decoder que lesse só o primeiro
    devolveria imagem truncada — e como a inflação de um IDAT isolado falha, o
    erro apareceria como "PNG corrompido" num arquivo perfeitamente válido.
    """
    partes, i = [], 8
    while i + 8 <= len(dados):
        tamanho = struct.unpack(">I", dados[i:i + 4])[0]
        tipo = dados[i + 4:i + 8]
        if tipo == b"IDAT":
            partes.append(dados[i + 8:i + 8 + tamanho])
        elif tipo == b"IEND":
            break
        i += 12 + tamanho
    if not partes:
        raise PngNaoSuportado("PNG sem nenhum chunk IDAT — não há pixels para ler")
    return b"".join(partes)


# ---------- Unfiltering: uma função por filtro ----------
#
# Decomposto porque `C901 max-complexity = 8` vale em `webqa/` — e é bom que
# valha: cada filtro fica testável isoladamente contra vetor conhecido, que é o
# único jeito de saber que Paeth está certo. Um `if/elif` de cinco ramos passaria
# no lint e seria indistinguível de um Paeth errado.


def _desfiltrar(bruto: bytes, largura: int, altura: int, canais: int) -> bytes:
    passo = largura * canais
    anterior = bytearray(passo)
    saida = bytearray()
    for y in range(altura):
        inicio = y * (1 + passo)
        filtro = bruto[inicio]
        linha = bytearray(bruto[inicio + 1:inicio + 1 + passo])
        aplicar = _FILTROS.get(filtro)
        if aplicar is None:
            raise PngNaoSuportado(f"tipo de filtro {filtro} desconhecido na linha {y}")
        aplicar(linha, anterior, canais)
        saida += linha
        anterior = linha
    return bytes(saida)


def _filtro_none(linha: bytearray, anterior: bytearray, canais: int) -> None:
    """Nada a fazer — a linha já está crua."""


def _filtro_sub(linha: bytearray, anterior: bytearray, canais: int) -> None:
    for i in range(canais, len(linha)):
        linha[i] = (linha[i] + linha[i - canais]) & 0xFF


def _filtro_up(linha: bytearray, anterior: bytearray, canais: int) -> None:
    for i in range(len(linha)):
        linha[i] = (linha[i] + anterior[i]) & 0xFF


def _filtro_average(linha: bytearray, anterior: bytearray, canais: int) -> None:
    for i in range(len(linha)):
        esquerda = linha[i - canais] if i >= canais else 0
        linha[i] = (linha[i] + ((esquerda + anterior[i]) >> 1)) & 0xFF


def _filtro_paeth(linha: bytearray, anterior: bytearray, canais: int) -> None:
    for i in range(len(linha)):
        esquerda = linha[i - canais] if i >= canais else 0
        acima_esquerda = anterior[i - canais] if i >= canais else 0
        linha[i] = (linha[i] + _paeth(esquerda, anterior[i], acima_esquerda)) & 0xFF


def _paeth(a: int, b: int, c: int) -> int:
    """O preditor de Paeth, como a especificação o define.

    Vetor conhecido em `tests/test_imagem.py`: escrito de cabeça, ele erra o
    desempate — e o erro não estoura, produz uma imagem levemente deslocada que
    o diff lê como página inteira mudada.
    """
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


_FILTROS = {0: _filtro_none, 1: _filtro_sub, 2: _filtro_up,
            3: _filtro_average, 4: _filtro_paeth}


# ---------- Diff ----------


@dataclass(frozen=True)
class Bloco:
    """Uma região que mudou, com a coordenada de onde ela está na página."""

    x: int
    y: int
    lado: int
    maior_desvio: int

    def __str__(self) -> str:
        return (f"bloco em ({self.x},{self.y}) {self.lado}x{self.lado}px — "
                f"maior desvio de canal: {self.maior_desvio}")


def blocos_divergentes(referencia: Imagem, atual: Imagem, *, tolerancia: int,
                       lado: int = LADO_DO_BLOCO) -> tuple[Bloco, ...]:
    """Blocos em que algum canal de algum pixel passou da tolerância.

    O comparador é `>`, não `>=`: no desvio exatamente igual à tolerância o bloco
    ainda está dentro. Mesma disciplina de borda do 25% da cobertura de foco
    (OS-43), dos 50ms do TBT (OS-46) e dos 30% da sobreposição (OS-48).

    Dimensões diferentes não viram "tudo divergente": é outro achado, com outra
    causa (viewport mudou, referência de outro perfil), e o chamador o trata
    antes de chegar aqui — ver `divergencia_de_tamanho`.
    """
    canais = min(referencia.canais, atual.canais)
    achados = []
    for topo in range(0, min(referencia.altura, atual.altura), lado):
        for esquerda in range(0, min(referencia.largura, atual.largura), lado):
            desvio = _maior_desvio(referencia, atual, esquerda, topo, lado, canais)
            if desvio > tolerancia:
                achados.append(Bloco(esquerda, topo, lado, desvio))
    return tuple(achados)


def _maior_desvio(referencia: Imagem, atual: Imagem, esquerda: int, topo: int,
                  lado: int, canais: int) -> int:
    maior = 0
    fim_y = min(topo + lado, referencia.altura, atual.altura)
    fim_x = min(esquerda + lado, referencia.largura, atual.largura)
    for y in range(topo, fim_y):
        for x in range(esquerda, fim_x):
            a, b = referencia.pixel(x, y), atual.pixel(x, y)
            for canal in range(canais):
                diferenca = abs(a[canal] - b[canal])
                if diferenca > maior:
                    maior = diferenca
    return maior


def divergencia_de_tamanho(referencia: Imagem, atual: Imagem) -> str:
    """Dimensão diferente é outro achado, e vem antes do diff.

    Comparar imagens de tamanhos diferentes bloco a bloco produziria "quase tudo
    divergente" e esconderia a causa real — que costuma ser trivial: o viewport
    mudou, ou a referência é de outro perfil.
    """
    if (referencia.largura, referencia.altura) == (atual.largura, atual.altura):
        return ""
    return (f"a captura tem {atual.largura}x{atual.altura}px e a referência tem "
            f"{referencia.largura}x{referencia.altura}px. Tamanho diferente não é "
            "regressão visual: ou o viewport mudou, ou a referência é de outro perfil. "
            "Regrave com `make referencia-visual` se a mudança for intencional")


def resumo_de_blocos(blocos, teto: int = 10) -> str:
    """As regiões, não só o percentual: quem for corrigir precisa saber ONDE."""
    lista = list(blocos)
    linhas = [f"  {b}" for b in sorted(lista, key=lambda b: -b.maior_desvio)[:teto]]
    if len(lista) > teto:
        linhas.append(f"  … e mais {len(lista) - teto}")
    return "\n".join(linhas)
