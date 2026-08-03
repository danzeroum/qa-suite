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
import ipaddress
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

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

# Timeout granular: connect baixo (host inacessível não come o orçamento) e read
# maior (host lento, mas dentro do orçamento, ainda responde). Escalar único
# forçava escolher entre abortar cedo demais ou cortar probe legítimo (G6).
TIMEOUT_CONNECT_S = 5.0
TIMEOUT_READ_S = 10.0
USER_AGENT = "WebQA-FaseC/1.0 (auditoria autorizada; detectar-nao-explorar)"

# Circuit breaker: N recuos/falhas de rede CONSECUTIVOS abortam o alvo. Um alvo
# que responde 429 a cada probe faria o run dormir minutos e terminar inconclusivo
# do mesmo jeito — falhar rápido é mais honesto e respeita o alvo (G1). Uma
# resposta válida no meio zera a contagem.
MAX_FALHAS_CONSECUTIVAS = 5


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
    run_id: str = ""
    falhas_rede: int = 0
    recuos: int = 0

    @property
    def inconclusivo(self) -> bool:
        """Run parcial NÃO é 'tudo limpo'.

        Abortado (kill-switch, posse), falha de rede, recuo do servidor (429/503),
        ou com menos probes que o esperado: o resultado não cobre a superfície
        declarada, e tratá-lo como conclusivo seria a falha de infra que parece
        'zero exposições'.
        """
        return (bool(self.abortado_por) or self.falhas_rede > 0 or self.recuos > 0
                or self.executado < self.esperado)


def _cliente_padrao() -> httpx.Client:
    """Cliente stateless para sondagem: sem redirect, sem cookies persistidos.

    `follow_redirects=False` é invariante: seguir um 3xx é fazer uma requisição
    que o alvo não ofereceu para aquele caminho — e poderia sair do escopo.
    """
    return httpx.Client(
        timeout=httpx.Timeout(connect=TIMEOUT_CONNECT_S, read=TIMEOUT_READ_S,
                              write=TIMEOUT_CONNECT_S, pool=TIMEOUT_CONNECT_S),
        follow_redirects=False,
        http2=True,
        headers={"User-Agent": USER_AGENT},
    )


def _e_soft_404(content_type_esperado: str, content_type_recebido: str) -> bool:
    """Heurística de soft-404 pelo header, sem ler corpo.

    Um servidor que responde 200 para tudo entrega HTML de erro onde se esperava
    `application/octet-stream`/`text/plain`. Corta quando o recebido é HTML e o
    esperado não é — INCLUSIVE quando não há tipo esperado declarado: sem
    contrato, HTML recebido é suspeito de catch-all, e desconfiar é o lado seguro
    (um catch-all vira falso positivo em todo caminho). Sem Content-Type na
    resposta, não há sinal e não se corta.
    """
    esperado = (content_type_esperado or "").split(";")[0].strip().lower()
    recebido = (content_type_recebido or "").split(";")[0].strip().lower()
    if not recebido:
        return False
    if not esperado:
        return recebido == "text/html"
    return esperado != "text/html" and recebido == "text/html"


class _FalhaDeRede:
    """Sinal interno: o probe falhou por rede — não é achado nem 'não existe'."""


_FALHA_DE_REDE = _FalhaDeRede()


class _PedeRecuo:
    """Sinal interno: o servidor pediu recuo (429/503) — não conclui o caminho."""


_PEDE_RECUO = _PedeRecuo()


class _Soft404:
    """Sinal interno: 2xx, mas provável soft-404 — descartado, e o descarte é
    auditado pelo chamador (a avaliação é pura; o log é efeito, fica fora dela)."""


_SOFT_404 = _Soft404()

# Status em que o servidor pede para desacelerar: o laço faz backoff e NÃO conta
# o probe como concluído (o caminho fica inconclusivo, nunca 'limpo').
STATUS_DE_RECUO = frozenset({429, 503})
BACKOFF_FATOR = 4
TETO_BACKOFF_S = 30.0


