"""Alvo fabricado, deliberadamente NÃO conforme — o teste de sistema da dimensão.

Por que existe: medir a estabilidade da infraestrutura de navegador contra um
alvo de produção mistura dois sinais. Se o site alheio muda, a suíte "flaka" sem
que nada tenha piorado. Aqui o alvo é congelado: qualquer variação de resultado é
da SUÍTE ou do AMBIENTE, nunca do alvo.

O contrato de violações está em `fixture_target/esperado.json` e é conferido por
`tests/test_alvo_fixture.py`: os FAILs observados têm de ser exatamente os
esperados — nem a mais (regressão que reprova alvo conforme) nem a menos
(check que parou de detectar e ninguém notou).

Limites conhecidos, declarados de propósito:

* O "CDN sem SRI" aponta para um domínio `.invalid` (RFC 2606, nunca resolve).
  Os checks de SRI leem o ATRIBUTO do HTML, não a resposta — então a violação é
  exercida de verdade sem depender de terceiro. O navegador tenta resolver e
  falha de imediato; isso não faz parte do contrato.
* O único contato com host externo é um `fetch` abortável para um domínio de
  tracker: o `network_log` registra o evento de REQUISIÇÃO, e o teste depende
  disso, nunca da resposta. Funciona offline, e nenhum JavaScript de terceiro é
  executado.

Somente stdlib.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import struct
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    # Caminho normal: importado como pacote (`from fixture_target import servir`).
    from fixture_target.paginas_gui import PAGINAS_GUI
except ImportError:  # pragma: no cover - só na execução direta
    # `python fixture_target/servir.py` (Makefile e docker/entrypoint.sh) põe a
    # PRÓPRIA pasta no sys.path, e aí o nome do pacote não resolve. As duas
    # formas de subir o alvo têm de funcionar: uma é como os testes o usam, a
    # outra é como a VPS o sobe todas as noites.
    from paginas_gui import PAGINAS_GUI

HOST = "127.0.0.1"

# Domínio reservado pela RFC 2606: garantidamente inexistente, sem tráfego real.
CDN_FALSO = "https://cdn.exemplo-fixture.invalid/jquery-3.7.1.min.js"
# Domínio de tracker real é necessário: é a lista TRACKER_DOMAINS que está sob
# teste. Só a requisição é observada — a resposta é irrelevante e descartada.
TRACKER = "https://www.googletagmanager.com/gtm.js?id=GTM-FIXTURE"

# PNG 1x1 transparente: evita 404 no log de rede, que poderia ser lido como
# problema de infraestrutura pelo classificador de estabilidade.
PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGP6zwAAAgUBAScrLu8AAAAASUVORK5CYII="
)

# Vida útil de 730 dias (> teto de 400) + cookie de sessão que NÃO deve reprovar.
COOKIES = (
    "_ga=GA1.1.fixture; Max-Age=63072000; Path=/",
    "sessionid=fixture; Path=/; HttpOnly",
)

# VIOLAÇÃO (seguranca, Fase A): credencial servida ao navegador. A chave é o
# exemplo público da documentação da AWS — formato válido, valor inerte, e
# nenhum segredo real entra no repositório. O check tem de detectá-la e o
# relatório tem de mostrá-la MASCARADA.
#
# VIOLAÇÃO (gui, GUI-PERF-01): seis blocos de ~110ms bloqueiam a thread
# principal durante a carga. São 6 long tasks (> 50ms cada) e TBT ≈ 6 × (110−50)
# = 360ms, acima do orçamento de 200ms. Precisa estar AQUI, e não numa página
# nova: o bloqueio só é medível na página que o check carrega, e `app.js` é o
# que a home puxa. É a única constante hasheada que esta OS toca por vontade
# própria — ver o comentário de `identidade()`.
#
# **Os blocos são reagendados, não sequenciais num laço só.** Um `for` com seis
# iterações síncronas é UMA tarefa de 660ms para o navegador, e a API de
# `longtask` reporta 1, não 6 — a validação em navegador real mostrou
# exatamente isso. Só o retorno ao laço de eventos (`setTimeout`) separa uma
# tarefa da seguinte. O primeiro bloco fica síncrono de propósito: é ele que
# atrasa o DOMContentLoaded, como um bundle pesado de verdade faria.
#
# Bloqueio por laço com prazo, nunca `while(true)`: seis tarefas curtas e
# limitadas produzem o sinal sem risco de travar o navegador se algo mudar.
APP_JS = (
    "// Bundle do alvo fixture.\n"
    "var config = { region: 'us-east-1', accessKeyId: 'AKIAIOSFODNN7EXAMPLE' };\n"
    "var blocosRestantes = 6;\n"
    "function bloquearThreadPrincipal() {\n"
    "  var fim = Date.now() + 110;\n"
    "  while (Date.now() < fim) { /* bloqueio deliberado */ }\n"
    "  if (--blocosRestantes > 0) { setTimeout(bloquearThreadPrincipal, 0); }\n"
    "}\n"
    "bloquearThreadPrincipal();\n"
    "console.log('fixture');\n"
)

# VIOLAÇÃO (seguranca, Fase A): `.js` que o servidor devolve como HTML. Caso
# clássico de fallback de erro numa SPA — o navegador recebe documento onde
# esperava executável.
MIME_TROCADO = "<!doctype html><html lang=\"pt-BR\"><body>pagina de erro</body></html>\n"

# VIOLAÇÃO (seguranca, Fase B): SVG com handler inline — documento executável
# servido como se fosse imagem.
SVG_EXECUTAVEL = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1" '
    'onload="console.log(1)"><rect width="1" height="1"/></svg>\n'
)

# VIOLAÇÃO (seguranca, Fase B): bundle referenciando sourcemap. O check aponta o
# caminho e NÃO baixa o .map — baixar seria sondagem (Fase C).
BUNDLE_JS = "var x = 1;\n//# sourceMappingURL=/bundle.js.map\n"

# ---------- ISCAS DE EXPOSIÇÃO (Fase C) — NÃO LINKADAS, inertes até C1 ----------
#
# Recursos que só se alcança PEDINDO diretamente — nada no HOME aponta para eles.
# É exatamente o que a sondagem ativa (Fase C) faria: pedir ao servidor o que ele
# não ofereceu. Servem para o teste de nível de SISTEMA da Fase C (matriz A.4),
# quando o motor existir (pós-C0d). Enquanto a trava está fechada, ficam inertes:
# nenhum check passivo os busca.
#
# Conteúdo FALSO e inofensivo — nenhum segredo real entra no repositório, do mesmo
# jeito que a chave da AWS acima é o exemplo público da documentação. E, de
# propósito, ficam FORA de `identidade()`: o ledger de estabilidade mede o
# contrato PASSIVO, que estes recursos não tocam — incluí-los resetaria a
# sequência sem-flake por conteúdo que nenhum check observa.
MARCA_ISCA = "isca-fixture-fase-c"

# Assinatura clássica de repositório .git exposto. Formato real de um HEAD, valor
# inerte (aponta para um branch, não carrega segredo).
GIT_HEAD = "ref: refs/heads/main\n"

# `.env` exposto: o alvo de SSRF/exposição mais comum. Valores explicitamente
# FALSOS — o teste e o grep do repo provam que não há segredo real aqui.
ENV_ISCA = (
    f"# {MARCA_ISCA}: valores FALSOS de teste, nenhum segredo real\n"
    "APP_ENV=fixture\n"
    "DB_HOST=127.0.0.1\n"
    "API_KEY=exemplo-fake-nao-e-segredo\n"
)


def _backup_zip() -> bytes:
    """Zip mínimo e VÁLIDO com um único arquivo-isca de conteúdo falso.

    Construído em memória (stdlib `zipfile`), sem binário opaco no repo — o que a
    isca É fica legível no diff. `date_time` fixo mantém os bytes determinísticos.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as arquivo:
        info = zipfile.ZipInfo("leia.txt", date_time=(1980, 1, 1, 0, 0, 0))
        arquivo.writestr(info, f"{MARCA_ISCA}: backup falso, sem dado real\n")
    return buffer.getvalue()


