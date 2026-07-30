"""VERIFICAÇÃO: o compose separa quem tem a caneta de quem não tem.

A VPS roda dois serviços na MESMA imagem, e a diferença entre eles não é
cosmética — é de autoridade:

* `estabilidade` monta a deploy key e declara `WEBQA_ORIGEM=vps`: escreve o
  ledger, e o que ele registra destrava (ou não) a Fase 2;
* `campanha` mede alvos de terceiros e **não pode** tocar o ledger.

Se um refactor der segredo ou `WEBQA_ORIGEM` à campanha, uma medição contra site
alheio passa a contar como evidência de estabilidade do ambiente oficial — e a
sequência de 10 noites deixa de significar o que diz. Isso é exatamente o tipo de
erro que ninguém percebe lendo o YAML no meio de um PR grande.

Sem daemon e sem rede: o arquivo é lido como dado. `docker compose config` roda
por cima quando o CLI existe, e é pulado quando não.
"""
from __future__ import annotations

import shutil
import subprocess  # nosec B404
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.verification

COMPOSE = Path(__file__).resolve().parent.parent.parent / "docker" / "compose.yml"


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def campanha(compose) -> dict:
    return compose["services"]["campanha"]


@pytest.fixture(scope="module")
def estabilidade(compose) -> dict:
    return compose["services"]["estabilidade"]


def test_os_dois_servicos_existem(compose):
    assert set(compose["services"]) == {"estabilidade", "campanha"}


def test_mesma_imagem_nos_dois_servicos(campanha, estabilidade):
    """O ambiente medido tem de ser um só — imagens diferentes mediriam dois."""
    assert campanha["image"] == estabilidade["image"]


def test_campanha_nao_monta_segredo_nenhum(campanha):
    """A campanha não tem a caneta: nenhum caminho de segredo montado."""
    volumes = campanha.get("volumes") or []
    for volume in volumes:
        assert "secret" not in str(volume).lower(), f"volume suspeito na campanha: {volume}"
        assert "deploy_key" not in str(volume), f"deploy key montada na campanha: {volume}"
    assert not campanha.get("secrets"), "campanha não declara secrets do compose"


def test_campanha_nao_declara_origem(campanha):
    """Sem WEBQA_ORIGEM nada aqui pode ser lido como evidência do ambiente oficial.

    O classificador degrada origem desconhecida para "local", que não conta —
    mas a campanha nem chega a chamá-lo. A ausência é a primeira barreira.
    """
    assert "WEBQA_ORIGEM" not in (campanha.get("environment") or {})


def test_campanha_nao_usa_o_entrypoint_do_noturno(campanha):
    """O entrypoint do noturno atualiza o repo e commita; a campanha só mede."""
    entrypoint = campanha.get("entrypoint")
    assert entrypoint and "campanha.py" in " ".join(entrypoint)
    assert "entrypoint.sh" not in " ".join(entrypoint)


def test_volume_da_campanha_fica_fora_da_arvore_da_suite(campanha):
    """No HOST o volume é docker/report-campanha — fora de webqa-suite/.

    É o que impede a campanha de sujar o `git status` da VPS, que é o mesmo
    repositório de onde o noturno commita o ledger.
    """
    volumes = campanha.get("volumes") or []
    assert len(volumes) == 1, "a campanha monta exatamente um volume: a saída"
    host, destino = str(volumes[0]).split(":")[:2]
    assert host == "./report-campanha"
    assert "webqa-suite" not in host
    # E no CONTAINER aponta para o destino padrão do runner, sem o que o
    # consolidado nasceria dentro da imagem e morreria com o `--rm`.
    assert destino == "/app/webqa-suite/report/campanha"


def test_saida_da_campanha_e_ignorada_no_git():
    gitignore = (COMPOSE.parent.parent / ".gitignore").read_text(encoding="utf-8")
    assert "docker/report-campanha/" in gitignore


def test_estabilidade_continua_com_os_segredos(estabilidade):
    """Regressão ao contrário: separar os papéis não pode desarmar o noturno."""
    volumes = " ".join(str(v) for v in estabilidade.get("volumes") or [])
    assert "/run/secrets/deploy_key:ro" in volumes
    assert "/run/secrets/known_hosts:ro" in volumes
    assert estabilidade["environment"]["WEBQA_ORIGEM"] == "vps"


def test_campanha_mantem_as_guardas_de_runtime_do_chromium(campanha):
    """shm pequeno derruba o Chromium; sem init sobram zumbis."""
    assert campanha.get("shm_size") == "1gb"
    assert campanha.get("init") is True
    assert "no-new-privileges:true" in (campanha.get("security_opt") or [])


def test_campanha_smoke_e_minima_e_de_um_alvo_so():
    """O passo 6 do smoke prova que MEDE; não serve para medir."""
    caminho = Path(__file__).resolve().parent.parent / "campanha-smoke.yaml"
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    assert dados["repeticoes"] == 1
    assert len(dados["alvos"]) == 1


def test_docker_compose_config_valida():
    """Validação de sintaxe pelo próprio Compose — sem daemon, só parsing."""
    if not shutil.which("docker"):
        pytest.skip("CLI do docker ausente neste ambiente.")
    resultado = subprocess.run(  # nosec B603
        ["docker", "compose", "-f", str(COMPOSE), "config"],
        capture_output=True, text=True, timeout=120, check=False)
    if resultado.returncode != 0 and "compose" in resultado.stderr.lower() \
            and "unknown" in resultado.stderr.lower():
        pytest.skip("Compose v2 indisponível neste ambiente.")
    assert resultado.returncode == 0, f"compose config falhou:\n{resultado.stderr[:500]}"
    assert "campanha" in resultado.stdout
