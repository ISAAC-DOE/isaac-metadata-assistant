"""The public-evidence scanner must FAIL when it should, not merely pass when it does.

`docs/evidence/private-30-verification-2026-08-08.md` tells its readers the scanner was
tested against a deliberately poisoned control. Before this file existed that was an
unverifiable assertion in a public document -- exactly the shape of claim this project
polices. These tests are that assertion made checkable.

Two halves, and the second is the load-bearing one:

* the committed artifact passes, and
* a file carrying each forbidden thing FAILS.

A scanner with no failing test is a scanner nobody has proven scans anything. The
allowlist would be satisfied by an empty file.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCANNER = REPO_ROOT / "scripts" / "scan_public_evidence.py"
ARTIFACT_JSON = REPO_ROOT / "docs" / "evidence" / "private-30-verification-2026-08-08.json"
ARTIFACT_MD = REPO_ROOT / "docs" / "evidence" / "private-30-verification-2026-08-08.md"


def _scan(*paths: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCANNER), *[str(p) for p in paths]],
        capture_output=True,
        text=True,
    )


# --------------------------------------------------------------------------
# The committed artifact
# --------------------------------------------------------------------------

def test_the_committed_public_artifact_passes_its_own_scanner():
    """The exact files in the repository, not a copy built for the test."""
    result = _scan(ARTIFACT_JSON, ARTIFACT_MD)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_artifact_does_not_publish_the_unapproved_eighth_safeguard():
    """The approval enumerates SEVEN safeguard results. The endpoint serves eight.

    `parameterized_queries_only` shipped in the first draft and was caught in review.
    Pinned by name so it cannot drift back in on the "it was in the payload" reasoning
    that produced gate G3.
    """
    payload = json.loads(ARTIFACT_JSON.read_text(encoding="utf-8"))
    assert "parameterized_queries_only" not in payload
    assert "parameterized_queries_only" not in ARTIFACT_MD.read_text(encoding="utf-8")


def test_the_artifact_names_the_one_safeguard_that_is_asserted_not_measured():
    """`export_gating_unchanged` is a literal in the report builder, not a runtime probe.

    An earlier draft headed the safeguards table "all measured, none assumed", which was
    false for that row. If the correction is ever dropped, the artifact resumes overclaiming.
    """
    text = ARTIFACT_MD.read_text(encoding="utf-8")

    # The overclaiming phrase must not survive as a HEADING or a live claim. It is
    # allowed -- and wanted -- inside the retraction that names it as a past error,
    # so a naive substring check over the whole file is the wrong assertion. (That
    # is exactly how the first version of this test failed: against a correction.)
    heading = next(line for line in text.splitlines() if line.startswith("## 3."))
    assert "all measured" not in heading, heading
    assert "asserted" in heading, heading

    # The retraction itself must remain, with a citation a reader can open.
    assert "An earlier draft" in text
    assert "verification.py:1149" in text
    # And the row must be named, not merely alluded to.
    assert "export_gating_unchanged" in text


# --------------------------------------------------------------------------
# Poisoned controls -- each must FAIL
# --------------------------------------------------------------------------

POISONED_JSON: tuple[tuple[str, dict], ...] = (
    ("unapproved key", {"record_count": 30, "sample_title": "some title"}),
    ("record identifier", {"record_count": 30, "corpus_type": "01SYNTHXANESSEED0000000005"}),
    (
        "sha256 digest",
        {"record_count": 30, "corpus_type": "e80bb7a7d18f3fadc581601447d1b6a72e859e428a46871b27eb04ceb3e5e9a3"},
    ),
    ("exact timestamp", {"record_count": 30, "corpus_type": "2026-08-08T01:20:40Z"}),
    ("database name", {"record_count": 30, "corpus_type": "metadata_assistant"}),
    ("service topology", {"record_count": 30, "corpus_type": "isaac-psql-rw.isaac-psql.svc.cluster.local"}),
    ("connection variable", {"record_count": 30, "corpus_type": "PGPASSWORD is set"}),
    ("connection URI", {"record_count": 30, "corpus_type": "postgresql://host/db"}),
    ("ip address", {"record_count": 30, "corpus_type": "10.42.0.7"}),
    ("the unapproved eighth safeguard", {"record_count": 30, "parameterized_queries_only": "verified"}),
)


@pytest.mark.parametrize("label,payload", POISONED_JSON, ids=[p[0] for p in POISONED_JSON])
def test_a_poisoned_json_control_is_rejected(tmp_path: Path, label: str, payload: dict):
    poisoned = tmp_path / "poisoned.json"
    poisoned.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    result = _scan(poisoned)
    assert result.returncode == 1, f"{label} was NOT rejected:\n{result.stdout}"


POISONED_MARKDOWN: tuple[tuple[str, str], ...] = (
    ("record identifier in prose", "The record 01SYNTHXANESSEED0000000005 failed."),
    ("digest in prose", "sha256 e80bb7a7d18f3fadc581601447d1b6a72e859e428a46871b27eb04ceb3e5e9a3"),
    ("exact timestamp in prose", "Generated at 2026-08-08T01:20:40Z."),
    ("database name in prose", "Connected to metadata_assistant."),
    ("service topology in prose", "Host isaac-psql-rw.isaac-psql.svc.cluster.local"),
    ("credential variable in prose", "PGPASSWORD was read from the environment."),
    ("ip address in prose", "The pod reached 10.42.0.7 directly."),
)


@pytest.mark.parametrize("label,body", POISONED_MARKDOWN, ids=[p[0] for p in POISONED_MARKDOWN])
def test_a_poisoned_markdown_control_is_rejected(tmp_path: Path, label: str, body: str):
    """Markdown gets no key check, so the content patterns are its only defence.

    That asymmetry is disclosed in the artifact itself; these cases pin the half that
    does work.
    """
    poisoned = tmp_path / "poisoned.md"
    poisoned.write_text(f"# Evidence\n\n{body}\n", encoding="utf-8")
    result = _scan(poisoned)
    assert result.returncode == 1, f"{label} was NOT rejected:\n{result.stdout}"


def test_the_scanner_would_not_pass_an_empty_allowlist_by_accident(tmp_path: Path):
    """A negative control on the negative controls.

    If every poisoned case above passed for some unrelated reason -- a broken argv,
    a scanner that exits 0 unconditionally -- these tests would be vacuous. This one
    fails if the scanner cannot distinguish a clean file from a dirty one at all.
    """
    clean = tmp_path / "clean.json"
    clean.write_text(json.dumps({"record_count": 30, "corpus_type": "example"}), encoding="utf-8")
    assert _scan(clean).returncode == 0

    dirty = tmp_path / "dirty.json"
    dirty.write_text(json.dumps({"record_count": 30, "unapproved_key": 1}), encoding="utf-8")
    assert _scan(dirty).returncode == 1
