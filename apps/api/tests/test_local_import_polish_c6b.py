"""Polish c6-b: walkthrough findings on one real beamtime, reproduced on synthetic data. Synthetic only.

* (1) ``python -m isaac_api.local_import.extract`` on a Word/PowerPoint file prints a compact manifest (counts,
  ``text_file``, the images, how to read) - the blocks are in ``text.md`` and printed only on ``--blocks``.
* (2) Template import, following the template's own rule (Electrolyte = name only, Concentration separate): a name
  equal to the name part of an AI electrolyte statement that carries a concentration ("0.5 M H2SO4") agrees with
  it, and so does a concentration equal to its concentration part; a different name or concentration is flagged.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isaac_api.local_import import extract as ex
from isaac_api.local_import import mutations as M
from isaac_api.local_import import template as T

from test_local_import_extract import make_docx, make_pptx
from test_local_import_polish_c3t import _export, _fill
from test_local_import_template_adopt import (  # noqa: F401  (fixtures)
    _col, _import, _row_of, _miss, corpus, grouped, grouped_base)

NAME = "context.electrochemistry.electrolyte.name"
CONC = "context.electrochemistry.electrolyte.concentration_M"


def _extract(capsys, argv):
    capsys.readouterr()
    code = ex.main(argv)
    out = capsys.readouterr()
    return code, out.out, out.err


def _src(tmp_path: Path) -> Path:
    """The extractor refuses an --out inside the file's own folder, so the file lives in its own folder."""
    (tmp_path / "src").mkdir(exist_ok=True)
    return tmp_path / "src"


# --- (1) a document's printed manifest is compact ---------------------------------------------------


def test_a_docx_prints_a_compact_manifest_and_its_text_is_in_the_text_file(tmp_path, capsys):
    path = make_docx(_src(tmp_path) / "n.docx")
    out = tmp_path / "out"
    code, printed, err = _extract(capsys, [str(path), "--out", str(out)])
    assert code == 0, err
    m = json.loads(printed)
    # no block is printed: the text is in the file the manifest names, which holds every paragraph and table row
    assert "blocks" not in m and "Alpha paragraph" not in printed and "Omega paragraph" not in printed
    assert m["counts"]["paragraphs"] == 5 and m["counts"]["tables"] == 1 and m["counts"]["images"] == 2
    text_file = Path(m["text_file"])
    assert text_file.is_file() and out in text_file.parents
    text = text_file.read_text(encoding="utf-8")
    assert "Alpha paragraph" in text and "h1 | h2" in text and "Omega paragraph" in text
    assert "text_file" in m["read_text"] and "--blocks" in m["read_text"]
    # the images stay: each with its position, alt text and caption
    assert [i["locations"][0]["alt_text"]["descr"] for i in m["images"]] == ["A synthetic figure", "Second figure"]
    assert m["images"][0]["locations"][0]["caption"] == "Figure 1: synthetic caption"


def test_blocks_prints_every_block_as_before(tmp_path, capsys):
    path = make_docx(_src(tmp_path) / "n.docx")
    code, printed, err = _extract(capsys, [str(path), "--out", str(tmp_path / "out"), "--blocks"])
    assert code == 0, err
    m = json.loads(printed)
    assert [b["type"] for b in m["blocks"]] == ["paragraph", "paragraph", "paragraph", "table", "paragraph", "paragraph"]
    assert "read_text" not in m


def test_a_pptx_prints_a_compact_manifest_too_and_blocks_brings_the_slides_back(tmp_path, capsys):
    path = make_pptx(_src(tmp_path) / "p.pptx")
    code, printed, err = _extract(capsys, [str(path), "--out", str(tmp_path / "out")])
    assert code == 0, err
    m = json.loads(printed)
    assert "slides" not in m and "First in order" not in printed and m["counts"]["slides"] == 2
    assert "First in order" in Path(m["text_file"]).read_text(encoding="utf-8")
    assert m["images"] and "--blocks" in m["read_text"]
    code, printed, err = _extract(capsys, [str(path), "--out", str(tmp_path / "out"), "--blocks"])
    assert [s["slide"] for s in json.loads(printed)["slides"]] == [1, 2]


def test_from_bundle_prints_each_document_compact_and_blocks_applies_to_all(tmp_path, capsys):
    root = tmp_path / "root"
    root.mkdir()
    make_docx(root / "n.docx")
    unread = tmp_path / "unread_files.json"
    unread.write_text(json.dumps({"unread_files": [{"relative_path": "n.docx", "reason_code": "no_reader_for_source_type"}]}))
    argv = ["--from-bundle", str(unread), "--root", str(root), "--out", str(tmp_path / "out")]
    code, printed, err = _extract(capsys, argv)
    [doc] = json.loads(printed)["extractions"]
    assert code == 0 and "blocks" not in doc and Path(doc["text_file"]).is_file() and "Alpha paragraph" not in printed
    code, printed, err = _extract(capsys, [*argv, "--blocks"])
    assert json.loads(printed)["extractions"][0]["blocks"]


