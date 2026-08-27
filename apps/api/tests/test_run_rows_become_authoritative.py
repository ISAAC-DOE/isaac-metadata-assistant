"""STAGE 2b — the proof suite for moving the run list's authority onto `isaac_runs`.

WHAT THIS FILE PROVES, AND WHAT IT DELIBERATELY CANNOT
======================================================
The contract is `docs/isaac-runs-stage-2-contract.md` §7, written before the
reader existed. Stage 2b is exactly one sentence of behaviour:

    When hydrating an experiment whose run projection is COMPLETE, build the
    restored document's `runs` key from `isaac_runs` rows instead of from
    `state["runs"]`. Nothing else moves.

That is also where a silent-data-loss bug would live, which is why the suite is
organised around the three phases §7.5 names — BEFORE completeness, DURING the
transition, AFTER completeness — plus a NEGATIVE CONTROL that proves the suite
can fail.

THE DRIVER IS THE IN-PROCESS FAKE, and its limits are stated rather than left to
inference. `FakeConnection` models `to_regclass` per parameter, punishes a
statement naming an absent relation with the real SQLSTATE, and now models the
projection row's CONTENT (it did not need to while nothing read it). So these
cases prove WHICH STATEMENTS ARE ISSUED, WITH WHICH PARAMETERS, and WHAT THE
RESTORED DOCUMENT CONTAINS. They do NOT prove the SQL is valid PostgreSQL, that
`= ANY(%s::text[])` binds as intended, or that the server's `ORDER BY ordinal,
state ->> 'created_utc', run_id` sorts as `sorted_runs` does. CI's `postgres:18`
service is where a real engine answers those; `test_run_row_parity.py` is where
the real-engine cases live, and this slice ADDS NONE — the existing pod-restart
parity case already covers a real-engine hydration and is unchanged by it.

WHY THE FAKE IS ENOUGH FOR THE DANGEROUS HALF. The failure this contract exists
to make unwritable is not a SQL bug — it is a reader that treats "no rows" as
"no runs" and silently deletes every run of every pre-existing record while
reporting success. That failure is a decision made from values, in
`resolve_run_authority`, and values are exactly what a fake can drive.
"""

from __future__ import annotations

import json

import pytest

import isaac_api.db_write as dbw  # noqa: F401 - used via _durable_client
import isaac_api.experiment_repository as repo
import isaac_api.workspace as ws

from test_experiment_repository import (  # noqa: E402
    FakeConnection,
    _connector,
    _durable_client,
    _env,
)

pytestmark = pytest.mark.usefixtures("_clear_storage_observation")


# =============================================================================
# harness
# =============================================================================


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """The same app fixture `test_experiment_repository` uses, for the same reasons."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv("ISAAC_RUN_ROWS_AUTHORITATIVE", raising=False)
    from isaac_api.app import create_app

    return create_app()


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("ISAAC_RUN_ROWS_AUTHORITATIVE", raising=False)
    return tmp_path / "ws"


def _experiment(*labels, rid="01ABCDEFGHJKMNPQRSTVWXYZ00", title="Runs"):
    exp = ws.Experiment(
        id=rid,
        title=title,
        created_utc="2026-01-01T00:00:00Z",
        source={},
        draft={},
    )
    for label in labels:
        exp.add_run(label=label)
    return exp


def _with_runs(exp, *runs):
    """Append already-built `ws.Run` objects, for shapes `add_run` cannot mint."""
    exp.runs.extend(runs)
    return exp


def _store(conn, env=None):
    return repo.PostgresOrdinaryStore(env or _env(), connect=_connector(conn))


def _publish(conn, exp):
    """Make `isaac_experiments` hold this experiment's CURRENT document.

    The fake models `Q_ALL_EXPERIMENTS` from `conn.rows`, and `Q_UPSERT_EXPERIMENT`
    deliberately does not maintain that list — it records the row's EXISTENCE, not
    its content, because until Stage 2b nothing read a stored document back except
    on a refusal. Setting it here is what makes "the document the reader sees" an
    explicit knob, which is what the STALE and CONCURRENT cases below need.
    """
    conn.rows = [(exp.id, json.dumps(exp.to_state()))]


def _wipe(root, exp):
    """The pod restart, in one line: the workspace directory is gone."""
    path = root / exp.id / "experiment.json"
    if path.exists():
        path.unlink()


def _restored(root, exp):
    return json.loads((root / exp.id / "experiment.json").read_text())


def _restore(conn, exp, root, env=None):
    """One hydration pass over a workspace that is missing this record."""
    _wipe(root, exp)
    _store(conn, env).hydrate()
    return _restored(root, exp)


def _persist_publish_restore(conn, exp, root, env=None):
    """The whole round trip: save durably, lose the workspace, hydrate it back."""
    _store(conn, env).persist(exp)
    _publish(conn, exp)
    return _restore(conn, exp, root, env)


def _authority():
    """The distribution the last classifying hydration pass measured."""
    return repo.run_authority_summary()


def _only(state):
    """Assert the last pass classified exactly one experiment, in `state`."""
    summary = _authority()
    assert summary is not None, "the pass classified nothing at all"
    assert summary[state] == 1, summary
    assert sum(summary.values()) == 1, summary
    return summary


# =============================================================================
# 1. the predicate itself — pure, exhaustive, and no database in sight
# =============================================================================
#
# `resolve_run_authority` is where every decision that could delete a scientist's
# runs is made. It is a pure function of values, so it is tested as one.


def _doc(rev=3, generation="gen-a", run_ids=("r1", "r2")):
    return {
        "id": "01ABCDEFGHJKMNPQRSTVWXYZ00",
        "rev": rev,
        "generation": generation,
        "runs": [{"id": rid, "label": rid} for rid in run_ids],
    }


def _rows(*run_ids):
    return [(rid, {"id": rid, "label": rid}) for rid in run_ids]


def test_the_four_states_are_distinguished_and_only_one_of_them_uses_the_rows():
    """CONTRACT §2.1, the whole table, in one case so the four cannot drift apart.

    Three of the four read the DOCUMENT, and that is NORMAL OPERATION rather than
    an error path — which is why the assertion is on `runs is None` for each of
    them rather than on an exception.
    """
    document = _doc()
    matching = (3, "gen-a")

    assert repo.resolve_run_authority(
        document, None, [], tables_present=False
    ) == (repo.RUN_AUTHORITY_UNAVAILABLE, None)
    assert repo.resolve_run_authority(
        document, None, [], tables_present=True
    ) == (repo.RUN_AUTHORITY_NEVER_PROJECTED, None)
    assert repo.resolve_run_authority(
        document, (2, "gen-a"), _rows("r1", "r2"), tables_present=True
    ) == (repo.RUN_AUTHORITY_STALE, None)
    state, runs = repo.resolve_run_authority(
        document, matching, _rows("r1", "r2"), tables_present=True
    )
    assert state == repo.RUN_AUTHORITY_COMPLETE
    assert runs == [{"id": "r1", "label": "r1"}, {"id": "r2", "label": "r2"}]


def test_UNAVAILABLE_wins_even_when_a_projection_row_was_somehow_read():
    """The table check is FIRST, and it is not a shortcut for `projection is None`.

    An environment where `isaac_run_projection` is absent cannot have produced a
    row; asserting the order anyway is what stops a future edit from deciding
    UNAVAILABLE by "no row" and silently relabelling every un-migrated deployment
    as NEVER PROJECTED — two states §7.6 requires an operator to tell apart.
    """
    assert repo.resolve_run_authority(
        _doc(), (3, "gen-a"), _rows("r1", "r2"), tables_present=False
    ) == (repo.RUN_AUTHORITY_UNAVAILABLE, None)


def test_a_matching_pair_with_ZERO_rows_is_COMPLETE_and_means_zero_runs():
    """THE STATE STAGE 1 COULD NOT EXPRESS, and the reason `0005` exists at all.

    `run_count = 0` beside a matching version pair is a POSITIVE statement that
    this experiment has no runs — not an absence of information. A reader that
    could not say this would fall back forever for every empty record and the
    cutover could never be measured complete.
    """
    document = _doc(run_ids=())
    assert repo.resolve_run_authority(
        document, (3, "gen-a"), [], tables_present=True
    ) == (repo.RUN_AUTHORITY_COMPLETE, [])


@pytest.mark.parametrize(
    "projection",
    [
        (2, "gen-a"),  # rev behind
        (4, "gen-a"),  # rev AHEAD — still not equal, still not usable
        (3, "gen-b"),  # a delete-and-recreate at the same rev
        (None, "gen-a"),  # a stamp whose rev could not be read
    ],
)
def test_the_pair_is_compared_as_a_PAIR_and_any_difference_is_STALE(projection):
    """CONTRACT §2.2 invariant 2 and §7.2 row 2: never `rev` alone.

    `generation` is what makes a delete-and-recreate distinguishable at rev 0, so
    `(3, 'gen-b')` must be STALE even though the revs agree. And a rev AHEAD of
    the document is not "newer, therefore better": the stamp describes a document
    this reader is not holding, so the rows it claims are not the rows for this
    document.
    """
    assert repo.resolve_run_authority(
        _doc(), projection, _rows("r1", "r2"), tables_present=True
    ) == (repo.RUN_AUTHORITY_STALE, None)


@pytest.mark.parametrize(
    "document",
    [
        {"rev": "not a number", "generation": "gen-a", "runs": []},
        {"rev": None, "generation": "gen-a", "runs": []},
        {"generation": "gen-a", "runs": []},
        {"rev": 3, "runs": []},
        {"rev": 3, "generation": "", "runs": []},
        {"rev": 3, "generation": 7, "runs": []},
    ],
)
def test_a_document_that_cannot_state_its_own_version_is_never_COMPLETE(document):
    """FAIL-CLOSED, and `None` is deliberately never equal to anything.

    COMPLETE is the one verdict that lets the rows replace the document, so a
    document whose version cannot be read must not be able to reach it. Coercing
    an unreadable `rev` to `0` — the obvious alternative — would make a stamp at
    rev 0 match it.
    """
    state, runs = repo.resolve_run_authority(
        document, (3, "gen-a"), [], tables_present=True
    )
    assert state == repo.RUN_AUTHORITY_STALE
    assert runs is None


@pytest.mark.parametrize(
    "document_ids,row_ids",
    [
        (("r1", "r2"), ("r1",)),  # a row deleted out of band
        (("r1",), ("r1", "r2")),  # a row the document does not name
        (("r1", "r2"), ("r1", "r3")),  # one substituted
        (("r1", "r1"), ("r1",)),  # a duplicate the PK cannot reproduce
        ((), ("r1",)),  # the document says none and a row says otherwise
    ],
)
def test_a_COMPLETE_projection_whose_rows_disagree_is_a_MISMATCH_and_uses_the_document(
    document_ids, row_ids
):
    """CONTRACT §7.4, rules 1 and 2.

    The comparison is by run id and it is a MULTISET comparison. The duplicate row
    is the case a set comparison would call equal and then de-duplicate — writing
    the row version over a document nobody should have written, which is a silent
    edit rather than a refusal.
    """
    state, runs = repo.resolve_run_authority(
        _doc(run_ids=document_ids), (3, "gen-a"), _rows(*row_ids), tables_present=True
    )
    assert state == repo.RUN_AUTHORITY_MISMATCH
    assert runs is None, "a mismatch must never substitute the rows"


@pytest.mark.parametrize(
    "runs_value",
    ["not a list", 7, {"r1": {}}, [None], [{"label": "no id"}], [{"id": 7}], [{"id": ""}]],
)
def test_a_document_whose_runs_cannot_be_COMPARED_is_a_MISMATCH_not_an_empty_list(
    runs_value,
):
    """§11's read-path rule, applied here: a malformed value already PERSISTED is
    READ rather than refused — and reading it means leaving it exactly as it is.

    Treating an uncomparable `runs` as `[]` would let a COMPLETE projection with no
    rows agree with it and then REPLACE it with `[]`, which is the silent deletion
    this whole contract exists to make unwritable.
    """
    document = {"rev": 3, "generation": "gen-a", "runs": runs_value}
    assert repo.resolve_run_authority(
        document, (3, "gen-a"), [], tables_present=True
    ) == (repo.RUN_AUTHORITY_MISMATCH, None)


def test_a_document_with_no_runs_KEY_AT_ALL_is_read_as_zero_runs():
    """DISTINCT FROM THE CASE ABOVE, and the distinction is the point. An ABSENT
    key is not a malformed one: `Experiment.to_state` always emits `runs`, and a
    document that omits it is a legacy or hand-written one that genuinely names no
    run. It compares equal to zero rows."""
    document = {"rev": 3, "generation": "gen-a"}
    assert repo.resolve_run_authority(
        document, (3, "gen-a"), [], tables_present=True
    ) == (repo.RUN_AUTHORITY_COMPLETE, [])


def test_an_unreadable_row_document_is_a_MISMATCH_rather_than_a_dropped_run():
    """A row whose `state` is not a document cannot reproduce a run. Skipping it
    would restore the record with one run fewer and report success."""
    assert repo.resolve_run_authority(
        _doc(run_ids=("r1", "r2")),
        (3, "gen-a"),
        [("r1", {"id": "r1"}), ("r2", None)],
        tables_present=True,
    ) == (repo.RUN_AUTHORITY_MISMATCH, None)


def test_a_row_whose_document_does_not_carry_its_own_run_id_is_a_MISMATCH():
    """`0002_runs`' `isaac_runs_document_identity` CHECK forbids this pairing, so a
    row of this shape means the CHECK was bypassed. Substituting its document for a
    run filed under a different id is the one substitution that could RENAME a
    scientist's run."""
    assert repo.resolve_run_authority(
        _doc(run_ids=("r1",)),
        (3, "gen-a"),
        [("r1", {"id": "someone else"})],
        tables_present=True,
    ) == (repo.RUN_AUTHORITY_MISMATCH, None)


