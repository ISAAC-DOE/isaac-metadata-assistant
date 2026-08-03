# Evidence Sidecar — Code Audit

**Purpose.** Establish, from code, exactly what the evidence sidecar is, who writes it, who reads it,
what depends on it, and what breaks under each possible ruling. This document **audits and reports
only**. It proposes no redesign and asserts no authority the code does not already have.

**Scope of verification.** Every claim below carries a `file:line` or a command, resolved against
branch `feat/pre-dean-readiness` (base commit `f57e239`, `git log --oneline -5`). **All test figures in
this document are branch figures, re-run 2026-07-28:** backend `1375 passed, 0 failed`
(`.venv/bin/pytest -q`); frontend `1865 passed / 89 files` (`npm test` in `apps/web`). For comparison
only, the base commit `f57e239` was backend `1328` / frontend `1750 in 85 files` — do not use those
numbers to check out this branch.

---

## 1. Verdict up front

| Question | Answer |
|---|---|
| Is the sidecar described as official anywhere in code, UI, or docs? | **No.** Every user-facing string calls it an assistant convention. |
| Does official schema validation depend on it? | **No.** |
| Does the export gate depend on it? | **No.** It is built *after* both gates pass. |
| Does the audit verdict depend on it? | **No.** Coverage is reported; the exit code ignores it. |
| Does the Assistant read it? | **No.** |
| Does the code exceed the documented authority? | **No on authority. Yes on coupling** — see §8. |

**Stop-and-report check: negative.** The sidecar is not more *authoritative* in code than the
documentation admits. Validation, export gating, and the audit verdict are all independent of it, and
the UI labels it "assistant convention — not official" in every place it is shown.

There is, however, one thing the documentation does not say and Dean should know: for an
**already-exported** record the sidecar is the **sole** source of the Evidence Trail, and two read
endpoints open it **unguarded**. That is a hard *runtime coupling*, not an authority claim — but it is
what makes ruling (c) more expensive than the docs imply. Details in §8 and §9.

---

## 2. File structure and naming

One sidecar per exported record, a sibling of the record, named by the same ULID:

```
records/<ULID>.json           # official ISAAC v1.05 record
records/<ULID>.evidence.json  # evidence sidecar
```

Path construction — **all four writers** plus the accessor:

| Location | Code |
|---|---|
| `src/isaac_records/cli.py:76-77` | `record_path = records_dir / f"{rid}.json"` · `sidecar_path = records_dir / f"{rid}.evidence.json"` |
| `apps/api/isaac_api/routes.py:1136-1137` | same pair, inside `routes.py::_write_record` (written at 1138-1139) |
| `apps/api/isaac_api/workspace.py:296-298` | `Experiment.sidecar_path()` → `records_dir / f"{rid}.evidence.json"` |
| `apps/api/isaac_api/workspace.py:618-620` | canonical-seed writer, inside `workspace.py::_write_seed_record` (607-621) |
| `scripts/run_synthetic_demo.py:117-119` | reproducible-demo writer |

**Top-level shape** — `src/isaac_records/export.py:130-135`:

```json
{ "record_id": "<ULID>", "schema_version": "1.05", "generated_utc": "<ISO8601Z>", "evidence": { … } }
```

Confirmed against the committed synthetic sample
`docs/samples/01JQZ0SYNTHXANESDEMO000000.evidence.json`: keys exactly
`record_id`, `schema_version` (`1.05`), `generated_utc` (`2026-07-15T23:20:42Z`), `evidence`
(36 entries).

**`evidence` key namespaces** — `src/isaac_records/export.py:107-129`, mirrored for auditing at
`src/isaac_records/audit.py:66-85`:

| Key form | Source | Payload |
|---|---|---|
| `system.facility.beamline` (dotted) | draft scalar field envelopes | evidence list |
| `assets:<asset_id \| uri>` | draft assets | evidence list |
| `descriptors:<name>` | draft descriptor outputs | evidence list |
| `implicit:<about>` | draft `implicit[]` | **object** `{value, evidence}` — sidecar-only, never a record field (`src/isaac_records/models.py:21`) |
| `series:<series_id>` | draft `block_evidence` | evidence list |
| `qc:status` | draft `block_evidence` | evidence list |
| `links:<rel>\|<target>\|<basis>` | draft `block_evidence` | evidence list |
| `attribution:<name>\|<role>` | draft `block_evidence` | evidence list |

