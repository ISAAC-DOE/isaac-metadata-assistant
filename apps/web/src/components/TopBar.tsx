import './chrome.css';
import { Link } from 'react-router-dom';
import { AudioWaveform, Shield, ChevronRight } from './icons';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { StatusChip } from './StatusChip';
import { HelpPanel } from './HelpPanel';
import { SearchDialog } from './SearchDialog';
import { useHealth } from '../lib/useHealth';
import { useTutorialState } from '../lib/tutorialController';
import type { ChipKind } from '../lib/status';
import type { ApiHealth, ApiHealthDatabase } from '../lib/types';

/**
 * An UNEXPECTED `health.mode`, capitalized for display, or `null` when the mode is
 * the expected one (or unknown).
 *
 * `synthetic-only` is the only mode this build boots in (`runtime_mode.py` refuses
 * to start in `real`), and a missing/failed health check tells us nothing — in both
 * of those cases the chip names the SCOPE the reader is looking at instead. But a
 * real value we did not anticipate must be surfaced, visibly and distinctly, rather
 * than masked behind a friendly scope label. This chip is the only surface in the
 * app that reports it, which is why it is still rendered in every scope.
 *
 * The MODE'S OWN NAME is untouched by any label change here: `synthetic-only` is
 * what `/api/health` reports, what `runtime_mode.py` enforces, and what the machine
 * contract carries. Only reader-facing words are decided in this file.
 */
function anomalousMode(mode: string | undefined): string | null {
  if (!mode || mode === 'synthetic-only') return null;
  return mode.charAt(0).toUpperCase() + mode.slice(1);
}

/**
 * Slice 2A — the chip's SECOND axis, independent of `mode`.
 *
 * The deployment may be configured to run a protected, read-only diagnostic
 * against an isolated test database holding production-derived records. An
 * unqualified workspace chip would under-state what the deployment does, so this
 * state is disclosed — and nothing more. Since D3 it is read in the chip's
 * accessible name rather than appended to its visible text; the input, the two
 * states, and the reasoning below are unchanged.
 *
 * `none` is the ONLY state for an absent/failed health check: we then know
 * nothing about the database, and inventing either disclosure would be a guess.
 */
type DbChipState = 'none' | 'diagnostics' | 'failed';

/**
 * WHY "check failed" AND NOT "unavailable" — do not "improve" this back.
 *
 * GET /api/health performs ZERO I/O in its `database` block (it is the
 * Kubernetes readiness-probe target, so a sick database must never be able to
 * fail a probe). `last_recon` is therefore a memo of the last diagnostic RUN in
 * the server process: it may be minutes old, and it is absent entirely until
 * something runs a scan. "Unavailable" would assert PRESENT unreachability that
 * nothing has measured. "check failed" says only what is true — the last
 * recorded check did not complete. Approved by Krish (I5).
 *
 * By the same reasoning `configured: true` means "set up to run the
 * diagnostic", never "a database is currently reachable", so the diagnostics
 * qualifier is deliberately a capability statement and not a liveness one.
 *
 * A status outside {refused, error} — including a future/unknown value — is not
 * treated as a failure: only an outcome we know to be a failure may claim one.
 */
function databaseChipState(database: ApiHealthDatabase | undefined): DbChipState {
  if (!database?.configured) return 'none';
  const status = database.last_recon?.status;
  return status === 'refused' || status === 'error' ? 'failed' : 'diagnostics';
}

/**
 * The chip's VISIBLE text: which workspace scope the reader is looking at, or an
 * anomalous mode when there is one.
 *
 * TWO THINGS CHANGED HERE (D3), and neither is cosmetic.
 *
 * 1. THE SCOPE DECIDES THE LABEL. "Example workspace" was rendered on every
 *    ordinary screen, naming that scope after content this build never puts there —
 *    the examples are created only inside a worked-example session, so only that
 *    scope is named after them. (Deliberately phrased as what the build does, not as
 *    "the examples are not there": see `ORDINARY_ONLY` below, where two successive
 *    versions of that contents claim had to be retired.)
 *
 * 2. THE DATABASE QUALIFIER IS NO LONGER APPENDED. "Example workspace · test DB
 *    diagnostics" put an infrastructure disclosure in the primary header of every
 *    product screen. It is not dropped: it is still derived from the same
 *    `health.database` input and still stated in this chip's ACCESSIBLE NAME (see
 *    `chipAriaDetail`), and four surfaces that already carry technical disclosure
 *    state it at length — the Governance banner, Governance & Safety → Policy, the
 *    Help panel, and Settings → Data & Privacy.
 *
 * An anomalous mode outranks the scope name: a deployment reporting a mode we did
 * not anticipate is more important than which workspace is open, and naming the
 * scope instead would mask it.
 *
 * Never renders a host, database name, user, secret name, connection detail, record
 * count, or any record content — the only inputs are `mode` and whether a session
 * is open.
 */