# =============================================================================
# 2. BEFORE COMPLETENESS — row absence cannot erase runs
# =============================================================================


def test_a_NEVER_PROJECTED_experiment_with_three_runs_hydrates_with_three_runs(
    workspace,
):
    """CONTRACT §7.5, phase 1, verbatim: *a NEVER-PROJECTED experiment with three
    runs in its document hydrates with three runs while `isaac_runs` holds none.*

    THIS IS THE CASE THE WHOLE CONTRACT EXISTS FOR. A reader that read zero rows as
    "no runs" would restore this record with an empty run list and report
    `restored: 1`. It is the normal state of every experiment persisted before the
    projection existed, and of every experiment saved between a merge and the
    operator applying the migration.
    """
    exp = _experiment("Run 1", "Run 2", "Run 3")
    conn = FakeConnection()
    _publish(conn, exp)  # the experiment row exists; NO projection, NO run rows
    assert conn.projections == {} and conn.runs == {}

    document = _restore(conn, exp, workspace)

    assert [run["id"] for run in document["runs"]] == [r.id for r in exp.sorted_runs()]
    assert document["runs"] == exp.to_state()["runs"]
    _only(repo.RUN_AUTHORITY_NEVER_PROJECTED)


def test_an_UNAVAILABLE_deployment_reads_the_document_and_names_no_run_table(
    workspace,
):
    """`0005` IS NOT APPLIED ANYWHERE, so this is the state of EVERY environment
    today and the distribution an operator would check against §7.6's first row.

    The assertion is on the STATEMENTS as well as on the outcome: with the tables
    absent, the reader must not issue a statement naming either of them. A reader
    that asked and swallowed the error would look identical from the outside and
    would abort the transaction on a real engine.
    """
    exp = _experiment("Run 1", "Run 2")
    conn = FakeConnection(run_table=False, projection_table=False)
    _publish(conn, exp)

    document = _restore(conn, exp, workspace)

    assert document["runs"] == exp.to_state()["runs"]
    _only(repo.RUN_AUTHORITY_UNAVAILABLE)
    named = [
        sql
        for sql, _ in conn.statements
        if "isaac_runs" in sql.lower() or "isaac_run_projection" in sql.lower()
    ]
    assert named == [], named


def test_0005_ROLLED_BACK_UNDER_A_LIVE_POD_IS_UNAVAILABLE_AND_NOT_A_FAILED_LIST(
    workspace,
):
    """THE OPERATOR ACTION `forget_run_table_presence` EXISTS FOR, on the read path.

    This process has already seen both tables (it persists first, which caches the
    positive probe). The operator then rolls `0005` back, so the projection SELECT
    answers `undefined_table` on a transaction that is now poisoned. Before Stage
    2b that environment served My Experiments perfectly; a reader that let this
    propagate would turn a working list into a disclosed-incomplete one for a table
    whose own contract says its absence is normal operation.

    The pass degrades to UNAVAILABLE — the document — and forgets the cache so the
    next pass re-probes rather than needing a restart.
    """
    exp = _experiment("Run 1", "Run 2")
    conn = FakeConnection()
    _store(conn).persist(exp)
    _publish(conn, exp)
    assert repo.projection_table_seen(), "the premise is a CACHED positive probe"

    conn.projection_table = False  # the operator's rollback, mid-flight
    document = _restore(conn, exp, workspace)

    assert document["runs"] == exp.to_state()["runs"], "not one run was lost"
    _only(repo.RUN_AUTHORITY_UNAVAILABLE)
    assert not repo.projection_table_seen(), "a contradicted positive cache survived"


def test_a_read_failure_that_is_NOT_undefined_table_is_still_an_outage(workspace):
    """THE OTHER HALF OF THE ARM ABOVE, and the reason it is narrowed to one
    SQLSTATE. Swallowing every exception would make "the table is absent" and "the
    read is broken" indistinguishable, which is the exact ambiguity `0005` exists
    to remove one level up."""
    exp = _experiment("Run 1")
    conn = FakeConnection(
        raise_on={repo.Q_RUN_PROJECTIONS_FOR_EXPERIMENTS: RuntimeError("boom")}
    )
    _publish(conn, exp)
    _wipe(workspace, exp)

    with pytest.raises(repo.StorageUnavailable):
        _store(conn).hydrate()


# =============================================================================
# 3. AFTER COMPLETENESS — the reads come from the rows
# =============================================================================


@pytest.mark.parametrize(
    "labels",
    [
        pytest.param((), id="genuinely-empty"),
        pytest.param(("Run 1",), id="one-run"),
        pytest.param(("Run 1", "Run 2", "Run 3"), id="many-runs"),
        pytest.param(tuple(f"Run {n}" for n in range(1, 41)), id="large-run-set"),
    ],
)
def test_a_COMPLETE_projection_restores_the_runs_FROM_THE_ROWS(workspace, labels):
    """PHASE 3, at four widths including both edges.

    The proof that the rows are the SOURCE and not merely consistent with the
    document is the next case: here the document and the rows agree, so equality
    alone would pass either way. This case pins that the parity holds at every
    width — including zero, which is the width `0002` alone could not express, and
    forty, which is the width a naive per-experiment read would have made
    quadratic.
    """
    exp = _experiment(*labels)
    conn = FakeConnection()
    document = _persist_publish_restore(conn, exp, workspace)

    assert document["runs"] == exp.to_state()["runs"]
    assert [run["id"] for run in document["runs"]] == [r.id for r in exp.sorted_runs()]
    _only(repo.RUN_AUTHORITY_COMPLETE)


