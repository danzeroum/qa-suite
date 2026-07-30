# Handoff — WebQA Suite: dimensão `seguranca` + camada LLM local

Pacote de entrega para o desenvolvedor. Reúne os contratos de arquitetura e as
ordens de serviço em aberto. Repositório: https://github.com/danzeroum/qa-suite

---

## O que é a WebQA Suite

Suíte de testes automatizados (pytest) que audita **qualquer aplicação web** de
fora para dentro (caixa-preta), apontando só a URL. Dimensões já implementadas e
em `main`: `backend` (performance/segurança de transporte), `frontend`
(HTML/assets/Core Web Vitals), `ux` (Nielsen/arquitetura de informação/WCAG),
`functional` (links/formulários), `acceptance` (BDD), `lgpd` (privacidade
observável), `verification` (testes da própria suíte). Além de: campanha de
integração contra alvos reais, ledger de estabilidade com quarentena por versão
de classificador, e runtime Docker do noturno na VPS.

Este handoff cobre **duas trilhas novas**, ambas independentes entre si:
1. **Dimensão `seguranca`** — auditoria de segurança da informação sobre tudo que
   o navegador baixa (3 fases; Fases A e B para implementar, Fase C só desenhada).
2. **Camada LLM local** — sumário assistido dos achados, local e opcional.

---

## Conteúdo do pacote

```
handoff/
├── LEIA-PRIMEIRO.md              ← este arquivo
├── docs/
│   ├── SEGURANCA.md              ← contrato de arquitetura da dimensão seguranca (vira docs/SEGURANCA.md no repo)
│   ├── LLM.md                    ← contrato de arquitetura da camada LLM (vira docs/LLM.md no repo)
│   └── BRIEF-DESIGN.md           ← brief de design do relatório/painéis (referência; já há proposta aprovada)
└── ordens-de-servico/
    └── OS-abertas.md             ← OS-20 a OS-24, prontas para execução, no padrão XML
```

Os documentos em `docs/` devem ser commitados no repositório, ao lado dos
existentes (`ARQUITETURA.md`, `LGPD.md`, `RISCOS.md` etc.), na primeira OS de
cada trilha.

---

## Como usar este handoff

1. **Leia os contratos primeiro** (`docs/SEGURANCA.md` e `docs/LLM.md`). Eles
   explicam o *porquê* de cada decisão e as fronteiras duras que não se cruzam.
2. **Execute as OS na ordem de dependência** (`ordens-de-servico/OS-abertas.md`).
   Cada OS é um bloco XML colável, com `<aceite>` e `<testes>` verificáveis.
3. **Um PR por OS.** Empilhamento é permitido; ao empilhar sobre PR que sofreu
   squash, use `rebase --onto` dispensando os commits já mergeados (padrão da casa).
4. **CI obrigatório antes de merge:** `ruff` + `bandit` + `pytest -m verification`
   verdes. O `quality-gate` roda em todo push/PR.

---

## Ordem de dependência (resumo)

```
Trilha SEGURANÇA:
  OS-20 v2 → OS-21 → OS-22   (Fase C fica travada, só desenhada)

Trilha LLM:
  OS-23 v2 → OS-24 v2
```

As duas trilhas podem ser tocadas em paralelo por não terem dependência mútua.

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

---

## Pendências operacionais (fora de código — para o dono do repositório)

Estas não bloqueiam o desenvolvimento, mas seguem abertas:

- Tornar `quality-gate` um **required check** em Settings → Branches (sem isso,
  merge sem CI ainda é possível por acidente).
- Deletar as branches mortas: `claude/ci-gate-negative-test-jnf111` e as dos PRs
  já mergeados.
- Rodar `make vps-smoke` na VPS (fecha o aceite de build Docker que não pôde ser
  exercido no ambiente de dev).
- O noturno de estabilidade só conta noites `vps`; a Fase 2 da dimensão `lgpd`
  (canário de consentimento, heurísticas de CMP) destrava após 10 noites `vps`
  consecutivas sem flake.

---

## Fase C e nuvem — explicitamente fora de escopo agora

- **Fase C da segurança** (sondagem ativa de `/.git/`, `.env`, `.map`, sublinks):
  desenhada em `docs/SEGURANCA.md §7`, atrás do gate `WEBQA_ACTIVE_PROBES_AUTHORIZED`.
  Não implementar sem autorização explícita do dono de um alvo.
- **LLM em nuvem:** fora de escopo por decisão de produto (nada sai da máquina).
  O veto por IP resolvido na OS-23 torna isso estrutural.

Ambas são YAGNI com peso — construir capacidade intrusiva ou de exfiltração antes
da demanda real é risco sem retorno.
