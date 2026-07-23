# Phase 31 — Synthetic/Public File Ingestion (P31.0 proof gate + plan)

Status: **P31.0 format + threat-model proof gate COMPLETE (2026-07-22). No human gate triggered.** Active slice: **P31.1 (next).**
Baseline: `main @ b5cf608` (P30.6) · Railway synthetic-only · backend 826 · frontend 525.

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
| **P31.3** candidate/evidence staging | map parsed fields → candidates + locators; conflict/duplicate/version binding; NO mutation | P29.6 proposeForField, P28.4 classify |
| **P31.4** review + confirm UI | file select + synthetic-only warning + validation summary + candidate review + confirm/cancel | P29.6 ProposalCard/confirm, P28.5 evidence UI |
| **P31.5** retention/reset/degradation | in-memory (nothing persisted); reset clears; manual-first degradation | reset contract, useRecordSession |
| **P31.6** hosted QA + closure | valid/malformed/oversized/conflict/duplicate/inferred/unknown/confirm/cancel/stale/reset/security/a11y | — |

## 7. Test-first per slice; independent Opus review per release slice; verification loop per the mandate. Human gates: none (ledger §9 unchanged); stop only if a new native dep/service/real-data proves necessary (it does not — CSV is stdlib).
