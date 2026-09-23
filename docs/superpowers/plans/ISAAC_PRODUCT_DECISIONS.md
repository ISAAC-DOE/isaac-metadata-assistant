# ISAAC Product Decision Register

**Canonical, multi-session.** One row per decision. Update this file in the same PR as any slice
that changes a row. Never restate a decision elsewhere — link to its ID.

**Created:** 2026-09-12 · **Last updated:** 2026-09-23 (§B7 added — hosted-QA redesign and Angel's 2026-09-22 answers)

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

## B4. Decisions taken by the 2026-09-17 owner direction — the metadata-hierarchy policy

**Ten decisions. Nine are new; `DEC-46` narrows a claim this repository has been making wrongly.**

**PROVENANCE, same class as `B3` and stated for the same reason.** Every row reaches the
repository as an **owner instruction relayed in-session** — for `DEC-47`, an owner relay of a
**domain owner's** (Angel's) confirmation. No transcript, packet or evidence file backs any of
it, and authorship witnesses nothing. What a reader can check mechanically is the boundary:
each row is dated, names what it does and does **not** cover, and separates the decision from
the measurement it rests on. **Only Krish can confirm the instruction was given**, and for
`DEC-47` only Angel can confirm the domain content.

| ID | Decision | Status | Basis | Consequence |
|---|---|---|---|---|
| **DEC-38** | **ISAAC v1.05 is the metadata BASELINE, not the maximum.** A field being absent from the official schema is not a reason to discard the information. | **CONFIRMED 2026-09-17** | owner direction | This **reverses nothing in the truth plane** and must not be read as doing so. `CLAUDE.md` §1 is untouched: the vendored schema remains the sole authority on what a valid *official record* is, `isaac validate --official` remains the verdict, and nothing outside it may make a record exportable. What changes is the **disposition of the remainder**: 40 of the BL15-2 corpus's 45 concepts cannot reach an official field, and `DEC-38` says the correct response is structured retention, not loss. |
| **DEC-39** | **Do NOT mutate the upstream schema per experiment.** And **do not discard useful metadata** to make it fit. | **CONFIRMED 2026-09-17** | owner direction | These are one decision because each alone produces a bad outcome: mutating gives per-experiment schemas that nothing can validate against, discarding gives clean records that have lost the science. `schema/isaac_record_v1.json` stays vendored and byte-stable per `schema/PROVENANCE.md`; refreshing it means refreshing from upstream, never editing in place. |
| **DEC-40** | **Experiment/sample-level and Run-specific metadata stay DISTINCT, related by inheritance with EXPLICIT overrides.** | **CONFIRMED 2026-09-17** | owner direction; answers domain question **Q2** | A Run that does not state a value **inherits** it and says so; a Run that states a different one **overrides** it and says so. **Neither is duplication, and an override is never silent** — a reader must be able to see which of the two a value is. This is the shape `resolved_run_draft` already has for the run-level fields; the decision extends the posture to imported campaign context rather than inventing a second mechanism. |
| **DEC-41** | **The four-level placement hierarchy.** For any piece of metadata, in order: **(1)** a native official ISAAC field where one genuinely fits; **(2)** a schema-approved configuration/extension point; **(3)** Run / series conditions where the value is genuinely per-acquisition; **(4)** a structured **ISAAC Extended Context** companion. | **CONFIRMED 2026-09-17** | owner direction | **Level 4 is a companion artifact, not a record field** — the same architectural class as the existing evidence sidecar (`CLAUDE.md` §4), which already carries what the official record cannot. It is **structured**, not a prose dump: every entry keeps its concept, its raw literal, its source and its locator, exactly as `bl15/evidence.py` already records them. Two rules that make the hierarchy honest rather than a shrug: **never skip a level to reach 4** when a real field exists, and **level 4 never gates export** — a record is exportable or not on the official schema alone. This resolves domain questions **Q10**, **Q13**, **Q19**, **Q20** — and settles the *placement* half of **Q18**, whose *substance* (loading and thickness are two distinct concepts) is answered by the beamtime document, not by this decision. |
| **DEC-42** | **`acid` and `base` are preserved as STRUCTURED HISTORICAL CONTEXT, and where the beamtime document's general claim conflicts with its own sample-specific evidence, the SAMPLE-SPECIFIC evidence wins — with the general claim preserved as superseded.** | **CONFIRMED 2026-09-17** | owner direction; answers domain question **Q5** | The filename tokens `acid`/`base` are the scientist's own vocabulary and are kept verbatim as the literal, with the electrolyte identity attached as a separate, separately-sourced statement. **The conflict is real and is preserved, not resolved by deletion:** the document states one blanket electrolyte sentence and then names different electrolytes in individual sample sections. The blanket sentence becomes a superseded shared-context candidate carrying its own locator; **this is a precedence rule for a document that disagrees with itself, and is NOT the answer to `Q15`**, which is about three *different* sources disagreeing and remains Angel's. |
| **DEC-43** | ~~**`context.temperature_K = 298` is APPROVED as a nominal room-temperature assumption for the BL15-2 Angel profile**, and **only** for it.~~ **SUPERSEDED 2026-09-22 — struck, not deleted.** The domain owner (Angel), relayed by the project owner, withdrew the automatic value: missing temperature stays missing, and "room temperature" may mean 293 K as easily as 298 K. **No temperature value is inserted or proposed automatically.** A source's own words ("room temperature", "RT") are preserved verbatim as a `temperature_statement` in the extended context and are never converted to a number. A numeric NOMINAL value may be offered only by a **reviewed, versioned profile rule that names its convention** (NTP-style 293.15 K or SATP-style 298.15 K, [`docs/evidence/temperature-convention-research-2026-09-22.md`](../../evidence/temperature-convention-research-2026-09-22.md)), labelled nominal/inferred, never measured, and requiring scientist confirmation; **none is enabled by default** (`bl15/nominal.py`'s `REVIEWED_NOMINAL_RULES == ()`). See [`docs/historical-import-semantics-2026-09-22.md`](../../historical-import-semantics-2026-09-22.md). | ~~**CONFIRMED 2026-09-17 — a narrow, profile-scoped exception, and the ONLY value in this programme this repository supplies without a source**~~ **SUPERSEDED 2026-09-22** | owner direction (2026-09-17); superseded by the domain owner's answer, relayed 2026-09-22 | **Four conditions, all binding.** (i) Provenance must record it as **nominal / assumed / domain-supplied and NOT measured** — a record that shows 298 K without that qualifier is a defect, not a rounding. (ii) It applies to the **BL15-2 Angel profile only**; no other profile, corpus, or future import inherits it, and a profile that does not match must leave the field absent and stay blocked. (iii) It **does not generalize to any other required-but-absent field** — `CLAUDE.md` §5 is otherwise untouched and no second such default may be added by analogy with this one. (iv) The corpus states no temperature anywhere: the measurement behind the original blocker stands, and this decision supplies the value a scientist would have supplied, on that scientist's authority, not on the parser's. |
| **DEC-44** | **A durable Experiment Activity / Audit History is a product requirement**, recording actor, action, object, field, before, after, timestamp and **source channel** (`web` \| `mcp` \| `historical_import` \| `system`). **Statistics may SUMMARIZE this history; Statistics must never be its source of truth.** | **CONFIRMED 2026-09-17** | owner direction | **Measured 2026-09-17, and it decides the architecture: the change feed cannot serve this.** `change_feed` reports *current* state at a cursor position — it carries no actor, no before/after pair, no channel, and it deliberately **collapses** repeated changes to one entry per object per position, which is exactly the property an audit log must not have. So this needs a **separate append-only activity/event model**, not an extension of the feed. Two existing assets do transfer and must be reused rather than re-invented: the five append-only submission-lifecycle tables are the precedent for append-only-with-no-`DELETE` (`db_write._APPEND_ONLY_TABLES`), and `revision_history.py` is the precedent for a read module that is separate from its write module. **Blocked on `EXT-01`** for the *actor* column only — every other column is recordable today, and a history whose actor reads `unattributed` is more useful than no history. App-side tasks are filed in the ledger; **none of this is Hao's to build.** |
| **DEC-45** | **Do NOT build sharing or ACLs now.** The identity contract must nonetheless be **sufficient to support them later**, and **no authorization decision may ever be derived from an untrusted forwarded header.** | **CONFIRMED 2026-09-17** | owner direction | The second clause is not new policy — it is `docs/identity-trust-contract.md` §7 and `CLAUDE.md` §15 restated as a *forward* constraint so that a future sharing feature cannot quietly relax it. What "sufficient" requires, concretely: a **stable canonical principal** (Dean 2026-08-12: the Authentik **username**, which is not reassigned — **one key, not a username/UID pair**), a **trust basis** recorded beside every stamped actor (the `trust_basis == verified_edge_assertion` gate `record_attribution.py` already implements), and a **channel** on every recorded act. `DEC-44`'s event model must carry all three from day one, because retrofitting an actor onto an append-only history is not possible. |
| **DEC-46** | **File `32` is TWO DISTINCT ACQUISITIONS, not a duplicate. Preserve both and preserve the disagreement. Never overwrite one with the other.** | **CONFIRMED 2026-09-17 — and it RETIRES this repository's own "two duplicate 32 files" wording** | owner direction + the beamtime document | The corpus holds `…after1400Cycling…` and `…after1500Cycling…` under the same legacy number. **The document narrows it, and the measurement is sharper than "the table disagrees":** Sample 3's step 10 carries File Number 32 and records the condition as **after 1500 mV cycling**, and the string `1400` occurs **zero times in the entire document** — not merely in that table. The same sample does record a *different, lower* cycling voltage elsewhere, so it is not that the document names only one; **1400 specifically appears nowhere.** *(Procedure prose and the other cycling value are withheld per the characterization document's §0 disclosure boundary; `1500` is reproduced because it is a token of the filenames the authorizing brief quoted verbatim.)* **That is a narrowing, not an answer** — whether `runNo` was deliberately reused, whether the 1400 file is superseded or mislabelled, and whether `runNo` is unique at all are `Q16` and remain **Angel's**. Until then the import preserves both acquisitions and surfaces the conflict; **preferring either one is forbidden**, including by "the document says so". |
| **DEC-47** | **Angel has CONFIRMED the BL15-2 filename convention**: `runNo_sample/electrodeNo_sampleName_loading_electrolyte_gas_condition_pH_flowRate_filter_Potential`. The second token is a **sample/electrode instance number**. **Stop asking.** | **CONFIRMED 2026-09-17 — domain-owner answer relayed by the project owner** | Angel, relayed | **This is a vocabulary, not a grammar, and the parser stays PROFILE-BASED and tolerant.** The measured corpus still omits tokens, reorders them, spells potentials two ways and contains at least one typo, so a positional regex would still be wrong — the confirmation changes what the tokens **mean**, not how they are **found**. Closes `Q1` **and nothing else** — `Q3`, `Q4`, `Q5` and `Q18`'s substance are closed by the beamtime document, and `Q5`'s internal conflict by `DEC-42`; the remaining Angel set is **eight**: `Q6`, `Q7`, `Q8`, `Q9`, `Q11`, `Q14`, `Q15`, `Q16`. |

## B5. Decisions taken by the 2026-09-17 owner direction, second continuation

**Three decisions. Two unblock work that was recorded as waiting on Krish; the third overturns a
technical premise this repository's own ledger had written down, and is recorded as a decision rather
than as an implementation detail because the ledger's version of it would have stopped the work.**

**Provenance, stated because a repository cannot witness a conversation.** All three reach the
repository as an **owner instruction relayed in-session** — the same evidentiary class as `DEC-38`…`DEC-47`
and as the Dean answers §15 of `CLAUDE.md` records as *"OPERATOR TESTIMONY … not an observation by
this repository"*. No evidence file or transcript backs them, and authorship witnesses nothing: every
commit here is authored by the project owner with Claude co-authored, so a commit author cannot
distinguish a granted decision from an assumed one. What a reader **can** check is the boundary — each
row is dated, names what it does and does not cover, and forbids an earlier slice from citing it.
**Only Krish can confirm the instruction was given.**

| ID | Decision | Status | Source | Reasoning and boundary |
|---|---|---|---|---|
| **DEC-48** | **Do NOT add or prioritize a dedicated Authentik logout link.** It is not part of the core scientist workflow. It remains available as a later Settings / session-management decision. | **CONFIRMED 2026-09-17** | owner direction | **This CLOSES an item that was explicitly recorded as open and Krish's.** `CLAUDE.md` §15 says of Dean's Q9 answer: *"`/outpost.goauthentik.io/sign_out` is a valid logout path. Whether ISAAC should surface it is a product decision Dean was not asked and did not make — still open, and Krish's."* It is now answered: **not now.** Two things this does NOT do. It does not retract Dean's answer — the path is still valid and still recorded, so a future session building session management starts from a known-good endpoint rather than re-asking. And it does not authorize *removing* anything: no logout affordance exists to remove. **The honest framing of the deferral is that a scientist on a shared workstation currently has no in-app way to end a session**, which is a real gap and is deliberately accepted as lower priority than the capture workflow — recorded here so the acceptance is a decision on the record rather than an oversight nobody noticed. |
| **DEC-49** | **The Activity / Audit history persists in the EXPERIMENT STATE DOCUMENT, not in a new table. Migration `0006` is NOT to be written.** | **CONFIRMED 2026-09-17 — and it OVERTURNS a premise this repository's own ledger had committed** | owner direction (*"Build the application-side audit/activity foundation now"*) + the measured `proposals` precedent | **The ledger's `ACT-001` row says the model *"Needs migration `0006`, which means it needs an approval packet and an operator act"*. That is FALSE, and it is the kind of false premise that silently converts buildable work into blocked work** — a feature needing `0006` would be a feature that does not function until an operator acts, and no such authorization exists. The `proposals` precedent settles it: `proposals.STATE_KEY = "proposals"` is a top-level key in the experiment state document, and its own comment block records that **no migration is required, because `Experiment.from_state` reads every optional key with `.get` and a default**, so a document written before the feature existed hydrates to an empty value. `CLAUDE.md` §15's 2026-08-29 extension made that choice **deliberately**: it records **four** separate occasions on which a table reached `db_write.OWNED_TABLES` before any committed sentence named it, and says *"a fifth is avoidable by not needing one."* **`db_write.OWNED_TABLES` is therefore UNCHANGED by the activity work, and no migration file is added.** Two consequences stated rather than left to be discovered: activity is durable **exactly where the experiment document is durable and no more**, and an activity event is **structurally** inert to export (it is outside `draft`, so `export.transform` cannot see it, it is in no submission content signature, and in no run's `resolved_run_draft`) rather than inert by assertion. |
| **DEC-50** | **Build `ACT-001`…`ACT-004` NOW. Do not wait for trusted identity. Until a trusted boundary exists, record the actor honestly as `unattributed` — never guessed, and never derived from a forwarded header.** | **CONFIRMED 2026-09-17** | owner direction | This is `DEC-44` released for implementation, and it names the split precisely: **only `ACT-005`** — populating the actor from a trusted boundary — is externally blocked, on `EXT-01` (Hao). Everything else is recordable today with no external dependency: timestamp, channel (`web` \| `mcp` \| `historical_import` \| `system`), action, object type and id, experiment, run, field path, before, after, and a source/provenance reference. **A history whose actor reads `unattributed` is more useful than no history**, and it is *honest*, which the alternative is not: `CLAUDE.md` §15 records Dean's 2026-08-12 answer that the Service is a plain ClusterIP with no NetworkPolicy, so *"the presence of `X-authentik-username` ALONE DOES NOT PROVE AUTHENTICATED EDGE TRAVERSAL"* — an actor read from that header would be a **forgeable** claim rendered as a fact. `record_attribution.py`'s `trust_basis == verified_edge_assertion` gate is the seam, it already exists, and **no verifier in this build mints that basis**, so the seam stays unset by construction rather than by policy. Per `DEC-45`, the event model must carry the stable principal, the trust basis and the channel **from day one**, because retrofitting an actor onto an append-only history is not possible. **Append-only: no `DELETE`, no `UPDATE`, ever. Activity history is the source of truth; Statistics may summarize it and must never replace it.** Sharing and ACLs remain **NOT** authorized (`DEC-45`). |

