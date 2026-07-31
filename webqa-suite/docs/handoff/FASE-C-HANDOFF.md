# Fase C — Handoff para desenvolvedor(a)

Bem-vindo(a). Este documento é o ponto de partida: te orienta no repositório, te
dá o modelo mental da Fase C, lista o pacote que você recebeu e a ordem exata de
execução. Leia até o fim antes de escrever qualquer linha.

## 0. A única regra que não se negocia

A Fase C é **sondagem ativa autorizada** contra host **próprio**: pedir ao
servidor recursos que ele não linkou (`/.git/HEAD`, `/.env`, backups) para
descobrir exposições antes que um atacante o faça. A técnica é a mesma de uma
intrusão; o que a mantém do lado da auditoria é **autorização + escopo + a
disciplina de detectar-e-reportar, nunca explorar**.

Por isso:

1. **A trava está fechada.** `tests/test_fase_c_travada.py` reprova se qualquer
   símbolo de sondagem ativa aparecer no código. Ela só é invertida no **PR-C0d**,
   por revisor nomeado (CODEOWNERS), depois de toda a governança de C0 estar no
   lugar. Nada sonda nada até lá.
2. **Detectar e reportar, nunca explorar.** Achou `/.env` (200)? O laudo diz
   "exposto, alta, corrija" e para. Não baixa corpo, não reconstrói `.git`, não
   coleta segredo.
3. **Escopo fechado.** Só toca host listado em `escopo-autorizado.yaml`, por
   origem **exata**. Host fora do escopo não é "pulado com aviso": não existe
   caminho no código que fabrique requisição para ele.

Se um PR seu enfraquecer qualquer uma das três, o PR está errado — não o teste que
o reprovou.

## 1. Primeiro contato com o repositório

```bash
git clone https://github.com/danzeroum/qa-suite
cd qa-suite/webqa-suite
pip install -r requirements.txt
python -m playwright install chromium      # para os testes de navegador

make verify          # roda a suíte que testa a PRÓPRIA suíte (marker: verification)
make lint            # ruff
```

`make verify` verde é o seu ambiente pronto. Ele **não toca alvo externo** — é a
suíte se auto-verificando. É esse o alvo que a Fase C precisa manter verde.

### Leia, nesta ordem
1. `README.md` — o que a suíte faz.
2. `docs/PROXIMOS-PASSOS.md` — onde o trabalho parou e as "regras da casa" que o
   código não explica sozinho.
3. `docs/ARQUITETURA.md`, `docs/SEGURANCA.md`, `docs/RISCOS.md`.
4. **`docs/FASE-C.md`** (o plano) + **`FASE-C-revisao-1/2/3.md`** (três rodadas de
   avaliação, com o rastro de decisão). É o seu contrato de trabalho.

## 2. Mapa do código

**`webqa/`** — a biblioteca (sem estado global, injetável, stdlib-first):
- `config.py` — `Settings` a partir de `config.yaml` + variáveis `WEBQA_*`.
- `http_utils.py` — `make_client()` (um `httpx.Client` **síncrono**), `timed_get`.
  O `burst()` async é só do teste de carga (marker `load`), fora da Fase C.
- `auth.py` — Basic Auth, `origem_de(url)` (normaliza origem — **use esta** para
  escopo), e o mascaramento de credencial por valor.
- `rede.py` — localidade por **IP resolvido**, nunca por string (`ip_e_local`,
  `host_e_local`, `ips_de`). Consumir esses símbolos te obriga a entrar no
  registro de `tests/test_fronteira_de_rede.py` (regra §2.11).
- `dominio.py` — o modelo: `Finding` (frozen, sanitiza `evidencia`/`recurso` no
  construtor), `Corpo`/`ler_corpo`/`avaliavel` (leitura com teto),
  `mesma_origem` (asset de 1ª parte — **NÃO** serve para escopo, ver §5),
  `find_secrets`, `sourcemap_referenciado` (a fronteira B→C já documentada),
  `assinatura`/`parece_html` (ferramentas de **corpo**, Fase B).
- `gates.py` — as guardas de autorização (`LOAD`, `ACTIVE_PROBES`, `LLM`). Você
  adiciona `DISCOVERY` e o kill-switch aqui (§6).
- `etiqueta.py` — `PoliteFetcher` (robots.txt, crawl-delay, backoff 429/503). O
  motor de sondagem consome isto, não fala HTTP sozinho.
- `sanitize.py` — `sanitize_text` (borda de escrita: mascara segredo/PII).
- `report*.py` — o laudo. `llm.py` — sumário por LLM **local** (recusa endpoint
  público por invariante estrutural).

**`checks/`** — os testes de verdade, por dimensão (`backend/`, `frontend/`,
`ux/`, `functional/`, `seguranca/`, `lgpd/`, `acceptance/`). É aqui que entram os
checks ativos de C1/C2, sob gate.

**`tests/`** — a suíte testando a si mesma (marker `verification`). É onde moram
os detectores provados por violação plantada.

