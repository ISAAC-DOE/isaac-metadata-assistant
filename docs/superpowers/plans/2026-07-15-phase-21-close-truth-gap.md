# Phase 21 — Close the No-Guessing Truth Gap: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan slice-by-slice. Implementation is delegated to Opus 4.8 (truth-path slices) / Sonnet 5 (UI/docs slices); Fable 5 orchestrates, reviews, verifies.
> **APPROVED 2026-07-15 with guardrails** — see "Approval decisions" at the end of this document. P21B–P21D batch-approved as one truth-path arc with per-slice reports; no push until the full Phase 21 verification suite passes.

**Goal:** Make the no-guessing thesis true end-to-end: every scientific value in an exported official record is evidence-backed, user-confirmed, or explicitly pending/missing; unsupported values cannot silently export; audit coverage is computed from record content, not sidecar content; UI and docs stop overstating the guarantee.

**Architecture:** One new draft-side map (`block_evidence`) keyed by the sidecar's natural-key grammar covers block-level scientific structures (series/qc/links/attribution). `validate_draft` enforces coverage; `build_sidecar` harvests it; `transform` stops fabricating qc and stops stripping the schema-native `qc.evidence`; audit recomputes expected coverage from the record. Official schema untouched, byte-for-byte.

**Tech stack:** Existing — Python (deterministic core), pytest, FastAPI serializers, React/Vite (thin client), vitest.

## Global constraints

- `schema/isaac_record_v1.json` is vendored upstream truth — zero edits (CLAUDE.md §1).
- Truth path stays deterministic and Graphify-free (CLAUDE.md §2, §13).
- No fake evidence is ever synthesized; "missing" stays a valid honest state (CLAUDE.md §5).
- Export stays all-or-nothing: `validate_draft` → `transform` → `validate_official` → sidecar.
- Sidecar remains an assistant-side audit artifact, not an official ISAAC convention (CLAUDE.md §4).
- Every slice: small, reviewable, green tests, own commit, own report (CLAUDE.md §10, §12).
- No pushes mid-phase without explicit approval — push to `main` auto-deploys Railway + Vercel.

---

## 1. Executive summary

Verification (three subagents: Opus truth-path audit with empirical CLI tests, Sonnet UI/docs grep audit, Opus design pass; all citations spot-checked by the orchestrator against source) confirms the roadmap diagnosis and sharpens it:

- The draft validator, sidecar builder, and audit all treat `series`, `qc`, `links`, and `attribution` as opaque pass-throughs. **A fabricated spectrum with zero evidence exports to a schema-valid official record with an empty sidecar, exit 0** — empirically reproduced.
- The audit's "N/N" coverage is a referential-integrity check whose denominator comes from the sidecar itself, so it is structurally incapable of noticing the gap — also empirically reproduced ("evidence 2/2" on a record containing an unevidenced fabricated spectrum).
- Two defects the roadmap missed: `transform` **invents** `qc.status="valid"` when a draft has series but no qc (export.py:87-88), and `strip_evidence` **deletes the schema-native `measurement.qc.evidence` field** (an official string field, schema:1093-1096) from every exported record.
- sha256 `"asdf"` exports fine and becomes immutable record state (no format check at any layer; official schema has no pattern for it).
- UI and docs are mostly honest already; the residual gaps are three hardcoded literals (worst: `ExportReadiness.tsx:201` guessing `26`), two stale "137 tests" claims, and a reproducibly broken README quickstart (`.[dev]` collects 105/148 tests with 2 errors on a clean venv).

The fix is one coordinated truth-path arc (producers → enforcement → audit), then a small UI slice and a docs slice. Six slices, each independently reviewable and committable. sha256 validation belongs in this phase (two touch points in files already being edited).

## 2. Verified/falsified claim table

