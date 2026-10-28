"""Propose ISAAC record groups from a Local Import Bundle's runs. Stdlib only.

WHY
===

An official ISAAC record is ONE RESULT: one sample, one technique, one set of conditions
(upstream wiki, "What an ISAAC record is"). The domain owner (Angel, 28 Oct 2026):
*"Multiple scans, multiple runs, or repeats of the same sample in a specific condition
create a single record."* So the unit of a record is a GROUP of runs, and a run is the
unit of acquisition. This module only PROPOSES (``status: "proposed"``); a scientist
confirms, splits or merges later (``scientist_decisions``).

THE RULE (``isaac.grouping.record_groups.v1``)
=============================================

Each candidate the engine attached to a run is read as a *reading* — ``value``
(normalised), ``literal`` (casefolded literal(s)), ``conflicting`` (the engine says the
sources disagree), or absent — and every statement key falls in ONE of three classes:

* ``condition`` (:data:`CONDITION_KEYS`, each with its justification) — part of what the
  result IS. Any difference, a conflict, or stated-for-one-run-only SPLITS.
* ``bookkeeping`` (:data:`BOOKKEEPING_KEYS`, each with its reason) — how the acquisition
  was filed (counters, timestamps, scan grids, repeat markers ...). Ignored for grouping;
  runs differing ONLY here form ONE proposed group, with a question listing the differing
  bookkeeping literals ("these N runs look like repeats — merge?").
* ``unknown`` (:data:`UNKNOWN_KEYS`, plus every key this module has never seen) — not
  decided by this build (``new_spot``, ``step_number``, unrecognised name tokens). A
  difference SPLITS, and the groups are linked by a ``merge_candidate`` naming the key,
  so a scientist merges with one decision. Nothing unknown is merged silently.

Known ENGINE MISREADINGS (:func:`engine_reading_issues`) are identified with their
evidence and never hard-split: the affected run is its own group, flagged
``blocked_by_engine_reading``, and offered in a merge candidate. The engine is not edited.

A proposed group needs, for every member: same role; no conflicting condition; a stated
sample identity; at least one scan; no engine-reading issue; equal condition AND unknown
readings. A merge candidate needs: same role, equal condition readings, no hard condition
conflict, scans. Ids are stable sha256 prefixes; order follows the bundle.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

GROUPING_RULE_ID = "isaac.grouping.record_groups.v1"
ROLE_RULE_ID = "isaac.grouping.run_role.v0"
UNREAD_RULE_ID = "isaac.grouping.unread_numbered_scans.v0"
ENGINE_RULE_ID = "isaac.grouping.engine_misreading.v0"

ROLE_SAMPLE = "sample"
ROLE_REFERENCE = "reference"
ROLE_ALIGNMENT = "alignment"
_ROLE_ORDER = {ROLE_SAMPLE: 0, ROLE_REFERENCE: 1, ROLE_ALIGNMENT: 2}

CLASS_CONDITION = "condition"
CLASS_BOOKKEEPING = "bookkeeping"
CLASS_UNKNOWN = "unknown"

SAMPLE_KEYS: tuple[str, ...] = ("sample_name", "sample_or_electrode_number", "loading_or_thickness")
TECHNIQUE_KEYS: tuple[str, ...] = ("acquisition_method",)
ENVIRONMENT_KEYS: tuple[str, ...] = ("environment_statement", "cell_type_statement", "reaction_statement")

#: Part of what the result IS. key -> why a difference makes a different record.
CONDITION_KEYS: Mapping[str, str] = {
    "sample_name": "sample identity: a different material is a different result",
    "sample_or_electrode_number": "sample identity: a different electrode/specimen is a different result",
    "loading_or_thickness": "material: loading/thickness changes absorption and self-absorption",
    "acquisition_method": "technique: a different acquisition method is a different measurement",
    "environment_statement": "environment (operando / in situ / ex situ) changes the state measured",
    "cell_type_statement": "environment: the electrochemical cell defines the conditions",
    "reaction_statement": "environment: the reaction under study defines the experiment",
    "potential_magnitude": "condition: the applied potential sets the electrochemical state",
    "potential_reference_basis": "condition: a potential means nothing without its reference electrode",
    "electrolyte_or_medium": "condition: electrolyte/medium (incl. concentration) changes the state",
    "ph": "condition: pH changes the state",
    "gas_condition": "condition: gas atmosphere changes the state",
    "flow_rate": "condition: flow changes mass transport and the state",
    "cycling_state": "condition: electrochemical history (cycling) changes the sample",
    "before_after_state": "condition: before/after a treatment are different states",
    "dry_state": "condition: dry vs in electrolyte are different states",
    "temperature_statement": "condition: temperature changes the state",
    "filter": "detector setup: an attenuating filter changes the measured count rate and dose",
    "emission_energy": "detector setup: the HERFD emission energy selects which line is measured",
}

#: How the acquisition was filed, not what was measured. key -> reason.
BOOKKEEPING_KEYS: Mapping[str, str] = {
    "measurement": "structural: says a measurement exists, not a value",
    "legacy_run_or_file_number": "file counter; duplicates are kept as separate runs",
    "repeat_marker": "marks a REPEAT of the same condition (`again`, `repeat`) — the thing that merges",
    "acquisition_timestamp": "when, not under which condition",
    "acquisition_epoch": "when, not under which condition",
    "counting_time": "acquisition setting (statistics), not a sample condition",
    "scan_command": "energy grid / dwell of the scan, not a sample condition",
    "energy_grid": "energy grid of the scan; the merge step handles differing grids",
    "scan_count": "how many scans, not a condition",
    "point_count": "how many points, not a condition",
    "detector_column": "columns present; channel choice is a processing step",
    "spec_file_declaration": "the file's own name declaration (its tokens are read separately)",
    "spec_user_string": "free SPEC comment; kept as evidence, not compared",
    "acquisition_target": "file relationship, not a condition",
    "motor_position": "every motor in the header; drifts between runs",
    "sample_position": "stage coordinates drift between repeats (a NEW SPOT is `new_spot`, unknown)",
    "trigger": "acquisition trigger setting",
    "internal_declaration_vs_filename": "a run-level naming conflict; reported by the engine",
    "acquired_never_declared": "a run-level macro relationship; reported by the engine",
    "note_file_number_row": "notes cross-reference, not a condition",
    "quality_note": "data-quality remark; kept as evidence",
    "contributor_statement": "provenance, never a condition",
    "beamtime_dates": "beamtime context",
    "beamtime_purpose": "beamtime context",
    "beamsize": "beamtime instrument context",
    "spectrometer_configuration": "beamtime instrument context",
    "monochromator_calibration": "beamtime instrument context (used by calibration, not grouping)",
    "element": "absorber identity, used by processing; stated once per beamtime",
    "absorption_edge": "absorber edge, used by processing",
    "sample_preparation": "preparation prose; kept as evidence",
    "echem_procedure": "procedure prose; kept as evidence",
}
#: Backwards-compatible name (LOCAL-P v0).
NOT_A_CONDITION = BOOKKEEPING_KEYS

#: Not decided by this build — a scientist (Angel/Oscar) decides. key -> the question.
UNKNOWN_KEYS: Mapping[str, str] = {
    "new_spot": "Is a measurement on a new spot of the same sample a REPEAT (merge) or a different result?",
    "step_number": "Is a numbered step (e.g. `stepNN`) a repeat at the same condition, or a different point in a protocol?",
    "unknown_token": "The acquisition file name carries tokens no naming profile recognises; do they mark a different condition?",
}


def classify_key(key: str, *, overrides: Mapping[str, str] | None = None) -> str:
    if overrides and key in overrides:
        return overrides[key]
    if key in CONDITION_KEYS:
        return CLASS_CONDITION
    if key in BOOKKEEPING_KEYS:
        return CLASS_BOOKKEEPING
    return CLASS_UNKNOWN


_UNKNOWN_TOKEN = "unknown_token"
_TOKEN_SPLIT = re.compile(r"[_\-\s.]+")
_ALIGN_PREFIXES = ("align", "rough")
_REFERENCE_PREFIXES = ("foil", "calib", "reference", "standard")
_REFERENCE_EXACT = frozenset({"ref", "std", "stds", "refs"})
_ENGINE_ROLE = {"alignment": ROLE_ALIGNMENT, "standard_or_reference": ROLE_REFERENCE}
_NUMBERED_SCAN = re.compile(r"^(?P<stem>.+)\.(?P<index>\d{3})$")
_SCAN_FILE_INDEX = re.compile(r"_(\d+)\.[A-Za-z0-9]+$")
_NUMBER_UNIT = re.compile(r"^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*([A-Za-z%]*)\s*$")
_EXPORT_EXT = re.compile(r"^(?P<base>.+)\.(dat|nor|xmu|txt|csv|chi)$", re.IGNORECASE)


# --- readings ------------------------------------------------------------------------------


def _norm_literal(text: Any) -> str | None:
    if text is None:
        return None
    s = str(text).strip().casefold()
    return s or None


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


def _literals(candidate: Mapping) -> list[str]:
    return sorted({x for x in (_norm_literal(v) for v in candidate.get("observed_literals") or ()) if x})


def _reading(candidate: Mapping, run: Mapping) -> dict | None:
    state = candidate.get("value_state") or candidate.get("extracted_state")
    if state == "rejected":
        return None
    if candidate.get("extracted_state") == "conflicting" or state == "conflicting":
        return {"kind": "conflicting", "readings": _literals(candidate)}
    if candidate.get("statement_key") == _UNKNOWN_TOKEN:
        acq = run.get("acquisition_source_id")
        toks = sorted(
            {
                x
                for x in (
                    _norm_literal(e.get("literal_value"))
                    for e in candidate.get("evidence") or ()
                    if acq is not None and e.get("source_id") == acq
                )
                if x
            }
        )
        return {"kind": "literal", "value": toks} if toks else None
    if candidate.get("value") is not None:
        return {"kind": "value", "value": candidate["value"]}
    lits = _literals(candidate)
    if not lits:
        return None
    return {"kind": "literal", "value": lits[0] if len(lits) == 1 else lits}


# --- engine misreadings --------------------------------------------------------------------


def _scan_file_indexes(run: Mapping) -> dict[str, int]:
    out = {}
    for s in run.get("scans") or ():
        idx = s.get("scan_index")
        if idx is None:
            m = _SCAN_FILE_INDEX.search(str(s.get("relative_path") or ""))
            idx = int(m.group(1)) if m else None
        if s.get("source_id") and idx is not None:
            out[s["source_id"]] = int(idx)
    return out


def _scan_index_misread(c: Mapping, run: Mapping) -> dict | None:
    """A conflict whose every scan-file witness is that scan file's own index token."""
    if c.get("evidence_truncated"):
        return None
    idx = _scan_file_indexes(run)
    ev = list(c.get("evidence") or ())
    on_scans = [e for e in ev if e.get("source_id") in idx]
    if not on_scans:
        return None
    for e in on_scans:
        lit = str(e.get("literal_value") or "").strip()
        if not lit.isdigit() or int(lit) != idx[e["source_id"]]:
            return None
    rest = sorted({x for x in (_norm_literal(e.get("literal_value")) for e in ev if e.get("source_id") not in idx) if x})
    effective = None if not rest else ({"kind": "literal", "value": rest[0]} if len(rest) == 1 else {"kind": "conflicting", "readings": rest})
    return {
        "code": "scan_index_token_read_as_value",
        "rule_id": ENGINE_RULE_ID,
        "statement_key": c.get("statement_key"),
        "candidate_id": c.get("candidate_id"),
        "detail": "every scan-file witness is that scan file's own trailing index (`_001` -> 1)",
        "evidence": [{"source_id": e.get("source_id"), "locator": e.get("locator"), "literal": e.get("literal_value"), "scan_file_index": idx[e["source_id"]]} for e in on_scans[:10]],
        "effective_reading": effective,
    }


