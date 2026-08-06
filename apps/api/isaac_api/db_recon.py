"""Read-only, fail-closed reconnaissance of the isolated app Postgres database.

This is the SHARED SERVICE module. It lives under ``apps/api/isaac_api`` on
purpose: the Dockerfile's COPY allowlist ships ``apps/api/`` but ships only ONE
file out of ``scripts/``, so reconnaissance logic placed in ``scripts/`` is
absent from the deployed image. Per ``docs/postgres-test-db-guide.md`` (lines
8-13) the database is reachable **only from the deployed pod**, so the code has
to be in the image to be runnable at all.

Two callers, one implementation:

* ``GET /api/runtime/database/recon`` (``apps/api/isaac_api/routes.py``) — the
  supported path. Runs in the pod, projects a strictly narrower sanitized
  aggregate view, and passes ``require_opt_in=False`` (the pod does not and must
  not need ``ISAAC_RUN_SLAC_DB_RECON``).
* ``scripts/db_recon.py`` — a thin, UNEXECUTED CLI wrapper kept as a design/dev
  artifact. It passes ``require_opt_in=True``.

EXECUTION STATUS (corrected 2026-08-01). This docstring previously read "this
module has **never been run against any database**". That was written on
2026-07-31 at 04:27 (``e7fd755``), when it was true, and was never updated. It
has since been run: the deployed pod contacted the database through
``GET /api/runtime/database/recon`` on image ``v0.0.38`` (``ceea656``), observed
by the operator in an authenticated session.

Treat that result as dated operator TESTIMONY, not as a re-checkable artifact —
the route holds its report in process memory only, under a TTL lock, so no
artifact was ever capable of being produced. The scan logic, the vendored schema
and the response projection are byte-identical at ``7a9f15d``, so the result
still describes the current release; only ``app_commit`` would differ.

The distinction that matters, and the reason this marker caused a false
retraction once already: "no connection was opened during THIS session" is not
"the database has never been contacted". Do not restate the second. If you need
a citable artifact rather than testimony, capture one per
``docs/hosted-qa-checklist.md`` Part 1 — do not infer from this docstring.

Purpose
-------
Answer one high-value question with **aggregate counts only**:

    Do the 30 real production-derived records in the ``metadata_assistant``
    database actually validate against the vendored official schema
    ``schema/isaac_record_v1.json`` (v1.05)?

The vendored schema is ``additionalProperties: false`` at the root and in
dozens of nested places. If the production portal's writers have drifted from
v1.05, real records will fail with ``additionalProperties`` errors. The guide
calls finding that drift "a useful result, not a problem with the database".
This module reports it as counts, rule families and structural signatures.

Safety posture
--------------
* **Read-only.** Only ``SELECT`` and read-only catalog introspection are ever
  issued. Every statement passes :func:`assert_read_only_sql` before execution.
  Session read-only mode is *set* (``conn.set_session(readonly=True)`` plus
  ``SET default_transaction_read_only``) and then *verified* server-side via
  ``SELECT current_setting('transaction_read_only')`` — defence in depth,
  because setting a flag is not the same as confirming it.
* **Fail-closed.** Every gate must hold or the run raises having produced no
  report. Absence of proof is treated as failure.
* **Redacting against the schema, not against a shape heuristic.** The record
  ``data`` JSONB is read into memory (it must be, to validate it). No value is
  ever read into a path, and every object KEY is checked against the property
  names the vendored public schema declares — a key survives only if the schema
  already publishes it. Keys inside ``additionalProperties``-open locations
  (``sample.composition``, ``system.configuration``, ...) are always masked,
  because the writer there may legitimately key the map by a scientific value:
  this repo's own fixtures key ``sample.composition`` by species. Only counts,
  value-stripped structural paths, schema-enum-recognised labels, and salted
  truncated digests of ``record_id`` leave this process.

  An earlier version asked "is this key identifier-shaped?" as a proxy for "is
  this a field name". That is FALSE for exactly the data ISAAC stores —
  chemical formulas and species slugs are identifier-shaped — and it leaked.
  The schema allowlist replaced it. The final leak scan is a backstop for
  ULIDs, environment values and credential shapes; it cannot recognise
  arbitrary science, so it is not what keeps values out.
* **The driver.** ``psycopg2-binary`` IS now a declared project dependency (the
  ``api`` extra), authorized by ``docs/postgres-test-db-guide.md`` line 58. The
  import still lives inside :func:`connect_psycopg2` so this module, and its
  test suite, import and run fine in an environment where the driver happens to
  be absent.

Gates (all must pass; the env gates run before any socket is opened)
--------------------------------------------------------------------
1. ``PGDATABASE`` is exactly ``metadata_assistant``.
2. ``SELECT current_database()`` is exactly ``metadata_assistant``.
3. ``SELECT current_user`` is exactly ``metadata_assistant`` (and
   ``session_user`` matches, so a ``SET ROLE`` cannot slip past).
4. TLS is CONFIRMED via ``pg_stat_ssl`` joined on ``pg_backend_pid()``.
5. The ``records`` table exists and is visible to this role.
6. The environment does not look like the production records database
   (see :func:`check_not_production_shaped` — a backstop, not a guarantee).
7. ``ISAAC_RUN_SLAC_DB_RECON=1`` is set — **only when ``require_opt_in`` is
   True**. The CLI requires it so it can never run by accident. The endpoint
   does not: the pod's feature switch is ``PGHOST`` (the guide's own contract),
   and requiring a second variable nobody sets would make the endpoint
   permanently dead.
8. The transaction is VERIFIED read-only server-side via
   ``current_setting('transaction_read_only')``.
9. The record count is unchanged between the start and end of the run
   (:class:`MutationDetected`). This is a CONCURRENCY CHECK, not a mutation
   proof: a row-count equality cannot detect an ``UPDATE`` and cannot tell our
   writes apart from a concurrent writer's. No write is possible because the
   transaction is verified read-only server-side (gate 8) and every statement
   passes the SELECT-only allowlist (:func:`assert_read_only_sql`).

The Postgres major version is **reported, never gated**: the guide documents
Postgres 18 (:data:`EXPECTED_SERVER_MAJOR_VERSION`) and the report carries
``expected_major_version_match``, but a mismatch is information, not a refusal.

Every gate fails CLOSED: absence of proof is treated as failure, never as a
pass.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

# --- repo root ----------------------------------------------------------------
# Resolved by the SAME mechanism the rest of the API already uses
# (``workspace._find_repo_root`` walks up until ``schema/isaac_record_v1.json``
# is found), so this module is correct both in a developer checkout
# (``<repo>/apps/api/isaac_api/``) and inside the container image, where the
# layout is ``/app/{schema,src,apps/api}`` and a ``parent.parent`` guess would
# point at ``/app/apps``. Never a hardcoded path.
from .workspace import REPO_ROOT  # noqa: F401  (re-exported for callers/tests)

_log = logging.getLogger("db_recon")

RECON_SCHEMA_VERSION = 1

EXPECTED_DATABASE = "metadata_assistant"
EXPECTED_ROLE = "metadata_assistant"
OPT_IN_ENV = "ISAAC_RUN_SLAC_DB_RECON"
OPT_IN_VALUE = "1"
RAW_ID_ENV = "ISAAC_DB_RECON_ALLOW_RAW_IDS"

#: Documented seed size from docs/postgres-test-db-guide.md: "the 30 earliest
#: real records from production".
DOCUMENTED_SEED_ROWS = 30

#: Production-shape refusal threshold for ``records``.
#:
#: Justification: the documented seed is exactly 30 rows, and the guide is
#: explicit that "the seeded rows are real production-derived records" while
#: the app "may **write** whatever it needs to" inside its own database — so a
#: developer or the app under test may legitimately have added rows on top of
#: the seed. 500 gives ~16x headroom over the seed while staying orders of
#: magnitude below any plausible production corpus for a facility records
#: portal.
#:
#: CORRECTION (2026-07-31): an earlier revision of this comment justified the
#: headroom by quoting the guide as calling the data "disposable test data:
#: write, mutate, and drop freely". Dean DELETED that sentence in ``b746b1a``
#: and replaced it with "the seeded rows are real production-derived records".
#: The row-count headroom is unchanged; the reason for it is not "the data is
#: disposable", it is "the app owns the database and may write to it".
#:
#: HONEST LIMIT: this is a BACKSTOP, not a guarantee. A production database
#: that happened to be small would sail straight through it, and a database
#: that someone bulk-loaded would be refused as a false positive. The real
#: isolation guarantee is the one stated in the guide — the
#: ``metadata_assistant`` role "has no grant into any other database on the
#: cluster, so it cannot reach the production records DB at all" — which this
#: module cannot verify from inside a connection. Gates 2, 3 and the
#: non-superuser / table-owner checks below are positive identification of the
#: least-privilege role; this row-count check is only a tripwire for the case
#: where that role was later granted more than the guide describes.
MAX_PLAUSIBLE_RECORD_ROWS = 500

#: The Postgres major version the guide documents ("Postgres 18"). REPORTED,
#: NEVER GATED: a cluster upgrade must not turn this endpoint into a refusal.
#: The report carries ``expected_major_version_match`` so a mismatch is visible
#: as information.
EXPECTED_SERVER_MAJOR_VERSION = 18

#: Fetch bound so a surprise-huge table cannot be pulled into memory wholesale.
DEFAULT_MAX_RECORDS = 1000

#: Values of these columns are emitted verbatim ONLY when they are members of
#: the vendored public schema's enum for that field. Anything else is reported
#: as a masked bucket with its count — which is itself the drift signal we
#: want, without leaking an unvetted string.
SCHEMA_ENUM_RECORD_TYPE = frozenset({"evidence", "intent", "synthesis"})
SCHEMA_ENUM_RECORD_DOMAIN = frozenset(
    {"characterization", "performance", "simulation", "theory", "derived"}
)
#: ``isaac_record_version`` is a schema ``const`` of "1.05"; any dotted numeric
#: version is safe to name (it is a version string, not science) and naming it
#: is the entire point of the drift check.
_VERSION_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){0,2}\Z")

MASK_UNRECOGNISED = "<unrecognized>"
MASK_NON_IDENTIFIER = "<non-identifier-key>"
MASK_WITHHELD = "<withheld>"
MASK_NULL_BUCKET = "<null>"
#: A key inside a schema location that is ``additionalProperties``-open BY
#: DESIGN. At those locations the writer legitimately keys the map by a
#: scientific value (``sample.composition`` is keyed by species in this repo's
#: own fixtures), so the key itself is data. Masking to a fixed token keeps the
#: structural shape — "this open map has members" — while naming nothing.
MASK_OPEN_MAP_KEY = "<open-map-key>"
#: A key that is not a property name declared anywhere in the vendored schema
#: and is not inside a known-open map. It is either drift or a value-as-key;
#: either way it must not be named.
MASK_UNDECLARED_KEY = "<undeclared-key>"

#: Column names in ``vocabulary_cache`` whose grouped values may be emitted,
#: and only then if each value is identifier-shaped (a controlled-vocabulary
#: category slug, not free text). Everything else: counts only.
VOCAB_CATEGORY_COLUMN_ALLOWLIST = frozenset(
    {"category", "term_type", "term_category", "vocabulary_type", "vocab_type"}
)

# ``\Z`` not ``$``: Python's ``$`` also matches immediately before a trailing
# newline, so ``^...$`` would pass "CuO2\n" through unmasked.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
_LOWER_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}\Z")

#: The shape of a raw ``record_id``: a 26-character ULID. Deliberately broader
#: than strict Crockford base32 (which excludes I/L/O/U) — this is a leak
#: detector, so a near-miss must trip it too. Nothing this module legitimately
#: emits is a 26-character run of uppercase alphanumerics.
_ULID_RE = re.compile(r"\b[0-9A-Z]{26}\b")

ARRAY_SEGMENT = "[]"
MAX_STRUCTURE_DEPTH = 40
MAX_PATHS_PER_RECORD = 4000

#: Exit code for anything not modelled as a refusal. Distinct from every
#: ``ReconRefusal.exit_code`` (2-7) so an operator can tell "a gate stopped me"
#: from "something unexpected broke".
EXIT_UNEXPECTED_ERROR = 8


class ReconRefusal(Exception):
    """A fail-closed gate refused to proceed. Names the gate; leaks nothing."""

    exit_code = 2

    def __init__(self, gate: str, reason: str) -> None:
        super().__init__(f"gate={gate}: {reason}")
        self.gate = gate
        self.reason = reason


class UnsafeStatement(ReconRefusal):
    """A statement failed the read-only guard."""

    def __init__(self, reason: str) -> None:
        super().__init__("read_only_sql", reason)


class MissingDependency(ReconRefusal):
    """psycopg2 is not importable."""

    exit_code = 5

    def __init__(self, reason: str) -> None:
        super().__init__("psycopg2_available", reason)


class ConnectionRefused(ReconRefusal):
    exit_code = 6

    def __init__(self, reason: str) -> None:
        super().__init__("connect", reason)


class LeakDetected(ReconRefusal):
    exit_code = 3

    def __init__(self, codes: Sequence[str]) -> None:
        super().__init__("leak_scan", "forbidden content in report: " + ", ".join(codes))
        self.codes = list(codes)


class MutationDetected(ReconRefusal):
    exit_code = 4

    def __init__(self, reason: str) -> None:
        super().__init__("no_mutation", reason)


class UsageError(ReconRefusal):
    exit_code = 7

    def __init__(self, gate: str, reason: str) -> None:
        super().__init__(gate, reason)


# --- read-only SQL guard -----------------------------------------------------

#: Statement-initial keywords allowed by the general helper. Everything that
#: can write, lock, or change session/transaction state is excluded.
_ALLOWED_LEADING = ("select", "with")

#: Word tokens that must not appear anywhere in a statement handed to
#: :func:`run_read_only`. ``\b`` boundaries mean ``created_at`` /
#: ``updated_at`` / ``record_history`` do not false-positive (the following
#: character is a word character, so there is no boundary after the keyword).
_FORBIDDEN_TOKENS = (
    "insert", "update", "delete", "drop", "create", "alter", "truncate",
    "grant", "revoke", "copy", "merge", "call", "do", "vacuum", "analyze",
    "reindex", "cluster", "comment", "lock", "begin", "start", "commit",
    "rollback", "savepoint", "release", "prepare", "execute", "deallocate",
    "listen", "notify", "unlisten", "discard", "reset", "refresh", "import",
    "checkpoint", "load", "move", "fetch", "close", "declare", "set",
    "nextval", "setval", "pg_terminate_backend", "pg_cancel_backend",
    "pg_read_file", "pg_read_binary_file", "lo_import", "lo_export",
    "dblink", "into",
)
_FORBIDDEN_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(t) for t in _FORBIDDEN_TOKENS) + r")\b"
)

#: The ONLY non-SELECT statements this module may execute, as exact literals.
#: All three make the session *more* restrictive; none can write data.
SESSION_READ_ONLY_STATEMENTS = (
    "SET default_transaction_read_only = on",
    "SET TRANSACTION READ ONLY",
    "SET statement_timeout = '30s'",
)


def _normalise_sql(sql: str) -> str:
    """Lowercase, strip comments, collapse whitespace, drop one trailing ';'."""
    text = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    text = re.sub(r"--[^\n]*", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    if text.endswith(";"):
        text = text[:-1].rstrip()
    return text


def assert_read_only_sql(sql: str) -> str:
    """Raise :class:`UnsafeStatement` unless ``sql`` is a single read-only query.

    Belt-and-braces over the server-side read-only transaction: a bug that
    constructs a write statement is stopped in this process, before it reaches
    a socket.
    """
    if not isinstance(sql, str) or not sql.strip():
        raise UnsafeStatement("empty or non-string statement")
    text = _normalise_sql(sql)
    if ";" in text:
        raise UnsafeStatement("multiple statements are not allowed")
    if not text.startswith(_ALLOWED_LEADING):
        raise UnsafeStatement("statement does not begin with SELECT or WITH")
    hit = _FORBIDDEN_RE.search(text)
    if hit:
        # The token itself is a SQL keyword, never data — safe to name.
        raise UnsafeStatement(f"forbidden token {hit.group(0)!r} in statement")
    return sql


def _assert_session_statement(sql: str) -> str:
    if sql not in SESSION_READ_ONLY_STATEMENTS:
        raise UnsafeStatement("session statement is not in the read-only allowlist")
    return sql


def _quote_ident(name: str) -> str:
    """Double-quote a catalog-supplied identifier after validating its shape.

    Identifiers cannot be bound as parameters, so the one place this module
    interpolates into SQL is a column name that came back from
    ``information_schema.columns``. It must match ``_IDENTIFIER_RE`` first.
    Data VALUES are never interpolated — they are always ``%s`` parameters.
    """
    if not _IDENTIFIER_RE.match(str(name)):
        raise UnsafeStatement("refusing to interpolate a non-identifier column name")
    return '"' + str(name) + '"'


# --- redaction primitives ----------------------------------------------------


def load_schema_vocabulary(repo_root: Path) -> tuple[frozenset[str], frozenset[str]]:
    """Read the vendored schema and return ``(declared_names, open_map_paths)``.

    ``declared_names`` is every property name the authoritative schema declares
    anywhere. ``open_map_paths`` is every structural path (in the same ``a/b/[]``
    notation :func:`structural_paths` emits) whose subschema is an object that
    does NOT set ``additionalProperties: false`` — i.e. a map the schema leaves
    open by design, where the writer may legitimately use a scientific value as
    a key.

    This is the anchor for the whole redaction policy. The previous policy asked
    "is this key identifier-shaped?", which is FALSE as a proxy for "is this a
    field name": chemical formulas, gas species, beamline slugs and sample codes
    are all identifier-shaped. This asks the only question that is actually
    sound — "does the public, vendored schema declare this name?" — so a key can
    be emitted only if it is already public information.

    The cache lives in :func:`_schema_vocabulary_for`, keyed on the resolved
    schema path plus its ``st_mtime_ns`` and ``st_size`` — parity with
    ``official._checked_schema_text``, including parity in what it does NOT
    guarantee: an edit that lands in the same nanosecond tick AND leaves the byte
    length unchanged is still served stale. It is a heuristic, not content
    identity. This wrapper keeps the public
    ``(repo_root: Path) -> (frozenset, frozenset)`` contract callers and tests
    depend on. The wrapper now costs a ``stat()`` per call (~0.09 us -> ~6 us);
    it is called per record and per error, so the multiplier is large even though
    the absolute cost stays trivial.
    """
    # Imported lazily, matching how this module reaches isaac_records elsewhere,
    # and resolved through official.schema_path so the path is never hardcoded.
    from isaac_records.official import schema_path as official_schema_path

    path = official_schema_path(repo_root)
    stat = path.stat()
    return _schema_vocabulary_for(str(path), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=4)
def _schema_vocabulary_for(
    path_str: str, mtime_ns: int, size: int
) -> tuple[frozenset[str], frozenset[str]]:
    """Cached body of :func:`load_schema_vocabulary`; see it for the policy."""
    schema = json.loads(Path(path_str).read_bytes())
    declared: set[str] = set()
    open_maps: set[str] = set()

    def walk(node: Any, path: str, may_open: bool) -> None:
        if not isinstance(node, dict):
            return
        props = node.get("properties")
        is_open = node.get("additionalProperties") is not False
        if isinstance(props, dict):
            # An object that declares properties but does not close itself is
            # open by design. ``may_open`` is False inside a combinator branch:
            # an allOf/if/then fragment constrains the SAME object as its
            # parent, so it must not re-decide that object's openness (without
            # this, the root — which IS closed — was registered as open via its
            # own allOf branches).
            if may_open and is_open:
                open_maps.add(path)
            for name, sub in props.items():
                declared.add(str(name))
                walk(sub, f"{path}/{name}" if path else str(name), True)
        elif may_open and path and node.get("type") == "object" and is_open:
            # A free-form object with no declared properties: open by design.
            open_maps.add(path)
        items = node.get("items")
        if isinstance(items, dict):
            walk(items, f"{path}/{ARRAY_SEGMENT}" if path else ARRAY_SEGMENT, True)
        for combinator in ("allOf", "anyOf", "oneOf"):
            for sub in node.get(combinator) or []:
                walk(sub, path, False)
        for branch in ("if", "then", "else", "not"):
            if isinstance(node.get(branch), dict):
                walk(node[branch], path, False)
        for container in ("$defs", "definitions"):
            for name, sub in (node.get(container) or {}).items():
                declared.add(str(name))
                walk(sub, path, True)

    walk(schema, "", True)
    return frozenset(declared), frozenset(open_maps)


def safe_key_segment(
    key: Any,
    parent_path: str = "",
    declared: frozenset[str] | None = None,
    open_maps: frozenset[str] | None = None,
) -> str:
    """Emit ``key`` only if the vendored schema declares it as a property name.

    Three outcomes, in priority order:

    * ``parent_path`` is a schema location that is open by design ->
      :data:`MASK_OPEN_MAP_KEY`. The key there is data, however it is shaped.
    * the key is not identifier-shaped -> :data:`MASK_NON_IDENTIFIER`.
    * the key is not declared anywhere in the schema -> :data:`MASK_UNDECLARED_KEY`.

    Only a name the public schema already publishes survives verbatim.

    ``declared``/``open_maps`` default to the vendored schema's vocabulary. They
    are parameters so tests can drive the logic directly, NOT so a caller can
    widen the allowlist: a wider set can only ever be a subset of what the
    schema already publishes if callers pass what :func:`load_schema_vocabulary`
    returned.
    """
    if declared is None or open_maps is None:
        loaded_declared, loaded_open = load_schema_vocabulary(REPO_ROOT)
        declared = loaded_declared if declared is None else declared
        open_maps = loaded_open if open_maps is None else open_maps
    text = str(key)
    if parent_path and parent_path in open_maps:
        return MASK_OPEN_MAP_KEY
    if not _IDENTIFIER_RE.match(text):
        return MASK_NON_IDENTIFIER
    if text not in declared:
        return MASK_UNDECLARED_KEY
    return text


def safe_sql_identifier(name: Any) -> str:
    """Mask a TABLE or COLUMN name by shape only — not by the record allowlist.

    A SQL identifier from ``information_schema`` is database structure, not
    record content: it is fixed by the mirrored portal DDL that Dean's guide
    publishes, and no scientific value can occupy that position. It must NOT go
    through :func:`safe_key_segment`, whose allowlist is the ISAAC *record*
    schema — ``category`` and ``term_type`` are real columns but are not record
    property names, so that check would wrongly mask the entire table inventory.

    Shape is still enforced: anything not identifier-shaped is masked, because a
    non-identifier "column name" means something unexpected is being reported.
    """
    text = str(name)
    return text if _IDENTIFIER_RE.match(text) else MASK_NON_IDENTIFIER


def safe_enum_value(value: Any, allowed: Iterable[str]) -> str:
    """Emit ``value`` only if it is a member of a vendored public schema enum.

    Anything unrecognised collapses into ``<unrecognized>``. The count of the
    unrecognised bucket is itself the drift signal, so nothing is lost, and an
    unvetted database string never reaches the report.
    """
    if value is None:
        return MASK_NULL_BUCKET
    text = str(value).strip()
    return text if text in set(allowed) else MASK_UNRECOGNISED


def safe_version_value(value: Any) -> str:
    """Version strings are structure, not science — emit if dotted-numeric."""
    if value is None:
        return MASK_NULL_BUCKET
    text = str(value).strip()
    return text if _VERSION_RE.match(text) else MASK_UNRECOGNISED


def server_major_version(version_text: Any, version_num: Any = None) -> Optional[int]:
    """Parse the Postgres MAJOR version. Returns ``None`` when unparseable.

    Never raises and never gates: the caller reports the result alongside
    :data:`EXPECTED_SERVER_MAJOR_VERSION` as information.
    """
    try:
        if version_num is not None:
            num = int(version_num)
            if num >= 100000:  # 180000 -> 18
                return num // 10000
            if num > 0:  # pre-10 style, 90624 -> 9
                return num // 10000
    except (TypeError, ValueError):
        pass
    match = re.match(r"^\s*(\d{1,3})", str(version_text or ""))
    return int(match.group(1)) if match else None


def link_targets(document: Any) -> list[str]:
    """Every ``links[].target`` in a record, for COUNTING only.

    The schema declares ``links`` as an array of objects whose ``target`` is a
    26-character ULID pattern. The returned strings are record identifiers and
    are therefore NEVER emitted — the only thing a caller may derive from them
    is a count (how many link targets fall outside the scanned id set).
    """
    if not isinstance(document, dict):
        return []
    links = document.get("links")
    if not isinstance(links, list):
        return []
    out: list[str] = []
    for entry in links:
        if isinstance(entry, dict):
            target = entry.get("target")
            if isinstance(target, str) and target.strip():
                out.append(target.strip())
    return out


# --- schema authority ---------------------------------------------------------

#: Root properties the official v1.05 schema MUST declare. A trimmed or partial
#: stand-in schema would not, and must never be accepted as validator authority
#: — validating real records against a subset schema would report a false
#: "everything passes".
REQUIRED_ROOT_PROPERTIES = frozenset(
    {
        "isaac_record_version",
        "record_id",
        "record_type",
        "record_domain",
        "source_type",
        "timestamps",
    }
)


def schema_authority(root: Path = REPO_ROOT) -> dict[str, Any]:
    """Fingerprint the vendored schema and PROVE it is the full official one.

    Returns ``{"fingerprint", "full_schema", "declared_version"}``.
    ``full_schema`` is True only when the file the validator will actually load
    is closed at the root (``additionalProperties: false``), declares every
    member of :data:`REQUIRED_ROOT_PROPERTIES`, requires them, and pins
    ``isaac_record_version`` to the version this build expects. Any failure is
    a refusal condition for the caller — fail closed.
    """
    from isaac_records.official import EXPECTED_VERSION
    from isaac_records.official import schema_path as official_schema_path

    raw = official_schema_path(Path(root)).read_bytes()
    fingerprint = hashlib.sha256(raw).hexdigest()
    try:
        schema = json.loads(raw)
    except ValueError:
        return {"fingerprint": fingerprint, "full_schema": False, "declared_version": None}
    props = schema.get("properties")
    declared_version = None
    if isinstance(props, dict) and isinstance(props.get("isaac_record_version"), dict):
        declared_version = props["isaac_record_version"].get("const")
    full = (
        schema.get("additionalProperties") is False
        and isinstance(props, dict)
        and REQUIRED_ROOT_PROPERTIES <= set(props)
        and REQUIRED_ROOT_PROPERTIES <= set(schema.get("required") or [])
        and declared_version == EXPECTED_VERSION
    )
    return {
        "fingerprint": fingerprint,
        "full_schema": bool(full),
        "declared_version": declared_version,
    }


# --- statement auditing -------------------------------------------------------

#: Statement-initial keywords that WRITE data.
_DML_LEADING = ("insert", "update", "delete", "merge", "truncate", "copy")
#: Statement-initial keywords that change SCHEMA.
_DDL_LEADING = ("create", "alter", "drop", "grant", "revoke", "comment", "refresh")


def classify_statement(sql: Any) -> str:
    """Classify a statement as ``read``/``session``/``dml``/``ddl``/``other``.

    Used by :class:`StatementAudit` so "no DML and no DDL was issued" is an
    OBSERVATION of what actually reached a cursor, not a claim the report makes
    about itself.
    """
    if isinstance(sql, str) and sql in SESSION_READ_ONLY_STATEMENTS:
        return "session"
    text = _normalise_sql(sql if isinstance(sql, str) else str(sql))
    if not text:
        return "other"
    if text.startswith(_DML_LEADING):
        return "dml"
    if text.startswith(_DDL_LEADING):
        return "ddl"
    if text.startswith(_ALLOWED_LEADING):
        return "read"
    return "other"


class StatementAudit:
    """Counts, by class, every statement issued through a cursor by this service.

    SCOPE, stated precisely: the audit sits in :class:`_AuditedCursor`, so it
    sees exactly the statements this module executes. It is NOT a wire-level
    record — the driver's own transaction framing (``BEGIN``, ``ROLLBACK``, the
    ``SET SESSION CHARACTERISTICS`` psycopg2 emits for ``set_session``) never
    passes through a cursor and is therefore never counted. ``dml``/``ddl`` of
    zero remains correct and meaningful: the driver's framing contains no DML
    and no DDL.
    """

    __slots__ = ("counts",)

    def __init__(self) -> None:
        self.counts: dict[str, int] = {
            "read": 0,
            "session": 0,
            "dml": 0,
            "ddl": 0,
            "other": 0,
        }

    def record(self, sql: Any) -> None:
        self.counts[classify_statement(sql)] += 1

    def as_dict(self) -> dict[str, int]:
        return dict(self.counts)


class _AuditedCursor:
    """Cursor proxy that counts statements. Forwards everything else."""

    def __init__(self, cursor: Any, audit: StatementAudit) -> None:
        self._cursor = cursor
        self._audit = audit

    def execute(self, sql: Any, params: Any = None) -> Any:
        self._audit.record(sql)
        if params is None:
            return self._cursor.execute(sql)
        return self._cursor.execute(sql, params)

    def fetchall(self) -> Any:
        return self._cursor.fetchall()

    def close(self) -> Any:
        return self._cursor.close()

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - passthrough
        return getattr(self._cursor, name)


class AuditedConnection:
    """Connection proxy handing out :class:`_AuditedCursor` objects.

    Wrapping is what makes ``dml_statements_issued: 0`` an observation about
    every statement THIS SERVICE issues through a cursor. It adds no behaviour
    of its own and opens nothing. See :class:`StatementAudit` for what the
    counts do and do not cover — the driver's own transaction framing is not
    routed through a cursor and so is not counted.
    """

    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self.audit = StatementAudit()

    def cursor(self, *args: Any, **kwargs: Any) -> _AuditedCursor:
        return _AuditedCursor(self._connection.cursor(*args, **kwargs), self.audit)

    def set_session(self, *args: Any, **kwargs: Any) -> Any:
        setter = getattr(self._connection, "set_session", None)
        if setter is None:
            raise AttributeError("set_session")
        return setter(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - passthrough
        return getattr(self._connection, name)


def hash_record_id(record_id: str, salt: str) -> str:
    """Salted, truncated digest of a ``record_id``.

    Whether raw ``record_id`` ULIDs are safe to emit is UNDECIDED by the
    project owner, so the default is a one-way digest: enough to count and
    de-duplicate records, not enough to name one. The salt is never emitted.
    """
    # ``record_id`` is CHAR(26) and Postgres blank-pads fixed-width columns, so
    # strip here too rather than trusting every caller to have done it
    # (docs/postgres-test-db-guide.md, "Gotchas to code around").
    normalised = str(record_id).strip()
    digest = hashlib.sha256(salt.encode("utf-8") + b"\x00" + normalised.encode("utf-8"))
    return digest.hexdigest()[:16]


def counted_buckets(pairs: Iterable[tuple[str, int]]) -> list[dict[str, Any]]:
    """Merge ``(value, count)`` pairs deterministically: count desc, then value."""
    merged: dict[str, int] = {}
    for value, count in pairs:
        merged[value] = merged.get(value, 0) + int(count)
    return [
        {"value": value, "count": merged[value]}
        for value in sorted(merged, key=lambda v: (-merged[v], v))
    ]


# --- structural signatures ---------------------------------------------------


def structural_paths(document: Any) -> tuple[list[str], dict[str, Any]]:
    """Sorted set of JSON paths present in ``document``, with values stripped.

    Algorithm
    ---------
    * Depth-first walk. Every node except the root contributes exactly one path.
    * Object keys contribute ``parent/key``, with the key passed through
      :func:`safe_key_segment`.
    * Arrays collapse: a non-empty list contributes a single ``parent/[]``
      segment and every element recurses under that same prefix, so
      ``descriptors[0].name`` and ``descriptors[7].name`` both become
      ``descriptors/[]/name`` and signatures aggregate meaningfully across
      records. An EMPTY list contributes no ``[]`` segment (there is no element
      structure to describe) — only its own key path, added by its parent.
    * Scalars (str/int/float/bool/None) contribute nothing of their own; their
      key path was already added by the containing object or array. **No value
      is ever read into a path.**
    * Output is ``sorted()``, so it is deterministic for identical input and
      independent of dict insertion order.
    * Bounded: ``MAX_STRUCTURE_DEPTH`` deep and ``MAX_PATHS_PER_RECORD`` wide;
      exceeding either sets a truncation flag rather than emitting unbounded
      output.
    """
    paths: set[str] = set()
    stats = {"masked_key_segments": 0, "depth_truncated": False, "width_truncated": False}
    declared, open_maps = load_schema_vocabulary(REPO_ROOT)
    _masks = (MASK_NON_IDENTIFIER, MASK_UNDECLARED_KEY, MASK_OPEN_MAP_KEY)

    def walk(node: Any, prefix: str, depth: int) -> None:
        if stats["width_truncated"]:
            return
        if depth > MAX_STRUCTURE_DEPTH:
            stats["depth_truncated"] = True
            if prefix:
                paths.add(prefix + "/<max-depth>")
            return
        if isinstance(node, dict):
            for key in node:
                segment = safe_key_segment(key, prefix, declared, open_maps)
                # Count EVERY masked segment, not just one flavour. This counter
                # is what an operator checks for reassurance, so it must never
                # read 0 while keys are in fact being withheld (review C2).
                if segment in _masks:
                    stats["masked_key_segments"] += 1
                child = f"{prefix}/{segment}" if prefix else segment
                if len(paths) >= MAX_PATHS_PER_RECORD:
                    stats["width_truncated"] = True
                    return
                paths.add(child)
                walk(node[key], child, depth + 1)
        elif isinstance(node, list):
            if not node:
                return
            child = f"{prefix}/{ARRAY_SEGMENT}" if prefix else ARRAY_SEGMENT
            if len(paths) >= MAX_PATHS_PER_RECORD:
                stats["width_truncated"] = True
                return
            paths.add(child)
            for item in node:
                walk(item, child, depth + 1)
        # scalars contribute nothing; their path came from the parent

    walk(document, "", 0)
    return sorted(paths), stats


def signature_id(paths: Sequence[str]) -> str:
    """Stable 16-hex id for a path set. Unsalted: paths carry no values."""
    return hashlib.sha256("\n".join(paths).encode("utf-8")).hexdigest()[:16]


def collapse_instance_path(path: str) -> str:
    """Normalise a validator instance path for aggregation.

    ``validate_official`` renders ``ErrorTree.absolute_path`` as dot-joined
    segments, so array indices arrive as digit strings. Digits collapse to
    ``[]`` and non-identifier segments are masked, exactly as in
    :func:`structural_paths`, so error paths aggregate the same way structural
    paths do.

    LIMITATION: because the upstream join uses ``.``, a field name that itself
    contained a dot would be split here. No v1.05 field name does.
    """
    if not path or path == "$":
        return "$"
    return _collapse_segments(str(path).split("."))


def _collapse_segments(segments: Sequence[str]) -> str:
    """Collapse indices to ``[]`` and mask each key against the schema allowlist.

    The parent path is rebuilt as we go and fed to :func:`safe_key_segment`, so a
    segment sitting inside an ``additionalProperties``-open location is masked
    as an open-map key exactly as it would be in :func:`structural_paths`. Both
    functions therefore agree on what is and is not safe to name.
    """
    declared, open_maps = load_schema_vocabulary(REPO_ROOT)
    out: list[str] = []
    parent = ""
    for segment in segments:
        if segment.isdigit():
            token = ARRAY_SEGMENT
        else:
            token = safe_key_segment(segment, parent, declared, open_maps)
        out.append(token)
        parent = f"{parent}/{token}" if parent else token
    return "/".join(out)


#: Keywords that legitimately appear in a JSON Schema pointer. A schema pointer
#: is derived from the vendored PUBLIC schema, so it can never carry record
#: data — but we still allowlist rather than pass through, so a future caller
#: that hands an instance pointer to the wrong function fails safe.
_SCHEMA_KEYWORDS = frozenset(
    {
        "properties", "items", "required", "allOf", "anyOf", "oneOf", "not",
        "if", "then", "else", "$defs", "definitions", "additionalProperties",
        "patternProperties", "prefixItems", "contains", "propertyNames",
        "dependentRequired", "dependentSchemas", "enum", "const", "pattern",
        "format", "type", "minItems", "maxItems", "minLength", "maxLength",
        "minimum", "maximum", "uniqueItems", "minProperties", "maxProperties",
    }
)


def collapse_schema_pointer(pointer: str) -> str:
    """Collapse a pointer into the SCHEMA (not into a record instance).

    Schema pointers name JSON Schema keywords and declared property names, both
    of which are public information published in the vendored schema file, so
    they are emitted verbatim. Anything that is neither is masked — a schema
    pointer should never contain such a segment, and if one appears it means an
    instance pointer reached this function by mistake.
    """
    text = str(pointer or "")
    if text in {"", "/", "$"}:
        return "$"
    declared, _ = load_schema_vocabulary(REPO_ROOT)
    out: list[str] = []
    for segment in [s for s in text.lstrip("/").split("/") if s != ""]:
        unescaped = segment.replace("~1", "/").replace("~0", "~")
        if unescaped.isdigit():
            out.append(unescaped)
        elif unescaped in _SCHEMA_KEYWORDS or unescaped in declared:
            out.append(unescaped)
        else:
            out.append(MASK_UNDECLARED_KEY)
    return "/".join(out) or "$"


# --- validation rule families ------------------------------------------------

#: Classify a jsonschema error message into a rule family. The MESSAGE ITSELF IS
#: NEVER EMITTED — jsonschema embeds the offending value in most messages
#: ("'CuO nanopowder' is not one of [...]"), which would be a direct scientific
#: value leak. Only the family label and the collapsed instance path escape.
_FAMILY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("additional_properties", re.compile(r"[Aa]dditional properties are not allowed")),
    ("required", re.compile(r"is a required property")),
    ("const", re.compile(r"was expected")),
    ("enum", re.compile(r"is not one of")),
    ("type", re.compile(r"is not of type")),
    ("pattern", re.compile(r"does not match")),
    ("format", re.compile(r"is not a '[^']*'")),
    ("any_of", re.compile(r"is not valid under any of the given schemas")),
    ("one_of", re.compile(r"is valid under each of")),
    (
        "bounds",
        re.compile(
            r"is too short|is too long|has too few items|has too many items|"
            r"is less than|is greater than|does not have enough properties|"
            r"has too many properties"
        ),
    ),
    ("unique_items", re.compile(r"has non-unique elements")),
    ("dependency", re.compile(r"is a dependency of")),
)

_UNEXPECTED_PROPS_RE = re.compile(r"'([^']*)'")

#: Both spellings of the additionalProperties rule family that can reach the
#: aggregator. :func:`rule_family` normalizes the official engine's message to
#: ``additional_properties``; ``isaac_records.diagnostics`` reports the raw
#: jsonschema keyword ``additionalProperties`` instead. They denote the same
#: failure, and :func:`aggregate_validation` has to recognize either to tell
#: "no structural drift was found" apart from "drift detail was not computed".
#: The family label each engine emits is NOT rewritten — the report says which
#: engine produced it, and renaming its taxonomy would misreport that.
ADDITIONAL_PROPERTIES_FAMILIES = frozenset({"additional_properties", "additionalProperties"})


def rule_family(message: str) -> str:
    """Map a validator message to a family label. Never returns the message."""
    text = str(message or "")
    for family, pattern in _FAMILY_PATTERNS:
        if pattern.search(text):
            return family
    return "other"


def unexpected_property_names(
    message: str, declared: frozenset[str] | None = None
) -> list[str]:
    """Extract the offending KEY names from an additionalProperties message.

    jsonschema renders ``Additional properties are not allowed ('a', 'b' were
    unexpected)``. An *unexpected* property is by definition one the schema does
    not declare, so under the schema-allowlist policy it must be masked: the
    only names that survive are ones the public vendored schema already
    publishes (which happens when a property is declared elsewhere in the schema
    but is not valid at this location — genuine, non-sensitive structure drift).

    Everything else collapses to :data:`MASK_UNDECLARED_KEY`. The COUNT of
    unexpected properties and the parent path are retained by the caller, and
    those are the actual schema-drift signal — they name nothing.
    """
    if rule_family(message) != "additional_properties":
        return []
    if declared is None:
        declared, _ = load_schema_vocabulary(REPO_ROOT)
    out: set[str] = set()
    for name in _UNEXPECTED_PROPS_RE.findall(str(message)):
        text = str(name)
        out.add(text if _IDENTIFIER_RE.match(text) and text in declared else MASK_UNDECLARED_KEY)
    return sorted(out)


# --- final leak scan ---------------------------------------------------------

_SECRET_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pem_block", re.compile(r"-----BEGIN [A-Z ]*")),
    ("connection_uri", re.compile(r"postgres(?:ql)?://", re.IGNORECASE)),
    ("uri_credentials", re.compile(r"://[^/\s]*:[^/\s]*@")),
    ("password_assignment", re.compile(r"(?i)\bpassword\s*[=:]\s*\S")),
    ("pgpassword_literal", re.compile(r"(?i)\bPGPASSWORD\b")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}")),
)

#: Env vars whose VALUES must never appear in the report. ``PGUSER`` is
#: deliberately absent: its value is the role name ``metadata_assistant``, which
#: the report emits on purpose as gate-3 evidence.
_FORBIDDEN_ENV_VALUES = ("PGPASSWORD", "PGHOST", "PGPASSFILE", "PGSSLKEY", "PGSSLCERT")


def string_leaves(node: Any) -> tuple[str, ...]:
    """Every string in ``node``, keys included, decoded and unescaped.

    The same unit :func:`verification._string_leaves` compares against, and for
    the same reason (see :func:`scan_for_leaks`). Keys are collected as well as
    values because a leaked value can arrive as a mapping KEY — which is exactly
    the shape the recon report's histogram cells have.
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


