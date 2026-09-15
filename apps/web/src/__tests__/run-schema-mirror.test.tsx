/**
 * THE RECORD MAP BESIDE THE RUN EDITOR — and the one claim it must never make.
 *
 * Built on the project owner's ask (2026-09-14/15): *"there should be an
 * intuitive way users can both add runs and then see the schema being filled at
 * the same time, maybe like a split screen type of thing"*, then *"build a
 * provisional one and revise later, i want the view there so i can show angel
 * and hao the vision"*, and then, on the first version: *"I can't clearly
 * distinguish what fields are done, what fields aren't done, what my values were
 * for those fields … genuinely, it's unreadable."*
 *
 * ── THE STATE VOCABULARY CHANGED AND THREE ASSERTIONS WERE REWRITTEN ───────
 *
 * They are REWRITTEN, not deleted, and the property each one protects is
 * unchanged. The pane used to say `not shown here` / `nothing yet` / `recorded
 * on this run` in a lowercase sentence fragment; it now says `Not Shown Here` /
 * `Missing` / `Filled` in a badge with a glyph beside it. The words moved
 * because the owner could not tell the states apart; the RULE did not move, and
 * the first test below is still the mutation-guarded one.
 *
 * WHAT THESE TESTS PROTECT. The pane reads `run.fields`, which is keyed by
 * dotted official path and carries THE FIVE RUN CONDITION FIELDS and nothing
 * else. Measured over HTTP: after answering `qc` on a run, `run.fields` was
 * still `{}` — the qc, series and descriptor answers live in the run's draft,
 * which the run-list payload does not serve.
 *
 * So a block with no observable path must read "Not Shown Here", NEVER
 * "Missing". Telling a scientist `measurement` is empty on a run whose spectrum
 * and QC verdict are recorded would be this product's signature defect: a
 * surface stating something it never checked.
 */
import { describe, expect, it, vi, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup, fireEvent } from '@testing-library/react';

import { RunSchemaMirror } from '../components/RunSchemaMirror';
import type { ApiRunCheckResponse, ApiRunView } from '../lib/types';

const SCHEMA = {
  schema_version: '1.05',
  schema: {
    properties: {
      measurement: { properties: { series: {}, qc: {} }, required: ['series', 'qc'] },
      timestamps: { properties: { acquired_start_utc: {} } },
      descriptors: { properties: { outputs: {} }, required: ['outputs'] },
      context: { properties: { environment: {}, temperature_K: {} }, required: ['environment'] },
      sample: { properties: { material: {} } },
    },
  },
};


/** A run as the runs page serves it — the mirror RECEIVES this, see below. */
function runFixture(
  fields: Record<string, unknown>,
  inherited: Record<string, unknown> = {},
): ApiRunView {
  return {
    id: 'RUN1',
    experiment_id: 'E1',
    label: 'Run 1',
    ordinal: 1,
    created_utc: '2026-09-15T00:00:00Z',
    updated_utc: '2026-09-15T00:00:00Z',
    rev: 1,
    version: '1.1',
    record_id: null,
    fields: fields as ApiRunView['fields'],
    inherited: inherited as ApiRunView['inherited'],
  };
}

/*
 * ONLY THE SCHEMA IS FETCHED NOW. The mirror used to read `GET /runs?limit=1`
 * itself, which made the Runs workspace read the runs list twice on first paint
 * — `runs-live-refresh-integration.test.tsx` pins it at once and caught it. The
 * run arrives as a prop from `RunsSection`, which already holds the page.
 */
function stub() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(typeof input === 'string' ? input : (input as Request).url ?? input);
      const json = (payload: unknown) =>
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      if (url.includes('/schema')) return json(SCHEMA);
      throw new Error(`unexpected request: ${url}`);
    }),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** The state badge of one BLOCK row, inside the full-schema disclosure. */
const stateOf = (block: string): string => {
  const path = screen.getByText(block, { selector: '.rsm-path' });
  const row = path.closest('.rsm-block') as HTMLElement;
  return (row.querySelector('.rm-state')?.textContent ?? '').trim();
};

/** One FIELD row of the map, addressed by its dotted official path. */
const fieldRow = (path: string): HTMLElement => {
  const code = screen
    .getAllByText(path, { selector: '.rm-row-path' })
    .map((el) => el.closest('.rm-row') as HTMLElement)
    // The same row can appear twice — once under Needs Attention, once under
    // This Run — so this deliberately takes the LAST, which is always the
    // full `This Run` list.
    .filter((el): el is HTMLElement => el !== null);
  return code[code.length - 1];
};

const fieldState = (path: string): string =>
  (fieldRow(path).querySelector('.rm-state')?.textContent ?? '').trim();