An individual evidence entry, as it appears in the committed sample:

```json
{ "source_type": "spreadsheet", "source_file": "mock_campaign.csv",
  "locator": "Sheet 'Campaign Info', field=facility_name", "quote": "SSRL" }
```

**There is no schema for the sidecar.** `ls schema/` returns exactly
`isaac_draft.schema.json`, `isaac_record_v1.json`, `PROVENANCE.md`. The draft schema types the
envelope's `evidence` only as `{"type": "array"}` (`schema/isaac_draft.schema.json:39, 57, 70, 77`; the envelope's `required` list is at 65) —
the entry fields above are conventions of the extractor, not a validated contract. The sidecar's
shape is defined **solely by `build_sidecar` in code** and pinned only by tests (§7).

---

## 3. Creation path

`src/isaac_records/export.py::export_draft` (lines 147-166) is the only producer of sidecar content.
Order matters and is the core finding of this section:

```
154  draft_report = validate_draft(draft)          # no-guessing gate
157-158  if not draft_report.ok: return (no record, no sidecar)
160  record = transform(draft, …)                  # official shape, evidence stripped
161  official_report = validate_official(record, root)   # official schema gate
162-163  if not official_report.ok: return (record, NO sidecar)
165  sidecar = build_sidecar(draft, record)        # only now
```

The sidecar is therefore **downstream of both gates and an input to neither**. A record that fails
either gate produces no sidecar at all, and nothing is written
(`src/isaac_records/cli.py:64-71`; API path returns `ok: false` with nothing written,
`apps/api/isaac_api/routes.py:1220-1234`).

`build_sidecar` reads the **draft**, not the record, except to copy `record["record_id"]`
(`export.py:131`). It emits a dotted-path entry only when the draft envelope carries evidence *and* a
non-null `value` (`export.py:110-112`) — note that this is a test of the **draft envelope**, not of the
produced record: `build_sidecar` never inspects `record` beyond the id. That every dotted sidecar key
resolves into the record is an invariant of `transform`, **asserted by tests rather than enforced by
the builder** (`tests/test_export.py:93-100`, `tests/test_e2e.py:50-58`); a `transform` change that
dropped a field would therefore produce a dangling key, which `isaac audit` would report (§6).

Evidence never enters the official record: `strip_evidence` deep-copies structured blocks with every
`evidence` key removed (`export.py:48-55`), because the official schema is
`additionalProperties: false` throughout (37 occurrences in `schema/isaac_record_v1.json`; root at
line 5). The **one** exception is deliberate and documented in code: `measurement.qc.evidence` is a
*native schema string field* (`schema/isaac_record_v1.json:1093-1096`), so `qc` is copied verbatim
rather than stripped (`export.py:86-89`). That field is part of the official record, not part of the
sidecar mechanism.

---

## 4. Read path

| Consumer | Location | What it does with the sidecar |
|---|---|---|
| `GET /api/experiments/{id}/evidence` | `routes.py::get_evidence`, `apps/api/isaac_api/routes.py:1712-1717` | **For an exported record, the trail is built from the sidecar and nothing else** (`serialize.evidence_trail_from_sidecar`, `apps/api/isaac_api/serialize.py:263-296`). Pre-export it uses the draft envelopes instead. |
| `GET /api/experiments/{id}/artifacts` | `routes.py::get_artifacts`, `apps/api/isaac_api/routes.py:1870-1897` | Returns the parsed sidecar JSON verbatim, plus basenames only (never a server path). |
| `isaac audit` / `POST /experiments/{id}/audit` | `src/isaac_records/audit.py:88-146`; `routes.py:1622-1623` | Reads it to compute coverage/dangling **reporting only** (§6). |
| Export Readiness screen | `apps/web/src/screens/ExportReadiness.tsx:456-462` (second card), `465-478` (the not-official note), `638-655` (the JSON viewer) | Second artifact card + JSON viewer, labelled not-official. |
| Evidence screen | `apps/web/src/screens/EvidenceExplorer.tsx:114-126, 213` | Derives its post-export branch, shows `schema_version`/`generated_utc`, renders the JSON. |
| Source Preview | `apps/web/src/components/SourcePreview.tsx:56, 98-108, 143-157` | "Sidecar JSON" tab and per-field "Sidecar Entry" block. |

**Not consumers** (verified by grep over `apps/api/isaac_api/`): `assistant_query.py`,
`assistant_paths.py`, `memory.py`, `memory_graph.py`, `evidence_classify.py` contain no reference to
the sidecar.

