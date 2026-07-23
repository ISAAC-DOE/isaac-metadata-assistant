# Phase 31 — Synthetic/Public File Ingestion (P31.0 proof gate + plan)

Status: **P31.0 + P31.1 COMPLETE (2026-07-22).** Human decision 2026-07-22: **Phase 31 is RECONCILIATION-ONLY**
(§11) — the confirmed-write surface is NOT extended; CSV ingestion parses + reconciles + reviews evidence and
never mutates the mapped official fields. Active slice: **P31.2 (reconciliation staging).**
Baseline for P31.2: `main @ 0387d72` · CI green · Railway synthetic-only · backend 866 · frontend 525.

Derived from a targeted read-only audit (extract layer, schema, upload seam, deps — done by the orchestrator with `rg`/`Read`, no swarm). Obeys the master ledger; not a competing master plan.

**Governing principle:** ingestion is synthetic/public-only, deterministic, bounded, authenticated, reviewable, candidate-producing, evidence-producing, human-confirmed, Workspace-subordinate, safe to disable/reset/delete. Flow: `file → ingress validation → bounded in-memory read → deterministic parser → candidates + evidence locators → human review → explicit confirm → version-gated mutation`. NEVER `file → parser → silent write`. No LLM, no real/private data, no Project-Memory-as-evidence, no candidate auto-promotion.

---

## 1. Repository evidence (what already exists)

- **A deterministic parser already exists**: `src/isaac_records/extract/structured.py` `parse_structured()` reads a campaign metadata sheet (`.csv` via stdlib `csv.DictReader`; `.xlsx` via `openpyxl`), maps sheet `field`→ official dotted path via an explicit `FIELD_MAP` (e.g. `beamline→system.facility.beamline`, `formula→sample.material.formula`, `CuO2_mass_fraction→sample.composition.CuO2_mass_fraction (float)`), coerces to the tightest JSON type, skips unmapped rows, and attaches a `spreadsheet` evidence entry per field `{source_type, source_file, locator (CSV row / xlsx cell), quote}`. Tested: `tests/test_extract_structured.py`. This is EXACTLY the candidate+evidence shape ingestion needs.
- **A governance upload seam already exists**: `POST /api/uploads` (`routes.py:1077`) is an explicit REFUSAL tied to runtime-mode ("real or private data upload is approval-gated and not enabled").
- **Confirmation + classification + version machinery already exists** (reuse, do not rebuild): P29.6 `proposeForField`/`confirmProposal` (staged candidate → explicit confirm → `If-Match` mutation, stale/412 refuse), P28.4 `classify_fields` (5 evidence classes), P27 version/atomic/lock, reset/cleanup contract.
- **`openpyxl>=3.1` is already a declared dependency** (`pyproject.toml`), so `.xlsx` needs no NEW dep — but xlsx is a ZIP container (archive/entity attack surface); CSV is plain text (stdlib, minimal surface).

## 2. Format evaluation (scored; only repo/domain-grounded candidates)

| Format | Repo-grounded? | Public spec | Deterministic parse | Existing safe parser | New dep | Attack surface | Field-mapping clarity | Verdict |
|---|---|---|---|---|---|---|---|---|
| **CSV campaign sheet** | **YES** (parse_structured + FIELD_MAP + tests) | RFC 4180 | yes | **yes (stdlib csv)** | **none** | **low** (text; only formula-injection) | high (FIELD_MAP) | **SELECTED (initial)** |
| XLSX campaign sheet | yes (same parser) | ECMA-376 | yes | yes (openpyxl, already a dep) | none | medium (ZIP container) | high | DEFER (easy later add; larger surface) |
| JSON metadata | partial (our OUTPUT format) | RFC 8259 | yes | no (would be new) | none | low | n/a (no input mapping) | rejected — JSON is our export, not the scientist's input artifact |
| HDF5 / NeXus | no | yes | binary | no (native h5py) | native lib | HIGH (binary) | none | rejected — no repo evidence, native crash risk |
| CIF | no | yes | text-ish | no | new parser | medium | none | rejected — no repo evidence |
| XML / ZIP / Office / PDF / images / arbitrary text / binary instrument | no | — | — | no | — | HIGH (XXE/bombs/native) | none | rejected — no evidence; dangerous categories prohibited |

