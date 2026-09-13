/*
 * THE EXPERIMENT LIBRARY SCREEN — search, facets, sort, folders, and the two
 * different empty states.
 *
 * THE ONE DEFECT THIS FILE MOST EXISTS TO PREVENT is the last test in it: an empty
 * RESULT is not an empty WORKSPACE. `queueIsEmpty` gates the first-run empty state
 * ("Start your first experiment") and it is derived from the UNFILTERED server
 * list; deriving it from the filtered rows instead would put that invitation in
 * front of somebody with forty records who had typed a word matching none of them.
 * That is the worst false claim this screen could make and it is one line of
 * carelessness away.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ExperimentsHome } from '../screens/ExperimentsHome';
import { LABELS } from '../lib/labels';
import type { ApiExperimentSummary } from '../lib/types';

function row(overrides: Partial<ApiExperimentSummary> = {}): ApiExperimentSummary {
  return {
    id: '01SYNTH0000000000000000001',
    title: 'A record',
    status: 'needs_attention',
    created_utc: '2026-07-12T00:00:01Z',
    pending_count: 0,
    evidenced_field_count: 0,
    exported: false,
    record_id: null,
    updated_utc: '2026-07-12T00:00:01Z',
    run_count: 0,
    open_proposal_count: 0,
    folder: '',
    technique: null,
    beamline: null,
    ...overrides,
  };
}

/**
 * A fetch stub narrow enough to be honest about what it serves. Only the two
 * routes this screen reads are answered; anything else rejects loudly, so a screen
 * that started making a third request would fail rather than silently degrade.
 */
