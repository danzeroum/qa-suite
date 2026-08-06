"""Exploração assistida por LLM local sobre o material já coletado (OS-55).

**Sob demanda, nunca no CI.** A saída não é determinística e o veredito é
triagem humana; pôr isto num gate transformaria uma sugestão em barreira.

Liga as pontas que os módulos não podem ligar sozinhos: `webqa/exploracao.py`
não importa navegação por invariante estrutural, então é aqui — no script — que
o grafo já coletado encontra o modelo.

Fail-closed em duas portas, e nenhuma delas degrada:

* **sem `WEBQA_LLM_ENABLED=1`** → parada instruída nomeando a variável;
* **com o gate e sem runtime local** → erro nomeando o que falta.

Nunca há fallback para API externa. `webqa/llm.py` recusa endpoint público por
invariante, e um script que contornasse isso desfaria a invariante do lado de
fora — a camada de IA desta suíte é local, e local é o que ela é, não o que ela
prefere.

**A sanitização é da borda, não do destino.** O insumo passa por `sanitize_text`
antes de virar prompt mesmo com modelo local: quem decide o que sai do processo é
a borda de escrita, e "é local, então tudo bem" é exatamente o raciocínio que faz
uma borda deixar de existir.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from webqa.exploracao import (  # noqa: E402
    carregar_personas,
    montar_prompt,
    triar,
)
from webqa.gates import LLM_ENV, llm_enabled  # noqa: E402
from webqa.llm import endpoint_configurado, modelo_configurado, runtime_disponivel  # noqa: E402
from webqa.sanitize import sanitize_text  # noqa: E402


def sanitizar_snapshot(snapshot: dict) -> dict:
    """TUDO do insumo atravessa a borda ANTES do prompt — inclusive as URLs.

    **A primeira versão preservava a URL crua**, com o argumento de que ela é a
    chave que liga a fricção de volta ao grafo e mascará-la faria toda saída
    virar alucinação. O argumento estava errado, e o alvo fabricado mostrou por
    quê: ele serve `/newsletter?email=joao@exemplo.com`. **PII mora em URL
    também** — em query string é onde ela mais mora.

    E o medo era infundado: a validação compara a página citada contra
    `paginas_do(snapshot)`, e o snapshot que vai ao prompt é o MESMO que vai ao
    validador. Sanitizar os dois lados juntos não quebra chave nenhuma; o que
    quebraria seria sanitizar um só.
    """
    return {
        "paginas": [{"url": sanitize_text(p["url"]),
                     "titulo": sanitize_text(p.get("titulo") or ""),
                     "links": [{"para": sanitize_text(ligacao["para"]),
                                "rotulo": sanitize_text(ligacao.get("rotulo") or "")}
                               for ligacao in p.get("links") or []]}
                    for p in snapshot.get("paginas") or []],
        "desfechos": [{**d, "detalhe": sanitize_text(d.get("detalhe") or "")}
                      for d in snapshot.get("desfechos") or []],
    }


def _parar(mensagem: str) -> int:
    print(mensagem, file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("snapshot", type=Path,
                        help="JSON do insumo já coletado (grafo + textos + desfechos)")
    parser.add_argument("--persona", default="literal")
    parser.add_argument("--destino", type=Path, default=RAIZ / "report" / "exploratorio")
    parser.add_argument("--saida-bruta", type=Path, default=None,
                        help="usa esta saída de LLM em vez de chamar o modelo (triagem seca)")
    args = parser.parse_args(argv)

    if not llm_enabled():
        return _parar(
            f"exploração NÃO executada: {LLM_ENV} não está em '1'. Esta etapa é "
            f"opt-in porque a saída é sugestão para triagem humana, não veredito — "
            f"exporte {LLM_ENV}=1 para habilitá-la.")

    snapshot = sanitizar_snapshot(json.loads(args.snapshot.read_text(encoding="utf-8")))
    personas = carregar_personas()
    if args.persona not in personas:
        return _parar(f"persona desconhecida: {args.persona!r}. "
                      f"Válidas: {', '.join(sorted(personas))}.")
    prompt = montar_prompt(snapshot, args.persona, personas[args.persona])

    if args.saida_bruta is not None:
        brutas = json.loads(args.saida_bruta.read_text(encoding="utf-8"))
    else:
        endpoint = endpoint_configurado()
        if not runtime_disponivel(endpoint):
            return _parar(
                f"runtime local não respondeu em {endpoint}. Suba o modelo "
                f"({modelo_configurado()}) e repita. NÃO há caída para API externa: a "
                f"camada de IA desta suíte é local por invariante, não por preferência.")
        brutas = _consultar(endpoint, prompt)

    aceitas, rejeitadas = triar(brutas, snapshot, args.persona)
    args.destino.mkdir(parents=True, exist_ok=True)
    alvo = args.destino / f"friccoes-{args.persona}.json"
    alvo.write_text(json.dumps({
        "persona": args.persona,
        "aviso": ("FRICÇÕES são hipóteses para triagem humana — não são achados. "
                  "Elas ficam fora do SARIF e fora do contrato do alvo fixture."),
        "friccoes": [{"pagina": f.pagina, "tipo": f.tipo, "descricao": f.descricao,
                      "evidencia": f.evidencia} for f in aceitas],
        "rejeitadas": [{"classe": r.classe, "motivo": r.motivo, "bruta": r.bruta}
                       for r in rejeitadas],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"exploração ({args.persona}): {len(aceitas)} fricção(ões) para triagem · "
          f"{len(rejeitadas)} rejeitada(s) pelo validador · {alvo.name}")
    for r in rejeitadas:
        print(f"  rejeitada [{r.classe}]: {r.motivo[:110]}")
    return 0


def _consultar(endpoint: str, prompt: str) -> list:
    """POST ao runtime local. Saída ilegível vira lista vazia, nunca exceção:
    instrumentação opcional não pode derrubar a execução de quem a chamou."""
    import httpx

    from webqa.llm import MODELO_PADRAO, TEMPERATURA
    corpo = {"model": modelo_configurado() or MODELO_PADRAO,
             "temperature": TEMPERATURA,
             "messages": [{"role": "user", "content": prompt}]}
    try:
        resposta = httpx.post(endpoint, json=corpo, timeout=180.0)
        texto = resposta.json()["choices"][0]["message"]["content"]
        inicio, fim = texto.find("["), texto.rfind("]")
        return json.loads(texto[inicio:fim + 1]) if inicio >= 0 < fim else []
    except Exception as exc:
        print(f"  saída do modelo ilegível ({str(exc).splitlines()[0][:100]}) — "
              f"zero fricções, e isso é resultado, não erro.", file=sys.stderr)
        return []


if __name__ == "__main__":
    raise SystemExit(main())