**`fixture_target/`** — alvos-dublê locais (`servir.py`, `autenticado.py`) com
violações plantadas para os checks acharem.

**`conftest.py`** — as fixtures (`settings`, `client`, `credencial`, `soup`,
`browser`, `paginas_internas`, `network_log`).

`Makefile`, `pytest.ini` (markers), `pyproject.toml` (ruff/bandit), CI em
`.github/workflows/`.

### O idioma da casa (o que o código exige de você)
- **Stdlib-first.** Dependência nova é decisão versionada e justificada. Nada de
  `pydantic`, `requests`, etc. — valide no `__post_init__` do dataclass.
- **Invariante no construtor**, não em cada borda que precisa lembrar da regra
  (o `Finding` sanitiza ao nascer; a `Credencial` se registra para mascaramento).
- **Detector provado com violação plantada.** Um teste que nunca pegou uma
  violação plantada não está provado.
- **Prosa e código concordam, e a prosa está certa** (§2.10). Comentário que
  mente é bug.
- **Localidade por IP resolvido, nunca por string** (§2.11).
- **`skip`, não `fail`, quando falta autorização** — ausência de opt-in não é
  defeito do alvo.

## 3. Modelo mental da Fase C

Quatro fases, cada uma um conjunto de PRs revisáveis:

- **C0 — governança (zero sondagem).** Escopo, gates, auditoria, CODEOWNERS,
  `Finding.remediacao`, e por fim a inversão assinada da trava. Nada bate em rede.
- **C1 — descoberta read-only.** O motor `sondagem.py`: HEAD-only, escopo-locked,
  rate-limited, detectar-e-reportar. É onde a capacidade nasce.
- **C2 — interação (escrita).** Consentimento/DSAR — **proibido em produção**;
  só depois de haver sandbox. Adiado por decisão.
- **C3 — consolidação/relatório.** Diff entre runs, dimensão ativa separada da
  passiva no laudo.

## 4. O que veio neste pacote

**Código de C0, pronto e validado** (governança pura, `make verify` verde):
- `webqa/escopo.py` — a trava de escopo (origem exata, fail-fast, hash de
  congelamento). Sem rede.
- `webqa/audit.py` — auditoria append-only (mascaramento, supressão de
  query-string, anti log-injection). Injetável, sem rede.
- `tests/test_escopo.py`, `tests/test_audit_fase_c.py` — detectores com violação
  plantada (inclui a prova de que `www.`/`cdn.` reprovam quando só o apex está
  listado, e de que os alvos de terceiro da campanha nunca entram no escopo).
- `escopo-autorizado.yaml.example` — schema/exemplo. O arquivo **real nunca é
  comitado** (vive fora do repo público; ver `docs/FASE-C.md` B.8).
- `data/caminhos-sensiveis.yaml.example` — lista curada de exemplo, com
  procedência por item.
- `.github/CODEOWNERS` — controle técnico de governança.

**Plano e revisões:** `docs/FASE-C.md`, `FASE-C-revisao-1.md`, `-2.md`, `-3.md`.

## 5. Decisões já fechadas que você NÃO deve reabrir
- **Escopo usa `auth.origem_de` (origem exata), não `mesma_origem`.** `mesma_origem`
  dobra `www`↔apex (bom para asset de 1ª parte, ruim para autorizar). Autorizar
  `alvo.com` não cobre `www.alvo.com` nem `cdn.alvo.com` — cada host é listado.
- **HEAD-only, zero corpo.** Existência (2xx) já é o achado. Nunca `GET` de corpo.
  `TETO_CORPO_FASE_C = 0`. Soft-404 se corta **só por header** (`Content-Type`
  inesperado). `parece_html`/`assinatura` são Fase B — não use em C1.
- **Finding por status puro.** 200 = exposição, mesmo com corpo vazio; não
  consulte `avaliavel` para decidir existência.
- **`follow_redirects=False`.** `make_client` segue redirect e carrega credencial;
  a sondagem usa cliente **próprio, stateless, sem redirect**; `3xx` vira finding.
- **`llm.py` nunca origina caminhos.** A lista é dado estático curado.

## 6. Sequência de execução (PRs)

Governança (C0) precede toda sondagem. Diffs pequenos, revisáveis.

### PR-C0a — CODEOWNERS + branch protection (zero código)
Merge do `.github/CODEOWNERS` (incluído) e, no GitHub, ative *Require review from
Code Owners* na `main` para os caminhos listados. Isto é o controle técnico que
torna a inversão da trava (C0d) impossível sem sign-off.

### PR-C0b-i — split de gate em `gates.py`
Adicione ao `webqa/gates.py` (atualize também o parágrafo de abertura do módulo,
de "dois gates" para a lista completa, no rigor da docstring de `llm_enabled`):