BACKUP_ZIP = _backup_zip()

# Iscas de exposição da Fase C (existência 2xx = achado). Mapa REUSÁVEL: o teste
# de sistema do motor (tests/test_sondagem.py) prova a detecção ponta a ponta
# contra AS MESMAS iscas que o fixture serve — remover uma daqui some do fixture
# e reprova o teste juntos (prova por mutação do nível A.4).
ISCAS_FASE_C: dict[str, tuple[bytes, str]] = {
    "/.git/HEAD": (GIT_HEAD.encode("utf-8"), "text/plain; charset=utf-8"),
    "/.env": (ENV_ISCA.encode("utf-8"), "text/plain; charset=utf-8"),
    "/backup.zip": (BACKUP_ZIP, "application/zip"),
}


def _foto_com_gps() -> bytes:
    """JPEG 1x1 válido com APP1/EXIF contendo ponteiro de IFD de GPS.

    VIOLAÇÃO (seguranca, Fase B). Construído aqui, em stdlib, em vez de
    versionar um binário: o que a violação É fica legível no diff, e não há
    arquivo opaco no repositório. Nenhuma coordenada real — só a estrutura que
    o detector procura.
    """
    ifd0_offset = 8
    gps_offset = ifd0_offset + 2 + 12 + 4
    ifd0 = (struct.pack("<H", 1)
            + struct.pack("<HHII", 0x8825, 4, 1, gps_offset)   # GPSInfo → IFD de GPS
            + struct.pack("<I", 0))
    gps = (struct.pack("<H", 1)
           + struct.pack("<HHI4s", 0x0001, 2, 2, b"N\x00\x00\x00")  # GPSLatitudeRef
           + struct.pack("<I", 0))
    corpo = b"Exif\x00\x00" + b"II*\x00" + struct.pack("<I", ifd0_offset) + ifd0 + gps
    app1 = b"\xff\xe1" + struct.pack(">H", len(corpo) + 2) + corpo
    return JPEG_BASE[:2] + app1 + JPEG_BASE[2:]


