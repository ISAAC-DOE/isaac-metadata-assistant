"""Anchored string gates in the vendored official schema: what they accept TODAY,
and what ISAAC refuses on top.

READ THIS BEFORE "FIXING" A FAILURE HERE.
=========================================
Part A is CHARACTERIZATION. Every assertion in it pins a DEFECT in the vendored
upstream schema as validated by the pinned jsonschema. Nothing in Part A asserts
desired behaviour. If Part A starts failing, the most likely cause is a GOOD
event — ``schema/isaac_record_v1.json`` was refreshed from upstream and the
patterns were tightened, or ``jsonschema``/Python changed regex flavour. In that
case the fix is to re-read this module, confirm the new behaviour is genuinely
stricter, and update the pins; it is NOT to weaken ISAAC's own gate in Part B/C.

THE DEFECT
==========
All five ``pattern`` gates are written ``^...$``, which reads as "the whole
string must look like this". Python's ``$`` also matches immediately before a
single trailing ``\\n``, so all five accept one value they mean to refuse.

Be exact about the cause, because the obvious explanation is the wrong one. It
is NOT that JSON Schema ``pattern`` uses *search* rather than *match* semantics.
``^`` without ``re.M`` still pins offset 0 — which is exactly why LEADING and
EMBEDDED newlines ARE correctly refused, and ``test_leading_and_embedded_*``
below pin that as the control. The cause is only ``$``.

WHAT ISAAC DOES ABOUT IT
========================
It does not edit the schema (``CLAUDE.md`` §1) and it does not make
``validate_official`` stricter (that would report a local policy as an upstream
schema error, and would move the corpus-mutation oracle). It adds a separate,
separately-named gate, ``isaac_records.exactness``, armed at the three points
where ISAAC decides something: ``export_draft``, ``isaac validate --official``,
and ``POST /api/validate/record``. Parts B and C pin that gate.

It REFUSES; it never strips. Part D pins that, because a future "helpful"
normalisation is the most likely way this protection gets undone.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from isaac_records.exactness import (
    check_exactness,
    declares_whole_string,
    describe_characters,
)
from isaac_records.export import export_draft, transform
from isaac_records.official import validate_official

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schema" / "isaac_record_v1.json").read_text(encoding="utf-8"))


def _patterns() -> dict[str, str]:
    """Every ``pattern`` in the vendored schema, keyed by its location."""
    found: dict[str, str] = {}

    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "pattern" and isinstance(value, str):
                    found[path] = value
                walk(value, f"{path}/{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{path}/{i}")

    walk(SCHEMA)
    return found


#: Location -> (pattern, a value that legitimately satisfies it).
#: The pattern text is pinned too, so an upstream refresh that CHANGES a pattern
#: fails loudly here rather than silently re-characterising a different rule.
GATES = {
    "/properties/record_id": (r"^[0-9A-Z]{26}$", "A" * 26),
    "/properties/links/items/properties/target": (r"^[0-9A-Z]{26}$", "B" * 26),
    "/properties/descriptors/properties/outputs/items/properties/descriptors/items/properties/name": (
        r"^(?!(.*_magnitude($|\..*))|(.*_ratio\..*)|(.*_normalized.*)|(^current_fraction\..*)|(.*\.partial_sum_.*)$)"
        r"[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)*$",
        "alpha_beta",
    ),
    "/properties/attribution/properties/contributors/items/properties/orcid": (
        r"^\d{4}-\d{4}-\d{4}-\d{3}[0-9X]$",
        "0000-0002-1825-0097",
    ),
    "/properties/tags/items": (r"^\S(.*\S)?$", "campaign"),
}

#: Every terminator measured, not just the newline. The point of testing all of
#: them is that anchors are end-of-STRING, so "newline is the leaky one" is a
#: measurement and not an assumption — and for ``tags`` it turns out NOT to be the
#: only one (see ``test_tags_pattern_also_admits_nul_everywhere``).
TERMINATORS = {
    "\n": "LINE FEED",
    "\r": "CARRIAGE RETURN",
    "\x0b": "LINE TABULATION",
    "\x0c": "FORM FEED",
    "\x1c": "INFORMATION SEPARATOR FOUR",
    "\x85": "NEXT LINE",
    " ": "SPACE",
    "\t": "CHARACTER TABULATION",
    " ": "LINE SEPARATOR",
    " ": "PARAGRAPH SEPARATOR",
    "\xa0": "NO-BREAK SPACE",
}


def test_the_terminator_table_holds_the_distinct_entries_it_claims():
    """A table that silently collapses is worse than no table.

    Written because the throwaway script used during investigation spelled U+2028
    and U+2029 as literal spaces; two dict keys collapsed onto SPACE and the run
    reported results for eleven terminators while actually testing nine. The pins
    below would have inherited that hole.
    """
    assert len(TERMINATORS) == 11, "keys collapsed — check for literal whitespace"
    assert sorted(ord(c) for c in TERMINATORS) == [
        0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x1C, 0x20, 0x85, 0xA0, 0x2028, 0x2029
    ]


def _is_valid(pattern: str, value: str) -> bool:
    return Draft202012Validator({"type": "string", "pattern": pattern}).is_valid(value)


# --------------------------------------------------------------------------
# Part A — CHARACTERIZATION of the vendored schema. Pins defects, not wishes.
# --------------------------------------------------------------------------


def test_the_schema_declares_exactly_the_five_gates_this_module_characterises():
    """If upstream adds or removes a pattern, every pin below is suspect.

    Counted from the document rather than trusted from a review note.
    """
    assert _patterns() == {loc: pat for loc, (pat, _) in GATES.items()}


@pytest.mark.parametrize("location", sorted(GATES))
def test_the_legitimate_value_is_accepted(location):
    """Control. If this fails, the fixture is wrong and Part A proves nothing."""
    pattern, good = GATES[location]
    assert _is_valid(pattern, good)


@pytest.mark.parametrize("location", sorted(GATES))
def test_every_anchored_gate_admits_a_trailing_newline(location):
    """THE DEFECT — all five, not the two an earlier review named.

    A failure here most likely means the schema was refreshed and FIXED. Re-read
    this module's docstring; do not weaken ``isaac_records.exactness``.
    """
    pattern, good = GATES[location]
    assert _is_valid(pattern, good + "\n"), (
        f"{location} no longer admits a trailing newline. If the vendored schema was "
        f"refreshed from upstream, this is GOOD NEWS: update this characterization "
        f"(and schema/PROVENANCE.md), and leave the isaac_records.exactness gate armed "
        f"— it is a no-op against a correct pattern and still defends the other gates."
    )


@pytest.mark.parametrize("location", sorted(GATES))
@pytest.mark.parametrize("terminator", sorted(set(TERMINATORS) - {"\n"}))
def test_no_terminator_other_than_newline_is_admitted_trailing(location, terminator):
    """The leak is EXACTLY one character wide.

    Measured rather than assumed: ``$`` is tolerant of a trailing newline and of
    nothing else, so ``\\r``, ``\\x0b``, ``\\x0c``, ``\\x1c``, ``\\x85``, a space,
    a tab, U+2028, U+2029 and NBSP are all correctly refused by all five gates.
    """
    pattern, good = GATES[location]
    assert not _is_valid(pattern, good + terminator), (
        f"{location} now admits a trailing {TERMINATORS[terminator]} — a NEW leak, "
        f"wider than the single-newline one this module was written against."
    )


@pytest.mark.parametrize("location", sorted(GATES))
@pytest.mark.parametrize("terminator", sorted(TERMINATORS))
def test_leading_terminators_are_refused(location, terminator):
    """THE CONTROL that identifies the cause.

    ``^`` without ``re.M`` pins offset 0, so a LEADING newline is refused. This is
    the evidence that the defect is ``$``'s trailing-newline tolerance and NOT, as
    is commonly assumed, JSON Schema's search-vs-match semantics — under search
    semantics a leading newline would leak too.
    """
    pattern, good = GATES[location]
    assert not _is_valid(pattern, terminator + good)


@pytest.mark.parametrize("location", sorted(GATES))
def test_embedded_newlines_are_refused(location):
    """Second half of the control: an EMBEDDED newline is refused everywhere."""
    pattern, good = GATES[location]
    assert not _is_valid(pattern, good[:2] + "\n" + good[2:])


def test_tags_pattern_also_admits_nul_everywhere():
    """A SECOND, DIFFERENT defect in the tags gate — deliberately NOT fixed here.

    ``^\\S(.*\\S)?$`` accepts ``\\x00`` leading, trailing, embedded, and alone,
    because NUL is not whitespace (so ``\\S`` matches it) and ``.`` matches it too.
    ``"\\x00"`` on its own is a valid tag.

    This is about which characters ``\\S`` covers, not about what ``$`` anchors,
    and ``re.fullmatch`` does NOT catch it — the match legitimately consumes the
    whole string. So ``isaac_records.exactness`` is silent on it BY DESIGN, and
    ``test_exactness_is_silent_on_the_nul_defect`` pins that silence so nobody
    reads it as an oversight. Widening that gate into a general control-character
    policy is a scope decision for a human; it is recorded here and reported, not
    smuggled in.
    """
    pattern, good = GATES["/properties/tags/items"]
    assert _is_valid(pattern, good + "\x00")
    assert _is_valid(pattern, "\x00" + good)
    assert _is_valid(pattern, good[:2] + "\x00" + good[2:])
    assert _is_valid(pattern, "\x00")


# --------------------------------------------------------------------------
# Part B — ISAAC's gate: the rule itself
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pattern,expected",
    [
        (r"^[0-9A-Z]{26}$", True),
        (r"^\S(.*\S)?$", True),
        (r"^abc", False),  # anchored at the front only
        (r"abc$", False),  # anchored at the end only
        (r"abc", False),  # unanchored: fullmatch would be over-refusal
        (r"^costs \$", False),  # escaped dollar: a literal, not an anchor
        (r"^costs \\$", True),  # escaped backslash, then a real anchor
    ],
)
def test_declares_whole_string(pattern, expected):
    """Only a pattern that SAYS it is whole-string gets the fullmatch treatment.

    An unanchored ``pattern`` is legitimate JSON Schema (a substring rule), and
    demanding ``fullmatch`` of one would be over-refusal — the main regression
    risk in this whole change.
    """
    assert declares_whole_string(pattern) is expected


def test_describe_characters_names_without_emitting():
    """A refusal message must never carry the control character it is refusing.

    It is rendered into a terminal, a JSON body and a web page; echoing a raw
    ``\\r`` can overwrite the line that explains the error.
    """
    described = describe_characters("\n\r\x00")
    assert described == "U+000A LINE FEED, U+000D CARRIAGE RETURN, U+0000 NULL"
    assert "\n" not in described
    assert "\r" not in described
    assert "\x00" not in described


# --------------------------------------------------------------------------
# Part C — ISAAC's gate: applied to records and to export
# --------------------------------------------------------------------------

#: The COMMITTED synthetic sample, not a hand-rolled minimal record. Two reasons:
#: a hand-rolled fixture drifts from the schema silently, and this one is the
#: artifact `scripts/run_synthetic_demo.py` regenerates — so if this gate were ever
#: to break the demo, these tests break first and say so.
SAMPLE_PATH = ROOT / "docs" / "samples" / "01JQZ0SYNTHXANESDEMO000000.json"


def _sample_record() -> dict:
    record = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    record.setdefault("tags", [])
    record["tags"] = ["campaign"]
    return record


def test_the_baseline_record_is_schema_valid_and_exact():
    """Control for Part C: without it, every refusal below could be a typo."""
    record = _sample_record()
    assert validate_official(record, ROOT).ok, validate_official(record, ROOT).render()
    assert check_exactness(record, ROOT).ok


@pytest.mark.parametrize(
    "field,mutate",
    [
        ("record_id", lambda r: r.update(record_id=RID + "\n")),
        ("tags.0", lambda r: r.update(tags=["campaign\n"])),
        ("tags.1", lambda r: r.update(tags=["ok", "campaign\n"])),
    ],
)
def test_exactness_refuses_a_trailing_newline_and_names_the_field(field, mutate):
    record = _sample_record()
    mutate(record)

    # The premise: the SCHEMA still says this is fine. Without this assertion the
    # test could pass for the wrong reason (e.g. the value being invalid anyway).
    assert validate_official(record, ROOT).ok, "premise lost: schema now refuses this"

    report = check_exactness(record, ROOT)
    assert not report.ok
    assert [e.path for e in report.errors] == [field]
    message = report.errors[0].message
    assert "U+000A LINE FEED" in message
    # Never dump the raw control byte into a user-facing string.
    assert "\n" not in message
    # Refuse, do not offer to repair.
    assert "will not strip them for you" in message


@pytest.mark.parametrize("terminator", sorted(set(TERMINATORS) - {"\n"}))
def test_exactness_is_silent_where_the_schema_already_refuses(terminator):
    """One problem, one report, in the schema's own words.

    A value the schema ALREADY rejects must not be reported twice in two
    vocabularies — that is how an operator ends up chasing the wrong rule.
    """
    record = _sample_record()
    record["tags"] = ["campaign" + terminator]
    assert not validate_official(record, ROOT).ok
    assert check_exactness(record, ROOT).ok


def test_exactness_is_silent_on_the_nul_defect():
    """Pins the DELIBERATE non-coverage documented in Part A.

    If someone later widens the gate to control characters, this test fails and
    forces them to read the rationale rather than discover the scope change by
    accident.
    """
    record = _sample_record()
    record["tags"] = ["campaign\x00"]
    assert validate_official(record, ROOT).ok
    assert check_exactness(record, ROOT).ok


def test_a_legitimate_record_is_not_over_refused():
    """THE REGRESSION RISK. Ordinary values must sail through untouched.

    Includes an ORCID and a descriptor name, so the two gates that Part C's
    smaller fixture does not exercise are covered against over-refusal too.
    """
    record = _sample_record()
    record["tags"] = ["campaign", "xanes", "cu-k-edge", "two words", "trailing-dash-"]
    record["attribution"] = {
        "contributors": [
            {
                "name": "A. Synthetic",
                "orcid": "0000-0002-1825-0097",
                "role": "performed_measurement",
            }
        ]
    }
    assert validate_official(record, ROOT).ok, validate_official(record, ROOT).render()
    report = check_exactness(record, ROOT)
    assert report.ok, report.render()


def test_committed_sample_record_is_exact():
    """The shipped sample must not be collateral damage of this gate."""
    sample = ROOT / "docs" / "samples" / "01JQZ0SYNTHXANESDEMO000000.json"
    record = json.loads(sample.read_text(encoding="utf-8"))
    assert check_exactness(record, ROOT).ok


# --------------------------------------------------------------------------
# Part C2 — `isaac validate --official`, the command CLAUDE.md §1 tells users to run
# --------------------------------------------------------------------------


def test_cli_validate_official_passes_a_clean_record(tmp_path, capsys):
    """Control: the ordinary record still exits 0 and says PASS."""
    from isaac_records.cli import main

    path = tmp_path / "clean.json"
    path.write_text(json.dumps(_sample_record()), encoding="utf-8")

    assert main(["--root", str(ROOT), "validate", str(path), "--official"]) == 0
    out = capsys.readouterr().out
    assert "PASS — valid against official ISAAC schema" in out
    assert "exactness" not in out.lower(), "a clean record must not mention the gate"


def test_cli_validate_official_exits_nonzero_on_an_inexact_record(tmp_path, capsys):
    """THE CONTRADICTION THIS CLOSES.

    Before the gate, this command exited 0 — reporting a clean PASS — for a record
    ``isaac export`` refuses. A user asking "will this export?" got the wrong
    answer from the tool documented for exactly that question.
    """
    from isaac_records.cli import main

    record = _sample_record()
    record["tags"] = ["campaign\n"]
    path = tmp_path / "inexact.json"
    path.write_text(json.dumps(record), encoding="utf-8")

    code = main(["--root", str(ROOT), "validate", str(path), "--official"])
    out = capsys.readouterr().out

    assert code == 1, "the command a user runs to predict export exited 0 on a refusal"
    # The schema verdict is still reported truthfully and separately: the record IS
    # schema-valid, and the gate must not pretend otherwise.
    assert "PASS — valid against official ISAAC schema" in out
    assert "not a schema rule" in out, "a local policy is being attributed to upstream"
    assert "tags.0" in out
    assert "U+000A LINE FEED" in out


def test_cli_advisory_warnings_still_do_not_affect_the_exit_code(tmp_path, capsys):
    """Re-pins the pre-existing rule alongside the new one, so the two cannot merge."""
    from isaac_records.cli import main

    record = _sample_record()
    record["measurement"] = copy.deepcopy(record["measurement"])
    record["measurement"]["series"] = []
    path = tmp_path / "warned.json"
    path.write_text(json.dumps(record), encoding="utf-8")

    code = main(["--root", str(ROOT), "validate", str(path), "--official", "--warnings"])
    out = capsys.readouterr().out

    assert "NO_MEASUREMENT_SERIES" in out, "premise lost: no advisory warning raised"
    assert code == 0, "an advisory warning moved the exit code — it must never"


# --------------------------------------------------------------------------
# Part D — export REFUSES, and does not repair
# --------------------------------------------------------------------------


#: The COMMITTED golden draft — the same fixture `tests/test_export.py` uses and
#: the one the synthetic demo drives. A hand-rolled draft would drift from the
#: no-guessing rules and start failing for reasons unrelated to this gate.
DRAFT_PATH = ROOT / "tests" / "fixtures" / "cuo_xanes_draft.json"
RID = "01JFH3Q8Z1Q9F0XG3V7N4K2M8C"


def _golden_draft() -> dict:
    draft = json.loads(DRAFT_PATH.read_text(encoding="utf-8"))
    draft["tags"] = ["campaign"]
    return draft


def test_a_clean_draft_still_exports():
    """Control: the gate must not break the ordinary path."""
    result = export_draft(_golden_draft(), ROOT, record_id=RID)
    assert result.ok, result.draft_report.render()
    assert result.record["tags"] == ["campaign"]
    assert result.sidecar is not None


def test_export_refuses_a_tag_with_a_trailing_newline():
    """The end-to-end defect: verbatim tag copy + a lenient gate = a bad record.

    ``transform`` still PRODUCES the value — it is a pure function and stays one —
    and the schema still calls the result valid. The refusal is ISAAC's.
    """
    draft = _golden_draft()
    draft["tags"] = ["campaign\n"]

    produced = transform(draft, record_id=RID, now="2099-03-05T20:15:00Z")
    assert produced["tags"] == ["campaign\n"], "transform must stay pure and total"
    assert validate_official(produced, ROOT).ok, "premise: the schema accepts it"

    result = export_draft(draft, ROOT, record_id=RID)
    assert not result.ok
    assert result.record is not None, "the offending record is returned for inspection"
    assert result.sidecar is None, "nothing is exported"
    rendered = result.draft_report.render()
    assert "tags.0" in rendered
    assert "U+000A LINE FEED" in rendered


def test_export_never_strips_the_offending_value():
    """CLAUDE.md §5. A silent repair is the failure mode this gate exists to avoid.

    Both halves matter: the caller's draft is not mutated, and the refused record
    still carries the value the author actually supplied.
    """
    draft = _golden_draft()
    draft["tags"] = ["campaign\n"]
    before = copy.deepcopy(draft)

    result = export_draft(draft, ROOT, record_id=RID)

    assert not result.ok
    assert draft == before, "export_draft mutated the caller's draft"
    assert result.record["tags"] == ["campaign\n"], "the value was silently repaired"


def test_record_id_refusal_does_not_cite_a_pattern_that_matches_the_value():
    """REVIEW FINDING F2 — the message asserted the wrong rule.

    The old text was ``"'AAA…\\n' is not a valid ULID (^[0-9A-Z]{26}$)"``. In
    Python that pattern MATCHES the string being rejected, so the operator was
    handed a refusal justified by a rule that accepts their value — the same
    ``$`` defect, restated in prose, in the error message about it.

    The previous test asserted only ``not result.ok`` and never looked at the
    message, which is why the drift was invisible. This one looks.
    """
    bad = "not-a-ulid"
    result = export_draft(_golden_draft(), ROOT, record_id=bad)

    assert not result.ok
    rendered = result.draft_report.render()
    assert "^[0-9A-Z]{26}$" not in rendered, (
        "the refusal cites a regex whose Python flavour is the very thing in question"
    )
    assert "exactly 26 characters" in rendered
    # And the rule it states must be TRUE of the value it rejects.
    assert not re.fullmatch(r"[0-9A-Z]{26}", bad)


def test_a_newline_suffixed_record_id_is_refused_by_the_record_level_gate():
    """WHICH gate catches this is itself worth pinning, and it is not the obvious one.

    ``ids.is_record_id`` still uses ``^[0-9A-Z]{26}$`` with ``.match()``, so it
    ACCEPTS ``RID + "\\n"`` — the `export_draft` pre-check above waves it through.
    The refusal comes from the record-level exactness gate after ``transform``,
    which is exactly the "guard the OUTPUT, not the writers" property this change
    is built on.

    Asserted this way ON PURPOSE so the test stays correct and meaningful whether
    or not the separate ``ids.RECORD_ID_RE`` anchoring fix has landed: it pins
    that the record is refused and that the message is well-formed, not which of
    two overlapping defences fired first.
    """
    from isaac_records.ids import is_record_id

    newline_id = RID + "\n"
    result = export_draft(_golden_draft(), ROOT, record_id=newline_id)

    assert not result.ok
    rendered = result.draft_report.render()
    assert "U+000A LINE FEED" in rendered
    assert "record_id" in rendered
    # The exactness gate never echoes the offending value at all — strictly better
    # than escaping it. Pin that: no raw control byte, and no raw id either.
    assert "\r" not in rendered
    assert newline_id not in rendered

    if is_record_id(newline_id):
        # Belt and braces: while `ids` remains lenient, this test is the only thing
        # standing between a newline-suffixed ULID and an exported record.
        assert "only because Python's '$'" in rendered
