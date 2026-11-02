import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { StatusBar } from '../components/StatusBar';
import { LeftNav } from '../components/LeftNav';

/*
 * The hosted-environment TRUTHFULNESS guard.
 *
 * Hosted QA found the always-visible chrome asserting local-development facts on
 * the SLAC-hosted deployment: the left-nav badge read `isaac v0.1.0 · local` and
 * the status-bar footer read `local · offline · no telemetry`. They were then
 * derived (`isaac v0.1.0 · local dev` / `hosted preview · no telemetry`).
 *
 * 2026-11-02 — BOTH BADGES RETIRED at the owner's direction (standing disclaimers
 * removed; the version is shown in Settings → This Build). A build with no
 * environment label in its chrome cannot be wrong about it, so this file now pins
 * "no false claim" instead of "the right label is present":
 *   · neither the hosted nor the local chrome renders an environment label, a
 *     telemetry claim or a local-development fact;
 *   · no frontend source carries either retired literal (negative-controlled below).
 *
 * It still pins the claims the frontend is NOT allowed to make at all: that it
 * verified the deployment's access edge, or that it classified data as synthetic
 * by looking at content. Neither is observable from the browser, and no
 * real-vs-synthetic detector exists anywhere in the backend
 * (`apps/api/isaac_api/runtime_mode.py` gates on an env var and nothing else).
 */

/**
 * Load the chrome as a HOSTED build. `isHostedBuild` is a comparison of two
 * compile-time literals that Vite folds at build time, so the only faithful way to
 * exercise the hosted branch is a fresh module registry with the env stubbed — the
 * same technique `backend-down-state.test.tsx` uses.
 */
async function loadHosted() {
  vi.resetModules();
  vi.stubEnv('VITE_API_BASE', '/krish/api');
  const [api, runtimeContext, statusBar, leftNav] = await Promise.all([
    import('../lib/api'),
    import('../lib/runtimeContext'),
    import('../components/StatusBar'),
    import('../components/LeftNav'),
  ]);
  return {
    isHostedBuild: api.isHostedBuild,
    ...runtimeContext,
    StatusBar: statusBar.StatusBar,
    LeftNav: leftNav.LeftNav,
  };
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

/**
 * Every way this app's own copy has said "you are running this on your own
 * machine". A hosted-rendered string matching any of these is the defect.
 * `offline` is included: it was in the old footer badge and is false of any
 * deployed page.
 */
const LOCAL_DEV_CLAIM =
  /\blocal\b|\blocally\b|localhost|127\.0\.0\.1|uvicorn|\boffline\b|your (own )?(machine|laptop|computer)/i;

/** Any environment label or telemetry claim in chrome — the retired badge class. */
const ENVIRONMENT_BADGE =
  /no telemetry|hosted preview|local dev|isaac v\d+\.\d+\.\d+\s*·|·\s*local\b/i;

const RETIRED_BADGES = [
  'isaac v0.1.0 · local',
  'local · offline · no telemetry',
  'isaac v0.1.0 · local dev',
  'local dev · no telemetry',
  'isaac v0.1.0 · hosted preview',
  'hosted preview · no telemetry',
];

function chromeText(StatusBarC: typeof StatusBar, LeftNavC: typeof LeftNav): string {
  const footer = render(<StatusBarC note="a note" />).getByRole('contentinfo');
  const nav = render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <LeftNavC active="experiments" />
    </MemoryRouter>,
  ).getByRole('navigation', { name: 'Primary' });
  return `${footer.textContent} ${nav.textContent}`;
}

describe('runtime environment — hosted build (VITE_API_BASE=/krish/api)', () => {
  it('is decided by the one existing mechanism, not a second one', async () => {
    const hosted = await loadHosted();
    expect(hosted.isHostedBuild).toBe(true);
    // Still used, by Copy Diagnostics only.
    expect(hosted.ENVIRONMENT_LABEL).toBe('hosted preview');
  });

  it('renders footer and nav with no local-development claim and no environment badge', async () => {
    const hosted = await loadHosted();
    const text = chromeText(hosted.StatusBar, hosted.LeftNav);
    expect(text).not.toMatch(LOCAL_DEV_CLAIM);
    expect(text).not.toMatch(ENVIRONMENT_BADGE);
  });
});

describe('runtime environment — local build (no VITE_API_BASE)', () => {
  it('renders footer and nav with no environment badge either', () => {
    expect(chromeText(StatusBar, LeftNav)).not.toMatch(ENVIRONMENT_BADGE);
  });
});

describe('runtime environment — the retired badges, proven against the ban (negative control)', () => {
  it.each(RETIRED_BADGES)('the ban rejects %s', (retired) => {
    expect(retired).toMatch(ENVIRONMENT_BADGE);
  });

  it('every retired HOSTED-false badge is also a local-development claim', () => {
    for (const retired of ['isaac v0.1.0 · local', 'local · offline · no telemetry']) {
      expect(retired).toMatch(LOCAL_DEV_CLAIM);
    }
  });
});

// --- claims the frontend may never make --------------------------------------

/** A claim that the frontend (or ISAAC) verified the access edge or a sign-in. */
const VERIFIED_EDGE =
  /(this app|the app|ISAAC|it)\s+(has\s+)?(verified|confirmed|checked)\s+(the\s+|your\s+)?(sign-?in|edge|access|identity)|\bverified to sit behind\b/i;

/*
 * ~~The Settings Authentication Boundary and synthetic-only concept cards~~ — retired
 * 2026-11-02 with the Privacy & Governance tab. Their bans now run over EVERY frontend
 * source below (`never claims the edge was verified`, alongside the content-
 * classification scan), so a sentence like theirs cannot come back anywhere.
 */
