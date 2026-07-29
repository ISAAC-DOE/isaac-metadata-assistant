/*
 * The diagnostics report — ONE pure generator, two render sites.
 *
 * WHY IT EXISTS. When someone reports "the hosted app is broken", the useful
 * facts are the ones only their browser knows: which build they loaded, which
 * route they were on, what size their viewport is, whether the page thought it
 * was online. Asking for them one at a time over Slack is slow and lossy. This
 * module turns them into one pasteable block.
 *
 * WHY IT IS A PURE FUNCTION. `buildDiagnosticsReport` takes every value as an
 * argument and returns a string. It reads no global, touches no `window`, calls
 * no API and consults no clock, so a test can pin the exact bytes it emits — and
 * so the redaction guarantee below is a property of a function, not of a
 * component's incidental behaviour. The two impure steps are separate and small:
 * `collectBrowserContext()` reads the four browser measurements, and the mounts
 * pass in whatever server-derived facts they already hold.
 *
 * THE PRIVACY BOUNDARY, stated as an invariant. Every field is either a build
 * constant, a server-derived non-sensitive value from `GET /api/about` or
 * `GET /api/graph/status`, or a browser measurement. This module NEVER reads
 * `document.cookie`, `localStorage`, `sessionStorage`, any `Authorization`
 * header, `import.meta.env.VITE_API_KEY`, the Assistant transcript, record field
 * values, uploaded content, or a network payload — there is no code path here
 * that could, because nothing is read: everything arrives as a typed argument.
 *
 * The one argument that could carry anything is a failing request's signals, so
 * `DiagnosticsFailure` models the five OBSERVABLE signals `ApiError` exposes and
 * deliberately has no `body` field. `ApiError.body` is typed `unknown` and is
 * populated from a response body the app does not control (see `lib/api.ts`), so
 * it is excluded by the type, not by a runtime filter — `diagnosticsFailureFrom`
 * cannot pass it on, and `DownTechnicalDetails` omits it for the same reason.
 *
 * NO NETWORK, EVER. Generating or copying a report performs no request and
 * records nothing. There is no telemetry here and nothing is uploaded; the string
 * goes to the clipboard the reader explicitly asked for, or to the page as
 * selectable text if that fails.
 *
 * ON BROWSER ZOOM — deliberately absent. There is no reliable way to measure it:
 * `devicePixelRatio` conflates page zoom with display density and OS scaling (a
 * Retina display at 100% reads 2, the same as a 1x display at 200%), and
 * `visualViewport.scale` reports pinch-zoom only, staying at 1 through desktop
 * page zoom. Reporting either as "zoom" would be a plausible-looking guess, so
 * the field is omitted and the raw, honest `devicePixelRatio` is reported under
 * its own name instead.
 */

import { API_BASE, isHostedBuild } from './api';
import type { ApiError } from './api';
import { ENVIRONMENT_LABEL } from './runtimeContext';
import type { ApiAboutResponse, ApiGraphStatus } from './types';

/**
 * The one placeholder for a value that was not obtainable. Always this exact
 * string, never a zero, an empty cell or a plausible-looking default — a reader
 * pasting the report must be able to tell "we could not read this" apart from
 * "this is the value".
 */
export const NOT_AVAILABLE = 'not available';

/** Server-derived build identity, from `GET /api/about`. */
export interface DiagnosticsApp {
  appVersion: string;
  /** Full SHA, or `null` when no build identity was injected. */
  buildCommit: string | null;
  runtimeMode: string;
  recordSchemaVersion: string;
  dataRegime: string;
  persistence: string;
}

/**
 * Memory-plane provenance, from `GET /api/graph/status` — the cheap
 * provider-agnostic status endpoint, NOT the graph payload.
 *
 * ON THE SINGLE SOURCE COMMIT. `source_graph_commit` IS the memory graph's own
 * `built_at_commit` (see `apps/api/isaac_api/memory.py`, where the reader sets
 * `"source_graph_commit": state.built_at_commit`), so "the Project Memory source
 * commit" and "the graph source commit" are one value here, reported once rather
 * than twice under two labels. The symbol-level artifact
 * (`memory-graph-detail.json`) carries a `built_at_commit` of its own, but it is
 * only reachable through the ~0.5 MB deep graph payload, which this box
 * deliberately does not fetch; it is therefore not reported at all rather than
 * reported as an unexplained blank.
 */
