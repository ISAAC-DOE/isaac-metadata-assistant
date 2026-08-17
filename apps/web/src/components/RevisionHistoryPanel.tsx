/*
 * SUBMISSION HISTORY — the surface, and the four things it must never become.
 *
 * 1. IT NEVER SHOWS AN EMPTY LIST FOR A HISTORY IT COULD NOT READ. The
 *    submission-history tables are created by a migration an OPERATOR applies,
 *    separately from the image, and on this deployment they have not been applied.
 *    So "no revisions" and "could not find out" are both reachable, they look
 *    identical if you are careless, and only one of them is something anybody
 *    observed. The server answers `503` with no `revisions` key at all in the
 *    second case, and this panel renders the server's own sentence rather than an
 *    empty table. `revision-history.test.tsx` pins that in both directions —
 *    including the direction that would make the guard vacuous, a genuinely empty
 *    history rendering as an empty history.
 *
 * 2. IT NEVER INVENTS AN ACTOR. A revision recorded without an attributable person
 *    carries `subject: null`, and this panel says so in words. There is no "System",
 *    no "Unknown user", no em dash standing in for a name, and no fallback to the
 *    deployment. Where a name IS recorded on a test-fixture basis, the panel says
 *    what that basis is worth rather than presenting it as an authenticated person.
 *
 * 3. IT NEVER CALLS AN EXPORT A SUBMISSION. Export is a mechanical transform any
 *    caller can perform; submission is a person saying "this is finished, and I am
 *    the one saying so". The lifecycle chip renders the SERVER's derived state,
 *    which has no export input at all, and no copy in this file uses one word for
 *    the other.
 *
 * 4. IT NEVER LETS AN OPERATOR PROBLEM READ AS AN UNFINISHED RECORD. "This record
 *    is ready" and "this deployment cannot accept a submission" are two facts about
 *    two subjects. They are rendered in two separate blocks with two separate
 *    headings, and the second never modifies the first — which matters, because on
 *    every deployment shipped today the second is TRUE: no edge-trust verifier is
 *    configured, so `POST .../submit` refuses every request.
 *
 * IT IS READ-ONLY AND SAYS SO. Nothing here submits, edits, reverts, restores or
 * exports. There is no "restore this revision" control, and there must not be one
 * until a route exists that could honour it: an affordance that implies a rollback
 * this application cannot perform is the same class of falsehood as the three above.
 */
import './revision-history.css';
import { useCallback, useEffect, useId, useState } from 'react';

import { api, ApiError } from '../lib/api';
import {
  LIFECYCLE_NOTES,
  LIFECYCLE_UNKNOWN_NOTE,
  SIDE_NOW,
  SIDE_REVISION,
  actorBasisNote,
  actorText,
  availabilityHeading,
  diffChangeWord,
  recordedChangeWord,
  sideSentence,
  sideText,
} from '../lib/revisionHistory';
import type {
  ApiHistoryAvailability,
  ApiRevisionDetail,
  ApiRevisionDiff,
  ApiRevisionHistory,
  ApiRevisionSummary,
  ApiLifecycle,
} from '../lib/types';
import { BackendDown, LoadingPanel } from './FetchStates';

/** Same narrowing the other panels use — a non-`ApiError` throw still renders. */
function asApiError(err: unknown): ApiError {
  return err instanceof ApiError
    ? err
    : new ApiError(err instanceof Error ? err.message : String(err));
}

type ListState =
  | { status: 'loading' }
  | { status: 'error'; error: ApiError }
  | { status: 'data'; history: ApiRevisionHistory };

type SelectionState =
  | { status: 'idle' }
  | { status: 'loading'; revisionNo: number }
  | { status: 'error'; revisionNo: number; error: ApiError }
  | {
      status: 'data';
      revisionNo: number;
      detail: ApiRevisionDetail;
      diff: ApiRevisionDiff;
    };

export function RevisionHistoryPanel({ experimentId }: { experimentId: string }) {
  return (
    <section className="revhist-section" aria-labelledby="revision-history-heading">
      <div className="revhist-head">
        <h2 className="revhist-title" id="revision-history-heading">
          Submission History
        </h2>
        <p className="revhist-sub">
          Submitting a record captures an immutable snapshot of it and records who
          submitted it and when. This is a read-only view of those snapshots — nothing
          here changes the record, and no snapshot can be restored from this screen.
        </p>
      </div>
      {/* Keyed on the record so switching records rebuilds this panel's state rather
          than showing one record's history under another's heading. */}
      <RevisionHistoryBrowser key={experimentId} experimentId={experimentId} />
    </section>
  );
}

