import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
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
