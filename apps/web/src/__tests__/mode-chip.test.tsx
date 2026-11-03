import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { TopBar } from '../components/TopBar';
import { LABELS } from '../lib/labels';
import { __resetHealthCache } from '../lib/useHealth';
import {
  __resetTutorialStore,
  getTutorialState,
  startTutorial,
} from '../lib/tutorialController';
import {
  healthNonSynthetic,
  healthSynthetic,
  stubFetchDown,
  stubFetchRoutes,
  tutorialSessionRoutes,
} from '../test/apiFixtures';

/*
 * THE MODE CHIP — WHEN IT RENDERS, AND WHAT IT MAY NEVER SAY.
 *
 * 2026-11-02, at the owner's direction (standing disclaimers retired): the chip renders
 * ONLY inside a worked-example session (`LABELS.modeWorkedExample`) or when
 * `health.mode` is anomalous. On the ordinary scope there is no chip. Its ~90-word
 * accessible-name disclosure (`file upload is refused`, `no official institutional
 * record is shown`, the scope clauses and the database diagnostic) and the B-22
 * hover/focus popover that showed it were removed with it.
 *
 * WHAT THIS FILE STILL PINS, as "no false claim" rather than "this sentence is present":
 *   · the anomaly outranks every scope label and is never masked (iii);
 *   · neither scope ever shows the retired "Example workspace" / "Synthetic" labels (i);
 *   · no retired claim — including the two emptiness claims that were false (ii) —
 *     comes back in the chip's text or any attribute;
 *   · if an `aria-label` is ever re-added, it opens with the visible text (WCAG 2.5.3)
 *     and sits on a role that may carry a name (QA-023);
 *   · a failed health check never invents a chip, and never reads as another mode.
 * The negative controls at the end run the bans against the exact retired strings.
 */

beforeEach(() => {
  __resetHealthCache(); // fresh module cache so each case proves a real fetch
});

afterEach(() => {
  vi.unstubAllGlobals();
  __resetTutorialStore();
  sessionStorage.clear();
});

function renderTopBar() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <TopBar variant="home" />
    </MemoryRouter>,
  );
}

/** Everything the chip says: text plus every attribute value, so a claim cannot hide in one. */
function chipSurface(chip: Element): string {
  const attrs = Array.from(chip.attributes).map((a) => a.value);
  return [chip.textContent ?? '', ...attrs].join(' ');
}

/** Claims the chip once carried and may not carry again — each retired, two of them false. */
const RETIRED_CHIP_CLAIMS: [string, RegExp][] = [
  ['the retired "Example workspace" label', /example workspace/i],
  ['the retired "Synthetic" label', /\bsynthetic\b/i],
  ['file upload is refused', /file upload is refused/i],
  ['no official institutional record is shown', /no official institutional record is shown/i],
  ['the retired emptiness claim (1)', /holds no records of its own/i],
  ['the retired emptiness claim (2)', /the built-in example records are not in this workspace/i],
  ['the retired ordinary-scope enforcement clause', /nothing in this build adds a built-in example record/i],
  ['the retired session clause', /reference files committed to this build/i],
  ['the retired diagnostic disclosure', /read-only diagnostic|test database|test DB/i],
];

describe('mode chip — health-driven', () => {
  it('renders NO chip on the ordinary scope when health.mode is "synthetic-only" (queries the health endpoint)', async () => {
    const calls = stubFetchRoutes({ 'GET /api/health': { body: healthSynthetic } });
    const { container } = renderTopBar();
    await waitFor(() => expect(calls).toContain('GET /api/health'));
    // Settle a tick after health resolves, so a chip rendered from the resolved state
    // cannot hide behind the loading state.
    await new Promise((r) => setTimeout(r, 0));
    expect(container.querySelector('.mode-chip')).toBeNull();
    expect(container.textContent).not.toMatch(/example workspace/i);
  });

  it('surfaces an UNEXPECTED backend mode truthfully — a distinct label, never masked', async () => {
    // healthNonSynthetic.mode is 'production'. An anomalous reported mode must be shown,
    // even on the ordinary scope where there is otherwise no chip. Falsifiable: it fails
    // if health.mode stops driving the chip.
    const calls = stubFetchRoutes({ 'GET /api/health': { body: healthNonSynthetic } });
    const { container } = renderTopBar();
    await waitFor(() => expect(calls).toContain('GET /api/health'));
    await waitFor(() => {
      const chip = container.querySelector('.mode-chip')!;
      expect(chip).not.toBeNull();
      expect(chip.textContent).toBe('Production'); // capitalized raw mode
      expect(chip.textContent).not.toContain('Example workspace');
      expect(chip.textContent).not.toContain('Synthetic');
    });
  });

  it('a failed health check invents no chip on the ordinary scope (and so implies no mode)', async () => {
    stubFetchDown();
    const { container } = renderTopBar();
    await new Promise((r) => setTimeout(r, 20));
    expect(container.querySelector('.mode-chip')).toBeNull();
  });
});

