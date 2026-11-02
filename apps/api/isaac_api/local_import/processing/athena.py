"""Athena-first: read the scientist's Athena projects, match their groups to record groups,
and compare the scientist's normalisation with the ISAAC protocol's.

The scientist's Athena output is PREFERRED for the record; a disagreement is a review
item, never an override in either direction.

MATCHING RULE (``isaac.athena.match_by_name.v1``)
===============================================

A name is normalised: casefold; one trailing ``.txt``/``.dat``/``.xmu``/``.nor``/``.csv``
removed; runs of whitespace, ``-`` and ``.`` become ``_``. An Athena group's names are its
``label`` and its file name's basename. A record group's names are its members' run stems
(for an unread acquisition, its stem). An Athena group MATCHES a record group when one of
its names EQUALS a stem (exact), or is the stem followed by ``_`` and a scan-selection
suffix — digits and digit ranges (``5_6``, ``001``), or ``merge``/``mrg``/``avg``/
``average``/``mean``/``sum`` (+ anything) — (suffix match), or is the stem followed by the
SSRL XDC scan-file suffix ``_A.NNN`` (normalised ``_a_NNN``; any case) — the name of one of
that run's own scan files (``xdc_scan_file`` match, read as scan NNN by :func:`scan_selection`).

v1 = v0 + the XDC scan-file suffix, nothing else. Measured on two real SSRL BL4-3 beamtimes: the
scientists named their Athena groups after the scan file each holds (``03_<sample>_016_A.001``;
the EXAFS Data Collector writes a run's scans as ``<stem>_A.NNN``), and under v0 161 + 29 Athena
groups matched no record group. Only that exact shape is accepted: another letter (``_B.001``), no
separator (``_A001``) or anything after the number is not, and there is no prefix or substring
matching. A name that fits two record groups (``x`` + ``_A.001`` and ``x_A`` + ``_001``) is
ambiguous like any other and matches neither.

THE SCIENTIST'S OWN MERGE (``isaac.athena.scientist_merge_label.v0``, :data:`SCIENTIST_MERGE_RULE_ID`). An Athena name
that is a merge word (+ digits) followed by ``_`` and a name (``merge4_<base>``, ``merge_<run name>``) matches a
record group when that name EQUALS one of the group's stems (that run's merge) or the group's shared BASE name
(:func:`base_names`: the stems with the whole-number token in which they differ removed, and an XDAC ``_a`` after it, or
a lone stem without its trailing run counter ``_016`` / ``_016_a``): the merge of every run of the group. Measured on a
real BL4-3 beamtime: the scientists' merges named before a two-run group's base name matched nothing, and ISAAC averaged
the per-scan groups beside them instead, saying the scientist made no merge. Such a merge is a merged candidate like any
other (below), so it is preferred over the per-scan groups of the same project.

A PER-SCAN SET BESIDE THE MERGE (r3-d). The per-scan groups beside the preferred merge are never dropped silently: each
set they form (:func:`_per_scan_set`, one per project) is kept on the matched entry (``_sets_aside``), and the result says
it was set aside. When such a set covers every scan of the group, the merge is compared with the set's mean
(:func:`compare`, the same tolerances); a merge that differs from it (stale, or of only some scans) is no longer preferred,
and the scientist is asked which is the result of record (``run.process_group``).

* an Athena group matching several record groups: an exact match wins over suffix matches;
  still several -> ambiguous, matched to none, and noted;
* several Athena groups for one record group: identical data (same energy+mu bytes) count
  once; otherwise a single merged one (Athena ``is_merge`` or a merge-word suffix) wins;
  otherwise ambiguous -> no match, and the candidates are noted.

The Athena normalisation is reproduced the way larch's own ``read_athena(do_preedge=True)``
does: ``pre_edge`` on the stored energy with the project's ``e0``, ``pre1``, ``pre2``,
``nor1``, ``nor2``, ``nnorm`` and ``flatten``. Comparisons are made in the scientist's
energy frame: stored energy + ``bkg_eshift``, E0 + ``bkg_eshift``.

ALREADY-NORMALISED DATA (``isaac.athena.already_normalized.v0``). A group Athena flags ``is_nor``
was imported as normalised data (e.g. a Demeter ``.nor`` export read back in): its stored spectrum
IS the scientist's normalised curve, pre-edge 0 and post-edge 1, so its edge step is 1 by
definition. It is used AS STORED (``norm`` = ``flat`` = stored mu), never normalised again: larch
does re-run the pre-edge fit on it, and on a real BL6-2c beamtime that fit (a post-edge range of
zero width, ``nor1 == nor2``, which larch widens to 2 eV, with a cubic) gave edge steps of 4683 to
190115 and a flattened curve sloping to -1.3, which ISAAC then compared and plotted. The project's
``pre1``/``nor1``... are recorded but were not applied to it by Athena, so no comparison re-runs them.

IMPLAUSIBLE EDGE STEP (:func:`core.edge_step_implausible`). Any other group whose reproduced edge
step is more than :data:`core.EDGE_STEP_MAX_RANGE_RATIO` times its own stored range is NOT
COMPARED (verdict ``not_comparable``, flag :data:`EDGE_STEP_IMPLAUSIBLE_FLAG`, a plain ``reason``),
not overlaid on the plot, not preferred, and its QC fails ``edge_step_implausible``.

TODO (bundle 1.2.0 ``processed_outputs[]``, NOT BUILT): the bundle now also carries the
scientists' exported Athena/Demeter XDI files (``.nor``, ``.xmu`` ...) as reference results,
each with at most one PROPOSED link to a run (``bundle.LINK_RULE_ID``) and, through it, a
record group. They are not fed into this comparison. Doing so honestly needs more than a
name match: (1) only a scientist-CONFIRMED link should count (a decision kind for
processed-output links does not exist yet; a proposed link is a suggestion); (2) an XDI
export carries the processed spectrum, not the project's ``pre1``/``nor1``/``nnorm``
parameters (those are present only when the file states ``Athena.*`` fields), so
:func:`compare` cannot re-run the scientist's normalisation from it; and (3) which column is
the normalised spectrum must come from the file's own ``Column.N``/column-header statement,
never from its extension. Until then the ``.prj`` path below is the only Athena comparison.
Measured on a real BL6-2c beamtime, that statement can be wrong: Demeter 0.9.24 ``.nor`` exports
declare ``Column.1: k``, ``Column.2: energy``, ``Column.4: merge`` over rows of TWO columns
(energy, normalised mu); the reader's ``declared_columns_differ`` anomaly must then refuse the
column mapping, never compare a misread column. (Those same curves reach this comparison through
their project, as ``is_nor`` groups; see ALREADY-NORMALISED DATA.)
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import re
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence

from . import core as C

MATCH_RULE_ID = "isaac.athena.match_by_name.v1"
#: r3-b H3: a merge word BEFORE a group's run or base name is the scientist's merge of it (module docstring)
SCIENTIST_MERGE_RULE_ID = "isaac.athena.scientist_merge_label.v0"
COMPARE_RULE_ID = "isaac.athena.compare.v0"

_EXT = re.compile(r"\.(txt|dat|xmu|nor|csv)$", re.IGNORECASE)
_SEP = re.compile(r"[\s\-.]+")
_MERGE_WORD = r"(merge|merged|mrg|avg|average|mean|sum)"
_SCAN_SUFFIX = re.compile(r"^(\d+(_\d+)*|" + _MERGE_WORD + r"\w*|scans?_?\d+(_\d+)*|\d+_?to_?\d+)$")
_HAS_MERGE_WORD = re.compile(r"(^|_)" + _MERGE_WORD + r"(_|$|\d)")
#: The SSRL XDC scan-file suffix after ``<stem>_`` in a NORMALISED name (``_A.001`` -> ``a_001``).
_XDC_SCAN_FILE = re.compile(r"^a_(\d+)$")
#: The same suffix after ``<stem>`` in a raw label (``_A.001``, ``_a_001``, ``.a.001``), case-insensitive.
_XDC_SCAN_FILE_RAW = re.compile(r"^[_\-. ][aA][._](\d+)$")
#: r3-b H3: a merge word (+ digits) BEFORE the rest of a normalised name (``merge4_<base>``)
_MERGE_PREFIX = re.compile(r"^" + _MERGE_WORD + r"\d*_(.+)$")
_WHOLE = re.compile(r"^[0-9]+$")


def normalise_name(name: str) -> str:
    base = PurePosixPath(str(name).replace("\\", "/")).name
    base = _EXT.sub("", base.strip())
    return _SEP.sub("_", base.casefold()).strip("_")


def _match_kind(names: Iterable[str], stem: str) -> str | None:
    """``exact`` | ``suffix`` | ``xdc_scan_file`` | ``None`` for normalised ``names`` against one stem."""
    best = None
    for n in names:
        if not n or not stem:
            continue
        if n == stem:
            return "exact"
        if n.startswith(stem + "_"):
            tail = n[len(stem) + 1 :]
            if _SCAN_SUFFIX.match(tail):
                best = "suffix"
            elif _XDC_SCAN_FILE.match(tail) and best is None:
                best = "xdc_scan_file"
    return best


def base_names(stems: Sequence[str]) -> set[str]:
    """The group's shared BASE name (normalised), the name without its counter, as a set (empty when there is none).
    Several runs: the stems with the token positions in which they differ removed, only when every such token is a
    whole number in every stem (``11_x_dry_091`` + ``11_x_dry_092`` -> ``11_x_dry``), and (r3-d) the XDAC letter after a
    removed final counter too (``22_x_dry_016_a`` + ``22_x_dry_017_a`` -> ``22_x_dry``, as for one run). One run: the
    stem without its trailing run counter (``_016``, XDAC ``_016_a``), else the stem itself."""
    names = sorted({normalise_name(s) for s in stems if s} - {""})
    if not names:
        return set()
    toks = [n.split("_") for n in names]
    if len(names) == 1:
        t = toks[0]
        if len(t) > 2 and len(t[-1]) == 1 and t[-1].isalpha() and _WHOLE.match(t[-2]):
            t = t[:-2]
        elif len(t) > 1 and _WHOLE.match(t[-1]):
            t = t[:-1]
        return {"_".join(t)}
    if len({len(t) for t in toks}) != 1:
        return set()
    differ = {i for i in range(len(toks[0])) if len({t[i] for t in toks}) > 1}
    if not all(_WHOLE.match(t[i]) for t in toks for i in differ):
        return set()
    drop = set(differ)
    last = len(toks[0]) - 1
    if (last >= 2 and (last - 1) in differ and last not in differ and len(toks[0][last]) == 1 and toks[0][last].isalpha()
            and any(i not in differ for i in range(last - 1))):
        drop.add(last)  # the XDAC letter of a run counter that was removed (``_016_a``): part of the counter
    base = [x for i, x in enumerate(toks[0]) if i not in drop]
    return {"_".join(base)} if base else set()


def scientist_merge_of(names: Iterable[str], stems: Sequence[str], bases: Iterable[str]) -> list[str] | None:
    """The (normalised) stems a scientist's merge named ``<merge word>[digits]_<name>`` covers (:data:`SCIENTIST_MERGE_RULE_ID`):
    ``[stem]`` when ``<name>`` is one stem, every stem when it is the group's base name; ``None`` otherwise."""
    stems = [s for s in stems if s]
    for n in names:
        m = _MERGE_PREFIX.match(n or "")
        if not m:
            continue
        rest = m.group(2)
        if rest in stems:
            return [rest]
        if rest in set(bases):
            return list(stems)
    return None


