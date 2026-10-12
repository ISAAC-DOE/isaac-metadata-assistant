/*
 * B-A17 — counts that read as placeholders or as bare adjectives.
 *
 * Measured on the rendered screens (grep -a over the source, then confirmed in Chromium):
 *   · the advisory chip and the status bar printed "2 advisory" — an adjective with its
 *     noun dropped — beside "1 advisory", so the plural was invisible;
 *   · the CSV reconciliation summary printed "Reconciled 3 mapped field(s) …", a literal
 *     placeholder (the same `field(s)` the assistant's own formatter promises never to
 *     emit — `assistantPaths.count`'s docstring);
 *   · a removed run said "1 run remain in this record" (see `run-removal.test.tsx`).
 *
 * The advisory noun is "advisories" — the plural of the word already on screen — rather
 * than a longer "advisory notes", because the status bar is a fixed single-line row whose
 * width is measured (`LAYOUT-01`), and "· non-gating" must keep fitting beside it.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, waitFor } from '@testing-library/react';
import { AdvisoryChip } from '../components/AdvisoryChip';
import { StatusBar } from '../components/StatusBar';
import { CsvReconcilePanel } from '../components/CsvReconcilePanel';
import { stubFetchRoutes } from '../test/apiFixtures';
import type { AdvisoryResult } from '../lib/types';

const warn = (code: string) => ({ code, where: 'record.links', message: 'm' });
const advisory = (n: number): AdvisoryResult => ({
  advisory: true,
  gating: false,
  warnings: Array.from({ length: n }, (_, i) => warn(`NO_LINKS_${i}`)),
});

describe('the advisory count agrees with its number', () => {
  it.each([
    [1, '1 advisory'],
    [2, '2 advisories'],
    [5, '5 advisories'],
  ])('AdvisoryChip: %i → "%s"', (n, expected) => {
    const { container } = render(<AdvisoryChip advisory={advisory(n)} />);
    expect(container.querySelector('.advisory-title')?.textContent).toBe(expected);
  });

  it('AdvisoryChip: none is still "No Advisory"', () => {
    const { container } = render(<AdvisoryChip advisory={advisory(0)} />);
    expect(container.querySelector('.advisory-title')?.textContent).toBe('No Advisory');
  });

  const PASS = { verdict: 'pass', ok: true, schemaVersion: '1.05', errors: [] } as never;
  const COVERAGE = { covered: 3, total: 3 } as never;

  it.each([
    [1, '1 advisory · non-gating'],
    [2, '2 advisories · non-gating'],
  ])('StatusBar: %i → "%s"', (n, expected) => {
    const { container } = render(
      <StatusBar phase="Draft" validation={PASS} coverage={COVERAGE} advisory={advisory(n)} />,
    );
    expect(container.querySelector('.statusbar-advisory')?.textContent).toBe(expected);
  });
});

describe('the CSV reconciliation summary carries no placeholder', () => {
  const EXP = 'demo';
  const preview = (count: number) => ({
    format: 'isaac_campaign_csv',
    source_name: 'campaign.csv',
    parser_id: 'p',
    parser_version: '1',
    source_record_rev: 3,
    row_count: count,
    recognized_header_count: 1,
    unknown_header_warnings: [],
    candidate_count: count,
    reconciliation_summary: { matches_current: count, conflicts_with_current: 0, absent_from_record: 0 },
    candidates: [],
    warnings: [],
  });

  beforeEach(() => vi.restoreAllMocks());

  async function summaryFor(count: number): Promise<string> {
    stubFetchRoutes({
      [`POST /api/experiments/${EXP}/ingestion/csv/preview`]: { body: preview(count) },
    });
    const { container, unmount } = render(<CsvReconcilePanel experimentId={EXP} version="v.1" />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(['section,field,value\n'], 'campaign.csv', { type: 'text/csv' })] },
    });
    await waitFor(() => expect(container.querySelector('.csv-recon-summary')).not.toBeNull());
    const text = container.querySelector('.csv-recon-summary')!.textContent ?? '';
    unmount();
    return text;
  }

  it('says "1 mapped field" and "3 mapped fields", never "field(s)"', async () => {
    const one = await summaryFor(1);
    expect(one).toMatch(/Reconciled 1 mapped field against the current record/);
    const three = await summaryFor(3);
    expect(three).toMatch(/Reconciled 3 mapped fields against the current record/);
    for (const t of [one, three]) expect(t).not.toContain('(s)');
  });
});
