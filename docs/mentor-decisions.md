# Mentor decision package — ISAAC Metadata Assistant

**For:** Angel, Dean, and ISAAC mentors · **From:** Krish Verma (intern)
**Repo state:** `main`, clean, full test suite passing (see git history for the exact commit).

> For a shorter overview start with **[`mentor-brief.md`](mentor-brief.md)**; the live-meeting
> walkthrough is **[`demo-script.md`](demo-script.md)**. This file remains the detailed decision
> register (D1–D8). The decisions below are unchanged since Phase 8 — later phases (portal seam,
> Graphify demo, docs) added no new decisions.

This is a decision-oriented summary. It exists so you can review the prototype quickly and tell
me which way to go next. Each open decision below lists **our recommended default**, the
**tradeoffs/risks**, and **what changes if you say yes vs. no** — so a decision can be made in one
pass without reading the code. Nothing here changes behavior; it is a request for direction.

---

## 1. Current prototype status

A working, synthetic, end-to-end prototype that turns scattered experiment metadata into an
**official ISAAC v1.05 record** plus an **evidence sidecar**, without guessing.

- Source of truth is the **official ISAAC schema** (`schema/isaac_record_v1.json`, v1.05, vendored,
  provenance pinned). We do not author or maintain a record schema.
- One path is complete end-to-end: **characterization / XANES-family (`record_type=evidence`)**.
- The deterministic core (extract → draft → validate → export → audit) is **LLM-free and
  Graphify-free**, enforced by a test.
- **The full test suite passes**, including that all 10 official golden records validate, that export is
  doubly gated, that sidecar paths resolve, and that the truth core never imports Graphify or the
  advisory soft-warning seam.
- A reproducible demo (`scripts/run_synthetic_demo.py`) regenerates a committed sample record
  **byte-for-byte**.

Maturity: **prototype / proof-of-concept**, not a production service. It is ready to *demo and
review*, not to ingest real beamline data yet (that is a decision below).

## 2. What is already working (verified)

- **Deterministic extraction** from a structured campaign sheet (`.csv`/`.xlsx`) and a raw file
  listing → per-field evidence with precise locators.
- **Draft assembly** with `{value, unit?, status, evidence[]}` envelopes, `implicit[]` inferences
  (e.g. absorbing element / edge), and `pending[]` blockers for anything unsupported.
- **No-guessing draft validation** — refuses a finalized field with no evidence, an asset with no
  `sha256`, a descriptor with a null value.
- **Completion** — applies human answers to blockers as `user_confirmation` evidence; never invents.
- **Schema-gated export** → official ISAAC v1.05 record + evidence sidecar; refuses unless *both*
  no-guessing and official-schema checks pass. No `--force`.
- **Audit** — every stored record re-validates and every sidecar path resolves (0 dangling).
- **CLI**: `isaac validate | export | audit | new-id`, and the `/isaac-*` skill workflow.

Demo result: official record `01JQZ0SYNTHXANESDEMO000000` — 26 evidenced fields, 5 blockers
correctly refused then human-answered, valid against v1.05, clean audit (`evidence 26/26`).

## 3. What is intentionally synthetic / demo-only

These are deliberate scope choices, not gaps we missed:

- **All input data is synthetic.** A fictional year-2099 SSRL session, fictional people. No real
  SLAC/SSRL data has been read, committed, or shown to any model. `examples/` is gitignored.
- **Completion is simulated in the demo.** An answers fixture stands in for a human typing into
  `/isaac-complete`.
- **Extraction is structured-only.** Screenshots, PDFs, notes, and web-form dumps are **designed**
  (`docs/extraction.md`) but **not implemented** — no LLM extraction runs yet.
- **Graphify (memory/query plane) is present.** The query-layer phase (routing, `/isaac-query`,
  graceful-degradation + freshness tests) has since been built; a deeper behavioral routing
  simulation remains future work. The truth pipeline runs fully without it.
