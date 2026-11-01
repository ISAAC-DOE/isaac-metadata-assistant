"""Polish r2-a: findings from a real-data run on an SSRL Pt L3 HERFD beamtime (223 SPEC runs). SYNTHETIC only: every
scan, name and value below is invented (``SYN_``/ZZ); the HERFD-like spectrum is an arctan edge plus a Gaussian white
line, not a measurement.

* (MED 1) With 4-5 scans the glitch check flagged points at E0 and on the white line (a sub-eV jitter between scans
  moves the steepest points by many robust scales): flagged points within 5 eV of E0 or where the merged curve is
  steep are listed apart and said as points on the edge, not glitches. The stored count, flag and verdict are those
  first written (qc.json is hashed into the result id), so no result id moves.
* (MED 2) A potentiostatic group with no set-point and no confirmed scale: the minimum said 1 answer (the set-point)
  and asked for the scale only after it. Both are named and counted now, and the scale question blocks the group.
* (MED 3) The counter question (order-critical: confirmed groups cannot be joined later) came 28th of 43 in the
  experiment scope. While open it sorts first in every scope that lists it, and the minimum names it
  (``answer_first``) before any group is confirmed. No id changes.
* (LOW 1) ``--e0-measured`` on a result not flagged ``athena_e0_possibly_fixed`` was accepted silently: refused now,
  nothing recorded.
* (LOW 2) Export said "Wrote 7 record(s)" when every record was ``unchanged``: it says how many are ready, how many
  unchanged and how many written.
"""

from __future__ import annotations

import io
import json
import shlex
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

from test_local_import_records import (  # noqa: F401  (fixtures)
    BY, _cand, _decide_everything, _miss, _portal, bdir, fake_upstream, pristine)
from test_local_import_reader_ssrl_xdc import make_scan

POT = "context.electrochemistry.potential_setpoint_V"
SCALE = "context.electrochemistry.potential_scale"


def _quiet(*argv: str) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        rc = cli.main(list(argv))
    return rc, buf.getvalue()


def _questions(bdir_: Path, *extra: str) -> dict:
    rc, out = _quiet("bundle", "questions", str(bdir_), *extra)
    assert rc == 0, out
    return json.loads(out)


def _proc():
    pytest.importorskip("numpy", reason="needs the optional `processing` extra (numpy)")
    pytest.importorskip("larch", reason="needs the optional `processing` extra (xraylarch)")
    import test_local_import_processing as T

    return T


# --- MED 1: flagged points on the edge are not glitches ----------------------------------------------------------

SYN_E0 = 11564.0  # an invented edge position near a Pt L3 edge (eV)


def _herfd_grid(np):
    return np.concatenate([np.arange(11500.0, 11550.0, 2.0), np.arange(11550.0, 11590.0, 0.25), np.arange(11590.0, 11700.0, 1.0)])


def _herfd(np, e, *, shift=0.0, white_line=1.0):
    """A HERFD-like curve: a sharp arctan edge with a tall, narrow white line just above it (invented shape)."""
    x = e - shift
    return 0.05 + (0.5 + np.arctan((x - SYN_E0) / 0.7) / np.pi) + white_line * 1.8 * np.exp(-0.5 * ((x - SYN_E0 - 1.6) / 1.1) ** 2)


def _herfd_scans(np, e, *, spike_at=None):
    """Five scans; the third sits 0.2 eV off the others (energy jitter), heights vary by 2 %; optionally one spike."""
    M = np.vstack([_herfd(np, e, shift=(0.2 if s == 2 else 0.0), white_line=1 + 0.02 * (s - 2))
                   + np.random.default_rng(s).normal(0, 0.003, e.size) for s in range(5)])
    if spike_at is not None:
        M[3, int(np.searchsorted(e, spike_at))] += 0.3
    return M


