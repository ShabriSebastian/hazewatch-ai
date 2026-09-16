#!/usr/bin/env python3
"""Export the OpenAPI schema to api_contract/openapi.json.

This file is the frozen contract handed to the frontend team. After the first
export, changes must be additive only - new optional fields, new endpoints.
`tests/test_contract.py` fails the build on any breaking change.

Usage:
    python scripts/00_export_contract.py            # write if unchanged or new
    python scripts/00_export_contract.py --force    # overwrite regardless
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haze import config  # noqa: E402
from haze.api.main import app  # noqa: E402

OUT = config.CONTRACT / "openapi.json"


def main() -> int:
    force = "--force" in sys.argv
    spec = app.openapi()
    payload = json.dumps(spec, indent=2, sort_keys=True) + "\n"

    config.CONTRACT.mkdir(parents=True, exist_ok=True)

    if OUT.exists() and not force:
        existing = OUT.read_text()
        if existing == payload:
            print(f"Contract unchanged: {OUT}")
            return 0
        print(f"Contract differs from {OUT}.")
        print("Re-run with --force if the change is intentional and additive.")
        return 1

    OUT.write_text(payload)
    paths = len(spec.get("paths", {}))
    schemas = len(spec.get("components", {}).get("schemas", {}))
    print(f"Wrote {OUT}")
    print(f"  {paths} paths, {schemas} schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
