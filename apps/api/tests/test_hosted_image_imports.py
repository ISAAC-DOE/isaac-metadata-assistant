"""THE HOSTED IMAGE MUST CARRY WHAT HISTORICAL IMPORT READS — measured 2026-10-12.

**THE DEFECT.** Reproducing the image layout from the Dockerfile's own ``COPY`` lines
(only what stage 2 copies: ``pyproject.toml``, ``src/``, ``apps/api/``, ``schema/``,
``tests/fixtures/synthetic/``, ``tests/fixtures/official/``) and serving it with
uvicorn, ``GET /api/imports`` answered ``available_fixtures: []`` and
``available_archives: []``. Both lists are filtered by EXISTENCE
(:func:`historical_import.fixture_names`, :func:`historical_import.archive_names`), so a
deployment whose image left the fixtures out advertises nothing — which is the correct
behaviour of the lists and exactly why nothing complained: the hosted Historical Import
screen offered nothing to read, and no test, no CI job and no log said so.

**WHAT THIS FILE PINS.** Every directory the import code reads at runtime is copied
into stage 2 EXCEPT the ones withheld on purpose, and those are asserted absent:
``tests/fixtures/bl15/notes/`` (a governance flag on it is pending the project owner)
and ``tests/fixtures/bl15/gold/mini_corpus/``, whose notes file shares a sentence with
it (orchestrator decision, 2026-10-12, review item I3). The check is a PARSE of the
Dockerfile rather than a docker build, because no docker daemon runs in this test
suite; ``.github/workflows/pr-docker-smoke.yml`` is the only place the built image
itself is checked, and the last test here keeps that workflow's import step naming
exactly what the image offers.

DATA BOUNDARY: none. Every file read is a committed synthetic fixture or a committed
deployment artifact; no database connection is opened.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

import pytest
from fastapi.testclient import TestClient

import isaac_api.capabilities as capabilities
import isaac_api.historical_import as hist
import isaac_api.workspace as ws

REPO_ROOT = ws.REPO_ROOT
DOCKERFILE = REPO_ROOT / "Dockerfile"
SMOKE = REPO_ROOT / ".github" / "workflows" / "pr-docker-smoke.yml"
#: Must never reach the image — a governance flag on it is pending the owner.
NOTES_FIXTURE = "tests/fixtures/bl15/notes"
#: WITHHELD FROM THE IMAGE, and the reason is the notes fixture's (review item I3,
#: 2026-10-12): its `990101 SYNTHETIC BL15 notes.txt` shares a nine-word sentence with
#: `bl15/notes/beamtime-notes.txt`, whose governance call is pending. It stays
#: registered and readable locally; the image does not offer it.
MINI_CORPUS = "tests/fixtures/bl15/gold/mini_corpus"
#: What the image must offer, by the key a client sends.
SHIPPED_ARCHIVES = ("bl15_synthetic_semantics_corpus",)
WITHHELD_ARCHIVES = ("bl15_synthetic_mini_corpus",)


def _stage_two_copies() -> list[str]:
    """The repository paths stage 2 of the Dockerfile copies, normalised, in order.

    Stage 2 begins at the SECOND ``FROM``. ``COPY --from=…`` lines copy out of another
    stage rather than out of the repository and are skipped; so is stage 1, whose
    copies feed only the frontend build.
    """
    stage = 0
    out: list[str] = []
    for raw in DOCKERFILE.read_text("utf-8").splitlines():
        line = raw.strip()
        if line.startswith("FROM "):
            stage += 1
            continue
        if stage != 2 or not line.startswith("COPY ") or "--from" in line:
            continue
        parts = line.split()
        assert len(parts) == 3, f"a COPY this parser does not understand: {line!r}"
        out.append(str(PurePosixPath(parts[1])).rstrip("/"))
    assert out, "no stage-2 COPY was found, so this test proved nothing"
    return out


def _covered(relative: str, copies: list[str]) -> bool:
    """Whether a repository path is inside (or is) one of the copied paths."""
    target = PurePosixPath(relative)
    return any(target == PurePosixPath(c) or PurePosixPath(c) in target.parents for c in copies)


def _runtime_import_paths() -> dict[str, str]:
    """``what -> repo-relative path`` for every directory the import code reads.

    DERIVED FROM THE MODULE, never transcribed: adding an archive to
    :data:`historical_import.ARCHIVE_FIXTURES` adds a row here, and the image check
    below then fails until the Dockerfile copies it.
    """
    out = {"example sources (FIXTURE_DIR)": hist.FIXTURE_DIR.relative_to(REPO_ROOT).as_posix()}
    for name, relative in hist.ARCHIVE_FIXTURES.items():
        out[f"archive {name}"] = relative
    return out


def test_the_withheld_and_shipped_archives_are_every_registered_archive():
    """A NEW archive must be classified, so it cannot be forgotten in either direction."""
    assert sorted(SHIPPED_ARCHIVES + WITHHELD_ARCHIVES) == sorted(hist.ARCHIVE_FIXTURES)
    assert hist.ARCHIVE_FIXTURES["bl15_synthetic_mini_corpus"] == MINI_CORPUS


def test_the_image_copies_every_directory_the_import_reads_except_the_withheld_ones():
    copies = _stage_two_copies()
    withheld = {f"archive {name}" for name in WITHHELD_ARCHIVES}
    missing = {
        what: relative
        for what, relative in _runtime_import_paths().items()
        if what not in withheld and not _covered(relative, copies)
    }
    assert missing == {}, (
        "the hosted image would advertise nothing for these, because the lists are "
        f"filtered by existence: {missing}"
    )


def test_the_mini_corpus_is_not_in_the_image():
    """I3: by a parent directory or by name — a broader ``COPY tests/fixtures/bl15/``
    would carry it in silently, so coverage is checked, not the string."""
    copies = _stage_two_copies()
    assert not _covered(MINI_CORPUS, copies), copies
    assert not _covered(f"{MINI_CORPUS}/990101 SYNTHETIC BL15 notes.txt", copies), copies


def test_every_path_the_image_is_told_to_copy_exists():
    """A COPY of a path that is not in the repository fails the docker build."""
    for relative in _stage_two_copies():
        assert (REPO_ROOT / relative).exists(), relative


def test_the_notes_fixture_is_not_in_the_image():
    """``tests/fixtures/bl15/notes/`` must not ship, by a parent directory or by name.

    Checked by coverage rather than by searching for the string, so a broader
    ``COPY tests/fixtures/bl15/`` — which would carry it in silently — fails here too.
    """
    copies = _stage_two_copies()
    assert not _covered(NOTES_FIXTURE, copies), copies
    assert not _covered(f"{NOTES_FIXTURE}/beamtime-notes.txt", copies), copies
    # NOTHING ELSE under the bl15 fixture tree either: only the corpora the import reads.
    bl15 = [c for c in copies if c.startswith("tests/fixtures/bl15")]
    assert sorted(bl15) == sorted(
        hist.ARCHIVE_FIXTURES[name]
        for name in SHIPPED_ARCHIVES
        if hist.ARCHIVE_FIXTURES[name].startswith("tests/fixtures/bl15")
    ), bl15


def _shipped_import_dirs() -> list:
    copies = _stage_two_copies()
    return [
        REPO_ROOT / relative
        for what, relative in _runtime_import_paths().items()
        if _covered(relative, copies)
    ]


def test_every_file_the_image_ships_for_imports_says_it_is_synthetic_the_way_the_comment_says():
    """M1: the Dockerfile comment names WHERE each file says so, and this checks exactly
    that — first line, or a SPEC ``#C SYNTHETIC FIXTURE`` header line, or (for a per-scan
    ``.dat`` export, which carries no marker of its own) the corpus's README row saying
    those exports are covered by it. A file matching none of the three fails."""
    readme_rows = (REPO_ROOT / "tests/fixtures/bl15/README.md").read_text("utf-8")
    shipped = _shipped_import_dirs()
    assert shipped, "nothing to check"
    checked = 0
    for root in shipped:
        relative = root.relative_to(REPO_ROOT).as_posix()
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            lines = path.read_text("utf-8", errors="replace").splitlines()
            checked += 1
            if lines and "SYNTHETIC" in lines[0]:
                continue
            if any(line.startswith("#C SYNTHETIC FIXTURE") for line in lines[:12]):
                continue
            if path.suffix == ".dat" and lines and lines[0].startswith("#S"):
                row = next(
                    (r for r in readme_rows.splitlines() if relative.removeprefix("tests/fixtures/bl15/") in r),
                    "",
                )
                assert "`.dat` exports carry no marker of their own" in row, path
                assert "covered by this row" in row, path
                continue
            raise AssertionError(f"{path.relative_to(REPO_ROOT)} declares nothing synthetic")
    assert checked > 20


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv(capabilities.INGESTION_ENV, raising=False)
    monkeypatch.delenv(capabilities.STAGING_ROOT_ENV, raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


SEMANTICS_KEY = "bl15_synthetic_semantics_corpus"
MINI_KEY = "bl15_synthetic_mini_corpus"


def test_the_multi_operator_corpus_is_offered_as_a_second_archive_and_is_the_default(client):
    """Locally (a full checkout) both archives are offered; the DEFAULT is the semantics
    corpus everywhere, so a picker opens on the archive the hosted image actually has."""
    listing = client.get("/api/imports").json()
    assert listing["available_archives"] == sorted([MINI_KEY, SEMANTICS_KEY])
    assert listing["available_fixtures"] == ["SYNTHETIC-bundle-a.txt", "SYNTHETIC-bundle-b.txt"]
    assert listing["default_archive"] == SEMANTICS_KEY
    view = client.post("/api/imports", json={"label": "d"}).json()["import"]
    assert view["default_archive"] == SEMANTICS_KEY


def test_without_the_mini_corpus_on_disk_only_the_semantics_corpus_is_offered(client, monkeypatch, tmp_path):
    """The IMAGE's case, reproduced: the mini corpus's path does not exist, so it is not
    offered — nothing names it, and the default is still the semantics corpus."""
    monkeypatch.setitem(hist.ARCHIVE_FIXTURES, MINI_KEY, str(tmp_path / "not-in-this-image"))
    listing = client.get("/api/imports").json()
    assert listing["available_archives"] == [SEMANTICS_KEY]
    assert set(listing["archive_display_names"]) == {SEMANTICS_KEY}
    assert listing["default_archive"] == SEMANTICS_KEY


def test_every_offered_archive_has_a_scientist_facing_name_and_not_its_id(client):
    """The picker shows a NAME. An id like ``bl15_synthetic_semantics_corpus`` is a
    handle for the API, and humanising it on the client produced "Bl15 synthetic
    semantics corpus" — a code with spaces in it."""
    for body in (
        client.get("/api/imports").json(),
        client.post("/api/imports", json={"label": "names"}).json()["import"],
    ):
        names = body["archive_display_names"]
        assert set(names) == set(body["available_archives"]), names
        for key, name in names.items():
            assert name and name != key and "_" not in name, (key, name)
            assert "synthetic" in name.lower(), (key, name)
            assert not re.search(r"\b(fixture|corpus)\b", name, re.I), (key, name)
    # EVERY committed archive has one, so a new archive cannot ship with its id as a label.
    assert set(hist.ARCHIVE_DISPLAY_NAMES) == set(hist.ARCHIVE_FIXTURES)


