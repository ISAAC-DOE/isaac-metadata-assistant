import './screens.css';
import './historical-import.css';
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { BackendDown, LoadingPanel } from '../components/FetchStates';
import { Inbox, Plus, TriangleAlert } from '../components/icons';
import { ImportFileStaging } from '../components/ImportFileStaging';
import { ArchiveRuns, CorpusReadOverview } from '../components/ImportCorpusReview';
import { ImportCandidateRow } from '../components/ImportCandidateRow';
import { ImportConflicts } from '../components/ImportConflicts';
import { ImportRules } from '../components/ImportRules';
import { ImportScopeProvider } from '../components/ImportScope';
import { TechniqueChooser, type TechniqueEvidence } from '../components/ImportTechnique';
import { Disclosure } from '../components/Disclosure';
import { HelpTip } from '../components/HelpTip';
import { SemanticStatus } from '../components/SemanticStatus';
import { Widget } from '../components/Widget';
import { Breakable } from '../components/Breakable';
import { LABELS } from '../lib/labels';
import { IMPORT_SESSION_PARAM, IMPORT_STAGE_PARAM, ROUTES } from '../lib/routes';
import { api, ApiError } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import { useProposalDestinations, type ProposalDestinations } from '../lib/importDestinations';
import {
  IMPORT_COPY,
  archiveLabel,
  IMPORT_STAGE_COPY,
  PARSE_STATE_LABELS,
  SOURCE_KIND_LABELS,
} from '../lib/historicalImportContent';
import {
  candidateConcept,
  candidateLabel,
  candidateReview,
  conflictTally,
  conflictViews,
  defaultStage,
  groupUnsent,
  IMPORT_STAGES,
  MATCHED_BY_LABELS,
  plural,
  STAGE_WORKFLOW_STEP,
  stageReached,
  stagesReached,
  summaryItems,
  planFor,
  REVIEW_BUCKET_ORDER,
  REVIEW_BUCKET_STATE,
  reviewCounts,
  type ImportStageId,
  type ReviewBucket,
} from '../lib/importStages';
import type {
  ApiImportAddedToExperiment,
  ApiImportLeftForAPerson,
  ApiImportCandidate,
  ApiImportListResponse,
  ApiImportSession,
  ApiImportSource,
  ApiImportSummary,
  ApiImportWorkflowStep,
} from '../lib/types';

/**
 * HISTORICAL IMPORT — `HIST-004`'s review surface over `HIST-001`'s session and
 * `HIST-003a`'s reconstruction.
 *
 * ── THE BANNED PATTERN, AND WHAT IS DONE INSTEAD ────────────────────────────
 *
 * `HIST-004` bans `Upload Files -> Spinner -> Mysterious JSON`. All three halves
 * are refused here deliberately:
 *
 * * **No upload** — and the shape of that claim CHANGED on 2026-09-15, so the
 *   old form is struck rather than edited away. ~~There is no
 *   `<input type="file">` on this screen and no drop handler. That is not a
 *   promise — `upload-claim-parity.test.tsx` asserts that EXACTLY two non-test
 *   files in `apps/web/src` declare a file input and names both, so adding a
 *   third fails CI.~~
 *
 *   ALL THREE OF THOSE CLAUSES ARE NOW FALSE, and this docstring was
 *   contradicting the very test this screen's own §1 was inverted to assert.
 *   The screen mounts `ImportFileStaging`, which has both a file input and an
 *   `onDrop`; the census is THREE named files. Found by independent review — it
 *   survived because §1's source scan runs over `stripComments(src)`.
 *
 *   WHAT IS STILL TRUE, AND IS THE CLAIM THAT MATTERS: **no file's content ever
 *   reaches ISAAC.** Choosing one stages it in the browser; `Record as source`
 *   sends its name, size, type and — if you asked for one — a checksum computed
 *   in your tab. Proved by instrumenting `fetch` and `XMLHttpRequest` before
 *   the picker was touched: choosing issued zero requests, the checksum zero,
 *   and recording one POST whose body carries no file bytes. `POST /api/uploads`
 *   remains an unconditional 403 and nothing here calls it. A source is still
 *   either a POINTER (recorded, not opened) or one of the committed example
 *   sources.
 * * **No spinner over work that does not happen.** Reading and reconstructing are
 *   real server operations and their in-flight state says which one is running;
 *   nothing else animates, and no control implies a step this build does not
 *   have. The one unbuilt step renders the server's own sentence about why,
 *   with no control at all — not a disabled one, which would imply it is nearly
 *   ready.
 * * **No mysterious JSON.** Every one of the nine things `HIST-004` requires a
 *   scientist to be able to see has a named place on this screen: which sources
 *   were recognised, what was read, what failed, what experiment and run
 *   candidates exist, which sources support each candidate, what was read versus
 *   inferred, where sources disagree, and what is unresolved.
 *
 * ── THE SESSION IS IN THE URL (2026-10-18, QA `C-14`) ───────────────────────
 *
 * ~~"WHY THE SESSION IS IN COMPONENT STATE AND NOT IN THE URL … A `?import=` would be
 * a link to a working area that may not exist when it is followed."~~ — WITHDRAWN.
 * Measured, the cost of not linking was the larger one: a reload put the reader back
 * on the list mid-import, and Back left the feature. The open import and its stage are
 * `?import=<id>&stage=<stage>` (`ROUTES.importSession`): deep-linkable, reload-safe,
 * and Back/Forward walk the stages a reader CHOSE — automatic moves replace the entry
 * rather than adding one. A link to an import that no longer exists says so
 * (`IMPORT_COPY.goneTitle`) instead of failing as a backend error.
 *
 * ── ONE VOCABULARY (2026-10-18, QA `C-20`) ──────────────────────────────────
 *
 * The server's six workflow steps describe what the BACKEND does (Parse, Reconstruct);
 * the stage tabs carry the owner's names for what a scientist is LOOKING AT. The
 * landing's "how it works" strip used the first and the tabs the second, so one
 * sequence had two sets of names. Every surface now uses the stage names; the server's
 * steps still decide how far a session has REACHED (`STAGE_WORKFLOW_STEP`), and the
 * server's own sentence still discloses any step it declares unbuilt.
 */
export function HistoricalImport() {
  const list = useFetch<ApiImportListResponse>(() => api.listImports(), []);
  const [params, setParams] = useSearchParams();
  /* `?import=` with no value is no import (review, 2026-10-18: it crashed the screen). */
  const openId = params.get(IMPORT_SESSION_PARAM) || null;
  const rawStage = params.get(IMPORT_STAGE_PARAM);
  /* An unrecognised stage falls back to the derived one without throwing. */
  const stage = (IMPORT_STAGES as readonly string[]).includes(rawStage ?? '')
    ? (rawStage as ImportStageId)
    : null;
  const reloadList = list.reload;
  /* THE LIST IS RE-READ WHENEVER IT COMES BACK INTO VIEW — by Back as well as by "Back to
     imports" — so a row never shows a session's stage from before the reader opened it. */
  const wasOpen = useRef(openId !== null);
  useEffect(() => {
    if (wasOpen.current && openId === null) reloadList();
    wasOpen.current = openId !== null;
  }, [openId, reloadList]);

  const open = useCallback((id: string) => setParams({ [IMPORT_SESSION_PARAM]: id }), [setParams]);
  const close = useCallback(() => setParams({}), [setParams]);
  /*
   * A STAGE THE READER CHOSE IS A HISTORY ENTRY; ONE AN ACT MOVED THEM TO IS NOT. So
   * Back walks the tabs a reader pressed and then leaves the import — never through the
   * automatic step from Source Bundle to Runs & Candidates that an add triggers.
   */
  const setStage = useCallback(
    (next: ImportStageId, how: { replace?: boolean } = {}) => {
      setParams(
        (prev) => {
          const out = new URLSearchParams(prev);
          out.set(IMPORT_STAGE_PARAM, next);
          return out;
        },
        { replace: how.replace === true },
      );
    },
    [setParams],
  );

  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="imports" />}
      mainPad="pad"
      width="wide"
    >
      {/*
        ONE CONTAINER, ONE RHYTHM. `.hi-screen` sets ONE gap between its blocks and
        `historical-import.css` zeroes the last child's margin inside each, so the
        spacing is a property of the container and survives any edit to a block.
      */}
      <div className={`hi-screen${openId !== null ? ' is-session' : ''}`}>
        <header className="hi-page-head">
          {/* The ONE `<h1>` on this surface — `LABELS.navImports`, the same string the
              nav item and the `document.title` segment read. The eyebrow above it is
              gone (2026-10-18): it restated the heading in capitals. */}
          <h1 className="page-title">{LABELS.navImports}</h1>
          <p className="hi-lead">{IMPORT_COPY.lead}</p>
        </header>

        {openId !== null ? (
          <ImportSessionView
            key={openId}
            importId={openId}
            stage={stage}
            onStage={setStage}
            onClose={close}
          />
        ) : (
          <>
            {/* `LoadingPanel`, NOT a hand-rolled `role="status"` div: the width sweep
                waits on `div.fetch-state[role="status"]` before it measures a surface. */}
            {list.status === 'loading' && (
              <div className="hi-section">
                <LoadingPanel label="Loading imports…" />
              </div>
            )}
            {list.status === 'error' && (
              <div className="hi-section">
                <BackendDown error={list.error} onRetry={list.reload} />
              </div>
            )}
            {list.status === 'data' && <ImportsLanding data={list.data} onOpen={open} onChanged={list.reload} />}
          </>
        )}
      </div>
    </AppShell>
  );
}

/* --------------------------------------------------------------------------
 * The landing — ONE widget: start an import, and the imports already started.
 * -------------------------------------------------------------------------- */

/**
 * THE LANDING, AS ONE WIDGET (2026-10-18, owner direction + design spec).
 *
 * It was three cards: `New Import` (a label, a full-width field and a button), `Imports`
 * (each row "1 source · 1 read · 100 candidates · 0 sent to review"), and a collapsed
 * "How Historical Import works". It is now the shared `Widget`:
 *
 *   * the header is the list's own `<h2>Imports</h2>` — LOAD-BEARING: `e2e/surfaces.ts`
 *     gates this surface on it and `imports-session-a11y.spec.ts` asserts it at level 2;
 *   * the inline name field and `Start an Import` sit directly under the title, the one
 *     primary action on the page;
 *   * each row is its name, when it was started, and a six-step progress meter read
 *     from the server's `furthest_step` — in the stage names the session uses;
 *   * "How it works" is the widget's info panel ("How Historical Import works", the name
 *     the stepper probe in `pill-shape.spec.ts` presses): the six stages, the server's
 *     own durability sentence, and any step the server declares unbuilt — hidden until
 *     asked for, and still in the DOM.
 */
function ImportsLanding({
  data,
  onOpen,
  onChanged,
}: {
  data: ApiImportListResponse;
  onOpen: (id: string) => void;
  onChanged: () => void;
}) {
  const [label, setLabel] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const start = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await api.createImport(label);
      setLabel('');
      onChanged();
      onOpen(created.import.import_id);
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(String(err)));
    } finally {
      setBusy(false);
    }
  }, [label, onChanged, onOpen]);

  return (
    <Widget
      id="hi-imports"
      title="Imports"
      sub={IMPORT_COPY.landingSub}
      infoLabel="How Historical Import works"
      info={
        <div className="hi-how-it-works">
          <p className="hi-body">{IMPORT_COPY.howItWorksLead}</p>
          <WorkflowStrip workflow={data.workflow} furthest={null} />
          {/* THE SERVER'S OWN SENTENCE about what a session is and is not. */}
          <p className="hi-note" role="note">
            {data.durability}
          </p>
        </div>
      }
      lead={
        <form
          className="hi-new"
          onSubmit={(event) => {
            event.preventDefault();
            void start();
          }}
        >
          <label className="hi-new-field">
            <span className="hi-field-label">{IMPORT_COPY.nameLabel}</span>
            <input
              className="hi-input"
              type="text"
              value={label}
              maxLength={200}
              onChange={(event) => setLabel(event.target.value)}
              placeholder={IMPORT_COPY.namePlaceholder}
            />
          </label>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            <Plus size={14} strokeWidth={2.2} aria-hidden="true" />
            {busy ? 'Starting…' : IMPORT_COPY.actionStart}
          </button>
        </form>
      }
    >
      {error !== null && <Refusal error={error} />}
      {data.total === 0 ? (
        <div className="hi-empty">
          <span className="hi-empty-mark" aria-hidden="true">
            <Inbox size={18} strokeWidth={1.75} />
          </span>
          <div className="hi-empty-main">
            <h3 className="hi-empty-title">{IMPORT_COPY.emptyTitle}</h3>
            <p className="hi-empty-body">{IMPORT_COPY.emptyBody}</p>
          </div>
        </div>
      ) : (
        <ul className="hi-list">
          {data.imports.map((row) => (
            <ImportRow key={row.import_id} row={row} workflow={data.workflow} />
          ))}
        </ul>
      )}
    </Widget>
  );
}

