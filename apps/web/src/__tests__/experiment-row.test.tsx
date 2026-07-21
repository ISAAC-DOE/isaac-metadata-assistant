import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ExperimentRow } from '../components/ExperimentRow';
import type { ExperimentSummary } from '../lib/types';

function renderRow(exp: ExperimentSummary) {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ExperimentRow exp={exp} />
    </MemoryRouter>,
  );
}

const baseExp: ExperimentSummary = {
  id: '01JQZ0EXPORTED',
  title: 'CuO₂ XANES',
  technique: 'Cu K-edge XANES',
  idOrDraft: '01JQZ0EXPORTED',
  group: 'done',
  trailing: { exported: true },
};

describe('ExperimentRow — accessible name (CQ-10)', () => {
  it('never renders "undefined" in the aria-label when coverage is absent on an exported row', () => {
    const { getByRole } = renderRow(baseExp);
    const link = getByRole('link');
    const label = link.getAttribute('aria-label') ?? '';
    expect(label).not.toContain('undefined');
    expect(label).toContain('Exported');
  });

  it('never renders "undefined" in the aria-label when coverage is absent on a passing row', () => {
    const exp: ExperimentSummary = {
      ...baseExp,
      trailing: { verdict: 'pass' },
    };
    const { getByRole } = renderRow(exp);
    const link = getByRole('link');
    const label = link.getAttribute('aria-label') ?? '';
    expect(label).not.toContain('undefined');
    expect(label).toContain('PASS');
  });

  it('includes "coverage R/T" in the aria-label when coverage IS present on an exported row', () => {
    const exp: ExperimentSummary = {
      ...baseExp,
      trailing: { exported: true, coverage: { resolved: 7, total: 8 } },
    };
    const { getByRole } = renderRow(exp);
    const link = getByRole('link');
    const label = link.getAttribute('aria-label') ?? '';
    expect(label).toContain('coverage 7/8');
    expect(label).toContain('Exported');
  });

  it('includes "coverage R/T" in the aria-label when coverage IS present on a passing row', () => {
    const exp: ExperimentSummary = {
      ...baseExp,
      trailing: { verdict: 'pass', coverage: { resolved: 8, total: 8 } },
    };
    const { getByRole } = renderRow(exp);
    const link = getByRole('link');
    const label = link.getAttribute('aria-label') ?? '';
    expect(label).toContain('coverage 8/8');
    expect(label).toContain('PASS');
  });
});