def test_flagged_points_at_e0_and_on_the_white_line_are_on_the_edge():
    T = _proc()
    np = T.np
    from isaac_api.local_import.processing import core as C

    e = _herfd_grid(np)
    M = _herfd_scans(np, e, spike_at=11578.75)
    dg = C.deglitch(M, e, T.P.resolve_params(), np)
    assert dg["method"] == "cross_scan_median" and dg["flagged_points_total"] >= 3  # the edge IS flagged (stored as before)
    mean = C.merge(M, np=np)["mean"]
    points = C.glitch_points_on_edge(dg["point_flags"], e, e, mean, SYN_E0, np)
    assert len(points) == dg["flagged_points_total"]
    on = [en for _, en, edge in points if edge]
    off = [en for _, en, edge in points if not edge]
    assert on and all(abs(en - SYN_E0) <= 5.0 for en in on)
    assert off == [pytest.approx(11578.75)]  # a real spike off the edge stays a glitch
    # a spike ON a flat stretch is never made "steep" by itself: its own point is left out of its slope
    flat = np.linspace(0.0, 1.0, 50)
    spiky = flat.copy()
    spiky[30] += 5.0
    flags = np.zeros((1, 50), dtype=bool)
    flags[0, 30] = True
    assert C.glitch_points_on_edge(flags, np.arange(50.0), np.arange(50.0), spiky, None, np) == [(0, 30.0, False)]


def test_processing_lists_points_on_the_edge_apart_and_keeps_the_hashed_files(tmp_path):
    T = _proc()
    np = T.np
    e = _herfd_grid(np)
    M = _herfd_scans(np, e)
    i0 = np.full(e.size, 1.0e5)
    scans = [T.spec_file({"energy": e, "I0": i0, "vortDT": M[s] * i0 * 0.01}) for s in range(5)]
    bdir_, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", scans, {"sample_name": "ZZ1"})])
    r = T.isaac(T.run_process(bdir_, source_root=root))
    m = r["qc"]["metrics"]
    # stored as first written: the count, the reason and the verdict
    assert m["glitch_points"] >= 3 and r["qc"]["verdict"] == "warn" and "glitches_flagged" in r["qc"]["reasons"]
    assert m["glitch_points_on_edge"] == m["glitch_points"] and m["glitch_points_off_edge"] == 0
    said = r["qc"]["statements"]["glitch_points_on_edge"]
    assert f"{m['glitch_points']} of the {m['glitch_points']} flagged points lie on the edge" in said
    assert "points on the edge, not counted as glitches" in said and "(01_SYN_ZZ1_003.dat)" in said  # the jittered scan
    assert "No point off the edge is flagged" in said and "within 5 eV of E0" in said
    step = T.step(r, "deglitch")["outcome"]
    assert len(step["flagged_points_on_edge"]) == m["glitch_points"]
    assert all(abs(p["energy_eV"] - r["outputs"]["e0_eV"]) <= 5.0 for p in step["flagged_points_on_edge"])
    qc_file = next(f for f in r["outputs"]["files"] if f["role"] == "qc")
    text = (bdir_ / qc_file["relative_path"]).read_text()
    assert "on_edge" not in text and "glitches_flagged" in text  # hashed: no id moves
    # the compact row carries the split beside the stored count
    from isaac_api.local_import import cli

    row = cli._row("processing-results", r)
    assert row["metrics"]["glitch_points_on_edge"] == m["glitch_points"] and row["metrics"]["glitch_points_off_edge"] == 0


def test_a_result_with_no_point_on_the_edge_is_unchanged(tmp_path):
    T = _proc()
    bdir_, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", [T.spec_file(T.fluo_scan(s, spike=(300 if s == 1 else None))) for s in range(4)],
                                             {"sample_name": "ZZ1"})])
    r = T.isaac(T.run_process(bdir_, source_root=root))
    assert r["qc"]["metrics"]["glitch_points"] >= 1  # the spike sits 84 eV above the edge
    assert "glitch_points_on_edge" not in r["qc"]["metrics"] and "glitch_points_on_edge" not in (r["qc"].get("statements") or {})
    assert "flagged_points_on_edge" not in T.step(r, "deglitch")["outcome"]


# --- MED 2: a set-point and its scale are asked together -------------------------------------------------------


def _potentiostatic_no_setpoint(bdir_: Path) -> None:
    _decide_everything(bdir_)
    b = M.load(bdir_)
    M.decide(bdir_, target_ids=[_miss(b, B.CONTROL_MODE_PATH, "run-001")], decision="correct", value="potentiostatic", **BY)