def _validar_alvo(alvo: str) -> None:
    """Rejeita alvo malformado ANTES dos portões — fail-fast e claro.

    O alvo é uma ORIGEM (`esquema://host[:porta]`), não uma URL com path: sondar
    `https://x/app` levaria os caminhos para baixo de `/app`, não à raiz do host,
    e uma query/fragment no alvo não tem sentido para descoberta de recurso.
    """
    partes = urlsplit(alvo)
    if partes.scheme not in ("http", "https"):
        raise ValueError(f"alvo deve ser http(s)://: {alvo!r}")
    if not partes.hostname:
        raise ValueError(f"alvo sem hostname: {alvo!r}")
    if partes.path not in ("", "/") or partes.query or partes.fragment:
        raise ValueError(f"alvo deve ser origem sem path/query/fragment: {alvo!r}")


def _escolher_ip(ips: frozenset[str]) -> str:
    """Escolhe UM IP pinado de forma determinística, preferindo IPv4.

    A escolha é por FAMÍLIA (`ipaddress.version`), NUNCA por ordem de string:
    com dual-stack, `sorted()` sobre strings pode eleger o IPv6
    ('2001:...' < '93...') e quebrar a URL pinada. IPv4 primeiro; dentro da
    família, a ordem canônica do endereço — determinística, não lexicográfica.
    """
    enderecos = [ipaddress.ip_address(x) for x in ips]
    v4 = sorted(a for a in enderecos if a.version == 4)
    v6 = sorted(a for a in enderecos if a.version == 6)
    return str((v4 or v6)[0])


def _url_pinada(alvo: str, ip: str, path: str) -> tuple[str, str, str]:
    """(url_lógica, url_pinada, host). A lógica usa o hostname (para laudo e
    auditoria); a pinada conecta no IP provado, sem re-resolver o DNS.

    IPv6 vai entre colchetes na URL pinada (`https://[2001:db8::1]:443/…`) —
    sem eles o `:` do endereço se confunde com o separador de porta e a URL fica
    malformada (era falha silenciosa antes do G2)."""
    partes = urlsplit(alvo)
    host = partes.hostname or ""
    porta = partes.port or (443 if partes.scheme == "https" else 80)
    caminho_norm = path if path.startswith("/") else "/" + path
    url_logica = f"{partes.scheme}://{partes.netloc}{caminho_norm}"
    ip_para_url = f"[{ip}]" if ipaddress.ip_address(ip).version == 6 else ip
    url_pinada = f"{partes.scheme}://{ip_para_url}:{porta}{caminho_norm}"
    return url_logica, url_pinada, host


def calcular_espera_backoff(recuos_seguidos: int, intervalo: float) -> float:
    """Espera ENTRE requisições: o piso, ampliado por backoff exponencial após
    recuo (429/503), com teto. `intervalo` já vem pisado (>= PISO_INTERVALO_S),
    então o resultado nunca fica abaixo do piso — invariante isolado num só lugar
    (higiene), sem mudar o cálculo do laço."""
    return min(intervalo * (BACKOFF_FATOR ** recuos_seguidos), TETO_BACKOFF_S)


def avaliar_resposta_em_finding(status: int, content_type: str,
                                caminho: CaminhoSensivel, url_logica: str, *,
                                content_length: str | None = None,
                                baseline_catch_all: tuple | None = None):
    """PURA: classifica a resposta FINAL do probe, sem I/O nem log.

    `_PEDE_RECUO` (429/503) · `None` (não-2xx: ausência) · `_SOFT_404` (2xx mas
    provável soft-404 — o chamador audita o descarte) · `Finding` (2xx legítimo).
    Isolar aqui a decisão a torna testável sem mockar httpx nem AuditLog.

    `baseline_catch_all` é a assinatura `(content_type, content_length)` de um
    caminho-fantasma inexistente que respondeu 2xx: um alvo catch-all responde
    igual a tudo, então um probe com a MESMA assinatura é ruído, não achado —
    descartado como soft-404. Content-length diferente do fantasma continua sendo
    achado (o baseline não engole verdadeiro-positivo)."""
    if status in STATUS_DE_RECUO:
        return _PEDE_RECUO
    if not (200 <= status < 300):
        return None
    if _e_soft_404(caminho.content_type_esperado, content_type):
        return _SOFT_404
    if baseline_catch_all is not None and (content_type, content_length) == baseline_catch_all:
        return _SOFT_404
    return Finding(
        tipo=f"exposicao:{caminho.categoria}",
        recurso=url_logica,
        severidade=caminho.severidade,
        evidencia=f"{caminho.path} respondeu {status} "
                  "(existência confirmada; corpo não lido)",
        fase="C",
        remediacao=caminho.remediacao,
        procedencia=caminho.procedencia,
    )


