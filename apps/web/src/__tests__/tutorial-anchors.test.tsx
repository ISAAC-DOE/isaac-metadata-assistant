/*
 * R0 · every walkthrough step points at a control that really exists.
 *
 * This is the file that makes the walkthrough a product rather than a slideshow,
 * and it attacks the question from three directions, because any one of them
 * alone can pass while the walkthrough is broken:
 *
 *  1. STATIC — every token in `TUTORIAL_ANCHORS` is really rendered somewhere in
 *     `apps/web/src` as `data-tutorial-anchor={TUTORIAL_ANCHORS.<key>}`. This is
 *     what catches a step added with an anchor nobody wired up. It is proven
 *     falsifiable by a NEGATIVE CONTROL: an invented token must fail the same
 *     check. Without that control the scan could be silently vacuous.
 *
 *  2. RUNTIME — each anchor is found in the DOM on the surface its step routes
 *     to, with the app's own fixtures. A token can be present in the source and
 *     still never render (behind a condition that is never true), which the
 *     static scan cannot see.
 *
 *  3. THE FAILURE PATH — a step whose control is genuinely absent must SAY SO to
 *     the reader. A walkthrough that silently skips is indistinguishable from one
 *     that is broken, so "the mark degrades to an explanation" is asserted
 *     directly, on the real component, with a real absent anchor.
 */

import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { GuidedTutorial } from '../components/GuidedTutorial';
import { startTutorial } from '../lib/tutorialController';
import {
  TUTORIAL_ANCHORS,
  TUTORIAL_STEPS,
  tutorialAnchorSelector,
} from '../lib/tutorialSteps';
import {
  CANONICAL_RESET_IDS,
  aboutResponse,
  bundleRoutes,
  canonicalFiveSummaries,
  exportReadyRoutes,
  graphStatusUnavailable,
  healthSynthetic,
  openApiFixture,
  stubFetchRoutes,
} from '../test/apiFixtures';

afterEach(() => vi.unstubAllGlobals());

// --- 1. the static scan -------------------------------------------------------

/** Locate `apps/web/src`. Deliberately not `import.meta.url`: under jsdom that is
 *  an http URL, not a file one — the same reasoning the sibling source-scanning
 *  guards give, and duplicated rather than shared for the same reason. */
function locateSrcDir(): string {
  const candidates = [join(process.cwd(), 'src'), join(process.cwd(), 'apps', 'web', 'src')];
  const found = candidates.find((dir) => existsSync(join(dir, 'main.tsx')));
  if (found === undefined) throw new Error(`cannot locate apps/web/src from ${process.cwd()}`);
  return found;
}

const SRC_DIR = locateSrcDir();

function sourceFiles(dir: string = SRC_DIR): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name !== '__tests__' && entry.name !== 'test') found.push(...sourceFiles(full));
    } else if (/\.tsx?$/.test(entry.name) && !entry.name.endsWith('.d.ts')) {
      found.push(relative(SRC_DIR, full).split(sep).join('/'));
    }
  }
  return found.sort();
}

/**
 * Every `data-tutorial-anchor={TUTORIAL_ANCHORS.<key>}` in the app sources, as
 * the set of KEYS used. Matching on the constant reference rather than on a
 * string literal is what makes a typo impossible to hide: a literal would have to
 * be compared by value, and a mistyped literal looks exactly like a correct one.
 */
function anchorKeysWiredInSources(): Set<string> {
  const used = new Set<string>();
  const pattern = /data-tutorial-anchor=\{TUTORIAL_ANCHORS\.(\w+)\}/g;
  for (const path of sourceFiles()) {
    const source = readFileSync(join(SRC_DIR, path), 'utf8');
    for (const match of source.matchAll(pattern)) used.add(match[1]);
  }
  return used;
}

