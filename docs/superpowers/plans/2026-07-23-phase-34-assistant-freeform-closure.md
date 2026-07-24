# Phase 34 — Free-Form Deterministic Assistant Q&A · Closure

**Status:** CLOSED 2026-07-23 — code HEAD `d69d0ed`.
**Owner:** orchestrator (Opus 4.8, ratified fallback for Fable 5).
**Created:** 2026-07-23.

Goal: let the Assistant answer flexibly-phrased natural-language questions about the current record,
and record-agnostically about Project Memory, **without adding an LLM** — a bounded, deterministic
intent-classify-then-answer resolver, honest refusal for anything outside that catalog, read-only end
to end. This closes the deferral recorded at Phase 33 closure ("real free-form assistant Q&A —
separate approval-gated backend phase").

---

## 1. Decision #13 — documentation language (binding)

The closure narrative, the ledger entry, and `CLAUDE.md` §11/§15 all use this framing. It is not
optional wording — it is the accuracy boundary for what shipped:

- Phase 34 does **not** add an LLM; no model provider, secret, AI dependency, or outbound model
  request exists anywhere in the shipped code.
- "Free-form" means flexible natural-language **phrasing** over a **bounded, deterministic intent
  catalog** — **not** a general-purpose chatbot and **not** open-world answering.
- Unsupported and ambiguous questions are refused honestly; unknown scientific/open-world facts are
  never guessed.
- Project Memory answers are **advisory and cited** (leads to verify) — never treated as
  record/experiment truth or a verdict.
- Q&A is **READ-ONLY** and cannot mutate records/revision/workflow/evidence/validation/export/
  memory/files.
- Conversations are **ephemeral** (browser session), cleared on Reset Demo — no server-side
  persistence, no Project-Memory indexing of conversation text, no prompt/answer text in logs.
- **Tier 2** (a real LLM provider) remains an **unapproved, deferred future product decision** — it is
  not described anywhere as committed work.

---

## 2. What shipped

### Backend
- `apps/api/isaac_api/assistant_query.py` — pure, stdlib-only, deterministic intent resolver
  (classify → answer). Covers 8 record intents plus a `memory_lead` intent; honest refusal path for
  unsupported/ambiguous/open-world questions.
- Two READ-ONLY routes in `apps/api/isaac_api/routes.py`:
  - `POST /api/experiments/{id}/assistant/query` — record-scoped.
  - `POST /api/assistant/memory/query` — record-agnostic, used by Project Memory.
- Verdict-guard and path/secret scrubbing applied to every answer **and** every cited source label;
  answers are revision-stamped; errors are typed; the resolver never mutates state.

### Frontend
- The composer (`apps/web/src/components/AssistantPanel.tsx` / `apps/web/src/lib/assistant.ts`) is
  wired to the two endpoints.
- The on-mount auto-reply ("N fields still need you") was **removed** — the rail now rests on its
  honest empty state instead of firing an unsolicited summary.
- Conversation is ephemeral and bounded: reuses the existing P29 session, `MAX_MESSAGES=40`, cleared
  on Reset Demo; a Clear Conversation control was added.
- Answers carry provenance chips + cited-lead chips with client-route source navigation; a compact
  live-answer staleness indicator plus an explicit Ask Again action (no silent auto-regeneration).
- Follow-up support; accessibility (single polite live region, focus management, accessible names);
  responsive behavior (narrow width, 200% zoom, long-content wrapping); honest degradation (explicit
  "unavailable" state, defensive timeout — never a silent hang or a fabricated answer).
- **One `AssistantPanel`** is used across all 5 surfaces (Record Workbench, Guided Completion,
  Evidence Explorer, Export Readiness, Project Memory — the My Experiments dashboard does not mount it).
  Suggested Questions remain
  precomposed and share the same answer pipeline. Agent Actions and the single write path
  (`confirmProposal`) are unchanged and stay fully separate from the read-only Q&A path.

---

## 3. Slice ledger (6 commits, all CI green)

| Slice | Commit | Outcome |
|---|---|---|
| P34.1 | `15fb8ec` | Read-only deterministic assistant query resolver + endpoint |
| P34.2 | `ccd786a` | Wire composer to the read-only resolver; remove auto-reply; bounded history + Clear Conversation |
| P34.3 | `8f7c12f` | Answer provenance, source navigation, live-answer staleness + Ask Again |
| P34.4 | `a9339f2` | Cross-surface consistency — record-agnostic Project-Memory query |
| P34.5 | `2481858` | Assistant a11y, responsive & degradation hardening |
| P34.5(2) | `d69d0ed` | Close independent-review findings D1 (verdict-guard on source labels) + R2 (suppress misleading provenance on refusals) |

Final HEAD: `d69d0ed`.

---

## 4. Authority / read-only contract (what independent review checked)

The independent Opus review evaluated the full `15fb8ec..d69d0ed` range against:

- **Authority / read-only:** the resolver and both routes never write; the confirmed-write surface
  (`confirmProposal`) is untouched and stays the only mutation path.
- **No-LLM / no-infra:** no model provider, API key, secret, or outbound network call anywhere in the
  new code; the resolver is pure Python stdlib.
- **No-guessing:** unsupported/ambiguous/open-world questions are refused, not answered speculatively.
- **Determinism:** same input → same classification → same answer; no randomness, no hidden state.
- **Privacy:** verdict-guard + path/secret scrubbing applied to answer text and source labels.
- **Staleness:** live answers carry an honest staleness indicator; nothing auto-regenerates silently.
- **No-regression:** existing Agent Actions / Suggested Questions / confirmed-write flows unchanged.
- **Synthetic-only:** no real/private data path introduced.

**Result:** PASSED, with two findings fixed in `d69d0ed`:

- **D1** — the verdict-guard scrub was applied to answer text but not to cited *source labels*;
  extended to cover both.
- **R2** — a refusal answer could still carry a (misleading) provenance/staleness stamp; refusals now
  suppress provenance display entirely.

---

## 5. Verification at close

- Backend: `.venv/bin/pytest -q` → **964 passed**.
- Frontend: `npm test` → **672 passed** (55 files).
- `npm run build` → clean.
- Committed-snapshot gate → green.
- CI green on every one of the 6 pushes.
- Railway: `synthetic-only` @ HEAD. Vercel: deployed.

## 6. Hosted synthetic QA (live, PASS)

- Empty-state rail: no auto pending-summary card on load.
- Free-form deterministic answers rendered for in-catalog record questions.
- An open-world scientific question was refused — no guess offered.
- Read-only confirmed by network inspection: only `/assistant/query` was hit during the session; no
  `/answers`, `/edit`, or `/export` calls fired from Q&A interaction.
- Provenance labels + cited-lead chips render and navigate correctly.
- Clear Conversation works.
- The memory-scoped composer on Project Memory answers correctly (record-agnostic path).
- Console clean; no telemetry observed.

---

## 7. Open items (honestly carried, not overstated)

- **Human VISUAL sign-off (narrow-viewport 1280/1024/768/375 + 200% zoom)** remains a human decision.
  Phase 34 added the responsive CSS and accessibility work, and automated/desktop QA passed, but the
  human visual gate is Krish's to give — this parallels the still-open Phase 33 human visual gate
  (see `docs/superpowers/plans/2026-07-23-phase-33-ui-refinement.md` §11 and the master ledger's
  Phase 33 HQA section).
- **Tier 2 (a real LLM provider)** remains unapproved and deferred. Nothing shipped in Phase 34
  schedules or implies it; it is a separate, future, explicitly-approval-gated product decision.

---

**Phase 34 = COMPLETE at `d69d0ed`.** No new phase started; the next phase requires explicit user
approval.
