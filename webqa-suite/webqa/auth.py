"""Credencial de HTTP Basic Auth do alvo — o dado mais sensível que a suíte toca.

Existe separado de `gates.py` porque as duas coisas não são a mesma. Os gates
autorizam **agir contra** o alvo (gerar carga, sondar caminho não oferecido);
credencial é **configuração** — diz apenas quem a suíte é ao bater na porta.
Juntá-los faria "tenho a senha" parecer "posso gerar carga", e cada mistura
dessas é uma autorização que ninguém deu.

Duas invariantes estruturais, no molde do `Finding` (webqa/dominio.py):

    **não existe `Credencial` cuja senha não esteja registrada para mascaramento.**

O registro acontece no CONSTRUTOR. Não é regra que cada borda de escrita precisa
lembrar de seguir — é caminho que não existe. E registra-se a senha em TODAS as
formas em que ela pode reaparecer num artefato (escapada para JSON, escapada
para HTML, percent-encoded, e o blob base64 do cabeçalho), porque varrer o
arquivo serializado procurando só o valor cru falharia em silêncio justamente
com as senhas que têm caractere especial — as boas.

    **a senha só é enviada para a ORIGEM do alvo, e só sob https (ou rede local).**

O cliente HTTP é de sessão e é usado contra hosts que não são o alvo: o axe-core
vem de um CDN (`checks/ux/test_acessibilidade.py`), a política de privacidade
costuma morar em outro domínio (`checks/lgpd/test_transparencia.py`), e há um
teste que bate no alvo em `http://` puro de propósito, para conferir o
redirecionamento (`checks/backend/test_http_basics.py`). Um `httpx.BasicAuth`
comum anexa `Authorization` em toda requisição do cliente: a senha do operador
iria para a Cloudflare e trafegaria em claro. Por isso a política é origem +
esquema, e não "o cliente tem credencial".

Somente stdlib. O adaptador para o httpx mora em `http_utils.py`, para que a
política de quando enviar não dependa de qual cliente HTTP o projeto usa.
"""
from __future__ import annotations

import base64
import html
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

USUARIO_ENV = "WEBQA_BASIC_AUTH_USER"
SENHA_ENV = "WEBQA_BASIC_AUTH_PASS"

# Abaixo disto o relatório sai muito mascarado: uma senha "123" apaga o "123" de
# qualquer número no laudo. NÃO é uma recusa — é um aviso. Recusar credencial
# curta deixaria a suíte sem rodar contra um alvo que o operador não controla,
# e vazar é pior que embaralhar: a garantia vale para qualquer senha, sempre.
TAMANHO_CONFORTAVEL = 8

# Portas que a origem não precisa soletrar. `https://a.com` e `https://a.com:443`
# são a mesma origem, e o Playwright normaliza — se aqui não normalizasse, o
# `origin` do `http_credentials` deixaria de casar e a senha não seria enviada.
_PORTA_PADRAO = {"http": "80", "https": "443"}


def origem_de(url: str) -> str:
    """`esquema://host:porta` sem userinfo, com porta padrão omitida.

    Sem userinfo porque uma URL de alvo escrita como `https://u:p@host/` não
    pode transformar a própria credencial em parte da identidade da origem.
    """
    partes = urlsplit(url)
    esquema = partes.scheme.lower()
    # `.hostname` já descarta o userinfo e normaliza a caixa (host é
    # case-insensitive), mas devolve IPv6 SEM os colchetes — que precisam voltar,
    # senão `http://::1:8080` fica ambíguo e inválido.
    hospedeiro = partes.hostname or ""
    if ":" in hospedeiro:
        hospedeiro = f"[{hospedeiro}]"
    try:
        porta = partes.port
    except ValueError:
        porta = None    # porta ilegível: a origem sem ela ainda compara certo
    if porta and str(porta) != _PORTA_PADRAO.get(esquema):
        return f"{esquema}://{hospedeiro}:{porta}"
    return f"{esquema}://{hospedeiro}"


