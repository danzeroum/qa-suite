#!/usr/bin/env bash
# Smoke da VPS: valida imagem, segredos e pipeline ANTES de agendar o cron.
#
# Paridade dev/prod (12-Factor): roda exatamente os comandos que o cron vai
# rodar — apenas sem a caneta (WEBQA_DRY_RUN=1 pula só commit e push). Um
# noturno que falha às 3h da manhã é um dia perdido; falhar agora é de graça.
#
# Cada passo imprime PASS ou FAIL. No primeiro FAIL o script para e cita a seção
# de docs/VPS.md que corrige — mensagem sem stacktrace, porque quem lê isso está
# instalando, não depurando Python.
#
# Regra de sigilo: caminhos de segredo podem aparecer no log; BYTES de segredo
# nunca. Nenhum passo ecoa conteúdo de chave — nem em caso de falha.
set -uo pipefail   # sem -e: cada passo decide o próprio destino

RAIZ=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
COMPOSE_FILE="$RAIZ/docker/compose.yml"
IMAGEM=${WEBQA_IMAGEM:-webqa-estabilidade:local}
CHAVE="$RAIZ/docker/secrets/deploy_key"
KNOWN_HOSTS="$RAIZ/docker/secrets/known_hosts"
UID_CONTAINER=${WEBQA_UID_CONTAINER:-1000}   # pwuser da imagem do Playwright
TOTAL=5
OK=0

titulo() { printf '\n[%d/%d] %s\n' "$1" "$TOTAL" "$2"; }
pass() { OK=$((OK + 1)); printf '  PASS  %s\n' "$1"; }
fail() {
  printf '  FAIL  %s\n' "$1"
  printf '        corrija: %s\n' "$2"
  printf '\n%d/%d passos OK — smoke interrompido, cron NÃO deve ser agendado.\n' "$OK" "$TOTAL"
  exit 1
}

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

# ---------- 1. Daemon e build ----------

titulo 1 "Docker disponível e imagem construindo"
if ! command -v docker >/dev/null 2>&1; then
  fail "docker não encontrado no PATH" "instale o Docker Engine e o Compose v2 (VPS.md §Instalação)"
fi
if ! docker info >/dev/null 2>&1; then
  fail "daemon do Docker não responde" \
       "instale/inicie o Docker (\`sudo systemctl start docker\`) e garanta permissão do usuário (VPS.md §Instalação)"
fi
if ! compose build; then
  fail "\`docker compose build\` falhou" "veja o erro acima; VPS.md §Imagem"
fi
pass "imagem $IMAGEM construída"

# ---------- 2. Nenhum segredo em camada ----------

titulo 2 "Nenhum segredo em camada de imagem"
HISTORICO=$(docker history --no-trunc --format '{{.CreatedBy}}' "$IMAGEM" 2>/dev/null) || \
  fail "não foi possível ler o histórico de $IMAGEM" "confirme o nome da imagem (VPS.md §Imagem)"
# Só o NOME do padrão casado é reportado: imprimir a linha poderia vazar a
# própria chave que estamos tentando manter fora da imagem.
for padrao in 'deploy_key' 'BEGIN OPENSSH' 'id_rsa' 'id_ed25519'; do
  if printf '%s' "$HISTORICO" | grep -qiF "$padrao"; then
    fail "camada de imagem menciona '$padrao'" \
         "remova o COPY do segredo; ele é montado em runtime (VPS.md §Deploy key e .dockerignore)"
  fi
done
pass "docker history limpo (deploy_key, BEGIN OPENSSH, id_rsa, id_ed25519)"

# ---------- 3. Segredos presentes e com permissão fechada ----------

titulo 3 "Segredos presentes, 0400 e legíveis pelo container"
for arquivo in "$CHAVE" "$KNOWN_HOSTS"; do
  [ -f "$arquivo" ] || fail "ausente: $arquivo" \
    "gere os segredos (VPS.md §Deploy key e §known_hosts)"
  [ -s "$arquivo" ] || fail "vazio: $arquivo" \
    "regere o arquivo (VPS.md §Deploy key e §known_hosts)"

  MODO=$(stat -c '%a' "$arquivo")
  [ "$MODO" = "400" ] || fail "$arquivo está com permissão $MODO, esperado 400" \
    "rode \`chmod 400 $arquivo\` (VPS.md §Deploy key)"

  # A montagem preserva o uid do host: chave 0400 de outro dono é ilegível para
  # o usuário não-root do container, e o noturno morreria no `install`.
  DONO=$(stat -c '%u' "$arquivo")
  [ "$DONO" = "$UID_CONTAINER" ] || fail \
    "$arquivo pertence ao uid $DONO; o container roda como uid $UID_CONTAINER e não conseguiria ler" \
    "rode \`sudo chown $UID_CONTAINER $arquivo\` (VPS.md §Deploy key)"