def scan_for_leaks(
    text: str, *, env: Mapping[str, str], allow_raw_ids: bool, leaves: Sequence[str]
) -> list[str]:
    """Return issue CODES for forbidden content in the report.

    Codes only — never the matched text, or the scanner would itself become the
    leak. An empty list means the report is clear.

    IT MATCHES AGAINST DECODED LEAVES AS WELL AS THE SERIALIZED TEXT
    ===============================================================
    This is a correction of a real defect, recorded rather than silently
    replaced, and it is the SAME defect that ``verification._leak_scan``
    documents (with ``verification._string_leaves`` as its decoded-leaf walker)
    — fixed there, and for a while still live here. That module is NOT on
    ``main``: it arrives with ``feat/record-verification`` (PR #63), so until
    that merges the citation resolves only on that branch.

    Both call sites in ``routes.py`` pass ``json.dumps(payload,
    ensure_ascii=True)``. That escapes any non-ASCII character to ``\\uXXXX``,
    and JSON *always* escapes ``"``, ``\\``, newline and tab. So a forbidden env
    value containing any of those appeared in ``text`` in a different
    representation than the raw Python string it was compared against, and
    ``value in text`` was **permanently false** — the ``env_value_present``
    check could not fire at all. Measured before the fix: an ASCII password was
    detected; the same password containing ``é``, ``"``, ``\\``, a newline, or
    ``→`` was missed in every case.

    A PostgreSQL password containing a quote, a backslash or a non-ASCII
    character is ordinary, not exotic, so this was the realistic case rather
    than a corner one.

    Scanning the decoded leaves removes the encoding step, so there is no
    representation for an escape to hide in. The serialized ``text`` is still
    scanned as well, so this strictly widens detection and can never narrow it.
    ``text`` is NOT, however, general coverage for a value split across
    structure: it catches such a value only when the value itself happens to
    span the JSON separator. See residual 4.

    ``leaves`` IS REQUIRED, WITH NO DEFAULT, ON PURPOSE. A default of ``()``
    would keep every existing call compiling while silently restoring exactly
    the behaviour above, and a last line of defence that a caller can disable by
    omission is not one. Callers pass :func:`string_leaves` of the payload they
    are about to serialize.

    RESIDUALS, stated so the claim is not read as stronger than it is:

    1. Values shorter than 4 characters are not compared, because they collide
       with legitimate counts and labels.
    2. A value some transformation RESHAPED (truncated, case-folded) is not
       caught by a substring scan. UNICODE NORMAL FORM belongs here too, and the
       word "reshaped" understated it: an NFC/NFD divergence needs NO
       transformation by ISAAC at all — the environment variable can simply be
       stored in one normal form while the value that reached the payload
       carries the other, and the two are then different strings. Measured, in
       both directions: env NFC + payload NFD and env NFD + payload NFC each
       return ``[]``, while the same value in matching forms is detected. No
       normalization is performed here, deliberately — normalizing before
       comparison would be a second representation-guessing step of the kind
       that produced this defect in the first place.
    3. Only string leaves and the serialized text are compared. A secret that
       reached the payload as a NUMBER would be caught only via ``text``.
    4. A value SPLIT across two adjacent leaves is not detected. Measured:
       ``PGPASSWORD="supersecretpassword"`` against
       ``{"a": ["supersecret", "password"]}`` is MISSED by both haystacks —
       ``text`` catches a split value only when the value itself spans the
       JSON separator (``", "``). This residual was omitted from the first
       version of this list, which is precisely how a known-limitations list
       becomes a false assurance.
    5. ``_ULID_RE`` is ``\\b[0-9A-Z]{26}\\b``, so ``raw_ulid_present`` misses any
       ULID ADJACENT TO A WORD CHARACTER — and ``_`` is a word character.
       Measured: a bare ULID and ``rec-<ULID>`` are both detected;
       ``id_<ULID>``, ``x<ULID>`` and ``<ULID>z`` are all MISSED. That is a
       realistic shape, since a leaked id would plausibly arrive as a prefixed
       key. This residual is PRE-EXISTING and untouched by this change — the
       leaf scan neither widens nor narrows it.

       WHY IT IS DEFERRED, STATED CORRECTLY THE SECOND TIME. The first version
       of this entry justified deferring the fix by asserting that dropping the
       boundaries "would match any 26-character uppercase run inside a longer
       token, which is the shape of the digests and fingerprints this report
       legitimately carries". **That was false of this report, and a false
       sentence in a limitations list is the exact failure residual 4 above
       exists to warn about — committed here one paragraph later.** Measured
       against a realistic projected response: the only digest served is
       ``schema_fingerprint``, a **lowercase** sha256 hex that ``[0-9A-Z]{26}``
       cannot match; ``record_id`` digests are truncated, lowercase, and not
       projected at all; a loose ``[0-9A-Z]{26}`` matches **nothing** in the
       response, whose longest uppercase run is 11 characters
       (``CONCURRENCY``); and removing both ``\\b`` breaks **no** test.

       So the honest reason is PROSPECTIVE, not present: the boundaries are not
       protecting against a collision that exists today, and widening them
       would cost nothing today. It stays out of this PR because this PR is
       about the escaping defect, because ``allow_raw_ids=False`` sits behind a
       projection that already excludes record ids (so it is a backstop, not the
       boundary), and because a future report that legitimately carries an
       uppercase token would silently start refusing. It is a small, separable
       slice — not a trade-off that has already been made.

       Note the shared root with the audit-tooling defect recorded elsewhere in
       this project: a ``\\b``-anchored pattern returning zero is not evidence
       of absence.
    """
    issues: list[str] = []
    haystacks: tuple[str, ...] = (text, *leaves)
    if not allow_raw_ids and any(_ULID_RE.search(hay) for hay in haystacks):
        issues.append("raw_ulid_present")
    for name in _FORBIDDEN_ENV_VALUES:
        value = (env.get(name) or "").strip()
        # Very short values would false-positive against counts and labels.
        if len(value) >= 4 and any(value in hay for hay in haystacks):
            issues.append(f"env_value_present:{name}")
    for code, pattern in _SECRET_SHAPES:
        if any(pattern.search(hay) for hay in haystacks):
            issues.append(f"secret_shape:{code}")
    return sorted(set(issues))

