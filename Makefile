PY := .venv/bin/python
export PYTHONPATH := src

.PHONY: help venv data features train validate report saturation ablations attribution demo check test refresh clean

help:
	@echo "make venv      - create .venv and install dependencies"
	@echo "make data      - download and cache all external inputs (network required, once)"
	@echo "make features  - build data/processed/features.parquet"
	@echo "make train     - train models, write models/v1/metrics.json"
	@echo "make validate  - score two held-out events, write metrics_by_event.json (~10 min)"
	@echo "make report    - corrected metrics + calibration into diagnostics/ (~15 min)"
	@echo "make saturation- fire-feature saturation diagnostic, no retrain"
	@echo "make ablations - isolated feature ablations, incl. no_ufei (~40 min)"
	@echo "make attribution- daily-resolution attribution refit + lag profile (~1 min)"
	@echo "make check     - test suite: metrics and forecast-uncertainty gates"
	@echo "make refresh   - regenerate the published live snapshot (~60s, needs internet)"

# There is no longer a serving install to keep separate: the API was retired
# and this package exists only to build data and train models. `pipeline` is
# therefore the normal install, not an extra for developers.
venv:
	python3 -m venv .venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -e ".[dev,pipeline]"

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

# Full rebuild from cached raw data. Does not touch the network.
demo: features train
	@echo "Model artifacts rebuilt. Run 'make refresh' to publish a snapshot."

test:
	$(PY) -m pytest -q

# Regenerate and publish the live snapshot the Pro dashboard reads. Safe to run
# at any time: it publishes only if the new snapshot passes its checks, and
# otherwise leaves the existing one in place. Never touches the replay demo.
refresh:
	@bash scripts/refresh_snapshot.sh

check: test
	@echo "All gates passed."

clean:
	rm -rf data/processed/*.parquet models/v1/*.joblib models/v1/*.pt

# Phase 2D experiments. Both write only to diagnostics/ and re-checksum the
# served artifacts and the feature matrix before exiting.
saturation:
	$(PY) scripts/12_saturation_diagnostic.py

ablations:
	$(PY) scripts/13_ablations.py

# Puts a computation behind the daily correlation the README quotes, and tests
# whether attribution is actually stronger at daily resolution. Writes only to
# diagnostics/; re-checksums the served artifacts and the feature matrix.
attribution:
	$(PY) scripts/14_daily_attribution.py
