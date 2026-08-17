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
import { useEffect, useId, useRef, useState } from 'react';
import { Link, useInRouterContext } from 'react-router-dom';
import { AudioWaveform, Check, Copy, TriangleAlert } from './icons';
import { API_BASE, isHostedBuild, RUN_COMMAND } from '../lib/api';
import type { ApiError } from '../lib/api';
import { isExampleRecordId } from '../lib/exampleRecords';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { useWorkspaceScope } from '../lib/workspaceScope';
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
 * - `not_found`  — HTTP 404 the API attributed to the RECORD
 *                  (`experiment_not_found`), or — no reason observed — for a path
 *                  that names one record and nothing else. That record is not
 *                  there. Unchanged copy.
 * - `record_part_not_found`
 *                — HTTP 404 the API attributed to a PART of a record
 *                  (`run_not_found`, `source_not_allowed`), or for a path that
 *                  read one. It names the part that was read and refuses to claim
 *                  the experiment is absent.
 * - `example_workspace_ended`
 *                — the same 404 as `not_found`, for one of the five BUILT-IN
 *                  WORKED-EXAMPLE ids, while NO worked-example session is open.
 *                  "It may not have been created yet" is the wrong explanation for
 *                  that id, so this branch gives the right one: worked-example
 *                  records live only in a temporary workspace, and none is open.
 * - `path_not_found`
 *                — HTTP 404 for anything else — a collection read, a build-level
 *                  read, or a request whose path was not recorded. See
 *                  `isRecordPath` for why this branch had to exist.
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
export type DownKind =
  | 'not_found'
  | 'example_workspace_ended'
  | 'record_part_not_found'
  | 'path_not_found'
  | 'auth'
  | 'http_error'
  | 'unreachable'
  | 'local';

export interface DownCopy {
  kind: DownKind;
  title: string;
  /** Body sentences, in order; each renders as its own paragraph. */
  lines: string[];
  /** Local builds only — the run command is the actionable remedy there. */
  showRunCommand: boolean;
  /** Whether reloading (re-entering the identity flow) is offered. */
  offerReload: boolean;
  /**
   * Whether a link back to My Experiments is offered.
   *
   * Set ONLY where navigating actually helps — i.e. where the API answered, so the
   * rest of the app is reachable. It stays false for every branch whose cause is
   * "the API did not answer": a link into another surface that is equally broken is
   * the same small lie `DownBrand` refuses to tell.
   */
  offerExperimentsLink: boolean;
}

/**
 * Does this failed API path name ONE record AND NOTHING BELOW IT?
 *
 * WHY THIS PREDICATE EXISTS. Every 404 used to render "Record Not Found — this
 * experiment id is not in the local workspace", from all 14 call sites. That is
 * true of `GET /api/experiments/{id}`, and FALSE of everything
 * else that can answer 404 — and the false case was reached. Browser testing
 * caught My Experiments rendering it: a reload holding an expired worked-example
 * pointer issued `GET /api/experiments`, the backend rejected the unknown session
 * with a 404, and this panel reported a LIST failure to the reader as a missing
 * RECORD, on a screen whose truthful state was the ordinary empty workspace. The
 * same wording was reachable on `/api/runtime/records`, `/api/memory/*` and
 * `/api/graph/*`, where "experiment id" names nothing at all.
 *
 * The shape is exact rather than heuristic: `api.ts` builds every per-record read
 * as `/experiments/{id}` plus an optional suffix, and the only other `/experiments`
 * path is the bare collection. `/memory/concepts/{id}` is deliberately NOT matched —
 * a concept is not an experiment.
 *
 * `$` NARROWED THIS PREDICATE, and is only PART of the second fix. The pattern used
 * to be `/^\/experiments\/[^/]/` — no anchor — so it also matched EVERY sub-read
 * `api.ts` builds under a record (`/draft`, `/pending`, `/answers`, `/edit`, `/runs`,
 * `/runs/{run_id}`, `/runs/{run_id}/check`, `/export`, `/validate`, `/evidence`,
 * `/source-preview`, `/artifacts`, `/assistant/query`, …). MEASURED, rather than
 * counted by eye: 19 sub-read path literals → 17 distinct suffixes → 15 distinct
 * first segments, derived from `api.ts` by `backend-down-state.test.tsx` and asserted
 * there, so the figure cannot go stale silently. (An earlier revision of this comment
 * said "all EIGHTEEN sub-reads"; that number matched none of the three measurements
 * and is withdrawn.) A 404 from any of them rendered "this experiment id is not in the
 * workspace", while the backend DELIBERATELY distinguishes four reasons it can 404
 * under this prefix: `experiment_not_found` (`routes.py::_not_found`),
 * `run_not_found` (`routes.py::_run_not_found`, whose docstring says collapsing
 * them "would tell a client to go looking in the wrong place"),
 * `source_not_allowed`, and `tutorial_session_not_found` from the scope
 * dependency. The client collapsed all four.
 *
 * THE ANCHOR ALONE WOULD NOT HAVE BEEN A CORRECT FIX, which is why `downCopy` reads
 * `ApiError.reason` first and consults this predicate only when no reason was
 * observed. The record screens read an experiment and its parts CONCURRENTLY —
 * `api.getRecordBundle` issues seven experiment-scoped reads in one `Promise.all` —
 * so on a genuinely missing experiment the path that reaches the panel is
 * nondeterministic. See the comment in `downCopy` for the citation and for a
 * correction to an earlier revision of it. This predicate answers a question about
 * a PATH; it is not, on its own, evidence about a record.
 *
 * A query string is deliberately still matched: `?scope=x` on a bare record read
 * does not stop it naming that one record. A `/` after the id does.
 */