## B6. Decision taken by the 2026-09-18 owner direction — where Activity lives

**One decision, and it was found to be ALREADY SATISFIED by the shipped code. That is recorded as
the finding rather than smoothed over, because "the decision is already implemented" and "the
decision was implemented in response to the decision" are different facts, and only the first is
true here.**

**Provenance.** An **owner instruction relayed in-session**, 2026-09-18 — the same evidentiary class
as `DEC-38`…`DEC-50` and subject to the same caveat: no evidence file backs it, authorship witnesses
nothing, and **only Krish can confirm the instruction was given.** What a reader can check
mechanically is the boundary and the compliance measurement, both given below.

| ID | Decision | Status | Source | Reasoning and boundary |
|---|---|---|---|---|
| **DEC-51** | **Activity belongs INSIDE each Experiment. It must NOT become a primary global scientist-sidebar destination.** The global navigation stays simple. | **CONFIRMED 2026-09-18 — and MEASURED as already satisfied at `938e4829`** | owner direction | The scientist's global navigation is four destinations — `Experiments`, `Historical Import`, `Statistics`, `Settings & API` (`apps/web/src/components/LeftNav.tsx`'s `ITEMS`) — and **Activity is not among them and must not be added.** Where it actually lives: the **fifth Experiment-scoped workspace**, `RECORD_VIEW_IDS = ['fields','runs','capture','graph','activity']` (`apps/web/src/lib/routes.ts:128`), reachable at `?view=activity` and mounted at `apps/web/src/screens/RecordWorkbench.tsx`. **Verified mechanically, not assumed:** `LeftNav.tsx`'s `ITEMS` has no activity entry, and `ROUTES` declares no global activity path. **It is a DESTINATION, not a workflow step** — it carries no tick, no lock and no `aria-current="step"`, because there is no derivable criterion for *"the history is finished"*. That is the argument `workflow.py:128-149` already makes for submission and the capture group makes for itself, so this is a reuse of a settled precedent rather than a new exception. **The alternative the owner permitted — a dedicated Experiment-level tab instead of `Overview → View all activity` — is the shape that shipped**, and it shipped on the sidebar-destination mechanism the other four workspaces already use, so the five destinations are one system rather than four plus an exception. |

