"""The local extractor: turn the files ``isaac import`` could not read into things Claude can read.

SYNTHETIC FILES ONLY, built in ``tmp_path`` with the standard library and openpyxl. No
committed binary, no real beamtime content. Every document here carries invented text.

What these pin: reading order, embedded-image extraction with hashes and positions, the
zip-safety refusals (path traversal, oversize, duplicate names, a header that lies about
its size, entity declarations), the bound-and-count behaviour (nothing is cut without a
counter), formulas kept as formulas, and that an unknown binary is ``unreadable`` and not
described.
"""

from __future__ import annotations

import hashlib
import io
import json
import struct
import zipfile
import zlib
from dataclasses import replace
from pathlib import Path

import pytest

from isaac_api.local_import import extract as ex

# --- synthetic builders ---------------------------------------------------------------------


def _png(width: int = 3, height: int = 2, colour: int = 0) -> bytes:
    """A tiny valid PNG (RGB). ``colour`` varies the bytes so two images hash differently."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    raw = b"".join(
        b"\x00" + bytes((x * 37 + y * 11 + colour + k * 5) % 256 for x in range(width) for k in range(3))
        for y in range(height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _rels(items: dict[str, str], external: dict[str, str] | None = None) -> str:
    rows = "".join(
        f'<Relationship Id="{rid}" Type="http://x/{typ.split(":")[0]}" Target="{target}"/>'
        for rid, (typ, target) in ((k, tuple(v.split(":", 1))) for k, v in items.items())
    )
    for rid, target in (external or {}).items():
        rows += f'<Relationship Id="{rid}" Type="http://x/hyperlink" Target="{target}" TargetMode="External"/>'
    return f'<?xml version="1.0"?><Relationships xmlns="{REL}">{rows}</Relationships>'


def _drawing(rid: str, descr: str) -> str:
    return (
        f'<w:r><w:drawing><wp:inline><wp:docPr id="1" name="Picture 1" descr="{descr}"/>'
        f'<a:graphic><a:graphicData><a:blip r:embed="{rid}"/></a:graphicData></a:graphic>'
        f"</wp:inline></w:drawing></w:r>"
    )


def make_docx(path: Path, *, extra_members: dict[str, bytes] | None = None, body_xml: str | None = None) -> Path:
    body = body_xml or (
        "<w:p><w:r><w:t>Alpha paragraph</w:t></w:r></w:p>"
        f"<w:p>{_drawing('rId1', 'A synthetic figure')}</w:p>"
        '<w:p><w:pPr><w:pStyle w:val="Caption"/></w:pPr><w:r><w:t>Figure 1: synthetic caption</w:t></w:r></w:p>'
        "<w:tbl>"
        "<w:tr><w:tc><w:p><w:r><w:t>h1</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>h2</w:t></w:r></w:p></w:tc></w:tr>"
        "<w:tr><w:tc><w:p><w:r><w:t>a</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>b</w:t></w:r></w:p></w:tc></w:tr>"
        "</w:tbl>"
        f"<w:p>{_drawing('rId2', 'Second figure')}</w:p>"
        "<w:p><w:r><w:t>Omega paragraph</w:t></w:r></w:p>"
    )
    document = (
        f'<?xml version="1.0"?><w:document xmlns:w="{W}" xmlns:r="{R}" xmlns:a="{A}" xmlns:wp="{WP}">'
        f"<w:body>{body}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", document)
        zf.writestr(
            "word/_rels/document.xml.rels",
            _rels({"rId1": "image:media/image1.png", "rId2": "image:media/image2.png"}, {"rId9": "https://example.invalid/x"}),
        )
        zf.writestr("word/media/image1.png", _png(3, 2, 10))
        zf.writestr("word/media/image2.png", _png(12, 12, 200))
        for name, data in (extra_members or {}).items():
            zf.writestr(name, data)
    return path


def make_pptx(path: Path) -> Path:
    def slide(text: str, rid: str | None, descr: str = "") -> str:
        pic = (
            f'<p:pic><p:nvPicPr><p:cNvPr id="4" name="Pic" descr="{descr}"/></p:nvPicPr>'
            f'<p:blipFill><a:blip r:embed="{rid}"/></p:blipFill></p:pic>'
            if rid
            else ""
        )
        return (
            f'<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:cSld><p:spTree>'
            f'<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/></p:nvSpPr><p:txBody><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp>'
            f"{pic}</p:spTree></p:cSld></p:sld>"
        )

    presentation = (
        f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst>'
        '<p:sldId id="256" r:id="rId2"/><p:sldId id="257" r:id="rId1"/></p:sldIdLst></p:presentation>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ppt/presentation.xml", presentation)
        # The order in sldIdLst (rId2, then rId1) differs from the file numbering on purpose.
        zf.writestr("ppt/_rels/presentation.xml.rels", _rels({"rId1": "slide:slides/slide1.xml", "rId2": "slide:slides/slide2.xml"}))
        zf.writestr("ppt/slides/slide1.xml", slide("Second in order", "rId1", "Slide image alt"))
        zf.writestr("ppt/slides/slide2.xml", slide("First in order", None))
        zf.writestr("ppt/slides/_rels/slide1.xml.rels", _rels({"rId1": "image:../media/image1.png"}))
        zf.writestr("ppt/media/image1.png", _png(2, 2, 77))
    return path


def make_xlsx(path: Path, rows: int = 5, cols: int = 3) -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    for r in range(1, rows + 1):
        for c in range(1, cols + 1):
            ws.cell(row=r, column=c, value=f"r{r}c{c}")
    ws["A2"] = 5
    ws["B2"] = 7
    ws["C2"] = "=A2+B2"
    ws.merge_cells("A1:B1")
    wb.create_sheet("Second")["A1"] = "only"
    wb.save(path)
    return path


def make_pdf(path: Path, pages: int = 3) -> Path:
    kids = " ".join(f"{3 + i} 0 R" for i in range(pages))
    objs = [
        "1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj",
        f"2 0 obj<</Type/Pages/Kids[{kids}]/Count {pages}>>endobj",
    ]
    objs += [f"{3 + i} 0 obj<</Type/Page/Parent 2 0 R>>endobj" for i in range(pages)]
    objs.append(f"{3 + pages} 0 obj<</Title(Synthetic title)/Author(Nobody)/Producer(test)>>endobj")
    path.write_bytes(("%PDF-1.4\n" + "\n".join(objs) + "\ntrailer<</Root 1 0 R>>\n%%EOF\n").encode("latin-1"))
    return path


def run(path: Path, tmp_path: Path, **kw) -> dict:
    return ex.extract_source(path, tmp_path / "out", **kw)


# --- provenance on every output -------------------------------------------------------------


@pytest.mark.parametrize(
    "build",
    [make_docx, make_pptx, make_xlsx, make_pdf],
)
def test_every_manifest_carries_provenance_and_counters(tmp_path, build):
    ext = {make_docx: "docx", make_pptx: "pptx", make_xlsx: "xlsx", make_pdf: "pdf"}[build]
    src = build(tmp_path / f"sample.{ext}")
    m = run(src, tmp_path, source_relative_path=f"sub/sample.{ext}")
    assert m["source_relative_path"] == f"sub/sample.{ext}"
    assert m["source_sha256"] == hashlib.sha256(src.read_bytes()).hexdigest()
    assert m["extractor"] == ex.EXTRACTOR_ID and m["extractor_version"] == ex.EXTRACTOR_VERSION
    assert isinstance(m["truncation"], dict) and isinstance(m["refusals"], list)
    assert m["limits"]["max_zip_members"] == ex.DEFAULT_LIMITS.max_zip_members
    assert str(tmp_path) not in json.dumps(m), "an absolute path leaked into the manifest"


def test_the_label_defaults_to_the_file_name_and_may_not_escape(tmp_path):
    src = make_pdf(tmp_path / "a.pdf")
    assert run(src, tmp_path)["source_relative_path"] == "a.pdf"
    for bad in ("/abs/a.pdf", "../a.pdf", "x/../../a.pdf", "a\\b.pdf"):
        with pytest.raises(ValueError):
            run(src, tmp_path, source_relative_path=bad)


# --- docx -----------------------------------------------------------------------------------


def test_docx_text_in_reading_order_with_tables_and_images_placed(tmp_path):
    m = run(make_docx(tmp_path / "d.docx"), tmp_path)
    assert m["status"] == "extracted" and m["read_with"] == "extractor"
    kinds = [b["type"] for b in m["blocks"]]
    assert kinds == ["paragraph", "paragraph", "paragraph", "table", "paragraph", "paragraph"]
    texts = [b.get("text") for b in m["blocks"] if b["type"] == "paragraph"]
    assert texts == ["Alpha paragraph", "", "Figure 1: synthetic caption", "", "Omega paragraph"]
    table = next(b for b in m["blocks"] if b["type"] == "table")
    assert table["rows"] == [["h1", "h2"], ["a", "b"]]
    # reading order: the first image is attached to the paragraph before the table, the second after.
    first, second = m["images"]
    assert first["locations"][0]["paragraph_index"] == 1 and second["locations"][0]["paragraph_index"] == 3
    assert first["locations"][0]["alt_text"]["descr"] == "A synthetic figure"
    assert first["locations"][0]["caption"] == "Figure 1: synthetic caption"
    assert "caption" not in second["locations"][0]
    md = (tmp_path / "out" / m["text_file"]).read_text(encoding="utf-8")
    assert md.index("Alpha paragraph") < md.index("[image img-001]") < md.index("[table 0]") < md.index("Omega paragraph")


def test_docx_images_are_written_with_hashes_dimensions_and_generated_names(tmp_path):
    m = run(make_docx(tmp_path / "d.docx"), tmp_path)
    assert [i["image_id"] for i in m["images"]] == ["img-001", "img-002"]
    for image, colour, (w, h) in zip(m["images"], (10, 200), ((3, 2), (12, 12))):
        data = _png(w, h, colour)
        assert image["sha256"] == hashlib.sha256(data).hexdigest()
        assert (image["width_px"], image["height_px"], image["format"]) == (w, h, "png")
        assert image["read_with"] == "claude_read_tool"
        written = tmp_path / "out" / image["file"]
        assert written.read_bytes() == data
        assert written.name == f"{image['image_id'][4:]}_{image['sha256'][:8]}.png"
    assert m["counts"]["images"] == 2


def test_an_image_used_twice_is_written_once_and_placed_twice(tmp_path):
    body = (
        f"<w:p>{_drawing('rId1', 'first use')}</w:p><w:p>{_drawing('rId1', 'second use')}</w:p>"
    )
    m = run(make_docx(tmp_path / "d.docx", body_xml=body), tmp_path)
    shared = next(i for i in m["images"] if i["archive_member"] == "word/media/image1.png")
    assert len(shared["locations"]) == 2
    unreferenced = next(i for i in m["images"] if i["archive_member"] == "word/media/image2.png")
    assert unreferenced["locations"] == []  # present in word/media, referenced by nothing in the body


def test_external_relationships_are_counted_and_never_followed(tmp_path):
    m = run(make_docx(tmp_path / "d.docx"), tmp_path)
    assert m["truncation"]["external_relationships_not_followed"] == 1
    assert "example.invalid" not in json.dumps(m)


def test_docx_zip_slip_member_is_refused_and_nothing_escapes(tmp_path):
    src = make_docx(tmp_path / "d.docx", extra_members={"word/media/../../../escaped.png": _png()})
    out = tmp_path / "out"
    m = ex.extract_source(src, out)
    assert m["status"] == "extracted"
    assert any(r["code"] == "unsafe_member_name" for r in m["refusals"])
    assert "escaped" not in json.dumps(m)  # the member's name is withheld
    assert not list(tmp_path.rglob("escaped*")), "a traversal member was written somewhere"
    for written in out.rglob("*"):
        assert out in written.parents


@pytest.mark.parametrize("name", ["/abs/evil.png", "word\\evil.png"])
def test_absolute_and_backslash_member_names_are_refused(tmp_path, name):
    m = run(make_docx(tmp_path / "d.docx", extra_members={name: _png()}), tmp_path)
    assert any(r["code"] == "unsafe_member_name" for r in m["refusals"])


def test_a_duplicate_member_name_is_refused(tmp_path):
    src = tmp_path / "d.docx"
    make_docx(src)
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # zipfile warns about the duplicate on purpose
        with zipfile.ZipFile(src, "a") as zf:
            zf.writestr("word/media/image1.png", _png(9, 9, 1))
    m = run(src, tmp_path)
    assert any(r["code"] == "duplicate_member_name" for r in m["refusals"])
    first = next(i for i in m["images"] if i["archive_member"] == "word/media/image1.png")
    assert first["sha256"] == hashlib.sha256(_png(3, 2, 10)).hexdigest()  # the first one won


def test_oversize_image_member_is_refused_not_truncated(tmp_path):
    src = make_docx(tmp_path / "d.docx")
    limits = replace(ex.DEFAULT_LIMITS, max_image_bytes=len(_png(3, 2, 10)) + 1)  # image2 (12x12) is larger
    m = ex.extract_source(src, tmp_path / "out", limits=limits)
    members = {i["archive_member"] for i in m["images"]}
    assert members == {"word/media/image1.png"}
    assert any(r["code"] == "member_too_large" for r in m["refusals"])


def test_a_member_whose_header_lies_about_its_size_is_refused(tmp_path):
    src = tmp_path / "d.docx"
    make_docx(src)
    data = bytearray(src.read_bytes())
    # Rewrite image1's uncompressed size in its central directory entry to something tiny.
    marker = b"word/media/image1.png"
    central = data.rindex(marker) - 46
    assert data[central : central + 4] == b"PK\x01\x02"
    struct.pack_into("<I", data, central + 24, 4)
    src.write_bytes(bytes(data))
    limits = replace(ex.DEFAULT_LIMITS, max_image_bytes=40)  # image1 inflates past this, its header says 4
    m = ex.extract_source(src, tmp_path / "out", limits=limits)
    assert any(r["code"] in ("member_inflated_past_bound", "member_unreadable") for r in m["refusals"])
    assert all(i["archive_member"] != "word/media/image1.png" for i in m["images"])


def test_too_many_members_are_counted(tmp_path):
    extra = {f"word/other{i}.txt": b"x" for i in range(10)}
    m = ex.extract_source(
        make_docx(tmp_path / "d.docx", extra_members=extra),
        tmp_path / "out",
        limits=replace(ex.DEFAULT_LIMITS, max_zip_members=8),
    )
    assert m["truncation"]["zip_members_not_admitted"] > 0
    assert any(r["code"] == "too_many_members" for r in m["refusals"])


def test_an_oversize_document_is_refused_before_it_is_opened(tmp_path):
    src = make_docx(tmp_path / "d.docx")
    m = ex.extract_source(src, tmp_path / "out", limits=replace(ex.DEFAULT_LIMITS, max_source_bytes=100))
    assert m["status"] == "refused" and m["source_sha256"]
    assert not (tmp_path / "out").exists()


def test_entity_declarations_are_not_parsed(tmp_path):
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaa">]>'
        f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>&a;</w:t></w:r></w:p></w:body></w:document>'
    )
    src = tmp_path / "d.docx"
    with zipfile.ZipFile(src, "w") as zf:
        zf.writestr("word/document.xml", bomb)
    m = ex.extract_source(src, tmp_path / "out")
    assert any(r["code"] == "xml_declares_entities" for r in m["refusals"])
    assert m["status"] in ("refused", "unreadable") and not m.get("blocks")


def test_text_bounds_are_counted_never_silent(tmp_path):
    body = "".join(f"<w:p><w:r><w:t>{'x' * 50}</w:t></w:r></w:p>" for _ in range(30))
    limits = replace(ex.DEFAULT_LIMITS, max_blocks=10, max_paragraph_chars=20)
    m = ex.extract_source(make_docx(tmp_path / "d.docx", body_xml=body), tmp_path / "out", limits=limits)
    assert len(m["blocks"]) == 10
    assert m["truncation"]["blocks_not_returned"] == 20
    assert m["truncation"]["paragraph_chars_not_returned"] == 10 * 30
    assert all(len(b["text"]) == 20 for b in m["blocks"])
    assert m["counts"]["paragraphs"] == 30


def test_total_text_bound_is_counted(tmp_path):
    body = "".join(f"<w:p><w:r><w:t>{'y' * 100}</w:t></w:r></w:p>" for _ in range(10))
    m = ex.extract_source(
        make_docx(tmp_path / "d.docx", body_xml=body),
        tmp_path / "out",
        limits=replace(ex.DEFAULT_LIMITS, max_text_chars=250),
    )
    assert sum(len(b["text"]) for b in m["blocks"]) == 250
    assert m["truncation"]["text_chars_past_document_bound"] == 750


def test_table_bounds_are_counted(tmp_path):
    rows = "".join("<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>" for c in range(6)) + "</w:tr>" for _ in range(7))
    m = ex.extract_source(
        make_docx(tmp_path / "d.docx", body_xml=f"<w:tbl>{rows}</w:tbl>"),
        tmp_path / "out",
        limits=replace(ex.DEFAULT_LIMITS, max_table_rows=3, max_table_cols=4),
    )
    table = m["blocks"][0]
    assert len(table["rows"]) == 3 and all(len(r) == 4 for r in table["rows"])
    assert m["truncation"]["table_rows_not_returned"] == 4
    assert m["truncation"]["table_cols_not_returned"] == 3 * 2


def test_an_image_budget_is_counted(tmp_path):
    m = ex.extract_source(
        make_docx(tmp_path / "d.docx"), tmp_path / "out", limits=replace(ex.DEFAULT_LIMITS, max_images=1)
    )
    assert len(m["images"]) == 1 and m["truncation"]["images_not_written"] == 1


def test_a_corrupt_zip_is_unreadable_not_a_crash(tmp_path):
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"this is not a zip file")
    m = run(bad, tmp_path)
    assert m["status"] == "unreadable" and "zip" in m["reason"]
    assert m["source_sha256"]


# --- pptx -----------------------------------------------------------------------------------


def test_pptx_slides_follow_the_presentation_order_with_images_and_alt_text(tmp_path):
    m = run(make_pptx(tmp_path / "p.pptx"), tmp_path)
    assert m["status"] == "extracted"
    assert [s["slide"] for s in m["slides"]] == [1, 2]
    assert m["slides"][0]["shapes"][0]["text"] == "First in order"
    second = m["slides"][1]
    assert second["shapes"][0]["text"] == "Second in order"
    assert second["shapes"][1] == {"type": "image", "image_id": "img-001"}
    image = m["images"][0]
    assert image["locations"][0]["slide"] == 2
    assert image["locations"][0]["alt_text"]["descr"] == "Slide image alt"
    assert image["sha256"] == hashlib.sha256(_png(2, 2, 77)).hexdigest()
    assert (tmp_path / "out" / image["file"]).read_bytes() == _png(2, 2, 77)
    md = (tmp_path / "out" / m["text_file"]).read_text(encoding="utf-8")
    assert md.index("## Slide 1") < md.index("First in order") < md.index("## Slide 2") < md.index("[image img-001]")


# --- xlsx -----------------------------------------------------------------------------------


def test_xlsx_sheets_formulas_and_merged_cells(tmp_path):
    m = run(make_xlsx(tmp_path / "x.xlsx"), tmp_path)
    assert m["status"] == "extracted"
    assert [s["name"] for s in m["sheets"]] == ["Data", "Second"]
    data = m["sheets"][0]
    assert data["dimensions"] == "A1:C5"
    by_row = {r["row"]: r["cells"] for r in data["preview_rows"]}
    assert by_row[2] == [5, 7, "=A2+B2"], "a formula must be shown as a formula, not its result"
    assert data["merged_ranges"] == {"scanned": True, "total": 1, "ranges": ["A1:B1"]}
    assert [r["row"] for r in data["header_rows"]] == [1, 2, 3]
    assert m["sheets"][1]["preview_rows"][0]["cells"] == ["only"]


def test_xlsx_preview_is_bounded_and_counted(tmp_path):
    src = make_xlsx(tmp_path / "x.xlsx", rows=12, cols=8)
    limits = replace(ex.DEFAULT_LIMITS, max_preview_rows=4, max_preview_cols=5)
    m = ex.extract_source(src, tmp_path / "out", limits=limits)
    sheet = m["sheets"][0]
    assert len(sheet["preview_rows"]) == 4
    assert all(len(r["cells"]) <= 5 for r in sheet["preview_rows"])
    assert sheet["preview_bounds"] == {"rows": 4, "columns": 5, "cell_chars": limits.max_preview_cell_chars}
    assert sheet["preview_columns_not_returned"] == 4 * 3
    assert m["truncation"]["preview_columns_not_returned"] == 4 * 3
    assert any("first 4 rows" in n for n in m["notes"])  # the bound is stated, not implied


def test_xlsx_long_cells_and_sheet_count_are_counted(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    wb.active["A1"] = "z" * 100
    for i in range(4):
        wb.create_sheet(f"S{i}")
    path = tmp_path / "x.xlsx"
    wb.save(path)
    m = ex.extract_source(
        path, tmp_path / "out", limits=replace(ex.DEFAULT_LIMITS, max_sheets=2, max_preview_cell_chars=10)
    )
    assert len(m["sheets"]) == 2 and m["truncation"]["sheets_not_read"] == 3
    assert m["sheets"][0]["preview_rows"][0]["cells"] == ["z" * 10]
    assert m["truncation"]["preview_cell_chars_not_returned"] == 90


def test_xlsx_hidden_sheets_are_marked(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    wb.active["A1"] = 1
    wb.create_sheet("Quiet").sheet_state = "hidden"
    path = tmp_path / "x.xlsx"
    wb.save(path)
    states = {s["name"]: s["state"] for s in run(path, tmp_path)["sheets"]}
    assert states["Quiet"] == "hidden"


# --- pdf ------------------------------------------------------------------------------------


def test_pdf_reports_pages_and_metadata_and_is_read_by_claude(tmp_path):
    m = run(make_pdf(tmp_path / "p.pdf", pages=45), tmp_path)
    assert m["status"] == "read_with_claude" and m["read_with"] == "claude_read_tool"
    assert m["pdf"]["page_count"] == 45
    assert m["pdf"]["metadata"]["Title"] == "Synthetic title"
    assert m["pdf"]["text_extracted"] is False
    assert m["page_ranges"] == ["1-20", "21-40", "41-45"]


def test_pdf_page_ranges_are_capped_and_counted(tmp_path):
    limits = replace(ex.DEFAULT_LIMITS, pdf_max_page_ranges=2)
    m = ex.extract_source(make_pdf(tmp_path / "p.pdf", pages=100), tmp_path / "out", limits=limits)
    assert m["page_ranges"] == ["1-20", "21-40"] and m["truncation"]["page_ranges_not_listed"] == 3


def test_pdf_page_count_inside_a_compressed_object_stream(tmp_path):
    inner = b"1 0 2 20 <</Type/Catalog/Pages 2 0 R>> <</Type/Pages/Count 7/Kids[]>>"
    stream = zlib.compress(inner)
    pdf = (
        b"%PDF-1.5\n5 0 obj<</Type/ObjStm/N 2/First 8/Filter/FlateDecode/Length "
        + str(len(stream)).encode()
        + b">>\nstream\n"
        + stream
        + b"\nendstream\nendobj\n%%EOF\n"
    )
    path = tmp_path / "c.pdf"
    path.write_bytes(pdf)
    m = run(path, tmp_path)
    assert m["pdf"]["page_count"] == 7 and m["pdf"]["page_count_basis"] == "page tree /Count"


def test_a_pdf_with_no_determinable_page_count_says_null_not_zero(tmp_path):
    path = tmp_path / "e.pdf"
    path.write_bytes(b"%PDF-1.7\n%%EOF\n")
    m = run(path, tmp_path)
    assert m["pdf"]["page_count"] is None and m["page_ranges"] == []
    assert any("null, not zero" in n for n in m["notes"])


def test_a_file_named_pdf_without_the_header_is_unreadable(tmp_path):
    path = tmp_path / "n.pdf"
    path.write_bytes(b"not a pdf at all")
    m = run(path, tmp_path)
    assert m["status"] == "unreadable"


# --- images ---------------------------------------------------------------------------------


def test_image_files_report_dimensions_and_are_read_by_claude(tmp_path):
    png = tmp_path / "a.png"
    png.write_bytes(_png(7, 9))
    m = run(png, tmp_path)
    assert m["status"] == "read_with_claude" and m["read_with"] == "claude_read_tool"
    assert m["image"] == {"format": "png", "width_px": 7, "height_px": 9}
    jpg = tmp_path / "b.jpg"
    jpg.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\xff\xc0\x00\x0b\x08\x00\x20\x00\x30\x01\x01\x11\x00" + b"\xff\xd9")
    assert run(jpg, tmp_path)["image"] == {"format": "jpeg", "width_px": 48, "height_px": 32}
    heic = tmp_path / "c.heic"
    heic.write_bytes(b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00" + b"\x00" * 16)
    m = run(heic, tmp_path)
    assert m["read_with"] == "claude_read_tool" and m["image"]["width_px"] is None
    assert any("convert" in n for n in m["notes"])


# --- unknown binary -------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["data.pxp", "scan.bin", "noext", "old.doc"])
def test_unknown_binary_is_unreadable_with_a_reason_and_size_and_is_never_guessed(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(bytes(range(40)))
    m = run(path, tmp_path)
    assert m["status"] == "unreadable" and m["read_with"] is None
    assert m["reason"] and m["source_size_bytes"] == 40
    assert m["source_sha256"] == hashlib.sha256(bytes(range(40))).hexdigest()
    for key in ("blocks", "sheets", "images", "text_file", "pdf", "image"):
        assert key not in m, f"an unreadable file must not carry {key}"
    assert m["leading_bytes_hex"] == bytes(range(8)).hex()


# --- plain text of any extension, and archives -----------------------------------------------


def test_a_plain_text_file_of_any_extension_is_read_with_claude_with_a_bounded_preview(tmp_path):
    lines = [f"synthetic line {i} " + "q" * 10 for i in range(100)]
    path = tmp_path / "scan.001"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    m = ex.extract_source(path, tmp_path / "out", limits=replace(ex.DEFAULT_LIMITS, max_text_preview_lines=5, max_text_preview_line_chars=12))
    assert m["status"] == "read_with_claude" and m["read_with"] == "claude_read_tool" and m["kind"] == "text"
    assert m["text"]["line_count"] == 100
    assert m["text"]["preview_lines"] == [ln[:12] for ln in lines[:5]]
    assert m["truncation"]["preview_lines_not_returned"] == 95
    assert m["truncation"]["preview_line_chars_not_returned"] == 5 * (len(lines[0]) - 12)
    assert "reason" not in m


def test_text_is_decided_by_mechanical_tests_only(tmp_path):
    with_nul = tmp_path / "a.txt"
    with_nul.write_bytes(b"looks like text\x00but is not")
    assert run(with_nul, tmp_path)["status"] == "unreadable"
    not_utf8 = tmp_path / "b.txt"
    not_utf8.write_bytes(b"caf\xe9 " * 50)
    assert run(not_utf8, tmp_path)["status"] == "unreadable"
    empty = tmp_path / "c.txt"
    empty.write_bytes(b"")
    assert run(empty, tmp_path)["status"] == "unreadable"
    multibyte_cut = tmp_path / "d.txt"
    multibyte_cut.write_bytes(("é" * 5000).encode("utf-8"))  # cut mid-character by the 8 KiB sample
    assert run(multibyte_cut, tmp_path)["status"] == "read_with_claude"


def test_a_long_text_file_stops_counting_at_the_byte_bound_and_says_so(tmp_path):
    path = tmp_path / "long.txt"
    path.write_text("abcdefghij\n" * 1000, encoding="utf-8")
    m = ex.extract_source(path, tmp_path / "out", limits=replace(ex.DEFAULT_LIMITS, max_text_count_bytes=500))
    assert m["text"]["line_count"] is None and "more lines" in m["text"]["line_count_note"]


def test_a_zip_archive_is_listed_never_extracted(tmp_path):
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("a/one.txt", "x")
        zf.writestr("a/two.txt", "y")
        zf.writestr("three.dat", "z")
        zf.writestr("../escape.txt", "w")
    m = run(archive, tmp_path)
    assert m["status"] == "unreadable" and "listed" in m["reason"]
    listing = m["archive_listing"]
    assert listing["extensions"] == {".txt": 2, ".dat": 1}
    assert listing["names_withheld_unsafe"] == 1 and "escape" not in json.dumps(m)
    assert sorted(listing["names"]) == ["a/one.txt", "a/two.txt", "three.dat"]
    assert not (tmp_path / "out").exists(), "an archive must not be extracted"
    capped = ex.extract_source(archive, tmp_path / "out", limits=replace(ex.DEFAULT_LIMITS, max_archive_listing_names=1))
    assert len(capped["archive_listing"]["names"]) == 1 and capped["truncation"]["archive_names_not_listed"] == 2


def test_xlsx_rows_past_the_preview_are_counted_from_the_sheet_dimensions(tmp_path):
    m = ex.extract_source(
        make_xlsx(tmp_path / "x.xlsx", rows=12, cols=3), tmp_path / "out", limits=replace(ex.DEFAULT_LIMITS, max_preview_rows=5)
    )
    sheet = m["sheets"][0]
    assert sheet["rows_in_sheet"] == 12 and sheet["preview_rows_not_returned"] == 7
    assert m["truncation"]["preview_rows_not_returned"] == 7


def test_a_symlink_source_is_refused(tmp_path):
    target = make_pdf(tmp_path / "t.pdf")
    link = tmp_path / "l.pdf"
    link.symlink_to(target)
    with pytest.raises(ValueError):
        run(link, tmp_path)


# --- the unread_files batch and the CLI -----------------------------------------------------


def test_extract_unread_resolves_inside_the_root_and_reports_every_entry(tmp_path):
    root = tmp_path / "root"
    (root / "d").mkdir(parents=True)
    make_docx(root / "d" / "n.docx")
    (root / "z.bin").write_bytes(b"\x00\x01")
    entries = [
        {"relative_path": "d/n.docx", "reason_code": "no_reader_for_source_type"},
        {"relative_path": "z.bin", "reason_code": "no_reader_for_source_type"},
        {"relative_path": None, "reason_code": "unsafe_member_name"},
        {"relative_path": "../outside.docx", "reason_code": "x"},
        {"relative_path": "gone.pdf", "reason_code": "x"},
    ]
    result = ex.extract_unread(entries, root, tmp_path / "out")
    statuses = [r["status"] for r in result["extractions"]]
    assert statuses == ["extracted", "unreadable", "refused", "refused", "unreadable"]
    assert result["extractions"][0]["source_relative_path"] == "d/n.docx"
    assert result["extractions"][0]["bundle_reason_code"] == "no_reader_for_source_type"
    assert result["by_status"] == {"extracted": 1, "unreadable": 2, "refused": 2}
    cut = ex.extract_unread(entries, root, tmp_path / "out2", limit=2)
    assert len(cut["extractions"]) == 2 and cut["truncation"]["entries_not_processed"] == 3 and cut["total_entries"] == 5


def test_extract_unread_does_not_follow_a_symlinked_directory(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    outside.mkdir()
    make_pdf(outside / "secret.pdf")
    root.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    result = ex.extract_unread([{"relative_path": "link/secret.pdf", "reason_code": "x"}], root, tmp_path / "out")
    assert result["extractions"][0]["status"] == "unreadable"


def test_cli_prints_a_json_manifest(tmp_path, capsys):
    src = make_docx(tmp_path / "root" / "n.docx") if (tmp_path / "root").mkdir() is None else None
    rc = ex.main([str(src), "--out", str(tmp_path / "out"), "--root", str(tmp_path / "root")])
    assert rc == 0
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["source_relative_path"] == "n.docx" and manifest["status"] == "extracted"


def test_cli_from_bundle_and_usage_errors(tmp_path, capsys):
    root = tmp_path / "root"
    root.mkdir()
    make_pdf(root / "a.pdf")
    unread = tmp_path / "unread_files.json"
    unread.write_text(json.dumps({"unread_files": [{"relative_path": "a.pdf", "reason_code": "no_reader_for_source_type"}]}))
    assert ex.main(["--from-bundle", str(unread), "--root", str(root), "--out", str(tmp_path / "out")]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["extractions"][0]["status"] == "read_with_claude"
    assert ex.main(["--from-bundle", str(unread), "--out", str(tmp_path / "out")]) == 2
    assert ex.main(["--out", str(tmp_path / "out")]) == 2
    outside = make_pdf(tmp_path / "o.pdf")
    assert ex.main([str(outside), "--out", str(tmp_path / "out"), "--root", str(root)]) == 3


def test_the_module_imports_no_network_or_web_framework():
    source = Path(ex.__file__).read_text(encoding="utf-8")
    for needle in ("import requests", "import httpx", "urllib", "socket", "import fastapi", "isaac_api.routes", "subprocess", "os.system"):
        assert needle not in source, needle


# --- a defect `isaac import` has on real data, reproduced synthetically ---------------------


def test_two_acquisitions_with_the_same_file_name_in_different_folders_import(tmp_path):
    from isaac_api import historical_import as hist
    from isaac_api.local_import import cli

    root = hist.archive_root_for("bl15_synthetic_semantics_corpus")
    template = (root / "05_02_ZZ2_base_after400Cycling_filter20_800mV").read_text(encoding="utf-8")
    corpus = tmp_path / "corpus"
    for i, folder in enumerate(("first", "second")):
        (corpus / folder).mkdir(parents=True)
        body = template.replace("#F 05_02_ZZ2_base_after400Cycling_filter20_800mV", "#F same_name") + f"\n# synthetic note {i}\n"
        (corpus / folder / "same_name.dat").write_text(body, encoding="utf-8")
    assert cli.main(["import", str(corpus), "--out", str(tmp_path / "bundle")]) == 0
    bundle = json.loads((tmp_path / "bundle" / "bundle.json").read_text(encoding="utf-8"))
    assert len(bundle["runs"]) == 2
    # BOTH RUNS KEPT, KEYED APART, AND THE PAIR FLAGGED FOR REVIEW (R1).
    a, b = bundle["runs"]
    assert a["stem"] == b["stem"]  # the engine's label for both
    assert a["run_key"] != b["run_key"]
    assert a["shares_file_name_with"] == [b["run_id"]] and b["shares_file_name_with"] == [a["run_id"]]
    assert set(a["candidate_ids"]).isdisjoint(b["candidate_ids"])
    pair = [c for c in bundle["conflicts"] if c["kind"] == "same_file_name_different_folders"]
    assert len(pair) == 1 and sorted(pair[0]["run_ids"]) == sorted([a["run_id"], b["run_id"]])
    assert {r["value"] for r in pair[0]["readings"]} == {"first/same_name.dat", "second/same_name.dat"}
