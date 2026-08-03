"""VERIFICAÇÃO do motor de sondagem ativa da Fase C (C1a).

Nenhuma requisição real sai daqui: o cliente é um `httpx.MockTransport` e o
`getaddrinfo` é dublado (posse). O que se prova é o CONTORNO — gated, HEAD-only,
sem redirect, dry-run por padrão, kill-switch no laço, piso de rate-limit, run
parcial inconclusivo, achados `fase="C"` com remediação — e que cada guarda
morde. Um detector que nunca pegou violação plantada não está provado.

Specs de comportamento adiado ao C1b entram como `xfail(strict=True)`: o
contrato fica registrado, e o dia em que forem implementadas o `strict` obriga a
remover o marcador.
"""
from __future__ import annotations

import json
import socket
from datetime import date

import httpx
import pytest

from webqa import escopo as escopo_mod
from webqa import gates
from webqa import sondagem as sondagem_mod
from webqa.audit import AuditLog
from webqa.sondagem import (
    MAX_CAMINHOS,
    PISO_INTERVALO_S,
    CaminhoSensivel,
    ResultadoSondagem,
    carregar_caminhos,
    sondar,
)

pytestmark = pytest.mark.verification

ALVO = "https://alvo-fixture.exemplo"
IP_ALVO = "203.0.113.7"

C_GIT = CaminhoSensivel("/.git/HEAD", "vcs", "alta", "text/plain", "Remova o .git do docroot.")
C_ENV = CaminhoSensivel("/.env", "configuracao", "alta", "application/octet-stream", "Bloqueie o .env.")
C_BACKUP = CaminhoSensivel("/backup.zip", "backup", "media", "application/zip", "Exclua backups.")


@pytest.fixture(autouse=True)
def _ambiente_limpo(monkeypatch):
    """Gates desligados e SEM DNS real por padrão. Cada teste liga o que precisa."""
    for env in (gates.DISCOVERY_ENV, gates.ACTIVE_PROBES_ENV, gates.KILL_ENV, gates.LOAD_ENV):
        monkeypatch.delenv(env, raising=False)

    def _sem_dns(*_a, **_k):
        raise socket.gaierror("getaddrinfo dublado: DNS real proibido no teste")
    monkeypatch.setattr(socket, "getaddrinfo", _sem_dns)


def _resolve_para(monkeypatch, ip: str) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p, *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))])


def _escopo_valido(tmp_path, monkeypatch, ip: str = IP_ALVO):
    """Escopo real com o ALVO autorizado e snapshot de posse no IP dado."""
    p = tmp_path / "escopo-autorizado.yaml"
    p.write_text(
        "alvos:\n"
        f'  - origem: "{ALVO}"\n'
        '    autorizado_por: "danzeroum"\n'
        f'    data: "{date.today().isoformat()}"\n'
        '    evidencia: "pr#1"\n'
        '    ambiente: "homologacao"\n',
        encoding="utf-8")
    _resolve_para(monkeypatch, ip)          # snapshot no carregamento
    return escopo_mod.carregar(p)


def _transporte(rotas, registro=None):
    def handler(request):
        if registro is not None:
            registro.append((request.method, request.url.path,
                             request.headers.get("range")))
        status, headers = rotas.get(request.url.path, (404, {}))
        return httpx.Response(status, headers=headers)
    return httpx.MockTransport(handler)


def _client(rotas, registro=None) -> httpx.Client:
    # follow_redirects=False espelha o cliente de produção.
    return httpx.Client(transport=_transporte(rotas, registro), follow_redirects=False)


# ---------- dry-run é o padrão e não toca a rede ----------

def test_dry_run_e_o_padrao_e_nao_sonda(tmp_path, monkeypatch):
    escopo = _escopo_valido(tmp_path, monkeypatch)

    def _explode(*_a, **_k):
        raise AssertionError("dry-run não pode tocar a rede")
    resultado = sondar(escopo, ALVO, [C_GIT, C_ENV], client=_client({}), dormir=_explode)

    assert resultado.abortado_por == "dry-run"
    assert resultado.executado == 0
    assert resultado.esperado == 2
    assert resultado.inconclusivo is True     # nada foi coberto


# ---------- os três portões: sem eles, nenhum probe ----------

def test_gate_de_discovery_fechado_pula(tmp_path, monkeypatch):
    escopo = _escopo_valido(tmp_path, monkeypatch)
    # DISCOVERY não setado → require_discovery pula (skip, não fail)
    with pytest.raises(pytest.skip.Exception, match=gates.DISCOVERY_ENV):
        sondar(escopo, ALVO, [C_GIT], client=_client({}), dry_run=False)


def test_fora_do_escopo_pula(tmp_path, monkeypatch):
    escopo = _escopo_valido(tmp_path, monkeypatch)
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    with pytest.raises(pytest.skip.Exception, match=r"\[gate:escopo\]"):
        sondar(escopo, "https://outro-host.exemplo", [C_GIT], client=_client({}), dry_run=False)


def test_posse_divergente_aborta_sem_sondar(tmp_path, monkeypatch):
    escopo = _escopo_valido(tmp_path, monkeypatch, ip=IP_ALVO)
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    _resolve_para(monkeypatch, "198.51.100.9")     # host reapontado (takeover)

    def _explode(*_a, **_k):
        raise AssertionError("posse divergente não pode chegar a sondar")
    resultado = sondar(escopo, ALVO, [C_GIT], client=_client({}, registro=None),
                       dry_run=False, dormir=_explode)

    assert resultado.abortado_por == "posse-divergente"
    assert resultado.executado == 0
    assert resultado.inconclusivo is True


# ---------- caminho feliz: existência (2xx) é o achado ----------

def _sondar_ativo(tmp_path, monkeypatch, rotas, caminhos, registro=None, **kw):
    escopo = _escopo_valido(tmp_path, monkeypatch)
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    log = AuditLog(run_id="teste", escopo_hash=escopo.hash_congelado)
    kw.setdefault("dormir", lambda _s: None)   # sem espera real, salvo se o teste medir
    resultado = sondar(escopo, ALVO, caminhos, client=_client(rotas, registro),
                       log=log, dry_run=False, **kw)
    return resultado, log


