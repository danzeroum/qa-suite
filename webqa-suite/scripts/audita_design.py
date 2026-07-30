#!/usr/bin/env python3
"""Gate de design: audita o pacote de referência com os critérios do §12.

Dogfooding — a suíte julga o relatório que a própria suíte vai gerar. Se o
contrato visual não passa nos critérios que ele mesmo cobra dos alvos, a
implementação do template não deve começar.

Fronteira de papéis, deliberada: este script **não corrige** os HTML do
designer. Ele produz laudo. Se der BLOQUEADO, quem itera é o design.

Dois níveis:

* **estático** (sempre): critérios verificáveis lendo o arquivo — lang, h1,
  requisição externa, JS obrigatório, @media print, tema escuro, nota
  epistêmica, tamanho, vazamento da capa, tokens do §11.5;
* **dogfooding** (`--suite`): serve os arquivos e roda `pytest -m
  "frontend or ux"` contra cada um, de onde vem o veredito do axe. Sem
  Chromium, o axe é declarado como PULADO — nunca como PASS.

Somente stdlib + BeautifulSoup (já dependência da suíte).
"""
from __future__ import annotations

import argparse
import json
import os
import re

# subprocess com argv FIXO e sem shell: a única entrada variável é o nome de
# arquivo do próprio diretório auditado. Sem interpolação de string, sem shell=True.
import subprocess  # nosec B404
import sys
import tempfile
import threading
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from bs4 import BeautifulSoup

RAIZ = Path(__file__).resolve().parent.parent
REFERENCIA_PADRAO = RAIZ / "docs" / "qa-suite design brief" / "referencia"
LAUDO_PADRAO = RAIZ / "docs" / "design-audit.md"
LIMITE_KB = 300

# Entregáveis de relatório: cobram a nota epistêmica e os quatro estados.
RELATORIOS = ("summary.html", "summary-verde.html", "summary-sem-navegador.html",
              "summary-parcial.html")
# Trecho literal de webqa/report.py::DIMENSION_NOTES — o design apresenta a nota,
# não a reescreve.
NOTA_EPISTEMICA = "não certifica conformidade"
# Padrões que a CAPA do estúdio continha e que NÃO podem ter vazado.
VAZAMENTOS_DA_CAPA = ("x-dc", "<helmet", "support.js")
ESTADOS = ("passed", "failed", "xfail", "skipped")

PASS, FAIL, NA, PULADO = "PASS", "FAIL", "N.A.", "PULADO"

# Reprovações da bateria que NÃO são defeito do design. Ficam no laudo com a
# atribuição explícita: laudo que mistura artefato do arranjo com defeito do
# entregável manda o designer caçar fantasma.
ARTEFATOS_CONHECIDOS = {
    "test_ajuda_no_erro_pagina_404_amigavel":
        "artefato do ARRANJO: o `SimpleHTTPRequestHandler` do auditor não tem página "
        "404 amigável. Um pacote de arquivos estáticos não tem handler de erro — "
        "critério não se aplica ao entregável.",
}


@dataclass(frozen=True)
class Resultado:
    status: str
    evidencia: str = ""


@dataclass
class Documento:
    caminho: Path
    texto: str

    @property
    def nome(self) -> str:
        return self.caminho.name

    @property
    def soup(self) -> BeautifulSoup:
        if not hasattr(self, "_soup"):
            self._soup = BeautifulSoup(self.texto, "lxml")
        return self._soup

    @property
    def kb(self) -> int:
        return len(self.texto.encode("utf-8")) // 1024

    def linha_de(self, agulha: str) -> int:
        """Número da linha da primeira ocorrência — evidência acionável."""
        pos = self.texto.find(agulha)
        return self.texto.count("\n", 0, pos) + 1 if pos >= 0 else 0


# ---------- Critérios estáticos ----------

def criterio_lang(doc: Documento) -> Resultado:
    html = doc.soup.find("html")
    lang = (html.get("lang") if html else "") or ""
    if lang.lower() == "pt-br":
        return Resultado(PASS, 'lang="pt-BR"')
    return Resultado(FAIL, f'<html lang={lang or "AUSENTE"}> (linha {doc.linha_de("<html")})')


