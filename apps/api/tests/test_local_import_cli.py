"""LOCAL-1: ``isaac import`` / ``isaac bundle`` end to end, defect-shaped.

Every test runs the CLI in-process (``local_import.cli.main``) or through the
``isaac`` entry point (``isaac_records.cli.main``) over committed synthetic fixtures or
tiny ``tmp_path`` fixtures built here. No real data, no network, no server.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import isaac_api.historical_import as hist
import isaac_api.workspace as ws
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli

REPO_ROOT = ws.REPO_ROOT
SEMANTICS = REPO_ROOT / "tests/fixtures/bl15/semantics/multi_operator_corpus"


@pytest.fixture(scope="module")
def imported(tmp_path_factory):
    out = tmp_path_factory.mktemp("bundle") / "out"
    assert cli.main(["import", str(SEMANTICS), "--out", str(out)]) == cli.EXIT_OK
    return out, json.loads((out / "bundle.json").read_text(encoding="utf-8"))


def _run(capsys, *argv) -> tuple[int, str, str]:
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _run_by_stem(bundle, stem):
    return next(r for r in bundle["runs"] if r["stem"] == stem)


# --- the files ------------------------------------------------------------------------


def test_import_writes_every_bundle_file_and_a_valid_bundle(imported):
    out, bundle = imported
    assert sorted(p.name for p in out.iterdir()) == sorted(cli.BUNDLE_FILES)
    assert B.check_bundle(out) == []
    assert json.loads((out / "runs.json").read_text())["total"] == len(bundle["runs"]) == 9
    assert json.loads((out / "conflicts.json").read_text())["total"] == len(bundle["conflicts"])
    questions = json.loads((out / "questions.json").read_text())
    assert questions["format"] == "isaac.questions" and questions["format_version"] == "2.0.0"
    assert questions["counts"]["fine_grained_v1"] == len(bundle["questions"])
    full = json.loads((out / "reading.full.json").read_text())
    assert len(full["candidates"]) == len(bundle["candidates"])


def test_summary_is_compact_and_says_it_is_not_an_official_record(imported):
    out, _ = imported
    summary = (out / "summary.md").read_bytes()
    assert len(summary) <= cli.SUMMARY_TARGET_BYTES, len(summary)
    text = summary.decode("utf-8")
    assert "This is not a validated official ISAAC record" in text
    for heading in ("## Counts", "## Run groups", "## Runs", "## Needs review", "## Unread files", "## Readiness"):
        assert heading in text


def test_no_absolute_path_is_written_by_default(imported, tmp_path, capsys):
    out, bundle = imported
    for name in cli.BUNDLE_FILES:
        assert str(SEMANTICS) not in (out / name).read_text(encoding="utf-8"), name
    assert "local_root_hint" not in bundle["source_root"]
    hinted = tmp_path / "hinted"
    code, _, _ = _run(capsys, "import", str(SEMANTICS), "--out", str(hinted), "--record-local-root")
    assert code == 0
    hint = json.loads((hinted / "bundle.json").read_text())["source_root"]["local_root_hint"]
    assert hint == str(SEMANTICS.resolve())


# --- what the archive holds ---------------------------------------------------------------


def test_multiple_runs_from_one_archive(imported):
    _, bundle = imported
    assert len(bundle["runs"]) == 9
    assert len({r["run_key"] for r in bundle["runs"]}) == 9
    assert all(r["run_candidate"] for r in bundle["runs"])


def test_one_macro_declares_several_acquisitions(imported):
    _, bundle = imported
    declaring = {}
    for r in bundle["runs"]:
        for d in r["declared_by"]:
            declaring.setdefault(d["macro_path"], []).append(r["run_id"])
    assert len(declaring["run01.mac"]) >= 5
    macro = next(s for s in bundle["sources"] if s["relative_path"] == "run01.mac")
    assert macro["classification"]["source_type"].endswith("macro")


def test_several_scans_belong_to_one_measurement(imported):
    _, bundle = imported
    run = bundle["runs"][0]
    assert run["scan_count"] == 2 == len(run["scans"])
    assert len({s["source_id"] for s in run["scans"]}) == 2
    assert all(s["relative_path"].startswith(run["stem"] + "_dir/") for s in run["scans"])


def test_operators_are_evidence_not_the_naming_profile(imported):
    _, bundle = imported
    people = bundle["contributors"]
    assert len(people) >= 2
    for p in people:
        assert p["role"] == "provenance" and p["is_actor"] is False and p["is_naming_profile"] is False
        assert p["evidence"] and all(e["source_id"] for e in p["evidence"])
    profile_ids = {n["profile_id"] for n in bundle["naming_profiles"]}
    assert not profile_ids & {p["name"] for p in people}
    # the runs' naming profile is the convention, whoever operated
    assert {tuple(r["naming_profile"]["profile_ids"]) for r in bundle["runs"]} == {
        ("ssrl_bl152_herfd_echem_naming",)
    }
    named_runs = [r for r in bundle["runs"] if r["contributor_ids"]]
    assert len({tuple(r["contributor_ids"]) for r in named_runs}) >= 2


def test_duplicate_legacy_numbers_are_two_runs_both_flagged(imported):
    _, bundle = imported
    fives = [r for r in bundle["runs"] if r["legacy_number"] == 5]
    assert len(fives) == 2
    a, b = fives
    assert a["run_key"] != b["run_key"]
    assert a["legacy_number_shared"] and b["legacy_number_shared"]
    assert a["shares_legacy_number_with"] == [b["run_id"]]
    assert b["shares_legacy_number_with"] == [a["run_id"]]
    dup = next(c for c in bundle["conflicts"] if c["kind"] == "duplicate_legacy_number")
    assert sorted(dup["run_ids"]) == sorted([a["run_id"], b["run_id"]])
    assert dup["value_state"] == "conflicting"


def test_filename_header_and_macro_disagreement_keeps_every_witness(imported):
    _, bundle = imported
    conflict = next(
        c for c in bundle["conflicts"]
        if c["kind"] == "internal_declaration_vs_filename" and c["run_ids"] == ["run-001"]
    )
    assert conflict["value_state"] == "conflicting"
    locators = {w["locator"] for r in conflict["readings"] for w in r["witnesses"]}
    assert {"filename", "#F"} <= locators
    values = {r["value"] for r in conflict["readings"]}
    assert len(values) == 2  # both readings kept; nothing chosen
    cand = next(c for c in bundle["candidates"] if c["candidate_id"] == conflict["candidate_id"])
    assert cand["value"] is None
    assert {e["relation"] for e in cand["evidence"]} == {"contradicts"}
    assert {e["reading_index"] for e in cand["evidence"]} == {0, 1, 2}


def test_a_timestamp_disagreement_across_files_is_conflicting(imported):
    _, bundle = imported
    run = _run_by_stem(bundle, "04_02_ZZ2_base_after500Cycling_filter20_800mV")
    cand = next(
        c for c in bundle["candidates"]
        if c["run_id"] == run["run_id"] and c["statement_key"] == "acquisition_timestamp"
    )
    assert cand["value_state"] == "conflicting" and cand["value"] is None
    assert len({e["source_id"] for e in cand["evidence"]}) >= 2


# --- unread, unsupported, refused ---------------------------------------------------------


def _small_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    shutil.copytree(SEMANTICS, root)
    return root


def test_files_no_reader_handles_are_listed_as_unread(tmp_path, capsys):
    root = _small_corpus(tmp_path)
    (root / "detector_counts.mca").write_text("#F detector_counts.mca\n#S 1 mca\n1 2 3\n")
    (root / "picture.bin").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00binary")
    out = tmp_path / "out"
    code, _, _ = _run(capsys, "import", str(root), "--out", str(out))
    assert code == 0
    unread = json.loads((out / "unread_files.json").read_text())
    paths = {u["relative_path"]: u for u in unread["unread_files"]}
    assert {"detector_counts.mca", "picture.bin"} <= set(paths)
    for u in paths.values():
        assert u["reason"] and u["reason_code"] and u["source_id"]
    assert unread["total"] == len(unread["unread_files"])
    assert "detector_counts.mca" in (out / "summary.md").read_text()


@pytest.mark.parametrize("name, content", [("beamtime.tar", b"not a zip at all"), ("notes.7z", b"7z\xbc\xaf")])
def test_an_unsupported_format_is_refused_truthfully(tmp_path, capsys, name, content):
    target = tmp_path / name
    target.write_bytes(content)
    code, _, err = _run(capsys, "import", str(target), "--out", str(tmp_path / "out"))
    assert code == cli.EXIT_INPUT_REFUSED
    assert "unsupported_format" in err and "neither a folder nor a ZIP" in err
    assert not (tmp_path / "out").exists()


def test_a_missing_path_is_refused(tmp_path, capsys):
    code, _, err = _run(capsys, "import", str(tmp_path / "nope"), "--out", str(tmp_path / "out"))
    assert code == cli.EXIT_INPUT_REFUSED and "not_found" in err


def test_a_symlinked_root_is_not_followed(tmp_path, capsys):
    root = _small_corpus(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(root, target_is_directory=True)
    code, _, err = _run(capsys, "import", str(link), "--out", str(tmp_path / "out"))
    assert code == cli.EXIT_INPUT_REFUSED and "symlink_root" in err


def test_a_symlink_escaping_the_root_is_refused_and_listed(tmp_path, capsys):
    root = _small_corpus(tmp_path)
    secret = tmp_path / "outside-secret.txt"
    secret.write_text("SYNTHETIC SECRET THAT MUST NOT BE READ")
    (root / "escape.txt").symlink_to(secret)
    (root / "escape_dir").symlink_to(tmp_path, target_is_directory=True)
    out = tmp_path / "out"
    code, _, _ = _run(capsys, "import", str(root), "--out", str(out))
    assert code == 0
    unread = json.loads((out / "unread_files.json").read_text())["unread_files"]
    assert {u["reason_code"] for u in unread if u["relative_path"] in {"escape.txt", "escape_dir"}} == {"symlink"}
    for name in cli.BUNDLE_FILES:
        assert "MUST NOT BE READ" not in (out / name).read_text(encoding="utf-8")


def test_zip_slip_and_absolute_members_are_refused_and_their_names_withheld(tmp_path, capsys):
    archive = tmp_path / "crafted.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("corpus/ok.txt", "SYNTHETIC readme")
        zf.writestr("corpus/../../evil.txt", "x")
        zf.writestr("/etc/evil.txt", "x")
    out = tmp_path / "out"
    code, _, _ = _run(capsys, "import", str(archive), "--out", str(out))
    assert code == 0
    assert not (tmp_path / "evil.txt").exists() and not (tmp_path.parent / "evil.txt").exists()
    bundle = json.loads((out / "bundle.json").read_text())
    codes = {u["reason_code"] for u in bundle["unread_files"]}
    assert {"path_traversal", "absolute_path"} <= codes
    text = (out / "bundle.json").read_text()
    assert "/etc/evil.txt" not in text and "../../evil.txt" not in text
    assert B.validate_bundle(bundle) == []


def test_a_decompression_bomb_member_is_refused(tmp_path, capsys):
    archive = tmp_path / "bomb.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(zipfile.ZipInfo("c/zeros.txt"), b"\0" * 6_000_000, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        zf.writestr("c/ok.txt", "SYNTHETIC")
    out = tmp_path / "out"
    assert _run(capsys, "import", str(archive), "--out", str(out))[0] == 0
    unread = json.loads((out / "unread_files.json").read_text())["unread_files"]
    assert any(u["reason_code"] == "compression_ratio" for u in unread)


def test_the_entry_count_ceiling_stops_the_walk_and_says_so(tmp_path, capsys):
    root = tmp_path / "many"
    root.mkdir()
    for i in range(5_001):
        (root / f"f{i:05d}.txt").write_text("a")
    out = tmp_path / "out"
    assert _run(capsys, "import", str(root), "--out", str(out))[0] == 0
    bundle = json.loads((out / "bundle.json").read_text())
    assert bundle["source_root"]["truncated_reason"] == "too_many_entries"
    assert bundle["source_root"]["entry_count"] == 5_000
    assert "walk stopped" in (out / "summary.md").read_text()


def test_macros_are_never_executed(tmp_path, capsys, monkeypatch):
    root = _small_corpus(tmp_path)
    sentinel = tmp_path / "SENTINEL_EXECUTED"
    (root / "dangerous.mac").write_text(
        "def boom '{\n"
        f'  unix("touch {sentinel}")\n'
        f"  `touch {sentinel}`\n"
        f"  $(touch {sentinel})\n"
        "  newfile 99_99_ZZ9_never_real\n"
        "}'\n"
    )

    def refuse(*_a, **_k):  # any attempt to run something fails the test loudly
        raise AssertionError("a process was started during import")

    for name in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, refuse)
    for name in ("system", "popen", "execv", "execvp", "spawnv"):
        monkeypatch.setattr(os, name, refuse)
    out = tmp_path / "out"
    assert _run(capsys, "import", str(root), "--out", str(out))[0] == 0
    assert not sentinel.exists()
    bundle = json.loads((out / "bundle.json").read_text())
    macro = next(s for s in bundle["sources"] if s["relative_path"] == "dangerous.mac")
    assert macro["classification"]["source_type"].endswith("macro")
    assert macro["reader"]["content_read"] is True  # read as TEXT


# --- output directory safety -------------------------------------------------------------


def test_a_non_empty_out_is_refused_without_force(tmp_path, capsys):
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.txt").write_text("mine")
    code, _, err = _run(capsys, "import", str(SEMANTICS), "--out", str(out))
    assert code == cli.EXIT_OUTPUT_REFUSED and "--force" in err
    assert sorted(p.name for p in out.iterdir()) == ["keep.txt"]
    code, _, _ = _run(capsys, "import", str(SEMANTICS), "--out", str(out), "--force")
    assert code == 0
    assert (out / "keep.txt").read_text() == "mine"  # --force deletes nothing
    assert (out / "bundle.json").is_file()


def test_out_inside_the_source_folder_is_refused(tmp_path, capsys):
    root = _small_corpus(tmp_path)
    code, _, err = _run(capsys, "import", str(root), "--out", str(root / "bundle"))
    assert code == cli.EXIT_OUTPUT_REFUSED and "inside the folder" in err


def test_an_unknown_profile_is_a_usage_error(tmp_path, capsys):
    code, _, err = _run(capsys, "import", str(SEMANTICS), "--out", str(tmp_path / "o"), "--profile", "nope")
    assert code == cli.EXIT_USAGE and "ssrl_bl152_herfd_echem_naming" in err


def test_naming_the_default_profile_reads_exactly_as_auto(tmp_path, capsys):
    a, b = tmp_path / "a", tmp_path / "b"
    assert _run(capsys, "import", str(SEMANTICS), "--out", str(a))[0] == 0
    assert _run(capsys, "import", str(SEMANTICS), "--out", str(b), "--profile", "ssrl_bl152_herfd_echem_naming")[0] == 0
    ja, jb = (json.loads((d / "bundle.json").read_text()) for d in (a, b))
    assert ja["candidates"] == jb["candidates"] and ja["runs"] == jb["runs"]


# --- bundle list / show / check ------------------------------------------------------------


def test_list_is_paginated_and_reports_what_it_omitted(imported, capsys):
    out, bundle = imported
    code, stdout, _ = _run(capsys, "bundle", "list", str(out), "candidates", "--limit", "5", "--offset", "10")
    assert code == 0
    page = json.loads(stdout)
    total = len(bundle["candidates"])
    assert page["total"] == total and page["returned"] == 5
    assert page["omitted_before"] == 10 and page["omitted_after"] == total - 15
    assert [i["candidate_id"] for i in page["items"]] == [c["candidate_id"] for c in bundle["candidates"][10:15]]
    code, stdout, _ = _run(capsys, "bundle", "list", str(out), "candidates", "--state", "conflicting", "--limit", "200")
    filtered = json.loads(stdout)
    assert filtered["total"] == bundle["counts"]["conflicting_candidates"]
    assert _run(capsys, "bundle", "list", str(out), "runs", "--limit", "999")[0] == cli.EXIT_USAGE


@pytest.mark.parametrize("kind", cli.LIST_KINDS)
def test_every_list_kind_works(imported, capsys, kind):
    out, _ = imported
    code, stdout, _ = _run(capsys, "bundle", "list", str(out), kind)
    assert code == 0 and "total" in json.loads(stdout)


def test_show_returns_one_object_or_not_found(imported, capsys):
    out, bundle = imported
    for kind, section, key in (
        ("run", "runs", "run_id"),
        ("conflict", "conflicts", "conflict_id"),
        ("candidate", "candidates", "candidate_id"),
        ("source", "sources", "source_id"),
        ("question", "questions", "question_id"),
    ):
        obj = bundle[section][0]
        code, stdout, _ = _run(capsys, "bundle", "show", str(out), kind, obj[key])
        assert code == 0 and json.loads(stdout) == obj
    code, _, err = _run(capsys, "bundle", "show", str(out), "run", "run-999")
    assert code == cli.EXIT_NOT_FOUND and "run-999" in err
    assert _run(capsys, "bundle", "show", str(out / "nowhere"), "run", "run-001")[0] == cli.EXIT_NOT_FOUND


def test_check_refuses_a_tampered_bundle(imported, tmp_path, capsys):
    out, bundle = imported
    tampered = json.loads(json.dumps(bundle))
    target = next(c for c in tampered["candidates"] if c["value_state"] == "candidate_extracted")
    target["value_state"] = "scientist_confirmed"
    (tmp_path / "bundle.json").write_bytes(B.encode(tampered))
    code, stdout, _ = _run(capsys, "bundle", "check", str(tmp_path))
    assert code == cli.EXIT_INVALID and "INVALID" in stdout and target["candidate_id"] in stdout
    code, stdout, _ = _run(capsys, "bundle", "check", str(out))
    assert code == 0 and "VALID" in stdout


# --- the `isaac` entry point -------------------------------------------------------------------


def test_isaac_dispatches_import_and_bundle(tmp_path, capsys):
    from isaac_records import cli as isaac_cli

    out = tmp_path / "out"
    assert isaac_cli.main(["import", str(SEMANTICS), "--out", str(out)]) == 0
    capsys.readouterr()
    assert isaac_cli.main(["bundle", "check", str(out)]) == 0
    assert "VALID" in capsys.readouterr().out
    # also through the parser path (a leading global option)
    assert isaac_cli.main(["--root", str(REPO_ROOT), "bundle", "check", str(out)]) == 0


def test_isaac_existing_subcommands_are_unchanged(capsys):
    """Real outputs, not just "an exit code in (0, 1)" (review minor)."""
    from isaac_records import cli as isaac_cli
    from isaac_records.ids import is_record_id

    assert isaac_cli.main(["new-id"]) == 0
    assert is_record_id(capsys.readouterr().out.strip())
    valid = REPO_ROOT / "tests" / "fixtures" / "official" / "dft_neb_evidence_record.json"
    assert isaac_cli.main(["--root", str(REPO_ROOT), "validate", str(valid), "--official"]) == 0
    assert capsys.readouterr().out.startswith("PASS — valid against official ISAAC schema v1.05")
    draft = REPO_ROOT / "tests" / "fixtures" / "cuo_xanes_draft.json"
    code = isaac_cli.main(["--root", str(REPO_ROOT), "validate", str(draft), "--draft"])
    out = capsys.readouterr().out
    assert out.startswith("Draft validation (no-guessing checks):")
    assert code in (0, 1)  # the fixture's own verdict, unchanged by this slice
    with pytest.raises(SystemExit) as raised:
        isaac_cli.main(["no-such-command"])
    assert raised.value.code == 2


def _site_packages() -> str:
    import sysconfig

    return sysconfig.get_paths()["purelib"]


def test_isaac_import_without_the_api_package_prints_one_instruction(tmp_path):
    """Runs with a CLEAN sys.path (``-S``: no site, so no .pth file can add apps/api),
    so it cannot be skipped by an installed .pth (review minor)."""
    code = (
        "import sys; "
        f"sys.path[:0] = [{str(REPO_ROOT / 'src')!r}, {_site_packages()!r}]; "
        "from isaac_records.cli import main; sys.exit(main(['import', 'x', '--out', 'y']))"
    )
    done = subprocess.run(
        [sys.executable, "-S", "-c", code], capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin"}, cwd=str(tmp_path), timeout=60,
    )
    assert done.returncode == 2, done.stderr
    assert "install_local_cli.sh" in done.stderr
    assert len(done.stderr.strip().splitlines()) == 1