def test_THE_ROWS_REALLY_ARE_THE_SOURCE_and_not_merely_equal_to_the_document(
    workspace,
):
    """THE CASE THAT MAKES EVERY OTHER "PARITY" ASSERTION IN THIS FILE MEAN
    SOMETHING — REBUILT 2026-08-27 ON A DEVICE THAT SURVIVES THE CONTENT RULE.

    Every parity case in this file compares a restored document against an
    experiment whose rows and document AGREE, so a reader that ignored the rows
    entirely would pass all of them. Something has to break that tie.

    ~~The previous version broke it by mutating a row's `label` out of band and
    asserting the ROW's label was restored.~~ That device is gone, because the
    reader now compares the full run DOCUMENTS and calls exactly that divergence a
    MISMATCH — see
    `test_a_ROW_MUTATED_OUT_OF_BAND_is_a_MISMATCH_and_the_DOCUMENT_WINS`, which is
    the same fixture asserting the corrected behaviour. Under a content rule, ANY
    observable difference in the restored VALUES is a mismatch by construction, so
    the tie can only be broken by something that is not a value.

    IT IS BROKEN BY KEY ORDER, WHICH IS PROVENANCE WITHOUT BEING CONTENT. Both
    sides carry `Run.to_state()`, but they carry it in different orders:
    `_run_row_params` writes the row with `json.dumps(..., sort_keys=True)`, so a
    row's document is ALPHABETICAL, while `Experiment.to_state()` embeds
    `Run.to_state()` in its own insertion order, which is not. `dict.__eq__` is
    order-insensitive, so the reader still says COMPLETE; `json.dumps` of the
    restored state is order-PRESERVING, so the file on disk says which side it came
    from. That is an end-to-end proof, through `hydrate`, that the bytes were built
    from the rows.

    THE LIMIT IS STATED RATHER THAN LEFT TO INFERENCE. This device works because
    the fake preserves the key order `_run_row_params` produced; a real `jsonb`
    column normalises key order and would erase it. So this is a HARNESS-LEVEL
    provenance probe, not a claim about PostgreSQL — which is why
    `test_the_resolved_runs_ARE_THE_ROW_DOCUMENTS_by_identity` states the same
    property at the level where it is engine-independent.
    """
    exp = _experiment("Run 1", "Run 2")
    conn = FakeConnection()
    document = _persist_publish_restore(conn, exp, workspace)

    document_order = list(exp.to_state()["runs"][0])
    row_order = sorted(document_order)
    assert document_order != row_order, (
        "the premise is that `to_state()` order and `sort_keys=True` order DIFFER"
    )

    assert [list(run) for run in document["runs"]] == [row_order, row_order], (
        "the restored runs carry the DOCUMENT's key order, so they came from the "
        "document and not from the rows"
    )
    assert document["runs"] == exp.to_state()["runs"], "and they are still equal"
    _only(repo.RUN_AUTHORITY_COMPLETE)


def test_the_resolved_runs_ARE_THE_ROW_DOCUMENTS_by_identity():
    """THE SAME PROPERTY, STATED WHERE NO SERIALISATION CAN ERASE IT.

    `resolve_run_authority` is handed row documents and a stored document whose
    `runs` are EQUAL but not the SAME objects. On COMPLETE it must return the ROW
    objects — that is what "the rows are the authority" means once content parity
    is enforced, and `is` is the only assertion a `==`-preserving reader cannot
    fake. No database, no JSON, no key order.
    """
    row_documents = [
        {"id": "r1", "label": "one"},
        {"id": "r2", "label": "two"},
    ]
    state = {
        "rev": 3,
        "generation": "gen-a",
        # Equal by value, distinct by identity, and deliberately built in a
        # different key order so the copies cannot be the same objects.
        "runs": [{"label": "one", "id": "r1"}, {"label": "two", "id": "r2"}],
    }
    assert state["runs"] == row_documents
    assert all(a is not b for a, b in zip(state["runs"], row_documents))

    authority, resolved = repo.resolve_run_authority(
        state,
        (3, "gen-a"),
        [(doc["id"], doc) for doc in row_documents],
        tables_present=True,
    )

    assert authority == repo.RUN_AUTHORITY_COMPLETE
    assert resolved is not None
    assert [id(run) for run in resolved] == [id(run) for run in row_documents]


def test_a_ROW_MUTATED_OUT_OF_BAND_is_a_MISMATCH_and_the_DOCUMENT_WINS(workspace):
    """THE HOLE IN CONTRACT §7.4, CLOSED — AND THE SUPERSEDED CLAIM KEPT VISIBLE.

    **What this fixture used to assert, and it is kept because it was measured
    rather than assumed:**

        ~~`assert document["runs"][0]["label"] == "the label only the ROW carries"`
        … §7.4 rule 1 specifies comparison BY RUN ID, so a content divergence
        inside a matching id set is not detected and the row wins.~~

    That was the honest consequence of implementing rule 1 to the letter, and the
    implementing slice reported it as a finding rather than arguing it was right.
    It is now WRONG, because §7.4 rule 1 and rule 2 disagreed and rule 2 governs:
    *on any disagreement, use the DOCUMENT*. The document is the side the
    compare-and-swap protects and the side a scientist's last write landed in, and
    a content divergence is exactly as much "a COMPLETE projection that does not
    reproduce the document" as a missing id is — and MORE dangerous, because it
    substitutes different science rather than a different count.

    So the same out-of-band `UPDATE` of a row's document — which §7.4 says cannot
    happen by construction — is now a MISMATCH: the DOCUMENT's label is restored,
    nothing is repaired, and the disagreement is COUNTED, because a mismatch that
    only fell back would be indistinguishable from a healthy fallback (rule 3).
    """
    exp = _experiment("the label the document carries")
    conn = FakeConnection()
    _store(conn).persist(exp)
    _publish(conn, exp)

    run_id = exp.sorted_runs()[0].id
    experiment_id, ordinal, state, rev, generation = conn.runs[run_id]
    state = dict(state, label="the label only the ROW carries")
    conn.runs[run_id] = (experiment_id, ordinal, state, rev, generation)

    document = _restore(conn, exp, workspace)

    assert document["runs"][0]["label"] == "the label the document carries"
    assert document["runs"] == exp.to_state()["runs"], "nothing was lost"
    _only(repo.RUN_AUTHORITY_MISMATCH)
    # NEVER REPAIRED SILENTLY (§7.4 rule 4): the row still carries the divergence.
    assert conn.runs[run_id][2]["label"] == "the label only the ROW carries"


@pytest.mark.parametrize(
    "field,value",
    [
        pytest.param("label", "renamed out of band", id="a-scientist-visible-value"),
        pytest.param("record_id", "01ZZZZZZZZZZZZZZZZZZZZZZZZ", id="a-link"),
        pytest.param("draft", {"planted": True}, id="the-whole-draft"),
        pytest.param("overrides", {"block:tags": {"payload": []}}, id="an-override"),
        pytest.param("experiment_id", "01OTHEREXPERIMENT000000000", id="its-owner"),
    ],
)
def test_ANY_field_of_a_row_document_diverging_is_a_MISMATCH(workspace, field, value):
    """THE CONTENT RULE IS OVER THE WHOLE DOCUMENT, NOT OVER A CHOSEN SUBSET.

    A rule that compared only the fields somebody thought to name would be a
    shorter version of the id comparison it replaces. Each of these is a field a
    broken writer, a migration or a hand-run `UPDATE` could move, and every one of
    them must keep the document.
    """
    exp = _experiment("Run 1")
    conn = FakeConnection()
    _store(conn).persist(exp)
    _publish(conn, exp)

    run_id = exp.sorted_runs()[0].id
    experiment_id, ordinal, state, rev, generation = conn.runs[run_id]
    assert state[field] != value, "the premise is that this is a CHANGE"
    conn.runs[run_id] = (
        experiment_id,
        ordinal,
        dict(state, **{field: value}),
        rev,
        generation,
    )

    document = _restore(conn, exp, workspace)

    assert document["runs"] == exp.to_state()["runs"]
    _only(repo.RUN_AUTHORITY_MISMATCH)


def test_a_row_MISSING_A_KEY_the_document_carries_is_a_MISMATCH(workspace):
    """DIVERGENCE BY ABSENCE, WHICH AN EQUALITY OVER SHARED KEYS WOULD MISS.

    A reader that compared only the keys both sides carry would call this equal and
    then restore a run with no `label` at all.
    """
    exp = _experiment("Run 1")
    conn = FakeConnection()
    _store(conn).persist(exp)
    _publish(conn, exp)

    run_id = exp.sorted_runs()[0].id
    experiment_id, ordinal, state, rev, generation = conn.runs[run_id]
    trimmed = {key: val for key, val in state.items() if key != "label"}
    conn.runs[run_id] = (experiment_id, ordinal, trimmed, rev, generation)

    document = _restore(conn, exp, workspace)

    assert document["runs"][0]["label"] == "Run 1"
    _only(repo.RUN_AUTHORITY_MISMATCH)


def _legacy_run(run_id, **overrides):
    """A run document of the oldest reachable shape: `experiment_id: ""`, ordinal 0."""
    return ws.Run.from_state(
        {"id": run_id, "experiment_id": "", "label": run_id[:4], **overrides}
    )


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda: _experiment(), id="zero-runs"),
        pytest.param(lambda: _experiment("Run 1"), id="one-run"),
        pytest.param(
            lambda: _experiment(*(f"Run {n}" for n in range(1, 41))), id="forty-runs"
        ),
        pytest.param(
            lambda: _with_runs(
                _experiment(),
                _legacy_run("01AAAAAAAAAAAAAAAAAAAAAAAA"),
                _legacy_run("01BBBBBBBBBBBBBBBBBBBBBBBB"),
            ),
            id="legacy-empty-experiment-id-and-TIED-ordinals",
        ),
        pytest.param(
            lambda: _with_runs(
                _experiment("An ordinary run"),
                _legacy_run("01CCCCCCCCCCCCCCCCCCCCCCCC"),
            ),
            id="mixed-legacy-and-modern",
        ),
        pytest.param(
            lambda: _with_runs(
                _experiment(),
                _legacy_run(
                    "01DDDDDDDDDDDDDDDDDDDDDDDD",
                    draft={
                        "nested": {"deep": [1, 2, {"z": None, "a": True}]},
                        "unicode": "µ K-edge — Ångström",
                        "empty_map": {},
                        "empty_list": [],
                        "float": 2.5,
                        "int": 7,
                        "zero": 0,
                        "false": False,
                    },
                ),
            ),
            id="awkward-json-values",
        ),
    ],
)
def test_a_REAL_save_then_hydrate_resolves_COMPLETE_at_every_shape(workspace, build):
    """THE FAILURE MODE THAT WOULD BE WORSE THAN THE HOLE THE CONTENT RULE CLOSES.

    A content comparison that reported MISMATCH for an artefact of SERIALISATION
    would make the reader fall back on every experiment forever — Stage 2b
    disabled, silently, while the suite that only tested divergence stayed green.
    So the safe direction is proved directly: take a real experiment through
    `persist` -> `hydrate` at every shape this repository can reach, and require
    COMPLETE.

    The shapes are chosen for the four things `_rows_reproduce_the_document`
    documents as deliberately NOT normalised: key order (`sort_keys=True` on the
    row, insertion order in the document), `jsonb`-as-text, numeric types, and the
    legacy `experiment_id: ""` that `workspace._hydrate_runs` never repairs. Tied
    ordinals are here too, because they are the case where the row ORDER and the
    document order are free to diverge.
    """
    exp = build()
    conn = FakeConnection()
    document = _persist_publish_restore(conn, exp, workspace)

    _only(repo.RUN_AUTHORITY_COMPLETE)
    assert document["runs"] == exp.to_state()["runs"]


