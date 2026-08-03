"""`attribution.uploaded_by` is refused, never laundered into an official record.

The official schema declares this field SERVER-STAMPED from the authenticated
identity at ingestion, with any client value overwritten — "tamper-proof
attribution", decided by D. Sokaras 2026-06-15. ISAAC authenticates nobody, so it
has nothing true to stamp. Before this module existed, a draft could simply carry
`attribution.uploaded_by` and the whole attribution dict was copied verbatim by
`export.transform`: `validate_draft` returned ok with ZERO errors and required NO
evidence, the official schema PASSED, and the client's string landed in the
on-disk record — in a field readers are told the server owns, and which can name a
real person.

Note the shape of the old defect, because it is why a grep audit missed it: there
is no literal "uploaded_by" anywhere in `src/`. The passthrough was STRUCTURAL
(`record["attribution"] = strip_evidence(draft["attribution"])`), so searching for
the field name concluded it was "dead in code".

THERE WERE THREE STRUCTURAL PASSTHROUGHS, NOT ONE. A first attempt at this fix
guarded the `attribution` block writer only. An independent adversarial review
(finding C1) proved per-writer guards do not compose: `transform` writes into
`record["attribution"]` from two independent places, and the other one — the
`fields` loop's `set_path`, the draft format's NATIVE mechanism for scalar official
JSON-paths — was unguarded, so `fields["attribution.uploaded_by"]` bypassed both
layers end-to-end. A third spelling (`fields["attribution"]` carrying the whole
block as one object value) leaked identically.

So the fix is a SINGLE CHOKEPOINT per artifact, and this module pins each:
  1. `draft_validator.validate_draft` — the user-visible refusal, now covering BOTH
     mechanisms and sharing ONE message constant so they cannot drift.
  2. `export._enforce_server_owned_invariant` — runs as the LAST step of `transform`,
     after every writer, so no ordering of writes can leak.
  3. `export.build_sidecar` — deliberately does NOT filter. The sidecar is unvalidated
   free text and a denylist over caller-chosen keys protects nothing; see
   `test_sidecar_may_name_the_refused_field_and_that_is_deliberate`.

Every identity string below is deliberately unusable: `example.invalid` is a
reserved non-resolvable TLD, and no real person is named.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from isaac_records import validate_draft
from isaac_records.cli import main
from isaac_records.draft_validator import UPLOADED_BY_PATH, UPLOADED_BY_REFUSAL
from isaac_records.export import build_sidecar, export_draft, transform
from isaac_records.official import validate_official

ROOT = Path(__file__).resolve().parents[1]
DRAFT_PATH = ROOT / "tests" / "fixtures" / "cuo_xanes_draft.json"
RID = "01JFH3Q8Z1Q9F0XG3V7N4K2M8C"

# Unmistakably fake: `.invalid` is reserved by RFC 2606 and can never resolve.
SPOOFED = "not-a-real-user@example.invalid"


def _contributor_key(draft: dict) -> str:
    """The golden draft's contributor block-evidence key, derived not hardcoded.

    Derived so this module introduces no new personal name of its own: the only
    real name involved is the one already committed in the shared fixture.
    """
    contributor = draft["attribution"]["contributors"][0]
    return f"attribution:{contributor['name']}|{contributor['role']}"


@pytest.fixture
def draft():
    return json.loads(DRAFT_PATH.read_text(encoding="utf-8"))


def _joined(report) -> str:
    return "\n".join(f"{w} — {m}" for w, m in report.errors)


FIELDS_WHERE = f"fields[{UPLOADED_BY_PATH!r}]"


def _uploaded_by_errors(report) -> list[tuple[str, str]]:
    """Refusals of the server-owned field, by EITHER mechanism.

    Matched on the shared message constant rather than on `where`, so a new
    mechanism reporting at a new location is still counted here — the thing under
    test is "was the field refused", not "was it refused at one known site".
    """
    return [(w, m) for w, m in report.errors if m == UPLOADED_BY_REFUSAL]


def _evidenced(value):
    """A fully-evidenced envelope — the hardest case for the guard to refuse."""
    return {
        "value": value,
        "status": "verified",
        "evidence": [
            {
                "source_type": "user_confirmation",
                "question": "Who uploaded this?",
                "answer": str(value),
                "timestamp": "2099-03-05T21:00:00Z",
            }
        ],
    }


def _drop_attribution(draft: dict) -> None:
    """Remove the fixture's attribution block AND its block evidence.

    Needed for the pure-`fields` cases: an attribution block in the draft
    overwrites whatever the `fields` loop wrote at `record["attribution"]`, which
    is exactly what masked C1 from a casual reading.
    """
    key = _contributor_key(draft)
    draft.pop("attribution", None)
    draft["block_evidence"].pop(key, None)


# --------------------------------------------------------------------------- #
# 1. The validator refuses — this is the user-visible refusal.
# --------------------------------------------------------------------------- #


def test_negative_control_validator_refuses_spoofed_uploaded_by(draft):
    """NEGATIVE CONTROL for the validator half of the fix.

    Reverting the `attribution.uploaded_by` check in
    `draft_validator.validate_draft` makes this test fail: the golden draft is
    otherwise fully covered, so adding this one key is the only thing that can
    turn an ok report into a failing one.
    """
    draft["attribution"]["uploaded_by"] = SPOOFED
    report = validate_draft(draft)
    assert not report.ok, (
        "a client-authored attribution.uploaded_by was accepted — the schema "
        "declares this field server-stamped and ISAAC has no identity to stamp it "
        "with:\n" + report.render()
    )
    errors = _uploaded_by_errors(report)
    assert errors, f"refused, but not at attribution.uploaded_by:\n{_joined(report)}"
    assert errors[0][0] == UPLOADED_BY_PATH, errors[0][0]


def test_refusal_message_explains_why_and_offers_the_alternative():
    """The message must explain WHY and name the sanctioned alternative.

    Asserted against the module constant, not hand-typed substrings (review
    finding M5): every refusal site now shares that constant, so a reword updates
    one string and cannot make a test lie about a message it no longer matches.
    What is pinned here is the required CONCEPTS, so a reword that quietly drops
    the reason or the alternative still fails.
    """
    for concept in ("server-stamped", "authenticated", "contributors", "evidence"):
        assert concept in UPLOADED_BY_REFUSAL, concept


def test_both_refusal_sites_share_one_message(draft):
    """The two mechanisms cannot drift into two different explanations.

    The first attempt had one site and a hand-typed message; the review found a
    second mechanism. A second hand-typed message would have been free to diverge.
    """
    block_draft = copy.deepcopy(draft)
    block_draft["attribution"]["uploaded_by"] = SPOOFED
    fields_draft = copy.deepcopy(draft)
    fields_draft["fields"][UPLOADED_BY_PATH] = _evidenced(SPOOFED)

    block_errors = _uploaded_by_errors(validate_draft(block_draft))
    fields_errors = _uploaded_by_errors(validate_draft(fields_draft))
    assert [w for w, _ in block_errors] == [UPLOADED_BY_PATH]
    assert [w for w, _ in fields_errors] == [FIELDS_WHERE]
    # Different `where` (so the user can tell which mechanism they used), one message.
    assert block_errors[0][1] == fields_errors[0][1] == UPLOADED_BY_REFUSAL


def test_envelope_form_of_uploaded_by_is_also_refused(draft):
    """The evidence-envelope form is refused too — evidence cannot authenticate.

    Evidence can show that a document NAMES someone; it can never show that the
    server AUTHENTICATED them. So a fully-evidenced envelope is exactly as
    unacceptable as a bare string, and must not be a way around the check.
    """
    draft["attribution"]["uploaded_by"] = {
        "value": SPOOFED,
        "status": "verified",
        "evidence": [
            {
                "source_type": "user_confirmation",
                "question": "Who uploaded this?",
                "answer": SPOOFED,
                "timestamp": "2099-03-05T21:00:00Z",
            }
        ],
    }
    report = validate_draft(draft)
    assert not report.ok
    assert _uploaded_by_errors(report), _joined(report)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(None, id="null"),
        pytest.param("", id="empty-string"),
        pytest.param({}, id="empty-envelope"),
        pytest.param([SPOOFED], id="list"),
    ],
)
def test_uploaded_by_refused_on_key_presence_not_truthiness(draft, value):
    """Any presence of the key is refused, including null-ish forms.

    The check is key-presence deliberately. A draft that writes
    `uploaded_by: null` or `uploaded_by: ""` is still asserting authorship of a
    server-owned field, and a truthiness guard would wave those through — the
    same class of mistake as the old falsy `series` guard (see the R2 comment in
    `export.transform`).
    """
    draft["attribution"]["uploaded_by"] = value
    report = validate_draft(draft)
    assert not report.ok
    assert _uploaded_by_errors(report), _joined(report)


# --------------------------------------------------------------------------- #
# 1b. C1 — the `fields` mechanism. The draft format's NATIVE way to write a
#     scalar official JSON-path, and the passthrough the first attempt missed.
# --------------------------------------------------------------------------- #


def test_negative_control_c1_fields_path_is_refused(draft):
    """NEGATIVE CONTROL for the `fields` half of the validator chokepoint.

    THE C1 REPRODUCTION, INVERTED. At the first-attempt commit this exact draft
    gave `validate_draft` ok with ZERO errors, `isaac export` printing "PASS —
    valid against official ISAAC schema v1.05", and `{"uploaded_by": ...}` on disk.

    Reverting the `_paths_authoring_uploaded_by` loop in `validate_draft` makes
    this fail: the golden draft is otherwise fully covered, so this one key is the
    only thing that can turn an ok report into a failing one.
    """
    draft["fields"][UPLOADED_BY_PATH] = _evidenced(SPOOFED)
    report = validate_draft(draft)
    assert not report.ok, (
        "attribution.uploaded_by supplied through `fields` was accepted — the "
        "`fields` + set_path mechanism is the draft format's native way to write a "
        "scalar official path, and this field IS a scalar official string:\n"
        + report.render()
    )
    errors = _uploaded_by_errors(report)
    assert errors, f"refused, but not for uploaded_by:\n{_joined(report)}"
    # `where` names the mechanism, so the user can tell which one they used.
    assert errors[0][0] == FIELDS_WHERE, errors[0][0]


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(UPLOADED_BY_PATH, id="exact-path"),
        pytest.param(f"{UPLOADED_BY_PATH}.sub", id="deeper-path-creates-the-key"),
    ],
)
def test_fields_spellings_that_reach_the_field_are_refused(draft, path):
    """Both dotted spellings that `set_path` lands on the refused field.

    A deeper path is included because `set_path` CREATES `attribution.uploaded_by`
    as a dict in order to reach `...uploaded_by.sub` — a different value shape at
    the same refused location.
    """
    draft["fields"][path] = _evidenced(SPOOFED)
    report = validate_draft(draft)
    assert not report.ok
    assert _uploaded_by_errors(report), _joined(report)


def test_fields_whole_block_object_value_is_refused(draft):
    """The THIRD spelling: a shorter path whose VALUE supplies the last segment.

    `fields["attribution"] = {"value": {"uploaded_by": ...}}` is not a dotted
    spelling of the refused path at all, yet `set_path` writes the whole object
    and the field lands. Measured leaking at the first-attempt commit exactly as
    the dotted form did — which is why the validator resolves paths against the
    envelope value instead of string-matching keys.
    """
    _drop_attribution(draft)
    draft["fields"]["attribution"] = _evidenced({"uploaded_by": SPOOFED})
    report = validate_draft(draft)
    assert not report.ok
    errors = _uploaded_by_errors(report)
    assert errors, _joined(report)
    assert errors[0][0] == "fields['attribution']", errors[0][0]


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(None, id="null"),
        pytest.param("", id="empty-string"),
    ],
)
def test_fields_mechanism_refused_on_key_presence_not_truthiness(draft, value):
    """Key presence again, matching the block check.

    Note this is strictly stricter than what can leak: the `fields` loop SKIPS an
    envelope whose value is None or whose status is "missing", so these two could
    not have reached the record. Refusing them anyway is the intended direction —
    the draft is still asserting authorship of a server-owned field, and a
    truthiness guard here would be the same class of mistake as the old falsy
    `series` guard (see the R2 comment in `export.transform`).
    """
    draft["fields"][UPLOADED_BY_PATH] = {"value": value, "status": "missing"}
    report = validate_draft(draft)
    assert not report.ok
    assert _uploaded_by_errors(report), _joined(report)


def test_neighbouring_field_paths_are_not_over_refused(draft):
    """The guard must not swallow legitimate attribution or lookalike paths.

    Whitespace and empty-segment variants are deliberately NOT normalised: they
    land somewhere else entirely (`" attribution"`, `"uploaded_by "`, an
    empty-string key), and the official schema rejects each outright via
    `additionalProperties: false`. Treating them as the real field would invent an
    intent the draft did not express.
    """
    for path in (
        "attribution.contributors",
        "attribution.uploaded_by_someone_else",
        " attribution.uploaded_by",
        "attribution.uploaded_by ",
        "attribution..uploaded_by",
        "uploaded_by",
    ):
        probe = copy.deepcopy(draft)
        probe["fields"][path] = _evidenced("x")
        assert not _uploaded_by_errors(validate_draft(probe)), path


# --------------------------------------------------------------------------- #
# 2. `transform` never emits the field — one invariant, after every writer.
# --------------------------------------------------------------------------- #


def test_negative_control_transform_never_emits_uploaded_by(draft):
    """NEGATIVE CONTROL for the export chokepoint.

    Called DIRECTLY, bypassing `validate_draft` entirely — so this exercises the
    structural backstop on its own. Reverting
    `_enforce_server_owned_invariant`'s pop makes this test fail even with the
    validator check intact.
    """
    draft["attribution"]["uploaded_by"] = SPOOFED
    record = transform(draft, record_id=RID)

    assert "uploaded_by" not in record.get("attribution", {}), record.get("attribution")
    # Structural check is not enough on its own: prove the string is nowhere in the
    # record at all, in case a future change relocates rather than drops it.
    assert SPOOFED not in json.dumps(record)
    # The rest of the attribution block is untouched by the drop.
    assert record["attribution"]["contributors"] == draft["attribution"]["contributors"]


def test_attribution_omitted_when_uploaded_by_was_its_only_key(draft):
    """An attribution block emptied by the refusal is omitted, not written as `{}`.

    `{}` IS schema-valid here (`additionalProperties: false`, no required keys —
    pinned by test_truthpath_characterization's "attribution = {}" case), so
    emitting it would validate. But it asserts nothing, and writing an empty
    claim where the draft's only claim was refused is worse than writing no block.
    """
    contributor_key = _contributor_key(draft)  # read before replacing the block
    draft["attribution"] = {"uploaded_by": SPOOFED}
    draft["block_evidence"].pop(contributor_key, None)
    record = transform(draft, record_id=RID)
    assert "attribution" not in record, record.get("attribution")
    # And the resulting record is still officially valid without the block.
    assert validate_official(record, ROOT).ok


def test_evidence_only_attribution_block_is_omitted_not_written_as_empty(draft):
    """DISCLOSED BEHAVIOUR CHANGE (review finding I4) — kept deliberately.

    An `attribution` block holding only `evidence` keys is emptied by
    `strip_evidence`, and is now OMITTED where the parent commit exported
    `attribution: {}`. No `uploaded_by` is involved: this shape changes on its own.

    Measured: parent 3079f5f -> `record["attribution"] == {}`; now -> no key.

    Both are officially valid (`additionalProperties: false`, no required keys —
    pinned by test_truthpath_characterization's "attribution = {}" case). Omission
    is kept because `{}` asserts nothing, and the review's instruction was to
    disclose the change rather than revert it.
    """
    contributor_key = _contributor_key(draft)
    draft["attribution"] = {"evidence": [{"source_type": "document", "locator": "p.1"}]}
    draft["block_evidence"].pop(contributor_key, None)

    report = validate_draft(draft)
    assert report.ok, report.render()  # nothing about this shape is refused

    result = export_draft(draft, ROOT, record_id=RID)
    assert result.ok, result.draft_report.render()
    assert "attribution" not in result.record, result.record.get("attribution")


def test_negative_control_transform_never_emits_a_fields_supplied_uploaded_by(draft):
    """NEGATIVE CONTROL — C1 at the `transform` layer, called directly.

    The second half of the C1 reproduction: the `fields` loop's `set_path` writing
    the refused field. The first attempt's per-writer pop lived inside the
    `attribution` block writer and never saw this, so `transform` emitted the
    value. Removing `_enforce_server_owned_invariant(record)` from the end of
    `transform` makes this fail.
    """
    _drop_attribution(draft)
    draft["fields"][UPLOADED_BY_PATH] = _evidenced(SPOOFED)
    record = transform(draft, record_id=RID)

    assert "uploaded_by" not in record.get("attribution", {}), record.get("attribution")
    assert SPOOFED not in json.dumps(record)
    # Nothing was left behind: attribution held only the refused key, so it is omitted.
    assert "attribution" not in record, record.get("attribution")
    assert validate_official(record, ROOT).ok


def test_negative_control_i2_emptied_block_no_longer_unmasks_a_fields_leak(draft):
    """NEGATIVE CONTROL for review finding I2 — THE regression the review found.

    The specific shape: an `attribution` block holding ONLY `evidence` keys (so
    `strip_evidence` empties it) PLUS `fields["attribution.uploaded_by"]`.

    Measured across three commits:
      * parent 3079f5f      -> record.attribution == {}   (no leak, by accident:
                               the unconditional assignment clobbered the `fields`
                               write)
      * first attempt       -> record.attribution ==
                               {"uploaded_by": "<spoofed>"}   (LEAK — the new
                               `if attribution:` stopped clobbering it, making this
                               shape WORSE than the code being fixed)
      * chokepoint (now)    -> no `attribution` key at all

    This is why the invariant runs after every writer: with a per-writer guard
    there is always an ordering in which one writer's output survives another's.
    """
    contributor_key = _contributor_key(draft)
    draft["attribution"] = {"evidence": [{"source_type": "document", "locator": "p.1"}]}
    draft["block_evidence"].pop(contributor_key, None)
    draft["fields"][UPLOADED_BY_PATH] = _evidenced(SPOOFED)

    record = transform(draft, record_id=RID)

    assert "attribution" not in record, record.get("attribution")
    assert SPOOFED not in json.dumps(record)
    assert validate_official(record, ROOT).ok


def test_transform_never_emits_the_whole_block_object_spelling(draft):
    """The third spelling, at the `transform` layer."""
    _drop_attribution(draft)
    draft["fields"]["attribution"] = _evidenced({"uploaded_by": SPOOFED})
    record = transform(draft, record_id=RID)
    assert SPOOFED not in json.dumps(record)
    assert "attribution" not in record, record.get("attribution")


def test_fields_written_attribution_siblings_survive_the_invariant(draft):
    """The invariant removes ONE key — it does not discard the `fields` block.

    Guards against the chokepoint being implemented as "delete
    record['attribution']", which would pass every leak test while destroying
    legitimate data.
    """
    _drop_attribution(draft)
    draft["fields"]["attribution.contributors"] = _evidenced(
        [{"name": "Synthetic Operator", "role": "performed_measurement"}]
    )
    draft["fields"][UPLOADED_BY_PATH] = _evidenced(SPOOFED)
    record = transform(draft, record_id=RID)

    assert record["attribution"] == {
        "contributors": [{"name": "Synthetic Operator", "role": "performed_measurement"}]
    }
    assert SPOOFED not in json.dumps(record)
    assert validate_official(record, ROOT).ok


# --------------------------------------------------------------------------- #
# 2b. The sidecar: a refused field ships no provenance claim.
# --------------------------------------------------------------------------- #


def test_sidecar_may_name_the_refused_field_and_that_is_deliberate(draft):
    """A DELIBERATE NON-GUARANTEE, pinned so it is not mistaken for an oversight.

    Two revisions of this branch filtered the sidecar for this field. Both were withdrawn.
    An exact-match filter missed `implicit`; a normalising one missed
    `implicit:implicit:...`, an unlisted prefix, and zero-width characters — a denylist over
    caller-chosen free text, which cannot be closed by adding cases. It also caused real
    harm, silently deleting a legitimately-exported descriptor's evidence.

    The sidecar is an assistant audit artifact with no schema, and it legitimately carries
    arbitrary caller text: contributor names, document quotes, user-confirmation answers. An
    author who wants a person's name in it can write `about: "who_uploaded_this"`, which no
    filter would or should touch. Filtering keys that merely LOOK like the refused path
    therefore prevented nothing.

    What must remain true is the RECORD invariant, asserted below: the exported record makes
    no false server-stamped-identity claim. The sidecar asserts nothing about authentication.
    """
    draft["implicit"] = [
        {
            "about": UPLOADED_BY_PATH,
            "value": SPOOFED,
            "evidence": [{"source_type": "user_confirmation", "question": "Who?", "answer": SPOOFED}],
        }
    ]
    report = validate_draft(draft)
    assert report.ok, "an implicit entry is not a record-bound spelling and is not refused"

    result = export_draft(draft, ROOT, record_id=RID)
    assert result.ok
    # The sidecar DOES retain it — stated plainly rather than asserted away.
    assert f"implicit:{UPLOADED_BY_PATH}" in result.sidecar["evidence"]
    # And the record does NOT, which is the guarantee that matters.
    attribution = result.record.get("attribution")
    assert not (isinstance(attribution, dict) and "uploaded_by" in attribution)


def test_sidecar_keeps_evidence_for_lookalike_paths(draft):
    """The filter is scoped: it must not eat neighbouring evidence keys."""
    draft["fields"]["attribution.uploaded_by_someone_else"] = _evidenced("x")
    draft["block_evidence"]["attribution"] = [{"source_type": "document", "locator": "p.1"}]
    sidecar = build_sidecar(draft, transform(draft, record_id=RID))

    assert "attribution.uploaded_by_someone_else" in sidecar["evidence"]
    assert "attribution" in sidecar["evidence"]


# --------------------------------------------------------------------------- #
# 3. Regression guard: the fix must not become "delete attribution".
# --------------------------------------------------------------------------- #


def test_evidenced_contributors_still_export_intact(draft):
    """THE regression guard. Refusing `uploaded_by` must not cost us attribution.

    The golden draft's attribution is an evidenced contributor and no
    `uploaded_by`. It must still validate, still export, and still carry its
    contributor through to the official record byte-for-byte.
    """
    assert "uploaded_by" not in draft["attribution"]  # fixture precondition
    expected = copy.deepcopy(draft["attribution"]["contributors"])

    report = validate_draft(draft)
    assert report.ok, report.render()

    result = export_draft(draft, ROOT, record_id=RID)
    assert result.ok, (
        result.draft_report.render(),
        result.official_report and result.official_report.render(),
    )
    assert result.record["attribution"] == {"contributors": expected}
    # The contributor's block-level evidence still reaches the sidecar.
    assert _contributor_key(draft) in result.sidecar["evidence"]


def test_other_attribution_keys_survive_alongside_the_refusal(draft):
    """Only `uploaded_by` is dropped — sibling keys pass through untouched.

    Uses `transform` directly, because a draft carrying `uploaded_by` cannot
    reach `transform` through `export_draft`.
    """
    draft["attribution"]["uploaded_by"] = SPOOFED
    record = transform(draft, record_id=RID)
    attribution = record["attribution"]
    assert set(attribution) == {"contributors"}
    assert attribution["contributors"][0]["affiliation"] == "SSRL/SLAC"


def test_draft_without_attribution_is_unaffected(draft):
    """No attribution block at all: no new error, no emitted block, still exports."""
    contributor_key = _contributor_key(draft)  # read before removing the block
    draft.pop("attribution", None)
    draft["block_evidence"].pop(contributor_key, None)

    report = validate_draft(draft)
    assert report.ok, report.render()
    assert not _uploaded_by_errors(report)

    result = export_draft(draft, ROOT, record_id=RID)
    assert result.ok, (
        result.draft_report.render(),
        result.official_report and result.official_report.render(),
    )
    assert "attribution" not in result.record


# --------------------------------------------------------------------------- #
# 4. End to end: the refusal happens before anything is written.
# --------------------------------------------------------------------------- #


def test_export_draft_refuses_before_producing_a_record(draft):
    """`export_draft` — the function `isaac export` calls — refuses at the gate.

    `record` is None because the draft gate fires before `transform` runs, and
    `official_report` is None because the official schema was never consulted.
    The old behaviour was `ok=True` with the spoofed string in `record`.
    """
    draft["attribution"]["uploaded_by"] = SPOOFED
    result = export_draft(draft, ROOT, record_id=RID)
    assert result.ok is False
    assert result.record is None
    assert result.sidecar is None
    assert result.official_report is None
    assert _uploaded_by_errors(result.draft_report), _joined(result.draft_report)


def test_export_draft_refuses_the_fields_mechanism_before_producing_a_record(draft):
    """C1 through `export_draft` — the gate fires before `transform` runs.

    At the first-attempt commit this returned `ok=True`, a `record` carrying the
    spoofed string, and a passing `official_report`.
    """
    _drop_attribution(draft)
    draft["fields"][UPLOADED_BY_PATH] = _evidenced(SPOOFED)
    result = export_draft(draft, ROOT, record_id=RID)

    assert result.ok is False
    assert result.record is None
    assert result.sidecar is None
    assert result.official_report is None
    assert _uploaded_by_errors(result.draft_report), _joined(result.draft_report)


@pytest.mark.parametrize("mechanism", ["block", "fields"])
def test_cli_export_writes_no_record_and_no_sidecar(tmp_path, capsys, mechanism):
    """Through the real CLI: exit 1, and NOTHING on disk — no record, no sidecar.

    Parametrised over both mechanisms. The `fields` case is the end-to-end C1
    reproduction: at the first-attempt commit it exited 0, printed "PASS — valid
    against official ISAAC schema v1.05", and wrote a record whose attribution read
    `{"uploaded_by": "<spoofed>"}`.
    """
    draft = json.loads(DRAFT_PATH.read_text(encoding="utf-8"))
    if mechanism == "block":
        draft["attribution"]["uploaded_by"] = SPOOFED
    else:
        _drop_attribution(draft)
        draft["fields"][UPLOADED_BY_PATH] = _evidenced(SPOOFED)
    spoofed_draft = tmp_path / "spoofed_draft.json"
    spoofed_draft.write_text(json.dumps(draft), encoding="utf-8")
    records = tmp_path / "records"

    code = main(
        [
            "--root",
            str(ROOT),
            "export",
            str(spoofed_draft),
            "--records-dir",
            str(records),
        ]
    )
    out = capsys.readouterr().out

    assert code == 1, out
    assert not records.exists() or not list(records.glob("*.json"))
    assert "nothing exported" in out.lower()
    assert "attribution.uploaded_by" in out
    # The refusal must not echo the spoofed identity back as if it were recorded.
    assert f"{RID}.json" not in out


# ---------------------------------------------------------------------------
# Review #2 findings I-1 and I-2.
#
# Both were found by an independent adversarial reviewer AFTER the single-chokepoint
# rewrite had already fixed review #1's Critical. Recorded here as named regressions
# because each was a case of the fix's own comment overstating what the code did.
# ---------------------------------------------------------------------------


def test_transform_does_not_mutate_the_caller_draft(draft):
    """I-2: `transform` must stay total and side-effect free.

    The `fields` loop writes by reference via `set_path`, so for the whole-block spelling
    `record["attribution"]` IS the draft's own nested dict. The first version of the
    invariant popped in place and silently deleted the key from the CALLER'S draft.

    This is not theoretical: `apps/api/isaac_api/dependencies.py:68` passes the LIVE
    `exp.draft` for read-only drift detection, and `:70` documents transform as
    "read-only + total". An in-place pop would strip a stored draft and make the drift
    check non-idempotent.
    """
    draft.pop("attribution", None)
    draft["fields"]["attribution"] = {
        "value": {"uploaded_by": SPOOFED, "contributors": []},
        "status": "verified",
        "evidence": [{"source_type": "document", "locator": "p.1", "quote": SPOOFED}],
    }
    before = copy.deepcopy(draft)

    record = transform(draft, record_id=RID)

    assert draft == before, "transform mutated its input draft"
    assert "uploaded_by" in draft["fields"]["attribution"]["value"], (
        "the caller's draft lost a key — transform is not read-only"
    )
    attribution = record.get("attribution")
    assert not (isinstance(attribution, dict) and "uploaded_by" in attribution)


def test_transform_leaves_the_attribution_block_unaliased_after_refusal(draft):
    """The refusal must not hand the caller's own dict back inside the record.

    Deliberately NOT the idempotence test that stood here first: output idempotence held
    even with the mutating in-place `pop` (both runs strip the key), so it passed at the
    defective commit and guarded nothing. Review #3 caught that. Object identity is the
    property that actually distinguishes rebuild-from-pop.
    """
    draft.pop("attribution", None)
    block = {"uploaded_by": SPOOFED, "contributors": []}
    draft["fields"]["attribution"] = {
        "value": block,
        "status": "verified",
        "evidence": [{"source_type": "document", "locator": "p.1", "quote": SPOOFED}],
    }
    record = transform(draft, record_id=RID)
    assert record.get("attribution") is not block
    assert "uploaded_by" in block, "the caller's own dict was mutated"
