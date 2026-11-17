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
    assert _line(done.stdout, "[skipped]").startswith("[skipped] update check  offline")
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
    assert _line(out, "[skipped]").startswith("[skipped] update check  offline")


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
    assert done.returncode == 3 and "could not be reached" in done.stderr