describe('the verified-edge ban is proven on the claims it exists to stop', () => {
  it.each([
    'This app verified the sign-in edge.',
    'ISAAC confirmed your sign-in.',
    'The deployment is verified to sit behind single sign-on.',
  ])('fires on %s', (claim) => {
    expect(claim).toMatch(VERIFIED_EDGE);
  });
});

// --- the same claim class, across EVERY frontend source file -----------------

/*
 * WHY THIS EXISTS. An earlier assertion scanned `settingsConcepts` ONLY, so it
 * passed while `screens/LoadMaterials.tsx` shipped "A file that looks real or
 * private is intercepted and routed to governance" and `screens/GovernancePage.tsx`
 * shipped "a real-looking file is intercepted here" — the identical false claim,
 * in screen copy the Settings-scoped guard could never see.
 *
 * WHAT THE CODE ACTUALLY DOES. `POST /api/uploads`
 * (`apps/api/isaac_api/routes.py`) refuses EVERY request with 403: it declares
 * and parses no multipart form and reads, inspects and stores no file.
 * `runtime_mode.py` gates on an environment variable. There is no real-vs-
 * synthetic content detector anywhere in this repository — the app enforces a
 * synthetic MODE, not synthetic CONTENT.
 *
 * SO THIS GUARD SCANS SOURCE, not a hand-listed copy of the strings: every
 * `.ts`/`.tsx` file under `apps/web/src` except tests and fixtures, which means
 * a NEW screen is covered the day it is written. Comments are stripped first, so
 * a note explaining a past defect (like this one) is not mistaken for the defect.
 */

/**
 * Locate `apps/web/src` on disk. Deliberately NOT `import.meta.url`: under the
 * jsdom environment that is an http URL, not a file one. The anchor file is
 * asserted to exist, so a wrong working directory fails loudly instead of
 * scanning an empty set.
 */
function locateSrcDir(): string {
  const candidates = [join(process.cwd(), 'src'), join(process.cwd(), 'apps', 'web', 'src')];
  const found = candidates.find((dir) => existsSync(join(dir, 'main.tsx')));
  if (found === undefined) {
    throw new Error(`cannot locate apps/web/src from ${process.cwd()}`);
  }
  return found;
}

const SRC_DIR = locateSrcDir();
/** Tests and fixtures are copy ABOUT the app, not copy the app renders. */
const NOT_USER_FACING = new Set(['__tests__', 'test']);

function frontendSourceFiles(dir: string = SRC_DIR): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!NOT_USER_FACING.has(entry.name)) found.push(...frontendSourceFiles(full));
    } else if (/\.tsx?$/.test(entry.name) && !entry.name.endsWith('.d.ts')) {
      found.push(relative(SRC_DIR, full).split(sep).join('/'));
    }
  }
  return found.sort();
}

/** Strip comments; keep string literals and JSX text, which is what a user reads.
 *  The `[^:'"\`]` guard keeps `https://…` inside a literal from being eaten. */
function renderedCopy(path: string): string {
  return readFileSync(join(SRC_DIR, path), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/(^|[^:'"`\\])\/\/[^\n]*/g, '$1');
}

/** Each entry is one way of claiming the app judged a file BY ITS CONTENT. */
const CONTENT_CLASSIFICATION_CLAIM: [string, RegExp][] = [
  ['a file "looks" real or private', /looks? real|looks? private|real-looking|looks like (a )?real/i],
  ['a file "appears" or "seems" real', /appears (to be )?real|seems (to be )?real/i],
  ['detecting real data', /detects? real|real-data detection|content-based (check|detection|classification)/i],
  ['classifying a file or upload', /classif\w+ (a |an |the |each |every |your )?(file|upload)/i],
  [
    'examining a file to judge it',
    /(inspects?|inspecting|examines?|examining|analy[sz]es?|analy[sz]ing|sniffs?) (a |an |the |each |every |your )?(files?|uploads?)\b/i,
  ],
];

describe('user-facing copy — no content-based real/synthetic classification, anywhere', () => {
  const files = frontendSourceFiles();

  it('scans the real string sources, not a duplicate of them', () => {
    // A guard that silently scanned nothing would "pass" forever.
    expect(files.length).toBeGreaterThan(40);
    for (const covered of [
      'screens/LoadMaterials.tsx',
      'screens/GovernancePage.tsx',
      'lib/settingsContent.ts',
      'components/AdvisoryChip.tsx',
    ]) {
      expect(files).toContain(covered);
    }
    // Tests are excluded — this very file names the retired strings on purpose.
    expect(files.some((f) => f.startsWith('__tests__/'))).toBe(false);
  });

  it('never claims the access edge or a sign-in was verified', () => {
    const offenders = files.filter((path) => VERIFIED_EDGE.test(renderedCopy(path)));
    expect(offenders).toEqual([]);
  });

  it('never names the retired "single sign-on" claim', () => {
    const offenders = files.filter((path) => /single sign-on/i.test(renderedCopy(path)));
    expect(offenders).toEqual([]);
  });

  it.each(CONTENT_CLASSIFICATION_CLAIM)('never claims %s', (_label, pattern) => {
    const offenders = files.filter((path) => pattern.test(renderedCopy(path)));
    expect(offenders).toEqual([]);
  });
});

describe('user-facing copy — no retired environment badge in any frontend source', () => {
  it.each(RETIRED_BADGES)('no source carries %s', (retired) => {
    const offenders = frontendSourceFiles().filter((path) => renderedCopy(path).includes(retired));
    expect(offenders).toEqual([]);
  });
});