def is_scientist_merge(entry: Mapping) -> bool:
    """An Athena group the scientist merged: Athena flags it ``is_merge``, or one of its names carries a merge word."""
    return bool(entry.get("is_merge")) or any(_HAS_MERGE_WORD.search(n) for n in entry.get("names") or ())


def accepted_suffix(tail: str) -> bool:
    """True when the rule accepts ``tail`` (what follows ``<stem>_`` in a normalised name)."""
    return bool(_SCAN_SUFFIX.match(tail) or _XDC_SCAN_FILE.match(tail))


# --- reading projects -------------------------------------------------------------------------


def load_project(path: Path, rel_path: str, source_id: str | None, np) -> tuple[list[dict], list[str]]:
    """The xmu groups of one Athena project, with the scientist's parameters. (entries, notes)."""
    from larch.io import AthenaProject

    notes: list[str] = []
    prj = AthenaProject()
    try:
        # larch prints notes ("nans seen") and needs a real file descriptor: devnull, not StringIO
        # (StringIO.fileno() raises io.UnsupportedOperation, an OSError, inside larch).
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink):
            prj.read(str(path), do_preedge=True, do_bkg=False, do_fft=False)
    except Exception as exc:  # noqa: BLE001 - an unreadable project is a note, not a crash
        return [], [f"athena_unreadable:{rel_path}:{type(exc).__name__}"]
    out = []
    for gname, g in sorted(prj.groups.items()):
        energy = getattr(g, "energy", None)
        mu = getattr(g, "mu", None)
        if energy is None or mu is None or not hasattr(g, "norm"):
            notes.append(f"athena_group_not_xmu:{gname}")
            continue
        ap = getattr(g, "athena_params", None)
        bkg = getattr(ap, "bkg", None)
        # NEVER A NON-FINITE NUMBER: a project can carry "nan" text (larch reads it as a NaN float),
        # which is not a JSON number. Each such value becomes None and is NAMED in
        # ``non_finite_values`` (and on the result, run._athena_result) — never dropped silently.
        non_finite: list[str] = []

        def _p(obj, name):
            v = getattr(obj, name, None) if obj is not None else None
            try:
                f = float(v)
            except (TypeError, ValueError):
                return v
            if not math.isfinite(f):
                non_finite.append(f"params.{name}")
                return None
            return f

        params = {
            k: _p(bkg, k) for k in ("e0", "pre1", "pre2", "nor1", "nor2", "nnorm", "eshift", "flatten", "step", "fixstep", "z")
        }
        # A NON-FINITE bkg_eshift: the stored energies' frame is unknown. The group is KEPT (it is one of
        # the scientist's versions: dropping it would silently make the result-of-record choice), with
        # its identity intact, but nothing of it is placed on an energy axis (``energy_frame_known``):
        # no e0, no comparison, no curve file, no plot. Its result says so (ENERGY_FRAME_UNKNOWN_FLAG).
        frame_known = "params.eshift" not in non_finite
        if not frame_known:
            notes.append(f"athena_group_eshift_not_finite:{rel_path}:{gname}")
        eshift = (params["eshift"] or 0.0) if frame_known else 0.0
        channel_expr = {k: getattr(ap, k, None) for k in ("numerator", "denominator", "ln", "energy_string", "i0_string", "signal_string")} if ap is not None else {}
        e = np.asarray(energy, dtype=float)
        m = np.asarray(mu, dtype=float)
        e0_raw, step_raw = _finite(getattr(g, "e0", None)), _finite(getattr(g, "edge_step", None))
        already_normalized = _flag(ap, "is_nor")
        norm = np.asarray(g.norm, dtype=float)
        flat = np.asarray(getattr(g, "flat", g.norm), dtype=float)
        implausible = None
        renormalised, basis = None, None
        if already_normalized:
            # the stored spectrum is the scientist's normalised curve: used as stored, step 1 by definition
            # (larch's re-fit of it is not the scientist's processing and is discarded)
            norm, flat, step_raw = m.copy(), m.copy(), 1.0
            # ... believed only when it looks normalised (review): else handled as an implausible step
            implausible = C.stored_normalized_implausible(e, m, e0_raw, np)
        else:
            # r5 H1: larch's reading is not Athena's curve: made as Athena makes it (ATHENA_RENORM_RULE_ID)
            # (only where larch placed the curve: a non-finite E0 or step stays named as it is)
            rebuilt = (athena_normalisation(e, m, norm, step_raw, bkg, params, np, refits=_flag(ap, "update_norm"))
                       if e0_raw is not None and step_raw is not None else None)
            if rebuilt is not None:
                norm, flat, step_raw = rebuilt["norm"], rebuilt["flat"], rebuilt["edge_step"]
                renormalised, basis = rebuilt["said"], rebuilt["basis"]
            implausible = C.edge_step_implausible(step_raw, m, np, post_edge=_post_edge(params))
        if e0_raw is None:
            non_finite.append("e0_eV")
        if step_raw is None:
            non_finite.append("edge_step")
        is_merge = merge_flag(getattr(ap, "is_merge", None))
        # r3-b M3: where this group's OWN data puts its edge (larch find_e0, ISAAC's method), in the scientist's frame:
        # an Athena E0 far from it is evidence of a fixed setting (run.possibly_fixed_athena_e0); never compared or kept.
        # r3-d L-1: looked for only near the group's Athena E0 (DATA_E0_WINDOW_EV), so a glitch far away is never its edge
        data_e0 = _data_e0(e, m, e0_raw, np) if frame_known and not implausible else None
        out.append(
            {
                "prj_relative_path": rel_path,
                "prj_source_id": source_id,
                "group_name": gname,
                "label": str(getattr(g, "label", gname)),
                "filename": str(getattr(ap, "file", "") or getattr(g, "filename", "") or ""),
                "names": sorted({normalise_name(str(getattr(g, "label", gname))), normalise_name(str(getattr(ap, "file", "") or ""))} - {""}),
                "is_merge": is_merge,
                "energy": e + float(eshift),
                "mu": m,
                "norm": norm,
                "flat": flat,
                "energy_frame_known": frame_known,
                "e0_eV": (e0_raw + float(eshift)) if (e0_raw is not None and frame_known) else None,
                "edge_step": step_raw,
                "params": params,
                "non_finite_values": non_finite,
                "channel_expression": {k: (str(v) if v is not None else None) for k, v in channel_expr.items()},
                "data_hash": hashlib.sha256(e.tobytes() + m.tobytes()).hexdigest(),
                "data_e0_eV": (data_e0 + float(eshift)) if data_e0 is not None else None,
                # present only when true / found, so an entry without them is exactly as before
                **({"already_normalized": True} if already_normalized else {}),
                **({"edge_step_implausible": implausible} if implausible else {}),
                **({RENORMALISED_KEY: renormalised} if renormalised else {}),
                **({BASIS_KEY: basis} if basis else {}),
            }
        )
    return out, notes


#: r5 H1: THE SCIENTIST'S OWN NORMALISATION (``isaac.athena.project_normalisation.v1``). larch's
#: ``AthenaProject.read(do_preedge=True)`` is not Athena's curve: it passes ``bkg_nnorm`` to ``pre_edge`` unchanged,
#: while Athena (Ifeffit) counts coefficients (2 is a line, 3 a quadratic), and it ignores what the project stores.
#: Athena's definitions, with X = stored energy + ``bkg_eshift`` (``bkg_e0`` is in that frame, as Demeter has it),
#: L = ``bkg_int`` + ``bkg_slope``·X (absolute X) and P = sum ``bkg_nc<k>``·X^k (a fit to mu itself):
#: ``norm = (mu - L) / bkg_step``; ``flat = norm`` below E0 and, at and above E0,
#: ``norm - [(P - L)(X) - (P - L)(E0)] / bkg_step`` (``bkg_fixstep`` too).
#:
#: The STORED values are used only when they are CURRENT (:func:`_stored_current`): a fresh least-squares line over
#: the stored pre-edge window matches L within :data:`STORED_LINE_TOL` of a step, a fresh polynomial of the stored
#: curve's own degree over the stored normalisation window matches P within :data:`STORED_POST_TOL` of a step (a
#: window with too few points to fit is not judged), and, unless the step is fixed, P - L at E0 is the stored step
#: within :data:`STORED_STEP_TOL`. Measured on those projects (largest deviation over the window, in steps): sample
#: groups' lines 0.0002 (median) to 0.009 (95th percentile) and their post-edge curves 0.002 to 0.022; the stale
#: reference-channel groups' lines 0.1 (median) and up to 26. The tolerances sit between the two. Otherwise Athena
#: re-fits on display (``update_norm``), and so does ISAAC: larch ``pre_edge`` on X with the project's ranges,
#: ``nnorm = bkg_nnorm - 1`` and the stored step only when ``bkg_fixstep``. A stored line is never mixed with a
#: re-fitted step, nor the reverse. Measured on the projects of five real SSRL beamtimes (1,406 groups): the stored
#: formula is Athena's curve exactly on 788 of 799 sample groups whose values are current; 104 of 105 reference-channel
#: groups and 11 sample groups hold stale values (Athena re-fits them). larch's own reading differed from Athena's curve
#: in most groups (its step by more than 1 % in 853 of 904; 0.0058 for a stored 1.566 on a BL4-3 project, which put
#: the curve 328 steps above its pre-edge line), and by up to 0.065 even where the steps agreed.
#: A result says which way its curve was made (``normalisation_basis``) and, when the curve differs from larch's
#: reading by more than :data:`ATHENA_CURVE_TOL` (or its step by more than :data:`ATHENA_STEP_RTOL`), carries
#: :data:`ATHENA_RENORM_FLAG` and a sentence: larch's reproduction, never the scientist's fault. r6 G4: no longer
#: flagged on each result; recorded on it and said once for the bundle (:data:`ATHENA_RENORM_MATERIAL`).
ATHENA_RENORM_RULE_ID = "isaac.athena.project_normalisation.v1"
ATHENA_RENORM_FLAG = "athena_renormalisation_differs"
RENORMALISED_KEY = "renormalised_from_project"
BASIS_KEY = "normalisation_basis"
#: r6 G3: a per-scan set's members by basis (``{basis: count}``); absent on one curve
BASIS_COUNTS_KEY = "normalisation_basis_members"
BASIS_STORED = "stored"
BASIS_REFIT = "athena_refit"
ATHENA_STEP_RTOL = 0.01
ATHENA_CURVE_TOL = 0.01
#: r6 G4: a difference from larch's reading is MATERIAL when the two normalised curves differ by more than this (a
#: fraction of the edge step) over the project's post-edge range (``nor1`` to ``nor2`` above E0; over the whole curve
#: when that range holds no point). Every difference is recorded on its result (``renormalised_from_project``, with
#: ``post_edge_difference_from_larch`` and ``material``) and said ONCE for the bundle (``run.renormalisation_line``,
#: which counts the material ones); it is no longer flagged on each result. Measured on a real BL4-3 beamtime: the
#: flag was on 16 of 16 Athena results, and 16 of 18 differ by more than this (larch's step is a few percent off).
ATHENA_RENORM_MATERIAL = 0.02
STORED_LINE_TOL = 0.02
STORED_POST_TOL = 0.03
STORED_STEP_TOL = 0.01


