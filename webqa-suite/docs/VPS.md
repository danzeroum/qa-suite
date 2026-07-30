# Noturno de estabilidade na VPS (ambiente oficial da métrica)

Desde a **emenda de 2026-07-30**, o ambiente controlado é o container Docker
desta VPS — não o runner do GitHub. Só ele escreve o ledger
`docs/lgpd-estabilidade.json`, e só execuções com `WEBQA_ORIGEM=vps` contam na
sequência que destrava a Fase 2 (ver [`LGPD.md`](LGPD.md)).

Por que aqui e não no GitHub: a imagem é **fixada por digest**, então o ambiente
de hoje é bit a bit o de amanhã. Um runner hospedado troca a versão da imagem
base sob os pés — e a métrica passaria a comparar ambientes diferentes como se
fossem o mesmo. Além disso, **um escritor só**: dois processos commitando o
mesmo arquivo é conflito de push às 3h da manhã.

## Papéis

| Onde | O quê | Escreve o ledger? |
|---|---|---|
| GitHub Actions — `ci.yml` | `quality-gate` em push/PR; validação manual contra alvo real | **não** (`contents: read`) |
| GitHub Actions — `estabilidade.yml` | smoke-test do pipeline em `--dry-run` | **não** (há passo que reprova se o arquivo mudar) |
| Container desta VPS | medição noturna oficial | **sim**, via deploy key |

## Instalação

Requer Docker Engine e Compose v2.

```bash
sudo git clone https://github.com/danzeroum/qa-suite /opt/webqa-suite
cd /opt/webqa-suite
git checkout main          # o entrypoint aborta se a imagem não for de main
```

### 1. Deploy key (escritor do ledger)

Deploy key **exclusiva deste repositório**, com permissão de escrita — nunca um
PAT de conta pessoal: o PAT carrega o alcance da pessoa, a deploy key só alcança
este repositório.

```bash
mkdir -p docker/secrets && chmod 700 docker/secrets
ssh-keygen -t ed25519 -N '' -C 'webqa-vps-bot' -f docker/secrets/deploy_key
cat docker/secrets/deploy_key.pub    # cole em Settings → Deploy keys → Allow write access

# Permissão e DONO importam: a montagem preserva o uid do host, e o container
# roda como uid 1000 (pwuser). Uma chave 0400 de outro dono é ilegível lá
# dentro — o noturno morreria ao copiá-la, com erro obscuro.
sudo chown 1000 docker/secrets/deploy_key docker/secrets/known_hosts
chmod 400 docker/secrets/deploy_key docker/secrets/known_hosts
```

A chave **privada** fica só no disco da VPS e é montada somente-leitura no
container. Ela nunca entra em camada de imagem (ver `.dockerignore`), e o
`docker/secrets/` está no `.gitignore`.

### 2. `known_hosts` do github.com

