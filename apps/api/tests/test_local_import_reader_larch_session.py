"""The ``.larix`` (Larch session) reader. SYNTHETIC files only: sample ``FAKE_SAMPLE``, element
``Xx``, every path and name invented here. Nothing is read from a real file."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import.readers import larch_session as L

FAKE_UNC = "//fakehost.invalid/fakeshare/FAKE_SAMPLE_001.dat"


def make_session_text(extra_commands: tuple[str, ...] = ()) -> str:
    group = {
        "__class__": "Group",
        "groupname": "fakegrp1",
        "filename": "FAKE_SAMPLE_001.dat",
        "atsym": "Xx",
        "edge": "K",
        "e0": 1234.5,
        "energy_shift": 0.0,
        "energy_units": "eV",
        "datatype": "xas",
        "mu": {"__class__": "Array", "value": [1, 2, 3]},
        "callargs": {
            "__class__": "Group",
            "pre_edge": {"__class__": "Dict", "pre1": -100.0, "pre2": -30.0, "norm1": 50.0, "norm2": 200.0, "nnorm": 1},
        },
    }
    commands = [
        "# larch history saved Mon Jan  1 00:00:00 2001",
        f"fakegrp1 = read_ascii('{FAKE_UNC}', labels='energy mu')",
        "fakegrp1.groupname = 'fakegrp1'",
        "fakegrp1.energy_shift = 0.5000",
        "pre_edge(fakegrp1, pre1=-100.00, pre2=-30.00, nvict=0, npre=1, nnorm=1, norm1=50.00, norm2=-1.00)",
        "plot_mu(fakegrp1, show_norm=False,",
        "        title='FAKE title', new=True)",
        "plot_mu(fakegrp1, show_norm=True, new=False)",
        "autobk(fakegrp1, rbkg= 1.000, ek0= 1234.5,",
        "      kmin= 0.000, kmax= 7.750, kweight= 2.0)",
        "xftf(fakegrp1, kmin= 2.000, kmax= 7.250, dk= 4.000, window='Kaiser-Bessel')",
        "try:",
        "    npaths = len(_feffpaths.keys())",
        "except:",
        "    _feffpaths = {}",
        *extra_commands,
    ]
    symbols = [
        "<:_xasgroups:>",
        json.dumps({"__class__": "Dict", "FAKE_SAMPLE_001.dat": "fakegrp1"}),
        "<:fakegrp1:>",
        json.dumps(group),
        "<:broken:>",
        "{not json at all",
    ]
    return "\n".join(
        [
            "##LARIX: 1.0      Larch Session File",
            "##Date Saved: 2001-01-01 00:00:00",
            "##<CONFIG>",
            "##Machine Platform: FakeOS",
            "##Machine Name: FAKE-HOST-NAME",
            "##Machine MACID: 000000000000",
            "##Python Version: 3.12.8",
            "##Larch Release Version: 2099.1.0",
            '##Larch home_dir: "C:/Users/fake_user"',
            "##Larch Core Groups: [\"_main\"]",
            "##</CONFIG>",
            "##<Session Commands>",
            *commands,
            "##</Session Commands>",
            "##<Symbols: count=3>",
            *symbols,
            "##</Symbols>",
            "",
        ]
    )


def write_larix(path: Path, text: str | None = None, *, compress: bool = True) -> Path:
    text = make_session_text() if text is None else text
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(text.encode("utf-8")) if compress else text.encode("utf-8"))
    return path


def by_concept(result, concept):
    return [e for e in result.entries if e["concept"] == concept]


# --- happy path ---------------------------------------------------------------------------------


def test_a_session_yields_header_groups_files_commands_and_parameters(tmp_path):
    result = L.read(write_larix(tmp_path / "s.larix"), "s.larix")
    assert result.refused_reason is None and result.kind == "larch_session" and result.reader_id == "larch_session_v1"
    assert by_concept(result, "larch.header.larix")[0]["literal"].startswith("1.0")
    assert by_concept(result, "larch.header.date_saved")[0]["literal"] == "2001-01-01 00:00:00"
    assert by_concept(result, "larch.config.python_version")[0]["literal"] == "3.12.8"
    # the data file a command read, verbatim, with the command that read it
    data = by_concept(result, "larch.data_file")
    assert [d["literal"] for d in data] == [FAKE_UNC] and data[0]["locator"].startswith("command ")
    # group names and file names from the symbol table
    assert by_concept(result, "larch.group.groupname")[0]["literal"] == "fakegrp1"
    assert by_concept(result, "larch.group.atsym")[0]["literal"] == "Xx"
    assert by_concept(result, "larch.group.e0")[0]["literal"] == "1234.5"
    assert by_concept(result, "larch.group.callargs.pre_edge.pre1")[0]["literal"] == "-100.0"
    assert by_concept(result, "larch.xasgroup.groupname")[0]["literal"] == "fakegrp1"
    assert by_concept(result, "larch.xasgroup.filename")[0]["literal"] == "FAKE_SAMPLE_001.dat"
    # processing parameters stated in calls, written as in the call
    params = {e["concept"]: e["literal"] for e in result.entries if e["concept"].startswith("larch.param.")}
    assert params["larch.param.pre_edge.pre1"] == "-100.00" and params["larch.param.pre_edge.norm2"] == "-1.00"
    assert params["larch.param.autobk.rbkg"] == "1.000" and params["larch.param.autobk.kweight"] == "2.0"
    assert params["larch.param.xftf.window"] == "'Kaiser-Bessel'"
    assert params["larch.param.set.energy_shift"] == "0.5000"


def test_commands_are_statements_with_stable_numbers_and_display_calls_are_counted_not_stored(tmp_path):
    result = L.read(write_larix(tmp_path / "s.larix"), "s.larix")
    commands = by_concept(result, "larch.command")
    texts = [c["literal"] for c in commands]
    assert any(t.startswith("autobk(fakegrp1") and "kmax= 7.750" in t for t in texts), "a multi-line call is one command"
    assert not any(t.startswith("plot_mu") for t in texts)
    summary = json.loads(by_concept(result, "larch.reader_summary")[0]["literal"])
    assert summary["display_commands_not_stored"] == {"plot_mu": 2}
    # command N counts ALL statements, so the autobk call (after two plot calls) is not 'command 4'
    autobk = next(c for c in commands if c["literal"].startswith("autobk"))
    assert autobk["locator"].startswith("command 7 (lines ")
    assert summary["symbols_skipped_unparseable"] == 1


def test_machine_name_machine_id_and_profile_paths_are_withheld_and_it_says_so(tmp_path):
    result = L.read(write_larix(tmp_path / "s.larix"), "s.larix")
    blob = json.dumps(result.entries)
    for withheld in ("FAKE-HOST-NAME", "000000000000", "fake_user"):
        assert withheld not in blob
    summary = json.loads(by_concept(result, "larch.reader_summary")[0]["literal"])
    assert summary["config_lines_withheld"] == 3 and "machine" in summary["withheld"]


def test_a_plain_text_session_with_the_header_is_read(tmp_path):
    result = L.read(write_larix(tmp_path / "s.larix", compress=False), "s.larix")
    assert result.refused_reason is None and by_concept(result, "larch.data_file")


def test_nothing_in_a_session_is_executed(tmp_path):
    sentinel = tmp_path / "SENTINEL"
    text = make_session_text((f"__import__('pathlib').Path({str(sentinel)!r}).write_text('x')", f"open({str(sentinel)!r}, 'w')"))
    result = L.read(write_larix(tmp_path / "s.larix", text), "s.larix")
    assert not sentinel.exists()
    assert any("__import__" in c["literal"] for c in by_concept(result, "larch.command"))


# --- bounds and refusals --------------------------------------------------------------------------


def test_an_overlong_command_is_clipped_with_a_marker_naming_the_original_length(tmp_path):
    long_arg = "x" * 900
    text = make_session_text((f"fakegrp1.note = '{long_arg}'",))
    result = L.read(write_larix(tmp_path / "s.larix", text), "s.larix")
    clipped = [c for c in by_concept(result, "larch.command") if "[clipped:" in c["literal"]]
    assert len(clipped) == 1 and "first 500 of " in clipped[0]["literal"]
    assert json.loads(by_concept(result, "larch.reader_summary")[0]["literal"])["commands_clipped"] == 1


def test_the_entry_budget_caps_the_file_and_the_summary_says_what_was_dropped(tmp_path):
    result = L.read(write_larix(tmp_path / "s.larix"), "s.larix", entry_budget=12)
    assert len(result.entries) == 12 and result.entries[0]["concept"] == "larch.reader_summary"
    summary = json.loads(result.entries[0]["literal"])
    assert summary["dropped_for_a_cap"]["file_budget"] > 0 and result.partial


def test_the_per_category_cap_counts_what_it_drops(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "MAX_COMMAND_ENTRIES", 3)
    result = L.read(write_larix(tmp_path / "s.larix"), "s.larix")
    summary = json.loads(by_concept(result, "larch.reader_summary")[0]["literal"])
    assert len(by_concept(result, "larch.command")) == 3
    assert summary["dropped_for_a_cap"]["commands"] == summary["commands_stored_of"] - 3 > 0


@pytest.mark.parametrize(
    "payload, needle",
    [
        (b"\x00\x01garbage that is not gzip and has no header", "neither a gzip file"),
        (b"plain text without the header\n", "neither a gzip file"),
        (gzip.compress(b"not a larch file\n"), "not a `##LARIX:` header"),
        (gzip.compress(make_session_text().encode())[:40], "ends early"),
        (b"\x1f\x8b" + b"\x00" * 30, "damaged"),
    ],
)
def test_a_file_that_is_not_a_session_is_refused_with_a_reason_and_no_entries(tmp_path, payload, needle):
    path = tmp_path / "bad.larix"
    path.write_bytes(payload)
    result = L.read(path, "bad.larix")
    assert needle in (result.refused_reason or "") and result.entries == []


def test_a_gzip_bomb_is_refused_by_its_ratio_before_it_is_held(tmp_path):
    path = tmp_path / "bomb.larix"
    path.write_bytes(gzip.compress(b"##LARIX: 1.0\n" + b"\0" * 6_000_000, compresslevel=9))
    result = L.read(path, "bomb.larix")
    assert "expands past" in (result.refused_reason or "") and result.entries == []


def test_an_absolute_ceiling_applies_even_when_the_ratio_is_modest(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "MAX_DECOMPRESSED_BYTES", 2_000)
    import os

    noise = os.urandom(5_000).hex().encode()
    path = tmp_path / "big.larix"
    path.write_bytes(gzip.compress(b"##LARIX: 1.0\n" + noise))
    assert "expands past" in (L.read(path, "big.larix").refused_reason or "")


def test_a_missing_file_is_a_refusal_not_an_exception(tmp_path):
    assert L.read(tmp_path / "nope.larix", "nope.larix").refused_reason


# --- through the bundle -----------------------------------------------------------------------------


def _import(tmp_path: Path, root: Path, capsys) -> tuple[Path, dict]:
    out = tmp_path / "out"
    assert cli.main(["import", str(root), "--out", str(out)]) == 0
    capsys.readouterr()
    return out, json.loads((out / "bundle.json").read_text(encoding="utf-8"))


def test_a_session_in_a_folder_becomes_evidence_never_a_run(tmp_path, capsys):
    root = tmp_path / "bt"
    write_larix(root / "LARCH" / "session.larix")
    (root / "LARCH" / "note.txt").write_text("free text\n")
    out, bundle = _import(tmp_path, root, capsys)
    assert B.validate_bundle(bundle) == []
    assert cli.main(["bundle", "check", str(out)]) == 0
    src = next(s for s in bundle["sources"] if s["relative_path"] == "LARCH/session.larix")
    assert src["reader"]["reader_id"] == "larch_session_v1" and src["reader"]["content_read"] is True
    assert src["classification"]["source_type"] == "analysis_file:larch_session"
    assert "LARCH/session.larix" not in {u["relative_path"] for u in bundle["unread_files"]}
    entries = [e for e in bundle["extended_context"] if e["source_id"] == src["source_id"] and e["parser_id"] == "larch_session_v1"]
    assert entries and all(e["scope"] == "analysis_file" and e["run_id"] is None for e in entries)
    assert all(e["value_state"] == "source_recorded" and e["is_official_field_value"] is False for e in entries)
    assert not any("processed_output_id" in e and e["processed_output_id"] for e in entries)
    # not a run, not a processed output, not in any group
    for run in bundle["runs"]:
        assert "session.larix" not in json.dumps(run["scans"])
    assert all("session.larix" not in json.dumps(po["files"]) for po in bundle["processed_outputs"])
    assert {"reader_id": "larch_session_v1", "version": "1"} in bundle["generator"]["readers"]
    assert "local_import_analysis_file_classifier_v1" in bundle["generator"]["classifier_ids"]


def test_a_bad_session_stays_unread_with_the_readers_own_reason(tmp_path, capsys):
    root = tmp_path / "bt"
    root.mkdir()
    (root / "broken.larix").write_bytes(b"\x00not gzip")
    out, bundle = _import(tmp_path, root, capsys)
    assert B.validate_bundle(bundle) == []
    row = next(u for u in bundle["unread_files"] if u["relative_path"] == "broken.larix")
    assert row["reason_code"] == "reader_refused" and "neither a gzip file" in row["reason"]
    src = next(s for s in bundle["sources"] if s["relative_path"] == "broken.larix")
    assert src["reader"]["content_read"] is False and src["reader"]["reader_id"] == "larch_session_v1"
    assert "larch_session_v1" not in [r["reader_id"] for r in bundle["generator"]["readers"]]


def test_header_config_literals_summary_names_and_concept_parts_are_all_bounded(tmp_path):
    text = make_session_text()
    text = text.replace("##LARIX: 1.0      Larch Session File", "##LARIX: " + "H" * 5_000, 1)
    text = text.replace("##Python Version: 3.12.8", "##Python Version: " + "P" * 5_000, 1)
    extra_sections = "\n".join(f"##<Section {i}>\n##</Section {i}>" for i in range(300))
    plots = "\n".join(f"plot_kind_{i}(fakegrp1)" for i in range(150))
    long_kw = "k" * 500
    odd_call = f"pre_edge(fakegrp1, {long_kw}=1)"
    text = text.replace("##<Session Commands>", extra_sections + "\n##<Session Commands>\n" + plots + "\n" + odd_call, 1)
    result = L.read(write_larix(tmp_path / "s.larix", text), "s.larix")
    assert result.refused_reason is None
    for concept in ("larch.header.larix", "larch.config.python_version"):
        literal = by_concept(result, concept)[0]["literal"]
        assert len(literal) < 400 and "[clipped:" in literal
    summary_entry = by_concept(result, "larch.reader_summary")[0]
    summary = json.loads(summary_entry["literal"])
    assert len(summary["sections"]) <= L.MAX_SUMMARY_NAMES and summary["sections_not_listed"] > 200
    assert len(summary["display_commands_not_stored"]) <= L.MAX_SUMMARY_NAMES + 1
    assert sum(summary["display_commands_not_stored"].values()) == 152
    assert len(summary_entry["literal"]) < 20_000
    assert max(len(e["concept"]) for e in result.entries) < 140
    assert all(len(e["literal"]) <= 500 + 60 for e in result.entries if e["concept"] != "larch.reader_summary"), "every stored literal is within the stated cap"
