import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { act, fireEvent, render, waitFor } from '@testing-library/react';
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

// P27.5 — the mode chip is driven by the backend health.mode (via the shared,
// cached useHealth) rather than a hardcoded label. Because this app is
// synthetic-only by hard invariant, a missing/failed health check must degrade to
// the SAME indicator — never vanish, and never read as something else.
//
// D3 made the chip SCOPE-AWARE, which is the correction this file now pins on both
// sides. "Example workspace" was rendered on every ordinary screen, naming the ordinary
// workspace after content this build never puts there — the five built-in examples are
// created only inside a worked-example session. So the ordinary label is the neutral
// `Workspace`, the in-session label is `Worked Example`, and an anomalous `health.mode`
// still outranks both. The `mode` value on the wire is untouched.
//
// Note the wording of that: "never puts there", not "does not contain". This file has
// twice pinned a claim about a directory's CONTENTS that nothing in the app measures —
// see the long note in the scope-parity block below, which is where the distinction is
// argued and where a future edit should read before changing a string.

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

describe('mode chip — health-driven', () => {
  it('renders the ordinary workspace label from health.mode "synthetic-only" (queries the health endpoint)', async () => {
    const calls = stubFetchRoutes({ 'GET /api/health': { body: healthSynthetic } });
    const { container } = renderTopBar();

    // the chip drives itself from the health endpoint, not a hardcoded label
    await waitFor(() => expect(calls).toContain('GET /api/health'));
    const chip = container.querySelector('.mode-chip')!;
    expect(chip).not.toBeNull();
    expect(chip.textContent).toContain(LABELS.modeOrdinaryWorkspace);
    // The retired label must not come back here: it named this scope after contents
    // nothing in this app measures.
    expect(chip.textContent).not.toContain('Example workspace');
  });

  it('surfaces an UNEXPECTED backend mode truthfully — a distinct label, never masked as the expected one', async () => {
    // healthNonSynthetic.mode is 'production'. This app is synthetic-only by hard
    // invariant, so an anomalous reported mode must be shown, not hidden. This
    // test is falsifiable: it fails if health.mode stops driving the label.
    const calls = stubFetchRoutes({ 'GET /api/health': { body: healthNonSynthetic } });
    const { container } = renderTopBar();

    await waitFor(() => expect(calls).toContain('GET /api/health'));
    await waitFor(() => {
      const chip = container.querySelector('.mode-chip')!;
      expect(chip.textContent).toContain('Production'); // capitalized raw mode
      expect(chip.textContent).not.toContain('Example workspace');
      expect(chip.textContent).not.toContain('Synthetic');
      // and the scope name has not displaced the anomaly
      expect(chip.textContent).not.toContain(LABELS.modeOrdinaryWorkspace);
    });
  });

  it('still shows the workspace indicator when the health check fails (degrades gracefully)', async () => {
    stubFetchDown();
    const { container } = renderTopBar();

    // a failed health check must NOT hide the chip or read as something else
    await waitFor(() => {
      const chip = container.querySelector('.mode-chip');
      expect(chip).not.toBeNull();
      expect(chip!.textContent).toContain(LABELS.modeOrdinaryWorkspace);
    });
  });
});

/*
 * D3 · SCOPE PARITY — the chip's visible text AND its accessible name, in BOTH
 * scopes, with no false claim in either.
 *
 * This is the test the D3 decision asks for by name, and it exists because the chip is
 * the one control on every screen that carries this deployment's governance claims. The
 * failure mode it guards is specific and has happened: a label is simplified, and a
 * true claim leaves with the words. So each scope is asserted on four axes — what the
 * label says, what it must NOT say, which claims the accessible name carries, and which
 * claims it must NOT carry.
 *
 * The two claims that hold unconditionally — file upload is refused, no official
 * institutional record is shown — are required in BOTH branches. The scope-specific
 * clause is required in one and forbidden in the other, which is the part a single-scope
 * test cannot check.
 */