### What `DEC-51` does NOT change

- **No global navigation item is added, now or later, without a new decision.** `DEC-25`'s standing
  obligation on `Statistics` is the precedent for how expensive a sidebar slot is.
- **It authorizes no second Activity surface.** A `Recent Activity` summary elsewhere (for example on
  `Statistics`, per `ACT-004`) is a **summary that links into** this destination, never a competing
  copy of it — `DEC-44`'s *"Statistics summarizes Activity; Statistics is never the source of truth"*
  governs, unchanged.
- **It does not make Activity a workflow step**, and a future slice that gives it a completion state
  would be inventing a criterion nobody defined (`CLAUDE.md` §5).
- **The truth plane is untouched**, exactly as under `DEC-50`.

### What `DEC-48`…`DEC-50` do NOT change

- **No new table, no migration, no operator act.** `db_write.OWNED_TABLES` unchanged. `DEC-49` is
  specifically a decision *not* to need one.
- **No authorization is derived from any forwarded header**, for any purpose, ever (`DEC-45`,
  `docs/identity-trust-contract.md` §7).
- **`ACT-005` stays blocked** on `EXT-01`. Building the seam is not wiring it, and a seam that is
  built must not be described as connected (`ai-integration-decision-packet.md` §6's *no fake
  `Connected` state*, applied to identity).