---

## 5. Does official validation depend on it? No

`validate_official(record, root)` takes a record dict and a repo root, loads
`schema/isaac_record_v1.json`, and returns jsonschema errors
(`src/isaac_records/official.py:67-79`, `26-39`). The module contains no mention of the sidecar, of
evidence maps, or of any companion file. The standalone Validator
(`POST /api/validate/record`, surfaced at `/governance?tab=validator`) calls that same
`validate_official` (`apps/web/src/components/RecordValidator.tsx:9-19`), so a pasted record is judged
with no sidecar in existence.

`docs/cli.md:202-205` states the corollary correctly: validating a `.evidence.json` file *as* an
official record fails, because it is not one.

---

## 6. Does the audit verdict depend on it? No

`audit_records` iterates `*.json`, **skips** `*.evidence.json`
(`src/isaac_records/audit.py:133-135`), validates each record, and attaches a coverage tuple
(`audit.py:142-145`).

- Coverage's **denominator is enumerated from the record**, not from the sidecar's keys
  (`audit.py:43-85`, and the module docstring at `audit.py:1-13`). Evidence claiming objects the
  record does not have surfaces as `dangling` (`audit.py:116-127`).
- A **missing** sidecar yields an honest `(0, expected, …)` — 0/N, never 0/0, never a crash
  (`audit.py:106-107`; test `tests/test_audit.py:154-160`).
- **Exit code**: `src/isaac_records/cli.py:96` — `return 0 if all(r.ok for _, r, _ in results) else 1`,
  where `r` is the `OfficialReport`. The coverage tuple is the third element and is never consulted.
  `docs/cli.md:173` states this correctly: "`0` all records pass · `1` at least one record fails
  official validation."

So a record with a dangling sidecar key, or with no sidecar file at all, still **passes** `isaac audit`
provided the record itself validates. Coverage is completeness reporting, as `audit.py:12-13` and
`docs/cli.md:171` both say.

**Documentation discrepancy — found in two docs, four places, and now CORRECTED in all four.** Both
docs had rendered the audit as if 0-dangling were enforced. The corrected text now says the audit
*reports* sidecar coverage and dangling paths and does not gate on them:

| Where | Was | Now |
|---|---|---|
| `docs/architecture.md:58-64` (the ASCII box) | `+ every sidecar path / resolves (0 dangling)` | `+ sidecar coverage and / dangling paths REPORTED`, with `(this alone sets PASS/FAIL)` on the re-validate line |
| `docs/architecture.md:90` (module map, `audit.py` row) | "Re-validate every record in a dir + confirm sidecar dotted paths resolve" | "Re-validate every record in a dir (that result alone sets PASS/FAIL) + **report** sidecar coverage and dangling paths" |
| `docs/mentor-decisions.md:48-51` | "every stored record re-validates and every sidecar path resolves (0 dangling)" | official validation "alone sets the PASS/FAIL verdict and the exit status"; coverage and dangling paths are "*reported* alongside it, not enforced" |
| `docs/mentor-decisions.md:109-112` (D1 tradeoffs) | "risk of drift … mitigated today by the audit that checks every sidecar path resolves" | the audit *reports* dangling sidecar paths and does not gate on them, so the drift risk is **surfaced, not prevented** |

The old wording was true as an *observation about the committed sample* (pinned for the demo draft by
`tests/test_e2e.py:50-58` and `tests/test_export.py:93-100`) but neither statement described an audit
**gate**. Read as enforcement they overstated `cli.py:96`, which consults only the `OfficialReport`.

---

## 7. Which tests protect it

**Truth-core tests (`tests/`)**

| Test | What it pins |
|---|---|
| `tests/test_export.py:93-100` `test_sidecar_dotted_paths_resolve_in_record` | every dotted sidecar key resolves in the produced record |
| `tests/test_export.py:111-132` `test_sidecar_harvests_series_qc_links_attribution` | `block_evidence` keys and values pass through verbatim |
| `tests/test_cli.py:16-24` `test_export_writes_record_and_sidecar` | both files written; stems match |
| `tests/test_audit.py:22-23, 56-128` | coverage/uncovered/dangling semantics for constructed sidecars |
| `tests/test_audit.py:131-149` | a legacy (pre-Phase-21) sidecar audits honestly without crashing |
| `tests/test_audit.py:154-160` | missing sidecar → 0-of-expected, not 0-of-0 |
| `tests/test_audit.py:187-188` | empty evidence map handled |
| `tests/test_e2e.py:50-58, 71-72` | end-to-end draft → record + sidecar; every path resolves |

