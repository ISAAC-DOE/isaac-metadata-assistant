"""AN AGENT CAN GIVE A RUN ITS SCIENCE, AND THE RECORD THEN EXPORTS. Nothing borrowed.

WHY THIS FILE EXISTS, AND WHY IT IS NOT A NEW CAPABILITY
========================================================
``docs/mcp-capability-audit.md`` §5A recorded a capability gap — *"give a Run its
spectrum, verdict or descriptors: **no**"* — and §5A.1 records it **CLOSED on
2026-08-19** by ``isaac_list_questions`` + ``isaac_answer_questions``. A 2026-09-17
slice was commissioned to close it a second time, re-measured it first, and found it
genuinely closed. **So this file adds no tool and no write path.** It closes the
different, narrower thing that measurement found: the capability was real and CI did
not prove it end to end.

WHAT THE SUITE ALREADY PROVED, so this file does not repeat it
==============================================================
``test_mcp_server.py`` §6A drives ``isaac_answer_questions`` at both levels against the
committed seed ``01SYNTHXANESSEED0000000002``, proves a spectrum lands on the named run
and not on its sibling, and proves eight wrong-typed shapes are refused.
``test_answers_that_cannot_land.py`` proves the same refusals over plain HTTP.

THE THREE THINGS NO TEST REACHED, each measured on ``e34983a9`` before this file
================================================================================
1. **An OPEN ``qc`` question on a Run, ANSWERED.** Every MCP ``qc`` case is either a
   refusal or a *correction*. The suite says why in its own words
   (``test_mcp_server.py``, the `qc` half of the per-field correction test): on that
   seed *"``qc`` arrives from the sheet already carrying a status, so it is NOT an open
   question on the run and the answer path drops it."* So the **accepting** branch of
   ``qc`` at the run level was exercised nowhere — and ``qc`` not being forwarded at all
   is a defect this repository has already shipped once
   (``test_scientist_can_finish_a_record.py``, defect 1).
2. **All three blocks on one Run, from a record with no answers at all.** The seed has
   ``series`` and ``descriptor`` open and ``qc`` already answered, so no MCP test ever
   held a Run that owed all three.
3. **An export after an agent finished the record.** No MCP test exports, so "the agent
   finished it" was never carried through to "and it is a valid official ISAAC record".
   There is no export TOOL and there must not be — ``export`` is in
   ``FORBIDDEN_TOOL_TOKENS`` — so the export here is a person's own HTTP call, which is
   exactly the division of labour the audit describes.

IT BORROWS NOTHING, and that is asserted rather than intended
=============================================================
Every value below is written out as a person would type it. No canonical seed, no
``demo_answer``, no ``build_draft``. That is the same discipline
``test_scientist_can_finish_a_record.py`` was written with, for the reason its docstring
gives: the five canonical scenarios arrive already carrying a spectrum, a verdict and a
descriptor, so a suite built on them begins past the part that does not work.
``test_this_file_borrows_nothing_from_a_fixture`` parses this file's own source and
fails if it ever starts.

DATA BOUNDARY: **none.** Every value is synthetic and unmistakably so, in a ``tmp_path``
workspace. No database connection is opened, no migration is applied, no external host
is contacted, no credential is read, and nothing production-derived is touched.

AUTHORIZATION BASIS: ``CLAUDE.md`` §15 — *"AI / MCP / voice IMPLEMENTATION against
deterministic fake providers — authorized by the project owner 2026-08-12"* (code,
APIs, tests, security boundaries) — plus the 2026-08-29 application-side extension's
*"the remote MCP and bounded change-feed application architecture"* and *"the associated
tests"*. This file exercises existing routes and adds none, so it needs no write
authorization of its own.
"""

from __future__ import annotations

import asyncio
import json
import pathlib

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws
from isaac_api.mcp import LocalLoopbackDeployment, McpServer, Scope
from isaac_api.mcp.policy import (
    ALLOWED_METHODS,
    FORBIDDEN_TOOL_TOKENS,
    OPERATIONS,
    PERMITTED_TOOL_NAMES,
    forbidden_tool_reason,
)
from isaac_api.mcp.tools import TOOLS

# --------------------------------------------------------------------------
# the values. written out, not harvested. see the module docstring.
# --------------------------------------------------------------------------

