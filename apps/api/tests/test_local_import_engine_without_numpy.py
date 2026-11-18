"""Without the optional `processing` extra (CI installs only `.[dev,api]`): the v1 engine adapter imports, and
`isaac process` on the default (v1) path says `processing_unavailable` and writes no result.

Runs in a fresh interpreter with numpy, scipy, larch, yaml and matplotlib BLOCKED (``sys.modules[name] = None`` makes
every import of them raise ImportError), so it holds whether or not the extra is installed here. SYNTHETIC SPEC
values only (SYN_ names; every header says SYNTHETIC FIXTURE)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BLOCKED = ("numpy", "scipy", "larch", "yaml", "matplotlib")

SCRIPT = textwrap.dedent('''
    import json, sys
    for name in {blocked!r}:
        sys.modules[name] = None
    from pathlib import Path
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    import isaac_api.local_import.processing.engine_xas as EX      # imports without numpy
    from isaac_api.local_import import cli
    from isaac_api.local_import import mutations as M
    assert EX.PROTOCOL_ID == "isaac.xas.v1"
    assert cli.main(["import", str(root), "--out", str(out)]) == 0
    M.group(out)
    code = cli.main(["process", str(out), "--source", str(root)])
    status = json.loads((out / "processing" / "status.json").read_text()) \\
        if (out / "processing" / "status.json").exists() else None
    print("RESULT " + json.dumps({{"code": code, "status": status and status.get("status"),
                                  "missing": status and status.get("missing"),
                                  "results": (out / "processing" / "processing_results.json").exists()}}))
''').format(blocked=BLOCKED)


def _spec(path: Path) -> None:
    lines = ["#F SYN", "#E 1", "", "#C SYNTHETIC FIXTURE -- NOT INSTRUMENT OUTPUT. Every value is invented.",
             "#S 1  gscan energy 11165 11500 5 0.5", "#D Sat Apr 12 09:01:00 2025", "#L energy  absev  I0  I1  I2  vortDT  sec"]
    for k in range(60):
        e = 11165 + 5.0 * k
        lines.append(f"{e - 2.3:.3f} {e:.3f} 100000 3 2 {50 + (40 if e > 11215 else 0)} 1")
    path.write_text("\n".join(lines) + "\n")


def test_without_the_processing_extra_the_adapter_imports_and_process_says_unavailable(tmp_path):
    root = tmp_path / "SYN_beamtime"
    (root / "01_SYN_ZZ1_060mV_dir").mkdir(parents=True)
    _spec(root / "01_SYN_ZZ1_060mV")
    _spec(root / "01_SYN_ZZ1_060mV_dir" / "01_SYN_ZZ1_060mV_001.dat")
    env = {k: v for k, v in os.environ.items() if k != "ISAAC_PROCESSING_ENGINE"}      # the default path: v1
    env.update(ISAAC_PORTAL_VALIDATOR_DIR="/nonexistent", ISAAC_PORTAL_VALIDATOR_PYTHON="/nonexistent",
               PYTHONPATH=os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT / "apps" / "api")]))
    got = subprocess.run([sys.executable, "-c", SCRIPT, str(root), str(tmp_path / "out")], capture_output=True,
                         text=True, env=env, cwd=str(tmp_path), timeout=300)
    line = next((x for x in got.stdout.splitlines() if x.startswith("RESULT ")), None)
    assert line is not None, got.stdout[-2000:] + got.stderr[-2000:]
    res = json.loads(line[len("RESULT "):])
    assert res["code"] == 2 and res["status"] == "processing_unavailable" and res["results"] is False, res
    assert "numpy" in res["missing"] or "larch" in res["missing"], res
    assert "processing_unavailable" in got.stderr and "processing not installed" in got.stderr