function RevisionHistoryBrowser({ experimentId }: { experimentId: string }) {
  const [list, setList] = useState<ListState>({ status: 'loading' });
  const [selection, setSelection] = useState<SelectionState>({ status: 'idle' });

  const load = useCallback(() => {
    setList({ status: 'loading' });
    setSelection({ status: 'idle' });
    api
      .getRevisionHistory(experimentId)
      .then((history) => setList({ status: 'data', history }))
      .catch((err: unknown) => setList({ status: 'error', error: asApiError(err) }));
  }, [experimentId]);

  useEffect(load, [load]);

  const select = (revisionNo: number) => {
    setSelection({ status: 'loading', revisionNo });
    Promise.all([
      api.getRevision(experimentId, revisionNo),
      api.getRevisionDiff(experimentId, revisionNo),
    ])
      .then(([detail, diff]) =>
        setSelection({ status: 'data', revisionNo, detail, diff }),
      )
      .catch((err: unknown) =>
        setSelection({ status: 'error', revisionNo, error: asApiError(err) }),
      );
  };

  if (list.status === 'loading') {
    return <LoadingPanel label="Loading submission history from the ISAAC API…" />;
  }
  if (list.status === 'error') {
    return <BackendDown error={list.error} onRetry={load} />;
  }

  const { history } = list;
  return (
    <>
      <LifecycleCard lifecycle={history.lifecycle} />
      <DeploymentBlockNote lifecycle={history.lifecycle} />
      <AvailabilityBlock availability={history.availability} />
      {history.availability.state === 'available' && (
        <RevisionList
          history={history}
          selection={selection}
          onSelect={select}
        />
      )}
    </>
  );
}

/* ── the lifecycle ─────────────────────────────────────────────────────────── */

