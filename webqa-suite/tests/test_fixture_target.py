"""VERIFICAÇÃO (unidade): o alvo fixture serve o que promete e sobe sem flake.

Rápido e sem navegador — roda no quality-gate. O teste de SISTEMA (contrato
completo da dimensão) está em tests/test_alvo_fixture.py e exige Chromium.
"""
import json
import socket
import urllib.request
from pathlib import Path

import pytest

from fixture_target import servir
from fixture_target.paginas_gui import PAGINAS_GUI
from fixture_target.servir import (
    CDN_FALSO,
    MARCA_ISCA,
    TRACKER,
    AlvoFixture,
    identidade,
)

pytestmark = pytest.mark.verification

CONTRATO = Path(__file__).resolve().parent.parent / "fixture_target" / "esperado.json"


def _get(url: str):
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310 - 127.0.0.1 fixo
        return resp.status, resp.read().decode("utf-8"), resp.headers


# ---------- Subida do servidor ----------

def test_porta_efemera_por_padrao():
    with AlvoFixture() as a, AlvoFixture() as b:
        assert a.porta != b.porta
        assert a.url.startswith("http://127.0.0.1:")


def test_porta_ocupada_nao_vira_flake():
    """Porta ocupada é problema de ambiente; o fixture contorna e serve."""
    bloqueio = socket.socket()
    bloqueio.bind(("127.0.0.1", 0))
    ocupada = bloqueio.getsockname()[1]
    bloqueio.listen(1)
    try:
        with AlvoFixture(porta=ocupada) as alvo:
            assert alvo.porta != ocupada
            status, corpo, _ = _get(alvo.url)
            assert status == 200 and "Loja Fixture" in corpo
    finally:
        bloqueio.close()


# ---------- Violações servidas ----------

@pytest.fixture(scope="module")
def home():
    with AlvoFixture() as alvo:
        status, corpo, headers = _get(alvo.url + "/")
        assert status == 200
        return corpo, headers


def test_pii_na_query_string(home):
    corpo, _ = home
    assert "?email=joao@exemplo.com" in corpo


def test_form_pessoal_em_get(home):
    corpo, _ = home
    assert 'method="get"' in corpo and 'name="email"' in corpo


def test_imagem_sem_alt(home):
    """A LOGO é a única imagem sem alt — e continua sendo.

    A asserção olha a tag da logo, não "nenhum alt na página": o fixture ganhou
    imagens para a dimensão `seguranca` (SVG executável, foto com EXIF) que TÊM
    alt de propósito, porque não são violações de acessibilidade. Exigir zero
    `alt=` no documento inteiro amarraria a violação de acessibilidade ao
    conteúdo de outra dimensão.
    """
    corpo, _ = home
    logo = next(linha for linha in corpo.splitlines() if 'src="/logo.png"' in linha)
    assert logo.startswith("<img") and "alt=" not in logo
    outras = [linha for linha in corpo.splitlines()
              if linha.startswith("<img") and 'src="/logo.png"' not in linha]
    assert outras and all("alt=" in linha for linha in outras), (
        "só a logo pode estar sem alt: uma segunda imagem sem alt mudaria a "
        "contagem que o contrato do fixture cobra")


def test_script_de_terceiro_sem_sri(home):
    corpo, _ = home
    assert CDN_FALSO in corpo and "integrity=" not in corpo
    assert CDN_FALSO.endswith(".invalid/jquery-3.7.1.min.js"), (
        "o CDN do fixture precisa ser .invalid (RFC 2606): sem dependência externa real"
    )


def test_tracker_disparado_sem_consentimento(home):
    corpo, _ = home
    assert TRACKER in corpo and "googletagmanager.com" in TRACKER


def test_cookie_de_730_dias_e_cookie_de_sessao(home):
    _, headers = home
    cookies = headers.get_all("Set-Cookie") or []
    assert any("_ga=" in c and "Max-Age=63072000" in c for c in cookies)
    assert any(c.startswith("sessionid=") and "Max-Age" not in c for c in cookies)


def test_politica_e_conforme(home):
    """O fixture é não conforme em consentimento, mas CONFORME em transparência."""
    with AlvoFixture() as alvo:
        status, corpo, _ = _get(alvo.url + "/privacidade")
    assert status == 200 and len(corpo) > 1500
    for termo in ("acesso", "correcao", "eliminacao", "portabilidade", "revogar", "DPO"):
        assert termo in corpo, f"política do fixture sem '{termo}'"


