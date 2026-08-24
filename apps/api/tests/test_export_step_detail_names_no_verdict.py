"""THE SERVER STATED AN OFFICIAL-SCHEMA VERDICT THAT WAS NEVER RENDERED.

WHAT WAS MEASURED. ``routes.py``'s worked-example pipeline built its ``export_draft``
step detail as::

    f"official schema valid: {result.official_report.ok if result.official_report else False}"

``isaac_records.export.export_draft`` returns ``official_report=None`` on exactly two
paths that ``return`` BEFORE ``validate_official`` is ever called: the no-guessing draft
failure, and ISAAC's anchored-pattern EXACTNESS gate, whose findings it folds into
``draft_report`` on the way out. On both of them that ternary rendered

    "official schema valid: False"

for a record the official schema never examined. Measured here, over a real
``export_draft`` call on a real draft carrying ``tags: ["campaign\\n"]`` — the exactness
case ``exactness.py`` documents, where Python's ``$`` also matches before a trailing
newline::

    result.ok                     False
    result.official_report        None          <- validate_official never ran
    result.draft_report.errors    1
    old detail                    "official schema valid: False"

WHY IT IS A PROJECT-RULE VIOLATION AND NOT A WORDING NIT. ``CLAUDE.md`` §1 makes the
vendored schema upstream-owned; §12 states the rule in as many words: *"the gate is
ISAAC's, not upstream's ... no surface may report an exactness refusal as an
official-schema error."* §12 also records that a surface shipped exactly this conflation
once already (``VerdictCard``). This was the same claim in the SERVER's own words, which
is why no frontend fix could reach it: ``StagedRunner`` renders ``detail`` verbatim, and
its own docstring quotes this exact string as the text a failing step shows.

THE VOCABULARY IS BORROWED, NOT INVENTED. Three surfaces already faced the same missing
discriminator on the analogous per-run payload and settled it the same way — name the
official ISAAC schema ONLY where the verdict came from ``validate_official``, otherwise
report the finding without naming a source (``ValidateReview.tsx``, ``RunFindings.tsx``).

WHAT THIS FILE DOES NOT CLAIM. It does not claim the branch is reachable through
``POST /api/demo/run``: that operation applies the committed demo answers to a canonical
seed, and those pass. The defect was latent on that route and live in the helper, so the
helper is tested against real ``ExportResult``s and the route is tested against an
injected one — no assertion here depends on a hand-built report object.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import isaac_api.routes as routes
import isaac_api.workspace as ws
from isaac_records.export import export_draft

from test_scientist_can_finish_a_record import DESCRIPTOR, QC, SERIES


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


@pytest.fixture()
def tutorial(tmp_path, monkeypatch):
    """A client bound to a worked-example session — what `POST /api/demo/run` requires.

    Same workspace as ``client``; the worked-example scope is derived from it. Two
    fixtures rather than one because ``POST /api/experiments`` is refused in a tutorial
    scope and ``POST /api/demo/run`` is refused outside one.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from conftest import tutorial_client
    from isaac_api.app import create_app

    return tutorial_client(create_app())


def _answered_draft(client) -> dict:
    """A real, complete draft from the product's own create+answer path."""
    exp_id = client.post("/api/experiments", json={"title": "Cu K-edge"}).json()["id"]
    version = client.get(f"/api/experiments/{exp_id}").json()["version"]
    applied = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={
            "answers": {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC},
            "confirmed_by_user": True,
        },
        headers={"If-Match": f'"{version}"'},
    )
    assert applied.status_code == 200, applied.text
    return ws.load_experiment(exp_id).draft


def test_an_exactness_refusal_is_not_reported_as_an_official_schema_verdict(client):
    """THE REGRESSION, on the gate `CLAUDE.md` §12 names explicitly."""
    draft = json.loads(json.dumps(_answered_draft(client)))
    draft["tags"] = ["campaign\n"]

    result = export_draft(draft, routes.REPO_ROOT)
    # The precondition, asserted rather than assumed: the official validator never ran.
    assert result.ok is False
    assert result.official_report is None
    assert len(result.draft_report.errors) == 1, result.draft_report.errors

    detail = routes._export_step_detail(result)
    assert "official schema" not in detail, detail
    assert "official" not in detail.split("refused before official validation")[-1], detail
    assert detail == (
        "refused before official validation — 1 finding on the candidate record; "
        "source not named"
    ), detail


