import { describe, it, expect, afterEach, vi, type Mock } from 'vitest';
import { render, fireEvent, within, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProjectMemory } from '../screens/ProjectMemory';
import {
  stubFetchRoutes,
  stubFetchDown,
  graphStatusAvailable,
  graphStatusPreRegen,
  graphStatusMalformed,
  graphStatusUnavailable,
  memoryFilesAvailable,
  memoryFilesUnavailable,
  memoryConceptsAvailable,
  memoryConceptsUnavailable,
} from '../test/apiFixtures';

/*
 * P24.10 — the Project Memory status detail card under the SEPARATED-freshness
 * contract. The old single conflated `status` verdict is gone; the screen now
 * reads `availability` to decide available vs degraded, and renders the three
 * individually-honest axes (Snapshot Integrity / Memory Policy / Indexed
 * Sources) with scope-accurate microcopy. Every assertion is driven by a
 * stubbed GET /api/graph/status response (no-fake-data invariant).
 */

/*
 * THE HARNESS DEADLINE. This file was NOT on the list of known-flaky graph
 * suites; it was found by measurement, failing `renders exactly the three
 * approved chips in order` by HARNESS TIMEOUT on an untouched tree in the same
 * run that took down the two graph files, and passing on the next identical run.
 * It mounts the same Project Memory screen, so it is the same contention, not a
 * second defect. No time budget is declared here either. See
 * `experiment-graph.test.tsx` for the full reasoning.
 */
vi.setConfig({ testTimeout: 30000 });

function renderScreen() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ProjectMemory />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('P24.10 · status card — available, fully current', () => {
  it('renders the Available chip, real counts, and the three separated axes with approved wording', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusAvailable },
      'GET /api/memory/files': { body: memoryFilesAvailable },
    });
    const { findByText, getByText, container } = renderScreen();

    await findByText('Memory Available');

    // counts come only from the API overview
    expect(getByText('2296')).toBeInTheDocument();
    expect(getByText('3447')).toBeInTheDocument();
    expect(getByText('214')).toBeInTheDocument();
    expect(getByText('190')).toBeInTheDocument(); // "Served Files (Path Set)" = file_count
    expect(getByText('19')).toBeInTheDocument();

    // the three separated axes, each individually honest
    expect(getByText('Snapshot Integrity')).toBeInTheDocument();
    expect(getByText('Memory Policy')).toBeInTheDocument();
    expect(getByText('Indexed Sources')).toBeInTheDocument();
    expect(getByText('Verified')).toBeInTheDocument(); // integrity
    // policy + indexed sources both "Current" (two pills carry the same label)
    expect(container.querySelectorAll('.memory-axis-state').length).toBe(3);
    expect(container.textContent).toMatch(/Current/);

    // indexed-sources scope caveat is stated honestly (proven only over served files)
    expect(getByText(/only the files already in the snapshot/i)).toBeInTheDocument();
    expect(getByText(/re-index/i)).toBeInTheDocument();

    // never a verdict / validity claim on the memory plane
    expect(container.textContent).not.toMatch(/\b(PASS|FAIL|valid|invalid)\b/i);
  });

  it('describes what memory indexes honestly, without inventing counts the API did not return', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusAvailable },
      'GET /api/memory/files': { body: memoryFilesAvailable },
    });
    const { findByText } = renderScreen();
    await findByText(/source code, docs, schema, and test fixtures/i);
  });

  it('renders a derived relative age only when graph_mtime is present', async () => {
    const NOW = new Date('2026-07-16T12:00:00Z');
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(NOW);
    const withAge = { ...graphStatusAvailable, graph_mtime: NOW.getTime() / 1000 - 3 * 3600 };
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: withAge },
      'GET /api/memory/files': { body: memoryFilesAvailable },
    });
    const { findByText, getByText } = renderScreen();
    await findByText('Memory Available');
    expect(getByText('built 3 hours ago')).toBeInTheDocument();
  });
});

