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
