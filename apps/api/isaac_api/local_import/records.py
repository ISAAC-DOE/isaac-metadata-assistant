"""From a reviewed bundle to official ISAAC records — compose, validate, export, dry-run.

``isaac bundle build-records`` — one ISAAC DRAFT (the repository's envelope format,
``draft_validator`` / ``export``) per ``scientist_confirmed`` record group. Values come
ONLY from:

* candidates that are ``scientist_confirmed`` AND eligible (decision value applied);
* ``missing_values`` a scientist answered (``confirm``/``correct`` with a value);
* the group's processing result a scientist APPROVED (series, qc, the E0 descriptor).

Beamtime-scope confirmed values (facility, beamline, technique, ...) apply to every
record EXCEPT ``context.environment``, ``context.electrochemistry.reaction`` and
``context.electrochemistry.cell_type`` (DEC-69: never filled from a beamtime fact).
Two confirmed values that differ for one path inside a group fill nothing and are
listed. Every required value nobody supplied stays a ``status: missing`` envelope and
is listed — nothing is defaulted, no temperature is assumed.

``isaac bundle validate`` — per draft: ``validate_draft`` → export DRY RUN through
``isaac_records.export.export_draft`` (writes nothing) → ``validate_official`` +
``check_exactness`` (vendored v1.05) → the OFFLINE upstream portal check
(:mod:`.portal`). Every error and warning is kept verbatim in
``validation/<group_id>.json`` with a plain-English summary. A disagreement between the
vendored and upstream schemas is reported as ``blocked_by_schema_drift``.

``isaac bundle export`` — writes ``<ULID>.json`` + ``<ULID>.evidence.json`` ONLY for a
record that passes official validation AND whose portal outcome is ``publish``.

``isaac bundle upload --dry-run`` — prints what WOULD be sent. No network call, ever;
without ``--dry-run`` it refuses.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import bundle as B

DRAFTS_DIR = "drafts"
VALIDATION_DIR = "validation"
#: Never filled from a beamtime-scope value (DEC-69).
RUN_ONLY_PATHS = frozenset(
    {"context.environment", "context.electrochemistry.reaction", "context.electrochemistry.cell_type"}
)
#: How a required schema object is asked for as a scalar field.
REQUIRED_AS_FIELD = {"sample.material": "sample.material.name"}
#: Required paths that come from an approved processing result, not from fields.
STRUCTURED_REQUIRED = frozenset({"measurement.series", "measurement.qc.status", "descriptors.outputs"})
META = {"record_type": "evidence", "record_domain": "characterization", "source_type": "facility"}
#: DEC-76: an engine target path -> its home in the portal's (upstream) schema.
FIELD_REMAP = {"context.electrochemistry.reaction": "context.reaction.name"}
#: Approved processing step -> the upstream vocabulary token (measurement.processing.steps),
#: exactly as `data/vocabulary.json` @ a1cb1c8 spells it. `deglitch` and `qc` have none.
PROCESSING_STEP_VOCABULARY = {"calibration": "calibration", "merge": "spectrum_merging", "normalize": "normalization"}
PORTAL_VALIDATE = "/portal/api/validate"
PORTAL_RECORDS = "/portal/api/records"


class RecordsRefused(ValueError):
    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


def _repo_root() -> Path:
    from .. import workspace as ws

    return ws.REPO_ROOT


# --- composition ----------------------------------------------------------------------------


def _witnesses(candidate: Mapping) -> list[dict]:
    out = []
    for e in candidate["evidence"]:
        if e["method"] == "ai_interpretation":
            continue  # an interpretation is not observed evidence
        out.append(
            {
                "source_type": "document",
                "source_file": e["relative_path"] or "(unlocated)",
                "locator": e["locator"],
                "quote": e["literal_value"] if isinstance(e["literal_value"], str) else json.dumps(e["literal_value"]),
                "method": e["method"],
                "method_id": e["method_id"],
            }
        )
    return out


def _confirmation(decision: Mapping, question: str) -> dict:
    by = decision.get("decided_by") or {}
    entry = {
        "source_type": "user_confirmation",
        "question": question,
        "answer": decision.get("value") if isinstance(decision.get("value"), str) else json.dumps(decision.get("value")),
        "timestamp": decision.get("decided_utc"),
        "decision_id": decision.get("decision_id"),
        "decided_by": by.get("name"),
        "identity": by.get("identity", "local_unverified"),
    }
    if by.get("orcid_claimed"):
        entry["orcid_claimed"] = by["orcid_claimed"]["value"]
    return entry


def _absorber_implicit(bundle: Mapping, group: Mapping) -> list[dict]:
    """``implicit[]`` entries ``absorbing_element`` and ``edge`` for one group, or ``[]``."""
    from . import suggestions as S

    sug = S.absorber_for_group(bundle, group)
    decision = S.absorber_decisions(bundle).get(group["group_id"])
    witnesses = [
        {"source_type": "document", "source_file": w.get("relative_path") or "(unlocated)", "locator": w.get("locator"),
         "quote": w.get("literal") or f"{w.get('element') or ''} {w.get('edge') or ''}".strip(),
         "quote_basis": "the file's own statement" if w.get("literal") else f"as the {w.get('role') or 'reader'} rule recorded it, not a literal",
         "method": "stored_rule", "method_id": S.ABSORBER_RULE_ID}
        for w in sug["witnesses"]
    ]
    if decision is None and not witnesses:
        return []
    out = []
    for about, key in (("absorbing_element", "element"), ("edge", "edge")):
        evidence = list(witnesses) or [{"source_type": "derivation", "rule": f"{S.ABSORBER_RULE_ID}: no file states it"}]
        value = None
        if decision is not None:
            value = decision.get(key)
            evidence.append(_confirmation({**decision, "value": value}, f"What is the {about.replace('_', ' ')}?"))
        else:
            evidence.append({"source_type": "derivation",
                             "rule": f"{S.ABSORBER_RULE_ID}: the files suggest {sug[key] or 'nothing single'} ({sug['status']}); "
                                     "needs a scientist's confirmation (set_absorber)"})
        out.append({"about": about, "value": value, "evidence": evidence})
    return out


#: The processing output contract (LOCAL-P ``processing/run.py``, ``normalized.csv``):
#: a ``#`` banner, then the header ``energy_eV,norm,flat``. Columns are selected BY NAME.
SERIES_ENERGY_COLUMN = "energy_eV"
SERIES_SIGNAL_COLUMN = "norm"
SPECTRUM_ROLES = ("normalized", "normalized_spectrum")


def _read_series_file(path: Path) -> tuple[list[float], list[float]] | str:
    """``(energy, normalised mu)`` from a processing output, or the REASON it was refused.

    A header line names the columns and they are selected by name (energy_eV, norm);
    ``flat`` is not read. A headerless file of exactly two numeric columns is still read
    as (energy, signal). Blank cells and non-numeric rows refuse the file — nothing is
    guessed or interpolated."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return f"the file could not be read ({type(exc).__name__})"
    rows = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    if not rows:
        return "the file holds no data rows"
    first = [c.strip() for c in rows[0].replace("\t", ",").split(",")] if "," in rows[0] or "\t" in rows[0] else rows[0].split()

    def numeric(cells):
        try:
            [float(c) for c in cells]
            return True
        except ValueError:
            return False

    if numeric(first):
        xi, yi, data = 0, 1, rows
        if len(first) != 2:
            return f"a headerless file must have exactly two numeric columns; it has {len(first)}"
    else:
        if SERIES_ENERGY_COLUMN not in first or SERIES_SIGNAL_COLUMN not in first:
            return f"the header {first!r} does not name {SERIES_ENERGY_COLUMN!r} and {SERIES_SIGNAL_COLUMN!r}"
        xi, yi, data = first.index(SERIES_ENERGY_COLUMN), first.index(SERIES_SIGNAL_COLUMN), rows[1:]
    xs: list[float] = []
    ys: list[float] = []
    for n, row in enumerate(data, 1):
        cells = [c.strip() for c in row.split(",")] if "," in row else row.split()
        try:
            xs.append(float(cells[xi]))
            ys.append(float(cells[yi]))
        except (ValueError, IndexError):
            return f"data row {n} has no number in the {SERIES_ENERGY_COLUMN}/{SERIES_SIGNAL_COLUMN} columns"
    return (xs, ys) if xs else "the file holds no data rows"


