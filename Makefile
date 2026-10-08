PYTHON  := venv/bin/python
PIP     := venv/bin/pip
PYTEST  := venv/bin/pytest
COMPANY ?= lido

.PHONY: install check test run dry-run dev-run run-with-trends dashboard clean \
        run-company dev-run-company dry-run-company dashboard-company \
        run-lido dev-run-lido dry-run-lido dashboard-lido \
        run-ambrook dev-run-ambrook dry-run-ambrook dashboard-ambrook \
        new-company

install:
	$(PIP) install -r requirements.txt -q

check:
	$(PYTEST) tests/ -q --tb=short

test: check

# ── Legacy targets (read root company.yaml — backward compat) ──────────────

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

# ── Multi-company targets ──────────────────────────────────────────────────

run-company:
	$(PYTHON) __main__.py run --company $(COMPANY) --skip-trends

dev-run-company:
	$(PYTHON) __main__.py run --company $(COMPANY) --queries 3 --skip-trends

dry-run-company:
	$(PYTHON) __main__.py run --company $(COMPANY) --dry-run

dashboard-company:
	COMPANY_SLUG=$(COMPANY) venv/bin/streamlit run dashboard.py

run-lido:
	$(MAKE) run-company COMPANY=lido

dev-run-lido:
	$(MAKE) dev-run-company COMPANY=lido

dry-run-lido:
	$(MAKE) dry-run-company COMPANY=lido

dashboard-lido:
	$(MAKE) dashboard-company COMPANY=lido

# Onboard a new company: make new-company SLUG=acme
new-company:
	@test -n "$(SLUG)" || (echo "Usage: make new-company SLUG=acme" && exit 1)
	@test ! -d companies/$(SLUG) || (echo "companies/$(SLUG) already exists" && exit 1)
	cp -r companies/_template companies/$(SLUG)
	sed -i '' 's/slug: _template/slug: $(SLUG)/' companies/$(SLUG)/profile.yaml
	@echo "Created companies/$(SLUG)/. Edit profile.yaml, queries.yaml, and probes.yaml."

run-ambrook:
	$(MAKE) run-company COMPANY=ambrook

dev-run-ambrook:
	$(MAKE) dev-run-company COMPANY=ambrook

dry-run-ambrook:
	$(MAKE) dry-run-company COMPANY=ambrook

dashboard-ambrook:
	COMPANY_SLUG=ambrook venv/bin/streamlit run dashboard.py --server.port 8502

clean-company:
	rm -f companies/$(COMPANY)/out/*.csv companies/$(COMPANY)/out/*.md
	rm -f companies/$(COMPANY)/data.db