function chipText(health: ApiHealth | undefined, inExampleSession: boolean): string {
  const anomaly = anomalousMode(health?.mode);
  if (anomaly !== null) return anomaly;
  return inExampleSession ? LABELS.modeWorkedExample : LABELS.modeOrdinaryWorkspace;
}

/**
 * The accessible name always OPENS with the exact visible text (WCAG 2.5.3
 * label-in-name), then states, in plain language, what is true of the scope.
 *
 * THE VISIBLE LABEL HAS BEEN SHORTENED TWICE, and each time the claims it carried
 * had to survive somewhere. It once read "Synthetic"; then "Example workspace ·
 * test DB diagnostics"; it now names the scope alone. What the chip is responsible
 * for asserting has NOT shrunk with it — this accessible name states all of it:
 *
 *   · what the built-in example records are in THIS scope (present and rebuilt from
 *     committed reference files, or structurally absent);
 *   · file upload is refused;
 *   · no official institutional record is shown;
 *   · and, when `health.database` says so, the protected read-only test-database
 *     diagnostic and its last recorded outcome.
 *
 * The first three are the SAME claims the Governance banner, the Governance & Safety
 * policy tab and the Help panel make at length, and those three keep their exact
 * technical wording — a chip is not where a governance guarantee is defined, but it
 * must not be where one silently disappears either.
 *
 * SCOPE-DEPENDENT, and that is a correctness fix rather than a rewording. The single
 * sentence used to open with "the records here are rebuilt from reference files
 * committed to this build". That was true when the five built-in examples were
 * materialised into the ordinary workspace on every read. They are not any more:
 * they exist only inside a worked-example session, so in the ordinary scope the clause
 * described records that are not there.
 *
 * Split, so each scope states what is actually true of it. The two claims that hold
 * unconditionally — upload refused, no official institutional record shown — are
 * shared and must never be dropped from either branch.
 *
 * THE ORDINARY BRANCH HAS NOW BEEN CORRECTED TWICE, and the second correction is the
 * interesting one. The first fix replaced the stale clause with "this workspace holds no
 * records of its own" — an EMPTINESS claim nothing in this app measures. The second fix
 * replaced THAT with "the built-in example records are not in this workspace", which is a
 * narrower emptiness claim and still an assertion about what a directory CONTAINS. Both
 * were false in the same situation. See `ORDINARY_ONLY` below for the third wording, which
 * states what the BUILD ENFORCES instead, and for why that distinction is the whole point.
 */
export const CHIP_CLAIMS_ALWAYS =
  'file upload is refused, and no official institutional record is shown.';

