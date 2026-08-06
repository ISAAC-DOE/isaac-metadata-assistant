"""Record Verification — the sanitized aggregate report served to Statistics.

WHAT THIS IS. One report combining three independent programs over a corpus of
official ISAAC records:

1. **Official validation** — ``isaac_records.official.validate_official``. The
   authority. This module reads its verdict and changes nothing about it.
2. **Format shadow** — ``format_shadow.shadow_validate``. Stricter than the
   official validator because it checks JSON Schema ``format``. Advisory ONLY:
   its verdict never becomes validity, never gates export, and never overrides
   the official result. Q20 in ``docs/dean-authorization-packet.md`` is the
   unanswered question about arming enforcement globally; this module does not
   pre-empt it, and ``tests/test_truthpath_characterization.py`` proves it.
3. **Mutation harness** — ``corpus_mutation.run_harness``. Deep-clones each
   record, applies a schema-derived operator catalog, and checks seven oracles.

WHICH CORPUS. ``PUBLIC_UPSTREAM_CORPUS`` only. Those ten records are copied
verbatim from the upstream ISAAC ``examples/`` directory (``schema/PROVENANCE.md``)
and are already public on GitHub, so nothing about publishing figures derived
from them needs authorization.

**The 30 production-derived rows in the SLAC Postgres are NOT a corpus this
module knows.** ``VERIFICATION_MODES`` has exactly one member and no database
mode. Adding one requires Dean's answer to Q19, which
``docs/dean-authorization-packet.md:3`` records as never sent. Do not add a
"disabled" private mode either — the authorization audit is explicit that a
disabled runner is a runner someone enables
(``docs/superpowers/plans/2026-08-02-corpus-validation-authorization.md:221-223``).

WHY THE SUPPRESSION RUNS ANYWAY. Every histogram is projected through
``disclosure.suppress_small_cells`` even though the public corpus needs no such
protection. Dean's guide is explicit that a visibility boundary belongs in the
read path from the start rather than bolted on afterwards
(``docs/postgres-test-db-guide.md:158-162``). A gate that arms only for the
private corpus is a gate someone forgets to arm.

NO DATABASE. This module opens no connection, imports no driver and knows no
hostname — the same stance, and for the same reason, as ``corpus_mutation``.
Scoped to THIS MODULE: ``db_recon.py`` does connect from the pod, and
``CLAUDE.md`` §15 requires the honest form "no connection was opened here",
never "the database has never been contacted".
"""

from __future__ import annotations

import json
import threading
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from isaac_records.official import EXPECTED_VERSION, validate_official

from . import corpus_mutation
from .disclosure import MIN_CELL_SIZE, SuppressedHistogram, suppress_small_cells
from .format_shadow import shadow_validate

__all__ = [
    "PUBLIC_UPSTREAM_CORPUS",
    "REPORT_FORMAT_VERSION",
    "VERIFICATION_MODES",
    "VerificationState",
    "build_report",
    "build_pending_report",
    "load_public_corpus",
    "run_verification",
]

#: Bumped from ``corpus_mutation.REPORT_FORMAT_VERSION`` (1) because this
#: envelope is a superset: it adds ``metadata``, ``official_validation``,
#: ``format_shadow`` and ``safeguards``.
REPORT_FORMAT_VERSION = 2

#: The ONE corpus. See the module docstring for why there is no second member.
PUBLIC_UPSTREAM_CORPUS = "public_upstream_corpus"
VERIFICATION_MODES: tuple[str, ...] = (PUBLIC_UPSTREAM_CORPUS,)

#: Where the public upstream examples live, relative to the repository root.
#: The Dockerfile COPY allowlist must include this path or the deployed pod
#: reports ``unavailable`` rather than guessing.
PUBLIC_CORPUS_DIR = Path("tests") / "fixtures" / "official"

#: A recomputation is offered at most this often. The sweep costs ~19s over ten
#: records, so it never runs inside a request — see ``VerificationState``.
CACHE_TTL_SECONDS = 3600

#: Minimum length of a corpus string worth leak-scanning for. Shorter values
#: ("Cu", "2.5", "eV") collide with legitimate report content — schema path
#: segments and error codes — and would make the scan cry wolf rather than
#: catch anything.
_LEAK_SCAN_MIN_LENGTH = 8


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

