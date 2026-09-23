/**
 * CAPTURE HOME — the four ways in, and what each may claim.
 *
 * REWRITTEN 2026-09-22 (owner QA C1), and the rewrite INVERTS rather than drops
 * what the old file pinned:
 *
 *  - ~~"writing and recording open the capture panel"~~ — the chooser no longer
 *    expands a panel beneath itself (1,795px empty, 4,297px after Start Writing,
 *    and Start Writing and Open Recorder opened the SAME panel). Each way in is
 *    now a LINK to a focused view on this record (`?view=capture&method=…`), so it
 *    is addressable, bookmarkable and reachable again with Back. Asserted below.
 *  - The route that works in every deployment is still the ONE primary action,
 *    and still first — unchanged, and still mutation-guarded.
 *  - The honesty bans are unchanged in kind: Capture Home must never claim
 *    transcription works, and the files route must never claim a file is uploaded
 *    or read. What moved is the honest SENTENCE the ban could otherwise be
 *    satisfied by deleting: the chooser now names the real voice alternative
 *    ("type what was said") instead of the provider paragraph, which lives with
 *    the local recorder (the capability seam's own report) and is pinned there.
 *  - ~~The chooser and the panel, wired together (one primary control; open,
 *    close, reopen)~~ — the pairing no longer exists on one screen. The
 *    single-primary property is asserted over Capture Home itself; the focused
 *    views' own behaviour is `capture-workspace.test.tsx`'s.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { CaptureIntake } from '../components/CaptureIntake';
import { CAPTURE_COPY } from '../lib/transcriptCaptureContent';
import type { ApiCaptureSummary } from '../lib/types';
import { __resetHealthCache } from '../lib/useHealth';
import { healthSynthetic, stubFetchRoutes } from '../test/apiFixtures';

const RECORD = '/record/01SYNTHTESTEXP000000000000';

function renderHome(
  captureSummary: ApiCaptureSummary | null = null,
  search = '?view=capture',
) {
  return render(
    <MemoryRouter
      initialEntries={[`${RECORD}${search}`]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <CaptureIntake captureSummary={captureSummary} />
    </MemoryRouter>,
  );
}

const row = (route: string) =>
  document.querySelector<HTMLElement>(`.capture-method[data-route="${route}"]`)!;
const query = (href: string | null) => new URLSearchParams((href ?? '').split('?')[1] ?? '');

describe('Capture Home offers four ways in', () => {
  it('names all four, each with ONE action of its own', () => {
    renderHome();
    for (const [route, title] of [
      ['write', CAPTURE_COPY.intakeWriteTitle],
      ['voice', CAPTURE_COPY.intakeVoiceTitle],
      ['files', CAPTURE_COPY.intakeFilesTitle],
      ['runs', CAPTURE_COPY.intakeRunTitle],
    ] as const) {
      const el = row(route);
      expect(el, `no row for ${route}`).toBeTruthy();
      expect(within(el).getByRole('heading', { level: 3 }).textContent).toBe(title);
      expect(within(el).getAllByRole('link'), `${route} has more than one action`).toHaveLength(1);
      expect(within(el).queryAllByRole('button')).toHaveLength(0);
    }
  });

  it('each way in is a LINK to its focused view on this record, not a panel toggle', () => {
    renderHome();
    for (const method of ['write', 'voice', 'files'] as const) {
      const href = within(row(method)).getByRole('link').getAttribute('href');
      expect(href?.startsWith(RECORD), href ?? '').toBe(true);
      expect(query(href).get('view')).toBe('capture');
      expect(query(href).get('method')).toBe(method);
    }
    // The fourth is the Runs workspace itself, which needs no method.
    const runs = query(within(row('runs')).getByRole('link').getAttribute('href'));
    expect(runs.get('view')).toBe('runs');
    expect(runs.has('method')).toBe(false);
  });

  it('keeps the rest of the address, and drops a stale proposal focus on the way in', () => {
    renderHome(null, '?view=capture&run=RUNA&proposal=P1');
    const write = query(within(row('write')).getByRole('link').getAttribute('href'));
    expect(write.get('run')).toBe('RUNA');
    // `view=capture&proposal=` resolves to Proposals, so carrying it would
    // reopen Proposals instead of the task the reader chose.
    expect(write.has('proposal')).toBe(false);
  });

  it('MUTATION-GUARDED — the route that works in every deployment is the ONE primary action, and first', () => {
    renderHome();
    const primaries = Array.from(document.querySelectorAll('.btn-primary'));
    expect(primaries).toHaveLength(1);
    expect(row('write').contains(primaries[0]!)).toBe(true);
    const rows = Array.from(document.querySelectorAll('.capture-method'));
    expect(rows[0]!.getAttribute('data-route')).toBe('write');
  });
});

describe('the one-line summary of what the record holds', () => {
  it('states the server’s counts and links to the ONE review surface', () => {
    renderHome({ notes_total: 3, proposals_open: 2, unreadable_entries: 0 });
    const summary = document.querySelector('.capture-home-summary')!;
    expect(summary.textContent).toContain('3 notes · 2 to review');
    const review = within(summary as HTMLElement).getByRole('link');
    expect(review).toHaveAccessibleName(/^Review/);
    expect(query(review.getAttribute('href')).get('view')).toBe('proposals');
  });

  it('says NOTHING while the counts are unknown — never "0"', () => {
    renderHome(null);
    expect(document.querySelector('.capture-home-summary')).toBeNull();
  });

  it('offers no Review link when there is nothing to review', () => {
    renderHome({ notes_total: 0, proposals_open: 0, unreadable_entries: 0 });
    const summary = document.querySelector('.capture-home-summary')!;
    expect(summary.textContent).toContain(CAPTURE_COPY.homeSummaryLabel);
    expect(within(summary as HTMLElement).queryByRole('link')).toBeNull();
  });
});

describe('what Capture Home must NOT claim', () => {
  const CLAIMS = [
    /transcri\w* (?:is|are) (?:on|enabled|available|ready|configured)/i,
    /we (?:will )?transcribe/i,
    /automatically transcrib/i,
    /speech-to-text (?:is|will be) (?:on|enabled|available|ready)/i,
    /(?:model|provider) (?:is )?connected/i,
    /turns? your (?:voice|speech|audio) into text/i,
    /\bconnected\b/i,
  ];

  it('MUTATION-GUARDED — never says transcription, speech-to-text or a connection is available', () => {
    renderHome({ notes_total: 1, proposals_open: 1, unreadable_entries: 0 });
    const text = document.querySelector('.capture-intake')!.textContent ?? '';
    for (const claim of CLAIMS) {
      expect(text, `Capture Home claims: ${claim}`).not.toMatch(claim);
    }
    // ...and the honest alternative is STATED, so the ban cannot be satisfied by
    // deleting the voice line: recording here means typing what was said.
    expect(text).toContain(CAPTURE_COPY.homeVoiceLine);
    expect(text.toLowerCase()).toContain('type what was said');
  });

  it('POSITIVE CONTROL — those patterns catch the claims they forbid', () => {
    const MUST_CATCH = [
      'Transcription is available',
      'we transcribe it for you',
      'automatically transcribed',
      'Speech-to-text is ready',
      'provider connected',
      'turns your voice into text',
      'Your Claude app is connected',
    ];
    MUST_CATCH.forEach((phrasing, i) => {
      expect(CLAIMS[i]!.test(phrasing), `${CLAIMS[i]} missed ${JSON.stringify(phrasing)}`).toBe(
        true,
      );
    });
    // ...and none of the shipped voice copy trips them.
    for (const claim of CLAIMS) {
      expect(claim.test(CAPTURE_COPY.homeVoiceLine)).toBe(false);
      expect(claim.test(CAPTURE_COPY.voiceLead)).toBe(false);
    }
  });

  it('MUTATION-GUARDED — the files route never says files are uploaded or read', () => {
    renderHome();
    const text = (row('files').textContent ?? '').toLowerCase();
    for (const banned of ['upload', 'we read your files', 'we open', 'attach']) {
      expect(text, `the files row claims: ${banned}`).not.toContain(banned);
    }
    expect(text).toContain('reference');
  });

  it('is not a workflow step: no tick, no lock, no aria-current="step", no disabled control', () => {
    const { container } = renderHome({ notes_total: 0, proposals_open: 0, unreadable_entries: 0 });
    expect(container.querySelector('[aria-current="step"]')).toBeNull();
    expect(container.querySelector('[aria-disabled="true"]')).toBeNull();
    expect(container.querySelectorAll('button:disabled')).toHaveLength(0);
  });
});

/* ── review #277, I-4: Claude dictation is offered only where it exists ────────── */

