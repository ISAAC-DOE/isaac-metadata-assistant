import './screens.css';
import './historical-import.css';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
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
import { Disclosure } from '../components/Disclosure';
import { HelpTip } from '../components/HelpTip';
import { SemanticStatus } from '../components/SemanticStatus';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
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
  BUCKET_ORDER,
  BUCKET_STATE,
  bucketCounts,
  candidateBucket,
  candidateLabel,
  conflictCount,
  conflictViews,
  defaultStage,
  groupUnsent,
  IMPORT_STAGES,
  MATCHED_BY_LABELS,
  plural,
  STAGE_WORKFLOW_STEP,
  stageReached,
  summaryItems,
  planFor,
  readyToSend,
  type ImportStageId,
} from '../lib/importStages';
import type {
  ApiImportAddedToExperiment,
  ApiImportCandidate,
  ApiImportListResponse,
  ApiImportSession,
  ApiImportSource,
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
 * ── WHY THE SESSION IS IN COMPONENT STATE AND NOT IN THE URL ────────────────
 *
 * A deliberate departure from the `?view=`/`?run=`/`?proposal=` convention, and
 * `lib/routes.ts` carries the argument: an import session is not durable, holds
 * no scientific state, and its useful output is the PROPOSAL it mints — which
 * already has its own deep link. A `?import=` would be a link to a working area
 * that may not exist when it is followed.
 *
 * ── ONE VOCABULARY, AND IT IS THE SERVER'S ──────────────────────────────────
 *
 * The workflow steps, their labels, the unbuilt step's disclosure and the
 * durability sentence all come from the response. A second copy in the browser
 * would be free to drift from the operation that enforces it, which is the
 * defect the retired step names already recorded once.
 */
export function HistoricalImport() {
  const list = useFetch<ApiImportListResponse>(() => api.listImports(), []);
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="imports" />}
      mainPad="pad"
      width="wide"
    >
      {/*
        ONE CONTAINER, ONE RHYTHM.
        =========================

        `.hi-screen` is the vertical-rhythm owner this screen did not have. Its
        four (or six) blocks used to be sibling `div.placeholder`s, and the gaps
        between them measured 8px, 4px and 0px — each one the residue of
        whichever element that block happened to end with, not a decision.
        `.hi-screen` sets ONE gap (`--space-lg`, 16px — the top of
        `spacing-layout.md:19`'s "gaps between cards 10–16px" band) and
        `historical-import.css` zeroes the last child's margin inside each
        section, so the spacing is a property of the container and survives any
        future edit to a section's contents.

        `.placeholder` is gone from this file entirely, and its name was the
        clearest statement of the problem: a class that declares a measure and
        calls itself a placeholder is not a section system.
      */}
      <div className="hi-screen">
        <header className="hi-page-head">
          <span className="eyebrow">{IMPORT_COPY.eyebrow}</span>
          {/* The ONE `<h1>` on this surface. `e2e/specs/structure.spec.ts` holds
              every surface to exactly one, and it reads `LABELS.navImports` — the
              same string the nav item and the `document.title` segment read, so
              the destination cannot end up with three names.

              `.page-title` is `screens.css`'s shared page-title class — 22px/600,
              `typography.md:46`'s "Page title (H2) 22px / 600". It used to inherit
              that size from `.placeholder > h1`; stating it through the shared
              class instead means dropping `.placeholder` does not silently hand
              the heading back to the UA's `2em`/bold default. */}
          <h1 className="page-title">{LABELS.navImports}</h1>
          <p className="hi-lead">{IMPORT_COPY.lead}</p>
        </header>

        {/*
          `LoadingPanel`, NOT a hand-rolled `role="status"` div — and the reason is
          an INVARIANT rather than consistency for its own sake.

          The first version of this screen rendered
          `<div className="placeholder" role="status">Loading imports…</div>`. It
          looked right and announced correctly, and it was INVISIBLE to
          `e2e/specs/layout-widths.spec.ts`, which asserts
          `locator('div.fetch-state[role="status"]')` has count 0 before it
          measures a surface — i.e. "no screen is still loading". A loading panel
          outside that class is a loading panel that sweep cannot wait for, so it
          would one day measure a skeleton and report it as this surface. Found
          while diagnosing that sweep's timeouts, not by a failing test.

          THE WRAPPER IS A `div`, NOT A `section`, HERE AND EVERYWHERE ON THIS
          SCREEN. `.hi-section` is a presentational grouping — a card with a
          measure, a padding and a rhythm — and an unnamed `<section>` is exposed
          as a generic container anyway, so the element would buy nothing while
          inviting a future `aria-labelledby` that would mint a `region` landmark
          per card. The accessibility tree is byte-for-byte what it was before
          this redesign, which is why the a11y baseline (zero recorded cells for
          `imports`) does not move.
        */}
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
        {list.status === 'data' && openId === null && (
          <ImportList data={list.data} onOpen={setOpenId} onChanged={list.reload} />
        )}
        {list.status === 'data' && openId !== null && (
          <ImportSessionView
            importId={openId}
            onClose={() => {
              setOpenId(null);
              list.reload();
            }}
          />
        )}
      </div>
    </AppShell>
  );
}

/* --------------------------------------------------------------------------
 * The list, and starting one.
 * -------------------------------------------------------------------------- */

