"""Command line: survey | recipe init | reduce | mback | soft | scope | skill."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="xas-analysis")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("reduce", help="SPEC -> aligned + averaged *_raw files (reduce_xas_v2)")
    p.add_argument("recipe")
    p.add_argument("-q", "--quiet", action="store_true")

    p = sub.add_parser("mback", help="normalization of an [eV, raw] file (default Victoreen + McMaster)")
    p.add_argument("file")
    p.add_argument("--element", "-Z", required=True)
    p.add_argument("--core", default="", help="K, L1, L2, L3, M1 or empty for auto")
    p.add_argument("--range", nargs="+", type=float, default=None,
                   help="2 values (offsets from edge, eV) or 4 (absolute pre/post windows, eV)")
    p.add_argument("--nth", nargs="+", type=int, default=[1, 1])
    p.add_argument("--erfc", action="store_true")
    p.add_argument("--model", choices=["poly", "xrs"], default="xrs",
                   help="xrs (default): Victoreen + McMaster step, XRS low-q objective (mback_xrs); "
                        "poly: polynomial background (mback, --nth, --legacy-bg)")
    p.add_argument("--legacy-bg", action="store_true",
                   help="mback_v4.m background (independent post polynomial; A_edge unidentified)")
    p.add_argument("--no-save", action="store_true")

    p = sub.add_parser("soft", help="soft-XAS Pearson-VII + FEFF mu0 reduction of a BL8-2 export")
    p.add_argument("file")
    p.add_argument("-o", "--out", default=None)

    p = sub.add_parser("survey", help="inspect a beamtime folder: edge, channels, energy reference; "
                                      "recommends a calibration (no data are changed)")
    p.add_argument("folder")
    p.add_argument("--json", default=None, help="write the full survey here")

    p = sub.add_parser("recipe", help="recipe tools")
    rs = p.add_subparsers(dest="rcmd", required=True)
    q = rs.add_parser("init", help="draft recipe from a survey of FOLDER (review before use)")
    q.add_argument("folder")
    q.add_argument("-o", "--out", required=True)
    q = rs.add_parser("show", help="print a recipe after defaults are filled in")
    q.add_argument("recipe")

    sub.add_parser("scope", help="what this version can reduce (validated / exploratory / not supported)")

    p = sub.add_parser("skill", help="locate or install the agent skill shipped with the package")
    p.add_argument("action", choices=["path", "install"])
    p.add_argument("--link", action="store_true", help="symlink instead of copy (git clone)")

    a = ap.parse_args(argv)
    if a.cmd == "survey":
        from .survey import print_report, survey, write_survey
        rep = survey(a.folder)
        print_report(rep)
        if a.json:
            write_survey(rep, a.json)
            print("wrote", a.json)
        return 0
    if a.cmd == "recipe":
        if a.rcmd == "init":
            from .recipe_init import write_draft
            from .survey import print_report, survey
            rep = survey(a.folder)
            print_report(rep)
            write_draft(a.folder, a.out, rep)
            print(f"wrote DRAFT recipe {a.out}: review roles, curate scans from the logbook, then reduce")
        else:
            import yaml

            from .pipeline import fill_recipe_defaults, load_recipe
            print(yaml.safe_dump(fill_recipe_defaults(load_recipe(a.recipe)), sort_keys=False, width=200))
        return 0
    if a.cmd == "scope":
        from importlib import resources
        print(resources.files("xas_analysis.skill").joinpath("scope.md").read_text())
        return 0
    if a.cmd == "skill":
        import shutil
        from importlib import resources
        src = Path(str(resources.files("xas_analysis.skill")))
        if a.action == "path":
            print(src)
            return 0
        dst = Path("~/.claude/skills/xas-analysis").expanduser()
        if dst.exists() or dst.is_symlink():
            print(f"{dst} exists; remove it first")
            return 1
        dst.parent.mkdir(parents=True, exist_ok=True)
        if a.link:
            dst.symlink_to(src)
        else:
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.py"))
        print(("linked" if a.link else "copied"), src, "->", dst)
        return 0
    if a.cmd == "reduce":
        from .pipeline import load_recipe, reduce
        r = load_recipe(a.recipe)
        if a.quiet:
            r["quiet"] = True
        reduce(r)
    elif a.cmd == "mback":
        if a.model == "xrs":
            import numpy as np

            from .matlab_compat import save_ascii
            from .model.mback_xrs import mback_xrs
            d = np.loadtxt(a.file)
            res = mback_xrs(a.element, d[:, 0], d[:, 1], a.range, a.core)
            if not a.no_save:
                p = Path(a.file)
                save_ascii(p.with_name(p.name.split(".")[0] + ".nrm_xrs"),
                           np.c_[res.energy_eV, res.norm_xas, res.mu])
            i = res.info
            print(f"A_edge={i['A_edge']:.6g}  objective={i['objective']:.4g}  E_edge={i['E_edge_keV'] * 1000:.1f} eV  "
                  f"pre/post pts {i['num_pre']}/{i['num_post']}  terms " +
                  " ".join(f"{k}={v:.2e}" for k, v in i["terms"].items()))
            return 0
        from .model.mback import mback_file
        nth = a.nth[0] if len(a.nth) == 1 else tuple(a.nth[:2])
        res = mback_file(a.element, a.file, a.range, nth, a.core, erfc_enabled=a.erfc, bg_continuity=not a.legacy_bg,
                         save_nrm=not a.no_save)
        i = res.info
        print(f"A_edge={i['A_edge']:.6g}  resnorm={i['resnorm']:.4g}  E_edge={i['E_edge_keV'] * 1000:.1f} eV  "
              f"pre/post pts {i['num_pre']}/{i['num_post']}  Nth {i['Nth_pre']}/{i['Nth_post']}")
        for w in i["warnings"]:
            print("warning:", w)
    elif a.cmd == "soft":
        from .model.soft_pvii import reduce_file
        r = reduce_file(a.file)
        print(f"a1={r['a1']:.6g} b1={r['b1']:.2f} c1={r['c1']:.6g} d1={r['d1']:.4g} "
              f"coeff1={r['cf']:.6g} unmodeled_post_slope={r['unmod']:.1f}% rail={r['rail'] or 'none'}")
        out = a.out or str(Path(a.file).with_suffix("")) + "_soft_pvii.dat"
        np.savetxt(out, np.c_[r["E"], r["red"], r["unit"]], fmt="%.6f",
                   header="Energy_eV  reduced_area_norm(280-310)  norm_unit_edge_jump")
        print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
