"""HISTORICAL IMPORT — the SHELL. ``HIST-001`` and ``HIST-003a``.

WHAT THIS MODULE IS
===================

An **Import Session** is a working area in which a scientist assembles a **Source
Bundle** — a manifest of the files their historical work is scattered across —
has whatever this build can read parsed, has candidate Experiment/Run/field
values reconstructed from that reading, and sends the candidates into the
**existing** proposal review pipeline so a person decides each one.

The workflow this module exists to make honest, and the order is the product's:

    New Import -> Sources -> Parse -> Reconstruct -> Review -> Add to Experiments

The last step is ``HIST-005`` and is **not built**; see
:data:`CANDIDATE_NOT_PROPOSABLE_NO_EXPERIMENT_CREATION`.

THE ONE RULE THAT MATTERS MOST: NO BYTES ARRIVE FROM OUTSIDE
=============================================================

``POST /api/uploads`` is an unconditional 403 and this feature neither changes
nor depends on it. There is **no multipart parser reachable from here and no
file input on the import surface** — the latter is not a claim, it is enforced by
``apps/web/src/__tests__/upload-claim-parity.test.tsx``, which asserts that
EXACTLY two non-test frontend files declare ``type="file"`` and names both.

~~So a Source Bundle entry is one of exactly two kinds~~ — **CORRECTED 2026-09-16
by the slice that added the third, and struck rather than rewritten because "one of
exactly two" is a closed enumeration a future reader counts against.** There are
**three**, and the third was added because one-source-per-file does not fit: the
measured BL15-2 archive is **1,192 files** against a
:data:`MAX_SOURCES_PER_SESSION` of 500, and raising that ceiling would have been
the wrong fix rather than a bigger one — ``HIST-004``'s banned pattern is
*"Upload -> Spinner -> Mysterious JSON"*, and a 1,192-row manifest a scientist
cannot audit is the same as no manifest. So a folder or ZIP is **ONE** manifest
entry whose *parse result* is an inventory.

A Source Bundle entry is one of exactly three kinds, and the distinction is the
whole honesty boundary of the feature:

* :data:`SOURCE_KIND_REFERENCE` — a **pointer**. The scientist records where a
  file is (``reference``), what it is called (``filename``), and any digest they
  say identifies it. This build stores that. It does not open the file the
  pointer names, and :data:`PARSE_STATE_NO_CONTENT_PATH` says so per entry
  rather than in a banner. This is exactly the discipline
  :mod:`isaac_api.assets` already applies ("NO BYTES, EVER"), reused rather than
  re-invented — including ``is_sha256_shaped``, imported from the truth core so
  the shape rule has one definition.
* :data:`SOURCE_KIND_SYNTHETIC_FIXTURE` — one of the **committed synthetic
  fixtures** in :data:`FIXTURE_DIR`, named from a frozen allowlist
  (:func:`fixture_names`). These ARE read, because they are files inside this
  repository put there for this purpose, and each one says in its own first line
  that it is synthetic and was never produced by an instrument.
* :data:`SOURCE_KIND_ARCHIVE` — one of the **committed archive fixtures** named
  by :data:`ARCHIVE_FIXTURES`, a frozen allowlist resolved through
  :func:`archive_root_for`. A folder or ZIP inside this repository, read by
  :mod:`isaac_api.bl15.archive`'s bounded walk. It IS read, and it is a third
  kind precisely so that being read does not weaken the pointer's rule for the
  other two: a ``reference`` still means "NO BYTES, EVER", and this kind is
  honest about being read exactly as ``synthetic_fixture`` already is. Its
  ``provenance`` records ``bytes_read_by_this_application: True``.

~~**A DIGEST IS NEVER COMPUTED HERE, not even for a fixture this module does
read.**~~ — **CORRECTED 2026-09-16, in the same slice that made it false, and
struck rather than rewritten because an absolute is what a reader relies on.**
A digest IS computed here now, for archive MEMBERS, inside the parse. It had to
be: content hashing is the only thing that stops the corpus doubling (measured
in ``bl15.relate`` — every ``*_dir`` holds a byte-identical copy of its root
acquisition, and letting those copies become units turned **94** measurements
into **181**), and it is the only correct way to recognise the **96** duplicate
groups covering 193 files — one of which (``run22.mac``, ``run29``,
``run29.mac.mac``) shares no name at all, so no name heuristic could ever
assemble it.

**THE NARROW POSITION THAT REPLACES IT, stated precisely because the old
sentence was load-bearing for one specific surface:** a member digest is
computed **inside the parse, for structural deduplication, and is NEVER
published as a manifest** :attr:`SourceReference.sha256` **for any source, of
any kind.** That field stays *"what the scientist said"* — the scientist
supplies it or it stays absent, no surface may describe it as verified, and
:func:`add_source` still validates its SHAPE and computes nothing. The two
meanings behind one field name that the old sentence guarded against therefore
never arise: the digest that IS computed lives on an archive member inside
:class:`ArchiveReading`, never on a manifest entry. That distinction is
**mechanical rather than prose** —
``test_historical_import_archive.py`` asserts an archive source's
``sha256`` is ``None`` unless the scientist supplied one.

WHAT IS DELIBERATELY NOT BUILT, AND WHY IT IS NAMED RATHER THAN IMPLIED
=======================================================================

* **``BL15-001`` — the ``.mac`` parser. BLOCKED.** There is no representative
  ``.mac`` file anywhere in reach (``REC-009`` measured zero ``.mac`` and zero
  ``.xlsx``/``.xls`` in the whole tree), and ``CLAUDE.md`` §5 forbids designing
  against assumptions. This module ships a parser **interface**
  (:class:`SourceParser`) and a registry with exactly ONE registered parser,
  which reads a format this repository's own fixtures declare. No ``.mac`` syntax
  is guessed, and :data:`PARSERS` is deliberately short rather than aspirational.
* **``BL15-002`` — the Beamline Profile's conventions. BLOCKED.**
  :class:`BeamlineProfile` exists and encodes **zero** conventions;
  :data:`EMPTY_BEAMLINE_PROFILE` is the only instance this build has, and
  ``test_historical_import.py`` asserts every one of its collections is empty. A
  Beamline Profile is an interpretation aid and **never an unofficial
  validator** — nothing in this module consults it to accept or refuse a value.
* **``HIST-002`` — the first-wave deterministic parsers.** Spreadsheet reading
  would need ``openpyxl``. ~~which is not a dependency and is deliberately not
  added~~ — **THAT WAS FALSE AND IS CORRECTED 2026-09-13 after an independent
  review measured it.** ``openpyxl>=3.1`` IS a declared runtime dependency
  (``pyproject.toml``, added in ``dea4a7ae``), and it imports (3.1.5). The
  sentence invented a cost that does not exist, in the paragraph a reader
  consults to learn why this is blocked.
  **THE REAL BLOCKER IS UNCHANGED AND IS SUFFICIENT ON ITS OWN:** there is no
  representative corpus to validate a spreadsheet parser against, and §5 forbids
  designing against assumptions. Correcting this does NOT unblock ``HIST-002``;
  it removes a second reason that was never true.
* **``HIST-003b`` — real model reconstruction.** :class:`ReconstructionProvider`
  is provider-NEUTRAL and the only implementation is
  :class:`DeterministicFakeReconstructionProvider`. No provider is configured, no
  credential exists, no outbound call is made and none is authorized (Dean
  deferred **D1–D9**).

WHY A SEMANTIC CANDIDATE CANNOT BECOME RECORD TRUTH
====================================================

Structurally, not by assertion:

1. **Nothing in this module writes a draft.** It has no reference to
   ``Experiment.draft``, mints no evidence entry and builds no confirmation
   envelope. A negative control in ``test_historical_import.py`` greps this file
   for the literals that would give that away and asserts zero hits — the same
   check ``test_ingestion_proposals.py`` runs over ``proposals.py``.
2. **An import session is stored outside every experiment document.** It lives
   under :data:`IMPORTS_NAMESPACE`, a ``_``-prefixed directory that
   ``workspace._experiment_dirs`` skips unconditionally, so no experiment read
   can reach it and ``export_draft`` — which reads ``draft`` — cannot see it.
3. **The only way onward is a proposal.** A candidate leaves this module by
   being minted as one OPEN :class:`~isaac_api.proposals.IngestionProposal`
   citing one note, through ``proposals.new_proposal`` unchanged. Accepting a
   proposal is a separate operation that requires a trusted human identity, and
   in every default-configured deployment it answers ``409
   human_actor_required``. :data:`RECONSTRUCTION_APPLIED` is the constant this
   module publishes on the wire so a client reads the guarantee rather than
   having to know it.

WHERE AN IMPORT SESSION IS STORED, AND WHAT THAT COSTS
=======================================================

``<scope_root>/_imports/<import_id>/session.json``, written with
``workspace.atomic_write_text``.

**IT IS NOT DURABLE, AND THAT IS DISCLOSED RATHER THAN HIDDEN.** An experiment
survives a pod restart because ``experiment_repository`` upserts it into
``isaac_experiments``; an import session has no such row, because adding one
would need a migration and an operator action, and ``CLAUDE.md`` §15's
**DEC-24** is explicit that "zero migrations" is a target that must not become
pressure to force a requirement into an unsuitable structure. The honest
position is that a session is a **working area** whose durable output is the
proposals it mints onto real experiments — those ARE durable, because they are
inside the experiment document — and that the surface says so
(:data:`SESSION_DURABILITY_DISCLOSURE`). If a future slice needs a session to
survive a restart, that slice writes ``0006``, prepares the operator packet,
does not apply it, and adds the authorization sentence to §15 in the same change.

THE SCOPE IS PART OF THE PATH, so a worked-example session's imports live inside
that session's own root and are disposed with it. Every path is built through
``workspace.scope_root``, which is the one place the tutorial-session traversal
boundary is enforced.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence

from isaac_records.complete import is_sha256_shaped
from isaac_records.ids import is_record_id, new_record_id

from . import workspace as ws

# --- refusals -----------------------------------------------------------------


class UnsupportedImport(ValueError):
    """A refusal the HTTP layer renders as a typed 422 — never a 500.

    Carries a machine-readable ``error`` code and whatever extra body keys the
    refusal needs to be actionable. It is :class:`isaac_api.assets.UnsupportedAsset`'s
    arrangement for the same reason: ``complete.py`` grew type-guards because a
    wrong-typed structured answer used to escape as an HTTP 500, and a new write
    surface must not reopen that.
    """

    def __init__(self, error: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.extra = extra


# --- source bundle: the manifest ----------------------------------------------

#: A pointer. The scientist says where a file is; this build records that and
#: does not open it.
SOURCE_KIND_REFERENCE = "reference"

#: One of the committed synthetic fixtures in :data:`FIXTURE_DIR`. Read, because
#: it is a file inside this repository placed there for this purpose.
SOURCE_KIND_SYNTHETIC_FIXTURE = "synthetic_fixture"

#: A whole FOLDER or ZIP, as ONE manifest entry. Read by
#: :mod:`isaac_api.bl15.archive`'s bounded walk; its parse result is an
#: inventory rather than a list of statements.
#:
#: **ONE ENTRY FOR AN ARCHIVE OF ANY SIZE, AND THAT IS THE WHOLE REASON THIS
#: KIND EXISTS.** :data:`MAX_SOURCES_PER_SESSION` is 500 and the measured
#: BL15-2 corpus is 1,192 files. Raising the ceiling was considered and rejected:
#: ``HIST-004`` bans *"Upload -> Spinner -> Mysterious JSON"*, and a 1,192-row
#: manifest is that pattern wearing a manifest's clothes — complete, and
#: unreadable. The ceiling is untouched and still bounds MANIFEST ENTRIES; the
#: archive's own ceilings (:class:`isaac_api.bl15.inventory.ArchiveLimits`)
#: bound its members.
SOURCE_KIND_ARCHIVE = "archive"

SOURCE_KINDS = frozenset(
    {SOURCE_KIND_REFERENCE, SOURCE_KIND_SYNTHETIC_FIXTURE, SOURCE_KIND_ARCHIVE}
)

#: Registered, never parsed yet.
PARSE_STATE_UNPARSED = "unparsed"
#: A parser read it and produced statements.
PARSE_STATE_PARSED = "parsed"
#: A parser was applied and refused the content. ``parse_detail`` says why.
PARSE_STATE_FAILED = "failed"
#: **The honest state of every pointer in this build.** No parser can be applied
#: because this build has no path to the bytes: it did not receive them and it
#: does not open what a reference names.
PARSE_STATE_NO_CONTENT_PATH = "no_content_path"

PARSE_STATES = frozenset(
    {
        PARSE_STATE_UNPARSED,
        PARSE_STATE_PARSED,
        PARSE_STATE_FAILED,
        PARSE_STATE_NO_CONTENT_PATH,
    }
)

#: The per-entry sentence a pointer carries, in place of a banner. It states what
#: this build DID (recorded the reference) and what it did not do (open the file),
#: scoped to this entry — it makes no claim about the application as a whole, and
#: it deliberately does not mention the upload route at all. The absolute forms
#: are banned by ``apps/web/src/__tests__/upload-claim-parity.test.tsx`` for a
#: measured reason: they were false of this build.
NO_CONTENT_PATH_DETAIL = (
    "Recorded as a reference. This build stores where the file is and what you "
    "say identifies it; it has not opened the file, so nothing has been parsed "
    "from it and no value has been read out of it."
)

#: Longest filename this module will store. A manifest entry is a label, not a
#: filesystem operation, so the bound exists to keep one document from growing
#: without limit rather than to mirror any OS limit.
MAX_FILENAME_CHARS = 512
#: Longest reference. A URI can be long; a document should still be bounded.
MAX_REFERENCE_CHARS = 2048
#: Most sources one bundle may hold. Disclosed on refusal, never silently applied.
MAX_SOURCES_PER_SESSION = 500
#: Longest session label.
MAX_LABEL_CHARS = 200

#: Recognised media types are NOT constrained. A historical bundle contains
#: whatever it contains, and an allowlist here would be this module asserting
#: which formats historical science comes in — which is precisely the question
#: ``HIST-000``'s data request exists to answer. The value is stored verbatim,
#: bounded in length, and consulted by nothing.
MAX_MEDIA_TYPE_CHARS = 128


def _clean(value: object, label: str, *, maximum: int, required: bool) -> str | None:
    """A bounded, non-blank string, or ``None`` — never a silently-coerced one."""
    if value is None:
        if required:
            raise UnsupportedImport(
                "missing_field", f"`{label}` is required.", key=label
            )
        return None
    if not isinstance(value, str):
        raise UnsupportedImport(
            "wrong_type", f"`{label}` must be a string.", key=label
        )
    text = value.strip()
    if not text:
        if required:
            raise UnsupportedImport(
                "missing_field",
                f"`{label}` is required and must not be blank.",
                key=label,
            )
        return None
    if len(text) > maximum:
        raise UnsupportedImport(
            "too_long",
            f"`{label}` is longer than this build stores.",
            key=label,
            characters=len(text),
            maximum=maximum,
        )
    return text


@dataclass(frozen=True)
class SourceReference:
    """ONE manifest entry: metadata about one file, and never its bytes.

    The seven things ``HIST-001`` requires a manifest entry to record are the
    seven fields below plus :attr:`provenance`: filename, media type, size,
    digest, reference, parse state, provenance.

    :attr:`size_bytes` and :attr:`sha256` are **what the scientist said**, for a
    pointer, and are absent unless they said it. Nothing measures either.
    """

    source_id: str
    kind: str
    filename: str
    reference: str
    parse_state: str
    provenance: Mapping[str, Any]
    media_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    fixture_name: str | None = None
    parse_detail: str | None = None

    def to_state(self) -> dict:
        return {
            "source_id": self.source_id,
            "kind": self.kind,
            "filename": self.filename,
            "reference": self.reference,
            "parse_state": self.parse_state,
            "provenance": dict(self.provenance),
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "fixture_name": self.fixture_name,
            "parse_detail": self.parse_detail,
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> "SourceReference":
        """Rehydrate ONE entry. Raises on a shape this module cannot read.

        The raise is what :func:`_hydrate_sources` turns into a preserved
        unreadable entry rather than a discarded one — ``workspace._hydrate_notes``'
        arrangement, for its reason: a read path that silently drops what it cannot
        parse is a read path that deletes a scientist's work.
        """
        if not isinstance(state, Mapping):
            raise UnsupportedImport("invalid_entry", "A source entry must be an object.")
        kind = state.get("kind")
        parse_state = state.get("parse_state")
        if kind not in SOURCE_KINDS or parse_state not in PARSE_STATES:
            raise UnsupportedImport(
                "invalid_entry", "A source entry carries an unknown kind or parse state."
            )
        source_id = state.get("source_id")
        filename = state.get("filename")
        reference = state.get("reference")
        if not (
            isinstance(source_id, str)
            and isinstance(filename, str)
            and isinstance(reference, str)
        ):
            raise UnsupportedImport(
                "invalid_entry", "A source entry is missing a required string."
            )
        provenance = state.get("provenance")
        size = state.get("size_bytes")
        return cls(
            source_id=source_id,
            kind=kind,
            filename=filename,
            reference=reference,
            parse_state=parse_state,
            provenance=dict(provenance) if isinstance(provenance, Mapping) else {},
            media_type=state.get("media_type")
            if isinstance(state.get("media_type"), str)
            else None,
            # `bool` is excluded explicitly: `isinstance(True, int)` is True in
            # Python, so a persisted `true` would otherwise read as a size of 1.
            size_bytes=size
            if isinstance(size, int) and not isinstance(size, bool) and size >= 0
            else None,
            sha256=state.get("sha256")
            if isinstance(state.get("sha256"), str)
            else None,
            fixture_name=state.get("fixture_name")
            if isinstance(state.get("fixture_name"), str)
            else None,
            parse_detail=state.get("parse_detail")
            if isinstance(state.get("parse_detail"), str)
            else None,
        )


# --- the committed synthetic fixtures -----------------------------------------

#: Where the fixtures live. Inside the repository, never inside a workspace.
FIXTURE_DIR = ws.REPO_ROOT / "tests" / "fixtures" / "historical_import"

#: The allowlist shape. A fixture name is a bare filename with no separator and
#: no dot-segment, so no value a caller supplies can ever leave
#: :data:`FIXTURE_DIR`. This is an ALLOWLIST rather than a denylist of bad shapes
#: for the reason ``workspace._SESSION_ID_RE`` is one, and it is anchored
#: ``\A``/``\Z`` rather than ``^``/``$`` because Python's ``$`` also matches
#: before a trailing newline.
_FIXTURE_NAME_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,120}\Z")


def fixture_names() -> tuple[str, ...]:
    """Every synthetic fixture this build can parse, in name order.

    Derived from the directory rather than transcribed, so adding a fixture does
    not need a second edit — and filtered through :data:`_FIXTURE_NAME_RE`, so a
    file whose name could be mistaken for a path is not offered.
    """
    if not FIXTURE_DIR.is_dir():  # pragma: no cover - the directory is committed
        return ()
    return tuple(
        sorted(
            p.name
            for p in FIXTURE_DIR.iterdir()
            if p.is_file() and _FIXTURE_NAME_RE.fullmatch(p.name) is not None
        )
    )


def fixture_path(name: str) -> Path:
    """The path of one named fixture. Raises unless the name is on the allowlist.

    The membership test is against :func:`fixture_names`, not against the pattern
    alone: a name that merely LOOKS safe but does not exist must be refused by the
    same branch, so a caller cannot use this function to probe the filesystem.
    """
    if name not in fixture_names():
        raise UnsupportedImport(
            "unknown_fixture",
            "That is not one of the synthetic fixtures this build can parse.",
            key=name if isinstance(name, str) else None,
            available=list(fixture_names()),
        )
    return FIXTURE_DIR / name


# --- the committed archive fixtures (SOURCE_KIND_ARCHIVE) ---------------------

#: Everything :data:`ARCHIVE_FIXTURES`' values are resolved against. Inside the
#: repository, never inside a workspace, exactly as :data:`FIXTURE_DIR` is.
ARCHIVE_FIXTURE_ROOT = ws.REPO_ROOT

#: ``archive name -> repo-relative path of the folder or ZIP``. **A FROZEN
#: MAPPING RATHER THAN A DERIVED DIRECTORY LISTING, and the difference is the
#: traversal boundary.** :func:`fixture_names` can derive its allowlist from a
#: flat directory because every entry is a bare filename; an archive fixture is
#: a nested path (``tests/fixtures/bl15/gold/mini_corpus``), so a derived
#: allowlist would have to admit ``/`` — and once a caller-supplied string may
#: contain a separator, the allowlist stops being the boundary. Here the CALLER
#: only ever supplies a key, and the path is this module's own literal.
#:
#: The name is the scientist's handle and says what the corpus is. It
#: deliberately does not say "fixture" —
#: ``product-facing-language.test.tsx`` retires that word as product copy, and
#: this string reaches a screen.
ARCHIVE_FIXTURES: Mapping[str, str] = {
    "bl15_synthetic_mini_corpus": "tests/fixtures/bl15/gold/mini_corpus",
}


def archive_names() -> tuple[str, ...]:
    """Every archive this build can walk, in name order.

    Filtered by EXISTENCE, exactly as :func:`fixture_names` is: a key whose path
    is not on disk is not offered, so a deployment whose image excluded the
    fixtures advertises nothing it cannot read.

    **PLUS STAGED ARCHIVES, WHEN — AND ONLY WHEN — ``historical_file_ingestion`` IS
    ENABLED BY CONFIGURATION** (added 2026-09-22; :mod:`isaac_api.capabilities`). A staged
    name is namespaced ``staged:<name>`` so it can never collide with or shadow a
    committed fixture, and the capability is disabled in every shipped deployment
    (``EXT-13``), so in production this list is exactly the committed fixtures it
    always was.
    """
    from . import capabilities  # local: keeps import order flexible

    committed = tuple(
        name
        for name, relative in ARCHIVE_FIXTURES.items()
        if (ARCHIVE_FIXTURE_ROOT / relative).exists()
    )
    return tuple(sorted(committed + capabilities.staged_archive_names()))


def archive_root_for(name: str) -> Path:
    """The folder or ZIP one named archive fixture lives at.

    The membership test is against :func:`archive_names`, not against
    :data:`ARCHIVE_FIXTURES` alone, for :func:`fixture_path`'s reason: a name
    that merely LOOKS plausible but is not present must be refused by the same
    branch, so this cannot be used to probe the filesystem.
    """
    if name not in archive_names():
        raise UnsupportedImport(
            "unknown_archive",
            "That is not one of the committed archives this build can read.",
            key=name if isinstance(name, str) else None,
            available=list(archive_names()),
        )
    if name in ARCHIVE_FIXTURES:
        return ARCHIVE_FIXTURE_ROOT / ARCHIVE_FIXTURES[name]
    from . import capabilities  # local: keeps import order flexible

    # MEMBERSHIP ABOVE IS THE TRAVERSAL BOUNDARY: a staged name is only ever a direct,
    # allowlisted child of the configured staging root, re-listed on every call.
    staged = capabilities.resolve_staged(name)
    if staged is None:  # pragma: no cover - membership was just checked
        raise UnsupportedImport("unknown_archive", "That archive is no longer staged.")
    return staged


# --- parsers: the INTERFACE, and one fixture-format implementation ------------


@dataclass(frozen=True)
class EvidenceStatement:
    """ONE thing a source literally says, with where in the source it says it.

    :attr:`value` is VERBATIM. A parser reads; it does not normalise, coerce,
    round, or reinterpret — which is why there is no ``determinism`` field here.
    Every statement is read, and the deterministic-versus-inferred distinction
    belongs one stage later, at reconstruction, where an interpretation is made.
    """

    key: str
    value: str
    locator: str

    def to_state(self) -> dict:
        return {"key": self.key, "value": self.value, "locator": self.locator}


@dataclass(frozen=True)
class ParsedSource:
    """What ONE parser read out of ONE source.

    :attr:`skipped` is the other half of the report and is not optional: a parse
    that reported only what it understood would leave a scientist unable to see
    what it passed over, which is the ``Upload -> Spinner -> Mysterious JSON``
    pattern in miniature.
    """

    source_id: str
    parser_id: str
    statements: tuple[EvidenceStatement, ...]
    skipped: tuple[dict, ...] = ()
    #: The filename of the source this reading is of. Carried so a reconstruction
    #: can state which FILE supports a candidate — a source id means nothing to a
    #: scientist, and re-joining against the manifest in every consumer would be
    #: the same lookup written several times.
    filename: str = ""

    def to_state(self) -> dict:
        return {
            "source_id": self.source_id,
            "parser_id": self.parser_id,
            "filename": self.filename,
            "statements": [s.to_state() for s in self.statements],
            "skipped": [dict(entry) for entry in self.skipped],
        }


class SourceParser(Protocol):
    """The parser seam. ``HIST-002`` and ``BL15-001`` implement more of these.

    A parser is handed TEXT that the caller has already obtained by a means the
    caller is answerable for — today, only reading a committed synthetic fixture.
    **A parser never opens a file itself**, which is what keeps the "no bytes
    arrive from outside" boundary in one place instead of in every parser.
    """

    parser_id: str
    display_name: str

    def can_parse(self, source: SourceReference) -> bool:  # pragma: no cover - protocol
        ...

    def parse(self, source: SourceReference, text: str) -> ParsedSource:  # pragma: no cover - protocol
        ...


#: Longest source text a parser is handed. A bound rather than a silent
#: truncation: over it, the source's parse state becomes
#: :data:`PARSE_STATE_FAILED` with the measured size and this ceiling in
#: ``parse_detail``, so nothing is read partly and reported as whole.
MAX_SOURCE_TEXT_BYTES = 1_000_000
#: Most statements one source may contribute.
MAX_STATEMENTS_PER_SOURCE = 2_000


@dataclass(frozen=True)
class SyntheticFixtureKeyValueParser:
    """Reads THIS REPOSITORY'S OWN fixture format and nothing else.

    ``key = value``, one per line; ``#`` begins a comment line; a line with no
    ``=`` is reported under :attr:`ParsedSource.skipped` rather than dropped.

    **THIS IS NOT A BEAMLINE PARSER AND MUST NOT BE CITED AS ONE.** The format is
    declared by the fixtures in :data:`FIXTURE_DIR`, which say so in their own
    first lines. It exists so the contract from parsed evidence to a reviewed
    proposal can be exercised end to end; it encodes no convention that any real
    instrument uses, and ``BL15-001``/``BL15-002`` remain blocked on corpus
    evidence that does not exist in this repository.
    """

    parser_id: str = "synthetic_fixture_key_value"
    #: WHAT A SCIENTIST IS SHOWN, and it deliberately does not say "fixture".
    #:
    #: ``display_name`` reaches a product screen verbatim — it is interpolated
    #: into every parsed source's ``parse_detail`` ("Read by …"). "Fixture" is this
    #: project's test-harness vocabulary, and
    #: ``apps/web/src/__tests__/product-facing-language.test.tsx`` retires it as
    #: product copy; it caught the frontend half of this surface using it. That
    #: guard reads ``apps/web/src`` only — its own header names backend-served copy
    #: as a live gap it cannot see — so this string is register-checked by review,
    #: which is what this comment is for.
    #:
    #: ``parser_id`` KEEPS THE ENGINEERING NAME on purpose: it is a machine-readable
    #: identifier a client branches on, not a sentence anybody reads.
    display_name: str = "Example source (key = value)"

    def can_parse(self, source: SourceReference) -> bool:
        return source.kind == SOURCE_KIND_SYNTHETIC_FIXTURE

    def parse(self, source: SourceReference, text: str) -> ParsedSource:
        statements: list[EvidenceStatement] = []
        skipped: list[dict] = []
        for index, raw in enumerate(text.splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                skipped.append(
                    {
                        "locator": f"line {index}",
                        "reason": "no_key_value_separator",
                        "message": (
                            "This line has no `=`, so this parser cannot say what it "
                            "asserts. It is reported rather than dropped."
                        ),
                    }
                )
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if not key or not value:
                skipped.append(
                    {
                        "locator": f"line {index}",
                        "reason": "empty_key_or_value",
                        "message": (
                            "One side of the `=` is empty, so this parser cannot say "
                            "what it asserts. It is reported rather than dropped."
                        ),
                    }
                )
                continue
            if len(statements) >= MAX_STATEMENTS_PER_SOURCE:
                skipped.append(
                    {
                        "locator": f"line {index}",
                        "reason": "too_many_statements",
                        "message": (
                            "This source states more than one parse may report on. "
                            "The lines past the ceiling are named rather than read."
                        ),
                        "maximum": MAX_STATEMENTS_PER_SOURCE,
                    }
                )
                continue
            statements.append(
                EvidenceStatement(key=key, value=value, locator=f"line {index}")
            )
        return ParsedSource(
            source_id=source.source_id,
            parser_id=self.parser_id,
            filename=source.filename,
            statements=tuple(statements),
            skipped=tuple(skipped),
        )


#: EXACTLY ONE registered parser, and the shortness is the point. ``HIST-002``
#: (filenames, directories, spreadsheet cells, CSV, explicit key/value) is
#: BLOCKED on the corpus request, and ``BL15-001`` (``.mac``) is blocked because
#: no representative file exists anywhere in reach. Registering a stub for either
#: would be a parser that claims a format it has never seen.
PARSERS: tuple[SourceParser, ...] = (SyntheticFixtureKeyValueParser(),)


def parser_for(source: SourceReference) -> SourceParser | None:
    """The first registered parser that can read this source, or ``None``."""
    for parser in PARSERS:
        if parser.can_parse(source):
            return parser
    return None


# --- the Beamline Profile INTERFACE, encoding zero conventions ----------------


@dataclass(frozen=True)
class BeamlineProfile:
    """Repeatable source interpretation for one beamline — **the shape only**.

    ``BL15-002`` is **BLOCKED** on corpus evidence (``DEC-13`` / ``EXT-10``), and
    this build encodes **no convention at all**: every collection below is empty
    in the only instance that exists (:data:`EMPTY_BEAMLINE_PROFILE`), and
    ``test_historical_import.py`` asserts that.

    **A BEAMLINE PROFILE IS NOT AN UNOFFICIAL VALIDATOR.** Nothing in this module
    consults a profile to accept or refuse a value; the official schema is the
    only authority on what is valid (``CLAUDE.md`` §1). A profile's role is to
    make the same source read the same way twice, and only conventions supported
    by measured corpus evidence may ever be put in one.
    """

    profile_id: str
    display_name: str
    #: ``(regex, what it identifies)``. EMPTY — no filename convention is known.
    filename_patterns: tuple[tuple[str, str], ...] = ()
    #: ``(source key, official field path)``. EMPTY — no alias table is known.
    key_aliases: tuple[tuple[str, str], ...] = ()
    #: ``(source term, official vocabulary term)``. EMPTY.
    terminology: tuple[tuple[str, str], ...] = ()
    #: A stable facility identifier. ``None`` — the pilot beamline's canonical
    #: identifier is to be confirmed from primary evidence before anything
    #: hard-codes one, and ``bl152-users``/``bl152-staff`` are Authentik groups
    #: and explicitly not ISAAC identifiers.
    facility_identifier: str | None = None

    def is_empty(self) -> bool:
        return (
            not self.filename_patterns
            and not self.key_aliases
            and not self.terminology
            and self.facility_identifier is None
        )


#: The ONLY profile this build has. It is empty, and it is passed to the
#: reconstruction provider so the seam is exercised rather than merely declared.
EMPTY_BEAMLINE_PROFILE = BeamlineProfile(
    profile_id="empty",
    display_name="No beamline profile",
)


# --- semantic reconstruction: the provider-neutral contract (HIST-003a) -------

#: The candidate was produced by reading a source and nothing else. The rule
#: names the key and the locator it was read from.
DETERMINISM_DETERMINISTIC = "deterministic"
#: The candidate was produced by a STORED RULE applied over what the sources say,
#: and the sources do not state it. The rule sentence says which rule.
DETERMINISM_INFERRED = "inferred"

DETERMINISM_KINDS = frozenset({DETERMINISM_DETERMINISTIC, DETERMINISM_INFERRED})

#: What a candidate is ABOUT. ``field`` is a value at an official field path;
#: ``experiment`` and ``run`` are structural candidates — "ISAAC thinks an
#: experiment/run exists here" — which ``HIST-004`` requires the surface to show
#: and which nothing in this build can create from an import.
CANDIDATE_KIND_FIELD = "field"
CANDIDATE_KIND_EXPERIMENT = "experiment"
CANDIDATE_KIND_RUN = "run"

#: Why a candidate has no value: two or more sources assert different values at
#: the same path and this module chooses neither. ``SRC-001`` records that
#: multi-source disagreement is already representable downstream
#: (``evidence_classify.asserted_values`` -> ``conflicting_evidence``,
#: ``conflict_resolution``'s ``competing_values`` with ``deferred`` first-class),
#: so a disagreement reaching review as a decision rather than as a value is the
#: existing design and not a new one.
UNRESOLVED_SOURCES_DISAGREE = "sources_disagree"

#: The constant this module publishes so a client reads the guarantee instead of
#: having to know it — ``transcript_capture``'s ``applied`` flag, for its reason.
#: **Reconstruction applies nothing.** It writes no field, mints no evidence and
#: changes no record.
RECONSTRUCTION_APPLIED = False

#: Why a structural candidate is not proposable. Named rather than implied: the
#: proposal contract targets ONE field path, so "an experiment exists here" has
#: no proposal shape, and creating an experiment from an import is ``HIST-005``.
CANDIDATE_NOT_PROPOSABLE_NO_EXPERIMENT_CREATION = (
    "Nothing in this build creates an experiment or a run from an import. A "
    "proposal is about one value at one official field path, so this candidate "
    "has no proposal to become. Create the experiment yourself and propose the "
    "field candidates onto it."
)

#: Why a disagreeing candidate is not proposable.
CANDIDATE_NOT_PROPOSABLE_DISAGREEMENT = (
    "The sources disagree about this value, so this reconstruction chose none of "
    "them. Every competing value is listed with the source that asserts it; "
    "deciding between them is yours."
)

#: Why a candidate at a RECOGNISED path is still not proposable: no write
#: operation in this build accepts a value there, so a proposal for it could be
#: created and never applied. The wording is ``POST .../proposals``'
#: ``no_write_path_for_field`` refusal's, deliberately — ``CLAUDE.md`` §1 makes
#: the official schema not ours to speak for, and this says the limitation is
#: THIS BUILD's and never that the schema has no such field.
CANDIDATE_NOT_PROPOSABLE_NO_WRITE_PATH = (
    "This IS an official ISAAC field, and no write operation in this build "
    "accepts a value at its path — so a proposal for it could be created and "
    "never applied. The value stays visible here with the source it was read "
    "from. THIS IS A LIMITATION OF THIS BUILD AND NOT A STATEMENT ABOUT THE "
    "OFFICIAL ISAAC SCHEMA, which defines this field."
)

#: Why a time with NO ZONE is never proposed into a ``*_utc`` field (2026-09-23).
#:
#: A SPEC ``#D`` line — ``Fri Jan 01 00:00:00 2099`` — is the instrument's local clock
#: and names no zone. Proposing it verbatim into ``timestamps.acquired_start_utc``
#: would assert a UTC instant nothing states; converting it would guess the zone. It is
#: kept as evidence. A reading that carries its zone (the epoch line, converted to UTC
#: by a named rule) is proposable as before.
CANDIDATE_NOT_PROPOSABLE_LOCAL_TIME = (
    "This time is written in the instrument's local clock and names no time zone, so "
    "it cannot go into a UTC field without guessing the zone. It is kept as evidence. "
    "Where the file also states the instant as an epoch, that UTC value is the one "
    "offered."
)


#: Why a run-owned value read from a measurement that is NOT offered as a Run is not
#: proposable (2026-09-23). It was proposable, so the Add stage said "11 can be sent" and
#: the batch then sent 9: an alignment scan's epoch and timestamp have no run to belong
#: to, and never will. Stated once, here, and quoted by the batch route.
CANDIDATE_NOT_PROPOSABLE_NOT_A_RUN = (
    "This value belongs to a measurement this import does not offer as a Run — "
    "an alignment scan or a reference standard rather than a sample "
    "measurement. Its reading is kept and nothing is discarded; there is simply "
    "no run for it to be proposed against. Change the measurement's "
    "classification if you disagree."
)


def _target_scope(path: str | None) -> str | None:
    """``record`` | ``run`` | ``None`` — which writer applies a value at ``path``.

    Read from ``routes``, the one derivation the proposal routes use, rather than
    transcribed.
    """
    if not path:
        return None
    from . import routes

    writer = routes._proposal_writer_for(path)
    return routes._PROPOSAL_WRITER_SCOPE.get(writer) if writer else None


def _no_run_for(candidate: "SemanticCandidate") -> "SemanticCandidate":
    """A run-owned value of a measurement that is not a Run: shown, never sendable."""
    if candidate.proposable and _target_scope(candidate.target_field_path) == "run":
        return replace(candidate, not_proposable_reason=CANDIDATE_NOT_PROPOSABLE_NOT_A_RUN)
    return candidate


def is_zoned_utc_value(path: str | None, value: Any) -> bool:
    """Whether ``value`` may be proposed at ``path`` as far as TIME ZONES go.

    Any path not ending ``_utc`` is unaffected. A ``*_utc`` path takes only an ISO-8601
    instant that states its own offset (``Z`` or ``±hh:mm``).
    """
    if not path or not path.endswith("_utc"):
        return True
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


@dataclass(frozen=True)
class SemanticCandidate:
    """ONE thing a reconstruction thinks the sources support, and its warrant.

    :attr:`proposed_value` is ``None`` exactly when :attr:`unresolved_reason` is
    set. The two are not independent: a candidate either carries a value or says
    why it does not, and a candidate that carried a chosen value beside a
    recorded disagreement would be this module deciding a scientific question.
    """

    candidate_id: str
    kind: str
    determinism: str
    rule: str
    supporting_source_ids: tuple[str, ...]
    supporting_statements: tuple[dict, ...] = ()
    target_field_path: str | None = None
    proposed_value: Any = None
    disagreement: tuple[dict, ...] = ()
    unresolved_reason: str | None = None
    not_proposable_reason: str | None = None
    #: How many statements this candidate ACTUALLY rests on, when
    #: :attr:`supporting_statements` is a WINDOW onto more of them. ``None``
    #: means the list is complete, which is the state of every candidate the
    #: fixture provider builds.
    #:
    #: **IT EXISTS BECAUSE A LIST THAT IS A WINDOW MUST SAY SO, and the measured
    #: reason is the archive path:** one SPEC acquisition records its motor
    #: positions once per scan, so a single ``motor_position`` candidate over a
    #: 14-scan file rests on **4,816** statements
    #: (``bl15.evidence.MAX_EVIDENCE_PER_SOURCE``'s own measurement), and the
    #: real corpus produces ~1,000 candidates. Storing every statement on every
    #: candidate would put megabytes in one session document; storing the first
    #: :data:`MAX_STATEMENTS_PER_CANDIDATE` and saying nothing would report a
    #: window as a whole. Any count of witnesses reads THIS, never
    #: ``len(supporting_statements)`` — the same discipline
    #: ``bl15.evidence``'s own "a reader's evidence list can be a PARTIAL
    #: reading" note imposes one layer down.
    supporting_statement_total: int | None = None
    #: How many DIFFERENT source files state this candidate's reading(s). Added
    #: 2026-09-22 so :attr:`agreement` can say "sources agree" from a fact rather than
    #: from the length of a window. ``None`` for a candidate built before it existed.
    distinct_sources: int | None = None
    #: The scientist-confirmed resolution rule this candidate carries, when one applies
    #: (:mod:`isaac_api.convention_rules`). On a disagreeing candidate it marks the
    #: disagreement RESOLVED — the competing readings stay, as source facts — and on the
    #: derived candidate it names the rule the chosen value came from.
    resolved_by_rule: str | None = None
    #: READINGS THAT LEGITIMATELY DIFFER — one row per scan (or per item of a scan, or
    #: per file) for a concept whose cardinality says so
    #: (``bl15.mapping.RULE_CARDINALITY``). Each row is
    #: ``{scan, item, source, value, source_ids, locators}``. Added 2026-09-22 so values
    #: that differ from scan to scan are preserved as what they are instead of being
    #: reported as a disagreement. Empty when the readings agree, and on every
    #: candidate carrying a disagreement: a VARIATION and a CONFLICT are different facts
    #: and one candidate is never both.
    variation: tuple[dict, ...] = ()
    #: The cardinality the variation is keyed by — ``per_scan``, ``per_scan_item`` or
    #: ``per_source``. ``None`` with no variation.
    variation_basis: str | None = None
    #: How many rows the variation ACTUALLY has when :attr:`variation` is a window
    #: (:data:`MAX_VARIATION_ROWS`). ``None`` means the list is complete.
    variation_total: int | None = None
    #: How many distinct scans (or, for ``per_source``, files) the variation spans.
    variation_scans: int | None = None

    # --- UI statuses, DERIVED (2026-09-22) ----------------------------------------

    @property
    def agreement(self) -> str:
        """``sources_conflict`` | ``varies`` | ``sources_agree`` | ``single_source``.

        ``varies`` (2026-09-22): the readings differ from scan to scan (or file to
        file) as the concept's cardinality expects — neither agreement nor conflict.
        """
        if self.unresolved_reason is not None:
            return "sources_conflict"
        if self.variation:
            return "varies"
        if self.distinct_sources is not None and self.distinct_sources >= 2:
            return "sources_agree"
        return "single_source"

    @property
    def review_status(self) -> str:
        """What a scientist is asked to do about this candidate. Derived, never stored.

        ``resolved`` — a confirmed resolution applies; ``sources_conflict`` — the
        sources disagree and nothing is chosen; ``ready`` — a value can be sent to
        review as a proposal; ``unmapped`` — no official field takes it here (kept as
        evidence / extended context); ``needs_review`` — there is a field and something
        other than a disagreement keeps the value from travelling (a domain question, a
        build boundary, a structural candidate).
        """
        if self.resolved_by_rule is not None:
            return "resolved"
        if self.unresolved_reason is not None:
            return "sources_conflict"
        if self.proposable:
            return "ready"
        if self.kind == CANDIDATE_KIND_FIELD and self.target_field_path is None:
            return "unmapped"
        return "needs_review"

    @property
    def proposable(self) -> bool:
        """Whether this candidate can become a proposal in THIS build.

        A property with no field behind it, deliberately: it is derived from the
        conditions that decide it, so it cannot be persisted out of step with
        them.

        **IT KEYS ON ``not_proposable_reason``, AND THE FIRST VERSION DID NOT —
        WHICH WAS A MEASURED OVERCLAIM, not a latent one.** It read
        ``kind == field and unresolved_reason is None and target_field_path is
        not None``, and on the committed fixtures that returned ``True`` for
        ``system.configuration.detector_model``: a path this build recognises and
        has **no write route for**, which ``POST .../proposals`` refuses with
        ``no_write_path_for_field``. So the surface would have offered a
        `Send to Review` control for a candidate the server was always going to
        refuse — a queue entry promising work this application cannot do, which is
        the exact shape that refusal exists to prevent.

        Whether the chosen RECORD will accept it is still a separate question
        (an unknown run, a run-scoped target with no run named, the per-record
        ceiling) and is answered by the route against that record.
        """
        return (
            self.kind == CANDIDATE_KIND_FIELD
            and self.unresolved_reason is None
            and self.not_proposable_reason is None
            and self.target_field_path is not None
        )

    def to_state(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "kind": self.kind,
            "determinism": self.determinism,
            "rule": self.rule,
            "supporting_source_ids": list(self.supporting_source_ids),
            "supporting_statements": [dict(s) for s in self.supporting_statements],
            "target_field_path": self.target_field_path,
            "proposed_value": self.proposed_value,
            "disagreement": [dict(d) for d in self.disagreement],
            "unresolved_reason": self.unresolved_reason,
            "not_proposable_reason": self.not_proposable_reason,
            "supporting_statement_total": self.supporting_statement_total,
            "distinct_sources": self.distinct_sources,
            "resolved_by_rule": self.resolved_by_rule,
            "variation": [dict(v) for v in self.variation],
            "variation_basis": self.variation_basis,
            "variation_total": self.variation_total,
            "variation_scans": self.variation_scans,
            # DERIVED, and serialised anyway. A client that recomputed it would be
            # a second expression of the rule, free to drift from this one.
            "proposable": self.proposable,
            "agreement": self.agreement,
            "review_status": self.review_status,
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> "SemanticCandidate":
        if not isinstance(state, Mapping):
            raise UnsupportedImport(
                "invalid_entry", "A candidate entry must be an object."
            )
        cid = state.get("candidate_id")
        kind = state.get("kind")
        determinism = state.get("determinism")
        rule = state.get("rule")
        if not (
            isinstance(cid, str)
            and kind in {CANDIDATE_KIND_FIELD, CANDIDATE_KIND_EXPERIMENT, CANDIDATE_KIND_RUN}
            and determinism in DETERMINISM_KINDS
            and isinstance(rule, str)
        ):
            raise UnsupportedImport(
                "invalid_entry", "A candidate entry is missing a required field."
            )
        supporting = state.get("supporting_source_ids")
        statements = state.get("supporting_statements")
        disagreement = state.get("disagreement")
        return cls(
            candidate_id=cid,
            kind=kind,
            determinism=determinism,
            rule=rule,
            supporting_source_ids=tuple(
                s for s in (supporting or []) if isinstance(s, str)
            )
            if isinstance(supporting, list)
            else (),
            supporting_statements=tuple(
                dict(s) for s in (statements or []) if isinstance(s, Mapping)
            )
            if isinstance(statements, list)
            else (),
            target_field_path=state.get("target_field_path")
            if isinstance(state.get("target_field_path"), str)
            else None,
            proposed_value=state.get("proposed_value"),
            disagreement=tuple(
                dict(d) for d in (disagreement or []) if isinstance(d, Mapping)
            )
            if isinstance(disagreement, list)
            else (),
            unresolved_reason=state.get("unresolved_reason")
            if isinstance(state.get("unresolved_reason"), str)
            else None,
            not_proposable_reason=state.get("not_proposable_reason")
            if isinstance(state.get("not_proposable_reason"), str)
            else None,
            # `bool` excluded explicitly, for `SourceReference.from_state`'s
            # reason: `isinstance(True, int)` is True in Python, so a persisted
            # `true` would otherwise read as a total of 1.
            supporting_statement_total=state.get("supporting_statement_total")
            if isinstance(state.get("supporting_statement_total"), int)
            and not isinstance(state.get("supporting_statement_total"), bool)
            and state.get("supporting_statement_total") >= 0
            else None,
            distinct_sources=_as_count(state.get("distinct_sources")),
            resolved_by_rule=state.get("resolved_by_rule")
            if isinstance(state.get("resolved_by_rule"), str)
            else None,
            variation=tuple(
                dict(v) for v in (state.get("variation") or []) if isinstance(v, Mapping)
            )
            if isinstance(state.get("variation"), list)
            else (),
            variation_basis=state.get("variation_basis")
            if isinstance(state.get("variation_basis"), str)
            else None,
            variation_total=_as_count(state.get("variation_total")),
            variation_scans=_as_count(state.get("variation_scans")),
        )


@dataclass(frozen=True)
class Reconstruction:
    """What ONE provider made of ONE bundle's parsed evidence.

    :attr:`applied` is the constant :data:`RECONSTRUCTION_APPLIED` and is carried
    here so it crosses the JSON boundary with the payload it is about.
    """

    provider_id: str
    candidates: tuple[SemanticCandidate, ...]
    reconstructed_utc: str
    applied: bool = RECONSTRUCTION_APPLIED

    def to_state(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "reconstructed_utc": self.reconstructed_utc,
            "applied": self.applied,
            "candidates": [c.to_state() for c in self.candidates],
        }


class ReconstructionProvider(Protocol):
    """The semantic-reconstruction seam — **provider-neutral by construction**.

    It is handed parsed evidence and a :class:`BeamlineProfile` and returns
    candidates. It is given no network client, no credential, no model handle and
    no way to reach one; a real provider would be a different implementation of
    this protocol, wired by configuration that does not exist and is not
    authorized (Dean deferred **D1–D9**).

    **NO IMPLEMENTATION MAY WRITE.** The return type carries candidates, and a
    candidate reaches a record only by becoming an OPEN proposal a person
    accepts.
    """

    provider_id: str
    display_name: str

    def reconstruct(
        self,
        *,
        parsed: Sequence[ParsedSource],
        profile: BeamlineProfile,
        now_utc: str,
        mint_id,
    ) -> Reconstruction:  # pragma: no cover - protocol
        ...


def _official_field_paths() -> frozenset[str]:
    """Every official field path this build RECOGNISES, read from the ONE source.

    Imported lazily from :mod:`isaac_api.routes` because ``routes`` imports this
    module: a module-level import would be a cycle. The set is the route layer's
    own ``NOTE_MAPPABLE_FIELD_PATHS`` rather than a transcription of it, so this
    provider cannot recognise a path the rest of the application does not.
    """
    from . import routes

    return frozenset(routes.NOTE_MAPPABLE_FIELD_PATHS)


def _writable_field_paths() -> frozenset[str]:
    """Every recognised path this build has a WRITE ROUTE for. A strict subset.

    **THE TWO SETS ARE DIFFERENT AND THE DIFFERENCE IS LOAD-BEARING.** Measured
    at this HEAD: 25 recognised, 18 writable. A candidate at one of the other
    seven is shown with its value and its source and is marked not proposable —
    see :data:`CANDIDATE_NOT_PROPOSABLE_NO_WRITE_PATH`. Read from ``routes``
    rather than transcribed, for :func:`_official_field_paths`' reason.
    """
    from . import routes

    return frozenset(routes.PROPOSAL_TARGET_PATHS)


@dataclass(frozen=True)
class DeterministicFakeReconstructionProvider:
    """The fake. Deterministic, offline, and it recognises nothing it invented.

    **THE MAPPING RULE, STATED IN FULL BECAUSE IT IS THE WHOLE OF THE
    INTERPRETATION:** a parsed statement becomes a field candidate **iff its key
    IS an official ISAAC field path, verbatim**. There is no alias table, no
    fuzzy match, no case folding and no synonym list — because every one of those
    is a beamline convention, and ``BL15-002`` is blocked on evidence this
    repository does not hold. A key that is not a field path is reported as
    unmapped, never guessed at.

    It produces all three things ``HIST-004`` requires the surface to
    distinguish:

    * **deterministic** field candidates, whose rule quotes the key and the
      locator it was read from;
    * a **disagreement** whenever two or more sources state different values at
      one path — the candidate then carries every competing value with the source
      asserting it, and **no chosen value**;
    * one **inferred** structural candidate: a suggested experiment TITLE derived
      from the bundle's filenames by the stored rule in
      :data:`_TITLE_FROM_FILENAMES_RULE`. It is marked ``inferred`` because no
      source states it, and it is **not proposable** — a title is not a field
      path, and creating an experiment from an import is ``HIST-005``.

    Determinism is a property of the output, not a hope: candidates are ordered
    by ``(kind, target path, candidate order)`` and the ids are supplied by the
    caller's minter, so a test can pin the whole reconstruction.
    """

    provider_id: str = "deterministic_fake"
    display_name: str = "Deterministic fake (no model, no network)"

    def reconstruct(
        self,
        *,
        parsed: Sequence[ParsedSource],
        profile: BeamlineProfile,
        now_utc: str,
        mint_id,
    ) -> Reconstruction:
        # THE PROFILE IS ACCEPTED AND NOT CONSULTED, and that is the honest
        # behaviour of a build whose only profile is empty. Reading
        # `profile.key_aliases` would be reading an empty tuple and calling it an
        # interpretation; the seam is exercised by being in the signature, and a
        # future profile with measured conventions is what gives it work to do.
        official = _official_field_paths()
        writable = _writable_field_paths()
        # path -> value -> [(source_id, statement)]
        by_path: dict[str, dict[str, list[tuple[str, EvidenceStatement]]]] = {}
        unmapped: list[tuple[str, EvidenceStatement]] = []
        for source in parsed:
            for statement in source.statements:
                if statement.key in official:
                    by_path.setdefault(statement.key, {}).setdefault(
                        statement.value, []
                    ).append((source.source_id, statement))
                else:
                    unmapped.append((source.source_id, statement))

        candidates: list[SemanticCandidate] = []
        for path in sorted(by_path):
            values = by_path[path]
            supporting_ids = tuple(
                sorted({sid for entries in values.values() for sid, _ in entries})
            )
            statements = tuple(
                {
                    "source_id": sid,
                    "key": st.key,
                    "value": st.value,
                    "locator": st.locator,
                }
                for value in sorted(values)
                for sid, st in values[value]
            )
            if len(values) > 1:
                candidates.append(
                    SemanticCandidate(
                        candidate_id=mint_id(),
                        kind=CANDIDATE_KIND_FIELD,
                        determinism=DETERMINISM_DETERMINISTIC,
                        rule=(
                            f"{len(values)} of the parsed sources state a value at "
                            f"`{path}` and they do not agree, so this "
                            "reconstruction chose none of them."
                        ),
                        supporting_source_ids=supporting_ids,
                        supporting_statements=statements,
                        target_field_path=path,
                        proposed_value=None,
                        disagreement=tuple(
                            {
                                "value": value,
                                "source_ids": sorted({sid for sid, _ in values[value]}),
                                "locators": [st.locator for _, st in values[value]],
                            }
                            for value in sorted(values)
                        ),
                        unresolved_reason=UNRESOLVED_SOURCES_DISAGREE,
                        not_proposable_reason=CANDIDATE_NOT_PROPOSABLE_DISAGREEMENT,
                    )
                )
                continue
            (value,) = tuple(values)
            first_source, first_statement = values[value][0]
            candidates.append(
                SemanticCandidate(
                    candidate_id=mint_id(),
                    kind=CANDIDATE_KIND_FIELD,
                    determinism=DETERMINISM_DETERMINISTIC,
                    rule=(
                        f"Read verbatim from `{first_statement.key}` at "
                        f"{first_statement.locator} of the parsed source, whose key "
                        "IS this official ISAAC field path. No alias, synonym or "
                        "normalisation was applied."
                    ),
                    supporting_source_ids=supporting_ids,
                    supporting_statements=statements,
                    target_field_path=path,
                    proposed_value=value,
                    # THE WRITABILITY CHECK IS HERE, at the point the candidate is
                    # built, rather than left for the surface or the route to
                    # discover. A candidate offered for review that the proposal
                    # route was always going to refuse is a control that promises
                    # work this build cannot do.
                    not_proposable_reason=(
                        None
                        if path in writable
                        else CANDIDATE_NOT_PROPOSABLE_NO_WRITE_PATH
                    ),
                )
            )

        title = _title_from_filenames(parsed)
        if title is not None:
            stem, source_ids = title
            candidates.append(
                SemanticCandidate(
                    candidate_id=mint_id(),
                    kind=CANDIDATE_KIND_EXPERIMENT,
                    determinism=DETERMINISM_INFERRED,
                    rule=_TITLE_FROM_FILENAMES_RULE.format(stem=stem),
                    supporting_source_ids=source_ids,
                    proposed_value=stem,
                    not_proposable_reason=CANDIDATE_NOT_PROPOSABLE_NO_EXPERIMENT_CREATION,
                )
            )

        # UNMAPPED KEYS ARE REPORTED, NEVER GUESSED AT. They are not candidates —
        # this provider has no basis for saying what they mean — so they travel as
        # a disclosure on the session rather than as a candidate with an invented
        # target. See `ImportSession.unmapped_keys`.
        return Reconstruction(
            provider_id=self.provider_id,
            candidates=tuple(candidates),
            reconstructed_utc=now_utc,
        )


#: The ONE stored inference this build makes, written out so it can be quoted to
#: the scientist verbatim and pinned by test. It is a rule about FILENAMES, which
#: is the only thing about the bundle every source has in common, and it is
#: marked ``inferred`` precisely because no source states a title.
_TITLE_FROM_FILENAMES_RULE = (
    "Suggested from the parsed sources' filenames, which share the leading text "
    "`{stem}`. NO SOURCE STATES A TITLE — this is an inference by a stored rule, "
    "not something read, and it is offered only as a starting point for a name "
    "you choose."
)


def _title_from_filenames(parsed: Sequence[ParsedSource]) -> tuple[str, tuple[str, ...]] | None:
    """The longest common leading text of the parsed sources' FILENAMES, or ``None``.

    Returns ``None`` unless at least two sources were parsed AND they share at
    least three leading characters after trimming separators. Three rather than
    one, because a one- or two-character stem is not a name and offering it would
    be an inference with nothing behind it — and ``None`` is the honest answer
    when the filenames have nothing in common, which is the common case for a
    real historical bundle.
    """
    names = [p.filename for p in parsed if p.filename]
    if len(names) < 2:
        return None
    stem = names[0]
    for name in names[1:]:
        limit = min(len(stem), len(name))
        cut = 0
        while cut < limit and stem[cut] == name[cut]:
            cut += 1
        stem = stem[:cut]
    stem = stem.strip(" -_.")
    if len(stem) < 3:
        return None
    return stem, tuple(sorted(p.source_id for p in parsed))


#: The provider this build uses. ONE, and it is the fake — named in the constant
#: so no surface has to decide what to call it.
PROVIDER: ReconstructionProvider = DeterministicFakeReconstructionProvider()


# --- reading a whole archive (SOURCE_KIND_ARCHIVE) ----------------------------
#
# WHAT THIS SECTION IS, AND WHERE ITS LAYERS LIVE. Everything below composes
# `isaac_api.bl15` — the archive walk, the content-led classifier, the five
# readers, the relationship pass and the candidate assembly — and adds nothing
# scientific of its own. Every decision about WHAT a file is, WHAT it says, WHAT
# belongs to what and WHICH official field path a concept maps to is made there
# and is not re-derived here.
#
# `bl15` IS IMPORTED LAZILY, INSIDE THE FUNCTIONS, AND THAT IS NOT STYLE.
# `bl15.reconstruct` imports `EvidenceStatement`, `SemanticCandidate` and four
# constants FROM THIS MODULE, so a module-level import here would be a cycle.
# `_official_field_paths` already does the same thing for `routes`, for the same
# reason.

#: WHAT THIS SESSION PERSISTS, AND WHAT IT RECOMPUTES — the decision the design
#: doc asked for, stated here rather than left to be inferred from the code.
#:
#: **MEASURED FIRST.** Over the real 1,192-file corpus the reading layer produces
#: roughly **500,000 evidence items** and **~1,000 candidates**. A session
#: document carrying every evidence item would be tens of megabytes: not merely
#: slow, but a working area nobody can load, which is a worse failure than a
#: refusal. So:
#:
#: **PERSISTED** (:class:`ArchiveReading`, written into the session document):
#: the inventory's totals, refusals, truncation reason and duplicate groups; the
#: per-entry MANIFEST; the per-entry CLASSIFICATION with its reason, confidence
#: and overridability; a per-source READING ROW (which reader ran, how many
#: statements it read, how many it suppressed, whether the reading is partial,
#: why it was refused); the RELATIONSHIPS (units, sample groups, conflicts,
#: unattached sources); the reconstruction's own concept and mapping-status
#: AGGREGATES; and the CANDIDATES, each with a bounded window of its supporting
#: statements.
#:
#: **NOT PERSISTED, and recomputed by re-running Parse:** the full
#: :class:`~isaac_api.bl15.evidence.SourceEvidence` set. It is derived — the same
#: asymmetry :func:`_hydrate_parsed` already applies to a parse result — and an
#: unreadable or absent one costs a recomputation rather than a scientist's work.
#: Nothing in the review pipeline consumes it: a candidate carries the statements
#: it rests on, and the archive path travels in every locator.
ARCHIVE_PERSISTENCE_DECISION = (
    "An import session stores this archive's manifest, its classifications, its "
    "relationships, its measurement units and its candidates. It does not store "
    "every individual reading a parser made — over a real archive that is "
    "hundreds of thousands of entries — so the per-statement detail is "
    "recomputed by parsing again rather than kept. Nothing you review depends on "
    "it: every candidate carries the statements it rests on, each naming the file "
    "and the line it was read from."
)

#: Most supporting statements ONE candidate stores. Over the ceiling the list is
#: a WINDOW and :attr:`SemanticCandidate.supporting_statement_total` states the
#: true count — see that field for the measurement that forced it.
#:
#: **FIVE, AND THE NUMBER IS MEASURED RATHER THAN CHOSEN.** With no window at
#: all, a session over the real corpus's cardinality persisted at **10,453,571
#: bytes**, of which the candidates alone were **5,566,994** — 2,963 bytes each
#: across 1,879 candidates, because every statement's locator carries the full
#: archive path. At five the candidates come to roughly a third of that. The
#: window is deliberately NOT applied to
#: :attr:`SemanticCandidate.disagreement`, which is what carries EVERY competing
#: reading of a conflict: windowing that would turn "the sources disagree, here
#: is each one" into "here are some of them", which is the one thing this whole
#: feature exists not to do.
MAX_STATEMENTS_PER_CANDIDATE = 5

#: Most per-scan VARIATION rows one candidate stores. Over it the list is a window and
#: ``variation_total`` states the true count. Unlike a disagreement, a variation MAY be
#: windowed: it is not "the sources disagree, here is each one" — it is "each scan has
#: its own value", and a 14-scan acquisition with 172 motors would otherwise carry 2,408
#: rows on one candidate. The first rows plus a true total say what it is.
MAX_VARIATION_ROWS = 24

#: Most ``skipped`` entries ONE source's reading row stores. Over it the list is
#: a window and the row's ``skipped_total`` states the true count.
#:
#: **ALSO MEASURED.** Unbounded, the per-source reading rows came to
#: **1,618,508 bytes** over 1,096 sources — 1,477 each — because a reader reports
#: every prose block it passed over, with the first line of each. The rows exist
#: so a scientist can see what a reader did not understand; five examples plus a
#: true total serves that, and 1.5 MB of it does not.
MAX_SKIPPED_PER_SOURCE = 5

#: The concepts the review surface's scientific columns read, and the ONLY evidence an
#: archive reading retains per measurement.
#:
#: **THIS EXISTS BECAUSE THE SURFACE AND THE PAYLOAD DID NOT MEET.** The review surface
#: was built against a ``Bl15CorpusReview.evidence`` list and the server persisted no
#: evidence at all — measured at the real corpus's cardinality, the full set is ~500,000
#: items, which is why the wiring slice deliberately did not keep it. So the surface
#: rendered behind a payload no route emitted, and three comments justified that with a
#: reason that had gone false. Independent review found both.
#:
#: The join is possible because the surface needs **six** concepts, not forty-five: it
#: reads them for five columns (sample, medium, state, filter, potential) and ignores the
#: rest. Restricted to those, and to readings that name a measurement, the set is a few
#: per unit rather than five thousand.
#:
#: Kept in step with ``apps/web/src/lib/bl15Review.ts``'s ``BL15_COLUMN_CONCEPTS`` by
#: ``test_historical_import_archive.py``, so a sixth column cannot be added on one side
#: only.
REVIEW_COLUMN_CONCEPTS: frozenset[str] = frozenset(
    {
        "sample_name",
        "electrolyte_or_medium",
        "cycling_state",
        "before_after_state",
        "filter",
        "potential_magnitude",
    }
)

#: Most DISTINCT readings retained per measurement-and-concept.
#:
#: **THE CAP IS BY DISTINCT LITERAL, NOT BY COUNT, AND THAT IS WHAT MAKES IT SAFE.** The
#: surface's cell has three states — absent, read, disputed — and `disputed` fires on two
#: or more DIFFERENT literals. A cap on the raw count could drop the one reading that
#: differed and silently turn a disputed cell into a settled one, which is the class of
#: defect this whole feature exists to prevent. Keeping the first reading of each distinct
#: literal preserves that decision exactly, whatever the corpus does.
#:
#: Four rather than two, so a scientist opening a disputed cell sees more than the minimum
#: needed to prove the dispute. The number of readings DROPPED is carried beside the list.
MAX_DISTINCT_COLUMN_READINGS = 4

#: Most candidates one archive reading contributes. The real corpus produces
#: ~1,000 across 94 measurements, so this is ~4x headroom rather than a round
#: number. Over it, candidates are DROPPED FROM THE TAIL and the count is
#: disclosed in :attr:`ArchiveReading.candidate_total` — never trimmed silently.
MAX_CANDIDATES_PER_SESSION = 4_000

#: Most `DEC-41` level-4 companion entries one archive reading contributes.
#:
#: **THE NUMBER IS NOT DERIVED FROM A CORPUS MEASUREMENT, AND SAYING SO IS PART OF
#: THE BOUND.** No level-4 statement count over the real BL15-2 archive exists in
#: this repository, and inventing one would be the kind of figure
#: ``bl15.evidence.MAX_EVIDENCE_PER_SOURCE``'s own struck paragraph records paying
#: for. What IS known and is what this is sized against: a companion entry
#: serialises to roughly the size of one :class:`SemanticCandidate` statement, and
#: it lands in the EXPERIMENT state document, which is rewritten whole on every
#: save. So this is set at a quarter of :data:`MAX_CANDIDATES_PER_SESSION` —
#: deliberately tighter than the candidate bound, because a candidate lives in a
#: session document that a discard throws away and a companion entry lives in the
#: record forever.
#:
#: Over it, entries are dropped FROM THE TAIL and the number dropped is carried in
#: :attr:`ArchiveReading.extended_context_dropped` — never trimmed silently.
#:
#: ***THAT SENTENCE WAS TRUE OF THE CEILING AND FALSE OF THE COUNTER, AND THE COUNTER IS
#: NOW SPLIT RATHER THAN THE SENTENCE REWORDED — `CTX-004`, 2026-09-18.*** Until this
#: change ``extended_context_dropped`` was incremented by TWO different causes: this tail
#: cap, and the per-source ``(concept, source, literal)`` dedup in
#: :func:`_extended_context_entries`. The attribute's own docstring said so correctly
#: ("the per-source dedup and the tail cap"); this comment and that function's docstring
#: both said "the tail", so the repository described one integer two incompatible ways and
#: **no test pinned any of them**.
#:
#: It matters because the two facts have OPPOSITE significance to a scientist, and the
#: disclosure `CTX-004` had to render could not be truthful over their sum. Hitting this
#: ceiling means statements the archive made are **not in the record** and the reader's
#: corpus is larger than the companion holds — actionable. The dedup means a literal
#: repeated inside ONE file kept its first locator and lost the later ones — a SPEC
#: acquisition names its motors once per scan, so a 22-scan file states the same value 22
#: times, and thinning it destroys no statement. Reported as one number, a reader cannot
#: tell whether anything was lost.
#:
#: So :attr:`ArchiveReading.extended_context_dropped` now means the tail cap ALONE, which
#: is what this comment always claimed, and the dedup is
#: :attr:`ArchiveReading.extended_context_thinned`.
MAX_EXTENDED_CONTEXT_ENTRIES = 1_000

#: Most manifest rows, unit rows or reading rows :func:`session_view` serves in
#: one response. The archive KEEPS all of them; this bounds the WINDOW.
#:
#: **THE WINDOW BOUNDS WHAT IS FETCHED, NEVER WHAT IS CLAIMED** — the rule
#: ``CLAUDE.md`` §11's 2026-09-02 entry states for ``PENDING_WINDOW``, applied
#: here because the failure mode is identical: a surface that counted the rows it
#: received would understate a 1,192-file corpus as 200 files. Every page served
#: below carries its own ``total``, read off the persisted collection.
ARCHIVE_PAGE_WINDOW = 200

#: Why a candidate Run from a historical archive cannot be export-ready. THREE
#: reasons, each measured, and the surface must say so rather than showing a
#: progress indicator that can never fill.
#:
#: Two of the three are quoted from :mod:`isaac_api.bl15.mapping` rather than
#: rewritten, so there is one wording per fact. The third has no home there
#: because it is not about a CONCEPT's mapping at all — it is a property of the
#: official schema's ``record_type`` conditional — so it is stated here, once.
EXPORT_BLOCKED_NO_DESCRIPTORS = (
    "An official ISAAC record of type `evidence` must carry `descriptors`, and "
    "no historical source in this archive provides one. A descriptor is a "
    "derived scientific product, not something a filename or an instrument "
    "header states, so nothing here can supply it and nothing here will invent "
    "it."
)


def export_blocked_reasons() -> tuple[str, ...]:
    """The three sentences a surface shows instead of a progress bar. Derived.

    Two are :mod:`bl15.mapping`'s own constants, read at call time rather than
    transcribed: if that module's wording changes, this follows it. The third is
    :data:`EXPORT_BLOCKED_NO_DESCRIPTORS`.
    """
    from .bl15 import mapping as mp

    return (
        mp.TEMPERATURE_ABSENT_REASON,
        EXPORT_BLOCKED_NO_DESCRIPTORS,
        mp.ASSETS_BLOCKED_REASON,
    )


@dataclass(frozen=True)
class UnitReading:
    """ONE measurement this archive found, as the session remembers it.

    It is a projection of :class:`isaac_api.bl15.relate.MeasurementUnit` plus the
    two things the session adds: the candidate ids this unit produced, and the
    :attr:`label` a Run would carry.

    :attr:`run_candidate` is **carried, not re-derived** — it is
    ``MeasurementUnit.run_candidate``, which is itself derived from the
    classification. An alignment scan and a reference pellet are real
    measurements, fully assembled, and are deliberately **not** offered as Runs;
    a scientist who disagrees changes the classification, which is a separate
    act, and nothing is discarded either way.
    """

    stem: str
    acquisition_path: str
    source_type: str
    run_candidate: bool
    label: str
    legacy_number: int | None = None
    group_token: str | None = None
    scan_count: int = 0
    source_count: int = 0
    conflict_count: int = 0
    candidate_ids: tuple[str, ...] = ()
    # --- added 2026-09-22 ------------------------------------------------------
    #: A DURABLE INTERNAL IDENTITY for the acquisition this unit is built around:
    #: ``<archive>:<archive path>@<member digest>``. **Never the legacy number** — two
    #: distinct acquisitions carry legacy number 32 in the real archive (``Q16``, which
    #: the domain owner cannot settle), so a run is matched to its measurement by WHAT
    #: IT IS. The digest is the member digest the walk computes for deduplication; it is
    #: never published as a manifest ``sha256``.
    acquisition_identity: str = ""
    #: Whether another unit in this archive carries the same legacy number.
    legacy_number_shared: bool = False
    #: Which naming convention the acquisition was read under, at what scope, on what
    #: basis, and any ambiguity — :class:`bl15.applicability.Applicability`.
    applicability: Mapping[str, Any] = field(default_factory=dict)
    #: The per-Run HERFD primary-signal selection — :mod:`bl15.signals`. A suggestion
    #: at most; it writes no field.
    signal_selection: Mapping[str, Any] | None = None
    #: The file's own Notes-cell remarks, verbatim — "Data Quality Notes". Never a QC
    #: verdict.
    data_quality_notes: tuple[dict, ...] = ()
    #: People the sources NAME for this measurement — provenance, never a parsing rule
    #: and never an actor.
    contributors: tuple[dict, ...] = ()

    def to_state(self) -> dict:
        return {
            "stem": self.stem,
            "acquisition_path": self.acquisition_path,
            "source_type": self.source_type,
            "run_candidate": self.run_candidate,
            "label": self.label,
            "legacy_number": self.legacy_number,
            "group_token": self.group_token,
            "scan_count": self.scan_count,
            "source_count": self.source_count,
            "conflict_count": self.conflict_count,
            "candidate_ids": list(self.candidate_ids),
            "acquisition_identity": self.acquisition_identity,
            "legacy_number_shared": self.legacy_number_shared,
            "applicability": dict(self.applicability),
            "signal_selection": (
                dict(self.signal_selection) if self.signal_selection is not None else None
            ),
            "data_quality_notes": [dict(n) for n in self.data_quality_notes],
            "contributors": [dict(c) for c in self.contributors],
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> "UnitReading":
        if not isinstance(state, Mapping):
            raise UnsupportedImport("invalid_entry", "A unit entry must be an object.")
        stem = state.get("stem")
        path = state.get("acquisition_path")
        source_type = state.get("source_type")
        label = state.get("label")
        if not (
            isinstance(stem, str)
            and isinstance(path, str)
            and isinstance(source_type, str)
            and isinstance(label, str)
        ):
            raise UnsupportedImport(
                "invalid_entry", "A unit entry is missing a required string."
            )
        return cls(
            stem=stem,
            acquisition_path=path,
            source_type=source_type,
            run_candidate=state.get("run_candidate") is True,
            label=label,
            legacy_number=_as_count(state.get("legacy_number")),
            group_token=state.get("group_token")
            if isinstance(state.get("group_token"), str)
            else None,
            scan_count=_as_count(state.get("scan_count")) or 0,
            source_count=_as_count(state.get("source_count")) or 0,
            conflict_count=_as_count(state.get("conflict_count")) or 0,
            candidate_ids=tuple(
                cid for cid in (state.get("candidate_ids") or []) if isinstance(cid, str)
            )
            if isinstance(state.get("candidate_ids"), list)
            else (),
            # READ, NOT REFUSED: a session written before 2026-09-22 has none of these
            # and hydrates to their empty values — a re-parse recomputes them.
            acquisition_identity=state.get("acquisition_identity")
            if isinstance(state.get("acquisition_identity"), str)
            else "",
            legacy_number_shared=state.get("legacy_number_shared") is True,
            applicability=dict(state.get("applicability"))
            if isinstance(state.get("applicability"), Mapping)
            else {},
            signal_selection=dict(state.get("signal_selection"))
            if isinstance(state.get("signal_selection"), Mapping)
            else None,
            data_quality_notes=tuple(
                dict(n) for n in (state.get("data_quality_notes") or []) if isinstance(n, Mapping)
            )
            if isinstance(state.get("data_quality_notes"), list)
            else (),
            contributors=tuple(
                dict(c) for c in (state.get("contributors") or []) if isinstance(c, Mapping)
            )
            if isinstance(state.get("contributors"), list)
            else (),
        )


def _mapping_rows(value: object) -> tuple[dict, ...]:
    """A persisted list of objects, read tolerantly: non-objects are skipped."""
    if not isinstance(value, list):
        return ()
    return tuple(dict(row) for row in value if isinstance(row, Mapping))


def _as_count(value: object) -> int | None:
    """A non-negative whole number, or ``None``. ``bool`` is excluded explicitly.

    ``isinstance(True, int)`` is True in Python, so a persisted ``true`` would
    otherwise read as the count 1 — the trap :meth:`SourceReference.from_state`
    already names.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


