import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProjectMemory } from '../screens/ProjectMemory';
import {
  stubFetchRoutes,
  graphStatusUnavailable,
  memoryFilesAvailable,
  memoryFilesUnavailable,
  memoryFileDetailWithLeads,
  memoryFileDetailEmptyLeads,
  memoryConceptsUnavailable,
} from '../test/apiFixtures';

/*
 * P24.4 — the Source Index card: the served-allowlist file list from
 * GET /api/memory/files, plus a lazy per-row provenance detail from
 * GET /api/memory/file?path=. It is a provenance navigator, never a file
 * browser or content viewer — nothing here fetches or renders file bytes.
 */

function renderScreen() {
  const view = render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ProjectMemory />
    </MemoryRouter>,
  );
  // P33 S3 (D6): the Source Index moved behind the "Sources" internal tab. These
  // tests exercise the SAME card, now reached through the tabbed IA — the tablist
  // renders immediately (independent of the graph fetch), so open it here.
  fireEvent.click(view.getByRole('tab', { name: 'Sources' }));
  return view;
}

/** The provenance panel <div> for a given row button (sibling inside the row's <li>). */
function panelFor(row: HTMLElement): HTMLElement {
  const panel = row.closest('li')?.querySelector('.source-index-panel');
  if (!panel) throw new Error('provenance panel not found for row');
  return panel as HTMLElement;
}

const filePath = (p: string) => `GET /api/memory/file?path=${encodeURIComponent(p)}`;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('P24.4 · Source Index — list', () => {
  it('renders exactly the stubbed files, grouped by humanized file_type, with community + node count context', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesAvailable },
    });
    const { findByText, getByText, container } = renderScreen();
    await findByText('Source Index');

    // exactly the fixture's rows — no extras
    expect(container.querySelectorAll('.source-index-row-btn')).toHaveLength(
      memoryFilesAvailable.files.length,
    );

    // group headings: humanized file_type, never invented
    expect(getByText('Code')).toBeInTheDocument();
    expect(getByText('Documents')).toBeInTheDocument();
    expect(getByText('Other')).toBeInTheDocument(); // null file_type — honest, not fabricated

    for (const f of memoryFilesAvailable.files) {
      expect(getByText(f.path)).toBeInTheDocument();
    }

    // community: real name, honest id-fallback ("community <id>"), never invented
    expect(getByText('Export Pipeline')).toBeInTheDocument();
    expect(getByText('community 55')).toBeInTheDocument();

    // node counts, singular/plural
    expect(getByText('42 nodes')).toBeInTheDocument();
    expect(getByText('1 node')).toBeInTheDocument();

    // on_disk:false row marker
    expect(getByText('not on disk')).toBeInTheDocument();

    // standing caption + metadata-only subtitle
    expect(getByText('project knowledge — not scientific evidence')).toBeInTheDocument();
    expect(
      getByText(/metadata and provenance only, never file contents/i),
    ).toBeInTheDocument();
  });
});

