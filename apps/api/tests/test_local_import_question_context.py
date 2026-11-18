"""Beamtime CONTEXT beside a question (``question_context``): what the files, the readings and the processing hold for
it, so the scientist has what they need to answer. Evidence, never a value. SYNTHETIC bundles only (the committed
multi-operator corpus and invented SSRL XDC scans dated 2099); every added reading, plot and image is invented here.

Pinned, each by behaviour:

* The relevance rules: which question gets which kinds (environment: logbook quotes, step-table rows, the potentials,
  the group plot; sample: quotes and document images; clock: ``#D`` beside ``#E`` with the offset; curve: the plot,
  scan proposals, the quick-merge comparison, the curve's edge; naming: file names; technique; a group's runs side by
  side), every item bounded and saying its source; anything else carries none.
* Additive: question ids, blocking, counts, text and the minimum are identical with and without context
  (``--no-context``); the context sets and chooses nothing.
* The clock values show the offset the two header lines imply, and never a time zone.
* Every file value a context states is recorded as an exposure, under its own command, before it is printed.
* ``bundle questions`` prints a compact context, ``bundle show question`` the full one, with the file to open.
* The local-only image endpoint serves a plot from the bundle and an extracted image from its notes folder, and
  refuses ``..``, absolute paths, backslashes, symlinks (in the path, and the notes folder itself), other types, a
  missing file, and any request without the local header.
* The skill docs say how Claude presents the context.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import shutil
import struct
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from isaac_api import local_bundles as LB
from isaac_api.app import create_app
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import question_context as QC
from isaac_api.local_import import questions as Q

from tests_support_records import REPO_ROOT, pristine_bundle  # noqa: F401
from test_local_import_xdc_start_time import _import as xdc_import, stamp

SKILL = REPO_ROOT / ".claude/skills/isaac-historical-import"
LOCAL = dict(base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50123), headers={LB.LOCAL_HEADER: "1"})
QUOTE = "SYNTHETIC fill the cell with 0.1 M ZZOH before every hold"
#: An IANA zone name (Area/Location) or a zone abbreviation: never in a context
ZONE_LIKE = re.compile(r"\b(?:Africa|America|Antarctica|Asia|Atlantic|Australia|Europe|Indian|Pacific|Etc)/\w+|"
                       r"\b(?:PST|PDT|EST|EDT|CET|CEST|GMT|BST|JST)\b")


@pytest.fixture(scope="module", autouse=True)
def _vendored_schema_basis(tmp_path_factory):
    d = tmp_path_factory.mktemp("no-validator")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(d))
        mp.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(d / "python"))
        yield


def png_bytes() -> bytes:
    """A valid 1x1 PNG (invented)."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b""))


def _notes_source(b) -> dict:
    return next(s for s in b["sources"] if (s.get("classification") or {}).get("source_type") == "beamtime_notes")


def _group_of(b, rid: str) -> str:
    return next(g["group_id"] for g in b["record_groups"] if rid in g["member_run_ids"])


