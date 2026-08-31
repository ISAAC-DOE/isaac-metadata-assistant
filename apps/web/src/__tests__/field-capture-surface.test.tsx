/*
 * THE RECORD SCREEN'S FIELD ROWS, AND THE ONE RULE THEY MUST NOT BREAK.
 *
 * ── What was measured ───────────────────────────────────────────────────────
 *
 * A record created through `POST /api/experiments` served `GET .../draft` ->
 * `{"groups": []}`: ZERO field rows, in an app where `FieldGroup` is the only
 * field-rendering component. So a scientist who created a record saw no metadata field
 * at all and had no way to discover that a record holds a sample, a facility or a
 * technique. The server now returns the group SKELETON — a row for all 26 paths this
 * build can extract into or write at — and these are the assertions that make those
 * rows worth having.
 *
 * ── THE RULE ────────────────────────────────────────────────────────────────
 *
 * A CONTROL IS RENDERED ONLY WHERE A RECORD-LEVEL ROUTE ACCEPTS A VALUE. `CLAUDE.md`
 * §11 records the shipped defect this exists to prevent — *"a panel told the scientist
 * to enter a value on 25 fields, and 7 accept none"* — and `RunCard` and
 * `RunInheritedPanel` already enforce the same rule from their own sides. Measured over
 * HTTP: 2 of the 26 paths take a value at `POST .../answers`, 5 at `PATCH .../runs/{id}`,
 * 13 at `.../overrides` (one RUN's divergence, which is not the record's value), and 7
 * at nothing at all.
 *
 * So the negative assertions here are the load-bearing ones: the seven that accept
 * nothing render NO input, and neither do the eighteen whose only route is a run's.
 *
 * ── What this file does NOT do ──────────────────────────────────────────────
 *
 * It never re-derives a classification. `capture` is the server's own derivation from
 * the sets its write routes enforce (`apps/api/tests/test_draft_capture_surface.py`
 * proves those facts by SENDING the writes); every fixture below transcribes a measured
 * response rather than deciding what should be writable.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { act, configure, render, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { captureHint, canEnterOnRecord } from '../components/FieldCaptureControl';
import { FieldRow } from '../components/FieldRow';
import { draftGroupsToFieldGroups } from '../lib/adapt';
import { bundleRoutes, stubFetchRoutes, type RouteEntry } from '../test/apiFixtures';
import type { DraftFieldCapture } from '../lib/types';

configure({ asyncUtilTimeout: 5_000 });
/* See `run-workspace.test.tsx:67-112` for the full argument: vitest's own per-test
   deadline is ALSO 5,000 ms by default, which makes the raised query budget above
   unreachable and turns a slow mount into `Test timed out in 5000ms` — a failure that
   names neither the query nor the DOM. A HARNESS limit, not a performance claim. */
vi.setConfig({ testTimeout: 30_000 });

const ID = 'demo';
const BASE = `/api/experiments/${ID}`;

/** The five capture shapes the server actually serves, transcribed from a measured
 *  response (see the backend test's own table). */
const NOWHERE_OPEN_NS: DraftFieldCapture = {
  level: 'unclassified',
  record_writable: false,
  run_field_writable: false,
  run_overridable: false,
  choices: null,
  open_namespace: 'system.configuration',
};
const NOWHERE_STAMPED: DraftFieldCapture = { ...NOWHERE_OPEN_NS, open_namespace: null };
const RUN_FIELD: DraftFieldCapture = {
  level: 'run',
  record_writable: false,
  run_field_writable: true,
  run_overridable: false,
  choices: null,
  open_namespace: null,
};
const OVERRIDABLE: DraftFieldCapture = {
  level: 'experiment',
  record_writable: false,
  run_field_writable: false,
  run_overridable: true,
  choices: null,
  open_namespace: null,
};
const RECORD_ENUM: DraftFieldCapture = {
  level: 'experiment',
  record_writable: true,
  run_field_writable: false,
  run_overridable: false,
  choices: ['experimental', 'computational'],
  open_namespace: null,
};

