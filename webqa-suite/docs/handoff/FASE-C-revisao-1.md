# Fase C — Revisão 1 (incorporações da avaliação Pareto)

> Adendo ao `docs/FASE-C.md`. Consolida a rodada de revisão em estilo Pareto.
> Cada item foi checado contra o código real antes de entrar — as análises são bom
> moinho de ideias, mas erram fatos do repo com frequência (ver §D). **Nenhum
> trecho de código das análises deve ser colado literalmente.**

## A. Correções de fato (mudam o veredito de várias sugestões)

1. **Stack é `httpx`** (`requirements.txt: httpx[http2]`), não `requests`. Snippets
   com `session.head(...).iter_content`, `stream=True`, `get_session()` não se
   aplicam: a Fase C consome `make_client`/`PoliteFetcher` existentes.
2. **Pydantic não é dependência** e o projeto é stdlib-first com dependências
   pinadas e justificadas. Validação é no `__post_init__` do dataclass — padrão
   que o `Finding` já usa. Sugestões de pydantic ficam **rejeitadas**.
3. **`Finding` já tem `fase` (`A/B/C`) e `severidade` (`alta/media/baixa`)**,
   validados no construtor, e o `summary.json` já os emite como dado. As várias
   sugestões de "adicionar fase/severidade" já estão feitas. Novo mesmo: só
   `remediacao`.
4. **`llm.py` é local-only por invariante estrutural** (`validar_endpoint` recusa
   endpoint que resolva para IP público; "nuvem fora de escopo, nem como opt-in").
   O risco "llm.py exfiltra corpo para API de terceiro" é estruturalmente
   impossível hoje. Sobra a invariante estreita do §B.9.

## B. Incorporado ao plano (por valor)

### B.1 — R-C6: takeover de subdomínio "próprio" (DNS dangling)
Host no escopo pode ser sequestrado **entre** a autorização e o probe (CNAME
órfão, IP desalocado). É bypass da premissa "host meu" sem violar nenhuma regra
do plano v1. *Mitigação:* prova de posse **no momento do probe** — desafio
`_webqa-ownership.<host> TXT "<hash-da-entrada-de-escopo>"` verificado antes da
primeira requisição ativa ao host; snapshot do IP resolvido e dos registros DNS
na auditoria; divergência de IP entre carregamento e probe **aborta o alvo**.

### B.2 — Governança vira controle técnico: CODEOWNERS + branch protection
O §7 do plano v1 era processo ("revisor nomeado"), não trava. `.github/CODEOWNERS`
cobrindo `tests/test_fase_c_travada.py`, `webqa/gates.py` e (quando existirem)
`webqa/escopo.py`/`webqa/sondagem.py`, com *required review* de code owner na
`main` para esses caminhos. Contagem de aprovações e política de squash ficam a
critério do dono do repo — o essencial é o code owner nesses arquivos.

### B.3 — HEAD-only, zero corpo (com o refinamento que a revisão errou)
Para os caminhos sensíveis, existência (2xx) já é o finding; **não se lê corpo**.
Isso fecha a ambiguidade "quantos bytes é o mínimo" (resposta: nenhum) e cumpre
"detectar-e-reportar" de forma estrutural. Refinamento: HEAD não é sempre
confiável (405, WAF, host onde HEAD≠GET) — então HEAD primeiro; se inconclusivo,
`Range: bytes=0-0` via streaming do `httpx`, fechado na hora; **nunca** GET de
corpo inteiro.

### B.4 — R-C-ativa: C2 (interação) proibida em produção
Aceitar banner / disparar DSAR em produção cria **consentimento real** (afeta a
base legal do controlador), pode disparar exclusão real e manda dado a terceiros
(analytics/tags). *Mitigação:* campo `ambiente` (`producao`/`homologacao`/
`sandbox`) por entrada de escopo; **C2 recusa dura em `producao`**; recomendação
de **adiar C2** até haver sandbox provisionado. A bateria read-only (C1) entrega o
valor de segurança imediato sem esse risco.

### B.5 — R-C7: TOCTOU no escopo (modificação concorrente durante o run)
Escopo é **congelado no início do run**: hash SHA-256 do escopo carregado gravado
na auditoria; cada probe valida contra o snapshot em memória, sem reler o arquivo.
Runs concorrentes não compartilham estado de escopo.

### B.6 — Piso de rate-limit e teto de caminhos como constantes de código
`PISO_INTERVALO_S` não-configurável; intervalo efetivo = `max(config, PISO)`, com
teste provando que `config=0` não zera. Lista curada é dado versionado
(`data/caminhos-sensiveis.yaml`: `path`, `categoria`, `severidade`, `remediacao`,
`procedencia` por item) **e** o carregador impõe `MAX_CAMINHOS`: um arquivo com
10k linhas **falha ao carregar**. Reconcilia "revisável por diff + procedência"
com "não-substituível por wordlist".

### B.7 — R-C8/R-C9: vazamento por resposta de erro e contexto de CI
*R-C8:* um 500 pode trazer segredo em header/traceback. Todo texto capturado
(header, evidência do finding, URL da auditoria) passa pelo mascaramento por valor
de `auth.py` **antes** de virar finding ou linha de log; query-string com
parâmetro sensível é suprimida. Teste de não-vazamento irmão de
`test_vazamento_de_credencial.py`, com resposta-de-erro plantada.
*R-C9:* Fase C roda em job dedicado — `permissions: contents: read`, sem deploy
key/secrets, container efêmero, egresso de rede restrito aos hosts do escopo.
Nunca no mesmo job que publica.

