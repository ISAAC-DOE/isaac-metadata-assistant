#!/usr/bin/env python3
"""Generate SYNTHETIC mock intake artifacts for the ISAAC XANES demo.

Everything this script writes is OBVIOUSLY FAKE: made-up people (Ada Lovelace,
Grace Hopper), a fictional 2099 beamline session, and scientifically-plausible
but invented CuO / Cu K-edge XANES numbers. It contains NO real SLAC, SSRL, or
otherwise proprietary data.

It writes only into the repository's ``examples/`` directory, which is
gitignored (see ``.gitignore``: ``examples/*`` except ``examples/README.md``).
Nothing under ``examples/`` is ever committed. This lets a developer exercise
``/isaac-draft`` end-to-end without real experiment data on the machine.

Committed, stable copies of the text artifacts live under
``tests/fixtures/synthetic/`` for Phase 3 tests; this generator reproduces the
same content into ``examples/``.

Spreadsheet handling: if ``openpyxl`` is importable, a real ``mock_campaign.xlsx``
(with Campaign Info / Sample / Configurations tabs) is written. openpyxl is NOT
yet a project dependency, so by default the script falls back to a dependency-free
``mock_campaign.csv`` carrying the same rows, plus a short note. Either way the
script always succeeds.

Usage:
    python scripts/make_synthetic_examples.py

The script is idempotent (re-running overwrites with identical content) and
prints exactly which files it wrote.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Synthetic content. All values below are invented for demo purposes only.
# ---------------------------------------------------------------------------

# Campaign spreadsheet, as (section, [(field, value, unit, notes), ...]).
# Mirrors the real SSRL template's tabs but with clearly-fake identifiers.
SECTIONS: list[tuple[str, list[tuple[str, str, str, str]]]] = [
    (
        "Campaign Info",
        [
            ("facility_name", "SSRL", "", "synthetic demo data - not real"),
            ("organization", "SLAC", "", ""),
            ("site", "SSRL", "", ""),
            ("beamline", "15-2", "", ""),
            ("endstation", "XES", "", ""),
            ("technique", "HERFD-XAS", "", ""),
            ("proposal_id", "SYN-2099-000", "", "fake proposal id"),
            ("session_id", "2099_run_000", "", "fake beamline session"),
            ("lead_experimenter", "Ada Lovelace", "", "fictional person"),
            ("co_experimenter", "Grace Hopper", "", "fictional person"),
            ("acquired_start_utc", "2099-03-01T18:30:00Z", "", ""),
            ("acquired_end_utc", "2099-03-01T18:45:00Z", "", ""),
            ("created_utc", "2099-03-05T20:15:00Z", "", ""),
        ],
    ),
    (
        "Sample",
        [
            ("material_name", "Copper(II) Oxide", "", ""),
            ("formula", "CuO2", "", ""),
            ("provenance", "commercial", "", "synthetic vendor"),
            ("sample_form", "pellet", "", ""),
            ("CuO2_mass_fraction", "0.001", "", ""),
            ("sucrose_mass_fraction", "0.999", "", "diluent matrix"),
            ("pellet_diameter_mm", "7.0", "mm", ""),
        ],
    ),
    (
        "Configurations",
        [
            ("environment", "ex_situ", "", ""),
            ("temperature_K", "298", "K", ""),
            ("atmosphere", "air", "", ""),
            ("monochromator_crystal", "Si(311)", "", ""),
            ("spectrometer_geometry", "Von_Hamos", "", ""),
            ("detector_model", "Pilatus_100K", "", ""),
            ("incident_energy_start_eV", "8970", "eV", ""),
            ("incident_energy_end_eV", "9000", "eV", ""),
            ("n_scans", "6", "", ""),
            ("qc_status", "valid", "", ""),
        ],
    ),
]


def _campaign_csv() -> str:
    """Flatten SECTIONS into a single dependency-free CSV string.

    No value contains a comma, so a plain join is safe and keeps the output
    byte-stable (and identical to the committed fixture)."""
    lines = ["section,field,value,unit,notes"]
    for section, rows in SECTIONS:
        for field, value, unit, notes in rows:
            lines.append(f"{section},{field},{value},{unit},{notes}")
    return "\n".join(lines) + "\n"


CAMPAIGN_CSV = _campaign_csv()

XLSX_MISSING_NOTE = """\
# mock_campaign.xlsx not generated

`openpyxl` is not installed in this environment, so `make_synthetic_examples.py`
wrote a dependency-free `mock_campaign.csv` with the same synthetic rows instead
of a real `.xlsx` workbook.