describe('P24.10 · status card — pre-regen snapshot (available, currency not yet provable)', () => {
  it('renders Available with real counts, integrity Verified, policy + indexed sources Unknown, and no stale warning', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusPreRegen },
      'GET /api/memory/files': { body: memoryFilesAvailable },
    });
    const { findByText, getByText, queryByText, container } = renderScreen();

    await findByText('Memory Available');

    // available → real counts render ("Served Files (Path Set)" = file_count = 9)
    expect(getByText('42')).toBeInTheDocument();
    expect(getByText('17')).toBeInTheDocument();
    expect(getByText('9')).toBeInTheDocument();
    expect(getByText('3')).toBeInTheDocument();

    // integrity is proven; policy + indexed-sources currency is honestly Unknown
    expect(getByText('Verified')).toBeInTheDocument();
    // two axes read "Unknown" — quiet/neutral, never an "out of date" warning
    expect(container.querySelectorAll('.memory-axis-state.axis-quiet').length).toBe(2);
    expect(queryByText(/out of date/i)).toBeNull();

    // the indexed-sources scope caveat is still shown
    expect(getByText(/only the files already in the snapshot/i)).toBeInTheDocument();

    /* served_file_count is null (pre-regen) — no broken/empty "served" figure.
     *
     * This used to read `not.toMatch(/served files/i)`, which worked only because
     * the one figure derived from `file_count` was then labelled "Indexed files".
     * That label was the SAME number the Statistics dashboard labels "Served
     * Files (Path Set)" — one backend field under two names, on an endpoint that
     * genuinely carries two similar counts — so the screen now uses the
     * scope-naming label and the word "served" is legitimately on the page.
     *
     * The guard is restated as what it was actually protecting, and is now
     * stricter than the substring form: EXACTLY ONE served-labelled figure
     * exists, it names its scope, and its value is `file_count` (9) — never the
     * null status-plane `served_file_count`, which would render blank or as a
     * fabricated number. */
    const servedRows = [...container.querySelectorAll('.memory-figure')].filter((row) =>
      /served/i.test(row.querySelector('dt')?.textContent ?? ''),
    );
    expect(servedRows.map((row) => row.querySelector('dt')?.textContent?.trim())).toEqual([
      'Served Files (Path Set)',
    ]);
    expect(servedRows[0].querySelector('dd')?.textContent?.trim()).toBe('9');
    expect(graphStatusPreRegen.served_file_count).toBeNull();

    // no fabricated age (graph_mtime null, so never a 1970 epoch artifact)
    expect(container.textContent).not.toMatch(/1970/);
    expect(container.textContent).not.toMatch(/\bAge\b/);

    // available, so NOT the degraded/unavailable panel
    expect(queryByText(/artifacts are not present/i)).toBeNull();
    expect(container.querySelector('.memory-figures')).not.toBeNull();

    expect(container.textContent).not.toMatch(/\b(PASS|FAIL|valid|invalid)\b/i);
  });
});

describe('P24.10 · status card — malformed snapshot (unavailable + integrity malformed)', () => {
  it('degrades quietly, surfaces Snapshot Integrity Malformed, shows no counts, and no error styling', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusMalformed },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
    });
    const { findByText, getByText, container } = renderScreen();

    await findByText('Memory Unavailable');

    // the malformed integrity axis is surfaced, honestly explained
    expect(getByText('Snapshot Integrity')).toBeInTheDocument();
    expect(getByText('Malformed')).toBeInTheDocument();
    expect(getByText(/present but malformed/i)).toBeInTheDocument();

    // no counts, and never the error / verdict visual language
    expect(container.querySelector('.memory-figures')).toBeNull();
    expect(container.querySelector('.fetch-state.error')).toBeNull();
    expect(container.querySelector('.verdict-fail')).toBeNull();
    expect(container.textContent).not.toMatch(/\b(PASS|FAIL|valid|invalid)\b/i);
  });
});

