"""PLAIN WORDS for a bundle's questions, in Python: what the question site's cards say. Stdlib only.

The command line's question text (``questions.py``) names field paths, decision names and flags: the skill reads it.
The local website has a plain layer on top of it (``apps/web/src/lib/plainQuestions.ts``). This module is that layer
in Python, so the question site (``question_site.py``) and the local website say the same thing:

* THE PORT (:data:`FIELD_ASK`, :data:`FIELD_NOUN`, :data:`VAGUE`, :data:`CHOICE_ASK`, :func:`field_noun`,
  :func:`field_ask`, :func:`confirm_shape`, :func:`sample_label`): the same tables and rules as the TypeScript file.
  ``apps/api/tests/test_local_import_question_site.py`` reads that file and fails when a table here drifts from it.
* THE CARD WORDING (:func:`ask_for`, :func:`is_it`, :func:`field_label`, :func:`value_label`): what only the
  question site needs. A card stands alone on a phone, so its title names who it is about ("What form was sample ZZ1
  in?") and, where the files give a value, the value ("Is the applied potential 0.1 V for this measurement?").

COPY ONLY. No function here reads a value from a file, chooses one, or says more than the question's own structured
fields say. A title is one sentence with no field path, no decision name and no flag (:func:`not_plain` is the check
the export and the tests apply). A kind with no wording here gets none: the export leaves it out and counts it.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

# --- the port of apps/web/src/lib/plainQuestions.ts ------------------------------------------------------------------

#: How a field is ASKED when no file states it, in the words a scientist would use.
FIELD_ASK: Mapping[str, str] = {
    "sample.sample_form": "What form was the sample in?",
    "system.domain": "Is this experimental or computational work?",
    "system.technique": "Which technique was used?",
    "attribution.produced_by.group": "Which research group produced this data?",
    "attribution.produced_by.organization": "Which institution produced this data?",
    "sample.material.name": "What is the sample material?",
    "sample.sample_id": "What is the sample ID?",
    "context.electrochemistry.cell_type": "What kind of cell was used?",
    "context.electrochemistry.reaction": "Which reaction was studied?",
    "context.electrochemistry.potential_setpoint_V": "What potential was applied?",
    "context.electrochemistry.electrolyte.name": "What was the electrolyte?",
    "timestamps.acquired_start_utc": "When did the measurement start?",
}

#: What a field IS, as a noun, for "is the ... right?" and "your files disagree about the ...".
FIELD_NOUN: Mapping[str, str] = {
    "context.environment": "measurement environment",
    "sample.sample_form": "sample form",
    "system.domain": "domain",
    "system.technique": "technique",
    "attribution.produced_by.group": "research group",
    "attribution.produced_by.organization": "institution",
    "sample.material.name": "sample material",
    "sample.material.provenance": "sample source",
    "sample.sample_id": "sample ID",
    "context.electrochemistry.cell_type": "cell type",
    "context.electrochemistry.reaction": "reaction",
    "context.electrochemistry.potential_setpoint_V": "applied potential",
    "context.electrochemistry.electrolyte.name": "electrolyte",
    "timestamps.acquired_start_utc": "start time",
    "measurement.series[].channels[].name": "signal channel name",
    "measurement.series[].independent_variables[].values": "energy values",
    "assets[].uri": "data file location",
    "links[].rel": "link type",
}

#: Last path segments that say nothing alone: their parent is named with them.
VAGUE = frozenset({"name", "group", "organization", "value", "type", "status", "id"})

#: Fields asked as a choice between their allowed values: the lead, then the values themselves (never written here:
#: they are the question's own ``allowed_values``).
CHOICE_ASK: Mapping[str, str] = {"context.environment": "Was this done"}

_UNIT_SUFFIX = re.compile(r"_(mA_cm2|eV|mm|K|V|M)$")


def field_noun(path: str) -> str:
    """A field path as a noun: ``sample.sample_form`` -> "sample form" (``fieldNoun``)."""
    if path in FIELD_NOUN:
        return FIELD_NOUN[path]
    # a unit the field's NAME carries (temperature_K) is said by the answer box, not the question
    segs = [_UNIT_SUFFIX.sub("", re.sub(r"\[\]$", "", s)).replace("_", " ") for s in path.split(".")]
    last = segs[-1] if segs else path
    return f"{segs[-2]} {last}" if last in VAGUE and len(segs) > 1 else last


def value_words(value: Any) -> str:
    """A vocabulary value in words: ``in_situ`` -> "in situ" (``valueWords``)."""
    return str(value).replace("_", " ")


def or_list(items: Sequence[str]) -> str:
    """"a, b or c" (``orList``)."""
    items = list(items)
    return (items[0] if items else "") if len(items) <= 1 else f"{', '.join(items[:-1])} or {items[-1]}"


def field_ask(path: str, allowed: Sequence[Any] | None = None) -> str:
    """The plain question for a field no file states; a choice field names its allowed values (``fieldAsk``)."""
    lead = CHOICE_ASK.get(path)
    values = [v for v in allowed or () if isinstance(v, str) and v != ""]
    if lead and len(values) > 1:
        return f"{lead} {or_list([value_words(v) for v in values])}?"
    return FIELD_ASK.get(path) or f"What is the {field_noun(path)}?"


def confirm_shape(q: Mapping) -> str:
    """What a confirm question can be answered with, from the question's own flags (``confirmShape``): ``no_value``
    (no target carries a value: the question asks for one), ``unfit`` (every target's value is missing or one its
    field refuses), else ``value`` (there is a value read from the files to confirm)."""
    if q.get("no_value"):
        return "no_value"
    total = len(q.get("targets") or ())
    without = int(q.get("targets_without_a_value") or 0)
    unfit = int(q.get("targets_with_an_unfit_value") or 0)
    if total > 0 and without >= total:
        return "no_value"
    if total > 0 and unfit > 0 and without + unfit >= total:
        return "unfit"
    return "value"


_SAMPLE_SAID = re.compile(r"sample reading \((.+?), as the files write it\)")
_SAMPLE_PAIR = re.compile(r"([a-z][a-z ]*?) '([^']*)'")


def sample_pairs(q: Mapping) -> list[tuple[str, str]] | None:
    """The sample a per-sample question is asked for, as ``(key, value)`` pairs in the files' own spelling where the
    question's wording gives it, else from its ``partition``; ``[]`` for the groups whose files name no sample;
    ``None`` for a question not asked per sample (the reading half of ``sampleLabel``)."""
    partition = str(q.get("partition") or "")
    if not partition.startswith("sample="):
        return None
    raw = partition[len("sample="):]
    if raw == "unrecorded":
        return []
    said = _SAMPLE_SAID.search(str(q.get("text") or ""))
    pairs = [(m.group(1).strip().replace(" ", "_"), m.group(2)) for m in _SAMPLE_PAIR.finditer(said.group(1))] if said else []
    if not pairs:
        try:
            obj = json.loads(raw)
        except ValueError:
            return [("sample_name", raw)]
        if not isinstance(obj, Mapping):
            return [("sample_name", raw)]
        pairs = [(str(k), str(v)) for k, v in obj.items() if v not in (None, "")]
    return pairs


def sample_label(q: Mapping) -> str | None:
    """"Sample ZZ1, no. 06", as the local website's cards say it (``sampleLabel``); ``None`` when not per sample."""
    pairs = sample_pairs(q)
    if pairs is None:
        return None
    if not pairs:
        return "Groups whose files name no sample"
    got = dict(pairs)
    name, number = got.get("sample_name"), got.get("sample_or_electrode_number")
    rest = [v for k, v in pairs if k not in ("sample_name", "sample_or_electrode_number")]
    parts = [p for p in (name, f"no. {number}" if number else None, *rest) if p]
    return f"Sample {', '.join(parts)}" if parts else "Sample (no name in the files)"


