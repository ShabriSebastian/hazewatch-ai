#!/usr/bin/env bash
#
# Refresh the published live snapshot. Run this right before submission.
#
#     make refresh
#
# Takes about a minute. It generates a new snapshot from current satellite and
# reanalysis data, checks it, and publishes it only if it passes. If anything
# goes wrong it changes nothing and the previously published snapshot keeps
# being served - so running this and having it fail is always safe.
#
# It never touches the replay demo, the API, or any model artifact.

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY=".venv/bin/python"
PUBLISHED="data/live/latest.json"
CANDIDATE="$(mktemp -t hazesnap).json"
RAW_URL="https://raw.githubusercontent.com/ShabriSebastian/hazewatch-ai/main/data/live/latest.json"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\n\033[31mSTOPPED: %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- preconditions
say "1/5  Checking preconditions"
[ -x "$PY" ] || die "No virtualenv at $ROOT/$PY. Run: make venv"
[ -f models/v1/rf_forecast.joblib ] \
  || die "Model missing at models/v1/rf_forecast.joblib (it is gitignored, ~2 GB).
        Restore it with:  gh release download v1 --pattern rf_forecast.joblib --output models/v1/rf_forecast.joblib"
git rev-parse --abbrev-ref HEAD | grep -qx main \
  || die "Not on the main branch. The published snapshot is read from main."
echo "     ok - venv, model, branch"

# ------------------------------------------------------------------- generate
say "2/5  Generating a snapshot from live data (~60s)"
echo "     Fetching NASA FIRMS hotspots and Open-Meteo weather/CAMS, then"
echo "     running the served model. Needs internet."
PYTHONPATH=src "$PY" -u scripts/07_live_snapshot.py --out "$CANDIDATE" \
  || die "Snapshot generation failed. Nothing was published; the existing
        snapshot is untouched and still being served. Safe to retry."

# ----------------------------------------------------------------------- gate
say "3/5  Checking it before publishing"
set +e
PYTHONPATH=src "$PY" scripts/08_gate_snapshot.py \
  --candidate "$CANDIDATE" --published "$PUBLISHED"
GATE=$?
set -e

case "$GATE" in
  0) echo "     ok - passed, and it differs from what is published" ;;
  2) printf '\n\033[33mNothing to do.\033[0m The new snapshot is identical to the published one\n'
     printf 'apart from timestamps, which means upstream data has not refreshed yet.\n'
     printf 'The site is already showing the latest available data. No commit made.\n\n'
     rm -f "$CANDIDATE"; exit 0 ;;
  *) die "The snapshot failed its checks (see the reason above). Nothing was
        published; the existing snapshot is untouched and still being served." ;;
esac

# -------------------------------------------------------------------- publish
say "4/5  Publishing"
cp "$CANDIDATE" "$PUBLISHED"
rm -f "$CANDIDATE"
git add "$PUBLISHED"
git commit -q -m "live snapshot $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git push -q origin main
echo "     ok - committed and pushed"

# --------------------------------------------------------------------- verify
say "5/5  Verifying what the site will serve"
GEN=$("$PY" -c "import json;print(json.load(open('$PUBLISHED'))['generated_at'])")
ALERTS=$("$PY" -c "import json;d=json.load(open('$PUBLISHED'));print(sum(1 for i in d['institutions'] if i['alert']))")
echo "     generated_at : $GEN"
echo "     alerting     : $ALERTS of 6 institutions"

printf '\n\033[32mDone.\033[0m The dashboard will show this within ~5 minutes.\n'
printf 'GitHub caches raw files for 5 minutes, so it is not instant.\n\n'
printf 'Check it here:\n'
printf '  %s\n' "$RAW_URL"
printf '  https://hazewatch-ai.vercel.app/pro/live-monitor\n\n'
printf 'The panel shows the generation time above, so a slightly older snapshot\n'
printf 'is labelled honestly rather than passed off as current.\n\n'
