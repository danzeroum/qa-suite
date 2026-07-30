.PHONY: all backend frontend ux functional acceptance load verify lint sast

all: ; pytest
backend: ; pytest -m backend
frontend: ; pytest -m frontend
ux: ; pytest -m ux
functional: ; pytest -m functional
acceptance: ; pytest -m acceptance
load: ; pytest -m load
verify: ; pytest -m verification tests
lint: ; ruff check webqa checks tests
sast: ; bandit -q -r webqa checks
