# Handoff — WebQA Suite: dimensão `seguranca` + camada LLM local + design do relatório

Pacote de entrega para o desenvolvedor. Reúne os contratos de arquitetura e as
ordens de serviço em aberto. Repositório: https://github.com/danzeroum/qa-suite

Estado em 2026-07-30: `main` @ `b22af7d`, 314 testes de verificação verdes.

---

## O que é a WebQA Suite

Suíte de testes automatizados (pytest) que audita **qualquer aplicação web** de
fora para dentro (caixa-preta), apontando só a URL. Dimensões já implementadas e
em `main`: `backend` (performance/segurança de transporte), `frontend`
(HTML/assets/Core Web Vitals), `ux` (Nielsen/arquitetura de informação/WCAG),
`functional` (links/formulários), `acceptance` (BDD), `lgpd` (privacidade
observável), `seguranca` (Fases A e B, 13 checks passivos — PRs #15–#17),
`verification` (testes da própria suíte). Além de: campanha de integração contra
alvos reais, ledger de estabilidade com quarentena por versão de classificador,
e runtime Docker do noturno na VPS.

Este handoff cobre **três trilhas**, independentes entre si:
1. **Dimensão `seguranca`** — ✅ CONCLUÍDA (OS-20→22 mergeadas; Fase C só desenhada, travada).
2. **Camada LLM local** — sumário assistido dos achados, local e opcional (OS-23→24).
3. **Design do relatório** — template `seguranca` no summary.html + painel de
   estabilidade, a partir da proposta de design aprovada (OS-25→26).

---

## Conteúdo do pacote

```
handoff/
├── LEIA-PRIMEIRO.md              ← este arquivo
├── docs/
│   ├── SEGURANCA.md              ← contrato de arquitetura da dimensão seguranca (já commitado no repo)
│   ├── LLM.md                    ← contrato de arquitetura da camada LLM (vira docs/LLM.md no repo)
│   └── BRIEF-DESIGN.md           ← brief de design do relatório/painéis (referência; proposta aprovada)
└── ordens-de-servico/
    └── OS-abertas.md             ← OS-23 a OS-26 abertas (OS-20→22 concluídas), no padrão XML
```

A spec visual das OS de design vive no repositório, fora deste pacote:
`docs/qa-suite design brief/referencia/` — `componentes.html` (§5/§8) é o
contrato de componentes; o bloco `<style>` de `referencia/summary.html` é a
folha canônica (copiar byte a byte, não recriar).

⚠️ **Numeração:** OS-23/OS-24 são a trilha **LLM** (numeração original deste
pacote). As OS de design que circularam em chat com esses números foram
**renumeradas para OS-25/OS-26** — valem os blocos do `OS-abertas.md`.

---

## Como usar este handoff

1. **Leia os contratos primeiro** (`docs/SEGURANCA.md`, `docs/LLM.md` e — para
   as OS de design — `componentes.html` §8 no repo). Eles explicam o *porquê*
   de cada decisão e as fronteiras duras que não se cruzam.
2. **Execute as OS na ordem de dependência** (`ordens-de-servico/OS-abertas.md`).
   Cada OS é um bloco XML colável, com `<aceite>` e `<testes>` verificáveis.
3. **Um PR por OS.** Empilhamento é permitido; ao empilhar sobre PR que sofreu
   squash, use `rebase --onto` dispensando os commits já mergeados (padrão da casa).
4. **CI obrigatório antes de merge:** `ruff` + `bandit` + `pytest -m verification`
   verdes. O `quality-gate` roda em todo push/PR.

---

## Ordem de dependência (resumo)

```
Trilha SEGURANÇA — CONCLUÍDA:
  OS-20 v2 ✓ (#15, 5dd0245) → OS-21 ✓ (#16, 80d8269) → OS-22 ✓ (#17, b22af7d)
     └── [Fase C fica travada, só desenhada]

Trilha LLM:
  OS-23 v2 → OS-24 v2

Trilha DESIGN/RELATÓRIO:
  OS-25 (template seguranca) → OS-26 (painel de estabilidade)
```

As trilhas LLM e DESIGN podem ser tocadas em paralelo por não terem dependência
mútua (a LLM só depende de que o `summary.json` exista, o que já é verdade hoje;
o design depende só da base atual).

---

## Princípios da casa (valem para todo o código)

Estas regras foram firmadas ao longo do projeto e não se renegociam sem decisão
de arquitetura:

- **stdlib-first.** Só entram dependências pesadas com justificativa forte; o
  default é resolver com biblioteca-padrão. (Rejeitadas: Pillow, pypdf,
  python-magic, imghdr, SDKs proprietários de LLM.)
- **Um único ponto de verdade para "o que é dado sensível":** o `sanitize.py`.
  Serve para mascarar (borda de escrita) e para detectar (scan de segredos).
  Nunca se duplica a lógica de sanitização.
- **Ausência de análise nunca é atestado de segurança.** Corpo truncado, recurso
  não avaliado, modelo indisponível → declara "não avaliado", nunca PASS/seguro.
  (Foi o bug mais caro do projeto: navegador morto classificado como "noite limpa".)
- **Capacidade opcional nunca degrada a fonte da verdade.** Chromium ausente,
  LLM ausente → skip/exit 0; o laudo determinístico permanece íntegro.
- **Separação de processo para código probabilístico.** A LLM roda em
  `scripts/sumario.py`, nunca dentro do hook que escreve o laudo.
- **Fronteiras éticas como invariante estrutural, não convenção.** Segredo nunca
  em claro (invariante do `Finding` no construtor); nuvem fora de escopo (veto por
  IP resolvido); sondagem ativa só atrás de gate autorizado.
- **Resultados de alvo real nunca versionados.** Ficam em `report/` (ignorado).
- **No relatório, o design é contrato.** Classes de estado = outcomes verbatim
  (`.passed/.failed/.xfail/.skipped`); xfail fora de toda soma de falha; nota
  epistêmica inseparável do card lgpd; nenhum selo, badge ou linguagem de
  certificação — nem no HTML, nem na saída da LLM (guarda de linguagem).

---

## Pendências operacionais (fora de código — para o dono do repositório)

Estas não bloqueiam o desenvolvimento, mas seguem abertas:

- Tornar `quality-gate` um **required check** em Settings → Branches (sem isso,
  merge sem CI ainda é possível por acidente).
- Deletar as branches mortas: `claude/ci-gate-negative-test-jnf111` e as dos PRs
  já mergeados (#15–#17 inclusive).
- Rodar `make vps-smoke` na VPS (fecha o aceite de build Docker que não pôde ser
  exercido no ambiente de dev).
- O noturno de estabilidade só conta noites `vps`; a Fase 2 da dimensão `lgpd`
  (canário de consentimento, heurísticas de CMP) destrava após 10 noites `vps`
  consecutivas sem flake. O `alvo_sha256` mudou no #17 — a sequência reinicia
  por regra; a OS-26 exibe isso com a nota "o alvo mudou de identidade".

---

## Fase C e nuvem — explicitamente fora de escopo agora

- **Fase C da segurança** (sondagem ativa de `/.git/`, `.env`, `.map`, sublinks):
  desenhada em `docs/SEGURANCA.md §7`, atrás do gate `WEBQA_ACTIVE_PROBES_AUTHORIZED`.
  Não implementar sem autorização explícita do dono de um alvo.
- **LLM em nuvem:** fora de escopo por decisão de produto (nada sai da máquina).
  O veto por IP resolvido na OS-23 torna isso estrutural.

Ambas são YAGNI com peso — construir capacidade intrusiva ou de exfiltração antes
da demanda real é risco sem retorno.