def executar_fallback_get(client: httpx.Client, url_logica: str, url_pinada: str,
                          cabecalhos: dict, extensoes: dict, log: AuditLog, alvo: str,
                          autorizacao_id: str) -> tuple[int, str, str | None] | _FalhaDeRede:
    """A ÚNICA exceção ao HEAD-only, isolada para o CODEOWNER auditar num só lugar
    que 'nunca baixa o recurso' é mantido: 405 → GET com `Range: bytes=0-0`, em
    stream SEM iterar (lê no máximo 1 byte). Devolve (status, content_type,
    content_length) ou `_FALHA_DE_REDE`; audita a requisição (ou a falha)."""
    try:
        with client.stream("GET", url_pinada, extensions=extensoes,
                           headers={**cabecalhos, "Range": "bytes=0-0"}) as r:
            status = r.status_code
            content_type = r.headers.get("content-type", "")
            content_length = r.headers.get("content-length")
    except httpx.RequestError as erro:
        log.registrar(url=url_logica, metodo="GET(range)", alvo=alvo,
                      autorizacao_id=autorizacao_id, status=-1,
                      evento=f"falha-de-rede:{type(erro).__name__}")
        return _FALHA_DE_REDE
    log.registrar(url=url_logica, metodo="GET(range)", alvo=alvo,
                  autorizacao_id=autorizacao_id, status=status)
    return status, content_type, content_length


def _detectar_catch_all(client: httpx.Client, alvo: str, ip_pinado: str,
                        log: AuditLog, autorizacao_id: str) -> tuple | None:
    """1 HEAD num caminho inexistente ALEATÓRIO, ANTES do laço, para pegar alvo
    catch-all (responde 2xx a tudo). Se 2xx, devolve a assinatura
    `(content_type, content_length)` que os probes idênticos serão descartados
    contra. Auditada (`evento="baseline-soft404"`) — nenhuma requisição invisível;
    conecta no IP pinado com SNI pelo hostname, como qualquer probe."""
    ghost = f"/{uuid.uuid4().hex}"          # inexistente por construção
    url_logica, url_pinada, host = _url_pinada(alvo, ip_pinado, ghost)
    try:
        r = client.head(url_pinada, headers={"Host": host},
                        extensions={"sni_hostname": host})
    except httpx.RequestError as erro:
        log.registrar(url=url_logica, metodo="HEAD", alvo=alvo, autorizacao_id=autorizacao_id,
                      status=-1, evento=f"baseline-soft404:falha-de-rede:{type(erro).__name__}")
        return None
    log.registrar(url=url_logica, metodo="HEAD", alvo=alvo, autorizacao_id=autorizacao_id,
                  status=r.status_code, evento="baseline-soft404")
    if 200 <= r.status_code < 300:
        return (r.headers.get("content-type", ""), r.headers.get("content-length"))
    return None