def test_recurso_desconhecido_responde_404():
    with AlvoFixture() as alvo:
        try:
            _get(alvo.url + "/.well-known/security.txt")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        else:
            pytest.fail("security.txt deveria faltar no fixture (ausência é xfail informativo)")


# ---------- Iscas de exposição (Fase C) — servidas, inertes, sem segredo real ----------
#
# Este arquivo VALIDA que a isca é servida; a DETECÇÃO em si é do PR-C1a (o motor
# ainda não existe). Nível de sistema: o alvo fabricado responde ao probe direto.

def _get_bytes(url: str):
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310 - 127.0.0.1 fixo
        return resp.status, resp.read(), resp.headers


def test_isca_env_servida_com_marcador_e_valores_fake():
    with AlvoFixture() as alvo:
        status, corpo, _ = _get(alvo.url + "/.env")
    assert status == 200
    assert MARCA_ISCA in corpo, "corpo tem de trazer o marcador de isca"
    assert "exemplo-fake" in corpo, "valores são explicitamente falsos"


def test_isca_git_head_servida():
    with AlvoFixture() as alvo:
        status, corpo, _ = _get(alvo.url + "/.git/HEAD")
    assert status == 200
    assert corpo.startswith("ref:"), "assinatura de um .git/HEAD exposto"


def test_isca_backup_zip_servida_e_valida():
    with AlvoFixture() as alvo:
        status, corpo, headers = _get_bytes(alvo.url + "/backup.zip")
    assert status == 200
    assert headers.get("Content-Type") == "application/zip"
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(corpo)) as z:      # zip válido de verdade
        assert z.namelist() == ["leia.txt"]
        assert MARCA_ISCA in z.read("leia.txt").decode("utf-8")


def test_soft_404_ancora():
    """Caminho benigno inexistente → 404. Âncora contra falso positivo de
    soft-404 quando o motor de C1 existir."""
    with AlvoFixture() as alvo:
        try:
            _get(alvo.url + "/nao-existe")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        else:
            pytest.fail("caminho inexistente deveria retornar 404")


def test_iscas_nao_sao_linkadas_no_home():
    """São alcançáveis só por probe DIRETO — nada no HOME aponta para elas, senão
    um check passivo as descobriria e o contrato de esperado.json mudaria."""
    for caminho in ("/.env", "/.git", "/backup.zip"):
        assert caminho not in servir.HOME, f"{caminho} não pode estar linkado no HOME"


def test_iscas_nao_tem_segredo_real():
    """Grep semântico: o motor de detecção da casa não acha segredo nas iscas —
    são valores fake, não credenciais de verdade."""
    from webqa.sanitize import encontrar_segredos

    assert encontrar_segredos(servir.ENV_ISCA) == []
    assert encontrar_segredos(servir.GIT_HEAD) == []


def test_iscas_ficam_fora_da_identidade(monkeypatch):
    """Trocar uma isca NÃO muda a identidade do alvo: elas não são parte do
    contrato passivo, então não resetam o ledger de estabilidade."""
    antes = identidade()
    monkeypatch.setattr(servir, "ENV_ISCA", "API_KEY=outra-coisa-fake\n")
    monkeypatch.setattr(servir, "GIT_HEAD", "ref: refs/heads/outro\n")
    assert identidade() == antes


# ---------- Violações de GUI (OS-40) ----------
#
# Um teste por violação, e cada um nomeia o check FUTURO que vai lê-la. Página
# que "reprova de propósito" sem ninguém lendo é a classe de defeito "a garantia
# existe, a ligação não" (docs/PROXIMOS-PASSOS.md §2.10) — dentro justamente do
# PR que existe para preveni-la.

