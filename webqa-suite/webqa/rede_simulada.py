"""Rede 3G e CPU lenta emuladas por CDP (GUI-PERF-02/03, OS-50).

`checks/frontend/test_rendering.py` e `checks/gui/test_interatividade.py` medem o
alvo na rede do runner: fibra de datacenter, CPU ociosa. É a condição em que
**nenhum** visitante está. Um alvo que pinta em 400ms ali pode levar seis
segundos num celular em 3G — e as duas medidas são verdadeiras, porque medem
coisas diferentes.

Este módulo é o outro lado: a mesma coleta, sob restrição declarada.

**Orçamento próprio, nunca o de fibra.** `thresholds.lcp_ms` (2500ms) descreve o
alvo sem restrição; cobrá-lo sob 3G reprovaria toda página do mundo, e cobrar
`gui_lcp_ms_rede_lenta` de uma medida de fibra aprovaria qualquer coisa. Réguas
diferentes não se comparam — e é por isso que as chaves são separadas, e não um
multiplicador aplicado à mesma chave.

**Por que CDP, e o preço disso.** O Playwright não expõe emulação de rede
neutra entre engines: `context.set_offline` liga e desliga, e não há meio-termo.
Estrangular no cliente (`page.route` com `sleep`) atrasaria o corpo da resposta
mas não o *handshake*, e portanto não mediria latência — o número sairia otimista
sem nada avisar. CDP mede o que se propõe a medir, e o preço é ser **Chromium
apenas**. O preço é pago na porta: a sessão que não abre vira `skip` nomeando a
incapacidade, nunca uma lista de engines escrita à mão (lição das OS-46/56 — a
engine que ganhar a API amanhã não pode ficar de fora por causa de uma constante).

**A fronteira que este módulo é.** Nenhum check pronuncia `Network.emulate*` ou
`Emulation.setCPUThrottlingRate`: os comandos vivem aqui e `tests/` prova que
vivem só aqui. É a mesma lição de `_contextos_de_gui` — detalhe de navegador
espalhado por `checks/` diverge no primeiro campo novo, e a divergência aparece
como um check estrangulando e o outro não.

Somente stdlib + PyYAML (já dependência).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
PERFIS_PADRAO = RAIZ / "data" / "gui-perfis.yaml"

ENV_PERFIL = "WEBQA_GUI_PERFIL_REDE"
PERFIL_PADRAO = "3g_rapido"

# `downloadThroughput` do CDP é em BYTES por segundo; o perfil é declarado em
# kbps porque é assim que rede se fala (e é assim que o Lighthouse documenta o
# preset). A conversão mora aqui, num lugar só, e é testada nas duas pontas: o
# erro clássico deste comando é passar kbps direto e emular uma rede oito vezes
# mais rápida do que a declarada — sem nada ficar vermelho.
BITS_POR_BYTE = 8
BITS_POR_KBIT = 1000

# Comandos do Chrome DevTools Protocol. Constantes, e não literais no meio da
# chamada, porque é sobre ELES que a guarda estrutural de `tests/` se apoia: um
# check que os pronunciasse por conta própria reintroduziria a fronteira que
# este módulo existe para manter.
COMANDO_HABILITA_REDE = "Network.enable"
COMANDO_REDE = "Network.emulateNetworkConditions"
COMANDO_CPU = "Emulation.setCPUThrottlingRate"


class SemCDP(RuntimeError):
    """A sessão CDP não abriu — a restrição NÃO foi aplicada.

    Erro próprio, e não `Exception` genérica, para que o check possa distinguir
    "esta engine não sabe estrangular" de "o alvo caiu". Confundir os dois faria
    uma queda do alvo sair do laudo como `skip`, que é o falso verde silencioso.
    """


@dataclass(frozen=True)
class PerfilDeRede:
    """Uma condição de rede e CPU nomeada. Congelado: é snapshot de configuração.

    `cpu_fator` mora aqui junto com a banda, e não num perfil à parte, porque a
    condição real é uma só: o celular barato tem rede ruim **e** CPU lenta ao
    mesmo tempo. Separar os dois produziria a combinação que não existe em campo
    — 3G com CPU de desktop — e mediria uma degradação mais leve do que a que a
    pessoa sente.
    """

    nome: str
    download_kbps: float
    upload_kbps: float
    latencia_ms: float
    cpu_fator: float

    @property
    def download_bytes_por_s(self) -> float:
        return self.download_kbps * BITS_POR_KBIT / BITS_POR_BYTE

    @property
    def upload_bytes_por_s(self) -> float:
        return self.upload_kbps * BITS_POR_KBIT / BITS_POR_BYTE

    def __str__(self) -> str:
        return (f"{self.nome} ({self.download_kbps:.0f} kbps down, "
                f"{self.upload_kbps:.0f} kbps up, {self.latencia_ms:.0f}ms RTT, "
                f"CPU ×{self.cpu_fator:g})")


def _numero(bruto: Mapping, chave: str, nome: str, *, minimo: float) -> float:
    """Lê e valida uma chave numérica do perfil.

    Validação na LEITURA, e não no uso: banda negativa vira, no CDP, uma condição
    que o navegador aceita e traduz para "sem limite" — a emulação silenciosamente
    não acontece e o check aprova o alvo sob fibra achando que mediu 3G. É o
    fail-closed da casa: configuração sem sentido falha onde a mensagem ainda
    sabe qual chave está errada.

    `minimo` difere por chave e cada diferença tem motivo: latência **0 é
    válida** (é a rede perfeita, e serve de perfil de controle), enquanto
    `cpu_fator` abaixo de 1 pediria ao navegador que rodasse MAIS RÁPIDO que a
    máquina, o que o CDP não faz — aceitá-lo produziria um perfil que não emula
    nada e cujo nome diz que emula.
    """
    if chave not in bruto:
        raise ValueError(f"perfil de rede {nome!r} sem {chave!r} em gui-perfis.yaml")
    try:
        valor = float(bruto[chave])
    except (TypeError, ValueError):
        raise ValueError(
            f"perfil de rede {nome!r}: {chave}={bruto[chave]!r} não é número") from None
    if valor < minimo:
        raise ValueError(
            f"perfil de rede {nome!r}: {chave}={valor:g} abaixo do mínimo {minimo:g}")
    return valor


def carregar_perfis_de_rede(caminho: str | Path | None = None) -> dict[str, PerfilDeRede]:
    """Lê o bloco `rede:` de `data/gui-perfis.yaml` → {nome: PerfilDeRede}."""
    dados = yaml.safe_load(Path(caminho or PERFIS_PADRAO).read_text(encoding="utf-8")) or {}
    perfis: dict[str, PerfilDeRede] = {}
    for nome, bruto in (dados.get("rede") or {}).items():
        nome = str(nome)
        if not isinstance(bruto, Mapping):
            raise ValueError(f"perfil de rede {nome!r} não é um mapa em gui-perfis.yaml")
        perfis[nome] = PerfilDeRede(
            nome=nome,
            download_kbps=_numero(bruto, "download_kbps", nome, minimo=0.0),
            upload_kbps=_numero(bruto, "upload_kbps", nome, minimo=0.0),
            latencia_ms=_numero(bruto, "latencia_ms", nome, minimo=0.0),
            cpu_fator=_numero(bruto, "cpu_fator", nome, minimo=1.0),
        )
    if not perfis:
        raise ValueError("gui-perfis.yaml não declara nenhum perfil de rede")
    return perfis


def perfil_de_rede(nome: str | None, perfis: Mapping[str, PerfilDeRede]) -> PerfilDeRede:
    """O perfil pedido, ou ERRO nomeando os válidos.

    Fail-closed pela mesma razão de `viewports_configurados`: um typo
    (`3g_rapdio`) não pode degenerar em "rodou sem estrangular e passou". Esse é
    o pior verde possível — o check informa que mediu sob 3G, e mediu fibra.
    """
    # `strip()` ANTES do default, e não depois: `WEBQA_GUI_PERFIL_REDE=` (ou com
    # espaços) é o caso real de quem exporta a variável vazia num script de CI, e
    # ele significa "não escolhi", não "escolhi o perfil de nome vazio". Mesma
    # ordem de `viewports_configurados`, e pela mesma razão.
    escolhido = (nome or "").strip().lower() or PERFIL_PADRAO
    if escolhido not in perfis:
        raise ValueError(
            f"perfil de rede desconhecido em {ENV_PERFIL}: {escolhido!r}. "
            f"Válidos: {', '.join(perfis)}.")
    return perfis[escolhido]


def parametros_de_rede(perfil: PerfilDeRede) -> dict:
    """Argumentos de `Network.emulateNetworkConditions`. Função PURA.

    `offline: False` é explícito, e não omitido, porque o comando exige o campo —
    e porque a diferença entre "rede lenta" e "sem rede" é justamente o que a
    OS-47 já mede em outro check. Um `offline` acidentalmente verdadeiro aqui
    faria este check virar o daquela OS, medindo outra coisa com este nome.
    """
    return {
        "offline": False,
        "latency": perfil.latencia_ms,
        "downloadThroughput": perfil.download_bytes_por_s,
        "uploadThroughput": perfil.upload_bytes_por_s,
    }


def parametros_de_cpu(perfil: PerfilDeRede) -> dict:
    """Argumentos de `Emulation.setCPUThrottlingRate`. Função PURA."""
    return {"rate": perfil.cpu_fator}


def estrangular(pagina, perfil: PerfilDeRede) -> None:
    """Aplica rede e CPU do perfil à página, via sessão CDP do contexto dela.

    **Antes do `goto`, sempre.** Emulação ligada depois da carga mede uma página
    que já baixou tudo em fibra: o número sai bom e descreve uma condição que
    ninguém viveu. Não há como um teste detectar essa inversão pelo resultado —
    ele simplesmente passa.

    **Morre com o contexto.** A sessão é do par (contexto, página) que o chamador
    abriu, e `contexto_gui` fecha os contextos que abriu num `finally`. É a mesma
    disciplina do R20 em versão rede: estrangulamento vazado para a página de
    sessão faria `checks/frontend/test_rendering.py` medir LCP sob 3G sem
    declarar isso — e o LCP sairia ruim sem nada estar errado no alvo.

    Levanta `SemCDP` quando a engine não fala o protocolo. Sem lista de engines:
    a incapacidade é perguntada ao navegador, não consultada numa constante que
    envelhece.
    """
    try:
        sessao = pagina.context.new_cdp_session(pagina)
    except Exception as exc:                      # engine sem CDP (firefox/webkit)
        raise SemCDP(
            "Sessão CDP indisponível nesta engine — a emulação de rede e de CPU NÃO "
            "foi aplicada, e medir sem ela seria medir fibra com nome de 3G. "
            f"Rode a dimensão gui em chromium para obter o número ({exc}).") from exc
    sessao.send(COMANDO_HABILITA_REDE)
    sessao.send(COMANDO_REDE, parametros_de_rede(perfil))
    sessao.send(COMANDO_CPU, parametros_de_cpu(perfil))


def avaliar_pintura(fcp_ms: float | None, lcp_ms: float | None, *,
                    fcp_max: float, lcp_max: float) -> list[str]:
    """Estouros de pintura sob restrição, um por linha. Puro.

    `None` NÃO vira problema: pintura não observada é ausência de medida, e
    ausência nunca vira zero nem veredito (`webqa/metricas.py`). Quem chama
    decide o que dizer sobre ela.
    """
    problemas = []
    if fcp_ms is not None and fcp_ms > fcp_max:
        problemas.append(
            f"FCP {fcp_ms:.0f}ms acima do orçamento de rede lenta ({fcp_max:.0f}ms) — "
            "sob 3G a tela fica em branco por esse tempo, e é o intervalo em que "
            "quem visita decide se espera ou desiste.")
    if lcp_ms is not None and lcp_ms > lcp_max:
        problemas.append(
            f"LCP {lcp_ms:.0f}ms acima do orçamento de rede lenta ({lcp_max:.0f}ms) — "
            "o conteúdo principal demora esse tempo para existir na tela.")
    return problemas


def avaliar_bloqueio(tbt_ms: float, *, tbt_max: float) -> list[str]:
    """Estouro de bloqueio sob CPU lenta. Puro.

    Orçamento separado do `gui_tbt_ms` de CPU plena pela mesma razão que a
    pintura: sob ×4 o mesmo trabalho custa quatro vezes mais, e cobrar a régua de
    desktop reprovaria alvo conforme. O que este número procura não é "o alvo é
    lento": é trabalho síncrono que só aparece quando a máquina é modesta.
    """
    problemas = []
    if tbt_ms > tbt_max:
        problemas.append(
            f"TBT {tbt_ms:.0f}ms acima do orçamento de CPU lenta ({tbt_max:.0f}ms) — "
            "num aparelho ×4 mais lento a thread principal fica indisponível por esse "
            "tempo somado, e nem o toque nem a tecla produzem efeito enquanto isso.")
    return problemas


def resumo_da_condicao(perfil: PerfilDeRede) -> str:
    """A frase que acompanha TODA medida deste módulo no laudo.

    Existe porque um LCP de 3800ms sem a condição ao lado é um número que mente
    por omissão: lido como medida de fibra, descreve um alvo quebrado; lido com a
    condição, descreve um alvo normal sob 3G. A diferença entre as duas leituras
    é esta linha.
    """
    return f"Condição emulada: {perfil}. Orçamentos próprios — NÃO são os de fibra."
