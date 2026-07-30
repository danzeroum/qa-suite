.PHONY: all backend frontend ux functional acceptance lgpd lgpd-passivo load verify lint sast

all: ; pytest
backend: ; pytest -m backend
frontend: ; pytest -m frontend
ux: ; pytest -m ux
functional: ; pytest -m functional
acceptance: ; pytest -m acceptance
lgpd: ; pytest -m lgpd
lgpd-passivo: ; pytest -m "lgpd and not browser"   # só HTTP, sem navegador
load: ; pytest -m load
verify: ; pytest -m verification tests
lint: ; ruff check webqa checks tests
sast: ; bandit -q -r webqa checks