#: The unit each numeric key is stated in by its field. Unit-spelling normalisation is applied
#: ONLY when the one unit written is this one (never a conversion: `9.1754 keV` is not read).
FIELD_UNITS: Mapping[str, str] = {"emission_energy": "ev"}

#: Misreadings detected mechanically and unambiguously: the run still joins a PROPOSED group
#: (a scientist confirms every group) and the group records `merged_despite_engine_reading`.
MERGEABLE_MISREADINGS = frozenset({"scan_index_token_read_as_value", "same_value_different_unit_spelling"})


def _unit_spelling_misread(c: Mapping) -> dict | None:
    """A conflict whose readings are one number written with and without the field's own unit
    (`9175.4` / `9175.4 eV` for an emission energy)."""
    unit = FIELD_UNITS.get(c.get("statement_key") or "")
    if unit is None:
        return None
    lits = [str(x) for x in c.get("observed_literals") or () if str(x).strip()]
    if len(lits) < 2:
        return None
    nums, units = set(), set()
    for lit in lits:
        m = _NUMBER_UNIT.match(lit)
        if not m:
            return None
        nums.add(float(m.group(1)))
        units.add(m.group(2).casefold())
    if len(nums) != 1 or not (units - {""}) or (units - {""}) != {unit}:
        return None
    return {
        "code": "same_value_different_unit_spelling",
        "rule_id": ENGINE_RULE_ID,
        "statement_key": c.get("statement_key"),
        "candidate_id": c.get("candidate_id"),
        "detail": "the disagreeing readings are one number written with and without its unit",
        "evidence": [{"literal": lit} for lit in lits[:10]],
        "effective_reading": {"kind": "value", "value": nums.pop()},
    }


