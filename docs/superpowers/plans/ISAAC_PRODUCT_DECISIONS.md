# ISAAC Product Decision Register

**Canonical, multi-session.** One row per decision. Update this file in the same PR as any slice
that changes a row. Never restate a decision elsewhere — link to its ID.

**Created:** 2026-09-12 · **Last updated:** 2026-09-12 (**REVISION APPLIED** — implementation authorized)

> ## REVISION 2026-09-12 — IMPLEMENTATION AUTHORIZED
> Krish approved moving from planning into implementation. The planning gate is **CLEARED**.
> External-owner, security, migration and data-governance boundaries are **UNCHANGED**.
> Eight decisions moved from `PROPOSED`/`OPEN` to `CONFIRMED`; three were *narrowed*, and two were
> **reversed or hardened against my planning recommendation** — those two are marked `SUPERSEDES MY
> PROPOSAL` so a reader can see that the owner overrode the plan rather than ratifying it.
> Source: `2026-09-12-plan-review-and-revisions.md`.

**Status vocabulary:** `HARD CONSTRAINT` · `CONFIRMED CURRENT` · `USER PREFERENCE` · `PROPOSED` ·
`OPEN — NEEDS KRISH` · `OPEN — NEEDS EXTERNAL OWNER` · `SUPERSEDED` · `REJECTED` ·
`CONFLICTING EVIDENCE` · `UNKNOWN`

**Rule this register exists to enforce:** a decision recorded here is *evidence that the decision
was taken*, not evidence that it was correct or that it was delivered. Where the basis is an owner
instruction relayed in-session, the row says so, because this repository cannot witness a
conversation.

---

## A. Carried forward — hard constraints this scope change does NOT touch

| ID | Decision | Status | Basis / evidence |
|---|---|---|---|
| **D1** | One Run → exactly one ISAAC record | HARD CONSTRAINT | scalar conditions + per-record QC make multi-Run records scientifically wrong |
| **D2** | Inherit by reference; overrides explicit | HARD CONSTRAINT | avoids copied/stale shared values |
| **D3** | `submitted` is stored; other workflow status is derived | CONFIRMED CURRENT | `workflow.py::derive_workflow` |
| **D4** | Submit N records atomically | HARD CONSTRAINT | partial submission misrepresents completeness |
| **D5** | References + hashes, never file bytes, in the official record | HARD CONSTRAINT | schema models pointers; `assets[]` header states "NO BYTES, EVER" |
| **D7** | Runs / revisions as relational rows with JSONB documents | CONFIRMED architecture | avoids rewriting one Experiment blob per keystroke |
| **T1** | Deterministic validation is the truth plane; the Record Validator **stays** and is not weakened | HARD CONSTRAINT | `CLAUDE.md` §1–§3, §13; reaffirmed by the 2026-09-12 directive |
| **T2** | No model output in the truth path | HARD CONSTRAINT | `ai-integration-decision-packet.md` §6 |
| **T3** | No external agent performs final Submit | HARD CONSTRAINT / REJECTED alternative | scientist is final authority |
| **T4** | Client-supplied identity is never authoritative | HARD CONSTRAINT | `identity-trust-contract.md`; Dean 2026-08-12 |
| **T5** | Missing facts stay missing; ambiguity stays visibly uncertain until a scientist accepts | HARD CONSTRAINT | `CLAUDE.md` §5 |
| **T6** | Fail closed when identity or provider trust is absent; no fake `Connected` | HARD CONSTRAINT | §6/§9 of the AI packet |
| **T7** | Graphify is memory/query, never truth | CONFIRMED CURRENT (Graphify-as-truth REJECTED) | `CLAUDE.md` §7 |
| **T8** | Tutorial / worked-example sessions are never persisted as ordinary experiments | HARD CONSTRAINT | enforced in three places; observed intact this session |
| **R1** | `POST /ingestion/csv/preview` has **no apply route**, by decision | CONFIRMED CURRENT — **a committed human decision, NOT residual work** | `routes.py:11917`; re-verified 2026-09-12 |
| **R2** | Claude embedded inside ISAAC via MCP | **REJECTED as technically false** | MCP is client→server; ISAAC cannot call Claude over that connection |
| **R3** | A public/personal Claude Artifact as a production workaround | REJECTED | private Team artifact / deep link only, if approved |
| **R4** | Replacing the SLAC deployment with Railway/Vercel | REJECTED | personal deploys are legacy, pending Krish's retirement decision |
| **R5** | `Submit Anyway` | REJECTED | — |
| **R6** | MCP Submit / delete / migration / governance tools | REJECTED | — |
| **R7** | One continuously expanding record page | REJECTED / SUPERSEDED | 2026-09-03 UX direction; the four-workspace split implements the replacement |
| **R8** | Preserve existing developer-owned service identities (GitHub/Railway/Vercel) | HARD CONSTRAINT | `CLAUDE.md` §17 |

