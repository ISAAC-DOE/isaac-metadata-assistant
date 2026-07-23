import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProjectMemory } from '../screens/ProjectMemory';
import {
  stubFetchRoutes,
  graphStatusUnavailable,
  memoryFilesUnavailable,
  memoryConceptsAvailable,
  memoryConceptsUnavailable,
  memoryConceptDetailWithLeads,
  memoryConceptDetailEmptyLeads,
  memoryConceptDetailWithheldAnchor,
} from '../test/apiFixtures';

/*
 * P24.5 — the Concept Lookup card: the 19 curated concepts Graphify anchored
 * in project docs, from GET /api/memory/concepts, plus a lazy per-concept
 * provenance detail from GET /api/memory/concepts/{id}. Concepts are
 * navigation anchors, not findings — every assertion checks leads, never a
 * verdict. Source Index is stubbed unavailable in every test here (its own
 * card renders independently; these tests only exercise Concept Lookup).
 */

function renderScreen() {
  const view = render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ProjectMemory />
    </MemoryRouter>,
  );
  // P33 S3 (D6): the Concept Lookup moved behind the "Concepts" internal tab.
  // These tests exercise the SAME card through the tabbed IA — the tablist
  // renders immediately (independent of the graph fetch), so open it here. The
  // ?concept= deep-link test below renders its own tree and auto-selects the tab.
  fireEvent.click(view.getByRole('tab', { name: 'Concepts' }));
  return view;
}

/** The provenance panel <div> for a given row button (sibling inside the row's <li>). */
function panelFor(row: HTMLElement): HTMLElement {
  const panel = row.closest('li')?.querySelector('.concept-lookup-panel');
  if (!panel) throw new Error('provenance panel not found for row');
  return panel as HTMLElement;
}

const conceptPath = (id: string) => `GET /api/memory/concepts/${encodeURIComponent(id)}`;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('P24.5 · Concept Lookup — list', () => {
  it('renders exactly the stubbed concepts, with labels and community context (name or honest fallback)', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
      'GET /api/memory/concepts': { body: memoryConceptsAvailable },
    });
    const { findByText, getByText, container } = renderScreen();
    await findByText('Concept Lookup');

    expect(container.querySelectorAll('.concept-lookup-row-btn')).toHaveLength(
      memoryConceptsAvailable.concepts.length,
    );

    for (const c of memoryConceptsAvailable.concepts) {
      expect(getByText(c.label)).toBeInTheDocument();
    }

    // community: real name, honest id-fallback, never invented
    expect(getByText('Export Pipeline')).toBeInTheDocument();
    expect(getByText('community 55')).toBeInTheDocument();

    // standing caption + honest subtitle
    expect(getByText('leads — open the cited file to verify')).toBeInTheDocument();
    expect(
      getByText('Concepts Graphify anchored in project docs — memory leads, not scientific conclusions.'),
    ).toBeInTheDocument();
  });
});

describe('P24.5 · Concept Lookup — detail (real leads)', () => {
  it('activating a concept fetches its provenance and renders the anchor, community, related files, and related concepts', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
      'GET /api/memory/concepts': { body: memoryConceptsAvailable },
      [conceptPath('concept-provenance')]: { body: memoryConceptDetailWithLeads },
    });
    const { findByText, getByRole } = renderScreen();
    await findByText('Concept Lookup');

    const row = getByRole('button', { name: /Provenance/ });
    expect(row).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(row);
    expect(row).toHaveAttribute('aria-expanded', 'true');

    await findByText('src/other_mod.py');
    const panel = panelFor(row);
    const scoped = within(panel);

    expect(scoped.getByText('src/fake_mod.py')).toBeInTheDocument(); // anchor source_file
    expect(scoped.getByText('Export Pipeline')).toBeInTheDocument(); // community
    expect(scoped.getByText('src/other_mod.py')).toBeInTheDocument(); // related.files path
    expect(scoped.getByText('imports')).toBeInTheDocument(); // file relation
    expect(scoped.getByText('code')).toBeInTheDocument(); // file_type
    expect(scoped.getByText('Governance allowlist')).toBeInTheDocument(); // related.concepts label
    expect(scoped.getByText('relates_to')).toBeInTheDocument(); // concept relation
  });
});

describe('P24.5 · Concept Lookup — empty-leads honesty', () => {
  it('shows the honest empty note when related is empty, still rendering the anchor provenance — never invented leads', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
      'GET /api/memory/concepts': { body: memoryConceptsAvailable },
      [conceptPath('concept-governance')]: { body: memoryConceptDetailEmptyLeads },
    });
    const { findByText, getByRole } = renderScreen();
    await findByText('Concept Lookup');

    const row = getByRole('button', { name: /Governance allowlist/ });
    fireEvent.click(row);

    await findByText('docs/fake-note.md'); // anchor source_file still renders
    const panel = panelFor(row);
    const scoped = within(panel);

    expect(scoped.getByText('docs/fake-note.md')).toBeInTheDocument();
    expect(scoped.getByText('not present locally on this backend')).toBeInTheDocument();
    expect(
      scoped.getByText('no recorded leads for this concept in the current graph'),
    ).toBeInTheDocument();
    // never invented: no related-file/related-concept content in this panel
    expect(scoped.queryByText('Files')).toBeNull();
    expect(scoped.queryByText('Concepts')).toBeNull();
  });
});

