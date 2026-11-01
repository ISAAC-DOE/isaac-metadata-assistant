"""Cycle 15 review fixes on the integrated branch.

* ``same_ruling_left`` reads each peer's value as it holds it now: a ``confirm`` ruling's value is its candidate's
  own, so ruling the same value again never warns, and a real split names the value the other runs keep.
* Text lines for cells not tied to the sheet say "not tied", not "clash".
"""

from isaac_api.local_import import mutations as M
from isaac_api.local_import import template as T

from test_local_import_template_adopt import WHO, corpus, grouped, grouped_base, ticking  # noqa: F401

POT = "context.electrochemistry.potential_setpoint_V"
NOTE = "template import (your ruling on disagreement D3: SYN_their.xlsx 'File List'!H9, 'File List'!H10 = 2.5)"


def _pot(b, run):
    return next(c for c in b["candidates"] if c["target_field_path"] == POT and c["run_id"] == run)


def _ruled(grouped):
    b = M.load(grouped)
    c8, c9 = _pot(b, "run-008"), _pot(b, "run-009")
    assert c8["value"] == c9["value"]
    M.decide(grouped, target_ids=[c8["candidate_id"], c9["candidate_id"]], decision="confirm", value=None, by=WHO,
             orcid=None, note=NOTE)
    return c8["candidate_id"], c8["value"]


def test_a_confirm_ruling_restated_with_its_own_value_does_not_warn(grouped, ticking):
    t8, held = _ruled(grouped)
    same = M.decide(grouped, target_ids=[t8], decision="correct", value=held, by=WHO, orcid=None)
    assert not same.get("same_ruling_left")


def test_a_split_of_a_confirm_ruling_names_the_value_the_other_run_holds(grouped, ticking):
    t8, held = _ruled(grouped)
    split = M.decide(grouped, target_ids=[t8], decision="correct", value=held + 1.0, by=WHO, orcid=None)
    left = split.get("same_ruling_left")
    assert left and left[0]["value"] == held


def test_cells_not_tied_say_not_tied():
    item = {"cell": "'Campaign Info'!B3", "header": "Facility Name", "value": "ZZ", "targets": 9, "runs": 9,
            "clashes": 1, "held_back": 8, "hold_value": 0, "target_ids": ["a", "b"], "reason": "why", "command": "c"}
    assert "1 not tied" in T._cell_lines([item], "not tied")[0]
    assert "1 clash" in T._cell_lines([item])[0]