/**
 * Ordinary workspace: a claim about what this BUILD DOES, never about what the
 * directory holds.
 *
 * TWO EARLIER WORDINGS WERE FALSE IN THE SAME SITUATION, and the second one was false
 * while a comment here argued it was proven. Keeping both on the record, because the
 * second mistake was made by a reader of the first correction:
 *
 *  1. "this workspace holds no records of its own" — an emptiness claim derived from
 *     `sessionId === null` alone. The chip reads no count and asks the backend nothing.
 *  2. "the built-in example records are not in this workspace" — a NARROWER emptiness
 *     claim, and narrower did not make it measured. The justification given for it was
 *     that `_materialise_seed` requires a `session_id`, which establishes only that THIS
 *     BUILD cannot put one there. It does not establish that none IS there.
 *
 * WHY THAT GAP IS REAL, MEASURED RATHER THAN REASONED. `list_experiments(None)`
 * (`apps/api/isaac_api/workspace.py:922`) enumerates whatever is on disk under the
 * workspace root, and there is NO startup migration. On a workspace pre-populated as the
 * retired `ensure_seeded()` would have left it, that call returns all five canonical
 * records, each classifying `canonical`, and `remove_experiment`
 * (`apps/api/isaac_api/workspace.py:1220`) REFUSES to delete a canonical id — so wording
 * 2 denied, on every screen, the presence of five rows My Experiments was listing
 * directly beneath it. `DEFAULT_WORKSPACE` is `/tmp/isaac-ui-workspace`
 * (`workspace.py:96`), so any developer who ran an older build then this one reaches that
 * state by default; the `/krish` pod mounts `emptyDir` and does not.
 *
 * WHAT IS ACTUALLY TRUE OF EVERY DEPLOYMENT is the enforcement, so that is what is said.
 * `_materialise_seed`, `reset_to_canonical_seed` and `ensure_tutorial_seeded` each now
 * REFUSE a `None` session id at runtime with `InvalidTutorialSession` — not merely
 * "require" one, which was the over-reading: `scope_root(None)` returns
 * `workspace_root()` silently, and an explicit `session_id=None` was measured writing a
 * canonical record into the ordinary root before the refusal was added
 * (`apps/api/tests/test_tutorial_scope.py::test_the_seeding_functions_refuse_an_unscoped_call`).
 *
 * THERE IS NO OTHER PRODUCER OF A BUILT-IN EXAMPLE, and the reason given here was wrong.
 * `POST /api/uploads` is an unconditional 403 — that part holds. But "record creation mints
 * a fresh ULID rather than a canonical id" is false as stated: `create_experiment` does
 * `rid = id or new_record_id()` (`apps/api/isaac_api/workspace.py:608`), so it mints a fresh
 * ULID only when no explicit id is given, and `create_experiment(..., id=SEED_READY_ID,
 * session_id=None)` writes a canonical record into the ordinary root. The real reason is
 * stronger: this build exposes no record-creation surface at all — there is no
 * `POST /api/experiments`, and `create_experiment` has no caller under
 * `apps/api/isaac_api/`, pinned by
 * `test_tutorial_scope.py::test_create_experiment_has_no_caller_in_the_api_package`.
 *
 * DO NOT REPLACE THIS WITH AN ABSENCE CLAIM WITHOUT MEASURING ONE. The honest way to
 * assert absence would be to read the scope's count, which this chip deliberately does
 * not do.
 */
const ORDINARY_ONLY =
  'nothing in this build adds a built-in example record to this workspace — they are ' +
  `created only inside a guided-walkthrough session; ${CHIP_CLAIMS_ALWAYS}`;

/** Inside a worked-example session: the examples ARE rebuilt from committed
 *  reference files, and they are discarded with the session. */
const EXAMPLE_SESSION_ONLY =
  'the example records here belong to this walkthrough only, are rebuilt from ' +
  'reference files committed to this build, and are discarded when the ' +
  `walkthrough ends; ${CHIP_CLAIMS_ALWAYS}`;

function baseAriaDetail(inExampleSession: boolean): string {
  return inExampleSession ? EXAMPLE_SESSION_ONLY : ORDINARY_ONLY;
}

/**
 * The rest of the accessible name after the visible text.
 *
 * THIS IS WHERE THE DATABASE DISCLOSURE NOW LIVES ALONE (D3). It used to be a
 * visible `· test DB diagnostics` suffix as well; dropping that suffix without
 * keeping this would have deleted the only per-deployment, health-derived statement
 * of the diagnostic's state from the app — the four prose surfaces say a diagnostic
 * "may run", which is a policy statement, not this deployment's status. The two
 * branches below are the same two `health.database` states the suffix was derived
 * from, so nothing about WHAT is disclosed changed; only where it is read.
 */
function chipAriaDetail(state: DbChipState, inExampleSession: boolean): string {
  const base = baseAriaDetail(inExampleSession);
  if (state === 'diagnostics') {
    return (
      `${base} This deployment is also configured to run a protected, ` +
      'read-only diagnostic against an isolated test database; it returns ' +
      'sanitized aggregate results only, and no database records are displayed.'
    );
  }
  if (state === 'failed') {
    return (
      `${base} The most recent protected, read-only test-database ` +
      'diagnostic recorded by this deployment did not complete; it returns ' +
      'sanitized aggregate results only, and no database records are displayed.'
    );
  }
  return base;
}

function chipAriaLabel(health: ApiHealth | undefined, inExampleSession: boolean): string {
  return `${chipText(health, inExampleSession)} — ${chipAriaDetail(
    databaseChipState(health?.database),
    inExampleSession,
  )}`;
}

