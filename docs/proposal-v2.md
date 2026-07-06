# ISAAC Metadata Assistant — Proposal (v3, official-schema aligned)

**Status:** revised 2026-07-06. Supersedes v2 (2026-07-04) and the original docx (v1).
**Owner:** Krish Verma (intern) · **Context:** ISAAC / SSRL / SLAC — AI-ready metadata.

---

## 1. One-paragraph pitch

An assistant that turns beamline metadata chaos (Excel, web-form screenshots, PDFs, notes) into
**official ISAAC records** — validated against the real ISAAC v1.05 schema — without guessing.
The LLM only extracts and asks; a deterministic core transforms a working draft into the native
record shape, validates it against the vendored official schema, and emits an evidence sidecar so
every asserted value keeps a traceable source. An optional knowledge graph (Graphify) adds
cross-experiment memory but is never the source of truth.

## 2. The pivotal fact: the official schema exists

The official ISAAC standard is public and mature:
[`github.com/ISAAC-DOE/isaac-ai-ready-record`](https://github.com/ISAAC-DOE/isaac-ai-ready-record)
(DOE BES AI Pathfinder). It ships `schema/isaac_record_v1.json` (**v1.05**, June 2026), an
18-page wiki, an official validator (`portal/validation.py`), and 10 golden example records. This
project **adopts** that schema as the authority and vendors it (`schema/isaac_record_v1.json`,
pinned; provenance in `schema/PROVENANCE.md`). We do not author or maintain a record schema.

### What the official schema is like (and why it reshaped the design)

- **Strict and closed.** `additionalProperties: false` throughout; direct values with units baked
  into key names (`temperature_K`, `potential_setpoint_V`); vocabulary enforced by inline `enum`s;
  `record_id` is a ULID.
- **Typed and conditional.** `record_type` (evidence/intent/synthesis) × `record_domain`
  (characterization/performance/simulation/theory/derived) gate required blocks via `allOf`
  if/then rules (evidence ⇒ descriptors; performance+galvanostatic ⇒ `current_setpoint_mA_cm2`).
- **Already embodies "no guessing" natively.** Descriptor `value` may not be null; potentials
  carry an explicit `rhe_basis` trust tier with null-with-reason; uncertainty has a `basis`
  ("do not encode 'not reported' as sigma 0"); `qc.status` ∈ valid/compromised/failed/pending.
- **10 blocks:** sample, system, context, measurement, descriptors, assets, links, computation,
  attribution, timestamps.

## 3. Architecture: draft → transform → official record + sidecar

```
examples/ ──/isaac-draft──▶ drafts/<name>.draft.json     envelope {value,status,evidence[]}
                                   │  no-guessing enforced at authoring
                             /isaac-export  (deterministic, LLM-free, doubly gated)
                                   ├─▶ records/<ULID>.json           valid vs official v1.05
                                   └─▶ records/<ULID>.evidence.json  JSON-path → evidence
```

- **Draft layer (ours).** Every scalar is an envelope `{value, unit?, status, evidence[]}` whose
  keys are **dotted paths into the official schema**. This is the only place the envelope exists.
- **Transform (`src/isaac_records/export.py`).** Drops the envelope, writes native values at their
  official paths, generates a ULID, copies the structured blocks (series/assets/descriptors/…),
  and strips evidence keys the schema would reject. Refuses unless the draft passes no-guessing
  checks **and** the produced record passes the official schema.
- **Evidence sidecar.** The official record has no per-field provenance slot and forbids extra
  keys, so evidence moves to `records/<ULID>.evidence.json`, keyed by official JSON-path (plus
  `assets:`/`descriptors:`/`implicit:` namespaces). This is the design choice that keeps
  auditability — the project's whole point — without violating the standard. *(It is not part of
  the ISAAC standard; to be confirmed with mentors before records leave the repo.)*

## 4. Conceptual roles → implementation

The original 8-agent framing remains a good mental model; it is implemented as one workflow + a
deterministic library.

| Conceptual role | Implementation |
|---|---|
| Orchestrator | the 5-command workflow |
| Extraction | `/isaac-draft` (LLM) — into official JSON-paths, evidence at capture time |
| Question | `/isaac-complete` (LLM) — questions come from the validators, not model judgment |
| Record builder | `export.transform` (deterministic) |
| Validator | `official.validate_official` = jsonschema vs vendored v1.05 (all hard/400 rules) |
| Evidence | the draft envelope + the exported **sidecar** |
| Audit | `audit` — loop `validate_official` over `records/` + sidecar coverage |
| Graph / Query | `/isaac-query` routing; Graphify optional/derived |

The LLM touches only extraction and question-asking; everything downstream is deterministic.

## 5. How "no guessing" holds, in two stages

1. **Authoring (draft):** `draft_validator` rejects a finalized field with no evidence, a
   `missing` field that still has a value, an `inferred` field with no derivation rule, an asset
   with no `sha256`, a descriptor with a null value.
2. **Export (record):** the official schema rejects unknown blocks, out-of-enum vocabulary,
   anti-pattern descriptor names, and conditionally-required fields absent for the record's
   type/domain. Export writes nothing unless both pass. There is no `--force`.