# --- SQL (all read-only; module-level so tests can drive a fake cursor) ------

Q_CURRENT_DATABASE = "SELECT current_database()"
Q_CURRENT_USER = "SELECT current_user, session_user"
Q_SERVER_VERSION = (
    "SELECT current_setting('server_version'), current_setting('server_version_num')"
)
Q_TRANSACTION_READ_ONLY = "SELECT current_setting('transaction_read_only')"
Q_IS_SUPERUSER = "SELECT current_setting('is_superuser')"
Q_SSL = (
    "SELECT s.ssl, s.version, s.cipher, s.bits "
    "FROM pg_stat_ssl s WHERE s.pid = pg_backend_pid()"
)
Q_RECORDS_TABLE_PRESENT = (
    "SELECT count(*) FROM information_schema.tables "
    "WHERE table_schema = 'public' AND table_name = 'records'"
)
Q_RECORDS_TABLE_OWNER = (
    "SELECT tableowner FROM pg_tables "
    "WHERE schemaname = 'public' AND tablename = 'records'"
)
Q_TABLE_INVENTORY = (
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
    "ORDER BY table_name"
)
Q_RECORD_COUNT = "SELECT count(*) FROM records"
Q_RECORDS_BY_TYPE = (
    "SELECT record_type, count(*) FROM records GROUP BY 1 ORDER BY 2 DESC, 1"
)
Q_RECORDS_BY_DOMAIN = (
    "SELECT record_domain, count(*) FROM records GROUP BY 1 ORDER BY 2 DESC, 1"
)
#: ``data`` is the full record JSON. It is needed in memory to validate and to
#: derive structural paths; it NEVER reaches the report. Ordered for
#: determinism, bounded by a parameterised LIMIT.
Q_RECORDS_PAGE = (
    "SELECT record_id, record_type, record_domain, data FROM records "
    "ORDER BY record_id LIMIT %s"
)
Q_VOCAB_TABLE_PRESENT = (
    "SELECT count(*) FROM information_schema.tables "
    "WHERE table_schema = 'public' AND table_name = 'vocabulary_cache'"
)
Q_VOCAB_COLUMNS = (
    "SELECT column_name, data_type FROM information_schema.columns "
    "WHERE table_schema = 'public' AND table_name = 'vocabulary_cache' "
    "ORDER BY ordinal_position"
)
Q_VOCAB_COUNT = "SELECT count(*) FROM vocabulary_cache"
VOCAB_GROUP_TEMPLATE = (
    "SELECT {column}, count(*) FROM vocabulary_cache GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 200"
)
MAX_VOCAB_GROUPS = 200


