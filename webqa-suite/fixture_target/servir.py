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
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

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
APP_JS = (
    "// Bundle do alvo fixture.\n"
    "var config = { region: 'us-east-1', accessKeyId: 'AKIAIOSFODNN7EXAMPLE' };\n"
    "console.log('fixture');\n"
)

# VIOLAÇÃO (seguranca, Fase A): `.js` que o servidor devolve como HTML. Caso
# clássico de fallback de erro numa SPA — o navegador recebe documento onde
# esperava executável.
MIME_TROCADO = "<!doctype html><html lang=\"pt-BR\"><body>pagina de erro</body></html>\n"

HOME = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Loja Fixture — alvo deliberadamente nao conforme</title>
<!-- VIOLACAO: script de terceiro sem integrity/crossorigin (SRI) -->
<script src="{CDN_FALSO}"></script>
<!-- VIOLACAO (seguranca): bundle de origem com credencial exposta -->
<script src="/app.js"></script>
<!-- VIOLACAO (seguranca): .js servido como text/html -->
<script src="/fallback.js"></script>
</head><body>
<h1>Loja Fixture</h1>
<!-- VIOLACAO: imagem sem atributo alt (WCAG / LBI Art. 63) -->
<img src="/logo.png" width="1" height="1">
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
<script>
// VIOLACAO: tracker disparado antes de qualquer consentimento.
// no-cors + catch: o evento de requisicao e registrado mesmo sem rede,
// e nenhum codigo de terceiro chega a executar.
fetch("{TRACKER}", {{mode: "no-cors"}}).catch(function () {{}});
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
<h1>Politica de Privacidade</h1>
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
    """
    digest = hashlib.sha256()
    for parte in (HOME, POLITICA, APP_JS, MIME_TROCADO, *COOKIES):
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
        elif caminho == "/logo.png":
            self._responder(PIXEL, "image/png", com_cookies=False)
        elif caminho.startswith("/privacidade"):
            self._responder(POLITICA.encode("utf-8"), "text/html; charset=utf-8")
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