## B. New — taken by the 2026-09-12 scope directive

| ID | Decision | Status | Basis | Consequence |
|---|---|---|---|---|
| **DEC-01** | ISAAC narrows to two scientist jobs — capture new science, recover historical science — converging on one Experiment Library | **USER PREFERENCE / CONFIRMED by owner directive 2026-09-12** | owner instruction relayed in-session; **repository cannot witness it** | several working capabilities stop being first-class; none is deleted by that fact |
| **DEC-02** | The ISAAC website stays the canonical durable workspace; Claude is one interaction surface, not the product | **CONFIRMED by owner directive** | same | the settling test: a scientist must understand an Experiment from ISAAC alone six months later, without the Claude conversation |
| **DEC-03** | The Experiment Library becomes the website home and a core responsibility | **CONFIRMED by owner directive** | same | requires a list-payload extension before any screen work — see **DEC-07** |
| **DEC-04** | Evidence Graph is removed from **primary scientist navigation**; underlying provenance relationships are retained | **CONFIRMED 2026-09-12** | directive §40; my measurement: the Graph workspace is the most control-dense surface in the record screen (34 buttons, 145 text elements) | depth of removal is **DEC-11**; backend removal requires dependency analysis first |
| **DEC-05** | Final labels for top-level and Experiment-level navigation | **CONFIRMED 2026-09-12** — top level `Experiments / Historical Import / Settings`; Experiment `Overview / Runs / Capture / Review / Record` | my proposal: `Experiments` / `Historical Import` / `Settings`, and `Overview / Runs / Capture / Review / Record` | must be reconciled with the app's established language (prior direction used `Lab Records`, `Experiment Details`, `Capture & Proposals`, `Review Evidence`, `Review Export`) |
| **DEC-06** | Folder storage shape | **OPEN — engineering, resolved in the data-model workstream** | strong prior: **no new table** (a feature needing a migration does not work until an operator acts — a hard stop no agent can lift) | if a new table is required, it needs a new committed `CLAUDE.md` §15 sentence **plus** an owner-approved packet **plus** an operator action |
| **DEC-07** | Extend `GET /api/experiments` before redesigning the Library screen | **CONFIRMED 2026-09-12** — with the added constraint: **do not invent `Last Updated` if the backend cannot provide it**; server counts are totals, never client array lengths | measured: the payload carries no run count, no technique/beamline, and **no `updated_utc`** — so "sort by Last Updated" is not implementable today | this is the first implementation slice; the screen cannot be honest without it |
| **DEC-08** | `Review` becomes its own Experiment workspace, consolidating proposals, ambiguities, conflicts, unmapped notes, missing info and export readiness | **PROPOSED** | those six live in four different places today | the largest single IA simplification available; prerequisite for one review experience across all ingestion sources |
| **DEC-09** | Whether a cross-Experiment "Needs Review" queue is first-class navigation | **CONFIRMED 2026-09-12 — it is NOT.** `Needs Review` and `Recent` are **Library views/filters**, not top-level destinations | promoting a lens to a peer destination is what produced the current 21-destination census | recommendation: start as a filter chip on `Experiments`, promote only on evidence of use |
| **DEC-10** | Native ISAAC microphone capture is **retained** and polished, with its role stated | **CONFIRMED 2026-09-12** | four PRs of recent work; an orphaned-microphone defect was found and fixed; playback shipped | role: manual recording + typed/pasted transcript + fallback + foundation for a future approved provider. **Automatic transcription must never be implied** — every provider answers `501` and `audio_ref` is an integer no provider can dereference |
| **DEC-11** | Depth of Evidence Graph removal | **CONFIRMED 2026-09-12, ORDERED:** (1) add provenance parity outside the Graph; (2) prove `derived_from`/source relationships stay discoverable; (3) remove from primary navigation; (4) **if the dependency recheck is still clean, delete the unused frontend visualization/lib/CSS/tests**; (5) preserve backend/source provenance structures; (6) old `?view=graph` deep links degrade safely | dependency analysis pending | deletion is not a substitute for understanding |
| **DEC-12** | Historical Import raw-source retention model | **CONFIRMED 2026-09-12: Option A (reference-first) now; Option C (ephemeral parse) for parser development; Option B deferred; Option D ruled out for real data** | Option A costs zero new code and reuses the shipped `assets[]` pointer-only feature; Option C mirrors the already-approved "one short-lived read, sanitized output only" pattern; Option B needs infra approval and there is no corpus to justify it; **Option D — a live model reading real scientific files — is exactly what Dean's D1–D9 deferral withholds** | revisit if the corpus arrives with a reproducibility requirement Option A cannot meet |
| **DEC-13** | BL15-2 as the first Historical Import pilot | **THE PILOT DECISION IS CLOSED — CONFIRMED 2026-09-12.** What remains blocked is the **corpus and expert ground truth only** (`EXT-10`), which is a data availability problem, not a product question. Build the shell, source model, provenance, Review integration, parser *interfaces* and synthetic harness **now**; format-specific parser behaviour waits for representative data | **measured 2026-09-12: this repository contains no historical BL15-2 material at all** — zero `.mac`, zero `.xlsx`/`.xls`; everything beamline-shaped in `examples/` is generated by `scripts/make_synthetic_examples.py` with fictional people and a fictional year-2099 session; `openpyxl` is not a dependency | **no `.mac` parser may be designed before a representative file exists.** §5 forbids designing against assumptions. The first Pillar 2 deliverable is a data request |
| **DEC-14** | Capture is a sidebar destination, **not** a workflow step | **CONFIRMED (carried forward)** | no derivable criterion for "capture is finished"; `notes >= 1` would invent one and nag records that need none; `workflow.py:128-149` already argued this for submission | no tick, no lock, no ordering, no `aria-current="step"` |
| **DEC-15** | The ambiguity / candidate model is **unified** across live voice, historical import, assistant output and CSV ingestion | **CONFIRMED 2026-09-12** | they are one problem: multiple sources offer candidate information not yet accepted as truth | the alternative — four ambiguity systems — is the outcome to design against. A justified reason not to unify must be named, not assumed |
| **DEC-16** | Ambiguity is an **assistant-side (draft/sidecar) construct**; a single value must be chosen before export unless the official schema natively represents uncertainty at that path | **CONFIRMED 2026-09-12 — and the verification landed:** the schema's ONLY uncertainty path is `$.descriptors.outputs[].descriptors[].uncertainty`, which is descriptor-only, so `context.temperature_K` has no such sibling. **Never encode "425 maybe 430" as a continuous range to fit the schema** | §5 forbids inventing range semantics | if the schema has no native representation, the candidate set never reaches an official record — and that is correct, not a limitation |
| **DEC-17** | Orchestrator model for this programme | **CONFIRMED + NARROWED 2026-09-12: Fable 5.1 is PRIMARY.** Opus 5 is a **disclosed fallback only when Fable is unavailable and the substitution is approved** — it must be recorded in the ledger session header, orchestrator-only discipline preserved, and **no other model may be silently substituted** | owner selected "proceed on Opus 5" when told this session is `claude-opus-5[1m]` and not Fable 5.1 | `CLAUDE.md` §10 already ratifies an Opus orchestrator as the standing fallback; orchestrator-only discipline retained |
| **DEC-18** | Sub-agent ceiling for this programme | **CONFIRMED + SHARPENED 2026-09-12: five TOTAL subordinate agents per top-level session** — not five per sub-agent, not five plus nested, not five implementers plus extra reviewers. **Nested spawning is forbidden.** Reviewers count. **Do not immediately spend all five — reserve review capacity.** If the programme needs more, checkpoint in the ledger and resume in a new top-level session with a fresh ceiling of five | owner: "spawn only 5 subagents don't let them spend 5 more" | **five total, not five concurrent**; nested spawning forbidden and the constraint was relayed to every running agent. Reviewer agents count. Consequence already paid: Impeccable's `critique` ran single-context and is bannered `⚠️ DEGRADED` |

