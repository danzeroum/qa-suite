"""Etiqueta de campanha — a suíte não deve ser CAPAZ de maltratar terceiro.

Ver `docs/CAMPANHA.md §etiqueta`. A campanha mede sistemas que não são nossos.
Uma suíte que prega respeito ao sistema sob teste e ignora o `robots.txt` dele
perde a autoridade moral de cobrar conformidade de quem ela mede — e a perde com
razão.

A disciplina é **invariante estrutural, não instrução**: quem escreve um alvo
novo no `campanha.yaml` não precisa lembrar de nada. O runner consulta o
`robots.txt` antes de tocar em host de terceiro, recua quando o servidor pede, e
percorre páginas uma de cada vez.

Três fronteiras que este módulo NÃO cruza, de propósito:

* **o alvo fixture é isento.** `127.0.0.1` é nosso, fabricado e controlado;
  pedir licença a nós mesmos é cerimônia, e cerimônia ensina a ignorar a regra.
  A distinção é por IP RESOLVIDO (`webqa/rede.py`), nunca por string;
* **assets de UMA página não entram na conta.** Carregar uma página dispara
  CSS, JS e imagens em paralelo — é o que um visitante faz, e é o que a métrica
  precisa medir. O que a etiqueta serializa é o crawl ENTRE páginas;
* **nada aqui autoriza carga.** A campanha já aborta se `WEBQA_LOAD_AUTHORIZED`
  existir no ambiente. Etiqueta e autorização de carga são coisas diferentes.

Somente stdlib mais `httpx`, que já existe no projeto.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from webqa.rede import PORTA_PADRAO, host_e_local

# O servidor pediu para desacelerar (429) ou disse que não está em condições de
# atender (503). Nos dois casos a resposta correta é a mesma: parar com aquele
# alvo NESTA execução. Reinsistir depois de um 429 é transformar cortesia em
# ataque lento.
STATUS_DE_RECUO = (429, 503)

# Teto de leitura do robots.txt. Arquivo maior que isto não é política de
# rastreamento: é outra coisa, e analisá-la não é trabalho desta suíte.
TETO_ROBOTS_BYTES = 512_000


@dataclass(frozen=True)
class Veredito:
    """O que a etiqueta permite fazer com um alvo, e por quê."""

    permitido: bool
    motivo: str
    crawl_delay_s: float = 0.0
    isento: bool = False

    @property
    def bloqueado(self) -> bool:
        return not self.permitido


def _crawl_delay(rp: RobotFileParser, user_agent: str) -> float:
    """`Crawl-delay` do robots, 0.0 quando não há — e nunca uma exceção.

    O `try` não é decorativo: o `RobotFileParser` do stdlib levanta
    `AttributeError` em `crawl_delay()` quando o arquivo só traz regras de
    agentes específicos e nenhum grupo `*` (o default_entry fica `None`). Deixar
    isso propagar derrubaria a campanha inteira por causa do robots de UM alvo —
    e derrubaria com um traceback que não diz nada sobre etiqueta.
    """
    try:
        return float(rp.crawl_delay(user_agent) or rp.crawl_delay("*") or 0.0)
    except (AttributeError, TypeError, ValueError):
        return 0.0


class PoliteFetcher:
    """Consulta o `robots.txt` de um host e responde o que é permitido.

    Recebe o `get` por parâmetro para que a verificação exercite todas as bordas
    sem tocar a rede — mesma razão pela qual os checks só conhecem fixtures.
    """

    def __init__(self, user_agent: str, timeout_s: float = 20.0, get=None,
                 credencial=None, origem_do_alvo: str = ""):
        self.user_agent = user_agent or "*"
        self.timeout_s = timeout_s
        self._get = get
        self._credencial = credencial
        self._origem_do_alvo = origem_do_alvo
        self._parsers: dict[str, RobotFileParser | None] = {}
        self._vereditos: dict[str, Veredito] = {}

    # ------------------------------------------------------------ infra
    def _cabecalhos(self, url: str) -> dict[str, str]:
        """`User-Agent` sempre; `Authorization` só na origem do próprio alvo.

        O `robots.txt` de um alvo protegido responde 401 para quem chega anônimo,
        e a regra deste módulo é "política ilegível → alvo pulado" — o que
        deixava a dimensão `functional` sem produzir veredito nenhum contra
        qualquer alvo com Basic Auth (achado da OS-37, visto só contra host real:
        loopback é isento e mascarava o limite).

        Ler a política do alvo AUTENTICADO é legítimo — é o alvo de quem
        configurou a credencial. Já o `robots.txt` de TERCEIRO, alcançado durante
        um crawl, continua anônimo: a barreira de origem+esquema da OS-37 vale
        aqui igual, e cortesia com terceiro nunca é motivo para mostrar a ele uma
        credencial que não é dele.
        """
        cabecalhos = {"User-Agent": self.user_agent}
        if self._credencial is None or not self._origem_do_alvo:
            return cabecalhos
        from webqa.auth import pode_enviar_credencial

        if pode_enviar_credencial(url, self._origem_do_alvo):
            cabecalhos["Authorization"] = self._credencial.cabecalho_basic
        return cabecalhos

    def _autenticou(self, url: str) -> bool:
        return "Authorization" in self._cabecalhos(url)

    def _buscar(self, url: str):
        cabecalhos = self._cabecalhos(url)
        if self._get is not None:
            return self._get(url, timeout=self.timeout_s, headers=cabecalhos)
        import httpx

        return httpx.get(url, timeout=self.timeout_s, follow_redirects=True,
                         headers=cabecalhos)

    @staticmethod
    def _base(url: str) -> str:
        partes = urlsplit(url)
        return f"{partes.scheme}://{partes.netloc}"

    def isento(self, url: str) -> bool:
        """Alvo controlado (loopback/rede local) não deve etiqueta a ninguém.

        ⚠️ Este `True` **curto-circuita tudo que vem depois** em `preparar`: a
        busca do `robots.txt`, o tratamento de status, a leitura autenticada e o
        `Disallow`. Contra `127.0.0.1` nada disso executa — então o alvo fixture
        é incapaz, por construção, de exercitar esse caminho, e um ensaio local
        sai verde sem ter rodado a linha que interessa.

        Custou duas vezes (OS-37 e OS-38). É a regra da casa **§2.11** em
        `docs/PROXIMOS-PASSOS.md`: loopback prova a lógica, nunca a fronteira —
        comportamento daqui pra baixo só se dá por provado contra host não-local.
        """
        partes = urlsplit(url)
        porta = partes.port or PORTA_PADRAO.get(partes.scheme, 80)
        return host_e_local(partes.hostname or "", porta)

    # ------------------------------------------------------------ regra
    def preparar(self, url: str) -> Veredito:  # noqa: C901 — máquina de etiqueta (isenção local, robots, status), CC 9 (teto 8). TODO(Q1d): extrair a leitura de robots.
        """Decide se o alvo pode ser medido, consultando o `robots.txt` uma vez.

        `robots.txt` inacessível, 5xx ou ilegível vira **disallow temporário**:
        o alvo é pulado com motivo, não tratado como erro. Não conseguir ler a
        política de alguém não é licença para ignorá-la — e não é defeito da
        campanha, então também não pode reprovar a execução.

        404 é o contrário: o host respondeu e disse que não há política. Aí
        tudo é permitido, que é o que a norma manda.
        """
        base = self._base(url)
        if base in self._vereditos:
            return self._vereditos[base]

        if self.isento(url):
            veredito = Veredito(True, "alvo controlado (rede local) — isento de etiqueta",
                                isento=True)
            self._vereditos[base] = veredito
            self._parsers[base] = None
            return veredito

        try:
            resposta = self._buscar(f"{base}/robots.txt")
        except Exception as erro:
            veredito = Veredito(
                False, f"robots.txt inacessível ({type(erro).__name__}) — alvo pulado")
            self._vereditos[base] = veredito
            return veredito

        status = int(getattr(resposta, "status_code", 0) or 0)
        if status in STATUS_DE_RECUO:
            veredito = Veredito(False, f"servidor pediu recuo ({status}) já no robots.txt")
        elif status >= 500:
            veredito = Veredito(
                False, f"robots.txt respondeu HTTP {status} — política ilegível, alvo pulado")
        elif status == 404 or status == 410:
            # Sem política publicada: a norma diz que tudo é permitido.
            rp = RobotFileParser()
            rp.parse([])
            rp.allow_all = True
            self._parsers[base] = rp
            veredito = Veredito(True, "sem robots.txt (HTTP 404) — nada restrito")
        elif status == 401 or status == 403:
            # Distinguir os dois casos é o que torna a mensagem acionável:
            # "faltou credencial" tem conserto do operador; "a credencial foi
            # recusada" é dado sobre o alvo. Nenhum dos dois é licença para
            # ignorar a política — bloqueia igual, mas dizendo o que houve.
            motivo = (f"robots.txt respondeu HTTP {status} MESMO com credencial — "
                      "política ilegível, alvo pulado"
                      if self._autenticou(f"{base}/robots.txt")
                      else f"robots.txt respondeu HTTP {status} sem credencial — alvo "
                           "pulado (alvo protegido? defina WEBQA_BASIC_AUTH_USER/PASS)")
            veredito = Veredito(False, motivo)
        elif status >= 400:
            veredito = Veredito(
                False, f"robots.txt respondeu HTTP {status} — alvo pulado")
        else:
            texto = str(getattr(resposta, "text", "") or "")[:TETO_ROBOTS_BYTES]
            rp = RobotFileParser()
            # `parse` sobre o texto JÁ BAIXADO, nunca `rp.read()`: o `read` do
            # stdlib usa `urllib` sem timeout, e um host que aceita a conexão e
            # nunca responde travaria a campanha inteira, sem log e sem fim.
            rp.parse(texto.splitlines())
            self._parsers[base] = rp
            veredito = Veredito(True, "robots.txt lido",
                                crawl_delay_s=_crawl_delay(rp, self.user_agent))

        self._vereditos[base] = veredito
        return veredito

    def pode_acessar(self, url: str) -> bool:
        """O `robots.txt` permite este caminho para o nosso user-agent?

        Alvo não preparado devolve `False`: perguntar antes de ler a política é
        o mesmo que não ter política, e o default seguro é não acessar.
        """
        base = self._base(url)
        if base not in self._vereditos:
            return False
        if self._vereditos[base].isento:
            return True
        rp = self._parsers.get(base)
        if rp is None:
            return False
        return bool(rp.can_fetch(self.user_agent, url))

    def motivo_do_bloqueio(self, url: str) -> str:
        caminho = urlsplit(url).path or "/"
        return f"robots.txt proíbe {caminho}"


def resposta_pede_recuo(status: int) -> bool:
    return int(status or 0) in STATUS_DE_RECUO


def motivo_do_recuo(status: int) -> str:
    """Mensagem única para os dois status — quem lê o consolidado não precisa
    saber a diferença entre 429 e 503 para entender que a campanha parou ali."""
    return f"servidor pediu recuo ({int(status)})"