export interface DiagnosticsMemory {
  availability: string;
  integrity: string;
  provider: string;
  /** The graph's `built_at_commit`, as the status endpoint reports it. */
  sourceCommit: string | null;
  /** `served_manifest_fingerprint` — the served-CONTENT drift-detection basis. */
  snapshotFingerprint: string | null;
  policyFingerprint: string | null;
  servedFileCount: number | null;
  snapshotSchemaVersion: number | null;
}

/** The four browser measurements, read by {@link collectBrowserContext}. */
export interface DiagnosticsBrowser {
  userAgent: string | null;
  viewportWidth: number | null;
  viewportHeight: number | null;
  devicePixelRatio: number | null;
  /** `navigator.onLine` — what the BROWSER believes, never a verified reachability claim. */
  online: boolean | null;
}

/** Where in the app the reader is. `route` is a pathname; it carries no query string. */
export interface DiagnosticsLocation {
  route: string;
  /** The active local page tab (Settings / Governance / Project Memory), when one applies. */
  tab?: string | null;
}

/**
 * A failing request's OBSERVABLE signals — the same five `DownTechnicalDetails`
 * renders. There is deliberately no `body`: see the module header.
 */
export interface DiagnosticsFailure {
  status?: number;
  unreachable?: boolean;
  htmlIntercept?: boolean;
  contentType?: string | null;
  path?: string | null;
}

export interface DiagnosticsInput {
  /** Injected so the generator stays pure; the mounts pass `new Date()` at activation. */
  generatedAt: Date;
  /** The compiled-in API base — reuse `API_BASE`, never a re-derived string. */
  apiBase: string;
  /** The environment name from `lib/runtimeContext.ts` — the ONE naming mechanism. */
  deployment: string;
  location: DiagnosticsLocation;
  browser: DiagnosticsBrowser;
  /** Absent when `GET /api/about` has not answered (e.g. the failure box). */
  app?: DiagnosticsApp | null;
  /** Absent when `GET /api/graph/status` has not answered. */
  memory?: DiagnosticsMemory | null;
  /** Present only on the failure mount. */
  failure?: DiagnosticsFailure | null;
}

// --- mappers (pure; the wire shapes in, the report shapes out) ---------------

export function diagnosticsAppFrom(about: ApiAboutResponse): DiagnosticsApp {
  return {
    appVersion: about.app_version,
    buildCommit: about.build_commit,
    runtimeMode: about.runtime_mode,
    recordSchemaVersion: about.record_schema_version,
    dataRegime: about.data_regime,
    persistence: about.persistence,
  };
}

export function diagnosticsMemoryFrom(status: ApiGraphStatus): DiagnosticsMemory {
  return {
    availability: status.availability,
    integrity: status.integrity,
    provider: status.provider,
    sourceCommit: status.source_graph_commit,
    snapshotFingerprint: status.served_manifest_fingerprint,
    policyFingerprint: status.policy_fingerprint,
    servedFileCount: status.served_file_count,
    snapshotSchemaVersion: status.snapshot_schema_version,
  };
}

/**
 * The five observable signals off an `ApiError`.
 *
 * `body` is NOT copied across — the return type has no such field, so no future
 * edit can add one without changing {@link DiagnosticsFailure} on purpose.
 */
export function diagnosticsFailureFrom(error: ApiError): DiagnosticsFailure {
  return {
    status: error.status,
    unreachable: error.unreachable,
    htmlIntercept: error.htmlIntercept,
    contentType: error.contentType ?? null,
    path: error.path ?? null,
  };
}

// --- browser context (the ONE impure step) ----------------------------------

/**
 * Read the browser measurements. Every read is guarded, because a report that
 * throws while someone is diagnosing a failure is worse than one missing a row;
 * anything unreadable becomes `null` and renders as {@link NOT_AVAILABLE}.
 */
export function collectBrowserContext(): DiagnosticsBrowser {
  const win: Window | undefined = typeof window === 'undefined' ? undefined : window;
  const nav = typeof navigator === 'undefined' ? undefined : navigator;
  const num = (value: unknown): number | null =>
    typeof value === 'number' && Number.isFinite(value) ? value : null;
  return {
    userAgent: typeof nav?.userAgent === 'string' && nav.userAgent !== '' ? nav.userAgent : null,
    viewportWidth: num(win?.innerWidth),
    viewportHeight: num(win?.innerHeight),
    devicePixelRatio: num(win?.devicePixelRatio),
    online: typeof nav?.onLine === 'boolean' ? nav.onLine : null,
  };
}

