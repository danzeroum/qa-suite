"""Motor de sondagem ativa da Fase C (C1) — descoberta read-only, sob governança.

A técnica é a de um atacante: pedir ao servidor recursos que ele não linkou
(`/.git/HEAD`, `/.env`, backups). O que a mantém do lado da AUDITORIA, e não da
intrusão, é estrutural e está tudo aqui:

* **Gated.** A sondagem real exige `require_discovery()` (opt-in read-only C1) e
  `require_escopo(escopo, alvo)` (host na allowlist, origem exata). Sem os dois,
  não há caminho de código que emita uma requisição.
* **Prova de posse (R-C6).** Antes do primeiro probe, `escopo.verificar_posse`
  compara os IPs do alvo com o snapshot do carregamento; divergência (takeover
  de subdomínio) aborta o alvo — sondar um host reapontado atingiria terceiro.
* **Detectar, nunca explorar.** `HEAD`-only; a EXISTÊNCIA (2xx) já é o achado.
  Nunca lê corpo, nunca segue redirect (`follow_redirects=False`), nunca baixa
  o recurso.
* **Contido.** Lista curada com teto (`MAX_CAMINHOS`), piso de rate-limit
  não-configurável entre requisições, kill-switch checado A CADA iteração do
  laço, e `--dry-run` por padrão (planeja, não toca a rede).
* **Auditável.** Cada requisição vira uma linha de `AuditLog` (append-only,
  mascarada, sem query-string). Achados nascem `Finding(fase="C")` com
  `remediacao` obrigatória — logo já mascarados e sem markup.
* **Honesto sobre run parcial.** Conta executado × esperado: um run que parou no
  meio é `inconclusivo`, nunca "zero achados = tudo limpo".

Rodar isto NÃO é autorizado por abrir a trava: exige o `escopo-autorizado.yaml`
do dono do alvo + a prova de posse. Este módulo é a capacidade; a autorização é
de quem opera.
"""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
import yaml

from webqa.audit import AuditLog
from webqa.dominio import Finding
from webqa.gates import kill_switch_active, require_discovery, require_escopo

CATEGORIAS_VALIDAS = frozenset({"vcs", "configuracao", "backup", "editor", "credencial"})
SEVERIDADES_VALIDAS = frozenset({"alta", "media", "baixa"})

# Teto do carregador: a lista é CURADA, não uma wordlist. Um arquivo inflado é
# erro de configuração e falha ao carregar, não vira varredura de 10k rotas.
MAX_CAMINHOS = 200

# Piso de rate-limit entre requisições ao MESMO alvo. NÃO-configurável para baixo:
# quem chama pode ser mais lento, nunca mais rápido (respeito ao alvo é invariante).
PISO_INTERVALO_S = 1.0

TIMEOUT_S = 10.0
USER_AGENT = "WebQA-FaseC/1.0 (auditoria autorizada; detectar-nao-explorar)"


@dataclass(frozen=True)
class CaminhoSensivel:
    """Uma entrada curada da lista. Nasce validada, como o `Finding`."""

    path: str
    categoria: str
    severidade: str
    content_type_esperado: str
    remediacao: str
    procedencia: str = ""

    def __post_init__(self) -> None:
        if not self.path.startswith("/"):
            raise ValueError(f"path deve começar com '/': {self.path!r}")
        if self.categoria not in CATEGORIAS_VALIDAS:
            raise ValueError(f"categoria inválida em {self.path!r}: {self.categoria!r} "
                             f"(use uma de {sorted(CATEGORIAS_VALIDAS)})")
        if self.severidade not in SEVERIDADES_VALIDAS:
            raise ValueError(f"severidade inválida em {self.path!r}: {self.severidade!r}")
        # Remediação obrigatória: é o mesmo contrato do Finding de Fase C — um
        # achado de sondagem sem o que fazer a respeito não tem valor de auditoria.
        if not self.remediacao.strip():
            raise ValueError(f"remediação obrigatória em {self.path!r}")


