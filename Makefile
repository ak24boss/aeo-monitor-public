PYTHON := venv/bin/python
PIP    := venv/bin/pip
PYTEST := venv/bin/pytest

.PHONY: install check test run dry-run dev-run run-with-trends dashboard clean

install:
	$(PIP) install -r requirements.txt -q

check:
	$(PYTEST) tests/ -q --tb=short

test: check

run:
	$(PYTHON) __main__.py run --skip-trends

dry-run:
	$(PYTHON) __main__.py run --dry-run

dev-run:
	$(PYTHON) __main__.py run --queries 3 --skip-trends

run-with-trends:
	$(PYTHON) __main__.py run

dashboard:
	venv/bin/streamlit run dashboard.py

clean:
	rm -f out/*.csv out/*.md aeo_monitor.db
