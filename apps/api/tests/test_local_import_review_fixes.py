"""LOCAL-1 independent-review findings (L1-L5 + minors) and real-data finding R2,
each pinned by a defect-shaped test. Synthetic fixtures only."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import isaac_api.historical_import as hist
import isaac_api.workspace as ws
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli

REPO_ROOT = ws.REPO_ROOT
SEMANTICS = REPO_ROOT / "tests/fixtures/bl15/semantics/multi_operator_corpus"
NOW = "2026-10-28T00:00:00Z"


def _build(root: Path):
    ev: dict = {}
    reading, candidates = hist.read_local_archive(root, source_id="S", evidence_sink=ev)
    return B.build_bundle(reading, candidates, evidence_by_source=ev, source_kind="folder", created_utc=NOW)


@pytest.fixture(scope="module")
def bundle():
    return _build(SEMANTICS)


@pytest.fixture()
def b(bundle):
    return copy.deepcopy(bundle)


# --- L1: reading.full.json leaked what bundle.json withholds -------------------------------------


def test_no_output_file_carries_a_refused_member_name(tmp_path, capsys):
    archive = tmp_path / "crafted.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("corpus/readme.txt", "SYNTHETIC readme")
        zf.writestr("corpus/../../escape.txt", "x")
        zf.writestr("/abs/very_SECRETNAME.txt", "x")
        zf.writestr("..\\..\\win.txt", "x")
    out = tmp_path / "out"
    assert cli.main(["import", str(archive), "--out", str(out)]) == 0
    for path in out.iterdir():
        text = path.read_text(encoding="utf-8")
        for needle in ("escape.txt", "SECRETNAME", "win.txt"):
            assert needle not in text, (path.name, needle)
    full = json.loads((out / "reading.full.json").read_text())
    assert "strings_truncated" in full
    assert all(r["archive_path"] is None or ".." not in r["archive_path"] for r in full["reading"]["inventory"]["refused"])


def test_reading_full_is_bounded(monkeypatch, tmp_path):
    monkeypatch.setattr(B, "MAX_BUNDLE_BYTES", 10_000)
    with pytest.raises(B.BundleBoundsExceeded):
        reading, candidates = hist.read_local_archive(SEMANTICS, source_id="S")
        B.full_reading(reading, candidates)


# --- L2: tampering the validator used to accept -----------------------------------------------------


def _conflicting(b):
    return next(c for c in b["candidates"] if c["extracted_state"] == "conflicting" and c["kind"] == "field")


def test_T1_a_conflict_rewritten_as_extracted_with_an_invented_value_is_refused(b):
    c = _conflicting(b)
    c["extracted_state"] = "candidate_extracted"
    c["value"] = "2100-01-01T00:00:00Z"
    B.apply_derivations(b)  # even with every derived field made consistent
    assert any(c["candidate_id"] in e for e in B.validate_bundle(b))


def test_T1b_clearing_the_disagreement_too_is_still_refused(b):
    c = _conflicting(b)
    c["state_basis"]["unresolved_reason"] = None
    c["state_basis"]["review_status"] = "needs_review"
    c["extracted_state"] = "needs_review"
    c["value"] = "2100-01-01T00:00:00Z"
    B.apply_derivations(b)
    errors = B.validate_bundle(b)
    assert any("disagreeing witnesses" in e or "no witness states" in e for e in errors), errors


def test_an_invented_value_on_an_agreeing_candidate_is_refused(b):
    c = next(c for c in b["candidates"] if c["value"] is not None and c["extracted_state"] == "candidate_extracted")
    c["value"] = "not what any file says"
    assert any("no witness states" in e for e in B.validate_bundle(b))


def test_T4_zeroed_counts_and_blocking_are_refused(b):
    b["counts"] = {k: 0 for k in b["counts"]}
    b["readiness"]["blocking"] = {"conflicts": 0, "needs_review": 0, "missing": 0, "unread_files": 0}
    errors = B.validate_bundle(b)
    assert any("counts." in e for e in errors) and any("readiness.blocking" in e for e in errors)


def test_T5_deleting_every_conflict_is_refused(b):
    b["conflicts"] = []
    for r in b["runs"]:
        r["conflict_ids"] = []
    b["questions"] = [q for q in b["questions"] if q["target"]["kind"] != "conflict"]
    B.apply_derivations(b)
    assert any("no conflicts[] entry" in e for e in B.validate_bundle(b))


# --- L3: one index space, a visible cap, and field checks before eligibility -----------------------


def test_choose_reading_indexes_the_raw_readings_duplicates_kept():
    decision = {"decision": "choose_reading", "chosen_reading_index": 2}
    assert B.final_value(None, decision, ["A", "B", "B", "C"]) == "B"


def test_conflict_options_and_candidate_readings_share_one_index_space(b):
    for conflict in b["conflicts"]:
        if not conflict["candidate_id"]:
            continue
        cand = next(c for c in b["candidates"] if c["candidate_id"] == conflict["candidate_id"])
        assert [r["value"] for r in conflict["readings"]] == cand["readings"]


def test_the_observed_literals_cap_is_stated(b):
    for c in b["candidates"]:
        assert c["observed_literals_truncated"] == (c["observed_literals_total"] > len(c["observed_literals"]))
        assert len(c["observed_literals"]) <= B.MAX_OBSERVED_LITERALS


@pytest.mark.parametrize(
    "path, value, ok",
    [
        ("timestamps.acquired_start_utc", "Fri Jan 01 00:00:00 2100", False),  # T2: a zoneless local time
        ("timestamps.acquired_start_utc", "2100-01-01T00:10:00+00:00", True),
        ("context.environment", "outdoors", False),  # not in the schema's enum
        ("context.environment", "ex_situ", True),
        ("context.temperature_K", "hot", False),  # wrong type
        ("context.temperature_K", 298.0, True),
    ],
)
def test_a_confirmed_value_must_fit_its_field_before_it_is_eligible(path, value, ok):
    got = B.eligibility_for_official_record("scientist_confirmed", target_field_path=path, value=value, writable_paths=B._writable_paths())
    assert got["eligible"] is ok, got


# --- L4: a standing-rule resolution is carried, and is a conflict entry ----------------------------------


@pytest.fixture(scope="module")
def resolved_bundle(tmp_path_factory):
    root = tmp_path_factory.mktemp("res") / "corpus"
    shutil.copytree(SEMANTICS, root)
    mac = root / "run01.mac"
    mac.write_text(mac.read_text().replace(
        "newfile 04_02_ZZ2_base_after500Cycling_filter20_800mV\n",
        "newfile 04_02_ZZ2_base_after500Cycling_filter20_800mV\nmv Sx 13.0\n",
    ))
    acq = root / "04_02_ZZ2_base_after500Cycling_filter20_800mV"
    acq.write_text(acq.read_text().replace("#O0     synmono   synemiss", "#O0     synmono   synemiss   Sx")
                   .replace("#P0 1000.0 900.0", "#P0 1000.0 900.0 12.5"))
    return _build(root)


def test_a_standing_resolution_is_carried_and_has_a_conflict_entry(resolved_bundle):
    b = resolved_bundle
    cand = next(c for c in b["candidates"] if c["state_basis"]["review_status"] == "resolved")
    assert cand["standing_resolution"]["rule_id"] == "bl15.resolution.recorded_motor_position.v1"
    assert cand["standing_resolution"]["statement"] and cand["standing_resolution"]["attribution"]
    used = {r["value"] for r in cand["standing_resolution"]["reading_used"]}
    relations = {e["literal_value"]: e["relation"] for e in cand["evidence"]}
    assert any(rel == "supports" for rel in relations.values())
    conflict = next(c for c in b["conflicts"] if c["candidate_id"] == cand["candidate_id"])
    assert conflict["resolution"]["standing_resolution"]["rule_id"] == cand["standing_resolution"]["rule_id"]
    assert conflict["value_state"] == "needs_review"  # a stored rule, not a scientist
    assert sorted(cand["readings"]) == ["Sx 12.5", "Sx 13.0"] and used == {"Sx 12.5"}
    assert B.validate_bundle(b) == []


# --- L5: parity pinned against main, not true by construction ---------------------------------------------

#: Produced on `main` @ 69982fb9 by the independent reviewer's script
#: (scratchpad review/scripts/parity.py): for each committed archive, read it through
#: the SERVER route (`read_archive`, SourceReference(source_id='S', filename='lbl',
#: fixture_name=<key>)) and hash
#: `json.dumps([reading.to_state(), [c.to_state() for c in candidates]], sort_keys=True,
#: default=str)` with sha256. Branch HEAD reproduces both digests exactly.
GOLDEN = {
    "bl15_synthetic_mini_corpus": ("6ec55ca84db75f43661f4daa247dfb9af7a5777f858795ac92d912dd81bae770", 5, 100),
    "bl15_synthetic_semantics_corpus": ("acf0ba4acf87f144a66a6c817d796e935226610aab1c3b260a2ff2dd021a6fa2", 9, 200),
}


def _digest(reading, candidates) -> str:
    blob = json.dumps([reading.to_state(), [c.to_state() for c in candidates]], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_the_server_route_reads_exactly_what_main_read(name):
    digest, units, cands = GOLDEN[name]
    src = hist.SourceReference(source_id="S", kind=hist.SOURCE_KIND_ARCHIVE, filename="lbl", reference=name,
                               parse_state=hist.PARSE_STATE_UNPARSED, provenance={}, fixture_name=name)
    reading, candidates = hist.read_archive(src)
    assert (len(reading.units), len(candidates)) == (units, cands)
    assert _digest(reading, candidates) == digest


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_the_local_route_reads_exactly_what_main_read_modulo_its_name(name):
    import dataclasses

    digest, _, _ = GOLDEN[name]
    reading, candidates = hist.read_local_archive(hist.archive_root_for(name), source_id="S")
    renamed = dataclasses.replace(
        reading, root_label="lbl", archive_name=name, inventory={**reading.inventory, "root_label": "lbl"}
    )
    assert _digest(renamed, candidates) == digest


# --- minors -------------------------------------------------------------------------------------------------


def test_a_non_path_locator_is_typed_not_a_relative_path(b):
    paths = {s["relative_path"] for s in b["sources"]}
    for c in b["candidates"]:
        for e in c["evidence"]:
            if e["relative_path"] is not None:
                assert e["relative_path"] in paths and e["locator_kind"] == "source_file"
            elif e.get("locator_kind") == "described":
                assert e["source_id"] is None and e["locator"]


def test_bundle_files_are_world_readable_not_0600(tmp_path):
    out = tmp_path / "out"
    assert cli.main(["import", str(SEMANTICS), "--out", str(out)]) == 0
    for path in out.iterdir():
        if path.is_file() and not path.name.startswith("."):
            assert stat.S_IMODE(path.stat().st_mode) == 0o644, path.name


def test_force_stages_every_file_before_touching_out(tmp_path, monkeypatch):
    out = tmp_path / "out"
    assert cli.main(["import", str(SEMANTICS), "--out", str(out)]) == 0
    before = {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()}
    calls = {"n": 0}
    real = cli._atomic_write

    def flaky(path, data):
        calls["n"] += 1
        if calls["n"] == 5:
            raise OSError("synthetic disk full")
        return real(path, data)

    monkeypatch.setattr(cli, "_atomic_write", flaky)
    with pytest.raises(OSError):
        cli.main(["import", str(SEMANTICS), "--out", str(out), "--force"])
    assert {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()} == before
    assert not list(tmp_path.glob(".isaac-bundle-*"))


def test_the_install_script_says_what_it_may_download():
    text = (REPO_ROOT / "scripts" / "install_local_cli.sh").read_text()
    assert "DOWNLOADS a Python build" in text
    assert "download anything other than" not in text


def test_the_contract_doc_versioning_matches_the_schema():
    doc = (REPO_ROOT / "docs" / "local-import-bundle-contract.md").read_text()
    assert B.bundle_schema()["additionalProperties"] is False
    assert "A v1.0 reader must still validate it" not in doc
    assert "additionalProperties: false" in doc


# --- R2: the one process the local CLI starts lives outside the API package ------------------------------


def test_the_server_never_loads_the_portal_runner():
    code = (
        "import sys; from isaac_api.app import create_app; create_app(); "
        "import isaac_api.local_import.portal, isaac_api.local_import.records; "
        "print('isaac_portal_runner' in sys.modules)"
    )
    env = {"PYTHONPATH": f"{REPO_ROOT / 'src'}:{REPO_ROOT / 'apps' / 'api'}", "PATH": "/usr/bin:/bin",
           "ISAAC_UI_WORKSPACE": "/tmp/isaac-r2-probe-ws"}
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd="/", timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip().splitlines()[-1] == "False"


def test_only_the_portal_module_imports_the_runner():
    importers = []
    for path in sorted((REPO_ROOT / "apps" / "api" / "isaac_api").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, (ast.Import, ast.ImportFrom)) else []
            if "isaac_portal_runner" in names or (isinstance(node, ast.ImportFrom) and node.module == "isaac_portal_runner"):
                importers.append(path.relative_to(REPO_ROOT).as_posix())
    assert importers == ["apps/api/isaac_api/local_import/portal.py"]


def test_the_runner_starts_a_fixed_argv_list_with_no_shell():
    import isaac_portal_runner as runner

    tree = ast.parse(Path(runner.__file__).read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", None) in {"run", "Popen", "call", "check_output", "system"}]
    assert len(calls) == 1
    call = calls[0]
    assert isinstance(call.args[0], ast.List)
    assert [ast.unparse(e) for e in call.args[0].elts] == ["exe", "'-I'", "'-c'", "RUNNER"]
    kw = {k.arg: ast.unparse(k.value) for k in call.keywords}
    assert kw["shell"] == "False" and kw["timeout"] == "TIMEOUT_S" and kw["env"] == "env"


def test_the_runner_refuses_an_unacceptable_interpreter(tmp_path):
    import isaac_portal_runner as runner

    portal = tmp_path / "portal"
    portal.mkdir()
    (portal / "validation.py").write_text("")
    with pytest.raises(runner.RunnerRefused):
        runner.run("python3", str(portal), "{}", must_be_within=None)  # relative
    not_exec = tmp_path / "py"
    not_exec.write_text("")
    with pytest.raises(runner.RunnerRefused):
        runner.run(str(not_exec), str(portal), "{}", must_be_within=None)
    with pytest.raises(runner.RunnerRefused):
        runner.run(sys.executable, str(portal), "{}", must_be_within=tmp_path / "cache")  # outside the cache
