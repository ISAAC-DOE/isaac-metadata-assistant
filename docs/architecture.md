# Architecture overview (for reviewers)

A one-page map of how the ISAAC Metadata Assistant turns experiment metadata into an official,
evidence-grounded ISAAC v1.05 record. It is kept accurate to the code in this repo;
where something is designed but not yet built, it says so.

## The pipeline

```
 INPUT ARTIFACTS (synthetic today)
   mock_campaign.csv        raw_scan_listing.txt        xanes_completion_answers.json
   (structured sheet)       (archive listing, no hashes) (simulated human answers)
        │                          │                              │
        ▼                          ▼                              │
 ┌───────────────────────────────────────────┐                   │
 │ DETERMINISTIC EXTRACTORS  (zero LLM)        │                  │
 │   extract/structured.py   sheet → fields    │                  │
 │   extract/file_listing.py listing → assets  │                  │
 └───────────────────────────────────────────┘                   │
        │                                                         │
        ▼                                                         │
 ┌───────────────────────────────────────────┐                   │
 │ DRAFT BUILDER   extract/draft_builder.py    │                  │
 │   assembles the draft envelope:             │                  │
 │   fields{path:{value,unit,status,evidence}} │                  │
 │   implicit[]  (absorbing_element, edge)     │                  │
 │   pending[]   (sha256, series, descriptor)  │  ← never guessed │
 └───────────────────────────────────────────┘                   │
        │                                                         │
        ▼                                                         ▼
 ┌───────────────────────────┐          ┌──────────────────────────────────┐
 │ DRAFT VALIDATION           │          │ COMPLETION  complete.py           │
 │ draft_validator.py         │          │   apply_answers(draft, answers)   │
 │   no-guessing checks        │─────────▶│   fills pending[] from answers,   │
 │   (draft passes with        │          │   each as user_confirmation       │
 │    pending open)            │          │   evidence; unanswered stays open │
 └───────────────────────────┘          └──────────────────────────────────┘
                                                     │
                                                     ▼
 ┌──────────────────────────────────────────────────────────────┐
 │ EXPORT (schema-gated)   export.py                              │
 │   transform(): drop the envelope, keep values → official shape │
 │   validate_official(): jsonschema against v1.05 (official.py)  │
 │   build_sidecar(): official JSON-path → evidence               │
 │   refuses unless BOTH no-guessing AND official schema pass      │
 └──────────────────────────────────────────────────────────────┘
        │                                   │
        ▼                                   ▼
 records/<ULID>.json                 records/<ULID>.evidence.json
 (official ISAAC v1.05)              (evidence sidecar)
        │
        ▼
 ┌───────────────────────────┐
 │ AUDIT   audit.py           │
 │   every record re-validates │
 │   + every sidecar path      │
 │   resolves (0 dangling)     │
 └───────────────────────────┘
```

## The two planes

The system deliberately separates **what is true** from **what we remember**.

- **Truth plane (deterministic, LLM-free, Graphify-free).** `schema/isaac_record_v1.json`,
  `official.py`, `draft_validator.py`, `export.py`, `audit.py`, `cli.py`, plus `ids.py`/`models.py`
  and the `extract/` seam. This path decides whether a record exists and is valid. It never imports
  Graphify — enforced by `test_core_never_imports_graphify`.
- **Memory / query plane (Graphify-central, optional).** Project memory, relationship/similar-record
  search, documentation search, "what changed?" history. It can *suggest context* but **cannot
  authorize export**. The truth plane runs correctly with Graphify entirely absent.

If a graph answer ever conflicts with the schema, a validated record, or the audit, the
deterministic source wins.

## Module map

| Module | Plane | Role |
|---|---|---|
| `schema/isaac_record_v1.json` | truth | **Vendored official schema (v1.05) — the authority.** Provenance in `schema/PROVENANCE.md` |
| `official.py` | truth | `validate_official(record, root)` — jsonschema against the vendored schema |
| `draft_validator.py` | truth | `validate_draft(draft)` — no-guessing checks (evidence required, missing ⇒ null, assets need sha256) |
| `export.py` | truth | `transform` (draft → official shape), `build_sidecar`, `export_draft` (gated by both validators) |
| `audit.py` | truth | Re-validate every record in a dir + confirm sidecar dotted paths resolve |
| `cli.py` | truth | `isaac validate | export | audit | new-id` |
| `ids.py` / `models.py` | truth | ULID record ids; the draft envelope + evidence constructors |
| `extract/structured.py` | truth-adjacent | Structured sheet (`.csv`/`.xlsx`) → evidenced `fields` with precise locators |
| `extract/file_listing.py` | truth-adjacent | Archive listing → asset URI candidates (**no sha256**) |
| `extract/draft_builder.py` | truth-adjacent | Assemble the draft envelope, `implicit[]`, and `pending[]` blockers |
| `complete.py` | authoring (non-truth) | `apply_answers` — fill `pending[]` from human answers as `user_confirmation` evidence; never invents values |
| `portal_warnings.py` | advisory (isolated) | Non-gating portal-style **soft-warnings** (local heuristics: `NO_LINKS`, `QC_NONVALID_WITHOUT_EVIDENCE`) — read-only, no validity verdict, not imported by the truth path |
| `review.py` | advisory (isolated) | **Placeholder** advisory reviewer — never marks valid/invalid, never mutates, not imported by the truth path |
| `.claude/skills/isaac-*` | assistant | The `/isaac-draft`, `/isaac-complete`, `/isaac-validate`, `/isaac-export`, `/isaac-query` workflows |

For a concept→file quick map that complements this table, see
[`project-memory-map.md`](project-memory-map.md).

## Why the sidecar exists

The official record schema is `additionalProperties: false` — it has **no room for per-field
provenance**. So evidence is preserved in a separate `…​.evidence.json` sidecar keyed by official
JSON-path (and by `assets:` / `descriptors:` / `implicit:` for the structured blocks). The record
stays schema-clean; auditability survives export. The sidecar is an assistant audit artifact unless
mentors adopt it as an official ISAAC convention.

## What is deterministic vs. what needs a human

- **Deterministic (system does it, zero LLM):** parse the structured sheet + file listing, build the
  evidenced draft, run the no-guessing checks, transform to the official shape, validate against the
  schema, build the sidecar, and audit.
- **Human-supplied (system refuses to guess):** file `sha256`s, the reduced spectrum
  (`measurement.series`), at least one descriptor, and the absorption `edge`. These surface as
  `pending[]` blockers (or a null `implicit[]` candidate for `edge`) and are answered through
  `/isaac-complete`.

## Not built yet (future / optional)

- **LLM-assisted extraction** of screenshots, PDFs, notes, and web-form dumps — designed in
  `docs/extraction.md`, not implemented. Today's extraction covers the structured sheet + listing.
- **Graphify memory/query layer** — the plane exists and `/isaac-query` routes to it; a reviewer
  demo is in [`query-demo.md`](query-demo.md). The deeper query-layer work (an automated
  graceful-degradation test tier) is **deferred**.
- **True portal parity** — a **non-gating advisory soft-warning seam** now exists
  (`portal_warnings.py`, `isaac validate --warnings`; see [`portal-warnings.md`](portal-warnings.md)),
  but it is **local heuristics, not** the upstream `portal/validation.py` (not vendored). Full parity
  is future work.
- **Advisory AI review** — `review.py` is a no-op placeholder by design.
- **Real / sanitized data** — only synthetic fixtures are processed; real data requires explicit
  approval per `docs/intake.md`.