describe('mode chip — scope parity (visible text and accessible name)', () => {
  async function chipIn(scope: 'ordinary' | 'session') {
    stubFetchRoutes({
      ...tutorialSessionRoutes(),
      'GET /api/health': { body: healthSynthetic },
      'GET /api/experiments': { body: { experiments: [] } },
    } as never);
    if (scope === 'session') {
      await startTutorial(null);
      expect(getTutorialState().sessionId).not.toBeNull();
    }
    const { container } = renderTopBar();
    return waitFor(() => {
      const chip = container.querySelector<HTMLElement>('.mode-chip')!;
      expect(chip).not.toBeNull();
      expect(chip.textContent).toBeTruthy();
      return chip;
    });
  }

  const ALWAYS: [string, RegExp][] = [
    ['file upload is refused', /file upload is refused/i],
    ['no official institutional record is shown', /no official institutional record is shown/i],
  ];

  it('ordinary scope: names the workspace, and claims only what this build enforces', async () => {
    const chip = await chipIn('ordinary');
    const name = chip.getAttribute('aria-label') ?? '';

    expect(chip.textContent).toBe(LABELS.modeOrdinaryWorkspace);
    expect(chip.textContent).not.toMatch(/example|worked/i);
    // WCAG 2.5.3 — the accessible name opens with the exact visible text.
    expect(name.startsWith(chip.textContent ?? '')).toBe(true);
    for (const [what, pattern] of ALWAYS) {
      expect(name, `the ordinary chip must still claim: ${what}`).toMatch(pattern);
    }
    /*
     * TWO RETIRED EMPTINESS CLAIMS, BOTH NOW FORBIDDEN, AND ONE ENFORCEMENT CLAIM
     * REQUIRED.
     *
     * `holds no records of its own` went first: the chip derived it from
     * `sessionId === null` alone — it reads no count and asks the backend nothing.
     *
     * `the built-in example records are not in this workspace` went second, and this
     * assertion previously REQUIRED it while a comment here called the reasoning proven.
     * It is a narrower emptiness claim, and narrower is not measured.
     * `list_experiments(None)` enumerates whatever is on disk and there is no startup
     * migration; a second independent review reproduced a workspace holding all five
     * canonical records in the ordinary scope, each classifying `canonical` and each
     * refused by `remove_experiment`. On such a deployment the chip denied, on every
     * screen, five rows My Experiments was listing beneath it.
     *
     * What is required now is a claim about what the BUILD DOES, which is checkable and
     * is checked: `_materialise_seed`, `reset_to_canonical_seed` and
     * `ensure_tutorial_seeded` refuse a `None` session id with `InvalidTutorialSession`
     * (`apps/api/tests/test_tutorial_scope.py::test_the_seeding_functions_refuse_an_unscoped_call`
     * asserts the refusal and that nothing was written).
     *
     * If a future slice wants to say a scope is empty, it must read the count. Do not
     * re-derive an absence claim from `sessionId` — that is the mistake, twice.
     */
    expect(name).toMatch(/nothing in this build adds a built-in example record to this workspace/i);
    expect(name).toMatch(/created only inside a guided-walkthrough session/i);
    expect(name).not.toMatch(/holds no records of its own/i);
    expect(name).not.toMatch(/the built-in example records are not in this workspace/i);
    // FORBIDDEN here: no built-in example is in this scope to be rebuilt from anything,
    // and no walkthrough whose end could discard one.
    expect(name).not.toMatch(/reference files committed to this build/i);
    expect(name).not.toMatch(/discarded when the walkthrough ends/i);
  });

  it('worked-example scope: names the example scope, and says what those records are', async () => {
    const chip = await chipIn('session');
    const name = chip.getAttribute('aria-label') ?? '';

    expect(chip.textContent).toBe(LABELS.modeWorkedExample);
    // The neutral ordinary label must not leak into a scope that DOES hold examples.
    expect(chip.textContent).not.toBe(LABELS.modeOrdinaryWorkspace);
    expect(name.startsWith(chip.textContent ?? '')).toBe(true);
    for (const [what, pattern] of ALWAYS) {
      expect(name, `the worked-example chip must still claim: ${what}`).toMatch(pattern);
    }
    expect(name).toMatch(/reference files committed to this build/i);
    expect(name).toMatch(/discarded when the walkthrough ends/i);
    expect(name).toMatch(/belong to this walkthrough only/i);
    // FORBIDDEN here: this scope's five examples ARE present, so it must carry neither
    // the ordinary scope's enforcement clause (which is about a different scope)...
    expect(name).not.toMatch(/nothing in this build adds a built-in example record/i);
    // ...nor either retired emptiness claim, neither of which anything ever measured.
    expect(name).not.toMatch(/the built-in example records are not in this workspace/i);
    expect(name).not.toMatch(/holds no records of its own/i);
  });

  it('neither scope renders the retired "Example workspace" label', async () => {
    for (const scope of ['ordinary', 'session'] as const) {
      __resetHealthCache();
      __resetTutorialStore();
      sessionStorage.clear();
      const chip = await chipIn(scope);
      expect(chip.textContent, `scope ${scope}`).not.toContain('Example workspace');
      vi.unstubAllGlobals();
    }
  });
});

/* ── QA-023 · the chip's accessible name must be PERMITTED, not merely present ─ */

