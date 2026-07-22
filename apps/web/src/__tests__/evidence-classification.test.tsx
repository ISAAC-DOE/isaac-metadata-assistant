import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { EvidenceClassificationPanel } from '../components/EvidenceClassificationPanel';
import {
  evidenceBundleRoutes,
  evidenceClassificationResponse,
  stubFetchDown,
  stubFetchRoutes,
} from '../test/apiFixtures';
import type { ApiEvidenceClassification } from '../lib/types';

function renderAt(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

const CLASS_LABELS = [
  'Supported',
  'Inferred Candidate',
  'Insufficient Evidence',
  'Conflicting Evidence',
  'Unknown',
] as const;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('P28.5 · EvidenceClassificationPanel (evidence-support axis)', () => {
  const panel = (overrides: Partial<ApiEvidenceClassification> = {}, stale = false) =>
    render(
      <EvidenceClassificationPanel
        classification={{ ...evidenceClassificationResponse, ...overrides }}
        stale={stale}
        onRefresh={() => {}}
      />,
    );

  it('renders all five classes with a non-color signal (icon + text label + explanation)', () => {
    const { container, getAllByText } = panel();

    // each class label appears (in the summary chip AND its field row chip)
    for (const label of CLASS_LABELS) {
      expect(getAllByText(label).length).toBeGreaterThan(0);
    }

    // every chip carries an inline icon — the signal is never color alone
    const chips = container.querySelectorAll('.evclass-list .chip');
    expect(chips.length).toBe(5);
    chips.forEach((chip) => {
      expect(chip.querySelector('svg')).not.toBeNull(); // icon present
      expect((chip.textContent ?? '').trim().length).toBeGreaterThan(0); // text present
    });

    // the deterministic explanation is shown per field
    expect(container.querySelectorAll('.evclass-explanation').length).toBe(5);
  });

  it('an inferred_candidate is visually distinct from a supported/confirmed value', () => {
    const { container } = panel();

    const supportedRow = container.querySelector('.evclass-row[data-class="supported"]')!;
    const candidateRow = container.querySelector('.evclass-row[data-class="inferred_candidate"]')!;
    expect(supportedRow).not.toBeNull();
    expect(candidateRow).not.toBeNull();

    const supportedChip = supportedRow.querySelector('.chip')!;
    const candidateChip = candidateRow.querySelector('.chip')!;

    // distinct palette class (candidate is dashed, never the confirmed style)
    expect(supportedChip.className).toContain('chip-ev-supported');
    expect(candidateChip.className).toContain('chip-ev-candidate');
    expect(candidateChip.className).not.toContain('chip-ev-supported');

    // distinct label + distinct icon glyph
    expect(supportedChip.textContent).toContain('Supported');
    expect(candidateChip.textContent).toContain('Inferred Candidate');
    expect(candidateChip.textContent).not.toContain('Confirmed');
    const supportedIcon = supportedChip.querySelector('svg')!.getAttribute('class');
    const candidateIcon = candidateChip.querySelector('svg')!.getAttribute('class');
    expect(supportedIcon).not.toEqual(candidateIcon);
  });

  it('the per-field info affordance is a keyboard-operable button that toggles guidance', () => {
    const { container, getByText, queryByText } = panel();

    const infoButtons = container.querySelectorAll<HTMLButtonElement>('.evclass-info-btn');
    expect(infoButtons.length).toBe(5);
    const btn = infoButtons[1]; // the inferred_candidate row

    // native <button> → in the tab order + focusable (keyboard reachable)
    expect(btn.tagName).toBe('BUTTON');
    expect(btn.getAttribute('aria-expanded')).toBe('false');
    btn.focus();
    expect(document.activeElement).toBe(btn);

    // closed → no guidance region yet
    expect(queryByText(/What to do next\./)).toBeNull();

    fireEvent.click(btn);
    expect(btn.getAttribute('aria-expanded')).toBe('true');
    // guidance names the class meaning + the next step
    expect(getByText(/What this means\./)).toBeInTheDocument();
    expect(getByText(/Confirm or correct it in Complete Missing Fields/)).toBeInTheDocument();
    // the region is wired to the button for screen readers
    expect(btn.getAttribute('aria-controls')).toBe(
      container.querySelector('.evclass-info')!.getAttribute('id'),
    );
  });

  it('renders the honest empty state when there are no fields', () => {
    const { getByText, container } = panel({
      field_results: [],
      counts: {
        supported: 0,
        inferred_candidate: 0,
        insufficient_evidence: 0,
        conflicting_evidence: 0,
        unknown: 0,
      },
    });
    expect(getByText(/No fields to classify yet/)).toBeInTheDocument();
    expect(container.querySelectorAll('.evclass-row').length).toBe(0);
  });

  it('shows the stale/out-of-date affordance only when the view rev drifts from the record', () => {
    const fresh = panel({}, false);
    expect(fresh.queryByText(/may be out of date/)).toBeNull();
    fresh.unmount();

    const drifted = panel({ record_rev: 999 }, true);
    expect(drifted.getByText(/may be out of date/)).toBeInTheDocument();
    expect(drifted.getByRole('button', { name: 'Refresh' })).toBeInTheDocument();
  });

  it('never surfaces a raw answer, secret, or absolute path (leak-safe end to end)', () => {
    const { container } = panel();
    const text = container.textContent ?? '';
    expect(text).not.toContain('/Users/');
    expect(text).not.toMatch(/[0-9a-f]{32,}/i); // no sha256/token blobs
  });
});

describe('P28.5 · EvidenceExplorer wires the classification to the record', () => {
  it('surfaces the Evidence Support panel bound to the loaded record', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { findByText, getAllByText } = renderAt('/record/demo/evidence');

    expect(await findByText('Evidence Support')).toBeInTheDocument();
    // coherent by default (record_rev matches the detail version rev) → no stale hint
    for (const label of CLASS_LABELS) {
      expect(getAllByText(label).length).toBeGreaterThan(0);
    }
  });

  it('shows the refresh affordance when the classification rev drifts from the record', async () => {
    stubFetchRoutes({
      ...evidenceBundleRoutes('demo'),
      'GET /api/experiments/demo/evidence-classification': {
        body: { ...evidenceClassificationResponse, record_rev: 999 },
      },
    });
    const { findByText } = renderAt('/record/demo/evidence');
    expect(await findByText(/may be out of date/)).toBeInTheDocument();
  });

  it('stays in the loading state until the bundle resolves (no panel yet)', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})));
    const { container, getByRole } = renderAt('/record/demo/evidence');
    expect(getByRole('status')).toBeInTheDocument(); // LoadingPanel
    expect(container.querySelector('.evclass')).toBeNull();
  });

  it('renders the backend-down state instead of the panel when the API is unreachable', async () => {
    stubFetchDown();
    const { container, findByText } = renderAt('/record/demo/evidence');
    await findByText('Backend Not Running');
    expect(container.querySelector('.evclass')).toBeNull();
  });
});