## B2. Decisions added or hardened by the 2026-09-12 revision

Five of these did not exist in the planning package. **Two of them override what I recommended**,
and they are marked so a reader can see the owner corrected the plan rather than ratifying it.

| ID | Decision | Status | Basis / consequence |
|---|---|---|---|
| **DEC-19** | **Project Memory and Statistics are demoted out of primary scientist navigation.** Project Memory moves under `Settings → Advanced/Developer`; useful `My Stats` information may merge into the Library; `General ISAAC` information moves to Settings. | **CONFIRMED 2026-09-12** | I *raised* Project Memory as a question (`UX-015`) because the original directive did not name it. The owner answered it. **Capability and tests are PRESERVED** — demotion is a navigation decision; deletion would be a separate one. Measured stake: ~7,800 lines and **578 test cases**, the largest single test mass in the app, for a graph of this repository's own source code. |
| **DEC-20** | **Folders v1 is a migration-free VIRTUAL NESTED PATH-LABEL model on Experiment application state** — not a Drive-style container model. A path **materializes when at least one Experiment is assigned to it**. | **CONFIRMED + NARROWED 2026-09-12** | v1 **must** support: assign/create a folder path while creating, moving or importing · nested paths · breadcrumbs · browse · cross-folder search · clear/move. v1 **must not pretend** to have: durable empty folder entities · folder ACLs · sharing · folder ownership · **atomic folder rename**. Those need a separate persistence/identity decision *if later shown necessary*. **This supersedes my "ship create/move/delete, defer rename" framing** — the honest v1 has no durable folder entity to delete. Invariant unchanged: folder state must never reach an exported record or sidecar, and must not alter scientific metadata, record identity, Run values, validation result, or `content_signature`. |
| **DEC-21** | **A submitted snapshot is IMMUTABLE. The Experiment workspace may accumulate "Current Working Changes" after submission and later create the next immutable snapshot.** | **CONFIRMED + CORRECTED 2026-09-12** | **SUPERSEDES MY PROPOSAL.** I recommended reinterpreting the operation as *"keep editing, then submit again"* — which is mechanically what happens, but describing it that way **understates the modelling requirement**. The UI must explicitly distinguish **`Last Submitted Revision`** from **`Current Working Changes`** and expose revision history. **Never describe the historical submitted revision as mutable.** Tasks: `REV-001`, `REV-002`. The rename trap must be surfaced, not hidden: a rename does **not** move `content_signature`, so submit → rename → resubmit yields `409 already_submitted`. |
| **DEC-22** | **Claude/LLM semantic reconstruction over REAL historical scientific files is BLOCKED pending institutional data/provider/egress approval — not rejected.** | **CONFIRMED 2026-09-12** | Build the provider-neutral seam and the synthetic/authorized test path **now** (`HIST-003a`, unblocked). Activate for real data only after approval (`HIST-003b`, blocked). **Do NOT use personal Claude uploads or a personal self-service connector as a governance workaround for real SLAC data.** This is a narrowing of my Option-D "ruled out" language: ruled out *for now*, by governance, with the seam built. |
| **DEC-23** | **Authless remote MCP is REJECTED for production ISAAC scientific data**, even though Anthropic documents it as supported. | **CONFIRMED 2026-09-12** | **SUPERSEDES MY PROPOSAL.** I surfaced vendor-permitted authless MCP as *"a stronger, cheaper argument to put to Dean"* (`MCP-009`). The owner rejected that framing: **trusted attribution is load-bearing**, so vendor permission is not a reason to drop it. Authless mode may be used **only for explicitly approved local/synthetic/non-sensitive smoke testing** — never as a governance shortcut. `MCP-009` is therefore **REJECTED as a production route** and survives only as the local-smoke-test caveat. |
| **DEC-24** | **"Zero migrations" is a migration-free TARGET, not a promise.** | **CONFIRMED + SOFTENED 2026-09-12** | My plan asserted zero migrations across all 31 PRs "by design rather than luck". That stands as an intent, but must not become pressure to force a requirement into an unsuitable existing structure. If fresh implementation evidence proves a safe requirement cannot be represented in existing approved state: **stop that slice**, document the evidence, add the required committed authorization sentence, prepare forward/rollback/test evidence and an operator packet, **do not apply it yourself**, and continue unrelated unblocked work. Never rewrite an applied migration. |

