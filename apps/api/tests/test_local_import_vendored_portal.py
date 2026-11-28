"""The portal validator SHIPPED with the repository (``vendor/isaac-portal-validator/``).

It is the third place ``portal.locate`` looks (after ``ISAAC_PORTAL_VALIDATOR_DIR``/``_PYTHON`` and the
``~/.cache`` install), it is used only when every file's sha256 matches ``PROVENANCE.md``, and it is never a
pass when it cannot run. All records here are synthetic test fixtures.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from isaac_api.local_import import portal as P

REPO_ROOT = Path(__file__).resolve().parents[3]
VENDORED = REPO_ROOT / "vendor" / "isaac-portal-validator" / P.PINNED_COMMIT
PROVENANCE = REPO_ROOT / "vendor" / "isaac-portal-validator" / "PROVENANCE.md"
SETUP = REPO_ROOT / "scripts" / "setup_isaac_local.sh"
FIXTURES = REPO_ROOT / "tests" / "fixtures"
#: synthetic records: 14 the pinned portal publishes, 3 it rejects (measured 28 Nov 2026)
SYNTHETIC_RECORDS = sorted((FIXTURES / "official").glob("*.json")) + [
    FIXTURES / "legacy" / "01JQZ0SYNTHXANESDEMO000000.json",
    FIXTURES / "truthpath" / "SYNTHETIC-FORMAT-PROBE-01.json",
    FIXTURES / "truthpath" / "SYNTHETIC-EMPTY-PROBE-01.json",
]


def _find_venv_with_validator_modules() -> Path | None:
    for venv in P.vendored_interpreters():
        if (venv / "bin" / "python").exists() and P.has_validator_modules(venv):
            return venv
    return None


#: looked up once, before any test hides the cache: a real environment that can run the validator, or None
_REAL_VENV = _find_venv_with_validator_modules()


def _venv_with_validator_modules() -> Path | None:
    return _REAL_VENV


def _cache_validator() -> dict | None:
    """The full upstream checkout in the cache, as ``locate`` would return it, or None."""
    if not P.CACHE_ROOT.is_dir():
        return None
    for child in sorted(P.CACHE_ROOT.iterdir()):
        src, py = child / "src", child / "venv" / "bin" / "python"
        if child.name.startswith(P.PINNED_COMMIT) and (src / "portal" / "validation.py").is_file() and py.exists():
            head = P.git_head(src)
            if head and head.startswith(P.PINNED_COMMIT):
                return {"available": True, "dir": str(src), "python": str(py), "commit": head,
                        "pinned_commit": P.PINNED_COMMIT, "must_be_within": str(child), "source": "cache", "reason": None}
    return None


@pytest.fixture()
def no_env_no_cache(monkeypatch, tmp_path):
    monkeypatch.delenv(P.DIR_ENV, raising=False)
    monkeypatch.delenv(P.PYTHON_ENV, raising=False)
    monkeypatch.setattr(P, "CACHE_ROOT", tmp_path / "no-cache")
    return tmp_path


# --- the vendored files ------------------------------------------------------------------------------------------


def test_the_vendored_files_are_exactly_the_ones_provenance_lists():
    rows = dict(re.findall(r"^\| `((?:portal|schema|data)/[^`]+)` \| `([0-9a-f]{64})` \|", PROVENANCE.read_text(), flags=re.M))
    assert rows == P.VENDORED_SHA256
    on_disk = {p.relative_to(VENDORED).as_posix() for p in VENDORED.rglob("*")
               if p.is_file() and "__pycache__" not in p.parts}
    assert on_disk == set(P.VENDORED_SHA256)
    assert P.vendored_state() == (VENDORED, None)
    assert P.VENDORED_COMMIT.startswith(P.PINNED_COMMIT) and P.VENDORED_COMMIT in PROVENANCE.read_text()


def test_the_vendored_schema_is_the_repositorys_schema_byte_for_byte():
    assert (VENDORED / "schema" / "isaac_record_v1.json").read_bytes() == (REPO_ROOT / "schema" / "isaac_record_v1.json").read_bytes()


def test_the_cached_checkout_holds_the_same_bytes_when_present():
    cache = _cache_validator()
    if cache is None:
        pytest.skip("no cached upstream checkout to compare with")
    for rel in P.VENDORED_SHA256:
        assert (Path(cache["dir"]) / rel).read_bytes() == (VENDORED / rel).read_bytes(), rel


# --- where it is found ---------------------------------------------------------------------------------------------


def test_the_vendored_copy_is_used_when_there_is_no_env_and_no_cache(no_env_no_cache, monkeypatch, tmp_path):
    venv = tmp_path / "venv"
    site = venv / "lib" / "python3.11" / "site-packages"
    for m in P.VALIDATOR_MODULES:
        (site / m).mkdir(parents=True)
        (site / m / "__init__.py").write_text("")
    (venv / "bin").mkdir()
    (venv / "bin" / "python").symlink_to(sys.executable)
    monkeypatch.setattr(P, "vendored_interpreters", lambda: [tmp_path / "empty-venv", venv])
    where = P.locate()
    assert where["available"] is True and where["source"] == "vendored"
    assert where["dir"] == str(VENDORED) and where["python"] == str(venv / "bin" / "python")
    assert where["must_be_within"] == str(venv) and where["commit"] == P.VENDORED_COMMIT
    assert P.upstream_schema(where) == json.loads((REPO_ROOT / "schema" / "isaac_record_v1.json").read_text())


def test_without_an_interpreter_holding_the_packages_it_is_unavailable_never_a_pass(no_env_no_cache, monkeypatch, tmp_path):
    venv = tmp_path / "venv"
    (venv / "lib" / "python3.11" / "site-packages" / "jsonschema").mkdir(parents=True)  # one of five
    (venv / "lib" / "python3.11" / "site-packages" / "jsonschema" / "__init__.py").write_text("")
    (venv / "bin").mkdir()
    (venv / "bin" / "python").symlink_to(sys.executable)
    assert P.has_validator_modules(venv) is False
    monkeypatch.setattr(P, "vendored_interpreters", lambda: [venv])
    where = P.locate()
    assert where["available"] is False and "scripts/setup_isaac_local.sh" in where["reason"]
    check = P.run_portal_check({"record_id": "SYNTHETIC"})
    assert check["verdict"] == P.VERDICT_UNAVAILABLE == P.verdict_of(check)


def _vendored_copy(tmp_path: Path) -> Path:
    copy = tmp_path / "vendor"
    shutil.copytree(VENDORED, copy / P.PINNED_COMMIT, ignore=shutil.ignore_patterns("__pycache__"))
    return copy


#: a stand-in validator that passes everything: what a tampered or planted module would do
_ALWAYS_PUBLISH = (
    "def validate_record_full(record):\n    return {'valid': True, 'errors': [], 'warnings': []}\n"
    "def outcome(result):\n    return ('publish', [])\n"
)
_INVALID_RECORD = FIXTURES / "truthpath" / "SYNTHETIC-EMPTY-PROBE-01.json"


def _assert_unavailable(monkeypatch, copy: Path, *words: str) -> None:
    monkeypatch.setattr(P, "VENDOR_ROOT", copy)
    venv = _venv_with_validator_modules()
    monkeypatch.setattr(P, "vendored_interpreters", lambda: [venv] if venv else [])
    src, why = P.vendored_state()
    assert src is None and all(w in why for w in words), why
    assert P.locate()["available"] is False
    check = P.run_portal_check(json.loads(_INVALID_RECORD.read_text()))
    assert check["status"] == "unavailable" and check["verdict"] == P.VERDICT_UNAVAILABLE == P.verdict_of(check)


@pytest.mark.parametrize("rel", sorted(P.VENDORED_SHA256))
@pytest.mark.parametrize("damage", ["edit", "truncate", "delete"])
def test_damage_to_any_vendored_file_is_unavailable_never_a_pass(no_env_no_cache, monkeypatch, tmp_path, rel, damage):
    copy = _vendored_copy(tmp_path)
    target = copy / P.PINNED_COMMIT / rel
    if damage == "edit" and rel == "portal/validation.py":
        target.write_text(target.read_text() + "\n" + _ALWAYS_PUBLISH)  # the dangerous edit: it would publish anything
    elif damage == "edit":
        target.write_bytes(target.read_bytes() + b"\n")
    elif damage == "truncate":
        target.write_bytes(target.read_bytes()[:100])
    else:
        target.unlink()
    _assert_unavailable(monkeypatch, copy, rel, "PROVENANCE.md")


@pytest.mark.parametrize("extra", ["portal/validation/__init__.py", "portal/jsonschema/__init__.py", "portal/jsonschema.py",
                                   "portal/validation.pyc", "portal/json.py", "data/extra.json", "notes.txt"])
def test_an_extra_file_in_the_vendored_folder_is_unavailable_never_a_pass(no_env_no_cache, monkeypatch, tmp_path, extra):
    copy = _vendored_copy(tmp_path)
    target = copy / P.PINNED_COMMIT / extra
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_ALWAYS_PUBLISH)
    _assert_unavailable(monkeypatch, copy, extra.split("/")[0], "does not list")


def test_a_planted_package_would_have_been_imported_so_the_file_set_check_is_needed(tmp_path):
    """The negative control for the test above: the runner itself DOES import portal/validation/__init__.py
    ahead of validation.py, and that fake would publish an invalid record."""
    import isaac_portal_runner as runner

    venv = _venv_with_validator_modules()
    if venv is None:
        pytest.skip("no Python environment with the validator's packages")
    copy = _vendored_copy(tmp_path)
    (copy / P.PINNED_COMMIT / "portal" / "validation").mkdir()
    (copy / P.PINNED_COMMIT / "portal" / "validation" / "__init__.py").write_text(_ALWAYS_PUBLISH)
    code, out, _ = runner.run(str(venv / "bin" / "python"), str(copy / P.PINNED_COMMIT / "portal"),
                              _INVALID_RECORD.read_text(), must_be_within=venv)
    assert code == 0 and json.loads(out.splitlines()[-1])["outcome"] == "publish"


def test_finder_files_and_compiled_folders_are_not_extra(no_env_no_cache, monkeypatch, tmp_path):
    copy = _vendored_copy(tmp_path)
    (copy / P.PINNED_COMMIT / ".DS_Store").write_bytes(b"\0")
    (copy / P.PINNED_COMMIT / "portal" / "__pycache__").mkdir()
    (copy / P.PINNED_COMMIT / "portal" / "__pycache__" / "validation.cpython-311.pyc").write_bytes(b"\0")
    monkeypatch.setattr(P, "VENDOR_ROOT", copy)
    assert P.vendored_state() == (copy / P.PINNED_COMMIT, None)


def _plant_stale_pyc(venv: Path, portal_dir: Path, tmp_path: Path) -> None:
    """An UNCHECKED-hash .pyc for validation.py that publishes everything: Python loads such a file
    without looking at the source, so only never reading __pycache__ protects against it."""
    fake = tmp_path / "fake_validation.py"
    fake.write_text(_ALWAYS_PUBLISH)
    subprocess.run([str(venv / "bin" / "python"), "-I", "-c",
                    "import importlib.util, py_compile, sys; py_compile.compile(sys.argv[1], "
                    "cfile=importlib.util.cache_from_source(sys.argv[2]), "
                    "invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)",
                    str(fake), str(portal_dir / "validation.py")], check=True, cwd="/")


def test_a_stale_compiled_file_beside_the_vendored_sources_is_never_loaded(no_env_no_cache, monkeypatch, tmp_path):
    venv = _venv_with_validator_modules()
    if venv is None:
        pytest.skip("no Python environment with the validator's packages")
    copy = _vendored_copy(tmp_path)
    portal_dir = copy / P.PINNED_COMMIT / "portal"
    _plant_stale_pyc(venv, portal_dir, tmp_path)
    planted = sorted((portal_dir / "__pycache__").glob("validation.*.pyc"))
    assert planted
    # negative control: a plain `python -I` in that folder (the runner's old argv) loads the planted file
    old = subprocess.run([str(venv / "bin" / "python"), "-I", "-c",
                          "import sys; sys.path.insert(0, '.'); import validation; print(validation.outcome({})[0])"],
                         cwd=portal_dir, capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    assert old.stdout.strip() == "publish"
    monkeypatch.setattr(P, "VENDOR_ROOT", copy)
    monkeypatch.setattr(P, "vendored_interpreters", lambda: [venv])
    check = P.run_portal_check(json.loads(_INVALID_RECORD.read_text()))
    assert check["status"] == "ran" and check["verdict"] == "reject"  # the checked source ran, not the .pyc
    assert sorted((portal_dir / "__pycache__").glob("*.pyc")) == planted  # and nothing new was written there


def test_a_validator_run_writes_no_compiled_file_into_the_vendored_folder(no_env_no_cache, monkeypatch, tmp_path):
    venv = _venv_with_validator_modules()
    if venv is None:
        pytest.skip("no Python environment with the validator's packages")
    copy = _vendored_copy(tmp_path)
    monkeypatch.setattr(P, "VENDOR_ROOT", copy)
    monkeypatch.setattr(P, "vendored_interpreters", lambda: [venv])
    assert P.run_portal_check(json.loads(_INVALID_RECORD.read_text()))["verdict"] == "reject"
    assert not list(copy.rglob("__pycache__")) and not list(copy.rglob("*.pyc"))


def test_a_missing_vendored_copy_is_unavailable(no_env_no_cache, monkeypatch, tmp_path):
    monkeypatch.setattr(P, "VENDOR_ROOT", tmp_path / "nothing")
    assert P.locate()["available"] is False
    assert P.run_portal_check({"x": 1})["verdict"] == P.VERDICT_UNAVAILABLE


def test_an_operator_named_validator_is_final_and_never_falls_back_to_the_vendored_copy(monkeypatch, tmp_path):
    monkeypatch.setenv(P.DIR_ENV, str(tmp_path / "no-validator"))
    monkeypatch.setenv(P.PYTHON_ENV, str(tmp_path / "no-validator" / "python"))
    where = P.locate()
    assert where["available"] is False and P.DIR_ENV in where["reason"]


def test_an_older_cache_installs_source_is_never_run_only_its_venv_may_be(no_env_no_cache, monkeypatch, tmp_path):
    """The full upstream checkout in ~/.cache holds some twenty importable modules (ontology.py imports
    `database` when present), so its source cannot be checked by five hashes: it is never run. An edited
    cache therefore gives no verdict of its own; the checked vendored copy runs instead."""
    cache = tmp_path / "cache"
    src = cache / P.PINNED_COMMIT / "src"
    (src / "portal").mkdir(parents=True)
    (src / "portal" / "validation.py").write_text(_ALWAYS_PUBLISH)
    (src / ".git").mkdir()
    (src / ".git" / "HEAD").write_text(P.VENDORED_COMMIT + "\n")  # even AT the pin
    (cache / P.PINNED_COMMIT / "venv" / "bin").mkdir(parents=True)
    (cache / P.PINNED_COMMIT / "venv" / "bin" / "python").symlink_to(sys.executable)
    monkeypatch.setattr(P, "CACHE_ROOT", cache)
    monkeypatch.setattr(P, "vendored_interpreters", lambda: [])
    where = P.locate()
    assert where["available"] is False and "packages" in where["reason"]  # not the cache's source
    venv = _venv_with_validator_modules()
    if venv is None:
        pytest.skip("no Python environment with the validator's packages")
    monkeypatch.setattr(P, "vendored_interpreters", lambda: [venv])
    where = P.locate()
    assert where["source"] == "vendored" and where["dir"] == str(VENDORED)
    assert P.run_portal_check(json.loads(_INVALID_RECORD.read_text()))["verdict"] == "reject"


def test_a_worktree_finds_its_main_checkout_from_gits_own_files(tmp_path):
    main = tmp_path / "ISAAC"
    (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
    (main / ".git" / "worktrees" / "wt" / "commondir").write_text("../..\n")
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {main / '.git' / 'worktrees' / 'wt'}\n")
    assert P.main_checkout(wt) == main.resolve()
    assert P.main_checkout(main) is None  # a main checkout has a .git folder
    assert P.main_checkout(tmp_path / "nowhere") is None


def test_the_interpreter_order_is_this_checkout_then_the_main_checkout_then_the_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(P, "CHECKOUT_ROOT", tmp_path / "wt")
    monkeypatch.setattr(P, "main_checkout", lambda root: tmp_path / "main")
    (tmp_path / "cache" / f"{P.PINNED_COMMIT}").mkdir(parents=True)
    (tmp_path / "cache" / "0000000").mkdir()
    monkeypatch.setattr(P, "CACHE_ROOT", tmp_path / "cache")
    assert P.vendored_interpreters() == [tmp_path / "wt" / ".venv", tmp_path / "main" / ".venv",
                                         tmp_path / "cache" / P.PINNED_COMMIT / "venv"]


# --- the verdict -------------------------------------------------------------------------------------------------


_REAL_CACHE = _cache_validator()


def test_the_vendored_verdict_is_the_cached_checkouts_on_synthetic_records(no_env_no_cache, monkeypatch):
    cache = _REAL_CACHE
    venv = _venv_with_validator_modules()
    if cache is None or venv is None:
        pytest.skip("needs the cached upstream checkout and a Python environment with the validator's packages")
    monkeypatch.setattr(P, "vendored_interpreters", lambda: [venv])
    vendored = P._vendored
    assert vendored()["available"] is True
    outcomes = []
    for path in SYNTHETIC_RECORDS:
        record = json.loads(path.read_text())
        monkeypatch.setattr(P, "locate", lambda: dict(cache))
        from_cache = P.run_portal_check(record)
        monkeypatch.setattr(P, "locate", vendored)
        from_vendor = P.run_portal_check(record)
        assert from_cache["status"] == from_vendor["status"] == "ran", path.name
        assert from_vendor["validator_source"] == "vendored" and from_cache["validator_source"] == "cache"
        for key in ("result", "outcome", "held", "verdict", "validator_commit", "pinned_commit"):
            assert from_cache[key] == from_vendor[key], (path.name, key)
        outcomes.append(from_vendor["outcome"])
    assert outcomes.count("publish") == 14 and outcomes.count("reject") == 3


def test_the_vendored_validator_runs_end_to_end_with_the_cache_hidden(no_env_no_cache, monkeypatch):
    venv = _venv_with_validator_modules()
    if venv is None:
        pytest.skip("no Python environment with the validator's packages")
    monkeypatch.setattr(P, "vendored_interpreters", lambda: [venv])
    good = P.run_portal_check(json.loads((FIXTURES / "official" / "echem_performance_record.json").read_text()))
    bad = P.run_portal_check(json.loads((FIXTURES / "truthpath" / "SYNTHETIC-EMPTY-PROBE-01.json").read_text()))
    assert good["validator_source"] == bad["validator_source"] == "vendored"
    assert good["verdict"] == "publish" and bad["verdict"] == "reject"


# --- setup --check -----------------------------------------------------------------------------------------------


def _syn_checkout(tmp_path: Path, env: dict) -> Path:
    co = tmp_path / "ISAAC"
    (co / "schema").mkdir(parents=True)
    (co / "schema" / "isaac_record_v1.json").write_text("{}\n")
    (co / "apps" / "api" / "isaac_api").mkdir(parents=True)
    (co / "apps" / "api" / "isaac_api" / "__init__.py").write_text("")  # git keeps no empty folder
    (co / "scripts").mkdir()
    shutil.copy2(SETUP, co / "scripts" / "setup_isaac_local.sh")
    (co / ".claude" / "skills" / "isaac-historical-import").mkdir(parents=True)
    (co / ".claude" / "skills" / "isaac-historical-import" / "SKILL.md").write_text("SYN skill\n")
    subprocess.run(["git", "-C", str(co), "init", "-q", "-b", "main"], env=env, check=True)
    subprocess.run(["git", "-C", str(co), "add", "-A"], env=env, check=True)
    subprocess.run(["git", "-C", str(co), "commit", "-q", "-m", "SYN"], env=env, check=True)
    return co


def _env(tmp_path: Path, path: str) -> dict:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "ISAAC_PORTAL"))}
    env.update(HOME=str(home), PATH=path, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
               GIT_AUTHOR_NAME="SYN", GIT_AUTHOR_EMAIL="syn@example.invalid",
               GIT_COMMITTER_NAME="SYN", GIT_COMMITTER_EMAIL="syn@example.invalid")
    return env


def _check(co: Path, env: dict, *args: str) -> str:
    done = subprocess.run(["bash", str(co / "scripts" / "setup_isaac_local.sh"), *args], env=env,
                          capture_output=True, text=True, timeout=120)
    return done.stdout


def _line(out: str, label: str) -> str:
    [line] = [x for x in out.splitlines() if label in x] or [""]
    return line


needs_git = pytest.mark.skipif(shutil.which("git") is None or shutil.which("bash") is None, reason="needs git and bash")


@needs_git
def test_check_says_how_to_install_pdftoppm_and_counts_it_optional(tmp_path):
    if shutil.which("pdftoppm", path="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"):
        pytest.skip("a real pdftoppm is installed where the script also looks")
    git_dir = str(Path(shutil.which("git")).parent)
    env = _env(tmp_path, f"/usr/bin:/bin:{git_dir}")
    co = _syn_checkout(tmp_path, env)
    out = _check(co, env, "--check", "--offline")
    line = _line(out, "pdf pages")
    assert line.startswith("[optional] pdf pages") and "brew install poppler" in line
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "pdftoppm").write_text("#!/bin/sh\nexit 0\n")
    (fake / "pdftoppm").chmod(0o755)
    out = _check(co, _env(tmp_path, f"{fake}:/usr/bin:/bin:{git_dir}"), "--check", "--offline")
    assert _line(out, "pdf pages").startswith(f"[ok] pdf pages           {fake}/pdftoppm")


@needs_git
def test_check_reports_the_portal_check_with_its_fix_when_the_tools_are_missing(tmp_path):
    env = _env(tmp_path, os.environ.get("PATH", "/usr/bin:/bin"))
    co = _syn_checkout(tmp_path, env)
    line = _line(_check(co, env, "--check", "--offline"), "portal check")
    assert line.startswith("[missing] portal check") and "Run: scripts/setup_isaac_local.sh" in line


@needs_git
def test_a_run_writes_the_skills_checkout_path_and_check_says_so(tmp_path):
    env = _env(tmp_path, os.environ.get("PATH", "/usr/bin:/bin"))
    co = _syn_checkout(tmp_path, env)
    pointer = co / ".claude" / "skills" / "isaac-historical-import" / "checkout-path.txt"
    out = _check(co, env, "--check", "--offline")
    assert not pointer.exists(), "--check changes nothing"
    assert _line(out, "skill path file").startswith("[missing] skill path file") and "--refresh-skill" in _line(out, "skill path file")
    _check(co, env, "--refresh-skill", "--skill-dir", str(co / ".claude" / "skills"))
    assert pointer.read_text() == f"{co}\n"
    out = _check(co, env, "--check", "--offline", "--skill-dir", str(co / ".claude" / "skills"))
    assert _line(out, "skill path file").startswith("[ok] skill path file")
    assert _line(out, "skill at").startswith("[ok] skill at")  # the pointer is not a difference


@needs_git
def test_the_skills_checkout_path_is_gitignored():
    done = subprocess.run(["git", "-C", str(REPO_ROOT), "check-ignore", "-q", "--no-index",
                           ".claude/skills/isaac-historical-import/checkout-path.txt"], capture_output=True)
    assert done.returncode == 0  # 0: ignored; 1: it would be committed


@needs_git
def test_a_worktree_without_a_venv_uses_the_main_checkouts(tmp_path):
    env = _env(tmp_path, os.environ.get("PATH", "/usr/bin:/bin"))
    co = _syn_checkout(tmp_path, env)
    (co / ".venv" / "bin").mkdir(parents=True)
    (co / ".venv" / "bin" / "python").symlink_to(sys.executable)
    wt = tmp_path / "wt"
    subprocess.run(["git", "-C", str(co), "worktree", "add", "-q", "-b", "syn-wt", str(wt)], env=env, check=True)
    out = _check(wt, env, "--check", "--offline")
    line = _line(out, "Python environment")
    assert line.startswith("[ok] Python environment") and str(co / ".venv") in line
    assert "git worktree with no .venv of its own" in line and "scripts/setup_isaac_local.sh" in line


@needs_git
def test_without_an_installed_copy_the_folders_own_skill_is_ok_and_next_steps_say_start_claude_here(tmp_path):
    env = _env(tmp_path, os.environ.get("PATH", "/usr/bin:/bin"))
    co = _syn_checkout(tmp_path, env)
    out = _check(co, env, "--check", "--offline")  # the default skills folder (~/.claude/skills) has no copy
    line = _line(out, "] skill  ")
    assert line.startswith("[ok] skill") and "this folder's own copy" in line and "--install-skill" in line
    assert f"In this folder ({co}) start Claude Code" in out and "beamtime folder's parent" not in out
    assert "/isaac-historical-import" in out


@needs_git
def test_a_refused_setup_writes_nothing(tmp_path):
    """'Nothing was changed' must be true: no Python 3.11 and no uv -> refused before the skill's path file."""
    env = _env(tmp_path, "/usr/bin:/bin:" + str(Path(shutil.which("git")).parent))
    if shutil.which("uv", path=env["PATH"]) or any(
            shutil.which(c, path=env["PATH"]) for c in ("python3.11",)):
        pytest.skip("a uv or python3.11 is on the minimal PATH")
    co = _syn_checkout(tmp_path, env)
    done = subprocess.run(["bash", str(co / "scripts" / "setup_isaac_local.sh"), "--offline"], env=env,
                          capture_output=True, text=True, timeout=120)
    if done.returncode != 2:
        pytest.skip("this machine's /usr/bin/python3 is 3.11, so setup is not refused")
    assert "Nothing was changed" in done.stderr
    assert not (co / ".claude" / "skills" / "isaac-historical-import" / "checkout-path.txt").exists()
    assert not (co / ".venv").exists()