def _poly(coeffs, x, np):
    return sum(c * x ** k for k, c in enumerate(coeffs))


def _stored_current(X, m, e0: float, S, bkg, params: Mapping, np, *, refits: bool = False) -> tuple | None:
    """``(L, P coefficients)`` when the project's stored line, post-edge curve and step are CURRENT for this data
    (:data:`ATHENA_RENORM_RULE_ID`), else ``None``. ``refits``: Athena marks the group for re-normalisation on display
    (``update_norm``); a window too short to judge then counts as not current (Athena's re-fit is what it shows)."""
    slope, intercept = _finite(getattr(bkg, "slope", None)), _finite(getattr(bkg, "int", None))
    nc = [_finite(getattr(bkg, f"nc{k}", None)) for k in range(4)]
    if S is None or S <= 0 or slope is None or intercept is None or nc[0] is None or nc[1] is None:
        return None
    nc = [c or 0.0 for c in nc]
    lims = [_finite(params.get(k)) for k in ("pre1", "pre2", "nor1", "nor2")]
    if any(v is None for v in lims):
        return None
    pre = (X >= e0 + lims[0]) & (X <= e0 + lims[1])
    post = (X >= e0 + lims[2]) & (X <= e0 + lims[3])
    # the stored curve's own degree (Athena lowers it on a short window); a window too short to fit is not judged
    deg = max([k for k in range(4) if nc[k] != 0] or [0])
    L = intercept + slope * X
    with np.errstate(all="ignore"):
        if int(pre.sum()) >= 2:
            fresh = np.polyval(np.polyfit(X[pre], m[pre], 1), X[pre])
            if not np.max(np.abs(fresh - L[pre])) / S <= STORED_LINE_TOL:
                return None
        elif refits:
            return None
        if int(post.sum()) >= deg + 1:
            fresh_p = np.polyval(np.polyfit(X[post], m[post], deg), X[post])
            if not np.max(np.abs(fresh_p - _poly(nc, X[post], np))) / S <= STORED_POST_TOL:
                return None
        elif refits:
            return None
    if not _finite(params.get("fixstep")):
        at = float(_poly(nc, e0, np) - (intercept + slope * e0))
        if not abs(at / S - 1.0) <= STORED_STEP_TOL:
            return None
    return L, nc, intercept + slope * e0


def athena_normalisation(energy, mu, larch_norm, larch_step, bkg, params: Mapping, np, *,
                         refits: bool = False) -> dict | None:
    """r5 H1 (:data:`ATHENA_RENORM_RULE_ID`): the scientist's normalised curve as Athena makes it: from the stored
    values when they are current, else Athena's re-fit. ``None`` when neither can be made (no E0, a fit that fails):
    larch's reading is then used as it is. ``said`` is what the result states."""
    e0, S = _finite(params.get("e0")), _finite(params.get("step"))
    if e0 is None:
        return None
    es = _finite(params.get("eshift")) or 0.0
    e, m = np.asarray(energy, dtype=float), np.asarray(mu, dtype=float)
    X = e + es
    fixed = bool(_finite(params.get("fixstep"))) and S is not None and S > 0
    flatten = bool(_finite(params.get("flatten")))
    current = _stored_current(X, m, e0, S, bkg, params, np, refits=refits)
    if current is not None:
        L, nc, L0 = current
        norm = (m - L) / S
        PL, PL0 = _poly(nc, X, np) - L, float(_poly(nc, e0, np) - L0)
        flat = np.where(X >= e0, norm - (PL - PL0) / S, norm) if flatten else norm.copy()
        step, basis = S, BASIS_STORED
    else:
        try:
            from larch import Group
            from larch.xafs import pre_edge

            g = Group(energy=X.copy(), mu=m.copy())
            nn = max(0, min(3, int(_finite(params.get("nnorm")) or 2) - 1))
            kw = {k: _finite(params.get(src)) for k, src in (("pre1", "pre1"), ("pre2", "pre2"), ("norm1", "nor1"), ("norm2", "nor2"))}
            with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink):
                pre_edge(g, e0=e0, nnorm=nn, nvict=int(_finite(getattr(bkg, "nvict", 0)) or 0),
                         step=S if fixed else None, make_flat=flatten, **{k: v for k, v in kw.items() if v is not None})
            norm = np.asarray(g.norm, dtype=float)
            flat = np.asarray(g.flat, dtype=float) if flatten else norm.copy()
            step = _finite(g.edge_step)
        except Exception:  # noqa: BLE001 - a re-fit that cannot be made leaves larch's reading as it is
            return None
        if step is None or step == 0:
            return None
        basis = BASIS_REFIT
    s = _finite(larch_step)
    ln = np.asarray(larch_norm, dtype=float)
    ok = np.isfinite(ln) & np.isfinite(norm)
    gap = float(np.max(np.abs(norm[ok] - ln[ok]))) if ok.any() else None
    differs = (gap is None or gap > ATHENA_CURVE_TOL or s is None or abs(s / step - 1.0) > ATHENA_STEP_RTOL)
    said = None
    if differs:
        post_gap = _post_edge_gap(X, norm, ln, e0, params, np)
        material = (post_gap > ATHENA_RENORM_MATERIAL) if post_gap is not None else (gap is None or gap > ATHENA_RENORM_MATERIAL)
        how = ("the project's stored normalisation, which still fits the data (its stored pre-edge line, post-edge "
               f"curve and edge step {step:.4g})" if basis == BASIS_STORED else
               "Athena's own re-fit of the project's ranges (the project's stored line or post-edge curve no longer "
               "fits the data, so Athena re-fits it on display; ISAAC re-ran that fit the way Athena does, counting "
               f"bkg_nnorm as coefficients{', with the fixed step' if fixed else ''}), edge step {step:.4g}")
        said = {"rule_id": ATHENA_RENORM_RULE_ID, "basis": basis, "larch_edge_step": s, "project_edge_step": S,
                "edge_step": step, "max_difference_from_larch": gap,
                # r6 G4: over the post-edge range, and whether that is material (ATHENA_RENORM_MATERIAL)
                "post_edge_difference_from_larch": post_gap, "material": bool(material),
                "statement": (f"larch's reading of this Athena group gives another curve (edge step "
                              f"{'unknown' if s is None else f'{s:.4g}'}, up to {'?' if gap is None else f'{gap:.3g}'} "
                              f"from the curve Athena shows). ISAAC used {how}, so the curve is the scientist's as "
                              "Athena makes it. The difference is larch's reproduction, not the scientist's "
                              "processing.")}
    return {"norm": norm, "flat": flat, "edge_step": step, "basis": basis, "said": said}


def _post_edge_gap(X, norm, larch_norm, e0: float, params: Mapping, np) -> float | None:
    """r6 G4: the largest difference between ISAAC's curve and larch's reading over the project's post-edge range
    (``nor1`` to ``nor2`` above ``e0``, in X's frame), or ``None`` when the range is unknown or holds no point."""
    lo, hi = _finite(params.get("nor1")), _finite(params.get("nor2"))
    if lo is None or hi is None or larch_norm.shape != norm.shape:
        return None
    win = (X >= e0 + lo) & (X <= e0 + hi) & np.isfinite(norm) & np.isfinite(larch_norm)
    if not win.any():
        return None
    return float(np.max(np.abs(norm[win] - larch_norm[win])))


def renorm_material(said: Mapping | None) -> bool:
    """r6 G4: whether a ``renormalised_from_project`` record is a MATERIAL difference (:data:`ATHENA_RENORM_MATERIAL`).
    A record made before r6 has no ``material`` key: it counts as material, as it was flagged."""
    return bool(said) and bool(said.get("material", True))


#: The rule that uses an ``is_nor`` group's stored spectrum as its normalised curve (module docstring).
ALREADY_NORMALIZED_RULE_ID = "isaac.athena.already_normalized.v0"
#: Comparison flag: the Athena curve's edge step failed the sanity bound, so it was not compared.
EDGE_STEP_IMPLAUSIBLE_FLAG = "athena_edge_step_implausible"


#: r3-d L-1: the half-width (eV) of the window around a group's Athena E0 in which its own data's edge is looked for
DATA_E0_WINDOW_EV = 25.0
_DATA_E0_MIN_POINTS = 10


def _data_e0(energy, mu, e0, np) -> float | None:
    """larch ``find_e0`` (maximum of the first derivative) of a group's stored data within :data:`DATA_E0_WINDOW_EV` of
    its Athena E0 ``e0`` (both in the stored frame), or ``None`` (no E0, too few points there, no edge found).

    r3-d L-1: over the whole curve, one glitch (a spike well above the edge) can have the largest derivative, which put
    "its own edge" tens of eV from the E0 and counted as evidence of a fixed E0. An edge outside the window still reads
    as far from the E0 (the steepest point inside is then on the window's side nearest the edge)."""
    if e0 is None:
        return None
    try:
        from larch.xafs import find_e0

        e, m = np.asarray(energy, dtype=float), np.asarray(mu, dtype=float)
        sel = np.isfinite(e) & np.isfinite(m) & (np.abs(e - float(e0)) <= DATA_E0_WINDOW_EV)
        if int(np.sum(sel)) < _DATA_E0_MIN_POINTS:
            return None
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink):
            return _finite(find_e0(e[sel], m[sel]))
    except Exception:  # noqa: BLE001 - an edge that cannot be found is no evidence either way
        return None