## B3. Decisions taken by the 2026-09-15 owner direction

**Eleven decisions, and TWO OF THEM REVERSE A DECISION IN THE TABLE ABOVE.** They are recorded as
reversals rather than folded in silently, because `DEC-19` and `DEC-05` are exactly the kind of
committed row a future session builds against.

**PROVENANCE, stated because a repository cannot witness a conversation.** Every row here reaches
the repository as an **owner instruction relayed in-session**, the same evidentiary class as
`DEC-01`…`DEC-24`. No transcript, packet or evidence file backs it, and authorship witnesses
nothing — every commit here is authored by the project owner with Claude co-authored, so a commit
author cannot distinguish a granted direction from an assumed one. What a reader CAN check
mechanically is the boundary: each row is dated, names what it does and does not cover, and
carries the measurement it rests on where one exists. **Only Krish can confirm the instruction was
given.**

| ID | Decision | Status | Basis | Consequence |
|---|---|---|---|---|
| **DEC-25** | **Statistics RETURNS to the primary scientist sidebar.** | **CONFIRMED 2026-09-15 — REVERSES the Statistics half of `DEC-19`** | owner instruction: *"Return Statistics to the primary sidebar … This is a newer product-owner decision and supersedes the earlier plan to demote it completely."* | **`UX-017`'s measurement is NOT retracted — it becomes the acceptance bar.** It measured the SCREEN (3,820 px, 422 visible text elements) and concluded the slot was unearned; that was an answer about a screen, and the slot is a question about a destination. So the promotion carries an obligation, written into `LeftNav.tsx` beside the item: **Statistics earns the slot only once the page is scientist-first.** Shipped in `d7780b53`; the redesign is a separate slice. |
| **DEC-26** | **Project Memory STAYS OUT of primary scientist navigation.** | **RE-AFFIRMED 2026-09-15** | owner: *"Do NOT return Project Memory to the primary scientist sidebar"* — it is source-code/Graphify/developer memory tooling, not a scientist's day-to-day job | The other half of `DEC-19` is untouched. Capability and its ~578 test cases are preserved; this remains a navigation decision and not a deletion one. `statistics-nav.test.tsx` now pins the ASYMMETRY — one of the two 2026-09-13 demotions is reversed and the other is not — so a future session cannot "tidy up" by treating them alike. |
| **DEC-27** | **Governance & Safety is demoted out of primary navigation, to Settings.** | **CONFIRMED 2026-09-15** | owner: *"evaluate moving it under Settings rather than keeping it as another primary scientist destination … The desired top-level navigation should remain extremely small."* | **This is decided by the same reasoning that previously KEPT it.** The prior ground was that the authorizing direction enumerated it in neither list, so removal would be "a product decision nobody took"; the new direction takes it. **No capability moves** — the route is unchanged, `?tab=validator` and `?tab=schema` deep links still resolve, and Data & Privacy already carried a reciprocal link, which is §19's "provide the capability elsewhere FIRST" and now has its own assertion. |
| **DEC-28** | **`Settings & API` -> `Settings`**, and Settings reorganises toward `Overview / Privacy & Governance / Integrations / Advanced`. | **CONFIRMED 2026-09-15** (rename shipped in `d7780b53`; the regroup is a slice) | owner: the area *"remains too cluttered"*; developer-heavy material goes to Advanced | The `& API` named the page's CONTENTS in the DESTINATION's label — and those contents are what is being reorganised. **The route and every `?tab=` deep link are deliberately NOT moved**; the rename and the route are asserted separately so a later tidy-up that renames the route fails a test instead of breaking a bookmark. That guard has now caught two renames. **A nested tablist is banned** by `settings-page.test.tsx`, so the regroup uses sections, not tabs-in-tabs. |
| **DEC-29** | **The Runs split-screen is APPROVED and retained; the right pane becomes a READABLE RECORD MAP.** | **CONFIRMED 2026-09-15** | owner: *"I like that split-screen architecture … but it's not really readable. I can't clearly distinguish what fields are done, what fields aren't done, what my values were for those fields"* | The architecture is ratified; only the pane's content is at issue. Required states — Filled / Missing / Needs Review / Invalid / Inherited / Not Applicable — **icon or shape plus text, never colour alone**, with the current value shown where one is honestly held. **`Not Shown Here` is retained and is not a defect**: `run.fields` carries only the five `RUN_FIELDS`, so the QC verdict, series and descriptors answered through Complete Metadata are genuinely not visible to this payload, and claiming "nothing yet" about them would be this product's signature defect. |
| **DEC-30** | **A validation blocker must name its field and offer the fix; `Check Failed` alone is not acceptable.** | **CONFIRMED 2026-09-15** | owner: *"I don't even know what it's asking … you should point to the specific field … and there could be a button right next to it that points to the agent, and then the agent will have the context"* | Each finding gets a subject, a state word, the server's own sentence **verbatim**, and a `Go to field` **only where a real destination exists** — a non-action must not look clickable. `FindingList` is the ONE shared renderer (Runs and Validate & Review), so both surfaces move together. **`kind` is optional on the wire and must be read as such**: absent, the row says nothing about its subject rather than inferring one from the message text. |
| **DEC-31** | **Contextual `Ask ISAAC` becomes a general pattern beside blockers and fields.** | **CONFIRMED 2026-09-15** | owner: *"if they want more information, then they can ask the agent … and then he'll tell you, okay, this, this, this needs to be done"* | It carries only safe structured context — experiment id, run id, field path, validation code, current value, message. It is **advisory**: it may not validate, accept, submit, fill a field, or decide scientific truth. **There is no LLM in any deployment** (`/api/assistant/ask` is a bounded deterministic resolver; every provider answers `501`), so an unanswerable question must refuse honestly — a fabricated explanation is forbidden, and `ASSISTANT_NO_MODEL_CLAIM` stays on the panel. |
| **DEC-32** | **The browser tab must carry the ISAAC mark, reusing the EXISTING logo.** | **CONFIRMED 2026-09-15** | owner: *"Nerve already has a recognizable browser-tab icon. ISAAC should too … Reuse the existing ISAAC logo already displayed in the upper-left application header. Do not design a new brand/logo."* | The mark is measured, not chosen: `TopBar.tsx`'s `Brand()` renders the lucide `AudioWaveform` glyph, white, on a 30×30 `border-radius: 8px` tile filled `var(--action)`. **The deployment base path `/krish/` is the trap** — a root-relative icon href 404s there, so the build must be inspected rather than assumed. |
| **DEC-33** | **Historical Import gets a familiar file-selection UI**; real file-byte ingestion may be implemented **application-side** but stays **disabled by default** until governance enables it. | **CONFIRMED 2026-09-15 — this is a NEW authorization** | owner: the reference-only Source experience *"is insufficient as the ordinary scientist workflow"* | **The existing guards are RECONCILED, not deleted.** `POST /api/uploads` is an unconditional 403 and `upload-claim-parity.test.tsx` pins that claim **and its polarity**. The honest shape is a capability-driven path: size- and type-bounded, traversal-safe, separate from official record bytes, discoverable through capability state, **disabled in governed production** — and where browser-only local staging is honest, files may be listed as `Local only — not sent to ISAAC` **without transmitting a byte**. A button that merely fails after being clicked is forbidden. `Record a reference` survives as the secondary path. |
| **DEC-34** | **Proposal creation must be discoverable.** | **CONFIRMED 2026-09-15 — and the owner's premise was measured and found FALSE, in the product's favour** | owner: *"there's no way to actually add an ingestion proposal. I understand maybe it's not hooked up to the backend, maybe it's blocked"* | **It is NOT blocked.** Measured at `dbf9d121`: `POST /api/experiments/{id}/proposals` is registered and documented (`routes.py`, `post_proposal`), requiring `note_id`, `target_field_path`, `proposed_value`, `rule`, conditional `run_id` and the record's `If-Match`. **So this was a UI gap, not a capability gap**, and the correct outcome is a real form — not a disabled placeholder. **Creation and ACCEPTANCE must never be conflated:** acceptance answers `409 human_actor_required` in every default deployment because no trusted authentication boundary exists (`EXT-01`), which is a configuration fact no application change can close. |
| **DEC-35** | **Visible prose is reduced product-wide; long explanation moves behind accessible disclosure.** And **Impeccable is required for every significant UI redesign.** | **CONFIRMED 2026-09-15** | owner: *"the text is still stopping midway through half the block"* — the earlier `38em -> 68ch` change did NOT close it | Defaults: one sentence of page introduction, one line of card description. **Never disclose-away a blocking error, a scientific uncertainty, a destructive consequence, a security/privacy state, or a required action** — those stay visible. Disclosures must be keyboard- and screen-reader-accessible, **never hover-only**. The dead-whitespace defect is **per-composition**, not one global CSS constant — a prior instance in this repository was a `max-width` media query fixing the wrong box entirely. **Impeccable's mechanical detector is non-functional here** (missing parsers AND `.tsx` routed to a regex engine with no accessibility ruleset), so a `0 findings` from it is a non-answer unless a negative control says otherwise; its in-browser overlay is a different code path and does work. |