def vocab_group_sql(column: str) -> str:
    """Build (and guard) the one query that interpolates a catalog identifier."""
    return assert_read_only_sql(VOCAB_GROUP_TEMPLATE.format(column=_quote_ident(column)))


# --- cursor helpers ----------------------------------------------------------


def run_read_only(cursor: Any, sql: str, params: Optional[Sequence[Any]] = None) -> list[tuple]:
    """Execute a guarded read-only statement and return all rows as tuples.

    Logging discipline (matches the ``outcome=`` style of
    ``apps/api/isaac_api/routes.py``): operation name and row count only. No
    SQL text with values, no parameter values, no payloads.
    """
    assert_read_only_sql(sql)
    if params is None:
        cursor.execute(sql)
    else:
        cursor.execute(sql, tuple(params))
    rows = list(cursor.fetchall() or [])
    _log.debug("db_recon outcome=query_ok rows=%d", len(rows))
    return rows


def _scalar(cursor: Any, sql: str, params: Optional[Sequence[Any]] = None) -> Any:
    rows = run_read_only(cursor, sql, params)
    if not rows:
        return None
    row = rows[0]
    return row[0] if isinstance(row, (list, tuple)) else row


# --- gates -------------------------------------------------------------------


def check_env_gates(
    env: Mapping[str, str], *, require_opt_in: bool = True
) -> dict[str, str]:
    """Gates 7 and 1 — the two that need no socket, so they run first.

    ``require_opt_in`` controls gate 7 ONLY. Gate 1 (``PGDATABASE`` is exactly
    ``metadata_assistant``) always applies.

    * ``True`` (the default, used by ``scripts/db_recon.py``): the operator must
      set ``ISAAC_RUN_SLAC_DB_RECON=1``, so a CLI run can never happen by
      accident.
    * ``False`` (used by ``GET /api/runtime/database/recon``): the deployed pod
      is never given that variable, and per
      ``docs/postgres-test-db-guide.md`` the pod's documented feature switch is
      ``PGHOST``. Demanding a second variable nobody sets would make the
      endpoint permanently dead rather than safe.
    """
    if require_opt_in and (env.get(OPT_IN_ENV) or "").strip() != OPT_IN_VALUE:
        raise ReconRefusal(
            "opt_in",
            f"{OPT_IN_ENV} must be exactly {OPT_IN_VALUE!r}; this entry point never "
            "runs by accident",
        )
    pgdatabase = (env.get("PGDATABASE") or "").strip()
    if pgdatabase != EXPECTED_DATABASE:
        # The observed value is a database name the operator supplied, not data;
        # naming it is what makes the refusal actionable.
        raise ReconRefusal(
            "pgdatabase_env",
            f"PGDATABASE must be exactly {EXPECTED_DATABASE!r} (got {pgdatabase!r})",
        )
    gates = {"pgdatabase_env": "pass"}
    if require_opt_in:
        gates["opt_in"] = "pass"
    return gates


