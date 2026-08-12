/*
 * Typed fetch client for the ISAAC FastAPI backend (apps/api).
 *
 * Thin client: it fetches server-derived truth (validation / coverage / advisory /
 * field status / evidence / status) and never computes any of it. Every verdict
 * comes from an endpoint; this module only parses envelopes and unwraps arrays.
 *
 * Base URL comes from `VITE_API_BASE` (default `http://127.0.0.1:8000/api`),
 * which also decides `isHostedBuild` — the one place the app knows whether it is
 * a hosted deployment or a local dev build.
 *
 * Every failure surfaces as a typed `ApiError` carrying what was actually
 * OBSERVED — `unreachable` (the request never completed), an HTTP `status`, and
 * `htmlIntercept` (an `/api/*` path answered with HTML, i.e. an authenticating
 * edge served a sign-in page). Screens render the honest down state from those
 * signals and never fabricate data — or a cause.
 */

import type { RuntimeRecord } from './crossRecordTriage';
// P36V.1 Unit F — the deep graph layer's wire contract lives in `graphDeep.ts`
// (with its decoder), not in `types.ts`, so the graph's deep layer stays one
// self-contained module.
import type { ApiGraphDetailResponse } from './graphDeep';
import type {
  ApiAboutResponse,
  ApiAnswersResponse,
  ApiArtifactsResponse,
  ApiAuditResponse,
  AssistantQueryResponse,
  ApiCsvPreview,
  ApiDraftResponse,
  ApiEvidenceClassification,
  ApiEvidenceEntry,
  ApiEvidenceResponse,
  ApiExperimentDetail,
  ApiExperimentList,
  ApiExperimentSummary,
  ApiExportResponse,
  ApiGraphStatus,
  ApiHealth,
  ApiListIncomplete,
  ApiMemoryConceptResponse,
  ApiMemoryConceptsResponse,
  ApiMemoryFileResponse,
  ApiMemoryFilesResponse,
  ApiMemoryGraphResponse,
  ApiOpenApiResponse,
  ApiPendingResponse,
  ApiRunCheckResponse,
  ApiRunCreated,
  ApiRunOverrideCleared,
  ApiRunOverrideResponse,
  ApiRunResponse,
  ApiRunsResponse,
  ApiSchemaResponse,
  ApiSearchResponse,
  ApiSearchScope,
  ApiSourcePreview,
  ApiTutorialSession,
  ApiDemoRunResponse,
  ApiDemoResetResult,
  ApiUploadsBlocked,
  ApiValidateRecordError,
  ApiValidateRecordResult,
  ApiValidateResult,
  ApiWarningsResponse,
  EvidenceBundle,
  ExperimentGraphBundle,
  ExportReadinessBundle,
  RecordBundle,
} from './types';
import { readTutorialSession } from './tutorialSession';

/**
 * The base a build with no `VITE_API_BASE` falls back to — the local FastAPI
 * dev server. Kept as a named literal because `isHostedBuild` compares against
 * it (see below).
 */
const LOCAL_API_BASE = 'http://127.0.0.1:8000/api';

const RAW_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? LOCAL_API_BASE;

export const API_BASE = RAW_BASE.replace(/\/+$/, '');

/**
 * Hosted vs. local, decided ONCE here — never sniffed per component.
 *
 * A hosted image is built with an explicit `VITE_API_BASE` (`/krish/api` for
 * the S3DF deployment); a local build leaves it unset and falls back to
 * `LOCAL_API_BASE`. Vite substitutes `import.meta.env.VITE_API_BASE` with a
 * string LITERAL at build time, so this is a comparison of two compile-time
 * literals: a hosted bundle folds it to `true` and can then drop every
 * local-only branch — including `RUN_COMMAND`, which must never ship in a
 * hosted build (telling a hosted user to start a server on their laptop is
 * both unactionable and false).
 *
 * Consequence worth stating: a developer who points `VITE_API_BASE` at some
 * other base (e.g. `http://localhost:8000/api`) is treated as "hosted" — i.e.
 * we stop claiming the local run command is the remedy. That is the safe
 * direction: we withhold an instruction we cannot justify rather than assert
 * one we cannot support.
 */
export const isHostedBuild = RAW_BASE !== LOCAL_API_BASE;

/*
 * THE CLIENT SENDS NO BEARER TOKEN, AND CANNOT BE MADE TO.
 *
 * There used to be an `apiKey()` here that read `import.meta.env.VITE_API_KEY`
 * and attached `Authorization: Bearer <key>` to every request. It is gone, and
 * the reason is not that it was unused — it is that the mechanism cannot work.
 *
 * Vite substitutes `import.meta.env.VITE_*` at BUILD time. The value does not
 * travel as configuration; it is compiled into the JavaScript bundle that is
 * served to every visitor. A shared secret in that bundle is not a secret, and
 * a bearer token that anyone who loads the page can read is not an
 * authentication control — it is a credential published on a website that
 * happens to be checked by a server.
 *
 * The seam was DORMANT rather than harmless: `Dockerfile:22` builds with only
 * `VITE_BASE_PATH` and `VITE_API_BASE`, so no key has ever shipped. But a
 * Phase-20 deployment plan described setting it to the same value as the
 * server's `ISAAC_UI_API_KEY`, which is exactly the mistake this removal makes
 * unavailable. Leaving a loaded footgun on the floor because nobody has picked
 * it up yet is not a security posture.
 *
 * WHAT PROTECTS THE HOSTED APP INSTEAD: the Authentik edge in front of
 * `/krish`, which authenticates before a request reaches this application at
 * all. That boundary is real, external to the bundle, and not something a
 * reader of the JavaScript can defeat.
 *
 * WHAT THIS COSTS, STATED PLAINLY: the backend's `ISAAC_UI_API_KEY` seam
 * (`apps/api/isaac_api/auth.py`) still exists and still works. If it is ever
 * set, this browser client will receive 401s, because it no longer has any way
 * to authenticate. That asymmetry is deliberate. `ISAAC_UI_API_KEY` is now a
 * control for NON-BROWSER callers — scripts, probes, other services — which is
 * the only kind of caller that can hold a shared secret without publishing it.
 * A browser session that needs authentication needs a session, not a baked
 * constant, and that is a design decision rather than a missing feature.
 *
 * Several tests still plant a `VITE_API_KEY` value on purpose. They are leak
 * canaries — they assert the value never surfaces in diagnostics, reset
 * payloads or error states — and they get STRONGER with no consumer, not
 * weaker. `__tests__/api.test.ts` additionally pins that a planted key produces
 * no `Authorization` header, so this removal cannot be quietly undone.
 */

/**
 * The exact phrase the backend requires to EXECUTE a reset of the example
 * workspace. Sent verbatim on execute only; the operator types the shorter "RESET"
 * gate in the UI and never sees or re-types this phrase (no auto-fill of the typed
 * gate). Pinned character-for-character to `_RESET_CONFIRMATION` in
 * `apps/api/isaac_api/routes.py` — renaming it on one side only makes every reset
 * fail closed with a 409.
 *
 * R1 retired the previous value. It named the app after its own test harness, and
 * although the dialog does not display it, it ships in the bundle and reads as the
 * product's own vocabulary to anyone who finds it.
 */
export const RESET_CONFIRMATION = 'RESET EXAMPLE WORKSPACE';

/**
 * The exact command that starts the local backend (shown in the LOCAL down
 * state only). Every render site guards it with `!isHostedBuild` so a hosted
 * bundle constant-folds the branch away and never ships this string.
 */
export const RUN_COMMAND =
  '.venv/bin/uvicorn isaac_api.app:app --app-dir apps/api --host 127.0.0.1 --port 8000';

/**
 * A fetch/HTTP failure. `unreachable` distinguishes "the request never
 * completed" from "the server answered with a status"; `htmlIntercept`
 * distinguishes "an authenticating edge answered instead of our JSON API"
 * from either. Screens branch on these to say something TRUE about the
 * cause instead of a single guessed one.
 */