def merge_flag(value) -> bool:
    """r5 A4: an Athena group's ``is_merge`` value as a bool. Athena (Demeter) writes the SPACE the group was merged
    in (``'e'`` mu(E), ``'n'`` normalised, ``'k'`` chi(k)) and ``''`` for a group that is no merge; older projects
    write ``1`` / ``0``. Measured on the projects of five real SSRL beamtimes: only ``''``, ``'e'`` and ``'n'``
    occur, and reading the value as a number made every merge ``False``. True for a number other than 0 and for any other non-empty text."""
    if value is None or isinstance(value, bool):
        return bool(value)
    text = str(value).strip()
    if not text:
        return False
    try:
        number = float(text)
    except ValueError:
        return text.casefold() not in ("false", "no", "none")
    return math.isfinite(number) and number != 0.0


def _flag(ap, name: str) -> bool:
    """An Athena ``is_*`` flag ("1", "1.0", 1) as a bool; anything unreadable is False."""
    try:
        return bool(int(float(getattr(ap, name, 0) or 0)))
    except (TypeError, ValueError):
        return False


def _post_edge(params: Mapping) -> str | None:
    lo, hi = params.get("nor1"), params.get("nor2")
    if lo is None or hi is None:
        return None
    return f"nor1 {lo:g} to nor2 {hi:g} eV above E0, nnorm {params.get('nnorm')}"


def already_normalized(entry: Mapping) -> bool:
    return entry.get("already_normalized") is True


def plausible(entry: Mapping) -> bool:
    """False when the entry's edge step failed :func:`core.edge_step_implausible`."""
    return not entry.get("edge_step_implausible")


#: A version whose ``bkg_eshift`` is not a finite number: listed, never placed on an energy axis.
ENERGY_FRAME_UNKNOWN_FLAG = "athena_energy_frame_unknown"


def frame_known(entry: Mapping) -> bool:
    return entry.get("energy_frame_known", True) is not False