def test_2xx_vira_finding_de_fase_c_com_remediacao(tmp_path, monkeypatch):
    rotas = {
        "/.git/HEAD": (200, {"content-type": "text/plain"}),
        "/.env": (200, {"content-type": "application/octet-stream"}),
        "/backup.zip": (404, {}),
    }
    resultado, _ = _sondar_ativo(tmp_path, monkeypatch, rotas, [C_GIT, C_ENV, C_BACKUP])

    assert resultado.executado == 3 and resultado.esperado == 3
    assert resultado.inconclusivo is False
    tipos = sorted(f.tipo for f in resultado.findings)
    assert tipos == ["exposicao:configuracao", "exposicao:vcs"]
    for f in resultado.findings:
        assert f.fase == "C"
        assert f.remediacao          # obrigatória em C
        assert "corpo não lido" in f.evidencia


def test_so_faz_HEAD_e_nao_segue_redirect(tmp_path, monkeypatch):
    registro = []
    rotas = {
        "/.git/HEAD": (200, {"content-type": "text/plain"}),
        "/.env": (302, {"location": "https://alvo-fixture.exemplo/login"}),
    }
    resultado, _ = _sondar_ativo(tmp_path, monkeypatch, rotas, [C_GIT, C_ENV], registro=registro)

    assert {metodo for metodo, _p, _r in registro} == {"HEAD"}, "só HEAD, nunca GET"
    # o 3xx não é achado e não foi seguido (um único request por caminho curado).
    # O HEAD-fantasma (baseline C2) também é HEAD, mas num caminho aleatório —
    # filtra-se pelos caminhos curados para provar o "um request por caminho".
    curados = [p for _m, p, _r in registro if p in ("/.git/HEAD", "/.env")]
    assert curados == ["/.git/HEAD", "/.env"]
    assert [f.recurso for f in resultado.findings] == ["https://alvo-fixture.exemplo/.git/HEAD"]


def test_soft_404_por_content_type_nao_vira_finding(tmp_path, monkeypatch):
    """200 com text/html onde se esperava octet-stream = provável soft-404."""
    rotas = {"/.env": (200, {"content-type": "text/html; charset=utf-8"})}
    resultado, _ = _sondar_ativo(tmp_path, monkeypatch, rotas, [C_ENV])

    assert resultado.executado == 1
    assert resultado.findings == []


# ---------- kill-switch, checado a cada iteração ----------

def test_kill_switch_desde_o_inicio_aborta_sem_sondar(tmp_path, monkeypatch):
    monkeypatch.setenv(gates.KILL_ENV, "1")
    resultado, log = _sondar_ativo(tmp_path, monkeypatch, {}, [C_GIT, C_ENV])

    assert resultado.abortado_por == "kill-switch"
    assert resultado.executado == 0
    # G4: nenhuma REQUISIÇÃO, mas o aborto deixa 1 evento (rastro de governança).
    assert [linha["evento"] for linha in log.linhas] == ["abortado:kill-switch"]
    assert all(linha["metodo"] == "" for linha in log.linhas)   # evento, não probe
    assert resultado.inconclusivo is True


def test_kill_switch_no_meio_do_laco_para_o_run(tmp_path, monkeypatch):
    chamadas = {"n": 0}

    def _kill_na_terceira():
        # C2: o kill-switch é checado 1x ANTES do HEAD-fantasma, depois a cada
        # iteração. 1ª (pré-fantasma) e 2ª (i=0) livres; 3ª (i=1) dispara → o
        # primeiro probe roda e o run aborta antes do segundo.
        chamadas["n"] += 1
        return chamadas["n"] >= 3
    monkeypatch.setattr("webqa.sondagem.kill_switch_active", _kill_na_terceira)

    rotas = {"/.git/HEAD": (200, {"content-type": "text/plain"})}
    resultado, _ = _sondar_ativo(tmp_path, monkeypatch, rotas, [C_GIT, C_ENV, C_BACKUP])

    assert resultado.abortado_por == "kill-switch"
    assert resultado.executado == 1         # só o primeiro rodou
    assert resultado.inconclusivo is True   # 1 < 3


# ---------- piso de rate-limit, não-configurável ----------

def test_piso_de_rate_limit_nao_pode_ser_reduzido(tmp_path, monkeypatch):
    intervalos = []
    rotas = {"/.git/HEAD": (404, {}), "/.env": (404, {}), "/backup.zip": (404, {})}
    _sondar_ativo(tmp_path, monkeypatch, rotas, [C_GIT, C_ENV, C_BACKUP],
                  intervalo_s=0.001, dormir=intervalos.append)

    assert intervalos, "houve espera entre requisições"
    assert all(i >= PISO_INTERVALO_S for i in intervalos), "o piso não pode ser burlado"
    assert len(intervalos) == 2, "espera ENTRE requisições (n-1), nunca antes da 1ª"


# ---------- auditoria: uma linha por requisição, sem query ----------

def test_cada_probe_e_auditado(tmp_path, monkeypatch):
    rotas = {"/.git/HEAD": (200, {"content-type": "text/plain"}), "/.env": (404, {})}
    resultado, log = _sondar_ativo(tmp_path, monkeypatch, rotas, [C_GIT, C_ENV])

    # C2: o baseline-soft404 (HEAD-fantasma) também é auditado, além dos probes.
    probes = [linha for linha in log.linhas if linha["evento"] is None]
    assert len(probes) == resultado.executado == 2
    assert any(linha["evento"] == "baseline-soft404" for linha in log.linhas)
    for linha in log.linhas:
        assert linha["metodo"] == "HEAD"
        assert linha["alvo"] == ALVO
        assert "?" not in linha["url"]      # supressão de query-string do AuditLog


# ---------- run parcial é inconclusivo, nunca "tudo limpo" ----------

def test_run_parcial_e_inconclusivo():
    r = ResultadoSondagem(alvo=ALVO, esperado=5, executado=3)
    assert r.inconclusivo is True
    completo = ResultadoSondagem(alvo=ALVO, esperado=3, executado=3)
    assert completo.inconclusivo is False


# ---------- carregador: teto, schema, duplicata ----------

def test_carregar_a_lista_real_do_repo():
    from pathlib import Path
    real = Path(__file__).resolve().parent.parent / "data" / "caminhos-sensiveis.yaml"
    caminhos = carregar_caminhos(real)
    assert caminhos and all(isinstance(c, CaminhoSensivel) for c in caminhos)


