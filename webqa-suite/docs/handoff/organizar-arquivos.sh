#!/usr/bin/env bash
# Organiza os arquivos do handoff da Fase C nos lugares certos do repositório.
# RODE A PARTIR DA RAIZ DO REPO (qa-suite/), onde existe a pasta webqa-suite/.
#
#   bash webqa-suite/docs/handoff/organizar-arquivos.sh
#
# Só toca nos 12 arquivos gerados no handoff; não mexe em mais nada da pasta.
set -euo pipefail

H="webqa-suite/docs/handoff"
[ -d "$H" ] || { echo "ERRO: rode da raiz do repo (qa-suite/), onde existe $H"; exit 1; }

mover() {  # origem destino
  local src="$1" dst="$2"
  if [ ! -e "$src" ]; then echo "  (ausente, pulado) $src"; return 0; fi
  mkdir -p "$(dirname "$dst")"
  git mv -f "$src" "$dst" 2>/dev/null || mv -f "$src" "$dst"
  echo "  $src  ->  $dst"
}

echo "== Código e dados da Fase C =="
mover "$H/escopo.py"                        "webqa-suite/webqa/escopo.py"
mover "$H/audit.py"                         "webqa-suite/webqa/audit.py"
mover "$H/test_escopo.py"                   "webqa-suite/tests/test_escopo.py"
mover "$H/test_audit_fase_c.py"             "webqa-suite/tests/test_audit_fase_c.py"
mover "$H/escopo-autorizado.yaml.example"   "webqa-suite/escopo-autorizado.yaml.example"
mover "$H/caminhos-sensiveis.yaml.example"  "webqa-suite/data/caminhos-sensiveis.yaml.example"

echo "== Governança (CODEOWNERS vai para a RAIZ do repo) =="
mover "$H/CODEOWNERS"                        ".github/CODEOWNERS"

echo "== Documentos do plano (para docs/; o handoff em si fica onde está) =="
for d in FASE-C.md FASE-C-revisao-1.md FASE-C-revisao-2.md FASE-C-revisao-3.md; do
  mover "$H/$d" "webqa-suite/docs/$d"
done

echo
echo "== Validação =="
( cd webqa-suite && python -m pytest tests/test_escopo.py tests/test_audit_fase_c.py -q )
echo "OK. Agora rode o gate completo:  cd webqa-suite && make verify && make lint"