// Driven by the backend health (via the shared, cached useHealth) rather than a
// hardcoded label — `mode` for an anomaly, `database` for the accessible-name
// disclosure. No extra fetch, no polling, no call to the reconnaissance endpoint
// itself. On backend-down the chip still renders and still carries this
// deployment's two unconditional claims — it never vanishes and never implies
// non-synthetic.
function WorkspaceChip() {
  const health = useHealth();
  // Which scope the chip is describing. Read from the tutorial store rather than
  // from health: `/api/health`'s `mode` describes the DEPLOYMENT and is
  // deliberately unchanged by this (it is still `synthetic-only` in both scopes),
  // while the chip describes the workspace the reader is currently looking at.
  const inExampleSession = useTutorialState().sessionId !== null;
  return (
    <span className="mode-chip" aria-label={chipAriaLabel(health, inExampleSession)}>
      <Shield size={13} strokeWidth={2} aria-hidden="true" />
      {chipText(health, inExampleSession)}
    </span>
  );
}

// The identity mark doubles as the home crumb — a real link back to the queue,
// so no surface is a dead end from the top-left.
function Brand() {
  return (
    <Link to={ROUTES.experiments} className="brand" aria-label={`${LABELS.brand} — ${LABELS.navExperiments}`}>
      <span className="brand-tile" aria-hidden="true">
        <AudioWaveform size={17} strokeWidth={2.2} />
      </span>
      {LABELS.brand}
    </Link>
  );
}

interface TopBarProps {
  variant: 'home' | 'record' | 'breadcrumb';
  breadcrumb?: string;
  title?: string;
  filename?: string;
  stateChip?: ChipKind;
  /** Record id — when present on a record sub-surface, the record title becomes a
   * breadcrumb link back to Review Record (/record/:id). */
  recordId?: string;
  /** Leaf crumb naming the current sub-surface (e.g. "Evidence & File Preview").
   * Rendered as the current, non-link crumb after the linked record title. */
  surface?: string;
}

/** Identity, context/breadcrumb, the persistent Synthetic mode chip, Help, and
 * the ⌘K search command palette. The mode chip is always mounted — it is
 * load-bearing. Search is real (P26): the SearchDialog affordance is mounted on
 * every variant so ⌘K opens the API-backed palette from any surface. */
export function TopBar({ variant, breadcrumb, title, filename, stateChip, recordId, surface }: TopBarProps) {
  return (
    <header className="topbar">
      <Brand />

      {variant === 'home' && (
        <>
          <div className="topbar-spacer" />
          <div className="topbar-right">
            <SearchDialog />
            <WorkspaceChip />
            <HelpPanel />
          </div>
        </>
      )}

      {variant === 'breadcrumb' && (
        <>
          <span className="breadcrumb" aria-current="page">
            <ChevronRight size={14} strokeWidth={2} aria-hidden="true" />
            {breadcrumb}
          </span>
          <div className="topbar-spacer" />
          <div className="topbar-right">
            <SearchDialog />
            <WorkspaceChip />
          </div>
        </>
      )}

      {variant === 'record' && (
        <>
          <div className="record-context">
            <ChevronRight size={14} strokeWidth={2} aria-hidden="true" style={{ color: 'var(--text-disabled)' }} />
            {recordId ? (
              // Sub-surface: the record title is an ancestor crumb linking back to
              // Review Record. The current sub-surface is the leaf below.
              <Link to={ROUTES.record(recordId)} className="record-title record-title-link">
                {title}
              </Link>
            ) : (
              // No sub-surface context: this title IS the current page (leaf).
              <span className="record-title" aria-current="page">
                {title}
              </span>
            )}
            {surface && (
              <>
                <ChevronRight
                  size={14}
                  strokeWidth={2}
                  aria-hidden="true"
                  style={{ color: 'var(--text-disabled)' }}
                />
                <span className="record-surface" aria-current="page">
                  {surface}
                </span>
              </>
            )}
            {stateChip && <StatusChip kind={stateChip} />}
            {filename && <span className="record-file">{filename}</span>}
          </div>
          <div className="topbar-spacer" />
          <div className="topbar-right">
            <SearchDialog />
            <WorkspaceChip />
          </div>
        </>
      )}
    </header>
  );
}