def test_a_row_returned_as_TEXT_rather_than_a_dict_still_resolves_COMPLETE():
    """`jsonb` COMES BACK AS TEXT WHEN THE ADAPTER IS NOT REGISTERED, and that must
    not read as a divergence.

    `_grouped_run_rows` parses it, so by the time the content rule sees it the two
    sides are both documents. Asserted at the predicate, because the fake always
    hands back a `dict` and could not show this.
    """
    payload = {"id": "r1", "label": "one", "draft": {"b": 2, "a": 1}, "ordinal": 0}
    rows = repo._grouped_run_rows(
        [("exp", "r1", json.dumps(payload, sort_keys=True))]
    )
    authority, resolved = repo.resolve_run_authority(
        {"rev": 1, "generation": "gen-a", "runs": [payload]},
        (1, "gen-a"),
        rows["exp"],
        tables_present=True,
    )
    assert authority == repo.RUN_AUTHORITY_COMPLETE
    assert resolved == [payload]


def test_an_INT_and_a_FLOAT_of_the_same_value_are_not_a_divergence():
    """A `jsonb` round trip may legitimately return `2` where the document holds
    `2.0`. `==` on parsed values calls those equal; a canonical-JSON comparison
    would not, which is why one is used and the other is not."""
    authority, _ = repo.resolve_run_authority(
        {"rev": 1, "generation": "g", "runs": [{"id": "r1", "ordinal": 2.0}]},
        (1, "g"),
        [("r1", {"id": "r1", "ordinal": 2})],
        tables_present=True,
    )
    assert authority == repo.RUN_AUTHORITY_COMPLETE


def test_the_restored_run_order_is_sorted_runs_order_and_not_the_INDEX_order(
    workspace,
):
    """THE ORDERING TRAP, MEASURED RATHER THAN ASSERTED.

    `sorted_runs` orders by `(ordinal, created_utc, id)` where `created_utc` is the
    DOCUMENT field. `isaac_runs_experiment_order_idx` is `(experiment_id, ordinal,
    run_id)` and the column of that name on the table is the SERVER-SIDE ROW STAMP.
    The two coincide unless runs share an ordinal, so the fixture makes three runs
    share ordinal 0 and gives them document `created_utc` values in the OPPOSITE
    order to their ids — a sequence the index alone cannot reproduce.
    """
    exp = _experiment(rid="01ABCDEFGHJKMNPQRSTVWXYZ01")
    for run_id, created in (
        ("01AAAAAAAAAAAAAAAAAAAAAAAA", "2026-03-03T00:00:00Z"),
        ("01BBBBBBBBBBBBBBBBBBBBBBBB", "2026-02-02T00:00:00Z"),
        ("01CCCCCCCCCCCCCCCCCCCCCCCC", "2026-01-01T00:00:00Z"),
    ):
        exp.runs.append(
            ws.Run.from_state(
                {
                    "id": run_id,
                    "experiment_id": exp.id,
                    "ordinal": 0,
                    "created_utc": created,
                    "label": run_id[:4],
                }
            )
        )
    expected = [run.id for run in exp.sorted_runs()]
    assert expected != sorted(run.id for run in exp.runs), (
        "the premise is that document order and id order DIFFER"
    )

    conn = FakeConnection()
    document = _persist_publish_restore(conn, exp, workspace)

    assert [run["id"] for run in document["runs"]] == expected
    _only(repo.RUN_AUTHORITY_COMPLETE)


def test_authority_is_RECOMPUTED_on_every_pass_and_never_remembered(workspace):
    """CONTRACT §7.2 row 15: a restart preserves authority because there is nothing
    to preserve — it is derived from the stamp on each pass.

    Asserted by hydrating TWICE with the projection made stale in between. A cached
    "this experiment is COMPLETE" bit would keep reading the rows; there is none, so
    the second pass reads the document.
    """
    exp = _experiment("Run 1", "Run 2")
    conn = FakeConnection()
    assert _persist_publish_restore(conn, exp, workspace)["runs"] == exp.to_state()["runs"]
    _only(repo.RUN_AUTHORITY_COMPLETE)

    rev, generation, count, projector = conn.projections[exp.id]
    conn.projections[exp.id] = (rev - 1, generation, count, projector)

    document = _restore(conn, exp, workspace)
    assert document["runs"] == exp.to_state()["runs"]
    _only(repo.RUN_AUTHORITY_STALE)


def test_the_reader_issues_exactly_two_statements_for_any_number_of_experiments(
    workspace,
):
    """THE COST BOUND, STATED AS A SHAPE. `hydrate` runs on EVERY ordinary
    `GET /api/experiments`, so a per-experiment read would be 2N round trips on the
    product's primary screen. `= ANY(%s::text[])` keeps it at two for any N."""
    experiments = [
        _experiment("Run 1", "Run 2", rid=f"01ABCDEFGHJKMNPQRSTVWXYZ0{n}")
        for n in range(5)
    ]
    conn = FakeConnection()
    store = _store(conn)
    for exp in experiments:
        store.persist(exp)
    conn.rows = [(exp.id, json.dumps(exp.to_state())) for exp in experiments]
    for exp in experiments:
        _wipe(workspace, exp)
    conn.statements.clear()

    assert store.hydrate() == 5
    issued = [sql for sql, _ in conn.statements]
    assert issued.count(repo.Q_RUN_PROJECTIONS_FOR_EXPERIMENTS) == 1
    assert issued.count(repo.Q_RUN_ROWS_FOR_EXPERIMENTS) == 1
    summary = _authority()
    assert summary[repo.RUN_AUTHORITY_COMPLETE] == 5, summary


def test_a_WARM_pod_issues_NEITHER_read_because_there_is_nothing_to_restore(
    workspace,
):
    """THE REASON THIS IS AFFORDABLE ON A PER-REQUEST PATH, and it is the sizing
    §7.4's own price tag had to be corrected for. `hydrate` RESTORES rather than
    refreshes, so on a pod whose workspace already holds every record the candidate
    list is empty and neither statement is issued at all."""
    exp = _experiment("Run 1")
    conn = FakeConnection()
    _persist_publish_restore(conn, exp, workspace)
    assert (workspace / exp.id / "experiment.json").exists()

    repo.forget_run_authority()
    conn.statements.clear()
    assert _store(conn).hydrate() == 0

    issued = [sql for sql, _ in conn.statements]
    assert repo.Q_RUN_PROJECTIONS_FOR_EXPERIMENTS not in issued
    assert repo.Q_RUN_ROWS_FOR_EXPERIMENTS not in issued
    assert _authority() is None, (
        "a pass that classified nothing must not publish an all-zero distribution — "
        "it would erase the post-restart measurement, which is the informative one"
    )


# =============================================================================
# 4. DURING THE TRANSITION — mismatches are visible, and nothing is lost
# =============================================================================


def test_a_row_deleted_OUT_OF_BAND_hydrates_from_the_document_and_is_COUNTED(
    workspace,
):
    """CONTRACT §7.5, phase 2, verbatim: *a COMPLETE projection with a row deleted
    out of band hydrates from the document, is counted as a mismatch, and loses
    nothing.*

    THE COUNT IS HALF THE POINT. A mismatch that only fell back would be
    indistinguishable from a healthy fallback, and the stamp exists precisely so
    the two are distinguishable (§7.4 rule 3).
    """
    exp = _experiment("Run 1", "Run 2", "Run 3")
    conn = FakeConnection()
    _store(conn).persist(exp)
    _publish(conn, exp)
    del conn.runs[exp.sorted_runs()[1].id]  # not a statement this application owns

    document = _restore(conn, exp, workspace)

    assert document["runs"] == exp.to_state()["runs"], "a run was lost"
    assert len(document["runs"]) == 3
    _only(repo.RUN_AUTHORITY_MISMATCH)


def test_a_mismatch_is_NEVER_REPAIRED_SILENTLY(workspace):
    """CONTRACT §7.4 rule 4. The reader does not rewrite rows to match and does not
    re-stamp. Repair is an ordinary save's job, or an operator's — and a reader that
    repaired would be a second, unowned writer into a table whose whole safety
    argument is that it has exactly one."""
    exp = _experiment("Run 1", "Run 2")
    conn = FakeConnection()
    _store(conn).persist(exp)
    _publish(conn, exp)
    del conn.runs[exp.sorted_runs()[0].id]

    before_runs = dict(conn.runs)
    before_projection = dict(conn.projections)
    conn.statements.clear()
    _restore(conn, exp, workspace)

    assert conn.runs == before_runs, "the reader wrote to isaac_runs"
    assert conn.projections == before_projection, "the reader re-stamped a claim"
    for sql, _ in conn.statements:
        assert sql.lower().startswith(("select", "set")), sql


def test_a_CONCURRENT_SAVE_DURING_THE_CUTOVER_reads_the_document_and_loses_nothing(
    workspace,
):
    """§7.2 row 16, from the READER's side.

    The reader holds the document at rev N; another writer wins the compare-and-swap
    and stamps a COMPLETE projection at rev N+1 with its own rows. The pair stops
    matching, so the reader is STALE and writes the document it actually holds. It
    does NOT graft a newer writer's runs onto an older document, which is the one
    outcome that would fabricate a record that never existed.
    """
    exp = _experiment("Run 1", "Run 2")
    conn = FakeConnection()
    _store(conn).persist(exp)
    _publish(conn, exp)  # the reader will see THIS document

    winner = ws.Experiment.from_state(exp.to_state())
    winner.add_run(label="the concurrent writer's run")
    winner.rev = exp.rev + 1
    _store(conn).persist(winner)  # rows and stamp both move to rev+1

    document = _restore(conn, exp, workspace)

    assert document["runs"] == exp.to_state()["runs"]
    assert len(document["runs"]) == 2
    _only(repo.RUN_AUTHORITY_STALE)


