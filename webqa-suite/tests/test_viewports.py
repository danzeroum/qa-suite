"""VERIFICAÇÃO: a matriz de viewports é fail-closed e não inventa execução.

O que se prova aqui é a mesma propriedade que `tests/test_navegador.py` prova
para as engines: um typo na variável de ambiente REPROVA, em vez de silenciar a
execução inteira. "Rodou zero viewports e passou" é a forma de verde falso mais
cara que esta suíte pode produzir, porque nada fica vermelho.

Sem rede e sem navegador: `opcoes_de_contexto` é pura, e os perfis vêm de YAML.
"""
import pytest

from webqa.viewports import (
    ENV_VIEWPORTS,
    VIEWPORTS_PADRAO,
    Viewport,
    carregar_perfis,
    opcoes_de_contexto,
    viewports_configurados,
)

pytestmark = pytest.mark.verification

_PERFIS = {
    "mobile": Viewport("mobile", 390, 844, mobile=True, toque=True),
    "desktop": Viewport("desktop", 1366, 768),
    "ultrawide": Viewport("ultrawide", 2560, 1080),
}


def _env(valor=None):
    return {} if valor is None else {ENV_VIEWPORTS: valor}


# ---------- Fail-closed ----------

def test_viewport_desconhecido_e_erro_e_nomeia_os_validos():
    """Typo não vira filtro silencioso, e a mensagem diz o que era válido.

    Sem a lista na mensagem, quem escreveu `mobil` no cron descobre o erro mas
    não descobre o acerto — e tenta de novo às cegas na noite seguinte.
    """
    with pytest.raises(ValueError) as erro:
        viewports_configurados(_env("mobil"), _PERFIS)
    assert "mobil" in str(erro.value)
    assert "mobile" in str(erro.value) and "desktop" in str(erro.value)


def test_um_nome_errado_no_meio_reprova_a_lista_inteira():
    """Não roda os válidos e ignora o inválido: a execução pedida não existe."""
    with pytest.raises(ValueError):
        viewports_configurados(_env("mobile,ultawide,desktop"), _PERFIS)


def test_valor_so_com_virgulas_e_erro_nao_cai_para_o_default():
    """Configuração sem sentido não pode virar execução silenciosa — cair para o
    default esconderia exatamente o engano que o fail-closed existe para expor."""
    with pytest.raises(ValueError):
        viewports_configurados(_env(" , , "), _PERFIS)


# ---------- Seleção ----------

def test_default_sem_env_e_mobile_mais_desktop():
    escolhidos = viewports_configurados(_env(), _PERFIS)
    assert tuple(v.nome for v in escolhidos) == VIEWPORTS_PADRAO


def test_env_vazia_cai_para_o_default():
    """Variável definida como string vazia é o mesmo que não definida."""
    assert viewports_configurados(_env("  "), _PERFIS) == viewports_configurados(_env(), _PERFIS)


def test_ordem_de_declaracao_preservada():
    """A ordem escrita é a ordem executada: o laudo sai na sequência que quem
    configurou pediu, e não numa ordenação que ninguém declarou."""
    escolhidos = viewports_configurados(_env("desktop,mobile"), _PERFIS)
    assert [v.nome for v in escolhidos] == ["desktop", "mobile"]


def test_repeticao_nao_roda_duas_vezes():
    escolhidos = viewports_configurados(_env("mobile,desktop,mobile"), _PERFIS)
    assert [v.nome for v in escolhidos] == ["mobile", "desktop"]


def test_nome_e_normalizado_para_minusculas():
    assert [v.nome for v in viewports_configurados(_env("MOBILE"), _PERFIS)] == ["mobile"]


# ---------- Perfis do YAML ----------

def test_perfis_reais_carregam_e_trazem_os_defaults():
    """O YAML versionado tem de conter os perfis que o default nomeia — senão o
    default reprova em toda execução, e o erro só aparece na primeira noite."""
    perfis = carregar_perfis()
    for nome in VIEWPORTS_PADRAO:
        assert nome in perfis, f"gui-perfis.yaml não declara o viewport {nome!r}"
    assert perfis["mobile"].largura == 390 and perfis["mobile"].mobile


def test_perfil_de_reflow_segue_a_norma():
    """320 CSS px é o que a WCAG 1.4.10 exige. Mudar esse número é mudar a
    norma que o check afirma medir, e isso não pode acontecer por descuido."""
    assert carregar_perfis()["reflow_aa"].largura == 320


def test_perfil_sem_dimensao_e_erro_de_configuracao(tmp_path):
    caminho = tmp_path / "perfis.yaml"
    caminho.write_text("viewports:\n  quebrado: {width: 100}\n", encoding="utf-8")
    with pytest.raises(ValueError) as erro:
        carregar_perfis(caminho)
    assert "quebrado" in str(erro.value)


def test_yaml_sem_viewport_nenhum_e_erro(tmp_path):
    caminho = tmp_path / "perfis.yaml"
    caminho.write_text("viewports: {}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        carregar_perfis(caminho)


# ---------- Opções de contexto (função pura) ----------

def test_opcoes_traduzem_o_viewport():
    opcoes = opcoes_de_contexto(_PERFIS["mobile"])
    assert opcoes["viewport"] == {"width": 390, "height": 844}
    assert opcoes["is_mobile"] is True and opcoes["has_touch"] is True


def test_desktop_nao_manda_is_mobile():
    """Não é economia de bytes: o Firefox RECUSA `is_mobile`, e mandá-lo sempre
    quebraria todo perfil de desktop naquela engine por um campo que ele nem usa."""
    opcoes = opcoes_de_contexto(_PERFIS["desktop"])
    assert "is_mobile" not in opcoes and "has_touch" not in opcoes


def test_sem_viewport_nao_inventa_dimensao():
    """Ausência de perfil é ausência: o contexto herda o default do navegador,
    e não um tamanho que a suíte tenha escolhido sem ninguém pedir."""
    assert "viewport" not in opcoes_de_contexto(None)


def test_extras_passam_adiante_e_vencem():
    opcoes = opcoes_de_contexto(_PERFIS["mobile"], color_scheme="dark", is_mobile=False)
    assert opcoes["color_scheme"] == "dark"
    assert opcoes["is_mobile"] is False, "o que o check pede explicitamente vence o perfil"
