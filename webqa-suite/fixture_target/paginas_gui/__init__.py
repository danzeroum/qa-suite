"""Páginas de GUI do alvo fabricado — violações que os checks de `gui` lerão.

Vivem AQUI, e não em `servir.py`, por uma razão que não é organizacional: elas
ficam **fora de `identidade()`**. O ledger de estabilidade
(`scripts/estabilidade.py`) usa a identidade do alvo como chave da caminhada, e
mexer no que entra no hash reinicia a sequência sem-flake. Estas páginas não são
observadas por nenhum check do contrato passivo hoje, então incluí-las no hash
custaria um reinício por conteúdo que ninguém mede — o mesmo raciocínio que já
mantém `ISCAS_FASE_C` fora do hash (`servir.py`).

O que precisa estar na home para ser observado — a faixa larga, o foco sem
indicador, o alvo de toque pequeno, a animação infinita — está na home e paga o
reinício uma vez só. O que só faz sentido numa página própria está aqui.

Conteúdo construído em memória e legível no diff: o que a violação É se lê no
código, não num arquivo opaco. Somente stdlib.
"""
from __future__ import annotations

# VIOLAÇÃO (gui, GUI-FOCO-04): armadilha de foco. O `onblur` devolve o foco ao
# próprio campo, então Tab nunca sai daqui — quem navega por teclado fica preso
# e não alcança o resto da página. Mora nesta página, e não na home, de
# propósito: uma armadilha na home prenderia a caminhada de foco dos checks
# GUI-FOCO-01/02/03, que precisam percorrer a página inteira para medir o que
# medem. A armadilha ganha a sua própria página e o seu próprio check.
_ARMADILHA = """
<section id="armadilha">
  <h2>Campo que não devolve o foco</h2>
  <label for="preso">Cupom</label>
  <input id="preso" name="cupom" type="text" onblur="this.focus()">
</section>
"""

# VIOLAÇÃO (gui, GUI-ESTADO-03): o controle desabilitado é só mais claro — não
# tem `disabled` nem `aria-disabled`, então leitor de tela o anuncia como
# acionável e teclado ainda o alcança.
# VIOLAÇÃO (gui, GUI-ESTADO-01): o estado de erro é sinalizado SÓ por cor, sem
# texto, ícone ou forma que o acompanhe (WCAG 1.4.1).
# VIOLAÇÃO (gui, GUI-ESTADO-04): o estado vazio é uma caixa sem nenhum texto —
# o visitante não sabe se carregou, se falhou, ou se não há nada.
_ESTADOS = """
<section id="estados">
  <h2>Estados de componente</h2>
  <p><button class="btn">Normal</button></p>
  <p><button class="btn hover-forcado">Hover</button></p>
  <p><button class="btn foco-forcado">Foco</button></p>
  <p><button class="btn ativo-forcado">Ativo</button></p>
  <p><button class="btn falso-desabilitado">Desabilitado (sem disabled)</button></p>
  <p><span class="carregando" aria-hidden="true"></span> Carregando</p>
  <p><input class="campo-erro" aria-label="CEP" value="00000"></p>
  <p><span class="vazio"></span></p>
</section>
"""

_ESTILO = """
.btn { padding: 8px 12px; }
/* Os "forçados" existem para a captura de estado do GUI-VIS-02 sair
   determinística: hover e active de verdade dependem de ponteiro, e um
   screenshot que depende de ponteiro é um screenshot que oscila. */
.hover-forcado { background: #dde; }
.foco-forcado { outline: 2px solid #35c; }
.ativo-forcado { background: #bbc; }
.falso-desabilitado { color: #aaa; }
.carregando { display: inline-block; width: 12px; height: 12px; background: #ccc; }
/* VIOLAÇÃO (gui, GUI-ESTADO-01): erro só por cor da borda. */
.campo-erro { border: 2px solid #c00; }
.vazio { display: inline-block; width: 120px; height: 40px; background: #f4f4f4; }
"""

ESTADOS_HTML = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Galeria de estados — Loja Fixture</title>
<style>{_ESTILO}</style>
</head><body>
<h1>Galeria de estados</h1>
<p>Página do alvo fabricado. Cada bloco carrega uma violação declarada no
código-fonte desta página.</p>
{_ESTADOS}
{_ARMADILHA}
</body></html>
"""

# Resposta da API que a home consome. Responde 200 e ESTÁVEL de propósito: a
# violação do GUI-RESIL-01 não está aqui, está na home, que consome esta
# resposta sem nenhum tratamento de falha. O check é quem força o erro, no
# cliente, com `page.route` — o alvo nunca precisa servir 500 para que a falta
# de tratamento fique visível.
API_PEDIDOS = '{"total": 3, "itens": ["a", "b", "c"]}\n'

# Caminhos servidos por `servir.py`. Mapa, e não uma cadeia de `elif`, porque o
# teste que prova a ausência destas páginas no hash itera sobre ele — a lista
# de páginas e a lista conferida são a mesma coisa, e não podem divergir.
PAGINAS_GUI: dict[str, tuple[bytes, str]] = {
    "/gui/estados": (ESTADOS_HTML.encode("utf-8"), "text/html; charset=utf-8"),
    "/gui/api/pedidos": (API_PEDIDOS.encode("utf-8"), "application/json"),
}
