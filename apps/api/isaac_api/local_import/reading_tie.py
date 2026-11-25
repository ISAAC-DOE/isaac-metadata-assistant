"""THE LEXICAL TIE (1.19.0, DEC-97): a reading fills only when its quote ITSELF states the value. Pure; reads nothing.

A reading pass's ``stated`` finding cites a quote the loader found in the file (``reading_check``). That proves the quote
is there, never that it says the value: a replay on a real BL15-2 beamtime filled 49 materials with the sample's own
code (as a synthetic example, ``Sample 3 ZZ9 in base (SYNTHETIC)`` read as material ``ZZ9``) and 13 environments from
sentences that name none. So
``isaac.fill.reading_stated.v1`` also asks the stored quote (as stored: possibly truncated to 300 characters) to carry
the value, by the value's kind (:func:`tie_problem`):

* **a number** — the number appears in the quote WITH ONE OF THE FIELD'S OWN UNITS, or with a unit a DECLARED
  conversion takes (:data:`FIELD_UNITS`: ``0.06 V``, ``100 mV`` for 0.1 V, ``25 °C`` for 298.15 K, ``100 mM`` for 0.1 M);
  a number carrying ANY other unit (``0.1 mV/s`` or ``100 mV s-1``, a scan rate, for a set-point; ``0.1 M`` for a
  temperature; ``1 C rate``, a charge rate, for a temperature) never ties, nor a number inside a heading or an
  identifier (``Sample 1``, ``scan 5``, ``01_01``, ``ZZ1``); a unitless field (the pH) ties only a number written right
  after its own word (``pH 13``, ``pH = 13``, ``pH of 13``, ``pH13``), never a bare count (``2 electrodes``, ``500
  cycles``); a numeric field :data:`FIELD_UNITS` does not list never ties. "room temperature" holds no number, so it
  never fills a temperature;
* **a field with a closed list** — the member's own words (``in_situ`` as ``in situ`` / ``in-situ``), or a registered
  synonym (:data:`MEMBER_SYNONYMS`, explicit and small), as whole words, and never in a SENTENCE that holds a
  negation (:data:`NEGATIONS`), before or after the member's words (sentences end at ``;``, a full stop that is not a
  decimal point, and a blank line, never a single line end: "an in situ measurement was not possible", "the cell was never, at any point,
  operated in situ" and "In situ: not possible" do not tie ``in_situ``; "in situ, not ex situ" is asked, not filled);
* **free text** — every significant word of the value (letters and digits, at least 3 characters, compared without
  case, :data:`STOPWORDS` left out) is a word of the quote; a value with no significant word never ties.

A value of any other kind (a boolean, a list, an object) never ties. A reading that does not tie stays a suggestion.

Also here: what a sample's own LABEL is (:func:`label_key`), so a label is never filled as its material, and an
electrolyte name that carries a concentration or a pH (:func:`electrolyte_name_problem`).
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Iterable, Mapping, Sequence

#: EACH NUMERIC FIELD'S UNITS, as files write them (case kept: ``M`` is molar, ``m`` is not): ``own`` — the units
#: the field's value is in; ``conversions`` — ``(units, factor, offset)``: a quoted ``<number> <unit>`` states the value
#: ``number * factor + offset``; ``unitless`` — a bare number states it (the pH). A numeric field not listed never ties.
FIELD_UNITS: Mapping[str, Mapping[str, Any]] = {
    "context.electrochemistry.potential_setpoint_V": {
        "own": ("V", "v"), "conversions": ((("mV", "mv"), 0.001, 0.0),)},
    "context.electrochemistry.current_setpoint_mA_cm2": {
        "own": ("mA/cm2", "mA/cm^2", "mA cm-2", "mA cm^-2", "mA·cm-2", "mA/cm²", "mA cm⁻²"),
        "conversions": ((("µA/cm2", "μA/cm2", "uA/cm2", "µA cm-2", "μA cm-2", "uA cm-2"), 0.001, 0.0),)},
    "context.electrochemistry.electrolyte.concentration_M": {
        "own": ("M", "mol/L", "mol/l", "mol L-1", "mol l-1", "mol dm-3"),
        "conversions": ((("mM", "mmol/L", "mmol/l"), 0.001, 0.0),)},
    "context.temperature_K": {
        "own": ("K",), "conversions": ((("°C", "ºC", "C", "degC", "deg C"), 1.0, 273.15),)},
    # a unitless field: only a number right after its own word (``pH 13``, ``pH = 13``, ``pH of 13``, ``pH13``)
    "context.electrochemistry.pH": {"own": (), "conversions": (), "unitless": True, "anchor": "pH"},
}
#: The declared conversions alone, ``field path -> ((units, factor, offset), ...)`` (what :data:`FIELD_UNITS` says).
UNIT_CONVERSIONS: Mapping[str, tuple] = {p: u["conversions"] for p, u in FIELD_UNITS.items() if u["conversions"]}
#: Units of OTHER quantities a quote may put after a number (a rate, a current, a length, a time, an energy): such a
#: number is never a bare one. Any token holding ``/``, ``^``, ``°``, ``%`` or ``·`` counts as a unit too.
OTHER_UNITS = frozenset({"mV/s", "V/s", "mV s-1", "mV s^-1", "mV s⁻¹", "V s-1", "V s^-1", "V s⁻¹", "mV /s", "V /s",
                         "C-rate", "C rate", "mA", "A", "µA", "μA", "uA", "nA", "nm", "µm", "μm", "um", "mm", "cm", "eV",
                         "keV", "s", "ms", "min", "h", "hr", "Hz", "kHz", "mg", "g", "mL", "ml", "L", "µL", "uL", "W",
                         "mW", "Pa", "kPa", "bar", "mbar", "Torr", "wt%", "%", "rpm", "sccm"})
#: The words a number inside a heading or an identifier follows: ``Sample 1``, ``scan 5``, ``file 27``, ``No. 3``.
HEADING_WORDS = frozenset({"sample", "samples", "scan", "scans", "file", "files", "run", "runs", "step", "steps", "line",
                           "lines", "page", "electrode", "electrodes", "no", "number", "cycle", "spot", "position",
                           "slot", "channel", "id", "series", "batch", "cell", "#"})
#: ``field path -> {member: (synonym phrases, ...)}``: words a file uses for a list member besides the member's own
#: (``flow_cell`` reads as ``flow cell`` without an entry). Explicit and small; each is pinned by a test.
MEMBER_SYNONYMS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "context.electrochemistry.cell_type": {"h_cell": ("h type cell",), "three_electrode": ("3 electrode",)},
    "sample.sample_form": {"pellet": ("pellets",), "powder": ("powders",), "film": ("films",),
                           "nanoparticle": ("nanoparticles",)},
}
#: Words a free-text value may hold that the quote need not repeat.
STOPWORDS = frozenset({"the", "and", "for", "with", "was", "were", "are", "from", "into", "onto", "this", "that",
                       "its", "per", "via", "has", "had", "have", "been", "but", "not", "all"})
#: A word that, anywhere in the same sentence as a member's words, says (or may say) the opposite (``n't`` is read as
#: ``not``): the member is then asked, never filled.
NEGATIONS = frozenset({"not", "no", "never", "without", "non", "neither", "nor", "cannot", "unable", "impossible",
                       "instead", "rather", "failed", "absent", "unavailable", "lacking"})

_PLAIN = str.maketrans({"−": "-", "–": "-", "—": "-", " ": " ", " ": " ", " ": " "})
_NUMBER = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
#: What follows a number: the next token, and a second one only where a unit writes it in two (``mA cm-2``, ``deg C``).
_AFTER = re.compile(r"(?P<gap>\s*)(?P<tok>[A-Za-z°ºµμ%#][\w°ºµμ%/^·²⁻¹\-]*)"
                    r"(?:\s+(?P<tok2>(?:cm-?2|cm\^-?2|cm⁻²|L-1|l-1|dm-3|C)\b))?")
#: A RATE word right after a unit — a one-word unit or a two-word one (``mV s-1``, ``mA cm-2 s-1``, ``mV per second``,
#: ``mV s^{-1}``, ``mV sec-1``, ``1 C rate``): the number before it is a rate (a scan rate, a ramp, a charge rate),
#: which no fill field holds, so it never ties.
_RATE_AFTER = re.compile(r"\s*(?:s\s*-\s*1|s\^\s*\{?\s*-\s*1\s*\}?|s⁻¹|/\s*s\b|sec\s*-\s*1|sec⁻¹|/\s*sec\b|"
                         r"per\s+second\b|per\s+sec\b|per\s+s\b|rate\b)", re.IGNORECASE)
#: Sentences end at ``;``, a full stop that is not a decimal point, and a blank line — never at a single line end: a
#: wrapped logbook line ("in situ was planned\nbut not done") is one sentence.
_SENTENCE = re.compile(r";|\.(?!\d)|\n\s*\n")
_WORD = re.compile(r"[0-9a-z]+")


def _plain(text: Any) -> str:
    return unicodedata.normalize("NFKC", str(text or "")).translate(_PLAIN)


def words(text: Any) -> list[str]:
    """The words of ``text`` as the tie compares them: casefolded runs of letters and digits (``_`` and ``-`` split)."""
    return _WORD.findall(_plain(text).casefold().replace("_", " "))


def _all_units() -> frozenset[str]:
    out = set(OTHER_UNITS)
    for u in FIELD_UNITS.values():
        out |= set(u["own"])
        for units, _f, _o in u["conversions"]:
            out |= set(units)
    return frozenset(out)


def _numbers(quote: str) -> list[tuple[float, str | None]]:
    """``(number, unit)`` for each number of ``quote`` that is not inside a heading or an identifier; ``unit`` is the
    unit written after it (one of the known units, or a unit-shaped token), else ``None`` (a bare number)."""
    text = _plain(quote)
    known = _all_units()
    out = []
    for m in _NUMBER.finditer(text):
        before = text[:m.start()].rstrip()
        prev = re.search(r"([A-Za-z]+|#)\.?\s*$", before)
        if prev and prev.group(1).casefold() in HEADING_WORDS:
            continue  # Sample 1, scan 5, No. 3: a heading or a count, never a value
        if text[m.end():m.end() + 1] == "_":
            continue  # 01_01: an identifier
        after = _AFTER.match(text, m.end())
        unit = None
        if after:
            tok, tok2 = after.group("tok"), after.group("tok2")
            two = f"{tok} {tok2}" if tok2 else None
            if _RATE_AFTER.match(text, after.end()) or _RATE_AFTER.match(text, after.end("tok")):
                unit = f"{two or tok} (a rate)"  # a scan rate, a ramp, a C rate: a unit of no fill field, never a tie
            elif two and two in known:
                unit = two
            elif tok in known or any(ch in tok for ch in "/^°%·"):
                unit = tok
            elif not after.group("gap"):
                continue  # 13A, 5th, 1x: a number written into a word is an identifier, never a value
        try:
            n = float(m.group(0))
        except ValueError:
            continue
        if math.isfinite(n):
            out.append((n, unit))
    return out


def _same_number(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


def number_tie(path: str, value: float, quote: str) -> bool:
    """The number ``value`` appears in ``quote`` with one of ``path``'s own units, or a declared conversion of a quoted
    number with its unit gives it; a bare number only for a unitless field (:data:`FIELD_UNITS`). Any other unit, a
    number inside a heading or an identifier, and a field :data:`FIELD_UNITS` does not list: no tie."""
    spec = FIELD_UNITS.get(path)
    if spec is None:
        return False
    if spec.get("unitless"):
        # only a number written right after the field's own word: pH 13, pH = 13, pH of 13, pH13 (never a bare count)
        anchor = re.compile(rf"(?<![A-Za-z]){re.escape(spec['anchor'])}\s*(?:=|:|~|≈|of|is|was|at)?\s*([-+]?\d+(?:\.\d+)?)(?![\d.])",
                            re.IGNORECASE)
        return any(_same_number(float(m.group(1)), value) for m in anchor.finditer(_plain(quote)))
    for n, unit in _numbers(quote):
        if unit is None:
            continue
        if unit in spec["own"] and _same_number(n, value):
            return True
        for units, factor, offset in spec["conversions"]:
            if unit in units and _same_number(n * factor + offset, value):
                return True
    return False


def _phrase_at(quote_words: Sequence[str], phrase: Sequence[str]) -> list[int]:
    k = len(phrase)
    return [i for i in range(len(quote_words) - k + 1) if list(quote_words[i:i + k]) == list(phrase)] if k else []


def _sentences(quote: str) -> list[list[str]]:
    """``quote``'s sentences (split at ``;``, a full stop that is not a decimal point, and a blank line — never a single
    line end), each as its words, with ``n't`` read as ``not``."""
    text = re.sub(r"n['’]t\b", " not", _plain(quote), flags=re.IGNORECASE)
    return [words(c) for c in _SENTENCE.split(text)]


