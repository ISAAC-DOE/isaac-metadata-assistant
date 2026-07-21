import { describe, it, expect, afterEach, vi, type Mock } from 'vitest';
import { render, fireEvent, within } from '@testing-library/react';
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

    await findByText('Memory: Available');

    // counts come only from the API overview
    expect(getByText('2296')).toBeInTheDocument();
    expect(getByText('3447')).toBeInTheDocument();
    expect(getByText('214')).toBeInTheDocument();
    expect(getByText('190')).toBeInTheDocument(); // Indexed files = file_count
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
    await findByText('Memory: Available');
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

    await findByText('Memory: Available');

    // available → real counts render (Indexed files comes from file_count = 9)
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

    // served_file_count is null (pre-regen) — no broken/empty "served" figure,
    // and no fabricated age (graph_mtime null, so never a 1970 epoch artifact)
    expect(container.textContent).not.toMatch(/served files/i);
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

    await findByText('Memory: Unavailable');

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
  it('renders an honest unavailable panel with hosted + future-wiring copy, no counts, no error styling', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
    });
    const { findByText, container } = renderScreen();

    await findByText('Memory: Unavailable');
    expect(
      await findByText(/memory graph artifacts are not present/i),
    ).toBeInTheDocument();
    expect(container.textContent).toMatch(/hosted demo does not currently ship/i);
    expect(container.textContent).toMatch(/wired later to an approved source/i);

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
    await findByText('Memory: Unavailable');
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
    await findByText('Memory: Available');

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

    // default reply is the provenance chip, answered from Project Memory
    expect(panel.getByText(/Leads come from indexed project files and concepts/)).toBeInTheDocument();
    expect(panel.getByText('answered from: Project Memory')).toBeInTheDocument();
    // leads-to-verify framing, never a verdict
    expect(assistant.textContent).toMatch(/leads to verify — never a validation verdict/);
    expect(assistant.textContent).not.toMatch(/\b(PASS|FAIL)\b/);
    expect(assistant.textContent).not.toMatch(/\b(in)?valid\b/i);

    // the status card (truth) renders ABOVE the assistant (advisory) in the DOM
    const statusChip = container.querySelector('.graph-chip') as HTMLElement;
    expect(statusChip).not.toBeNull();
    expect(statusChip.compareDocumentPosition(assistant) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('is guided-prompts-only — no textbox, no send button', async () => {
    stubFetchRoutes(availableRoutes);
    const { findByText, container, queryByRole } = renderScreen();
    await findByText('Memory: Available');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    expect(within(assistant).queryByRole('textbox')).toBeNull();
    expect(queryByRole('button', { name: /^send$/i })).toBeNull();
    expect(assistant.textContent).toMatch(/Guided prompts only/i);
  });

  it('renders the memory: available head line but NO unavailable caveat (unchanged behavior)', async () => {
    stubFetchRoutes(availableRoutes);
    const { findByText, container } = renderScreen();
    await findByText('Memory: Available');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    // available → the caveat slot is never rendered (dedupe guard only ever
    // applies in the unavailable state); the head-line dot still shows.
    expect(assistant.querySelector('.assistant-caveat')).toBeNull();
    expect(assistant.textContent).not.toMatch(
      /Project Memory is unavailable, so no memory-based answer is available here\./,
    );
    expect(assistant.querySelector('.assistant-memory')?.textContent).toMatch(/available/);
  });

  it('clicking a chip swaps in its live answer and issues NO further network request', async () => {
    stubFetchRoutes(availableRoutes);
    const { findByText, container } = renderScreen();
    await findByText('Memory: Available');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    const panel = within(assistant);

    const before = (globalThis.fetch as Mock).mock.calls.length;
    fireEvent.click(panel.getByText('What sources are included?').closest('button')!);
    // the scope chip echoes file_count (190), grounded, deterministic
    expect(panel.getByText(/This snapshot indexes 190 project files/)).toBeInTheDocument();
    const after = (globalThis.fetch as Mock).mock.calls.length;
    expect(after).toBe(before); // clicking a guided chip is pure — never fetches
  });

  it('chips are keyboard-activatable native buttons', async () => {
    stubFetchRoutes(availableRoutes);
    const { findByText, container } = renderScreen();
    await findByText('Memory: Available');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    const chips = Array.from(assistant.querySelectorAll('.assistant-prompt'));
    expect(chips.length).toBe(3);
    for (const chip of chips) {
      expect(chip.tagName).toBe('BUTTON');
      (chip as HTMLButtonElement).focus();
      expect(chip).toHaveFocus();
    }
  });

  it('the existing Source Index and Concept Lookup cards still render alongside the assistant', async () => {
    stubFetchRoutes(availableRoutes);
    const { findByText, getByText } = renderScreen();
    await findByText('Memory: Available');
    expect(getByText('Source Index')).toBeInTheDocument();
    expect(getByText('Concept Lookup')).toBeInTheDocument();
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
    await findByText('Memory: Unavailable');

    const assistant = container.querySelector('.assistant') as HTMLElement;
    expect(assistant).not.toBeNull();
    const chips = Array.from(assistant.querySelectorAll('.assistant-prompt')).map(
      (b) => b.textContent?.trim() ?? '',
    );
    expect(chips).toEqual(['Why is memory unavailable?']); // never four chips
    // Dedupe regression (P25.7): the composed reply text is byte-identical to
    // MEMORY_UNAVAILABLE_CAVEAT here, so the unavailable sentence must render
    // EXACTLY ONCE (in `.assistant-reply`) — never stacked a second time in
    // `.assistant-caveat`. Count occurrences, not merely ≥1 presence.
    const occurrences = (
      assistant.textContent?.match(
        /Project Memory is unavailable, so no memory-based answer is available here\./g,
      ) ?? []
    ).length;
    expect(occurrences).toBe(1);
    expect(assistant.querySelector('.assistant-reply')?.textContent).toBe(
      'Project Memory is unavailable, so no memory-based answer is available here.',
    );
    // …and the caveat slot is suppressed precisely because it would duplicate
    // the reply (the `memory: unavailable` head line still shows below).
    expect(assistant.querySelector('.assistant-caveat')).toBeNull();
    expect(assistant.querySelector('.assistant-memory')?.textContent).toMatch(/unavailable/);
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