def criterio_h1_unico(doc: Documento) -> Resultado:
    h1 = doc.soup.find_all("h1")
    if len(h1) == 1:
        return Resultado(PASS, f'h1 único: "{h1[0].get_text(" ", strip=True)[:40]}"')
    return Resultado(FAIL, f"{len(h1)} elementos h1 (esperado exatamente 1)")


def criterio_headings_sem_salto(doc: Documento) -> Resultado:
    niveis = [int(h.name[1]) for h in doc.soup.find_all(re.compile(r"^h[1-6]$"))]
    for anterior, atual in zip(niveis, niveis[1:], strict=False):
        if atual > anterior + 1:
            return Resultado(FAIL, f"salto h{anterior} → h{atual}")
    return Resultado(PASS, f"{len(niveis)} headings, sem saltos")


def criterio_zero_requisicao_externa(doc: Documento) -> Resultado:
    ofensores = []
    for tag in doc.soup.find_all(True):
        for atributo in ("src", "href", "srcset", "poster", "action"):
            valor = tag.get(atributo) or ""
            if isinstance(valor, list):
                valor = " ".join(valor)
            if re.match(r"(?i)^(https?:)?//", valor.strip()):
                # Link de navegação para documentação não busca recurso; recurso é
                # o que o navegador BAIXA sozinho.
                if tag.name == "a" and atributo == "href":
                    continue
                ofensores.append(f"<{tag.name} {atributo}={valor[:60]}> (linha {doc.linha_de(valor)})")
    for importacao in re.findall(r"@import[^;]+", doc.texto):
        if re.search(r"(?i)https?://|//", importacao):
            ofensores.append(f"@import externo (linha {doc.linha_de(importacao)})")
    if ofensores:
        return Resultado(FAIL, "; ".join(ofensores[:3]))
    return Resultado(PASS, "nenhum recurso externo")


def criterio_funciona_sem_js(doc: Documento) -> Resultado:
    """JS pode existir; não pode ser NECESSÁRIO."""
    externos = [s for s in doc.soup.find_all("script") if s.get("src")]
    if externos:
        return Resultado(FAIL, f'<script src="{externos[0]["src"][:60]}"> — dependência de JS')
    geradores = ("document.write", ".innerHTML", "insertAdjacentHTML", "createElement")
    for script in doc.soup.find_all("script"):
        corpo = script.string or ""
        achados = [g for g in geradores if g in corpo]
        if achados:
            return Resultado(FAIL, f"script gera conteúdo ({', '.join(achados)})")
    # Conteúdo tem de estar no HTML servido, não injetado depois.
    if not doc.soup.find("main") or not doc.soup.find_all("section"):
        return Resultado(FAIL, "sem <main>/<section> no HTML entregue")
    n = len(doc.soup.find_all("script"))
    return Resultado(PASS, "conteúdo íntegro sem JS" + (f"; {n} script(s) progressivo(s)" if n else ""))


def criterio_media_print(doc: Documento) -> Resultado:
    if "@media print" not in doc.texto:
        return Resultado(FAIL, "sem @media print")
    faltando = [r for r in ("@page", "break-inside") if r not in doc.texto]
    if faltando:
        return Resultado(FAIL, f"@media print sem {', '.join(faltando)}")
    return Resultado(PASS, "@media print com @page e break-inside")


def criterio_tema_escuro(doc: Documento) -> Resultado:
    if "prefers-color-scheme" not in doc.texto:
        return Resultado(FAIL, "sem prefers-color-scheme")
    gancho = 'data-tema="escuro"' in doc.texto or "data-tema='escuro'" in doc.texto
    return Resultado(PASS, "prefers-color-scheme" + (" + gancho data-tema" if gancho else ""))


def criterio_nota_epistemica(doc: Documento) -> Resultado:
    if doc.nome not in RELATORIOS:
        return Resultado(NA, "critério é dos relatórios de execução")
    if NOTA_EPISTEMICA.lower() in doc.texto.lower():
        return Resultado(PASS, f'contém "{NOTA_EPISTEMICA}" (linha {doc.linha_de("certifica")})')
    return Resultado(FAIL, f'sem o texto de DIMENSION_NOTES ("{NOTA_EPISTEMICA}")')