def compose_group(bundle: Mapping, group: Mapping, bundle_dir: Path) -> tuple[dict, dict]:
    """``(draft, composition_report)`` for ONE scientist-confirmed record group."""
    decisions = B._decisions_by_target(bundle.get("scientist_decisions") or ())
    runs_by_key = {r["run_key"]: r for r in bundle["runs"]}
    member_runs = [runs_by_key[k] for k in group["member_run_keys"] if k in runs_by_key]
    member_ids = {r["run_id"] for r in member_runs}
    report: dict[str, Any] = {
        "group_id": group["group_id"],
        "member_run_ids": sorted(member_ids),
        "filled": [],
        "disagreements": [],
        "missing_required": [],
        "not_composed": [],
        "processing": None,
    }
    proposals: dict[str, list[tuple[Any, list, str]]] = {}

    for c in bundle["candidates"]:
        if not c["eligibility_for_official_record"]["eligible"]:
            continue
        in_group = c["run_id"] in member_ids
        beamtime = c["run_id"] is None
        if not (in_group or beamtime):
            continue
        path = c["target_field_path"]
        if beamtime and path in RUN_ONLY_PATHS:
            report["not_composed"].append({"candidate_id": c["candidate_id"], "reason": "DEC-69: a beamtime fact never fills this run-level field"})
            continue
        if "[]" in path:
            report["not_composed"].append({"candidate_id": c["candidate_id"], "path": path, "reason": "an array path; composed only from structured blocks"})
            continue
        d = B.candidate_decision(bundle, c)
        value = B.final_value(c["value"], d, c.get("readings"))
        evidence = _witnesses(c) + [_confirmation({**d, "value": value}, f"Confirm {path}")]
        # DEC-76: the reaction's home in the portal's schema is context.reaction.name;
        # context.electrochemistry.reaction is deprecated there.
        proposals.setdefault(FIELD_REMAP.get(path, path), []).append((value, evidence, c["candidate_id"]))

    for m in bundle["missing_values"]:
        if not m["eligibility_for_official_record"]["eligible"]:
            continue
        if not (m["run_id"] in member_ids or m["run_id"] is None):
            continue
        d = decisions[("missing_value", m["value_id"])]
        value = B.final_value(None, d)
        proposals.setdefault(FIELD_REMAP.get(m["target_field_path"], m["target_field_path"]), []).append(
            (value, [_confirmation(d, f"What is {m['target_field_path']}?")], m["value_id"])
        )

    fields: dict[str, dict] = {}
    for path, options in sorted(proposals.items()):
        distinct = {json.dumps(v, sort_keys=True) for v, _, _ in options}
        if len(distinct) > 1:
            report["disagreements"].append(
                {"path": path, "values": [v for v, _, _ in options], "from": [i for _, _, i in options],
                 "reason": "confirmed values differ inside one record group; nothing is filled"}
            )
            continue
        value = options[0][0]
        evidence = [e for _, ev, _ in options for e in ev]
        fields[path] = {"value": value, "status": "verified", "evidence": evidence}
        report["filled"].append({"path": path, "from": [i for _, _, i in options]})

    draft: dict[str, Any] = {
        "meta": dict(META),
        "fields": fields,
        "assets": [],
        "descriptors_outputs": [],
        "links": [],
        "implicit": [],
        "block_evidence": {},
    }

    # THE ABSORBER (sidecar only: the official schema has no field for it). A scientist's
    # set_absorber decision gives the value; otherwise the files' suggestion is carried with
    # value null, exactly as the hosted path carries an unconfirmed edge.
    absorber = _absorber_implicit(bundle, group)
    if absorber:
        draft["implicit"] += absorber
        report["absorber"] = {"element": absorber[0]["value"], "edge": absorber[1]["value"],
                              "confirmed": absorber[0]["value"] is not None}

    # processing (series, qc, E0 descriptor) — ONLY an approved result
    mine = [r for r in bundle.get("processing_results") or () if r["group_id"] == group["group_id"]]
    approved = [r for r in mine if r["state"] == B.STATE_SCIENTIST_CONFIRMED and not B.processing_not_applicable(r)]
    # A group whose LATEST result says the protocol does not apply cannot get an approved
    # curve from it: that is a blocking reason in its own words, never a fake approval.
    latest_na = B.processing_blocked_groups(bundle).get(group["group_id"])
    not_applicable = [latest_na] if latest_na else []
    blocked_by_protocol = latest_na is not None
    if len(approved) > 1:
        report["processing"] = {"used": None, "reason": "more than one approved processing result; a person chooses one"}
    elif approved:
        r = approved[0]
        pid = B.processing_id(r)
        d = decisions[("processing_result", pid)]
        conf = _confirmation({**d, "value": f"approved {pid}"}, f"Approve processing result {pid}")
        used: dict[str, Any] = {"result": pid}
        files = (r.get("outputs") or {}).get("files") or []
        bound = d.get("approved_files")
        current = [{"role": f.get("role"), "relative_path": f.get("relative_path"), "sha256": f.get("sha256")} for f in files]
        if bound is not None and json.dumps(bound, sort_keys=True) != json.dumps(current, sort_keys=True):
            # The approval names other files than the result now lists: nothing is used.
            files = []
            used["approval"] = "the approval binds to different files than this result now lists; not used"
        roles = (("athena_normalized",) if r.get("source") == "scientist_athena" else ()) + SPECTRUM_ROLES
        spectrum = next((f for role in roles for f in files if f.get("role") == role), None)
        if spectrum is not None:
            fpath = contained_file(Path(bundle_dir), spectrum["relative_path"])
            if fpath is not None and hashlib.sha256(fpath.read_bytes()).hexdigest() == spectrum["sha256"]:
                cols = _read_series_file(fpath)
                if isinstance(cols, str):
                    used["series"] = f"not used: {cols}"
                    cols = None
                if cols:
                    sid = f"{group['group_id']}_normalized"
                    draft["series"] = [
                        {
                            "series_id": sid,
                            "independent_variables": [{"name": "incident_energy", "unit": "eV", "values": cols[0]}],
                            "channels": [{"name": "absorption", "unit": "mu_normalized", "role": "primary_signal", "values": cols[1]}],
                        }
                    ]
                    draft["block_evidence"][f"series:{sid}"] = [
                        conf,
                        {"source_type": "document", "source_file": spectrum["relative_path"], "locator": f"sha256 {spectrum['sha256']}", "quote": f"{len(cols[0])} points"},
                    ]
                    used["series"] = spectrum["relative_path"]
                elif "series" not in used:
                    used["series"] = "not used: no data"
            else:
                used["series"] = "the normalised file is missing or its sha256 differs; not used"
        steps = []
        for step in r.get("steps") or ():
            token = PROCESSING_STEP_VOCABULARY.get(step.get("step"))
            if token and token not in steps:
                steps.append(token)
        if steps:
            fields["measurement.processing.steps"] = {"value": steps, "status": "verified", "evidence": [conf]}
            used["processing_steps"] = steps
        verdict = (r.get("qc") or {}).get("verdict")
        if d.get("qc_status"):
            # D2: a person STATED the QC status when approving; it wins over any mapping.
            draft["qc"] = {"status": d["qc_status"]}
            if d.get("qc_note"):
                draft["qc"]["evidence"] = d["qc_note"]
            draft["block_evidence"]["qc:status"] = [
                conf,
                {**_confirmation({**d, "value": d["qc_status"]}, "What is the measurement's QC status?"),
                 "processing_qc": d.get("qc_evidence")},
            ]
            used["qc"] = f"stated by a scientist: {d['qc_status']}"
        else:
            # I4: the QC status is NEVER mapped from the protocol's verdict (CLAUDE.md §5);
            # a person states it when approving.
            used["qc"] = (
                f"no QC status was stated (protocol verdict {verdict!r}); a person states it: "
                f"isaac bundle decide <bundle_dir> --target {pid} --decision approve --qc-status <value> --by \"<name>\""
            )
        e0 = (r.get("outputs") or {}).get("e0_eV")
        if isinstance(e0, (int, float)):
            sigma = (r.get("outputs") or {}).get("e0_uncertainty_eV")
            uncertainty = (
                {"sigma": sigma, "unit": "eV", "basis": "reported"}
                if isinstance(sigma, (int, float))
                else {"sigma": None, "basis": "not_reported"}
            )
            draft["descriptors_outputs"] = [
                {
                    "label": f"{r['protocol_id']}@{r['protocol_version']}",
                    "generated_utc": d.get("decided_utc"),
                    "generated_by": {"agent": r["protocol_id"], "version": str(r["protocol_version"])},
                    "descriptors": [
                        {
                            "name": "edge_position",
                            "kind": "absolute",
                            "source": "auto",
                            "value": e0,
                            "unit": "eV",
                            "uncertainty": uncertainty,
                            "definition": "E0 reported by the scientist-approved processing result.",
                            "evidence": [conf],
                        }
                    ],
                }
            ]
        report["processing"] = used
    elif blocked_by_protocol:
        app = not_applicable[-1]["applicability"]
        report["processing"] = {
            "used": None,
            "reason": f"{B.NO_PROTOCOL_COVERS} ({app.get('reason_code')}): {app.get('statement')}",
            "not_applicable": {"result_id": B.processing_id(not_applicable[-1]), "reason_code": app.get("reason_code"),
                               "what_the_data_states": app.get("what_the_data_states")},
        }
    else:
        report["processing"] = {"used": None, "reason": "no scientist-approved processing result for this group"}

    # what the record requires and nobody supplied: stays missing, listed
    control = fields.get("context.electrochemistry.control_mode", {}).get("value")
    required = list(B.required_record_paths(control_mode=control if isinstance(control, str) else None))
    required += list(B.PORTAL_REQUIRED_PATHS)
    if "context.reaction.name" in fields:
        required += list(B.REACTION_REQUIRED_PATHS)
    report["record_overrides"] = {}
    if "context.temperature_K" not in fields:
        # DEC-76: an unknown temperature is written the way the portal's schema says —
        # temperature_K null with temperature_basis not_reported. Never a default value.
        nobody = [m["value_id"] for m in bundle["missing_values"]
                  if m["target_field_path"] == "context.temperature_K" and m["run_id"] in member_ids]
        fields["context.temperature_basis"] = {
            "value": "not_reported",
            "status": "inferred",
            "evidence": [
                {
                    "source_type": "derivation",
                    "rule": (
                        "DEC-76: no source in this import and no scientist answer states a "
                        "temperature for this record, so temperature_K is null and "
                        "temperature_basis is not_reported. Nothing is defaulted."
                    ),
                    "missing_value_ids": nobody,
                }
            ],
        }
        report["record_overrides"]["context.temperature_K"] = None
        report["temperature"] = "not_reported (temperature_K null)"
    for req in required:
        if req == "context.temperature_K" and "context.temperature_K" in report["record_overrides"]:
            continue
        if req in STRUCTURED_REQUIRED:
            present = {
                "measurement.series": bool(draft.get("series")),
                "measurement.qc.status": bool((draft.get("qc") or {}).get("status")),
                "descriptors.outputs": bool(draft.get("descriptors_outputs")),
            }[req]
            if not present:
                report["missing_required"].append(
                    {"path": req, "from": "an approved processing result"}
                    | ({"blocked": B.NO_PROTOCOL_COVERS} if blocked_by_protocol and not approved else {})
                )
            continue
        field = REQUIRED_AS_FIELD.get(req, req)
        if not any(p == field or p.startswith(field + ".") for p in fields):
            fields[field] = {"value": None, "status": "missing", "evidence": []}
            report["missing_required"].append({"path": field, "from": "a scientist's answer"})
    return draft, report