def test_a_PARTIAL_projection_leaves_each_experiment_INDEPENDENTLY_classified(
    workspace,
):
    """§7.2 row 6: partial backfill means nothing special. There is no global state
    to be half-way through, so one pass can and must report several states at once
    — which is also the shape an operator sees while a backfill is running."""
    complete = _experiment("Run 1", rid="01ABCDEFGHJKMNPQRSTVWXYZ01")
    never = _experiment("Run 1", "Run 2", rid="01ABCDEFGHJKMNPQRSTVWXYZ02")
    stale = _experiment("Run 1", "Run 2", "Run 3", rid="01ABCDEFGHJKMNPQRSTVWXYZ03")

    conn = FakeConnection()
    store = _store(conn)
    store.persist(complete)
    store.persist(stale)
    rev, generation, count, projector = conn.projections[stale.id]
    conn.projections[stale.id] = (rev + 5, generation, count, projector)
    conn.rows = [
        (exp.id, json.dumps(exp.to_state())) for exp in (complete, never, stale)
    ]
    for exp in (complete, never, stale):
        _wipe(workspace, exp)

    assert store.hydrate() == 3
    for exp in (complete, never, stale):
        assert _restored(workspace, exp)["runs"] == exp.to_state()["runs"]
    assert _authority() == {
        repo.RUN_AUTHORITY_COMPLETE: 1,
        repo.RUN_AUTHORITY_STALE: 1,
        repo.RUN_AUTHORITY_NEVER_PROJECTED: 1,
        repo.RUN_AUTHORITY_UNAVAILABLE: 0,
        repo.RUN_AUTHORITY_MISMATCH: 0,
    }


def test_a_FAILED_BACKFILL_leaves_the_unprojected_experiments_reading_the_document(
    workspace,
):
    """A BACKFILL THAT STOPPED PART-WAY is the same shape as a partial projection,
    and it is stated separately because the contract's §3 gate is about exactly
    this: a pass whose `UNREADABLE`/`refused`/`failed` counts are not all zero left
    some experiment unprojected. The reader is unbothered — those experiments are
    NEVER PROJECTED and read the document — which is why §7.3 can say the reader
    ships before the backfill runs."""
    projected = _experiment("Run 1", rid="01ABCDEFGHJKMNPQRSTVWXYZ01")
    missed = _experiment("Run 1", "Run 2", rid="01ABCDEFGHJKMNPQRSTVWXYZ02")
    conn = FakeConnection()
    _store(conn).persist(projected)  # the backfill got this far and then failed
    conn.rows = [(exp.id, json.dumps(exp.to_state())) for exp in (projected, missed)]
    for exp in (projected, missed):
        _wipe(workspace, exp)

    assert _store(conn).hydrate() == 2
    assert _restored(workspace, missed)["runs"] == missed.to_state()["runs"]
    summary = _authority()
    assert summary[repo.RUN_AUTHORITY_NEVER_PROJECTED] == 1, summary
    assert summary[repo.RUN_AUTHORITY_COMPLETE] == 1, summary


def test_an_IDEMPOTENT_RETRY_of_the_projection_changes_nothing_the_reader_sees(
    workspace,
):
    """The backfill is idempotent — a re-run re-projects and re-stamps to the same
    values — so a second pass must leave the reader's verdict and its output
    identical. Asserted as byte equality of the restored document, because "the same
    values" is what idempotence claims and anything weaker would not test it."""
    exp = _experiment("Run 1", "Run 2")
    conn = FakeConnection()
    first = _persist_publish_restore(conn, exp, workspace)

    _store(conn).persist(exp)  # the retry, through the same code path
    second = _restore(conn, exp, workspace)

    assert second == first
    _only(repo.RUN_AUTHORITY_COMPLETE)


# =============================================================================
# 5. THE KILL SWITCH
# =============================================================================


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off", " Off "])
def test_the_kill_switch_forces_document_behaviour_and_issues_NEITHER_read(
    workspace, monkeypatch, value
):
    """CONTRACT §7.3. `ISAAC_RUN_ROWS_AUTHORITATIVE=0` forces every experiment to
    document-reading behaviour WITHOUT A REDEPLOY.

    THE STATEMENTS ARE ASSERTED, NOT JUST THE OUTCOME. "Off" means the reader does
    not ASK — it does not ask and then discard the answer — which is what makes the
    switch provable by inspection rather than by trusting a branch. The environment
    is read per call, so the same process behaves differently before and after.
    """
    exp = _experiment("Run 1", "Run 2")
    conn = FakeConnection()
    _store(conn).persist(exp)
    _publish(conn, exp)
    # Corrupt the rows so that USING them would be visible.
    conn.runs.clear()

    env = _env()
    env[repo.RUN_ROWS_AUTHORITATIVE_ENV] = value
    conn.statements.clear()
    document = _restore(conn, exp, workspace, env=env)

    assert document["runs"] == exp.to_state()["runs"], "the document was not used"
    issued = [sql for sql, _ in conn.statements]
    assert repo.Q_RUN_PROJECTIONS_FOR_EXPERIMENTS not in issued
    assert repo.Q_RUN_ROWS_FOR_EXPERIMENTS not in issued
    assert _authority() is None, (
        "a disabled reader classified nothing, and must not publish a state it "
        "did not measure"
    )


def test_the_switch_defaults_ON_and_an_unrecognised_value_does_not_disable_it():
    """A design that needed a flag to be SAFE would not be safe (§7.3), so the
    default is on. And a typo must not silently disable a shipped behaviour: only
    the enumerated values turn it off."""
    assert repo.run_rows_authoritative({}) is True
    assert repo.run_rows_authoritative({repo.RUN_ROWS_AUTHORITATIVE_ENV: ""}) is True
    assert repo.run_rows_authoritative({repo.RUN_ROWS_AUTHORITATIVE_ENV: "1"}) is True
    assert repo.run_rows_authoritative({repo.RUN_ROWS_AUTHORITATIVE_ENV: "tru"}) is True
    assert repo.run_rows_authoritative({repo.RUN_ROWS_AUTHORITATIVE_ENV: "0"}) is False


def test_the_switch_takes_effect_WITHOUT_A_REDEPLOY(workspace, monkeypatch):
    """The whole value of a kill switch is that an operator can use it on a pod
    that is already running. Read at import time it would be useless, so this
    asserts the same live store answers differently either side of one edit."""
    exp = _experiment("Run 1")
    conn = FakeConnection()
    _store(conn).persist(exp)
    _publish(conn, exp)
    store = repo.PostgresOrdinaryStore(None, connect=_connector(conn))

    monkeypatch.setenv("PGHOST", "db.invalid")
    monkeypatch.setenv("PGDATABASE", dbw.EXPECTED_DATABASE)
    monkeypatch.delenv(repo.RUN_ROWS_AUTHORITATIVE_ENV, raising=False)
    _wipe(workspace, exp)
    store.hydrate()
    _only(repo.RUN_AUTHORITY_COMPLETE)

    repo.forget_run_authority()
    monkeypatch.setenv(repo.RUN_ROWS_AUTHORITATIVE_ENV, "0")
    _wipe(workspace, exp)
    store.hydrate()
    assert _authority() is None, "the same live store still read the rows"


# =============================================================================
# 6. WHAT IS OBSERVABLE — §7.6
# =============================================================================


def test_the_health_block_carries_counts_and_nothing_else(workspace, monkeypatch):
    """§7.6: counts only. No ids, no titles, no record content.

    Asserted by SERIALISING the block and searching for the record id and title
    that the pass just classified — a shape assertion would pass over a field that
    carried them.
    """
    exp = _experiment("Run 1", "Run 2", title="A title that must not be published")
    conn = FakeConnection()
    _persist_publish_restore(conn, exp, workspace)

    monkeypatch.setenv("PGHOST", "db.invalid")
    monkeypatch.setenv("PGDATABASE", dbw.EXPECTED_DATABASE)
    block = repo.storage_status()["run_projection"]

    assert block == {
        "authoritative": True,
        "last_pass": {
            repo.RUN_AUTHORITY_COMPLETE: 1,
            repo.RUN_AUTHORITY_STALE: 0,
            repo.RUN_AUTHORITY_NEVER_PROJECTED: 0,
            repo.RUN_AUTHORITY_UNAVAILABLE: 0,
            repo.RUN_AUTHORITY_MISMATCH: 0,
        },
    }
    serialised = json.dumps(block)
    assert exp.id not in serialised
    assert "A title that must not be published" not in serialised
    for run in exp.runs:
        assert run.id not in serialised
    assert all(isinstance(value, int) for value in block["last_pass"].values())


def test_the_health_block_reports_NO_PASS_distinguishably_from_a_pass_that_found_none():
    """`None` is not `{}` and not all-zeros. "No pass has classified anything in
    this process" is a different claim from "a pass ran and every experiment was
    UNAVAILABLE", and an operator checking §7.6's prediction needs to tell them
    apart."""
    assert repo.run_authority_summary() is None
    assert repo.storage_status({})["run_projection"]["last_pass"] is None


def test_the_UNAVAILABLE_prediction_an_operator_would_check_today(workspace):
    """§7.6's FIRST row, which is the one that describes every environment right
    now: `0005` is not applied, so the honest distribution is every experiment
    `unavailable`. That is the reader working correctly, not the reader being off —
    and it must never be reported as, or mistaken for, `never_projected`."""
    experiments = [
        _experiment("Run 1", rid=f"01ABCDEFGHJKMNPQRSTVWXYZ0{n}") for n in range(3)
    ]
    conn = FakeConnection(run_table=False, projection_table=False)
    conn.rows = [(exp.id, json.dumps(exp.to_state())) for exp in experiments]

    assert _store(conn).hydrate() == 3
    assert _authority() == {
        repo.RUN_AUTHORITY_COMPLETE: 0,
        repo.RUN_AUTHORITY_STALE: 0,
        repo.RUN_AUTHORITY_NEVER_PROJECTED: 0,
        repo.RUN_AUTHORITY_UNAVAILABLE: 3,
        repo.RUN_AUTHORITY_MISMATCH: 0,
    }


