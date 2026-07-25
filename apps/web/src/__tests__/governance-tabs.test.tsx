/**
 * P36.6 — Governance & Safety reorganized into local page tabs: Policy ·
 * Validator · Schema & Vocabulary. Mirrors ProjectMemory's internal-tabs test
 * shape (`memory-tabs.test.tsx`). This slice is presentation/IA only: the
 * P36.3 Validator and its existing behavior must be unchanged, and the
 * `active="governance"` LeftNav wiring must be preserved.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { GovernancePage } from '../screens/GovernancePage';
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

describe('Governance & Safety — tablist', () => {
  it('exposes an accessible tablist with Policy, Validator, and Schema & Vocabulary', () => {
    renderPage();
    expect(screen.getByRole('tablist', { name: /Governance & Safety sections/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Policy' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Validator' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Schema & Vocabulary' })).toBeInTheDocument();
    // Policy is the default selected tab.
    expect(screen.getByRole('tab', { name: 'Policy' })).toHaveAttribute('aria-selected', 'true');
  });
});

describe('Governance & Safety — content routing', () => {
  it('Policy shows the synthetic-only governance text (preserved verbatim)', () => {
    renderPage();
    expect(
      screen.getByText(/This prototype is synthetic-only by default/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Standalone Validator/i)).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Schema & Vocabulary', level: 2 })).toBeNull();
  });

  it('clicking Validator reveals the standalone validator (unchanged)', () => {
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: 'Validator' }));
    expect(screen.getByText('Standalone Validator')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Validator' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByText(/This prototype is synthetic-only by default/i)).toBeNull();
  });

  it('clicking Schema & Vocabulary reveals the new browser', async () => {
    stubFetchRoutes({ 'GET /api/schema': { body: { schema_title: 't', schema_version: '1.05', schema: { properties: {} }, vocabularies: {} } } });
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: 'Schema & Vocabulary' }));
    expect(await screen.findByRole('heading', { name: 'Schema & Vocabulary', level: 2 })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Schema & Vocabulary' })).toHaveAttribute(
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
    fireEvent.click(screen.getByRole('tab', { name: 'Validator' }));

    fireEvent.change(screen.getByLabelText(/candidate record \(json\)/i), {
      target: { value: JSON.stringify(syntheticCandidateRecord) },
    });
    fireEvent.click(screen.getByRole('button', { name: /^validate$/i }));

    expect(await screen.findByText('PASS')).toBeInTheDocument();
    expect(hits).toEqual(['POST /api/validate/record']);
  });
});

describe('Governance & Safety — keyboard navigation', () => {
  it('ArrowRight moves selection and focus to the next tab', () => {
    renderPage();
    const policy = screen.getByRole('tab', { name: 'Policy' });
    policy.focus();
    fireEvent.keyDown(policy, { key: 'ArrowRight' });

    const validator = screen.getByRole('tab', { name: 'Validator' });
    expect(validator).toHaveAttribute('aria-selected', 'true');
    expect(validator).toHaveFocus();
    expect(screen.getByText('Standalone Validator')).toBeInTheDocument();
  });
});