| # | Claim | Verdict | Key evidence | Impact |
|---|---|---|---|---|
| 1 | `validate_draft` misses series/qc/links/attribution/tags | **TRUE** | `draft_validator.py:88-116` — loops only over `fields`(:96), `assets`(:102), `descriptors_outputs`(:107), `implicit`(:113) | The most scientific block in a XANES record (the spectrum) bypasses the no-guessing gate |
| 2 | `strip_evidence` deletes series evidence so it never reaches the sidecar | **PARTIALLY TRUE** | `strip_evidence` (export.py:48-55) is a non-mutating copy-strip; the actual loss is `build_sidecar` (export.py:103-126) having no series/qc/links/attribution harvest | Outcome true, mechanism wrong — fixing `strip_evidence` alone would change nothing |
| 3 | Sidecar cannot express series/block provenance | **TRUE** | Key vocabulary fixed at export.py:103-126; `get_path` can't descend arrays (export.py:39-45, docstring :31) | No representation exists for where a spectrum came from |
| 4 | `draft_builder` drops contributor evidence while claiming sidecar deferral | **TRUE** | Comment at draft_builder.py:109-111; drop at :112-115; `parse_contributors` produces evidence (structured.py:238-245); no downstream deferral exists | Contributor provenance silently, permanently lost; comment is a false promise |
| 5 | Fabricated spectrum exports schema-valid with empty sidecar | **TRUE (empirical)** | `isaac validate --draft` PASS + `isaac export` PASS on evidence-free synthetic series; sidecar `"evidence": {}`; record contains full fabricated spectrum + auto-added `qc.status="valid"` | Strongest possible violation of the thesis, on the happy path, exit 0 |
| 6 | sha256 accepts "asdf" into immutable record state | **TRUE (empirical)** | Schema :1198-1200 bare string, no pattern; draft_validator.py:103-104 truthiness only; complete.py copies answers verbatim; export PASS with `"sha256": "asdf"`; cli.py:78-79 refuses overwrite | Integrity hash that can't verify anything, in an immutable record |
| 7 | UI hardcodes counts that should come from backend | **PARTIALLY TRUE** | Real: `ExportReadiness.tsx:201` (`coverage === 'pending' ? 26 : coverage.total`), `WorkflowSpine.tsx:50-51` skeleton copy ("reviewing 26 fields"), `assistant.ts:158,162` canned "26/26" copy. Main paths (CoverageBadge, ExperimentRow, StatusBar, live spine overrides) correctly live-wired; backend already exposes `evidence_present`/`evidence_expected` (serialize.py:82-83) | Narrow, mostly cosmetic — but `adapt.ts:164-170` also hardcodes `dangling: []` |
| 8 | Docs contain stale/false first-run/test/deployment claims | **PARTIALLY TRUE** | Stale: `final-deliverable-outline.md:95` and `paper-notes.md:104` say "137 tests" (actual: 148). Broken: README:74-76 quickstart with `.[dev]` collects 105/148 with 2 errors on a clean venv (testpaths include `apps/api/tests`, needs `api` extra) — reproduced. Deployment claims consistent. ~30 "26/26" refs accurate for the demo record but will drift when audit semantics change | README quickstart fails for a fresh evaluator — bad for the deliverable |
| A (new) | `strip_evidence` deletes schema-native `measurement.qc.evidence` | **TRUE** | Schema :1093-1096 defines `qc.evidence` (string, "REQUIRED in practice when status != valid"); golden draft carries it (cuo_xanes_draft.json:87); transform routes qc through blanket `strip_evidence` (export.py:86) which drops every key named `evidence` (:52) | Export silently deletes official scientific content from records |
| B (new) | qc has two independent defects | **TRUE** | (i) fabrication when absent (export.py:87-88); (ii) zero provenance even when sheet-sourced (committed sample's qc came from mock_campaign.csv via draft_builder.py:120-124, with no evidence trail) | Both must be fixed; fixing only the fabrication leaves qc unevidenced |

Smallest safe fix per claim (detailed in §5–§7): 1 — add block-coverage checks to `validate_draft` against `block_evidence`; 2 — extend `build_sidecar` to harvest block evidence (leave `strip_evidence` alone for series); 3 — natural-key sidecar namespaces (`series:<id>`, `qc`, `links:<rel>|<target>|<basis>`, `attribution:<name>|<role>`); 4 — route contributor evidence into `block_evidence` so the claimed deferral becomes real; 5 — closed by 1+2+3 (validator refusal gates export); 6 — `^[0-9a-f]{64}$` check in `draft_validator` + `complete` (schema edit is out of bounds; escalate the missing pattern upstream); 7 — remove the `ExportReadiness` guess, de-specify skeleton copy, update canned assistant copy; 8 — refresh the two "137" counts, fix quickstart to `.[dev,api]`; A — build qc from `draft["qc"]` directly instead of blanket-stripping; B — delete the fabrication AND evidence sheet-sourced qc.

Claim-2 correction to carry forward: **do not modify `strip_evidence`'s core behavior** for series (schema `series[]` is `additionalProperties:false`, so stripping is correct there); route qc around it instead.

## 3. Current truth-path diagram

```
files ──▶ draft_builder ─────────────────────────────▶ DRAFT
              │ contributor evidence DROPPED (:112-115,
              │ comment falsely claims sidecar deferral)
              ▼
        validate_draft ── checks: meta presence, fields envelopes,
              │           assets (sha256 truthiness only), descriptors, implicit
              │           BLIND TO: series, qc, links, attribution, tags
              ▼ ok
          transform ───── fields: envelope→value (missing dropped honestly)
              │           series/links/attribution: strip_evidence pass-through
              │           qc: strip_evidence (DELETES native qc.evidence)
              │               or FABRICATES {"status":"valid"} if absent (:87-88)
              ▼
       validate_official ── official schema (sha256 = any string)
              ▼ ok
        build_sidecar ──── harvests fields / assets: / descriptors: / implicit: ONLY
              │            series/qc/links/attribution evidence NEVER harvested
              ▼
   records/<ULID>.json + <ULID>.evidence.json   (immutable)
              ▼
           audit ───────── denominator = sidecar's own dotted keys (skips ALL ':' keys)
                           → "N/N" possible with a zero-evidence fabricated spectrum
              ▼
     API serialize ─────── evidence_present/expected passed through; dangling dropped
              ▼
          web UI ────────── mostly live-wired; ExportReadiness guesses 26; adapt.ts
                            hardcodes dangling: []
```

## 4. Proposed truth-path diagram

```
files ──▶ draft_builder ─────────────────────────────▶ DRAFT (+ block_evidence map)
              │ contributor & qc provenance → block_evidence   [P21B]
              ▼
        validate_draft ── everything current, PLUS:               [P21C]
              │   • every series_id covered in block_evidence, else error
              │   • qc present + covered when series present, else error
              │   • every link / contributor covered, else error
              │   • sha256 must match ^[0-9a-f]{64}$, else error
              │   • duplicate natural keys → error (no silent dedupe)
              │   • processing/computation present → explicit refusal (no silent drop)
              ▼ ok                                  ┌──────────────────────────────┐
          transform ───── qc built from draft["qc"] │ /isaac-complete asks only    │
              │           directly (native evidence │ validator-blocking questions;│
              │           PRESERVED); fabrication   │ answers → user_confirmation  │
              │           REMOVED; series/links/    │ entries in block_evidence;   │
              │           attribution unchanged     │ bad sha256 rejected at       │
              ▼                                     │ answer time          [P21B]  │
       validate_official ── unchanged, schema untouched └────────────────────────────┘
              ▼ ok
        build_sidecar ──── existing harvests, PLUS block_evidence passthrough:
              │            series:<id>  qc  links:<rel>|<target>|<basis>
              │            attribution:<name>|<role>                       [P21B]
              ▼
   records/<ULID>.json + <ULID>.evidence.json   (immutable, schema-identical)
              ▼
           audit ───────── expected = enumerated from RECORD content        [P21D]
                           (scalar leaves + every series/qc/link/asset/
                           descriptor/contributor; tags & created_utc exempt)
                           → "covered/expected + uncovered[] + dangling[]"
                           → old "N/N while spectrum uncovered" impossible
              ▼
     API serialize ─────── + uncovered[] + dangling[] arrays               [P21D]
              ▼
          web UI ────────── adapt.ts consumes real lists; ExportReadiness stops
                            guessing 26; skeleton/canned copy de-specified [P21E]
              ▼
            docs ────────── counts refreshed, quickstart fixed, walkthrough
                            updated to honest coverage                     [P21F]
```

## 5. Evidence coverage model

A target is **covered** iff its `block_evidence` entry (or inline envelope, for existing paths) holds ≥1 entry whose `source_type` is machine-observed (`spreadsheet`, `file_listing`, …), `user_confirmation`, or a `derivation` carrying a `rule` (documented inference — reusing `_has_observed`/`_has_derivation`, draft_validator.py:52-57). Absent → **uncovered**.

Draft representation: **one top-level `block_evidence` map**, keyed by the sidecar grammar (§6). Chosen over inline `evidence` keys (would collide with schema-native `qc.evidence` — Finding A — and re-create the blanket-strip bug) and over four per-block maps (four loops/harvesters vs. one). Example shape:

```json
"block_evidence": {
  "series:averaged_spectrum": [
    { "source_type": "user_confirmation",
      "question": "Confirm the reduced spectrum data points for series 'averaged_spectrum'.",
      "answer": "7-point .xdi reduction from CuO2_merged.xdi",
      "timestamp": "2099-03-05T21:00:00Z" }
  ],
  "qc": [
    { "source_type": "spreadsheet", "source_file": "mock_campaign.csv",
      "locator": "Sheet 'Configurations', field=qc_status", "quote": "valid" }
  ],
  "attribution:Ada Lovelace|curated_record": [
    { "source_type": "spreadsheet", "source_file": "mock_campaign.csv",
      "locator": "Sheet 'Campaign Info', field=lead_experimenter", "quote": "Ada Lovelace" }
  ]
}
```

Per-block policy:

| Block | Representation | Missing coverage → |
|---|---|---|
| scalar `fields.*` (sample/system/context/acquired timestamps) | existing envelope — **unchanged** | already enforced |
| `measurement.series[]` | record-shaped + `block_evidence["series:<id>"]` | **blocks export** |
| `measurement.qc` | record-shaped (native `evidence` string stays inside) + `block_evidence["qc"]` (provenance of the verdict — distinct from the native descriptive string) | **blocks export** when series present |
| `links[]` | record-shaped + `block_evidence["links:<rel>\|<target>\|<basis>"]` | **blocks export** (a link is a scientific claim) |
| `assets[]`, `descriptors` | existing inline evidence — **unchanged** | already enforced |
| `attribution.contributors[]` | name/role record-shaped + `block_evidence["attribution:<name>\|<role>"]` | **blocks export** |
| `timestamps.created_utc` | system-stamped | **exempt** — record-keeping, not a scientific claim |
| `tags` | plain list | **exempt** — user-authored labels; authorship is the confirmation; excluded from audit denominator |
| `measurement.processing`, `computation` | no exporter path exists | **explicit refusal** if present in a draft — never silently dropped |

Honest states (formalized; export column):

| State | Representation | Export |
|---|---|---|
| verified | machine-observed source_type | exports |
| user_confirmed | `user_confirmation` entry (complete.py:34-41) — always appended alongside machine evidence, never replacing it | exports |
| inferred | `derivation` + `rule` | exports |
| needs_confirmation | envelope status / pending blocker | **blocks** |
| missing | status `missing` + null, or omitted | **dropped from record** — stays valid ("I don't know" remains honest) |

`source_type` is preserved in draft and sidecar, so user-confirmed remains distinguishable from machine-extracted everywhere (the UI already derives display status from it — serialize.py:207-217). No AI-generated value ever becomes evidence.

## 6. Sidecar / provenance model

Extend the existing namespaced-key scheme (`assets:<id>`, `descriptors:<name>`, `implicit:<about>`) with:

```
series:<series_id>                    # one per measurement.series[] item
qc                                    # singleton — measurement has exactly one qc
links:<rel>|<target>|<basis>          # one per links[] item
attribution:<name>|<role>             # one per contributor
```

Every key component is a schema-**required** subfield (series_id :964; rel/target/basis :1116-1119; name/role :1715-1718), so the **expected key set is derivable from record content alone** — which is exactly what the honest audit denominator (§7) needs. No array indices: natural keys are stable across reordering.

Collision rules — deterministic refusal, no silent dedupe: duplicate `series_id`, duplicate `rel|target|basis` tuple, or duplicate `name|role` pair each produce a `validate_draft` error (a duplicate natural key is itself a data smell). Same person with two roles = two distinct keys, no collision.

The sidecar remains an assistant-side audit artifact (CLAUDE.md §4). No official schema change; official records stay byte-identical in shape. `implicit:*` keys stay informational (they annotate concepts with no official field, e.g. absorbing element/edge) and are not counted in coverage.

Sidecar format change is **additive** (new key namespaces in the existing `evidence` map). Old audit code would ignore them (`:`-skip); new audit reads old sidecars without error (test 19).

## 7. Export / validation / audit behavior changes

**`validate_draft` (the single enforcement point — export-blocking AND question-driving, since /isaac-complete sources questions from validator errors):**
- Coverage checks for every series / qc-when-series / link / contributor against `block_evidence`.
- sha256 regex `^[0-9a-f]{64}$` replaces the truthiness check (draft_validator.py:103-104).
- Natural-key collision errors (§6).
- `processing`/`computation` present → explicit "unsupported scientific block — out of XANES MVP scope; the exporter has no path for it" error.
- Error message shape (existing `DraftReport.err`): `✗ error  series[0] (averaged_spectrum) — series has no evidence; a spectrum must cite its reduction source or be user-confirmed`, `✗ error  qc — measurement has series but qc verdict has no evidence; confirm or supply provenance (no default 'valid')`, `✗ error  assets[1] (reduced_spectrum) — sha256 'asdf' is not a 64-char lowercase hex digest`.

**`transform`:**
- Delete the `qc = {"status": "valid"}` fabrication (export.py:87-88). Never invent a verdict. The qc enum (`valid|compromised|failed|pending`, no "unknown"; `pending` reserved for intent records) means **refuse, don't default** — an honest default does not exist in the official vocabulary.
- Build qc directly from `draft["qc"]` (already record-shaped `{status, evidence?, assumptions?, notes?}`) instead of routing through blanket `strip_evidence` — preserves the native `qc.evidence` string (Finding A). Series keep `strip_evidence` (schema forbids stray keys there; official validation remains the safety net if anything leaks).
- Everything else unchanged; `export_draft` signature and all-or-nothing flow unchanged; `now` stays injectable; no clock/network additions.

**`complete.py` / `/isaac-complete` (deterministic, validator-error-driven — no new question invention):**
- Series answers additionally write `block_evidence["series:<id>"]` as `user_confirmation` (today apply_answers sets `draft["series"]` only).
- New `qc` blocker kind when series present but qc uncovered: "What is the QC verdict for this measurement and how was it determined?" — answer validated against the schema enum, written to `draft["qc"].status` + `block_evidence["qc"]`.
- sha256 answers validated at apply time (complete.py:64-65 area): malformed hash → rejected, stays in `pending`, never written.

**`draft_builder.py`:**
- Stop dropping `parse_contributors` evidence — route it to `block_evidence["attribution:<name>|<role>"]` (machine `spreadsheet` evidence; no question needed on the synthetic path). The false comment (:109-111) becomes true by making the deferral real.
- Sheet-sourced qc gains its `block_evidence["qc"]` entry at build time (Finding B-ii).

**`audit.py`:**
- `_sidecar_coverage` → expected-vs-covered computed from **record content**: (1) scalar leaf dotted paths, excluding identity/classification (`isaac_record_version`, `record_id`, `record_type`, `record_domain`, `source_type`), `timestamps.created_utc`, and `tags`; (2) block targets — one per series_id, qc-if-present, each link tuple, each asset_id, each descriptor name, each contributor. Returns `(covered, expected, uncovered[], dangling[])`; dangling-dotted-path detection preserved.
- Render: `PASS  <ULID>.json  (0 schema errors, evidence 30/34)` + indented `uncovered:` list + existing dangling warnings. The committed demo sample audits at **30/34** (uncovered: `series:averaged_spectrum`, `qc`, 2 contributors) until regenerated through the fixed pipeline, which should yield an honest **34/34**.

**API/web serialization (minimal):** `serialize.audit_to_dict` adds `"uncovered": [...]` and `"dangling": [...]` per record (it currently drops `_dangling`); `adapt.ts` `toAuditResult` stops hardcoding `dangling: []` and consumes the real arrays. `CoverageBadge` needs no structural change — it already renders resolved/total + a dangling list + "coverage · not a verdict".

## 8. Test plan

New files: `tests/test_evidence_coverage.py`, `tests/test_audit.py` (audit currently only exercised via test_e2e.py). Extended: `tests/test_export.py`, `tests/test_complete.py`, `tests/test_draft_builder.py`, `tests/test_e2e.py`, `apps/api/tests/test_api.py`, web `__tests__`. **(neg)** = negative/regression test proving a hole closed.

| # | Test | Proves | Slice |
|---|---|---|---|
| 1 | `test_draft_builder.py::test_contributor_evidence_reaches_block_evidence` | claim 4 closed at build time | B |
| 2 | `test_export.py::test_sidecar_harvests_series_qc_links_attribution` | claims 2/3 closed | B |
| 3 | `test_export.py::test_qc_native_evidence_preserved` | Finding A closed | B |
| 4 | `test_complete.py::test_series_answer_writes_block_evidence` | completion covers series | B |
| 5 | `test_complete.py::test_valid_sha256_accepted` | 64-hex answer applies as user_confirmation | B |
| 6 | `test_evidence_coverage.py::test_fabricated_spectrum_refused` (neg) | claim 5 closed — export_draft.ok is False | C |
| 7 | `test_evidence_coverage.py::test_series_requires_evidence` (neg) | claim 1 (series) | C |
| 8 | `test_evidence_coverage.py::test_qc_requires_evidence_when_series_present` (neg) | Finding B | C |
| 9 | `test_evidence_coverage.py::test_link_requires_evidence` (neg) | claim 1 (links) | C |
| 10 | `test_evidence_coverage.py::test_attribution_requires_evidence` (neg) | claim 1 (attribution) | C |
| 11 | `test_evidence_coverage.py::test_duplicate_natural_keys_refused` (neg) | §6 collision rules | C |
| 12 | `test_evidence_coverage.py::test_unsupported_block_refused` (neg) | processing/computation never silently dropped | C |
| 13 | `test_export.py::test_qc_status_never_fabricated` (neg) | Finding B-i closed | C |
| 14 | `test_draft_builder.py::test_sha256_asdf_rejected_at_draft` (neg) | claim 6 closed at draft time | C |
| 15 | `test_complete.py::test_bad_sha256_answer_rejected_at_completion` (neg) | claim 6 closed at answer time | C |
| 16 | `test_export.py::test_tags_need_no_evidence` | tags exemption is deliberate | C |
| 17 | `test_audit.py::test_honest_denominator_counts_blocks` | claim 6→audit: expected from record content | D |
| 18 | `test_audit.py::test_no_full_coverage_while_series_uncovered` (neg) | the empirical "2/2 with fabricated spectrum" case now impossible | D |
| 19 | `test_audit.py::test_dangling_still_detected` | no regression on referential check | D |
| 20 | `test_audit.py::test_legacy_sidecar_backward_compat` | pre-change sidecar audits without crash, honestly lower | D |
| 21 | `test_e2e.py::test_full_pipeline_reaches_full_coverage` | golden path → honest M/M | D |
| 22 | `apps/api/tests/test_api.py::test_audit_response_includes_uncovered_and_dangling` | serializer contract | D |
| 23 | web `__tests__`: adapt/audit mapping + ExportReadiness no-guess fallback | claim 7 fixes | E |

TDD discipline: each slice writes its tests first (red), implements minimal code (green), commits — red-green within a slice, every commit green. Fixtures updated in the same slice as the enforcement that requires them (`cuo_xanes_draft.json` gains `block_evidence`; `xanes_completion_answers.json` gains a qc answer). A frozen copy of the current committed sidecar becomes the legacy fixture for test 20.

## 9. Slice-by-slice implementation plan

Ordering rationale — **producers before enforcement**: if validator enforcement landed first, the e2e pipeline (draft_builder → complete → export) would fail its own gate because nothing emits `block_evidence` yet. This deviates from the suggested "all failing tests first" P21B; the negative-test battery lands with its enforcement slice instead (tests-first *within* each slice), keeping every commit green. Alternative honored on request: commit the battery early as `xfail(strict=True)` and flip marks per slice — more churn, same coverage.

- **P21A — Spec commit & fixture decisions** (docs-only, ~15 min). Move this plan into `docs/superpowers/plans/`; record approved decisions (§15) in `docs/mentor-decisions.md` if desired. Commit. *Gate: user approval of this plan.*
- **P21B — Producers: block_evidence emission + sidecar harvest** (Opus 4.8). `draft_builder.py` (contributor + qc evidence → block_evidence; fix the false comment), `complete.py` (series answer coverage; valid-sha256 path), `export.py` (`build_sidecar` passthrough harvest; `transform` qc built directly from draft, native evidence preserved). Purely additive — no existing test breaks. Tests 1–5. Commit + report.
- **P21C — Enforcement: validator + export refusal + sha256** (Opus 4.8). `draft_validator.py` (block coverage, sha256 regex, collisions, unsupported-block refusal), `export.py` (delete qc fabrication), `complete.py` (reject bad sha256 answers, qc blocker question), fixtures (`cuo_xanes_draft.json`, `xanes_completion_answers.json`). Tests 6–16. Full suite green. Commit + report. **This is the thesis-closing slice.**
- **P21D — Audit honest denominator + serialization** (Opus 4.8). `audit.py` rewrite of `_sidecar_coverage` + render; `serialize.py` uncovered/dangling arrays; `adapt.ts` consumption; freeze legacy sidecar fixture. Tests 17–22. Commit + report.
- **P21E — UI truth alignment** (Sonnet 5, narrow). `ExportReadiness.tsx:201` (no more guessed 26 — mirror CoverageBadge's "loading" honesty), `WorkflowSpine.tsx:50-51` skeleton copy de-specified (no fake numbers), `assistant.ts:158,162` canned copy updated to the new honest coverage framing, surface `uncovered` where CoverageBadge lists dangling. No layout/motion/nav changes. Test 23 + vitest suite green. Commit + report.
- **P21F — Docs truth update + sample regeneration** (Sonnet 5). Regenerate `docs/samples/01JQZ0SYNTHXANESDEMO000000.{json,evidence.json}` through the fixed pipeline (pending §15 approval) → walkthrough shows honest full coverage; refresh `sample-record-walkthrough.md` and the "26/26" references (~30 across docs/); fix stale "137 tests" (`final-deliverable-outline.md:95`, `paper-notes.md:104`); fix README quickstart (recommend documenting `.[dev,api]`; alternative: split testpaths — touches pyproject, needs approval). Verify counts by running the commands. Commit + report.

Each slice: implementation subagent gets exact goal / files / files-not-to-touch / acceptance criteria / verification command; Fable reviews diff against invariants, runs `.venv/bin/pytest` (+ vitest for E) before accepting; per-slice report per CLAUDE.md §12/§13. Stop at the gate after each slice unless batch approval is given.

## 10. Risk analysis

- **Entire truth path modified** (highest inherent risk in this repo). Mitigated by: schema untouched, export flow/signature unchanged, producers-before-enforcement ordering, per-slice review by orchestrator, 23-test battery, official validation as final safety net (any stray assistant key leaking into a record fails `additionalProperties:false`).
- **Push = production deploy.** Railway/Vercel auto-deploy from `main`. Mid-phase pushes would ship a half-migrated truth path to the live demo. Mitigation: commit locally per slice, push only at phase end after full verification (or per approved checkpoints).
- **Deployed volume has legacy records.** The 6 experiments on the Railway volume have legacy sidecars → will show honestly lower coverage after P21D deploys. That is the desired truth, but the demo changes appearance. Mitigation: regenerate demo data post-deploy, or accept and narrate ("this is the honesty feature").
- **Export friction increases by design.** Drafts that exported yesterday (unevidenced series/qc/contributors) will refuse until completed. This is the point, but /isaac-complete must ask the new questions well (P21B/C include that path) or users hit a wall.
- **qc refusal has no escape hatch.** The enum has no "unknown"; a user who genuinely doesn't know the QC verdict cannot export. Honest per the schema, but worth flagging to mentors as an upstream vocabulary gap (alongside the missing sha256 pattern).
- **Natural-key edge cases.** Two contributors with identical name+role collide (acceptable in synthetic scope; refusal error is clear). Renaming a series_id orphans its old sidecar key in legacy records — surfaces as dangling, which is correct.
- **Denominator definition drift.** "Scalar leaf walk minus exemptions" must be deterministic and stable; lock it with tests 17/21 and document the exemption list in the audit docstring.
- **~30 doc references to "26/26"** go stale at P21D; P21F sweeps them, but the phase must not stop between D and F for long.

## 11. Files likely touched

- Truth path (CLAUDE.md §13 protection applies — every report must state why/what/tests): `src/isaac_records/draft_validator.py`, `export.py`, `audit.py`, `complete.py`, `extract/draft_builder.py`
- Tests: `tests/test_evidence_coverage.py` (new), `tests/test_audit.py` (new), `test_export.py`, `test_complete.py`, `test_draft_builder.py`, `test_e2e.py`, `apps/api/tests/test_api.py`
- Fixtures: `tests/fixtures/cuo_xanes_draft.json`, `tests/fixtures/synthetic/xanes_completion_answers.json`, new frozen legacy-sidecar fixture
- API/web: `apps/api/isaac_api/serialize.py`, `apps/web/src/lib/adapt.ts`, `apps/web/src/screens/ExportReadiness.tsx`, `apps/web/src/components/WorkflowSpine.tsx`, `apps/web/src/lib/assistant.ts`, web tests
- Docs/demo: `docs/samples/01JQZ0SYNTHXANESDEMO000000.{json,evidence.json}` (regeneration — gated), `docs/sample-record-walkthrough.md`, `README.md`, `docs/final-deliverable-outline.md`, `docs/paper-notes.md`, `docs/cli.md`, `docs/demo.md`, `docs/demo-script.md`, `docs/mentor-brief.md` (26/26 refs), `docs/superpowers/plans/` (this plan)
- Possibly (gated): `pyproject.toml` (only if quickstart fix via testpaths is chosen over docs-only fix)

## 12. Files that must not be touched

- `schema/isaac_record_v1.json`, `schema/PROVENANCE.md` — vendored upstream truth
- `src/isaac_records/official.py` — official validation semantics unchanged
- `src/isaac_records/models.py`, `ids.py`, `review.py`, `portal_warnings.py`, `cli.py` (no CLI surface change expected; audit render lives in audit.py)
- `examples/` — sensitive, gitignored; not read, not staged
- `graphify-out/` — never committed
- Deployment/auth surface: `Dockerfile`, `vercel.json`, `.github/workflows/`, `apps/api/isaac_api/auth.py`, CORS config — Phase 20 territory, out of scope
- `.claude/` skills — no new slash commands; existing skill docs only if a later phase requires it
- Historical snapshot docs (`docs/proposal-v2.md`, `docs/mentor-decisions.md` old entries) — stale "80 tests" refs are dated snapshots; leave unless user opts to annotate

## 13. Acceptance criteria

1. Fabricated-spectrum draft (series, zero evidence): `isaac validate --draft` fails, `isaac export` refuses (was: both PASS).
2. sha256 `"asdf"`: rejected at draft validation and at completion answer time; never reaches a record.
3. Contributor evidence from `parse_contributors` appears in the exported sidecar under `attribution:` keys; the false comment is gone.
4. No code path invents `qc.status`; native `qc.evidence` string survives export byte-for-byte.
5. Sidecar can express series/qc/links/attribution provenance; golden pipeline produces those keys.
6. Audit denominator derives from record content; the empirical "evidence 2/2 with an unevidenced spectrum" scenario renders uncovered targets; legacy sidecars audit without error at honestly lower coverage.
7. `schema/isaac_record_v1.json` diff is empty; all exported records validate `--official`; export remains deterministic and Graphify-free (existing no-Graphify-import test still passes).
8. Full `.venv/bin/pytest` green (148 + new ≈ 23 tests), vitest green, on a correctly-provisioned env.
9. UI: no hardcoded coverage guess remains on a truth path (`ExportReadiness.tsx:201` gone); counts render from `/audit` data; "coverage · not a verdict" framing preserved.
10. Docs: no stale test counts; README quickstart reproducibly collects/passes the full suite on a clean venv; walkthrough matches the regenerated (or honestly-annotated) sample.
11. "I don't know" still works: missing optional values export as omitted; blocking questions remain answerable with honest non-answers that keep the draft pending rather than fabricating.

## 14. Rollback plan

- Every slice is one commit; `git revert <slice>` restores the prior truth path cleanly (no migrations, no persisted-state format breaks: sidecar changes are additive; new audit reads old sidecars, old audit ignores new keys).
- Hold pushes until the phase (or an approved checkpoint) is verified — nothing reaches the deployed demo until then. If a bad state does deploy, follow the documented rollback in `docs/deployment.md` (Railway/Vercel redeploy of prior commit + version-compatibility verification).
- The pre-change committed sample + sidecar are preserved as the frozen legacy fixture, so the old demo artifact remains reproducible from git history even after regeneration.
- If P21C proves too strict in practice (legitimate drafts blocked), revert C alone: B and D are independently safe (B is additive; D only reports honestly).

## 15. Requires explicit user approval before implementation

1. This plan overall, and slice gating mode (approve each slice vs. batch-approve B–D).
2. Truth-path modification authorization (CLAUDE.md §13) for the five core files.
3. The `block_evidence` draft representation + sidecar key grammar (assistant-side convention; flag to mentors that sidecar-as-official-convention remains their call — CLAUDE.md §4).
4. qc policy: **refuse without evidence/confirmation** (recommended) vs. any softer default. Also approval to flag the enum's missing "unknown" and the missing sha256 pattern upstream to mentors.
5. Regenerating the committed demo sample `01JQZ0SYNTHXANESDEMO000000` (changes a committed artifact referenced ~30 times and the deployed demo's appearance) vs. annotating it as an honest 30/34 baseline.
6. README quickstart fix mode: docs-only (`.[dev,api]`) vs. `pyproject.toml` testpaths split.
7. Push cadence given auto-deploys (recommended: local commits per slice, single push at phase end after full verification).
8. Whether stale historical snapshot docs (proposal-v2, old mentor-decisions entries) get a "historical" annotation or stay untouched (recommended: untouched).

## If this were my own project, I would…

Run P21B→C→D as one tight arc in a single sitting — the three slices are one logical change (producers, gate, honest meter) and the repo is worst off in between. I'd take the qc refusal without hesitation (a metadata assistant that invents QC verdicts is worse than one that asks), regenerate the demo sample so the deliverable shows an honest 34/34 rather than explaining a 30/34, and keep sha256 in this phase — it's a regex in a file already open, and "asdf becomes immutable state" is embarrassing in a demo Q&A. I'd fix the README quickstart via docs (`.[dev,api]`), not pyproject surgery. I'd leave tags exempt and implicit informational — chasing "evidence for a label the user typed" is theater, not rigor. And I'd write the mentor note about the schema's missing sha256 pattern and missing honest qc-"unknown" now, while the evidence is fresh — that's the kind of upstream feedback that makes this project look like it understands the standard better than the standard does.

## Approval decisions (recorded 2026-07-15)

1. **Plan approved.** Phase 21 is truth-gap closure before UX polish or feature work.
2. **Gating:** P21B–P21D batch-approved as one truth-path arc; report after each slice before continuing. P21E/P21F proceed in order.
3. **Truth-path authorization:** only `draft_validator.py`, `export.py`, `audit.py`, `complete.py`, `extract/draft_builder.py`. `schema/isaac_record_v1.json` and `schema/PROVENANCE.md` must not be touched.
4. **block_evidence model approved:** draft map + additive sidecar grammar `series:<series_id>`, `qc`, `links:<rel>|<target>|<basis>`, `attribution:<name>|<role>`. Assistant-side convention, not an official ISAAC standard.
5. **QC policy approved:** never fabricate `qc.status="valid"`; series without evidenced qc refuses export and surfaces a completion question; schema-native `measurement.qc.evidence` preserved; missing honest "unknown" state flagged as an upstream/schema discussion item, not invented locally.
6. **sha256 policy approved:** reject malformed values at draft validation and completion-answer time; strict `^[0-9a-f]{64}$` unless source inspection justifies uppercase — if uppercase is accepted, normalize or document the rule explicitly.
7. **Demo sample:** regenerate the committed synthetic sample after the truth-path fix so the demo lands on an honest full-coverage result.
8. **README quickstart:** docs-only fix (`pip install -e '.[dev,api]'`); no pyproject testpaths change without clear reason.
9. **Push cadence:** local commits per slice; no push until the entire Phase 21 verification suite passes (main auto-deploys to Vercel + Railway).
10. **Historical docs:** left alone unless linked as current guidance or actively misleading; current docs, README, walkthrough, sample docs, and paper/deliverable numbers get updated.

**UI/copy requirement:** when the denominator changes, the UI must explain it — e.g. "Evidence Audit — 34 / 34 targets covered. Includes fields, assets, descriptors, series, QC, links, and attribution." Keep the three-signal separation: audit = coverage (not a verdict), validation = hard PASS/FAIL gate, advisory warnings = non-gating; never merge them.

**Model rule:** Fable 5 orchestrates/plans/reviews/verifies only; Opus 4.8 implements truth-path/QC/sha256/audit/high-risk test design and final review; Sonnet 5 implements narrow frontend truth alignment, docs updates, grep audits, copy fixes.
