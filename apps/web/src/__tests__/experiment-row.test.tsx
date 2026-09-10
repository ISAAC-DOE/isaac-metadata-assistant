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

// P33 S1 · Dashboard card contract (D1, D2, C1). The card shows a clean scientific
// title, ONE lifecycle badge + ONE neutral date badge beneath it, no technique badge,
// and a right side that carries an actionable field-count chip (Needs Attention) or a
// chevron only (In Review / Ready to Export / Done). `Exported` is a lifecycle badge,
// never a right-side chip. State is never communicated by visuals alone.

const draftNeedsAttention: ExperimentSummary = {
  id: '01SYNTH1',
  title: 'Synthetic XANES — CuO (Cu K-edge)',
  technique: 'Cu K-edge XANES',
  idOrDraft: 'draft',
  lifecycle: 'draft',
  date: { iso: '2026-07-12', display: 'Jul 12, 2026', accessible: 'Created July 12, 2026' },
  group: 'needsAttention',
  trailing: { needsYouCount: 5 },
};

const exportedDone: ExperimentSummary = {
  id: '01SYNTH5',
  title: 'Synthetic XANES — CuO (Cu K-edge)',
  technique: 'Cu K-edge XANES',
  idOrDraft: '01SYNTHXANESSEED0000000005',
  lifecycle: 'exported',
  date: { iso: '2026-07-12', display: 'Jul 12, 2026', accessible: 'Created July 12, 2026' },
  group: 'done',
  trailing: {},
};

const inReview: ExperimentSummary = {
  ...draftNeedsAttention,
  id: '01SYNTH3',
  group: 'inReview',
  trailing: {},
};

const readyToExport: ExperimentSummary = {
  ...draftNeedsAttention,
  id: '01SYNTH4',
  group: 'ready',
  trailing: {},
};

describe('ExperimentRow — D1 title & badges', () => {
  it('renders the clean scientific title', () => {
    const { getByText } = renderRow(draftNeedsAttention);
    expect(getByText('Synthetic XANES — CuO (Cu K-edge)')).toBeTruthy();
  });

  it('does NOT render a separate technique badge', () => {
    const { queryByText } = renderRow(draftNeedsAttention);
    expect(queryByText('Cu K-edge XANES')).toBeNull();
  });

  it('renders exactly one lifecycle badge (Draft / Exported)', () => {
    expect(renderRow(draftNeedsAttention).getByText('Draft')).toBeTruthy();
    expect(renderRow(exportedDone).getByText('Exported')).toBeTruthy();
  });

  it('renders the visible short date and an accessible full date', () => {
    const { getByText, getByLabelText } = renderRow(draftNeedsAttention);
    expect(getByText('Jul 12, 2026')).toBeTruthy();
    // full, unambiguous date is available to assistive tech
    const time = getByLabelText('Created July 12, 2026');
    expect(time).toBeTruthy();
    // the <time> carries a VALID machine datetime (not the prose string)
    expect(time.tagName.toLowerCase()).toBe('time');
    expect(time.getAttribute('datetime')).toBe('2026-07-12');
  });

  it('does NOT render the raw ULID / "draft" text on the card face', () => {
    const { queryByText } = renderRow(exportedDone);
    expect(queryByText('01SYNTHXANESSEED0000000005')).toBeNull();
  });
});

describe('ExperimentRow — D2/C1 right side', () => {
  it('Needs Attention shows an actionable field-count chip in the trailing region', () => {
    const { container } = renderRow(draftNeedsAttention);
    const trailing = container.querySelector('.exp-trailing');
    expect(trailing?.textContent).toContain('5 Fields Need You');
  });

  // Found by independent design review, 2026-09: the row rendered "1 Fields Need You"
  // for a record with exactly one outstanding field — wrong on both the noun (Fields
  // vs Field) and the verb (Need vs Needs). `pending_count > 0` is the only route to
  // this chip (`workspace.py`: "pending > 0 -> needs_attention"), so 0 never reaches
  // it and is not asserted here.
  it('singular (1) reads "1 Field Needs You", not "1 Fields Need You"', () => {
    const one: ExperimentSummary = { ...draftNeedsAttention, trailing: { needsYouCount: 1 } };
    const { container } = renderRow(one);
    const trailing = container.querySelector('.exp-trailing');
    expect(trailing?.textContent).toContain('1 Field Needs You');
    expect(trailing?.textContent).not.toContain('1 Fields');
    expect(trailing?.textContent).not.toContain('Need You');
  });

  it('plural (2) reads "2 Fields Need You"', () => {
    const two: ExperimentSummary = { ...draftNeedsAttention, trailing: { needsYouCount: 2 } };
    const { container } = renderRow(two);
    const trailing = container.querySelector('.exp-trailing');
    expect(trailing?.textContent).toContain('2 Fields Need You');
  });

  it('Done shows NO status chip on the right — chevron only (Exported is a lifecycle badge, not a right chip)', () => {
    const { container } = renderRow(exportedDone);
    const trailing = container.querySelector('.exp-trailing');
    expect(trailing?.textContent?.trim()).toBe('');
    // the only "Exported" is the lifecycle badge in the metadata row
    const sub = container.querySelector('.exp-sub');
    expect(sub?.textContent).toContain('Exported');
  });

  it('In Review shows chevron only (no repeated group-state chip)', () => {
    const { container } = renderRow(inReview);
    expect(container.querySelector('.exp-trailing')?.textContent?.trim()).toBe('');
  });

  it('Ready to Export shows chevron only', () => {
    const { container } = renderRow(readyToExport);
    expect(container.querySelector('.exp-trailing')?.textContent?.trim()).toBe('');
  });
});

describe('ExperimentRow — accessible name parity (CQ-10 invariant preserved)', () => {
  it('Needs Attention: name carries title + lifecycle + group state + count, never "undefined"', () => {
    const label = renderRow(draftNeedsAttention).getByRole('link').getAttribute('aria-label') ?? '';
    expect(label).not.toContain('undefined');
    expect(label).toContain('Synthetic XANES — CuO (Cu K-edge)');
    expect(label).toContain('Draft');
    expect(label).toContain('Needs Attention');
    expect(label).toContain('5 fields need you');
  });

  // The accessible name builds the same count phrase as the visible chip
  // (`describeAccessibleName`'s `countPart`), and had the identical singular/verb
  // defect — a screen reader would have announced "1 field need you".
  it('singular (1) accessible name reads "1 field needs you"', () => {
    const one: ExperimentSummary = { ...draftNeedsAttention, trailing: { needsYouCount: 1 } };
    const label = renderRow(one).getByRole('link').getAttribute('aria-label') ?? '';
    expect(label).toContain('1 field needs you');
    expect(label).not.toContain('1 fields');
    expect(label).not.toContain('field need you');
  });

  it('plural (2) accessible name reads "2 fields need you"', () => {
    const two: ExperimentSummary = { ...draftNeedsAttention, trailing: { needsYouCount: 2 } };
    const label = renderRow(two).getByRole('link').getAttribute('aria-label') ?? '';
    expect(label).toContain('2 fields need you');
  });

  it('Done: name carries lifecycle + group state, never "undefined" or stray coverage', () => {
    const label = renderRow(exportedDone).getByRole('link').getAttribute('aria-label') ?? '';
    expect(label).not.toContain('undefined');
    expect(label).toContain('Exported');
    expect(label).toContain('Done');
  });
});