#: A three-point spectrum shaped as the store keeps it. Small on purpose: this asserts
#: that a series an AGENT sent is stored and exported, not that a reduction works.
SERIES = [
    {
        "series_id": "agent_supplied_spectrum",
        "independent_variables": [
            {"name": "incident_energy", "unit": "eV", "values": [8970, 8980, 8990]}
        ],
        "channels": [
            {
                "name": "absorption",
                "unit": "mu_normalized",
                "role": "primary_signal",
                "values": [0.03, 0.87, 1.41],
            }
        ],
    }
]

#: A descriptor exactly as the entry form emits one — `name` from the vocabulary,
#: `kind`/`source` from the schema's enums, a numeric value and an uncertainty.
DESCRIPTOR = {
    "name": "inflection_point_energy",
    "kind": "absolute",
    "source": "manual",
    "value": 8981.4,
    "unit": "eV",
    "uncertainty": {"sigma": 0.02, "unit": "eV", "basis": "reported"},
}

#: The verdict. THE BLOCK NO MCP TEST HAD EVER ANSWERED ON THE ACCEPTING BRANCH.
QC = {"status": "valid", "evidence": "I0 steady over three scans; no shutter glitches."}

#: What this file sends as a title. Unmistakably synthetic.
TITLE = "Synthetic Cu K-edge XANES, agent-completed"


# --------------------------------------------------------------------------
# fixtures — an EMPTY workspace and NO worked-example session
# --------------------------------------------------------------------------

@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return create_app()


@pytest.fixture()
def client(app) -> TestClient:
    """The person's own HTTP client. Creates the record; exports it at the end."""
    return TestClient(app)


@pytest.fixture()
def agent(app) -> McpServer:
    """The scientist's agent.

    ``tutorial_session_id=None`` on purpose: this record lives in the ordinary
    workspace, so nothing here can be satisfied by a committed example.
    """
    return McpServer(
        app,
        binding=LocalLoopbackDeployment(
            scopes=frozenset({Scope.READ, Scope.DRAFT_WRITE}),
            tutorial_session_id=None,
        ),
    )


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def call(agent: McpServer, name: str, **arguments) -> dict:
    """One ``tools/call``. Returns the result envelope, error or not."""
    envelope = asyncio.run(
        agent.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
    )
    assert "error" not in envelope, envelope["error"]
    return envelope["result"]


def payload(agent: McpServer, name: str, **arguments) -> dict:
    result = call(agent, name, **arguments)
    assert result["isError"] is False, result["structuredContent"]
    return result["structuredContent"]


def a_new_record(client: TestClient) -> str:
    """Create a record through the product's own Create Experiment path."""
    created = client.post("/api/experiments", json={"title": TITLE})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def record_etag(agent: McpServer, experiment_id: str) -> str:
    return payload(agent, "isaac_get_experiment", experiment_id=experiment_id)["etag"]


def a_new_run(agent: McpServer, experiment_id: str, label: str = "Run A") -> dict:
    got = payload(
        agent,
        "isaac_create_run",
        experiment_id=experiment_id,
        if_match=record_etag(agent, experiment_id),
        label=label,
    )
    return got["data"]["run"]


def run_version(agent: McpServer, experiment_id: str, run_id: str) -> str:
    """The RUN's validator, freshly read.

    Deliberately re-read rather than carried: the record's own etag is a different
    validator, and feeding it to a run-level call is a ``412`` — which the tool's
    description says, and which this helper exists so as not to rediscover.
    """
    runs = payload(agent, "isaac_list_runs", experiment_id=experiment_id)["data"]["runs"]
    return next(r["version"] for r in runs if r["id"] == run_id)


def questions(agent: McpServer, experiment_id: str) -> list[dict]:
    return payload(agent, "isaac_list_questions", experiment_id=experiment_id)["data"][
        "pending"
    ]


def answer_the_run(agent: McpServer, experiment_id: str, run_id: str, answers: dict):
    return call(
        agent,
        "isaac_answer_questions",
        experiment_id=experiment_id,
        run_id=run_id,
        if_match=f'"{run_version(agent, experiment_id, run_id)}"',
        # PASSED, NOT DEFAULTED. The agent asserts the scientist's confirmation on the
        # scientist's behalf; this file states it at the call site so the assertion is
        # visible rather than inherited.
        confirmed_by_user=True,
        answers=answers,
    )


def export(client: TestClient, experiment_id: str):
    """The PERSON exports. There is no export tool and there must not be."""
    version = client.get(f"/api/experiments/{experiment_id}").json()["version"]
    return client.post(
        f"/api/experiments/{experiment_id}/export",
        headers={"If-Match": f'"{version}"'},
    )


