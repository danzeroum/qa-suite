#!/usr/bin/env bash
# Noturno de estabilidade: atualiza o repo, sobe o alvo fixture, roda a
# dimensão browser, classifica e commita o ledger.
#
# Ordem deliberada: os segredos são conferidos ANTES de qualquer teste. Medir
# sem poder escrever é desperdício de 15 minutos de VPS, e um commit parcial é
# pior que nenhuma medição.
#
# Só o passo da dimensão tolera falha: contra o alvo fixture ele reprova por
# definição (violações de contrato). Quem decide estabilidade é o classificador.
set -euo pipefail

RAIZ=${WEBQA_REPO_DIR:-/app}
SUITE="$RAIZ/webqa-suite"
LEDGER="webqa-suite/docs/lgpd-estabilidade.json"
CHAVE=${WEBQA_DEPLOY_KEY:-/run/secrets/deploy_key}
KNOWN_HOSTS=${WEBQA_KNOWN_HOSTS:-/run/secrets/known_hosts}
RAMO=${WEBQA_RAMO:-main}
ESPERA_MAX=${WEBQA_FIXTURE_TIMEOUT:-15}

log() { printf '%s | %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
falhar() { log "ERRO: $*"; exit 1; }

# ---------- 1. Segredos (antes de tudo) ----------

[ -s "$CHAVE" ] || falhar "segredo ausente: deploy key não montada em $CHAVE"
[ -s "$KNOWN_HOSTS" ] || falhar "segredo ausente: known_hosts não montado em $KNOWN_HOSTS"

# O ssh recusa chave com permissão frouxa, e a montagem herda o modo do host.
# Cópia em tmpfs com 0400 resolve sem exigir nada do host — e nunca em volume.
CHAVE_PRIVADA=$(mktemp)
URL_ALVO=$(mktemp)
FIXTURE_PID=""
limpar() {
  [ -n "$FIXTURE_PID" ] && kill "$FIXTURE_PID" 2>/dev/null || true
  rm -f "$CHAVE_PRIVADA" "$URL_ALVO"
}
trap limpar EXIT
install -m 0400 "$CHAVE" "$CHAVE_PRIVADA"

export GIT_SSH_COMMAND="ssh -i $CHAVE_PRIVADA -o IdentitiesOnly=yes \
-o UserKnownHostsFile=$KNOWN_HOSTS -o StrictHostKeyChecking=yes -o BatchMode=yes"

# ---------- 2. Repositório ----------

git config --global --add safe.directory "$RAIZ"
ATUAL=$(git -C "$RAIZ" rev-parse --abbrev-ref HEAD)
[ "$ATUAL" = "$RAMO" ] || falhar "imagem construída fora de '$RAMO' (HEAD=$ATUAL)"
git -C "$RAIZ" config user.name "webqa-vps-bot"
git -C "$RAIZ" config user.email "webqa-vps-bot@users.noreply.github.com"

log "atualizando $RAMO (--ff-only: nunca cria merge silencioso)"
git -C "$RAIZ" pull --ff-only origin "$RAMO"

# ---------- 3. Alvo fixture ----------

cd "$SUITE"
log "subindo o alvo fixture (porta efêmera)"
python fixture_target/servir.py --url-file "$URL_ALVO" > /tmp/alvo.log 2>&1 &
FIXTURE_PID=$!

for _ in $(seq 1 "$ESPERA_MAX"); do
  if [ -s "$URL_ALVO" ]; then break; fi
  kill -0 "$FIXTURE_PID" 2>/dev/null || falhar "alvo fixture morreu ao subir: $(cat /tmp/alvo.log)"
  sleep 1
done
[ -s "$URL_ALVO" ] || falhar "alvo fixture não abriu porta em ${ESPERA_MAX}s (sem flake fantasma: aborta explícito)"

WEBQA_TARGET_URL=$(cat "$URL_ALVO")
export WEBQA_TARGET_URL
# Readiness de verdade: porta aberta não é o mesmo que servir HTML.
python - "$WEBQA_TARGET_URL" <<'PY' || falhar "alvo fixture não respondeu ao GET inicial"
import sys, urllib.request
with urllib.request.urlopen(sys.argv[1], timeout=5) as r:
    sys.exit(0 if r.status == 200 else 1)
PY
log "alvo fixture pronto em $WEBQA_TARGET_URL"

# ---------- 4. Medição ----------

# Contrato primeiro: um check que parou de detectar tornaria a medição de
# estabilidade uma mentira estável.
log "conferindo o contrato do alvo fixture"
# `python -m pytest`, não `pytest`: garante que o interpretador e os pacotes
# instalados sejam os mesmos, sem depender de resolução de PATH.
python -m pytest tests -m verification

log "rodando a dimensão lgpd (FAIL de conformidade é esperado)"
python -m pytest -m lgpd || true   # ÚNICO passo tolerante a falha

log "classificando a execução"
python scripts/estabilidade.py --alvo-fixture

# ---------- 5. Escrita do ledger ----------

# --porcelain e não `git diff`: se o ledger ainda não existir, ele é arquivo
# novo e `git diff` não enxerga não rastreado.
if [ -z "$(git -C "$RAIZ" status --porcelain -- "$LEDGER")" ]; then
  log "ledger inalterado (execução duplicada ou sem testes de navegador) — nada a commitar"
  exit 0
fi

git -C "$RAIZ" add -- "$LEDGER"
git -C "$RAIZ" commit -q -m "chore(ledger): noite $(date -u +%F) [skip ci]"

if git -C "$RAIZ" push origin "HEAD:$RAMO"; then
  log "ledger publicado"
  exit 0
fi

# Modo de falha REAL de um bot que escreve num repo onde humanos também
# mergeiam: alguém empurrou entre o pull e o push. Uma tentativa de rebase.
log "push rejeitado (provável non-fast-forward): rebase e nova tentativa"
git -C "$RAIZ" pull --rebase origin "$RAMO" || falhar "rebase do ledger falhou"
git -C "$RAIZ" push origin "HEAD:$RAMO" || falhar "push falhou após rebase — noite não registrada"
log "ledger publicado após rebase"