describe('R0 · anchors — the static scan', () => {
  const wired = anchorKeysWiredInSources();

  it('finds real wiring at all (the scan is not vacuous)', () => {
    expect(wired.size).toBeGreaterThan(10);
  });

  it.each(Object.keys(TUTORIAL_ANCHORS))(
    'TUTORIAL_ANCHORS.%s is rendered by at least one component',
    (key) => {
      expect(wired.has(key), `nothing renders data-tutorial-anchor={TUTORIAL_ANCHORS.${key}}`).toBe(
        true,
      );
    },
  );

  it('every step in the catalog uses a token from the registry', () => {
    const tokens = new Set<string>(Object.values(TUTORIAL_ANCHORS));
    for (const step of TUTORIAL_STEPS) {
      expect(tokens.has(step.anchor), `${step.id} uses an unregistered anchor`).toBe(true);
    }
  });

  it('every registry token is used by exactly one step (no dead tokens, no duplicates)', () => {
    const byToken = new Map<string, string[]>();
    for (const step of TUTORIAL_STEPS) {
      byToken.set(step.anchor, [...(byToken.get(step.anchor) ?? []), step.id]);
    }
    for (const token of Object.values(TUTORIAL_ANCHORS)) {
      expect(byToken.get(token), `${token} is registered but no step uses it`).toBeDefined();
      expect(byToken.get(token), `${token} is used by more than one step`).toHaveLength(1);
    }
  });

  /*
   * THE NEGATIVE CONTROL. Everything above would also pass if the scan matched
   * nothing and the registry were empty, or if the `wired` set were accidentally
   * populated with every identifier in the repository. This proves the check can
   * FAIL: a plausible-looking token that nothing renders is not in the set.
   */
  it('an anchor nothing renders is NOT reported as wired', () => {
    expect(anchorKeysWiredInSources().has('aTokenNothingRenders')).toBe(false);
    // ...and the corresponding selector really finds nothing in a rendered app.
    expect(document.querySelector(tutorialAnchorSelector('a-token-nothing-renders'))).toBeNull();
  });
});

// --- 2. the runtime scan ------------------------------------------------------

const PENDING_ID = CANONICAL_RESET_IDS[0]; // 5 unanswered fields, not exported
const READY_ID = CANONICAL_RESET_IDS[2]; // 0 unanswered fields, not exported

/** The whole app's read surface for a walkthrough run. Deliberately contains NO
 *  destructive route: `stubFetchRoutes` rejects an unknown route, so a write
 *  attempted anywhere in these tests fails loudly rather than being tolerated. */
function readOnlyRoutes(): Record<string, unknown> {
  return {
    ...bundleRoutes(PENDING_ID),
    ...exportReadyRoutes(READY_ID),
    'GET /api/health': { body: healthSynthetic },
    'GET /api/experiments': { body: { experiments: canonicalFiveSummaries } },
    'GET /api/graph/status': { body: graphStatusUnavailable },
    'GET /api/about': { body: aboutResponse },
    'GET /api/openapi': { body: openApiFixture },
  };
}

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

/** The anchors each surface is responsible for, and the settled text that proves
 *  the surface finished loading before the DOM is inspected. */
const SURFACES: [string, string, string | null, readonly string[]][] = [
  [
    'My Experiments',
    '/experiments',
    null,
    [TUTORIAL_ANCHORS.experimentsQueue, TUTORIAL_ANCHORS.experimentRow],
  ],
  [
    'Review Record (unanswered fields)',
    `/record/${PENDING_ID}`,
    '5 Fields Need Your Confirmation',
    [
      TUTORIAL_ANCHORS.recordWorkflow,
      TUTORIAL_ANCHORS.recordSignals,
      TUTORIAL_ANCHORS.recordPending,
      TUTORIAL_ANCHORS.recordEvidenceTrail,
    ],
  ],
  [
    'Complete Missing Fields',
    `/record/${PENDING_ID}/complete`,
    'Answer 5 Questions to Finish This Record',
    [
      TUTORIAL_ANCHORS.completionQuestion,
      TUTORIAL_ANCHORS.completionConfirm,
      TUTORIAL_ANCHORS.completionDontKnow,
    ],
  ],
  [
    'Ready to Export (export still gated)',
    `/record/${PENDING_ID}/export`,
    '5 fields still block export',
    [
      TUTORIAL_ANCHORS.exportGate,
      TUTORIAL_ANCHORS.exportRepair,
      TUTORIAL_ANCHORS.exportValidation,
    ],
  ],
  [
    'Ready to Export (export open)',
    `/record/${READY_ID}/export`,
    'dry-run · would validate',
    [TUTORIAL_ANCHORS.exportAction],
  ],
  [
    'Governance & Safety → Validator',
    '/governance?tab=validator',
    null,
    [TUTORIAL_ANCHORS.standaloneValidator],
  ],
  ['Settings & API', '/settings', null, [TUTORIAL_ANCHORS.settingsSections]],
  [
    'Settings & API → Help & Tutorial',
    '/settings?tab=help',
    null,
    [TUTORIAL_ANCHORS.tutorialReplay],
  ],
];

