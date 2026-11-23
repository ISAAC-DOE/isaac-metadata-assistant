"""Write the SYNTHETIC 1.14.0 fixture bundle (bundle_1_14_0/) with the 1.14.0 build: run it with PYTHONPATH on a
checkout of commit 6b26a631 (origin/main when 1.15.0 was written), never on a later build.
usage: python gen_114.py <checkout> <out_dir>"""
import shutil, sys
from pathlib import Path
co, out = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(co / "apps/api/tests"))
from test_local_import_quick_merges import _spec_run
from test_local_import_reader_mca import make_mca
from isaac_api.local_import import cli, bundle as B
assert B.FORMAT_VERSION == "1.14.0", B.FORMAT_VERSION
src = out.parent / "src" / "SYN_BL00_2100-31_Upgrade"
if src.exists(): shutil.rmtree(src)
RUN = "SYN_cat_m600mV"
for stem in (RUN, "SYN_cat_1200mV"):
    _spec_run(src, stem)
def mca(path, title):
    make_mca(path); path.write_text(path.read_text().replace("#S 1 (synthetic title 2.1 DTC)", f"#S 1 {title}"))
mca(src / "PyMcaAdded" / f"{RUN}.mca", f"({RUN} 1.1 DTC + {RUN} 1.1 I1)/2")       # an expression title: a run at 1.14.0
mca(src / "MERGE" / "ave_ZZ_f10.mca", f"Average of 1 from Norm. {RUN} 1.1 Y")     # an average: unlinked at 1.14.0
p = src / "averages" / f"{RUN}_ave.dat"; p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(f"#F /data/synthetic/{p.name}\n#D Mon Sep  9 03:00:00 2001\n\n#S 1 ({RUN} 1.1 DTC + {RUN} 1.1 I1)/2\n"
             "#D Mon Sep  9 03:00:00 2001\n#N 2\n#L energy  DTC\n1000 0.1\n1005 0.2\n1010 0.3\n")  # an engine run at 1.14.0
if out.exists(): shutil.rmtree(out)
assert cli.main(["import", str(src), "--out", str(out)]) == 0