def test_the_NEVER_PROJECTED_prediction_after_0005_and_before_the_backfill(workspace):
    """§7.6's SECOND row. The tables exist and no pass has stamped these
    experiments, so every one is `never_projected`. The two predictions are
    separately reported, which is the whole reason §7.3's stated reason had to be
    corrected: an operator checking the health block against the wrong one would
    find it disagreeing."""
    experiments = [
        _experiment("Run 1", rid=f"01ABCDEFGHJKMNPQRSTVWXYZ0{n}") for n in range(3)
    ]
    conn = FakeConnection()
    conn.rows = [(exp.id, json.dumps(exp.to_state())) for exp in experiments]

    assert _store(conn).hydrate() == 3
    summary = _authority()
    assert summary[repo.RUN_AUTHORITY_NEVER_PROJECTED] == 3, summary
    assert summary[repo.RUN_AUTHORITY_UNAVAILABLE] == 0, summary


# =============================================================================
# 7. THE PRODUCT PATHS — every scenario the contract's list names, over HTTP
# =============================================================================
#
# The cases above drive the store directly. These drive the REAL ROUTES, because
# the property that matters to a scientist is "the record I get back after a pod
# restart is the record I left", and only the routes produce the documents a
# scientist actually creates.
#
# THE SHAPE IS THE SAME EVERY TIME: perform the mutation over HTTP, then destroy
# the workspace and hydrate, then assert the restored record is the one the API
# had just reported. The assertion is on `GET /api/experiments/{id}` BEFORE and
# AFTER, so a reader that dropped, reordered or substituted a run fails.


def _bundle(client, rid):
    response = client.get(f"/api/experiments/{rid}")
    assert response.status_code == 200, response.text
    return response.json()


def _runs(client, rid):
    """THE RUN LIST AS THE PRODUCT REPORTS IT.

    Read from `GET /api/experiments/{id}/runs` rather than from the detail bundle,
    because the detail bundle does not carry one — which is itself worth knowing
    here: the run list a scientist sees is composed from the hydrated
    `ws.Experiment`, so this is the surface a lost run would actually show up on.
    """
    response = client.get(f"/api/experiments/{rid}/runs")
    assert response.status_code == 200, response.text
    return response.json()["runs"]


def _etag(client, rid):
    return client.get(f"/api/experiments/{rid}").headers["ETag"]


def _add_run(client, rid, label):
    response = client.post(
        f"/api/experiments/{rid}/runs",
        json={"label": label},
        headers={"If-Match": _etag(client, rid)},
    )
    assert response.status_code == 201, response.text
    return response.json()["run"]["id"]


def _restart(client, conn, tmp_path, rid):
    """The pod restart: publish the current document, lose the workspace, re-read.

    `conn.rows` is set from the WORKSPACE FILE rather than from a model object,
    because that file is byte-for-byte what `persist` sent — both are
    `json.dumps(exp.to_state())` — so this is the row the database would hold.
    """
    path = tmp_path / "ws" / rid / "experiment.json"
    conn.rows = [(rid, json.dumps(json.loads(path.read_text())))]
    path.unlink()
    repo.forget_run_authority()
    return _runs(client, rid)


def _labels(runs):
    return [run["label"] for run in runs]


def _ids(runs):
    return [run["id"] for run in runs]


@pytest.fixture()
def durable(app, monkeypatch, tmp_path):
    conn = FakeConnection()
    client = _durable_client(app, monkeypatch, conn)
    return client, conn, tmp_path


def _survives_a_restart(durable, rid):
    client, conn, tmp_path = durable
    before = _runs(client, rid)
    after = _restart(client, conn, tmp_path, rid)
    assert _ids(after) == _ids(before), "a run was lost, gained or reordered"
    assert after == before, "a run's own content changed across the restart"
    return before, after


def test_CREATION_survives_a_restart(durable):
    """A record created through `POST /api/experiments` HAS NO RUNS AT ALL, which
    makes it the single most dangerous shape for this reader: its projection is
    COMPLETE with `run_count = 0`, and "zero rows" and "no claim" are the two
    things `0005` exists to keep apart. Asserted rather than assumed, because if
    the premise ever changes this case stops testing what it says it does."""
    client, _, _ = durable
    rid = client.post("/api/experiments", json={"title": "Created"}).json()["id"]
    assert _runs(client, rid) == [], "the premise moved: a created record now has runs"
    before, after = _survives_a_restart(durable, rid)
    assert after == before == []
    _only(repo.RUN_AUTHORITY_COMPLETE)


def test_ADDING_RUNS_survives_a_restart(durable):
    client, _, _ = durable
    rid = client.post("/api/experiments", json={"title": "Runs"}).json()["id"]
    for label in ("R1", "R2", "R3"):
        _add_run(client, rid, label)

    before, after = _survives_a_restart(durable, rid)
    assert _labels(after)[-3:] == ["R1", "R2", "R3"]
    _only(repo.RUN_AUTHORITY_COMPLETE)


def test_LATER_RUNS_added_after_a_restart_survive_a_second_one(durable):
    """The cutover is per experiment and continuous: a record restored FROM the
    rows and then edited must re-stamp and restore correctly again."""
    client, conn, tmp_path = durable
    rid = client.post("/api/experiments", json={"title": "Later runs"}).json()["id"]
    _add_run(client, rid, "R1")
    _restart(client, conn, tmp_path, rid)

    _add_run(client, rid, "R2 after the restart")

    before, after = _survives_a_restart(durable, rid)
    assert _labels(after)[-2:] == ["R1", "R2 after the restart"]
    _only(repo.RUN_AUTHORITY_COMPLETE)


def test_RUN_REMOVAL_survives_a_restart_and_the_removed_run_stays_removed(durable):
    """§7.2 row 14. The removal mutates the document; `persist` re-diffs the rows
    and re-stamps in the same transaction, so the projection stays COMPLETE at the
    new pair — and the restored record must NOT resurrect the removed run from a
    stale row."""
    client, conn, tmp_path = durable
    rid = client.post("/api/experiments", json={"title": "Removal"}).json()["id"]
    ids = [_add_run(client, rid, label) for label in ("R1", "R2", "R3")]
    removed = client.post(
        f"/api/experiments/{rid}/runs/{ids[1]}/remove",
        json={"confirmed_by_user": True},
        headers={"If-Match": _etag(client, rid)},
    )
    assert removed.status_code == 200, removed.text

    before, after = _survives_a_restart(durable, rid)
    assert ids[1] not in _ids(after), "a removed run came back from the rows"
    assert _labels(after)[-2:] == ["R1", "R3"]
    _only(repo.RUN_AUTHORITY_COMPLETE)


def test_RENAMING_the_record_survives_a_restart(durable):
    """An EDIT that is not a run edit. It bumps the document's `rev`, so a reader
    that compared the stamp loosely would go STALE here for no reason — and a
    reader that did not re-stamp would be reading rows for a superseded version."""
    client, conn, tmp_path = durable
    rid = client.post("/api/experiments", json={"title": "Before"}).json()["id"]
    _add_run(client, rid, "R1")
    renamed = client.patch(
        f"/api/experiments/{rid}",
        json={"title": "After"},
        headers={"If-Match": _etag(client, rid)},
    )
    assert renamed.status_code == 200, renamed.text

    _survives_a_restart(durable, rid)
    assert _bundle(client, rid)["title"] == "After"
    _only(repo.RUN_AUTHORITY_COMPLETE)


def _run_tag(client, rid, run_id):
    """A RUN's own strong validator.

    Run-level operations take the RUN's version, not the experiment's — measured,
    not guessed: sending the experiment's ETag answers `412 stale_write` with
    `expected_version` and `current_version` differing. That is also why this
    quotes it: the raw `version` field answers `400 malformed_if_match`.
    """
    run = [r for r in _runs(client, rid) if r["id"] == run_id][0]
    return '"%s"' % run["version"]


def test_ANSWERS_survive_a_restart(durable):
    """ANSWERS ARE RUN-LEVEL CONTENT — the route itself says so, refusing a
    record-level answer with `409 belongs_to_a_run` once the record has runs. They
    land inside a run's own draft, so an answer that did not reach the row would be
    silently discarded on restore and the record would come back with the question
    open again.

    Asserted on the blocking-question COUNT as well as on the run documents,
    because the count is what a scientist sees and it is derived from the draft the
    reader just restored.
    """
    client, conn, tmp_path = durable
    rid = client.post("/api/experiments", json={"title": "Answers"}).json()["id"]
    run_id = _add_run(client, rid, "R1")
    before_count = _bundle(client, rid)["pending_count"]

    answered = client.post(
        f"/api/experiments/{rid}/runs/{run_id}/answers",
        json={
            "answers": {"qc": {"status": "valid", "note": "a note a scientist wrote"}},
            "confirmed_by_user": True,
        },
        headers={"If-Match": _run_tag(client, rid, run_id)},
    )
    assert answered.status_code == 200, answered.text
    after_count = _bundle(client, rid)["pending_count"]
    assert after_count < before_count, "the premise is that the answer LANDED"

    before, after = _survives_a_restart(durable, rid)
    assert _bundle(client, rid)["pending_count"] == after_count, (
        "the restored record re-opened a question the scientist had answered"
    )
    assert [run["fields"] for run in after] == [run["fields"] for run in before]
    _only(repo.RUN_AUTHORITY_COMPLETE)