- **No sharing, no ACLs, no per-experiment collaborator model** is built. `DEC-45` is unchanged;
  `DEC-50` only requires that the activity model not *foreclose* them.
- **The truth plane is untouched.** Activity is not evidence, not a confirmation, and not a field
  value; it cannot make a failing record pass or a passing record fail.

### What `DEC-38`…`DEC-43` do NOT change, stated because the truth plane is the thing most at risk here

A hierarchy that ends in "keep it somewhere else" is one careless slice away from becoming a
hierarchy that ends in "put it in the record anyway". So, explicitly:

- **Official validation is unchanged.** `schema/isaac_record_v1.json` + `official.py` remain the
  only authority on record validity. Nothing in level 2, 3 or 4 can make a failing record pass.
- **Export gating is unchanged.** `export.py` still refuses what it refused yesterday.
- ~~**The no-guessing rule is unchanged** except for the single, named, profile-scoped `DEC-43`
  exception — which is a *scientist-supplied* value, recorded as assumed, not a parser inference.~~
  **Corrected 2026-09-22: the no-guessing rule is now unchanged WITHOUT exception.** `DEC-43` is
  superseded; no value is supplied without a source, and a nominal temperature can only ever be
  offered by a reviewed, convention-naming rule — none of which is enabled — for a scientist to confirm.