def carregar_caminhos(caminho: str | Path) -> list[CaminhoSensivel]:
    """Carrega e VALIDA a lista curada. Falha alto: teto, schema, duplicata.

    Impor `MAX_CAMINHOS` no carregador é a diferença entre uma lista curada e
    uma wordlist: um arquivo grande demais é erro, não licença para varrer.
    """
    p = Path(caminho)
    dados = yaml.safe_load(p.read_text(encoding="utf-8")) or []
    if not isinstance(dados, list):
        raise ValueError(f"lista de caminhos malformada em {p}: esperava uma sequência")
    if len(dados) > MAX_CAMINHOS:
        raise ValueError(
            f"lista excede MAX_CAMINHOS={MAX_CAMINHOS} ({len(dados)} itens): a lista é "
            "curada, não uma wordlist. Reduza ou justifique numa revisão.")

    entradas = [
        CaminhoSensivel(
            path=str(item["path"]),
            categoria=str(item.get("categoria", "")),
            severidade=str(item.get("severidade", "")),
            content_type_esperado=str(item.get("content_type_esperado", "")),
            remediacao=str(item.get("remediacao", "")),
            procedencia=str(item.get("procedencia", "")),
        )
        for item in dados
    ]
    paths = [e.path for e in entradas]
    duplicados = {p_ for p_ in paths if paths.count(p_) > 1}
    if duplicados:
        raise ValueError(f"caminhos duplicados na lista: {sorted(duplicados)}")
    return entradas


@dataclass
class ResultadoSondagem:
    """Veredito de um run contra UM alvo. `inconclusivo` é o sinal que importa."""

    alvo: str
    esperado: int
    executado: int = 0
    findings: list[Finding] = field(default_factory=list)
    abortado_por: str = ""

    @property
    def inconclusivo(self) -> bool:
        """Run parcial NÃO é 'tudo limpo'.

        Abortado (kill-switch, posse) ou com menos probes que o esperado: o
        resultado não cobre a superfície declarada, e tratá-lo como conclusivo
        seria a falha de infra que parece 'zero exposições'.
        """
        return bool(self.abortado_por) or self.executado < self.esperado


def _cliente_padrao() -> httpx.Client:
    """Cliente stateless para sondagem: sem redirect, sem cookies persistidos.

    `follow_redirects=False` é invariante: seguir um 3xx é fazer uma requisição
    que o alvo não ofereceu para aquele caminho — e poderia sair do escopo.
    """
    return httpx.Client(
        timeout=TIMEOUT_S,
        follow_redirects=False,
        http2=True,
        headers={"User-Agent": USER_AGENT},
    )


def _e_soft_404(content_type_esperado: str, content_type_recebido: str) -> bool:
    """Heurística de soft-404 pelo header, sem ler corpo.

    Um servidor que responde 200 para tudo entrega HTML de erro onde se esperava
    `application/octet-stream`/`text/plain`. Só corta quando há divergência CLARA
    (esperado não-HTML, recebido HTML); na dúvida, NÃO corta — falso negativo
    aqui é pior que reportar um achado a mais para revisão humana.
    """
    esperado = (content_type_esperado or "").split(";")[0].strip().lower()
    recebido = (content_type_recebido or "").split(";")[0].strip().lower()
    if not esperado or not recebido:
        return False
    return esperado != "text/html" and recebido == "text/html"


def sondar_caminho(client: httpx.Client, alvo: str, caminho: CaminhoSensivel,
                   log: AuditLog, autorizacao_id: str) -> Finding | None:
    """UM probe: HEAD no caminho, audita, e devolve Finding se existir (2xx).

    Nunca lê corpo e nunca segue redirect (o cliente é `follow_redirects=False`).
    Um 3xx/4xx não é achado; um 2xx que pareça soft-404 pelo Content-Type também
    não. A existência confirmada é o único achado, e ele nasce mascarado.
    """
    url = urljoin(alvo if alvo.endswith("/") else alvo + "/", caminho.path.lstrip("/"))
    resposta = client.head(url)
    log.registrar(url=url, metodo="HEAD", alvo=alvo,
                  autorizacao_id=autorizacao_id, status=resposta.status_code)
    if not (200 <= resposta.status_code < 300):
        return None
    content_type = resposta.headers.get("content-type", "")
    if _e_soft_404(caminho.content_type_esperado, content_type):
        return None
    return Finding(
        tipo=f"exposicao:{caminho.categoria}",
        recurso=url,
        severidade=caminho.severidade,
        evidencia=f"{caminho.path} respondeu {resposta.status_code} "
                  "(existência confirmada por HEAD; corpo não lido)",
        fase="C",
        remediacao=caminho.remediacao,
    )


