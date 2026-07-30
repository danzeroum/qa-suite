"""Sanitização de PII incidental capturada de sites-alvo (minimização, LGPD Art. 6º/46).

A suíte é caixa-preta contra alvos arbitrários: conteúdo de falhas, erros de
console e URLs podem carregar dados pessoais do alvo. A regra é mascarar na
BORDA DE ESCRITA (antes de persistir ou exibir), nunca depois.

Hierarquia aplicada: não coletar > mascarar > reter pouco > criptografar.
Somente stdlib (re, urllib) — sem dependências novas.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# Parâmetros de URL cujo VALOR nunca deve aparecer em relatório/log.
_SENSITIVE_PARAMS = (
    "token", "key", "apikey", "api_key", "senha", "password", "pass",
    "secret", "auth", "authorization", "bearer", "x-api-key", "session", "sid",
    "cpf", "email",
)

# Segredos de credencial. Mesma doutrina do PII: as expressões que DETECTAM são
# as que MASCARAM — ponto único de verdade, e um padrão novo passa a valer nas
# duas pontas no mesmo commit.
#
# O valor é substituído pelo TIPO, nunca por um prefixo "só para ajudar a
# depurar": republicar metade de uma chave é republicar a chave para quem tem o
# resto. Reportar tipo + local é suficiente para agir; o valor não é.
#
# Nada aqui casa por ENTROPIA. Um sha256 em hex, um hash de build ou um id de
# 64 caracteres não são segredos, e uma heurística de entropia os acusaria em
# massa — falso positivo em bateria de segurança custa a credibilidade da
# bateria inteira. Só entram formatos com prefixo declarado pelo emissor, ou
# valor precedido de um NOME que diz o que ele é.
_SEGREDOS: tuple[tuple[str, re.Pattern, str], ...] = (
    ("PEM_PRIVATE_KEY", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"), "alta"),
    ("AWS_ACCESS_KEY_ID", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "alta"),
    ("GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), "alta"),
    ("STRIPE_SECRET_KEY", re.compile(r"\bsk_live_[0-9A-Za-z]{16,}\b"), "alta"),
    ("GOOGLE_API_KEY", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "alta"),
    # JWT: três segmentos base64url. Exigir os dois pontos evita casar qualquer
    # palavra que comece com "eyJ".
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"),
     "alta"),
    # Genérico por NOME: `api_key: "..."`, `secret = '...'`, `"token":"..."`.
    # Severidade média porque o nome pode mentir (um `token` de CSRF público
    # casa aqui) — mas mascarar de todo jeito é o lado seguro do erro.
    ("CREDENCIAL_NOMEADA",
     re.compile(r"""(?i)\b(?:api[_-]?key|secret|token|password|passwd|senha)\b"""
                r"""["'\s]*[:=]\s*["']([^"'\s]{8,})["']"""), "media"),
)

# Cabeçalho `Authorization` na forma com DOIS-PONTOS, que o `_PARAM` não alcança
# (ele só casa `nome=valor`) e o `CREDENCIAL_NOMEADA` também não (exige aspas e
# não lista `authorization`).
#
# Fica AQUI, e deliberadamente FORA de `_SEGREDOS`: aquela tupla é a de
# DETECÇÃO — alimenta `encontrar_segredos`/`find_secrets` e vira `Finding` com
# severidade. Uma expressão de `authorization:` ali acusaria prosa inocente
# ("Authorization: required", numa página de documentação do alvo) como achado
# de segurança alta. É o falso positivo em massa que este módulo argumenta, logo
# acima, custar "a credibilidade da bateria inteira". Esconder é barato e não
# tem efeito colateral; acusar tem.
#
# O `(?![\s\[])` torna a substituição idempotente. O `\[` sozinho não bastava:
# com o separador `\s*[:=]\s*` sendo guloso, a expressão simplesmente DEVOLVIA o
# espaço para satisfazer o lookahead e casava " [AUTHORIZATION]" como valor —
# reaplicar comia o espaço em silêncio. Barrar espaço também fecha o retrocesso.
_AUTHORIZATION = re.compile(r"(?i)\b(authorization)\b(\s*[:=]\s*)(?![\s\[])[^\r\n,;\"']+")

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# CPF com e sem pontuação (limites para não engolir números maiores).
_CPF = re.compile(r"(?<!\d)(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})(?!\d)")
# Telefone BR: +55 opcional, DDD com/sem parênteses, 8-9 dígitos com separadores.
_FONE_BR = re.compile(r"(?<!\d)(?:\+?55[\s.-]?)?(?:\(?\d{2}\)?[\s.-]?)?\d{4,5}[\s.-]\d{4}(?!\d)")
_PARAM = re.compile(
    r"(?i)\b(" + "|".join(_SENSITIVE_PARAMS) + r")=([^&\s\"'<>]+)"
)


