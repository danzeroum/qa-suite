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

import socket
from datetime import date

import httpx
import pytest

from webqa import escopo as escopo_mod
from webqa import gates
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
    # o 3xx não é achado e não foi seguido (um único request por caminho)
    assert [p for _m, p, _r in registro] == ["/.git/HEAD", "/.env"]
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
    assert log.linhas == ()                 # nenhuma requisição registrada
    assert resultado.inconclusivo is True


def test_kill_switch_no_meio_do_laco_para_o_run(tmp_path, monkeypatch):
    chamadas = {"n": 0}

    def _kill_na_segunda():
        chamadas["n"] += 1
        return chamadas["n"] >= 2           # False, depois True
    monkeypatch.setattr("webqa.sondagem.kill_switch_active", _kill_na_segunda)

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

    assert len(log.linhas) == resultado.executado == 2
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


# ---------- specs adiadas ao C1b (contrato registrado, ainda não implementado) ----------

@pytest.mark.xfail(strict=True, reason="C1b: fallback GET Range: bytes=0-0 quando HEAD é 405")
def test_head_405_faz_fallback_range_get(tmp_path, monkeypatch):
    """Servidor que rejeita HEAD (405) deve ser reprovado por um GET mínimo
    (`Range: bytes=0-0`), sem baixar o corpo. Ainda não implementado."""
    registro = []
    rotas = {"/.git/HEAD": (405, {})}
    _sondar_ativo(tmp_path, monkeypatch, rotas, [C_GIT], registro=registro)
    metodos = {m for m, _p, _r in registro}
    ranges = [r for _m, _p, r in registro]
    assert "GET" in metodos and "bytes=0-0" in ranges


@pytest.mark.xfail(strict=True, reason="C1b: backoff em 429/503 antes de continuar")
def test_429_dispara_backoff(tmp_path, monkeypatch):
    """Um 429 deve disparar uma espera MAIOR que o piso antes do próximo probe.
    Ainda não implementado (hoje o intervalo é sempre o piso)."""
    intervalos = []
    rotas = {"/.git/HEAD": (429, {}), "/.env": (404, {})}
    _sondar_ativo(tmp_path, monkeypatch, rotas, [C_GIT, C_ENV], dormir=intervalos.append)
    assert any(i > PISO_INTERVALO_S for i in intervalos), "429 deveria ampliar a espera"
