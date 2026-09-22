/*
 * THE CAPTURE WORKSPACE'S FOCUSED VIEWS (owner QA 2026-09-22, C1–C5), driven
 * through the real record screen.
 *
 * `capture-intake.test.tsx` owns Capture Home's own claims. This file owns what
 * only the assembled screen can show:
 *
 *   1. Each way in opens a FOCUSED view — one task, the Record Map beside it,
 *      a way back — and never expands a panel beneath the chooser again.
 *   2. Write and Voice are ONE transcript panel: typed text survives a trip to
 *      Capture Home, to the other view, and to another workspace.
 *   3. The Voice view reads the deployment's own `mcp.posture` and never says
 *      "Connected"; the local recorder is secondary, behind a disclosure.
 *   4. Proposal review is ONE focused destination, and every proposal link ever
 *      minted (`?view=capture&proposal=…`) lands there.
 *   5. Each focused view has its own document title.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { act, configure, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';

import { AppRoutes } from '../App';
import { __resetHealthCache } from '../lib/useHealth';
import { __resetRunAutosaveStore } from '../lib/runAutosaveStore';
import { claudeVoiceState } from '../components/ClaudeVoicePath';
import { CAPTURE_COPY } from '../lib/transcriptCaptureContent';
import {
  bundleRoutes,
  healthSynthetic,
  runFixture,
  runsPage,
  stubFetchRoutes,
  type RouteEntry,
} from '../test/apiFixtures';

configure({ asyncUtilTimeout: 5_000 });
vi.setConfig({ testTimeout: 30_000 });

const ID = 'demo';
const BASE = `/api/experiments/${ID}`;
const RUN = runFixture({ id: 'RUNAAA', label: 'Run 1', ordinal: 1, version: 'ra.0' });

function Address() {
  const loc = useLocation();
  return <span data-testid="address">{`${loc.pathname}${loc.search}`}</span>;
}
const address = () => screen.getByTestId('address').textContent ?? '';
const params = () => new URLSearchParams(address().split('?')[1] ?? '');

function renderAt(search: string, extra: Record<string, RouteEntry> = {}, posture = 'unmounted') {
  stubFetchRoutes({
    ...bundleRoutes(ID),
    [`GET ${BASE}/runs`]: { body: runsPage([RUN]) },
    'GET /api/health': { body: { ...healthSynthetic, mcp: { posture } } },
    ...extra,
  });
  return render(
    <MemoryRouter
      initialEntries={[`/record/${ID}${search}`]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Address />
      <AppRoutes />
    </MemoryRouter>,
  );
}

const capturePanel = () => document.querySelector('#record-workspace-capture') as HTMLElement;
/** The capture workspace, once the record has loaded and mounted it. */
const loadedCapture = () =>
  waitFor(() => {
    const el = capturePanel();
    if (el === null) throw new Error('capture workspace not mounted yet');
    return el;
  });

beforeEach(() => {
  __resetHealthCache();
  __resetRunAutosaveStore();
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe('Capture Home opens focused views', () => {
  it('Capture Home is the chooser ONLY — no transcript box, no notes queue, no proposal list', async () => {
    renderAt('?view=capture');
    await screen.findByRole('heading', { name: CAPTURE_COPY.intakeHeading });
    expect(screen.queryByRole('textbox', { name: 'Transcript' })).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Unmapped Notes' })).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Ingestion Proposals' })).toBeNull();
  });

  it('Start Writing opens the Write view: one task, the map beside it, and a way back', async () => {
    renderAt('?view=capture');
    fireEvent.click(await screen.findByRole('link', { name: /Start Writing/ }));
    await waitFor(() => expect(params().get('method')).toBe('write'));

    const main = within(capturePanel());
    expect(main.getByRole('heading', { level: 2, name: CAPTURE_COPY.intakeWriteTitle })).toBeTruthy();
    expect(main.getByRole('textbox', { name: 'Transcript' })).toBeTruthy();
    expect(main.getByRole('combobox', { name: CAPTURE_COPY.runLabel })).toBeTruthy();
    // The privacy line stays VISIBLE (DEC-35), not behind a disclosure.
    expect(main.getByText(CAPTURE_COPY.writePrivacyLine)).toBeVisible();
    // No voice controls on the Write view, and no chooser.
    expect(main.queryByRole('button', { name: 'Start Recording' })).toBeNull();
    expect(main.queryByRole('heading', { name: CAPTURE_COPY.intakeHeading })).toBeNull();
    // The Record Map is beside the task, and it has NOT chosen a run.
    expect(await main.findByText(CAPTURE_COPY.mapChooseRun)).toBeTruthy();

    fireEvent.click(main.getByRole('link', { name: CAPTURE_COPY.backToHome }));
    await waitFor(() => expect(params().has('method')).toBe(false));
    expect(await screen.findByRole('heading', { name: CAPTURE_COPY.intakeHeading })).toBeTruthy();
  });

  it('the Files view is a bridge to two real destinations and re-implements neither', async () => {
    renderAt('?view=capture&method=files');
    const main = within(await loadedCapture());
    const importLink = await main.findByRole('link', { name: CAPTURE_COPY.intakeFilesAction });
    expect(importLink.getAttribute('href')).toBe('/imports');
    expect(main.getByRole('button', { name: CAPTURE_COPY.filesAssetsAction })).toBeTruthy();
    expect(main.queryByRole('textbox', { name: 'Transcript' })).toBeNull();
  });
});

