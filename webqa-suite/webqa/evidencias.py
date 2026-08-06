"""A borda de escrita de PIXEL — o R19, e a mitigação que ele exige.

`webqa/sanitize.py` é a borda de escrita de TEXTO: e-mail, CPF, telefone e
credencial são mascarados antes de qualquer coisa chegar ao `summary.json`. Ela
não alcança pixel. Uma captura de tela de aplicação real exibe o que estiver na
tela — nome, endereço, saldo, o e-mail de quem estava logado —, e nenhuma
expressão regular vai encontrar isso dentro de um PNG.

**A mitigação registrada em `docs/RISCOS.md` para o R19 é NÃO COLETAR**, e é o
que este módulo implementa. Por padrão, captura de alvo real não vira arquivo.
Não é configuração conservadora que alguém aperta depois: é o default, e ligá-lo
exige `WEBQA_GUI_SCREENSHOTS=1` — opt-in explícito, no molde dos gates de
`webqa/gates.py`, onde só a string exata `"1"` autoriza.

**O alvo FABRICADO é a exceção, e ela tem fundamento.** `fixture_target/` é
conteúdo escrito no repositório, em `127.0.0.1`: não há dado de ninguém ali para
vazar, e é o único alvo cuja captura pode ser versionada como referência visual.
A distinção é a mesma que `webqa/rede.py` já faz para a etiqueta — e a mesma
lição da casa: loopback prova a lógica, nunca a fronteira.

Somente stdlib.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit

from webqa.rede import host_e_local

ENV_CAPTURAS = "WEBQA_GUI_SCREENSHOTS"


def capturas_autorizadas(ambiente=None) -> bool:
    """Só a string exata `"1"` autoriza — `"true"`, `" 1"` e afins não ligam.

    Fail-closed pelo mesmo motivo de `webqa/gates.py`: um valor quase-certo numa
    variável de ambiente não pode ser interpretado como consentimento.
    """
    ambiente = os.environ if ambiente is None else ambiente
    return ambiente.get(ENV_CAPTURAS) == "1"


def alvo_fabricado(url: str) -> bool:
    """A URL aponta para o alvo fabricado (loopback/rede local)?

    Host que não resolve conta como NÃO fabricado — na dúvida, o lado seguro é
    tratar como alvo de verdade e não gravar nada.
    """
    partes = urlsplit(url or "")
    if not partes.hostname:
        return False
    porta = partes.port or (443 if partes.scheme == "https" else 80)
    try:
        return host_e_local(partes.hostname, porta)
    except Exception:
        return False       # resolução falhou: trata como alvo de verdade


def pode_gravar_png(url: str, ambiente=None) -> bool:
    """PNG deste alvo pode chegar ao disco?

    Duas portas, e basta uma: alvo fabricado (não há dado de ninguém) ou opt-in
    explícito de quem opera a suíte.
    """
    return alvo_fabricado(url) or capturas_autorizadas(ambiente)


def motivo_de_nao_gravar(url: str) -> str:
    """A frase que vai ao laudo quando a captura não é gravada.

    Diz o que NÃO aconteceu e como mudar isso. Ausência silenciosa de artefato é
    indistinguível de artefato que se perdeu — e quem lê o laudo precisa saber
    que a omissão foi decidida, não acidental.
    """
    return (f"Captura de {url} NÃO gravada: o alvo não é o fabricado e "
            f"{ENV_CAPTURAS}=1 não foi declarado. Pixel não passa pela borda de "
            "sanitização (R19) — tela de aplicação real exibe dado de quem estava "
            "logado, e nenhuma regex encontra isso dentro de um PNG. O achado se "
            "sustenta em seletor e número; a imagem ajudaria a ver, não a corrigir.")
