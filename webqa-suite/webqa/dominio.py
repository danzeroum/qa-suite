"""Linguagem ubíqua da dimensão `seguranca` — value objects imutáveis.

Ver `docs/SEGURANCA.md`. Até aqui um achado era uma string de mensagem de
`assert`: dado sem modelo, reescrito em cada check. Com `Finding` e `Recurso`,
checks, relatório e contrato do alvo fixture passam a falar o mesmo vocabulário.

A invariante que dá razão a este módulo é ética, não técnica:

    **é impossível instanciar um `Finding` com segredo em claro.**

A `evidencia` passa por `webqa.sanitize` no CONSTRUTOR. Não é uma regra que cada
check precisa lembrar de seguir — é uma impossibilidade estrutural. Republicar um
segredo encontrado reencena exatamente o risco que a bateria existe para apontar,
e a única defesa confiável contra o esquecimento é não deixar o caminho existir.

Somente stdlib.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal
from urllib.parse import urlsplit

from webqa.sanitize import encontrar_segredos, sanitize_text

Severidade = Literal["alta", "media", "baixa"]
Fase = Literal["A", "B", "C"]

# Teto de leitura de corpo. Análise acontece em MEMÓRIA; nada é gravado em disco,
# nem em `report/`. O teto existe para que um asset de 80 MB não derrube a
# execução — e estourá-lo NÃO é aprovação: ver `Corpo.avaliavel`.
TETO_CORPO_BYTES = 512_000


@dataclass(frozen=True)
class Finding:
    """Um achado de segurança, com a evidência já mascarada.

    `recurso` é a URL (ou identificação) de onde veio; `fase` diz qual fase do
    desenho o produziu, o que mantém rastreável o que é passivo (A, B) e o que
    exigiu autorização explícita (C).
    """

    tipo: str
    recurso: str
    severidade: Severidade
    evidencia: str
    fase: Fase

    def __post_init__(self) -> None:
        # `object.__setattr__` porque a instância é congelada — a sanitização
        # acontece ANTES de o objeto existir para o resto do programa.
        object.__setattr__(self, "evidencia", sanitize_text(str(self.evidencia)))
        object.__setattr__(self, "recurso", sanitize_text(str(self.recurso)))
        if self.severidade not in ("alta", "media", "baixa"):
            raise ValueError(f"severidade inválida: {self.severidade!r}")
        if self.fase not in ("A", "B", "C"):
            raise ValueError(f"fase inválida: {self.fase!r}")

    @property
    def contem_segredo_em_claro(self) -> bool:
        """Sempre False para instância válida — existe para o teste PROVAR."""
        return bool(encontrar_segredos(self.evidencia))

    def __str__(self) -> str:
        return f"[{self.severidade}] {self.tipo} em {self.recurso}: {self.evidencia}"


@dataclass(frozen=True)
class Corpo:
    """Resultado de uma leitura de corpo — nunca um `bytes` solto.

    O par (dados, truncado) é o que impede o engano mais caro desta dimensão:
    corpo grande demais devolve `dados=None`, e um check que tratasse isso como
    "nada encontrado" transformaria teto de memória em atestado de segurança.
    Quem consome verifica `avaliavel` antes de concluir qualquer coisa.
    """

    dados: bytes | None
    truncado: bool = False
    motivo: str = ""

    @property
    def avaliavel(self) -> bool:
        return self.dados is not None


def _raiz_do_host(host: str) -> str:
    """Host sem `www.` e sem ponto final — normalização do alvo e dos assets.

    Mesma normalização do inventário de terceiros (`trackers._normalize_domain`),
    reusada aqui de propósito: se as duas divergirem, o mesmo host seria "primeira
    parte" num relatório e "terceiro" no outro.
    """
    host = (host or "").strip().lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def mesma_origem(url: str, origem: str) -> bool:
    """O recurso veio do próprio alvo? `www` e sem-`www` são o MESMO site.

    Casamento EXATO após tirar o `www.`, não por sufixo: `cdn.alvo.com` é
    infraestrutura separada, com configuração e dono possivelmente distintos, e
    tratá-lo como primeira parte esconderia justamente o caso que a Fase A quer
    ver — um script de outro host servido sem cabeçalho de segurança.
    """
    alvo = _raiz_do_host(urlsplit(origem).hostname or "")
    recurso = _raiz_do_host(urlsplit(url).hostname or "")
    return bool(alvo) and alvo == recurso


@dataclass(frozen=True, eq=False)
class Recurso:
    """Uma resposta observada no carregamento — metadados, sem o corpo.

    `eq=False` de propósito: dois recursos com a mesma URL não são "o mesmo"
    (a página pode buscar o mesmo asset duas vezes, e as duas respostas são
    fatos distintos). Identidade por objeto, e o `Recurso` segue hashável.

    O corpo NÃO é campo: é lido sob demanda por `ler_corpo`, em memória, com
    teto. Guardar bytes aqui faria o log de rede inteiro residir na RAM e, pior,
    tornaria trivial alguém serializar o objeto para disco.
    """

    url: str
    status: int
    headers: Mapping[str, str]
    content_type: str
    size: int
    scheme: str
    from_origin: bool
    # Fonte do corpo e cache da leitura ficam fora da igualdade e do repr: são
    # mecanismo, não identidade.
    fonte: Callable[[], bytes] | None = field(default=None, repr=False, compare=False)
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def de_resposta(cls, resposta, origem: str) -> Recurso:
        """Constrói a partir de uma resposta do Playwright (ou de um dublê).

        Aceita qualquer objeto com `url`, `status`, `headers` e `body()` — é o
        que permite testar o mapeamento sem subir navegador.
        """
        brutos = dict(getattr(resposta, "headers", {}) or {})
        headers = {str(k).lower(): str(v) for k, v in brutos.items()}
        content_type = headers.get("content-type", "").split(";")[0].strip().lower()
        try:
            tamanho = int(headers.get("content-length", "-1"))
        except (TypeError, ValueError):
            tamanho = -1        # desconhecido; NUNCA 0, que significaria "vazio"
        url = str(getattr(resposta, "url", ""))
        return cls(
            url=url,
            status=int(getattr(resposta, "status", 0) or 0),
            headers=MappingProxyType(headers),
            content_type=content_type,
            size=tamanho,
            scheme=(urlsplit(url).scheme or "").lower(),
            from_origin=mesma_origem(url, origem),
            fonte=getattr(resposta, "body", None),
        )

    def cabecalho(self, nome: str) -> str:
        return self.headers.get(nome.lower(), "")


def ler_corpo(recurso: Recurso, max_bytes: int = TETO_CORPO_BYTES) -> Corpo:
    """Lê o corpo em MEMÓRIA, com teto. Nunca grava em disco.

    Acima do teto devolve `dados=None` e `truncado=True` — e não os primeiros
    512 KB. Analisar um pedaço e concluir "sem segredo" seria pior que não
    analisar: daria um veredito sobre o que não foi lido.

    O resultado é memoizado porque a leitura de corpo do Playwright pode não
    sobreviver a uma segunda chamada, e um check não deveria precisar saber
    disso para funcionar.
    """
    if "corpo" in recurso._cache:
        return recurso._cache["corpo"]

    if recurso.fonte is None:
        corpo = Corpo(None, motivo="recurso sem fonte de corpo (não navegado)")
    elif recurso.size > max_bytes:
        # Content-Length já denuncia o excesso: nem chega a puxar os bytes.
        corpo = Corpo(None, truncado=True,
                      motivo=f"{recurso.size} bytes declarados excedem o teto de {max_bytes}")
    else:
        try:
            dados = recurso.fonte()
        except Exception as erro:      # corpo indisponível (redirect, 204, aborto)
            corpo = Corpo(None, motivo=f"corpo indisponível: {type(erro).__name__}")
        else:
            dados = dados or b""
            corpo = (Corpo(None, truncado=True,
                           motivo=f"{len(dados)} bytes excedem o teto de {max_bytes}")
                     if len(dados) > max_bytes else Corpo(dados))
    recurso._cache["corpo"] = corpo
    return corpo


def texto_do_corpo(corpo: Corpo) -> str:
    """Corpo como texto para varredura. Bytes indecodificáveis não derrubam nada."""
    if not corpo.avaliavel:
        return ""
    return corpo.dados.decode("utf-8", errors="replace")