_TECHNIQUE_WORD = re.compile(r"(xas|xanes|exafs|xafs|herfd|xes|rixs)", re.IGNORECASE)


def _auxiliary_macro_misread(c: Mapping) -> dict | None:
    """An ``acquisition_method`` conflict where exactly ONE reading names a technique
    (``Zz_XAS.mac``) and the others are helper macros a run also calls (``syn_helper.mac``).
    Measured on two real BL15-2 beamtimes: 56 of 92 and 67 of 87 runs."""
    if c.get("statement_key") != "acquisition_method":
        return None
    lits = sorted({str(x).strip() for x in c.get("observed_literals") or () if str(x).strip()})
    named = [x for x in lits if _TECHNIQUE_WORD.search(x)]
    if len(lits) < 2 or len(named) != 1:
        return None
    return {
        "code": "auxiliary_macro_read_as_method",
        "rule_id": ENGINE_RULE_ID,
        "statement_key": "acquisition_method",
        "candidate_id": c.get("candidate_id"),
        "detail": "exactly one disagreeing reading names a technique; the others look like helper macros the run also calls",
        "evidence": [{"literal": x, "names_a_technique": x in named} for x in lits[:10]],
        "effective_reading": {"kind": "literal", "value": _norm_literal(named[0])},
    }


def _sample_number_consistency(run_readings: Sequence[Mapping[str, dict]]) -> dict | None:
    """Beamtime-level: does `sample_or_electrode_number` identify samples at all here?

    When at least two sample numbers are each read beside two or more DIFFERENT sample
    names, and they are at least half of the numbers read beside a name, the number is not
    a sample identifier in this beamtime (measured: a naming profile reading the run counter
    as the sample number). Reported with counts; the key is then treated as ``unknown``.
    """
    by_number: dict[str, set] = {}
    for r in run_readings:
        n, s = r.get("sample_or_electrode_number"), r.get("sample_name")
        if not n or not s or n["kind"] == "conflicting" or s["kind"] == "conflicting":
            continue
        by_number.setdefault(_canon(n.get("value")), set()).add(_canon(s.get("value")))
    several = [k for k, names in by_number.items() if len(names) > 1]
    if len(several) >= 2 and len(several) * 2 >= len(by_number):
        return {
            "code": "sample_number_inconsistent_with_sample_name",
            "rule_id": ENGINE_RULE_ID,
            "statement_key": "sample_or_electrode_number",
            "detail": f"{len(several)} of {len(by_number)} sample numbers are each read beside two or more different sample names",
            "numbers_with_several_names": len(several),
            "numbers_with_a_name": len(by_number),
            "reclassified_as": CLASS_UNKNOWN,
        }
    return None


def engine_reading_issues(bundle: Mapping) -> dict:
    """Every known engine misreading in ``bundle``: per run and beamtime-level. No I/O."""
    cands = {c["candidate_id"]: c for c in bundle.get("candidates") or () if "candidate_id" in c}
    per_run: dict[str, list[dict]] = {}
    for run in bundle.get("runs") or ():
        for cid in run.get("candidate_ids") or ():
            c = cands.get(cid)
            if not c or c.get("extracted_state") != "conflicting":
                continue
            if classify_key(c.get("statement_key") or "") == CLASS_BOOKKEEPING:
                continue
            issue = _scan_index_misread(c, run) or _unit_spelling_misread(c) or _auxiliary_macro_misread(c)
            if issue:
                per_run.setdefault(run["run_key"], []).append(issue)
    for run_key, issue in _exported_file_misreads(bundle):
        per_run.setdefault(run_key, []).append(issue)
    return {"per_run": per_run}


def _exported_file_misreads(bundle: Mapping) -> list[tuple[str, dict]]:
    out = []
    stems = {r.get("stem"): r["run_key"] for r in bundle.get("runs") or () if int(r.get("scan_count") or 0) > 0}
    for run in bundle.get("runs") or ():
        m = _EXPORT_EXT.match(str(run.get("stem") or ""))
        if int(run.get("scan_count") or 0) == 0 and m and m.group("base") in stems:
            out.append((run["run_key"],
                {
                    "code": "exported_file_read_as_acquisition",
                    "rule_id": ENGINE_RULE_ID,
                    "statement_key": None,
                    "detail": "a zero-scan run named like another run plus a data-file extension: likely the scientist's exported/processed file of that run",
                    "evidence": [{"stem": run.get("stem"), "source_id": run.get("acquisition_source_id"), "same_as_run_key": stems[m.group("base")]}],
                    "related_run_key": stems[m.group("base")],
                }
            ))
    return out


