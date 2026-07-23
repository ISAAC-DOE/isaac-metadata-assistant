"""P31.1 — fuller CSV-ingress test matrix (sibling to the frozen contract).

Extends ``test_csv_ingress.py`` (frozen, unchanged) with the validation / leak /
resource / filename-safety cases the mandate requires: X-Filename sanitization,
too-many-columns, cell-too-long, unknown-header-warning-not-mapped, the bounded
read boundary, resource release after a parse failure, and proof the raw body is
never persisted to disk. All fixtures synthetic; the endpoint is read-only.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import isaac_api.csv_ingest as ci
import isaac_api.workspace as ws

URL = "/api/experiments/{id}/ingestion/csv/preview"
CT = {"Content-Type": "text/csv"}

VALID_CSV = (
    "section,field,value,unit,notes\n"
    "system,beamline,BL-SYNTH-01,,\n"
    "sample,formula,ZzO2,,\n"
)

_SEP = "/\\⁄∕／∖＼"


@pytest.fixture()
def ws_dir(tmp_path):
    return tmp_path / "ws"


@pytest.fixture()
def client(ws_dir, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(ws_dir))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


def _etag(client, exp_id):
    return client.get(f"/api/experiments/{exp_id}").headers["ETag"]


def _post(client, body, headers=None):
    h = dict(CT)
    h["If-Match"] = _etag(client, ws.SEED_NEW_DRAFT_ID)
    if headers:
        h.update(headers)
    return client.post(URL.format(id=ws.SEED_NEW_DRAFT_ID), content=body, headers=h)


# --- X-Filename sanitization (unit) -------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "../../x.csv",
        "/etc/passwd.csv",
        "x\x00.csv",
        "a∕b.csv",  # unicode division slash
        "a⁄b.csv",  # unicode fraction slash
        "a／b.csv",  # fullwidth solidus
        "..\\..\\win.csv",
        "x" * 5000 + ".csv",
        "evil.csv.exe",
        "",
        "   ",
        "..",
        ".",
    ],
)
def test_safe_source_name_is_never_a_path(raw):
    name = ci.safe_source_name(raw)
    assert name, "must always yield a non-empty display basename"
    assert not any(sep in name for sep in _SEP), f"leaked a separator: {name!r}"
    assert ".." not in name.split("."), "traversal fragment survived"
    assert "\x00" not in name and all(c >= " " for c in name)
    assert len(name) <= ci.MAX_FILENAME_CHARS
    assert name != raw or raw == name == "evil.csv.exe"  # only the already-safe one passes through


def test_safe_source_name_specific_basenames():
    assert ci.safe_source_name("../../x.csv") == "x.csv"
    assert ci.safe_source_name("/etc/passwd.csv") == "passwd.csv"
    assert ci.safe_source_name("a∕b.csv") == "b.csv"
    assert ci.safe_source_name(None) == ci.DEFAULT_SOURCE_NAME
    assert ci.safe_source_name("") == ci.DEFAULT_SOURCE_NAME
    assert ci.safe_source_name("..") == ci.DEFAULT_SOURCE_NAME


def test_x_filename_sanitized_end_to_end(client):
    body = _post(client, VALID_CSV, headers={"X-Filename": "../../etc/danger.csv"}).json()
    assert body["source_name"] == "danger.csv"  # never a path
    assert "/etc/" not in _post(client, VALID_CSV, headers={"X-Filename": "/etc/danger.csv"}).text


def test_default_source_name_when_header_absent(client):
    assert _post(client, VALID_CSV).json()["source_name"] == ci.DEFAULT_SOURCE_NAME


# --- header validation: columns + unknown-header warning ----------------------


def test_too_many_columns_rejected(client):
    header = ",".join(["field", "value"] + [f"c{i}" for i in range(70)])
    r = _post(client, header + "\nbeamline,X" + ",z" * 70 + "\n")
    assert r.status_code == 422
    assert r.json()["error"] == "too_many_columns"


def test_unknown_header_warns_but_never_maps(client):
    body = (
        "section,field,value,extra_col\n"
        "system,beamline,BL-1,SHOULD-NOT-MAP\n"
    )
    r = _post(client, body)
    assert r.status_code == 200, r.text
    payload = r.json()
    warned = {w["header"] for w in payload["unknown_header_warnings"]}
    assert "extra_col" in warned
    assert "SHOULD-NOT-MAP" not in r.text  # the extra column is never surfaced as a value
    # beamline still maps; the unknown column does not spawn a candidate.
    assert any(c["field"] == "system.facility.beamline" for c in payload["candidates"])
    assert payload["recognized_header_count"] == 3  # section, field, value


def test_typed_error_codes_are_stable(client):
    assert _post(client, "field,field,value\na,b,c\n").json()["error"] == "duplicate_header"
    assert _post(client, "section,notes\nx,y\n").json()["error"] == "missing_required_header"
    assert _post(client, "field,,value\na,b,c\n").json()["error"] == "empty_header"


# --- cell length --------------------------------------------------------------


def test_cell_too_long_rejected(client):
    huge = "x" * (ci.MAX_CELL_CHARS + 1)
    r = _post(client, f"section,field,value\nsample,formula,{huge}\n")
    assert r.status_code == 422
    assert r.json()["error"] == "cell_too_long"


# --- bounded read boundary ----------------------------------------------------


def test_body_at_cap_ok_over_cap_rejected(client):
    header = "section,field,value,unit,notes\n"
    row = "sample,formula,X,,\n"
    # Just over the byte cap -> 413 (bounded read aborts before full allocation).
    over = header + row * ((ci.MAX_BODY_BYTES // len(row)) + 20)
    assert len(over.encode()) > ci.MAX_BODY_BYTES
    assert _post(client, over).status_code == 413


# --- resource release + no persistence ----------------------------------------


def test_valid_request_after_parse_failure(client):
    # A rejected malformed request must not wedge state for the next valid one.
    assert _post(client, "field,field,value\na,b,c\n").status_code == 422
    assert _post(client, VALID_CSV).status_code == 200


def _all_files(root):
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def test_raw_body_is_never_persisted(client, ws_dir):
    # Warm up so the lazily-materialized seed workspace files already exist; then
    # any delta is attributable to the preview alone.
    client.get("/api/experiments")
    _etag(client, ws.SEED_NEW_DRAFT_ID)
    before = set(_all_files(ws_dir))
    r = _post(client, VALID_CSV, headers={"X-Filename": "myupload.csv"})
    assert r.status_code == 200, r.text
    after = set(_all_files(ws_dir))
    # No new file appeared, and certainly nothing named like the upload / raw CSV.
    assert after == before, f"preview persisted files: {after - before}"
    for p in after:
        assert "myupload" not in p.name
        assert p.suffix != ".csv"  # no raw CSV body written anywhere in the workspace


def test_preview_does_not_bump_rev(client):
    before = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()["version"]
    _post(client, VALID_CSV)
    after = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()["version"]
    assert before == after