**Decision: the single initial format is CSV** (the narrow `field,value,unit,notes`-style campaign metadata table already parsed by `extract.structured`). xlsx is a documented easy follow-on (parser + dep exist) but deferred to keep the first release narrowest and avoid the ZIP surface until CSV is proven. **No human gate:** the format is defensibly derivable from an existing tested parser; no new dependency, service, secret, storage, or real data is required.

## 3. Architecture (smallest; reuse everything)

- **Bounded IN-MEMORY read (no temp file).** CSV files are tiny (≤256 KB cap); read the uploaded bytes into memory, parse, discard. This ELIMINATES the entire filesystem-safety threat category (no temp path, no traversal, no predictable filename, no cleanup-after-crash, no public serving of raw uploads) — the safest possible posture. The filename is used only as a sanitized basename for display/evidence attribution, never as a path.
- **One authenticated ingestion endpoint** (flip/extend the `/uploads` seam or a new `/experiments/{id}/ingest`), synthetic-only (runtime-mode gated), bounded (size/rows/cols), typed rejections.
- **Parser = the existing `parse_structured`**, adapted to accept in-memory CSV text (not just a path), bounded.
- **Candidates via the existing P29.6 flow**: each parsed field → a candidate (never a write); the P28.4 classifier + P29.6 ProposalCard/confirmProposal drive review + confirm. Conflicts → conflicting candidates (no winner); same-value → no-op; unknown/unmapped → skipped (not guessed); filename-derived values (none in this format) would be labeled inferred_candidate.

## 4. Threat model (CSV-only initial)

- **Ingress:** auth (existing middleware); extension allow-list `.csv` ONLY; MIME `text/csv`/`text/plain`; max size 256 KB (checked before parse); 1 file per action; reject empty/truncated/bad-encoding (utf-8 strict). Real/private-data upload stays refused; synthetic ingestion is a distinct, warned path.
- **Filesystem:** N/A by design — bounded in-memory read, no temp file, no path from the client ever hits disk. Filename → sanitized basename for display only.
- **Parser:** bounded rows (≤500), columns (≤64), cell length (≤4 KB), parse duration; **formula-injection cells** (leading `= + - @ tab`) treated as inert TEXT, never executed, and flagged/prefixed-safe if ever re-exported; unknown columns skipped; duplicate columns → defined rule (first wins + flag); NaN/inf rejected by the numeric coercer; conflicting values preserved as conflicting candidates.
- **Data governance:** visible "synthetic/public data only — do NOT upload real/private data" warning; NO logging of file contents or extracted values (metadata-only audit event: filename, row count, candidate count); reset/deletion clears staged candidates; raw file NOT indexed in Project Memory or runtime retrieval; assistant never persists raw file contents.
- **Prohibited categories** (rejected at ingress): xlsx (deferred), HDF5, NeXus, CIF, XML, ZIP/archives, Office docs, PDFs, images, binary instrument files, arbitrary text.

## 5. Candidate + evidence contract

Each candidate retains: `{candidate_id, experiment_id, field (official dotted path), proposed_value, source_filename (basename), source_format='csv', parser_id+version, locator (CSV row+column), extraction_method, evidence_classification, explanation, source_record_rev, confirmation_state, created_utc, stale}`. NEVER a raw server path (P30.6). Evidence locator = `row N, column "<name>"` (JSON-pointer-equivalent for CSV); excerpt minimal/bounded/safe. Duplicate-of-confirmed → supporting evidence, no redundant mutation, no rev bump. Different-from-confirmed → conflicting candidate, no overwrite, human review. Two file locations disagree → both preserved, conflict flagged, no winner.

