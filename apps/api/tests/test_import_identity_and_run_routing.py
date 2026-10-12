"""THREE IMPORT DEFECTS AN INDEPENDENT QA AUDIT MEASURED IN A REAL BROWSER (2026-10-11).

Every fixture here is SYNTHETIC — the BL15 synthetic mini corpus and the multi-operator
semantics corpus, both committed under ``tests/fixtures/bl15/``, plus copies of them
made inside ``tmp_path``. Nothing under ``examples/`` is read and no database is opened.

* **C-01 — values landed on the wrong run.** With "Make one run per measurement" OFF,
  the batch sent EVERY measurement's run-owned values to the ONE named run, so it held
  competing acquisition start times from nine different measurements; and the single-
  candidate send accepted measurement #2's value onto the run made from measurement #1.
* **C-02 — re-importing duplicated everything.** The same corpus staged once as a
  FOLDER and once as a ZIP made a second set of runs (18 runs, 9 distinct labels),
  duplicate proposals and duplicate Data Quality Notes, because the archive's NAME was
  part of the acquisition identity; and a second import session of the same archive
  minted every proposal again, because the proposal key carried the session id.
* **C-09 — a year-apart timestamp disagreement was not flagged.** The mini corpus's
  SPEC header said ``#E 4102444800`` (2100-01-01T00:00Z) and ``#D Fri Jan 01 00:00:00
  2099``; the epoch candidate was "Ready to Send" and nothing was a conflict.

**THE FIXTURE WAS THE ERROR, AND IT IS CORRECTED (2026-10-11).** Its gold file, readme and
notes file all say 2099, so every ``#E`` was moved back exactly 365 days
(``tests/fixtures/bl15/README.md``). The C-09 cross-check is therefore proven on a
deliberately DISAGREEING tmp copy (``disagreeing_mini``, the auditor's exact bytes), and
the corrected committed corpus is shown to send its start times again.

MEASURED: every test whose docstring says what ``main`` did FAILS on an exported copy of
``origin/main`` at ``1879baef``. The fixes made after the first independent review (a run
added by hand holding several measurements, remark keys that named the notes file's path,
the beamtime source basis, macOS Finder artefacts, the already-sent report's run, the
same-file restriction and the exact gap wording) were each checked by reverting that one
fix and watching its test fail. The rest PASS on ``main`` by design and are controls (11,
measured) — the within-bound rows of C-09, the scan-line, unreadable-line and other-file
cases (``main`` compares nothing, so it trivially agrees; the other-file case was also
mutation-checked), the agreeing semantics corpus, the only-run invariant, and the guard that
already-held values never count against a named run. Three tests cover records written BEFORE this change (old origin spelling, old
remark keys, proposals with no content key); each was checked by removing the
backward-compatible read it relies on.
"""

from __future__ import annotations

import dataclasses
import shutil
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import isaac_api.capabilities as capabilities
import isaac_api.historical_import as hist
import isaac_api.identity as identity
import isaac_api.workspace as ws
from isaac_api.bl15 import evidence as ev
from isaac_api.bl15 import reconstruct as rc

REPO_ROOT = Path(__file__).resolve().parents[3]
SEMANTICS = "tests/fixtures/bl15/semantics/multi_operator_corpus"
ARCHIVE = "bl15_synthetic_semantics_corpus"
MINI = "bl15_synthetic_mini_corpus"
EPOCH_PATH = "timestamps.acquired_start_utc"


# --- fixtures -----------------------------------------------------------------


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv(identity.EDGE_TRUST_VERIFIER_ENV, raising=False)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, raising=False)
    monkeypatch.delenv(capabilities.INGESTION_ENV, raising=False)
    monkeypatch.delenv(capabilities.STAGING_ROOT_ENV, raising=False)
    monkeypatch.setitem(hist.ARCHIVE_FIXTURES, ARCHIVE, SEMANTICS)
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture()
def staged(client, tmp_path, monkeypatch):
    """The semantics corpus staged TWICE: as a folder, and as a ZIP of the same files.

    The ZIP carries a single wrapper folder, which the walk strips
    (``bl15.archive.common_root_prefix``), so every member's archive path is the same
    in both containers and only the CONTAINER differs — exactly the auditor's case.
    """
    staging = tmp_path / "staging"
    staging.mkdir()
    folder = staging / "synthetic_corpus"
    shutil.copytree(REPO_ROOT / SEMANTICS, folder)
    with zipfile.ZipFile(staging / "synthetic_corpus_copy.zip", "w") as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                zf.write(path, "synthetic_corpus_copy/" + str(path.relative_to(folder)))
    monkeypatch.setenv(capabilities.INGESTION_ENV, capabilities.INGESTION_MODE_STAGING)
    monkeypatch.setenv(capabilities.STAGING_ROOT_ENV, str(staging))
    return ("staged:synthetic_corpus", "staged:synthetic_corpus_copy.zip")


def _zip_folder(folder: Path, target: Path, prefix: str, *, finder: bool = False) -> None:
    """Zip ``folder`` with every member under ``prefix``; ``finder`` adds what macOS
    Finder adds — a `__MACOSX/` AppleDouble twin of every file, and `.DS_Store` files."""
    with zipfile.ZipFile(target, "w") as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                relative = str(path.relative_to(folder))
                zf.write(path, prefix + relative)
                if finder:
                    head, _sep, name = (prefix + relative).rpartition("/")
                    zf.writestr(f"__MACOSX/{head}/._{name}", b"\x00\x05\x16\x07 SYNTHETIC AppleDouble")
        if finder:
            zf.writestr(prefix + ".DS_Store", b"SYNTHETIC Finder settings")
            zf.writestr(prefix + "01_01_ZZ1_acid_after500Cycling_filter10_100mV_dir/.DS_Store", b"x")


