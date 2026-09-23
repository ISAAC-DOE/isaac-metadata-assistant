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
  SUBMITTED_IMMUTABLE_NOTE,
  SUBMITTED_REVISION_HEADING,
  submittedRevisionText,
  WORKING_CHANGES_HEADING,
  actorBasisNote,
  actorText,
  availabilityHeading,
  diffChangeWord,
  recordedChangeWord,
  renameTrapNote,
  sideSentence,
  sideText,
  workingState,
  workingStateSentence,
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
import { Disclosure } from './Disclosure';
import { HelpTip } from './HelpTip';

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
        {/* The explanation is reference, read once — one `?` away (DEC-35). The
            read-only promise inside it is still in the DOM for a screen reader. */}
        <HelpTip subject="Submission History">
          <span className="revhist-sub">
            Submitting a record captures an immutable snapshot of it and records who
            submitted it and when. This is a read-only view of those snapshots — nothing
            here changes the record, and no snapshot can be restored from this screen.
          </span>
        </HelpTip>
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
      {/*
        ONE STATUS LINE, THEN THE CARDS ONE CLICK AWAY (owner QA V1, 2026-09-22).
        This panel sits below the export verdict and is not what the screen is
        for; it used to render four prose cards in full on every visit. Every
        clause of the line is a field the server sent — the lifecycle label, the
        availability heading `AvailabilityBlock` already uses, the deployment
        block's own heading — so nothing is summarised that the cards do not say.
        What stays VISIBLE is exactly what DEC-35 forbids hiding: whether history
        could be read, and whether this deployment can submit at all.
      */}
      <p className="revhist-status">
        <span className="revhist-chip" data-state={history.lifecycle.state}>
          {history.lifecycle.label}
        </span>
        <span className="revhist-status-text">{historyStatusText(history)}</span>
      </p>
      <Disclosure summary="Submission Details" className="revhist-details">
      <LifecycleCard lifecycle={history.lifecycle} />
      <SubmittedVersusWorking history={history} />
      <DeploymentBlockNote lifecycle={history.lifecycle} />
      <AvailabilityBlock availability={history.availability} />
      {history.availability.state === 'available' && (
        <RevisionList
          history={history}
          selection={selection}
          onSelect={select}
        />
      )}
      </Disclosure>
    </>
  );
}

/**
 * The clauses of the visible status line, each one a server field or a sentence
 * this panel already renders below. A history that could not be read says so
 * (never "no revisions"); a readable one gives its count; a deployment that
 * cannot submit says that too — it is a fact about the server, stated beside the
 * record's own label and never folded into it (see `DeploymentBlockNote`).
 */
function historyStatusText(history: ApiRevisionHistory): string {
  const clauses: string[] = [];
  if (history.availability.state !== 'available') {
    clauses.push(availabilityHeading(history.availability));
  } else {
    const total = history.total ?? (history.revisions ?? []).length;
    clauses.push(
      total === 0
        ? 'No submitted revisions'
        : `${total} submitted revision${total === 1 ? '' : 's'}`,
    );
  }
  if (history.lifecycle.submission_blocked_by_deployment.blocked) {
    clauses.push('Submitting is unavailable in this deployment');
  }
  return clauses.join(' · ');
}

/* ── REV-002 · the submitted snapshot versus the record now ───────────────── */

/**
 * *** THE TWO HALVES `DEC-21` REQUIRES, SIDE BY SIDE AND NAMED. ***
 *
 * The decision, quoted because the owner's correction is the whole point of this
 * block: *"A submitted snapshot is IMMUTABLE. The Experiment workspace may
 * accumulate 'Current Working Changes' after submission and later create the
 * next immutable snapshot."* The planning run had proposed describing this as
 * "keep editing, then submit again" and was told that understates the modelling
 * requirement — the UI must show the two as two things.
 *
 * ── WHAT MAKES THIS HONEST RATHER THAN DECORATIVE ───────────────────────────
 *
 * Every word is derived from the response. The comparison is an exact match of
 * two signatures the SERVER computed (`workingState`), not a diff this client
 * re-derives; the scope of what a submission covers is the server's own
 * `signature_scope` string rather than a list written here; and `unknown` is a
 * first-class state, because on every deployment shipped today the history
 * tables are unapplied and the server says so in terms.
 *
 * ── WHERE IT SITS, AND WHY THAT ORDER ───────────────────────────────────────
 *
 * Directly below the lifecycle chip and ABOVE the availability block. The chip
 * answers "where does this record stand"; this answers "and is what I am looking
 * at the thing that was submitted" — which is the question the chip invites and
 * cannot itself answer. It is deliberately not inside `RevisionList`, because it
 * must render in the `unknown` case too, when there is no list at all.
 *
 * It renders no control. Nothing here submits, and the immutability sentence
 * describes what no route does rather than asserting a database guarantee.
 */