## 6. Slices (leaner than the mandate sketch — parser/confirm/classify all reused)

| Slice | Scope | Reuse |
|---|---|---|
| **P31.1** safe ingress | authenticated synthetic-only CSV endpoint; size/count/row/col limits; MIME/ext allow-list; bounded in-memory read; typed rejections | `/uploads` seam, runtime_mode |
| **P31.2** deterministic parse | adapt `parse_structured` to in-memory CSV text; bounded; malformed→typed error; no-guessing preserved | `extract.structured` (mostly wiring) |
| **P31.2** reconciliation staging (CORRECTED, §11) | enrich the preview into version-bound reconciliation items (matches/conflicts/absent) over the current record view; NO mutation, NO confirm, NO write-surface change | `evidence_trail_from_draft`, P28.4 `classify_fields`, `parse_structured_text` |
| **P31.3** reconciliation + evidence review UI | file select + synthetic-only warning + "review evidence, not a write" banner + reconciliation review (match/conflict/absent) + navigate-to-existing-manual-surface; NO Stage/Confirm/Apply/Import/Overwrite | P28.5 evidence UI, existing manual edit surface |
| **P31.4** retention/reset/degradation | in-memory (nothing persisted); reset/rev-change → stale; manual-first degradation | reset contract, useRecordSession |
| **P31.5** hosted QA + closure | valid/malformed/oversized/conflict/absent/matching/unknown/stale/reset/navigation/security/a11y | — |

## 7. MEMORY-SAFETY CORRECTION (P31.1 revalidation — the "in-memory" claim, verified against the real framework)

The P30.0/§3 claim "bounded in-memory eliminates the filesystem threat category" was UNVERIFIED. Verified now:
FastAPI + uvicorn; **`python-multipart` is NOT a dependency** → the app cannot parse multipart today, and adding
`UploadFile`/multipart would (a) add a dependency and (b) inherit Starlette's `SpooledTemporaryFile` (spools to
disk >1 MB) — reintroducing the filesystem risk. **Corrected design: accept the CSV as a RAW `text/csv` request
body (NOT multipart)**, read via a BOUNDED stream (`request.stream()` accumulating ≤ MAX+1 bytes, reject 413
before full allocation). This is genuinely all-in-memory with **no multipart, no SpooledTemporaryFile, no temp
file, no new dependency** — Outcome A (proven bounded memory) achieved BY CONSTRUCTION, not assumed. Auth
(middleware, header-only) + runtime-mode + experiment-404 + If-Match all run before the endpoint reads the body.
The filesystem-threat category is genuinely N/A because the body never touches disk — proven, not claimed.

## 8. CSV v1 CONTRACT (frozen — ONE deliberately narrow dialect; NOT "arbitrary CSV")

Named honestly: **"ISAAC campaign metadata sheet (CSV)"** — the LONG format the existing `extract.structured`
parser reads (it is campaign-specific, not a general scientific-CSV parser).
- **File count:** exactly 1 (raw body = one document; a 2nd file is impossible without multipart).
- **Extension/MIME:** `.csv` only (case-insensitive suffix; reject multi-extension like `.csv.exe`); `Content-Type`
  `text/csv` (or `text/plain`) — advisory, validated by the contract below (CSV has no magic number).
- **Encoding:** UTF-8 strict; a leading BOM tolerated deterministically (`utf-8-sig`); reject invalid UTF-8,
  reject any NUL byte. NO charset auto-detection.
- **Dialect:** comma delimiter, standard CSV quoting, universal newlines. **NO `csv.Sniffer`** / no delimiter
  inference.
- **Header:** required columns `field` + `value` (at least); optional `section`,`unit`,`notes`. Case-normalized
  (lower, trimmed). Duplicate header → reject (`duplicate_header`). Empty header → reject. Missing `field` or
  `value` → reject (`missing_required_header`). Unknown EXTRA columns → typed non-actionable WARNING, never
  mapped. Header count ≤ 64.
