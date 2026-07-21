"""Tests for ``scripts/isaac_preflight.py`` — the deterministic first-push
preflight (R4.3) that prevents predictable failed pushes (e.g. committed-snapshot
drift, the a0446fe class of failure).

Loaded via ``importlib.util.spec_from_file_location`` (``scripts/`` is not a
package), the same pattern ``test_build_memory_snapshot.py`` and
``test_committed_snapshot.py`` use.

Offline + deterministic: git-topology tests build a throwaway repo with a LOCAL
bare "origin" (a filesystem path, never the network); the snapshot-check tests
reuse the committed synthetic fixture graph + golden snapshot. The real
``git fetch`` is only ever exercised with ``skip=True``.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "isaac_preflight.py"

# Committed synthetic fixture graph + golden snapshot (also used by
# test_build_memory_snapshot.py). served_root supplies the manifest bytes.
_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "memory_snapshot"
_FIXTURE_GRAPH = _FIXTURE / "graph"
_GOLDEN_SNAPSHOT = _FIXTURE / "memory-snapshot.json"
_SERVED_ROOT = _FIXTURE / "served_root"


def _load():
    spec = importlib.util.spec_from_file_location("isaac_preflight", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass can resolve the module in sys.modules.
    sys.modules["isaac_preflight"] = module
    spec.loader.exec_module(module)
    return module


pf = _load()


# --- git repo helpers (local bare origin; fully offline) ----------------------


def _run(cwd, *args):
    proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc.stdout


def _make_repo(tmp_path) -> Path:
    """Create a bare origin whose path contains the expected ISAAC substring,
    plus a working clone on ``main`` with the ISAAC marker file committed and
    pushed. Returns the working-clone path."""
    origin = tmp_path / "isaac-metadata-assistant.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)],
                   check=True, capture_output=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", str(origin), str(work)], check=True, capture_output=True)
    _run(work, "config", "user.email", "t@example.com")
    _run(work, "config", "user.name", "Test")
    # ISAAC marker so check_repo_identity recognizes the repo.
    (work / "schema").mkdir()
    (work / "schema" / "isaac_record_v1.json").write_text("{}\n")
    _run(work, "add", "-A")
    _run(work, "commit", "-m", "init")
    _run(work, "push", "-u", "origin", "main")
    return work


def _commit_ahead(work, rel, content):
    """Add + commit ``rel`` locally so it sits in a commit AHEAD of origin, with
    a CLEAN working tree afterward (mirrors the /isaac-checkpoint push moment)."""
    p = work / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    _run(work, "add", "-A")
    _run(work, "commit", "-m", f"ahead: {rel}")


# --- 1. snapshot check: passes with no drift, never regenerates ---------------


def test_snapshot_check_passes_for_golden_fixture_no_drift():
    before = _GOLDEN_SNAPSHOT.read_bytes()
    result = pf.run_snapshot_check(
        REPO_ROOT,
        graph_dir=_FIXTURE_GRAPH,
        out_path=_GOLDEN_SNAPSHOT,
        snapshot_repo_root=_SERVED_ROOT,
    )
    assert result.severity == "pass", result.detail
    # --check writes nothing: the committed fixture is byte-identical afterward.
    assert _GOLDEN_SNAPSHOT.read_bytes() == before


def test_snapshot_check_fails_on_injected_drift_and_never_regenerates(tmp_path):
    drifted = tmp_path / "memory-snapshot.json"
    # A deliberately-drifted copy of the golden snapshot.
    text = _GOLDEN_SNAPSHOT.read_text(encoding="utf-8")
    drifted.write_text(text.replace("isaac-memory-snapshot", "TAMPERED", 1), encoding="utf-8")
    injected = drifted.read_bytes()

    result = pf.run_snapshot_check(
        REPO_ROOT,
        graph_dir=_FIXTURE_GRAPH,
        out_path=drifted,
        snapshot_repo_root=_SERVED_ROOT,
    )
    assert result.severity == "fail", "drift must fail the preflight"
    assert "drift" in result.detail.lower()
    # CRITICAL: --check must NOT regenerate/repair the drifted file on the push
    # path — the injected (still-drifted) bytes remain exactly as written.
    assert drifted.read_bytes() == injected


def test_snapshot_check_command_is_always_check_mode():
    cmd = pf.snapshot_check_command(REPO_ROOT)
    assert "--check" in cmd, "snapshot check command must always run in --check mode"
    # The command targets the committed snapshot and the live graph dir.
    assert str(pf._SNAPSHOT_BUILDER_REL) in " ".join(cmd)


# --- 2. secret-like / junk filename rejection ---------------------------------


@pytest.mark.parametrize("path", [
    ".env", ".env.production", "config/prod.pem", "certs/server.key",
    "id_rsa", ".npmrc", "deploy/credentials", "app.p12",
])
def test_scan_rejects_secret_like_filenames(path):
    result = pf.scan_changed_filenames([path])
    assert result.severity == "fail"
    assert any(path in ln for ln in result.lines)


@pytest.mark.parametrize("path", [
    ".DS_Store", "debug.log", "scratch.tmp", "src/foo.pyc", "src/__pycache__/x.py",
])
def test_scan_rejects_junk_filenames(path):
    result = pf.scan_changed_filenames([path])
    assert result.severity == "fail"


def test_scan_passes_ordinary_changes():
    result = pf.scan_changed_filenames(["docs/mentor-brief.md", "src/isaac_records/foo.py"])
    assert result.severity == "pass"


# --- 3. content leak scan -----------------------------------------------------


def test_content_leak_scan_detects_private_key(tmp_path):
    # Assemble the marker from fragments so THIS test's own source file does not
    # contain a contiguous secret-shaped string (which the preflight would then
    # correctly flag when this very file is a changed/untracked file to push).
    marker = "-----BEGIN " + "OPENSSH PRIVATE KEY" + "-----"
    rel = "secrets_leaked.txt"
    (tmp_path / rel).write_text(f"{marker}\nabc\n")
    result = pf.content_leak_scan(tmp_path, [("A", " ", rel)])
    assert result.severity == "fail"
    assert any("private-key" in ln for ln in result.lines)


def test_content_leak_scan_detects_github_token(tmp_path):
    rel = "notes.md"
    token = "ghp" + "_" + ("A" * 30)  # fragmented (see note above)
    (tmp_path / rel).write_text(f"token = {token}\n")
    result = pf.content_leak_scan(tmp_path, [("A", " ", rel)])
    assert result.severity == "fail"


def test_content_leak_scan_clean(tmp_path):
    rel = "clean.py"
    (tmp_path / rel).write_text("print('hello world')\n")
    result = pf.content_leak_scan(tmp_path, [("A", " ", rel)])
    assert result.severity == "pass"


def test_content_leak_scan_skips_deleted_files(tmp_path):
    # Deleted file: nothing on disk; must not raise and must pass.
    result = pf.content_leak_scan(tmp_path, [("D", " ", "gone.txt")])
    assert result.severity == "pass"


# --- 4. git identity / branch / divergence (local bare origin) ----------------


def test_repo_identity_ok(tmp_path):
    work = _make_repo(tmp_path)
    assert pf.check_repo_identity(work).severity == "pass"


def test_repo_identity_missing_marker(tmp_path):
    work = _make_repo(tmp_path)
    (work / "schema" / "isaac_record_v1.json").unlink()
    assert pf.check_repo_identity(work).severity == "fail"


def test_branch_ok_and_non_main(tmp_path):
    work = _make_repo(tmp_path)
    assert pf.check_branch(work).severity == "pass"
    _run(work, "checkout", "-b", "feature")
    assert pf.check_branch(work).severity == "fail"


def test_divergence_clean_zero_zero(tmp_path):
    work = _make_repo(tmp_path)
    assert pf.check_divergence(work).severity == "pass"


def test_divergence_ahead_only_passes(tmp_path):
    work = _make_repo(tmp_path)
    (work / "a.txt").write_text("a\n")
    _run(work, "add", "-A")
    _run(work, "commit", "-m", "local ahead")
    result = pf.check_divergence(work)
    assert result.severity == "pass"  # ahead-only is a normal fast-forward push


def test_divergence_behind_fails(tmp_path):
    work = _make_repo(tmp_path)
    # Advance origin/main tracking ref past HEAD, then drop the local commit.
    (work / "b.txt").write_text("b\n")
    _run(work, "add", "-A")
    _run(work, "commit", "-m", "c2")
    _run(work, "push", "origin", "main")  # origin/main now == c2
    _run(work, "reset", "--hard", "HEAD~1")  # HEAD back to c1; behind origin by 1
    result = pf.check_divergence(work)
    assert result.severity == "fail"
    assert "REMOTE_ADVANCED" in result.detail


def test_divergence_diverged_fails(tmp_path):
    work = _make_repo(tmp_path)
    (work / "b.txt").write_text("b\n")
    _run(work, "add", "-A")
    _run(work, "commit", "-m", "c2")
    _run(work, "push", "origin", "main")  # origin/main == c2
    _run(work, "reset", "--hard", "HEAD~1")  # back to c1
    (work / "c.txt").write_text("c\n")
    _run(work, "add", "-A")
    _run(work, "commit", "-m", "c3")  # local now c1->c3, origin c1->c2: diverged
    result = pf.check_divergence(work)
    assert result.severity == "fail"
    assert "DIVERGED" in result.detail


def test_fetch_skip_is_info_not_fail(tmp_path):
    work = _make_repo(tmp_path)
    result = pf.fetch_origin(work, skip=True)
    assert result.severity == "info"


# --- 4b. ahead-of-origin commit coverage (the reviewed false-PASS vector) -----


def test_ahead_commit_files_enumerates_committed_changes(tmp_path):
    work = _make_repo(tmp_path)
    _commit_ahead(work, "src/feature.py", "print('ok')\n")
    assert pf.collect_changes(work) == []  # clean working tree
    paths, err = pf.ahead_commit_files(work)
    assert err is None
    assert "src/feature.py" in paths


def test_ahead_commit_files_fail_closed_without_origin_main(tmp_path):
    # A plain repo with no origin/main ref: enumeration must FAIL closed.
    work = tmp_path / "plain"
    work.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(work)], check=True, capture_output=True)
    _run(work, "config", "user.email", "t@example.com")
    _run(work, "config", "user.name", "Test")
    (work / "a.txt").write_text("a\n")
    _run(work, "add", "-A")
    _run(work, "commit", "-m", "c1")
    paths, err = pf.ahead_commit_files(work)
    assert paths == []
    assert err is not None and "origin/main" in err


def test_content_leak_scan_catches_secret_in_ahead_commit(tmp_path):
    """THE reviewed gap: a credential committed AHEAD of origin with a CLEAN tree.
    Working-tree scan sees nothing; the ahead-commit blob scan must catch it."""
    work = _make_repo(tmp_path)
    token = "ghp" + "_" + ("B" * 30)  # fragmented so THIS file isn't self-flagged
    _commit_ahead(work, "deploy/notes.txt", f"gh_token = {token}\n")
    assert pf.collect_changes(work) == []  # clean tree at push time
    ahead, err = pf.ahead_commit_files(work)
    assert err is None and "deploy/notes.txt" in ahead

    # WITHOUT the fix (ahead_paths omitted → old working-tree-only behavior) the
    # secret sails through — this asserts the exact false-PASS the review found.
    assert pf.content_leak_scan(work, []).severity == "pass"

    # WITH the fix (ahead-commit blobs scanned) it is caught.
    result = pf.content_leak_scan(work, [], ahead_paths=ahead)
    assert result.severity == "fail"
    assert any("deploy/notes.txt" in ln for ln in result.lines)


def test_content_leak_scan_clean_ahead_commit_passes(tmp_path):
    work = _make_repo(tmp_path)
    _commit_ahead(work, "src/feature.py", "print('clean feature')\n")
    ahead, err = pf.ahead_commit_files(work)
    assert err is None
    assert pf.content_leak_scan(work, [], ahead_paths=ahead).severity == "pass"
    assert pf.scan_changed_filenames(ahead).severity == "pass"


def test_scan_filenames_catches_secret_filename_in_ahead_commit(tmp_path):
    work = _make_repo(tmp_path)
    _commit_ahead(work, "config/.env", "SECRET=1\n")
    ahead, err = pf.ahead_commit_files(work)
    assert err is None and "config/.env" in ahead
    assert pf.scan_changed_filenames(ahead).severity == "fail"


def test_run_preflight_full_catches_ahead_commit_secret(monkeypatch, tmp_path):
    """End-to-end: run_preflight (snapshot/gate stubbed to pass, since the
    synthetic repo has no builder) must FAIL on an ahead-commit secret."""
    work = _make_repo(tmp_path)
    token = "AKIA" + ("A" * 16)  # AWS-key-shaped, fragmented literal
    _commit_ahead(work, "infra/keys.txt", f"aws = {token}\n")
    monkeypatch.setattr(pf, "run_snapshot_check", lambda *a, **k: pf._passed("snapshot-check"))
    monkeypatch.setattr(pf, "run_gate_test", lambda *a, **k: pf._passed("snapshot-gate-test"))
    results = pf.run_preflight(work, "full", skip_fetch=True)
    leak = next(r for r in results if r.name == "content-leak-scan")
    assert leak.severity == "fail"
    assert any("infra/keys.txt" in ln for ln in leak.lines)


# --- 5. failure is not masked: any fail => nonzero exit -----------------------


def test_main_returns_nonzero_when_any_check_fails(monkeypatch, capsys):
    mixed = [
        pf._passed("a"),
        pf._failed("b", "boom"),
        pf._info("c"),
    ]
    monkeypatch.setattr(pf, "run_preflight", lambda *a, **k: mixed)
    rc = pf.main(["full", "--skip-fetch"])
    assert rc == pf.EXIT_FAIL
    assert "DO NOT PUSH" in capsys.readouterr().out


def test_main_returns_zero_when_all_pass(monkeypatch, capsys):
    allgood = [pf._passed("a"), pf._info("b"), pf._passed("c")]
    monkeypatch.setattr(pf, "run_preflight", lambda *a, **k: allgood)
    rc = pf.main(["docs", "--skip-fetch"])
    assert rc == pf.EXIT_OK
    assert "PREFLIGHT PASSED" in capsys.readouterr().out


def test_single_failed_result_flips_aggregate(tmp_path):
    # Even a lone failure among many passes must not be masked.
    results = [pf._passed("x") for _ in range(5)] + [pf._failed("y", "z")]
    assert any(r.failed for r in results)


# --- 6. mode differences: snapshot gates are unconditional in every mode ------


def test_all_modes_include_snapshot_and_gate(monkeypatch, tmp_path):
    """The committed-snapshot --check and gate test must be scheduled in EVERY
    mode; only the advisory reminders differ."""
    work = _make_repo(tmp_path)
    calls = {"snapshot": 0, "gate": 0}
    monkeypatch.setattr(pf, "run_snapshot_check",
                        lambda *a, **k: (calls.__setitem__("snapshot", calls["snapshot"] + 1)
                                         or pf._passed("snapshot-check")))
    monkeypatch.setattr(pf, "run_gate_test",
                        lambda *a, **k: (calls.__setitem__("gate", calls["gate"] + 1)
                                         or pf._passed("snapshot-gate-test")))
    for mode in pf.MODES:
        calls["snapshot"] = calls["gate"] = 0
        results = pf.run_preflight(work, mode, skip_fetch=True)
        assert calls["snapshot"] == 1, f"snapshot check not run in mode {mode}"
        assert calls["gate"] == 1, f"gate test not run in mode {mode}"
        names = [r.name for r in results]
        assert "snapshot-check" in names and "snapshot-gate-test" in names