def member_tie(path: str, member: str, quote: str) -> bool:
    """The list member ``member`` is named in ``quote``: its own words (``in_situ`` -> ``in situ``), the same words run
    together (``insitu``), or a synonym of :data:`MEMBER_SYNONYMS`; as whole words, in a sentence that holds NO negation
    (:data:`NEGATIONS`) before or after them."""
    phrases = [words(member), ["".join(words(member))], *(words(s) for s in MEMBER_SYNONYMS.get(path, {}).get(member, ()))]
    for sentence in _sentences(quote):
        if any(w in NEGATIONS for w in sentence):
            continue
        if any(_phrase_at(sentence, phrase) for phrase in phrases):
            return True
    return False


def significant_words(value: Any) -> list[str]:
    """The words of a free-text value the quote must hold: at least 3 characters, not a :data:`STOPWORDS` word."""
    return [w for w in words(value) if len(w) >= 3 and w not in STOPWORDS]


def text_tie(value: Any, quote: str) -> bool:
    """Every significant word of ``value`` is a word of ``quote``; a value with none never ties."""
    need = significant_words(value)
    have = set(words(quote))
    return bool(need) and all(w in have for w in need)


def tie_problem(path: str, value: Any, quote: Any, allowed: Iterable | None) -> str | None:
    """Why ``quote`` does not STATE ``value`` for ``path``, else ``None`` (the module's rules, by the value's kind;
    ``allowed``: the field's closed list, or ``None``)."""
    if not isinstance(quote, str) or not quote.strip():
        return "the reading keeps no quote"
    if isinstance(value, bool) or value is None:
        return "a value of this kind is never read off a quote"
    if isinstance(value, (int, float)):
        return None if number_tie(path, float(value), quote) else "the quote does not state this number"
    if not isinstance(value, str):
        return "a value of this kind is never read off a quote"
    if allowed is not None:
        return None if member_tie(path, value, quote) else "the quote does not name this value"
    return None if text_tie(value, quote) else "the quote does not hold every word of this value"