done
pass "deploy key e known_hosts com 0400 e uid $UID_CONTAINER"

# ---------- 4. Autenticação no GitHub pela deploy key ----------

titulo 4 "Deploy key autentica no github.com"
SAIDA_SSH=$(compose run --rm --entrypoint sh estabilidade -c '
  ssh -i /run/secrets/deploy_key -o IdentitiesOnly=yes \
      -o UserKnownHostsFile=/run/secrets/known_hosts \
      -o StrictHostKeyChecking=yes -o BatchMode=yes \
      -T git@github.com 2>&1' 2>&1)
# O GitHub responde à deploy key e encerra com código 1 — o veredito está na
# mensagem, não no código de saída.
if printf '%s' "$SAIDA_SSH" | grep -q 'successfully authenticated'; then
  pass "github.com aceitou a deploy key"
elif printf '%s' "$SAIDA_SSH" | grep -qi 'host key verification failed'; then
  fail "verificação de host key falhou" \
       "regere o known_hosts e confira o fingerprint (VPS.md §known_hosts do github.com)"
elif printf '%s' "$SAIDA_SSH" | grep -qi 'permission denied'; then
  fail "github.com recusou a chave" \
       "cadastre a chave PÚBLICA em Settings → Deploy keys com Allow write access (VPS.md §Deploy key)"
else
  printf '        resposta do ssh: %s\n' "$(printf '%s' "$SAIDA_SSH" | tail -3)"
  fail "não foi possível confirmar a autenticação" \
       "verifique a rede da VPS e o cadastro da deploy key (VPS.md §Deploy key)"
fi

# ---------- 5. Pipeline completo, sem escrever ----------

titulo 5 "Pipeline completo em dry-run (nada é commitado)"
ANTES=$(git -C "$RAIZ" rev-parse HEAD 2>/dev/null || echo desconhecido)
REMOTO_ANTES=$(git -C "$RAIZ" ls-remote origin -h refs/heads/main 2>/dev/null | cut -f1)

SAIDA=$(compose run --rm -e WEBQA_DRY_RUN=1 estabilidade 2>&1)
CODIGO=$?
printf '%s\n' "$SAIDA" | sed 's/^/        | /' | tail -8

[ "$CODIGO" -eq 0 ] || fail "o noturno saiu com código $CODIGO" \
  "leia o log acima e a tabela de modos de falha (VPS.md §Modos de falha)"
printf '%s' "$SAIDA" | grep -q 'streak' || fail \
  "a saída não contém 'streak' — o classificador não chegou a rodar" \
  "leia o log acima (VPS.md §O que o noturno faz)"
printf '%s' "$SAIDA" | grep -q 'commit e push PULADOS' || fail \
  "o dry-run não confirmou que commit e push foram pulados" \
  "confirme que a imagem foi reconstruída após a última mudança (VPS.md §Imagem)"

DEPOIS=$(git -C "$RAIZ" rev-parse HEAD 2>/dev/null || echo desconhecido)
[ "$ANTES" = "$DEPOIS" ] || fail "o HEAD local mudou durante o dry-run ($ANTES → $DEPOIS)" \
  "não deveria acontecer: abra uma issue com o log acima"
if [ -n "$REMOTO_ANTES" ]; then
  REMOTO_DEPOIS=$(git -C "$RAIZ" ls-remote origin -h refs/heads/main 2>/dev/null | cut -f1)
  [ "$REMOTO_ANTES" = "$REMOTO_DEPOIS" ] || fail \
    "o remoto avançou durante o dry-run ($REMOTO_ANTES → $REMOTO_DEPOIS)" \
    "o dry-run escreveu no repositório: NÃO agende o cron e reporte"
  pass "pipeline completo, HEAD local e remoto intactos"
else
  # Sem acesso ao remoto o veredito fica mais fraco — e isso é dito, não omitido.
  pass "pipeline completo, HEAD local intacto (remoto não consultado: \`ls-remote\` indisponível)"
fi

printf '\n%d/%d PASS\n' "$OK" "$TOTAL"
printf 'Pronto: agende o cron (VPS.md §agendamento)\n'