# --- the question site's card wording ------------------------------------------------------------------------------

#: How a field is asked ABOUT SOMETHING NAMED (a sample, a measurement): the subject goes where ``{subject}`` stands.
FIELD_ASK_ABOUT: Mapping[str, str] = {
    "sample.sample_form": "What form was {subject} in?",
    "sample.material.name": "What material is {subject}?",
    "sample.material.formula": "What is the chemical formula of {subject}?",
    "sample.material.provenance": "Where did {subject} come from?",
    "sample.sample_id": "What is the sample ID of {subject}?",
}

#: A choice field asked about something named: ``(one thing, several things)``, of a sample and of a measurement.
CHOICE_ASK_ABOUT: Mapping[str, tuple[str, str]] = {"context.environment": ("Was {subject} measured", "Were {subject} measured")}
CHOICE_ASK_OF_MEASUREMENT: Mapping[str, tuple[str, str]] = {"context.environment": ("Was {subject} done", "Were {subject} done")}

#: Fields the port has no ask for, in a scientist's words (the question site asks optional fields too).
MORE_ASKS: Mapping[str, str] = {
    "context.electrochemistry.pH": "What was the electrolyte pH?",
    "context.electrochemistry.potential_scale": "Which reference scale are the potentials given on?",
    "context.electrochemistry.control_mode": "How was the cell controlled?",
    "context.electrochemistry.current_setpoint_mA_cm2": "What current density was applied?",
    "context.electrochemistry.electrolyte.concentration_M": "What was the electrolyte concentration?",
    "context.thermodynamics.atmosphere": "What atmosphere or gas was the sample in?",
    "context.temperature_K": "What was the temperature?",
    "context.reaction.catalysis": "What type of catalysis is this?",
    "context.reaction.drive": "What drives the reaction?",
    "sample.material.formula": "What is the sample's chemical formula?",
    "sample.material.provenance": "Where did the sample come from?",
    "system.facility.facility_name": "At which facility was this measured?",
    "system.facility.beamline": "At which beamline was this measured?",
    "system.facility.endstation": "At which endstation was this measured?",
    "system.facility.site": "At which site is the facility?",
    "system.facility.organization": "Which organization runs the facility?",
    "timestamps.acquired_end_utc": "When did the measurement end?",
}