def label_key(text: Any) -> str:
    """A label compared without case or punctuation (``ZZ-9``, ``zz9`` and ``ZZ9`` are one label)."""
    return "".join(words(text))


#: A logbook sample heading: ``Sample 3 ZZ9 in base (SYNTHETIC)`` -> ``ZZ9`` (the code the heading gives the sample: a token with a
#: digit, or one of two or more capitals; ``Sample 1 was measured`` gives none).
_HEADING = re.compile(r"\b(?i:sample)\s*#?\s*\d+\s*[:\-\u2013]?\s*([A-Za-z]*\d[A-Za-z0-9_\-.]*|[A-Z]{2,}[A-Za-z0-9_\-.]*)")


def heading_codes(text: Any) -> set[str]:
    """The sample codes ``text`` gives in a ``Sample <n> <code>`` heading, as :func:`label_key` keys."""
    return {label_key(m.group(1)) for m in _HEADING.finditer(_plain(text))} - {""}


_CONCENTRATION = re.compile(r"\d(?:[.,]\d+)?\s*(?:m?M|mol\s*/\s*[lL]|mol\s*[lL]\s*-\s*1|mol\s*dm-?3)(?![A-Za-z])")
_PH = re.compile(r"(?<![A-Za-z])pH(?![A-Za-z])")


def electrolyte_name_problem(value: Any) -> str | None:
    """An electrolyte NAME that carries a concentration (a number followed by M, mM or mol/L) or a pH: never filled (the
    concentration and the pH are their own fields; splitting the statement is the scientist's step)."""
    if not isinstance(value, str):
        return None
    if _CONCENTRATION.search(value):
        return "the name carries a concentration"
    if _PH.search(value):
        return "the name carries a pH"
    return None