def test_a_staged_archive_carries_no_invented_name(client, tmp_path, monkeypatch):
    """A staged archive's only name is the one its file has; none is made up for it."""
    staging = tmp_path / "staging"
    (staging / "my_beamtime").mkdir(parents=True)
    (staging / "my_beamtime" / "readme.txt").write_text("# SYNTHETIC FIXTURE\n")
    monkeypatch.setenv(capabilities.INGESTION_ENV, capabilities.INGESTION_MODE_STAGING)
    monkeypatch.setenv(capabilities.STAGING_ROOT_ENV, str(staging))
    body = client.get("/api/imports").json()
    assert "staged:my_beamtime" in body["available_archives"]
    assert "staged:my_beamtime" not in body["archive_display_names"]


def test_the_semantics_corpus_parses_from_the_committed_path(client):
    """Registered means READABLE: a session over it walks nine acquisitions."""
    import_id = client.post("/api/imports", json={"label": "walk"}).json()["import"]["import_id"]
    added = client.post(
        f"/api/imports/{import_id}/sources",
        json={"kind": "archive", "fixture_name": SEMANTICS_KEY},
    )
    assert added.status_code == 200, added.text
    assert client.post(f"/api/imports/{import_id}/parse").status_code == 200
    digest = client.get(f"/api/imports/{import_id}").json()["import"]["corpus_digest"]
    assert digest["measurement_units"] == 9
    assert digest["run_candidate_units"] == 9


def test_the_image_smoke_test_checks_what_the_image_offers_and_what_it_must_not():
    """The PR smoke job is the ONLY check that runs against the built image, so its
    import step must expect every SHIPPED archive and example source — a new archive the
    Dockerfile forgot would otherwise pass every other check and ship empty again — and
    must refuse a WITHHELD archive being offered."""
    text = SMOKE.read_text("utf-8")
    assert "$BASE_URL/api/imports" in text
    step = text[text.index("# 8. Historical Import") : text.index("ALL SMOKE CHECKS PASSED")]
    for name in (*SHIPPED_ARCHIVES, *hist.fixture_names()):
        assert name in step, name
    for name in WITHHELD_ARCHIVES:
        assert f"for withheld in {name}" in step, name