**API tests (`apps/api/tests/`)**

| Test | What it pins |
|---|---|
| `test_api.py:212-231` | export writes both files; distinct basenames; no `/` in either; `sidecar["record_id"] == exp_id` |
| `test_api.py:446-448, 452-463` | `/artifacts` nulls before export; record ≠ sidecar after |
| `test_artifact_path_safety.py:68` | artifacts response is populated without exposing a server path |
| `test_seed.py:123-132` | the canonical `done` scenario has a record id **and** an existing sidecar file |
| `test_reset_content.py:146` | reset restores the exported scenario's sidecar |
| `test_committed_snapshot.py` | (indirect) the served-content manifest covering these files |

**Frontend tests (`apps/web/src/__tests__/`)**

| Test | What it pins |
|---|---|
| `evidence.test.tsx:42-44` | the exact string `sidecar · assistant convention, not an official ISAAC standard` is rendered |
| `evidence.test.tsx:115-120` | the sidecar JSON view is distinct from the record JSON view |
| `completion-export.test.tsx:254-262` | two separate artifact cards; `Review the sidecar before sharing` present |
| `completion-export.test.tsx:295-297, 332-340, 359-362` | filenames shown; read-only load note; no invented path-count badge |
| `modal-a11y.test.tsx:116-129` | the sidecar viewer is a properly labelled dialog with focus return |
| `display-labels.test.ts:41, 73-74, 113, 129` | display labels for "Evidence sidecar (`records/<ULID>.evidence.json>`)" |

---

## 8. Official vs advisory — the actual strings

Every user-facing claim about the sidecar, located and quoted verbatim.

**In-app UI**

| Where | String |
|---|---|
| `apps/web/src/lib/labels.ts:217` | `sidecar · assistant convention, not an official ISAAC standard` |
| `apps/web/src/lib/labels.ts:218` | `assistant convention — not official` |
| `apps/web/src/components/ArtifactCard.tsx:38` | record card reads `schema-clean · ISAAC v1.05`; sidecar card reads `LABELS.sidecarNotOfficial` |
| `apps/web/src/screens/ExportReadiness.tsx:473-476` | "**Review the sidecar before sharing.** It is an assistant convention — not an official ISAAC standard — and can carry source paths, URIs and hashes. Records are written once, immutable via the CLI: no hand-edit, no overwrite, no portal submission from here." |
| `apps/web/src/screens/ExportReadiness.tsx:531-533` | "Exporting runs the real, gated validation and writes the local record + evidence sidecar. There is no override and no portal submission." |
| `apps/web/src/screens/EvidenceExplorer.tsx:213` | `sidecar · assistant convention, not an official ISAAC standard · <n> direct paths counted in coverage` |
| `apps/web/src/components/EvidenceTrailPanel.tsx:15, 41` | rendered as "always labeled an [assistant convention]" via `LABELS.sidecarConvention` |
| `apps/web/src/components/SourcePreview.tsx:150-151` | per-field Sidecar Entry carries the same convention note |
| `apps/web/src/components/HelpPanel.tsx:143-145` | "Exports write an evidence sidecar (`<record>.evidence.json`) beside the official record." — **neutral wording; makes no officiality claim either way** |

**API contract text**

| Where | String |
|---|---|
| `apps/api/isaac_api/routes.py` (`GET …/evidence`) | "For an already-exported record the trail is read from the evidence sidecar written alongside the official record; otherwise — including when that sidecar or record cannot be read — it is read from the draft's own evidence envelopes, which are the sidecar's own source." — *extended 2026-08-03: the export-recovery slice made this reader tolerate an unreadable artifact, and the contract text had to say so. The line number is dropped because it drifts; the operation is the stable reference.* |
| `apps/api/isaac_api/routes.py:1857-1859` | "The official ISAAC record and the evidence-sidecar JSON that this …" |

**Documentation**

