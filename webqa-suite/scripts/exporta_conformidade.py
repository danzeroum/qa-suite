"""Gera a evidência de conformidade da dimensão `gui` (OS-53).

Três artefatos em `report/`, de uma leitura só do `summary.json`:

* **SARIF 2.1.0** — os `failed` de `gui`, cada um carregando o critério WCAG que
  o mapa declara. Só `failed`: `xfailed` é veredito adiado por ambiente e
  `skipped` é não-avaliado, e nenhum dos dois é defeito medido;
* **VPAT parcial (HTML)** — uma linha por critério, nos três estados, com os
  `exige-humano` presentes de propósito;
* **PDF executivo** — o mesmo HTML impresso pelo Chromium (`page.pdf()`), zero
  dependência nova.

`report/` nunca é versionado (`.gitignore`), e a sanitização é HERDADA do
`summary.json`, que `webqa/report.py` já varre por valor.

O PDF renderiza um arquivo LOCAL por `file://`: nenhuma requisição externa, nem
para fonte, nem para folha de estilo — a mesma disciplina do `summary.html`.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:          # execução direta: python scripts/exporta_...
    sys.path.insert(0, str(RAIZ))

from webqa.conformidade import (  # noqa: E402
    EXIGE_HUMANO,
    NOTA_EPISTEMICA,
    carregar_mapa,
    linhas_do_vpat,
    para_sarif,
    placar_do_mapa,
    problemas_do_mapa,
    resumo,
)


def _e(texto: str) -> str:
    return html.escape(str(texto or ""))


def vpat_html(laudo: dict, mapa: dict) -> str:
    """O VPAT parcial. Sem CSS externo e sem fonte remota — imprimível offline."""
    linhas = []
    for linha in linhas_do_vpat(laudo, mapa):
        provas = "<br>".join(_e(n) for n in linha["nodeids"]) or "—"
        marca = "EXIGE HUMANO" if linha["estado"] == EXIGE_HUMANO else "coberto por teste"
        linhas.append(
            f"<tr><td>{_e(linha['criterio'])}</td><td>{_e(linha['nome'])}</td>"
            f"<td>{_e(marca)}</td><td>{_e(linha['situacao'])}</td>"
            f"<td class='prova'>{provas}</td></tr>")
    alvo = _e((laudo.get("alvo") or {}).get("url") if isinstance(laudo.get("alvo"), dict)
              else laudo.get("alvo") or "não declarado")
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>Evidência de conformidade — dimensão gui</title>
<style>
 body {{ font: 12pt/1.5 serif; margin: 2.5cm; color: #111; }}
 h1 {{ font-size: 20pt; margin-bottom: .2em; }}
 .nota {{ border: 1pt solid #111; padding: 1em; margin: 1.5em 0; font-size: 10.5pt; }}
 table {{ border-collapse: collapse; width: 100%; font-size: 10pt; }}
 th, td {{ border: .5pt solid #666; padding: .4em .6em; text-align: left;
           vertical-align: top; }}
 th {{ background: #eee; }}
 .prova {{ font-family: monospace; font-size: 8.5pt; }}
 footer {{ margin-top: 2em; font-size: 9.5pt; border-top: .5pt solid #666; padding-top: 1em; }}
</style></head><body>
<h1>Evidência de conformidade — dimensão <code>gui</code></h1>
<p>Alvo observado: <strong>{alvo}</strong> · gerado em {_e(laudo.get('generated_at') or '—')}</p>
<div class="nota"><strong>Leia antes da tabela.</strong> {_e(NOTA_EPISTEMICA)}</div>
<table><thead><tr><th>Critério</th><th>Nome</th><th>Estado</th>
<th>Situação nesta campanha</th><th>Prova</th></tr></thead>
<tbody>{''.join(linhas)}</tbody></table>
<footer>{_e(NOTA_EPISTEMICA)}</footer>
</body></html>
"""


