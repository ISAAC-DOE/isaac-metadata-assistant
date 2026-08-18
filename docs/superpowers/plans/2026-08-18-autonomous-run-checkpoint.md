# Autonomous run checkpoint — 2026-08-18

**Why this file exists.** The run was interrupted by an external boundary, not by a design
problem: **the organisation's monthly API spend limit was reached**, and six subagents were
terminated mid-task by the platform. `CLAUDE.md` §16 and the run's own stop policy require a
precise recovery record so the next session resumes from verified facts instead of an audit.

Everything below was **measured in this session**. Nothing is carried forward from prose.

---

## 1. The blocker, stated plainly

```
Agent terminated early due to an API error:
You've hit your org's monthly spend limit · run /usage-credits to ask your admin for a higher limit
```

**This is Krish's to resolve** (raise the limit, or wait for the monthly reset). It is not
something an agent can work around, and it is the reason the remaining roadmap is unstarted
rather than abandoned.

**What it terminated, mid-task:**

| Agent | State when killed |
|---|---|
| Conflict-resolution backend implementation | model layer written (~1000 lines), **no routes, no tests** — preserved, see §4 |
| Independent review of PR #157 | **mid-investigation**, last words: *"This is a significant finding. Let me determine the cause with a standalone probe."* |
| Scientific-truthfulness sweep + 4 sub-sweeps | partial; two sub-audits DID complete and their findings are in §5 |

---

## 2. Verified repository state

Measured with `git`, `gh`, and the test suites at the times stated.

- **`origin/main` = `068e4be`** — *Merge pull request #158*. Local `main` matches; tree clean.
- Session started at `81ab3a1`, fast-forwarded to `fe374c0` (17 commits behind), and `main`
  has since advanced by the #158 merge.

### Merged this session

| PR | Merge commit | What |
|---|---|---|
| **#158** | `068e4be` | Owner's `0003`/`0004` approval recorded; a test that required a false claim corrected; an overstated constraint-coverage figure scoped and mechanically guarded |

### Open, and exactly why each is open

| PR | Head | CI | Blocking reason |
|---|---|---|---|
| **#156** Run removal | `9d4788d` | re-running at this head | Review COMPLETE, all findings fixed. Was waiting only on the ~25-min browser job when the session ended. **Merge when green — no outstanding work.** |
| **#157** Visual sweep | `b847a21` | **all five green** | **DELIBERATELY NOT MERGED.** Its independent review was killed mid-investigation having announced a significant finding. Green CI is not a substitute for the review this repository's history says is necessary. **Re-run the review before merging.** |

### Branch pushed with NO pull request, on purpose

**`feat/conflict-resolution`** — see §4. Incomplete. Do not merge.

---

## 3. Measurements taken (quote these, do not re-derive)

| Thing | Value | Where measured |
|---|---|---|
| Backend suite, `main` + #158 | **4590 passed / 25 skipped** | local `pytest -q` |
| Backend suite, #156 head | **4625 passed / 28 skipped** | local `pytest -q` |
| Frontend suite, #156 head | **4027 passed / 153 files** | `npx vitest run` |
| `tsc -b`, #156 head | exit 0 | — |
| e2e typecheck | exit 0 | `tsc -p e2e/tsconfig.json` |
| a11y aggregate invariant | **34 passed** incl. the merge-collision negative control | `baseline-aggregate.invariant.test.ts` |
| OpenAPI operations, #156 head | **64** ops / **74,091** chars / **162** post-lead paragraphs | measured three independent ways that agree |
| Constraints declared by `0003`+`0004` | **46**, of which CI blames **27** | now guarded by a test |
| Snapshot + deep-graph drift | clean on every branch touched | `--check` with `--detail-out` |

**`main` is UNPROTECTED** — `branches/main.protected` = `false`, `rulesets` = `0`. CI reports,
it does not block. Every merge this session verified the exact head by hand for that reason.

---

## 4. `feat/conflict-resolution` — what is there and what is missing

Preserved so ~1000 lines are not stranded in a temp worktree; **pushed without a PR so it
cannot be mistaken for finished work.** Verified green at its tip (backend 4586 / 27 skipped).

**Present:** `apps/api/isaac_api/conflict_resolution.py` — frozen `ConflictResolution` record,
append-only transition history, closed vocabularies, staleness states, and a
`competing_digest` so a resolution superseded by new evidence is *detectable* rather than
silently still-resolved. Plus a `resolved` review state in `provenance.py` and wiring in
`evidence_classify.py` / `submissions.py`.

**Missing — the honest list:**

- **No routes.** `GET /api/experiments/{id}/conflicts` and `POST .../conflicts/resolve` do not
  exist. The feature is unreachable, so **the motivating defect is NOT fixed** (see §5, C-A).
- **No `test_conflict_resolution.py`.** None of the fourteen required scenarios.
- **No independent review.** Every other slice this session had one.
- **No frontend** (always a separate slice, by design).
- Landing the routes moves the OpenAPI count; the frontend counters must be **re-measured**,
  never delta-arithmetic'd.