describe('QA-023 · the governance disclosure sits on a role that may carry a name', () => {
  /*
   * THE DEFECT THIS PINS. The chip carried its ~90-word governance disclosure in
   * `aria-label` on a BARE `<span>` — `role=generic`, where ARIA prohibits naming.
   * Measured with axe 4.12.1 on the exact shipped markup: `violations=0`,
   * `incomplete=[aria-prohibited-attr, ...]`. It was invisible to this repo's own
   * a11y suite because `e2e/helpers/axe.ts` reads only `results.violations` and
   * never `results.incomplete` — see `QA-023` in the ledger.
   *
   * WHAT IS ASSERTED is the property, not the literal role: an element carrying an
   * `aria-label` must have an explicit `role`, because that is what makes the name
   * permitted. A future slice may pick a different naming-capable role; it may not
   * go back to none.
   */
  it('MUTATION-GUARDED — the chip has an explicit role, so its aria-label is not prohibited', async () => {
    stubFetchRoutes({ 'GET /api/health': { body: healthSynthetic } });
    const { container } = renderTopBar();
    await waitFor(() => expect(container.querySelector('.mode-chip')).not.toBeNull());
    const chip = container.querySelector<HTMLElement>('.mode-chip')!;

    expect(chip.getAttribute('aria-label'), 'the disclosure is gone entirely').toBeTruthy();
    const role = chip.getAttribute('role');
    expect(
      role,
      'the chip carries an aria-label with NO role. A bare span is role=generic and ARIA ' +
        'prohibits naming it, so the governance disclosure is on an attribute that may be ' +
        'ignored. Give it a naming-capable role (`note` is what shipped).',
    ).toBeTruthy();

    // ...and NOT a live region, which is the tempting wrong answer: the chip is
    // driven by polled /api/health, so `status`/`alert` would re-announce ninety
    // words of governance prose on every poll that changed a value.
    expect(
      ['status', 'alert', 'log', 'marquee', 'timer'],
      `role="${role}" is a live region; the chip updates from a health poll`,
    ).not.toContain(role);
  });

  it('the visible text stays readable — the role does not suppress it', async () => {
    // `role="img"` would have cleared the prohibition too, and would have hidden
    // the one word a sighted reader actually sees. Asserted so that fix is not
    // "simplified" into this one.
    stubFetchRoutes({ 'GET /api/health': { body: healthSynthetic } });
    const { container } = renderTopBar();
    await waitFor(() => expect(container.querySelector('.mode-chip')).not.toBeNull());
    const chip = container.querySelector<HTMLElement>('.mode-chip')!;
    expect(chip.getAttribute('role')).not.toBe('img');
    expect((chip.textContent ?? '').trim().length).toBeGreaterThan(0);
  });
});

/*
 * B-22 — THE CHIP'S CLAIMS WERE REACHABLE ONLY BY A SCREEN READER'S BROWSE CURSOR.
 *
 * The mode chip carries ~90 words of governance disclosure (file upload is refused, no
 * official institutional record is shown, the test-database diagnostic) — and it was a
 * non-focusable `<span>` whose only carrier was its `aria-label`. A sighted keyboard user,
 * or anyone with a pointer, could never read what it claimed; it was not in the tab order
 * and showed nothing on hover.
 *
 * The chip stays the same `span.mode-chip role="note"` with the same `aria-label` (so every
 * assertion above and every browser locator is untouched), and gains: a place in the tab
 * order, and a visible popover — on focus AND on hover — carrying EXACTLY the claims the
 * accessible name carries. The popover is `aria-hidden`, because the name already speaks
 * them: a second, announced copy would read ninety words twice.
 */