@pytest.fixture()
def staged_layouts(client, tmp_path, monkeypatch):
    """The semantics corpus staged as a folder, as a ZIP nested `outer/inner/`, and as a
    Finder-made ZIP (one wrapper, plus `__MACOSX/` and `.DS_Store`) — and as a folder
    holding a `.DS_Store` of its own. Only the container and its layout differ."""
    staging = tmp_path / "staging"
    staging.mkdir()
    folder = staging / "synthetic_corpus"
    shutil.copytree(REPO_ROOT / SEMANTICS, folder)
    _zip_folder(folder, staging / "nested.zip", "outer/inner/")
    _zip_folder(folder, staging / "finder.zip", "synthetic_corpus/", finder=True)
    finder_folder = staging / "finder_folder"
    shutil.copytree(REPO_ROOT / SEMANTICS, finder_folder)
    (finder_folder / ".DS_Store").write_bytes(b"SYNTHETIC Finder settings")
    monkeypatch.setenv(capabilities.INGESTION_ENV, capabilities.INGESTION_MODE_STAGING)
    monkeypatch.setenv(capabilities.STAGING_ROOT_ENV, str(staging))
    return {
        "folder": "staged:synthetic_corpus",
        "nested": "staged:nested.zip",
        "finder": "staged:finder.zip",
        "finder_folder": "staged:finder_folder",
    }


def _import(client, archive: str = ARCHIVE) -> str:
    created = client.post("/api/imports", json={"label": "synthetic routing"})
    assert created.status_code == 200, created.text
    import_id = created.json()["import"]["import_id"]
    added = client.post(
        f"/api/imports/{import_id}/sources", json={"kind": "archive", "fixture_name": archive}
    )
    assert added.status_code == 200, added.text
    assert client.post(f"/api/imports/{import_id}/parse").status_code == 200
    assert client.post(f"/api/imports/{import_id}/reconstruct").status_code == 200
    return import_id


def _view(client, import_id: str) -> dict:
    response = client.get(f"/api/imports/{import_id}")
    assert response.status_code == 200, response.text
    return response.json()["import"]


def _record(client, title="routing record") -> str:
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


def _propose(client, import_id: str, candidate_id: str, eid: str, run_id: str | None):
    body = {"experiment_id": eid}
    if run_id is not None:
        body["run_id"] = run_id
    return client.post(
        f"/api/imports/{import_id}/candidates/{candidate_id}/propose",
        json=body,
        headers={"If-Match": _etag(client, eid)},
    )