- **Portal-style soft-warnings** now have a **non-gating local advisory seam** (`portal_warnings.py`,
  `isaac validate --warnings`; Phase 8) — **not** upstream parity. The **advisory AI review** remains
  a stub. Neither gates anything.

---

## 4. Decisions that need mentor input

Quick view (details follow):

| # | Decision | Our recommended default |
|---|---|---|
| D1 | Is the evidence **sidecar** an acceptable ISAAC assistant convention? | Keep it; propose it upstream as an *optional companion* artifact |
| D2 | Whether/how to integrate the official **portal soft-warning** tier | Vendor + integrate as a **non-gating** advisory stage; never blocks export |
| D3 | Data-governance boundaries for **real or sanitized** data | Stay synthetic-first; real/sanitized only with written approval + a defined boundary |
| D4 | May **Claude/LLMs inspect real** experiment artifacts? | **No** by default; deterministic-only on real data until explicitly approved |
| D5 | **Graphify** in the near-term demo, or stay deferred? | Keep **deferred**; demo the deterministic truth plane |
| D6 | Which **domain** comes after XANES-family? | **Performance / electrochemistry** (exercises conditional-required rules) |
| D7 | What is the **final summer deliverable**? | Prototype + official-valid sample + docs + paper/poster (proof-of-concept) |
| D8 | What should the **paper/poster** emphasize? | No-guessing + evidence sidecar auditability + truth/memory separation |

### D1 — Evidence sidecar as an accepted ISAAC assistant convention

**Question.** The official record schema is `additionalProperties: false` and has no per-field
provenance slot. We preserve evidence in a separate `records/<ULID>.evidence.json` sidecar keyed by
official JSON-path (plus `assets:` / `descriptors:` / `implicit:` namespaces). Is this an acceptable
assistant convention, or should evidence map *only* into native slots (`qc.assumptions`,
`uncertainty.basis`, descriptor `generated_by`)?

**Recommended default.** Keep the sidecar as the assistant's audit artifact **and** propose it to
ISAAC as an *optional companion file* (record stays 100% standard; sidecar travels alongside).

- **Tradeoffs / risks.** Pro: full field-level auditability without touching the standard; the
  record alone always validates. Con: it is out-of-standard, so a consumer that only reads the
  record loses provenance; risk of drift between record and sidecar (mitigated today by the audit
  that checks every sidecar path resolves).
- **If yes (adopt/endorse).** We document it as a supported convention and can pitch it upstream as
  an optional artifact. No code change required — it already works.
- **If no (native-only).** We map what fits into native slots and **drop** evidence that has no home
  (edge/absorbing-element provenance, per-asset source lines). Auditability shrinks to what the
  schema can hold; this is a real information loss and would need a follow-up slice.

### D2 — Official portal soft-warning validation

**Question.** Upstream ships `portal/validation.py` with a **soft-warning** tier on top of the hard
schema rules. We currently cover all hard/400 rules via jsonschema but do **not** run the soft tier.
Integrate it, and if so, how?

**Recommended default.** Vendor and integrate it as **validation stage 3 — non-gating advisory
warnings** only. It never blocks export; it surfaces "you probably want to fix this" notes.

**Status (Phase 8 — partial).** The non-gating advisory **seam** is now built: `portal_warnings.py`
runs as validation stage 3, surfaced via `isaac validate --warnings`, with tests proving it never
changes official pass/fail and is not imported by the truth path (see
[`portal-warnings.md`](portal-warnings.md)). It emits two schema-grounded **local heuristics**
(`NO_LINKS`, `QC_NONVALID_WITHOUT_EVIDENCE`) — **not** the real upstream rule set. The remaining open
question is therefore narrower: **vendor the upstream `portal/validation.py` for true parity, or keep
the local seam as-is?**

- **Tradeoffs / risks.** Pro: parity with the official portal; catches soft issues before a human
  does. Con: a new upstream dependency to pin and refresh; its warnings must never be mistaken for
  hard failures; version drift vs. the schema. Keeping it strictly non-gating avoids changing what
  "valid" means.