### `DEC-33` in detail — what it actually reverses, found 2026-09-15

**`DEC-33` is not a green field. It REVERSES A RECORDED, REASONED DECLINE, and a future session
must be able to see that rather than discover it the way I did.**

`screens/HistoricalImport.tsx` (~line 640) carries a comment stating that a previous session
**built a multi-file picker and reverted it**. Its argument, quoted because it is a good one:

> *"A `Choose Files…` button is an upload affordance whatever it does underneath — a scientist who
> picked twelve files would reasonably believe twelve files had been uploaded. Recording their
> names while they believe that is worse than asking them to type, because it is a false
> impression the product created on purpose."*

Two committed guards enforce it:

* `historical-import.test.tsx` §1 — the screen renders **no** `input[type="file"]`, declares no
  `type="file"` in its source, and has no `onDrop`, `FormData` or `multipart`. Its stated subject:
  *"the destination cannot accept bytes and does not say it can"*.
* `upload-claim-parity.test.tsx` — **exactly two** non-test files under `apps/web/src` declare a
  file input, both named, so a third anywhere fails whatever it does.

**THE DECLINE WAS RIGHT ON ITS OWN TERMS AND THE OWNER HAS ANSWERED ITS OBJECTION DIRECTLY.** The
objection was a false impression; the instruction supplies the mitigation — staged files must read
`Local only — not sent to ISAAC` — and says explicitly: *"Do not merely delete the guards.
Reconcile them."* So the decline is superseded, not refuted, and is left standing in the source
beside its reversal.

