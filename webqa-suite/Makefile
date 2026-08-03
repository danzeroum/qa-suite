.PHONY: all backend frontend ux functional acceptance lgpd seguranca lgpd-passivo load verify lint sast estabilidade fixture vps-smoke audita-design campanha campanha-vps sumario painel telemetria mutar cockpit

all: ; pytest
backend: ; pytest -m backend
frontend: ; pytest -m frontend
ux: ; pytest -m ux
functional: ; pytest -m functional
acceptance: ; pytest -m acceptance
lgpd: ; pytest -m lgpd
seguranca: ; pytest -m seguranca
lgpd-passivo: ; pytest -m "lgpd and not browser"   # só HTTP, sem navegador
load: ; pytest -m load
estabilidade: ; python scripts/estabilidade.py
# Painel do ledger. Só LE o ledger — nunca escreve, em nenhuma combinacao de
# flags, entao e seguro rodar no GitHub (docs/VPS.md).
painel: ; python scripts/estabilidade.py --painel
# Agrega campanhas JA executadas. Nao faz requisicao nenhuma (docs/TELEMETRIA.md).
telemetria: ; python scripts/telemetria.py
# Anexo assistido por IA, APÓS o pytest e em processo separado (docs/LLM.md).
# Sem WEBQA_LLM_ENABLED=1 ou sem runtime local: nao gera nada e sai 0.
sumario: ; python scripts/sumario.py
fixture: ; python fixture_target/servir.py   # alvo fabricado, porta efemera
vps-smoke: ; scripts/vps_smoke.sh   # valida VPS antes de agendar o cron
audita-design: ; python scripts/audita_design.py --suite   # gate do pacote de design (§12)
campanha: ; python scripts/campanha.py   # nivel sistema: alvos reais x N, consolidado
# Campanha no ambiente controlado (VPS): Chromium com egresso direto, logo
# FCP/LCP/CLS preenchidos. Sem segredos e sem WEBQA_ORIGEM — nao toca o ledger.
# Rodar FORA da janela do noturno; ver docs/VPS.md §campanha.
campanha-vps: ; docker compose -f ../docker/compose.yml run --rm campanha
verify: ; pytest -m verification tests
# Cockpit de testes: leitura AST do repo -> report/cockpit.html + .json (D1k).
# Arquivo unico, offline, sem tocar a rede. So LE o codigo (nao executa nada).
cockpit: ; python scripts/cockpit.py --html
# Mutação escopada na superfície de segurança. NAO roda no PR (lento: ~1 min por
# modulo); roda no noturno agendado e a mao. O ambiente TEM de estar limpo — este
# harness inverte a logica dos gates de proposito. Ver
# docs/handoff/HANDOFF-Q1-instrumentacao.md §Q5.
mutar: ; python scripts/mutar.py . webqa/escopo.py tests/test_escopo.py tests/test_fase_c_travada.py
lint: ; ruff check webqa checks tests scripts fixture_target
# Mesmos comandos do CI (.github/workflows/ci.yml): rigor total na biblioteca;
# nos checks, as exceções já documentadas nos per-file-ignores do ruff.
sast:
	bandit -q -c pyproject.toml -r webqa scripts fixture_target
	bandit -q -c pyproject.toml -r checks --skip B101,B110,B112