# --- per-run reading -----------------------------------------------------------------------


def _run_readings(run: Mapping, cands: Mapping[str, Mapping], issues: Sequence[Mapping]) -> tuple[dict[str, dict], dict[str, list]]:
    """(grouping readings by key, bookkeeping literals by key). Engine misreadings applied."""
    fixed = {i["candidate_id"]: i for i in issues if i.get("candidate_id")}
    out: dict[str, dict] = {}
    books: dict[str, list] = {}
    for cid in run.get("candidate_ids") or ():
        c = cands.get(cid)
        if c is None or not c.get("statement_key"):
            continue
        key = c["statement_key"]
        if classify_key(key) == CLASS_BOOKKEEPING:
            if key in ("legacy_run_or_file_number", "repeat_marker"):
                books.setdefault(key, []).extend(c.get("observed_literals") or [])
            continue
        if cid in fixed:
            r = fixed[cid]["effective_reading"]
            r = dict(r, engine_reading_issue=fixed[cid]["code"]) if r else None
        else:
            r = _reading(c, run)
        if r is None:
            continue
        prev = out.get(key)
        if prev is None:
            out[key] = {**r, "candidate_ids": [cid]}
            continue
        ids = prev["candidate_ids"] + [cid]
        if prev["kind"] != "conflicting" and r["kind"] != "conflicting" and _canon(prev.get("value")) == _canon(r.get("value")):
            out[key] = {**prev, "candidate_ids": ids}
        else:
            readings = sorted({_canon(x.get("value") if x["kind"] != "conflicting" else x.get("readings")) for x in (prev, r)})
            out[key] = {"kind": "conflicting", "readings": readings, "candidate_ids": ids}
    return out, books


def _comparable(reading: Mapping | None) -> str | None:
    if reading is None:
        return None
    return _canon({"kind": reading["kind"], "value": reading.get("value"), "readings": reading.get("readings")})


def _category(key: str, klass: str) -> str:
    if klass == CLASS_UNKNOWN:
        return "unclassified"
    if key in SAMPLE_KEYS:
        return "sample"
    if key in TECHNIQUE_KEYS:
        return "technique"
    if key in ENVIRONMENT_KEYS:
        return "environment"
    return "conditions"


# --- roles ---------------------------------------------------------------------------------


def _name_tokens(name: str) -> list[str]:
    return [t for t in _TOKEN_SPLIT.split(name.casefold()) if t]


def role_from_name(name: str) -> tuple[str, str] | None:
    """(role, token) when a name token marks a reference or alignment acquisition."""
    for tok in _name_tokens(name):
        if tok.startswith(_ALIGN_PREFIXES):
            return ROLE_ALIGNMENT, tok
    for tok in _name_tokens(name):
        if tok.startswith(_REFERENCE_PREFIXES) or tok in _REFERENCE_EXACT:
            return ROLE_REFERENCE, tok
    return None


def run_role(run: Mapping, sources_by_id: Mapping[str, Mapping] | None = None) -> tuple[str, dict]:
    """The run's role and the evidence for it (``isaac.grouping.run_role.v0``).

    1. The engine's content-led classifier: ``source_type`` ``alignment`` -> alignment,
       ``standard_or_reference`` -> reference.
    2. Otherwise a stem token: starting ``align``/``rough`` -> alignment; starting
       ``foil``/``calib``/``reference``/``standard`` or equal to ``ref``/``std`` -> reference.
    3. Otherwise ``sample``.
    """
    stype = run.get("source_type")
    acq = (sources_by_id or {}).get(run.get("acquisition_source_id") or "", {})
    if stype in _ENGINE_ROLE:
        cls = acq.get("classification") or {}
        return _ENGINE_ROLE[stype], {
            "rule_id": ROLE_RULE_ID,
            "basis": "engine_classifier",
            "source_type": stype,
            "classifier_id": cls.get("classifier_id"),
            "classifier_reason": cls.get("reason"),
            "source_id": run.get("acquisition_source_id"),
        }
    named = role_from_name(str(run.get("stem") or run.get("label") or ""))
    if named:
        return named[0], {"rule_id": ROLE_RULE_ID, "basis": "name_token", "token": named[1], "name": run.get("stem"), "source_id": run.get("acquisition_source_id")}
    return ROLE_SAMPLE, {"rule_id": ROLE_RULE_ID, "basis": "default_sample", "source_type": stype}


# --- grouping ------------------------------------------------------------------------------


def group_id_for(experiment_key: str, run_keys: Iterable[str]) -> str:
    h = hashlib.sha256((experiment_key + "\n" + "\n".join(sorted(run_keys))).encode("utf-8")).hexdigest()
    return "rg-" + h[:16]


def experiment_key_of(bundle: Mapping) -> str:
    """One ISAAC experiment = one beamtime folder: the source root's NAME (never a path)."""
    root = bundle.get("source_root") or {}
    return "experiment:" + str(root.get("label") or bundle.get("bundle_id") or "unnamed")


def _basis(readings_list: Sequence[Mapping[str, dict]], classes: Mapping[str, str]) -> dict:
    basis: dict = {"sample": {}, "technique": {}, "environment": {}, "conditions": {}, "unclassified": {}}
    for key in sorted({k for r in readings_list for k in r}):
        rs = [r[key] for r in readings_list if key in r]
        first = rs[0]
        entry: dict = {
            "value": None if first["kind"] == "conflicting" else first.get("value"),
            "kind": first["kind"],
            "key_class": classes[key],
            "candidate_ids": sorted({cid for r in rs for cid in r["candidate_ids"]}),
        }
        if first["kind"] == "conflicting":
            entry["readings"] = first.get("readings")
        if first.get("engine_reading_issue"):
            entry["engine_reading_issue"] = first["engine_reading_issue"]
        basis[_category(key, classes[key])][key] = entry
    return basis


