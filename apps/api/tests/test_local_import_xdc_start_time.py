"""Beamline 4-3 style SSRL XDC 4.0 scans: the scan start time, the instrument clock's zone, UTC.

What these pin (rule ``ssrl_xdc_scan_start_v1``, decision ``set_clock_time_zone``, conversion
``local_clock_to_utc_via_confirmed_zone_v1``):

* one ``timestamps.acquired_start_utc`` candidate per XDC run, its start the EARLIEST parsed line-2
  time, every usable scan kept as evidence, scan-index/time order disagreement NOTED, never fixed;
  an unparsed or weekday-mismatched time is not used;
* with no zone decision the candidate has no value, is not proposable for a specific reason,
  cannot be confirmed, and ONE beamtime question asks for the zone WITHOUT suggesting one;
* a zone value must be an IANA name (or UTC): offsets, abbreviations, unknown names and
  non-strings are refused;
* a zone converts the local time DST-aware; a fall-back (ambiguous) or spring-forward
  (nonexistent) time gets NO value and says which;
* a confirmation is BOUND to the zone it was made under: a later zone change makes the candidate
  ineligible until it is confirmed again;
* the composed draft carries the file literal, the confirmation, and the zone confirmation;
* other generic profiles produce no such candidate; every bundle written is schema-valid.

SYNTHETIC files only: every scan below is invented, dated 2099, named ``SYN_``.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

from test_local_import_reader_ssrl_xdc import make_scan
from test_local_import_reader_two_column import make_two
from test_local_import_reader_xdi import make_xdi

BY = "SYNTHETIC TEST"
LA = "America/Los_Angeles"
NY = "America/New_York"
PATH = "timestamps.acquired_start_utc"


def stamp(iso: str) -> str:
    """The header's own format, with the weekday the date really falls on."""
    return datetime.fromisoformat(iso).strftime("%a %b %d %H:%M:%S %Y")


def _import(tmp_path: Path, scans: dict[str, str], *, extra=None) -> Path:
    """``scans``: file name -> line-2 literal. Returns the bundle dir (schema-checked)."""
    src = tmp_path / "src" / "SYN_bt"
    for name, literal in scans.items():
        make_scan(src / name, timestamp=literal)
    if extra:
        extra(src)
    out = tmp_path / "out"
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    _valid(out)
    return out


def _valid(out: Path) -> dict:
    data = json.loads((out / "bundle.json").read_text())
    assert B.validate_bundle(data) == []
    return data


def _starts(bundle: dict) -> list[dict]:
    return [c for c in bundle["candidates"] if B.is_local_clock_start(c)]


def _start_of(bundle: dict, label: str) -> dict:
    rid = next(r["run_id"] for r in bundle["runs"] if r["label"] == label)
    [c] = [c for c in _starts(bundle) if c["run_id"] == rid]
    return c


def _zone(out: Path, zone, by: str = BY) -> dict:
    result = M.decide(out, target_ids=["experiment"], decision="set_clock_time_zone", value=zone, by=by, orcid=None)
    _valid(out)
    return result


def _confirm(out: Path, cid: str) -> dict:
    result = M.decide(out, target_ids=[cid], decision="confirm", value=None, by=BY, orcid=None)
    _valid(out)
    return result


# --- the candidate --------------------------------------------------------------------------


def test_one_candidate_per_run_continuing_the_candidate_sequence(tmp_path):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45"), "SYN_alpha_A.002": stamp("2099-07-14T10:40:00"),
                             "SYN_beta_A.001": stamp("2099-01-15T08:00:00")})
    b = _valid(out)
    starts = _starts(b)
    assert len(starts) == len([r for r in b["runs"] if r["source_type"] == B.XDC_RUN_SOURCE_TYPE]) == 2
    ids = [c["candidate_id"] for c in b["candidates"]]
    assert ids == [f"cand-{i:04d}" for i in range(1, len(ids) + 1)]  # the sequence continues, no gaps
    for c in starts:
        run = next(r for r in b["runs"] if r["run_id"] == c["run_id"])
        assert c["candidate_id"] in run["candidate_ids"]
        assert (c["statement_key"], c["target_field_path"], c["scope"], c["target_write_scope"]) == (
            "acquisition_timestamp", PATH, "run", "run")
        assert c["rule"].startswith(B.XDC_START_RULE_ID) and "EARLIEST" in c["rule"]
        assert c["kind"] == "field" and c["state_basis"]["determinism"] == "deterministic"
    # a run with a start-time candidate no longer has a "no source states it" missing value for it
    assert not [m for m in b["missing_values"] if m["target_field_path"] == PATH]
    assert b["counts"]["candidates"] == len(b["candidates"])
    # the timestamp statements stay extended context, exactly as before
    assert [e for e in b["extended_context"] if e["concept"] == "timestamp" and e["official_path"] is None]


