"""P26.1 — Workspace Search Core (pure, deterministic, truth-plane workspace helper).

This module is a PURE function over an already-materialised list of ``Experiment``
snapshots. Given a query string it returns a ranked, paginated set of *leads* — a
title, an experiment id, an exported record id, a confirmed draft field, a pending
blocker, an evidence entry, a source-file reference, or an exported artifact — each
carrying just enough to route a client to the right screen.

Governance boundary (there are tests for every clause):

* It is a **truth-plane read/navigation helper** that computes NO verdict — never a
  validation authority. It reshapes only content the workspace already exposes over its
  existing read endpoints. It decides nothing about validity/exportability, and imports
  no truth-core checker or exporter.
* It performs **no filesystem access of its own**. It reads only the in-memory
  attributes/derived views of the injected ``Experiment`` objects (``.id``, ``.title``,
  ``.record_id``, ``.source``, ``.draft`` and the derived ``.status()``); it never
  touches an experiment's directory, record path, sidecar path or state path, and it
  never walks a directory. The derived ``exp.status()`` it calls MAY transitively run
  the truth-core exporter as a repo-schema-only dry-run (never a workspace-directory
  read and never a verdict), which is why removing an experiment's workspace directory
  cannot make search raise. Consuming the hardened ``list_experiments()`` snapshot means
  a directory removed by a concurrent reset can never make search raise (P26.0b
  read-race contract).
* Emitted strings never surface an absolute/filesystem path, ``examples/`` fixtures,
  a sidecar filename, a records directory, or verdict keys/language. The only
  leading-slash value is ``navigate_to`` — a client route ``/record/<id>[...]``.

Stdlib only (``re``, ``unicodedata``, ``dataclasses``, ``typing``).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:  # typing only — never a runtime import of the store or the truth core
    from isaac_api.workspace import Experiment


# --- public constants ---------------------------------------------------------

PLANE = "truth"
PROVIDER = "workspace-store"

DEFAULT_LIMIT = 10
MAX_RESULTS = 50  # hard cap on total materialized results
MIN_QUERY_LEN = 2  # measured after normalization
QUERY_TOO_SHORT = "query_too_short"

_MAX_INPUT_LEN = 256  # raw query truncated to this before normalization (determinism)
_SNIPPET_WHOLE_MAX = 120  # values at or below this are echoed whole
_SNIPPET_WINDOW = 80  # window width for long text (locators / quotes)


# --- match tiers + facet priorities -------------------------------------------
#
# Ranking is a fully deterministic ascending tuple; smaller sorts first:
#
#   1. tier rank          exact(0) < prefix(1) < token(2) < substring(3)
#   2. facet priority     title(0) < id(1) < record_id(2) < draft_field(3)
#                         < pending(4) < evidence(5) < source_ref(6) < artifact(7)
#   3. created_utc        ascending (stable ISO string compare)
#   4. experiment id      ascending
#   5. match.field        ascending — final tie-break. Two non-asset pending blockers
#                         of the same kind can share a match.field, so uniqueness is
#                         NOT the guarantee: deterministic candidate/experiment
#                         iteration plus Python's stable sort make the total order
#                         reproducible and pagination non-overlapping.

_TIER_RANK = {"exact": 0, "prefix": 1, "token": 2, "substring": 3}

_P_TITLE = 0
_P_ID = 1
_P_RECORD_ID = 2
_P_DRAFT_FIELD = 3
_P_PENDING = 4
_P_EVIDENCE = 5
_P_SOURCE_REF = 6
_P_ARTIFACT = 7


# --- result shape (frozen dataclasses) ----------------------------------------


@dataclass(frozen=True)
class MatchInfo:
    field: str
    snippet: str
    reason: str
    tier: str
    offsets: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class WorkspaceResult:
    kind: str
    experiment_id: str
    record_id: str | None
    title: str
    label: str
    status: str | None
    match: MatchInfo
    navigate_to: str
    plane: str = PLANE
    source: str = PROVIDER


@dataclass(frozen=True)
class WorkspaceSearchResults:
    query: str
    normalized_query: str
    total: int
    returned: int
    limit: int
    offset: int
    reason: str | None
    results: tuple[WorkspaceResult, ...]
    available: bool = True


# --- normalization ------------------------------------------------------------


def normalize(text: str) -> str:
    """Deterministic normalization: NFC, casefold, whitespace collapsed to spaces.

    Leading/trailing/internal runs of whitespace all collapse to a single space,
    so ``"  New   Draft  "`` and ``"new draft"`` compare equal.
    """
    nfc = unicodedata.normalize("NFC", text)
    return " ".join(nfc.casefold().split())


def _normalize_query(query: str) -> str:
    # Cap the raw input first so an unbounded query stays bounded work.
    return normalize((query or "")[:_MAX_INPUT_LEN])


# --- matching -----------------------------------------------------------------


def _tier(field_cf: str, query_cf: str, tokens: tuple[str, ...]) -> str | None:
    """Best matching tier of a normalized field text against the normalized query.

    Token-AND is enforced at every tier: a match requires EVERY query token to be
    present. Returns ``None`` when the field does not match at all.
    """
    if not field_cf:
        return None
    if field_cf == query_cf:
        return "exact"
    if field_cf.startswith(query_cf):
        return "prefix"
    field_tokens = field_cf.split()
    if all(t in field_tokens for t in tokens):
        return "token"
    if all(t in field_cf for t in tokens):
        return "substring"
    return None


def _snippet_and_offsets(
    text: str, tokens: tuple[str, ...]
) -> tuple[str, tuple[tuple[int, int], ...]]:
    """A safe, deterministic snippet of ``text`` plus token offsets within it.

    Short values are echoed whole; long text is windowed around the first token
    hit. Offsets index into the returned snippet so a client can highlight without
    any server-authored HTML. Snippets echo already-served data only.
    """
    cf = text.casefold()
    # Earliest position at which any token occurs (drives the window origin).
    first = None
    for t in tokens:
        i = cf.find(t)
        if i != -1 and (first is None or i < first):
            first = i
    if first is None:
        first = 0

    if len(text) <= _SNIPPET_WHOLE_MAX:
        snippet = text
    else:
        start = max(0, first - _SNIPPET_WINDOW // 2)
        snippet = text[start : start + _SNIPPET_WINDOW]

    scf = snippet.casefold()
    offsets: list[tuple[int, int]] = []
    for t in tokens:
        idx = scf.find(t)
        if idx != -1:
            offsets.append((idx, idx + len(t)))
    ordered = tuple(sorted(set(offsets)))
    if not ordered:
        # Defensive: a matched candidate always has at least one in-snippet token,
        # but never return an empty offsets tuple.
        ordered = ((0, min(len(snippet), 1)),)
    return snippet, ordered


# --- candidate model ----------------------------------------------------------
#
# A "candidate" is one searchable aspect of an experiment. Multi-aspect facets
# (draft field, pending blocker, evidence entry) collapse to a single best-tier
# aspect so each field-path/entry yields at most one result.


@dataclass(frozen=True)
class _Aspect:
    text: str  # original text (drives the snippet — echoes served data)
    reason: str
    field: str


@dataclass(frozen=True)
class _Candidate:
    kind: str
    priority: int
    navigate_suffix: str
    label: str
    aspects: tuple[_Aspect, ...]


def _label_from_path(path: str) -> str:
    """Humanize the last dotted segment (mirrors ``serialize._label``)."""
    last = path.split(".")[-1]
    return last.replace("_", " ").strip().title()


def _blocker_id(entry: dict) -> str:
    """Stable blocker id (mirrors ``serialize.blocker_id``): asset -> uri, else kind."""
    if entry.get("kind") == "asset":
        return entry.get("uri") or "asset"
    return entry.get("kind") or "blocker"


def _is_pathlike(s) -> bool:
    """True when a string looks like a filesystem/absolute path that must never be
    emitted as a lead. Deliberately does NOT flag scheme URIs like 'ssrl-archive://'
    (those are already-served legitimate leads)."""
    if not isinstance(s, str) or not s:
        return False
    if s[:1] in ("/", "\\"):
        return True
    for frag in ("examples/", "/records/", ".evidence.json", "/tmp/", "/var/",
                 "/private/", "/Users/", "/home/", "/app/", "/data/", "/root/"):
        if frag in s:
            return True
    return False


def _evidence_owner_label(owner: str, ev: dict) -> str:
    """Short, path-free label for an evidence hit: a source basename or a fallback."""
    sf = ev.get("source_file")
    if isinstance(sf, str) and sf and not _is_pathlike(sf):
        return sf
    return _label_from_path(owner) if owner else "Evidence"


_EVIDENCE_ASPECTS = (
    ("source_type", "source type"),
    ("source_file", "source file"),
    ("locator", "locator"),
    ("quote", "quote"),
    ("rule", "rule"),
)


def _candidates(exp: "Experiment") -> list[_Candidate]:
    """Every searchable candidate for one experiment (in-memory reads only)."""
    out: list[_Candidate] = []
    exp_id = exp.id
    title = exp.title or ""

    # experiment title
    out.append(
        _Candidate(
            kind="experiment",
            priority=_P_TITLE,
            navigate_suffix="",
            label=title,
            aspects=(_Aspect(title, "matched experiment title", "title"),),
        )
    )
    # experiment id
    out.append(
        _Candidate(
            kind="experiment",
            priority=_P_ID,
            navigate_suffix="",
            label=title,
            aspects=(_Aspect(exp_id, "matched experiment identifier", "id"),),
        )
    )
    # exported record id
    if exp.record_id is not None:
        out.append(
            _Candidate(
                kind="record_id",
                priority=_P_RECORD_ID,
                navigate_suffix="",
                label=exp.record_id,
                aspects=(_Aspect(exp.record_id, "matched record identifier", "record_id"),),
            )
        )

    draft = exp.draft or {}

    # confirmed draft fields
    for path, env in (draft.get("fields") or {}).items():
        if not isinstance(env, dict):
            continue
        value = env.get("value")
        aspects: list[_Aspect] = []
        if value is not None:
            aspects.append(
                _Aspect(str(value), "matched draft field value", f"draft.{path}.value")
            )
        aspects.append(
            _Aspect(_label_from_path(path), "matched draft field label", f"draft.{path}.label")
        )
        aspects.append(_Aspect(path, "matched draft field path", f"draft.{path}.path"))
        status = env.get("status")
        if status is not None:
            aspects.append(
                _Aspect(str(status), "matched draft field status", f"draft.{path}.status")
            )
        out.append(
            _Candidate(
                kind="draft_field",
                priority=_P_DRAFT_FIELD,
                navigate_suffix="/evidence",
                label=_label_from_path(path),
                aspects=tuple(aspects),
            )
        )

    # pending blockers (leads to the completion screen)
    for entry in draft.get("pending") or []:
        if not isinstance(entry, dict):
            continue
        bid = _blocker_id(entry)
        aspects = []
        question = entry.get("question")
        if question is not None:
            aspects.append(
                _Aspect(str(question), "matched pending field question", f"pending.{bid}.question")
            )
        aspects.append(_Aspect(bid, "matched pending field name", f"pending.{bid}.name"))
        out.append(
            _Candidate(
                kind="draft_field",
                priority=_P_PENDING,
                navigate_suffix="/complete",
                label=(entry.get("kind") or "pending").replace("_", " ").title(),
                aspects=tuple(aspects),
            )
        )

    # evidence entries: draft field envelopes + implicit + assets
    def _emit_evidence(owner: str, ev_list, tag: str) -> None:
        for idx, ev in enumerate(ev_list or []):
            if not isinstance(ev, dict):
                continue
            aspects = []
            for key, human in _EVIDENCE_ASPECTS:
                val = ev.get(key)
                if isinstance(val, str) and val:
                    aspects.append(
                        _Aspect(
                            val,
                            f"matched evidence {human}",
                            f"evidence.{tag}.{idx}.{key}",
                        )
                    )
            if aspects:
                out.append(
                    _Candidate(
                        kind="evidence",
                        priority=_P_EVIDENCE,
                        navigate_suffix="/evidence",
                        label=_evidence_owner_label(owner, ev),
                        aspects=tuple(aspects),
                    )
                )

    for path, env in (draft.get("fields") or {}).items():
        if isinstance(env, dict):
            _emit_evidence(path, env.get("evidence"), path)
    for i, imp in enumerate(draft.get("implicit") or []):
        if isinstance(imp, dict):
            about = imp.get("about") or f"implicit_{i}"
            _emit_evidence(f"implicit:{about}", imp.get("evidence"), f"implicit:{about}")
    for i, asset in enumerate(draft.get("assets") or []):
        if isinstance(asset, dict):
            aid = asset.get("asset_id") or asset.get("uri") or f"asset_{i}"
            _emit_evidence(f"assets:{aid}", asset.get("evidence"), f"assets:{aid}")

    # source references (bare basenames + free-text description)
    source = exp.source or {}
    files = [f for f in (source.get("files") or []) if isinstance(f, str) and f]
    if files:
        out.append(
            _Candidate(
                kind="source_ref",
                priority=_P_SOURCE_REF,
                navigate_suffix="",
                label=files[0],
                aspects=tuple(
                    _Aspect(f, "matched source file reference", "source.files") for f in files
                ),
            )
        )
    description = source.get("description")
    if isinstance(description, str) and description:
        out.append(
            _Candidate(
                kind="source_ref",
                priority=_P_SOURCE_REF,
                navigate_suffix="",
                label="Source files",
                aspects=(
                    _Aspect(description, "matched source description", "source.description"),
                ),
            )
        )

    # exported artifact lead (only when a record was produced)
    if exp.record_id is not None:
        out.append(
            _Candidate(
                kind="artifact",
                priority=_P_ARTIFACT,
                navigate_suffix="/export",
                label="Exported record",
                aspects=(
                    _Aspect("Exported record", "matched exported artifact", "artifact.label"),
                    _Aspect(exp.record_id, "matched exported artifact", "artifact.record_id"),
                ),
            )
        )

    return out


# --- ranked row ---------------------------------------------------------------


@dataclass(frozen=True)
class _Ranked:
    sort_key: tuple
    result: WorkspaceResult


def _best_aspect(
    cand: _Candidate, query_cf: str, tokens: tuple[str, ...]
) -> tuple[str, _Aspect] | None:
    """Choose the single best-tier aspect of a candidate (ties favor aspect order)."""
    best: tuple[int, int, str, _Aspect] | None = None
    for order, asp in enumerate(cand.aspects):
        # Governance: a path-like value/quote/locator/source_file can never match and
        # so is never snippeted. Safe aspects of the same candidate remain eligible,
        # so the sanitizer is surgical, not over-broad.
        if _is_pathlike(asp.text):
            continue
        tier = _tier(normalize(asp.text), query_cf, tokens)
        if tier is None:
            continue
        rank = _TIER_RANK[tier]
        if best is None or rank < best[0]:
            best = (rank, order, tier, asp)
    if best is None:
        return None
    return best[2], best[3]


def _rank_candidate(
    exp: "Experiment",
    status: str | None,
    cand: _Candidate,
    query_cf: str,
    tokens: tuple[str, ...],
) -> _Ranked | None:
    chosen = _best_aspect(cand, query_cf, tokens)
    if chosen is None:
        return None
    tier, asp = chosen
    snippet, offsets = _snippet_and_offsets(asp.text, tokens)
    # Governance: even when a SAFE aspect matched, the candidate's own label could
    # still be path-like (e.g. an evidence entry whose source_type matched but whose
    # source_file basename is an examples/ path). Replace any path-like label with a
    # neutral, kind-appropriate, path-free fallback so no emitted label leaks a path.
    label = cand.label
    if _is_pathlike(label):
        _LABEL_FALLBACK = {
            "evidence": "Evidence",
            "source_ref": "Source files",
            "artifact": "Exported record",
            "record_id": exp.record_id if not _is_pathlike(exp.record_id) else "Record",
            "experiment": "Experiment",
            "draft_field": "Draft field",
        }
        label = _LABEL_FALLBACK.get(cand.kind, "Lead")
    result = WorkspaceResult(
        kind=cand.kind,
        experiment_id=exp.id,
        record_id=exp.record_id,
        title=exp.title or "",
        label=label,
        status=status,
        match=MatchInfo(field=asp.field, snippet=snippet, reason=asp.reason, tier=tier, offsets=offsets),
        navigate_to=f"/record/{exp.id}{cand.navigate_suffix}",
    )
    sort_key = (
        _TIER_RANK[tier],
        cand.priority,
        exp.created_utc,
        exp.id,
        asp.field,
    )
    return _Ranked(sort_key=sort_key, result=result)


# --- public entry point -------------------------------------------------------


def workspace_search(
    query: str,
    experiments: Iterable["Experiment"],
    *,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> WorkspaceSearchResults:
    """Search the injected in-memory experiment snapshots and return ranked leads.

    Pure and deterministic: identical inputs always yield an identical result set.
    A too-short normalized query short-circuits with ``reason=QUERY_TOO_SHORT`` and
    no rows. Otherwise every match across all experiments is collected, ranked,
    truncated to ``MAX_RESULTS`` (that truncated list is ``total``), then paginated.
    """
    normalized = _normalize_query(query)
    clamped_limit = max(0, min(limit, MAX_RESULTS))
    clamped_offset = max(0, offset)

    if len(normalized) < MIN_QUERY_LEN:
        return WorkspaceSearchResults(
            query=query,
            normalized_query=normalized,
            total=0,
            returned=0,
            limit=clamped_limit,
            offset=clamped_offset,
            reason=QUERY_TOO_SHORT,
            results=(),
        )

    tokens = tuple(normalized.split())

    ranked: list[_Ranked] = []
    for exp in experiments:
        status = exp.status()  # derived in-memory view; no workspace file is read here
        for cand in _candidates(exp):
            row = _rank_candidate(exp, status, cand, normalized, tokens)
            if row is not None:
                ranked.append(row)

    ranked.sort(key=lambda r: r.sort_key)

    # Collapse redundant identical leads to the single best-ranked one. Several
    # underlying entries can present the SAME lead to a reader — e.g. three assets
    # in one experiment each citing the same source basename in their evidence —
    # and byte-identical leads (same label AND snippet AND reason AND tier) collapse
    # to one per experiment. Same-value fields with DISTINCT labels are kept, though:
    # facility_name ("Facility Name") and site ("Site") both holding "SSRL" surface as
    # two leads because label is part of the signature. Dedup is by
    # (experiment, kind, label, snippet, reason, tier); it never merges across
    # experiments, so cloned experiments each keep their own leads.
    deduped: list[_Ranked] = []
    seen: set[tuple] = set()
    for row in ranked:
        m = row.result.match
        sig = (row.result.experiment_id, row.result.kind, row.result.label, m.snippet, m.reason, m.tier)
        if sig in seen:
            continue
        seen.add(sig)
        deduped.append(row)

    truncated = deduped[:MAX_RESULTS]
    total = len(truncated)

    page = truncated[clamped_offset : clamped_offset + clamped_limit]
    results = tuple(r.result for r in page)

    return WorkspaceSearchResults(
        query=query,
        normalized_query=normalized,
        total=total,
        returned=len(results),
        limit=clamped_limit,
        offset=clamped_offset,
        reason=None,
        results=results,
    )