const skeleton = (path: string, label: string, capture: DraftFieldCapture) => ({
  path,
  label,
  value: null,
  status: 'missing' as const,
  evidence_count: 0,
  source_types: [] as string[],
  present: false,
  capture,
});

/** A created record's draft, in the shape the server returns for one. */
const CREATED_DRAFT = {
  groups: [
    {
      title: 'System & Instrument',
      fields: [
        skeleton('system.configuration.n_scans', 'N Scans', NOWHERE_OPEN_NS),
        skeleton('system.domain', 'Domain', RECORD_ENUM),
        skeleton('system.facility.beamline', 'Beamline', OVERRIDABLE),
      ],
    },
    {
      title: 'Timestamps',
      fields: [
        skeleton('timestamps.acquired_start_utc', 'Acquired Start Utc', RUN_FIELD),
        skeleton('timestamps.created_utc', 'Created Utc', NOWHERE_STAMPED),
      ],
    },
  ],
};

function renderRecord(extra: Record<string, RouteEntry> = {}) {
  stubFetchRoutes({
    ...bundleRoutes(ID),
    [`GET ${BASE}/draft`]: { body: CREATED_DRAFT },
    ...extra,
  });
  render(
    <MemoryRouter
      initialEntries={[`/record/${ID}`]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

/** Open one collapsed draft block by its visible section name. */
async function openBlock(name: RegExp): Promise<HTMLElement> {
  const header = await screen.findByRole('button', { name });
  await act(async () => {
    fireEvent.click(header);
  });
  const section = header.closest('section[data-draft-block]');
  if (!section) throw new Error('draft block header is not inside a data-draft-block section');
  return section as HTMLElement;
}

/** The row whose mono path text is `path`. */
function rowFor(section: HTMLElement, path: string): HTMLElement {
  const found = Array.from(section.querySelectorAll('.field-row')).find(
    (el) => (el.querySelector('.field-path')?.textContent ?? '') === path,
  );
  if (!found) throw new Error(`no field row for ${path}`);
  return found as HTMLElement;
}

beforeEach(() => {
  vi.useRealTimers();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// --- the rule, asserted on the rendered screen --------------------------------

describe('a control is offered only where a record-level route accepts a value', () => {
  it('renders a row for every skeleton path, and an input for exactly one of them', async () => {
    renderRecord();
    const system = await openBlock(/System & Instrument/);

    // All three rows exist. Before the skeleton, none of them did.
    expect(system.querySelectorAll('.field-row')).toHaveLength(3);

    // And exactly ONE carries a control — the record-writable enum.
    const controls = system.querySelectorAll('.field-capture select');
    expect(controls).toHaveLength(1);
    expect(rowFor(system, 'system.domain').querySelector('select')).not.toBeNull();
  });

  it('offers NO input on a path no operation in this build accepts', async () => {
    renderRecord();
    const system = await openBlock(/System & Instrument/);
    const timestamps = await openBlock(/Timestamps/);

    for (const [section, path] of [
      [system, 'system.configuration.n_scans'],
      [timestamps, 'timestamps.created_utc'],
    ] as const) {
      const row = rowFor(section, path);
      expect(row.querySelector('input, select, textarea')).toBeNull();
      expect(within(row).queryByRole('button')).toBeNull();
    }
  });

  it('offers NO input on a path whose only route is a RUN’s', async () => {
    renderRecord();
    const system = await openBlock(/System & Instrument/);
    const timestamps = await openBlock(/Timestamps/);

    // An override is one RUN's divergence from a record-level value; a box here would
    // claim to set the record's value while setting something else.
    const overridable = rowFor(system, 'system.facility.beamline');
    expect(overridable.querySelector('input, select, textarea')).toBeNull();
    expect(overridable.textContent).toContain('run of this record');
    // And it does NOT read as the record's own value, which is the whole point: an
    // override is that run's, and copy calling it the record's would describe a
    // different operation from the one it names.
    expect(overridable.textContent).toContain('not to the record');

    const runField = rowFor(timestamps, 'timestamps.acquired_start_utc');
    expect(runField.querySelector('input, select, textarea')).toBeNull();
    expect(runField.textContent).toContain('Runs section');
  });

  it('says WHERE, per path, rather than one sentence for all of them', async () => {
    renderRecord();
    const system = await openBlock(/System & Instrument/);
    const timestamps = await openBlock(/Timestamps/);

    const sentences = [
      rowFor(system, 'system.configuration.n_scans'),
      rowFor(system, 'system.facility.beamline'),
      rowFor(timestamps, 'timestamps.acquired_start_utc'),
      rowFor(timestamps, 'timestamps.created_utc'),
    ].map((row) => row.querySelector('.field-capture-hint')?.textContent ?? '');

    expect(sentences.every((s) => s.length > 0)).toBe(true);
    // FOUR DISTINCT SENTENCES. A single shared string would be "true on average", read
    // about one field — the exact failure `valueWriteHint` was rewritten to remove.
    expect(new Set(sentences).size).toBe(4);
  });

  it('does not tell the reader the export stamp’s scope is an open question', async () => {
    /* `workspace.field_level` warns against exactly this conflation: all seven
       unwritable paths are `unclassified`, but `timestamps.created_utc` "is the one
       member of this list that does NOT need a scientific answer". */
    renderRecord();
    const system = await openBlock(/System & Instrument/);
    const timestamps = await openBlock(/Timestamps/);

    const six = rowFor(system, 'system.configuration.n_scans').textContent ?? '';
    const stamp = rowFor(timestamps, 'timestamps.created_utc').textContent ?? '';

    expect(six).toContain('open scientific question');
    expect(six).toContain('system.configuration');
    expect(stamp).not.toContain('open scientific question');
    expect(stamp).toContain('exporter');
  });
});

// --- the write ---------------------------------------------------------------

describe('the one control that exists', () => {
  it('offers the schema’s own values and nothing else, with no default choice', async () => {
    renderRecord();
    const system = await openBlock(/System & Instrument/);
    const select = rowFor(system, 'system.domain').querySelector('select') as HTMLSelectElement;

    const values = Array.from(select.options).map((o) => o.value);
    // The empty option is the honest rendering of a value the record does not hold —
    // NOT a placeholder, and not a value that can be sent.
    expect(values).toEqual(['', 'experimental', 'computational']);
    expect(select.value).toBe('');
  });

  it('sends the record’s If-Match to POST /answers, and reports that it landed', async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    renderRecord({
      [`POST ${BASE}/answers`]: {
        body: { pending: [], status: 'needs_attention' },
        // Recorded through the fixture's own spy below rather than here.
      },
    });
    const originalFetch = globalThis.fetch;
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      calls.push({ url: String(input), init: init as RequestInit });
      return originalFetch(input as RequestInfo, init);
    });

    const system = await openBlock(/System & Instrument/);
    const row = rowFor(system, 'system.domain');
    const select = row.querySelector('select') as HTMLSelectElement;

    await act(async () => {
      fireEvent.change(select, { target: { value: 'experimental' } });
    });
    await act(async () => {
      fireEvent.click(within(row).getByRole('button', { name: /Save/ }));
    });

    const write = calls.find((c) => c.url.includes('/answers') && c.init?.method === 'POST');
    expect(write, 'no POST to /answers was made').toBeTruthy();
    expect(JSON.parse(String(write!.init!.body))).toEqual({
      answers: { 'system.domain': 'experimental' },
      confirmed_by_user: true,
    });
    // The RECORD's token, not a run's — both operations here are the record's.
    expect((write!.init!.headers as Record<string, string>)['If-Match']).toMatch(/^".+"$/);

    await waitFor(() => {
      expect(row.querySelector('.field-capture-status')?.textContent).toContain('Saved');
    });
  });

  it('will not send a blank, because a blank is not a delete here', async () => {
    renderRecord();
    const system = await openBlock(/System & Instrument/);
    const row = rowFor(system, 'system.domain');
    const save = within(row).getByRole('button', { name: /Save/ }) as HTMLButtonElement;

    // Nothing chosen: Save is disabled rather than sending a clear that no route
    // performs. A control that appeared to remove a value would be promising a
    // removal that never happens.
    expect(save.disabled).toBe(true);
  });

  it('never presents a refused write as a success, and offers no silent retry', async () => {
    renderRecord({
      [`POST ${BASE}/answers`]: {
        status: 412,
        body: { error: 'stale_write', current_version: 'v9.9' },
      },
    });
    const system = await openBlock(/System & Instrument/);
    const row = rowFor(system, 'system.domain');
    const select = row.querySelector('select') as HTMLSelectElement;

    await act(async () => {
      fireEvent.change(select, { target: { value: 'computational' } });
    });
    await act(async () => {
      fireEvent.click(within(row).getByRole('button', { name: /Save/ }));
    });

    await waitFor(() => {
      expect(within(row).getByRole('alert').textContent).toMatch(/nothing was written/i);
    });
    expect(row.querySelector('.field-capture-status')?.textContent ?? '').not.toContain('Saved');
    // The reader's choice is kept. A refusal that also discarded the input would make
    // the retry a re-entry.
    expect(select.value).toBe('computational');
  });
});

// --- the copy rule, unit-tested over every shape ------------------------------

describe('captureHint', () => {
  it('says nothing at all when the server said nothing', () => {
    // An absent fact is not a refusal, and a sentence here would be invented.
    expect(captureHint(undefined)).toBeNull();
  });

  it('is silent exactly when the caller is rendering the control', () => {
    expect(captureHint(RECORD_ENUM, true)).toBeNull();
    // …and NOT silent when it is not, so a screen that cannot write still tells the
    // reader where the value goes rather than leaving the row unexplained.
    expect(captureHint(RECORD_ENUM, false)).toContain('on this record');
  });

  it('claims a record-level route only where one exists', () => {
    const forRun = captureHint(RUN_FIELD) ?? '';
    const forOverride = captureHint(OVERRIDABLE) ?? '';
    for (const sentence of [forRun, forOverride]) {
      expect(sentence).toContain('run');
    }
    expect(forRun).not.toBe(forOverride);
  });

  it('fails closed when a record-writable path arrives with no choices', () => {
    // A control cannot be offered without the schema's set, and the sentence says so
    // rather than implying the field is unwritable.
    const noChoices = { ...RECORD_ENUM, choices: null };
    expect(canEnterOnRecord(noChoices)).toBe(false);
    expect(captureHint(noChoices)).toContain('entered and confirmed on this record');
  });

  it('gives every capture shape a sentence, so no row is silently unexplained', () => {
    for (const shape of [NOWHERE_OPEN_NS, NOWHERE_STAMPED, RUN_FIELD, OVERRIDABLE, RECORD_ENUM]) {
      expect(captureHint(shape)).toBeTruthy();
    }
  });
});

// --- the collapsed summary ----------------------------------------------------

describe('the collapsed section summary', () => {
  /* THE DEFECT THIS CATCHES. `summarize` computed `all verified` from the STATUS SET,
     which a section of nothing but `missing` rows satisfies vacuously — so a created
     record's 13-row `System & Instrument` section would have read "13 fields · all
     verified" on the header a reader scans instead of opening. */
  const rows = (statuses: string[]) => [
    {
      title: 'System & Instrument',
      fields: statuses.map((status, i) => ({
        path: `system.p${i}`,
        label: `P${i}`,
        value: status === 'missing' ? null : 'x',
        status,
        evidence_count: 0,
        source_types: [] as string[],
        present: status !== 'missing',
      })),
    },
  ];

  it('never calls a section of unrecorded fields verified', () => {
    const [group] = draftGroupsToFieldGroups(rows(['missing', 'missing']) as never, new Map());
    expect(group.summary).toBe('2 fields · none recorded yet');
    expect(group.summary).not.toContain('verified');
  });

  it('counts what is recorded when a section is part-filled', () => {
    const [group] = draftGroupsToFieldGroups(
      rows(['verified', 'missing', 'missing']) as never,
      new Map(),
    );
    expect(group.summary).toBe('1 of 3 recorded · all verified');
  });

  it('reads exactly as it always did when every field is recorded', () => {
    const [group] = draftGroupsToFieldGroups(rows(['verified', 'inferred']) as never, new Map());
    expect(group.summary).toBe('2 fields · verified & inferred');
  });

  it('still leads with the blocker count, which a collapsed section must never hide', () => {
    const [group] = draftGroupsToFieldGroups(
      rows(['needs_confirmation', 'missing']) as never,
      new Map(),
    );
    expect(group.summary).toBe('1 field need you');
    expect(group.needsYouCount).toBe(1);
  });
});

// --- a row that HOLDS a value must not deny it -------------------------------

/*
 * THE DEFECT THESE CATCH, and why the fixtures above could not.
 *
 * Every row in `CREATED_DRAFT` is a skeleton (`present: false`), so every assertion
 * before this point reads a row the record genuinely holds nothing at. On a
 * fixture-seeded record — which is every worked example a reader opens — ALL 26 rows
 * are `present: true`, and seven of them are still refused by all six write routes.
 * Measured over HTTP on the first canonical example: `timestamps.created_utc` is
 * `2099-03-05T20:15:00Z` and `system.configuration.n_scans` is `6`. The copy those two
 * rows carried opened *"This version records no value here"*, one line under the value
 * the same row renders.
 */
const recorded = (path: string, label: string, value: unknown, capture: DraftFieldCapture) => ({
  path,
  label,
  value,
  status: 'verified' as const,
  evidence_count: 1,
  source_types: ['campaign_sheet'] as string[],
  present: true,
  capture,
});

const SEEDED_DRAFT = {
  groups: [
    {
      title: 'System & Instrument',
      fields: [recorded('system.configuration.n_scans', 'N Scans', 6, NOWHERE_OPEN_NS)],
    },
    {
      title: 'Timestamps',
      fields: [
        recorded('timestamps.created_utc', 'Created Utc', '2099-03-05T20:15:00Z', NOWHERE_STAMPED),
      ],
    },
  ],
};

/** Phrasings that assert the record holds nothing here. None may sit under a value. */
const DENIES_A_VALUE = /records no value|holds no value|has no value|there is no value/i;

describe('a row the record HAS a value at', () => {
  it('never denies the value it is rendering, on a path nothing can write', async () => {
    renderRecord({ [`GET ${BASE}/draft`]: { body: SEEDED_DRAFT } });
    const system = await openBlock(/System & Instrument/);
    const timestamps = await openBlock(/Timestamps/);

    const scans = rowFor(system, 'system.configuration.n_scans');
    const stamp = rowFor(timestamps, 'timestamps.created_utc');

    // The value is on the screen…
    expect(scans.textContent).toContain('6');
    expect(stamp.textContent).toContain('2099-03-05T20:15:00Z');
    // …so nothing in the row may say the record holds none. The sentence is about
    // where a value may be ENTERED, which is true whether or not one is there.
    for (const row of [scans, stamp]) {
      const hint = row.querySelector('.field-capture-hint')?.textContent ?? '';
      expect(hint).not.toMatch(DENIES_A_VALUE);
      expect(hint).toContain('nothing to type');
    }
    // And still no control, which is the rule these rows were always subject to.
    expect(scans.querySelector('input, select, textarea')).toBeNull();
    expect(stamp.querySelector('input, select, textarea')).toBeNull();
  });

  it('keeps the exporter sentence to the ONE path it is true of', () => {
    /* The last branch is reachable by more than one path: an unreadable schema makes
       `_schema_open_namespaces()` fail closed to `()`, and all six
       `system.configuration.*` rows then arrive with `open_namespace: null`. Telling
       them an exporter stamps the export time would be inventing a rule for them. */
    expect(captureHint(NOWHERE_STAMPED, false, 'timestamps.created_utc')).toContain('exporter');
    expect(captureHint(NOWHERE_STAMPED, false, 'system.configuration.n_scans')).not.toContain(
      'exporter',
    );
    // …and it still says the one thing that IS true of every path reaching it.
    expect(captureHint(NOWHERE_STAMPED, false, 'system.configuration.n_scans')).toContain(
      'nothing to type',
    );
  });
});

// --- the refusal's promise about the reader's choice --------------------------

describe('a refused write keeps what the reader chose', () => {
  it('does not replace an unsent choice when the record moves underneath it', async () => {
    /*
     * `STALE_MESSAGE` ends *"Nothing you chose has been lost."* — and the 412 branch
     * calls `onSaved()`, which silently refetches the whole record. So the ONE path
     * that produces this message is also the path on which the stored value most
     * plausibly changed. A box that follows the record unconditionally would reset the
     * reader's selection to somebody else's value in the same frame as the promise.
     */
    let reads = 0;
    renderRecord({
      [`GET ${BASE}/draft`]: () => {
        reads += 1;
        // After the first read the record holds a value somebody else wrote.
        return reads === 1
          ? { body: CREATED_DRAFT }
          : {
              body: {
                groups: [
                  {
                    title: 'System & Instrument',
                    fields: [
                      recorded('system.domain', 'Domain', 'experimental', RECORD_ENUM),
                    ],
                  },
                ],
              },
            };
      },
      [`POST ${BASE}/answers`]: { status: 412, body: { error: 'stale_write' } },
    });

    const system = await openBlock(/System & Instrument/);
    const row = rowFor(system, 'system.domain');
    const select = row.querySelector('select') as HTMLSelectElement;

    await act(async () => {
      fireEvent.change(select, { target: { value: 'computational' } });
    });
    await act(async () => {
      fireEvent.click(within(row).getByRole('button', { name: /Save/ }));
    });

    await waitFor(() => {
      expect(reads).toBeGreaterThan(1);
    });
    // The reader's unsent choice is still theirs…
    await waitFor(() => {
      const live = rowFor(
        document.querySelector('section[data-draft-block]') as HTMLElement,
        'system.domain',
      );
      expect((live.querySelector('select') as HTMLSelectElement).value).toBe('computational');
      // …and the record's own value is on the screen beside it, which is where the
      // message sends them to look.
      expect(live.textContent).toContain('experimental');
    });
  });

  it('adopts a new stored value when the reader has chosen nothing', () => {
    /* The other half, so the guard above cannot be satisfied by never syncing at all:
       with no unsent choice the box must follow the record. Asserted directly on the
       row, because the condition is a re-render with a different stored value and the
       screen adds nothing to it. */
    const capture = { experimentId: ID, version: 'v1', onSaved: () => {} };
    const before = skeleton('system.domain', 'Domain', RECORD_ENUM);
    const { rerender, container } = render(<FieldRow field={before as never} capture={capture} />);
    const select = container.querySelector('select') as HTMLSelectElement;
    expect(select.value).toBe('');

    rerender(
      <FieldRow
        field={recorded('system.domain', 'Domain', 'experimental', RECORD_ENUM) as never}
        capture={capture}
      />,
    );
    expect((container.querySelector('select') as HTMLSelectElement).value).toBe('experimental');
  });
});