**THE MECHANISM IS MEASURED AND NEEDS NO BACKEND CHANGE, NO NEW CAPABILITY AND NO GOVERNANCE
CHANGE** — which is what makes the reconciliation honest rather than a loosening. `POST
/api/imports/{id}/sources` already accepts `kind: "reference"` with `filename`, `reference`,
`media_type`, `size_bytes` and `sha256`, stores them verbatim, **fetches nothing**, and records the
entry as `parse_state: "no_content_path"`. A browser file picker supplies exactly those from the
chosen `File` — `name`, `type`, `size` — **without reading or transmitting a byte**. Proved over
HTTP against a local backend on 2026-09-15: the entry lands with the real filename, real size, a
genuine SHA-256, and `parse_state: "no_content_path"`.

**ONE PRECISION THAT MUST NOT DRIFT.** The route's own description says `sha256` *"is checked for
SHAPE only … and is **never computed**"*, and that **no surface may describe it as verified,
checked or matched**. A browser-computed digest does not change that: it is computed by the
CLIENT, over bytes the server never sees, and remains the caller's claim. It may be labelled as
computed in the reader's browser; it may **never** be labelled verified by ISAAC.

**THE GUARD RECONCILIATION, stated before it is written so it cannot be quietly weakened:** §1
inverts from *"the affordance cannot exist"* to *"the affordance exists **and** no bytes are ever
transmitted **and** every staged row carries the not-sent disclosure"*. That is a **stronger**
claim than the one it replaces — the old guard banned the affordance, the new one bans the actual
harm. `upload-claim-parity`'s file-input census goes two → three, with the third named and its
disclosure pinned. **Neither guard may be deleted, and neither may be weakened without the
replacement truth assertion landing in the same change.**