O repositório **não versiona** a chave de host de propósito: um valor errado aqui
quebra o push, e chave de host é coisa que se verifica na fonte, não se copia de
memória. Gere e confira o fingerprint contra a
[lista publicada pelo GitHub](https://docs.github.com/pt/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints):

```bash
ssh-keyscan -t ed25519 github.com > docker/secrets/known_hosts
ssh-keygen -lf docker/secrets/known_hosts     # compare com o fingerprint publicado
```

Depois de gerar os dois arquivos, aplique dono e permissão como na seção
anterior (`chown 1000` + `chmod 400`).

O container roda com `StrictHostKeyChecking=yes`: se o fingerprint não casar, o
push falha em vez de confiar em quem responder.

### 3. Imagem

```bash
docker compose -f docker/compose.yml build
```

Rebuild é necessário só quando mudam **dependências** ou o Dockerfile: o
entrypoint faz `git pull --ff-only` a cada noite, então check novo entra sem
rebuild. O container é `--rm`: o pull vive só naquela execução, e não há deriva
de estado entre noites.

## Antes do cron: o smoke (`make vps-smoke`)

Não agende o cron sem passar por aqui. O smoke roda **os mesmos comandos do
cron**, apenas sem a caneta, e para no primeiro problema citando a seção que
corrige:

```bash
cd /opt/webqa-suite/webqa-suite
make vps-smoke        # ou: scripts/vps_smoke.sh
```

| Passo | O que valida |
|---|---|
| 1 | daemon do Docker responde e a imagem constrói |
| 2 | `docker history` sem `deploy_key`/`BEGIN OPENSSH`/`id_rsa`/`id_ed25519` |
| 3 | deploy key e `known_hosts` presentes, `0400` e legíveis pelo uid do container |
| 4 | `ssh -T git@github.com` autentica pela deploy key |
| 5 | pipeline completo com `WEBQA_DRY_RUN=1`: sai com `streak`, e HEAD local e remoto ficam intactos |

Em `5/5 PASS` ele imprime `Pronto: agende o cron`. Em qualquer FAIL, sai com
código ≠ 0 — e o log **nunca** ecoa bytes de segredo, só caminhos.

`WEBQA_DRY_RUN=1` executa fixture, contrato, dimensão e classificador; pula
somente commit e push. É o modo de exercitar o noturno sem mexer no ledger.

## Execução manual

```bash
cd /opt/webqa-suite
docker compose -f docker/compose.yml run --rm estabilidade
```

Saída esperada ao fim: `streak N/10 (vps, N dias distintos)` e
`ledger publicado`. O commit aparece no GitHub como
`chore(ledger): noite AAAA-MM-DD` com autor `webqa-vps-bot`, e **não dispara
CI** (marcador de skip na mensagem).

## Agendamento (cron do host)

Agendamento fora do container de propósito: um container dormindo 24h é um
processo de longa duração acumulando estado; `run --rm` a cada noite é
descartável e idêntico.

```cron
# /etc/cron.d/webqa-estabilidade  (o cron do host roda em UTC nesta VPS)
17 3 * * * root cd /opt/webqa-suite && /usr/bin/docker compose -f docker/compose.yml run --rm estabilidade >> /var/log/webqa/estabilidade.log 2>&1
```

```
# /etc/logrotate.d/webqa-estabilidade
/var/log/webqa/estabilidade.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
}
```

Oito semanas de log é folga confortável para investigar uma sequência quebrada
sem acumular disco. O log é fluxo de eventos com timestamp UTC em cada linha.

## O que o noturno faz, na ordem

1. **confere os segredos** — deploy key e `known_hosts`. Falta um, aborta antes
   de qualquer teste: medir sem poder escrever é desperdício, e commit parcial é
   pior que noite não registrada;
2. `git pull --ff-only` — nunca cria merge silencioso;
3. sobe o **alvo fixture** em porta efêmera e espera readiness (até 15s,
   ajustável por `WEBQA_FIXTURE_TIMEOUT`) — porta aberta **e** `GET` respondendo;
4. **confere o contrato** do fixture (`pytest tests -m verification`): um check
   que parou de detectar tornaria a medição uma mentira estável;
5. roda `pytest -m lgpd` **tolerando falha** — contra o alvo fixture ele reprova
   por definição; o código de saída do pytest não diz nada sobre estabilidade;
6. **classifica** (`scripts/estabilidade.py --alvo-fixture`): quem separa flake
   de infra de veredito sobre o alvo é o classificador, lendo o `summary.json`;
7. **commita e empurra** o ledger, se mudou.

## Modos de falha e o que significam

| Sintoma no log | Significado |
|---|---|
| `ERRO: segredo ausente` | deploy key ou `known_hosts` não montados; nada foi medido |
| `ERRO: imagem construída fora de 'main'` | a imagem veio de outro branch; rebuild a partir de `main` |
| `ERRO: alvo fixture não abriu porta em 15s` | ambiente sem recursos ou fixture quebrado — **não** é flake fantasma, é aborto explícito |
| `ERRO: alvo fixture não respondeu ao GET inicial` | porta abriu mas não serviu HTML |
| falha no passo do **contrato** | a suíte parou de detectar uma violação conhecida: **corrija a suíte**, não o ledger |
| `push rejeitado … rebase e nova tentativa` | alguém empurrou entre o pull e o push; o bot rebaseia e tenta uma vez |
| `ERRO: push falhou após rebase` | noite não registrada; investigar antes da próxima |
| `ledger inalterado` | execução duplicada (mesmo `generated_at`) ou sem testes de navegador |

Falha do noturno, por si só, **não zera a sequência** — quem zera é flake de
infra classificado a partir do `summary.json`.

## Conferências de segurança

```bash
# Nenhum segredo em camada de imagem:
docker history --no-trunc webqa-estabilidade:local | grep -iE 'deploy_key|BEGIN OPENSSH|id_ed25519' && echo FALHOU || echo OK
docker run --rm --entrypoint sh webqa-estabilidade:local -c 'ls -la /run/secrets 2>/dev/null || echo "sem segredos na imagem"'
```

Postura do container: usuário não-root (`pwuser`), `no-new-privileges`,
segredos em montagem `ro`, `/tmp` em tmpfs e `WEBQA_REPORT_DIR=/tmp/report` —
o relatório de execução, que pode conter trechos de erro do alvo, **nunca**
persiste em volume nem é versionado.

## Limite honesto desta arquitetura

`WEBQA_ORIGEM=vps` é **declaração** do ambiente, não prova criptográfica: quem
tem push no repositório pode escrever `"origem": "vps"` à mão no ledger. A
barreira impede que uma execução local avance a métrica por descuido — não
resiste a falsificação deliberada. Proveniência forte exigiria assinar a entrada
com credencial que só este container possui, e isso não está implementado.
