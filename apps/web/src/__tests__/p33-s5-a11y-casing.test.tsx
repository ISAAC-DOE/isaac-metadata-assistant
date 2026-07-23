import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProjectMemory } from '../screens/ProjectMemory';
import { HelpPanel } from '../components/HelpPanel';
import { stubFetchRoutes, graphStatusAvailable } from '../test/apiFixtures';

/*
 * P33 S5 — targeted assertions for the accessibility + copy slice:
 *   A11Y-1  the promoted page title is a real screen-level <h1>.
 *   D10     status/badge labels read Title Case ("Out of Date"), consistent
 *           with their single-word siblings ("Verified" / "Current").
 *   C4      icon-only controls carry an accessible name; the memory section
 *           tablist only points aria-controls at the panel actually mounted
 *           (inactive tabs omit it — matching the accordion convention).
 */

function renderMemory(path = '/memory') {
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ProjectMemory />
    </MemoryRouter>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe('P33 S5 · A11Y-1 — promoted page title', () => {
  it('Project Memory exposes its title as a screen-level h1 (Title Case)', async () => {
    stubFetchRoutes({ 'GET /api/graph/status': { body: graphStatusAvailable } });
    const { findByText, getByRole } = renderMemory();
    await findByText('Memory Available');
    expect(getByRole('heading', { level: 1, name: 'Project Memory' })).toBeInTheDocument();
  });
});

describe('P33 S5 · D10 — status label casing', () => {
  it('renders the stale freshness axis as Title Case "Out of Date"', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': {
        body: { ...graphStatusAvailable, indexed_sources: 'stale' },
      },
    });
    const { findByText, getByText, queryByText } = renderMemory();
    await findByText('Memory Available');
    // The badge-tier status label is Title Case, not sentence case.
    expect(getByText('Out of Date')).toBeInTheDocument();
    expect(queryByText('Out of date')).toBeNull();
  });
});

describe('P33 S5 · C4 — icon-only accessible names', () => {
  it('the Help trigger and its close control both have accessible names', () => {
    const { getByRole } = render(<HelpPanel />);
    const trigger = getByRole('button', { name: 'Help' });
    expect(trigger).toBeInTheDocument();
    fireEvent.click(trigger);
    expect(getByRole('button', { name: 'Close help' })).toBeInTheDocument();
  });
});

describe('P33 S5 · C4/S3 — tablist aria-controls references only the mounted panel', () => {
  it('the selected tab points at its panel; inactive tabs omit aria-controls', async () => {
    stubFetchRoutes({ 'GET /api/graph/status': { body: graphStatusAvailable } });
    const { findByText, getByRole } = renderMemory();
    await findByText('Memory Available');

    const overview = getByRole('tab', { name: 'Overview' });
    const sources = getByRole('tab', { name: 'Sources' });

    // Overview is selected: it references its mounted panel by id.
    expect(overview).toHaveAttribute('aria-selected', 'true');
    expect(overview).toHaveAttribute('aria-controls', 'memory-tabpanel-overview');
    // Sources is not selected and its panel is NOT in the DOM — no dangling ref.
    expect(sources).toHaveAttribute('aria-selected', 'false');
    expect(sources).not.toHaveAttribute('aria-controls');

    // Selecting Sources moves the live reference to the now-mounted panel.
    fireEvent.click(sources);
    expect(sources).toHaveAttribute('aria-controls', 'memory-tabpanel-sources');
    expect(overview).not.toHaveAttribute('aria-controls');
  });
});
