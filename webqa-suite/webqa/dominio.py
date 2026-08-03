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

import re
import struct
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

    `remediacao` é o texto de correção. Opcional em A/B (retrocompatível), mas
    OBRIGATÓRIO em C: um achado de sondagem ativa sem o que fazer a respeito é
    só uma requisição intrusiva sem valor de auditoria. Passa pela MESMA
    sanitização de `evidencia`/`recurso` (segredo mascarado no construtor) e
    recusa markup — o laudo o renderiza, e texto de remediação não é lugar para
    HTML/`<script>`.
    """

    tipo: str
    recurso: str
    severidade: Severidade
    evidencia: str
    fase: Fase
    remediacao: str = ""
    # Referência de origem do achado (ex.: OWASP WSTG-CONF-004, CWE-538). Vem do
    # caminho curado na Fase C; opcional e retrocompatível como `remediacao`.
    procedencia: str = ""
    # Método HTTP que confirmou a existência (Fase C): "HEAD" ou, quando o HEAD
    # deu 405, "GET(range)". Alimenta o curl reproduzível (C3c). Rótulo interno,
    # não conteúdo de servidor — não passa por sanitize.
    metodo: str = "HEAD"

    def __post_init__(self) -> None:
        # `object.__setattr__` porque a instância é congelada — a sanitização
        # acontece ANTES de o objeto existir para o resto do programa.
        object.__setattr__(self, "evidencia", sanitize_text(str(self.evidencia)))
        object.__setattr__(self, "recurso", sanitize_text(str(self.recurso)))
        object.__setattr__(self, "remediacao", sanitize_text(str(self.remediacao)))
        object.__setattr__(self, "procedencia", sanitize_text(str(self.procedencia)))
        if self.severidade not in ("alta", "media", "baixa"):
            raise ValueError(f"severidade inválida: {self.severidade!r}")
        if self.fase not in ("A", "B", "C"):
            raise ValueError(f"fase inválida: {self.fase!r}")
        # Anti-markup sobre o valor JÁ sanitizado: o laudo exibe a remediação, e
        # HTML aqui viraria injeção no relatório.
        if self.remediacao.lstrip().startswith("<"):
            raise ValueError("remediação não pode conter markup")
        # A obrigatoriedade nasce no construtor, como a máscara: é impossível um
        # Finding de Fase C existir sem remediação, não uma regra a lembrar.
        if self.fase == "C" and not self.remediacao.strip():
            raise ValueError(f"Finding de Fase C exige remediação: {self.recurso}")

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


# Achados por nodeid da execução corrente. O relatório precisa de `severidade` e
# `fase` no summary.json, e a alternativa seria o template PARSEAR a mensagem de
# assert — reintroduzindo exatamente o "achado é string" que o value object veio
# eliminar. Aqui o dado viaja como dado; o ciclo de vida é a sessão pytest, como
# em webqa/metricas.py.
_ACHADOS_POR_TESTE: dict[str, list[Finding]] = {}

SEVERIDADE_ORDEM = {"alta": 0, "media": 1, "baixa": 2}


def registrar_achados(nodeid: str, achados: list[Finding]) -> None:
    if achados:
        _ACHADOS_POR_TESTE.setdefault(nodeid, []).extend(achados)


def achados_de(nodeid: str) -> list[Finding]:
    """Achados do teste, do mais severo ao menos — a ordem que o laudo usa."""
    return sorted(_ACHADOS_POR_TESTE.get(nodeid, []),
                  key=lambda a: SEVERIDADE_ORDEM.get(a.severidade, 9))


def limpar_achados() -> None:
    _ACHADOS_POR_TESTE.clear()


def find_secrets(texto: str, recurso: str, fase: Fase) -> list[Finding]:
    """Credenciais no texto, já como `Finding` — logo, já mascaradas.

    `fase` é OBRIGATÓRIA (sem default): a mesma varredura de segredo roda em A
    (asset de origem), B (arquivo baixado) e, no futuro, C (recurso sondado), e
    um default silencioso etiquetaria como passivo um achado que foi ativo. Quem
    chama diz de qual fase veio.

    Mora aqui e não em `sanitize.py` por camada: `sanitize` é a borda de escrita
    e não conhece o domínio; fazê-la importar `Finding` criaria ciclo, já que o
    `Finding` depende dela para existir. O MOTOR de detecção continua sendo o do
    `sanitize` (`encontrar_segredos`) — ponto único de verdade preservado.
    """
    return [Finding(tipo=f"segredo:{nome}", recurso=recurso, severidade=sev,
                    evidencia=f"{nome} encontrado no corpo de {recurso}", fase=fase)
            for nome, sev in encontrar_segredos(texto)]


# Assinaturas de formato (magic bytes). Só stdlib e só o começo do arquivo — a
# extensão e o Content-Type são DECLARAÇÕES do servidor; isto é o que o arquivo
# de fato é. Tabela compartilhada com a Fase B (docs/SEGURANCA.md §6).
_ASSINATURAS: tuple[tuple[str, bytes], ...] = (
    ("pdf", b"%PDF-"),
    ("png", b"\x89PNG\r\n\x1a\n"),
    ("gif", b"GIF87a"),
    ("gif", b"GIF89a"),
    ("jpeg", b"\xff\xd8\xff"),
    ("zip", b"PK\x03\x04"),
    ("gzip", b"\x1f\x8b"),
    ("webp", b"RIFF"),       # RIFF....WEBP; o prefixo já basta para separar de texto
)


def assinatura(dados: bytes | None) -> str:
    """Formato pelo conteúdo, "" quando não reconhecido (texto, JS, JSON…)."""
    if not dados:
        return ""
    for nome, prefixo in _ASSINATURAS:
        if dados.startswith(prefixo):
            return nome
    return ""


# ---------- Fase B: metadados e conteúdo de arquivos ----------
#
# Detecta PRESENÇA, nunca extrai o valor — minimização: o metadado é do titular,
# e a suíte não precisa do conteúdo para dizer que ele está lá. Stdlib pura;
# `Pillow`, `piexif` e `pypdf` foram rejeitadas em docs/SEGURANCA.md §9.

_EXIF_GPS = 0x8825                                  # ponteiro para a IFD de GPS
_EXIF_AUTORIA = (0x013B, 0x8298, 0x010F, 0x0110)    # Artist, Copyright, Make, Model


def _ifd_tags(tiff: bytes, offset: int, ordem: str) -> list[int]:
    """Tags de uma IFD TIFF. Devolve [] a qualquer sinal de corrupção."""
    if offset + 2 > len(tiff):
        return []
    (quantas,) = struct.unpack_from(ordem + "H", tiff, offset)
    tags = []
    for i in range(min(quantas, 512)):   # teto: arquivo corrompido não vira laço
        entrada = offset + 2 + i * 12
        if entrada + 12 > len(tiff):
            break
        tags.append(struct.unpack_from(ordem + "H", tiff, entrada)[0])
    return tags


def metadados_exif(dados: bytes | None) -> set[str]:
    """`{"gps", "autoria"}` conforme o que o JPEG carrega. Sem valores.

    Percorre os segmentos JPEG até o APP1 com cabeçalho Exif e lê a IFD0.
    Qualquer inconsistência devolve conjunto vazio: arquivo quebrado não é
    acusação, e um parser que "chuta" numa bateria de segurança é pior que
    parser nenhum.
    """
    achados: set[str] = set()
    if not dados or not dados.startswith(b"\xff\xd8"):
        return achados
    pos = 2
    while pos + 4 <= len(dados):
        if dados[pos] != 0xFF:
            break
        marcador = dados[pos + 1]
        if marcador == 0xDA:      # dados comprimidos: não há EXIF depois
            break
        (tamanho,) = struct.unpack_from(">H", dados, pos + 2)
        corpo = dados[pos + 4: pos + 2 + tamanho]
        if marcador == 0xE1 and corpo.startswith(b"Exif\x00\x00"):
            tiff = corpo[6:]
            if len(tiff) >= 8 and tiff[:2] in (b"II", b"MM"):
                ordem = "<" if tiff[:2] == b"II" else ">"
                (ifd0,) = struct.unpack_from(ordem + "I", tiff, 4)
                tags = _ifd_tags(tiff, ifd0, ordem)
                if _EXIF_GPS in tags:
                    achados.add("gps")
                if any(t in tags for t in _EXIF_AUTORIA):
                    achados.add("autoria")
            break
        pos += 2 + tamanho
    return achados


def metadados_pdf(dados: bytes | None) -> set[str]:
    """Presença de `/Author` ou `/Creator` num PDF — sem ler o valor."""
    if not dados or not dados.startswith(b"%PDF-"):
        return set()
    achados = set()
    if b"/Author" in dados:
        achados.add("autoria")
    if b"/Creator" in dados or b"/Producer" in dados:
        achados.add("ferramenta")
    return achados


# SVG é documento EXECUTÁVEL: `<script>` e handlers `on*=` rodam quando o SVG é
# aberto direto ou embutido inline. Vetor clássico de XSS em upload de avatar.
_SVG_SCRIPT = re.compile(rb"<\s*script\b", re.I)
_SVG_HANDLER = re.compile(rb"\son[a-z]+\s*=", re.I)
_SVG_JS_HREF = re.compile(rb"""(?:xlink:)?href\s*=\s*["']\s*javascript:""", re.I)