/** The build-derived half of the input, so neither mount re-derives it. */
export function buildContext(): { apiBase: string; deployment: string; hosted: boolean } {
  return { apiBase: API_BASE, deployment: ENVIRONMENT_LABEL, hosted: isHostedBuild };
}

// --- derivations (pure) -----------------------------------------------------

/** The conventional 12-character short SHA; never pads, never truncates shorter. */
export function shortSha(commit: string): string {
  return commit.length > 12 ? commit.slice(0, 12) : commit;
}

/**
 * The record id from a route, or `null`.
 *
 * Matches `/record/<id>` ANYWHERE in the pathname so a deployment served under
 * a base path (`/krish/record/…`) is handled by the same expression, and so the
 * record sub-surfaces (`/record/<id>/evidence`) resolve to the same id. A route
 * with no record segment returns `null` — the report then says "not applicable"
 * rather than inventing an id.
 */
export function recordIdFromRoute(route: string): string | null {
  const match = /(?:^|\/)record\/([^/?#]+)/.exec(route);
  if (!match) return null;
  const id = decodeURIComponent(match[1]);
  return id === '' ? null : id;
}

const BROWSER_TOKENS: { name: string; pattern: RegExp }[] = [
  // Order matters: Edge and Opera both advertise `Chrome`, and Chrome
  // advertises `Safari`, so the most specific token has to win.
  { name: 'Edge', pattern: /Edg(?:e|A|iOS)?\/(\d+)/ },
  { name: 'Opera', pattern: /OPR\/(\d+)/ },
  { name: 'Samsung Internet', pattern: /SamsungBrowser\/(\d+)/ },
  { name: 'Firefox', pattern: /(?:Firefox|FxiOS)\/(\d+)/ },
  { name: 'Chrome', pattern: /(?:Chrome|CriOS)\/(\d+)/ },
  { name: 'Safari', pattern: /Version\/(\d+).*Safari\// },
];

const OS_TOKENS: { name: string; pattern: RegExp }[] = [
  { name: 'iOS', pattern: /iPhone|iPad|iPod/ },
  { name: 'Android', pattern: /Android/ },
  { name: 'macOS', pattern: /Mac OS X|Macintosh/ },
  { name: 'Windows', pattern: /Windows NT/ },
  { name: 'Linux', pattern: /Linux/ },
];

/**
 * A CONCISE browser identification — engine family, major version and OS
 * family, e.g. `Chrome 130 on macOS`.
 *
 * Deliberately not the raw user-agent string: that is long, near-unreadable in a
 * pasted report, and carries more device detail than a diagnostic needs. When no
 * token matches, the raw string is reported (clipped) rather than guessed at —
 * an unrecognised browser is exactly the case where the raw value is the useful
 * one.
 */
export function summarizeBrowser(userAgent: string | null): string {
  if (userAgent === null || userAgent.trim() === '') return NOT_AVAILABLE;
  const ua = userAgent.trim();
  const os = OS_TOKENS.find((entry) => entry.pattern.test(ua))?.name ?? null;
  const browser = BROWSER_TOKENS.map((entry) => {
    const match = entry.pattern.exec(ua);
    return match ? `${entry.name} ${match[1]}` : null;
  }).find((value): value is string => value !== null);
  if (browser === null || browser === undefined) {
    const clipped = ua.length > 120 ? `${ua.slice(0, 120)}…` : ua;
    return os === null ? `unrecognised (${clipped})` : `unrecognised on ${os} (${clipped})`;
  }
  return os === null ? browser : `${browser} on ${os}`;
}

// --- formatting -------------------------------------------------------------

/** Longest label, so every value in the fenced block starts at one column. */
const LABEL_WIDTH = 24;

/**
 * Render one value defensively: server-derived strings are collapsed to a single
 * line and clipped, so no value can inject a line into the report's structure or
 * turn a paste into a wall of text.
 */
function renderValue(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined) return NOT_AVAILABLE;
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : NOT_AVAILABLE;
  const flat = value.replace(/\s+/g, ' ').trim();
  if (flat === '') return NOT_AVAILABLE;
  return flat.length > 200 ? `${flat.slice(0, 200)}…` : flat;
}

interface Row {
  label: string;
  value: string | number | boolean | null | undefined;
}

interface Group {
  title: string;
  rows: Row[];
}

function renderGroup(group: Group): string {
  const lines = group.rows.map(
    (row) => `  ${row.label.padEnd(LABEL_WIDTH)}${renderValue(row.value)}`,
  );
  return [group.title, ...lines].join('\n');
}

/** The report's stable first line — what a reader searches for in a thread. */
export const DIAGNOSTICS_HEADING = '### ISAAC Diagnostics';

/**
 * Build the pasteable report.
 *
 * FORMAT. A markdown heading followed by a fenced block. The fence is what makes
 * one string work in both targets a reader actually uses: GitHub renders it as a
 * preserved-whitespace code block, and Slack renders it as a code block too, so
 * the aligned columns survive a paste into either without reflowing.
 */
export function buildDiagnosticsReport(input: DiagnosticsInput): string {
  const { app, memory, browser, location, failure } = input;
  const recordId = recordIdFromRoute(location.route);

  const groups: Group[] = [
    {
      title: 'BUILD',
      rows: [
        { label: 'App Version', value: app?.appVersion },
        {
          label: 'Build Commit (Short)',
          value: app?.buildCommit == null ? null : shortSha(app.buildCommit),
        },
        { label: 'Build Commit (Full)', value: app?.buildCommit },
        { label: 'Runtime Mode', value: app?.runtimeMode },
        { label: 'Data Regime', value: app?.dataRegime },
        { label: 'Persistence', value: app?.persistence },
        { label: 'Record Schema', value: app?.recordSchemaVersion },
        { label: 'Deployment', value: input.deployment },
        { label: 'API Base', value: input.apiBase },
      ],
    },
    {
      title: 'SESSION',
      rows: [
        { label: 'Generated At', value: input.generatedAt.toISOString() },
        { label: 'Route', value: location.route },
        { label: 'Tab', value: location.tab ?? 'not applicable' },
        { label: 'Record Id', value: recordId ?? 'not applicable' },
        { label: 'Browser', value: summarizeBrowser(browser.userAgent) },
        {
          label: 'Viewport',
          value:
            browser.viewportWidth == null || browser.viewportHeight == null
              ? null
              : `${browser.viewportWidth} x ${browser.viewportHeight} px`,
        },
        { label: 'Device Pixel Ratio', value: browser.devicePixelRatio },
        {
          label: 'Network State',
          value:
            browser.online == null
              ? null
              : browser.online
                ? 'the browser reports online'
                : 'the browser reports offline',
        },
      ],
    },
    {
      title: 'PROJECT MEMORY',
      rows: [
        { label: 'Availability', value: memory?.availability },
        { label: 'Integrity', value: memory?.integrity },
        { label: 'Provider', value: memory?.provider },
        { label: 'Source Commit', value: memory?.sourceCommit },
        { label: 'Snapshot Fingerprint', value: memory?.snapshotFingerprint },
        { label: 'Policy Fingerprint', value: memory?.policyFingerprint },
        { label: 'Served File Count', value: memory?.servedFileCount },
        { label: 'Snapshot Schema', value: memory?.snapshotSchemaVersion },
      ],
    },
  ];

  if (failure) {
    groups.push({
      title: 'FAILURE SIGNALS',
      rows: [
        {
          label: 'HTTP Status',
          value: failure.status == null ? 'no status — the request did not complete' : failure.status,
        },
        // `?? null` rather than `=== true`: an ABSENT flag is unknown, and this
        // module's discipline is to say NOT_AVAILABLE rather than render a
        // plausible-looking `no`. Both are populated by
        // `diagnosticsFailureFrom` today; the invariant should hold anyway.
        { label: 'Network-Level Failure', value: failure.unreachable ?? null },
        { label: 'HTML Intercept', value: failure.htmlIntercept ?? null },
        { label: 'Response Content-Type', value: failure.contentType ?? 'not reported' },
        { label: 'Request Path', value: failure.path ?? 'not recorded' },
      ],
    });
  }

  return [
    DIAGNOSTICS_HEADING,
    '',
    '```text',
    groups.map(renderGroup).join('\n\n'),
    '```',
    '',
    'Observed values only — no credential, token, cookie, storage content, request',
    'header, conversation or record value is included, and nothing was uploaded.',
  ].join('\n');
}