def _shown(r: Mapping | None):
    if r is None:
        return None
    return {"conflicting": r.get("readings")} if r["kind"] == "conflicting" else r.get("value")


def _diff(a: Mapping[str, dict], b: Mapping[str, dict], classes: Mapping[str, str]) -> list[dict]:
    out = []
    for key in sorted(set(a) | set(b)):
        ca, cb = _comparable(a.get(key)), _comparable(b.get(key))
        if ca == cb:
            continue
        if ca is None or cb is None:
            kind = "unknown_vs_known"
        elif a[key]["kind"] == "conflicting" or b[key]["kind"] == "conflicting":
            kind = "conflicting"
        else:
            kind = "differs"
        out.append({"condition": key, "key_class": classes[key], "category": _category(key, classes[key]), "kind": kind, "this": _shown(a.get(key)), "other": _shown(b.get(key))})
    return out


def propose(bundle: Mapping, *, max_split_reasons: int = 20) -> dict:
    """Groups, merge candidates and engine-reading issues for ``bundle`` (deterministic; no I/O)."""
    runs: Sequence[Mapping] = bundle.get("runs") or ()
    cands = {c["candidate_id"]: c for c in bundle.get("candidates") or () if "candidate_id" in c}
    sources = {s["source_id"]: s for s in bundle.get("sources") or () if "source_id" in s}
    exp_key = experiment_key_of(bundle)
    eng = engine_reading_issues(bundle)

    raw = [_run_readings(run, cands, eng["per_run"].get(run["run_key"], [])) for run in runs]
    beamtime_issues = []
    overrides: dict[str, str] = {}
    sn = _sample_number_consistency([r for r, _ in raw])
    if sn:
        beamtime_issues.append(sn)
        overrides["sample_or_electrode_number"] = CLASS_UNKNOWN

    def klass(key: str) -> str:
        return classify_key(key, overrides=overrides)

    infos = []
    for index, (run, (readings, books)) in enumerate(zip(runs, raw)):
        role, role_basis = run_role(run, sources)
        classes = {k: klass(k) for k in readings}
        hard = sorted(k for k, r in readings.items() if r["kind"] == "conflicting" and classes[k] == CLASS_CONDITION)
        soft = sorted(k for k, r in readings.items() if r["kind"] == "conflicting" and classes[k] == CLASS_UNKNOWN)
        sample_known = any(k in readings and readings[k]["kind"] != "conflicting" and classes[k] == CLASS_CONDITION for k in SAMPLE_KEYS)
        scans = int(run.get("scan_count") or len(run.get("scans") or ()))
        issues = eng["per_run"].get(run["run_key"], [])
        blocking = [i for i in issues if i["code"] not in MERGEABLE_MISREADINGS]
        blockers = []
        if hard:
            blockers.append("conflicting_condition")
        if soft:
            blockers.append("conflicting_unknown_key")
        if not sample_known:
            blockers.append("sample_identity_not_stated")
        if scans == 0:
            blockers.append("no_scans")
        if blocking:
            blockers.append("blocked_by_engine_reading")
        cond_sig = _canon({k: _comparable(r) for k, r in sorted(readings.items()) if classes[k] == CLASS_CONDITION})
        unk_sig = _canon({k: _comparable(r) for k, r in sorted(readings.items()) if classes[k] == CLASS_UNKNOWN})
        infos.append(
            {
                "index": index, "run": run, "readings": readings, "books": books, "classes": classes,
                "role": role, "role_basis": role_basis, "hard": hard, "soft": soft, "blockers": blockers,
                "issues": issues, "blocking": blocking, "cond_sig": cond_sig, "unk_sig": unk_sig, "scans": scans,
                "candidate_eligible": not hard and scans > 0,
            }
        )

    buckets: dict[Any, list[dict]] = {}
    for info in infos:
        key = ("merge", info["role"], info["cond_sig"], info["unk_sig"]) if not info["blockers"] else ("alone", info["index"])
        buckets.setdefault(key, []).append(info)

    groups = []
    for members in buckets.values():
        run_keys = [m["run"]["run_key"] for m in members]
        first = members[0]
        classes = {k: c for m in members for k, c in m["classes"].items()}
        flags: list[str] = []
        if any(m["run"].get("legacy_number_shared") for m in members):
            flags.append("duplicate_legacy_number")
        if any(m["books"].get("repeat_marker") for m in members):
            flags.append("repeat_marker_present")
        if not any(k in first["readings"] for k in TECHNIQUE_KEYS):
            flags.append("technique_not_stated")
        if len(members) > 1:
            flags.append("multi_run_group")
        if first["blocking"]:
            flags.append("blocked_by_engine_reading")
        despite = [
            {"kind": i["code"], "run_key": m["run"]["run_key"], "statement_key": i.get("statement_key"), "evidence": i.get("evidence"), "rule_id": i.get("rule_id")}
            for m in members
            for i in m["issues"]
            if i["code"] in MERGEABLE_MISREADINGS
        ]
        if despite and len(members) > 1:
            flags.append("merged_despite_engine_reading")
        g = {
            "group_id": group_id_for(exp_key, run_keys),
            "experiment_key": exp_key,
            "member_run_keys": run_keys,
            "member_run_ids": [m["run"].get("run_id") for m in members],
            "role": first["role"],
            "role_basis": first["role_basis"],
            "basis": _basis([m["readings"] for m in members], classes),
            "split_reasons": [],
            "status": "proposed",
            "questions": [],
            "flags": flags,
            "merge_candidate_ids": [],
            "engine_reading_issues": [i for m in members for i in m["issues"]],
            "merged_despite_engine_reading": despite if len(members) > 1 else [],
            "rule_id": GROUPING_RULE_ID,
            "_members": members,
        }
        groups.append(g)
    groups.sort(key=lambda g: g["_members"][0]["index"])
    gid_of_run = {m["run"]["run_key"]: g["group_id"] for g in groups for m in g["_members"]}
    by_gid = {g["group_id"]: g for g in groups}

    qn = 0

    def _question(code: str, text: str, run_keys: list[str], **extra) -> dict:
        nonlocal qn
        qn += 1
        return {"question_id": f"rgq-{qn:04d}", "code": code, "text": text, "run_keys": run_keys, **extra}

    for g in groups:
        m0 = g["_members"][0]
        run = m0["run"]
        if len(g["_members"]) > 1:
            note = ""
            if g["merged_despite_engine_reading"]:
                kinds = sorted({d["kind"] for d in g["merged_despite_engine_reading"]})
                plain = {
                    "scan_index_token_read_as_value": "the importer read scan-file numbers (_001, _002) as a sample number",
                    "same_value_different_unit_spelling": "the importer saw one value written with and without its unit as a disagreement",
                }
                note = " They were grouped even though " + "; and ".join(plain[k] for k in kinds) + " — check that this is all that differs."
            g["questions"].append(
                _question(
                    "confirm_repeats_merge",
                    f"These {len(g['_members'])} runs agree on every condition and differ only in bookkeeping. "
                    "They look like repeats of the same measurement — merge them into one record?" + note,
                    g["member_run_keys"],
                    differing_bookkeeping=[
                        {
                            "run_key": m["run"]["run_key"],
                            "stem": m["run"].get("stem"),
                            "legacy_run_or_file_number": m["books"].get("legacy_run_or_file_number") or [],
                            "repeat_marker": m["books"].get("repeat_marker") or [],
                        }
                        for m in g["_members"]
                    ],
                )
            )
        if "conflicting_condition" in m0["blockers"]:
            for key in m0["hard"]:
                g["split_reasons"].append({"code": "conflicting_condition", "condition": key, "readings": m0["readings"][key].get("readings")})
            g["questions"].append(
                _question(
                    "resolve_conflicting_condition",
                    f"The sources disagree about {', '.join(m0['hard'])} for run {run.get('run_id')}. Which reading is right? Until then this run is its own group.",
                    [run["run_key"]],
                    conditions=m0["hard"],
                )
            )
        if "sample_identity_not_stated" in m0["blockers"]:
            g["split_reasons"].append({"code": "sample_identity_not_stated"})
            g["questions"].append(
                _question(
                    "state_sample_identity",
                    f"No source states which sample run {run.get('run_id')} measured, so it cannot be grouped automatically. Which sample is it?",
                    [run["run_key"]],
                )
            )
        if "no_scans" in m0["blockers"]:
            g["split_reasons"].append({"code": "no_scans"})
        if "blocked_by_engine_reading" in m0["blockers"]:
            g["split_reasons"].append({"code": "blocked_by_engine_reading", "issues": [i["code"] for i in m0["issues"]]})
        for key in m0["soft"]:
            g["split_reasons"].append({"code": "conflicting_unknown_key", "condition": key})

    # Condition differences between auto-eligible groups of the same sample and role.
    def _sample_sig(g: Mapping) -> str:
        r = g["_members"][0]["readings"]
        return _canon({k: _comparable(r.get(k)) for k in SAMPLE_KEYS})

    by_sample: dict[tuple, list[dict]] = {}
    for g in groups:
        if not g["_members"][0]["blockers"]:
            by_sample.setdefault((g["role"], _sample_sig(g)), []).append(g)
    for peers in by_sample.values():
        for i, g in enumerate(peers):
            ra = g["_members"][0]["readings"]
            classes = {**g["_members"][0]["classes"]}
            for h in peers:
                if h is g:
                    continue
                cls = {**classes, **h["_members"][0]["classes"]}
                diffs = [d for d in _diff(ra, h["_members"][0]["readings"], cls) if d["key_class"] == CLASS_CONDITION]
                if not diffs:
                    continue
                if len(g["split_reasons"]) < max_split_reasons:
                    g["split_reasons"].append({"code": "conditions_differ", "other_group_id": h["group_id"], "differences": diffs})
                else:
                    g["_dropped"] = g.get("_dropped", 0) + 1
                if all(d["kind"] == "unknown_vs_known" for d in diffs) and peers.index(h) > i:
                    keys = [d["condition"] for d in diffs]
                    q = _question(
                        "unknown_vs_known_condition",
                        f"Groups {g['group_id']} and {h['group_id']} agree on everything stated, but {', '.join(keys)} is stated for one and not the other. Same condition (merge) or not?",
                        g["member_run_keys"] + h["member_run_keys"],
                        conditions=keys,
                        group_ids=[g["group_id"], h["group_id"]],
                    )
                    g["questions"].append(q)
                    h["questions"].append(q)
        for g in peers:
            if g.get("_dropped"):
                g["split_reasons"].append({"code": "split_reasons_truncated", "limit": max_split_reasons, "omitted": g.pop("_dropped")})

    # Merge candidates: same role + equal CONDITION readings, more than one proposed group.
    merge_candidates: list[dict] = []
    classes_all: dict[str, dict] = {}
    pools: dict[tuple, list[dict]] = {}
    for info in infos:
        if info["candidate_eligible"]:
            pools.setdefault((info["role"], info["cond_sig"]), []).append(info)
    seen_sets = set()

    def _add_candidate(member_infos: list[dict], extra_reasons: list[dict] | None = None):
        gids = sorted({gid_of_run[m["run"]["run_key"]] for m in member_infos}, key=lambda x: [g["group_id"] for g in groups].index(x))
        if len(gids) < 2 or tuple(gids) in seen_sets:
            return
        seen_sets.add(tuple(gids))
        reasons: list[dict] = list(extra_reasons or [])
        unk_keys = sorted({k for m in member_infos for k, c in m["classes"].items() if c == CLASS_UNKNOWN})
        for key in unk_keys:
            vals = {}
            for m in member_infos:
                vals.setdefault(gid_of_run[m["run"]["run_key"]], _shown(m["readings"].get(key)))
            if len({_canon(v) for v in vals.values()}) > 1:
                why = UNKNOWN_KEYS.get(key) or next((i["detail"] for i in beamtime_issues if i.get("statement_key") == key), None) or "a key this build has not classified"
                reasons.append({"code": "unknown_key_differs", "key": key, "values_by_group": vals, "why_unknown": why})
        for m in member_infos:
            for issue in m["blocking"]:
                reasons.append({"code": "blocked_by_engine_reading", "group_id": gid_of_run[m["run"]["run_key"]], "issue": {k: v for k, v in issue.items() if k != "effective_reading"}})
            if "sample_identity_not_stated" in m["blockers"]:
                reasons.append({"code": "sample_identity_not_stated", "group_id": gid_of_run[m["run"]["run_key"]]})
            for key in m["soft"]:
                reasons.append({"code": "conflicting_unknown_key", "group_id": gid_of_run[m["run"]["run_key"]], "key": key})
        mcid = "mc-" + hashlib.sha256((exp_key + "\n" + "\n".join(gids)).encode()).hexdigest()[:16]
        nq = _question(
            "merge_candidate",
            f"{len(gids)} groups agree on every condition this build classifies, and differ only in what it cannot decide "
            f"({', '.join(sorted({r['code'] for r in reasons})) or 'unclassified keys'}). Merge them into one record?",
            [k for gid in gids for k in by_gid[gid]["member_run_keys"]],
            merge_candidate_id=mcid,
            group_ids=gids,
        )
        mc = {"merge_candidate_id": mcid, "experiment_key": exp_key, "group_ids": gids, "status": "proposed", "reasons": reasons, "question": nq, "rule_id": GROUPING_RULE_ID}
        merge_candidates.append(mc)
        for gid in gids:
            by_gid[gid]["merge_candidate_ids"].append(mcid)
            by_gid[gid]["questions"].append(nq)

    for pool in pools.values():
        _add_candidate(pool)
    run_info = {i["run"]["run_key"]: i for i in infos}
    for info in infos:
        for issue in info["issues"]:
            if issue["code"] == "exported_file_read_as_acquisition" and issue.get("related_run_key") in run_info:
                _add_candidate([info, run_info[issue["related_run_key"]]], [{"code": "exported_file_read_as_acquisition", "group_id": gid_of_run[info["run"]["run_key"]]}])

    for g in groups:
        g.pop("_members", None)
    key_classes = {
        "condition": dict(CONDITION_KEYS),
        "bookkeeping": dict(BOOKKEEPING_KEYS),
        "unknown": dict(UNKNOWN_KEYS),
        "unknown_rule": "every statement key in none of the three lists is unknown",
        "beamtime_overrides": overrides,
    }
    return {
        "record_groups": groups,
        "merge_candidates": merge_candidates,
        "engine_reading_issues": {"per_run": eng["per_run"], "beamtime": beamtime_issues},
        "key_classes": key_classes,
    }


