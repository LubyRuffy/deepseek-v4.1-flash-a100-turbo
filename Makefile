PYTHON ?= python3

.PHONY: check test docs-check version release
check: test docs-check

test:
	$(PYTHON) -m pytest -q tests

docs-check:
	$(PYTHON) scripts/docs_check.py

version:
	$(PYTHON) scripts/release.py version

release: check
	$(PYTHON) scripts/release.py publish