def svg_executavel(dados: bytes | None) -> list[str]:
    """Motivos pelos quais um SVG é executável. Lista vazia = inerte."""
    if not dados:
        return []
    motivos = []
    if _SVG_SCRIPT.search(dados):
        motivos.append("<script> embutido")
    if _SVG_HANDLER.search(dados):
        motivos.append("handler on*= inline")
    if _SVG_JS_HREF.search(dados):
        motivos.append("href javascript:")
    return motivos


_SOURCEMAP = re.compile(rb"//[#@]\s*sourceMappingURL\s*=\s*(\S+)")


def sourcemap_referenciado(dados: bytes | None) -> str:
    """URL do sourcemap declarado no bundle, `""` se não houver.

    Só LÊ a referência. Baixar o `.map` é requisição nova — logo Fase C, logo
    atrás do gate. Um sourcemap costuma trazer o código-fonte inteiro, e ir
    buscá-lo sem autorização é exatamente a linha que o desenho não cruza.
    """
    if not dados:
        return ""
    achado = _SOURCEMAP.search(dados)
    return achado.group(1).decode("ascii", errors="replace") if achado else ""


def parece_html(dados: bytes | None) -> bool:
    """Começo de documento HTML — usado para pegar asset executável que virou página.

    O caso real: um `.js` que o servidor devolve como a página de erro em HTML.
    O navegador recusa executar (nosniff) ou, pior, executa algo inesperado; de
    todo modo o app está quebrado e a declaração do servidor está mentindo.
    """
    if not dados:
        return False
    inicio = dados[:512].lstrip().lower()
    return inicio.startswith((b"<!doctype html", b"<html", b"<head", b"<body"))