#: More nouns, for the fields above.
MORE_NOUNS: Mapping[str, str] = {
    "context.electrochemistry.pH": "electrolyte pH",
    "context.electrochemistry.potential_scale": "potential reference scale",
    "context.electrochemistry.control_mode": "control mode",
    "context.electrochemistry.current_setpoint_mA_cm2": "applied current density",
    "context.electrochemistry.electrolyte.concentration_M": "electrolyte concentration",
    "context.thermodynamics.atmosphere": "atmosphere",
    "context.temperature_K": "temperature",
    "context.reaction.catalysis": "catalysis type",
    "context.reaction.drive": "reaction drive",
    "sample.material.formula": "sample formula",
    "system.facility.facility_name": "facility",
    "system.facility.beamline": "beamline",
    "system.facility.endstation": "endstation",
    "system.facility.site": "facility site",
    "system.facility.organization": "facility organization",
    "timestamps.acquired_end_utc": "end time",
}

#: The few options of a long list to show first, where the list is long (filtered by the field's own allowed
#: values; a value the schema does not offer is never shown). A convenience for the page, never a suggestion.
COMMON_OPTIONS: Mapping[str, tuple[str, ...]] = {
    "system.technique": ("XAS", "HERFD-XAS", "XES", "RIXS"),
    "sample.sample_form": ("powder", "pellet", "film", "nanoparticle", "liquid"),
}
#: A list at most this long needs no short list.
COMMON_FROM = 7


def noun(path: str) -> str:
    """:func:`field_noun`, with the question site's extra nouns."""
    return MORE_NOUNS.get(path) or field_noun(path)


def field_label(path: str) -> str:
    """The short label a card carries for its field (``field.label``): its noun."""
    return noun(path)


def value_label(value: Any, unit: str | None = None) -> str:
    """A value as a card shows it: a vocabulary word in words, a number with its unit."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        text = json.dumps(value)
        return f"{text} {unit}" if unit else text
    if isinstance(value, str):
        return value_words(value) if re.fullmatch(r"[a-z][a-z0-9]*(_[a-z0-9]+)+", value) else value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _base_ask(path: str, allowed: Sequence[Any] | None) -> str:
    if path in CHOICE_ASK or path in FIELD_ASK:
        return field_ask(path, allowed)
    return MORE_ASKS.get(path) or f"What is the {noun(path)}?"


def ask_for(path: str, allowed: Sequence[Any] | None = None, *, subject: str | None = None, plural: bool = False,
            names_sample: bool = False) -> str:
    """The question for a field, about ``subject`` when one is named ("sample ZZ1", "this measurement", "these 5
    measurements"); the beamtime-wide wording when none is. ``names_sample``: the subject is a sample by name (a
    sample field asked of a measurement is asked of "the sample of this measurement")."""
    if not subject:
        return _base_ask(path, allowed)
    values = [v for v in allowed or () if isinstance(v, str) and v != ""]
    if path in CHOICE_ASK_ABOUT and len(values) > 1:
        asks = CHOICE_ASK_ABOUT if names_sample else CHOICE_ASK_OF_MEASUREMENT
        lead = asks[path][1 if plural else 0].format(subject=subject)
        return f"{lead} {or_list([value_words(v) for v in values])}?"
    if path in FIELD_ASK_ABOUT:
        return FIELD_ASK_ABOUT[path].format(subject=subject if names_sample else f"the sample of {subject}")
    base = _base_ask(path, allowed)
    return f"{base[:-1]} for {subject}?" if base.endswith("?") else f"{base} ({subject})"


def is_it(path: str, shown: str, *, subject: str | None = None) -> str:
    """The yes-or-no form for a value the files give: "Is the applied potential 0.1 V for this measurement?"."""
    return f"Is the {noun(path)} {shown}{' for ' + subject if subject else ''}?"


def disagree(path: str, *, subject: str | None = None) -> str:
    """The files disagree, and each reading is a value the field takes: which is right."""
    return f"Your files disagree about the {noun(path)}{' for ' + subject if subject else ''}. Which is right?"


def quoted(literals: Sequence[Any], *, limit: int = 3) -> str:
    """"'a', 'b' and 'c'": the files' own words, at most ``limit`` of them (the rest counted)."""
    seen = list(dict.fromkeys(str(x) for x in literals if str(x).strip()))
    shown = [f"'{x}'" for x in seen[:limit]]
    more = len(seen) - len(shown)
    if more > 0:
        return f"{', '.join(shown)} and {more} more"
    return shown[0] if len(shown) == 1 else f"{', '.join(shown[:-1])} and {shown[-1]}" if shown else ""


