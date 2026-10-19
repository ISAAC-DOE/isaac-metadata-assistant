"""THE SHORT REASON A SCIENTIST READS — `bl15.mapping.CONCEPT_SUMMARIES` and
`historical_import.plain_reason` (2026-10-18, QA `C-05`/`C-06`).

An independent browser audit measured the import screen showing each candidate's FULL
`not_proposable_reason` — the mapping registry's engineering rationale, verbatim: a median
of ~350 characters and up to 1,318, with struck-through revision history, decision and
question ids, ALL-CAPS asides, one extension-namespace paragraph repeated on about ten
rows, and facts about the archive the registry was measured on stated as though they
described the import on screen.

The fix serves a SHORT sentence beside the full one, and these tests hold its shape:

* every registry concept has one, and every constant short reason passes the same bans;
* on every committed archive and every committed example source, EVERY candidate that
  cannot be sent carries a short reason that is not the fallback, is never the full
  reason itself, and passes the bans — while the full reason is still served beside it;
* the batch's own `not_sent` rows carry one too, so the report and the review agree.

THE BANS ARE THE AUDIT'S OWN LIST: no `~~`, no `DEC-…` or `Q<n>` id, no ISO date, and no
run of three or more ALL-CAPS words. A negative control proves each ban fires on the
registry's FULL reasons, so a ban that silently stopped matching would fail here rather
than pass.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

import isaac_api.capabilities as capabilities
import isaac_api.historical_import as hist
import isaac_api.identity as identity
from isaac_api.bl15 import mapping as mp

MAX_CHARS = 160

BANS: dict[str, re.Pattern[str]] = {
    "struck-through history": re.compile(r"~~"),
    "a decision id": re.compile(r"\bDEC-\d"),
    "a question id": re.compile(r"\bQ\d+\b"),
    "a date": re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b"),
    "an ALL-CAPS run of three words": re.compile(r"\b[A-Z][A-Z'’-]+(?:[\s,;:]+[A-Z][A-Z'’-]+){2,}\b"),
}


def _violations(text: str) -> list[str]:
    found = [name for name, pattern in BANS.items() if pattern.search(text)]
    if len(text) > MAX_CHARS:
        found.append(f"longer than {MAX_CHARS} characters ({len(text)})")
    return found


def _constant_summaries() -> dict[str, str]:
    return {
        name: value
        for name, value in vars(hist).items()
        if name.startswith("PLAIN_REASON_") and isinstance(value, str)
    }


# --- the registry -----------------------------------------------------------------


def test_every_registry_concept_has_a_short_reason():
    assert set(mp.CONCEPT_SUMMARIES) == set(mp.MAPPINGS), (
        "a mapping row without a scientist-facing summary would fall back to a sentence "
        "that says nothing about it"
    )


@pytest.mark.parametrize("concept", sorted(mp.MAPPINGS))
def test_each_registry_summary_obeys_the_bans(concept):
    summary = mp.MAPPINGS[concept].summary
    assert summary.strip(), concept
    assert not _violations(summary), (concept, _violations(summary), summary)
    # NEVER THE RATIONALE ITSELF: a summary equal to the full reason has shortened nothing.
    assert summary != mp.MAPPINGS[concept].reason


def test_the_registry_serves_the_summary_beside_the_full_reason():
    state = mp.MAPPINGS[mp.ev.CONCEPT_ACQUISITION_METHOD].to_state()
    assert state["summary"] == mp.CONCEPT_SUMMARIES[mp.ev.CONCEPT_ACQUISITION_METHOD]
    # The engineering rationale is kept intact, for engineers.
    assert state["reason"] == mp.MAPPINGS[mp.ev.CONCEPT_ACQUISITION_METHOD].reason
    assert "~~" in state["reason"]


@pytest.mark.parametrize("name", sorted(_constant_summaries()))
def test_each_constant_short_reason_obeys_the_bans(name):
    text = _constant_summaries()[name]
    assert not _violations(text), (name, _violations(text), text)


def test_NEGATIVE_CONTROL_the_bans_fire_on_the_full_reasons_they_replace():
    """Each ban matches at least one FULL registry reason (or a constructed one), so a ban
    that silently stopped matching would make the tests above vacuous."""
    full = " ".join(m.reason for m in mp.MAPPINGS.values())
    assert BANS["struck-through history"].search(full)
    assert BANS["a decision id"].search(full)
    assert BANS["an ALL-CAPS run of three words"].search(full)
    assert BANS["a date"].search(full)
    # No full reason carries a bare question id today; the ban is proved on its own text.
    assert BANS["a question id"].search("waiting on Q21")
    assert max(len(m.reason) for m in mp.MAPPINGS.values()) > MAX_CHARS


# --- the candidates, over every committed source ---------------------------------


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv(identity.EDGE_TRUST_VERIFIER_ENV, raising=False)
    monkeypatch.delenv(capabilities.INGESTION_ENV, raising=False)
    monkeypatch.delenv(capabilities.STAGING_ROOT_ENV, raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _read(client, kind: str, name: str) -> dict:
    import_id = client.post("/api/imports", json={"label": "plain"}).json()["import"]["import_id"]
    added = client.post(
        f"/api/imports/{import_id}/sources", json={"kind": kind, "fixture_name": name}
    )
    assert added.status_code == 200, added.text
    assert client.post(f"/api/imports/{import_id}/parse").status_code == 200
    assert client.post(f"/api/imports/{import_id}/reconstruct").status_code == 200
    return client.get(f"/api/imports/{import_id}").json()["import"]


SOURCES = [("archive", name) for name in hist.archive_names()] + [
    ("synthetic_fixture", name) for name in hist.fixture_names()
]


@pytest.mark.parametrize(("kind", "name"), SOURCES)
def test_every_unsendable_candidate_carries_a_plain_short_reason(client, kind, name):
    session = _read(client, kind, name)
    candidates = (session.get("reconstruction") or {}).get("candidates") or []
    unsendable = [c for c in candidates if not c["proposable"]]
    for candidate in unsendable:
        summary = candidate.get("not_proposable_summary")
        assert summary, candidate["candidate_id"]
        assert summary != hist.PLAIN_REASON_FALLBACK, (
            "a committed source reached the fallback — give its reason a short sentence",
            candidate["candidate_id"],
            candidate["not_proposable_reason"],
        )
        assert summary != candidate["not_proposable_reason"]
        assert not _violations(summary), (candidate["candidate_id"], _violations(summary))
        # The full reason is KEPT, served beside it, for "Why, in detail".
        assert candidate["not_proposable_reason"] or candidate["unresolved_reason"]
    for candidate in candidates:
        if candidate["proposable"]:
            assert candidate.get("not_proposable_summary") is None


def test_the_archives_reach_more_than_a_handful_of_distinct_short_reasons(client):
    """VACUITY GUARD: the parametrised test above is only worth something if the corpora
    reach many different reasons. Measured 2026-10-18: 28 and 29 distinct."""
    session = _read(client, "archive", "bl15_synthetic_semantics_corpus")
    distinct = {
        c["not_proposable_summary"]
        for c in session["reconstruction"]["candidates"]
        if not c["proposable"]
    }
    assert len(distinct) >= 20


def test_the_session_mapping_block_serves_summaries(client):
    session = _read(client, "archive", "bl15_synthetic_mini_corpus")
    concepts = session["corpus_review"]["mapping"]["concepts"]
    assert concepts
    for row in concepts:
        assert row["summary"] == mp.CONCEPT_SUMMARIES[row["concept"]]
        assert row["reason"] == mp.MAPPINGS[row["concept"]].reason


def test_the_batch_reports_the_short_reason_beside_the_full_one(client):
    session = _read(client, "archive", "bl15_synthetic_mini_corpus")
    created = client.post("/api/experiments", json={"title": "plain reasons"})
    assert created.status_code in (200, 201), created.text
    body = created.json()
    eid = body.get("id") or body["experiment"]["id"]
    etag = client.get(f"/api/experiments/{eid}").headers["ETag"]
    report = client.post(
        f"/api/imports/{session['import_id']}/add-to-experiment",
        json={"experiment_id": eid, "create_runs": True},
        headers={"If-Match": etag},
    )
    assert report.status_code == 200, report.text
    rows = report.json()["not_sent"]
    assert rows
    for row in rows:
        assert row["summary"], row["candidate_id"]
        assert row["summary"] != hist.PLAIN_REASON_FALLBACK, row
        assert not _violations(row["summary"]), row
        assert row["reason"]


def test_plain_reason_is_none_only_for_a_candidate_with_nothing_to_explain():
    assert hist.plain_reason(None) is None
    assert hist.plain_reason(None, unresolved=True) == hist.PLAIN_REASON_DISAGREEMENT
    assert hist.plain_reason("anything", kind=hist.CANDIDATE_KIND_RUN) == hist.PLAIN_REASON_NOT_A_VALUE
    assert hist.plain_reason("an unknown sentence.") == hist.PLAIN_REASON_FALLBACK
    entry = mp.MAPPINGS[mp.ev.CONCEPT_FILTER]
    assert hist.plain_reason(entry.reason, candidate_id="stem::filter") == entry.summary
    # A resolved derivative names its concept one segment earlier.
    assert hist.plain_reason(entry.reason, candidate_id="stem::filter::resolved") == entry.summary


# --- a structural finding with nothing to choose is not called a disagreement ----------


def _structural(session: dict) -> list[dict]:
    return [
        c
        for c in session["reconstruction"]["candidates"]
        if c["kind"] != "field" and c["unresolved_reason"]
    ]


def test_a_finding_against_an_absence_is_not_called_a_disagreement_to_decide(client):
    """Independent review, 2026-10-18: every unresolved structural candidate got
    "The sources disagree … It is decided in Conflicts", but `acquired_never_declared` is one
    file against the ABSENCE of a declaration (a reading whose source is `(…)`), which the
    Conflicts stage shows as "Noted — nothing to choose". The short reason now says the same
    thing the stage does; a real disagreement keeps the disagreement sentence."""
    session = _read(client, "archive", "bl15_synthetic_semantics_corpus")
    rows = _structural(session)
    noted = [c for c in rows if c["supporting_statements"][0]["key"] == "acquired_never_declared"]
    real = [c for c in rows if c["supporting_statements"][0]["key"] == "internal_declaration_vs_filename"]
    assert noted and real  # VACUITY: the corpus holds both kinds (measured 3 and 3)
    for c in noted:
        assert c["not_proposable_summary"] == hist.PLAIN_REASON_NOTED, c["candidate_id"]
    for c in real:
        assert c["not_proposable_summary"] == hist.PLAIN_REASON_STRUCTURAL, c["candidate_id"]


def test_the_batch_reports_the_same_short_reason_for_a_noted_finding(client):
    session = _read(client, "archive", "bl15_synthetic_semantics_corpus")
    created = client.post("/api/experiments", json={"title": "noted finding"})
    body = created.json()
    eid = body.get("id") or body["experiment"]["id"]
    etag = client.get(f"/api/experiments/{eid}").headers["ETag"]
    report = client.post(
        f"/api/imports/{session['import_id']}/add-to-experiment",
        json={"experiment_id": eid, "create_runs": True},
        headers={"If-Match": etag},
    )
    assert report.status_code == 200, report.text
    by_id = {c["candidate_id"]: c for c in _structural(session)}
    checked = 0
    for row in report.json()["not_sent"]:
        if row["candidate_id"] in by_id:
            assert row["summary"] == by_id[row["candidate_id"]]["not_proposable_summary"], row
            checked += 1
    assert checked == len(by_id) > 0
