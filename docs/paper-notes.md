# Paper / poster notes — ISAAC Metadata Assistant

Working notes for an intern paper, poster, or presentation. Written to be readable and reusable,
but every claim here matches what the repo actually does today. Where something is future
work, it is labeled as such — do not present future work as a current result.

## Title / one-liner

**ISAAC Metadata Assistant: turning scattered experiment metadata into evidence-grounded, schema-valid
records without guessing.**

## 1. Motivation

Synchrotron catalysis experiments (e.g. X-ray absorption / XANES-family measurements at SSRL)
produce metadata scattered across spreadsheets, beamline web forms, notebooks, and file archives.
Turning that into a clean, machine-readable record is slow and error-prone, and the DOE-BES ISAAC
effort defines an official "AI-ready" record standard that such records must match.

The tempting shortcut — have an AI just *fill in* a record — is exactly the wrong move for science:
a plausible-but-invented value (a hash, a units string, a peak energy) is worse than a blank. The
goal here is an assistant that **drafts fast, cites evidence for everything, and refuses to guess**,
producing records that validate against the official ISAAC schema.

## 2. Approach / methods

The core idea is a **two-layer pipeline** with a strict boundary between authoring and truth.

1. **Draft layer (authoring).** Extraction produces a *draft* in an evidence-envelope format:
   every field is `{value, unit?, status, evidence[]}`. A value only enters the draft if a source
   supports it, with a precise locator (which sheet cell, which line of the file listing). Values the
   system cannot support are not invented — they are recorded as **`pending[]` blockers** (things a
   human must supply) or **`implicit[]` candidates** (inferences with no official field).

2. **Truth layer (export + validation).** A deterministic transform drops the envelope, maps each
   value to its official JSON-path, and validates the result against the vendored **official ISAAC
   v1.05 schema**. Export is *gated*: it refuses unless the draft passes no-guessing checks **and**
   the produced record passes the official schema. Because the official record format has no room for
   per-field provenance (`additionalProperties: false`), evidence is preserved in a separate
   **sidecar** keyed by official JSON-path.

**No-guessing, concretely.** In the demo, deterministic extraction of a campaign sheet + file listing
yields a draft with **26 evidenced fields** but **5 open blockers**: three file `sha256` hashes, the
reduced spectrum, and at least one descriptor. The system leaves these open rather than fabricating
them; they become the exact questions a human answers in the completion step, and each answer is
stored as `user_confirmation` evidence.

**Two planes.** A deterministic *truth plane* (schema + validators + export + audit) decides validity;
an optional *memory/query plane* (a Graphify knowledge graph) provides context and search but can
never authorize a record. The truth plane is verified to never import the graph layer.

## 3. Current prototype status (what actually works)

- Deterministic extraction from a structured campaign sheet (`.csv`/`.xlsx`) and a raw file listing.
- Draft assembly with per-field evidence, `implicit[]` inferences, and `pending[]` blockers.
- No-guessing draft validation.
- Completion: applying human answers to blockers as `user_confirmation` evidence (no invented values).
- Schema-gated export to an official ISAAC v1.05 record **plus** an evidence sidecar.
- A deterministic CLI: `isaac validate | export | audit | new-id`.
- A reproducible synthetic end-to-end demo (`scripts/run_synthetic_demo.py`) that regenerates a
  committed sample record byte-for-byte.
- **The full test suite passes**, including a test that the truth core never imports the graph layer or the advisory
  soft-warning seam.

## 4. Validation strategy

Records pass through staged checks, each with a fixed authority (the AI never overrides code):

1. **Draft no-guessing validation** — gates authoring (evidence required, missing ⇒ null, assets need
   a real sha256).
2. **Official ISAAC v1.05 schema validation** — gates export (jsonschema, Draft 2020-12).
3. **Portal-style advisory soft-warnings** (`portal_warnings.py` · `--warnings`) — a **non-gating**
   local seam (never blocks export); **not** upstream parity. See `docs/portal-warnings.md`.