- **Rows:** LONG format — one row per metadata field; ALL rows apply to the ONE target experiment in the route
  path (no guessing which row belongs where). Blank-`field` rows skipped. Row count ≤ 500.
- **Cells:** max cell length 4 KB; max total decoded chars 256 KB (== file-size cap); whitespace trimmed on
  field/section/unit (parser behavior); empty `value` → `needs_confirmation`/absent (never a fabricated value).
  Numeric fields: strict Python numeric coercion per `FIELD_MAP` py_type (int/float/_to_number), NO locale
  parsing; coercion failure → `needs_confirmation` (never crash, never guess). NO unit guessing (unit is a
  passthrough column, never inferred). Candidate count ≤ 200.
- **Mapping:** `FIELD_MAP` ONLY (field → official dotted path + type); unmapped fields skipped, never guessed;
  contributors handled separately. Each candidate carries a `spreadsheet` evidence entry `{source_type,
  source_file (basename), locator ("row N, field=<field>"), quote}` — NO server path (P30.6).
- **Formula safety:** numeric fields use strict numeric grammar (a formula cell `=SUM(...)` fails coercion →
  `needs_confirmation`, never executed); text fields are inert untrusted text (kept verbatim, never executed);
  legitimate NEGATIVE numbers accepted (`-1.5` coerces fine — do NOT blanket-reject leading `-`); if any value
  is ever re-exported to CSV/spreadsheet, prefix-escape `= + - @`. Regression tests for `= + - @` in numeric AND
  text fields.

**Parser suitability:** `parse_structured` uses `FIELD_MAP`, official paths, row/field locators, skips unmapped,
never guesses units, never mutates, is deterministic + tested — SUITABLE for CSV v1, but campaign-sheet-specific;
the user-facing format is named "ISAAC campaign metadata sheet", not "scientific CSV". P31 adds an in-memory
adaptation (parse from bounded text, not a path) in the NON-truth `extract` layer; the path-based behavior stays
unchanged + tested.

## 9. P31.1 endpoint (safe ingress + read-only typed preview)

`POST /api/experiments/{id}/ingestion/csv/preview`, `Content-Type: text/csv`, raw bounded body. Order: auth
(middleware) → runtime-mode synthetic-only (else typed 403) → experiment 404 → **If-Match** (Option A: current
ETag required; stale → 412) → bounded body read (413 if > cap; reject empty/NUL/invalid-UTF-8) → CSV v1 validate
(typed errors) → in-memory `parse_structured` → typed preview `{safe_filename?, format, parser_id+version,
source_record_rev, row_count, recognized_header_count, unknown_header_warnings, candidate_count, candidates[
{field, proposed_value, value_state, evidence_classification, locator, source_format}], warnings[], }`.
**NO mutation** (read-only preview; nothing written, no rev change, no runtime-retrieval/Project-Memory
indexing, no persisted upload). Confirmation UI + staging into the P29.6 confirm flow = later slices (P31.2+).
Note: the source_filename is client-supplied metadata (a raw text/csv body has no filename) — if the FE sends an
`X-Filename` header it is sanitized to a bounded basename for display/attribution only, never a path/ID/value.

## 10. Test-first per slice; independent Opus review per release slice; verification loop per the mandate. Human gates: none (ledger §9 unchanged); stop only if a new native dep/service/real-data proves necessary (it does not — CSV is stdlib, raw-body needs no multipart dep).

## 11. P31.2 CORRECTED CONTRACT — RECONCILIATION-ONLY (human decision 2026-07-22)

**Architecture gate (proven, not assumed).** Before implementing P31.2 the orchestrator traced "candidate/
evidence staging INTO the P29.6 confirm flow" to ground truth and probed it live:

- The confirmed-mutation surface (`POST /answers` + `POST /edit` → `_answers_to_apply_shape` → `apply_answers`)
  recognizes ONLY the keys `{asset-uri, series, descriptor, descriptor_label, edge}`; unknown keys are
  deliberately ignored ("never invented into the draft").
