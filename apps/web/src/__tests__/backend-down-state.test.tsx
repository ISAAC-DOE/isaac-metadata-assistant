import { describe, it, expect, afterEach, vi } from 'vitest';
import { render } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { BackendDown, downCopy } from '../components/FetchStates';
import { ApiError, RUN_COMMAND } from '../lib/api';

/*
 * P36V.2 — the hosted down state.
 *
 * Hosted QA: a session token expired and all 14 BackendDown call sites told a
 * hosted user to run uvicorn on their laptop. The fix must NOT swap one
 * confident wrong screen for another (an unconditional "session expired"), so
 * these tests pin BOTH halves of the rule:
 *   specific where a signal determines the cause (401 / 403 / HTML intercept),
 *   generic where nothing does (a hosted network-level failure).
 */

/**
 * Load the component + client as a HOSTED build (`VITE_API_BASE=/krish/api`).
 * Vite substitutes that env at build time, so the only faithful way to exercise
 * it is a fresh module registry with the env stubbed. `BackendDown` and its
 * children are hook-free, so rendering a fresh-registry element with the
 * already-imported test renderer is safe.
 */
async function loadHosted() {
  vi.resetModules();
  vi.stubEnv('VITE_API_BASE', '/krish/api');
  const fetchStates = await import('../components/FetchStates');
  const apiModule = await import('../lib/api');
  return { ...fetchStates, ApiError: apiModule.ApiError, isHostedBuild: apiModule.isHostedBuild };
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});

const unreachable = () =>
  new ApiError('The ISAAC API could not be reached.', {
    unreachable: true,
    path: '/experiments',
  });

