# Claude Design brief — ISAAC Metadata Assistant UI

> Copy-paste this whole document into a Claude Design session as the opening prompt. It is
> self-contained — you do not need to open any other file first. Links at the bottom go deeper if
> you want them.

**Design a local-first web UI for a scientific metadata tool whose core promise is: it never
guesses.**

---

## Product summary

ISAAC Metadata Assistant turns scattered experiment metadata (campaign spreadsheets, file listings,
eventually screenshots/notes) into validated, evidence-grounded **official ISAAC records** (a DOE-BES
"AI-ready record" schema, v1.05). Every finalized field must carry evidence or an explicit human
confirmation, or it stays honestly blank — no invented values, ever. A deterministic Python CLI and
five Claude authoring skills already implement this end to end; **no UI exists yet**. You are
designing the first one: a visual, low-friction front end over a system that already works
correctly on the command line.

The pipeline, in one line:

```
files → evidence-tagged draft → refused blockers → human-confirmed answers → official record +
evidence sidecar → schema validation (PASS/FAIL) → evidence audit (coverage) → advisory warnings
(non-gating) → optional assistant/memory Q&A
```

## Desired design feel

Premium **scientific instrument**. Calm, trustworthy, restrained, evidence-first. The strongest
visual signal anywhere in the product is the deterministic verdict; everything else defers to it.

Deliberately **not**:

- a chatbot toy — the assistant is a helper, never the product;
- a generic admin dashboard — no vanity KPIs, no gauge clusters, no invented health scores;
- an over-automated black box — no "AI did it for you" theater; every value traces to its source;
- a flashy AI product — no shimmer, no sparkle-AI iconography, no hallucination-vibe gradients.

Core metaphor: a **scientific record workbench**. One record is the workpiece; the operator
assembles it from evidence while a deterministic inspector gives a hard pass/fail. Premium but
restrained — think precise instrumentation, not a consumer app.

## Main workflow to design around

The synthetic demo happy path — every step maps to a real command that runs today, on committed
fake fixture data (a fictional year-2099 CuO / Cu K-edge XANES session):

1. Load the synthetic demo (clearly labeled fake/safe).
2. Draft assembly — fields appear, each with a status chip and cited evidence.
3. Blockers surface — 5 things the system refuses to guess (3 file hashes, a spectrum pointer, one
   scientific descriptor), styled as expected "needs a human" questions, not errors.
4. Human completion — one question per blocker; "I don't know" is a safe, legitimate answer that
   leaves the field honestly missing.
5. Export — draft becomes an official record **plus** a separate evidence sidecar; doubly gated
   (no-guessing checks, then official schema).
6. Validate — hard verdict: **PASS/FAIL** against official ISAAC v1.05.
7. Audit — evidence coverage (`evidence N/N`), a distinct, non-gating signal.
8. Advisory warnings — non-gating soft notes (e.g. `⚠ [NO_LINKS]`); verdict never changes.
9. Assistant / memory Q&A — optional, always labeled with its source, never authoritative.

## Screens to design

Thirteen screens. The core artifact screens (4, 6, 7, 10) share one layout; Home, Intake,
Governance, Settings, and Diagnostics are full-canvas or standalone.

1. **Home / dashboard** — orient, list records/drafts, launch the demo.
2. **Demo runner** — the synthetic pipeline end to end, real stage-by-stage progress.
3. **File intake (future, gated placeholder)** — clearly marked not production-ready; real-data
   banner.
4. **Draft review** — every field with its status chip and evidence citation.
5. **Missing fields / completion** — the blocker questions, one at a time, batched.
6. **Evidence sidecar viewer** — JSON-path → source provenance, labeled an assistant convention.
7. **Validation & audit results** — the hard verdict plus the coverage figure, visually separated.
8. **Advisory warnings** — `⚠ [CODE]` chips, explicitly non-gating.
9. **Assistant / Graphify panel** — navigation and memory, "answered from" on every reply.
10. **Export / download** — two artifact cards: the record and the sidecar.
11. **Data-governance / safety** — synthetic-only policy, real-data intercepts.
12. **Settings** — minimal local config (root path, records dir, demo output dir).
13. **Developer / diagnostics (hidden)** — raw CLI output, exit codes, freshness checks.

**Suggested layout**, endorsed with one refinement: **left rail = the gated workflow spine** (draft →
complete → export → validate → audit), showing the current blocking gate, not just a nav menu;
**main canvas = the current artifact** (draft, record, or sidecar), always the largest, calmest
surface; **right panel = evidence stacked above the assistant/memory** — evidence is deterministic
truth and belongs visually with the artifact, while the assistant is advisory and must read as
subordinate, so keep them stacked or tabbed but never blended; **a persistent status bar** carries
the verdict, the coverage figure, and the advisory count as three distinct readouts. This layout
holds for the artifact-centric screens; Home/Governance/Settings are full-canvas and don't need the
rail/panel split.

## The three-signal status model

Three signals, three different jobs, **never** collapsed into one badge, and reserved verdict colors
are never reused elsewhere:

| Signal | Meaning | Gates export? | Visual weight |
|---|---|---|---|
| **Validation PASS/FAIL** | Deterministic verdict against official ISAAC v1.05 | **Yes — the hard gate** | Dominant: boldest, most saturated, largest |
| **Audit `evidence N/N`** | Sidecar coverage — every evidence path resolves | No — not a validity re-vote | Neutral: secondary, informational tone |
| **Advisory `⚠ [CODE]`** | Non-gating soft notes from a local heuristic seam | Never | Subordinate: amber, tertiary weight |

