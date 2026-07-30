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
    "secret", "auth", "session", "sid", "cpf", "email",
)

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# CPF com e sem pontuação (limites para não engolir números maiores).
_CPF = re.compile(r"(?<!\d)(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})(?!\d)")
# Telefone BR: +55 opcional, DDD com/sem parênteses, 8-9 dígitos com separadores.
_FONE_BR = re.compile(r"(?<!\d)(?:\+?55[\s.-]?)?(?:\(?\d{2}\)?[\s.-]?)?\d{4,5}[\s.-]\d{4}(?!\d)")
_PARAM = re.compile(
    r"(?i)\b(" + "|".join(_SENSITIVE_PARAMS) + r")=([^&\s\"'<>]+)"
)


def sanitize_text(text: str) -> str:
    """Mascara e-mail, CPF, telefone BR e valores de parâmetros sensíveis.

    Texto sem PII passa inalterado. Ordem importa: parâmetros primeiro
    (ex.: ?email=... vira [TOKEN] genérico por nome do parâmetro), depois
    padrões livres no corpo do texto.
    """
    if not text:
        return text
    text = _PARAM.sub(lambda m: f"{m.group(1)}=[{m.group(1).upper()}]", text)
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
