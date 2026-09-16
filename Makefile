PY := .venv/bin/python
export PYTHONPATH := src

.PHONY: help venv contract data features train validate report saturation ablations scenario serve demo check test offline refresh clean

help:
	@echo "make venv      - create .venv and install dependencies"
	@echo "make contract  - export api_contract/openapi.json (frozen; --force to change)"
	@echo "make data      - download and cache all external inputs (network required, once)"
	@echo "make features  - build data/processed/features.parquet"
	@echo "make train     - train models, write models/v1/metrics.json"
	@echo "make validate  - score two held-out events, write metrics_by_event.json (~10 min)"
	@echo "make report    - corrected metrics + calibration into diagnostics/ (~15 min)"
	@echo "make saturation- fire-feature saturation diagnostic, no retrain"
	@echo "make ablations - isolated dryness / ENSO ablations (~30 min)"
	@echo "make scenario  - precompute the demo scenario SQLite"
	@echo "make serve     - run the API on :8000"
	@echo "make check     - contract + offline + metrics regression gates"
	@echo "make offline   - pre-recording gate: run with Wi-Fi OFF"
	@echo "make refresh   - regenerate the published live snapshot (~60s, needs internet)"

# The full development environment: serving deps plus everything needed to
# rebuild the demo. A deployment installs the base package only - see Dockerfile.
venv:
	python3 -m venv .venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -e ".[dev,pipeline]"

contract:
	$(PY) scripts/00_export_contract.py

data:
	$(PY) scripts/01_download.py

features:
	$(PY) scripts/02_build_features.py

train:
	$(PY) scripts/03_train.py

# Generalisation evidence. Trains a throwaway model with both validation events
# withheld; never writes to models/v1/*.joblib and never touches the demo
# scenario. Kept out of `check` because it takes minutes and `check` is the
# pre-recording gate.
validate:
	$(PY) scripts/06_validate_events.py

# Corrected metrics report, threshold recalibration and above-range analysis.
# Writes only to diagnostics/; models/v1 stays frozen and is re-checksummed.
report:
	$(PY) scripts/10_metrics_and_calibration.py

scenario:
	$(PY) scripts/04_precompute_scenario.py

serve:
	$(PY) -m uvicorn haze.api.main:app --reload --port 8000

# Full rebuild from cached raw data. Does not touch the network.
demo: features train scenario
	@echo "Demo artifacts rebuilt. Run 'make offline' before recording."

test:
	$(PY) -m pytest -q

offline:
	$(PY) scripts/05_offline_smoke_test.py

# Regenerate and publish the live snapshot the Pro dashboard reads. Safe to run
# at any time: it publishes only if the new snapshot passes its checks, and
# otherwise leaves the existing one in place. Never touches the replay demo.
refresh:
	@bash scripts/refresh_snapshot.sh

check: test offline
	@echo "All gates passed."

clean:
	rm -rf data/processed/*.parquet models/v1/*.joblib models/v1/*.pt

# Phase 2D experiments. Both write only to diagnostics/ and re-checksum the
# served artifacts and the feature matrix before exiting.
saturation:
	$(PY) scripts/12_saturation_diagnostic.py

ablations:
	$(PY) scripts/13_ablations.py
