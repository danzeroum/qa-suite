.PHONY: all backend frontend ux functional acceptance lgpd lgpd-passivo load verify lint sast estabilidade fixture vps-smoke audita-design campanha campanha-vps

all: ; pytest
backend: ; pytest -m backend
frontend: ; pytest -m frontend
ux: ; pytest -m ux
functional: ; pytest -m functional
acceptance: ; pytest -m acceptance
lgpd: ; pytest -m lgpd
lgpd-passivo: ; pytest -m "lgpd and not browser"   # só HTTP, sem navegador
load: ; pytest -m load
estabilidade: ; python scripts/estabilidade.py
fixture: ; python fixture_target/servir.py   # alvo fabricado, porta efemera
vps-smoke: ; scripts/vps_smoke.sh   # valida VPS antes de agendar o cron
audita-design: ; python scripts/audita_design.py --suite   # gate do pacote de design (§12)
campanha: ; python scripts/campanha.py   # nivel sistema: alvos reais x N, consolidado
# Campanha no ambiente controlado (VPS): Chromium com egresso direto, logo
# FCP/LCP/CLS preenchidos. Sem segredos e sem WEBQA_ORIGEM — nao toca o ledger.
# Rodar FORA da janela do noturno; ver docs/VPS.md §campanha.
campanha-vps: ; docker compose -f ../docker/compose.yml run --rm campanha
verify: ; pytest -m verification tests
lint: ; ruff check webqa checks tests scripts fixture_target
# Mesmos comandos do CI (.github/workflows/ci.yml): rigor total na biblioteca;
# nos checks, as exceções já documentadas nos per-file-ignores do ruff.
sast:
	bandit -q -c pyproject.toml -r webqa scripts fixture_target
	bandit -q -c pyproject.toml -r checks --skip B101,B110,B112