def _augment(bdir: Path) -> dict:
    """The corpus plus an AI reading of the logbook, a processing result with a plot, scan proposals and a quick merge
    for run-001's group, and an extracted document image in the notes folder: all invented. Saved schema-valid."""
    b = M.load(bdir)
    notes = _notes_source(b)
    gid = _group_of(b, "run-001")
    b.setdefault("ai_interpretations", []).append({
        "interpretation_id": "ai-syn-0001", "target": {"kind": "record_group", "id": gid},
        "proposed_value": "ZZOH", "rationale": "SYNTHETIC: the logbook names the electrolyte.",
        "source_refs": [{"source_id": notes["source_id"], "locator": "line 7"}], "method": "ai_interpretation",
        "model": {"model_id": "synthetic"}, "created_utc": "2099-01-01T00:00:00Z", "max_state": "needs_review",
        "excerpt_locator": "line 7", "source_path": notes["relative_path"], "quote": QUOTE, "strength": "stated",
        "field_path": "context.electrochemistry.electrolyte.name"})
    plot = f"processing/{gid}/r-syn/plot.png"
    (bdir / plot).parent.mkdir(parents=True, exist_ok=True)
    (bdir / plot).write_bytes(png_bytes())
    b.setdefault("processing_results", []).append({
        "result_id": "proc-syn-isaac", "group_id": gid, "group_kind": "record_group", "protocol_id": "isaac.xas.v0",
        "protocol_version": "0.1.0", "protocol_status": "draft_unreviewed", "source": "isaac_protocol",
        "inputs": [], "steps": [], "comparison": None, "state": B.STATE_NEEDS_REVIEW,
        "outputs": {"files": [{"role": "plot", "relative_path": plot,
                               "sha256": hashlib.sha256(png_bytes()).hexdigest()}], "e0_eV": 9001.5},
        "qc": {"verdict": "warn", "reasons": [], "statements": {}},
        "scan_selection": {"scans": [
            {"file": "SYN_scan_001.dat", "proposal": "exclude_proposed", "said": ["SYNTHETIC stops early"]},
            {"file": "SYN_scan_002.dat", "proposal": "include"}]},
        "scientist_quick_merges": [{"relative_path": "MERGE/SYN_merge.nor", "verdict": "agrees",
                                    "statement": "SYNTHETIC quick merge agrees with ISAAC's curve"}]})
    assert B.validate_bundle(b) == [], B.validate_bundle(b)[:3]
    M.save_bundle(bdir, b)
    ex = QC.notes_dir_of(bdir) / "extracted" / str(notes["content_sha256"])[:12]
    ex.mkdir(parents=True)
    (ex / "text.md").write_text("Intro\n\nThe ZZ1 electrode before the first hold:\n\n[image img-001]\n\n"
                                "How to start a scan\n\n[image img-002]\n", encoding="utf-8")
    (ex / "001_0a1b2c3d.png").write_bytes(png_bytes())
    (ex / "002_0a1b2c3e.png").write_bytes(png_bytes())  # a picture of a scan script: not about the sample
    return b


@pytest.fixture(scope="module")
def built(pristine_bundle, tmp_path_factory):
    out = tmp_path_factory.mktemp("ctx") / "bundles" / "syn"
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(pristine_bundle, out)
    M.group(out)
    _augment(out)
    return out


@pytest.fixture()
def bdir(built, tmp_path):
    root = tmp_path / "bundles"
    root.mkdir()
    shutil.copytree(built, root / "syn")
    shutil.copytree(QC.notes_dir_of(built), root / "syn-notes")
    return root / "syn"


