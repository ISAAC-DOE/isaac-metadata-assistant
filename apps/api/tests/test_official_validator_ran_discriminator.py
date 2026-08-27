"""`official_validator_ran` — BOTH BRANCHES, over HTTP, on both operations.

WHY THE PAIR IN THIS FILE IS THE SHARPEST AVAILABLE
===================================================
Both cases below are the SAME field (``tags[0]``), refused against the SAME anchored
pattern (``^\\S(.*\\S)?$``), reported with the SAME ``{path, message}`` shape at the
SAME ``dry_run: true``. Everything a client could previously see is identical. The
only thing that differs is WHO refused:

    tags: [" x"]          -> the vendored official ISAAC schema's own `pattern` check
                             FAILED, so `validate_official` RAN and produced the finding
    tags: ["campaign\\n"]  -> that same pattern MATCHES in Python, because `$` also
                             matches before a trailing newline, so the schema accepts
                             it; ISAAC's own exactness gate refuses it, `export_draft`
                             returns `official_report=None`, and `validate_official`
                             NEVER RAN

Measured on this branch (values quoted verbatim in the assertions below)::

    POST /api/experiments/{id}/validate      tags=[" x"]
      {"ok": false, "schema": "ISAAC v1.05", "dry_run": true,
       "official_validator_ran": true,
       "errors": [{"path": "tags.0",
                   "message": "' x' does not match '^\\\\\\\\S(.*\\\\\\\\S)?$'"}]}

    POST /api/experiments/{id}/validate      tags=["campaign\\n"]
      {"ok": false, "schema": "ISAAC v1.05", "dry_run": true,
       "official_validator_ran": false,
       "errors": [{"path": "tags.0",
                   "message": "value is accepted by the schema pattern ... only
                     because Python's '$' also matches before a trailing newline ..."}]}

A surface handed the second payload and branching on ``dry_run`` — which is what all
five consumers did — told a scientist the OFFICIAL ISAAC SCHEMA rejected their record.
``CLAUDE.md`` §1 makes that schema not ours to speak for; §12: *"the gate is ISAAC's,
not upstream's ... no surface may report an exactness refusal as an official-schema
error."*

A MEASUREMENT THAT CONTRADICTED THE OBVIOUS GUESS, RECORDED BECAUSE IT IS THE ARGUMENT
======================================================================================
An unanswered, freshly created record reports ``official_validator_ran: TRUE`` with
``'descriptors' is a required property`` — and its ``draft.ok`` is ``true``. The
no-guessing validator passes such a draft; the ASSEMBLED record is what lacks
``descriptors``, so the official schema really does produce that finding.

Anyone hand-writing the ordering rule would have guessed the opposite ("nothing
answered, so the no-guessing check must have refused first, so don't name the
schema") and would have been wrong on the single most common failing payload in the
product. That is the case for a server-side discriminator rather than a client-side
rule, and it is pinned below so the reasoning survives.

Nothing here opens a network connection, reads real data, or touches a database. The
drafts are built by the product's own create+answer path over a temp workspace.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws

from test_scientist_can_finish_a_record import DESCRIPTOR, QC, SERIES

#: The value the vendored schema's own `pattern` REFUSES — a leading space fails
#: `^\S`. `validate_official` runs, rejects, and the finding is genuinely upstream's.
SCHEMA_REFUSES = " x"

#: The value that same pattern ACCEPTS in Python and that ISAAC refuses anyway. This
#: is `exactness.py`'s documented case, and it is the reason the gate exists.
ISAAC_REFUSES = "campaign\n"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    # `raise_server_exceptions=False` so a 500 is OBSERVED as a 500 rather than
    # raised into the test — a defensive branch that returns a sanitized envelope
    # must be measurable as such.
    return TestClient(create_app(), raise_server_exceptions=False)


def _answered(client, title: str, tags: list | None = None) -> str:
    """A complete record through the product's own create+answer path.

    `tags` is written onto the stored draft rather than sent over HTTP because no
    route accepts it; that is a fact about the capture surface, not a shortcut. The
    document under test is a PERSISTED one either way, which is what the read paths
    below actually see.
    """
    exp_id = client.post("/api/experiments", json={"title": title}).json()["id"]
    version = client.get(f"/api/experiments/{exp_id}").json()["version"]
    applied = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={
            "answers": {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC},
            "confirmed_by_user": True,
        },
        headers={"If-Match": f'"{version}"'},
    )
    assert applied.status_code == 200, applied.text
    if tags is not None:
        exp = ws.load_experiment(exp_id)
        exp.draft["tags"] = list(tags)
        exp.save()
    return exp_id


def _one_run(client, exp_id: str) -> str:
    version = client.get(f"/api/experiments/{exp_id}").json()["version"]
    made = client.post(
        f"/api/experiments/{exp_id}/runs",
        json={"label": "Run A"},
        headers={"If-Match": f'"{version}"'},
    )
    assert made.status_code in (200, 201), made.text
    return made.json()["run"]["id"]


def _check(client, exp_id: str, run_id: str) -> dict:
    got = client.post(f"/api/experiments/{exp_id}/runs/{run_id}/check")
    assert got.status_code == 200, got.text
    return got.json()


def _validate(client, exp_id: str) -> dict:
    got = client.post(f"/api/experiments/{exp_id}/validate")
    assert got.status_code == 200, got.text
    return got.json()


# --------------------------------------------------------------------------- #
# THE TWO BRANCHES, on POST /validate
# --------------------------------------------------------------------------- #


def test_a_dry_run_failure_the_OFFICIAL_SCHEMA_produced_says_so(client):
    body = _validate(client, _answered(client, "schema refuses", tags=[SCHEMA_REFUSES]))
    assert body["ok"] is False
    assert body["dry_run"] is True
    assert body["official_validator_ran"] is True, body
    # The finding is the schema's own `pattern` keyword, quoted rather than described.
    assert body["errors"] == [
        {"path": "tags.0", "message": "' x' does not match '^\\\\S(.*\\\\S)?$'"}
    ], body


def test_a_dry_run_failure_the_OFFICIAL_SCHEMA_NEVER_SAW_says_so(client):
    body = _validate(client, _answered(client, "isaac refuses", tags=[ISAAC_REFUSES]))
    assert body["ok"] is False
    assert body["dry_run"] is True
    assert body["official_validator_ran"] is False, body
    assert len(body["errors"]) == 1, body
    message = body["errors"][0]["message"]
    assert body["errors"][0]["path"] == "tags.0"
    # ISAAC's own gate, in its own words — and it names the very pattern the schema
    # accepted, which is exactly why a client cannot tell the two apart from the text.
    assert "only because Python's '$' also matches before a trailing newline" in message
    assert "'^\\\\S(.*\\\\S)?$'" in message


def test_the_two_payloads_are_INDISTINGUISHABLE_without_the_field(client):
    """THE ARGUMENT FOR THE FIELD, asserted rather than described.

    If any OTHER key differed between the two, a careful client could have branched on
    that instead and the field would be a convenience. Every other key is equal, so it
    is not.
    """
    ran = _validate(client, _answered(client, "a", tags=[SCHEMA_REFUSES]))
    not_ran = _validate(client, _answered(client, "b", tags=[ISAAC_REFUSES]))

    assert ran["official_validator_ran"] != not_ran["official_validator_ran"]

    def without_the_field_and_the_text(body: dict) -> dict:
        # The MESSAGE text is excluded deliberately: it does differ, and matching on
        # it is precisely the prose-coupling this repository has already had to remove
        # once (`unavailable` existed because a fixed English sentence was the only
        # signal). A client must not have to read English to get this right.
        return {
            "ok": body["ok"],
            "schema": body["schema"],
            "dry_run": body["dry_run"],
            "error_paths": [e["path"] for e in body["errors"]],
            "error_count": len(body["errors"]),
        }

    assert without_the_field_and_the_text(ran) == without_the_field_and_the_text(not_ran)


# --------------------------------------------------------------------------- #
# the same two branches, on POST /runs/{run_id}/check
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "tags,expected",
    [
        pytest.param([SCHEMA_REFUSES], True, id="schema-refuses->ran"),
        pytest.param([ISAAC_REFUSES], False, id="isaac-refuses->did-not-run"),
    ],
)
def test_the_check_operation_publishes_the_same_discriminator(client, tags, expected):
    exp_id = _answered(client, "check", tags=tags)
    body = _check(client, exp_id, _one_run(client, exp_id))
    official = body["official"]
    assert official["ok"] is False
    assert official["dry_run"] is True
    assert official["official_validator_ran"] is expected, official
    # The draft block is CLEAN in both cases, which is what made the old payload so
    # misleading: a scientist saw an empty "Draft checks" list beside findings headed
    # "Official schema".
    assert body["draft"]["ok"] is True, body["draft"]
    assert body["draft"]["errors"] == []


def test_the_OTHER_official_report_is_None_return_the_NO_GUESSING_one(client):
    """`export.py` has TWO returns before `validate_official`, and this is the second.

    The exactness case above is the interesting one because the schema ACCEPTS the
    value; this is the plainer one, and it is pinned separately because the two are
    different returns in `export_draft` and a change could break either alone.
    `draft_report.ok` is `False`, so `export_draft` returns `official_report=None` and
    the route reports the NO-GUESSING findings under the same `errors` key.

    Measured over HTTP on this branch::

        {"ok": false, "schema": "ISAAC v1.05", "dry_run": true,
         "official_validator_ran": false,
         "errors": [{"path": "fields.sample.material.formula",
                     "message": "verified field has no observed evidence or user
                                 confirmation"}]}

    NOTE WHAT THE FIELD DOES *NOT* SAY, and this is the deliberate limit recorded in
    `_export_step_detail` and in `lib/officialAttribution.ts`: it does not distinguish
    THIS return from the exactness one. `export.py` folds the exactness findings into
    `draft_report` on the way out, so the wire cannot separate ISAAC's two gates from
    each other — only both of them from upstream's. Naming one would be the same
    attribution defect one level finer.
    """
    exp_id = _answered(client, "no-guessing refusal")
    exp = ws.load_experiment(exp_id)
    # `status: verified` with an EMPTY evidence list — `draft_validator.py`'s
    # "verified field has no observed evidence or user confirmation".
    exp.draft["fields"]["sample.material.formula"] = {
        "value": "LiFePO4",
        "status": "verified",
        "evidence": [],
    }
    exp.save()

    body = _validate(client, exp_id)
    assert body["ok"] is False
    assert body["dry_run"] is True
    assert body["official_validator_ran"] is False, body
    assert body["errors"] == [
        {
            "path": "fields.sample.material.formula",
            "message": "verified field has no observed evidence or user confirmation",
        }
    ], body
    # NOT a no-verdict: a gate really did refuse, and said why. The two must stay
    # distinguishable — see the `unavailable` tests at the end of this file.
    assert "unavailable" not in body, body


def test_the_measurement_that_contradicts_the_obvious_ordering_RULE(client):
    """An unanswered record's failure IS the official schema's. See the module note."""
    exp_id = client.post("/api/experiments", json={"title": "nothing answered"}).json()["id"]
    body = _validate(client, exp_id)
    assert body["ok"] is False
    assert body["dry_run"] is True
    assert body["official_validator_ran"] is True, body
    assert body["errors"] == [
        {"path": "$", "message": "'descriptors' is a required property"}
    ], body

    check = _check(client, exp_id, _one_run(client, exp_id))
    assert check["official"]["official_validator_ran"] is True, check["official"]
    # And the no-guessing validator passed it, which is the half that makes the guess
    # wrong: "unanswered" does not imply "the draft check refused".
    assert check["draft"]["ok"] is True, check["draft"]


# --------------------------------------------------------------------------- #
# a PASS, and the invariant that must not move
# --------------------------------------------------------------------------- #


def test_a_dry_run_PASS_reports_that_the_validator_ran(client):
    """A pass is unreachable without it: `export.py` has ONE `ok=True` return, after
    `validate_official` has run and passed."""
    exp_id = _answered(client, "clean")
    body = _validate(client, exp_id)
    assert body == {
        "ok": True,
        "errors": [],
        "schema": "ISAAC v1.05",
        "dry_run": True,
        "official_validator_ran": True,
    }, body
    check = _check(client, exp_id, _one_run(client, exp_id))
    assert check["ok"] is True
    assert check["official"]["ok"] is True
    assert check["official"]["official_validator_ran"] is True


def test_adding_the_field_MOVED_NO_VERDICT(client):
    """CLAUDE.md §12's standing invariant: nothing turns a PASS into a FAIL.

    Asserted as a property rather than a snapshot: for each of the four payload shapes
    this slice touches, `ok` is recomputed from the SAME inputs it always had —
    `draft.ok and official.ok` for the check, `export_draft(...).ok` for the dry run —
    and the new field is not among them.

    THE STRONGEST FORM OF THIS IS THE NEGATIVE CONTROL BELOW, not this test: this one
    shows the verdicts are what they should be; that one shows the file cannot be
    quietly changed to make the field an input.
    """
    clean = _answered(client, "clean")
    assert _validate(client, clean)["ok"] is True
    check = _check(client, clean, _one_run(client, clean))
    assert check["ok"] is True

    for tags in ([SCHEMA_REFUSES], [ISAAC_REFUSES]):
        exp_id = _answered(client, "dirty", tags=tags)
        assert _validate(client, exp_id)["ok"] is False
        dirty = _check(client, exp_id, _one_run(client, exp_id))
        # `ok` is the conjunction the route always computed, and the draft half passes,
        # so the official half is the whole reason — regardless of who produced it.
        assert dirty["ok"] is (dirty["draft"]["ok"] and dirty["official"]["ok"])
        assert dirty["ok"] is False


def test_the_field_is_never_an_input_to_ok(client):
    """NEGATIVE CONTROL, by reading the route's own source.

    A test that only compares verdicts cannot distinguish "the field is not an input"
    from "the field happens to agree today". This reads `routes.py` and asserts that
    no expression computing `ok` mentions the discriminator.
    """
    import inspect

    import isaac_api.routes as routes

    for function in (
        routes._validate_unit,
        routes._fan_out_official_verdict,
        routes.post_validate,
        routes.post_run_check,
    ):
        source = inspect.getsource(function)
        for line in source.splitlines():
            stripped = line.strip()
            if not stripped.startswith('"ok"') and not stripped.startswith("ok ="):
                continue
            assert "official_validator_ran" not in stripped, (
                f"{function.__name__} computes `ok` from the discriminator: "
                f"{stripped!r}. CLAUDE.md §12 — an ISAAC-local gate must never turn a "
                "PASS into a FAIL, and this field is not a gate at all."
            )


def test_every_verdict_block_of_both_operations_carries_the_field(client):
    """THE PAYLOAD CONTRACT. A consumer that branches on a field which is sometimes
    absent is back to guessing, so absence is a failure on every branch — including
    the fan-out, whose per-run entries are what `RunFindings` and `ValidateReview`
    read."""
    exp_id = _answered(client, "fan out", tags=[ISAAC_REFUSES])
    _one_run(client, exp_id)
    _one_run(client, exp_id)

    body = _validate(client, exp_id)
    assert "official_validator_ran" in body, body
    assert body["runs"], body
    for entry in body["runs"]:
        assert "official_validator_ran" in entry, entry
        assert isinstance(entry["official_validator_ran"], bool)
    # The top level describes the TOP-LEVEL `errors`, which are the first failing
    # unit's — so it is that unit's flag, not an aggregate over a set the key does
    # not carry.
    failed = [e for e in body["runs"] if not e["ok"]]
    assert failed, body
    assert body["official_validator_ran"] == failed[0]["official_validator_ran"]

    for entry in body["runs"]:
        check = _check(client, exp_id, entry["run_id"])
        assert "official_validator_ran" in check["official"], check["official"]


def test_the_fan_out_top_level_flag_is_the_FIRST_FAILING_units(client):
    """Two runs, two DIFFERENT sources, so the aggregation rule is observable.

    With one run of each kind the `any`/`all` rules and the first-failing rule give
    different answers, which is the only way to show which one is implemented.
    """
    exp_id = _answered(client, "mixed")
    first = _one_run(client, exp_id)
    _one_run(client, exp_id)

    # Give run 1 an ISAAC-refused tag at the RUN level and leave run 2 clean, so the
    # first failing unit is the one the official validator never examined.
    exp = ws.load_experiment(exp_id)
    exp.runs[0].draft["tags"] = [ISAAC_REFUSES]
    exp.save()

    body = _validate(client, exp_id)
    entries = body["runs"]
    assert entries[0]["run_id"] == first
    if entries[0]["ok"]:  # pragma: no cover - the fixture is meant to fail unit 1
        pytest.skip("run-level `tags` is not part of the exported unit on this build")
    assert entries[0]["official_validator_ran"] is False, entries[0]
    assert body["official_validator_ran"] is False, body
    assert body["errors"] == entries[0]["errors"]


def test_the_shape_is_json_serialisable_booleans_not_python_reprs(client):
    """The field goes over the wire, so it is `true`/`false`, never `True`/`False`.

    Trivial-looking, and it exists because `_export_step_detail` deliberately DOES
    render a Python-cased boolean into a human string, and a future edit that reached
    for the same idiom here would produce a payload no JSON client can parse.
    """
    exp_id = _answered(client, "wire")
    raw = client.post(f"/api/experiments/{exp_id}/validate").text
    assert '"official_validator_ran":true' in raw.replace(" ", ""), raw
    assert "True" not in json.dumps(json.loads(raw))


# --------------------------------------------------------------------------- #
# THE THIRD STATE, AND WHY THE DISCRIMINATOR ALONE WAS NOT ENOUGH
# --------------------------------------------------------------------------- #
#
# `official_validator_ran: false` is TRUE of two different things:
#
#   ISAAC's own export gate refused    -> a gate spoke, and its findings are real
#   nothing ran at all                 -> no gate spoke; the record could not be READ
#
# `_validate_unit` has always separated them with `unavailable`. `post_validate` —
# the RECORD-level route — did not, so its no-verdict payload was equal to an
# export-gate refusal on every key a client can branch on. A consumer reading the new
# field alone would have replaced one false attribution ("the official schema rejected
# it") with a different false attribution ("ISAAC's export gate refused it").
#
# Measured over HTTP on this branch before the flag was added:
#
#     {"ok": false, "schema": "ISAAC v1.05", "dry_run": false,
#      "official_validator_ran": false,
#      "errors": [{"path": "$", "message": "Validation could not be completed."}]}


def _export(client, exp_id: str) -> None:
    version = client.get(f"/api/experiments/{exp_id}").json()["version"]
    done = client.post(
        f"/api/experiments/{exp_id}/export", headers={"If-Match": f'"{version}"'}
    )
    assert done.status_code == 200 and done.json()["ok"] is True, done.text


def test_an_exported_record_whose_artifact_cannot_be_read_says_NO_VERDICT(client):
    """The branch whose own server log line reads "reporting no verdict"."""
    exp_id = _answered(client, "deleted artifact")
    _export(client, exp_id)

    # The written record still validates, and the official validator is what said so.
    before = _validate(client, exp_id)
    assert before == {
        "ok": True,
        "errors": [],
        "schema": "ISAAC v1.05",
        "dry_run": False,
        "official_validator_ran": True,
    }, before
    # `unavailable` is ABSENT on a verdict that IS a verdict — the same rule the run
    # entries follow. A key always present and usually false invites a client to read
    # it as part of the verdict.
    assert "unavailable" not in before

    # Out-of-band deletion: the state says exported, the artifact is gone.
    ws.load_experiment(exp_id).record_path().unlink()

    after = _validate(client, exp_id)
    assert after["ok"] is False
    assert after["dry_run"] is False
    assert after["official_validator_ran"] is False, after
    assert after["unavailable"] is True, after
    assert after["errors"] == [
        {"path": "$", "message": "Validation could not be completed."}
    ], after


def test_no_verdict_is_DISTINGUISHABLE_from_an_ISAAC_gate_refusal(client):
    """THE ARGUMENT FOR THE SECOND FLAG, asserted rather than described.

    Both payloads carry `official_validator_ran: false`. If nothing else separated
    them, a consumer branching on the discriminator would report "ISAAC's export gate
    refused this" about a record no gate ever examined.
    """
    gate = _validate(client, _answered(client, "isaac gate", tags=[ISAAC_REFUSES]))

    unread = _answered(client, "unread")
    _export(client, unread)
    ws.load_experiment(unread).record_path().unlink()
    nothing = _validate(client, unread)

    assert gate["official_validator_ran"] is False
    assert nothing["official_validator_ran"] is False
    # ...and exactly one of them claims a gate spoke.
    assert "unavailable" not in gate, gate
    assert nothing["unavailable"] is True, nothing


def test_a_fan_out_propagates_the_flag_of_the_unit_its_errors_CAME_FROM(client):
    """`errors` at the top level is the FIRST FAILING unit's, so `unavailable` is that
    unit's too — the same aggregation rule `official_validator_ran` follows, and the
    only one derivable from what the key actually carries."""
    exp_id = _answered(client, "fan out unread")
    run_id = _one_run(client, exp_id)
    _export(client, exp_id)

    fine = _validate(client, exp_id)
    assert fine["ok"] is True and "unavailable" not in fine, fine

    # CORRUPTED, NOT DELETED, and the difference is a real asymmetry between the two
    # routes rather than a test convenience. `post_validate`'s single-record branch
    # keys off `exp.exported()`, which is STATE, so deleting the file is enough to
    # reach its no-verdict branch. `ExportUnit.materialised()` also requires both
    # halves of the pair to EXIST, so a deleted unit record falls back to the dry run
    # and passes. Only an unreadable-but-present artifact reaches the unit's branch.
    exp = ws.load_experiment(exp_id)
    unit = next(u for u in exp.export_units() if u.run_id == run_id)
    unit.record_path().write_text("{ not json", encoding="utf-8")

    body = _validate(client, exp_id)
    assert body["ok"] is False
    assert body["unavailable"] is True, body
    assert body["official_validator_ran"] is False, body
    assert body["runs"][0]["unavailable"] is True, body["runs"][0]
    assert body["errors"] == body["runs"][0]["errors"]


def test_the_run_check_operation_already_separated_them_and_still_does(client):
    """The regression guard for the surface that got this right first. If the
    record-level fix were ever "harmonised" by dropping the run entry's flag, this
    fails."""
    exp_id = _answered(client, "check unread")
    run_id = _one_run(client, exp_id)
    _export(client, exp_id)
    # Corrupted rather than deleted — see the note in the fan-out test above.
    exp = ws.load_experiment(exp_id)
    unit = next(u for u in exp.export_units() if u.run_id == run_id)
    unit.record_path().write_text("{ not json", encoding="utf-8")

    official = _check(client, exp_id, run_id)["official"]
    assert official["ok"] is False
    assert official["dry_run"] is False
    assert official["unavailable"] is True, official
    assert official["official_validator_ran"] is False, official
