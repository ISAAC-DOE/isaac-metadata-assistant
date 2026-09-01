/*
 * THE CHANGE FEED IS ACTUALLY MOUNTED — which, until this slice, it was not.
 *
 * `useChangeFeed` was defined and tested and referenced by NO application screen:
 * `grep -ral useChangeFeed apps/web/src` returned its own definition and its own test
 * and nothing else. A poller nothing mounts is a poller that cannot be wrong, so the
 * hook's own suite could be green while the product had no live updating at all.
 *
 * These tests are about the MOUNT: that it starts for a record and stops without one,
 * that what it learns reaches the screen as a SELECTIVE refresh of a canonical read,
 * that a failing server produces backoff rather than a storm, and — the one that
 * matters most — that nothing on this path writes.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { api } from '../lib/api';
import { useRecordSession } from '../lib/useRecordSession';
import { POLL_INTERVAL_MS, POLL_MAX_BACKOFF_MS, DEGRADED_THRESHOLD } from '../lib/useRecordSync';
import { clearAllSessions } from '../lib/assistantSession';
import { needsCanonicalRefetch, type RecordChangeSummary } from '../lib/recordChanges';
import {
  EXP_ID,
  experimentDetail,
  pendingResponse,
  evidenceClassificationResponse,
} from '../test/apiFixtures';
import type { ApiChangeEntry, ApiChangeFeedPage, ApiExperimentDetail } from '../lib/types';

const DETAIL = experimentDetail as unknown as ApiExperimentDetail;
/** The rev this view holds, derived exactly as `useRecordSession` derives it. */
const KNOWN_REV = Number(DETAIL.version.split('.').pop());

function page(over: Partial<ApiChangeFeedPage> = {}): ApiChangeFeedPage {
  return {
    changes: [],
    next_cursor: 'CURSOR-0',
    has_more: false,
    limit: 50,
    returned: 0,
    remaining: 0,
    kinds: ['experiment', 'proposal', 'run'],
    ...over,
  };
}

const laterRun = (id = '01RUN0000000000000000000AA'): ApiChangeEntry => ({
  kind: 'run',
  entity_id: id,
  changed_at_rev: KNOWN_REV + 1,
  version: `gen.${KNOWN_REV + 1}`,
  rev: KNOWN_REV + 1,
  generation: 'gen',
  updated_utc: '2026-08-30T12:00:00Z',
});

const laterProposal = (id = '01SYNTHETICPROPOSALPROPOS'): ApiChangeEntry => ({
  kind: 'proposal',
  entity_id: id,
  changed_at_rev: KNOWN_REV + 1,
  updated_utc: '2026-08-30T12:00:00Z',
  state: 'open',
});