def test_carregador_impoe_max_caminhos(tmp_path):
    p = tmp_path / "grande.yaml"
    item = ('- path: "/x{i}"\n  categoria: "vcs"\n  severidade: "baixa"\n'
            '  content_type_esperado: "text/plain"\n  remediacao: "r"\n')
    p.write_text("".join(item.replace("{i}", str(i)) for i in range(MAX_CAMINHOS + 1)),
                 encoding="utf-8")
    with pytest.raises(ValueError, match="MAX_CAMINHOS"):
        carregar_caminhos(p)


def test_carregador_reprova_duplicata(tmp_path):
    p = tmp_path / "dup.yaml"
    ent = ('- path: "/.env"\n  categoria: "configuracao"\n  severidade: "alta"\n'
           '  content_type_esperado: "application/octet-stream"\n  remediacao: "r"\n')
    p.write_text(ent + ent, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicad"):
        carregar_caminhos(p)


@pytest.mark.parametrize("kwargs,erro", [
    ({"path": "sem-barra"}, "path"),
    ({"categoria": "invalida"}, "categoria"),
    ({"severidade": "gravissima"}, "severidade"),
    ({"remediacao": "  "}, "remediação"),
])
def test_caminho_sensivel_nasce_validado(kwargs, erro):
    base = dict(path="/.env", categoria="configuracao", severidade="alta",
                content_type_esperado="application/octet-stream", remediacao="corrija")
    base.update(kwargs)
    with pytest.raises(ValueError, match=erro):
        CaminhoSensivel(**base)


# ---------- C1b fatia 1: robustez e correção (Tier A #2–#6) ----------

def test_erro_de_rede_num_probe_nao_derruba_o_run(tmp_path, monkeypatch):
    """#2: um ConnectError no meio da lista NÃO crasha — conta falha, segue,
    o run fica inconclusivo, e os achados anteriores são preservados."""
    def handler(request):
        if request.url.path == "/.env":
            raise httpx.ConnectError("conexão recusada")
        status = 200 if request.url.path == "/.git/HEAD" else 404
        headers = {"content-type": "text/plain"} if status == 200 else {}
        return httpx.Response(status, headers=headers)

    escopo = _escopo_valido(tmp_path, monkeypatch)
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    log = AuditLog(run_id="teste", escopo_hash=escopo.hash_congelado)
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    resultado = sondar(escopo, ALVO, [C_GIT, C_ENV, C_BACKUP], client=client, log=log,
                       dry_run=False, dormir=lambda _s: None)

    assert resultado.falhas_rede == 1
    assert resultado.executado == 2          # git e backup concluíram; env falhou
    assert len(resultado.findings) == 1      # o achado de /.git/HEAD foi preservado
    assert resultado.inconclusivo is True
    assert any(linha["status"] == -1 for linha in log.linhas), "a falha foi auditada"


def test_runs_sem_log_injetado_tem_run_ids_distintos(tmp_path, monkeypatch):
    """#3: sem log injetado, cada run gera um run_id único — não colidem."""
    escopo = _escopo_valido(tmp_path, monkeypatch)
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    r1 = sondar(escopo, ALVO, [C_GIT], client=_client({"/.git/HEAD": (404, {})}),
                dry_run=False, dormir=lambda _s: None)
    r2 = sondar(escopo, ALVO, [C_GIT], client=_client({"/.git/HEAD": (404, {})}),
                dry_run=False, dormir=lambda _s: None)
    assert r1.run_id.startswith("fase-c-") and r2.run_id.startswith("fase-c-")
    assert r1.run_id != r2.run_id


def test_run_id_injetado_e_herdado_do_log(tmp_path, monkeypatch):
    """Com log injetado, o resultado herda o run_id do log (o caller manda)."""
    escopo = _escopo_valido(tmp_path, monkeypatch)
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    log = AuditLog(run_id="run-do-caller", escopo_hash=escopo.hash_congelado)
    r = sondar(escopo, ALVO, [C_GIT], client=_client({"/.git/HEAD": (404, {})}),
               log=log, dry_run=False, dormir=lambda _s: None)
    assert r.run_id == "run-do-caller"


def test_e_soft_404_sem_tipo_esperado_desconfia_de_html():
    """#4: sem content_type_esperado declarado, HTML recebido é soft-404 suspeito."""
    from webqa.sondagem import _e_soft_404
    assert _e_soft_404("", "text/html; charset=utf-8") is True
    assert _e_soft_404("", "application/json") is False          # não-HTML: não corta
    assert _e_soft_404("", "") is False                          # sem sinal: não corta
    assert _e_soft_404("application/zip", "application/zip") is False


def test_caminho_sem_tipo_esperado_com_html_e_descartado(tmp_path, monkeypatch):
    """#4 ponta a ponta: caminho sem tipo esperado + 200 text/html → não é achado."""
    c = CaminhoSensivel("/qualquer", "configuracao", "media", "", "corrija")
    rotas = {"/qualquer": (200, {"content-type": "text/html"})}
    resultado, _ = _sondar_ativo(tmp_path, monkeypatch, rotas, [c])
    assert resultado.findings == []
    assert resultado.executado == 1


@pytest.mark.parametrize("alvo", [
    "example.com",                # sem esquema
    "ftp://x",                    # esquema errado
    "https://x/app",             # com path
    "https://x/?q=1",            # com query
    "https://x#frag",            # com fragment
    "https:///sem-host",         # sem hostname
])
def test_validar_alvo_reprova_malformado(alvo):
    """#5: alvo que não é origem http(s) limpa → ValueError."""
    from webqa.sondagem import _validar_alvo
    with pytest.raises(ValueError):
        _validar_alvo(alvo)


def test_alvo_malformado_reprova_em_sondar_antes_de_tocar_a_rede(tmp_path, monkeypatch):
    """#5: a validação roda ANTES dos portões e da rede.

    O alvo tem ORIGEM no escopo (`origem_de` remove o path), mas é malformado
    (path+query). Assim, sem `_validar_alvo`, o `require_escopo` deixaria passar
    — e é o `_validar_alvo` que tem de barrar. Escolha deliberada para que a
    prova por mutação FALHE (não seja pulada pelo gate de escopo)."""
    escopo = _escopo_valido(tmp_path, monkeypatch)
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    with pytest.raises(ValueError):
        sondar(escopo, ALVO + "/app?q=1", [C_GIT],
               client=_client({}), dry_run=False, dormir=lambda _s: None)


def test_autorizacao_id_vem_direto_do_escopo(tmp_path, monkeypatch):
    """#6: o autorizacao_id auditado vem de escopo.entrada(alvo).evidencia."""
    _, log = _sondar_ativo(tmp_path, monkeypatch, {"/.git/HEAD": (404, {})}, [C_GIT])
    assert log.linhas[0]["autorizacao_id"] == "pr#1"


# ---------- C1c: DNS-rebind (A#1) — pino de IP com TLS por hostname ----------

def test_verificar_posse_devolve_o_conjunto_pinado(tmp_path, monkeypatch):
    """A prova de posse agora entrega os IPs pinados (não só um bool)."""
    escopo = _escopo_valido(tmp_path, monkeypatch)
    assert escopo.verificar_posse("alvo-fixture.exemplo") == frozenset({IP_ALVO})


def test_probe_conecta_no_ip_pinado_preservando_sni_do_hostname(tmp_path, monkeypatch):
    """O HEAD sai para o IP PINADO, mas Host e SNI continuam o hostname — o cert
    é verificado contra o host, não contra o IP. É isto que fecha o rebinding."""
    capturado = {}

    def handler(request):
        capturado["host_conectado"] = request.url.host
        capturado["header_host"] = request.headers.get("host")
        capturado["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(404)

    escopo = _escopo_valido(tmp_path, monkeypatch)
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    sondar(escopo, ALVO, [C_GIT], client=client, dry_run=False, dormir=lambda _s: None)

    assert capturado["host_conectado"] == IP_ALVO           # conectou no IP pinado
    assert capturado["header_host"] == "alvo-fixture.exemplo"
    assert capturado["sni"] == "alvo-fixture.exemplo"       # TLS verifica o hostname


def test_rebind_entre_posse_e_probe_aborta(tmp_path, monkeypatch):
    """Snapshot num IP, resolução no probe diverge → posse-divergente, zero probes.
    Fecha a janela A#1: o probe nunca chega a sair para o IP reapontado."""
    escopo = _escopo_valido(tmp_path, monkeypatch, ip=IP_ALVO)
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    _resolve_para(monkeypatch, "198.51.100.9")             # host reapontado

    def _explode(*_a, **_k):
        raise AssertionError("rebind não pode chegar à rede")
    resultado = sondar(escopo, ALVO, [C_GIT, C_ENV], client=_client({}),
                       dry_run=False, dormir=_explode)
    assert resultado.abortado_por == "posse-divergente"
    assert resultado.executado == 0 and resultado.inconclusivo is True


def test_tls_nunca_e_desabilitado_no_motor():
    """Guarda estrutural (AST): nenhuma CHAMADA no motor passa verify=False.

    Pinar IP com verify=False trocaria o rebinding por um MITM — proibido. Por
    AST, não por substring: a docstring pode citar `verify=False` para explicar a
    proibição sem disparar a guarda — a lição da §2.11 (prosa não é código)."""
    import ast
    from pathlib import Path

    def _desliga_tls(fonte: str) -> bool:
        return any(
            isinstance(no, ast.keyword) and no.arg == "verify"
            and isinstance(no.value, ast.Constant) and no.value.value is False
            for no in ast.walk(ast.parse(fonte)))

    assert _desliga_tls("cliente(verify=False)") is True             # morde o plantado
    assert _desliga_tls('"""nunca verify=False"""\nx = 1') is False  # ignora a prosa

    raiz = Path(__file__).resolve().parent.parent
    for modulo in ("webqa/sondagem.py", "webqa/escopo.py"):
        fonte = (raiz / modulo).read_text(encoding="utf-8")
        assert not _desliga_tls(fonte), f"{modulo} desliga a verificação TLS"


# ---------- C1b fatia 2: HEAD 405 → GET Range, e backoff 429/503 ----------

def test_head_405_faz_fallback_range_get(tmp_path, monkeypatch):
    """Servidor que rejeita HEAD (405) é reprovado por um GET mínimo
    (`Range: bytes=0-0`), sem baixar o corpo."""
    registro = []
    rotas = {"/.git/HEAD": (405, {})}
    _sondar_ativo(tmp_path, monkeypatch, rotas, [C_GIT], registro=registro)
    metodos = {m for m, _p, _r in registro}
    ranges = [r for _m, _p, r in registro]
    assert "GET" in metodos and "bytes=0-0" in ranges


def test_405_fallback_get_range_confirma_existencia(tmp_path, monkeypatch):
    """HEAD 405 e GET Range 206 → existência confirmada, vira Finding fase=C."""
    def handler(request):
        if request.method == "HEAD":
            return httpx.Response(405)
        assert request.headers.get("range") == "bytes=0-0", "GET tem de pedir 1 byte"
        return httpx.Response(206, headers={"content-type": "application/octet-stream"})

    escopo = _escopo_valido(tmp_path, monkeypatch)
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    resultado = sondar(escopo, ALVO, [C_ENV], client=client, dry_run=False, dormir=lambda _s: None)

    assert [f.fase for f in resultado.findings] == ["C"]
    assert resultado.executado == 1


def test_429_dispara_backoff(tmp_path, monkeypatch):
    """Um 429 dispara uma espera MAIOR que o piso antes do próximo probe."""
    intervalos = []
    rotas = {"/.git/HEAD": (429, {}), "/.env": (404, {})}
    _sondar_ativo(tmp_path, monkeypatch, rotas, [C_GIT, C_ENV], dormir=intervalos.append)
    assert any(i > PISO_INTERVALO_S for i in intervalos), "429 deveria ampliar a espera"


def test_429_e_inconclusivo_e_nao_conta_como_executado(tmp_path, monkeypatch):
    """Recuo do servidor não conclui o caminho: conta em `recuos`, não em
    `executado`, e o run fica inconclusivo (não vira 'zero exposições')."""
    rotas = {"/.git/HEAD": (429, {})}
    resultado, _ = _sondar_ativo(tmp_path, monkeypatch, rotas, [C_GIT])
    assert resultado.recuos == 1
    assert resultado.executado == 0
    assert resultado.findings == []
    assert resultado.inconclusivo is True


# ---------- C1d: IPv6/dual-stack no pino (G2) + procedencia no Finding (G3) ----------

IP_V6 = "2001:db8::1"


def _resolve_multi(monkeypatch, *ips: str) -> None:
    """`getaddrinfo` devolve vários IPs (dual-stack), como no host real."""
    infos = [(socket.AF_INET6 if ":" in ip else socket.AF_INET,
              socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))
             for ip in ips]
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p, *a, **k: infos)