describe('P24.10 · status card — unavailable (no artifact present)', () => {
  /*
   * The copy this asserts was CORRECTED, and the assertions were tightened to
   * the new true strings rather than relaxed.
   *
   * It used to say "the hosted demo does not currently ship the Graphify graph
   * artifacts; when run locally against local artifacts, Project Memory works".
   * Both halves became false: `apps/api/isaac_api/data/memory-snapshot.json` and
   * `memory-graph-detail.json` are tracked in git and ship in the image (the
   * Dockerfile's `COPY apps/api/ apps/api/`), and `memory.py::_resolve_reader_choice`
   * PREFERS that packaged snapshot over any live `graphify-out/`. So the hosted
   * deployment does have Project Memory, and the panel now describes the
   * condition that actually produces it — naming the two possibilities the
   * browser cannot distinguish and asserting neither.
   */
  it('renders an honest unavailable panel that names the real condition, no counts, no error styling', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
    });
    const { findByText, container } = renderScreen();

    await findByText('Memory Unavailable');
    expect(
      await findByText(/no memory graph artifact was found where this build reads it/i),
    ).toBeInTheDocument();
    // The verifiable fact: the artifacts ARE shipped.
    expect(container.textContent).toMatch(/ships its memory artifacts with the application/i);
    // Two possible conditions, neither asserted — no signal separates them.
    expect(container.textContent).toMatch(/cannot tell which of two conditions applies/i);
    expect(container.textContent).toMatch(/not included in this build/i);
    expect(container.textContent).toMatch(
      /configured to read a memory source that is not present/i,
    );
    // The retired claims must not come back.
    expect(container.textContent).not.toMatch(/hosted demo does not currently ship/i);
    expect(container.textContent).not.toMatch(/Graphify graph artifacts/i);
    expect(container.textContent).not.toMatch(/institution-hosted/i);
    expect(container.textContent).not.toMatch(/behind login/i);
    // No locality claim at all: this panel renders on the hosted deployment too.
    expect(container.querySelector('.memory-unavailable')!.textContent).not.toMatch(
      /\blocal\b|\blocally\b|localhost|uvicorn/i,
    );
    // The forward-looking sentence is kept, with the corrected access vocabulary.
    expect(container.textContent).toMatch(/pointed at a richer approved source/i);
    expect(container.textContent).toMatch(/ISAAC manages no accounts or roles/i);

    // no counts / figures rendered, and never the error/verdict visual language
    expect(container.querySelector('.memory-figures')).toBeNull();
    expect(container.querySelector('.fetch-state.error')).toBeNull();
    expect(container.querySelector('.verdict-fail')).toBeNull();
    expect(container.textContent).not.toMatch(/\b(PASS|FAIL|valid|invalid)\b/i);
  });
});

describe('P24.10 · status card — backend down', () => {
  it('renders BackendDown with a retry action when the fetch is unreachable', async () => {
    stubFetchDown();
    const { findByText, getByRole } = renderScreen();
    await findByText('Backend Not Running');
    expect(getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});

describe('P24.10 · no fake search input on Project Memory', () => {
  it('has no search input or searchbox role anywhere on the screen', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
    });
    const { container, queryByRole, findByText } = renderScreen();
    await findByText('Memory Unavailable');
    expect(container.querySelector('input[type="search"]')).toBeNull();
    expect(queryByRole('searchbox')).toBeNull();
  });
});

/*
 * P25.7 — the grounded assistant mounts on Project Memory, subordinate to the
 * memory-status content and driven entirely by the ALREADY-fetched
 * GET /api/graph/status response. It adds NO fetch, never validates, and carries
 * the leads-to-verify framing. Available → the three approved chips; unavailable
 * → the single replacement chip (never red). Guided-prompts-only (no textbox).
 */