# Valores que este PROCESSO sabe serem segredos, mascarados por igualdade
# literal e não por formato. É o complemento necessário das duas tabelas acima:
# elas reconhecem credencial de EMISSOR conhecido (`AKIA…`, `ghp_…`) ou precedida
# de um nome; a senha de um Basic Auth de nginx não tem prefixo, não tem formato
# e não vem rotulada — só quem a configurou sabe que aquilo é segredo.
#
# Quem popula é `webqa.auth.Credencial`, no construtor. O registro vive aqui, e
# não lá, porque este módulo é o ponto único de verdade sobre "o que é dado
# sensível" — inclusive quando a resposta veio do ambiente em vez de uma regex.
_VALORES_SENSIVEIS: dict[str, str] = {}


def registrar_valor_sensivel(valor: str, rotulo: str = "SEGREDO") -> None:
    """Passa a mascarar este valor literal em toda saída sanitizada.

    Sem piso de tamanho de propósito: um valor curto embaralha o relatório, mas
    a alternativa é deixá-lo passar em claro. Vazar é pior que embaralhar, e a
    garantia só vale se valer para toda senha. Quem avisa sobre o incômodo é
    `webqa.auth`, que fala a língua do operador.
    """
    if valor:
        _VALORES_SENSIVEIS[valor] = rotulo


def esquecer_valores_sensiveis() -> None:
    """Esvazia o registro — isolamento entre casos de teste."""
    _VALORES_SENSIVEIS.clear()


def mascarar_valores_registrados(text: str) -> str:
    """Substitui cada valor registrado pelo seu rótulo.

    Substituição LITERAL, nunca regex: uma senha pode conter `.`, `*`, `(` e
    qualquer outro metacaractere, e compilá-la como padrão iria de erro de
    sintaxe a casamento errado.

    Do mais LONGO para o mais curto, e isso é obrigatório: com `s3nh4` e
    `joao:s3nh4` ambos registrados, começar pelo curto deixaria `joao:[SENHA]` —
    que entrega o usuário e ainda prova onde o par estava.
    """
    if not text or not _VALORES_SENSIVEIS:
        return text
    for valor in sorted(_VALORES_SENSIVEIS, key=len, reverse=True):
        if valor in text:
            text = text.replace(valor, f"[{_VALORES_SENSIVEIS[valor]}]")
    return text


def mascarar_segredos(text: str) -> str:
    """Substitui credenciais pelo TIPO. Texto sem segredo passa inalterado."""
    if not text:
        return text
    for nome, padrao, _severidade in _SEGREDOS:
        if nome == "CREDENCIAL_NOMEADA":
            # Preserva o NOME do campo (útil para localizar) e come só o valor.
            # `rotulo=nome` amarra o valor no momento da definição: a lambda é
            # consumida aqui dentro, mas depender disso é convite a bug futuro.
            text = padrao.sub(
                lambda m, rotulo=nome: m.group(0).replace(m.group(1), f"[{rotulo}]"), text)
        else:
            text = padrao.sub(f"[{nome}]", text)
    return text


