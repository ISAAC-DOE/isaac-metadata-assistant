"""Polish c6-b: walkthrough findings on one real beamtime, reproduced on synthetic data. Synthetic only.

* (1) ``python -m isaac_api.local_import.extract`` on a Word/PowerPoint file prints a compact manifest (counts,
  ``text_file``, the images, how to read) - the blocks are in ``text.md`` and printed only on ``--blocks``.
"""

from __future__ import annotations

import json
from pathlib import Path

from isaac_api.local_import import extract as ex

from test_local_import_extract import make_docx, make_pptx


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