LIMITATIONS: tuple[str, ...] = (
    "The corpus is the ten public upstream ISAAC example records vendored at "
    "tests/fixtures/official/. It is not the production-derived corpus, and no "
    "figure here describes production data.",
    "This module opens no connection to any database and imports no driver.",
    "The format shadow is advisory. It does not decide validity, does not gate "
    "export, and does not change what the official validator accepts.",
    "Histogram cells below the floor are withheld, and the number of withheld "
    "categories is never exactly one while any cell is published — one withheld "
    "key against an enumerable universe is identified by elimination.",
    "Failure paths are SCHEMA paths. The per-record instance-path breakdown is "
    "computed internally and deliberately not served: over a small corpus a "
    "count of one at an instance path is a single-record fact.",
    "Mutation counts are global scalars. Per-operator and per-category "
    "breakdowns are absent because mutation applicability is a fact about a "
    "record's structure, so a breakdown is a field-presence map.",
)


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


def _histogram(hist: SuppressedHistogram) -> dict:
    return _project(
        {
            "cells": [{"key": key, "count": count} for key, count in hist.cells],
            "suppressed_categories": hist.suppressed_categories,
            "suppressed_total": hist.suppressed_total,
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

    Sorted so the sweep is deterministic: ``run_harness`` iterates records in
    the order given, and an unordered filesystem listing would make
    ``duration_ms`` and any future per-record ordering vary between runs for no
    reason. A file that will not parse is SKIPPED rather than raising — one bad
    fixture should degrade the corpus, not delete the whole report — and the
    shortfall is visible as ``corpus_size`` below the directory's file count.
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
# Leak scan — a real measurement, not an assertion
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
        VERIFICATION_MODES,
        SHADOW_ERROR_CODES,
        corpus_mutation._MUTATION_KEYS,
        corpus_mutation._ORACLE_KEYS,
        ("ok", "running", "unavailable", "error", "refused", "key", "count"),
    ):
        authored.update(group)
    return frozenset(authored)


def _leak_scan(
    payload: Mapping[str, Any], records: Sequence[Mapping[str, Any]], root: Path
) -> bool:
    """True when no private corpus string appears in what would be served.

    This is what makes ``private_values_exposed: "verified"`` a measurement
    rather than a promise. It runs over the ALREADY-BUILT payload, so it tests
    what would actually be served rather than what the code intends to serve.

    ``limitations`` is blanked before scanning. Those strings are authored in
    this file, are identical on every run, and provably carry nothing
    record-derived — but they are English prose, so they collide with ordinary
    words that also appear in records. Measured on the public corpus: the words
    ``database`` and ``internal`` occur in both. Scanning fixed editorial text
    against a 500-string vocabulary produces false alarms and no true ones.

    Two residuals, stated so the claim is not read as stronger than it is:
    strings shorter than ``_LEAK_SCAN_MIN_LENGTH`` are not scanned, because
    short values ("Cu", "eV") collide with legitimate report content; and a
    value that some transformation reshaped would not be caught by a
    substring scan.
    """
    from .format_shadow import _introspect_root

    _, declared = _introspect_root(Path(root))
    scanned = dict(payload)
    scanned["limitations"] = []
    serialized = json.dumps(scanned, sort_keys=True)
    candidates = _corpus_strings(records, declared) - _authored_strings()
    return not any(value in serialized for value in candidates)


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
# The report
# --------------------------------------------------------------------------


def run_verification(root: Path, *, repeat: int = 3) -> dict:
    """Run all three programs over the public corpus and build the report.

    Costs roughly 19 seconds over ten records. Callers must not invoke this
    inside a request; :class:`VerificationState` exists to keep it off the
    request path.
    """
    root = Path(root)
    started = time.monotonic()
    records = load_public_corpus(root)

    official_passing = sum(1 for r in records if validate_official(dict(r), root).ok)

    shadow_passing = 0
    by_code: Counter[str] = Counter()
    by_schema_path: Counter[str] = Counter()
    for record in records:
        result = shadow_validate(record, root)
        if result.passed:
            shadow_passing += 1
        for finding in result.findings:
            by_code[finding.code] += 1
            by_schema_path[finding.schema_path] += 1
            # `finding.instance_path` is deliberately NOT accumulated. Over a
            # small corpus a count of one at an instance path is a single-record
            # fact; this is the aggregate that shipped in v0.0.32 and was
            # withdrawn (`CLAUDE.md` §15). Do not rebuild it.

    harness = corpus_mutation.run_harness(records, root, repeat=repeat)
    mutation_report = corpus_mutation.build_report(harness)

    duration_ms = int((time.monotonic() - started) * 1000)
    return build_report(
        records=records,
        official_passing=official_passing,
        shadow_passing=shadow_passing,
        by_code=by_code,
        by_schema_path=by_schema_path,
        mutation_report=mutation_report,
        harness=harness,
        duration_ms=duration_ms,
        root=root,
    )


def build_report(
    *,
    records: Sequence[Mapping[str, Any]],
    official_passing: int,
    shadow_passing: int,
    by_code: Mapping[str, int],
    by_schema_path: Mapping[str, int],
    mutation_report: Mapping[str, Any],
    harness: corpus_mutation.HarnessResult,
    duration_ms: int,
    root: Path,
) -> dict:
    """Project everything onto the frozen contract. Raises on an unlisted key."""
    total = len(records)

    metadata = _project(
        {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration_ms": duration_ms,
            "corpus_size": total,
            "cache_age_seconds": 0,
            "verification_mode": PUBLIC_UPSTREAM_CORPUS,
        },
        _METADATA_KEYS,
        strict=True,
    )
    corpus = _project(dict(mutation_report["corpus"]), _CORPUS_KEYS, strict=True)
    official_validation = _project(
        {"passing": official_passing, "failing": total - official_passing},
        _OFFICIAL_VALIDATION_KEYS,
        strict=True,
    )
    format_shadow = _project(
        {
            "records_passing": shadow_passing,
            "records_failing": total - shadow_passing,
            "failures_by_error_code": _histogram(suppress_small_cells(dict(by_code))),
            "failures_by_schema_path": _histogram(
                suppress_small_cells(dict(by_schema_path))
            ),
        },
        _FORMAT_SHADOW_KEYS,
        strict=True,
    )

    oracles = dict(mutation_report["oracles"])
    safeguards = _project(
        {
            # No database was contacted in this mode, so there is no transaction
            # and no query to characterise. "not_applicable" is mandatory here;
            # "verified" would be a claim about an event that never happened.
            "transaction_read_only": "not_applicable",
            "parameterized_queries_only": "not_applicable",
            "dml_statements": 0,
            "ddl_statements": 0,
            # Measured by the harness oracle, which re-reads each source object
            # after every trial. Not an assertion.
            "source_records_modified": (
                "verified" if oracles["source_mutation_failures"] == 0 else "unverified"
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
            "schema_fingerprint": harness.schema_fingerprint,
            "metadata": metadata,
            "corpus": corpus,
            "official_validation": official_validation,
            "format_shadow": format_shadow,
            "mutations": dict(mutation_report["mutations"]),
            "oracles": oracles,
            "safeguards": safeguards,
            "limitations": list(LIMITATIONS),
        },
        _ENVELOPE_KEYS,
        strict=True,
    )

    # The leak scan runs LAST, over the assembled payload, and its own result is
    # then written back. Scanning anything earlier would test a draft.
    payload["safeguards"]["private_values_exposed"] = (
        "verified" if _leak_scan(payload, records, root) else "unverified"
    )
    return payload


def build_pending_report(status: str) -> dict:
    """Sanitized envelope for a run that has produced no result yet.

    ``status`` must be a member of the closed set; anything else becomes
    ``"error"`` rather than being echoed. Projected non-strictly, for the reason
    given in :func:`_project`.
    """
    safe = status if status in ("running", "unavailable", "error", "refused") else "error"
    return _project(
        {
            "status": safe,
            "report_format_version": REPORT_FORMAT_VERSION,
            "schema_version": EXPECTED_VERSION,
            "limitations": list(LIMITATIONS),
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
    """Keeps the ~19s sweep off the request path.

    A request never blocks on the sweep. The first request starts it on a
    background thread and is answered ``running``; later requests are answered
    from cache with an honest ``cache_age_seconds`` until the TTL expires, at
    which point the next request triggers a refresh and is served the STALE
    result rather than nothing — a slightly old measurement beats a blank panel,
    and its age is stated rather than hidden.
    """

    def __init__(self, root: Path, *, ttl_seconds: int = CACHE_TTL_SECONDS) -> None:
        self._root = Path(root)
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._cached: _Cached | None = None
        self._running = False

    def _start(self) -> None:
        """Caller must hold the lock."""
        if self._running:
            return
        self._running = True

        def work() -> None:
            try:
                payload = run_verification(self._root)
            except (KeyboardInterrupt, SystemExit):
                raise
            except BaseException:  # noqa: BLE001 — must never leak, never abort
                # The exception text is NOT captured: it could carry a path or a
                # record value. The caller learns "error", which is all it may
                # safely know.
                payload = build_pending_report("error")
            with self._lock:
                self._cached = _Cached(payload=payload, completed_at=time.monotonic())
                self._running = False

        threading.Thread(target=work, name="isaac-verification", daemon=True).start()

    def get(self) -> dict:
        with self._lock:
            cached = self._cached
            if cached is None:
                self._start()
                return build_pending_report("running")
            age = int(time.monotonic() - cached.completed_at)
            if age >= self._ttl:
                self._start()
            payload = json.loads(json.dumps(cached.payload))

        if isinstance(payload.get("metadata"), dict):
            payload["metadata"]["cache_age_seconds"] = age
        return payload
