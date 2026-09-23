"""Historical-import semantics, 2026-09-22 — conventions, operators, conflicts, signals.

**The acceptance tests for the domain owner's (Angel's) 2026-09-22 answers, relayed by
the project owner, and for the scientist/profile model correction.** Every fixture here
is SYNTHETIC: ``tests/fixtures/bl15/semantics/multi_operator_corpus`` carries sample
codes ``ZZ1``-``ZZ3``, the invented element ``Zz``, a year of 2099/2100, energies of
1000-1100 and three invented operators ("Operator Alpha/Beta/Gamma (synthetic)"). No
real archive content is here and none may be put here (``CLAUDE.md`` §6).

The corpus, by design:

* legacy 01-03 (group 01, Alpha) and 04-05 (group 02, Beta) are named in the build's
  BL15-2 convention; 06-08 (group 03, Alpha + Gamma, then Gamma) use a DIFFERENT
  vocabulary (``alk``, ``fresh``) that only the test-only convention below reads;
* 01-03 declare ``beforeCycling`` internally while their names say ``after500Cycling``
  — a systematic rename, three in a row — and the notes' rows for them say "after 500";
* legacy 05 is carried by TWO distinct acquisitions (the Run-32 shape);
* 01-05 and 08 carry signal on ``vortDT`` only, 06 on ``vortDT2`` only, 07 on both;
* the notes say "SYNTHETIC: held at room temperature throughout" and nothing numeric;
* the notes' ``Notes`` cells carry invented remarks, each marked SYNTHETIC — one of
  them a multi-line cell in a row that is not last, and the last row of the last table
  followed directly by a line of prose that is NOT part of the cell.

**No sentence of the real archive is reproduced** (corrected 2026-09-22 after an
independent review found two remark phrases that also occur in the private corpus;
the procedure cells begin with the notes reader's own public recognition phrase and
are otherwise invented).
"""

from __future__ import annotations

import dataclasses
import json
import re
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import isaac_api.activity as activity
import isaac_api.capabilities as capabilities
import isaac_api.convention_rules as cr
import isaac_api.historical_import as hist
import isaac_api.identity as identity
import isaac_api.workspace as ws
from isaac_api.bl15 import applicability as appl
from isaac_api.bl15 import mapping as mp
from isaac_api.bl15 import profiles
from isaac_api.bl15 import resolution as res
from isaac_api.bl15 import signals as sig

REPO_ROOT = Path(__file__).resolve().parents[3]
SEMANTICS = "tests/fixtures/bl15/semantics/multi_operator_corpus"
ARCHIVE = "bl15_synthetic_semantics_corpus"
DEFAULT = profiles.DEFAULT_PROFILE_ID

#: THE SECOND CONVENTION — TEST-ONLY, and deliberately not shaped like a real beamline
#: standard: a two-word synthetic vocabulary. It is registered only inside a test
#: (``profiles.registered_for_tests``); no application module can see it otherwise.
ALK = profiles.NamingProfile(
    profile_id="synthetic_alk_convention",
    profile_version="1",
    display_name="Synthetic 'alk' convention (test only)",
    description="SYNTHETIC. A second filename vocabulary, for multi-convention tests.",
    token_recognizers=(
        profiles.RECOGNIZER_MEDIUM,
        profiles.RECOGNIZER_STATE,
        profiles.RECOGNIZER_POTENTIAL,
        profiles.RECOGNIZER_FILTER,
        profiles.RECOGNIZER_SAMPLE_NAME,
        profiles.RECOGNIZER_BARE_INTEGER,
    ),
    medium_aliases=(("alk", "base"),),
    state_aliases=(("fresh", "as_is"),),
    sample_code_pattern=r"^[A-Z]{2,}[0-9]+[A-Z]?$",
)


# --- fixtures -----------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv(identity.EDGE_TRUST_VERIFIER_ENV, raising=False)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, raising=False)
    monkeypatch.delenv(capabilities.INGESTION_ENV, raising=False)
    monkeypatch.delenv(capabilities.STAGING_ROOT_ENV, raising=False)
    monkeypatch.setitem(hist.ARCHIVE_FIXTURES, ARCHIVE, SEMANTICS)
    return ws


@pytest.fixture()
def alk():
    with profiles.registered_for_tests(ALK):
        yield ALK


@pytest.fixture()
def client(workspace):
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _import(client, archive: str = ARCHIVE) -> str:
    created = client.post("/api/imports", json={"label": "synthetic semantics"})
    assert created.status_code == 200, created.text
    import_id = created.json()["import"]["import_id"]
    added = client.post(
        f"/api/imports/{import_id}/sources",
        json={"kind": "archive", "fixture_name": archive},
    )
    assert added.status_code == 200, added.text
    assert client.post(f"/api/imports/{import_id}/parse").status_code == 200
    assert client.post(f"/api/imports/{import_id}/reconstruct").status_code == 200
    return import_id


def _view(client, import_id: str) -> dict:
    response = client.get(f"/api/imports/{import_id}")
    assert response.status_code == 200, response.text
    return response.json()["import"]


def _units(view: dict) -> dict[str, dict]:
    return {row["stem"]: row for row in view["archive"]["units_page"]["rows"]}