describe('Write and Voice are ONE transcript panel', () => {
  it('typed text survives Capture Home, the other view, and another workspace', async () => {
    renderAt('?view=capture&method=write');
    const box = await within(await loadedCapture()).findByRole('textbox', { name: 'Transcript' });
    fireEvent.change(box, { target: { value: 'the cryostat held at 301 K' } });

    await act(async () => {
      fireEvent.click(within(capturePanel()).getByRole('link', { name: CAPTURE_COPY.backToHome }));
    });
    expect(screen.queryByRole('textbox', { name: 'Transcript' })).toBeNull();

    await act(async () => {
      fireEvent.click(screen.getByRole('link', { name: /Open Voice Capture/ }));
    });
    // Voice view: the same text, inside the local recorder once it is opened.
    fireEvent.click(await screen.findByRole('button', { name: /Record Locally Instead/ }));
    expect(
      (within(capturePanel()).getByRole('textbox', { name: 'Transcript' }) as HTMLTextAreaElement).value,
    ).toBe('the cryostat held at 301 K');

    await act(async () => {
      fireEvent.click(screen.getByRole('link', { name: 'Runs' }));
    });
    expect(capturePanel().hidden).toBe(true);
    await act(async () => {
      fireEvent.click(screen.getByRole('link', { name: 'Capture' }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('link', { name: /Start Writing/ }));
    });
    expect(
      (within(capturePanel()).getByRole('textbox', { name: 'Transcript' }) as HTMLTextAreaElement).value,
    ).toBe('the cryostat held at 301 K');
  });
});

describe('the Voice view leads with Claude, read from the deployment', () => {
  it('an unmounted agent interface says "not enabled yet" and routes to Connect Your Agent', async () => {
    renderAt('?view=capture&method=voice', {}, 'unmounted');
    const main = within(await loadedCapture());
    expect(await main.findByText(CAPTURE_COPY.claudeUnmounted)).toBeTruthy();
    const connect = main.getByRole('link', { name: CAPTURE_COPY.claudeConnectAction });
    expect(connect.getAttribute('href')).toBe('/settings?tab=mcp');
    // The local recorder is SECONDARY: present, and collapsed.
    const local = main.getByRole('button', { name: /Record Locally Instead/ });
    expect(local).toHaveAttribute('aria-expanded', 'false');
  });

  it('MUTATION-GUARDED — never renders the word "Connected", in any posture', async () => {
    for (const posture of ['unmounted', 'local-only', 'oauth-mounted', 'remote-ready']) {
      __resetHealthCache();
      const view = renderAt('?view=capture&method=voice', {}, posture);
      await within(await loadedCapture()).findByRole('heading', { name: /Claude/ });
      await waitFor(() =>
        expect(within(capturePanel()).queryByText(CAPTURE_COPY.claudeChecking)).toBeNull(),
      );
      const claude = capturePanel().querySelector('.claude-voice')!;
      expect(claude.textContent ?? '', posture).not.toMatch(/\bconnected\b/i);
      view.unmount();
      vi.unstubAllGlobals();
    }
  });

  it('the "ready" state needs BOTH a reachable posture AND a published address', () => {
    // No such deployment exists in this build (`MCP_ENDPOINT` is null and no
    // configuration reports `remote-ready`); the derivation is still real code.
    const health = (posture: string | null) => ({ ...healthSynthetic, mcp: { posture } });
    expect(claudeVoiceState(false, undefined, null)).toEqual({ kind: 'checking' });
    expect(claudeVoiceState(true, undefined, 'https://x')).toEqual({
      kind: 'unavailable',
      reason: 'unreported',
    });
    expect(claudeVoiceState(true, health('unmounted'), 'https://x').kind).toBe('unavailable');
    expect(claudeVoiceState(true, health('local-only'), 'https://x')).toEqual({
      kind: 'unavailable',
      reason: 'local-only',
    });
    expect(claudeVoiceState(true, health('oauth-mounted'), null)).toEqual({
      kind: 'unavailable',
      reason: 'no-address',
    });
    expect(claudeVoiceState(true, health('oauth-mounted'), 'https://x')).toEqual({
      kind: 'ready',
      endpoint: 'https://x',
    });
    expect(claudeVoiceState(true, health(null), 'https://x').kind).toBe('unavailable');
    expect(claudeVoiceState(true, health('something-new'), 'https://x').kind).toBe('unavailable');
  });

  it('opening the local recorder does not duplicate the Claude explanation inside it', async () => {
    renderAt('?view=capture&method=voice');
    fireEvent.click(await screen.findByRole('button', { name: /Record Locally Instead/ }));
    // The old in-recorder drawer is reconciled into the Claude section, once.
    expect(capturePanel().querySelectorAll('.capture-mcp-route')).toHaveLength(0);
    expect(
      within(capturePanel()).getAllByRole('button', { name: CAPTURE_COPY.claudeHowHeading }),
    ).toHaveLength(1);
  });
});

describe('proposal review is ONE focused destination', () => {
  it('shows proposals first, then unmapped notes, with the Record Map beside them', async () => {
    renderAt('?view=proposals');
    const panel = await waitFor(() => {
      const el = document.querySelector('#record-workspace-proposals') as HTMLElement | null;
      if (el === null) throw new Error('no proposals workspace');
      return el;
    });
    const proposals = await within(panel).findByRole('heading', { name: 'Ingestion Proposals' });
    const notes = await within(panel).findByRole('heading', { name: 'Unmapped Notes' });
    expect(proposals.compareDocumentPosition(notes) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(panel).getByRole('complementary', { name: 'Record Map' })).toBeTruthy();
  });

  it('a proposal link minted as ?view=capture&proposal= lands on Proposals, not the chooser', async () => {
    renderAt('?view=capture&proposal=PROPX');
    const panel = await waitFor(() => {
      const el = document.querySelector('#record-workspace-proposals') as HTMLElement | null;
      if (el === null || el.hidden) throw new Error('proposals not shown');
      return el;
    });
    expect(panel.hidden).toBe(false);
    expect(screen.queryByRole('heading', { name: CAPTURE_COPY.intakeHeading })).toBeNull();
    // ...and the Capture row still reaches Capture Home from there.
    const captureLink = screen.getByRole('link', { name: 'Capture' });
    expect(new URLSearchParams(captureLink.getAttribute('href')!.split('?')[1]).has('proposal')).toBe(
      false,
    );
  });
});

describe('each focused view has its own title', () => {
  it.each([
    ['?view=capture', 'Capture'],
    ['?view=capture&method=write', `${CAPTURE_COPY.intakeWriteTitle} · Capture`],
    ['?view=capture&method=voice', `${CAPTURE_COPY.intakeVoiceTitle} · Capture`],
    ['?view=capture&method=files', `${CAPTURE_COPY.intakeFilesTitle} · Capture`],
    ['?view=proposals', 'Proposals'],
  ])('%s', async (search, lead) => {
    renderAt(search);
    await waitFor(() => expect(document.title.startsWith(`${lead} · `)).toBe(true));
  });
});
