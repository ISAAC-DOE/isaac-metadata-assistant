import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render } from '@testing-library/react';
import { StatusBar } from '../components/StatusBar';
import { LABELS } from '../lib/labels';
import { ENVIRONMENT_LABEL, RUNTIME_BADGE, VERSION_BADGE } from '../lib/runtimeContext';
import { settingsConcepts, settingsFactsFrom } from '../lib/settingsContent';

/*
 * The hosted-environment TRUTHFULNESS guard.
 *
 * Hosted QA found the always-visible chrome asserting local-development facts on
 * the SLAC-hosted deployment: the left-nav badge read `isaac v0.1.0 · local` and
 * the status-bar footer read `local · offline · no telemetry`. Both were
 * literals, so neither could ever have been right in both places.
 *
 * These tests pin BOTH halves of the rule, because the fix must not swap one
 * false confident string for another:
 *   · a HOSTED build must claim no local-development fact;
 *   · a LOCAL build must still say, truthfully, that it is local.
 *
 * They also pin the claims the frontend is NOT allowed to make at all: that it
 * verified the deployment's access edge, or that it classified data as synthetic
 * by looking at content. Neither is observable from the browser, and no
 * real-vs-synthetic detector exists anywhere in the backend
 * (`apps/api/isaac_api/runtime_mode.py` gates on an env var and nothing else).
 */

/**
 * Load the derived labels as a HOSTED build. `isHostedBuild` is a comparison of
 * two compile-time literals that Vite folds at build time, so the only faithful
 * way to exercise the hosted branch is a fresh module registry with the env
 * stubbed — the same technique `backend-down-state.test.tsx` uses.
 */