function ImportList({
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
    <>
      {/*
        SECTION ONE — `New Import`, FIRST. The action a reader came here for.

        WHY THIS IS NOW FIRST, AND WHY "HOW IT WORKS" IS NOW LAST (below). The
        owner, of this exact page: "the text is still stopping midway through
        half the block, and it's not really something that looks good" — the
        landing used to open with a six-line paragraph and THEN a full
        stepper-plus-note block before a reader ever reached a control. This
        screen's own job is simple (one sentence in `.hi-lead` now says it):
        reconstruct candidate metadata from files already on hand. State,
        action, and value belong before explanation — the design direction
        this repo has recorded elsewhere as "state -> action -> blocker ->
        value -> source before explanation" — so `New Import` and `Imports`
        (the record of past sessions) now render immediately after the intro,
        and the longer "how the six stages work" explanation moves to a
        collapsed disclosure at the end of this list (see the closing
        `<details>` below).

        MEASURED BEFORE: `IMPORT_COPY.actionStart` ("Start an Import") rendered
        TWICE, 78px apart — once as this section's `<h2>` and once as the label of
        the primary button inside it. A section title that repeats its own primary
        action's verb tells the reader nothing the button did not already say, and
        it makes the same string an ambiguous target for anything (a test, a
        screen reader user cycling headings, a person) looking for "the control".

        THE RULE APPLIED HERE AND ONE MORE TIME BELOW: a section is titled by
        its SUBJECT and the button keeps the verb. So `New Import` names the thing;
        `Start an Import` remains the only place that verb appears.
      */}
      <div className="hi-section hi-landing-col">
        <h2 className="hi-section-title">New Import</h2>
        <label className="hi-field">
          <span className="hi-field-label">Name this import (optional)</span>
          <input
            className="hi-input"
            type="text"
            value={label}
            maxLength={200}
            onChange={(event) => setLabel(event.target.value)}
            placeholder="e.g. Cu K-edge campaign, 2019"
          />
        </label>
        <button type="button" className="btn btn-primary" onClick={start} disabled={busy}>
          <Plus size={14} strokeWidth={2.2} aria-hidden="true" />
          {busy ? 'Starting…' : IMPORT_COPY.actionStart}
        </button>
        {error !== null && <Refusal error={error} />}
      </div>

      {/*
        SECTION TWO — `Imports`.

        THE HEADING STRING IS LOAD-BEARING AND MUST NOT BE "IMPROVED".
        `e2e/surfaces.ts:141` declares this surface's ready gate as
        `{ role: 'heading', name: 'Imports' }` and
        `e2e/mutation/imports-session-a11y.spec.ts:64` asserts it at `level: 2` —
        both because it is inside the `status === 'data'` branch and so cannot
        render over a skeleton. Renaming it, or changing its level, silently turns
        thirteen sweeps into measurements of a loading state. (This is also why
        moving it above `New Import` keeps it exactly as it was rather than
        touching its text or level — only its ORDER on the page changed.)
      */}
      <div className="hi-section hi-landing-col">
        <h2 className="hi-section-title">Imports</h2>
        {data.total === 0 ? (
          /*
            THE EMPTY STATE IS NOW A BOX, and it is `/experiments`' box.

            MEASURED BEFORE: a 20x20 icon flush-left at x=275 with no container at
            all, then a `<strong>`, then a paragraph at a third body measure
            (895.9px). Three fragments, no card, nothing holding them together.

            It now reuses the shape `components/queue.css` already ships for the
            same job — bordered box, icon in a tinted ~30px square, Title Case
            title, one-sentence body, consistent gutters — rather than inventing a
            third card language. The icon drops 20px -> 18px to match
            `.queue-empty-action-mark`'s glyph inside its 30px square.

            The two strings are UNCHANGED (`IMPORT_COPY.emptyTitle` /
            `emptyBody`); only the box around them is new.
          */
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
              <li key={row.import_id} className="hi-list-row">
                <div className="hi-list-main">
                  <span className="hi-list-title">{row.label || 'Unnamed import'}</span>
                  <span className="hi-list-meta">
                    {row.source_count} source{row.source_count === 1 ? '' : 's'} ·{' '}
                    {row.parsed_source_count} read · {row.candidate_count} candidate
                    {row.candidate_count === 1 ? '' : 's'} · {row.proposed_count} sent to
                    review
                  </span>
                </div>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => onOpen(row.import_id)}
                >
                  {IMPORT_COPY.actionOpen}
                  {/* WHICH import, for a screen reader: a list of identical "Open"
                      buttons names none of them (independent review, 2026-09-23). */}
                  <span className="sr-only"> {row.label || 'Unnamed import'}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/*
        SECTION THREE — the explanation, collapsed, LAST.

        A NATIVE `<details>`, the repo's own idiom for exactly this move (see
        `RecordValidator.tsx`'s `.rec-val-purpose`, `HelpPanel.tsx`'s
        `.help-more`, `FetchStates.tsx`'s `.fetch-state-technical`): keyboard-
        operable (Tab to the `<summary>`, Enter/Space to toggle), and exposed
        to a screen reader as a native disclosure widget with its own
        expanded/collapsed state — no ARIA authored by hand, and none needed.

        NOTHING IS DELETED. The six-stage stepper and the server's own
        durability sentence are exactly what rendered here before this slice;
        only their POSITION (last, not first) and their default VISIBILITY
        (collapsed, not always-open) changed. `CLAUDE.md`'s own rule for this
        exact situation — never delete a scientific caveat or honesty claim,
        only relocate it behind progressive disclosure — is what this is: the
        durability sentence stays reachable by keyboard and to a screen
        reader, and "Nothing here becomes a value on its own" (the OTHER
        claim this slice had to preserve) never left the always-visible
        `.hi-lead` above, so it did not need this disclosure at all.
      */}
      <div className="hi-section hi-landing-col">
        {/* The shared `Disclosure` since 2026-09-23 (it was a native `<details>` with
            an 11px triangle); collapsed by default exactly as before. */}
        <Disclosure className="hi-how-it-works" summary="How Historical Import works">
          <WorkflowStrip steps={data.workflow} furthest={null} />
          {/* THE SERVER'S OWN SENTENCE about what a session is and is not. Same
              string, same `role="note"`, same server source as before — only
              now the last child of a collapsed disclosure rather than of an
              always-visible heading. */}
          <p className="hi-note" role="note">
            {data.durability}
          </p>
        </Disclosure>
      </div>
    </>
  );
}