| Where | String |
|---|---|
| `docs/cli.md:192` | "Evidence **sidecar**: maps official JSON-paths to their source evidence. An assistant audit artifact, **not** part of the official ISAAC record format" |
| `docs/architecture.md:109-110` | "The sidecar is an assistant audit artifact unless mentors adopt it as an official ISAAC convention." |
| `docs/data-governance.md:106-112` | "Evidence sidecar caution … **If real data is ever used, the sidecar can contain identifying provenance** (real file paths, archive URIs, hashes)." |
| `README.md:247` | lists "Whether the evidence sidecar becomes an official ISAAC convention (vs. an assistant-only audit artifact)" as an **open** question |
| `CLAUDE.md` §4 | "The sidecar is an assistant audit artifact unless mentors approve it as an official ISAAC convention." |
| `docs/mentor-decisions.md:87` (register row) and `96-117` (the D1 section; the quote is at 104-105) | decision **D1**, recommended default: "Keep the sidecar as the assistant's audit artifact **and** propose it to ISAAC as an *optional companion file* (record stays 100% standard; sidecar travels alongside)." |

`schema/PROVENANCE.md` does not mention the sidecar at all — the vendored official schema neither
knows nor sanctions it.

**No string anywhere calls the sidecar official.** The claim is consistent across code, UI, API text,
and docs.

### The coupling the docs do not mention

Two API reads open the sidecar **without checking that it exists**, relying on the invariant "exported
⇒ sidecar present":

- `apps/api/isaac_api/routes.py:1714` — `json.loads(exp.sidecar_path().read_text(encoding="utf-8"))`, inside `routes.py::get_evidence`
- `apps/api/isaac_api/routes.py:1890` — the same call inside `routes.py::get_artifacts`

Both are guarded only by `exp.exported()`, which is `record_id is not None`
(`apps/api/isaac_api/workspace.py:394-395`) — it does not test the file. A record whose sidecar is
absent or unparseable would raise on those two routes rather than degrade. Contrast the audit path,
which handles absence honestly (`src/isaac_records/audit.py:106-107`).

Related, and worth Dean knowing because it affects any migration: the frontend's Evidence screen takes
`exported = artifacts.sidecar !== null` (`apps/web/src/screens/EvidenceExplorer.tsx:114`). That is
*consistent* today — `/artifacts` returns nulls for both fields unless `exp.exported()`
(`routes.py:1880-1886`) — so the sidecar is a proxy for export state, not an authority over it. But a
future sidecar-less export path would flip that screen into its pre-export presentation.

One more asymmetry, verified: for an exported record the **Evidence page** reads the sidecar
(`routes.py:1714`) while the **Assistant** grounds field-provenance answers on
`serialize.evidence_trail_from_draft(exp.draft)` (`routes.py:2744`; `assistant_query.py:314`). Two
different reads of the same provenance. They should agree because the sidecar is derived from the
draft, but nothing cross-checks them.

---

## 9. Migration risk under each ruling

Common baseline: the sidecar is produced by one function
(`src/isaac_records/export.py:107-135`), written by four call sites, read by three backend surfaces
and three frontend surfaces (§3, §4). It has **no schema**, so "the format" today means "whatever
`build_sidecar` emits", pinned by the tests in §7.

### (a) Approved as an official ISAAC artifact

**Lowest-cost ruling. No runtime behaviour has to change.**

| Work | Size |
|---|---|
| Add an upstream-owned JSON Schema for the sidecar and vendor it beside `isaac_record_v1.json`, with `schema/PROVENANCE.md` updated | Moderate — this is the real work; the format is currently code-defined only |
| Retire the "assistant convention — not official" labelling in 4 UI locations | Small — `labels.ts:217-218` are single-sourced; `ExportReadiness.tsx:473-476` and `EvidenceExplorer.tsx:213` are prose |
| Update the frontend tests that assert the convention string | Small — `evidence.test.tsx:42-44`, `completion-export.test.tsx:260`, `display-labels.test.ts` |
| Update docs: `docs/cli.md:192, 202-205`, `docs/architecture.md:104-110`, `README.md:247`, `CLAUDE.md` §4, `docs/mentor-decisions.md` D1 | Small |

**Risk:** the format becomes a contract we must not casually change, and the ULID-keyed
`assets:`/`descriptors:`/`implicit:`/`series:`/`qc:`/`links:`/`attribution:` namespaces become
external API — including the `|`-joined composite keys (`export.py:115-129`; note `audit.py:69`
records that `|` is not escaped). Those keys were designed for our own audit, not for interchange.
**Open question for Dean:** would upstream accept keys built by string-joining unescaped natural keys,
or would officialisation require re-keying — which turns ruling (a) into part of ruling (c)?