@pytest.mark.parametrize(("marcador", "check"), [
    ("min-width: 900px", "GUI-RESP-01 (reflow a 320px, WCAG 1.4.10)"),
    ("height: 24px; overflow: hidden", "GUI-TIPO-01 (zoom 200%, WCAG 1.4.4)"),
    (".sem-foco:focus { outline: none", "GUI-FOCO-01 (foco visível, WCAG 2.4.7)"),
    ('tabindex="4">Comprar', "GUI-FOCO-02 (ordem de tabulação, WCAG 2.4.3)"),
    # Quatro botões em ordem reversa geram TRÊS inversões: o limiar do check é
    # folgado (2) de propósito, e um par só passaria sem exercer nada.
    ('tabindex="1">Voltar', "GUI-FOCO-02 (o limiar folgado precisa ser ultrapassado)"),
    ("position: fixed", "GUI-FOCO-03 (foco obscurecido, WCAG 2.4.11)"),
    ("width: 16px; height: 16px", "GUI-ALVO-01 (alvo de toque, WCAG 2.5.8)"),
    # Dois alvos colados, e não um: um alvo pequeno SOZINHO é conforme pela
    # exceção de espaçamento da própria norma. Foi o check que mostrou isso.
    (".alvo-pequeno + .alvo-pequeno { margin-left: 2px; }",
     "GUI-ALVO-01 (a exceção de espaçamento precisa cair)"),
    ("passa a ocupar duas quando o usuario amplia",
     "GUI-TIPO-01 (o texto precisa CABER a 100% para poder sumir a 200%)"),
    ("animation: girar 2s linear infinite", "GUI-MOV-01 (reduced-motion, WCAG 2.3.3)"),
    ("prefers-color-scheme: dark", "GUI-CONTR-01 (contraste no tema escuro, WCAG 1.4.3)"),
    ("carregando pedidos...", "GUI-RESIL-01 (falha de API sem tratamento)"),
])
def test_home_serve_a_violacao_de_gui(home, marcador, check):
    """Cada violação de GUI está no HTML que a home realmente serve."""
    corpo, _ = home
    assert marcador in corpo, f"violação ausente da home — {check} não teria o que detectar"


def _consumidores_da_api(corpo: str) -> list[str]:
    """As cadeias `fetch("/gui/api/pedidos")…;` da home, uma por consumidor.

    Recortar por `</script>` juntava os dois num trecho só — e foi o que este
    par de testes pegou quando o segundo consumidor nasceu (OS-47): a guarda do
    primeiro passou a ler o `.catch` do segundo e acusou tratamento onde não há.
    """
    partes = corpo.split('fetch("/gui/api/pedidos")')[1:]
    return [parte.split("});", 1)[0] for parte in partes]


def test_home_consome_a_api_sem_tratar_falha(home):
    """GUI-RESIL-02: o primeiro fetch não tem `.catch` nem checa `r.ok`.

    É metade da violação. O alvo responde 200; quem força o erro é o check, no
    cliente (`page.route`) — e aí o parágrafo fica preso em "carregando", que é
    o SILÊNCIO: a página não avisa nada, e o desfecho é `xfail`.
    """
    corpo, _ = home
    trecho = _consumidores_da_api(corpo)[0]
    assert ".catch" not in trecho, "o fetch trata a falha — não há violação a detectar"
    assert "r.ok" not in trecho, "o fetch checa o status — não há violação a detectar"


def test_home_tambem_despeja_o_erro_cru_na_tela(home):
    """GUI-RESIL-01/03: a outra metade, e a que produz `failed` determinístico.

    Sem ela o fixture só exerceria o silêncio, e os quatro checks terminariam em
    `xfail` — nenhum entraria no contrato, e a classe "termo técnico vazado", que
    é a mais grave das três, nunca seria exercida contra alvo de verdade.

    O anti-padrão é literal e comum: `catch(e => elemento.textContent = e)`.
    Medido no navegador: sob 500 com corpo HTML a tela mostra
    `SyntaxError: Unexpected token '<'`.
    """
    corpo, _ = home
    consumidores = _consumidores_da_api(corpo)
    assert len(consumidores) == 2, "a home tem dois consumidores da mesma API"
    assert '.catch' in consumidores[1], "o segundo consumidor trata a falha…"
    assert 'textContent = "Erro: " + e' in consumidores[1], "…e despeja o erro cru"
    assert 'id="estoque"' in corpo, "o elemento que recebe o erro precisa existir"


def test_app_js_bloqueia_a_thread_principal():
    """GUI-PERF-01: seis blocos acima de 50ms — long tasks e TBT observáveis."""
    with AlvoFixture() as alvo:
        status, corpo, _ = _get(alvo.url + "/app.js")
    assert status == 200
    assert "blocosRestantes = 6" in corpo and "Date.now() + 110" in corpo
    # Reagendado, não num laço só: seis iterações síncronas seriam UMA long
    # task de 660ms para o navegador, e a API reportaria 1, não 6.
    assert "setTimeout(bloquearThreadPrincipal, 0)" in corpo