describe('mode chip — the worked-example scope', () => {
  async function inSession(health: 'ok' | 'down' | 'anomalous') {
    const healthRoute =
      health === 'ok'
        ? { 'GET /api/health': { body: healthSynthetic } }
        : health === 'anomalous'
          ? { 'GET /api/health': { body: healthNonSynthetic } }
          : { 'GET /api/health': { status: 503, body: {} } };
    stubFetchRoutes({
      ...tutorialSessionRoutes(),
      ...healthRoute,
      'GET /api/experiments': { body: { experiments: [] } },
    } as never);
    await startTutorial(null);
    expect(getTutorialState().sessionId).not.toBeNull();
    const { container } = renderTopBar();
    return waitFor(() => {
      const chip = container.querySelector<HTMLElement>('.mode-chip')!;
      expect(chip).not.toBeNull();
      expect(chip.textContent).toBeTruthy();
      return chip;
    });
  }

  it('names the session scope, and only that', async () => {
    const chip = await inSession('ok');
    expect(chip.textContent).toBe(LABELS.modeWorkedExample);
  });

  it('still names the session when health fails — the scope is known from the session, not from health', async () => {
    const chip = await inSession('down');
    expect(chip.textContent).toBe(LABELS.modeWorkedExample);
  });

  it('an anomalous mode outranks the session label (never masked by a scope name)', async () => {
    const chip = await inSession('anomalous');
    await waitFor(() => expect(chip.textContent).toBe('Production'));
    expect(chip.textContent).not.toContain(LABELS.modeWorkedExample);
  });

  it('carries no retired claim in its text or any attribute', async () => {
    const chip = await inSession('ok');
    const surface = chipSurface(chip);
    for (const [what, pattern] of RETIRED_CHIP_CLAIMS) {
      expect(surface, `the chip must not say ${what}`).not.toMatch(pattern);
    }
  });

  /*
   * QA-023 and WCAG 2.5.3, kept as CONDITIONAL guards. The chip has no `aria-label` now,
   * so its visible text is its whole name. If a later change re-adds one, it must open
   * with the visible text and sit on an explicit, non-live role (a bare span is
   * role=generic, which ARIA prohibits naming; a live role would re-announce on every
   * health poll).
   */
  it('if it ever carries an aria-label, that label opens with the visible text on a naming-capable, non-live role', async () => {
    const chip = await inSession('ok');
    const name = chip.getAttribute('aria-label');
    if (name === null) {
      expect(chip.getAttribute('role')).not.toBe('img');
      return;
    }
    expect(name.startsWith(chip.textContent ?? '')).toBe(true);
    const role = chip.getAttribute('role');
    expect(role).toBeTruthy();
    expect(['status', 'alert', 'log', 'marquee', 'timer', 'img']).not.toContain(role);
  });

  it('has no popover any more, and the chip is not a dead tab stop', async () => {
    const chip = await inSession('ok');
    expect(document.querySelector('.mode-chip-popover')).toBeNull();
    expect(chip.hasAttribute('tabindex')).toBe(false);
    expect(chip.tagName).toBe('SPAN');
  });
});

describe('mode chip — the bans are proven on the exact retired strings (negative controls)', () => {
  const RETIRED_ARIA_ORDINARY =
    'Workspace — nothing in this build adds a built-in example record to this workspace — they are ' +
    'created only inside a guided-walkthrough session; file upload is refused, and no official ' +
    'institutional record is shown.';
  const RETIRED_ARIA_SESSION =
    'Worked Example — the example records here belong to this walkthrough only, are rebuilt from ' +
    'reference files committed to this build, and are discarded when the walkthrough ends; file ' +
    'upload is refused, and no official institutional record is shown.';
  const RETIRED_DIAGNOSTIC =
    'This deployment is also configured to run a protected, read-only diagnostic against an ' +
    'isolated test database; it returns sanitized aggregate results only, and no database records are displayed.';

  /** Each ban, paired with the exact retired string it exists for — one per entry, so a
   *  single narrowed pattern cannot hide behind another that flags the same sentence. */
  const RETIRED_FOR: Record<string, string> = {
    'the retired "Example workspace" label': 'Example workspace',
    'the retired "Synthetic" label': 'Synthetic',
    'file upload is refused': RETIRED_ARIA_ORDINARY,
    'no official institutional record is shown': RETIRED_ARIA_SESSION,
    'the retired emptiness claim (1)': 'Workspace — this workspace holds no records of its own',
    'the retired emptiness claim (2)': 'Workspace — the built-in example records are not in this workspace',
    'the retired ordinary-scope enforcement clause': RETIRED_ARIA_ORDINARY,
    'the retired session clause': RETIRED_ARIA_SESSION,
    'the retired diagnostic disclosure': RETIRED_DIAGNOSTIC,
  };

  it('every ban has its own retired-string control', () => {
    expect(Object.keys(RETIRED_FOR).sort()).toEqual(RETIRED_CHIP_CLAIMS.map(([w]) => w).sort());
  });

  it.each(RETIRED_CHIP_CLAIMS)('the ban on %s fires on its own retired string', (what, pattern) => {
    expect(RETIRED_FOR[what]).toMatch(pattern);
  });

  it('leaves the current label alone, so the ban is not vacuous in the other direction', () => {
    expect(RETIRED_CHIP_CLAIMS.some(([, p]) => p.test(LABELS.modeWorkedExample))).toBe(false);
    expect(RETIRED_CHIP_CLAIMS.some(([, p]) => p.test('Production'))).toBe(false);
  });

  it('the popover CSS went with the popover', () => {
    const css = readFileSync(resolve(__dirname, '..', 'components/chrome.css'), 'utf8');
    expect(css).not.toMatch(/\.mode-chip-popover/);
  });
});