def record_on_disk(experiment_id: str) -> dict:
    exp = ws.load_experiment(experiment_id)
    return json.loads(exp.export_units()[0].record_path().read_text(encoding="utf-8"))


# ==========================================================================
# 1. THE WALK
# ==========================================================================

def test_an_agent_gives_one_run_all_three_blocks_and_the_record_is_ready(client, agent):
    """Create, add a Run, answer ``series`` + ``qc`` + ``descriptor``. Over MCP.

    The state before is asserted as well as the state after, because "the questions
    cleared" is only meaningful if they were open and addressed to this run.
    """
    experiment_id = a_new_record(client)
    run = a_new_run(agent, experiment_id)

    opened = questions(agent, experiment_id)
    assert {q["id"] for q in opened} == {"series", "qc", "descriptor"}, opened
    # Every one of them belongs to the run the agent just made — so answering them at
    # the record level is the refused call, not this one.
    assert all(q["run_id"] == run["id"] for q in opened), opened

    result = answer_the_run(
        agent,
        experiment_id,
        run["id"],
        {"series": SERIES, "qc": QC, "descriptor": DESCRIPTOR},
    )
    assert result["isError"] is False, result["structuredContent"]
    body = result["structuredContent"]
    assert body["operation"] == "answer_run_question", body
    assert body["status"] == 200, body
    assert body["data"]["pending"] == [], body["data"]["pending"]
    assert body["data"]["status"] == "ready_to_export", body["data"]["status"]
    # All three are reported as having MOVED, which is the difference between an answer
    # landing and a no-op being reported as one.
    assert sorted(body["data"]["invalidation"]["changed_fields"]) == [
        "descriptor",
        "qc",
        "series",
    ], body["data"]["invalidation"]

    assert questions(agent, experiment_id) == []
    assert client.get(f"/api/experiments/{experiment_id}").json()["pending_count"] == 0


def test_an_OPEN_qc_question_on_a_run_is_answerable_over_mcp(client, agent):
    """THE BLOCK THE MCP SUITE NEVER ANSWERED, isolated so its failure is unambiguous.

    Every other MCP ``qc`` case is a refusal or a correction of a verdict the seed draft
    already held. This one answers an OPEN ``qc``, alone, and reads the stored verdict
    back out of the run's draft rather than out of the response — because a response
    saying "changed" is the thing that was once wrong.
    """
    experiment_id = a_new_record(client)
    run = a_new_run(agent, experiment_id)
    assert "qc" in {q["id"] for q in questions(agent, experiment_id)}

    result = answer_the_run(agent, experiment_id, run["id"], {"qc": QC})
    assert result["isError"] is False, result["structuredContent"]
    assert result["structuredContent"]["data"]["invalidation"]["changed_fields"] == [
        "qc"
    ], result["structuredContent"]["data"]["invalidation"]

    stored = ws.load_experiment(experiment_id).sorted_runs()[0].draft
    assert stored["qc"]["status"] == QC["status"], stored.get("qc")
    assert stored["qc"]["evidence"] == QC["evidence"], stored.get("qc")
    assert "qc" not in {q["id"] for q in questions(agent, experiment_id)}
    # And the verdict earned an evidence entry rather than arriving unattributed.
    assert stored["block_evidence"]["qc:status"], stored.get("block_evidence")


# ==========================================================================
# 2. AND THEN IT EXPORTS — the half no MCP test carried through
# ==========================================================================

def test_the_record_an_agent_finished_exports_and_validates_officially(client, agent):
    """Not "the app said ok" — the bytes on disk, against the vendored schema.

    The export is the PERSON's HTTP call. ``export`` is in ``FORBIDDEN_TOOL_TOKENS``, so
    a tool that did this could not be registered, and that division is the point rather
    than a limitation of the test.
    """
    from isaac_records.official import validate_official

    experiment_id = a_new_record(client)
    run = a_new_run(agent, experiment_id)
    answer_the_run(
        agent,
        experiment_id,
        run["id"],
        {"series": SERIES, "qc": QC, "descriptor": DESCRIPTOR},
    )

    exported = export(client, experiment_id)
    assert exported.status_code == 200, exported.text
    assert exported.json()["ok"] is True, exported.json()

    report = validate_official(record_on_disk(experiment_id), pathlib.Path.cwd())
    ok = report.ok if hasattr(report, "ok") else report["ok"]
    assert ok, report