function stub(experiments: ApiExperimentSummary[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(typeof input === 'string' ? input : (input as Request).url ?? input);
      if (url.includes('/api/experiments')) {
        return new Response(JSON.stringify({ experiments }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/api/health')) {
        return new Response(
          JSON.stringify({
            status: 'ok',
            mode: 'synthetic-only',
            experiment_storage: { configured: false, durable: false, state: 'ephemeral' },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      throw new Error(`unexpected request: ${url}`);
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderLibrary() {
  return render(
    <MemoryRouter
      initialEntries={['/experiments']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <ExperimentsHome />
    </MemoryRouter>,
  );
}

const BASE = 'XANES Example — CuO (Cu K-edge)';

const FIVE: ApiExperimentSummary[] = [
  row({ id: '01SEED000000000000000000A', title: `${BASE} · New Draft`, pending_count: 5 }),
  row({ id: '01SEED000000000000000000B', title: `${BASE} · Partially Completed`, pending_count: 2 }),
  row({ id: '01SEED000000000000000000C', title: `${BASE} · Ready to Export`, status: 'ready_to_export' }),
  row({ id: '01SEED000000000000000000D', title: `${BASE} · Export Review Required`, status: 'in_review' }),
  row({
    id: '01SEED000000000000000000E',
    title: `${BASE} · Exported Record`,
    status: 'done',
    exported: true,
    record_id: '01SEED000000000000000000E',
  }),
];

describe('the Library renders every column from ONE request', () => {
  it('makes exactly one experiments request and shows run, folder, technique and proposals', async () => {
    stub([
      row({
        id: '01RICH00000000000000000001',
        title: 'Rich row',
        folder: 'Campaign/October',
        technique: 'HERFD-XAS',
        beamline: '15-2',
        run_count: 3,
        open_proposal_count: 2,
      }),
    ]);
    renderLibrary();
    expect(await screen.findByText('Rich row')).toBeInTheDocument();
    // THE COLUMNS, all from the one list read.
    expect(screen.getByText('Campaign/October')).toBeInTheDocument();
    expect(screen.getByText('HERFD-XAS')).toBeInTheDocument();
    expect(screen.getByText('Beamline 15-2')).toBeInTheDocument();
    expect(screen.getByText('3 runs')).toBeInTheDocument();
    expect(screen.getByText('2 proposals waiting')).toBeInTheDocument();
    // ONE request for the list. `/api/health` is the shared cached read the mode
    // chip also uses, so it is not a Library fan-out.
    const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) =>
      String(c[0]),
    );
    expect(calls.filter((u) => u.includes('/api/experiments')).length).toBe(1);
  });

  it('renders NO placeholder for a column the server did not fill', async () => {
    // A freshly created record has no technique, no beamline, no runs and no
    // folder. Four grey dashes would say "we looked and there is nothing", which is
    // a claim; nothing at all says only that nothing has established them.
    stub([row({ title: 'Bare row' })]);
    const { container } = renderLibrary();
    expect(await screen.findByText('Bare row')).toBeInTheDocument();
    expect(container.querySelector('.exp-meta')).toBeNull();
  });
});

describe('LIB-002 · the five identically-rendered rows are told apart on the list', () => {
  it('shows a record id on each, because their display titles collide', async () => {
    stub(FIVE);
    const { container } = renderLibrary();
    await screen.findAllByText(BASE);
    // The display titles DO collide — five rows, one rendered title.
    expect(screen.getAllByText(BASE)).toHaveLength(5);
    // ...and every row carries a distinct id, so a reader can tell them apart
    // WITHOUT opening one, which is the acceptance property.
    const ids = [...container.querySelectorAll('.exp-meta-mono')].map((n) => n.textContent);
    expect(ids).toHaveLength(5);
    expect(new Set(ids).size).toBe(5);
  });

  it('gives the five rows five DISTINCT accessible names', async () => {
    stub(FIVE);
    renderLibrary();
    await screen.findAllByText(BASE);
    const names = screen.getAllByRole('link').map((n) => n.getAttribute('aria-label'));
    // A screen reader moving between links hears only the accessible name, so the
    // visible remedy is worth nothing there unless the id reaches this too.
    const rowNames = names.filter((n) => n?.startsWith(BASE));
    expect(rowNames).toHaveLength(5);
    expect(new Set(rowNames).size).toBe(5);
    expect(rowNames.every((n) => n?.includes('record id'))).toBe(true);
  });
});

describe('search, facets and sort', () => {
  it('narrows the list by search, and states a count of what is on screen', async () => {
    stub([row({ id: '01A00000000000000000000001', title: 'Copper oxide' }), row({ id: '01A00000000000000000000002', title: 'Nickel foil' })]);
    renderLibrary();
    await screen.findByText('Copper oxide');
    fireEvent.change(screen.getByLabelText(LABELS.librarySearchLabel), {
      target: { value: 'nickel' },
    });
    expect(screen.queryByText('Copper oxide')).toBeNull();
    expect(screen.getByText('Nickel foil')).toBeInTheDocument();
    expect(screen.getByText('1 of 2 experiments')).toBeInTheDocument();
  });

  it('a facet chip filters, and its COUNT stays over the whole list as you type', async () => {
    stub([
      row({ id: '01A00000000000000000000001', title: 'Needs me', status: 'needs_attention' }),
      row({ id: '01A00000000000000000000002', title: 'All done', status: 'done' }),
    ]);
    renderLibrary();
    await screen.findByText('Needs me');
    const chips = screen.getByRole('radiogroup', { name: 'Filter these experiments' });
    const needsAttention = within(chips).getByRole('radio', { name: /Needs Attention/ });
    expect(needsAttention).toHaveTextContent('1');
    fireEvent.click(needsAttention);
    expect(needsAttention).toHaveAttribute('aria-checked', 'true');
    expect(screen.queryByText('All done')).toBeNull();
    // THE CHIP'S NUMBER DID NOT MOVE. It counts the whole list, deliberately: a
    // number that shrank with the filter would answer a question nobody asked.
    expect(within(chips).getByRole('radio', { name: /Done/ })).toHaveTextContent('1');
  });

  it('renders NO chip for a facet that would match nothing', async () => {
    // A filter that leads to an empty list is not a filter, it is a dead end a
    // reader has to discover by pressing it — and `Ready to Export 0` invites the
    // conclusion that nothing is ready rather than that this workspace has none.
    stub([row({ title: 'Only one', status: 'needs_attention' })]);
    renderLibrary();
    await screen.findByText('Only one');
    const chips = screen.getByRole('radiogroup', { name: 'Filter these experiments' });
    expect(within(chips).queryByRole('radio', { name: /Ready to Export/ })).toBeNull();
    expect(within(chips).queryByRole('radio', { name: /In Review/ })).toBeNull();
    expect(within(chips).getByRole('radio', { name: /Needs Attention/ })).toBeInTheDocument();
  });

  it('sorting by name reorders the rendered rows', async () => {
    stub([
      row({ id: '01A00000000000000000000001', title: 'Zinc', updated_utc: '2026-08-01T00:00:00Z' }),
      row({ id: '01A00000000000000000000002', title: 'Aluminium', updated_utc: '2026-01-01T00:00:00Z' }),
    ]);
    const { container } = renderLibrary();
    await screen.findByText('Zinc');
    const titles = () => [...container.querySelectorAll('.exp-title')].map((n) => n.textContent);
    // Default is last-updated, newest first.
    expect(titles()).toEqual(['Zinc', 'Aluminium']);
    fireEvent.change(screen.getByLabelText(LABELS.librarySortLabel), {
      target: { value: 'title' },
    });
    expect(titles()).toEqual(['Aluminium', 'Zinc']);
  });
});

describe('folders', () => {
  it('lists the folders that exist, browses into one, and offers a way back', async () => {
    stub([
      row({ id: '01A00000000000000000000001', title: 'Inside', folder: 'Campaign' }),
      row({ id: '01A00000000000000000000002', title: 'Outside', folder: '' }),
    ]);
    renderLibrary();
    await screen.findByText('Inside');
    // BOTH are visible at the root: the root contains everything, filed or not,
    // which is what makes cross-folder search the default rather than a mode.
    expect(screen.getByText('Outside')).toBeInTheDocument();

    const folders = screen.getByRole('heading', { name: LABELS.libraryFoldersHeading });
    expect(folders).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Campaign/ }));
    expect(screen.getByText('Inside')).toBeInTheDocument();
    expect(screen.queryByText('Outside')).toBeNull();

    // THE WAY BACK IS THE BREADCRUMB, and the current folder is not a link.
    const trail = screen.getByRole('navigation', { name: 'Folder path' });
    expect(within(trail).getByText('Campaign')).toHaveAttribute('aria-current', 'page');
    fireEvent.click(within(trail).getByRole('button', { name: LABELS.libraryRootFolder }));
    expect(screen.getByText('Outside')).toBeInTheDocument();
  });

  it('offers NO control that would create, rename, delete or share a folder', async () => {
    // `CLAUDE.md` §15: build nothing that implies any of it exists. None of these is
    // a DISABLED control either — a disabled control says "not now", and the honest
    // answer here is "not at all".
    stub([row({ title: 'Filed', folder: 'Campaign' })]);
    const { container } = renderLibrary();
    await screen.findByText('Filed');
    /*
     * SCOPED TO THE FOLDER SECTION AND THE TOOLBAR, NOT TO THE WHOLE CONTAINER.
     * This screen also renders the app shell — the left nav, the top bar, the mode
     * chip — and none of that is this assertion's business. An unscoped sweep would
     * make the test fail for a reason it does not name the moment anything unrelated
     * in the chrome gained a disabled control or the word "share", which is the
     * failure mode that makes a guard get deleted rather than fixed.
     */
    const region =
      container.querySelector<HTMLElement>('.library-folders') ??
      (() => {
        throw new Error('the folder section did not render');
      })();
    const toolbar = container.querySelector<HTMLElement>('.library-toolbar')!;
    for (const scope of [region, toolbar]) {
      const text = scope.textContent ?? '';
      for (const forbidden of [
        /new folder/i,
        /create folder/i,
        /rename folder/i,
        /delete folder/i,
        /share/i,
      ]) {
        expect(text, `the Library offers ${forbidden}`).not.toMatch(forbidden);
      }
      // NOR A DISABLED ONE. A disabled control says "not now"; the honest answer
      // for all four of these is "not at all", so the control must be ABSENT.
      for (const node of scope.querySelectorAll('button')) {
        expect(node).not.toBeDisabled();
      }
    }
  });

  it('states what a folder IS, once, at the root', async () => {
    stub([row({ title: 'Filed', folder: 'Campaign' })]);
    renderLibrary();
    await screen.findByText('Filed');
    // Every reader arrives expecting Drive. Saying what a folder is conveys the four
    // absences without listing four capabilities we do not have.
    expect(screen.getByText(LABELS.libraryFolderModelNote)).toBeInTheDocument();
  });
});

describe('the two empty states are DIFFERENT, and this is the one that matters', () => {
  it('an empty WORKSPACE offers the first-run invitation', async () => {
    stub([]);
    renderLibrary();
    expect(await screen.findByText(LABELS.emptyExperimentsTitle)).toBeInTheDocument();
  });

  it('an empty RESULT never says "start your first experiment"', async () => {
    // THE DEFECT THIS FILE MOST EXISTS TO PREVENT. `queueIsEmpty` must be derived
    // from the UNFILTERED list; from the filtered rows it would tell somebody with
    // records that they have none.
    stub([row({ title: 'I exist' }), row({ id: '01A00000000000000000000002', title: 'So do I' })]);
    renderLibrary();
    await screen.findByText('I exist');
    fireEvent.change(screen.getByLabelText(LABELS.librarySearchLabel), {
      target: { value: 'nothing matches this' },
    });
    expect(screen.queryByText(LABELS.emptyExperimentsTitle)).toBeNull();
    expect(screen.getByText(LABELS.libraryNoResultsTitle)).toBeInTheDocument();
    // AND IT SAYS NOTHING IS LOST, then offers the one action that resolves it.
    expect(screen.getByText(LABELS.libraryNoResultsBody)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: LABELS.libraryClearFilters }));
    expect(screen.getByText('I exist')).toBeInTheDocument();
    expect(screen.getByText('So do I')).toBeInTheDocument();
  });
});
