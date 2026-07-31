# Prompt inicial — Fase C (WebQA Suite)

Este é o contexto para começar. Pode ser lido por você (dev) ou colado como
briefing inicial num assistente de código. Se for para um assistente, as
**restrições** abaixo são vinculantes: ele não deve contorná-las.

---

## Quem é este projeto

`danzeroum/qa-suite` (pasta `webqa-suite/`) é uma suíte de QA de aplicações web em
Python/pytest. Aponta-se uma URL e ela avalia backend, frontend, UX, funcional,
segurança e LGPD **de forma passiva** — respeitando robots.txt, sem gerar carga,
com User-Agent identificável, nunca testando quem não quer ser testado.

Estamos adicionando a **Fase C**: sondagem **ativa** e **autorizada** contra hosts
**próprios** (`github/danzeroum`) — pedir ao servidor recursos não linkados
(`/.git/HEAD`, `/.env`, backups) para achar exposições antes que um atacante ache.
A técnica é a mesma de uma intrusão; o que a mantém do lado da auditoria é
autorização + escopo + a disciplina de detectar-e-reportar, nunca explorar.

## Restrições (não-negociáveis)

1. **A trava está fechada.** `tests/test_fase_c_travada.py` reprova qualquer
   símbolo de sondagem ativa no código. Ela só é invertida no PR-C0d, por code
   owner, depois de toda a governança de C0 pronta. **Não escreva o motor de
   sondagem (`sondagem.py`) ainda.**
2. **Detectar e reportar, nunca explorar.** Existência (2xx) já é o achado. Nunca
   baixe corpo, reconstrua `.git` ou colete segredo.
3. **Escopo fechado, origem exata.** Só toca host em `escopo-autorizado.yaml`,
   comparado por `auth.origem_de` (exato — `www`/`cdn`/`api` são hosts distintos).
4. **Stdlib-first.** Sem dependência nova (nada de `pydantic`/`requests`);
   validação no `__post_init__`, como o resto da casa.
5. **Tudo por PR revisado.** Mudanças em `gates.py`, `escopo.py`,
   `test_fase_c_travada.py` e `data/caminhos-sensiveis.yaml` são cobertas por
   CODEOWNERS. Nada de C1 antes de C0 fechar.
6. **Sem C2 em produção. Sem wordlist gigante. Sem carga.** Na dúvida entre
   auditoria e intrusão, pare e pergunte ao dono do alvo.

## Como se localizar (leia nesta ordem)

1. `README.md` — o que a suíte faz e como rodar.
2. `docs/PROXIMOS-PASSOS.md` — onde o trabalho parou e as regras da casa.
3. `docs/FASE-C-HANDOFF.md` — **o seu guia**: mapa do código, modelo mental,
   sequência de PRs com os diffs prontos.
4. `docs/FASE-C.md` + `docs/FASE-C-revisao-1/2/3.md` — o plano e o rastro de decisão.

Rode para ter o ambiente pronto (verde = pronto; não toca alvo externo):

```bash
pip install -r requirements.txt
python -m playwright install chromium
make verify && make lint
```

## O idioma da casa (o código vai te cobrar isto)
- Invariante no **construtor**, não em cada borda.
- **Detector provado com violação plantada** — teste que nunca pegou uma violação
  plantada não está provado.
- **Prosa e código concordam, a prosa está certa** (§2.10).
- **Localidade por IP resolvido, nunca por string** (§2.11) — consumir
  `rede.host_e_local`/`ip_e_local`/`ips_de` te obriga a entrar no registro de
  `tests/test_fronteira_de_rede.py`.
- **`skip`, não `fail`, quando falta autorização.**

## O que já está feito (validado, verde)
- `webqa/escopo.py` — a trava de escopo (origem exata, fail-fast, hash de
  congelamento). Sem rede.
- `webqa/audit.py` — auditoria append-only (mascaramento, supressão de
  query-string, anti log-injection). Injetável, sem rede.
- `tests/test_escopo.py`, `tests/test_audit_fase_c.py` — 21 detectores.
- `escopo-autorizado.yaml.example`, `data/caminhos-sensiveis.yaml.example`,
  `.github/CODEOWNERS`.

Se os arquivos ainda estão em `docs/handoff/`, rode primeiro, da raiz do repo:
`bash webqa-suite/docs/handoff/organizar-arquivos.sh`.

## Sua tarefa imediata: executar C0 (governança, zero sondagem)

Na ordem, cada um um PR pequeno e revisável (detalhe e diffs em `FASE-C-HANDOFF.md` §6):

- **C0a** — merge do `.github/CODEOWNERS` + ativar *Require review from Code
  Owners* na `main`. Zero código.
- **C0b-i** — `gates.py`: `require_discovery()`, `require_escopo()`,
  `kill_switch_active()` (diff pronto no handoff).
- **C0b-ii** — `escopo.py` (já incluído) + a prova de posse por IP (R-C6) usando
  `rede.ips_de`, registrando `escopo` no `FRONTEIRAS_DE_REDE`.
- **C0c** — `Finding.remediacao` (diff pronto) + `audit.py` + `find_secrets` com
  `fase` obrigatório. Atualize `test_sumario.py`/laudo no mesmo PR.
- **C0d** — inverter `test_fase_c_travada.py` (PR isolado, assinado). Só aqui a
  trava abre.

`sondagem.py` (C1) vem **depois** de C0d, seguindo a spec do handoff (HEAD-only,
`follow_redirects=False`, `MAX_CAMINHOS`, kill-switch no laço, `--dry-run` default).

## Definition of Done (por PR)
Cada invariante tem teste que reprova quando violada; `make verify` e `make lint`
verdes; `bandit` limpo; nada de C1+ antes de C0a–C0d fechados e a trava invertida
com assinatura.

---

### Se você é um assistente de código lendo isto
Faça **só C0** (governança), um PR de cada vez, do menor diff possível. **Não**
escreva `sondagem.py`, **não** inverta a trava sozinho, **não** adicione
dependência, **não** aponte nada para host fora do `escopo-autorizado.yaml`. Se
uma tarefa parecer exigir cruzar de auditoria para intrusão, pare e peça
confirmação humana. Toda mudança é proposta de PR para revisão, nunca merge direto.