def test_the_values_in_the_record_are_the_values_the_AGENT_supplied(client, agent):
    """A blocker clearing is not the same as a value arriving."""
    experiment_id = a_new_record(client)
    run = a_new_run(agent, experiment_id)
    answer_the_run(
        agent,
        experiment_id,
        run["id"],
        {"series": SERIES, "qc": QC, "descriptor": DESCRIPTOR},
    )
    assert export(client, experiment_id).json()["ok"] is True

    record = record_on_disk(experiment_id)
    assert record["measurement"]["series"][0]["series_id"] == "agent_supplied_spectrum"
    assert record["measurement"]["qc"] == QC
    stored = record["descriptors"]["outputs"][0]["descriptors"][0]
    assert {k: stored[k] for k in DESCRIPTOR} == DESCRIPTOR, stored


def test_the_record_does_not_name_an_agent_as_the_descriptor_s_author(client, agent):
    """The provenance question this path raises that the HTTP path does not.

    A descriptor block records the *"Tool/pipeline/person that generated these
    descriptors"*. Here a model's client sent it — so the one thing that must not appear
    is an assertion that some agent, this server, or a demo authored it. The record says
    what it can defend: the application, and that a person supplied the value.
    """
    experiment_id = a_new_record(client)
    run = a_new_run(agent, experiment_id)
    answer_the_run(agent, experiment_id, run["id"], {"series": SERIES, "qc": QC, "descriptor": DESCRIPTOR})
    export(client, experiment_id)

    output = record_on_disk(experiment_id)["descriptors"]["outputs"][0]
    serialized = json.dumps(output).lower()
    assert "demo" not in serialized, output
    assert "mcp" not in serialized, output
    assert "claude" not in serialized, output
    assert output["generated_by"]["agent"] == "isaac-metadata-assistant", output
    # Absent rather than invented: this build cannot name the person (no trusted
    # authentication boundary) and has no version to vouch for.
    assert "author" not in output["generated_by"], output["generated_by"]


# ==========================================================================
# 3. WRONG-TYPED INPUT AT THE RUN LEVEL — typed refusal, never a 500, never a coercion
# ==========================================================================

#: Shapes ``complete.py``'s type guards reject. Each is a mistake a model plausibly
#: makes: the bare verdict the question's own text suggests, the key a reader guesses,
#: an off-enum status, the pair-list a plotting library hands you, an empty series, and
#: a descriptor written as prose.
UNSTORABLE = [
    pytest.param({"qc": "valid"}, "qc", id="qc=bare-verdict-string"),
    pytest.param({"qc": {"verdict": "valid"}}, "qc", id="qc=wrong-key"),
    pytest.param({"qc": {"status": "ok"}}, "qc", id="qc=off-enum"),
    pytest.param({"series": []}, "series", id="series=empty"),
    pytest.param({"series": [[8979.0, 0.11]]}, "series", id="series=list-of-pairs"),
    pytest.param({"series": "8979,0.11"}, "series", id="series=bare-string"),
    pytest.param({"descriptor": "e0 = 8979 eV"}, "descriptor", id="descriptor=string"),
    pytest.param({"descriptor": [1, 2, 3]}, "descriptor", id="descriptor=list"),
]


@pytest.mark.parametrize("answers,key", UNSTORABLE)
def test_a_wrong_typed_value_on_a_RUN_is_a_typed_refusal_that_writes_nothing(
    client, agent, answers, key
):
    """422 ``invalid_field_value``, naming the key. Not a 500, and not a coercion.

    ``CLAUDE.md`` §11 records that a wrong-typed structured answer once returned **HTTP
    500 from the truth core**, and that a typed refusal was the deliberate follow-up.
    This is that refusal measured at the RUN level, on a record with all three questions
    open — a state the seed-based cases cannot reach for ``qc``.
    """
    experiment_id = a_new_record(client)
    run = a_new_run(agent, experiment_id)
    before = {q["id"] for q in questions(agent, experiment_id)}
    assert before == {"series", "qc", "descriptor"}

    result = answer_the_run(agent, experiment_id, run["id"], answers)

    assert result["isError"] is True, result["structuredContent"]
    refusal = result["structuredContent"]
    assert refusal["status"] == 422, refusal
    body = refusal["data"]
    assert body["error"] == "invalid_field_value", body
    assert body["keys"] == [key], body
    # The message must not claim the value was already there — the false cause that
    # made the original defect a closed loop rather than merely a bad message.
    assert "identical" not in body["message"], body["message"]

    # NOTHING WRITTEN, read from the record rather than from the refusal. The whole set
    # is compared, not the one key, so a refusal that silently landed a DIFFERENT key
    # fails here too.
    assert {q["id"] for q in questions(agent, experiment_id)} == before
    assert ws.load_experiment(experiment_id).sorted_runs()[0].draft.get(key) in (
        None,
        {},
        [],
    )


