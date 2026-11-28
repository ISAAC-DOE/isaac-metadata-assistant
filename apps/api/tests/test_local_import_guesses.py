"""Bundle format 1.22.0: GUESSES FILL, AS YELLOW (slice 5a, DEC-100; ``docs/guesses-and-review-page-design-2026-11-28.md``
goals 1, 2, 5 and the potential-scale half of 6). SYNTHETIC data only: the committed multi-operator corpus (unmistakably
fake: year 2100, samples ZZ1..ZZ3) and the invented memo of ``test_local_import_fill_readings``, imported under a fake
folder name; the scientist is "SYN Quillfeather".

* an INFERRED Claude reading whose quote is checked against the file and whose scope reaches the target fills the value
  as a GUESS (value state ``guessed``, rule ``isaac.fill.reading_inferred.v1``): eligible, not asked, never green;
* never a sample's own label as its material, never the environment, never an unchecked quote, never where two readings
  disagree, never over any decision (a defer included), never over a conflict;
* ONE colour per value (``bundle.value_colour``): the per-rule table sits next to ``FILL_RULES`` and is pinned here;
* the end review lists guesses under their own heading with the quote; ``--accept`` turns them green;
* a guess composes as ``inferred`` with a derivation marked ``guess`` carrying the quote, file and line; the draft
  validator and ``isaac export`` pass it;
* the final check before an upload lists the yellow values and refuses without, or with a wrong, ``--guesses-ok``
  digest; the yes is one ``submit_with_guesses`` decision;
* a record holding applied potentials with no stated scale is blocked by the potential-scale question;
* a rule-set-3 bundle is STALE, and its next write re-derives it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R
from isaac_api.local_import import review as RV
from isaac_api.local_import import status as ST

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tests_support_records import REPO_ROOT, fake_upstream_env  # noqa: E402,F401
from test_local_import_fill_first import _add_group, _reject_local_starts  # noqa: E402
from test_local_import_fill_readings import (  # noqa: E402,F401
    BEAMLINE, ENV, FORM, MEMO, MEMO_LINES, NAME, RUN1, _answer_the_required, _apply, _derived, _finding, _id,
    _readings_of, _targets, _value, _vendored_schema_basis, bdir, grouped, imported, src, ungrouped)

WHO = "SYN Quillfeather"
BY = dict(by=WHO, orcid=None)
INFERRED = "inferred"


def _guess(o: dict) -> bool:
    return o.get("value_state") == B.STATE_GUESSED and (o.get("fill") or {}).get("rule_id") == \
        B.FILL_READING_INFERRED_RULE_ID


def _refusal(b: dict, o: dict) -> str | None:
    kind = "candidate" if "candidate_id" in o else "missing_value"
    return B.guess_refusal(b, kind, o, B.fill_context(b))


def _portal(record):
    return {"status": "ran", "result": {"valid": True, "errors": [], "warnings": []}, "outcome": "publish", "held": [],
            "verdict": "publish"}


# --- the registration --------------------------------------------------------------------------------------------------


def test_the_state_the_rule_and_the_decision_are_registered_at_1_22_0_rule_set_4():
    assert B.FORMAT_VERSION == "1.22.0" == B._VERSION_ORDER[-1] and B.FILL_RULE_SET == 4
    assert B.STATE_GUESSED == "guessed" and B.STATE_GUESSED in B.VALUE_STATES and B.STATE_GUESSED not in B.PARSER_STATES
    assert B.FILL_STATES == {B.STATE_FILLED, B.STATE_GUESSED}
    assert B.GUESS_RULES == {B.FILL_READING_INFERRED_RULE_ID} <= set(B.FILL_RULES)
    text = B.FILL_RULES[B.FILL_READING_INFERRED_RULE_ID]
    assert text.startswith(B.FILL_READING_INFERRED_RULE_ID + ": ") and ". " not in text
    schema = B.bundle_schema()
    assert "guessed" in schema["$defs"]["value_state"]["enum"] and "guessed" not in schema["$defs"]["extracted_state"]["enum"]
    assert set(schema["$defs"]["fill"]["properties"]["rule_id"]["enum"]) == set(B.FILL_RULES)
    assert B.SUBMIT_WITH_GUESSES_DECISION in schema["$defs"]["scientist_decision"]["properties"]["decision"]["enum"]
    assert B.SUBMIT_WITH_GUESSES_DECISION in B.DECISIONS_BY_KIND["experiment"]
    assert "1.22.0" in schema["properties"]["format_version"]["enum"] and "guess" in B.CHANGES_ADDED_IN["1.22.0"]
    # only derive_value_state gives it, and never from a parser state of its own
    assert B.derive_value_state(B.STATE_MISSING, decision=None, interpreted=True,
                                fill_rule=B.FILL_READING_INFERRED_RULE_ID) == B.STATE_GUESSED
    assert B.derive_value_state(B.STATE_MISSING, decision=None, interpreted=True, fill_rule=B.FILL_READING_INFERRED_RULE_ID,
                                reviewed=True) == B.STATE_SCIENTIST_CONFIRMED
    assert B.derive_value_state(B.STATE_CONFLICTING, decision=None, interpreted=True,
                                fill_rule=B.FILL_READING_INFERRED_RULE_ID) == B.STATE_CONFLICTING
    with pytest.raises(ValueError):
        B.derive_value_state(B.STATE_GUESSED, decision=None, interpreted=False)


# --- the colour table (goal 2) -----------------------------------------------------------------------------------------


def test_every_rule_has_exactly_one_colour_and_the_table_is_the_owners():
    assert set(B.FILL_RULE_COLOURS) == set(B.FILL_RULES)
    green = {B.FILL_PARSER_EXACT_RULE_ID, B.FILL_READING_STATED_RULE_ID, B.FILL_FACILITY_RULE_ID, B.FILL_DOMAIN_RULE_ID,
             B.FILL_STORED_CONVENTION_RULE_ID}
    yellow = {B.FILL_READING_INFERRED_RULE_ID, B.FILL_GROUP_RULE_ID, B.FILL_ORGANIZATION_RULE_ID,
              B.FILL_ENVIRONMENT_RULE_ID, B.FILL_SETPOINT_NAME_RULE_ID, B.FILL_CONTROL_MODE_RULE_ID}
    assert {r for r, c in B.FILL_RULE_COLOURS.items() if c == B.COLOUR_GREEN} == green
    assert {r for r, c in B.FILL_RULE_COLOURS.items() if c == B.COLOUR_YELLOW} == yellow
    assert B.DEDUCTION_RULES == yellow - B.GUESS_RULES
    assert B.COLOUR_RED not in B.FILL_RULE_COLOURS.values()  # red is never a rule's: it is a needed value no one knows


@pytest.mark.parametrize("state, rule, needed, colour", [
    (B.STATE_SCIENTIST_CONFIRMED, None, True, "green"),
    (B.STATE_SCIENTIST_CONFIRMED, B.FILL_READING_INFERRED_RULE_ID, True, "green"),  # a reviewed guess
    (B.STATE_FILLED, B.FILL_PARSER_EXACT_RULE_ID, True, "green"),
    (B.STATE_FILLED, B.FILL_READING_STATED_RULE_ID, True, "green"),
    (B.STATE_FILLED, B.FILL_FACILITY_RULE_ID, True, "green"),
    (B.STATE_FILLED, B.FILL_DOMAIN_RULE_ID, True, "green"),
    (B.STATE_FILLED, B.FILL_STORED_CONVENTION_RULE_ID, True, "green"),
    (B.STATE_FILLED, B.FILL_GROUP_RULE_ID, True, "yellow"),
    (B.STATE_FILLED, B.FILL_ORGANIZATION_RULE_ID, True, "yellow"),
    (B.STATE_FILLED, B.FILL_ENVIRONMENT_RULE_ID, True, "yellow"),
    (B.STATE_FILLED, "isaac.fill.made_up.v9", True, "yellow"),  # an unknown rule is never green
    (B.STATE_GUESSED, B.FILL_READING_INFERRED_RULE_ID, True, "yellow"),
    (B.STATE_GUESSED, B.FILL_PARSER_EXACT_RULE_ID, True, "yellow"),  # a guess is never green, whatever it names
    (B.STATE_MISSING, None, True, "red"),
    (B.STATE_CONFLICTING, None, True, "red"),
    (B.STATE_NEEDS_REVIEW, None, True, "red"),  # a deferred answer leaves it here
    (B.STATE_MISSING, None, False, None),
])
def test_value_colour(state, rule, needed, colour):
    assert B.value_colour(state, rule, needed=needed) == colour


def test_the_colour_of_a_field_as_a_draft_keeps_it():
    deriv = {"source_type": "derivation", "rule": B.FILL_READING_INFERRED_RULE_ID, "guess": True, "value_id": "miss-1"}
    seen = {"source_type": "document", "quote": "x"}
    review = {"source_type": "user_confirmation", "basis": B.REVIEW_BASIS, "target_id": "miss-1"}
    assert B.evidence_colour([seen, deriv]) == "yellow"
    assert B.evidence_colour([seen, deriv, review]) == "green"
    other = {**deriv, "value_id": "miss-2"}
    assert B.evidence_colour([seen, deriv, other, review]) == "yellow"  # a merged field: one guess still unconfirmed
    assert B.evidence_colour([seen, {"source_type": "derivation", "rule": B.FILL_PARSER_EXACT_RULE_ID}]) == "green"
    assert B.evidence_colour([seen, {"source_type": "derivation", "rule": B.FILL_GROUP_RULE_ID}]) == "yellow"
    assert B.evidence_colour([{"source_type": "user_confirmation"}]) == "green" and B.evidence_colour([]) is None
    # review C1: an ANSWER beside an unconfirmed guess never green-washes it (the answer names its own value)
    answer = {"source_type": "user_confirmation", "target_id": "miss-9"}
    assert B.evidence_colour([seen, answer, deriv]) == "yellow"
    assert B.evidence_colour([seen, {"source_type": "user_confirmation"}, deriv]) == "yellow"  # no target_id: no green
    # review M3: a derivation no rule registers is yellow; the DEC-76 absence record is green, by its mark only
    assert B.evidence_colour([seen, {"source_type": "derivation", "rule": "some free text"}]) == "yellow"
    assert B.evidence_colour([{"source_type": "derivation", "rule": "DEC-76: ...",
                               B.ABSENCE_DERIVATION_KEY: True}]) == "green"
    fields = {"a": {"value": 1, "status": "verified", "evidence": [seen, answer]},
              "b": {"value": 2, "status": "inferred", "evidence": [seen, deriv]},
              "e": {"value": None, "status": "missing", "evidence": []}}
    report = {"missing_required": [{"path": "c"}], "disagreements": [{"path": "d"}]}
    colours = B.record_field_colours(fields, report)
    assert colours == {"a": "green", "b": "yellow", "c": "red", "d": "red"}
    assert R.field_colours({"field_colours": colours}) == colours
    assert R.colour_counts([{"field_colours": colours}] * 2) == B.count_colours([colours] * 2) == {
        "green": 2, "yellow": 2, "red": 4}


# --- the guess, and every refusal (goal 1) -----------------------------------------------------------------------------


def test_an_inferred_checked_reading_fills_as_a_guess_and_is_not_asked(bdir, src):
    before = _value(M.load(bdir), FORM)
    assert before["value_id"] in _targets(Q.consolidate(M.load(bdir)))  # asked before the reading
    done = _apply(bdir, src, _finding(FORM, "pellet", 9, strength=INFERRED))
    assert done["quote_check"]["failed"] == 0
    b = M.load(bdir)
    m = _value(b, FORM)
    assert _guess(m) and m["fill"]["value"] == "pellet" and m["eligibility_for_official_record"]["eligible"]
    assert "Guessed" in m["eligibility_for_official_record"]["reason"]
    [i] = _readings_of(b, m)
    assert m["fill"]["readings"] == [i["interpretation_id"]] and i["strength"] == INFERRED
    assert B.is_yellow(m) and B.value_colour(m["value_state"], m["fill"]["rule_id"]) == "yellow"
    assert b["counts"]["guessed"] == 1 and B.validate_bundle(b) == []
    assert m["value_id"] not in _targets(Q.consolidate(b))  # left out of the questions like a fill
    assert m["value_id"] in _targets(Q.consolidate(b, include_answered=True))  # ...and still addressable


def test_a_label_is_never_guessed_as_its_material(bdir, src):
    """The slice 2 replay's class: a sample's own code ("ZZ1") read as its material."""
    _apply(bdir, src, _finding(NAME, "ZZ1", 12, strength=INFERRED))
    b = M.load(bdir)
    c = _value(b, NAME)
    assert not _guess(c) and "fill" not in c
    assert _refusal(b, c) == "a sample's own label or code is not its material"


def test_the_environment_is_never_guessed(bdir, src):
    """The other replay class: "in situ" inferred from lines that state no environment. The convention question
    settles the environment."""
    _apply(bdir, src, _finding(ENV, "in_situ", 33, strength=INFERRED))
    b = M.load(bdir)
    m = _value(b, ENV)
    assert not _guess(m) and "fill" not in m and B.guess_never_fills(ENV)
    assert _refusal(b, m).startswith("a field no guess fills")


def test_a_quote_that_is_not_in_the_cited_file_never_guesses(bdir, src):
    done = _apply(bdir, src, _finding(FORM, "pellet", 9, quote="every synthetic sample was a powder (NOT IN THE MEMO)",
                                      strength=INFERRED))
    assert done["quote_check"]["failed"] == 1
    b = M.load(bdir)
    m = _value(b, FORM)
    assert not _guess(m) and "fill" not in m and _refusal(b, m) == "no checked inferred reading"


def test_two_inferred_readings_that_disagree_guess_nothing(bdir, src):
    _apply(bdir, src, _finding(FORM, "pellet", 9, strength=INFERRED), _finding(FORM, "film", 38, strength=INFERRED))
    b = M.load(bdir)
    m = _value(b, FORM)
    assert not _guess(m) and "fill" not in m and _refusal(b, m) == "readings of this value disagree"
    assert m["value_id"] in _targets(Q.consolidate(b))  # it stays asked


def test_a_value_off_the_fields_list_is_never_guessed(bdir, src, monkeypatch):
    _apply(bdir, src, _finding(FORM, "pellet", 9, strength=INFERRED))
    b = M.load(bdir)
    assert _guess(_value(b, FORM))
    real = B.allowed_values
    monkeypatch.setattr(B, "allowed_values", lambda path: ["film"] if path == FORM else real(path))  # pellet off the list
    m = _value(_derived(b), FORM)
    assert not _guess(m) and _refusal(b, m).startswith("the field does not take the value")


@pytest.mark.parametrize("decision", ["defer", "correct", "reject"])
def test_any_decision_beats_a_guess(bdir, src, decision):
    _apply(bdir, src, _finding(FORM, "pellet", 9, strength=INFERRED))
    m = _value(M.load(bdir), FORM)
    assert _guess(m)
    M.decide(bdir, target_ids=[m["value_id"]], decision=decision, value="film" if decision == "correct" else None, **BY)
    after = _value(M.load(bdir), FORM)
    assert after["value_state"] != B.STATE_GUESSED and "fill" not in after


def test_a_guess_never_fills_over_a_conflict(bdir, src):
    """Where the sources disagree about the field for the run, nothing is guessed: the scientist is asked. (The synthetic
    corpus's conflicts are about start times and files, so one is pointed at the form IN MEMORY.)"""
    _apply(bdir, src, _finding(FORM, "pellet", 9, strength=INFERRED))
    b = M.load(bdir)
    assert _guess(_value(b, FORM))
    c = next(c for c in b["candidates"] if c["extracted_state"] == B.STATE_CONFLICTING and c["run_id"] == "run-001")
    c["target_field_path"] = FORM  # the sources now disagree about run-001's form
    m = _value(_derived(b), FORM)
    assert not _guess(m) and "fill" not in m
    assert _refusal(b, m).startswith("another reading, a file value or a disagreement of the sources")
    # and a conflict itself is never lifted, by any rule
    assert B.derive_value_state(B.STATE_CONFLICTING, decision=None, interpreted=True,
                                fill_rule=B.FILL_READING_INFERRED_RULE_ID) == B.STATE_CONFLICTING


def test_a_stated_reading_that_ties_fills_green_and_no_guess_is_made_beside_it(bdir, src):
    _apply(bdir, src, _finding(BEAMLINE, "SYN-BL9", 8, runs=()), _finding(BEAMLINE, "SYN-BL9", 8, runs=(),
                                                                          strength=INFERRED))
    m = _value(M.load(bdir), BEAMLINE)
    assert m["value_state"] == B.STATE_FILLED and m["fill"]["rule_id"] == B.FILL_READING_STATED_RULE_ID
    assert B.value_colour(m["value_state"], m["fill"]["rule_id"]) == "green"


def test_the_validator_re_derives_a_guess_and_refuses_one_it_cannot(bdir, src):
    _apply(bdir, src, _finding(FORM, "pellet", 9, strength=INFERRED))
    b = M.load(bdir)
    m = _value(b, FORM)
    m["value_state"] = B.STATE_FILLED  # a guess dressed as a green fill
    assert any("only guessed is supported" in e for e in B.validate_bundle(b)), B.validate_bundle(b)
    b = M.load(bdir)
    other = _value(b, "sample.material.form") if any(
        x["target_field_path"] == "sample.material.form" for x in b["missing_values"]) else None
    victim = other or _value(b, "context.temperature_K")
    victim.update(value_state=B.STATE_GUESSED, fill={"rule_id": B.FILL_READING_INFERRED_RULE_ID, "value": 1})
    assert any("guessed" in e for e in B.validate_bundle(b))


def test_a_rule_set_3_bundle_is_stale_and_its_next_write_re_derives_the_guess(bdir, src, monkeypatch, capsys):
    _apply(bdir, src, _finding(FORM, "pellet", 9, strength=INFERRED))
    b = json.loads((bdir / "bundle.json").read_text())
    with monkeypatch.context() as mp:  # what rule set 3 derived: no guess
        mp.setattr(B, "reading_inferred_fill_for", lambda *a, **k: None)
        B.apply_derivations(b)
    b["fill_rule_set"], b["format_version"] = 3, "1.21.0"
    b.get("counts", {}).pop("guessed", None)
    (bdir / "bundle.json").write_text(json.dumps(b))
    stale = B.stale_eligibility(b)
    assert any(s["id"] == _value(b, FORM)["value_id"] and s.get("fill_moved") for s in stale)
    capsys.readouterr()
    assert cli.main(["bundle", "check", str(bdir)]) == 1 and capsys.readouterr().out.startswith("STALE:")
    M.record_consent(bdir, by=WHO)
    saved = json.loads((bdir / "bundle.json").read_text())
    assert saved["fill_rule_set"] == 4 and saved["format_version"] == "1.22.0" and B.validate_bundle(saved) == []
    assert _guess(_value(saved, FORM))
    assert _value(saved, FORM)["value_id"] in {r["id"] for r in saved["eligibility_rederived"]}


# --- composition, the review, the final check ---------------------------------------------------------------------------


@pytest.fixture()
def built(ungrouped, src) -> Path:
    """One confirmed record group whose every required value is answered or filled, and the beamline GUESSED from an
    inferred reading for the whole beamtime; records built."""
    _add_group(ungrouped)
    _answer_the_required(ungrouped)
    _reject_local_starts(ungrouped, "run-001")
    _answer_scale(ungrouped, "run-001")  # the run's set-point (100mV in its name) goes in beside its scale
    _apply(ungrouped, src, _finding(BEAMLINE, "SYN-BL9", 8, runs=(), strength=INFERRED))
    m = _value(M.load(ungrouped), BEAMLINE)
    assert _guess(m), m
    R.build_records(ungrouped)
    return ungrouped


SCALE = "context.electrochemistry.potential_scale"
POT = B.POTENTIAL_SETPOINT_PATH


def _answer_scale(bdir: Path, run_id: str, value: str = "RHE") -> None:
    m = next(m for m in M.load(bdir)["missing_values"] if m["target_field_path"] == SCALE and m["run_id"] == run_id)
    M.decide(bdir, target_ids=[m["value_id"]], decision="correct", value=value, **BY)


def test_a_guess_composes_as_inferred_marked_a_guess_and_exports(built, fake_upstream_env):
    from isaac_records.draft_validator import validate_draft
    from isaac_records.export import export_draft

    draft = json.loads((built / "drafts" / "g1.draft.json").read_text())
    comp = json.loads((built / "drafts" / "g1.composition.json").read_text())
    env = draft["fields"][BEAMLINE]
    assert env["value"] == "SYN-BL9" and env["status"] == "inferred"
    [d] = [e for e in env["evidence"] if e.get("source_type") == "derivation"]
    assert d["rule"] == B.FILL_READING_INFERRED_RULE_ID and d["guess"] is True and d["basis"] == R.GUESS_BASIS
    assert d["quote"] == MEMO_LINES[8] and d["source_file"] == MEMO and d["locator"] == "line 8"
    assert not any(e["source_type"] == "user_confirmation" for e in env["evidence"])
    assert B.evidence_colour(env["evidence"]) == "yellow" and R.field_colours(comp)[BEAMLINE] == "yellow"
    report = validate_draft(draft)
    assert report.ok, report.errors
    result = export_draft(draft, REPO_ROOT)  # export refuses needs_confirmation, never inferred
    assert result.ok, (result.draft_report.errors, result.official_report and result.official_report.errors)
    assert result.record["system"]["facility"]["beamline"] == "SYN-BL9"
    assert any(e.get("guess") is True for e in result.sidecar["evidence"][BEAMLINE])  # the sidecar keeps the mark
    assert "guess" not in json.dumps(result.record)  # the official record carries no mark


def test_the_review_lists_guesses_apart_with_the_quote_and_accept_turns_them_green(built):
    out = RV.review(built)
    assert out["values_by_kind"]["guess"] == 1
    [row] = [v for f in out["fields"] if f["path"] == BEAMLINE for v in f["values"]]
    assert row["kind"] == "guess" and row["colour"] == "yellow" and row["rule_id"] == B.FILL_READING_INFERRED_RULE_ID
    assert row["witness"]["quote"] == MEMO_LINES[8] and row["witness"]["by"] == "a Claude reading of the files"
    text = RV.render(out)
    heading = "Guesses — the skill's best reading, please check:"
    assert heading in text and MEMO_LINES[8] in text
    read = "Read from your files:"
    assert read in text and text.index(heading) < text.index(read)
    guesses = text[text.index(heading):text.index(read)]
    assert "SYN-BL9" in guesses and "experimental" not in guesses  # the domain (green) is not among the guesses
    done = RV.accept(built, by=WHO, apply=True, listing=out["listing"])
    assert done["recorded"] and done["guesses"] == 1 and "1 of them guesses" in done["statement"]
    b = M.load(built)
    m = _value(b, BEAMLINE)
    assert m["value_state"] == B.STATE_SCIENTIST_CONFIRMED and m["review"]["basis"] == B.REVIEW_BASIS
    assert B.value_colour(m["value_state"], m["fill"]["rule_id"]) == "green" and B.validate_bundle(b) == []
    R.build_records(built)
    env = json.loads((built / "drafts" / "g1.draft.json").read_text())["fields"][BEAMLINE]
    assert env["status"] == "verified" and B.evidence_colour(env["evidence"]) == "green"


def test_status_says_one_line_of_colours_and_counts_the_guesses(built):
    M.record_consent(built, by=WHO)
    facts = ST.status(built)
    f = facts["facts"]
    assert f["values_guessed"] == 1 and f["colours"]["yellow"] >= 1 and f["colours"]["records"] == 1
    [line] = [x for x in facts["lines"] if x.startswith("Values in the 1 record(s) as they stand:")]
    assert f"{f['colours']['green']} green" in line and f"{f['colours']['yellow']} yellow" in line
    assert f"{f['colours']['red']} red" in line
    assert "review" in f["next"]  # the built records wait for the end review


def _exported(bdir: Path) -> Path:
    out = bdir.parent / "records"
    res = R.export_records(bdir, out, run_portal=_portal)
    assert not res["refused"] and res["exported"], res["refused"]
    return out


def _upload(out: Path, *args: str) -> list[str]:
    return ["bundle", "upload", str(out), "--dry-run", *args]


def test_the_final_check_refuses_without_or_with_a_wrong_digest_and_records_the_yes(built, capsys, fake_upstream_env):
    out = _exported(built)
    capsys.readouterr()
    assert cli.main(_upload(out)) == 1
    said = json.loads(capsys.readouterr().out)
    check = said["final_check"]
    # the beamline is a guess; the run's set-point (from its file name) and its control mode are deductions
    assert said["sent"] is False and (check["values"], check["guesses"], check["deductions"]) == (3, 1, 2)
    assert said["question"] == ("These 3 values are my guesses from your files or worked out by a rule (1 guess, 2 "
                                "worked out by a rule). Send them as they are, or check them first?")
    assert check["items"][0]["kind"] == "guess"  # the guesses first
    guess = check["items"][0]
    assert (guess["path"], guess["value"], guess["rule_id"], guess["guess"], guess["records"]) == (
        BEAMLINE, "SYN-BL9", B.FILL_READING_INFERRED_RULE_ID, True, 1)
    assert guess["quote"] == MEMO_LINES[8] and "not confirmed by you" in check["statement"]
    assert {(i["path"], i["rule_id"]) for i in check["items"][1:]} == {
        (POT, B.FILL_SETPOINT_NAME_RULE_ID), (B.CONTROL_MODE_PATH, B.FILL_CONTROL_MODE_RULE_ID)}
    assert RV.PORTAL_COPY_NOTE in check["statement"]  # the record has no note to carry the marks
    assert "--guesses-ok " + check["digest"] in said["final_check_words"]
    assert RV.UPLOAD_NOTE in said["statement"] and "portal does not run this check" in RV.UPLOAD_NOTE  # review I4
    # review I4: the export index flags the record that holds yellow values (never an official field)
    [row] = json.loads((out / R.EXPORT_INDEX).read_text())["records"]
    assert row["unconfirmed_values"] == {"count": 3, "paths": sorted([BEAMLINE, POT, B.CONTROL_MODE_PATH])}
    # a wrong digest is refused; so is a yes with no bundle to record it in
    assert cli.main(_upload(out, "--bundle", str(built), "--guesses-ok", "0" * 16, "--by", WHO)) == 1
    assert "changed since you were shown them" in capsys.readouterr().err
    assert cli.main(_upload(out, "--guesses-ok", check["digest"], "--by", WHO)) == 2
    capsys.readouterr()
    assert not B.submit_decisions(M.load(built))
    # the yes, bound to exactly that list
    assert cli.main(_upload(out, "--bundle", str(built), "--guesses-ok", check["digest"], "--by", WHO)) == 0
    sent = json.loads(capsys.readouterr().out)
    assert sent["final_check"]["recorded"] is True and sent["records"] and sent["upload_note"] == RV.UPLOAD_NOTE
    b = M.load(built)
    [d] = B.submit_decisions(b)
    assert d["decided_by"]["name"] == WHO and d["decided_utc"] and d[B.SUBMIT_DIGEST_KEY] == check["digest"]
    assert d[B.SUBMIT_ITEMS_KEY][0]["path"] == BEAMLINE and d[B.SUBMIT_ITEMS_KEY][0]["guess"] is True
    assert d[B.SUBMIT_RECORDS_KEY] == check["records"] and d["value"] is None
    assert B.validate_bundle(b) == []
    assert _guess(_value(b, BEAMLINE))  # the yes confirms nothing: it stays a guess
    # review M2: the same yes to the same list is recorded once
    assert cli.main(_upload(out, "--bundle", str(built), "--guesses-ok", check["digest"], "--by", WHO)) == 0
    again = json.loads(capsys.readouterr().out)["final_check"]
    assert again["recorded"] is False and again["already_recorded"] and len(B.submit_decisions(M.load(built))) == 1


def test_one_value_is_said_in_the_singular():
    check = {"values": 1, "guesses": 1, "deductions": 0, "unknown": 0}
    assert RV.final_check_question(check) == ("This value is my guess from your files or worked out by a rule (1 guess, "
                                              "0 worked out by a rule). Send it as it is, or check it first?")
    assert RV.values_sentence(1, {"guess": 1}).startswith("1 value is my guess")


def test_a_record_with_no_readable_evidence_file_is_never_green(built, capsys, fake_upstream_env):
    """Review I1: a record whose sidecar is gone would still be sent: it is listed and needs the yes."""
    out = _exported(built)
    RV.accept(built, by=WHO, apply=True, listing=RV.review(built)["listing"])  # nothing yellow left in the bundle
    R.build_records(built)
    out = _exported(built)
    [sidecar] = list(out.glob("*.evidence.json"))
    sidecar.unlink()
    check = RV.final_check(out)
    assert check["values"] == 1 and check["unknown"] == 1 and check["items"][0]["kind"] == "unknown"
    capsys.readouterr()
    assert cli.main(_upload(out)) == 1 and json.loads(capsys.readouterr().out)["sent"] is False


def test_a_yes_is_refused_when_the_index_names_no_bundle_or_another(built, capsys, fake_upstream_env):
    """Review I2: with the export index gone, a yes would be written into whatever bundle was named."""
    out = _exported(built)
    digest = RV.final_check(out)["digest"]
    (out / R.EXPORT_INDEX).unlink()
    with pytest.raises(RV.ReviewRefused, match="does not say these records come from this bundle"):
        RV.accept_guesses(out, built, digest=RV.final_check(out)["digest"], by=WHO)
    assert not B.submit_decisions(M.load(built)) and digest


def test_records_older_than_the_answers_are_refused(built, capsys, fake_upstream_env):
    """Review I3: a guess corrected after the export still sits in the exported record; the yes is refused until the
    records are built and exported again."""
    out = _exported(built)
    digest = RV.final_check(out)["digest"]
    M.decide(built, target_ids=[_value(M.load(built), BEAMLINE)["value_id"]], decision="correct", value="SYN-BL7", **BY)
    check = RV.final_check(out, built)
    assert check["stale_records"] and check["digest"] == digest  # the export alone still lists the old guess
    with pytest.raises(RV.ReviewRefused, match="older than your answers"):
        RV.accept_guesses(out, built, digest=digest, by=WHO)
    R.build_records(built)
    out = _exported(built)
    fresh = RV.final_check(out, built)
    assert not fresh["stale_records"] and BEAMLINE not in {i["path"] for i in fresh["items"]}


def test_an_answer_pooled_with_a_guess_stays_yellow_in_status_and_in_the_final_check(ungrouped, src, fake_upstream_env,
                                                                                    capsys):
    """Review C1: group g1 of run-001 and run-002; run-001's form ANSWERED "pellet", run-002's GUESSED "pellet". The
    merged field must be yellow everywhere (it was green: the answer's confirmation washed the guess), so the upload
    needs the yes."""
    _add_group(ungrouped, run_ids=("run-001", "run-002"))
    _answer_the_required(ungrouped)  # answers run-001's form "pellet" (among the rest)
    _reject_local_starts(ungrouped, "run-001", "run-002")
    b = M.load(ungrouped)
    for path, value in (("context.environment", "ex_situ"), ("context.temperature_K", 298.0)):
        m = next(m for m in b["missing_values"] if m["target_field_path"] == path and m["run_id"] == "run-002")
        M.decide(ungrouped, target_ids=[m["value_id"]], decision="correct", value=value, **BY)
    # the two runs were held at different potentials (100 and 200 mV), which one record cannot carry: left out here
    M.decide(ungrouped, target_ids=[c["candidate_id"] for c in b["candidates"] if c["target_field_path"] == POT
                                    and c["run_id"] in ("run-001", "run-002")], decision="reject", value=None, **BY)
    run2 = next(r["stem"] for r in b["runs"] if r["run_id"] == "run-002")
    b = M.load(ungrouped)
    b["grouping_questions"] = []  # the naming settled (no counter question), so a logbook line reaches run-002 by name
    M.save_bundle(ungrouped, b)
    _apply(ungrouped, src, _finding(FORM, "pellet", 9, runs=(run2,), strength=INFERRED))
    assert _guess(_value(M.load(ungrouped), FORM, "run-002"))
    R.build_records(ungrouped)
    env = json.loads((ungrouped / "drafts" / "g1.draft.json").read_text())["fields"][FORM]
    assert env["value"] == "pellet" and B.evidence_colour(env["evidence"]) == "yellow"
    comp = json.loads((ungrouped / "drafts" / "g1.composition.json").read_text())
    assert R.field_colours(comp)[FORM] == "yellow"
    res = R.export_records(ungrouped, ungrouped.parent / "records", run_portal=_portal)
    assert res["exported"], [(r.get("missing_required"), r.get("summary")) for r in res["refused"]]
    check = RV.final_check(ungrouped.parent / "records", ungrouped)
    assert any(i["path"] == FORM and i["kind"] == "guess" for i in check["items"])
    M.record_consent(ungrouped, by=WHO)
    assert ST.status(ungrouped)["facts"]["colours"]["yellow"] == check["values"]  # one aggregation, one answer


def test_after_the_review_nothing_is_yellow_and_the_upload_needs_no_yes(built, capsys, fake_upstream_env):
    out_review = RV.review(built)
    RV.accept(built, by=WHO, apply=True, listing=out_review["listing"])
    R.build_records(built)
    out = _exported(built)
    capsys.readouterr()
    assert cli.main(["bundle", "upload", str(out), "--dry-run"]) == 0
    said = json.loads(capsys.readouterr().out)
    assert said["final_check"]["values"] == 0


def test_decide_cannot_record_the_final_checks_yes(bdir):
    with pytest.raises(M.MutationRefused, match="bundle upload"):
        M.decide(bdir, target_ids=["experiment"], decision=B.SUBMIT_WITH_GUESSES_DECISION, value=None, **BY)


def test_the_validator_refuses_a_malformed_yes(built):
    b = M.load(built)
    b["scientist_decisions"].append({
        "decision_id": f"d-{len(b['scientist_decisions']) + 1:05d}", "target": {"kind": "experiment", "id": "experiment"},
        "decision": B.SUBMIT_WITH_GUESSES_DECISION, "value": None, "chosen_reading_index": None,
        "decided_by": b["scientist_decisions"][0]["decided_by"], "decided_utc": "2100-02-01T10:00:00Z",
        "method": "scientist_answer", "note": None, "batch_id": None, B.SUBMIT_DIGEST_KEY: "0" * 16,
        B.SUBMIT_RECORDS_KEY: ["r1"]})
    assert any("lists no value or no record" in e for e in B.validate_bundle(b))


# --- the potential scale blocks (goal 6) --------------------------------------------------------------------------------


def test_a_record_with_potentials_and_no_stated_scale_is_blocked_by_the_scale_question(ungrouped):
    """Before 1.22.0 a set-point held for its scale left the record complete, the potential silently out, and the scale
    question optional. Now the scale is required for such a record (required by the control mode it implies, or, when
    the mode is another, as a potential the record holds), and the question that asks it blocks it (the same id)."""
    _add_group(ungrouped)
    _answer_the_required(ungrouped)
    b = M.load(ungrouped)
    [sp] = [c for c in b["candidates"] if c["target_field_path"] == POT and c["run_id"] == "run-001"]
    assert sp["value_state"] == B.STATE_FILLED and sp["fill"]["rule_id"] == B.FILL_SETPOINT_NAME_RULE_ID
    group = next(g for g in b["record_groups"] if g["group_id"] == "g1")
    scale_target = next(m["value_id"] for m in b["missing_values"] if m["target_field_path"] == SCALE
                        and m["run_id"] == "run-001")
    draft, comp = R.compose_group(b, group, ungrouped)
    assert POT not in draft["fields"] and draft["fields"][SCALE]["status"] == "missing"
    [need] = [m for m in comp["missing_required"] if m["path"] == SCALE]
    assert need["from"] == R.FROM_AN_ANSWER and SCALE in need["required_because"] and POT in need["required_because"]
    assert R.field_colours(comp)[SCALE] == "red"
    [q] = [q for q in Q.consolidate(b)["questions"] if scale_target in {t["id"] for t in q["targets"]}]
    assert q["blocking"] is True and q["tier"] == Q.TIER_BLOCKING and q["required_fields"] == [SCALE]
    ids_before = {x["question_id"] for x in Q.consolidate(b)["questions"]}
    # a mode that requires no set-point (a scientist's "mixed"): the potential is still one the record holds, so the
    # scale is still required, now with the 1.22.0 reason
    mode = next(m["value_id"] for m in b["missing_values"] if m["target_field_path"] == B.CONTROL_MODE_PATH
                and m["run_id"] == "run-001")
    M.decide(ungrouped, target_ids=[mode], decision="correct", value="mixed", **BY)
    b = M.load(ungrouped)
    draft, comp = R.compose_group(b, group, ungrouped)
    [need] = [m for m in comp["missing_required"] if m["path"] == SCALE]
    assert need["required_because"] == R.POTENTIALS_NEED_SCALE.format(value=R._said(0.1, POT))
    [q2] = [q for q in Q.consolidate(b)["questions"] if scale_target in {t["id"] for t in q["targets"]}]
    assert q2["blocking"] is True and q2["question_id"] == q["question_id"] and q["question_id"] in ids_before
    # answering the scale lets the potential in, and nothing is missing for it any more
    M.decide(ungrouped, target_ids=[scale_target], decision="correct", value="RHE", **BY)
    b = M.load(ungrouped)
    draft, comp = R.compose_group(b, group, ungrouped)
    assert draft["fields"][POT]["value"] == 0.1 and draft["fields"][SCALE]["value"] == "RHE"
    assert not [m for m in comp["missing_required"] if m["path"] == SCALE]


def test_a_record_with_no_potential_is_not_asked_the_scale(ungrouped):
    _add_group(ungrouped)
    _answer_the_required(ungrouped)
    b = M.load(ungrouped)
    [sp] = [c for c in b["candidates"] if c["target_field_path"] == POT and c["run_id"] == "run-001"]
    M.decide(ungrouped, target_ids=[sp["candidate_id"]], decision="reject", value=None, **BY)
    b = M.load(ungrouped)
    _, comp = R.compose_group(b, next(g for g in b["record_groups"] if g["group_id"] == "g1"), ungrouped)
    assert SCALE not in {m["path"] for m in comp["missing_required"]}
    mode = next(m for m in b["missing_values"] if m["target_field_path"] == B.CONTROL_MODE_PATH and m["run_id"] == "run-001")
    assert mode["value_state"] != B.STATE_FILLED  # no set-point: no mode is deduced


# --- the set-point from the file name (R2) and the control mode (R1a) ----------------------------------------------------


@pytest.mark.parametrize("token, value", [("100mV", 0.1), ("m800mV", -0.8), ("-500mV", -0.5), ("1p2V", 1.2),
                                          ("1600mv", 1.6), ("m0V", 0.0), ("2V", 2.0)])
def test_a_file_name_token_states_its_potential_with_its_sign(token, value):
    assert B.name_token_potential(token) == value


@pytest.mark.parametrize("token", ["M800mV", "after1200mVCycling", "100mV_to_1200mV", "OCV", "1200", "mV", "ZZ1"])
def test_a_token_that_is_no_single_signed_potential_states_none(token):
    assert B.name_token_potential(token) is None


def _setpoint(b: dict, run_id: str = "run-001") -> dict:
    return next(c for c in b["candidates"] if c["target_field_path"] == POT and c["run_id"] == run_id)


def test_the_file_name_set_point_fills_as_a_yellow_deduction(bdir):
    b = M.load(bdir)
    sp = _setpoint(b)
    assert sp["value_state"] == B.STATE_FILLED and sp["fill"] == {"rule_id": B.FILL_SETPOINT_NAME_RULE_ID, "value": 0.1}
    assert B.value_colour(sp["value_state"], sp["fill"]["rule_id"]) == "yellow" and B.validate_bundle(b) == []
    mode = _value(b, B.CONTROL_MODE_PATH)
    assert mode["value_state"] == B.STATE_FILLED and mode["fill"] == {"rule_id": B.FILL_CONTROL_MODE_RULE_ID,
                                                                       "value": "potentiostatic"}
    assert B.control_mode_by_run(b)["run-001"] == "potentiostatic"  # the questions read the deduced mode


@pytest.mark.parametrize("edit", ["sign_dropped", "two_tokens", "cycling_token", "capital_m", "contradicted",
                                  "reading_differs", "decided"])
def test_the_file_name_set_point_is_never_filled_when_anything_is_off(bdir, src, edit):
    b = M.load(bdir)
    sp = _setpoint(b)
    if edit == "sign_dropped":  # the token says m100mV (-0.1 V) but the value read is +0.1: never trusted
        for e in sp["evidence"]:
            e["literal_value"] = "m100mV"
    elif edit == "two_tokens":
        sp["evidence"][0]["literal_value"] = "200mV"
    elif edit == "cycling_token":
        for e in sp["evidence"]:
            e["literal_value"] = "after100mVCycling"
    elif edit == "capital_m":
        for e in sp["evidence"]:
            e["literal_value"] = "M100mV"
    elif edit == "contradicted":
        sp["evidence"][0]["relation"] = "contradicts"
    elif edit == "reading_differs":
        _apply(bdir, src, _finding(POT, 0.4, 31, file=MEMO))
        b = M.load(bdir)
        sp = _setpoint(b)
    elif edit == "decided":
        M.decide(bdir, target_ids=[sp["candidate_id"]], decision="defer", value=None, **BY)
        b = M.load(bdir)
        sp = _setpoint(b)
    got = _setpoint(_derived(b))
    assert (got.get("fill") or {}).get("rule_id") != B.FILL_SETPOINT_NAME_RULE_ID, edit
    mode = _value(_derived(b), B.CONTROL_MODE_PATH)
    assert (mode.get("fill") or {}).get("rule_id") != B.FILL_CONTROL_MODE_RULE_ID or edit == "decided", edit


def test_a_current_set_point_or_a_stated_mode_stops_the_deduction(bdir, src):
    b = M.load(bdir)
    cur = next(m for m in b["missing_values"] if m["target_field_path"] == B.CURRENT_SETPOINT_PATH
               and m["run_id"] == "run-001")
    M.decide(bdir, target_ids=[cur["value_id"]], decision="correct", value=1.0, **BY)
    mode = _value(M.load(bdir), B.CONTROL_MODE_PATH)
    assert (mode.get("fill") or {}).get("rule_id") != B.FILL_CONTROL_MODE_RULE_ID  # galvanostatic or mixed: asked


def test_a_reading_of_another_mode_stops_the_deduction(bdir, src):
    _apply(bdir, src, _finding(B.CONTROL_MODE_PATH, "galvanostatic", 33, strength=INFERRED))
    mode = _value(M.load(bdir), B.CONTROL_MODE_PATH)
    assert mode["value_state"] not in B.FILL_STATES or mode["fill"]["value"] != "potentiostatic"


def test_an_open_circuit_token_is_deduced_open_circuit(bdir):
    """The build's own open-circuit suggestion (an OCV token with no potential after it), as a candidate of the run's
    control mode, fills as open_circuit (made IN MEMORY: the synthetic corpus has no OCV run)."""
    from isaac_api.local_import import suggestions as S

    b = M.load(bdir)
    sp = _setpoint(b, "run-002")
    b["candidates"].remove(sp)  # no potential is read for the run
    c = json.loads(json.dumps(sp))
    c.update(candidate_id="cand-9001", target_field_path=B.CONTROL_MODE_PATH, value=S.CONTROL_MODE_VALUE,
             rule=S.OPEN_CIRCUIT_RULE, extracted_state=B.STATE_NEEDS_REVIEW, statement_key=S.OPEN_CIRCUIT_KEY)
    for e in c["evidence"]:
        e.update(literal_value="OCV", normalization=[{"step": "derive", "rule_id": S.OPEN_CIRCUIT_RULE_ID,
                                                       "from": "OCV", "to": S.CONTROL_MODE_VALUE}])
    b["candidates"].append(c)
    got = next(x for x in _derived(b)["candidates"] if x["candidate_id"] == "cand-9001")
    assert got["value_state"] == B.STATE_FILLED and got["fill"] == {"rule_id": B.FILL_CONTROL_MODE_RULE_ID,
                                                                     "value": "open_circuit"}


# --- asked once for the beamtime (R1b) and a sample's reading (R3) --------------------------------------------------------


def test_a_field_asked_per_group_with_the_same_suggestion_is_asked_once_for_the_beamtime():
    """R1b: three groups asked the reaction on their own question, two with the same suggestion (their files give OER),
    one with another (HER): ONE beamtime question asks the two (its own id, hashed from the field and kind), each member
    keeps its id and targets and names it; the third is listed as an exception and stays asked on its own."""
    path = "context.electrochemistry.reaction"
    bundle = {"candidates": [{"candidate_id": f"c{i}", "value": v} for i, v in ((1, "OER"), (2, "OER"), (3, "HER"))]}

    def member(i: int) -> dict:
        return {"question_id": f"Q-member{i}", "kind": "confirm_value", "scope": f"group:g{i}", "target_field_path": path,
                "targets": [{"kind": "candidate", "id": f"c{i}"}], "per_scope_targets": {f"group:g{i}": [f"c{i}"]},
                "blocking": True, "tier": Q.TIER_BLOCKING, "why": "SYN", "text": "SYN.", "hints": [],
                "applies_to": {"runs": 1}, "allowed_decisions": ["confirm", "correct", "defer"],
                "blocks_group_ids": [f"g{i}"]}

    questions = [member(1), member(2), member(3)]
    [fam] = Q._beamtime_family_questions(questions, bundle)
    assert fam["question_id"] == Q._qid("experiment", Q.SAMPLE_FAMILY_TAG, "confirm_value", path, Q.BEAMTIME_FAMILY_KEY)
    assert fam["scope"] == "experiment" and fam["blocking"] and fam["sample_family"]["basis"] == Q.BEAMTIME_FAMILY_KEY
    assert fam["sample_family"]["member_questions"] == ["Q-member1", "Q-member2"]
    assert fam["targets"] == [{"kind": "candidate", "id": "c1"}, {"kind": "candidate", "id": "c2"}]
    assert fam["asked_once_for_beamtime"]["suggested"] == "OER"
    assert fam["asked_once_for_beamtime"]["exceptions"] == [{"question_id": "Q-member3", "scope": "group:g3"}]
    assert "--decision confirm" in fam["answer_command"] and "OER" in fam["text"]
    assert [q.get("asked_for_sample_by") for q in questions] == [fam["question_id"], fam["question_id"], None]
    assert [q["question_id"] for q in questions] == ["Q-member1", "Q-member2", "Q-member3"]  # ids unchanged
    counts = Q.question_counts([*questions, fam])
    assert counts["blocking"] == 2 and counts["asked_once_per_sample"] == 2  # the family and the exception
    # a field outside the list, or one group alone, is never folded
    assert Q._beamtime_family_questions([member(1)], bundle) == []
    other = [{**member(1), "target_field_path": "context.electrochemistry.electrolyte.name"},
             {**member(2), "target_field_path": "context.electrochemistry.electrolyte.name"}]
    assert Q._beamtime_family_questions(other, bundle) == []


def test_the_beamtime_scale_question_covers_each_groups_question_that_blocks_only_for_the_scale(grouped):
    """R1: once potentials compose, every group's own optional-values question blocked for the scale alone (65 on a real
    beamtime). The beamtime scale question asks it once and covers them: ONE blocking question for the scale."""
    payload = Q.consolidate(M.load(grouped))
    [scale_q] = [q for q in payload["questions"] if q["question_id"] == Q.potential_scale_question_id()]
    assert scale_q["blocking"] is True and scale_q["blocks_groups"] >= 2
    covered = [q for q in payload["questions"] if q.get("covered_by") == scale_q["question_id"]]
    assert covered and all(not q["blocking"] and q["required_fields"] == [SCALE] for q in covered)
    assert not [q for q in payload["questions"] if q["blocking"] and q.get("required_fields") == [SCALE]
                and q is not scale_q]


def test_a_reading_about_a_sample_reaches_every_run_of_it(bdir, src):
    """R3: applies_to `samples` names a sample; the reading reaches every run of it, never another sample's."""
    done = _apply(bdir, src, {**_finding(FORM, "pellet", 9, strength=INFERRED, runs=()),
                              "applies_to": {"scope": "samples", "samples": ["ZZ1"]}})
    assert done["quote_check"]["failed"] == 0 and done["interpretations"] == 3, done
    b = M.load(bdir)
    assert all(_guess(_value(b, FORM, r)) for r in ("run-001", "run-002", "run-003"))
    assert not any(_guess(_value(b, FORM, r)) for r in ("run-004", "run-007"))
    refused = _apply(bdir, src, {**_finding(FORM, "pellet", 9, strength=INFERRED, runs=()),
                                 "applies_to": {"scope": "samples", "samples": ["ZZ9"]}})
    assert refused["interpretations"] == 0
