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

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# CPF com e sem pontuação (limites para não engolir números maiores).
_CPF = re.compile(r"(?<!\d)(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})(?!\d)")
# Telefone BR: +55 opcional, DDD com/sem parênteses, 8-9 dígitos com separadores.
_FONE_BR = re.compile(r"(?<!\d)(?:\+?55[\s.-]?)?(?:\(?\d{2}\)?[\s.-]?)?\d{4,5}[\s.-]\d{4}(?!\d)")
_PARAM = re.compile(
    r"(?i)\b(" + "|".join(_SENSITIVE_PARAMS) + r")=([^&\s\"'<>]+)"
)


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
    text = _PARAM.sub(lambda m: f"{m.group(1)}=[{m.group(1).upper()}]", text)
    text = mascarar_segredos(text)
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
    """Versão de URL segura para relatório: remove a query string inteira.

    A URL original continua sendo usada nas requisições; apenas o texto
    reportado usa esta versão. Se havia parâmetros, sinaliza para o dev.
    """
    parsed = urlparse(url)
    if not parsed.query:
        return url
    return parsed._replace(query="", fragment="").geturl() + "?[params ocultos]"
