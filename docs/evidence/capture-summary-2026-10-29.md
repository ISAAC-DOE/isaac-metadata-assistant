# `capture_summary` on the record detail payload — evidence, 2026-10-29

Branch `wip/capture`, base `83764392`.

## The premise was stale: this had already been built

CLAUDE.md §11 (the "Named rather than implied, and still not done" paragraph)
still names "a `capture_summary` on the record detail payload, which would delete
`useCaptureSummary.ts`" as residue. **It shipped on 2026-09-11 in `a8a69733`**
(*"fix(capture): a permanent spinner, …"*), which is an ancestor of this branch:

- `apps/api/isaac_api/routes.py` — `_capture_summary(exp)` (three integers:
  `notes_total`, `proposals_open`, `unreadable_entries`), served by `_detail` from
  lists already in memory, and sharing one expression per count with the two list
  routes (`_notes_total`, `_proposal_state_counts`, `_unreadable_*_count`). No
  re-read and nothing memoised on the instance.
- `apps/web/src/lib/useCaptureSummary.ts` — deleted. `RecordWorkbench` reads
  `detail.capture_summary` (withheld on `?view=proposals`, where the panels state
  their own counts).
- `apps/api/tests/test_capture_summary_on_detail.py` — parity with both list
  routes, no-extra-work spies, an A/B with the block stubbed out, and a
  one-expression source guard.

CLAUDE.md was **not** edited, as instructed. The residue sentence needs striking
by whoever owns that file.

## What this slice added (tests only, no production change)

Two claims were left to comments rather than tests:

1. **No list read on every workspace.** Only `?view=fields` was pinned.
2. **Live truthfulness.** The deleted hook re-read both lists when the feed's
   `note`/`proposal` positions moved. The bundle-borne count moves only when the
   bundle refetches, and `needsCanonicalRefetch` refetches nothing for a
   proposal-only feed summary. So "the bundle refetch already covers it" has
   three paths:
   - a `note` feed entry lands in `otherKinds`, so the **feed** refetches;
   - a proposal act moves the record's ETag, so the **record poller** refetches;
   - a proposal-only feed page, with the record poller not yet caught up,
     refetches **nothing**. The count lags by up to one record-poll interval
     (`POLL_INTERVAL_MS` = 8 s) and is then correct. That lag is pinned in a test
     rather than hidden.

Files:

- `apps/web/src/__tests__/capture-summary-request-graph.test.tsx` (new, 9 tests)
- `apps/api/tests/test_capture_summary_on_detail.py`: added
  `test_every_capture_write_that_moves_the_summary_also_moves_the_detail_etag`,
  which covers the server half of path 2 across capture, a second capture,
  propose/reject, propose/withdraw, propose/supersede and dismiss.

## Request counts per workspace (jsdom, fetch stub; exact counts, no bytes)

**Before** was measured on this tree by restoring the deleted hook
(`git show a8a69733^:apps/web/src/lib/useCaptureSummary.ts`) and wiring it back
into `RecordWorkbench`, with its workspace gate moved to `proposals` to match
today's layout. Both runs then used the same harness. **Feed step** means one
forward change-feed page `[experiment, note]` with the record poller held, and
the count excludes `/changes` itself.

| workspace | first paint, before → after | list reads at first paint | feed step, before → after | list reads per step |
|---|---|---|---|---|
| `fields`    | 17 → 15 | 2 → 0 | 15 → 13 | 2 → 0 |
| `runs`      | 15 → 13 | 2 → 0 | 16 → 14 | 2 → 0 |
| `graph`     | 20 → 18 | 2 → 0 | 15 → 13 | 2 → 0 |
| `capture`   | 13 → 11 | 2 → 0 | 15 → 13 | 2 → 0 |
| `activity`  | 14 → 12 | 2 → 0 | 15 → 13 | 2 → 0 |
| `proposals` | 15 → 15 | 3 → 3 (panel-owned) | 14 → 14 | 1 → 1 (panel) |

On `proposals`, the three reads all belong to panels: `IngestionProposalsPanel`
reads `GET …/proposals`, and `UnmappedNotesPanel` reads `GET …/notes` plus
`GET …/proposals?limit=1`. The last one fetches proposal *capabilities*, not
counts. The original commit recorded `?view=fields`/`runs` 27 → 23, `graph`
39 → 35 and a feed step 18 → 16 under a different harness and a four-workspace
layout. Those numbers are not comparable to this table.

The documented-operations count is unchanged at **101** because no route was
added (`test_about_and_openapi.py`, 37 passed).

## Mutations (each applied, run, reverted)

| mutation | result |
|---|---|
| A. restore the old hook in `RecordWorkbench` | 8 RED: 5 workspace tests and 3 live tests. The proposals control stays green |
| B. freeze `captureSummary` at first paint (`useRef`) | 3 RED, the live tests |
| C. drop `otherKinds` from `needsCanonicalRefetch` | 1 RED, the `note` live test |
| D. `Experiment.etag()` constant once a proposal exists | 1 RED, the new backend test only |
| E. drop proposals from `_authoritative_signature` | 6 RED, but at the summary assertion: the write never persists |

## Commands

```bash
WT=<worktree>
cd $WT && PYTHONPATH=$WT/src:$WT/apps/api <venv>/bin/python -m pytest -q -p no:cacheprovider \
  apps/api/tests/test_capture_summary_on_detail.py \
  apps/api/tests/test_detail_route_composes_each_run_once.py \
  apps/api/tests/test_ingestion_proposals.py            # 214 passed
cd $WT && PYTHONPATH=... pytest -q -p no:cacheprovider apps/api/tests/test_about_and_openapi.py  # 37 passed
cd $WT/apps/web && npx vitest run \
  src/__tests__/capture-summary-request-graph.test.tsx \
  src/__tests__/record-capture-destination.test.tsx \
  src/__tests__/live-refresh-request-graph.test.tsx \
  src/__tests__/notes-live-refresh-integration.test.tsx \
  src/__tests__/record-workspaces.test.tsx              # 5 files, 68 passed
cd $WT/apps/web && npx tsc -b                           # exit 0
```

The measurement harness that produced the table was a temporary vitest file. It
is not committed, and it reused this file's `detailRoute`/`feedPage` helpers with
a per-view loop.