### `DEC-17` — the orchestrator fallback, disclosed for this session

`DEC-17` requires that an Opus orchestrator be **recorded in the ledger session header** rather
than silently substituted. Recorded here too: the 2026-09-15 session ran on **Opus 5
(`claude-opus-5[1m]`)**, not Fable 5.1, under `CLAUDE.md` §10's ratified standing fallback, with
orchestrator-only discipline preserved. `DEC-18`'s ceiling of **five subordinate agents total**
was applied: four implementation lanes and one reserved for independent review.

## C. Open — external owners

These are not ours to decide. Full detail in
[`2026-09-12-isaac-blockers-and-risks.md`](2026-09-12-isaac-blockers-and-risks.md).

| ID | Question | Owner | Status |
|---|---|---|---|
| **EXT-01** | Trusted authentication boundary (the Service is a plain ClusterIP with no NetworkPolicy; forwarded identity headers are forgeable in-cluster) | Dean / SLAC infra | **OPEN** — reconfirmed 2026-08-12. Hosted `submission.blockers` reads exactly `["no_attributable_actor"]` |
| **EXT-02** | Remote MCP reachability and OAuth in production | Dean / SLAC infra | **OPEN** — `GET /krish/api/mcp` returned **404** on 2026-09-12 while `docs/` cites that URL as live |
| **EXT-03** | Registering an organization-wide remote MCP connector | **Claude organization Owner / Primary Owner — identity UNKNOWN; do not assume this is Dean** | **OPEN.** Note `DEC-23`: a self-service personal connector is **not** an acceptable substitute for real SLAC data |
| **EXT-04** | D1–D9: model provider, credential, billing, egress, retention, data policy, transcription provider | Dean — **DEFERRED 2026-08-12**: *"leave AI integration as future work rather than increasing scope at this point"* | **DEFERRED.** Implementation against deterministic fakes is separately owner-authorized; a production provider is not |
| **EXT-05** | Is scientific speech/data approved to flow through the organization's Claude environment? | institution / Dean | **OPEN — and new.** Created by the Claude-Voice architecture. Distinct from EXT-04: Claude-mediated capture may need no ISAAC-owned ASR, but it does need this answer |
| **EXT-06** | **G2** — hosted per-record display | Dean | **CLOSED BY DEFAULT.** Hosted `record_display: "closed"`, observed 2026-09-12 |
| **EXT-07** | **G3** — the five withheld aggregates | Dean | **OPEN** — withheld pending his answer |
| **EXT-08** | Migration `0005` approval, application, backfill, Stage-2b cutover | Krish (approval) + operator (application) | **OPEN.** Observed 2026-09-12: hosted `run_projection.last_pass.unavailable: 3` — all three hosted experiments have an unreadable run projection |
| **EXT-09** | Six `system.configuration.*` classifications | Angel / domain owner | **OPEN** — blocks nothing else; two question packets prepared |
| **EXT-10** | Representative BL15-2 corpus + expert ground truth | Krish + Angel | **OPEN — gates Pillar 2.** See **DEC-13** |
| **EXT-11** | Authenticated hosted QA, true 200% zoom, real-microphone check, hosted narrow widths | Krish | **OPEN.** *Partially advanced 2026-09-12*: rollout verified (hosted `commit` = `2f9a1133`), and that is the **rollout**, not the QA. No CDP method can drive true zoom; `resize_window` does not move the rendered viewport |
| **EXT-12** | Personal deployment retirement (Vercel + Railway) | Krish | **OPEN** — both still live and public; Railway has a persistent volume, so deleting destroys what pausing preserves |

