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

# Página CONFORME que consome a MESMA API — o outro lado do contrato do GUI-RESIL.
#
# Sem ela, os quatro checks de resiliência só teriam a direção "reprova": contra
# `/privacidade` eles PULAM, porque aquela página não faz chamada nenhuma, e um
# check que nunca foi visto passando é um check que ninguém sabe se reprova por
# regressão ou por natureza. É a mesma razão de `test_transparencia_passa_no_fixture`
# existir no contrato: provar os dois lados, senão um check que reprova tudo
# passaria por "funcionando".
#
# NÃO é linkada pela home, e a omissão é deliberada: um `<a>` a mais lá dentro
# mudaria a contagem de alvos de toque e a caminhada de foco, que são justamente
# o que três checks do contrato medem. Esta página é endereçada direto, como
# alvo (`WEBQA_TARGET_URL`), no mesmo papel que `/privacidade` cumpre no smoke.
#
# O que ela faz de certo, e que o `#estoque` da home faz de errado:
#   * `AbortController` com prazo — pedido que não responde vira falha tratada,
#     em vez de "carregando..." para sempre;
#   * `r.ok` conferido — 500 com corpo válido não é sucesso;
#   * o `catch` mostra mensagem PARA GENTE, e nunca o objeto de erro;
#   * escuta o evento `offline`, que é o navegador avisando a página de que a
#     conexão caiu — quem não escuta não tem como contar a ninguém.
_RESILIENTE_JS = """
function mostrar(texto) { document.getElementById('pedidos').textContent = texto; }
var controlador = new AbortController();
var prazo = setTimeout(function () { controlador.abort(); }, 2000);
fetch('/gui/api/pedidos', {signal: controlador.signal})
  .then(function (r) {
    if (!r.ok) { throw new Error('resposta ' + r.status); }
    return r.json();
  })
  .then(function (d) { clearTimeout(prazo); mostrar(d.total + ' pedidos'); })
  .catch(function () {
    clearTimeout(prazo);
    mostrar('Nao foi possivel carregar seus pedidos agora. Tente novamente em instantes.');
  });
window.addEventListener('offline', function () {
  mostrar('Voce esta sem conexao com a internet. Tente novamente quando ela voltar.');
});
"""

RESILIENTE_HTML = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Meus pedidos — Loja Fixture</title>
</head><body>
<main>
  <h1>Meus pedidos</h1>
  <p id="pedidos">carregando pedidos...</p>
</main>
<script>{_RESILIENTE_JS}</script>
</body></html>
"""

# VIOLAÇÕES de desempenho SOB CONDIÇÃO DEGRADADA (gui, GUI-PERF-02/03, OS-50).
#
# Esta página existe porque a home NÃO serve para o que a OS-50 mede, e a
# medição é que mostrou isso — não o projeto.
#
# **O bloqueio da home é imune a throttling de CPU, por construção.** Ele é
# `while (Date.now() < fim)`: um laço com prazo de RELÓGIO. Estrangular a CPU em
# ×4 reduz instruções por segundo, e não o relógio — então o laço sai no mesmo
# instante e a tarefa dura os mesmos 110ms. Medido: TBT 363ms sob ×4 contra
# 357ms sem throttle, uma diferença de 2%. Um check de CPU lenta apontado para a
# home relataria "a degradação não mudou nada" e estaria certo pelo motivo
# errado — mediria um alvo que não pode reagir ao que ele emula.
#
# A violação daqui é COMPUTACIONAL: trabalho de quantidade fixa, cujo tempo
# escala com a velocidade da máquina. É o que a torna interessante — ela é
# **invisível no desktop e severa no aparelho modesto**:
#
#   sem throttle  ~39ms por bloco → nenhuma tarefa longa, TBT 0
#   sob CPU ×4   ~156ms por bloco → dez tarefas longas, TBT ~1000ms
#
# Um alvo assim passa em toda medição de laboratório e falha na mão de quem usa.
# É exatamente a classe de defeito que só um perfil degradado encontra, e a razão
# de esta OS existir.
#
# **O dimensionamento é apertado dos dois lados, e o número saiu de medição.** A
# janela é estreita por aritmética, não por gosto: o bloco precisa ficar ABAIXO
# de 50ms sem throttle (senão a violação aparece no desktop e deixa de ser o que
# esta página existe para ser) e BEM ACIMA de 50ms sob ×4 (senão não há tarefa
# longa e o TBT é zero). Como o fator é fixo em 4, isso confina a duração do
# bloco à faixa 21ms–50ms na máquina de referência. `n` foi escolhido para cair
# no meio dela (~39ms), e o número de blocos subiu de 6 para 10 porque é o outro
# grau de liberdade: o TBT cresce com a CONTAGEM sem empurrar o bloco individual
# para perto do teto de 50ms. Máquina muito mais rápida encolhe o bloco e pode
# apagar o sinal — é limite conhecido, e por isso o veredito duro desta família
# só existe sob `WEBQA_ORIGEM=vps`, onde a máquina é uma só e conhecida.
#
# Blocos REAGENDADOS por `setTimeout`, e não um laço só, pela lição da OS-40 já
# registrada em `webqa/vitals_interacao.py`: dez blocos síncronos no mesmo
# retorno ao laço de eventos são UMA tarefa para o navegador, e a API reporta 1
# em vez de 10.
_PESADO_JS = """
var blocosRestantes = 10;
function trabalhoComputacional() {
  var soma = 0;
  for (var i = 0; i < 3000000; i++) { soma += Math.sqrt(i) * Math.sin(i); }
  window.__soma = soma;   // impede que a engine descarte o laco como morto
  if (--blocosRestantes > 0) { setTimeout(trabalhoComputacional, 0); }
}
trabalhoComputacional();
"""

# VIOLAÇÃO (gui, GUI-PERF-02): folha de estilo que BLOQUEIA a renderização e pesa
# o suficiente para a banda importar. Em fibra ela chega em ~50ms e não custa
# nada; a 1638 kbps são ~3,4s em que a tela fica em branco — o defeito real de
# quem publica uma folha única, não dividida e não minificada.
#
# Gerada em memória por repetição, e não guardada como arquivo: 700KB de blob no
# repositório seriam opacos no diff, e o que a violação É precisa se ler no
# código. O conteúdo é CSS válido e inerte de propósito — o peso é o defeito, e
# misturar uma segunda violação aqui tornaria ambíguo o que o check acusa.
_REGRA_DE_ENCHIMENTO = (
    "/* peso deliberado: esta folha existe para custar banda, nao para estilizar */\n"
    ".enchimento-%d { margin: 0; padding: 0; border: 0; outline: 0; }\n"
)
PESADO_CSS = "".join(_REGRA_DE_ENCHIMENTO % i for i in range(4200))

PESADO_HTML = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Catalogo — Loja Fixture</title>
<link rel="stylesheet" href="/gui/pesado.css">
</head><body>
<main>
  <h1>Catalogo de produtos</h1>
  <p>Conteudo principal da pagina, que so aparece depois da folha de estilo.</p>
</main>
<script>{_PESADO_JS}</script>
</body></html>
"""

