# Final deliverable outline — paper / poster / report

A skeleton for the intern write-up (paper, poster, or short report). Every claim below is what the
repo actually does today (`main`; see README.md and git history for current status) — future work is labeled as such.
Do **not** present future work as a current result.

Source material to reuse: [`docs/paper-notes.md`](paper-notes.md) (fuller prose),
[`docs/architecture.md`](architecture.md) (pipeline diagram + module map),
[`docs/mentor-decisions.md`](mentor-decisions.md) (open decisions), [`docs/demo.md`](demo.md) (results).

---

## Title options

1. **ISAAC Metadata Assistant: turning scattered experiment metadata into evidence-grounded,
   schema-valid records without guessing.**
2. **No-Guessing Metadata Authoring: an evidence-grounded assistant for official ISAAC records.**
3. **Draft, Cite, Refuse: building AI-ready DOE-BES catalysis records that never invent data.**

(1 is the safe default; 2 foregrounds the design principle; 3 is poster-punchy.)

## Abstract (bullet draft)

- **Problem.** Synchrotron catalysis metadata is scattered across spreadsheets, beamline forms,
  notebooks, and file archives; producing a record that matches the DOE-BES **ISAAC** AI-ready
  standard is slow and error-prone. Naively having an AI *fill in* a record risks
  plausible-but-invented values — worse than blanks.
- **Approach.** A two-plane assistant: a deterministic **truth plane** (extract → draft → validate →
  export → audit against the vendored official ISAAC v1.05 schema) with a strict **no-guessing**
  rule, and an optional **memory/query plane** (a Graphify knowledge graph) that provides context but
  never decides validity.
- **Mechanism.** Every drafted field carries `{value, unit?, status, evidence[]}`; unsupported values
  become explicit `pending[]` blockers, not guesses. Because the official record schema is
  `additionalProperties: false`, provenance is preserved in an **evidence sidecar** keyed by official
  JSON-path.
- **Result.** On a synthetic XANES-family campaign, the pipeline produces one official v1.05 record
  (26 evidenced fields; 5 blockers refused then human-answered; clean audit, `evidence 26/26`),
  reproducible byte-for-byte, with the full test suite passing.
- **Contribution.** A design pattern for trustworthy AI-assisted scientific metadata: evidence-first
  authoring, structural refusal to guess, and separation of *validity* (deterministic) from *memory*
  (AI/graph).

## 1. Introduction / problem

- Scientific-metadata bottleneck at beamlines; the ISAAC "AI-ready record" standard as the target.
- Why "let the AI fill it in" fails for science (invented hash/unit/energy looks trustworthy, isn't).
- Thesis: an assistant that **drafts fast, cites evidence, and refuses to guess**.
- Scope statement (state up front, honestly): synthetic data, one characterization/XANES path,
  proof-of-concept.

## 2. Methods

- **Two-layer pipeline.** Draft layer (authoring, evidence envelopes) vs. truth layer (export +
  official-schema validation). Boundary is strict.
- **No-guessing, concretely.** `pending[]` blockers and `implicit[]` inferences; no value enters a
  draft without a source locator.
- **Schema-gated export.** Refuses unless *both* no-guessing checks and official v1.05 schema pass;
  no `--force`.
- **Evidence sidecar.** Why (schema is `additionalProperties:false`); how (keyed by official
  JSON-path + `assets:`/`descriptors:`/`implicit:` namespaces). Note it is an **assistant convention**
  pending mentor approval (decision D1) — do **not** call it an official ISAAC artifact.
- **Two planes.** Deterministic truth plane vs. optional Graphify memory plane; the truth core is
  tested to never import the graph.

## 3. System architecture

- Pipeline figure (reuse [`docs/architecture.md`](architecture.md)).
- Module map: `official.py` (schema validation), `draft_validator.py` (no-guessing), `export.py`
  (gated transform + sidecar), `audit.py`, `cli.py`; `portal_warnings.py` (advisory seam).
- Assistant layer: five `/isaac-*` Claude skills as the operator interface over the CLI.
- Delivery shape: local Python CLI + tooling (not a web app, not MCP).

## 4. Demo workflow

- The end-to-end synthetic run (reuse [`docs/demo.md`](demo.md) output).
- Emphasize the **5 refused blockers** moment and the reproducibility check.
- Note completion is simulated by an answers fixture standing in for `/isaac-complete`.

## 5. Validation strategy

Staged checks, each with a fixed authority (the AI never overrides code):
1. Draft no-guessing validation — gates authoring.
2. Official ISAAC v1.05 schema validation — gates export.
3. Portal-style advisory soft-warnings (`--warnings`) — **non-gating** local seam; not upstream parity.
4. Advisory AI scientific review — **placeholder only**.
5. Human review — final decider.
The **audit** ties 1–2 together on stored records (schema-valid + every sidecar path resolves).

## 6. Results so far

- Official record `01JQZ0SYNTHXANESDEMO000000`: **26** evidenced fields; **5** blockers refused then
  answered; **3** assets resolved from human answers; validates against v1.05; clean audit
  (`evidence 26/26`, 0 dangling); **byte-identical reproducible**.
- **Quotable poster numbers:** 1 official record · 26 evidenced fields · 5 blockers refused-then-answered
  · 10 official golden records validating · **137 passing Python tests** · 0 audit failures.
- A test asserts every scientific value traces to a committed synthetic fixture (nothing fabricated).

## 7. Limitations (state honestly)

- One path only (single XANES-family / characterization record, synthetic structured input).
- Extraction is structured-only; screenshots/PDFs/notes/web-forms are designed, not implemented.
- Completion is simulated in the demo.
- The evidence sidecar is an assistant convention, not (yet) an official ISAAC artifact.
- Portal soft-warnings are a local non-gating stand-in, not upstream parity.
- The advisory AI review is a placeholder.
- Graphify is optional; the query/memory layer (routing, `/isaac-query`, graceful-degradation + freshness tests) is built, but a deeper behavioral routing simulation is still future work.

## 8. Future work

Tie each to a mentor decision where relevant ([`docs/mentor-decisions.md`](mentor-decisions.md)):
- LLM-assisted extraction of unstructured artifacts, still evidence-cited (needs D4 for real data).
- Second record domain — performance/electrochemistry — to exercise conditional-required rules (D6).
- True portal-validator parity by vendoring upstream `portal/validation.py`, still non-gating (D2).
- Grow the advisory scientific review from placeholder to real checks (advisory-only).
- Deeper Graphify query/memory layer — behavioral routing simulation beyond the current graceful-degradation + freshness test tier (D5).
- Real/sanitized data pilot — **only** with written governance approval (D3/D4).

## Figures / tables to include

- **F1** — Pipeline diagram (truth plane vs. memory plane), from `docs/architecture.md`.
- **F2** — The Step-1 demo output showing the **5 refused blockers** (the no-guessing moment).
- **F3** — Side-by-side: one draft field `{value, status, evidence}` → its official record value +
  sidecar entry (shows where provenance goes after export).
- **T1** — Validation stages table (stage · authority · gates? · implemented?).
- **T2** — Results table (fields, blockers, assets resolved, audit, tests).
- **T3** *(optional)* — Open decisions D1–D8 with recommended defaults (for a "next steps" panel).