### DEC-36 — Settings is grouped, not collapsed: "Advanced" is a label on a flat tablist
*(2026-09-15, in response to the owner's "Settings simplified with developer material under
Advanced")*

**Decided.** The seven Settings tabs are reordered into two groups — the four scientist-facing
tabs, then API Access, Endpoint Explorer and Connect Your Agent behind a neutral divider and the
word ADVANCED. All seven remain `role="tab"` children of ONE tablist, keep their own deep links,
and keep their accessible names unchanged; the group reaches assistive technology as an
`aria-describedby` **description**.

**Rejected, on measured grounds rather than taste:** collapsing the three developer tabs into a
single "Advanced" tab holding three disclosures. `ApiDocs` alone renders two `search` landmarks,
`a11y-landmarks-headings-and-tabs.test.tsx` already pins that exactly one region is named
"Endpoint Explorer", and `querySelectorAll` reaches inside a closed `<details>` — so stacking the
three collides those landmarks whether or not they are visibly collapsed. It would also relocate
the a11y baseline cells of two separately-keyed scanned surfaces (`settings-api`,
`settings-explorer`), and `settings-explorer`'s count already tracks the live OpenAPI document's
own growth.

**Reopenable.** If the grouping is not enough, the collapse is a decision to take deliberately,
with the landmark collision solved first. The reasoning is recorded at `SETTINGS_TABS` in
`apps/web/src/screens/SettingsPage.tsx` so it is not rediscovered.

**Withdrawn en route, and recorded because the mistake generalises:** the group was first added as
an `aria-label` suffix ("API Access — Advanced"), by analogy with the mode chip, whose accessible
name opens with its visible text and then adds its claims. **A tab's name is its handle** —
`getByRole('tab', { name })` matches exactly — and 98 assertions across three suites broke at once.
A description is announced after the name and changes no handle.

---

### DEC-37 — Adding a whole import is ONE server operation, and it applies nothing
*(2026-09-15, `HIST-005`)*

**Decided.** `POST /api/imports/{import_id}/add-to-experiment` sends every proposable candidate of
one import to review on one record, as OPEN proposals with their notes, inside one `record_lock`
and one save. The record holds the whole batch or none of it. **No value is written** — the fields
of the record and of every run are byte-identical afterwards, which is asserted rather than
claimed.

**Rejected:** a client-side loop over the existing per-candidate operation. It needs no backend
change and is retry-safe, and it was still wrong for the reason
`routes._mint_transcript_proposals` had already written down for the transcript case: N requests,
each with its own `If-Match`, means a closed tab or a `412` partway through leaves a record holding
part of an import with **no surface able to say which part**. The scientist's act is one act.

**Decided — partial success is split by whether the caller can fix it.** A candidate that is
intrinsically unproposable (sources disagree, structural, no write path in this build) is reported
with the server's own reason and skipped; the review screen already shows that reason, so nothing
is a surprise. A candidate that needs a run when none was named refuses the **whole batch**, because
sending only the rest would silently leave the run's values behind.

**Decided — `run_id` behaves differently here than on the per-candidate operation, deliberately.**
There, a run given for a record-scoped target is refused, because the caller named one candidate.
Here one run is given for a whole import and applied only to the candidates a run owns, because a
record-scoped candidate in the same batch is not a mistake. The difference is stated on the
operation, in the API client, and on the screen.

**Consequence, stated rather than left to be found:** `historical_import.UNBUILT_STEP` is now
`None`. The constant and the `session_view` mechanism are KEPT, so a future unbuilt step declares
itself in the same list the surface renders from and cannot be shown as available by omission.
`furthest_step` can now reach `add_to_experiments`, on the strict criterion that every proposable
candidate has been sent — and it drops back to `review` when a re-reconstruction mints new ones.