/* --------------------------------------------------------------------------
 * The workflow strip — the server's steps, in the server's order.
 * -------------------------------------------------------------------------- */

/**
 * The six steps, with the reached one marked and the unbuilt one stated.
 *
 * IT IS NOT A WORKFLOW SPINE AND MUST NOT BE READ AS ONE. The record screen's
 * spine is server-DERIVED and GATED — it decides what a scientist may do next.
 * This strip is a description of a sequence: nothing here is locked, no step
 * blocks another, and `aria-current="step"` marks only where the session has
 * reached. Modelling an import as a gated pipeline would claim a completion
 * criterion nobody defined, which is the argument `workflow.py` already makes
 * for submission and `CLAUDE.md` §11 records for capture.
 */
function WorkflowStrip({
  steps,
  furthest,
}: {
  steps: ApiImportWorkflowStep[];
  furthest: string | null;
}) {
  /*
   * THE DISCLOSURE SITS BELOW THE ROW, NOT INSIDE IT, and that is unchanged
   * from the pill-row version this replaces — only the NODE's own shape and
   * the connector between nodes changed.
   *
   * WHAT CHANGED, AND WHY. The owner, of this exact row: "it should be a
   * little bit cleaner, and I think it should be like a circle-dotted thing
   * instead." The pill row (bordered/filled chips joined by a `›` chevron)
   * had already been through one correction — the SAME owner had previously
   * said of it "are they supposed to be clickable or something?", because a
   * bordered, filled chip is this app's shape for `.section-tab` and for
   * filter chips, both of which ARE controls. Removing the border and fill
   * (the prior fix, still in `.hi-step`'s base rule) answered "is it a
   * button" but not "is it clean" — six one-word labels chained by `›` still
   * read as a breadcrumb, not as a sequence with a position in it. A dot per
   * step, joined by a line, is the vocabulary this app already uses for
   * exactly that job: `components/workflow.css`'s record-screen spine
   * (`.spine-disc` + `.spine-step::before`) is a disc-and-connector stepper,
   * and `.trail-dot` (`evidence.css`) is the same disc vocabulary at its
   * smallest size. `.hi-step-node` below reuses that vocabulary rather than
   * inventing a third.
   *
   * THE UNBUILT NODE IS DASHED, NOT THE UNBUILT STEP'S CONNECTOR. Only the
   * CIRCLE for "Add to Experiments" is dashed; the line reaching it is the
   * same solid `--border-strong` every other segment uses, because the
   * dashing is a claim about that ONE step ("not built"), not about how far
   * the sequence has got.
   *
   * NARROW WIDTH: see `.hi-steps-wrap`'s `container-type` in
   * historical-import.css. Below the container's own measured 560px this
   * renders as a VERTICAL stepper (dot beside label, rows stacked, a
   * vertical connector) rather than the six-across horizontal row, which is
   * this file's own established pattern for "the safe direction to fail in"
   * (see `experiment-graph.css`'s `@container` comment) — a container query
   * responds to the CARD's rendered width, not the window's, which matters
   * here because a sidebar sits between them (see
   * `viewport-media-query-wrong-box` in this repo's own session memory).
   */
  const unbuilt = steps.filter((step) => !step.built && step.disclosure !== null);
  return (
    <div className="hi-steps-wrap">
      <ol className="hi-steps" aria-label="Historical import workflow">
        {steps.map((step) => {
          const reached = furthest !== null && step.id === furthest;
          return (
            <li
              key={step.id}
              className={`hi-step${reached ? ' reached' : ''}${step.built ? '' : ' unbuilt'}`}
              aria-current={reached ? 'step' : undefined}
              aria-describedby={
                !step.built && step.disclosure !== null ? `hi-step-note-${step.id}` : undefined
              }
            >
              {/* THE UNBUILT STEP OFFERS NO CONTROL -- not a disabled one. A
                  disabled button implies the act exists and is temporarily
                  unavailable, which is the claim section 15 forbids. The dot
                  itself carries no text and is `aria-hidden`: the state it
                  shows (reached / unbuilt / plain) is decorative reinforcement
                  of what the LABEL and `aria-current`/`aria-describedby`
                  already say, never the only way to know it. */}
              <span className="hi-step-node" aria-hidden="true" />
              <span className="hi-step-label">{step.label}</span>
            </li>
          );
        })}
      </ol>
      {unbuilt.map((step) => (
        <p className="hi-steps-disclosure" id={`hi-step-note-${step.id}`} key={step.id}>
          <span className="hi-steps-disclosure-subject">{step.label}:</span> {step.disclosure}
        </p>
      ))}
    </div>
  );
}

/* --------------------------------------------------------------------------
 * One session — SIX STAGES, ONE IN FOCUS (owner QA H1, 2026-09-22).
 * -------------------------------------------------------------------------- */

type ActFn = (name: string, run: () => Promise<unknown>) => Promise<void>;
type ActWithNext = (name: string, run: () => Promise<unknown>, next?: ImportStageId) => Promise<void>;