# JPEG 1x1 mínimo e válido — base para a foto com EXIF.
JPEG_BASE = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
    "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAARCAABAAEDASIAAhEBAxEB/8QAHwAA"
    "AQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIh"
    "MUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpT"
    "VFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5"
    "usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/9oACAEBAAA/APf6KKKAP//Z")

FOTO_GPS = _foto_com_gps()

# Bloco de GUI da home. Fica numa constante própria só para o diff ficar
# legível; o VALOR é interpolado em HOME, então mexer aqui muda `identidade()`
# exatamente como mexer no resto da home — não há porta dos fundos para o hash.
#
# Cada regra abaixo é a contraparte de um dos dez primeiros checks
# (docs/GUI-CATALOGO.md §3). Elas moram na home porque é a home que esses checks
# carregam: violação em página não visitada não é detectada, e um fixture que
# "reprova de propósito" onde ninguém olha dá a mesma confiança falsa que o
# check ausente.
_ESTILO_GUI = """
/* VIOLACAO (gui, GUI-RESP-01): faixa de 900px nao cabe em 320 CSS px e
   forca rolagem horizontal (WCAG 1.4.10). */
.faixa-larga { min-width: 900px; background: #eee; }
/* VIOLACAO (gui, GUI-TIPO-01): altura travada + overflow hidden cortam o
   texto quando ele cresce a 200% (WCAG 1.4.4). */
.altura-travada { height: 24px; overflow: hidden; }
/* VIOLACAO (gui, GUI-FOCO-01): foco sem nenhum indicador visivel
   (WCAG 2.4.7). */
.sem-foco:focus { outline: none; box-shadow: none; }
/* VIOLACAO (gui, GUI-FOCO-03): barra fixa cobre o que recebe foco no fim da
   pagina (WCAG 2.4.11, criterio novo da 2.2). O z-index e explicito: sem ele a
   cobertura depende da ordem do documento, e a violacao passaria a ser um
   acidente de layout em vez de um fato. */
.barra-fixa { position: fixed; left: 0; right: 0; bottom: 0; height: 72px;
              background: #333; color: #fff; z-index: 10; }
/* A pagina precisa ROLAR para a barra cobrir alguma coisa: numa pagina que
   cabe na tela, o navegador nao rola e o ultimo botao fica acima da barra —
   foi o que a validacao em navegador real mostrou. Com o documento mais alto
   que a viewport, focar o ultimo botao rola o MINIMO necessario, o que o
   deixa rente ao rodape, exatamente sob a barra. */
.rolagem-longa { height: 1200px; }
/* VIOLACAO (gui, GUI-ALVO-01): 16x16 px, abaixo dos 24 exigidos (WCAG 2.5.8).
   Sao DOIS, colados: um alvo pequeno SOZINHO e conforme pela excecao de
   espacamento da propria norma — um circulo de 24px centrado nele nao
   encostaria em ninguem. Com o vizinho a 2px, os circulos se cruzam e a
   excecao cai. Foi o check que mostrou isso: a primeira versao do fixture
   declarava violacao onde a norma perdoa. */
.alvo-pequeno { display: inline-block; width: 16px; height: 16px;
                background: #567; }
.alvo-pequeno + .alvo-pequeno { margin-left: 2px; }
/* VIOLACAO (gui, GUI-MOV-01): animacao infinita e NENHUMA media query de
   prefers-reduced-motion que a suprima (WCAG 2.3.3). */
@keyframes girar { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.gira { display: inline-block; animation: girar 2s linear infinite; }
/* VIOLACAO (gui, GUI-CONTR-01): o tema escuro existe (logo, o check nao pula)
   e nele o aviso fica em ~1.6:1, longe dos 4.5:1 (WCAG 1.4.3). */
@media (prefers-color-scheme: dark) {
  body { background: #222222; color: #ffffff; }
  .aviso-tema { color: #3a3a3a; background: #222222; }
}
"""