- The CSV v1 `FIELD_MAP` produces ONLY official paths `{system.facility.*, system.technique,
  system.configuration.*, timestamps.*, sample.material.*, sample.composition.*, sample.geometry.*,
  context.*}`. **The two sets are DISJOINT.**
- Empirical probe: confirming `series` (a real blocker key) bumped rev `…077.0 → …077.1` (mutation applied);
  confirming `system.facility.beamline` (a FIELD_MAP path) returned 200 but left rev **unchanged** — a silent
  no-op. So a CSV FIELD_MAP candidate CANNOT be written through the existing confirm contract.
- Every seed record is built by `build_draft(CSV_PATH, …)`, so all 25 FIELD_MAP paths are ALREADY populated
  (extraction-backed). A re-uploaded campaign sheet is therefore *reconciliation* (agreement/conflict against
  existing values), not net-new fills. `absent_from_record` is unreachable via the canonical seeds → covered at
  the pure-builder unit level with a crafted record view.

**Decision (human, 2026-07-22): Option 1 — reconciliation-only.** The earlier "CSV candidate → confirm →
official field mutation" requirement is WITHDRAWN as insufficiently grounded in the actual confirmed-write
architecture. The confirmed-write surface (`apply_answers`/`/answers`/`/edit`) is NOT extended in Phase 31 or
Phase 32. Making additional official paths CSV-writable is deferred to a future, separately approval-gated
**"Future — CSV-Assisted Official Field Write Contract"** phase (must first define schema-path authorization,
validation, workflow invalidation, evidence effects, concurrency, and rollback). This is a deliberate authority
boundary, NOT a defect.

**Corrected Phase-31 flow:** `Upload → Parse → Reconcile (version-bound) → Review Evidence → Navigate to the
existing approved manual workflow where supported`. NEVER `Upload → Confirm → CSV field mutation`.

**P31.2 reconciliation item** (read-only; NO mutation, NO rev bump, NO workflow/export/runtime/Project-Memory
change; no winner selection): `{experiment_id, field (official path), field_label (safe display), proposed_value,
current_value (or absent), reconciliation_state ∈ {matches_current, conflicts_with_current, absent_from_record},
evidence_classification (current field's P28 class where applicable), source_name (safe basename), parser_id,
parser_version, locator (row), column, source_record_rev, stale (version-bound), explanation}`.
- **matches_current** → supporting/matching evidence; locator preserved; no mutation, no rev bump, no proposal.
- **conflicts_with_current** → BOTH values shown; conflict marked; human review; no overwrite; no winner.
- **absent_from_record** → labeled unconfirmed + absent; not written; not auto-staged into any write path.
- Two CSV rows mapping to the same field with different values → BOTH preserved (distinct row locators), no
  winner (the parser emits both in row order; reconciliation never dedupes them).
- **Stale** when the record rev changes / Reset Demo / Run Synthetic Demo / experiment switch / reparse against
  a newer record / a relevant current field changes. Backend is stateless → staleness is version-binding by
  construction (`source_record_rev`); the client detects a rev mismatch.

Implemented by ENRICHING the existing `POST /ingestion/csv/preview` endpoint (no second endpoint, no second
ETag owner, no second candidate model): the route computes the current record view (`evidence_trail_from_draft`
values + `classify_fields` classes) and passes it to `csv_ingest.build_preview`, which adds the reconciliation
fields to each item + a `reconciliation_summary` count. P31.1's ingress/limits/version-gate/leak-safety are
unchanged; the truth path (§13) is untouched; `apply_answers` is NOT modified. P31.3 builds the reconciliation/
evidence review UI (no Stage/Confirm/Apply/Import/Overwrite controls; a visible "CSV values are review evidence —
uploading does not change the official record" banner; safe actions only + navigate-to-existing-manual-surface
where the field is manually editable, else read-only evidence).
