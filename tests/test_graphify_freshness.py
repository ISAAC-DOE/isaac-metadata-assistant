"""scripts/check_graphify_freshness.py is a stdlib-only, memory-plane convenience:
it reports fresh/stale/missing for the derived graph by mtime, never runs graphify,
never rewrites graphify-out/, never scans examples/, and never touches the truth path.
Every case runs against a tmp_path sandbox — never the real graphify-out/."""

import importlib.util
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_graphify_freshness.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_graphify_freshness", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


freshness = _load()


def _write(root: Path, rel: str, mtime: float) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n", encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def _graph(root: Path, mtime: float) -> Path:
    return _write(root, "graphify-out/graph.json", mtime)


def test_missing_when_no_graph(tmp_path):
    _write(tmp_path, "README.md", 100)
    assert freshness.check(tmp_path) == "missing"
    assert freshness.EXIT["missing"] == 2


def test_fresh_when_graph_newer_than_all_sources(tmp_path):
    _write(tmp_path, "README.md", 100)
    _write(tmp_path, "docs/x.md", 100)
    _graph(tmp_path, 200)
    assert freshness.check(tmp_path) == "fresh"
    assert freshness.EXIT["fresh"] == 0


def test_stale_when_a_tracked_source_is_newer(tmp_path):
    _graph(tmp_path, 100)
    _write(tmp_path, "docs/x.md", 200)  # newer than the graph
    assert freshness.check(tmp_path) == "stale"
    assert freshness.EXIT["stale"] == 1


def test_ignores_derived_and_volatile_paths(tmp_path):
    _graph(tmp_path, 100)
    # Newer files under derived / volatile trees must NOT flip it to stale.
    _write(tmp_path, "graphify-out/manifest.json", 300)   # not tracked
    _write(tmp_path, ".venv/lib/x.py", 300)               # not tracked
    _write(tmp_path, ".pytest_cache/v/x", 300)            # not tracked
    _write(tmp_path, "src/isaac_records/__pycache__/x.pyc", 300)  # tracked tree, skipped dir
    assert freshness.check(tmp_path) == "fresh"


def test_never_scans_examples(tmp_path):
    _graph(tmp_path, 100)
    # A newer, sensitive file under examples/ must not affect freshness or be read.
    _write(tmp_path, "examples/real_secret.txt", 999)
    assert freshness.check(tmp_path) == "fresh"


def test_main_prints_single_word_and_returns_exit_code(tmp_path, capsys):
    _write(tmp_path, "README.md", 100)
    _graph(tmp_path, 200)
    code = freshness.main([str(tmp_path)])
    out = capsys.readouterr().out.strip()
    assert out == "fresh"
    assert code == 0
