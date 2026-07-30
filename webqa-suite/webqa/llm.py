"""Camada de sumário por LLM **local** — a LLM apresenta, o código julga.

Ver `docs/LLM.md`. Etapa opcional, desligada por padrão, que transforma achados
JÁ produzidos e JÁ sanitizados em texto legível. O veredito de qualquer teste
continua determinístico e vive no `summary.json`; nada aqui decide nada.

Três invariantes deste módulo, em ordem de dureza:

1. **Nada sai da máquina.** O endpoint é validado por IP RESOLVIDO, não por
   string. Nuvem está fora de escopo — nem como opt-in (§2.1 do contrato).
2. **`passed` nunca entra no prompt.** Confirmar conformidade por ausência de
   achado é o erro que a suíte inteira existe para não cometer.
3. **O texto nunca certifica.** Saída com linguagem de certificação é marcada
   para revisão e **preservada** — descartar em silêncio esconderia o sinal de
   que o modelo se comportou mal, que é justamente o que se quer ver.

Só `httpx`, que já existe no projeto. Nenhum SDK proprietário.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

from webqa.rede import METADADOS_DE_NUVEM, PORTA_PADRAO, ips_de

ENDPOINT_ENV = "WEBQA_LLM_ENDPOINT"
MODELO_ENV = "WEBQA_LLM_MODEL"

ENDPOINT_PADRAO = "http://127.0.0.1:11434/v1/chat/completions"
MODELO_PADRAO = "qwen2.5:7b-instruct"

# Consistência sobre criatividade: um laudo que muda de tom entre execuções
# perde a autoridade que a parte determinística construiu.
TEMPERATURA = 0.2

# Teto de contexto do runtime local. Acima disto o modelo degrada em silêncio —
# e degradação silenciosa num laudo é pior que ausência de laudo.
TETO_ACHADOS = 80

# `passed` fora, sempre. Ver invariante 2.
ESTADOS_NO_PROMPT = frozenset({"failed", "xfail", "error"})

# Campos que viajam ao modelo. Lista FECHADA em vez de "tudo menos X": campo
# novo no summary.json não vaza para o prompt sem alguém decidir que ele deve.
CAMPOS_DO_PROMPT = ("test", "dimension", "estado", "severidade", "fase_seguranca", "detail")

PREFIXO_REVISAR = "revisar: linguagem de certificação"

# Formas flexionadas, nunca radicais soltos: `segur` casaria com "segurança",
# que aparece em toda linha de um sumário desta suíte. `\b` no fim é o que
# impede "segura" de casar dentro de "segurança".
_CERTIFICACAO = (
    ("aprovado", re.compile(r"\baprovad[oa]s?\b", re.I)),
    ("conforme", re.compile(r"\bconforme\b", re.I)),
    ("seguro", re.compile(r"\bsegur[oa]s?\b", re.I)),
    ("certificado", re.compile(r"\bcertificad[oa]s?\b", re.I)),
)



def validar_endpoint(url: str) -> str:
    """Devolve a URL se ela aponta para a máquina local ou a rede local; senão levanta.

    Valida por **IP resolvido**, nunca por string. Casar `localhost` ou `127.`
    no texto da URL é ilusão de controle: um hostname qualquer pode resolver
    para um IP público, e é exatamente assim que um endpoint "local" vira um
    envio para a nuvem sem ninguém perceber. Aqui resolve-se primeiro e
    julga-se o endereço.

    Exige que **todos** os IPs resolvidos sejam locais. Um host que devolve um
    IP privado e um público é rejeitado: a escolha de qual usar é do sistema
    operacional, e uma garantia que depende de sorte não é garantia.
    """
    partes = urlsplit(url)
    host = partes.hostname
    if not host:
        raise ValueError(
            f"endpoint de LLM sem host: {url!r}. Esperado algo como {ENDPOINT_PADRAO}")

    porta = partes.port or PORTA_PADRAO.get(partes.scheme, 80)
    try:
        ips = ips_de(host, porta)
    except OSError as erro:
        raise ValueError(
            f"endpoint de LLM não resolve: {host!r} ({type(erro).__name__}). "
            "Sem resolver não há como provar que é local, e na dúvida não se envia."
        ) from erro

    if not ips:
        raise ValueError(f"endpoint de LLM não resolveu para nenhum IP: {host!r}")

    for ip in ips:
        # ANTES de `is_private`: em `ipaddress`, 0.0.0.0 está em 0.0.0.0/8 e
        # responde True a `is_private`. "Endereço nenhum" não é "endereço local".
        if ip.is_unspecified:
            raise ValueError(
                f"endpoint de LLM aponta para endereço não especificado ({ip}): {url!r}. "
                "0.0.0.0 não é destino, é curinga de escuta.")
        if ip in METADADOS_DE_NUVEM:
            raise ValueError(
                f"envio para nuvem fora de escopo: {host!r} resolve para {ip}, o "
                "serviço de metadados do provedor. É link-local, mas não é esta máquina.")
        if not (ip.is_loopback or ip.is_private or ip.is_link_local):
            raise ValueError(
                f"envio para nuvem fora de escopo: {host!r} resolve para {ip}, que é "
                "endereço público. A camada de LLM é local por invariante estrutural "
                "(docs/LLM.md §2.1) — nuvem não é opção nem com opt-in.")
    return url


def endpoint_configurado() -> str:
    return os.environ.get(ENDPOINT_ENV) or ENDPOINT_PADRAO


def modelo_configurado() -> str:
    return os.environ.get(MODELO_ENV) or MODELO_PADRAO


# Ordem de corte quando o teto aperta. `failed` primeiro porque é veredito sobre
# o alvo; `error` antes de `xfail` porque teste que NÃO ACONTECEU é notícia mais
# urgente que sinal de maturidade ausente — perder um `error` no corte esconderia
# infraestrutura quebrada, que é o defeito que este projeto mais pagou caro.
ORDEM_ESTADO = {"failed": 0, "error": 1, "xfail": 2}
_ORDEM_SEVERIDADE = {"alta": 0, "media": 1, "baixa": 2}


def achados_para_prompt(resultados: list[dict]) -> list[dict]:
    """Achados que podem ir ao modelo: só `failed`/`xfail`/`error`, teto de 80.

    O `detail` já vem sanitizado do `report.py` (borda de escrita) e **não** é
    re-sanitizado aqui: duplicar o ponto único de verdade cria a ilusão de duas
    defesas onde há uma só, e a segunda inevitavelmente diverge da primeira.
    Se a borda falhar, conserta-se a borda.

    Ordena por (estado, severidade) antes de cortar, com `sort` estável: se 80
    não couberem tudo, o que fica de fora é o menos urgente — nunca o que por
    acaso rodou por último. Dentro do mesmo estado e da mesma severidade, a
    ordem de execução é preservada.
    """
    elegiveis = [r for r in resultados if r.get("estado") in ESTADOS_NO_PROMPT]
    elegiveis.sort(key=lambda r: (
        ORDEM_ESTADO.get(str(r.get("estado")), 9),
        _ORDEM_SEVERIDADE.get(str(r.get("severidade") or ""), 3),
    ))
    return [{campo: r[campo] for campo in CAMPOS_DO_PROMPT if r.get(campo)}
            for r in elegiveis[:TETO_ACHADOS]]


INSTRUCAO = (
    "Você resume achados de uma auditoria automatizada de qualidade web para leitura "
    "humana. Você NÃO julga: o veredito já foi decidido pelo código e está nos dados. "
    "Nunca ameniza um achado 'failed'. Nunca afirma que o site está aprovado, conforme, "
    "seguro ou certificado — você não tem como saber isso e não é o seu papel. "
    "Escreva em português do Brasil: um sumário executivo de 2 a 3 parágrafos (o mais "
    "grave, por quê, por onde começar), depois agrupe os achados por causa raiz."
)


def corpo_da_requisicao(achados: list[dict], modelo: str) -> dict:
    """Payload OpenAI-compat. Função pura — é o que permite testar sem rede."""
    linhas = [
        " | ".join(f"{campo}={achado[campo]}" for campo in CAMPOS_DO_PROMPT if campo in achado)
        for achado in achados
    ]
    return {
        "model": modelo,
        "temperature": TEMPERATURA,
        "stream": False,
        "messages": [
            {"role": "system", "content": INSTRUCAO},
            {"role": "user", "content": "Achados:\n" + "\n".join(linhas)},
        ],
    }


def aplicar_guarda_de_linguagem(texto: str) -> str:
    """Marca — não descarta — saída com linguagem de certificação.

    Descartar em silêncio esconderia duas coisas ao mesmo tempo: o texto que o
    operador pediu e o fato de que o modelo tentou certificar. O prefixo entrega
    as duas, e a decisão volta para o humano, que é onde ela sempre esteve.

    `conforme` produz falso positivo em português corrente ("conforme o
    esperado"). É aceito de propósito: um "revisar" indevido custa uma leitura
    humana, e uma certificação que passa custa a autoridade do laudo.

    **Idempotente.** O próprio prefixo contém "aprovado" e "conforme", então uma
    segunda aplicação casaria consigo mesma e empilharia marcações — foi o que
    aconteceu quando a guarda morava em dois lugares. Hoje ela mora só em
    `scripts/sumario.py::gerar`, e esta checagem é a rede embaixo disso.
    """
    if texto.startswith(PREFIXO_REVISAR):
        return texto
    encontradas = [rotulo for rotulo, padrao in _CERTIFICACAO if padrao.search(texto)]
    if not encontradas:
        return texto
    return f"{PREFIXO_REVISAR} ({', '.join(encontradas)})\n\n{texto}"


PREFIXO_OMISSAO = "revisar: achados de {dimensoes} não cobertos"

# Health-check curto de propósito: o POST do sumário tem timeout de minutos
# porque geração é lenta, mas "o runtime está de pé?" se responde em
# milissegundos. Sem este passo, ausência de runtime custaria a espera inteira
# do POST — e uma etapa opcional que trava a execução por dois minutos deixa de
# ser opcional na prática.
TIMEOUT_HEALTH_S = 2.0


def runtime_disponivel(endpoint: str, timeout_s: float = TIMEOUT_HEALTH_S) -> bool:
    """O runtime local responde? Nunca levanta — ausência não é erro (§2.4).

    Qualquer resposta HTTP serve como prova de vida, inclusive 404: o que se
    quer saber é se há alguém escutando na porta, não se aquela rota existe.
    """
    import httpx

    partes = urlsplit(endpoint)
    raiz = f"{partes.scheme}://{partes.netloc}/"
    try:
        httpx.get(raiz, timeout=timeout_s)
    except Exception:
        return False
    return True


def dimensoes_com_falha(resultados: list[dict]) -> set[str]:
    return {str(r.get("dimension") or "") for r in resultados
            if r.get("estado") == "failed" and r.get("dimension")}


def aplicar_guarda_de_omissao(texto: str, resultados: list[dict]) -> str:
    """Marca sumário que deixou uma dimensão com `failed` fora do texto.

    Irmã da guarda de linguagem, e pela mesma lógica: o risco de um modelo não é
    só afirmar demais, é **calar**. Um sumário que fala de três dimensões e
    ignora a quarta parece completo — e o leitor não tem como saber que faltou,
    porque a ausência não deixa marca. Aqui ela deixa.

    Só `failed` conta. `xfail` é sinal de maturidade e pode legitimamente não
    entrar num sumário executivo; veredito de não conformidade, não.
    """
    if texto.startswith(PREFIXO_OMISSAO.split("{")[0]):
        return texto        # idempotente, pelo mesmo motivo da guarda de linguagem
    ausentes = sorted(d for d in dimensoes_com_falha(resultados)
                      if d.lower() not in texto.lower())
    if not ausentes:
        return texto
    return f"{PREFIXO_OMISSAO.format(dimensoes=', '.join(ausentes))}\n\n{texto}"


@runtime_checkable
class ResumidorLLM(Protocol):
    """A abstração que o chamador conhece. Trocar de runtime é configuração.

    Existe para que `scripts/sumario.py` (OS-24 v2) dependa de um contrato e não
    de uma implementação — e para que teste nenhum precise de rede: um fake que
    devolve string já satisfaz isto.
    """

    def resumir(self, resultados: list[dict]) -> str:
        """Recebe `results` do `summary.json`; devolve o sumário em texto."""
        ...


@dataclass(frozen=True)
class ResumidorLocal:
    """Implementação default: runtime local falando OpenAI-compat por HTTP.

    O endpoint é validado no CONSTRUTOR, como o `Finding` sanitiza no dele: não
    existe instância desta classe apontando para a nuvem. A guarda não é um
    passo que `resumir` precisa lembrar de chamar — é condição de existência.
    """

    endpoint: str = ""
    modelo: str = ""
    timeout_s: float = 120.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "endpoint", validar_endpoint(self.endpoint or endpoint_configurado()))
        object.__setattr__(self, "modelo", self.modelo or modelo_configurado())

    def resumir(self, resultados: list[dict]) -> str:
        """Texto CRU do modelo. As guardas são do orquestrador, não desta classe.

        `scripts/sumario.py::gerar` é o único ponto que aplica guarda de
        linguagem e de omissão — e tem de ser único por dois motivos. Guardar
        aqui deixaria qualquer outra implementação do `Protocol` sem proteção
        (a garantia viraria "cada impl que lembre"); e guardar nos dois lugares
        empilha marcação, porque o prefixo de certificação contém as próprias
        palavras que a guarda procura. Ambos aconteceram antes desta linha
        existir. Ver `docs/LLM.md §8`, que já colocava a guarda no script.
        """
        import httpx

        achados = achados_para_prompt(resultados)
        if not achados:
            return ""      # nada a resumir não é sumário vazio: é ausência de etapa
        resposta = httpx.post(self.endpoint, json=corpo_da_requisicao(achados, self.modelo),
                              timeout=self.timeout_s)
        resposta.raise_for_status()
        dados = resposta.json()
        return str(dados["choices"][0]["message"]["content"]).strip()