def test_the_minimum_names_and_counts_the_setpoint_and_its_scale_together(bdir):
    _potentiostatic_no_setpoint(bdir)
    qs = _questions(bdir, "--scope", "group:g1", "--blocking-only")
    minimum = qs["minimum_for_one_group"]
    assert minimum["group_id"] == "g1"
    assert minimum["missing_required_now"] == [POT, SCALE]
    assert minimum["blocking_questions"] == 2 and len(minimum["questions"]) == 2
    by_field = {e["fields"][0]: e for e in minimum["questions"]}
    assert set(by_field) == {POT, SCALE}
    assert "asked now with it, so the scientist is not asked twice" in by_field[SCALE]["required_because"][SCALE]
    assert f"--field {SCALE}" in by_field[SCALE]["command"]
    # the scale question blocks this group now, so --blocking-only lists it beside the set-point's
    listed = {q["question_id"]: q for q in qs["questions"]}
    assert by_field[SCALE]["question_id"] in listed and listed[by_field[SCALE]["question_id"]]["blocking"] is True
    assert by_field[POT]["question_id"] in listed

    # answer the scale first, with the command the minimum named: only the set-point is left, counted once
    argv = shlex.split(by_field[SCALE]["command"].replace("<bundle_dir>", str(bdir))
                       .replace("<one of its allowed values>", "RHE").replace("<your name>", "Synthetic Scientist"))
    assert _quiet(*argv[1:])[0] == 0
    after = _questions(bdir, "--scope", "group:g1", "--blocking-only")["minimum_for_one_group"]
    assert after["missing_required_now"] == [POT] and after["blocking_questions"] == 1


def test_a_confirmed_setpoint_still_names_only_the_scale(bdir):
    # the c12-q state is unchanged: a confirmed set-point held back by its scale names the scale alone
    _potentiostatic_no_setpoint(bdir)
    M.decide(bdir, target_ids=[_cand(M.load(bdir), POT, "run-001")["candidate_id"]], decision="confirm", value=None, **BY)
    minimum = _questions(bdir, "--scope", "group:g1", "--blocking-only")["minimum_for_one_group"]
    assert minimum["missing_required_now"] == [SCALE] and minimum["blocking_questions"] == 1


# --- MED 3: the counter question comes first ---------------------------------------------------------------------

RUNS = ("01_SYNelS_015", "01_SYNelS_016", "03_SYNmofA_dry_017", "03_SYNmofA_dry_018")  # last tokens at 3 and 4


@pytest.fixture()
def counter_bundle(tmp_path) -> Path:
    src = tmp_path / "SYN_bt"
    for name in RUNS:
        make_scan(src / f"{name}_A.001", free_text=("SYNTHETIC comment line",))
    out = tmp_path / "b"
    assert _quiet("import", str(src), "--out", str(out))[0] == 0
    assert _quiet("bundle", "group", str(out))[0] == 0
    return out


def _ids(page: dict) -> list[str]:
    return [q["question_id"] for q in page["questions"]]


def test_the_open_counter_question_sorts_first_in_every_scope_that_lists_it(counter_bundle):
    payload = Q.consolidate(M.load(counter_bundle))
    every = [q["question_id"] for q in payload["questions"]]
    assert every[0] == Q.COUNTER_QUESTION_ID and any(q["blocking"] for q in payload["questions"])
    assert payload["questions"][0]["tier"] == Q.TIER_CONFLICT  # its tier and id are unchanged; only its place
    exp = _questions(counter_bundle, "--scope", "experiment", "--with-targets")
    assert _ids(exp)[0] == Q.COUNTER_QUESTION_ID
    gid = M.load(counter_bundle)["record_groups"][0]["group_id"]
    grp = _questions(counter_bundle, "--scope", f"group:{gid}", "--with-targets")
    assert _ids(grp)[0] == Q.COUNTER_QUESTION_ID
    # the minimum names it before any group is confirmed, not counted
    minimum = grp["minimum_for_one_group"]
    first = minimum["answer_first"]
    assert first["question_id"] == Q.COUNTER_QUESTION_ID and "before confirming any group" in first["why"]
    assert "set_counter_positions" in first["answer_command"]
    assert all(e["question_id"] != Q.COUNTER_QUESTION_ID for e in minimum.get("questions") or ())
    # the same ids, in the same set, before and after: only the order moved
    assert sorted(every) == sorted(q["question_id"] for q in Q.consolidate(M.load(counter_bundle))["questions"])

    # once a group is confirmed, the minimum no longer names it (the skill's order is past)
    M.decide(counter_bundle, target_ids=[gid], decision="confirm", value=None, by="SYNTHETIC TEST", orcid=None)
    assert "answer_first" not in _questions(counter_bundle, "--scope", f"group:{gid}")["minimum_for_one_group"]


