# Synthetic XANES demo — reproducible walkthrough

This is the end-to-end demo you can run in front of a reviewer. It uses **only committed
synthetic fixtures** (a fake year-2099 SSRL session — no real SLAC/SSRL data), and it
regenerates the committed sample record byte-for-byte.

What it demonstrates: **scattered structured metadata → an evidence-checked draft → the parts
a human must supply → an official ISAAC v1.05 record + evidence sidecar**, with nothing
guessed by the system.

## Prerequisites (one-time)

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

## The inputs (all synthetic, all committed)

| File | Role |
|---|---|
| `tests/fixtures/synthetic/mock_campaign.csv` | A structured campaign metadata sheet (facility, sample, configuration, QC) |
| `tests/fixtures/synthetic/raw_scan_listing.txt` | A fake `ls -R` of the data archive — gives asset URIs, **no hashes** |
| `tests/fixtures/synthetic/xanes_completion_answers.json` | **Simulated human answers** — stands in for what a person types in `/isaac-complete` |

## Step 1 — run the demo driver

```bash
.venv/bin/python scripts/run_synthetic_demo.py
```

This runs the real pipeline (`build_draft → validate_draft → apply_answers → export_draft`)
and writes the record + sidecar to `/tmp/isaac-demo/`. Expected output:

```
[1] build_draft  (deterministic extraction, no guessing)
      -> 26 evidenced fields, 0 assets, 5 pending blocker(s)
         pending[asset]: What is the sha256 of ssrl-archive://BL15-2/2099_run_000/notebooks/xanes_reduction_v2.ipynb?
         pending[asset]: What is the sha256 of ssrl-archive://BL15-2/2099_run_000/reduced/CuO2_merged.xdi?
         pending[asset]: What is the sha256 of ssrl-archive://BL15-2/2099_run_000/raw/?
         pending[series]: Provide/point to the reduced spectrum (the .xdi reduction_product) so measurement.series can be built.
         pending[descriptor]: Provide at least one descriptor (e.g. XANES inflection-point energy + uncertainty) — an evidence record requires descriptors.

[2] validate_draft  (no-guessing checks)
      draft ok: True  (pending blockers are surfaced, never guessed)

[3] apply_answers  (simulated human answers -> user_confirmation evidence)
      -> 0 pending remaining, 3 assets now resolved (sha256 supplied)

[4] export_draft  (schema-gated transform)
      official schema valid: True  (ISAAC v1.05)
      record_id: 01JQZ0SYNTHXANESDEMO000000
      wrote: /tmp/isaac-demo/01JQZ0SYNTHXANESDEMO000000.json
      wrote: /tmp/isaac-demo/01JQZ0SYNTHXANESDEMO000000.evidence.json

[5] reproducibility check
      record byte-identical to committed docs/samples sample: True
      sidecar generated_utc is wall-clock (not byte-identical, by design)
```

The five `pending[...]` lines are the whole point: the deterministic extractor **knows it needs**
three file hashes, the reduced spectrum, and a descriptor, and it **refuses to invent any of
them**. They become the exact questions `/isaac-complete` asks. In the demo they are answered by
the committed `xanes_completion_answers.json` fixture.

## Step 2 — validate the generated record with the official CLI

```bash
.venv/bin/isaac validate /tmp/isaac-demo/01JQZ0SYNTHXANESDEMO000000.json --official
.venv/bin/isaac audit --records-dir /tmp/isaac-demo
```

Expected output:

```
PASS — valid against official ISAAC schema v1.05

PASS  01JQZ0SYNTHXANESDEMO000000.json  (0 schema errors, evidence 26/26)

1 records audited, 0 failing official validation
```

`evidence 26/26` means every dotted-path evidence entry in the sidecar resolves to a real field
in the record (0 dangling). The audit is the deterministic check that the record is schema-valid
**and** its evidence trail is intact.

## The committed sample (`docs/samples/`)

The same two artifacts are committed so reviewers can read them without running anything:

| File | What it is |
|---|---|
| `docs/samples/01JQZ0SYNTHXANESDEMO000000.json` | The official ISAAC v1.05 record (validates, audits clean) |
| `docs/samples/01JQZ0SYNTHXANESDEMO000000.evidence.json` | The evidence sidecar — official JSON-path → source/evidence |
| `docs/samples/README.md` | States they are synthetic and how they were produced |

For a field-by-field tour of these two files — what was extracted, what a human confirmed, and what
the pipeline refused to guess — see [`sample-record-walkthrough.md`](sample-record-walkthrough.md).

You can validate the committed copies directly:

```bash
.venv/bin/isaac validate docs/samples/01JQZ0SYNTHXANESDEMO000000.json --official
.venv/bin/isaac audit --records-dir docs/samples
```

## Reproducibility — what is and isn't byte-identical

- **The record is byte-identical.** `scripts/run_synthetic_demo.py` pins the record id
  (`01JQZ0SYNTHXANESDEMO000000`) and `created_utc` (`2099-03-05T20:15:00Z`), so the regenerated
  `…/01JQZ0SYNTHXANESDEMO000000.json` matches `docs/samples/…json` byte-for-byte (the script
  asserts this in step [5]).
- **The sidecar is not byte-identical.** `export.build_sidecar` stamps `generated_utc` with the
  real wall clock; every *other* field matches the committed sidecar. This is by design and the
  docs do not claim sidecar byte-identity.

## What this demo does and does not cover

- **Deterministic today:** extraction from the structured campaign sheet + the file listing,
  draft no-guessing validation, export to the official schema, and audit — all zero-LLM.
- **Human-supplied (not guessed):** file `sha256`s, the reduced spectrum (`measurement.series`),
  at least one descriptor, and the absorption edge. The demo supplies these from the answers
  fixture; in real use they come through `/isaac-complete`.
- **Not covered in this demo run:** LLM-assisted extraction of screenshots/PDFs/notes/web-form
  dumps (designed in `docs/extraction.md`, **not implemented**); the Graphify memory/query plane;
  the non-gating portal soft-warning tier (`isaac validate --warnings` — built, but not exercised
  here); and the advisory AI review placeholder — see `README.md` and `docs/architecture.md`.
