import { describe, it, expect, afterEach, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  BackendDown,
  downCopy,
  isRecordPath,
  recordSubResource,
  SUB_RESOURCE_LABELS,
} from '../components/FetchStates';
import { ApiError, RUN_COMMAND } from '../lib/api';
import { EXAMPLE_RECORD_IDS } from '../lib/exampleRecords';

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
    // ...BUT THE REASON MAY NOT WIDEN THE RECORD CLAIM OFF `/experiments/{id}`. The
    // sentence names an experiment id, so a path with no experiment id in it may not
    // reach it — see the sibling describe for the three concrete paths.
    reasonRecordOnConceptPath: downCopy(
      new ApiError('x', {
        status: 404,
        path: '/memory/concepts/CONC-1',
        reason: 'experiment_not_found',
      }),
      hosted,
    ).kind,
    reasonRecordPathless: downCopy(
      new ApiError('x', { status: 404, reason: 'experiment_not_found' }),
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
      reasonRecordOnConceptPath: 'path_not_found',
      reasonRecordPathless: 'path_not_found',
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
      reasonRecordOnConceptPath: 'path_not_found',
      reasonRecordPathless: 'path_not_found',
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
    // `downCopy(error…` rather than `downCopy(error)`: the palette now passes the
    // same `hosted` and `scope` arguments `BackendDown` passes, which is MORE
    // sharing, not less. What this pins is that the copy comes from the shared
    // function at all — the wording assertions below are what stop it drifting.
    expect(source).toMatch(/downCopy\(error[,)]/);
    expect(source).toContain('DownTechnicalDetails');
    expect(source).not.toContain('The local ISAAC API is not responding');
  });
});

/*
 * A MISSING SUB-RESOURCE IS NOT A MISSING EXPERIMENT.
 *
 * `isRecordPath` was `/^\/experiments\/[^/]/` — unanchored — so it matched every
 * sub-read `api.ts` builds under a record as well as the record itself (17 distinct
 * suffixes, measured by the inventory block above; an earlier revision of this comment
 * said EIGHTEEN, which matched no measurement and is withdrawn). Every 404 from any of
 * them rendered the most definitive sentence this panel can say: "Record Not Found —
 * this experiment id is not in the workspace".
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
/*
 * THE SUB-READ INVENTORY, DERIVED FROM `api.ts` RATHER THAN RESTATED.
 *
 * Two tests below need "every sub-resource path `api.ts` builds under a record", and
 * a hand-written list of them is exactly the artefact that rots: a sub-read added to
 * the client would leave the list — and therefore both guards, and the label map they
 * check — quietly describing yesterday's API. So the list is READ OUT OF `api.ts`.
 *
 * HOW. Every per-record path in that module is a single-line template literal of the
 * form `` `/experiments/${enc(…)}…` ``, so those literals are collected and each is
 * required to be either the bare record path or a sub-read. Measured, and re-measured
 * when the run REMOVAL write was added on top of the submission-history reads.
 * The three numbers are asserted below and are MEASURED after this merge, never
 * added: both merged branches raised them from a shared base, and the arithmetic
 * on a pair of deltas is exactly the failure this file already carries a note
 * about. (The run-removal literal is `runs/${…}/remove`, which adds one literal
 * and one suffix and moves NO segment count, because `runs` was already a first
 * segment. The submission-history reads before it added three `/revisions…`
 * suffixes sharing one new first segment. Before those, the Asset References
 * reads and writes added `assets` twice — the list read and the create write
 * share one path, and the Set folds them into ONE suffix — plus `assets/${…}`
 * and `assets/${…}/remove`, moving the segment count because `assets` is a first
 * segment nothing else used. Before that, `notes` twice plus
 * `notes/${…}/review`; and before that the two per-run override writes
 * `runs/${…}/overrides` and `runs/${…}/overrides/clear`, whose segment `runs`
 * already covered.) Those counts are asserted, so adding a sub-read fails this
 * file.
 *
 * WHAT THIS CANNOT SEE, stated precisely because the obvious reading of the previous
 * paragraph is too generous. `unclassifiedLiterals` catches a literal that STARTS
 * with `/experiments/` and then has an unexpected interior shape. It does NOT catch a
 * per-record path assembled some other way — by concatenation, by a path helper, or
 * across a wrapped multi-line literal — because such a path never appears as a
 * literal beginning with `/experiments/` at all, and the count assertions would still
 * hold. So this derivation is a guard against api.ts GAINING A SUB-READ IN THE
 * ESTABLISHED SHAPE, which is the realistic drift; it is not a proof that the
 * inventory is exhaustive. A refactor that changes how paths are built must revisit
 * this block by hand.
 */
