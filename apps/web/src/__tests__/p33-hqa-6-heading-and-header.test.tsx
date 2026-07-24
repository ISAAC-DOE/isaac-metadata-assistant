import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import {
  bundleRoutes,
  stubFetchRoutes,
  experimentDetail,
  draftResponse,
  pendingResponse,
  validateDryRun,
  auditNotExported,
  warningsDryRun,
  evidenceResponse,
  evidenceClassificationResponse,
  artifactsNull,
  graphStatusUnavailable,
} from '../test/apiFixtures';

/*
 * P33 Human-QA #6 (duplicate-state / casing regressions on the record surface):
 *  - metadata group headers lead with the HUMAN-facing label ("System &
 *    Instrument"), never the raw lowercase technical key ("system") as the
 *    primary heading;
 *  - the record header shows the title WITHOUT a "· New Draft" lifecycle suffix
 *    (the suffix is carried once by the Draft badge), and shows NO second raw
 *    lowercase "draft" token beside that badge, while preserving the identifier.
 */

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

// A bundle whose server-authored detail title carries a lifecycle suffix (as the
// live backend returns), so we can prove the workbench strips it for display.
function bundleWithTitle(id: string, title: string): Record<string, unknown> {
  const base = `/api/experiments/${encodeURIComponent(id)}`;
  return {
    'GET /api/experiments': { body: { experiments: [] } },
    [`GET ${base}`]: { body: { ...experimentDetail, id, title } },
    [`GET ${base}/draft`]: { body: draftResponse },
    [`GET ${base}/pending`]: { body: pendingResponse },
    [`POST ${base}/validate`]: { body: validateDryRun },
    [`POST ${base}/audit`]: { body: auditNotExported },
    [`GET ${base}/warnings`]: { body: warningsDryRun },
    [`GET ${base}/evidence`]: { body: evidenceResponse },
    [`GET ${base}/evidence-classification`]: { body: evidenceClassificationResponse },
    [`GET ${base}/artifacts`]: { body: artifactsNull },
    'GET /api/graph/status': { body: graphStatusUnavailable },
  };
}

afterEach(() => vi.unstubAllGlobals());

describe('P33 HQA#6 — group headings lead with the human label', () => {
  it('the human label leads; the raw lowercase key is never the primary heading', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { findByText, container } = renderAt('/record/demo');
    await findByText('5 Fields Need Your Confirmation');
    const header = container.querySelector('.field-group .fg-header') as HTMLElement;
    const text = header.textContent ?? '';
    const human = text.indexOf('System & Instrument');
    const rawKey = text.indexOf('system'); // the lowercase technical block key
    expect(human).toBeGreaterThanOrEqual(0);
    // the header must NOT lead with the raw lowercase key
    expect(text.trimStart().startsWith('system')).toBe(false);
    // if the raw key is still shown (as demoted provenance), it comes AFTER the label
    if (rawKey !== -1) expect(human).toBeLessThan(rawKey);
  });
});

describe('P33 HQA#6 — record header lifecycle de-duplication', () => {
  it('strips the "· New Draft" suffix from the header title', async () => {
    stubFetchRoutes(bundleWithTitle('demo', 'Synthetic XANES — CuO (Cu K-edge) · New Draft') as never);
    const { findByText, container } = renderAt('/record/demo');
    await findByText('5 Fields Need Your Confirmation');
    const ctx = container.querySelector('.record-context') as HTMLElement;
    expect(within(ctx).getByText('Synthetic XANES — CuO (Cu K-edge)')).toBeTruthy();
    expect(ctx.textContent).not.toMatch(/· New Draft/);
  });

  it('shows the Draft badge once and NO redundant raw lowercase "draft ·" token', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { findByText, container } = renderAt('/record/demo');
    await findByText('5 Fields Need Your Confirmation');
    // the Draft lifecycle badge (chip) is present exactly once …
    expect(container.querySelectorAll('.chip-draft').length).toBe(1);
    // … and the old "draft · <id>" filename token no longer duplicates it
    const file = container.querySelector('.record-file');
    expect(file?.textContent ?? '').not.toMatch(/draft ·/);
    // the record identifier is still preserved somewhere in the header
    expect((container.querySelector('.record-context') as HTMLElement).textContent).toContain('demo');
  });
});