def encontrar_segredos(text: str) -> list[tuple[str, str]]:
    """(tipo, severidade) de cada formato de credencial presente no texto.

    Mesmas expressões que mascaram — quem detecta e quem esconde não podem
    divergir, senão a suíte acusa o que não esconde ou esconde o que não acusa.
    """
    if not text:
        return []
    return [(nome, sev) for nome, padrao, sev in _SEGREDOS if padrao.search(text)]


def sanitize_text(text: str) -> str:
    """Mascara e-mail, CPF, telefone BR, parâmetros sensíveis e CREDENCIAIS.

    Texto sem PII passa inalterado. Ordem importa: parâmetros primeiro
    (ex.: ?email=... vira [TOKEN] genérico por nome do parâmetro), depois
    padrões livres no corpo do texto.

    Segredos entram aqui, e não só no domínio de segurança, porque esta função é
    a BORDA DE ESCRITA de tudo que a suíte persiste: mensagem de falha, motivo de
    skip, erro de console. Uma chave AWS numa mensagem de assert ia inteira para
    o `summary.json` antes disso.
    """
    if not text:
        return text
    # PRIMEIRO, e a ordem aqui é a que mais importa neste módulo: toda passagem
    # seguinte REESCREVE o texto. Se a senha for — ou contiver — algo que
    # `_EMAIL`/`_CPF`/`_FONE_BR`/`_PARAM` casam, essas expressões comem um PEDAÇO
    # dela e o resto sobrevive em claro. Senha `x9@corp.com7Kq` viraria
    # `x[EMAIL]7Kq`: a busca literal nunca mais casa e `7Kq` ficou publicado.
    # Publicar metade de um segredo é publicá-lo para quem tem o resto.
    text = mascarar_valores_registrados(text)
    text = _PARAM.sub(lambda m: f"{m.group(1)}=[{m.group(1).upper()}]", text)
    text = mascarar_segredos(text)
    text = _AUTHORIZATION.sub(lambda m: f"{m.group(1)}{m.group(2)}[AUTHORIZATION]", text)
    text = _EMAIL.sub("[EMAIL]", text)
    text = _CPF.sub("[CPF]", text)
    text = _FONE_BR.sub("[FONE]", text)
    return text


def find_pii(text: str) -> list[str]:
    """Tipos de PII encontrados no texto: 'email', 'cpf' e/ou 'telefone'.

    Mesmas expressões usadas para MASCARAR são usadas para DETECTAR — ponto
    único de verdade sobre "o que é dado pessoal" nesta suíte. Se um padrão
    entra aqui, ele passa a ser mascarado e detectado no mesmo commit.
    """
    if not text:
        return []
    achados = []
    if _EMAIL.search(text):
        achados.append("email")
    if _CPF.search(text):
        achados.append("cpf")
    if _FONE_BR.search(text):
        achados.append("telefone")
    return achados


def safe_url(url: str) -> str:
    """Versão de URL segura para relatório: sem credencial embutida e sem query.

    A URL original continua sendo usada nas requisições; apenas o texto
    reportado usa esta versão. Se havia parâmetros, sinaliza para o dev.

    O userinfo (`https://usuario:senha@host/`) é removido SEMPRE — com ou sem
    query. Antes, o caminho "sem query" devolvia a URL recebida VERBATIM, e uma
    credencial escrita dentro de `WEBQA_TARGET_URL` ia inteira para o campo
    `alvo` do `summary.json`. O aviso fica no lugar do valor em vez de o valor
    sumir calado: credencial embutida na URL é defeito de configuração, e quem
    lê o laudo precisa saber que havia uma.
    """
    parsed = urlparse(url)
    if "@" in parsed.netloc:
        parsed = parsed._replace(netloc="[credencial oculta]@" + parsed.netloc.rpartition("@")[2])
    if not parsed.query:
        return parsed.geturl()
    return parsed._replace(query="", fragment="").geturl() + "?[params ocultos]"