def criterio_estados_sem_cor(doc: Documento) -> Resultado:
    """Cada estado presente precisa de marcador não cromático (forma + rótulo)."""
    if doc.nome not in RELATORIOS:
        return Resultado(NA, "critério é dos relatórios de execução")
    presentes = [e for e in ESTADOS if f'"{e}"' in doc.texto or f" {e}" in doc.texto]
    sem_marcador = []
    for estado in presentes:
        # Um elemento da classe do estado precisa conter svg (forma) ou texto.
        elementos = doc.soup.select(f".{estado}")
        if not elementos:
            continue
        if not any(el.find("svg") or el.get_text(strip=True) for el in elementos):
            sem_marcador.append(estado)
    if sem_marcador:
        return Resultado(FAIL, f"estados só por cor: {sem_marcador}")
    legenda = "com legenda" if "Legenda dos estados" in doc.texto else "sem legenda declarada"
    return Resultado(PASS, f"{len(presentes)} estados com forma+rótulo, {legenda}")


def criterio_tamanho(doc: Documento) -> Resultado:
    if doc.kb < LIMITE_KB:
        return Resultado(PASS, f"{doc.kb} KB (orçamento {LIMITE_KB} KB)")
    return Resultado(FAIL, f"{doc.kb} KB excede {LIMITE_KB} KB")


def criterio_sem_vazamento_da_capa(doc: Documento) -> Resultado:
    for padrao in VAZAMENTOS_DA_CAPA:
        if padrao.lower() in doc.texto.lower():
            return Resultado(FAIL, f'"{padrao}" da capa vazou (linha {doc.linha_de(padrao)})')
    return Resultado(PASS, "sem x-dc, helmet ou support.js")


def criterio_tokens_custom_properties(doc: Documento) -> Resultado:
    """§11.5: a especificação precisa nomear os tokens como custom properties."""
    if doc.nome != "componentes.html":
        return Resultado(NA, "critério é da especificação de componentes")
    tokens = sorted(set(re.findall(r"--[a-z][a-z0-9-]*(?=\s*:)", doc.texto)))
    obrigatorios = [f"--cor-{e}" for e in ESTADOS if e != "passed"] + ["--cor-passed", "--acento"]
    ausentes = [t for t in obrigatorios if t not in tokens]
    if ausentes:
        return Resultado(FAIL, f"§11.5: tokens ausentes {ausentes}")
    return Resultado(PASS, f"{len(tokens)} tokens em custom properties")


# nome, função, bloqueante
CRITERIOS = (
    ('lang="pt-BR"', criterio_lang, True),
    ("h1 único", criterio_h1_unico, True),
    ("headings sem saltos", criterio_headings_sem_salto, False),
    ("zero requisição externa", criterio_zero_requisicao_externa, True),
    ("funciona sem JS", criterio_funciona_sem_js, True),
    ("sem vazamento da capa", criterio_sem_vazamento_da_capa, True),
    ("@media print", criterio_media_print, False),
    ("tema escuro", criterio_tema_escuro, False),
    ("nota epistêmica", criterio_nota_epistemica, False),
    ("4 estados sem cor", criterio_estados_sem_cor, False),
    (f"< {LIMITE_KB} KB", criterio_tamanho, False),
    ("tokens §11.5", criterio_tokens_custom_properties, False),
)


def auditar_estatico(doc: Documento) -> dict[str, Resultado]:
    return {nome: funcao(doc) for nome, funcao, _ in CRITERIOS}


# ---------- Dogfooding: a suíte contra o pacote ----------

class _Servidor:
    """Serve o diretório de referência em porta efêmera (padrão do fixture_target)."""

    def __init__(self, diretorio: Path) -> None:
        handler = partial(_SilenciosoHandler, directory=str(diretorio))
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def __enter__(self) -> _Servidor:
        self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"


class _SilenciosoHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        """O log do servidor de auditoria não é objeto de observação."""


