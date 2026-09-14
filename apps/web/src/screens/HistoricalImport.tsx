import './screens.css';
import './historical-import.css';
import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { BackendDown, LoadingPanel } from '../components/FetchStates';
import { CircleAlert, Inbox, Plus, TriangleAlert } from '../components/icons';
import { LABELS } from '../lib/labels';
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
 * * **No upload.** There is no `<input type="file">` on this screen and no drop
 *   handler. That is not a promise — `__tests__/upload-claim-parity.test.tsx`
 *   asserts that EXACTLY two non-test files in `apps/web/src` declare a file
 *   input and names both, so adding a third fails CI. A source is either a
 *   POINTER (recorded, not opened) or one of the committed example sources.
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
        SECTION ONE — the sequence, titled by its SUBJECT.

        `How An Import Works` is a new heading and it is the reason this block
        stops being an unlabelled strip floating above the page: it had no title
        at all, so the six stage chips and the durability sentence were two
        unrelated fragments a reader had to interpret unaided.

        Register 1 Title Case, per `casing-and-copy.md:8-12` ("section titles").
      */}
      <div className="hi-section">
        <h2 className="hi-section-title">How An Import Works</h2>
        <WorkflowStrip steps={data.workflow} furthest={null} />
        {/* THE SERVER'S OWN SENTENCE about what a session is and is not. Rendered
            before anything is created, because a reader deciding whether to start
            one is exactly who needs it.

            MOVED, NOT CHANGED: it used to be the last child of an untitled block
            and is now the last child of `How An Import Works`. Same string, same
            `role="note"`, same server source — the claim that an import session is
            not part of the durable record store is unaltered, and it now sits
            under a heading that says what it is a note ABOUT. */}
        <p className="hi-note" role="note">
          {data.durability}
        </p>
      </div>

      {/*
        SECTION TWO — and the heading no longer repeats its own button.

        MEASURED BEFORE: `IMPORT_COPY.actionStart` ("Start an Import") rendered
        TWICE, 78px apart — once as this section's `<h2>` and once as the label of
        the primary button inside it. A section title that repeats its own primary
        action's verb tells the reader nothing the button did not already say, and
        it makes the same string an ambiguous target for anything (a test, a
        screen reader user cycling headings, a person) looking for "the control".

        THE RULE APPLIED HERE AND THREE MORE TIMES BELOW: a section is titled by
        its SUBJECT and the button keeps the verb. So `New Import` names the thing;
        `Start an Import` remains the only place that verb appears.
      */}
      <div className="hi-section">
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
        SECTION THREE — `Imports`.

        THE HEADING STRING IS LOAD-BEARING AND MUST NOT BE "IMPROVED".
        `e2e/surfaces.ts:141` declares this surface's ready gate as
        `{ role: 'heading', name: 'Imports' }` and
        `e2e/mutation/imports-session-a11y.spec.ts:64` asserts it at `level: 2` —
        both because it is inside the `status === 'data'` branch and so cannot
        render over a skeleton. Renaming it, or changing its level, silently turns
        thirteen sweeps into measurements of a loading state.
      */}
      <div className="hi-section">
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
  return (
    <ol className="hi-steps" aria-label="Historical import workflow">
      {steps.map((step) => {
        const reached = furthest !== null && step.id === furthest;
        return (
          <li
            key={step.id}
            className={`hi-step${reached ? ' reached' : ''}${step.built ? '' : ' unbuilt'}`}
            aria-current={reached ? 'step' : undefined}
          >
            <span className="hi-step-label">{step.label}</span>
            {/* THE UNBUILT STEP SAYS SO, in the server's own words, and offers no
                control — not a disabled one. A disabled button implies the act
                exists and is temporarily unavailable, which would be the claim
                §15 forbids. */}
            {!step.built && step.disclosure !== null && (
              <span className="hi-step-note">{step.disclosure}</span>
            )}
          </li>
        );
      })}
    </ol>
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
      <p className="hi-body">{IMPORT_COPY.sourcesLead}</p>
      <p className="hi-body">{IMPORT_COPY.fixturesLead}</p>
      <p className="hi-note">{IMPORT_COPY.formatsNote}</p>

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
          <label className="hi-field">
            <span className="hi-field-label">Send it to which record?</span>
            <input
              className="hi-input"
              type="text"
              required
              value={experimentId}
              onChange={(event) => setExperimentId(event.target.value)}
              placeholder="the record's id"
            />
          </label>
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