4. **Advisory AI scientific review** — **placeholder only**; advisory, never marks valid/invalid,
   never mutates, not wired into export.
5. **Human review** — the final decider for ambiguous science or policy.

The **audit** ties stages 1–2 together on stored records: every record re-validates against the schema
and every sidecar evidence path resolves (0 dangling).

## 5. Data governance & safety

- **Synthetic-first.** All fixtures are unmistakably fake (a year-2099 SSRL session, fictional people).
  The demo touches no real SLAC/SSRL data.
- **`examples/` is gitignored.** Real artifacts (spreadsheets, screenshots, PDFs, raw listings) stay
  local and are never committed; processing real data requires explicit approval (`docs/intake.md`).
- **No fabrication.** The system never invents scientific values, hashes, URIs, units, or timestamps.
- **Deterministic core.** Validation and export are LLM-free and reproducible; nothing in the truth
  path depends on a model or the network.

## 6. Results so far

On the synthetic XANES-family campaign, the pipeline produces official record
`01JQZ0SYNTHXANESDEMO000000`:

- **26** evidenced fields extracted deterministically; **5** blockers surfaced (never guessed).
- After completion: **0** blockers remaining, **3** assets resolved (hashes from human answers).
- The record **validates against the official ISAAC v1.05 schema** and passes a clean audit
  (`evidence 33/33`, 0 dangling sidecar paths).
- The record is **byte-identical reproducible** via `scripts/run_synthetic_demo.py`; the sidecar is
  identical except its wall-clock `generated_utc` field.
- Every scientific value traces to a committed synthetic fixture — a test asserts nothing is fabricated.
- A later hardening pass closed a truth gap the audit could not previously see: the evidence
  denominator now comes from the record's own content (25 scalar fields + 8 block targets — the
  spectrum, the QC verdict, every asset, the descriptor, every contributor) instead of the sidecar's
  own keys, so a spectrum or QC verdict with no evidence can no longer export undetected. The same
  pass removed a silent `qc.status = "valid"` default and added strict `sha256` format checking.

*(Numbers to quote on a poster: 1 official record, 26 evidenced fields, 5 blockers correctly refused
then human-answered, 174 passing Python tests, 0 audit failures.)*

## 7. Limitations (state these honestly)

- **One path only:** a single XANES-family / characterization record on synthetic structured input.
- **Extraction is structured-only:** screenshots, PDFs, notes, and web-form dumps are **not** parsed
  yet (designed in `docs/extraction.md`, not implemented).
- **Completion is simulated** in the demo (an answers fixture stands in for a human at
  `/isaac-complete`).
- **The sidecar is an assistant convention,** not (yet) an official ISAAC artifact — pending mentor
  input.
- **The advisory review layer is a placeholder;** it performs no scientific checks yet.
- **Graphify is optional.** Its query/memory layer (routing, `/isaac-query`, graceful-degradation + freshness tests) is built; a deeper behavioral routing simulation is still future work.

## 8. Next work

- Wire real (LLM-assisted) extraction for unstructured artifacts, still evidence-cited and
  no-guessing (screenshots/PDF/notes/web-form).
- Extend the Graphify memory/query layer beyond the current routing + graceful-degradation tests to
  a deeper behavioral routing simulation.
- A non-gating advisory soft-warning seam now exists (`portal_warnings.py`); if approved, replace the
  local heuristics with **true portal parity** by vendoring the upstream `portal/validation.py`.
- Grow the advisory scientific review from placeholder to real checks (still advisory-only).
- With explicit approval, add a sanitized real-data path and additional record domains beyond XANES.

## Suggested figures for a poster

- The pipeline diagram from `docs/architecture.md`.
- The Step-1 demo output showing the **5 refused blockers** (the no-guessing moment).
- A side-by-side of one draft field `{value, status, evidence}` and its official record value + sidecar
  entry (shows where provenance goes after export).