async function loadHosted() {
  vi.resetModules();
  vi.stubEnv('VITE_API_BASE', '/krish/api');
  const [api, runtimeContext, labels, statusBar] = await Promise.all([
    import('../lib/api'),
    import('../lib/runtimeContext'),
    import('../lib/labels'),
    import('../components/StatusBar'),
  ]);
  return {
    isHostedBuild: api.isHostedBuild,
    ...runtimeContext,
    LABELS: labels.LABELS,
    StatusBar: statusBar.StatusBar,
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

describe('runtime environment label — hosted build (VITE_API_BASE=/krish/api)', () => {
  it('is decided by the one existing mechanism, not a second one', async () => {
    const hosted = await loadHosted();
    expect(hosted.isHostedBuild).toBe(true);
    expect(hosted.ENVIRONMENT_LABEL).toBe('hosted preview');
  });

  it('names the version badge without any local-development claim', async () => {
    const hosted = await loadHosted();
    expect(hosted.LABELS.version).toBe('isaac v0.1.0 · hosted preview');
    expect(hosted.LABELS.version).not.toMatch(LOCAL_DEV_CLAIM);
    // The version itself is still stated — the fix removed a false claim, not a
    // useful one.
    expect(hosted.LABELS.version).toContain('isaac v0.1.0');
  });

  it('renders a status-bar footer with no local-development claim', async () => {
    const hosted = await loadHosted();
    expect(hosted.RUNTIME_BADGE).toBe('hosted preview · no telemetry');
    const view = render(<hosted.StatusBar note="a note" />);
    const footer = view.getByRole('contentinfo');
    expect(footer.textContent).toContain('hosted preview · no telemetry');
    expect(footer.textContent).not.toMatch(LOCAL_DEV_CLAIM);
  });

  it('names no deployment, host, cluster or identity product in the chrome', async () => {
    const hosted = await loadHosted();
    // `isHostedBuild` only reports "a non-default API base was compiled in". It
    // does not identify WHICH deployment, so the badges must not pretend to.
    for (const badge of [hosted.VERSION_BADGE, hosted.RUNTIME_BADGE]) {
      expect(badge).not.toMatch(/authentik|ingress|kubernetes|k8s|s3df|slac|krish/i);
    }
  });
});

describe('runtime environment label — local build (no VITE_API_BASE)', () => {
  it('still says, truthfully, that it is a local development build', () => {
    expect(ENVIRONMENT_LABEL).toBe('local dev');
    expect(VERSION_BADGE).toBe('isaac v0.1.0 · local dev');
    expect(RUNTIME_BADGE).toBe('local dev · no telemetry');
    expect(LABELS.version).toBe(VERSION_BADGE);
  });

  it('renders the local footer badge', () => {
    const view = render(<StatusBar note="a note" />);
    expect(view.getByRole('contentinfo').textContent).toContain('local dev · no telemetry');
  });

  it('drops `offline`, which was never true of a page talking to a backend', () => {
    expect(RUNTIME_BADGE).not.toMatch(/\boffline\b/);
  });
});

// --- claims the frontend may never make --------------------------------------

/** The concepts are pure functions of the `GET /api/about` facts, so the copy is
 *  asserted directly rather than through five tab renders (which
 *  `settings-page.test.tsx` already does for placement and duplication). */
const concepts = settingsConcepts(
  settingsFactsFrom({
    data_regime: 'synthetic-only',
    persistence: 'ephemeral',
    record_schema_version: '1.05',
  }),
);

const concept = (id: string) => {
  const found = concepts.find((c) => c.id === id);
  if (!found) throw new Error(`no such concept: ${id}`);
  return found;
};

describe('Settings copy — the authentication boundary keeps four things separate', () => {
  const auth = concept('authentication-boundary');
  const text = `${auth.summary} ${auth.detail} ${auth.more?.text ?? ''}`;

  it('never says there is no sign-in or no authentication', () => {
    // The old summary read "No sign-in and no accounts", which reads as "this
    // deployment is open". It is not: it is reached through an authenticating
    // edge. ISAAC having no ACCOUNT SYSTEM is a different fact.
    expect(text).not.toMatch(/no sign-?in/i);
    expect(text).not.toMatch(/no authentication/i);
    expect(text).not.toMatch(/\bunauthenticated\b/i);
  });

  it('states edge access as how the deployment is operated, never as verified', () => {
    /*
     * FINDING F — this used to assert `/single sign-on/i`, which pinned a claim
     * nothing observed supports. "Institutional single sign-on" reads plainest
     * as "your institutional account signs you in"; the one unauthenticated
     * observation of the deployment's login flow (`docs/developer-guide-k8s.md`,
     * 2026-08-01) found only an Email-or-Username field and an ORCID button at
     * the identification stage, with later stages UNOBSERVED. The copy was
     * WEAKENED rather than specified, because naming the identity product is
     * forbidden on every Settings tab (see the withheld list below, and the
     * same list in `settings-page.test.tsx` and the backend's own guard).
     *
     * The assertion is inverted rather than deleted: the retired phrase must
     * not come back, and the edge must still be described as a real sign-in
     * step, so this does not drift into "no authentication" — which the test
     * above it already forbids.
     */
    expect(auth.detail).not.toMatch(/single sign-on/i);
    expect(auth.detail).toMatch(/sit behind an interactive sign-in step/i);
    expect(auth.detail).toMatch(/a browser session is established there/i);
    expect(auth.detail).toMatch(/how the deployment is operated/i);
    expect(auth.detail).toMatch(/never something this app verified/i);
    expect(auth.detail).toMatch(/the browser cannot see the edge/i);
  });

  it('states app-managed identity, the shared key, and key management separately', () => {
    // (b) app-managed identity / roles
    expect(auth.detail).toMatch(
      /ISAAC itself does not manage user accounts, profiles, or application roles/i,
    );
    // (c) the optional shared bearer key
    expect(auth.detail).toMatch(/one shared bearer key/i);
    expect(auth.detail).toMatch(/no way to report whether either restriction is active/i);
    // (d) per-user API-key management
    expect(auth.detail).toMatch(/no per-user API-key management/i);
    expect(auth.detail).toMatch(/no operation creates, lists, revokes, or rotates a credential/i);
  });

  it('names no identity product, host or infrastructure component', () => {
    // The same withheld list `settings-page.test.tsx` and the backend enforce.
    for (const needle of ['authentik', 'ingress', 'k8s', 'kubernetes', 'localhost', '127.0.0.1']) {
      expect(text.toLowerCase()).not.toContain(needle);
    }
  });
});

describe('Settings copy — synthetic-only is a MODE claim, never a content claim', () => {
  const synthetic = concept('synthetic-data-only');
  const noReal = concept('no-real-experiment-data');

  it('says the app cannot tell real data from synthetic', () => {
    expect(synthetic.detail).toMatch(/cannot tell real data from synthetic/i);
    expect(noReal.detail).toMatch(/nothing in the app inspects that text to judge whether it is real/i);
  });

  it('states that real mode intentionally refuses to start', () => {
    expect(synthetic.detail).toMatch(/real mode intentionally refuses to start/i);
    expect(synthetic.detail).toMatch(/guardrails it would need do not exist yet/i);
  });

  it('claims no content-based real/synthetic classification anywhere', () => {
    const all = concepts
      .flatMap((c) => [c.heading, c.summary, c.detail, c.more?.text ?? ''])
      .join(' ');
    expect(all).not.toMatch(/detects? real data/i);
    expect(all).not.toMatch(/scans? (the )?(file|content)/i);
    expect(all).not.toMatch(/inspects? (the )?(file|upload)s? (content|to (prove|verify))/i);
    expect(all).not.toMatch(/real-looking .* (intercepted|rejected|refused)/i);
  });
});

// --- the same claim class, across EVERY frontend source file -----------------

/*
 * WHY THIS EXISTS. The assertion above scanned `settingsConcepts` ONLY, so it
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

  it.each(CONTENT_CLASSIFICATION_CLAIM)('never claims %s', (_label, pattern) => {
    const offenders = files.filter((path) => pattern.test(renderedCopy(path)));
    expect(offenders).toEqual([]);
  });
});
