"""WHAT AN IMPORT READ MUST OUTLIVE THE IMPORT — and three batch defects beside it.

Measured 2026-10-12 on the committed multi-operator corpus, before any change here:

* **Most of what Historical Import reads never reached the record.** After Add to
  Experiment with one run per measurement, every run's fields were ``{}`` and the
  record's extended context held identifiers only. The cycling state, before/after
  state, potential, filter, medium, sample token and number, counting time, emission
  energy, energy grid, detector columns, scan command, element and edge, calibration,
  spectrometer configuration, the operator the notes name and the HERFD channel
  suggestion existed ONLY in the import session, which is not durable and is gone on
  Discard or restart. ``DEC-41`` forbids the obvious fix — those concepts have a home at
  levels 1-3, so ``check_placement`` raises on putting them in the level-4 companion —
  so each measurement now gets ONE note, "Also read from the archive", on its run.
* **With ``create_runs: true`` and nothing sendable, the batch refused whole**
  (``422 nothing_to_send``), so a scientist whose every value needs a decision could not
  get the measurements onto a record at all.
* **The extended-context companion doubled on a re-import from a ZIP nested
  ``outer/inner/``** (127 -> 254), because its entry ids named the member's path.

DATA BOUNDARY: none. The only archives read are the committed synthetic corpora and
copies of them made inside ``tmp_path``; no database connection is opened.
"""

from __future__ import annotations

import dataclasses
import shutil
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import isaac_api.capabilities as capabilities
import isaac_api.extended_context as xc
import isaac_api.historical_import as hist
import isaac_api.identity as identity
import isaac_api.workspace as ws
from isaac_api.bl15 import mapping as mp

REPO_ROOT = Path(__file__).resolve().parents[3]
SEMANTICS = "tests/fixtures/bl15/semantics/multi_operator_corpus"
ARCHIVE = "bl15_synthetic_semantics_corpus"
UNIT_01 = "01_01_ZZ1_acid_after500Cycling_filter10_100mV"
TITLE = hist.READINGS_NOTE_TITLE
BEAMTIME_TITLE = f"{TITLE} — the whole beamtime"


# --- fixtures and helpers -------------------------------------------------------


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv(identity.EDGE_TRUST_VERIFIER_ENV, raising=False)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, raising=False)
    monkeypatch.delenv(capabilities.INGESTION_ENV, raising=False)
    monkeypatch.delenv(capabilities.STAGING_ROOT_ENV, raising=False)
    # Registered in `ARCHIVE_FIXTURES` since 2026-10-12; set here too so this file's
    # assertions are about the batch, not about the registration (which
    # `test_hosted_image_imports.py` pins), on a tree that predates it.
    monkeypatch.setitem(hist.ARCHIVE_FIXTURES, ARCHIVE, SEMANTICS)
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _zip_folder(folder: Path, target: Path, prefix: str) -> None:
    with zipfile.ZipFile(target, "w") as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                zf.write(path, prefix + str(path.relative_to(folder)))


@pytest.fixture()
def staging(client, tmp_path, monkeypatch):
    """A staging root holding the semantics corpus as a folder and as a ZIP nested
    ``outer/inner/`` — the layout an independent review measured doubling things."""
    root = tmp_path / "staging"
    root.mkdir()
    folder = root / "synthetic_corpus"
    shutil.copytree(REPO_ROOT / SEMANTICS, folder)
    _zip_folder(folder, root / "nested.zip", "outer/inner/")
    monkeypatch.setenv(capabilities.INGESTION_ENV, capabilities.INGESTION_MODE_STAGING)
    monkeypatch.setenv(capabilities.STAGING_ROOT_ENV, str(root))
    return root


