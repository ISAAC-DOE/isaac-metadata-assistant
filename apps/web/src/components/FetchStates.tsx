/*
 * Shared fetch states — the loading panel and the ONE honest failure state.
 *
 * `BackendDown` is rendered from 14 call sites, so its copy is the copy the
 * whole app shows when anything server-derived fails. Hosted QA caught it
 * telling a hosted user to start a server on their laptop, for a failure that
 * was actually an expired sign-in session.
 *
 * The rule this module encodes: BE SPECIFIC WHERE THE CAUSE IS OBSERVABLE, AND
 * GENERIC WHERE IT IS NOT. `ApiError` carries the observable signals (an HTTP
 * status, a network-level failure, an HTML intercept on an API path) and
 * `downCopy` maps them to copy that claims only what those signals support.
 * Replacing "the backend is down" with an equally confident "your session
 * expired" would be the same defect wearing different words.
 */

import './fetchstates.css';
import { AudioWaveform, TriangleAlert } from './icons';
import { API_BASE, isHostedBuild, RUN_COMMAND } from '../lib/api';
import type { ApiError } from '../lib/api';
import { LABELS } from '../lib/labels';

/** Calm inline loading state — a processing dot + a label. */
export function LoadingPanel({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="fetch-state" role="status" aria-live="polite">
      <span className="dot dot-processing" aria-hidden="true" />
      <span className="fetch-state-label">{label}</span>
    </div>
  );
}

/**
 * Which failure this is, from the observable signals only.
 *
 * - `not_found`  — HTTP 404: the record is not there. Unchanged behaviour.
 * - `auth`       — HTTP 401/403, or an HTML page served for an API path. The
 *                  session is no longer authenticated/authorized; a reload
 *                  re-enters the identity flow.
 * - `http_error` — a hosted build got SOME other status: the API was reached
 *                  and answered, so "could not be reached" would be false.
 * - `unreachable`— a hosted build's request never completed. Two plausible
 *                  causes (ended session vs. unavailable service) and NO
 *                  signal that separates them, so neither is asserted.
 * - `local`      — a local build. Today's copy and the run command, unchanged:
 *                  there the "start the backend" instruction is actionable.
 */
export type DownKind = 'not_found' | 'auth' | 'http_error' | 'unreachable' | 'local';

export interface DownCopy {
  kind: DownKind;
  title: string;
  /** Body sentences, in order; each renders as its own paragraph. */
  lines: string[];
  /** Local builds only — the run command is the actionable remedy there. */
  showRunCommand: boolean;
  /** Whether reloading (re-entering the identity flow) is offered. */
  offerReload: boolean;
}

/**
 * Classify + phrase a failure. Exported and pure so both render sites (this
 * panel and the ⌘K search dialog) share ONE source of copy and cannot drift.
 *
 * `hosted` is injectable only so tests can exercise a hosted build without a
 * separate bundle; production always uses the compile-time `isHostedBuild`.
 */
export function downCopy(error?: ApiError, hosted: boolean = isHostedBuild): DownCopy {
  const status = error?.status;

  if (status === 404) {
    return {
      kind: 'not_found',
      title: 'Record Not Found',
      lines: [
        hosted
          ? 'This experiment id is not in the workspace — it may not have been created yet.'
          : 'This experiment id is not in the local workspace — it may not have been created yet.',
      ],
      showRunCommand: false,
      offerReload: false,
    };
  }

  if (status === 401 || status === 403 || error?.htmlIntercept === true) {
    // Each first line states the signal actually observed, not a shared guess.
    const cause =
      error?.htmlIntercept === true
        ? 'A sign-in page was returned in place of the ISAAC API, so the request never reached it. That happens when a session has ended.'
        : status === 401
          ? 'The ISAAC API rejected this request as unauthenticated (HTTP 401). The sign-in session is no longer valid.'
          : 'The ISAAC API refused this request as unauthorized (HTTP 403). The sign-in session is no longer permitted to read it.';
    return {
      kind: 'auth',
      title: 'Sign-In Required',
      lines: [
        cause,
        'Reload the page to sign in again.',
        'This prototype reads only server-derived truth — it will never show placeholder data.',
      ],
      showRunCommand: false,
      offerReload: true,
    };
  }

  if (!hosted) {
    return {
      kind: 'local',
      title: 'Backend Not Running',
      lines: [
        'The local ISAAC API is not responding. This prototype reads only server-derived truth — it will never show placeholder data. Start the backend, then retry:',
      ],
      showRunCommand: true,
      offerReload: false,
    };
  }

  if (status !== undefined) {
    return {
      kind: 'http_error',
      title: 'ISAAC Returned an Error',
      lines: [
        `The ISAAC API was reached but answered with HTTP ${status}, so this view has no server-derived data to show.`,
        'This prototype reads only server-derived truth — it will never show placeholder data.',
      ],
      showRunCommand: false,
      offerReload: false,
    };
  }

  return {
    kind: 'unreachable',
    title: 'ISAAC Is Not Responding',
    lines: [
      'The ISAAC API could not be reached. This page cannot tell which of two causes applies: the sign-in session may have ended, or the service may be temporarily unavailable.',
      'Reload the page — that restores the session if it had ended, and is harmless if it had not.',
      'This prototype reads only server-derived truth — it will never show placeholder data.',
    ],
    showRunCommand: false,
    offerReload: true,
  };
}