/** Flush the extras `Promise.all` under fake timers. */
async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe('the change feed, mounted on the record-session owner', () => {
  beforeEach(() => {
    clearAllSessions();
    vi.useFakeTimers();
    // Jitter pinned so a scheduled delay is exactly the interval.
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    vi.spyOn(api, 'getPendingPage').mockResolvedValue({
      pending: pendingResponse.pending,
    } as never);
    vi.spyOn(api, 'getEvidenceClassification').mockResolvedValue(
      evidenceClassificationResponse as never,
    );
    vi.spyOn(api, 'checkRecordVersion').mockResolvedValue({ changed: false });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    clearAllSessions();
  });

  it('starts polling the feed once a record screen has a record to poll for', async () => {
    const spy = vi.spyOn(api, 'getChanges').mockResolvedValue(page());
    renderHook(() => useRecordSession(EXP_ID, { detail: DETAIL }));
    await flush();

    expect(spy).not.toHaveBeenCalled(); // nothing before the first cadence tick
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy.mock.calls[0][0]).toBe(EXP_ID);
  });

  it('does NOT poll while the screen has no target — no detail, or disabled', async () => {
    const spy = vi.spyOn(api, 'getChanges').mockResolvedValue(page());

    // A screen whose bundle has not arrived: `active` is false, so nothing polls.
    const bare = renderHook(() => useRecordSession(EXP_ID, { detail: undefined }));
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);
    });
    expect(spy).not.toHaveBeenCalled();
    bare.unmount();

    // A screen that has switched the session off.
    const off = renderHook(() => useRecordSession(EXP_ID, { detail: DETAIL, enabled: false }));
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);
    });
    expect(spy).not.toHaveBeenCalled();
    off.unmount();
  });

  it('stops polling on unmount', async () => {
    const spy = vi.spyOn(api, 'getChanges').mockResolvedValue(page());
    const { unmount } = renderHook(() => useRecordSession(EXP_ID, { detail: DETAIL }));
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy).toHaveBeenCalledTimes(1);

    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 5);
    });
    expect(spy).toHaveBeenCalledTimes(1); // not one more
  });

  it('resumes from the cursor the server issued, never one it built itself', async () => {
    const spy = vi
      .spyOn(api, 'getChanges')
      .mockResolvedValueOnce(page({ next_cursor: 'SERVER-A' }))
      .mockResolvedValue(page({ next_cursor: 'SERVER-B' }));
    renderHook(() => useRecordSession(EXP_ID, { detail: DETAIL }));
    await flush();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy.mock.calls[0][1]).toEqual({ cursor: undefined });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy.mock.calls[1][1]).toEqual({ cursor: 'SERVER-A' });
  });

  it('says nothing at all when every entry is at or below the revision on screen', async () => {
    /*
     * The first poll carries no cursor and so returns the whole record. A mount that
     * announced that would tell every scientist their record had changed elsewhere.
     *
     * THIS TEST USED TO PASS WITH THE POLLER ENTIRELY DISABLED. It asserted only two
     * absences — no callback, no `activity` — and never that `getChanges` was called,
     * so `enabled: false` on the `useChangeFeed` mount satisfied it: a build with no
     * live updating at all read exactly like a build whose filter works. That is the
     * same defect class the sibling `change-feed-preserves-unsaved-input.test.tsx`
     * found in its own harness (fake timers installed after `render`) and fixed there;
     * this file was not swept for it.
     *
     * TWO THINGS CLOSE IT, and the second is the one that matters. The poll is
     * asserted to have happened — and then the SAME harness is shown to announce when
     * the entries are moved above the floor. Without that positive control, "the poll
     * happened" still would not prove the response was applied; with it, the silence
     * above is attributable to the filter and to nothing else.
     */
    const onEntitiesChanged = vi.fn();
    const spy = vi.spyOn(api, 'getChanges').mockResolvedValue(
      page({
        changes: [
          { ...laterRun(), changed_at_rev: KNOWN_REV },
          { kind: 'experiment', entity_id: EXP_ID, changed_at_rev: KNOWN_REV },
        ],
        returned: 2,
      }),
    );
    const { result } = renderHook(() =>
      useRecordSession(EXP_ID, { detail: DETAIL, onEntitiesChanged }),
    );
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });

    expect(spy).toHaveBeenCalledTimes(1); // the poll really happened
    expect(onEntitiesChanged).not.toHaveBeenCalled();
    expect(result.current.activity).toBeNull();

    // THE POSITIVE CONTROL, in the same test and the same harness: move the entries
    // one revision above the floor and the identical setup DOES announce. So the
    // silence above is the filter's, not a dead poller's.
    spy.mockResolvedValue(page({ changes: [laterRun()], returned: 1 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(onEntitiesChanged).toHaveBeenCalledTimes(1);
    expect(result.current.activity).not.toBeNull();
  });

  it('raises the summary and calls the screen back when something IS newer', async () => {
    const onEntitiesChanged = vi.fn();
    vi.spyOn(api, 'getChanges').mockResolvedValue(
      page({ changes: [laterRun(), laterProposal()], returned: 2 }),
    );
    const { result } = renderHook(() =>
      useRecordSession(EXP_ID, { detail: DETAIL, onEntitiesChanged }),
    );
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });

    expect(onEntitiesChanged).toHaveBeenCalledTimes(1);
    const summary = onEntitiesChanged.mock.calls[0][0];
    expect(summary.runIds).toEqual(['01RUN0000000000000000000AA']);
    expect(summary.proposalIds).toEqual(['01SYNTHETICPROPOSALPROPOS']);
    expect(result.current.activity).not.toBeNull();
  });

  it('lets a screen take a TARGETED refresh: a proposal-only page refetches nothing', async () => {
    /*
     * THE SELECTIVITY, ASSERTED AT THE SEAM THE SCREENS USE. The three read-only
     * screens gate `reloadSilent()` on `recordMoved || runIds.length || otherKinds.length`,
     * so a page carrying ONLY proposal ids announces and refetches nothing.
     *
     * Stated honestly: in this build a proposal act ALSO moves the record's own entry
     * (`workspace._authoritative_signature` hashes proposals), so the common path does
     * refetch. This branch is reachable through the feed's contract — the server may
     * serve any combination, and a page boundary can split one save across two pages —
     * and that is what is exercised here. It is not claimed to be the common case.
     */
    const reloadSilent = vi.fn();
    const gate = (s: RecordChangeSummary) => {
      if (needsCanonicalRefetch(s)) reloadSilent();
    };
    vi.spyOn(api, 'getChanges').mockResolvedValue(
      page({ changes: [laterProposal()], returned: 1 }),
    );
    const { result } = renderHook(() =>
      useRecordSession(EXP_ID, { detail: DETAIL, onEntitiesChanged: gate }),
    );
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });

    expect(reloadSilent).not.toHaveBeenCalled(); // announced, not refetched
    expect(result.current.activity!.proposalIds).toEqual(['01SYNTHETICPROPOSALPROPOS']);
  });

  it('and a page naming a run DOES refetch that screen’s canonical read', async () => {
    const reloadSilent = vi.fn();
    const gate = (s: RecordChangeSummary) => {
      if (needsCanonicalRefetch(s)) reloadSilent();
    };
    vi.spyOn(api, 'getChanges').mockResolvedValue(page({ changes: [laterRun()], returned: 1 }));
    renderHook(() => useRecordSession(EXP_ID, { detail: DETAIL, onEntitiesChanged: gate }));
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(reloadSilent).toHaveBeenCalledTimes(1);
  });

  it('NEVER writes: not one mutating client method is reachable from a change event', async () => {
    /*
     * THE ANTI-LOOP GUARANTEE, ASSERTED STRUCTURALLY RATHER THAN BY TIMING.
     *
     * The worry is a save that triggers a feed entry that triggers a save. It cannot
     * happen here because there is no second edge: nothing on this path writes. That
     * is a stronger property than "the filter suppresses my own rev", and it is the
     * one asserted, because the filter has a race window (a write whose response has
     * not yet been adopted) and this does not.
     *
     * AND IT USED TO PROVE THAT NO WRITE HAPPENS WHEN NOTHING HAPPENS. The first
     * version asserted only the absence of writes: it passed with the change-feed
     * poller mounted `enabled: false`, i.e. on a build where no poll ever resolved and
     * no change event ever arrived — the vacuous reading of a guarantee whose own
     * docstring calls it "asserted structurally". A guarantee about what a change
     * event cannot do is worth nothing until a change event has arrived, so the
     * arrival is now asserted first, three ways: the request was made, the screen's
     * callback fired with the ids, and the notice is standing. THEN no write.
     */
    const writeNames = [
      'submitAnswer',
      'editField',
      'exportRecord',
      'setOverride',
      'reviewNote',
      'patchRun',
      'renameExperiment',
      'discardExperiment',
      'resolveConflict',
    ] as const;
    const writeSpies = writeNames
      .filter((n) => typeof (api as unknown as Record<string, unknown>)[n] === 'function')
      .map((n) => vi.spyOn(api as never, n as never).mockResolvedValue({} as never));
    expect(writeSpies.length).toBeGreaterThan(0); // the sweep is not vacuous

    const changes = vi
      .spyOn(api, 'getChanges')
      .mockResolvedValue(page({ changes: [laterRun(), laterProposal()], returned: 2 }));
    const onEntitiesChanged = vi.fn();
    const { result } = renderHook(() =>
      useRecordSession(EXP_ID, { detail: DETAIL, onEntitiesChanged }),
    );
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 4);
    });

    // THE EVENT GENUINELY ARRIVED — the precondition, without which everything below
    // is a statement about a build that does nothing.
    expect(changes).toHaveBeenCalled();
    expect(onEntitiesChanged).toHaveBeenCalled();
    expect(onEntitiesChanged.mock.calls[0][0].runIds).toEqual([
      '01RUN0000000000000000000AA',
    ]);
    expect(result.current.activity).not.toBeNull();

    // …AND NOTHING WROTE.
    for (const spy of writeSpies) expect(spy).not.toHaveBeenCalled();
  });

  it('backs off exponentially on failure — bounded, not a storm', async () => {
    /*
     * A SERVER THAT IS DOWN MUST NOT BE HAMMERED. Measured as an interval between
     * requests rather than as a count over a window, because a count passes on a
     * client that fires everything in the first second and then sleeps.
     */
    const spy = vi.spyOn(api, 'getChanges').mockRejectedValue(new Error('down'));
    const { result } = renderHook(() => useRecordSession(EXP_ID, { detail: DETAIL }));
    await flush();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy).toHaveBeenCalledTimes(1);

    // The next attempt is at 2x, so nothing happens one interval later.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy).toHaveBeenCalledTimes(2);

    // Three consecutive failures is an honest degraded state, reported separately
    // from the record poller's.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MAX_BACKOFF_MS * 2);
    });
    expect(spy.mock.calls.length).toBeGreaterThanOrEqual(DEGRADED_THRESHOLD);
    expect(result.current.feedDegraded).toBe(true);

    // AND THE STORM BOUND, stated as a rate: an hour of a dead server is nowhere
    // near an hour of 8-second polling.
    const before = spy.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60 * 60 * 1000);
    });
    const perHourAtCadence = (60 * 60 * 1000) / POLL_INTERVAL_MS;
    expect(spy.mock.calls.length - before).toBeLessThan(perHourAtCadence / 5);
  });

  it('KEEPS the summary when the refetch landed BELOW the change it was about', async () => {
    /*
     * A NOTICE THAT CLEARS ON ANY REFETCH WOULD LIE. If a background refresh lands on
     * a revision that is still behind the change the notice reported, the notice is
     * STILL TRUE, and clearing it would tell a reader they are current when they are
     * not. That is why the clear compares against `highestRev` rather than firing on
     * any `version` change — and this is the case that distinguishes the two.
     */
    vi.spyOn(api, 'getChanges').mockResolvedValue(
      page({ changes: [{ ...laterRun(), changed_at_rev: KNOWN_REV + 10 }], returned: 1 }),
    );
    const { result, rerender } = renderHook(
      ({ detail }: { detail: ApiExperimentDetail }) => useRecordSession(EXP_ID, { detail }),
      { initialProps: { detail: DETAIL } },
    );
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(result.current.activity!.highestRev).toBe(KNOWN_REV + 10);

    // A refetch that moved the version, but only PART of the way there.
    const partial = { ...DETAIL, version: `gen.${KNOWN_REV + 3}` } as ApiExperimentDetail;
    await act(async () => {
      rerender({ detail: partial });
    });
    expect(result.current.activity).not.toBeNull(); // still behind — still true

    // And now all the way.
    const caughtUp = { ...DETAIL, version: `gen.${KNOWN_REV + 10}` } as ApiExperimentDetail;
    await act(async () => {
      rerender({ detail: caughtUp });
    });
    expect(result.current.activity).toBeNull();
  });

  it('refresh() does NOT clear a notice the view has not caught up to', async () => {
    /*
     * `refresh()` USED TO CLEAR IT UNCONDITIONALLY, AND THAT LOST IT FOR GOOD.
     *
     * Its stated justification was that "a refresh that finds nothing new would
     * otherwise leave a notice standing about a change already taken on board". A
     * refresh that finds nothing new has NOT taken the change on board: `recordRev` is
     * still below `activity.highestRev`, so the notice is still true — and the clear
     * was PERMANENT, because the feed cursor has already advanced past those entries
     * and nothing re-reports them.
     *
     * The clear now belongs entirely to the `highestRev` effect, which is the
     * published reasoning `refresh()` was contradicting. Both halves are asserted:
     * a refresh that lands nowhere new KEEPS the notice, and one paired with a detail
     * that has caught up clears it.
     */
    vi.spyOn(api, 'getChanges').mockResolvedValue(
      page({ changes: [{ ...laterRun(), changed_at_rev: KNOWN_REV + 7 }], returned: 1 }),
    );
    const { result, rerender } = renderHook(
      ({ detail }: { detail: ApiExperimentDetail }) => useRecordSession(EXP_ID, { detail }),
      { initialProps: { detail: DETAIL } },
    );
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(result.current.activity!.highestRev).toBe(KNOWN_REV + 7);

    // `RecordWorkbench.onAgentRefresh` calls this, then refetches its bundle. Here the
    // refetch brings back the SAME revision — nothing new — so the notice is still true.
    await act(async () => {
      result.current.refresh();
    });
    expect(result.current.activity).not.toBeNull();

    // …and it clears the moment the view actually catches up, which is the only thing
    // that may clear it.
    const caughtUp = { ...DETAIL, version: `gen.${KNOWN_REV + 7}` } as ApiExperimentDetail;
    await act(async () => {
      rerender({ detail: caughtUp });
    });
    expect(result.current.activity).toBeNull();
  });

  it('drops the outstanding summary when the view adopts a new revision', async () => {
    vi.spyOn(api, 'getChanges').mockResolvedValue(page({ changes: [laterRun()], returned: 1 }));
    const { result, rerender } = renderHook(
      ({ detail }: { detail: ApiExperimentDetail }) => useRecordSession(EXP_ID, { detail }),
      { initialProps: { detail: DETAIL } },
    );
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(result.current.activity).not.toBeNull();

    // The screen refetched and adopted the newer revision: the notice is spent.
    const adopted = { ...DETAIL, version: `gen.${KNOWN_REV + 5}` } as ApiExperimentDetail;
    await act(async () => {
      rerender({ detail: adopted });
    });
    expect(result.current.activity).toBeNull();
  });
});
