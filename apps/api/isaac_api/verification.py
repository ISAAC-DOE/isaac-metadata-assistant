"""Record Verification — the sanitized aggregate report served to Statistics.

WHAT THIS IS. One report combining three independent programs over a corpus of
official ISAAC records:

1. **Official validation** — ``isaac_records.official.validate_official``. The
   authority. This module reads its verdict and changes nothing about it.
2. **Format shadow** — ``format_shadow.shadow_validate``. Stricter than the
   official validator because it checks JSON Schema ``format``. Advisory ONLY:
   its verdict never becomes validity, never gates export, and never overrides
   the official result. Q20 in ``docs/dean-authorization-packet.md`` is the
   still-unanswered question about arming enforcement globally
   (``authorization.Q20_FORMAT_ENFORCEMENT_APPROVED`` is ``False``); this module
   does not pre-empt it, and ``tests/test_truthpath_characterization.py`` proves
   it.
3. **Mutation harness** — ``corpus_mutation``. Deep-clones each record, applies a
   schema-derived operator catalog, and checks seven oracles.

TWO MODES, ONE ENGINE
=====================
``VERIFICATION_MODES`` now has two members and they differ in **exactly one
thing: where the records come from.**

* :data:`PUBLIC_REFERENCE` — the ten upstream ISAAC examples vendored at
  ``tests/fixtures/official/``, already public on GitHub
  (``schema/PROVENANCE.md``). Needs no authorization at all.
* :data:`AUTHORIZED_PRIVATE_SAMPLE` — records streamed from the application's
  own datastore by an injected provider. Authorized on 2026-08-05; the machine-
  readable record of *what* was authorized, and of the twelve constraints that
  came with it, is ``authorization.py``.

The mode list is COMPUTED from ``authorization.verification_modes()``. It is not
a literal here and must never become one: the whole point is that clearing the
approval flag deletes the mode rather than disabling it, and
``test_authorization_state.py`` fails if the two ever drift apart.

Everything after the record arrives is identical between the modes — the same
validator, the same shadow, the same operator catalog, the same oracles, the same
suppression, the same frozen allowlists. There is no second code path to keep in
step, which is the only reason a private-corpus mode is safe to add at all.

WHY THE SUPPRESSION RUNS IN BOTH MODES. Every histogram is projected through
``disclosure.suppress_small_cells``, unconditionally, even though the public
corpus needs no such protection. Dean's guide is explicit that a visibility
boundary belongs in the read path from the start rather than bolted on afterwards
(``docs/postgres-test-db-guide.md:158-162``). A gate that arms only for the
private corpus is a gate someone forgets to arm.

NO DATABASE **HERE**. This module opens no connection, imports no driver and
knows no hostname. It never constructs a provider; one is injected, or the run
reports ``unavailable``. Scoped to THIS MODULE, per ``CLAUDE.md`` §15:
``db_provider.py`` and ``db_recon.py`` do reach the datastore from the pod, so
the honest form is "no connection is opened here", never "the database has never
been contacted".
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from isaac_records.official import EXPECTED_VERSION, validate_official

from . import authorization, corpus_mutation
from .disclosure import MIN_CELL_SIZE, SuppressedHistogram, suppress_small_cells
from .format_shadow import shadow_validate

__all__ = [
    "AUTHORIZED_PRIVATE_SAMPLE",
    "PUBLIC_REFERENCE",
    "REPORT_FORMAT_VERSION",
    "VERIFICATION_MODES",
    "VerificationState",
    "build_report",
    "build_pending_report",
    "limitations_for",
    "load_public_corpus",
    "run_verification",
]

#: Bumped from ``corpus_mutation.REPORT_FORMAT_VERSION`` (1) because this
#: envelope is a superset: it adds ``metadata``, ``official_validation``,
#: ``format_shadow`` and ``safeguards``.
#:
#: NOT bumped by the two-mode change, and the reason is narrower than an earlier
#: revision of this comment claimed. That revision said "only the closed
#: ``verification_mode`` vocabulary gained a member" — which was FALSE, and is
#: recorded rather than replaced. The vocabulary also had its existing member
#: **renamed**: ``public_upstream_corpus`` -> ``public_reference``. A rename
#: inside a closed vocabulary is normally breaking, because a consumer switching
#: on the old value silently stops matching.
#:
#: It is judged non-breaking here on facts, not on principle:
#:
#: 1. The key set, every block shape and every value type are unchanged, so no
#:    consumer has to parse anything new.
#: 2. Nothing outside this repository consumes the field. The only consumer is
#:    ``apps/web``, which renders ``verification_mode`` VERBATIM as a disclosure
#:    and switches on nothing; its contract literal was updated in the same
#:    change.
#: 3. No published build can pair a new server value with an old client
#:    literal. This point has been RE-GROUNDED, and the old ground is recorded
#:    rather than deleted. It used to read: "No build carrying the old value was
#:    ever released. CI is billing-blocked, so no image has published and
#:    nothing has merged since the old name existed — there is no deployed
#:    reader to break." That EXPIRED on 2026-08-07, when the org-wide billing
#:    block ended: Actions execute again, this work has merged, and the
#:    publish-blocking premise no longer holds (no rollout has been OBSERVED
#:    from a development environment, which is a weaker statement than "none
#:    happened" and must not be used as one). The judgement survives on a
#:    fact that does not expire the same
#:    way — the sole consumer, ``apps/web``, is built into the SAME image as
#:    this module and ships with it, so server and client literal move
#:    together and no deployment can hold a stale reader. An independently
#:    deployed or external consumer would break that argument; none exists.
#:
#: If any of those three stops holding, bump to 3. Point 3 in particular is
#: contingent: it lasts exactly as long as the only consumer ships in the same
#: image as this module.
#:
#: BUMPED TO 3 by the single-category withholding in :func:`_histogram`. What
#: changed is one value TYPE and nothing else: ``suppressed_total`` is now
#: ``int | null`` where it was always ``int``. It is ``null`` when EITHER
#: ``format_shadow`` histogram reaches ``suppressed_categories == 1``, and then
#: on BOTH of them. The first half is because the honest numbers
#: ``disclosure.suppress_small_cells`` returns are then a single key's exact
#: count against an enumerable universe, and this module is the caller that
#: module's docstring delegates the withholding to. The second half is because
#: the two histograms count the same findings, so their totals are one number
#: and the sibling would republish by subtraction what the other withheld —
#: see the comment in :func:`build_report`.
#:
#: What did NOT change, stated so a consumer knows the blast radius: the key set
#: of every block is identical, no block was added or removed, all four
#: ``_HISTOGRAM_KEYS`` are still present on every histogram,
#: ``suppressed_categories`` is still an ``int`` and still reports the real
#: number of withheld categories, and no other field became nullable. A consumer
#: that reads ``suppressed_total`` as a number must now handle ``null``; one that
#: does not read it is unaffected.
#:
#: Unlike the two-mode change above, this one IS breaking on its own terms — a
#: reader doing arithmetic on ``suppressed_total`` gets a type error rather than
#: a wrong number — so it is versioned rather than argued around. The only
#: consumer remains ``apps/web``, whose contract was updated in the same change.
REPORT_FORMAT_VERSION = 3

#: The mode names, re-exported from the authorization record so there is one
#: spelling of each. Do NOT inline the string literals.
PUBLIC_REFERENCE = authorization.PUBLIC_REFERENCE_MODE
AUTHORIZED_PRIVATE_SAMPLE = authorization.AUTHORIZED_PRIVATE_SAMPLE_MODE

#: DERIVED, never declared. See the module docstring.
VERIFICATION_MODES: tuple[str, ...] = authorization.verification_modes()

#: Where the public upstream examples live, relative to the repository root.
#: The Dockerfile COPY allowlist must include this path or the deployed pod
#: reports ``unavailable`` rather than guessing.
PUBLIC_CORPUS_DIR = Path("tests") / "fixtures" / "official"

#: A recomputation is offered at most this often. The sweep costs ~19s over ten
#: records, so it never runs inside a request — see :class:`VerificationState`.
CACHE_TTL_SECONDS = 3600

#: A refresh is never STARTED more often than this, regardless of TTL, staleness
#: or how many callers ask. It is what stops a failing source from being
#: retried on every request: in the private mode each start is a connection, and
#: the deployment's connection limit is 5.
MIN_REFRESH_INTERVAL_SECONDS = 60

#: Minimum length of a corpus string worth leak-scanning for. Shorter values
#: ("Cu", "2.5", "eV") collide with legitimate report content — schema path
#: segments and error codes — and would make the scan cry wolf rather than
#: catch anything.
_LEAK_SCAN_MIN_LENGTH = 8

#: Planted, one at a time, into COPIES of the finished payload to prove the
#: structural audit is not a no-op. Never planted into the real payload, never
#: into a record, and never served. See :func:`_canary_is_detected`.
#:
#: Each entry stands for a SHAPE that a record value plausibly has, because a
#: canary is only as strong as the weakest admission rule it can defeat:
#:
#: * an obvious sentence — the trivial case;
#: * a sha256-shaped digest — what a ``raw_data`` pointer looks like;
#: * a short hex string — what the old ``^[0-9a-f]{8,64}$`` rule admitted;
#: * an RFC 3339 timestamp — what ``timestamps.created_utc`` looks like;
#: * a schema-pointer-shaped string that does NOT resolve.
_CANARY_SENTINELS: tuple[str, ...] = (
    "ISAAC_CANARY_SENTINEL_MUST_NEVER_BE_SERVED_ZZ9",
    "9f" * 32,
    "deadbeef",
    "2019-03-14T09:12:44Z",
    "/properties/isaac_canary_not_a_real_property_zz9",
)


# --------------------------------------------------------------------------
# Frozen allowlists. Same discipline as `corpus_mutation` and `db_recon`:
# an unlisted key can never be served, and on the success path it RAISES.
# --------------------------------------------------------------------------

_ENVELOPE_KEYS: tuple[str, ...] = (
    "status",
    "report_format_version",
    "schema_version",
    "schema_fingerprint",
    "metadata",
    "corpus",
    "official_validation",
    "format_shadow",
    "mutations",
    "oracles",
    "safeguards",
    "limitations",
)

_METADATA_KEYS: tuple[str, ...] = (
    "generated_at",
    "duration_ms",
    "corpus_size",
    "cache_age_seconds",
    "verification_mode",
)

_CORPUS_KEYS: tuple[str, ...] = (
    "records_scanned",
    "records_passing_baseline",
    "records_failing_baseline",
)

_OFFICIAL_VALIDATION_KEYS: tuple[str, ...] = ("passing", "failing")

_FORMAT_SHADOW_KEYS: tuple[str, ...] = (
    "records_passing",
    "records_failing",
    "failures_by_error_code",
    "failures_by_schema_path",
)

_HISTOGRAM_KEYS: tuple[str, ...] = (
    "cells",
    "suppressed_categories",
    "suppressed_total",
    "floor",
)

_SAFEGUARD_KEYS: tuple[str, ...] = (
    "transaction_read_only",
    "parameterized_queries_only",
    "dml_statements",
    "ddl_statements",
    "source_records_modified",
    "private_values_exposed",
    "official_validator_unchanged",
    "export_gating_unchanged",
)

#: The three values a tri-state safeguard may take. A bare ``True`` is NOT a
#: member, deliberately: "read-only transaction: verified" when no transaction
#: was ever opened is the exact class of false claim this project has shipped
#: and corrected repeatedly (``CLAUDE.md`` §15).
SAFEGUARD_STATES: tuple[str, ...] = ("verified", "not_applicable", "unverified")

#: Statuses :func:`build_pending_report` may emit. Frozen so a caller's
#: ``str(exc)`` can never become a status.
PENDING_STATUSES: tuple[str, ...] = ("running", "unavailable", "error", "refused")

#: Limitations true of BOTH modes.
LIMITATIONS: tuple[str, ...] = (
    "The format shadow is advisory. It does not decide validity, does not gate "
    "export, and does not change what the official validator accepts.",
    "Histogram cells below the floor are withheld, and the number of withheld "
    "categories is never exactly one while any cell is published — one withheld "
    "key against an enumerable universe is identified by elimination. Where "
    "exactly one category is withheld and nothing is published, the number of "
    "withheld occurrences is itself withheld and reported as null, because that "
    "number would be that one category's exact count.",
    "Failure paths are SCHEMA paths. The per-record instance-path breakdown is "
    "computed internally and deliberately not served: over a small corpus a "
    "count of one at an instance path is a single-record fact.",
    "Mutation counts are global scalars. Per-operator and per-category "
    "breakdowns are absent because mutation applicability is a fact about a "
    "record's structure, so a breakdown is a field-presence map.",
    # This line USED to name `authorized_private_sample` and was published in
    # BOTH modes. With the approval flag cleared the engine goes completely
    # clean — the mode is refused everywhere and no connection can be opened —
    # and yet every served report would still have told its reader that a
    # datastore mode exists. That is a false disclosure surviving the exact
    # withdrawal path this design's headline claim is about, so the sentence now
    # says only what is true of this module in every build, and the datastore
    # half moved into `_MODE_LIMITATIONS[AUTHORIZED_PRIVATE_SAMPLE]`.
    "This module opens no connection and imports no driver. Where records are "
    "not read from this repository, they arrive from an injected read-only "
    "provider, which is the component that reaches any external source.",
)

#: Limitations true of ONE mode. Fixed constants, nothing interpolated — the
#: leak scan blanks ``limitations`` before scanning, which is only sound while
#: nothing record-derived can enter it.
_MODE_LIMITATIONS: dict[str, tuple[str, ...]] = {
    PUBLIC_REFERENCE: (
        "The corpus is the public upstream ISAAC example records vendored at "
        "tests/fixtures/official/. It is not the production-derived corpus, and "
        "no figure here describes production data.",
    ),
    AUTHORIZED_PRIVATE_SAMPLE: (
        "The records for the authorized_private_sample mode arrive from an "
        "injected read-only provider, which is the component that reaches the "
        "datastore; this module still opens no connection and imports no driver.",
        "The corpus is a bounded sample of the application's own datastore, read "
        "under the authorization recorded in "
        "docs/evidence/2026-08-05-q19-q20-authorization.md. Every figure is an "
        "aggregate; no record id, title, field value or per-record outcome is "
        "computed into this report.",
        "It is a SAMPLE, not a census: the read is bounded by a fixed row cap and "
        "rows whose payload will not parse are skipped, so corpus_size may be "
        "smaller than the table.",
        "Cross-references to records outside the sample are expected and are "
        "neither followed, repaired nor counted.",
    ),
}


def limitations_for(mode: str) -> tuple[str, ...]:
    """The limitations to publish for ``mode``: mode-specific first, then shared.

    An unknown mode contributes nothing rather than raising: this is called while
    building a response, and a raise here would turn a naming mistake into a 500.
    """
    return tuple(_MODE_LIMITATIONS.get(mode, ())) + LIMITATIONS


class ReportKeyError(KeyError):
    """An allowlist violation. Never carries a key that came from a record."""


def _project(
    built: Mapping[str, Any], allowlist: Sequence[str], *, strict: bool
) -> dict:
    """Project ``built`` onto ``allowlist``, key by key.

    Mirrors ``corpus_mutation._project`` exactly, including the asymmetry: the
    success path raises on an extra or missing key, the failure envelope does
    not. The failure envelope is what a raise degrades INTO; if it raised too, a
    broken allowlist would escape as an unhandled traceback instead of a
    sanitized response.
    """
    if strict:
        extra = sorted(set(built) - set(allowlist))
        if extra:
            raise ReportKeyError(f"key not on the frozen allowlist: {extra[0]!r}")
        missing = sorted(set(allowlist) - set(built))
        if missing:
            raise ReportKeyError(f"required key missing from block: {missing[0]!r}")
        return {key: built[key] for key in allowlist}
    return {key: built.get(key) for key in allowlist}


def _histogram(hist: SuppressedHistogram, *, withhold_total: bool = False) -> dict:
    """Serve a suppressed histogram, withholding a recoverable total.

    WHAT THIS DOES AND DOES NOT DO, stated precisely because the two are easy to
    conflate. ``disclosure.py`` (module docstring, "THE ONE CASE THIS CANNOT
    FIX") hands a decision to whoever publishes: *"The caller is responsible for
    not publishing a histogram whose universe is a single key … returns the
    honest numbers and the caller withholds the whole block."* This function is
    that caller. It does **not** withhold the whole block — it withholds one
    field, ``suppressed_total``, and serves the rest. That is a narrower remedy
    than ``disclosure.py`` describes, and it is chosen deliberately: with
    ``cells`` empty (the only shape that reaches the single-category case) the
    remaining fields are ``suppressed_categories``, which is the disclosure of
    the withholding itself, and ``floor``, which is a published constant. The
    number that identified a cell is gone; nothing else in the block does.

    Until this change the function withheld nothing — it copied
    ``suppressed_total`` straight onto the wire. So for the one input shape that
    reaches ``suppressed_categories == 1`` (a single key whose count is below
    the floor, the only shape the absorption loop cannot break up) the served
    block carried that key's EXACT count against a universe — schema paths and
    ``format_shadow.SHADOW_ERROR_CODES`` — an observer can enumerate. Over a
    ~30-record corpus one record with one format finding produces exactly that.

    ``suppressed_total`` therefore becomes ``None``. It is deliberately NOT the
    two alternatives ``disclosure.py`` names by name — reporting ``0`` withheld
    is a false claim, and zeroing ``suppressed_total`` is a differently false
    one. ``suppressed_categories`` stays at its real value, so the report still
    says that something was withheld; only the recoverable figure goes.

    ``withhold_total`` FORCES that same withholding on a histogram whose own
    category count is 2 or more. This function cannot see the reason on its own,
    because the reason is a relationship between two histograms rather than a
    property of either: :func:`build_report` serves ``failures_by_error_code``
    and ``failures_by_schema_path`` over the SAME findings, so their totals are
    one number, and publishing one publishes the other by subtraction. The
    caller decides; see the comment at the call site.

    All four frozen keys are still present. ``_HISTOGRAM_KEYS`` is projected
    strictly, and a key dropped rather than nulled would raise.
    """
    withheld_total: int | None = hist.suppressed_total
    if withhold_total or hist.suppressed_categories == 1:
        withheld_total = None
    return _project(
        {
            "cells": [{"key": key, "count": count} for key, count in hist.cells],
            "suppressed_categories": hist.suppressed_categories,
            "suppressed_total": withheld_total,
            "floor": hist.floor,
        },
        _HISTOGRAM_KEYS,
        strict=True,
    )


# --------------------------------------------------------------------------
# Corpus
# --------------------------------------------------------------------------


def load_public_corpus(root: Path) -> tuple[dict, ...]:
    """Load the vendored public upstream examples, sorted by filename.

    Sorted so the sweep is deterministic: the harness iterates records in the
    order given, and an unordered filesystem listing would make ``duration_ms``
    and any future per-record ordering vary between runs for no reason. A file
    that will not parse is SKIPPED rather than raising — one bad fixture should
    degrade the corpus, not delete the whole report — and the shortfall is
    visible as ``corpus_size`` below the directory's file count.
    """
    directory = Path(root) / PUBLIC_CORPUS_DIR
    if not directory.is_dir():
        return ()
    records: list[dict] = []
    for path in sorted(directory.glob("*.json")):
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
    return tuple(records)


# --------------------------------------------------------------------------
# Privacy measurements
# --------------------------------------------------------------------------


def _corpus_strings(
    records: Iterable[Mapping[str, Any]], declared: frozenset[str]
) -> frozenset[str]:
    """The corpus strings that would be a DISCLOSURE if they were served.

    The distinction that makes this scan mean something:

    * **Record values are private.** Every string leaf counts.
    * **Schema-declared property names are public.** ``timestamps``,
      ``created_utc`` and the rest are in the vendored schema, which anyone can
      read; they are also, unavoidably, the segments of every schema path this
      report serves. Counting them as private would make the scan fire on
      ``failures_by_schema_path`` the moment the corpus has a single failure —
      a permanent false alarm, which is how a safeguard stops being read.
    * **UNDECLARED keys are private.** A key the schema does not declare came
      from the record — that is the open-map case ``db_recon`` masks with
      ``MASK_OPEN_MAP_KEY`` — so it stays in the scan set.
    """
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, str):
            if len(node) >= _LEAK_SCAN_MIN_LENGTH:
                found.add(node)
        elif isinstance(node, Mapping):
            for key, value in node.items():
                if (
                    isinstance(key, str)
                    and len(key) >= _LEAK_SCAN_MIN_LENGTH
                    and key not in declared
                ):
                    found.add(key)
                walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    for record in records:
        walk(record)
    return frozenset(found)


def _authored_strings() -> frozenset[str]:
    """Every string this module can emit that it authored itself.

    A corpus value that happens to EQUAL one of these is not a disclosure:
    ``not_applicable`` appears in the safeguards block unconditionally, so
    seeing it there tells a reader nothing about any record. Measured on the
    public corpus, ``not_applicable`` is exactly such a collision — it is both a
    safeguard state word and a value somewhere in the ten records.

    Subtracting them is what keeps the scan pointed at record content. Without
    it the safeguard reads ``unverified`` forever, and a safeguard that is
    always ``unverified`` is one nobody looks at.
    """
    from .format_shadow import SHADOW_ERROR_CODES

    authored: set[str] = set()
    for group in (
        _ENVELOPE_KEYS,
        _METADATA_KEYS,
        _CORPUS_KEYS,
        _OFFICIAL_VALIDATION_KEYS,
        _FORMAT_SHADOW_KEYS,
        _HISTOGRAM_KEYS,
        _SAFEGUARD_KEYS,
        SAFEGUARD_STATES,
        PENDING_STATUSES,
        VERIFICATION_MODES,
        SHADOW_ERROR_CODES,
        corpus_mutation._MUTATION_KEYS,
        corpus_mutation._ORACLE_KEYS,
        ("ok", "key", "count"),
    ):
        authored.update(group)
    return frozenset(authored)


def _leak_scan(
    payload: Mapping[str, Any], records: Sequence[Mapping[str, Any]], root: Path
) -> bool:
    """True when no private corpus string appears in what would be served.

    Runs over the ALREADY-BUILT payload, so it tests what would actually be
    served rather than what the code intends to serve.

    **It requires the corpus, so it is only available in the public mode.** In
    the private mode the records are consumed and dropped as the sweep proceeds,
    and nothing is retained past it — so by the time this payload is assembled
    there is no corpus left to scan against.

    State that precisely, because an earlier revision of this docstring said the
    private records "are never all in memory at once", and that was FALSE. It is
    recorded rather than silently replaced.
    ``DatastoreRecordProvider._drain`` accumulates the ENTIRE bounded page into
    one list and returns it whole. What is true: the page is BOUNDED (by
    ``MAX_RECORDS_CEILING``, and identical to what the driver had already
    buffered client-side anyway); its rows are RELEASED PROGRESSIVELY as they are
    consumed; exactly one *parsed record* exists at a time; and nothing survives
    the sweep. The guarantee is non-retention, not an inability to hold the rows.

    And the skip is a DESIGN DECISION, not a physical impossibility:
    :func:`run_verification` sets ``records = None`` for this mode, so this scan
    has nothing to run against. The corpus *could* be retained to make it
    runnable — it deliberately is not, because retaining it would defeat the
    non-retention boundary, which is worth more than this scan.

    :func:`_structural_string_audit` is what covers the private mode, and it is
    strictly stronger in one respect: it does not need the corpus, because it
    accounts for every served string from public information alone.

    ``limitations`` is blanked before scanning. Those strings are authored in
    this file, are identical on every run, and provably carry nothing
    record-derived — but they are English prose, so they collide with ordinary
    words that also appear in records. Measured on the public corpus: the words
    ``database`` and ``internal`` occur in both. Scanning fixed editorial text
    against a 500-string vocabulary produces false alarms and no true ones.

    IT MATCHES AGAINST DECODED STRING LEAVES, NOT AGAINST SERIALIZED JSON
    ====================================================================
    This is a correction of a real defect, recorded rather than silently
    replaced. The previous implementation compared each candidate against
    ``json.dumps(scanned, sort_keys=True)``. ``json.dumps`` defaults to
    ``ensure_ascii=True``, so a corpus value containing ``→`` appears in that
    text as the seven characters ``\\u2192`` while the candidate is still the raw
    one-character Python string — and ``value in serialized`` was then
    **permanently false**. The same applied to any value containing ``"``,
    ``\\``, a newline or a tab, all of which JSON escapes.

    It was not hypothetical: 3 of the 392 candidate strings in the shipped
    ten-record public corpus are already non-ASCII (``→``, ``–``, ``—``), and
    chemistry metadata (Å, µ, °C, arrows, en-dashes) makes this the ordinary
    case rather than a corner one. The report went on publishing
    ``private_values_exposed: "verified"`` throughout.

    Walking the decoded leaves removes the encoding step entirely, so there is
    no representation for an escape to hide in.

    RESIDUALS, stated so the claim is not read as stronger than it is — and note
    that the list used to say "two" while omitting the escaping defect above,
    which is how a known-limitations list becomes a false assurance:

    1. Strings shorter than :data:`_LEAK_SCAN_MIN_LENGTH` are not scanned,
       because short values ("Cu", "eV") collide with legitimate report content.
    2. A value that some transformation RESHAPED (truncated, case-folded,
       normalized) would not be caught by a substring scan.
    3. Only string leaves are compared. A record value that reached the payload
       as a NUMBER would not be caught here — nothing in the current builder can
       do that, and :func:`_structural_string_audit` does not cover it either.
    """
    from .format_shadow import _introspect_root

    _, declared = _introspect_root(Path(root))
    scanned = dict(payload)
    scanned["limitations"] = []
    leaves = _string_leaves(scanned)
    candidates = _corpus_strings(records, declared) - _authored_strings()
    return not any(
        value in leaf for value in candidates for leaf in leaves
    )


def _string_leaves(node: Any) -> tuple[str, ...]:
    """Every string in ``node``, keys included, decoded and unescaped.

    The unit the leak scan compares against. Keys are collected as well as
    values because a leaked value could arrive as a histogram cell KEY, which is
    exactly the shape ``failures_by_schema_path`` has.
    """
    found: list[str] = []

    def walk(inner: Any) -> None:
        if isinstance(inner, str):
            found.append(inner)
        elif isinstance(inner, Mapping):
            for key, value in inner.items():
                if isinstance(key, str):
                    found.append(key)
                walk(value)
        elif isinstance(inner, (list, tuple)):
            for item in inner:
                walk(item)

    walk(node)
    return tuple(found)


# --- the structural DTO allowlist -------------------------------------------
#
# The complement of the leak scan. The leak scan asks "does any private string
# appear here?", which needs the private strings. This asks the opposite
# question — "is every string here accountable to something PUBLIC?" — which
# needs nothing but the payload and the vendored schema, and therefore works in
# the mode where the corpus cannot be retained.
#
# It is also the stronger question. A leak scan can only catch a value it was
# shown; this catches any string that cannot be explained, including one that
# arrived by a route nobody anticipated.

#: The EXACT shape :func:`build_report` emits for ``generated_at``. It is a
#: necessary condition, never a sufficient one — see
#: :func:`_structural_string_audit` for why shape alone was a hole.
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
#: The exact shape of a sha256 hex digest, used only to sanity-check the ONE
#: value that is independently recomputed. Not an admission rule.
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")

#: Cache for the parsed vendored schema, keyed the way ``format_shadow`` and
#: ``official`` key theirs: resolved path plus ``st_mtime_ns`` plus size. Same
#: heuristic, same admitted weakness — an edit landing in the same nanosecond
#: tick that leaves byte length unchanged is served stale.
_schema_cache: dict[tuple[str, int, int], Any] = {}


def _vendored_schema(root: Path) -> Any:
    from isaac_records.official import schema_path

    path = schema_path(Path(root))
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    cached = _schema_cache.get(key)
    if cached is None:
        cached = json.loads(path.read_text(encoding="utf-8"))
        _schema_cache.clear()
        _schema_cache[key] = cached
    return cached


def _schema_pointer_resolves(pointer: str, schema: Any) -> bool:
    """True when ``pointer`` addresses a node of the PUBLIC vendored schema.

    This is what lets ``failures_by_schema_path`` be served at all. A schema
    pointer is produced by the schema, not by the data — the rule ``CLAUDE.md``
    §15 states as *the schema may describe the data; the data may not describe
    itself*. Checking that it resolves is how that claim stops being an
    assumption: a pointer that does not resolve did not come from the schema.
    """
    if pointer == "":
        return True
    if not pointer.startswith("/"):
        return False
    node = schema
    for raw in pointer.split("/")[1:]:
        segment = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, Mapping):
            if segment not in node:
                return False
            node = node[segment]
        elif isinstance(node, list):
            if not segment.isdigit() or int(segment) >= len(node):
                return False
            node = node[int(segment)]
        else:
            return False
    return True


def _structural_string_audit(payload: Mapping[str, Any], root: Path) -> bool:
    """True when EVERY string in ``payload`` is accountable to public information.

    A string qualifies only if it is one of:

    * a name or word this module authored (:func:`_authored_strings`, plus the
      fixed limitation sentences and the schema version literal);
    * the schema fingerprint THIS RUN should carry, recomputed independently
      from the vendored schema file;
    * the single ``metadata.generated_at`` value this payload carries, and only
      if it has the exact shape this module emits;
    * a pointer that RESOLVES in the vendored public schema.

    Nothing else. There is deliberately no "looks harmless" branch — and that
    sentence is only true because of a correction, which is recorded here rather
    than quietly applied.

    THE HOLE THIS CLOSES
    ====================
    The previous version admitted any string matching ``^[0-9a-f]{8,64}$`` or a
    timestamp shape. Those are SHAPES, and they are precisely the shapes ISAAC
    records carry: a ``raw_data`` sha256 pointer and ``timestamps.created_utc``.
    An adversarial review got a real sha256 digest, ``deadbeef``, a 32-character
    hex string and ``2019-03-14T09:12:44Z`` all ADMITTED — while this docstring
    claimed there was no "looks harmless" branch and there were two. In the
    datastore mode that mattered most, because :func:`_leak_scan` cannot run
    there and this is the ONLY string-level privacy check.

    Both are now EQUALITY tests:

    * The fingerprint is not read from the payload at all. It is recomputed with
      ``corpus_mutation.schema_fingerprint(root)`` — hashing the vendored schema
      file's bytes — so a digest that came from a record cannot whitelist
      itself, and a *different* digest anywhere in the payload fails.
    * ``generated_at`` is the one self-referential admission, and it is bounded:
      exactly the value at ``metadata.generated_at``, admitted only if it also
      matches :data:`_TIMESTAMP_RE`. It is produced by ``datetime.now`` in
      :func:`build_report` and is not record-derived. A second timestamp — any
      record's ``created_utc``, however well-formed — is a different string and
      fails.
    """
    accountable = set(_authored_strings())
    accountable.update(LIMITATIONS)
    for lines in _MODE_LIMITATIONS.values():
        accountable.update(lines)
    accountable.add(EXPECTED_VERSION)
    schema = _vendored_schema(Path(root))

    # Independent recomputation. Deliberately NOT `payload["schema_fingerprint"]`.
    try:
        expected_fingerprint = corpus_mutation.schema_fingerprint(Path(root))
    except Exception:  # noqa: BLE001 — a failed measurement admits nothing
        expected_fingerprint = None
    if isinstance(expected_fingerprint, str) and _SHA256_HEX_RE.match(
        expected_fingerprint
    ):
        accountable.add(expected_fingerprint)

    metadata = payload.get("metadata")
    if isinstance(metadata, Mapping):
        stamp = metadata.get("generated_at")
        if isinstance(stamp, str) and _TIMESTAMP_RE.match(stamp):
            accountable.add(stamp)

    def ok(text: str) -> bool:
        if text == "" or text in accountable:
            return True
        return _schema_pointer_resolves(text, schema)

    def walk(node: Any) -> bool:
        if isinstance(node, str):
            return ok(node)
        if isinstance(node, Mapping):
            return all(
                (not isinstance(key, str) or ok(key)) and walk(value)
                for key, value in node.items()
            )
        if isinstance(node, (list, tuple)):
            return all(walk(item) for item in node)
        return True

    return walk(payload)


def _canary_is_detected(payload: Mapping[str, Any], root: Path) -> bool:
    """Plant each sentinel in a COPY of the payload; the audit must reject all.

    A scan that never fires proves nothing, and a scan that has been weakened
    into a no-op looks exactly like a scan that found nothing. This is the
    runtime negative control: if the audit accepts a copy carrying any member of
    :data:`_CANARY_SENTINELS`, then ``private_values_exposed`` degrades to
    ``unverified`` on the *running deployment*, not merely in a unit test.

    THE SENTINELS ARE SHAPED LIKE REAL RECORD CONTENT, and that is the point of
    the set rather than the single string it used to be. The original canary was
    an uppercase English sentence, which no plausible admission rule would ever
    have accepted — so it demonstrated the audit was not *completely* inert and
    nothing more. It could not have caught the actual defect: an audit admitting
    any hex digest and any timestamp by SHAPE, which is exactly what an ISAAC
    ``raw_data`` pointer and a ``created_utc`` look like. Each sentinel below
    stands for one such shape, so weakening the audit back toward shape matching
    fails here.

    The sentinels go into deep copies. None is ever planted into a record or
    into the real payload, and every copy is discarded here.
    """
    block = payload.get("format_shadow")
    if not isinstance(block, Mapping):
        return False
    histogram = block.get("failures_by_error_code")
    if not isinstance(histogram, Mapping) or not isinstance(
        histogram.get("cells"), list
    ):
        return False

    for sentinel in _CANARY_SENTINELS:
        probe = json.loads(json.dumps(payload))
        probe["format_shadow"]["failures_by_error_code"]["cells"].append(
            {"key": sentinel, "count": 999}
        )
        if _structural_string_audit(probe, root):
            return False
    return True


def _official_validator_is_unchanged(root: Path) -> bool:
    """Measure, at runtime, that the official validator is still format-blind.

    ``format_shadow`` builds its OWN checker and its OWN validator precisely so
    this stays true. If a future change armed the global registry instead, this
    flips to ``unverified`` on the running deployment — not only in a test.
    """
    try:
        from isaac_records.official import load_official_validator

        return load_official_validator(Path(root)).format_checker is None
    except Exception:  # noqa: BLE001 — a failed measurement is not a pass
        return False


# --------------------------------------------------------------------------
# The sweep — one engine, one record at a time
# --------------------------------------------------------------------------


#: The ``mutations`` counters that ADD across per-record reports.
#: ``operators_defined`` is excluded because it is a constant property of the
#: catalog, not a per-record measurement — summing it would report
#: ``755 * corpus_size`` operators.
_ADDITIVE_MUTATION_KEYS: tuple[str, ...] = tuple(
    key for key in corpus_mutation._MUTATION_KEYS if key != "operators_defined"
)


@dataclass
class _SweepResult:
    """Everything one pass over a record stream measured. Internal only.

    THIS HOLDS COUNTERS, NOT TRIALS, and that is a correction worth recording.
    It used to accumulate every ``TrialOutcome`` for the whole sweep and build
    one ``HarnessResult`` at the end. An adversarial review measured 1510 trials
    for 2 records at roughly 497 bytes each — about 188 MB at the shipped row
    ceiling of 500. ``MAX_RECORDS_CEILING``'s docstring claimed to keep a large
    table out of pod memory; it bounded the raw ROWS, not the 755-operators-by-N
    derived structure hanging off them.

    No record content was ever in those objects, so this was a resource defect
    and not a disclosure one. The fix is to project each record's harness result
    through ``corpus_mutation.build_report`` immediately and add the resulting
    scalars, so at most one record's trials exist at a time.
    """

    schema_fingerprint: str = ""
    operators_defined: int = 0
    corpus: Counter = field(default_factory=Counter)
    mutations: Counter = field(default_factory=Counter)
    oracles: Counter = field(default_factory=Counter)
    official_passing: int = 0
    shadow_passing: int = 0
    by_code: Counter = field(default_factory=Counter)
    by_schema_path: Counter = field(default_factory=Counter)
    #: Records whose SOURCE object differed before and after the sweep. An
    #: independent check, run here rather than trusting the harness oracle.
    source_objects_mutated: int = 0

    def mutations_block(self) -> dict:
        """The ``mutations`` block, in the frozen key order."""
        built = {key: int(self.mutations.get(key, 0)) for key in _ADDITIVE_MUTATION_KEYS}
        built["operators_defined"] = self.operators_defined
        return {key: built[key] for key in corpus_mutation._MUTATION_KEYS}

    def oracles_block(self) -> dict:
        return {
            key: int(self.oracles.get(key, 0)) for key in corpus_mutation._ORACLE_KEYS
        }

    def corpus_block(self) -> dict:
        return {key: int(self.corpus.get(key, 0)) for key in _CORPUS_KEYS}


def _structural_snapshot(record: Mapping[str, Any]) -> str:
    """A canonical serialization used only to compare a record against itself.

    ``default=str`` so an exotic leaf cannot raise mid-sweep. The value is
    compared and discarded; it is never stored, hashed into anything served, or
    included in the payload.
    """
    return json.dumps(record, sort_keys=True, default=str)


def _sweep(
    stream: Iterable[Mapping[str, Any]], root: Path, *, repeat: int
) -> _SweepResult:
    """Run all three programs over ``stream``, one record at a time.

    The ordering per record is the one the authorization describes: baseline
    official validation → format shadow → deep copy and bounded mutation (inside
    ``corpus_mutation.run_harness``) → oracles → aggregate counters → confirm the
    source object is unchanged → discard.

    **The harness is invoked once per record, with a pre-built operator catalog.**
    That is not an optimisation, it is the streaming property:
    ``run_harness`` materialises the corpus it is handed, so handing it a
    generator would put every record in memory at once. Handing it a one-element
    tuple keeps exactly one there — and it reuses the harness wholesale rather
    than reimplementing the mutation loop, so there is no second copy of the
    mutation or validation logic to keep in step.

    **Each record's harness result is PROJECTED and discarded immediately.**
    ``corpus_mutation.build_report`` runs per record and only its scalar counters
    are added up; the ``TrialOutcome`` objects never outlive the iteration that
    produced them. Retaining them was a real memory defect — see
    :class:`_SweepResult`.

    The results are summed. That is safe because the harness's accounting is
    per-trial and additive — ``attempted = applicable + skipped`` and
    ``applicable = expected + unexpected + observation_only`` hold within each
    per-record report and are preserved by addition. ``test_corpus_mutation.py:318-334``
    pins those identities; nothing here redesigns them. Summing the PROJECTED
    reports rather than the raw trials is in fact the stronger arrangement: every
    addend has already passed the frozen-allowlist projection.
    """
    root = Path(root)
    catalog = corpus_mutation.build_operators(root)

    result = _SweepResult(
        schema_fingerprint=corpus_mutation.schema_fingerprint(root),
        operators_defined=len(catalog),
    )
    scanned = 0

    for record in stream:
        scanned += 1
        before = _structural_snapshot(record)

        if validate_official(dict(record), root).ok:
            result.official_passing += 1

        shadow = shadow_validate(record, root)
        if shadow.passed:
            result.shadow_passing += 1
        for finding in shadow.findings:
            result.by_code[finding.code] += 1
            result.by_schema_path[finding.schema_path] += 1
            # `finding.instance_path` is deliberately NOT accumulated. Over a
            # small corpus a count of one at an instance path is a single-record
            # fact; this is the aggregate that shipped in v0.0.32 and was
            # withdrawn (`CLAUDE.md` §15). Do not rebuild it.

        one = corpus_mutation.run_harness(
            (record,), root, operators=catalog, repeat=repeat
        )
        # Project NOW, add the scalars, and let the trials go. This is the whole
        # of the memory fix: `projected` is ~17 integers, `one.trials` is 755
        # objects per record.
        projected = corpus_mutation.build_report(one)
        for key in _CORPUS_KEYS:
            result.corpus[key] += int(projected["corpus"][key])
        for key in _ADDITIVE_MUTATION_KEYS:
            result.mutations[key] += int(projected["mutations"][key])
        for key in corpus_mutation._ORACLE_KEYS:
            result.oracles[key] += int(projected["oracles"][key])

        if _structural_snapshot(record) != before:
            result.source_objects_mutated += 1

        # Drop every reference this frame holds before pulling the next record.
        del record, before, shadow, one, projected

    # `records_scanned` is also summed above (one per record), so this is only a
    # cross-check that the two agree. They can only diverge if `run_harness`
    # stopped reporting one record per call, which would silently break every
    # other figure too.
    if result.corpus.get("records_scanned", 0) != scanned:  # pragma: no cover
        raise ReportKeyError("per-record harness accounting did not reconcile")
    return result


#: How a provider's terminal state becomes an envelope ``status``. ``timeout``
#: collapses into ``unavailable`` because the envelope's status vocabulary is
#: frozen and a consumer already renders ``unavailable`` as "the source did not
#: answer" — which is what a timeout is. The distinction is not lost: the
#: provider still holds ``state == "timeout"`` for a log or a future field.
_PROVIDER_STATUS: dict[str, str] = {
    "ok": "ok",
    "not_run": "unavailable",
    "unavailable": "unavailable",
    "timeout": "unavailable",
    "refused": "refused",
    "error": "error",
}


def run_verification(
    root: Path,
    *,
    mode: str = PUBLIC_REFERENCE,
    provider: Any | None = None,
    repeat: int = 3,
) -> dict:
    """Run all three programs over ``mode``'s corpus and build the report.

    Costs roughly 19 seconds over ten records. Callers must not invoke this
    inside a request; :class:`VerificationState` exists to keep it off the
    request path.

    ``provider`` is required for :data:`AUTHORIZED_PRIVATE_SAMPLE` and is
    ignored for :data:`PUBLIC_REFERENCE`. It is INJECTED and never constructed
    here: this module must not be able to reach a datastore by itself, and a
    default that quietly built one would make that guarantee a matter of caller
    discipline.
    """
    root = Path(root)

    if mode not in VERIFICATION_MODES:
        # Includes the case where the approval flag was cleared and the private
        # mode no longer exists. Refused, not attempted.
        return build_pending_report("refused", mode=mode)

    if mode == AUTHORIZED_PRIVATE_SAMPLE and provider is None:
        return build_pending_report("unavailable", mode=mode)

    started = time.monotonic()

    if mode == PUBLIC_REFERENCE:
        # Public records: safe to retain, so the corpus leak scan is available.
        records: Sequence[Mapping[str, Any]] | None = load_public_corpus(root)
        stream: Iterable[Mapping[str, Any]] = iter(records)
    else:
        # Private records: consumed and dropped as the sweep proceeds, and not
        # retained past it — so by report-assembly time there is no corpus.
        #
        # `records = None` is a DESIGN DECISION, not a physical impossibility.
        # It is what makes `_leak_scan` unavailable below. The corpus could be
        # retained to make that scan runnable; it deliberately is not, because
        # the non-retention boundary is worth more than the scan. Note also that
        # the raw page IS held whole while the sweep runs (see
        # `DatastoreRecordProvider._drain`) — the property relied on here is
        # non-retention afterwards, never "never all in memory at once".
        records = None
        stream = provider.records()

    sweep = _sweep(stream, root, repeat=repeat)

    if mode == AUTHORIZED_PRIVATE_SAMPLE:
        state = getattr(provider, "state", "error")
        status = _PROVIDER_STATUS.get(state, "error")
        if status != "ok":
            # A partial sweep must not be published as a report. Whatever the
            # provider managed to yield is discarded with the envelope.
            return build_pending_report(status, mode=mode)

    duration_ms = int((time.monotonic() - started) * 1000)
    return build_report(
        sweep=sweep,
        mode=mode,
        provider=provider,
        records=records,
        duration_ms=duration_ms,
        root=root,
    )


def build_report(
    *,
    sweep: _SweepResult,
    mode: str,
    provider: Any | None,
    records: Sequence[Mapping[str, Any]] | None,
    duration_ms: int,
    root: Path,
) -> dict:
    """Project everything onto the frozen contract. Raises on an unlisted key."""
    total = int(sweep.corpus.get("records_scanned", 0))

    metadata = _project(
        {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration_ms": duration_ms,
            "corpus_size": total,
            "cache_age_seconds": 0,
            "verification_mode": mode,
        },
        _METADATA_KEYS,
        strict=True,
    )
    corpus = _project(sweep.corpus_block(), _CORPUS_KEYS, strict=True)
    official_validation = _project(
        {
            "passing": sweep.official_passing,
            "failing": total - sweep.official_passing,
        },
        _OFFICIAL_VALIDATION_KEYS,
        strict=True,
    )
    # Floor suppression on BOTH distributions, in BOTH modes, unconditionally.
    by_code = suppress_small_cells(dict(sweep.by_code))
    by_schema_path = suppress_small_cells(dict(sweep.by_schema_path))
    # THE TWO HISTOGRAMS SHARE ONE TOTAL, so they must withhold it together.
    # `_sweep` increments `by_code` and `by_schema_path` once per finding, so
    # `sum(by_code) == sum(by_schema_path) == F` by construction, and each served
    # histogram satisfies `F = sum(cells) + suppressed_total`. Withholding the
    # total on only the histogram that reached one category therefore withholds
    # nothing: the sibling publishes F - sum(cells), which is the same number, on
    # the same screen. Either one reaching the single-category case nulls both.
    #
    # When that happens BOTH histograms are in fact cell-less, which is why
    # nulling both totals removes F rather than merely obscuring it: one category
    # means a single key below the floor, so F < floor, so every cell of the
    # sibling is also below the floor and is suppressed too. Nothing else served
    # carries F -- `records_failing` and `official_validation.failing` count
    # RECORDS, and a record may carry several findings, so they are a lower bound
    # on F and not F. Pinned by `test_verification.py`.
    withhold_shared_total = 1 in (
        by_code.suppressed_categories,
        by_schema_path.suppressed_categories,
    )
    format_shadow = _project(
        {
            "records_passing": sweep.shadow_passing,
            "records_failing": total - sweep.shadow_passing,
            "failures_by_error_code": _histogram(
                by_code, withhold_total=withhold_shared_total
            ),
            "failures_by_schema_path": _histogram(
                by_schema_path, withhold_total=withhold_shared_total
            ),
        },
        _FORMAT_SHADOW_KEYS,
        strict=True,
    )

    oracles = sweep.oracles_block()
    safeguards = _project(
        {
            **_transport_safeguards(mode, provider),
            # TWO independent measurements, both of which must hold: the
            # harness's own per-trial oracle, and this module's before/after
            # comparison of each source object. Either one degrading is enough.
            "source_records_modified": (
                "verified"
                if oracles["source_mutation_failures"] == 0
                and sweep.source_objects_mutated == 0
                else "unverified"
            ),
            # Filled in by the caller below, after the payload exists — a scan of
            # the built payload is the only scan that tests what is served.
            "private_values_exposed": "unverified",
            "official_validator_unchanged": (
                "verified" if _official_validator_is_unchanged(root) else "unverified"
            ),
            # This module imports nothing from `isaac_records.export` and writes
            # nothing; `test_verification.py` asserts the import absence
            # mechanically rather than trusting this comment.
            "export_gating_unchanged": "verified",
        },
        _SAFEGUARD_KEYS,
        strict=True,
    )

    payload = _project(
        {
            "status": "ok",
            "report_format_version": REPORT_FORMAT_VERSION,
            "schema_version": EXPECTED_VERSION,
            "schema_fingerprint": sweep.schema_fingerprint,
            "metadata": metadata,
            "corpus": corpus,
            "official_validation": official_validation,
            "format_shadow": format_shadow,
            "mutations": sweep.mutations_block(),
            "oracles": oracles,
            "safeguards": safeguards,
            "limitations": list(limitations_for(mode)),
        },
        _ENVELOPE_KEYS,
        strict=True,
    )

    # The privacy measurements run LAST, over the assembled payload, and their
    # result is written back. Scanning anything earlier would test a draft.
    payload["safeguards"]["private_values_exposed"] = (
        "verified" if _privacy_holds(payload, records, root) else "unverified"
    )
    return payload


def _transport_safeguards(mode: str, provider: Any | None) -> dict:
    """The four safeguards that describe how the records were obtained.

    In the public mode there is no transaction and no query to characterise, so
    the two tri-states are ``not_applicable`` and the counts are 0. ``verified``
    there would be a claim about an event that never happened.

    In the private mode all four become MEASUREMENTS read off the provider:
    ``transaction_read_only`` may say ``verified`` only because the provider read
    the setting back from the server, and the statement counts are what the
    policy guard COUNTED, not what this module asserts. A provider that failed to
    verify, or that is missing the attribute entirely, degrades to ``unverified``
    rather than defaulting to a pass.
    """
    if mode != AUTHORIZED_PRIVATE_SAMPLE:
        return {
            "transaction_read_only": "not_applicable",
            "parameterized_queries_only": "not_applicable",
            "dml_statements": 0,
            "ddl_statements": 0,
        }

    def count(name: str) -> int:
        value = getattr(provider, name, None)
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    return {
        "transaction_read_only": (
            "verified" if getattr(provider, "read_only_verified", False) is True
            else "unverified"
        ),
        "parameterized_queries_only": (
            "verified" if getattr(provider, "parameterized_only", False) is True
            else "unverified"
        ),
        "dml_statements": count("dml_statements"),
        "ddl_statements": count("ddl_statements"),
    }


def _privacy_holds(
    payload: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]] | None,
    root: Path,
) -> bool:
    """All applicable privacy measurements, ANDed. Defence in depth, in order.

    1. The structural allowlist — every served string accountable to public
       information. Runs in BOTH modes.
    2. The planted-sentinel canary — proof that (1) is not a no-op. BOTH modes.
    3. The corpus leak scan — only where the corpus is public and therefore
       retainable.

    A failed measurement is never a pass: any exception is caught and reported as
    a failure, because "the check crashed" and "the check succeeded" must not
    produce the same word.
    """
    try:
        if not _structural_string_audit(payload, root):
            return False
        if not _canary_is_detected(payload, root):
            return False
        if records is not None and not _leak_scan(payload, records, root):
            return False
        return True
    except Exception:  # noqa: BLE001
        return False


def build_pending_report(status: str, *, mode: str | None = None) -> dict:
    """Sanitized envelope for a run that has produced no result yet.

    ``status`` must be a member of the closed set; anything else becomes
    ``"error"`` rather than being echoed. Projected non-strictly, for the reason
    given in :func:`_project`.

    ``mode`` selects which fixed limitation lines to publish and is validated
    against the closed vocabulary for the same reason ``status`` is.
    """
    safe = status if status in PENDING_STATUSES else "error"
    limitations = (
        limitations_for(mode) if mode in VERIFICATION_MODES else LIMITATIONS
    )
    return _project(
        {
            "status": safe,
            "report_format_version": REPORT_FORMAT_VERSION,
            "schema_version": EXPECTED_VERSION,
            "limitations": list(limitations),
        },
        _ENVELOPE_KEYS,
        strict=False,
    )


# --------------------------------------------------------------------------
# Off-request execution
# --------------------------------------------------------------------------


@dataclass
class _Cached:
    payload: dict
    completed_at: float


class VerificationState:
    """Keeps the sweep off the request path, and off the datastore's back.

    A request never blocks on the sweep and never opens a connection. The first
    request for a mode starts it on a background thread and is answered
    ``running``; later requests are answered from cache with an honest
    ``cache_age_seconds`` until the TTL expires, at which point the next request
    triggers a refresh and is served the STALE result rather than nothing — a
    slightly old measurement beats a blank panel, and its age is stated rather
    than hidden.

    Four properties that matter more once a mode can reach a datastore:

    **Single-flight.** A second caller arriving during a run JOINS it: it is told
    ``running`` and does not start a second sweep. One run means one connection.

    **Rate-limited refresh.** A start is refused within
    :data:`MIN_REFRESH_INTERVAL_SECONDS` of the previous *attempt*, successful or
    not. Without this a source that fails fast would be retried on every request,
    which is how a connection limit of 5 gets exhausted by a failure rather than
    by load.

    **Last-known-safe.** A failed refresh NEVER replaces a good cached report.
    The cache is only written on ``status == "ok"``; a failure updates the
    last-status word used when there is nothing cached at all. So a datastore
    that goes away leaves the last successful aggregate on screen, ageing
    visibly, instead of blanking it.

    **Bounded.** The cache is keyed by mode and modes are a closed tuple, so it
    holds at most ``len(VERIFICATION_MODES)`` payloads. There is no unbounded key
    and nothing a caller can vary to grow it.

    There is no polling loop: nothing here runs on a timer. Work happens only
    when a request finds the cache empty or stale.
    """

    def __init__(
        self,
        root: Path,
        *,
        ttl_seconds: int = CACHE_TTL_SECONDS,
        min_refresh_interval_seconds: int = MIN_REFRESH_INTERVAL_SECONDS,
        provider_factory: Callable[[], Any] | None = None,
        runner: Callable[..., dict] | None = None,
        modes: Sequence[str] | None = None,
    ) -> None:
        self._root = Path(root)
        self._ttl = ttl_seconds
        self._min_refresh = min_refresh_interval_seconds
        # No factory means the private mode can never obtain records, and so can
        # never open anything. Fail-closed by construction rather than by policy.
        self._provider_factory = provider_factory
        self._runner = runner or run_verification
        self._modes = tuple(modes) if modes is not None else VERIFICATION_MODES
        self._lock = threading.Lock()
        self._cached: dict[str, _Cached] = {}
        self._running: set[str] = set()
        self._last_attempt: dict[str, float] = {}
        self._last_status: dict[str, str] = {}

    @property
    def default_mode(self) -> str:
        return self._modes[0]

    def _start_locked(self, mode: str) -> bool:
        """Start a sweep unless one is in flight or the rate limit forbids it."""
        if mode in self._running:
            return False
        now = time.monotonic()
        last = self._last_attempt.get(mode)
        if last is not None and (now - last) < self._min_refresh:
            return False
        self._running.add(mode)
        self._last_attempt[mode] = now
        threading.Thread(
            target=self._work,
            args=(mode,),
            name=f"isaac-verification-{mode}",
            daemon=True,
        ).start()
        return True

    def _work(self, mode: str) -> None:
        payload: dict
        try:
            provider = None
            if mode == AUTHORIZED_PRIVATE_SAMPLE:
                if self._provider_factory is None:
                    raise RuntimeError("no provider factory")
                provider = self._provider_factory()
            payload = self._runner(self._root, mode=mode, provider=provider)
            if not isinstance(payload, dict):
                payload = build_pending_report("error", mode=mode)
        except (KeyboardInterrupt, SystemExit):
            with self._lock:
                self._running.discard(mode)
            raise
        except BaseException:  # noqa: BLE001 — must never leak, never abort
            # The exception text is NOT captured: it could carry a path, a
            # credential or a record value. The caller learns a status word,
            # which is all it may safely know.
            payload = build_pending_report(
                "unavailable" if mode == AUTHORIZED_PRIVATE_SAMPLE else "error",
                mode=mode,
            )

        with self._lock:
            status = payload.get("status")
            if status == "ok":
                self._cached[mode] = _Cached(
                    payload=payload, completed_at=time.monotonic()
                )
            # else: the previous successful payload is left exactly where it is.
            self._last_status[mode] = status if isinstance(status, str) else "error"
            self._running.discard(mode)

    def get(self, mode: str | None = None) -> dict:
        """Return the report for ``mode``, starting or joining a sweep if needed."""
        selected = self.default_mode if mode is None else mode
        if selected not in self._modes:
            # An unknown mode — including a private mode whose approval flag was
            # cleared — is refused, never silently served the public one.
            return build_pending_report("refused")

        with self._lock:
            cached = self._cached.get(selected)
            if cached is None:
                started = self._start_locked(selected)
                if started or selected in self._running:
                    return build_pending_report("running", mode=selected)
                return build_pending_report(
                    self._last_status.get(selected, "unavailable"), mode=selected
                )
            age = int(time.monotonic() - cached.completed_at)
            if age >= self._ttl:
                self._start_locked(selected)
            payload = json.loads(json.dumps(cached.payload))

        if isinstance(payload.get("metadata"), dict):
            payload["metadata"]["cache_age_seconds"] = age
        return payload
