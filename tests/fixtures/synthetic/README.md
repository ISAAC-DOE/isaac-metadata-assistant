# tests/fixtures/synthetic/

Committed, stable, **synthetic** intake artifacts — safe to commit, **never real data**.

Unlike `examples/` (gitignored, holds real user artifacts), these files are checked in
so Phase 3 extraction tests have deterministic inputs. Everything here is obviously fake:
fictional people (Ada Lovelace, Grace Hopper), a made-up 2099 SSRL beamline session, and
invented-but-plausible CuO / Cu K-edge XANES values. No real SLAC/SSRL/proprietary data.

| File | What it stands in for |
|---|---|
| `mock_campaign.csv` | The SSRL campaign metadata sheet (Campaign Info / Sample / Configurations). The `.xlsx` variant is produced into `examples/` at runtime once `openpyxl` is available. |
| `raw_scan_listing.txt` | A fake `ls -R` listing of scan files under `ssrl-archive://BL15-2/2099_run_000/`. |
| `webform_dump.txt` | A plain-text stand-in for the SSRL web-form screenshots (field: value pairs). |

These are byte-identical to what `scripts/make_synthetic_examples.py` writes into `examples/`.
To refresh the working set locally, run `python scripts/make_synthetic_examples.py`.

See `docs/intake.md` for the intake spec and `schema/isaac_record_v1.json` for the record authority.