def sondar_caminho(client: httpx.Client, alvo: str, caminho: CaminhoSensivel,
                   log: AuditLog, autorizacao_id: str, ip_pinado: str,
                   baseline_catch_all: tuple | None = None
                   ) -> Finding | None | _FalhaDeRede | _PedeRecuo:
    """UM probe: HEAD no caminho, conectando ao IP PINADO, com TLS pelo hostname.

    Conecta ao `ip_pinado` (o IP provado por `verificar_posse`), NÃO ao que o DNS
    resolveria agora — é isto que fecha a janela de rebinding (A#1). O header
    `Host` e o SNI (`sni_hostname`) permanecem o hostname, então a verificação do
    certificado continua contra o host (nunca `verify=False`). Laudo e auditoria
    registram a URL LÓGICA (hostname), não o IP.

    Servidor que rejeita HEAD (405) é reprovado por um GET mínimo (`Range:
    bytes=0-0`) — lê no máximo 1 byte, nunca o corpo. Recuo (429/503) devolve
    `_PEDE_RECUO`: o caminho não é concluído e o laço desacelera. Falha de rede →
    `_FALHA_DE_REDE`. Nunca segue redirect. Em qualquer caso, run parcial fica
    inconclusivo — nunca um silêncio que pareça 'limpo'.
    """
    url_logica, url_pinada, host = _url_pinada(alvo, ip_pinado, caminho.path)
    cabecalhos = {"Host": host}
    extensoes = {"sni_hostname": host}
    metodo_usado = "HEAD"
    try:
        resposta = client.head(url_pinada, headers=cabecalhos, extensions=extensoes)
    except httpx.RequestError as erro:
        log.registrar(url=url_logica, metodo="HEAD", alvo=alvo, autorizacao_id=autorizacao_id,
                      status=-1, evento=f"falha-de-rede:{type(erro).__name__}")
        return _FALHA_DE_REDE
    log.registrar(url=url_logica, metodo="HEAD", alvo=alvo,
                  autorizacao_id=autorizacao_id, status=resposta.status_code)
    status = resposta.status_code
    content_type = resposta.headers.get("content-type", "")
    content_length = resposta.headers.get("content-length")

    # 405 (HEAD não permitido): confirma existência com GET mínimo (Range), na
    # função isolada que o CODEOWNER audita como a única exceção ao HEAD-only.
    if status == 405:
        metodo_usado = "GET(range)"
        fallback = executar_fallback_get(client, url_logica, url_pinada,
                                         cabecalhos, extensoes, log, alvo, autorizacao_id)
        if isinstance(fallback, _FalhaDeRede):
            return _FALHA_DE_REDE
        status, content_type, content_length = fallback

    veredito = avaliar_resposta_em_finding(
        status, content_type, caminho, url_logica,
        content_length=content_length, baseline_catch_all=baseline_catch_all)
    if veredito is _SOFT_404:
        # Descarte auditado: sem isto o log mostra 200 sem finding e sem motivo,
        # indistinguível de bug (G5). Nenhuma requisição nova — só a decisão.
        log.registrar(url=url_logica, metodo=metodo_usado, alvo=alvo,
                      autorizacao_id=autorizacao_id, status=status,
                      evento="descartado:soft-404")
        return None
    return veredito


