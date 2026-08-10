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

  /*
   * THE PATH IS NOW PART OF THIS TEST'S PRECONDITION, and that is a strengthening
   * rather than a relaxation. This branch claims a missing RECORD, so it may only be
   * reached by a request that named one; the assertion used to be made over a 404
   * with no path at all, which is why the same sentence was also being rendered for a
   * failed LIST read (see `isRecordPath` and the sibling test below).
   */
  it('404 on a RECORD path stays the Record Not Found branch — no command, no reload', () => {
    const view = render(
      <BackendDown
        error={new ApiError('Request failed (404).', { status: 404, path: '/experiments/EXP-1' })}
      />,
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

  /*
   * THE DEFECT BROWSER TESTING CAUGHT, pinned as copy.
   *
   * A reload holding an expired worked-example pointer issued `GET /api/experiments`
   * with a session header naming no session; the backend answered 404; and My
   * Experiments rendered "Record Not Found — this experiment id is not in the local
   * workspace" over a LIST failure, on a screen whose truthful state was the ordinary
   * empty workspace. The boot-window desync that issued that request is fixed in
   * `tutorialController.initialState()`; this pins the second half — that the copy
   * itself may not describe a collection read as a missing record, which is reachable
   * from any expiry mid-session and from `/runtime/records`, `/memory/*` and
   * `/graph/*` as well.
   */
  it('404 on a COLLECTION path claims only the 404 — no record, no experiment id', () => {
    const view = render(
      <BackendDown error={new ApiError('Request failed (404).', { status: 404, path: '/experiments' })} />,
    );
    expect(view.getByText('Not Found')).toBeInTheDocument();
    expect(view.queryByText('Record Not Found')).toBeNull();
    const body = view.container.querySelector('.fetch-state-body')!.textContent ?? '';
    expect(body).toContain('answered HTTP 404 for this request');
    // The two claims that were false of a list read.
    expect(body).not.toMatch(/experiment id/i);
    expect(body).not.toMatch(/may not have been created yet/i);
    // Still no unactionable local remedy and no unevidenced reload prompt.
    expect(view.queryByText(RUN_COMMAND)).toBeNull();
    expect(view.queryByRole('button', { name: 'Reload' })).toBeNull();
  });

  it('the Retry the caller supplies is still offered on a collection 404', () => {
    const view = render(
      <BackendDown
        error={new ApiError('Request failed (404).', { status: 404, path: '/experiments' })}
        onRetry={() => {}}
      />,
    );
    expect(view.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
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

  it('404 on a record path keeps its own branch, worded without "local"', async () => {
    const hosted = await loadHosted();
    const view = render(
      <hosted.BackendDown
        error={new hosted.ApiError('x', { status: 404, path: '/experiments/EXP-1' })}
      />,
    );
    expect(view.getByText('Record Not Found')).toBeInTheDocument();
    expect(
      view.getByText(
        'This experiment id is not in the workspace — it may not have been created yet.',
      ),
    ).toBeInTheDocument();
  });

  /*
   * AN HTML-BODIED 404 ON A RECORD PATH IS NOT A MISSING RECORD, and it used to be
   * reported as one — the most definitive sentence this panel can say ("this
   * experiment id is not in the workspace"), asserted from a response that never
   * reached the application. `httpError` copies the status and nothing else, so the
   * edge's 404 arrived indistinguishable from `{"error": "experiment_not_found"}`.
   *
   * The two record-404 tests above are the other half of this pair and must both
   * keep passing: a real 404 from ISAAC still says "Record Not Found". What changed
   * is only which responses are allowed to make that claim.
   */
  it('a 404 whose body is HTML is an intercept, not a missing record', async () => {
    const hosted = await loadHosted();
    const view = render(
      <hosted.BackendDown
        error={
          new hosted.ApiError('x', {
            status: 404,
            path: '/experiments/EXP-1',
            contentType: 'text/html; charset=utf-8',
            htmlIntercept: true,
          })
        }
      />,
    );
    expect(view.queryByText('Record Not Found')).toBeNull();
    expect(view.getByText('Sign-In Required')).toBeInTheDocument();
    expect(
      view.getByText(/A sign-in page was returned in place of the ISAAC API/),
    ).toBeInTheDocument();
    expect(view.getByRole('button', { name: 'Reload' })).toBeInTheDocument();
  });

  it('an HTML-bodied 404 on a NON-record path is also an intercept', async () => {
    const hosted = await loadHosted();
    const view = render(
      <hosted.BackendDown
        error={
          new hosted.ApiError('x', {
            status: 404,
            path: '/memory/graph',
            contentType: 'text/html; charset=utf-8',
            htmlIntercept: true,
          })
        }
      />,
    );
    // The generic 404 branch's first sentence — "The ISAAC API answered HTTP 404"
    // — would be false here: an intercept answered, not the API.
    expect(view.queryByText('Not Found')).toBeNull();
    expect(view.getByText('Sign-In Required')).toBeInTheDocument();
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
  /*
   * `notFound` SPLIT IN TWO, because a 404 does not by itself say what was missing.
   * The record branch requires a record path; a collection path, a build-level path
   * and an unrecorded path all take the narrower `path_not_found` branch. The old
   * single row asserted the record claim over a pathless 404, i.e. over the exact
   * input for which it is unsupported.
   */
  const kindsFor = (hosted: boolean) => ({
    notFoundRecord: downCopy(
      new ApiError('x', { status: 404, path: '/experiments/EXP-1' }),
      hosted,
    ).kind,
    notFoundCollection: downCopy(new ApiError('x', { status: 404, path: '/experiments' }), hosted)
      .kind,
    // A read BELOW the record, with no reason observed — the path decides.
    notFoundRecordPart: downCopy(
      new ApiError('x', { status: 404, path: '/experiments/EXP-1/runs/RUN-1' }),
      hosted,
    ).kind,
    // THE REASON OVERRIDES THE PATH, both ways. These two rows are the race-proof
    // half of the rule: `experiment_not_found` on a sub-path is still the record
    // claim, and `source_not_allowed` on a sub-path never is.
    reasonRecordOnSubPath: downCopy(
      new ApiError('x', {
        status: 404,
        path: '/experiments/EXP-1/source-preview?source=x.csv',
        reason: 'experiment_not_found',
      }),
      hosted,
    ).kind,
    reasonSourceNotAllowed: downCopy(
      new ApiError('x', {
        status: 404,
        path: '/experiments/EXP-1/source-preview?source=x.csv',
        reason: 'source_not_allowed',
      }),
      hosted,
    ).kind,
    // A dead worked-example session is not a missing record, and an unrecognised
    // reason is not anything — both must degrade, not assert.
    reasonDeadSession: downCopy(
      new ApiError('x', {
        status: 404,
        path: '/experiments/EXP-1',
        reason: 'tutorial_session_not_found',
      }),
      hosted,
    ).kind,
    reasonUnrecognised: downCopy(
      new ApiError('x', { status: 404, path: '/experiments/EXP-1', reason: 'brand_new_reason' }),
      hosted,
    ).kind,
    notFoundPathless: downCopy(new ApiError('x', { status: 404 }), hosted).kind,
    unauthenticated: downCopy(new ApiError('x', { status: 401 }), hosted).kind,
    forbidden: downCopy(new ApiError('x', { status: 403 }), hosted).kind,
    intercepted: downCopy(new ApiError('x', { status: 200, htmlIntercept: true }), hosted).kind,
    serverError: downCopy(new ApiError('x', { status: 500 }), hosted).kind,
    unreachable: downCopy(new ApiError('x', { unreachable: true }), hosted).kind,
    nothing: downCopy(undefined, hosted).kind,
  });

  it('hosted: 404 → not_found only for a record, auth signals → auth, other status → http_error, else generic', () => {
    expect(kindsFor(true)).toEqual({
      notFoundRecord: 'not_found',
      notFoundCollection: 'path_not_found',
      notFoundRecordPart: 'record_part_not_found',
      reasonRecordOnSubPath: 'not_found',
      reasonSourceNotAllowed: 'record_part_not_found',
      reasonDeadSession: 'path_not_found',
      reasonUnrecognised: 'path_not_found',
      notFoundPathless: 'path_not_found',
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
      notFoundRecord: 'not_found',
      // Deliberately NOT the `local` branch: the API answered, so "Backend Not
      // Running" would be false. A 404 is a 404 in both builds.
      notFoundCollection: 'path_not_found',
      notFoundRecordPart: 'record_part_not_found',
      reasonRecordOnSubPath: 'not_found',
      reasonSourceNotAllowed: 'record_part_not_found',
      reasonDeadSession: 'path_not_found',
      reasonUnrecognised: 'path_not_found',
      notFoundPathless: 'path_not_found',
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

/*
 * A MISSING SUB-RESOURCE IS NOT A MISSING EXPERIMENT.
 *
 * `isRecordPath` was `/^\/experiments\/[^/]/` — unanchored — so it matched all
 * EIGHTEEN sub-reads `api.ts` builds under a record as well as the record itself,
 * and every 404 from any of them rendered the most definitive sentence this panel
 * can say: "Record Not Found — this experiment id is not in the workspace".
 *
 * The backend had gone out of its way to say otherwise. `routes.py::_run_not_found`
 * is a deliberately DIFFERENT body from `_not_found` because, in its own docstring,
 * `run_not_found` means the record "exists and was read successfully and simply
 * holds no run under that id", and collapsing the two "would tell a client to go
 * looking in the wrong place". The client collapsed them anyway.
 *
 * MEASURED ON THE DEPLOYED APP, hosted commit `bd3effc` (`v0.0.100`), 2026-08-10:
 * `GET /krish/api/experiments` lists `01KZM7HYJVQY1C0X3KFV805YT2`, and
 * `GET /krish/api/experiments/01KZM7HYJVQY1C0X3KFV805YT2/runs/01BOGUS0000000000000000000`
 * answers `404 {"error":"run_not_found","experiment_id":"01KZM7HYJVQY1C0X3KFV805YT2",
 * "id":"01BOGUS0000000000000000000"}`. A real, existing, listed record.
 *
 * The reachable USER-FACING instance is Evidence, not Runs: `getEvidenceBundle`
 * previews every cited source file in one `Promise.all` with no per-item catch, so a
 * single `source_not_allowed` 404 rejected the whole bundle and `EvidenceExplorer`
 * blamed the record's existence.
 */
describe('a 404 about part of a record never claims the record is missing', () => {
  const at = (path: string, reason?: string) =>
    new ApiError('Request failed (404).', { status: 404, path, reason });

  /** The two sentences that assert the record does not exist. */
  const assertsMissingRecord = (text: string) =>
    /experiment id is not in the/i.test(text) || /may not have been created yet/i.test(text);

  const bodyOf = (error: ApiError) => {
    const view = render(<BackendDown error={error} />);
    const text = view.container.querySelector('.fetch-state-body')!.textContent ?? '';
    view.unmount();
    return text;
  };

  it('THE REGRESSION: a run 404 does not claim the experiment is missing', () => {
    const body = bodyOf(at('/experiments/EXP-1/runs/RUN-1', 'run_not_found'));
    expect(assertsMissingRecord(body)).toBe(false);
    expect(body).toContain('does not establish that the experiment is missing');
    // It names the part that WAS read, from the path.
    expect(body).toContain('“runs”');
  });

  it('THE REGRESSION: a source-preview 404 does not claim the experiment is missing', () => {
    const error = at('/experiments/EXP-1/source-preview?source=outside.csv', 'source_not_allowed');
    expect(assertsMissingRecord(bodyOf(error))).toBe(false);
    const lines = downCopy(error, false).lines.join(' ');
    // The query string is not mistaken for part of the segment. Asserted over the
    // COPY, not the whole panel: Technical Details reports the full request path by
    // design, and that row is pre-existing, correct, and credential-free.
    expect(lines).toContain('“source-preview”');
    expect(lines).not.toContain('outside.csv');
  });

  it('no sub-read of a record can produce the missing-record claim from its PATH alone', () => {
    // Every suffix `api.ts` builds under `/experiments/{id}`.
    const suffixes = [
      'draft',
      'pending',
      'answers',
      'edit',
      'runs',
      'runs/RUN-1',
      'runs/RUN-1/check',
      'ingestion/csv/preview',
      'export',
      'validate',
      'audit',
      'warnings',
      'evidence',
      'evidence-classification',
      'source-preview?source=a.csv',
      'artifacts',
      'assistant/query',
    ];
    for (const suffix of suffixes) {
      const copy = downCopy(at(`/experiments/EXP-1/${suffix}`), true);
      expect(copy.kind).toBe('record_part_not_found');
      expect(assertsMissingRecord(copy.lines.join(' '))).toBe(false);
    }
    // Guard the guard: the list above must be sub-reads, not the record itself.
    expect(downCopy(at('/experiments/EXP-1'), true).kind).toBe('not_found');
  });

  /*
   * THE CASE A PATH-BASED FIX SILENTLY BREAKS, which is why the reason is read at
   * all. `getEvidenceBundle` awaits `getExperiment(id)` and every
   * `getSourcePreview(id, file)` in ONE `Promise.all`; when the experiment really is
   * absent they all 404 and the rejection that arrives is whichever landed first — a
   * race. Narrowing the path predicate alone would make the copy for one underlying
   * truth depend on that race. The reason does not.
   */
  it('experiment_not_found on a SUB-resource path still says Record Not Found', () => {
    const view = render(
      <BackendDown
        error={at('/experiments/EXP-1/source-preview?source=a.csv', 'experiment_not_found')}
      />,
    );
    expect(view.getByText('Record Not Found')).toBeInTheDocument();
    expect(
      view.getByText(
        'This experiment id is not in the local workspace — it may not have been created yet.',
      ),
    ).toBeInTheDocument();
  });

  it('a real missing record is still reported plainly — the fix hides no 404', () => {
    for (const error of [
      at('/experiments/EXP-1'), // no reason observed; the path names one record
      at('/experiments/EXP-1', 'experiment_not_found'),
      at('/experiments/EXP-1/runs', 'experiment_not_found'),
    ]) {
      const body = bodyOf(error);
      expect(assertsMissingRecord(body)).toBe(true);
    }
  });

  it('a dead worked-example session is not reported as a missing record', () => {
    // `tutorial_scope` raises this BEFORE any record work, so it is evidence about
    // the session and none at all about whether the record exists.
    const body = bodyOf(at('/experiments/EXP-1', 'tutorial_session_not_found'));
    expect(assertsMissingRecord(body)).toBe(false);
    expect(body).toContain('answered HTTP 404 for this request');
  });

  it('an unrecognised reason degrades to generic — never to a confident claim', () => {
    const copy = downCopy(at('/experiments/EXP-1', 'some_future_reason'), true);
    expect(copy.kind).toBe('path_not_found');
    expect(assertsMissingRecord(copy.lines.join(' '))).toBe(false);
  });

  it('a pathless, reasonless 404 still lands generic', () => {
    const copy = downCopy(new ApiError('x', { status: 404 }), true);
    expect(copy.kind).toBe('path_not_found');
    expect(assertsMissingRecord(copy.lines.join(' '))).toBe(false);
  });

  it('Retry is still offered on a sub-resource 404 when the caller supplies one', () => {
    const view = render(
      <BackendDown error={at('/experiments/EXP-1/runs/RUN-1', 'run_not_found')} onRetry={() => {}} />,
    );
    expect(view.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    // No unevidenced reload prompt, and no unactionable local remedy.
    expect(view.queryByRole('button', { name: 'Reload' })).toBeNull();
    expect(view.queryByText(RUN_COMMAND)).toBeNull();
  });

  /*
   * POLARITY GUARD, asserted in BOTH directions because a test in this repo once
   * shipped inverted and passed. `interceptedByEdge` must win over every 404 branch,
   * including the two new reason-based ones: a sign-in page served with a 404 carries
   * no ISAAC reason, and a reason must never be honoured from one.
   */
  it('an HTML-bodied 404 on a record path is STILL the auth branch, not either 404 branch', () => {
    const html = (path: string, reason?: string) =>
      new ApiError('x', {
        status: 404,
        path,
        contentType: 'text/html; charset=utf-8',
        htmlIntercept: true,
        reason,
      });
    // The positive half: it lands in `auth`.
    const view = render(<BackendDown error={html('/experiments/EXP-1')} />);
    expect(view.getByText('Sign-In Required')).toBeInTheDocument();
    expect(
      view.getByText(/A sign-in page was returned in place of the ISAAC API/),
    ).toBeInTheDocument();
    // The negative half: neither 404 branch, and neither 404 branch's wording.
    expect(view.queryByText('Record Not Found')).toBeNull();
    expect(view.queryByText('Not Found')).toBeNull();
    const body = view.container.querySelector('.fetch-state-body')!.textContent ?? '';
    expect(assertsMissingRecord(body)).toBe(false);
    expect(body).not.toContain('answered HTTP 404');

    // And the intercept wins even when a reason field is somehow populated — on a
    // record path, a sub-resource path, and for each reason the branches key on.
    for (const path of ['/experiments/EXP-1', '/experiments/EXP-1/runs/RUN-1']) {
      for (const reason of [undefined, 'experiment_not_found', 'run_not_found']) {
        expect(downCopy(html(path, reason), true).kind).toBe('auth');
      }
    }
  });
});