def test_an_OVERRIDE_and_its_REVERT_survive_a_restart(durable):
    """INHERITANCE AND OVERRIDES live in a run's own document (`inherited`), so an
    override that did not reach the row would come back as INHERITED — a silent
    scientific change rather than a lost one, which is the harder of the two to
    see. Both directions are exercised: set it, restart, clear it, restart again.
    """
    client, conn, tmp_path = durable
    rid = client.post("/api/experiments", json={"title": "Overrides"}).json()["id"]
    run_id = _add_run(client, rid, "R1")
    assert (
        _runs(client, rid)[0]["inherited"]["block:attribution"]["state"] == "inherited"
    ), "the premise moved"

    overridden = client.post(
        f"/api/experiments/{rid}/runs/{run_id}/overrides",
        json={
            "address": "block:attribution",
            "payload": {"contributors": [{"name": "A Scientist", "role": "operator"}]},
            "confirmed_by_user": True,
        },
        headers={"If-Match": _run_tag(client, rid, run_id)},
    )
    assert overridden.status_code in (200, 201), overridden.text
    assert (
        _runs(client, rid)[0]["inherited"]["block:attribution"]["state"] != "inherited"
    ), "the premise is that the override LANDED"

    before, after = _survives_a_restart(durable, rid)
    assert [run["inherited"] for run in after] == [run["inherited"] for run in before]
    assert (
        after[0]["inherited"]["block:attribution"]["state"] != "inherited"
    ), "the restored run silently reverted to the inherited value"
    _only(repo.RUN_AUTHORITY_COMPLETE)

    cleared = client.post(
        f"/api/experiments/{rid}/runs/{run_id}/overrides/clear",
        json={"address": "block:attribution", "confirmed_by_user": True},
        headers={"If-Match": _run_tag(client, rid, run_id)},
    )
    assert cleared.status_code in (200, 201), cleared.text
    _, reverted = _survives_a_restart(durable, rid)
    assert reverted[0]["inherited"]["block:attribution"]["state"] == "inherited"
    _only(repo.RUN_AUTHORITY_COMPLETE)


def test_a_DISCARDED_experiment_is_NEVER_PROJECTED_because_its_row_is_gone(durable):
    """§7.1's correction: `discard` is the ONE method that DELETES a projection row
    and its run rows, so after a discard the experiment is NEVER PROJECTED by §2.1's
    predicate — and that is correct, because the experiment's durable row is gone
    too. A reader must not be surprised by it and must not resurrect anything."""
    client, conn, _ = durable
    rid = client.post("/api/experiments", json={"title": "Discarded"}).json()["id"]
    _add_run(client, rid, "R1")
    assert rid in conn.projections and conn.runs

    discarded = client.post(
        f"/api/experiments/{rid}/discard",
        json={"confirmed_by_user": True},
        headers={"If-Match": _etag(client, rid)},
    )
    assert discarded.status_code in (200, 204), discarded.text
    assert conn.projections == {}, "a completeness claim outlived its experiment"
    assert conn.runs == {}, "run rows outlived their experiment"
    conn.rows = []

    repo.forget_run_authority()
    assert _store(conn).hydrate() == 0
    assert _authority() is None, "a pass with no candidate classified something"
    assert client.get(f"/api/experiments/{rid}").status_code == 404


def test_ASSETS_survive_a_restart(durable):
    """An asset reference is RECORD-level and is named by runs. It lives outside
    `runs`, which is exactly why it belongs in this list: a reader that replaced the
    whole document instead of the one key would take the assets with it, and the
    failure would look like a storage bug rather than a reader bug."""
    client, conn, tmp_path = durable
    rid = client.post("/api/experiments", json={"title": "Assets"}).json()["id"]
    _add_run(client, rid, "R1")
    created = client.post(
        f"/api/experiments/{rid}/assets",
        json={
            "confirmed_by_user": True,
            "asset_id": "reduced_spectrum",
            "content_role": "reduction_product",
            "uri": "synthetic://example/reduced/CuO2_merged.xdi",
            "sha256": "a" * 64,
        },
        headers={"If-Match": _etag(client, rid)},
    )
    assert created.status_code == 201, created.text
    listed = client.get(f"/api/experiments/{rid}/assets").json()["assets"]
    assert listed, "the premise is that the asset LANDED"

    _survives_a_restart(durable, rid)
    assert client.get(f"/api/experiments/{rid}/assets").json()["assets"] == listed
    _only(repo.RUN_AUTHORITY_COMPLETE)


def test_a_TRANSCRIPT_ACCEPTED_CHANGE_survives_a_restart(durable):
    """A finalized transcript is stored VERBATIM with the record and its proposals
    become candidates. It is stored per record and per run, so it is a second thing
    a run's document carries that a wrong reader could drop."""
    client, conn, tmp_path = durable
    rid = client.post("/api/experiments", json={"title": "Transcript"}).json()["id"]
    run_id = _add_run(client, rid, "R1")
    read = client.post(
        f"/api/experiments/{rid}/transcript",
        json={
            "text": "Scan two ran at the copper K edge and looked clean.",
            "finalized": True,
            "run_id": run_id,
        },
        headers={"If-Match": _etag(client, rid)},
    )
    assert read.status_code == 200, read.text

    before, after = _survives_a_restart(durable, rid)
    assert after == before
    _only(repo.RUN_AUTHORITY_COMPLETE)


def test_CORRECTING_a_previously_given_answer_survives_a_restart(durable):
    """A CORRECTION, which is the case `CLAUDE.md` records as having produced a
    record asserting `valid` beside provenance saying the spectrum was unusable. The
    corrected value and the provenance that goes with it both live in the run's
    document, so both must come back — and the ORIGINAL value must not."""
    client, conn, tmp_path = durable
    rid = client.post("/api/experiments", json={"title": "Correction"}).json()["id"]
    run_id = _add_run(client, rid, "R1")
    answered = client.post(
        f"/api/experiments/{rid}/runs/{run_id}/answers",
        json={
            "answers": {"qc": {"status": "valid", "note": "first pass looked fine"}},
            "confirmed_by_user": True,
        },
        headers={"If-Match": _run_tag(client, rid, run_id)},
    )
    assert answered.status_code == 200, answered.text
    # THE CORRECTION GOES THROUGH `edit`, NOT `answers`, and the API says so: the
    # answers route refuses a differing value for an already-answered key with
    # `422 already_answered` and names `answer_at` in the body. That refusal is the
    # write-path bound `CLAUDE.md` records; it is not this reader's business, and
    # following it is what makes this a real correction rather than a re-answer.
    corrected = client.post(
        f"/api/experiments/{rid}/runs/{run_id}/edit",
        json={
            "answers": {
                "qc": {
                    "status": "compromised",
                    "note": "on review the spectrum is unusable",
                }
            },
            "confirmed_by_user": True,
        },
        headers={"If-Match": _run_tag(client, rid, run_id)},
    )
    assert corrected.status_code == 200, corrected.text

    before, after = _survives_a_restart(durable, rid)
    # ASSERTED ON THE RESTORED RUNS, not on the runs listing and not on the whole
    # document. The qc verdict and its note live inside the run's DRAFT, which the
    # listing does not surface — and the superseded note DOES survive elsewhere, in
    # the record-level `answer_log`, which is an audit trail and is supposed to keep
    # it. Scoping the assertion to `runs` is what makes the second half a real claim
    # about the corrected value rather than a claim about the audit trail.
    restored = json.loads((tmp_path / "ws" / rid / "experiment.json").read_text())
    draft = restored["runs"][0]["draft"]
    assert draft["qc"]["status"] == "compromised", (
        "the restored run carries the SUPERSEDED verdict"
    )
    # THE EVIDENCE TRAIL IS APPEND-ONLY AND BOTH ANSWERS MUST SURVIVE. A reader that
    # restored the corrected status while losing the trail would produce a record
    # asserting `compromised` with nothing saying who decided that or when.
    answers = [e["answer"] for e in draft["block_evidence"]["qc:status"]]
    assert answers == ["valid", "compromised"], answers
    assert after == before
    _only(repo.RUN_AUTHORITY_COMPLETE)


def test_NOTES_AND_PROVENANCE_survive_a_restart(durable):
    """PROVENANCE is derived from the record's notes and its runs' evidence, so it
    is the surface on which a lost run or a lost note becomes a WRONG SCIENTIFIC
    CLAIM rather than a missing one — an origin disappears and the record reads as
    though nobody said it."""
    client, conn, tmp_path = durable
    rid = client.post("/api/experiments", json={"title": "Provenance"}).json()["id"]
    _add_run(client, rid, "R1")
    created = client.post(
        f"/api/experiments/{rid}/notes",
        json={"text": "spoken aside about the second scan", "source": "transcript"},
        headers={"If-Match": _etag(client, rid)},
    )
    assert created.status_code == 201, created.text
    before_provenance = client.get(f"/api/experiments/{rid}/provenance").json()

    _survives_a_restart(durable, rid)

    assert client.get(f"/api/experiments/{rid}/provenance").json() == before_provenance
    _only(repo.RUN_AUTHORITY_COMPLETE)


def test_a_LEGACY_EMBEDDED_ONLY_document_hydrates_unchanged(workspace):
    """THE OLDEST SHAPE IN THE TABLE, and the one the whole contract is written for.

    A document persisted by a build that had no `isaac_runs` at all: its runs carry
    `experiment_id: ""` (which `workspace._hydrate_runs` deliberately does NOT
    repair, because repairing it on read would bump every record's `rev` on a mere
    listing) and no `ordinal` (so every run defaults to 0). It is NEVER PROJECTED,
    it reads the document, and every one of its runs survives — including the two
    that share an ordinal, which a set-based reader would have been free to reorder.
    """
    exp = _experiment(rid="01ABCDEFGHJKMNPQRSTVWXYZ07")
    for run_id in ("01AAAAAAAAAAAAAAAAAAAAAAAA", "01BBBBBBBBBBBBBBBBBBBBBBBB"):
        exp.runs.append(
            ws.Run.from_state({"id": run_id, "experiment_id": "", "label": run_id[:4]})
        )
    assert [run.ordinal for run in exp.runs] == [0, 0], "the premise moved"

    conn = FakeConnection()
    _publish(conn, exp)  # a document, and NOTHING in either run table
    document = _restore(conn, exp, workspace)

    assert document["runs"] == exp.to_state()["runs"]
    assert [run["experiment_id"] for run in document["runs"]] == ["", ""]
    _only(repo.RUN_AUTHORITY_NEVER_PROJECTED)


