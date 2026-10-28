"""The ISAAC XAS processing protocol ``isaac.xas.v0`` — every parameter, in one place.

**DRAFT — not reviewed by a beamline scientist.** Status ``draft_unreviewed``. A
colleague's (Oscar's) protocol supersedes this one on arrival. Every default below is a
starting point chosen so a scientist can SEE what was done and change it; none is a
scientific judgement this build is entitled to make. ``docs/xas-processing-protocol-v0.md``
is the human-readable version; :data:`PARAM_DOCS` says, per parameter, what it does and
whether a scientist must approve it before results may be relied on.

Stdlib only (imported without numpy/larch).
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

PROTOCOL_ID = "isaac.xas.v0"
PROTOCOL_VERSION = "0.1.0"
PROTOCOL_STATUS = "draft_unreviewed"
PROTOCOL_NOTICE = (
    "DRAFT — not reviewed by a beamline scientist; Oscar's protocol supersedes on arrival. "
    "Results are review material, never an official value."
)

DEFAULT_PARAMS: dict[str, Any] = {
    "channels": {
        # Energy column names, first present wins. A column found only by the value-shape
        # fallback is flagged.
        # Measured/achieved (encoder) energy before the requested set-point. Measured
        # 2026-10-28 on a real BL15-2 beamtime: the scientist's Athena energy arrays equal
        # the `absev` column, not `energy` (1.7-3.4 eV apart). XDAC: Achieved Energy.
        "energy_candidates": ["Achieved Energy", "absev", "energy", "Energy", "mono", "Requested Energy", "energy_eV", "E"],
        "i0_candidates": ["I0", "i0", "IO"],
        # Fluorescence signals in priority order. "sum:<prefix>" sums every column whose
        # name starts with <prefix> followed by digits/underscores (e.g. SCA1_1..SCA1_7).
        "fluorescence_candidates": [
            "vortDT", "vortDT2", "vortDT3", "vortDT4",
            "sum:DTC_FF", "sum:FF", "sum:SCA1_", "Lytle", "PIPS", "If", "fluor",
        ],
        "transmission_after_sample": ["I1", "It", "IT"],
        "reference_after_reference": ["I2", "Iref", "IR"],
        "energy_value_range_eV": [1000.0, 100000.0],
        "use_bl15_signal_selection": True,
        # Columns of input count rates (XDAC ICR1_1..7). Their presence is FLAGGED; no
        # dead-time correction is applied until a rule is approved.
        "dead_time_rate_prefix": "ICR1_",
    },
    "calibration": {
        "use_in_scan_reference_channel": True,
        "reference_min_edge_snr": 10.0,
        "apply_shift_when_confirmed": True,
        "max_plausible_shift_eV": 25.0,
        "align_scans_by_reference": False,
        # A params-file value PROPOSES the reference; it is never a scientist decision. The
        # shift is applied only under a processing-approval decision (calibration_approvals).
        "proposed_reference": None,  # {"element": "Ti", "edge": "K"}
    },
    "deglitch": {
        "point_z_threshold": 6.0,
        "robust_scale": "1.4826*MAD",
        "min_scans_for_cross_scan": 3,
        "scan_rms_ratio_threshold": 3.0,
        "scan_rms_floor": 0.005,
        "exclude_flagged": False,
        "max_listed_points": 200,
    },
    "merge": {
        "grid": "first_scan_points_within_common_overlap",
        "interpolation": "linear",
        "duplicate_energy_tolerance_eV": 1e-6,
        "min_points": 20,
    },
    "normalize": {
        "e0": None,
        "pre1": None,
        "pre2": -30.0,
        # norm1 None -> min(norm1_rule_cap_eV, norm1_rule_fraction * (Emax - E0)). Measured
        # 2026-10-28 over 107 scientist Athena groups in the real archive: nor1 median
        # 110 eV (43..150), pre2 mode -30, nnorm 2 (82) or 3 (25), flatten on (107/107).
        # larch's own default (norm1 ~25 eV on these XANES ranges) put the post-edge fit on
        # the white line and was the dominant ISAAC-vs-Athena difference.
        "norm1": None,
        "norm1_rule_cap_eV": 100.0,
        "norm1_rule_fraction": 0.4,
        "norm2": None,
        "nnorm": 2,
        "make_flat": True,
    },
    "qc": {
        "fail_min_points": 20,
        "warn_min_scans": 2,
        "warn_pre_edge_noise": 0.02,
        "warn_scan_spread": 0.02,
        "warn_energy_shift_eV": 2.0,
        "warn_reference_e0_spread_eV": 0.5,
        "saturation_run_points": 3,
        "fail_i0_nonpositive_fraction": 0.05,
    },
    "athena": {
        "enabled": True,
        "agree_e0_delta_eV": 1.0,
        "agree_rms_norm": 0.05,
        "min_overlap_points": 20,
        "min_overlap_eV": 30.0,
        "edge_step_ratio_range": [0.8, 1.25],
    },
}

#: path -> (meaning, scientist_must_approve)
PARAM_DOCS: Mapping[str, tuple[str, bool]] = {
    "channels.energy_candidates": ("Energy column names in priority order (achieved/encoder energy first: absev, Achieved Energy).", True),
    "channels.dead_time_rate_prefix": ("Input-count-rate column family; present -> flag dead_time_correction_not_applied (no correction rule approved).", True),
    "channels.i0_candidates": ("Incident-intensity column names. None found: signal used un-normalised and flagged i0_missing.", True),
    "channels.fluorescence_candidates": ("Fluorescence/HERFD signal columns in priority order (sum:<prefix> sums a detector-element family).", True),
    "channels.transmission_after_sample": ("Transmission detector after the sample: mu = ln(I0/I1).", True),
    "channels.reference_after_reference": ("Detector after the reference foil: mu_ref = ln(I1/I2).", True),
    "channels.energy_value_range_eV": ("Value-shape fallback for an unnamed energy column: monotonic, within this range.", True),
    "channels.use_bl15_signal_selection": ("Use the BL15-2 HERFD selector's (bl15/signals.py) proposed channel when it proposes one.", True),
    "calibration.use_in_scan_reference_channel": ("Compute E0 of an in-scan reference channel (I1/I2) when it shows an edge.", True),
    "calibration.reference_min_edge_snr": ("Edge step / pre-edge noise a reference channel needs before its E0 is used.", True),
    "calibration.apply_shift_when_confirmed": ("Apply (tabulated - measured reference E0) only under a scientist's processing-approval decision for the group.", True),
    "calibration.max_plausible_shift_eV": ("A larger computed shift is not applied and is flagged.", True),
    "calibration.align_scans_by_reference": ("Align scans to each other by their reference E0 differences (off by default).", True),
    "calibration.proposed_reference": ("Reference {element, edge} PROPOSED by a params file (label params_file_value). Never applies a shift by itself.", True),
    "deglitch.point_z_threshold": ("Robust z-score above which a point is flagged as a glitch.", True),
    "deglitch.min_scans_for_cross_scan": ("With at least this many scans, points are judged against the group median spectrum; otherwise against their two neighbours.", True),
    "deglitch.scan_rms_ratio_threshold": ("A scan whose RMS deviation from the group median exceeds this multiple of the median scan's is flagged.", True),
    "deglitch.scan_rms_floor": ("…and exceeds this fraction of the median spectrum's span (so near-identical scans are not flagged).", True),
    "deglitch.exclude_flagged": ("Exclude flagged points/scans from the merge. FALSE by default: flagged data is kept and reported.", True),
    "merge.grid": ("Common grid: the first scan's energy points inside the overlap of all scans.", True),
    "merge.min_points": ("Fewer common-grid points: no merge.", False),
    "normalize.e0": ("E0 for normalisation; None = larch find_e0 (maximum of the first derivative).", True),
    "normalize.pre1": ("Pre-edge fit start relative to E0 (eV); None = larch default.", True),
    "normalize.pre2": ("Pre-edge fit end relative to E0 (eV); default -30 (scientists' mode).", True),
    "normalize.norm1": ("Post-edge fit start relative to E0 (eV); None = min(norm1_rule_cap_eV, norm1_rule_fraction*(Emax-E0)).", True),
    "normalize.norm1_rule_cap_eV": ("Cap of the default norm1 rule (scientists' median nor1 = 110 eV in the archive).", True),
    "normalize.norm1_rule_fraction": ("Fraction of the post-E0 range for the default norm1 rule on short scans.", True),
    "normalize.norm2": ("Post-edge fit end relative to E0 (eV); None = larch default.", True),
    "normalize.nnorm": ("Post-edge polynomial degree; default 2 (scientists: 2 in 82/107, 3 in 25/107).", True),
    "qc.fail_min_points": ("Fewer merged points: fail.", True),
    "qc.warn_min_scans": ("Fewer scans: warn (no scan-to-scan spread).", True),
    "qc.warn_pre_edge_noise": ("Pre-edge residual std / edge step above this: warn.", True),
    "qc.warn_scan_spread": ("Median standard error / edge step above this: warn.", True),
    "qc.warn_energy_shift_eV": ("|calibration shift| above this: warn.", True),
    "qc.warn_reference_e0_spread_eV": ("Reference E0 spread across scans above this: warn (energy drift).", True),
    "qc.saturation_run_points": ("This many consecutive identical maximum signal values: saturation suspected (warn).", True),
    "qc.fail_i0_nonpositive_fraction": ("Fraction of I0 <= 0 points above this: fail.", True),
    "athena.agree_e0_delta_eV": ("|E0(ISAAC) - E0(Athena)| at most this for 'agree'.", True),
    "athena.agree_rms_norm": ("RMS of normalised-mu difference on the overlap at most this for 'agree'.", True),
    "athena.min_overlap_points": ("Fewer overlap points: not_comparable.", False),
    "athena.min_overlap_eV": ("Narrower overlap: not_comparable.", False),
    "athena.edge_step_ratio_range": ("Edge-step ratio outside this range is flagged (absolute mu scaling is not part of the verdict).", True),
}


#: Open questions for the scientists (Oscar / Angel), machine-readable so the skill can ask
#: them. ``affects`` names the protocol parameters or grouping keys an answer would change.
PROTOCOL_QUESTIONS: list[dict] = [
    {
        "question_id": "pq-001",
        "topic": "energy_column",
        "ask": "angel_or_oscar",
        "text": "At SSRL BL15-2, is `absev` (encoder/absolute energy) the energy axis to use, rather than `energy`? Measured: the scientists' Athena energy arrays equal `absev`, 1.7-3.4 eV from `energy`.",
        "affects": ["channels.energy_candidates"],
        "current_default": "absev before energy",
        "status": "open",
    },
    {
        "question_id": "pq-002",
        "topic": "grouping.new_spot",
        "ask": "angel_or_oscar",
        "text": "Is a measurement on a NEW SPOT of the same sample, at the same condition, a repeat (one record) or a different result?",
        "affects": ["grouping.UNKNOWN_KEYS.new_spot"],
        "current_default": "unknown: separate groups plus a merge candidate",
        "status": "open",
    },
    {
        "question_id": "pq-003",
        "topic": "grouping.step_number",
        "ask": "angel_or_oscar",
        "text": "Is a numbered step (`stepNN`) a repeat at the same condition, or a different point in a protocol?",
        "affects": ["grouping.UNKNOWN_KEYS.step_number"],
        "current_default": "unknown: separate groups plus a merge candidate",
        "status": "open",
    },
    {
        "question_id": "pq-004",
        "topic": "calibration.foil_shift_to_samples",
        "ask": "oscar",
        "text": "Should the energy shift measured on a reference-foil group be applied to the beamtime's sample groups (and under which conditions)?",
        "affects": ["calibration.proposed_reference", "calibration.apply_shift_when_confirmed"],
        "current_default": "never propagated automatically",
        "status": "open",
    },
    {
        "question_id": "pq-005",
        "topic": "athena.e0_frame",
        "ask": "oscar",
        "text": "Is the E0 stored in an Athena project in the energy-SHIFTED frame (after bkg_eshift) or the stored-energy frame? This build follows larch's read_athena reproduction (stored frame) and compares in the shifted frame.",
        "affects": ["athena comparison: e0_delta_eV"],
        "current_default": "larch read_athena convention",
        "status": "open",
    },
    {
        "question_id": "pq-006",
        "topic": "channels.dead_time",
        "ask": "oscar",
        "text": "For SSRL XDAC data, should SCA fluorescence channels be dead-time corrected with the ICR columns, and by which rule?",
        "affects": ["channels.dead_time_rate_prefix"],
        "current_default": "no correction; flag dead_time_correction_not_applied",
        "status": "open",
    },
    {
        "question_id": "pq-007",
        "topic": "athena.result_of_record",
        "ask": "scientist_of_the_beamtime",
        "text": "When several Athena projects hold different versions of one measurement (re-normalised, glitch-removed, smoothed), which is the result of record?",
        "affects": ["processing_results[].athena_versions"],
        "current_default": "none selected; each listed and compared",
        "status": "open",
    },
]


def resolve_params(overrides: Mapping | None = None) -> dict:
    """DEFAULT_PARAMS with ``overrides`` (``{section: {key: value}}``) applied. Unknown keys refused."""
    params = copy.deepcopy(DEFAULT_PARAMS)
    overrides = copy.deepcopy(dict(overrides or {}))
    cal = overrides.get("calibration")
    if isinstance(cal, Mapping) and "confirmed_reference" in cal:
        # v0 name. A params file cannot confirm anything: it is read as a PROPOSAL.
        cal = dict(cal)
        cal.setdefault("proposed_reference", cal.pop("confirmed_reference"))
        overrides["calibration"] = cal
    for section, values in overrides.items():
        if section not in params or not isinstance(values, Mapping):
            raise ValueError(f"unknown protocol section {section!r}")
        for key, value in values.items():
            if key not in params[section]:
                raise ValueError(f"unknown protocol parameter {section}.{key}")
            params[section][key] = value
    return params


def changed_from_default(params: Mapping) -> list[str]:
    return sorted(
        f"{s}.{k}" for s, vals in params.items() for k, v in vals.items() if DEFAULT_PARAMS.get(s, {}).get(k) != v
    )


def needs_approval() -> list[str]:
    return sorted(k for k, (_, must) in PARAM_DOCS.items() if must)