40 tests lock this in: all 10 official golden records validate; representative violations fail;
the transform is gated; the sidecar's paths resolve; the core never imports Graphify.

## 6. Graphify: central for memory and query, not for truth

The system separates two planes on purpose:

- **Truth plane (deterministic, Graphify-free).** Schema, validators, and export decide whether a
  record exists and is valid. This path never imports Graphify (enforced by
  `test_core_never_imports_graphify`). The official schema and official validator are the only
  authorities on validity.
- **Memory/query plane (Graphify-central).** Graphify is a **major** component here, not an
  optional add-on: project memory, relationship search, similar-record lookup, prior-experiment and
  document queries, contextual help while drafting, documentation search, and "what changed?"
  history. This is where the assistant becomes a living project memory, not just a record maker.

`/isaac-query` routes each question to its owner: schema/vocab → `schema/isaac_record_v1.json` +
`vocabulary/`; "how is X encoded" → golden examples; completeness → `isaac audit`; history →
`git log`; **similarity/relationships/memory → `graphify query`**. If a graph answer conflicts with
the schema, a validated record, or the audit, the deterministic source wins. The truth pipeline is
fully functional with Graphify absent; the memory/query experience leans on it heavily.
Data-governance note: Graphify runs key-less so no content is routed to an external API.

## 6a. Validation stack and the future AI review layer

Records pass through staged checks with fixed authorities; the AI never overrides code.

1. **Draft no-guessing validation** (`draft_validator.py`) — gates authoring.
2. **Official ISAAC schema validation** (`official.py`, vendored v1.05) — gates export.
3. **Official `portal/validation.py` soft-warning tier** (upstream; integration deferred) — warnings.
4. **AI scientific consistency review** (`review.py`) — **advisory only**; a placeholder interface today.
5. **Human review** of flagged issues — the decider.

**Stage 4 (advisory review).** A future Scientific / Consistency Review Agent would check
scientific plausibility, record↔context consistency, descriptor↔technique mismatch, missing but
important context, possible overclaiming beyond evidence, comparison to similar records (via
Graphify, as advisory context), and suggest human-review questions. It **must not** replace the
schema validator or `portal/validation.py`, silently modify records, override validation, or mark a
record officially valid/invalid. Today it is a no-op interface (`src/isaac_records/review.py`,
`NoOpReviewer`) that returns no findings, touches no record, and is not wired into export or
validation — a stable seam for later work, with zero effect on current behavior.

## 7. MVP scope and demo

**Scope:** one path end-to-end — **characterization / XANES (record_type=evidence)** — mirroring
the official `ex_situ_xanes_cuo2_record.json`. `tests/fixtures/cuo_xanes_draft.json` is a full CuO
K-edge XANES draft that exports to a schema-valid record.

**Demo:** upload the campaign spreadsheet + web-form screenshots → `/isaac-draft` maps values to
official paths, flags gaps → `/isaac-complete` asks only blockers (raw-data URI **+ sha256**, the
inflection-point descriptor + uncertainty, endstation/spectrometer, qc status) → `/isaac-export`
writes `records/<ULID>.json` + sidecar, valid against v1.05. Note the honest change from v2:
absorbing element and edge are **not** asked as fields — they have no schema field; they are
recorded as `implicit` inferences (from formula + technique) in the sidecar only.

## 8. Roadmap

| Week | Milestone |
|---|---|
| — (done) | Vendor schema + 10 examples; deterministic core (validate/export/audit/new-id); XANES draft→record; 40 tests; skills + docs migrated |
| Next | Run `/isaac-draft` on the **real** artifacts (needs `examples/` populated); tune extraction → path mapping |
| + | Second domain (performance / electrochemistry) to exercise conditional requireds |
| + | Optionally reuse official `portal/validation.py` for the soft-warning tier |
| + | Graphify build over `records/`; `/isaac-query` against real questions |

## 9. Migration from v2 (honest record of discarded work)

v2 authored a **provisional** schema (before the official one was located) and made the
`{value,status,evidence[]}` envelope the record format. The official schema contradicts both.
Removed: the provisional record schema, pint unit-dimension checks (units are in key names),
the vocabulary files (superseded by schema enums), and the tests built around them. Kept and
repositioned: the deterministic-core architecture, git-as-source-of-truth, Graphify-as-optional,
and the evidence envelope — now a **draft** format that exports into the official shape.

## 10. Risks / open questions for mentors

- **Sidecar acceptance.** Is an out-of-standard `records/<ULID>.evidence.json` acceptable, or
  should evidence map only into native slots (`qc.assumptions`, `uncertainty.basis`,
  `descriptors…generated_by`)? Current choice: sidecar, for full auditability.
- **Vendored-schema drift.** We pin v1.05; need a refresh cadence vs upstream.
- **Portal parity.** We cover all hard/400 rules via jsonschema but not the soft-warning tier;
  decide whether to depend on `portal/validation.py`.
- **Real artifacts + data governance.** `examples/` is gitignored; confirm what may leave SLAC
  machines at all.