describe('P25.7 · Project Memory grounded assistant — available', () => {
  const availableRoutes = {
    'GET /api/memory/concepts': { body: memoryConceptsAvailable },
    'GET /api/graph/status': { body: graphStatusAvailable },
    'GET /api/memory/files': { body: memoryFilesAvailable },
  };

  it('renders exactly the three approved chips in order, subordinate to the status card', async () => {
    stubFetchRoutes(availableRoutes);
    const { findByText, container } = renderScreen();
    await findByText('Memory Available');

    const assistant = container.querySelector('.assistant') as HTMLElement;
    expect(assistant).not.toBeNull();
    const panel = within(assistant);

    const chips = Array.from(assistant.querySelectorAll('.assistant-prompt')).map(
      (b) => b.textContent?.trim() ?? '',
    );
    expect(chips).toEqual([
      'Where do these leads come from?',
      'Is project memory current?',
      'What sources are included?',
    ]);

    // P34.2: the on-mount auto-reply was removed; the provenance answer is now
    // surfaced by clicking its chip (sourced from Project Memory).
    //
    // P36R S10 — this assertion used `findByText`, whose default 1 s poll window
    // made a DETERMINISTIC result look intermittent (one CI failure on PR #14,
    // one local failure in ~35 runs). The path is synchronous:
    // `AssistantPanel.ask()` reads `prompt.answer` — precomposed by
    // `compose({ context: 'memory', graph })` from the SAME already-resolved
    // status payload that rendered "Memory Available" above — and calls
    // `setLiveQuestion` / `setLiveAnswer` / `setActiveIndex` directly. No fetch,
    // no promise, no timer. So `act()` + `getByText` is the honest assertion:
    // it flushes the update and then either finds the answer or fails at once
    // against the real DOM. The timeout was NOT raised and nothing was retried,
    // skipped or marked flaky — the polling was removed instead.
    act(() => {
      fireEvent.click(panel.getByText('Where do these leads come from?').closest('button')!);
    });
    expect(
      panel.getByText(/Leads come from indexed project files and concepts/),
    ).toBeInTheDocument();
    expect(panel.getByText('Source: Project Memory')).toBeInTheDocument();
    // leads-to-verify framing, never a verdict
    expect(assistant.textContent).toMatch(/leads to verify — never a validation verdict/);
    expect(assistant.textContent).not.toMatch(/\b(PASS|FAIL)\b/);
    expect(assistant.textContent).not.toMatch(/\b(in)?valid\b/i);

    // the status card (truth) renders ABOVE the assistant (advisory) in the DOM
    const statusChip = container.querySelector('.graph-chip') as HTMLElement;
    expect(statusChip).not.toBeNull();
    expect(statusChip.compareDocumentPosition(assistant) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('surfaces an honest visual-only composer — a guided-only helper + a SECONDARY send, replacing the standalone guided-note', async () => {
    stubFetchRoutes(availableRoutes);
    const { findByText, container } = renderScreen();
    await findByText('Memory Available');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    const panel = within(assistant);
    // P33 S2 (D3/C3): the textbox now exists but free-form Q&A is not wired; the
    // persistent guided-only helper states the limitation before any interaction,
    // and the send control is SECONDARY (never the primary action).
    expect(panel.getByRole('textbox')).toBeInTheDocument();
    const send = panel.getByRole('button', { name: /send/i });
    expect(send.className).toMatch(/btn-secondary/);
    expect(send.className).not.toMatch(/btn-primary/);
    // P34.2: the persistent helper names the grounded scopes the resolver answers over
    expect(assistant.textContent).toMatch(/Ask about this record/i);
    // the legacy standalone guided-note ("Guided prompts only …") is never surfaced
    expect(assistant.textContent).not.toMatch(/Guided prompts only — the assistant answers/i);
  });

  it('renders NO unavailable caveat, and does NOT duplicate the availability chip in the assistant head (P33 HQA#7)', async () => {
    stubFetchRoutes(availableRoutes);
    const { findByText, container } = renderScreen();
    await findByText('Memory Available');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    // available → the caveat slot is never rendered (dedupe guard only ever
    // applies in the unavailable state).
    expect(assistant.querySelector('.assistant-caveat')).toBeNull();
    expect(assistant.textContent).not.toMatch(
      /Project Memory is unavailable, so no memory-based answer is available here\./,
    );
    // P33 HQA#6/#7: the GraphStatusChip is the single availability indicator on
    // this page; the assistant head no longer duplicates it (availability is
    // still passed to the panel, so classification/caveat behavior is unchanged).
    expect(assistant.querySelector('.assistant-memory')).toBeNull();
  });

  it('clicking a chip swaps in its live answer and issues NO further network request', async () => {
    stubFetchRoutes(availableRoutes);
    const { findByText, container } = renderScreen();
    await findByText('Memory Available');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    const panel = within(assistant);

    const before = (globalThis.fetch as Mock).mock.calls.length;
    fireEvent.click(panel.getByText('What sources are included?').closest('button')!);
    // the scope chip echoes file_count (190), grounded, deterministic.
    // findByText (retry-until-present) — the answer swaps in on a later tick, so a
    // synchronous getByText is a CI race (B1 in the Phase 32 issue register).
    expect(await panel.findByText(/This snapshot indexes 190 project files/)).toBeInTheDocument();
    const after = (globalThis.fetch as Mock).mock.calls.length;
    expect(after).toBe(before); // clicking a guided chip is pure — never fetches
  });

  it('chips are keyboard-activatable native buttons', async () => {
    stubFetchRoutes(availableRoutes);
    const { findByText, container } = renderScreen();
    await findByText('Memory Available');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    const chips = Array.from(assistant.querySelectorAll('.assistant-prompt'));
    expect(chips.length).toBe(3);
    for (const chip of chips) {
      expect(chip.tagName).toBe('BUTTON');
      (chip as HTMLButtonElement).focus();
      expect(chip).toHaveFocus();
    }
  });

  it('the existing Source Index and Concept Lookup cards still render (behind tabs) alongside the assistant', async () => {
    // P33 S3 (D6): the cards moved behind the Sources / Concepts tabs; the
    // assistant moved to the right rail and stays present across every tab. This
    // is the tabbed re-expression of "both cards still render alongside the
    // assistant" — no coverage dropped, just routed through the new IA.
    stubFetchRoutes(availableRoutes);
    const { findByText, getByRole, container } = renderScreen();
    await findByText('Memory Available');
    expect(container.querySelector('.assistant')).not.toBeNull();

    fireEvent.click(getByRole('tab', { name: 'Sources' }));
    expect(await findByText('Source Index')).toBeInTheDocument();
    expect(container.querySelector('.assistant')).not.toBeNull();

    fireEvent.click(getByRole('tab', { name: 'Concepts' }));
    expect(await findByText('Concept Lookup')).toBeInTheDocument();
    expect(container.querySelector('.assistant')).not.toBeNull();
  });
});

describe('P25.7 · Project Memory grounded assistant — unavailable & fetch states', () => {
  it('unavailable → the single replacement chip only, no red/error semantics', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
    });
    const { findByText, container } = renderScreen();
    await findByText('Memory Unavailable');

    const assistant = container.querySelector('.assistant') as HTMLElement;
    expect(assistant).not.toBeNull();
    const chips = Array.from(assistant.querySelectorAll('.assistant-prompt')).map(
      (b) => b.textContent?.trim() ?? '',
    );
    expect(chips).toEqual(['Why is memory unavailable?']); // never four chips
    // P34.2: the on-mount auto-reply was removed. At rest the reply is EMPTY
    // (P36.1 — no resting placeholder); the unavailable sentence is now the
    // availability-driven caveat and must render EXACTLY ONCE (in
    // `.assistant-caveat`), never stacked.
    const occurrences = (
      assistant.textContent?.match(
        /Project Memory is unavailable, so no memory-based answer is available here\./g,
      ) ?? []
    ).length;
    expect(occurrences).toBe(1);
    expect(assistant.querySelector('.assistant-caveat')?.textContent).toBe(
      'Project Memory is unavailable, so no memory-based answer is available here.',
    );
    // P36.1: the resting live region carries no placeholder text and no visible
    // card chrome — it stays mounted (aria-live) but empty.
    const reply = assistant.querySelector('.assistant-reply');
    expect(reply?.textContent).toBe('');
    expect(reply?.classList.contains('assistant-reply--empty')).toBe(true);
    expect(reply?.getAttribute('aria-live')).toBe('polite');
    // P33 HQA#7: the GraphStatusChip owns the single availability state on this
    // page, so the assistant head is not rendered here.
    expect(assistant.querySelector('.assistant-memory')).toBeNull();
    // approved wording — NOT the retired "source files directly" string
    expect(assistant.textContent).not.toMatch(/answered from source files directly/i);
    // no verdict / error styling classes
    expect(assistant.querySelector('.verdict-pass')).toBeNull();
    expect(assistant.querySelector('.verdict-fail')).toBeNull();
  });

  it('loading → the assistant panel is NOT shown', () => {
    // fetch never resolves → the screen stays on the loading state
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})));
    const { container, getByText } = renderScreen();
    expect(getByText(/Checking memory status/i)).toBeInTheDocument();
    expect(container.querySelector('.assistant')).toBeNull();
  });

  it('backend down → BackendDown, and the assistant panel is NOT shown', async () => {
    stubFetchDown();
    const { findByText, container } = renderScreen();
    await findByText('Backend Not Running');
    expect(container.querySelector('.assistant')).toBeNull();
  });
});
