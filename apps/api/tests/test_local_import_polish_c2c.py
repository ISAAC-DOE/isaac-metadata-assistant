"""Skill polish, cycle 2 (blind cross-check). Synthetic only.

* ``excerpt`` of a candidate whose locator is a file-name token shows the file name and which token
  (the source text), not the file's first lines.
* ``reveal`` compares an AI reading with the parser's value by ``records.same_value`` (the same
  instant written two ways agrees) and says the ``relation`` the way the record's evidence does.
* ``annotate --source-id`` must be one of the sources the target's locators name (exit 2); a target
  with no source locators still takes any known source.
"""

from __future__ import annotations

import shutil

import pytest

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M

from test_local_import_records import SEMANTICS, _cand, _run, bdir, pristine  # noqa: F401  (fixtures)


def _filename_candidate(b):
    for c in b["candidates"]:
        for e in c["evidence"]:
            if (e["locator"] or "").startswith("filename token") and e["method"] != "ai_interpretation":
                return c, e
    raise AssertionError("the corpus has no file-name token candidate")


def test_excerpt_of_a_file_name_token_shows_the_name_and_the_token(bdir, tmp_path):
    source = tmp_path / "src"
    shutil.copytree(SEMANTICS, source)
    b = M.load(bdir)
    c, e = _filename_candidate(b)
    got = M.excerpt(b, c["candidate_id"], source=str(source))
    hit = next(x for x in got["excerpts"] if x["locator"] == e["locator"])
    assert e["relative_path"] in hit["text"] and "filename token" in hit["text"]
    assert hit["lines"] is None
    assert "#E" not in hit["text"] and "#S" not in hit["text"]  # not the file's first lines


def test_reveal_agrees_for_the_same_instant_written_two_ways(bdir):
    b = M.load(bdir)
    c = _cand(b, "timestamps.acquired_start_utc", "run-001")
    assert c["value"].endswith("+00:00")
    other = c["value"][: -len("+00:00")] + "Z"
    M.annotate(bdir, target_id=c["candidate_id"], value=other, excerpt_locator="line 2",
               source_id=c["evidence"][0]["source_id"], model_id="m", blind=True, rationale="")
    M.annotate(bdir, target_id=c["candidate_id"], value="2100-01-01T00:11:00Z", excerpt_locator="line 2",
               source_id=c["evidence"][0]["source_id"], model_id="m", blind=True, rationale="")
    first, second = M.reveal(bdir, c["candidate_id"])["ai_readings"]
    assert first["agrees_with_parser"] is True and first["relation"] == "supports"
    assert second["agrees_with_parser"] is False and second["relation"] == "contradicts"


def test_annotate_refuses_a_source_id_the_target_does_not_name(bdir, capsys):
    b = M.load(bdir)
    c = _cand(b, "timestamps.acquired_start_utc", "run-001")
    named = sorted({e["source_id"] for e in c["evidence"] if e["method"] != "ai_interpretation"})
    stranger = next(s["source_id"] for s in b["sources"] if s["source_id"] not in named)
    code, _, err = _run(capsys, "bundle", "annotate", str(bdir), "--target", c["candidate_id"], "--value", "x",
                        "--source-id", stranger, "--model", "m", "--blind", "--rationale", "r")
    assert code == 2 and stranger in err and all(n in err for n in named)
    assert M.load(bdir)["ai_interpretations"] == []
    code, _, _ = _run(capsys, "bundle", "annotate", str(bdir), "--target", c["candidate_id"], "--value", "x",
                      "--source-id", named[0], "--model", "m", "--blind", "--rationale", "r")
    assert code == 0


def test_annotate_still_takes_any_known_source_for_a_target_with_no_source_locators(bdir):
    b = M.load(bdir)
    miss = b["missing_values"][0]
    out = M.annotate(bdir, target_id=miss["value_id"], value="x", excerpt_locator=None,
                     source_id=b["sources"][0]["source_id"], model_id="m", blind=False, rationale="")
    assert out["interpretation_id"]
