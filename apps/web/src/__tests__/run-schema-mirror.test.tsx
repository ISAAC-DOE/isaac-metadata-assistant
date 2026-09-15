/**
 * THE SCHEMA MIRROR BESIDE THE RUN EDITOR — and the one claim it must never make.
 *
 * Built on the project owner's ask (2026-09-14/15): *"there should be an
 * intuitive way users can both add runs and then see the schema being filled at
 * the same time, maybe like a split screen type of thing"*, then *"build a
 * provisional one and revise later, i want the view there so i can show angel
 * and hao the vision"*.
 *
 * WHAT THESE TESTS PROTECT. The pane reads `run.fields`, which is keyed by
 * dotted official path and carries THE FIVE RUN CONDITION FIELDS and nothing
 * else. Measured over HTTP: after answering `qc` on a run, `run.fields` was
 * still `{}` — the qc, series and descriptor answers live in the run's draft,
 * which the run-list payload does not serve.
 *
 * So a block with no observable path must read "not shown here", NEVER "nothing
 * yet". Telling a scientist `measurement` is empty on a run whose spectrum and
 * QC verdict are recorded would be this product's signature defect: a surface
 * stating something it never checked.
 */
import { describe, expect, it, vi, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';

import { RunSchemaMirror } from '../components/RunSchemaMirror';
import type { ApiRunView } from '../lib/types';

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


/** A run as the runs page serves it — the mirror now RECEIVES this, see below. */
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

const stateOf = (block: string): string => {
  const path = screen.getByText(block, { selector: '.rsm-path' });
  const row = path.closest('.rsm-block') as HTMLElement;
  return (row.querySelector('.rsm-state')?.textContent ?? '').trim();
};

describe('the schema mirror never claims a state it did not check', () => {
  it('MUTATION-GUARDED: an unobservable block reads "not shown here", not "nothing yet"', async () => {
    /*
     * MUTATION: dropping the `observable` check in `stateOf` — so every miss
     * falls through to 'empty' — makes this RED on `measurement` and
     * `descriptors`. That is the false-surface defect this pane could have
     * shipped.
     */
    stub();
    render(<RunSchemaMirror run={runFixture({})} />);
    await waitFor(() => expect(screen.getByText('measurement')).toBeTruthy());

    // No `RUN_FIELDS` path reaches these, so the pane cannot see them.
    expect(stateOf('measurement')).toBe('not shown here');
    expect(stateOf('descriptors')).toBe('not shown here');
    expect(stateOf('sample')).toBe('not shown here');
    // `context` and `timestamps` DO have run-field paths, so an empty run is
    // honestly empty there.
    expect(stateOf('context')).toBe('nothing yet');
    expect(stateOf('timestamps')).toBe('nothing yet');
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
    expect(stateOf('context')).toBe('recorded on this run');
    // …and says nothing new about the blocks it still cannot see.
    expect(stateOf('measurement')).toBe('not shown here');
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
    /* The schema is still worth showing; no block is claimed as recorded on the
       strength of a read that failed. */
    expect(stateOf('context')).toBe('nothing yet');
    expect(screen.queryByText(/recorded on this run/)).toBeNull();
  });

  it('says on the pane that the run/record grouping is a draft', async () => {
    /*
     * The honesty this whole pane rests on: the STRUCTURE is exact, the SPLIT is
     * a starting point for a conversation with the scientist who owns it, and
     * nothing here gates export.
     */
    stub();
    render(<RunSchemaMirror run={runFixture({})} />);
    await waitFor(() => expect(screen.getByText('measurement')).toBeTruthy());
    const draft = document.querySelector('.rsm-draft') as HTMLElement;
    expect(draft).not.toBeNull();
    expect(draft.textContent).toMatch(/Draft grouping/);
    expect(draft.textContent).toMatch(/still to be confirmed/);
    expect(draft.textContent).toMatch(/Nothing here gates export/i);
  });

  it('names the schema it read, rather than implying a hand-written list', async () => {
    stub();
    render(<RunSchemaMirror run={runFixture({})} />);
    await waitFor(() => expect(screen.getByText('measurement')).toBeTruthy());
    expect(screen.getByText(/vendored ISAAC v1.05 schema/)).toBeTruthy();
  });
});