#: What a card says of a value no parser found (the local website's words for a missing value).
NONE_SAY = "None of your files say."

#: What must never be in a card's title or detail: a dotted field path, a command-line flag, a decision or kind name
#: with an underscore, an id, the tool's own command.
_NOT_PLAIN = (
    (re.compile(r"\b[a-z_]+(?:\[\])?\.[a-z_]+(?:\[\])?(?:\.[a-z_\[\]]+)*\b"), "a field path"),
    (re.compile(r"(?<![\w-])--[a-z]"), "a command-line flag"),
    (re.compile(r"\bisaac bundle\b|\bbundle decide\b"), "a command"),
    (re.compile(r"\b(?:set_[a-z_]+|same_reading[a-z_]*|missing_value|confirm_value|resolve_conflict|optional_values|"
                r"condition_label|no_value|needs_review)\b"), "a decision or kind name"),
    (re.compile(r"\b(?:Q|SR|C)-[0-9a-f]{10}\b|\brg-[0-9a-f]{8,}\b|\b(?:cand|miss|conf)-\d+\b"), "an id"),
)


def not_plain(text: Any) -> str | None:
    """Why ``text`` is not plain words (it holds a field path, a flag, a command, a decision name or an id), or
    ``None`` when it is. File names and the files' own quoted words are the caller's to leave out of the check."""
    for pattern, what in _NOT_PLAIN:
        m = pattern.search(str(text or ""))
        if m:
            return f"{what} ({m.group(0)!r})"
    return None


# --- the asks of the kinds the question site does not put on a card (read by ``bundle questions``) ------------------
# COPY ONLY, like everything above: each is built from the question's own structured fields.

def ordinal(n: int) -> str:
    """1 -> "1st", 4 -> "4th", 11 -> "11th", 21 -> "21st"."""
    suffix = "th" if n % 100 in (11, 12, 13) else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def counter_ask(positions: Sequence[Any]) -> str:
    """The file-name counter question, from the positions it names (a number, or ``last``)."""
    named = [("last part" if str(p).casefold() == "last" else f"{ordinal(int(p))} part") for p in positions]
    if len(named) == 1:
        return (f"Is the {named[0]} of the file names a run counter, a number that only tells repeats of one "
                "measurement apart?")
    return (f"Are the {or_list(named)} of the file names run counters, numbers that only tell repeats of one "
            "measurement apart?")


def absorber_ask(element: str, edge: str) -> str:
    return f"Is the absorbing element and edge {element} {edge}?"


#: The beamtime-wide start-time question: the files give the moment each file was created; a scientist chooses.
START_TIME_ASK = "Should each measurement's start time be the moment its file was created?"

#: The beamtime-wide dose question (the processing card's own sentence is longer: it counts spots).
DOSE_ASK = "Is the change in the white line after the first scan at a spot beam damage?"


def optional_ask(paths: Sequence[str]) -> str:
    """The optional-fields question: the fields it lists, in nouns."""
    nouns = [noun(p) for p in paths]
    shown = or_list(nouns[:6])
    more = len(nouns) - 6
    return f"Do you know any of these: {shown}{f' (and {more} more)' if more > 0 else ''}?"