def rodar_bateria(base: str, arquivo: str, saida: Path) -> dict[str, str]:
    """Roda `pytest -m "frontend or ux"` contra um arquivo e devolve {teste: outcome}."""
    destino = saida / arquivo.replace(".html", "")
    env = {
        **os.environ,
        "WEBQA_TARGET_URL": f"{base}/{arquivo}",
        "WEBQA_REPORT_DIR": str(destino),
        "NO_PROXY": "*",
        "no_proxy": "*",
    }
    # argv fixo, sem shell — ver nota no import de subprocess.
    subprocess.run(  # nosec B603
        [sys.executable, "-m", "pytest", "-m", "frontend or ux", "-q", "-p", "no:cacheprovider"],
        cwd=RAIZ, env=env, capture_output=True, text=True, timeout=900, check=False,
    )
    summary = destino / "summary.json"
    if not summary.exists():
        return {}
    dados = json.loads(summary.read_text(encoding="utf-8"))
    return {r["test"].split("::")[-1]: r["outcome"] for r in dados.get("results", [])}


def veredito_axe(resultados: dict[str, str]) -> Resultado:
    """Axe sem críticas/sérias — PULADO quando não houve navegador."""
    if not resultados:
        return Resultado(PULADO, "bateria não produziu summary.json")
    criticas = resultados.get("test_sem_violacoes_criticas")
    serias = resultados.get("test_sem_violacoes_serias")
    if criticas is None:
        return Resultado(PULADO, "testes de axe não coletados")
    if criticas == "skipped" or serias == "skipped":
        return Resultado(PULADO, "Chromium/axe indisponível — NÃO conta como PASS")
    if criticas == "failed" or serias == "failed":
        quais = [n for n, v in (("críticas", criticas), ("sérias", serias)) if v == "failed"]
        return Resultado(FAIL, f"axe reportou violações {', '.join(quais)}")
    return Resultado(PASS, "axe sem violações críticas nem sérias")


# ---------- Laudo ----------

def _tabela(nomes: list[str], linhas: dict[str, dict[str, Resultado]]) -> str:
    cabecalho = "| Critério | " + " | ".join(nomes) + " |"
    separador = "|---" * (len(nomes) + 1) + "|"
    corpo = []
    for criterio in list(linhas[nomes[0]]):
        celulas = [linhas[n][criterio].status for n in nomes]
        corpo.append(f"| {criterio} | " + " | ".join(celulas) + " |")
    return "\n".join([cabecalho, separador, *corpo])


def secao_informativa(reprovacoes: dict[str, list[str]]) -> list[str]:
    """Reprovações da bateria fora do §12, cada uma com a quem atribuir."""
    if not reprovacoes:
        return []
    partes = ["## Achados fora do §12 (informativo, não bloqueia)", "",
              "| Teste da bateria | Arquivos | Atribuição |", "|---|---|---|"]
    for teste, arquivos in sorted(reprovacoes.items(), key=lambda kv: -len(kv[1])):
        nota = ARTEFATOS_CONHECIDOS.get(teste, "**a investigar** — não classificado")
        partes.append(f"| `{teste}` | {len(arquivos)}/{len(arquivos)} auditados | {nota} |")
    partes += ["", "Nenhum destes reprova o pacote: os critérios do §12 estão nas "
               "tabelas acima. Um laudo que confunde artefato do arranjo com defeito "
               "do entregável faz o designer perseguir fantasma.", ""]
    return partes