### (b) Interim assistant convention (status quo)

**Zero code change. Zero doc change.** This is exactly what the code, UI, API text, and docs already
say (§8), and what `docs/mentor-decisions.md:87` already recommends. The only action is to record the
ruling and close the open item at `README.md:247`.

**Risk:** the open question stays open, and every real-data conversation reopens it. Also the
data-governance caution at `docs/data-governance.md:106-112` remains load-bearing: with real data the
sidecar is the artifact most likely to carry identifying provenance (paths, archive URIs, hashes),
while carrying no official status that would force it through a review process.

### (c) Must be replaced

**Highest cost, and higher than the documentation implies.** Ordered by blast radius:

| Area | What breaks | Notes |
|---|---|---|
| Producer | `build_sidecar` + its call in `export_draft` (`export.py:107-135, 165`) | Contained; the gates above it are untouched, so **the truth path itself does not change** |
| Writers | `cli.py:82`, `routes.py:1139`, `workspace.py:618-620`, `scripts/run_synthetic_demo.py:119` | Four sites, mechanical |
| Audit | `audit.py:88-128` `_sidecar_coverage` and the block-key construction at `audit.py:66-85` must be re-derived for the new format | The coverage *model* (denominator from the record) survives a format change; the *keys* do not |
| **Evidence Trail, exported records** | `routes.py:1712-1717` + `serialize.py:263-296` | **The only post-export provenance source.** Until the replacement lands, exported records have no evidence trail at all |
| `/artifacts` | `routes.py:1870-1897`, unguarded read at 1890 | Would raise, not degrade, on a missing sidecar (§8) |
| Frontend | `ExportReadiness.tsx` (artifact card, viewer, download), `EvidenceExplorer.tsx:114-126`, `SourcePreview.tsx:56, 98-108, 143-157` | The `exported` inference at `EvidenceExplorer.tsx:114` needs rewiring to `detail.exported` |
| Committed sample | `docs/samples/01JQZ0SYNTHXANESDEMO000000.evidence.json` and the byte-for-byte reproducibility claim in `scripts/run_synthetic_demo.py:23-24, 127` | The record is byte-identical; the sidecar deliberately is not (wall-clock `generated_utc`) |
| Tests | ~20 tests across §7, in 9 backend files (4 under `tests/`, 5 under `apps/api/tests/`) and 4 frontend files | The audit-semantics tests (`tests/test_audit.py`) are the largest cluster |
| Docs | `docs/cli.md`, `docs/architecture.md`, `docs/data-governance.md`, `docs/sample-record-walkthrough.md`, `README.md`, `CLAUDE.md` §4, `docs/mentor-decisions.md` D1 | `docs/sample-record-walkthrough.md` is a field-by-field tour of this exact sidecar |

**What does *not* break under (c):** official schema validation, the export gate, the no-guessing
draft validator, the audit verdict, the Assistant. All are independent of the sidecar (§5, §6, §4).
The deterministic truth core keeps working with a sidecar of any shape, or none.

**Open questions we cannot answer from this repository:**

1. If the replacement is a portal-side provenance store rather than a file, does export still produce
   a local artifact at all — and if not, what does the Evidence page show for a record exported before
   the portal existed?
2. Is `implicit:` provenance (absorbing element, edge — values with **no** valid official path,
   `CLAUDE.md` §5) expected to survive into any replacement, or to be dropped? It exists today only
   because the sidecar can hold what the record cannot (`src/isaac_records/models.py:21`).

---

## 10. One-paragraph summary for Dean

The sidecar is a companion JSON file written next to each exported record, mapping official JSON paths
(plus namespaced asset/descriptor/series/QC/link/attribution/implicit keys) to the source evidence
behind each value. It exists because the official v1.05 schema is `additionalProperties: false` and
has no per-field provenance slot. It is produced only after a draft passes both the no-guessing checks
and the official schema, and it feeds nothing that decides validity: validation, export gating, and
the audit verdict are all independent of it. The app labels it "assistant convention — not official"
everywhere it is shown. It has no schema of its own — its shape is defined by one function and pinned
by roughly twenty tests. Keeping it as-is costs nothing. Officialising it mainly costs an upstream
schema and a decision about whether its composite key format is acceptable for interchange. Replacing
it is the expensive ruling, chiefly because it is the only source of the evidence trail for records
that have already been exported.
