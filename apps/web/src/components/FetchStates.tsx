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
import { useEffect, useRef, useState } from 'react';
import { AudioWaveform, Check, Copy, TriangleAlert } from './icons';
import { API_BASE, isHostedBuild, RUN_COMMAND } from '../lib/api';
import type { ApiError } from '../lib/api';
import { LABELS } from '../lib/labels';
import {
  buildContext,
  buildDiagnosticsReport,
  collectBrowserContext,
  diagnosticsFailureFrom,
  type DiagnosticsApp,
  type DiagnosticsMemory,
} from '../lib/diagnostics';

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
      {/* The SAME control and the SAME generator the Settings → About mount uses.
          `app` / `memory` are deliberately omitted: the request that produced
          this error is the evidence that server-derived facts are not available
          right now, so those rows say so rather than showing a stale value. */}
      <CopyDiagnostics
        build={() =>
          buildDiagnosticsReport({
            generatedAt: new Date(),
            ...buildContext(),
            location: { route: currentRoute() },
            browser: collectBrowserContext(),
            failure: diagnosticsFailureFrom(error),
          })
        }
      />
    </details>
  );
}

/**
 * The reader's current pathname.
 *
 * Read from `window.location` rather than the router, because `BackendDown`
 * renders from 14 call sites including the ⌘K dialog, and a router hook here
 * would make the failure state depend on a provider being present — exactly the
 * kind of coupling that turns one broken fetch into a blank page. Guarded, so a
 * non-browser environment yields the honest placeholder instead of throwing.
 */
function currentRoute(): string {
  try {
    return window.location.pathname;
  } catch {
    return 'not available';
  }
}

/**
 * COPY DIAGNOSTICS — one compact, secondary control, mounted twice.
 *
 * BEHAVIOUR CONTRACT, in the order it matters:
 *
 *  1. NOTHING HAPPENS UNTIL ASKED. The report is generated inside the click
 *     handler, never at render, so no clipboard write, no measurement and no
 *     state change occurs from merely displaying the control. That also means
 *     the timestamp and viewport describe the moment of activation.
 *  2. NO NETWORK. There is no fetch, no beacon and no telemetry on this path;
 *     the string goes to the reader's clipboard or to the page, nowhere else.
 *  3. THE FAILURE PATH IS A FEATURE, NOT AN EXCUSE. `navigator.clipboard` is
 *     unavailable over plain HTTP, in cross-origin frames and under some
 *     permission policies, and `writeText` can reject even when it exists. Both
 *     cases render the report as focusable, selectable text so the reader can
 *     still copy it by hand — the deliverable is the report, not the clipboard.
 *  4. SUCCESS IS ANNOUNCED, NOT COLOURED. A persistent `role="status"` region
 *     (present from first render, so the update is announced rather than the
 *     region's arrival) carries the outcome as words; the visible signal is the
 *     button's own LABEL changing, not a tint.
 *
 * `build` is a thunk rather than a string for reason 1.
 */
export function CopyDiagnostics({ build }: { build: () => string }) {
  const [outcome, setOutcome] = useState<'idle' | 'copied' | 'manual'>('idle');
  const [report, setReport] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const manualRef = useRef<HTMLPreElement | null>(null);

  // On the manual path the reader has to select the text, so the block is given
  // focus and pre-selected — otherwise a keyboard user is handed a wall of text
  // with no way to reach it. Both APIs are guarded: jsdom and older engines
  // implement selection partially.
  useEffect(() => {
    if (outcome !== 'manual') return;
    const node = manualRef.current;
    if (!node) return;
    try {
      node.focus();
      const selection = window.getSelection?.();
      const range = document.createRange?.();
      if (selection && range) {
        range.selectNodeContents(node);
        selection.removeAllRanges();
        selection.addRange(range);
      }
    } catch {
      /* selection unsupported — the text is still selectable by hand */
    }
  }, [outcome]);

  function toManual(text: string) {
    setReport(text);
    setOutcome('manual');
    setMessage(
      'Clipboard access is unavailable in this browser, so the diagnostics report is shown below as selectable text. Select it and copy it manually.',
    );
  }

  async function activate() {
    const text = build();
    const clipboard = navigator.clipboard;
    if (typeof clipboard?.writeText !== 'function') {
      toManual(text);
      return;
    }
    try {
      await clipboard.writeText(text);
      setReport(text);
      setOutcome('copied');
      setMessage('Diagnostics report copied to the clipboard.');
    } catch {
      toManual(text);
    }
  }

  return (
    <div className="fetch-state-diagnostics">
      <button
        type="button"
        className="fetch-state-diagnostics-btn"
        onClick={() => {
          void activate();
        }}
      >
        {outcome === 'copied' ? (
          <Check size={12} strokeWidth={2.4} aria-hidden="true" />
        ) : (
          <Copy size={12} strokeWidth={2} aria-hidden="true" />
        )}
        {outcome === 'copied' ? 'Diagnostics Copied' : 'Copy Diagnostics'}
      </button>
      <p className="fetch-state-diagnostics-note">
        Copies this build&rsquo;s version, route, viewport and Project Memory provenance as text you
        can paste into a bug report. Nothing is uploaded.
      </p>
      {/* Present from first render so a change to its text is what gets
          announced — a live region that appears WITH its message is unreliable. */}
      <p className="sr-only" role="status">
        {message}
      </p>
      {outcome === 'manual' && report !== null && (
        <>
          <p className="fetch-state-diagnostics-fallback">{message}</p>
          <pre
            ref={manualRef}
            className="fetch-state-diagnostics-block mono"
            tabIndex={0}
            aria-label="Diagnostics report — selectable text"
          >
            {report}
          </pre>
        </>
      )}
    </div>
  );
}

/**
 * The normal-state diagnostics box — the SECOND mount, for when nothing is
 * broken. Renders the same control over the same generator, with the
 * server-derived facts the host surface already holds.
 *
 * Exported from this module rather than authored again on Settings, because the
 * whole point of the extension was ONE diagnostics system: if a field is added
 * to the report it appears on both surfaces, and if the privacy boundary is
 * tightened it tightens in both places.
 */
export function DiagnosticsPanel({
  app,
  memory,
  route,
  tab,
}: {
  app?: DiagnosticsApp | null;
  memory?: DiagnosticsMemory | null;
  route?: string;
  tab?: string | null;
}) {
  return (
    <CopyDiagnostics
      build={() =>
        buildDiagnosticsReport({
          generatedAt: new Date(),
          ...buildContext(),
          location: { route: route ?? currentRoute(), tab: tab ?? null },
          browser: collectBrowserContext(),
          app,
          memory,
        })
      }
    />
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