def test_a_mistyped_key_on_a_RUN_is_refused_by_name_and_guesses_nothing(client, agent):
    """The ordinary mistake, and it must not be absorbed.

    ``answers`` is declared ``{"type": "object", "minProperties": 1}`` with no inner
    properties — it cannot declare them, because an asset key is the asset's own URI —
    so argument validation cannot catch a typo and the route has to.
    """
    experiment_id = a_new_record(client)
    run = a_new_run(agent, experiment_id)

    result = answer_the_run(agent, experiment_id, run["id"], {"qc_staus": "valid"})

    assert result["isError"] is True, result["structuredContent"]
    body = result["structuredContent"]["data"]
    assert result["structuredContent"]["status"] == 422, result["structuredContent"]
    assert body["error"] == "unrecognized_field", body
    assert body["keys"] == ["qc_staus"], body
    assert {q["id"] for q in questions(agent, experiment_id)} == {
        "series",
        "qc",
        "descriptor",
    }


def test_a_wrong_typed_value_alongside_a_good_one_lands_NEITHER(client, agent):
    """Fail closed on the whole request, and say so.

    The alternative — store the half that parses — would leave an agent holding a 422
    while the record had quietly changed, which is the worst of both readings.
    """
    experiment_id = a_new_record(client)
    run = a_new_run(agent, experiment_id)

    result = answer_the_run(
        agent, experiment_id, run["id"], {"series": SERIES, "qc": "valid"}
    )
    assert result["isError"] is True, result["structuredContent"]
    assert result["structuredContent"]["data"]["keys"] == ["qc"], result[
        "structuredContent"
    ]["data"]

    # The well-formed series must NOT have landed.
    assert "series" in {q["id"] for q in questions(agent, experiment_id)}
    assert not ws.load_experiment(experiment_id).sorted_runs()[0].draft.get("series")


# ==========================================================================
# 4. THE SHAPE OF THE SURFACE IS UNCHANGED BY THIS FILE
# ==========================================================================

def test_this_slice_added_no_tool(client, agent):
    """The count, asserted because the 2026-09-17 slice's finding was that it must not move.

    Sixteen tools, re-derived rather than quoted. If a later slice adds a run-level write
    tool it will fail here and have to say so — which is the deliberate act
    ``PERMITTED_TOOL_NAMES`` exists to make visible.

    ***16 -> 17 on 2026-09-18, AND THE TEST'S SUBJECT IS UNCHANGED.*** `CTX-004` added
    `isaac_get_extended_context`, a READ over the `DEC-41` level-4 companion. **That is
    not the thing this test guards against.** Its name and its own sentence are about a
    RUN-LEVEL WRITE tool: the 2026-09-17 slice's finding was that finishing a run needed
    no new tool, and the assertion exists so a later slice that adds one has to say so
    out loud. A read that touches no draft content does not weaken that, and the
    assertion two lines down — that every registered name is a permitted name — is what
    actually keeps the set closed. Saying so here is the visible act the docstring asks
    for.

    ***17 -> 18 on 2026-09-22, AND AGAIN THE SUBJECT IS UNCHANGED.*** `isaac_list_activity`
    is a READ over the append-only activity history — no draft content, no run write —
    and it is asserted read-only by name below, beside the extended-context read.
    """
    assert len(PERMITTED_TOOL_NAMES) == 18, sorted(PERMITTED_TOOL_NAMES)
    # THE ADDED TOOL IS A READ, asserted rather than asserted-by-count: a bare count
    # moving from 16 to 17 is equally consistent with a run-level write having been
    # added, which is the one outcome this test exists to make loud.
    from isaac_api.mcp.tools import TOOLS as _TOOLS

    assert _TOOLS["isaac_get_extended_context"].read_only is True
    assert _TOOLS["isaac_list_activity"].read_only is True
    assert set(TOOLS) == set(PERMITTED_TOOL_NAMES)
    # The pair that closes §5A is present, and nothing new joined them.
    assert {"isaac_list_questions", "isaac_answer_questions"} <= set(TOOLS)