def test_a_no_guessing_refusal_is_not_reported_as_an_official_schema_verdict(client):
    """The OTHER `official_report is None` path — `export.py`'s first early return.

    Reached here through the ``record_id`` ULID check, which appends to ``draft_report``
    and returns before ``transform``. Its findings are as un-official as the exactness
    ones and used to render the same false sentence.
    """
    result = export_draft(_answered_draft(client), routes.REPO_ROOT, record_id="not-a-ulid")
    assert result.ok is False
    assert result.official_report is None

    detail = routes._export_step_detail(result)
    assert "official schema valid" not in detail, detail
    assert "source not named" in detail, detail


def test_a_real_official_verdict_still_names_the_official_schema(client):
    """The discriminator is `official_report is not None`, NOT `result.ok`.

    A present report is a real verdict from ``validate_official`` and keeps the original
    sentence verbatim — including its Python-cased boolean, which ``StagedRunner``'s
    docstring and the frontend fixtures quote.
    """
    result = export_draft(_answered_draft(client), routes.REPO_ROOT)
    assert result.official_report is not None
    assert routes._export_step_detail(result) == "official schema valid: True"


def test_a_genuine_official_failure_keeps_the_original_sentence(client):
    """`ok: False` WITH a report is the one case that may say "valid: False".

    Built by validating a record the official schema really does reject, so the report is
    a real ``OfficialReport`` from the authoritative validator rather than a stand-in.
    """
    from isaac_records.export import ExportResult
    from isaac_records.official import validate_official

    report = validate_official({}, routes.REPO_ROOT)
    assert report.ok is False and report.errors

    result = export_draft(_answered_draft(client), routes.REPO_ROOT)
    failed = ExportResult(False, result.record, None, result.draft_report, report)
    assert routes._export_step_detail(failed) == "official schema valid: False"


def test_the_pipeline_step_renders_the_helper_rather_than_its_own_sentence(
    client, tutorial, monkeypatch
):
    """END TO END over HTTP, on the operation that publishes the string.

    The refused-early branch is not reachable through this route with the committed demo
    answers, so the REAL ``ExportResult`` measured above is injected in place of
    ``export_draft``. That keeps the assertion about the route's rendering while the
    verdict under test stays one the truth core actually produced.
    """
    draft = json.loads(json.dumps(_answered_draft(client)))
    draft["tags"] = ["campaign\n"]
    refused = export_draft(draft, routes.REPO_ROOT)
    assert refused.official_report is None

    monkeypatch.setattr(routes, "export_draft", lambda *a, **k: refused)
    ran = tutorial.post("/api/demo/run", json={"mode": "full"})
    assert ran.status_code == 200, ran.text
    step = next(s for s in ran.json()["steps"] if s["name"] == "export_draft")
    assert step["ok"] is False
    assert step["detail"] == (
        "refused before official validation — 1 finding on the candidate record; "
        "source not named"
    ), step
    assert "official schema valid" not in step["detail"]


def test_the_normal_pipeline_run_is_unmoved(tutorial):
    """The committed worked example still reports the verdict it always reported."""
    ran = tutorial.post("/api/demo/run", json={"mode": "full"})
    assert ran.status_code == 200, ran.text
    step = next(s for s in ran.json()["steps"] if s["name"] == "export_draft")
    assert step["ok"] is True
    assert step["detail"] == "official schema valid: True", step


def test_the_singular_plural_is_not_a_stray_s(client):
    """`1 finding`, `2 findings`. Small, and it renders in a UI verbatim."""
    from isaac_records.draft_validator import DraftReport
    from isaac_records.export import ExportResult

    for n, expected in ((0, "0 findings"), (1, "1 finding"), (2, "2 findings")):
        report = DraftReport()
        for i in range(n):
            report.err(f"$.f{i}", "refused")
        detail = routes._export_step_detail(ExportResult(False, None, None, report, None))
        assert detail.startswith(f"refused before official validation — {expected} "), detail