describe('B-22 · the claims are reachable by keyboard and by pointer', () => {
  async function chip(): Promise<{ chip: HTMLElement; container: HTMLElement }> {
    stubFetchRoutes({ 'GET /api/health': { body: healthSynthetic } });
    const { container } = renderTopBar();
    await waitFor(() => expect(container.querySelector('.mode-chip')).not.toBeNull());
    return { chip: container.querySelector<HTMLElement>('.mode-chip')!, container };
  }

  /** The claims, as the accessible name carries them: everything after the visible word. */
  const claimsOf = (el: HTMLElement) =>
    (el.getAttribute('aria-label') ?? '').slice((el.textContent ?? '').length + ' — '.length);

  it('is in the tab order', async () => {
    const { chip: el } = await chip();
    expect(el.tabIndex).toBe(0);
    el.focus();
    expect(document.activeElement).toBe(el);
  });

  it('shows nothing until it is focused or hovered (the default state is unchanged)', async () => {
    const { container } = await chip();
    expect(container.querySelector('.mode-chip-popover')).toBeNull();
  });

  it('focus shows the claims, verbatim; blur hides them', async () => {
    const { chip: el, container } = await chip();
    fireEvent.focus(el);
    const pop = container.querySelector<HTMLElement>('.mode-chip-popover');
    expect(pop).not.toBeNull();
    expect(pop!.textContent).toBe(claimsOf(el));
    expect(pop!.textContent).toMatch(/file upload is refused/i);
    fireEvent.blur(el);
    expect(container.querySelector('.mode-chip-popover')).toBeNull();
  });

  it('hover shows the claims too, and leaving hides them', async () => {
    const { chip: el, container } = await chip();
    const wrap = el.closest('.mode-chip-wrap')!;
    fireEvent.mouseEnter(wrap);
    expect(container.querySelector('.mode-chip-popover')?.textContent).toBe(claimsOf(el));
    fireEvent.mouseLeave(wrap);
    expect(container.querySelector('.mode-chip-popover')).toBeNull();
  });

  it('Escape dismisses it without moving focus (WCAG 1.4.13)', async () => {
    const { chip: el, container } = await chip();
    el.focus();
    fireEvent.focus(el);
    expect(container.querySelector('.mode-chip-popover')).not.toBeNull();
    act(() => {
      fireEvent.keyDown(document, { key: 'Escape' });
    });
    expect(container.querySelector('.mode-chip-popover')).toBeNull();
    expect(document.activeElement).toBe(el);
  });

  it('the popover is hidden from assistive technology, so the claims are announced once', async () => {
    const { chip: el, container } = await chip();
    fireEvent.focus(el);
    expect(container.querySelector('.mode-chip-popover')!.getAttribute('aria-hidden')).toBe('true');
    // and the accessible name that speaks them is exactly what it was
    expect(el.getAttribute('role')).toBe('note');
    expect(claimsOf(el).length).toBeGreaterThan(60);
  });

  it('is shifted back on screen when it would start off the left edge (measured at 375px: x = -30)', async () => {
    const { chip: el, container } = await chip();
    const real = HTMLElement.prototype.getBoundingClientRect;
    HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
      return this.classList.contains('mode-chip-popover')
        ? ({ left: -30, right: 310, top: 62, bottom: 150, width: 340, height: 88, x: -30, y: 62, toJSON() {} } as DOMRect)
        : real.call(this);
    };
    try {
      fireEvent.focus(el);
      const pop = container.querySelector<HTMLElement>('.mode-chip-popover')!;
      expect(pop.style.transform).toBe('translateX(38px)');
    } finally {
      HTMLElement.prototype.getBoundingClientRect = real;
    }
  });

  it('is left where it is when it already fits', async () => {
    const { chip: el, container } = await chip();
    const real = HTMLElement.prototype.getBoundingClientRect;
    HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
      return this.classList.contains('mode-chip-popover')
        ? ({ left: 863, right: 1203, top: 68, bottom: 156, width: 340, height: 88, x: 863, y: 68, toJSON() {} } as DOMRect)
        : real.call(this);
    };
    try {
      fireEvent.focus(el);
      expect(container.querySelector<HTMLElement>('.mode-chip-popover')!.style.transform).toBe('');
    } finally {
      HTMLElement.prototype.getBoundingClientRect = real;
    }
  });

  it('has a hover bridge across the gap between chip and popover (WCAG 1.4.13 hoverable)', () => {
    // jsdom lays nothing out, so the property is asserted on the rule: the popover sits at
    // `top: calc(100% + 6px)`, and a transparent child strip at least that tall closes the gap.
    const css = readFileSync(resolve(__dirname, '..', 'components/chrome.css'), 'utf8');
    const gap = Number(/\.mode-chip-popover\s*\{[^}]*top:\s*calc\(100%\s*\+\s*(\d+)px\)/.exec(css)?.[1]);
    const bridge = /\.mode-chip-popover::before\s*\{([^}]*)\}/.exec(css)?.[1] ?? '';
    expect(gap).toBeGreaterThan(0);
    expect(bridge).toMatch(/position:\s*absolute/);
    expect(Number(/height:\s*(\d+)px/.exec(bridge)?.[1])).toBeGreaterThanOrEqual(gap);
    expect(Number(/top:\s*-(\d+)px/.exec(bridge)?.[1])).toBeGreaterThanOrEqual(gap);
  });

  it('the chip element itself still reads just the visible word (browser locators keep working)', async () => {
    const { chip: el } = await chip();
    fireEvent.focus(el);
    expect(el.textContent).toBe(LABELS.modeOrdinaryWorkspace);
    expect(el.tagName).toBe('SPAN');
  });
});