def montar_laudo(linhas: dict[str, dict[str, Resultado]], bloqueios: list[str],
                 axe: dict[str, Resultado], comando: str,
                 reprovacoes: dict[str, list[str]] | None = None) -> str:
    nomes = list(linhas)
    veredito = "BLOQUEADO" if bloqueios else "LIBERADO"
    partes = [
        "# Laudo de auditoria — pacote de design (§12)",
        "",
        f"**Veredito: {veredito}**",
        "",
        "Gerado por `scripts/audita_design.py` (dogfooding: a suíte auditando o "
        "contrato visual do relatório que ela mesma vai gerar). Este laudo **não "
        "corrige** os arquivos do designer — correção é iteração de design.",
        "",
        f"Comando: `{comando}`",
        "",
        "## Estático",
        "",
        _tabela(nomes, linhas),
        "",
        "## Acessibilidade automatizada (axe, via bateria da suíte)",
        "",
        "| Arquivo | Resultado | Evidência |",
        "|---|---|---|",
    ]
    for nome in nomes:
        r = axe.get(nome, Resultado(PULADO, "bateria não executada (rode com --suite)"))
        partes.append(f"| `{nome}` | {r.status} | {r.evidencia} |")

    partes += ["", *secao_informativa(reprovacoes or {})]
    partes += ["## Evidências dos critérios estáticos", ""]
    for nome in nomes:
        partes.append(f"### `{nome}`")
        partes.append("")
        for criterio, r in linhas[nome].items():
            partes.append(f"- **{criterio}** — {r.status}: {r.evidencia}")
        partes.append("")

    if bloqueios:
        partes += ["## Bloqueios", "",
                   "Critérios bloqueantes reprovados — a OS-15 (template) **não deve começar**:", ""]
        partes += [f"- {b}" for b in bloqueios]
    else:
        partes += ["## Bloqueios", "",
                   "Nenhum. Critérios bloqueantes (`lang`, `h1` único, requisição externa, "
                   "JS obrigatório, vazamento da capa, axe crítico) aprovados em todos os "
                   "entregáveis — a OS-15 está liberada para começar."]
    partes.append("")
    return "\n".join(partes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=Path, default=REFERENCIA_PADRAO)
    parser.add_argument("--saida", type=Path, default=LAUDO_PADRAO)
    parser.add_argument("--suite", action="store_true",
                       help="roda a bateria frontend+ux contra cada arquivo (traz o veredito do axe)")
    parser.add_argument("--tmp", type=Path, default=None, help="diretório dos relatórios da bateria")
    args = parser.parse_args(argv)

    arquivos = sorted(args.dir.glob("*.html"))
    if not arquivos:
        print(f"nenhum .html em {args.dir}", file=sys.stderr)
        return 2

    linhas: dict[str, dict[str, Resultado]] = {}
    bloqueios: list[str] = []
    for caminho in arquivos:
        doc = Documento(caminho, caminho.read_text(encoding="utf-8"))
        resultados = auditar_estatico(doc)
        linhas[doc.nome] = resultados
        for nome, _funcao, bloqueante in CRITERIOS:
            if bloqueante and resultados[nome].status == FAIL:
                bloqueios.append(f"`{doc.nome}` — {nome}: {resultados[nome].evidencia}")

    axe: dict[str, Resultado] = {}
    reprovacoes: dict[str, list[str]] = {}
    if args.suite:
        tmp = args.tmp or Path(tempfile.gettempdir()) / "webqa-design-audit"
        tmp.mkdir(parents=True, exist_ok=True)
        with _Servidor(args.dir) as servidor:
            for caminho in arquivos:
                bateria = rodar_bateria(servidor.base, caminho.name, tmp)
                for teste, outcome in bateria.items():
                    if outcome == "failed":
                        reprovacoes.setdefault(teste, []).append(caminho.name)
                resultado = veredito_axe(bateria)
                axe[caminho.name] = resultado
                if resultado.status == FAIL:
                    bloqueios.append(f"`{caminho.name}` — axe: {resultado.evidencia}")
                print(f"  {caminho.name}: axe {resultado.status} — {resultado.evidencia}")

    comando = "python scripts/audita_design.py" + (" --suite" if args.suite else "")
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(montar_laudo(linhas, bloqueios, axe, comando, reprovacoes),
                          encoding="utf-8")

    veredito = "BLOQUEADO" if bloqueios else "LIBERADO"
    print(f"\n{len(arquivos)} arquivos auditados · laudo em {args.saida}")
    print(f"VEREDITO: {veredito}")
    for b in bloqueios:
        print(f"  - {b}")
    return 1 if bloqueios else 0


if __name__ == "__main__":
    raise SystemExit(main())