def test_the_library_manifest_still_holds_the_blocks(tmp_path):
    m = ex.extract_source(make_docx(tmp_path / "n.docx"), tmp_path / "out")
    assert len(m["blocks"]) == 6 and "read_text" not in m


# --- (2) an electrolyte name or concentration that is a part of the statement agrees with it -----------


def _statement(bdir, statement, *, run_id="run-001", on_concentration=False):
    b = M.load(bdir)
    target = _miss(b, CONC, run_id)["value_id"] if on_concentration else next(
        c["candidate_id"] for c in b["candidates"] if c["run_id"] == run_id and c["target_field_path"] == NAME)
    M.annotate(bdir, target_id=target, value=statement, excerpt_locator="line 7", source_id=None,
               model_id="synthetic-model", blind=False, rationale="synthetic")


def _typed(grouped, tmp_path, capsys, name, conc, run_id="run-001"):
    xlsx = tmp_path / "t.xlsx"
    if not xlsx.exists():
        _export(grouped, tmp_path)
    r = _row_of(xlsx, run_id)
    cells = {("File List", f"{_col('Electrolyte')}{r}"): name, ("File List", f"{_col('Electrolyte Concentration (M)')}{r}"): conc}
    code, rep, err = _import(grouped, _fill(xlsx, tmp_path / "f.xlsx", cells), capsys)
    assert code == 0, err
    return [x for x in rep["replaces_or_contradicts_a_file_reading"] if x["run_id"] == run_id]


@pytest.mark.parametrize("statement,name,conc", [
    ("0.5 M H2SO4", "H2SO4", 0.5),
    ("H2SO4 0.5 M", "H2SO4", 0.5),
    ("100 mM KOH", "KOH", 0.1),
    ("the cell was filled with 0.5M H2SO4", None, 0.5),
])
@pytest.mark.parametrize("on_concentration", [False, True])
def test_a_name_and_a_concentration_that_split_the_statement_agree_with_it(grouped, tmp_path, capsys, statement, name, conc,
                                                                           on_concentration):
    _statement(grouped, statement, on_concentration=on_concentration)
    if name is None:  # a sentence around the statement is not a name: only the concentration part is compared
        assert [x["target_field_path"] for x in _typed(grouped, tmp_path, capsys, None, conc)] == []
        return
    assert _typed(grouped, tmp_path, capsys, name, conc) == []


@pytest.mark.parametrize("on_concentration", [False, True])
def test_a_different_name_or_concentration_is_still_flagged(grouped, tmp_path, capsys, on_concentration):
    _statement(grouped, "0.5 M H2SO4", on_concentration=on_concentration)
    flagged = _typed(grouped, tmp_path, capsys, "NaOH", 0.1)
    assert {x["target_field_path"] for x in flagged} == {NAME, CONC}
    assert all("0.5 M H2SO4" in x["readings"][0] for x in flagged)
    only_name = _typed(grouped, tmp_path, capsys, "NaOH", 0.5)
    assert {x["target_field_path"] for x in only_name} == {NAME}
    only_conc = _typed(grouped, tmp_path, capsys, "H2SO4", 0.1)
    assert {x["target_field_path"] for x in only_conc} == {CONC}


def test_a_statement_without_a_concentration_still_compares_the_name_whole(grouped, tmp_path, capsys):
    _statement(grouped, "H2SO4")
    assert _typed(grouped, tmp_path, capsys, "H2SO4", None) == []
    assert {x["target_field_path"] for x in _typed(grouped, tmp_path, capsys, "KOH", None)} == {NAME}


def test_a_statement_of_two_concentrations_is_not_split(grouped, tmp_path, capsys):
    _statement(grouped, "0.1 M KOH and 0.5 M NaCl")
    assert {x["target_field_path"] for x in _typed(grouped, tmp_path, capsys, "KOH", 0.1)} == {NAME}


def test_the_split_is_one_helper_and_never_reads_a_name_cell_with_a_concentration():
    assert T.electrolyte_statement_parts("0.5 M H2SO4") == ("H2SO4", 0.5)
    assert T.electrolyte_statement_parts("KOH 100 mM") == ("KOH", pytest.approx(0.1))
    assert T.electrolyte_statement_parts("H2SO4") is None
    assert T.electrolyte_statement_parts("0.1 M KOH and 0.5 M NaCl") is None
    assert T.electrolyte_statement_parts(0.5) is None