#: The ONLY self-test marker (review minor): a fixed constant, never free text.
TEST_MARKER = "ISAAC SELF-TEST RECORD — NOT SCIENTIST-CONFIRMED — DO NOT UPLOAD"


def _apply_test_marker(draft: dict) -> list[str]:
    """Write :data:`TEST_MARKER` into the record's own NOTES fields (series notes, QC
    notes) — never as a field value with a confirmation it does not have."""
    placed = []
    for series in draft.get("series") or ():
        series["notes"] = TEST_MARKER
        placed.append("measurement.series[].notes")
    if draft.get("qc"):
        draft["qc"]["notes"] = TEST_MARKER
        placed.append("measurement.qc.notes")
    return placed


def contained_file(base: Path, relative: str) -> Path | None:
    """``base/relative`` if it is a regular file INSIDE ``base`` (no ``..``, no symlink
    escape), else ``None`` (review I2)."""
    if B._safe_relative(relative) is None:
        return None
    root = base.resolve()
    target = (base / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target if target.is_file() else None


def load_validated(bundle_dir: Path) -> dict:
    """Load AND validate the bundle (review I1). A bundle that fails v1 is refused with the
    validator's own findings; nothing downstream reads an unvalidated bundle."""
    from . import mutations as M

    bundle = M.load(bundle_dir)
    errors = B.validate_bundle(bundle)
    if errors:
        raise RecordsRefused("The bundle does not meet v1, so nothing was composed:\n  - " + "\n  - ".join(errors[:20]), code=1)
    return bundle


def fresh_compositions(bundle_dir: Path, bundle: Mapping, *, test_marker: bool = False) -> list[tuple[str, dict, dict]]:
    """``(group_id, draft, composition)`` for every scientist-confirmed group, composed NOW
    from the validated bundle — the only thing validate and export trust (review C1)."""
    out = []
    for g in bundle.get("record_groups") or ():
        if g["status"] != "scientist_confirmed":
            continue
        draft, comp = compose_group(bundle, g, bundle_dir)
        if test_marker:
            comp["test_marker"] = {"text": TEST_MARKER, "placed": _apply_test_marker(draft)}
        out.append((g["group_id"], draft, comp))
    return out


def _on_disk_differs(bundle_dir: Path, group_id: str, draft: Mapping, comp: Mapping) -> bool:
    path = bundle_dir / DRAFTS_DIR / f"{group_id}.draft.json"
    if not path.is_file():
        return False
    try:
        disk = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return json.dumps(disk, sort_keys=True) != json.dumps(draft, sort_keys=True)


def build_records(bundle_dir: Path, *, test_marker: bool = False) -> dict:
    from . import mutations as M

    bundle_dir = Path(bundle_dir)
    refusal = B.legacy_refusal(load_validated(bundle_dir))
    if refusal:  # a pre-1.2.0 bundle whose runs include the scientists' processed outputs
        raise RecordsRefused(refusal, code=2)

    def mark(b):  # the self-test state lives IN bundle.json, re-validated on write
        b["self_test"] = {"test_marker": bool(test_marker), "set_by": "isaac bundle build-records"}

    M.mutate(bundle_dir, mark)
    bundle = load_validated(bundle_dir)
    groups = [g for g in bundle.get("record_groups") or () if g["status"] == "scientist_confirmed"]
    out_dir = bundle_dir / DRAFTS_DIR
    out_dir.mkdir(exist_ok=True)
    from .cli import _atomic_write, _json_bytes

    index = []
    for g in groups:
        draft, report = compose_group(bundle, g, bundle_dir)
        if test_marker:
            report["test_marker"] = {"text": TEST_MARKER, "placed": _apply_test_marker(draft)}
        _atomic_write(out_dir / f"{g['group_id']}.draft.json", _json_bytes(draft))
        _atomic_write(out_dir / f"{g['group_id']}.composition.json", _json_bytes(report))
        index.append(
            {
                "group_id": g["group_id"],
                "draft": f"{DRAFTS_DIR}/{g['group_id']}.draft.json",
                "filled": len(report["filled"]),
                "missing_required": [m["path"] for m in report["missing_required"]],
                "disagreements": len(report["disagreements"]),
                "complete": not report["missing_required"] and not report["disagreements"],
            }
            | ({"blocked": report["processing"]["reason"]} if (report.get("processing") or {}).get("not_applicable") else {})
        )
    skipped = [
        {"group_id": g["group_id"], "status": g["status"], "reason": "only a scientist-confirmed record group becomes a draft"}
        for g in bundle.get("record_groups") or ()
        if g["status"] != "scientist_confirmed"
    ]
    result = {"drafts": index, "skipped_groups": skipped, "test_marker": bool(test_marker),
              "statement": "Drafts, not records. A draft with missing required values is incomplete and is never exported."}
    _atomic_write(out_dir / "index.json", _json_bytes(result))
    return result


# --- validation ----------------------------------------------------------------------------------


def _schema_error_keys(errors: Sequence[tuple[str, str]]) -> set[tuple[str, str]]:
    import re

    keys = set()
    for path, message in errors:
        m = re.match(r"'([^']+)' is a required property", message)
        keys.add((path.replace("/", ".").strip(".$") or "$", m.group(1) if m else message[:80]))
    return keys


def _portal_demands_undeclared(portal_check: Mapping | None) -> list[dict]:
    """Portal errors naming a field the VENDORED schema does not declare under a parent
    that forbids unknown keys — a requirement no v1.05 record can ever satisfy."""
    out = []
    result = (portal_check or {}).get("result") or {}
    for err in result.get("errors") or ():
        path = str(err.get("path") or "").replace("/", ".").strip(".")
        if not path or "." not in path:
            continue
        if B._schema_node(path) is not None:
            continue
        parent = B._schema_node(path.rsplit(".", 1)[0])
        if parent is not None and parent.get("additionalProperties") is False:
            out.append(
                {
                    "path": path,
                    "portal_code": err.get("code"),
                    "explanation": (
                        f"The upstream portal requires {path}; vendored v1.05 does not declare it "
                        "and forbids unknown keys there, so no record exported through the "
                        "vendored schema can satisfy both."
                    ),
                }
            )
    return out


def schema_drift(record: Mapping, upstream: Mapping | None, portal_check: Mapping | None = None) -> dict:
    """Vendored-vs-upstream disagreement about THIS record, both directions, plus the
    one known shape of drift: an unknown temperature (upstream: ``temperature_K: null`` +
    ``temperature_basis: not_reported``; vendored: a number is required, no basis field)."""
    from jsonschema import Draft202012Validator
    from isaac_records.official import validate_official

    if upstream is None:
        demanded = _portal_demands_undeclared(portal_check)
        return {
            "status": "upstream_schema_unavailable",
            "portal_requires_undeclared_fields": demanded,
            "blocked_by_schema_drift": bool(demanded),
        }
    vendored_errors = [(e.path, e.message) for e in validate_official(dict(record), _repo_root()).errors]
    upstream_errors = [
        (".".join(str(p) for p in err.absolute_path), err.message)
        for err in Draft202012Validator(upstream).iter_errors(record)
    ]
    v, u = _schema_error_keys(vendored_errors), _schema_error_keys(upstream_errors)
    out = {
        "status": "compared",
        "vendored_only": sorted(map(list, v - u)),
        "upstream_only": sorted(map(list, u - v)),
    }
    context = record.get("context") if isinstance(record.get("context"), Mapping) else None
    if context is not None and context.get("temperature_K") is None:
        probe = json.loads(json.dumps(record))
        probe["context"]["temperature_K"] = None
        probe["context"]["temperature_basis"] = "not_reported"
        up_ok = not any(
            "temperature" in ".".join(map(str, e.absolute_path)) + e.message
            for e in Draft202012Validator(upstream).iter_errors(probe)
        )
        v_ok = not any("temperature" in e.path + e.message for e in validate_official(probe, _repo_root()).errors)
        if up_ok and not v_ok:
            out["temperature"] = (
                "The temperature is unknown. Upstream accepts temperature_K: null with "
                "temperature_basis: not_reported; vendored v1.05 requires a number and has no "
                "temperature_basis. Nothing is defaulted, so this record is blocked by schema "
                "drift unless a scientist states the temperature."
            )
    demanded = _portal_demands_undeclared(portal_check)
    if demanded:
        out["portal_requires_undeclared_fields"] = demanded
    out["blocked_by_schema_drift"] = bool(
        out.get("vendored_only") or out.get("upstream_only") or out.get("temperature") or demanded
    )
    return out


def compose_record(draft: Mapping, composition: Mapping | None, *, record_id: str, now: str) -> dict:
    """The official-shape record for the PORTAL'S schema (DEC-76).

    Reuses the truth plane's own functions — ``isaac_records.export.transform`` and
    ``isaac_records.export.set_path`` — and does not edit them. ``export_draft`` is NOT
    used: its ``transform`` drops every null field, so it cannot write the upstream
    schema's ``temperature_K: null`` (with ``temperature_basis: not_reported``); that one
    shape is applied here from the composition's ``record_overrides`` after ``transform``.
    """
    from isaac_records.export import set_path, transform

    record = transform(dict(draft), record_id=record_id, now=now)
    for path, value in ((composition or {}).get("record_overrides") or {}).items():
        # ONLY the derivation this module owns (review C1): an unknown temperature is null.
        if path not in RECORD_OVERRIDE_ALLOWLIST or value != RECORD_OVERRIDE_ALLOWLIST[path]:
            raise RecordsRefused(f"record override {path!r}={value!r} is not a derivation this composer owns", code=1)
        set_path(record, path, value)
    return record


#: ``path -> the one value`` a composition may override after ``transform``.
RECORD_OVERRIDE_ALLOWLIST = {"context.temperature_K": None}


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def schemas_used(where: Mapping) -> dict:
    """Which schema each verdict used — sha and source, never a local path."""
    target = None
    if where.get("available"):
        target = {
            "source": "ISAAC-DOE/isaac-ai-ready-record (pinned upstream clone)",
            "commit": where.get("commit"),
            "pinned_commit": where.get("pinned_commit"),
            "schema_sha256": _sha256(Path(where["dir"]) / "schema" / "isaac_record_v1.json"),
            "gates": ["official schema", "exactness", "portal validate_record_full"],
        }
    return {
        "local_export_target": target,
        "website_schema": {
            "source": "vendored schema/isaac_record_v1.json (v1.05, July)",
            "schema_sha256": _sha256(_repo_root() / "schema" / "isaac_record_v1.json"),
            "gates": [],
            "statement": "Reported for information only. It does not gate the local export, and nothing here is claimed valid for the website.",
        },
    }


def validate_draft_file(draft: Mapping, *, run_portal, composition: Mapping | None = None) -> dict:
    """Every gate, verbatim, and which schema each used. ``verdict`` is the honest word.

    Gating (DEC-76): ISAAC's own ``validate_official`` and ``check_exactness`` with
    ``root`` = the pinned upstream clone, plus the offline portal check. The vendored
    v1.05 result is computed and reported as ``website_schema`` and gates nothing."""
    from isaac_records.draft_validator import validate_draft
    from isaac_records.exactness import check_exactness
    from isaac_records.official import validate_official

    from . import portal as P

    where = P.locate()
    dr = validate_draft(draft)
    missing = sorted(p for p, env in (draft.get("fields") or {}).items() if isinstance(env, dict) and env.get("status") == "missing")
    record = compose_record(draft, composition, record_id="0" * 26, now="1970-01-01T00:00:00Z")
    website = validate_official(record, _repo_root())
    target_official = target_exact = None
    if where.get("available"):
        upstream_root = Path(where["dir"])
        target_official = validate_official(record, upstream_root)
        target_exact = check_exactness(record, upstream_root)
    portal_check = run_portal(record)
    drift = schema_drift(record, P.upstream_schema(where), portal_check)
    pv = portal_check.get("verdict") or P.verdict_of(portal_check)
    proc = (composition or {}).get("processing") or {}
    blocked = proc.get("reason") if proc.get("not_applicable") else None
    if missing or not dr.ok or blocked:
        verdict = "incomplete"
    elif target_official is None:
        verdict = P.VERDICT_UNAVAILABLE
    elif not (target_official.ok and target_exact.ok):
        verdict = "invalid_official"
    elif pv != "publish":
        verdict = pv if pv in (P.VERDICT_UNAVAILABLE, P.VERDICT_DEGRADED) else f"portal_{pv}"
    else:
        verdict = "exportable"
    result = (portal_check.get("result") or {}) if portal_check.get("status") == "ran" else {}
    used = schemas_used(where)
    commit = (used["local_export_target"] or {}).get("commit") or "unavailable"
    summary = [
        f"Draft checks: {'pass' if dr.ok else 'FAIL'} ({len(dr.errors)} error(s), {len(dr.warnings)} warning(s)).",
        f"Missing required values: {', '.join(missing) if missing else 'none'}.",
        *([f"Processing: {blocked}. The record's series, QC status and E0 cannot be supplied, so it stays incomplete."] if blocked else []),
        (
            f"Portal-target schema (upstream {commit[:12]}): {'pass' if target_official.ok else 'FAIL'} "
            f"({len(target_official.errors)} error(s)); exactness: {'pass' if target_exact.ok else 'FAIL'}."
            if target_official is not None
            else "Portal-target schema: not available — install the pinned validator. This is not a pass."
        ),
        (
            f"Upstream portal check: {portal_check.get('outcome')} "
            f"({len(result.get('errors') or [])} error(s), {len(result.get('warnings') or [])} warning(s))."
            if portal_check.get("status") == "ran"
            else f"Upstream portal check: not run — {portal_check.get('reason')}. This is not a pass."
        ),
        f"Website schema (vendored v1.05, July), for information only: {'pass' if website.ok else 'FAIL'} ({len(website.errors)} error(s)). Not claimed valid for the website.",
        "This is NOT an official record until `isaac bundle export` writes one, and nothing has been uploaded.",
    ]
    return {
        "verdict": verdict,
        "plain_summary": summary,
        "schemas_used": used,
        "draft_validation": {"ok": dr.ok, "errors": [list(e) for e in dr.errors], "warnings": [list(w) for w in dr.warnings]},
        "missing_required": missing,
        "processing_blocked": blocked,
        "composition": {
            "reused": ["isaac_records.export.transform", "isaac_records.export.set_path", "isaac_records.export.build_sidecar"],
            "not_used": "isaac_records.export.export_draft (its transform drops null fields, so it cannot write temperature_K: null)",
            "record_overrides": dict((composition or {}).get("record_overrides") or {}),
        },
        "official_validation": (
            {"schema": "local_export_target", "ok": target_official.ok,
             "errors": [{"path": e.path, "message": e.message} for e in target_official.errors]}
            if target_official is not None else {"schema": "local_export_target", "ok": None, "errors": [], "status": "unavailable"}
        ),
        "exactness": (
            {"schema": "local_export_target", "ok": target_exact.ok, "errors": [str(e) for e in target_exact.errors]}
            if target_exact is not None else {"schema": "local_export_target", "ok": None, "errors": [], "status": "unavailable"}
        ),
        "website_schema": {
            "schema": "website_schema",
            "ok": website.ok,
            "errors": [{"path": e.path, "message": e.message} for e in website.errors],
            "gates_export": False,
        },
        "portal_check": portal_check,
        "schema_drift": drift,
    }


def validate_records(bundle_dir: Path, *, run_portal=None) -> dict:
    """Validate a FRESH composition of every confirmed group (review C1/I1). An on-disk
    draft that differs from it is flagged and never used."""
    from . import portal as P
    from .cli import _atomic_write, _json_bytes

    run_portal = run_portal or P.run_portal_check
    bundle_dir = Path(bundle_dir)
    bundle = load_validated(bundle_dir)
    marked = _was_marked(bundle)
    out_dir = bundle_dir / VALIDATION_DIR
    out_dir.mkdir(exist_ok=True)
    verdicts, stale = {}, []
    for group_id, draft, composition in fresh_compositions(bundle_dir, bundle, test_marker=marked):
        if _on_disk_differs(bundle_dir, group_id, draft, composition):
            stale.append(group_id)
        report = validate_draft_file(draft, run_portal=run_portal, composition=composition)
        report["group_id"] = group_id
        report["composed_from"] = "the validated bundle, now (an on-disk draft is never trusted)"
        report["on_disk_draft_differs"] = group_id in stale
        _atomic_write(out_dir / f"{group_id}.json", _json_bytes(report))
        verdicts[group_id] = report["verdict"]
    return {"verdicts": verdicts, "on_disk_drafts_ignored_because_they_differ": stale}


def _was_marked(bundle: Mapping) -> bool:
    """True when ``build-records --test-marker`` set the self-test state in bundle.json."""
    return bool((bundle.get("self_test") or {}).get("test_marker"))


# --- export ----------------------------------------------------------------------------------------


def export_records(bundle_dir: Path, out: Path, *, run_portal=None) -> dict:
    """Write ONLY records that pass the portal-target official validation AND whose portal
    outcome is ``publish`` (DEC-76). Every gate is re-run here; a stale validation file is
    never trusted. The record is composed with ``export.transform`` and its sidecar with
    ``export.build_sidecar`` — the truth plane's own functions, unedited."""
    from isaac_records.export import build_sidecar
    from isaac_records.ids import new_record_id
    from isaac_records.official import validate_official

    from . import portal as P
    from .cli import _atomic_write

    run_portal = run_portal or P.run_portal_check
    bundle_dir, out = Path(bundle_dir), Path(out)
    bundle = load_validated(bundle_dir)
    exported, refused = [], []
    fresh = fresh_compositions(bundle_dir, bundle, test_marker=_was_marked(bundle))
    confirmed = {gid for gid, _, _ in fresh}
    stale = [gid for gid, d, c in fresh if _on_disk_differs(bundle_dir, gid, d, c)]
    orphans = sorted(
        p.name[: -len(".draft.json")] for p in (bundle_dir / DRAFTS_DIR).glob("*.draft.json")
        if p.name[: -len(".draft.json")] not in confirmed
    ) if (bundle_dir / DRAFTS_DIR).is_dir() else []
    for group_id, draft, composition in fresh:
        report = validate_draft_file(draft, run_portal=run_portal, composition=composition)
        if report["verdict"] != "exportable":
            refused.append({"group_id": group_id, "verdict": report["verdict"], "summary": report["plain_summary"]})
            continue
        where = P.locate()
        rid = new_record_id()
        from .mutations import now_utc

        record = compose_record(draft, composition, record_id=rid, now=now_utc())
        if not validate_official(record, Path(where["dir"])).ok:  # the minted record, re-checked
            refused.append({"group_id": group_id, "verdict": "invalid_official", "summary": ["the minted record failed re-validation"]})
            continue
        sidecar = build_sidecar(dict(draft), record)
        sidecar["schemas_used"] = report["schemas_used"]
        out.mkdir(parents=True, exist_ok=True)
        record_path, sidecar_path = out / f"{rid}.json", out / f"{rid}.evidence.json"
        _atomic_write(record_path, (json.dumps(record, indent=2) + "\n").encode("utf-8"))
        _atomic_write(sidecar_path, (json.dumps(sidecar, indent=2) + "\n").encode("utf-8"))
        artifacts = []
        for r in bundle.get("processing_results") or ():
            if r["group_id"] == group_id and r["state"] == B.STATE_SCIENTIST_CONFIRMED:
                for f in (r.get("outputs") or {}).get("files") or ():
                    # I2: contained in the bundle, sha256 verified, contained in --out.
                    src = contained_file(bundle_dir, f["relative_path"])
                    if src is None or hashlib.sha256(src.read_bytes()).hexdigest() != f.get("sha256"):
                        artifacts.append({"relative_path": f.get("relative_path"), "refused": "outside the bundle, missing, or sha256 mismatch"})
                        continue
                    base = (out / f"{rid}.artifacts").resolve()
                    dest = (base / f["relative_path"]).resolve()
                    try:
                        dest.relative_to(base)
                    except ValueError:
                        artifacts.append({"relative_path": f.get("relative_path"), "refused": "would land outside --out"})
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dest)
                    artifacts.append(f["relative_path"])
        exported.append({"group_id": group_id, "record_id": rid, "record": record_path.name, "sidecar": sidecar_path.name,
                         "artifacts": artifacts, "schemas_used": report["schemas_used"],
                         "statement": "Valid for the portal's pinned schema; NOT claimed valid for the website."})
    result = {
        "exported": exported,
        "refused": refused,
        "on_disk_drafts_ignored_because_they_differ": stale,
        "on_disk_drafts_ignored_with_no_confirmed_group": orphans,
    }
    if not exported:
        result["statement"] = "Nothing was exported."
    return result


# --- upload (dry run only) -------------------------------------------------------------------------


def upload_plan(records_dir: Path, portal_url: str | None) -> list[dict]:
    """Exactly what an upload WOULD send. Reads record files; opens no socket and never
    reads the token (the Authorization header names where it would come from)."""
    base = (portal_url or "<portal-url>").rstrip("/")
    plan = []
    for path in sorted(Path(records_dir).glob("*.json")):
        if path.name.endswith(".evidence.json"):
            continue
        body = path.read_bytes()
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer <from $ISAAC_PORTAL_TOKEN, not read>",
        }
        meta = {"body_bytes": len(body), "body_sha256": hashlib.sha256(body).hexdigest()}
        plan.append(
            {
                "record": path.name,
                "requests": [
                    {"method": "POST", "url": base + PORTAL_VALIDATE, "headers": headers, **meta},
                    {"method": "POST", "url": base + PORTAL_RECORDS, "headers": headers, **meta,
                     "only_if": "the validate response is valid with outcome publish"},
                ],
            }
        )
    return plan