describe('P24.4 · Source Index — detail (real leads)', () => {
  it('activating a row (click, then keyboard) fetches its provenance and renders related concepts, related files, rationales, and local_reference', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesAvailable },
      [filePath('src/fake_mod.py')]: { body: memoryFileDetailWithLeads },
    });
    const { findByText, getByRole } = renderScreen();
    await findByText('Source Index');

    const row = getByRole('button', { name: /src\/fake_mod\.py/ });
    expect(row).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(row);
    expect(row).toHaveAttribute('aria-expanded', 'true');

    await findByText('Deterministic, doubly-gated export transform.');
    const panel = panelFor(row);
    const scoped = within(panel);

    expect(scoped.getByText('Provenance')).toBeInTheDocument(); // related.concepts label
    expect(scoped.getByText('relates_to')).toBeInTheDocument(); // concept relation
    expect(scoped.getByText('src/other_mod.py')).toBeInTheDocument(); // related.files path
    expect(scoped.getByText('imports')).toBeInTheDocument(); // file relation
    expect(scoped.getByText('src/fake_mod.py')).toBeInTheDocument(); // local_reference
    expect(scoped.getByText('local reference — open in your editor')).toBeInTheDocument();

    // collapse via click
    fireEvent.click(row);
    expect(row).toHaveAttribute('aria-expanded', 'false');

    // Reopen via the keyboard path: on a native <button>, Enter/Space
    // activation is a browser-synthesized click on the FOCUSED button — so
    // the honest jsdom equivalent is focus + click (there is no custom
    // onKeyDown; one would double-toggle in a real browser). A raw keydown
    // alone must NOT toggle: that would prove a duplicate handler exists.
    fireEvent.keyDown(row, { key: 'Enter' });
    expect(row).toHaveAttribute('aria-expanded', 'false');

    row.focus();
    expect(document.activeElement).toBe(row);
    fireEvent.click(row);
    expect(row).toHaveAttribute('aria-expanded', 'true');
    await findByText('Deterministic, doubly-gated export transform.');
  });
});

describe('P24.4 · Source Index — on_disk:false', () => {
  it('shows "not present locally" with no open-style affordance, never invented content', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesAvailable },
      [filePath('docs/fake-note.md')]: { body: memoryFileDetailEmptyLeads },
    });
    const { findByText, getByRole } = renderScreen();
    await findByText('Source Index');

    const row = getByRole('button', { name: /docs\/fake-note\.md/ });
    fireEvent.click(row);
    await findByText('not present locally — cannot open');

    const panel = panelFor(row);
    const scoped = within(panel);

    expect(scoped.getByText('not present locally — cannot open')).toBeInTheDocument();
    expect(scoped.queryByText('local reference — open in your editor')).toBeNull();
    expect(panel.querySelector('a')).toBeNull(); // no link/open-style affordance
  });
});

describe('P24.4 · Source Index — unavailable', () => {
  it('renders a compact honest unavailable note, zero rows, no fake content, no error styling', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
    });
    const { findByText, container } = renderScreen();

    await findByText(/Source Index is unavailable/i);
    expect(container.querySelectorAll('.source-index-row-btn')).toHaveLength(0);
    expect(container.querySelector('.fetch-state.error')).toBeNull();
    expect(container.querySelector('.verdict-fail')).toBeNull();
    expect(container.textContent).not.toMatch(/\b(PASS|FAIL)\b/);
  });
});

describe('P24.4 · Source Index — accessibility basics', () => {
  it('rows are real buttons with accessible names, aria-expanded toggles, the card has a heading, and there is still no search input', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesAvailable },
      [filePath('src/fake_mod.py')]: { body: memoryFileDetailWithLeads },
    });
    const { findByText, getByRole, container, queryByRole } = renderScreen();
    await findByText('Source Index');

    expect(getByRole('heading', { name: 'Source Index' })).toBeInTheDocument();

    const row = getByRole('button', { name: /src\/fake_mod\.py/ });
    expect(row).toHaveAccessibleName();
    expect(row).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(row);
    expect(row).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(row);
    expect(row).toHaveAttribute('aria-expanded', 'false');

    // still no search/filter input anywhere on the screen (Phase 26)
    expect(container.querySelector('input[type="search"]')).toBeNull();
    expect(queryByRole('searchbox')).toBeNull();
  });
});

describe('P24.4 · Source Index — empty-leads honesty', () => {
  it('renders the honest empty-leads note for rationales, related files, and related concepts — never hidden, never invented', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesAvailable },
      [filePath('docs/fake-note.md')]: { body: memoryFileDetailEmptyLeads },
    });
    const { findByText, getByRole, findAllByText } = renderScreen();
    await findByText('Source Index');

    const row = getByRole('button', { name: /docs\/fake-note\.md/ });
    fireEvent.click(row);

    const notes = await findAllByText('no recorded leads for this file');
    expect(notes).toHaveLength(3); // rationales, related files, related concepts
  });
});