def test_the_start_is_the_earliest_scan_and_every_scan_is_evidence(tmp_path):
    lits = [stamp("2099-07-14T09:00:00"), stamp("2099-07-14T09:30:00"), stamp("2099-07-14T10:00:00")]
    out = _import(tmp_path, {f"SYN_alpha_A.00{i + 1}": lit for i, lit in enumerate(lits)})
    c = _start_of(_valid(out), "SYN_alpha")
    assert [e["literal_value"] for e in c["evidence"]] == lits  # verbatim, scan-index order
    assert [e["relative_path"] for e in c["evidence"]] == ["SYN_alpha_A.001", "SYN_alpha_A.002", "SYN_alpha_A.003"]
    assert [e["relation"] for e in c["evidence"]] == ["supports", "context", "context"]
    for e in c["evidence"]:
        assert (e["locator"], e["method"], e["method_id"]) == ("line:2", "deterministic_parser", B.XDC_START_RULE_ID)
        assert e["source_id"] is not None
    assert c["local_clock"]["local_time"] == "2099-07-14T09:00:00" and c["local_clock"]["start_rule"] == "earliest"
    assert c["local_clock"]["order_note"] is None and c["local_clock"]["scans_used"] == 3
    assert c["evidence_total"] == 3 and c["evidence_truncated"] is False


def test_scan_index_and_time_order_disagreeing_is_noted_never_reordered(tmp_path):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T11:00:00"), "SYN_alpha_A.002": stamp("2099-07-14T09:15:00")})
    b = _valid(out)
    c = _start_of(b, "SYN_alpha")
    assert [e["relative_path"] for e in c["evidence"]] == ["SYN_alpha_A.001", "SYN_alpha_A.002"]  # index order kept
    assert [e["relation"] for e in c["evidence"]] == ["context", "supports"]
    assert c["local_clock"]["local_time"] == "2099-07-14T09:15:00"
    assert "not in scan-index order" in c["local_clock"]["order_note"] and "nothing was reordered" in c["local_clock"]["order_note"]
    run = next(r for r in b["runs"] if r["run_id"] == c["run_id"])
    assert any(a["kind"] == "scan_time_order_differs_from_index_order" for a in run["other_relationships"]["anomalies"])


def test_an_unparsed_or_weekday_mismatched_time_is_not_used(tmp_path):
    out = _import(tmp_path, {
        "SYN_alpha_A.001": "not a time at all",
        "SYN_alpha_A.002": "Mon Jul 14 08:00:00 2099",  # 14 July 2099 is a Tuesday
        "SYN_alpha_A.003": stamp("2099-07-14T10:00:00"),
        "SYN_gamma_A.001": "garbled",
    })
    b = _valid(out)
    c = _start_of(b, "SYN_alpha")
    assert [e["relative_path"] for e in c["evidence"]] == ["SYN_alpha_A.003"]
    assert c["local_clock"]["local_time"] == "2099-07-14T10:00:00"  # the earlier, mismatched 08:00 is NOT the start
    excluded = {x["relative_path"]: x["reason"] for x in c["local_clock"]["excluded_scans"]}
    assert set(excluded) == {"SYN_alpha_A.001", "SYN_alpha_A.002"}
    assert "does not parse" in excluded["SYN_alpha_A.001"] and "weekday" in excluded["SYN_alpha_A.002"]
    run = next(r for r in b["runs"] if r["run_id"] == c["run_id"])
    assert {"timestamp_unparsed", "timestamp_weekday_mismatch"} <= {a["kind"] for a in run["other_relationships"]["anomalies"]}
    # a run with no usable time gets no candidate: its start stays a missing value
    gamma = next(r for r in b["runs"] if r["label"] == "SYN_gamma")
    assert not [x for x in _starts(b) if x["run_id"] == gamma["run_id"]]
    assert [m for m in b["missing_values"] if m["target_field_path"] == PATH and m["run_id"] == gamma["run_id"]]


def test_other_generic_profiles_produce_no_start_time_candidate(tmp_path):
    src = tmp_path / "src"
    make_two(src / "SYN_cell.txt")
    make_xdi(src / "SYN_ref.xdi")
    out = tmp_path / "out"
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    b = _valid(out)
    assert b["runs"] and not [r for r in b["runs"] if r["source_type"] == B.XDC_RUN_SOURCE_TYPE]
    assert _starts(b) == [] and not [c for c in b["candidates"] if c["target_field_path"] == PATH]
    assert not [q for q in b["questions"] if q["kind"] == "confirm_clock_time_zone"]
    assert not [q for q in Q.consolidate(b)["questions"] if q["kind"] == "clock_time_zone"]


# --- no zone ----------------------------------------------------------------------------------