@pytest.mark.parametrize(("caminho", "marcador"), [
    ("/gui/estados", 'onblur="this.focus()"'),      # GUI-FOCO-04: armadilha de foco
    ("/gui/estados", "falso-desabilitado"),         # GUI-ESTADO-03: sem disabled
    ("/gui/estados", "campo-erro"),                 # GUI-ESTADO-01: erro só por cor
    ("/gui/api/pedidos", '"total": 3'),             # resposta estável que a home consome
])
def test_pagina_de_gui_responde_com_a_violacao(caminho, marcador):
    with AlvoFixture() as alvo:
        status, corpo, _ = _get(alvo.url + caminho)
    assert status == 200
    assert marcador in corpo


@pytest.mark.parametrize("marcador", [
    "AbortController",            # pedido que não responde vira falha tratada
    "if (!r.ok)",                 # 500 com corpo válido não é sucesso
    "Tente novamente",            # a mensagem é para gente, e usa o vocabulário
    "addEventListener('offline'", # o navegador avisa; esta página escuta
    "<main>",                     # há conteúdo principal: não é tela branca
])
def test_pagina_resiliente_e_o_lado_CONFORME_do_contrato(marcador):
    """Os quatro checks de resiliência precisam ser vistos PASSANDO em algum lugar.

    Contra `/privacidade` eles pulam (aquela página não faz chamada nenhuma), e
    check que nunca foi visto passando é check de que ninguém sabe se reprova por
    regressão ou por natureza. Mesma razão de `test_transparencia_passa_no_fixture`
    existir: o contrato precisa provar os dois lados, senão um check que reprova
    tudo passaria por "funcionando".

    Vive em `paginas_gui/`, logo FORA de `identidade()` — o lado conforme não
    custa reinício de sequência no ledger.
    """
    with AlvoFixture() as alvo:
        status, corpo, _ = _get(alvo.url + "/gui/resiliente")
    assert status == 200
    assert marcador in corpo


def test_pagina_resiliente_nao_e_linkada_na_home():
    """Omissão deliberada, e o teste existe para que ninguém a "conserte".

    Um `<a>` a mais na home mudaria a contagem de alvos de toque e a caminhada de
    foco — que são exatamente o que três checks do contrato medem. Esta página é
    endereçada direto, como alvo (`WEBQA_TARGET_URL`), no papel que
    `/privacidade` já cumpre no smoke.
    """
    with AlvoFixture() as alvo:
        _, corpo, _ = _get(alvo.url)
    assert 'href="/gui/resiliente"' not in corpo


def test_galeria_de_gui_e_alcancavel_por_link(home):
    """A galeria é LINKADA na home: o crawl passivo chega nela seguindo o que a
    aplicação oferece, e nenhum check precisa fabricar endereço para alcançá-la.

    É a diferença entre esta página e as iscas da Fase C, que são deliberadamente
    não linkadas — e o teste ao lado (`test_iscas_nao_sao_linkadas_no_home`)
    fixa o outro lado da mesma fronteira.
    """
    corpo, _ = home
    assert 'href="/gui/estados"' in corpo


def test_paginas_de_gui_ficam_fora_da_identidade(monkeypatch):
    """Mexer numa página de GUI NÃO reinicia a caminhada do ledger.

    Mesma razão das iscas: o ledger mede o contrato passivo, e estas páginas não
    são observadas por nenhum check dele. Incluí-las cobraria um reinício da
    sequência sem-flake por conteúdo que ninguém mede.
    """
    antes = identidade()
    monkeypatch.setitem(PAGINAS_GUI, "/gui/estados", (b"<html>outra coisa</html>", "text/html"))
    monkeypatch.setattr(servir, "PAGINAS_GUI", dict(PAGINAS_GUI))
    assert identidade() == antes


def test_violacao_de_gui_na_home_muda_a_identidade(monkeypatch):
    """O outro lado da fronteira: o que está no hash reinicia a sequência.

    Sem este par, o teste acima passaria também se `identidade()` tivesse parado
    de observar QUALQUER COISA — provaria a ausência sem provar a presença.
    """
    antes = identidade()
    monkeypatch.setattr(servir, "APP_JS",
                    servir.APP_JS.replace("blocosRestantes = 6", "blocosRestantes = 2"))
    assert identidade() != antes