export class ApiError extends Error {
  readonly status?: number;
  readonly unreachable: boolean;
  /** The parsed error body, when the caller read it (e.g. the P27.5 412
   *  `stale_write` payload carrying `current_version`). Undefined otherwise. */
  readonly body?: unknown;
  /**
   * The API path that failed (as passed to `request`, without the base). Safe
   * to display: this client puts credentials in the `Authorization` HEADER and
   * never in a URL, so a path can never carry a token.
   */
  readonly path?: string;
  /** The response `Content-Type`, when the response reported one. */
  readonly contentType?: string;
  /**
   * True when a response to an `/api/*` path carried `text/html`. Our API only
   * ever answers JSON, so HTML on an API path is an edge/proxy intercept — in
   * this deployment, the identity provider's sign-in page. That is observed
   * evidence of an authentication redirect, not an inference.
   */
  readonly htmlIntercept: boolean;
  /**
   * The backend's OWN typed reason string — the `error` field of a JSON error
   * body — when one was safely readable. `undefined` whenever it was not, and
   * consumers must treat `undefined` as "not observed", never as a default.
   *
   * WHY THIS EXISTS. The API deliberately distinguishes reasons that share a
   * status: a 404 under `/experiments/{id}` can be `experiment_not_found` (no
   * such record), `run_not_found` (the record exists and was read successfully
   * and holds no run under that id — `routes.py::_run_not_found` says
   * collapsing them "would tell a client to go looking in the wrong place"),
   * `source_not_allowed`, or `tutorial_session_not_found` from the scope
   * dependency. `httpError` copies the status and nothing else, so every one of
   * those arrived at the UI identical, and `FetchStates.downCopy` reported all
   * of them as a missing record. This field is how a screen can tell them apart.
   *
   * NEVER SET FROM AN HTML BODY. A sign-in page served on an API path carries no
   * ISAAC reason, and inventing one from it is the defect `htmlIntercept`
   * exists to prevent — see `readReason`.
   */
  readonly reason?: string;

  constructor(
    message: string,
    opts: {
      status?: number;
      unreachable?: boolean;
      body?: unknown;
      path?: string;
      contentType?: string;
      htmlIntercept?: boolean;
      reason?: string;
    } = {},
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = opts.status;
    this.unreachable = opts.unreachable ?? false;
    this.body = opts.body;
    this.path = opts.path;
    this.contentType = opts.contentType;
    this.htmlIntercept = opts.htmlIntercept ?? false;
    this.reason = opts.reason;
  }
}

/** `text/html`, with or without a charset parameter. */
const HTML_CONTENT_TYPE = /^\s*text\/html\b/i;

const HTML_INTERCEPT_MESSAGE =
  'The API path returned an HTML page instead of JSON (an edge intercept).';

/** The response `Content-Type`, tolerating a stub/response without headers. */
function contentTypeOf(res: Response): string | undefined {
  const raw = res.headers?.get?.('content-type');
  return raw ?? undefined;
}

function isHtml(contentType: string | undefined): boolean {
  return contentType !== undefined && HTML_CONTENT_TYPE.test(contentType);
}

/** The typed error for a non-OK response, carrying every observable signal. */
function httpError(res: Response, path: string): ApiError {
  const contentType = contentTypeOf(res);
  const htmlIntercept = isHtml(contentType);
  return new ApiError(
    htmlIntercept ? HTML_INTERCEPT_MESSAGE : `Request failed (${res.status}).`,
    { status: res.status, path, contentType, htmlIntercept },
  );
}

/**
 * `httpError`, PLUS the backend's own typed reason when one is safely readable.
 *
 * `httpError` stays synchronous and body-free, because many callers are and
 * because a body can be consumed only once — this is a separate, async
 * construction used where the caller is about to throw and has NOT read the body.
 * It is the same shape `tutorialSessionState` already uses for its one reason
 * (`httpError`, then a guarded `res.json()`), generalised so that every read
 * failure carries what the API actually said instead of only its status.
 *
 * THREE RULES, each of which is a defect this module has already had:
 *
 *  1. NEVER READ A REASON OUT OF AN HTML BODY. An authenticating edge answers an
 *     `/api/*` path with its sign-in page, and a reason parsed from that would be
 *     fabricated. The `htmlIntercept` short-circuit is the same refusal
 *     `readJson` and `mutationError` make.
 *  2. A FAILED OR ABSENT PARSE LEAVES `reason` UNDEFINED. `.catch(() =>
 *     undefined)` and the `typeof === 'string'` test mean a non-JSON body, an
 *     empty body, `{}`, or `{"detail": …}` (FastAPI's shape for an unrouted
 *     path) all yield "not observed" rather than a wrong reason. Consumers must
 *     degrade to their generic branch, which `downCopy` does.
 *  3. ONLY 404. Widening this to other statuses would read bodies that
 *     `mutationError` owns and could double-consume one; there is no need, and
 *     the narrow rule is the safe one.
 *
 * A BEHAVIOUR CHANGE RULE 3 CAUSES, DISCLOSED BECAUSE IT IS REAL AND NOT OBVIOUS.
 * Only the 404 path awaits `res.json()`, so a 404 now rejects one `await` LATER than
 * every other failing status. In a bundle whose members fail with MIXED statuses —
 * say a 404 on `GET /experiments/{id}` and a 500 on `POST /audit` — the non-404
 * rejection therefore wins the `Promise.all` systematically, where previously the
 * winner was whatever the network happened to deliver first. Three things to hold
 * onto: this is ORDERING, not information (no reason is lost, and a 404 reaching the
 * panel still carries its reason); both outcomes produce honest copy (a 500 renders
 * `http_error`, "the API was reached but answered with HTTP 500", which is true of
 * that response); and it is deliberately NOT compensated for, because introducing a
 * delay to even the race up would be complexity in service of a cosmetic tie-break.
 * It is pinned by test (`api.test.ts`, "a mixed-status bundle") so that a future
 * change to the precedence is loud rather than silent.
 */
async function httpErrorWithReason(res: Response, path: string): Promise<ApiError> {
  const base = httpError(res, path);
  if (res.status !== 404 || base.htmlIntercept) return base;
  const body = (await res.json().catch(() => undefined)) as { error?: unknown } | undefined;
  if (typeof body?.error !== 'string') return base;
  return new ApiError(base.message, {
    status: base.status,
    path: base.path,
    contentType: base.contentType,
    htmlIntercept: base.htmlIntercept,
    reason: body.error,
  });
}

/**
 * Read a response body as JSON — the ONE place this module parses a body.
 *
 * `res.json()` REJECTS on a non-JSON body, and the case that matters is not
 * hypothetical: an authenticating edge can answer an `/api/*` request with its
 * sign-in HTML and HTTP **200**. Before this was centralized, that rejection
 * escaped every reader as a raw `SyntaxError` — not an `ApiError` — so screens
 * rendered a generic crash instead of the honest down state. Here the HTML case
 * is detected from the `Content-Type` first (so the caller learns it was an
 * intercept, not corrupt JSON), and any other parse failure still becomes a
 * typed `ApiError`.
 */
async function readJson<T>(res: Response, path: string): Promise<T> {
  const contentType = contentTypeOf(res);
  if (isHtml(contentType)) {
    throw new ApiError(HTML_INTERCEPT_MESSAGE, {
      status: res.status,
      path,
      contentType,
      htmlIntercept: true,
    });
  }
  try {
    return (await res.json()) as T;
  } catch {
    throw new ApiError(`The API response was not valid JSON (${res.status}).`, {
      status: res.status,
      path,
      contentType,
    });
  }
}

/**
 * The statuses on which `POST /api/demo/reset` answers with a typed RESET RESULT
 * rather than an error: 200 (preview or a completed execute) and the four safe
 * refusals 403 / 409 / 412 / 428. Named because the fail-closed check below has to
 * apply to exactly this set and nothing wider.
 */
const RESET_RESULT_STATUSES = [200, 403, 409, 412, 428];