### B.8 — R-C10: repo público publica a superfície
`escopo-autorizado.yaml` versionado num repo público entrega o mapa de alvos.
*Mitigação:* versionar só `escopo-autorizado.yaml.example` (schema); o escopo real
e o registro de autorização vivem fora do repo público (config privada/secret ou
repo privado). Trade-off auditabilidade × exposição explicitado para os analistas.

### B.9 — Invariante LLM (o resíduo válido do "RG-3")
A Fase C **nunca origina caminhos de sondagem via `llm.py`**; a lista é dado
estático curado. Comentário-âncora em `sondagem.py` e nota em `docs/SEGURANCA.md`.
(A exfiltração para nuvem já é barrada por `validar_endpoint` — não é novo controle.)

### B.10 — `--dry-run` como default; auditoria na camada certa
`--dry-run` é o **default**; execução real exige `WEBQA_ACTIVE_PROBES_AUTHORIZED=1`.
Passo de CI roda dry-run e mostra o diff da superfície de sondagem. Auditoria mora
na camada `sondagem`/`audit`, **não** dentro de `require_active_probes` (o gate
fica puro); timestamp timezone-aware (`datetime.now(timezone.utc)`).

### B.11 — Nice-to-haves aceitos em C3 (baixo custo)
Diff/tendência de findings entre runs (lê dois `summary.json`); canary num repo de
baixo risco antes de abrir geral; mapa visual do escopo (mermaid) para auditoria;
templates de remediação — já embutidos no dado curado do §B.6.

## C. Rejeitado ou redimensionado (com motivo)

- **Pydantic:** não é dependência; contraria stdlib-first e a disciplina de
  dependências pinadas. Validar no `__post_init__` (padrão da casa).
- **"Adicionar `fase`/`severidade` ao Finding":** já existem e validados. Nada a
  fazer além de `remediacao`.
- **"`llm.py` vaza para API de terceiro":** estruturalmente impossível hoje.
  Mantida só a invariante do §B.9.
- **"Campanha separada só por convenção":** o design já exige pertencer ao escopo
  para qualquer probe ativo. Adiciono só o **teste negativo** (host da campanha
  reprova `esta_no_escopo`); não é lacuna de design.
- **Migração do `summary.json` como risco "grave":** é aditiva com default —
  registro antigo lê `remediacao=""`. Nota, não risco grave.
- **`required_approving_review_count >= 2` / no-squash:** política do repo, a seu
  critério. O essencial é o CODEOWNERS (§B.2).
- **Snippets em `requests`/`iter_content`/`stream=True`:** reescrever sobre httpx +
  `make_client`/`PoliteFetcher`.

## D. Nota sobre a proveniência das análises
Várias têm marcas de saída de LLM: tamanhos de arquivo inventados, "referências"
fantasma no texto, e a stack errada (`requests`, `pydantic`). Trate-as como
gerador de hipóteses, não como fonte sobre o código — cada item aqui foi conferido
no repositório antes de entrar.

## E. `Finding.remediacao` — a única mudança de modelo (esboço no padrão da casa)
Sem pydantic, no molde da validação que o `Finding` já faz:

```python
# webqa/dominio.py — adição ao Finding existente (que já tem severidade e fase)
remediacao: str = ""

def __post_init__(self) -> None:
    # ...validações existentes de severidade e fase...
    if self.fase == "C" and not self.remediacao.strip():
        raise ValueError(f"Finding de Fase C exige remediação: {self.recurso}")
```

## F. Sequência de PRs revisada (governança antes de qualquer sondagem)

- **PR-C0a — CODEOWNERS + branch protection** (B.2). Primeiro de todos: controle
  técnico antes de qualquer código de Fase C. Fecha a governança do §7.
- **PR-C0b — `escopo.py`** com validação no construtor (dataclass, stdlib),
  `ambiente` por entrada (B.4), congelamento por hash (B.5), prova de posse TXT
  (B.6/B.1), e `escopo-autorizado.yaml.example` versionado (B.8). Quarto consumidor
  da fronteira de rede → entra no registro de `test_fronteira_de_rede.py`.
- **PR-C0c — `Finding.remediacao`** (§E) + `audit` append-only com mascaramento e
  supressão de query-string (B.7/B.10).
- **PR-C0d — inversão assinada de `test_fase_c_travada.py`** (isolado, code owner).
  Único PR que remove uma invariante de segurança — abre a trava só depois de
  C0a–C0c estarem no lugar.
- **PR-C1a — `sondagem.py`** HEAD-only com `Range: bytes=0-0` de fallback (B.3),
  `data/caminhos-sensiveis.yaml` + `MAX_CAMINHOS` + `PISO_INTERVALO_S` (B.6),
  `--dry-run` default (B.10), job de CI de privilégio mínimo (B.7).
- **C2/C3** — só após sandbox provisionado (B.4) e sign-off; nice-to-haves em C3
  (B.11).
