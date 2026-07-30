#!/usr/bin/env python3
"""Ledger de estabilidade da dimensão browser — critério de saída da Fase 1.

A Fase 2 (canário de consentimento, CMPs) foi condicionada pela arquitetura à
estabilidade da infraestrutura de `network_log` em produção. "Estável" precisa
ser um número verificável, não uma impressão: este script conta execuções
CONSECUTIVAS sem falha de infraestrutura e registra cada uma no ledger.

A distinção que dá sentido à métrica:

* **flake de infra** — Timeout, TargetClosed, `net::`, Chromium ausente.
  É defeito do AMBIENTE DE TESTE. Zera a sequência.
* **FAIL determinístico** — tracker antes do consentimento, cookie de 730 dias.
  É veredito sobre o ALVO, e a suíte funcionou exatamente como deveria.
  NÃO zera a sequência; um alvo não conforme não torna a suíte instável.

Privacidade: a URL do alvo NUNCA entra no ledger, só o sha256. O digest serve
para correlacionar execuções do mesmo alvo — não é segredo (o espaço de URLs é
pequeno e enumerável), é chave de agrupamento.

REGRA OBRIGATÓRIA — versão do classificador
-------------------------------------------
Toda entrada carrega `classificador`: a versão do juiz que a produziu. Qualquer
PR que altere COMO uma execução é classificada (o regex de infra, o critério de
`limpa`, o que conta como teste de navegador) **precisa** incrementar
`CLASSIFICADOR_VERSAO`. Ver docs/LGPD.md §versão do classificador.

O motivo é histórico e concreto: até a v1, erros de setup sumiam do summary, e
uma noite com o navegador completamente inalcançável era classificada como
LIMPA — a métrica de confiança inflava exatamente quando a infraestrutura
quebrava. Entradas produzidas por um juiz defeituoso não podem sustentar a
sequência que destrava a Fase 2, e não há como reclassificá-las: o dado que
faltava nunca foi gravado.

A saída para isso é QUARENTENA, não expurgo — entradas de versão com defeito
conhecido não contam, não zeram e não são apagadas. As três propriedades juntas:
a sequência só anda sobre dado íntegro, o histórico continua auditável, e a
regra é retroativa sem reescrever o passado.

Somente stdlib.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# O diretório de relatório é redirecionável por ambiente (mesma variável que
# webqa/report.py honra ao ESCREVER). Ler de um lugar fixo enquanto a suíte
# escreve noutro fazia o noturno da VPS classificar um summary velho — ou
# nenhum, já que o container não tem `report/` na imagem.
SUMMARY_PADRAO = Path(os.environ.get("WEBQA_REPORT_DIR") or ROOT / "report") / "summary.json"
LEDGER_PADRAO = ROOT / "docs" / "lgpd-estabilidade.json"
# Painel vai para report/, que é ignorado pelo git (R8) e honra WEBQA_REPORT_DIR
# como o resto dos artefatos. O ledger é versionado; o painel é derivado dele e
# se refaz a qualquer momento — versionar os dois seria versionar a mesma
# verdade duas vezes, e elas divergiriam.
PAINEL_PADRAO = Path(os.environ.get("WEBQA_REPORT_DIR") or ROOT / "report") / "estabilidade.html"
META_PADRAO = 10
# Violações declaradas no contrato do alvo fixture. INTERPOLADO na narrativa do
# painel, nunca literal: o fixture já cresceu uma vez, e um número fixo dentro de
# um parágrafo envelhece em silêncio.
CONTRATO_PADRAO = ROOT / "fixture_target" / "esperado.json"
# schema 2: entradas ganham "origem" e "dia_utc"; sequência recalculada do
#           histórico, contando só o ambiente oficial e um dia por vez.
# schema 3: EMENDA de arquitetura (2026-07-30) — o ambiente oficial deixa de ser
#           o runner do GitHub e passa a ser o container Docker da VPS, com
#           imagem fixada por digest. A origem não é mais DETECTADA
#           (GITHUB_ACTIONS), é DECLARADA por WEBQA_ORIGEM, injetada somente no
#           container oficial. Entradas "ci" anteriores viram histórico.
# schema 4: entradas ganham "classificador" (versão do juiz). Entradas sem o
#           campo recebem 1 na carga — migração one-shot, ver carregar_ledger.
# schema 5: entradas ganham "infra_assinaturas" — QUAIS sinais de infra
#           dispararam, para o painel dizer o motivo em vez de só a contagem
#           ("1 — TimeoutError" em vez de "1"). Campo descritivo e opcional:
#           NENHUMA regra de julgamento o lê, então CLASSIFICADOR_VERSAO NÃO
#           sobe (regra 2.3 é sobre mudar COMO se julga, e nada aqui muda).
#           Entrada antiga sem o campo continua válida e mostra só a contagem.
SCHEMA = 5

# Só este ambiente move a métrica. Um runner hospedado troca a imagem base sob
# os pés; um container fixado por digest não — logo é MAIS controlado, e é dele
# que a sequência fala.
ORIGEM_OFICIAL = "vps"
ORIGENS_VALIDAS = ("vps", "ci", "local")

# Versão do CLASSIFICADOR (não do arquivo). Incrementar em todo PR que mude como
# uma execução é julgada — ver a regra obrigatória no docstring do módulo.
#
# v1 → juiz anterior à correção de 2026-07-30.
# v2 → passa a enxergar erro de setup/teardown (webqa/report.py registra a fase),
#      então navegador inalcançável vira flake de infra em vez de noite limpa.
CLASSIFICADOR_VERSAO = 2

# Versões cujo veredito não sustenta a sequência. Lista FECHADA de culpados
# conhecidos, deliberadamente — não é whitelist. Versão futura desconhecida
# conta normalmente: travar a sequência para sempre porque um refactor esqueceu
# de registrar o campo seria um fail-safe que falha para o lado errado.
DEFEITOS_CONHECIDOS = {
    1: "erros de setup invisíveis; noite limpa com navegador morto",
}

# Assinaturas de falha do ambiente de teste — nunca de conformidade do alvo.
#
# SEM re.IGNORECASE e com limite de palavra, de propósito: o pytest inclui no
# longrepr o cabeçalho de argumentos das fixtures, onde aparece
# `Settings(..., timeout_s=15.0, ...)`. Casar "timeout" sem caixa transformava
# TODA falha determinística num falso flake — a sequência nunca sairia de zero.
INFRA = re.compile(
    r"\bTimeout(?:Error)?\b"          # Playwright: "Timeout 60000ms exceeded" / TimeoutError
    r"|\bTargetClosed"                # página/contexto fechado no meio do teste
    r"|net::"                         # erros de rede do Chromium (net::ERR_*)
    r"|Chromium indispon"             # skip da fixture browser
    r"|Playwright n[ãa]o instalado"   # skip da fixture browser
)


@dataclass(frozen=True)
class Classificacao:
    """Veredito sobre UMA execução da suíte."""

    generated_at: str
    browser_total: int
    flakes: tuple[str, ...]
    # QUAIS sinais dispararam, para o painel dizer o motivo. Vocabulário FECHADO,
    # vindo da alternação de INFRA — nunca o trecho de erro do alvo. O ledger é
    # versionado, e texto livre de execução ali violaria o R8; um rótulo do nosso
    # próprio regex não carrega host nem dado do alvo.
    assinaturas: tuple[str, ...] = ()

    @property
    def tem_browser(self) -> bool:
        return self.browser_total > 0

    @property
    def limpa(self) -> bool:
        return self.tem_browser and not self.flakes


def classificar(summary: dict) -> Classificacao:
    """Separa flake de infra de veredito sobre o alvo."""
    browser = [r for r in summary.get("results", []) if r.get("browser")]
    flakes, assinaturas = [], []
    for r in browser:
        if r.get("outcome") == "passed":
            continue
        achado = INFRA.search(r.get("detail") or "")
        if not achado:
            continue
        flakes.append(r.get("test", "?"))
        # O TEXTO CASADO, não o trecho ao redor: `achado.group(0)` é sempre um
        # dos rótulos da alternação de INFRA. Levar o contexto colocaria erro do
        # alvo num arquivo versionado (R8) — o rótulo, não.
        rotulo = achado.group(0).strip()
        if rotulo not in assinaturas:
            assinaturas.append(rotulo)
    return Classificacao(
        generated_at=str(summary.get("generated_at", "")),
        browser_total=len(browser),
        flakes=tuple(flakes),
        assinaturas=tuple(sorted(assinaturas)),
    )


def sha256_do_alvo(target_url: str) -> str:
    return hashlib.sha256(target_url.encode("utf-8")).hexdigest()


def carregar_ledger(caminho: Path) -> dict:
    if not caminho.exists():
        return {"schema": SCHEMA, "execucoes": []}
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    dados.setdefault("execucoes", [])
    # Migração one-shot: entrada sem o campo é, por definição, anterior à
    # introdução dele — logo v1. Assumir a versão CORRENTE seria dar fé de
    # integridade a exatamente o dado que não a tem.
    for entrada in dados["execucoes"]:
        entrada.setdefault("classificador", 1)
    return dados


def versao_de(entrada: dict) -> int:
    """Versão do juiz que produziu a entrada (ausente = v1, pré-campo)."""
    try:
        return int(entrada.get("classificador", 1))
    except (TypeError, ValueError):
        return 1


def em_quarentena(entrada: dict) -> bool:
    return versao_de(entrada) in DEFEITOS_CONHECIDOS


def quarentena(execucoes: list[dict]) -> dict[int, int]:
    """Quantas entradas por versão defeituosa — insumo da mensagem de saída."""
    contagem: dict[int, int] = {}
    for entrada in execucoes:
        if em_quarentena(entrada):
            versao = versao_de(entrada)
            contagem[versao] = contagem.get(versao, 0) + 1
    return dict(sorted(contagem.items()))


def origem_da_execucao() -> str:
    """Origem DECLARADA em WEBQA_ORIGEM: vps | ci | local.

    Valor ausente ou desconhecido degrada para "local" — fail-safe deliberado:
    um erro de digitação no compose jamais pode inflar a métrica de confiança.
    No pior caso a execução deixa de contar; nunca conta errado.

    Não é prova criptográfica de proveniência — é declaração do ambiente, e quem
    tem push no repositório pode escrever o que quiser no ledger. A barreira
    existe contra descuido, não contra falsificação deliberada.
    """
    declarada = (os.environ.get("WEBQA_ORIGEM") or "local").strip().lower()
    return declarada if declarada in ORIGENS_VALIDAS else "local"


def _dia_utc_de(entrada: dict) -> str:
    """Dia UTC da entrada; cai para o prefixo de generated_at se o campo faltar.

    O fallback cobre a entrada anterior à migração, gravada por um runner do
    Actions (TZ=UTC) — logo o prefixo É o dia UTC.
    """
    return str(entrada.get("dia_utc") or str(entrada.get("generated_at", ""))[:10])


def sequencia_oficial(execucoes: list[dict],
                      origem_oficial: str = ORIGEM_OFICIAL) -> tuple[int, int]:
    """(sequência sem flake, dias distintos) contando SÓ o ambiente oficial.

    Recalculada do histórico inteiro a cada rodada, em vez de incrementada a
    partir da última entrada: o valor gravado passa a ser derivável e auditável,
    e uma entrada inserida fora de ordem não contamina o resto.

    Quatro regras:

    * `origem != origem_oficial` não conta — inclui as entradas `ci` anteriores
      à emenda, que permanecem no ledger como HISTÓRICO, e as `local`;
    * entrada de versão do classificador com DEFEITO CONHECIDO fica em
      quarentena: não conta e **não zera**. Ela foi julgada por um juiz que
      errava, então nem avança a sequência (o veredito não é confiável) nem a
      derruba (a execução pode ter sido perfeitamente boa — não há como saber).
      Também não é apagada: o histórico continua auditável;
    * no máximo UMA por dia UTC, e vale a PRIMEIRA do dia: uma segunda execução
      no mesmo dia não infla a sequência;
    * a sequência é por alvo — se o `alvo_sha256` muda entre dias contados,
      recomeça.
    """
    passos = caminhada(execucoes, origem_oficial)
    streak = passos[-1].streak if passos else 0
    return streak, len(passos)


@dataclass(frozen=True)
class Passo:
    """Uma entrada que CONTA, e o que ela fez com a sequência.

    Existe para que o painel HTML não precise repetir a caminhada. Duas
    implementações da mesma regra divergem — e divergiriam justamente no número
    que a página exibe como verdade.
    """

    entrada: dict
    dia_utc: str
    limpa: bool
    streak: int          # sequência DEPOIS desta noite
    alvo_mudou: bool     # o alvo trocou de identidade nesta noite


def caminhada(execucoes: list[dict],
              origem_oficial: str = ORIGEM_OFICIAL) -> list[Passo]:
    """As noites que contam, em ordem de dia UTC, com o efeito de cada uma.

    Ponto único da regra: `sequencia_oficial` devolve o último passo desta lista,
    e o painel (`webqa/estabilidade_html.py`) rotula cada linha a partir dela.
    """
    primeira_do_dia: dict[str, dict] = {}
    for entrada in execucoes:
        if entrada.get("origem") != origem_oficial:
            continue
        # Filtrar a quarentena ANTES do agrupamento por dia é o que faz o
        # "não zera": se a entrada em quarentena disputasse a vaga do dia, uma
        # v1 no mesmo dia de uma v2 boa apagaria a boa da contagem.
        if em_quarentena(entrada):
            continue
        primeira_do_dia.setdefault(_dia_utc_de(entrada), entrada)

    passos: list[Passo] = []
    streak = 0
    alvo_anterior: str | None = None
    for dia in sorted(primeira_do_dia):
        entrada = primeira_do_dia[dia]
        mudou = alvo_anterior is not None and entrada.get("alvo_sha256") != alvo_anterior
        if mudou:
            streak = 0
        limpa = int(entrada.get("infra_flakes", 0)) == 0 and int(entrada.get("browser_total", 0)) > 0
        streak = streak + 1 if limpa else 0
        alvo_anterior = entrada.get("alvo_sha256")
        passos.append(Passo(entrada=entrada, dia_utc=dia, limpa=limpa,
                            streak=streak, alvo_mudou=mudou))
    return passos


@dataclass(frozen=True)
class Registro:
    """O que aconteceu ao tentar registrar a execução."""

    streak: int
    entrada: dict | None
    dias: int = 0
    origem: str = "local"
    duplicada: bool = False
    ignorada: bool = False
    alvo_mudou: bool = False


def registrar(ledger: dict, classificacao: Classificacao, alvo_sha256: str,
              origem: str | None = None, dia_utc: str | None = None) -> Registro:
    """Aplica a execução ao ledger (em memória) e devolve o que mudou."""
    execucoes = ledger["execucoes"]
    origem = origem or origem_da_execucao()
    streak_atual, dias_atuais = sequencia_oficial(execucoes)

    # generated_at é a chave: rodar o script duas vezes no mesmo summary não
    # infla a sequência nem cria entrada duplicada.
    for entrada in execucoes:
        if entrada.get("generated_at") == classificacao.generated_at:
            return Registro(streak=streak_atual, entrada=entrada, dias=dias_atuais,
                            origem=str(entrada.get("origem", "local")), duplicada=True)

    # Execução sem nenhum teste de navegador não diz nada sobre a estabilidade
    # do network_log: não conta e não zera.
    if not classificacao.tem_browser:
        return Registro(streak=streak_atual, entrada=None, dias=dias_atuais,
                        origem=origem, ignorada=True)

    anterior_oficial = next(
        (e for e in reversed(execucoes) if e.get("origem") == ORIGEM_OFICIAL), None
    )
    alvo_mudou = bool(anterior_oficial
                      and anterior_oficial.get("alvo_sha256") != alvo_sha256)

    entrada = {
        "generated_at": classificacao.generated_at,
        # Dia vem do generated_at do summary, não do relógio de agora: o script
        # pode rodar minutos (ou um retry) depois da suíte, e o dia que importa é
        # o da EXECUÇÃO. Nos runners do Actions TZ=UTC — e são justamente as
        # entradas de CI que a deduplicação por dia considera.
        "dia_utc": dia_utc or classificacao.generated_at[:10],
        "origem": origem,
        "alvo_sha256": alvo_sha256,
        "browser_total": classificacao.browser_total,
        "infra_flakes": len(classificacao.flakes),
        # Descritivo, para o painel dizer o MOTIVO em vez de só a contagem.
        # Omitido quando vazio: campo presente e vazio e campo ausente diriam a
        # mesma coisa, e o ledger é lido por humano.
        **({"infra_assinaturas": list(classificacao.assinaturas)}
           if classificacao.assinaturas else {}),
        # Versão do JUIZ que produziu este veredito. Sem ela, uma correção no
        # classificador não tem como distinguir dado íntegro de dado viciado —
        # e a sequência seguiria andando sobre os dois.
        "classificador": CLASSIFICADOR_VERSAO,
    }
    execucoes.append(entrada)
    # `streak` gravado = sequência de CI DEPOIS desta entrada. Numa entrada
    # local ele repete o valor anterior, deixando explícito que nada mudou.
    streak, dias = sequencia_oficial(execucoes)
    entrada["streak"] = streak
    ledger["schema"] = SCHEMA
    return Registro(streak=streak, entrada=entrada, dias=dias, origem=origem,
                    alvo_mudou=alvo_mudou and origem == ORIGEM_OFICIAL)


def _resolver_alvo(explicito: str | None, usar_fixture: bool = False) -> str:
    if usar_fixture:
        # A identidade do fixture vem do que ele SERVE, não da URL: a porta é
        # efêmera e mudaria a cada noite, zerando a sequência para sempre.
        sys.path.insert(0, str(ROOT))
        from fixture_target.servir import identidade

        return identidade()
    if explicito:
        return explicito
    if os.environ.get("WEBQA_TARGET_URL"):
        return os.environ["WEBQA_TARGET_URL"]
    try:  # reusa a resolução oficial (config.yaml + env) em vez de duplicá-la
        sys.path.insert(0, str(ROOT))
        from webqa.config import load_settings

        return load_settings().target_url
    except Exception:
        return ""


def _quarentena_texto(execucoes: list[dict]) -> str:
    """Sufixo do placar listando as versões em quarentena, com o motivo.

    Sem o motivo à vista, "0/10" depois de nove noites parece bug do script; com
    ele, fica claro que o ledger recusou dado viciado de propósito.
    """
    contagem = quarentena(execucoes)
    if not contagem:
        return ""
    partes = [f"v{versao} ({n} entrada{'s' if n > 1 else ''}) — {DEFEITOS_CONHECIDOS[versao]}"
              for versao, n in contagem.items()]
    texto = " · quarentena: " + "; ".join(partes)

    oficiais = [e for e in execucoes if e.get("origem") == ORIGEM_OFICIAL]
    if oficiais and all(em_quarentena(e) for e in oficiais):
        texto += (" · toda a sequência oficial está em quarentena: a contagem "
                  "RECOMEÇA do zero, sem apagar o histórico")
    return texto


def violacoes_do_contrato(caminho: Path = CONTRATO_PADRAO) -> int:
    """Quantos FAILs o alvo fixture deve produzir, lidos do contrato.

    Ausência do arquivo devolve 0, e o painel omite o número em vez de chutar:
    narrativa com número inventado é pior que narrativa sem número.
    """
    try:
        return len(json.loads(caminho.read_text(encoding="utf-8"))["devem_falhar"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0


def _sha_do_alvo_de_hoje() -> str:
    """Identidade do alvo fixture AGORA, para o painel saber se ela mudou.

    Devolve `""` quando não dá para resolver — e aí o painel simplesmente não
    afirma o motivo, em vez de chutar. Dizer "o alvo mudou" sem saber seria
    inventar explicação para um zero, que é pior que não explicá-lo.
    """
    try:
        sys.path.insert(0, str(ROOT))
        from fixture_target.servir import identidade

        return sha256_do_alvo(identidade())
    except Exception:
        return ""


def escrever_painel(ledger: dict, destino: Path, meta: int = META_PADRAO,
                    ledger_path: str = "docs/lgpd-estabilidade.json") -> Path:
    """Renderiza o painel. NUNCA escreve no ledger — só lê e desenha."""
    sys.path.insert(0, str(ROOT))       # execução direta: python scripts/estabilidade.py
    from webqa.estabilidade_html import montar

    html = montar(ledger, caminhada(ledger.get("execucoes") or []),
                  violacoes_do_contrato(), meta=meta, ledger_path=ledger_path,
                  sha_do_alvo_atual=_sha_do_alvo_de_hoje())
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html, encoding="utf-8")
    return destino


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("summary", nargs="?", type=Path, default=SUMMARY_PADRAO)
    parser.add_argument("--ledger", type=Path, default=LEDGER_PADRAO)
    parser.add_argument("--alvo", default=None, help="URL do alvo (só o sha256 é gravado)")
    parser.add_argument("--alvo-fixture", action="store_true",
                        help="usa a identidade do alvo fixture (estável entre execuções, "
                             "ao contrário da porta efêmera)")
    parser.add_argument("--meta", type=int, default=META_PADRAO)
    parser.add_argument("--dry-run", action="store_true",
                        help="classifica e imprime sem gravar (uso em CI, que não commita)")
    parser.add_argument("--recompute", action="store_true",
                        help="reavalia o ledger existente sem registrar execução nova "
                             "(auditoria: mostra a sequência e a quarentena atuais)")
    parser.add_argument("--painel", nargs="?", type=Path, const=PAINEL_PADRAO, default=None,
                        help="gera o painel HTML do ledger (default: report/estabilidade.html). "
                             "Só LÊ o ledger — combina com --recompute para auditar sem gravar")
    args = parser.parse_args(argv)

    if args.painel is not None:
        # Gerar o painel nunca escreve no ledger, em nenhuma combinação de
        # flags: é leitura mais renderização. Assim `--painel` é seguro no
        # GitHub, onde nada pode tocar o arquivo (docs/VPS.md).
        destino = escrever_painel(carregar_ledger(args.ledger), args.painel,
                                  meta=args.meta, ledger_path=str(args.ledger))
        print(f"painel: {destino}")
        if not args.recompute:
            return 0

    if args.recompute:
        # Auditoria pura: nenhuma classificação, nenhuma escrita. Existe porque a
        # sequência é DERIVADA do histórico — logo é verificável a qualquer
        # momento, sem depender de uma execução nova da suíte.
        ledger = carregar_ledger(args.ledger)
        streak, dias = sequencia_oficial(ledger["execucoes"])
        plural = "dia" if dias == 1 else "dias"
        historicas = sum(1 for e in ledger["execucoes"] if e.get("origem") == "ci")
        linha = (f"Recompute: streak {streak}/{args.meta} "
                 f"({ORIGEM_OFICIAL}, {dias} {plural} contado{'s' if dias != 1 else ''}, "
                 f"{len(ledger['execucoes'])} entrada(s) no ledger)")
        if historicas:
            linha += f" · histórico: {historicas} execução(ões) 'ci', fora da conta"
        print(linha + _quarentena_texto(ledger["execucoes"]))
        return 0

    if not args.summary.exists():
        print(f"summary não encontrado: {args.summary} — rode a suíte antes.", file=sys.stderr)
        return 2

    classificacao = classificar(json.loads(args.summary.read_text(encoding="utf-8")))
    alvo = _resolver_alvo(args.alvo, usar_fixture=args.alvo_fixture)
    if not alvo:
        print("alvo indeterminado: defina WEBQA_TARGET_URL, use --alvo ou --alvo-fixture.",
              file=sys.stderr)
        return 2

    ledger = carregar_ledger(args.ledger)
    registro = registrar(ledger, classificacao, sha256_do_alvo(alvo))

    def _placar() -> str:
        plural = "dia" if registro.dias == 1 else "dias"
        distintos = "distinto" if registro.dias == 1 else "distintos"
        placar = (f"streak {registro.streak}/{args.meta} "
                  f"({ORIGEM_OFICIAL}, {registro.dias} {plural} {distintos})")
        # Entradas de antes da emenda continuam no ledger; dizer isso evita que
        # alguém leia "0/10" como perda de histórico.
        historicas = sum(1 for e in ledger["execucoes"] if e.get("origem") == "ci")
        if historicas:
            placar += f" · histórico: {historicas} execução(ões) 'ci' anterior(es), fora da conta"
        placar += _quarentena_texto(ledger["execucoes"])
        return placar

    if registro.ignorada:
        print("Execução sem testes de navegador — ignorada (não conta nem zera). "
              f"{_placar()}")
        return 0
    if registro.duplicada:
        print(f"Execução {classificacao.generated_at} já registrada — nada a fazer. "
              f"{_placar()}")
        return 0

    if registro.alvo_mudou:
        print(f"Alvo mudou desde a última execução '{ORIGEM_OFICIAL}': sequência "
              "reiniciada (métrica é por alvo).")
    if classificacao.limpa:
        print(f"Execução limpa: {classificacao.browser_total} testes de navegador, 0 flakes.")
    else:
        print(f"Flake de INFRA em {len(classificacao.flakes)} de {classificacao.browser_total} "
              "testes de navegador.")
        for teste in classificacao.flakes[:5]:
            print(f"  - {teste}")

    dia = registro.entrada["dia_utc"] if registro.entrada else "?"
    if registro.origem == ORIGEM_OFICIAL:
        print(f"Origem: {ORIGEM_OFICIAL} — conta no máximo uma vez por dia UTC (dia {dia}).")
    else:
        # Registrada para auditoria, mas fora da métrica: execução em ambiente
        # não oficial não é evidência de estabilidade do ambiente oficial.
        print(f"Origem: {registro.origem} — entrada informativa, NÃO avança nem zera "
              f"a sequência (só '{ORIGEM_OFICIAL}' conta; declare WEBQA_ORIGEM no "
              "container oficial).")

    if not args.dry_run:
        args.ledger.parent.mkdir(parents=True, exist_ok=True)
        args.ledger.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")

    print(_placar() + (" (dry-run: ledger não gravado)" if args.dry_run else ""))
    if registro.streak >= args.meta:
        print("FASE 2 DESTRAVADA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
