import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { GraphStatusChip } from '../components/GraphStatusChip';
import { evidenceBundleRoutes, stubFetchDown, stubFetchRoutes } from '../test/apiFixtures';

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

    // P25.5: the Evidence context now mounts the grounded assistant (Phase 25
    // plan §20). The panel is subordinate — truth (trail + preview) renders first.
    expect(container.querySelector('.assistant')).not.toBeNull();
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
    // the /graph/status chip (unavailable in this fixture) degrades quietly
    expect(getByText('Memory: Unavailable')).toBeInTheDocument();
    expect(getByText('memory plane')).toBeInTheDocument();
  });
});

describe('S5 · grounded assistant (P25.5) — subordinate, guided-only, LLM-free', () => {
  it('mounts the assistant with exactly the three approved evidence chips', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { container, findByText, getByText } = renderAt('/record/demo/evidence');

    await findByText('Direct Fields');
    const panel = container.querySelector('.assistant');
    expect(panel).not.toBeNull();

    // exactly the three approved chip labels render as prompt buttons
    expect(getByText('Why multiple evidence entries?')).toBeInTheDocument();
    expect(getByText('What is the evidence sidecar?')).toBeInTheDocument();
    expect(getByText('Where are the exported artifacts?')).toBeInTheDocument();
    expect(panel!.querySelectorAll('.assistant-prompt').length).toBe(3);
  });

  it('is guided-prompts-only — the note is present and there is NO textbox/send button', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { container, findByText, getByText, queryByRole } = renderAt('/record/demo/evidence');

    await findByText('Direct Fields');
    expect(
      getByText('Guided prompts only — the assistant answers the suggested questions above.'),
    ).toBeInTheDocument();
    // no free-text affordance at all
    expect(container.querySelector('.assistant textarea')).toBeNull();
    expect(container.querySelector('.assistant input')).toBeNull();
    expect(queryByRole('textbox')).toBeNull();
    expect(queryByRole('button', { name: /send/i })).toBeNull();
  });

  it('selecting a different trail entry updates the multiplicity reply to that path', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { container, findByText, getByText } = renderAt('/record/demo/evidence');

    await findByText('Direct Fields');
    // default selection = first entry (system.technique, a single spreadsheet entry)
    const reply = () => container.querySelector('.assistant-reply')!.textContent!;
    expect(reply()).toContain('system.technique has 1 evidence entry: spreadsheet.');

    // select the asset (2 entries: file_listing + user_confirmation)
    fireEvent.click(getByText('assets:processing_notebook'));
    expect(reply()).toContain('assets:processing_notebook has 2 evidence entries');
    expect(reply()).toContain('Multiple entries can provide separate support');
    // provenance must NOT leak into the assistant copy
    expect(reply()).not.toContain('raw_scan_listing.txt');
    expect(reply()).not.toContain('xanes_reduction_v2.ipynb');
  });

  it('clicking a chip issues NO new network request (pure, LLM-free)', async () => {
    const calls = stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { container, findByText, getByText } = renderAt('/record/demo/evidence');

    await findByText('Direct Fields');
    const before = calls.length;

    fireEvent.click(getByText('What is the evidence sidecar?'));
    // the sidecar answer swaps in with no fetch
    expect(container.querySelector('.assistant-reply')!.textContent).toContain(
      'assistant convention, not part of the official ISAAC schema',
    );
    expect(calls.length).toBe(before);
  });

  it('does NOT render an assistant panel in the loading state', () => {
    // never-resolving fetch keeps the screen in its loading state
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})));
    const { container, getByRole } = renderAt('/record/demo/evidence');
    expect(getByRole('status')).toBeInTheDocument(); // LoadingPanel
    expect(container.querySelector('.assistant')).toBeNull();
  });

  it('does NOT render an assistant panel when the backend is down', async () => {
    stubFetchDown();
    const { container, findByText } = renderAt('/record/demo/evidence');
    await findByText('Backend Not Running');
    expect(container.querySelector('.assistant')).toBeNull();
  });
});

describe('GraphStatusChip shows the availability axis, never implies validation', () => {
  it('renders Available / Unavailable with the memory-plane note', () => {
    for (const [availability, label] of [
      ['available', 'Available'],
      ['unavailable', 'Unavailable'],
    ] as const) {
      const { getByText, container, unmount } = render(
        <GraphStatusChip
          availability={availability}
          note="Project Memory provides leads and provenance, never a correctness ruling."
        />,
      );
      expect(getByText(`Memory: ${label}`)).toBeInTheDocument();
      expect(getByText('memory plane')).toBeInTheDocument();
      // never a verdict / validity claim on the memory plane
      expect(container.textContent).not.toMatch(/\b(PASS|FAIL|valid|invalid)\b/i);
      unmount();
    }
  });

  it('unavailable degrades quietly (not an error state)', () => {
    const { getByText, container } = render(<GraphStatusChip availability="unavailable" />);
    expect(getByText('Memory: Unavailable')).toBeInTheDocument();
    expect(container.querySelector('.graph-unavailable')).not.toBeNull();
  });
});