def test_without_a_zone_there_is_no_value_no_proposal_no_confirm_and_one_question(tmp_path, capsys):
    lit = stamp("2099-07-14T10:23:45")
    out = _import(tmp_path, {"SYN_alpha_A.001": lit, "SYN_beta_A.001": stamp("2099-07-15T10:00:00")})
    b = _valid(out)
    c = _start_of(b, "SYN_alpha")
    assert c["value"] is None and c["value_state"] == B.STATE_NEEDS_REVIEW
    assert c["state_basis"]["proposable"] is False
    reason = c["state_basis"]["not_proposable_reason"]
    for words in ("local clock time", "names no time zone", "states no epoch", "time zone the instrument clock",
                  "--decision set_clock_time_zone"):
        assert words in reason
    assert c["local_clock"]["status"] == B.LOCAL_CLOCK_AWAITING and c["local_clock"]["zone"] is None
    assert c["eligibility_for_official_record"]["eligible"] is False
    with pytest.raises(M.MutationRefused, match="set_clock_time_zone"):
        M.decide(out, target_ids=[c["candidate_id"]], decision="confirm", value=None, by=BY, orcid=None)
    with pytest.raises(M.MutationRefused, match="takes no --value.*--decision correct"):
        M.decide(out, target_ids=[c["candidate_id"]], decision="confirm", value="2099-07-14T17:23:45Z", by=BY, orcid=None)
    assert _valid(out)["scientist_decisions"] == []
    # the fine-grained question never offers the LOCAL literal as an answer for a *_utc field
    [v1] = [q for q in b["questions"] if q["kind"] == "confirm_value" and q["target"]["id"] == c["candidate_id"]]
    assert v1["options"] == [] and "waits on the instrument clock's time zone" in v1["prompt"]
    # ONE beamtime question, v1 and consolidated; it suggests NOTHING
    [q1] = [q for q in b["questions"] if q["kind"] == "confirm_clock_time_zone"]
    assert q1["target"] == {"kind": "experiment", "id": "experiment"} and q1["options"] == [] and q1["run_id"] is None
    [q] = [q for q in Q.consolidate(b)["questions"] if q["kind"] == "clock_time_zone"]
    assert q["scope"] == "experiment" and q["allowed_decisions"] == ["set_clock_time_zone"]
    assert q["suggested_value"] is None and q["allowed_values"] is None
    assert q["applies_to"]["runs"] == 2 and "2 run(s)" in q["text"]
    assert lit in q["text"] and "SYN_alpha_A.001" in q["text"]
    assert "No file in this import states the clock's time zone" in q["text"]
    assert "--decision set_clock_time_zone" in q["text"] and "--decision set_clock_time_zone" in q["answer_command"]
    assert "Los_Angeles" not in json.dumps(q) and "Pacific" not in json.dumps(q)  # never guessed from the facility
    # nothing to confirm yet, so no confirm question about the start times
    assert not [x for x in Q.consolidate(b)["questions"] if x["kind"] == "confirm_value" and x["target_field_path"] == PATH]


@pytest.mark.parametrize(
    "bad, words",
    [("-08:00", "fixed UTC offset"), ("UTC-8", "fixed UTC offset"), ("GMT+8", "fixed UTC offset"),
     ("Etc/GMT+8", "fixed UTC offset"), ("PST", "no Area/Location form"), ("PDT", "no Area/Location form"), ("EST", "no Area/Location form"),
     ("Japan", "no Area/Location form"), ("Etc/UTC", "fixed zone under Etc/"),
     ("Mars/Olympus_Mons", "zoneinfo"), ("", "needs --value"), (None, "needs --value"), (-8, "needs --value"),
     (["America/Los_Angeles"], "needs --value")],
)
def test_a_zone_that_is_not_an_iana_name_is_refused(tmp_path, bad, words):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45")})
    with pytest.raises(M.MutationRefused, match=words.replace("+", r"\+")) as err:
        _zone(out, bad)
    assert "Nothing was recorded" in str(err.value)
    assert _valid(out)["scientist_decisions"] == []


def test_a_bad_zone_is_refused_through_the_cli_too(tmp_path, capsys):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45")})
    capsys.readouterr()
    code = cli.main(["bundle", "decide", str(out), "--target", "experiment", "--decision", "set_clock_time_zone",
                     "--value", "PST", "--by", BY])
    assert code != 0 and _valid(out)["scientist_decisions"] == []
    code = cli.main(["bundle", "decide", str(out), "--target", "experiment", "--decision", "set_clock_time_zone",
                     "--value", "UTC", "--by", BY])
    assert code == 0 and B.clock_zone_decision(_valid(out))["value"] == "UTC"


def test_the_validator_refuses_a_hand_written_bad_zone(tmp_path):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45")})
    _zone(out, LA)
    data = _valid(out)
    data["scientist_decisions"][0]["value"] = "-07:00"
    assert any("fixed UTC offset" in e for e in B.validate_bundle(data))


# --- with a zone ------------------------------------------------------------------------------


def test_a_zone_converts_summer_and_winter_times_dst_aware(tmp_path):
    out = _import(tmp_path, {"SYN_summer_A.001": stamp("2099-07-14T10:23:45"), "SYN_winter_A.001": stamp("2099-01-15T10:23:45")})
    _zone(out, LA)
    b = _valid(out)
    zd = B.clock_zone_decision(b)
    summer, winter = _start_of(b, "SYN_summer"), _start_of(b, "SYN_winter")
    assert summer["value"] == "2099-07-14T17:23:45Z"  # PDT, UTC-7
    assert winter["value"] == "2099-01-15T18:23:45Z"  # PST, UTC-8
    for c in (summer, winter):
        assert c["local_clock"]["status"] == B.LOCAL_CLOCK_CONVERTED
        assert (c["local_clock"]["zone"], c["local_clock"]["zone_decision_id"]) == (LA, zd["decision_id"])
        step = c["evidence"][0]["normalization"][-1]
        assert (step["step"], step["rule_id"], step["zone"], step["zone_decision_id"], step["to"]) == (
            B.LOCAL_CLOCK_CONVERT_STEP, B.CLOCK_ZONE_RULE_ID, LA, zd["decision_id"], c["value"])
        # the reason says why it is not proposable to the WEBSITE; what the conversion did is said elsewhere
        assert c["state_basis"]["not_proposable_reason"] == B.NOT_PROPOSABLE_TO_WEBSITE and c["state_basis"]["proposable"] is False
        assert "website" in c["state_basis"]["not_proposable_summary"]
        expl = c["local_clock"]["explanation"]
        assert B.CLOCK_ZONE_RULE_ID in expl and LA in expl and c["value"] in expl
        [v1] = [q for q in b["questions"] if q["kind"] == "confirm_value" and q["target"]["id"] == c["candidate_id"]]
        assert v1["options"] == [c["value"]] and c["value"] in v1["prompt"]
        assert c["value_state"] == B.STATE_NEEDS_REVIEW  # still a scientist's to confirm
        assert c["eligibility_for_official_record"]["eligible"] is False
    # the question is answered: it is gone, and the start times are now asked to be confirmed
    assert not [q for q in b["questions"] if q["kind"] == "confirm_clock_time_zone"]
    qs = Q.consolidate(b)["questions"]
    assert not [q for q in qs if q["kind"] == "clock_time_zone"]
    assert [q for q in qs if q["kind"] == "confirm_value" and q["target_field_path"] == PATH]
    # the zone decision's wording is about the instrument clock, never "the facility's time zone"
    assert "facility" not in B.CLOCK_ZONE_QUESTION and "instrument clock" in B.CLOCK_ZONE_QUESTION