def variantes_da_senha(usuario: str, senha: str) -> tuple[str, ...]:
    """Toda forma em que a senha pode reaparecer num artefato escrito.

    Função pura, e o coração da varredura por VALOR. Sem as formas escapadas, a
    varredura do `summary.json`/`summary.html` seria teatro: `json.dumps` escapa
    aspas e barra invertida, `html.escape` escapa `&<>"'`, e uma senha com
    qualquer um desses caracteres atravessaria a varredura intacta — a senha
    forte passaria e a fraca seria pega, exatamente ao contrário do desejável.
    """
    par = f"{usuario}:{senha}"
    formas = (
        senha,
        par,
        base64.b64encode(par.encode()).decode("ascii"),
        quote(senha, safe=""),
        html.escape(senha, quote=True),
        json.dumps(senha)[1:-1],
    )
    # dict.fromkeys preserva ordem e remove duplicata (senha ASCII simples faz
    # três das seis formas coincidirem).
    return tuple(f for f in dict.fromkeys(formas) if f)


@dataclass(frozen=True)
class Credencial:
    """Usuário e senha do Basic Auth. Nasce registrada para mascaramento."""

    usuario: str
    senha: str

    def __post_init__(self) -> None:
        if not self.usuario or not self.senha:
            raise ValueError(
                f"Credencial incompleta: {USUARIO_ENV} e {SENHA_ENV} precisam dos dois valores."
            )
        from webqa.sanitize import registrar_valor_sensivel

        for forma in variantes_da_senha(self.usuario, self.senha):
            registrar_valor_sensivel(forma, "SENHA")

    @property
    def cabecalho_basic(self) -> str:
        """Valor do cabeçalho `Authorization` (RFC 7617, UTF-8)."""
        par = f"{self.usuario}:{self.senha}".encode()
        return "Basic " + base64.b64encode(par).decode("ascii")

    @property
    def senha_curta(self) -> bool:
        return len(self.senha) < TAMANHO_CONFORTAVEL

    @property
    def expoe_senha_em_claro(self) -> bool:
        """Sempre False numa instância válida — existe para o teste PROVAR.

        Irmão de `Finding.contem_segredo_em_claro`: uma invariante que ninguém
        consegue exercitar é uma invariante que ninguém sabe se vale.
        """
        from webqa.sanitize import mascarar_valores_registrados

        amostra = f"{self!r} {self.cabecalho_basic} {self.usuario}:{self.senha}"
        return self.senha in mascarar_valores_registrados(amostra)

    def __repr__(self) -> str:
        # Cobre repr(), str(), f-string, %s, .format() — e o caso que mais pega:
        # o repr de um dict ou tupla que contenha a credencial num traceback.
        return f"Credencial(usuario={self.usuario!r}, senha=[SENHA])"

    __str__ = __repr__


def credencial_do_ambiente(ambiente: Mapping[str, str] | None = None) -> Credencial | None:
    """Credencial declarada no ambiente, ou None (alvo anônimo, comportamento atual).

    Sem cache de propósito: o idioma de teste da casa é `monkeypatch.setenv`, e
    memoizar faria o segundo caso de teste ler o ambiente do primeiro.

    Só UMA das duas variáveis definida é erro de configuração, não anonimato: cair
    em silêncio para anônimo reencenaria a cascata de 401 que este módulo existe
    para eliminar, e ainda esconderia o motivo.
    """
    ambiente = os.environ if ambiente is None else ambiente
    usuario = ambiente.get(USUARIO_ENV) or ""
    senha = ambiente.get(SENHA_ENV) or ""
    if not usuario and not senha:
        return None
    if not usuario or not senha:
        faltante = USUARIO_ENV if not usuario else SENHA_ENV
        raise ValueError(
            f"Basic Auth configurado pela metade: {faltante} está vazia ou ausente. "
            f"Defina {USUARIO_ENV} e {SENHA_ENV}, ou nenhuma das duas para acesso anônimo."
        )
    return Credencial(usuario=usuario, senha=senha)


