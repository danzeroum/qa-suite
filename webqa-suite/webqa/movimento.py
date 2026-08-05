"""Movimento na interface — o núcleo puro do check de `prefers-reduced-motion`.

WCAG 2.2 **2.3.3 (Animation from Interactions)**. Quem declara
`prefers-reduced-motion: reduce` no sistema operacional tem motivo: desconforto
vestibular é sintoma físico, não preferência estética. Ignorar a declaração é
impor náusea a quem pediu para não senti-la.

O que este módulo resolve não é ler animações — é **decidir quais contam**. Uma
página bem-feita anima na entrada e para; contar essas acusaria de violação todo
alvo que faz a coisa certa. O filtro é o valor aqui, e ele tem duas partes:

* **estado** — só `running` conta. Animação pausada ou terminada não incomoda
  ninguém, e `getAnimations()` devolve as três;
* **tempo RESTANTE, não duração declarada** — uma animação de 10s que já rodou
  9,5s termina em meio segundo. Filtrar por duração a acusaria; filtrar pelo que
  falta descreve o que a pessoa ainda vai sentir.

Somente stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass

# Abaixo disto, o que resta de animação é um rabicho: termina antes de a pessoa
# perceber, e reprovar por isso seria cobrar perfeição em vez de conforto.
RESTANTE_MINIMO_MS = 1000.0


@dataclass(frozen=True)
class Animacao:
    """Uma animação viva na página, como `getAnimations()` a descreve."""

    nome: str
    alvo: str
    estado: str = "running"
    # `None` = infinita. Ausência de fim é o caso mais grave: nada faz parar.
    restante_ms: float | None = None

    @property
    def infinita(self) -> bool:
        return self.restante_ms is None

    @property
    def persistente(self) -> bool:
        """Ainda vai incomodar por tempo suficiente para importar."""
        if self.estado != "running":
            return False
        return self.infinita or self.restante_ms > RESTANTE_MINIMO_MS

    def __str__(self) -> str:
        quanto = "infinita" if self.infinita else f"{self.restante_ms:.0f}ms restantes"
        return f"{self.nome} em {self.alvo} ({quanto})"


def animacoes_persistentes(brutas) -> list[Animacao]:
    """As que ainda vão rodar sob `reduced-motion`. Puro e determinístico."""
    return [a for a in (_de_bruta(b) for b in brutas) if a.persistente]


def _de_bruta(bruta) -> Animacao:
    if isinstance(bruta, Animacao):
        return bruta
    return Animacao(
        nome=str(bruta.get("nome") or "animação sem nome"),
        alvo=str(bruta.get("alvo") or "?"),
        estado=str(bruta.get("estado") or "running"),
        restante_ms=bruta.get("restante_ms"),
    )


def resumo_de_animacoes(animacoes, teto: int = 10) -> str:
    linhas = [f"  {a}" for a in animacoes[:teto]]
    if len(animacoes) > teto:
        linhas.append(f"  … e mais {len(animacoes) - teto}")
    return "\n".join(linhas)


# ---------- Coletor ----------

# `getAnimations()` cobre CSS animations, CSS transitions e Web Animations API —
# as três formas de animar que existem hoje. Varrer folhas de estilo procurando
# `@keyframes` veria só a primeira, e ainda perderia a distinção entre declarada
# e ativa, que é justamente o que decide se conta.
#
# `restante_ms` é `null` para iteração infinita: ausência de fim é o caso mais
# grave, e representá-lo como um número grande o esconderia atrás de um limiar.
JS_ANIMACOES = """
() => {
  const seletorDe = (n) => {
    if (!n || !n.tagName) { return '?'; }
    if (n.id) { return n.tagName.toLowerCase() + '#' + n.id; }
    const classe = (n.className || '').toString().trim().split(/\\s+/)[0];
    return n.tagName.toLowerCase() + (classe ? '.' + classe : '');
  };
  return document.getAnimations().map(a => {
    const efeito = a.effect;
    const tempos = efeito && efeito.getComputedTiming ? efeito.getComputedTiming() : {};
    const infinita = tempos.iterations === Infinity || tempos.iterations === null;
    let restante = null;
    if (!infinita && typeof tempos.activeDuration === 'number') {
      const corrido = typeof a.currentTime === 'number' ? a.currentTime : 0;
      restante = Math.max(0, tempos.activeDuration - corrido);
    }
    return {
      nome: a.animationName || (a.transitionProperty ? 'transition:' + a.transitionProperty
                                                     : 'animação'),
      alvo: efeito && efeito.target ? seletorDe(efeito.target) : '?',
      estado: a.playState,
      restante_ms: restante,
    };
  });
}
"""