# VIOLACAO (gui, GUI-FOCO-02): na tela a ordem e Comprar, Cancelar, Salvar,
# Voltar; os tabindex a invertem por completo (WCAG 2.4.3). tabindex positivo de
# proposito — e o jeito de descolar ordem visual de ordem de foco sem depender de
# CSS de layout.
#
# Sao QUATRO botoes, e nao dois, porque o limiar do check e folgado (2) na Fase 1:
# a inversao e medida por geometria, e a geometria nao conhece a intencao do
# layout, entao grade densa produz salto legitimo. Um par invertido gera UMA
# inversao e passaria no limiar — o alvo fabricado precisa ultrapassa-lo para
# exercer o check de verdade. Quatro em ordem reversa geram tres.
_CORPO_GUI = """
<section id="gui">
  <h2>Area de compra</h2>
  <p class="faixa-larga">Faixa de largura fixa que nao reflui.</p>
  <p class="altura-travada">Este paragrafo cabe em uma linha na largura cheia e
  passa a ocupar duas quando o usuario amplia a fonte, momento em que a segunda
  linha e cortada pelo overflow hidden e deixa de estar disponivel.</p>
  <p><button class="sem-foco">Buscar</button></p>
  <p>
    <button tabindex="4">Comprar</button>
    <button tabindex="3">Cancelar</button>
    <button tabindex="2">Salvar</button>
    <button tabindex="1">Voltar</button>
  </p>
  <p><a class="alvo-pequeno" href="/gui/estados" aria-label="Galeria de estados"></a><a
     class="alvo-pequeno" href="/gui/estados#armadilha" aria-label="Armadilha de foco"></a></p>
  <p><span class="gira" aria-hidden="true">*</span> processando</p>
  <p class="aviso-tema">Aviso que some no tema escuro.</p>
  <p id="pedidos">carregando pedidos...</p>
  <div class="rolagem-longa"></div>
  <p><button>Finalizar</button></p>
</section>
<div class="barra-fixa">rodape fixo</div>
"""

HOME = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Loja Fixture — alvo deliberadamente nao conforme</title>
<style>{_ESTILO_GUI}</style>
<!-- VIOLACAO: script de terceiro sem integrity/crossorigin (SRI) -->
<script src="{CDN_FALSO}"></script>
<!-- VIOLACAO (seguranca): bundle de origem com credencial exposta -->
<script src="/app.js"></script>
<!-- VIOLACAO (seguranca): .js servido como text/html -->
<script src="/fallback.js"></script>
<!-- VIOLACAO (seguranca Fase B): bundle referenciando sourcemap -->
<script src="/bundle.js"></script>
</head><body>
<h1>Loja Fixture</h1>
<!-- VIOLACAO: imagem sem atributo alt (WCAG / LBI Art. 63) -->
<img src="/logo.png" width="1" height="1">
<!-- VIOLACAO (seguranca Fase B): SVG com handler inline -->
<img src="/icone.svg" alt="icone" width="1" height="1">
<!-- VIOLACAO (seguranca Fase B): foto publicada com EXIF-GPS -->
<img src="/foto.jpg" alt="foto" width="1" height="1">
<!-- VIOLACAO: dado pessoal na query string -->
<a href="/newsletter?email=joao@exemplo.com">assine a newsletter</a>
<a href="/privacidade">Politica de Privacidade</a>
<!-- VIOLACAO: formulario com campo pessoal em GET e fora de HTTPS.
     O rotulo existe de proposito: a unica violacao de acessibilidade
     do fixture e a imagem sem alt. -->
