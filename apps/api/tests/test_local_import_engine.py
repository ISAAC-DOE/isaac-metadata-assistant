"""LOCAL-1: the standalone engine is the SERVER's engine, and it runs without FastAPI.

Pins four things:

1. reading an archive imports neither ``fastapi`` nor ``isaac_api.routes`` (fresh
   subprocess, ``sys.modules``);
2. ``routes`` re-exports the moved field-path derivations as the SAME objects;
3. CLI/server PARITY — the fixture route, the ``staged:`` route and the local-path
   route produce identical ``to_state()`` except the explicitly listed
   source-reference fields, and identical candidates;
4. the schema resolver honours ``ISAAC_SCHEMA_PATH`` and fails closed.

DATA BOUNDARY: committed synthetic fixtures only. The mini corpus's notes file is
processed by code here and never printed or quoted (governance flag, CLAUDE.md §6).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import isaac_api.capabilities as capabilities
import isaac_api.historical_import as hist
import isaac_api.workspace as ws

REPO_ROOT = ws.REPO_ROOT
CORPORA = ("bl15_synthetic_semantics_corpus", "bl15_synthetic_mini_corpus")

#: The ONLY fields allowed to differ between the server's reading of a committed or
#: staged archive and the CLI's reading of the same folder: what the archive is CALLED.
SOURCE_REFERENCE_FIELDS = ("root_label", "archive_name")


def _server_source(name: str, filename: str = "server-label") -> hist.SourceReference:
    return hist.SourceReference(
        source_id="SAME",
        kind=hist.SOURCE_KIND_ARCHIVE,
        filename=filename,
        reference=name,
        parse_state=hist.PARSE_STATE_UNPARSED,
        provenance={},
        fixture_name=name,
    )


def _without_reference_fields(state: dict) -> dict:
    out = {k: v for k, v in state.items() if k not in SOURCE_REFERENCE_FIELDS}
    out["inventory"] = {k: v for k, v in state["inventory"].items() if k != "root_label"}
    return out


def test_reading_an_archive_imports_neither_fastapi_nor_routes():
    code = (
        "import sys, json\n"
        "import isaac_api.historical_import as h\n"
        "src = h.SourceReference(source_id='S', kind='archive', filename='x', reference='r',"
        " parse_state='unparsed', provenance={}, fixture_name='bl15_synthetic_semantics_corpus')\n"
        "r, c = h.read_archive(src)\n"
        "from isaac_api.local_import import bundle, cli\n"
        "print(json.dumps({'units': len(r.units), 'loaded': sorted(m for m in sys.modules"
        " if m.split('.')[0] in ('fastapi', 'starlette', 'pydantic', 'uvicorn')"
        " or m == 'isaac_api.routes')}))\n"
    )
    env = {"PYTHONPATH": f"{REPO_ROOT / 'src'}:{REPO_ROOT / 'apps' / 'api'}", "PATH": "/usr/bin:/bin"}
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd="/", timeout=120
    )
    assert done.returncode == 0, done.stderr
    result = json.loads(done.stdout.strip().splitlines()[-1])
    assert result["units"] == 9
    assert result["loaded"] == [], result["loaded"]


def test_routes_reexports_the_moved_field_paths_as_the_same_objects():
    import isaac_api.field_paths as fp
    import isaac_api.routes as routes

    for name in (
        "EXPERIMENT_OVERRIDABLE_ADDRESSES",
        "NOTE_MAPPABLE_FIELD_PATHS",
        "NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT",
        "PROPOSAL_TARGET_PATHS",
        "RECORD_WRITABLE_BLOCK_ADDRESSES",
        "RECORD_WRITABLE_FIELD_PATHS",
        "RUN_CHOSEN_ENUM_PATH_NAMES",
        "RUN_WRITABLE_FIELD_PATHS",
        "_PROPOSAL_WRITER_SCOPE",
        "_proposal_writer_for",
        "_record_enum_fields",
        "_run_chosen_enum_fields",
    ):
        assert getattr(routes, name) is getattr(fp, name), name
    # and historical_import now asks field_paths, not routes
    assert hist._writable_field_paths() == frozenset(fp.PROPOSAL_TARGET_PATHS)
    assert hist._official_field_paths() == frozenset(fp.NOTE_MAPPABLE_FIELD_PATHS)


@pytest.mark.parametrize("name", CORPORA)
def test_fixture_route_and_local_path_route_read_identically(name):
    server_reading, server_candidates = hist.read_archive(_server_source(name))
    local_reading, local_candidates = hist.read_local_archive(
        hist.archive_root_for(name), source_id="SAME"
    )
    a, b = server_reading.to_state(), local_reading.to_state()
    assert set(a) == set(b)
    differing = sorted(k for k in a if a[k] != b[k])
    assert set(differing) <= {*SOURCE_REFERENCE_FIELDS, "inventory"}, differing
    assert _without_reference_fields(a) == _without_reference_fields(b)
    assert [c.to_state() for c in server_candidates] == [c.to_state() for c in local_candidates]
    assert b["archive_name"].startswith(hist.LOCAL_ARCHIVE_PREFIX)


@pytest.mark.parametrize("name", CORPORA)
def test_staged_route_and_local_path_route_read_identically(name, tmp_path, monkeypatch):
    staging = tmp_path / "staging"
    staging.mkdir()
    shutil.copytree(hist.archive_root_for(name), staging / "copy")
    monkeypatch.setenv(capabilities.INGESTION_ENV, capabilities.INGESTION_MODE_STAGING)
    monkeypatch.setenv(capabilities.STAGING_ROOT_ENV, str(staging))
    staged_reading, staged_candidates = hist.read_archive(_server_source("staged:copy"))
    local_reading, local_candidates = hist.read_local_archive(staging / "copy", source_id="SAME")
    assert _without_reference_fields(staged_reading.to_state()) == _without_reference_fields(
        local_reading.to_state()
    )
    assert [c.to_state() for c in staged_candidates] == [c.to_state() for c in local_candidates]


def test_a_zip_reads_like_its_folder(tmp_path):
    import zipfile

    root = hist.archive_root_for("bl15_synthetic_semantics_corpus")
    archive = tmp_path / "corpus.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=f"corpus/{path.relative_to(root).as_posix()}")
    folder_reading, folder_candidates = hist.read_local_archive(root, source_id="SAME")
    zip_reading, zip_candidates = hist.read_local_archive(archive, source_id="SAME")
    assert [row["archive_path"] for row in folder_reading.manifest] == [
        row["archive_path"] for row in zip_reading.manifest
    ]
    assert [c.to_state() for c in folder_candidates] == [c.to_state() for c in zip_candidates]


def test_the_local_path_is_never_recorded_in_the_reading(tmp_path):
    copy = tmp_path / "private-home" / "beamtime"
    shutil.copytree(hist.archive_root_for("bl15_synthetic_semantics_corpus"), copy)
    reading, candidates = hist.read_local_archive(copy, source_id="SAME")
    text = json.dumps([reading.to_state(), [c.to_state() for c in candidates]])
    assert str(tmp_path) not in text
    assert "private-home" not in text
    assert reading.root_label == "beamtime"


# --- the one schema resolver -------------------------------------------------------


def test_schema_resolver_searches_upward_by_default(monkeypatch):
    from isaac_api import schema_locator

    monkeypatch.delenv(schema_locator.SCHEMA_PATH_ENV, raising=False)
    assert schema_locator.resolve_schema_path() == REPO_ROOT / "schema" / "isaac_record_v1.json"


def test_schema_resolver_honours_the_env_override(tmp_path, monkeypatch):
    from isaac_api import schema_locator

    monkeypatch.setattr(schema_locator, "_LOCAL_CLI_CONTEXT", True)

    copy = tmp_path / "elsewhere.json"
    copy.write_bytes((REPO_ROOT / "schema" / "isaac_record_v1.json").read_bytes())
    monkeypatch.setenv(schema_locator.SCHEMA_PATH_ENV, str(copy))
    assert schema_locator.resolve_schema_path() == copy


def test_schema_resolver_fails_closed_on_a_bad_override(tmp_path, monkeypatch):
    from isaac_api import schema_locator

    monkeypatch.setattr(schema_locator, "_LOCAL_CLI_CONTEXT", True)

    monkeypatch.setenv(schema_locator.SCHEMA_PATH_ENV, str(tmp_path / "missing.json"))
    with pytest.raises(schema_locator.SchemaNotFound) as raised:
        schema_locator.resolve_schema_path()
    assert schema_locator.SCHEMA_PATH_ENV in str(raised.value)
    assert isinstance(raised.value, FileNotFoundError)  # existing OSError handlers still apply


def test_schema_resolver_fails_closed_with_no_schema_above(tmp_path, monkeypatch):
    from isaac_api import schema_locator

    monkeypatch.delenv(schema_locator.SCHEMA_PATH_ENV, raising=False)
    assert schema_locator.find_repo_root(tmp_path) is None
    monkeypatch.setattr(schema_locator, "find_repo_root", lambda start=None: None)
    with pytest.raises(schema_locator.SchemaNotFound):
        schema_locator.resolve_schema_path()


def test_mapping_reads_the_schema_through_the_resolver(tmp_path, monkeypatch):
    """A bad override makes the bl15 enum lookup fail CLOSED (``()``), not crash."""
    from isaac_api import schema_locator
    from isaac_api.bl15 import mapping

    monkeypatch.setattr(schema_locator, "_LOCAL_CLI_CONTEXT", True)
    monkeypatch.setenv(schema_locator.SCHEMA_PATH_ENV, str(tmp_path / "missing.json"))
    mapping._schema.cache_clear()
    mapping.schema_enum.cache_clear()
    try:
        assert mapping.schema_enum("system.technique") == ()
    finally:
        monkeypatch.undo()
        mapping._schema.cache_clear()
        mapping.schema_enum.cache_clear()
    assert "HERFD-XAS" in mapping.schema_enum("system.technique")


def test_the_server_path_ignores_the_schema_override():
    """A fresh process that builds the APP (not the local CLI) with ISAAC_SCHEMA_PATH set to
    a missing file still reads the vendored schema: the override is local-CLI-only."""
    code = (
        "import json; from isaac_api.app import create_app; create_app(); "
        "from isaac_api.bl15 import mapping; from isaac_api import schema_locator; "
        "print(json.dumps([schema_locator.local_cli_override_enabled(), 'HERFD-XAS' in mapping.schema_enum('system.technique')]))"
    )
    env = {"PYTHONPATH": f"{REPO_ROOT / 'src'}:{REPO_ROOT / 'apps' / 'api'}", "PATH": "/usr/bin:/bin",
           "ISAAC_SCHEMA_PATH": "/nonexistent/schema.json", "ISAAC_UI_WORKSPACE": "/tmp/isaac-schema-probe-ws"}
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd="/", timeout=120)
    assert done.returncode == 0, done.stderr[-1500:]
    assert json.loads(done.stdout.strip().splitlines()[-1]) == [False, True]


def test_the_hosted_staged_route_keeps_same_named_acquisitions_in_different_folders_apart(tmp_path, monkeypatch):
    """DEC §B9 / R1, on the SERVER's route: two acquisition files with one name and
    different bytes, in different folders, are two units — each with its own path and its
    own sha256-keyed identity. Before the fix both carried the second file's path."""
    import hashlib

    root = hist.archive_root_for("bl15_synthetic_semantics_corpus")
    template = (root / "05_02_ZZ2_base_after400Cycling_filter20_800mV").read_text(encoding="utf-8")
    staging = tmp_path / "staging"
    corpus = staging / "dup"
    bodies = {}
    for i, folder in enumerate(("first", "second")):
        (corpus / folder).mkdir(parents=True)
        body = template.replace("#F 05_02_ZZ2_base_after400Cycling_filter20_800mV", "#F same_name") + f"\n# synthetic note {i}\n"
        (corpus / folder / "same_name.dat").write_text(body, encoding="utf-8")
        bodies[f"{folder}/same_name.dat"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    monkeypatch.setenv(capabilities.INGESTION_ENV, capabilities.INGESTION_MODE_STAGING)
    monkeypatch.setenv(capabilities.STAGING_ROOT_ENV, str(staging))
    reading, _ = hist.read_archive(_server_source("staged:dup"))
    units = {u.acquisition_path: u for u in reading.units}
    assert set(units) == set(bodies)
    for path, digest in bodies.items():
        assert units[path].acquisition_identity.endswith(digest), path