describe('the voice row states what is true on THIS deployment', () => {
  beforeEach(() => __resetHealthCache());
  afterEach(() => vi.unstubAllGlobals());

  function renderWith(posture: string, endpoint: string | null) {
    stubFetchRoutes({ 'GET /api/health': { body: { ...healthSynthetic, mcp: { posture } } } });
    return render(
      <MemoryRouter
        initialEntries={[`${RECORD}?view=capture`]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <CaptureIntake captureSummary={null} claudeEndpoint={endpoint} />
      </MemoryRouter>,
    );
  }
  const voiceLine = () => row('voice').querySelector('.capture-method-line')?.textContent ?? '';

  it('an unmounted agent interface: the line offers NO Claude dictation', async () => {
    renderWith('unmounted', 'https://example.invalid/mcp');
    // Wait for the health read to settle, then assert the settled copy.
    await waitFor(() => expect(voiceLine()).toBe(CAPTURE_COPY.homeVoiceLine));
    expect(voiceLine()).not.toMatch(/claude|dictate/i);
  });

  it('a reachable posture WITHOUT a published address still offers none', async () => {
    renderWith('oauth-mounted', null);
    await waitFor(() => expect(voiceLine()).toBe(CAPTURE_COPY.homeVoiceLine));
  });

  it('POLARITY: only a reachable posture WITH an address offers Claude dictation', async () => {
    renderWith('oauth-mounted', 'https://example.invalid/mcp');
    await waitFor(() => expect(voiceLine()).toBe(CAPTURE_COPY.homeVoiceLineWithClaude));
  });

  it('the unmounted sentence makes no future promise', () => {
    expect(CAPTURE_COPY.claudeUnmounted).not.toMatch(/\byet\b/i);
  });
});