describe('P24.9 · Concept Lookup — withheld anchor honesty', () => {
  it('renders an honest "anchor withheld" note (not an empty mono span) when the backend nulls a governance-excluded anchor', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
      'GET /api/memory/concepts': { body: memoryConceptsAvailable },
      [conceptPath('concept-governance')]: { body: memoryConceptDetailWithheldAnchor },
    });
    const { findByText, getByRole } = renderScreen();
    await findByText('Concept Lookup');

    const row = getByRole('button', { name: /Governance allowlist/ });
    fireEvent.click(row);

    await findByText('anchor withheld (excluded source)');
    const panel = panelFor(row);
    const scoped = within(panel);

    // The honest withheld note is present...
    expect(scoped.getByText('anchor withheld (excluded source)')).toBeInTheDocument();
    // ...and no empty mono span was rendered for the withheld anchor.
    const monoSpans = panel.querySelectorAll('.concept-lookup-anchor .mono');
    expect(monoSpans).toHaveLength(0);
    // The "not present locally" note is suppressed when there is no anchor path.
    expect(scoped.queryByText('not present locally on this backend')).toBeNull();
  });
});

describe('P24.5 · Concept Lookup — unavailable', () => {
  it('renders a compact honest unavailable note, zero concept rows, no error/red styling', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
    });
    const { findByText, container } = renderScreen();

    await findByText(/Concept lookup is unavailable/i);
    expect(container.querySelectorAll('.concept-lookup-row-btn')).toHaveLength(0);
    expect(container.querySelector('.fetch-state.error')).toBeNull();
    expect(container.querySelector('.verdict-fail')).toBeNull();
    expect(container.textContent).not.toMatch(/\b(PASS|FAIL)\b/);
  });
});

describe('P24.5 · Concept Lookup — keyboard accessibility', () => {
  it('is activatable via focus + synthesized click, a raw keydown alone does not toggle, aria-expanded tracks state, and the screen has no inline/decorative search input', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
      'GET /api/memory/concepts': { body: memoryConceptsAvailable },
      [conceptPath('concept-provenance')]: { body: memoryConceptDetailWithLeads },
    });
    const { findByText, getByRole, container, queryByRole } = renderScreen();
    await findByText('Concept Lookup');

    expect(getByRole('heading', { name: 'Concept Lookup' })).toBeInTheDocument();

    const row = getByRole('button', { name: /Provenance/ });
    expect(row).toHaveAccessibleName();
    expect(row).toHaveAttribute('aria-expanded', 'false');

    // A raw keydown must NOT toggle — that would prove a duplicate onKeyDown
    // handler exists (P24.4's binding decision: native-button activation only).
    fireEvent.keyDown(row, { key: 'Enter' });
    expect(row).toHaveAttribute('aria-expanded', 'false');

    // The honest jsdom equivalent of real-browser Enter/Space activation on a
    // focused native <button> is focus + the browser-synthesized click.
    row.focus();
    expect(document.activeElement).toBe(row);
    fireEvent.click(row);
    expect(row).toHaveAttribute('aria-expanded', 'true');
    await findByText('src/other_mod.py'); // panel content present

    fireEvent.click(row);
    expect(row).toHaveAttribute('aria-expanded', 'false');

    // P26: the memory SCREEN itself still has no DECORATIVE/INLINE search input.
    // Real search is the global ⌘K command palette (SearchDialog, mounted in the
    // TopBar and proven in search-command.test.tsx) — a separate surface, not
    // part of <ProjectMemory>. This invariant guards against re-adding a fake
    // inline filter box to the screen, not against search existing at all.
    expect(container.querySelector('input[type="search"]')).toBeNull();
    expect(queryByRole('searchbox')).toBeNull();
  });
});

describe('P26.5 · Concept Lookup — search-palette deep link', () => {
  it('auto-opens the concept named by ?concept= on mount (memory-search navigation lands here)', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
      'GET /api/memory/concepts': { body: memoryConceptsAvailable },
      [conceptPath('concept-provenance')]: { body: memoryConceptDetailWithLeads },
    });
    const view = render(
      <MemoryRouter
        initialEntries={['/memory?concept=concept-provenance']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <ProjectMemory />
      </MemoryRouter>,
    );

    const row = await view.findByRole('button', { name: /Provenance/ });
    expect(row).toHaveAttribute('aria-expanded', 'true'); // auto-opened from the URL param
    await view.findByText('src/other_mod.py'); // its provenance detail auto-fetched
  });
});

describe('P24.5 · Concept Lookup — no verdict language', () => {
  it('never renders PASS/FAIL/valid/invalid, across available and unavailable states', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
      'GET /api/memory/concepts': { body: memoryConceptsAvailable },
      [conceptPath('concept-provenance')]: { body: memoryConceptDetailWithLeads },
    });
    const available = renderScreen();
    await available.findByText('Concept Lookup');
    fireEvent.click(available.getByRole('button', { name: /Provenance/ }));
    await available.findByText('src/other_mod.py');
    expect(available.container.textContent).not.toMatch(/\b(PASS|FAIL|valid|invalid)\b/i);
    available.unmount();
    vi.unstubAllGlobals();

    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
    });
    const unavailable = renderScreen();
    await unavailable.findByText(/Concept lookup is unavailable/i);
    expect(unavailable.container.textContent).not.toMatch(/\b(PASS|FAIL|valid|invalid)\b/i);
  });
});