def test_SUBMIT_and_its_REVISION_HISTORY_cannot_be_exercised_here_and_that_is_STATED(
    durable,
):
    """§7.5's list names *first Submit* and *subsequent Draft revision*, and this
    build CANNOT REACH EITHER. Stated as an executable claim rather than omitted,
    because a scenario silently missing from a suite is indistinguishable from one
    that passed.

    THE REASON IS NOT THIS SLICE'S TO FIX. `POST .../submit` answers `409
    human_actor_required / no_verifier_configured`: submitting records WHO
    performed it, and `CLAUDE.md` §15 records that no trusted authentication
    boundary exists in this build, so no verifier mints an actor. `0003` and `0004`
    are additionally not applied anywhere.

    WHAT CAN BE SAID, AND IS: the reader is not involved in either. Submit and the
    revision snapshots read the hydrated `ws.Experiment` (contract §7.2 rows 12 and
    13) — the same object either way if the reader is correct, which is precisely
    the parity property every case above asserts. A real-engine Submit case belongs
    with `0003`/`0004`, not here.
    """
    client, _, _ = durable
    rid = client.post("/api/experiments", json={"title": "Submit"}).json()["id"]
    _add_run(client, rid, "R1")

    submitted = client.post(
        f"/api/experiments/{rid}/submit", headers={"If-Match": _etag(client, rid)}
    )
    assert submitted.status_code == 409, submitted.text
    assert submitted.json()["reason"] == "no_verifier_configured"


def test_a_CONFLICTING_write_that_LOST_the_swap_leaves_the_projection_untouched(
    durable,
):
    """§2.2 invariant 3 seen from the reader's side: a writer that lost the CAS
    stamps nothing, so a lost write cannot leave a projection claiming completeness
    for a document it failed to write. The record still restores as the WINNER's."""
    client, conn, tmp_path = durable
    rid = client.post("/api/experiments", json={"title": "Conflict"}).json()["id"]
    client.post(
        f"/api/experiments/{rid}/runs",
        json={"label": "R1"},
        headers={"If-Match": _etag(client, rid)},
    )
    before = _runs(client, rid)
    stamp_before = conn.projections[rid]
    rows_before = dict(conn.runs)

    conn.refuse_upsert.add(rid)
    conn.stored[rid] = json.loads(
        (tmp_path / "ws" / rid / "experiment.json").read_text()
    )
    refused = client.post(
        f"/api/experiments/{rid}/runs",
        json={"label": "a run the loser tried to add"},
        headers={"If-Match": _etag(client, rid)},
    )
    assert refused.status_code == 412, refused.text
    assert conn.projections[rid] == stamp_before, "a loser stamped a claim"
    assert conn.runs == rows_before, "a loser wrote run rows"

    conn.refuse_upsert.discard(rid)
    after = _restart(client, conn, tmp_path, rid)
    assert _labels(after) == _labels(before) == ["R1"]


# =============================================================================
# 8. THE NEGATIVE CONTROL — proving this suite can turn RED
# =============================================================================
#
# §7.5: *a parity suite that passes with the feature off is testing nothing*, and
# this repository has a written instance of exactly that —
# `test_detail_route_composes_each_run_once.py::_disable_threading` silently
# failed to revert each newly-added seam until it was extended, TWICE.
#
# THE LESSON FROM THAT FAILURE IS BUILT IN HERE. The control does not re-implement
# a case in order to break it; it calls THE SAME FUNCTIONS the real cases call,
# under a mutation, and requires them to raise. So a case added above is covered by
# the control the moment it is added, and a control that stopped reverting anything
# would fail its own assertion rather than silently pass.


def _revert_the_reader(monkeypatch):
    """MUTATION 1 — the reader is reverted to Stage 2a: authority never moves.

    This is the pre-Stage-2b behaviour exactly: `hydrate` writes `state["runs"]`
    unchanged. Every case that asserts the rows are the SOURCE must fail.
    """
    monkeypatch.setattr(
        repo,
        "resolve_run_authority",
        lambda *a, **k: (repo.RUN_AUTHORITY_UNAVAILABLE, None),
    )


def _read_zero_rows_as_zero_runs(monkeypatch):
    """MUTATION 2 — THE DEFECT THE WHOLE CONTRACT EXISTS TO MAKE UNWRITABLE.

    `rows exist -> use them`, with no completeness claim consulted: any state,
    however unprojected, returns whatever rows were found. On a NEVER-PROJECTED
    experiment that is `[]`, so every run of every pre-existing record is silently
    deleted and the pass reports success.
    """
    monkeypatch.setattr(
        repo,
        "resolve_run_authority",
        lambda state, projection, run_rows, **k: (
            repo.RUN_AUTHORITY_COMPLETE,
            [document for _, document in run_rows if document is not None],
        ),
    )


def _never_disclose_a_mismatch(monkeypatch):
    """MUTATION 3 — the fallback still happens and the DISCLOSURE does not.

    §7.4 rule 3 exists because a mismatch that only fell back is indistinguishable
    from a healthy fallback. This mutation makes exactly that substitution, so a
    suite that only checked "nothing was lost" would stay green.
    """
    real = repo.resolve_run_authority

    def quiet(*a, **k):
        state, runs = real(*a, **k)
        if state == repo.RUN_AUTHORITY_MISMATCH:
            return repo.RUN_AUTHORITY_NEVER_PROJECTED, None
        return state, runs

    monkeypatch.setattr(repo, "resolve_run_authority", quiet)


def _compare_by_run_id_only(monkeypatch):
    """MUTATION 4 — THE HOLE THIS SLICE CLOSED, PUT BACK.

    §7.4 rule 1 as it was originally written and originally implemented: the row
    set is compared against the document BY RUN ID, so a row whose CONTENT has
    diverged inside a matching id set is COMPLETE and the row's document is written
    over the scientist's. Reverting only the content check — everything else in
    `resolve_run_authority` is the real thing — is what makes this mutation a test
    of the new rule rather than of the whole function.
    """
    monkeypatch.setattr(repo, "_rows_reproduce_the_document", lambda rows, runs: True)


@pytest.mark.parametrize(
    "mutation,cases",
    [
        (
            _revert_the_reader,
            [
                test_THE_ROWS_REALLY_ARE_THE_SOURCE_and_not_merely_equal_to_the_document,
                test_the_resolved_runs_ARE_THE_ROW_DOCUMENTS_by_identity,
                test_a_ROW_MUTATED_OUT_OF_BAND_is_a_MISMATCH_and_the_DOCUMENT_WINS,
                test_the_restored_run_order_is_sorted_runs_order_and_not_the_INDEX_order,
                test_a_COMPLETE_projection_restores_the_runs_FROM_THE_ROWS,
            ],
        ),
        (
            _read_zero_rows_as_zero_runs,
            [
                test_a_NEVER_PROJECTED_experiment_with_three_runs_hydrates_with_three_runs,
                test_a_row_deleted_OUT_OF_BAND_hydrates_from_the_document_and_is_COUNTED,
                test_a_CONCURRENT_SAVE_DURING_THE_CUTOVER_reads_the_document_and_loses_nothing,
            ],
        ),
        (
            _never_disclose_a_mismatch,
            [
                test_a_row_deleted_OUT_OF_BAND_hydrates_from_the_document_and_is_COUNTED,
                test_a_ROW_MUTATED_OUT_OF_BAND_is_a_MISMATCH_and_the_DOCUMENT_WINS,
            ],
        ),
        (
            _compare_by_run_id_only,
            [
                test_a_ROW_MUTATED_OUT_OF_BAND_is_a_MISMATCH_and_the_DOCUMENT_WINS,
                test_a_row_MISSING_A_KEY_the_document_carries_is_a_MISMATCH,
            ],
        ),
    ],
    ids=[
        "reader-reverted",
        "zero-rows-read-as-zero-runs",
        "mismatch-not-disclosed",
        "content-rule-narrowed-back-to-run-ids",
    ],
)
def test_THE_NEGATIVE_CONTROL_every_named_case_turns_RED_under_the_mutation(
    workspace, monkeypatch, mutation, cases
):
    """EACH NAMED CASE MUST FAIL, AND IT IS ASSERTED PER CASE RATHER THAN AS A SET.

    "at least one failed" is the assertion that let `_disable_threading` pass while
    reverting nothing; requiring EVERY listed case to raise is what makes a case
    that stopped depending on the feature visible here instead of silently
    tolerated.
    """
    mutation(monkeypatch)
    for case in cases:
        repo.forget_run_authority()
        repo.forget_run_table_presence()
        for child in workspace.iterdir() if workspace.exists() else []:
            if child.is_dir():
                for path in child.glob("*"):
                    path.unlink()
        with pytest.raises((AssertionError, KeyError, IndexError)):
            if case is test_a_COMPLETE_projection_restores_the_runs_FROM_THE_ROWS:
                case(workspace, ("Run 1", "Run 2"))
            elif case is test_the_resolved_runs_ARE_THE_ROW_DOCUMENTS_by_identity:
                # A PURE-PREDICATE CASE: it takes no workspace, deliberately, and
                # that is the whole reason it is here — it states "the rows are the
                # source" at a level no serialisation can erase.
                case()
            else:
                case(workspace)


def test_the_negative_control_is_not_vacuous_and_the_same_cases_PASS_unmutated(
    workspace,
):
    """THE CONTROL'S OWN CONTROL. A `pytest.raises` block that passed because the
    case was broken for an unrelated reason would prove nothing, so the same three
    cases are run here with no mutation at all and must succeed."""
    for case in (
        test_a_NEVER_PROJECTED_experiment_with_three_runs_hydrates_with_three_runs,
        test_THE_ROWS_REALLY_ARE_THE_SOURCE_and_not_merely_equal_to_the_document,
        test_a_ROW_MUTATED_OUT_OF_BAND_is_a_MISMATCH_and_the_DOCUMENT_WINS,
        test_a_row_MISSING_A_KEY_the_document_carries_is_a_MISMATCH,
        test_a_row_deleted_OUT_OF_BAND_hydrates_from_the_document_and_is_COUNTED,
    ):
        repo.forget_run_authority()
        repo.forget_run_table_presence()
        for child in workspace.iterdir() if workspace.exists() else []:
            if child.is_dir():
                for path in child.glob("*"):
                    path.unlink()
        case(workspace)
    test_the_resolved_runs_ARE_THE_ROW_DOCUMENTS_by_identity()