def _new_run(client, eid: str, label: str) -> str:
    response = client.post(
        f"/api/experiments/{eid}/runs",
        json={"label": label},
        headers={"If-Match": _etag(client, eid)},
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["run"]["id"]


def _units(view: dict) -> list[dict]:
    rows = view["archive"]["units_page"]["rows"]
    assert view["archive"]["units_page"]["total"] == len(rows)
    return rows


def _epoch_candidates(view: dict) -> dict[str, str]:
    """``unit stem -> candidate id`` for every SENDABLE acquisition-epoch candidate."""
    sendable = set(view["send_plan"]["sendable"])
    return {
        cid.split("::", 1)[0]: cid
        for cid in sendable
        if cid.endswith("::acquisition_epoch")
    }


def _record_origins_by_hand(eid: str, view: dict, *, skip: tuple[str, ...] = ()) -> dict[str, str]:
    """One hand-made run per measurement, each RECORDED as made from that measurement.

    White-box on purpose: ``create_runs`` would also SEND every value, and what C-01's
    tests need is a record whose runs carry recorded origins and NO proposals yet, so the
    routing of a later send can be observed rather than deduplicated away.
    Returns ``stem -> run id``.
    """
    out: dict[str, str] = {}
    with ws.record_lock(eid):
        exp = ws.load_experiment(eid)
        for unit in _units(view):
            if not unit["run_candidate"] or unit["stem"] in skip:
                continue
            run = exp.add_run(label=f"hand {unit['stem'][:5]}", draft={})
            assert exp.record_run_origin(
                run.id,
                {
                    "acquisition_identity": unit["acquisition_identity"],
                    "acquisition_path": unit["acquisition_path"],
                    "stem": unit["stem"],
                },
            )
            out[unit["stem"]] = run.id
        exp.save_versioned()
    return out


# =============================================================================
# C-09 — a zone-less date line is CROSS-CHECKED against the epoch
# =============================================================================


def _spec_items(epoch_iso: str, date_line: str, *, scan_line: str | None = None):
    """The two header statements one SPEC acquisition makes about its start, built as
    the SPEC reader builds them (``bl15.spec``): ``#E`` normalised to UTC, ``#D`` read."""
    path = "01_01_ZZ1_synthetic"
    items = [
        ev.SourceEvidence(
            evidence_id="e-1",
            source_path=path,
            source_type=ev.SOURCE_TYPE_SPEC_ACQUISITION,
            locator="line 2 header #E",
            raw_literal="4102444800",
            concept=ev.CONCEPT_ACQUISITION_EPOCH,
            parser_id="synthetic",
            determinism=ev.DETERMINISM_NORMALIZED,
            normalized_value=epoch_iso,
            normalization_rule="unix_epoch_seconds_to_iso8601_utc",
            timestamp_utc=epoch_iso,
            scope=ev.SCOPE_MEASUREMENT,
        ),
        ev.SourceEvidence(
            evidence_id="e-2",
            source_path=path,
            source_type=ev.SOURCE_TYPE_SPEC_ACQUISITION,
            locator="line 3 header #D",
            raw_literal=date_line,
            concept=ev.CONCEPT_ACQUISITION_TIMESTAMP,
            parser_id="synthetic",
            scope=ev.SCOPE_MEASUREMENT,
        ),
    ]
    if scan_line is not None:
        items.append(
            ev.SourceEvidence(
                evidence_id="e-3",
                source_path=path,
                source_type=ev.SOURCE_TYPE_SPEC_ACQUISITION,
                locator="line 9 header #D (scan 1)",
                raw_literal=scan_line,
                concept=ev.CONCEPT_ACQUISITION_TIMESTAMP,
                parser_id="synthetic",
                scope=ev.SCOPE_SCAN,
                scan="1",
            )
        )
    return items


def _epoch_of(items):
    candidates = rc._candidates_from_evidence(
        items,
        candidate_prefix="01_01_ZZ1_synthetic",
        source_ids={i.source_path: "src" for i in items},
        by_concept=defaultdict(int),
        by_status=defaultdict(int),
        unregistered=set(),
    )
    return next(c for c in candidates if c.candidate_id.endswith("::acquisition_epoch"))


def _spec_date(instant: datetime) -> str:
    return instant.strftime("%a %b %d %H:%M:%S %Y")


EPOCH = datetime(2100, 1, 1, 0, 10, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("gap", "conflict"),
    [
        (timedelta(0), False),
        (timedelta(minutes=10), False),
        (timedelta(hours=14), False),  # the widest real offset, UTC+14:00
        (-timedelta(hours=14), False),  # the bound is applied EITHER WAY
        (-timedelta(hours=12), False),  # UTC-12:00
        (timedelta(hours=14, seconds=1), True),
        (-timedelta(hours=14, seconds=1), True),
        (timedelta(days=365), True),
        (-timedelta(days=365), True),
    ],
)
def test_C09_the_bound_is_fourteen_hours_either_way(gap, conflict):
    """On ``main`` every row was ``conflict=False``: the two were never compared."""
    wall = (EPOCH + gap).replace(tzinfo=None)
    candidate = _epoch_of(_spec_items(EPOCH.isoformat(), _spec_date(wall)))
    if not conflict:
        # WITHIN THE BOUND NOTHING CHANGES — the epoch is offered exactly as before, and
        # the local time is neither converted nor "reconciled" into it.
        assert candidate.proposable
        assert candidate.proposed_value == EPOCH.isoformat()
        assert candidate.unresolved_reason is None
        return
    assert candidate.unresolved_reason == hist.UNRESOLVED_SOURCES_DISAGREE
    assert candidate.proposed_value is None
    assert not candidate.proposable
    values = {row["value"] for row in candidate.disagreement}
    # BOTH READINGS, VERBATIM: the epoch as the UTC instant it states, the date line as
    # the file wrote it — never converted into a zone it does not name.
    assert values == {EPOCH.isoformat(), _spec_date(wall)}
    literals = {s["value"] for s in candidate.supporting_statements}
    assert {"4102444800", _spec_date(wall)} <= literals


def test_C09_a_scan_date_line_is_not_compared_with_the_files_start():
    """A ``#D`` inside a scan is THAT scan's start, which may be days after the file's
    epoch; only the header's own ``#D`` states the same instant as ``#E``."""
    wall = EPOCH.replace(tzinfo=None)
    candidate = _epoch_of(
        _spec_items(EPOCH.isoformat(), _spec_date(wall), scan_line=_spec_date(wall + timedelta(days=3)))
    )
    assert candidate.proposable and candidate.proposed_value == EPOCH.isoformat()


def test_C09_an_unreadable_date_line_decides_nothing():
    """A date line this build cannot read is neither agreement nor disagreement."""
    candidate = _epoch_of(_spec_items(EPOCH.isoformat(), "SYNTHETIC not a date"))
    assert candidate.proposable and candidate.proposed_value == EPOCH.isoformat()


#: How far the committed mini corpus's `#E` lines were moved (2026-10-11): exactly 365 days.
#: They said 2100 while the fixture's gold file, readme and notes file all say 2099 — so the
#: epochs were the authoring error. Adding it back reproduces the auditor's exact bytes.
YEAR_SECONDS = 31_536_000


@pytest.fixture()
def disagreeing_mini(tmp_path, monkeypatch):
    """The mini corpus AS THE AUDITOR SAW IT: every `#E` a year after its own `#D`.

    A tmp copy of the committed fixture with every `#E` value moved forward by
    :data:`YEAR_SECONDS`, applied to every file alike so the byte-identical `*_dir`
    copies stay byte-identical. This is the deliberately disagreeing variant that keeps
    C-09 proven now that the committed fixture is internally consistent.
    """
    source = hist.ARCHIVE_FIXTURE_ROOT / "tests/fixtures/bl15/gold/mini_corpus"
    copy = tmp_path / "mini_corpus_epoch_a_year_late"
    shutil.copytree(source, copy)
    for path in sorted(copy.rglob("*")):
        if not path.is_file():
            continue
        lines = path.read_bytes().split(b"\n")
        moved = [
            b"#E " + str(int(line[3:].strip()) + YEAR_SECONDS).encode()
            if line.startswith(b"#E ")
            else line
            for line in lines
        ]
        if moved != lines:
            path.write_bytes(b"\n".join(moved))
    name = "bl15_synthetic_mini_corpus_epoch_a_year_late"
    monkeypatch.setitem(hist.ARCHIVE_FIXTURES, name, str(copy))
    return name


def test_C09_a_year_apart_header_is_a_conflict_on_the_epoch(client, disagreeing_mini):
    """The auditor's own case, reproduced byte for byte. On ``main``: ``review_status ==
    'ready'``, a value of ``2100-01-01T00:00:00+00:00``, and the candidate sendable."""
    view = _view(client, _import(client, disagreeing_mini))
    stem = "01_01_SYN1_acid_beforeCycling_filter10_060mV"
    cand = next(
        c for c in view["reconstruction"]["candidates"] if c["candidate_id"] == f"{stem}::acquisition_epoch"
    )
    assert cand["kind"] == "field"
    assert cand["proposed_value"] is None
    assert cand["unresolved_reason"] == "sources_disagree"
    assert cand["review_status"] == "sources_conflict"
    assert {row["value"] for row in cand["disagreement"]} == {
        "2100-01-01T00:00:00+00:00",
        "Fri Jan 01 00:00:00 2099",
    }
    assert cand["candidate_id"] not in view["send_plan"]["sendable"]
    assert not [c for c in view["send_plan"]["sendable"] if c.endswith("::acquisition_epoch")]
    # EXACT, never a rounded figure: 365 days to the second.
    assert "They are 365 days apart" in cand["rule"]


def test_I3_the_corrected_mini_corpus_sends_its_start_times_again(client):
    """The committed fixture's `#E` lines now name 2099, as its gold file, readme and notes
    file always did, so each sample measurement's start time is ready, and Add with one run
    per measurement makes 4 runs and puts each start time on its OWN measurement's run."""
    import_id = _import(client, MINI)
    view = _view(client, import_id)
    epochs = _epoch_candidates(view)
    assert sorted(epochs) == [
        "01_01_SYN1_acid_beforeCycling_filter10_060mV",
        "02_01_SYN1_acid_beforeCycling_filter10_060mV_again",
        "03_02_SYN2_base_after1500Cycling_ffilter35_1200mV_zz9",
        "03_02_SYN2_base_after1500Cycling_filter20_0p5nm_1200mV",
    ]
    by_id = {c["candidate_id"]: c for c in view["reconstruction"]["candidates"]}
    assert by_id[epochs["01_01_SYN1_acid_beforeCycling_filter10_060mV"]]["proposed_value"] == (
        "2099-01-01T00:00:00+00:00"
    )
    assert all(by_id[cid]["review_status"] == "ready" for cid in epochs.values())

    eid = _record(client)
    added = _add(client, import_id, eid, create_runs=True)
    assert added.status_code == 200, added.text
    body = added.json()
    assert body["counts"]["runs_created"] == 4
    run_of_stem = {row["stem"]: row["run_id"] for row in body["created_runs"]}
    sent = {row["candidate_id"]: row for row in body["sent"]}
    for stem, cid in epochs.items():
        assert sent[cid]["already_sent"] is False
        assert sent[cid]["run_id"] == run_of_stem[stem]


def test_C09_the_clock_check_compares_only_the_SAME_files_header():
    """An epoch in one file and a year-apart date line in ANOTHER are two files' facts,
    not two spellings of one instant — nothing is compared and nothing changes."""
    items = _spec_items(EPOCH.isoformat(), _spec_date((EPOCH + timedelta(days=365)).replace(tzinfo=None)))
    items[1] = dataclasses.replace(items[1], source_path="02_02_ZZ2_another_file")
    candidate = _epoch_of(items)
    assert candidate.proposable and candidate.proposed_value == EPOCH.isoformat()


@pytest.mark.parametrize(
    ("gap", "words"),
    [
        (timedelta(hours=14, seconds=1), "14 h 0 min 1 s"),
        (-timedelta(hours=14, seconds=1), "14 h 0 min 1 s"),
        (timedelta(hours=14, minutes=30), "14 h 30 min"),
        (timedelta(days=1, hours=2, minutes=5), "1 day, 2 h 5 min"),
        (timedelta(days=1, hours=2, minutes=3, seconds=4), "1 day, 2 h 3 min 4 s"),
        (timedelta(days=365), "365 days"),
    ],
)
def test_C09_the_gap_is_written_exactly_and_never_as_the_bound(gap, words):
    """Just over the bound the rule used to read "14.0 hours apart … no real offset
    exceeds 14 hours" — a figure equal to the bound it claimed to exceed."""
    wall = (EPOCH + gap).replace(tzinfo=None)
    candidate = _epoch_of(_spec_items(EPOCH.isoformat(), _spec_date(wall)))
    assert f"They are {words} apart" in candidate.rule
    assert "14.0" not in candidate.rule


def test_C09_agreeing_readings_in_the_semantics_corpus_are_unchanged(client):
    """Each semantics-corpus file's ``#E`` is 10-90 minutes from its header ``#D``, and
    unit 04's scan-2 ``#D`` is a day later — none of which is a disagreement."""
    view = _view(client, _import(client))
    epochs = _epoch_candidates(view)
    assert len(epochs) == 9
    by_id = {c["candidate_id"]: c for c in view["reconstruction"]["candidates"]}
    for cid in epochs.values():
        assert by_id[cid]["review_status"] == "ready"
        assert by_id[cid]["proposed_value"].startswith("2100-01-01T")


# =============================================================================
# C-02 — the acquisition identity is the CONTENT, never the container
# =============================================================================


def test_C02_the_identity_names_no_container_and_keeps_shared_legacy_numbers_apart(client, staged):
    folder, zipped = staged
    a = {u["stem"]: u["acquisition_identity"] for u in _units(_view(client, _import(client, folder)))}
    b = {u["stem"]: u["acquisition_identity"] for u in _units(_view(client, _import(client, zipped)))}
    assert a == b, "the same files in a folder and in a ZIP must be the same acquisitions"
    for identity_ in a.values():
        assert "synthetic_corpus" not in identity_
    # the two acquisitions carrying legacy number 05 stay TWO
    fives = [i for stem, i in a.items() if stem.startswith("05_")]
    assert len(fives) == 2 and len(set(fives)) == 2


def test_C02_a_folder_then_a_zip_of_the_same_files_is_one_set_of_runs(client, staged):
    """On ``main``: the ZIP batch reported ``runs_created: 9`` and the record ended with
    18 runs, 18 proposals and 12 Data Quality Notes."""
    folder, zipped = staged
    eid = _record(client)
    first = _add(client, _import(client, folder), eid, create_runs=True)
    assert first.status_code == 200, first.text
    first = first.json()
    assert first["counts"]["runs_created"] == 9

    second = _add(client, _import(client, zipped), eid, create_runs=True)
    assert second.status_code == 200, second.text
    second = second.json()
    assert second["counts"]["runs_created"] == 0
    assert second["counts"]["runs_already_present"] == 9
    assert {r["matched_by"] for r in second["runs_already_present"]} == {"acquisition_identity"}
    assert second["counts"]["sent"] == 0
    assert second["counts"]["already_sent"] == first["counts"]["sent"] == 9
    assert second["data_quality_notes"]["captured_as_run_notes"] == 0
    assert second["data_quality_notes"]["already_present"] == first["data_quality_notes"][
        "captured_as_run_notes"
    ]

    exp = ws.load_experiment(eid)
    assert len(exp.runs) == 9
    assert len({r.label for r in exp.runs}) == 9
    assert len(exp.proposals) == 9
    dqn = [n for n in exp.notes if n.text.startswith("Data Quality Note")]
    assert len(dqn) == first["data_quality_notes"]["captured_as_run_notes"]
    # each "already sent" row names the proposal that was ALREADY there, on its run
    by_id = {p.proposal_id: p for p in exp.proposals}
    for row in second["sent"]:
        assert row["already_sent"] is True
        assert by_id[row["proposal_id"]].run_id == row["run_id"]


def test_C02_a_second_session_of_the_same_archive_mints_no_second_proposal(client):
    """On ``main`` the runs were matched but every proposal was minted again (9 -> 18),
    because the proposal key was ``import:<import id>:<candidate id>``."""
    eid = _record(client)
    first = _add(client, _import(client), eid, create_runs=True).json()
    assert first["counts"]["sent"] == 9
    second = _add(client, _import(client), eid, create_runs=True)
    assert second.status_code == 200, second.text
    second = second.json()
    assert second["counts"]["sent"] == 0
    assert second["counts"]["already_sent"] == 9
    assert len(ws.load_experiment(eid).proposals) == 9


def test_C02_the_single_candidate_send_is_exactly_once_across_sessions_too(client):
    eid = _record(client)
    run = _new_run(client, eid, "hand-made")
    first_import = _import(client)
    stem, cid = sorted(_epoch_candidates(_view(client, first_import)).items())[0]
    first = _propose(client, first_import, cid, eid, run)
    assert first.status_code == 200, first.text
    assert first.json()["deduplicated"] is False

    again = _propose(client, _import(client), cid, eid, run)
    assert again.status_code == 200, again.text
    assert again.json()["deduplicated"] is True
    assert again.json()["proposal"]["proposal_id"] == first.json()["proposal"]["proposal_id"]
    assert len(ws.load_experiment(eid).proposals) == 1


def test_C02_runs_recorded_under_the_old_identity_format_are_still_matched(client, staged):
    """Records written before this change carry ``<archive>:<path>@<digest>``. A later
    import of the same files — from ANOTHER container — must find those runs, and must
    neither make new ones nor raise on the differently-spelled origin row."""
    folder, zipped = staged
    eid = _record(client)
    first = _add(client, _import(client, folder), eid, create_runs=True).json()
    assert first["counts"]["runs_created"] == 9
    with ws.record_lock(eid):
        exp = ws.load_experiment(eid)
        for run_id, origin in list(exp.historical_run_origins.items()):
            digest = origin["content_sha256"]
            assert len(digest) == 64
            exp.historical_run_origins[run_id] = {
                **origin,
                "acquisition_identity": f"{folder}:{origin['acquisition_path']}@{digest}",
            }
        exp.save_versioned()

    second = _add(client, _import(client, zipped), eid, create_runs=True)
    assert second.status_code == 200, second.text
    second = second.json()
    assert second["counts"]["runs_created"] == 0
    assert {r["matched_by"] for r in second["runs_already_present"]} == {"acquisition_identity"}
    assert second["data_quality_notes"]["captured_as_run_notes"] == 0
    exp = ws.load_experiment(eid)
    assert len(exp.runs) == 9 and len(exp.proposals) == 9
    # the old rows are KEPT as written — an origin is a fact about how a run was made
    assert all(":" in o["acquisition_identity"].split("@")[0] for o in exp.historical_run_origins.values())


def test_C02_proposals_written_before_content_keys_are_still_found(client):
    """A proposal minted before 2026-10-11 has no cross-session key on its note. Where
    its run's recorded origin pins the acquisition, a later session still finds it."""
    import dataclasses

    eid = _record(client)
    assert _add(client, _import(client), eid, create_runs=True).json()["counts"]["sent"] == 9
    with ws.record_lock(eid):
        exp = ws.load_experiment(eid)
        stripped = 0
        for note in list(exp.notes):
            if (note.client_request_key or "").startswith("historical-proposal:"):
                exp.replace_note(dataclasses.replace(note, client_request_key=None))
                stripped += 1
        assert stripped == 9
        exp.save_versioned()

    second = _add(client, _import(client), eid, create_runs=True)
    assert second.status_code == 200, second.text
    assert second.json()["counts"]["sent"] == 0
    assert second.json()["counts"]["already_sent"] == 9
    assert len(ws.load_experiment(eid).proposals) == 9


def test_C02_remarks_kept_under_the_old_identity_are_not_kept_again(client, staged):
    """A record written before 2026-10-11 keyed each Data Quality Note on the
    container-naming identity. The first re-import after the change — here from the OTHER
    container — must find those notes, not mint every remark a second time."""
    import dataclasses

    import isaac_api.routes as routes

    folder, zipped = staged
    eid = _record(client)
    first_import = _import(client, folder)
    first = _add(client, first_import, eid, create_runs=True).json()
    kept = first["data_quality_notes"]["captured_as_run_notes"]
    assert kept > 0

    # Re-spell what the record holds exactly as the pre-change build wrote it.
    reading = hist.load_session(first_import).archive_reading
    digest_of_path = {row["archive_path"]: row["content_sha256"] for row in reading.manifest}
    legacy_of: dict[str, str] = {}
    old_identity: dict[str, str] = {}
    for unit in reading.units:
        key = hist.measurement_key(unit)
        digest = key.rsplit(ws.ACQUISITION_IDENTITY_SEPARATOR, 1)[1]
        old_identity[key] = f"{folder}:{unit.acquisition_path}@{digest}"
        for row in unit.data_quality_notes:
            current = routes._dqn_request_key(key, row, digest_of_path[row["source_path"]])
            legacy_of[current] = routes._dqn_legacy_request_key(old_identity[key], row)
    with ws.record_lock(eid):
        exp = ws.load_experiment(eid)
        for run_id, origin in list(exp.historical_run_origins.items()):
            exp.historical_run_origins[run_id] = {
                **origin,
                "acquisition_identity": old_identity[origin["acquisition_identity"]],
            }
        rekeyed = 0
        for note in list(exp.notes):
            if note.client_request_key in legacy_of:
                exp.replace_note(
                    dataclasses.replace(note, client_request_key=legacy_of[note.client_request_key])
                )
                rekeyed += 1
        assert rekeyed == kept
        exp.save_versioned()

    second = _add(client, _import(client, zipped), eid, create_runs=True)
    assert second.status_code == 200, second.text
    dqn = second.json()["data_quality_notes"]
    assert dqn["captured_as_run_notes"] == 0
    assert dqn["already_present"] == kept


def test_C02_a_zip_nested_two_folders_deep_adds_no_remark_twice(client, staged_layouts):
    """The independent review's measurement: folder, then a ZIP of the same files under
    `outer/inner/` — runs and proposals were deduplicated, but every Data Quality Note
    was kept AGAIN (6 -> 12), because its key hashed the notes file's archive PATH."""
    eid = _record(client)
    first = _add(client, _import(client, staged_layouts["folder"]), eid, create_runs=True).json()
    kept = first["data_quality_notes"]["captured_as_run_notes"]
    assert kept == 6
    nested_import = _import(client, staged_layouts["nested"])
    paths = {row["archive_path"] for row in hist.load_session(nested_import).archive_reading.manifest}
    assert any(path.startswith("inner/") for path in paths), "the layout really differs"
    second = _add(client, nested_import, eid, create_runs=True)
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["counts"]["runs_created"] == 0
    assert body["counts"]["sent"] == 0
    assert body["data_quality_notes"]["captured_as_run_notes"] == 0
    assert body["data_quality_notes"]["already_present"] == kept
    exp = ws.load_experiment(eid)
    assert len([n for n in exp.notes if n.text.startswith("Data Quality Note")]) == kept


def test_C02_macos_finder_artefacts_are_skipped_and_reported(client, staged_layouts):
    """A Finder-made ZIP carries `__MACOSX/` beside its one wrapper folder, and Finder
    writes `.DS_Store` into folders. Neither is read as a source; each is reported; and
    the wrapper is still stripped, so every path matches the plain folder's."""
    from isaac_api.bl15 import inventory as inv

    plain = _import(client, staged_layouts["folder"])
    plain_paths = {r["archive_path"] for r in hist.load_session(plain).archive_reading.manifest}
    for name in ("finder", "finder_folder"):
        import_id = _import(client, staged_layouts[name])
        reading = hist.load_session(import_id).archive_reading
        paths = {row["archive_path"] for row in reading.manifest}
        assert paths == plain_paths, name
        refused = [r for r in reading.inventory["refused"] if r["reason"] == inv.REFUSAL_OS_METADATA]
        assert refused, name
        assert all("macOS Finder" in r["detail"] for r in refused)
        assert {u.acquisition_identity for u in reading.units} == {
            u.acquisition_identity for u in hist.load_session(plain).archive_reading.units
        }
    finder = hist.load_session(_import(client, staged_layouts["finder"])).archive_reading
    rows = {r["archive_path"]: r for r in finder.inventory["refused"]}
    assert rows["__MACOSX/"]["detail"].startswith(f"{len(plain_paths)} member(s)")
    # THE WRAPPER IS STRIPPED HERE TOO, as from every other path in the reading.
    assert {".DS_Store", "01_01_ZZ1_acid_after500Cycling_filter10_100mV_dir/.DS_Store"} <= set(rows)
    assert not [path for path in rows if path.startswith("synthetic_corpus/")]


def test_C02_a_beamtime_statement_is_identified_by_its_bytes_not_its_path():
    """`hist.candidate_source_basis` for a value no single measurement owns: the same
    statement read from the same BYTES is one source wherever the file sits; different
    bytes at the same path are a different source; and it is never `None`."""
    from types import SimpleNamespace

    def basis(path: str, digest: str):
        reading = SimpleNamespace(
            units=(),
            unit_of_candidate=lambda _cid: None,
            shared_candidate_ids=("shared::ph",),
            manifest=({"archive_path": path, "content_sha256": digest},),
        )
        candidate = SimpleNamespace(
            candidate_id="shared::ph",
            supporting_statements=({"key": "ph", "value": "SYNTHETIC 7", "locator": f"{path} · line 4"},),
        )
        return hist.candidate_source_basis(SimpleNamespace(archive_reading=reading), candidate)

    here = basis("readme.txt", "a" * 64)
    assert here is not None
    assert here == basis("outer/inner/readme.txt", "a" * 64)
    assert here != basis("readme.txt", "b" * 64)


# =============================================================================
# C-01 — a run-owned value goes only to its own measurement's run
# =============================================================================


def test_C01_one_named_run_cannot_take_values_from_several_measurements(client):
    """On ``main``: ``200`` and nine competing start times on one run."""
    import_id = _import(client)
    eid = _record(client)
    run = _new_run(client, eid, "the only run")
    before = ws.load_experiment(eid).rev

    refused = _add(client, import_id, eid, run_id=run)
    assert refused.status_code == 422, refused.text
    body = refused.json()
    assert body["error"] == "values_from_several_measurements"
    assert len(body["measurements"]) == 9
    assert len({m["acquisition_identity"] for m in body["measurements"]}) == 9
    assert all(m["candidate_ids"] for m in body["measurements"])
    assert "one run per measurement" in body["message"]
    # ~~"one at a time"~~ — one at a time onto ONE run is the same defect by a longer road
    # (independent review): the remedy is each value onto its own measurement's run.
    assert "its own measurement's run" in body["message"]
    assert "one at a time" not in body["message"]
    exp = ws.load_experiment(eid)
    assert exp.rev == before and exp.proposals == [] and len(exp.runs) == 1


def test_C01_values_go_to_the_run_recorded_as_made_from_their_measurement(client):
    """Every measurement already has its own run here, so naming one run sends each
    value to ITS measurement's run — and the named run receives only its own."""
    import_id = _import(client)
    view = _view(client, import_id)
    eid = _record(client)
    run_of = _record_origins_by_hand(eid, view)
    named = run_of[sorted(run_of)[0]]

    sent = _add(client, import_id, eid, run_id=named)
    assert sent.status_code == 200, sent.text
    rows = {row["candidate_id"]: row for row in sent.json()["sent"]}
    for stem, cid in _epoch_candidates(view).items():
        assert rows[cid]["run_id"] == run_of[stem]
    exp = ws.load_experiment(eid)
    assert sorted(p.run_id for p in exp.proposals) == sorted(run_of.values())


def test_C01_with_every_measurement_owning_a_run_no_run_need_be_named(client):
    import_id = _import(client)
    view = _view(client, import_id)
    eid = _record(client)
    run_of = _record_origins_by_hand(eid, view)
    sent = _add(client, import_id, eid)
    assert sent.status_code == 200, sent.text
    assert sorted(r["run_id"] for r in sent.json()["sent"]) == sorted(run_of.values())


def test_C01_a_named_run_may_take_the_values_of_exactly_one_other_measurement(client):
    import_id = _import(client)
    view = _view(client, import_id)
    eid = _record(client)
    lone = sorted(_epoch_candidates(view))[-1]
    run_of = _record_origins_by_hand(eid, view, skip=(lone,))
    named = _new_run(client, eid, "hand-made, no origin")

    sent = _add(client, import_id, eid, run_id=named)
    assert sent.status_code == 200, sent.text
    rows = {row["candidate_id"]: row["run_id"] for row in sent.json()["sent"]}
    assert rows[_epoch_candidates(view)[lone]] == named
    assert sorted(v for k, v in rows.items() if not k.startswith(lone)) == sorted(run_of.values())


def test_C01_a_named_run_made_from_another_measurement_is_refused_in_the_batch(client):
    import_id = _import(client)
    view = _view(client, import_id)
    eid = _record(client)
    lone = sorted(_epoch_candidates(view))[-1]
    run_of = _record_origins_by_hand(eid, view, skip=(lone,))
    before = ws.load_experiment(eid).rev

    refused = _add(client, import_id, eid, run_id=run_of[sorted(run_of)[0]])
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"] == "run_is_another_measurement"
    assert [m["stem"] for m in refused.json()["measurements"]] == [lone]
    assert ws.load_experiment(eid).rev == before


def test_C01_the_single_send_refuses_a_run_made_from_another_measurement(client):
    """On ``main``: ``200``, measurement 02's start time on measurement 01's run."""
    import_id = _import(client)
    view = _view(client, import_id)
    eid = _record(client)
    run_of = _record_origins_by_hand(eid, view)
    epochs = _epoch_candidates(view)
    first, second = sorted(epochs)[:2]
    before = ws.load_experiment(eid).rev

    refused = _propose(client, import_id, epochs[second], eid, run_of[first])
    assert refused.status_code == 422, refused.text
    body = refused.json()
    assert body["error"] == "run_is_another_measurement"
    assert body["run_origin"]["stem"] == first
    assert body["candidate_measurement"]["stem"] == second
    assert ws.load_experiment(eid).rev == before

    accepted = _propose(client, import_id, epochs[second], eid, run_of[second])
    assert accepted.status_code == 200, accepted.text
    # a run with NO recorded origin is the scientist's own choice and stays allowed
    free = _new_run(client, eid, "hand-made, no origin")
    assert _propose(client, import_id, epochs[first], eid, free).status_code == 200


def test_C01_a_hand_made_run_takes_one_measurements_values_even_one_at_a_time(client):
    """INVERTED 2026-10-11 after an independent review. This test used to be
    ``..._values_already_sent_one_at_a_time_do_not_count_against_the_named_run`` and
    asserted that nine one-at-a-time sends of nine measurements' start times to ONE run
    added by hand each answered ``200`` — which is the C-01 end state reached by a longer
    road. Now the first send lands, the second measurement's value is refused (nothing
    written), and re-sending the first is still answered as already sent."""
    import_id = _import(client)
    view = _view(client, import_id)
    eid = _record(client)
    free = _new_run(client, eid, "hand-made, no origin")
    epochs = sorted(_epoch_candidates(view).items())
    (first_stem, first), (second_stem, second) = epochs[0], epochs[1]
    assert _propose(client, import_id, first, eid, free).status_code == 200
    before = ws.load_experiment(eid).rev

    refused = _propose(client, import_id, second, eid, free)
    assert refused.status_code == 422, refused.text
    body = refused.json()
    assert body["error"] == "run_is_another_measurement"
    assert body["because"] == "values_already_on_it"
    assert body["candidate_measurement"]["stem"] == second_stem
    assert [h["acquisition_identity"].split("@")[0] for h in body["run_holds"]] == [first_stem]
    assert "its own measurement's run" in body["message"]
    assert "add a run yourself" in body["message"]
    assert "one at a time" not in body["message"]
    assert ws.load_experiment(eid).rev == before
    assert len(ws.load_experiment(eid).proposals) == 1

    again = _propose(client, import_id, first, eid, free)
    assert again.status_code == 200 and again.json()["deduplicated"] is True
    # A NEW SESSION of the same archive is held to the same rule.
    assert _propose(client, _import(client), second, eid, free).status_code == 422


def test_C01_a_batch_cannot_add_another_measurement_to_a_hand_made_run(client):
    """The batch form of the same rule: a run added by hand that already holds one
    measurement's start time is refused as the named run for another measurement."""
    import_id = _import(client)
    view = _view(client, import_id)
    eid = _record(client)
    epochs = sorted(_epoch_candidates(view))
    held, lone = epochs[0], epochs[-1]
    free = _new_run(client, eid, "hand-made, no origin")
    assert _propose(client, import_id, _epoch_candidates(view)[held], eid, free).status_code == 200
    _record_origins_by_hand(eid, view, skip=(held, lone))
    before = ws.load_experiment(eid).rev

    refused = _add(client, import_id, eid, run_id=free)
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"] == "run_is_another_measurement"
    assert refused.json()["because"] == "values_already_on_it"
    assert [m["stem"] for m in refused.json()["measurements"]] == [lone]
    assert ws.load_experiment(eid).rev == before


def test_C01_values_the_record_already_holds_count_against_no_named_run(client):
    """The guard the inverted test used to be about, kept: a value already on the record
    goes nowhere, so it never makes a batch refuse."""
    import_id = _import(client)
    view = _view(client, import_id)
    eid = _record(client)
    epochs = _epoch_candidates(view)
    held = sorted(epochs)[0]
    free = _new_run(client, eid, "hand-made, no origin")
    assert _propose(client, import_id, epochs[held], eid, free).status_code == 200
    _record_origins_by_hand(eid, view, skip=(held,))
    again = _add(client, import_id, eid, run_id=free)
    assert again.status_code == 200, again.text
    assert again.json()["counts"]["sent"] == 8
    assert again.json()["counts"]["already_sent"] == 1


@pytest.fixture()
def armed_client(client, monkeypatch):
    """The fixture verifier — the only configuration in which a person can ACCEPT."""
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, "synthetic.routing.reviewer")
    monkeypatch.delenv(identity.FIXTURE_ACTOR_GROUPS_ENV, raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _review(client, eid: str, pid: str, **body):
    return client.post(
        f"/api/experiments/{eid}/proposals/{pid}/review",
        json={"confirmed_by_user": True, **body},
        headers={"If-Match": _etag(client, eid)},
    )


def _first_two_on_a_hand_made_run(client):
    import_id = _import(client)
    epochs = sorted(_epoch_candidates(_view(client, import_id)).items())
    eid = _record(client)
    free = _new_run(client, eid, "hand-made, no origin")
    sent = _propose(client, import_id, epochs[0][1], eid, free)
    assert sent.status_code == 200, sent.text
    return import_id, eid, free, sent.json()["proposal"]["proposal_id"], epochs[1][1]


@pytest.mark.parametrize("act", [{"action": "withdraw"}, {"action": "reject"}])
def test_C01_a_proposal_taken_back_frees_the_hand_made_run(client, act):
    """Independent re-review: a proposal the scientist WITHDREW or REJECTED still marked
    the run as holding that measurement, so correcting exactly the C-01 mistake left the
    run unusable for the measurement it should have held ("already holds a value read
    from another measurement" — false). A run holds what its LIVE proposals claim."""
    import_id, eid, free, pid, second = _first_two_on_a_hand_made_run(client)
    taken_back = _review(client, eid, pid, **act)
    assert taken_back.status_code == 200, taken_back.text
    accepted = _propose(client, import_id, second, eid, free)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["deduplicated"] is False


def test_C01_an_accepted_proposal_still_holds_the_hand_made_run(armed_client):
    """…and an ACCEPTED one is the run's value now, so the run is still that measurement's."""
    client = armed_client
    import_id, eid, free, pid, second = _first_two_on_a_hand_made_run(client)
    accepted = _review(client, eid, pid, action="accept", accepted_from="candidate")
    assert accepted.status_code == 200, accepted.text
    refused = _propose(client, import_id, second, eid, free)
    assert refused.status_code == 422, refused.text
    assert refused.json()["because"] == "values_already_on_it"


def test_C01_a_proposal_sent_before_this_change_still_marks_its_hand_made_run(client):
    """A proposal minted before content keys has a note with no measurement in its key;
    the run's measurement then comes from the proposal's own candidate id
    (`import:<session>:<stem>::<concept>`), and a different stem is a different file."""
    import_id, eid, free, _pid, second = _first_two_on_a_hand_made_run(client)
    with ws.record_lock(eid):
        exp = ws.load_experiment(eid)
        for note in list(exp.notes):
            if (note.client_request_key or "").startswith("historical-proposal:"):
                exp.replace_note(dataclasses.replace(note, client_request_key=None))
        exp.save_versioned()
    refused = _propose(client, import_id, second, eid, free)
    assert refused.status_code == 422, refused.text
    assert refused.json()["because"] == "values_already_on_it"
    assert "stem" in refused.json()["run_holds"][0]


def test_C01_an_already_sent_value_is_reported_on_the_run_it_is_actually_on(client):
    """A value sent by hand to a run added by hand, whose measurement LATER gets a run of
    its own: the batch routes it to that run, finds it already sent, and must report the
    run the proposal is on — not the run it would have sent it to."""
    import_id = _import(client)
    view = _view(client, import_id)
    eid = _record(client)
    epochs = _epoch_candidates(view)
    held = sorted(epochs)[0]
    free = _new_run(client, eid, "hand-made, no origin")
    assert _propose(client, import_id, epochs[held], eid, free).status_code == 200
    run_of = _record_origins_by_hand(eid, view)
    assert run_of[held] != free
    body = _add(client, import_id, eid).json()
    row = next(r for r in body["sent"] if r["candidate_id"] == epochs[held])
    assert row["already_sent"] is True
    assert row["run_id"] == free


def test_C01_the_run_is_still_never_inferred_from_the_only_run(client):
    """The existing invariant, kept: one run, no recorded origin, no `run_id` -> refused."""
    import_id = _import(client)
    eid = _record(client)
    _new_run(client, eid, "the only run")
    refused = _add(client, import_id, eid)
    assert refused.status_code == 422
    assert refused.json()["error"] == "target_requires_a_run"


def test_C01_the_view_publishes_what_the_forms_need_to_preselect(client):
    """The send plan names each run-owned candidate's measurement, and each run names the
    measurement it was recorded as made from — the SAME key, so a form compares strings
    and re-implements no matching rule."""
    import_id = _import(client)
    view = _view(client, import_id)
    eid = _record(client)
    run_of = _record_origins_by_hand(eid, view)
    measurement_of = view["send_plan"]["measurement_of"]
    runs = client.get(f"/api/experiments/{eid}/runs").json()["runs"]
    origin_of = {r["id"]: (r["historical_origin"] or {}).get("acquisition_identity") for r in runs}
    for stem, cid in _epoch_candidates(view).items():
        assert origin_of[run_of[stem]] == measurement_of[cid]
    plain = _new_run(client, eid, "no origin")
    runs = client.get(f"/api/experiments/{eid}/runs").json()["runs"]
    assert next(r for r in runs if r["id"] == plain)["historical_origin"] is None