def sondar(escopo, alvo: str, caminhos: list[CaminhoSensivel], *,
           client: httpx.Client | None = None, log: AuditLog | None = None,
           dry_run: bool = True, intervalo_s: float = PISO_INTERVALO_S,
           dormir=time.sleep) -> ResultadoSondagem:
    """Orquestra a sondagem de um alvo. `dry_run=True` (padrão) NÃO toca a rede.

    O caminho ativo (`dry_run=False`) é gated em três portões antes de qualquer
    requisição: `require_discovery` (opt-in C1), `require_escopo` (host na
    allowlist) e `verificar_posse` (IP não divergiu do carregamento). Depois,
    o laço respeita o piso de rate-limit e checa o kill-switch a cada iteração,
    e aborta o alvo após `MAX_FALHAS_CONSECUTIVAS` recuos/falhas seguidos
    (circuit breaker). Todos os abortos deixam evento no `AuditLog`.
    """
    _validar_alvo(alvo)          # fail-fast antes de qualquer portão ou requisição
    esperado = len(caminhos)
    # run_id único por run: sem log injetado, dois runs não colidem no AuditLog.
    # Com log injetado, herda o run_id dele (o caller manda na trilha).
    run_id = log.run_id if log is not None else f"fase-c-{uuid.uuid4().hex[:12]}"

    # Planejar é seguro e não exige autorização: nenhuma requisição sai.
    if dry_run:
        return ResultadoSondagem(alvo=alvo, esperado=esperado, executado=0,
                                 abortado_por="dry-run", run_id=run_id)

    # --- portões: sem os três, nenhum probe acontece ---
    require_discovery()
    require_escopo(escopo, alvo)
    host = urlsplit(alvo).hostname or ""
    # require_escopo já abortou se fora do escopo: aqui o alvo está no escopo.
    autorizacao_id = escopo.entrada(alvo).evidencia
    # Log criado DEPOIS dos portões (que decidem SE roda) e ANTES de verificar_posse,
    # para o aborto por posse-divergente deixar rastro. Antes de require_discovery
    # faria um run não-autorizado criar o log (G4).
    log = log or AuditLog(run_id=run_id, escopo_hash=getattr(escopo, "hash_congelado", ""))

    ips_pinados, motivo_posse = escopo.verificar_posse_detalhada(host)
    if not ips_pinados:
        # O motivo (takeover/nao-listado/sem-baseline/resolucao-falhou) vem do
        # escopo por retorno e é logado AQUI — escopo não conhece o AuditLog (G7).
        log.registrar_evento(alvo=alvo, autorizacao_id=autorizacao_id,
                             evento=f"abortado:posse-divergente:{motivo_posse}")
        return ResultadoSondagem(alvo=alvo, esperado=esperado, executado=0,
                                 abortado_por="posse-divergente", run_id=run_id)
    # Pina UM IP provado e conecta só nele — o probe não re-resolve o DNS.
    # Por família (IPv4 primeiro), nunca por ordem de string (G2/dual-stack).
    ip_pinado = _escolher_ip(ips_pinados)

    intervalo = max(intervalo_s, PISO_INTERVALO_S)   # piso não-configurável
    fechar_no_fim = client is None
    client = client or _cliente_padrao()

    resultado = ResultadoSondagem(alvo=alvo, esperado=esperado, run_id=run_id)
    recuos_seguidos = 0
    falhas_consecutivas = 0
    try:
        # Kill-switch checado ANTES do HEAD-fantasma: ativo desde o início, nem o
        # baseline sai (kill-switch = nenhuma requisição).
        if kill_switch_active():
            resultado.abortado_por = "kill-switch"
            log.registrar_evento(alvo=alvo, autorizacao_id=autorizacao_id,
                                 evento="abortado:kill-switch")
            return resultado
        # Baseline dinâmico de soft-404: 1 HEAD-fantasma ANTES do laço. Se o alvo
        # é catch-all, os probes com a mesma assinatura viram ruído, não achado.
        baseline_catch_all = _detectar_catch_all(client, alvo, ip_pinado, log, autorizacao_id)
        for i, caminho in enumerate(caminhos):
            if kill_switch_active():
                resultado.abortado_por = "kill-switch"
                log.registrar_evento(alvo=alvo, autorizacao_id=autorizacao_id,
                                     evento="abortado:kill-switch")
                break
            if i:
                # Piso entre requisições; após recuo (429/503), backoff exponencial
                # com teto. Nunca antes da 1ª, e nunca abaixo do piso.
                dormir(calcular_espera_backoff(recuos_seguidos, intervalo))
            achado = sondar_caminho(client, alvo, caminho, log, autorizacao_id,
                                    ip_pinado, baseline_catch_all)
            if isinstance(achado, _PedeRecuo | _FalhaDeRede):
                # Probe NÃO concluído (executado não sobe). Recuo amplia o backoff;
                # ambos contam para o circuit breaker (G1).
                if isinstance(achado, _PedeRecuo):
                    resultado.recuos += 1
                    recuos_seguidos += 1
                else:
                    resultado.falhas_rede += 1
                    recuos_seguidos = 0    # falha de rede não é recuo: não amplia backoff
                falhas_consecutivas += 1
                if falhas_consecutivas >= MAX_FALHAS_CONSECUTIVAS:
                    resultado.abortado_por = "circuit-breaker"
                    log.registrar_evento(alvo=alvo, autorizacao_id=autorizacao_id,
                                         evento="abortado:circuit-breaker")
                    break
                continue
            # Resposta válida: probe concluído, zera backoff e breaker.
            recuos_seguidos = 0
            falhas_consecutivas = 0
            resultado.executado += 1
            if achado is not None:
                resultado.findings.append(achado)
    finally:
        if fechar_no_fim:
            client.close()
    return resultado