def _escopo_multi(tmp_path, monkeypatch, *ips):
    """Escopo com o ALVO autorizado e snapshot de posse com os IPs dados
    (snapshot no carregamento e re-resolução no probe batem por igualdade)."""
    _resolve_multi(monkeypatch, *ips)
    p = tmp_path / "escopo-autorizado.yaml"
    p.write_text(
        "alvos:\n"
        f'  - origem: "{ALVO}"\n'
        '    autorizado_por: "danzeroum"\n'
        f'    data: "{date.today().isoformat()}"\n'
        '    evidencia: "pr#1"\n'
        '    ambiente: "homologacao"\n',
        encoding="utf-8")
    return escopo_mod.carregar(p)


# --- G2: escolha de IP por família, nunca por ordem de string ---

def test_escolher_ip_prefere_ipv4_em_dual_stack():
    from webqa.sondagem import _escolher_ip
    assert _escolher_ip(frozenset({IP_V6, IP_ALVO})) == IP_ALVO
    # a ordenação de string elegeria o IPv6 — é o bug que a família evita:
    assert sorted({IP_V6, IP_ALVO})[0] == IP_V6


def test_escolher_ip_usa_ipv6_quando_e_o_unico():
    from webqa.sondagem import _escolher_ip
    assert _escolher_ip(frozenset({IP_V6})) == IP_V6


