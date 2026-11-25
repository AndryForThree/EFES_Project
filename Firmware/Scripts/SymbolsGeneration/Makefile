PY ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: all check
all:
	$(PY) generate_assets.py
check:
	$(PY) -m unittest -v test_generate_assets