<form action="/newsletter" method="get">
  <label for="email">E-mail</label>
  <input id="email" name="email" type="text">
  <button type="submit">Enviar</button>
</form>
{_CORPO_GUI}
<script>
// VIOLACAO: tracker disparado antes de qualquer consentimento.
// no-cors + catch: o evento de requisicao e registrado mesmo sem rede,
// e nenhum codigo de terceiro chega a executar.
fetch("{TRACKER}", {{mode: "no-cors"}}).catch(function () {{}});
// VIOLACAO (gui, GUI-RESIL-01): consome a API SEM nenhum tratamento de falha —
// sem .catch, sem checar r.ok, sem estado de erro. Em operacao normal a API
// responde 200 e o paragrafo e preenchido; quando ela falha, #pedidos fica
// preso em "carregando pedidos..." para sempre e nada avisa o visitante.
// Quem forca a falha e o CHECK, no cliente, com page.route: o alvo nunca
// precisa servir 500 para que a ausencia de tratamento fique observavel.
fetch("/gui/api/pedidos")
  .then(function (r) {{ return r.json(); }})
  .then(function (d) {{
    document.getElementById("pedidos").textContent = d.total + " pedidos";
  }});
</script>
</body></html>
"""

# Politica CONFORME: transparencia nao esta entre as violacoes do fixture, então
# os checks do Art. 9/18/41 devem PASSAR — o contrato cobre os dois lados.
_CORPO_POLITICA = (
    "Esta politica descreve como tratamos dados pessoais no ambiente de teste. " * 40
)
POLITICA = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Politica de Privacidade — Loja Fixture</title></head><body>
<style>@keyframes piscar {{ from {{ opacity: 1; }} to {{ opacity: .2; }} }}
.plantada {{ animation: piscar 1s linear infinite; }}</style>
<h1 class="plantada">Politica de Privacidade</h1>
<p>{_CORPO_POLITICA}</p>
<p>O titular tem direito de acesso, correcao, eliminacao e portabilidade dos
seus dados, e pode revogar o consentimento a qualquer momento.</p>
<p>Nosso encarregado (DPO) pode ser contatado em
<a href="mailto:dpo@exemplo-fixture.invalid">dpo@exemplo-fixture.invalid</a>.</p>
</body></html>
"""


def identidade() -> str:
    """Identidade estável do alvo, para o ledger de estabilidade.

    Hash do que o alvo SERVE — não do arquivo e não da URL. Duas consequências
    deliberadas:

    * a porta é efêmera e muda a cada noite; se a identidade viesse da URL, a
      sequência sem flake zeraria todo dia e nunca chegaria a 10;
    * mexer num comentário não muda a identidade, mas mexer numa violação muda —
      e aí a sequência recomeça, porque o alvo passou a ser outro.

    **Por que as violações de GUI entraram todas de uma vez (OS-40).** Reiniciar
    a caminhada custa o que já havia sido andado, e nada mais. Quando esta OS
    foi executada a sequência oficial estava em **0/10**: reiniciar zero custa
    zero. Espalhar as violações de GUI por três OS ao longo das fases teria
    cobrado o reinício três vezes — e a terceira poderia cair sobre um 8/10,
    custando oito noites de espera para destravar a LGPD Fase 2. É por isso que
    esta OS é a primeira da fila em `docs/handoff/ordens-de-servico/OS-gui-fila.md`,
    e não por preferência de ordenação.

    Pelo mesmo motivo, `PAGINAS_GUI` fica **fora** deste hash, como as
    `ISCAS_FASE_C`: são páginas que nenhum check do contrato passivo observa, e
    incluí-las cobraria um reinício por conteúdo que ninguém mede.
    """
    digest = hashlib.sha256()
    for parte in (HOME, POLITICA, APP_JS, MIME_TROCADO, SVG_EXECUTAVEL,
                  BUNDLE_JS, *COOKIES):
        digest.update(parte.encode("utf-8"))
        digest.update(b"\0")
    return "fixture_target:" + digest.hexdigest()


