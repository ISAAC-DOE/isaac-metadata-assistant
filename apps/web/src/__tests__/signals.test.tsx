import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { VerdictCard } from '../components/VerdictCard';
import { CoverageBadge } from '../components/CoverageBadge';
import { AdvisoryChip } from '../components/AdvisoryChip';
import {
  NO_MEASUREMENT_SERIES_CODE,
  NO_SERIES_COVERAGE_NOTE,
} from '../lib/adapt';
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
/** An advisory reporting that the record carries NO measured series. */
const ADVISORY_NO_SERIES: AdvisoryResult = {
  advisory: true,
  gating: false,
  warnings: [
    { code: 'NO_LINKS', where: 'record.links', message: 'no relationships declared' },
    {
      code: NO_MEASUREMENT_SERIES_CODE,
      where: 'measurement.series',
      message: '`measurement.series` is empty, so the record contains no measured data.',
    },
  ],
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
    const { container, getByText } = render(<CoverageBadge audit={AUDIT} advisory={ADVISORY} />);
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
    const c = render(<CoverageBadge audit={AUDIT} advisory={ADVISORY} />).container.querySelector('.coverage');
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
    const { getByText, container } = render(<CoverageBadge audit={partial} advisory={ADVISORY} />);
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
    const { container, getByText } = render(<CoverageBadge audit={AUDIT} advisory={ADVISORY} />);
    expect(getByText('33 / 33')).toBeInTheDocument();
    expect(container.querySelectorAll('.coverage-dangling')).toHaveLength(0);
  });

  it('CoverageBadge explains its denominator with a static line next to the live count', () => {
    // the count must be self-explanatory where it is shown — a user seeing
    // "N / N" must not have to guess what is counted (P21E copy requirement)
    const partial: AuditResult = { resolved: 30, total: 33, uncovered: ['links'], dangling: [] };
    for (const audit of [AUDIT, partial]) {
      const { getByText, unmount } = render(<CoverageBadge audit={audit} advisory={ADVISORY} />);
      expect(
        getByText(
          'Counted from what this record contains: fields, assets, descriptors, series, QC, links, and attribution.',
        ),
      ).toBeInTheDocument();
      unmount();
    }
  });

  it('CoverageBadge states the denominator as SCOPE, never as a claim that any target exists', () => {
    // The line this replaces read "Includes fields, assets, descriptors, series,
    // QC, links, and attribution." — a description of the enumeration RULE that a
    // reader takes as a description of THIS record. It matters because the
    // denominator is built from record content (`isaac_records.audit`), so a
    // record with fewer targets has a smaller denominator and still reads as a
    // full count: measured 33 / 33 with a series, 32 / 32 with the series emptied.
    const { container, getByText } = render(<CoverageBadge audit={AUDIT} advisory={ADVISORY} />);
    expect(
      getByText(
        'A full count means every target this record has is evidenced — not that any particular target exists.',
      ),
    ).toBeInTheDocument();
    // The old wording must not come back alongside the new one.
    expect(container.textContent).not.toContain('Includes fields, assets, descriptors');
  });

  it('CoverageBadge discloses a missing measurement series when the advisory reports one', () => {
    // The record-specific half of the same defect. A record whose
    // `measurement.series` is `[]` contributes no series target, so `N / N` is
    // reachable with zero measured data — and this is the surface that shows N / N.
    const { getByText } = render(
      <CoverageBadge audit={AUDIT} advisory={ADVISORY_NO_SERIES} />,
    );
    expect(getByText(NO_SERIES_COVERAGE_NOTE)).toBeInTheDocument();
  });

  it('CoverageBadge does NOT disclose a missing series when the advisory does not report one', () => {
    // The negative half: the disclosure is keyed on the backend advisory, never
    // shown unconditionally. An always-on note would be a claim about records that
    // do carry measured data.
    const { container } = render(<CoverageBadge audit={AUDIT} advisory={ADVISORY} />);
    expect(container.textContent).not.toContain(NO_SERIES_COVERAGE_NOTE);
    expect(container.querySelector('.coverage-sub-scope')).toBeNull();
  });

  it('the series disclosure states an observation and does not classify the science', () => {
    // The domain question — is an empty series invalid, incomplete, not
    // applicable, or deliberately empty? — belongs to a scientific owner. The
    // vendored schema sets no `minItems`, so `[]` validates with zero errors, and
    // nothing on this surface may decide which of the four it is. Asserted as a
    // SET of forbidden verdict words, so adding a new one to the sentence fails.
    const { container } = render(
      <CoverageBadge audit={AUDIT} advisory={ADVISORY_NO_SERIES} />,
    );
    const scope = container.querySelector('.coverage-sub-scope')?.textContent ?? '';
    expect(scope).not.toBe('');
    for (const forbidden of [
      'invalid',
      'incomplete',
      'not applicable',
      'failed',
      'compromised',
      'suspicious',
      'should',
      'must',
    ]) {
      expect(scope.toLowerCase()).not.toContain(forbidden);
    }
  });
});