def _finite(x) -> float | None:
    """``float(x)`` when it is a finite number, else ``None`` (the caller names what was not)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _mean_or_none(values, np) -> float | None:
    """The mean, or ``None`` when any value is unknown (never a mean over what is left)."""
    return None if any(v is None for v in values) else _finite(np.mean(values))


def find_projects(bundle: Mapping) -> list[tuple[str, str | None]]:
    """(relative_path, source_id) of every ``.prj`` the bundle inventoried, sorted."""
    seen: dict[str, str | None] = {}
    for item in list(bundle.get("sources") or ()) + list(bundle.get("unread_files") or ()):
        rel = item.get("relative_path")
        if rel and str(rel).lower().endswith(".prj"):
            seen.setdefault(str(rel), item.get("source_id"))
    return sorted(seen.items())


# --- matching ---------------------------------------------------------------------------------


def _per_scan_set(pool: Sequence[Mapping], stems: Sequence[str], np) -> dict | None:
    """When the scientist kept ONE Athena group per scan file (no merge) — every candidate
    selects exactly one, distinct, scan of this record group, all in one project — the
    scientist's result is that SET. It is compared as the mean of the scientist's own
    per-scan normalised spectra (on the first group's grid), labelled as derived.

    r3-b H3: in a group of SEVERAL runs a scan is a run's scan (scan numbers restart in each run): the members are told
    apart by (run, scan), so the per-scan groups of every run form one set (measured on a real BL4-3 beamtime: of a
    two-run group, only one run's per-scan groups were read). Such a set names each member's run (``runs``)."""
    if np is None or len(pool) < 2 or len({c["prj_relative_path"] for c in pool}) != 1:
        return None
    if not all(frame_known(c) for c in pool):
        return None  # a curve in an unknown energy frame is never averaged: the versions stay listed
    sels = [_selection_of_run(c["label"], stems) for c in pool]
    if any(s is None or len(s[1]) != 1 for s in sels) or len({(s[0], s[1][0]) for s in sels}) != len(sels):
        return None
    # scan order as before when the scan numbers are distinct (so no set that formed before changes its first member,
    # its grid or its id); run, then scan, when runs repeat them
    distinct = len({s[1][0] for s in sels}) == len(sels)
    order = sorted(range(len(pool)), key=lambda i: sels[i][1][0] if distinct else (sels[i][0], sels[i][1][0]))
    runs = [str(stems[sels[i][0]]) for i in order]
    base = pool[order[0]]
    e = base["energy"]

    def _mean(key):
        rows = []
        for i in order:
            c = pool[i]
            y = np.interp(e, c["energy"], c[key])
            y[(e < c["energy"][0]) | (e > c["energy"][-1])] = np.nan
            rows.append(y)
        return np.nanmean(np.vstack(rows), axis=0)

    out = dict(base)
    out.update(
        {
            "label": f"{base['label']} [+{len(pool) - 1} per-scan groups]",
            "group_name": base["group_name"],
            "norm": _mean("norm"),
            "flat": _mean("flat"),
            "e0_eV": _mean_or_none([pool[i]["e0_eV"] for i in order], np),
            "edge_step": _mean_or_none([pool[i]["edge_step"] for i in order], np),
            "non_finite_values": sorted({v for i in order for v in pool[i].get("non_finite_values") or ()}),
            "per_scan_set": {
                "scans": [sels[i][1][0] for i in order],
                # r3-b H3: the run of each member, only when they span several runs (absent otherwise, as before)
                **({"runs": runs} if len(set(runs)) > 1 else {}),
                "labels": [pool[i]["label"] for i in order],
                "athena_groups": [pool[i]["group_name"] for i in order],
                "e0_eV": [pool[i]["e0_eV"] for i in order],
                "edge_step": [pool[i]["edge_step"] for i in order],
                "params": [pool[i]["params"] for i in order],
                # what makes two sets the same set (_per_scan_sets_by_project); internal, never written out
                "member_keys": [_curve_key(pool[i]) for i in order],
                "derived": "mean of the scientist's per-scan Athena normalisations (ISAAC-computed summary, not a scientist merge)",
            },
        }
    )
    # the set is already normalised only when every member is; it is implausible when any member is
    out.pop("already_normalized", None)
    out.pop("edge_step_implausible", None)
    if all(already_normalized(pool[i]) for i in order):
        out["already_normalized"] = True
    bad = next((pool[i]["edge_step_implausible"] for i in order if not plausible(pool[i])), None)
    if bad is not None:
        out["edge_step_implausible"] = bad
    # r5 H1: each member was made as Athena makes it before the mean (load_project); the set says how and how many
    out.pop(RENORMALISED_KEY, None)
    out.pop(BASIS_KEY, None)
    bases = sorted({pool[i][BASIS_KEY] for i in order if pool[i].get(BASIS_KEY)})
    if bases:
        out[BASIS_KEY] = "+".join(bases)
        # r6 G3: how many members were made each way, so the result names the basis of the set
        out[BASIS_COUNTS_KEY] = {b: sum(1 for i in order if pool[i].get(BASIS_KEY) == b) for b in bases}
    rebuilt = [pool[i][RENORMALISED_KEY] for i in order if pool[i].get(RENORMALISED_KEY)]
    if rebuilt:
        # r6 G3: the basis of each rebuilt member is named (stored values, or Athena's re-fit), never "one or the other"
        n_by = {b: sum(1 for r in rebuilt if r.get("basis") == b) for b in (BASIS_STORED, BASIS_REFIT)}
        how = " and ".join(x for x in (
            f"{n_by[BASIS_STORED]} from the project's stored values, which still fit the data" if n_by[BASIS_STORED] else "",
            f"{n_by[BASIS_REFIT]} by Athena's own re-fit of the project's ranges, the stored values no longer fitting "
            "the data" if n_by[BASIS_REFIT] else "") if x)
        post = [r.get("post_edge_difference_from_larch") for r in rebuilt]
        out[RENORMALISED_KEY] = {
            "rule_id": ATHENA_RENORM_RULE_ID, "members_rebuilt": len(rebuilt), "members": len(order),
            "larch_edge_step": [r["larch_edge_step"] for r in rebuilt],
            "project_edge_step": [r["project_edge_step"] for r in rebuilt],
            "basis": [r.get("basis") for r in rebuilt],
            # r6 G4: material when any member's difference is (renorm_material)
            "post_edge_difference_from_larch": post,
            "material": any(renorm_material(r) for r in rebuilt),
            "statement": (f"For {len(rebuilt)} of the {len(order)} per-scan groups, larch's reading gives another curve "
                          f"than Athena shows. ISAAC made {'it' if len(rebuilt) == 1 else 'them'} as Athena does"
                          f"{f' ({how})' if how else ''} before taking the mean, so the set is the scientist's curves as Athena makes them. "
                          "The difference is larch's reproduction, not the scientist's processing.")}
    return out


def _curve_key(entry: Mapping) -> tuple:
    """One Athena curve as the scientist made it: its raw data AND the normalisation parameters applied to it."""
    return (entry["data_hash"], json.dumps(entry.get("params"), sort_keys=True, default=str))


def _per_scan_sets_by_project(cands: Sequence[Mapping], stems: Sequence[str], np, *, group_id: str | None = None,
                              notes: list | None = None) -> list[dict] | None:
    """c10-m: the per-scan groups of ONE run kept in SEVERAL projects are one set PER PROJECT, never a version per
    scan. Measured on a real BL4-3 beamtime: scans 1-22 of a 42-scan run were per-scan groups in one project and
    1-25 in another (the same raw data, another normalisation). Collapsing them by data hash alone mixed the two
    projects (each scan's first copy kept), the one-project rule of :func:`_per_scan_set` then refused the mix,
    and every scan was listed as a "version" of the measurement. Here each project's candidates are taken on their
    own (:func:`_per_scan_set`; a project that forms no set keeps its groups as they are), and versions that are the
    same curves with the same parameters are one. ``None`` when no project forms a set: the caller's pool stands.

    c10-r: a project whose set is IDENTICAL to another's (the same curves AND the same parameters) is collapsed into
    the first (by path) and NAMED: on the kept set (``identical_sets_in``) and in a note appended to ``notes``."""
    by_prj: dict[str, dict[str, dict]] = {}
    for c in cands:
        by_prj.setdefault(c["prj_relative_path"], {}).setdefault(c["data_hash"], c)
    if len(by_prj) < 2:
        return None
    out, formed = [], False
    for path in sorted(by_prj):
        pool = list(by_prj[path].values())
        combined = _per_scan_set(pool, stems, np) if len(pool) > 1 else None
        if combined is not None:
            out.append({**combined, "_match_kind": "per_scan_set"})
            formed = True
        else:
            out.extend(pool)
    if not formed:
        return None
    same: dict[tuple, dict] = {}
    for v in out:
        is_set = v.get("_match_kind") == "per_scan_set"
        key = ("set", *v["per_scan_set"]["member_keys"]) if is_set else ("one", _curve_key(v))
        kept = same.setdefault(key, v)
        if is_set and kept is not v and v["prj_relative_path"] not in kept.setdefault("identical_sets_in", []):
            kept["identical_sets_in"].append(v["prj_relative_path"])
    for v in same.values():
        if v.get("identical_sets_in") and notes is not None:
            scans = ", ".join(str(n) for n in v["per_scan_set"]["scans"])
            notes.append({
                "code": "identical_athena_set_in_several_projects",
                "group_id": group_id,
                "prj_relative_path": v["prj_relative_path"],
                "identical_in": list(v["identical_sets_in"]),
                "statement": (f"The scientist's per-scan Athena groups for scans {scans} in "
                              f"{', '.join(v['identical_sets_in'])} are the same curves with the same normalisation "
                              f"parameters as those in {v['prj_relative_path']}, so they are one set (read from "
                              f"{v['prj_relative_path']})."),
            })
    return list(same.values())


#: c10-r: what a SET of per-scan groups is identified by (``version_provenance`` ``data_sha256_prefix``). A set's
#: project file and Athena group are its first member's, so its identity names its MEMBERS too (data hash and
#: parameters of each): a selection of one curve never resolves to a set holding it, nor a set to another set.
SET_IDENTITY_PREFIX = "set-"


def set_identity(members: Mapping) -> str:
    """``set-`` + the first 16 hex of the sha256 of the set's members (data hash, parameters), in scan order."""
    keys = json.dumps([list(k) for k in members["member_keys"]], sort_keys=True)
    return SET_IDENTITY_PREFIX + hashlib.sha256(keys.encode("utf-8")).hexdigest()[:16]


MAX_VERSIONS = 20
_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


def _set_named(entry: Mapping, members: Mapping) -> dict:
    """What a set's provenance names: its member groups, labels and scans, and (c10-r) the other projects that
    hold the identical set (absent when none does)."""
    out = {k: list(members[k]) for k in ("athena_groups", "labels", "scans")}
    if members.get("runs"):
        out["runs"] = list(members["runs"])
    if entry.get("identical_sets_in"):
        out["identical_in_projects"] = list(entry["identical_sets_in"])
    return out


#: The value Athena (Perl, Demeter) writes for a field it has no value for, e.g. a group's source file name.
ATHENA_NULL_MARKER = "@&^^null^^&@"


def version_provenance(entry: Mapping, stems: Sequence[str]) -> dict:
    """What the scientist's own files STATE about one Athena version — file name, the years
    the project's path names, the group label, merge flag, scan selection and parameters.
    Nothing is ranked; no version is selected."""
    path = entry["prj_relative_path"]
    members = entry.get("per_scan_set") if entry.get("_match_kind") == "per_scan_set" else None
    return {
        "prj_relative_path": path,
        "prj_file_name": PurePosixPath(path).name,
        "years_stated_in_path": sorted(set(_YEAR.findall(path))),
        "athena_label": entry["label"],
        "athena_group": entry["group_name"],
        "is_merge": entry.get("is_merge"),
        "scan_selection": list(members["scans"]) if members else scan_selection(entry["label"], stems),
        "params": entry.get("params"),
        # c10-r: a SET's identity names its members (set_identity); one curve's is its data hash
        "data_sha256_prefix": set_identity(members) if members else str(entry.get("data_hash") or "")[:16],
        # c10-m: a version that is a SET of the scientist's per-scan groups names them (its label is the first's)
        **({"per_scan_set": _set_named(entry, members)} if members else {}),
        **({"already_normalized": True, "already_normalized_rule": ALREADY_NORMALIZED_RULE_ID} if already_normalized(entry) else {}),
        **({"edge_step_implausible": entry["edge_step_implausible"]} if not plausible(entry) else {}),
    }


#: r5 A2: record-group statuses whose runs another (live) group now holds: such a group takes no part in the match.
MERGED_AWAY_STATUSES = frozenset({"merged", "split"})


def takes_part(group: Mapping) -> bool:
    """Whether a record group takes part in the name match: it has scans, and (r5 A2) it was not MERGED AWAY (status
    ``merged`` or ``split``: another live group holds its runs). Measured on a real BL4-3 beamtime: two one-run groups
    merged into one two-run group stayed in the match, so the Athena groups of the dead run matched it as well as the
    live group, were ambiguous, and the live group lost the scientist's merge to the dead one. A rejected group still
    takes part: its runs are in no live group, so an Athena group naming them is not the live group's."""
    return bool(group.get("_has_scans", True)) and group.get("status") not in MERGED_AWAY_STATUSES


def match(groups: Sequence[Mapping], entries: Sequence[Mapping], np=None) -> tuple[dict[str, dict], list[dict]]:
    return match_with_versions(groups, entries, np)[:2]


#: r6 G1: the match kind of an Athena group the SCIENTIST named for a record group (params ``athena_match``)
TIED_KIND = "named_by_scientist"


def resolve_ties(ties: Mapping[str, Sequence[Mapping]], entries: Sequence[Mapping],
                 groups: Sequence[Mapping], *, not_this: bool = False) -> tuple[dict[int, list[str]], list[dict]]:
    """r6 G1: ``({entry index: [group ids]}, what was done with each named tie)`` for a params file's ``athena_match``
    (``protocol.athena_match_ties``). A tie names ONE Athena group exactly: its project (relative path, or file name)
    AND its Athena group name or label. One that names no group read, several, or no live record group ties nothing,
    and says so. Never a near name: the scientist's naming is the only way such a group is tied. A rejected group is
    no live group here (review LOW 2). ``not_this``: the rows of ``athena_match_not`` (the scientist's "no": that
    Athena group is not that record group's), resolved the same way, status ``not_this_group``."""
    section, done = ("athena_match_not", "set aside") if not_this else ("athena_match", "tied")
    live = {g["group_id"] for g in groups if hint_eligible(g)}
    known = {g["group_id"] for g in groups}
    stems = {g["group_id"]: [normalise_name(s) for s in g.get("_stems") or ()] for g in groups if takes_part(g)}
    bases = {gid: base_names(gstems) for gid, gstems in stems.items()}
    by_entry: dict[int, list[str]] = {}
    said: list[dict] = []
    for gid, items in sorted(ties.items()):
        for item in items:
            prj, grp = item["project"], item["athena_group"]
            hit = [i for i, e in enumerate(entries)
                   if prj in (e["prj_relative_path"], PurePosixPath(e["prj_relative_path"]).name)
                   and grp in (e["group_name"], e["label"])]
            row = {"group_id": gid, "project": prj, "athena_group": grp}
            if gid not in live:
                row["status"] = "no_live_group"
                row["statement"] = (f"The params file's {section} names {grp!r} in {prj} for {gid}, which is "
                                    f"{'no live record group (rejected, merged or split)' if gid in known else 'no record group of this bundle'}: nothing was {done}.")
            elif not hit:
                row["status"] = "not_found"
                row["statement"] = (f"The params file's {section} names {grp!r} in {prj} for {gid}, but no Athena "
                                    f"group read has that project and that name or label: nothing was {done}. Check both.")
            elif len(hit) > 1:
                row["status"] = "several"
                row["statement"] = (f"The params file's {section} names {grp!r} in {prj} for {gid}, which fits "
                                    f"{len(hit)} Athena groups read: nothing was {done}. Name the project by its relative "
                                    "path and the group by its Athena group name.")
            elif not_this:
                # review LOW 4: the scientist said this merge is NOT this group's: no hint names it for the group
                row["status"] = "not_this_group"
                row["entry_index"] = hit[0]
                lst = by_entry.setdefault(hit[0], [])
                if gid not in lst:
                    lst.append(gid)
                row["statement"] = (f"The scientist said Athena group {entries[hit[0]]['label']!r} in "
                                    f"{entries[hit[0]]['prj_relative_path']} is not {gid}'s (params athena_match_not): "
                                    "it is no longer offered as a hint for that group.")
            else:
                row["status"] = "tied"
                row["entry_index"] = hit[0]
                lst = by_entry.setdefault(hit[0], [])
                if gid not in lst:
                    lst.append(gid)
                row["statement"] = (f"The scientist named Athena group {entries[hit[0]]['label']!r} in "
                                    f"{entries[hit[0]]['prj_relative_path']} as {gid}'s (params athena_match): it is "
                                    "matched to that group by the scientist's naming, not by its name.")
                # review LOW 5: a tied group that ALSO matches another group by name is now the named group's only
                others = sorted({h[0] for h in _hits(entries[hit[0]], stems, bases)} - {gid})
                if others:
                    row["also_matches_by_name"] = others
                    row["statement"] += (f" Its name also matches {', '.join(others)}; it is now {gid}'s only, so "
                                         f"{'that group no longer has' if len(others) == 1 else 'those groups no longer have'} it.")
            said.append(row)
    return by_entry, said


def resolve_ignores(items: Sequence[Mapping], entries: Sequence[Mapping], groups: Sequence[Mapping]) -> tuple[set[int], list[dict]]:
    """r7 K5: ``({entry index}, what was done with each)`` for a params file's ``athena_ignore``
    (``protocol.athena_ignores``): the scientist's merges that are no group's, set aside so they are no longer listed
    as unmatched. Each names ONE Athena group exactly (project and Athena group name or label, as a tie does); one
    that names none, several, or a group that is not an unmatched merge sets nothing aside, and says so."""
    stems = {g["group_id"]: [normalise_name(s) for s in g.get("_stems") or ()] for g in groups if takes_part(g)}
    bases = {gid: base_names(gstems) for gid, gstems in stems.items()}
    out: set[int] = set()
    rows: list[dict] = []
    for item in items:
        prj, grp = item["project"], item["athena_group"]
        hit = [i for i, e in enumerate(entries)
               if prj in (e["prj_relative_path"], PurePosixPath(e["prj_relative_path"]).name)
               and grp in (e["group_name"], e["label"])]
        row = {"project": prj, "athena_group": grp}
        if not hit:
            row.update(status="not_found", statement=(
                f"The params file's athena_ignore names {grp!r} in {prj}, but no Athena group read has that project "
                "and that name or label: nothing was set aside. Check both."))
        elif len(hit) > 1:
            row.update(status="several", statement=(
                f"The params file's athena_ignore names {grp!r} in {prj}, which fits {len(hit)} Athena groups read: "
                "nothing was set aside. Name the project by its relative path and the group by its Athena group name."))
        elif _hits(entries[hit[0]], stems, bases) or not is_scientist_merge(entries[hit[0]]):
            row.update(status="not_unmatched", statement=(
                f"The params file's athena_ignore names {grp!r} in {prj}, which is no merge that matches no group: "
                "nothing was set aside (it is matched by name, or it is no merge)."))
        else:
            out.add(hit[0])
            row.update(status="ignored", label=entries[hit[0]]["label"],
                       prj_relative_path=entries[hit[0]]["prj_relative_path"])
        rows.append(row)
    return out, rows


def match_with_versions(groups: Sequence[Mapping], entries: Sequence[Mapping], np=None, *,
                        ties: Mapping[int, Sequence[str]] | None = None) -> tuple[dict[str, dict], list[dict], dict[str, list[dict]]]:
    """group_id -> athena entry (unambiguous matches only), and notes on every ambiguity.

    Record groups with no scans take no part (measured: a scientist's exported ``x.dat``
    became a zero-scan run named like the real run, which made every match ambiguous), nor (r5 A2) groups MERGED AWAY
    (:func:`takes_part`).

    r6 G1: ``ties`` (:func:`resolve_ties`) are the Athena groups the SCIENTIST named for a group: such an entry is that
    group's candidate (:data:`TIED_KIND`) and no other group's, whatever its name says; it is then handled as any
    candidate (a single merge is preferred, several are versions the scientist chooses between).
    """
    stems = {g["group_id"]: [normalise_name(s) for s in g.get("_stems") or ()] for g in groups if takes_part(g)}
    raw_stems = {g["group_id"]: list(g.get("_stems") or ()) for g in groups}
    bases = {gid: base_names(gstems) for gid, gstems in stems.items()}
    notes: list[dict] = []
    by_group: dict[str, list[dict]] = {}
    ties = ties or {}
    for idx, entry in enumerate(entries):
        if idx in ties:
            for gid in ties[idx]:
                by_group.setdefault(gid, []).append({**entry, "_match_kind": TIED_KIND, "_index": idx,
                                                     "_merge_of": list(stems.get(gid) or ())})
            continue
        hits = _hits(entry, stems, bases)
        if not hits:
            continue
        exact = [h for h in hits if h[1] == "exact"]
        chosen = exact if exact else hits
        if len(chosen) > 1:
            notes.append(
                {
                    "code": "athena_group_matches_several_record_groups",
                    "athena_label": entry["label"],
                    "prj_relative_path": entry["prj_relative_path"],
                    "group_ids": sorted(h[0] for h in chosen),
                }
            )
            continue
        gid, kind, covers = chosen[0]
        by_group.setdefault(gid, []).append({**entry, "_match_kind": kind, "_index": idx,
                                             **({"_merge_of": covers} if kind == "scientist_merge" else {})})
    matched: dict[str, dict] = {}
    versions: dict[str, list[dict]] = {}
    for gid, cands in by_group.items():
        # c10-r: copies in SEVERAL projects are one curve only when the parameters applied to them are the same too.
        # A data hash alone kept each scan's first copy: when the first project's copies covered every scan, its set
        # formed from it alone and another project's normalisation of the same scans disappeared without a word.
        several = len({c["prj_relative_path"] for c in cands}) > 1
        uniq: dict = {}
        for c in cands:
            uniq.setdefault(_curve_key(c) if several else c["data_hash"], c)
        pool = list(uniq.values())
        aside: list[dict] = []
        settled = False
        if len(pool) > 1:
            # one merged candidate is the scientist's result (r3-b H3: a ``merge_<base>`` group too, so it is preferred
            # over the per-scan groups beside it, which ISAAC would otherwise average)
            merged = [c for c in pool if is_scientist_merge(c)]
            if len(merged) == 1:
                # r3-d: the per-scan sets beside it are kept (set aside, said, and compared with it in run.process_group)
                aside = _sets_beside([c for c in pool if c is not merged[0]], raw_stems.get(gid) or (), np)
                pool = merged
            elif 1 < len(merged) < len(pool):
                # r5 A3: SEVERAL merges beside per-scan groups: the merges are versions, and the per-scan groups of
                # each project are one version, a set (_per_scan_set), never a version per scan
                pool, settled = _merges_and_sets(merged, [c for c in pool if not is_scientist_merge(c)],
                                                 [c for c in cands if not is_scientist_merge(c)],
                                                 raw_stems.get(gid) or (), np)
        if len(pool) > 1 and not settled:
            if several:
                # c10-m/c10-r: per-scan groups in several projects are a set PER PROJECT (split first), never a
                # version per scan, and never one project's set standing for another's
                pool = _per_scan_sets_by_project(cands, raw_stems.get(gid) or (), np, group_id=gid, notes=notes) or pool
            else:
                combined = _per_scan_set(pool, raw_stems.get(gid) or (), np)
                if combined is not None:
                    pool = [{**combined, "_match_kind": "per_scan_set"}]
        if len(pool) == 1:
            matched[gid] = {**pool[0], "_candidates": len(cands), "_distinct": len(uniq), **({"_sets_aside": aside} if aside else {})}
        else:
            notes.append(
                {
                    "code": "several_athena_groups_for_record_group",
                    "group_id": gid,
                    "candidates": [{"label": c["label"], "prj_relative_path": c["prj_relative_path"]} for c in pool][:20],
                }
            )
            versions[gid] = [{**c, "_match_kind": c.get("_match_kind")} for c in sorted(pool, key=lambda c: (c["prj_relative_path"], c["group_name"]))][:MAX_VERSIONS]
    return matched, notes, versions


def _merges_and_sets(merged: Sequence[Mapping], rest: Sequence[Mapping], every: Sequence[Mapping],
                     stems: Sequence[str], np) -> tuple[list[dict], bool]:
    """r5 A3: the versions of a record group whose candidates hold SEVERAL scientist merges and per-scan groups:
    every merge, each per-scan SET the per-scan groups form (:func:`_sets_beside`, one per project, built from EVERY
    non-merge candidate of that project, ``every``, as :func:`_per_scan_sets_by_project` builds them; a set identical
    to another project's, the same curves and parameters, is one), and the per-scan groups of ``rest`` (the deduped
    pool) that are in no set (never dropped). ``(pool, True)`` when a set formed, else ``(merged + rest, False)``: the
    pool stands and is handled as before. Measured on a real BL4-3 beamtime: a two-run group had the scientist's merge
    in two projects (other post-edge ranges) and four per-scan groups in one of them, and all six were listed as
    versions, every scan one of them."""
    by_prj: dict[str, dict[str, Mapping]] = {}
    for c in every:
        by_prj.setdefault(c["prj_relative_path"], {}).setdefault(c["data_hash"], c)
    sets, seen = [], set()
    for st in _sets_beside([c for d in by_prj.values() for c in d.values()], stems, np):
        key = tuple(st["per_scan_set"]["member_keys"])
        if key not in seen:
            seen.add(key)
            sets.append(st)
    if not sets:
        return list(merged) + list(rest), False
    in_set = {k for st in sets for k in st["per_scan_set"]["member_keys"]}
    loose = [c for c in rest if _curve_key(c) not in in_set]
    return list(merged) + sets + loose, True


def _sets_beside(rest: Sequence[Mapping], stems: Sequence[str], np) -> list[dict]:
    """r3-d: the per-scan sets (:func:`_per_scan_set`, one per project) that the candidates beside a scientist's merge
    form, in project order; each is a ``per_scan_set`` entry exactly as it would be matched without the merge."""
    by_prj: dict[str, list[Mapping]] = {}
    for c in rest:
        by_prj.setdefault(c["prj_relative_path"], []).append(c)
    out = []
    for path in sorted(by_prj):
        combined = _per_scan_set(by_prj[path], stems, np) if len(by_prj[path]) > 1 else None
        if combined is not None:
            out.append({**combined, "_match_kind": "per_scan_set"})
    return out


def merge_versus_set(merge: Mapping, aside: Mapping, params: Mapping, np) -> dict:
    """r3-d: the scientist's merge compared with the mean of a per-scan set beside it (:func:`compare`, the same
    tolerances, the merge in ISAAC's place): ``verdict`` ``agree`` | ``differs`` | ``not_comparable``."""
    if not frame_known(merge) or not plausible(merge):
        return {"verdict": "not_comparable", "metrics": {}, "flags": [ENERGY_FRAME_UNKNOWN_FLAG if not frame_known(merge)
                                                                   else EDGE_STEP_IMPLAUSIBLE_FLAG]}
    got = compare({"grid": merge["energy"], "norm": merge["norm"], "flat": merge["flat"], "e0_eV": merge["e0_eV"],
                   "edge_step": merge["edge_step"]}, aside, params, np)
    m = got["metrics"]
    metrics = {"e0_merge_eV": m.get("e0_isaac_eV"), "e0_set_mean_eV": m.get("e0_athena_eV"), "e0_delta_eV": m.get("e0_delta_eV"),
               "edge_step_merge": m.get("edge_step_isaac"), "edge_step_set_mean": m.get("edge_step_athena"),
               **{k: m[k] for k in ("compared_quantity", "overlap_points", "rms_norm") if k in m}}
    return {"verdict": got["verdict"], "metrics": metrics, "flags": list(got["flags"]), "tolerances": got["tolerances"]}


def _hits(entry: Mapping, stems: Mapping[str, Sequence[str]], bases: Mapping[str, set]) -> list[tuple]:
    """``[(group_id, kind, covered stems or None)]``: every record group one Athena entry matches (module docstring)."""
    hits = []
    for gid, gstems in stems.items():
        kinds = [k for k in (_match_kind(entry["names"], s) for s in gstems) if k]
        if kinds:
            hits.append((gid, "exact" if "exact" in kinds else ("suffix" if "suffix" in kinds else kinds[0]), None))
            continue
        covers = scientist_merge_of(entry["names"], gstems, bases.get(gid) or ())
        if covers:
            hits.append((gid, "scientist_merge", covers))
    return hits


def entry_groups(groups: Sequence[Mapping], entries: Sequence[Mapping], *,
                 ties: Mapping[int, Sequence[str]] | None = None) -> dict[int, str]:
    """``{entry index: group_id}`` for every Athena entry that matches exactly ONE record group (an exact match winning,
    as :func:`match_with_versions` decides), whether or not that group then uses it. r6 G1: an entry the scientist
    tied (``ties``) is its (first) named group's."""
    stems = {g["group_id"]: [normalise_name(s) for s in g.get("_stems") or ()] for g in groups if takes_part(g)}
    bases = {gid: base_names(gstems) for gid, gstems in stems.items()}
    out = {}
    ties = ties or {}
    for idx, entry in enumerate(entries):
        if ties.get(idx):
            out[idx] = ties[idx][0]
            continue
        hits = _hits(entry, stems, bases)
        chosen = [h for h in hits if h[1] == "exact"] or hits
        if len(chosen) == 1:
            out[idx] = chosen[0][0]
    return out


# --- the scientist's merges that match no group (r6 G1) --------------------------------------------------------------

#: r6 G1: NEAR-NAME HINTS for a scientist's merge that matches no record group (``isaac.athena.unmatched_merge_hint.v0``).
#: A HINT ONLY: it never matches, never selects and never changes a result; the scientist says which group (if any) the
#: merge is, and ties it by name in a params file (:data:`protocol.ATHENA_MATCH_SECTION`). The merge's own name is its
#: normalised label (or file name) after its merge word and counter (``merge4_``, ``truncated_merge2_``). A live record
#: group (not rejected) is a candidate when (a) the leading run number of its base name (``07`` of ``07_x_m300mv``) is
#: one of the whole numbers the merge's own name STARTS with (``07_…``, ``03_05_…``; a number later in the name, such
#: as scans ``1_4``, is not a run number) AND they share at least one other token, or (b) the two names without their
#: leading run numbers are at least :data:`UNMATCHED_HINT_MIN_RATIO` alike (difflib ratio, an edit distance), unless
#: (review M2) they differ in a token that holds the same letters with other digits (``m200mv`` / ``m300mv``, ``s1`` /
#: ``s2``): another potential or spot is another sample, never a typo. Every hint names the tokens in which the
#: names differ (``differs_in``). (a) hints come first, then (b), best first; neither hides the other. Measured on a
#: real BL4-3 beamtime: 46 of the scientists' 56 Athena merges matched no group, their names typed shorter or
#: otherwise than the scan files (``spt2`` for ``spot2``, ``sugar`` for ``sucrose``, ``0V`` for ``m0V``, ``postXA``),
#: and ISAAC said nothing of them.
UNMATCHED_HINT_RULE_ID = "isaac.athena.unmatched_merge_hint.v0"
#: r7 K3: a hint never crosses run numbers. When both names START with whole numbers (electrode, run: ``01_05_…``)
#: and neither set of them holds the other, the names are other runs (``01_05`` / ``03_04``), never a hint, however
#: alike the rest is. A group whose leading numbers are the merge's own is ranked first. A leading ``Ref`` word is
#: no part of the name. The run numbers that differ are named in ``differs_in``.
UNMATCHED_HINT_RUN_NUMBERS_RULE_ID = "isaac.athena.unmatched_merge_hint.run_numbers.v0"
#: r7 K3: Athena names the REFERENCE CHANNEL it reads beside a sample ``"  Ref <name>"``. Such a group is the
#: reference foil of a scan, not the scientist's merge of a sample: it is never listed as an unmatched merge, never
#: hinted and never asked about; it is counted in the summary line. Measured on a real BL15-2 beamtime: 77 of the 79
#: "merges that match no group" were these, and their hints sat on 116 of 153 results.
REFERENCE_CHANNEL_RULE_ID = "isaac.athena.reference_channel.v0"
_REFERENCE_CHANNEL = re.compile(r"^\s*ref\s+\S", re.IGNORECASE)
UNMATCHED_HINT_MIN_RATIO = 0.85
UNMATCHED_HINT_MAX = 3
_MERGE_TOKEN = re.compile(r"^" + _MERGE_WORD + r"\d*$")


def is_reference_channel(entry: Mapping) -> bool:
    """r7 K3 (:data:`REFERENCE_CHANNEL_RULE_ID`): an Athena group whose label is Athena's name for a reference channel
    (``"  Ref <name>"``): the reference read beside a sample, never a sample merge."""
    return bool(_REFERENCE_CHANNEL.match(str(entry.get("label") or "")))


def _without_ref(name: str) -> str:
    """r7 K3: a normalised name without a leading ``ref`` word (``ref_01_05_x`` -> ``01_05_x``)."""
    return name[4:] if name.startswith("ref_") else name


def merge_own_name(entry: Mapping) -> str:
    """The name a scientist's merge gives what it merged: its normalised label (else file name) after the first merge
    word (+ counter) token, or the whole name when it has none (an ``is_merge`` flag only)."""
    names = [n for n in entry.get("names") or () if n]
    label = normalise_name(str(entry.get("label") or ""))
    for n in ([label] if label else []) + names:
        toks = n.split("_")
        at = next((i for i, t in enumerate(toks) if _MERGE_TOKEN.match(t)), None)
        if at is not None:
            return "_".join(toks[at + 1:])  # "" when the merge word is all it says (``merge16``)
    return label or (names[0] if names else "")


def _lead_number(name: str) -> int | None:
    tok = name.split("_", 1)[0]
    return int(tok) if _WHOLE.match(tok) else None


def _without_lead_numbers(name: str) -> str:
    toks = name.split("_")
    while toks and _WHOLE.match(toks[0]):
        toks = toks[1:]
    return "_".join(toks)


def _lead_tokens(name: str) -> list[str]:
    """The whole-number tokens a name STARTS with, as written (``03_05_x`` -> ["03", "05"])."""
    out = []
    for t in name.split("_"):
        if not _WHOLE.match(t):
            break
        out.append(t)
    return out


def _lead_numbers(name: str) -> set[int]:
    """The whole numbers a name STARTS with (``03_05_x`` -> {3, 5}); none when it starts with a word."""
    return {int(t) for t in _lead_tokens(name)}


def _run_numbers_compatible(a: Sequence[int], b: Sequence[int]) -> bool:
    """r7 K3: whether two names' leading numbers (in order) can name the same run: either has none; one has a single
    number that the other names (a merge ``03_05_…`` of runs 03 and 05, a group ``05_…``); or both name the same
    numbers in the same order (``01_05`` is never ``03_04``, nor ``04_11`` ``04_04``)."""
    if not a or not b:
        return True
    if len(a) == 1 or len(b) == 1:
        return a[0] in b if len(a) == 1 else b[0] in a
    return list(a) == list(b)


def _differs_in(a: str, b: str) -> dict:
    """The tokens only in ``a`` (the merge's name) and only in ``b`` (the group's): first (r7 K3) the leading run
    numbers one names and the other does not, then the other tokens without their leading numbers."""
    na, nb = _lead_numbers(a), _lead_numbers(b)
    runs_a = [t for t in _lead_tokens(a) if int(t) not in nb] if nb else []
    runs_b = [t for t in _lead_tokens(b) if int(t) not in na] if na else []
    words = _word_diff(a, b)
    return {"merge": runs_a + words["merge"], "group": runs_b + words["group"]}


def _word_diff(a: str, b: str) -> dict:
    """The tokens only in ``a`` and only in ``b``, each name without its leading numbers."""
    ta, tb = _without_lead_numbers(a).split("_"), _without_lead_numbers(b).split("_")
    return {"merge": [t for t in ta if t and t not in tb], "group": [t for t in tb if t and t not in ta]}


def _digits_only_difference(diff: Mapping) -> bool:
    """Review M2: the names differ in a token that holds the same letters with other digits (``m200mv`` / ``m300mv``,
    ``s1`` / ``s2``): another potential, spot or sample number, never a typo, whatever else differs."""
    skel = lambda t: re.sub(r"\d+", "#", t)  # noqa: E731
    theirs = {skel(t) for t in diff["group"] if re.search(r"\d", t)}
    return any(re.search(r"\d", t) and skel(t) in theirs for t in diff["merge"])


def hint_eligible(group: Mapping) -> bool:
    """A group a hint or a tie may name: it takes part in the match (:func:`takes_part`) and is not rejected (review
    LOW 2: a rejected group cannot become a record)."""
    return takes_part(group) and group.get("status") != "rejected"


def near_name_candidates(entry: Mapping, groups: Sequence[Mapping]) -> list[dict]:
    """r6 G1 (:data:`UNMATCHED_HINT_RULE_ID`): the live record groups whose names are NEAR the merge's own name, best
    first, at most :data:`UNMATCHED_HINT_MAX`. Each says why (``shares_run_number``, ``shared_tokens``, ``similarity``,
    ``differs_in``). Hints only: nothing is matched."""
    import difflib

    if is_reference_channel(entry):
        return []
    own = _without_ref(merge_own_name(entry))
    if not own:
        return []
    toks = set(own.split("_")) - {""}
    numbers = _lead_numbers(own)
    seq = [int(t) for t in _lead_tokens(own)]
    words = {t for t in toks if not _WHOLE.match(t)}
    bare = _without_lead_numbers(own)
    out = []
    for g in groups:
        if not hint_eligible(g):
            continue
        stems = [normalise_name(x) for x in g.get("_stems") or () if x]
        if not stems:
            continue
        best = None
        for name in sorted(base_names(stems) | set(stems)):
            gtoks = set(name.split("_")) - {""}
            shared = sorted(words & {t for t in gtoks if not _WHOLE.match(t)})
            lead = _lead_number(name)
            gseq = [int(t) for t in _lead_tokens(name)]
            if not _run_numbers_compatible(seq, gseq):
                continue  # r7 K3: other run numbers (``01_05`` / ``03_04``): another run, never a hint
            same_numbers = bool(seq) and seq == gseq
            by_number = lead is not None and lead in numbers and bool(shared)
            ratio = difflib.SequenceMatcher(None, bare, _without_lead_numbers(name)).ratio() if bare else 0.0
            diff = _differs_in(own, name)
            alike = ratio >= UNMATCHED_HINT_MIN_RATIO and not _digits_only_difference(_word_diff(own, name))
            if not (by_number or alike):
                continue
            key = (same_numbers, by_number, round(ratio, 3), len(shared))
            if best is None or key > best[0]:
                best = (key, {"group_id": g["group_id"], "group_name": name, "shares_run_number": by_number,
                              "same_run_numbers": same_numbers, "shared_tokens": shared, "similarity": round(ratio, 3),
                              "differs_in": diff})
        if best is not None:
            out.append(best)
    out.sort(key=lambda kv: (not kv[0][0], not kv[0][1], -kv[0][2], -kv[0][3], kv[1]["group_id"]))
    return [c for _, c in out[:UNMATCHED_HINT_MAX]]


def _merge_key(e: Mapping) -> tuple:
    """One merge's identity across projects: its normalised label and its data (the same in several projects is one)."""
    return normalise_name(str(e.get("label") or "")), e.get("data_hash")


def unmatched_reference_channels(groups: Sequence[Mapping], entries: Sequence[Mapping], *,
                                 tied: Iterable[int] = ()) -> list[dict]:
    """r7 K3: the reference-channel groups (:func:`is_reference_channel`) that match no record group and that no params
    file ties: ``[{"athena_label", "in": [project, ...]}]``, one per label and data. Counted, never hinted."""
    stems = {g["group_id"]: [normalise_name(s) for s in g.get("_stems") or ()] for g in groups if takes_part(g)}
    bases = {gid: base_names(gstems) for gid, gstems in stems.items()}
    tied = set(tied)
    items: dict[tuple, dict] = {}
    for idx, e in enumerate(entries):
        if idx in tied or not is_reference_channel(e) or not is_scientist_merge(e) or _hits(e, stems, bases):
            continue
        item = items.setdefault(_merge_key(e), {"athena_label": str(e.get("label") or "").strip(), "in": []})
        item["in"].append(e["prj_relative_path"])
    return list(items.values())


def unmatched_merges(groups: Sequence[Mapping], entries: Sequence[Mapping], *, tied: Iterable[int] = (),
                     not_this: Mapping[int, Sequence[str]] | None = None, ignored: Iterable[int] = ()) -> list[dict]:
    """r6 G1: the scientist's merges (:func:`is_scientist_merge`) that match NO record group by name (no hit at all;
    one that matches several groups has its own note) and that no params file ties to a group (``tied``: entry
    indexes). One item per merge: the same label with the same data in several projects is ONE merge, naming every
    project. Each item lists its near-name candidates (:func:`near_name_candidates`: hints only, never matched), less
    the groups the scientist said it is not (``not_this``: {entry index: [group ids]}, params ``athena_match_not``,
    any copy of it). r7 K3: a reference channel (:func:`is_reference_channel`) is no sample merge: never listed
    (:func:`unmatched_reference_channels` counts them). r7 K5: a merge the scientist set aside (``ignored``: entry
    indexes, params ``athena_ignore``), and any copy of it, is not listed."""
    stems = {g["group_id"]: [normalise_name(s) for s in g.get("_stems") or ()] for g in groups if takes_part(g)}
    bases = {gid: base_names(gstems) for gid, gstems in stems.items()}
    tied = set(tied) | set(ignored)
    _key = _merge_key

    # a copy of a tied merge (the same label and data in another project) is the same merge: tied too
    tied_keys = {_key(entries[i]) for i in tied if 0 <= i < len(entries)}
    items: dict[tuple, dict] = {}
    for idx, e in enumerate(entries):
        if (idx in tied or _key(e) in tied_keys or not is_scientist_merge(e) or is_reference_channel(e)
                or _hits(e, stems, bases)):
            continue
        key = _key(e)
        item = items.get(key)
        if item is None:
            item = items[key] = {"athena_label": str(e.get("label") or ""), "is_merge": bool(e.get("is_merge")),
                                 "merge_name": merge_own_name(e), "in": [], "_entry": e}
        item["in"].append({"prj_relative_path": e["prj_relative_path"], "athena_group": e["group_name"]})
    said_no: dict[tuple, set] = {}
    for i, gids in (not_this or {}).items():
        if 0 <= i < len(entries):
            said_no.setdefault(_key(entries[i]), set()).update(gids)
    out = []
    for key, item in items.items():
        e = item.pop("_entry")
        no = said_no.get(key) or set()
        item["candidates"] = [c for c in near_name_candidates(e, groups) if c["group_id"] not in no]
        if no:
            item["not_this_group"] = sorted(no)
        item["hint_rule"] = UNMATCHED_HINT_RULE_ID
        out.append(item)
    out.sort(key=lambda i: (not i["candidates"], i["athena_label"].casefold(), i["in"][0]["prj_relative_path"]))
    return out


_RANGE = re.compile(r"^(\d+)\s*-\s*(\d+)$")


def scan_selection(label: str, stems: Sequence[str]) -> list[int] | None:
    """Scan numbers a scientist's Athena label selects after the run stem (``..._5-6`` ->
    [5, 6]; ``..._1-3_7`` -> [1, 2, 3, 7]; XDAC ``...A.003`` -> [3], whether or not the stem
    ends in ``A``: ``<stem>_A.003`` is that run's scan file 3); None when the label states no
    selection."""
    got = _selection_of_run(label, stems)
    return got[1] if got else None


def _selection_of_run(label: str, stems: Sequence[str]) -> tuple[int, list[int]] | None:
    """``(position in stems of the run the label names, its scan selection)`` (:func:`scan_selection`), else None.
    r3-d L-5: the longest stem is tried first, so ``x_dry_2_003`` is scan 3 of run ``x_dry_2``, never scans 2 and 3 of
    run ``x_dry`` (stems of one length keep their order)."""
    raw = PurePosixPath(str(label)).name
    raw = _EXT.sub("", raw)
    low = raw.casefold()
    for k, stem in sorted(enumerate(stems), key=lambda ks: -len(str(ks[1]))):
        st = str(stem).casefold()
        if not st or not low.startswith(st) or len(low) == len(st) or low[len(st)] not in "_-. ":
            continue
        xdc = _XDC_SCAN_FILE_RAW.match(raw[len(st) :])
        if xdc:
            return k, [int(xdc.group(1))]
        rest = raw[len(st) + 1 :]
        out: list[int] = []
        for tok in re.split(r"[_,\s.]+", rest):
            if not tok:
                continue
            m = _RANGE.match(tok)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                if b < a or b - a > 500:
                    return None
                out.extend(range(a, b + 1))
            elif tok.isdecimal():  # c14m LOW-3: "²".isdigit() is true, and int("²") raises
                out.append(int(tok))
            else:
                return None
        return (k, sorted(set(out))) if out else None
    return None


# --- comparing --------------------------------------------------------------------------------


def compare(isaac: Mapping, entry: Mapping, params: Mapping, np) -> dict:
    """ISAAC protocol vs the scientist's Athena normalisation."""
    tol = params["athena"]
    flatten = entry["params"].get("flatten")
    quantity = "flat" if (flatten is None or float(flatten or 0) >= 0.5) else "norm"
    ref = {
        "prj_relative_path": entry["prj_relative_path"],
        "prj_source_id": entry["prj_source_id"],
        "athena_group": entry["group_name"],
        "athena_label": entry["label"],
        "match_rule": MATCH_RULE_ID,
        "match_kind": entry.get("_match_kind"),
        **({"merge_rule": SCIENTIST_MERGE_RULE_ID} if entry.get("_match_kind") == "scientist_merge" else {}),
        # r6 G1: named for this group by the scientist (params athena_match), never by a near name
        **({"named_by": "params athena_match"} if entry.get("_match_kind") == TIED_KIND else {}),
        **({"athena_data": "already_normalized", "athena_data_rule": ALREADY_NORMALIZED_RULE_ID} if already_normalized(entry) else {}),
    }
    out = {"athena_ref": ref, "rule_id": COMPARE_RULE_ID, "metrics": {}, "verdict": "not_comparable", "flags": [], "tolerances": dict(tol)}
    if not frame_known(entry):
        out["flags"].append(ENERGY_FRAME_UNKNOWN_FLAG)
        out["non_finite_values"] = list(entry.get("non_finite_values") or ())
        return out
    if not plausible(entry):
        # NEVER COMPARE A BROKEN CURVE: the reproduced normalisation is not the scientist's spectrum
        bad = entry["edge_step_implausible"]
        out["flags"].append(EDGE_STEP_IMPLAUSIBLE_FLAG)
        out["metrics"] = {"e0_athena_eV": entry["e0_eV"], "edge_step_athena": entry["edge_step"],
                          **{k: bad[k] for k in ("ratio", "pre_edge_mean", "post_edge_mean") if k in bad}}
        if "ratio" in out["metrics"]:
            out["metrics"]["edge_step_to_range"] = out["metrics"].pop("ratio")
        out["reason"] = f"The scientist's Athena normalisation was not compared: {bad['statement']}"
        return out
    grid = isaac.get("grid")
    y = isaac.get(quantity)
    if grid is None or y is None:
        out["flags"].append("isaac_normalization_unavailable")
        return out
    ae, ay = entry["energy"], entry[quantity]
    lo, hi = max(float(grid[0]), float(ae[0])), min(float(grid[-1]), float(ae[-1]))
    sel = (grid >= lo) & (grid <= hi)
    npts = int(np.sum(sel))
    m = out["metrics"]
    m.update(
        {
            "compared_quantity": quantity,
            "overlap_points": npts,
            "overlap_eV": [lo, hi] if hi > lo else None,
            "e0_isaac_eV": isaac.get("e0_eV"),
            "e0_athena_eV": entry["e0_eV"],
            "e0_delta_eV": (isaac["e0_eV"] - entry["e0_eV"]) if isaac.get("e0_eV") is not None and entry["e0_eV"] is not None else None,
            "edge_step_isaac": isaac.get("edge_step"),
            "edge_step_athena": entry["edge_step"],
            # an already-normalised curve has step 1 by definition: a ratio would only restate ISAAC's step
            "edge_step_ratio": (isaac["edge_step"] / entry["edge_step"]) if isaac.get("edge_step") and entry["edge_step"] and not already_normalized(entry) else None,
        }
    )
    if npts < int(tol["min_overlap_points"]) or (hi - lo) < float(tol["min_overlap_eV"]):
        out["flags"].append("overlap_too_small")
        return out
    diff = y[sel] - np.interp(grid[sel], ae, ay)
    rms = float(np.sqrt(np.mean(diff**2)))
    m["rms_norm"] = rms if math.isfinite(rms) else None
    if m["rms_norm"] is None or m["e0_delta_eV"] is None:
        out["flags"].append("metric_not_finite")
        return out
    lo_r, hi_r = tol["edge_step_ratio_range"]
    if not already_normalized(entry) and (m["edge_step_ratio"] is None or not (lo_r <= m["edge_step_ratio"] <= hi_r)):
        out["flags"].append("edge_step_scale_differs")
    agree = abs(m["e0_delta_eV"]) <= float(tol["agree_e0_delta_eV"]) and rms <= float(tol["agree_rms_norm"])
    out["verdict"] = "agree" if agree else "differs"
    if abs(m["e0_delta_eV"]) > float(tol["agree_e0_delta_eV"]):
        out["flags"].append("e0_differs")
    if rms > float(tol["agree_rms_norm"]):
        out["flags"].append("normalized_shape_differs")
    return out
