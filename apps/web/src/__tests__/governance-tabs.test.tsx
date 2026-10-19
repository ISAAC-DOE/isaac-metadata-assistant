/**
 * P36.6 / P36R S8 — Governance & Safety reorganized into local page tabs:
 * Validator · Schema Reference (Policy moved to Settings › Privacy & Governance,
 * 2026-10-12). Mirrors ProjectMemory's internal-tabs
 * test shape (`memory-tabs.test.tsx`). This slice is presentation/IA only: the
 * P36.3 Validator's request path and behavior must be unchanged, and the
 * `active="governance"` LeftNav wiring must be preserved.
 *
 * P36R S8 renamed the third tab "Schema & Vocabulary" → "Schema Reference"
 * (plan §R7); the vocabulary did not go away, it became one of that tab's three
 * subviews.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import { GovernancePage, GovernanceRoute } from '../screens/GovernancePage';
import {
  stubFetchRoutes,
  validateRecordPass,
  syntheticCandidateRecord,
} from '../test/apiFixtures';

function renderPage() {
  return render(
    <MemoryRouter
      initialEntries={['/governance']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <GovernancePage />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="loc">{`${location.pathname}${location.search}`}</span>;
}

describe('Governance & Safety — tablist', () => {
  /*
   * TWO TABS SINCE 2026-10-12. The Policy tab moved to Settings › Privacy &
   * Governance (`DEC-28`); its text lives in `GOVERNANCE_POLICY`, and the route
   * redirects there (asserted below). Rendered directly, the page falls back to
   * its first tab — the Validator — exactly as it used to fall back to Policy.
   */
  it('exposes an accessible tablist with Validator and Schema Reference', () => {
    renderPage();
    expect(screen.getByRole('tablist', { name: /Governance & Safety sections/i })).toBeInTheDocument();
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual([
      'Validator',
      'Schema Reference',
    ]);
    expect(screen.queryByRole('tab', { name: 'Policy' })).toBeNull();
    expect(screen.getByRole('tab', { name: 'Validator' })).toHaveAttribute('aria-selected', 'true');
  });

  it('no longer offers the old "Schema & Vocabulary" tab label', () => {
    renderPage();
    expect(screen.queryByRole('tab', { name: 'Schema & Vocabulary' })).toBeNull();
  });
});

describe('Governance & Safety — content routing', () => {
  it('the Validator is the first tab and the policy text is no longer on this page', () => {
    renderPage();
    expect(screen.getByText('Standalone Validator')).toBeInTheDocument();
    expect(
      screen.queryByText(/The visible workspace remains synthetic and uploads remain disabled/i),
    ).toBeNull();
  });

  it.each(['/governance', '/governance?tab=policy', '/governance?tab=bogus'])(
    '%s redirects to Settings › Privacy & Governance, where the policy now lives',
    (entry) => {
      stubFetchRoutes({});
      render(
        <MemoryRouter
          initialEntries={[entry]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <Routes>
            <Route path="/governance" element={<GovernanceRoute />} />
            <Route path="/settings" element={<LocationProbe />} />
          </Routes>
        </MemoryRouter>,
      );
      expect(screen.getByTestId('loc').textContent).toBe('/settings?tab=privacy');
    },
  );

  it.each(['validator', 'schema'])('?tab=%s still renders this page, not a redirect', (id) => {
    stubFetchRoutes({ 'GET /api/schema': { body: { schema_title: 't', schema_version: '1.05', schema: { properties: {} }, vocabularies: {} } } });
    render(
      <MemoryRouter
        initialEntries={[`/governance?tab=${id}`]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/governance" element={<GovernanceRoute />} />
          <Route path="/settings" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.queryByTestId('loc')).toBeNull();
    expect(screen.getByRole('tab', { selected: true })).toHaveAttribute('id', `governance-tab-${id}`);
  });

  it('clicking Schema Reference reveals the browser', async () => {
    stubFetchRoutes({ 'GET /api/schema': { body: { schema_title: 't', schema_version: '1.05', schema: { properties: {} }, vocabularies: {} } } });
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: 'Schema Reference' }));
    expect(await screen.findByRole('heading', { name: 'Schema Reference', level: 2 })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Schema Reference' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.queryByText('Standalone Validator')).toBeNull();
  });
});

describe('Governance & Safety — the Validator still works inside its tab', () => {
  it('validates a pasted record via POST /api/validate/record exactly as before', async () => {
    const hits = stubFetchRoutes({ 'POST /api/validate/record': { body: validateRecordPass } });
    renderPage();

    fireEvent.change(screen.getByLabelText(/candidate record \(json\)/i), {
      target: { value: JSON.stringify(syntheticCandidateRecord) },
    });
    fireEvent.click(screen.getByRole('button', { name: /^validate$/i }));

    expect(await screen.findByText('PASS')).toBeInTheDocument();
    expect(hits).toEqual(['POST /api/validate/record']);
  });
});

describe('Governance & Safety — keyboard navigation', () => {
  it('ArrowRight moves selection and focus to the next tab', async () => {
    stubFetchRoutes({ 'GET /api/schema': { body: { schema_title: 't', schema_version: '1.05', schema: { properties: {} }, vocabularies: {} } } });
    renderPage();
    const validator = screen.getByRole('tab', { name: 'Validator' });
    validator.focus();
    fireEvent.keyDown(validator, { key: 'ArrowRight' });

    const schema = screen.getByRole('tab', { name: 'Schema Reference' });
    expect(schema).toHaveAttribute('aria-selected', 'true');
    expect(schema).toHaveFocus();
    expect(await screen.findByRole('heading', { name: 'Schema Reference', level: 2 })).toBeInTheDocument();
  });

  it('End jumps to Schema Reference and Home returns to the Validator', async () => {
    stubFetchRoutes({ 'GET /api/schema': { body: { schema_title: 't', schema_version: '1.05', schema: { properties: {} }, vocabularies: {} } } });
    renderPage();
    const validator = screen.getByRole('tab', { name: 'Validator' });
    validator.focus();
    fireEvent.keyDown(validator, { key: 'End' });

    const schema = screen.getByRole('tab', { name: 'Schema Reference' });
    expect(schema).toHaveAttribute('aria-selected', 'true');
    expect(schema).toHaveFocus();
    expect(await screen.findByRole('heading', { name: 'Schema Reference', level: 2 })).toBeInTheDocument();

    fireEvent.keyDown(schema, { key: 'Home' });
    expect(screen.getByRole('tab', { name: 'Validator' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('Standalone Validator')).toBeInTheDocument();
  });
});
