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
import { useRecordSession, CHANGE_FEED_CLIENT_LIMIT } from '../lib/useRecordSession';
import { POLL_INTERVAL_MS, POLL_MAX_BACKOFF_MS, DEGRADED_THRESHOLD } from '../lib/useRecordSync';
import { clearAllSessions } from '../lib/assistantSession';
import {
  describeChangeSummary,
  needsCanonicalRefetch,
  type RecordChangeSummary,
} from '../lib/recordChanges';
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
    /*
     * THE WHOLE OPTIONS OBJECT, `limit` INCLUDED, and this assertion is deliberately
     * not narrowed to the one key it is about. `toEqual` on the whole object is what
     * pins "never a cursor it built itself": a client that started inventing one would
     * add a key here, and a `toMatchObject` or a `.cursor` read would not see it.
     *
     * `limit` arrived on 2026-09-02, when `useRecordSession` began asking for the
     * server's whole page (see `CHANGE_FEED_CLIENT_LIMIT` and the measurement at its
     * `useChangeFeed` call site). Asserted through the imported constant rather than a
     * re-typed `200`, so the two cannot drift apart.
     */
    expect(spy.mock.calls[0][1]).toEqual({
      cursor: undefined,
      limit: CHANGE_FEED_CLIENT_LIMIT,
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy.mock.calls[1][1]).toEqual({
      cursor: 'SERVER-A',
      limit: CHANGE_FEED_CLIENT_LIMIT,
    });
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

  /*
   * ══ THE TWO FLOORS ═══════════════════════════════════════════════════════════════
   *
   * Everything below is about one measured defect: the record poller and the change
   * feed shared ONE floor, so whichever resolved first decided whether a colleague's
   * proposal ever reached the panel that shows it. The measurement is in
   * `apps/web/e2e/mutation/proposals.spec.ts` and the reasoning in
   * `recordChanges.ChangeFloors`; these are the same property asserted where it is
   * cheap to assert — at the hook that owns both pollers.
   */

  /** The same record detail, moved to a given revision — what a bundle refetch produces. */
  const detailAtRev = (rev: number): ApiExperimentDetail =>
    ({ ...DETAIL, version: `1.${rev}`, rev }) as ApiExperimentDetail;

  it("a proposal reaches the panel even when the RECORD poller got there first", async () => {
    /*
     * THE REGRESSION, IN THE ORDER IT HAPPENS IN A BROWSER.
     *
     *   1. the screen is open at rev R;
     *   2. a colleague files a proposal, which moves the record's own rev to R+1;
     *   3. the RECORD poller notices first and the screen refetches its bundle, so
     *      `detail` — and therefore the floor — is now R+1;
     *   4. the feed poll lands, carrying `experiment@R+1` and `proposal@R+1`.
     *
     * Under one floor step 4 produced `null` and the panel was never told. Measured:
     * no further list read in 47 s, "Showing 0 of 0" before and after.
     */
    const onEntitiesChanged = vi.fn();
    const spy = vi.spyOn(api, 'getChanges').mockResolvedValue(page());
    const { result, rerender } = renderHook(
      ({ detail }) => useRecordSession(EXP_ID, { detail, onEntitiesChanged }),
      { initialProps: { detail: DETAIL } },
    );
    await flush();

    // 3 — the record poller won the race and the bundle has already been adopted.
    rerender({ detail: detailAtRev(KNOWN_REV + 1) });
    await flush();

    // 4 — and only now does the feed deliver the batch for that same save.
    spy.mockResolvedValue(
      page({
        changes: [
          { kind: 'experiment', entity_id: EXP_ID, changed_at_rev: KNOWN_REV + 1 },
          { ...laterProposal(), changed_at_rev: KNOWN_REV + 1 },
        ],
        returned: 2,
      }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });

    expect(spy).toHaveBeenCalled(); // the poll really happened
    expect(onEntitiesChanged).toHaveBeenCalledTimes(1);
    const summary = onEntitiesChanged.mock.calls[0][0];
    expect(summary.proposalIds).toEqual(['01SYNTHETICPROPOSALPROPOS']);
    expect(summary.proposalRev).toBe(KNOWN_REV + 1);

    // THE PANEL'S SOURCE IS LIVE…
    expect(result.current.proposalActivity).not.toBeNull();
    expect(result.current.proposalActivity!.proposalIds).toEqual([
      '01SYNTHETICPROPOSALPROPOS',
    ]);

    // …AND THE RECORD ENTRY BESIDE IT IS STILL FILTERED, which is the control that
    // says the floor was not simply deleted. The view HAS adopted that save.
    expect(summary.recordMoved).toBe(false);

    // …AND THE NOTICE DOES NOT FIRE, because its sentence — "what is on screen was
    // loaded before that" — is false here: the record read has caught up.
    expect(result.current.activity).toBeNull();
  });

  it('NEGATIVE CONTROL: a RUN at that same position is still filtered', async () => {
    /*
     * The exemption is the proposal kind's alone. A run entry at a revision the record
     * read has adopted is genuinely not news — `bundle.reloadSilent()` has already
     * run — and reporting it would re-announce a change the view reflects, which is
     * the reason the floor exists at all.
     *
     * Same harness, same revisions, one field changed. If this reported, the fix would
     * have widened into "no floor" rather than "one floor per read".
     */
    const onEntitiesChanged = vi.fn();
    const spy = vi.spyOn(api, 'getChanges').mockResolvedValue(page());
    const { result, rerender } = renderHook(
      ({ detail }) => useRecordSession(EXP_ID, { detail, onEntitiesChanged }),
      { initialProps: { detail: DETAIL } },
    );
    await flush();
    rerender({ detail: detailAtRev(KNOWN_REV + 1) });
    await flush();

    spy.mockResolvedValue(
      page({
        changes: [
          { kind: 'experiment', entity_id: EXP_ID, changed_at_rev: KNOWN_REV + 1 },
          { ...laterRun(), changed_at_rev: KNOWN_REV + 1 },
        ],
        returned: 2,
      }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });

    expect(spy).toHaveBeenCalled();
    expect(onEntitiesChanged).not.toHaveBeenCalled();
    expect(result.current.activity).toBeNull();
    expect(result.current.proposalActivity).toBeNull();
  });

  it('a replayed batch says the SAME thing — no narrowing, no re-announcement', async () => {
    /*
     * THE DUPLICATE-ANNOUNCEMENT CONTROL, AND THE DESIGN IT REJECTED.
     *
     * The feed drops its cursor whenever its effect re-subscribes, and the poll after
     * that replays every entity at its current position. A first attempt at this fix
     * suppressed the replay by ADVANCING the proposal floor each time an entry was
     * reported onward. It did suppress it, and it broke something better protected
     * elsewhere: the replayed batch then arrived NARROWER than the one before it — the
     * proposal filtered, the record's own entry not — so an outstanding notice went
     * from "1 suggestion changed" to "this record changed", and that is a CHANGED
     * sentence in a live region, which is a re-announcement.
     * `change-feed-preserves-unsaved-input.test.tsx`'s flooding guard caught it.
     *
     * So the floor is fixed and a replay is deduplicated where it already was: the
     * summary is IDENTICAL, so the notice's sentence does not change and the panel's
     * `proposalRev`+ids key does not change. This asserts that identity, which is the
     * property both downstream guards depend on.
     */
    const onEntitiesChanged = vi.fn();
    const spy = vi.spyOn(api, 'getChanges').mockResolvedValue(page());
    const { result, rerender } = renderHook(
      ({ detail }) => useRecordSession(EXP_ID, { detail, onEntitiesChanged }),
      { initialProps: { detail: DETAIL } },
    );
    await flush();
    rerender({ detail: detailAtRev(KNOWN_REV + 1) });
    await flush();

    spy.mockResolvedValue(
      page({
        changes: [{ ...laterProposal(), changed_at_rev: KNOWN_REV + 1 }],
        returned: 1,
      }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(onEntitiesChanged).toHaveBeenCalledTimes(1);
    const firstSentence = describeChangeSummary(onEntitiesChanged.mock.calls[0][0]);

    // The identical page arrives three more times — the shape a resync produces.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);
    });
    expect(spy.mock.calls.length).toBeGreaterThan(1); // the polls really happened

    // WHAT A READER HEARS is unchanged, on every one of them…
    for (const [summary] of onEntitiesChanged.mock.calls) {
      expect(describeChangeSummary(summary)).toBe(firstSentence);
      // …and WHAT THE PANEL KEYS ON is unchanged, so it issues no further read.
      expect(summary.proposalRev).toBe(KNOWN_REV + 1);
      expect(summary.proposalIds).toEqual(['01SYNTHETICPROPOSALPROPOS']);
    }
    expect(result.current.activity).toBeNull(); // still caught up: no banner at all

    // A LATER position for the same proposal IS news — created, then reviewed — and it
    // is what makes the stability above a filter rather than a dead poller.
    spy.mockResolvedValue(
      page({
        changes: [{ ...laterProposal(), changed_at_rev: KNOWN_REV + 2 }],
        returned: 1,
      }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    const calls = onEntitiesChanged.mock.calls;
    const last = calls[calls.length - 1][0];
    expect(last.proposalRev).toBe(KNOWN_REV + 2);
  });

  it('the NOTICE is unchanged: a change the view has NOT adopted still raises it', async () => {
    /*
     * The other half of the honesty claim. The fix moves what the PANEL is told; it
     * must not move what the READER is shown. A proposal above the record's revision
     * is a change the view has not adopted, so the notice fires exactly as before —
     * and keeps standing until the record read catches up.
     */
    const { result, rerender } = renderHook(
      ({ detail }) => useRecordSession(EXP_ID, { detail }),
      { initialProps: { detail: DETAIL } },
    );
    vi.spyOn(api, 'getChanges').mockResolvedValue(
      page({ changes: [laterProposal()], returned: 1 }),
    );
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(result.current.activity).not.toBeNull();
    expect(result.current.proposalActivity).not.toBeNull();

    // …and it clears the moment the view reaches the position it was about.
    rerender({ detail: detailAtRev(KNOWN_REV + 1) });
    await flush();
    expect(result.current.activity).toBeNull();
    // The panel's source deliberately does NOT clear with it: the record read catching
    // up adopts no proposal state, and treating it as though it did is the defect.
    expect(result.current.proposalActivity).not.toBeNull();
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

  /*
   * ══ THE THIRD FLOOR — THE RUN LIST ═══════════════════════════════════════════════
   *
   * The same measured defect as the proposal one, in the kind the first split left
   * behind. `RunsSection` fetches the run list itself (`api.listRuns`, its own paging,
   * its own component), so a record refetch adopts none of it — and the record floor
   * therefore filters a `run` entry the run list has never seen, permanently, whenever
   * the record poller wins the race. Which it does, in the ordinary case.
   *
   * `activity` deliberately does NOT widen: it drives an announced sentence. See
   * `useRecordSession.handleFeed`, which asks the two questions separately.
   */
  it('a RUN reaches the run list even when the RECORD poller got there first', async () => {
    const spy = vi.spyOn(api, 'getChanges').mockResolvedValue(page());
    const { result, rerender } = renderHook(
      ({ detail }) => useRecordSession(EXP_ID, { detail }),
      { initialProps: { detail: DETAIL } },
    );
    await flush();

    // The record poller won: the bundle is already at R+1, so the record floor is too.
    rerender({ detail: detailAtRev(KNOWN_REV + 1) });
    await flush();

    spy.mockResolvedValue(
      page({
        changes: [
          { kind: 'experiment', entity_id: EXP_ID, changed_at_rev: KNOWN_REV + 1 },
          { ...laterRun(), changed_at_rev: KNOWN_REV + 1 },
        ],
        returned: 2,
      }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });

    // THE RUN LIST'S SIGNAL IS LIVE…
    expect(result.current.runActivity).not.toBeNull();
    expect(result.current.runActivity!.runIds).toEqual(['01RUN0000000000000000000AA']);
    expect(result.current.runActivity!.runRev).toBe(KNOWN_REV + 1);

    // …AND THE ANNOUNCED NOTICE IS UNCHANGED BY IT. This is the control that says the
    // run floor did not leak into the sentence a screen-reader user hears: the record
    // read HAS caught up, so "what is on screen was loaded before that" is false.
    expect(result.current.activity).toBeNull();
  });

  it('NEGATIVE CONTROL: a run at or below the revision the list loaded at is NOT reported', async () => {
    /*
     * The floor is seeded from the revision the screen mounted at, because
     * `RunsSection` issues its own first read then. Without that, the first (cursorless)
     * poll would report every run on the record as news and the list would re-read for
     * nothing on every mount.
     */
    vi.spyOn(api, 'getChanges').mockResolvedValue(
      page({
        changes: [{ ...laterRun(), changed_at_rev: KNOWN_REV }],
        returned: 1,
      }),
    );
    const { result } = renderHook(() => useRecordSession(EXP_ID, { detail: DETAIL }));
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(result.current.runActivity).toBeNull();
  });

  it('delivers a run signal ONCE — a replayed batch does not re-deliver it', async () => {
    /*
     * A cursorless resync returns every entity at its current position, so without an
     * advancing floor the run list would be told to re-read on every resync for a
     * change it took on board long ago. The floor advances here and deliberately does
     * NOT on the proposal side; the divergence is safe only because this summary feeds
     * no announced sentence, and `runFloorRef` carries the argument.
     */
    const spy = vi.spyOn(api, 'getChanges').mockResolvedValue(
      page({ changes: [{ ...laterRun(), changed_at_rev: KNOWN_REV + 1 }], returned: 1 }),
    );
    const { result } = renderHook(() => useRecordSession(EXP_ID, { detail: DETAIL }));
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    const first = result.current.runActivity;
    expect(first).not.toBeNull();

    // The identical batch again — the same entity at the same position.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(spy.mock.calls.length).toBeGreaterThan(1); // the second poll really happened
    expect(
      Object.is(result.current.runActivity, first),
      'the replay produced no new signal for the run list to act on',
    ).toBe(true);

    // …and a genuinely LATER move of the same run still is reported, which is the
    // control that says the floor is a filter and not a mute.
    spy.mockResolvedValue(
      page({ changes: [{ ...laterRun(), changed_at_rev: KNOWN_REV + 2 }], returned: 1 }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(result.current.runActivity).not.toBeNull();
    expect(result.current.runActivity!.runRev).toBe(KNOWN_REV + 2);
  });

});