# Caminhos servidos por `servir.py`. Mapa, e não uma cadeia de `elif`, porque o
# teste que prova a ausência destas páginas no hash itera sobre ele — a lista
# de páginas e a lista conferida são a mesma coisa, e não podem divergir.
PAGINAS_GUI: dict[str, tuple[bytes, str]] = {
    "/gui/estados": (ESTADOS_HTML.encode("utf-8"), "text/html; charset=utf-8"),
    "/gui/resiliente": (RESILIENTE_HTML.encode("utf-8"), "text/html; charset=utf-8"),
    "/gui/api/pedidos": (API_PEDIDOS.encode("utf-8"), "application/json"),
    "/gui/pesado": (PESADO_HTML.encode("utf-8"), "text/html; charset=utf-8"),
    "/gui/pesado.css": (PESADO_CSS.encode("utf-8"), "text/css; charset=utf-8"),
}


# Páginas do contrato VISUAL — e a razão de elas serem SEM TEXTO.
#
# Métrica de fonte varia entre sistema operacional, versão de engine e fontes
# instaladas. Um pixel-diff sobre texto renderizado seria loteria entre o local e
# o CI: verde numa máquina, vermelho na outra, sem nada ter mudado no alvo. Só
# formas sólidas alinhadas ao pixel — sem fonte, sem raio de borda, sem sombra,
# sem gradiente, sem transformação — produzem a mesma matriz em toda parte.
#
# Texto só entraria aqui MASCARADO por região declarada no perfil, e não há texto
# nenhum de propósito: a máscara é para alvo real, não para o contrato.
def _pagina_visual(deslocamento: int, titulo: str) -> str:
    """As duas páginas visuais, do mesmo molde, diferindo por UM número.

    É o que torna a divergência legível: o diff acusa exatamente os blocos onde
    `.b` está, e o código diz por quê numa linha.
    """
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titulo}</title>
<style>
  html, body {{ margin: 0; padding: 0; background: #ffffff; }}
  div {{ position: absolute; }}
  .a {{ left: 40px;  top: 40px;  width: 160px; height: 120px; background: #1155aa; }}
  .b {{ left: {240 + deslocamento}px; top: 40px; width: 120px; height: 120px;
        background: #aa2211; }}
  .c {{ left: 40px;  top: 220px; width: 320px; height: 80px;  background: #227733; }}
</style>
</head><body><div class="a"></div><div class="b"></div><div class="c"></div></body></html>
"""


VISUAL_HTML = _pagina_visual(0, "Contrato visual — estavel")

# VIOLAÇÃO deliberada (gui, GUI-VIS-01): esta página nasceu deslocada em relação
# à referência versionada dela, que é uma cópia da referência da página estável.
# Não é bug do alvo — é o único jeito honesto de exercer a direção `failed` do
# diff visual contra o alvo fabricado. O manifesto da referência declara isso, e
# `make referencia-visual` NÃO a regrava (senão o defeito se autocorrigiria e o
# check nunca mais reprovaria).
VISUAL_MUDADO_HTML = _pagina_visual(48, "Contrato visual — deslocado")

PAGINAS_GUI["/gui/visual"] = (VISUAL_HTML.encode("utf-8"), "text/html; charset=utf-8")
PAGINAS_GUI["/gui/visual-mudado"] = (VISUAL_MUDADO_HTML.encode("utf-8"),
                                     "text/html; charset=utf-8")
