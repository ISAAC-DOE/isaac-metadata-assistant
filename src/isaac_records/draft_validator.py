"""No-guessing enforcement on drafts (authoring time).

This is where the project's core promise is enforced BEFORE anything becomes an
official record: a finalized scalar needs evidence, a missing field must be null,
an inferred field needs a stated derivation rule, and every asset and descriptor
(both scientific/provenance claims) must cite a source.

It deliberately does NOT check vocabulary or units — those are the official
schema's job, applied to the transformed record by `official.validate_official`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field

# A sha256 digest: exactly 64 lowercase hex chars (strict — no uppercase).
#
# ``\A``/``\Z``, not ``^``/``$``: Python's ``$`` also matches immediately BEFORE a
# trailing newline, so ``^[0-9a-f]{64}$`` accepted the 65-character string
# ``"a"*64 + "\n"`` — measured — and nothing downstream caught it. The official
# schema declares ``assets.items.properties.sha256`` as bare ``{"type": "string"}``
# (no pattern, no length bound), so the malformed digest exported into an official
# record and passed ``validate_official`` clean. A hash that is not a hash is
# exactly the guessed/unverifiable value this module exists to refuse.
#
# The exactness lives in the PATTERN rather than in a ``fullmatch`` call site so
# that every present and future consumer of this constant is exact by construction;
# a new ``.match()`` caller cannot reintroduce the hole. ``format_shadow``'s
# ``_RFC3339_SHAPE`` took the same decision for the same reason.
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")

FINAL_STATUSES = ("verified", "inferred")

# The one official field a draft may never author, as a dotted official JSON-path.
#
# It is LOAD-BEARING, not decorative, and that distinction was earned: an earlier revision
# of this comment claimed the constant coupled three sites so that renaming it would move
# them all, while the block refusal below and `export`'s invariant both hardcoded the leaf
# string. Review #4 renamed the constant and measured the result — the validator stopped
# refusing and the invariant stopped stripping, i.e. the single edit the comment promised was
# safe silently DISARMED the guard. Both sites now split this constant instead, so the claim
# is true. Do not reintroduce a literal "uploaded_by" in either place.
UPLOADED_BY_PATH = "attribution.uploaded_by"

# ONE message for every mechanism. It used to be typed out at the single site that
# existed; an independent review then found a second, unguarded mechanism, and a
# hand-copied second message would have been free to drift from the first.
UPLOADED_BY_REFUSAL = (
    "a draft may not author this field — the official schema declares it "
    "server-stamped from the authenticated identity at ingestion, with any "
    "client value overwritten. ISAAC has no trusted authenticated identity to "
    "stamp it with, and no evidence can make a client-supplied value true "
    "(evidence can show a document names someone, not that the server "
    "authenticated them). Remove it; record people via "
    "attribution.contributors[], which is evidence-gated. A future "
    "server-stamped value must be injected server-side at ingestion, never "
    "carried in draft content."
)

OBSERVED_SOURCE_TYPES = (
    "document",
    "spreadsheet",
    "screenshot",
    "web_form",
    "file_listing",
    "user_confirmation",
)


@dataclass
class DraftReport:
    errors: list[tuple[str, str]] = dc_field(default_factory=list)
    warnings: list[tuple[str, str]] = dc_field(default_factory=list)

    def err(self, where: str, msg: str) -> None:
        self.errors.append((where, msg))

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append((where, msg))

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        lines = [f"✗ error   {w} — {m}" for w, m in self.errors]
        lines += [f"⚠ warning {w} — {m}" for w, m in self.warnings]
        lines.append(
            f"{'PASS' if self.ok else 'FAIL'} "
            f"({len(self.errors)} errors, {len(self.warnings)} warnings)"
        )
        return "\n".join(lines)


def _has_observed(entries: list[dict]) -> bool:
    return any(e.get("source_type") in OBSERVED_SOURCE_TYPES for e in entries)


def _has_derivation(entries: list[dict]) -> bool:
    return any(e.get("source_type") == "derivation" and e.get("rule") for e in entries)


def _check_envelope(report: DraftReport, where: str, env: dict) -> None:
    status = env.get("status")
    value = env.get("value")
    # `_cited_sources`, NOT `env.get("evidence") or []`. The comprehension ITERATED the
    # stored value, so `{"evidence": 7}` raised `TypeError` out of the truth core and
    # became an HTTP 500 on `GET /api/experiments/{id}` (measured on `724ce58`).
    sources = _cited_sources(report, where, env.get("evidence"))
    unreadable_evidence = sources is None
    entries = [e for e in (sources or []) if isinstance(e, dict)]

    if status not in ("verified", "inferred", "needs_confirmation", "missing", "rejected"):
        report.err(where, f"invalid status {status!r}")
        return
    # THE STATUS/VALUE CHECKS STILL RUN over an envelope whose evidence is unreadable:
    # `status` and `value` were read fine, and withholding a finding they DO support
    # would hide a real defect behind an unrelated one.
    if status == "missing" and value is not None:
        report.err(where, "status 'missing' but a value is present")
    if status in FINAL_STATUSES and value is None:
        report.err(where, f"status '{status}' but value is null")
    # THE EVIDENCE-DERIVED CHECKS DO NOT. "has no observed evidence" is a claim about
    # what the sources say, and this module has just reported that it could not read
    # them — the same rule `_cited_sources` and the `series`/`qc` gate follow. The
    # envelope is still refused, by the shape finding filed at this same address.
    if unreadable_evidence:
        return
    if status == "verified" and value is not None and not _has_observed(entries):
        report.err(where, "verified field has no observed evidence or user confirmation")
    if status == "inferred" and value is not None:
        if not _has_derivation(entries):
            report.err(where, "inferred field has no derivation evidence with a stated rule")
        elif not _has_observed(entries):
            report.warn(where, "inferred field cites a rule but no observed supporting evidence")


def _paths_authoring_uploaded_by(fields) -> list[str]:
    """Every `draft["fields"]` key that would land a value on `attribution.uploaded_by`.

    `fields` + `export.set_path` is the draft format's NATIVE mechanism for scalar
    official JSON-paths, and `attribution.uploaded_by` IS a scalar official string —
    so this is not an exotic bypass, it is the ordinary way to write the field. Three
    spellings reach it, and all three are refused:

      1. the exact path, `fields["attribution.uploaded_by"]`;
      2. a DEEPER path, `fields["attribution.uploaded_by.x"]`, which `set_path` creates
         the refused key as a dict in order to reach;
      3. a SHORTER path whose envelope VALUE supplies the remaining segments, e.g.
         `fields["attribution"] = {"value": {"uploaded_by": ...}, ...}`.

    (3) is measured, not hypothetical: at the first-attempt commit it produced a record
    carrying `{"uploaded_by": "attacker@example.invalid"}` exactly as (1) did.

    On spellings that do NOT reach it: `set_path` performs no normalisation whatsoever —
    it splits on "." and uses the segments as dict keys verbatim. So `" attribution.
    uploaded_by"` writes a top-level `" attribution"` key and `"attribution.uploaded_by "`
    writes `"uploaded_by "` inside the block; `"attribution..uploaded_by"` nests under an
    empty-string key. None is the real field, and each is rejected outright by the
    official schema, which sets `additionalProperties: false` on both the record root and
    the attribution block. Whitespace variants are therefore deliberately NOT normalised
    here: silently treating `" attribution"` as `attribution` would invent an intent the
    draft did not express, and the schema already refuses it loudly.

    Refusal is on KEY PRESENCE, consistent with the `attribution` block check: a null or
    empty-string value still asserts authorship of a server-owned field. (Note the
    exporter would SKIP such an envelope, so this check is strictly stricter than what
    can leak — that is the intended direction.)
    """
    target = UPLOADED_BY_PATH.split(".")
    offenders: list[str] = []
    for path, env in (fields or {}).items():
        if not isinstance(path, str):
            continue
        parts = path.split(".")
        if parts[: len(target)] == target:
            offenders.append(path)  # spellings (1) and (2)
            continue
        if target[: len(parts)] == parts:
            # spelling (3): walk the envelope's value for the missing segments.
            node = env.get("value") if isinstance(env, dict) else None
            for segment in target[len(parts) :]:
                if not isinstance(node, dict) or segment not in node:
                    break
                node = node[segment]
            else:
                offenders.append(path)
    return sorted(offenders)


def _claim_covered(entries: list) -> bool:
    """A claim is covered iff it cites at least one source (a dict evidence entry).

    Reached only through :func:`_cited_sources`, which has already established that
    ``entries`` IS a list. Calling it with anything else is a programming error here,
    and used to be a live HTTP 500 — see that function's note.
    """
    return any(isinstance(e, dict) for e in entries)


def _cited_sources(report: DraftReport, where: str, raw) -> list | None:
    """The sources one claim cites, or ``None`` when the stored value cannot be read.

    **THE MEASURED DEFECT.** ``_claim_covered`` was ``any(isinstance(e, dict) for e in
    (entries or []))``, which ITERATES whatever it is given. A stored evidence value
    that is not a list therefore raised out of the truth core rather than being
    reported. Measured over HTTP on ``724ce58``, one wrong-typed value at a time,
    written into the persisted state of a record created through ``POST
    /api/experiments`` — ``GET /api/experiments/{id}`` in every row, with ``GET
    /api/experiments`` and ``GET /api/experiments/{id}/pending`` answering 200
    throughout:

    ==================================================  ========  ==================
    stored value                                        before    raised
    ==================================================  ========  ==================
    ``assets[0]["evidence"] = 7``                       **500**   ``TypeError``
    ``implicit[0]["evidence"] = 7``                     **500**   ``TypeError``
    ``block_evidence["series:s"] = 7``                  **500**   ``TypeError``
    ``fields["a.b"]["evidence"] = 7``                   **500**   ``TypeError``
    ==================================================  ========  ==================

    (``links`` and ``attribution.contributors`` reach the same call and raised the same
    way; they are reported here for completeness rather than as separate defects.)

    **WHY A SEPARATE FUNCTION RATHER THAN A TOLERANT ``_claim_covered``.** Returning
    ``False`` for an unreadable value would have been one line, and it would have made
    this module state something it cannot know: that the claim cites no source. It
    cites nothing this module could READ, which is a different sentence and the only
    one the draft supports. So the shape is reported at the claim's own address and the
    caller is told — by ``None`` — not to add a second finding derived from the value
    just refused. That is the same rule the ``series``/``qc`` gate below now follows.

    **NOTHING IS WALKED, COERCED OR QUOTED.** A string is refused rather than iterated,
    for the reason ``_container`` states: ``any(isinstance(e, dict) for e in "abc")``
    silently answers "no sources" over three characters that were never entries. The
    stored VALUE never appears in the message — only its JSON shape.

    **VERDICT MOVEMENT.** A truthy non-list value previously either RAISED (no verdict
    at all) or, for the two iterable non-list shapes JSON can produce — a string and an
    object — answered ``False`` and produced the caller's "no evidence" error. Both are
    already FAIL, so no draft that validated clean changes verdict; only the message
    moves. See the §13 disclosure for the full statement.
    """
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    report.err(
        where,
        f"evidence must be a list of source entries; this draft stores {_kind(raw)}. "
        f"The value is refused rather than walked — nothing here can assume what it "
        f"was meant to cite, and reading positions out of it would invent sources the "
        f"draft never named.",
    )
    return None


def _check_claim(report: DraftReport, where: str, entries) -> None:
    """A claim (asset, descriptor, implicit) must cite at least one source."""
    sources = _cited_sources(report, where, entries)
    if sources is None:
        return
    if not _claim_covered(sources):
        report.err(where, "no evidence — every asset/descriptor/inference must cite a source")


def _block_uncited(report: DraftReport, where: str, raw) -> bool:
    """True iff the caller should file its own block-specific "no evidence" finding.

    False in BOTH the covered case and the unreadable one. In the second,
    :func:`_cited_sources` has already filed the finding that says what shape was
    found, and a second finding asserting the block cites nothing would be a claim
    about a value this module just said it could not read.
    """
    sources = _cited_sources(report, where, raw)
    if sources is None:
        return False
    return not _claim_covered(sources)


# --- malformed top-level containers -------------------------------------------
#
# EVERY TOP-LEVEL CONTAINER THIS MODULE WALKS, AND THE JSON TYPE IT MUST BE.
#
# This table exists because `validate_draft` used to walk these containers without
# asking, so a stored draft whose `assets` was a string reached `asset.get("sha256")`
# and raised. Measured over HTTP on `721238a`, on a record with nothing pending (which
# is what lets `Experiment.export_ready` reach `draft_ok`): `GET
# /api/experiments/{id}` -> 500. The exception class depended only on whether the wrong
# type happened to be iterable (`TypeError`) or not (`AttributeError`); neither is an
# answer.
#
# NOT ALL TEN RAISED, AND THE DIFFERENCE MATTERS ENOUGH TO STATE IT HERE RATHER THAN
# LET A READER ASSUME OTHERWISE. An earlier revision of this comment, and of three
# sibling claims, said "all ten"; an independent review measured that false and it is
# corrected rather than deleted, because the false version concealed the one verdict
# this change moves. Measured on `721238a`, wrong-typed and truthy, one container at a
# time on an otherwise-minimal draft:
#
#   EIGHT raised unconditionally:  meta, fields, attribution, assets,
#                                  descriptors_outputs, implicit, series, links
#   `qc`  raised only when a series was present, because that is the only thing that
#         reads it — and the guard below is inside the SAME `if series:`, so `qc`
#         behaves identically before and after, in both branches.
#   `block_evidence` raised only when a series, a link, a contributor or the qc gate
#         looked it up. A draft with NONE of those never reached `.get` and so
#         VALIDATED CLEAN.
#
# So there is exactly one verdict flip: a draft storing a truthy non-object
# `block_evidence` and carrying no series, no links and no contributors went from
# PASS to FAIL, and `Experiment.draft_ok()` from True to False. It is a flip toward
# refusal, on a document that could never have exported anyway — `export.build_sidecar`
# does `(draft.get("block_evidence") or {}).items()`, so that draft raised
# `AttributeError` out of `export_draft`. The change converts that third crash into a
# clean refusal. Nothing that previously EXPORTED stops exporting; one thing that
# previously reported PASS while being unexportable now reports why.
#
# THE RULE: a container of the wrong type is a FINDING, not an exception. This module
# is asked "is this draft fit to become an official record, and if not, where is it
# wrong"; for a wrong-typed container the answer is *no, here*. Raising instead denies
# the reader the one answer their record's own validator exists to give — and unlike a
# malformed REQUEST, which the caller sent and can be told to fix, a malformed
# PERSISTED document is not the reader's fault and refusing it hides their record.
#
# The container is then treated as EMPTY for the rest of the pass. Not coerced, not
# guessed at, and NOT walked: `enumerate("abc")` would file three per-position claims
# invented out of a string's characters, which `serialize.py`'s per-item isolation note
# names as "a fabricated partial success, which is worse than the failure it replaced".
# Nothing here may assume what the container was meant to hold (CLAUDE.md §5).
#
# DELIBERATELY LIMITED TO THE TOP LEVEL. Nested payloads — a field envelope's
# `evidence`, `attribution.contributors` — still raise, and `routes._probe_override`
# depends on that: it catches `_PROBE_STRUCTURAL_ERRORS` to turn a malformed request
# into a typed 422. Widening this into them would make both `except` branches dead and
# would replace a refusal the caller can act on with a stored-then-refused override.
_TOP_LEVEL_CONTAINERS: dict[str, type] = {
    "meta": dict,
    "fields": dict,
    "block_evidence": dict,
    "qc": dict,
    "attribution": dict,
    "assets": list,
    "descriptors_outputs": list,
    "implicit": list,
    "series": list,
    "links": list,
}

#: Neutral English for a JSON type. The stored VALUE is never interpolated into a
#: message: the reader is told what SHAPE was found, not handed arbitrary content back
#: rendered as though it were the validator's own words. `serialize._JSON_KIND` took
#: the same decision for the same reason.
_JSON_KIND: dict[type, str] = {
    bool: "a boolean",
    int: "a number",
    float: "a number",
    str: "a string",
    dict: "an object",
    list: "a list",
    type(None): "null",
}

_CONTAINER_SHAPE: dict[type, str] = {dict: "an object", list: "a list"}


def _kind(value: object) -> str:
    # `bool` before `int`: `type(True) is bool`, so the dict lookup is already exact,
    # but a future `isinstance` rewrite here would get it wrong in the usual way.
    return _JSON_KIND.get(type(value), "a value of an unreadable type")


def _container(report: DraftReport, draft: dict, name: str):
    """The named top-level container, or an EMPTY one of the right type plus a finding.

    A FALSY wrong type keeps its long-standing normalisation: `draft.get("assets") or
    []` has always read `0`, `""` and `False` as "no assets", exactly as
    `workspace._hydrate_notes` reads a non-list `notes` as no notes. That tolerance is
    not obviously right, but it is not this guard's to change — altering it would move
    the verdict on drafts nobody reported a defect about. Only a TRUTHY wrong type,
    which is the shape that used to raise, is reported.
    """
    expected = _TOP_LEVEL_CONTAINERS[name]
    raw = draft.get(name)
    if not raw:
        return expected()
    if isinstance(raw, expected):
        return raw
    report.err(
        name,
        f"must be {_CONTAINER_SHAPE[expected]}; this draft stores {_kind(raw)}. "
        f"A container of another type is refused rather than walked — nothing here "
        f"can assume what it was meant to hold, and reading positions out of it "
        f"would invent claims the draft never made.",
    )
    return expected()


#: What ONE item of a walked LIST has to be, in the reader's words.
#:
#: THE FIVE TOP-LEVEL LIST CONTAINERS, PLUS THE TWO NESTED LISTS THIS MODULE WALKS.
#: ~~"Only the five list containers appear: a dict container's items are its VALUES,
#: which each reader already type-checks for itself (`fields` files 'must be a field
#: envelope', `block_evidence` goes through `_claim_covered`)."~~ **That justification
#: was FALSE for its second example and is kept struck rather than deleted, because the
#: falsity was a live HTTP 500 rather than a wording slip.** `_claim_covered` was
#: `any(isinstance(e, dict) for e in (entries or []))` — it ITERATED the value instead
#: of type-checking it, so `block_evidence = {"series:s": 7}` raised `TypeError: 'int'
#: object is not iterable` and `GET /api/experiments/{id}` answered **500** (measured on
#: `724ce58`). The `fields` half was and remains true. Dict containers are now genuinely
#: covered, by `_cited_sources`, which is the type check the comment claimed existed.
#:
#: `descriptors` and `contributors` are NESTED lists, and they are here because the
#: item guard stopping at the top level left them raising: `{"descriptors_outputs":
#: [{"descriptors": [7]}]}` reached `d.get("value")` and raised `AttributeError`, also a
#: 500 on the same route. They are the only two nested lists `validate_draft` walks
#: position-by-position, so the table is complete for what this module iterates rather
#: than complete for the draft format.
_ITEM_NOUNS: dict[str, str] = {
    "assets": "an asset object",
    "descriptors_outputs": "a descriptors-output object",
    "implicit": "an implicit-claim object",
    "series": "a series object",
    "links": "a link object",
    "descriptors": "a descriptor object",
    "contributors": "a contributor object",
}

def _nested_list(report: DraftReport, owner: dict, key: str, where: str) -> list:
    """A nested list a walker is about to enumerate, or an EMPTY one plus a finding.

    The top-level `_container` guard cannot reach these: `descriptors_outputs[j]
    ["descriptors"]` and `attribution["contributors"]` are one level down, and
    `enumerate(7)` raised out of both. A truthy non-list is refused rather than walked,
    for `_container`'s reason — `enumerate("abc")` would file three per-position
    findings invented out of a string's characters. The falsy normalisation the rest of
    this module lives by (`or []` reading `0`/`""`/`False` as empty) is preserved.
    """
    raw = owner.get(key)
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    report.err(
        where,
        f"must be a list; this draft stores {_kind(raw)}. The value is refused rather "
        f"than walked — nothing here can assume what it was meant to hold, and reading "
        f"positions out of it would invent claims the draft never made.",
    )
    return []


def _mapping_items(report: DraftReport, container: list, name: str, *, where: str | None = None):
    """``(index, item)`` for every item of a walked list that IS a mapping, with a
    finding filed at ``where[index]`` (default ``name[index]``) for every item that is
    not. ``where`` exists only so a NESTED list can file at its real position
    (``descriptors[0][1]``) while still naming its item type from ``name``.

    **THE MEASURED DEFECT.** ``_container`` guards the CONTAINER's type, so
    ``{"assets": "not a list"}`` became a finding — but a well-formed list holding a
    wrong-typed ITEM still reached ``asset.get("sha256")`` and raised. Measured on
    ``1ad1f8f``, one truthy wrong-typed item at a time, ``validate_draft`` raising
    rather than reporting: ``{"assets": [7]}``, ``{"descriptors_outputs": [7]}``,
    ``{"implicit": [7]}``, ``{"series": [7]}``, ``{"links": [7]}`` — all
    ``AttributeError``. ``test_a_wrong_typed_ITEM_inside_a_well_formed_list_still_raises``
    pinned that and said to invert it "when that decision is made"; this is the
    decision, and the test is inverted rather than deleted.

    **THE ANSWER IS A REPORT, for the same reason ``_container``'s is.** This module is
    asked "is this draft fit to become an official record, and if not, where is it
    wrong". For an item of the wrong type the answer is *no, here* — and raising denies
    the reader the answer their own record's validator was asked for, which on the read
    path is an HTTP 500 over a document they did not write.

    **THE ITEM IS NOT WALKED.** Nothing here can assume what a number or a string was
    meant to hold, and deriving per-field claims from it would invent findings the draft
    never made — ``serialize.py``'s per-item note calls that "a fabricated partial
    success, which is worse than the failure it replaced". It is not repaired either:
    this function reads and reports, and never writes to ``draft``.

    **THE POSITION IS REAL, so it is used.** ``name[index]`` locates the item inside a
    container that genuinely IS a list, which is what distinguishes this from the
    per-position claims invented out of a dict's keys or a string's characters that
    ``serialize.py`` measured. The stored VALUE is never quoted — only its shape.

    **~~NESTED ITEMS STILL RAISE~~ — NARROWED to ONE nested list, and the narrowing is
    the point rather than a relaxation.** The old absolute is struck because this
    function now also walks ``descriptors_outputs[j]["descriptors"]``, whose items used
    to raise ``AttributeError`` and answer HTTP 500 on a persisted document nobody could
    fix. What is UNCHANGED, deliberately, is ``attribution["contributors"]``:
    ``routes._refuse_override_payload`` probes a client's override payload through
    ``validate_draft`` and catches ``_PROBE_STRUCTURAL_ERRORS`` to answer a typed 422 —
    the honest answer for a malformed REQUEST, which the caller can fix — and its BLOCK
    probe filters the report to ``UPLOADED_BY_PATH`` alone. So a finding filed against a
    contributor index is DISCARDED by that route, and a guard here would turn its 422
    into a stored malformed override rather than into a better message. Guarding
    ``contributors`` therefore requires a paired change in ``routes.py`` and is
    deliberately not made here. (The ``fields.*.evidence`` half of that rationale DID
    move: ``_cited_sources`` now files its finding at ``fields.<path>``, which is
    exactly the address that route's FIELD probe collects, so the same payload is still
    refused ``422 invalid_envelope`` — with the validator's own words instead of a
    quoted stand-in. Pinned by test over HTTP.)
    """
    at = where or name
    for index, item in enumerate(container):
        if isinstance(item, dict):
            yield index, item
            continue
        report.err(
            f"{at}[{index}]",
            f"must be {_ITEM_NOUNS[name]}; this draft stores {_kind(item)}. The item "
            f"is refused rather than walked — nothing here can assume what it was "
            f"meant to hold, and reading fields out of it would invent claims the "
            f"draft never made.",
        )


def validate_draft(draft: dict) -> DraftReport:
    report = DraftReport()

    meta = _container(report, draft, "meta")
    for key in ("record_type", "record_domain", "source_type"):
        if not meta.get(key):
            report.err(f"meta.{key}", "required to classify the record before export")

    fields = _container(report, draft, "fields")
    for path, env in fields.items():
        if not isinstance(env, dict):
            report.err(f"fields.{path}", "must be a field envelope")
            continue
        _check_envelope(report, f"fields.{path}", env)

    for i, asset in _mapping_items(report, _container(report, draft, "assets"), "assets"):
        sha = asset.get("sha256")
        if not sha:
            report.err(f"assets[{i}]", "asset requires a sha256 (raw data is linked + hashed, not copied)")
        elif not isinstance(sha, str):
            # `_SHA256_RE.match(7)` raised `TypeError: expected string or bytes-like
            # object` — measured as a 500 on `GET /api/experiments/{id}` at `724ce58`.
            # The SHAPE is named and the stored value is NOT quoted, unlike the digest
            # branch below: a digest is a fixed-width hex string a reader can compare,
            # whereas an arbitrary stored value is content this module does not echo.
            report.err(
                f"assets[{i}]",
                f"sha256 must be a string; this draft stores {_kind(sha)}. A digest of "
                f"another type is refused rather than matched — CLAUDE.md §5 forbids "
                f"inventing a sha256, and coercing one would do exactly that.",
            )
        elif not _SHA256_RE.match(sha):
            report.err(f"assets[{i}]", f"sha256 {sha!r} is not a 64-char lowercase hex digest")
        _check_claim(report, f"assets[{i}] ({asset.get('asset_id', '?')})", asset.get("evidence"))

    for j, out in _mapping_items(
        report, _container(report, draft, "descriptors_outputs"), "descriptors_outputs"
    ):
        # `descriptors` is a NESTED list, so `_container`'s guard never reached it and
        # `_mapping_items`' did not either: `{"descriptors_outputs": [{"descriptors":
        # [7]}]}` reached `d.get("value")` and raised `AttributeError` — 500 on `GET
        # /api/experiments/{id}`, measured at `724ce58`. Both levels are guarded now.
        for k, d in _mapping_items(
            report,
            _nested_list(report, out, "descriptors", f"descriptors[{j}]"),
            "descriptors",
            where=f"descriptors[{j}]",
        ):
            if d.get("value") is None:
                report.err(f"descriptors[{j}][{k}]", "descriptor value must not be null — it is a scientific claim")
            _check_claim(report, f"descriptor '{d.get('name', '?')}'", d.get("evidence"))

    for m, imp in _mapping_items(report, _container(report, draft, "implicit"), "implicit"):
        _check_claim(report, f"implicit '{imp.get('about', '?')}'", imp.get("evidence"))

    # Block-level provenance coverage. The official record cannot carry per-field
    # evidence for series/qc/links/attribution, so drafts cite it in a block_evidence
    # natural-key map. Each block below CONSTRUCTS its key from draft content and
    # requires a covered entry — a fabricated spectrum, an unevidenced qc verdict, or
    # an unsourced link/contributor is refused here, before export.
    block_evidence = _container(report, draft, "block_evidence")

    # Series: every spectrum must cite its reduction source or be user-confirmed.
    seen_series: set[str] = set()
    # BOUND ONCE, and read again by the qc gate below, so the finding about an
    # unreadable `series` is filed exactly once and both readers see the same value.
    series = _container(report, draft, "series")
    # THE READABLE SPECTRA, NOT THE STORED LIST — see the qc gate below for why this is
    # materialised instead of iterated lazily.
    series_items = list(_mapping_items(report, series, "series"))
    for i, s in series_items:
        series_id = s.get("series_id")
        where = f"series[{i}] ({series_id if isinstance(series_id, str) else '?'})"
        if not series_id:
            report.err(where, "series has no series_id — cannot key its evidence")
            continue
        if not isinstance(series_id, str):
            # `series_id in seen_series` raised `TypeError: unhashable type: 'dict'` for
            # a truthy object or list — measured as a 500 on `GET
            # /api/experiments/{id}` at `724ce58` with `series_id = {"a": 1}`. (The
            # review reported the same defect for `series_id = {}`; that value is FALSY
            # and takes the branch above, so it answers 200. The corrected repro is the
            # truthy one.) A HASHABLE non-string — `7`, `1.5`, `True` — never raised,
            # and is refused here too rather than being coerced into the evidence key
            # `f"series:{series_id}"`: the key is what an evidence entry is filed under,
            # and str()-ing a number into it invents a name the draft never wrote. That
            # is the ONE verdict this guard can move on a draft that used to have one,
            # and the §13 disclosure states it rather than claiming it cannot happen.
            report.err(
                where,
                f"series_id must be a string; this draft stores {_kind(series_id)}. It "
                f"is the key this spectrum's evidence is filed under, so a value of "
                f"another type is refused rather than coerced into one.",
            )
            continue
        if series_id in seen_series:
            report.err(f"series[{i}]", f"duplicate series_id '{series_id}' — evidence key not unique")
            continue
        seen_series.add(series_id)
        if _block_uncited(report, where, block_evidence.get(f"series:{series_id}")):
            report.err(where, "series has no evidence; a spectrum must cite its reduction source or be user-confirmed")

    # QC: a measurement with series must carry an evidenced qc verdict (no default 'valid').
    #
    # `series_items`, NOT `series` AND NOT `draft.get("series")`. THE SAME DEFECT HAS NOW
    # BEEN FOUND TWICE, ONE LEVEL APART, and the comment that used to sit here described
    # the first as past tense while the second was live. #177 changed `draft.get("series")`
    # to `series` because a truthy-but-unreadable CONTAINER satisfied this gate by
    # truthiness alone. An independent review then measured the ITEM case at `724ce58`:
    # `_container` returns `[7]` unchanged, so `if series:` was still true and
    # `validate_draft({"series": [7]})` reported errors `['series[0]', 'qc']` — the
    # second being a claim about the QC verdict of a spectrum this module had just
    # refused to read, which is exactly what the old comment said no longer happened.
    #
    # `series_items` holds only the items that ARE readable spectra, so the gate now
    # fires when and only when the draft carries at least one spectrum this module could
    # read. A draft whose every series item is junk gets the per-item findings and no
    # qc claim; a draft mixing one readable spectrum with one junk item gets both, which
    # is right — there IS a spectrum, and it does need a verdict.
    if series_items:
        qc = _container(report, draft, "qc")
        if not qc.get("status"):
            report.err("qc", "measurement has series but qc verdict has no evidence; confirm or supply provenance (no default 'valid')")
        elif _block_uncited(report, "qc", block_evidence.get("qc:status")):
            report.err("qc", "measurement has series but qc verdict has no evidence; confirm or supply provenance (no default 'valid')")

    # Links: each cross-record link must cite its basis; tuple keys must be unique.
    seen_links: set[str] = set()
    for i, link in _mapping_items(report, _container(report, draft, "links"), "links"):
        where = f"links[{i}]"
        rel, target, basis = link.get("rel"), link.get("target"), link.get("basis")
        if not (rel and target and basis):
            report.err(where, "link missing required rel/target/basis — cannot key its evidence")
            continue
        key = f"links:{rel}|{target}|{basis}"
        if key in seen_links:
            report.err(where, f"duplicate link {rel}|{target}|{basis} — evidence key not unique")
            continue
        seen_links.add(key)
        if _block_uncited(report, where, block_evidence.get(key)):
            report.err(where, "link has no evidence; a cross-record link must cite its basis or be user-confirmed")

    # Attribution: `uploaded_by` is refused outright, and each contributor must cite
    # its source; name|role keys must be unique.
    attribution = _container(report, draft, "attribution")

    # `attribution.uploaded_by` is not a field a draft may author. The official schema
    # declares it SERVER-STAMPED from the authenticated identity at ingestion, with any
    # client value overwritten ("tamper-proof attribution", D. Sokaras 2026-06-15) — and
    # ISAAC has no trusted identity to stamp it with (nothing in the app reads an
    # authenticated principal; see docs/identity-trust-contract.md §6A). So there is no
    # evidence that could make a draft-supplied value true: evidence can show that a
    # document NAMES someone, never that the server AUTHENTICATED them. Letting it pass
    # would launder a client string into a field readers are told is tamper-proof, and
    # it can name a real person. Refuse, fail closed. This is key-presence, not
    # truthiness: a null, an empty string and an envelope are all refused, because each
    # asserts authorship of a server-owned field.
    #
    # TWO refusals, because there are two ways a draft can express the field, and the
    # first attempt at this fix guarded only the block. `where` names the mechanism so a
    # user can tell which one they used; the message is one shared constant.
    if isinstance(attribution, dict) and UPLOADED_BY_PATH.split(".")[1] in attribution:
        report.err(UPLOADED_BY_PATH, UPLOADED_BY_REFUSAL)
    for path in _paths_authoring_uploaded_by(fields):
        report.err(f"fields[{path!r}]", UPLOADED_BY_REFUSAL)
    # THE SIDECAR-ONLY MECHANISMS (`implicit[].about`, `block_evidence` keys) ARE
    # DELIBERATELY NOT REFUSED. An earlier revision of this branch refused them, to keep
    # every spelling loud rather than silently filtered. That was withdrawn together with
    # the sidecar filter it paired with — see the long note in `export.build_sidecar`. In
    # short: the sidecar is unvalidated free text that legitimately carries names and
    # quotes, so matching keys that merely LOOK like this field guarded nothing, and the
    # refusal's normalising comparison over-matched (it would have rejected a
    # `block_evidence` key a user wrote as `implicit:...`). The official record is where a
    # server-stamped identity is asserted, and that is guarded above and in `export`.
    seen_contrib: set[str] = set()
    # THIS ONE STILL RAISES, AND IT IS THE ONLY WALK IN THIS MODULE THAT DOES.
    # `{"contributors": 7}` raises `TypeError` out of `enumerate`, and
    # `{"contributors": ["not-a-dict"]}` raises `AttributeError` out of `c.get`. Both
    # are ALSO reachable on a persisted document, where they answer HTTP 500 on `GET
    # /api/experiments/{id}` — so this is a known, named residue, not a case nobody
    # found. It is left because closing it HERE, alone, would make a live route less
    # safe: `routes._refuse_override_payload` catches exactly these two
    # (`_PROBE_STRUCTURAL_ERRORS`) to answer `422 invalid_block_payload` for a
    # client-authored `block:attribution` override, and its block probe then filters the
    # report to `UPLOADED_BY_PATH` alone — so a finding filed at
    # `attribution.contributors[i]` is DISCARDED and the malformed override would be
    # STORED with 200. The fix is a paired change in `routes.py` (collect the shape
    # findings, or refuse on report rather than on exception) and belongs in the slice
    # that owns that file. Until then the raise is the thing keeping the write refused.
    for i, c in enumerate(attribution.get("contributors") or []):
        where = f"attribution.contributors[{i}]"
        name, role = c.get("name"), c.get("role")
        if not (name and role):
            report.err(where, "contributor missing name/role — cannot key its evidence")
            continue
        key = f"attribution:{name}|{role}"
        if key in seen_contrib:
            report.err(where, f"duplicate contributor {name}|{role} — evidence key not unique")
            continue
        seen_contrib.add(key)
        if _block_uncited(report, where, block_evidence.get(key)):
            report.err(where, "contributor has no evidence; attribution must cite its source or be user-confirmed")

    # Tags are user-authored grouping labels — authorship IS the confirmation, so they
    # are deliberately exempt from evidence coverage (no check here, by design).

    # Unsupported scientific blocks: refuse (do not silently drop) any block the XANES
    # MVP exporter has no path for — dropping scientific values violates no-guessing.
    for name in ("processing", "computation"):
        if name in draft:
            report.err(name, f"unsupported scientific block '{name}' — out of XANES MVP scope; the exporter has no path for it")
    measurement = draft.get("measurement")
    if isinstance(measurement, dict) and "processing" in measurement:
        report.err("measurement.processing", "unsupported scientific block 'measurement.processing' — out of XANES MVP scope; the exporter has no path for it")

    return report