def propose_record_groups(bundle: Mapping, *, max_split_reasons: int = 20) -> list[dict]:
    """The proposed ``record_groups[]`` for ``bundle`` (see :func:`propose` for the rest)."""
    return propose(bundle, max_split_reasons=max_split_reasons)["record_groups"]


# --- runs the import did not read ------------------------------------------------------------


def propose_unread_acquisition_groups(bundle: Mapping) -> list[dict]:
    """Groups for acquisitions the import engine has NO reader for (``isaac.grouping.unread_numbered_scans.v0``).

    Measured: SSRL BL4-3 XDAC exports (``<stem>.001``, ``<stem>.002``) are inventoried but
    not read, so the bundle has no run for them. Rule: unread files in one directory whose
    basename is ``<stem>.<NNN>`` (three digits) are the numbered scans of ONE acquisition.
    Nothing about sample or condition is known (no reader extracted it), so each
    acquisition is its own group and asks a question; acquisitions are never merged.

    These are NOT ``record_groups`` (they name no bundle ``run_key``); they are reported
    beside them so the processing step can still run and be compared with Athena.
    """
    exp_key = experiment_key_of(bundle)
    sources = {s.get("source_id"): s for s in bundle.get("sources") or ()}
    acqs: dict[tuple[str, str], list[dict]] = {}
    for u in bundle.get("unread_files") or ():
        path = u.get("relative_path")
        if not path:
            continue
        # Only files the walk read as TEXT (classifier confidence "content"). Measured on
        # BL4-3: a binary twin of every export (``binary/x.001``) is inventoried with
        # confidence "unknown" ("no content was supplied") and is not a second acquisition.
        cls = (sources.get(u.get("source_id")) or {}).get("classification") or {}
        if cls and cls.get("confidence") != "content":
            continue
        parent, _, base = str(path).rpartition("/")
        m = _NUMBERED_SCAN.match(base)
        if not m:
            continue
        acqs.setdefault((parent, m.group("stem")), []).append(
            {"source_id": u.get("source_id"), "relative_path": path, "scan_index": int(m.group("index"))}
        )
    out = []
    for (parent, stem), scans in sorted(acqs.items()):
        scans.sort(key=lambda s: s["scan_index"])
        key = f"unread:{parent}/{stem}" if parent else f"unread:{stem}"
        named = role_from_name(stem)
        role = named[0] if named else ROLE_SAMPLE
        out.append(
            {
                "group_id": group_id_for(exp_key, [key]),
                "group_kind": "unread_acquisition",
                "experiment_key": exp_key,
                "acquisition_key": key,
                "stem": stem,
                "member_run_keys": [],
                "member_scans": scans,
                "role": role,
                "role_basis": {"rule_id": ROLE_RULE_ID, "basis": "name_token", "token": named[1], "name": stem}
                if named
                else {"rule_id": ROLE_RULE_ID, "basis": "default_sample"},
                "basis": {"sample": {}, "technique": {}, "environment": {}, "conditions": {}},
                "split_reasons": [{"code": "conditions_not_extracted_by_import"}],
                "status": "proposed",
                "questions": [
                    {
                        "question_id": f"ruq-{len(out) + 1:04d}",
                        "code": "conditions_not_extracted",
                        "text": f"The import has no reader for {stem}'s files, so its sample and conditions are unknown. Which sample and condition is it?",
                        "run_keys": [],
                    }
                ],
                "flags": ["no_bundle_run", "conditions_unknown"],
                "rule_id": UNREAD_RULE_ID,
            }
        )
    return out


