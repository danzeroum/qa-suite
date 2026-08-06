"""Navegação principal em telas estreitas — o gatilho abre por clique **e** por teclado?

**O "e" é o critério inteiro.** Um menu que abre com o dedo e não com o teclado
não está meio acessível: para quem navega por teclado, a navegação do site
simplesmente não existe (WCAG 2.1.1). E o defeito tem uma forma dominante, quase
sempre a mesma — `<div onclick>` ou `<span onclick>` fazendo papel de botão.
Um `<div>` não recebe foco, não responde a Enter, não é anunciado como
acionável; ele "funciona" em todo teste manual feito com mouse.

**A fronteira do clique.** Clicar aqui é passivo pelo critério de `webqa/gates.py`:
o gate de sondagem ativa existe contra o que ESCREVE no sistema do alvo (submeter
formulário, aceitar banner, exercer direito de titular). Abrir um menu não
escreve nada. Ainda assim o candidato é escolhido de forma conservadora — `a[href]`
e `[type=submit]` são EXCLUÍDOS por construção, e o check confere se a URL mudou
depois do clique. Menu que navega não é menu; é link, e link não se clica.

**Onde a heurística acaba, o veredito abranda.** Achar o gatilho é heurística:
não existe marcação obrigatória para "isto abre o menu". Por isso a partição de
desfechos é assimétrica e deliberada:

* nav visível no viewport → **passa**, e não há gatilho a procurar;
* gatilho encontrado, abre por clique e **não** por teclado → **reprova**. Não é
  heurística: o controle existe, funciona com mouse, não funciona com teclado;
* nenhum gatilho encontrado → **xfail**. Pode ser um alvo que esconde a navegação
  sem oferecer nada (defeito real) ou um gatilho que a heurística não reconhece.
  Reprovar sem saber qual dos dois é o erro que custa a credibilidade da bateria.

Somente stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Gatilho:
    """O candidato a abrir o menu, com o que o navegador respondeu sobre ele."""

    seletor: str = ""
    focavel: bool = False
    abre_por_clique: bool = False
    abre_por_teclado: bool = False
    navegou: bool = False

    @property
    def existe(self) -> bool:
        return bool(self.seletor)


def motivo_de_reprovar(gatilho: Gatilho) -> str:
    """A mensagem do `assert`, ou "" quando não há o que reprovar.

    Só o caso inequívoco: abre com o mouse e não com o teclado. Os demais são
    ausência de medida e cabem ao chamador (`motivo_de_abrandar`).
    """
    if not (gatilho.abre_por_clique and not gatilho.abre_por_teclado):
        return ""
    if not gatilho.focavel:
        return (f"O gatilho da navegação ({gatilho.seletor}) abre o menu com o mouse e "
                "NÃO recebe foco de teclado — quem navega por teclado não alcança a "
                "navegação do site (WCAG 2.1.1). É a assinatura do `<div onclick>` "
                "fazendo papel de botão: funciona em todo teste feito com mouse.")
    return (f"O gatilho da navegação ({gatilho.seletor}) recebe foco, mas Enter e Espaço "
            "não abrem o menu — só o clique abre. O controle parece acionável por "
            "teclado e não é (WCAG 2.1.1).")


def motivo_de_abrandar(gatilho: Gatilho, nav: str) -> str:
    """Quando NÃO dá para afirmar nada: o `xfail`, com o motivo separado por causa."""
    if gatilho.navegou:
        return (f"O candidato a gatilho ({gatilho.seletor}) NAVEGOU ao ser acionado — "
                "é link, não gatilho de menu, e a medição foi abandonada em vez de "
                "seguir contra outra página.")
    if not gatilho.existe:
        return (f"A navegação principal ({nav}) não está visível neste viewport e "
                "nenhum gatilho reconhecível a abre. Pode ser navegação inalcançável "
                "(defeito) ou um gatilho que a heurística não reconhece — e reprovar "
                "sem saber qual dos dois custaria a credibilidade da bateria. "
                "Sinal, não prova.")
    return (f"O gatilho ({gatilho.seletor}) não abriu o menu nem por clique nem por "
            "teclado — provavelmente não é o gatilho. Sinal, não prova.")


def gatilho_de(bruto) -> Gatilho:
    """Traduz o que o coletor devolveu; ausência vira `Gatilho()` vazio."""
    bruto = bruto or {}
    return Gatilho(
        seletor=str(bruto.get("seletor") or ""),
        focavel=bool(bruto.get("focavel")),
        abre_por_clique=bool(bruto.get("abre_por_clique")),
        abre_por_teclado=bool(bruto.get("abre_por_teclado")),
        navegou=bool(bruto.get("navegou")),
    )


# ---------- Coletores ----------

# A navegação principal e se ela está visível AGORA, neste viewport.
JS_NAV = """
() => {
  const nav = document.querySelector('nav, [role=navigation]');
  if (!nav) { return {seletor: '', visivel: false}; }
  const s = getComputedStyle(nav);
  const r = nav.getBoundingClientRect();
  const visivel = s.display !== 'none' && s.visibility !== 'hidden'
      && r.width > 0 && r.height > 0;
  const seletor = nav.tagName.toLowerCase()
      + (nav.id ? '#' + nav.id : (nav.className ? '.' + String(nav.className).split(/\\s+/)[0] : ''));
  return {seletor: seletor, visivel: visivel};
}
"""

# Candidatos a gatilho, do mais provável ao menos.
#
# Os sinais são ESTRUTURAIS (`aria-expanded`, `aria-controls`, `onclick`, papel
# de botão), não de nome: procurar a palavra "menu" no texto não sobreviveria a
# alvo em outro idioma, e um ícone de três traços não tem texto nenhum. O nome
# entra só como último critério de desempate.
#
# `a[href]` e `[type=submit]` ficam de FORA por construção: são as duas coisas
# que um clique não pode tocar sem sair do território passivo. A exclusão é aqui,
# no coletor, e não numa conferência depois — filtro que depende de alguém
# lembrar de aplicá-lo é filtro que um dia não é aplicado.
JS_GATILHOS = """
() => {
""" + """
  const visivel = (el) => {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') { return false; }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const seletorDe = (el) => {
    if (el.id) { return el.tagName.toLowerCase() + '#' + el.id; }
    const classe = String(el.className || '').trim().split(/\\s+/)[0];
    return el.tagName.toLowerCase() + (classe ? '.' + classe : '');
  };
  const SEL = '[aria-expanded], [aria-controls], [onclick], button, [role=button], ' +
              '[class*=menu], [class*=hamburg], [class*=nav-toggle], [class*=gatilho]';
  const proibido = (el) =>
      (el.tagName === 'A' && el.hasAttribute('href')) ||
      el.getAttribute('type') === 'submit' ||
      (el.tagName === 'BUTTON' && !el.hasAttribute('type') && el.form);
  const peso = (el) => (el.hasAttribute('aria-expanded') ? 4 : 0)
      + (el.hasAttribute('aria-controls') ? 3 : 0)
      + (el.hasAttribute('onclick') ? 2 : 0)
      + (/menu|hamburg|nav|gatilho/i.test(String(el.className || '')) ? 1 : 0);
  return [...document.querySelectorAll(SEL)]
    .filter(el => visivel(el) && !proibido(el))
    .map(el => ({seletor: seletorDe(el), peso: peso(el)}))
    .filter(c => c.peso > 0)
    .sort((a, b) => b.peso - a.peso)
    .map(c => c.seletor);
}
"""

# O elemento recebe foco de verdade? `<div>` sem `tabindex` não recebe, e é
# exatamente esse o defeito que este módulo existe para nomear.
JS_FOCAVEL = """
(seletor) => {
  const el = document.querySelector(seletor);
  if (!el) { return false; }
  el.focus();
  return document.activeElement === el;
}
"""