def test_the_zone_decision_is_idempotent_and_the_latest_one_wins(tmp_path):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45")})
    assert _zone(out, LA)["recorded"] == ["experiment"]
    assert _zone(out, LA)["unchanged"] == ["experiment"]
    assert len(_valid(out)["scientist_decisions"]) == 1
    _zone(out, NY)
    b = _valid(out)
    assert [d["value"] for d in b["scientist_decisions"]] == [LA, NY]  # the earlier one is kept, superseded
    assert _start_of(b, "SYN_alpha")["value"] == "2099-07-14T14:23:45Z"  # EDT, UTC-4


@pytest.mark.parametrize("link", ["US/Pacific", "Asia/Calcutta"])
def test_an_iana_link_in_area_location_form_is_accepted(tmp_path, link):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-01-15T10:00:00")})
    _zone(out, link)
    assert _start_of(_valid(out), "SYN_alpha")["local_clock"]["status"] == B.LOCAL_CLOCK_CONVERTED


def test_utc_is_accepted_and_converts_to_itself(tmp_path):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45")})
    _zone(out, "UTC")
    assert _start_of(_valid(out), "SYN_alpha")["value"] == "2099-07-14T10:23:45Z"


@pytest.mark.parametrize(
    "local, status, word",
    [("2099-11-01T01:30:00", B.LOCAL_CLOCK_AMBIGUOUS, "AMBIGUOUS"), ("2099-03-08T02:30:00", B.LOCAL_CLOCK_NONEXISTENT, "NONEXISTENT")],
)
def test_a_fall_back_or_spring_forward_time_gets_no_value(tmp_path, local, status, word):
    # premise checked, not assumed: in this zone 01:30 on 1 Nov 2099 happens twice and 02:30 on
    # 8 Mar 2099 never happens
    assert B.local_clock_to_utc(local, LA) == (status, None)
    lit = stamp(local)
    out = _import(tmp_path, {"SYN_alpha_A.001": lit})
    _zone(out, LA)
    c = _start_of(_valid(out), "SYN_alpha")
    assert c["value"] is None and c["local_clock"]["status"] == status
    reason = c["state_basis"]["not_proposable_reason"]
    assert reason.startswith(word) and lit in reason and LA in reason and "correct --value" in reason
    assert all(n["step"] != B.LOCAL_CLOCK_CONVERT_STEP for n in c["evidence"][0]["normalization"])
    with pytest.raises(M.MutationRefused, match=word):
        _confirm(out, c["candidate_id"])
    # a scientist may still give the UTC start themselves
    M.decide(out, target_ids=[c["candidate_id"]], decision="correct", value="2099-11-01T09:30:00Z", by=BY, orcid=None)
    c = _start_of(_valid(out), "SYN_alpha")
    assert c["eligibility_for_official_record"]["eligible"] is True


def test_a_correct_with_a_utc_value_needs_no_zone(tmp_path):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45")})
    cid = _start_of(_valid(out), "SYN_alpha")["candidate_id"]
    M.decide(out, target_ids=[cid], decision="correct", value="2099-07-14T17:23:45Z", by=BY, orcid=None)
    c = _start_of(_valid(out), "SYN_alpha")
    assert c["value_state"] == B.STATE_SCIENTIST_CONFIRMED and c["eligibility_for_official_record"]["eligible"] is True
    # a zoneless local time is still refused as a correction (the *_utc rule)
    M.decide(out, target_ids=[cid], decision="correct", value="2099-07-14T10:23:45", by=BY, orcid=None)
    assert _start_of(_valid(out), "SYN_alpha")["eligibility_for_official_record"]["eligible"] is False


def test_bulk_confirmation_is_allowed_once_the_zone_is_set(tmp_path):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45"), "SYN_beta_A.001": stamp("2099-07-15T10:00:00")})
    _zone(out, LA)
    ids = [c["candidate_id"] for c in _starts(_valid(out))]
    result = M.decide(out, target_ids=ids, decision="confirm", value=None, by=BY, orcid=None)
    assert result["recorded"] == ids and result["batch_id"]
    assert all(c["eligibility_for_official_record"]["eligible"] for c in _starts(_valid(out)))


# --- the binding ---------------------------------------------------------------------------------


