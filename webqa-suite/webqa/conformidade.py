"""Evidência de conformidade da dimensão `gui` (OS-53).

Três saídas, uma fonte: o `summary.json` que a execução já produziu e o mapa
critério→teste de `data/gui-perfis.yaml`. **Nenhum número é digitado** — tudo é
derivado do laudo ou do mapa, porque número de conformidade escrito à mão é a
forma mais barata de um relatório mentir.

**O que NÃO vira achado, e por quê.** Só `failed` vira resultado SARIF.

* `xfailed` é veredito ADIADO por ambiente (a navalha da casa: tempo, rede e
  binário instalado só reprovam sob `WEBQA_ORIGEM=vps`). Exportá-lo como achado
  diria que o alvo tem um defeito que a suíte decidiu não afirmar;
* `skipped` é NÃO AVALIADO — capacidade ausente, alvo sem o recurso, engine sem a
  API. Vira achado seria transformar ausência de medida em defeito medido, que é
  a mentira simétrica da que a casa mais persegue ("ausência nunca vira zero");
* `passed` não é achado por definição, e `error` é o teste não tendo acontecido.

A regra vale para o VPAT também: um critério cujo teste pulou não é "conforme".

**Padrão R10, e ele mora nas três saídas.** Passar não certifica. O que estes
artefatos são é *evidência que contribui* para uma declaração assinada por uma
pessoa — nunca a declaração. A frase vai na capa e no rodapé porque um documento
que se deixa ler como selo vira selo.

`webqa/sarif.py` continua dono do schema e da versão; este módulo os IMPORTA.
Duas constantes iguais em dois módulos divergiriam no primeiro upgrade.

Somente stdlib + PyYAML (já dependência).
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import yaml

from webqa.sarif import SCHEMA_SARIF, VERSAO_SARIF

RAIZ = Path(__file__).resolve().parent.parent
PERFIS_PADRAO = RAIZ / "data" / "gui-perfis.yaml"

FERRAMENTA_GUI = "WebQA-GUI"
DIMENSAO = "gui"
ACHADO = "failed"

# O laudo grava o nodeid no campo `test`, nao `nodeid` — conferido no esquema
# real de `report/summary.json`, que e como `tests/test_alvo_fixture.py` tambem o
# le. Constante e nao literal solto porque a primeira versao INVENTOU o nome do
# campo: o exportador rodou, escreveu SARIF valido, e casou zero criterios —
# dezoito achados saindo como "sem criterio WCAG" num alvo cujos dez criterios
# estao mapeados. Verde de ferramenta, laudo vazio de sentido.
CAMPO_NODEID = "test"

NOTA_EPISTEMICA = (
    "Este documento é EVIDÊNCIA QUE CONTRIBUI para uma declaração de "
    "conformidade assinada por uma pessoa — não é a declaração, e não é "
    "certificado. Uma falha aqui PROVA um defeito de interface; passar NÃO "
    "certifica acessibilidade: o que a suíte mede é o que o navegador mostra, "
    "não se a pessoa entendeu. Os critérios marcados EXIGE HUMANO aparecem de "
    "propósito — omiti-los fingiria completude."
)

COBERTO, EXIGE_HUMANO, NAO_COBERTO = "coberto-por-teste", "exige-humano", "não-coberto"


def carregar_mapa(caminho: str | Path | None = None) -> dict:
    """Lê o bloco `conformidade:` de `data/gui-perfis.yaml`."""
    dados = yaml.safe_load(Path(caminho or PERFIS_PADRAO).read_text(encoding="utf-8")) or {}
    mapa = dados.get("conformidade") or {}
    for chave in ("criterios", "exige_humano", "sem_criterio"):
        mapa.setdefault(chave, {})
    return mapa


def nodeids_mapeados(mapa: Mapping) -> set[str]:
    fora: set[str] = set()
    for dados in (mapa.get("criterios") or {}).values():
        fora.update((dados or {}).get("nodeids") or ())
    return fora


def _problemas_de_cobertura(mapeados, declarados, coletados) -> list[str]:
    """Os dois sentidos da guarda, e nenhum cobre o outro.

    Sem o primeiro, o mapa cita teste que já não existe e o VPAT promete
    cobertura sem objeto. Sem o segundo, check novo nasce invisível ao documento
    de conformidade — e um VPAT que ignora um check envelhece calado, que é o
    defeito que as âncoras da OS-57 tinham.
    """
    problemas = []
    for nodeid in sorted(mapeados | declarados):
        if nodeid not in coletados:
            problemas.append(
                f"data/gui-perfis.yaml cita {nodeid}, que a coleta de `gui` não produz. "
                f"Ou o teste foi renomeado e o mapa ficou para trás, ou ele sumiu — nos "
                f"dois casos o VPAT promete cobertura sem objeto.")
    for nodeid in sorted(coletados - mapeados - declarados):
        problemas.append(
            f"{nodeid} é um check de `gui` que o mapa não conhece. Ligue-o a um critério "
            f"em `criterios:` ou declare em `sem_criterio:` por que ele não é WCAG — "
            f"check invisível ao documento de conformidade o faz envelhecer calado.")
    return problemas


def _problemas_de_declaracao(mapa: Mapping) -> list[str]:
    """Declaração sem motivo não vale como declaração — a mesma regra da
    allowlist de `afere_simbolos.py` e dos pendentes de `afere_ancoras.py`."""
    problemas = []
    for criterio, dados in sorted((mapa.get("criterios") or {}).items()):
        if not (dados or {}).get("nome"):
            problemas.append(f"critério {criterio} sem `nome` no mapa.")
    for criterio, dados in sorted((mapa.get("exige_humano") or {}).items()):
        if not str((dados or {}).get("motivo") or "").strip():
            problemas.append(
                f"critério {criterio} está em `exige_humano` sem motivo escrito — "
                f"limitação que ninguém consegue revisar depois não vale como limitação.")
    for nodeid, motivo in sorted((mapa.get("sem_criterio") or {}).items()):
        if not str(motivo or "").strip():
            problemas.append(f"{nodeid} está em `sem_criterio` sem motivo escrito.")
    return problemas


def problemas_do_mapa(mapa: Mapping, coletados) -> list[str]:
    """Guarda bidirecional do mapa, mais as declarações sem motivo."""
    return (_problemas_de_cobertura(nodeids_mapeados(mapa),
                                    set(mapa.get("sem_criterio") or {}),
                                    set(coletados))
            + _problemas_de_declaracao(mapa))


def placar_do_mapa(mapa: Mapping, coletados) -> dict:
    return {"criterios": len(mapa.get("criterios") or {}),
            "exige_humano": len(mapa.get("exige_humano") or {}),
            "sem_criterio": len(mapa.get("sem_criterio") or {}),
            "coletados": len(set(coletados))}


def resumo(placar: Mapping) -> str:
    return (f"conformidade gui: {placar['criterios']} critério(s) com teste, "
            f"{placar['exige_humano']} exige(m) humano, "
            f"{placar['sem_criterio']} check(s) sem critério declarado; "
            f"{placar['coletados']} check(s) coletados.")


def _criterio_de(nodeid: str, mapa: Mapping) -> tuple[str, str]:
    for criterio, dados in (mapa.get("criterios") or {}).items():
        if nodeid in ((dados or {}).get("nodeids") or ()):
            return criterio, (dados or {}).get("nome") or ""
    return "", ""


def achados_de(laudo: Mapping, mapa: Mapping) -> tuple[dict, ...]:
    """Os `failed` de `gui`, com o critério do mapa quando houver. Puro."""
    fora = []
    for r in (laudo.get("results") or []):
        if r.get("dimension") != DIMENSAO or r.get("outcome") != ACHADO:
            continue
        criterio, nome = _criterio_de(r.get(CAMPO_NODEID) or "", mapa)
        fora.append({"nodeid": r.get(CAMPO_NODEID) or "", "criterio": criterio,
                     "criterio_nome": nome, "detalhe": (r.get("detail") or "").strip()})
    return tuple(fora)


def para_sarif(laudo: Mapping, mapa: Mapping) -> dict:
    """SARIF 2.1.0 dos achados de `gui`. Puro: recebe o laudo já sanitizado.

    A sanitização é HERDADA e não refeita: `webqa/report.py` varre a string
    serializada do `summary.json` (§R8), então tudo que chega aqui já passou pela
    borda de escrita. Refazer a varredura aqui daria duas bordas com regras que
    divergem na primeira mudança.
    """
    regras, vistos = [], {}
    resultados = []
    for a in achados_de(laudo, mapa):
        regra = a["criterio"] and f"WCAG-{a['criterio']}" or "GUI-SEM-CRITERIO"
        if regra not in vistos:
            vistos[regra] = True
            regras.append({
                "id": regra,
                "shortDescription": {"text": a["criterio_nome"] or
                                     "Defeito de interface sem critério WCAG correspondente"},
                "properties": {"criterio_wcag": a["criterio"]} if a["criterio"] else {},
            })
        resultados.append({
            "ruleId": regra,
            "level": "error",
            "message": {"text": f"{a['nodeid']}: {a['detalhe'][:800]}" if a["detalhe"]
                        else a["nodeid"]},
            "locations": [{"physicalLocation": {
                "artifactLocation": {"uri": a["nodeid"].split("::")[0]}}}],
        })
    return {
        "version": VERSAO_SARIF,
        "$schema": SCHEMA_SARIF,
        "runs": [{
            "tool": {"driver": {"name": FERRAMENTA_GUI, "rules": regras,
                                "informationUri": "https://www.w3.org/TR/WCAG22/"}},
            "results": resultados,
        }],
    }


def linhas_do_vpat(laudo: Mapping, mapa: Mapping) -> tuple[dict, ...]:
    """Uma linha por critério, nos TRÊS estados, ordenadas por critério.

    O desfecho de cada teste vem do laudo: critério cujo teste PULOU não é
    conforme, é **não avaliado**, e a linha diz isso. Contar skip como conforme
    seria transformar ausência de medida em atestado.
    """
    desfechos = {r.get(CAMPO_NODEID): r.get("outcome")
                 for r in (laudo.get("results") or []) if r.get("dimension") == DIMENSAO}
    linhas = []
    for criterio, dados in (mapa.get("criterios") or {}).items():
        nodeids = tuple((dados or {}).get("nodeids") or ())
        obtidos = [desfechos.get(n) for n in nodeids]
        if any(o == ACHADO for o in obtidos):
            situacao = "NÃO conforme (falha medida)"
        elif obtidos and all(o == "passed" for o in obtidos):
            situacao = "conforme na medida automatizada"
        elif not any(obtidos):
            situacao = "não executado nesta campanha"
        else:
            situacao = "não avaliado (teste pulou ou ficou adiado por ambiente)"
        linhas.append({"criterio": criterio, "nome": (dados or {}).get("nome") or "",
                       "estado": COBERTO, "situacao": situacao, "nodeids": nodeids})
    for criterio, dados in (mapa.get("exige_humano") or {}).items():
        linhas.append({"criterio": criterio, "nome": (dados or {}).get("nome") or "",
                       "estado": EXIGE_HUMANO,
                       "situacao": (dados or {}).get("motivo") or "", "nodeids": ()})
    return tuple(sorted(linhas, key=lambda x: [int(p) for p in x["criterio"].split(".")]))
