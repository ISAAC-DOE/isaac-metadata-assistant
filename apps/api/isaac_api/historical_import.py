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

So a Source Bundle entry is one of exactly two kinds, and the distinction is the
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

**A DIGEST IS NEVER COMPUTED HERE, not even for a fixture this module does
read.** The scientist supplies it or it stays absent. Computing one for the
fixture and not for the pointer would put two meanings behind one field name,
and every surface reporting a digest would then have to say which it had —
whereas today every surface can say "recorded", never "verified".

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

SOURCE_KINDS = frozenset({SOURCE_KIND_REFERENCE, SOURCE_KIND_SYNTHETIC_FIXTURE})

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
            # DERIVED, and serialised anyway. A client that recomputed it would be
            # a second expression of the rule, free to drift from this one.
            "proposable": self.proposable,
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
        """Sources a registered parser can read. Never a count of the manifest."""
        return [s for s in self.sources if parser_for(s) is not None]

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
        if self.reconstruction is not None:
            return "reconstruct"
        if self.parsed:
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
            "reconstruction": (
                None
                if self.reconstruction is None
                else {
                    **self.reconstruction.to_state(),
                    "candidates": [
                        c.to_state() for c in self.reconstruction.candidates
                    ]
                    + list(self.unreadable_candidates),
                }
            ),
            "unmapped_keys": [dict(entry) for entry in self.unmapped_keys],
            "proposed": {cid: dict(row) for cid, row in sorted(self.proposed.items())},
        }

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
        session.reconstruction = reconstruction
        session.unreadable_candidates = unreadable_candidates
        return session


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
            "`kind` must name one of the two kinds of source this build stores.",
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


def _provenance(recorded_utc: str, kind: str) -> dict:
    return {
        "recorded_utc": recorded_utc,
        "recorded_by": PROVENANCE_NO_ACTOR,
        "recorded_how": (
            "a person entered this reference on the Historical Import surface"
            if kind == SOURCE_KIND_REFERENCE
            else "a person chose this committed synthetic fixture"
        ),
        "bytes_read_by_this_application": kind == SOURCE_KIND_SYNTHETIC_FIXTURE,
    }


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
    session.updated_utc = now_utc
    return True


def parse_session(session: ImportSession, *, now_utc: str) -> list[ParsedSource]:
    """Apply every registered parser to every source that has one. In memory.

    A source with no registered parser is left with the parse state it already
    carries — :data:`PARSE_STATE_NO_CONTENT_PATH` for a pointer — so the
    manifest's own column answers "what parsed and what did not" per entry. **No
    source is silently skipped**: every entry ends in exactly one of the four
    states, and the two that are not ``parsed`` carry a ``parse_detail``.
    """
    parsed: list[ParsedSource] = []
    rewritten: list[SourceReference] = []
    for source in session.sources:
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
    # A RE-PARSE INVALIDATES THE RECONSTRUCTION, and does not merely sit beside
    # it. Candidates derived from an earlier reading of a bundle that has been
    # re-read are a claim about evidence that may no longer exist.
    session.reconstruction = None
    session.unreadable_candidates = []
    session.unmapped_keys = []
    session.updated_utc = now_utc
    return parsed


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
    """
    if not session.parsed:
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
        "reconstruction": (
            None if reconstruction is None else reconstruction.to_state()
        ),
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
        "candidate_count": 0 if reconstruction is None else len(reconstruction.candidates),
        "proposed_count": len(session.proposed),
    }


def candidates_of(session: ImportSession) -> Iterable[SemanticCandidate]:
    """Every candidate, or nothing. Saves every caller an ``is None`` branch."""
    if session.reconstruction is None:
        return ()
    return session.reconstruction.candidates
