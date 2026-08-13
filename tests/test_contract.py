"""The contract is frozen. This test fails on any breaking change.

Additive changes (new endpoints, new optional fields) are allowed and require
re-running `python scripts/00_export_contract.py --force`. Renames, removals and
type changes are not - the frontend is built against this file.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from haze import config
from haze.api.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def frozen() -> dict:
    path = config.CONTRACT / "openapi.json"
    if not path.exists():
        pytest.skip("No frozen contract yet - run scripts/00_export_contract.py")
    with path.open() as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def live() -> dict:
    return app.openapi()


def test_no_endpoint_removed(frozen, live):
    missing = set(frozen["paths"]) - set(live["paths"])
    assert not missing, f"Endpoints removed from the frozen contract: {sorted(missing)}"


def test_no_method_removed(frozen, live):
    for path, ops in frozen["paths"].items():
        live_ops = set(live["paths"].get(path, {}))
        missing = set(ops) - live_ops
        assert not missing, f"{path}: methods removed {sorted(missing)}"


def test_no_schema_removed(frozen, live):
    frozen_schemas = set(frozen.get("components", {}).get("schemas", {}))
    live_schemas = set(live.get("components", {}).get("schemas", {}))
    missing = frozen_schemas - live_schemas
    assert not missing, f"Schemas removed: {sorted(missing)}"


def test_no_required_field_added_or_retyped(frozen, live):
    """Adding a required field, or changing a field's type, breaks existing clients."""
    frozen_schemas = frozen.get("components", {}).get("schemas", {})
    live_schemas = live.get("components", {}).get("schemas", {})

    for name, spec in frozen_schemas.items():
        live_spec = live_schemas.get(name)
        if live_spec is None:
            continue  # covered by test_no_schema_removed

        added_required = set(live_spec.get("required", [])) - set(spec.get("required", []))
        assert not added_required, f"{name}: new required fields {sorted(added_required)}"

        for field, definition in spec.get("properties", {}).items():
            live_def = live_spec.get("properties", {}).get(field)
            assert live_def is not None, f"{name}.{field} was removed"
            if "type" in definition and "type" in live_def:
                assert definition["type"] == live_def["type"], (
                    f"{name}.{field} type changed: "
                    f"{definition['type']} -> {live_def['type']}"
                )


def test_enum_values_not_removed(frozen, live):
    """Removing an enum value breaks clients that switch on it."""
    frozen_schemas = frozen.get("components", {}).get("schemas", {})
    live_schemas = live.get("components", {}).get("schemas", {})

    for name, spec in frozen_schemas.items():
        if "enum" not in spec:
            continue
        live_values = set(live_schemas.get(name, {}).get("enum", []))
        missing = set(spec["enum"]) - live_values
        assert not missing, f"{name}: enum values removed {sorted(missing)}"


def test_every_frozen_endpoint_still_responds(frozen):
    """A contract that documents a 404 is not a contract."""
    skip_params = {"{institution_id}"}
    for path, ops in frozen["paths"].items():
        if "get" not in ops:
            continue
        concrete = path
        if any(p in path for p in skip_params):
            concrete = path.replace("{institution_id}", "my-kch-greenroad")
        response = client.get(concrete)
        assert response.status_code in (200, 503), (
            f"GET {concrete} returned {response.status_code}: {response.text[:200]}"
        )
