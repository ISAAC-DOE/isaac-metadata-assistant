# Session closure — 2026-09-03: record-screen redesign (PR-A through PR-E, plus #232)

This session redesigned the Review Record screen from one long page into four
sidebar-navigated workspaces, made transcript capture a durable proposal
producer, rebuilt Runs as master-detail, and made the Assistant panel
responsive. Six PRs merged (#228–#233). Every number in this document is
either quoted from a command run in this session (`gh`, `git`) or copied
verbatim from a PR body / commit message, marked as such.

---

## 1. Slices, PRs, SHAs

Org `main` moved from `6ce3f5c` (v0.0.213, this session's starting point,
verified with `git merge-base --is-ancestor 6ce3f5c origin/main`) to `ec945d7`
(PR #231's merge, the last of the six).

| Slice | PR | Title | Branch head | Merge SHA | Merged at (UTC) | Implementer | Reviewer |
|---|---|---|---|---|---|---|---|
| PR-A | [#228](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/228) | feat(capture): transcript finalize mints durable proposals — the website's first proposal producer | `5d44f0b` | `a342175` | 2026-09-03T23:49:59Z | Opus | Opus |
| PR-B | [#229](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/229) | feat(record): four sidebar workspaces replace the one long record page | `0aee23b` | `6bac9cc` | 2026-09-04T01:02:26Z | Opus | Opus |
| PR-C | [#230](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/230) | feat(runs): master-detail Runs workspace — compact rows, one open editor, guarded leave | `f55839d` | `363180f` | 2026-09-04T03:02:33Z | Sonnet | Opus |
| PR-D | [#231](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/231) | feat(capture): state-driven transcript capture, note→proposal act, calmer proposal review | `3aa6e95` | `ec945d7` | 2026-09-04T04:41:56Z | Sonnet | Opus |
| PR-E | [#233](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/233) | feat(shell): collapsible Assistant rail, compact workflow spine at narrow widths, workspace-aware Assistant | `0db23d9` | `7320b9c` | 2026-09-04T03:52:12Z | Sonnet | Opus |
| — | [#232](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/232) | test(concurrency): sentinel checks walk document values, not the serialized text | `c6eb625` | `51f4f40` | 2026-09-04T04:36:42Z | Opus | Opus |

Merge order was NOT PR-A→B→C→D→E→#232 in a straight line: PR-C merged before
PR-D and PR-E's final (re-merged) heads, and #232 (a flake fix that had
started blocking PR-C's own CI) landed between PR-E and PR-D. The exact
sequence, from this session's own orchestration log
(`orchestration-plan.md`, quoted verbatim for the ordering claim): PR-A →
PR-B → PR-C → PR-E → #232 → PR-D. Each of PR-D and PR-E was re-merged with
`main` and re-verified (typecheck + full suite + the trusted/mutation e2e
specs that share code with what had just landed) after every PR that merged
ahead of it — this is why PR-D's own branch head moved three times
(`8ea7d5d` → `c542f5f` → `3aa6e95`) before its final merge.

**CI run ids**, one row per SHA that actually ran CI (`gh run list --commit
<sha>`, re-run at doc-write time):

| SHA | CI run | Conclusion |
|---|---|---|
| `5d44f0b` (PR-A head) | `33816526967` | success |
| `a342175` (PR-A merge) | `33819285869` | success |
| `0aee23b` (PR-B head) | `33821389704` | success |
| `6bac9cc` (PR-B merge) | `33824192751` | success |
| `f55839d` (PR-C head) | `33829216588` | success |
| `363180f` (PR-C merge) | `33831738924` | success |
| `c6eb625` (#232 head) | `33832605781` | success |
| `0db23d9` (PR-E head, first re-merge) | `33832303467` | success |
| `7320b9c` (PR-E merge) | `33834758234` | success |
| `3aa6e95` (PR-D head, final re-merge) | `33835029534` | success |
| `51f4f40` (#232 merge) | `33837450907` | success (resolved during this fix pass — released as **v0.0.218**, see below) |
| `ec945d7` (PR-D merge, `main` HEAD) | `33837767977` | success (resolved after the second fix pass — released as **v0.0.219**, see below) |

**Release tags** (`git tag --sort=-creatordate`, `git rev-list -n1 <tag>`,
re-derived rather than copied):

| Tag | SHA | PR |
|---|---|---|
| v0.0.214 | `a342175` | #228 |
| v0.0.215 | `6bac9cc` | #229 |
| v0.0.216 | `363180f` | #230 |
| v0.0.217 | `7320b9c` | #233 |
| v0.0.218 | `51f4f40` | #232 |
| v0.0.219 | `ec945d7` | #231 |

`51f4f40` (#232)'s CI concluded `success` during the first fix pass, and the
release gate — resolved via `gh run view 33839970832 --log`, which shows
`commit under release: 51f4f4015bccbf176baa7d0784c5730ee73b09f7` and
`release gate ALLOWED for 51f4f40…: all 1 required 'CI' run(s) for this
commit concluded 'success'`, then `TAG="v0.0.218"` — tagged it **v0.0.218**;
`git rev-list -n1 v0.0.218` resolves to `51f4f40`, confirmed.

**`ec945d7` (PR-D's merge, then current `main` HEAD) has since resolved
too**, in a later pass of this document. Its own CI run (`33837767977`)
concluded `success`, confirmed with `gh run view 33837767977 --json
status,conclusion`. The release gate then ran as `33842289349` and, per its
own log (`gh run view 33842289349 --log | grep -aE "commit under release|
release gate|TAG="`), printed `commit under release:
ec945d75e21b64cf6138a9ec09199c413deae692`, `release gate ALLOWED for
ec945d7…: all 1 required 'CI' run(s) for this commit concluded 'success'`,
then `TAG="v0.0.219"` — tagged it **v0.0.219**; `git rev-list -n1 v0.0.219`
resolves to `ec945d7`, confirmed. **All six PRs of this session are now
merged AND released**, `v0.0.214` through `v0.0.219`. §9 has the full
detail and no longer carries an "unresolved" status for `ec945d7`.

**A seventh, related PR merged after this closure doc's own drafting
began and is worth recording here rather than treated as out of scope:**
[#235](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/235)
("test(trusted): two-actor proof with a REAL second browser", head
`632ac85`) — this is PR-F1, the real-second-browser proof discussed in §7b
— **merged as `30ac611`** (`gh pr view 235 --json state,mergeCommit`
confirms `MERGED` / `30ac6115e73cb601918ba326f69b15274581ce6e`). It is
test/doc-only (a new Playwright spec plus its own evidence doc); it also
releases an image when its own CI concludes, on the same mechanism as every
other merge in this table — not reported here as a further release because
this document does not track PR #235's own CI/release status as closely as
the six PRs that are this session's actual subject.

---

## 2. What changed, in scientist-facing language

**Before this session**, the Review Record screen was one page: a 3,116px
scroll (desktop, the seeded 2-run record) holding the record's own fields,
the run list, transcript capture, Unmapped Notes, Ingestion Proposals, and
Asset References — 59 visible interactive controls with no wayfinding between
them (measured in `docs/evidence/redesign-before-after-2026-09-03.md`, and
independently confirmed by PR-B's own body, which quotes the identical
3,116px/59-control figures from its own IA audit). Transcript capture wrote
run fields directly by `PATCH`; nothing could persist an interpreted value as
a reviewable proposal.

**After this session:**

- The record sidebar lists four **Workspaces** beneath the unchanged,
  server-derived workflow spine: **Record Fields** (default), **Runs**,
  **Capture & Proposals**, **Graph**. Each is a real link, deep-linkable and
  Back/Forward-safe.
- **Runs** is master-detail: a compact list of rows, one open editor at a
  time, Previous/Next between loaded runs, and a real confirmation dialog
  before leaving a run holding text this build could not parse.
- **Capture & Proposals** puts one entry action ("Capture Experiment Notes")
  and one primary action per state on the transcript panel, and finalizing a
  capture now **mints durable, reviewable proposals** — the first path in the
  product that can create a proposal at all, closing a gap the prior session
  measured and left open (`docs/evidence/two-actor-workflow-proof-2026-09-02.md`
  §1).
- **Ingestion Proposals** stays oldest-first by default (the server's own
  default, deliberately unchanged — a review queue reads chronologically);
  the "Show Newest" control / order selector brings a just-arrived proposal
  into the first window on demand. (The "counted but not reachable past the
  load window" gap itself was already closed by the prior session's #225,
  `b467324`, 2026-09-02 — not by this session.) Unmapped Notes gained
  "Propose a Value from This Note" — the website's first caller of the
  direct `api.createProposal` path.
- The **Assistant** panel can be collapsed to a 44px labelled rail on desktop
  (≥1025px) without unmounting — a staged proposal or a typed question
  survives collapse and a workspace switch — and names the workspace the
  reader is on. At ≤1024px, the workflow spine collapses to a single-row
  compact stepper and the Assistant reverts to its existing slide-over
  drawer.

Nothing above changed what counts as valid or exportable; every workspace
still reads from, and writes through, the same truth-plane routes as before
(`src/isaac_records/*`, untouched — see §7).

---

## 3. The final information architecture

```
Record sidebar
├── Workflow spine (server-derived, gated — unchanged)
│     Load Record → Complete Metadata → Review Evidence
│     → Review Export Readiness → Export
├── Workspaces (ungated, local, no completion state)
│     ├── Record Fields   (?view=fields — default; bare /record/<id> lands here)
│     │     experiment field groups → Record Identity → Asset References (collapsed)
│     ├── Runs            (?view=runs)
│     │     master-detail: compact row list, OR one open run editor
│     ├── Capture & Proposals  (?view=capture)
│     │     transcript capture → Unmapped Notes → Ingestion Proposals
│     └── Graph           (?view=graph)
│           the record's memory-graph projection
└── Evidence Trail (link, outside the workspace nav — record-level evidence)
```

All four workspace links, `?run=`, `?compare=`, and `?at=` are independent
URL parameters copied forward on every internal navigation, so a reader who
focused a run and then opened the graph returns to the run they left. An old
`?run=`/`?compare=` link (from before this redesign) resolves to the Runs
workspace rather than 404ing or landing on Fields with the parameter
silently dropped.

---

## 4. How Runs, Capture, and Proposals work now

**Runs (master-detail, PR-C).** The list shows compact rows: label, ordinal,
one-line condition summary, "N of M run fields," and override/exported/
save-state chips — all from the same response that filled the list, never a
second read. A row's entire header is the open control (`onFocusRun`,
pushing `?run=<id>`); there is no separate "Focus" button — it was removed
in PR-C's own review (finding I-3) because a `<button>` inside the row's
`<button>` was not reachable by keyboard without opening the row first.
Opening a run **replaces** the list with the one full editor; it cannot
collapse back to a summary in place (a fix-round finding: an in-editor
accordion could put the only open editor behind a header with nothing
beneath it). Leaving a run whose held text this build could not parse — via
Back, Previous, Next, or a workspace switch — opens a real
`aria-modal` confirmation with a focus trap; Escape means Stay.

**Capture & Proposals — transcript capture (PR-D).** The panel is a state
machine with exactly one primary action per state (Start Recording / Stop
Recording / Type What Was Said / Finalize and Read / Review N Proposals /
Try Again). Nothing in the collapsed header claims audio is saved or that a
value has been written — recording is introduced only inside the open Voice
Capture section, next to its own live seam-status line. Finalizing calls
`POST /experiments/{id}/transcript`, which mints one OPEN proposal per
candidate atomically with the stored note (same `record_lock` +
`_save_versioned` write, per PR-A) and returns both `proposals[]` (minted)
and `unproposable[]` (disclosed, never silently dropped).

**Ingestion Proposals — review (PR-D).** Open proposals list oldest-first
by default (the server's documented default, unchanged by this session); use
"Show Newest" or the order control to bring a just-arrived proposal into the
first window. Accept as Proposed and Reject stay top-level peers (Reject is
the single most common refusing act, reachable in one click); **Correct the
Value, Then Accept**, **Supersede…** and **Withdraw…** move behind one "More
Actions" disclosure that refuses to collapse while it holds an open form
(and says why) — two clicks, never zero, never hidden entirely, and none of
the three demoted in what the act means once reached. **Correct the Value,
Then Accept does NOT supersede or mint a new proposal** — measured over
HTTP in the real-second-browser proof
(`docs/evidence/two-actor-real-browser-proof-2026-09-03.md`, in the parallel
`ISAAC-wt-proof` worktree): it accepts the SAME proposal with a corrected
`accepted_value` (`accepted_from: 'edited'`). Supersede and Withdraw are
separate acts, distinct from a correction. Each proposal's scope
line reads `"On the record"` (record-scoped) or `"On run {label}"`
(run-scoped) — the run's **label**, not its id, except when two runs
currently loaded share a label, in which case the id is added as a `title`
+ `.sr-only` suffix for disambiguation (`.proposal-scope`,
`IngestionProposalsPanel.tsx`). A scientist's own finalize is suppressed from
being announced to themselves as a colleague's arrival (same-tab own-act
suppression, fail-closed, 30s TTL, tested).

**Unmapped Notes → direct proposal (PR-D).** "Propose a Value from This
Note" is the website's first caller of the direct `api.createProposal` path
(previously only the transcript-mint path could create one): target field
chosen from the server's own proposable-paths list, run required when the
target is run-scoped, a dedupe key from note + path + value digest, and a
412 path when the record has moved under the caller.

None of the above changes what an export or the official schema accepts —
accepting a proposal writes through the same manual-entry routes that
already existed; a proposal remains, per the ingestion-proposal contract,
"a suggestion awaiting a person's judgement... inert to export" until
accepted.

---

## 5. Assistant behaviour per width

| Width | Behaviour |
|---|---|
| Desktop (≥1025px) | Docked rail, default open, collapsible to a 44px labelled strip via **Collapse Assistant** (`aria-expanded`/`aria-controls`, remembered per browser). Never unmounted on collapse or on a workspace switch — a staged proposal or typed question survives both (pinned by an integration test asserting the same DOM node persists across a switch). Laptop band (1280×800) measured with zero main-column overflow; stays open by default there too. |
| ≤1024px | Existing slide-over drawer, opened by the "Assistant" trigger. The focus trap inside it was fixed this session: it previously trapped Tab focus ON the close button, never reaching the composer input, because the trap did not know to skip CSS-hidden controls made hidden by the new desktop collapse toggle — now ancestor-aware, proven in a real browser (`keyboard.spec.ts`). |
| All widths | The panel's copy names the current workspace ("You are on Runs."), reusing the same label `RecordWorkspaceNav`'s own pill row shows — one label, not two vocabularies for the same four destinations. |
| ≤1024px (spine) | The workflow spine becomes a single-row compact stepper of the same five server-derived steps (wraps 3+2 at ≤640px) — no re-derivation of workflow state; blocking reasons stay in the accessibility tree (visually hidden, not deleted). |

---

## 6. Premises from the session brief that proved false

Quoted from this session's own orchestration log
(`orchestration-plan.md` §"Premises from the prompt that proved false"),
verified again here rather than only trusted from the log:

1. **"`main` was `504c2ee`."** False — `git merge-base --is-ancestor 6ce3f5c
   origin/main` at session start confirmed `main` was `6ce3f5c` (v0.0.213),
   not `504c2ee`.
2. **"PR #219 is open."** False — #219 had already merged, as `f4ccfc2`
   (`gh pr view 219 --json state,mergeCommit` confirms `MERGED`).
3. **Test counts.** The brief's assumed baseline (7085 backend passed / 43
   skipped, 191 frontend files / 5074 tests) was stale; the measured baseline
   at session start was 7131/45 backend, 195 files / 5174 tests.
4. **"The five defects the prior session left open were closed by #221–#226."**
   **Partially true, not false outright** — worth stating precisely rather
   than collapsing to one verdict: four of the five gaps named in
   `docs/session-closure-2026-09-02.md` §7 were genuinely closed by
   #221–#226 (proven in `docs/session-closure-2026-09-02b.md` §2's table),
   and this session's own PR-B independently re-verified rather than assumed
   this — PR-B's body notes fixing the trusted-suite failures the re-merge
   surfaced, which is exactly the kind of adversarial re-check that would
   have caught a false "closed" claim. Where the premise was closer to
   overstated than false: `docs/session-closure-2026-09-02b.md` §6 itself
   lists real residues from that same arc that were NOT fully closed (the
   proposal-only bundle refetch, `RUN_LIST_LIMIT_MAX` duplication, feed
   poison-page semantics) — this session closed two of those three (see
   CLAUDE.md §11's new bullet), and the third (bundle refetch) remains open
   and undisputed.
5. **"Converting a transcript into a structured proposal is not possible
   today."** This premise was **TRUE**, not false, and is recorded here to
   correct the task instruction that grouped it with the false premises: at
   session start, no surface in the build could create a proposal at all
   (`docs/evidence/two-actor-workflow-proof-2026-09-02.md` §1) — PR-A's own
   body opens with exactly this measurement. PR-A is what made it false
   going forward, not evidence that the premise was already false at the
   start of the session.

---

## 7. Measurement-integrity findings

Four separate integrity issues surfaced this session, in test tooling and
review method rather than in application code:

1. **The `'4712'` substring flake (#232).** A pre-existing backend test,
   `test_two_edits_of_one_run_with_one_token_leave_exactly_the_winner`,
   asserted `'4712' not in json.dumps(state)` — a random hex generation
   nonce (measured collision rate ≈5.8×10⁻⁴ per nonce for the three sentinels) occasionally embedded
   those digits inside an unrelated identifier (`…9e66e7cd464712`) and failed
   the test on a correct outcome. It had already failed PR-C's own CI once.
   Fixed by replacing all fourteen substring assertions in the file with a
   leaf-walk over the *parsed* document (`_value_sites`: leaf equality,
   quoted-in-string, word-delimited numerics — never digits inside an
   identifier), each with a positive control and a guard test reproducing
   the exact CI document that had triggered it. Test-only; no production
   code changed. Quoted mutation controls from the PR body: loser value
   injected → red at the exact paths; undelimited pattern → guard red; walk
   returning `[]` → 12 red.
2. **The Impeccable mechanical detector runs DEGRADED in this environment.**
   Found independently by two reviewers (PR-D's and PR-E's), each by
   deliberately feeding it bad input and observing it return `[]` (exit 0)
   anyway — `htmlparser2`/`css-select`/`css-tree`/`domutils` are missing
   here. Both PR bodies record the same finding in near-identical words,
   which is itself informative: two independent reviewers hit the same wall
   rather than one reviewer's report being taken on faith. Consequence: every
   "0 findings" the detector reported this session (and, by the same logic,
   in any prior session that did not separately check this) carries no
   information — reviewers used the skill's playbooks and manual checks
   instead once the defect was found, and this document's Part 1 evidence
   (`docs/evidence/redesign-before-after-2026-09-03.md`) states the same
   caveat rather than silently relying on the detector.
3. **The trusted suite is the only end-to-end walk that exercises acceptance
   at all.** `apps/web/playwright.trusted.config.ts` (own backend, own
   workspace, `ISAAC_EDGE_TRUST_VERIFIER=test_fixture`) is the sole
   Playwright configuration where `POST .../proposals/{id}/review` succeeds;
   every other suite runs against a deployment with no trusted identity
   boundary, where acceptance answers `409 human_actor_required` by design.
   PR-C's initial CI run failed the trusted suite (`two-actor-workflow.spec.ts`
   :318, "master-detail: editor not open") — a real defect the redesign
   introduced, caught only because this suite exists and ran; a read-only or
   mutation-suite pass would not have caught it, because neither ever opens
   a run's editor through the compact-row click path under a trusted
   identity in the same way.
4. **`LAYOUT-05` was a probe artifact, not a real accessibility defect.**
   The narrow-width accessibility baseline had recorded the Assistant
   trigger as "clipped," because `findClippedText`'s containing-block walk
   treated every ancestor the same way — but a `position: fixed` element
   lays out against the viewport, not its nearest positioned ancestor, so an
   element correctly positioned relative to the viewport was flagged as
   clipped by an unrelated ancestor box. PR-E's fix checks six
   containing-block-establishing CSS properties before treating an element
   as clipped by an ancestor at all, each proven (per the PR body) to
   re-arm the walk; the baseline entry was **deleted, not narrowed**, because
   the underlying claim was never true.

---

## 7b. The two-actor real-browser proof (PR-F1, parallel worktree)

A separate slice (PR-F1, developed in
`/Users/krishverma/Documents/ISAAC-wt-proof`) produced
[`docs/evidence/two-actor-real-browser-proof-2026-09-03.md`](docs/evidence/two-actor-real-browser-proof-2026-09-03.md)
— merged to `main` as PR
[#235](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/235)
(`30ac611`), ahead of this document, so the link resolves — two real
Chromium browser contexts (not an HTTP client standing in for a second
actor) driving the actual UI through PR-A's and PR-D's new proposal
producers. Referenced here by path rather than duplicated, because it is not
this slice's own evidence. What it establishes, quoted rather than
re-derived:

- **The whole trusted suite (`playwright.trusted.config.ts`) passed 8/8,
  three separate times**: once before any mutation, once as a flakiness
  check, and once after every mutation below was applied, observed red, and
  reverted (`git checkout --`). The suite grew from 6 tests to 8 with this
  slice's own new spec.
- **Four mutations, each applied to production source, each reproduced
  red**: M1 (arrival-announcement firing on hydration, `IngestionProposalsPanel.tsx`),
  M2 (dropped `heading.focus()` on "Review N Proposals", `TranscriptCapturePanel.tsx`),
  M3 (removed the accept staleness gate, `routes.py`), M4 (an accepted
  run-field proposal writing the first run instead of the one it names,
  `routes.py`).
- **`PostgreSQL durability is CITED, not measured there`** — the proof's own
  words (§6/§9): its backend is filesystem-backed, and the durable claim
  rests on `apps/api/tests/test_proposal_durability.py`'s real-engine
  scenarios, which run in CI against a real `postgres:18`. Nothing in the
  real-browser proof itself touches PostgreSQL.

Three corrections that proof made to this document, folded into §4 and this
list above rather than left only in the proof doc: **Correct the Value,
Then Accept does not supersede or mint a new proposal** — it accepts the
same proposal with a corrected `accepted_value` (the proof's finding C-1);
**this build has no `Submit` control anywhere** — the finalizing act is
*Export Official Record + Sidecar* on the export screen, and on a
not-yet-ready record that control is **absent**, not disabled (findings
C-2/C-3, §3 step 10); and **`UnmappedNotesPanel` has no live refresh** —
notes minted by a finalize on the same screen appear only after a reload,
while the proposals from that same save appear live (finding F-1, §3 step 3
— added to the residue list below).

---

## 8. Remaining gates, grouped by owner

Copied structurally from `docs/session-closure-2026-09-02b.md` §6 (which
remains the authoritative external-gate list) and updated only where this
session's own work changed the picture — no gate below was closed by this
session, and no external authorization was sought or granted.

### Dean / operator / SLAC — unchanged by this session

- `0005_run_projection` approval and hosted application; any later
  migration.
- Gate **G2** (per-record hosted display) and **G3** (the five withheld
  aggregates).
- Production remote MCP and OAuth routing.
- The infrastructure half of trusted identity — until it exists, `accept`
  answers `409 human_actor_required` in every deployment, and
  `attribution.uploaded_by` stays unset. This session's own trusted-suite
  proofs (§7 item 3) run only under the deterministic fixture verifier,
  exactly as the prior session's did.
- Dean's **D1–D9** deferral is unchanged.

### Angel — unchanged by this session

- The six `system.configuration.*` fields remain `unclassified`. Nothing
  this session touched or inferred them, and nothing in the programme is
  blocked on the answer.

### Krish / authenticated human — unchanged in kind; new images added

- **`HOSTED QA PENDING` for every image `v0.0.214` and later** (this
  session's six PRs). `/krish` sits behind an Authentik edge this
  environment cannot authenticate to. Checklist:
  `docs/krish-manual-verification-checklist.md`, extended this session with
  a new §1b covering the four workspaces, Runs master-detail, the Assistant
  collapse control, and the compact narrow-width spine.
- The genuine browser **200%-zoom sign-off** — no CDP method, flag, or API
  can drive it; nothing in this session's evidence (§ below) should be read
  as that sign-off.
- Team Owner artifact review and private artifact sharing; a real Claude
  voice-plus-MCP smoke test.
- Personal Vercel and Railway retirement, preserving the Railway volume.
- **Subjective approval of the redesigned workflow** — this is new to this
  session and is the reason the before/after evidence bundle
  (`docs/evidence/redesign-before-after-2026-09-03.md`) exists: it is
  measurement, not a substitute for Krish's own judgement of whether the
  new IA is actually better to work in.

### Application-side residue — unchanged from the prior closure doc except where noted

See `CLAUDE.md` §11's new 2026-09-03 bullet for the full, precise list
(duplicated here only in summary to avoid the two documents drifting apart):
the proposal-only bundle-refetch residue is **still open**; the
`RUN_LIST_LIMIT_MAX`/`RUN_PAGE_MAX` drift and the feed's poison-page
semantics are **now closed and tested**, both by PR-A (#228); Export
Readiness's unbounded `/pending` per poll remains deliberate; `isaac_runs`
Stage 2b remains gated on the operator's completeness queries. **New this
pass, found by the real-second-browser proof (§7b, finding F-1):**
`UnmappedNotesPanel` has no live refresh — a note minted by a finalize on
the same Capture & Proposals screen appears only after a manual reload,
while the proposals minted by that same save appear live in Ingestion
Proposals. Not fixed here; named as residue.

---

## 9. CI resolution for the two runs that were pending at hand-off — BOTH NOW RESOLVED

At the time §1's table was first drafted, `51f4f40` (#232's merge) and
`ec945d7` (PR-D's merge, current `main` HEAD) both had CI runs still
executing. Re-checked repeatedly across three passes of this document; the
two runs did not resolve together, but both have now resolved, `success`,
and both have released images. Kept as two separate write-ups below (rather
than collapsed into one paragraph) because each pass's own re-check is part
of the record of how this was established, not asserted.

**`51f4f40` (#232) — RESOLVED, success, released as v0.0.218.**

```
$ gh run view 33837450907 --json status,conclusion
{"status":"completed","conclusion":"success"}
$ gh run view 33839970832 --log | grep -iE "commit under release|TAG=|gate ALLOWED"
commit under release: 51f4f4015bccbf176baa7d0784c5730ee73b09f7
release gate ALLOWED for 51f4f40…: all 1 required 'CI' run(s) for this
  commit concluded 'success'
TAG="v0.0.218"
$ git rev-list -n1 v0.0.218
51f4f4015bccbf176baa7d0784c5730ee73b09f7
```

**Corrected from an earlier pass of this document, which described the
gate mechanism wrong.** It is NOT true that the gate "resolves and releases
the oldest unreleased commit with a passing CI run" — that implies a queue
the workflow does not implement. The actual mechanism, read from
`origin/main:.github/workflows/build-push.yaml` (its own header, `:11-21`,
and the resolve step, `:108-119`): `build-push.yaml` triggers on
`workflow_run: [CI] completed` — i.e. it fires when a `CI` run finishes, not
on `push`, precisely so publishing is ordered after CI rather than racing it
(the file's own comment explains this replaced a race that once let an image
publish 33 minutes before the CI run that should have gated it concluded
`failure`). It then releases `github.event.workflow_run.head_sha` — **the
commit that workflow_run's own triggering CI run actually ran on**, not
`main`'s current tip. Run `33839970832` was triggered by **`51f4f40`'s own
CI run** (`33837450907`) concluding `success`; that is why it resolved and
released `51f4f40`, correctly. The workflow's own header names the exact
trap this document's earlier pass fell into: `github.sha` in a
`workflow_run` context reports the **default branch tip at trigger time**,
which is why `gh run list`'s summary view can show a `workflow_run`-family
run's `headSha` as `ec945d7` (the tip at the moment it fired) even though
the run's actual release target — resolved from
`github.event.workflow_run.head_sha` inside the job, not from the summary
field — was `51f4f40`. Nothing here was a queue; it was one CI run's
completion firing one release for that CI run's own commit.

**`ec945d7` (PR-D merge, current `main` HEAD) — RESOLVED, success, released
as v0.0.219.**

The status at the time an earlier pass of this document was drafted (quoted
here as history, not as current state):

```
$ gh run view 33837767977 --json status,conclusion   # AS OF THAT EARLIER PASS
{"status":"in_progress","conclusion":""}
```

Re-checked in a later pass and now resolved:

```
$ gh run view 33837767977 --json status,conclusion
{"status":"completed","conclusion":"success"}
$ gh run view 33842289349 --log | grep -aE "commit under release|release gate|TAG="
commit under release: ec945d75e21b64cf6138a9ec09199c413deae692
release gate ALLOWED for ec945d75e21b64cf6138a9ec09199c413deae692: all 1
  required 'CI' run(s) for this commit concluded 'success'
TAG="v0.0.219"
$ git fetch --tags && git rev-list -n1 v0.0.219
ec945d75e21b64cf6138a9ec09199c413deae692
```

This confirms the mechanism corrected earlier in this section, exactly as
predicted: `ec945d7`'s own CI run concluding `success` fired
`build-push.yaml` as run `33842289349`, which resolved
`github.event.workflow_run.head_sha` to `ec945d7` itself (not the branch
tip at trigger time — by this point `ec945d7` WAS the tip, so the two
happened to coincide, but the resolution is still via the triggering CI
run's own commit, not an assumption that the tip is always right) and
released it as **v0.0.219**.

**All six PRs of this session (#228–#233, plus #232) are now merged AND
released** — images v0.0.214 through v0.0.219. Nothing in this document
remains "unresolved" for the release status of this session's own work.
The only CI status this document does not track to a conclusion is PR
#235's own (the real-second-browser proof, §7b/§1) — that PR is not this
session's own subject matter and its release status is not repeated here.

---

## 10. Ready-to-send stakeholder messages

Drafted from `/private/tmp/.../scratchpad/stakeholder-messages-draft.md`,
refined with the real SHAs/tags from §1. Not sent by this session — sending
is Krish's act, per this repository's standing rule that an agent does not
act as Krish, Dean, or Angel.

### To Dean (operator / infrastructure)

> **Subject: ISAAC — nothing new needed from you; status of the items you own**
>
> Dean — this week's ISAAC changes are application-side only (record screen
> reorganised into four workspaces, transcript capture now stores proposals
> durably, Runs rebuilt as master-detail, Assistant panel made responsive).
> Nothing touched the hosted database, `isaac-k8`, Authentik, or any
> migration. The items that remain yours are unchanged:
> - `0005_run_projection` approval and hosted application (packet:
>   `docs/migration-approval-packet-0005.md`; the two completeness queries
>   in §8A gate Stage 2b).
> - Gates G2 (per-record hosted display) and G3 (the five withheld
>   aggregates).
> - The trusted-identity boundary: hosted proposal acceptance still answers
>   409 `human_actor_required` by design until a trusted edge exists; every
>   acceptance proof in the repo runs under the fixture verifier only.
> - Production MCP/OAuth routing and the infrastructure half of D1–D9
>   (still deferred, as you asked).
>
> No action is requested now. If you want to see the new screens before the
> next hosted QA: images `v0.0.214` (`a342175`) through `v0.0.219`
> (`ec945d7`) carry all six PRs — #228/#229/#230/#233/#232/#231. A seventh,
> related PR (#235, the real-second-browser proof — test/doc-only, no
> product-screen change) has also merged and releases its own image on the
> same mechanism once its CI concludes. See
> `docs/session-closure-2026-09-03.md` §1/§9 for exact SHAs and tags.

### To Angel (scientific classification)

> **Subject: ISAAC — six `system.configuration.*` fields still unclassified; nothing blocked on it**
>
> Angel — the six `system.configuration.*` fields remain `unclassified` in
> ISAAC, and this week's work deliberately did not touch or infer them (they
> are the only run-level fields no route accepts). Nothing in the programme
> is blocked on your answer; when you have time, the question list is
> `docs/angel-scope-questions-2026-08-25.md`. No action needed otherwise.

### To Krish (owner)

> **Subject: ISAAC redesign shipped to main — your gates**
>
> Krish — the record-screen redesign is on `main`. Six PRs merged
> (#228–#233, plus #232); images `v0.0.214`–`v0.0.219` are all released and
> together carry every one of them (`ec945d7`, `v0.0.219`, is the current
> `main` HEAD as this was written). A seventh, related PR (#235 — the
> real-second-browser proof, test/doc-only) has also merged and will release
> its own image once its CI concludes; nothing in it changes a product
> screen. What only you can do:
> 1. Hosted QA behind Authentik for the new images — checklist:
>    `docs/krish-manual-verification-checklist.md` §1b covers the four new
>    workspaces (Record Fields / Runs / Capture & Proposals / Graph), Runs
>    master-detail, the Assistant collapse control, and the compact
>    narrow-width spine.
> 2. The genuine 200% browser-zoom sign-off (no automation can drive real
>    zoom).
> 3. Team Owner review of the Claude companion artifact and a real
>    voice-plus-MCP smoke test.
> 4. Personal Vercel/Railway retirement (preserve the Railway volume).
> 5. Your own judgement of the redesigned workflow — the measured
>    before/after evidence is in
>    `docs/evidence/redesign-before-after-2026-09-03.md`, but it is
>    measurement, not a substitute for your read of whether the new IA is
>    actually better to work in.

---

## 11. Verification run in this closure slice

Every command below was re-run against the working tree AFTER the review
fix pass (i.e. it covers this document, `CLAUDE.md`, and
`docs/krish-manual-verification-checklist.md` in their final, corrected
state, not the pre-review draft):

```
$ .venv/bin/python scripts/build_memory_snapshot.py \
    --graph-dir /Users/krishverma/Documents/ISAAC/graphify-out \
    --out apps/api/isaac_api/data/memory-snapshot.json \
    --detail-out apps/api/isaac_api/data/memory-graph-detail.json --check
error: snapshot is stale/drifted relative to apps/api/isaac_api/data/memory-snapshot.json
ok: apps/api/isaac_api/data/memory-graph-detail.json matches regenerated graph detail (no drift)
# exit 6 — regenerated (same command without --check), then re-checked:
ok: apps/api/isaac_api/data/memory-snapshot.json matches regenerated snapshot (no drift)
ok: apps/api/isaac_api/data/memory-graph-detail.json matches regenerated graph detail (no drift)
# exit 0

$ .venv/bin/python -m pytest apps/api/tests/test_committed_snapshot.py \
    apps/api/tests/test_memory_graph_detail.py -q -rs
154 passed, 1 skipped, 1 warning in 5.19s
SKIPPED [1] apps/api/tests/test_memory_graph_detail.py:1568: graphify-out/graph.json
  is absent (it is gitignored, so it is never present in CI)
# This IS expected here, and is not "the main checkout should run clean" —
# an earlier pass of this document said that and was WRONG. This checkout
# is the WORKTREE `/Users/krishverma/Documents/ISAAC-wt-closure`, not the
# main checkout: `ls graphify-out/` in this tree returns "No such file or
# directory" (it is gitignored, so it is absent from every worktree — only
# the main checkout `/Users/krishverma/Documents/ISAAC` has it, per
# CLAUDE.md §11's own "any backend skip count measured in a git WORKTREE"
# entry). Re-run from the main checkout to see whether this specific skip
# clears there; do not assume it does without re-running.

$ .venv/bin/python -m pytest tests/test_validator_qa_package.py \
    apps/api/tests/test_run_page_bound_parity.py \
    apps/api/tests/test_submission_store.py -q
93 passed, 1 warning in 1.25s
```

Docs-guard tests were found with
`grep -rln "CLAUDE.md\|session-closure" apps/api/tests tests`, narrowed to
the three files above that actually parse committed prose as text (the
others merely cite a section number in a comment).

This document, `docs/evidence/redesign-before-after-2026-09-03.md`,
`docs/krish-manual-verification-checklist.md`, and `CLAUDE.md` were all
edited only in the `docs/session-closure-2026-09-03` worktree
(`/Users/krishverma/Documents/ISAAC-wt-closure`) and are left uncommitted
per this slice's instructions.