def test_contrato_cobra_os_checks_de_gui_existentes():
    """O contrato lista os checks de `gui` que JÁ existem — nem mais, nem menos.

    Este teste nasceu na OS-40 exigindo o contrário: `esperado.json` INTACTO,
    porque nenhum check de `gui` existia e uma entrada para teste inexistente
    seria o id fantasma que `tests/test_alvo_fixture.py` reprova. Ele cumpriu o
    papel e agora afirma o outro lado da mesma regra: check que nasce entra no
    contrato no MESMO PR, senão o alvo passa a reprovar sem ninguém ter
    declarado que devia.

    A lista é explícita de propósito. Derivá-la de um glob sobre `checks/gui/`
    faria a cobertura encolher junto com o código removido, fechando o furo no
    papel e deixando-o aberto no contrato.
    """
    contrato = json.loads(CONTRATO.read_text(encoding="utf-8"))
    esperados = {
        "checks/gui/test_alvos.py::test_area_minima_de_toque",
        "checks/gui/test_reflow.py::test_sem_rolagem_horizontal_em_320px",
        "checks/gui/test_reflow.py::test_zoom_200_nao_perde_conteudo",
        "checks/gui/test_foco.py::test_indicador_de_foco_visivel",
        "checks/gui/test_foco.py::test_ordem_de_tabulacao_segue_a_ordem_visual",
        "checks/gui/test_foco.py::test_foco_nao_obscurecido",
        "checks/gui/test_preferencias.py::test_reduced_motion_respeitado",
        "checks/gui/test_resiliencia.py::test_erro_500_na_api_nao_vaza_detalhe_tecnico",
        "checks/gui/test_resiliencia.py::test_json_truncado_nao_vaza_detalhe_tecnico",
    }
    declarados = {i for i in contrato["devem_falhar"] if "checks/gui/" in i}
    assert declarados == esperados


def test_particao_dos_checks_de_resiliencia_segue_o_desfecho_e_nao_o_arquivo():
    """Os quatro modos de falha moram no mesmo arquivo e caem em lados OPOSTOS.

    É o teste que impede a simplificação errada — "são todos de resiliência,
    ponham os quatro no contrato". A partição não é por assunto, é por desfecho:

    * **500** e **JSON truncado** terminam em `failed` determinístico contra o
      fixture, porque a home despeja o objeto de erro cru na tela. Entram;
    * **não responde** e **offline** terminam em `xfail`, porque a home fica em
      silêncio — e silêncio é ausência de mensagem, que a spec classificou como
      sinal e não prova. Ficam fora, com motivo.

    Pôr um xfail em `devem_falhar` faria o contrato cobrá-lo como "a menos" em
    toda execução, reprovando por classificação e não por regressão.
    """
    contrato = json.loads(CONTRATO.read_text(encoding="utf-8"))
    prefixo = "checks/gui/test_resiliencia.py::"
    dentro = {i for i in contrato["devem_falhar"] if i.startswith(prefixo)}
    fora = {i for i in contrato["fora_do_contrato"] if i.startswith(prefixo)}

    assert dentro == {prefixo + "test_erro_500_na_api_nao_vaza_detalhe_tecnico",
                      prefixo + "test_json_truncado_nao_vaza_detalhe_tecnico"}
    assert fora == {prefixo + "test_api_que_nao_responde_avisa_o_visitante",
                    prefixo + "test_perda_de_conexao_e_comunicada"}
    for excluido in fora:
        assert "xfail" in contrato["fora_do_contrato"][excluido], (
            "a exclusão precisa nomear o desfecho que a motivou, senão vira "
            "'não sei classificar' com aparência de decisão")


def test_check_de_gui_que_depende_de_CDN_fica_fora_do_contrato():
    """Check baseado em axe-core não entra em `devem_falhar` — e o motivo é o
    mesmo dos dois irmãos dele na dimensão `ux`.

    Ele baixa o axe de um CDN. Offline, PULA com motivo (o que é o
    comportamento correto), e um `devem_falhar` que não é observado vira "a
    menos": o contrato reprovaria por ambiente, não por regressão. A exclusão
    protege a propriedade que o contrato existe para ter — reprovar quando um
    check parou de detectar, e só então.

    A detecção segue coberta, por outro mecanismo (§2.8): unidade sobre a
    pré-checagem e sobre a verificação de hash, mais validação real registrada
    no PR. Fingir que o contrato a exercita daria confiança falsa justamente na
    regra mais fácil de errar.
    """
    contrato = json.loads(CONTRATO.read_text(encoding="utf-8"))
    fora = contrato["fora_do_contrato"]
    alvo = "checks/gui/test_preferencias.py::test_contraste_em_tema_escuro"
    assert alvo in fora, "check de axe em devem_falhar tornaria o contrato dependente de rede"
    assert "rede externa" in fora[alvo]
    assert alvo not in contrato["devem_falhar"]