def _record(client, title="semantics record") -> str:
    response = client.post("/api/experiments", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _etag(client, eid: str) -> str:
    return client.get(f"/api/experiments/{eid}").headers["ETag"]


def _rule(client, import_id: str, payload: dict, eid: str | None = None):
    headers = {"If-Match": _etag(client, eid)} if eid else {}
    return client.post(f"/api/imports/{import_id}/rules", json=payload, headers=headers)


def _bind_alk(client, import_id, *, scope="import", eid=None, legacy=(6, 8)):
    payload = {
        "kind": "profile_binding",
        "scope": scope,
        "selector": {"legacy_range": list(legacy)},
        "body": {"profile_id": ALK.profile_id, "profile_version": ALK.profile_version},
    }
    if eid:
        payload["experiment_id"] = eid
    response = _rule(client, import_id, payload, eid=eid)
    assert response.status_code == 200, response.text
    return response.json()


def _stem(units: dict, legacy: str) -> str:
    return next(s for s in units if s.startswith(f"{legacy}_"))


# =============================================================================
# 1. MULTIPLE OPERATORS, ONE EXPERIMENT — no parser choice by operator identity
# =============================================================================


def test_a_selector_has_no_operator_field_and_neither_does_a_binding():
    """Structural: there is no way to express "read Alpha's files this way"."""
    for cls in (appl.Selector, appl.ProfileBinding):
        names = {f.name for f in dataclasses.fields(cls)}
        assert not names & {"operator", "operators", "person", "scientist", "contributor"}


def test_multiple_operators_one_experiment_every_source_read_by_convention(client):
    """Three operators, one convention in force: every unit reads under it, and the
    operators appear as PROVENANCE on the units they are named for."""
    view = _view(client, _import(client))
    units = _units(view)
    for stem, unit in units.items():
        assert unit["applicability"]["profile_ids"] == [DEFAULT], stem
        assert unit["applicability"]["basis"] == appl.BASIS_BUILD_DEFAULT
    people = {stem: sorted(c["name"] for c in unit["contributors"]) for stem, unit in units.items()}
    assert people[_stem(units, "01")] == ["Operator Alpha (synthetic)"]
    assert people[_stem(units, "04")] == ["Operator Beta (synthetic)"]
    assert people[_stem(units, "07")] == [
        "Operator Alpha (synthetic)",
        "Operator Gamma (synthetic)",
    ]
    for unit in units.values():
        for person in unit["contributors"]:
            assert person["is_actor"] is False
            assert person["role"] == "provenance"
    assert view["corpus_review"]["profile_applicability"]["selected_by_operator"] is False


def test_renaming_every_operator_changes_no_parsing_choice(client, tmp_path, monkeypatch):
    """The operator is provenance: swap every name and the applicability is identical."""
    copy = tmp_path / "renamed"
    shutil.copytree(REPO_ROOT / SEMANTICS, copy)
    notes = next(copy.glob("*notes*.txt"))
    text = notes.read_bytes().decode("utf-8")
    text = text.replace("Alpha", "Omega").replace("Beta", "Sigma").replace("Gamma", "Tau")
    notes.write_bytes(text.encode("utf-8"))
    monkeypatch.setitem(hist.ARCHIVE_FIXTURES, "renamed_semantics", str(copy))

    original = _units(_view(client, _import(client)))
    renamed = _units(_view(client, _import(client, "renamed_semantics")))
    assert set(original) == set(renamed)
    for stem in original:
        assert original[stem]["applicability"] == renamed[stem]["applicability"], stem
    # NOT VACUOUS: the rename really reached every unit that names an operator.
    named = [stem for stem in original if original[stem]["contributors"]]
    assert len(named) == len(original)
    for stem in named:
        before = [c["name"] for c in original[stem]["contributors"]]
        after = [c["name"] for c in renamed[stem]["contributors"]]
        assert before != after and len(before) == len(after), stem


# =============================================================================
# 2-4. CONVENTIONS PER RUN SUBSET; SAME CONVENTION MANY SCIENTISTS; ONE SCIENTIST
#      MANY CONVENTIONS
# =============================================================================


def test_multiple_conventions_one_experiment_select_by_run_subset(client, alk):
    import_id = _import(client)
    body = _bind_alk(client, import_id)
    assert body["rule"]["scope"] == cr.SCOPE_IMPORT
    view = body["import"]
    units = _units(view)
    for stem, unit in units.items():
        legacy = int(stem.split("_", 1)[0])
        applies = unit["applicability"]
        if 6 <= legacy <= 8:
            assert applies["profile_ids"] == [ALK.profile_id], stem
            assert applies["scope"] == appl.SCOPE_RUN_SUBSET
            assert applies["basis"] == appl.BASIS_IMPORT_CHOICE
            assert applies["rule_refs"] == [body["rule"]["rule_id"]]
        else:
            assert applies["profile_ids"] == [DEFAULT], stem
    # THE READING DIFFERS BY CONVENTION: `alk` is a medium under the alk convention.
    evidence = view["corpus_review"]["evidence"]
    media = {
        (row["measurement_stem"], row["normalized_value"])
        for row in evidence
        if row["concept"] == "electrolyte_or_medium"
    }
    assert (_stem(units, "06"), "base") in media
    counts = view["corpus_review"]["profile_applicability"]["convention_counts"]
    assert counts[ALK.profile_id] > 0 and counts[DEFAULT] > 0


def test_without_the_binding_the_other_vocabulary_is_unknown_not_guessed(client):
    view = _view(client, _import(client))
    units = _units(view)
    evidence = view["corpus_review"]["evidence"]
    media_06 = [
        row
        for row in evidence
        if row["concept"] == "electrolyte_or_medium"
        and row["measurement_stem"] == _stem(units, "06")
    ]
    assert media_06 == []


def test_same_convention_multiple_scientists(client):
    units = _units(_view(client, _import(client)))
    alpha, beta = _stem(units, "01"), _stem(units, "04")
    assert units[alpha]["applicability"]["profile_ids"] == units[beta]["applicability"]["profile_ids"]
    assert units[alpha]["contributors"][0]["name"] != units[beta]["contributors"][0]["name"]


def test_one_scientist_multiple_conventions(client, alk):
    import_id = _import(client)
    units = _units(_bind_alk(client, import_id)["import"])
    alpha_units = [
        s for s, u in units.items() if any("Alpha" in c["name"] for c in u["contributors"])
    ]
    conventions = {tuple(units[s]["applicability"]["profile_ids"]) for s in alpha_units}
    assert conventions == {(DEFAULT,), (ALK.profile_id,)}


def test_the_second_convention_is_reachable_only_through_the_test_seam(alk):
    """The test-only convention must not look like, or become, a real standard: no
    application module calls the registration seam, and it is gone after the block."""
    package = REPO_ROOT / "apps" / "api" / "isaac_api"
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in package.rglob("*.py")
        if path.name != "profiles.py"
        # word-bounded: `nominal.reviewed_rule_registered_for_tests` is a different seam
        and re.search(r"(?<![A-Za-z0-9_])registered_for_tests\(", path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
    assert ALK.profile_id in profiles.PROFILES  # inside the fixture's block


def test_the_second_convention_is_unregistered_outside_the_block():
    assert ALK.profile_id not in profiles.PROFILES
    assert profiles.profile_for(ALK.profile_id) is None


def test_a_tie_between_two_conventions_is_an_ambiguity_never_a_choice(alk):
    one = appl.ProfileBinding(
        binding_id="a", profile_id=DEFAULT, profile_version="1",
        scope=appl.SCOPE_RUN_SUBSET, selector=appl.Selector(legacy_range=(6, 6)),
        basis=appl.BASIS_IMPORT_CHOICE,
    )
    two = appl.ProfileBinding(
        binding_id="b", profile_id=ALK.profile_id, profile_version="1",
        scope=appl.SCOPE_RUN_SUBSET, selector=appl.Selector(legacy_range=(6, 6)),
        basis=appl.BASIS_IMPORT_CHOICE,
    )
    applies = appl.resolve(
        [one, two], archive_path="x/06_03_ZZ3_alk", stem="06_03_ZZ3_alk", source_type=None
    )
    assert applies.ambiguous
    assert set(applies.profile_ids) == {DEFAULT, ALK.profile_id}
    assert "nothing was chosen" in applies.ambiguity


# =============================================================================
# 5. CONFLICT PRESERVATION — no hierarchy; recommendation non-authoritative;
#    confirmation goes forward as a proposal only
# =============================================================================


def test_every_reading_is_preserved_and_the_recommendation_is_non_authoritative(client):
    view = _view(client, _import(client))
    rel = view["archive"]["relationships"]
    assert rel["conflict_model"]["source_hierarchy"] is None
    declared = [
        c
        for unit in rel["units"]
        for c in unit["conflicts"]
        if c["kind"] == "internal_declaration_vs_filename"
    ]
    assert len(declared) == 3
    for conflict in declared:
        roles = {r["source_role"] for r in conflict["readings"]}
        assert {"human_label", "instrument_header", "planned_acquisition"} <= roles
        rec = conflict["recommendation"]
        assert rec["authority"] == "non_authoritative"
        assert rec["status"] == res.RECOMMENDATION_SUGGESTED
        assert rec["value"] == conflict["subject"]
        kinds = {s["kind"] for s in rec["supports"] if s["counts"]}
        assert kinds >= {res.SUPPORT_REPEATED_PATTERN, res.SUPPORT_FINAL_NOTES}
        # the macro and header agree and are counted ONCE — as a non-counting note
        assert any(
            s["kind"] == res.SUPPORT_ONE_CAUSAL_CHAIN and not s["counts"]
            for s in rec["supports"]
        )
        assert conflict["resolution"] is None
        assert conflict["review_status"] == "needs_review"


def test_evidence_pointing_both_ways_yields_no_recommendation():
    from isaac_api.bl15.relate import (
        CONFLICT_DECLARATION_VS_FILENAME,
        Conflict,
        MeasurementUnit,
        Reading,
    )

    conflict = Conflict(
        kind=CONFLICT_DECLARATION_VS_FILENAME,
        subject="09_04_ZZ9_a_after500Cycling_x",
        readings=(
            Reading("09_04_ZZ9_a_after500Cycling_x", "filename", "09_04_ZZ9_a_after500Cycling_x"),
            Reading("09_04_ZZ9_a_after500Cycling_x", "#F", "09_04_ZZ9_a_after400Cycling_x"),
        ),
        explanation="synthetic",
    )
    unit = MeasurementUnit(
        stem="09_04_ZZ9_a_after500Cycling_x", acquisition_path="09_04_ZZ9_a_after500Cycling_x",
        legacy_number=9, group_token="04", conflicts=(conflict,),
    )
    rec = res.recommend(
        conflict,
        unit=unit,
        units=[unit],
        note_texts_by_number={9: [{"text": "after 500 then 400 cycles"}]},
    )
    assert rec.status == res.RECOMMENDATION_NONE
    assert rec.value is None


def test_a_confirmed_resolution_goes_forward_as_a_proposal_only(client):
    """A scientist resolves a FIELD disagreement; the value becomes a PROPOSAL whose
    acceptance keeps its `409 human_actor_required` gate in the default configuration."""
    import_id = _import(client)
    view = _view(client, import_id)
    # The fixture's unit 04 states two different acquisition dates (its second scan's
    # `#D` differs): a real field-level disagreement at a writable path.
    disagreeing = [
        c
        for c in view["reconstruction"]["candidates"]
        if c["unresolved_reason"] and c["target_field_path"] == "timestamps.acquired_start_utc"
    ]
    assert disagreeing, "the fixture no longer carries a field disagreement"
    target = disagreeing[0]
    assert target["review_status"] == "sources_conflict"
    chosen = target["disagreement"][0]["value"]

    response = _rule(
        client,
        import_id,
        {
            "kind": "conflict_resolution",
            "scope": "import",
            "body": {"candidate_id": target["candidate_id"], "chosen_value": chosen},
        },
    )
    assert response.status_code == 200, response.text
    candidates = {
        c["candidate_id"]: c for c in response.json()["import"]["reconstruction"]["candidates"]
    }
    original = candidates[target["candidate_id"]]
    derived = candidates[f"{target['candidate_id']}::resolved"]
    # THE DISAGREEMENT IS KEPT, as source facts; the original is marked resolved.
    assert original["disagreement"] == target["disagreement"]
    assert original["proposed_value"] is None
    assert original["review_status"] == "resolved"
    assert derived["proposable"] is True
    assert derived["resolved_by_rule"] == response.json()["rule"]["rule_id"]

    eid = _record(client)
    sent = client.post(
        f"/api/imports/{import_id}/add-to-experiment",
        json={"experiment_id": eid, "create_runs": True},
        headers={"If-Match": _etag(client, eid)},
    )
    assert sent.status_code == 200, sent.text
    row = next(r for r in sent.json()["sent"] if r["candidate_id"] == derived["candidate_id"])
    exp = ws.load_experiment(eid)
    proposal = exp.get_proposal(row["proposal_id"])
    assert proposal.state == "open"
    # AND NO VALUE WAS WRITTEN: the run's draft does not hold it.
    run = exp.get_run(row["run_id"])
    assert "timestamps.acquired_start_utc" not in (run.draft.get("fields") or {})
    accept = client.post(
        f"/api/experiments/{eid}/proposals/{row['proposal_id']}/review",
        json={"action": "accept", "confirmed_by_user": True, "accepted_from": "candidate"},
        headers={"If-Match": _etag(client, eid)},
    )
    assert accept.status_code == 409
    assert accept.json()["error"] == "human_actor_required"


def test_a_resolution_must_choose_a_stated_reading(client):
    import_id = _import(client)
    view = _view(client, import_id)
    conflict = next(
        c
        for unit in view["archive"]["relationships"]["units"]
        for c in unit["conflicts"]
        if c["kind"] == "internal_declaration_vs_filename"
    )
    bad = _rule(
        client,
        import_id,
        {
            "kind": "conflict_resolution",
            "scope": "import",
            "body": {"conflict_id": conflict["conflict_id"], "chosen_value": "invented"},
        },
    )
    assert bad.status_code == 422
    assert bad.json()["error"] == "not_a_reading"


def test_a_recurring_resolution_applies_only_within_its_selector(client):
    import_id = _import(client)
    response = _rule(
        client,
        import_id,
        {
            "kind": "conflict_resolution",
            "scope": "import",
            "selector": {"legacy_range": [1, 2]},
            "body": {
                "conflict_kind": "internal_declaration_vs_filename",
                "chosen_source_role": "human_label",
            },
        },
    )
    assert response.status_code == 200, response.text
    rel = response.json()["import"]["archive"]["relationships"]
    resolved = {
        unit["stem"].split("_", 1)[0]: c
        for unit in rel["units"]
        for c in unit["conflicts"]
        if c["kind"] == "internal_declaration_vs_filename"
    }
    assert resolved["01"]["resolution"]["applied"] is True
    assert resolved["01"]["resolution"]["chosen_value"] == resolved["01"]["subject"]
    assert resolved["02"]["review_status"] == "resolved"
    assert resolved["03"]["resolution"] is None  # outside the selector


# =============================================================================
# 6. PROFILE LEARNING — reusable only within the recorded scope and version
# =============================================================================


def test_an_experiment_rule_applies_to_imports_targeting_that_experiment_only(client, alk):
    eid_a = _record(client, "experiment A")
    eid_b = _record(client, "experiment B")
    import_a = _import(client)
    body = _bind_alk(client, import_a, scope="experiment", eid=eid_a)
    assert body["rule"]["experiment_id"] == eid_a
    assert body["rule"]["confirmed_by"] == activity.ACTOR_UNATTRIBUTED
    units_a = _units(body["import"])
    assert units_a[_stem(units_a, "06")]["applicability"]["basis"] == appl.BASIS_CONFIRMED_RULE

    # The rule is DURABLE on experiment A, and recorded in its activity history.
    rules_a = client.get(f"/api/experiments/{eid_a}/convention-rules").json()
    assert rules_a["active_count"] == 1
    assert rules_a["rules"][0]["is_official_field_value"] is False
    history = client.get(f"/api/experiments/{eid_a}/activity").json()
    assert history["events"][0]["action"] == activity.ACTION_CONVENTION_RULE_RECORDED
    assert history["events"][0]["channel"] == activity.CHANNEL_HISTORICAL_IMPORT

    # A fresh import targeting B does NOT get A's experiment-scoped rule.
    import_b = _import(client)
    units_b = _units(_view(client, import_b))
    assert units_b[_stem(units_b, "06")]["applicability"]["profile_ids"] == [DEFAULT]
    assert _view(client, import_b)["rules"]["reusable_from_other_experiments"] == []
    del eid_b


def test_a_convention_rule_is_offered_elsewhere_and_applies_only_once_confirmed(client, alk):
    eid_a = _record(client, "experiment A")
    import_a = _import(client)
    rule_id = _bind_alk(client, import_a, scope="profile", eid=eid_a)["rule"]["rule_id"]

    eid_b = _record(client, "experiment B")
    import_b = _import(client)
    view_b = _view(client, import_b)
    reusable = view_b["rules"]["reusable_from_other_experiments"]
    assert [r["rule"]["rule_id"] for r in reusable] == [rule_id]
    assert reusable[0]["applied_here"] is False
    assert reusable[0]["matches"]["units"] == 3
    assert reusable[0]["difference_count"] == 3
    units_b = _units(view_b)
    assert units_b[_stem(units_b, "06")]["applicability"]["profile_ids"] == [DEFAULT]

    # REUSE IS A REVIEWED ACT: a new rule for B citing A's.
    payload = {
        "kind": "profile_binding",
        "scope": "experiment",
        "experiment_id": eid_b,
        "selector": {"legacy_range": [6, 8]},
        "body": {"profile_id": ALK.profile_id, "profile_version": "1"},
        "derived_from": rule_id,
    }
    confirmed = _rule(client, import_b, payload, eid=eid_b)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["rule"]["derived_from"] == rule_id
    units_b = _units(confirmed.json()["import"])
    assert units_b[_stem(units_b, "06")]["applicability"]["profile_ids"] == [ALK.profile_id]


def test_a_rule_reviewed_against_one_version_does_not_apply_to_the_next(alk):
    rule = cr.new_rule(
        rule_id="01TESTRULE0000000000000000",
        kind=cr.KIND_PROFILE_BINDING,
        scope=cr.SCOPE_IMPORT,
        body={"profile_id": ALK.profile_id, "profile_version": "1"},
        selector={"legacy_range": [6, 8]},
        confirmed_utc="2099-01-01T00:00:00Z",
        existing=[],
        import_id="01TESTIMPORT00000000000000",
    )
    v2 = dataclasses.replace(ALK, profile_version="2")
    profiles.PROFILES[ALK.profile_id] = v2
    try:
        applies = appl.resolve(
            cr.bindings_from([rule]),
            archive_path="06_03_ZZ3_alk",
            stem="06_03_ZZ3_alk",
            source_type=None,
        )
    finally:
        profiles.PROFILES[ALK.profile_id] = ALK
    assert applies.profile_ids == (DEFAULT,)
    assert applies.stale_bindings == (f"rule:{rule.rule_id}",)
    assert rule.version_is_current() is True  # at v1 again


def test_a_rule_is_superseded_by_a_new_version_never_edited(client, alk):
    import_id = _import(client)
    first = _bind_alk(client, import_id)["rule"]
    second = _rule(
        client,
        import_id,
        {
            "kind": "profile_binding",
            "scope": "import",
            "selector": {"legacy_range": [7, 8]},
            "body": {"profile_id": ALK.profile_id, "profile_version": "1"},
            "supersedes": first["rule_id"],
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["rule"]["version"] == 2
    view = second.json()["import"]
    assert [r["rule_id"] for r in view["rules"]["import"]] == [
        first["rule_id"],
        second.json()["rule"]["rule_id"],
    ]
    units = _units(view)
    assert units[_stem(units, "06")]["applicability"]["profile_ids"] == [DEFAULT]
    assert units[_stem(units, "07")]["applicability"]["profile_ids"] == [ALK.profile_id]


# =============================================================================
# 7. RUN 32 — two acquisitions, distinct durable identities, no preference
# =============================================================================


def test_two_acquisitions_under_one_legacy_number_keep_distinct_identities(client):
    import_id = _import(client)
    view = _view(client, import_id)
    fives = [u for u in _units(view).values() if u["legacy_number"] == 5]
    assert len(fives) == 2
    assert len({u["acquisition_identity"] for u in fives}) == 2
    assert all(u["legacy_number_shared"] for u in fives)
    conflict = next(
        c
        for c in view["archive"]["relationships"]["corpus_conflicts"]
        if c["kind"] == "duplicate_legacy_number"
    )
    rec = conflict["recommendation"]
    assert rec["status"] == res.RECOMMENDATION_FORBIDDEN
    assert rec["value"] is None
    # the notes' support is SHOWN, as evidence and not truth
    assert rec["supports"] and all(not s["counts"] for s in rec["supports"])

    refused = _rule(
        client,
        import_id,
        {
            "kind": "conflict_resolution",
            "scope": "import",
            "body": {"conflict_id": conflict["conflict_id"], "chosen_value": fives[0]["stem"]},
        },
    )
    assert refused.status_code == 422
    assert refused.json()["error"] == "resolution_forbidden"

    eid = _record(client)
    first = client.post(
        f"/api/imports/{import_id}/add-to-experiment",
        json={"experiment_id": eid, "create_runs": True},
        headers={"If-Match": _etag(client, eid)},
    ).json()
    created = {r["stem"]: r for r in first["created_runs"]}
    run_a, run_b = (created[u["stem"]]["run_id"] for u in fives)
    assert run_a != run_b
    exp = ws.load_experiment(eid)
    assert exp.historical_run_origins[run_a]["acquisition_identity"] != (
        exp.historical_run_origins[run_b]["acquisition_identity"]
    )

    # EVEN IF THE LABELS ARE MADE IDENTICAL, a re-run finds each run by IDENTITY.
    with ws.record_lock(eid):
        exp = ws.load_experiment(eid)
        exp.get_run(run_b).label = exp.get_run(run_a).label
        exp.save_versioned()
    second = client.post(
        f"/api/imports/{import_id}/add-to-experiment",
        json={"experiment_id": eid, "create_runs": True},
        headers={"If-Match": _etag(client, eid)},
    ).json()
    assert second["counts"]["runs_created"] == 0
    present = {r["stem"]: r for r in second["runs_already_present"]}
    for unit in fives:
        assert present[unit["stem"]]["matched_by"] == "acquisition_identity"
        assert present[unit["stem"]]["run_id"] == created[unit["stem"]]["run_id"]


# =============================================================================
# 8. TEMPERATURE — nothing by default; "room temperature" kept verbatim
# =============================================================================


def test_room_temperature_is_kept_verbatim_and_no_number_is_offered(client):
    import_id = _import(client)
    view = _view(client, import_id)
    temperature = view["corpus_review"]["temperature"]
    assert temperature["status"] == "stated_in_source"
    assert [t["raw_literal"] for t in temperature["statements"]] == [
        "SYNTHETIC: held at room temperature throughout"
    ]
    assert all(t["converted_to_a_number"] is False for t in temperature["statements"])
    assert temperature["automatic_value"] is None
    # THE POLICY MUST NOT CONTRADICT THE STATEMENT SERVED BESIDE IT. It used to be
    # `TEMPERATURE_ABSENT_REASON` unconditionally, which opens "this corpus states no
    # temperature anywhere" — false for this corpus, whose notes state one in words.
    # Found by the Historical Import UI slice (2026-09-22), which would have rendered
    # the two side by side.
    assert "states no temperature anywhere" not in temperature["policy"]
    assert "verbatim" in temperature["policy"]
    assert "298" in temperature["policy"] and "must not be defaulted" in temperature["policy"]

    eid = _record(client)
    body = client.post(
        f"/api/imports/{import_id}/add-to-experiment",
        json={"experiment_id": eid, "create_runs": True},
        headers={"If-Match": _etag(client, eid)},
    ).json()
    assert body["nominal_offers"] == []
    exp = ws.load_experiment(eid)
    kept = [e for e in exp.extended_context.entries if e.concept == "temperature_statement"]
    assert [e.raw_literal for e in kept] == ["SYNTHETIC: held at room temperature throughout"]
    assert kept[0].normalized_value is None
    assert kept[0].is_official_field_value is False
    for run in exp.runs:
        assert "context.temperature_K" not in (run.draft.get("fields") or {})


# =============================================================================
# 9. HERFD SELECTOR
# =============================================================================


def _channels(**liveness) -> tuple[sig.ChannelSummary, ...]:
    out = []
    for channel in sig.BL152_VORTEX.candidate_channels:
        state = liveness.get(channel, sig.LIVENESS_EMPTY)
        out.append(
            sig.ChannelSummary(
                channel=channel, scans_present=2, scans_with_edge=2 if state == "live" else 0,
                share=0.98 if state == "live" else 0.0,
                edge_fraction=1.0 if state == "live" else 0.0, liveness=state, reason="synthetic",
            )
        )
    return tuple(out)


ZZ = sig.ElementEvidence("Zz", "readme.txt", "line 3", sig.ELEMENT_ROLE_SHARED_README, "r", edge="L3")


def test_single_live_channel_and_established_element_is_proposed():
    selection = sig.select_primary_signal(_channels(vortDT2="live"), [ZZ])
    assert selection.status == sig.STATUS_PROPOSED
    assert selection.primary_channel == "vortDT2"
    assert selection.authority == sig.AUTHORITY_NON_AUTHORITATIVE
    assert [(a.channel, a.element, a.edge) for a in selection.assignments] == [("vortDT2", "Zz", "L3")]
    assert selection.to_state()["writes_a_record_field"] is False


@pytest.mark.parametrize(
    "channels,elements,code",
    [
        (dict(vortDT="live", vortDT2="live"), [ZZ], sig.REASON_MULTIPLE_LIVE_CHANNELS),
        (dict(vortDT="live"), [], sig.REASON_ELEMENT_NOT_ESTABLISHED),
        (
            dict(vortDT="live"),
            [ZZ, sig.ElementEvidence("Yy", "09_x_Yy", "filename token 2", sig.ELEMENT_ROLE_FILENAME, "r")],
            sig.REASON_CONFLICTING_ELEMENTS,
        ),
        (dict(vortDT="live", vortDT2="ambiguous"), [ZZ], sig.REASON_AMBIGUOUS_LIVENESS),
        (dict(), [ZZ], sig.REASON_NO_LIVE_CHANNEL),
    ],
)
def test_the_selector_leaves_anything_unclear_unresolved(channels, elements, code):
    selection = sig.select_primary_signal(_channels(**channels), elements)
    assert selection.status == sig.STATUS_UNRESOLVED
    assert selection.reason_code == code
    assert selection.primary_channel is None


def test_a_dual_element_mapping_is_representable_and_confirmable():
    assignments = (
        sig.ChannelAssignment("vortDT", "Zz", "L3", "rule"),
        sig.ChannelAssignment("vortDT2", "Yy", "K", "rule"),
    )
    selection = sig.select_primary_signal(
        _channels(vortDT="live", vortDT2="live"), [ZZ],
        confirmed_assignments=assignments, rule_ref="r1",
    )
    assert selection.status == sig.STATUS_CONFIRMED
    assert {(a.channel, a.element) for a in selection.assignments} == {("vortDT", "Zz"), ("vortDT2", "Yy")}
    contradicted = sig.select_primary_signal(
        _channels(vortDT="live"), [ZZ], confirmed_assignments=assignments, rule_ref="r1"
    )
    assert contradicted.status == sig.STATUS_NEEDS_REVIEW


def test_the_selector_over_the_synthetic_archive(client):
    view = _view(client, _import(client))
    units = _units(view)
    s01, s06, s07 = (units[_stem(units, n)]["signal_selection"] for n in ("01", "06", "07"))
    assert (s01["status"], s01["primary_channel"]) == (sig.STATUS_PROPOSED, "vortDT")
    assert s01["assignments"][0]["element"] == "Zz" and s01["assignments"][0]["edge"] == "L3"
    assert (s06["status"], s06["primary_channel"]) == (sig.STATUS_PROPOSED, "vortDT2")
    assert (s07["status"], s07["reason_code"]) == (
        sig.STATUS_UNRESOLVED,
        sig.REASON_MULTIPLE_LIVE_CHANNELS,
    )
    assert s01["thresholds"]["edge_z_min"] == sig.DEFAULT_THRESHOLDS.edge_z_min
    assert set(s01["thresholds"]["basis"]) == {"edge_z_min", "live_edge_fraction_min", "empty_share_max"}
    assert s01["evidence_not_used"]


def test_a_confirmed_dual_element_rule_resolves_run_07(client):
    import_id = _import(client)
    response = _rule(
        client,
        import_id,
        {
            "kind": "signal_assignment",
            "scope": "import",
            "selector": {"legacy_range": [7, 7]},
            "body": {
                "assignments": [
                    {"channel": "vortDT", "element": "Zz", "edge": "L3"},
                    {"channel": "vortDT2", "element": "Yy", "edge": "K"},
                ]
            },
        },
    )
    assert response.status_code == 200, response.text
    units = _units(response.json()["import"])
    s07 = units[_stem(units, "07")]["signal_selection"]
    assert s07["status"] == sig.STATUS_CONFIRMED
    assert s07["authority"] == sig.AUTHORITY_CONFIRMED
    assert {a["channel"]: a["element"] for a in s07["assignments"]} == {"vortDT": "Zz", "vortDT2": "Yy"}
    s06 = units[_stem(units, "06")]["signal_selection"]
    assert s06["status"] == sig.STATUS_PROPOSED  # outside the selector


def test_the_thresholds_are_replaceable_and_recorded():
    scan = sig.scan_channel_stats(
        "#L e vortDT vortDT2\n" + "\n".join(f"{i} {100 if i < 20 else 1000} 0" for i in range(40)),
        scan_path="s", channels=sig.BL152_VORTEX.candidate_channels,
    )
    assert scan.channels["vortDT"].edge_z > 5
    strict = sig.SelectorThresholds(edge_z_min=10_000.0)
    summary = {c.channel: c.liveness for c in sig.summarize_channels([scan], thresholds=strict)}
    assert summary["vortDT"] == sig.LIVENESS_AMBIGUOUS  # big share, no edge at that bar
    assert summary["vortDT3"] == sig.LIVENESS_ABSENT


# =============================================================================
# 10. DATA QUALITY NOTES NEVER PRODUCE qc.status
# =============================================================================


def test_data_quality_notes_are_kept_verbatim_and_never_become_qc_status(client):
    import_id = _import(client)
    view = _view(client, import_id)
    units = _units(view)
    assert [n["text"] for n in units[_stem(units, "01")]["data_quality_notes"]] == [
        "SYNTHETIC: skip the opening sweep"
    ]
    assert [n["text"] for n in units[_stem(units, "08")]["data_quality_notes"]] == ["3"]
    for unit in units.values():
        for note in unit["data_quality_notes"]:
            assert note["writes_qc_status"] is False
    assert not [
        c
        for c in view["reconstruction"]["candidates"]
        if (c["target_field_path"] or "").startswith("measurement.qc")
        and c["proposable"]
    ]
    assert mp.mapping_for("quality_note").scientist_label == "Data Quality Notes"

    eid = _record(client)
    body = client.post(
        f"/api/imports/{import_id}/add-to-experiment",
        json={"experiment_id": eid, "create_runs": True},
        headers={"If-Match": _etag(client, eid)},
    ).json()
    assert body["data_quality_notes"]["writes_qc_status"] is False
    assert body["data_quality_notes"]["captured_as_run_notes"] >= 4
    exp = ws.load_experiment(eid)
    assert not [p for p in exp.proposals if p.target_field_path.startswith("measurement.qc")]
    for run in exp.runs:
        # `qc` is a RUN-LEVEL BLOCK at `draft["qc"]` (what `export.transform` reads).
        # ~~`"qc" not in (run.draft.get("blocks") or {})`~~ checked a key no draft has and
        # was vacuous — corrected 2026-09-22 after an independent review.
        assert not run.draft.get("qc")
        assert not any(k.startswith("measurement.qc") for k in (run.draft.get("fields") or {}))
    texts = [n.text for n in exp.notes]
    assert any("SYNTHETIC: skip the opening sweep" in t for t in texts)
    again = client.post(
        f"/api/imports/{import_id}/add-to-experiment",
        json={"experiment_id": eid, "create_runs": True},
        headers={"If-Match": _etag(client, eid)},
    ).json()
    assert again["data_quality_notes"]["captured_as_run_notes"] == 0
    assert again["data_quality_notes"]["already_present"] == body["data_quality_notes"]["captured_as_run_notes"]


# =============================================================================
# 11. CAPABILITIES
# =============================================================================


def test_historical_file_ingestion_is_disabled_by_default_and_uploads_stay_refused(client):
    health = client.get("/api/health").json()
    # THE BANNER SERVES EXACTLY TWO KEYS — the shape the frontend builds against.
    assert health["historical_file_ingestion"] == {
        "enabled": False,
        "reason": "governance_not_approved",
    }
    assert client.post("/api/uploads").status_code == 403
    listing = client.get("/api/imports").json()
    block = listing["historical_file_ingestion"]
    # ...and the banner is a PROJECTION of the detail, never a second computation.
    assert {k: block[k] for k in ("enabled", "reason")} == health["historical_file_ingestion"]
    assert block["uploads_route_open"] is False
    assert block["governance_gate"] == "EXT-13"
    assert not [a for a in listing["available_archives"] if a.startswith("staged:")]


def test_enabling_ingestion_by_configuration_opens_only_the_staging_path(
    client, tmp_path, monkeypatch
):
    staging = tmp_path / "staging"
    staging.mkdir()
    shutil.copytree(REPO_ROOT / "tests/fixtures/bl15/gold/mini_corpus", staging / "synthetic_staged")
    monkeypatch.setenv(capabilities.INGESTION_ENV, capabilities.INGESTION_MODE_STAGING)
    monkeypatch.setenv(capabilities.STAGING_ROOT_ENV, str(staging))

    health = client.get("/api/health")
    assert health.json()["historical_file_ingestion"] == {"enabled": True, "reason": None}
    block = client.get("/api/imports").json()["historical_file_ingestion"]
    assert block["enabled"] is True and block["staged_archive_count"] == 1
    assert str(staging) not in health.text  # no path is ever served
    assert client.post("/api/uploads").status_code == 403  # STILL refused

    created = client.post("/api/imports", json={}).json()["import"]["import_id"]
    added = client.post(
        f"/api/imports/{created}/sources",
        json={"kind": "archive", "fixture_name": "staged:synthetic_staged"},
    )
    assert added.status_code == 200, added.text
    source = added.json()["source"]
    assert source["provenance"]["staged"] is True
    assert source["reference"] == "staged:synthetic_staged"
    assert source["sha256"] is None
    assert client.post(f"/api/imports/{created}/parse").status_code == 200
    reading = client.get(f"/api/imports/{created}").json()["import"]["corpus_digest"]
    assert reading["measurement_units"] >= 1
    # TRAVERSAL: a name that is not a direct allowlisted child is refused.
    for name in ("staged:../etc", "staged:", "staged:synthetic_staged/../x"):
        assert client.post(
            f"/api/imports/{created}/sources",
            json={"kind": "archive", "fixture_name": name},
        ).status_code == 422


def test_a_requested_but_unconfigured_staging_root_stays_disabled(monkeypatch):
    monkeypatch.setenv(capabilities.INGESTION_ENV, capabilities.INGESTION_MODE_STAGING)
    monkeypatch.delenv(capabilities.STAGING_ROOT_ENV, raising=False)
    block = capabilities.historical_file_ingestion()
    assert block == {**block, "enabled": False, "reason": "staging_root_not_configured"}
    monkeypatch.setenv(capabilities.INGESTION_ENV, "yes please")
    assert capabilities.historical_file_ingestion()["reason"] == "governance_not_approved"


def test_no_shipped_deploy_artifact_enables_ingestion():
    artifacts = [REPO_ROOT / "Dockerfile", *(REPO_ROOT / ".github/workflows").glob("*.y*ml")]
    for path in artifacts:
        assert capabilities.INGESTION_ENV not in path.read_text(encoding="utf-8"), path


def test_proposal_acceptance_is_reported_unavailable_by_the_same_resolution(client):
    health = client.get("/api/health").json()
    assert health["proposal_acceptance"] == {
        "available": False,
        "reason": identity.IdentityRefusal.NO_VERIFIER_CONFIGURED.value,
    }
    detail = capabilities.proposal_acceptance()
    assert detail["refusal_error"] == identity.HUMAN_ACTOR_REQUIRED_ERROR
    assert detail["refusal_status"] == 409


def test_the_preflight_reason_is_the_reason_the_accept_route_actually_returns(client):
    """NOT A COPY: drive a real proposal to the accept route and compare the 409's own
    `reason` with what the banner predicted."""
    import_id = _import(client)
    eid = _record(client)
    sent = client.post(
        f"/api/imports/{import_id}/add-to-experiment",
        json={"experiment_id": eid, "create_runs": True},
        headers={"If-Match": _etag(client, eid)},
    ).json()
    proposal_id = sent["sent"][0]["proposal_id"]
    refused = client.post(
        f"/api/experiments/{eid}/proposals/{proposal_id}/review",
        json={"action": "accept", "confirmed_by_user": True, "accepted_from": "candidate"},
        headers={"If-Match": _etag(client, eid)},
    )
    assert refused.status_code == 409
    predicted = client.get("/api/health").json()["proposal_acceptance"]
    assert predicted["available"] is False
    assert refused.json()["reason"] == predicted["reason"]


def test_proposal_acceptance_is_available_under_the_fixture_verifier(monkeypatch):
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, "synthetic.reviewer")
    acceptance = capabilities.proposal_acceptance()
    assert acceptance["available"] is True
    assert acceptance["reason"] is None
    assert acceptance["trust_basis_when_available"] == identity.TRUST_BASIS_TEST_FIXTURE
    # never the subject itself
    assert "synthetic.reviewer" not in json.dumps(acceptance)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_SUBJECT_ENV)
    assert capabilities.proposal_acceptance()["reason"] == (
        identity.IdentityRefusal.UNVERIFIED_EDGE_TRAVERSAL.value
    )


# =============================================================================
# 12. ACTIVITY: THE MCP READ, AND THE CHANNEL NO WRITE SITE RECORDS
# =============================================================================


def test_the_activity_history_is_an_mcp_read_with_closed_filter_sets():
    from isaac_api.mcp import policy, tools

    tool = tools.TOOLS["isaac_list_activity"]
    assert tool.scope is policy.Scope.READ
    assert tool.read_only is True
    props = tool.input_schema["properties"]
    assert props["action"]["enum"] == sorted(activity.ACTIVITY_ACTIONS)
    assert props["channel"]["enum"] == sorted(activity.ACTIVITY_CHANNELS)
    assert props["object_type"]["enum"] == sorted(activity.ACTIVITY_OBJECT_TYPES)
    assert props["run_id"]["maxLength"] == 128
    # resolved WITHOUT widening the reviewed free-string map
    assert not [k for k in tools._DECLARED_STRING_BOUNDS if k[0] == "list_activity"]


def test_system_is_named_as_a_channel_no_write_site_records():
    """The reservation is served; the guard that no write site records it lives in
    ``test_activity_channel_guard.py`` (moved there 2026-09-22, where the pointer in
    ``activity.py`` has always said it is)."""
    assert activity.CHANNEL_SYSTEM in activity.CHANNELS_WITHOUT_A_WRITE_SITE


def test_the_activity_read_serves_the_reservation(client):
    eid = _record(client)
    body = client.get(f"/api/experiments/{eid}/activity").json()
    assert body["channels_without_a_write_site"] == activity.CHANNELS_WITHOUT_A_WRITE_SITE
    summary = client.get("/api/activity/summary").json()
    assert summary["channels_without_a_write_site"] == activity.CHANNELS_WITHOUT_A_WRITE_SITE


# =============================================================================
# 13. THE COLUMN-READING COSTS ARE TWO COUNTS
# =============================================================================


def test_the_column_reading_dedup_and_cap_are_counted_separately():
    from isaac_api.bl15 import evidence as ev

    def reading(literal, i):
        return ev.SourceEvidence(
            evidence_id=f"e{i}", source_path=f"f{i}", source_type=ev.SOURCE_TYPE_SCAN_EXPORT,
            locator="x", raw_literal=literal, concept="filter", parser_id="p",
            measurement_stem="01_01_ZZ1",
        )

    literals = ["f1", "f2", "f3", "f4", "f5", "f1", "f2"]
    rows, capped, thinned = hist._column_readings(
        {f"p{i}": [reading(lit, i)] for i, lit in enumerate(literals)}
    )
    assert len(rows) == hist.MAX_DISTINCT_COLUMN_READINGS
    assert thinned == 2
    assert capped == 1


# =============================================================================
# 14. INDEPENDENT-REVIEW FIXES (2026-09-22). Each test FAILED against the committed
#     code before its fix (the polarity is stated in the report); the reviewer's
#     probes are reused where they apply.
# =============================================================================

from collections import defaultdict  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from isaac_api.bl15 import evidence as ev  # noqa: E402
from isaac_api.bl15 import reconstruct as rc  # noqa: E402


def _item(i, literal, concept="acquisition_timestamp", **extra):
    return ev.SourceEvidence(
        evidence_id=f"synthetic-{i}",
        source_path=f"synthetic/file-{i}",
        source_type=ev.SOURCE_TYPE_SCAN_EXPORT,
        locator=f"line {i}",
        raw_literal=literal,
        concept=concept,
        parser_id="synthetic",
        measurement_stem="01_01_ZZ1",
        **extra,
    )


def _disagreeing(items):
    (candidate,) = rc._candidates_from_evidence(
        items,
        candidate_prefix="01_01_ZZ1",
        source_ids={i.source_path: "src" for i in items},
        by_concept=defaultdict(int),
        by_status=defaultdict(int),
        unregistered=set(),
    )
    assert candidate.unresolved_reason is not None
    return candidate


def _resolve(items, chosen):
    candidate = _disagreeing(items)
    rule = SimpleNamespace(
        rule_id="R", version=1, confirmed_utc="2099-01-01T00:00:00Z",
        confirmed_by=activity.ACTOR_UNATTRIBUTED, body={"chosen_value": chosen},
    )
    index = hist._evidence_index({"synthetic": items})
    _marked, derived = hist._apply_resolution(candidate, {candidate.candidate_id: rule}, index)
    return derived


@pytest.mark.parametrize("literal", ["060", "10 A", "500 cycles", "2099 12"])
def test_I3_a_resolved_literal_is_kept_exactly_as_written(literal):
    """I-3: the first version regex-coerced the chosen reading (`'060'` -> 60,
    `'500 cycles'` -> 500). A literal nothing normalised stays the literal."""
    derived = _resolve([_item(1, literal), _item(2, "SYNTHETIC other")], literal)
    assert derived.proposed_value == literal
    assert isinstance(derived.proposed_value, str)


def test_I3_a_resolved_normalised_reading_takes_the_evidences_own_value():
    """…and a normalised reading takes `normalized_value` from the evidence that states
    it — the value an agreeing candidate would propose — never a parse of the string."""
    items = [
        _item(1, "060mV", concept="potential_magnitude", determinism=ev.DETERMINISM_NORMALIZED,
              normalized_value=0.06, unit="V", normalization_rule="synthetic-rule"),
        _item(2, "0p1V", concept="potential_magnitude", determinism=ev.DETERMINISM_NORMALIZED,
              normalized_value=0.1, unit="V", normalization_rule="synthetic-rule"),
    ]
    derived = _resolve(items, "0.06 V")
    assert derived.proposed_value == 0.06
    assert derived.proposed_value == rc.value_of_reading(items, "0.06 V")
    # only the statement that states the chosen reading supports the derived value
    assert [s["value"] for s in derived.supporting_statements] == ["060mV"]


def test_I2_a_resolved_timestamp_is_the_literal_an_agreeing_candidate_would_send():
    """I-2, timestamp half: resolution opens NO new route to `timestamps.*`. The value
    is the ctime literal as stated, identical to what the pre-existing agreeing path
    proposes for the same statement, and proposability is the registry's."""
    stated = "Fri Jan 01 00:00:00 2100"
    derived = _resolve([_item(1, stated), _item(2, "Sat Jan 02 00:00:00 2100")], stated)
    (agreeing,) = rc._candidates_from_evidence(
        [_item(1, stated)], candidate_prefix="01_01_ZZ1", source_ids={"synthetic/file-1": "src"},
        by_concept=defaultdict(int), by_status=defaultdict(int), unregistered=set(),
    )
    assert derived.proposed_value == agreeing.proposed_value == stated
    assert (derived.not_proposable_reason is None) is mp.mapping_for("acquisition_timestamp").proposable


@pytest.mark.parametrize("concept", ["sample_name", "acquisition_method", "sample_preparation"])
def test_I2_resolving_a_concept_the_registry_does_not_propose_keeps_it_unsendable(concept):
    """I-2: the first version set `not_proposable_reason=None` for any field candidate
    with a path, so a resolved `sample_name` / `acquisition_method` /
    `sample_preparation` became sendable to `sample.material.name` /
    `system.technique` / `sample.material.provenance`."""
    entry = mp.mapping_for(concept)
    assert entry.official_path and not entry.proposable
    derived = _resolve(
        [_item(1, "SYNTHETIC-A", concept=concept), _item(2, "SYNTHETIC-B", concept=concept)],
        "SYNTHETIC-A",
    )
    assert derived.target_field_path == entry.official_path
    assert derived.not_proposable_reason == entry.reason
    assert derived.proposable is False


def test_I2_over_http_a_resolved_sample_name_is_never_sent(client):
    """The reviewer's probe 4, as a regression test: two test-only conventions read
    unit 06's sample token differently; resolving it must not make it sendable."""
    X = profiles.NamingProfile(
        profile_id="synthetic_x", profile_version="1", display_name="X (test)",
        description="SYNTHETIC", token_recognizers=(profiles.RECOGNIZER_SAMPLE_NAME,),
        sample_code_pattern=r"^f[0-9]+$",
    )
    Y = profiles.NamingProfile(
        profile_id="synthetic_y", profile_version="1", display_name="Y (test)",
        description="SYNTHETIC", token_recognizers=(profiles.RECOGNIZER_SAMPLE_NAME,),
        sample_code_pattern=r"^[A-Z]{2,}[0-9]+[A-Z]?$",
    )
    with profiles.registered_for_tests(X), profiles.registered_for_tests(Y):
        import_id = _import(client)
        for pid in ("synthetic_x", "synthetic_y"):
            assert _rule(client, import_id, {
                "kind": "profile_binding", "scope": "import", "selector": {"legacy_range": [6, 6]},
                "body": {"profile_id": pid, "profile_version": "1"},
            }).status_code == 200
        view = _view(client, import_id)
        target = next(
            c for c in view["reconstruction"]["candidates"]
            if c["candidate_id"].startswith("06_") and c["candidate_id"].endswith("::sample_name")
            and c["unresolved_reason"]
        )
        resolved = _rule(client, import_id, {
            "kind": "conflict_resolution", "scope": "import",
            "body": {"candidate_id": target["candidate_id"],
                     "chosen_value": target["disagreement"][0]["value"]},
        })
        assert resolved.status_code == 200, resolved.text
        derived = next(
            c for c in resolved.json()["import"]["reconstruction"]["candidates"]
            if c["candidate_id"] == target["candidate_id"] + "::resolved"
        )
        assert derived["proposable"] is False
        eid = _record(client)
        sent = client.post(
            f"/api/imports/{import_id}/add-to-experiment",
            json={"experiment_id": eid, "create_runs": True},
            headers={"If-Match": _etag(client, eid)},
        ).json()
        assert not [s for s in sent["sent"] if "sample_name" in s["candidate_id"]]


def _timestamp_disagreement(view):
    return next(
        c for c in view["reconstruction"]["candidates"]
        if c["unresolved_reason"] and c["target_field_path"] == "timestamps.acquired_start_utc"
    )


def test_I1_a_rule_confirmed_on_A_never_shapes_proposals_minted_on_B(client):
    """I-1, the reviewer's probe 2 as a regression test. An Experiment-scoped resolution
    on A made the session's reading A's; adding the SAME import to B minted a
    `::resolved` proposal on B citing A's rule. Now B's batch re-reads the import under
    B's rules only (`reread_for_target`) and nothing of A's reaches B."""
    import_id = _import(client)
    target = _timestamp_disagreement(_view(client, import_id))
    eid_a, eid_b = _record(client, "A"), _record(client, "B")
    on_a = _rule(client, import_id, {
        "kind": "conflict_resolution", "scope": "experiment", "experiment_id": eid_a,
        "body": {"candidate_id": target["candidate_id"],
                 "chosen_value": target["disagreement"][0]["value"]},
    }, eid=eid_a)
    assert on_a.status_code == 200, on_a.text
    a_rule = on_a.json()["rule"]["rule_id"]

    to_b = client.post(
        f"/api/imports/{import_id}/add-to-experiment",
        json={"experiment_id": eid_b, "create_runs": True},
        headers={"If-Match": _etag(client, eid_b)},
    )
    assert to_b.status_code == 200, to_b.text
    body = to_b.json()
    # THE LEAK, asserted first so the pre-fix failure is this line and not a missing key.
    assert not [s for s in body["sent"] if s["candidate_id"].endswith("::resolved")]
    assert body["reread_for_target"] is True
    b = ws.load_experiment(eid_b)
    assert b.convention_rules == []
    assert not [p for p in b.proposals if a_rule in (p.rule or "")]
    # the session now reads for B: A's derived candidate is gone from it
    view = _view(client, import_id)
    assert view["rules"]["target_experiment_id"] == eid_b
    ids = {c["candidate_id"] for c in view["reconstruction"]["candidates"]}
    assert target["candidate_id"] + "::resolved" not in ids

    # …and adding to A again re-reads under A's rules, so A DOES get its own resolution.
    to_a = client.post(
        f"/api/imports/{import_id}/add-to-experiment",
        json={"experiment_id": eid_a, "create_runs": True},
        headers={"If-Match": _etag(client, eid_a)},
    ).json()
    assert to_a["reread_for_target"] is True
    assert [s for s in to_a["sent"] if s["candidate_id"].endswith("::resolved")]


def test_I1_the_single_candidate_route_refuses_another_records_resolution(client):
    import_id = _import(client)
    target = _timestamp_disagreement(_view(client, import_id))
    eid_a, eid_b = _record(client, "A"), _record(client, "B")
    assert _rule(client, import_id, {
        "kind": "conflict_resolution", "scope": "experiment", "experiment_id": eid_a,
        "body": {"candidate_id": target["candidate_id"],
                 "chosen_value": target["disagreement"][0]["value"]},
    }, eid=eid_a).status_code == 200
    derived_id = target["candidate_id"] + "::resolved"
    b = ws.load_experiment(eid_b)
    run_b = client.post(
        f"/api/experiments/{eid_b}/runs", json={"label": "SYNTHETIC run"},
        headers={"If-Match": _etag(client, eid_b)},
    )
    assert run_b.status_code in (200, 201), run_b.text
    refused = client.post(
        f"/api/imports/{import_id}/candidates/{derived_id}/propose",
        json={"experiment_id": eid_b, "run_id": run_b.json()["run"]["id"]},
        headers={"If-Match": _etag(client, eid_b)},
    )
    assert refused.status_code == 404, refused.text
    assert refused.json()["error"] == "import_candidate_not_found"
    assert ws.load_experiment(eid_b).proposals == b.proposals


def test_I5_importing_the_same_archive_twice_adds_no_data_quality_note_twice(client):
    """I-5, the reviewer's probe 5: the key carried the import id, so a SECOND session of
    the same archive minted every remark again (6 -> 12)."""
    eid = _record(client)
    first = second = None
    for _ in range(2):
        import_id = _import(client)
        body = client.post(
            f"/api/imports/{import_id}/add-to-experiment",
            json={"experiment_id": eid, "create_runs": True},
            headers={"If-Match": _etag(client, eid)},
        ).json()
        first, second = (body, None) if first is None else (first, body)
    assert first["data_quality_notes"]["captured_as_run_notes"] > 0
    assert second["data_quality_notes"]["captured_as_run_notes"] == 0
    assert second["data_quality_notes"]["already_present"] == (
        first["data_quality_notes"]["captured_as_run_notes"]
    )
    exp = ws.load_experiment(eid)
    per_run = [(n.run_id, n.text) for n in exp.notes if n.text.startswith("Data Quality Note")]
    assert len(per_run) == len(set(per_run)) == first["data_quality_notes"]["captured_as_run_notes"]


def test_a_remark_bound_by_a_shared_legacy_number_says_so_on_both_runs(client):
    """Minor finding: the Run-32 shape attaches one remark to BOTH acquisitions' runs,
    and each stored note must disclose that the number is shared."""
    import_id = _import(client)
    eid = _record(client)
    client.post(
        f"/api/imports/{import_id}/add-to-experiment",
        json={"experiment_id": eid, "create_runs": True},
        headers={"If-Match": _etag(client, eid)},
    )
    exp = ws.load_experiment(eid)
    fives = [n for n in exp.notes if "(file number 5)" in n.text]
    assert len({n.run_id for n in fives}) == 2
    for note in fives:
        assert "Legacy file number 5 is carried by more than one acquisition" in note.text
    ones = [n for n in exp.notes if "(file number 1)" in n.text]
    assert ones and not any("carried by more than one acquisition" in n.text for n in ones)


def test_I4_an_unreadable_staging_root_never_breaks_the_readiness_probe(
    client, tmp_path, monkeypatch
):
    """I-4: with staging enabled, every `/api/health` listed the root, and a `chmod 000`
    root made the readiness probe answer 500. Now the probe stats it and nothing else,
    and every read reports `staging_root_unreadable` instead of raising."""
    import os
    import stat as stat_module

    staging = tmp_path / "locked"
    staging.mkdir()
    (staging / "synthetic_staged").mkdir()
    monkeypatch.setenv(capabilities.INGESTION_ENV, capabilities.INGESTION_MODE_STAGING)
    monkeypatch.setenv(capabilities.STAGING_ROOT_ENV, str(staging))
    staging.chmod(0)
    try:
        if os.access(staging, os.R_OK):  # pragma: no cover - running as root
            pytest.skip("permissions are not enforced for this user")
        health = client.get("/api/health")
        assert health.status_code == 200, health.text
        assert health.json()["historical_file_ingestion"] == {
            "enabled": False,
            "reason": capabilities.REASON_STAGING_ROOT_UNREADABLE,
        }
        listing = client.get("/api/imports")
        assert listing.status_code == 200, listing.text
        assert listing.json()["historical_file_ingestion"]["reason"] == (
            capabilities.REASON_STAGING_ROOT_UNREADABLE
        )
        assert not [a for a in listing.json()["available_archives"] if a.startswith("staged:")]
        assert str(staging) not in health.text + listing.text
    finally:
        staging.chmod(stat_module.S_IRWXU)


def test_I4_a_listing_that_fails_after_the_access_check_is_reported_not_raised(
    tmp_path, monkeypatch
):
    staging = tmp_path / "root"
    staging.mkdir()
    env = {
        capabilities.INGESTION_ENV: capabilities.INGESTION_MODE_STAGING,
        capabilities.STAGING_ROOT_ENV: str(staging),
    }

    def refuse(self):
        raise PermissionError("synthetic")

    monkeypatch.setattr(type(staging), "iterdir", refuse)
    block = capabilities.historical_file_ingestion(env)
    assert (block["enabled"], block["reason"]) == (False, capabilities.REASON_STAGING_ROOT_UNREADABLE)
    assert capabilities.staged_archive_names(env) == ()


def test_I4_each_way_a_named_root_can_be_wrong_has_its_own_reason(tmp_path):
    base = {capabilities.INGESTION_ENV: capabilities.INGESTION_MODE_STAGING}
    a_file = tmp_path / "a-file"
    a_file.write_text("SYNTHETIC")
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    cases = {
        "": capabilities.REASON_STAGING_ROOT_MISSING,
        str(tmp_path / "absent"): capabilities.REASON_STAGING_ROOT_ABSENT,
        str(a_file): capabilities.REASON_STAGING_ROOT_NOT_A_DIRECTORY,
        str(link): capabilities.REASON_STAGING_ROOT_IS_SYMLINK,
    }
    for raw, reason in cases.items():
        env = {**base, capabilities.STAGING_ROOT_ENV: raw}
        assert capabilities.health_historical_file_ingestion(env) == {"enabled": False, "reason": reason}, raw
        assert capabilities.historical_file_ingestion(env)["reason"] == reason, raw
    ok = {**base, capabilities.STAGING_ROOT_ENV: str(real)}
    assert capabilities.health_historical_file_ingestion(ok) == {"enabled": True, "reason": None}
    assert capabilities.INGESTION_REASONS >= set(cases.values())


def test_I4_the_readiness_probe_never_lists_the_staging_root(tmp_path, monkeypatch):
    """Health reads configuration and one stat — it must not list the directory."""
    staging = tmp_path / "root"
    staging.mkdir()
    env = {
        capabilities.INGESTION_ENV: capabilities.INGESTION_MODE_STAGING,
        capabilities.STAGING_ROOT_ENV: str(staging),
    }
    calls = []
    original = type(staging).iterdir

    def spy(self):
        calls.append(self)
        return original(self)

    monkeypatch.setattr(type(staging), "iterdir", spy)
    assert capabilities.health_historical_file_ingestion(env)["enabled"] is True
    assert calls == []


def test_the_activity_tool_does_not_say_events_arrive_through_the_reserved_channel():
    """Minor finding: the tool listed `system` among the channels events arrive through,
    while `CHANNELS_WITHOUT_A_WRITE_SITE` says no act is recorded through it."""
    from isaac_api.mcp import tools

    description = tools.TOOLS["isaac_list_activity"].description
    first_paragraph = description.split("\n\n", 1)[0]
    for channel in activity.CHANNELS_WITHOUT_A_WRITE_SITE:
        assert f"`{channel}` is in the vocabulary, but no act in this build is recorded" in first_paragraph
        assert f"`{channel}`)" not in first_paragraph


def test_a_rules_trust_basis_is_the_projects_one_unattributed_sentinel(client, alk):
    """Minor finding, resolved by aligning the DOC with the wire rather than the reverse:
    a rule's `confirmed_trust_basis` is `activity.TRUST_BASIS_UNATTRIBUTED`, the value every
    activity event's `actor_trust_basis` and every proposal's `trust_basis` carries."""
    import_id = _import(client)
    rule = _bind_alk(client, import_id)["rule"]
    assert rule["confirmed_by"] == activity.ACTOR_UNATTRIBUTED
    assert rule["confirmed_trust_basis"] == activity.TRUST_BASIS_UNATTRIBUTED
    doc = (REPO_ROOT / "docs/historical-import-semantics-2026-09-22.md").read_text(encoding="utf-8")
    assert "confirmed_trust_basis: \"unattributed\"" in doc
    assert "confirmed_trust_basis (\"unattributed\")" in doc


def test_an_unreadable_run_origin_entry_survives_a_save(client):
    """Minor finding: `_hydrate_run_origins` dropped unreadable rows and the next save
    deleted them from the document. They are now carried verbatim, as unreadable
    convention rules are, and a readable row for another run is still usable."""
    eid = _record(client)
    exp = ws.load_experiment(eid)
    state = exp.to_state()
    readable = {"acquisition_identity": "synthetic:01@abc", "stem": "01_01_ZZ1"}
    state[ws.HISTORICAL_RUN_ORIGINS_KEY] = {
        "RUN-READABLE": readable,
        "RUN-NOT-A-MAPPING": "SYNTHETIC garbage",
        "RUN-NO-IDENTITY": {"stem": "02_01_ZZ1"},
    }
    hydrated = ws.Experiment.from_state(state)
    assert hydrated.historical_run_origins == {"RUN-READABLE": readable}
    assert set(hydrated.unreadable_run_origins) == {"RUN-NOT-A-MAPPING", "RUN-NO-IDENTITY"}
    written = hydrated.to_state()[ws.HISTORICAL_RUN_ORIGINS_KEY]
    assert written == state[ws.HISTORICAL_RUN_ORIGINS_KEY]
    # a readable row is never written over an unreadable one for the same run
    assert hydrated.record_run_origin("RUN-NO-IDENTITY", {"acquisition_identity": "x"}) is False
    assert hydrated.to_state()[ws.HISTORICAL_RUN_ORIGINS_KEY]["RUN-NO-IDENTITY"] == {"stem": "02_01_ZZ1"}


def test_a_confirmed_assignment_is_not_applied_over_an_ambiguous_channel():
    """Minor finding: a confirmed rule was applied over a channel whose liveness the Run's
    evidence could not decide, and the result then said the channel "carries signal"."""
    assignments = (sig.ChannelAssignment("vortDT", "Zz", "L3", "rule"),)
    selection = sig.select_primary_signal(
        _channels(vortDT="ambiguous"), [ZZ], confirmed_assignments=assignments, rule_ref="r1"
    )
    assert selection.status == sig.STATUS_NEEDS_REVIEW
    assert selection.reason_code == sig.REASON_RULE_UNDECIDED
    assert selection.assignments == ()
    live = sig.select_primary_signal(
        _channels(vortDT="live"), [ZZ], confirmed_assignments=assignments, rule_ref="r1"
    )
    assert live.status == sig.STATUS_CONFIRMED


def test_exactly_the_applicability_levels_this_build_can_reach_are_the_ones_it_claims():
    """Minor finding: seven levels were presented as available and only five are reachable.
    Derived here from every selector shape a rule can carry plus the default binding, and
    compared EXACTLY — so making `facility` reachable without saying so fails this."""
    shapes = [
        {},
        {"legacy_range": [1, 2]},
        {"group_tokens": ["01"]},
        {"stem_prefixes": ["01_"]},
        {"source_types": [ev.SOURCE_TYPE_SCAN_EXPORT]},
        {"source_paths": ["synthetic/file"]},
    ]
    reached = {appl.default_binding().scope}
    for selector in shapes:
        rule = cr.new_rule(
            rule_id=f"R{len(reached)}{len(selector)}", kind=cr.KIND_PROFILE_BINDING,
            scope=cr.SCOPE_IMPORT, body={"profile_id": DEFAULT, "profile_version": "1"},
            selector=selector, confirmed_utc="2099-01-01T00:00:00Z", existing=[],
            import_id="01TESTIMPORT00000000000000",
        )
        reached.add(rule.binding_scope)
    assert reached == set(appl.REACHABLE_SCOPES)
    assert appl.REACHABLE_SCOPES < appl.SCOPES
    assert not appl.REACHABLE_SCOPES & {appl.SCOPE_FACILITY, appl.SCOPE_BEAMLINE}


_RECURRING_RENAME = {
    "kind": "conflict_resolution",
    "selector": {"legacy_range": [1, 3]},
    "body": {
        "conflict_kind": "internal_declaration_vs_filename",
        "chosen_source_role": "human_label",
    },
}


def test_a_convention_scoped_resolution_records_its_convention_and_is_offered_only_where_it_applies(
    client, alk
):
    """Minor finding: a `profile`-scoped resolution recorded no convention (`profile_id`
    None, so `version_is_current` could never be false) and was offered to every
    experiment regardless of the convention its sources follow."""
    eid_a = _record(client, "A")
    import_a = _import(client)
    recorded = _rule(client, import_a, {**_RECURRING_RENAME, "scope": "profile",
                                         "experiment_id": eid_a}, eid=eid_a)
    assert recorded.status_code == 200, recorded.text
    rule = recorded.json()["rule"]
    default = profiles.PROFILES[DEFAULT]
    assert (rule["profile_id"], rule["profile_version"]) == (default.profile_id, default.profile_version)

    # OFFERED where the convention applies…
    eid_b = _record(client, "B")
    view_b = _view(client, _import(client))
    offered = view_b["rules"]["reusable_from_other_experiments"]
    assert [r["rule"]["rule_id"] for r in offered] == [rule["rule_id"]]
    assert offered[0]["matches"]["units"] == 3

    # …and NOT offered to an import whose sources are all read under another convention.
    import_c = _import(client)
    everything_alk = _rule(client, import_c, {
        "kind": "profile_binding", "scope": "import", "selector": {},
        "body": {"profile_id": ALK.profile_id, "profile_version": "1"},
    })
    assert everything_alk.status_code == 200, everything_alk.text
    rules_c = everything_alk.json()["import"]["rules"]
    assert rules_c["reusable_from_other_experiments"] == []
    assert rules_c["reusable_scan"]["not_offered_other_convention"] == 1
    del eid_b


def test_a_convention_scoped_rule_over_two_conventions_is_refused(client, alk):
    eid = _record(client)
    import_id = _import(client)
    _bind_alk(client, import_id)  # 06-08 under the test convention, 01-05 the default
    refused = _rule(client, import_id, {
        "kind": "signal_assignment", "scope": "profile", "experiment_id": eid,
        "selector": {"legacy_range": [5, 6]},
        "body": {"assignments": [{"channel": "vortDT", "element": "Zz", "edge": "L3"}]},
    }, eid=eid)
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"] == "convention_not_determinable"
    assert ws.load_experiment(eid).convention_rules == []


def test_the_reusable_rule_scan_discloses_its_bound(client):
    """Minor finding: `rules.reusable_scan` was promised as the disclosure of the
    200-experiment cap and did not exist."""
    _record(client, "A")
    _record(client, "B")
    scan = _view(client, _import(client))["rules"]["reusable_scan"]
    assert scan["experiments_listed"] == 2
    assert scan["experiments_scanned"] == 2
    assert scan["cap"] == 200 and scan["truncated"] is False
    assert scan["listing_complete"] is True
    assert scan["order"] == "most_recently_created"


#: Raised only when a STORED rule is rehydrated or by invariants the route always
#: satisfies (it always passes the holder's id and the unattributed actor pair) — not a
#: refusal a caller of the route can meet.
_NOT_ROUTE_REACHABLE = {
    "invalid_entry", "invalid_version", "actor_basis_mismatch", "experiment_required",
    "import_required",
}


def test_the_documented_rule_refusals_are_every_one_the_route_can_emit():
    """Minor finding: doc §10.1's list omitted three codes. Derived from the source, so a
    new refusal cannot ship undocumented."""
    import isaac_api.routes as routes_module

    routes_src = Path(routes_module.__file__).read_text(encoding="utf-8")
    segment = routes_src[
        routes_src.index("def _rule_target_problem(")
        : routes_src.index("def get_experiment_convention_rules(")
    ]
    emitted = set(re.findall(r'"error": "([a-z_]+)"', segment))
    rules_src = Path(cr.__file__).read_text(encoding="utf-8")
    emitted |= set(re.findall(r'UnsupportedRule\(\s*"([a-z_]+)"', rules_src)) - _NOT_ROUTE_REACHABLE
    doc = (REPO_ROOT / "docs/historical-import-semantics-2026-09-22.md").read_text(encoding="utf-8")
    listed = doc[doc.index("* `422` errors"): doc.index("**`GET /api/experiments/{experiment_id}/convention-rules`**")]
    missing = sorted(code for code in emitted if f"`{code}`" not in listed)
    assert missing == [], missing
    assert {"invalid_body", "unknown_conflict", "unknown_acquisition_system"} <= emitted
