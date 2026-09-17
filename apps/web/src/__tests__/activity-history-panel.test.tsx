import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';

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
    mount({ events: three, total: 200, matched: 200, returned: 3, highest_seq: 200 });
    const counts = await screen.findByText(/of 200/);
    expect(counts.textContent).toContain('3 of 200');
    expect(counts.textContent).not.toMatch(/\b3 of 3\b/);
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
    mount({ events: [], total: 0, matched: 0, returned: 0, highest_seq: 0 });
    expect(await screen.findByText(LABELS.activityEmpty)).toBeTruthy();
    expect(screen.queryByRole('list')).toBeNull();
  });

  it('offers NO control that writes, because an event is recorded by the act it describes', async () => {
    /*
     * Structural, not a promise: `api` exposes no activity mutator at all. This
     * asserts the surface as well — a button here would be a client asking for an
     * audit row, which is the one thing an audit log must not accept.
     */
    mount();
    await screen.findByText('Experiment Renamed');
    const panel = screen.getByRole('region', { name: LABELS.activityTitle });
    expect(within(panel).queryAllByRole('button')).toHaveLength(0);
    expect(within(panel).queryAllByRole('textbox')).toHaveLength(0);
    expect('listActivity' in api).toBe(true);
    expect(Object.keys(api).filter((k) => /activity/i.test(k))).toEqual(['listActivity']);
  });

  it('reports a failed read without claiming the history is empty', async () => {
    /*
     * The two are different claims. "Nothing has been recorded" about a record whose
     * history merely failed to load is a false statement about the science.
     */
    vi.spyOn(api, 'listActivity').mockRejectedValue(new Error('down'));
    render(<ActivityHistoryPanel experimentId="demo" />);
    expect(await screen.findByText(LABELS.activityUnavailable)).toBeTruthy();
    expect(screen.queryByText(LABELS.activityEmpty)).toBeNull();
  });
});