def sondar_multialvo(escopo, caminhos: list[CaminhoSensivel],
                     **kwargs) -> list[ResultadoSondagem]:
    """Sonda TODAS as origens do escopo CARREGADO — nunca uma lista externa.

    Iterar só o escopo é o que impede a ampliação de cobertura de virar brecha no
    portão de origem exata: um alvo fora do escopo não existe aqui. Cada alvo
    passa pelos próprios portões (discovery/escopo/posse) e pelo próprio piso de
    rate-limit; um alvo que aborta (ex.: posse-divergente) devolve seu resultado
    e NÃO impede os demais. Devolve um resultado por alvo (resumo consolidado)."""
    return [sondar(escopo, entrada.origem, caminhos, **kwargs)
            for entrada in escopo.entradas]


def main(argv: list[str] | None = None) -> int:
    """CLI. `--dry-run` é o padrão; sondar de verdade exige `--executar`.

    Mesmo com `--executar`, os portões de `sondar` decidem: sem
    WEBQA_DISCOVERY_AUTHORIZED=1 e sem o alvo no escopo, nada sai.
    """
    from webqa import escopo as escopo_mod
    from webqa.gates import DISCOVERY_ENV, discovery_authorized

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--alvo", help="origem exata (https://host)")
    parser.add_argument("--multi-alvo", action="store_true",
                        help="sonda TODAS as origens do escopo (ignora --alvo)")
    parser.add_argument("--escopo", type=Path, default=Path("escopo-autorizado.yaml"))
    parser.add_argument("--caminhos", type=Path, default=Path("data/caminhos-sensiveis.yaml"))
    parser.add_argument("--executar", action="store_true",
                        help="sonda de verdade; sem esta flag, só planeja (dry-run)")
    args = parser.parse_args(argv)
    if not args.alvo and not args.multi_alvo:
        parser.error("informe --alvo ou --multi-alvo")

    caminhos = carregar_caminhos(args.caminhos)
    escopo = escopo_mod.carregar(args.escopo)
    alvos = [e.origem for e in escopo.entradas] if args.multi_alvo else [args.alvo]

    if not args.executar:
        print(f"[dry-run] {len(caminhos)} caminhos planejados contra {len(alvos)} alvo(s):")
        for alvo in alvos:
            for c in caminhos:
                print(f"  HEAD {alvo.rstrip('/')}{c.path}  ({c.categoria}/{c.severidade})")
        print("Nenhuma requisição foi feita. Use --executar para sondar.")
        return 0

    if not discovery_authorized():
        print(f"Sondagem não autorizada: exporte {DISCOVERY_ENV}=1 com autorização "
              "documentada do dono do alvo. Nada foi enviado.")
        return 1

    resultados = (sondar_multialvo(escopo, caminhos, dry_run=False) if args.multi_alvo
                  else [sondar(escopo, args.alvo, caminhos, dry_run=False)])
    for resultado in resultados:
        print(f"Sondagem [{resultado.alvo}]: {resultado.executado}/{resultado.esperado} "
              f"caminhos, {len(resultado.findings)} achado(s)"
              + (f", ABORTADO por {resultado.abortado_por}" if resultado.abortado_por else ""))
        if resultado.inconclusivo:
            print("  Resultado INCONCLUSIVO: o run não cobriu a superfície declarada.")
        for f in resultado.findings:
            print(f"  [{f.severidade}] {f.tipo} — {f.recurso}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