def test_check_com_veredito_condicionado_ao_ambiente_fica_fora_do_contrato():
    """A mesma navalha da OS-45, aplicada ao outro tipo de dependência externa.

    O check de interatividade só reprova sob `WEBQA_ORIGEM=vps`; fora do ambiente
    oficial o estouro de TBT vira `xfail`, porque numa máquina compartilhada o
    número mede o vizinho, não o alvo. Isso o torna inelegível para
    `devem_falhar`: o contrato o cobraria como "a menos" em toda execução que não
    fosse da VPS — reprovando por AMBIENTE, e não por regressão.

    O critério é um só, e vale para os dois casos: o contrato 1:1 aceita apenas
    checks cujo desfecho contra o fixture dependa exclusivamente do que o fixture
    serve. Rede externa (axe) e origem declarada (ledger) são a mesma classe de
    exclusão, e é por isso que este teste fica ao lado daquele.
    """
    contrato = json.loads(CONTRATO.read_text(encoding="utf-8"))
    fora = contrato["fora_do_contrato"]
    alvo = "checks/gui/test_interatividade.py::test_tbt_long_tasks_e_inp"
    assert alvo in fora, (
        "veredito condicionado a WEBQA_ORIGEM em devem_falhar tornaria o contrato "
        "dependente do ambiente — verde na VPS, vermelho em todo lugar que importa")
    assert "WEBQA_ORIGEM" in fora[alvo], "a exclusão precisa nomear a condição"
    assert alvo not in contrato["devem_falhar"]


def test_escopo_do_contrato_inclui_a_dimensao_gui():
    """Sem `gui` na seleção, os três checks nem rodariam na execução interna — e
    o contrato os cobraria como "a menos" a cada run. A seleção é lida do próprio
    contrato por `tests/test_alvo_fixture.py`, então este é o único lugar em que
    ela é afirmada."""
    contrato = json.loads(CONTRATO.read_text(encoding="utf-8"))
    assert "gui" in contrato["escopo"]


# ---------- Identidade do alvo (chave do ledger) ----------

def test_identidade_nao_depende_da_porta():
    """A porta é efêmera; se a identidade viesse da URL, a sequência sem flake
    zeraria toda noite e a Fase 2 nunca destravaria."""
    with AlvoFixture() as a, AlvoFixture() as b:
        assert a.porta != b.porta
    assert identidade() == identidade()
    assert identidade().startswith("fixture_target:")


def test_identidade_muda_quando_a_violacao_muda(monkeypatch):
    """Mexeu no que o alvo serve, o alvo é outro — e a sequência recomeça."""
    antes = identidade()
    monkeypatch.setattr(servir, "HOME", servir.HOME.replace('method="get"', 'method="post"'))
    assert identidade() != antes


def test_identidade_ignora_comentario_do_codigo():
    """Só o conteúdo SERVIDO entra no hash: comentário não reinicia a métrica."""
    fonte = Path(servir.__file__).read_text(encoding="utf-8")
    assert "# VIOLACAO" not in identidade()
    assert fonte.count("VIOLACAO") >= 5  # os marcadores seguem no código, fora do hash


# ---------- Sanidade do contrato ----------

def test_contrato_e_json_valido_e_coerente():
    contrato = json.loads(CONTRATO.read_text(encoding="utf-8"))
    devem = contrato["devem_falhar"]
    fora = contrato["fora_do_contrato"]
    assert devem, "contrato vazio aprovaria qualquer regressão"
    assert len(devem) == len(set(devem)), "ids duplicados em devem_falhar"
    assert not (set(devem) & set(fora)), "um teste não pode ser esperado e excluído ao mesmo tempo"
    for teste in devem:
        assert "::" in teste, f"id sem '::' não casa com nodeid do pytest: {teste}"
    for motivo in fora.values():
        assert motivo.strip(), "exclusão do contrato exige motivo escrito"