function LifecycleCard({ lifecycle }: { lifecycle: ApiLifecycle }) {
  const headingId = useId();
  return (
    <section className="revhist-card" aria-labelledby={headingId}>
      <h3 className="revhist-card-title" id={headingId}>
        Where this record stands
      </h3>
      <p className="revhist-lifecycle">
        {/* The chip carries a WORD, never colour alone — the repo's system-wide
            rule. `data-state` drives the surface treatment. */}
        <span className="revhist-chip" data-state={lifecycle.state}>
          {lifecycle.label}
        </span>{' '}
        <span className="revhist-lifecycle-note">{LIFECYCLE_NOTES[lifecycle.state]}</span>
      </p>
      <ul className="revhist-reasons">
        {lifecycle.reasons.map((reason) => (
          <li key={reason.code}>{reason.message}</li>
        ))}
      </ul>
      {!lifecycle.submission.known && (
        <p className="revhist-unknown" role="note">
          {LIFECYCLE_UNKNOWN_NOTE}
        </p>
      )}
      {lifecycle.scientific_readiness.failing_units.length > 0 && (
        <ul className="revhist-failing">
          {lifecycle.scientific_readiness.failing_units.map((unit) => (
            <li key={unit.unit_id}>
              {unit.run_label ?? 'This record'} does not pass the export check.
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * WHY THIS IS ITS OWN BLOCK WITH ITS OWN HEADING, and not a modifier on the chip
 * above. It is a fact about this SERVER, and the chip is a fact about this RECORD.
 * Rendering it as a downgrade — a greyed chip, a "blocked" state, a strikethrough —
 * would tell a scientist their science is unfinished because an operator has not
 * configured something. On every deployment shipped today this block is present,
 * so getting it wrong would mislead every reader rather than an unlucky one.
 */
function DeploymentBlockNote({ lifecycle }: { lifecycle: ApiLifecycle }) {
  const blocked = lifecycle.submission_blocked_by_deployment;
  if (!blocked.blocked) return null;
  return (
    <section className="revhist-deployment" role="note" aria-labelledby="revhist-deployment-heading">
      <h3 className="revhist-card-title" id="revhist-deployment-heading">
        Submitting is unavailable in this deployment
      </h3>
      <p className="revhist-deployment-text">{blocked.message}</p>
      <ul className="revhist-blockers">
        {blocked.blockers.map((code) => (
          <li key={code}>{DEPLOYMENT_BLOCKER_TEXT[code] ?? code}</li>
        ))}
      </ul>
    </section>
  );
}

/**
 * The two blocker codes this API can report, in product words. An unrecognised
 * code renders VERBATIM rather than being swept into a generic sentence — a code
 * this build has not been taught is still a fact, and hiding it behind "something
 * is not configured" would lose the only actionable part.
 */
const DEPLOYMENT_BLOCKER_TEXT: Readonly<Record<string, string>> = {
  no_attributable_actor:
    'No attributable person can be established for a request here, and a submission ' +
    'is a declaration by a person. This is a server configuration matter.',
  no_durable_storage:
    'This deployment has no application database to record a durable submission in.',
};

/* ── availability ──────────────────────────────────────────────────────────── */

function AvailabilityBlock({ availability }: { availability: ApiHistoryAvailability }) {
  if (availability.state === 'available') return null;
  return (
    <section
      className="revhist-availability"
      data-state={availability.state}
      role="note"
      aria-labelledby="revhist-availability-heading"
    >
      <h3 className="revhist-card-title" id="revhist-availability-heading">
        {availabilityHeading(availability)}
      </h3>
      {/* THE SERVER'S OWN SENTENCE, VERBATIM. It is the one place that knows which
          of the causes applies, and paraphrasing it here would create a second
          wording that could drift into asserting something about the record. */}
      <p className="revhist-availability-text">{availability.message}</p>
    </section>
  );
}

/* ── the list ──────────────────────────────────────────────────────────────── */

function RevisionList({
  history,
  selection,
  onSelect,
}: {
  history: ApiRevisionHistory;
  selection: SelectionState;
  onSelect: (revisionNo: number) => void;
}) {
  const revisions = history.revisions ?? [];
  const total = history.total ?? revisions.length;

  if (revisions.length === 0) {
    return (
      <p className="revhist-empty" role="note">
        {/* THE SERVER'S MESSAGE IS DELIBERATELY NOT REPEATED HERE. On this branch it
            says the same thing this sentence says, and stacking the two reads as two
            separate findings. It IS rendered verbatim on every other branch, where it
            is the only thing that knows why nothing could be read. */}
        This record has no submitted revisions. The submission history was read; it
        holds none for this record.
      </p>
    );
  }

  return (
    <>
      <p className="revhist-count">
        {total} submitted revision{total === 1 ? '' : 's'}
        {revisions.length < total ? `, showing the ${revisions.length} most recent` : ''}. Newest
        first.
      </p>
      <ol className="revhist-list">
        {revisions.map((revision) => (
          <li key={revision.revision_id}>
            <RevisionRow
              revision={revision}
              expanded={
                selection.status !== 'idle' && selection.revisionNo === revision.revision_no
              }
              onSelect={() => onSelect(revision.revision_no)}
            />
            {selection.status !== 'idle' && selection.revisionNo === revision.revision_no && (
              <SelectionBody selection={selection} onRetry={() => onSelect(revision.revision_no)} />
            )}
          </li>
        ))}
      </ol>
    </>
  );
}

function RevisionRow({
  revision,
  expanded,
  onSelect,
}: {
  revision: ApiRevisionSummary;
  expanded: boolean;
  onSelect: () => void;
}) {
  const basis = actorBasisNote(revision.actor);
  const submittedUtc = revision.submission?.submitted_utc ?? revision.created_utc;
  return (
    <div className="revhist-row">
      <button
        type="button"
        className="revhist-row-button"
        aria-expanded={expanded}
        onClick={onSelect}
      >
        <span className="revhist-row-no">Revision {revision.revision_no}</span>
        <span className="revhist-row-when">
          {/* The SERVER assigned this time and this renders it verbatim. A missing
              one is stated rather than replaced with "just now" or the local clock. */}
          {submittedUtc ?? 'No submission time was recorded'}
        </span>
      </button>
      <p className="revhist-row-actor">
        {actorText(revision.actor)}
        {basis !== null && <span className="revhist-row-basis"> · {basis}</span>}
      </p>
      {revision.submission === null && (
        <p className="revhist-row-actor" role="note">
          No submission row is recorded against this snapshot.
        </p>
      )}
    </div>
  );
}

function SelectionBody({
  selection,
  onRetry,
}: {
  selection: Exclude<SelectionState, { status: 'idle' }>;
  onRetry: () => void;
}) {
  if (selection.status === 'loading') {
    return <LoadingPanel label={`Loading revision ${selection.revisionNo}…`} />;
  }
  if (selection.status === 'error') {
    return <BackendDown error={selection.error} onRetry={onRetry} />;
  }
  return (
    <div className="revhist-detail">
      <RevisionSnapshot detail={selection.detail} />
      <RevisionDiff diff={selection.diff} />
    </div>
  );
}

/* ── one revision's own content ────────────────────────────────────────────── */

function RevisionSnapshot({ detail }: { detail: ApiRevisionDetail }) {
  if (detail.availability.state !== 'available' || !detail.revision) {
    return (
      <p className="revhist-availability-text" role="note">
        {detail.availability.message}
      </p>
    );
  }
  const revision = detail.revision;
  return (
    <div className="revhist-block">
      <h4 className="revhist-block-title">What this revision recorded</h4>
      {revision.run_revisions.length > 0 ? (
        <ul className="revhist-runs">
          {revision.run_revisions.map((run) => (
            <li key={run.run_revision_id}>
              {/* `label` is `null` when the stored run document carried none. The
                  id is shown, said to be an id, rather than a heading this panel
                  made up — "Run 1" would be an ordinal nobody recorded. */}
              {run.label ?? `A run with no recorded label · ${run.run_id}`}
            </li>
          ))}
        </ul>
      ) : (
        <p className="revhist-block-note">
          This revision recorded no separate runs — the record itself was the one
          thing submitted.
        </p>
      )}
      <h4 className="revhist-block-title">
        What changed from the revision before it
      </h4>
      {revision.changes.length === 0 ? (
        <p className="revhist-block-note">
          No field value differed from the previous revision. A first revision has no
          previous revision to differ from, so it records no changes at all — which is
          not the same as having changed nothing.
        </p>
      ) : (
        <ul className="revhist-changes">
          {revision.changes.map((change) => (
            <li key={`${change.unit_id}:${change.address}`}>
              <span className="revhist-change-kind">{recordedChangeWord(change.change_kind)}</span>{' '}
              <span className="mono">{change.address}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="revhist-scope" role="note">
        Only draft field values are compared. Evidence entries, run overrides, answer
        logs and assets are not, so an empty list means no field value differed —
        never that nothing changed.
      </p>
    </div>
  );
}

/* ── the record now, against that revision ─────────────────────────────────── */

function RevisionDiff({ diff }: { diff: ApiRevisionDiff }) {
  if (diff.availability.state !== 'available') {
    return (
      <p className="revhist-availability-text" role="note">
        {diff.availability.message}
      </p>
    );
  }
  return (
    <div className="revhist-block">
      <h4 className="revhist-block-title">
        The record now, compared with revision {diff.revision_no}
      </h4>
      {diff.comparable === false ? (
        <p className="revhist-block-note" role="note">
          {diff.comparable_note}
        </p>
      ) : (
        <>
          <p className="revhist-block-note">
            {diff.content_signature_matches
              ? 'This record holds exactly the content that was submitted in this revision.'
              : 'This record has changed since this revision was submitted.'}
          </p>
          {(diff.changes ?? []).length === 0 ? (
            <p className="revhist-block-note">
              {diff.content_signature_matches
                ? 'No field value differs.'
                : 'No draft field value differs. Something outside draft field values ' +
                  'differs, and this comparison does not look there.'}
            </p>
          ) : (
            <table className="revhist-table">
              <caption className="sr-only">
                Draft field values that differ between revision {diff.revision_no} and
                the record as it stands
              </caption>
              <thead>
                <tr>
                  <th scope="col">Field</th>
                  <th scope="col">{SIDE_REVISION}</th>
                  <th scope="col">{SIDE_NOW}</th>
                  <th scope="col">Difference</th>
                </tr>
              </thead>
              <tbody>
                {(diff.changes ?? []).map((change) => {
                  const previous = sideText(change.previous_value);
                  const current = sideText(change.current_value);
                  return (
                    <tr key={`${change.unit_id}:${change.address}`}>
                      <th scope="row" className="mono">
                        {change.address}
                        {diff.current_run_labels?.[change.unit_id] ? (
                          <span className="revhist-unit">
                            {' '}
                            · {diff.current_run_labels[change.unit_id]}
                          </span>
                        ) : null}
                      </th>
                      <td>{sideSentence(previous)}</td>
                      <td>{sideSentence(current)}</td>
                      <td>{diffChangeWord(change.change_kind)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          <UnitChanges diff={diff} />
        </>
      )}
    </div>
  );
}

/**
 * Runs added and removed since the revision — the same event the field rows above
 * describe one value at a time, said once at the altitude a reader arrives with.
 */
function UnitChanges({ diff }: { diff: ApiRevisionDiff }) {
  const units = diff.units;
  if (!units || !units.comparable) return null;
  if (units.added.length === 0 && units.removed.length === 0) return null;
  return (
    <ul className="revhist-units">
      {units.added.map((id) => (
        <li key={`added:${id}`}>
          Recorded now and not in this revision: {diff.current_run_labels?.[id] ?? id}
        </li>
      ))}
      {units.removed.map((id) => (
        <li key={`removed:${id}`}>
          In this revision and not recorded now: {diff.revision?.run_labels?.[id] ?? id}
        </li>
      ))}
    </ul>
  );
}