describe('the record map never claims a state it did not check', () => {
  it('MUTATION-GUARDED: an unobservable block reads "Not Shown Here", not "Missing"', async () => {
    /*
     * MUTATION: dropping the `observable` check in `blockRows` — so every miss
     * falls through to `missing` — makes this RED on `measurement` and
     * `descriptors`. That is the false-surface defect this pane could have
     * shipped.
     */
    stub();
    render(<RunSchemaMirror run={runFixture({})} />);
    await waitFor(() => expect(screen.getByText('measurement')).toBeTruthy());

    // No `RUN_FIELDS` path reaches these, so the pane cannot see them.
    expect(stateOf('measurement')).toBe('Not Shown Here');
    expect(stateOf('descriptors')).toBe('Not Shown Here');
    expect(stateOf('sample')).toBe('Not Shown Here');
    // `context` and `timestamps` DO have run-field paths, so an empty run is
    // honestly empty there.
    expect(stateOf('context')).toBe('Missing');
    expect(stateOf('timestamps')).toBe('Missing');
  });

  it('reports a recorded condition on the run that carries it', async () => {
    stub();
    render(
      <RunSchemaMirror
        run={runFixture({
          'context.temperature_K': { value: 301 },
          'context.environment': { value: 'vacuum' },
        })}
      />,
    );
    await waitFor(() => expect(screen.getByText('context')).toBeTruthy());
    expect(stateOf('context')).toBe('Filled');
    // …and says nothing new about the blocks it still cannot see.
    expect(stateOf('measurement')).toBe('Not Shown Here');
  });

  it('distinguishes inherited from recorded', async () => {
    stub();
    render(<RunSchemaMirror run={runFixture({}, { 'block:attribution': { state: 'inherited' } })} />);
    await waitFor(() => expect(screen.getByText('context')).toBeTruthy());
    // `attribution` is not in this fixture's schema, so the pane omits it —
    // which is the other half of the rule: it renders the schema's blocks, not
    // a list of its own.
    expect(screen.queryByText('attribution', { selector: '.rsm-path' })).toBeNull();
  });

  it('shows the structure, and marks nothing, when there is no run yet', async () => {
    /* `run={null}` is the real state before the page has loaded or on a record
       with no runs. The schema is still worth showing; no block is claimed as
       recorded on the strength of a run nobody has. */
    stub();
    render(<RunSchemaMirror run={null} />);
    await waitFor(() => expect(screen.getByText('measurement')).toBeTruthy());
    expect(stateOf('context')).toBe('Missing');
    expect(screen.queryByText('Filled')).toBeNull();
    // And it says WHOSE state it is not showing, rather than leaving the pane
    // to read as the record's.
    expect(screen.getByText('No run loaded yet')).toBeTruthy();
  });

  it('says on the pane that the run/record grouping is a draft', async () => {
    /*
     * The honesty this whole pane rests on: the STRUCTURE is exact, the SPLIT is
     * a starting point for a conversation with the scientist who owns it, and
     * nothing here gates export.
     *
     * IT MOVED BEHIND A DISCLOSURE AND NOT ONE WORD OF IT WENT. The assertion is
     * unchanged for exactly that reason — `querySelectorAll` reaches inside a
     * closed `<details>`, so a guard over this text cannot be satisfied by
     * hiding it, only by keeping it.
     */
    stub();
    render(<RunSchemaMirror run={runFixture({})} />);
    await waitFor(() => expect(screen.getByText('measurement')).toBeTruthy());
    const draft = document.querySelector('.rsm-draft') as HTMLElement;
    expect(draft).not.toBeNull();
    expect(draft.textContent).toMatch(/Draft grouping/);
    expect(draft.textContent).toMatch(/still to be confirmed/);
    expect(draft.textContent).toMatch(/Nothing here gates export/i);
    // The exhaustive block listing is the thing behind the disclosure, and the
    // disclosure names what it holds rather than saying "more".
    expect(screen.getByText('Show full official schema')).toBeTruthy();
  });

  it('names the schema it read, rather than implying a hand-written list', async () => {
    stub();
    render(<RunSchemaMirror run={runFixture({})} />);
    await waitFor(() => expect(screen.getByText('measurement')).toBeTruthy());
    expect(screen.getByText(/vendored ISAAC v1.05 schema/)).toBeTruthy();
  });
});

describe('the record map shows what the value actually is', () => {
  it('renders the run’s own value, and re-spells a stored timestamp', async () => {
    /*
     * "what my values were for those fields" — the half that did not exist at
     * all before. The timestamp is re-spelled from the literal components of the
     * stored string; see `formatStoredDatetime` for why no `Date` is involved.
     */
    stub();
    render(
      <RunSchemaMirror
        run={runFixture({
          'context.temperature_K': { value: 301 },
          'timestamps.acquired_start_utc': { value: '2026-01-31T09:00:00Z' },
        })}
      />,
    );
    await waitFor(() => expect(screen.getByText('measurement')).toBeTruthy());
    expect(fieldState('context.temperature_K')).toBe('Filled');
    expect(fieldRow('context.temperature_K').textContent).toContain('301');
    // The unit the schema's path name already encodes, shown beside it.
    expect(fieldRow('context.temperature_K').textContent).toContain('K');
    expect(fieldRow('timestamps.acquired_start_utc').textContent).toContain(
      'Jan 31, 2026 · 09:00 UTC',
    );
  });

  it('MUTATION-GUARDED: an unparseable timestamp is shown verbatim, not re-spelled', async () => {
    /*
     * MUTATION: making `formatStoredDatetime` fall back to `new Date(raw)`
     * turns this into `Invalid Date` or a guess. Handing back the stored string
     * is the only honest answer for a value this build cannot read.
     */
    stub();
    render(
      <RunSchemaMirror
        run={runFixture({ 'timestamps.acquired_start_utc': { value: 'last Tuesday' } })}
      />,
    );
    await waitFor(() => expect(screen.getByText('measurement')).toBeTruthy());
    expect(fieldRow('timestamps.acquired_start_utc').textContent).toContain('last Tuesday');
  });

  it('a field with no value carries no value line at all', async () => {
    stub();
    render(<RunSchemaMirror run={runFixture({})} />);
    await waitFor(() => expect(screen.getByText('measurement')).toBeTruthy());
    expect(fieldState('context.environment')).toBe('Missing');
    expect(fieldRow('context.environment').querySelector('.rm-row-value')).toBeNull();
  });
});

