"""Audit of 18 Nov 2026, finding 14: "I don't know" on a required field says what it costs: how many records cannot
be exported until it is answered. SYNTHETIC data only.
"""

from __future__ import annotations

import json
import shutil

import pytest

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

from tests_support_records import BY, pristine_bundle  # noqa: F401


@pytest.fixture()
def bdir(pristine_bundle, tmp_path):
    target = tmp_path / "b"
    shutil.copytree(pristine_bundle, target)
    M.group(target)
    return target


def _blocking(bdir, path):
    return next(q for q in Q.consolidate(M.load(bdir))["questions"] if q["blocking"] and q.get("target_field_path") == path)


def test_deferring_a_required_field_says_how_many_records_wait_on_it(bdir, capsys):
    q = _blocking(bdir, "sample.sample_form")
    groups = len(q.get("blocks_group_ids") or [q["scope"]])
    capsys.readouterr()
    assert cli.main(["bundle", "decide", str(bdir), "--question", q["question_id"], "--decision", "defer",
                     "--by", "SYN Scientist"]) == 0
    said = json.loads(capsys.readouterr().out)
    assert said["deferral_cost"]["records_blocked"] == groups >= 1
    assert said["deferral_cost"]["fields"] == ["sample.sample_form"]
    assert f"{groups} record" in said["statement"] and "cannot be exported until this is answered" in said["statement"]
    assert said["statement"].startswith("deferred for")              # the plain sentence first, the cost after it
    # the question is still asked, and still blocking
    again = Q.question(Q.consolidate(M.load(bdir)), q["question_id"])
    assert again["blocking"] and again["deferred"]


def test_deferring_an_optional_value_costs_nothing_and_says_nothing_more(bdir):
    q = next(q for q in Q.consolidate(M.load(bdir))["questions"]
             if q["kind"] == "optional_values" and not q["blocking"] and not q.get("completeness") and q.get("fields"))
    field = sorted(q["fields"])[0]
    done = M.decide_question(bdir, question_id=q["question_id"], field=field, decision="defer", value=None, **BY)
    assert "deferral_cost" not in done and "cannot be exported" not in done["statement"]


def test_a_deferral_by_target_id_says_the_same(bdir):
    q = _blocking(bdir, "attribution.produced_by.group")
    done = M.decide(bdir, target_ids=[t["id"] for t in q["targets"]], decision="defer", value=None, **BY)
    assert done["deferral_cost"]["records_blocked"] >= 1 and "cannot be exported" in done["statement"]