class _Handler(BaseHTTPRequestHandler):
    """Serve três recursos e injeta os cabeçalhos que os checks observam."""

    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 (nome exigido pelo BaseHTTPRequestHandler)
        caminho = self.path.split("?", 1)[0]
        if caminho == "/app.js":
            self._responder(APP_JS.encode("utf-8"), "application/javascript",
                            com_cookies=False)
        elif caminho == "/fallback.js":
            # Content-Type MENTE sobre o corpo, de proposito.
            self._responder(MIME_TROCADO.encode("utf-8"), "text/html; charset=utf-8",
                            com_cookies=False)
        elif caminho == "/icone.svg":
            self._responder(SVG_EXECUTAVEL.encode("utf-8"), "image/svg+xml",
                            com_cookies=False)
        elif caminho == "/foto.jpg":
            self._responder(FOTO_GPS, "image/jpeg", com_cookies=False)
        elif caminho == "/bundle.js":
            self._responder(BUNDLE_JS.encode("utf-8"), "application/javascript",
                            com_cookies=False)
        elif caminho == "/logo.png":
            self._responder(PIXEL, "image/png", com_cookies=False)
        elif caminho.startswith("/privacidade"):
            self._responder(POLITICA.encode("utf-8"), "text/html; charset=utf-8")
        elif caminho in PAGINAS_GUI:
            # Páginas de GUI (OS-40). LINKADAS a partir da home, de propósito: a
            # galeria é alcançável seguindo o que a aplicação oferece, então o
            # crawl passivo chega nela sem ninguém fabricar endereço.
            corpo, tipo = PAGINAS_GUI[caminho]
            self._responder(corpo, tipo, com_cookies=False)
        elif caminho in ISCAS_FASE_C:
            # Iscas de exposição (Fase C): existência 2xx = achado. Inerte até C1.
            corpo, tipo = ISCAS_FASE_C[caminho]
            self._responder(corpo, tipo, com_cookies=False)
        elif caminho in ("/", "/newsletter"):
            self._responder(HOME.encode("utf-8"), "text/html; charset=utf-8")
        else:
            # 404 explícito: nada de /.well-known/security.txt nem
            # Permissions-Policy — a ausência deles é xfail informativo, e o
            # fixture também precisa exercitar esse caminho.
            self._responder(b"nao encontrado", "text/plain; charset=utf-8", status=404)

    def _responder(self, corpo: bytes, tipo: str, *, status: int = 200,
                   com_cookies: bool = True) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        if com_cookies:
            for cookie in COOKIES:
                self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *args) -> None:
        """Silencioso: o log do fixture não é o objeto de observação."""


def _bind(porta: int, tentativas: int = 10) -> ThreadingHTTPServer:
    """Sobe o servidor; porta 0 = efêmera escolhida pelo SO (sem colisão).

    Com porta explícita ocupada, tenta as seguintes e, em último caso, cai para
    efêmera: porta ocupada é problema de ambiente, não motivo de flake.
    """
    if porta == 0:
        return ThreadingHTTPServer((HOST, 0), _Handler)
    for offset in range(tentativas):
        try:
            return ThreadingHTTPServer((HOST, porta + offset), _Handler)
        except OSError:
            continue
    return ThreadingHTTPServer((HOST, 0), _Handler)


class AlvoFixture:
    """Context manager: sobe o alvo numa thread e devolve a URL efetiva."""

    def __init__(self, porta: int = 0) -> None:
        self._porta = porta
        self._servidor: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> AlvoFixture:
        self._servidor = _bind(self._porta)
        self._thread = threading.Thread(target=self._servidor.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        if self._servidor is not None:
            self._servidor.shutdown()
            self._servidor.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    @property
    def porta(self) -> int:
        assert self._servidor is not None, "use dentro do with"
        return int(self._servidor.server_address[1])

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.porta}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=0,
                        help="0 (padrão) = porta efêmera escolhida pelo SO")
    parser.add_argument("--url-file", type=Path, default=None,
                        help="grava a URL efetiva neste arquivo (uso em CI)")
    args = parser.parse_args(argv)

    with AlvoFixture(args.port) as alvo:
        if args.url_file:
            args.url_file.write_text(alvo.url + "\n", encoding="utf-8")
        print(alvo.url, flush=True)
        try:
            while True:
                threading.Event().wait(3600)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