```python
DISCOVERY_ENV = "WEBQA_DISCOVERY_AUTHORIZED"   # C1: descoberta read-only
KILL_ENV = "WEBQA_ACTIVE_PROBES_KILL"          # parada de emergência

def discovery_authorized() -> bool:
    """Dono do alvo autorizou descoberta de conteúdo não linkado (Fase C1)?

    Read-only: HEAD, nunca escreve. Autorizar descoberta NÃO autoriza escrita
    (use WEBQA_ACTIVE_PROBES_AUTHORIZED para C2). Gates independentes porque os
    riscos são independentes.
    """
    return _enabled(DISCOVERY_ENV)

def kill_switch_active() -> bool:
    """Parada de emergência: verdadeira interrompe o host corrente no laço da sondagem."""
    return _enabled(KILL_ENV)

def require_discovery() -> None:
    import pytest
    if not discovery_authorized():
        pytest.skip(f"[gate:discovery] Exporte {DISCOVERY_ENV}=1 com autorização documentada.")

def require_escopo(escopo, url: str) -> None:
    """Aborta (skip, não fail) se a URL não está no escopo autorizado. Ortogonal ao gate."""
    import pytest
    if not escopo.esta_no_escopo(url):
        pytest.skip(f"[gate:escopo] {url} fora do escopo autorizado — adicione com autorização.")
```

E padronize a mensagem de skip do `require_active_probes` com o prefixo
`[gate:active_probes]`. Testes: estenda `tests/test_gates.py` com o caminho
negativo dos três gates atuais **e** dos dois novos (skip, não fail).

### PR-C0b-ii — `webqa/escopo.py` (incluído)
Já vem pronto e validado. Neste PR você **adiciona a prova de posse por IP**
(R-C6): uma função que resolve o host via `rede.ips_de` no carregamento, grava o
snapshot, e o compara no momento do probe (divergência aborta o alvo). Ao importar
`rede.ips_de`, `escopo` vira o **quarto consumidor da fronteira** — registre-o em
`tests/test_fronteira_de_rede.py::FRONTEIRAS_DE_REDE` com o teste que exercita o
ramo, senão o guard §2.11 reprova (ele reprova de propósito).

### PR-C0c — `Finding.remediacao` + auditoria
No `webqa/dominio.py`, adicione o campo (com default, backward-compatible) e a
validação, ao lado das sanitizações que o `Finding` já faz:

```python
    fase: Fase
    remediacao: str = ""          # NOVO

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidencia", sanitize_text(str(self.evidencia)))
        object.__setattr__(self, "recurso", sanitize_text(str(self.recurso)))
        object.__setattr__(self, "remediacao", sanitize_text(str(self.remediacao)))   # NOVO
        if self.severidade not in ("alta", "media", "baixa"):
            raise ValueError(f"severidade inválida: {self.severidade!r}")
        if self.fase not in ("A", "B", "C"):
            raise ValueError(f"fase inválida: {self.fase!r}")
        if self.remediacao.lstrip().startswith("<"):                                   # NOVO (anti-XSS)
            raise ValueError("remediação não pode conter markup")
        if self.fase == "C" and not self.remediacao.strip():                           # NOVO
            raise ValueError(f"Finding de Fase C exige remediação: {self.recurso}")
```

Atenção: adicionar campo muda o `summary.json` — atualize `tests/test_sumario.py`
e o que renderiza o laudo no MESMO PR. Traga o `webqa/audit.py` (incluído) e o
`tests/test_audit_fase_c.py`. Torne `find_secrets(fase=...)` obrigatório (remova o
default `"A"`) e ajuste os chamadores A/B por grep — evita fase errada silenciosa.

### PR-C0d — inverter a trava (o ato de governança)
PR **isolado**, assinado por code owner. Adicione um cabeçalho a
`test_fase_c_travada.py` dizendo quais assertions serão invertidas × quais
permanecem — é o que o analista assina, não o diff inteiro. Só depois disto C1
existe.

### PR-C1a — `webqa/sondagem.py` (o motor)
Só depois de C0 verde e assinado. Consome `escopo` + `PoliteFetcher`; HEAD-only
(`Range: bytes=0-0` de fallback), `follow_redirects=False`, cliente stateless,
`MAX_CAMINHOS` imposto no carregador do `data/caminhos-sensiveis.yaml`, piso de
rate-limit não-configurável, kill-switch no laço interno, contador
executado×esperado (run parcial = inconclusivo), `--dry-run` default. Findings com
`fase="C"` e `remediacao`. Specs `xfail(strict=True)` primeiro, implementação
depois.

## 7. Definition of Done (por PR)
- Cada invariante tem um teste que **reprova quando violada** (detector provado
  com violação plantada).
- `make lint` e `make verify` verdes; `bandit` limpo.
- Nada de C1+ antes de C0a–C0d fechados e a trava invertida com assinatura.
- O laudo traz `fase` + `severidade` + `remediacao` como dado.

## 8. O que NÃO fazer (limites)
Sem exploração de achado (git-dump, harvest de segredo, dump inteiro). Sem escrita
destrutiva. Sem carga (é outro gate). Sem C2 em produção. Sem host fora do escopo.
Sem wordlist gigante — a lista é curada, com procedência, e o carregador impõe
teto. Na dúvida entre auditoria e intrusão, pare e pergunte ao dono do alvo.
