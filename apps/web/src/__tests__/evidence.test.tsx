import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { GraphStatusChip } from '../components/GraphStatusChip';
import { evidenceBundleRoutes, stubFetchRoutes } from '../test/apiFixtures';

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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('S5 · Evidence & File Preview (live)', () => {
  it('renders the live evidence trail: direct + namespaced entries in two sections', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { container, findByText, getByText } = renderAt('/record/demo/evidence');

    // both coverage sections, from /evidence
    expect(await findByText('Direct Fields')).toBeInTheDocument();
    expect(getByText('Namespaced')).toBeInTheDocument();
    expect(getByText('not in coverage count')).toBeInTheDocument();

    // dotted-path (direct) + namespaced entries, keys rendered verbatim in the trail
    expect(getByText('system.technique', { selector: '.trail-key' })).toBeInTheDocument();
    expect(
      getByText('assets:processing_notebook', { selector: '.trail-key' }),
    ).toBeInTheDocument();
    expect(
      getByText('implicit:absorbing_element', { selector: '.trail-key' }),
    ).toBeInTheDocument();

    // the sidecar is labeled an assistant convention, not an official standard
    expect(
      getByText('sidecar · assistant convention, not an official ISAAC standard', {
        selector: '.trail-flag',
      }),
    ).toBeInTheDocument();

    // per the S5 screen spec there is NO dedicated assistant panel here —
    // the provenance copy carries the explanation (design authority, D1 review)
    expect(container.querySelector('.assistant')).toBeNull();
  });

  it('selecting an entry drives the preview and highlights the cited line', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { container, findByText, getByText } = renderAt('/record/demo/evidence');

    // default selection = first entry (a spreadsheet-cited field): no cited line
    await findByText('Direct Fields');
    expect(container.querySelector('.preview-prov-text')!.textContent).toMatch(
      /campaign spreadsheet/,
    );
    expect(container.querySelector('.preview-line.cited')).toBeNull();

    // select the asset entry → preview swaps to the archive listing with line 16 cited
    fireEvent.click(getByText('assets:processing_notebook'));

    expect(container.querySelector('.preview-prov-text')!.textContent).toMatch(
      /archive listing/,
    );
    const cited = container.querySelector('.preview-line.cited');
    expect(cited).not.toBeNull();
    expect(cited!.textContent).toContain('16');
    expect(cited!.textContent).toContain('xanes_reduction_v2.ipynb');
    // the Cited tag marks it
    expect(getByText('Cited')).toBeInTheDocument();
  });

  it('shows a copyable sha256 for the selected asset entry (never truncated)', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { findByText, getByText, getAllByLabelText, container } = renderAt(
      '/record/demo/evidence',
    );

    await findByText('Direct Fields');
    fireEvent.click(getByText('assets:processing_notebook'));

    const copyButtons = getAllByLabelText('Copy sha256');
    expect(copyButtons.length).toBeGreaterThan(0);

    // the full hash is rendered verbatim in a horizontally-scrollable mono field
    const fullSha = 'c3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b345';
    const hash = container.querySelector('.hash-field .hash');
    expect(hash!.textContent).toContain(fullSha);

    // clicking copy writes the full value to the clipboard
    const writeText = vi.fn();
    Object.assign(navigator, { clipboard: { writeText } });
    fireEvent.click(copyButtons[0]);
    expect(writeText).toHaveBeenCalledWith(fullSha);
  });

  it('Record JSON and Sidecar JSON tabs show distinct, real artifact content', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { findByText, getByText, container } = renderAt('/record/demo/evidence');

    await findByText('Direct Fields');

    fireEvent.click(getByText('Record JSON'));
    const recordText = container.querySelector('.preview-json')!.textContent!;
    expect(recordText).toContain('asset_id');
    expect(recordText).not.toContain('generated_utc');

    fireEvent.click(getByText('Sidecar JSON'));
    const sidecarText = container.querySelector('.preview-json')!.textContent!;
    expect(sidecarText).toContain('generated_utc');
    expect(sidecarText).toContain('evidence');

    // the two tabs are genuinely different artifacts, never blended
    expect(recordText).not.toEqual(sidecarText);
  });

  it('mounts the memory-plane graph status chip in the status bar', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { findByText, getByText } = renderAt('/record/demo/evidence');
    await findByText('Direct Fields');
    // the /graph/status chip (missing in this fixture) degrades quietly
    expect(getByText('Memory: Missing')).toBeInTheDocument();
    expect(getByText('memory plane')).toBeInTheDocument();
  });
});

describe('GraphStatusChip renders all three states, never implies validation', () => {
  it('renders Fresh / Stale / Missing with the memory-plane note', () => {
    for (const [status, label] of [
      ['fresh', 'Fresh'],
      ['stale', 'Stale'],
      ['missing', 'Missing'],
    ] as const) {
      const { getByText, container, unmount } = render(
        <GraphStatusChip status={status} note="Graphify is a memory/query layer — never a validator." />,
      );
      expect(getByText(`Memory: ${label}`)).toBeInTheDocument();
      expect(getByText('memory plane')).toBeInTheDocument();
      // never a verdict / validity claim
      expect(container.textContent).not.toMatch(/\b(PASS|FAIL|valid)\b/i);
      unmount();
    }
  });

  it('unavailable degrades quietly to Missing (not an error state)', () => {
    const { getByText, container } = render(<GraphStatusChip status="unavailable" />);
    expect(getByText('Memory: Missing')).toBeInTheDocument();
    expect(container.querySelector('.graph-missing')).not.toBeNull();
  });
});