def test_url_pinada_poe_colchetes_em_ipv6():
    from webqa.sondagem import _url_pinada
    _log, url_pinada, host = _url_pinada(ALVO, IP_V6, "/.env")
    assert url_pinada == "https://[2001:db8::1]:443/.env"
    assert host == "alvo-fixture.exemplo"


def test_url_pinada_ipv4_sem_colchetes():
    from webqa.sondagem import _url_pinada
    _log, url_pinada, _host = _url_pinada(ALVO, IP_ALVO, "/.env")
    assert url_pinada == f"https://{IP_ALVO}:443/.env"


def test_dual_stack_conecta_no_ipv4(tmp_path, monkeypatch):
    """Host dual-stack: o probe conecta no IPv4 (a ordem de string elegeria o
    IPv6, que ainda quebraria a URL pinada)."""
    capturado = {}

    def handler(request):
        capturado["host"] = request.url.host
        return httpx.Response(404)

    escopo = _escopo_multi(tmp_path, monkeypatch, IP_V6, IP_ALVO)
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    sondar(escopo, ALVO, [C_GIT], client=client, dry_run=False, dormir=lambda _s: None)
    assert capturado["host"] == IP_ALVO


def test_ipv6_unico_gera_url_bem_formada_e_conecta(tmp_path, monkeypatch):
    """Só IPv6: a URL pinada é bem-formada (colchetes) e o probe conecta —
    hoje viraria falha de rede silenciosa (run inconclusivo sem explicar)."""
    capturado = {}

    def handler(request):
        capturado["host"] = request.url.host
        return httpx.Response(404)

    escopo = _escopo_multi(tmp_path, monkeypatch, IP_V6)
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    resultado = sondar(escopo, ALVO, [C_GIT], client=client, dry_run=False, dormir=lambda _s: None)
    assert capturado["host"] == IP_V6        # httpx desembrulha os colchetes em .host
    assert resultado.executado == 1


# --- G3: procedencia do caminho curado chega ao Finding ---

def test_finding_carrega_procedencia_do_caminho(tmp_path, monkeypatch):
    """A procedencia (OWASP/CWE) do caminho curado chega ao Finding — hoje é
    carregada de `caminhos-sensiveis.yaml` e descartada antes do achado."""
    c = CaminhoSensivel("/.git/HEAD", "vcs", "alta", "text/plain",
                        "Remova o .git.", procedencia="OWASP WSTG-CONF-004")
    rotas = {"/.git/HEAD": (200, {"content-type": "text/plain"})}
    resultado, _ = _sondar_ativo(tmp_path, monkeypatch, rotas, [c])
    assert [f.procedencia for f in resultado.findings] == ["OWASP WSTG-CONF-004"]


def test_finding_sem_procedencia_fica_vazio_sem_erro(tmp_path, monkeypatch):
    """Caminho sem procedencia → Finding.procedencia == '' e nenhum erro."""
    rotas = {"/.git/HEAD": (200, {"content-type": "text/plain"})}
    resultado, _ = _sondar_ativo(tmp_path, monkeypatch, rotas, [C_GIT])
    assert resultado.findings[0].procedencia == ""


# ---------- C1e: circuit breaker (G1) + abortos no log (G4) + evento soft-404 (G5)
#            + timeout granular (G6) ----------

def _caminhos(n: int) -> list:
    return [CaminhoSensivel(f"/p{i}", "vcs", "baixa", "text/plain", "corrija")
            for i in range(n)]


# --- G1: circuit breaker por falhas consecutivas ---

def test_circuit_breaker_aborta_apos_falhas_consecutivas(tmp_path, monkeypatch):
    """N recuos consecutivos → abortado_por='circuit-breaker', o laço PARA (não
    sonda os caminhos restantes) e o run fica inconclusivo."""
    from webqa.sondagem import MAX_FALHAS_CONSECUTIVAS
    caminhos = _caminhos(MAX_FALHAS_CONSECUTIVAS + 3)
    rotas = {c.path: (429, {}) for c in caminhos}
    resultado, _ = _sondar_ativo(tmp_path, monkeypatch, rotas, caminhos)
    assert resultado.abortado_por == "circuit-breaker"
    assert resultado.recuos == MAX_FALHAS_CONSECUTIVAS   # parou no N-ésimo
    assert resultado.executado == 0
    assert resultado.inconclusivo is True


def test_circuit_breaker_conta_falhas_de_rede_tambem(tmp_path, monkeypatch):
    """Falha de rede também conta para o breaker (alvo instável)."""
    from webqa.sondagem import MAX_FALHAS_CONSECUTIVAS

    def handler(request):
        raise httpx.ConnectError("conexão recusada")

    caminhos = _caminhos(MAX_FALHAS_CONSECUTIVAS + 2)
    escopo = _escopo_valido(tmp_path, monkeypatch)
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    resultado = sondar(escopo, ALVO, caminhos, client=client, dry_run=False,
                       dormir=lambda _s: None)
    assert resultado.abortado_por == "circuit-breaker"
    assert resultado.falhas_rede == MAX_FALHAS_CONSECUTIVAS