def check_current_database(cursor: Any) -> str:
    """Gate 2 — guards against a PGDATABASE lie or a redirected connection."""
    actual = (_scalar(cursor, Q_CURRENT_DATABASE) or "")
    actual = str(actual).strip()
    if actual != EXPECTED_DATABASE:
        raise ReconRefusal(
            "current_database",
            f"connected database must be {EXPECTED_DATABASE!r} (got {actual!r})",
        )
    return actual


def check_current_user(cursor: Any) -> tuple[str, str]:
    """Gate 3 — the least-privilege role, and no ``SET ROLE`` in effect."""
    rows = run_read_only(cursor, Q_CURRENT_USER)
    if not rows:
        raise ReconRefusal("current_user", "server returned no current_user row")
    current = str(rows[0][0] or "").strip()
    session = str(rows[0][1] or "").strip() if len(rows[0]) > 1 else current
    if current != EXPECTED_ROLE:
        raise ReconRefusal(
            "current_user", f"current_user must be {EXPECTED_ROLE!r} (got {current!r})"
        )
    if session != EXPECTED_ROLE:
        raise ReconRefusal(
            "current_user",
            f"session_user must be {EXPECTED_ROLE!r} (got {session!r}); a role switch is in effect",
        )
    return current, session


def check_tls(cursor: Any) -> dict[str, Any]:
    """Gate 4 — TLS must be CONFIRMED, not merely requested.

    Absence of proof is not proof of absence: no row, a null ``ssl``, or a
    false ``ssl`` all refuse. Certificate material is never read or emitted;
    only the boolean, protocol version, cipher name and bit count.
    """
    rows = run_read_only(cursor, Q_SSL)
    if not rows:
        raise ReconRefusal(
            "tls", "pg_stat_ssl returned no row for this backend; TLS cannot be confirmed"
        )
    row = rows[0]
    ssl_on = row[0]
    if ssl_on is not True and str(ssl_on).lower() not in {"true", "t", "on", "1"}:
        raise ReconRefusal("tls", "pg_stat_ssl reports this connection is not encrypted")
    version = str(row[1]).strip() if len(row) > 1 and row[1] is not None else None
    cipher = str(row[2]).strip() if len(row) > 2 and row[2] is not None else None
    bits = int(row[3]) if len(row) > 3 and row[3] is not None else None
    return {"confirmed": True, "version": version, "cipher": cipher, "bits": bits}


