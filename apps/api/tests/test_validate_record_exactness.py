"""``POST /api/validate/record`` refuses a record ISAAC's exporter would refuse.

WHY THIS ROUTE SPECIFICALLY. It is the standalone validator — the surface an
operator points at a candidate file precisely to ask "is this good?". Before this
change it called ``validate_official`` and returned an unqualified ``ok: true``
for a record carrying a trailing newline in a pattern-gated field, because the
vendored schema's ``^...$`` gates accept one (Python's ``$`` also matches before a
trailing newline). ``export_draft`` refuses that record. So the one screen whose
whole job is to predict the verdict was the one place that disagreed with it.

THE CONTRACT THIS MODULE PINS, INCLUDING THE PART THAT DID NOT CHANGE:

* ``ok`` is now ``schema-valid AND exact``. This is the ONLY non-schema input
  ever allowed to move it.
* ``schema_ok`` is exactly ``validate_official``'s verdict, unchanged and still
  available, so nothing is lost for a caller that wants the pure schema answer.
* ``errors`` stays schema-only; exactness findings live in ``exactness_errors``.
  Merging them would attribute an ISAAC policy to the upstream schema.
* ``warnings`` remain ADVISORY and STILL cannot move ``ok`` — the pre-existing
  rule, re-pinned here because this change is the first thing ever to move ``ok``
  and the two must not be confused.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE = REPO_ROOT / "docs" / "samples" / "01JQZ0SYNTHXANESDEMO000000.json"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Same construction as ``test_run_api.py``'s — this route is workspace-free
    (read-only, writes nothing), but the app still needs a workspace to boot."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from conftest import tutorial_client
    from isaac_api.app import create_app

    return tutorial_client(create_app())


@pytest.fixture()
def record() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def _post(client, payload: dict):
    return client.post("/api/validate/record", content=json.dumps(payload))


def test_a_clean_record_passes_and_reports_both_verdicts(client, record):
    """Control. Without it, every refusal below could be an unrelated breakage."""
    body = _post(client, record).json()
    assert body["ok"] is True
    assert body["schema_ok"] is True
    assert body["errors"] == []
    assert body["exactness_errors"] == []


@pytest.mark.parametrize(
    "field,mutate",
    [
        ("record_id", lambda r: r.update(record_id=r["record_id"] + "\n")),
        ("tags.0", lambda r: r.update(tags=["campaign\n"])),
    ],
)
def test_a_trailing_newline_is_refused_while_the_schema_still_passes(
    client, record, field, mutate
):
    mutate(record)
    body = _post(client, record).json()

    # The premise. If this ever flips, the vendored schema was fixed and this
    # module should be re-read rather than patched.
    assert body["schema_ok"] is True, "premise lost: the schema now refuses this"
    assert body["errors"] == []

    assert body["ok"] is False, "the standalone validator passed a record export refuses"
    assert [e["path"] for e in body["exactness_errors"]] == [field]
    message = body["exactness_errors"][0]["message"]
    assert "U+000A LINE FEED" in message
    assert "\n" not in message, "a raw control byte was serialized into the response"


def test_the_response_never_carries_the_offending_raw_bytes(client, record):
    """A JSON response is rendered into a browser; the refused byte must not ride along.

    Asserted over the WHOLE serialized body, not just the message, because the
    value could leak through any field that echoes input.
    """
    record["tags"] = ["campaign\n"]
    raw = _post(client, record).text
    assert "campaign\\n" not in raw
    assert '"campaign\n' not in raw


def test_schema_errors_and_exactness_errors_stay_in_separate_lists(client, record):
    """A record that is BOTH schema-invalid and inexact reports each in its own place."""
    record["tags"] = ["campaign\n"]
    record["record_type"] = "not_a_real_type"

    body = _post(client, record).json()

    assert body["ok"] is False
    assert body["schema_ok"] is False
    assert [e["path"] for e in body["errors"]] == ["record_type"]
    assert [e["path"] for e in body["exactness_errors"]] == ["tags.0"]
    # The summary carries BOTH verdicts, each under its own heading.
    assert "record_type" in body["summary"]
    assert "U+000A" in body["summary"]
    assert "not a schema rule" in body["summary"]


def test_the_summary_never_contradicts_the_verdict(client, record):
    """THE DEFECT THIS CHANGE WOULD OTHERWISE HAVE INTRODUCED.

    The web Validator renders ``summary`` and does NOT (today) render
    ``exactness_errors``. With a schema-only summary, a refused record produced a
    FAIL badge above a pane reading "PASS — valid against official ISAAC schema
    v1.05" and an empty structured error list: a screen stating no reason for its
    own refusal, while appearing to assert the opposite verdict.

    So when ``ok`` is false, the summary must say why — and it must still report
    the schema verdict truthfully, because the record really is schema-valid.
    """
    record["tags"] = ["campaign\n"]
    body = _post(client, record).json()

    assert body["ok"] is False
    assert body["schema_ok"] is True
    assert body["errors"] == []
    summary = body["summary"]
    assert "PASS — valid against official ISAAC schema" in summary
    assert "not a schema rule" in summary
    assert "tags.0" in summary
    assert "U+000A LINE FEED" in summary


def test_a_clean_record_summary_is_the_bare_schema_summary(client, record):
    """The ordinary path is byte-for-byte unmoved."""
    body = _post(client, record).json()
    assert body["summary"] == "PASS — valid against official ISAAC schema v1.05"


def test_exactness_is_silent_where_the_schema_already_refuses(client, record):
    """One problem, one report. A trailing SPACE is a plain schema error."""
    record["tags"] = ["campaign "]
    body = _post(client, record).json()
    assert body["schema_ok"] is False
    assert body["ok"] is False
    assert [e["path"] for e in body["errors"]] == ["tags.0"]
    assert body["exactness_errors"] == []


def test_advisory_warnings_still_cannot_turn_a_pass_into_a_failure(client, record):
    """RE-PINS THE PRE-EXISTING RULE, which this change must not have loosened.

    ``measurement.series: []`` raises the advisory ``NO_MEASUREMENT_SERIES``. It
    is non-gating and must stay non-gating: ``ok`` may be moved by exactness and
    by nothing else.
    """
    record["measurement"] = copy.deepcopy(record["measurement"])
    record["measurement"]["series"] = []

    body = _post(client, record).json()

    assert body["warnings"], "premise lost: this no longer raises an advisory warning"
    assert body["schema_ok"] is True
    assert body["ok"] is True, "an advisory warning moved `ok` — it must never"
    assert body["exactness_errors"] == []