UNREAD_NAME_RULE_ID = "isaac.grouping.unread_name_counters.v0"
_LEADING_COUNTER = re.compile(r"^\d+_")
_TRAILING_COUNTER = re.compile(r"_\d+(_[A-Za-z])?$")


def propose_unread_merge_candidates(groups: Sequence[Mapping]) -> list[dict]:
    """Merge CANDIDATES (never merges) among acquisitions no reader extracted conditions for.

    ``isaac.grouping.unread_name_counters.v0``: two acquisitions of the same role whose
    names are equal once a leading run counter (``17_``) and a trailing acquisition counter
    (``_098``, ``_098_A``) are removed. The name is the only evidence available, so this
    only ASKS; a scientist decides.
    """
    pools: dict[tuple, list[Mapping]] = {}
    for g in groups:
        stem = str(g.get("stem") or "")
        core = _TRAILING_COUNTER.sub("", _LEADING_COUNTER.sub("", stem))
        if core and core != stem:
            pools.setdefault((g.get("role"), g.get("experiment_key"), core.casefold()), []).append(g)
    out = []
    for (role, exp_key, _), members in pools.items():
        if len(members) < 2:
            continue
        gids = [m["group_id"] for m in members]
        mcid = "mc-" + hashlib.sha256((str(exp_key) + "\n" + "\n".join(sorted(gids))).encode()).hexdigest()[:16]
        out.append(
            {
                "merge_candidate_id": mcid,
                "experiment_key": exp_key,
                "group_ids": gids,
                "status": "proposed",
                "reasons": [{"code": "names_differ_only_in_counters", "stems": [m.get("stem") for m in members]}],
                "question": {
                    "code": "merge_candidate",
                    "text": f"{len(gids)} acquisitions have the same name apart from run/acquisition counters, and no reader extracted their conditions. Are they repeats of one measurement?",
                    "group_ids": gids,
                    "merge_candidate_id": mcid,
                },
                "rule_id": UNREAD_NAME_RULE_ID,
            }
        )
    return out