Once `openpyxl` lands as a project dependency (planned in Phase 3, alongside the
deterministic `.xlsx` parser), re-run:

    python scripts/make_synthetic_examples.py

and a real multi-tab `mock_campaign.xlsx` (Campaign Info / Sample /
Configurations) will be produced here instead.

This file, like everything under `examples/`, is SYNTHETIC and gitignored.
"""

RAW_SCAN_LISTING = """\
# SYNTHETIC file listing - fake `ls -R` output. NOT real SLAC data.
# Produced by scripts/make_synthetic_examples.py for the ISAAC intake demo.
# Archive root and run id are fictional (year 2099).

ssrl-archive://BL15-2/2099_run_000/:
metadata/
notebooks/
raw/
reduced/

ssrl-archive://BL15-2/2099_run_000/metadata/:
mock_campaign.csv
webform_dump.txt

ssrl-archive://BL15-2/2099_run_000/notebooks/:
xanes_reduction_v2.ipynb

ssrl-archive://BL15-2/2099_run_000/raw/:
CuO2_scan_001.h5
CuO2_scan_002.h5
CuO2_scan_003.h5
CuO2_scan_004.h5
CuO2_scan_005.h5
CuO2_scan_006.h5

ssrl-archive://BL15-2/2099_run_000/reduced/:
CuO2_merged.xdi
"""

WEBFORM_DUMP = """\
# SYNTHETIC web-form dump - plain-text stand-in for SSRL web-form screenshots.
# NOT real data. Lists the field: value pairs a screenshot would show, grouped
# by the form's sections. Produced by scripts/make_synthetic_examples.py.

[Session details]
Session title: HERFD-XAS - BL15-2
Facility: SSRL
Beamline: 15-2
Endstation: XES
Proposal: SYN-2099-000
Lead experimenter: Ada Lovelace
Co-experimenter: Grace Hopper
Acquired start (UTC): 2099-03-01 18:30
Acquired end (UTC): 2099-03-01 18:45

[Sample details]
Sample name: Copper(II) Oxide
Chemical formula: CuO2
Physical form: pellet
Provenance: commercial (synthetic vendor)
CuO2 mass fraction: 0.001
Sucrose mass fraction: 0.999
Pellet diameter: 7 mm

[Conditions]
Environment: ex_situ
Temperature: 298 K
Atmosphere: air
Monochromator crystal: Si(311)
Spectrometer geometry: Von Hamos
Detector: Pilatus 100K
Incident energy range: 8970-9000 eV
Number of scans: 6
QC status: valid
"""


def _build_xlsx(path: Path) -> None:
    """Write a multi-tab workbook mirroring SECTIONS. Requires openpyxl."""
    from openpyxl import Workbook  # local import: optional dependency

    wb = Workbook()
    # Drop the default sheet openpyxl creates so tab order matches SECTIONS.
    wb.remove(wb.active)
    for section, rows in SECTIONS:
        ws = wb.create_sheet(title=section)
        ws.append(["field", "value", "unit", "notes"])
        for field, value, unit, notes in rows:
            ws.append([field, value, unit, notes])
    wb.save(path)


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    examples = root / "examples"
    examples.mkdir(exist_ok=True)

    written: list[Path] = []

    # Spreadsheet: real .xlsx if openpyxl is available, else CSV fallback.
    try:
        import openpyxl  # noqa: F401  (presence check only)

        xlsx_path = examples / "mock_campaign.xlsx"
        _build_xlsx(xlsx_path)
        written.append(xlsx_path)
    except ImportError:
        print(
            "openpyxl not installed - writing dependency-free mock_campaign.csv "
            "instead of mock_campaign.xlsx (see the .md note)."
        )
        csv_path = examples / "mock_campaign.csv"
        csv_path.write_text(CAMPAIGN_CSV, encoding="utf-8")
        written.append(csv_path)
        note_path = examples / "mock_campaign_xlsx_note.md"
        note_path.write_text(XLSX_MISSING_NOTE, encoding="utf-8")
        written.append(note_path)

    # Text artifacts (always written, dependency-free).
    listing_path = examples / "raw_scan_listing.txt"
    listing_path.write_text(RAW_SCAN_LISTING, encoding="utf-8")
    written.append(listing_path)

    webform_path = examples / "webform_dump.txt"
    webform_path.write_text(WEBFORM_DUMP, encoding="utf-8")
    written.append(webform_path)

    print(f"Wrote {len(written)} synthetic artifact(s) into {examples}/ (gitignored):")
    for p in written:
        print(f"  {p.relative_to(root)}  ({p.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