const API_SOURCE = readFileSync(resolve(__dirname, '..', 'lib/api.ts'), 'utf8');

const experimentPathLiterals = [...API_SOURCE.matchAll(/`([^`\n]*)`/g)]
  .map((m) => m[1])
  .filter((lit) => lit.includes('/experiments/') && lit.includes('${'));

const bareRecordLiterals: string[] = [];
const subReadSuffixes = new Set<string>();
const unclassifiedLiterals: string[] = [];
for (const lit of experimentPathLiterals) {
  if (/^\/experiments\/\$\{[^}]*\}$/.test(lit)) bareRecordLiterals.push(lit);
  else {
    const sub = /^\/experiments\/\$\{[^}]*\}\/(.+)$/.exec(lit);
    if (sub) subReadSuffixes.add(sub[1]);
    else unclassifiedLiterals.push(lit);
  }
}

/** Every distinct suffix, with each `${…}` replaced by a concrete-looking segment. */
const SUB_READ_SUFFIXES = [...subReadSuffixes]
  .sort()
  .map((suffix) => suffix.replace(/\$\{[^}]*\}/g, 'SEG-1'));

/** The first segment below `/experiments/{id}` for each — the PART that was read. */
const SUB_READ_SEGMENTS = [
  ...new Set([...subReadSuffixes].map((s) => s.split(/[?#]/)[0].split('/')[0])),
].sort();

describe('the sub-read inventory this file derives from api.ts', () => {
  it('classifies every per-record path literal, and finds the counts it expects', () => {
    // An unexpected interior shape in one of these literals would silently shrink
    // both guards below — see the limits paragraph above for what this misses.
    expect(unclassifiedLiterals).toEqual([]);
    // MEASURED after the merge, not derived by adding the two branches' deltas
    // together. Both the asset/submission-history side and the run-removal side
    // add per-record route literals, and the merge of two counter edits is
    // exactly where this repository has been bitten before — see the note on
    // `A11Y_BASELINE_TOTAL_NODES`, and see the `SUB_READ_SEGMENTS` case below,
    // where both branches wrote the SAME literal and git merged two additions
    // while recording one. Every number here was read out of this test's own
    // failure output after the merge.
    // 37 -> 39: the two RUN-LEVEL WRITE literals in `submitAnswer` and `editField`.
    // Each of those two functions now carries a ternary — the run route when the
    // question belongs to a run, the record route otherwise — because a spectrum, a QC
    // verdict, a descriptor and an asset hash are per-Run, and the record-level route
    // refuses them with `409 belongs_to_a_run` once runs exist. Two functions, one new
    // literal each. Read out of this test's own failure output, not derived.
    // 39 -> 40: `getPendingPage`, the BOUNDED read of the open-question list. It
    // writes the SAME `/experiments/${…}/pending` literal `getPending` writes and
    // appends the query to it as a separate string, so this array — which counts
    // OCCURRENCES — gains one while `SUB_READ_SUFFIXES` and `SUB_READ_SEGMENTS` do not
    // move at all. That identical-literal shape is deliberate and is commented at the
    // call site: a nested template would have registered a sub-read suffix and a
    // segment with no product word behind it, and the two guards below would have gone
    // red over a route this panel already covers. Read out of this test's own failure
    // output, not derived by adding a delta.
    // 40 -> 41: `renameExperiment`, the RENAME. It writes the SAME bare
    // `/experiments/${…}` literal `getExperiment` and `checkRecordVersion` already
    // write, so this array — which counts OCCURRENCES — gains one while
    // `SUB_READ_SUFFIXES` and `SUB_READ_SEGMENTS` do not move at all: there is no
    // sub-path below the record, because a rename PATCHes the record itself. Read out
    // of this test's own failure output (`- 40 / + 41`), not derived by adding a delta.
    // 41 -> 42: `getProvenance`, the read of where each value came from. It writes
    // one new `/experiments/${…}/provenance` literal and appends its optional `?run=`
    // query as a separate string, exactly as `listConflicts`, `listNotes` and
    // `listRuns` do — so this array gains one, `SUB_READ_SUFFIXES` gains `provenance`,
    // and `SUB_READ_SEGMENTS` gains it too, because `provenance` is a first segment
    // nothing else used and therefore needed its own product word in
    // `SUB_RESOURCE_LABELS`. Read out of this test's own failure output
    // (`- 41 / + 42`), not derived by adding a delta.
    expect(experimentPathLiterals.length).toBe(42);
    expect(bareRecordLiterals.length).toBeGreaterThan(0);
    // 31 -> 33: `runs/SEG-1/answers` and `runs/SEG-1/edit`, the two run-level write
    // suffixes. Both are WRITES rather than reads, and they appear here because this
    // inventory is over every per-record path literal in `api.ts` — which is the point:
    // a new sub-path that no down-state classification covers is exactly what this
    // guard exists to surface.
    // 33 -> 34: `provenance`, the read of where each value came from. Read out of
    // this test's own failure output (`have a length of 33 but got 34`), not derived.
    expect(SUB_READ_SUFFIXES).toHaveLength(34);
    // 19, AND THE ROUTE TO THAT NUMBER IS WORTH KEEPING.
    //
    // THIS INCIDENT RECORD WAS LOST IN A MERGE RESOLUTION AND IS RESTORED HERE, an
    // independent review having noticed that the paragraph above still refers to
    // "the `SUB_READ_SEGMENTS` case below" while the case itself had been deleted —
    // a dangling reference to an incident this repository deliberately keeps.
    //
    // What happened: this line was NOT in a merge conflict. Two branches both raised
    // it from 16 to 17 — the asset slice for its own new segment, the transcript
    // slice for `transcript` — so git saw two IDENTICAL one-line changes and merged
    // them without a murmur, leaving a literal that accounted for one of the two
    // additions. The entries changed twice; the total was recorded once. It was
    // caught only because this count is DERIVED from `api.ts` and re-measured here;
    // a hand-maintained pair with no derivation behind it would have merged clean
    // and stayed wrong.
    //
    // That is the same failure mode `A11Y_BASELINE_TOTAL_NODES` carries a long note
    // about, reproduced in a different counter within days, which says something
    // about how easily it recurs. The run-removal merge then hit the SAME class a
    // third time in four separate counters — and 19 is where this one lands, because
    // run removal adds a suffix under `runs`, a first segment that already existed.
    // 20 -> 21: `provenance`. It is a FIRST segment nothing else used, so unlike
    // `runs/SEG-1/remove` above it moves this counter as well as the suffix one, and
    // it needed its own product word in `SUB_RESOURCE_LABELS` ("where the values came
    // from") — the guard below this line is what surfaced that. Read out of this
    // test's own failure output (`have a length of 20 but got 21`), not derived.
    expect(SUB_READ_SEGMENTS).toHaveLength(21);
    // THE CONFLICT-RESOLUTION PAIR, and how these three numbers were arrived at.
    // `listConflicts` and `resolveConflict` add TWO literals and TWO suffixes —
    // `conflicts` and `conflicts/resolve`, the second of which carries no `${…}`
    // at all, so it is the one suffix in this inventory that needs no substitution
    // — and ONE segment, because `conflicts` is a first segment nothing else used
    // and therefore needs its own product word in `SUB_RESOURCE_LABELS`. Every one of 37 / 31 / 20 was READ OUT OF THIS TEST'S
    // OWN FAILURE OUTPUT, one at a time, after the client change — never computed
    // by adding a delta to the previous literal, which is the failure the note
    // above this line records happening three times in four counters.
    expect(SUB_READ_SUFFIXES).toContain('conflicts');
    expect(SUB_READ_SUFFIXES).toContain('conflicts/resolve');
    expect(SUB_READ_SEGMENTS).toContain('conflicts');
    // The run REMOVAL write. It adds one literal and one suffix and moves NO
    // segment count: `runs` was already a first segment, so the product word this
    // panel uses for a failed read of it ("the measurement runs") already covers
    // it and no new label is needed.
    expect(SUB_READ_SUFFIXES).toContain('runs/SEG-1/remove');
    // Spot-check the two shapes that are easiest to derive wrongly.
    expect(SUB_READ_SUFFIXES).toContain('runs/SEG-1/check');
    expect(SUB_READ_SUFFIXES).toContain('source-preview?source=SEG-1');
    expect(SUB_READ_SEGMENTS).toContain('evidence-classification');
    // `notes` is built by TWO methods (the list read and the capture write) from
    // one identical literal, so it must appear as ONE suffix, not two.
    expect(SUB_READ_SUFFIXES).toContain('notes');
    expect(SUB_READ_SUFFIXES).toContain('notes/SEG-1/review');
    expect(SUB_READ_SEGMENTS).toContain('notes');
    // The three submission-history reads share ONE first segment and are three
    // distinct suffixes — the inverse of the `notes` case above, and the shape a
    // hand-written inventory gets wrong in the other direction.
    expect(SUB_READ_SUFFIXES).toContain('revisions');
    expect(SUB_READ_SUFFIXES).toContain('revisions/SEG-1');
    expect(SUB_READ_SUFFIXES).toContain('revisions/SEG-1/diff');
    expect(SUB_READ_SEGMENTS).toContain('revisions');
  });
});

/*
 * THE PART IS NAMED IN THE PRODUCT'S WORDS, NOT THE BACKEND'S PATH VOCABULARY.
 *
 * The first version of this panel rendered the raw URL segment into the sentence a
 * scientist reads — "a read of “ingestion”", "a read of “evidence-classification”" —
 * which is the "backend-sourced jargon on product screens" class `CLAUDE.md` §11
 * records as still open. The remedy is `SUB_RESOURCE_LABELS`, and the objection to a
 * hand-maintained map is real: it rots the moment `api.ts` gains a sub-read. THIS is
 * the answer to that objection. The map is checked against the inventory derived
 * above from `api.ts` itself, so a new sub-read fails CI instead of leaking a wire
 * name into product copy.
 */
describe('SUB_RESOURCE_LABELS covers every sub-read api.ts builds', () => {
  it('has an entry for each first segment, and no entry for anything else', () => {
    expect(Object.keys(SUB_RESOURCE_LABELS).sort()).toEqual(SUB_READ_SEGMENTS);
  });

  it('names every part without leaking the wire segment or the path vocabulary', () => {
    for (const suffix of SUB_READ_SUFFIXES) {
      const segment = recordSubResource(`/experiments/EXP-1/${suffix}`)!;
      const label = SUB_RESOURCE_LABELS[segment];
      const lines = downCopy(
        new ApiError('x', { status: 404, path: `/experiments/EXP-1/${suffix}` }),
        true,
      ).lines.join(' ');
      expect(lines).toContain(label);
      // The quoted-verbatim form is reserved for a segment this build does NOT know.
      expect(lines).not.toContain(`“${segment}”`);
      // Body-copy register (register 2 — sentence case, so no leading capital), and
      // never a path fragment, a query parameter or a snake_case wire token.
      expect(label).not.toMatch(/^[A-Z]/);
      expect(label).not.toMatch(/[/?=_]/);
    }
  });

  it('an UNRECOGNISED segment is quoted verbatim, never given an invented name', () => {
    // A sub-read added to `api.ts` without an entry, or a path this client did not
    // shape. Honest jargon beats a fabricated friendly name — and the test above is
    // what keeps this fallback off the screens of real users.
    const lines = downCopy(
      new ApiError('x', { status: 404, path: '/experiments/EXP-1/not-a-real-part' }),
      true,
    ).lines.join(' ');
    expect(lines).toContain('“not-a-real-part”');
    expect(lines).toContain('does not establish that the experiment is missing');
  });
});

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
    // It names the part that WAS read, from the path — in the product's words, and
    // not by rendering the backend's `runs` path segment into the sentence.
    expect(body).toContain('the measurement runs');
    expect(body).not.toContain('“runs”');
  });

  it('THE REGRESSION: a source-preview 404 does not claim the experiment is missing', () => {
    const error = at('/experiments/EXP-1/source-preview?source=outside.csv', 'source_not_allowed');
    expect(assertsMissingRecord(bodyOf(error))).toBe(false);
    const lines = downCopy(error, false).lines.join(' ');
    // The query string is not mistaken for part of the segment. Asserted over the
    // COPY, not the whole panel: Technical Details reports the full request path by
    // design, and that row is pre-existing, correct, and credential-free.
    expect(lines).toContain('a reference source file');
    expect(lines).not.toContain('“source-preview”');
    expect(lines).not.toContain('outside.csv');
  });

  it('no sub-read of a record can produce the missing-record claim from its PATH alone', () => {
    // Every suffix `api.ts` builds under `/experiments/{id}`, derived from `api.ts`
    // itself rather than restated here — see the inventory block above.
    for (const suffix of SUB_READ_SUFFIXES) {
      const copy = downCopy(at(`/experiments/EXP-1/${suffix}`), true);
      expect(copy.kind).toBe('record_part_not_found');
      expect(assertsMissingRecord(copy.lines.join(' '))).toBe(false);
    }
    // Guard the guard: the list above must be sub-reads, not the record itself.
    expect(downCopy(at('/experiments/EXP-1'), true).kind).toBe('not_found');
  });

  /*
   * THE CASE A PATH-BASED FIX SILENTLY BREAKS, which is why the reason is read at
   * all. `api.getRecordBundle` (`api.ts:1136-1147`) awaits SEVEN experiment-scoped
   * reads in ONE `Promise.all` — the record itself plus `/draft`, `/pending`,
   * `/validate`, `/audit`, `/warnings`, `/evidence` — so six of the seven paths are
   * sub-resource paths. When the experiment really is absent all seven 404 and the
   * rejection that arrives is whichever landed first: a race. Narrowing the path
   * predicate alone would make the copy for one underlying truth depend on that race.
   * The reason does not.
   *
   * CORRECTION, kept visible rather than overwritten: an earlier revision of this
   * comment cited `getEvidenceBundle` awaiting `getExperiment(id)` and every
   * `getSourcePreview(id, file)` in one `Promise.all`. That was FALSE and is
   * withdrawn — `getEvidenceBundle` is two SEQUENTIAL `Promise.all`s
   * (`api.ts:1172-1180`), previews are fetched only after the first resolves, and on
   * a genuinely absent experiment `getSourcePreview` is never called. The behaviour
   * this test pins is unchanged; only the racing site named above is.
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

  /*
   * THE SECOND ARM OF THE PART SENTENCE — unreachable through `api.ts`, exercised
   * here so that "unreachable" is a claim about the client rather than about untested
   * code. A reason arm can be satisfied with no path (`downCopy` is exported and
   * pure); the copy must then say "one part of this experiment" and must NOT invent a
   * segment to fill the gap.
   */
  it('names no part when the path carried none, and invents none', () => {
    const copy = downCopy(new ApiError('x', { status: 404, reason: 'run_not_found' }), true);
    expect(copy.kind).toBe('record_part_not_found');
    const lines = copy.lines.join(' ');
    expect(lines).toContain('a read of one part of this experiment');
    expect(lines).not.toContain('“');
    expect(lines).not.toContain('the measurement runs');
    expect(assertsMissingRecord(lines)).toBe(false);
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

/*
 * THE REASON WIDENS WHERE THE RECORD CLAIM IS ALLOWED, NOT WHAT IT IS ALLOWED TO
 * DESCRIBE.
 *
 * "This experiment id is not in the workspace" is the most definitive sentence this
 * panel can say, and `isRecordPath` exists because it was once said over a LIST read.
 * Honouring `experiment_not_found` on a sub-resource path — which is the fix that
 * makes the copy race-independent — must not also make it sayable on a path that
 * names no experiment at all. Before the reason was plumbed through, a 404 on
 * `/memory/concepts/{id}`, `/graph/status` or `/schema` could not reach that sentence
 * by construction; the reason arm made it reachable, and this pins it shut again.
 *
 * LATENT, NOT LIVE. Every `_not_found(` call site in `routes.py` today is inside an
 * `/experiments/{experiment_id}` handler, so no current backend response can carry
 * this reason on one of those paths. That is a fact about the backend, not a property
 * of this component, and it is exactly the kind of fact that changes without anyone
 * revisiting the copy. `isRecordPath` is imported here so the boundary this asserts
 * is the same predicate the component branches on.
 */
describe('experiment_not_found is honoured only under /experiments/{id}', () => {
  const nonRecordPaths = [
    '/memory/concepts/CONC-1',
    '/graph/status',
    '/schema',
    '/experiments', // the collection read that started all of this
    '/runtime/records',
  ];

  it('renders the record claim on the record path and on its parts', () => {
    for (const path of ['/experiments/EXP-1', '/experiments/EXP-1/runs/RUN-1']) {
      const copy = downCopy(
        new ApiError('x', { status: 404, path, reason: 'experiment_not_found' }),
        true,
      );
      expect(copy.kind).toBe('not_found');
      expect(copy.lines.join(' ')).toContain('This experiment id is not in the workspace');
    }
  });

  it('never renders it on a path that names no experiment', () => {
    for (const path of nonRecordPaths) {
      // Precondition: these really are outside the predicate the claim rests on.
      expect(isRecordPath(path)).toBe(false);
      expect(recordSubResource(path)).toBeUndefined();
      const copy = downCopy(
        new ApiError('x', { status: 404, path, reason: 'experiment_not_found' }),
        true,
      );
      expect(copy.kind).toBe('path_not_found');
      const lines = copy.lines.join(' ');
      expect(lines).not.toMatch(/experiment id/i);
      expect(lines).not.toMatch(/may not have been created yet/i);
      expect(lines).toContain('answered HTTP 404 for this request');
    }
  });

  /*
   * THE ASYMMETRY WITH THE PART BRANCH, PINNED AND DISCLOSED RATHER THAN QUIETLY
   * LEFT — because it is a residual of this slice, not something it fixed.
   *
   * `run_not_found` / `source_not_allowed` are NOT path-constrained the way
   * `experiment_not_found` now is, so on one of these paths they still take the part
   * branch and its pathless sentence ("a read of one part of this experiment"). That
   * is deliberate for now, for one reason: the pathless sentence is the
   * anti-fabrication guard kept above, and constraining these arms too would make it
   * unreachable in principle and therefore dead.
   *
   * It is a WEAKER claim than the record branch's — it never says the experiment is
   * absent — and it is unreachable from `routes.py`, where both reasons are raised
   * only by handlers under `/experiments/{experiment_id}`. The invariant that
   * actually matters is asserted first; the `kind` is asserted second so that
   * narrowing these arms later is a LOUD change made on purpose, not a silent one.
   */
  it('a part-reason on those paths still refuses the missing-record claim', () => {
    for (const path of nonRecordPaths) {
      for (const reason of ['run_not_found', 'source_not_allowed']) {
        const copy = downCopy(new ApiError('x', { status: 404, path, reason }), true);
        const lines = copy.lines.join(' ');
        expect(lines).not.toMatch(/experiment id is not in the/i);
        expect(lines).not.toMatch(/may not have been created yet/i);
        // Current, deliberate behaviour — see the comment above before changing it.
        expect(copy.kind).toBe('record_part_not_found');
      }
    }
  });
});

/*
 * AN ENDED WORKED EXAMPLE IS NOT A RECORD THAT WAS NEVER CREATED.
 *
 * THE DEFECT. For one of the five built-in worked-example ids, "this experiment id
 * is not in the workspace — it may not have been created yet" is the wrong account
 * of what happened: that record WAS created, inside a worked-example session, and
 * the backend discarded the session's workspace when the walkthrough ended. The
 * hedge made it literally not-false and still left a scientist reading a
 * malfunction.
 *
 * WHY IT IS REACHABLE AT ALL. `useWorkspaceScopeChanged` is a DELTA detector, so a
 * COLD MOUNT in the ordinary workspace (`null` → `null`) is not a change and the
 * usual bounce to My Experiments cannot fire. `finishTutorial` + Back, and a pasted
 * or bookmarked example link, both land here.
 *
 * WHAT THESE TESTS PIN, in order of how load-bearing it is:
 *   1. the new copy is scoped to EXACTLY that case — example id AND no open
 *      walkthrough. An ordinary id keeps today's copy verbatim; the same example id
 *      inside a live session keeps it too;
 *   2. the copy does not claim the record exists, is retrievable, or can be
 *      restored;
 *   3. no request is made to find out — the whole decision is a build-time set
 *      membership test, so the backend is never asked to cross a scope.
 */
describe('an example-record 404 with no worked-example session open', () => {
  const EXAMPLE = EXAMPLE_RECORD_IDS[0];
  const ORDINARY = '01ARZ3NDEKTSV4RRFFQ69G5FAV';
  const missing = (path: string) =>
    new ApiError('x', { status: 404, path, reason: 'experiment_not_found' });

  it('explains the ended worked example instead of “may not have been created yet”', () => {
    const copy = downCopy(missing(`/experiments/${EXAMPLE}`), true, null);
    expect(copy.kind).toBe('example_workspace_ended');
    expect(copy.title).toBe('Worked Example Not Open');
    const lines = copy.lines.join(' ');
    expect(lines).toContain('one of the five built-in worked-example records');
    expect(lines).toContain('this browser tab is not in one');
    // The withdrawn explanation, in either build's wording.
    expect(lines).not.toMatch(/may not have been created yet/i);
    expect(lines).not.toMatch(/experiment id is not in the/i);
  });

  /*
   * THE SCOPE SIGNAL IS PER-TAB, SO THE COPY MAY NOT SPEAK FOR OTHER TABS.
   *
   * `scope === null` comes from `sessionStorage`, which dies with the tab. A reader
   * with the walkthrough open in tab A who opens a bookmarked example link in tab B
   * reaches this panel while their walkthrough is alive. An earlier revision told
   * that reader "none is open" and that the API had discarded "anything answered or
   * exported inside it" — a per-tab fact stated globally, which is the same defect
   * this panel exists to remove. These assertions pin the correction in BOTH
   * directions so it cannot regress to the confident wording.
   */
  it('does not speak for tabs it cannot see', () => {
    const lines = downCopy(missing(`/experiments/${EXAMPLE}`), true, null).lines.join(' ');
    // It must NOT assert a global absence…
    expect(lines).not.toMatch(/none is open/i);
    expect(lines).not.toMatch(/no worked.example is open\b/i);
    // …it must scope the claim to this tab…
    expect(lines).toContain('this browser tab is not in one');
    // …and it must name the still-open-elsewhere case rather than deny it.
    expect(lines).toMatch(/still open in another tab/i);
  });

  it('says the workspace is gone and promises no way back to it', () => {
    const lines = downCopy(missing(`/experiments/${EXAMPLE}`), true, null).lines.join(' ');
    // Honest about the loss, conditioned on the walkthrough actually having ended…
    expect(lines).toMatch(/when that walkthrough ends the ISAAC API discards it/i);
    expect(lines).toContain('anything answered or exported inside it');
    expect(lines).toContain('this page cannot reach it');
    // …and explicit that a replay is a new start, not a way back.
    expect(lines).toContain('not a way back into an earlier one');
    // No claim that the record is still there or retrievable.
    expect(lines).not.toMatch(/still (exists|available)|try again later|restore your/i);
  });

  it('applies on a sub-resource path too, because the bundle read is a race', () => {
    // `getRecordBundle` fires seven reads at once; whichever rejects first reaches
    // the panel. The explanation must not depend on which one won.
    const copy = downCopy(missing(`/experiments/${EXAMPLE}/draft`), true, null);
    expect(copy.kind).toBe('example_workspace_ended');
  });

  it('leaves an ordinary missing id on today’s copy, unchanged', () => {
    const copy = downCopy(missing(`/experiments/${ORDINARY}`), true, null);
    expect(copy.kind).toBe('not_found');
    expect(copy.title).toBe('Record Not Found');
    expect(copy.lines).toEqual([
      'This experiment id is not in the workspace — it may not have been created yet.',
    ]);
    expect(copy.offerExperimentsLink).toBe(false);
    // and the local build's wording is likewise untouched
    expect(downCopy(missing(`/experiments/${ORDINARY}`), false, null).lines).toEqual([
      'This experiment id is not in the local workspace — it may not have been created yet.',
    ]);
  });

  it('leaves an example id INSIDE a live session on today’s copy', () => {
    // A 404 for an example id while a walkthrough IS open is a different fact —
    // that session really does not hold it — and this branch must not speak for it.
    const copy = downCopy(missing(`/experiments/${EXAMPLE}`), true, 'sess-abc');
    expect(copy.kind).toBe('not_found');
  });

  it('does not fire when the caller supplied no scope at all', () => {
    // Omission is fail-safe: an unaware caller keeps today's copy rather than
    // gaining a claim it never supplied evidence for.
    expect(downCopy(missing(`/experiments/${EXAMPLE}`), true).kind).toBe('not_found');
  });

  it('does not weaken the tutorial_session_not_found discrimination', () => {
    // That reason is raised by the scope dependency BEFORE any record work, so it is
    // evidence about a dead session and none about the record. It must keep falling
    // through to the generic branch even for an example id — this branch is reached
    // only from `experiment_not_found` (or from no reason at all on a bare record
    // path), never from a dead-session 404.
    const copy = downCopy(
      new ApiError('x', {
        status: 404,
        path: `/experiments/${EXAMPLE}`,
        reason: 'tutorial_session_not_found',
      }),
      true,
      null,
    );
    expect(copy.kind).toBe('path_not_found');
    expect(copy.lines.join(' ')).not.toMatch(/worked-example|may not have been created yet/i);
  });

  it('decides without issuing any request', () => {
    const original = globalThis.fetch;
    globalThis.fetch = (() => {
      throw new Error('downCopy must never fetch');
    }) as typeof fetch;
    try {
      expect(downCopy(missing(`/experiments/${EXAMPLE}`), true, null).kind).toBe(
        'example_workspace_ended',
      );
    } finally {
      globalThis.fetch = original;
    }
  });

  it('offers My Experiments as a keyboard-operable link, inside a router', () => {
    const view = render(
      <MemoryRouter>
        <BackendDown error={missing(`/experiments/${EXAMPLE}`)} />
      </MemoryRouter>,
    );
    const link = view.getByRole('link', { name: 'My Experiments' });
    expect(link).toHaveAttribute('href', '/experiments');
    // A real link: reachable and activatable by keyboard with no handler of ours.
    link.focus();
    expect(document.activeElement).toBe(link);
    // No reload is offered — reloading renders exactly this panel again.
    expect(view.queryByRole('button', { name: 'Reload' })).toBeNull();
  });

  it('names the panel by its title for assistive technology', () => {
    const view = render(
      <MemoryRouter>
        <BackendDown error={missing(`/experiments/${EXAMPLE}`)} />
      </MemoryRouter>,
    );
    expect(view.getByRole('alert', { name: 'Worked Example Not Open' })).toBeInTheDocument();
  });

  it('renders the explanation, minus the link, with no router present', () => {
    // `BackendDown` is unit-rendered bare in this very file. A failure state that
    // crashed the page it is explaining would be the worst possible regression.
    const view = render(<BackendDown error={missing(`/experiments/${EXAMPLE}`)} />);
    expect(view.getByText('Worked Example Not Open')).toBeInTheDocument();
    expect(view.queryByRole('link', { name: 'My Experiments' })).toBeNull();
    // The walkthrough's home is still named in words, so nothing is lost.
    expect(view.container.textContent).toContain('Settings & API → Help & Tutorial');
  });
});