def pode_enviar_credencial(
    url: str, origem: str, e_local: Callable[[str, int], bool] | None = None
) -> bool:
    """A senha pode ir NESTA requisição?

    Duas condições, e as duas são necessárias: mesma origem que o alvo (senão a
    senha vaza para CDN e para o host da política de privacidade) e transporte
    que não a exponha — `https`, ou um host da própria máquina/rede controlada.

    A exceção local existe pelo alvo fixture (`http://127.0.0.1:porta`) e é
    decidida pelo IP RESOLVIDO, nunca por casar string: `localhost` pode resolver
    para um endereço público, e aí "é local" seria uma afirmação falsa sobre para
    onde a senha está indo.
    """
    if origem_de(url) != origem:
        return False
    partes = urlsplit(url)
    if partes.scheme.lower() == "https":
        return True
    if e_local is None:
        from webqa.rede import host_e_local

        e_local = host_e_local
    hospedeiro = partes.hostname or ""
    return bool(hospedeiro) and e_local(hospedeiro, partes.port or 80)


def credenciais_para_playwright(credencial: Credencial | None, alvo: str) -> dict | None:
    """`http_credentials` do contexto Playwright — None quando não há credencial.

    `origin` prende o envio ao alvo (mesma razão da política do httpx: o
    navegador baixa recurso de terceiro). `send="unauthorized"` só emite o
    cabeçalho depois do desafio 401, em vez de oferecê-lo a quem não pediu.
    """
    if credencial is None:
        return None
    return _CredenciaisDoNavegador(
        {
            "username": credencial.usuario,
            "password": credencial.senha,
            "origin": origem_de(alvo),
            "send": "unauthorized",
        }
    )


class _CredenciaisDoNavegador(dict):
    """dict com repr redigido — o Playwright exige dict, o traceback não precisa.

    Sem isto, um `--showlocals` num erro de fixture imprimiria a senha em claro
    no terminal, que é o único caminho de saída que a varredura do laudo não
    cobre.
    """

    def __repr__(self) -> str:
        usuario, origem = self.get("username"), self.get("origin")
        return f"{{'username': {usuario!r}, 'password': '[SENHA]', 'origin': {origem!r}}}"

    __str__ = __repr__


def orientacao_sem_credencial(alvo: str = "") -> str:
    from webqa.sanitize import safe_url

    onde = f" ({safe_url(alvo)})" if alvo else ""
    return (
        f"O alvo{onde} exige autenticação HTTP (401) e nenhuma credencial foi informada. "
        f"Exporte {USUARIO_ENV} e {SENHA_ENV} e rode de novo. "
        "A suíte parou aqui de propósito: sem passar da porta, todo teste viraria "
        "erro de infraestrutura, e erro de infraestrutura não é veredito sobre o alvo."
    )


def orientacao_credencial_rejeitada(alvo: str = "") -> str:
    from webqa.sanitize import safe_url

    onde = f" ({safe_url(alvo)})" if alvo else ""
    return (
        f"O alvo{onde} recusou a credencial informada (401). Confira os valores de "
        f"{USUARIO_ENV} e {SENHA_ENV} — usuário ou senha não conferem, ou o realm "
        "protegido não é o mesmo caminho configurado em WEBQA_TARGET_URL."
    )


def aviso_de_senha_curta() -> str:
    return (
        f"A senha em {SENHA_ENV} tem menos de {TAMANHO_CONFORTAVEL} caracteres. "
        "Ela será mascarada no relatório por VALOR, como qualquer senha — mas um "
        "valor curto também casa com trechos legítimos do laudo, que sairão "
        "mascarados junto. Uma senha longa e aleatória evita isso."
    )


def verificar_desafio_de_autenticacao(
    status: int, credencial: Credencial | None, alvo: str = ""
) -> None:
    """Preflight: 401 vira orientação, não cascata.

    Recebe o STATUS, não a resposta — é o que permite exercitar os dois caminhos
    com um 401 fabricado, sem rede e sem httpx.

    `pytest.exit` nos dois casos, e não `fail`: com a porta fechada nenhum teste
    chega a acontecer, e sessenta `error` idênticos escondem a única linha que o
    operador precisa ler. Mesmo precedente do alvo ausente em `conftest.py`.
    """
    if status != 401:
        return

    import pytest

    if credencial is None:
        pytest.exit(orientacao_sem_credencial(alvo), returncode=4)
    pytest.exit(orientacao_credencial_rejeitada(alvo), returncode=4)