const STAGE = IMPORT_STAGE_COPY;

/**
 * AN OPENED IMPORT, AS A FOCUSED STAGE FLOW.
 *
 * ── WHAT THIS REPLACED ──────────────────────────────────────────────────────
 *
 * Every stage used to render at once, one card after another: the sources, what
 * was read, the whole corpus review, every candidate as a full card, and the batch
 * send. Measured at 1440px on the synthetic five-measurement archive: 43,994 px of
 * page, each of 101 candidates headed by a raw schema path and carrying its
 * normalisation rule in full, with internal tokens (`sources_disagree`,
 * `deterministic_fake`) on the surface.
 *
 * ── WHAT IT IS NOW ─────────────────────────────────────────────────────────
 *
 *  1. THE SUMMARY FIRST — the counts a reader decides from, before any detail.
 *  2. SIX STAGES AS TABS — Source Bundle · What ISAAC Read · Runs & Candidates ·
 *     Conflicts · Review · Add to Experiment — the owner's names, one in focus.
 *     Each shows ONE heading and ONE sentence; its explanation is behind a `?`.
 *  3. EVERY STAGE STAYS MOUNTED, the inactive ones `hidden`, so a half-typed form
 *     survives a trip to another stage and every guard that reads the DOM still
 *     reaches the text (the record screen's workspaces follow the same rule).
 *
 * The tabs are a real ARIA tablist: arrow keys move between them, Home/End jump,
 * and each panel is labelled by its tab. `aria-current="step"` still marks how far
 * the session has got — a fact the SERVER derives — on the stage that owns that step.
 */