def test_circuit_breaker_reseta_com_resposta_valida(tmp_path, monkeypatch):
    """Uma resposta válida no meio zera o contador — nunca N seguidos, não aborta."""
    from webqa.sondagem import MAX_FALHAS_CONSECUTIVAS
    n = MAX_FALHAS_CONSECUTIVAS
    caminhos = _caminhos(2 * (n - 1) + 1)
    rotas = {c.path: (429, {}) for c in caminhos}
    rotas[caminhos[n - 1].path] = (404, {})       # uma resposta válida no meio
    resultado, _ = _sondar_ativo(tmp_path, monkeypatch, rotas, caminhos)
    assert resultado.abortado_por == ""           # nunca N recuos seguidos
    assert resultado.executado == 1               # o 404 concluiu


def test_backoff_durante_recuos_respeita_piso_e_teto(tmp_path, monkeypatch):
    """Enquanto o breaker não dispara, cada espera fica entre o piso e o teto."""
    from webqa.sondagem import MAX_FALHAS_CONSECUTIVAS, PISO_INTERVALO_S, TETO_BACKOFF_S
    esperas = []
    caminhos = _caminhos(MAX_FALHAS_CONSECUTIVAS)
    rotas = {c.path: (429, {}) for c in caminhos}
    _sondar_ativo(tmp_path, monkeypatch, rotas, caminhos, dormir=esperas.append)
    assert esperas
    assert all(PISO_INTERVALO_S <= e <= TETO_BACKOFF_S for e in esperas)


# --- G4: abortos deixam evento no AuditLog ---

def test_kill_switch_deixa_evento_no_log(tmp_path, monkeypatch):
    monkeypatch.setenv(gates.KILL_ENV, "1")
    _resultado, log = _sondar_ativo(tmp_path, monkeypatch, {}, [C_GIT])
    assert [linha["evento"] for linha in log.linhas] == ["abortado:kill-switch"]


def test_posse_divergente_deixa_evento_no_log(tmp_path, monkeypatch):
    """O aborto por rebind/takeover deixa rastro auditável (antes era mudo)."""
    escopo = _escopo_valido(tmp_path, monkeypatch, ip=IP_ALVO)
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    log = AuditLog(run_id="teste", escopo_hash=escopo.hash_congelado)
    _resolve_para(monkeypatch, "198.51.100.9")     # host reapontado
    resultado = sondar(escopo, ALVO, [C_GIT], client=_client({}), log=log,
                       dry_run=False, dormir=lambda _s: None)
    assert resultado.abortado_por == "posse-divergente"
    # G7: o evento agora carrega a CAUSA (aqui, takeover — o IP divergiu).
    assert [linha["evento"] for linha in log.linhas] == ["abortado:posse-divergente:takeover"]


def test_circuit_breaker_deixa_evento_no_log(tmp_path, monkeypatch):
    from webqa.sondagem import MAX_FALHAS_CONSECUTIVAS
    caminhos = _caminhos(MAX_FALHAS_CONSECUTIVAS)
    rotas = {c.path: (429, {}) for c in caminhos}
    _resultado, log = _sondar_ativo(tmp_path, monkeypatch, rotas, caminhos)
    assert "abortado:circuit-breaker" in [linha["evento"] for linha in log.linhas]


# --- G5: descarte por soft-404 é auditado (não some) ---

def test_soft_404_deixa_evento_de_descarte_no_log(tmp_path, monkeypatch):
    """200 com text/html onde se espera text/plain: sem finding, MAS com evento
    de descarte no log — hoje o descarte é silencioso (status=200 sem motivo)."""
    rotas = {"/.env": (200, {"content-type": "text/html; charset=utf-8"})}
    resultado, log = _sondar_ativo(tmp_path, monkeypatch, rotas, [C_ENV])
    assert resultado.findings == []
    assert "descartado:soft-404" in [linha["evento"] for linha in log.linhas]


# --- G6: timeout granular (connect ≠ read) ---

def test_cliente_usa_timeouts_granulares():
    from webqa.sondagem import TIMEOUT_CONNECT_S, TIMEOUT_READ_S, _cliente_padrao
    client = _cliente_padrao()
    try:
        assert client._timeout.connect == TIMEOUT_CONNECT_S
        assert client._timeout.read == TIMEOUT_READ_S
        assert client._timeout.connect != client._timeout.read   # não é escalar único
    finally:
        client.close()


# ---------- C1g: funções puras extraídas (higiene 1.7) — testáveis isoladas ----------

def test_avaliar_resposta_recuo_sinaliza_pede_recuo():
    from webqa.sondagem import _PEDE_RECUO, avaliar_resposta_em_finding
    assert avaliar_resposta_em_finding(429, "", C_GIT, "https://a/.git/HEAD") is _PEDE_RECUO
    assert avaliar_resposta_em_finding(503, "", C_GIT, "https://a/.git/HEAD") is _PEDE_RECUO


def test_avaliar_resposta_nao_2xx_e_ausencia():
    from webqa.sondagem import avaliar_resposta_em_finding
    assert avaliar_resposta_em_finding(404, "", C_GIT, "https://a/.git/HEAD") is None
    assert avaliar_resposta_em_finding(302, "", C_GIT, "https://a/.git/HEAD") is None


def test_avaliar_resposta_soft_404_sinaliza_descarte():
    from webqa.sondagem import _SOFT_404, avaliar_resposta_em_finding
    # 200 text/html onde se espera text/plain → provável soft-404
    assert avaliar_resposta_em_finding(200, "text/html", C_GIT, "https://a/.git/HEAD") is _SOFT_404


def test_avaliar_resposta_2xx_legitimo_vira_finding():
    from webqa.sondagem import avaliar_resposta_em_finding
    f = avaliar_resposta_em_finding(200, "text/plain", C_GIT, "https://a/.git/HEAD")
    assert f.fase == "C" and f.tipo == "exposicao:vcs"
    assert f.recurso == "https://a/.git/HEAD" and f.remediacao


def test_calcular_espera_backoff_piso_teto_e_exponencial():
    from webqa.sondagem import (
        BACKOFF_FATOR,
        PISO_INTERVALO_S,
        TETO_BACKOFF_S,
        calcular_espera_backoff,
    )
    assert calcular_espera_backoff(0, PISO_INTERVALO_S) == PISO_INTERVALO_S     # nunca < piso
    assert calcular_espera_backoff(1, PISO_INTERVALO_S) == PISO_INTERVALO_S * BACKOFF_FATOR
    assert calcular_espera_backoff(10, PISO_INTERVALO_S) == TETO_BACKOFF_S      # capado no teto