/**
 * Is this body actually a reset result?
 *
 * WHY THIS EXISTS, on the one destructive path in the app. `resetDemo` decodes five
 * statuses as a typed result, and every genuine reset result is built by ONE
 * backend helper (`routes._reset_response`), which always sets `status` to `"ok"`
 * or `"refused"`. But those statuses are not exclusively its: `POST /api/demo/reset`
 * also answers **409** `{"error": "tutorial_scope_required", …}` when the request
 * carries no worked-example session (`routes.py:1254-1255` → `_tutorial_scope_required`,
 * `:795-805`), and that body has no `status`, no counts and no `plan_digest`.
 *
 * Read as an `ApiDemoResetResult` it produced a HALF-BUILT object, and the failure
 * was silent in the dangerous direction: `ResetDemoDialog`'s `refused` is
 * `data.status === 'refused' || data.ambiguous_count > 0`, and with both fields
 * `undefined` that is `false` — so the dialog would have rendered `undefined`
 * counts and left the execute button armable by typing the phrase. Rejecting
 * instead lands the dialog in its existing preview-`error` state, where
 * `actionDisabled` is true because `preview.status !== 'data'`.
 *
 * Believed unreachable today (the dialog only mounts inside a session, so the
 * request always carries the header), but it is a guard rather than an assertion
 * about reachability: the invariant it would rest on is two module-level variables
 * — `api.ts`'s `tutorialScope` and the tutorial store's `sessionId` — staying in
 * step, and a destructive control must not be armed by that holding.
 *
 * Narrow on purpose: it tests ONLY the discriminator, so every currently-handled
 * refusal (`not_synthetic_only`, `confirmation_required`, `plan_digest_required`,
 * `plan_digest_stale`, `ambiguous_records_present`) keeps working exactly as it
 * does now.
 */
function isResetResult(body: unknown): body is ApiDemoResetResult {
  if (typeof body !== 'object' || body === null) return false;
  const status = (body as { status?: unknown }).status;
  return status === 'ok' || status === 'refused';
}

/**
 * Decode the `incomplete` block of a list response, or `null`.
 *
 * FAIL-CLOSED TOWARDS SILENCE, DELIBERATELY, and the direction is the whole
 * decision. This block drives a warning on the primary screen, so a body this
 * client cannot read must not raise one: an unreadable `incomplete` is treated as
 * NO CLAIM, exactly as an absent one is. The opposite choice would let any
 * malformed response — an edge intercept, a proxy's error page decoded as JSON,
 * a future server sending a different shape — tell every reader their list might
 * be missing records when nothing said so.
 *
 * `reason` IS NOT VALIDATED AGAINST THE TWO KNOWN LABELS. A label this build has
 * never seen is still a server saying "this list may be short", which is true and
 * worth showing; the RENDERER is what must not index a lookup table with it. See
 * `ExperimentsHome`'s `incompleteHeading`.
 */
function decodeListIncomplete(raw: unknown): ApiListIncomplete | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const { reason, message, missing_count: missingCount } = raw as Record<string, unknown>;
  if (typeof reason !== 'string' || reason === '') return null;
  if (typeof message !== 'string' || message === '') return null;
  return {
    reason,
    message,
    // Passed through, never defaulted. `null` is the server's honest "unknown".
    missing_count: typeof missingCount === 'number' ? missingCount : null,
  };
}

/** The header the backend resolves the workspace scope from. Must match
 *  `TUTORIAL_SESSION_HEADER` in `apps/api/isaac_api/routes.py`. */
export const TUTORIAL_SESSION_HEADER = 'X-Isaac-Tutorial-Session';

/**
 * Which workspace scope every request operates in: `null` = the ordinary
 * workspace, otherwise an open worked-example session.
 *
 * Module-level rather than threaded through the ~40 exported functions, because
 * `request()` below is the single point where headers are composed — so scope is
 * applied in exactly one place and a new API function cannot forget it.
 *
 * INITIALISED FROM `sessionStorage` AT MODULE LOAD, and that ordering is
 * load-bearing: after a reload the first record fetch can be issued by a screen
 * mounting before any tutorial code runs, and an unscoped fetch would 404 the
 * reader out of their own session.
 *
 * THIS IS THE AUTHORITY ON WHICH SCOPE REQUESTS CARRY, and the tutorial store's
 * `sessionId` is its React-observable mirror — `tutorialController.ts`'s
 * `initialState()` seeds itself from `getTutorialScope()` for exactly that reason, so
 * the two cannot disagree on the first render. Nothing here may import that store
 * (the dependency runs the other way, which is what guarantees this line has already
 * executed when the store initialises).
 */
let tutorialScope: string | null = readTutorialSession()?.sessionId ?? null;

/** Enter (`sessionId`) or leave (`null`) a worked-example session. */
export function setTutorialScope(sessionId: string | null): void {
  tutorialScope = sessionId;
}

/** The scope requests currently carry. `null` = the ordinary workspace. */
export function getTutorialScope(): string | null {
  return tutorialScope;
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(`${API_BASE}${path}`, {
      ...init,
      // Thread the optional AbortSignal through so a caller (e.g. the P27.6 poller)
      // can cancel an in-flight request. `...init` already carries it, but we make
      // it explicit so the intent is obvious and existing callers stay unaffected.
      signal: init?.signal,
      headers: {
        Accept: 'application/json',
        ...(init?.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(tutorialScope !== null ? { [TUTORIAL_SESSION_HEADER]: tutorialScope } : {}),
        ...init?.headers,
      },
    });
  } catch {
    // Network-level failure (server not started, connection refused, CORS reject).
    // Deliberately does NOT name a cause: from here the two are indistinguishable.
    throw new ApiError('The ISAAC API could not be reached.', { unreachable: true, path });
  }
}

/*
 * THE TWO GENERIC HELPERS, BOTH WIDENED TO CARRY A TYPED 404 REASON — and they have
 * to be BOTH, which is a correction of a first attempt that widened only `getJson`.
 *
 * Every read that renders `BackendDown` through `useFetch` comes through one of
 * these, and the screens fetch in BUNDLES. `getRecordBundle` issues SEVEN
 * experiment-scoped requests for one route in ONE `Promise.all` — `GET {id}`,
 * `/draft`, `/pending`, `POST /validate`, `POST /audit`, `/warnings`, `/evidence`,
 * so six of the seven are sub-resource paths and two of the seven are POSTs. On a
 * genuinely missing record ALL of them 404, and the rejection that reaches the panel
 * is whichever landed first. If only `getJson` carried the reason, a `POST /validate`
 * rejection winning that race would leave `reason === undefined` and the copy would
 * fall back to the path rule — so the screen's wording for ONE underlying truth would
 * depend on scheduling. Widening both makes every member of the bundle carry
 * `experiment_not_found`, and the race stops mattering. That race-independence is the
 * entire reason this is done by reason rather than by path; see
 * `FetchStates.downCopy`.
 *
 * CORRECTION, RECORDED RATHER THAN OVERWRITTEN. An earlier revision of this comment
 * cited "`getEvidenceBundle` races `getExperiment` against every `getSourcePreview`"
 * as the racing site. THAT IS FALSE and is withdrawn: `getEvidenceBundle` is TWO
 * SEQUENTIAL `Promise.all`s (see its own comment below), the previews are fetched
 * only after the first bundle resolves, and on a genuinely missing record the first
 * bundle rejects and `getSourcePreview` is never called at all. The racing sites are
 * `getRecordBundle` above, `getEvidenceBundle`'s FIRST `Promise.all` (1 exact +
 * 3 sub-resource reads), `getExportReadiness`, `getExperimentGraphBundle`,
 * `GuidedCompletion.tsx:46` and `useRecordSession.ts:226`. The conclusion — widen
 * both helpers — is unchanged; only the example was wrong.
 *
 * SAFE AGAINST DOUBLE-CONSUMPTION: on the failure path the body is untouched before
 * this point and the throw follows immediately, so `readJson` never also runs. On
 * the success path nothing changed — `readJson` still performs the only parse.
 *
 * `mutationError` is deliberately untouched. It already owns body reading for the
 * statuses that carry a conflict payload (412 / 400), and the methods that use it
 * surface failures inline rather than through `BackendDown`.
 */