function SubmittedVersusWorking({ history }: { history: ApiRevisionHistory }) {
  const state = workingState(history);
  const headingId = useId();
  const trap = renameTrapNote(state);
  return (
    <section className="revhist-card" aria-labelledby={headingId}>
      <h3 className="revhist-card-title" id={headingId}>
        {SUBMITTED_REVISION_HEADING} and {WORKING_CHANGES_HEADING}
      </h3>
      <dl className="revhist-working">
        <div className="revhist-working-row">
          <dt className="revhist-working-label">{SUBMITTED_REVISION_HEADING}</dt>
          <dd className="revhist-working-value">
            {/*
              C-4 — `submittedRevisionText`, NOT `revisionNo === null ? 'None'`.
              `revisionNo` is null for BOTH `unknown` and `never_submitted`, and on
              every deployment shipped today the state is `unknown`, so this cell
              read "None" about a history that had not been read. The helper carries
              the reasoning; `None` survives for the one state where it is a fact.
            */}
            {submittedRevisionText(state)}
            <span className="revhist-working-note">{SUBMITTED_IMMUTABLE_NOTE}</span>
          </dd>
        </div>
        <div className="revhist-working-row">
          <dt className="revhist-working-label">{WORKING_CHANGES_HEADING}</dt>
          <dd className="revhist-working-value">
            {workingStateSentence(state)}
            {trap !== null && <span className="revhist-working-note">{trap}</span>}
          </dd>
        </div>
        {/*
          THE SCOPE, VERBATIM AND UNDER ITS OWN LABEL. It is an identifier a
          curator maps by, not a word — the same reason `Experiment id` is not
          humanized in the graph detail pane. Rendering it is what lets the
          sentence above say "anything else outside the scope named below"
          without this file asserting what that scope is.
        */}
        <div className="revhist-working-row">
          <dt className="revhist-working-label">What a submission covers</dt>
          <dd className="revhist-working-value">
            <span className="mono revhist-working-scope">{history.signature_scope}</span>
          </dd>
        </div>
      </dl>
    </section>
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
      {/* The label chip is the panel's status line now, visible above this card,
          so it is said once — the WORD still carries the state, never colour alone
          (`data-state` drives its surface). This card keeps what the label means. */}
      <p className="revhist-lifecycle">
        <span className="revhist-lifecycle-note">{LIFECYCLE_NOTES[lifecycle.state]}</span>
      </p>
      <ul className="revhist-reasons">
        {lifecycle.reasons.map((reason) => (
          <li key={reason.code}>{reason.message}</li>
        ))}
      </ul>
      {/*
       * SAID ONCE, NOT TWICE. `lifecycle.reasons` already carries
       * `submission_state_unknown` whenever the history could not be read, so
       * rendering `LIFECYCLE_UNKNOWN_NOTE` unconditionally beneath it stacked two
       * wordings of one fact — and since `tables_absent` is this deployment's
       * CURRENT state, every reader saw the pair. `RevisionList` states the rule
       * this violates a few components down: do not stack two reads of one
       * finding as two separate findings.
       *
       * The note is kept for the case it is actually needed: submission state
       * unknown for a reason the reasons list does NOT already name.
       */}
      {!lifecycle.submission.known &&
        !lifecycle.reasons.some((reason) => reason.code === 'submission_state_unknown') && (
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
                        <UnitTag diff={diff} unitId={change.unit_id} />
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
 * How one unit is named, wherever a unit is named.
 *
 * THREE SOURCES, IN ORDER, AND NEVER A BARE ULID. The diff table used to read
 * `current_run_labels` alone — which is built from CURRENT units only, so a run
 * REMOVED since the revision is absent from it by construction. Its rows got no
 * annotation at all, indistinguishable from a record-level field: in a record
 * where run B was deleted and run C edited, two rows both reading
 * `sample.composition` appeared, one marked `· Run C` and one marked nothing,
 * and a scientist could not tell which measurement each value belonged to.
 *
 * `diff.revision.run_labels` was already fetched and sat unused for exactly this.
 * When neither side has a label, the id is shown as an id — the treatment
 * `RevisionSnapshot` already uses, and this file's own rule.
 *
 * A UNIT IS NOT ALWAYS A RUN. `export_units` returns the RECORD ITSELF as the
 * single unit of a record with no runs, so `unitLabel` says "this record" for
 * that case rather than describing it in run words.
 */
function unitLabel(diff: ApiRevisionDiff, unitId: string): string | null {
  const current = diff.current_run_labels?.[unitId];
  if (current) return current;
  const historical = diff.revision?.run_labels?.[unitId];
  if (historical) return historical;
  if (unitId === diff.experiment_id) return 'this record';
  return null;
}

function UnitTag({ diff, unitId }: { diff: ApiRevisionDiff; unitId: string }) {
  const label = unitLabel(diff, unitId);
  return (
    <span className="revhist-unit">
      {' '}
      · {label ?? `a run with no recorded label · ${unitId}`}
    </span>
  );
}

/**
 * Units added and removed since the revision — the same event the field rows
 * above describe one value at a time, said once at the altitude a reader arrives
 * with.
 *
 * "Units", not "runs", and the distinction is not pedantry: an `ExportUnit` is
 * the RECORD ITSELF for a record with no runs. A record that had zero runs at
 * revision time and has one now produced `removed: [<experiment ULID>]`, which
 * this rendered as "In this revision and not recorded now: 01J…" — asserting
 * that something had been deleted when the record had simply gained its first
 * run.
 */
function UnitChanges({ diff }: { diff: ApiRevisionDiff }) {
  const units = diff.units;
  if (!units || !units.comparable) return null;
  if (units.added.length === 0 && units.removed.length === 0) return null;
  const name = (id: string) => unitLabel(diff, id) ?? `a run with no recorded label · ${id}`;
  return (
    <ul className="revhist-units">
      {units.added.map((id) => (
        <li key={`added:${id}`}>Recorded now and not in this revision: {name(id)}</li>
      ))}
      {units.removed.map((id) => (
        <li key={`removed:${id}`}>In this revision and not recorded now: {name(id)}</li>
      ))}
    </ul>
  );
}