def gerar_pdf(caminho_html: Path, destino: Path) -> str:
    """Imprime o HTML local em PDF pelo Chromium. Devolve o motivo do pulo, ou ''."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "Playwright não instalado — PDF não gerado (SARIF e VPAT saíram)."
    try:
        with sync_playwright() as p:
            navegador = p.chromium.launch()
            pagina = navegador.new_page()
            pagina.goto(caminho_html.resolve().as_uri(), wait_until="load")
            pagina.pdf(path=str(destino), format="A4", print_background=True)
            navegador.close()
    except Exception as exc:                      # chromium ausente ou sem libs
        return (f"Chromium indisponível — PDF não gerado, SARIF e VPAT saíram "
                f"({str(exc).splitlines()[0][:160]}).")
    return ""


def coletados_da_suite(raiz: Path | None = None) -> list[str]:
    """Os nodeids de `gui` pela COLETA REAL do pytest, em subprocesso.

    **Não por AST, e a diferença apareceu na primeira execução.** A leitura por
    AST enxerga `def test_*` e é cega para os testes que o `pytest-bdd` gera: os
    quatro cenários de `test_jornada.py` nascem da feature, não do módulo, e a
    guarda os acusou como "citados no mapa e ausentes da coleta" — quando os
    ausentes eram da minha leitura, não da suíte.

    Subprocesso, e não `pytest.main` embutido: rodar coleta dentro do próprio
    processo do pytest é a receita de importar duas vezes o que já está
    importado. Aqui o script roda fora do pytest, então o custo é só o tempo.
    """
    # `# nosec` no molde de scripts/audita_design.py e scripts/mutar.py: o
    # comando e literal, montado com sys.executable e argumentos fixos — nao ha
    # entrada de usuario nele, e nao ha shell.
    import subprocess  # nosec B404

    raiz = raiz or RAIZ
    saida = subprocess.run(  # nosec B603
        [sys.executable, "-m", "pytest", "-m", "gui", "--collect-only", "-q",
         "--no-header", "-p", "no:cacheprovider"],
        cwd=raiz, capture_output=True, text=True, timeout=300, check=False)
    return [linha.strip() for linha in saida.stdout.splitlines()
            if linha.strip().startswith("checks/gui/") and "::" in linha]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--placar", action="store_true",
                        help="só imprime o placar do mapa (não precisa de laudo)")
    parser.add_argument("laudo", type=Path, nargs="?",
                        default=RAIZ / "report" / "summary.json")
    parser.add_argument("--destino", type=Path, default=RAIZ / "report")
    parser.add_argument("--coletados", type=Path, default=None,
                        help="arquivo com um nodeid por linha; sem ele, a guarda usa o laudo")
    args = parser.parse_args(argv)

    mapa = carregar_mapa()
    if args.placar:
        coletados = coletados_da_suite()
        print(resumo(placar_do_mapa(mapa, coletados)))
        problemas = problemas_do_mapa(mapa, coletados)
        for p in problemas:
            print(f"::error::{p}", file=sys.stderr)
        return 1 if problemas else 0
    if not args.laudo.is_file():
        print(f"laudo não encontrado: {args.laudo} — rode a suíte antes.", file=sys.stderr)
        return 1
    laudo = json.loads(args.laudo.read_text(encoding="utf-8"))

    if args.coletados and args.coletados.is_file():
        coletados = [x.strip() for x in args.coletados.read_text(encoding="utf-8").splitlines()
                     if x.strip()]
    else:
        coletados = [r.get("nodeid") for r in (laudo.get("results") or [])
                     if r.get("dimension") == "gui"]

    print(resumo(placar_do_mapa(mapa, coletados)))
    problemas = problemas_do_mapa(mapa, coletados)
    if problemas:
        for p in problemas:
            print(f"::error::{p}", file=sys.stderr)
        return 1

    args.destino.mkdir(parents=True, exist_ok=True)
    sarif = args.destino / "gui-conformidade.sarif"
    sarif.write_text(json.dumps(para_sarif(laudo, mapa), ensure_ascii=False, indent=2),
                     encoding="utf-8")
    pagina = args.destino / "gui-vpat.html"
    pagina.write_text(vpat_html(laudo, mapa), encoding="utf-8")
    print(f"conformidade: {sarif.name} · {pagina.name}")
    motivo = gerar_pdf(pagina, args.destino / "gui-vpat.pdf")
    print(f"  {motivo}" if motivo else "  gui-vpat.pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