def _attr(obj: Any, *names: str, default: Any = None) -> Any:
    for n in names:
        if isinstance(obj, Mapping) and n in obj:
            return obj[n]
        if hasattr(obj, n):
            return getattr(obj, n)
    return default


def groups_from_generic_runs(runs: Iterable[Any], *, experiment_key: str, sources_by_path: Mapping[str, str] | None = None) -> list[dict]:
    """Adapter: groups for runs produced by a NON-engine reader (e.g. the SSRL XDC reader's
    ``collect_generic_runs(root) -> list[GenericRun]``). Duck-typed — each run needs a
    ``stem`` (or ``name``/``run_key``) and ``scans``; each scan a ``relative_path`` (or
    ``path``) and optionally ``scan_index``. As for unread acquisitions, no condition was
    extracted, so each run is its own group with a question; runs are never merged.
    """
    out = []
    for run in runs:
        stem = str(_attr(run, "stem", "name", "run_key", default="") or "")
        key = str(_attr(run, "run_key", default=None) or f"generic:{stem}")
        scans = []
        for i, sc in enumerate(_attr(run, "scans", default=()) or ()):
            rel = str(_attr(sc, "relative_path", "path", default="") or "")
            scans.append(
                {
                    "source_id": (sources_by_path or {}).get(rel) or _attr(sc, "source_id", default=None),
                    "relative_path": rel,
                    "scan_index": _attr(sc, "scan_index", "index", default=i + 1),
                }
            )
        named = role_from_name(stem)
        out.append(
            {
                "group_id": group_id_for(experiment_key, [key]),
                "group_kind": "generic_run",
                "experiment_key": experiment_key,
                "acquisition_key": key,
                "stem": stem,
                "member_run_keys": [],
                "member_scans": scans,
                "role": named[0] if named else ROLE_SAMPLE,
                "role_basis": {"rule_id": ROLE_RULE_ID, "basis": "name_token", "token": named[1], "name": stem}
                if named
                else {"rule_id": ROLE_RULE_ID, "basis": "default_sample"},
                "basis": {"sample": {}, "technique": {}, "environment": {}, "conditions": {}},
                "split_reasons": [{"code": "conditions_not_extracted_by_import"}],
                "status": "proposed",
                "questions": [
                    {
                        "question_id": f"rgg-{len(out) + 1:04d}",
                        "code": "conditions_not_extracted",
                        "text": f"No condition was extracted for {stem}. Which sample and condition is it?",
                        "run_keys": [],
                    }
                ],
                "flags": ["no_bundle_run", "conditions_unknown"],
                "rule_id": GROUPING_RULE_ID,
            }
        )
    return out


def summarize_groups(groups: Sequence[Mapping]) -> dict:
    roles: dict[str, int] = {}
    for g in groups:
        roles[g.get("role", "?")] = roles.get(g.get("role", "?"), 0) + 1
    return {
        "groups": len(groups),
        "multi_run_groups": sum(1 for g in groups if len(g.get("member_run_keys") or ()) > 1),
        "runs_grouped": sum(len(g.get("member_run_keys") or ()) for g in groups),
        "by_role": dict(sorted(roles.items())),
        "with_questions": sum(1 for g in groups if g.get("questions")),
    }
