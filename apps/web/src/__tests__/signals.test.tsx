import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { VerdictCard } from '../components/VerdictCard';
import { CoverageBadge } from '../components/CoverageBadge';
import { AdvisoryChip } from '../components/AdvisoryChip';
import type { AdvisoryResult, AuditResult, ValidationResult } from '../lib/types';

const PASS: ValidationResult = {
  verdict: 'pass',
  ok: true,
  schemaVersion: 'v1.05',
  errors: [],
};
const AUDIT: AuditResult = { resolved: 33, total: 33, uncovered: [], dangling: [] };
const ADVISORY: AdvisoryResult = {
  advisory: true,
  gating: false,
  warnings: [{ code: 'NO_LINKS', where: 'record.links', message: 'no relationships declared' }],
};

describe('the three signals are separate components with distinct treatments', () => {
  it('VerdictCard renders the reserved PASS verdict with its own class', () => {
    const { container, getByText } = render(<VerdictCard result={PASS} />);
    expect(getByText('PASS')).toBeInTheDocument();
    expect(container.querySelector('.verdict-pass')).not.toBeNull();
    // verdict styling belongs to no other signal
    expect(container.querySelector('.coverage')).toBeNull();
    expect(container.querySelector('.advisory')).toBeNull();
  });

  it('CoverageBadge is neutral slate N/N — labeled "not a verdict", never a PASS', () => {
    const { container, getByText } = render(<CoverageBadge audit={AUDIT} />);
    expect(container.querySelector('.coverage')).not.toBeNull();
    expect(getByText('33 / 33')).toBeInTheDocument();
    expect(getByText(/coverage · not a verdict/)).toBeInTheDocument();
    // coverage must not borrow verdict classes or say PASS
    expect(container.querySelector('.verdict-pass')).toBeNull();
    expect(container.textContent).not.toMatch(/\bPASS\b/);
  });

  it('AdvisoryChip is soft amber, non-gating, and contains no fail/error wording', () => {
    const { container, getByText } = render(<AdvisoryChip advisory={ADVISORY} />);
    expect(container.querySelector('.advisory')).not.toBeNull();
    expect(getByText('[NO_LINKS]')).toBeInTheDocument();
    expect(getByText(/non-gating/)).toBeInTheDocument();
    // never mistakable for a FAIL
    expect(container.querySelector('.verdict-fail')).toBeNull();
    expect(container.textContent).not.toMatch(/\b(FAIL|error|invalid)\b/i);
  });

  it('the three components use three distinct root classes', () => {
    const v = render(<VerdictCard result={PASS} />).container.querySelector('.verdict');
    const c = render(<CoverageBadge audit={AUDIT} />).container.querySelector('.coverage');
    const a = render(<AdvisoryChip advisory={ADVISORY} />).container.querySelector('.advisory');
    const classes = [v?.className, c?.className, a?.className];
    expect(new Set(classes).size).toBe(3);
  });

  it('CoverageBadge lists uncovered AND dangling targets separately, never merged into one list', () => {
    const partial: AuditResult = {
      resolved: 30,
      total: 33,
      uncovered: ['qc.completeness_score', 'links'],
      dangling: ['assets:legacy_notebook'],
    };
    const { getByText, container } = render(<CoverageBadge audit={partial} />);
    expect(getByText('30 / 33')).toBeInTheDocument();
    // every uncovered target renders
    expect(getByText('qc.completeness_score')).toBeInTheDocument();
    expect(getByText('links')).toBeInTheDocument();
    // every dangling target renders too
    expect(getByText('assets:legacy_notebook')).toBeInTheDocument();
    // two distinct lists (uncovered, dangling), same neutral treatment
    expect(container.querySelectorAll('.coverage-dangling')).toHaveLength(2);
  });

  it('CoverageBadge at full coverage renders no uncovered/dangling section', () => {
    const { container, getByText } = render(<CoverageBadge audit={AUDIT} />);
    expect(getByText('33 / 33')).toBeInTheDocument();
    expect(container.querySelectorAll('.coverage-dangling')).toHaveLength(0);
  });

  it('CoverageBadge explains its denominator with a static line next to the live count', () => {
    // the count must be self-explanatory where it is shown — a user seeing
    // "N / N" must not have to guess what is counted (P21E copy requirement)
    const partial: AuditResult = { resolved: 30, total: 33, uncovered: ['links'], dangling: [] };
    for (const audit of [AUDIT, partial]) {
      const { getByText, unmount } = render(<CoverageBadge audit={audit} />);
      expect(
        getByText('Includes fields, assets, descriptors, series, QC, links, and attribution.'),
      ).toBeInTheDocument();
      unmount();
    }
  });
});