- **The extended-context companion is an ASSISTANT artifact**, exactly as the evidence sidecar is,
  *"unless mentors approve it as an official ISAAC convention"* (`CLAUDE.md` §4). It is not an
  ISAAC standard and this repository must not describe it as one.

## B7. Decisions taken by the 2026-09-22 owner direction — hosted-QA redesign and Angel's BL15 answers

**Sixteen decisions, `DEC-52`…`DEC-67`. Two supersede earlier rows — `DEC-43` (by `DEC-63`) and
the "Angel-style" profile framing behind `DEC-47`'s implementation (by `DEC-60`) — and are recorded
as supersessions rather than folded in.**

**Provenance, per row.** `DEC-52`…`DEC-61` are **owner instructions relayed in-session** (the
2026-09-22 direction, which cites Krish's hosted QA of build `0a12f7ae9010`). `DEC-62`…`DEC-66` are
**domain-owner (Angel) answers relayed by the project owner**, dated 2026-09-22. `DEC-67` is an
**engineering decision taken by the orchestrator** inside `DEC-65`'s conflict model, on measured
evidence, and narrowed after an independent review. Same evidentiary class as `B3`–`B6` for the
relayed rows: no transcript backs them, authorship witnesses nothing, and **only Krish can confirm
the instruction was given — and for the domain rows, only Angel can confirm the content.** The
screenshots the direction cites **did not arrive** with the message; every UI finding was instead
reproduced locally from `main` at `0a12f7ae`, then confirmed read-only on hosted, and is listed in
[`docs/evidence/owner-qa-issue-inventory-2026-09-22.md`](../../evidence/owner-qa-issue-inventory-2026-09-22.md).

| ID | Decision | Status | Source | Reasoning and boundary |
|---|---|---|---|---|
| **DEC-52** | **Capture is a focused Experiment section, and Runs live under Capture.** The Experiment sidebar reads `DATA CAPTURE` (Capture · Proposals · Runs) / `WORKFLOW` (five server-derived steps) / `WORKSPACES` (Activity · Evidence Trail). `Record Fields` is **removed** from workspace navigation; its route stays and is reached through the `Record Created` step. | CONFIRMED 2026-09-22 | owner | Extends `DEC-14` (Capture is a destination, never a step) and `DEC-51` (Activity inside the Experiment). Two labels reaching one place was the defect. |
| **DEC-53** | **Each capture method opens a focused task view**, never an inline expansion beneath four cards. | CONFIRMED 2026-09-22 | owner | Measured before: 1795 px empty, 4297 px after `Start Writing`; `Start Writing` and `Open Recorder` opened the same inline panel. |
| **DEC-54** | **Focused capture views pair the task with a live Record Map** (task left, sticky map right, stacked when narrow). | CONFIRMED 2026-09-22 | owner | Reuses `DEC-29`'s Record Map; never the full schema wall by default. |
| **DEC-55** | **Voice Capture's primary production path is Claude → ISAAC MCP**, rendered from real capability state (`mcp.posture`); the local MediaRecorder is a **secondary** "Record locally instead" path. | CONFIRMED 2026-09-22 | owner | `DEC-10`'s native recorder is retained, not deleted; its role narrows to fallback. **No fake `Connected`** (T6): "Connected" renders only if ISAAC can verify a connection. |
| **DEC-56** | **Normal scientist views hide raw schema paths by default**; the path lives behind accessible `?` help or advanced detail. | CONFIRMED 2026-09-22 | owner | Exceptions: developer/settings surfaces, copyable API references, evidence where the exact path is the point. `UX-014`'s rule that a path is never *removed* stands — it is *relocated*. |
| **DEC-57** | **Semantic states use one shared icon + text + colour primitive** (success/warning/danger/info/neutral), never colour alone. | CONFIRMED 2026-09-22 | owner | "Sources Agree" renders only where source evidence says they agree. |
| **DEC-58** | **Workflow rows carry two independent signals: completion STATE and current LOCATION.** | CONFIRMED 2026-09-22 | owner | Measured before: `Complete Metadata` drew as current on Runs, Capture, Activity and `/export`. |
| **DEC-59** | **Proposal acceptance is preflighted from capability state**; when success is known impossible the Accept action is locked with a compact reason. | CONFIRMED 2026-09-22 | owner | `409 human_actor_required` is **unchanged** and still handled; no actor is faked (`EXT-01`). |
| **DEC-60** | **Parsing/convention profiles are independent of scientist/operator identity.** One Experiment may use several convention profiles and several operators; a profile applies at facility, beamline, acquisition system, Experiment, Run subset, source family or source; the operator is **provenance**. | CONFIRMED 2026-09-22 | owner | **Supersedes the "Angel-style" framing** of `ssrl_bl152_angel` as an architectural unit; the id survives as a historical alias. `DEC-47`'s *vocabulary* is unchanged. |
| **DEC-61** | **Historical "learning" means reviewed, versioned convention reuse** — scoped (only here / this Experiment / profile), never silently promoted, stored migration-free. | CONFIRMED 2026-09-22 | owner | Not model retraining. Actor recorded honestly `unattributed` until `EXT-01` (`DEC-50`). |
| **DEC-62** | **Missing scientific facts remain empty by default.** A suggestion requires an explicit, reviewed rule. | CONFIRMED 2026-09-22 | **Angel** (relayed) | Restates T5 with the domain owner's own reasoning. |
| **DEC-63** | **`DEC-43` (nominal 298 K for the BL15-2 profile) is SUPERSEDED.** No automatic insert and no automatic proposal. A literal "room temperature" is preserved verbatim; a numeric nominal may be *offered* only by a reviewed profile rule that names its convention, labelled nominal, confirmed by the scientist, never labelled measured. | CONFIRMED 2026-09-22 — **SUPERSEDES `DEC-43`** | **Angel** + targeted research | Research: `docs/evidence/temperature-convention-research-2026-09-22.md` — 298.15 K (SATP) and 293.15 K (NTP / dictionary "room temperature") are both real conventions answering different questions; neither is evidence of an unrecorded temperature. |
| **DEC-64** | **The HERFD primary signal is selected per Run from evidence.** `vortDT` is common, not universal; dual-element channel→element mapping is representable; ambiguity stays unresolved for review. | CONFIRMED 2026-09-22 | **Angel** | Resolves `Q11` conditionally. Any threshold is measured, tested and reviewable. |
| **DEC-65** | **Run 32 remains unresolved; historical source conflicts have no universal precedence.** Source fact · normalized reading · suggested resolution (non-authoritative) · scientist-confirmed resolution are distinct, and only the last is authoritative. | CONFIRMED 2026-09-22 | **Angel** (does not know; asked ISAAC to brainstorm) | `Q16` becomes "domain owner does not know → permanently preserved conflict"; `Q15` becomes a policy. A confirmed resolution of a record field still goes forward as a proposal behind the actor gate. |
| **DEC-66** | **Free-text quality phrases are Data Quality Notes and never become `qc.status` automatically.** | CONFIRMED 2026-09-22 | **Angel** (did not know what "QC" meant in the question) | `Q14` → intentionally left missing pending explicit domain rules. The schema field is untouched. |
| **DEC-67** | **A value expected once per scan item (a detector column, a motor, a file-name token, a scan's own target) that differs across ESTABLISHED scans is VARIATION, not a conflict.** A measurement-level reading (e.g. a macro's planned value) is ALWAYS compared with each scan-level reading of the same concept, and readings whose scan correspondence is not established are compared as one measurement — so a planned-vs-recorded disagreement is always a conflict. Named and versioned (`bl15.mapping.cardinality.v2`). `emission_energy`, `energy_grid`, `counting_time` and `scan_command` stay **per-measurement until Angel says otherwise**. | CONFIRMED 2026-09-23 — engineering decision inside `DEC-65`, **narrowed after the final independent review** found v1 could hide a planned-vs-recorded disagreement (C1) | measured: on the synthetic multi-operator corpus v1 turned 36 of 43 field "conflicts" into variation; the review then showed v1 also silenced a genuine one-scan disagreement, so v2 restores the comparison and reverts four concepts pending the domain owner | **Never suppresses a genuine disagreement** (mutation-tested: measurement-vs-scan, one scan two sources, unverified scan correspondence). Which acquisition quantities are legitimately per-scan, and whether the real corpus's `acquisition_timestamp` / `sample_position` conflicts are genuine, are **Angel's**; they stay surfaced as conflicts meanwhile. Evidence: `docs/evidence/bl15-real-regression-2026-09-22.md`. |

### What `DEC-52`…`DEC-67` do NOT change
- **The truth plane is untouched.** Official validation, export gating, provenance, actor trust,
  immutable submitted snapshots, no-guessing and no agent final Submit are unchanged.
- **No new table, no migration, no operator act** (`DEC-49` precedent).
- **`Q6`, `Q7`, `Q8` remain Angel's** — his reply did not address them — and **`Q21`** (which acquisition quantities are legitimately per-scan) is new.
- **No production provider, MCP endpoint, identity boundary or real-byte ingestion is enabled.**
  `EXT-01`, `EXT-02`, `EXT-13` are unchanged; the new `historical_file_ingestion` capability
  defaults to **disabled**.

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
| **EXT-13** | **Governance decision to enable REAL historical file bytes** — retention period, storage location, data classification, and deletion path for uploaded scientific files | institution / SLAC data governance, via Hao | **OPEN — and it is the gate `DEC-33` names.** `POST /api/uploads` is an unconditional **403** today and `upload-claim-parity.test.tsx` pins that claim and its polarity. Application-side implementation is owner-authorized; **enabling it is not an application decision** |

### Addressee change, 2026-09-17 — Hao, not Dean

**Dean's name stays on every committed row above**, because those rows record who answered or
deferred at the time and rewriting them would falsify the history. **New asks, packets and
unblock requests go to Hao.** The operator package for this handoff is
[`docs/hao-production-unblock-package-2026-09-17.md`](../../hao-production-unblock-package-2026-09-17.md);
the paste-ready discovery prompt is
[`docs/hao-production-ai-execution-prompt-2026-09-17.md`](../../hao-production-ai-execution-prompt-2026-09-17.md).

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