describe('BackendDown — local build (no VITE_API_BASE)', () => {
  it('keeps the run command and today’s copy: there it is actionable', () => {
    const view = render(<BackendDown error={unreachable()} onRetry={() => {}} />);
    expect(view.getByText('Backend Not Running')).toBeInTheDocument();
    expect(view.getByText(RUN_COMMAND)).toBeInTheDocument();
    expect(view.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('keeps role="alert" and a single h2 title', () => {
    const view = render(<BackendDown error={unreachable()} />);
    const alert = view.getByRole('alert');
    expect(alert).toBeInTheDocument();
    const headings = alert.querySelectorAll('h2');
    expect(headings).toHaveLength(1);
    expect(headings[0].textContent).toBe('Backend Not Running');
  });

  it('404 stays the Record Not Found branch — no command, no reload', () => {
    const view = render(
      <BackendDown error={new ApiError('Request failed (404).', { status: 404 })} />,
    );
    expect(view.getByText('Record Not Found')).toBeInTheDocument();
    expect(
      view.getByText(
        'This experiment id is not in the local workspace — it may not have been created yet.',
      ),
    ).toBeInTheDocument();
    expect(view.queryByText(RUN_COMMAND)).toBeNull();
    expect(view.queryByRole('button', { name: 'Reload' })).toBeNull();
  });

  it('401 is specific even locally — a rejected session is a rejected session', () => {
    const view = render(
      <BackendDown error={new ApiError('Request failed (401).', { status: 401 })} />,
    );
    expect(view.getByText('Sign-In Required')).toBeInTheDocument();
    expect(view.getByText('Reload the page to sign in again.')).toBeInTheDocument();
    expect(view.queryByText(RUN_COMMAND)).toBeNull();
  });

  it('carries the ISAAC mark presentationally — never a link on a dead end', () => {
    const view = render(<BackendDown error={unreachable()} />);
    const brand = view.container.querySelector('.fetch-state-brand');
    expect(brand).not.toBeNull();
    // The wordmark reads as text; the tile reuses the TopBar mark, aria-hidden.
    expect(brand!.textContent).toContain('ISAAC');
    const tile = brand!.querySelector('.brand-tile');
    expect(tile).not.toBeNull();
    expect(tile!.getAttribute('aria-hidden')).toBe('true');
    expect(tile!.querySelector('svg')).not.toBeNull();
    // Navigation cannot help when the API is unreachable.
    expect(brand!.querySelector('a')).toBeNull();
  });
});

describe('BackendDown — the Technical Details box', () => {
  it('is its own collapsed, keyboard-operable disclosure at the bottom', () => {
    const view = render(<BackendDown error={unreachable()} />);
    const details = view.container.querySelector('details.fetch-state-technical');
    expect(details).not.toBeNull();
    // <details>/<summary> is natively focusable and toggles on Enter/Space.
    expect((details as HTMLDetailsElement).open).toBe(false);
    expect(details!.querySelector('summary')!.textContent).toBe('Technical Details');
    // Last child of the message body — below the copy and the actions.
    const body = view.container.querySelector('.fetch-state-body')!;
    expect(body.lastElementChild).toBe(details);
  });

  it('reports only observed facts, and says plainly when a fact is absent', () => {
    const view = render(<BackendDown error={unreachable()} />);
    const text = view.container.querySelector('.fetch-state-technical')!.textContent ?? '';
    expect(text).toContain('no HTTP status — the request did not complete');
    expect(text).toContain('yes — the request did not complete'); // network-level
    expect(text).toContain('no — not detected'); // HTML intercept
    expect(text).toContain('not reported'); // content-type
    expect(text).toContain('http://127.0.0.1:8000/api'); // API base
    expect(text).toContain('/experiments'); // request path
  });

  it('reports a status, a content-type and an intercept when they WERE observed', () => {
    const view = render(
      <BackendDown
        error={
          new ApiError('The API path returned an HTML page instead of JSON (an edge intercept).', {
            status: 200,
            path: '/memory/graph',
            contentType: 'text/html; charset=utf-8',
            htmlIntercept: true,
          })
        }
      />,
    );
    const text = view.container.querySelector('.fetch-state-technical')!.textContent ?? '';
    expect(text).toContain('200');
    expect(text).toContain('text/html; charset=utf-8');
    expect(text).toContain('yes — an API path answered with HTML');
    expect(text).toContain('/memory/graph');
  });

  it('never renders a credential — no token, no Bearer, no Authorization, no API key', () => {
    vi.stubEnv('VITE_API_KEY', 'synthetic-not-a-real-key-abc123');
    const view = render(
      <BackendDown
        error={
          new ApiError('Request failed (401).', {
            status: 401,
            path: '/experiments',
            contentType: 'application/json',
          })
        }
      />,
    );
    const whole = view.container.textContent ?? '';
    expect(whole).not.toContain('synthetic-not-a-real-key-abc123');
    expect(whole).not.toContain('Bearer');
    expect(whole).not.toContain('Authorization');
    // The reported facts themselves — every <dt>/<dd> pair — mention no
    // credential at all (the word "token" appears only in the note below them,
    // promising the opposite).
    const figures =
      view.container.querySelector('.fetch-state-technical-figures')!.textContent ?? '';
    for (const forbidden of ['token', 'bearer', 'authorization', 'cookie', 'api key', 'secret']) {
      expect(figures.toLowerCase()).not.toContain(forbidden);
    }
    expect(whole).toContain('No credential, token, cookie or request header is shown here');
  });
});

describe('BackendDown — hosted build (VITE_API_BASE=/krish/api)', () => {
  it('a network-level failure names BOTH plausible causes and asserts neither', async () => {
    const hosted = await loadHosted();
    const view = render(
      <hosted.BackendDown
        error={
          new hosted.ApiError('The ISAAC API could not be reached.', {
            unreachable: true,
            path: '/experiments',
          })
        }
      />,
    );
    expect(view.getByText('ISAAC Is Not Responding')).toBeInTheDocument();
    const body = view.container.querySelector('.fetch-state-body')!.textContent ?? '';
    expect(body).toContain('cannot tell which of two causes applies');
    expect(body).toContain('the sign-in session may have ended');
    expect(body).toContain('the service may be temporarily unavailable');
    // It must NOT claim the specific cause it cannot observe.
    expect(view.queryByText('Sign-In Required')).toBeNull();
    expect(body).not.toContain('session has ended');
    // Reload is right if it was the session, harmless otherwise.
    expect(view.getByRole('button', { name: 'Reload' })).toBeInTheDocument();
  });

  it('never shows the local run command and never says "local"', async () => {
    const hosted = await loadHosted();
    for (const error of [
      new hosted.ApiError('x', { unreachable: true, path: '/experiments' }),
      new hosted.ApiError('x', { status: 401, path: '/experiments' }),
      new hosted.ApiError('x', { status: 500, path: '/experiments' }),
      new hosted.ApiError('x', {
        status: 200,
        path: '/experiments',
        contentType: 'text/html',
        htmlIntercept: true,
      }),
    ]) {
      const view = render(<hosted.BackendDown error={error} onRetry={() => {}} />);
      const whole = view.container.textContent ?? '';
      expect(whole).not.toContain(RUN_COMMAND);
      expect(whole).not.toContain('uvicorn');
      expect(whole.toLowerCase()).not.toContain('local');
      view.unmount();
    }
  });

  it('401 and 403 each say what was actually observed', async () => {
    const hosted = await loadHosted();
    const view401 = render(
      <hosted.BackendDown error={new hosted.ApiError('x', { status: 401 })} />,
    );
    expect(view401.getByText('Sign-In Required')).toBeInTheDocument();
    expect(
      view401.getByText(/rejected this request as unauthenticated \(HTTP 401\)/),
    ).toBeInTheDocument();
    view401.unmount();

    const view403 = render(
      <hosted.BackendDown error={new hosted.ApiError('x', { status: 403 })} />,
    );
    expect(view403.getByText('Sign-In Required')).toBeInTheDocument();
    expect(
      view403.getByText(/refused this request as unauthorized \(HTTP 403\)/),
    ).toBeInTheDocument();
  });

  it('an HTML intercept is treated as the authentication signal it is', async () => {
    const hosted = await loadHosted();
    const view = render(
      <hosted.BackendDown
        error={
          new hosted.ApiError('x', {
            status: 200,
            contentType: 'text/html; charset=utf-8',
            htmlIntercept: true,
          })
        }
      />,
    );
    expect(view.getByText('Sign-In Required')).toBeInTheDocument();
    expect(
      view.getByText(/A sign-in page was returned in place of the ISAAC API/),
    ).toBeInTheDocument();
    expect(view.getByRole('button', { name: 'Reload' })).toBeInTheDocument();
  });

  it('a status that is not 404/401/403 does not claim the API was unreachable', async () => {
    const hosted = await loadHosted();
    const view = render(
      <hosted.BackendDown error={new hosted.ApiError('x', { status: 500 })} />,
    );
    expect(view.getByText('ISAAC Returned an Error')).toBeInTheDocument();
    expect(view.getByText(/was reached but answered with HTTP 500/)).toBeInTheDocument();
  });

  it('404 keeps its own branch, worded without "local"', async () => {
    const hosted = await loadHosted();
    const view = render(
      <hosted.BackendDown error={new hosted.ApiError('x', { status: 404 })} />,
    );
    expect(view.getByText('Record Not Found')).toBeInTheDocument();
    expect(
      view.getByText(
        'This experiment id is not in the workspace — it may not have been created yet.',
      ),
    ).toBeInTheDocument();
  });

  it('the debug box reports the hosted base and build mode', async () => {
    const hosted = await loadHosted();
    expect(hosted.isHostedBuild).toBe(true);
    const view = render(
      <hosted.BackendDown
        error={new hosted.ApiError('x', { unreachable: true, path: '/memory/graph' })}
      />,
    );
    const text = view.container.querySelector('.fetch-state-technical')!.textContent ?? '';
    expect(text).toContain('/krish/api');
    expect(text).toContain('hosted');
    expect(text).toContain('/memory/graph');
  });
});

describe('downCopy — the branch table, as a pure function', () => {
  const kindsFor = (hosted: boolean) => ({
    notFound: downCopy(new ApiError('x', { status: 404 }), hosted).kind,
    unauthenticated: downCopy(new ApiError('x', { status: 401 }), hosted).kind,
    forbidden: downCopy(new ApiError('x', { status: 403 }), hosted).kind,
    intercepted: downCopy(new ApiError('x', { status: 200, htmlIntercept: true }), hosted).kind,
    serverError: downCopy(new ApiError('x', { status: 500 }), hosted).kind,
    unreachable: downCopy(new ApiError('x', { unreachable: true }), hosted).kind,
    nothing: downCopy(undefined, hosted).kind,
  });

  it('hosted: 404 → not_found, auth signals → auth, other status → http_error, else generic', () => {
    expect(kindsFor(true)).toEqual({
      notFound: 'not_found',
      unauthenticated: 'auth',
      forbidden: 'auth',
      intercepted: 'auth',
      serverError: 'http_error',
      unreachable: 'unreachable',
      nothing: 'unreachable',
    });
  });

  it('local: the auth signals still win; everything else keeps today’s local state', () => {
    expect(kindsFor(false)).toEqual({
      notFound: 'not_found',
      unauthenticated: 'auth',
      forbidden: 'auth',
      intercepted: 'auth',
      serverError: 'local',
      unreachable: 'local',
      nothing: 'local',
    });
  });

  it('only the local kind ever offers the run command', () => {
    for (const hosted of [true, false]) {
      for (const error of [
        new ApiError('x', { status: 404 }),
        new ApiError('x', { status: 401 }),
        new ApiError('x', { status: 500 }),
        new ApiError('x', { unreachable: true }),
      ]) {
        const copy = downCopy(error, hosted);
        expect(copy.showRunCommand).toBe(copy.kind === 'local');
      }
    }
  });
});

/*
 * The two render sites must not drift. `SearchDialog` is hook-bearing, so it
 * cannot be re-imported into a fresh (hosted) module registry the way the
 * hook-free panel can; this pins the invariant at the source instead — every
 * RUN_COMMAND render is behind the compile-time `!isHostedBuild` guard that
 * lets a hosted bundle drop the string. Verified end-to-end by the hosted
 * `vite build` + `grep -c uvicorn dist/assets/*.js` → 0.
 */
describe('both render sites guard the run command at build time', () => {
  const SRC = resolve(__dirname, '..');
  const files = ['components/FetchStates.tsx', 'components/SearchDialog.tsx'];

  it('renders RUN_COMMAND only behind !isHostedBuild, in exactly these two files', () => {
    for (const file of files) {
      const source = readFileSync(resolve(SRC, file), 'utf8');
      expect(source).toContain('{!isHostedBuild && copy.showRunCommand && (');
      // The only RUN_COMMAND render in the file is that guarded one.
      const renders = source.match(/\{RUN_COMMAND\}/g) ?? [];
      expect(renders).toHaveLength(1);
    }
  });

  it('SearchDialog renders the SHARED copy, not its own local-only wording', () => {
    const source = readFileSync(resolve(SRC, 'components/SearchDialog.tsx'), 'utf8');
    expect(source).toContain('downCopy(error)');
    expect(source).toContain('DownTechnicalDetails');
    expect(source).not.toContain('The local ISAAC API is not responding');
  });
});