def check_records_table(cursor: Any) -> None:
    """Gate 5 — ``information_schema.tables`` only shows tables we may read."""
    present = int(_scalar(cursor, Q_RECORDS_TABLE_PRESENT) or 0)
    if present < 1:
        raise ReconRefusal(
            "records_table", "no 'records' table is visible to this role in schema 'public'"
        )


def check_transaction_read_only(cursor: Any) -> str:
    """Verify server-side that the transaction really is read-only."""
    setting = str(_scalar(cursor, Q_TRANSACTION_READ_ONLY) or "").strip().lower()
    if setting != "on":
        raise ReconRefusal(
            "transaction_read_only",
            f"server reports transaction_read_only={setting!r}; refusing to proceed "
            "without a confirmed read-only transaction",
        )
    return setting


def check_not_production_shaped(cursor: Any, record_count: int) -> dict[str, Any]:
    """Gate 6 — positive identification of the least-privilege test role.

    Three checks, all cheap and all read-only:

    1. ``records`` row count within :data:`MAX_PLAUSIBLE_RECORD_ROWS`.
    2. ``records`` is owned by ``metadata_assistant`` — the guide says this
       role owns the database and its ``public`` schema, so a table owned by
       anyone else means we are not looking at the DB we think we are.
    3. ``is_superuser`` is off — the guide specifies NOSUPERUSER, so a
       superuser session is prima facie not this role's documented environment.

    HONEST LIMITATION (see :data:`MAX_PLAUSIBLE_RECORD_ROWS`): checks 2 and 3
    are genuine positive identification of the documented role, but none of the
    three can *prove* the target is not production. A small production database
    owned by a similarly named non-superuser role would pass all three. The
    actual isolation guarantee is external to this module: per the guide the
    ``metadata_assistant`` role has no grant into any other database on the
    cluster, so it cannot reach the production records DB at all. Treat this
    gate as a tripwire, not an assurance.
    """
    if record_count > MAX_PLAUSIBLE_RECORD_ROWS:
        raise ReconRefusal(
            "not_production_shaped",
            f"records row count {record_count} exceeds the safety threshold "
            f"{MAX_PLAUSIBLE_RECORD_ROWS} (documented test seed is "
            f"{DOCUMENTED_SEED_ROWS}); refusing in case this is not the test database",
        )
    owner = str(_scalar(cursor, Q_RECORDS_TABLE_OWNER) or "").strip()
    if owner != EXPECTED_ROLE:
        raise ReconRefusal(
            "not_production_shaped",
            f"'records' is owned by {owner!r}, not {EXPECTED_ROLE!r}; "
            "this is not the documented test database layout",
        )
    # FAIL CLOSED, matching check_tls above and this module's stated posture
    # ("absence of proof is treated as failure"). An empty string is what
    # ``_scalar`` yields for a missing row or a NULL, so accepting "" here made
    # the gate fail OPEN: no row, NULL and "" all passed, and the report then
    # asserted is_superuser=false as though it had been observed.
    is_superuser = str(_scalar(cursor, Q_IS_SUPERUSER) or "").strip().lower()
    if is_superuser not in {"off", "false", "f", "0"}:
        raise ReconRefusal(
            "not_production_shaped",
            "could not confirm the session is non-superuser; the documented test "
            "role is NOSUPERUSER and absence of proof is treated as failure",
        )
    return {
        "record_count_within_threshold": True,
        "threshold": MAX_PLAUSIBLE_RECORD_ROWS,
        "documented_seed_rows": DOCUMENTED_SEED_ROWS,
        "records_table_owner_is_expected_role": True,
        # The value actually OBSERVED from pg_catalog, not a constant. It was
        # hardcoded False, which reported an observation that — because the gate
        # above used to accept "" — may never have been made.
        "is_superuser_observed": is_superuser,
        "is_superuser": False,
        "heuristic_is_a_backstop_not_a_guarantee": True,
    }


# --- validation --------------------------------------------------------------


def collapse_json_pointer(pointer: str) -> str:
    """Collapse an RFC-6901 JSON pointer for aggregation (indices -> ``[]``)."""
    text = str(pointer or "")
    if text in {"", "/"}:
        return "$"
    segments = [s for s in text.lstrip("/").split("/") if s != ""]
    if not segments:
        return "$"
    return _collapse_segments(
        [s.replace("~1", "/").replace("~0", "~") for s in segments]
    )


def load_diagnostics_enricher() -> tuple[Optional[Callable[..., Any]], str]:
    """Try to obtain ``isaac_records.diagnostics.diagnose``.

    Guarded broadly, not just against :class:`ImportError`: this module may be
    absent, or present-but-incomplete in a working tree where another change is
    in flight, in which case importing it could raise almost anything. A failed
    import is never fatal — the module falls back to ``validate_official``.
    """
    try:
        from isaac_records.diagnostics import diagnose  # type: ignore
    except ImportError as exc:
        return None, f"unavailable (ImportError: {type(exc).__name__})"
    except Exception as exc:  # noqa: BLE001 - see docstring
        return None, f"unavailable ({type(exc).__name__})"
    if not callable(diagnose):
        return None, "unavailable (diagnose is not callable)"
    return diagnose, "isaac_records.diagnostics.diagnose"


def _official_findings(record: Mapping[str, Any], root: Path) -> tuple[bool, list[dict[str, Any]]]:
    """Authoritative pass/fail plus a taxonomy derived from official errors."""
    from isaac_records.official import validate_official

    report = validate_official(dict(record), Path(root))
    findings: list[dict[str, Any]] = []
    for err in report.errors:
        # err.message is deliberately NOT stored: it embeds the offending value.
        findings.append(
            {
                "family": rule_family(err.message),
                "instance_path": collapse_instance_path(err.path),
                "schema_path": None,
                "conditional": None,
                "kind": None,
                "unexpected_properties": unexpected_property_names(err.message),
            }
        )
    return report.ok, findings


def _diagnostics_findings(
    diagnose: Callable[..., Any], record: Mapping[str, Any], root: Path
) -> Optional[list[dict[str, Any]]]:
    """Richer taxonomy from the frozen diagnostics API, or None if unusable."""
    try:
        report = diagnose(dict(record), Path(root))
        items = list(getattr(report, "diagnostics", []) or [])
    except Exception:  # noqa: BLE001 - enrichment must never break the run
        return None
    findings: list[dict[str, Any]] = []
    for item in items:
        findings.append(
            {
                "family": str(getattr(item, "rule_family", None) or "other"),
                "instance_path": collapse_json_pointer(getattr(item, "pointer", "") or ""),
                "schema_path": collapse_schema_pointer(getattr(item, "schema_pointer", "") or "")
                if getattr(item, "schema_pointer", None)
                else None,
                "conditional": getattr(item, "conditional", None),
                "kind": str(getattr(item, "kind", None)) if getattr(item, "kind", None) else None,
                "unexpected_properties": [],
            }
        )
    return findings