def test_a_zone_change_after_confirming_makes_it_ineligible_until_confirmed_again(tmp_path):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45")})
    _zone(out, LA)
    cid = _start_of(_valid(out), "SYN_alpha")["candidate_id"]
    _confirm(out, cid)
    b = _valid(out)
    c = _start_of(b, "SYN_alpha")
    [conf] = [d for d in b["scientist_decisions"] if d["decision"] == "confirm"]
    assert conf["value"] is None
    assert conf["clock_zone_binding"] == {"zone": LA, "zone_decision_id": B.clock_zone_decision(b)["decision_id"],
                                          "value": "2099-07-14T17:23:45Z", "rule_id": B.CLOCK_ZONE_RULE_ID}
    assert c["value_state"] == B.STATE_SCIENTIST_CONFIRMED and c["eligibility_for_official_record"]["eligible"] is True
    # the zone changes: the live value changes, and the old confirmation does NOT carry it
    _zone(out, NY)
    c = _start_of(_valid(out), "SYN_alpha")
    assert c["value"] == "2099-07-14T14:23:45Z"
    assert c["value_state"] == B.STATE_SCIENTIST_CONFIRMED  # the confirmation is still on record ...
    elig = c["eligibility_for_official_record"]
    assert elig["eligible"] is False  # ... but it was about another value
    assert "clock time zone changed after it was confirmed" in elig["reason"] and "Confirm it again" in elig["reason"]
    assert LA in elig["reason"] and NY in elig["reason"]
    # re-confirming binds to the new zone and is eligible again
    assert _confirm(out, cid)["recorded"] == [cid]
    c = _start_of(_valid(out), "SYN_alpha")
    assert c["eligibility_for_official_record"]["eligible"] is True
    # a replay is idempotent; going back to the first zone makes the NEW confirmation stale, not the old one valid
    assert _confirm(out, cid)["unchanged"] == [cid]
    _zone(out, LA)
    assert _start_of(_valid(out), "SYN_alpha")["eligibility_for_official_record"]["eligible"] is False


def test_a_hand_made_confirm_without_a_binding_is_not_eligible(tmp_path):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45")})
    _zone(out, LA)
    cid = _start_of(_valid(out), "SYN_alpha")["candidate_id"]
    _confirm(out, cid)
    data = _valid(out)
    del data["scientist_decisions"][-1]["clock_zone_binding"]
    B.apply_derivations(data)
    assert B.validate_bundle(data) == []
    c = _start_of(data, "SYN_alpha")
    assert c["eligibility_for_official_record"]["eligible"] is False
    assert "not under a confirmed instrument-clock time zone" in c["eligibility_for_official_record"]["reason"]


def test_the_validator_re_runs_the_conversion(tmp_path):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45")})
    _zone(out, LA)
    data = _valid(out)
    c = _start_of(data, "SYN_alpha")
    c["value"] = "2099-07-14T10:23:45Z"  # as if the local time were UTC
    c["evidence"][0]["normalization"][-1]["to"] = "2099-07-14T10:23:45Z"
    assert any("is not what ssrl_xdc_scan_start_v1" in e for e in B.validate_bundle(data))
    data = _valid(out)
    _start_of(data, "SYN_alpha")["value"] = None
    assert B.validate_bundle(data)


# --- composition, end to end ------------------------------------------------------------------------


def test_import_group_decide_build_records_composes_the_start_with_three_kinds_of_evidence(tmp_path, capsys):
    lit = stamp("2099-07-14T10:23:45")
    out = _import(tmp_path, {"SYN_alpha_A.001": lit, "SYN_alpha_A.002": stamp("2099-07-14T10:50:00")})
    assert cli.main(["bundle", "group", str(out)]) == 0
    b = _valid(out)
    [group] = [g for g in b["record_groups"] if g["status"] == "proposed"]
    M.decide(out, target_ids=[group["group_id"]], decision="confirm", value=None, by=BY, orcid=None)
    _valid(out)
    [q] = [q for q in Q.consolidate(M.load(out))["questions"] if q["kind"] == "clock_time_zone"]
    capsys.readouterr()
    assert cli.main(["bundle", "decide", str(out), "--question", q["question_id"], "--decision", "set_clock_time_zone",
                     "--value", LA, "--by", BY]) == 0
    b = _valid(out)
    cid = _start_of(b, "SYN_alpha")["candidate_id"]
    _confirm(out, cid)
    result = R.build_records(out)
    _valid(out)
    [d] = result["drafts"]
    draft = json.loads((out / d["draft"]).read_text())
    field = draft["fields"][PATH]
    assert field["value"] == "2099-07-14T17:23:45Z" and field["status"] == "verified"
    docs = [e for e in field["evidence"] if e["source_type"] == "document"]
    confs = [e for e in field["evidence"] if e["source_type"] == "user_confirmation"]
    assert lit in [e["quote"] for e in docs] and {e["locator"] for e in docs} == {"line:2"}
    assert {e["source_file"] for e in docs} == {"SYN_alpha_A.001", "SYN_alpha_A.002"}
    b = _valid(out)
    zone_d = B.clock_zone_decision(b)
    confirm_d = next(x for x in b["scientist_decisions"] if x["decision"] == "confirm" and x["target"]["id"] == cid)
    assert {e["decision_id"] for e in confs} == {confirm_d["decision_id"], zone_d["decision_id"]}
    [zone_e] = [e for e in confs if e["decision_id"] == zone_d["decision_id"]]
    assert zone_e["answer"] == LA and "instrument clock" in zone_e["question"] and zone_e["rule_id"] == B.CLOCK_ZONE_RULE_ID
    [cand_e] = [e for e in confs if e["decision_id"] == confirm_d["decision_id"]]
    assert cand_e["answer"] == "2099-07-14T17:23:45Z"
    # after a zone change the start is no longer composed, and the report says why
    _zone(out, NY)
    draft, report = R.compose_group(M.load(out), next(g for g in M.load(out)["record_groups"] if g["group_id"] == group["group_id"]), out)
    assert PATH not in draft["fields"]
    assert any(x.get("candidate_id") == cid and "changed after it was confirmed" in x["reason"] for x in report["not_composed"])


