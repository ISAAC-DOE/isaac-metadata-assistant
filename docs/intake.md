# ISAAC Metadata Assistant — Artifact Intake (XANES / characterization path)

**Status:** drafted 2026-07-06 · **Scope:** the MVP characterization / XANES path (see
`docs/proposal-v2.md` §7). This document defines *what* `/isaac-draft` ingests from `examples/`
and *how each artifact type is allowed to be handled*. It does not define record structure — the
vendored official schema `schema/isaac_record_v1.json` (v1.05) is the sole authority on that.

## 1. Purpose

`/isaac-draft` reads user-supplied experiment artifacts from `examples/` and extracts candidate
metadata into a draft (`drafts/<name>.draft.json`, envelope format), citing each value back to its
source file and locator. This doc specifies the accepted artifact types for the XANES path, which
ones a deterministic parser can read locally, and which ones require a model — the distinction that
drives data governance. The field-by-field mapping from these artifacts into official JSON-paths
lives in `docs/proposal-v2.md` (§3 record format and the §7 MVP walk-through); this doc is about the
*inputs* and their *handling constraints*, not the target shape.

To work without any real data, run `python scripts/make_synthetic_examples.py` to populate
`examples/` with the synthetic mock artifacts described below (see also
`tests/fixtures/synthetic/` for the committed copies).

## 2. Accepted artifact types

| Artifact type | Example filename | Parsed by | Safe to parse locally? | May be sent to an external model/tool? |
|---|---|---|---|---|
| Excel metadata sheet (`.xlsx`) | `mock_campaign.xlsx` | **Deterministic** (openpyxl, planned Phase 3) | **Yes** — read cell-by-cell, no model | **No** (default) |
| Raw file listing (text) | `raw_scan_listing.txt` | **Deterministic** (text / line parse) | **Yes** — plain text, no model | **No** (default) |
| Structured export (CSV / JSON) | `mock_campaign.csv` | **Deterministic** (csv / json parse) | **Yes** — no model | **No** (default) |
| Web-form screenshots (PNG / JPG) | `webform_sample_details.png` | **LLM-assisted** (vision) | **No** — pixels require a model to read | **No by default** — needs a data-governance decision before any real file |
| Narrative / protocol PDF | `isaac_narrative.pdf` | **LLM-assisted** (+ deterministic text-layer extract where a real text layer exists) | **Partial** — an embedded text layer is local; scanned/image pages need a model | **No by default** — governance decision before any real file |
| Free-text notes | `notes.txt`, `webform_dump.txt` | **LLM-assisted** (reading is local; interpretation/extraction is the model) | **Read locally, yes; interpret, no** | **No by default** — governance decision before any real file |

Notes on the table:

- **"Parsed by" = deterministic** means a plain Python parser (no LLM) reads the bytes and pulls
  values with an exact locator (sheet/cell, line number). These are the trustworthy, reproducible
  inputs and are the backbone of the MVP.
- **"Parsed by" = LLM-assisted** means a model must interpret the artifact (read a screenshot, OCR a
  scanned page, pull structure from prose). The plain-text stand-in `webform_dump.txt` exists so the
  synthetic demo can exercise the *screenshot* path deterministically without shipping image files.
- The **"May be sent external" default is NO for every row.** The deterministic parsers never need an
  external service. The LLM-assisted rows are the only ones where reading the artifact implies sending
  its contents to a model, and that is exactly the step a data-governance decision must gate (see §3).

## 3. Data-governance red lines

These are hard rules, not preferences:

1. **`examples/` stays gitignored, always.** `.gitignore` ignores `examples/*` except
   `examples/README.md`. Nothing under `examples/` is ever committed — it may hold sensitive
   experiment data. Committed test inputs go under `tests/fixtures/synthetic/` and must be synthetic.
2. **No real data is processed until the user explicitly provides it.** The default working set is
   the synthetic mock artifacts from `scripts/make_synthetic_examples.py`. Development, demos, and
   tests run on synthetic data.
3. **No real artifact that requires a model to read leaves the machine without explicit approval.**
   Deterministic-local parsing (`.xlsx`, text listings, CSV/JSON) is always fine. But screenshots,
   scanned PDFs, and free-text notes can only be extracted by having a model read them — for *real*
   (non-synthetic) files that is a data-governance decision the user and mentors must approve first.
   For synthetic data it is fine by construction (there is nothing sensitive to leak).
4. **Graphify (memory/query plane) runs key-less**, so no artifact content is routed to an external
   API through it (see `docs/proposal-v2.md` §6). Governance concern is limited to the LLM-assisted
   extraction step in row 4–6 above.

## 4. What is safe to parse locally vs. what needs a model

Structured, byte-addressable artifacts — the Excel sheet, CSV/JSON exports, and raw file listings —
are **safe to parse entirely locally** with deterministic code: no model, no network, exact
locators, reproducible output. These carry most of the campaign/sample/configuration metadata and
should always be preferred as the source of a value. Everything that only exists as **pixels or
prose** — web-form screenshots, scanned PDF pages, free-text notes — **needs a model** to turn into
structured fields, because there is no deterministic way to read them. That model-read step is the
single point where artifact contents would be exposed to an external service, so it is the one the
data-governance red lines gate: allowed freely for synthetic data, and only after explicit user +
mentor approval for any real file.

## 5. Cross-references

- **Field mapping (artifact value → official JSON-path):** `docs/proposal-v2.md` §3 (draft → record)
  and §7 (the MVP XANES walk-through, including which values are recorded as `implicit` inferences).
- **Record authority:** `schema/isaac_record_v1.json` (official v1.05) — the source of truth for
  structure, required fields, and vocabulary. This intake doc must never contradict it.
- **Golden target shape:** `tests/fixtures/official/ex_situ_xanes_cuo2_record.json`.
- **Synthetic working set:** `scripts/make_synthetic_examples.py` (writes into `examples/`) and the
  committed copies under `tests/fixtures/synthetic/`.