def _safe_label(value: Any) -> Any:
    """Coerce an enrichment label to something provably non-sensitive.

    Booleans/None pass through; strings must be identifier-shaped (rule-family
    and conditional labels are code-level constants, so they are) or they are
    masked. This stops an unexpected free-text label from becoming a leak.
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    text = str(value)
    return text if _IDENTIFIER_RE.match(text) else MASK_WITHHELD


def aggregate_validation(
    per_record: Sequence[tuple[bool, list[dict[str, Any]]]], *, engine: str, engine_detail: str
) -> dict[str, Any]:
    """Roll per-record findings into counts only. No record is identifiable."""
    passed = sum(1 for ok, _ in per_record if ok)
    failed = len(per_record) - passed

    family_records: dict[str, int] = {}
    family_errors: dict[str, int] = {}
    instance_paths: dict[tuple[str, str], int] = {}
    schema_paths: dict[str, int] = {}
    conditionals: dict[str, int] = {}
    unexpected: dict[str, int] = {}
    unexpected_parents: dict[str, int] = {}

    for _ok, findings in per_record:
        seen_families: set[str] = set()
        for finding in findings:
            family = str(_safe_label(finding.get("family")) or "other")
            family_errors[family] = family_errors.get(family, 0) + 1
            seen_families.add(family)
            path = str(finding.get("instance_path") or "$")
            key = (path, family)
            instance_paths[key] = instance_paths.get(key, 0) + 1
            schema_path = finding.get("schema_path")
            if schema_path:
                schema_paths[str(schema_path)] = schema_paths.get(str(schema_path), 0) + 1
            conditional = finding.get("conditional")
            if conditional is not None and conditional is not False:
                # A conditional may be a named rule ("evidence_requires_descriptors")
                # or a bare boolean flag meaning "this error came from an if/then
                # branch". Booleans get a stable named bucket rather than "True".
                if conditional is True:
                    label = "unnamed_conditional"
                else:
                    safe = _safe_label(conditional)
                    label = str(safe) if isinstance(safe, str) else MASK_WITHHELD
                conditionals[label] = conditionals.get(label, 0) + 1
            for name in finding.get("unexpected_properties") or []:
                unexpected[name] = unexpected.get(name, 0) + 1
                if family == "additional_properties":
                    unexpected_parents[path] = unexpected_parents.get(path, 0) + 1
        for family in seen_families:
            family_records[family] = family_records.get(family, 0) + 1

    # Is the per-key drift detail below an OBSERVATION, or was it never derived?
    # It is built from the offending KEY NAMES, and only the official engine
    # supplies those: it parses them out of the validator message. The
    # diagnostics engine reports the failure but not the names, so
    # ``_diagnostics_findings`` emits an empty list for every finding and each
    # counter below stays 0 — a zero that means "not computed", not "none
    # found". This is derived from what was actually observed rather than from
    # the engine label, because a run can mix the two (enrichment is attempted
    # per record and falls back on failure).
    additional_property_errors = sum(
        count for family, count in family_errors.items() if family in ADDITIONAL_PROPERTIES_FAMILIES
    )
    names_computed = not (additional_property_errors > 0 and not unexpected)

    return {
        "engine": engine,
        "engine_detail": engine_detail,
        "authority_note": (
            "pass/fail is always decided by isaac_records.official.validate_official "
            "against schema/isaac_record_v1.json; the diagnostics module, when "
            "available, only enriches the failure taxonomy"
        ),
        "records_validated": len(per_record),
        "passed": passed,
        "failed": failed,
        "all_records_valid": failed == 0 and len(per_record) > 0,
        "failure_rule_families": [
            {
                "family": family,
                "records_affected": family_records.get(family, 0),
                "error_count": family_errors[family],
            }
            for family in sorted(family_errors, key=lambda f: (-family_errors[f], f))
        ],
        "failing_instance_paths": [
            {"path": path, "family": family, "error_count": count}
            for (path, family), count in sorted(
                instance_paths.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1])
            )
        ],
        "failing_schema_paths": [
            {"schema_path": path, "error_count": schema_paths[path]}
            for path in sorted(schema_paths, key=lambda p: (-schema_paths[p], p))
        ],
        "conditional_rules_triggered": [
            {"conditional": label, "error_count": conditionals[label]}
            for label in sorted(conditionals, key=lambda c: (-conditionals[c], c))
        ],
        "unexpected_property_names": [
            {"name": name, "occurrences": unexpected[name]}
            for name in sorted(unexpected, key=lambda n: (-unexpected[n], n))
        ],
        # The anonymous schema-drift signal. An "unexpected" property is by
        # definition not declared in the vendored schema, so its NAME may be a
        # scientific value used as a key and is never emitted (review C1).
        # Count plus parent path is equally actionable and names nothing.
        #
        # `names_computed` is false when this run's engine reported
        # additionalProperties failures but supplied no key names — then the
        # counters here are NOT an observation and must not be read as one. The
        # failures themselves are still reported, under this engine's own family
        # label, in `failure_rule_families` and `failing_instance_paths`.
        "unexpected_properties": {
            "names_computed": names_computed,
            "not_computed_reason": (
                None
                if names_computed
                else (
                    "the active validation engine reports additionalProperties failures "
                    "without the offending key names; the counts below are not computed, "
                    "not zero-by-observation — see failure_rule_families and "
                    "failing_instance_paths for the failures themselves"
                )
            ),
            "total_occurrences": sum(unexpected.values()),
            "undeclared_name_count": sum(
                count
                for name, count in unexpected.items()
                if name in {MASK_UNDECLARED_KEY, MASK_NON_IDENTIFIER}
            ),
            "by_parent_path": [
                {"parent_path": path, "occurrences": unexpected_parents[path]}
                for path in sorted(
                    unexpected_parents, key=lambda p: (-unexpected_parents[p], p)
                )
            ],
        },
    }


def aggregate_structure(
    signatures: Sequence[tuple[list[str], dict[str, Any]]]
) -> dict[str, Any]:
    """Distinct path-set signatures with counts, plus per-path presence."""
    by_signature: dict[str, dict[str, Any]] = {}
    presence: dict[str, int] = {}
    masked = 0
    depth_truncated = False
    width_truncated = False
    for paths, stats in signatures:
        sig = signature_id(paths)
        entry = by_signature.setdefault(
            sig, {"signature": sig, "count": 0, "path_count": len(paths), "paths": list(paths)}
        )
        entry["count"] += 1
        for path in paths:
            presence[path] = presence.get(path, 0) + 1
        masked += int(stats.get("masked_key_segments", 0))
        depth_truncated = depth_truncated or bool(stats.get("depth_truncated"))
        width_truncated = width_truncated or bool(stats.get("width_truncated"))
    return {
        "records_analyzed": len(signatures),
        "distinct_signature_count": len(by_signature),
        "distinct_signatures": sorted(
            by_signature.values(), key=lambda e: (-e["count"], e["signature"])
        ),
        "path_presence": [
            {"path": path, "records_with_path": presence[path]}
            for path in sorted(presence, key=lambda p: (-presence[p], p))
        ],
        "distinct_path_count": len(presence),
        "masked_key_segments": masked,
        "depth_truncated": depth_truncated,
        "width_truncated": width_truncated,
        "algorithm": (
            "sorted set of JSON paths with all values stripped; array indices "
            "collapsed to '[]'; object keys masked by THREE rules, in order: a "
            f"key inside an additionalProperties-open location -> '{MASK_OPEN_MAP_KEY}'; "
            f"a non-identifier-shaped key -> '{MASK_NON_IDENTIFIER}'; a key not "
            f"declared anywhere in the vendored schema -> '{MASK_UNDECLARED_KEY}'. "
            "masked_key_segments counts all three. "
            "signature = sha256(newline-joined paths)[:16]"
        ),
    }


def collect_vocabulary_cache(cursor: Any) -> dict[str, Any]:
    """Row count, column inventory, and guarded category groupings."""
    if int(_scalar(cursor, Q_VOCAB_TABLE_PRESENT) or 0) < 1:
        return {"present": False, "row_count": None, "columns": [], "grouped": []}
    columns = [
        {"name": safe_sql_identifier(row[0]), "data_type": safe_sql_identifier(str(row[1]).replace(" ", "_"))}
        for row in run_read_only(cursor, Q_VOCAB_COLUMNS)
    ]
    row_count = int(_scalar(cursor, Q_VOCAB_COUNT) or 0)
    grouped: list[dict[str, Any]] = []
    for column in columns:
        name = column["name"]
        if name not in VOCAB_CATEGORY_COLUMN_ALLOWLIST:
            continue
        rows = run_read_only(cursor, vocab_group_sql(name))
        # Values are emitted only when EVERY value in the column is an
        # identifier-shaped lowercase slug, i.e. a controlled-vocabulary
        # category label rather than free text. One suspicious value withholds
        # the whole column: counts survive, strings do not.
        values = [(None if r[0] is None else str(r[0]).strip()) for r in rows]
        emit = all(v is None or bool(_LOWER_SLUG_RE.match(v)) for v in values)
        grouped.append(
            {
                "column": name,
                "values_emitted": emit,
                "distinct_groups": len(rows),
                "truncated": len(rows) >= MAX_VOCAB_GROUPS,
                "groups": [
                    {
                        "value": (
                            MASK_NULL_BUCKET
                            if values[i] is None
                            else (values[i] if emit else MASK_WITHHELD)
                        ),
                        "count": int(rows[i][1]),
                    }
                    for i in range(len(rows))
                ]
                if emit
                else [],
                "group_counts_only": None
                if emit
                else sorted((int(r[1]) for r in rows), reverse=True),
            }
        )
    return {
        "present": True,
        "row_count": row_count,
        "columns": columns,
        "column_count": len(columns),
        "grouped": grouped,
        "value_policy": (
            "grouped values are emitted only for allow-listed category columns "
            "whose every value is a lowercase controlled-vocabulary slug; "
            "otherwise counts only. No term values are ever emitted."
        ),
    }


HONEST_NOTES = (
    "READ-ONLY: only SELECT and read-only catalog introspection were issued; "
    "the transaction was set AND verified read-only server-side.",
    "The record and vocabulary_cache row counts are compared before and after "
    "the run as a CONCURRENCY CHECK, not as a mutation proof: a row-count "
    "equality cannot detect an UPDATE and cannot distinguish this run's writes "
    "from a concurrent writer's. No write is possible because the transaction "
    "is verified read-only server-side and every statement passes a "
    "SELECT-only allowlist before it is issued.",
    "This report contains aggregate counts and value-stripped RECORD structure. "
    "It is not literally 'counts only': three classes of verbatim database "
    "string are emitted by design — server_version, TLS version/cipher, and "
    "allow-listed vocabulary-CATEGORY values that are lowercase slugs. Those "
    "last are emitted by SHAPE, and nothing proves a lowercase slug is a "
    "controlled-vocabulary term rather than data (see vocabulary_cache."
    "value_policy). No record field value, title, identity or free-text field "
    "is emitted. "
    "Record values are never read into a path, and every object KEY is checked "
    "against the set of property names the vendored public schema declares: a "
    "key survives verbatim only if the schema already publishes it, otherwise "
    "it is masked. Keys inside the schema's additionalProperties-open maps "
    "(sample.composition, system.configuration, ...) are always masked, because "
    "the writer there may legitimately key the map by a scientific value. "
    "A leak scan over the serialised output must also pass before anything is "
    "written.",
    "LIMIT OF THAT CLAIM, stated plainly: the key allowlist is the vendored "
    "schema, so if a real record used a declared schema property NAME as a map "
    "key in an open location, the open-map branch masks it FIRST, so it is not "
    "emitted; were it emitted at a non-open location it would be a public "
    "schema name, not a value. The leak scan detects ULIDs, environment values "
    "and credential shapes; it does not and cannot recognise arbitrary science, "
    "so the allowlist, not the scan, is what keeps values out.",
    "The record 'data' JSONB is read into process memory (validation requires "
    "it) but is never serialised into this report.",
    "The production-detection gate is a BACKSTOP, not a guarantee: a small "
    "production database owned by a similarly named non-superuser role would "
    "pass it. The real isolation guarantee is external — per "
    "docs/postgres-test-db-guide.md the metadata_assistant role has no grant "
    "into any other database on the cluster, so it cannot connect to the "
    "production records database at all.",
    "The rows in this database are NOT disposable test data. An earlier "
    "revision of this module repeated the guide's since-deleted 'write, "
    "mutate, and drop freely' framing; the guide now states that the seeded "
    "rows are real production-derived records and that hosted display of "
    "per-record content is CLOSED BY DEFAULT pending an explicit visibility "
    "decision. This module emits aggregates only, which the guide authorises "
    "now; it must not become a record-display path.",
    "The Postgres major version is REPORTED, never gated: the guide documents "
    f"Postgres {EXPECTED_SERVER_MAJOR_VERSION}, and the report carries "
    "expected_major_version_match, but a mismatch is information rather than "
    "a refusal.",
    "TLS is confirmed server-side via pg_stat_ssl. Note that sslmode 'require' "
    "encrypts but does not verify the server certificate; set PGSSLMODE="
    "verify-full with a CA bundle for authenticated TLS.",
    "record_id values are emitted only as salted truncated digests. Whether raw "
    "ULIDs are safe to publish is UNDECIDED by the project owner; raw emission "
    "requires the caller to pass emit_raw_record_ids, which the CLI exposes as "
    f"--emit-raw-record-ids plus {RAW_ID_ENV}=1. The HTTP endpoint never sets "
    "it, and does not project the digest list either — only its count.",
    "No wall-clock timestamp is recorded by this function, and no host metadata "
    "leaks. Output is byte-identical across runs only when the salt is PINNED: "
    "the CLI's default --id-salt is random per run, so record_id digests differ "
    "on every invocation by design. Determinism of everything else is "
    "unaffected. The HTTP endpoint DOES stamp generated_at, deliberately: a "
    "served report needs to say when it was made.",
)


def run_recon(
    connection: Any,
    *,
    env: Mapping[str, str],
    salt: str,
    root: Path = REPO_ROOT,
    max_records: int = DEFAULT_MAX_RECORDS,
    emit_raw_record_ids: bool = False,
    apply_session_read_only: bool = True,
    require_opt_in: bool = True,
) -> dict[str, Any]:
    """Run every gate then every aggregate query against an open connection.

    ``connection`` only needs ``cursor()`` returning an object with
    ``execute``/``fetchall``/``close`` — which is why the whole flow is testable
    with a fake and no database.

    ``require_opt_in`` is forwarded to :func:`check_env_gates`; see that
    function for why the HTTP endpoint passes ``False`` and the CLI ``True``.

    ``root`` must be the vendored :data:`REPO_ROOT`; see the gate below.
    """
    # Fail closed on a divergent schema root. ``root`` is what per-record
    # validation is anchored to, but every redaction call site in this module
    # loads its vocabulary from the module-level REPO_ROOT. If the two could
    # differ, one schema would decide which keys are emittable while a different
    # one decided validity, and the report would be internally inconsistent
    # while still presenting a single `schema_authority` fingerprint. No caller
    # passes a non-default root today, so rather than plumb ``root`` through the
    # five masking helpers for a caller that does not exist, the divergence is
    # made impossible here — before this function touches the connection at all
    # (note the HTTP route opens the socket in connect_psycopg2 before calling
    # us, so this is "before any use", not "before any connection exists").
    if Path(root).resolve() != Path(REPO_ROOT).resolve():
        raise UsageError(
            "schema_root",
            "validation root must be the vendored REPO_ROOT; the redaction "
            "vocabulary is anchored there",
        )

    gates = dict(check_env_gates(env, require_opt_in=require_opt_in))

    # Defence in depth #1: ask the driver for a read-only session, if it can.
    session_readonly_applied = False
    setter = getattr(connection, "set_session", None)
    if apply_session_read_only and callable(setter):
        try:
            setter(readonly=True)
            session_readonly_applied = True
        except Exception:  # noqa: BLE001 - verified server-side below anyway
            session_readonly_applied = False

    cursor = connection.cursor()
    try:
        # Defence in depth #2: explicit read-only session statements from the
        # frozen literal allowlist. Any failure is non-fatal because the state
        # is then VERIFIED below and the run refuses if it is not read-only.
        if apply_session_read_only:
            for statement in SESSION_READ_ONLY_STATEMENTS:
                try:
                    cursor.execute(_assert_session_statement(statement))
                except UnsafeStatement:
                    raise
                except Exception:  # noqa: BLE001
                    continue

        # Defence in depth #3: verify, do not assume.
        transaction_read_only = check_transaction_read_only(cursor)
        gates["transaction_read_only"] = "pass"

        gates["current_database"] = "pass" if check_current_database(cursor) else "fail"
        current_user, session_user = check_current_user(cursor)
        gates["current_user"] = "pass"
        tls = check_tls(cursor)
        gates["tls"] = "pass"
        check_records_table(cursor)
        gates["records_table"] = "pass"

        version_rows = run_read_only(cursor, Q_SERVER_VERSION)
        server_version = str(version_rows[0][0]).strip() if version_rows else None
        server_version_num = (
            int(version_rows[0][1]) if version_rows and version_rows[0][1] is not None else None
        )
        # REPORTED, NEVER GATED (see EXPECTED_SERVER_MAJOR_VERSION).
        server_version_major = server_major_version(server_version, server_version_num)

        records_before = int(_scalar(cursor, Q_RECORD_COUNT) or 0)
        production_check = check_not_production_shaped(cursor, records_before)
        gates["not_production_shaped"] = "pass"

        tables = [safe_sql_identifier(row[0]) for row in run_read_only(cursor, Q_TABLE_INVENTORY)]

        by_type = counted_buckets(
            (safe_enum_value(row[0], SCHEMA_ENUM_RECORD_TYPE), int(row[1]))
            for row in run_read_only(cursor, Q_RECORDS_BY_TYPE)
        )
        by_domain = counted_buckets(
            (safe_enum_value(row[0], SCHEMA_ENUM_RECORD_DOMAIN), int(row[1]))
            for row in run_read_only(cursor, Q_RECORDS_BY_DOMAIN)
        )

        # --- the one query that touches record payloads ----------------------
        page = run_read_only(cursor, Q_RECORDS_PAGE, (int(max_records),))

        diagnose, diagnostics_detail = load_diagnostics_enricher()
        engine = "official"
        engine_detail = (
            "isaac_records.official.validate_official "
            "(schema/isaac_record_v1.json, official v1.05)"
        )

        digests: list[str] = []
        raw_ids: list[str] = []
        versions: list[tuple[str, int]] = []
        structures: list[tuple[list[str], dict[str, Any]]] = []
        per_record: list[tuple[bool, list[dict[str, Any]]]] = []
        unreadable_payloads = 0
        #: Only ever used to compute COUNTS. No id and no link target is
        #: emitted; both sets are discarded when this function returns.
        scanned_ids: set[str] = set()
        link_targets_seen: list[str] = []
        records_with_links = 0

        for row in page:
            # CHAR(26) is blank-padded by Postgres: strip on every read
            # (docs/postgres-test-db-guide.md "Gotchas to code around").
            record_id = str(row[0] or "").strip()
            payload = row[3]
            if isinstance(payload, (str, bytes, bytearray)):
                try:
                    payload = json.loads(payload)
                except (ValueError, TypeError):
                    payload = None
            if not isinstance(payload, dict):
                unreadable_payloads += 1
                payload = {}

            digests.append(hash_record_id(record_id, salt))
            if record_id:
                scanned_ids.add(record_id)
            targets = link_targets(payload)
            if targets:
                records_with_links += 1
            link_targets_seen.extend(targets)
            if emit_raw_record_ids:
                raw_ids.append(record_id)
            versions.append((safe_version_value(payload.get("isaac_record_version")), 1))
            structures.append(structural_paths(payload))

            ok, findings = _official_findings(payload, root)
            if diagnose is not None:
                enriched = _diagnostics_findings(diagnose, payload, root)
                if enriched is not None:
                    findings = enriched
                    engine = "diagnostics"
                    engine_detail = diagnostics_detail
            per_record.append((ok, findings))

        # --- link resolvability, as COUNTS only ------------------------------
        # The guide records that some sampled records link to record_ids outside
        # the sample. "Dangling" is only meaningful relative to the set actually
        # scanned, so it is reported ONLY when the whole table was scanned;
        # otherwise it would be an approximation dressed as a fact.
        whole_table_scanned = len(page) == records_before and len(page) < int(max_records)
        dangling = sum(1 for t in link_targets_seen if t not in scanned_ids)
        links_summary = {
            "total_link_count": len(link_targets_seen),
            "records_with_links": records_with_links,
            "whole_table_scanned": whole_table_scanned,
            # None (not 0) when it cannot be derived without approximating.
            "dangling_link_count": dangling if whole_table_scanned else None,
        }

        vocabulary = collect_vocabulary_cache(cursor)

        # --- concurrency check (gate 9; NOT a mutation proof) -----------------
        # A row-count equality cannot see an UPDATE and cannot distinguish our
        # writes from a concurrent writer's. What makes a write impossible is
        # the server-verified read-only transaction plus the SELECT-only
        # allowlist; this comparison only catches the table shifting under us.
        records_after = int(_scalar(cursor, Q_RECORD_COUNT) or 0)
        vocab_after = (
            int(_scalar(cursor, Q_VOCAB_COUNT) or 0) if vocabulary.get("present") else None
        )
        if records_after != records_before:
            raise MutationDetected(
                f"records row count changed during the run ({records_before} -> {records_after})"
            )
        if vocabulary.get("present") and vocab_after != vocabulary.get("row_count"):
            raise MutationDetected("vocabulary_cache row count changed during the run")
        gates["no_mutation"] = "pass"
    finally:
        closer = getattr(cursor, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:  # noqa: BLE001
                pass

    report: dict[str, Any] = {
        "recon_schema_version": RECON_SCHEMA_VERSION,
        # The shared implementation, not one of its two entry points. The CLI
        # wrapper is no longer where this logic lives.
        "producer": "isaac_api.db_recon.run_recon",
        "mode": "read_only_reconnaissance",
        "generated_at": None,
        "gates": {name: gates[name] for name in sorted(gates)},
        "connection": {
            "database": EXPECTED_DATABASE,
            "current_user": current_user,
            "session_user": session_user,
            "host": MASK_WITHHELD,
            "server_version": server_version,
            "server_version_num": server_version_num,
            "server_version_major": server_version_major,
            "expected_major_version": EXPECTED_SERVER_MAJOR_VERSION,
            # Reported, never gated. ``None`` when the major version could not
            # be parsed — absence of proof is not reported as a match.
            "expected_major_version_match": (
                None
                if server_version_major is None
                else server_version_major == EXPECTED_SERVER_MAJOR_VERSION
            ),
            "transaction_read_only": transaction_read_only,
            "driver_readonly_session_applied": session_readonly_applied,
            "tls": tls,
            # Sourced from the gate's OBSERVED value; the gate refuses unless it
            # positively read a non-superuser answer, so this is now an
            # observation rather than an assumption.
            "is_superuser": False,
            "is_superuser_observed": production_check.get("is_superuser_observed"),
        },
        "tables": {"count": len(tables), "names": sorted(tables)},
        "records": {
            "total": records_before,
            "analyzed": len(page),
            "fetch_limit": int(max_records),
            "truncated_by_limit": len(page) >= int(max_records),
            "unreadable_payloads": unreadable_payloads,
            "by_record_type": by_type,
            "by_record_domain": by_domain,
            "by_isaac_record_version": counted_buckets(versions),
            "record_id_digests": {
                "algorithm": "sha256(salt || 0x00 || record_id) truncated to 16 hex chars",
                "salt_emitted": False,
                "count": len(digests),
                "digests": sorted(digests),
            },
            "raw_record_ids_emitted": bool(emit_raw_record_ids),
            "links": links_summary,
        },
        "structure": aggregate_structure(structures),
        "validation": aggregate_validation(
            per_record, engine=engine, engine_detail=engine_detail
        ),
        "diagnostics_module": {"available": diagnose is not None, "detail": diagnostics_detail},
        "vocabulary_cache": vocabulary,
        "mutation_check": {
            "records_before": records_before,
            "records_after": records_after,
            "vocabulary_cache_before": vocabulary.get("row_count"),
            "vocabulary_cache_after": vocab_after,
            "unchanged": True,
        },
        "production_detection": production_check,
        "notes": list(HONEST_NOTES),
    }
    if emit_raw_record_ids:
        report["records"]["raw_record_ids"] = sorted(raw_ids)
    return report


# --- connection --------------------------------------------------------------


def connect_psycopg2(env: Mapping[str, str]) -> Any:
    """Open a TLS connection using libpq env vars. psycopg2 imported LAZILY.

    ``psycopg2-binary>=2.9`` IS a declared project dependency (the ``api``
    extra in ``pyproject.toml``), authorized by
    ``docs/postgres-test-db-guide.md``. The import is still deferred to call
    time so that importing this module — and running its test suite — never
    depends on the driver being present: the deployed image installs
    ``.[api]`` and has it, a bare developer checkout may not.
    """
    try:
        import psycopg2  # noqa: PLC0415 - intentionally lazy; see docstring
    except ImportError:
        raise MissingDependency(
            "psycopg2 is not importable in this interpreter. It IS a declared "
            "project dependency (the 'api' extra in pyproject.toml, "
            "psycopg2-binary>=2.9), so this environment is simply missing it: "
            "install the api extra (e.g. `pip install -e '.[api]'`). The "
            "deployed image installs '.[api]' and therefore has it."
        )
    missing = [name for name in ("PGHOST", "PGUSER", "PGPASSWORD") if not (env.get(name) or "")]
    if missing:
        raise ConnectionRefused(
            "missing required libpq environment variables: " + ", ".join(sorted(missing))
        )
    try:
        return psycopg2.connect(
            host=env["PGHOST"],
            port=env.get("PGPORT", "5432"),
            dbname=EXPECTED_DATABASE,  # never the env value: gate 1 already pinned it
            user=env["PGUSER"],
            password=env["PGPASSWORD"],
            sslmode=env.get("PGSSLMODE", "require"),
            connect_timeout=int(env.get("PGCONNECT_TIMEOUT", "10")),
            application_name="isaac_db_recon",
        )
    except Exception as exc:  # noqa: BLE001
        # Only the exception CLASS is reported: psycopg2 messages can echo the
        # host, user and connection string.
        raise ConnectionRefused(f"could not connect ({type(exc).__name__})")