@dataclass(frozen=True)
class ArchiveReading:
    """What ONE archive source's parse found. The session's whole memory of it.

    **IT CARRIES NO CANDIDATES.** They live where every candidate already lives —
    :attr:`ImportSession.reconstruction` — and each :class:`UnitReading` names
    the ones it produced by id. Holding a second copy here would put the same
    ~1,000 candidates in the session document twice, and would let the two
    disagree about what the reconstruction found.
    """

    source_id: str
    root_label: str
    archive_name: str
    walker_id: str
    #: ``ArchiveInventory.to_state()``. Totals, refusals, truncation, duplicate
    #: group count — and deliberately NOT the entries, which
    #: :attr:`manifest` carries because ``inventory.to_state()`` omits them and
    #: this module may not change that contract.
    inventory: Mapping[str, Any] = field(default_factory=dict)
    #: One row per accepted entry: the file facts AND its classification, joined
    #: here because they are keyed identically and a surface renders them
    #: together. ``content_sha256`` is a MEMBER digest computed inside the parse
    #: for deduplication; it is never a manifest ``sha256``.
    manifest: tuple[dict, ...] = ()
    #: One row per source a reader was applied to: which reader, how much it
    #: read, how much it SUPPRESSED, and whether the reading is partial.
    reading: tuple[dict, ...] = ()
    #: ``Relationships.to_state()`` — units, sample groups, corpus conflicts,
    #: unattached sources, and which relate inputs were actually present.
    relationships: Mapping[str, Any] = field(default_factory=dict)
    units: tuple[UnitReading, ...] = ()
    #: ``SourceEvidence.to_state()`` for the review surface's five scientific columns,
    #: and nothing else — see :data:`REVIEW_COLUMN_CONCEPTS` for why this is six concepts
    #: rather than forty-five, and :data:`MAX_DISTINCT_COLUMN_READINGS` for why the cap is
    #: by distinct literal. Only readings that NAME a measurement are here; a
    #: beamtime-scope statement belongs to the import and the surface is explicit that
    #: folding one into a unit would invent a relationship ``relate`` declined to make.
    column_readings: tuple[dict, ...] = ()
    #: How many readings the per-cell cap dropped, over the whole archive. Carried so the
    #: list is never a trimmed one presented as whole — the same rule every other page
    #: here follows.
    column_readings_dropped: int = 0
    #: How many readings the per-cell DEDUP thinned — a literal already kept for the
    #: same measurement and concept. **A different fact from
    #: :attr:`column_readings_dropped`, split 2026-09-22 exactly as `CTX-004` split the
    #: extended-context counter:** thinned loses no distinct reading (corroboration was
    #: trimmed), while dropped means a DIFFERENT literal was not kept because the cell
    #: already held :data:`MAX_DISTINCT_COLUMN_READINGS` of them. ~~Until the split, both
    #: were counted into one integer served as `evidence_readings_dropped` under a
    #: comment describing the dedup half only~~ — ``docs/session-closure-2026-09-18.md``
    #: §8 named it as residue. A session written before the split hydrates this to 0 and
    #: keeps its union count in ``column_readings_dropped``; it cannot be split
    #: retroactively and a re-parse recomputes both.
    column_readings_thinned: int = 0
    #: Candidate ids belonging to the import rather than to one measurement — the
    #: beamtime-scope context every unit INHERITS and none of them copies.
    shared_candidate_ids: tuple[str, ...] = ()
    #: ``extended_context.ContextEntry.to_state()`` for every `DEC-41` LEVEL-4
    #: statement this archive stated — the metadata the official ISAAC v1.05 record
    #: has no field for. See :func:`_extended_context_entries` for what is included,
    #: why the level is never chosen here, and why the dedup key carries the source
    #: path.
    #:
    #: **IT IS NOT A CANDIDATE AND NEVER BECOMES ONE.** A candidate is a value
    #: proposed at an official field path; these have no such path by definition, and
    #: their whole reason for existing is that the twelve level-4 concepts were read
    #: and then had nowhere to go. The candidate stream is UNCHANGED by this field.
    extended_context_entries: tuple[dict, ...] = ()
    #: How many level-4 statements the TAIL CAP dropped — ``MAX_EXTENDED_CONTEXT_ENTRIES``
    #: and nothing else. Non-zero means statements this archive made are absent from the
    #: companion, so the list is a trimmed one and must never be presented as whole.
    #:
    #: ~~"the per-source dedup and the tail cap"~~ — **NARROWED 2026-09-18 (`CTX-004`),
    #: and the old wording is struck rather than edited because it was the ACCURATE
    #: description of a counter two other comments described as the tail alone.** The two
    #: causes are now separate fields; the argument for separating them is at
    #: ``MAX_EXTENDED_CONTEXT_ENTRIES``. Narrowing was safe to do rather than merely
    #: desirable: nothing read this field except :meth:`to_state`/:meth:`from_state` and
    #: the constructor, and no test asserted over it — which is also how the conflation
    #: survived.
    extended_context_dropped: int = 0
    #: How many level-4 statements the per-source ``(concept, source, literal)`` dedup
    #: thinned. **A different fact from :attr:`extended_context_dropped` and deliberately
    #: not added to it.** Non-zero means a literal stated more than once INSIDE ONE source
    #: kept its first locator and lost the later ones; no statement was lost and no
    #: disagreement was settled, because two different sources are two different keys.
    extended_context_thinned: int = 0
    #: How many level-4 statements this BUILD could not place — ``check_placement`` or
    #: ``ContextEntry``'s own construction refused them. **A third fact, and the one no
    #: comment anywhere described before `CTX-004`.** It is not a bound and not a
    #: duplicate: a larger ceiling and a re-import would both leave it unchanged. The
    #: statements are still in the reader's evidence and in this reading's other counts;
    #: what they are absent from is the companion.
    extended_context_unplaceable: int = 0
    #: The naming profile the readers were run under, and its version. Recorded
    #: rather than assumed at a consumer, because `DEC-43`'s condition (ii) scopes
    #: the one nominal default in this programme to ONE profile id: a consumer that
    #: hard-coded the profile would be asserting which convention was applied instead
    #: of reading it.
    profile_id: str = ""
    profile_version: str = ""
    #: ``ReconstructionReport``'s OWN aggregates, served rather than recomputed
    #: by any client: a client-side recount is a second expression of one number.
    by_concept: Mapping[str, int] = field(default_factory=dict)
    by_mapping_status: Mapping[str, int] = field(default_factory=dict)
    unregistered_concepts: tuple[str, ...] = ()
    #: How many candidates the reconstruction produced, BEFORE
    #: :data:`MAX_CANDIDATES_PER_SESSION`. Equal to the stored count unless the
    #: ceiling was reached, and :attr:`candidates_truncated` says which.
    candidate_total: int = 0
    candidates_truncated: bool = False
    #: Evidence items every reader reported, and every item a reader SUPPRESSED
    #: at its own per-source ceiling. The second is why the first is not a
    #: completeness claim.
    statements_read: int = 0
    statements_suppressed: int = 0
    # --- added 2026-09-22 ------------------------------------------------------
    #: Every convention binding in force for this reading — the build default plus any
    #: rule-backed one — so a surface can show WHICH conventions applied WHERE.
    bindings: tuple[dict, ...] = ()
    #: ``profile id -> how many entries were read under it``, plus ``ambiguous``.
    convention_counts: Mapping[str, int] = field(default_factory=dict)
    #: The rule ids that shaped this reading (bindings, resolutions, assignments).
    rules_applied: tuple[str, ...] = ()
    #: Beamtime-scope element/edge statements the HERFD selector read, verbatim.
    element_evidence: tuple[dict, ...] = ()
    #: What any source said about temperature, VERBATIM. Empty is the normal state and
    #: means the field is Not recorded; nothing here is ever a number.
    temperature_statements: tuple[dict, ...] = ()
    #: Data Quality Notes no measurement could be bound to (no file number in its row).
    unbound_data_quality_notes: tuple[dict, ...] = ()
    #: People named at beamtime scope — inherited by every measurement as provenance.
    beamtime_contributors: tuple[dict, ...] = ()
    #: The acquisition-system knowledge the selector used, with its basis.
    acquisition_system: Mapping[str, Any] = field(default_factory=dict)

    def to_state(self) -> dict:
        return {
            "source_id": self.source_id,
            "root_label": self.root_label,
            "archive_name": self.archive_name,
            "walker_id": self.walker_id,
            "inventory": dict(self.inventory),
            "manifest": [dict(row) for row in self.manifest],
            "reading": [dict(row) for row in self.reading],
            "relationships": dict(self.relationships),
            "units": [u.to_state() for u in self.units],
            "column_readings": [dict(row) for row in self.column_readings],
            "column_readings_dropped": self.column_readings_dropped,
            "column_readings_thinned": self.column_readings_thinned,
            "shared_candidate_ids": list(self.shared_candidate_ids),
            "extended_context_entries": [dict(row) for row in self.extended_context_entries],
            "extended_context_dropped": self.extended_context_dropped,
            "extended_context_thinned": self.extended_context_thinned,
            "extended_context_unplaceable": self.extended_context_unplaceable,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "by_concept": dict(self.by_concept),
            "by_mapping_status": dict(self.by_mapping_status),
            "unregistered_concepts": list(self.unregistered_concepts),
            "candidate_total": self.candidate_total,
            "candidates_truncated": self.candidates_truncated,
            "statements_read": self.statements_read,
            "statements_suppressed": self.statements_suppressed,
            "bindings": [dict(b) for b in self.bindings],
            "convention_counts": dict(self.convention_counts),
            "rules_applied": list(self.rules_applied),
            "element_evidence": [dict(e) for e in self.element_evidence],
            "temperature_statements": [dict(t) for t in self.temperature_statements],
            "unbound_data_quality_notes": [dict(n) for n in self.unbound_data_quality_notes],
            "beamtime_contributors": [dict(c) for c in self.beamtime_contributors],
            "acquisition_system": dict(self.acquisition_system),
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> "ArchiveReading":
        """Rehydrate. Raises on a shape this build cannot read.

        The raise is what :func:`_hydrate_archive_reading` turns into ``None``
        rather than a crash — an archive reading is DERIVED, so an unreadable one
        costs a re-parse and never a scientist's work.
        """
        if not isinstance(state, Mapping):
            raise UnsupportedImport(
                "invalid_entry", "An archive reading must be an object."
            )
        source_id = state.get("source_id")
        if not isinstance(source_id, str):
            raise UnsupportedImport(
                "invalid_entry", "An archive reading is missing its source id."
            )
        units: list[UnitReading] = []
        for row in state.get("units") or []:
            units.append(UnitReading.from_state(row))
        return cls(
            source_id=source_id,
            root_label=state.get("root_label")
            if isinstance(state.get("root_label"), str)
            else "",
            archive_name=state.get("archive_name")
            if isinstance(state.get("archive_name"), str)
            else "",
            walker_id=state.get("walker_id")
            if isinstance(state.get("walker_id"), str)
            else "",
            inventory=dict(state.get("inventory"))
            if isinstance(state.get("inventory"), Mapping)
            else {},
            manifest=tuple(
                dict(row) for row in (state.get("manifest") or []) if isinstance(row, Mapping)
            )
            if isinstance(state.get("manifest"), list)
            else (),
            reading=tuple(
                dict(row) for row in (state.get("reading") or []) if isinstance(row, Mapping)
            )
            if isinstance(state.get("reading"), list)
            else (),
            relationships=dict(state.get("relationships"))
            if isinstance(state.get("relationships"), Mapping)
            else {},
            units=tuple(units),
            # READ, NOT REFUSED, exactly as every other persisted collection here is:
            # a malformed row in a document a reader did not write must not make the
            # session unreadable to the person whose it is.
            column_readings=tuple(
                dict(row)
                for row in (state.get("column_readings") or [])
                if isinstance(row, Mapping)
            )
            if isinstance(state.get("column_readings"), list)
            else (),
            column_readings_dropped=state.get("column_readings_dropped")
            if isinstance(state.get("column_readings_dropped"), int)
            and not isinstance(state.get("column_readings_dropped"), bool)
            else 0,
            shared_candidate_ids=tuple(
                cid
                for cid in (state.get("shared_candidate_ids") or [])
                if isinstance(cid, str)
            )
            if isinstance(state.get("shared_candidate_ids"), list)
            else (),
            # READ, NOT REFUSED, for the reason ``column_readings`` two keys up is:
            # a malformed row in a document a reader did not write must not make
            # the session unreadable to the person whose it is.
            extended_context_entries=tuple(
                dict(row)
                for row in (state.get("extended_context_entries") or [])
                if isinstance(row, Mapping)
            )
            if isinstance(state.get("extended_context_entries"), list)
            else (),
            extended_context_dropped=state.get("extended_context_dropped")
            if isinstance(state.get("extended_context_dropped"), int)
            and not isinstance(state.get("extended_context_dropped"), bool)
            else 0,
            # A SESSION WRITTEN BEFORE THIS FIELD EXISTED HYDRATES TO 0, and 0 is the
            # honest value rather than a lossy default: such a document's whole dropped
            # count is in `extended_context_dropped`, where it was recorded under the
            # union meaning. It cannot be split retroactively — the causes were never
            # stored separately — and inventing a split here would be a guess (§5). A
            # session is re-parsed rather than migrated, which `ArchiveReading.from_state`
            # already relies on: an unreadable one "costs a re-parse and never a
            # scientist's work".
            extended_context_thinned=state.get("extended_context_thinned")
            if isinstance(state.get("extended_context_thinned"), int)
            and not isinstance(state.get("extended_context_thinned"), bool)
            else 0,
            extended_context_unplaceable=state.get("extended_context_unplaceable")
            if isinstance(state.get("extended_context_unplaceable"), int)
            and not isinstance(state.get("extended_context_unplaceable"), bool)
            else 0,
            profile_id=state.get("profile_id")
            if isinstance(state.get("profile_id"), str)
            else "",
            profile_version=state.get("profile_version")
            if isinstance(state.get("profile_version"), str)
            else "",
            by_concept={
                k: v
                for k, v in (state.get("by_concept") or {}).items()
                if isinstance(k, str) and _as_count(v) is not None
            }
            if isinstance(state.get("by_concept"), Mapping)
            else {},
            by_mapping_status={
                k: v
                for k, v in (state.get("by_mapping_status") or {}).items()
                if isinstance(k, str) and _as_count(v) is not None
            }
            if isinstance(state.get("by_mapping_status"), Mapping)
            else {},
            unregistered_concepts=tuple(
                c
                for c in (state.get("unregistered_concepts") or [])
                if isinstance(c, str)
            )
            if isinstance(state.get("unregistered_concepts"), list)
            else (),
            candidate_total=_as_count(state.get("candidate_total")) or 0,
            candidates_truncated=state.get("candidates_truncated") is True,
            statements_read=_as_count(state.get("statements_read")) or 0,
            statements_suppressed=_as_count(state.get("statements_suppressed")) or 0,
            column_readings_thinned=_as_count(state.get("column_readings_thinned")) or 0,
            bindings=_mapping_rows(state.get("bindings")),
            convention_counts={
                k: v
                for k, v in (state.get("convention_counts") or {}).items()
                if isinstance(k, str) and _as_count(v) is not None
            }
            if isinstance(state.get("convention_counts"), Mapping)
            else {},
            rules_applied=tuple(
                r for r in (state.get("rules_applied") or []) if isinstance(r, str)
            )
            if isinstance(state.get("rules_applied"), list)
            else (),
            element_evidence=_mapping_rows(state.get("element_evidence")),
            temperature_statements=_mapping_rows(state.get("temperature_statements")),
            unbound_data_quality_notes=_mapping_rows(state.get("unbound_data_quality_notes")),
            beamtime_contributors=_mapping_rows(state.get("beamtime_contributors")),
            acquisition_system=dict(state.get("acquisition_system"))
            if isinstance(state.get("acquisition_system"), Mapping)
            else {},
        )

    # -- derived ------------------------------------------------------------

    def run_candidate_units(self) -> tuple[UnitReading, ...]:
        """The units a Run may be created from. **Alignment and standards are not.**

        Filtered on :attr:`UnitReading.run_candidate`, which is
        ``MeasurementUnit.run_candidate`` carried across — so this cannot
        disagree with the layer that decided it.
        """
        return tuple(u for u in self.units if u.run_candidate)

    def unit_of_candidate(self, candidate_id: object) -> UnitReading | None:
        """Which measurement produced this candidate, or ``None``.

        ``None`` for a shared (beamtime-scope) candidate and for anything the
        fixture provider built, both of which belong to no measurement.
        """
        for unit in self.units:
            if candidate_id in unit.candidate_ids:
                return unit
        return None

    def by_source_type(self) -> dict[str, int]:
        """``source_type -> accepted entry count``, counted from :attr:`manifest`.

        **The digest's core content, and it is COUNTED rather than declared.**
        ``SourceRecord`` carries no ``source_type`` — classification is
        ``bl15.classify``'s and lives nowhere on the record — so without this the
        archive-wide "how many scans, how many macros, how many notes" figures
        would not be derivable from anything on the wire, and a surface would be
        tempted toward a literal.
        """
        out: dict[str, int] = {}
        for row in self.manifest:
            source_type = row.get("source_type")
            if isinstance(source_type, str):
                out[source_type] = out.get(source_type, 0) + 1
        return dict(sorted(out.items()))

    def by_confidence(self) -> dict[str, int]:
        """``classification confidence -> count``. Counted, never declared.

        Served beside :meth:`by_source_type` because a path-confidence
        classification is a lead and a content-confidence one is a reading of the
        file's own bytes, and a scientist deciding what to correct needs to know
        which they are looking at.
        """
        out: dict[str, int] = {}
        for row in self.manifest:
            confidence = row.get("confidence")
            if isinstance(confidence, str):
                out[confidence] = out.get(confidence, 0) + 1
        return dict(sorted(out.items()))

    def partial_reading_count(self) -> int:
        """How many sources were read PARTIALLY. Read from the reading rows.

        A reader's evidence list can be a partial reading —
        ``bl15.evidence.MAX_EVIDENCE_PER_SOURCE`` records one real file
        suppressing ~41,000 statements — so a count of statements is never a
        completeness claim and this is the number that says so.
        """
        return sum(1 for row in self.reading if row.get("partial") is True)

    def refused_reading_count(self) -> int:
        """How many sources a reader declined WHOLE, with nothing read."""
        return sum(
            1 for row in self.reading if isinstance(row.get("refused_reason"), str)
        )


def _run_label_for(unit, tokens: Sequence[tuple[str, str]]) -> str:
    """The label a Run created from ``unit`` carries. **Verbatim tokens only.**

    ``<legacy>`` first, because the registry marks the legacy number
    ``not_expressible`` and records that it is *"the handle they already use"* —
    so it is the scientist's own identifier for this measurement and belongs at
    the front of the one string a Runs list shows.

    Then the readable condition, as the SOURCE WROTE IT. ``tokens`` is
    ``(concept, raw_literal)`` in the order the caller read them, and the
    literals are interpolated unchanged: ``after1500Cycling`` is not expanded to
    "After 1500 mV cycling" and ``ffilter35`` is not corrected to "filter 35",
    because writing either would be this module composing scientific prose out of
    a token — a small invention, in the one string a scientist identifies the run
    by. The normalisation exists and travels on the CANDIDATE, where its rule is
    named beside it.

    Bounded to ``routes._MAX_LABEL_BYTES``' 512 characters by construction: the
    caller supplies at most :data:`_LABEL_TOKEN_LIMIT` tokens and each is a
    filename fragment. Truncation is still applied, and it is applied to the
    WHOLE label rather than to a token, so a truncated label never reads as a
    different complete value.
    """
    parts: list[str] = []
    if unit.legacy_number is not None:
        parts.append(f"Legacy {unit.legacy_number}")
    seen: set[str] = set()
    for _concept, literal in tokens:
        text = literal.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        parts.append(text)
        if len(parts) >= _LABEL_TOKEN_LIMIT:
            break
    if not parts:
        # No legacy number and no readable token: the stem IS the only handle the
        # scientist has, so it is used rather than inventing "Run 1" — which
        # `workspace.new_run` would otherwise assign, naming an ordinal this
        # import did not choose.
        parts.append(unit.stem)
    label = " · ".join(parts)
    if len(label) > MAX_LABEL_CHARS:
        label = label[: MAX_LABEL_CHARS - 1].rstrip() + "…"
    return label


#: Most tokens a Run label interpolates, beyond the legacy number. The brief's
#: own example carries eight; this bounds a crafted stem rather than the real
#: convention.
_LABEL_TOKEN_LIMIT = 10

#: Concepts whose literals go in a Run label, in the order a scientist reads
#: them. **The brief's §47 example is the specification** — "Legacy Run/File 44 ·
#: Sample 04 · JK2 · Base · After 1500 mV cycling · Filter 35 · Potential 1.2 V ·
#: New spot" — and this is that ordering expressed as concepts, with the literals
#: left verbatim. A concept the sources did not state simply does not appear; no
#: placeholder is emitted, because "unknown" in a run label is a claim about the
#: measurement.
_LABEL_CONCEPTS: tuple[str, ...] = (
    "sample_or_electrode_number",
    "sample_name",
    "electrolyte_or_medium",
    "cycling_state",
    "before_after_state",
    "filter",
    "potential_magnitude",
    "new_spot",
    "repeat_marker",
    "step_number",
)


def _readers():
    """``source_type -> the reader that reads it``. Built at call time.

    **THE CLASSIFICATION SELECTS THE READER, and nothing here re-decides what a
    file is.** ``bl15.classify`` is content-led and tests ``.mca`` BEFORE the
    ``#F`` branch, for a measured reason (both detector products in the archive
    are SPEC-format dumps, so a content-first order called them acquisitions and
    produced two spurious measurement units). That order is not re-derived here
    and must not be.

    A source type absent from this map has NO reader in this build, which is a
    fact rather than a gap: ``detector_product`` (`.mca`) content is deliberately
    not read, ``processed_spectrum`` and ``unknown`` have no format this
    repository holds a representative example of. Those entries still appear in
    the manifest with their classification, and their reading row says a reader
    was not applied — the same "no source is silently passed over" discipline
    :func:`parse_session` already states per manifest entry.
    """
    from .bl15 import evidence as ev
    from .bl15 import macros, notes, scans, spec

    return {
        ev.SOURCE_TYPE_SPEC_ACQUISITION: spec.read_spec_acquisition,
        ev.SOURCE_TYPE_ALIGNMENT: spec.read_spec_acquisition,
        ev.SOURCE_TYPE_STANDARD_OR_REFERENCE: spec.read_spec_acquisition,
        ev.SOURCE_TYPE_SCAN_EXPORT: scans.read_scan_export,
        ev.SOURCE_TYPE_MACRO: macros.read_macro,
        ev.SOURCE_TYPE_ACQUISITION_METHOD_MACRO: macros.read_macro,
        ev.SOURCE_TYPE_MOTOR_SNAPSHOT_MACRO: macros.read_macro,
        ev.SOURCE_TYPE_SHARED_README: notes.read_shared_readme,
        ev.SOURCE_TYPE_BEAMTIME_NOTES: notes.read_beamtime_notes,
    }


def _inventory_of(root: Path, *, root_label: str):
    """Walk a folder or a ZIP. The suffix decides which, and neither raises.

    ``bl15.archive`` returns an inventory carrying one refusal rather than
    raising for a root that is missing, is a symlink, or is an unopenable ZIP —
    so a scientist who chose the wrong thing gets a readable answer about it.
    """
    from .bl15 import archive

    if root.is_dir():
        return archive.inventory_folder(root, root_label=root_label)
    return archive.inventory_zip(root, root_label=root_label)


def _suppressed_in(skipped: Sequence[Mapping]) -> int:
    """How many statements a reader suppressed at its own per-source ceiling.

    **READ OFF THE SKIP ENTRY, never inferred from ``len(evidence)``.** The
    ceiling entry is the only thing that distinguishes "this file states 1,376
    things" from "this file states 49,000 things and 41,000 of them were not
    reported", and ``bl15._emit`` puts the count there precisely so a consumer
    does not have to guess.
    """
    from .bl15._emit import SKIP_EVIDENCE_CEILING

    total = 0
    for entry in skipped:
        if entry.get("reason") != SKIP_EVIDENCE_CEILING:
            continue
        count = _as_count(entry.get("suppressed_count"))
        if count is not None:
            total += count
    return total


def read_archive(
    source: SourceReference,
    *,
    rules: Sequence[Any] = (),
) -> tuple[ArchiveReading, tuple[SemanticCandidate, ...]]:
    """Walk, classify, read, relate and reconstruct ONE archive source.

    Returns the session's durable memory of the archive and the candidates it
    produced. **Writes nothing** — not a file, not a record, not a draft. The
    caller owns persistence.

    THE CHAIN, in order, with the layer that owns each decision:

    1. ``bl15.archive`` walks the folder or ZIP under its own ceilings, refusing
       per entry (and keeping going) or stopping the walk and saying so.
    2. ``bl15.classify`` decides what each entry IS, from the first 8 KiB of its
       own bytes where they are available and from the path otherwise — and
       reports which, because a path decision is a lead and not a fact.
    3. the reader its classification selects reads it, plus
       ``bl15.filenames``, which reads the stem's tokens under the naming
       convention(s) ``bl15.applicability`` says apply to THAT entry.
    4. ``bl15.relate`` attaches scans, macro declarations, processed products and
       note rows to the acquisition each belongs to, and names what disagrees.
    5. ``bl15.reconstruct`` turns evidence plus structure into candidates.
    6. (2026-09-22) per measurement: the HERFD primary-signal selection
       (``bl15.signals``), a recommendation for each conflict (``bl15.resolution``),
       the Data Quality Notes and the named contributors — each a READING or a
       SUGGESTION, none of them a value.

    ``rules`` are :class:`~isaac_api.convention_rules.ConventionRule` objects in force
    for this reading — the import's own apply-only-here rules and, when the import
    targets an experiment, that experiment's confirmed rules. **Nothing in this
    function selects a convention by who ran a measurement**: bindings select by the
    source's name and classification only.

    **THE ONE THING THIS FUNCTION DECIDES that the layers below do not:** whether
    THIS BUILD has a write route for a candidate's target path. ``bl15.mapping``
    answers the schema question (is there an official path, and is the mapping
    deterministic enough to propose?) and six concepts pass it; three of those
    six land on paths ``routes._proposal_writer_for`` answers ``None`` for. A
    candidate left proposable there would be offered a *Send to Review* control
    the server was always going to refuse, and in the batch operation it would
    refuse the WHOLE batch with ``no_write_path_for_field``. So the writability
    check is applied HERE, at the point the candidate is built, exactly as
    :class:`DeterministicFakeReconstructionProvider` already applies it and with
    the same constant — see :data:`CANDIDATE_NOT_PROPOSABLE_NO_WRITE_PATH`, whose
    wording says the limitation is this build's and never the schema's.
    """
    from . import convention_rules as cr
    from .bl15 import applicability as appl
    from .bl15 import archive, classify
    from .bl15 import evidence as ev
    from .bl15 import filenames, macros, reconstruct as rc, relate as R
    from .bl15 import notes as notes_reader
    from .bl15 import resolution as res
    from .bl15 import signals as sig

    name = source.fixture_name or ""
    root = archive_root_for(name)
    inventory = _inventory_of(root, root_label=source.filename or name)

    bindings = cr.bindings_from(rules)
    readers = _readers()
    classifications: dict[str, classify.Classification] = {}
    evidence_by_source: dict[str, list] = {}
    reading_rows: list[dict] = []
    manifest: list[dict] = []
    internal_declarations: dict[str, str] = {}
    macro_declarations: dict[str, Sequence[str]] = {}
    note_file_numbers: dict[int, list[dict]] = {}
    applicability_by_path: dict[str, Any] = {}
    convention_counts: dict[str, int] = {}
    scan_stats_by_stem: dict[str, list] = {}
    statements_read = 0
    statements_suppressed = 0

    for entry in inventory.entries:
        head, _head_refusal = archive.read_source_head(
            inventory, entry.archive_path, source_root=root
        )
        verdict = classify.classify(entry, head_text=head)
        classifications[entry.archive_path] = verdict
        # WHICH CONVENTION(S) APPLY TO THIS ENTRY, by its own name and classification.
        applies = appl.resolve(
            bindings,
            archive_path=entry.archive_path,
            stem=filenames.stem_of(entry.basename),
            source_type=verdict.source_type,
        )
        applicability_by_path[entry.archive_path] = applies
        for pid in applies.profile_ids:
            convention_counts[pid] = convention_counts.get(pid, 0) + 1
        if applies.ambiguous:
            convention_counts["ambiguous"] = convention_counts.get("ambiguous", 0) + 1
        row_manifest = {
            "archive_path": entry.archive_path,
            "basename": entry.basename,
            "extension": entry.extension,
            "size_bytes": entry.size_bytes,
            "parent_dir": entry.parent_dir,
            "depth": entry.depth,
            # THE MEMBER DIGEST. Computed inside this parse, for structural
            # deduplication, and NEVER published as a manifest `sha256` —
            # see this module's docstring for the corrected claim and the
            # test that makes the distinction mechanical.
            "content_sha256": entry.content_sha256,
            **verdict.to_state(),
        }
        # THE CONVENTION, per row, ONLY WHEN IT IS NOT THE PLAIN BUILD DEFAULT. A
        # 1,192-row manifest carrying the same default binding on every row would add
        # a quarter of a megabyte saying nothing; the absence of the key means "read
        # under the build default", which `bindings` on the reading states once.
        if applies.binding_ids != ("build-default",) or applies.ambiguous or applies.stale_bindings:
            row_manifest["convention"] = {
                "profile_ids": list(applies.profile_ids),
                "binding_ids": list(applies.binding_ids),
                "ambiguous": applies.ambiguous,
                "stale_bindings": list(applies.stale_bindings),
            }
        manifest.append(row_manifest)

        items: list = []
        reader = readers.get(verdict.source_type)
        row: dict = {
            "archive_path": entry.archive_path,
            "source_type": verdict.source_type,
            "parser_id": None,
            "statements_read": 0,
            "statements_suppressed": 0,
            "partial": False,
            "skipped": [],
            "skipped_total": 0,
            "refused_reason": None,
        }
        if reader is None:
            row["refused_reason"] = (
                "This build has no reader for this kind of source, so nothing "
                "was read out of it. It is listed with its classification "
                "rather than passed over."
            )
        else:
            text, refusal = archive.read_source_text(
                inventory, entry.archive_path, source_root=root
            )
            if text is None:
                row["refused_reason"] = (
                    f"The archive would not give up this file's contents: "
                    f"{refusal}. Nothing was read from it."
                )
            else:
                result = reader(entry, text, id_prefix=f"{entry.archive_path}:")
                suppressed = _suppressed_in(result.skipped)
                row.update(
                    {
                        "parser_id": result.parser_id,
                        "statements_read": len(result.evidence),
                        "statements_suppressed": suppressed,
                        # PARTIAL IS ITS OWN FLAG rather than `suppressed > 0`
                        # restated at every consumer. It is the fact a count of
                        # statements cannot carry.
                        "partial": suppressed > 0,
                        # A WINDOW WITH ITS TOTAL BESIDE IT, never a trimmed
                        # list presented as a whole one — see
                        # `MAX_SKIPPED_PER_SOURCE` for the measurement. The ceiling
                        # disclosure is pulled to the FRONT; see
                        # `_skips_ceiling_first`.
                        "skipped": _skips_ceiling_first(result.skipped),
                        "skipped_total": len(result.skipped),
                        "refused_reason": result.refused_reason,
                    }
                )
                statements_suppressed += suppressed
                items.extend(result.evidence)
                for item in result.evidence:
                    if item.concept == ev.CONCEPT_SPEC_FILE_DECLARATION:
                        internal_declarations[entry.archive_path] = item.raw_literal
                    elif item.concept == ev.CONCEPT_NOTE_FILE_NUMBER_ROW:
                        number = _legacy_int(item.raw_literal)
                        if number is not None:
                            note_file_numbers.setdefault(number, []).append(
                                {
                                    "source_path": item.source_path,
                                    "locator": item.locator,
                                    "value": item.raw_literal,
                                }
                            )
                if verdict.source_type in {
                    ev.SOURCE_TYPE_MACRO,
                    ev.SOURCE_TYPE_ACQUISITION_METHOD_MACRO,
                    ev.SOURCE_TYPE_MOTOR_SNAPSHOT_MACRO,
                }:
                    # THE MACRO'S DECLARED TARGETS, IN ORDER, read by `bl15`'s own
                    # function rather than re-parsed here.
                    macro_declarations[entry.archive_path] = macros.newfile_targets(text)
                if verdict.source_type == ev.SOURCE_TYPE_SCAN_EXPORT:
                    # CHANNEL CONTENTS FOR THE HERFD SELECTOR, AGGREGATES ONLY: a total,
                    # a non-zero count and an edge-step significance per candidate
                    # channel. No row value is kept. Bucketed by the scan directory's
                    # stem, the same join `relate` uses to attach the scan.
                    parent = entry.parent_dir.rsplit("/", 1)[-1] if entry.parent_dir else ""
                    if parent.endswith(R.SCAN_DIR_SUFFIX):
                        scan_stats_by_stem.setdefault(
                            parent[: -len(R.SCAN_DIR_SUFFIX)], []
                        ).append(
                            sig.scan_channel_stats(
                                text,
                                scan_path=entry.archive_path,
                                channels=sig.BL152_VORTEX.candidate_channels,
                            )
                        )

        # THE FILENAME IS READ FOR EVERY ENTRY, whatever its classification and
        # whether or not a reader ran, under EACH convention that applies to it. One
        # convention is the normal case and keeps the historical evidence-id prefix,
        # so extended-context entry ids (derived from evidence ids) are stable across
        # this change. Two conventions are an AMBIGUITY: each reading carries its own
        # profile id, and any token they read differently becomes a disagreement.
        for pid in applies.profile_ids:
            prefix = (
                f"filename:{entry.archive_path}:"
                if len(applies.profile_ids) == 1
                else f"filename:{pid}:{entry.archive_path}:"
            )
            tokens = filenames.read_filename(
                entry,
                profile_id=pid,
                source_type=verdict.source_type,
                id_prefix=prefix,
            )
            items.extend(tokens.evidence)
            if tokens.refused_reason is not None:
                # PREPENDED, and the total is bumped with it — see the note on the
                # ceiling disclosure above for why it must survive the window.
                row["skipped"] = [
                    {
                        "reason": "filename_not_read",
                        "locator": "filename",
                        "detail": tokens.refused_reason,
                    }
                ] + list(row["skipped"])[: MAX_SKIPPED_PER_SOURCE - 1]
                row["skipped_total"] = row["skipped_total"] + 1

        row["statements_read"] = len(items)
        statements_read += len(items)
        reading_rows.append(row)
        evidence_by_source[entry.archive_path] = items

    relationships = R.relate(
        entries=inventory.entries,
        classifications={
            path: verdict.source_type for path, verdict in classifications.items()
        },
        internal_declarations=internal_declarations,
        macro_declarations=macro_declarations,
        note_file_numbers=note_file_numbers,
        duplicate_groups=inventory.duplicate_groups,
    )

    report = rc.reconstruct(
        relationships=relationships,
        evidence_by_source=evidence_by_source,
        # ONE SOURCE ID FOR THE WHOLE ARCHIVE, because the archive IS one
        # manifest entry. `reconstruct` documents exactly this case, and the
        # archive path travels in every statement's locator regardless, so
        # provenance never depends on this map.
        source_ids={path: source.source_id for path in evidence_by_source},
    )

    # --- 2026-09-22: the per-measurement semantics -------------------------------
    semantics = _archive_semantics(
        relationships=relationships,
        evidence_by_source=evidence_by_source,
        applicability_by_path=applicability_by_path,
        scan_stats_by_stem=scan_stats_by_stem,
        entries_by_path={e.archive_path: e for e in inventory.entries},
        archive_name=name,
        rules=rules,
    )

    writable = _writable_field_paths()
    candidates: list[SemanticCandidate] = []
    units: list[UnitReading] = []
    candidate_total = 0
    by_stem = relationships.by_stem()
    resolutions = cr.resolutions_by_target(rules)
    evidence_index = _evidence_index(evidence_by_source)
    rules_applied: set[str] = set(semantics["rules_applied"])
    rules_applied.update(b.rule_ref for b in bindings if b.rule_ref)

    for unit_candidates in report.units:
        unit = by_stem.get(unit_candidates.stem)
        bounded: list[SemanticCandidate] = []
        for candidate in unit_candidates.candidates:
            candidate_total += 1
            if len(candidates) + len(bounded) >= MAX_CANDIDATES_PER_SESSION:
                continue
            candidate, derived = _apply_resolution(candidate, resolutions, evidence_index)
            if candidate.resolved_by_rule:
                rules_applied.add(candidate.resolved_by_rule)
            bounded.append(_bound_candidate(candidate, writable))
            if derived is not None and len(candidates) + len(bounded) < MAX_CANDIDATES_PER_SESSION:
                bounded.append(_bound_candidate(derived, writable))
        # (2026-09-23) A value of a measurement that is not a Run has no run to go to,
        # so it is not "ready"; and readings that target ONE field are compared again
        # AFTER resolutions, since a confirmed resolution is itself a reading of it.
        if unit is not None and not unit.run_candidate:
            bounded = [_no_run_for(c) for c in bounded]
        bounded = rc._reconcile_same_field(bounded)
        label_tokens = _label_tokens_for(unit, evidence_by_source)
        per_unit = semantics["units"].get(unit_candidates.stem, {})
        units.append(
            UnitReading(
                stem=unit_candidates.stem,
                acquisition_path=unit.acquisition_path if unit else "",
                source_type=unit.source_type if unit else ev.SOURCE_TYPE_UNKNOWN,
                run_candidate=bool(unit and unit.run_candidate),
                label=_run_label_for(unit, label_tokens) if unit else unit_candidates.stem,
                legacy_number=unit.legacy_number if unit else None,
                group_token=unit.group_token if unit else None,
                scan_count=unit.scan_count if unit else 0,
                source_count=unit.source_count if unit else 0,
                conflict_count=len(unit.conflicts) if unit else 0,
                candidate_ids=tuple(c.candidate_id for c in bounded),
                acquisition_identity=per_unit.get("acquisition_identity", ""),
                legacy_number_shared=bool(per_unit.get("legacy_number_shared")),
                applicability=per_unit.get("applicability", {}),
                signal_selection=per_unit.get("signal_selection"),
                data_quality_notes=tuple(per_unit.get("data_quality_notes", ())),
                contributors=tuple(per_unit.get("contributors", ())),
            )
        )
        candidates.extend(bounded)

    shared_ids: list[str] = []
    for candidate in report.shared:
        candidate_total += 1
        if len(candidates) >= MAX_CANDIDATES_PER_SESSION:
            continue
        candidate, derived = _apply_resolution(candidate, resolutions, evidence_index)
        if candidate.resolved_by_rule:
            rules_applied.add(candidate.resolved_by_rule)
        bounded_shared = _bound_candidate(candidate, writable)
        candidates.append(bounded_shared)
        shared_ids.append(bounded_shared.candidate_id)
        if derived is not None and len(candidates) < MAX_CANDIDATES_PER_SESSION:
            bounded_derived = _bound_candidate(derived, writable)
            candidates.append(bounded_derived)
            shared_ids.append(bounded_derived.candidate_id)

    column_readings, column_capped, column_thinned = _column_readings(evidence_by_source)
    # `DEC-41` LEVEL 4, PRODUCED HERE BECAUSE HERE IS WHERE THE EVIDENCE OBJECTS
    # EXIST. A candidate carries only the three-field `EvidenceStatement` shape
    # (`bl15.reconstruct.statement_for`), so a consumer downstream could not rebuild
    # a companion entry without inventing the determinism, the rule and the profile
    # it dropped. `evidence_by_source` holds the real `SourceEvidence`, so the
    # companion is built from the reading rather than from a projection of it.
    (
        context_entries,
        context_dropped,
        context_thinned,
        context_unplaceable,
    ) = _extended_context_entries(evidence_by_source)
    reading = ArchiveReading(
        source_id=source.source_id,
        root_label=inventory.root_label,
        archive_name=name,
        walker_id=archive.ARCHIVE_WALKER_ID,
        inventory=inventory.to_state(),
        manifest=tuple(manifest),
        reading=tuple(reading_rows),
        relationships=semantics["relationships_state"],
        units=tuple(units),
        column_readings=column_readings,
        column_readings_dropped=column_capped,
        column_readings_thinned=column_thinned,
        shared_candidate_ids=tuple(shared_ids),
        extended_context_entries=context_entries,
        extended_context_dropped=context_dropped,
        extended_context_thinned=context_thinned,
        extended_context_unplaceable=context_unplaceable,
        # THE BUILD-DEFAULT CONVENTION, named for back-compatibility: a consumer that
        # predates per-source applicability reads this. Which convention actually
        # applied to WHICH source is per unit (`UnitReading.applicability`) and per
        # manifest row, and `convention_counts` says how many entries each read.
        profile_id=_archive_profile().profile_id,
        profile_version=_archive_profile().profile_version,
        by_concept=dict(report.by_concept or {}),
        by_mapping_status=dict(report.by_mapping_status or {}),
        unregistered_concepts=tuple(report.unregistered_concepts),
        candidate_total=candidate_total,
        candidates_truncated=candidate_total > len(candidates),
        statements_read=statements_read,
        statements_suppressed=statements_suppressed,
        bindings=tuple(b.to_state() for b in [appl.default_binding(), *bindings]),
        convention_counts=dict(sorted(convention_counts.items())),
        rules_applied=tuple(sorted(r for r in rules_applied if r)),
        element_evidence=tuple(e.to_state() for e in semantics["beamtime_elements"]),
        temperature_statements=tuple(semantics["temperature_statements"]),
        unbound_data_quality_notes=tuple(semantics["unbound_data_quality_notes"]),
        beamtime_contributors=tuple(semantics["beamtime_contributors"]),
        acquisition_system=sig.BL152_VORTEX.to_state(),
    )
    return reading, tuple(candidates)


def _evidence_index(evidence_by_source: Mapping[str, Sequence[Any]]) -> dict:
    """``(concept, statement locator) -> [SourceEvidence]`` — the way back from a
    candidate's three-field supporting statement to the reading it was built from."""
    from .bl15 import reconstruct as rc  # local: keeps import order flexible

    index: dict[tuple[str, str], list] = {}
    for items in evidence_by_source.values():
        for item in items:
            index.setdefault((item.concept, rc.statement_locator(item)), []).append(item)
    return index


def _apply_resolution(
    candidate: SemanticCandidate,
    resolutions: Mapping[str, Any],
    evidence_index: Mapping[tuple[str, str], Sequence[Any]] | None = None,
):
    """``(candidate, derived or None)`` — a confirmed resolution applied to a disagreement.

    THE DISAGREEMENT IS KEPT. The original candidate still carries every competing
    reading and ``proposed_value: None``; it gains ``resolved_by_rule`` so its review
    status reads *resolved*. The chosen value travels on a DERIVED candidate, id
    ``<original>::resolved``. A resolution naming a value no source stated is not
    applied: the scientist resolves BETWEEN readings, they do not invent a new one here.

    THE DERIVED CANDIDATE IS EXACTLY WHAT AN AGREEING CANDIDATE WOULD BE — two
    corrections made 2026-09-22 after an independent review, and together they are the
    guarantee that a resolution opens NO route a value could not already take:

    * **Its value** is :func:`bl15.reconstruct.value_of_reading` over the evidence that
      states the chosen reading — the normalised value when that evidence carries one,
      else the literal exactly as written. The first version regex-coerced the
      comparison string, so ``'060'`` became ``60`` and ``'500 cycles'`` became ``500``.
      When the evidence cannot be found, the chosen literal is kept unchanged.
    * **Its proposability** is the MAPPING REGISTRY's, exactly as for an agreeing
      candidate: a concept the registry does not let become a proposal (``sample_name``
      -> ``sample.material.name``, ``acquisition_method`` -> ``system.technique``,
      ``sample_preparation`` -> ``sample.material.provenance`` …) stays unsendable
      after it is resolved. The first version cleared ``not_proposable_reason`` for any
      field candidate with a path, so resolving a disagreement made those sendable.
      Writability is then applied by :func:`_bound_candidate`, as for every candidate.
    """
    from .bl15 import mapping as mp  # local: keeps import order flexible
    from .bl15 import reconstruct as rc  # local: keeps import order flexible

    rule = resolutions.get(candidate.candidate_id)
    if rule is None or candidate.unresolved_reason is None:
        return candidate, None
    chosen = rule.body.get("chosen_value")
    values = [str(row.get("value")) for row in candidate.disagreement]
    if chosen not in values:
        return candidate, None
    marked = replace(candidate, resolved_by_rule=rule.rule_id)

    stating_items: list = []
    stating_statements: list[dict] = []
    for statement in candidate.supporting_statements:
        key = (statement.get("key"), statement.get("locator"))
        items = [
            item
            for item in (evidence_index or {}).get(key, ())
            if rc.reading_of(item) == chosen
        ]
        if items:
            stating_items.extend(items)
            stating_statements.append(statement)
    value = rc.value_of_reading(stating_items, chosen) if stating_items else None
    if value is None:
        value = chosen

    concept = next(
        (str(s.get("key")) for s in candidate.supporting_statements if s.get("key")),
        candidate.candidate_id.rsplit("::", 1)[-1],
    )
    entry = mp.mapping_for(concept)
    if candidate.kind != CANDIDATE_KIND_FIELD or not candidate.target_field_path:
        not_proposable = (
            candidate.not_proposable_reason or CANDIDATE_NOT_PROPOSABLE_DISAGREEMENT
        )
    elif entry is None:
        not_proposable = (
            "This reading has no entry in the mapping registry, so nothing here can say "
            "whether the official schema has a place for it. Resolving which source is "
            "right does not change that; it is kept as evidence."
        )
    elif not entry.proposable:
        not_proposable = entry.reason
    else:
        not_proposable = None

    derived = SemanticCandidate(
        candidate_id=f"{candidate.candidate_id}::resolved",
        kind=candidate.kind,
        determinism=DETERMINISM_DETERMINISTIC,
        rule=(
            f"Scientist-confirmed resolution (rule {rule.rule_id}, v{rule.version}, "
            f"confirmed {rule.confirmed_utc}, confirmed by {rule.confirmed_by}): "
            f"`{chosen}` chosen from {len(values)} disagreeing readings, each kept as "
            "a source fact. Sending it to review makes it a PROPOSAL; accepting that "
            "proposal is a separate act with its own trusted-actor requirement."
        ),
        supporting_source_ids=candidate.supporting_source_ids,
        supporting_statements=tuple(stating_statements) or candidate.supporting_statements,
        target_field_path=candidate.target_field_path,
        proposed_value=value,
        distinct_sources=candidate.distinct_sources,
        resolved_by_rule=rule.rule_id,
        not_proposable_reason=not_proposable,
    )
    return marked, derived


def _archive_semantics(
    *,
    relationships,
    evidence_by_source: Mapping[str, Sequence],
    applicability_by_path: Mapping[str, Any],
    scan_stats_by_stem: Mapping[str, Sequence],
    entries_by_path: Mapping[str, Any],
    archive_name: str,
    rules: Sequence[Any],
) -> dict:
    """Per-measurement semantics added 2026-09-22. READINGS AND SUGGESTIONS ONLY.

    Returns ``{"units": {stem: {...}}, "relationships_state": {...}, ...}``. Nothing
    here writes, chooses between sources, or makes a value proposable: the HERFD
    selection is labelled non-authoritative, a conflict recommendation is labelled
    non-authoritative, and a Data Quality Note is a verbatim remark.
    """
    from . import convention_rules as cr
    from .bl15 import evidence as ev
    from .bl15 import filenames
    from .bl15 import notes as notes_reader
    from .bl15 import resolution as res
    from .bl15 import signals as sig

    # -- evidence gathered across the archive, once --------------------------------
    beamtime_elements: list = []
    filename_elements: dict[str, list] = {}
    temperature_statements: list[dict] = []
    notes_by_number: dict[int, list[dict]] = {}
    quality_by_number: dict[int, list[dict]] = {}
    unbound_quality: list[dict] = []
    contributors_by_number: dict[int, list[dict]] = {}
    beamtime_contributors: list[dict] = []
    table_row_file: dict[tuple[str, int, int], int] = {}
    procedure_rows: list[tuple[str, tuple[int, int], Any]] = []

    for path in sorted(evidence_by_source):
        for item in evidence_by_source[path]:
            concept = item.concept
            if concept == ev.CONCEPT_ELEMENT:
                if item.source_type == ev.SOURCE_TYPE_SHARED_README:
                    beamtime_elements.append(
                        sig.ElementEvidence(
                            element=str(item.normalized_value or item.raw_literal),
                            source_path=item.source_path,
                            locator=item.locator,
                            role=sig.ELEMENT_ROLE_SHARED_README,
                            rule=sig.RULE_README_ELEMENT,
                        )
                    )
                elif item.parser_id == filenames.PARSER_ID and item.measurement_stem:
                    filename_elements.setdefault(item.measurement_stem, []).append(
                        sig.ElementEvidence(
                            element=str(item.normalized_value or item.raw_literal),
                            source_path=item.source_path,
                            locator=item.locator,
                            role=sig.ELEMENT_ROLE_FILENAME,
                            rule=item.normalization_rule or "read from the filename",
                        )
                    )
            elif concept == ev.CONCEPT_ACQUISITION_METHOD and "`def`" in item.locator:
                found = sig.element_evidence_from_method_symbol(
                    item.raw_literal, source_path=item.source_path, locator=item.locator
                )
                if found is not None:
                    beamtime_elements.append(found)
            elif concept == ev.CONCEPT_TEMPERATURE_STATEMENT:
                temperature_statements.append(
                    {
                        "raw_literal": item.raw_literal,
                        "source_path": item.source_path,
                        "locator": item.locator,
                        "scope": item.scope,
                        # SAID ON THE WIRE: the words are never a number.
                        "converted_to_a_number": False,
                    }
                )
            elif concept == ev.CONCEPT_NOTE_FILE_NUMBER_ROW:
                key = notes_reader.table_row_of(item.locator)
                number = _legacy_int(item.raw_literal)
                if key is not None and number is not None:
                    table_row_file[(item.source_path, key[0], key[1])] = number
            elif concept == ev.CONCEPT_ECHEM_PROCEDURE:
                key = notes_reader.table_row_of(item.locator)
                if key is not None:
                    procedure_rows.append((item.source_path, key, item))
            elif concept == ev.CONCEPT_QUALITY_NOTE:
                number = notes_reader.file_number_of(item.locator)
                row = {
                    "text": item.raw_literal,
                    "source_path": item.source_path,
                    "locator": item.locator,
                    "file_number": number,
                    "label": "Data Quality Note",
                    # NEVER A VERDICT — the domain owner's answer, 2026-09-22.
                    "writes_qc_status": False,
                }
                if number is None:
                    unbound_quality.append(row)
                else:
                    quality_by_number.setdefault(number, []).append(row)
                    notes_by_number.setdefault(number, []).append(row)
            elif concept == ev.CONCEPT_CONTRIBUTOR_STATEMENT:
                value = item.normalized_value if isinstance(item.normalized_value, Mapping) else {}
                person = {
                    "name": value.get("name") or item.raw_literal,
                    "label": value.get("label"),
                    "section": value.get("section"),
                    "source_path": item.source_path,
                    "locator": item.locator,
                    "role": "provenance",
                    # NEVER AN ACTOR, and never a parsing input.
                    "is_actor": False,
                }
                numbers = value.get("file_numbers") or []
                if numbers:
                    for number in numbers:
                        if isinstance(number, int):
                            contributors_by_number.setdefault(number, []).append(
                                {**person, "basis": "named in the notes section that lists this file number"}
                            )
                else:
                    beamtime_contributors.append(
                        {**person, "basis": "named at beamtime scope; inherited by every measurement"}
                    )
    for path, key, item in procedure_rows:
        number = table_row_file.get((path, key[0], key[1]))
        if number is not None:
            notes_by_number.setdefault(number, []).append(
                {"text": item.raw_literal, "source_path": item.source_path, "locator": item.locator}
            )

    # -- per unit -------------------------------------------------------------------
    legacy_counts: dict[int, int] = {}
    for unit in relationships.units:
        if unit.legacy_number is not None:
            legacy_counts[unit.legacy_number] = legacy_counts.get(unit.legacy_number, 0) + 1

    rules_applied: set[str] = set()
    resolutions = cr.resolutions_by_target(rules)
    per_unit: dict[str, dict] = {}
    for unit in relationships.units:
        entry = entries_by_path.get(unit.acquisition_path)
        digest = getattr(entry, "content_sha256", "") if entry is not None else ""
        shared = unit.legacy_number is not None and legacy_counts.get(unit.legacy_number, 0) > 1
        applies = applicability_by_path.get(unit.acquisition_path)
        channels = sig.summarize_channels(scan_stats_by_stem.get(unit.stem, ()))
        elements = tuple(beamtime_elements) + tuple(filename_elements.get(unit.stem, ()))
        assignments, rule_ref = cr.signal_assignments_for(
            rules,
            archive_path=unit.acquisition_path,
            stem=unit.stem,
            source_type=unit.source_type,
        )
        if rule_ref:
            rules_applied.add(rule_ref)
        selection = sig.select_primary_signal(
            channels, elements, confirmed_assignments=assignments, rule_ref=rule_ref
        )
        quality = [
            {**row, "legacy_number_shared": shared}
            for row in quality_by_number.get(unit.legacy_number, ())
        ] if unit.legacy_number is not None else []
        people = [
            {**row, "legacy_number_shared": shared}
            for row in contributors_by_number.get(unit.legacy_number, ())
        ] if unit.legacy_number is not None else []
        people.extend(dict(row) for row in beamtime_contributors)
        per_unit[unit.stem] = {
            "acquisition_identity": f"{archive_name}:{unit.acquisition_path}@{digest}",
            "legacy_number_shared": shared,
            "applicability": applies.to_state() if applies is not None else {},
            "signal_selection": selection.to_state(),
            "data_quality_notes": quality,
            "contributors": people,
        }

    # -- conflicts, annotated with their layers ----------------------------------------
    rel_state = relationships.to_state()
    units_list = list(relationships.units)

    def annotated(conflict, unit):
        recommendation = res.recommend(
            conflict,
            unit=unit,
            units=units_list,
            note_texts_by_number=notes_by_number,
        )
        rule = resolutions.get(res.conflict_id(conflict))
        chosen = rule.body.get("chosen_value") if rule is not None else None
        not_applied = "The chosen value is not one of this conflict's readings."
        if rule is None and unit is not None:
            # A RECURRING resolution: chosen by the MEANING of a source, within the
            # rule's selector, and applied only where exactly one reading has that role.
            rule = cr.recurring_resolution_for(
                rules,
                conflict_kind=conflict.kind,
                archive_path=unit.acquisition_path,
                stem=unit.stem,
                source_type=unit.source_type,
            )
            if rule is not None:
                role = rule.body.get("chosen_source_role")
                matching = [r for r in conflict.readings if res.role_of(r) == role]
                chosen = matching[0].value if len(matching) == 1 else None
                not_applied = (
                    f"This conflict has {len(matching)} reading(s) with the role "
                    f"`{role}`, so the recurring rule cannot say which one it means."
                )
        resolution = None
        if rule is not None:
            valid = chosen is not None and chosen in {r.value for r in conflict.readings}
            resolution = {
                "rule_id": rule.rule_id,
                "rule_version": rule.version,
                "scope": rule.scope,
                "recurring": bool(rule.body.get("conflict_kind")),
                "chosen_value": chosen,
                "chosen_source_role": rule.body.get("chosen_source_role"),
                "confirmed_utc": rule.confirmed_utc,
                "confirmed_by": rule.confirmed_by,
                "confirmed_trust_basis": rule.confirmed_trust_basis,
                "layer": res.LAYER_CONFIRMED_RESOLUTION,
                "applied": valid,
                "not_applied_reason": None if valid else not_applied,
            }
            if valid:
                rules_applied.add(rule.rule_id)
        return res.annotate_conflict(
            conflict, recommendation, resolution if (resolution and resolution["applied"]) else None
        ) | ({"unapplied_resolution": resolution} if resolution and not resolution["applied"] else {})

    for unit_state, unit in zip(rel_state.get("units") or [], units_list):
        unit_state["conflicts"] = [annotated(c, unit) for c in unit.conflicts]
    rel_state["corpus_conflicts"] = [
        annotated(c, None) for c in relationships.corpus_conflicts
    ]
    rel_state["conflict_model"] = {
        "layers": [{"layer": key, "meaning": text} for key, text in res.LAYERS],
        "source_roles": dict(res.ROLE_MEANINGS),
        "source_hierarchy": None,
        "policy": (
            "No universal source hierarchy. Every source is preserved, the "
            "disagreement is shown, and nothing is chosen; ISAAC may add a "
            "non-authoritative recommendation; only a scientist-confirmed resolution "
            "is authoritative, and for a record field it still goes forward as a "
            "proposal."
        ),
    }

    return {
        "units": per_unit,
        "relationships_state": rel_state,
        "beamtime_elements": beamtime_elements,
        "temperature_statements": temperature_statements,
        "unbound_data_quality_notes": unbound_quality,
        "beamtime_contributors": beamtime_contributors,
        "rules_applied": sorted(rules_applied),
    }


def _column_readings(
    evidence_by_source: Mapping[str, Sequence],
) -> tuple[tuple[dict, ...], int, int]:
    """The review surface's five scientific columns, bounded. ``(rows, capped, thinned)``.

    **THE WHOLE EVIDENCE SET IS NOT PERSISTED AND MUST NOT BE** — measured at the real
    corpus's cardinality it is roughly 500,000 items. The review surface does not need it:
    it reads :data:`REVIEW_COLUMN_CONCEPTS`, six of the forty-five, for five columns, and
    only for readings that NAME a measurement. Restricted that way the set is a few per
    unit.

    **The cap is on DISTINCT LITERALS per measurement-and-concept, and that is the whole
    safety argument.** The surface's cell is ``absent`` / ``read`` / ``disputed``, and
    ``disputed`` fires on two or more different literals. A cap on the raw count could
    drop the one reading that differed and turn a disputed cell into a settled one — a
    conflict silently resolved by a payload bound, which is the exact class of defect this
    feature exists to prevent. Keeping the FIRST reading of each distinct literal
    preserves the cell's verdict whatever the corpus does; only corroboration is thinned.

    **TWO COUNTS, NEVER SUMMED — split 2026-09-22, exactly as `CTX-004` split the
    extended-context counter.** ~~One integer counted both, served as
    ``evidence_readings_dropped`` under a comment describing only the dedup~~
    (``docs/session-closure-2026-09-18.md`` §8's residue). ``thinned`` is a repeated
    literal (no distinct reading lost); ``capped`` is a DIFFERENT literal not kept because
    the cell already holds :data:`MAX_DISTINCT_COLUMN_READINGS` — a disputed cell whose
    further readings are not all shown. They mean opposite things to a reader.

    A beamtime-scope reading is excluded because it has no ``measurement_stem``, and the
    surface is explicit that folding one into a unit would invent a relationship
    ``relate`` declined to make.
    """
    seen: dict[tuple[str, str], set[str]] = {}
    rows: list[dict] = []
    capped = 0
    thinned = 0
    for path in sorted(evidence_by_source):
        for item in evidence_by_source[path]:
            if item.concept not in REVIEW_COLUMN_CONCEPTS or not item.measurement_stem:
                continue
            key = (item.measurement_stem, item.concept)
            literals = seen.setdefault(key, set())
            if item.raw_literal in literals:
                thinned += 1
                continue
            if len(literals) >= MAX_DISTINCT_COLUMN_READINGS:
                capped += 1
                continue
            literals.add(item.raw_literal)
            rows.append(item.to_state())
    return tuple(rows), capped, thinned


def _archive_profile():
    """The :class:`bl15.profiles.NamingProfile` the archive readers run under.

    ONE expression of "which convention was applied", so the reading row and any
    consumer that scopes a decision to a profile cannot disagree. ``read_filename``
    is called below with no ``profile_id``, so its default is the answer; reading the
    default here rather than transcribing the id keeps the two in step.
    """
    from .bl15 import profiles

    return profiles.PROFILES[profiles.DEFAULT_PROFILE_ID]


def _extended_context_entries(
    evidence_by_source: Mapping[str, Sequence],
) -> tuple[tuple[dict, ...], int, int, int]:
    """`DEC-41` LEVEL-4 COMPANION ENTRIES FOR THIS ARCHIVE.

    Returns ``(rows, dropped, thinned, unplaceable)`` — three counts, never one.

    **THE PRODUCER `CTX-002` LEFT UNBUILT.** `DEC-41` says a concept with no home at
    levels 1-3 lands in a structured ISAAC Extended Context companion; twelve of the
    forty-five registry concepts are at level 4, none of them is proposable, and
    until this function existed every statement about them was read, reported and
    then had nowhere to go.

    **THE LEVEL IS NEVER CHOSEN HERE.** Each row is built by
    :func:`extended_context.entry_from_source_evidence`, which takes the placement
    and the official path from the registry and has no ``level`` parameter at all —
    so `DEC-41`'s first rule (*never skip a level to reach 4 when a real field
    exists*) is unreachable through this path rather than merely checked in it. This
    function's only judgement is WHICH statements to offer, and it makes that by
    asking the registry for the level: a concept whose ``placement_level`` is 1, 2 or
    3 is passed over, because its information belongs at that level and
    ``check_placement`` would raise if it were recorded here.

    **AN UNEXAMINED CONCEPT IS INCLUDED**, and that is deliberate rather than
    permissive: ``mapping_for`` answering ``None`` means nobody has established a
    home, which is exactly the state level 4 exists for, and
    ``entry_from_source_evidence`` records it with the registry's own "kept as
    evidence" reason.

    **DEDUPLICATED ON ``(concept, source, literal)`` AND NOT ON ``(concept,
    literal)``**, which is the whole safety argument and is
    :func:`_column_readings`' argument transposed.
    ``extended_context.build``'s own docstring says a companion must NOT collapse
    sixteen files each recording one filter index, because that would destroy fifteen
    locators. Keying on the source path preserves every one of those sixteen; what is
    thinned is a literal repeated INSIDE ONE FILE — a SPEC acquisition names its
    motors once per scan, so a 22-scan file states the same value 22 times at 22
    locators inside one document. The FIRST occurrence keeps its locator; a
    disagreement between two files can never be silently settled, because two
    different sources are two different keys.

    The tail is dropped at :data:`MAX_EXTENDED_CONTEXT_ENTRIES` and the count is
    returned, so the list is never a trimmed one presented as whole.

    **THREE CAUSES ARE RETURNED SEPARATELY, AND THIS DOCSTRING USED TO REPORT ONLY THE
    FIRST — `CTX-004`, 2026-09-18.** Until this change one integer, ``dropped``, was
    incremented at three sites: the tail cap (what the paragraph above describes, and the
    only one any comment mentioned), the per-source dedup two paragraphs above it, and the
    ``except ValueError`` branch below for a statement this build cannot place at all. The
    third was the one nothing anywhere described.

    They are different facts with different significance — see
    :data:`MAX_EXTENDED_CONTEXT_ENTRIES` for the argument — and a scientist-facing
    disclosure over their sum cannot say which happened. ``dropped`` means statements are
    absent because the archive exceeded a BOUND; ``thinned`` means a literal repeated
    inside one source kept its first locator and lost the later ones, losing no statement;
    ``unplaceable`` means this BUILD could not construct an entry. **They are never summed
    here and must not be summed by a caller.**
    """
    from . import extended_context as ctx
    from .bl15 import mapping as mp

    seen: set[tuple[str, str, str]] = set()
    rows: list[dict] = []
    dropped = 0
    thinned = 0
    unplaceable = 0
    for path in sorted(evidence_by_source):
        for item in evidence_by_source[path]:
            entry = mp.mapping_for(item.concept)
            if entry is not None and entry.placement_level != mp.PLACEMENT_EXTENDED_CONTEXT:
                continue
            key = (item.concept, item.source_path, item.raw_literal)
            if key in seen:
                # THINNED, NOT DROPPED. A duplicate reached before the ceiling and one
                # reached after it are both counted here rather than there, because what
                # happened to this statement is that an identical literal from the same
                # source was already kept — the ceiling is not why it is absent.
                thinned += 1
                continue
            if len(rows) >= MAX_EXTENDED_CONTEXT_ENTRIES:
                dropped += 1
                continue
            seen.add(key)
            try:
                rows.append(
                    ctx.entry_from_source_evidence(
                        item,
                        # DETERMINISTIC, AND THE DETERMINISM IS LOAD-BEARING RATHER
                        # THAN TIDY. ``extended_context`` is inside
                        # ``workspace._authoritative_signature``, and
                        # ``Experiment.add_extended_context_entries`` is idempotent by
                        # ``entry_id`` — so a fresh ULID per import would make every
                        # re-run of the same archive a new revision of the record. The
                        # reader's own ``evidence_id`` is already derived from the
                        # archive path and the locator, so re-reading the same archive
                        # produces the same ids.
                        entry_id=item.evidence_id
                        or f"ctx::{item.source_path}::{item.locator}::{item.concept}",
                        # EXPERIMENT-SCOPED HERE, ALWAYS. At read time no run exists —
                        # runs are created later, by a scientist, on a record this
                        # session does not yet name — so a run-scoped entry would have
                        # no ``run_id`` to carry. The consumer binds run scope where it
                        # can (see ``routes._extended_context_for_record``), and every
                        # entry keeps the source path and locator that identify the
                        # measurement regardless.
                        scope=ctx.SCOPE_EXPERIMENT,
                    ).to_state()
                )
            except ValueError:
                # A statement this build cannot place is PASSED OVER, never
                # recorded at a level it does not belong to, and never raised out
                # of a parse: ``read_archive`` is a read, and a reading that 500ed
                # over one statement would lose the other thousand. It is not lost
                # either — the statement is still in the reader's evidence and in
                # this reading's own counts.
                #
                # UNPLACEABLE, AND THAT IS A THIRD FACT — `CTX-004`, 2026-09-18. This
                # branch used to increment `dropped` too, so ONE integer carried the tail
                # cap, the dedup AND this. It is the cause a reader would most want told
                # apart from the other two: it means this build could not construct an
                # entry for a statement the archive made, which is a property of the
                # BUILD rather than of a bound, and no ceiling change or re-import would
                # alter it.
                unplaceable += 1
                seen.discard(key)
    return tuple(rows), dropped, thinned, unplaceable


def _label_tokens_for(
    unit, evidence_by_source: Mapping[str, Sequence]
) -> list[tuple[str, str]]:
    """``(concept, raw_literal)`` for this unit's label, in reading order.

    Drawn from the ACQUISITION's own evidence and deliberately nothing else: a
    label built from a scan child's or a macro's tokens would describe a
    different file. The FIRST literal for each concept wins — the acquisition's
    filename and its internal declaration can disagree, and that disagreement is
    preserved as a conflict CANDIDATE where a scientist decides it; silently
    concatenating both into the label would present an unresolved question as a
    name. The ordering is :data:`_LABEL_CONCEPTS`, so two units with the same
    tokens produce the same label whatever order their readers ran in.
    """
    if unit is None:
        return []
    first: dict[str, str] = {}
    for item in evidence_by_source.get(unit.acquisition_path, ()):
        if item.concept in first:
            continue
        first[item.concept] = item.raw_literal
    return [
        (concept, first[concept]) for concept in _LABEL_CONCEPTS if concept in first
    ]


def _legacy_int(text: object) -> int | None:
    """A note row's file number as an integer, or ``None``. Never raises.

    ``relate`` keys note rows by the legacy number, which is an ``int``; a row
    whose cell is not one is dropped from THAT index and is still present in the
    reader's evidence, so nothing is lost — only the note-versus-filesystem
    cross-reference is unavailable for it.
    """
    if not isinstance(text, str):
        return None
    try:
        return int(text.strip())
    except ValueError:
        return None


def _bound_candidate(
    candidate: SemanticCandidate, writable: frozenset[str]
) -> SemanticCandidate:
    """Window the statements, and apply THIS BUILD's writability check.

    Two changes, and neither invents anything:

    * the supporting-statement list is cut to
      :data:`MAX_STATEMENTS_PER_CANDIDATE` and
      :attr:`SemanticCandidate.supporting_statement_total` records the true
      count, so a window is never reported as a whole list;
    * a candidate at a path this build has **no write route for** is marked not
      proposable with :data:`CANDIDATE_NOT_PROPOSABLE_NO_WRITE_PATH` — which is
      a statement about this build and explicitly not about the official schema.

    An existing ``not_proposable_reason`` is never overwritten: the registry's
    own reason for 39 of the 45 concepts, and the disagreement reason, are more
    specific and are what a scientist should read.
    """
    statements = candidate.supporting_statements
    total = len(statements)
    windowed = (
        statements[:MAX_STATEMENTS_PER_CANDIDATE]
        if total > MAX_STATEMENTS_PER_CANDIDATE
        else statements
    )
    reason = candidate.not_proposable_reason
    if (
        reason is None
        and candidate.unresolved_reason is None
        and candidate.kind == CANDIDATE_KIND_FIELD
        and candidate.target_field_path is not None
        and candidate.target_field_path not in writable
    ):
        reason = CANDIDATE_NOT_PROPOSABLE_NO_WRITE_PATH
    # THE ZONE GUARD, applied here as well as in the reconstruction so a DERIVED
    # candidate (a confirmed resolution) or any provider's candidate cannot carry a
    # zone-less time into a UTC field either.
    if (
        reason is None
        and candidate.unresolved_reason is None
        and candidate.kind == CANDIDATE_KIND_FIELD
        and not is_zoned_utc_value(candidate.target_field_path, candidate.proposed_value)
    ):
        reason = CANDIDATE_NOT_PROPOSABLE_LOCAL_TIME
        # …and it carries no value, exactly like the reconstruction's own zone-less
        # candidate, so a resolved one and an agreeing one never differ.
        candidate = replace(candidate, proposed_value=None)
    variation = candidate.variation
    variation_total = candidate.variation_total
    if len(variation) > MAX_VARIATION_ROWS:
        variation_total = len(variation)
        variation = variation[:MAX_VARIATION_ROWS]
    return replace(
        candidate,
        supporting_statements=windowed,
        supporting_statement_total=total if total > len(windowed) else None,
        not_proposable_reason=reason,
        variation=variation,
        variation_total=variation_total,
    )


# --- the import session -------------------------------------------------------

#: The workflow, in order, as the product states it. ONE list, so the surface and
#: the server cannot disagree about what the steps are or what they are called.
WORKFLOW_STEPS: tuple[tuple[str, str], ...] = (
    ("new_import", "New Import"),
    ("sources", "Sources"),
    ("parse", "Parse"),
    ("reconstruct", "Reconstruct"),
    ("review", "Review"),
    ("add_to_experiments", "Add to Experiments"),
)

#: The step that is NOT BUILT, named in the same list the surface renders from so
#: it cannot be shown as available.
#:
#: **THERE IS NO LONGER ONE (2026-09-15), AND THE MECHANISM IS KEPT RATHER THAN
#: DELETED.** ``HIST-005`` shipped: ``POST /api/imports/{id}/add-to-experiment``
#: sends every proposable candidate to review on one record in one write, so
#: ``add_to_experiments`` is built and every workflow row now reports
#: ``built: true`` with no disclosure. The constant stays because it is how a
#: future step declares itself unbuilt in the SAME list the surface renders from
#: — the property that kept the old surface honest — and because deleting
#: it would let the next unbuilt step be shown as available by omission.
UNBUILT_STEP: str | None = None

#: What an unbuilt step would say instead of offering an action. Unused while
#: :data:`UNBUILT_STEP` is ``None``; :func:`session_view` reads it only for the
#: step that constant names.
UNBUILT_STEP_DISCLOSURE = (
    "Not built in this build as a single step. Each candidate you send becomes an "
    "ingestion proposal on the record you choose \u2014 or on a new record created "
    "from this import \u2014 and you review it there. Nothing is applied for you."
)
#: WHAT THE RETIRED SENTENCE CLAIMED, kept because the claim was TRUE when it was
#: written and a future reader must be able to see a recorded change rather than a
#: drift. It said the step was "not built in this build as a single step", and it
#: named exactly what was missing: a one-click way to put a whole import in front
#: of a scientist. That is what now exists.
#:
#: The half of the old wording that is STILL exactly true is stated on the batch
#: operation itself rather than repeated here: a candidate becomes a PROPOSAL,
#: reviewed on the record, and nothing is applied for you — the new step writes
#: no scientific value at all.
#:
#: An earlier revision (2026-09-14) had already narrowed the sentence once, when
#: "nothing here creates an experiment for you" became false as the surface gained
#: "New record from this import".

#: The session's durability, stated on the surface rather than assumed. Measured:
#: an import session is one JSON file under the workspace directory, and the
#: deployed pod mounts that directory on an `emptyDir`, so it does not survive a
#: restart. A proposal minted from a candidate is a different matter — it is
#: inside the experiment document, which IS persisted durably.
SESSION_DURABILITY_DISCLOSURE = (
    "An import session is a working area. It is kept in this workspace and is "
    "not part of the durable record store, so a server restart can end it. "
    "Anything you propose onto an experiment is stored with that experiment and "
    "is not affected."
)

#: Where sessions live, ``_``-prefixed so ``workspace._experiment_dirs`` skips it
#: unconditionally and no experiment read can reach it.
IMPORTS_NAMESPACE = "_imports"

#: The per-session state file. Deliberately not named ``experiment.json``.
SESSION_FILE = "session.json"


@dataclass
class ImportSession:
    """ONE assembly of sources, their reading, and what was made of it.

    MUTABLE, unlike the frozen value types above, because it is the aggregate a
    route loads, changes and saves — the arrangement
    :class:`~isaac_api.workspace.Experiment` uses, for its reason.
    """

    import_id: str
    created_utc: str
    updated_utc: str
    label: str
    sources: list[SourceReference] = field(default_factory=list)
    parsed: list[ParsedSource] = field(default_factory=list)
    reconstruction: Reconstruction | None = None
    #: Keys the reconstruction could not map to an official field path, with the
    #: source and locator. Reported, never guessed at.
    unmapped_keys: list[dict] = field(default_factory=list)
    #: ``{candidate_id: {"experiment_id", "proposal_id", "note_id", "proposed_utc"}}``
    #: — what a person has already sent into review. It records that the act
    #: happened; the proposal itself lives on the experiment, which is the only
    #: place a proposal is ever stored.
    proposed: dict[str, dict] = field(default_factory=dict)
    #: RAW entries this build could not read, kept VERBATIM so a save cannot
    #: discard them. ``workspace._hydrate_notes``' arrangement, for its reason.
    unreadable_sources: list = field(default_factory=list)
    unreadable_candidates: list = field(default_factory=list)
    #: What the archive source's parse found, when this bundle holds one. ``None``
    #: for a bundle of pointers and fixtures, which is every session that
    #: existed before :data:`SOURCE_KIND_ARCHIVE` did.
    archive_reading: ArchiveReading | None = None
    #: The candidates the ARCHIVE produced, as distinct from the ones the fixture
    #: provider produced.
    #:
    #: **THE SPLIT EXISTS SO EACH CANDIDATE IS WRITTEN EXACTLY ONCE.**
    #: :attr:`reconstruction` holds the UNION — it is where every consumer
    #: already looks — but :meth:`to_state` writes the archive's under
    #: ``archive_reading`` and the provider's under ``reconstruction``, and
    #: :meth:`from_state` re-composes the union. Persisting the union under
    #: ``reconstruction`` as well would put ~1,000 candidates in one document
    #: twice, and would let the two copies disagree about what was found.
    archive_candidates: list[SemanticCandidate] = field(default_factory=list)
    # --- added 2026-09-22: reviewed convention rules --------------------------
    #: APPLY-ONLY-HERE rules (:data:`convention_rules.SCOPE_IMPORT`). Exactly as durable
    #: as this session — which is to say not durable, and every response says so.
    rules: list = field(default_factory=list)
    #: Raw rule entries this build could not read, kept verbatim.
    unreadable_rules: list = field(default_factory=list)
    #: The experiment this import is being applied to, once a scientist names one by
    #: recording a rule for it. Its confirmed rules are read at parse time.
    target_experiment_id: str | None = None
    #: A SNAPSHOT of the target experiment's active rules as of the last parse, with
    #: the experiment version they were read at — so a GET of this session can show
    #: which confirmed rules shaped the reading without re-reading the experiment.
    experiment_rules: list = field(default_factory=list)
    experiment_rules_version: str | None = None
    #: REUSABLE SUGGESTIONS: convention-scoped rules confirmed on OTHER experiments,
    #: with what they would match here. Never applied until a scientist confirms one
    #: for this experiment — a rule is never promoted across experiments silently.
    reusable_rules: list = field(default_factory=list)
    #: HOW THE REUSABLE SUGGESTIONS WERE GATHERED — the scan's bound and what it left
    #: out, so a short list is never read as "no other experiment has a rule".
    reusable_scan: dict = field(default_factory=dict)

    # -- derived ------------------------------------------------------------

    def source(self, source_id: object) -> SourceReference | None:
        for entry in self.sources:
            if entry.source_id == source_id:
                return entry
        return None

    def candidate(self, candidate_id: object) -> SemanticCandidate | None:
        if self.reconstruction is None:
            return None
        for entry in self.reconstruction.candidates:
            if entry.candidate_id == candidate_id:
                return entry
        return None

    def parsable_sources(self) -> list[SourceReference]:
        """Sources this build can READ. Never a count of the manifest.

        **AN ARCHIVE COUNTS, AND LEAVING IT OUT MADE THE WHOLE FEATURE
        UNREACHABLE.** Added 2026-09-16, found by a browser test rather than by
        review or by any unit test.

        This read ``parser_for(s) is not None``, which asks a narrower question
        than the name: *is there a registered* :class:`SourceParser` *for this*.
        An archive has none by design — it takes :func:`read_archive`, a
        different path with a different output, which is why
        :data:`SOURCE_KIND_ARCHIVE` exists as a third kind at all.

        So ``parse_session`` read an archive perfectly well while this count said
        nothing here could be read, the surface disabled `Read the Sources` on
        that count, and a scientist could add an archive and then do nothing with
        it. Every layer was correct in isolation: the route parsed, the walk
        worked, the review rendered — and the one number gating the button
        described a different question from the one it was asked.

        That is the recurring shape this repository records: **a count not
        derived from what it claims to describe.** It is stated here rather than
        only fixed, because the narrower predicate is the one a reader reaches
        for, and the name will keep inviting it.
        """
        return [
            s
            for s in self.sources
            if parser_for(s) is not None or s.kind == SOURCE_KIND_ARCHIVE
        ]

    def furthest_step(self) -> str:
        """WHICH STEP THIS SESSION HAS REACHED — derived, never stored.

        Derived for ``workspace.Experiment.status``'s reason: a stored step goes
        stale the moment a source is added, and a surface showing a stale step
        tells the reader they are somewhere they are not.

        IT CAN NOW REACH ``add_to_experiments`` (2026-09-15), and the criterion is
        the strict one: EVERY candidate this import can propose has been sent.
        Before ``HIST-005`` shipped, this function could not return that step at
        all and said so — "no session can reach a step this build does not
        have" — which was true, and is why that sentence is quoted here rather
        than deleted.

        "SOME WERE SENT" IS DELIBERATELY NOT ENOUGH. A stepper marking the last
        step reached while three candidates still sat unsent in the review list
        would tell the reader they had finished something they had not. And the
        criterion is re-derived from the CURRENT candidates on every call, so
        adding a source and reconstructing again drops the session back to
        ``review`` rather than leaving a finished-looking stepper over new work.
        """
        if self.proposed:
            sendable = [
                candidate.candidate_id
                for candidate in (
                    self.reconstruction.candidates
                    if self.reconstruction is not None
                    else ()
                )
                if candidate.proposable
            ]
            if sendable and all(cid in self.proposed for cid in sendable):
                return "add_to_experiments"
            return "review"
        # AN ARCHIVE REACHES `reconstruct` AT THE READ, and saying otherwise
        # misreported the workflow. Added 2026-09-16, found by a browser test.
        #
        # For an archive the parse IS the reconstruction: `read_archive` runs the
        # whole chain and produces the candidates, so a session holding one has
        # 101 of them while `self.reconstruction` — the PROVIDER's reconstruction
        # over `self.parsed` — is still `None` and `self.parsed` is empty. The
        # derivation below asked only about those two, so a fully-reconstructed
        # archive session reported `sources`: two steps behind where it was.
        #
        # This is the same shape as `parsable_sources`' defect one method above,
        # and they were found together: a predicate asking about the FIXTURE path
        # while the archive path does the same work somewhere else.
        if self.archive_candidates:
            return "reconstruct"
        if self.reconstruction is not None:
            return "reconstruct"
        if self.parsed:
            return "parse"
        if self.archive_reading is not None:
            # Read, but it produced no candidate — a real outcome for an archive
            # of sources this build can classify and not interpret.
            return "parse"
        if self.sources:
            return "sources"
        return "new_import"

    # -- persistence --------------------------------------------------------

    def to_state(self) -> dict:
        return {
            "import_id": self.import_id,
            "created_utc": self.created_utc,
            "updated_utc": self.updated_utc,
            "label": self.label,
            # The unreadable raw entries are written back out INSIDE these arrays,
            # at the end, which is what makes "no silent discard" hold across a
            # save of a document this build could not fully parse.
            "sources": [s.to_state() for s in self.sources]
            + list(self.unreadable_sources),
            "parsed": [p.to_state() for p in self.parsed],
            # EACH CANDIDATE IS WRITTEN EXACTLY ONCE, and the split is the reason
            # `archive_candidates` exists as its own field. `reconstruction`
            # holds the UNION in memory — every consumer already looks there —
            # so this writes the PROVIDER's half here and the ARCHIVE's half
            # under `archive_reading`, and `from_state` re-composes. Writing the
            # union in both places would put ~1,000 candidates in one document
            # twice and let the copies disagree.
            "reconstruction": (
                None
                if self.reconstruction is None
                else {
                    **self.reconstruction.to_state(),
                    "candidates": [
                        c.to_state()
                        for c in self.reconstruction.candidates
                        if c.candidate_id not in self._archive_candidate_ids()
                    ]
                    + list(self.unreadable_candidates),
                }
            ),
            "archive_reading": (
                None
                if self.archive_reading is None
                else {
                    **self.archive_reading.to_state(),
                    "candidates": [c.to_state() for c in self.archive_candidates],
                }
            ),
            "unmapped_keys": [dict(entry) for entry in self.unmapped_keys],
            "proposed": {cid: dict(row) for cid, row in sorted(self.proposed.items())},
            "rules": [r.to_state() for r in self.rules] + list(self.unreadable_rules),
            "target_experiment_id": self.target_experiment_id,
            "experiment_rules": [dict(r) for r in self.experiment_rules],
            "experiment_rules_version": self.experiment_rules_version,
            "reusable_rules": [dict(r) for r in self.reusable_rules],
            "reusable_scan": dict(self.reusable_scan),
        }

    def _archive_candidate_ids(self) -> frozenset[str]:
        return frozenset(c.candidate_id for c in self.archive_candidates)

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> "ImportSession":
        """Rehydrate. TOTAL for every optional key, strict for identity.

        ``import_id`` and ``created_utc`` are hard reads and this raises without
        them — a document with no id cannot be addressed, so a fail-closed read is
        the only honest one. **Every other key is read with a default**, so a
        session written by an older build hydrates rather than raising, and a
        malformed value is READ rather than refused: §11's rule is that a
        malformed PERSISTED value must not make the reader's session vanish.
        """
        if not isinstance(state, Mapping):
            raise UnsupportedImport("invalid_session", "A session must be an object.")
        import_id = state.get("import_id")
        created = state.get("created_utc")
        if not (isinstance(import_id, str) and isinstance(created, str)):
            raise UnsupportedImport(
                "invalid_session", "A session document is missing its identity."
            )
        sources, unreadable_sources = _hydrate_sources(state.get("sources"))
        session = cls(
            import_id=import_id,
            created_utc=created,
            updated_utc=state.get("updated_utc")
            if isinstance(state.get("updated_utc"), str)
            else created,
            label=state.get("label") if isinstance(state.get("label"), str) else "",
            sources=sources,
            parsed=_hydrate_parsed(state.get("parsed")),
            unmapped_keys=[
                dict(entry)
                for entry in (state.get("unmapped_keys") or [])
                if isinstance(entry, Mapping)
            ]
            if isinstance(state.get("unmapped_keys"), list)
            else [],
            proposed={
                cid: dict(row)
                for cid, row in (state.get("proposed") or {}).items()
                if isinstance(cid, str) and isinstance(row, Mapping)
            }
            if isinstance(state.get("proposed"), Mapping)
            else {},
        )
        session.unreadable_sources = unreadable_sources
        reconstruction, unreadable_candidates = _hydrate_reconstruction(
            state.get("reconstruction")
        )
        session.unreadable_candidates = unreadable_candidates
        reading, archive_candidates = _hydrate_archive_reading(
            state.get("archive_reading")
        )
        session.archive_reading = reading
        session.archive_candidates = archive_candidates
        # THE UNION IS RE-COMPOSED HERE, which is the read half of `to_state`'s
        # write-once split. The archive's candidates come back in the order they
        # were written, appended after the provider's, so `candidates_of` and
        # every propose route see one list exactly as they did before an archive
        # kind existed.
        if reconstruction is not None and archive_candidates:
            reconstruction = replace(
                reconstruction,
                candidates=reconstruction.candidates + tuple(archive_candidates),
            )
        session.reconstruction = reconstruction
        # READ, NOT REFUSED (2026-09-22): a session written before rules existed has
        # none of these keys and hydrates to no rules and no target.
        from . import convention_rules as cr  # local: keeps import order flexible

        session.rules, session.unreadable_rules = cr.hydrate(state.get("rules"))
        target = state.get("target_experiment_id")
        session.target_experiment_id = target if is_record_id(target) else None
        session.experiment_rules = list(_mapping_rows(state.get("experiment_rules")))
        version = state.get("experiment_rules_version")
        session.experiment_rules_version = version if isinstance(version, str) else None
        session.reusable_rules = list(_mapping_rows(state.get("reusable_rules")))
        scan = state.get("reusable_scan")
        session.reusable_scan = dict(scan) if isinstance(scan, Mapping) else {}
        return session


def _hydrate_archive_reading(
    raw: object,
) -> tuple[ArchiveReading | None, list[SemanticCandidate]]:
    """``(reading, its candidates)``. Never raises.

    **AN UNREADABLE ARCHIVE READING IS DROPPED, NOT PRESERVED, and the asymmetry
    is the same one :func:`_hydrate_parsed` already makes.** A reading is
    DERIVED — re-running Parse walks the archive again and recomputes all of it
    from the manifest entry, which IS preserved — so an unreadable one costs a
    recomputation. A source entry and a candidate are authored or judged content
    and are kept verbatim.

    A candidate this build cannot read is dropped for the same reason, and NOT
    kept in ``unreadable_candidates``: that list is written back inside the
    ``reconstruction`` array, and an archive candidate written there would be a
    second copy of something that belongs under ``archive_reading``. Losing one
    costs a re-parse; duplicating it would make the two halves disagree.
    """
    if not isinstance(raw, Mapping):
        return None, []
    try:
        reading = ArchiveReading.from_state(raw)
    except (UnsupportedImport, TypeError, ValueError, AttributeError):
        return None, []
    candidates: list[SemanticCandidate] = []
    for entry in raw.get("candidates") or []:
        try:
            candidates.append(SemanticCandidate.from_state(entry))
        except (UnsupportedImport, TypeError, ValueError, AttributeError):
            continue
    return reading, candidates


def _hydrate_sources(raw: object) -> tuple[list[SourceReference], list]:
    """``(sources, unreadable raw entries)``. Never raises, AND NEVER DISCARDS.

    The pair shape is ``workspace._hydrate_notes``', for its reason: an entry this
    build cannot read is kept verbatim and written back on the next save, so a
    later build that understands it reads it normally. A ``raw`` that is not a
    list yields no sources at all — there is nothing to iterate — rather than one
    entry per character, which is what ``enumerate("abc")`` would have invented.
    """
    if not isinstance(raw, list):
        return [], []
    out: list[SourceReference] = []
    unreadable: list = []
    for entry in raw:
        try:
            out.append(SourceReference.from_state(entry))
        except (UnsupportedImport, TypeError, ValueError, AttributeError):
            unreadable.append(entry)
    return out, unreadable


def _hydrate_parsed(raw: object) -> list[ParsedSource]:
    """Parse results, tolerantly. A malformed entry is DROPPED, not preserved.

    **The one place this module drops rather than preserves, and the asymmetry is
    deliberate.** A parse result is DERIVED — re-running Parse recomputes it from
    the sources, which are preserved — so an unreadable one costs a recomputation.
    A source entry and a candidate are authored or judged content and are
    preserved verbatim.
    """
    if not isinstance(raw, list):
        return []
    out: list[ParsedSource] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        source_id = entry.get("source_id")
        parser_id = entry.get("parser_id")
        if not (isinstance(source_id, str) and isinstance(parser_id, str)):
            continue
        statements = []
        for row in entry.get("statements") or []:
            if (
                isinstance(row, Mapping)
                and isinstance(row.get("key"), str)
                and isinstance(row.get("value"), str)
                and isinstance(row.get("locator"), str)
            ):
                statements.append(
                    EvidenceStatement(
                        key=row["key"], value=row["value"], locator=row["locator"]
                    )
                )
        out.append(
            ParsedSource(
                source_id=source_id,
                parser_id=parser_id,
                filename=entry.get("filename")
                if isinstance(entry.get("filename"), str)
                else "",
                statements=tuple(statements),
                skipped=tuple(
                    dict(row)
                    for row in (entry.get("skipped") or [])
                    if isinstance(row, Mapping)
                ),
            )
        )
    return out


def _hydrate_reconstruction(raw: object) -> tuple[Reconstruction | None, list]:
    """``(reconstruction, unreadable raw candidates)``. Never raises."""
    if not isinstance(raw, Mapping):
        return None, []
    provider_id = raw.get("provider_id")
    at = raw.get("reconstructed_utc")
    if not (isinstance(provider_id, str) and isinstance(at, str)):
        return None, []
    candidates: list[SemanticCandidate] = []
    unreadable: list = []
    for entry in raw.get("candidates") or []:
        try:
            candidates.append(SemanticCandidate.from_state(entry))
        except (UnsupportedImport, TypeError, ValueError, AttributeError):
            unreadable.append(entry)
    return (
        Reconstruction(
            provider_id=provider_id,
            candidates=tuple(candidates),
            reconstructed_utc=at,
            # NOT READ FROM THE DOCUMENT. `applied` is a constant of this build,
            # so a persisted `true` must not be able to make a surface say a
            # reconstruction was applied. It is recomputed, never hydrated.
            applied=RECONSTRUCTION_APPLIED,
        ),
        unreadable,
    )


# --- the store ----------------------------------------------------------------


def imports_root(session_id: str | None = None) -> Path:
    """``<scope_root>/_imports``. The scope boundary is ``ws.scope_root``'s."""
    return ws.scope_root(session_id) / IMPORTS_NAMESPACE


def _session_dir(import_id: str, session_id: str | None) -> Path:
    """The directory of one import session, after validating the id.

    **``is_record_id`` IS THE TRAVERSAL BOUNDARY**, and it is the truth core's
    predicate rather than a second copy of it: ``\\A[0-9A-Z]{26}\\Z`` admits no
    ``.``, no ``/``, no ``\\`` and no NUL, so no value a caller supplies can name
    a path outside this directory. Every path in this module is built here, so
    the check happens exactly once.
    """
    if not is_record_id(import_id):
        raise UnsupportedImport(
            "invalid_import_id",
            "That is not an import session id this build can address.",
        )
    return imports_root(session_id) / import_id


def load_session(import_id: str, *, session_id: str | None = None) -> ImportSession | None:
    """Read one session, or ``None`` if it does not exist or cannot be read.

    ``None`` rather than a raise for an unreadable document, so one corrupt file
    cannot take down a list read — the shape ``_readable_experiment_state``
    settled on after a malformed draft was measured to 500 the whole My
    Experiments screen.
    """
    try:
        path = _session_dir(import_id, session_id) / SESSION_FILE
    except UnsupportedImport:
        return None
    if not path.is_file():
        return None
    try:
        return ImportSession.from_state(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, UnsupportedImport):
        return None


def save_session(session: ImportSession, *, session_id: str | None = None) -> None:
    """Persist one session atomically.

    **NO SIGNATURE COMPARISON, and the difference from ``save_versioned`` is
    deliberate.** ``Experiment.save_versioned`` writes nothing when the
    authoritative state is unchanged, because its ``rev`` is a concurrency token
    an ``If-Match`` contract is built on. An import session has no such token and
    serves no ``ETag``: it is a working area, its writes are serialised by
    :func:`import_lock`, and a byte-identical rewrite costs one file write rather
    than a false revision. Adding a token later would mean adding the contract
    that needs it, which is a decision this shell does not take.
    """
    path = _session_dir(session.import_id, session_id) / SESSION_FILE
    ws.atomic_write_text(
        path, json.dumps(session.to_state(), indent=2, ensure_ascii=False) + "\n"
    )


def list_sessions(*, session_id: str | None = None) -> list[ImportSession]:
    """Every readable session in this scope, newest first.

    An unreadable document is SKIPPED rather than raising, for
    :func:`load_session`'s reason — one corrupt file must not empty the list
    screen for every other session.
    """
    root = imports_root(session_id)
    if not root.is_dir():
        return []
    out: list[ImportSession] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or not is_record_id(entry.name):
            continue
        session = load_session(entry.name, session_id=session_id)
        if session is not None:
            out.append(session)
    # `created_utc` descending, then id, so the order is total even when two
    # sessions share a whole-second timestamp.
    return sorted(out, key=lambda s: (s.created_utc, s.import_id), reverse=True)


def delete_session(import_id: str, *, session_id: str | None = None) -> bool:
    """Remove one session's directory. ``True`` if it was there.

    THIS DELETES A WORKING AREA AND NOTHING ELSE. A proposal minted from one of
    its candidates lives on the experiment and is untouched — which is why a
    session is deletable at all while a note and a proposal are not.
    """
    import shutil

    try:
        directory = _session_dir(import_id, session_id)
    except UnsupportedImport:
        return False
    if not directory.is_dir():
        return False
    shutil.rmtree(directory)
    return True


def import_lock(import_id: str, *, session_id: str | None = None):
    """Serialise the read-change-save critical section for one import session.

    ``workspace.record_lock`` REUSED rather than reimplemented, keyed on the
    import id. The two id spaces cannot collide: both come from
    ``new_record_id``, so two distinct ids are two distinct keys, and an import
    id sharing a key with an experiment id would require them to be the same
    ULID. A second lock map would be a second expression of one concurrency
    decision, free to drift from this one.
    """
    return ws.record_lock(import_id, session_id=session_id)


# --- the operations -----------------------------------------------------------


def new_session(*, label: str | None, now_utc: str) -> ImportSession:
    """Mint an empty session. Does not save; saving is the caller's."""
    cleaned = _clean(label, "label", maximum=MAX_LABEL_CHARS, required=False)
    return ImportSession(
        import_id=new_record_id(),
        created_utc=now_utc,
        updated_utc=now_utc,
        label=cleaned or "",
    )


def add_source(
    session: ImportSession,
    *,
    kind: object,
    filename: object = None,
    reference: object = None,
    fixture_name: object = None,
    media_type: object = None,
    size_bytes: object = None,
    sha256: object = None,
    recorded_utc: str,
    now_utc: str,
) -> SourceReference:
    """Add ONE manifest entry, in memory. Opens nothing, fetches nothing, hashes nothing.

    ``sha256`` is validated for SHAPE and never computed —
    :func:`isaac_records.complete.is_sha256_shaped` is IMPORTED rather than
    restated, because a ``$``-anchored second copy of that pattern accepted
    ``"9" * 64 + "\\n"`` once already and this repository keeps a whole module
    (``isaac_records.exactness``) about it.
    """
    if kind not in SOURCE_KINDS:
        raise UnsupportedImport(
            "unrecognized_kind",
            "`kind` must name one of the three kinds of source this build stores.",
            key=kind if isinstance(kind, str) else None,
            allowed=sorted(SOURCE_KINDS),
        )
    if len(session.sources) >= MAX_SOURCES_PER_SESSION:
        raise UnsupportedImport(
            "too_many_sources",
            "This bundle already holds the most sources one session may hold.",
            sources=len(session.sources),
            maximum=MAX_SOURCES_PER_SESSION,
        )

    digest = _clean(sha256, "sha256", maximum=64, required=False)
    if digest is not None and not is_sha256_shaped(digest):
        raise UnsupportedImport(
            "malformed_sha256",
            (
                "`sha256` must be 64 lowercase hex characters. This build checks "
                "the SHAPE only: it records the digest you supply and never "
                "computes one, so no surface may say a digest was verified."
            ),
            key="sha256",
        )
    size = None
    if size_bytes is not None:
        if (
            not isinstance(size_bytes, int)
            or isinstance(size_bytes, bool)
            or size_bytes < 0
        ):
            raise UnsupportedImport(
                "wrong_type",
                "`size_bytes` must be a non-negative whole number of bytes.",
                key="size_bytes",
            )
        size = size_bytes
    media = _clean(media_type, "media_type", maximum=MAX_MEDIA_TYPE_CHARS, required=False)

    if kind == SOURCE_KIND_SYNTHETIC_FIXTURE:
        name = _clean(fixture_name, "fixture_name", maximum=200, required=True)
        # Raises `unknown_fixture` for anything off the allowlist, which is also
        # the traversal boundary for this branch.
        fixture_path(name)
        entry = SourceReference(
            source_id=new_record_id(),
            kind=kind,
            filename=name,
            # THE REFERENCE IS THE FIXTURE'S REPO-RELATIVE PATH, not an absolute
            # one. An absolute path would carry this machine's home directory into
            # a stored document, which is the class of leak
            # `scripts/build_memory_snapshot.py` redacts for.
            reference=f"tests/fixtures/historical_import/{name}",
            parse_state=PARSE_STATE_UNPARSED,
            provenance=_provenance(recorded_utc, kind),
            media_type=media,
            size_bytes=size,
            sha256=digest,
            fixture_name=name,
        )
    elif kind == SOURCE_KIND_ARCHIVE:
        # `fixture_name` CARRIES THE ARCHIVE'S NAME, reusing the field rather
        # than adding a fourth "which committed thing is this" key. Both kinds
        # answer the same question — WHICH committed artifact, chosen from an
        # allowlist this module owns — and a second field would be a second
        # place for a hydration path to have to look.
        name = _clean(fixture_name, "fixture_name", maximum=200, required=True)
        # ONE ARCHIVE PER BUNDLE, ENFORCED RATHER THAN ASSERTED. `remove_source`'s own
        # comment relies on "a bundle may hold at most one archive" to justify dropping
        # the reading unconditionally — and NOTHING CHECKED IT. Independent review
        # measured the consequence: two archive entries were accepted, BOTH manifest rows
        # reported `parse_state: parsed`, row 0's detail claimed N files inventoried and
        # M candidates found, and `session.archive_reading` belonged to the SECOND source
        # only, because `parse_session` rebinds it per archive and the last one wins. So
        # the first row described a reading that no longer existed — a count not derived
        # from what it claims to describe.
        #
        # Harmless only while the allowlist holds one name, which makes this exactly the
        # kind of latent claim that goes false on a one-line change the module's own
        # design anticipates. Refused here rather than accumulated in `parse_session`,
        # because a session with two readings has no single `archive_reading` to serve and
        # every consumer would need a branch that has to stay correct.
        existing = [s for s in session.sources if s.kind == SOURCE_KIND_ARCHIVE]
        if existing:
            raise UnsupportedImport(
                error="archive_already_in_bundle",
                message=(
                    "This import already holds an archive, and a bundle may hold one. "
                    "Its reading is the session's whole memory of the corpus, so a "
                    "second archive would replace the first while the first's manifest "
                    "entry went on claiming it had been walked. Remove the existing "
                    "archive first, or start a new import."
                ),
                existing_source_id=existing[0].source_id,
            )
        # Raises `unknown_archive` for anything off the allowlist, which is also
        # the traversal boundary for this branch — and the same branch refuses a
        # name that merely looks plausible, so this cannot probe the filesystem.
        archive_root_for(name)
        entry = SourceReference(
            source_id=new_record_id(),
            kind=kind,
            filename=_clean(
                filename, "filename", maximum=MAX_FILENAME_CHARS, required=False
            )
            or name,
            # REPO-RELATIVE, never absolute, for the fixture branch's reason: an
            # absolute path carries this machine's home directory into a stored
            # document. A STAGED archive records its namespaced name, never the
            # staging directory's path, for the same reason.
            reference=ARCHIVE_FIXTURES.get(name, name),
            parse_state=PARSE_STATE_UNPARSED,
            provenance=_provenance(
                recorded_utc, kind, staged=name not in ARCHIVE_FIXTURES
            ),
            media_type=media,
            size_bytes=size,
            # **WHAT THE SCIENTIST SAID, AND NOTHING ELSE.** The parse computes a
            # digest for every MEMBER of this archive — it has to, or the corpus
            # doubles — and not one of them is ever written here. See the module
            # docstring's corrected claim.
            sha256=digest,
            fixture_name=name,
        )
    else:
        entry = SourceReference(
            source_id=new_record_id(),
            kind=kind,
            filename=_clean(
                filename, "filename", maximum=MAX_FILENAME_CHARS, required=True
            )
            or "",
            reference=_clean(
                reference, "reference", maximum=MAX_REFERENCE_CHARS, required=True
            )
            or "",
            # THE PARSE STATE IS DECIDED HERE AND NOT LEFT `unparsed`, because
            # "not parsed yet" and "cannot be parsed by this build" are different
            # facts and a reader waiting for the first would wait forever.
            parse_state=PARSE_STATE_NO_CONTENT_PATH,
            parse_detail=NO_CONTENT_PATH_DETAIL,
            provenance=_provenance(recorded_utc, kind),
            media_type=media,
            size_bytes=size,
            sha256=digest,
        )
    session.sources.append(entry)
    session.updated_utc = now_utc
    return entry


#: What ``provenance`` records, and what it deliberately does not.
#:
#: **NO ACTOR IS STAMPED.** ``CLAUDE.md`` §15 records that server-stamping the
#: canonical username is authorized *provided the request's identity was
#: established through the trusted authentication boundary*, and that no such
#: boundary exists in this build — so the actor seam stays unset, exactly as
#: ``record_attribution`` leaves ``attribution.uploaded_by`` unset. Writing
#: "recorded by <client-supplied name>" would be a forgeable claim in a
#: provenance record, which is worse than no claim.
PROVENANCE_NO_ACTOR = "no_trusted_identity_established"


def _provenance(recorded_utc: str, kind: str, *, staged: bool = False) -> dict:
    out = {
        "recorded_utc": recorded_utc,
        "recorded_by": PROVENANCE_NO_ACTOR,
        "recorded_how": _RECORDED_HOW_STAGED if staged else _RECORDED_HOW[kind],
        # TRUE FOR BOTH READ KINDS. An archive is read — that is its whole
        # purpose — and the provenance says so rather than leaving a reader to
        # infer it from the kind.
        "bytes_read_by_this_application": kind
        in {SOURCE_KIND_SYNTHETIC_FIXTURE, SOURCE_KIND_ARCHIVE},
    }
    if staged:
        # SAID, not implied, and present ONLY for a staged archive so every other
        # provenance record is byte-identical to what it was: a staged archive is
        # bytes an operator placed on the server under `historical_file_ingestion`,
        # never a committed fixture.
        out["staged"] = True
    return out


#: One sentence per kind, in ONE place. Previously a two-branch conditional
#: inside :func:`_provenance`, which a third kind would have made read as "a
#: person chose this committed synthetic fixture" for an archive.
_RECORDED_HOW: Mapping[str, str] = {
    SOURCE_KIND_REFERENCE: (
        "a person entered this reference on the Historical Import surface"
    ),
    SOURCE_KIND_SYNTHETIC_FIXTURE: "a person chose this committed synthetic fixture",
    SOURCE_KIND_ARCHIVE: (
        "a person chose this committed archive, and this build walked it"
    ),
}


#: A staged archive's provenance sentence. Reachable only while the capability is
#: enabled by configuration, which no shipped deployment does (``EXT-13``).
_RECORDED_HOW_STAGED = (
    "a person chose an archive an operator placed in the server-side staging "
    "directory (historical_file_ingestion, enabled by configuration), and this build "
    "walked it"
)


def remove_source(session: ImportSession, source_id: object, *, now_utc: str) -> bool:
    """Drop one manifest entry, in memory. ``True`` if it was there.

    Any parse result and any reconstruction that cited it are dropped with it,
    because a reading of a bundle the bundle no longer matches is a stale claim,
    and the alternative — keeping candidates whose supporting source is gone —
    would put unsupportable candidates in front of a scientist. What is NOT
    dropped is :attr:`ImportSession.proposed`: a proposal that was already minted
    exists on an experiment, and forgetting that it was minted would let the same
    candidate be proposed twice.
    """
    entry = session.source(source_id)
    if entry is None:
        return False
    session.sources = [s for s in session.sources if s.source_id != source_id]
    session.parsed = []
    session.reconstruction = None
    session.unreadable_candidates = []
    session.unmapped_keys = []
    # THE ARCHIVE READING GOES WITH IT, for the reason above: it is a reading of
    # a bundle the bundle no longer matches. Dropped unconditionally rather than
    # only when the removed entry WAS the archive, because a bundle may hold at
    # most one archive and the alternative is a branch that has to stay correct.
    #
    # THAT INVARIANT IS NOW ENFORCED IN `add_source` (`archive_already_in_bundle`),
    # 2026-09-16. It was relied on here and checked nowhere, which independent review
    # measured: two archives were accepted and the first manifest row kept reporting a
    # reading the second had replaced.
    session.archive_reading = None
    session.archive_candidates = []
    session.updated_utc = now_utc
    return True


def parse_session(
    session: ImportSession,
    *,
    now_utc: str,
    experiment_rules: Sequence[Any] = (),
    experiment_rules_version: str | None = None,
    reusable_rules: Sequence[Mapping] = (),
    reusable_scan: Mapping | None = None,
) -> list[ParsedSource]:
    """Apply every registered parser to every source that has one. In memory.

    A source with no registered parser is left with the parse state it already
    carries — :data:`PARSE_STATE_NO_CONTENT_PATH` for a pointer — so the
    manifest's own column answers "what parsed and what did not" per entry. **No
    source is silently skipped**: every entry ends in exactly one of the four
    states, and the two that are not ``parsed`` carry a ``parse_detail``.

    **AN ARCHIVE SOURCE TAKES A DIFFERENT PATH, and the difference is what the
    parse RESULT is.** A fixture's parse result is a list of statements; an
    archive's is an INVENTORY — 1,192 entries, their classifications, what each
    reader read, the relationships between them and the candidates that follow.
    So :func:`read_archive` runs the whole ``bl15`` chain (walk, classify, read,
    relate, reconstruct) and its output lands on
    :attr:`ImportSession.archive_reading` rather than in ``session.parsed``.
    ``MAX_SOURCES_PER_SESSION`` is untouched and still bounds MANIFEST ENTRIES;
    an archive's members are bounded by its own
    :class:`~isaac_api.bl15.inventory.ArchiveLimits`.

    The candidates it produces are held on :attr:`ImportSession.archive_candidates`
    and reach :attr:`ImportSession.reconstruction` when :func:`reconstruct_session`
    composes them — so Parse and Reconstruct remain the two steps the workflow
    says they are, and a session that has parsed but not reconstructed reports
    ``parse`` rather than looking finished.
    """
    parsed: list[ParsedSource] = []
    rewritten: list[SourceReference] = []
    archive_reading: ArchiveReading | None = None
    archive_candidates: list[SemanticCandidate] = []
    # THE RULES IN FORCE FOR THIS READING: this import's own apply-only-here rules,
    # plus the target experiment's confirmed ones (read by the caller, which owns the
    # experiment lock). Rules from OTHER experiments are never applied here — they are
    # carried as reusable suggestions only.
    from . import convention_rules as cr  # local: keeps import order flexible

    in_force = cr.active_rules(list(session.rules) + list(experiment_rules))
    session.experiment_rules = [r.to_state() for r in cr.active_rules(experiment_rules)]
    session.experiment_rules_version = experiment_rules_version
    session.reusable_rules = [dict(r) for r in reusable_rules]
    session.reusable_scan = dict(reusable_scan or {})
    for source in session.sources:
        if source.kind == SOURCE_KIND_ARCHIVE:
            try:
                archive_reading, minted = read_archive(source, rules=in_force)
            except UnsupportedImport as refusal:
                rewritten.append(
                    replace(
                        source,
                        parse_state=PARSE_STATE_FAILED,
                        parse_detail=refusal.message,
                    )
                )
                continue
            archive_candidates = list(minted)
            rewritten.append(
                replace(
                    source,
                    parse_state=PARSE_STATE_PARSED,
                    parse_detail=(
                        f"Walked by {archive_reading.walker_id}: "
                        f"{archive_reading.inventory.get('entry_count', 0)} file(s) "
                        f"inventoried, "
                        f"{len(archive_reading.inventory.get('refused') or ())} "
                        f"refused, "
                        f"{len(archive_reading.units)} measurement(s) found, "
                        f"{archive_reading.candidate_total} candidate(s)."
                    ),
                )
            )
            continue
        parser = parser_for(source)
        if parser is None:
            rewritten.append(source)
            continue
        try:
            text = _fixture_text(source)
        except UnsupportedImport as refusal:
            rewritten.append(
                replace(
                    source,
                    parse_state=PARSE_STATE_FAILED,
                    parse_detail=refusal.message,
                )
            )
            continue
        result = parser.parse(source, text)
        parsed.append(result)
        rewritten.append(
            replace(
                source,
                parse_state=PARSE_STATE_PARSED,
                parse_detail=(
                    f"Read by {parser.display_name}: "
                    f"{len(result.statements)} statement(s), "
                    f"{len(result.skipped)} line(s) reported as not understood."
                ),
            )
        )
    session.sources = rewritten
    session.parsed = parsed
    session.archive_reading = archive_reading
    session.archive_candidates = archive_candidates
    # A RE-PARSE INVALIDATES THE RECONSTRUCTION, and does not merely sit beside
    # it. Candidates derived from an earlier reading of a bundle that has been
    # re-read are a claim about evidence that may no longer exist.
    session.reconstruction = None
    session.unreadable_candidates = []
    session.unmapped_keys = []
    session.updated_utc = now_utc
    return parsed


def annotate_reusable(session: ImportSession) -> None:
    """For each REUSABLE suggestion, what it would match here and where it would differ.

    COMPARE, REUSE, SURFACE — the owner's "Experiment 2" flow — without APPLYING: a
    suggestion from another experiment says which of this import's measurements its
    selector reaches, and for each where today's reading differs from what the rule
    would say. Nothing changes until a scientist records a rule here with
    ``derived_from`` naming it. In memory; the caller saves.
    """
    from . import convention_rules as cr  # local: keeps import order flexible

    reading = session.archive_reading
    annotated: list[dict] = []
    not_offered = 0
    for row in session.reusable_rules:
        row = dict(row)
        try:
            rule = cr.ConventionRule.from_state(row.get("rule"))
        except (cr.UnsupportedRule, TypeError, ValueError):
            row["matches"] = {"units": 0, "stems": []}
            row["differences"] = []
            row["difference_count"] = 0
            row["unreadable"] = True
            annotated.append(row)
            continue
        matched: list[UnitReading] = []
        differences: list[str] = []
        # A RESOLUTION OR A CHANNEL ASSIGNMENT IS ABOUT SOURCES READ UNDER ONE
        # CONVENTION (2026-09-22): it reaches only this import's measurements read under
        # the convention it was confirmed under, and is not offered at all to an import
        # with none. A binding is the exception — changing the convention is its point.
        convention = rule.profile_id if rule.kind != cr.KIND_PROFILE_BINDING else None
        units = list(reading.units) if reading is not None else []
        if convention is not None and not any(
            convention in ((u.applicability or {}).get("profile_ids") or []) for u in units
        ):
            not_offered += 1
            continue
        for unit in units:
            if convention is not None and convention not in (
                (unit.applicability or {}).get("profile_ids") or []
            ):
                continue
            if not rule.selector.matches(
                archive_path=unit.acquisition_path,
                stem=unit.stem,
                source_type=unit.source_type,
            ):
                continue
            matched.append(unit)
            if rule.kind == cr.KIND_PROFILE_BINDING:
                current = (unit.applicability or {}).get("profile_ids") or []
                if current != [rule.body.get("profile_id")]:
                    differences.append(
                        f"{unit.stem}: read under {', '.join(current) or 'nothing'}; the "
                        f"rule would read it under {rule.body.get('profile_id')}"
                    )
            elif rule.kind == cr.KIND_SIGNAL_ASSIGNMENT:
                selection = unit.signal_selection or {}
                current = sorted(
                    (a.get("channel"), a.get("element")) for a in selection.get("assignments") or []
                )
                wanted = sorted(
                    (a.get("channel"), a.get("element")) for a in rule.body.get("assignments") or []
                )
                if current != wanted:
                    differences.append(
                        f"{unit.stem}: today {current or 'unresolved'}; the rule assigns {wanted}"
                    )
        row["matches"] = {
            "units": len(matched),
            "stems": [u.stem for u in matched[:5]],
        }
        row["differences"] = differences[:5]
        row["difference_count"] = len(differences)
        row["version_is_current"] = rule.version_is_current()
        annotated.append(row)
    session.reusable_rules = annotated
    if session.reusable_scan:
        session.reusable_scan = {
            **session.reusable_scan,
            "not_offered_other_convention": not_offered,
        }


def _skips_ceiling_first(
    skipped: Sequence[Mapping], limit: int = MAX_SKIPPED_PER_SOURCE
) -> list[dict]:
    """Window a source's skip list, keeping the evidence-ceiling entry first.

    ``_emit.result()`` appends the ceiling entry LAST, so a plain head window drops
    the one entry that says a reading is incomplete — and drops it precisely on the
    sources verbose enough to have reached the ceiling. That entry names the line,
    header, motor and scan where reading stopped; the rest of the list is individual
    lines a reader passed over. If exactly one of those must survive a window, it is
    not a prose line.

    **Order within the remainder is preserved**, so a reader still sees the earliest
    skips rather than an arbitrary sample.
    """
    from .bl15._emit import SKIP_EVIDENCE_CEILING

    ceiling = [dict(s) for s in skipped if s.get("reason") == SKIP_EVIDENCE_CEILING]
    rest = [dict(s) for s in skipped if s.get("reason") != SKIP_EVIDENCE_CEILING]
    return (ceiling + rest)[:limit]


def _fixture_text(source: SourceReference) -> str:
    """The text of one committed synthetic fixture, bounded.

    The ONLY read of file content anywhere in this module, and it can reach
    nothing but :data:`FIXTURE_DIR`: the path is built by :func:`fixture_path`,
    whose allowlist membership test is the traversal boundary.
    """
    name = source.fixture_name
    if not isinstance(name, str):
        raise UnsupportedImport(
            "no_fixture_named",
            "This source is recorded as a synthetic fixture but names none.",
        )
    path = fixture_path(name)
    raw = path.read_bytes()
    if len(raw) > MAX_SOURCE_TEXT_BYTES:
        raise UnsupportedImport(
            "source_too_large",
            (
                "This source is larger than one parse may read. It is refused "
                "whole rather than read partly, because a partly read source "
                "reports some of what it says and silently drops the rest."
            ),
            bytes=len(raw),
            maximum=MAX_SOURCE_TEXT_BYTES,
        )
    return raw.decode("utf-8", errors="replace")


def reconstruct_session(
    session: ImportSession,
    *,
    provider: ReconstructionProvider | None = None,
    profile: BeamlineProfile = EMPTY_BEAMLINE_PROFILE,
    now_utc: str,
    mint_id=new_record_id,
) -> Reconstruction:
    """Run the provider over this session's parsed evidence. In memory, writes nothing.

    **THE RESULT IS CANDIDATES AND NOTHING ELSE.** No field is written, no
    evidence entry is minted, no record is touched:
    :data:`RECONSTRUCTION_APPLIED` is ``False`` and travels with the payload.

    **THE ARCHIVE'S CANDIDATES ARE COMPOSED IN, NOT RE-DERIVED.**
    :func:`read_archive` already ran the whole ``bl15`` chain during Parse, and
    re-running it here would read every file in the archive a second time to
    reach the same answer. So the union is ``provider candidates + archive
    candidates``, in that order, and the provider is still asked even for an
    archive-only bundle — over an empty ``parsed`` list it deterministically
    returns none, which keeps ``provider_id`` on the payload saying which
    provider this build has rather than leaving the field's meaning to depend on
    what the bundle happened to contain.
    """
    if not session.parsed and not session.archive_candidates:
        raise UnsupportedImport(
            "nothing_parsed",
            (
                "No source in this bundle has been parsed, so there is no evidence "
                "to reconstruct from. A reference this build has not opened cannot "
                "contribute; the manifest says so per entry."
            ),
        )
    chosen = provider or PROVIDER
    reconstruction = chosen.reconstruct(
        parsed=list(session.parsed), profile=profile, now_utc=now_utc, mint_id=mint_id
    )
    if session.archive_candidates:
        reconstruction = replace(
            reconstruction,
            candidates=reconstruction.candidates + tuple(session.archive_candidates),
        )
    session.reconstruction = reconstruction
    session.unreadable_candidates = []
    session.unmapped_keys = unmapped_keys(session)
    session.updated_utc = now_utc
    return reconstruction


def unmapped_keys(session: ImportSession) -> list[dict]:
    """Every parsed key that is NOT an official field path, with where it came from.

    Reported so the surface can show what the reconstruction passed over. The
    keys are NOT guessed at: this build has no alias table, and inventing one is
    what ``BL15-002`` is blocked on.
    """
    official = _official_field_paths()
    out: list[dict] = []
    for result in session.parsed:
        for statement in result.statements:
            if statement.key in official:
                continue
            out.append(
                {
                    "source_id": result.source_id,
                    "key": statement.key,
                    "value": statement.value,
                    "locator": statement.locator,
                    "reason": "not_an_official_field_path",
                }
            )
    return out


def record_proposed(
    session: ImportSession,
    *,
    candidate_id: str,
    experiment_id: str,
    proposal_id: str,
    note_id: str,
    proposed_utc: str,
) -> None:
    """Record that one candidate has been sent into review on one experiment.

    It records the ACT, not the proposal — the proposal is on the experiment,
    which is the only place a proposal is ever stored. Keeping a copy here would
    be a second source of truth about a human judgement, free to go stale the
    moment the proposal is accepted or rejected.
    """
    session.proposed[candidate_id] = {
        "experiment_id": experiment_id,
        "proposal_id": proposal_id,
        "note_id": note_id,
        "proposed_utc": proposed_utc,
    }
    session.updated_utc = proposed_utc


def corpus_digest(session: ImportSession) -> dict | None:
    """WHAT A SCIENTIST READS FIRST about an imported archive, or ``None``.

    ``None`` when this bundle holds no archive — which is an honest absence and
    not an empty digest: a bundle of pointers has no corpus to describe, and
    zeroes would read as "a corpus with nothing in it".

    **EVERY NUMBER HERE IS COUNTED FROM THE PAYLOAD. Not one is a literal, and
    that is a rule rather than a style.** ``CLAUDE.md`` §11 records four separate
    surfaces that shipped a figure they had not derived from what they claimed to
    describe, and the archive case is the easiest one to get wrong: the
    scientist-facing "how many scans, how many macros, how many notes" figures
    are not on ``SourceRecord`` at all — classification is
    :mod:`bl15.classify`'s and lives nowhere on the record — so a surface with no
    classification map on the wire would be tempted to write the counts down. The
    map is carried (:attr:`ArchiveReading.manifest`) and these are counted off it.

    **THREE NUMBERS ARE HONESTY NUMBERS RATHER THAN PROGRESS NUMBERS**, and they
    are here so the digest cannot read as a completeness claim:

    * ``refused`` — entries the walk would not inventory, with the reason and the
      measured value against the ceiling. An inventory that listed only what it
      accepted could not be told apart from a smaller archive.
    * ``truncated_reason`` — set when the WALK stopped early, which means the
      inventory itself is incomplete and every count below it is a floor.
    * ``partial_readings`` / ``statements_suppressed`` — sources a reader
      understood and reported only PART of.
      :data:`~isaac_api.bl15.evidence.MAX_EVIDENCE_PER_SOURCE` records one real
      file suppressing ~41,000 statements, so ``statements_read`` is a count and
      never a guarantee.

    ``cannot_be_export_ready`` is the three measured reasons a Run from this
    corpus cannot reach an official record, stated plainly instead of a progress
    indicator that can never fill — see :func:`export_blocked_reasons`.
    """
    reading = session.archive_reading
    if reading is None:
        return None
    inventory = dict(reading.inventory)
    refused = list(inventory.get("refused") or [])
    candidate_count = len(session.archive_candidates)
    return {
        "archive_name": reading.archive_name,
        "root_label": reading.root_label,
        "walker_id": reading.walker_id,
        "total_sources": _as_count(inventory.get("entry_count")) or 0,
        "total_bytes": _as_count(inventory.get("total_bytes")) or 0,
        "by_source_type": reading.by_source_type(),
        "by_classification_confidence": reading.by_confidence(),
        "refused": refused,
        "refused_count": len(refused),
        "truncated_reason": inventory.get("truncated_reason"),
        "duplicate_group_count": _as_count(inventory.get("duplicate_group_count")) or 0,
        "statements_read": reading.statements_read,
        "statements_suppressed": reading.statements_suppressed,
        "partial_readings": reading.partial_reading_count(),
        "sources_no_reader_ran_on": reading.refused_reading_count(),
        "measurement_units": len(reading.units),
        "run_candidate_units": len(reading.run_candidate_units()),
        "sample_groups": len(reading.relationships.get("groups") or []),
        "conflicts": _as_count(reading.relationships.get("conflict_count")) or 0,
        "unattached_sources": len(reading.relationships.get("unattached") or []),
        "relate_inputs_present": list(reading.relationships.get("inputs_present") or []),
        # THE CANDIDATE TOTAL IS THE RECONSTRUCTION'S, NOT THE STORED COUNT, and
        # `candidates_truncated` says when they differ. A surface reporting the
        # stored count as the total would understate the corpus by exactly the
        # amount `MAX_CANDIDATES_PER_SESSION` withheld.
        "candidates": reading.candidate_total,
        "candidates_stored": candidate_count,
        "candidates_truncated": reading.candidates_truncated,
        "candidate_ceiling": MAX_CANDIDATES_PER_SESSION,
        "by_concept": dict(reading.by_concept),
        "by_mapping_status": dict(reading.by_mapping_status),
        "unregistered_concepts": list(reading.unregistered_concepts),
        "cannot_be_export_ready": list(export_blocked_reasons()),
        "persistence": ARCHIVE_PERSISTENCE_DECISION,
    }


def _page(rows: Sequence, *, limit: int = ARCHIVE_PAGE_WINDOW) -> dict:
    """``{"rows": <first `limit`>, "total": <all of them>, "limit": <limit>}``.

    **THE WINDOW BOUNDS WHAT IS FETCHED, NEVER WHAT IS CLAIMED** — ``CLAUDE.md``
    §11's 2026-09-02 rule for ``PENDING_WINDOW``, applied here because the
    failure mode is identical and worse: a surface counting the rows it received
    would report a 1,192-file corpus as 200 files. ``total`` is read off the
    whole collection, so every count a surface renders can come from the server.
    """
    rows = list(rows)
    return {
        "rows": rows[:limit],
        "total": len(rows),
        "limit": limit,
        "truncated": len(rows) > limit,
    }


def session_view(session: ImportSession) -> dict:
    """The wire shape of one session. Derived, never a second store.

    Everything ``HIST-004`` requires the surface to show is here: which sources
    were recognised, what parsed, what failed, what experiment and run candidates
    exist, which sources support each candidate, what was deterministic versus
    inferred, where sources disagree, and what is unresolved.
    """
    reconstruction = session.reconstruction
    return {
        "import_id": session.import_id,
        "label": session.label,
        "created_utc": session.created_utc,
        "updated_utc": session.updated_utc,
        "furthest_step": session.furthest_step(),
        "workflow": [
            {
                "id": step,
                "label": label,
                # `UNBUILT_STEP` is `None` in this build, so every row reports
                # built. Compared against the CONSTANT rather than a literal, so
                # naming a future unbuilt step changes one line and the surface
                # follows it.
                "built": UNBUILT_STEP is None or step != UNBUILT_STEP,
                "disclosure": UNBUILT_STEP_DISCLOSURE
                if UNBUILT_STEP is not None and step == UNBUILT_STEP
                else None,
            }
            for step, label in WORKFLOW_STEPS
        ],
        "durability": SESSION_DURABILITY_DISCLOSURE,
        "sources": [s.to_state() for s in session.sources],
        # THE SHAPE THE REVIEW SURFACE CONSUMES, added 2026-09-16 to JOIN two halves
        # that had been built independently and did not meet.
        #
        # Independent review measured the gap: `grep -rn corpus_review apps/api/` ->
        # 0 hits, and the surface's whole component tree rendered behind a member no
        # route ever set. Worse, three comments justified that with a reason that had
        # gone FALSE — "the archive source kind is a separate slice's step 1" — when
        # the kind had shipped on this same branch. So the honest product status was
        # neither built nor stated.
        #
        # SERVED AT THE SESSION LEVEL, not inside `archive`, because that is where the
        # committed client type declares it (`lib/types.ts`). Reshaping a contract the
        # other half was already built against would have been the same mistake twice.
        #
        # It is a PROJECTION of what is already here, not a second source of truth:
        # `inventory` and `relationships` are the identical dicts `_archive_view`
        # serves, and `mapping` is the static registry. The only new collection is
        # `evidence`, and it is the bounded six-concept set — see
        # `REVIEW_COLUMN_CONCEPTS`.
        **_corpus_review(session),
        "unreadable_source_count": len(session.unreadable_sources),
        "source_counts": {
            "total": len(session.sources),
            "parsed": sum(
                1 for s in session.sources if s.parse_state == PARSE_STATE_PARSED
            ),
            "failed": sum(
                1 for s in session.sources if s.parse_state == PARSE_STATE_FAILED
            ),
            "no_content_path": sum(
                1
                for s in session.sources
                if s.parse_state == PARSE_STATE_NO_CONTENT_PATH
            ),
            "unparsed": sum(
                1 for s in session.sources if s.parse_state == PARSE_STATE_UNPARSED
            ),
            "parsable_by_this_build": len(session.parsable_sources()),
        },
        "parsed": [p.to_state() for p in session.parsed],
        "unmapped_keys": [dict(entry) for entry in session.unmapped_keys],
        "reconstruction": _reconstruction_view(reconstruction),
        "unreadable_candidate_count": len(session.unreadable_candidates),
        "proposed": {cid: dict(row) for cid, row in sorted(session.proposed.items())},
        "parsers": [
            {"parser_id": p.parser_id, "display_name": p.display_name} for p in PARSERS
        ],
        "provider": {
            "provider_id": PROVIDER.provider_id,
            "display_name": PROVIDER.display_name,
            "applied": RECONSTRUCTION_APPLIED,
        },
        "beamline_profile": {
            "profile_id": EMPTY_BEAMLINE_PROFILE.profile_id,
            "display_name": EMPTY_BEAMLINE_PROFILE.display_name,
            "is_empty": EMPTY_BEAMLINE_PROFILE.is_empty(),
            "conventions_encoded": 0,
        },
        "available_fixtures": list(fixture_names()),
        "available_archives": list(archive_names()),
        # THE DIGEST FIRST, because it is what a scientist reads first. `None`
        # for a bundle with no archive, which is an absence rather than zeroes.
        "corpus_digest": corpus_digest(session),
        "archive": _archive_view(session),
        # (2026-09-23) What the batch will do with each candidate, from the batch's
        # own partition — so the Add stage predicts exactly what it then reports.
        "send_plan": send_plan(session),
        # --- added 2026-09-22 ----------------------------------------------------
        # The registered naming CONVENTIONS a scientist can bind a subset of Runs to —
        # each with its historical aliases, and none of them a person.
        "profiles": _registered_profiles(),
        # Reviewed, versioned rules: this import's apply-only-here rules, the target
        # experiment's confirmed rules as of the last parse, and convention-scoped
        # rules from other experiments offered as REUSABLE SUGGESTIONS (never applied
        # until confirmed here). Durability is stated per group.
        "rules": _rules_view(session),
        # Two capabilities a surface reads BEFORE offering a control that would fail.
        "capabilities": _capabilities_view(),
    }


def _reconstruction_view(reconstruction: Reconstruction | None) -> dict | None:
    """The reconstruction on the wire, with its CANDIDATE LIST BOUNDED.

    ``None`` when there is none. Otherwise exactly
    :meth:`Reconstruction.to_state`'s shape, with two additions and one change:
    ``candidates`` carries at most :data:`ARCHIVE_PAGE_WINDOW` entries, and
    ``candidate_page`` states the true ``total``, the ``limit`` applied and
    whether anything was withheld.

    **THE WINDOW BOUNDS WHAT IS FETCHED, NEVER WHAT IS CLAIMED.** Measured at the
    real corpus's cardinality, an unbounded response was **6,410,701 bytes**, of
    which ``reconstruction`` alone was **5,567,110** — a single HTTP response
    nobody can use, over ~1,879 candidates a surface could not render either.
    ``candidate_page.total`` is read off the whole tuple, so every count a
    surface shows comes from the server rather than from the length of what it
    received; ``CLAUDE.md`` §11's 2026-09-02 entry records the defect class this
    rule exists to prevent.

    **NOTHING ABOUT PROPOSING IS AFFECTED, and that is why the window is safe
    here.** Both propose operations resolve a candidate against the LOADED
    SESSION (``ImportSession.candidate`` and :func:`candidates_of`), never
    against this payload, so a candidate outside the window is still fully
    proposable by id. The fixture path is unchanged in practice as well as in
    shape: every committed example produces far fewer than the window, so its
    ``candidates`` array is byte-identical to what it has always been.
    """
    if reconstruction is None:
        return None
    state = reconstruction.to_state()
    candidates = state.get("candidates") or []
    state["candidates"] = candidates[:ARCHIVE_PAGE_WINDOW]
    state["candidate_page"] = {
        "total": len(candidates),
        "limit": ARCHIVE_PAGE_WINDOW,
        "truncated": len(candidates) > ARCHIVE_PAGE_WINDOW,
    }
    return state


def _archive_view(session: ImportSession) -> dict | None:
    """The archive reading, PAGED. ``None`` when this bundle holds no archive.

    Three collections are paged rather than served whole, and each carries its
    own ``total``: the per-file MANIFEST (1,192 rows on the real corpus), the
    per-source READING rows (the same cardinality), and the MEASUREMENT UNITS
    (94). The units' page is the one a surface builds its Runs list from, and it
    is bounded for the same reason the others are.

    **THE MANIFEST IS SERVED AT ALL BECAUSE THE BRIEF REQUIRES IT under
    disclosure, and it is PAGED because 1,192 flat rows by default is the
    pattern ``HIST-004`` bans.** It is built here rather than in
    :meth:`isaac_api.bl15.inventory.ArchiveInventory.to_state`, which omits
    ``entries`` deliberately — paging belongs at the surface that has a request
    to bound, not on a value type shared by a CLI and a walk.

    Relationships are served WHOLE and that is a deliberate exception: `units`
    inside it is the same 94 rows, but its `groups`, `corpus_conflicts` and
    `unattached` are the things a scientist most needs to see completely, and
    they are bounded by the archive's own entry ceiling rather than by its file
    count. If the real corpus makes this large, it is the next thing to page —
    named here so that is a decision rather than a discovery.
    """
    reading = session.archive_reading
    if reading is None:
        return None
    return {
        "source_id": reading.source_id,
        "archive_name": reading.archive_name,
        "root_label": reading.root_label,
        "walker_id": reading.walker_id,
        "inventory": dict(reading.inventory),
        "manifest_page": _page(reading.manifest),
        "reading_page": _page(reading.reading),
        "units_page": _page([u.to_state() for u in reading.units]),
        "relationships": dict(reading.relationships),
        "shared_candidate_ids": list(reading.shared_candidate_ids),
        "run_candidate_unit_count": len(reading.run_candidate_units()),
        "statements_read": reading.statements_read,
        "statements_suppressed": reading.statements_suppressed,
        "candidate_total": reading.candidate_total,
        "candidates_truncated": reading.candidates_truncated,
        "persistence": ARCHIVE_PERSISTENCE_DECISION,
    }


def _corpus_review(session: "ImportSession") -> dict:
    """``{"corpus_review": ...}`` when this bundle holds an archive reading, else ``{}``.

    Returns a mapping to be spread, so a session without an archive carries no key at all
    rather than a ``None`` the client would have to distinguish from an empty review.
    """
    reading = session.archive_reading
    if reading is None:
        return {}
    return {
        "corpus_review": {
            "inventory": dict(reading.inventory),
            "relationships": dict(reading.relationships),
            "evidence": [dict(row) for row in reading.column_readings],
            # A WINDOW WITH ITS COSTS BESIDE IT — TWO COUNTS, NEVER SUMMED (split
            # 2026-09-22, as `CTX-004` split extended context). ~~One integer was served
            # here under a comment describing only the dedup~~, while it also counted
            # the distinct-literal cap. `evidence_readings_thinned`: a literal repeated
            # for the same measurement and concept — corroboration trimmed, nothing
            # lost. `evidence_readings_dropped` NOW MEANS THE CAP ALONE: a DIFFERENT
            # literal not kept because the cell already holds the maximum — the cell is
            # disputed either way, but not every competing reading is listed. Neither
            # can ever settle a disputed cell, because the cap is on distinct literals.
            "evidence_readings_dropped": reading.column_readings_dropped,
            "evidence_readings_thinned": reading.column_readings_thinned,
            "evidence_readings_cap_per_cell": MAX_DISTINCT_COLUMN_READINGS,
            "evidence_scope": sorted(REVIEW_COLUMN_CONCEPTS),
            # `DEC-41` LEVEL 4, WITH ITS COSTS BESIDE IT — `CTX-004`.
            #
            # WHY IT IS HERE AT ALL. `ImportCorpusReview` already renders a candidate's
            # `placement_name` verbatim, so a reader can see that a concept LANDS at
            # level 4 — and then had no way to learn how much landed there, or what the
            # reading declined to carry. `available` is the reading's own total; the
            # three costs are the three reasons a statement the archive made is not
            # among them.
            #
            # THREE COUNTS, NEVER SUMMED, because they mean different things to a
            # reader: `dropped` is a BOUND (statements absent, a corpus larger than the
            # companion holds), `thinned` is a repeated literal inside ONE source that
            # kept its first locator (no statement lost), and `unplaceable` is this
            # BUILD failing to construct an entry (no ceiling change would alter it).
            # They were ONE integer until `CTX-004` measured the three sites — see
            # `MAX_EXTENDED_CONTEXT_ENTRIES` for the full account.
            #
            # `ceiling` travels with them so a surface can say WHAT bound applied
            # without transcribing the number, which is the rule `candidate_ceiling`
            # two blocks away already follows.
            #
            # `not_official` IS SAID ON THE WIRE rather than left to a client, exactly
            # as the import summary's own `extended_context` block says it: this is the
            # one claim a surface must not get wrong about these entries.
            "extended_context": {
                "available": len(reading.extended_context_entries),
                "dropped": reading.extended_context_dropped,
                "thinned": reading.extended_context_thinned,
                "unplaceable": reading.extended_context_unplaceable,
                "ceiling": MAX_EXTENDED_CONTEXT_ENTRIES,
                "not_official": _not_official_claim(),
            },
            "mapping": _mapping_block(),
            # --- added 2026-09-22 -----------------------------------------------
            # WHICH convention applied WHERE. Per-unit detail is on each unit
            # (`archive.units_page.rows[].applicability`); this is the summary.
            "profile_applicability": {
                "bindings": [dict(b) for b in reading.bindings],
                "convention_counts": dict(reading.convention_counts),
                "ambiguous_sources": int(reading.convention_counts.get("ambiguous", 0)),
                "selected_by_operator": False,
                "rule": (
                    "A convention is selected by the source's own name and "
                    "classification — facility, beamline, acquisition system, "
                    "experiment, a subset of Runs, a source family or one source — "
                    "and never by who ran a measurement. People named by the sources "
                    "are provenance, listed per measurement."
                ),
            },
            # TEMPERATURE: missing stays missing (2026-09-22). `status` is what a
            # surface renders — `not_recorded` unless a source literally stated
            # something, in which case the words are shown verbatim and still no
            # number is written or offered by default.
            "temperature": _temperature_view(reading),
            "data_quality_notes": {
                "label": "Data Quality Notes",
                "bound_to_a_measurement": sum(
                    len(u.data_quality_notes) for u in reading.units
                ),
                "unbound": [dict(n) for n in reading.unbound_data_quality_notes],
                "writes_qc_status": False,
                "policy": (
                    "Every free-text Notes cell is kept verbatim and bound to its file "
                    "number. No phrase is classified and qc.status is never written "
                    "from these notes — the domain owner's answer, 2026-09-22."
                ),
            },
            "herfd_signal": {
                "acquisition_system": dict(reading.acquisition_system),
                "element_evidence": [dict(e) for e in reading.element_evidence],
                "by_status": _selection_counts(reading),
                "writes_a_record_field": False,
            },
            "beamtime_contributors": [dict(c) for c in reading.beamtime_contributors],
            "rules_applied": list(reading.rules_applied),
        }
    }


def _registered_profiles() -> list[dict]:
    from .bl15 import profiles  # local: keeps import order flexible

    return profiles.registered_profiles()


def _capabilities_view() -> dict:
    """The two capability blocks, computed by the SAME functions ``/api/health`` uses."""
    from . import capabilities  # local: keeps import order flexible

    return {
        "historical_file_ingestion": capabilities.historical_file_ingestion(),
        "proposal_acceptance": capabilities.proposal_acceptance(),
    }


def _rules_view(session: "ImportSession") -> dict:
    return {
        "target_experiment_id": session.target_experiment_id,
        "import": [r.to_state() for r in session.rules],
        "import_durability": SESSION_DURABILITY_DISCLOSURE,
        "import_unreadable": len(session.unreadable_rules),
        "experiment": [dict(r) for r in session.experiment_rules],
        "experiment_rules_as_of_version": session.experiment_rules_version,
        "experiment_durability": (
            "A rule for an Experiment is stored in that experiment's own record and is "
            "exactly as durable as the record."
        ),
        "reusable_from_other_experiments": [dict(r) for r in session.reusable_rules],
        "reusable_scan": dict(session.reusable_scan),
        "reuse_policy": (
            "A convention-scoped rule confirmed on another experiment is shown here with "
            "what it would match and where it would differ. It is NOT applied until a "
            "scientist confirms it for this experiment; nothing is promoted across "
            "experiments silently."
        ),
    }


def _temperature_view(reading: "ArchiveReading") -> dict:
    from .bl15 import mapping as mp  # local: keeps import order flexible
    from .bl15 import nominal  # local: keeps import order flexible

    used = {
        pid
        for unit in reading.units
        for pid in (unit.applicability or {}).get("profile_ids", []) or []
    } or {reading.profile_id}
    offers = sorted(p for p in used if nominal.nominal_temperature_for(p) is not None)
    return {
        "official_path": nominal.NOMINAL_TEMPERATURE_PATH,
        "status": "stated_in_source" if reading.temperature_statements else "not_recorded",
        "display": (
            "Temperature — stated in the sources (verbatim, not converted)"
            if reading.temperature_statements
            else "Temperature — Not recorded"
        ),
        "statements": [dict(t) for t in reading.temperature_statements],
        "automatic_value": None,
        "automatic_proposal": False,
        "nominal_rule_enabled_for": offers,
        # ONE SENTENCE FOR BOTH CASES. It was briefly a second, "stated" wording here,
        # because the registry's sentence denied a statement in words; that sentence is
        # now true of both a corpus that states none and one that states one in words
        # (`bl15.mapping.TEMPERATURE_ABSENT_REASON`), so there is one wording per fact.
        "policy": mp.TEMPERATURE_ABSENT_REASON,
        "superseded_decision": nominal.SUPERSEDED_DECISION,
    }


def _selection_counts(reading: "ArchiveReading") -> dict:
    counts: dict[str, int] = {}
    for unit in reading.units:
        status = (unit.signal_selection or {}).get("status")
        if isinstance(status, str):
            counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _not_official_claim() -> str:
    """:data:`extended_context.NOT_OFFICIAL_CLAIM`, read rather than transcribed.

    A local import for the reason every other one in this module is: it keeps the import
    order flexible. Read rather than copied for the reason the whole companion exists —
    a second copy of the artifact's own denial is a second thing that can be softened,
    and this is the sentence that must not be.
    """
    from . import extended_context as ctx  # local: keeps import order flexible

    return ctx.NOT_OFFICIAL_CLAIM


def _mapping_block() -> dict:
    """The registry, served. Static, 45 entries, and cheap.

    Served from the session rather than a schema route because the review surface needs
    it in the same response it renders from, and a second request would let the two drift
    within one screen. It is regenerated from `bl15.mapping` on every call rather than
    cached, so a registry correction cannot be served stale — `acquisition_method` moved
    status on this branch and a cached copy would have kept publishing the old one.
    """
    from .bl15 import mapping as bl15_mapping

    return {
        "coverage": dict(bl15_mapping.coverage()),
        "concepts": [
            bl15_mapping.MAPPINGS[concept].to_state()
            for concept in sorted(bl15_mapping.MAPPINGS)
        ],
        "temperature_absent_reason": bl15_mapping.TEMPERATURE_ABSENT_REASON,
        "assets_blocked_reason": bl15_mapping.ASSETS_BLOCKED_REASON,
        "cycling_state_no_field_reason": bl15_mapping.CYCLING_STATE_NO_FIELD_REASON,
        # DEC-41 / CTX-001. Served BESIDE `coverage` and never folded into it: a status
        # count answers "can a value travel" and a placement count answers "does the
        # information have a home", and the second is the number that changed. They sum
        # to the same 45 and mean different things.
        "placement": dict(bl15_mapping.placement_coverage()),
        "placement_levels": {
            str(level): bl15_mapping.PLACEMENT_NAMES[level]
            for level in bl15_mapping.PLACEMENT_LEVELS
        },
        # The packet, reconciled: twelve closed and eight open, each with WHAT closed it.
        # A surface that showed only the eight would leave a reader unable to tell a
        # closed question from one nobody has looked at.
        "domain_questions": [
            bl15_mapping.DOMAIN_QUESTIONS[qid].to_state()
            for qid in sorted(
                bl15_mapping.DOMAIN_QUESTIONS, key=lambda q: int(q[1:])
            )
        ],
        "open_domain_questions": list(bl15_mapping.open_domain_questions()),
        # Named rather than left to be subtracted — see the function's own docstring.
        "needs_review_without_a_question": list(
            bl15_mapping.needs_review_without_a_question()
        ),
    }


def session_summary(session: ImportSession) -> dict:
    """The wire shape of one session in a LIST. Bounded by construction.

    It carries counts and never the manifest, the parse results or the
    candidates: a list screen that served every session's full reading would grow
    without bound in the number of sessions times the size of each bundle, which
    is the shape ``POST .../answers`` had to be un-picked from.
    """
    reconstruction = session.reconstruction
    return {
        "import_id": session.import_id,
        "label": session.label,
        "created_utc": session.created_utc,
        "updated_utc": session.updated_utc,
        "furthest_step": session.furthest_step(),
        "source_count": len(session.sources),
        "parsed_source_count": sum(
            1 for s in session.sources if s.parse_state == PARSE_STATE_PARSED
        ),
        # THE PROVIDER'S count, which is not the archive's. An archive reading carries
        # its OWN candidates on `archive_reading`, bounded by
        # `MAX_CANDIDATES_PER_SESSION` — so a list row that showed only this number on an
        # archive session would report 0 while the session held hundreds. Both are served,
        # and the truncation flag travels with the one that can be bounded, so no count
        # here is ever shown as a whole one when it is not.
        # Added 2026-09-16 after independent review.
        "candidate_count": 0 if reconstruction is None else len(reconstruction.candidates),
        "archive_candidate_count": len(session.archive_candidates),
        "archive_candidates_truncated": (
            session.archive_reading.candidates_truncated
            if session.archive_reading is not None
            else False
        ),
        "proposed_count": len(session.proposed),
    }


def batch_partition(session: "ImportSession") -> tuple[list[SemanticCandidate], list[dict]]:
    """``(sendable, not_sent)`` — how ``POST …/add-to-experiment`` splits this import.

    ONE function, used by the batch route AND by the session view's ``send_plan``, so
    what the Add stage says will happen and what then happens are one categorisation
    (2026-09-23 — the stage said "11 can be sent" and the batch sent 9). Each unsent
    row carries the reason the review surface already shows for the candidate.
    """
    sendable: list[SemanticCandidate] = []
    not_sent: list[dict] = []
    for candidate in candidates_of(session):
        if candidate.unresolved_reason is not None:
            not_sent.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "target_field_path": candidate.target_field_path,
                    "kind": candidate.kind,
                    "error": "candidate_unresolved",
                    "reason": candidate.not_proposable_reason
                    or CANDIDATE_NOT_PROPOSABLE_DISAGREEMENT,
                }
            )
        elif not candidate.proposable:
            not_sent.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "target_field_path": candidate.target_field_path,
                    "kind": candidate.kind,
                    "error": "candidate_not_proposable",
                    "reason": candidate.not_proposable_reason
                    or CANDIDATE_NOT_PROPOSABLE_NO_EXPERIMENT_CREATION,
                }
            )
        else:
            sendable.append(candidate)
    return sendable, not_sent