def _cli(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main([str(a) for a in argv])
    text = buf.getvalue()
    return code, (json.loads(text) if text.strip().startswith("{") else text)


def _q(payload, pred):
    return next(q for q in payload["questions"] if pred(q))


def _full(bdir: Path):
    """Every question, full, with its context (in memory: nothing recorded)."""
    b = M.load(bdir)
    payload = Q.consolidate(b)
    qs, shown = QC.annotate(payload["questions"], b, bdir)
    return b, {**payload, "questions": qs}, shown


# --- the relevance rules ---------------------------------------------------------------------------------------

@pytest.mark.parametrize(("q", "theme"), [
    ({"kind": "missing_value", "target_field_path": "context.environment"}, "environment"),
    ({"kind": "confirm_value", "target_field_path": "context.electrochemistry.potential_setpoint_V"}, "environment"),
    ({"kind": "missing_value", "target_field_path": "context.electrochemistry.potential_scale"}, "environment"),
    ({"kind": "missing_value", "target_field_path": "context.electrochemistry.control_mode"}, "environment"),
    ({"kind": "missing_value", "target_field_path": "context.electrochemistry.pH"}, "environment"),
    ({"kind": "missing_value", "target_field_path": "context.thermodynamics.atmosphere"}, "environment"),
    ({"kind": "optional_values", "fields": {"context.electrochemistry.cell_type": [], "system.facility.site": []}}, "environment"),
    ({"kind": "missing_value", "target_field_path": "sample.sample_form"}, "sample"),
    ({"kind": "confirm_value", "target_field_path": "sample.material.formula"}, "sample"),
    ({"kind": "missing_value", "target_field_path": "sample.material.provenance"}, "sample"),
    ({"kind": "clock_time_zone", "target_field_path": "timestamps.acquired_start_utc"}, "clock"),
    ({"kind": "stated_utc_start_times", "target_field_path": "timestamps.acquired_start_utc"}, "clock"),
    ({"kind": "resolve_conflict", "target_field_path": "timestamps.acquired_start_utc"}, "clock"),
    ({"kind": "confirm_absorber", "target_field_path": None}, "curve"),
    ({"kind": "missing_value", "target_field_path": "measurement.qc.status"}, "curve"),
    ({"kind": "naming_counter_positions", "target_field_path": None}, "naming"),
    ({"kind": "condition_label", "target_field_path": "sample.sample_id"}, "naming"),
    ({"kind": "confirm_value", "target_field_path": "system.technique"}, "technique"),
    ({"kind": "missing_value", "target_field_path": "attribution.produced_by.group"}, None),
    ({"kind": "optional_values", "fields": {"system.facility.site": []}}, None),
])
def test_each_question_kind_and_field_follows_its_documented_rule(q, theme):
    assert QC.theme_of(q) == theme
    if theme:
        assert set(QC.RULES[theme]) <= set(QC.KINDS)


def test_context_attaches_per_the_rules_and_every_item_is_bounded_and_says_its_source(bdir):
    b, payload, _ = _full(bdir)
    gid = _group_of(b, "run-001")
    for q in payload["questions"]:
        items = q.get("context") or []
        assert len(items) <= QC.MAX_ITEMS
        allowed = QC.RULES.get(QC.theme_of(q) or "", ())
        for it in items:
            assert it["kind"] in allowed and it["label"] and it["source"], (q["question_id"], it)
            if it["kind"] == "quote":
                assert len(it["quote"]) <= QC.QUOTE_CHARS and it["path"] and it["locator"]
            if it["kind"] == "values":
                assert len(it["rows"]) <= QC.MAX_ROWS and all(len(r) == len(it["columns"]) for r in it["rows"])

    env = _q(payload, lambda q: q.get("target_field_path") == "context.environment")
    kinds = [i["kind"] for i in env["context"]]
    assert {"quote", "values", "plot", "table_row"} <= set(kinds), kinds
    quote = next(i for i in env["context"] if i["kind"] == "quote")
    assert quote["quote"] == QUOTE and quote["origin"] == "ai_reading" and quote["locator"] == "line 7"
    assert quote["path"] == _notes_source(b)["relative_path"] and "AI reading" in quote["source"]
    assert "not file evidence" in quote["source"]
    values = next(i for i in env["context"] if i["kind"] == "values")
    assert "Potential (from the name)" in values["columns"] and values["rows_total"] == 9
    assert any("'100mV' (read as 0.1 V)" in row for row in values["rows"])
    plot = next(i for i in env["context"] if i["kind"] == "plot")
    assert plot["path"] == f"processing/{gid}/r-syn/plot.png" and plot["base"] == "bundle" and plot["alt"]

    form = _q(payload, lambda q: q.get("target_field_path") == "sample.sample_form" and "'ZZ1'" in q["text"])
    images = [i for i in form["context"] if i["kind"] == "image"]
    # the image beside a line naming the sample is shown; the scan-script picture beside it is not
    assert [i["path"] for i in images] == [f"extracted/{str(_notes_source(b)['content_sha256'])[:12]}/001_0a1b2c3d.png"]
    assert images[0]["base"] == "notes" and images[0]["document"] == _notes_source(b)["relative_path"]
    assert "The ZZ1 electrode before the first hold:" in images[0]["alt"]
    assert not [i for i in form["context"] if i["kind"] == "plot"]
    assert any("Sample (as the name writes it)" in i.get("columns", ()) for i in form["context"])

    absorber = _q(payload, lambda q: q["kind"] == "confirm_absorber")
    labels = {i["label"]: i for i in absorber["context"]}
    assert labels["Where each group's curve has its edge"]["rows"][0][1] == "9001.5"
    scans = labels["Scans proposed for leaving out or a look, and scan decisions"]
    assert [r[0] for r in scans["rows"]] == ["SYN_scan_001.dat"]  # a scan kept as it is is no proposal
    merge = labels["Their own quick merge (MERGE) compared with ISAAC's curve"]
    assert merge["rows"][0][:2] == ["MERGE/SYN_merge.nor", "agrees"] and "never the answer key" in merge["note"]

    technique = _q(payload, lambda q: q.get("target_field_path") == "system.technique" and q["scope"] == "experiment")
    assert {i["kind"] for i in technique["context"]} <= {"quote", "example_files"} and technique["context"]
    label = _q(payload, lambda q: q["kind"] == "condition_label")
    assert [i["kind"] for i in label["context"]] == ["example_files"]
    who = _q(payload, lambda q: q.get("target_field_path") == "attribution.produced_by.group")
    assert "context" not in who


def test_the_context_is_additive_ids_counts_text_and_the_minimum_are_unchanged(bdir, tmp_path):
    other = tmp_path / "copy"
    shutil.copytree(bdir, other)
    code, with_ctx = _cli(["bundle", "questions", bdir, "--limit", "200", "--with-targets"])
    assert code == 0
    code, without = _cli(["bundle", "questions", other, "--limit", "200", "--with-targets", "--no-context"])
    assert code == 0
    assert any(q.get("context") for q in with_ctx["questions"])
    assert not any("context" in q for q in without["questions"]) and "context_note" not in without
    strip = [{k: v for k, v in q.items() if k != "context"} for q in with_ctx["questions"]]
    assert strip == without["questions"]
    for key in ("counts", "total", "blocking_basis"):
        assert with_ctx[key] == without[key]
    m = {k: v for k, v in with_ctx["minimum_for_one_group"].items() if k != "decision_context"}
    m["questions"] = [{k: v for k, v in x.items() if k != "context"} for x in m["questions"]]
    assert m == without["minimum_for_one_group"]
    # nothing is decided by it: the bundle holds no decision, and the questions are the same
    assert M.load(bdir).get("scientist_decisions") == []
    assert [q["question_id"] for q in Q.consolidate(M.load(bdir))["questions"]] == [q["question_id"] for q in without["questions"]]


def test_the_compact_page_cuts_rows_and_show_question_prints_the_full_context_with_the_file_to_open(bdir):
    code, page = _cli(["bundle", "questions", bdir, "--limit", "200"])
    assert code == 0 and "never the answer" in page["context_note"]
    env = _q(page, lambda q: q.get("target_field_path") == "context.environment")
    values = next(i for i in env["context"] if i["kind"] == "values")
    assert len(values["rows"]) == QC.COMPACT_ROWS and values["rows_total"] == 9
    code, shown = _cli(["bundle", "show", bdir, "question", env["question_id"]])
    assert code == 0 and shown["question_id"] == env["question_id"] and shown["text"] == env["text"]
    full = next(i for i in shown["context"] if i["kind"] == "values")
    assert len(full["rows"]) == QC.MAX_ROWS
    plot = next(i for i in shown["context"] if i["kind"] == "plot")
    assert Path(plot["open_with_read"]) == (bdir / plot["path"]).resolve() and Path(plot["open_with_read"]).is_file()
    # the minimum carries its questions' context and its decisions' (the group's runs, its curve)
    m = page["minimum_for_one_group"]
    assert any(x.get("context") for x in m["questions"])
    assert "confirm_the_group" in (m.get("decision_context") or {})


def test_every_file_value_a_context_states_is_recorded_as_an_exposure_before_it_is_printed(bdir):
    before = {(e["target"]["kind"], e["target"]["id"]) for e in M.load(bdir)["exposures"] if e["command"] == QC.EXPOSURE_COMMAND}
    assert before == set()
    _, _, shown = _full(bdir)
    assert shown and all(k == "candidate" for k, _ in shown)
    code, _ = _cli(["bundle", "questions", bdir, "--limit", "200"])
    assert code == 0
    after = {(e["target"]["kind"], e["target"]["id"]) for e in M.load(bdir)["exposures"] if e["command"] == QC.EXPOSURE_COMMAND}
    # the page's context states (at least) the potentials its environment questions show
    b = M.load(bdir)
    potentials = {("candidate", c["candidate_id"]) for c in b["candidates"]
                  if c.get("target_field_path") == "context.electrochemistry.potential_setpoint_V"}
    assert potentials & after


# --- the clock ----------------------------------------------------------------------------------------------------

def test_spec_start_times_show_the_offset_the_d_and_e_lines_imply_and_no_zone(bdir):
    _, payload, _ = _full(bdir)
    q = _q(payload, lambda q: q.get("target_field_path") == "timestamps.acquired_start_utc" and q["kind"] == "resolve_conflict")
    [item] = q["context"]
    assert item["columns"] == ["Run", "#D local time (no zone)", "#E epoch, in UTC", "Offset they imply"]
    assert item["rows"][0][3] == "UTC−00:40"  # what the synthetic header's two lines imply: a value
    assert "not a time zone" in item["note"] and "no zone is suggested" in item["note"]
    assert not ZONE_LIKE.search(json.dumps(q["context"]))


def test_the_clock_zone_question_shows_each_local_time_with_no_epoch_and_never_suggests_a_zone(tmp_path):
    out = xdc_import(tmp_path, {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45"),
                                "SYN_beta_B.001": stamp("2099-07-14T11:00:00")})
    M.group(out)
    b = M.load(out)
    payload = Q.consolidate(b)
    zq = _q(payload, lambda q: q["kind"] == "clock_time_zone")
    [annotated], shown = QC.annotate([zq], b, out)
    [item] = annotated["context"]
    assert item["kind"] == "values" and item["rows_total"] >= 2
    rows = {r[0]: r for r in item["rows"]}
    assert any("Tue Jul 14 10:23:45 2099" in r[1] for r in rows.values())
    assert all(r[-1] == "none: no #E epoch in this file" for r in rows.values())
    said = json.dumps(annotated["context"])
    assert not ZONE_LIKE.search(said) and "suggested_value" not in said
    assert annotated["text"] == zq["text"] and annotated.get("suggested_value") is None


# --- the image endpoint -------------------------------------------------------------------------------------------

@pytest.fixture()
def client(bdir, monkeypatch, tmp_path):
    monkeypatch.setenv(LB.LOCAL_BUNDLES_ENV, str(bdir.parent))
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    LB._check_memo.clear()
    return TestClient(create_app(), **LOCAL)


def _plot_path(bdir: Path) -> str:
    b = M.load(bdir)
    return f"processing/{_group_of(b, 'run-001')}/r-syn/plot.png"


def test_the_endpoint_serves_a_plot_and_an_extracted_image_with_safe_headers(client, bdir):
    r = client.get("/api/local-bundles/syn/file", params={"path": _plot_path(bdir), "base": "bundle"})
    assert r.status_code == 200 and r.content == png_bytes()
    assert r.headers["content-type"] == "image/png" and r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in r.headers["content-security-policy"] and r.headers["cache-control"] == "no-store"
    notes = _notes_source(M.load(bdir))
    r = client.get("/api/local-bundles/syn/file",
                   params={"path": f"extracted/{str(notes['content_sha256'])[:12]}/001_0a1b2c3d.png", "base": "notes"})
    assert r.status_code == 200 and r.content == png_bytes()


@pytest.mark.parametrize(("path", "status"), [
    ("../syn-notes/extracted/x.png", 400), ("processing/../../syn-notes/x.png", 400), ("/etc/passwd.png", 400),
    ("processing\\x.png", 400), ("C:/x.png", 400), ("./processing/x.png", 400), ("processing//x.png", 400),
    ("bundle.json", 415), ("summary.md", 415), ("processing/x.PNG.txt", 415), ("processing/none.png", 404),
])
def test_the_endpoint_refuses_traversal_absolute_paths_and_other_types(client, path, status):
    r = client.get("/api/local-bundles/syn/file", params={"path": path, "base": "bundle"})
    assert r.status_code == status, (path, r.text)
    assert r.headers["content-type"].startswith("application/json")


def test_the_endpoint_refuses_a_symlink_anywhere_on_the_way_and_a_symlinked_notes_folder(client, bdir, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.png").write_bytes(png_bytes())
    (bdir / "link.png").symlink_to(outside / "secret.png")
    (bdir / "linkdir").symlink_to(outside)
    inside = bdir / "processing" / "inside.png"
    inside.write_bytes(png_bytes())
    (bdir / "alias.png").symlink_to(inside)  # even a link that stays inside is refused
    for path in ("link.png", "linkdir/secret.png", "alias.png"):
        r = client.get("/api/local-bundles/syn/file", params={"path": path})
        assert r.status_code == 403, (path, r.text)
    notes = QC.notes_dir_of(bdir)
    shutil.rmtree(notes)
    notes.symlink_to(outside)
    r = client.get("/api/local-bundles/syn/file", params={"path": "secret.png", "base": "notes"})
    assert r.status_code == 404
    r = client.get("/api/local-bundles/syn/file", params={"path": "processing/inside.png", "base": "elsewhere"})
    assert r.status_code == 422


def test_the_endpoint_needs_the_local_header_like_every_local_bundle_route(client, bdir):
    r = TestClient(create_app(), base_url=LOCAL["base_url"], client=LOCAL["client"]).get(
        "/api/local-bundles/syn/file", params={"path": _plot_path(bdir)})
    assert r.status_code == 403 and r.json()["detail"]["error"] == "local_header_required"
    r = TestClient(create_app(), base_url="http://evil.example:8000", client=LOCAL["client"],
                   headers=LOCAL["headers"]).get("/api/local-bundles/syn/file", params={"path": _plot_path(bdir)})
    assert r.status_code == 421


def test_the_questions_route_carries_each_questions_context_and_records_its_exposures(client, bdir):
    r = client.get("/api/local-bundles/syn/questions")
    assert r.status_code == 200
    qs = r.json()["questions"]
    env = next(q for q in qs if q.get("target_field_path") == "context.environment")
    kinds = [i["kind"] for i in env["context"]]
    assert "plot" in kinds and "quote" in kinds
    # no path on this computer is ever in the page's context
    assert str(bdir) not in json.dumps(qs) and "open_with_read" not in json.dumps(qs)
    plot = next(i for i in env["context"] if i["kind"] == "plot")
    assert client.get("/api/local-bundles/syn/file", params={"path": plot["path"], "base": plot["base"]}).status_code == 200
    assert any(e["command"] == QC.EXPOSURE_COMMAND for e in M.load(bdir)["exposures"])


# --- the skill docs -----------------------------------------------------------------------------------------------

def test_the_skill_says_how_to_present_the_context_and_that_it_is_never_the_answer():
    skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    ref = (SKILL / "reference" / "questions-and-decisions.md").read_text(encoding="utf-8")
    assert "`context`" in skill and "never the answer" in skill
    section = ref[ref.index("## Context beside a question"):]
    section = section[: section.index("\n## ", 3)]
    for words in ("quote the lines", "Read tool", "where each came from", "never the answer", "--no-context",
                  "bundle show <bundle> question", "offset", "suggest no zone", "AI reading"):
        assert words in section, words
