"""``scripts/setup_isaac_local.sh``: the skill notices it is out of date and updates itself.

Two levels: the installed skill copy differs from the checkout's (``[stale]``), and the checkout is behind GitHub's
``main`` (``[behind N commits]``, from a ``git fetch`` that never fails the check). ``--update`` fast-forwards only, and
refuses with local changes, on another branch or diverged. Everything runs on TEMPORARY git repositories with a local
bare ``origin``: no network. The checkout is a minimal SYN copy carrying the real script.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "setup_isaac_local.sh"
SKILL = ".claude/skills/isaac-historical-import"

pytestmark = pytest.mark.skipif(shutil.which("git") is None or shutil.which("bash") is None, reason="needs git and bash")


def _env(home: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(HOME=str(home), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="SYN",
               GIT_AUTHOR_EMAIL="syn@example.invalid", GIT_COMMITTER_NAME="SYN", GIT_COMMITTER_EMAIL="syn@example.invalid",
               ISAAC_FETCH_TIMEOUT="5")
    return env


def _git(cwd: Path, *args: str, env: dict) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], env=env, check=True, capture_output=True, text=True).stdout.strip()


def _commit(repo: Path, rel: str, text: str, env: dict) -> None:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(text)
    _git(repo, "add", "-A", env=env)
    _git(repo, "commit", "-q", "-m", f"SYN {rel}", env=env)


@pytest.fixture()
def world(tmp_path):
    """``(checkout, upstream working clone, env)``: a SYN ISAAC folder cloned from a local bare ``origin``."""
    home = tmp_path / "home"
    home.mkdir()
    env = _env(home)
    up = tmp_path / "upstream"
    up.mkdir()
    _git(up, "init", "-q", "-b", "main", env=env)
    (up / "schema").mkdir()
    (up / "schema" / "isaac_record_v1.json").write_text("{}\n")
    (up / "apps" / "api" / "isaac_api").mkdir(parents=True)
    (up / "apps" / "api" / "isaac_api" / "__init__.py").write_text("")
    (up / "scripts").mkdir()
    shutil.copy2(SCRIPT, up / "scripts" / "setup_isaac_local.sh")
    (up / "pyproject.toml").write_text("[project]\nname = 'syn'\n")
    (up / SKILL).mkdir(parents=True)
    (up / SKILL / "SKILL.md").write_text("SYN skill v1\n")
    _git(up, "add", "-A", env=env)
    _git(up, "commit", "-q", "-m", "SYN v1", env=env)
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(up), str(bare)], env=env, check=True)
    _git(up, "remote", "add", "origin", str(bare), env=env)
    co = tmp_path / "ISAAC"
    subprocess.run(["git", "clone", "-q", str(bare), str(co)], env=env, check=True)
    return co, up, env


def _run(co: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(co / "scripts" / "setup_isaac_local.sh"), *args], env=env, capture_output=True,
                          text=True, timeout=120)


def _line(out: str, word: str) -> str:
    [line] = [x for x in out.splitlines() if "update check" in x and word in x] or [""]
    return line


def _push(up: Path, env: dict, n: int = 2) -> None:
    for k in range(n):
        _commit(up, f"{SKILL}/SKILL.md", f"SYN skill v{k + 2}\n", env)
    _git(up, "push", "-q", "origin", "main", env=env)


def test_up_to_date_is_ok(world):
    co, _, env = world
    out = _run(co, env, "--check").stdout
    assert _line(out, "[ok]").startswith("[ok] update check")


def test_behind_says_how_many_and_how_to_update(world):
    co, up, env = world
    _push(up, env, 3)
    head = _git(co, "rev-parse", "HEAD", env=env)
    out = _run(co, env, "--check").stdout
    line = _line(out, "[behind 3 commits]")
    assert line.startswith("[behind 3 commits]") and "scripts/setup_isaac_local.sh --update" in line
    assert "it would refuse" not in line
    assert _git(co, "rev-parse", "HEAD", env=env) == head  # --check changes no file: only the remote ref moved
    assert (co / SKILL / "SKILL.md").read_text() == "SYN skill v1\n"


def test_offline_is_skipped_and_never_fails_the_check(world):
    co, _, env = world
    _git(co, "remote", "set-url", "origin", str(co.parent / "nowhere.git"), env=env)
    done = _run(co, env, "--check")
    assert _line(done.stdout, "[skipped]").startswith("[skipped] update check  could not reach GitHub")
    assert "update check" not in done.stderr
    assert "[skipped] update check  --offline" in _run(co, env, "--check", "--offline").stdout


def test_a_hanging_github_is_cut_off_and_skipped(world):
    co, _, env = world
    env = {**env, "ISAAC_FETCH_TIMEOUT": "1", "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "protocol.ext.allow",
           "GIT_CONFIG_VALUE_0": "always"}
    _git(co, "remote", "set-url", "origin", "ext::sleep 30", env=env)
    start = time.monotonic()
    out = _run(co, env, "--check").stdout
    assert time.monotonic() - start < 20
    assert _line(out, "[skipped]").startswith("[skipped] update check  GitHub did not answer within 1s")


def test_not_a_git_checkout_is_skipped(world, tmp_path):
    co, _, env = world
    plain = tmp_path / "plain"
    shutil.copytree(co, plain, ignore=shutil.ignore_patterns(".git"))
    assert "[skipped] update check  not a git checkout" in _run(plain, env, "--check").stdout
    done = _run(plain, env, "--update")
    assert done.returncode == 3 and "not a git checkout" in done.stderr


def test_a_stale_installed_copy_is_said(world):
    co, _, env = world
    assert _run(co, env, "--install-skill", "--skip-cli", "--skip-portal", "--offline").returncode in (0, 1)
    installed = Path(env["HOME"]) / ".claude" / "skills" / "isaac-historical-import"
    assert (installed / "SKILL.md").read_text() == "SYN skill v1\n"
    assert "[ok] skill installed" in _run(co, env, "--check", "--offline").stdout
    (installed / "SKILL.md").write_text("SYN skill v0 (old)\n")
    assert "[stale] skill at" in _run(co, env, "--check", "--offline").stdout


def test_update_fast_forwards_and_reinstalls_the_skill(world):
    co, up, env = world
    _push(up, env, 2)
    done = _run(co, env, "--update")
    assert "Updated 2 commits" in done.stdout and "code only; no data was touched" in done.stdout
    assert _git(co, "rev-parse", "HEAD", env=env) == _git(up, "rev-parse", "HEAD", env=env)
    installed = Path(env["HOME"]) / ".claude" / "skills" / "isaac-historical-import"
    assert (installed / "SKILL.md").read_text() == "SYN skill v3\n"
    assert (installed / "checkout-path.txt").read_text().strip() == str(co)
    assert "[ok] update check" in _run(co, env, "--check").stdout


def test_update_refuses_local_changes(world):
    co, up, env = world
    _push(up, env)
    (co / SKILL / "SKILL.md").write_text("SYN skill edited here\n")
    head = _git(co, "rev-parse", "HEAD", env=env)
    assert "it would refuse now: this folder has local changes" in _run(co, env, "--check").stdout
    done = _run(co, env, "--update")
    assert done.returncode == 3 and "local changes" in done.stderr and "Nothing was changed" in done.stderr
    assert _git(co, "rev-parse", "HEAD", env=env) == head
    assert (co / SKILL / "SKILL.md").read_text() == "SYN skill edited here\n"


def test_update_refuses_another_branch(world):
    co, up, env = world
    _push(up, env)
    _git(co, "checkout", "-q", "-b", "syn-work", env=env)
    done = _run(co, env, "--update")
    assert done.returncode == 3 and 'branch "syn-work", not main' in done.stderr
    assert _git(co, "symbolic-ref", "--short", "HEAD", env=env) == "syn-work"


def test_update_refuses_a_diverged_folder(world):
    co, up, env = world
    _push(up, env)
    _commit(co, "notes.txt", "SYN local commit\n", env)
    head = _git(co, "rev-parse", "HEAD", env=env)
    done = _run(co, env, "--update")
    assert done.returncode == 3 and "1 local commit(s)" in done.stderr and "diverged" in done.stderr
    assert _git(co, "rev-parse", "HEAD", env=env) == head


def test_update_offline_refuses_and_changes_nothing(world):
    co, _, env = world
    _git(co, "remote", "set-url", "origin", str(co.parent / "nowhere.git"), env=env)
    done = _run(co, env, "--update")
    assert done.returncode == 3 and "could not reach GitHub" in done.stderr


# --- --update never replaces a file git does not track (examples/ is where scientists' data lives) -----------------


def _ship_a_file_over_local_data(co: Path, up: Path, env: dict, *, ignored: bool) -> Path:
    """Upstream (force-)adds ``examples/scan.xdi``; this folder already holds its own file at that path."""
    if ignored:
        _commit(up, ".gitignore", "examples/\n", env)
        _git(up, "push", "-q", "origin", "main", env=env)
        _git(co, "pull", "-q", "--ff-only", env=env)
    data = co / "examples" / "scan.xdi"
    data.parent.mkdir(parents=True, exist_ok=True)
    data.write_text("SYN scientist's own data, never in git\n")
    (up / "examples").mkdir(exist_ok=True)
    (up / "examples" / "scan.xdi").write_text("SYN upstream file\n")
    _git(up, "add", "-f", "examples/scan.xdi", env=env)
    _git(up, "commit", "-q", "-m", "SYN ships examples/scan.xdi", env=env)
    _git(up, "push", "-q", "origin", "main", env=env)
    return data


def test_plain_git_would_replace_an_ignored_data_file(world, tmp_path):
    """The hazard itself, measured: a plain ``git merge --ff-only`` replaces an IGNORED file and exits 0."""
    co, up, env = world
    data = _ship_a_file_over_local_data(co, up, env, ignored=True)
    _git(co, "fetch", "-q", "origin", env=env)
    subprocess.run(["git", "-C", str(co), "merge", "--ff-only", "-q", "origin/main"], env=env, check=True, capture_output=True)
    assert data.read_text() == "SYN upstream file\n"  # the scientist's file is gone, with no word from git


@pytest.mark.parametrize("ignored", [True, False], ids=["ignored", "untracked"])
def test_update_refuses_to_replace_a_file_git_does_not_track(world, ignored):
    co, up, env = world
    data = _ship_a_file_over_local_data(co, up, env, ignored=ignored)
    head = _git(co, "rev-parse", "HEAD", env=env)
    check = _run(co, env, "--check").stdout
    assert "it would refuse now: the update adds its own files where this folder holds 1 file(s)" in _line(check, "[behind")
    done = _run(co, env, "--update")
    assert done.returncode == 3, done.stdout + done.stderr
    assert "git does not track" in done.stderr and "(in: examples/)" in done.stderr and "Nothing was changed" in done.stderr
    assert "scan.xdi" not in done.stderr  # a data file's name is never printed, only its folder
    assert data.read_text() == "SYN scientist's own data, never in git\n"
    assert _git(co, "rev-parse", "HEAD", env=env) == head


def test_a_root_level_collision_names_the_top_folder_not_the_file(world):
    co, up, env = world
    (co / "SYN_private_sample_name.dat").write_text("SYN scientist's own file\n")
    _commit(up, "SYN_private_sample_name.dat", "SYN upstream file\n", env)
    _git(up, "push", "-q", "origin", "main", env=env)
    done = _run(co, env, "--update")
    assert done.returncode == 3 and "(in: the top folder)" in done.stderr
    assert "SYN_private_sample_name" not in done.stderr + done.stdout
    assert "diff --name-only" not in done.stderr  # no command that would list every added path
    assert (co / "SYN_private_sample_name.dat").read_text() == "SYN scientist's own file\n"


def _case_insensitive(where: Path) -> bool:
    probe = where / "SYN_Case_Probe"
    probe.write_text("")
    try:
        return (where / "syn_case_probe").exists()
    finally:
        probe.unlink()


def test_a_case_only_rename_upstream_is_not_refused(world, tmp_path):
    co, up, env = world
    if not _case_insensitive(tmp_path):
        pytest.skip("needs a case-insensitive disk (the default on macOS)")
    _commit(up, "SYN_Notes.txt", "SYN tracked\n", env)
    _git(up, "push", "-q", "origin", "main", env=env)
    _git(co, "pull", "-q", "--ff-only", env=env)
    _git(up, "mv", "SYN_Notes.txt", "syn_notes.txt", env=env)
    _git(up, "commit", "-q", "-m", "SYN case-only rename", env=env)
    _git(up, "push", "-q", "origin", "main", env=env)
    line = _line(_run(co, env, "--check").stdout, "[behind")
    assert line and "it would refuse" not in line, line


def test_a_tracked_file_that_becomes_a_folder_is_not_refused(world):
    co, up, env = world
    _commit(up, "SYN_layout", "SYN a file for now\n", env)
    _git(up, "push", "-q", "origin", "main", env=env)
    _git(co, "pull", "-q", "--ff-only", env=env)
    _git(up, "rm", "-q", "SYN_layout", env=env)
    _commit(up, "SYN_layout/inner.txt", "SYN now a folder\n", env)
    _git(up, "push", "-q", "origin", "main", env=env)
    done = _run(co, env, "--update")
    assert done.returncode == 0, done.stdout + done.stderr
    assert (co / "SYN_layout" / "inner.txt").read_text() == "SYN now a folder\n"


def test_update_merges_with_no_overwrite_ignore():
    """The second lock: even past the check, git itself refuses to replace an ignored file."""
    text = SCRIPT.read_text()
    assert "merge --ff-only --no-overwrite-ignore" in text and "merge --ff-only --quiet" not in text


# --- the GitHub check: no orphan process, the user's ssh setup, plain reasons ----------------------------------------


def _alive(pattern: str) -> list[str]:
    done = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
    return done.stdout.split()


@pytest.mark.skipif(shutil.which("pgrep") is None, reason="needs pgrep")
def test_a_timeout_leaves_no_network_process_running(world):
    co, _, env = world
    marker = "61.37"  # a sleep no other process runs
    env = {**env, "ISAAC_FETCH_TIMEOUT": "1", "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "protocol.ext.allow",
           "GIT_CONFIG_VALUE_0": "always"}
    _git(co, "remote", "set-url", "origin", f"ext::sleep {marker}", env=env)
    assert not _alive(f"sleep {marker}")
    out = _run(co, env, "--check").stdout
    assert "GitHub did not answer within 1s" in out
    deadline = time.monotonic() + 5
    while _alive(f"sleep {marker}") and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not _alive(f"sleep {marker}"), "the fetch's helper outlived the timeout"


def _recorder(path: Path, log: Path) -> Path:
    path.write_text(f"#!/bin/sh\necho \"$0 $* ASKPASS=$GIT_ASKPASS\" >> '{log}'\nexit 1\n")
    path.chmod(0o755)
    return path


def test_ssh_is_told_not_to_prompt_when_nothing_is_configured(world, tmp_path):
    co, _, env = world
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "ssh.log"
    _recorder(bin_dir / "ssh", log)
    env = {**env, "PATH": f"{bin_dir}:{env['PATH']}"}
    _git(co, "remote", "set-url", "origin", "ssh://syn.invalid/syn.git", env=env)
    out = _run(co, env, "--check").stdout
    said = log.read_text()
    assert "BatchMode=yes" in said and "ConnectTimeout=" in said
    assert "ASKPASS=/usr/bin/true" in said or "ASKPASS=/bin/true" in said  # prints nothing, never a password
    assert _line(out, "[skipped]").startswith("[skipped] update check  could not reach GitHub")


def test_the_users_own_ssh_command_wins(world, tmp_path):
    co, _, env = world
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    plain_log, own_log = tmp_path / "plain.log", tmp_path / "own.log"
    _recorder(bin_dir / "ssh", plain_log)
    own = _recorder(tmp_path / "my-ssh", own_log)
    env = {**env, "PATH": f"{bin_dir}:{env['PATH']}"}
    _git(co, "remote", "set-url", "origin", "ssh://syn.invalid/syn.git", env=env)
    _git(co, "config", "core.sshCommand", str(own), env=env)
    out = _run(co, env, "--check").stdout
    assert own_log.exists() and "BatchMode" not in own_log.read_text()
    assert not plain_log.exists()
    line = _line(out, "[skipped]")
    assert "passphrase prompt cannot be shown" in line and "--offline" in line


def _ext_env(env: dict, timeout: str) -> dict:
    return {**env, "ISAAC_FETCH_TIMEOUT": timeout, "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "protocol.ext.allow",
            "GIT_CONFIG_VALUE_0": "always"}


def test_a_fetch_killed_by_something_else_is_not_called_a_timeout(world, tmp_path):
    """git dying of a TERM it did not get from the watcher exits 143: that is not "did not answer"."""
    co, _, env = world
    killer = tmp_path / "syn-kill-parent"
    killer.write_text("#!/bin/sh\nkill -TERM $PPID\nsleep 53.71\n")
    killer.chmod(0o755)
    env = _ext_env(env, "30")
    _git(co, "remote", "set-url", "origin", f"ext::{killer}", env=env)
    line = _line(_run(co, env, "--check").stdout, "[skipped]")
    assert line.startswith("[skipped] update check  could not reach GitHub") and "did not answer" not in line
    if shutil.which("pgrep"):
        time.sleep(0.5)
        assert not _alive("sleep 53.71"), "git's helper outlived git"


@pytest.mark.skipif(shutil.which("pgrep") is None, reason="needs pgrep")
@pytest.mark.parametrize("sig, status", [("SIGINT", 130), ("SIGTERM", 143), ("SIGHUP", 129)])
def test_stopping_the_check_leaves_no_network_process(world, sig, status):
    """Ctrl-C reaches the script's whole process group (as a terminal sends it), never the fetch's own group:
    the script must kill that group itself, and stop with the usual status."""
    import signal

    co, _, env = world
    marker = {"SIGINT": "71.13", "SIGTERM": "71.17", "SIGHUP": "71.19"}[sig]
    env = _ext_env(env, "60")
    _git(co, "remote", "set-url", "origin", f"ext::sleep {marker}", env=env)
    proc = subprocess.Popen(["bash", str(co / "scripts" / "setup_isaac_local.sh"), "--check"], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        deadline = time.monotonic() + 20
        while not _alive(f"sleep {marker}") and time.monotonic() < deadline:
            time.sleep(0.1)
        assert _alive(f"sleep {marker}"), "the fetch never started"
        os.killpg(proc.pid, getattr(signal, sig))
        proc.wait(timeout=15)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
    assert proc.returncode == status
    deadline = time.monotonic() + 5
    while _alive(f"sleep {marker}") and time.monotonic() < deadline:
        time.sleep(0.2)
    leftover = _alive(f"sleep {marker}")
    for pid in leftover:
        os.kill(int(pid), signal.SIGKILL)
    assert not leftover, f"{sig} left the fetch's helper running"


def test_an_origin_without_main_is_said_plainly(world, tmp_path):
    co, up, env = world
    fork = tmp_path / "fork.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "trunk", str(fork)], env=env, check=True)
    _git(up, "push", "-q", str(fork), "main:trunk", env=env)
    _git(co, "remote", "set-url", "origin", str(fork), env=env)
    line = _line(_run(co, env, "--check").stdout, "[skipped]")
    assert "has no 'main' branch to compare with (a fork or another repository?)" in line
    done = _run(co, env, "--update")
    assert done.returncode == 3 and "has no 'main' branch" in done.stderr


def test_a_fork_is_named_and_a_token_in_its_url_never_printed(world):
    co, up, env = world
    out = _run(co, env, "--check").stdout
    assert "not github.com/ISAAC-DOE/isaac-metadata-assistant" in _line(out, "[ok]")
    canonical = "https://syn-token@github.com/ISAAC-DOE/isaac-metadata-assistant.git"
    _git(co, "config", f"url.{co.parent / 'origin.git'}.insteadOf", canonical, env=env)
    _git(co, "remote", "set-url", "origin", canonical, env=env)
    line = _line(_run(co, env, "--check").stdout, "[ok]")
    assert line.startswith("[ok] update check") and "not github.com" not in line
    _git(co, "remote", "set-url", "origin", "https://syn-token@syn.invalid/x.git", env=env)
    out = _run(co, env, "--check").stdout
    assert "syn-token" not in out and "https://syn.invalid/x.git" in out


def test_a_bad_fetch_timeout_is_the_default(world):
    co, _, env = world
    done = _run(co, {**env, "ISAAC_FETCH_TIMEOUT": "fifteen; rm -rf /"}, "--check")
    assert _line(done.stdout, "[ok]").startswith("[ok] update check") and "syntax error" not in done.stderr


def test_check_never_updates(world):
    co, up, env = world
    _push(up, env)
    head = _git(co, "rev-parse", "HEAD", env=env)
    for extra in ("--update", "--refresh-skill", "--install-skill"):
        done = _run(co, env, "--check", extra)
        assert done.returncode == 2 and "--check changes nothing" in done.stderr
    assert _git(co, "rev-parse", "HEAD", env=env) == head


# --- --refresh-skill: the skill copy and nothing else --------------------------------------------------------------


def test_refresh_skill_copies_only_the_skill_and_says_where(world, tmp_path):
    co, _, env = world
    target = tmp_path / "project" / ".claude" / "skills"
    done = _run(co, env, "--refresh-skill", "--skill-dir", str(target))
    assert done.returncode == 0, done.stdout + done.stderr
    assert f"Skill written to: {target}/isaac-historical-import/SKILL.md" in done.stdout
    assert (target / "isaac-historical-import" / "SKILL.md").read_text() == "SYN skill v1\n"
    assert not (co / ".venv").exists()  # no Python environment, no package download
    assert "== 1/4" not in done.stdout and "== 2/4" not in done.stdout and "== 3/4" not in done.stdout
    assert "update check" not in done.stdout  # no network


def test_a_stale_copy_elsewhere_is_told_the_refresh_for_its_own_folder(world, tmp_path):
    co, _, env = world
    target = tmp_path / "project skills"
    _run(co, env, "--refresh-skill", "--skill-dir", str(target))
    (target / "isaac-historical-import" / "SKILL.md").write_text("SYN skill v0 (old)\n")
    out = _run(co, env, "--check", "--offline", "--skill-dir", str(target)).stdout
    assert f'--refresh-skill --skill-dir "{target}"' in out and "--install-skill" not in out.split("[stale]")[1].split("\n")[0]


def test_refresh_never_removes_the_checkouts_own_skill(world):
    co, _, env = world
    own = co / ".claude" / "skills"
    done = _run(co, env, "--refresh-skill", "--skill-dir", str(own))
    assert done.returncode == 0 and "this checkout's own copy" in done.stdout
    assert (own / "isaac-historical-import" / "SKILL.md").read_text() == "SYN skill v1\n"
    assert "[ok] skill at" in _run(co, env, "--check", "--offline", "--skill-dir", str(own)).stdout


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads an unreadable file")
def test_a_failed_refresh_keeps_the_old_copy_and_leaves_no_temp_folder(world, tmp_path):
    co, _, env = world
    target = tmp_path / "skills"
    assert _run(co, env, "--refresh-skill", "--skill-dir", str(target)).returncode == 0
    (target / "isaac-historical-import" / "SKILL.md").write_text("SYN skill v0 (old)\n")
    blocked = co / SKILL / "SYN_unreadable.md"
    blocked.write_text("SYN\n")
    blocked.chmod(0)
    try:
        done = _run(co, env, "--refresh-skill", "--skill-dir", str(target))
    finally:
        blocked.chmod(0o644)
    assert done.returncode == 1 and "the installed copy is unchanged" in done.stderr
    assert (target / "isaac-historical-import" / "SKILL.md").read_text() == "SYN skill v0 (old)\n"
    assert sorted(p.name for p in target.iterdir()) == ["isaac-historical-import"]  # no temp or .old folder