/** Re-request the page, which re-enters the identity flow when a session ended. */
function reloadPage() {
  window.location.reload();
}

/**
 * The ISAAC mark, PRESENTATIONAL. Deliberately not a `Link`: when the API is
 * unreachable no navigation can help, and a link that leads to another broken
 * surface is a small lie. Same visual language as the TopBar brand (the shared
 * `.brand-tile` + the wordmark), so the failure still looks like ISAAC.
 */
function DownBrand() {
  return (
    <div className="fetch-state-brand">
      <span className="brand-tile" aria-hidden="true">
        <AudioWaveform size={17} strokeWidth={2.2} />
      </span>
      <span className="fetch-state-brand-name">{LABELS.brand}</span>
    </div>
  );
}

/**
 * Observable facts only, in the repo's collapsed `Technical Details` pattern
 * (see Settings / Concepts / Graph Help) — a `<details>`, keyboard-operable and
 * announced, kept in its own bordered box below the message.
 *
 * SECURITY: every row below is a value this module derives from the RESPONSE or
 * from the build config. The `Authorization` header, `VITE_API_KEY`, tokens and
 * cookies are never read here, never passed in, and never logged. `error.path`
 * is safe by construction — this client sends credentials as a header and never
 * places one in a URL.
 */
export function DownTechnicalDetails({ error }: { error: ApiError }) {
  const rows: { label: string; value: string }[] = [
    {
      label: 'HTTP Status',
      value:
        error.status !== undefined
          ? String(error.status)
          : 'no HTTP status — the request did not complete',
    },
    {
      label: 'Network-Level Failure',
      value: error.unreachable ? 'yes — the request did not complete' : 'no',
    },
    {
      label: 'HTML Intercept',
      value: error.htmlIntercept
        ? 'yes — an API path answered with HTML'
        : 'no — not detected',
    },
    { label: 'Response Content-Type', value: error.contentType ?? 'not reported' },
    { label: 'API Base', value: API_BASE },
    { label: 'Build Mode', value: isHostedBuild ? 'hosted' : 'local' },
    { label: 'Request Path', value: error.path ?? 'not recorded' },
  ];
  return (
    <details className="fetch-state-technical">
      <summary>Technical Details</summary>
      <dl className="fetch-state-technical-figures">
        {rows.map((row) => (
          <div className="fetch-state-technical-figure" key={row.label}>
            <dt>{row.label}</dt>
            <dd className="mono">{row.value}</dd>
          </div>
        ))}
      </dl>
      <p className="fetch-state-technical-note">
        Observed values only. No credential, token, cookie or request header is shown here or
        recorded anywhere.
      </p>
    </details>
  );
}

/**
 * The honest failure state. It never fabricates data and never asserts a cause
 * the response did not evidence — see `downCopy` for the branch table.
 */
export function BackendDown({ error, onRetry }: { error?: ApiError; onRetry?: () => void }) {
  const copy = downCopy(error);
  return (
    <div className="fetch-state error" role="alert">
      <span className="fetch-state-icon" aria-hidden="true">
        <TriangleAlert size={22} strokeWidth={2.2} />
      </span>
      <div className="fetch-state-body">
        <DownBrand />
        <h2 className="fetch-state-title">{copy.title}</h2>
        {copy.lines.map((line) => (
          <p className="fetch-state-text" key={line}>
            {line}
          </p>
        ))}
        {/* The `!isHostedBuild` guard is redundant at runtime (only the `local`
            kind sets showRunCommand) and load-bearing at BUILD time: it is a
            compile-time literal, so a hosted bundle drops this branch — and
            with it RUN_COMMAND — entirely. */}
        {!isHostedBuild && copy.showRunCommand && (
          <pre className="fetch-state-cmd mono">{RUN_COMMAND}</pre>
        )}
        {(copy.offerReload || onRetry) && (
          <div className="fetch-state-actions">
            {copy.offerReload && (
              <button type="button" className="btn btn-primary" onClick={reloadPage}>
                Reload
              </button>
            )}
            {onRetry && (
              <button type="button" className="btn btn-secondary" onClick={onRetry}>
                Retry
              </button>
            )}
          </div>
        )}
        {error && <DownTechnicalDetails error={error} />}
      </div>
    </div>
  );
}