def test_executar_fallback_get_le_status_sem_baixar_corpo():
    from webqa.sondagem import executar_fallback_get
    pedido = {}

    def handler(request):
        pedido["method"] = request.method
        pedido["range"] = request.headers.get("range")
        return httpx.Response(206, headers={"content-type": "application/octet-stream",
                                            "content-length": "42"})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    log = AuditLog(run_id="t", escopo_hash="")
    try:
        status, ct, cl = executar_fallback_get(
            client, "https://a/.env", "https://203.0.113.7:443/.env",
            {"Host": "a"}, {"sni_hostname": "a"}, log, "https://a", "pr#1")
    finally:
        client.close()
    assert pedido["method"] == "GET" and pedido["range"] == "bytes=0-0"
    assert status == 206 and ct == "application/octet-stream" and cl == "42"
    assert log.linhas[0]["metodo"] == "GET(range)"


# ---------- C2 fatia 1: soft-404 dinâmico + canários A.4 + --multi-alvo ----------

ALVO2 = "https://alvo2-fixture.exemplo"
CANARIOS_A4 = ("/.git/HEAD", "/.env", "/backup.zip")   # contrato A.4 (estável)


def _escopo_duas_origens(tmp_path, monkeypatch, ip: str = IP_ALVO):
    p = tmp_path / "escopo-autorizado.yaml"
    corpo = "alvos:\n"
    for o in (ALVO, ALVO2):
        corpo += (f'  - origem: "{o}"\n'
                  '    autorizado_por: "danzeroum"\n'
                  f'    data: "{date.today().isoformat()}"\n'
                  '    evidencia: "pr#1"\n'
                  '    ambiente: "homologacao"\n')
    p.write_text(corpo, encoding="utf-8")
    _resolve_para(monkeypatch, ip)
    return escopo_mod.carregar(p)


# --- baseline dinâmico de soft-404 (requisição-fantasma) ---

def test_baseline_honesto_nao_guarda_assinatura_e_acha(tmp_path, monkeypatch):
    """Servidor honesto (404 ao fantasma) → sem baseline; o /.env real vira
    achado, comportamento inalterado. O fantasma consta no log."""
    rotas = {"/.env": (200, {"content-type": "application/octet-stream", "content-length": "50"})}
    resultado, log = _sondar_ativo(tmp_path, monkeypatch, rotas, [C_ENV])
    assert [f.recurso for f in resultado.findings] == [ALVO + "/.env"]
    fantasma = [linha for linha in log.linhas if linha["evento"] == "baseline-soft404"]
    assert fantasma and fantasma[0]["status"] == 404


def test_catch_all_zera_findings_e_audita_o_fantasma(tmp_path, monkeypatch):
    """Alvo catch-all (2xx a tudo, mesma assinatura não-HTML) → zero findings, e
    a requisição-fantasma consta no AuditLog."""
    def handler(request):
        return httpx.Response(200, headers={"content-type": "application/json",
                                            "content-length": "7"})

    escopo = _escopo_valido(tmp_path, monkeypatch)
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    log = AuditLog(run_id="teste", escopo_hash=escopo.hash_congelado)
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    resultado = sondar(escopo, ALVO, [C_ENV, C_BACKUP], client=client, log=log,
                       dry_run=False, dormir=lambda _s: None)
    assert resultado.findings == []
    assert any(linha["evento"] == "baseline-soft404" for linha in log.linhas)


def test_content_length_diferente_do_fantasma_ainda_e_achado(tmp_path, monkeypatch):
    """O fantasma assina (json, 7); /.env responde json com length DIFERENTE →
    não é o ruído do catch-all, segue sendo verdadeiro-positivo."""
    def handler(request):
        if request.url.path == "/.env":
            return httpx.Response(200, headers={"content-type": "application/json",
                                                "content-length": "999"})
        return httpx.Response(200, headers={"content-type": "application/json",
                                            "content-length": "7"})

    escopo = _escopo_valido(tmp_path, monkeypatch)
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    resultado = sondar(escopo, ALVO, [C_ENV], client=client, dry_run=False, dormir=lambda _s: None)
    assert [f.recurso for f in resultado.findings] == [ALVO + "/.env"]


# --- teste de SISTEMA: os canários do fixture, ponta a ponta (A.4) ---

def test_sistema_motor_acha_os_canarios_do_fixture(tmp_path, monkeypatch):
    """A.4: com a lista curada REAL, o motor acha as iscas que o fixture serve,
    de ponta a ponta (gates, posse, pino, avaliação, laço). Acoplado a
    `fixture_target.ISCAS_FASE_C` — remover uma isca de lá reprova este teste."""
    from pathlib import Path

    from fixture_target.servir import ISCAS_FASE_C
    from webqa.sondagem import carregar_caminhos

    def handler(request):
        entrada = ISCAS_FASE_C.get(request.url.path)
        if entrada is None:
            return httpx.Response(404)
        _corpo, tipo = entrada
        return httpx.Response(200, headers={"content-type": tipo})

    escopo = _escopo_valido(tmp_path, monkeypatch)
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    caminhos = carregar_caminhos(
        Path(__file__).resolve().parent.parent / "data" / "caminhos-sensiveis.yaml")
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    resultado = sondar(escopo, ALVO, caminhos, client=client, dry_run=False,
                       dormir=lambda _s: None)

    achados = {f.recurso for f in resultado.findings}
    for path in CANARIOS_A4:
        assert ALVO + path in achados, f"motor não achou o canário {path}"
    assert len(resultado.findings) == len(CANARIOS_A4)


# --- --multi-alvo: só as origens do escopo carregado ---

def test_multialvo_sonda_todas_as_origens_do_escopo(tmp_path, monkeypatch):
    from webqa.sondagem import sondar_multialvo
    escopo = _escopo_duas_origens(tmp_path, monkeypatch)
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    rotas = {"/.git/HEAD": (200, {"content-type": "text/plain"})}
    resultados = sondar_multialvo(escopo, [C_GIT], client=_client(rotas),
                                  dry_run=False, dormir=lambda _s: None)
    assert {r.alvo for r in resultados} == {ALVO, ALVO2}
    assert all(len(r.findings) == 1 for r in resultados)   # cada alvo achou a isca


