"""The ``.pxp`` (Igor Pro packed experiment) reader. SYNTHETIC files only, built here record by
record: wave names like ``FAKE_wave_a``, text that says FAKE_SAMPLE. Nothing is read from a real
experiment."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import.readers import igor_pxp as P


def record(rtype: int, data: bytes, order: str = "<") -> bytes:
    return struct.pack(order + "Hhi", rtype, 0, len(data)) + data


def wave_v5(name: str, note: bytes = b"", order: str = "<") -> bytes:
    wfm = 100
    head = struct.pack(order + "hhiii", 5, 0, wfm, 0, len(note)).ljust(64, b"\0")
    body = bytearray(wfm)
    body[28 : 28 + len(name)] = name.encode()  # bname sits at byte 92 of the record data
    return head + bytes(body) + note


def packed_file(text: bytes, name: str = "FAKE_proc", code: bytes = b"TXET", order: str = "<") -> bytes:
    data = bytearray(154)
    data[4:8] = code
    data[32 : 32 + len(name)] = name.encode()
    struct.pack_into(order + "i", data, 22, len(text))
    return bytes(data) + text


def make_pxp(order: str = "<", *, extra: tuple[bytes, ...] = ()) -> bytes:
    history = "•FAKE_SAMPLE step one\rsecond FAKE line\r\rthird line\r".encode("mac_roman")
    return b"".join(
        [
            record(11, b"\x10\x00" * 8, order),  # a record type this reader does not interpret
            record(2, history, order),
            record(4, b"// Platform=Macintosh, IGORVersion=6.370\rMacro FAKE_macro()\rEnd\r", order),
            record(5, b"#pragma rtGlobals=3\rFunction FAKE_fn()\rEnd\r", order),
            record(9, b"FAKE_folder\0", order),
            record(3, wave_v5("FAKE_wave_a", b"FAKE note for wave a", order), order),
            record(3, wave_v5("FAKE_wave_b", b"", order), order),
            record(10, b"", order),
            record(3, wave_v5("FAKE_wave_root", b"", order), order),
            record(8, packed_file(b"Function FAKE_packed()\rEnd\r", order=order), order),
            *extra,
        ]
    )


def write_pxp(path: Path, data: bytes | None = None, **kw) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(make_pxp(**kw) if data is None else data)
    return path


def by_concept(result, concept):
    return [e for e in result.entries if e["concept"] == concept]


def summary(result) -> dict:
    return json.loads(by_concept(result, "igor.reader_summary")[0]["literal"])


# --- happy path -------------------------------------------------------------------------------------


@pytest.mark.parametrize("order", ["<", ">"])
def test_history_text_records_waves_notes_and_folders_are_read(tmp_path, order):
    result = P.read(write_pxp(tmp_path / "e.pxp", order=order), "e.pxp")
    assert result.refused_reason is None and result.kind == "igor_experiment" and result.reader_id == "igor_pxp_v1"
    history = by_concept(result, "igor.history_line")
    assert [h["literal"] for h in history] == ["•FAKE_SAMPLE step one", "second FAKE line", "third line"]
    assert [h["locator"] for h in history] == ["history line 1", "history line 2", "history line 4"], "blank lines keep their numbers"
    assert by_concept(result, "igor.procedure_text")[0]["locator"] == "record 4 (procedure)"
    assert "FAKE_fn" in by_concept(result, "igor.procedure_text")[0]["literal"]
    assert by_concept(result, "igor.recreation_macros")[0]["locator"] == "record 3 (recreation macros)"
    waves = {w["literal"]: w["locator"] for w in by_concept(result, "igor.wave")}
    assert set(waves) == {"FAKE_wave_a", "FAKE_wave_b", "FAKE_wave_root"}
    assert "root:FAKE_folder" in waves["FAKE_wave_a"] and waves["FAKE_wave_root"].endswith("data folder root)")
    note = by_concept(result, "igor.wave_note")
    assert [n["literal"] for n in note] == ["FAKE note for wave a"] and note[0]["locator"].endswith("(wave note)")
    assert by_concept(result, "igor.data_folder")[0]["literal"] == "FAKE_folder"
    assert by_concept(result, "igor.packed_file_name")[0]["literal"] == "FAKE_proc"
    assert by_concept(result, "igor.packed_file_type")[0]["literal"] == "TXET"
    assert "FAKE_packed" in by_concept(result, "igor.packed_file_text")[0]["literal"]
    s = summary(result)
    assert s["byte_order"] == ("little-endian" if order == "<" else "big-endian")
    assert s["records_walked"] == 10 and s["record_types_skipped"] == {"11": 1}
    assert s["text_encodings"].get("mac_roman") == 1  # the history, which is not valid UTF-8


def test_a_wave_of_an_unsupported_version_is_skipped_and_counted_not_fatal(tmp_path):
    odd = struct.pack("<h", 9) + b"\0" * 200
    result = P.read(write_pxp(tmp_path / "e.pxp", extra=(record(3, odd),)), "e.pxp")
    assert summary(result)["wave_records_unrecognised"] == 1 and len(by_concept(result, "igor.wave")) == 3
    assert result.skipped_total >= 2  # that wave and the unread record type


def test_a_packed_file_that_does_not_match_the_observed_layout_is_skipped_and_counted(tmp_path):
    binary = record(8, bytes(range(256)) * 2)
    result = P.read(write_pxp(tmp_path / "e.pxp", extra=(binary,)), "e.pxp")
    assert summary(result)["packed_file_unrecognised"] == 1 and len(by_concept(result, "igor.packed_file_text")) == 1


# --- bounds and refusals ------------------------------------------------------------------------------


def test_a_truncated_file_keeps_what_was_read_and_says_where_it_stopped(tmp_path):
    full = make_pxp()
    result = P.read(write_pxp(tmp_path / "e.pxp", full[: len(full) - 20]), "e.pxp")
    s = summary(result)
    assert result.refused_reason is None and s["stopped_by"] == "malformed_length" and s["malformed_length"] == 1
    assert by_concept(result, "igor.history_line") and not by_concept(result, "igor.packed_file_text")


def test_a_negative_record_length_ends_the_walk_without_reading_past_it(tmp_path):
    bad = struct.pack("<Hhi", 3, 0, -5) + b"FAKE" * 10
    result = P.read(write_pxp(tmp_path / "e.pxp", extra=(bad,)), "e.pxp")
    s = summary(result)
    assert s["stopped_by"] == "malformed_length" and s["records_walked"] == 10


def test_a_length_past_the_end_of_the_file_is_not_followed(tmp_path):
    huge = struct.pack("<Hhi", 5, 0, 2_000_000_000)
    result = P.read(write_pxp(tmp_path / "e.pxp", extra=(huge,)), "e.pxp")
    assert summary(result)["malformed_length"] == 1


@pytest.mark.parametrize(
    "payload",
    [b"", b"\x01\x02\x03", bytes(range(256)) * 8, struct.pack("<Hhi", 0x7FFF, 0, 10**9) + b"x" * 50],
    ids=["empty", "short", "garbage", "first-header-implausible"],
)
def test_garbage_is_refused_with_a_reason_and_no_entries(tmp_path, payload):
    result = P.read(write_pxp(tmp_path / "g.pxp", payload), "g.pxp")
    assert result.refused_reason and result.entries == []


def test_the_record_ceiling_stops_the_walk_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "MAX_RECORDS", 3)
    result = P.read(write_pxp(tmp_path / "e.pxp"), "e.pxp")
    s = summary(result)
    assert s["stopped_by"] == "max_records" and s["records_walked"] == 3


def test_a_text_record_is_read_only_up_to_its_byte_ceiling(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "MAX_TEXT_RECORD_BYTES", 16)
    result = P.read(write_pxp(tmp_path / "e.pxp"), "e.pxp")
    s = summary(result)
    assert s["text_records_read_short"] >= 1 and result.suppressed_total >= 1


def test_a_long_text_record_is_clipped_with_a_marker(tmp_path):
    long_text = b"Function FAKE_long()\r" + b"// filler\r" * 2_000
    result = P.read(write_pxp(tmp_path / "e.pxp", extra=(record(5, long_text),)), "e.pxp")
    clipped = [e for e in by_concept(result, "igor.procedure_text") if "[clipped:" in e["literal"]]
    assert len(clipped) == 1 and summary(result)["text_records_clipped"] == 1


def test_history_lines_and_waves_are_capped_and_the_cap_is_stated(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "MAX_HISTORY_LINES", 2)
    monkeypatch.setattr(P, "MAX_WAVES", 1)
    result = P.read(write_pxp(tmp_path / "e.pxp"), "e.pxp")
    s = summary(result)
    assert len(by_concept(result, "igor.history_line")) == 2 and s["dropped_for_a_cap"]["history_lines"] == 1
    assert len(by_concept(result, "igor.wave")) == 1 and s["dropped_for_a_cap"]["waves"] == 2


def test_the_entry_budget_caps_the_whole_file(tmp_path):
    result = P.read(write_pxp(tmp_path / "e.pxp"), "e.pxp", entry_budget=5)
    assert len(result.entries) == 5 and result.entries[0]["concept"] == "igor.reader_summary" and result.partial


def test_nothing_in_the_experiment_is_executed(tmp_path):
    sentinel = tmp_path / "SENTINEL"
    code = f"Function FAKE_x()\rSystemCommand(\"touch {sentinel}\")\rEnd\r".encode()
    P.read(write_pxp(tmp_path / "e.pxp", extra=(record(5, code),)), "e.pxp")
    assert not sentinel.exists()


# --- through the bundle ---------------------------------------------------------------------------------


def _import(tmp_path: Path, root: Path, capsys) -> tuple[Path, dict]:
    out = tmp_path / "out"
    assert cli.main(["import", str(root), "--out", str(out)]) == 0
    capsys.readouterr()
    return out, json.loads((out / "bundle.json").read_text(encoding="utf-8"))


def test_an_experiment_in_a_folder_becomes_evidence_never_a_run(tmp_path, capsys):
    root = tmp_path / "bt"
    write_pxp(root / "experiment.pxp")
    out, bundle = _import(tmp_path, root, capsys)
    assert B.validate_bundle(bundle) == [] and cli.main(["bundle", "check", str(out)]) == 0
    src = next(s for s in bundle["sources"] if s["relative_path"] == "experiment.pxp")
    assert src["reader"]["reader_id"] == "igor_pxp_v1" and src["reader"]["content_read"] is True
    assert src["classification"]["source_type"] == "analysis_file:igor_experiment"
    assert "experiment.pxp" not in {u["relative_path"] for u in bundle["unread_files"]}
    mine = [e for e in bundle["extended_context"] if e["parser_id"] == "igor_pxp_v1"]
    assert {e["concept"] for e in mine} >= {"igor.history_line", "igor.wave", "igor.wave_note", "igor.procedure_text"}
    assert all(e["scope"] == "analysis_file" and e["run_id"] is None and e["source_id"] == src["source_id"] for e in mine)
    assert bundle["runs"] == [] and bundle["processed_outputs"] == [] and bundle["record_groups"] == []
    assert {"reader_id": "igor_pxp_v1", "version": "1"} in bundle["generator"]["readers"]


def test_a_garbage_experiment_stays_unread_with_the_readers_own_reason(tmp_path, capsys):
    root = tmp_path / "bt"
    root.mkdir()
    (root / "broken.pxp").write_bytes(bytes(range(256)) * 4)
    out, bundle = _import(tmp_path, root, capsys)
    assert B.validate_bundle(bundle) == []
    row = next(u for u in bundle["unread_files"] if u["relative_path"] == "broken.pxp")
    assert row["reason_code"] == "reader_refused" and "not an Igor packed experiment" in row["reason"]


def test_a_crafted_file_of_deeply_nested_folders_stays_bounded_in_time_and_output(tmp_path):
    import time

    depth, waves = 20_000, 300
    folders = [record(9, b"F" * 20 + b"\0") for _ in range(depth)]
    wave_records = [record(3, wave_v5(f"FAKE_w{i}")) for i in range(waves)]
    path = write_pxp(tmp_path / "deep.pxp", make_pxp(extra=(*folders, *wave_records)))
    started = time.time()
    result = P.read(path, "deep.pxp")
    assert time.time() - started < 10
    s = summary(result)
    assert s["folder_starts_past_depth_cap"] == depth - P.MAX_FOLDER_DEPTH
    wave_entries = by_concept(result, "igor.wave")
    assert len(wave_entries) == waves + 3
    assert max(len(e["locator"]) for e in wave_entries) < 400, "folder paths are clipped in locators"
    assert sum(len(json.dumps(e)) for e in result.entries) < 1_500_000
    # the pairing of ends with overflowed starts keeps later waves in their real folder
    ends = [record(10, b"") for _ in range(depth)]
    after = P.read(write_pxp(tmp_path / "deep2.pxp", make_pxp(extra=(*folders, *ends, record(3, wave_v5("FAKE_after"))))), "deep2.pxp")
    assert by_concept(after, "igor.wave")[-1]["locator"].endswith("data folder root)")