def test_two_runs_with_different_starts_in_one_group_still_disagree(tmp_path):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:00:00"), "SYN_beta_A.001": stamp("2099-07-14T12:00:00")})
    assert cli.main(["bundle", "group", str(out)]) == 0
    b = _valid(out)
    _zone(out, LA)
    ids = [c["candidate_id"] for c in _starts(_valid(out))]
    M.decide(out, target_ids=ids, decision="confirm", value=None, by=BY, orcid=None)
    b = M.load(out)
    keys = [r["run_key"] for r in b["runs"] if r["source_type"] == B.XDC_RUN_SOURCE_TYPE]
    group = {"group_id": "rg-synthetic", "member_run_keys": keys}
    draft, report = R.compose_group(b, group, out)
    assert PATH not in draft["fields"]
    assert any(x["path"] == PATH for x in report["disagreements"])  # no group-start rule is invented


# --- an older bundle ---------------------------------------------------------------------------------


def test_an_older_xdc_bundle_is_upgraded_saying_it_lacks_the_start_times(tmp_path, capsys):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45")})
    data = _valid(out)
    gone = {c["candidate_id"] for c in _starts(data)}
    data["candidates"] = [c for c in data["candidates"] if c["candidate_id"] not in gone]
    for r in data["runs"]:
        r["candidate_ids"] = [x for x in r["candidate_ids"] if x not in gone]
    data["format_version"] = "1.3.0"  # as a 1.3.0 build would have stored it
    B.refresh_questions(data)
    B.apply_derivations(data)
    assert B.validate_bundle(data) == []
    (out / "bundle.json").write_text(json.dumps(data))
    assert B.import_rules_missing(data) == [(B.XDC_RUN_SOURCE_TYPE, B.XDC_START_RULE_ID)]
    capsys.readouterr()
    _zone(out, LA)  # any write upgrades it
    err = capsys.readouterr().err
    b = _valid(out)
    [u] = b["format_upgrades"]
    assert b["format_version"] == B.FORMAT_VERSION and (u["from_format_version"], u["to_format_version"]) == ("1.3.0", B.FORMAT_VERSION)
    assert B.XDC_START_RULE_ID in u["statement"] and "re-import" in u["statement"] and u["statement"] in err
    _zone(out, NY)
    assert len(_valid(out)["format_upgrades"]) == 1  # logged once


# --- review fixes: bounds, confirm --value, re-read literals, zone change disclosure ----------------


def test_more_scans_than_the_evidence_bound_still_import_and_keep_the_earliest(tmp_path):
    from datetime import timedelta

    base = datetime(2099, 7, 14, 8, 0, 0)
    n = B.MAX_EVIDENCE_PER_CANDIDATE + 4  # 260
    # the LAST scan is the earliest, so it falls outside a plain first-256 window
    scans = {f"SYN_big_A.{i:03d}": stamp((base + timedelta(minutes=n - i)).isoformat()) for i in range(1, n + 1)}
    # a second run: one usable time and more unusable scans than excluded_scans keeps
    scans.update({f"SYN_bad_A.{i:03d}": "garbled" for i in range(1, n)})
    scans[f"SYN_bad_A.{n:03d}"] = stamp("2099-07-14T09:00:00")
    out = _import(tmp_path, scans)
    b = _valid(out)
    big = _start_of(b, "SYN_big")
    assert len(big["evidence"]) == B.MAX_EVIDENCE_PER_CANDIDATE
    assert big["evidence_total"] == n and big["evidence_truncated"] is True
    [sup] = [e for e in big["evidence"] if e["relation"] == "supports"]
    assert sup["relative_path"] == f"SYN_big_A.{n:03d}" and big["local_clock"]["local_time"] == "2099-07-14T08:00:00"
    assert big["variation"]["rows_total"] == n and big["local_clock"]["scans_used"] == n
    bad = _start_of(b, "SYN_bad")
    assert len(bad["local_clock"]["excluded_scans"]) == B.MAX_EVIDENCE_PER_CANDIDATE
    assert bad["local_clock"]["excluded_scans_total"] == n - 1
    _zone(out, LA)
    assert _start_of(_valid(out), "SYN_big")["value"] == "2099-07-14T15:00:00Z"


@pytest.mark.parametrize("local", ["2099-07-14T10:23:45", "2099-11-01T01:30:00"])
def test_confirm_with_a_value_is_refused_and_points_to_correct(tmp_path, local):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp(local)})
    _zone(out, LA)
    cid = _start_of(_valid(out), "SYN_alpha")["candidate_id"]
    with pytest.raises(M.MutationRefused, match="takes no --value.*--decision correct"):
        M.decide(out, target_ids=[cid], decision="confirm", value="2001-01-01T00:00:00Z", by=BY, orcid=None)
    assert [d["decision"] for d in _valid(out)["scientist_decisions"]] == ["set_clock_time_zone"]