One real defect was found and fixed in this state: the new module spelled an edge identity
header out in a comment and tripped `test_no_backend_module_names_an_identity_header`. The
comment was reworded rather than the guard loosened — bluntness is why that guard works.

---

## 5. Audit findings from THIS session that are not yet fixed

Two audits completed before the spend limit hit. **These are unfixed and are the best-evidenced
work waiting to be done.** Each was cited to `file:line` by the auditor.

### Critical

- **C-A — a scientist who fixes a typo owns a permanent, unclearable conflict.**
  `evidence_classify.py:172` flags a field the moment two distinct non-null `answer`s exist;
  every write path *appends* a `user_confirmation` and **no route in the application removes an
  evidence entry**. So answering, noticing a typo, and answering again manufactures a conflict
  with **no surface that can clear it**. `submissions.py:29-38` already states this in prose.
  **This is what `feat/conflict-resolution` exists to fix.**
- **C-B — a FAILED pipeline step renders a success check mark.** `adapt.ts:733` maps a step the
  server reported `ok: false` to `'current'`; `StagedRunner.tsx:37` collapses `'current'` into
  `'done'`; `:41` renders the `Check` glyph. The failure signal is computed and then discarded.
  Latent with today's fixtures; the amber treatment it used to have was removed with a dead-CTA
  branch and the tick was left behind.
- **C-C — Record Verification paints three green cards for a corpus that was not evaluated.**
  `RecordVerification.tsx:694/700/706` use `=== 0` for tone with **no zero-denominator guard**,
  and `verification.py:438-445` silently returns `()` for a missing directory and `continue`s a
  file that will not parse. A run that validated nothing reads as three passes.
  `StatisticsPage.tsx:1209-1212` does this correctly two files away.
- **C-D — "Your input is kept" sits beside a Refresh button that destroys it**, and one variant
  *instructs* the reader to press it. `GuidedCompletion.tsx:489/515/837`; `reload` sets
  `{status:'loading'}` (`useFetch.ts:47`), unmounting `GuidedPrompt` and its local `text`.
- **C-E — an assistant message containing a digest or a path loses its ENTIRE text on archive**,
  leaving a blank "You" bubble. `assistantSession.ts:118` drops the key when
  `isUnsafeString` fires; Settings promises the transcript "survives a page reload"
  (`settingsContent.ts:351`). "Stripped" is whole-message deletion, not redaction.

### Important (abridged — full detail is in this session's transcript)

Switching the Record Fields ↔ Graph tab unmounts every unsaved textarea on the record screen
(`RecordWorkbench.tsx:426`), and two comments promise the opposite; a 412 on a note review is an
unrecoverable dead end whose only exit destroys the typed correction
(`UnmappedNotesPanel.tsx:227-247`, same shape in `AssetReferencesPanel.tsx:288-334`); re-opening
"Edit wording" silently replaces a typed correction (`:651`); the asset form's open/close toggle
is its own destroyer (`:399`); a pasted description is silently truncated at 1000 chars where the
server would have refused loudly (`ExperimentsHome.tsx:811`); reserved pass-green is used for
non-verdict states in `GuidedCompletion.tsx:675` and `LoadMaterials.tsx:326`.

### A pre-existing a11y drift, measured twice

`settings-explorer@zoom-200` `darwin: 59` is **stale on `main`** — a local macOS run measures
**61**, and measures 61 with this session's changes absent. Invisible because CI runs only linux.
**Deliberately left uncorrected** rather than absorbed into an unrelated run-removal diff; the
entry says so in place. It needs its own slice, and correcting it moves the darwin total, which
is the one number in that file that makes a debt increase visible.

---

## 6. Exact next executable actions, in order

1. **Merge #156** once its browser job is green at `9d4788d`. Nothing else is outstanding on it.
2. **Re-run the independent review of #157** and find out what the killed reviewer had found.
   Do not merge it on green CI alone.
3. **Finish `feat/conflict-resolution`**: routes, the fourteen tests, independent review. This
   closes C-A.
4. Fix **C-B** and **C-C** (both small, both honesty defects behind green suites).
5. Fix **C-D** and **C-E** (scientist input destroyed by controls that promise the opposite).
6. Then the unstarted roadmap: `isaac_runs` Stage 2 — **note** that `CLAUDE.md` §15 says making
   it a read source is NOT covered by any committed sentence, so that slice must record its
   authorization basis and amend §15, exactly as the `isaac_runs` and submission-table slices
   did. Its real blocker is measured and recorded: **no completeness marker and no backfill**,
   so a read cutover cannot distinguish "zero runs" from "never projected", and rows only appear
   on a subsequent save.

## 7. Housekeeping done

An orphaned vite dev server was holding port 5173 from the terminated #157 reviewer, serving a
**different worktree**. `reuseExistingServer` would have adopted it and produced an
authoritative-looking measurement against the wrong tree. Identified by its cwd and cleared.
Worktrees are otherwise intact; nothing was deleted.