async function getJson<T>(path: string): Promise<T> {
  const res = await request(path);
  if (!res.ok) throw await httpErrorWithReason(res, path);
  return readJson<T>(res, path);
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await request(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw await httpErrorWithReason(res, path);
  return readJson<T>(res, path);
}

/**
 * Build the ApiError for a non-OK mutation response. On a 412 (`stale_write`) or
 * 400 (`malformed_if_match`) the JSON body is read and attached — it carries the
 * P27.5 conflict payload (`current_version`, `current_rev`, …) the screen needs.
 * A 409 (export immutability) and every other status keep the plain-error shape,
 * so existing callers (e.g. the export 409 branch) are unaffected. An HTML
 * intercept short-circuits: there is no conflict payload in a sign-in page.
 */
/*
 * 422 JOINED 412 AND 400, and the reason is a copy defect rather than a taste.
 *
 * `POST /edit` answers 422 with `{"error": "invalid_field_value", "key": …}` for a
 * correction it cannot store. Without the body, every 422 looked identical to every
 * other, so the screen could only say "could not be applied (422) … try again" — and
 * that DROPS the one sentence a scientist needs, which is that the value they had
 * before is still there. The body is what lets the notice say it.
 *
 * Additive: this only POPULATES `err.body` where it was previously `undefined`. No
 * caller's branch changes, because none of them reads `body` on a 422 today.
 */
async function mutationError(res: Response, path: string): Promise<ApiError> {
  const err = httpError(res, path);
  if (!err.htmlIntercept && (res.status === 412 || res.status === 400 || res.status === 422)) {
    const body = await res.json().catch(() => undefined);
    return new ApiError(err.message, {
      status: res.status,
      path,
      contentType: err.contentType,
      body,
    });
  }
  return err;
}

const enc = encodeURIComponent;

/**
 * The optional query a run listing may carry. Every field is optional and every
 * absent field means "the server's default", which for `limit` is THE WHOLE
 * LIST — see `api.listRuns`.
 *
 * `overrides` is the server's own two-valued vocabulary (`any` = this run holds
 * at least one override, `none` = it holds none) and is deliberately typed as
 * that union rather than as `string`, so a third state invented on this side is
 * a compile error instead of a query the server silently ignores.
 */
export interface ListRunsQuery {
  /** 1..200. Omitted means every run. */
  limit?: number;
  /** Runs to skip, in canonical order. An offset past the end is CLAMPED to an
   *  empty page by the server, never refused — that request is exactly what a
   *  Load More sends after a concurrent delete shortened the list. */
  offset?: number;
  /** Case-insensitive literal substring over each run's label, id and record id;
   *  an all-digits query also matches `ordinal` exactly. NOT a search over
   *  scientific values, and not fuzzy. */
  q?: string;
  overrides?: 'any' | 'none';
  exported?: boolean;
}

export const api = {
  health(): Promise<ApiHealth> {
    return getJson<ApiHealth>('/health');
  },

  // P36.4 — Settings "Help / About": non-sensitive app/provenance metadata.
  getAbout(): Promise<ApiAboutResponse> {
    return getJson<ApiAboutResponse>('/about');
  },

  // P36.4 — Settings "API Documentation": the app's own generated OpenAPI
  // schema, fetched base-path-correctly via this router (not the root
  // /openapi.json, which is unprefixed and would be wrong under a deployed
  // base path).
  getOpenApi(): Promise<ApiOpenApiResponse> {
    return getJson<ApiOpenApiResponse>('/openapi');
  },

  // Record Verification — the sanitized AGGREGATE report of the verification
  // program (official validation, the format-aware shadow checks, the mutation
  // harness). Read-only, and typed as `unknown` on purpose: the body is decoded
  // by `lib/verificationContract.ts::readVerificationBody`, which fails closed
  // on anything it does not fully understand. Asserting a wire type here would
  // hand the caller a lie the compiler cannot check.
  getVerification(): Promise<unknown> {
    return getJson<unknown>('/runtime/verification');
  },

  /**
   * Open an isolated worked-example session and return its id plus the record
   * ids actually materialised in it.
   *
   * The caller is responsible for entering the scope (`setTutorialScope`) before
   * reading those records — creating a session does not by itself change which
   * workspace subsequent requests address. Deliberately NOT scope-carrying
   * itself: opening a session from inside another session would be meaningless.
   */
  createTutorialSession(): Promise<ApiTutorialSession> {
    return postJson<ApiTutorialSession>('/tutorial/sessions');
  },

  /**
   * Discard a worked-example session and everything in it.
   *
   * Idempotent at the backend: discarding a session that is already gone
   * succeeds, so a client never has to know whether it is retrying. Returns
   * nothing — a 204 carries no body.
   */
  async disposeTutorialSession(sessionId: string): Promise<void> {
    const path = `/tutorial/sessions/${enc(sessionId)}`;
    const res = await request(path, { method: 'DELETE' });
    if (!res.ok) throw httpError(res, path);
  },

  /**
   * Does this worked-example session still exist? `'present'`, `'gone'`, or a throw.
   *
   * A scoped read of the experiment list is the cheapest existence probe there is:
   * the shared scope dependency answers an unknown session with `404` and the typed
   * body `{"error": "tutorial_session_not_found"}` BEFORE any record work happens
   * (`apps/api/isaac_api/routes.py::tutorial_scope`). The header is passed
   * explicitly rather than relied on from `tutorialScope`, so the probe asks about
   * the session it was given and not about whatever scope the module happens to
   * hold.
   *
   * WHY THIS IS NOT `listExperiments()` WRAPPED IN A `catch`. It was, and that was a
   * defect: `getJson` builds its failure through `httpError`, which deliberately does
   * NOT read the response body, so every caller saw an untyped `status` and could not
   * tell the backend's stated reason from any other 404 — let alone from a 401 at the
   * authenticating edge, a 500, or an unreachable backend. `'gone'` is therefore
   * returned ONLY on the observed typed body. Everything else is rethrown as the
   * `ApiError` it is, which forces the caller to decide what to do about a cause it
   * cannot name instead of guessing "expired".
   *
   * Read-only, and it takes no lock.
   */
  async tutorialSessionState(sessionId: string): Promise<'present' | 'gone'> {
    const path = '/experiments';
    const res = await request(path, {
      headers: { [TUTORIAL_SESSION_HEADER]: sessionId },
    });
    if (res.ok) return 'present';
    const err = httpError(res, path);
    // An HTML answer on an `/api/*` path is an edge intercept, never our 404 — do
    // not try to read a typed reason out of a sign-in page.
    if (res.status === 404 && !err.htmlIntercept) {
      const body = (await res.json().catch(() => undefined)) as { error?: unknown } | undefined;
      if (body?.error === 'tutorial_session_not_found') return 'gone';
    }
    throw err;
  },

  /**
   * S1 — the experiment queue, AND WHETHER IT IS WHOLE.
   *
   * IT NO LONGER UNWRAPS TO A BARE ARRAY, and that is the point rather than a
   * refactor. The server degrades this list rather than failing it when it cannot
   * restore its working copies from the database, so the array alone cannot be
   * told apart from a smaller workspace — the shortfall travels in a sibling key
   * and unwrapping threw it away before any screen could see it.
   *
   * `incomplete` IS DECODED, NOT TRUSTED. Only an object carrying a string
   * `reason` and a string `message` is accepted; anything else — absent, null, a
   * bare `true`, a number where a message should be — becomes `null`, which means
   * "no claim that anything is missing". Failing closed the other way would let a
   * malformed body put a permanent warning banner on the primary screen.
   *
   * `missing_count` is passed through as whatever the server sent and is NEVER
   * defaulted to a number here: the contract says it is unknown, and a client
   * that substituted 0 would be inventing the one figure the server refuses to
   * invent.
   */
  async listExperiments(): Promise<ApiExperimentList> {
    const body = await getJson<{
      experiments: ApiExperimentSummary[];
      incomplete?: unknown;
    }>('/experiments');
    return {
      experiments: body.experiments,
      incomplete: decodeListIncomplete(body.incomplete),
    };
  },

  /**
   * Create an experiment in the ordinary workspace.
   *
   * It sends a title and, when there is one, a note — and NOTHING else. There is
   * deliberately no `id` parameter on this function: the server mints the record
   * id, and its request model rejects an unrecognised field outright, so a client
   * that tried to choose one would get a 422 rather than be quietly obeyed. That
   * is the property `test_create_experiment_has_no_caller_in_the_api_package`
   * exists to keep, and the shape of this signature is the client-side half of it.
   *
   * `description` is omitted from the body when empty rather than sent as `""`:
   * the two are the same thing to a reader and only one of them is a value.
   *
   * The worked-example session header is attached by `request` when a session is
   * open — and the server then refuses with 409. That is intentional and is not
   * worked around here: a record a person created must not be written into a
   * workspace that is discarded on a timer. The UI does not offer this action
   * inside a session, so the refusal is a backstop rather than a path a reader
   * meets.
   */
  createExperiment(input: { title: string; description?: string }): Promise<ApiExperimentDetail> {
    const description = (input.description ?? '').trim();
    return postJson<ApiExperimentDetail>('/experiments', {
      title: input.title.trim(),
      ...(description ? { description } : {}),
    });
  },

  getExperiment(id: string): Promise<ApiExperimentDetail> {
    return getJson<ApiExperimentDetail>(`/experiments/${enc(id)}`);
  },

  // P27.6 — the client half of revision-aware live-sync. A conditional GET sends
  // the held ETag as `If-None-Match: "<version>"`; the backend answers 304 (no
  // body) when the record is unchanged or 200 + the fresh detail (+ new ETag)
  // when it changed. We call request() directly — getJson throws on any non-2xx,
  // and a 304 is deliberately non-ok. Branch on status: 304 → not changed; 200 →
  // changed, hand back the fresh detail (the caller decides whether to refetch);
  // anything else is a genuine error. A network failure from request() is already
  // an ApiError({unreachable:true}) and simply propagates. `signal` lets the
  // poller abort an in-flight check on unmount / record / version change.
  async checkRecordVersion(
    id: string,
    version: string,
    signal?: AbortSignal,
  ): Promise<{ changed: boolean; detail?: ApiExperimentDetail }> {
    const path = `/experiments/${enc(id)}`;
    const res = await request(path, {
      headers: { 'If-None-Match': `"${version}"` },
      signal,
    });
    if (res.status === 304) return { changed: false };
    if (res.ok) return { changed: true, detail: await readJson<ApiExperimentDetail>(res, path) };
    throw httpError(res, path);
  },

  async getDraftGroups(id: string) {
    return (await getJson<ApiDraftResponse>(`/experiments/${enc(id)}/draft`)).groups;
  },

  async getPending(id: string) {
    return (await getJson<ApiPendingResponse>(`/experiments/${enc(id)}/pending`)).pending;
  },

  // S4 — apply a confirmed answer to one blocker. The user has explicitly
  // confirmed (`confirmed_by_user:true`); the backend recomputes and returns the
  // remaining pending list + fresh status. Never called for "leave missing".
  // P27.5: when a `version` token is threaded, it is sent as the optimistic-
  // concurrency `If-Match: "<version>"` header (byte-identical to the ETag). A
  // stale write returns 412 (or a malformed token 400) — the body carrying
  // `current_version` is read and attached to the thrown ApiError so the screen
  // can show the conflict; other non-OK statuses keep the plain-error behavior.
  async submitAnswer(
    id: string,
    answersById: Record<string, unknown>,
    version?: string,
  ): Promise<ApiAnswersResponse> {
    const path = `/experiments/${enc(id)}/answers`;
    const res = await request(path, {
      method: 'POST',
      body: JSON.stringify({ answers: answersById, confirmed_by_user: true }),
      // Truthiness guard: never send an empty `If-Match: ""` for a blank token.
      ...(version ? { headers: { 'If-Match': `"${version}"` } } : {}),
    });
    if (res.ok) return readJson<ApiAnswersResponse>(res, path);
    throw await mutationError(res, path);
  },

  // P28.3 — correct/re-confirm an ALREADY-answered field. Same wire shape and
  // optimistic-concurrency contract as submitAnswer (`{answers, confirmed_by_user}`
  // + `If-Match: "<version>"`), but hits POST /edit, which OVERWRITES the current
  // value (rather than filling a pending blocker) and returns the same
  // pending/status/version/workflow/invalidation bundle. A 412 stale write (or 400
  // malformed token) is thrown with the parsed body attached; an unchanged submit
  // is a backend-guaranteed no-op (200, invalidation.changed:false).
  async editField(
    id: string,
    answersById: Record<string, unknown>,
    version?: string,
  ): Promise<ApiAnswersResponse> {
    const path = `/experiments/${enc(id)}/edit`;
    const res = await request(path, {
      method: 'POST',
      body: JSON.stringify({ answers: answersById, confirmed_by_user: true }),
      ...(version ? { headers: { 'If-Match': `"${version}"` } } : {}),
    });
    if (res.ok) return readJson<ApiAnswersResponse>(res, path);
    throw await mutationError(res, path);
  },

  /*
   * ---- Runs -------------------------------------------------------------
   *
   * Five thin readers over the frozen Slice-A Run contract. They reuse THIS
   * module's `request` / `readJson` / `mutationError` — so the tutorial scope
   * header, the HTML-intercept detection, the unreachable classification and
   * the 412/400 body attachment all behave exactly as they do for every other
   * write in the app. There is no second HTTP layer for runs.
   *
   * THE TWO `If-Match` TOKENS ARE DIFFERENT TOKENS, and confusing them is the
   * one mistake this seam invites. Creating a run mutates the EXPERIMENT
   * document, so `createRun` carries the experiment's version. Editing a run
   * mutates the RUN, so `updateRun` carries `run.version`. Sending the wrong
   * one is not a silent bug — it is a 412 — but it is a 412 the reader would
   * be told to resolve by refreshing something that was never stale.
   *
   * Each guards `If-Match` on truthiness exactly as `submitAnswer`/`editField`
   * do: an empty token is sent as ABSENT so the server refuses with 428, rather
   * than as `If-Match: ""`, which is a malformed token (400) and would report a
   * client bug as a precondition failure.
   */

  /**
   * One PAGE of a record's runs, optionally searched and filtered SERVER-SIDE.
   *
   * EVERY PARAMETER IS OMITTED WHEN UNSET, and that is the contract rather than
   * tidiness: omitting `limit` returns the whole list, which is what every
   * caller that has not opted into paging still gets. A caller that wants a
   * bounded read has to say so.
   *
   * `q` IS SENT ONLY WHEN IT IS NON-EMPTY. The server treats a blank or
   * whitespace-only `q` as absent, so sending `q=` would be harmless — but it
   * would also put a parameter on the wire that means "no search", and the one
   * place that is not harmless is a reader (or a test) inspecting the request
   * to find out whether a search was performed.
   */
  listRuns(experimentId: string, query: ListRunsQuery = {}): Promise<ApiRunsResponse> {
    const params = new URLSearchParams();
    if (query.limit !== undefined) params.set('limit', String(query.limit));
    if (query.offset !== undefined) params.set('offset', String(query.offset));
    if (query.q !== undefined && query.q.trim() !== '') params.set('q', query.q.trim());
    if (query.overrides !== undefined) params.set('overrides', query.overrides);
    if (query.exported !== undefined) params.set('exported', String(query.exported));
    /*
     * THE PATH LITERAL STAYS WHOLE, AND THE QUERY IS APPENDED TO IT SEPARATELY.
     * `backend-down-state.test.tsx` derives this module's per-record sub-read
     * inventory by reading the source and matching every single-line template
     * literal that starts with the per-record path prefix; interpolating the
     * query string INTO that literal makes the scanner read runs?… as a new
     * sub-resource, for which there is no product word, and the
     * down-state panel then has no product word for the part that failed. This is
     * the refactor the test's own header says "must revisit this block by hand" —
     * avoided by keeping the literal in the established shape.
     */
    const path = `/experiments/${enc(experimentId)}/runs`;
    const search = params.toString();
    return getJson<ApiRunsResponse>(search === '' ? path : `${path}?${search}`);
  },

  getRun(experimentId: string, runId: string): Promise<ApiRunResponse> {
    return getJson<ApiRunResponse>(
      `/experiments/${enc(experimentId)}/runs/${enc(runId)}`,
    );
  },

  /**
   * Create one run. `label` is omitted from the body when blank rather than
   * sent as `""` — the server assigns `"Run N"` for an omitted label, and `""`
   * is not a label a person chose.
   */
  async createRun(
    experimentId: string,
    opts: { experimentVersion: string; label?: string },
  ): Promise<ApiRunCreated> {
    const path = `/experiments/${enc(experimentId)}/runs`;
    const label = (opts.label ?? '').trim();
    const res = await request(path, {
      method: 'POST',
      body: JSON.stringify(label ? { label } : {}),
      ...(opts.experimentVersion
        ? { headers: { 'If-Match': `"${opts.experimentVersion}"` } }
        : {}),
    });
    if (res.ok) return readJson<ApiRunCreated>(res, path);
    throw await mutationError(res, path);
  },

  /**
   * Write run-level draft fields. `confirmed_by_user: true` is required by the
   * contract and is sent unconditionally, because this client only ever calls
   * this from a control the reader typed into — there is no path here that
   * writes a value nobody entered.
   *
   * A `null` value CLEARS a field; that is the contract's meaning and it is
   * passed through untouched rather than being turned into an omission.
   */
  async updateRun(
    experimentId: string,
    runId: string,
    body: { fields: Record<string, unknown>; label?: string },
    runVersion: string,
  ): Promise<ApiRunResponse> {
    const path = `/experiments/${enc(experimentId)}/runs/${enc(runId)}`;
    const res = await request(path, {
      method: 'PATCH',
      body: JSON.stringify({
        confirmed_by_user: true,
        fields: body.fields,
        ...(body.label !== undefined ? { label: body.label } : {}),
      }),
      ...(runVersion ? { headers: { 'If-Match': `"${runVersion}"` } } : {}),
    });
    if (res.ok) return readJson<ApiRunResponse>(res, path);
    throw await mutationError(res, path);
  },

  /*
   * ---- Per-run overrides of inherited record-level values ----------------
   *
   * TWO WRITES, AND NEITHER OF THEM CONFIRMS ON THE READER'S BEHALF. Both
   * operations refuse with `422 confirmation_required` unless the body carries
   * `confirmed_by_user: true`, and both functions below take that flag as an
   * ARGUMENT and send exactly what they were given. That is deliberately unlike
   * `updateRun`/`editField`, which send `true` unconditionally because their only
   * caller is a box the reader typed into: recording an override displaces a
   * value the record supplied, and the contract makes it an explicitly confirmed
   * act. Passing `true` is the CALLER's assertion that a confirmation gesture
   * happened, and the screen is where that gesture lives.
   *
   * THE `If-Match` IS THE RUN'S, NOT THE RECORD'S — the same trap `updateRun`
   * carries, and the route's own description spells it out. Guarded on
   * truthiness exactly as every other write here: an empty token is sent as
   * ABSENT (the server's 428, which is the honest refusal) rather than as
   * `If-Match: ""`, which is a malformed token and would report a client bug as
   * a precondition failure.
   *
   * A 412 MEANS THE OVERRIDE WAS NOT RECORDED. `mutationError` attaches the
   * parsed body, so the screen can show the server's `current_version` and say
   * so; it must never present a stale write as a success.
   */

  async setRunOverride(
    experimentId: string,
    runId: string,
    body: { address: string; payload: unknown; confirmedByUser: boolean },
    runVersion: string,
  ): Promise<ApiRunOverrideResponse> {
    const path = `/experiments/${enc(experimentId)}/runs/${enc(runId)}/overrides`;
    const res = await request(path, {
      method: 'POST',
      body: JSON.stringify({
        confirmed_by_user: body.confirmedByUser,
        address: body.address,
        payload: body.payload,
      }),
      ...(runVersion ? { headers: { 'If-Match': `"${runVersion}"` } } : {}),
    });
    if (res.ok) return readJson<ApiRunOverrideResponse>(res, path);
    throw await mutationError(res, path);
  },

  async clearRunOverride(
    experimentId: string,
    runId: string,
    body: { address: string; confirmedByUser: boolean },
    runVersion: string,
  ): Promise<ApiRunOverrideCleared> {
    const path = `/experiments/${enc(experimentId)}/runs/${enc(runId)}/overrides/clear`;
    const res = await request(path, {
      method: 'POST',
      body: JSON.stringify({
        confirmed_by_user: body.confirmedByUser,
        address: body.address,
      }),
      ...(runVersion ? { headers: { 'If-Match': `"${runVersion}"` } } : {}),
    });
    if (res.ok) return readJson<ApiRunOverrideCleared>(res, path);
    throw await mutationError(res, path);
  },

  /**
   * Check one run. READ-ONLY: it sends no `If-Match` because it writes nothing,
   * and the contract states its response advances no ETag. It is a POST only
   * because the check is computed rather than served.
   */
  checkRun(experimentId: string, runId: string): Promise<ApiRunCheckResponse> {
    return postJson<ApiRunCheckResponse>(
      `/experiments/${enc(experimentId)}/runs/${enc(runId)}/check`,
    );
  },

  // P31.3 — CSV reconciliation preview (RECONCILIATION-ONLY). Uploads the raw
  // CSV text (Content-Type: text/csv) and reconciles every mapped value against
  // the CURRENT record; the backend NEVER mutates the record. Same optimistic-
  // concurrency contract as editField: `If-Match: "<version>"` is REQUIRED
  // (missing → 428). The header spread puts `Content-Type: text/csv` last so it
  // overrides request()'s default JSON content-type. Non-OK responses are thrown
  // via mutationError (identical error handling to editField).
  async previewCsv(
    id: string,
    csvText: string,
    opts: { version: string; filename?: string },
  ): Promise<ApiCsvPreview> {
    const path = `/experiments/${enc(id)}/ingestion/csv/preview`;
    const res = await request(path, {
      method: 'POST',
      body: csvText,
      headers: {
        'Content-Type': 'text/csv',
        'If-Match': `"${opts.version}"`,
        ...(opts.filename ? { 'X-Filename': opts.filename } : {}),
      },
    });
    if (res.ok) return readJson<ApiCsvPreview>(res, path);
    throw await mutationError(res, path);
  },

  // S6 — the schema-gated export. A 409 (record already exists) is thrown as an
  // ApiError(status:409); records are immutable and never overwritten. P27.5: a
  // threaded `version` is sent as `If-Match: "<version>"`; a 412 stale write (or
  // 400 malformed token) is thrown as an ApiError carrying the parsed body.
  async exportRecord(id: string, version?: string): Promise<ApiExportResponse> {
    const path = `/experiments/${enc(id)}/export`;
    const res = await request(path, {
      method: 'POST',
      // Truthiness guard: never send an empty `If-Match: ""` for a blank token.
      ...(version ? { headers: { 'If-Match': `"${version}"` } } : {}),
    });
    if (res.ok) return readJson<ApiExportResponse>(res, path);
    throw await mutationError(res, path);
  },

  // The three signals — each fetched from its own endpoint, never merged here.
  validate(id: string): Promise<ApiValidateResult> {
    return postJson<ApiValidateResult>(`/experiments/${enc(id)}/validate`);
  },

  // P36.3 — the standalone Governance & Safety validator. No experiment id:
  // a candidate record (already parsed client-side) is POSTed as-is and
  // checked against the official schema server-side. Unlike `postJson`, a
  // non-OK response's typed body (`{error, message}` — non-object / invalid
  // JSON / oversized) is parsed and attached to the thrown ApiError so the
  // screen can show the server's exact reason instead of a generic status.
  async validateRecord(json: unknown): Promise<ApiValidateRecordResult> {
    const path = '/validate/record';
    const res = await request(path, {
      method: 'POST',
      body: JSON.stringify(json),
    });
    if (!res.ok) {
      const err = httpError(res, path);
      // An intercepted sign-in page carries no typed {error,message} body.
      if (err.htmlIntercept) throw err;
      const typed = (await res.json().catch(() => undefined)) as
        | ApiValidateRecordError
        | undefined;
      throw new ApiError(typed?.message ?? err.message, {
        status: res.status,
        path,
        contentType: err.contentType,
        body: typed,
      });
    }
    // Previously an unparseable 200 body silently resolved to `undefined` and
    // was cast to a result; now it is a typed ApiError like every other read.
    return readJson<ApiValidateRecordResult>(res, path);
  },

  // P36.6 — the read-only Schema Reference browser (renamed from "Schema &
  // Vocabulary" by P36R S8). Serves the vendored
  // official schema + vocabulary/*.json verbatim (reference plane, never truth
  // enforcement) — this client only parses the envelope, it never re-derives
  // or projects any part of it.
  getSchema(): Promise<ApiSchemaResponse> {
    return getJson<ApiSchemaResponse>('/schema');
  },

  audit(id: string): Promise<ApiAuditResponse> {
    return postJson<ApiAuditResponse>(`/experiments/${enc(id)}/audit`);
  },

  getWarnings(id: string): Promise<ApiWarningsResponse> {
    return getJson<ApiWarningsResponse>(`/experiments/${enc(id)}/warnings`);
  },

  async getEvidence(id: string) {
    return (await getJson<ApiEvidenceResponse>(`/experiments/${enc(id)}/evidence`)).evidence;
  },

  // P28.5 — the typed evidence-SUPPORT classification for the current record,
  // bound to `record_rev`. A separate axis from validation/audit/advisory; the
  // client parses it, it never computes a class or a verdict.
  getEvidenceClassification(id: string): Promise<ApiEvidenceClassification> {
    return getJson<ApiEvidenceClassification>(
      `/experiments/${enc(id)}/evidence-classification`,
    );
  },

  // S5 — one cited source fixture, read-only (governance-gated to the allowlist).
  getSourcePreview(id: string, source: string): Promise<ApiSourcePreview> {
    return getJson<ApiSourcePreview>(
      `/experiments/${enc(id)}/source-preview?source=${enc(source)}`,
    );
  },

  // S5/S6 — the written record + sidecar content (null before export). Read-only:
  // the backend reads only the two files export wrote inside the workspace.
  getArtifacts(id: string): Promise<ApiArtifactsResponse> {
    return getJson<ApiArtifactsResponse>(`/experiments/${enc(id)}/artifacts`);
  },

  // P34.2 — the READ-ONLY grounded assistant resolver. A non-mutating POST (a
  // GET-like query carrying a JSON body): it resolves a free-form question
  // against the current record context and returns a source-labeled answer. It
  // sends NO If-Match (nothing is written) and inherits the optional Bearer auth
  // via request(). A non-2xx (empty/too-long question, unknown experiment) or a
  // network failure throws ApiError, which the caller renders as unavailable —
  // never a fabricated answer. It touches no mutation endpoint.
  askAssistant(
    id: string,
    body: { question: string; grounded_rev?: string },
  ): Promise<AssistantQueryResponse> {
    return postJson<AssistantQueryResponse>(`/experiments/${enc(id)}/assistant/query`, body);
  },

  // P34.4 — the RECORD-AGNOSTIC grounded resolver for the Project Memory surface,
  // which has NO record (so it has no experiment id and cannot use askAssistant —
  // that would 404). A non-mutating POST with NO experiment path param: a
  // project-memory question is answered from the memory reader (leads to verify,
  // never a verdict); any record question is honestly refused server-side. Inherits
  // the optional Bearer auth via request() and sends no If-Match (nothing is
  // written). The response carries a null `record_rev`/`version` (no record). A
  // non-2xx or network failure throws ApiError, rendered as unavailable — never a
  // fabricated answer. It touches no mutation endpoint and loads/creates no record.
  askMemory(body: { question: string }): Promise<AssistantQueryResponse> {
    return postJson<AssistantQueryResponse>('/assistant/memory/query', body);
  },

  // Memory plane (advisory only; never gates).
  getGraphStatus(): Promise<ApiGraphStatus> {
    return getJson<ApiGraphStatus>('/graph/status');
  },

  // P24.4 — Source Index: the served-allowlist file list + one file's
  // provenance detail. Metadata/provenance only — never file content.
  getMemoryFiles(): Promise<ApiMemoryFilesResponse> {
    return getJson<ApiMemoryFilesResponse>('/memory/files');
  },

  getMemoryFile(path: string): Promise<ApiMemoryFileResponse> {
    return getJson<ApiMemoryFileResponse>(`/memory/file?path=${enc(path)}`);
  },

  // P24.5 — Concept Lookup: the 19 curated concepts + one concept's anchor
  // provenance and leads. Metadata/provenance only — never file content.
  getMemoryConcepts(): Promise<ApiMemoryConceptsResponse> {
    return getJson<ApiMemoryConceptsResponse>('/memory/concepts');
  },

  getMemoryConcept(id: string): Promise<ApiMemoryConceptResponse> {
    return getJson<ApiMemoryConceptResponse>(`/memory/concepts/${enc(id)}`);
  },

  // P36.2 — the Project Memory "Graph" tab: a deterministic, capped,
  // served-file reference projection (nodes/edges/communities). Metadata/
  // provenance only — never file content, never the full un-embedded source
  // graph. One fetch; the screen does all search/filter/select client-side.
  getMemoryGraph(): Promise<ApiMemoryGraphResponse> {
    return getJson<ApiMemoryGraphResponse>('/memory/graph');
  },

  // P36V.1 Unit F — the DEEP (symbol-level) layer behind the Explore canvas's
  // semantic zoom. A SEPARATE route from `/memory/graph` on purpose: it is
  // ~500 kB of columnar rows, so it is fetched LAZILY — only once the reader
  // has actually zoomed past the first level-of-detail threshold — and never on
  // a plain visit to Project Memory. Metadata/provenance only, never file
  // content; its structure is a point-in-time index of the snapshot's
  // `built_at_commit`, which the surface states explicitly.
  getMemoryGraphDetail(): Promise<ApiGraphDetailResponse> {
    return getJson<ApiGraphDetailResponse>('/memory/graph/detail');
  },

  // P26.4 — grouped truth+memory search. One query fans out to the workspace
  // (truth plane) and memory (advisory) groups server-side; this method only
  // builds the query string and parses the envelope, never merges/ranks the
  // two groups itself. Options are appended in a fixed order, and only when
  // the caller actually provided them (the frozen contract test asserts the
  // exact URL for both the full-options and q-only calls).
  search(
    q: string,
    opts?: { scope?: ApiSearchScope; limit?: number; offset?: number },
  ): Promise<ApiSearchResponse> {
    let path = `/search?q=${enc(q)}`;
    if (opts?.scope !== undefined) path += `&scope=${enc(opts.scope)}`;
    if (opts?.limit !== undefined) path += `&limit=${opts.limit}`;
    if (opts?.offset !== undefined) path += `&offset=${opts.offset}`;
    return getJson<ApiSearchResponse>(path);
  },

  // P30.3 — the cross-record runtime projection consumer (client half of the
  // P30.1 provider). Fetches the SAFE, current-by-construction projection of
  // ALL records (confirmed facts + freshness only — no draft values, evidence
  // bodies, or per-field classifications) so the deterministic crossRecordTriage
  // function can answer "which records need attention / are blocked / have
  // conflicts / are exportable now". This is a LEAD surface, not record truth —
  // opening a match hands off to a direct Workspace load. The typed filters map
  // 1:1 to the backend query params; each is appended only when provided, in a
  // fixed order, and this method only parses the {records,total} envelope (it
  // never computes triage or a verdict itself).
  getRuntimeRecords(filters?: {
    status?: string;
    workflow_state?: 'blocked' | 'reopened' | 'current';
    artifact?: 'none' | 'current' | 'stale';
    has_conflict?: boolean;
    limit?: number;
    offset?: number;
  }): Promise<{ records: RuntimeRecord[]; total: number }> {
    let path = '/runtime/records';
    const params: string[] = [];
    if (filters?.status !== undefined) params.push(`status=${enc(filters.status)}`);
    if (filters?.workflow_state !== undefined)
      params.push(`workflow_state=${enc(filters.workflow_state)}`);
    if (filters?.artifact !== undefined) params.push(`artifact=${enc(filters.artifact)}`);
    if (filters?.has_conflict) params.push('has_conflict=true');
    if (filters?.limit !== undefined) params.push(`limit=${filters.limit}`);
    if (filters?.offset !== undefined) params.push(`offset=${filters.offset}`);
    if (params.length > 0) path += `?${params.join('&')}`;
    return getJson<{ records: RuntimeRecord[]; total: number }>(path);
  },

  // S2 — run the synthetic pipeline; `draft_only` stops at the blockers.
  //
  // The backend now REFUSES (409 `demo_target_drifted`) rather than re-seeding
  // over a canonical scenario a user has edited, and its refusal body names the
  // reason and the scenario. `postJson` would have discarded that body —
  // `httpError` never reads one — leaving the screen with a bare "Request failed
  // (409)." and no way to tell a protective refusal from a broken backend. So
  // the 409 body is attached to the thrown ApiError, exactly as `mutationError`
  // does for the 412 stale-write payload; `mutationError` itself is deliberately
  // untouched, since its 409 (export immutability) callers expect the plain
  // shape. An HTML intercept is excluded: an edge sign-in page carries no
  // refusal payload. Every other status keeps the previous behaviour.
  async runDemo(mode: 'draft_only' | 'full' = 'draft_only'): Promise<ApiDemoRunResponse> {
    const path = '/demo/run';
    const res = await request(path, { method: 'POST', body: JSON.stringify({ mode }) });
    if (res.ok) return readJson<ApiDemoRunResponse>(res, path);
    const err = httpError(res, path);
    if (err.htmlIntercept || res.status !== 409) throw err;
    throw new ApiError(err.message, {
      status: res.status,
      path,
      contentType: err.contentType,
      body: await res.json().catch(() => undefined),
    });
  },

  // P26.0b / R1 — the guarded example-workspace reset. Preview (200) and ALL FOUR
  // safe refusals carry the SAME typed body, so — like blockUpload — we read the
  // JSON on those statuses instead of throwing:
  //
  //   403  not in synthetic-only mode
  //   409  wrong confirmation phrase, or an ambiguous record is present
  //   428  `plan_digest` omitted        (R1 precondition, nothing was written)
  //   412  `plan_digest` stale          (R1 precondition; see below — a 412 does
  //                                      NOT guarantee that nothing was written)
  //
  // C2 — WHY THE 412 LINE NO LONGER SAYS "nothing was written". The precondition is
  // also re-checked per record, inside that record's own lock, immediately before
  // that record is touched, so a write landing mid-reset is refused instead of
  // destroyed and the reset stops there with earlier records already restored. The
  // 428 line above is still exactly right: an omitted digest is rejected before any
  // mutation. No field on the body separates the two 412 cases, so no caller of this
  // module can tell them apart — which is why the dialog's copy claims neither. That
  // absence is a CHOICE, not a limit: the server computes the boolean and does not
  // serialize it. The reasoning is recorded in `__tests__/reset-claim-parity.test.tsx`.
  //
  // 412/428 are refusals, not failures: the body carries the CURRENT `plan_digest`
  // and refreshed counts, which is exactly what the caller needs to show the
  // operator what changed. Throwing them away as HTTP errors would leave the dialog
  // saying "request failed" about the one outcome it most needs to explain.
  //
  // Only a status outside {200,403,409,412,428} (or a network failure, which
  // request() already turns into an unreachable ApiError) is a genuine error.
  // Preview sends only { mode }; execute adds the phrase and the digest.
  async resetDemo(
    mode: 'preview' | 'execute',
    confirmation?: string,
    planDigest?: string,
  ): Promise<ApiDemoResetResult> {
    // A missing digest is deliberately NOT substituted or invented here: it is sent
    // as absent so the SERVER refuses (428). The client never decides that a reset
    // may proceed.
    const payload =
      mode === 'execute' ? { mode, confirmation, plan_digest: planDigest } : { mode };
    const res = await request('/demo/reset', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (RESET_RESULT_STATUSES.includes(res.status)) {
      // readJson still guards the HTML-intercept case: an edge sign-in page can
      // carry any status, and it is never a typed reset result.
      const body = await readJson<unknown>(res, '/demo/reset');
      // FAIL CLOSED on a body this client cannot interpret. See
      // `isResetResult` — a half-built result leaves a destructive control armed.
      if (!isResetResult(body)) {
        throw new ApiError(
          `The reset API answered ${res.status} with a body that is not a reset result.`,
          { status: res.status, path: '/demo/reset', contentType: contentTypeOf(res) },
        );
      }
      return body;
    }
    throw httpError(res, '/demo/reset');
  },

  // S2 — governance seam. Always 403; we read the verbatim reason from the body.
  async blockUpload(): Promise<ApiUploadsBlocked> {
    const res = await request('/uploads', { method: 'POST' });
    return readJson<ApiUploadsBlocked>(res, '/uploads');
  },

  // S3 — the full record bundle in one concurrent load. The nine endpoints stay
  // separate values in the result; nothing is merged into a single verdict.
  //
  // `artifacts` is the NINTH, added for the record-identity sections (Record Info
  // + Relationships). It is the SAME EXISTING ROUTE `getExportReadiness`,
  // `getEvidenceBundle` and `getExperimentGraphBundle` already read — no backend
  // route was added or changed — and it is the only thing that serves an official
  // record's own top-level values (`isaac_record_version`, `record_id`, the
  // classification trio, `timestamps.created_utc`) and its `links` block. It is
  // fetched with the bundle rather than lazily because those sections render from
  // the same load as the field blocks beside them, and a second load would let the
  // two disagree about the same record.
  async getRecordBundle(id: string): Promise<RecordBundle> {
    const [detail, groups, pending, validate, audit, warnings, evidence, graph, artifacts] =
      await Promise.all([
        this.getExperiment(id),
        this.getDraftGroups(id),
        this.getPending(id),
        this.validate(id),
        this.audit(id),
        this.getWarnings(id),
        this.getEvidence(id),
        this.getGraphStatus(),
        this.getArtifacts(id),
      ]);
    return { detail, groups, pending, validate, audit, warnings, evidence, graph, artifacts };
  },

  // S6 — the export readiness view: the three signals + the gate inputs, each
  // from its own endpoint, fetched together but kept separate (never merged).
  // `artifacts` lets View/Download work on a fresh load of an exported record.
  async getExportReadiness(id: string): Promise<ExportReadinessBundle> {
    const [detail, pending, validate, audit, warnings, graph, artifacts] =
      await Promise.all([
        this.getExperiment(id),
        this.getPending(id),
        this.validate(id),
        this.audit(id),
        this.getWarnings(id),
        this.getGraphStatus(),
        this.getArtifacts(id),
      ]);
    return { detail, pending, validate, audit, warnings, graph, artifacts };
  },

  // S5 — the evidence explorer: the trail + the exported artifacts + memory
  // freshness, then the previews of every source fixture the evidence cites
  // (fetched after so we know which fixtures are actually referenced).
  async getEvidenceBundle(id: string): Promise<EvidenceBundle> {
    const [detail, evidence, artifacts, graph, classification] = await Promise.all([
      this.getExperiment(id),
      this.getEvidence(id),
      this.getArtifacts(id),
      this.getGraphStatus(),
      this.getEvidenceClassification(id),
    ]);
    const files = citedSourceFiles(evidence);
    const previews = await Promise.all(files.map((f) => this.getSourcePreview(id, f)));
    const sourcePreviews: Record<string, ApiSourcePreview> = {};
    files.forEach((f, i) => {
      sourcePreviews[f] = previews[i];
    });
    return { detail, evidence, artifacts, graph, sourcePreviews, classification };
  },

  /**
   * The EXPERIMENT-SCOPED graph bundle — seven EXISTING endpoints, fetched
   * concurrently and kept as separate values.
   *
   * No backend route was added or changed for the experiment graph: every fact
   * it draws is already served to the record screens. It is fetched lazily (only
   * when the Graph view is opened) and re-fetched per mount rather than cached,
   * which is what makes a stale experiment graph structurally impossible.
   */
  async getExperimentGraphBundle(id: string): Promise<ExperimentGraphBundle> {
    const [detail, groups, evidence, artifacts, validate, warnings, classification] =
      await Promise.all([
        this.getExperiment(id),
        this.getDraftGroups(id),
        this.getEvidence(id),
        this.getArtifacts(id),
        this.validate(id),
        this.getWarnings(id),
        this.getEvidenceClassification(id),
      ]);
    return { detail, groups, evidence, artifacts, validate, warnings, classification };
  },
} as const;

/** Distinct source-file basenames referenced by any evidence entry (order kept). */
/**
 * The source fixtures the trail cites, read DEFENSIVELY, per entry.
 *
 * This is inside `getEvidenceBundle`'s async body, which is why its shape
 * assumptions were load-bearing in the worst way: on `77820bf` a single entry
 * whose `evidence` was not an array (measured with `evidence: 7`) threw here,
 * the WHOLE bundle promise rejected, and the Evidence view rendered the
 * "Backend Not Running" alert — blaming the server for one malformed item in one
 * record. One bad entry now contributes no cited files and nothing else changes.
 */
function citedSourceFiles(evidence: ApiEvidenceEntry[]): string[] {
  const seen: string[] = [];
  for (const entry of Array.isArray(evidence) ? evidence : []) {
    const list = entry && Array.isArray(entry.evidence) ? entry.evidence : [];
    for (const ev of list) {
      const file = ev && typeof ev === 'object' ? ev.source_file : undefined;
      if (typeof file === 'string' && file && !seen.includes(file)) seen.push(file);
    }
  }
  return seen;
}

export type IsaacApi = typeof api;
