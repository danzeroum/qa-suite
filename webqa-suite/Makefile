.PHONY: referencia-visual all backend frontend ux functional acceptance lgpd seguranca lgpd-passivo load verify lint sast estabilidade fixture vps-smoke audita-design campanha campanha-vps sumario painel telemetria mutar cockpit medicoes build

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
# Regrava a linha de base visual do alvo FABRICADO (GUI-VIS-01/02) com manifesto
# de procedencia. So o alvo fabricado: captura de alvo real nao e versionavel
# (R19 — pixel nao passa pela borda de sanitizacao). Variacao com
# `regravar: false` e PULADA de proposito.
referencia-visual: ; python scripts/referencia_visual.py
vps-smoke: ; scripts/vps_smoke.sh   # valida VPS antes de agendar o cron
audita-design: ; python scripts/audita_design.py --suite   # gate do pacote de design (§12)
campanha: ; python scripts/campanha.py   # nivel sistema: alvos reais x N, consolidado
# Campanha no ambiente controlado (VPS): Chromium com egresso direto, logo
# FCP/LCP/CLS preenchidos. Sem segredos e sem WEBQA_ORIGEM — nao toca o ledger.
# Rodar FORA da janela do noturno; ver docs/VPS.md §campanha.
campanha-vps: ; docker compose -f ../docker/compose.yml run --rm campanha
# Residuo de `report/` muda a contagem do dogfooding: tests/test_report_dogfooding.py
# le report/campanha/*/run*/summary.json e PULA quando nao ha execucao real, entao
# "N passed, 3 skipped" deixa de ser reproduzivel entre maquinas — e quem compara com
# o CI (que comeca limpo) persegue uma diferenca que nao existe no codigo.
#
# O aviso IGNORA summary.json/summary.html: toda execucao de pytest os reescreve,
# entao avisar por causa deles dispararia sempre — e aviso que dispara sempre e
# aviso que ninguem le. So o que a verificacao NAO produz sozinha e residuo.
# AVISA e nao apaga: o artefato pode ser exatamente o que a pessoa esta investigando.
verify:
	@ls report 2>/dev/null | grep -qvE '^summary\.(json|html)$$' && echo "AVISO: report/ tem residuo alem do summary da ultima execucao (campanha/, smoke-gui/, medicoes...). A contagem de skips do dogfooding pode divergir do CI, que comeca limpo. Apague com 'rm -rf report' antes de comparar." || true
	pytest -m verification tests
	@# Placar das ancoras arquivo:linha (OS-57). Fora do pytest de proposito: o
	@# numero de PENDENTES precisa aparecer na tela em toda execucao, e pytest
	@# engole print. Cobertura parcial silenciosa induz mais confianca que
	@# cobertura nenhuma. A reprovacao em si e do tests/test_ancoras.py.
	python scripts/afere_ancoras.py
	@# Placar dos coletores JS_ sem check que os execute (OS-52), mesmo motivo:
	@# o numero precisa aparecer, e pytest engole print.
	python scripts/afere_simbolos.py
	@# Placar do mapa criterio->teste (OS-53), mesma licao do placar invisivel.
	python scripts/exporta_conformidade.py --placar
# Cockpit de testes: leitura AST do repo -> report/cockpit.html + .json (D1k).
# Arquivo unico, offline, sem tocar a rede. So LE o codigo (nao executa nada).
cockpit: ; python scripts/cockpit.py --html
# Medicao do motor (D5k): report/medicoes.json de coverage.json (se houver) +
# ruff C901. O cockpit LE este arquivo; rode `make medicoes cockpit` para o motor
# aparecer preenchido. Complexidade sempre; cobertura so apos um run --cov.
medicoes: ; python scripts/medicoes.py
# Constroi o wheel + sdist do padrao instalavel (frente E, E2) em dist/. So a
# biblioteca webqa/ viaja; a versao vem de webqa.__version__. Publicar (onde) e
# decisao do dono — este alvo so PRODUZ o artefato versionado.
build: ; python -m build
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
