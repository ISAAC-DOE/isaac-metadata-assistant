import './screens.css';
import './historical-import.css';
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { BackendDown, LoadingPanel } from '../components/FetchStates';
import { CircleAlert, Inbox, Plus, TriangleAlert } from '../components/icons';
import { ImportFileStaging } from '../components/ImportFileStaging';
import { LABELS } from '../lib/labels';
import { stripLifecycleSuffix } from '../lib/adapt';
import { ROUTES } from '../lib/routes';
import { api, ApiError } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import {
  DETERMINISM_LABELS,
  IMPORT_COPY,
  PARSE_STATE_LABELS,
  SOURCE_KIND_LABELS,
} from '../lib/historicalImportContent';
import type {
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
        <details className="hi-how-it-works">
          <summary>How Historical Import works</summary>
          <WorkflowStrip steps={data.workflow} furthest={null} />
          {/* THE SERVER'S OWN SENTENCE about what a session is and is not. Same
              string, same `role="note"`, same server source as before — only
              now the last child of a collapsed disclosure rather than of an
              always-visible heading. */}
          <p className="hi-note" role="note">
            {data.durability}
          </p>
        </details>
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
 * One session.
 * -------------------------------------------------------------------------- */

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

  const act = useCallback(
    async (name: string, run: () => Promise<unknown>) => {
      setBusy(name);
      setError(null);
      try {
        await run();
        session.reload();
      } catch (err) {
        setError(err instanceof ApiError ? err : new ApiError(String(err)));
      } finally {
        setBusy(null);
      }
    },
    [session],
  );

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

  return (
    <>
      {/*
        THE SESSION HEADER.

        WHAT CHANGED, AND IT IS ORDER AS MUCH AS STYLE. `Back to imports` used to
        be the FIRST child, above the session's own name, so the block opened with
        a way out rather than with what a reader had opened. The title now leads
        and the control sits on its own baseline to the right of it
        (`.hi-section-head`), which is the arrangement every other detail surface
        in this app uses.

        THE EYEBROW IS NEW and is the cheapest honest way to say what this block
        is: the `<h1>` says `Historical Import` and this `<h2>` says the session's
        label, so without it two headings of different sizes sat above each other
        with nothing naming the relationship. `.eyebrow` is `base.css`'s shared
        mono/uppercase/.09em idiom — `typography.md:55`, "Eyebrow (section) | Mono
        | 11px / uppercase | letter-spacing .09em".

        `Import Session` claims nothing: it is the word the server's own durability
        sentence, rendered two lines below, already uses for this thing.
      */}
      <div className="hi-section">
        <span className="eyebrow hi-session-eyebrow">Import Session</span>
        <div className="hi-section-head">
          <h2 className="hi-section-title">{data.label || 'Unnamed import'}</h2>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Back to imports
          </button>
        </div>
        <WorkflowStrip steps={data.workflow} furthest={data.furthest_step} />
        <p className="hi-note" role="note">
          {data.durability}
        </p>
        {error !== null && <Refusal error={error} />}
      </div>

      <SourcesSection
        data={data}
        busy={busy}
        onAct={act}
        importId={importId}
      />

      <ParseSection data={data} busy={busy} onAct={act} importId={importId} />

      <CandidatesSection data={data} busy={busy} onAct={act} importId={importId} />

      {/*
        THE SAME RULE AS `New Import`: the section is titled by its subject and the
        button keeps the verb. This heading was `IMPORT_COPY.actionDiscard`
        ("Discard This Import") — the exact label of the `btn-danger` three lines
        below it — so the destructive act's name appeared twice and the section
        read as a second button.

        `This Working Area` is the server's own words for what a session is
        (`IMPORT_COPY.discardNote`: "Discarding removes this working area"), so the
        title borrows the vocabulary the disclosure beneath it already uses rather
        than introducing a fourth noun for the same thing.
      */}
      <div className="hi-section">
        <h3 className="hi-section-title">This Working Area</h3>
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

/* --------------------------------------------------------------------------
 * Sources.
 * -------------------------------------------------------------------------- */

type ActFn = (name: string, run: () => Promise<unknown>) => Promise<void>;

function SourcesSection({
  data,
  busy,
  onAct,
  importId,
}: {
  data: ApiImportSession;
  busy: string | null;
  onAct: ActFn;
  importId: string;
}) {
  const [filename, setFilename] = useState('');
  const [reference, setReference] = useState('');
  const [sha256, setSha256] = useState('');
  const [fixture, setFixture] = useState(data.available_fixtures[0] ?? '');

  return (
    <div className="hi-section">
      {/* `Sources` is already a subject, not a verb, so this heading needed no
          change — and `e2e/mutation/imports-session-a11y.spec.ts:147` gates on
          `heading /Sources/i`, so it must keep matching. */}
      <h3 className="hi-section-title">Sources</h3>
      {/*
        ONE LEAD VISIBLE, THE REST COLLAPSED. *"once again there is too much word
        clutter, put the question mark tooltip icons that users can click instead
        if they are curious"* — project owner, 2026-09-14.

        `sourcesLead` stays on the page because it is the one sentence that
        changes what a reader DOES here: a source is a pointer, and this workflow
        does not open the file it names. The other two explain the example
        sources and which layout is read — true, load-bearing for anyone
        auditing the claim, and read once.

        A native `<details>` rather than a tooltip icon: the content is two
        paragraphs, not a phrase, and a hover tooltip is unreachable by keyboard
        and by touch. It keeps the text in the DOM and the accessibility tree, so
        `historical-import.test.tsx`'s copy assertions still reach it.
      */}
      <p className="hi-body">{IMPORT_COPY.sourcesLead}</p>
      <details className="hi-more">
        <summary className="hi-more-summary">What counts as a source here</summary>
        <p className="hi-body">{IMPORT_COPY.fixturesLead}</p>
        <p className="hi-note">{IMPORT_COPY.formatsNote}</p>
      </details>

      {data.sources.length === 0 ? (
        <p className="hi-body hi-empty-inline">{IMPORT_COPY.emptySourcesBody}</p>
      ) : (
        <table className="hi-table">
          <caption className="sr-only">
            The source bundle: what each entry is, and what this build could read from it
          </caption>
          <thead>
            <tr>
              <th scope="col">File</th>
              <th scope="col">Kind</th>
              <th scope="col">Where it is</th>
              <th scope="col">Read?</th>
              <th scope="col">
                <span className="sr-only">Actions</span>
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
        ── THE FILE PICKER, AND THE RECORDED DECLINE IT REVERSES ─────────────
        *"for the historical import, there is no area or button to actually upload
        the files"* — project owner, 2026-09-14. ~~Correct observation, and the
        answer is a refusal rather than a gap.~~

        *** REVERSED 2026-09-15 BY THE PROJECT OWNER (`DEC-33`), AND THE DECLINE
        BELOW IS KEPT IN FULL BECAUSE IT WAS RIGHT ABOUT THE RISK. He did not
        overrule its argument; he ANSWERED it, and supplied the mitigation it
        asked for: a staged file must read `Local only — not sent to ISAAC`. His
        instruction was explicit — *"Do not merely delete the guards. Reconcile
        them."* ***

        WHAT MAKES THE REVERSAL HONEST RATHER THAN A LOOSENING — and it is a
        measurement, not an argument. `POST /api/imports/{id}/sources` ALREADY
        accepts `kind: "reference"` with `filename`, `reference`, `media_type`,
        `size_bytes` and `sha256`; it stores them verbatim, FETCHES NOTHING, and
        records the entry as `parse_state: "no_content_path"`. A browser hands
        over `File.name`, `File.size` and `File.type` as part of the SELECTION —
        no read is involved. Proved over HTTP on 2026-09-15: an entry sent that
        way lands with the real filename, the real size, a genuine digest and
        `no_content_path`. So this adds no route, no capability and no
        governance change. `POST /api/uploads` is still an unconditional 403 and
        nothing here calls it.

        THE PANEL CANNOT SEND A BYTE BY CONSTRUCTION, which is stronger than a
        promise in a comment: `ImportFileStaging` takes `onRecord` as a prop and
        therefore cannot import the API client. Asserted structurally AND
        behaviourally in `import-file-staging.test.tsx`.

        ~~I BUILT A MULTI-FILE PICKER AND REVERTED IT. It read no bytes — only
        `File.name`, which a browser hands over with the selection — and it would
        have turned "type twelve filenames" into one act. Two committed guards
        refused it, and both are right:

          * `historical-import.test.tsx` §1 asserts this screen renders NO
            `input[type="file"]`, declares no `type="file"` in its source, and
            has no `onDrop`, `FormData` or `multipart`. Its stated subject is
            "the destination cannot accept bytes and does not say it can".
          * `upload-claim-parity.test.tsx` asserts that EXACTLY TWO non-test
            files in `apps/web/src` declare a file input, and names both — so a
            third anywhere fails, whatever it does.

        THE REASONING THAT BEATS THE FEATURE REQUEST: `POST /api/uploads` answers
        an unconditional 403 and real-data ingestion is out of scope (`CLAUDE.md`
        §15). A "Choose Files…" button is an upload affordance whatever it does
        underneath — a scientist who picked twelve files would reasonably believe
        twelve files had been uploaded. Recording their names while they believe
        that is worse than asking them to type, because it is a false impression
        the product created on purpose.

        So this section keeps the reference form, and the honest mechanism is
        made obvious instead: a reference is a POINTER a later build can follow.~~

        THE ONE SENTENCE OF THE DECLINE THAT STILL GOVERNS: *"a scientist who
        picked twelve files would reasonably believe twelve files had been
        uploaded."* That is why the disclosure is on every ROW and in the drop
        zone itself, visible rather than in a tooltip — a privacy state is one of
        the things the copy rule keeps out in the open — and why the checksum,
        the only thing here that reads a file, is opt-in per file and says so
        before it runs.
      */}
      <ImportFileStaging
        busy={busy !== null}
        onRecord={async (input) => {
          /*
           * THE API CALL IS DELIBERATELY NOT ROUTED THROUGH `onAct`, and the
           * reason is where the failure lands. `onAct` catches and puts the
           * refusal in this SECTION's banner — correct for a single form, wrong
           * for a list, because a reader with four staged files would see one
           * banner and no indication of WHICH row the server refused. So the
           * call is made directly, its rejection propagates to the row that
           * caused it, and `onAct` is used afterwards only for its reload.
           */
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

      {/* `Record a reference` IS NOW SECONDARY, per `DEC-33`, and is deliberately
          NOT removed. It is the only way to describe a file that must stay where
          it is — external storage, a large raw dataset, a path on an instrument
          machine — which a browser file picker cannot express at all, because a
          browser does not disclose a local path. So it moves behind a disclosure
          and keeps every field it had. */}
      <details className="hi-reference-fallback">
        <summary>Add an external reference instead</summary>
        <p className="hi-note">
          For a file that has to stay where it is — on an instrument machine, in
          group storage, or anywhere ISAAC cannot be pointed at. You describe
          where it is; nothing is fetched.
        </p>
      <div className="hi-forms">
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
          {/*
              THESE TWO GROUP HEADINGS DO ECHO THEIR OWN BUTTONS, AND THEY ARE
              LEFT THAT WAY DELIBERATELY. I applied the section rule here first —
              subject-titled `Reference` and `Example Source`, buttons keeping the
              verbs — and MEASURED it into a worse defect: `Reference` and
              `Example source` are already the SOURCE_KIND labels rendered in the
              Kind column of the table 30 lines above
              (`historicalImportContent.ts:76-79`), so the screen then used one
              word for two different things — a group of controls, and a value in
              a column. `historical-import.test.tsx:516`
              (`getByText('Reference')`) failed on exactly that ambiguity, which
              is the guard working rather than an obstacle.

              The echo is also weaker here than it was on the `<h2>`s: this is a
              `<form>` whose heading acts as a legend and whose `btn-secondary`
              confirms it, not a section title standing over a `btn-primary`. The
              four places the rule DID apply are the ones where a section title
              repeated the screen's primary action.
          */}
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
      </div>
      </details>

      {/* THE EXAMPLE SOURCE STAYS OUT IN THE OPEN and is deliberately NOT inside
          the external-reference disclosure: it is the one source kind this build
          actually READS, so it is the only way to exercise parse and
          reconstruction end to end. Burying it under "add an external reference
          instead" would hide the only entry that can produce a candidate. */}
      <div className="hi-forms">

        {data.available_fixtures.length > 0 && (
          <form
            className="hi-form"
            onSubmit={(event) => {
              event.preventDefault();
              void onAct('add-fixture', () =>
                api.addImportSource(importId, {
                  kind: 'synthetic_fixture',
                  fixtureName: fixture,
                }),
              );
            }}
          >
            <h4 className="hi-group-title">{IMPORT_COPY.actionAddFixture}</h4>
            <label className="hi-field">
              <span className="hi-field-label">Which example source</span>
              <select
                className="hi-input"
                value={fixture}
                onChange={(event) => setFixture(event.target.value)}
              >
                {data.available_fixtures.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="submit"
              className="btn btn-secondary"
              disabled={busy !== null || !fixture}
            >
              {IMPORT_COPY.actionAddFixture}
            </button>
          </form>
        )}
      </div>
    </div>
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
        <span className="hi-filename">{source.filename}</span>
        {source.sha256 !== null && (
          <span className="hi-sub">checksum recorded · not verified</span>
        )}
      </td>
      <td>{SOURCE_KIND_LABELS[source.kind] ?? source.kind}</td>
      <td>
        <span className="hi-reference">{source.reference}</span>
      </td>
      <td>
        <span className={`hi-parse hi-parse-${source.parse_state}`}>{state}</span>
        {/* THE REASON, PER ENTRY. This is the whole answer to "what parsed and
            what did not" and it is deliberately here rather than in a banner:
            an example source IS read and a reference is not, so one sentence covering
            both would be false for half the manifest. */}
        {source.parse_detail !== null && (
          <span className="hi-sub">{source.parse_detail}</span>
        )}
      </td>
      <td>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy !== null}
          onClick={onRemove}
          aria-label={`${IMPORT_COPY.actionRemoveSource} ${source.filename}`}
        >
          {IMPORT_COPY.actionRemoveSource}
        </button>
      </td>
    </tr>
  );
}

/* --------------------------------------------------------------------------
 * Parse.
 * -------------------------------------------------------------------------- */

function ParseSection({
  data,
  busy,
  onAct,
  importId,
}: {
  data: ApiImportSession;
  busy: string | null;
  onAct: ActFn;
  importId: string;
}) {
  const counts = data.source_counts;
  return (
    <div className="hi-section">
      {/* WAS `Read the Sources` — the exact label of `IMPORT_COPY.actionParse`,
          the primary button six lines below. Third instance of the duplicated-verb
          defect; the section is now titled by what it reports and the button keeps
          the verb. */}
      <h3 className="hi-section-title">What Was Read</h3>
      <p className="hi-body">{IMPORT_COPY.parseLead}</p>
      <p className="hi-counts">
        {counts.total} source{counts.total === 1 ? '' : 's'} · {counts.parsed} read ·{' '}
        {counts.no_content_path} held as a pointer · {counts.failed} could not be read ·{' '}
        {counts.parsable_by_this_build} readable by this build
      </p>
      <button
        type="button"
        className="btn btn-primary"
        disabled={busy !== null || counts.parsable_by_this_build === 0}
        onClick={() => onAct('parse', () => api.parseImport(importId))}
      >
        {busy === 'parse' ? 'Reading…' : IMPORT_COPY.actionParse}
      </button>
      {/* THE CONTROL IS DISABLED ONLY WHEN THERE IS GENUINELY NOTHING TO READ,
          and the sentence beside it says which — never a bare disabled button,
          which leaves a reader guessing whether the feature is broken. */}
      {counts.parsable_by_this_build === 0 && (
        <p className="hi-note">
          Nothing in this bundle can be read by this build yet. Add an example source, or
          keep the references — they are stored either way.
        </p>
      )}

      {data.parsed.map((parsed) => (
        <div key={parsed.source_id} className="hi-parsed">
          <h4 className="hi-group-title">{parsed.filename}</h4>
          <p className="hi-sub">
            {parsed.statements.length} statement
            {parsed.statements.length === 1 ? '' : 's'} read ·{' '}
            {parsed.skipped.length} line{parsed.skipped.length === 1 ? '' : 's'} not
            understood
          </p>
          {parsed.statements.length > 0 && (
            <ul className="hi-statements">
              {parsed.statements.map((statement, index) => (
                <li key={`${statement.key}-${index}`}>
                  <code className="hi-key">{statement.key}</code>
                  <span className="hi-value">{statement.value}</span>
                  <span className="hi-locator">{statement.locator}</span>
                </li>
              ))}
            </ul>
          )}
          {/* WHAT IT PASSED OVER, LISTED. The other half of the report, and the
              half that stops this being `Mysterious JSON`. */}
          {parsed.skipped.length > 0 && (
            <ul className="hi-skipped">
              {parsed.skipped.map((entry, index) => (
                <li key={index}>
                  <span className="hi-locator">{String(entry.locator ?? '')}</span>
                  <span>{String(entry.message ?? entry.reason ?? '')}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

/* --------------------------------------------------------------------------
 * Candidates, and sending one to review.
 * -------------------------------------------------------------------------- */

function CandidatesSection({
  data,
  busy,
  onAct,
  importId,
}: {
  data: ApiImportSession;
  busy: string | null;
  onAct: ActFn;
  importId: string;
}) {
  const reconstruction = data.reconstruction;
  const candidates = reconstruction?.candidates ?? [];
  const structural = candidates.filter((c) => c.kind !== 'field');
  const disagreeing = candidates.filter((c) => c.kind === 'field' && c.unresolved_reason);
  const blocked = candidates.filter(
    (c) => c.kind === 'field' && !c.unresolved_reason && !c.proposable,
  );
  const sendable = candidates.filter((c) => c.proposable);

  return (
    <div className="hi-section">
      {/* WAS `Reconstruct Candidates` — the exact label of
          `IMPORT_COPY.actionReconstruct` below it. Fourth and last instance.

          `Candidates` is the subject. Note that
          `e2e/mutation/imports-session-a11y.spec.ts:99-106` records that waiting
          on `heading /Candidates/i` matches a heading present BEFORE
          reconstruction; that warning is unchanged and still correct — this
          heading, like the old one, renders from first paint. */}
      <h3 className="hi-section-title">Candidates</h3>
      <p className="hi-body">{IMPORT_COPY.reconstructLead}</p>
      <p className="hi-note">{IMPORT_COPY.profileNote}</p>
      <button
        type="button"
        className="btn btn-primary"
        disabled={busy !== null || data.parsed.length === 0}
        onClick={() => onAct('reconstruct', () => api.reconstructImport(importId))}
      >
        {busy === 'reconstruct' ? 'Reconstructing…' : IMPORT_COPY.actionReconstruct}
      </button>

      {/* THE SAME RULE THE PARSE CONTROL ALREADY OBEYS, APPLIED HERE — it was
          the one disabled primary button on this screen with no reason beside
          it, so a reader met a dead control and had to guess whether the
          feature was broken, unavailable or simply not ready yet.

          IT NAMES THE PRECONDITION AND THE NEXT ACT, not the internal state:
          the button is gated on `data.parsed.length === 0`, and what a reader
          can DO about that is read a source. Saying "no parsed sources" would
          restate the predicate back at them.

          AND IT SAYS WHAT RECONSTRUCTION IS, because this is the one place the
          distinction bites: it is deterministic, in this build. No model is
          called, so a reader waiting for "the AI" to become available is
          waiting for something that is not the blocker. `§15` forbids implying
          a capability exists; it equally forbids implying one is missing when
          the real precondition is one click away. */}
      {data.parsed.length === 0 && (
        <p className="hi-note">
          Nothing has been read yet, so there is nothing to reconstruct from. Read a source
          above first. Reconstruction is deterministic in this build — it reads the
          statements already parsed and calls no model.
        </p>
      )}

      {reconstruction === null ? (
        <p className="hi-body hi-empty-inline">{IMPORT_COPY.emptyCandidatesBody}</p>
      ) : (
        <>
          <p className="hi-counts">
            {candidates.length} candidate{candidates.length === 1 ? '' : 's'} ·{' '}
            {sendable.length} can be sent to review · {disagreeing.length} where sources
            disagree · {blocked.length} with nowhere to write · {structural.length}{' '}
            structural
          </p>
          {/* THE PROVIDER, NAMED, and its `applied` constant rendered from the
              response rather than asserted here. */}
          <p className="hi-sub">
            Reconstructed by {reconstruction.provider_id} ·{' '}
            {reconstruction.applied ? 'applied' : 'nothing was applied'}
          </p>

          {sendable.length > 0 && (
            <section className="hi-group">
              <h4 className="hi-group-title">Ready for your review</h4>
              <p className="hi-body">{IMPORT_COPY.reviewLead}</p>
              {sendable.map((candidate) => (
                <CandidateCard
                  key={candidate.candidate_id}
                  candidate={candidate}
                  session={data}
                  busy={busy}
                  onAct={onAct}
                  importId={importId}
                />
              ))}
            </section>
          )}

          {disagreeing.length > 0 && (
            <section className="hi-group">
              <h4 className="hi-group-title">Sources disagree</h4>
              <p className="hi-body">{IMPORT_COPY.disagreementNote}</p>
              {disagreeing.map((candidate) => (
                <CandidateCard
                  key={candidate.candidate_id}
                  candidate={candidate}
                  session={data}
                  busy={busy}
                  onAct={onAct}
                  importId={importId}
                />
              ))}
            </section>
          )}

          {blocked.length > 0 && (
            <section className="hi-group">
              <h4 className="hi-group-title">Read, with nowhere to write</h4>
              {blocked.map((candidate) => (
                <CandidateCard
                  key={candidate.candidate_id}
                  candidate={candidate}
                  session={data}
                  busy={busy}
                  onAct={onAct}
                  importId={importId}
                />
              ))}
            </section>
          )}

          {structural.length > 0 && (
            <section className="hi-group">
              <h4 className="hi-group-title">What this looks like</h4>
              {structural.map((candidate) => (
                <CandidateCard
                  key={candidate.candidate_id}
                  candidate={candidate}
                  session={data}
                  busy={busy}
                  onAct={onAct}
                  importId={importId}
                />
              ))}
            </section>
          )}

          {data.unmapped_keys.length > 0 && (
            <section className="hi-group">
              <h4 className="hi-group-title">Read, but not recognised</h4>
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
            </section>
          )}
        </>
      )}
    </div>
  );
}

/**
 * THE RECORDS THIS IMPORT CAN BE SENT TO, and a way to make a new one.
 *
 * ── WHAT WAS WRONG ─────────────────────────────────────────────────────────
 *
 * Sending a candidate to an experiment has always worked — `POST
 * /api/imports/{id}/candidates/{cid}/propose` — but the form asked for it by
 * typing the record's **ULID** into a free-text box ("the record's id"). Nobody
 * knows a ULID, so a path that existed was effectively invisible. The project
 * owner read the screen as having no way to land an import at all: *"there
 * should also be an intuitive way for users to add it into a current experiment
 * or make a new experiment from it because at the end of the day the import is
 * so that users can upload files and stuff from their previous experiment and
 * it can be mapped to the isaac schema"*.
 *
 * ── WHAT THIS DOES, AND WHAT IT REFUSES TO DO ──────────────────────────────
 *
 * It lists the workspace's experiments so one can be CHOSEN, and it can create a
 * new one named after the import. It does NOT map anything by itself: a chosen
 * candidate still becomes an ingestion PROPOSAL on that record, reviewed there,
 * exactly as before. Creating a record here writes a title and nothing else —
 * no field is inferred from the import, which is the same no-guessing rule the
 * rest of this screen follows.
 *
 * A failed list is reported, not swallowed: an empty picker with no explanation
 * would read as "you have no experiments", which is a different claim.
 */
function useProposalDestinations() {
  const [rows, setRows] = useState<{ id: string; title: string }[] | null>(null);
  const [failed, setFailed] = useState(false);

  const reload = useCallback(async () => {
    try {
      const list = await api.listExperiments();
      setRows(
        (list.experiments ?? []).map((e) => ({
          id: e.id,
          title: stripLifecycleSuffix(e.title) || e.id,
        })),
      );
      setFailed(false);
    } catch {
      setRows(null);
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { rows, failed, reload };
}

function CandidateCard({
  candidate,
  session,
  busy,
  onAct,
  importId,
}: {
  candidate: ApiImportCandidate;
  session: ApiImportSession;
  busy: string | null;
  onAct: ActFn;
  importId: string;
}) {
  const [experimentId, setExperimentId] = useState('');
  const [runId, setRunId] = useState('');
  const destinations = useProposalDestinations();
  const already = session.proposed[candidate.candidate_id];
  const filenameOf = (sourceId: string) =>
    session.sources.find((s) => s.source_id === sourceId)?.filename ?? sourceId;

  return (
    <article className="hi-candidate">
      <header className="hi-candidate-head">
        <span className="hi-candidate-target">
          {candidate.target_field_path ?? `A candidate ${candidate.kind}`}
        </span>
        {/* WHAT WAS READ VERSUS WHAT WAS INFERRED — one of the nine things
            `HIST-004` requires a scientist to be able to see, and the badge is
            derived from the server's own `determinism` rather than guessed from
            the shape of the rule. */}
        <span className={`hi-determinism hi-determinism-${candidate.determinism}`}>
          {DETERMINISM_LABELS[candidate.determinism] ?? candidate.determinism}
        </span>
      </header>

      {candidate.proposed_value !== null && candidate.proposed_value !== undefined ? (
        <p className="hi-candidate-value">{String(candidate.proposed_value)}</p>
      ) : (
        <p className="hi-candidate-value hi-candidate-none">No value was chosen</p>
      )}

      {/* THE WARRANT, VERBATIM. The reconstruction's own sentence, never a
          paraphrase — it names the key and the line the value was read from, or
          the stored rule that inferred it, and both are what a reviewer needs. */}
      <p className="hi-rule">{candidate.rule}</p>

      {/* WHICH SOURCES SUPPORT IT. Named by FILENAME, because a source id means
          nothing to a scientist. */}
      {candidate.supporting_statements.length > 0 && (
        <ul className="hi-support">
          {candidate.supporting_statements.map((statement, index) => (
            <li key={index}>
              <span className="hi-filename">{filenameOf(statement.source_id)}</span>
              <span className="hi-locator">{statement.locator}</span>
              <code className="hi-key">{statement.key}</code>
              <span className="hi-value">{statement.value}</span>
            </li>
          ))}
        </ul>
      )}

      {/* WHERE SOURCES DISAGREE — every competing value, with who says it. */}
      {candidate.disagreement.length > 0 && (
        <ul className="hi-disagreement">
          {candidate.disagreement.map((row, index) => (
            <li key={index}>
              <span className="hi-value">{row.value}</span>
              <span className="hi-sub">
                from {row.source_ids.map(filenameOf).join(', ')} ·{' '}
                {row.locators.join(', ')}
              </span>
            </li>
          ))}
        </ul>
      )}

      {already !== undefined ? (
        <p className="hi-sent" role="note">
          {IMPORT_COPY.proposedNote}{' '}
          <Link to={ROUTES.recordProposal(already.experiment_id, already.proposal_id)}>
            Open it on that record
          </Link>
        </p>
      ) : candidate.proposable ? (
        <form
          className="hi-send"
          onSubmit={(event) => {
            event.preventDefault();
            void onAct(`propose:${candidate.candidate_id}`, async () => {
              const detail = await api.getExperiment(experimentId);
              await api.proposeImportCandidate(importId, candidate.candidate_id, {
                experimentId,
                // THE RECORD'S OWN VERSION, read immediately before the write.
                // An import session serves none, and sending a blank would be a
                // 428 reported as a server disagreement.
                experimentVersion: detail.version,
                ...(runId.trim() ? { runId: runId.trim() } : {}),
              });
              setRunId('');
            });
          }}
        >
          {/*
            A PICKER, NOT A TYPED ULID. See `useProposalDestinations` for why:
            this field used to ask a scientist to type "the record's id".
          */}
          <label className="hi-field">
            <span className="hi-field-label">Send it to which record?</span>
            {destinations.failed ? (
              /*
                A LIST THAT COULD NOT BE READ FALLS BACK TO THE FIELD, rather
                than removing the only way to send. A scientist who has the id —
                from a URL, from a colleague — can still act, and the note says
                why they are being asked for one. Removing the control here would
                turn a failed READ into a blocked WRITE, which is a bigger claim
                than the failure supports.
              */
              <>
                <input
                  className="hi-input"
                  type="text"
                  required
                  value={experimentId}
                  onChange={(event) => setExperimentId(event.target.value)}
                  placeholder="the record's id"
                />
                <span className="hi-note">
                  The list of records could not be read, so this asks for the id instead.
                </span>
              </>
            ) : destinations.rows === null ? (
              <span className="hi-note">Reading your records…</span>
            ) : destinations.rows.length === 0 ? (
              <span className="hi-note">
                This workspace holds no records yet. Create one below and it becomes the
                destination.
              </span>
            ) : (
              <select
                className="hi-input"
                required
                value={experimentId}
                onChange={(event) => setExperimentId(event.target.value)}
              >
                <option value="">Choose a record…</option>
                {destinations.rows.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.title}
                  </option>
                ))}
              </select>
            )}
          </label>
          {/*
            …or make the destination. The title is the import's own label, so the
            new record is recognisable; NOTHING else is carried over, because
            nothing in the import has been reviewed yet.
          */}
          <button
            type="button"
            className="btn btn-ghost hi-new-destination"
            disabled={busy !== null}
            onClick={() => {
              void onAct(`create:${candidate.candidate_id}`, async () => {
                const created = await api.createExperiment({
                  title: session.label || 'Imported experiment',
                });
                await destinations.reload();
                setExperimentId(created.id);
              });
            }}
          >
            {busy === `create:${candidate.candidate_id}`
              ? 'Creating…'
              : 'New record from this import'}
          </button>
          <label className="hi-field">
            <span className="hi-field-label">
              Which run? (required for a value a run owns)
            </span>
            <input
              className="hi-input"
              type="text"
              value={runId}
              onChange={(event) => setRunId(event.target.value)}
              placeholder="leave blank for a value the record owns"
            />
          </label>
          <button
            type="submit"
            className="btn btn-secondary"
            disabled={busy !== null || !experimentId.trim()}
          >
            {busy === `propose:${candidate.candidate_id}`
              ? 'Sending…'
              : IMPORT_COPY.actionPropose}
          </button>
        </form>
      ) : (
        /* WHY IT CANNOT BE SENT, IN THE SERVER'S OWN WORDS, and with no control
           at all rather than a disabled one. The server's sentence is preferred
           to anything composed here because it is the one that will actually be
           enforced — and for the no-write-path case it carries the clause that
           the limitation is THIS BUILD's and not a statement about the official
           ISAAC schema. */
        <p className="hi-blocked" role="note">
          <CircleAlert size={14} strokeWidth={2.1} aria-hidden="true" />
          {candidate.not_proposable_reason ?? IMPORT_COPY.notProposableFallback}
        </p>
      )}
    </article>
  );
}

/* --------------------------------------------------------------------------
 * Refusals.
 * -------------------------------------------------------------------------- */

/**
 * A refusal, rendered with the SERVER's own reason where there is one.
 *
 * `BackendDown` is used only for a server that did not answer. A typed refusal —
 * a malformed checksum, a fixture that is not on the allowlist, a candidate whose
 * sources disagree — is the server answering CORRECTLY, and reporting it as
 * "Backend Not Running" is the defect `LoadMaterials` records for its own 409s.
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