def has_no_run_when_creating_runs(session: "ImportSession", candidate: SemanticCandidate) -> bool:
    """Whether a SENDABLE candidate would find no run when the batch creates runs.

    A value written on a run needs the run of the measurement it was read from; a
    beamtime-scope value belongs to no measurement. (A value of a measurement that is not
    a Run is already not proposable — `CANDIDATE_NOT_PROPOSABLE_NOT_A_RUN`.)
    """
    reading = session.archive_reading
    if reading is None or _target_scope(candidate.target_field_path) != "run":
        return False
    unit = reading.unit_of_candidate(candidate.candidate_id)
    return unit is None or not unit.run_candidate


def send_plan(session: "ImportSession") -> dict:
    """What the batch WILL do with each candidate, published before anything is sent.

    ``sendable`` and ``not_sent`` (candidate id -> the batch's own error code) come from
    :func:`batch_partition` itself; ``no_run_when_creating_runs`` lists the sendable
    candidates the batch reports as ``no_run_for_this_candidate`` when it creates runs.
    Reasons are not repeated here — each candidate already carries its own.
    """
    sendable, not_sent = batch_partition(session)
    return {
        "sendable": [c.candidate_id for c in sendable],
        "not_sent": {row["candidate_id"]: row["error"] for row in not_sent},
        "no_run_when_creating_runs": [
            c.candidate_id for c in sendable if has_no_run_when_creating_runs(session, c)
        ],
    }


def candidates_of(session: ImportSession) -> Iterable[SemanticCandidate]:
    """Every candidate, or nothing. Saves every caller an ``is None`` branch."""
    if session.reconstruction is None:
        return ()
    return session.reconstruction.candidates