def test_a_hand_made_confirm_with_its_own_value_is_never_credited_to_the_zone(tmp_path):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45")})
    _zone(out, LA)
    cid = _start_of(_valid(out), "SYN_alpha")["candidate_id"]
    _confirm(out, cid)
    data = _valid(out)
    data["scientist_decisions"][-1]["value"] = "2001-01-01T00:00:00Z"  # as if `confirm --value` had been accepted
    B.apply_derivations(data)
    c = _start_of(data, "SYN_alpha")
    assert c["eligibility_for_official_record"]["eligible"] is False and "a correction" in c["eligibility_for_official_record"]["reason"]
    # and even if something marked it eligible, the composer would not credit the zone rule with 2001
    c["eligibility_for_official_record"] = {"eligible": True, "reason": "forced by this test"}
    keys = [r["run_key"] for r in data["runs"]]
    draft, _ = R.compose_group(data, {"group_id": "rg-synthetic", "member_run_keys": keys}, out)
    ev = draft["fields"][PATH]["evidence"]
    assert draft["fields"][PATH]["value"] == "2001-01-01T00:00:00Z"
    assert not [e for e in ev if e.get("rule_id") == B.CLOCK_ZONE_RULE_ID or e.get("answer") == LA]


def test_the_validator_re_reads_each_literal_and_checks_the_earliest_supports(tmp_path):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T09:00:00"), "SYN_alpha_A.002": stamp("2099-07-14T10:00:00")})
    _zone(out, LA)
    # (a) the stored local time edited, the literal left alone
    data = _valid(out)
    _start_of(data, "SYN_alpha")["evidence"][0]["normalization"][0]["to"] = "2099-07-14T03:00:00"
    assert any("read_local_clock step does not say what its literal reads" in e for e in B.validate_bundle(data))
    # (b) `supports` moved onto the later scan
    data = _valid(out)
    ev = _start_of(data, "SYN_alpha")["evidence"]
    ev[0]["relation"], ev[1]["relation"] = "context", "supports"
    B.apply_derivations(data)
    assert any("is not the earliest scan time" in e for e in B.validate_bundle(data))
    # (c) a literal whose weekday is wrong
    data = _valid(out)
    w = _start_of(data, "SYN_alpha")["evidence"][1]
    w["literal_value"] = w["normalization"][0]["from"] = "Mon Jul 14 10:00:00 2099"
    assert any("is not a usable line-2 time" in e for e in B.validate_bundle(data))
    # the derivation converts the LITERAL, not the stored step
    data = _valid(out)
    c = _start_of(data, "SYN_alpha")
    c["evidence"][0]["normalization"][0]["to"] = "2099-07-14T03:00:00"
    assert B.local_clock_start(c, B.clock_zone_decision(data))["value"] == "2099-07-14T16:00:00Z"


def test_a_zone_change_says_what_it_undid_in_decide_summary_and_questions(tmp_path, capsys):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45")})
    first = _zone(out, LA)
    assert first["clock_zone"]["confirmations_invalidated_now"] == 0 and "No start-time confirmation" in first["clock_zone"]["statement"]
    cid = _start_of(_valid(out), "SYN_alpha")["candidate_id"]
    _confirm(out, cid)
    capsys.readouterr()
    assert cli.main(["bundle", "decide", str(out), "--target", "experiment", "--decision", "set_clock_time_zone",
                     "--value", NY, "--by", BY]) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    cz = result["clock_zone"]
    assert cz["zone"] == NY and cz["confirmations_invalidated_now"] == 1 and cz["candidate_ids_to_confirm_again"] == [cid]
    assert "1 start-time confirmation(s) made under another zone no longer count" in cz["statement"] and cid in cz["statement"]
    assert cz["statement"] in captured.err
    b = _valid(out)
    zd = B.clock_zone_decision(b)
    summary = (out / "summary.md").read_text()
    assert f"Instrument clock time zone: **{NY}** (decision {zd['decision_id']})" in summary
    assert "1 start-time confirmation(s) no longer count" in summary and cid in summary
    [again] = [q for q in Q.consolidate(b)["questions"] if q.get("reason") == "clock_zone_changed_after_confirmation"]
    assert again["kind"] == "confirm_value" and again["targets"] == [{"kind": "candidate", "id": cid}]
    assert "changed after 1 start time(s) here were confirmed" in again["text"] and "2099-07-14T14:23:45Z" in again["text"]
    [v1] = [q for q in b["questions"] if q["kind"] == "confirm_value" and q["target"]["id"] == cid]
    assert "changed after it was confirmed" in v1["prompt"]
    # answering it through the question restores it, and the question is gone
    assert cli.main(["bundle", "decide", str(out), "--question", again["question_id"], "--decision", "confirm", "--by", BY]) == 0
    b = _valid(out)
    assert _start_of(b, "SYN_alpha")["eligibility_for_official_record"]["eligible"] is True
    assert not [q for q in Q.consolidate(b)["questions"] if q.get("reason") == "clock_zone_changed_after_confirmation"]
    assert "no longer count" not in (out / "summary.md").read_text()


def test_summary_says_when_no_zone_is_stated(tmp_path):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45")})
    assert "Instrument clock time zone: **not stated**" in (out / "summary.md").read_text()


