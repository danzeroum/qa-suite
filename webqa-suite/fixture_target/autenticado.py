"""Alvo fixture AUTENTICADO — topologia conhecida para provar a disciplina do crawl.

Irmão de `servir.py`, com outro propósito. Aquele existe para os checks terem
violações plantadas para achar; este existe para a **navegação** ter uma forma
conhecida, e a forma é o teste:

    /            home, com menu para /produtos, /conta e /ajuda
    /produtos    ligada pelo menu
    /conta       ligada pelo menu, e liga para /ajuda (grafo, não estrela)
    /ajuda       ligada
    /orfa        EXISTE e responde 200 — e NINGUÉM a linka

A página órfã é o coração do aceite da OS-38. Ela não é um caso de borda: é a
única forma de distinguir, por fora, "o crawler segue o que a aplicação oferece"
de "o crawler acha as páginas de algum outro jeito". Um crawler que a visitasse
estaria adivinhando endereço — e adivinhar endereço é Fase C.

Tudo atrás de HTTP Basic Auth, inclusive o `robots.txt`: é o cenário que revelou,
na OS-37, que a dimensão `functional` nascia cega contra alvo protegido.

Somente stdlib.
"""
from __future__ import annotations

import base64
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
USUARIO = "operador-fixture"
SENHA = 'Xq7#fixture"auth&longa<ok>'
_ESPERADO = "Basic " + base64.b64encode(f"{USUARIO}:{SENHA}".encode()).decode("ascii")

# Cookie de sessão REAL: só existe depois de autenticar, e é o que permite
# auditar HttpOnly/Secure/SameSite de verdade em vez de "nenhum cookie".
COOKIE_DE_SESSAO = "sessionid=abc123; Path=/; HttpOnly; SameSite=Lax"

ROBOTS = "User-agent: *\nDisallow: /privado\n"

_MENU = ('<nav><a href="/produtos">Produtos</a> '
         '<a href="/conta">Conta</a> <a href="/ajuda">Ajuda</a></nav>')


def _pagina(titulo: str, corpo: str) -> bytes:
    return (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{titulo}</title></head><body><h1>{titulo}</h1>"
        f"{corpo}</body></html>"
    ).encode()


# A órfã NÃO aparece em nenhum `href` — é o que a torna órfã.
PAGINAS = {
    "/": _pagina("Área autenticada", _MENU + "<p>Bem-vindo.</p>"),
    "/produtos": _pagina("Produtos", _MENU + "<p>Catálogo interno.</p>"),
    "/conta": _pagina("Conta", _MENU + '<p>Dados. <a href="/ajuda">Ajuda</a></p>'),
    "/ajuda": _pagina("Ajuda", _MENU + "<p>Suporte.</p>"),
    "/orfa": _pagina("Órfã", "<p>Ninguém me linka.</p>"),
}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 (nome exigido pelo BaseHTTPRequestHandler)
        if self.headers.get("Authorization") != _ESPERADO:
            self._responder(b"<!doctype html><title>401</title><h1>401</h1>",
                            "text/html; charset=utf-8", status=401,
                            extras=[("WWW-Authenticate", 'Basic realm="restrito"')])
            return
        caminho = self.path.split("?", 1)[0].rstrip("/") or "/"
        if caminho == "/robots.txt":
            self._responder(ROBOTS.encode("utf-8"), "text/plain; charset=utf-8")
        elif caminho in PAGINAS:
            self._responder(PAGINAS[caminho], "text/html; charset=utf-8",
                            extras=[("Set-Cookie", COOKIE_DE_SESSAO)])
        else:
            self._responder(b"nao encontrado", "text/plain; charset=utf-8", status=404)

    def _responder(self, corpo: bytes, tipo: str, *, status: int = 200, extras=()) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        for nome, valor in extras:
            self.send_header(nome, valor)
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *args) -> None:
        """Silencioso: o log do fixture não é o objeto de observação."""


class AlvoAutenticado:
    """Sobe o alvo em porta efêmera. Usado como context manager na verificação."""

    def __init__(self, porta: int = 0) -> None:
        self._porta = porta
        self._servidor: ThreadingHTTPServer | None = None
        self._thread = None

    def __enter__(self) -> AlvoAutenticado:
        import threading

        self._servidor = ThreadingHTTPServer((HOST, self._porta), _Handler)
        self._thread = threading.Thread(target=self._servidor.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_) -> None:
        if self._servidor is not None:
            self._servidor.shutdown()
            self._servidor.server_close()

    @property
    def url(self) -> str:
        assert self._servidor is not None, "alvo não iniciado"
        return f"http://{HOST}:{self._servidor.server_address[1]}"


if __name__ == "__main__":
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    with AlvoAutenticado(porta) as alvo:
        print(f"alvo autenticado em {alvo.url} (usuario={USUARIO})", flush=True)
        try:
            while True:
                sys.stdin.readline()
        except KeyboardInterrupt:
            pass
