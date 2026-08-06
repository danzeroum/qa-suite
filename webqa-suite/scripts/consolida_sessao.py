"""Transforma uma sessão moderada em métricas e achados comparáveis (OS-54).

Entra um YAML preenchido pela moderadora durante a sessão; sai um JSON sob
`report/sessao/` que `webqa/comparador.py` consegue alinhar com o laudo
automatizado, porque as métricas usam os **mesmos nomes e as mesmas unidades** —
com `fonte=humano` para que nunca sejam confundidas com as sintéticas.

**A transcrição passa por `sanitize_text` ANTES do disco.** A pessoa vai dizer
o próprio nome, o e-mail, às vezes o CPF, enquanto pensa em voz alta — é o que
pensar em voz alta faz. Confiar em quem transcreve para remover isso é confiar
na disciplina onde a casa exige mecanismo: a mesma borda de escrita que protege
o laudo do alvo protege a sessão de quem participou dela.

`report/` nunca é versionado. O expurgo é do dono, no prazo que o consentimento
declarou — este script grava a data-limite junto para que ninguém precise
lembrar de cabeça.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import yaml  # noqa: E402

from webqa.sanitize import sanitize_text  # noqa: E402
from webqa.sessao import (  # noqa: E402
    Achado,
    Sessao,
    Tarefa,
    metricas_de,
    problemas_do_consentimento,
)

TEMPO_ALVO_PADRAO_S = 60.0


def carregar(caminho: Path) -> Sessao:
    """Lê o YAML da sessão. Nome de participante é RECUSADO na porta."""
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    if "nome" in dados:
        raise ValueError(
            "a ficha traz `nome`: a sessão é identificada por INICIAIS e perfil. "
            "Minimização é de desenho — apague o campo e use `iniciais`.")
    return Sessao(
        iniciais=str(dados.get("iniciais") or "").strip(),
        perfil=str(dados.get("perfil") or "").strip(),
        tarefas=tuple(
            Tarefa(cenario=str(t.get("cenario") or ""),
                   concluiu=bool(t.get("concluiu")),
                   segundos=t.get("segundos"),
                   cliques=t.get("cliques"),
                   seq=t.get("seq"))
            for t in (dados.get("tarefas") or [])),
        respostas_sus=tuple(dados["sus"]) if dados.get("sus") else None,
        achados=tuple(
            Achado(descricao=str(a.get("descricao") or ""),
                   severidade=int(a.get("severidade", 0)),
                   cenario=str(a.get("cenario") or ""),
                   criterio=str(a.get("criterio") or ""))
            for a in (dados.get("achados") or [])),
        notas=str(dados.get("notas") or ""),
        consentimento=dados.get("consentimento") or {},
    )


def consolidar(sessao: Sessao, tempo_alvo_s: float = TEMPO_ALVO_PADRAO_S) -> dict:
    """A sessão como JSON. TODO texto livre atravessa a borda de sanitização."""
    prazo = sessao.consentimento.get("retencao_dias")
    inicio = str(sessao.consentimento.get("data") or "")
    expurgar_ate = ""
    if isinstance(prazo, int) and inicio:
        try:
            expurgar_ate = str(date.fromisoformat(inicio) + timedelta(days=prazo))
        except ValueError:
            expurgar_ate = ""
    return {
        "participante": {"iniciais": sanitize_text(sessao.iniciais)[:8],
                         "perfil": sanitize_text(sessao.perfil)},
        "consentimento": {**{k: v for k, v in sessao.consentimento.items()},
                          "expurgar_ate": expurgar_ate},
        "metricas": metricas_de(sessao, tempo_alvo_s),
        "achados": [
            {"descricao": sanitize_text(a.descricao), "severidade": a.severidade,
             "rotulo": a.rotulo, "cenario": a.cenario, "criterio": a.criterio}
            for a in sorted(sessao.achados, key=lambda a: -a.severidade)],
        "notas": sanitize_text(sessao.notas),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ficha", type=Path)
    parser.add_argument("--destino", type=Path, default=RAIZ / "report" / "sessao")
    parser.add_argument("--tempo-alvo-s", type=float, default=TEMPO_ALVO_PADRAO_S)
    args = parser.parse_args(argv)

    sessao = carregar(args.ficha)
    problemas = problemas_do_consentimento(sessao.consentimento)
    if problemas:
        for p in problemas:
            print(f"::error::{p}", file=sys.stderr)
        return 1

    saida = consolidar(sessao, args.tempo_alvo_s)
    args.destino.mkdir(parents=True, exist_ok=True)
    alvo = args.destino / f"sessao-{saida['participante']['iniciais'] or 'anon'}.json"
    alvo.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")

    graves = [a for a in saida["achados"] if a["severidade"] >= 3]
    print(f"sessão consolidada: {alvo.name} · {len(saida['metricas'])} métrica(s) "
          f"(fonte=humano) · {len(saida['achados'])} achado(s), {len(graves)} grave(s) "
          f"· expurgar até {saida['consentimento'].get('expurgar_ate') or '(não declarado)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