describe('R0 · anchors — every step finds its control on the real surface', () => {
  it.each(SURFACES)('%s renders its anchors', async (_name, path, settledText, anchors) => {
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt(path);
    if (settledText !== null) await screen.findByText(settledText);
    for (const anchor of anchors) {
      await waitFor(() =>
        expect(
          document.querySelector(tutorialAnchorSelector(anchor)),
          `${anchor} is missing from ${path}`,
        ).not.toBeNull(),
      );
    }
  });

  it('the surface list covers every step in the catalog', () => {
    // If a step is added without being added here, the runtime scan would go
    // quietly incomplete while still passing.
    const covered = new Set(SURFACES.flatMap(([, , , anchors]) => anchors));
    for (const step of TUTORIAL_STEPS) {
      expect(covered.has(step.anchor), `${step.id}'s anchor is not runtime-checked`).toBe(true);
    }
  });
});

// --- 3. the failure path ------------------------------------------------------

describe('R0 · anchors — a control that is not there is REPORTED, not swallowed', () => {
  /*
   * The overlay is mounted with NO app around it, so step one's control
   * (`experiments-queue`) genuinely does not exist. That is the exact shape of the
   * regression this must catch: a step pointing at something that is not on the
   * page.
   *
   * `anchorTimeoutMs` is shortened so the give-up path is observable without a
   * real wait. It is a prop with a generous production default precisely because
   * a step navigates to another surface first and that surface has its own fetch
   * to finish — a short production timeout would report a slow screen as a missing
   * control.
   */
  function renderOverlayAlone() {
    return render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <GuidedTutorial anchorTimeoutMs={20} />
      </MemoryRouter>,
    );
  }

  it('tells the reader the control is not there, and says nothing was changed', async () => {
    stubFetchRoutes({ 'GET /api/experiments': { body: { experiments: canonicalFiveSummaries } } });
    renderOverlayAlone();
    startTutorial(null);

    const mark = await waitFor(() => {
      const found = document.querySelector('.tutorial-mark');
      expect(found).not.toBeNull();
      return found as HTMLElement;
    });
    // The step is still identified and still readable — it degrades, it does not
    // vanish and it does not become a blank bubble.
    expect(mark.getAttribute('data-tutorial-step')).toBe(TUTORIAL_STEPS[0].id);
    expect(mark.getAttribute('data-tutorial-step-available')).toBe('false');
    expect(mark.textContent).toContain(TUTORIAL_STEPS[0].title);
    expect(mark.textContent).toContain('Not shown on this visit');
    expect(mark.textContent).toMatch(/Nothing was changed/i);
    // No ring is drawn, because there is nothing to draw one around.
    expect(document.querySelector('.tutorial-ring')).toBeNull();
  });

  it('the SAME step reports itself AVAILABLE when its control is present', async () => {
    // The contrast is the point: if the "available" flag were hardcoded either
    // way, one of these two tests would fail.
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt('/experiments');
    startTutorial(null);

    await waitFor(() => {
      const mark = document.querySelector('.tutorial-mark');
      expect(mark).not.toBeNull();
      expect(mark!.getAttribute('data-tutorial-step-available')).toBe('true');
    });
    // ...and the highlight landed on the REAL control, not on a stand-in.
    const highlighted = document.querySelectorAll('[data-tutorial-highlight="true"]');
    expect(highlighted).toHaveLength(1);
    expect(highlighted[0]).toBe(document.querySelector('.queue'));
  });
});