function ImportSessionView({
  importId,
  onClose,
}: {
  importId: string;
  onClose: () => void;
}) {
  const session = useFetch(() => api.getImport(importId), [importId]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [stage, setStage] = useState<ImportStageId | null>(null);
  const destinations = useProposalDestinations();
  /* The stage on screen, kept for `act`: see "PINNED" below. */
  const activeRef = useRef<ImportStageId | null>(null);
  const [announcement, setAnnouncement] = useState('');
  const pendingFocus = useRef<string | null>(null);
  const [focusTick, setFocusTick] = useState(0);

  /*
   * THE RELOAD IS SILENT, which it was not until 2026-09-22 — and the stage flow is
   * why it has to be. A full reload put this component into `loading` and unmounted
   * every stage, so an open measurement, a half-chosen resolution or the stage in
   * focus were all lost on every act. `reloadSilent` re-reads the session and
   * replaces the data in place; a failed re-read is disclosed beside the stages
   * rather than swapping the page for a spinner.
   */
  const act: ActWithNext = useCallback(
    async (name, run, next) => {
      /*
       * PINNED. Until a reader picks a stage, the one shown is DERIVED from the
       * session — so without this, adding the first source re-derived it and swept
       * the reader from Source Bundle to What ISAAC Read mid-task, table and all
       * (caught by the import-session a11y spec). An act keeps the reader where they
       * are unless it names where to go next.
       */
      setStage((current) => current ?? activeRef.current);
      setBusy(name);
      setError(null);
      try {
        await run();
        session.reloadSilent();
        if (next) setStage(next);
        /* SAID AND FOCUSED (independent review, 2026-09-23): an act's result is
           announced in the stage's one polite region, and focus moves to what the act
           produced — its report or the stage heading — instead of being dropped when
           the control that had it re-renders away. */
        setAnnouncement(announcementFor(name));
        pendingFocus.current = name.startsWith('add-whole') ? '.hi-addwhole-result .hi-block-title' : '.hi-stage-title';
        setFocusTick((n) => n + 1);
      } catch (err) {
        setError(err instanceof ApiError ? err : new ApiError(String(err)));
      } finally {
        setBusy(null);
      }
    },
    [session],
  );

  /*
   * HIST-005's REPORT LIVES HERE, above the stages, because it cannot be re-derived
   * from the reloaded session: it is the server's statement about ONE request — its
   * counts and its reason per candidate it would not send — which the session never
   * stores. Reconstructing it would be composing a report rather than relaying one.
   */
  const [addedResult, setAddedResult] = useState<ApiImportAddedToExperiment | null>(null);

  /* Focus lands after the re-render that shows the act's result; until the target is
     on screen (a report renders a moment later), the request waits. */
  useEffect(() => {
    const selector = pendingFocus.current;
    if (!selector) return;
    const panel = document.querySelector('[role="tabpanel"]:not([hidden])');
    const target = panel?.querySelector<HTMLElement>(selector);
    if (target) {
      target.focus();
      pendingFocus.current = null;
    }
  });
  void focusTick;

  if (session.status === 'loading') {
    // Same reason as the list's, above.
    return (
      <div className="hi-section">
        <LoadingPanel label="Loading this import…" />
      </div>
    );
  }
  if (session.status === 'error') {
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
  const active: ImportStageId = stage ?? defaultStage(data);
  activeRef.current = active;
  const summary = summaryItems(data);

  return (
    <>
      {/*
        THE SESSION HEADER: what this is, a way out, and the counts a reader
        decides from. `Import Session` is the word the server's own durability
        sentence uses for this thing; the durability sentence itself stays visible
        (a working area a restart can end is a consequence, not a definition).
      */}
      <div className="hi-section hi-session-head">
        <span className="eyebrow hi-session-eyebrow">Import Session</span>
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
        <StageTabs session={data} active={active} onSelect={setStage} />
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
              <RunsStage
                data={data}
                busy={busy}
                onAct={act}
                importId={importId}
                destinations={destinations}
              />
            )}
            {id === 'conflicts' && (
              <ConflictsStage
                data={data}
                busy={busy}
                onAct={act}
                importId={importId}
                destinations={destinations}
              />
            )}
            {id === 'review' && (
              <ReviewStage
                data={data}
                busy={busy}
                onAct={act}
                importId={importId}
                destinations={destinations}
              />
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
                onGoTo={setStage}
              />
            )}
            {/* THE WAY ON. A tab strip alone leaves a first-time reader to guess that
                reading happens one tab over; this names the next stage and moves
                focus to its tab, so a keyboard reader lands where they asked to go. */}
            {IMPORT_STAGES.indexOf(id) < IMPORT_STAGES.length - 1 && (
              <div className="hi-stage-next">
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => {
                    const next = IMPORT_STAGES[IMPORT_STAGES.indexOf(id) + 1]!;
                    setStage(next);
                    window.setTimeout(() => document.getElementById(tabId(importId, next))?.focus(), 0);
                  }}
                >
                  Next: {STAGE[IMPORT_STAGES[IMPORT_STAGES.indexOf(id) + 1]!].title}
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/*
        THE SAME RULE AS `New Import`: the section is titled by its subject and the
        button keeps the verb. `This Working Area` is the server's own words for
        what a session is (`IMPORT_COPY.discardNote`). The consequence stays in the
        open beside the destructive button, never behind a disclosure.
      */}
      <div className="hi-section hi-discard">
        <h3 className="hi-section-title">{STAGE.discardTitle}</h3>
        <p className="hi-note">{IMPORT_COPY.discardNote}</p>
        <button
          type="button"
          className="btn btn-danger"
          disabled={busy !== null}
          onClick={() =>
            act('discard', async () => {
              await api.deleteImport(importId);
              onClose();
            })
          }
        >
          {IMPORT_COPY.actionDiscard}
        </button>
      </div>
    </>
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
  onSelect: (stage: ImportStageId) => void;
}) {
  const candidates = session.reconstruction?.candidates ?? [];
  const counts = bucketCounts(candidates.filter((c) => c.kind === 'field'));
  const conflicts = conflictCount(session);
  const measurements = session.corpus_digest?.measurement_units;
  const furthestStage = IMPORT_STAGES.filter((s) => STAGE_WORKFLOW_STEP[s] === session.furthest_step)[0];
  const unbuilt = (s: ImportStageId) =>
    session.workflow.find((step) => step.id === STAGE_WORKFLOW_STEP[s])?.built === false;

  const meta: Record<ImportStageId, string> = {
    sources: plural(session.sources.length, 'source', 'sources'),
    read:
      session.corpus_digest
        ? plural(session.corpus_digest.statements_read, 'statement', 'statements')
        : `${session.source_counts.parsed} of ${session.source_counts.total} read`,
    runs:
      measurements !== undefined && measurements !== null
        ? plural(measurements, 'measurement', 'measurements')
        : plural(candidates.length, 'candidate', 'candidates'),
    conflicts: conflicts === 0 ? 'none' : plural(conflicts, 'open', 'open'),
    review: `${counts.needsReview.toLocaleString('en-US')} need review`,
    add: unbuilt('add') ? STAGE.stateLabels.notBuilt : `${readyToSend(session).length.toLocaleString('en-US')} ready`,
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
    onSelect(next);
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
              id === 'conflicts' && conflicts > 0 ? ' has-conflicts' : ''
            }`}
            onClick={() => onSelect(id)}
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

/** What an act says in the stage's polite region when it succeeds. */
function announcementFor(name: string): string {
  if (name === 'add-archive') return 'Archive added to the source bundle.';
  if (name === 'add-fixture') return 'Example source added to the source bundle.';
  if (name === 'add-reference' || name === 'record-staged-file') return 'Recorded as a source.';
  if (name.startsWith('remove:')) return 'Source removed.';
  if (name === 'parse') return 'Sources read.';
  if (name === 'reconstruct') return 'Candidates reconstructed. Showing Runs & Candidates.';
  if (name.startsWith('add-whole') && !name.endsWith(':create')) return 'Sent to the record. The report is below.';
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
  const [archive, setArchive] = useState(data.available_archives[0] ?? '');

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
        actually READS — an archive and an example source — first, side by side;
        then staging a file from this computer (browser-local, its privacy statement
        on every row and in the drop zone itself); then, behind a disclosure, a
        pointer to a file that must stay where it is.
      */}
      <div className="hi-forms">
        {data.available_archives.length > 0 && (
          <form
            className="hi-form"
            onSubmit={(event) => {
              event.preventDefault();
              void onAct('add-archive', () =>
                api.addImportSource(importId, { kind: 'archive', archiveName: archive }),
              );
            }}
          >
            <h4 className="hi-group-title">{IMPORT_COPY.actionAddArchive}</h4>
            <label className="hi-field">
              <span className="hi-field-label">Which archive</span>
              <select className="hi-input" value={archive} onChange={(event) => setArchive(event.target.value)}>
                {data.available_archives.map((name) => (
                  <option key={name} value={name}>
                    {name.startsWith('staged:') ? `${archiveLabel(name)} (staged on the server)` : archiveLabel(name)}
                  </option>
                ))}
              </select>
            </label>
            <button type="submit" className="btn btn-secondary" disabled={busy !== null || !archive}>
              {IMPORT_COPY.actionAddArchive}
            </button>
            <HelpTip subject="reading an archive">{IMPORT_COPY.addArchiveNote}</HelpTip>
          </form>
        )}

        {data.available_fixtures.length > 0 && (
          <form
            className="hi-form"
            onSubmit={(event) => {
              event.preventDefault();
              void onAct('add-fixture', () =>
                api.addImportSource(importId, { kind: 'synthetic_fixture', fixtureName: fixture }),
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
            <button type="submit" className="btn btn-secondary" disabled={busy !== null || !fixture}>
              {IMPORT_COPY.actionAddFixture}
            </button>
          </form>
        )}
      </div>

      {/* THE FILE PICKER. `ImportFileStaging` takes `onRecord` as a prop and so
          cannot import the API client: it cannot send a byte by construction. What
          reaches ISAAC is a file's name, size, type and — only if asked — a
          checksum computed in this tab. `POST /api/uploads` stays an unconditional
          403 and nothing here calls it, whatever `historical_file_ingestion` says:
          that capability opens a server-side staging directory, never this route. */}
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
}: {
  source: ApiImportSource;
  busy: string | null;
  onRemove: () => void;
}) {
  const state = PARSE_STATE_LABELS[source.parse_state] ?? source.parse_state;
  return (
    <tr>
      <td>
        {/* An ARCHIVE is named in words; its id and where it was read from are one press
            away, because a staged archive's reference IS its id (`staged:<name>`) and
            printing it beside the name put the raw token straight back (review of #279). */}
        {source.kind === 'archive' ? (
          <span className="hi-filename">
            {archiveLabel(source.filename)}{' '}
            <HelpTip subject={`the archive ${archiveLabel(source.filename)}`}>
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
            <span className="hi-filename">{source.filename}</span>
            <span className="hi-reference">{source.reference}</span>
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
          aria-label={`${IMPORT_COPY.actionRemoveSource} ${source.kind === 'archive' ? archiveLabel(source.filename) : source.filename}`}
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
  return (
    <>
      <StageHead stage="read" />
      <div className="hi-stage-action">
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy !== null || counts.parsable_by_this_build === 0}
          onClick={() => onAct('parse', () => api.parseImport(importId), 'read')}
        >
          {busy === 'parse' ? 'Reading…' : IMPORT_COPY.actionParse}
        </button>
        <p className="hi-counts">
          {counts.total} source{counts.total === 1 ? '' : 's'} · {counts.parsed} read ·{' '}
          {counts.no_content_path} held as a pointer · {counts.failed} could not be read ·{' '}
          {counts.parsable_by_this_build} readable by this build
        </p>
      </div>
      {/* NEVER A BARE DISABLED BUTTON: the sentence beside it says why. */}
      {counts.parsable_by_this_build === 0 && (
        <p className="hi-note">
          Nothing in this bundle can be read by this build yet. Add an example source or an
          archive, or keep the references — they are stored either way.
        </p>
      )}

      {data.corpus_review && (
        <CorpusReadOverview
          review={data.corpus_review}
          profiles={data.profiles ?? []}
          units={data.archive?.units_page.rows ?? []}
        />
      )}

      {data.parsed.length > 0 && (
        <ul className="hi-parsed-list">
          {data.parsed.map((parsed) => (
            <li key={parsed.source_id}>
              <Disclosure
                className="hi-parsed"
                summary={<span className="hi-filename">{parsed.filename}</span>}
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

function useFilenameOf(data: ApiImportSession) {
  return useCallback(
    (sourceId: string) => data.sources.find((s) => s.source_id === sourceId)?.filename ?? sourceId,
    [data.sources],
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

  return (
    <>
      <StageHead stage="runs" lead={archive ? STAGE.runs.leadArchive : STAGE.runs.leadFixture} />
      <div className="hi-stage-action">
        <button
          type="button"
          className="btn btn-primary"
          /* AN ARCHIVE HAS SOMETHING TO RECONSTRUCT FROM even though `parsed` is empty:
             the whole chain runs at the READ, so the candidates already exist. */
          disabled={busy !== null || (data.parsed.length === 0 && !data.corpus_review)}
          onClick={() => onAct('reconstruct', () => api.reconstructImport(importId), 'runs')}
        >
          {busy === 'reconstruct' ? 'Reconstructing…' : IMPORT_COPY.actionReconstruct}
        </button>
        {reconstruction !== null && (
          <p className="hi-counts">
            {plural(candidates.length, 'candidate', 'candidates')} · nothing was applied
          </p>
        )}
      </div>
      {/* THE PRECONDITION AND THE NEXT ACT, never the internal state. */}
      {data.parsed.length === 0 && !data.corpus_review && (
        <p className="hi-note">
          Nothing has been read yet, so there is nothing to reconstruct from. Read a source
          first. Reconstruction is deterministic in this build — it reads the statements
          already parsed and calls no model.
        </p>
      )}

      {reconstruction === null && !archive ? (
        <p className="hi-body hi-empty-inline">
          {data.source_counts.parsed > 0 || data.corpus_review
            ? IMPORT_COPY.emptyCandidatesReadBody
            : IMPORT_COPY.emptyCandidatesBody}
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
          onAct={onAct}
          destinations={destinations}
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
                {fields.map((c) => (
                  <ImportCandidateRow key={c.candidate_id} candidate={c} filenameOf={filenameOf} />
                ))}
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
  /* PER-SCAN VARIATION IS NOT A CONFLICT, and a reader who remembers seeing more
     "conflicts" before is told where those values went — neutrally, with a count. */
  const varying = (data.reconstruction?.candidates ?? []).filter((c) => c.agreement === 'varies').length;
  /* THE TWO SETS THIS STAGE HOLDS, NAMED (2026-09-23): the tab's number is their sum;
     Review counts only the field values; Add counts only what it cannot send. */
  const structural = views.filter((v) => v.kind === 'structural').length;
  const field = views.length - structural;
  return (
    <>
      <StageHead stage="conflicts" />
      {views.length > 0 && (
        <p className="hi-counts">
          {plural(structural, 'finding', 'findings')} about which measurement a file is ·{' '}
          {plural(field, 'field value', 'field values')} whose sources disagree
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
  const counts = bucketCounts(fields);
  const buckets = BUCKET_ORDER.filter((b) => counts[b] > 0);
  const sentReady = fields.filter((c) => candidateBucket(c) === 'ready' && data.proposed[c.candidate_id]).length;
  /* WHICH MEASUREMENT, for an archive: the unit that lists the candidate, named by its
     legacy number and label — the handle the Runs stage already uses. */
  const contextOf = new Map<string, string>();
  for (const row of data.archive?.units_page.rows ?? []) {
    const handle = row.legacy_number !== null ? `#${row.legacy_number} · ${row.label}` : row.label;
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
            {buckets.map((b) => {
              /* "Ready to Send" counts what can STILL go forward: a candidate this import
                 already sent is counted as sent, beside it, not as ready again. */
              const n = b === 'ready' ? counts.ready - sentReady : counts[b];
              return n > 0 ? (
                <SemanticStatus
                  key={b}
                  state={BUCKET_STATE[b]}
                  label={`${n.toLocaleString('en-US')} ${STAGE.bucketTitles[b]}`}
                />
              ) : null;
            })}
            {sentReady > 0 && (
              <SemanticStatus
                state="complete"
                label={`${sentReady.toLocaleString('en-US')} ${STAGE.stateLabels.sent}`}
              />
            )}
            {/* What sending does, one press away rather than a paragraph above the list. */}
            <HelpTip subject={STAGE.bucketTitles.ready}>{IMPORT_COPY.reviewLead}</HelpTip>
          </div>
          {buckets.map((b) => (
            <Disclosure
              key={b}
              className="hi-bucket"
              headingLevel={4}
              defaultOpen={b === 'ready'}
              summary={STAGE.bucketTitles[b]}
              meta={counts[b].toLocaleString('en-US')}
            >
              <ul className="hi-cands">
                {fields
                  .filter((c) => candidateBucket(c) === b)
                  .map((candidate) => (
                    <ImportCandidateRow
                      key={candidate.candidate_id}
                      candidate={candidate}
                      filenameOf={filenameOf}
                      already={data.proposed[candidate.candidate_id]}
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
                  ))}
              </ul>
            </Disclosure>
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
        experimentId={experimentId}
        value={runId}
        onChange={setRunId}
        label="Which run? (required for a value a run owns)"
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

/**
 * A run CHOSEN FROM THE RECORD'S OWN RUNS, never a typed id — and only when the
 * record has any. Blank means "no run", which is correct for every value the record
 * itself owns.
 */
function RunPicker({
  experimentId,
  value,
  onChange,
  label,
}: {
  experimentId: string;
  value: string;
  onChange: (id: string) => void;
  label: string;
}) {
  const [runs, setRuns] = useState<{ id: string; label: string }[] | null>(null);
  useEffect(() => {
    let alive = true;
    setRuns(null);
    onChange('');
    if (!experimentId.trim()) return;
    api
      .listRuns(experimentId)
      .then((res) => {
        if (!alive) return;
        setRuns((res.runs ?? []).map((r) => ({ id: r.id, label: r.label || r.id })));
      })
      .catch(() => {
        if (alive) setRuns([]);
      });
    return () => {
      alive = false;
    };
    // `onChange` is a state setter; re-running on it would clear a choice on render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [experimentId]);
  if (!experimentId.trim() || runs === null || runs.length === 0) return null;
  return (
    <label className="hi-field">
      <span className="hi-field-label">{label}</span>
      <select className="hi-input" value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">No run — a value the record owns</option>
        {runs.map((run) => (
          <option key={run.id} value={run.id}>
            {run.label}
          </option>
        ))}
      </select>
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
      {busy === actKey ? 'Creating…' : 'New record from this import'}
    </button>
  );
}

/* --------------------------------------------------------------------------
 * Stage 6 — Add to Experiment (`HIST-005`).
 * -------------------------------------------------------------------------- */

/**
 * ADD EVERY READY CANDIDATE TO ONE RECORD, IN ONE REQUEST — and say beforehand what
 * will and will not go, in words.
 *
 * ONE request because a client loop would be N writes that could each fail alone,
 * leaving a record holding part of an import with nothing able to say which part.
 * The report renders what the SERVER said — every count, the reason per candidate it
 * would not send, `already_sent`, and how each measurement's run was found — never
 * what was asked for.
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
  const [createRuns, setCreateRuns] = useState(archive);
  /* ONE PLAN, the batch's own partition (`send_plan`) — so what this stage says will
     happen is what the report then says did (2026-09-23). */
  const plan = planFor(data, archive && createRuns);
  const sendable = plan.willSend;
  const blocked = groupUnsent(plan.unsent);
  const blockedTotal = plan.unsent.length;
  const sentTo = new Map<string, number>();
  for (const id of plan.alreadySent) {
    const target = data.proposed[id]?.experiment_id;
    if (target) sentTo.set(target, (sentTo.get(target) ?? 0) + 1);
  }
  const titleOf = (id: string) => destinations.rows?.find((r) => r.id === id)?.title ?? 'a record';
  const key = `add-whole:${importId}`;
  const step = data.workflow.find((s) => s.id === 'add_to_experiments');
  const acceptance = data.capabilities?.proposal_acceptance;

  return (
    <>
      <StageHead stage="add" />

      {step && !step.built && step.disclosure !== null ? (
        /* THE UNBUILT STEP OFFERS NO CONTROL — not a disabled one. The server's own
           sentence says why. */
        <p className="hi-steps-disclosure" id={`hi-step-note-${step.id}`}>
          <span className="hi-steps-disclosure-subject">{step.label}:</span> {step.disclosure}
        </p>
      ) : (
        <>
          <div className="hi-add-summary">
            <h4 className="hi-block-title">{STAGE.addSummaryTitle}</h4>
            <p className="hi-counts">
              {plural(sendable.length, 'candidate can', 'candidates can')} be sent
              {blockedTotal > 0 ? ` · ${blockedTotal.toLocaleString('en-US')} will not be` : ''}
              {plan.alreadySent.length > 0
                ? ` · ${plan.alreadySent.length.toLocaleString('en-US')} already sent`
                : ''}
            </p>
            {/* WHAT THIS IMPORT ALREADY SENT survives a reload: the session remembers
                each send (`proposed`), even though the last report is not kept. */}
            {sentTo.size > 0 && (
              <ul className="hi-add-blocked">
                {[...sentTo.entries()].map(([id, count]) => (
                  <li key={id}>
                    <span className="hi-add-blocked-count">{count.toLocaleString('en-US')}</span> already
                    sent to{' '}
                    <Link to={ROUTES.recordView(id, 'proposals')}>{titleOf(id)}</Link>
                  </li>
                ))}
              </ul>
            )}
            {blocked.length > 0 && (
              <ul className="hi-add-blocked">
                {blocked.map((group) => (
                  <li key={group.category}>
                    <span className="hi-add-blocked-count">{group.rows.length.toLocaleString('en-US')}</span>{' '}
                    {group.label}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {sendable.length === 0 ? (
            <p className="hi-body hi-empty-inline">
              {plan.alreadySent.length > 0
                ? 'Everything this import can send has been sent.'
                : 'Nothing in this import can be sent yet. Resolve its field conflicts, or read and reconstruct its sources first.'}
            </p>
          ) : sendable.length === 1 ? (
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
                    onChange={(event) => setCreateRuns(event.target.checked)}
                  />
                  <span>{STAGE.createRuns}</span>
                </label>
              )}
              {!createRuns && (
                <RunPicker
                  experimentId={experimentId}
                  value={runId}
                  onChange={setRunId}
                  label="Which run? (for the values a run owns)"
                />
              )}
              <p className="hi-note">{IMPORT_COPY.addWholeRunNote}</p>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={busy !== null || !experimentId.trim()}
              >
                {busy === key ? 'Sending…' : IMPORT_COPY.actionAddWhole}
              </button>
            </form>
          )}

          {result !== null && (
            <AddResult result={result} acceptanceUnavailable={acceptance?.available === false} />
          )}
        </>
      )}
    </>
  );
}

function AddResult({
  result,
  acceptanceUnavailable,
}: {
  result: ApiImportAddedToExperiment;
  /** The server's own `proposal_acceptance` capability says no reviewer can be identified. */
  acceptanceUnavailable: boolean;
}) {
  const groups = groupUnsent(result.not_sent);
  return (
    <div className="hi-addwhole-result">
      <h4 className="hi-block-title" tabIndex={-1}>
        {IMPORT_COPY.addWholeResultTitle}
      </h4>
      {/* EVERY NUMBER FROM `counts`, AND ALL OF THEM. */}
      <p className="hi-counts">
        {result.counts.sent} sent · {result.counts.already_sent} already there ·{' '}
        {result.counts.not_sent} could not be sent · {result.counts.candidates} candidate
        {result.counts.candidates === 1 ? '' : 's'} in this import
        {typeof result.counts.runs_created === 'number' ? ` · ${result.counts.runs_created} runs created` : ''}
      </p>
      {result.counts.sent === 0 && result.counts.already_sent > 0 && (
        <p className="hi-sent" role="note">
          {IMPORT_COPY.addWholeNothingNew}
        </p>
      )}
      {result.reread_for_target && <p className="hi-note">{STAGE.reread}</p>}
      {result.data_quality_notes && result.data_quality_notes.available > 0 && (
        <p className="hi-note">
          {STAGE.dqnCaptured}: {result.data_quality_notes.captured_as_run_notes} new ·{' '}
          {result.data_quality_notes.already_present} already there. Never read as a QC verdict.
        </p>
      )}
      <p>
        <Link className="btn btn-secondary" to={ROUTES.recordView(result.experiment_id, 'proposals')}>
          {STAGE.openProposals}
        </Link>
      </p>
      {/* SAID WHERE THE READER GOES TO REVIEW, and only when the server says so:
          accepting needs an identified reviewer this deployment cannot yet provide. */}
      {acceptanceUnavailable && <p className="hi-note">{STAGE.acceptanceNote}</p>}
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
        <Disclosure className="hi-disclosure" summary="Sent candidates" meta={String(result.sent.length)}>
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
                  {row.already_sent ? 'already there' : 'sent'}
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
                      {/* WHY NOT, IN THE SERVER'S WORDS — the sentence the candidate's
                          own row shows. */}
                      <span className="hi-blocked-reason">{row.reason}</span>
                    </li>
                  ))}
                </ul>
              </Disclosure>
            </li>
          ))}
        </ul>
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