def test_multialvo_alvo_sem_posse_nao_impede_os_outros(tmp_path, monkeypatch):
    from webqa.sondagem import sondar_multialvo
    escopo = _escopo_duas_origens(tmp_path, monkeypatch)     # snapshot: ambos em IP_ALVO
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")

    def _resolver(h, p, *a, **k):     # ALVO segue; ALVO2 reaponta (takeover)
        ip = IP_ALVO if h == "alvo-fixture.exemplo" else "198.51.100.9"
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))]
    monkeypatch.setattr(socket, "getaddrinfo", _resolver)

    rotas = {"/.git/HEAD": (200, {"content-type": "text/plain"})}
    resultados = sondar_multialvo(escopo, [C_GIT], client=_client(rotas),
                                  dry_run=False, dormir=lambda _s: None)
    por_alvo = {r.alvo: r for r in resultados}
    assert por_alvo[ALVO2].abortado_por == "posse-divergente"
    assert por_alvo[ALVO].abortado_por == "" and por_alvo[ALVO].findings


# ---------- C2 fatia 2: poda curada + procedencia obrigatória no carregamento ----------

def test_poda_aceitos_entram_na_lista_curada():
    """Os aceitos da poda C2 entram; os públicos-por-design NÃO entram."""
    from pathlib import Path

    from webqa.sondagem import carregar_caminhos
    real = Path(__file__).resolve().parent.parent / "data" / "caminhos-sensiveis.yaml"
    paths = {c.path for c in carregar_caminhos(real)}
    for aceito in ("/.env.local", "/docker-compose.yml", "/bundle.js.map"):
        assert aceito in paths, f"poda: {aceito} deveria entrar"
    for publico in ("/docs", "/openapi.json", "/redoc", "/api/v1/users"):
        assert publico not in paths, f"poda: {publico} é público por design, não entra"


def test_carregar_reprova_caminho_sem_procedencia(tmp_path):
    """Invariante de carregamento C2: caminho curado sem procedencia falha."""
    from webqa.sondagem import carregar_caminhos
    p = tmp_path / "sem-proc.yaml"
    p.write_text(
        '- path: "/.env"\n  categoria: "configuracao"\n  severidade: "alta"\n'
        '  content_type_esperado: "application/octet-stream"\n  remediacao: "corrija"\n',
        encoding="utf-8")
    with pytest.raises(ValueError, match="procedencia"):
        carregar_caminhos(p)


def test_categoria_fonte_e_valida_para_source_map(tmp_path):
    """A poda introduziu a categoria 'fonte' (source maps)."""
    c = CaminhoSensivel("/x.map", "fonte", "media", "application/json", "r", procedencia="CWE-540")
    assert c.categoria == "fonte"


# ---------- C3a: liga SARIF + baseline + laudo ao CLI (main) ----------

def _cli_setup(tmp_path, monkeypatch, rotas):
    """Escopo+caminhos em disco, posse dublada, e `_cliente_padrao` → MockTransport.
    Devolve os argumentos base do CLI (sem os flags de saída)."""
    _escopo_valido(tmp_path, monkeypatch)                 # escreve yaml + dubla getaddrinfo
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    caminhos = tmp_path / "caminhos.yaml"
    caminhos.write_text(
        '- path: "/.git/HEAD"\n  categoria: "vcs"\n  severidade: "alta"\n'
        '  content_type_esperado: "text/plain"\n  remediacao: "Remova o .git."\n'
        '  procedencia: "OWASP WSTG-CONF-004"\n', encoding="utf-8")
    monkeypatch.setattr(
        "webqa.sondagem._cliente_padrao",
        lambda: httpx.Client(transport=_transporte(rotas), follow_redirects=False))
    return ["--alvo", ALVO, "--executar",
            "--escopo", str(tmp_path / "escopo-autorizado.yaml"),
            "--caminhos", str(caminhos)]


_CHAVE_GIT = f"exposicao:vcs|{ALVO}/.git/HEAD"


def test_cli_grava_saida_e_sarif_e_reprova_achado_novo(tmp_path, monkeypatch):
    base = _cli_setup(tmp_path, monkeypatch, {"/.git/HEAD": (200, {"content-type": "text/plain"})})
    saida, sarif, baseline = (tmp_path / "r.json", tmp_path / "r.sarif", tmp_path / "b.yaml")
    rc = sondagem_mod.main(base + ["--saida", str(saida), "--sarif", str(sarif),
                                   "--baseline", str(baseline)])
    assert rc == 3                                        # baseline ausente → achado NOVO reprova
    dados = json.loads(saida.read_text())
    assert dados["alvos"][0]["findings"][0]["recurso"] == ALVO + "/.git/HEAD"
    assert json.loads(sarif.read_text())["version"] == "2.1.0"


def test_cli_baseline_persistente_nao_reprova(tmp_path, monkeypatch):
    base = _cli_setup(tmp_path, monkeypatch, {"/.git/HEAD": (200, {"content-type": "text/plain"})})
    baseline = tmp_path / "b.yaml"
    baseline.write_text(f'achados:\n  - chave: "{_CHAVE_GIT}"\n    estado: "persistente"\n',
                        encoding="utf-8")
    assert sondagem_mod.main(base + ["--baseline", str(baseline)]) == 0


def test_cli_sem_flags_de_saida_sai_0_e_nao_grava(tmp_path, monkeypatch):
    base = _cli_setup(tmp_path, monkeypatch, {"/.git/HEAD": (200, {"content-type": "text/plain"})})
    assert sondagem_mod.main(base) == 0
    assert not (tmp_path / "r.json").exists()
    assert not (tmp_path / "r.sarif").exists()


def test_cli_sarif_nao_vaza_ip_cru_no_laudo(tmp_path, monkeypatch):
    """O laudo/SARIF usa a URL LÓGICA (hostname), nunca o IP pinado."""
    base = _cli_setup(tmp_path, monkeypatch, {"/.git/HEAD": (200, {"content-type": "text/plain"})})
    saida, sarif = tmp_path / "r.json", tmp_path / "r.sarif"
    sondagem_mod.main(base + ["--saida", str(saida), "--sarif", str(sarif)])
    for arq in (saida, sarif):
        assert IP_ALVO not in arq.read_text()            # IP pinado nunca no laudo