def _import(client, archive: str = ARCHIVE) -> str:
    created = client.post("/api/imports", json={"label": "synthetic readings"})
    assert created.status_code == 200, created.text
    import_id = created.json()["import"]["import_id"]
    added = client.post(
        f"/api/imports/{import_id}/sources", json={"kind": "archive", "fixture_name": archive}
    )
    assert added.status_code == 200, added.text
    assert client.post(f"/api/imports/{import_id}/parse").status_code == 200
    assert client.post(f"/api/imports/{import_id}/reconstruct").status_code == 200
    return import_id


def _record(client, title="readings record") -> str:
    response = client.post("/api/experiments", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _etag(client, eid: str) -> str:
    return client.get(f"/api/experiments/{eid}").headers["ETag"]


def _add(client, import_id: str, eid: str, **body):
    return client.post(
        f"/api/imports/{import_id}/add-to-experiment",
        json={"experiment_id": eid, **body},
        headers={"If-Match": _etag(client, eid)},
    )


def _readings_notes(eid: str) -> list:
    return [n for n in ws.load_experiment(eid).notes if n.text.startswith(TITLE)]


def _run_of(eid: str, stem: str) -> str:
    exp = ws.load_experiment(eid)
    for run_id, origin in exp.historical_run_origins.items():
        if origin.get("stem") == stem:
            return run_id
    raise AssertionError(f"no run made from {stem}")


# --- item 2: the note exists, says what was read, and is only a note ----------------


def test_every_created_run_carries_one_note_of_what_was_read_and_not_sent(client):
    eid = _record(client)
    body = _add(client, _import(client), eid, create_runs=True)
    assert body.status_code == 200, body.text
    report = body.json()["readings_notes"]
    assert report == {
        "label": TITLE,
        "measurements": 9,
        "captured_as_run_notes": 9,
        "already_present": 0,
        "beamtime_notes_captured": 2,
        "beamtime_notes_already_present": 0,
        "not_listed": 0,
        "writes_field_values": False,
    }
    exp = ws.load_experiment(eid)
    per_run = [n for n in _readings_notes(eid) if n.run_id is not None]
    assert sorted(n.run_id for n in per_run) == sorted(r.id for r in exp.runs)
    note = next(n for n in per_run if n.run_id == _run_of(eid, UNIT_01))
    assert f"Measurement: {UNIT_01}" in note.text
    # PER CONCEPT: the plain label, the value EXACTLY as written, and the file + place.
    for line in (
        f"- Sample name: ZZ1 — {UNIT_01} · filename token 2 [chars 6..9]",
        f"- Sample or electrode number: 01 — {UNIT_01} · filename token 1",
        f"- Electrolyte or medium: acid — {UNIT_01} · filename token 3",
        f"- Cycling state: after500Cycling — {UNIT_01} · filename token 4",
        f"- Before / after state: after500Cycling — {UNIT_01} · filename token 4",
        f"- Potential: 100mV — {UNIT_01} · filename token 6",
        f"- Filter: filter10 — {UNIT_01} · filename token 5",
        f"- Filter: 10 — {UNIT_01}_dir/{UNIT_01}_001.dat · line 4 header #P0 key `filter`",
        f"- Scan command: gscan 1000 1100 5 0.5 — {UNIT_01} · line 7 header #S (scan 1)",
        f"- Energy grid: 1100 5 — {UNIT_01} · line 7 header #S (scan 1) gscan grid literal",
        f"- Counting time: 0.5  (Seconds) — {UNIT_01} · line 9 header #T (scan 1)",
        f"- Emission energy: 900.0 — {UNIT_01}_dir/{UNIT_01}_001.dat · line 4 header #P0 key `emiss`",
        f"- Detector column: vortDT — {UNIT_01} · line 12 header #L column 2 (scan 1)",
        f"- Detector column: vortDT4 — {UNIT_01} · line 12 header #L column 5 (scan 1)",
        "- Operator named in the notes: Operator Alpha (synthetic) — 2099 SYNTHETIC semantics notes.txt · line 13",
    ):
        assert line in note.text, line
    # I1 (review, 2026-10-12): EVERY LINE IS A READING. The HERFD selector's suggestion
    # and its element/edge-on-channel assignment are the build's CONCLUSIONS, so they are
    # not listed — the note is sourced `historical_source_line`, and "Propose a Value
    # From This Note" would cite it as a parsed file reading.
    for conclusion in ("HERFD", "suggested by this build", " on vortDT", "none suggested", "herfd_primary_signal_selector"):
        assert conclusion not in note.text, conclusion
    # THE LEAD SAYS WHAT IS TRUE: the operator line is read from the beamtime NOTES file,
    # not from this measurement's own files; and a value is used by PROPOSING it — note
    # review's map takes one field for the whole note, so "map a line" was false (I2).
    assert "read about this measurement" in note.text
    assert "this measurement's own files" not in note.text
    assert "Propose a Value From This Note" in note.text
    assert "map it to a field in note review" not in note.text
    # Each run's note is ITS measurement's, never another's.
    other = next(n for n in per_run if n.run_id == _run_of(eid, "06_03_ZZ3_alk_fresh_f30_900mV"))
    assert UNIT_01 not in other.text
    assert "Operator Gamma (synthetic)" in other.text or "Operator Alpha (synthetic)" in other.text


def test_the_note_leaves_out_what_was_sent_and_what_the_companion_carries(client):
    eid = _record(client)
    body = _add(client, _import(client), eid, create_runs=True).json()
    sent_epoch = next(row for row in body["sent"] if row["candidate_id"] == f"{UNIT_01}::acquisition_epoch")
    assert sent_epoch["already_sent"] is False
    note = next(n for n in _readings_notes(eid) if n.run_id == _run_of(eid, UNIT_01))
    # SENT AS A PROPOSAL -> not repeated as a note (its own proposal note cites it).
    assert "4102445400" not in note.text
    assert "Acquisition time (epoch)" not in note.text
    # CARRIED BY THE COMPANION (level 4) -> not repeated: the `#F` declaration, the
    # legacy number, the scan-index tokens, the macro's declared targets.
    assert "beforeCycling" not in note.text
    assert "Legacy run or file number" not in note.text
    assert "Unknown token" not in note.text
    assert "Acquisition target" not in note.text
    # NEVER THE BEAMLINE ACCOUNT STRING (`spec_user_string`, the registry's "actively
    # harmful to fix").
    assert "header #C" not in note.text
    assert "NOT INSTRUMENT OUTPUT. Every value is invented." not in note.text
    # …while the companion still holds what the note leaves out.
    concepts = {e.concept for e in ws.load_experiment(eid).extended_context.entries}
    assert {"spec_file_declaration", "spec_user_string", "unknown_token"} <= concepts


def test_the_account_string_is_excluded_by_name_and_not_only_by_the_companion(client, monkeypatch):
    """MUTATION-GUARDED: if the companion stopped carrying ``spec_user_string`` (here, by
    pretending it carries nothing), the note must still not list it — the registry calls
    it harmful to carry anywhere a note review could map it to an attribution field."""
    reason = mp.mapping_for("spec_user_string").reason
    assert "ACTIVELY HARMFUL" in reason, "the exclusion's premise moved in the registry"
    assert "spec_user_string" in hist.READINGS_NOTE_EXCLUDED_CONCEPTS
    monkeypatch.setattr(hist, "_companion_carries", lambda concept: False)
    eid = _record(client)
    assert _add(client, _import(client), eid, create_runs=True).status_code == 200
    note = next(n for n in _readings_notes(eid) if n.run_id == _run_of(eid, UNIT_01))
    assert "Legacy run or file number" in note.text, "the monkeypatch took effect"
    assert "NOT INSTRUMENT OUTPUT. Every value is invented." not in note.text


def test_the_note_is_a_note_and_never_a_field_value(client):
    eid = _record(client)
    assert _add(client, _import(client), eid, create_runs=True).status_code == 200
    exp = ws.load_experiment(eid)
    assert len(_readings_notes(eid)) == 11, "nine run notes and two beamtime notes"
    for note in _readings_notes(eid):
        assert note.source == "historical_source_line"
        assert note.candidate_field_path is None
        assert note.verified is False and note.is_field_value is False
    import json

    for run in exp.runs:
        drafted = json.dumps(run.draft)
        for literal in ("after500Cycling", "filter10", "gscan", "Operator Alpha", "vortDT", "synslit"):
            assert literal not in drafted, (run.label, literal)


def test_the_beamtime_readings_are_record_notes_one_per_file_and_not_copied_onto_runs(client):
    eid = _record(client)
    assert _add(client, _import(client), eid, create_runs=True).status_code == 200
    notes = _readings_notes(eid)
    record_level = {n.text.split("\n", 1)[0]: n.text for n in notes if n.run_id is None}
    assert sorted(record_level) == [
        f"{BEAMTIME_TITLE}, from Zz_XAS.mac",
        f"{BEAMTIME_TITLE}, from readme.txt",
    ]
    readme = record_level[f"{BEAMTIME_TITLE}, from readme.txt"]
    assert "Propose a Value From This Note" in readme
    assert "map it to a field in note review" not in readme
    for line in (
        "- Monochromator calibration: Monochromator: calib with Synthetic Foil, #1, 1000.0 — readme.txt · lines 9..9",
        "- Spectrometer configuration: Spectrometer:\n  \t1.0mm synslit — readme.txt · lines 6..7",
        "- Element: Zz — readme.txt · line 4",
    ):
        assert line in readme, line
    assert "- Acquisition method: ZzL3_xas — Zz_XAS.mac · line 3 `def`" in record_level[
        f"{BEAMTIME_TITLE}, from Zz_XAS.mac"
    ]
    # A BEAMTIME STATEMENT IS NEVER COPIED ONTO A RUN as though that run's files said it.
    for note in notes:
        if note.run_id is not None:
            assert "Synthetic Foil" not in note.text
            assert "— readme.txt ·" not in note.text
            # (The macro's NAME may appear — `run01.mac` says which method macro acquired
            # this measurement, which IS a per-measurement reading — but never a statement
            # read OUT OF the method macro, which is the beamtime's.)
            assert "— Zz_XAS.mac ·" not in note.text


# --- item 2: exactly once, keyed on content ---------------------------------------


def test_the_notes_are_exactly_once_across_reruns_sessions_and_containers(client, staging):
    eid = _record(client)
    import_id = _import(client)
    first = _add(client, import_id, eid, create_runs=True).json()["readings_notes"]
    assert (first["captured_as_run_notes"], first["beamtime_notes_captured"]) == (9, 2)
    expected_again = {
        **first,
        "captured_as_run_notes": 0,
        "already_present": 9,
        "beamtime_notes_captured": 0,
        "beamtime_notes_already_present": 2,
    }
    rev = ws.load_experiment(eid).rev
    for label, again in (
        ("the same session, again", lambda: import_id),
        ("another session", lambda: _import(client)),
        ("the same files staged as a folder", lambda: _import(client, "staged:synthetic_corpus")),
    ):
        response = _add(client, again(), eid, create_runs=True)
        assert response.status_code == 200, (label, response.text)
        assert response.json()["readings_notes"] == expected_again, label
    # A ZIP NESTED `outer/inner/`: its README sits one folder down, where the shared-README
    # reader does not look, so that layout states no element, calibration or spectrometer
    # at all. Every run's note and the macro's note are the SAME notes; the README's is
    # simply not produced — and nothing is added.
    nested = _add(client, _import(client, "staged:nested.zip"), eid, create_runs=True)
    assert nested.status_code == 200, nested.text
    assert nested.json()["readings_notes"] == {
        **expected_again,
        "beamtime_notes_already_present": 1,
    }
    assert len(_readings_notes(eid)) == 11
    assert ws.load_experiment(eid).rev == rev, "a batch that added nothing moved the revision"


def test_a_batch_whose_only_new_content_is_the_notes_still_saves_them(client):
    """M2 (review): runs made BEFORE this change hold no "Also read from the archive"
    note. Re-running the batch then creates nothing else — every run, proposal, remark
    and companion entry is already there — so the notes are its ONLY new content, and
    a save gated on the other kinds of change would report them and keep none."""
    import_id = _import(client)
    eid = _record(client)
    assert _add(client, import_id, eid, create_runs=True).status_code == 200
    with ws.record_lock(eid):
        exp = ws.load_experiment(eid)
        kept = [n for n in exp.notes if not n.text.startswith(TITLE)]
        assert len(kept) < len(exp.notes)
        exp.notes[:] = kept  # the record as a build before this change left it
        exp.save_versioned()
    rev = ws.load_experiment(eid).rev
    again = _add(client, import_id, eid, create_runs=True)
    assert again.status_code == 200, again.text
    body = again.json()
    assert body["counts"]["sent"] == 0 and body["counts"]["runs_created"] == 0
    assert body["data_quality_notes"]["captured_as_run_notes"] == 0
    assert body["extended_context"]["added"] == 0
    assert body["readings_notes"]["captured_as_run_notes"] == 9
    assert body["readings_notes"]["beamtime_notes_captured"] == 2
    # …and they are ON DISK, at one new revision, not only in the response.
    reloaded = ws.load_experiment(eid)
    assert len([n for n in reloaded.notes if n.text.startswith(TITLE)]) == 11
    assert reloaded.rev == rev + 1


def test_readings_that_changed_add_a_second_note_and_leave_the_first(client, staging):
    """THE STATED RULE: different readings are a different note; the earlier one stays."""
    eid = _record(client)
    first = _add(client, _import(client, "staged:synthetic_corpus"), eid, create_runs=True)
    assert first.status_code == 200, first.text
    before = {n.id: n.text for n in _readings_notes(eid)}
    # A CORRECTED SCAN EXPORT: unit 01's first export now states another emission energy.
    # The acquisition file is untouched, so the measurement — and its run — are the same.
    changed = staging / "corrected"
    shutil.copytree(staging / "synthetic_corpus", changed)
    export = changed / f"{UNIT_01}_dir" / f"{UNIT_01}_001.dat"
    text = export.read_text()
    assert "900.0" in text
    export.write_text(text.replace("900.0", "901.5", 1))
    second = _add(client, _import(client, "staged:corrected"), eid, create_runs=True)
    assert second.status_code == 200, second.text
    report = second.json()["readings_notes"]
    assert second.json()["counts"]["runs_created"] == 0
    assert (report["captured_as_run_notes"], report["already_present"]) == (1, 8)
    after = _readings_notes(eid)
    assert {n.id: n.text for n in after if n.id in before} == before, "an earlier note changed"
    fresh = [n for n in after if n.id not in before]
    assert len(fresh) == 1 and fresh[0].run_id == _run_of(eid, UNIT_01)
    assert "901.5" in fresh[0].text


def test_without_create_runs_the_note_follows_the_measurements_own_run(client):
    eid = _record(client)
    assert _add(client, _import(client), eid, create_runs=True).status_code == 200
    again = _add(client, _import(client), eid)  # every measurement already owns a run here
    assert again.status_code == 200, again.text
    report = again.json()["readings_notes"]
    assert (report["measurements"], report["already_present"], report["captured_as_run_notes"]) == (9, 9, 0)


# --- item 2: bounded, and says what it left out --------------------------------


def _row(concept, value, where="f.txt · line 1"):
    return {"concept": concept, "value": value, "where": where, "basis": [concept, value, where]}


def test_one_concept_cannot_crowd_out_the_rest_and_the_rest_is_counted():
    rows = [_row("motor_position", str(i), f"a · motor {i}") for i in range(180)]
    rows.append(_row("filter", "filter10"))
    note = hist._readings_note("", "lead", rows)
    text = note["text"]
    assert "- Filter: filter10" in text
    assert text.count("- Motor position:") == hist.READINGS_NOTE_MAX_PER_CONCEPT
    assert note["not_listed"] == 180 - hist.READINGS_NOTE_MAX_PER_CONCEPT
    assert f"{note['not_listed']} more readings are not listed here" in text


def test_the_note_is_bounded_in_lines_and_in_characters():
    many = [_row(f"concept_{i:03d}", f"v{i}") for i in range(200)]
    note = hist._readings_note("", "lead", many)
    assert note["listed"] == hist.READINGS_NOTE_MAX_ROWS
    assert note["not_listed"] == 200 - hist.READINGS_NOTE_MAX_ROWS
    long_rows = [_row(f"concept_{i:03d}", "x" * 900) for i in range(50)]
    long_note = hist._readings_note("", "lead", long_rows)
    assert len(long_note["text"]) <= hist.READINGS_NOTE_MAX_CHARS
    assert long_note["listed"] + long_note["not_listed"] == 50
    assert long_note["not_listed"] > 0
    assert f"{long_note['not_listed']} more readings are not listed here" in long_note["text"]


def test_a_reading_past_the_cap_still_changes_the_notes_identity():
    """The digest covers every row, listed or not — so a changed reading the note could
    not show is still a different note, never a silently stale one."""
    rows = [_row("motor_position", str(i), f"a · motor {i}") for i in range(20)]
    changed = rows[:-1] + [_row("motor_position", "changed", "a · motor 19")]
    one, two = hist._readings_note("", "l", rows), hist._readings_note("", "l", changed)
    assert one["text"] == two["text"], "the change is past the cap, so the text is equal"
    assert one["identity"] != two["identity"]


# --- item 3: creating the runs is itself the act -------------------------------


@pytest.fixture()
def nothing_sendable(client, tmp_path, monkeypatch):
    """The semantics corpus with every `#E` epoch line removed, so no value it reads is
    sendable (each time is the instrument's zoneless clock) — measured: `sendable == []`
    with 9 run-candidate measurements."""
    copy = tmp_path / "no_epochs"
    shutil.copytree(REPO_ROOT / SEMANTICS, copy)
    for path in copy.rglob("*"):
        if path.is_file():
            text = path.read_text(errors="replace")
            if any(line.startswith("#E") for line in text.splitlines()):
                path.write_text(
                    "\n".join(l for l in text.splitlines() if not l.startswith("#E")) + "\n"
                )
    monkeypatch.setitem(hist.ARCHIVE_FIXTURES, "no_epochs", str(copy))
    return "no_epochs"


def test_create_runs_with_nothing_sendable_creates_the_runs_and_says_so(client, nothing_sendable):
    import_id = _import(client, nothing_sendable)
    assert hist.batch_partition(hist.load_session(import_id))[0] == []
    eid = _record(client)
    response = _add(client, import_id, eid, create_runs=True)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sent"] == []
    assert body["counts"]["sent"] == 0 and body["counts"]["already_sent"] == 0
    assert body["counts"]["runs_created"] == 9
    assert body["readings_notes"]["captured_as_run_notes"] == 9
    assert body["data_quality_notes"]["captured_as_run_notes"] == 6
    exp = ws.load_experiment(eid)
    assert len(exp.runs) == 9 and exp.proposals == []
    # …and a second identical batch is a genuine no-op.
    rev = exp.rev
    again = _add(client, import_id, eid, create_runs=True)
    assert again.status_code == 200 and again.json()["counts"]["runs_created"] == 0
    assert ws.load_experiment(eid).rev == rev


def test_without_create_runs_nothing_sendable_is_still_refused_and_says_what_would_work(
    client, nothing_sendable
):
    import_id = _import(client, nothing_sendable)
    eid = _record(client)
    rev = ws.load_experiment(eid).rev
    response = _add(client, import_id, eid)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "nothing_to_send"
    assert "create_runs: true" in response.json()["message"]
    assert ws.load_experiment(eid).rev == rev and ws.load_experiment(eid).runs == []


def test_an_archive_read_but_not_reconstructed_is_still_told_to_reconstruct_first(client):
    """MEASURED IN A REAL BROWSER: before a reconstruction an archive has nine measurements
    and no candidate, and `create_runs` made nine runs whose notes listed almost nothing
    (the notes are built from the candidates). It is refused, and says why."""
    created = client.post("/api/imports", json={"label": "unread"}).json()["import"]["import_id"]
    assert client.post(
        f"/api/imports/{created}/sources", json={"kind": "archive", "fixture_name": ARCHIVE}
    ).status_code == 200
    assert client.post(f"/api/imports/{created}/parse").status_code == 200
    session = hist.load_session(created)
    assert len(session.archive_reading.run_candidate_units()) == 9
    assert list(hist.candidates_of(session)) == []
    eid = _record(client)
    response = _add(client, created, eid, create_runs=True)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "nothing_to_send"
    assert "reconstruct it first" in response.json()["message"]
    assert ws.load_experiment(eid).runs == [] and ws.load_experiment(eid).notes == []


def test_with_create_runs_and_nothing_to_create_it_is_still_nothing_to_send(client):
    """An import with no candidates and no archive: nothing to send AND nothing to make."""
    created = client.post("/api/imports", json={"label": "empty"}).json()["import"]["import_id"]
    eid = _record(client)
    response = _add(client, created, eid, create_runs=True)
    assert response.status_code == 422
    assert response.json()["error"] == "nothing_to_send"


# --- item 4: the companion is keyed on content -----------------------------------


def test_the_companion_is_not_doubled_by_a_zip_nested_two_folders_deep(client, staging):
    eid = _record(client)
    first = _add(client, _import(client, "staged:synthetic_corpus"), eid, create_runs=True).json()
    # EVERY entry lands: a key on the bytes alone would collapse the scan exports whose
    # bytes are identical (measured: 127 -> 116), which is why the file NAME is in it.
    assert first["extended_context"]["available"] == first["extended_context"]["added"] == 127
    nested = _import(client, "staged:nested.zip")
    paths = {r["archive_path"] for r in hist.load_session(nested).archive_reading.manifest}
    assert any(p.startswith("inner/") for p in paths), "the layout really differs"
    second = _add(client, nested, eid, create_runs=True)
    assert second.status_code == 200, second.text
    assert second.json()["extended_context"]["added"] == 0
    assert second.json()["extended_context"]["total_on_record"] == 127


def test_a_companion_written_under_the_old_path_ids_is_not_written_again(client):
    """A record written before content ids holds each entry under the reader's
    path-naming ``evidence_id``. A re-import must match that spelling too."""
    import_id = _import(client)
    eid = _record(client)
    assert _add(client, import_id, eid, create_runs=True).status_code == 200
    rows = hist.load_session(import_id).archive_reading.extended_context_entries
    old_id = {(r["concept"], r["source"], r["locator"], r["raw_literal"]): r["entry_id"] for r in rows}
    with ws.record_lock(eid):
        exp = ws.load_experiment(eid)
        assert all(e.entry_id.startswith("ctx2:") for e in exp.extended_context.entries)
        exp.extended_context = dataclasses.replace(
            exp.extended_context,
            entries=tuple(
                dataclasses.replace(
                    e, entry_id=old_id[(e.concept, e.source, e.locator, e.raw_literal)]
                )
                for e in exp.extended_context.entries
            ),
        )
        exp.save_versioned()
    again = _add(client, _import(client), eid, create_runs=True)
    assert again.status_code == 200, again.text
    assert again.json()["extended_context"]["added"] == 0
    assert len(ws.load_experiment(eid).extended_context.entries) == 127
    assert isinstance(ws.load_experiment(eid).extended_context, xc.ExtendedContext)
