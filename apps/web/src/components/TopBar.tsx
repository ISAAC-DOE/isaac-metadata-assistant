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
 *    ordinary screen while the ordinary workspace contains no examples at all —
 *    the label asserted contents that are not there. The examples exist only inside
 *    a worked-example session, so only that scope is named after them.
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
 * THE ORDINARY BRANCH'S FIRST FIX OVERSHOT, AND IS ITSELF CORRECTED. It replaced the
 * stale clause with "this workspace holds no records of its own" — an EMPTINESS claim
 * that nothing in this app measures. See `ORDINARY_ONLY` below for why that is false on
 * a deployment whose workspace survived this deploy, and for the narrower claim (the
 * built-in examples are structurally absent) that is true of every deployment.
 */
export const CHIP_CLAIMS_ALWAYS =
  'file upload is refused, and no official institutional record is shown.';

/**
 * Ordinary workspace: the STRUCTURAL claim, not a measured one.
 *
 * IT USED TO CLAIM EMPTINESS, AND NOTHING MEASURED IT. The string was "this workspace
 * holds no records of its own", derived from `sessionId === null` alone — the chip never
 * reads a count and never asks the backend what is in the scope. Meanwhile
 * `list_experiments(None)` enumerates whatever is on disk under the workspace root and
 * there is NO startup migration, so a deployment whose workspace survives this deploy
 * already holding the previously-seeded five WILL list them on My Experiments while this
 * chip denies they exist. `apps/api/isaac_api/workspace.py` names the affected
 * deployments in `_SEED_TITLE_BASE`'s note (a developer's uncleared
 * `/tmp/isaac-ui-workspace`, and the Railway deployment's persistent volume at
 * `/data/isaac-workspace`, which is still live); and those records are then undeletable
 * through the UI, because reset is session-scoped and `remove_experiment` refuses a
 * canonical id.
 *
 * What IS enforced — and enforced structurally rather than checked — is that the
 * BUILT-IN EXAMPLES are not in this scope: `_materialise_seed` REQUIRES a `session_id`
 * and has no normal-scope form, so no code path in this build can put one here. That is
 * the claim the chip makes now. It is narrower than the one it replaces, and unlike it,
 * it is true of every deployment.
 */
const ORDINARY_ONLY =
  'the built-in example records are not in this workspace — they exist only inside a ' +
  `guided-walkthrough session; ${CHIP_CLAIMS_ALWAYS}`;

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
