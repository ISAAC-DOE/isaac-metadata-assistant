"""REVIEWED, VERSIONED CONVENTION RULES — what "learning" means in this application.

WHAT THIS IS, AND WHAT IT IS NOT
================================

The project owner asked, on 2026-09-22, for historical import to LEARN: Experiment 1's
sources are reviewed and their conventions approved; Experiment 2 compares against the
approved rules, reuses what matches, surfaces what differs, and a scientist reviews the
new conventions. **That is implemented as reviewed, versioned rule reuse — never as an
opaque model retraining.** No weight, no score, no embedding and no model call exists
anywhere in this module or behind it. A rule is a small, inspectable record a scientist
confirmed, with its scope, its version, the examples it was confirmed from and who (or,
honestly, *that nobody attributable*) confirmed it.

THREE KINDS
===========

* :data:`KIND_PROFILE_BINDING` — "Runs 11-15 of this experiment are named under
  convention Y". Selects the naming convention for a subset of sources.
* :data:`KIND_CONFLICT_RESOLUTION` — "for this conflict, this reading is the right one".
  The only AUTHORITATIVE layer of :mod:`bl15.resolution`'s four; for a record field it
  still goes forward as a PROPOSAL, and acceptance keeps its ``409 human_actor_required``
  gate.
* :data:`KIND_SIGNAL_ASSIGNMENT` — "in this experiment vortDT is Element A's channel and
  vortDT2 is Element B's". What makes a dual-element Run's selection confirmable.

THREE SCOPES, AND NONE OF THEM IS "GLOBAL"
==========================================

* :data:`SCOPE_IMPORT` — **Apply only here.** Stored in the import session, so it is
  exactly as durable as the session (not durable; every response says so).
* :data:`SCOPE_EXPERIMENT` — **Use as a rule for this Experiment.** Stored in the
  experiment's state document at :data:`STATE_KEY`, so it is durable exactly where the
  experiment is and no more.
* :data:`SCOPE_PROFILE` — **Use as a rule for this convention.** ALSO stored on the
  experiment where it was confirmed. It is applied there; in any OTHER experiment it is
  offered as a REUSABLE SUGGESTION — with what it would match and where it would differ —
  and it applies there only once a scientist confirms it for that experiment, which
  records a NEW rule citing this one in ``derived_from``. **A rule is never promoted
  across experiments silently.**

A rule applies only within its recorded scope AND at its recorded convention version: a
binding confirmed against version 1 of a convention is reported as stale — not silently
upgraded — when the registry holds version 2.

NO NEW TABLE, NO MIGRATION
==========================

``DEC-49``'s location, for ``DEC-49``'s reasons: a top-level key of the experiment
state document, beside ``proposals`` and ``extended_context``, read with ``.get`` and a
default so a document written before this key existed hydrates to no rules.
``db_write.OWNED_TABLES`` is unchanged and no migration file exists for this. The key is
OMITTED when empty, so an experiment with no rules serialises byte-identically to one
written before rules existed. It is INSIDE ``workspace._authoritative_signature`` — a rule
is content the experiment holds, and ``save_versioned`` writes nothing when that hash is
unchanged — and OUTSIDE ``draft``, so it is structurally inert to export.

THE ACTOR IS HONEST
===================

``confirmed_by`` is :data:`~isaac_api.activity.ACTOR_UNATTRIBUTED` with the
unattributed trust basis, always, until ``EXT-01`` gives this build a trusted boundary.
It is never read from a forwarded header (``DEC-45``); the pairing is enforced at
construction exactly as :class:`~isaac_api.activity.ActivityEvent` enforces it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .activity import ACTOR_UNATTRIBUTED, TRUST_BASIS_UNATTRIBUTED
from .bl15 import profiles as prof
from .bl15.applicability import (
    BASIS_CONFIRMED_RULE,
    BASIS_IMPORT_CHOICE,
    SCOPE_EXPERIMENT as BINDING_SCOPE_EXPERIMENT,
    SCOPE_RUN_SUBSET,
    SCOPE_SOURCE,
    SCOPE_SOURCE_FAMILY,
    ProfileBinding,
    Selector,
)
from .bl15.signals import BL152_VORTEX, ChannelAssignment

__all__ = [
    "ConventionRule",
    "KIND_CONFLICT_RESOLUTION",
    "KIND_PROFILE_BINDING",
    "KIND_SIGNAL_ASSIGNMENT",
    "RULE_KINDS",
    "RULE_SCOPES",
    "SCOPE_EXPERIMENT",
    "SCOPE_IMPORT",
    "SCOPE_PROFILE",
    "STATE_KEY",
    "UnsupportedRule",
    "active_rules",
    "bindings_from",
    "hydrate",
    "new_rule",
    "state_payload",
]

STATE_KEY = "convention_rules"

KIND_PROFILE_BINDING = "profile_binding"
KIND_CONFLICT_RESOLUTION = "conflict_resolution"
KIND_SIGNAL_ASSIGNMENT = "signal_assignment"
RULE_KINDS: frozenset[str] = frozenset(
    {KIND_PROFILE_BINDING, KIND_CONFLICT_RESOLUTION, KIND_SIGNAL_ASSIGNMENT}
)

SCOPE_IMPORT = "import"
SCOPE_EXPERIMENT = "experiment"
SCOPE_PROFILE = "profile"
RULE_SCOPES: frozenset[str] = frozenset({SCOPE_IMPORT, SCOPE_EXPERIMENT, SCOPE_PROFILE})

#: Bounds. A rule is small by construction; these keep a crafted body from growing an
#: experiment document that is rewritten whole on every save.
MAX_RULES_PER_HOLDER = 500
MAX_SOURCE_EXAMPLES = 5
MAX_TEXT = 2048
MAX_ASSIGNMENTS = 8

_ELEMENT = re.compile(r"^[A-Z][a-z]?$")
#: The source roles a recurring resolution may choose — the meaningful ones only; the
#: absence of a source is never a "reading" to choose.
_CHOOSABLE_ROLES = frozenset(
    {"planned_acquisition", "instrument_header", "human_label", "retrospective_note"}
)
_EDGE = re.compile(r"^(K|L[1-3]|M[1-5])$")


class UnsupportedRule(ValueError):
    """A rule that cannot be recorded without inventing something. A typed 422."""

    def __init__(self, error: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.extra = extra


def _text(value: object, label: str, *, required: bool = True) -> str | None:
    if value is None:
        if required:
            raise UnsupportedRule("missing_field", f"`{label}` is required.", key=label)
        return None
    if not isinstance(value, str):
        raise UnsupportedRule("wrong_type", f"`{label}` must be a string.", key=label)
    text = value.strip()
    if not text:
        if required:
            raise UnsupportedRule(
                "missing_field", f"`{label}` must not be blank.", key=label
            )
        return None
    if len(text) > MAX_TEXT:
        raise UnsupportedRule(
            "too_long", f"`{label}` is longer than a rule stores.", key=label
        )
    return text


def _validated_body(kind: str, body: object) -> dict:
    """The kind-specific body, normalised. Raises :class:`UnsupportedRule`."""
    if not isinstance(body, Mapping):
        raise UnsupportedRule("wrong_type", "`body` must be an object.", key="body")
    if kind == KIND_PROFILE_BINDING:
        unknown = set(body) - {"profile_id", "profile_version"}
        if unknown:
            raise UnsupportedRule(
                "unrecognized_field",
                "A profile binding names a convention and its version, nothing else.",
                keys=sorted(unknown),
            )
        pid = _text(body.get("profile_id"), "body.profile_id")
        profile = prof.profile_for(pid)
        if profile is None:
            raise UnsupportedRule(
                "unknown_profile",
                "That is not a registered naming convention.",
                available=sorted(prof.PROFILES),
            )
        version = _text(body.get("profile_version"), "body.profile_version")
        if version != profile.profile_version:
            raise UnsupportedRule(
                "profile_version_mismatch",
                (
                    "The convention is registered at a different version today. A rule "
                    "is recorded against the version a scientist reviewed, so it cannot "
                    "name one that is not registered."
                ),
                registered_version=profile.profile_version,
            )
        return {"profile_id": profile.profile_id, "profile_version": version}
    if kind == KIND_CONFLICT_RESOLUTION:
        unknown = set(body) - {
            "conflict_id",
            "candidate_id",
            "conflict_kind",
            "chosen_value",
            "chosen_source_role",
            "note",
        }
        if unknown:
            raise UnsupportedRule(
                "unrecognized_field",
                "A conflict resolution names what it resolves and the chosen reading.",
                keys=sorted(unknown),
            )
        conflict = _text(body.get("conflict_id"), "body.conflict_id", required=False)
        candidate = _text(body.get("candidate_id"), "body.candidate_id", required=False)
        recurring = _text(body.get("conflict_kind"), "body.conflict_kind", required=False)
        if sum(x is not None for x in (conflict, candidate, recurring)) != 1:
            raise UnsupportedRule(
                "resolution_target_required",
                "Name exactly one of `conflict_id`, `candidate_id` or `conflict_kind`.",
            )
        # `DEC-46` / `Q16`: TWO ACQUISITIONS UNDER ONE LEGACY NUMBER ARE NEVER
        # RESOLVED. The domain owner does not know which is right (2026-09-22), so
        # the conflict is permanently preserved and no rule may prefer either.
        target_kind = recurring or (conflict.split(":", 1)[0] if conflict else "")
        if target_kind == "duplicate_legacy_number":
            raise UnsupportedRule(
                "resolution_forbidden",
                (
                    "Two distinct acquisitions carrying one legacy number are "
                    "preserved permanently and neither may be preferred — the domain "
                    "owner does not know which is right (2026-09-22; DEC-46, Q16)."
                ),
            )
        out: dict = {
            "conflict_id": conflict,
            "candidate_id": candidate,
            "conflict_kind": recurring,
        }
        if recurring is not None:
            # A RECURRING resolution chooses by the MEANING of a source, within the
            # rule's selector: "for these acquisitions, the human label is the
            # correction". Applied only where exactly one reading has that role.
            role = _text(body.get("chosen_source_role"), "body.chosen_source_role")
            if role not in _CHOOSABLE_ROLES:
                raise UnsupportedRule(
                    "unknown_source_role",
                    "`chosen_source_role` must name a source role.",
                    allowed=sorted(_CHOOSABLE_ROLES),
                )
            if body.get("chosen_value") is not None:
                raise UnsupportedRule(
                    "resolution_target_required",
                    "A recurring resolution chooses by source role, not by value.",
                )
            out["chosen_source_role"] = role
        else:
            out["chosen_value"] = _text(body.get("chosen_value"), "body.chosen_value")
        note = _text(body.get("note"), "body.note", required=False)
        if note is not None:
            out["note"] = note
        return out
    if kind == KIND_SIGNAL_ASSIGNMENT:
        unknown = set(body) - {"assignments", "system_id"}
        if unknown:
            raise UnsupportedRule(
                "unrecognized_field",
                "A signal assignment names channel-to-element pairs, nothing else.",
                keys=sorted(unknown),
            )
        system_id = body.get("system_id") or BL152_VORTEX.system_id
        if system_id != BL152_VORTEX.system_id:
            raise UnsupportedRule(
                "unknown_acquisition_system",
                "That is not an acquisition system this build knows the channels of.",
                available=[BL152_VORTEX.system_id],
            )
        raw = body.get("assignments")
        if not isinstance(raw, list) or not raw or len(raw) > MAX_ASSIGNMENTS:
            raise UnsupportedRule(
                "invalid_assignments",
                f"`assignments` must be a list of 1 to {MAX_ASSIGNMENTS} objects.",
            )
        seen: set[str] = set()
        assignments: list[dict] = []
        for item in raw:
            if not isinstance(item, Mapping) or set(item) - {"channel", "element", "edge"}:
                raise UnsupportedRule(
                    "invalid_assignments",
                    "Each assignment is `{channel, element, edge?}`.",
                )
            channel = _text(item.get("channel"), "channel")
            if channel not in BL152_VORTEX.candidate_channels:
                raise UnsupportedRule(
                    "unknown_channel",
                    "That is not a candidate HERFD channel for this acquisition system.",
                    available=list(BL152_VORTEX.candidate_channels),
                )
            if channel in seen:
                raise UnsupportedRule(
                    "invalid_assignments", "A channel may be assigned only once."
                )
            seen.add(channel)
            element = _text(item.get("element"), "element")
            if not _ELEMENT.match(element):
                raise UnsupportedRule(
                    "invalid_element",
                    "An element is a one- or two-letter chemical symbol.",
                )
            edge = _text(item.get("edge"), "edge", required=False)
            if edge is not None and not _EDGE.match(edge):
                raise UnsupportedRule(
                    "invalid_edge",
                    "An edge is written in X-ray level notation: K, L1-L3 or M1-M5.",
                )
            assignments.append({"channel": channel, "element": element, "edge": edge})
        return {"system_id": system_id, "assignments": assignments}
    raise UnsupportedRule(  # pragma: no cover - kind is validated first
        "unknown_kind", f"unknown rule kind {kind!r}"
    )


def _examples(raw: object) -> tuple[dict, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise UnsupportedRule(
            "wrong_type", "`source_examples` must be a list.", key="source_examples"
        )
    out: list[dict] = []
    for item in raw[:MAX_SOURCE_EXAMPLES]:
        if not isinstance(item, Mapping):
            raise UnsupportedRule(
                "wrong_type", "Each source example must be an object."
            )
        example = {}
        for key in ("source_path", "locator", "value"):
            value = item.get(key)
            if value is not None:
                example[key] = _text(value, f"source_examples.{key}")
        out.append(example)
    return tuple(out)


@dataclass(frozen=True)
class ConventionRule:
    """ONE reviewed rule. Immutable; a change is a NEW version that supersedes it."""

    rule_id: str
    kind: str
    scope: str
    version: int
    body: Mapping[str, Any]
    confirmed_utc: str
    selector: Selector = field(default_factory=Selector)
    experiment_id: str | None = None
    import_id: str | None = None
    profile_id: str | None = None
    profile_version: str | None = None
    supersedes: str | None = None
    derived_from: str | None = None
    confirmed_by: str = ACTOR_UNATTRIBUTED
    confirmed_trust_basis: str = TRUST_BASIS_UNATTRIBUTED
    source_examples: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in RULE_KINDS:
            raise UnsupportedRule("unknown_kind", f"unknown rule kind {self.kind!r}")
        if self.scope not in RULE_SCOPES:
            raise UnsupportedRule("unknown_scope", f"unknown rule scope {self.scope!r}")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise UnsupportedRule("invalid_version", "a rule version is an integer >= 1")
        if self.scope in {SCOPE_EXPERIMENT, SCOPE_PROFILE} and not self.experiment_id:
            raise UnsupportedRule(
                "experiment_required",
                "A rule for an Experiment or a convention is stored on an experiment.",
            )
        if self.scope == SCOPE_IMPORT and not self.import_id:
            raise UnsupportedRule(
                "import_required", "An apply-only-here rule belongs to one import."
            )
        if self.confirmed_by == ACTOR_UNATTRIBUTED and (
            self.confirmed_trust_basis != TRUST_BASIS_UNATTRIBUTED
        ):
            raise UnsupportedRule(
                "actor_basis_mismatch",
                "an unattributed confirmation must carry the unattributed trust basis",
            )
        if self.confirmed_by != ACTOR_UNATTRIBUTED and (
            self.confirmed_trust_basis == TRUST_BASIS_UNATTRIBUTED
        ):
            raise UnsupportedRule(
                "actor_basis_mismatch",
                "a named confirmer must carry the trust basis that established them",
            )

    # -- derived, and serialised so the guarantee crosses the wire -------------

    @property
    def is_official_field_value(self) -> bool:
        """Always ``False``. A rule says how to READ sources; it is not a value."""
        return False

    @property
    def is_evidence(self) -> bool:
        """Always ``False``. A confirmation of a convention is not scientific evidence."""
        return False

    @property
    def binding_scope(self) -> str:
        """The applicability level a PROFILE BINDING rule sits at, derived from its selector."""
        if self.selector.source_paths:
            return SCOPE_SOURCE
        if self.selector.legacy_range or self.selector.group_tokens or self.selector.stem_prefixes:
            return SCOPE_RUN_SUBSET
        if self.selector.source_types:
            return SCOPE_SOURCE_FAMILY
        return BINDING_SCOPE_EXPERIMENT

    def version_is_current(self) -> bool:
        """Whether the convention this rule names is still registered at that version."""
        if not self.profile_id:
            return True
        profile = prof.profile_for(self.profile_id)
        return profile is not None and profile.profile_version == self.profile_version

    def to_state(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "kind": self.kind,
            "scope": self.scope,
            "version": self.version,
            "body": dict(self.body),
            "selector": self.selector.to_state(),
            "experiment_id": self.experiment_id,
            "import_id": self.import_id,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "supersedes": self.supersedes,
            "derived_from": self.derived_from,
            "confirmed_utc": self.confirmed_utc,
            "confirmed_by": self.confirmed_by,
            "confirmed_trust_basis": self.confirmed_trust_basis,
            "source_examples": [dict(e) for e in self.source_examples],
            "version_is_current": self.version_is_current(),
            "is_official_field_value": self.is_official_field_value,
            "is_evidence": self.is_evidence,
        }

    @classmethod
    def from_state(cls, state: object) -> "ConventionRule":
        """Rehydrate. RAISES on a document it cannot represent; the caller preserves it."""
        if not isinstance(state, Mapping):
            raise UnsupportedRule("invalid_entry", "A rule entry must be an object.")
        kind = state.get("kind")
        if kind not in RULE_KINDS:
            raise UnsupportedRule("invalid_entry", "A rule entry has an unknown kind.")
        try:
            selector = Selector.from_state(state.get("selector"))
        except ValueError as refusal:
            raise UnsupportedRule("invalid_entry", str(refusal)) from refusal
        rule_id = state.get("rule_id")
        confirmed = state.get("confirmed_utc")
        if not isinstance(rule_id, str) or not isinstance(confirmed, str):
            raise UnsupportedRule("invalid_entry", "A rule entry is missing its identity.")
        body = state.get("body")
        return cls(
            rule_id=rule_id,
            kind=kind,
            scope=state.get("scope"),  # type: ignore[arg-type]
            version=state.get("version"),  # type: ignore[arg-type]
            body=dict(body) if isinstance(body, Mapping) else {},
            confirmed_utc=confirmed,
            selector=selector,
            experiment_id=_opt(state.get("experiment_id")),
            import_id=_opt(state.get("import_id")),
            profile_id=_opt(state.get("profile_id")),
            profile_version=_opt(state.get("profile_version")),
            supersedes=_opt(state.get("supersedes")),
            derived_from=_opt(state.get("derived_from")),
            confirmed_by=state.get("confirmed_by") or ACTOR_UNATTRIBUTED,
            confirmed_trust_basis=state.get("confirmed_trust_basis")
            or TRUST_BASIS_UNATTRIBUTED,
            source_examples=tuple(
                dict(e) for e in (state.get("source_examples") or []) if isinstance(e, Mapping)
            )
            if isinstance(state.get("source_examples"), list)
            else (),
        )


def _opt(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def new_rule(
    *,
    rule_id: str,
    kind: object,
    scope: object,
    body: object,
    selector: object,
    confirmed_utc: str,
    existing: Sequence[ConventionRule],
    experiment_id: str | None = None,
    import_id: str | None = None,
    supersedes: object = None,
    derived_from: object = None,
    source_examples: object = None,
) -> ConventionRule:
    """Validate and mint one rule against the rules its holder ALREADY has.

    ``supersedes`` must name an ACTIVE rule of the same kind held by the same holder —
    a new version replaces it, and the old one is kept, marked superseded by derivation
    (:func:`active_rules`). A rule is never edited in place and never deleted.
    """
    if kind not in RULE_KINDS:
        raise UnsupportedRule(
            "unknown_kind", "`kind` must name a rule kind.", allowed=sorted(RULE_KINDS)
        )
    if scope not in RULE_SCOPES:
        raise UnsupportedRule(
            "unknown_scope", "`scope` must name a rule scope.", allowed=sorted(RULE_SCOPES)
        )
    if len(existing) >= MAX_RULES_PER_HOLDER:
        raise UnsupportedRule(
            "too_many_rules",
            "This holder already stores the most rules one may hold.",
            maximum=MAX_RULES_PER_HOLDER,
        )
    try:
        parsed_selector = Selector.from_state(selector)
    except ValueError as refusal:
        raise UnsupportedRule("invalid_selector", str(refusal)) from refusal
    normalised = _validated_body(kind, body)
    version = 1
    superseded_id = _text(supersedes, "supersedes", required=False)
    if superseded_id is not None:
        active = {r.rule_id: r for r in active_rules(existing)}
        prior = active.get(superseded_id)
        if prior is None or prior.kind != kind:
            raise UnsupportedRule(
                "unknown_rule",
                "`supersedes` must name an active rule of the same kind held here.",
            )
        version = prior.version + 1
    profile_id = normalised.get("profile_id") if kind == KIND_PROFILE_BINDING else None
    profile_version = (
        normalised.get("profile_version") if kind == KIND_PROFILE_BINDING else None
    )
    return ConventionRule(
        rule_id=rule_id,
        kind=kind,
        scope=scope,
        version=version,
        body=normalised,
        confirmed_utc=confirmed_utc,
        selector=parsed_selector,
        experiment_id=experiment_id,
        import_id=import_id,
        profile_id=profile_id,
        profile_version=profile_version,
        supersedes=superseded_id,
        derived_from=_text(derived_from, "derived_from", required=False),
        source_examples=_examples(source_examples),
    )


def active_rules(rules: Iterable[ConventionRule]) -> list[ConventionRule]:
    """Every rule no later rule supersedes. Derived, never stored."""
    rules = list(rules)
    superseded = {r.supersedes for r in rules if r.supersedes}
    return [r for r in rules if r.rule_id not in superseded]


def hydrate(raw: object) -> tuple[list[ConventionRule], list]:
    """``(rules, unreadable raw entries)``. Never raises, and never discards."""
    if not isinstance(raw, list):
        return [], []
    rules: list[ConventionRule] = []
    unreadable: list = []
    for item in raw:
        try:
            rules.append(ConventionRule.from_state(item))
        except (UnsupportedRule, TypeError, ValueError):
            unreadable.append(item)
    return rules, unreadable


def state_payload(rules: Sequence[ConventionRule], unreadable: Sequence) -> list | None:
    """What to store at :data:`STATE_KEY`, or ``None`` for nothing — so no rev bump on legacy."""
    if not rules and not unreadable:
        return None
    return [r.to_state() for r in sorted(rules, key=lambda r: (r.confirmed_utc, r.rule_id))] + list(
        unreadable
    )


def bindings_from(rules: Iterable[ConventionRule]) -> list[ProfileBinding]:
    """The profile bindings the ACTIVE binding rules express, stale ones included.

    A stale binding (its convention is registered at another version today) is still
    returned: :func:`bl15.applicability.resolve` is where it is recognised as stale and
    reported per source, so the fact is visible where it matters instead of vanishing
    here.
    """
    out: list[ProfileBinding] = []
    for rule in active_rules(rules):
        if rule.kind != KIND_PROFILE_BINDING:
            continue
        out.append(
            ProfileBinding(
                binding_id=f"rule:{rule.rule_id}",
                profile_id=rule.body["profile_id"],
                profile_version=rule.body["profile_version"],
                scope=rule.binding_scope,
                selector=rule.selector,
                basis=BASIS_IMPORT_CHOICE if rule.scope == SCOPE_IMPORT else BASIS_CONFIRMED_RULE,
                rule_ref=rule.rule_id,
            )
        )
    return out


def signal_assignments_for(
    rules: Iterable[ConventionRule], *, archive_path: str, stem: str, source_type: str | None
) -> tuple[tuple[ChannelAssignment, ...], str | None]:
    """The confirmed channel assignments that apply to ONE Run, and the rule they came from.

    The most recent active rule whose selector matches wins; there is no merging of two
    rules' assignments, because two rules disagreeing about one Run is a question for a
    scientist, not an average.
    """
    matching = [
        r
        for r in active_rules(rules)
        if r.kind == KIND_SIGNAL_ASSIGNMENT
        and r.selector.matches(archive_path=archive_path, stem=stem, source_type=source_type)
    ]
    if not matching:
        return (), None
    rule = sorted(matching, key=lambda r: (r.confirmed_utc, r.rule_id))[-1]
    return (
        tuple(
            ChannelAssignment(
                channel=a["channel"],
                element=a["element"],
                edge=a.get("edge"),
                basis=f"scientist-confirmed rule {rule.rule_id} (v{rule.version})",
            )
            for a in rule.body.get("assignments") or []
        ),
        rule.rule_id,
    )


def resolutions_by_target(rules: Iterable[ConventionRule]) -> dict[str, ConventionRule]:
    """``conflict_id or candidate_id -> the active SPECIFIC resolution rule``. Latest wins."""
    out: dict[str, ConventionRule] = {}
    for rule in sorted(active_rules(rules), key=lambda r: (r.confirmed_utc, r.rule_id)):
        if rule.kind != KIND_CONFLICT_RESOLUTION:
            continue
        key = rule.body.get("conflict_id") or rule.body.get("candidate_id")
        if isinstance(key, str):
            out[key] = rule
    return out


def recurring_resolution_for(
    rules: Iterable[ConventionRule],
    *,
    conflict_kind: str,
    archive_path: str,
    stem: str,
    source_type: str | None,
) -> ConventionRule | None:
    """The latest active RECURRING resolution for this conflict kind whose selector
    matches this acquisition, or ``None``. Scope is the selector; nothing wider."""
    matching = [
        r
        for r in active_rules(rules)
        if r.kind == KIND_CONFLICT_RESOLUTION
        and r.body.get("conflict_kind") == conflict_kind
        and r.selector.matches(archive_path=archive_path, stem=stem, source_type=source_type)
    ]
    if not matching:
        return None
    return sorted(matching, key=lambda r: (r.confirmed_utc, r.rule_id))[-1]
