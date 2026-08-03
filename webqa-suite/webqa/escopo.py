"""Escopo autorizado da Fase C — a trava que separa auditoria de intrusão.

A técnica da Fase C (pedir ao servidor o que ele não ofereceu) é a mesma de um
atacante; o que a mantém do lado da auditoria é **autorização + escopo**. Este
módulo é o escopo, e ele é estrutural: um host que não está no
`escopo-autorizado.yaml` não é "pulado com aviso" — não existe caminho no
programa que fabrique uma requisição ativa para ele, porque `esta_no_escopo`
devolve `False` e todo consumidor a consulta primeiro.

Decisões que o código carrega (e que as revisões custaram a fixar):

* **Origem EXATA, via `auth.origem_de`, NÃO `dominio.mesma_origem`.** `mesma_origem`
  dobra `www`↔apex (bom para classificar asset de 1ª parte na Fase A, ruim para
  autorizar): autorizar `alvo.com` NÃO pode cobrir `www.alvo.com` nem
  `cdn.alvo.com`. Cada host é listado explicitamente, porque a prova de posse é
  por hostname. (Revisão 3, B3.1.)
* **`https` obrigatório.** A Fase C é contra host próprio publicado; o fixture
  local (passivo) não entra aqui.
* **Validação no CARREGAMENTO, não no probe.** Arquivo ausente, malformado, com
  data futura, ambiente inválido ou host que aparente gov/mil aborta a
  importação — a trava é fail-fast, não checagem de runtime.
* **Congelamento por hash (TOCTOU).** O hash do conteúdo carregado é gravado; o
  probe valida contra o snapshot em memória, nunca relê o arquivo. (R-C7.)

Somente stdlib + PyYAML (já dependência). NÃO importa `gates` e `esta_no_escopo`
é comparação de origem (string), sem rede. A prova de posse por IP (R-C6) é a
única parte que toca a rede: no CARREGAMENTO tira um snapshot dos IPs de cada
host via `rede.ips_de`, e `verificar_posse` compara os IPs atuais contra esse
snapshot ANTES do probe — divergência é takeover de subdomínio e aborta o alvo.
Importar `ips_de` torna `escopo` o quarto consumidor da fronteira, registrado em
`tests/test_fronteira_de_rede.py::FRONTEIRAS_DE_REDE` (regra da casa §2.11).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from webqa.auth import origem_de
from webqa.rede import ips_de

AMBIENTES_VALIDOS = frozenset({"producao", "homologacao", "sandbox"})

# A Fase C é contra host próprio publicado — sempre https. O snapshot de posse
# resolve na porta do serviço que será sondado.
_PORTA_HTTPS = 443

# Coarse: primeira barreira, NÃO exaustiva. O controle real é a autorização
# humana + CODEOWNERS; isto só pega o erro grosseiro de listar gov/mil por engano.
_SUFIXOS_BLOQUEADOS = (".gov", ".gov.br", ".mil", ".mil.br", ".jus.br")


def _parece_gov_ou_mil(origem: str) -> bool:
    host = (urlsplit(origem).hostname or "").lower()
    return any(host == s.lstrip(".") or host.endswith(s) for s in _SUFIXOS_BLOQUEADOS)


def _ips_resolvidos(host: str) -> frozenset[str]:
    """IPs atuais do host como conjunto de strings; vazio se não resolve.

    Nunca deixa `OSError` subir: falha de resolução vira conjunto vazio, que o
    chamador lê como 'sem posse' / divergência — jamais silêncio que se pareça
    com posse. Toca a rede via `rede.ips_de` (por isso `escopo` é consumidor da
    fronteira §2.11); nos testes, `getaddrinfo` é dublado.
    """
    try:
        return frozenset(str(ip) for ip in ips_de(host, _PORTA_HTTPS))
    except OSError:
        return frozenset()


@dataclass(frozen=True)
class EntradaEscopo:
    """Uma autorização, por host. Nasce validada — como o `Finding`."""

    origem: str          # esquema://host[:porta], EXATO (auth.origem_de)
    autorizado_por: str
    data: date
    evidencia: str       # link ou hash do aceite
    ambiente: str        # producao | homologacao | sandbox
    verificacao: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.autorizado_por.strip():
            raise ValueError(f"autorizado_por vazio para {self.origem!r}")
        if not self.evidencia.strip():
            raise ValueError(f"evidencia vazia para {self.origem!r}")
        if self.data > date.today():
            raise ValueError(f"data futura inválida em {self.origem!r}: {self.data.isoformat()}")
        if self.ambiente not in AMBIENTES_VALIDOS:
            raise ValueError(
                f"ambiente inválido em {self.origem!r}: {self.ambiente!r} "
                f"(use um de {sorted(AMBIENTES_VALIDOS)})")
        if not self.origem.startswith("https://"):
            raise ValueError(f"escopo exige https: {self.origem!r}")
        canonica = origem_de(self.origem)
        if canonica != self.origem:
            raise ValueError(
                f"origem não canônica: {self.origem!r}. Use exatamente {canonica!r} "
                "(o mesmo que auth.origem_de produz) — o arquivo tem de ser diffável.")

    @property
    def permite_escrita(self) -> bool:
        """C2 (interação com escrita) é proibida em produção."""
        return self.ambiente != "producao"


@dataclass(frozen=True)
class Escopo:
    """Conjunto de autorizações + o hash do arquivo que as originou."""

    entradas: tuple[EntradaEscopo, ...]
    hash_congelado: str
    # host → IPs resolvidos no carregamento (prova de posse, R-C6). Default
    # vazio mantém compatível a construção sem snapshot.
    ips_no_carregamento: dict = field(default_factory=dict)

    def _por_origem(self) -> dict[str, EntradaEscopo]:
        return {e.origem: e for e in self.entradas}

    def verificar_posse(self, host: str) -> frozenset[str]:
        """IPs PINADOS de `host` se a posse se confirma; conjunto vazio se não.

        Defesa contra takeover de subdomínio E contra DNS rebinding (R-C6, A#1):
        um host autorizado cujo IP mudou pode ter sido reapontado para infra de
        terceiro. Devolve o conjunto de IPs quando a resolução atual é não-vazia
        e IDÊNTICA ao snapshot — e o chamador conecta SÓ nesses IPs, sem
        re-resolver, fechando a janela entre esta checagem e a requisição.

        Conjunto VAZIO = sem posse: divergência (host reapontado), host não
        listado, snapshot vazio (não resolveu no carregamento), ou falha de
        resolução agora. Nunca exceção crua nem silêncio.

        O snapshot é do carregamento; esta comparação roda ANTES do probe, e os
        IPs devolvidos são os que o probe deve usar — nunca dentro do laço.
        """
        baseline = self.ips_no_carregamento.get(host)
        if not baseline:
            return frozenset()
        atuais = _ips_resolvidos(host)
        return atuais if atuais == baseline else frozenset()

    def esta_no_escopo(self, url: str) -> bool:
        """A origem EXATA da URL foi autorizada? (única pergunta que os probes fazem.)"""
        return origem_de(url) in self._por_origem()

    def entrada(self, url: str) -> EntradaEscopo:
        return self._por_origem()[origem_de(url)]

    def permite_escrita(self, url: str) -> bool:
        return self.esta_no_escopo(url) and self.entrada(url).permite_escrita


def carregar(path: str | Path) -> Escopo:
    """Carrega e VALIDA o escopo. Falha alto: qualquer defeito aborta, nunca degrada.

    A ausência do arquivo é erro de propósito — sem escopo declarado a Fase C não
    tem para onde apontar, e "rodar sem escopo" seria a intrusão que o módulo
    existe para impedir.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"escopo ausente: {p}. Fase C bloqueada até o escopo existir "
            "(docs/FASE-C.md §0). Copie escopo-autorizado.yaml.example.")
    bruto = p.read_text(encoding="utf-8")
    dados = yaml.safe_load(bruto) or {}
    alvos = dados.get("alvos") or []
    if not alvos:
        raise ValueError(f"escopo sem alvos declarados: {p}")

    entradas: list[EntradaEscopo] = []
    for a in alvos:
        bruta = str(a["origem"])
        origem = origem_de(bruta)
        if origem != bruta:
            raise ValueError(
                f"origem não canônica no arquivo: {bruta!r}. Use exatamente {origem!r} "
                "— o escopo tem de ser diffável (o revisor vê o que autoriza).")
        if _parece_gov_ou_mil(origem):
            raise ValueError(f"alvo bloqueado por política (gov/mil): {origem}")
        d = a["data"]
        entradas.append(EntradaEscopo(
            origem=origem,
            autorizado_por=str(a.get("autorizado_por", "")),
            data=d if isinstance(d, date) else date.fromisoformat(str(d)),
            evidencia=str(a.get("evidencia", "")),
            ambiente=str(a.get("ambiente", "")),
            verificacao=dict(a.get("verificacao") or {}),
        ))

    origens = [e.origem for e in entradas]
    duplicadas = {o for o in origens if origens.count(o) > 1}
    if duplicadas:
        raise ValueError(f"escopo com origem duplicada: {sorted(duplicadas)}")

    # Snapshot de posse por host, no carregamento (R-C6). Resolver aqui, e não
    # no probe, é o que dá a `verificar_posse` uma linha de base contra a qual
    # detectar takeover. Falha de resolução vira conjunto vazio, nunca aborta o
    # carregamento — a ausência de posse é decidida depois, por host.
    snapshot: dict[str, frozenset[str]] = {}
    for e in entradas:
        host = urlsplit(e.origem).hostname or ""
        snapshot[host] = _ips_resolvidos(host)

    return Escopo(
        entradas=tuple(entradas),
        hash_congelado=hashlib.sha256(bruto.encode("utf-8")).hexdigest(),
        ips_no_carregamento=snapshot,
    )
