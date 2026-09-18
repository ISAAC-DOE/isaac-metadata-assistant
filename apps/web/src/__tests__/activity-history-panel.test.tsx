import { describe, it, expect, afterEach, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';

import { ActivityHistoryPanel } from '../components/ActivityHistoryPanel';
import { LABELS } from '../lib/labels';
import { api } from '../lib/api';
import type { ApiActivityEvent, ApiActivityResponse } from '../lib/types';

/**
 * `ACT-003` — THE ACTIVITY HISTORY PANEL, tested against the ways it could be WRONG.
 *
 * Each case names the defect it refuses. Three of them are defect classes this
 * repository has already shipped once and recorded: a count taken from a fetched
 * array, an internal identifier rendered at a scientist, and `absent` collapsed
 * into `null`.
 */

afterEach(() => {
  vi.restoreAllMocks();
});

function event(over: Partial<ApiActivityEvent> = {}): ApiActivityEvent {
  return {
    id: 'act_1',
    experiment_id: 'demo',
    seq: 1,
    recorded_utc: '2099-01-01T00:00:00Z',
    actor: 'unattributed',
    actor_trust_basis: 'unattributed',
    channel: 'web',
    action: 'experiment_renamed',
    object_type: 'experiment',
    object_id: 'demo',
    run_id: null,
    field_path: null,
    before: { present: true, value: 'Old title' },
    after: { present: true, value: 'New title' },
    source_ref: null,
    ...over,
  };
}

function body(over: Partial<ApiActivityResponse> = {}): ApiActivityResponse {
  const events = over.events ?? [event()];
  return {
    events,
    total: events.length,
    matched: events.length,
    returned: events.length,
    highest_seq: events.length,
    unreadable_entries: 0,
    limit: 50,
    newest_first: true,
    next_since_seq: null,
    next_before_seq: null,
    actions: ['experiment_renamed'],
    channels: ['web', 'mcp', 'historical_import', 'system'],
    object_types: ['experiment'],
    ...over,
  };
}

function mount(over: Partial<ApiActivityResponse> = {}) {
  vi.spyOn(api, 'listActivity').mockResolvedValue(body(over));
  return render(<ActivityHistoryPanel experimentId="demo" />);
}

describe('the activity history panel', () => {
  it('shows the SERVER total, never the length of the page it received', async () => {
    /*
     * THE DEFECT THIS REFUSES is the one `CLAUDE.md` §11 records for `pendingTotal`:
     * a count read from the fetched array understates the truth the moment a page is
     * smaller than the history. Here the server reports ytwo hundred acts and sends
     * three, and the panel must say 200 — not 3.
     */
    const three = [event({ id: 'a', seq: 3 }), event({ id: 'b', seq: 2 }), event({ id: 'c', seq: 1 })];
    const { container } = mount({ events: three, total: 200, matched: 200, returned: 3, highest_seq: 200 });
    /*
     * SCOPED TO THE VISIBLE LINE. An unscoped `findByText(/of 200/)` now matches
     * TWICE, because the `sr-only` announcer carries the same sentence on purpose —
     * a screen-reader user otherwise hears nothing when a read finishes. Scoping is
     * the fix rather than loosening the matcher, and the announcer gets its own
     * assertion below so the duplication is pinned as intended rather than tolerated.
     */
    await screen.findAllByText(/of 200/);
    const counts = container.querySelector('.activity-counts');
    expect(counts?.textContent).toContain('3');
    expect(counts?.textContent).toContain('200');
    expect(counts?.textContent).not.toMatch(/\b3 of 3\b/);

    // EXACTLY ONE live region on this panel, and it is the announcer — not a second
    // one racing it, which is the defect `IngestionProposalsPanel` records.
    const live = container.querySelectorAll('[aria-live]');
    expect(live).toHaveLength(1);
    expect(live[0].className).toContain('sr-only');
    expect(live[0].textContent).toContain('200');
  });

  it('offers a way to reach the entries it says are hidden', async () => {
    /*
     * THE DEAD END THIS REFUSES, found by an Impeccable pass over this panel: the
     * first version reported "50 of 200" and offered NO control, so 150 facts it
     * named were unreachable. A count that advertises hidden content with no way to
     * reach it is not a deliberate scope boundary, it is an unfinished surface.
     */
    const first = [event({ id: 'p1', seq: 200 })];
    const second = [event({ id: 'p2', seq: 199, action: 'note_captured', object_type: 'note' })];
    const spy = vi
      .spyOn(api, 'listActivity')
      .mockResolvedValueOnce(body({ events: first, total: 2, returned: 1, next_before_seq: 200 }))
      .mockResolvedValueOnce(body({ events: second, total: 2, returned: 1, next_before_seq: null }));
    const { container } = render(<ActivityHistoryPanel experimentId="demo" />);

    const older = await screen.findByRole('button', { name: LABELS.activityShowOlder });
    fireEvent.click(older);

    // The older page is APPENDED — the reader never loses what they were looking at.
    await screen.findByText('Note Captured');
    expect(screen.getByText('Experiment Renamed')).toBeTruthy();
    expect(container.querySelectorAll('.activity-row')).toHaveLength(2);

    // The cursor walked: the second call asked for entries BEFORE the first page's tail.
    expect(spy.mock.calls[1]?.[1]).toEqual({ beforeSeq: 200 });

    // Exhausted, and SAID so — a vanished control is ambiguous between "no more"
    // and "broken".
    expect(await screen.findByText(LABELS.activityAllShown)).toBeTruthy();
    expect(screen.queryByRole('button', { name: LABELS.activityShowOlder })).toBeNull();
  });

  it('keeps the actor disclosure in the DOM behind a native details, not deleted', async () => {
    /*
     * `ACT-003` requires `unattributed` be rendered HONESTLY. Moving the explanation
     * behind a `<details>` must not weaken that: a closed native disclosure is still
     * in the DOM, still found by find-in-page, and still reachable by a screen
     * reader — which is exactly why the repo uses it rather than conditional
     * rendering. The SUMMARY also states the question, so nothing hides behind a
     * neutral label.
     */
    const { container } = mount();
    await screen.findByText('Experiment Renamed');
    const details = container.querySelector('details.activity-actor-details');
    expect(details).toBeTruthy();
    expect(details?.hasAttribute('open')).toBe(false);
    expect(container.querySelector('.activity-actor-summary')?.textContent).toBe(
      LABELS.activityWhyUnattributed,
    );
    // The sentence itself is PRESENT while collapsed — `querySelectorAll` reaches
    // inside a closed `<details>`, which is the property this relies on.
    expect(container.querySelector('.activity-actor-note')?.textContent).toBe(
      LABELS.activityActorUnattributed,
    );
  });

  it('a failed OLDER page leaves the list it already showed intact', async () => {
    /*
     * §11's destructive-silent-failure rule, which this repository has now fixed
     * twice (`IngestionProposalsPanel`, `UnmappedNotesPanel`): a background failure
     * must not destroy what is on screen. Before paging existed the case was
     * unreachable here; it is reachable now.
     */
    vi.spyOn(api, 'listActivity')
      .mockResolvedValueOnce(body({ events: [event({ id: 'keep', seq: 9 })], total: 5, returned: 1, next_before_seq: 9 }))
      .mockRejectedValueOnce(new Error('down'));
    const { container } = render(<ActivityHistoryPanel experimentId="demo" />);
    fireEvent.click(await screen.findByRole('button', { name: LABELS.activityShowOlder }));
    await screen.findByRole('button', { name: LABELS.activityShowOlder });
    // The row is still there, and the panel did NOT fall back to an error state.
    expect(container.querySelectorAll('.activity-row')).toHaveLength(1);
    expect(screen.queryByText(LABELS.activityEmpty)).toBeNull();
  });

  it('says in WORDS that entries are unattributed, and says why', async () => {
    /*
     * `ACT-003`: render `unattributed` HONESTLY rather than hiding entries that lack
     * an actor. Two failure modes are refused at once — dropping such rows, and
     * printing the bare token `unattributed` beside every row, which reads as a
     * fault rather than as a deliberate boundary. Confirmed against the hosted
     * deployment 2026-09-17: `actor_trust_basis: null`, `verifier_id: unconfigured`.
     */
    mount();
    expect(await screen.findByText(LABELS.activityActorUnattributed)).toBeTruthy();
    // The row itself is present — not filtered out for lacking an actor.
    expect(screen.getByText('Experiment Renamed')).toBeTruthy();
  });

  it('humanizes the server vocabularies and renders no bare snake_case token', async () => {
    /*
     * `CLAUDE.md` §11's measured rule, and the defect the Impeccable pass found on
     * the corpus-review surface earlier the same day: an internal identifier
     * rendered at a scientist. `experiment_renamed` must read "Experiment Renamed".
     */
    mount({ events: [event({ action: 'run_qc_answered', object_type: 'run', channel: 'historical_import' })] });
    await screen.findByText('Run QC Answered');
    expect(screen.getByText('Historical Import')).toBeTruthy();
    const panel = screen.getByRole('region', { name: LABELS.activityTitle });
    // No 2+-segment snake_case survives anywhere in the rendered text.
    expect(panel.textContent ?? '').not.toMatch(/\b[a-z]+_[a-z]+\b/);
  });

  it('distinguishes "was not set" from "was empty" — absent is not null', async () => {
    /*
     * The server's `{present, value}` envelope carries TWO DIFFERENT FACTS, and a
     * renderer branching on `value` instead of `present` collapses them. A run that
     * did not exist before is not a run whose label was null.
     */
    mount({
      events: [
        event({ id: 'absent', seq: 2, before: { present: false, value: null }, after: { present: true, value: 'Run 1' } }),
        event({ id: 'nulled', seq: 1, before: { present: true, value: null }, after: { present: true, value: 'x' } }),
      ],
    });
    await screen.findByText(LABELS.activityAbsent);
    expect(screen.getByText(LABELS.activityNull)).toBeTruthy();
    expect(LABELS.activityAbsent).not.toBe(LABELS.activityNull);
  });

  it('discloses unreadable stored entries rather than hiding them', async () => {
    /*
     * Counted, never rendered: saying what an unreadable entry contains would mean
     * inventing it. Showing zero while the record holds some is the silent discard
     * the feature exists to end.
     */
    mount({ unreadable_entries: 4 });
    const counts = await screen.findByText(new RegExp(LABELS.activityUnreadable.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
    expect(counts.textContent).toContain('4');
  });

  it('says nothing has been recorded, rather than showing an empty list', async () => {
    const { container } = mount({ events: [], total: 0, matched: 0, returned: 0, highest_seq: 0 });
    // Scoped: the announcer carries the same sentence on purpose (see the first test).
    await screen.findAllByText(LABELS.activityEmpty);
    expect(container.querySelector('.activity-counts')?.textContent).toContain(
      LABELS.activityEmpty,
    );
    expect(screen.queryByRole('list')).toBeNull();
  });

  it('offers NO control that writes, because an event is recorded by the act it describes', async () => {
    /*
     * Structural, not a promise: `api` exposes no activity mutator at all. This
     * asserts the surface as well — a button here would be a client asking for an
     * audit row, which is the one thing an audit log must not accept.
     *
     * STRENGTHENED BY `ACT-003b`, WHICH ADDED TWO MORE NATIVE `<details>`. The
     * original `queryAllByRole('button') === 0` still passes, and that is exactly
     * why it needed strengthening: `<summary>` is NOT reported as a button by this
     * environment's role mapping, so a disclosure could have become a form control
     * without moving that number. The assertions below are over TAGS, which no role
     * mapping can soften — every real `<button>` is enumerated, no form element of
     * any kind exists, and the disclosures are counted so a third one arriving is a
     * decision somebody makes rather than a diff nobody reads.
     */
    const { container } = mount({
      events: [
        event({
          id: 'structured',
          before: { present: true, value: { label: 'a' } },
          after: { present: true, value: { label: 'b' } },
        }),
      ],
    });
    await screen.findByText('Experiment Renamed');
    const panel = screen.getByRole('region', { name: LABELS.activityTitle });
    expect(within(panel).queryAllByRole('button')).toHaveLength(0);
    expect(within(panel).queryAllByRole('textbox')).toHaveLength(0);
    // No `<button>` at all on a page with no older entries to fetch, and never a
    // form control: `input`, `textarea`, `select` and `form` are all absent.
    expect(container.querySelectorAll('button')).toHaveLength(0);
    expect(container.querySelectorAll('input, textarea, select, form')).toHaveLength(0);
    // Two disclosures: the standing actor note, and this row's stored values.
    expect(container.querySelectorAll('details')).toHaveLength(2);
    expect(container.querySelectorAll('details > summary')).toHaveLength(2);
    expect('listActivity' in api).toBe(true);
    expect(Object.keys(api).filter((k) => /activity/i.test(k))).toEqual(['listActivity']);
  });

  it('reports a failed read without claiming the history is empty', async () => {
    /*
     * The two are different claims. "Nothing has been recorded" about a record whose
     * history merely failed to load is a false statement about the science.
     */
    vi.spyOn(api, 'listActivity').mockRejectedValue(new Error('down'));
    const { container } = render(<ActivityHistoryPanel experimentId="demo" />);
    // Scoped: the announcer carries the same sentence on purpose.
    await screen.findAllByText(LABELS.activityUnavailable);
    expect(container.querySelector('.activity-status-error')?.textContent).toBe(
      LABELS.activityUnavailable,
    );
    expect(screen.queryByText(LABELS.activityEmpty)).toBeNull();
  });
});

/* ════════════════════════════════════════════════════════════════════════════
 * `ACT-003b` — THE THREE NAMED DEFECTS IN `ACT-003`'s PANEL.
 *
 * A · no time hierarchy: every row carried its own absolute timestamp and nothing
 *     grouped them, so a scientist could not tell today from last month without
 *     reading every row.
 * B · the action, the object, the CHANNEL and the timestamp were four sibling
 *     spans at one weight, so "Web" competed with "Updated".
 * C · `describeSide` fell through to `JSON.stringify(value)` at 11px — a machine
 *     dump as the DEFAULT scientist view of any structured change.
 *
 * NONE OF THESE WAS PINNED BY AN EXISTING ASSERTION, so nothing here is an
 * inversion: they were defects of what the panel rendered, not of what it claimed.
 * The one existing test that came CLOSE — "offers NO control that writes" — was
 * strengthened in place above rather than left, because `ACT-003b` adds
 * disclosures and that test's number could not see them.
 * ════════════════════════════════════════════════════════════════════════════ */

/**
 * `now` IS CONTROLLED, NOT ASSUMED. "Today" is a claim about the clock, so every
 * case below fixes it — and the timestamps are derived FROM the fixed clock by
 * arithmetic rather than written as literals, because a hard-coded UTC instant
 * lands on a different local calendar day depending on where the suite runs, and
 * the panel groups by the reader's LOCAL day on purpose.
 */
const DAY_MS = 24 * 60 * 60 * 1000;
const FIXED_NOW = new Date('2099-03-10T12:00:00.000Z');
const agoMs = (ms: number): string => new Date(FIXED_NOW.getTime() - ms).toISOString();

function useFixedClock(now: Date = FIXED_NOW): void {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(now);
}

afterEach(() => {
  vi.useRealTimers();
});

describe('ACT-003b · A · the history has a time hierarchy', () => {
  it('groups rows under a day heading, in list semantics rather than beside them', async () => {
    useFixedClock();
    const { container } = mount({
      events: [
        event({ id: 't1', seq: 4, recorded_utc: agoMs(2 * 60 * 60 * 1000) }),
        event({ id: 't2', seq: 3, recorded_utc: agoMs(5 * 60 * 60 * 1000) }),
        event({ id: 'y1', seq: 2, recorded_utc: agoMs(DAY_MS) }),
        event({ id: 'o1', seq: 1, recorded_utc: agoMs(5 * DAY_MS) }),
      ],
    });
    await screen.findAllByText('Experiment Renamed');

    const headings = [...container.querySelectorAll('.activity-group-heading')].map(
      (h) => h.textContent,
    );
    expect(headings).toHaveLength(3);
    expect(headings[0]).toBe(LABELS.activityToday);
    expect(headings[1]).toBe(LABELS.activityYesterday);
    // The third is an absolute date, and it CARRIES ITS YEAR — a history spanning a
    // year boundary would otherwise show two indistinguishable headings.
    expect(headings[2]).not.toBe(LABELS.activityToday);
    expect(headings[2]).not.toBe(LABELS.activityYesterday);
    expect(headings[2]).toContain('2099');

    // STRUCTURE, not just text. The outer list holds one item per day; each item
    // carries a heading and its OWN list of rows. A heading floating beside a flat
    // list, or a bare `<div>` between `<li>`s, would break the list semantics a
    // screen reader walks — which is the shape this refuses.
    const groups = container.querySelectorAll('ol.activity-list > li.activity-group');
    expect(groups).toHaveLength(3);
    for (const group of groups) {
      expect(group.querySelector(':scope > h3.activity-group-heading')).toBeTruthy();
      expect(group.querySelector(':scope > ol.activity-group-list')).toBeTruthy();
    }
    expect(container.querySelectorAll('ol.activity-list > div')).toHaveLength(0);
    // The panel's own heading is `h2`, so the group headings must be `h3` or the
    // document outline skips a level.
    expect(container.querySelector('.activity-heading')?.tagName).toBe('H2');
    // Two rows under Today, one under each of the others — and in the server's order.
    const perGroup = [...groups].map((g) => g.querySelectorAll('.activity-row').length);
    expect(perGroup).toEqual([2, 1, 1]);
  });

  it('groups by the event’s own recorded_utc, never by its position in the array', async () => {
    /*
     * THE DEFECT THIS REFUSES is a grouping that counts rows — "the first ten are
     * today" — which would be right on every ordinary page and wrong on the one
     * that matters. The server orders by `seq`, a durable position, and nothing
     * guarantees `recorded_utc` is monotonic in it: here the middle row is OLDER
     * than the one after it, and the grouping must follow the timestamps while the
     * ORDER stays the server's.
     */
    useFixedClock();
    const { container } = mount({
      events: [
        event({ id: 'a', seq: 3, recorded_utc: agoMs(60 * 60 * 1000) }),
        event({ id: 'b', seq: 2, recorded_utc: agoMs(5 * DAY_MS) }),
        event({ id: 'c', seq: 1, recorded_utc: agoMs(DAY_MS) }),
      ],
    });
    await screen.findAllByText('Experiment Renamed');
    const headings = [...container.querySelectorAll('.activity-group-heading')].map(
      (h) => h.textContent,
    );
    // Three groups, in the array's order — the out-of-order row is NOT moved to sit
    // with its calendar neighbours, which would be a claim the record never made.
    expect(headings).toEqual([LABELS.activityToday, headings[1], LABELS.activityYesterday]);
    expect(headings[1]).toContain('2099');
    const rows = [...container.querySelectorAll('.activity-row')];
    expect(rows).toHaveLength(3);
  });

  it('MEASURED: a day opened by page 1 and continued by page 2 renders ONE heading', async () => {
    /*
     * `ACT-003b` asks for this to be measured rather than reasoned, with a fixture
     * whose page boundary falls INSIDE a day. The defect it refuses is a grouping
     * computed per page and concatenated, which renders the same heading twice and
     * tells the reader two different days happened.
     */
    useFixedClock();
    const sameDay = agoMs(3 * 60 * 60 * 1000);
    const spy = vi
      .spyOn(api, 'listActivity')
      .mockResolvedValueOnce(
        body({
          events: [
            event({ id: 'p1a', seq: 9, recorded_utc: sameDay }),
            event({ id: 'p1b', seq: 8, recorded_utc: agoMs(4 * 60 * 60 * 1000) }),
          ],
          total: 3,
          returned: 2,
          next_before_seq: 8,
        }),
      )
      .mockResolvedValueOnce(
        body({
          events: [event({ id: 'p2a', seq: 7, recorded_utc: agoMs(5 * 60 * 60 * 1000) })],
          total: 3,
          returned: 1,
          next_before_seq: null,
        }),
      );
    const { container } = render(<ActivityHistoryPanel experimentId="demo" />);

    fireEvent.click(await screen.findByRole('button', { name: LABELS.activityShowOlder }));
    await screen.findByText(LABELS.activityAllShown);

    expect(spy.mock.calls[1]?.[1]).toEqual({ beforeSeq: 8 });
    expect(container.querySelectorAll('.activity-row')).toHaveLength(3);
    // ONE heading for the three rows — the group survived the append.
    const headings = [...container.querySelectorAll('.activity-group-heading')].map(
      (h) => h.textContent,
    );
    expect(headings).toEqual([LABELS.activityToday]);
    expect(container.querySelectorAll('.activity-group')).toHaveLength(1);
  });

  it('recomputes "Today" on every render, so a tab left open overnight does not lie', async () => {
    /*
     * MUTATION-GUARDED. Cache `now` at mount — `useRef(new Date())` or a module
     * constant — and this is the only test that fails: every other case renders
     * once. The panel holds no unsaved state and re-reads on open, so recomputing
     * costs one `Date` per render and buys a claim that cannot go stale.
     */
    useFixedClock();
    const yesterdayNoon = agoMs(0);
    const spy = vi
      .spyOn(api, 'listActivity')
      .mockResolvedValueOnce(
        body({
          events: [event({ id: 'r1', seq: 2, recorded_utc: yesterdayNoon })],
          total: 2,
          returned: 1,
          next_before_seq: 2,
        }),
      )
      .mockResolvedValueOnce(
        body({
          events: [event({ id: 'r2', seq: 1, recorded_utc: yesterdayNoon })],
          total: 2,
          returned: 1,
          next_before_seq: null,
        }),
      );
    const { container } = render(<ActivityHistoryPanel experimentId="demo" />);
    await screen.findByText(LABELS.activityToday);

    // The clock moves a day forward while the tab sits open; the next render must
    // call the same instant "Yesterday".
    vi.setSystemTime(new Date(FIXED_NOW.getTime() + DAY_MS));
    fireEvent.click(screen.getByRole('button', { name: LABELS.activityShowOlder }));
    await screen.findByText(LABELS.activityAllShown);

    expect(spy).toHaveBeenCalledTimes(2);
    const headings = [...container.querySelectorAll('.activity-group-heading')].map(
      (h) => h.textContent,
    );
    expect(headings).toEqual([LABELS.activityYesterday]);
    expect(screen.queryByText(LABELS.activityToday)).toBeNull();
  });

  it('keeps the exact timestamp reachable — machine value, and the absolute one in full', async () => {
    /*
     * `ACT-003b`'s constraint: relative wording must not REPLACE the exact value.
     * The row shows a time of day under a dated heading, the `<time>` element still
     * carries the exact machine value it always did, and the full absolute
     * timestamp is one hover away rather than deleted.
     */
    useFixedClock();
    const stamp = agoMs(2 * 60 * 60 * 1000);
    const { container } = mount({ events: [event({ id: 'x', recorded_utc: stamp })] });
    await screen.findByText('Experiment Renamed');
    const time = container.querySelector('time.activity-when');
    expect(time?.getAttribute('dateTime') ?? time?.getAttribute('datetime')).toBe(stamp);
    // The VISIBLE text is a time of day, not the ISO wire format and not a date.
    expect(time?.textContent ?? '').not.toContain('T');
    expect(time?.textContent ?? '').not.toContain('2099');
    expect(time?.textContent ?? '').toMatch(/\d/);
    // The full readable timestamp survives, with its date.
    expect(time?.getAttribute('title') ?? '').toContain('2099');
  });

  it('gives an unparseable timestamp its own group rather than filing it under a day', async () => {
    /*
     * §11's persisted-value rule: a stored value this build cannot read must be
     * READ, not refused and not guessed. Merging it into a neighbouring day would
     * assert a date the record does not carry.
     */
    useFixedClock();
    const { container } = mount({
      events: [
        event({ id: 'good', seq: 2, recorded_utc: agoMs(60 * 60 * 1000) }),
        event({ id: 'bad', seq: 1, recorded_utc: 'not-a-timestamp' }),
      ],
    });
    await screen.findAllByText('Experiment Renamed');
    const headings = [...container.querySelectorAll('.activity-group-heading')].map(
      (h) => h.textContent,
    );
    expect(headings).toEqual([LABELS.activityToday, 'not-a-timestamp']);
    expect(container.querySelectorAll('.activity-group')).toHaveLength(2);
  });
});

describe('ACT-003b · B · the act reads louder than its own metadata', () => {
  it('puts ONLY the action and the object on the primary line', async () => {
    /*
     * THE DEFECT THIS REFUSES, exactly as shipped: `.activity-row-head` held the
     * action, the object, the CHANNEL and the timestamp as four sibling spans at
     * one weight. The channel and the time are secondary metadata; they now live on
     * their own demoted line and must not come back to the primary one.
     */
    useFixedClock();
    const { container } = mount({
      events: [event({ channel: 'historical_import', recorded_utc: agoMs(60 * 60 * 1000) })],
    });
    await screen.findByText('Experiment Renamed');

    const head = container.querySelector('.activity-row-head');
    expect(head?.querySelector('.activity-action')?.textContent).toBe('Experiment Renamed');
    expect(head?.querySelector('.activity-object')?.textContent).toBe('Experiment');
    expect(head?.querySelector('.activity-channel')).toBeNull();
    expect(head?.querySelector('time')).toBeNull();
    expect(head?.children).toHaveLength(2);

    // Both demoted facts are still rendered — moved, never dropped.
    const meta = container.querySelector('.activity-meta');
    expect(meta?.querySelector('.activity-channel')?.textContent).toBe('Historical Import');
    expect(meta?.querySelector('time.activity-when')).toBeTruthy();
  });

  it('shows NO per-row actor while every loaded event is unattributed, and says so once instead', async () => {
    /*
     * THE JUDGEMENT CALL, pinned so it is a decision and not an accident. Every
     * event in every deployment of this build reads `actor: "unattributed"`, so a
     * per-row actor would be the same non-answer 200 times, competing with the act
     * for attention — the very hierarchy defect B is about. `ACT-003`'s requirement
     * that it be rendered HONESTLY is met by the panel's standing disclosure, which
     * says it once WITH its reason and is still in the DOM.
     */
    useFixedClock();
    const { container } = mount({
      events: [
        event({ id: 'a', seq: 2, recorded_utc: agoMs(60 * 60 * 1000) }),
        event({ id: 'b', seq: 1, recorded_utc: agoMs(2 * 60 * 60 * 1000) }),
      ],
    });
    await screen.findAllByText('Experiment Renamed');
    expect(container.querySelectorAll('.activity-actor')).toHaveLength(0);
    // Not dropped as a fact — said once, in words, with its reason.
    expect(container.querySelector('.activity-actor-note')?.textContent).toBe(
      LABELS.activityActorUnattributed,
    );
    // And the rows themselves are present: nothing is filtered for lacking an actor.
    expect(container.querySelectorAll('.activity-row')).toHaveLength(2);
  });

  it('shows the actor on EVERY row once any event names one — including the honest ones', async () => {
    /*
     * THE OTHER HALF OF THE SAME DECISION, and the reason it is per-LIST rather than
     * per-row. Suppressing only the unattributed rows in a mixed history would make
     * "nobody was established" indistinguishable from "this build failed to read the
     * actor". Once one act has a name, every row says who — and the unattributed
     * ones say so in words rather than going blank.
     */
    useFixedClock();
    const { container } = mount({
      events: [
        event({
          id: 'named',
          seq: 2,
          recorded_utc: agoMs(60 * 60 * 1000),
          actor: 'aresearcher',
          actor_trust_basis: 'verified_edge_assertion',
        }),
        event({ id: 'nobody', seq: 1, recorded_utc: agoMs(2 * 60 * 60 * 1000) }),
      ],
    });
    await screen.findAllByText('Experiment Renamed');
    const actors = [...container.querySelectorAll('.activity-actor')].map((n) => n.textContent);
    expect(actors).toEqual(['Aresearcher', 'Unattributed']);
    // A verified edge assertion is what an attributed row is EXPECTED to be, so it
    // carries no extra qualification — the same rule `revisionHistory` already uses.
    expect(container.querySelectorAll('.activity-trust')).toHaveLength(0);
  });

  it('qualifies a name whose basis a reader would otherwise take at face value (DEC-45)', async () => {
    useFixedClock();
    const { container } = mount({
      events: [
        event({
          id: 'fixture',
          recorded_utc: agoMs(60 * 60 * 1000),
          actor: 'fixture-subject',
          actor_trust_basis: 'test_fixture',
        }),
      ],
    });
    await screen.findByText('Experiment Renamed');
    expect(container.querySelector('.activity-trust')?.textContent).toBe(
      LABELS.activityTrustFixture,
    );
  });
});

describe('ACT-003b · C · a structured change is not a JSON dump', () => {
  const objectEvent = (over: Partial<ApiActivityEvent> = {}): ApiActivityEvent =>
    event({
      id: 'asset',
      action: 'asset_updated',
      object_type: 'asset',
      recorded_utc: agoMs(60 * 60 * 1000),
      before: { present: true, value: { label: 'Old label', run_ids: ['r1'], bytes: 10 } },
      after: { present: true, value: { label: 'New label', run_ids: ['r1', 'r2'], bytes: 10 } },
      ...over,
    });

  it('names WHICH fields changed instead of stringifying the whole document', async () => {
    /*
     * THE DEFECT THIS REFUSES, quoted from the shipped code: `describeSide` ended
     * `return JSON.stringify(value);` — so a scientist's default view of an asset
     * edit was `{"label":"Old label","run_ids":["r1"],"bytes":10}` at 11px. The raw
     * document is not deleted, it stops being the default.
     */
    useFixedClock();
    const { container } = mount({ events: [objectEvent()] });
    await screen.findByText('Asset Updated');

    // The summary line describes the SHAPE, counted off the value itself, and says
    // nothing about what the value means.
    const change = container.querySelector('.activity-change')?.textContent ?? '';
    expect(change).toContain(`3 ${LABELS.activityFieldPlural}`);
    expect(change).not.toContain('{');
    expect(change).not.toContain('"');

    // The two fields that MOVED are named; the one that did not is absent.
    const keys = [...container.querySelectorAll('.activity-diff-key')].map((n) => n.textContent);
    expect(keys).toEqual(['Label', 'Run Ids']);
    expect(keys).not.toContain('Bytes');

    // A key whose values are short primitives shows the change; one whose values are
    // not is NAMED and nothing more, which is the required fallback.
    const rows = [...container.querySelectorAll('.activity-diff-row')].map((n) => n.textContent);
    expect(rows[0]).toContain('Old label');
    expect(rows[0]).toContain('New label');
    expect(rows[1]).toContain(LABELS.activityChangedSeeBelow);
    expect(rows[1]).not.toContain('r2');
  });

  it('keeps the raw stored documents reachable, verbatim, behind a native details', async () => {
    useFixedClock();
    const { container } = mount({ events: [objectEvent()] });
    await screen.findByText('Asset Updated');

    const stored = container.querySelector('details.activity-stored');
    expect(stored).toBeTruthy();
    expect(stored?.hasAttribute('open')).toBe(false);
    expect(stored?.querySelector('summary')?.textContent).toBe(LABELS.activityShowStored);
    const pres = [...container.querySelectorAll('.activity-stored-pre')].map((n) => n.textContent);
    expect(pres).toHaveLength(2);
    // Verbatim — the internal key is NOT humanized inside the stored document, and
    // both sides are present and distinguishable.
    expect(pres[0]).toContain('"run_ids"');
    expect(pres[0]).toContain('Old label');
    expect(pres[1]).toContain('New label');
    expect(JSON.parse(pres[1] ?? '')).toEqual({
      label: 'New label',
      run_ids: ['r1', 'r2'],
      bytes: 10,
    });
  });

  it('reports changed keys in the DOCUMENT’s order, never sorted', async () => {
    /*
     * §5: a stored value must not be reordered or normalised in a way that changes
     * what it says. Sorting would replace the record's own order with a lexical
     * one — here `zulu` precedes `alpha` in the document, and must on screen.
     */
    useFixedClock();
    const { container } = mount({
      events: [
        objectEvent({
          before: { present: true, value: { zulu: 1, alpha: 1 } },
          after: { present: true, value: { zulu: 2, alpha: 2 } },
        }),
      ],
    });
    await screen.findByText('Asset Updated');
    const keys = [...container.querySelectorAll('.activity-diff-key')].map((n) => n.textContent);
    expect(keys).toEqual(['Zulu', 'Alpha']);
  });

  it('distinguishes an ADDED key from a REMOVED one, reusing absent/null honestly', async () => {
    useFixedClock();
    const { container } = mount({
      events: [
        objectEvent({
          before: { present: true, value: { gone: 'x' } },
          after: { present: true, value: { arrived: 'y' } },
        }),
      ],
    });
    await screen.findByText('Asset Updated');
    const rows = [...container.querySelectorAll('.activity-diff-row')].map((n) => n.textContent);
    expect(rows).toHaveLength(2);
    // The added key reads "was not set -> y"; the removed one "x -> was not set".
    // `present` is the discriminator on BOTH, exactly as at the top level.
    expect(rows[0]).toContain('Arrived');
    expect(rows[0]?.indexOf(LABELS.activityAbsent)).toBeLessThan(rows[0]?.indexOf('y') ?? -1);
    expect(rows[1]).toContain('Gone');
    expect(rows[1]?.indexOf('x')).toBeLessThan(rows[1]?.indexOf(LABELS.activityAbsent) ?? -1);
  });

  it('describes an array by how many values it holds, and interprets none of them', async () => {
    useFixedClock();
    const { container } = mount({
      events: [
        objectEvent({
          before: { present: true, value: [1, 2, 3] },
          after: { present: true, value: [1, 2, 3, 4] },
        }),
      ],
    });
    await screen.findByText('Asset Updated');
    const change = container.querySelector('.activity-change')?.textContent ?? '';
    expect(change).toContain(`3 ${LABELS.activityValuePlural}`);
    expect(change).toContain(`4 ${LABELS.activityValuePlural}`);
    // No key diff for arrays: naming positions as "fields" would invent a structure
    // the value does not have. The stored documents are still one click away.
    expect(container.querySelectorAll('.activity-diff-key')).toHaveLength(0);
    expect(container.querySelector('details.activity-stored')).toBeTruthy();
  });

  it('says so when two documents differ only in stored order, rather than showing an empty diff', async () => {
    useFixedClock();
    const { container } = mount({
      events: [
        objectEvent({
          before: { present: true, value: { a: 1, b: 2 } },
          after: { present: true, value: { b: 2, a: 1 } },
        }),
      ],
    });
    await screen.findByText('Asset Updated');
    expect(container.querySelector('.activity-change-note')?.textContent).toBe(
      LABELS.activityStoredOrderOnly,
    );
    expect(container.querySelectorAll('.activity-diff-row')).toHaveLength(0);
  });

  it('renders a long text change as labelled blocks, not as an inline arrow', async () => {
    /*
     * THE DEFECT THIS REFUSES: two long values joined by ` -> ` wrap into one
     * another and the reader cannot see where the old value ended. Above the
     * threshold the sides are labelled; because the labels are visible, the
     * `sr-only` "changed to" is unnecessary and deliberately absent there.
     */
    useFixedClock();
    const long = 'A'.repeat(120);
    const { container } = mount({
      events: [
        event({
          id: 'long',
          recorded_utc: agoMs(60 * 60 * 1000),
          before: { present: true, value: long },
          after: { present: true, value: `${long}B` },
        }),
      ],
    });
    await screen.findByText('Experiment Renamed');
    expect(container.querySelector('.activity-change-blocks')).toBeTruthy();
    // No inline change line for this row.
    expect(container.querySelectorAll('.activity-change')).toHaveLength(0);
    const labels = [...container.querySelectorAll('.activity-change-label')].map(
      (n) => n.textContent,
    );
    expect(labels).toEqual([LABELS.activityBefore, LABELS.activityAfter]);
    // Under the threshold nothing changes: the inline form is still the default.
    expect(LABELS.activityBefore).not.toBe(LABELS.activityAfter);
  });

  it('TELLS the reader when it truncates, with exact counts, and keeps the whole value', async () => {
    /*
     * `ACT-003b`'s rule is that nothing is truncated SILENTLY — not that nothing is
     * ever truncated. A single audit row must not become a page, so the shown
     * portion is capped, the exact character counts are stated, and the full value
     * is under the disclosure unchanged.
     */
    useFixedClock();
    const huge = 'B'.repeat(900);
    const { container } = mount({
      events: [
        event({
          id: 'huge',
          recorded_utc: agoMs(60 * 60 * 1000),
          before: { present: true, value: 'short before' },
          after: { present: true, value: huge },
        }),
      ],
    });
    await screen.findByText('Experiment Renamed');

    const notices = [...container.querySelectorAll('.activity-truncated')];
    expect(notices).toHaveLength(1);
    const notice = notices[0].textContent ?? '';
    expect(notice).toContain('400');
    expect(notice).toContain('900');
    expect(notice).toContain(LABELS.activityTruncatedRest);
    // The visible side really is cut...
    const sides = [...container.querySelectorAll('.activity-change-side')];
    expect(sides).toHaveLength(2);
    expect(sides[0].querySelector('.activity-before')?.textContent).toBe('short before');
    expect((sides[1].querySelector('.activity-after')?.textContent ?? '').length).toBe(400);
    // ...and the whole value is reachable, unchanged, in the disclosure.
    const pres = [...container.querySelectorAll('.activity-stored-pre')].map((n) => n.textContent);
    expect(pres[1]).toBe(huge);
    expect((pres[1] ?? '').length).toBe(900);
  });

  it('leaves a short primitive change exactly as it was — inline, with its sr-only relation', async () => {
    /*
     * A NEGATIVE CONTROL for the three branches above: `20 -> 35` must not have
     * acquired a disclosure, a block or a summary it does not need. Only the
     * structured and truncated cases pay for the extra chrome.
     */
    useFixedClock();
    const { container } = mount({
      events: [
        event({
          id: 'small',
          recorded_utc: agoMs(60 * 60 * 1000),
          before: { present: true, value: 20 },
          after: { present: true, value: 35 },
        }),
      ],
    });
    await screen.findByText('Experiment Renamed');
    const change = container.querySelector('.activity-change');
    expect(change?.querySelector('.activity-before')?.textContent).toBe('20');
    expect(change?.querySelector('.activity-after')?.textContent).toBe('35');
    expect(change?.querySelector('.sr-only')?.textContent).toBe(LABELS.activityChangedTo);
    expect(container.querySelectorAll('.activity-change-blocks')).toHaveLength(0);
    expect(container.querySelectorAll('.activity-diff')).toHaveLength(0);
    // ONE disclosure on the page: the standing actor note, and no stored-values one.
    expect(container.querySelectorAll('details')).toHaveLength(1);
    expect(container.querySelectorAll('details.activity-stored')).toHaveLength(0);
  });
});
