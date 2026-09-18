"""THE EXTENDED CONTEXT READ SURFACE — `CTX-004`.

WHAT THIS FILE IS FOR
=====================

`CTX-002` made the `DEC-41` level-4 companion durable, exported and served on the
wire. `CTX-004` measured where it stopped, and this file pins each of those findings
as a property rather than as a description of the code that closed it:

1. **The companion was reachable only through `GET .../artifacts`, which serves it
   only once a record has been EXPORTED.** So a record that had imported extended
   context and had not yet exported had NO read surface for it, in any client. The
   route this file exercises answers from the record's own durable state, so the
   entries are readable the moment they are written — and
   ``test_the_companion_is_readable_before_any_export`` is the guard, written as the
   defect rather than as the fix: it asserts the artifacts route reports nothing
   while the new route reports the entries, in the same request pair.

2. **`extended_context_dropped` conflated THREE causes under a name two comments
   described as one.** ``_extended_context_entries`` incremented one integer at three
   sites — the tail cap, the per-source dedup, and the ``except ValueError`` branch
   for a statement the build cannot place — while
   ``MAX_EXTENDED_CONTEXT_ENTRIES``'s own comment and that function's docstring both
   said "the tail", and the attribute's docstring said two of the three. **No test
   asserted over any of them**, which is how it survived. The three are now separate
   and this file pins that they are never summed.

3. **No MCP tool could reach the companion**, so an agent asked what extra scientific
   context a record holds had to answer that it could not see any.

WHAT IS DELIBERATELY NOT ASSERTED HERE
======================================

Nothing here asserts that a companion entry is CORRECT science, and nothing asserts
that the presence or absence of extended context changes a record's validity — it
does not, structurally, and ``test_extended_context_wiring.py`` already owns that
property. This file is about whether a reader can SEE what is there.

DATA BOUNDARY: none. Every workspace is a ``tmp_path``; the only archive read is
``tests/fixtures/bl15/gold/mini_corpus``, committed sanitized fixtures whose sample
names and motor values are unmistakably synthetic. No database connection is opened,
no migration is applied, nothing under ``examples/`` is read, and no model sees
anything.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import isaac_api.extended_context as ctx
import isaac_api.extended_context_view as view
import isaac_api.historical_import as hist
import isaac_api.identity as identity
import isaac_api.workspace as ws
from isaac_api.bl15 import mapping as mp
from isaac_api.mcp import policy
from isaac_api.mcp.tools import TOOLS


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv(identity.EDGE_TRUST_VERIFIER_ENV, raising=False)
    return ws


@pytest.fixture()
def client(workspace):
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _entry(entry_id: str, **over) -> ctx.ContextEntry:
    """One unmistakably synthetic level-4 entry.

    The concept is a real level-4 registry concept because ``ContextEntry`` checks
    the placement against the registry at construction — `DEC-41`'s first rule makes
    an entry at a disagreeing level unbuildable rather than merely wrong.
    """
    body = {
        "entry_id": entry_id,
        "concept": "spec_user_string",
        "raw_literal": "SYNTHETIC-USER-STRING",
        "source": "synthetic/mini/01_SYN1.0001",
        "locator": "line 3 header #C",
        "placement_level": mp.PLACEMENT_EXTENDED_CONTEXT,
    }
    body.update(over)
    return ctx.ContextEntry(**body)


def _record_with_context(client, entries) -> str:
    """A record created through the product's own route, then given a companion.

    The record is created over HTTP rather than through ``ws.create_experiment`` so
    this file starts where a scientist starts — the blind spot
    ``test_scientist_can_finish_a_record.py`` exists for, applied to a read surface.
    """
    created = client.post("/api/experiments", json={"title": "Extended context read"})
    assert created.status_code == 201, created.text
    eid = created.json()["id"]
    exp = ws.load_experiment(eid)
    assert exp is not None
    exp.add_extended_context_entries(entries, generated_utc="2026-09-18T00:00:00Z")
    assert exp.save_versioned() is True
    return eid


# =============================================================================
# 1 — the finding: readable BEFORE an export, which is when it is needed
# =============================================================================


def test_the_companion_is_readable_before_any_export(client):
    """THE `CTX-004` FINDING, written as the defect rather than as the fix.

    Both routes are asked about the SAME unexported record in the same test, so the
    assertion is a contrast rather than a claim about one endpoint: the artifacts
    route — the only surface that served the companion before this slice — reports
    nothing at all, and the new route reports the entries. Inverting the new route's
    answer to null would leave the record with no read surface again, which is
    exactly the state this closes.
    """
    eid = _record_with_context(client, [_entry("e1"), _entry("e2")])

    artifacts = client.get(f"/api/experiments/{eid}/artifacts")
    assert artifacts.status_code == 200, artifacts.text
    # The pre-existing surface, on a record that holds two entries.
    assert artifacts.json()["extended_context"] is None
    assert artifacts.json()["extended_context_filename"] is None

    read = client.get(f"/api/experiments/{eid}/extended-context")
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["present"] is True
    assert body["total"] == 2
    assert [e["entry_id"] for e in body["entries"]] == ["e1", "e2"]


def test_a_record_with_no_companion_is_a_stated_fact_and_not_an_error(client):
    """ABSENT IS THE NORMAL STATE and must not read as a failure or a missing file.

    ``200`` with ``present: false`` and ``entry_count: 0``, never a 404 and never a
    refusal. ``routes.get_artifacts``'s own comment argues the same point for the
    exported file — folding the companion into its ``stale`` decision "would make
    every record without extended context report a missing artifact" — and this is
    that reasoning held at the new route.
    """
    created = client.post("/api/experiments", json={"title": "No context"})
    assert created.status_code == 201, created.text
    read = client.get(f"/api/experiments/{created.json()['id']}/extended-context")
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["present"] is False
    assert body["entry_count"] == 0
    assert body["total"] == 0
    assert body["entries"] == []
    assert body["unreadable_entries"] == 0


def test_an_unknown_record_is_a_404_and_not_an_empty_companion(client):
    """The one case that IS an error, kept distinct from the one above.

    An empty page for an unknown id would say "this record states no extended
    context", which is a claim about a record that does not exist.
    """
    assert client.get("/api/experiments/not-a-record/extended-context").status_code == 404


# =============================================================================
# 2 — the bound, and the counts that must not come from the page
# =============================================================================


def test_every_count_describes_the_record_and_only_returned_describes_the_page(client):
    """`CLAUDE.md` §11's 2026-09-02 rule, asserted where it is easy to break.

    The window bounds what is FETCHED, never what is CLAIMED. With a page of 2 over
    a record of 5, ``total``, ``entry_count`` and ``matched`` must all read 5 and
    only ``returned`` may read 2. A surface built on ``len(entries)`` would report a
    five-entry record as a two-entry one.
    """
    eid = _record_with_context(client, [_entry(f"e{i}") for i in range(5)])
    read = client.get(f"/api/experiments/{eid}/extended-context?limit=2")
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["total"] == 5
    assert body["entry_count"] == 5
    assert body["matched"] == 5
    assert body["returned"] == 2
    assert len(body["entries"]) == 2
    assert body["has_more"] is True


def test_offset_pages_the_whole_record_without_repeating_or_skipping_an_entry(client):
    """Stable paging, asserted over the UNION rather than over one page.

    ``offset`` is safe here because the companion is append-only — there is no
    remove and no replace — so a position already read cannot shift. The assertion
    is that walking the pages yields every entry exactly once, which a fencepost
    error in either direction breaks.
    """
    eid = _record_with_context(client, [_entry(f"e{i}") for i in range(5)])
    seen: list[str] = []
    offset = 0
    while True:
        body = client.get(
            f"/api/experiments/{eid}/extended-context?limit=2&offset={offset}"
        ).json()
        seen.extend(e["entry_id"] for e in body["entries"])
        if not body["has_more"]:
            break
        offset += body["returned"]
    assert seen == [f"e{i}" for i in range(5)]


def test_an_oversized_limit_is_clamped_and_the_clamp_is_reported(client):
    """CLAMPED, NEVER REFUSED, and never silently — ``activity_history``'s rule.

    A ``422`` would make a client guess the ceiling; a silent clamp would make it
    believe it had asked for and received everything.
    """
    eid = _record_with_context(client, [_entry("e1")])
    body = client.get(f"/api/experiments/{eid}/extended-context?limit=100000").json()
    assert body["limit"] == view.EXTENDED_CONTEXT_LIMIT_MAX


def test_a_negative_limit_or_offset_is_refused_by_the_route(client):
    """A malformed value in a REQUEST may be refused — `CLAUDE.md` §11's rule.

    The distinction that rule draws is the point: this is the caller's own input, so
    a typed refusal names what to fix. A malformed PERSISTED value is the opposite
    case and is read, which the unreadable-entries test below covers.
    """
    eid = _record_with_context(client, [_entry("e1")])
    assert client.get(f"/api/experiments/{eid}/extended-context?limit=-1").status_code == 422
    assert client.get(f"/api/experiments/{eid}/extended-context?offset=-1").status_code == 422


# =============================================================================
# 3 — the filters, and the claim each one makes
# =============================================================================


def test_a_run_filter_returns_what_APPLIES_to_the_run_including_what_it_inherits(client):
    """``applying_to_run`` AND NOT ``for_run``, asserted because they differ.

    The model is emphatic that the two are different claims. Serving the narrow one
    would hide every beamtime-wide reading — the statements a reader asking "what
    context applies to this measurement?" most needs — and would hide them silently,
    because a short list looks like a complete one. The inheritance stays VISIBLE:
    each returned entry still carries its own ``scope``.
    """
    eid = _record_with_context(
        client,
        [
            _entry("shared"),
            _entry("own", scope=ctx.SCOPE_RUN, run_id="run-a"),
            _entry("other", scope=ctx.SCOPE_RUN, run_id="run-b"),
        ],
    )
    body = client.get(f"/api/experiments/{eid}/extended-context?run_id=run-a").json()
    assert [e["entry_id"] for e in body["entries"]] == ["shared", "own"]
    assert body["matched"] == 2
    # …and the record's own total is unchanged by a filter.
    assert body["total"] == 3
    # The inheritance is legible rather than flattened.
    assert [e["scope"] for e in body["entries"]] == ["experiment", "run"]


def test_a_concept_filter_matches_exactly_and_is_never_fuzzy(client):
    """An exact match, because a concept name is an identifier the registry owns.

    Matching loosely would answer a question the caller did not ask, under the
    caller's own label.
    """
    eid = _record_with_context(
        client, [_entry("a"), _entry("b", concept="spec_comment_lines")]
    )
    exact = client.get(
        f"/api/experiments/{eid}/extended-context?concept=spec_comment_lines"
    ).json()
    assert [e["entry_id"] for e in exact["entries"]] == ["b"]
    # A prefix of a real concept matches nothing, rather than matching by substring.
    partial = client.get(f"/api/experiments/{eid}/extended-context?concept=spec_").json()
    assert partial["entries"] == []
    # And an unknown concept is ANSWERED, not refused — deliberately unlike
    # `list_activity`'s closed vocabularies. `extended_context` admits a concept the
    # registry has not examined (that is what level 4 is for), so refusing an
    # unregistered name would refuse a filter that may legitimately match.
    unknown = client.get(f"/api/experiments/{eid}/extended-context?concept=zzz")
    assert unknown.status_code == 200
    assert unknown.json()["matched"] == 0
    assert unknown.json()["total"] == 2


# =============================================================================
# 4 — the claims the payload must carry, and the one it must never make
# =============================================================================


def test_no_entry_is_ever_an_official_field_value_on_the_wire(client):
    """The one claim a surface must not get wrong about these entries.

    Asserted over the SERVED payload rather than over the dataclass, because the
    property is derived on the model and a projection at the route could have
    dropped it — which is how a claim survives a unit test and fails on the wire.
    """
    eid = _record_with_context(client, [_entry("e1"), _entry("e2")])
    body = client.get(f"/api/experiments/{eid}/extended-context").json()
    assert body["entries"]
    for entry in body["entries"]:
        assert entry["is_official_field_value"] is False
    assert body["not_official"] == ctx.NOT_OFFICIAL_CLAIM
    assert body["placement_hierarchy"]["4"] == mp.PLACEMENT_NAMES[
        mp.PLACEMENT_EXTENDED_CONTEXT
    ]


def test_every_entry_carries_its_provenance_verbatim(client):
    """`DEC-41`'s four, on the wire, unrewritten.

    The literal in particular: ``raw_literal`` is what the source said, and the read
    surface neither trims, normalises, converts nor shortens it. A value stripped of
    where it came from is the prose dump the companion exists to not be.
    """
    eid = _record_with_context(
        client, [_entry("e1", raw_literal="  ffilter35  \tspaced ")]
    )
    entry = client.get(f"/api/experiments/{eid}/extended-context").json()["entries"][0]
    assert entry["raw_literal"] == "  ffilter35  \tspaced "
    assert entry["source"] == "synthetic/mini/01_SYN1.0001"
    assert entry["locator"] == "line 3 header #C"
    assert entry["concept"] == "spec_user_string"


def test_an_unreadable_stored_entry_is_counted_and_never_rendered(client):
    """`CLAUDE.md` §11's persisted-value rule, held at a READ surface.

    A row this build cannot read belongs to a reader who did nothing wrong, so it is
    neither dropped nor coerced nor allowed to 500 the read. It is carried and
    COUNTED — and it is not rendered, because nothing can say what it contains
    without inventing it.

    The two halves matter separately, which is why both are asserted: ``present`` is
    ``True`` (a document exists) while ``entry_count`` is ``0`` (nothing in it is
    readable). Collapsing those would make an unreadable companion look like no
    companion, which is the one outcome ``hydrate``'s "never discards" promise exists
    to prevent.
    """
    created = client.post("/api/experiments", json={"title": "Unreadable"})
    eid = created.json()["id"]
    exp = ws.load_experiment(eid)
    assert exp is not None
    exp.extended_context = ctx.hydrate(
        {"entries": [{"entry_id": "broken"}]}, experiment_id=eid
    )
    assert exp.save_versioned() is True

    body = client.get(f"/api/experiments/{eid}/extended-context").json()
    assert body["present"] is True
    assert body["entry_count"] == 0
    assert body["total"] == 0
    assert body["entries"] == []
    assert body["unreadable_entries"] == 1


# =============================================================================
# 5 — the three counts that used to be one integer
# =============================================================================


def test_the_three_import_costs_are_separate_integers_and_are_never_summed():
    """THE CONFLATION `CTX-004` FOUND, pinned so it cannot be re-merged.

    ``_extended_context_entries`` incremented ONE counter at three sites while two
    comments described it as the tail cap alone. The three causes have different
    significance to a scientist — a bound, a lossless thinning, and a build
    limitation — and a disclosure over their sum cannot say which happened.

    This drives the function directly rather than through an archive, because the
    tail cap needs more than ``MAX_EXTENDED_CONTEXT_ENTRIES`` distinct statements
    and the dedup needs a repeat, and a fixture that produced both would be a
    fixture nobody could read.
    """

    class _Ev:
        """The five attributes ``entry_from_source_evidence`` reads. Nothing more."""

        def __init__(self, literal: str, path: str):
            self.concept = "spec_user_string"
            self.raw_literal = literal
            self.source_path = path
            self.locator = "line 1"
            self.source_type = "unknown"
            self.normalized_value = None
            self.unit = None
            self.normalization_rule = None
            self.determinism = "read"
            self.profile_id = None
            self.profile_version = None
            self.scope = None
            self.parser_id = None
            self.timestamp_utc = None
            self.evidence_id = f"{path}::{literal}"

    # Two identical statements in ONE source: one kept, one THINNED, none dropped.
    rows, dropped, thinned, unplaceable = hist._extended_context_entries(
        {"src/a": [_Ev("X", "src/a"), _Ev("X", "src/a")]}
    )
    assert len(rows) == 1
    assert (dropped, thinned, unplaceable) == (0, 1, 0)

    # The SAME literal from a DIFFERENT source is a different key and is KEPT — the
    # property `extended_context.build` insists on, because collapsing sixteen files
    # each recording one filter index would destroy fifteen locators.
    rows, dropped, thinned, unplaceable = hist._extended_context_entries(
        {"src/a": [_Ev("X", "src/a")], "src/b": [_Ev("X", "src/b")]}
    )
    assert len(rows) == 2
    assert (dropped, thinned, unplaceable) == (0, 0, 0)


def test_the_tail_cap_reports_dropped_and_not_thinned():
    """The cap alone, which is what its own comment always claimed it counted."""

    class _Ev:
        def __init__(self, n: int):
            self.concept = "spec_user_string"
            self.raw_literal = f"X{n}"
            self.source_path = "src/a"
            self.locator = f"line {n}"
            self.source_type = "unknown"
            self.normalized_value = None
            self.unit = None
            self.normalization_rule = None
            self.determinism = "read"
            self.profile_id = None
            self.profile_version = None
            self.scope = None
            self.parser_id = None
            self.timestamp_utc = None
            self.evidence_id = f"e{n}"

    over = hist.MAX_EXTENDED_CONTEXT_ENTRIES + 3
    rows, dropped, thinned, unplaceable = hist._extended_context_entries(
        {"src/a": [_Ev(n) for n in range(over)]}
    )
    assert len(rows) == hist.MAX_EXTENDED_CONTEXT_ENTRIES
    assert dropped == 3
    # NOT folded into `dropped`, and NOT folded into each other.
    assert thinned == 0
    assert unplaceable == 0


def test_the_corpus_review_serves_the_three_costs_beside_the_ceiling(client):
    """The disclosure's own data, on the wire, with the bound it refers to.

    A surface that had to transcribe ``MAX_EXTENDED_CONTEXT_ENTRIES`` to say which
    limit applied would hold a second copy of it — the rule ``candidate_ceiling``
    two blocks away in the same payload already follows.
    """
    created = client.post("/api/imports", json={"label": "BL15-2 historical"})
    import_id = created.json()["import"]["import_id"]
    added = client.post(
        f"/api/imports/{import_id}/sources",
        json={
            "kind": "archive",
            "fixture_name": "bl15_synthetic_mini_corpus",
            "filename": "BL15-2 corpus",
        },
    )
    assert added.status_code == 200, added.text
    assert client.post(f"/api/imports/{import_id}/parse").status_code == 200

    session = client.get(f"/api/imports/{import_id}").json()["import"]
    block = session["corpus_review"]["extended_context"]
    assert set(block) == {
        "available",
        "dropped",
        "thinned",
        "unplaceable",
        "ceiling",
        "not_official",
    }
    assert block["ceiling"] == hist.MAX_EXTENDED_CONTEXT_ENTRIES
    assert block["not_official"] == ctx.NOT_OFFICIAL_CLAIM
    # Every cost is a non-negative integer and none is a bool masquerading as one.
    for key in ("available", "dropped", "thinned", "unplaceable"):
        assert isinstance(block[key], int) and not isinstance(block[key], bool)
        assert block[key] >= 0


# =============================================================================
# 6 — the MCP read
# =============================================================================


def test_the_mcp_tool_is_a_read_that_adds_no_write():
    """`tools.py`'s header property, held over the new member.

    That header states a PROPERTY rather than a tally, because a hand-maintained
    count drifted: *every write touches DRAFT content only*. A read tool must not
    change what that sentence is true of, so this asserts the tool's own posture and
    its operation's, in both places a caller could read them.
    """
    tool = TOOLS["isaac_get_extended_context"]
    assert tool.scope is policy.Scope.READ
    assert tool.read_only is True
    assert tool.idempotent is True
    operation = policy.OPERATIONS["get_extended_context"]
    assert operation.method == "GET"
    assert operation.mutates is False
    assert operation.requires_if_match is False
    assert operation.scope is policy.Scope.READ


def test_the_tool_schema_is_derived_from_the_route_and_not_transcribed():
    """No second copy of the route's parameter set, and none of its bounds.

    The derivation is the reason ``policy._query_parameters`` exists: a transcribed
    set can advertise a filter the route does not have (FastAPI ignores unknown
    query parameters, so the call succeeds and silently returns an unfiltered list —
    a tool lying about what it did) or omit one the route does have.
    """
    schema = TOOLS["isaac_get_extended_context"].input_schema
    assert set(schema["properties"]) == {
        "experiment_id",
        "limit",
        "offset",
        "run_id",
        "concept",
    }
    assert schema["required"] == ["experiment_id"]
    # Both strings carry the ROUTE's own bound, so no `_DECLARED_STRING_BOUNDS`
    # entry is involved and there is nothing to drift.
    from isaac_api import routes

    assert schema["properties"]["run_id"]["maxLength"] == routes._CONTEXT_FILTER_MAX
    assert schema["properties"]["concept"]["maxLength"] == routes._CONTEXT_FILTER_MAX


def test_the_tool_name_carries_no_forbidden_capability_token():
    """Checked at import for every tool; asserted here for this one by name.

    ``forbidden_tool_reason`` refuses a forbidden token BEFORE it checks the
    permitted set, so adding a name to ``PERMITTED_TOOL_NAMES`` is not a way to
    smuggle one past. This pins that the new name passes the first check and not
    merely the second.
    """
    assert policy.forbidden_tool_reason("isaac_get_extended_context") is None
    for token in policy.FORBIDDEN_TOOL_TOKENS:
        assert token not in "isaac_get_extended_context"


def test_the_route_path_carries_no_forbidden_path_token():
    """`extended-context` contains no forbidden substring, and `export` is the trap.

    ``FORBIDDEN_PATH_TOKENS`` holds ``export``, the check is a plain substring test,
    and this path is one letter-sequence away from a family that would have been
    refused at import. Asserted rather than assumed.
    """
    path = policy.OPERATIONS["get_extended_context"].path_template
    for token in policy.FORBIDDEN_PATH_TOKENS:
        assert token not in path.lower(), f"{token!r} in {path!r}"


def test_the_view_modules_bounds_are_the_ones_the_route_publishes():
    """One source for the window and the ceiling, so a description cannot drift."""
    assert view.EXTENDED_CONTEXT_WINDOW == 50
    assert view.EXTENDED_CONTEXT_LIMIT_MAX == 200
    # The route's own description quotes both, built from these constants rather
    # than from literals — so a change here changes the published text too.
    from isaac_api import routes

    assert str(view.EXTENDED_CONTEXT_WINDOW) in routes._CONTEXT_LIMIT_DESC
    assert str(view.EXTENDED_CONTEXT_LIMIT_MAX) in routes._CONTEXT_LIMIT_DESC
