# ISAAC Metadata Assistant — Proposal v2

**Status:** revised proposal, 2026-07-04. Supersedes *Graphify_Backed_ISAAC_Metadata_Assistant_Proposal.docx* (v1).
**Deliverable owner:** Krish Verma (intern) · **Context:** ISAAC / SSRL / SLAC — AI-ready metadata infrastructure.

---

## 1. What changed from v1, and why

v1's goals and trust principles are kept in full. What changed is *how they are enforced* — the v2 design moves every trust-critical behavior out of prompts and into deterministic, testable code.

| v1 | v2 | Why |
|---|---|---|
| Schema + vocabulary listed as MVP *inputs* | Obtaining (or authoring) them is **Phase 0**, with a hard mentor sign-off gate | No machine-readable schema/vocabulary is available locally; an official schema (~v1.05?) may exist — first action is to request it |
| Validator, Evidence, parts of Audit as **LLM agents** | Deterministic Python (`isaac` CLI): JSON Schema + units + vocabulary + evidence checks | "No guessing" cannot be enforced by the component class most prone to guessing |
| 8 deployed agents | 8 *conceptual roles*, implemented as **one assistant workflow + a Python library + Graphify** (§4) | Multi-agent adds latency, cost, and state-handoff bugs an intern timeline can't absorb |
| Graphify as the general backend | Graphify as **optional, derived** relational memory with explicit query routing (§6) | Graphify's extraction is lossy; exact questions need exact sources |
| Evidence shown as a table at the end | Evidence **captured at extraction time, embedded per field**, and required by the validator (§5) | Evidence cannot be reconstructed after the fact; embedding makes "no guessing" structural |
| Records' storage location unspecified | A **git repository** is the source of truth (§7) | Git provides versioning, provenance, review, and change history for free |
| 11 slash commands | **5** (`draft`, `complete`, `validate`, `query`, `export`); evidence display folded into draft/validate | Ship five commands that work over eleven that half-work |
| Graph auto-updates on many triggers | Manual/best-effort refresh at export; auto-update deferred | Graphify already ships `--update` + commit hooks; wiring triggers is phase-3 polish |

## 2. Project overview (unchanged in spirit)

Scientists' metadata lives in Excel sheets, web forms, screenshots, PDFs, and notes. The assistant turns those into **validated, evidence-grounded, AI-ready ISAAC records**: it extracts candidate metadata, asks only the follow-up questions that block validation, builds a structured record, validates it deterministically, and shows exactly where every value came from.

**Core principle (unchanged):** no guessing, no invented values, no finalized field without evidence or user confirmation. **New in v2:** this is a property of the record format and validator, not a behavioral promise.

## 3. The record format

Every scientific field is an envelope:

```json
"temperature": {
  "value": 523,
  "unit": "kelvin",
  "status": "verified",
  "evidence": [{
    "source_type": "spreadsheet",
    "source_file": "examples/campaign_metadata.xlsx",
    "locator": "Sheet 'Configurations', cell D14",
    "quote": "523 K"
  }]
}
```

Statuses (tightened from v1):

| Status | Machine-checkable meaning |
|---|---|
| `verified` | ≥1 observed evidence entry (document/spreadsheet/screenshot/web form/file listing) **or** a user confirmation |
| `inferred` | ≥1 `derivation` evidence entry with a stated rule (e.g. "absorbing element = metal in sample.formula"); missing observed support downgrades to a warning |
| `needs_confirmation` | Plausible but requires scientific judgment — can never finalize |
| `missing` | Value must be `null`; honest and valid in drafts |
| `rejected` | Invalid or contradicted; excluded from finalization |

User answers are themselves evidence: `{"source_type": "user_confirmation", "question": …, "answer": …, "timestamp": …}` — so "confirmed by the user" is auditable, not implicit.