export function isRecordPath(path: string | undefined): boolean {
  return path !== undefined && /^\/experiments\/[^/]+$/.test(path);
}

/**
 * The first path segment BELOW `/experiments/{id}` — the PART that was read — or
 * `undefined` when the path does not read one.
 *
 * STRUCTURAL, and used for the BRANCH DECISION only; the reader never sees this
 * string when it is one this build recognises (see `SUB_RESOURCE_LABELS`). The
 * query string is stripped because `/source-preview?source=…` is the one sub-read
 * that carries one, and the segment — not the parameter — is what names the
 * subject.
 */
export function recordSubResource(path: string | undefined): string | undefined {
  if (path === undefined) return undefined;
  return /^\/experiments\/[^/]+\/([^/?#]+)/.exec(path)?.[1];
}

/**
 * The EXPERIMENT ID this failed path named, or `undefined` when it named none.
 *
 * Deliberately matches BOTH `/experiments/{id}` and `/experiments/{id}/…`, because
 * the record screens read an experiment and its parts concurrently and the path
 * that reaches the panel is whichever promise rejected first — see the long note in
 * `downCopy`. Reading the id from the PATH rather than from the router means it is
 * the id THIS REQUEST asked about, not whatever the address bar says now.
 *
 * The query string is stripped: `?scope=…` on a record read does not change which
 * id was named.
 */
export function recordPathExperimentId(path: string | undefined): string | undefined {
  if (path === undefined) return undefined;
  return /^\/experiments\/([^/?#]+)/.exec(path)?.[1];
}

/**
 * PRODUCT NAMES for the parts of a record, keyed by the wire segment `api.ts`
 * puts in the URL.
 *
 * WHY THIS EXISTS, and why it is a map rather than the raw segment. Without it
 * this panel rendered the backend's own path vocabulary into product copy —
 * "a read of “ingestion”", "a read of “evidence-classification”" — which is the
 * "backend-sourced jargon on product screens" class `CLAUDE.md` §11 records as
 * still open. The segment is a wire name; the reader is a scientist.
 *
 * WHY A MAP IS SAFE HERE, WHICH IT WOULD NOT BE ON ITS OWN. A hand-maintained
 * translation table rots silently the moment `api.ts` gains a sub-read: the new
 * segment gets no entry, and the panel quietly falls back to leaking it. That
 * objection is answered by a TEST, not by doing without the map —
 * `backend-down-state.test.tsx` derives the sub-resource suffixes `api.ts`
 * actually builds by reading `api.ts` itself, and fails if any of them has no
 * entry here. A new suffix therefore breaks CI loudly instead of leaking quietly.
 *
 * The keys are wire segments and are deliberately NOT re-cased or re-spelled;
 * only the values are copy.
 */
export const SUB_RESOURCE_LABELS: Readonly<Record<string, string>> = {
  answers: 'saved answers',
  artifacts: 'exported artifacts',
  assistant: 'an assistant answer',
  audit: 'the evidence audit',
  draft: 'the draft fields',
  edit: 'a field edit',
  evidence: 'the evidence trail',
  'evidence-classification': 'evidence support',
  export: 'the export',
  ingestion: 'a CSV comparison',
  notes: 'the unmapped notes',
  pending: 'the missing fields',
  // The three `/revisions…` reads. "Submission history" is the product's word for
  // them; `revisions` is the wire segment and never reaches a scientist.
  revisions: 'the submission history',
  runs: 'the measurement runs',
  'source-preview': 'a reference source file',
  validate: 'validation',
  warnings: 'advisory warnings',
};

/**
 * The part that was read, in product words when this build knows the segment and
 * VERBATIM when it does not.
 *
 * THE FALLBACK IS DELIBERATE AND IS THE LESSER OF TWO EVILS. An unrecognised
 * segment can only arrive from a path this build did not shape, or from a
 * sub-read added to `api.ts` without an entry above — and in that case naming the
 * segment we observed is honest but jargon, while inventing a friendly name for a
 * part we do not recognise would be a fabrication. Honest jargon wins, and the
 * coverage test above keeps the second case from reaching a user.
 *
 * THE QUOTES CARRY THAT DISTINCTION rather than decorating the sentence: a
 * recognised part is named in the app's own words and reads as prose, while an
 * unrecognised one is quoted, marking it as the verbatim token this client
 * observed in the URL and not as a name the product uses.
 */
function subResourceLabel(segment: string): string {
  return SUB_RESOURCE_LABELS[segment] ?? `“${segment}”`;
}

/**
 * Classify + phrase a failure. Exported and pure so both render sites (this
 * panel and the ⌘K search dialog) share ONE source of copy and cannot drift.
 *
 * `hosted` is injectable only so tests can exercise a hosted build without a
 * separate bundle; production always uses the compile-time `isHostedBuild`.
 *
 * `scope` IS THE WORKSPACE SCOPE AT RENDER TIME (`null` = the ordinary workspace),
 * and is OMITTED — not defaulted — by a caller that does not know it. Omission is
 * the fail-safe value: only `null` can unlock the `example_workspace_ended` branch,
 * so a caller unaware of this argument keeps today's copy rather than gaining a
 * claim it never supplied evidence for.
 *
 * WHY RENDER-TIME SCOPE IS SOUND HERE, GIVEN THAT THIS FUNCTION IS PURE AND THE
 * SCOPE MAY HAVE MOVED SINCE THE REQUEST. The generic 404 branch below refuses to
 * name an expired session for exactly that reason, and this branch does not
 * contradict it. It is used ONLY in the `scope === null` direction, where both
 * possible histories make the same sentence true: either the request also carried no
 * session (a deep link or a reload — the record is genuinely not in the ordinary
 * workspace), or it carried one that has since been disposed (the walkthrough just
 * ended — the temporary workspace and its records are gone). "This is a
 * worked-example id and no worked-example workspace is open" holds in both, and
 * neither is a claim about a cause the response did not evidence. A non-`null`
 * scope never takes the branch.
 */
export function downCopy(
  error?: ApiError,
  hosted: boolean = isHostedBuild,
  scope?: string | null,
): DownCopy {
  const status = error?.status;

  /*
   * AN HTML-BODIED 404 IS NOT ISAAC'S 404, and until this guard existed both 404
   * branches below treated it as one.
   *
   * `httpError` copies the status and nothing else, so a sign-in page served with a
   * 404 by the edge arrived here indistinguishable from `{"error":
   * "experiment_not_found"}` — and on a record path it was reported to the reader as
   * "Record Not Found — this experiment id is not in the workspace". That is a
   * definitive claim about a record's existence, made from a response that never
   * reached the application. `api.ts:498-503` already refuses to read a typed reason
   * out of such a response for exactly this reason; this is the same rule applied to
   * the copy, not a new one.
   *
   * The `auth` branch below is where it lands instead, which is the honest place: the
   * signal actually observed is HTML on an API path, and that branch says so and
   * offers the reload that re-enters the identity flow.
   */
  const interceptedByEdge = error?.htmlIntercept === true;

  /*
   * THE BACKEND'S OWN REASON WINS OVER THE PATH, and the path is only a fallback.
   *
   * WHY, and this is the part a later reader will be tempted to "simplify" back into
   * a path test. The record screens read an experiment and its PARTS CONCURRENTLY.
   * `api.getRecordBundle` (`api.ts:1136-1147`) issues SEVEN experiment-scoped reads
   * in ONE `Promise.all` — `GET /experiments/{id}` plus `/draft`, `/pending`,
   * `/validate`, `/audit`, `/warnings`, `/evidence` — so six of the seven are
   * sub-resource paths. When the experiment is genuinely absent all seven 404, and
   * `Promise.all` rejects with WHICHEVER REJECTED FIRST — a race. The same fan-out
   * shape recurs in `getEvidenceBundle`'s FIRST `Promise.all` (1 exact + 3
   * sub-resource), in `getExportReadiness`, in the experiment graph bundle, and at
   * `GuidedCompletion.tsx:46`; `useRecordSession.ts:226` awaits only SUB-resource
   * reads, so there a path rule could never reach the record claim at all, race or
   * no race.
   *
   * A purely path-based rule is therefore unsound in both directions: keep it broad
   * and a `source_not_allowed` 404 claims the record is missing (the reachable false
   * claim), narrow it to the exact record path and a genuinely absent experiment
   * renders generic copy whenever a sub-read's rejection happens to win the race —
   * nondeterministic copy for one underlying truth, which is a different way of
   * hiding a real 404.
   *
   * CORRECTION, RECORDED RATHER THAN OVERWRITTEN, because the withdrawn version is
   * the plausible-sounding one. An earlier revision of this comment grounded the race
   * on "`getEvidenceBundle` fetches `getExperiment(id)` and every
   * `getSourcePreview(id, file)` in ONE `Promise.all`". THAT IS FALSE and is
   * withdrawn. `getEvidenceBundle` is TWO SEQUENTIAL `Promise.all`s
   * (`api.ts:1172-1180`) and the previews are deliberately fetched second, "so we
   * know which fixtures are actually referenced": when the experiment is genuinely
   * absent the FIRST bundle rejects and `getSourcePreview` is never called, so
   * `source_not_allowed` is reachable only once the record has provably been read.
   * There is no race between `getExperiment` and `getSourcePreview` in either
   * direction. `source_not_allowed` remains a real non-experiment 404 reason and the
   * reachable false claim this branch table removes — only the RACE claim about it
   * was wrong. The conclusion is unchanged; its evidence is now `getRecordBundle`.
   *
   * A REASON-BASED RULE IS IMMUNE TO THE RACE: `experiment_not_found` says the record
   * is absent no matter which promise lost, and `run_not_found` /
   * `source_not_allowed` say it is not, likewise. `httpErrorWithReason` reads that
   * reason only from a JSON 404 body and never from an HTML one, so
   * `interceptedByEdge` still wins over every branch below.
   *
   * `undefined` MEANS NOT OBSERVED — a POST failure, a non-JSON body, an empty body,
   * or `{"detail": …}` from an unrouted path. Only then does the path shape decide,
   * and an unrecognised reason falls through to the generic branch rather than to any
   * confident claim.
   */
  const reason = interceptedByEdge ? undefined : error?.reason;
  const subResource = interceptedByEdge ? undefined : recordSubResource(error?.path);

  /*
   * THE RECORD ITSELF IS ABSENT. Today's copy and behaviour, unchanged.
   *
   * Reached either because the API said `experiment_not_found` — which is now
   * honoured ON A SUB-RESOURCE PATH TOO, so the race above cannot downgrade a real
   * missing record to generic copy — or, with no reason observed, because the path
   * names one record and nothing below it.
   *
   * THE REASON IS HONOURED ONLY UNDER `/experiments/{id}`, and that constraint is
   * load-bearing rather than defensive. This is the most definitive sentence the
   * panel can say, so it may only be reached by a request that named a record: the
   * reason widens WHERE under that prefix the claim is allowed (the record path and
   * its parts, instead of the record path alone), and it must not widen the claim to
   * paths that name no experiment. Without the constraint a 404 carrying this reason
   * on `/memory/concepts/{id}`, `/graph/status` or `/schema` would render "this
   * experiment id is not in the workspace" over a path that has no experiment id in
   * it — the exact class of defect `isRecordPath` was introduced to end, and one
   * that the first revision of this branch reintroduced. Latent rather than live
   * today (every `_not_found(` call site in `routes.py` is inside an
   * `/experiments/{experiment_id}` handler), and pinned by test so it stays that way.
   *
   * One behaviour DID change here, and it is a correction rather than a regression: a
   * 404 carrying `tutorial_session_not_found` on a record path no longer takes this
   * branch. That reason is raised by the scope dependency BEFORE any record work
   * happens (`routes.py::tutorial_scope`), so it is evidence about a dead
   * worked-example session and none at all about whether the record exists. It falls
   * through to the generic branch, which is what the panel can honestly say.
   */
  const underOneRecord = isRecordPath(error?.path) || subResource !== undefined;
  const recordAbsent =
    status === 404 &&
    !interceptedByEdge &&
    ((reason === 'experiment_not_found' && underOneRecord) ||
      (reason === undefined && isRecordPath(error?.path)));

  /*
   * THE RECORD IS ABSENT AND IT IS A WORKED-EXAMPLE ID, WITH NO WALKTHROUGH OPEN.
   *
   * SAME 404, SAME EVIDENCE, DIFFERENT EXPLANATION. The branch below is reached by
   * exactly the same signals; this one only overrides the SENTENCE, for the one id
   * class where "it may not have been created yet" is the wrong account of what
   * happened. The five built-in worked-example records ARE created — inside a
   * worked-example session, whose directory the backend discards when the
   * walkthrough ends. A reader who finishes the walkthrough and presses Back, or
   * who opens a bookmarked example link, is not looking at a malfunction.
   *
   * REACHED MOST EASILY BY `finishTutorial`, and reachable at all because the bounce
   * that normally protects a record surface CANNOT fire here:
   * `useWorkspaceScopeChanged` (`lib/workspaceScope.ts`) compares the scope now
   * against the scope AT MOUNT, so a COLD MOUNT in the ordinary workspace
   * (`null` → `null`) is not a change and nothing redirects. That is correct — there
   * was no change — which is precisely why the panel has to explain itself instead.
   *
   * NO CROSS-SCOPE READ, AND NO CLAIM OF ONE. `isExampleRecordId` is a build-time
   * set membership test (`lib/exampleRecords.ts`); no request is made, and the
   * backend is never asked to look outside the scope it was given —
   * `workspace.py:3587-3592` refuses that on purpose. The copy therefore says only
   * what is true of the id and of how worked-example workspaces work, and asserts
   * nothing about what any other scope holds.
   *
   * THE SCOPE SIGNAL IS PER-TAB, AND THE COPY IS WORDED TO MATCH — this is the one
   * thing to get right here, and the first draft got it wrong. `scope === null` comes
   * from `readTutorialSession()`, which reads **`sessionStorage`** (`lib/tutorialSession.ts`),
   * chosen deliberately so the pointer dies with the tab. So `null` means "THIS TAB
   * holds no session", NOT "no session exists". A reader with the walkthrough open in
   * tab A who opens a bookmarked example link in tab B lands here while their
   * walkthrough is very much alive — and that is the ORDINARY way to arrive, since a
   * pasted link is the motivating case for this branch existing at all.
   *
   * An earlier revision said "and none is open" and told that reader the API had
   * discarded "anything answered or exported inside it". Both were false in tab B, in
   * the same direction as the defect this branch removes — a per-tab fact stated as a
   * global one. The lines now say "this browser tab is not in one" and name the
   * possibility explicitly, so they are true whether the walkthrough ended or is still
   * running somewhere this page cannot see. `HelpAndTutorial.tsx` already draws the
   * same distinction ("if the check THIS TAB …"); this matches it.
   *
   * IT PROMISES NO RECOVERY. The discarded workspace is gone; the third line offers
   * a fresh walkthrough and says in the same breath that it is a new start, so the
   * one affordance named cannot be mistaken for a way back to the lost one.
   */
  if (recordAbsent && scope === null && isExampleRecordId(recordPathExperimentId(error?.path))) {
    return {
      kind: 'example_workspace_ended',
      title: 'Worked Example Not Open',
      lines: [
        'This id belongs to one of the five built-in worked-example records. Those records exist only inside a worked-example walkthrough, and this browser tab is not in one — so this id names nothing in the workspace you are viewing.',
        'A worked-example workspace is reachable only from the tab that opened it, and it is temporary: when that walkthrough ends the ISAAC API discards it, along with anything answered or exported inside it. If one is still open in another tab, carry on there — this page cannot reach it.',
        `Starting the walkthrough again from ${LABELS.navSettings} → ${LABELS.settingsTabHelp} opens a fresh worked-example workspace with new copies of these five records — a new start, not a way back into an earlier one.`,
      ],
      showRunCommand: false,
      offerReload: false,
      offerExperimentsLink: true,
    };
  }

  if (recordAbsent) {
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
      offerExperimentsLink: false,
    };
  }

  /*
   * A 404 ABOUT ONE PART OF A RECORD — which is NOT evidence that the record is
   * absent, and used to be reported as exactly that.
   *
   * THE REACHABLE FALSE CLAIM, and it is data-driven rather than hypothetical.
   * `api.getEvidenceBundle` previews every source file `citedSourceFiles(evidence)`
   * derives from the evidence itself, with no per-item catch, so ONE evidence entry
   * citing a file outside `ws.SOURCE_FILES` makes the backend answer `404 {"error":
   * "source_not_allowed"}` ("Only the two committed reference files may be
   * previewed"), rejects the whole bundle, and `EvidenceExplorer` — reading it
   * through `useFetch` — rendered "Record Not Found — this experiment id is not in
   * the workspace" for an experiment that exists and whose evidence had loaded fine.
   *
   * MEASURED ON THE DEPLOYED APP for the sibling reason, hosted commit `bd3effc`
   * (`v0.0.100`), 2026-08-10: `GET /krish/api/experiments` lists
   * `01KZM7HYJVQY1C0X3KFV805YT2`, so that record demonstrably EXISTS, while
   * `…/runs/01BOGUS0000000000000000000` answers `404 {"error":"run_not_found",…}`.
   * The unanchored `isRecordPath` matched that path too, so the panel contradicted a
   * listing the same deployment had just produced.
   *
   * `_run_not_found` is a separate body from `_not_found` BECAUSE, in its own words,
   * the record "exists and was read successfully and simply holds no run under that
   * id", and collapsing the two "would tell a client to go looking in the wrong
   * place". The client collapsed them.
   *
   * WHY THIS NAMES THE PART BUT NOT THE VERDICT, even with a reason in hand. When the
   * reason IS observed the panel could say "the record exists but holds no such run";
   * it deliberately does not, because the reason is evidence about the sub-resource
   * and the copy would then also have to be right about a race it did not witness.
   * What it states is the subject of the REQUEST — observed, in the URL this client
   * built — and it declines to state the subject of the 404. That understates rather
   * than overstates. Callers passing `onRetry` still render Retry, useful either way.
   *
   * A bare `/experiments/{id}` 404 does NOT land here — it took the branch above with
   * its copy unchanged. Nor does an `experiment_not_found` arriving on a sub-resource
   * path. Nor does a RECOGNISED HTML-bodied 404 — see the scope note on the generic
   * branch below for what "recognised" excludes, which this branch's first sentence
   * inherits verbatim.
   */
  if (
    status === 404 &&
    !interceptedByEdge &&
    (reason === 'run_not_found' || reason === 'source_not_allowed' || subResource !== undefined)
  ) {
    return {
      kind: 'record_part_not_found',
      title: 'Not Found',
      lines: [
        /*
         * The part is named only when the PATH carried it, in this build's own words
         * (`SUB_RESOURCE_LABELS`) rather than in the backend's path vocabulary.
         *
         * THE SECOND ARM IS UNREACHABLE THROUGH `api.ts` AND IS KEPT ANYWAY, as an
         * explicit anti-fabrication guard. Every `ApiError` this client raises carries
         * a path, and a reason-only entry to this branch therefore cannot happen in
         * production — but `downCopy` is exported and pure, the reason arms above can
         * be satisfied without a path, and the alternative to this sentence is
         * inventing a segment to fill the gap. It is exercised by test
         * (`backend-down-state.test.tsx`, "names no part when the path carried none")
         * so that "unreachable" stays a claim about `api.ts` rather than about
         * untested code.
         */
        subResource !== undefined
          ? `The ISAAC API answered HTTP 404 for a read of ${subResourceLabel(subResource)} under this experiment id, so this view has no server-derived data to show.`
          : 'The ISAAC API answered HTTP 404 for a read of one part of this experiment, so this view has no server-derived data to show.',
        'The request read one part of an experiment rather than the experiment itself, so this 404 does not establish that the experiment is missing — and this page does not claim it is.',
        'This prototype reads only server-derived truth — it will never show placeholder data.',
      ],
      showRunCommand: false,
      offerReload: false,
      offerExperimentsLink: false,
    };
  }

  /*
   * A 404 THAT IS NOT ABOUT A RECORD, said generically because the cause is not
   * observable from here.
   *
   * A 404 on a collection or build-level read has at least two plausible causes —
   * the worked-example session named in the request header no longer exists, or the
   * route is not served at this base path — and nothing in the response separates
   * them, so neither is asserted. In particular this does NOT name the expired
   * session: `downCopy` is pure in its arguments, the api scope at render time is
   * not necessarily the scope the failed request carried, and naming a cause we did
   * not observe is the same defect as the copy this replaces.
   *
   * A RECOGNISED HTML-BODIED 404 DOES NOT LAND HERE — see `interceptedByEdge` above.
   * Its first sentence would be false of one: the ISAAC API did not answer, an
   * intercept did.
   *
   * "RECOGNISED" IS THE WHOLE SCOPE OF THAT SENTENCE, and the gap is stated rather
   * than implied. `isHtml` matches `text/html` only, so a 404 carrying
   * `application/xhtml+xml`, or carrying NO `Content-Type` at all, is not detected as
   * an intercept and DOES land here (and in the branch above), where the claim that
   * the ISAAC API answered is unproven. That is a PRE-EXISTING class, not something
   * this branch table introduced: the generic wording made the identical claim before
   * `interceptedByEdge` existed, `isHtml` is unchanged, and every branch that names
   * the API inherits it. It is deliberately NOT fixed here — widening `isHtml` is a
   * change to how every API response is classified, which does not belong in a copy
   * correction — so treat this as a known, bounded limit of the intercept guard.
   *
   * WHAT THE WORKED-EXAMPLE BRANCH CHANGES ABOUT THAT GAP, recorded because it is a
   * real widening and not merely one more inheritor. An undetected intercept on an
   * example deep link used to produce the VAGUE claim ("may not have been created
   * yet"); it now produces a DETAILED and confident narrative about a discarded
   * walkthrough, for a response that never reached ISAAC. The frequency is unchanged
   * and no new path is opened — the guard is the same `isHtml` — but a wrong answer
   * stated confidently is worse than the same wrong answer stated vaguely, so the
   * cost of leaving `isHtml` alone went up by this branch, and a future decision to
   * widen it should count this among its reasons.
   *
   * NEITHER DOES A READ UNDER `/experiments/{id}/…` — that is the branch immediately
   * above, which can at least name the part that was read.
   *
   * ON A BARE RECORD PATH (`/experiments/{id}`, nothing below it) TWO KINDS OF 404 NOW
   * LAND HERE THAT USED TO CLAIM A MISSING RECORD: one carrying
   * `tutorial_session_not_found` (evidence about a dead worked-example session, none
   * about the record), and one carrying a reason this build does not recognise. Both
   * are cases where a subject was reported and it was not the record, so the generic
   * wording is the honest one — and an unknown reason must never be optimistically
   * mapped onto a branch that asserts something.
   *
   * THE PATH QUALIFIER ON THAT PARAGRAPH IS NECESSARY. On a SUB-RESOURCE path neither
   * of those two reaches this branch: `subResource !== undefined` satisfies the branch
   * above, so both land in `record_part_not_found`. The copy is honest either way —
   * that branch names the part that was read and refuses the record claim, which is
   * exactly as much as a dead session or an unknown reason supports — but an earlier
   * revision of this comment described a routing the code does not perform, and a
   * comment that misdescribes its own branch is how the next reader gets the branch
   * wrong. A third kind now lands here as well: `experiment_not_found` arriving on a
   * path that names no experiment (see `underOneRecord` above).
   *
   * A pathless 404 lands here too. Every `ApiError` this client raises carries a
   * path (`httpError`, `readJson` and `request`'s network branch all pass one), so
   * in production that is the case where the failure did not come from this client
   * at all — and with no subject observed, the narrower claim is the only honest one.
   *
   * No reload is offered: a reload does help when a dead session pointer is the
   * cause, but that is the cause we just said we cannot establish. The callers that
   * pass `onRetry` still render Retry.
   */
  if (status === 404 && !interceptedByEdge) {
    return {
      kind: 'path_not_found',
      title: 'Not Found',
      lines: [
        'The ISAAC API answered HTTP 404 for this request, so this view has no server-derived data to show.',
        'This prototype reads only server-derived truth — it will never show placeholder data.',
      ],
      showRunCommand: false,
      offerReload: false,
      offerExperimentsLink: false,
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
      offerExperimentsLink: false,
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
      offerExperimentsLink: false,
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
      offerExperimentsLink: false,
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
    offerExperimentsLink: false,
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
 *
 * THE MODULE NOW IMPORTS `Link`, AND THAT IS NOT AN EXCEPTION TO THE ABOVE — the
 * sentence would misdescribe its own module if it stopped here, so: the rule is
 * "no hook that THROWS without a provider". `useInRouterContext()` is
 * provider-optional by contract — it returns `false` outside a Router rather than
 * throwing — so it is used to DECIDE whether a `Link` may render, and the whole
 * actions wrapper is skipped when it cannot. `useLocation`/`useNavigate` would
 * throw and are still barred here. The bare-render path is exercised by tests,
 * because several suites mount `BackendDown` outside a Router.
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
  /* The workspace this surface is reading right now. Read from the tutorial store
     (a module store, no provider), so this stays safe from all 14 call sites —
     including the ⌘K dialog, which renders outside any screen. See `downCopy` for
     why the render-time value is sound in the one direction it is used. */
  const scope = useWorkspaceScope();
  /* `Link` needs a Router. `BackendDown` is unit-rendered bare in several suites,
     and a failure state that CRASHES the page it is explaining would be the worst
     possible regression, so the link is rendered only where routing exists. The
     copy never depends on this — it names Settings & API → Help & Tutorial in
     words, which stays findable with or without the shortcut. */
  const inRouter = useInRouterContext();
  const copy = downCopy(error, isHostedBuild, scope);
  const titleId = useId();
  return (
    <div className="fetch-state error" role="alert" aria-labelledby={titleId}>
      <span className="fetch-state-icon" aria-hidden="true">
        <TriangleAlert size={22} strokeWidth={2.2} />
      </span>
      <div className="fetch-state-body">
        <DownBrand />
        <h2 className="fetch-state-title" id={titleId}>
          {copy.title}
        </h2>
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
        {(copy.offerReload || (copy.offerExperimentsLink && inRouter) || onRetry) && (
          <div className="fetch-state-actions">
            {copy.offerExperimentsLink && inRouter && (
              <Link className="btn btn-primary fetch-state-link" to={ROUTES.experiments}>
                {LABELS.navExperiments}
              </Link>
            )}
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