def test_the_binding_checks_the_zone_even_when_the_value_is_the_same(tmp_path):
    # UTC and Europe/London agree in January, so ONLY the zone check can catch this switch
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-01-15T10:00:00")})
    _zone(out, "UTC")
    cid = _start_of(_valid(out), "SYN_alpha")["candidate_id"]
    _confirm(out, cid)
    _zone(out, "Europe/London")
    c = _start_of(_valid(out), "SYN_alpha")
    assert c["value"] == "2099-01-15T10:00:00Z"  # identical value ...
    assert c["eligibility_for_official_record"]["eligible"] is False  # ... different zone
    assert "changed after it was confirmed" in c["eligibility_for_official_record"]["reason"]


def test_the_binding_checks_the_value_even_when_the_zone_is_the_same(tmp_path):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45")})
    _zone(out, LA)
    cid = _start_of(_valid(out), "SYN_alpha")["candidate_id"]
    _confirm(out, cid)
    data = _valid(out)
    data["scientist_decisions"][-1]["clock_zone_binding"]["value"] = "2099-07-14T18:23:45Z"  # same zone, other value
    B.apply_derivations(data)
    c = _start_of(data, "SYN_alpha")
    assert c["eligibility_for_official_record"]["eligible"] is False
    assert "changed after it was confirmed" in c["eligibility_for_official_record"]["reason"]


def test_restating_the_same_zone_keeps_the_confirmation(tmp_path):
    # DELIBERATE: the binding compares zone and value, not the decision id
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45")})
    _zone(out, LA)
    cid = _start_of(_valid(out), "SYN_alpha")["candidate_id"]
    _confirm(out, cid)
    result = _zone(out, LA, by="ANOTHER SYNTHETIC PERSON")
    assert result["recorded"] == ["experiment"] and result["clock_zone"]["confirmations_invalidated_now"] == 0
    b = _valid(out)
    assert len([d for d in b["scientist_decisions"] if d["decision"] == "set_clock_time_zone"]) == 2
    assert _start_of(b, "SYN_alpha")["eligibility_for_official_record"]["eligible"] is True


def test_a_zone_change_into_an_ambiguous_time_asks_for_a_correction_not_a_confirm(tmp_path, capsys):
    lit = stamp("2099-11-01T01:30:00")
    assert lit == "Sun Nov 01 01:30:00 2099"
    out = _import(tmp_path, {"SYN_alpha_A.001": lit})
    _zone(out, "UTC")
    cid = _start_of(_valid(out), "SYN_alpha")["candidate_id"]
    _confirm(out, cid)
    result = _zone(out, LA)  # 01:30 on 1 Nov 2099 happens twice there
    cz = result["clock_zone"]
    assert cz["confirmations_invalidated_now"] == 1 and cz["to_correct"] == [cid] and cz["to_confirm_again"] == []
    assert "1 to correct with a UTC value" in cz["statement"] and "to confirm again" not in cz["statement"]
    b = _valid(out)
    c = _start_of(b, "SYN_alpha")
    assert c["value"] is None and "Correct it with the UTC start" in c["eligibility_for_official_record"]["reason"]
    assert "Confirm it again" not in c["eligibility_for_official_record"]["reason"]
    [q] = [q for q in Q.consolidate(b)["questions"] if q.get("reason") == "clock_zone_changed_after_confirmation"]
    assert "--decision correct --value" in q["answer_command"] and "--decision confirm" not in q["answer_command"]
    assert "Correct it" in q["text"] and "Confirm it again" not in q["text"]
    [v1] = [x for x in b["questions"] if x["kind"] == "confirm_value" and x["target"]["id"] == cid]
    assert "Correct it" in v1["prompt"]
    # the command it gives works
    capsys.readouterr()
    argv = q["answer_command"].split()[2:]  # drop "isaac bundle"
    argv = [str(out) if a == "<bundle_dir>" else "2099-11-01T08:30:00Z" if a == "YYYY-MM-DDTHH:MM:SSZ" else a for a in argv]
    argv = argv[: argv.index("--by")] + ["--by", BY]
    assert cli.main(["bundle", *argv]) == 0
    assert _start_of(_valid(out), "SYN_alpha")["eligibility_for_official_record"]["eligible"] is True


def test_a_second_zone_change_counts_only_what_it_undid(tmp_path):
    out = _import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:00:00"), "SYN_beta_A.001": stamp("2099-07-15T10:00:00")})
    _zone(out, "UTC")
    a, b_ = (_start_of(_valid(out), label)["candidate_id"] for label in ("SYN_alpha", "SYN_beta"))
    M.decide(out, target_ids=[a, b_], decision="confirm", value=None, by=BY, orcid=None)
    first = _zone(out, LA)["clock_zone"]
    assert first["confirmations_invalidated_now"] == 2
    _confirm(out, a)  # only alpha is confirmed again; beta stays stale
    second = _zone(out, NY)["clock_zone"]
    assert second["confirmations_invalidated_now"] == 1 and second["to_confirm_again"] == [a]  # NOT beta again
    assert sorted(second["candidate_ids_to_confirm_again"]) == sorted([a, b_])  # but both still need it
    assert second["confirmations_no_longer_counting"] == 2
    assert "1 start-time confirmation(s) made under another zone" in second["statement"] and b_ not in second["statement"]