**Finalization rule:** a record enters `records/` only when every *required* field (base + technique-conditional, both defined in the schema's `x-field-rules` block) is `verified` or `inferred`. Raw data is linked by URI, never copied.

## 4. Architecture: conceptual roles → implementation

The v1 eight-role decomposition remains the right way to *think* about the system. It is implemented as three things:

| v1 conceptual agent | v2 implementation |
|---|---|
| Orchestrator | The five-command workflow itself (`draft → complete → validate → export`, `query` on the side) |
| Input/Extraction | `/isaac-draft` skill (LLM) — extraction with evidence capture at extraction time |
| Question | `/isaac-complete` skill (LLM) — question list generated *by the validator*, not by model judgment |
| Record Builder | `/isaac-draft` + `isaac_records.models` helpers |
| Validator | `isaac validate` — deterministic Python: JSON Schema Draft 2020-12 + pint units + vocabulary + evidence rules |
| Evidence | The record format itself + `isaac validate --evidence` rendering |
| Audit | `isaac audit` — a loop over the validator, exact by construction |
| Graph/Knowledge + Query | `/isaac-query` skill with explicit routing (§6); Graphify supplies the fuzzy layer |

The LLM touches exactly two steps — extraction and question-asking — and both are gated by the deterministic validator downstream.

## 5. Enforcement: how "no guessing" actually holds

1. The schema requires evidence structurally (`verified`/`inferred` ⇒ `evidence.minItems ≥ 1`; `missing` ⇒ `value: null`).
2. The validator (all rules read from the schema file, keeping it the single authority) rejects: finalized values without evidence, inferred values without a derivation rule, out-of-vocabulary terms, missing/unparseable/wrong-dimension units, raw data pasted instead of linked, and finalization with any required field unconfirmed.
3. Export is a validator-gated file move. There is no `--force`. A blocked export leaves the draft untouched.
4. Every rule has a failing test fixture (21 tests in `tests/`), so trust properties are regression-tested like any other code.

## 6. Graphify's role (right-sized)

Graphify turns the repo into a queryable knowledge graph (entity extraction, community detection, BFS/DFS query, incremental `--update`). That is genuinely valuable as **project memory**: "which campaigns are related to CuO?", "what connects this sample to that paper?"

It is *not* a database, so queries route by class:

| Question class | Source of truth |
|---|---|
| Required fields / structure | `schema/isaac_record.schema.json` (via `isaac required-fields`) |
| Allowed vocabulary | `vocabulary/*.json` |
| Completeness ("missing raw-data URIs?") | `isaac audit` |
| Schema change history | `git log` |
| Similarity / relationships / cross-experiment memory | `graphify query` |

**Graphify is optional and pluggable.** The core pipeline is fully functional without it (enforced by test); the graph refresh at export is best-effort and never blocks. Dependency note for SLAC data governance: Graphify is a third-party PyPI package that can route document content to the Gemini API *if* a key is set — the project runs it key-less, so extraction stays inside the local Claude session.

## 7. Source of truth: the git repository

```
schema/       vocabulary/     ← final authorities (mentor-gated changes)
records/      ← validated records; written only by `isaac export`
drafts/       ← pre-validation working copies
examples/     ← raw user artifacts (gitignored — data governance)
src/, tests/  ← deterministic core + trust-rule test suite
.claude/skills/isaac-*  ← the assistant workflow
graphify-out/ ← derived graph (gitignored, rebuildable)
```

The v1 trust hierarchy maps onto git mechanics: schema/vocabulary changes are commits (reviewable, revertible, historied); validated records enter history at export; meeting notes and AI extractions never enter `records/` without passing the validator.

## 8. Commands (MVP surface)

| Command | Purpose |
|---|---|
| `/isaac-draft` | Extract candidates + evidence from files → honest draft (no validity claim) |
| `/isaac-complete` | Ask **only** validator-identified blockers; answers become evidence |
| `/isaac-validate` | Run the validator; show report + per-field evidence map |
| `/isaac-query` | Routed question answering (schema / audit / git / graph) |
| `/isaac-export` | Validator-gated move into `records/` + optional graph refresh |

Deferred: `enrich`, `audit` as a user command (the CLI exists; the skill wrapper is trivial later), `status`, `explain`, `update-graph`, auto-updating triggers.

## 9. MVP demo (CuO / operando XAS — unchanged from v1)

Upload the campaign spreadsheet + web-form screenshots → `/isaac-draft` reports: verified (facility SSRL, beamline BL15-2, technique XAS, formula CuO, form powder, environment operando, pattern prod-check-CuO), missing (absorbing element, edge, detection mode, raw-data URI). `/isaac-complete` asks exactly those four questions — note that Cu is the *obvious* guess for absorbing element, and the assistant asking anyway **is the demo**. Answers become user-confirmation evidence; `/isaac-export` validates and lands the record in `records/` with a complete evidence map.

A hand-built version of this exact record exists today as `tests/fixtures/golden_cuo_xas.json` and passes finalization.

## 10. Roadmap (~6 weeks)

| Week | Milestone |
|---|---|
| 1 | Request official ISAAC schema/vocabulary from mentors; else finalize the provisional drafts in this repo. **Hard gate — mentor review of:** required fields, vocabulary terms, envelope structure, evidence rules, golden CuO record |
| 2 | *(done ahead of schedule — scaffolded)* validator + audit + CLI + trust-rule test suite |
| 3 | `/isaac-draft` exercised on the real artifacts; evidence-capture quality pass |
| 4 | `/isaac-complete` → `validate` → `export` end-to-end; rehearse the CuO demo |
| 5 | Graphify build over the repo; `/isaac-query` routing exercised against real questions |
| 6 | Audit report over accumulated records; polish; demo script; final proposal |

## 11. Risks and open questions

- **Does an official schema (v1.05?) exist, and can we get it?** Biggest unknown; determines whether Phase 0 is adoption or authoring.
- **Real artifacts needed** in `examples/` before Week 3 has anything to extract from.
- **Vocabulary decisions** need domain owners (e.g. is "XAS/EXAFS" one technique or two? MVP: single primary term).
- **Graphify dependency**: personal third-party package — acceptable for a prototype, flagged for anything production-adjacent.
- **Data sensitivity**: examples/ is gitignored and Graphify runs key-less by policy; confirm with mentors what may leave SLAC machines at all.

## 12. Concise pitch

An assistant that turns beamline metadata chaos into validated ISAAC records — where "no guessing" is not a promise but a file format. The LLM only extracts and asks; a deterministic validator owns truth; every value carries its evidence; git carries history; and an optional knowledge graph adds cross-experiment memory. The MVP demo takes one real CuO/XAS campaign from spreadsheet-and-screenshots to an exported, fully evidenced record.