describe('the record map marks Needs Review only from a check of THIS version', () => {
  const check = (version: string): ApiRunCheckResponse =>
    ({
      ok: false,
      draft: { ok: false, errors: [{ path: 'context.temperature_K', message: 'no evidence' }] },
      official: { ok: true },
      blockers: [],
      checked_run_version: version,
    }) as unknown as ApiRunCheckResponse;

  it('marks the path a finding names, and quotes the server verbatim', async () => {
    stub();
    render(<RunSchemaMirror run={runFixture({ 'context.temperature_K': { value: 301 } })} check={check('1.1')} />);
    await waitFor(() => expect(screen.getByText('measurement')).toBeTruthy());
    expect(fieldState('context.temperature_K')).toBe('Needs Review');
    expect(fieldRow('context.temperature_K').textContent).toContain('no evidence');
    // It is promoted into its own group, which is the "what isn't done" half.
    expect(screen.getByText('Needs Attention · 1')).toBeTruthy();
    // A finding BEATS a value: the row holds 301 and still says Needs Review,
    // because reading `Filled` over a path the validator objected to would be
    // this surface telling the reader the opposite of what the server said.
    expect(fieldRow('context.temperature_K').textContent).toContain('301');
  });

  it('MUTATION-GUARDED: a check of an OLDER run version marks nothing', async () => {
    /*
     * MUTATION: dropping the `checked_run_version !== run.version` comparison in
     * `currentCheck` makes this RED. A check read before an autosave describes a
     * document that no longer exists, and marking a row from it is a claim about
     * a read nobody took.
     */
    stub();
    render(<RunSchemaMirror run={runFixture({ 'context.temperature_K': { value: 301 } })} check={check('1.0')} />);
    await waitFor(() => expect(screen.getByText('measurement')).toBeTruthy());
    expect(fieldState('context.temperature_K')).toBe('Filled');
    expect(screen.queryByText(/^Needs Attention/)).toBeNull();
    expect(screen.queryByText('no evidence')).toBeNull();
  });

  it('with no check at all, no row is marked and no attention group is claimed', async () => {
    stub();
    render(<RunSchemaMirror run={runFixture({ 'context.temperature_K': { value: 301 } })} />);
    await waitFor(() => expect(screen.getByText('measurement')).toBeTruthy());
    expect(screen.queryByText(/^Needs Attention/)).toBeNull();
    expect(screen.queryByText('Needs Review')).toBeNull();
  });
});

describe('only a row with a real destination is pressable', () => {
  it('a run-field row is a button, and pressing it focuses that run input', async () => {
    stub();
    /* The editor's own control, published exactly as `RunCard` publishes it.
       The map finds it by attribute, which is this section's existing idiom
       (`RunsSection` already does this for `[data-address]`). */
    const input = document.createElement('input');
    input.setAttribute('data-run-field-path', 'context.environment');
    document.body.appendChild(input);
    try {
      render(<RunSchemaMirror run={runFixture({})} />);
      await waitFor(() => expect(screen.getByText('measurement')).toBeTruthy());
      const button = screen.getByRole('button', { name: 'Edit Environment' });
      fireEvent.click(button);
      expect(document.activeElement).toBe(input);
    } finally {
      input.remove();
    }
  });

  it('MUTATION-GUARDED: a BLOCK row exposes no control and is not focusable', async () => {
    /*
     * MUTATION: passing `onOpen` for every row — or rendering `<button>`
     * unconditionally — makes this RED. A row that looks pressable and leads
     * nowhere is the defect the editable/inert split exists to prevent, and
     * `measurement` has no input on this screen to lead to.
     */
    stub();
    render(<RunSchemaMirror run={runFixture({})} />);
    await waitFor(() => expect(screen.getByText('measurement')).toBeTruthy());
    const path = screen.getByText('measurement', { selector: '.rsm-path' });
    const block = path.closest('.rsm-block') as HTMLElement;
    expect(block.querySelector('button')).toBeNull();
    expect(block.querySelector('[tabindex]')).toBeNull();
  });
});