/** "18 Oct 2026, 07:52" — when a session started, in the reader's own clock. */
function startedText(utc: string): string {
  const when = new Date(utc);
  if (Number.isNaN(when.getTime())) return '';
  return when.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * ONE IMPORT, AS A ROW: its name (a real link to it), when it started, and how far it
 * has got — six segments, filled from the server's `furthest_step`, labelled with the
 * stage it has reached. The meter is DECORATION OF A STATED FACT: the stage name and an
 * `sr-only` sentence say the same thing in words.
 */
function ImportRow({ row, workflow }: { row: ApiImportSummary; workflow: ApiImportWorkflowStep[] }) {
  const reached = stagesReached(workflow, row.furthest_step);
  const total = IMPORT_STAGES.length;
  const name = row.label || 'Unnamed import';
  const stageName = reached > 0 ? STAGE[IMPORT_STAGES[reached - 1]!].title : IMPORT_COPY.meterNotStarted;
  const started = startedText(row.created_utc);
  return (
    <li className="hi-list-row">
      <div className="hi-list-main">
        <Link className="hi-list-title" to={ROUTES.importSession(row.import_id)}>
          {name}
        </Link>
        {started && <span className="hi-list-meta">Started {started}</span>}
      </div>
      <div className="hi-meter-wrap">
        <span className="hi-meter" aria-hidden="true">
          {IMPORT_STAGES.map((stage, index) => (
            <span key={stage} className={`hi-meter-seg${index < reached ? ' is-reached' : ''}`} />
          ))}
        </span>
        <span className="hi-meter-label">
          <span aria-hidden="true">{reached > 0 ? `${reached} of ${total} · ${stageName}` : stageName}</span>
          <span className="sr-only">
            {reached > 0 ? IMPORT_COPY.meterLabel(stageName, reached, total) : IMPORT_COPY.meterNotStarted}
          </span>
          {row.proposed_count > 0 && <span className="hi-meter-sent"> · {IMPORT_COPY.rowSent(row.proposed_count)}</span>}
        </span>
      </div>
    </li>
  );
}

/* --------------------------------------------------------------------------
 * The workflow strip — the six stages, in the session's own names.
 * -------------------------------------------------------------------------- */

/**
 * The six stages, with the reached one marked and any step the server declares unbuilt
 * stated in the server's own words.
 *
 * IT IS NOT A WORKFLOW SPINE AND MUST NOT BE READ AS ONE: nothing here is locked, no
 * stage blocks another, and `aria-current="step"` marks only where a session has
 * reached. Since 2026-10-18 (QA `C-20`) its labels are the STAGE names the tabs use —
 * Source Bundle … Add to Experiment — not the server's step labels (Parse, Reconstruct),
 * so one sequence has one set of names. A dot per stage on a connecting line is the
 * owner's shape for it (`.hi-step-node`, the record spine's disc vocabulary).
 */
function WorkflowStrip({
  workflow,
  furthest,
}: {
  workflow: ApiImportWorkflowStep[];
  furthest: string | null;
}) {
  const stepOf = (stage: ImportStageId) => workflow.find((step) => step.id === STAGE_WORKFLOW_STEP[stage]);
  const unbuiltSteps = workflow.filter((step) => !step.built && step.disclosure !== null);
  return (
    <div className="hi-steps-wrap">
      <ol className="hi-steps" aria-label="Historical import stages">
        {IMPORT_STAGES.map((stage) => {
          const step = stepOf(stage);
          const unbuilt = step !== undefined && !step.built && step.disclosure !== null;
          const reached = furthest !== null && step?.id === furthest;
          return (
            <li
              key={stage}
              className={`hi-step${reached ? ' reached' : ''}${unbuilt ? ' unbuilt' : ''}`}
              aria-current={reached ? 'step' : undefined}
              aria-describedby={unbuilt && step ? `hi-step-note-${step.id}` : undefined}
            >
              {/* THE UNBUILT STAGE OFFERS NO CONTROL — not a disabled one. The dot is
                  `aria-hidden` reinforcement of what the label already says. */}
              <span className="hi-step-node" aria-hidden="true" />
              <span className="hi-step-label">{STAGE[stage].title}</span>
            </li>
          );
        })}
      </ol>
      {unbuiltSteps.map((step) => {
        const stage = IMPORT_STAGES.find((s) => STAGE_WORKFLOW_STEP[s] === step.id);
        return (
          <p className="hi-steps-disclosure" id={`hi-step-note-${step.id}`} key={step.id}>
            <span className="hi-steps-disclosure-subject">{stage ? STAGE[stage].title : step.label}:</span>{' '}
            {step.disclosure}
          </p>
        );
      })}
    </div>
  );
}

/* --------------------------------------------------------------------------
 * One session — SIX STAGES, ONE IN FOCUS (owner QA H1, 2026-09-22).
 * -------------------------------------------------------------------------- */

/** An act resolves `true` when it succeeded, so a control can say so where it was pressed. */
type ActFn = (name: string, run: () => Promise<unknown>) => Promise<boolean>;
type ActWithNext = (name: string, run: () => Promise<unknown>, next?: ImportStageId) => Promise<boolean>;

const STAGE = IMPORT_STAGE_COPY;

/** Acts whose result is said WHERE THEY WERE PRESSED, so focus stays there (QA `C-26`). */
const IN_PLACE_ACTS = /^(signal:|create:scope)/;

/**
 * AN OPENED IMPORT, AS A FOCUSED STAGE FLOW.
 *
 *  1. THE SUMMARY FIRST — the counts a reader decides from, before any detail.
 *  2. SIX STAGES AS TABS, one in focus, its name in the URL (`?stage=`).
 *  3. EVERY STAGE STAYS MOUNTED, the inactive ones `hidden`, so a half-typed form
 *     survives a trip to another stage and every guard that reads the DOM still reaches
 *     the text.
 *
 * ── FEWER CLICKS, NO DECISION LOST (2026-10-18, QA `C-21`) ──────────────────
 *
 * Reconstruct added no decision — for an archive the candidates already existed at the
 * read — and each "Next:" button only moved a tab. So adding a source this build can
 * read now READS AND RECONSTRUCTS IN THE SAME ACT and moves the reader to Runs &
 * Candidates; the per-stage "Next:" buttons are gone. Measured on the example archive:
 * Start an Import to proposals on a record went from 11 clicks (9 at the fewest) to 5.
 * The "never yank the reader off a stage they chose" guard is unchanged: an act moves
 * the reader only if they are still where it started.
 */
function ImportSessionView({
  importId,
  stage: stageParam,
  onStage,
  onClose,
}: {
  importId: string;
  stage: ImportStageId | null;
  onStage: (stage: ImportStageId, how?: { replace?: boolean }) => void;
  onClose: () => void;
}) {
  const session = useFetch(() => api.getImport(importId), [importId]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const destinations = useProposalDestinations();
  /* The stage on screen, and whether the URL names one, kept for `act`. */
  const activeRef = useRef<ImportStageId | null>(null);
  const stageParamRef = useRef<ImportStageId | null>(stageParam);
  stageParamRef.current = stageParam;
  const [announcement, setAnnouncement] = useState('');
  /* WHERE FOCUS GOES AFTER AN ACT: a selector AND the stage whose panel holds it. */
  const pendingFocus = useRef<{ selector: string; stage: ImportStageId } | null>(null);
  const [focusTick, setFocusTick] = useState(0);
  const [confirmDiscard, setConfirmDiscard] = useState(false);

  const act: ActWithNext = useCallback(
    async (name, run, next) => {
      /*
       * PINNED. Until a reader picks a stage, the one shown is DERIVED from the session
       * — so without this, adding the first source re-derived it mid-task. The pin
       * REPLACES the history entry: it records where the reader already is.
       */
      if (stageParamRef.current === null && activeRef.current !== null) {
        onStage(activeRef.current, { replace: true });
      }
      /* WHERE THE READER WAS WHEN THEY PRESSED IT: an act moves the reader — and takes
         focus — only if they are still on the stage where it started. */
      const startedOn = activeRef.current;
      setBusy(name);
      setError(null);
      try {
        await run();
        session.reloadSilent();
        const stayed = activeRef.current === startedOn;
        if (next && stayed && next !== startedOn) onStage(next, { replace: true });
        setAnnouncement(announcementFor(name, stayed));
        if (stayed && !IN_PLACE_ACTS.test(name) && startedOn !== null) {
          /* THE TARGET STAGE TRAVELS WITH THE REQUEST (independent review, 2026-10-18). The
             stage now lives in the URL, and with `v7_startTransition` the move lands a render
             LATER than this effect's next run — so focusing "the panel that is shown" found
             the Source Bundle heading about to hide, and focus fell to <body>. */
          pendingFocus.current = {
            selector: name.startsWith('add-whole') ? '.hi-addwhole-result .hi-block-title' : '.hi-stage-title',
            stage: next ?? startedOn,
          };
          setFocusTick((n) => n + 1);
        }
        return true;
      } catch (err) {
        setError(err instanceof ApiError ? err : new ApiError(String(err)));
        return false;
      } finally {
        setBusy(null);
      }
    },
    [session, onStage],
  );

  /*
   * HIST-005's REPORT LIVES HERE, above the stages, because it cannot be re-derived from
   * the reloaded session: it is the server's statement about ONE request. What the
   * session DOES remember — every candidate it sent, and where — is shown from the
   * session itself, so a reload keeps it (QA `C-25`).
   */
  const [addedResult, setAddedResult] = useState<ApiImportAddedToExperiment | null>(null);

  /* Focus lands after the re-render that SHOWS the target stage's panel — never in a panel
     that is hidden, or about to be. Until that render, the request waits. */
  useEffect(() => {
    const want = pendingFocus.current;
    if (!want) return;
    const panel = document.getElementById(panelId(importId, want.stage));
    if (!panel || panel.hidden) return;
    const target = panel.querySelector<HTMLElement>(want.selector);
    if (target) {
      target.focus();
      pendingFocus.current = null;
    }
  });
  void focusTick;

  const label = session.status === 'data' ? session.data.import.label : '';
  const createRecord = useCallback(async () => {
    const created = await api.createExperiment({ title: label || 'Imported experiment' });
    await destinations.reload();
    return created.id;
  }, [label, destinations]);

  if (session.status === 'loading') {
    return (
      <div className="hi-section">
        <LoadingPanel label="Loading this import…" />
      </div>
    );
  }
  if (session.status === 'error') {
    /* A LINK TO AN IMPORT THAT IS NOT THERE (QA `C-14`) is a fact about the import, not
       a backend that is down — said in words, with the way back. */
    if (session.error.status === 404) {
      return (
        <div className="hi-section hi-gone" role="status">
          <h2 className="hi-section-title">{IMPORT_COPY.goneTitle}</h2>
          <p className="hi-body">{IMPORT_COPY.goneBody}</p>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Back to imports
          </button>
        </div>
      );
    }
    return (
      <div className="hi-section">
        <BackendDown error={session.error} onRetry={session.reload} />
        <button type="button" className="btn btn-secondary" onClick={onClose}>
          Back to imports
        </button>
      </div>
    );
  }

  const data: ApiImportSession = session.data.import;
  const active: ImportStageId = stageParam ?? defaultStage(data);
  activeRef.current = active;
  const summary = summaryItems(data);
  const scope = {
    targetId: data.rules?.target_experiment_id ?? null,
    createRecord,
    onAct: act as ActFn,
    busy,
  };

  const discard = async () => {
    setBusy('discard');
    setError(null);
    try {
      await api.deleteImport(importId);
      /* NOT through `act`: an act re-reads the session afterwards, and this one has just
         removed it — the stray `GET … 404` the audit measured (QA `C-15`). */
      setConfirmDiscard(false);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(String(err)));
      setBusy(null);
    }
  };

  return (
    <ImportScopeProvider value={scope}>
      <div className="hi-section hi-session-head">
        <div className="hi-section-head">
          <h2 className="hi-section-title">{data.label || 'Unnamed import'}</h2>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Back to imports
          </button>
        </div>
        <dl className="hi-summary" aria-label={STAGE.summaryTitle}>
          {summary.map((item) => (
            <div className="hi-summary-item" key={item.id} data-id={item.id}>
              <dt>{item.label}</dt>
              <dd>{item.value.toLocaleString('en-US')}</dd>
            </div>
          ))}
        </dl>
        <p className="hi-note hi-durability" role="note">
          {data.durability}
        </p>
        {session.refreshFailed && (
          <p className="hi-warn" role="note">
            <TriangleAlert size={14} strokeWidth={2.1} aria-hidden="true" />
            The last change was saved, and this view could not be refreshed. Reopen the
            import to see its current state.
          </p>
        )}
      </div>

      <div className="hi-section hi-stages-card">
        <StageTabs session={data} active={active} onSelect={(next, replace) => onStage(next, { replace })} />
        <p className="sr-only" role="status" aria-live="polite">
          {announcement}
        </p>
        {IMPORT_STAGES.map((id) => (
          <div
            key={id}
            role="tabpanel"
            id={panelId(importId, id)}
            aria-labelledby={tabId(importId, id)}
            className="hi-stage-panel"
            hidden={id !== active}
          >
            {id === active && error !== null && <Refusal error={error} />}
            {id === 'sources' && (
              <SourceBundleStage data={data} busy={busy} onAct={act} importId={importId} />
            )}
            {id === 'read' && <ReadStage data={data} busy={busy} onAct={act} importId={importId} />}
            {id === 'runs' && (
              <RunsStage data={data} busy={busy} onAct={act} importId={importId} destinations={destinations} />
            )}
            {id === 'conflicts' && (
              <ConflictsStage data={data} busy={busy} onAct={act} importId={importId} destinations={destinations} />
            )}
            {id === 'review' && (
              <ReviewStage data={data} busy={busy} onAct={act} importId={importId} destinations={destinations} />
            )}
            {id === 'add' && (
              <AddStage
                data={data}
                busy={busy}
                onAct={act}
                importId={importId}
                destinations={destinations}
                result={addedResult}
                onResult={setAddedResult}
                onGoTo={(next) => onStage(next)}
              />
            )}
          </div>
        ))}
      </div>

      {/*
        THE WORKING AREA, AND ITS ONE DESTRUCTIVE ACT. The consequence stays in the open
        beside the button, and the button now ASKS (QA `C-15`) — a dialog saying what is
        lost and what is kept, before anything is removed.
      */}
      <div className="hi-section hi-discard">
        <p className="hi-note">{IMPORT_COPY.discardNote}</p>
        <button
          type="button"
          className="btn btn-danger-quiet"
          disabled={busy !== null}
          onClick={() => setConfirmDiscard(true)}
        >
          {IMPORT_COPY.actionDiscard}
        </button>
      </div>
      {confirmDiscard && (
        <DiscardDialog
          name={data.label || 'Unnamed import'}
          busy={busy === 'discard'}
          error={busy === 'discard' ? null : error}
          onKeep={() => setConfirmDiscard(false)}
          onConfirm={() => void discard()}
        />
      )}
    </ImportScopeProvider>
  );
}

/**
 * DISCARD, CONFIRMED (2026-10-18, QA `C-15`). The repository's existing dialog shell
 * (`.artifact-modal`, as `DiscardExperimentPanel` uses it): `role="alertdialog"`,
 * `aria-modal`, focus moved IN on open to the SAFE button, Tab contained, Escape = keep,
 * and focus returned to the opener on close.
 */
function DiscardDialog({
  name,
  busy,
  error,
  onKeep,
  onConfirm,
}: {
  name: string;
  busy: boolean;
  error: ApiError | null;
  onKeep: () => void;
  onConfirm: () => void;
}) {
  const keepRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(null);
  useEffect(() => {
    opener.current = document.activeElement;
    keepRef.current?.focus();
    return () => {
      if (opener.current instanceof HTMLElement && opener.current.isConnected) opener.current.focus();
    };
  }, []);
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        if (!busy) onKeep();
        return;
      }
      if (e.key !== 'Tab') return;
      const modal = dialogRef.current;
      if (modal === null) return;
      const items = Array.from(modal.querySelectorAll<HTMLElement>('button:not([disabled])'));
      if (items.length === 0) return;
      const first = items[0]!;
      const last = items[items.length - 1]!;
      const active = document.activeElement;
      if (e.shiftKey) {
        if (active === first || !modal.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else if (active === last || !modal.contains(active)) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown, true);
    return () => document.removeEventListener('keydown', onKeyDown, true);
  }, [busy, onKeep]);

  return (
    <div className="artifact-modal-backdrop" onClick={() => !busy && onKeep()}>
      <div
        ref={dialogRef}
        className="artifact-modal hi-discard-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="hi-discard-title"
        aria-describedby="hi-discard-body"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="artifact-modal-head">
          <span id="hi-discard-title" className="artifact-modal-title">
            {IMPORT_COPY.discardDialogTitle}
          </span>
        </div>
        <div className="hi-discard-dialog-body" id="hi-discard-body">
          <p className="hi-discard-dialog-name">
            <strong>{name}</strong>
          </p>
          <p className="reset-disclosure">{IMPORT_COPY.discardWhatGoes}</p>
          <p className="reset-disclosure">{IMPORT_COPY.discardWhatStays}</p>
          {error !== null && <Refusal error={error} />}
        </div>
        <div className="reset-dialog-actions">
          <button ref={keepRef} type="button" className="btn btn-secondary" onClick={onKeep} disabled={busy}>
            {IMPORT_COPY.discardKeep}
          </button>
          <button type="button" className="btn btn-danger" onClick={onConfirm} disabled={busy}>
            {busy ? IMPORT_COPY.discardPending : IMPORT_COPY.actionDiscard}
          </button>
        </div>
      </div>
    </div>
  );
}