- **If yes.** One focused slice: vendor `validation.py` (with provenance), wire it as advisory,
  show warnings in `/isaac-validate`, add tests that it never changes pass/fail of official
  validation.
- **If no.** We stay hard-rules-only (already complete) and note portal parity as future work. Zero
  new dependency, slightly less pre-human polish.

### D3 — Data-governance boundaries for real or sanitized data

**Question.** Everything so far is synthetic. What may we do with real or sanitized artifacts, and
what is allowed to leave SLAC/SSRL machines at all?

**Recommended default.** Stay **synthetic-first**. Process real or sanitized data only after
written mentor approval that names (a) exactly which artifacts, (b) whether they may leave SLAC
machines, and (c) whether they may be committed (default: never). Sanitized > raw whenever possible.

- **Tradeoffs / risks.** Pro: no accidental exposure of private/proprietary beamline data; matches
  the repo's existing governance (`docs/intake.md`, gitignored `examples/`). Con: we can't claim a
  "real data" result until this is granted; the prototype's realism is capped until then.
- **If yes (approve a bounded real/sanitized path).** We add a documented intake procedure for the
  named artifacts, keep them local/gitignored, and report exactly what was read each run.
- **If no (stay synthetic).** No change; we continue on synthetic fixtures and present the prototype
  as a proof-of-concept. This is a safe default and blocks nothing else on this list.

### D4 — May Claude/LLMs inspect real experiment artifacts?

**Question.** Distinct from D3: even if real data is allowed locally, may an **LLM** read it (e.g.
LLM-assisted extraction of a real screenshot/PDF/notes)?

**Recommended default.** **No** by default. Real data is handled by the **deterministic** extractors
only. LLM extraction stays on synthetic data until a specific, written approval says which real
artifacts a model may see and where that model runs.

- **Tradeoffs / risks.** Pro: nothing real is sent to a model or external API without explicit
  sign-off; conservative and defensible. Con: LLM-assisted extraction (the biggest realism upgrade)
  can only be demonstrated on synthetic inputs until approved.
- **If yes (approve LLM on named real artifacts).** We document the boundary (which artifacts, which
  model, local vs. hosted) and proceed with LLM extraction on just those, still evidence-cited.
- **If no.** LLM extraction is developed and demonstrated on synthetic artifacts only; real data, if
  approved under D3, is deterministic-only.

### D5 — Graphify in the near-term demo, or stay deferred?

**Question.** Graphify is the memory/query plane (project memory, similar-record lookup, "what
changed?"). It is central for *memory*, never for *truth*. Include it in the near-term demo, or keep
it deferred?

**Recommended default.** Keep it **deferred** for the near-term demo. Demo the deterministic truth
plane (which is the scientifically load-bearing part). Bring Graphify in as a later, clearly-labeled
memory/query phase.

- **Tradeoffs / risks.** Pro: the demo stays tight, deterministic, and reproducible; no risk of a
  graph answer being mistaken for authoritative. Con: we don't show the "living project memory"
  story yet, which is a compelling part of the vision.
- **If yes (include now).** We build the query-layer slice (routing + graceful-degradation tests)
  before the demo — more surface area, more to verify, and it must be visibly non-authoritative.
- **If no (defer).** No change; Graphify stays optional and the truth pipeline is unaffected. It
  becomes a strong "next phase" talking point.

**Status (Phases 13–16 — built).** The query-layer slice was subsequently implemented: explicit
routing, the `/isaac-query` skill, a query cookbook, a graceful-degradation + freshness test tier
(`tests/test_query_safety_docs.py`, `tests/test_graphify_freshness.py`), and a freshness helper —
all non-authoritative (never validates or authorizes export). The open question is now narrower:
how much further to invest (e.g. a live behavioral routing simulation).

### D6 — Which domain comes after the XANES-family path?

**Question.** The one complete path is characterization/XANES. What is the second domain?

**Recommended default.** **Performance / electrochemistry** (e.g. galvanostatic). It is the domain
that exercises the schema's **conditional-required** machinery (`record_domain=performance` +
galvanostatic ⇒ `current_setpoint_mA_cm2`, `rhe_basis` trust tiers), which is the most valuable
schema coverage to prove next.