def sondar(escopo, alvo: str, caminhos: list[CaminhoSensivel], *,
           client: httpx.Client | None = None, log: AuditLog | None = None,
           dry_run: bool = True, intervalo_s: float = PISO_INTERVALO_S,
           dormir=time.sleep) -> ResultadoSondagem:
    """Orquestra a sondagem de um alvo. `dry_run=True` (padrão) NÃO toca a rede.

    O caminho ativo (`dry_run=False`) é gated em três portões antes de qualquer
    requisição: `require_discovery` (opt-in C1), `require_escopo` (host na
    allowlist) e `verificar_posse` (IP não divergiu do carregamento). Depois,
    o laço respeita o piso de rate-limit e checa o kill-switch a cada iteração.
    """
    esperado = len(caminhos)

    # Planejar é seguro e não exige autorização: nenhuma requisição sai.
    if dry_run:
        return ResultadoSondagem(alvo=alvo, esperado=esperado, executado=0,
                                 abortado_por="dry-run")

    # --- portões: sem os três, nenhum probe acontece ---
    require_discovery()
    require_escopo(escopo, alvo)
    host = urlsplit(alvo).hostname or ""
    if not escopo.verificar_posse(host):
        return ResultadoSondagem(alvo=alvo, esperado=esperado, executado=0,
                                 abortado_por="posse-divergente")

    intervalo = max(intervalo_s, PISO_INTERVALO_S)   # piso não-configurável
    fechar_no_fim = client is None
    client = client or _cliente_padrao()
    log = log or AuditLog(run_id="fase-c", escopo_hash=getattr(escopo, "hash_congelado", ""))
    autorizacao_id = (escopo.entrada(alvo).evidencia
                      if escopo.esta_no_escopo(alvo) else "")

    resultado = ResultadoSondagem(alvo=alvo, esperado=esperado)
    try:
        for i, caminho in enumerate(caminhos):
            if kill_switch_active():
                resultado.abortado_por = "kill-switch"
                break
            if i:
                dormir(intervalo)      # piso ENTRE requisições, nunca antes da 1ª
            achado = sondar_caminho(client, alvo, caminho, log, autorizacao_id)
            resultado.executado += 1
            if achado is not None:
                resultado.findings.append(achado)
    finally:
        if fechar_no_fim:
            client.close()
    return resultado


def main(argv: list[str] | None = None) -> int:
    """CLI. `--dry-run` é o padrão; sondar de verdade exige `--executar`.

    Mesmo com `--executar`, os portões de `sondar` decidem: sem
    WEBQA_DISCOVERY_AUTHORIZED=1 e sem o alvo no escopo, nada sai.
    """
    from webqa import escopo as escopo_mod
    from webqa.gates import DISCOVERY_ENV, discovery_authorized

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--alvo", required=True, help="origem exata (https://host)")
    parser.add_argument("--escopo", type=Path, default=Path("escopo-autorizado.yaml"))
    parser.add_argument("--caminhos", type=Path, default=Path("data/caminhos-sensiveis.yaml"))
    parser.add_argument("--executar", action="store_true",
                        help="sonda de verdade; sem esta flag, só planeja (dry-run)")
    args = parser.parse_args(argv)

    caminhos = carregar_caminhos(args.caminhos)
    escopo = escopo_mod.carregar(args.escopo)

    if not args.executar:
        print(f"[dry-run] {len(caminhos)} caminhos planejados contra {args.alvo}:")
        for c in caminhos:
            print(f"  HEAD {args.alvo.rstrip('/')}{c.path}  ({c.categoria}/{c.severidade})")
        print("Nenhuma requisição foi feita. Use --executar para sondar.")
        return 0

    if not discovery_authorized():
        print(f"Sondagem não autorizada: exporte {DISCOVERY_ENV}=1 com autorização "
              "documentada do dono do alvo. Nada foi enviado.")
        return 1

    resultado = sondar(escopo, args.alvo, caminhos, dry_run=False)
    print(f"Sondagem: {resultado.executado}/{resultado.esperado} caminhos, "
          f"{len(resultado.findings)} achado(s)"
          + (f", ABORTADO por {resultado.abortado_por}" if resultado.abortado_por else ""))
    if resultado.inconclusivo:
        print("Resultado INCONCLUSIVO: o run não cobriu a superfície declarada.")
    for f in resultado.findings:
        print(f"  [{f.severidade}] {f.tipo} — {f.recurso}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