const tabId = (importId: string, stage: ImportStageId) => `hi-tab-${importId}-${stage}`;
const panelId = (importId: string, stage: ImportStageId) => `hi-panel-${importId}-${stage}`;

/**
 * THE SIX STAGES, AS A TABLIST. The meta beside each name is a count read off the
 * session; the stage that owns the server's furthest step carries
 * `aria-current="step"`; the one step the server may declare unbuilt says so.
 */
function StageTabs({
  session,
  active,
  onSelect,
}: {
  session: ApiImportSession;
  active: ImportStageId;
  /** `replace` for an arrow-key move: walking the tabs by keyboard is not a history step. */
  onSelect: (stage: ImportStageId, replace?: boolean) => void;
}) {
  const candidates = session.reconstruction?.candidates ?? [];
  const counts = reviewCounts(session);
  const tally = conflictTally(session);
  const measurements = session.corpus_digest?.measurement_units;
  const furthestStage = IMPORT_STAGES.filter((s) => STAGE_WORKFLOW_STEP[s] === session.furthest_step)[0];
  const unbuilt = (s: ImportStageId) =>
    session.workflow.find((step) => step.id === STAGE_WORKFLOW_STEP[s])?.built === false;

  const meta: Record<ImportStageId, string> = {
    sources: plural(session.sources.length, 'source', 'sources'),
    /* ~~"223 statements"~~ (QA `C-23`): a count of parser statements is the build's unit,
       not the reader's. Sources read is what this stage is about. */
    read: `${session.source_counts.parsed} of ${session.source_counts.total} read`,
    runs:
      measurements !== undefined && measurements !== null
        ? plural(measurements, 'measurement', 'measurements')
        : plural(candidates.length, 'candidate', 'candidates'),
    conflicts: tally.open === 0 ? 'none to decide' : STAGE.conflicts.toDecide(tally.open),
    review: `${counts.needsReview.toLocaleString('en-US')} need review`,
    add: unbuilt('add') ? STAGE.stateLabels.notBuilt : `${counts.ready.toLocaleString('en-US')} ready`,
  };

  const refs = useRef<Map<ImportStageId, HTMLButtonElement>>(new Map());
  const move = (from: ImportStageId, delta: number | 'first' | 'last') => {
    const i = IMPORT_STAGES.indexOf(from);
    const next =
      delta === 'first'
        ? IMPORT_STAGES[0]
        : delta === 'last'
          ? IMPORT_STAGES[IMPORT_STAGES.length - 1]
          : IMPORT_STAGES[(i + delta + IMPORT_STAGES.length) % IMPORT_STAGES.length];
    if (next === undefined) return;
    onSelect(next, true);
    refs.current.get(next)?.focus();
  };

  return (
    <div className="hi-stages" role="tablist" aria-label={STAGE.stagesLabel}>
      {IMPORT_STAGES.map((id, index) => {
        const selected = id === active;
        return (
          <button
            key={id}
            ref={(el) => {
              if (el) refs.current.set(id, el);
              else refs.current.delete(id);
            }}
            type="button"
            role="tab"
            id={tabId(session.import_id, id)}
            aria-controls={panelId(session.import_id, id)}
            aria-selected={selected}
            aria-current={id === furthestStage ? 'step' : undefined}
            tabIndex={selected ? 0 : -1}
            className={`hi-stage-tab${stageReached(session, id) ? ' is-reached' : ''}${
              id === 'conflicts' && tally.open > 0 ? ' has-conflicts' : ''
            }`}
            onClick={() => {
              if (!selected) onSelect(id);
            }}
            onKeyDown={(event) => {
              if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
                event.preventDefault();
                move(id, 1);
              } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
                event.preventDefault();
                move(id, -1);
              } else if (event.key === 'Home') {
                event.preventDefault();
                move(id, 'first');
              } else if (event.key === 'End') {
                event.preventDefault();
                move(id, 'last');
              }
            }}
          >
            <span className="hi-stage-index" aria-hidden="true">
              {index + 1}
            </span>
            <span className="hi-stage-text">
              <span className="hi-stage-name">{STAGE[id].title}</span>
              <span className="hi-stage-meta">{meta[id]}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

/**
 * The act's one polite sentence. `stayed` is false when the reader opened another stage
 * while it ran: the act then moved nothing, so the sentence names no stage it "shows"
 * and points at no report "below" (2026-09-23).
 */
function announcementFor(name: string, stayed = true): string {
  const showing = stayed ? ` Showing ${STAGE.runs.title}.` : '';
  if (name === 'add-archive' || name === 'add-default-archive') return `Archive added and read.${showing}`;
  if (name === 'add-fixture') return `Example source added and read.${showing}`;
  if (name === 'add-reference' || name === 'record-staged-file') return 'Recorded as a source.';
  if (name.startsWith('remove:')) return 'Source removed.';
  if (name === 'parse') return `Sources read.${showing}`;
  if (name === 'reconstruct') {
    return stayed ? `Candidates reconstructed.${showing}` : 'Candidates reconstructed.';
  }
  if (name.startsWith('add-whole') && !name.endsWith(':create')) {
    return stayed ? 'Sent to the record. The report is below.' : 'Sent to the record. The report is in Add to Experiment.';
  }
  if (name.startsWith('resolve') || name.startsWith('rule:') || name.startsWith('adopt:') || name.startsWith('signal:')) {
    return 'Choice recorded. The import was read again under it.';
  }
  if (name.startsWith('propose:')) return 'Sent to the record as a proposal.';
  if (name.includes('create')) return 'Record created.';
  return 'Done.';
}

/** A stage's one heading, one sentence, and the `?` holding the rest. */
function StageHead({ stage, lead }: { stage: ImportStageId; lead?: string }) {
  const copy = STAGE[stage];
  return (
    <div className="hi-stage-head">
      <div className="hi-stage-title-row">
        {/* Focusable by script only, so an act can land the reader here. */}
        <h3 className="hi-stage-title" tabIndex={-1}>
          {copy.title}
        </h3>
        <HelpTip subject={copy.title}>{copy.help}</HelpTip>
      </div>
      <p className="hi-stage-lead">{lead ?? ('lead' in copy ? copy.lead : '')}</p>
    </div>
  );
}

/* --------------------------------------------------------------------------
 * Stage 1 — Source Bundle.
 * -------------------------------------------------------------------------- */

/**
 * Read every source and reconstruct, as ONE step (2026-10-18, QA `C-21`): reconstruction
 * takes no decision of its own, so the reader is never asked to press for it separately.
 */
async function readAndReconstruct(importId: string): Promise<void> {
  await api.parseImport(importId);
  await api.reconstructImport(importId);
}

function SourceBundleStage({
  data,
  busy,
  onAct,
  importId,
}: {
  data: ApiImportSession;
  busy: string | null;
  onAct: ActWithNext;
  importId: string;
}) {
  const [filename, setFilename] = useState('');
  const [reference, setReference] = useState('');
  const [sha256, setSha256] = useState('');
  const [fixture, setFixture] = useState(data.available_fixtures[0] ?? '');
  /* THE SERVER'S DEFAULT (2026-10-12): the archive the hosted image ships, so the picker
     never opens on one a scientist there could not have been offered. */
  const defaultArchive =
    data.default_archive && data.available_archives.includes(data.default_archive)
      ? data.default_archive
      : (data.available_archives[0] ?? '');
  const [archive, setArchive] = useState(defaultArchive);
  const ingestion = data.capabilities?.historical_file_ingestion;
  const hasArchive = data.sources.some((s) => s.kind === 'archive');

  const addArchive = (name: string, actName: string) =>
    onAct(
      actName,
      async () => {
        await api.addImportSource(importId, { kind: 'archive', archiveName: name });
        await readAndReconstruct(importId);
      },
      'runs',
    );

  return (
    <>
      <StageHead stage="sources" />

      {data.sources.length === 0 ? (
        <p className="hi-body hi-empty-inline">{IMPORT_COPY.emptySourcesBody}</p>
      ) : (
        <table className="hi-table">
          <caption className="sr-only">
            The source bundle: what each entry is, and what this build could read from it
          </caption>
          <thead>
            <tr>
              <th scope="col">{STAGE.sourcesColumn.file}</th>
              <th scope="col">{STAGE.sourcesColumn.kind}</th>
              <th scope="col">{STAGE.sourcesColumn.read}</th>
              <th scope="col">
                <span className="sr-only">{STAGE.sourcesColumn.actions}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {data.sources.map((source) => (
              <SourceRow
                key={source.source_id}
                source={source}
                archiveNames={data.archive_display_names}
                busy={busy}
                onRemove={() =>
                  onAct(`remove:${source.source_id}`, () =>
                    api.removeImportSource(importId, source.source_id),
                  )
                }
              />
            ))}
          </tbody>
        </table>
      )}

      {data.unreadable_source_count > 0 && (
        <p className="hi-warn" role="note">
          <TriangleAlert size={14} strokeWidth={2.1} aria-hidden="true" />
          {data.unreadable_source_count} entr
          {data.unreadable_source_count === 1 ? 'y' : 'ies'} in this bundle could not be
          read by this build. They are kept exactly as they are and nothing has been
          discarded.
        </p>
      )}

      {/*
        THE ACTIONS, IN THE ORDER A READER REACHES FOR THEM. The two kinds this build
        actually READS — an archive and an example source — first; adding either now
        reads and reconstructs it in the same act and moves to Runs & Candidates. Then
        files from this computer, with what this deployment can do with them said first;
        then, behind a disclosure, a pointer to a file that must stay where it is.
      */}
      <div className="hi-forms">
        {data.available_archives.length > 0 && (
          <form
            className="hi-form"
            onSubmit={(event) => {
              event.preventDefault();
              void addArchive(archive, 'add-archive');
            }}
          >
            <h4 className="hi-group-title">{IMPORT_COPY.actionAddArchive}</h4>
            <label className="hi-field">
              <span className="hi-field-label">Which archive</span>
              <select className="hi-input" value={archive} onChange={(event) => setArchive(event.target.value)}>
                {/* THE SERVER'S NAME for each committed archive (2026-10-12), never its id. */}
                {data.available_archives.map((name) => (
                  <option key={name} value={name}>
                    {name.startsWith('staged:')
                      ? `${archiveLabel(name, data.archive_display_names)} (staged on the server)`
                      : archiveLabel(name, data.archive_display_names)}
                  </option>
                ))}
              </select>
            </label>
            <div className="hi-form-actions">
              <button type="submit" className="btn btn-secondary" disabled={busy !== null || !archive}>
                {busy === 'add-archive' ? 'Adding and reading…' : IMPORT_COPY.actionAddArchive}
              </button>
              <HelpTip subject="reading an archive">{IMPORT_COPY.addArchiveNote}</HelpTip>
            </div>
          </form>
        )}

        {data.available_fixtures.length > 0 && (
          <form
            className="hi-form"
            onSubmit={(event) => {
              event.preventDefault();
              void onAct(
                'add-fixture',
                async () => {
                  await api.addImportSource(importId, { kind: 'synthetic_fixture', fixtureName: fixture });
                  await readAndReconstruct(importId);
                },
                'runs',
              );
            }}
          >
            <h4 className="hi-group-title">{IMPORT_COPY.actionAddFixture}</h4>
            <label className="hi-field">
              <span className="hi-field-label">Which example source</span>
              <select className="hi-input" value={fixture} onChange={(event) => setFixture(event.target.value)}>
                {data.available_fixtures.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <div className="hi-form-actions">
              <button type="submit" className="btn btn-secondary" disabled={busy !== null || !fixture}>
                {busy === 'add-fixture' ? 'Adding and reading…' : IMPORT_COPY.actionAddFixture}
              </button>
            </div>
          </form>
        )}
      </div>

      {/*
        FILES FROM THIS COMPUTER — WHAT THIS DEPLOYMENT CAN DO WITH THEM, SAID FIRST
        (2026-10-18, QA `C-16`). Choosing a file used to lead nowhere: it was recorded by
        name, the read stage then said nothing here could be read, and nothing said why or
        what to do instead. The state comes from the server's own capability
        (`historical_file_ingestion`): real files are read only from a staging area on the
        server that an operator turns on. When it is off, the next step is offered in place.

        `ImportFileStaging` takes `onRecord` as a prop and so cannot import the API
        client: it cannot send a byte by construction. What reaches ISAAC is a file's
        name, size, type and — only if asked — a checksum computed in this tab.
        `POST /api/uploads` stays an unconditional 403 and nothing here calls it.
      */}
      <section className="hi-files" aria-labelledby={`hi-files-${importId}`}>
        <div className="hi-stage-sub-head">
          <h4 className="hi-group-title" id={`hi-files-${importId}`}>
            {STAGE.filesTitle}
          </h4>
          {!ingestion?.enabled && <HelpTip subject={STAGE.filesTitle}>{STAGE.filesNotReadableHelp}</HelpTip>}
        </div>
        <p className="hi-note">{ingestion?.enabled ? STAGE.filesReadable : STAGE.filesNotReadable}</p>
        {!ingestion?.enabled && !hasArchive && defaultArchive && (
          <p className="hi-files-next">
            {STAGE.filesTryExample}{' '}
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy !== null}
              onClick={() => void addArchive(defaultArchive, 'add-default-archive')}
            >
              {busy === 'add-default-archive' ? 'Adding and reading…' : STAGE.filesTryExampleAction}
            </button>
          </p>
        )}
        <ImportFileStaging
          busy={busy !== null}
          onRecord={async (input) => {
            /* NOT routed through `onAct`: a refusal must land on the ROW that caused
               it, not in one banner for a list. `onAct` is used afterwards only for
               its reload. */
            await api.addImportSource(importId, {
              kind: 'reference',
              filename: input.filename,
              reference: input.reference,
              ...(input.mediaType === '' ? {} : { mediaType: input.mediaType }),
              sizeBytes: input.sizeBytes,
              ...(input.sha256 === null ? {} : { sha256: input.sha256 }),
            });
            await onAct('record-staged-file', async () => {});
          }}
        />
      </section>

      <Disclosure className="hi-disclosure" summary="Add an external reference instead">
        <p className="hi-note">
          For a file that has to stay where it is — on an instrument machine, in group
          storage, or anywhere ISAAC cannot be pointed at. You describe where it is;
          nothing is fetched.
        </p>
        <form
          className="hi-form"
          onSubmit={(event) => {
            event.preventDefault();
            void onAct('add-reference', async () => {
              await api.addImportSource(importId, {
                kind: 'reference',
                filename,
                reference,
                ...(sha256 ? { sha256 } : {}),
              });
              setFilename('');
              setReference('');
              setSha256('');
            });
          }}
        >
          <h4 className="hi-group-title">{IMPORT_COPY.actionAddReference}</h4>
          <label className="hi-field">
            <span className="hi-field-label">File name</span>
            <input
              className="hi-input"
              type="text"
              required
              value={filename}
              maxLength={512}
              onChange={(event) => setFilename(event.target.value)}
              placeholder="scan_0012.mac"
            />
          </label>
          <label className="hi-field">
            <span className="hi-field-label">Where it is</span>
            <input
              className="hi-input"
              type="text"
              required
              value={reference}
              maxLength={2048}
              onChange={(event) => setReference(event.target.value)}
              placeholder="/data/2019/cu-campaign/scan_0012.mac"
            />
          </label>
          <label className="hi-field">
            <span className="hi-field-label">Checksum (optional)</span>
            <input
              className="hi-input"
              type="text"
              value={sha256}
              maxLength={64}
              onChange={(event) => setSha256(event.target.value)}
              placeholder="64 hex characters"
            />
          </label>
          <p className="hi-note">{IMPORT_COPY.digestNote}</p>
          <button
            type="submit"
            className="btn btn-secondary"
            disabled={busy !== null || !filename.trim() || !reference.trim()}
          >
            {IMPORT_COPY.actionAddReference}
          </button>
        </form>
      </Disclosure>

      <Disclosure className="hi-disclosure" summary={STAGE.moreSources}>
        <p className="hi-body">{IMPORT_COPY.sourcesLead}</p>
        <p className="hi-body">{IMPORT_COPY.fixturesLead}</p>
        <p className="hi-note">{IMPORT_COPY.formatsNote}</p>
      </Disclosure>
    </>
  );
}

function SourceRow({
  source,
  busy,
  onRemove,
  archiveNames,
}: {
  source: ApiImportSource;
  busy: string | null;
  onRemove: () => void;
  /** The server's names for committed archives (2026-10-12). */
  archiveNames?: Readonly<Record<string, string>>;
}) {
  const state = PARSE_STATE_LABELS[source.parse_state] ?? source.parse_state;
  const named = archiveLabel(source.filename, archiveNames);
  return (
    <tr>
      <td>
        {/* An ARCHIVE is named in words; its id and where it was read from are one press
            away, because a staged archive's reference IS its id (`staged:<name>`) and
            printing it beside the name put the raw token straight back (review of #279). */}
        {source.kind === 'archive' ? (
          <span className="hi-filename">
            {named}{' '}
            <HelpTip subject={`the archive ${named}`}>
              Its id: <code>{source.filename}</code>
              {source.reference !== source.filename && (
                <>
                  {' '}
                  · read from <code>{source.reference}</code>
                </>
              )}
            </HelpTip>
          </span>
        ) : (
          <>
            <span className="hi-filename">
              <Breakable text={source.filename} />
            </span>
            <span className="hi-reference">
              <Breakable text={source.reference} />
            </span>
          </>
        )}
        {source.sha256 !== null && <span className="hi-sub">checksum recorded · not verified</span>}
      </td>
      <td>{SOURCE_KIND_LABELS[source.kind] ?? source.kind}</td>
      <td>
        <span className={`hi-parse hi-parse-${source.parse_state}`}>{state}</span>
        {/* THE REASON, PER ENTRY — an example source IS read and a reference is
            not, so one sentence covering both would be false for half the bundle. */}
        {source.parse_detail !== null && <span className="hi-sub">{source.parse_detail}</span>}
      </td>
      <td>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy !== null}
          onClick={onRemove}
          aria-label={`${IMPORT_COPY.actionRemoveSource} ${source.kind === 'archive' ? named : source.filename}`}
        >
          {IMPORT_COPY.actionRemoveSource}
        </button>
      </td>
    </tr>
  );
}

/* --------------------------------------------------------------------------
 * Stage 2 — What ISAAC Read.
 * -------------------------------------------------------------------------- */

function ReadStage({
  data,
  busy,
  onAct,
  importId,
}: {
  data: ApiImportSession;
  busy: string | null;
  onAct: ActWithNext;
  importId: string;
}) {
  const counts = data.source_counts;
  /* WHETHER A READ WOULD CHANGE ANYTHING (2026-10-18): adding a readable source now reads
     it, so the control is the primary act only while something is unread (a source added
     before this build, or a pointer recorded beside an archive); otherwise it is a quiet
     "Read Again". */
  const read = counts.parsed > 0 || Boolean(data.corpus_review);
  const unread = counts.unparsed > 0 || (read && data.reconstruction === null);
  return (
    <>
      <StageHead stage="read" />
      <div className="hi-stage-action">
        <button
          type="button"
          className={unread || !read ? 'btn btn-primary' : 'btn btn-secondary'}
          disabled={busy !== null || counts.parsable_by_this_build === 0}
          onClick={() => onAct('parse', () => readAndReconstruct(importId), 'runs')}
        >
          {busy === 'parse' ? 'Reading…' : read && !unread ? STAGE.readAgain : IMPORT_COPY.actionParse}
        </button>
        <p className="hi-counts">
          {counts.total} source{counts.total === 1 ? '' : 's'} · {counts.parsed} read ·{' '}
          {counts.no_content_path} held as a pointer · {counts.failed} could not be read ·{' '}
          {counts.parsable_by_this_build} readable by this build
        </p>
      </div>
      {/* NEVER A BARE DISABLED BUTTON: the sentence beside it says why — and, for a bundle
          of files recorded from this computer, why they cannot be read here and what to do
          instead (QA `C-16`). */}
      {counts.parsable_by_this_build === 0 && (
        <p className="hi-note">{STAGE.nothingToRead}</p>
      )}

      {data.corpus_review && (
        <CorpusReadOverview
          review={data.corpus_review}
          profiles={data.profiles ?? []}
          units={data.archive?.units_page.rows ?? []}
          archiveNames={data.archive_display_names}
        />
      )}

      {data.parsed.length > 0 && (
        <ul className="hi-parsed-list">
          {data.parsed.map((parsed) => (
            <li key={parsed.source_id}>
              <Disclosure
                className="hi-parsed"
                summary={
                  <span className="hi-filename">
                    <Breakable text={parsed.filename} />
                  </span>
                }
                meta={`${plural(parsed.statements.length, 'statement', 'statements')} read · ${plural(
                  parsed.skipped.length,
                  'line',
                  'lines',
                )} passed over`}
              >
                {parsed.statements.length > 0 && (
                  <>
                    <h4 className="hi-block-title">{STAGE.statementsTitle}</h4>
                    <ul className="hi-statements">
                      {parsed.statements.map((statement, index) => (
                        <li key={`${statement.key}-${index}`}>
                          <code className="hi-key">{statement.key}</code>
                          <span className="hi-value">{statement.value}</span>
                          <span className="hi-locator">{statement.locator}</span>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
                {/* WHAT IT PASSED OVER, LISTED — the half that stops this being
                    `Mysterious JSON`. */}
                {parsed.skipped.length > 0 && (
                  <>
                    <h4 className="hi-block-title">{STAGE.skippedTitle}</h4>
                    <ul className="hi-skipped">
                      {parsed.skipped.map((entry, index) => (
                        <li key={index}>
                          <span className="hi-locator">{String(entry.locator ?? '')}</span>
                          <span>{String(entry.message ?? entry.reason ?? '')}</span>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </Disclosure>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/* --------------------------------------------------------------------------
 * Stage 3 — Runs & Candidates.
 * -------------------------------------------------------------------------- */

/** A record's title from the destinations the screen already loaded, if it is among them. */
function recordTitle(destinations: ProposalDestinations, id: string): string | undefined {
  return destinations.rows?.find((r) => r.id === id)?.title;
}

function useFilenameOf(data: ApiImportSession) {
  return useCallback(
    (sourceId: string) => data.sources.find((s) => s.source_id === sourceId)?.filename ?? sourceId,
    [data.sources],
  );
}

/** How many rows a long list shows before `Show N more` (QA `C-27`). */
const PAGE_SIZE = 25;

/**
 * A LONG LIST, PAGED (2026-10-18, QA `C-27`). The Review stage's Unmapped bucket held 93
 * candidate rows, every one mounted with its nested disclosures, and opening it took
 * seconds. A list longer than one page now mounts nothing until its bucket is first
 * opened, then shows {@link PAGE_SIZE} rows and a real `Show N more` button. The bucket's
 * header states the full count first, so a row not yet shown is never an unstated one.
 * A list of one page or fewer is mounted whole, exactly as before.
 */
function PagedList<T>({
  items,
  open,
  render,
  label,
}: {
  items: readonly T[];
  /** Whether the list's container has ever been opened. */
  open: boolean;
  render: (item: T) => ReactNode;
  label: string;
}) {
  const [shown, setShown] = useState(PAGE_SIZE);
  if (items.length > PAGE_SIZE && !open) return null;
  const rest = items.length - shown;
  return (
    <>
      <ul className="hi-cands">{items.slice(0, shown).map(render)}</ul>
      {rest > 0 && (
        <button
          type="button"
          className="btn btn-ghost hi-show-more"
          onClick={() => setShown((n) => n + PAGE_SIZE)}
        >
          Show {Math.min(PAGE_SIZE, rest)} more
          <span className="sr-only">
            {' '}
            of {rest} remaining in {label}
          </span>
        </button>
      )}
    </>
  );
}

function RunsStage({
  data,
  busy,
  onAct,
  importId,
  destinations,
}: {
  data: ApiImportSession;
  busy: string | null;
  onAct: ActWithNext;
  importId: string;
  destinations: ProposalDestinations;
}) {
  const reconstruction = data.reconstruction;
  const candidates = reconstruction?.candidates ?? [];
  const candidatesById = new Map(candidates.map((c) => [c.candidate_id, c]));
  const filenameOf = useFilenameOf(data);
  const archive = Boolean(data.corpus_review && data.archive);
  const structural = candidates.filter((c) => c.kind !== 'field' && !c.unresolved_reason);
  const fields = candidates.filter((c) => c.kind === 'field');
  /* The session's one review categorisation — a sent candidate reads Sent in this stage too. */
  const runsReview = candidateReview(data);
  const read = data.parsed.length > 0 || Boolean(data.corpus_review);

  return (
    <>
      <StageHead stage="runs" lead={archive ? STAGE.runs.leadArchive : STAGE.runs.leadFixture} />
      {/*
        RECONSTRUCT IS NOT A STEP OF ITS OWN ANY MORE (2026-10-18, QA `C-21`): adding a
        readable source reads AND reconstructs it. The control remains only for a session
        that was read without being reconstructed — one started before this build, or a
        read that stopped part-way — and is then the one thing to do here.
      */}
      {reconstruction === null && read && (
        <div className="hi-stage-action">
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy !== null}
            onClick={() => onAct('reconstruct', () => api.reconstructImport(importId), 'runs')}
          >
            {busy === 'reconstruct' ? 'Reconstructing…' : IMPORT_COPY.actionReconstruct}
          </button>
        </div>
      )}
      {/* THE PRECONDITION AND THE NEXT ACT, never the internal state. */}
      {!read && (
        <p className="hi-note">
          Nothing has been read yet, so there is nothing to reconstruct from. Add an archive
          or an example source in Source Bundle — it is read as soon as it is added.
          Reconstruction is deterministic in this build — it reads the statements already
          parsed and calls no model.
        </p>
      )}

      {reconstruction === null && !archive ? (
        <p className="hi-body hi-empty-inline">
          {read ? IMPORT_COPY.emptyCandidatesReadBody : IMPORT_COPY.emptyCandidatesBody}
        </p>
      ) : archive && data.corpus_review && data.archive ? (
        <ArchiveRuns
          review={data.corpus_review}
          units={data.archive.units_page.rows}
          profiles={data.profiles ?? []}
          candidatesById={candidatesById}
          filenameOf={filenameOf}
          importId={importId}
          busy={busy}
          onAct={onAct as ActFn}
          destinations={destinations}
          candidateReview={runsReview}
        />
      ) : (
        <>
          {structural.length > 0 && (
            <section className="hi-group">
              <h4 className="hi-block-title">What this looks like</h4>
              <ul className="hi-cands">
                {structural.map((c) => (
                  <ImportCandidateRow key={c.candidate_id} candidate={c} filenameOf={filenameOf} />
                ))}
              </ul>
            </section>
          )}
          {fields.length > 0 && (
            <section className="hi-group">
              <h4 className="hi-block-title">Candidate values</h4>
              <ul className="hi-cands">
                {fields.map((c) => {
                  const already = runsReview.sentOf(c.candidate_id);
                  return (
                    <ImportCandidateRow
                      key={c.candidate_id}
                      candidate={c}
                      filenameOf={filenameOf}
                      bucket={runsReview.bucketOf(c)}
                      already={already}
                      alreadyTitle={already ? recordTitle(destinations, already.experiment_id) : undefined}
                    />
                  );
                })}
              </ul>
            </section>
          )}
          {data.unmapped_keys.length > 0 && (
            <Disclosure
              className="hi-disclosure"
              summary="Read, but not recognised"
              meta={String(data.unmapped_keys.length)}
            >
              <p className="hi-body">
                These were read out of a source and are not official ISAAC field paths, so
                nothing was proposed for them. They are listed rather than guessed at.
              </p>
              <ul className="hi-unmapped">
                {data.unmapped_keys.map((row, index) => (
                  <li key={`${row.key}-${index}`}>
                    <code className="hi-key">{row.key}</code>
                    <span className="hi-value">{row.value}</span>
                    <span className="hi-locator">{row.locator}</span>
                  </li>
                ))}
              </ul>
            </Disclosure>
          )}
          {/* NO BEAMLINE CONVENTION IS APPLIED TO AN EXAMPLE SOURCE — true here, and
              false for an archive, which is why this is shown only without one. */}
          <Disclosure className="hi-disclosure" summary="How reconstruction works">
            <p className="hi-body">{IMPORT_COPY.reconstructLead}</p>
            <p className="hi-note">{IMPORT_COPY.profileNote}</p>
          </Disclosure>
        </>
      )}
    </>
  );
}

/* --------------------------------------------------------------------------
 * Stage 4 — Conflicts.
 * -------------------------------------------------------------------------- */

function ConflictsStage({
  data,
  busy,
  onAct,
  importId,
  destinations,
}: {
  data: ApiImportSession;
  busy: string | null;
  onAct: ActWithNext;
  importId: string;
  destinations: ProposalDestinations;
}) {
  const views = conflictViews(data);
  const tally = conflictTally(data);
  /* PER-SCAN VARIATION IS NOT A CONFLICT, and a reader who remembers seeing more
     "conflicts" before is told where those values went — neutrally, with a count. */
  const varying = (data.reconstruction?.candidates ?? []).filter((c) => c.agreement === 'varies').length;
  /* THE TWO SETS THIS STAGE HOLDS, NAMED (2026-09-23), and since 2026-10-18 (QA
     `C-12`/`C-22`) what each asks: only the ones TO DECIDE are counted as work; what is
     noted (one side is silent) or preserved (it may never be chosen) is shown and said. */
  const structural = views.filter((v) => v.kind === 'structural').length;
  const field = views.length - structural;
  return (
    <>
      <StageHead stage="conflicts" />
      {views.length > 0 && (
        <p className="hi-counts">
          {STAGE.conflicts.toDecide(tally.open)}
          {tally.noted > 0 ? ` · ${STAGE.conflicts.notedCount(tally.noted)}` : ''}
          {tally.preserved > 0 ? ` · ${STAGE.conflicts.preservedCount(tally.preserved)}` : ''}
          {tally.resolved > 0 ? ` · ${tally.resolved.toLocaleString('en-US')} resolved` : ''}{' '}
          <HelpTip subject="what these conflicts are about" label="What These Conflicts Are About">
            {plural(structural, 'finding', 'findings')} about which measurement a file is ·{' '}
            {plural(field, 'field value', 'field values')} whose sources disagree.
          </HelpTip>
        </p>
      )}
      {varying > 0 && (
        <p className="hi-varies-note">
          <SemanticStatus state="notApplicable" label={STAGE.stateLabels.variesByScan} size="sm" />{' '}
          {plural(varying, 'value', 'values')} {STAGE.variation.conflictsNote}
        </p>
      )}
      <ImportConflicts
        conflicts={views}
        importId={importId}
        busy={busy}
        onAct={onAct as ActFn}
        destinations={destinations}
      />
    </>
  );
}

/* --------------------------------------------------------------------------
 * Stage 5 — Review.
 * -------------------------------------------------------------------------- */

function ReviewStage({
  data,
  busy,
  onAct,
  importId,
  destinations,
}: {
  data: ApiImportSession;
  busy: string | null;
  onAct: ActWithNext;
  importId: string;
  destinations: ProposalDestinations;
}) {
  const fields = (data.reconstruction?.candidates ?? []).filter((c) => c.kind === 'field');
  const filenameOf = useFilenameOf(data);
  /* ONE CATEGORISATION (2026-09-23): a candidate this import already sent is SENT — its own
     group and chip — never "Ready to Send" again, exactly as the header and the Add stage
     count it. `review` is built on the same plan they read. */
  const review = candidateReview(data);
  const counts = reviewCounts(data);
  const buckets = REVIEW_BUCKET_ORDER.filter((b) => counts[b] > 0);
  const titleOf = (id: string) => recordTitle(destinations, id);
  /* WHICH MEASUREMENT, for an archive: the unit that lists the candidate, named by its
     legacy number and label — the handle the Runs stage already uses. */
  const contextOf = new Map<string, string>();
  for (const row of data.archive?.units_page.rows ?? []) {
    /* The run label already opens with "Legacy N" (2026-10-18): "#1 · Legacy 1 · …" said it twice. */
    const handle =
      row.legacy_number !== null && !row.label.startsWith('Legacy ')
        ? `#${row.legacy_number} · ${row.label}`
        : row.label;
    for (const id of row.candidate_ids) contextOf.set(id, handle);
  }

  return (
    <>
      <StageHead stage="review" />
      {data.reconstruction === null ? (
        <p className="hi-body hi-empty-inline">
          {data.source_counts.parsed > 0 || data.corpus_review
            ? IMPORT_COPY.emptyCandidatesReadBody
            : IMPORT_COPY.emptyCandidatesBody}
        </p>
      ) : (
        <>
          <div className="hi-review-counts">
            {buckets.map((b) => (
              <SemanticStatus
                key={b}
                state={REVIEW_BUCKET_STATE[b]}
                label={`${counts[b].toLocaleString('en-US')} ${STAGE.bucketTitles[b]}`}
              />
            ))}
            {/* What sending does, one press away rather than a paragraph above the list. */}
            <HelpTip subject={STAGE.bucketTitles.ready}>{IMPORT_COPY.reviewLead}</HelpTip>
          </div>
          {buckets.map((b) => (
            <ReviewBucketList
              key={b}
              bucket={b}
              count={counts[b]}
              candidates={fields.filter((c) => review.bucketOf(c) === b)}
              render={(candidate) => {
                const already = review.sentOf(candidate.candidate_id);
                return (
                  <ImportCandidateRow
                    key={candidate.candidate_id}
                    candidate={candidate}
                    filenameOf={filenameOf}
                    already={already}
                    alreadyTitle={already ? titleOf(already.experiment_id) : undefined}
                    bucket={b}
                    context={contextOf.get(candidate.candidate_id)}
                  >
                    <CandidateSendForm
                      candidate={candidate}
                      session={data}
                      busy={busy}
                      onAct={onAct}
                      importId={importId}
                      destinations={destinations}
                    />
                  </ImportCandidateRow>
                );
              }}
            />
          ))}
        </>
      )}
      {data.archive && (
        <ImportRules
          rules={data.rules}
          profiles={data.profiles ?? []}
          importId={importId}
          busy={busy}
          onAct={onAct as ActFn}
          destinations={destinations}
        />
      )}
    </>
  );
}

/** One review bucket: its count always visible, its rows paged once it is opened. */
function ReviewBucketList({
  bucket,
  count,
  candidates,
  render,
}: {
  bucket: ReviewBucket;
  count: number;
  candidates: ApiImportCandidate[];
  render: (candidate: ApiImportCandidate) => ReactNode;
}) {
  const [open, setOpen] = useState(bucket === 'ready');
  const [everOpened, setEverOpened] = useState(bucket === 'ready');
  return (
    <Disclosure
      className="hi-bucket"
      headingLevel={4}
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) setEverOpened(true);
      }}
      summary={STAGE.bucketTitles[bucket]}
      meta={count.toLocaleString('en-US')}
    >
      <PagedList items={candidates} open={everOpened} render={render} label={STAGE.bucketTitles[bucket]} />
    </Disclosure>
  );
}

/**
 * THE PER-CANDIDATE SEND. A record chosen from a list (never a typed ULID), the
 * record's own version read immediately before the write, and a run only when one
 * is named — never invented.
 */
function CandidateSendForm({
  candidate,
  session,
  busy,
  onAct,
  importId,
  destinations,
}: {
  candidate: ApiImportCandidate;
  session: ApiImportSession;
  busy: string | null;
  onAct: ActWithNext;
  importId: string;
  destinations: ProposalDestinations;
}) {
  const [experimentId, setExperimentId] = useState('');
  const [runId, setRunId] = useState('');
  const key = `propose:${candidate.candidate_id}`;
  const runs = useRecordRuns(experimentId);
  /* THE RUN MADE FROM THIS VALUE'S OWN MEASUREMENT, PRESELECTED (2026-10-11, QA `C-01`).
     The form used to default to "No run" even when the record held the run created from
     exactly this measurement, and measurement #2's value went onto #1's run without a
     word. The match is the server's: the send plan's key against each run's recorded
     origin. Never "the only run" — a run with no recorded origin is never chosen here. */
  const measurement = session.send_plan?.measurement_of?.[candidate.candidate_id] ?? null;
  const ownRun =
    measurement !== null && runs !== null ? (runs.find((r) => r.origin === measurement)?.id ?? null) : null;
  useEffect(() => {
    // A NEW RECORD (or its runs arriving) resets the choice, to that record's own run
    // for this measurement when it has one — the reset `RunPicker` used to do itself.
    setRunId(ownRun ?? '');
  }, [experimentId, runs, ownRun]);
  return (
    <form
      className="hi-send"
      onSubmit={(event) => {
        event.preventDefault();
        void onAct(key, async () => {
          const detail = await api.getExperiment(experimentId);
          await api.proposeImportCandidate(importId, candidate.candidate_id, {
            experimentId,
            // THE RECORD'S OWN VERSION, read immediately before the write.
            experimentVersion: detail.version,
            ...(runId.trim() ? { runId: runId.trim() } : {}),
          });
          setRunId('');
        });
      }}
    >
      <RecordPicker
        label="Send it to which record?"
        value={experimentId}
        onChange={setExperimentId}
        destinations={destinations}
      />
      <NewDestinationButton
        session={session}
        busy={busy}
        onAct={onAct}
        actKey={`create:${candidate.candidate_id}`}
        reloadDestinations={destinations.reload}
        onCreated={setExperimentId}
      />
      <RunPicker
        runs={runs}
        value={runId}
        onChange={setRunId}
        label="Which run? (required for a value a run owns)"
        measurement={measurement}
        preselected={ownRun}
      />
      <button type="submit" className="btn btn-secondary" disabled={busy !== null || !experimentId.trim()}>
        {busy === key ? 'Sending…' : IMPORT_COPY.actionPropose}
      </button>
    </form>
  );
}

function RecordPicker({
  label,
  value,
  onChange,
  destinations,
}: {
  label: string;
  value: string;
  onChange: (id: string) => void;
  destinations: ProposalDestinations;
}) {
  return (
    <label className="hi-field">
      <span className="hi-field-label">{label}</span>
      {destinations.failed ? (
        /* A FAILED READ IS NOT A BLOCKED WRITE: the id field stays, with the reason. */
        <>
          <input
            className="hi-input"
            type="text"
            required
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder="the record's id"
          />
          <span className="hi-note">The list of records could not be read, so this asks for the id instead.</span>
        </>
      ) : destinations.rows === null ? (
        <span className="hi-note">Reading your records…</span>
      ) : destinations.rows.length === 0 ? (
        <span className="hi-note">
          This workspace holds no records yet. Create one below and it becomes the destination.
        </span>
      ) : (
        <select className="hi-input" required value={value} onChange={(event) => onChange(event.target.value)}>
          <option value="">Choose a record…</option>
          {destinations.rows.map((row) => (
            <option key={row.id} value={row.id}>
              {row.title}
            </option>
          ))}
        </select>
      )}
    </label>
  );
}

/** One run of the chosen record, with the measurement it was recorded as made from. */
interface RunOption {
  id: string;
  label: string;
  /** `historical_origin.acquisition_identity` — the server's matching key — or `null`. */
  origin: string | null;
}

/**
 * THE CHOSEN RECORD'S RUNS, read once per record — lifted out of `RunPicker`
 * (2026-10-11) because both send forms now need the runs' recorded origins, not only
 * the picker. `null` while there is no record or the read is in flight; `[]` when the
 * record has none or the read failed, which leaves the picker absent exactly as before.
 */
function useRecordRuns(experimentId: string): RunOption[] | null {
  const [runs, setRuns] = useState<RunOption[] | null>(null);
  useEffect(() => {
    let alive = true;
    setRuns(null);
    if (!experimentId.trim()) return;
    api
      .listRuns(experimentId)
      .then((res) => {
        if (!alive) return;
        setRuns(
          (res.runs ?? []).map((r) => ({
            id: r.id,
            label: r.label || r.id,
            origin: r.historical_origin?.acquisition_identity ?? null,
          })),
        );
      })
      .catch(() => {
        if (alive) setRuns([]);
      });
    return () => {
      alive = false;
    };
  }, [experimentId]);
  return runs;
}

/**
 * A run CHOSEN FROM THE RECORD'S OWN RUNS, never a typed id — and only when the
 * record has any. Blank means "no run", which is correct for every value the record
 * itself owns.
 *
 * `measurement` (2026-10-11, QA `C-01`) is the send plan's key for the value's own
 * measurement. A run RECORDED as made from a different one cannot take it — the server
 * refuses with `run_is_another_measurement` — so that option is shown, labelled and
 * disabled rather than offered. The match is string equality on the server's own key;
 * no matching rule is re-implemented here.
 */
function RunPicker({
  runs,
  value,
  onChange,
  label,
  measurement = null,
  preselected = null,
}: {
  runs: RunOption[] | null;
  value: string;
  onChange: (id: string) => void;
  label: string;
  measurement?: string | null;
  /** The run the form chose for the reader because it was made from `measurement`. */
  preselected?: string | null;
}) {
  if (runs === null || runs.length === 0) return null;
  return (
    <label className="hi-field">
      <span className="hi-field-label">{label}</span>
      <select className="hi-input" value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">No run — a value the record owns</option>
        {runs.map((run) => {
          const another = measurement !== null && run.origin !== null && run.origin !== measurement;
          return (
            <option key={run.id} value={run.id} disabled={another}>
              {another ? `${run.label}${STAGE.otherMeasurementRun}` : run.label}
            </option>
          );
        })}
      </select>
      {preselected !== null && value === preselected && (
        <span className="hi-note">{STAGE.ownRunPreselected}</span>
      )}
    </label>
  );
}

/**
 * The one control on this screen that CREATES the destination. ONE component, used
 * from every send form, so there is one creation affordance expressed once (the P1
 * exemption for its label is one string, one occurrence). It creates a TITLE and
 * nothing else — no field is carried over, because nothing has been reviewed yet.
 */
function NewDestinationButton({
  session,
  busy,
  onAct,
  actKey,
  reloadDestinations,
  onCreated,
}: {
  session: ApiImportSession;
  busy: string | null;
  onAct: ActWithNext;
  actKey: string;
  /** THE CALLER'S `reload`, so the new record appears in the SAME picker that submits. */
  reloadDestinations: () => Promise<void>;
  onCreated: (experimentId: string) => void;
}) {
  return (
    <button
      type="button"
      className="btn btn-ghost hi-new-destination"
      disabled={busy !== null}
      onClick={() => {
        void onAct(actKey, async () => {
          const created = await api.createExperiment({ title: session.label || 'Imported experiment' });
          await reloadDestinations();
          onCreated(created.id);
        });
      }}
    >
      {busy === actKey ? 'Creating…' : IMPORT_COPY.actionNewRecord}
    </button>
  );
}

/* --------------------------------------------------------------------------
 * Stage 6 — Add to Experiment (`HIST-005`).
 * -------------------------------------------------------------------------- */

/**
 * What the import read about HOW the measurements were made — the acquisition-method
 * readings, verbatim, with how many places state each. Shown beside the technique picker
 * as evidence; never mapped to a technique (a macro's name is not one).
 */
function techniqueEvidence(data: ApiImportSession): TechniqueEvidence[] {
  const places = new Map<string, number>();
  for (const candidate of data.reconstruction?.candidates ?? []) {
    if (candidateConcept(candidate) !== 'acquisition_method') continue;
    for (const statement of candidate.supporting_statements) {
      const value = String(statement.value ?? '').trim();
      if (value) places.set(value, (places.get(value) ?? 0) + 1);
    }
  }
  return [...places.entries()].map(([value, n]) => ({ value, places: n }));
}

/**
 * ADD EVERY READY CANDIDATE TO ONE RECORD, IN ONE REQUEST — and say beforehand what
 * will and will not go, in words.
 *
 * ONE request because a client loop would be N writes that could each fail alone,
 * leaving a record holding part of an import with nothing able to say which part.
 * The report renders what the SERVER said, never what was asked for.
 *
 * ── WHAT CHANGED 2026-10-18 ─────────────────────────────────────────────────
 *
 *   * `C-17`: when no reviewer can be identified, that is said BEFORE sending — from the
 *     session's own `proposal_acceptance` capability — not only in the report after.
 *   * `C-25`: the form stays usable after a send, so the same import can go to another
 *     record; what is ready is counted against the CHOSEN record; what this import has
 *     sent is listed from the session itself, so a reload keeps it; and the report's
 *     numbers agree with each other ("4 proposals on this record: 2 new · 2 already
 *     there", not "2 sent · 2 already there" beside "Sent candidates 4").
 *   * `C-10`: the record's technique — the one choice the copy promised and no control
 *     offered — is chosen here, from the schema's own list, nothing preselected.
 */
function AddStage({
  data,
  busy,
  onAct,
  importId,
  destinations,
  result,
  onResult,
  onGoTo,
}: {
  data: ApiImportSession;
  busy: string | null;
  onAct: ActWithNext;
  importId: string;
  destinations: ProposalDestinations;
  result: ApiImportAddedToExperiment | null;
  onResult: (result: ApiImportAddedToExperiment) => void;
  onGoTo: (stage: ImportStageId) => void;
}) {
  const [experimentId, setExperimentId] = useState('');
  const [runId, setRunId] = useState('');
  const archive = Boolean(data.archive);
  const [createRunsChoice, setCreateRuns] = useState(archive);
  /* EVERY STAGE IS MOUNTED WHEN THE SESSION OPENS (hidden until chosen), so `useState`'s
     initial value was read while the bundle held no archive yet — measured in a real
     browser 2026-10-12. The default follows the archive's ARRIVAL; it never re-checks a
     box the scientist cleared, because `archive` does not change again. */
  useEffect(() => {
    if (archive) setCreateRuns(true);
  }, [archive]);
  const runUnits = data.archive?.run_candidate_unit_count ?? 0;
  /* CREATING THE RUNS IS AN ACT BY ITSELF (2026-10-12): with nothing sendable, an
     archive's measurements can still be put on a record as runs. */
  const withRuns = planFor(data, true);
  /* …and only once the import has been RECONSTRUCTED: the notes the batch writes are
     built from the candidates. */
  const reconstructed = (data.reconstruction?.candidates.length ?? 0) > 0;
  const runsOnly =
    archive &&
    reconstructed &&
    runUnits > 0 &&
    withRuns.willSend.length === 0 &&
    withRuns.alreadySent.length === 0;
  const createRuns = runsOnly || createRunsChoice;
  /* ONE PLAN, the batch's own partition (`send_plan`) — so what this stage says will
     happen is what the report then says did (2026-09-23). */
  const plan = planFor(data, archive && createRuns);
  const blocked = groupUnsent(plan.unsent);
  const blockedTotal = plan.unsent.length;
  /* COUNTED AGAINST THE CHOSEN RECORD (QA `C-25`). A candidate this import sent to one
     record is still sendable to ANOTHER — the server's exactly-once guard is per record —
     so with a record chosen, "already" means already on THAT record. */
  const sendableAll = [...plan.willSend, ...plan.alreadySent];
  const alreadyHere = experimentId
    ? sendableAll.filter((id) => data.proposed[id]?.experiment_id === experimentId)
    : [];
  const readyHere = experimentId ? sendableAll.length - alreadyHere.length : plan.willSend.length;
  const sentTo = new Map<string, string[]>();
  for (const [id, row] of Object.entries(data.proposed ?? {})) {
    const list = sentTo.get(row.experiment_id);
    if (list) list.push(id);
    else sentTo.set(row.experiment_id, [id]);
  }
  const titleOf = (id: string) => recordTitle(destinations, id) ?? 'a record';
  const key = `add-whole:${importId}`;
  const step = data.workflow.find((s) => s.id === 'add_to_experiments');
  const acceptance = data.capabilities?.proposal_acceptance;
  const techniqueTarget = experimentId || result?.experiment_id || [...sentTo.keys()][0] || '';
  const shortList =
    data.corpus_review?.mapping.concepts.find((c) => c.concept === 'acquisition_method')?.allowed_values ?? [];

  /* THE RULE, SAID BEFORE SUBMIT (2026-10-11, QA `C-01`). A run holds one measurement's
     values; these counts only FORESHADOW the server's refusal; the server still decides. */
  const runs = useRecordRuns(experimentId);
  useEffect(() => {
    setRunId(''); // a new record: the old record's run means nothing here
  }, [experimentId]);
  const measurementOf = data.send_plan?.measurement_of ?? {};
  const ownRuns = new Set((runs ?? []).map((r) => r.origin).filter((o): o is string => o !== null));
  const homeless = new Set(
    plan.willSend.map((id) => measurementOf[id]).filter((m): m is string => Boolean(m) && !ownRuns.has(m)),
  );
  const namedOrigin = runs?.find((r) => r.id === runId)?.origin ?? null;
  const routingWarning =
    createRuns || runs === null || runs.length === 0
      ? null
      : homeless.size > 1
        ? STAGE.severalMeasurements(homeless.size)
        : homeless.size === 1 && namedOrigin !== null
          ? STAGE.namedRunIsAnotherMeasurement
          : null;

  const showForm =
    !(sendableAll.length === 0 && !runsOnly) && !(sendableAll.length === 1 && !(archive && runUnits > 0));

  if (step && !step.built && step.disclosure !== null) {
    return (
      <>
        <StageHead stage="add" />
        {/* THE UNBUILT STEP OFFERS NO CONTROL — not a disabled one. */}
        <p className="hi-steps-disclosure" id={`hi-step-note-${step.id}`}>
          <span className="hi-steps-disclosure-subject">{STAGE.add.title}:</span> {step.disclosure}
        </p>
      </>
    );
  }

  return (
    <>
      <StageHead stage="add" />

      <div className="hi-add-summary">
        <h4 className="hi-block-title">{STAGE.addSummaryTitle}</h4>
        <p className="hi-add-headline">
          <strong>{STAGE.readyHere(readyHere)}</strong>
          {experimentId && alreadyHere.length > 0 ? ` · ${STAGE.alreadyHere(alreadyHere.length)}` : ''}
          {!experimentId && plan.alreadySent.length > 0
            ? ` · ${plan.alreadySent.length.toLocaleString('en-US')} already sent`
            : ''}
          {blockedTotal > 0 ? ` · ${blockedTotal.toLocaleString('en-US')} will not be` : ''}
        </p>
        {/* SAID BEFORE SENDING (QA `C-17`), from the server's own capability — the same
            decision the accept route makes, never a copy of it. */}
        {acceptance?.available === false && (
          <p className="hi-note" role="note">
            {STAGE.acceptanceBefore}
          </p>
        )}
        {blocked.length > 0 && (
          <Disclosure className="hi-disclosure" summary={STAGE.willNotBeSent} meta={String(blockedTotal)}>
            <ul className="hi-add-blocked">
              {blocked.map((group) => (
                <li key={group.category}>
                  <span className="hi-add-blocked-count">{group.rows.length.toLocaleString('en-US')}</span>{' '}
                  {group.label}
                </li>
              ))}
            </ul>
          </Disclosure>
        )}
      </div>

      <LeftForAPerson left={data.left_for_a_person ?? null} />

      {/* WHAT THIS IMPORT HAS SENT, FROM THE SESSION ITSELF (QA `C-25`), so a reload keeps
          it: the session remembers each send even though the last report is not kept. */}
      {/* Not shown while the report below says the same about the same one record. */}
      {sentTo.size > 0 && !(result !== null && sentTo.size === 1 && sentTo.has(result.experiment_id)) && (
        <section className="hi-sent-so-far" aria-label={STAGE.sentSoFarTitle}>
          <h4 className="hi-block-title">{STAGE.sentSoFarTitle}</h4>
          <ul className="hi-add-blocked">
            {[...sentTo.entries()].map(([id, ids]) => (
              <li key={id}>
                {STAGE.sentSoFarRow(ids.length)}{' '}
                <Link to={ROUTES.recordView(id, 'proposals')}>{titleOf(id)}</Link>
              </li>
            ))}
          </ul>
          {sendableAll.length > 0 && <p className="hi-sub">{STAGE.sendAnother}</p>}
        </section>
      )}

      {sendableAll.length === 0 && !runsOnly ? (
        <p className="hi-body hi-empty-inline">
          Nothing in this import can be sent yet. Resolve its field conflicts, or read and
          reconstruct its sources first.
        </p>
      ) : sendableAll.length === 1 && !(archive && runUnits > 0) ? (
        /* ONE CANDIDATE: this panel and that candidate's own form would do the
           same thing by two routes, so the one route is offered. */
        <p className="hi-body">
          One candidate can be sent. Send it from its row in Review.{' '}
          <button type="button" className="btn btn-ghost" onClick={() => onGoTo('review')}>
            {STAGE.review.title}
          </button>
        </p>
      ) : (
        <form
          className="hi-send hi-addwhole"
          onSubmit={(event) => {
            event.preventDefault();
            void onAct(key, async () => {
              const detail = await api.getExperiment(experimentId);
              const added = await api.addImportToExperiment(importId, {
                experimentId,
                // THE RECORD'S OWN VERSION, read immediately before the write.
                experimentVersion: detail.version,
                ...(!createRuns && runId.trim() ? { runId: runId.trim() } : {}),
                ...(createRuns ? { createRuns: true } : {}),
              });
              onResult(added);
              setRunId('');
            });
          }}
        >
          <h4 className="hi-block-title">{IMPORT_COPY.actionAddWhole}</h4>
          {runsOnly && <p className="hi-note">{STAGE.runsOnlyLead(runUnits)}</p>}
          <RecordPicker
            label="Which record?"
            value={experimentId}
            onChange={setExperimentId}
            destinations={destinations}
          />
          <NewDestinationButton
            session={data}
            busy={busy}
            onAct={onAct}
            actKey={`${key}:create`}
            reloadDestinations={destinations.reload}
            onCreated={setExperimentId}
          />
          {archive && (
            <label className="hi-choice">
              <input
                type="checkbox"
                checked={createRuns}
                /* With nothing to send, making the runs IS the act — the lead above
                   says so — so the choice is shown and held on. */
                disabled={runsOnly}
                onChange={(event) => setCreateRuns(event.target.checked)}
              />
              <span>{STAGE.createRuns}</span>
            </label>
          )}
          {!createRuns && (
            <RunPicker
              runs={runs}
              value={runId}
              onChange={setRunId}
              label="Which run? (for the values a run owns)"
            />
          )}
          <p className="hi-note">{IMPORT_COPY.addWholeRunNote}</p>
          {routingWarning !== null && (
            <p className="hi-note" role="note">
              {routingWarning}
            </p>
          )}
          {/* THE TECHNIQUE, ABOVE THE PRIMARY SEND (review, 2026-10-18), and on the record
              chosen in THIS form — it is that record's answer, saved by its own button. */}
          {archive && (
            <TechniqueChooser
              experimentId={experimentId}
              recordTitle={experimentId ? titleOf(experimentId) : undefined}
              evidence={techniqueEvidence(data)}
              shortList={shortList}
            />
          )}
          <button
            type="submit"
            className="btn btn-primary"
            disabled={busy !== null || !experimentId.trim()}
          >
            {busy === key ? 'Sending…' : IMPORT_COPY.actionAddWhole}
          </button>
        </form>
      )}

      {/* With no send form on the stage, the technique still has a home — on the record this
          import last sent to, when there is one. */}
      {archive && !showForm && (
        <TechniqueChooser
          experimentId={techniqueTarget}
          recordTitle={techniqueTarget ? titleOf(techniqueTarget) : undefined}
          evidence={techniqueEvidence(data)}
          shortList={shortList}
        />
      )}

      {result !== null && (
        <AddResult result={result} recordName={titleOf(result.experiment_id)} />
      )}

    </>
  );
}

/**
 * WHAT THIS IMPORT DOES NOT FILL ON THE RUNS (2026-10-12) — the environment, the reaction
 * and the cell type, each either proposed from what a file states or left blank for a
 * person, with the server's own rule sentence and where to set them. Every number is the
 * server's; nothing here decides what was stated.
 */
export function LeftForAPerson({
  left,
  headingLevel = 'h4',
}: {
  left: ApiImportLeftForAPerson | null;
  headingLevel?: 'h4' | 'h5';
}) {
  if (left === null || left.runs === 0) return null;
  const Heading = headingLevel;
  const rows = Object.entries(left.by_measurement ?? {}).filter(([, fields]) => fields.length > 0);
  return (
    <section className="hi-left-for-person" aria-label={STAGE.leftTitle}>
      <Heading className="hi-block-title">{STAGE.leftTitle}</Heading>
      <p className="hi-note">{left.rule}</p>
      <ul className="hi-add-blocked">
        {left.fields.map((field) => (
          <li key={field.path}>
            <strong>{field.label}</strong>{' '}
            {field.left > 0 ? STAGE.leftCount(field.left, left.runs) : STAGE.leftNone}
            {field.offered > 0 ? ` · ${STAGE.leftOffered(field.offered)}` : ''}
          </li>
        ))}
      </ul>
      <p className="hi-note">{left.where}</p>
      {rows.length > 0 && (
        <Disclosure className="hi-disclosure" summary={STAGE.leftPerMeasurement} meta={String(rows.length)}>
          <ul className="hi-addwhole-sent">
            {rows.map(([stem, fields]) => (
              <li key={stem}>
                <span className="hi-candidate-target">{stem}</span>
                <span className="hi-sub">
                  {fields.map((f) => `${f.label} — ${left.reasons[f.reason] ?? f.reason}`).join(' · ')}
                </span>
              </li>
            ))}
          </ul>
        </Disclosure>
      )}
    </section>
  );
}

/**
 * THE BATCH'S REPORT — every number the server's own, and worded so the numbers agree
 * (2026-10-18, QA `C-25`). The report read "2 sent · 2 already there" above a list titled
 * "Sent candidates 4": the list held both kinds and its title named one. Now the list is
 * "Proposals on this record", its count is the sum, and the line above says how it splits.
 * "Left for You to Choose" is not repeated here: the stage already shows it above.
 */
function AddResult({
  result,
  recordName,
}: {
  result: ApiImportAddedToExperiment;
  recordName: string;
}) {
  const groups = groupUnsent(result.not_sent);
  const onRecord = result.sent.length;
  return (
    <div className="hi-addwhole-result">
      <h4 className="hi-block-title" tabIndex={-1}>
        {IMPORT_COPY.addWholeResultTitle}
      </h4>
      {/* EVERY NUMBER FROM THE SERVER, AND ALL OF THEM: `sent` + `already_sent` is the
          list below, `not_sent` the groups after it, `candidates` the import's total. */}
      <p className="hi-counts">
        <strong>{STAGE.sentNow(onRecord)}</strong> to {recordName}:{' '}
        {STAGE.newAndAlready(result.counts.sent, result.counts.already_sent)} ·{' '}
        {result.counts.not_sent} could not be sent · {result.counts.candidates} candidate
        {result.counts.candidates === 1 ? '' : 's'} in this import
        {typeof result.counts.runs_created === 'number' ? ` · ${result.counts.runs_created} runs created` : ''}
      </p>
      {result.counts.sent === 0 && result.counts.already_sent > 0 && (
        <p className="hi-sent" role="note">
          {IMPORT_COPY.addWholeNothingNew}
        </p>
      )}
      {/* RUNS WERE MADE AND NOTHING WAS SENT (2026-10-12) — said, so "0 sent" does not read
          as a batch that did nothing. */}
      {result.counts.sent === 0 && result.counts.already_sent === 0 && (result.counts.runs_created ?? 0) > 0 && (
        <p className="hi-sent" role="note">
          {STAGE.runsOnlyResult}
        </p>
      )}
      {result.reread_for_target && <p className="hi-note">{STAGE.reread}</p>}
      {result.data_quality_notes && result.data_quality_notes.available > 0 && (
        <p className="hi-note">
          {STAGE.dqnCaptured}: {result.data_quality_notes.captured_as_run_notes} new ·{' '}
          {result.data_quality_notes.already_present} already there. Never read as a QC verdict.
        </p>
      )}
      {/* WHAT WAS READ AND NOT SENT (2026-10-12), every number the server's own. */}
      {result.readings_notes &&
        (result.readings_notes.measurements > 0 ||
          result.readings_notes.beamtime_notes_captured + result.readings_notes.beamtime_notes_already_present > 0) && (
          <p className="hi-note hi-readings-kept">
            {STAGE.readingsKept}: {result.readings_notes.captured_as_run_notes} new on runs ·{' '}
            {result.readings_notes.already_present} already there
            {result.readings_notes.beamtime_notes_captured + result.readings_notes.beamtime_notes_already_present > 0
              ? ` · for the whole beamtime, ${result.readings_notes.beamtime_notes_captured} new · ${result.readings_notes.beamtime_notes_already_present} already there`
              : ''}
            . {STAGE.readingsNever}
          </p>
        )}
      <p>
        <Link className="btn btn-secondary" to={ROUTES.recordView(result.experiment_id, 'proposals')}>
          {STAGE.openProposals}
        </Link>
      </p>
      {/* ~~The acceptance note, repeated here~~ (2026-10-18, QA `C-17`): it is said once,
          on the stage above, BEFORE a send, from the same capability. */}
      {result.runs_already_present && result.runs_already_present.length > 0 && (
        <Disclosure
          className="hi-disclosure"
          summary={STAGE.runsPresent}
          meta={String(result.runs_already_present.length)}
        >
          <ul className="hi-addwhole-sent">
            {result.runs_already_present.map((row) => (
              <li key={`${row.run_id}-${row.stem}`}>
                <span className="hi-candidate-target">{row.label}</span>
                <span className="hi-sub">{MATCHED_BY_LABELS[row.matched_by] ?? row.matched_by}</span>
              </li>
            ))}
          </ul>
        </Disclosure>
      )}
      {result.sent.length > 0 && (
        <Disclosure className="hi-disclosure" summary={STAGE.sentNowTitle} meta={String(onRecord)}>
          <ul className="hi-addwhole-sent">
            {result.sent.map((row) => (
              <li key={row.candidate_id}>
                <span className="hi-candidate-target">
                  {candidateLabel({
                    candidate_id: row.candidate_id,
                    kind: 'field',
                    target_field_path: row.target_field_path,
                  } as ApiImportCandidate)}
                </span>
                {/* THE SERVER'S OWN `already_sent`, never inferred from a second click. */}
                <span className="hi-sub">
                  {row.already_sent ? 'already there' : 'new'}
                  {row.run_id !== null ? ' · on a run' : ''}
                </span>
                <Link to={ROUTES.recordProposal(result.experiment_id, row.proposal_id)}>
                  Open it on that record
                </Link>
              </li>
            ))}
          </ul>
        </Disclosure>
      )}
      {groups.length > 0 && (
        /* ONE DISCLOSURE FOR WHAT WAS NOT SENT (2026-10-18): seven group rows under the
           report repeated the stage's own "What will not be sent" above it. */
        <Disclosure className="hi-disclosure" summary={STAGE.couldNotBeSent} meta={String(result.not_sent.length)}>
        <ul className="hi-addwhole-unsent">
          {groups.map((group) => (
            <li key={group.category}>
              <Disclosure
                className="hi-disclosure"
                summary={group.label}
                meta={String(group.rows.length)}
              >
                <ul className="hi-addwhole-sent">
                  {group.rows.map((row) => (
                    <li key={row.candidate_id}>
                      <span className="hi-candidate-target">
                        {candidateLabel({
                          candidate_id: row.candidate_id,
                          kind: row.kind as ApiImportCandidate['kind'],
                          target_field_path: row.target_field_path,
                        } as ApiImportCandidate)}
                      </span>
                      {/* WHY NOT — the server's SHORT sentence (QA `C-05`). The full one
                          is on the candidate's own row, behind "Why, in detail"; it is not
                          repeated here, and nothing on this element carries it. */}
                      <span className="hi-blocked-reason">{row.summary ?? row.reason}</span>
                    </li>
                  ))}
                </ul>
              </Disclosure>
            </li>
          ))}
        </ul>
        </Disclosure>
      )}
    </div>
  );
}

/* --------------------------------------------------------------------------
 * Refusals.
 * -------------------------------------------------------------------------- */

/**
 * A refusal, rendered with the SERVER's own reason where there is one.
 *
 * `BackendDown` is used only for a server that did not answer. A typed refusal is
 * the server answering CORRECTLY, and reporting it as "Backend Not Running" is the
 * defect `LoadMaterials` records for its own 409s.
 */
function Refusal({ error }: { error: ApiError }) {
  if (error.unreachable || error.htmlIntercept) {
    return <BackendDown error={error} />;
  }
  const body = error.body;
  const message =
    typeof body === 'object' && body !== null
      ? String((body as Record<string, unknown>).message ?? '')
      : '';
  return (
    <p className="hi-refusal" role="alert">
      <TriangleAlert size={14} strokeWidth={2.1} aria-hidden="true" />
      <span>
        {message ||
          `That request was refused${error.status ? ` (${error.status})` : ''} and nothing was changed.`}
      </span>
    </p>
  );
}
