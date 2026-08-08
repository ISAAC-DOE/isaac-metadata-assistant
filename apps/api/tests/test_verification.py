"""Tests for the Record Verification aggregate report.

The theme of this file is that the report must not be able to assert more than
it measured. Several tests below exist because a plausible-looking
implementation would have shipped a claim nothing backed.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from isaac_api import corpus_mutation, verification
from isaac_api.disclosure import suppress_small_cells
from isaac_api.verification import (
    AUTHORIZED_PRIVATE_SAMPLE,
    LIMITATIONS,
    PUBLIC_REFERENCE,
    REPORT_FORMAT_VERSION,
    SAFEGUARD_STATES,
    VERIFICATION_MODES,
    ReportKeyError,
    _authored_strings,
    _corpus_strings,
    _leak_scan,
    _project,
    build_pending_report,
    load_public_corpus,
    run_verification,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def report() -> dict:
    """One real sweep, shared. It costs ~19s; running it per-test would not
    make the assertions stronger."""
    return run_verification(ROOT, repeat=2)


# ---------------------------------------------------------------------------
# The corpus
# ---------------------------------------------------------------------------


def test_the_corpus_is_the_public_upstream_example_set():
    """Ten records, and they must be the vendored public examples.

    `schema/PROVENANCE.md` records these as copied verbatim from the upstream
    `examples/` directory. That provenance is the entire reason this report
    needs no authorization to publish, so a change in what loads here is a
    change in the authorization argument.
    """
    records = load_public_corpus(ROOT)
    assert len(records) == 10, f"expected the ten upstream examples, got {len(records)}"
    assert all(isinstance(r, dict) for r in records)


def test_the_mode_vocabulary_is_derived_from_the_authorization_record():
    """The modes are COMPUTED, never declared here.

    Q19 was answered on 2026-08-05 (relayed; see
    `docs/evidence/2026-08-05-q19-q20-authorization.md`), so a datastore mode may
    exist -- but only for as long as the flag in `authorization.py` says so. The
    withdrawal path is absence, not a disabled switch: the authorization audit is
    explicit that a disabled runner is a runner someone enables. The drift guard
    itself lives in `test_authorization_state.py`.
    """
    from isaac_api import authorization

    assert VERIFICATION_MODES == authorization.verification_modes()
    assert VERIFICATION_MODES == (PUBLIC_REFERENCE, AUTHORIZED_PRIVATE_SAMPLE)


def test_this_module_opens_no_database_and_imports_no_driver():
    source = (Path(verification.__file__)).read_text(encoding="utf-8")
    for token in ("psycopg", "PGHOST", "PGPASSWORD", "connect(", "asyncpg"):
        assert token not in source, f"{token!r} must not appear in verification.py"


def test_this_module_does_not_import_the_export_path():
    """Backs the `export_gating_unchanged: verified` safeguard mechanically
    rather than by comment. If a future change imports the export module, this
    fails and the safeguard must be re-justified.

    Parsed with `ast` rather than grepped: a substring search matches the module
    docstring and the comment that explains this very rule, so it would fail
    against correct code -- a test that cries wolf gets deleted, and the
    safeguard would lose its only mechanical backing.
    """
    import ast

    tree = ast.parse(Path(verification.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(alias.name for alias in node.names)

    assert not any("export" in name for name in imported), sorted(imported)


# ---------------------------------------------------------------------------
# The envelope
# ---------------------------------------------------------------------------


def test_the_envelope_carries_exactly_the_frozen_keys(report):
    assert list(report) == list(verification._ENVELOPE_KEYS)
    assert report["status"] == "ok"
    assert report["report_format_version"] == REPORT_FORMAT_VERSION


def test_every_nested_block_carries_exactly_its_frozen_keys(report):
    assert list(report["metadata"]) == list(verification._METADATA_KEYS)
    assert list(report["corpus"]) == list(verification._CORPUS_KEYS)
    assert list(report["official_validation"]) == list(
        verification._OFFICIAL_VALIDATION_KEYS
    )
    assert list(report["format_shadow"]) == list(verification._FORMAT_SHADOW_KEYS)
    assert list(report["safeguards"]) == list(verification._SAFEGUARD_KEYS)
    assert list(report["mutations"]) == list(corpus_mutation._MUTATION_KEYS)
    assert list(report["oracles"]) == list(corpus_mutation._ORACLE_KEYS)


def test_an_unlisted_key_raises_on_the_success_path():
    """The projection must fail closed, not silently drop. A dropped key is how
    five aggregates shipped inside `dataset` in v0.0.32 without tripping a
    single contract test."""
    with pytest.raises(ReportKeyError):
        _project({"status": "ok", "sneaky": 1}, ("status",), strict=True)


def test_the_failure_envelope_does_not_raise():
    """It is what a raise degrades INTO. If it raised too, a broken allowlist
    would escape as an unhandled 500 with a traceback instead of a sanitized
    envelope."""
    payload = build_pending_report("running")
    assert payload["status"] == "running"
    assert list(payload) == list(verification._ENVELOPE_KEYS)
    assert payload["metadata"] is None


def test_an_unknown_pending_status_is_replaced_not_echoed():
    """The natural caller is `except Exception as exc: build_pending_report(
    str(exc))`, which would put a path or a record value straight into the
    response."""
    assert build_pending_report("/Users/someone/secret/path")["status"] == "error"
    assert build_pending_report("ok")["status"] == "error"


# ---------------------------------------------------------------------------
# No record content
# ---------------------------------------------------------------------------


def test_no_record_string_reaches_the_served_payload(report):
    """The leak scan, re-run here independently of the safeguard it sets, so a
    bug in the safeguard cannot hide a bug in the report."""
    records = load_public_corpus(ROOT)
    assert _leak_scan(report, records, ROOT)


def test_the_leak_scan_actually_catches_a_planted_value():
    """A scan that never fires proves nothing. This is the negative control:
    without it, `private_values_exposed: verified` could be produced by a scan
    that had been weakened into a no-op.
    """
    records = load_public_corpus(ROOT)
    canary = records[0]["record_id"]
    assert len(canary) >= 8, "the canary must be long enough to be scanned for"
    leaky = {"limitations": [], "oops": canary}
    assert not _leak_scan(leaky, records, ROOT), (
        "a planted record value was not detected; the scan is not doing its job"
    )


def test_authored_strings_do_not_swallow_a_real_record_value():
    """The authored-string subtraction is what stops the safeguard reading
    `unverified` forever. It must not be so broad that it also excuses genuine
    record content."""
    records = load_public_corpus(ROOT)
    authored = _authored_strings()
    _, declared = __import__(
        "isaac_api.format_shadow", fromlist=["_introspect_root"]
    )._introspect_root(ROOT)
    private = _corpus_strings(records, declared)
    survivors = private - authored
    assert len(survivors) > 100, (
        "the authored-string set is too broad -- it removed most of the corpus "
        f"vocabulary from the scan (survivors: {len(survivors)})"
    )
    assert records[0]["record_id"] in survivors


def test_the_leak_scan_catches_a_NON_ASCII_record_value():
    """C1 REGRESSION. The scan used to be blind to every non-ASCII value.

    It compared each candidate against `json.dumps(payload, sort_keys=True)`,
    and `json.dumps` defaults to `ensure_ascii=True` -- so a corpus value
    containing an arrow appeared in that text as the seven characters
    `\\u2192` while the candidate was still the raw one-character Python
    string, and `value in serialized` was PERMANENTLY FALSE. The report went on
    publishing `private_values_exposed: "verified"`.

    Measured on the shipped ten-record public corpus: 3 of the 392 candidate
    strings are already non-ASCII. Chemistry metadata makes this ordinary, not
    exotic.

    This test plants such a value into a served histogram cell and requires the
    scan to fire. Before the fix it returned True.
    """
    records = load_public_corpus(ROOT)
    _, declared = __import__(
        "isaac_api.format_shadow", fromlist=["_introspect_root"]
    )._introspect_root(ROOT)
    candidates = verification._corpus_strings(records, declared) - _authored_strings()

    non_ascii = sorted(v for v in candidates if any(ord(ch) > 127 for ch in v))
    assert non_ascii, (
        "the public corpus no longer contains a non-ASCII value; pick another "
        "JSON-escaped character (a quote, a backslash, a newline) instead"
    )

    leaky = {
        "limitations": [],
        "format_shadow": {
            "failures_by_schema_path": {"cells": [{"key": non_ascii[0], "count": 9}]}
        },
    }
    assert not _leak_scan(leaky, records, ROOT), (
        "a non-ASCII record value was not detected; the scan is comparing "
        "against escaped JSON text again"
    )


@pytest.mark.parametrize("ch", ['"', "\\", "\n", "\t"])
def test_the_leak_scan_catches_a_value_containing_a_json_escaped_character(ch):
    """The same defect, in its other three forms. `ensure_ascii=False` alone
    would have fixed the arrow and left these broken, which is why the fix walks
    decoded string leaves instead of serializing at all."""
    planted = f"SYNTHETIC{ch}RECORD{ch}VALUE{ch}ZZ9"
    fake_records = [{"note": planted}]
    leaky = {"limitations": [], "oops": planted}
    assert not _leak_scan(leaky, fake_records, ROOT)


def test_no_instance_path_histogram_is_served(report):
    """`by_instance_path` shipped in v0.0.32 and was withdrawn: over a small
    corpus an error count of 1 at an instance path is a single-record fact.
    Do not rebuild it."""
    serialized = json.dumps(report)
    assert "instance_path" not in serialized
    assert "by_instance_path" not in serialized
    assert "path_presence" not in serialized


# ---------------------------------------------------------------------------
# Histograms
# ---------------------------------------------------------------------------


def test_every_published_histogram_cell_is_at_or_above_the_floor(report):
    for name in ("failures_by_error_code", "failures_by_schema_path"):
        hist = report["format_shadow"][name]
        assert hist["floor"] == 5
        for cell in hist["cells"]:
            assert cell["count"] >= hist["floor"], (name, cell)


def test_a_histogram_never_withholds_exactly_one_category_while_publishing(report):
    """The differencing defence, asserted on the served shape rather than only
    on the function that implements it."""
    for name in ("failures_by_error_code", "failures_by_schema_path"):
        hist = report["format_shadow"][name]
        if hist["cells"]:
            assert hist["suppressed_categories"] != 1, (name, hist)


def test_a_single_withheld_category_never_serves_its_exact_count():
    """THE DELEGATED DUTY, DISCHARGED — and this test is why it now is.

    `disclosure.py`'s module docstring ends by handing the decision to whoever
    publishes: *"The caller is responsible for not publishing a histogram whose
    universe is a single key … returns the honest numbers and the caller
    withholds the whole block."* `_histogram` is that caller, and it used to
    copy `suppressed_total` straight onto the wire. So `{"X": 1}` served
    `{"cells": [], "suppressed_categories": 1, "suppressed_total": 1,
    "floor": 5}` — one key's exact count against a universe (shadow error codes,
    schema paths) an observer enumerates from the public schema. Over the
    authorized 30-record corpus, one record with one format finding produces
    exactly that body.

    The served total is now `None`. Note what is NOT asserted here, because
    `disclosure.py` names both alternatives as false claims: the total is not
    `0`, and `suppressed_categories` is not reduced. The withholding stays
    disclosed; only the recoverable figure goes.
    """
    for counts, occurrences in (({"ISAAC_SHADOW_FORMAT_DATE": 1}, 1), ({"X": 3}, 3)):
        served = verification._histogram(suppress_small_cells(counts))
        assert served["cells"] == []
        assert served["suppressed_categories"] == 1, (
            "the withholding must stay visible; hiding it would be the '0 withheld' "
            "false claim disclosure.py rejects by name"
        )
        assert served["suppressed_total"] is None, (
            f"served the withheld key's exact count ({occurrences}); with one "
            "category withheld from an enumerable universe that IS the cell"
        )
        assert served["suppressed_total"] != 0, "zeroing it is a differently false claim"
        assert set(served) == set(verification._HISTOGRAM_KEYS), (
            "all four frozen keys stay present -- the strict projection requires it, "
            "and a dropped key would be an undisclosed withholding"
        )


def _served_format_shadow(
    by_code: dict[str, int], by_schema_path: dict[str, int], *, records_scanned: int
) -> dict:
    """The SERVED `format_shadow` block for a hand-built pair of distributions.

    Goes through `build_report` rather than calling `_histogram` twice, because
    the property under test is a relationship BETWEEN the two histograms and the
    block builder is the only place that sees both. A test that drove
    `_histogram` directly would pass against code that still leaks.
    """
    sweep = verification._SweepResult(schema_fingerprint="not-a-real-fingerprint")
    sweep.corpus.update(
        {
            "records_scanned": records_scanned,
            "records_passing_baseline": 0,
            "records_failing_baseline": records_scanned,
        }
    )
    sweep.by_code = Counter(by_code)
    sweep.by_schema_path = Counter(by_schema_path)
    report = verification.build_report(
        sweep=sweep,
        mode=PUBLIC_REFERENCE,
        provider=None,
        records=None,
        duration_ms=0,
        root=ROOT,
    )
    return report["format_shadow"]


def test_a_withheld_total_is_not_recoverable_from_the_sibling_histogram():
    """THE REVIEWER'S REPRODUCTION. Withholding one total is not enough.

    `_sweep` increments `by_code` and `by_schema_path` ONCE PER FINDING
    (`verification.py`, the `for finding in shadow.findings` loop), so by
    construction

        sum(by_code) == sum(by_schema_path) == F

    where F is the total number of format findings. Every served histogram then
    satisfies `F = sum(published cells) + suppressed_total`. So a total withheld
    on ONE histogram is recoverable by arithmetic the moment the OTHER publishes
    one: `withheld = F - sum(cells)`.

    Two records with a `date-time` violation at two DIFFERENT pointers is enough,
    and it is an ordinary shape rather than a contrived one: the shadow error
    code vocabulary is closed and small (many pointers map to one code) while the
    schema paths are distinct. Before this fix the block served

        failures_by_error_code:  cells [] categories 1 total null
        failures_by_schema_path: cells [] categories 2 total 2

    -- the withheld figure printed adjacent to the withholding, on one screen.

    The fix is cross-histogram because the leak is: EITHER histogram reaching one
    category withholds the total on BOTH, since the two totals are the same
    number by construction.
    """
    shadow = _served_format_shadow(
        {"ISAAC_SHADOW_FORMAT_DATE_TIME": 2},
        {
            "properties/collection/properties/date/format": 1,
            "properties/processing/properties/date/format": 1,
        },
        records_scanned=2,
    )
    by_code = shadow["failures_by_error_code"]
    by_path = shadow["failures_by_schema_path"]

    assert by_code["cells"] == [] and by_path["cells"] == [], (
        "the premise of the arithmetic: with no published cells the withheld "
        "total IS F, so publishing either one publishes both"
    )
    assert by_code["suppressed_categories"] == 1
    assert by_path["suppressed_categories"] == 2, (
        "the sibling is at two categories, which is exactly why the "
        "single-histogram rule considered it safe to publish"
    )
    assert by_code["suppressed_total"] is None
    assert by_path["suppressed_total"] is None, (
        "served the sibling's total (2) while the other histogram withheld the "
        "same number; `F - sum(cells)` recovers the withheld figure exactly"
    )
    # Both `suppressed_categories` values are unchanged and still real: the
    # withholding stays disclosed on both sides, which is the whole difference
    # between this and the "0 withheld" false claim `disclosure.py` rejects.
    assert by_code["suppressed_categories"] == 1
    assert by_path["suppressed_categories"] == 2


def test_the_record_counts_do_not_reconstruct_the_finding_total():
    """Why nulling both totals actually removes F, checked rather than asserted.

    The remaining served integers that might carry F are `records_failing` and
    `official_validation.failing`. Both count RECORDS; F counts FINDINGS, and a
    record may carry several. So the record counts are a LOWER BOUND on F and not
    F itself -- stated at exactly that strength, because in the reproduction
    above the two happen to coincide numerically (two records, one finding each).
    Coincidence at one corpus shape is not derivability, and this case shows the
    bound is not tight: one record, three findings, three schema paths.
    """
    shadow = _served_format_shadow(
        {"ISAAC_SHADOW_FORMAT_DATE_TIME": 3},
        {"a/format": 1, "b/format": 1, "c/format": 1},
        records_scanned=1,
    )
    assert shadow["records_failing"] == 1
    assert shadow["failures_by_error_code"]["suppressed_total"] is None
    assert shadow["failures_by_schema_path"]["suppressed_total"] is None
    # F is 3. Nothing served says so.
    assert 3 not in (shadow["records_passing"], shadow["records_failing"])


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        # Two sub-floor keys: the differencing attack does not apply, so the
        # honest total is served exactly as before.
        ({"A": 1, "B": 2}, {"cells": [], "suppressed_categories": 2, "suppressed_total": 3}),
        # Nothing observed: nothing withheld, and 0 here is measured, not a
        # stand-in for an unknown.
        ({}, {"cells": [], "suppressed_categories": 0, "suppressed_total": 0}),
        # Everything at or above the floor: no suppression at all.
        (
            {"A": 9, "B": 7},
            {
                "cells": [{"key": "A", "count": 9}, {"key": "B", "count": 7}],
                "suppressed_categories": 0,
                "suppressed_total": 0,
            },
        ),
        # ONE KEY WITH A COUNT OF ZERO. Nothing is actually withheld -- the
        # withheld bucket sums to 0 -- yet `suppressed_categories` is 1, so the
        # rule fires and the total is nulled. This is OVER-withholding, and it is
        # pinned rather than left to chance: a future refactor that "corrects" it
        # into publishing `0` would reintroduce the leak, because from outside
        # the report a served `0` and a served `1` are the same channel. `null`
        # here costs nothing, since 0 withheld occurrences is not a fact any
        # reader needs.
        ({"A": 0}, {"cells": [], "suppressed_categories": 1, "suppressed_total": None}),
    ],
)
def test_the_safe_histogram_shapes_are_unchanged(counts, expected):
    """The withholding is narrow ON PURPOSE, and this pins how narrow.

    Called WITHOUT `withhold_total`, `suppressed_total` goes to `None` for
    `suppressed_categories == 1` and for nothing else. A fix that nulled the
    total whenever anything was withheld would destroy a figure that is safe to
    publish and would make every breakdown less informative than the floor
    requires. (The cross-histogram rule that CAN null a two-category total lives
    in `build_report`, not here, and is pinned by
    `test_a_withheld_total_is_not_recoverable_from_the_sibling_histogram`.)
    """
    served = verification._histogram(suppress_small_cells(counts))
    assert served == {**expected, "floor": 5}


@pytest.mark.parametrize("counts", [{"A": 1, "B": 2}, {"A": 9, "B": 7}, {}])
def test_the_cross_histogram_flag_nulls_a_total_this_histogram_would_publish(counts):
    """The forced case, isolated from the block builder that decides it.

    Each of these shapes publishes an honest `suppressed_total` on its own. With
    `withhold_total=True` -- what `build_report` passes when the SIBLING
    histogram reached one category -- the number goes and nothing else moves.

    These are FLAG MECHANICS, not served bodies. In a real report the forced case
    always arrives with `cells == []` on both sides, because one category implies
    a single sub-floor key and therefore `F < floor`, which puts every sibling
    cell under the floor as well. The published-cell rows here exercise the flag
    in isolation so a refactor cannot make it conditional on the cells.
    """
    hist = suppress_small_cells(counts)
    alone = verification._histogram(hist)
    forced = verification._histogram(hist, withhold_total=True)

    assert alone["suppressed_total"] is not None
    assert forced["suppressed_total"] is None
    assert {k: v for k, v in forced.items() if k != "suppressed_total"} == {
        k: v for k, v in alone.items() if k != "suppressed_total"
    }, "only the total may change; cells, categories and floor are untouched"


# ---------------------------------------------------------------------------
# Safeguards -- the truthfulness-critical block
# ---------------------------------------------------------------------------


def test_every_safeguard_state_is_one_of_the_three_words(report):
    safeguards = report["safeguards"]
    for key in verification._SAFEGUARD_KEYS:
        value = safeguards[key]
        if key in ("dml_statements", "ddl_statements"):
            assert isinstance(value, int) and not isinstance(value, bool)
        else:
            assert value in SAFEGUARD_STATES, (key, value)
            assert value is not True, "a bare True is how 'verified' gets invented"


def test_database_safeguards_are_not_applicable_because_no_database_was_contacted(
    report,
):
    """THE most important assertion in this file.

    `transaction_read_only: "verified"` would be a claim about an event that
    never happened -- no connection is opened in this mode. Reporting a
    safeguard as verified when it was never exercised is the exact class of
    false claim `CLAUDE.md` §15 records this project shipping and correcting.
    """
    safeguards = report["safeguards"]
    assert safeguards["transaction_read_only"] == "not_applicable"
    assert safeguards["parameterized_queries_only"] == "not_applicable"
    assert safeguards["dml_statements"] == 0
    assert safeguards["ddl_statements"] == 0


def test_source_records_modified_is_measured_by_the_oracle_not_asserted(report):
    """It must track the harness oracle. If the oracle ever reports a mutation,
    the safeguard must degrade rather than keep saying `verified`."""
    assert report["oracles"]["source_mutation_failures"] == 0
    assert report["safeguards"]["source_records_modified"] == "verified"


def test_official_validator_unchanged_is_a_runtime_measurement():
    """It reads the live validator, so arming format enforcement globally would
    flip this on the running deployment and not only in a unit test."""
    assert verification._official_validator_is_unchanged(ROOT) is True


# ---------------------------------------------------------------------------
# The numbers
# ---------------------------------------------------------------------------


def test_the_official_validator_still_passes_every_upstream_example(report):
    assert report["official_validation"]["passing"] == 10
    assert report["official_validation"]["failing"] == 0


def test_the_format_shadow_is_reported_separately_from_official_validation(report):
    """The shadow is stricter and advisory. Its verdict must never be folded
    into the official one -- Q20 is unanswered and arming enforcement is not
    this feature's decision to make."""
    assert "records_passing" in report["format_shadow"]
    assert report["format_shadow"]["records_passing"] <= report["metadata"][
        "corpus_size"
    ]


def test_the_mutation_sweep_found_no_unexpected_outcome(report):
    assert report["mutations"]["unexpected_outcomes"] == 0
    assert report["mutations"]["trials_applicable"] > 0
    for key, value in report["oracles"].items():
        assert value == 0, f"oracle {key} failed {value} times"


def test_metadata_is_honest_about_which_corpus_ran(report):
    meta = report["metadata"]
    assert meta["verification_mode"] == PUBLIC_REFERENCE
    assert meta["corpus_size"] == 10
    assert meta["duration_ms"] > 0
    assert meta["generated_at"].endswith("Z")


def test_limitations_are_fixed_constants_carrying_nothing_interpolated():
    """The leak scan blanks `limitations` before scanning, which is only safe
    while nothing record-derived can enter it. This pins that."""
    assert isinstance(LIMITATIONS, tuple)
    for line in LIMITATIONS:
        assert isinstance(line, str)
        assert "{" not in line and "%s" not in line
