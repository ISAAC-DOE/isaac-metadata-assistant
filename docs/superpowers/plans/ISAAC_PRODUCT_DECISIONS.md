# ISAAC Product Decision Register

**Canonical, multi-session.** One row per decision. Update this file in the same PR as any slice
that changes a row. Never restate a decision elsewhere — link to its ID.

**Created:** 2026-09-12 · **Last updated:** 2026-09-12 (planning run, `main` @ `2f9a1133`)

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
| **DEC-04** | Evidence Graph is removed from **primary scientist navigation**; underlying provenance relationships are retained | **PROPOSED** | directive §40; my measurement: the Graph workspace is the most control-dense surface in the record screen (34 buttons, 145 text elements) | depth of removal is **DEC-11**; backend removal requires dependency analysis first |
| **DEC-05** | Final labels for top-level and Experiment-level navigation | **OPEN — NEEDS KRISH** | my proposal: `Experiments` / `Historical Import` / `Settings`, and `Overview / Runs / Capture / Review / Record` | must be reconciled with the app's established language (prior direction used `Lab Records`, `Experiment Details`, `Capture & Proposals`, `Review Evidence`, `Review Export`) |
| **DEC-06** | Folder storage shape | **OPEN — engineering, resolved in the data-model workstream** | strong prior: **no new table** (a feature needing a migration does not work until an operator acts — a hard stop no agent can lift) | if a new table is required, it needs a new committed `CLAUDE.md` §15 sentence **plus** an owner-approved packet **plus** an operator action |
| **DEC-07** | Extend `GET /api/experiments` before redesigning the Library screen | **PROPOSED** | measured: the payload carries no run count, no technique/beamline, and **no `updated_utc`** — so "sort by Last Updated" is not implementable today | this is the first implementation slice; the screen cannot be honest without it |
| **DEC-08** | `Review` becomes its own Experiment workspace, consolidating proposals, ambiguities, conflicts, unmapped notes, missing info and export readiness | **PROPOSED** | those six live in four different places today | the largest single IA simplification available; prerequisite for one review experience across all ingestion sources |
| **DEC-09** | Whether a cross-Experiment "Needs Review" queue is first-class navigation | **OPEN — NEEDS KRISH** | promoting a lens to a peer destination is what produced the current 21-destination census | recommendation: start as a filter chip on `Experiments`, promote only on evidence of use |
| **DEC-10** | Native ISAAC microphone capture is **retained**, with its role stated | **PROPOSED** | four PRs of recent work; an orphaned-microphone defect was found and fixed; playback shipped | role: manual recording + typed/pasted transcript + fallback + foundation for a future approved provider. **Automatic transcription must never be implied** — every provider answers `501` and `audio_ref` is an integer no provider can dereference |
| **DEC-11** | Depth of Evidence Graph removal: visualization-only / demote-to-Advanced / full backend removal | **OPEN — NEEDS EVIDENCE then KRISH** | dependency analysis pending | deletion is not a substitute for understanding |
| **DEC-12** | Historical Import raw-source retention model | **PROPOSED: Option A (reference-first) now; Option C (ephemeral parse) for parser development; Option B deferred; Option D ruled out for real data** | Option A costs zero new code and reuses the shipped `assets[]` pointer-only feature; Option C mirrors the already-approved "one short-lived read, sanitized output only" pattern; Option B needs infra approval and there is no corpus to justify it; **Option D — a live model reading real scientific files — is exactly what Dean's D1–D9 deferral withholds** | revisit if the corpus arrives with a reproducibility requirement Option A cannot meet |
| **DEC-13** | The BL15-2 pilot corpus | **OPEN — NEEDS KRISH + ANGEL. This is Pillar 2's gating item.** | **measured 2026-09-12: this repository contains no historical BL15-2 material at all** — zero `.mac`, zero `.xlsx`/`.xls`; everything beamline-shaped in `examples/` is generated by `scripts/make_synthetic_examples.py` with fictional people and a fictional year-2099 session; `openpyxl` is not a dependency | **no `.mac` parser may be designed before a representative file exists.** §5 forbids designing against assumptions. The first Pillar 2 deliverable is a data request |
| **DEC-14** | Capture is a sidebar destination, **not** a workflow step | **CONFIRMED (carried forward)** | no derivable criterion for "capture is finished"; `notes >= 1` would invent one and nag records that need none; `workflow.py:128-149` already argued this for submission | no tick, no lock, no ordering, no `aria-current="step"` |
| **DEC-15** | The ambiguity / candidate model is **unified** across live voice, historical import, assistant output and CSV ingestion | **PROPOSED — pending the data-model workstream's verdict** | they are one problem: multiple sources offer candidate information not yet accepted as truth | the alternative — four ambiguity systems — is the outcome to design against. A justified reason not to unify must be named, not assumed |
| **DEC-16** | Ambiguity is an **assistant-side (draft/sidecar) construct**; a single value must be chosen before export unless the official schema natively represents uncertainty at that path | **PROPOSED — verification pending** | §5 forbids inventing range semantics | if the schema has no native representation, the candidate set never reaches an official record — and that is correct, not a limitation |
| **DEC-17** | Orchestrator model for this programme | **CONFIRMED by owner, 2026-09-12** | owner selected "proceed on Opus 5" when told this session is `claude-opus-5[1m]` and not Fable 5.1 | `CLAUDE.md` §10 already ratifies an Opus orchestrator as the standing fallback; orchestrator-only discipline retained |
| **DEC-18** | Sub-agent ceiling for this programme | **CONFIRMED by owner, 2026-09-12** | owner: "spawn only 5 subagents don't let them spend 5 more" | **five total, not five concurrent**; nested spawning forbidden and the constraint was relayed to every running agent. Reviewer agents count. Consequence already paid: Impeccable's `critique` ran single-context and is bannered `⚠️ DEGRADED` |