@pytest.mark.parametrize(
    "candidate",
    [
        "isaac_submit_record",
        "isaac_export_record",
        "isaac_finalise_run",
        "isaac_finalize_run",
        "isaac_accept_proposal",
        "isaac_delete_run",
        "isaac_discard_experiment",
        "isaac_reset_workspace",
        "isaac_apply_migration",
        "isaac_grant_scope",
    ],
)
def test_no_finalisation_capability_can_be_named_on_this_surface(candidate):
    """BEHAVIOURAL, not a string search: the guard is asked, and it refuses.

    A name carrying a forbidden token is refused even if somebody has also added it to
    ``PERMITTED_TOOL_NAMES``, so widening the permitted set is not a route in.
    """
    reason = forbidden_tool_reason(candidate)
    assert reason is not None, candidate
    assert "forbidden capability token" in reason, reason


def test_the_surface_still_cannot_finalise_or_destroy_anything():
    """Three properties of the table's SHAPE, re-derived.

    ``ALLOWED_METHODS`` carrying no ``DELETE`` is what makes "no unrestricted
    destructive deletion" a property of the surface rather than of a review.
    """
    assert set(ALLOWED_METHODS) == {"GET", "POST", "PATCH"}
    assert "DELETE" not in ALLOWED_METHODS
    assert "PUT" not in ALLOWED_METHODS
    for name in PERMITTED_TOOL_NAMES:
        assert forbidden_tool_reason(name) is None, name
    for operation in OPERATIONS.values():
        assert operation.method in ALLOWED_METHODS, operation
    # And no forbidden verb reached a permitted tool name by any route.
    for name in PERMITTED_TOOL_NAMES:
        lowered = name.lower()
        assert not [t for t in FORBIDDEN_TOOL_TOKENS if t in lowered], name


# ==========================================================================
# 5. NEGATIVE CONTROL — this file borrows nothing
# ==========================================================================

def test_this_file_borrows_nothing_from_a_fixture():
    """The discipline the module docstring claims, asserted over this file's own source.

    ``test_scientist_can_finish_a_record.py`` carries the same control for the same
    reason: a later "simplification" that reached for a seed would restore the blind
    spot both files exist to close, and would do it while every assertion above still
    passed.

    TWO REGIONS ARE EXCLUDED AND BOTH ARE NAMED RATHER THAN QUIETLY SKIPPED. The module
    docstring lists the borrowed names in order to explain what is not used, and THIS
    FUNCTION lists them as data — so both necessarily contain them, and a scan over the
    whole file matches itself. The first version of this control did exactly that and
    failed on its own literals, which is why the exclusion is explicit.

    THE EXCLUSION IS THEN CLOSED, because "everything before this function" is only a
    complete scan if nothing follows it: the last assertion below reads the file's own
    definitions and fails if any ``def`` is added after this one. Without that, a later
    slice could append a seed-borrowing helper into the unscanned tail and this control
    would still pass.
    """
    import re

    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    after_docstring = source.split('"""', 2)[2]
    # DERIVED FROM `__name__`, not written out: a literal here would appear twice in
    # the file and the scan would match its own assignment. It also cannot drift on a
    # rename, which a literal silently would.
    me = test_this_file_borrows_nothing_from_a_fixture.__name__
    sentinel = f"def {me}"
    assert after_docstring.count(sentinel) == 1, "the sentinel must be unambiguous"
    body = after_docstring.split(sentinel)[0]

    for borrowed in (
        "demo_answer",
        "build_draft",
        "SEED_READY_ID",
        "CANONICAL_IDS",
        "create_tutorial_session",
        "01SYNTHXANESSEED",
    ):
        assert borrowed not in body, borrowed
    # The values are LITERALS here, which is the positive half of the same claim.
    assert '"series_id": "agent_supplied_spectrum"' in body
    assert '"status": "valid"' in body

    # AND NOTHING HIDES IN THE UNSCANNED TAIL. This control must be the file's last
    # definition, so "everything before it" is the whole file.
    definitions = re.findall(r"^def (\w+)", after_docstring, re.MULTILINE)
    assert definitions[-1] == me, (
        "this control must stay LAST, or the region it does not scan becomes a "
        f"place a seed-borrowing helper can live: {definitions[-3:]}"
    )