- **Tradeoffs / risks.** Pro: stress-tests the `allOf` if/then rules and the trust-tier fields —
  the parts XANES doesn't touch. Con: a genuinely new block set and vocabulary; more design lift
  than a second characterization technique.
- **Alternative (lower lift).** A second characterization technique (EXAFS/XRD) reuses most of the
  XANES path — faster, but proves less new schema coverage.
- **If yes (performance).** We scope a performance draft→record slice against the official
  performance golden example; expect new extractor fields + conditional-required tests.
- **If no / pick the alternative.** We add a second characterization technique instead; quicker, but
  the conditional-required rules stay unexercised until later.

### D7 — What counts as the final summer deliverable?

**Question.** What is the bar for "done" this summer?

**Recommended default.** A **working proof-of-concept**: the deterministic synthetic pipeline, at
least one official-schema-valid record + sidecar, the reproducible demo, the architecture/paper
docs, and an intern paper/poster. Explicitly **not** a production ingestion service.

- **Tradeoffs / risks.** Pro: achievable, already ~90% there, honest about scope, reviewable. Con:
  it is synthetic and single-domain unless D3/D4/D6 expand it.
- **Options.** (a) *Recommended* — prototype + writeup as above. (b) Prototype + **one real
  sanitized record** (requires D3, possibly D4). (c) **Multi-domain** prototype (requires D6 and
  more time). Each larger option adds risk and depends on approvals above.
- **If yes (a).** We polish, freeze scope, and focus effort on the paper/poster and demo quality.
- **If a bigger bar (b/c).** We re-plan time toward real-data intake or a second domain and treat
  the writeup as concurrent, not final-week, work.

### D8 — What should the intern paper/poster emphasize?

**Question.** What is the headline contribution to foreground?

**Recommended default.** Emphasize the **design principle**, not raw feature count:
1. **No-guessing / evidence-grounded** authoring (blockers are refused, not fabricated).
2. The **evidence sidecar** as the mechanism that keeps auditability against a closed
   (`additionalProperties: false`) official schema.
3. The **truth vs. memory two-plane** separation (deterministic validity; optional graph memory).

Quotable numbers: 1 official record, 26 evidenced fields, 5 blockers refused-then-answered, 80
passing tests, 0 audit failures. (See `docs/paper-notes.md` for the full draft.)

- **Tradeoffs / risks.** Pro: the design ideas generalize beyond XANES and are the real research
  contribution. Con: reviewers may want a real-data result; we must state synthetic-only honestly.
- **If yes.** Poster/paper lead with the principle + the sidecar figure + the "5 refused blockers"
  moment.
- **If mentors prefer a results-forward framing.** We re-weight toward the demo record and metrics,
  and clearly caveat the synthetic, single-domain scope.

---

## 5. Remaining open decisions (summary)

All eight decisions above (D1–D8) are open and awaiting mentor direction. None of them block each
other except by dependency:

- **D3 gates D4** (LLM on real data requires real data to be allowed at all).
- **D3/D4/D6 gate the size of D7** (real-data or multi-domain deliverables need those approvals).
- **D1, D2, D5** are independent and can be decided in any order.

Nothing in this document has changed code or behavior. The prototype remains synthetic-first,
single-domain, and demo-ready as described in §1–§2.

## 6. Recommended next step (Phase 7 candidate)

Assuming the recommended defaults, the highest-value next slice is **D6 → the second domain
(performance / electrochemistry)**, because it proves new schema coverage (conditional-required
rules) using only synthetic data — no data-governance approval required. If mentors instead
prioritize realism, the gating decision is **D3/D4** (approve a bounded real/sanitized path). Either
way, we recommended keeping **D5 (Graphify)** deferred (since built — see the D5 status note above)
and **D2 (portal tier)** as a small non-gating add whenever convenient.

We are ready to proceed on whichever decision you make first.
