"""VERIFICAÇÃO do painel de estabilidade (OS-26).

Dois níveis, e a divisão é a mesma do resto da casa:

* aqui, **verificação** — ledgers sintéticos cobrindo as bordas que o ledger
  real não exerce (dois alvos, duas execuções no mesmo dia, flake seguido de
  noite limpa, ledger vazio);
* em `test_estabilidade_html_real`, ao fim do arquivo, **validação** — o ledger
  versionado de verdade, que hoje tem uma entrada só.

A borda mais importante é a última: **ledger vazio não pode parecer defeito**.
Instalação nova é o estado inicial legítimo do projeto, e uma página que parece
quebrada no primeiro dia ensina o leitor a desconfiar dela para sempre.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.estabilidade import caminhada, sequencia_oficial, violacoes_do_contrato
from webqa.estabilidade_html import classificar_linhas, montar, motivos_do_zero
from webqa.report_style import ESTILO_CANONICO

pytestmark = pytest.mark.verification

RAIZ = Path(__file__).resolve().parent.parent
SHA_A = "a" * 64
SHA_B = "b" * 64


def _noite(dia: str, origem: str = "vps", flakes: int = 0, browser: int = 7,
           sha: str = SHA_A, classificador: int = 2, hora: str = "03:14:00",
           assinaturas: list[str] | None = None) -> dict:
    entrada = {"generated_at": f"{dia} {hora}", "dia_utc": dia, "origem": origem,
               "alvo_sha256": sha, "browser_total": browser, "infra_flakes": flakes,
               "classificador": classificador}
    if assinaturas:
        entrada["infra_assinaturas"] = assinaturas
    return entrada


def _painel(execucoes: list[dict], violacoes: int = 11) -> str:
    ledger = {"schema": 4, "execucoes": execucoes}
    return montar(ledger, caminhada(execucoes), violacoes)


def _efeitos(html: str) -> list[str]:
    """Textos da coluna 'Efeito na sequência', na ordem em que aparecem."""
    return [re.sub(r"\s+", " ", t).strip()
            for t in re.findall(r'class="estado-min [a-z]+">.*?</svg>([^<]+)', html, re.S)]


# ---------- Borda 1: dois alvos ----------

def test_troca_de_sha_reinicia_a_sequencia_e_preserva_o_historico():
    """Nove noites limpas contra um alvo mais uma contra outro não são dez."""
    execucoes = [_noite("2026-08-01", sha=SHA_A), _noite("2026-08-02", sha=SHA_A),
                 _noite("2026-08-03", sha=SHA_B)]
    html = _painel(execucoes)

    streak, _ = sequencia_oficial(execucoes)
    assert streak == 1, "a sequência devia ter recomeçado no alvo novo"
    assert 'prog-num num">1<small>/10' in html
    assert "o alvo mudou de identidade" in html
    # Nenhuma entrada some: o ledger é registro auditável.
    assert len(_efeitos(html)) == 3
    assert "2026-08-01" in html and "2026-08-02" in html


def test_nota_de_troca_de_alvo_so_aparece_quando_ha_troca():
    assert "mudou de identidade" not in _painel(
        [_noite("2026-08-01"), _noite("2026-08-02")])


# ---------- Borda 2: mesmo dia UTC e origem desconhecida ----------

def test_duas_execucoes_no_mesmo_dia_valem_a_primeira():
    """Dez execuções num dia não são dez dias estáveis."""
    execucoes = [
        _noite("2026-08-01", hora="03:14:00"),
        _noite("2026-08-01", hora="22:00:00", flakes=3),   # segunda do dia: ignorada
    ]
    html = _painel(execucoes)

    assert sequencia_oficial(execucoes)[0] == 1, "a segunda do dia não podia derrubar a primeira"
    efeitos = _efeitos(html)
    assert "não conta · segunda execução do dia UTC" in efeitos
    assert any(e.startswith("limpa · sequência: 1") for e in efeitos)


def test_origem_desconhecida_degrada_para_local_e_nao_conta():
    """Erro de digitação no compose jamais pode inflar a métrica de confiança."""
    execucoes = [_noite("2026-08-01", origem="banana")]
    html = _painel(execucoes)

    assert sequencia_oficial(execucoes)[0] == 0
    assert 'prog-num num">0<small>/10' in html
    assert _efeitos(html) == ["informativa · não conta"]


# ---------- Borda 3: flake e recuperação ----------

def test_flake_zera_e_a_noite_seguinte_recomeca_em_um():
    execucoes = [_noite("2026-08-01"), _noite("2026-08-02", flakes=1), _noite("2026-08-03")]
    html = _painel(execucoes)
    efeitos = _efeitos(html)   # ordem: mais recente primeiro

    assert efeitos[0] == "limpa · sequência: 1"
    assert efeitos[1] == "flake · sequência zerada"
    assert efeitos[2] == "limpa · sequência: 1"
    assert 'prog-num num">1<small>/10' in html
    # Flake usa o vocabulário de `failed`; noite limpa, o de `passed`.
    assert 'class="estado-min failed"' in html and 'class="estado-min passed"' in html


def test_flake_mostra_o_motivo_quando_o_ledger_o_registra():
    """"1" manda o leitor abrir o log; "1 — TimeoutError" já responde."""
    html = _painel([_noite("2026-08-02", flakes=1, assinaturas=["TimeoutError"])])
    assert "1 — TimeoutError" in html


def test_entrada_anterior_ao_schema_5_mostra_so_a_contagem():
    """Campo ausente não vira texto inventado — degrada para o número."""
    html = _painel([_noite("2026-08-02", flakes=2)])
    assert '<td class="t-det">2</td>' in html


def test_assinatura_do_ledger_e_escapada():
    html = _painel([_noite("2026-08-02", flakes=1, assinaturas=["<b>x</b>"])])
    assert "<b>x</b>" not in html.split("<style>")[0] + html.split("</style>")[-1]
    assert "&lt;b&gt;" in html


def test_execucao_sem_teste_de_navegador_nao_conta_como_limpa():
    """Sem navegador não houve o que medir — e nada medido não vira crédito."""
    execucoes = [_noite("2026-08-01", browser=0)]
    assert sequencia_oficial(execucoes)[0] == 0
    assert 'prog-num num">0<small>/10' in _painel(execucoes)


# ---------- Borda 4: instalação nova ----------

def test_ledger_vazio_gera_pagina_valida_e_explicativa():
    """Nunca parecer quebrada: instalação nova é estado legítimo, não defeito."""
    html = _painel([])

    assert html.startswith("<!doctype html>") and html.rstrip().endswith("</html>")
    assert html.count("<h1") == 1
    assert 'prog-num num">0<small>/10' in html
    assert "instalação nova, não um defeito" in html
    assert "ausência de evidência não vira crédito" in html
    assert "<table" not in html, "tabela vazia não informa; o texto explica melhor"


# ---------- Contrato visual (§12 do brief) ----------

def test_arquivo_unico_sem_requisicao_externa_e_sem_js_obrigatorio():
    html = _painel([_noite("2026-08-01")])

    externos = re.findall(r'(?:src|href)\s*=\s*["\']?(https?://[^"\'\s>]+)', html)
    assert externos == [], f"o painel precisa ser autocontido; achei {externos}"
    assert "<script" not in html, "nada aqui pode depender de JS"
    assert "<link rel=\"icon\" href='data:" in html, "favicon tem de ser data: URI"


def test_folha_canonica_reusada_byte_a_byte():
    """Regra 2.4: a folha é congelada. O painel compõe com o que existe."""
    assert ESTILO_CANONICO in _painel([_noite("2026-08-01")])


def test_impressao_e_tema_escuro_vem_da_folha():
    html = _painel([_noite("2026-08-01")])
    assert "@media print" in html
    assert "prefers-color-scheme" in html
    assert "data-tema" in html


def test_painel_nao_inventa_classe_fora_da_folha():
    """Nenhuma classe nova: inventar token ou classe é regressão, não melhoria."""
    html = _painel([_noite("2026-08-01", origem="local"), _noite("2026-08-02", flakes=1)])
    corpo = re.sub(r"<style>.*?</style>", "", html, flags=re.S)
    usadas = {c for m in re.finditer(r'class="([^"]+)"', corpo) for c in m.group(1).split()}
    ausentes = sorted(c for c in usadas if f".{c}" not in ESTILO_CANONICO)
    assert ausentes == [], f"classes sem regra na folha canônica: {ausentes}"


def test_estados_tem_forma_e_rotulo_nunca_so_cor():
    """Regra 2.5 — o laudo circula impresso em preto e branco."""
    html = _painel([_noite("2026-08-01"), _noite("2026-08-02", flakes=1),
                    _noite("2026-08-03", origem="ci")])
    for efeito in _efeitos(html):
        assert efeito.strip(), "linha sem rótulo textual"
    assert html.count("<svg") >= 3, "cada estado leva um ícone além da cor"


def test_slots_marcam_o_decimo_como_meta():
    html = _painel([_noite(f"2026-08-0{i}") for i in range(1, 4)])
    assert html.count('class="slot ok"') == 3
    assert 'meta-slot" title="10ª noite: Fase 2"' in html
    assert 'aria-label="3 de 10 noites limpas"' in html


def test_marco_nao_gamifica():
    html = _painel([])
    assert "FASE 2 DESTRAVADA" in html
    assert "Sem troféu" in html
    for confete in ("🎉", "🏆", "parabéns", "Parabéns"):
        assert confete not in html


# ---------- Narrativa interpolada ----------

def test_numero_de_violacoes_vem_do_contrato_e_nao_e_literal():
    """O fixture já cresceu uma vez; literal na narrativa envelhece em silêncio."""
    assert "— 7 não conformidades" in _painel([], violacoes=7)
    assert "— 11 não conformidades" in _painel([], violacoes=11)

    fonte = (RAIZ / "webqa" / "estabilidade_html.py").read_text(encoding="utf-8")
    assert "11 não conformidades" not in fonte, "número do contrato virou literal no gerador"


def test_contrato_lido_do_esperado_json():
    contrato = json.loads(
        (RAIZ / "fixture_target" / "esperado.json").read_text(encoding="utf-8"))
    assert violacoes_do_contrato() == len(contrato["devem_falhar"])


def test_historia_cabe_em_um_paragrafo_e_explica_o_essencial():
    """Critério §12: um leigo entende sem explicação oral."""
    html = _painel([_noite("2026-08-01")])
    historia = re.search(r'<p class="historia">(.*?)</p>', html, re.S).group(1)
    assert "robô" in historia and "site de teste" in historia
    assert "Dez noites limpas seguidas" in historia
    # O que zera é o equipamento, não o alvo — é a confusão que a página existe
    # para desfazer, e ela tem de aparecer antes da tabela.
    # Compara com a SEÇÃO, não com o link do índice — que cita a âncora lá em cima.
    assert html.index("equipamento</strong> falhar") < html.index('<section id="linha-do-tempo"')


# ---------- Escape ----------

def test_dado_do_ledger_nunca_vira_marcacao():
    execucoes = [_noite("2026-08-01", origem="<script>alert(1)</script>")]
    html = _painel(execucoes)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ---------- VALIDAÇÃO: o ledger real ----------

def test_ledger_real_renderiza_a_sequencia_correta():
    """Validação contra o arquivo versionado — hoje: uma entrada `ci`, 0/10.

    Não fixa o número 0 por acaso: recomputa do próprio ledger, para o teste
    continuar valendo quando as primeiras noites `vps` entrarem.
    """
    ledger = json.loads(
        (RAIZ / "docs" / "lgpd-estabilidade.json").read_text(encoding="utf-8"))
    execucoes = ledger["execucoes"]
    esperado, _ = sequencia_oficial(execucoes)
    html = montar(ledger, caminhada(execucoes), violacoes_do_contrato())

    assert f'prog-num num">{esperado}<small>/10' in html
    assert html.count("<h1") == 1
    assert re.findall(r'(?:src|href)\s*=\s*["\']?(https?://[^"\'\s>]+)', html) == []


def test_entrada_ci_real_e_rotulada_como_historico_e_nao_some():
    """Ela é `ci` E está em quarentena. O motivo que basta sozinho é ser `ci`:
    nem um juiz perfeito a faria pontuar fora do ambiente oficial."""
    ledger = json.loads(
        (RAIZ / "docs" / "lgpd-estabilidade.json").read_text(encoding="utf-8"))
    execucoes = ledger["execucoes"]
    linhas = classificar_linhas(execucoes, caminhada(execucoes))

    ci = [linha for linha in linhas if linha["origem"] == "ci"]
    assert len(ci) == 1, "a entrada histórica sumiu do painel"
    assert ci[0]["efeito"] == "histórico · anterior à emenda — não conta"
    assert ci[0]["conta"] is False
    assert "2026-07-30" in ci[0]["quando"]


# ---------- VALIDAÇÃO: lado a lado com a referência do designer ----------

# Ledger reconstruído da TABELA da referência. Reconstruído, e não inventado:
# cada linha aqui corresponde a uma linha visível em
# `docs/qa-suite design brief/referencia/estabilidade.html`.
SHA_REF = "a6ee5978da3bbfe091578e6dddbc63ecc22ea802f3e208d15f4cc580b6de15ca"
LEDGER_DEMO = [
    _noite("2026-07-30", origem="ci", browser=9, sha=SHA_REF, hora="02:38"),
    _noite("2026-08-01", sha=SHA_REF, hora="03:14"),
    _noite("2026-08-02", sha=SHA_REF, hora="03:14"),
    _noite("2026-08-03", sha=SHA_REF, hora="03:14", flakes=1, assinaturas=["TimeoutError"]),
    _noite("2026-08-03", origem="local", sha=SHA_REF, hora="11:02"),
    _noite("2026-08-04", sha=SHA_REF, hora="03:14"),
    _noite("2026-08-05", sha=SHA_REF, hora="03:14"),
    _noite("2026-08-06", sha=SHA_REF, hora="03:14"),
]
REFERENCIA = RAIZ / "docs" / "qa-suite design brief" / "referencia" / "estabilidade.html"


def _tabela_de(html: str) -> list[tuple[str, str]]:
    """(noite, efeito) por linha, na ordem em que a página as apresenta."""
    noites = re.findall(r'<td class="t-teste num">([^<]+)</td>', html)
    # strict: contagens diferentes seriam bug do parser, não empate a ignorar.
    return list(zip(noites, _efeitos(html), strict=True))


def test_ledger_de_demonstracao_reproduz_a_referencia():
    """O aceite visual: renderizar o ledger da referência tem de dar a referência.

    Se este teste quebrar, ou o gerador divergiu do contrato de design, ou o
    contrato mudou sem o gerador saber. Nos dois casos alguém precisa olhar —
    é justamente o que "divergência é regressão, não melhoria" quer dizer.
    """
    html = montar({"schema": 5, "execucoes": LEDGER_DEMO},
                  caminhada(LEDGER_DEMO), 7)
    ref = REFERENCIA.read_text(encoding="utf-8")

    assert _tabela_de(html) == _tabela_de(ref), "a tabela divergiu da referência"
    assert html.count('class="slot ok"') == ref.count('class="slot ok"')
    assert (re.search(r'prog-num num">(\d+)<small>/(\d+)', html).groups()
            == re.search(r'prog-num num">(\d+)<small>/(\d+)', ref).groups())


def test_mesmas_secoes_e_nenhuma_classe_nova_frente_a_referencia():
    html = montar({"schema": 5, "execucoes": LEDGER_DEMO},
                  caminhada(LEDGER_DEMO), 7)
    ref = REFERENCIA.read_text(encoding="utf-8")

    assert (re.findall(r'<section id="([^"]+)"', html)
            == re.findall(r'<section id="([^"]+)"', ref))

    def classes(h):
        corpo = re.sub(r"<style>.*?</style>", "", h, flags=re.S)
        return {c for m in re.finditer(r'class="([^"]+)"', corpo) for c in m.group(1).split()}

    novas = sorted(classes(html) - classes(ref))
    assert novas == [], f"o painel inventou classe que a referência não usa: {novas}"


# ---------- OS-33: o zero explicado, não apenas exibido ----------

SHA_HOJE = "c" * 64


def test_zero_do_ledger_real_mostra_os_tres_motivos():
    """Exibir 0/10 sem dizer por quê ensina o leitor a desconfiar do número.

    Hoje o ledger tem três motivos ao mesmo tempo, e mostrar só o primeiro
    esconderia que corrigir a origem não bastaria para a contagem começar.
    """
    ledger = json.loads(
        (RAIZ / "docs" / "lgpd-estabilidade.json").read_text(encoding="utf-8"))
    execucoes = ledger["execucoes"]
    motivos = motivos_do_zero(execucoes, caminhada(execucoes), SHA_HOJE)

    assert len(motivos) == 3, f"esperava 3 motivos, vieram {len(motivos)}: {motivos}"
    juntos = " ".join(motivos).lower()
    assert "ambiente oficial" in juntos and "<code>ci</code>" in " ".join(motivos)
    assert "quarentena" in juntos
    assert "mudou de identidade" in juntos


def test_motivos_sao_cumulativos_e_nao_excludentes():
    """Corrigir um não faz os outros sumirem — e a página tem de dizer isso."""
    so_origem = [_noite("2026-08-01", origem="local", sha=SHA_HOJE)]
    assert len(motivos_do_zero(so_origem, caminhada(so_origem), SHA_HOJE)) == 1

    origem_e_quarentena = [_noite("2026-08-01", origem="local", sha=SHA_HOJE,
                                  classificador=1)]
    assert len(motivos_do_zero(origem_e_quarentena,
                               caminhada(origem_e_quarentena), SHA_HOJE)) == 2


def test_sequencia_viva_nao_ganha_bloco_de_motivo():
    """O bloco existe para explicar zero. Com a contagem andando, ele some."""
    execucoes = [_noite("2026-08-01", sha=SHA_HOJE), _noite("2026-08-02", sha=SHA_HOJE)]
    assert motivos_do_zero(execucoes, caminhada(execucoes), SHA_HOJE) == []

    html = montar({"schema": 5, "execucoes": execucoes}, caminhada(execucoes), 11,
                  sha_do_alvo_atual=SHA_HOJE)
    assert "Por que a contagem está em zero" not in html


def test_flake_na_ultima_noite_e_dito_como_motivo():
    """Zero por 'ainda não houve noite oficial' e zero por 'flake ontem' são
    situações opostas — a primeira é normal, a segunda é infra quebrando."""
    execucoes = [_noite("2026-08-01", sha=SHA_HOJE),
                 _noite("2026-08-02", sha=SHA_HOJE, flakes=1)]
    motivos = " ".join(motivos_do_zero(execucoes, caminhada(execucoes), SHA_HOJE))
    assert "flake de infraestrutura" in motivos


def test_alvo_novo_nao_e_afirmado_sem_saber_qual_e_o_alvo_de_hoje():
    """Sem a identidade atual, o motivo não é afirmado — inventar explicação
    para um zero é pior que não explicá-lo."""
    execucoes = [_noite("2026-08-01", origem="local", sha=SHA_A)]
    motivos = " ".join(motivos_do_zero(execucoes, caminhada(execucoes), ""))
    assert "mudou de identidade" not in motivos


def test_ledger_vazio_nao_lista_motivos_porque_ja_tem_texto_proprio():
    assert motivos_do_zero([], [], SHA_HOJE) == []
    html = montar({"schema": 5, "execucoes": []}, [], 11, sha_do_alvo_atual=SHA_HOJE)
    assert "Por que a contagem está em zero" not in html
    assert "instalação nova, não um defeito" in html


def test_bloco_do_zero_compoe_com_a_folha_e_nao_inventa_classe():
    ledger = json.loads(
        (RAIZ / "docs" / "lgpd-estabilidade.json").read_text(encoding="utf-8"))
    html = montar(ledger, caminhada(ledger["execucoes"]), 11, sha_do_alvo_atual=SHA_HOJE)

    corpo = re.sub(r"<style>.*?</style>", "", html, flags=re.S)
    usadas = {c for m in re.finditer(r'class="([^"]+)"', corpo) for c in m.group(1).split()}
    ausentes = sorted(c for c in usadas if f".{c}" not in ESTILO_CANONICO)
    assert ausentes == [], f"classes sem regra na folha canônica: {ausentes}"
    assert html.count("<h1") == 1


def test_o_bloco_do_zero_chega_ao_HTML_e_nao_so_a_funcao():
    """A derivação certa não serve de nada se ela não for renderizada.

    Este teste existe porque a primeira versão da suíte da OS-33 passava com o
    bloco DESCONECTADO do `montar`: os testes chamavam `motivos_do_zero()`
    direto e nenhum conferia a página. É §2.10 de novo — a intenção estava certa
    e a ligação faltava, em silêncio.
    """
    ledger = json.loads(
        (RAIZ / "docs" / "lgpd-estabilidade.json").read_text(encoding="utf-8"))
    html = montar(ledger, caminhada(ledger["execucoes"]), 11, sha_do_alvo_atual=SHA_HOJE)

    assert "Por que a contagem está em zero" in html, "o bloco não foi renderizado"
    for esperado in ("ambiente oficial", "quarentena", "mudou de identidade"):
        assert esperado in html, f"motivo {esperado!r} derivado mas ausente da página"
    # O bloco fica ANTES do marco da Fase 2: explicar o zero vem antes de
    # prometer o prêmio de 10/10.
    assert html.index("Por que a contagem") < html.index("FASE 2 DESTRAVADA")