A viewer glancing at the status bar must tell these apart without reading. Never render a warning
that could be mistaken for a FAIL, or a coverage figure that could be mistaken for a PASS.

## AI/Graphify behavior rules

- The assistant (Claude) and Graphify are **optional helpers**, always visually subordinate to every
  deterministic surface.
- The only place AI touches a value: **propose → confirm → evidence.** The assistant may propose a
  value with a cited source; the user must explicitly confirm; only then is it stored, as
  `user_confirmation` evidence alongside — never replacing — the deterministic evidence.
- Every assistant/Graphify answer carries an **"answered from: …"** label (schema / audit / git /
  graph / files). An answer with no traceable source is not shown.
- Graphify carries a **freshness indicator**: `fresh` / `stale` / `missing`. Stale or missing still
  answers from files and discloses the situation — it never blocks the task and never fabricates
  graph output.
- Graceful degradation is the rule: if the assistant/Graphify is unavailable, the deterministic
  screens keep working normally; the UI says so rather than silently failing.
- Refusal (to invent a value, to validate, to process real data) is styled as **protective** — the
  no-guessing policy made visible — never as an error or an apology.

## Data-governance rules

- **Synthetic-only by default.** A persistent, always-visible mode indicator tells the operator
  which data regime is active.
- Real or private data is **approval-gated** — it needs explicit written approval before it can be
  loaded, indexed, or sent to any model.
- **Local-first**: no cloud storage of records/drafts/evidence by default, no telemetry, no analytics
  or usage beacons.
- Before sharing/exporting a record, surface a **sidecar review** step — the sidecar can carry
  identifying provenance (file paths, URIs, hashes) even though today's data is fake.

## What must never be overclaimed

These specific claims must never appear in labels, tooltips, empty states, or copy:

1. That the AI creates scientific truth — it drafts and cites; humans confirm; the schema decides.
2. That Graphify validates anything — a graph answer is never a validity, completeness, or value
   claim.
3. That zero advisory warnings equals portal acceptance — the real upstream portal validator is not
   vendored here.
4. That real experiment data is supported — only synthetic fixtures are processed today.
5. That any upload path is production-ready — none exists yet; any future one is governance-gated.
6. That a missing field can be invented — a blank stays blank until a human confirms it.
7. That the evidence sidecar is an official ISAAC standard — it is an assistant convention, pending
   a mentor decision.
8. That a license has been decided — none has; this is a research prototype with no reuse rights
   granted by public visibility.

## Field/evidence presentation essentials

- **Status chips:** `verified`, `user-confirmed`, `inferred`, `missing`, `pending` — each gets a
  color + icon + short label, never color alone.
- **Blockers are the product working as intended**, not errors — style them as a calm "needs you"
  state, never as a red failure. "I don't know" is a legitimate, non-penalized answer.
- **Monospace** for every technical value the user might need to verify: ULIDs, sha256 hashes, URIs,
  JSON paths, enum tokens, raw JSON. This is a trust signal — technical values are never
  "prettified."
- **Record and sidecar are two separate artifact cards.** The record is schema-clean and official;
  the sidecar is a clearly-labeled assistant convention that carries provenance the record can't.

## Constraints

- **Design only** — no implementation, no code, no dependency choices are expected or wanted in this
  session.
- **Light and dark themes**, both meeting **WCAG AA** contrast.
- **Never encode a distinction by hue alone** — pair every color with an icon and/or text label so
  the three signals and the status chips work in grayscale and for color-blind users.
- **Responsive**, collapsing the rail/canvas/panel split sensibly on narrow widths — but never
  hiding the verdict, whatever the viewport.

## Deliverables expected from Claude Design

- Overall visual direction and a design-token set (color, type, spacing) consistent with the feel
  above.
- The workbench layout system (rail / canvas / evidence+assistant panel / status bar) and how it
  collapses responsively.
- High-fidelity mockups of the priority six screens: **Home, Demo runner, Draft review, Completion,
  Validation & audit, Evidence sidecar viewer.**
- Component specs for the recurring pieces: status/evidence chips, the verdict card, evidence rows,
  the assistant panel.
- Empty, error, and loading state designs — each must reflect a real command's result, never a
  decorative placeholder.
- A short rationale tying the visual choices back to the trust model above — why the verdict
  dominates, why the assistant recedes, why blockers read as calm rather than alarming.

## Where to read more

This brief is self-contained, but the rest of the handoff package has the full depth behind every
rule above:

- [`README.md`](README.md) — package index and reading order.
- [`product-context.md`](product-context.md) — product, users, current state, glossary.
- [`user-workflows.md`](user-workflows.md) — full step-by-step flows, including future/error states.
- [`screens.md`](screens.md) — per-screen purpose, content, states, and "do not show" list.
- [`design-system.md`](design-system.md) — full visual/interaction direction and hard don'ts.
- [`ai-assistant-and-graphify.md`](ai-assistant-and-graphify.md) — assistant/Graphify behavior in
  depth.
- [`validation-audit-warning-model.md`](validation-audit-warning-model.md) — the three-signal model
  in depth, with copy guidance.
- [`data-governance-and-safety.md`](data-governance-and-safety.md) — full governance rules.
- [`technical-architecture.md`](technical-architecture.md) — a paper-design proposal for the backend
  this UI would eventually call (nothing implemented).
