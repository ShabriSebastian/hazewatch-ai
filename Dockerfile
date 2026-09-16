# Serving image for the haze early-warning API.
#
# The API does no inference and makes no network call: it reads a precomputed
# SQLite scenario. So this installs the base package only - no pandas, no
# scikit-learn, no model artifacts - and the image stays small enough to build
# and wake quickly on a free tier.
#
# Build:  docker build -t haze-api .
# Run:    docker run --rm -p 8000:8000 -e PORT=8000 haze-api
FROM python:3.12-slim

# HAZE_ROOT is required, not cosmetic: `pip install` puts the package in
# site-packages, where config.py's default walk up the tree lands in lib/ and
# misses the data directory entirely. Without this the API finds no scenario
# database and falls back to synthetic fixtures.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HAZE_ROOT=/app

WORKDIR /app

# Dependencies first, so application edits do not invalidate the install layer.
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --upgrade pip && pip install .

# The demo data. `data/replay/*.sqlite` is tracked in git precisely so it ships
# with the app - without it the API silently falls back to synthetic fixtures.
COPY data/replay/ ./data/replay/
COPY models/v1/metrics.json models/v1/feature_spec.json models/v1/training_ranges.json ./models/v1/

# Fail the build rather than ship an image that would serve invented numbers.
RUN test -f data/replay/scenario_2023_sept.sqlite \
    || (echo "FATAL: scenario database missing - the API would serve fixtures." && exit 1)

RUN useradd --create-home --uid 10001 haze && chown -R haze:haze /app
USER haze

EXPOSE 8000

# One worker, deliberately. The replay clock is in-process state; a second
# worker would give some visitors a different clock than others.
CMD ["sh", "-c", "uvicorn haze.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