## C. Open — external owners

These are not ours to decide. Full detail in
[`2026-09-12-isaac-blockers-and-risks.md`](2026-09-12-isaac-blockers-and-risks.md).

| ID | Question | Owner | Status |
|---|---|---|---|
| **EXT-01** | Trusted authentication boundary (the Service is a plain ClusterIP with no NetworkPolicy; forwarded identity headers are forgeable in-cluster) | Dean / SLAC infra | **OPEN** — reconfirmed 2026-08-12. Hosted `submission.blockers` reads exactly `["no_attributable_actor"]` |
| **EXT-02** | Remote MCP reachability and OAuth in production | Dean / SLAC infra | **OPEN** — `GET /krish/api/mcp` returned **404** on 2026-09-12 while `docs/` cites that URL as live |
| **EXT-03** | Registering an organization-wide remote MCP connector | **Claude organization Owner / Primary Owner — identity UNKNOWN; do not assume this is Dean** | **OPEN** |
| **EXT-04** | D1–D9: model provider, credential, billing, egress, retention, data policy, transcription provider | Dean — **DEFERRED 2026-08-12**: *"leave AI integration as future work rather than increasing scope at this point"* | **DEFERRED.** Implementation against deterministic fakes is separately owner-authorized; a production provider is not |
| **EXT-05** | Is scientific speech/data approved to flow through the organization's Claude environment? | institution / Dean | **OPEN — and new.** Created by the Claude-Voice architecture. Distinct from EXT-04: Claude-mediated capture may need no ISAAC-owned ASR, but it does need this answer |
| **EXT-06** | **G2** — hosted per-record display | Dean | **CLOSED BY DEFAULT.** Hosted `record_display: "closed"`, observed 2026-09-12 |
| **EXT-07** | **G3** — the five withheld aggregates | Dean | **OPEN** — withheld pending his answer |
| **EXT-08** | Migration `0005` approval, application, backfill, Stage-2b cutover | Krish (approval) + operator (application) | **OPEN.** Observed 2026-09-12: hosted `run_projection.last_pass.unavailable: 3` — all three hosted experiments have an unreadable run projection |
| **EXT-09** | Six `system.configuration.*` classifications | Angel / domain owner | **OPEN** — blocks nothing else; two question packets prepared |
| **EXT-10** | Representative BL15-2 corpus + expert ground truth | Krish + Angel | **OPEN — gates Pillar 2.** See **DEC-13** |
| **EXT-11** | Authenticated hosted QA, true 200% zoom, real-microphone check, hosted narrow widths | Krish | **OPEN.** *Partially advanced 2026-09-12*: rollout verified (hosted `commit` = `2f9a1133`), and that is the **rollout**, not the QA. No CDP method can drive true zoom; `resize_window` does not move the rendered viewport |
| **EXT-12** | Personal deployment retirement (Vercel + Railway) | Krish | **OPEN** — both still live and public; Railway has a persistent volume, so deleting destroys what pausing preserves |
