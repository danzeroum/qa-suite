"""Anexo assistido por IA — lê o `summary.json` e grava `report/sumario.md`.

Ver `docs/LLM.md`. Roda **DEPOIS** do pytest, em processo separado, e nunca
dentro de `pytest_sessionfinish`.

Por que processo separado, e não um hook: o hook que escreve o laudo já é o
lugar mais caro do projeto para se colocar um `try/except` amplo. Foi
exatamente ali que erros de setup sumiram do `summary.json` e uma noite com o
Chromium morto virou "noite limpa" no ledger — a métrica de confiança inflando
quando a infraestrutura quebrava. Uma etapa opcional e probabilística não pode
dividir o corpo de execução com a etapa que produz a fonte da verdade. Se este
script inteiro explodir, o laudo determinístico continua íntegro, porque ele já
foi gravado e fechado antes de este processo existir.

Contrato de saída, nesta ordem de precedência:

* gate fechado                  -> nada gerado, exit 0, silêncio;
* runtime local ausente         -> uma linha de log, exit 0 (em ~2s, não em 2min);
* nenhum achado a resumir       -> nada gerado, exit 0 (laudo 100% verde é resultado, não erro);
* modelo respondeu              -> `report/sumario.md`, rotulado, passado pelas duas guardas.

Em nenhum caminho este script escreve, move ou lê-para-reescrever o
`summary.json` ou o `summary.html`.
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:                      # execução direta: python scripts/sumario.py
    sys.path.insert(0, str(RAIZ))

from webqa.gates import LLM_ENV, llm_enabled  # noqa: E402
from webqa.llm import (  # noqa: E402
    ResumidorLLM,
    ResumidorLocal,
    achados_para_prompt,
    aplicar_guarda_de_linguagem,
    aplicar_guarda_de_omissao,
    endpoint_configurado,
    modelo_configurado,
    runtime_disponivel,
)
from webqa.report import report_dir  # noqa: E402

NOME_DO_ARQUIVO = "sumario.md"

# O rótulo é obrigatório e vem ANTES do texto (docs/LLM.md §4): quem abre o
# arquivo precisa saber o que está lendo antes de ler. Vai no arquivo e NUNCA no
# prompt — modelo não precisa saber a hora, e cada campo a mais no prompt é
# contexto gasto sem informação de achado.
CABECALHO = """# Sumário assistido por IA — NÃO é veredito

> Gerado por modelo de linguagem local a partir dos achados já produzidos e
> sanitizados pela suíte. **A fonte da verdade é `summary.json`.** Este texto
> apresenta; quem julga é o código. Nenhum achado aqui foi decidido por IA, e
> ausência de menção não é ausência de achado.
>
> modelo: `{modelo}` · endpoint: `{endpoint}` · gerado em: {momento}

---

"""


def carregar_resultados(diretorio: Path) -> list[dict]:
    """`results` do summary.json. Ausência do arquivo devolve lista vazia.

    Sem summary.json não há o que resumir — e isso é estado normal (ninguém
    rodou a suíte ainda), não erro que mereça código de saída.
    """
    caminho = diretorio / "summary.json"
    if not caminho.exists():
        return []
    try:
        return list(json.loads(caminho.read_text(encoding="utf-8")).get("results", []))
    except (ValueError, OSError):
        return []


def montar_documento(texto: str, modelo: str, endpoint: str, momento: str) -> str:
    return CABECALHO.format(modelo=modelo, endpoint=endpoint, momento=momento) + texto + "\n"


def gerar(resultados: list[dict], resumidor: ResumidorLLM) -> str:
    """Texto do sumário, já passado pelas duas guardas determinísticas.

    Recebe o `ResumidorLLM` pronto — é o que permite testar o montador inteiro
    com um fake, sem rede e sem runtime local (inversão de dependência).
    """
    texto = resumidor.resumir(resultados)
    if not texto.strip():
        return ""
    return aplicar_guarda_de_omissao(aplicar_guarda_de_linguagem(texto), resultados)


def main(argv: list[str] | None = None) -> int:
    if not llm_enabled():
        return 0        # silêncio: a etapa está desligada, não falhou

    diretorio = report_dir()
    resultados = carregar_resultados(diretorio)
    if not achados_para_prompt(resultados):
        # Laudo 100% verde (ou execução inexistente) é RESULTADO, não erro. Um
        # sumário de "nenhum achado" convidaria o modelo justamente ao que a
        # suíte proíbe: afirmar conformidade a partir de ausência.
        print("sumario: nenhum achado failed/xfail/error — nada a resumir.")
        return 0

    endpoint, modelo = endpoint_configurado(), modelo_configurado()
    try:
        resumidor: ResumidorLLM = ResumidorLocal(endpoint=endpoint, modelo=modelo)
    except ValueError as erro:
        # Endpoint recusado pelo veto: é configuração errada do operador, e
        # dizer qual é o problema vale mais que um exit silencioso.
        print(f"sumario: endpoint recusado — {erro}")
        return 0

    # `endpoint` local, e não `resumidor.endpoint`: o `Protocol` só promete
    # `resumir`. Alcançar atributo da implementação concreta faria este script
    # depender de `ResumidorLocal` em vez da abstração — e um resumidor
    # alternativo (ou um fake em teste) deixaria de servir.
    if not runtime_disponivel(endpoint):
        print(f"sumario: runtime local não respondeu em {endpoint} — "
              f"etapa pulada, laudo determinístico intacto (desligue com {LLM_ENV}=0).")
        return 0

    try:
        texto = gerar(resultados, resumidor)
    except Exception as erro:
        # Amplo DE PROPÓSITO, e seguro justamente porque estamos fora do hook do
        # laudo: aqui não há nada a engolir além desta etapa opcional. O erro é
        # impresso, não escondido — a lição do bug histórico é a separação de
        # processo, não a proibição de capturar.
        print(f"sumario: modelo falhou ({type(erro).__name__}: {erro}) — etapa pulada.")
        return 0

    if not texto:
        print("sumario: modelo devolveu texto vazio — nada gravado.")
        return 0

    momento = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    destino = diretorio / NOME_DO_ARQUIVO
    destino.write_text(montar_documento(texto, modelo, endpoint, momento), encoding="utf-8")
    print(f"sumario: {destino}")
    return 0


if __name__ == "__main__":                          # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