def test_a_deferred_or_answered_counter_question_is_not_put_first(counter_bundle):
    M.decide_question(counter_bundle, question_id=Q.COUNTER_QUESTION_ID, decision="defer", value=None, by="SYNTHETIC TEST",
                      orcid=None)
    b = M.load(counter_bundle)
    payload = Q.consolidate(b)
    counter = next(q for q in payload["questions"] if q["question_id"] == Q.COUNTER_QUESTION_ID)
    assert counter.get("deferred") and payload["questions"][0]["question_id"] != Q.COUNTER_QUESTION_ID
    assert "answer_first" not in (Q.minimum_answers_for_one_group(payload, b) or {})
    M.decide(counter_bundle, target_ids=["experiment"], decision=B.NOT_COUNTER_DECISION, value=None, by="SYNTHETIC TEST",
             orcid=None, positions=[3, 4])
    answered = Q.consolidate(M.load(counter_bundle), include_answered=True)
    q = next(q for q in answered["questions"] if q["question_id"] == Q.COUNTER_QUESTION_ID)
    assert q["order_critical"] is False and answered["questions"][0]["question_id"] != Q.COUNTER_QUESTION_ID
    assert not any(q["kind"] == "naming_counter_positions" for q in Q.consolidate(M.load(counter_bundle))["questions"])


# --- LOW 1: --e0-measured only answers the fixed-E0 flag ---------------------------------------------------------


def test_e0_measured_on_a_result_without_the_flag_is_refused_and_records_nothing(tmp_path, capsys):
    from test_local_import_polish_r1a import _processing, _versions_case

    _processing()
    processed, root = _versions_case(tmp_path)
    M.process(processed, source=str(root))
    capsys.readouterr()
    b = M.load(processed)
    r = next(r for r in b.get("processing_results") or ()
             if r.get("outputs") and "athena_e0_possibly_fixed" not in (r.get("review_flags") or ()))
    pid = B.processing_id(r)
    before = len(b.get("scientist_decisions") or ())
    with pytest.raises(M.MutationRefused, match="does not carry that flag") as exc:
        M.decide(processed, target_ids=[pid], decision="approve", value=None, qc_status="valid", e0_measured=True, **BY)
    assert "athena_e0_possibly_fixed" in str(exc.value) and "Nothing was recorded." in str(exc.value)
    assert len(M.load(processed).get("scientist_decisions") or ()) == before
    # without the statement the same approval goes through
    assert pid in M.decide(processed, target_ids=[pid], decision="approve", value=None, qc_status="valid", **BY)["recorded"]


# --- LOW 2: an export of unchanged records says so -------------------------------------------------------------


def test_an_export_of_unchanged_records_says_nothing_new_was_written(bdir, tmp_path):
    from isaac_api.local_import import records as R

    _decide_everything(bdir)
    out = tmp_path / "records"
    first = R.export_records(bdir, out, run_portal=_portal("publish"))
    n = first["records_written"]
    assert n >= 1 and first["records_unchanged"] == 0
    assert first["outcome"].startswith(f"{n} record(s) ready (0 unchanged since their export, {n} written), refused ")
    again = R.export_records(bdir, out, run_portal=_portal("publish"))
    assert again["records_written"] == n and again["records_unchanged"] == n
    assert {row["export"] for row in again["exported"]} == {"unchanged"}
    assert again["outcome"].startswith(f"{n} record(s) ready ({n} unchanged since their export, 0 written), refused ")
    assert "Wrote" not in again["outcome"]
    assert R.export_outcome(3, 0, 0, out, unchanged=1, replaced=1).startswith(
        "3 record(s) ready (1 unchanged since their export, 2 written, 1 of them replacing an earlier record), refused 0")
