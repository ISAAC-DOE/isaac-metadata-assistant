import { useEffect, useId, useState, type ReactNode } from 'react';

import { api } from '../lib/api';
import { RUN_FIELDS } from '../lib/runFields';
import {
  RECORD_MAP_STATE_LABEL,
  blockRows,
  recordMapBlockLabel,
  runFieldRows,
  type RecordMapCheck,
  type RecordMapRow,
  type RecordMapState,
} from '../lib/recordMap';
import { Disclosure } from './Disclosure';
import { HelpTip } from './HelpTip';
import { SemanticStatus, type SemanticState } from './SemanticStatus';
import { LABELS } from '../lib/labels';
import type { ApiRunCheckResponse, ApiRunView } from '../lib/types';
import './run-schema-mirror.css';

/**
 * THE RECORD MAP — what this run holds, what it does not, and what this build
 * cannot see, beside the editor that fills it in.
 *
 * ── WHY IT EXISTS ───────────────────────────────────────────────────────────
 *
 * The project owner, 2026-09-14: *"im assuming you would want to ingest the
 * isaac actual schema structure no? … the whole idea is that these populate into
 * the schema right so there should be an intuitive way users can both add runs
 * and then see the schema being filled at the same time, maybe like a split
 * screen type of thing"*, and then, explicitly: *"build a provisional one and
 * revise later, i want the view there so i can show angel and hao the vision"*.
 *
 * ── WHY IT WAS REBUILT, 2026-09-15 ─────────────────────────────────────────
 *
 * The first version was ten near-identical grey cards, each a block name over a
 * dot-separated run of raw schema leaf names, under a nine-line paragraph. The
 * owner, looking at it: *"I can't clearly distinguish what fields are done, what
 * fields aren't done, what my values were for those fields … the official record
 * structure on the right also, it needs to be changed, because genuinely, it's
 * unreadable."*
 *
 * Three things changed and nothing was deleted:
 *
 *   1. THE ROWS ARE FIELDS, NOT ONLY BLOCKS, for the five paths this payload can
 *      actually speak to — with the RUN'S OWN VALUE on the row. That is the
 *      "what my values were" half, and it was previously absent entirely.
 *   2. THE DEFAULT VIEW IS WHAT IS RELEVANT. Needs Attention, then this run's
 *      own fields, then what it inherits. The exhaustive block-by-block schema
 *      dump is unchanged and now sits behind a `<details>`.
 *   3. THE DISCLOSURE MOVED, NOT ONE WORD OF IT WENT. The draft-grouping
 *      paragraph is a scientific-honesty statement — the provisional run/record
 *      split, "nothing here gates export", "official validation decides that" —
 *      so its PLACEMENT is the only thing this slice was free to change.
 *
 * ── WHAT IS REAL HERE, AND WHAT IS PROVISIONAL ─────────────────────────────
 *
 * REAL: the structure. Every block and field name comes from `GET /api/schema`,
 * which serves the vendored `schema/isaac_record_v1.json` — the same document
 * `isaac validate --official` checks against. Nothing on this pane is a
 * hand-written field list, so a schema refresh moves it.
 *
 * REAL: the filled/empty state. A row reads as filled only when the run itself
 * carries it (`run.fields`) or inherits it from the record (`run.inherited`).
 * Nothing is inferred and no value is invented — an unfilled row says nothing
 * rather than showing a plausible default, which is §5.
 *
 * REAL, AND SCOPED: `Needs Review`. It is applied ONLY from the findings of a
 * Check Run the reader pressed, and ONLY while `checked_run_version` still
 * matches the run's own `version`. A check read at an older version is dropped
 * whole rather than shown against a document that has since moved.
 *
 * PROVISIONAL, AND SAID ON THE PANE: which blocks belong to a RUN rather than to
 * the record. That is a scientific decision about what a run owns, and the
 * project owner is getting the template from Angel. The split below is a
 * reasonable reading of the schema — `measurement`, `timestamps` and
 * `descriptors` move per run; `sample`, `system` and `attribution` describe the
 * campaign — and it is labelled as a draft so nobody mistakes it for settled.
 * It is deliberately NOT used to gate anything: no export decision, no
 * completeness claim, no validation. It is a mirror.
 *
 * ── WHY IT CANNOT CLAIM COMPLETENESS ───────────────────────────────────────
 *
 * "Filled" here means a key is present with a value, not that the value is
 * valid — official validation is the only thing that decides that, and it runs
 * at export. So the pane says "Filled" and never "complete", "ready" or "valid".
 */

/** The run/record split. PROVISIONAL — see the header. */
const RUN_BLOCKS: readonly string[] = ['measurement', 'timestamps', 'descriptors', 'context'];
const RECORD_BLOCKS: readonly string[] = [
  'sample',
  'system',
  'attribution',
  'links',
  'assets',
  'tags',
];

interface SchemaNode {
  properties?: Record<string, SchemaNode>;
  required?: string[];
  description?: string;
  type?: string | string[];
  format?: string;
  enum?: unknown[];
}

/** The schema node at a dotted path, or `undefined`. */
function nodeAt(schema: SchemaNode, path: string): SchemaNode | undefined {
  let node: SchemaNode | undefined = schema;
  for (const part of path.split('.')) node = node?.properties?.[part];
  return node;
}

/** The first sentence of a schema description, or `null`. */
function firstSentence(text: string | undefined): string | null {
  if (typeof text !== 'string' || text.trim() === '') return null;
  const m = /^(.+?[.!?])(\s|$)/.exec(text.trim());
  return (m ? m[1] : text.trim()).trim();
}

/**
 * WHAT A ROW'S `?` SAYS — only what the vendored schema, `RUN_FIELDS` or this
 * pane's own reading rules support. Nothing here is a scientific definition
 * this client wrote: a type, a format, an enum, a unit already in the path's
 * name, or the schema's own description sentence.
 */
function fieldFacts(schema: SchemaNode, row: RecordMapRow): string[] {
  const node = nodeAt(schema, row.path);
  const facts: string[] = [];
  if (Array.isArray(node?.enum) && node!.enum!.length > 0) {
    facts.push(`One of the schema's values: ${node!.enum!.map(String).join(', ')}.`);
  } else if (node?.format === 'date-time') {
    facts.push('A date and time, stored in UTC.');
  } else if (row.unit !== undefined) {
    facts.push(`A number, stored in ${row.unit === 'K' ? 'kelvin' : row.unit}.`);
  } else if (node?.type === 'string') {
    facts.push('Free text — the schema defines no vocabulary for it.');
  }
  const described = firstSentence(node?.description);
  if (described !== null) facts.push(described);
  return facts;
}

/** Where a block this pane cannot see is actually entered — the honest pointer
 *  a `Not Shown Here` row owes its reader. */
function notShownReason(block: string): string {
  const where =
    block === 'measurement' || block === 'descriptors'
      ? 'Complete Metadata, where the spectrum, QC verdict and descriptors are answered'
      : 'Record Fields';
  return `The run list this map reads does not carry this block, so its state is not shown here rather than guessed. See ${where}.`;
}

function blockFields(node: SchemaNode | undefined): { name: string; required: boolean }[] {
  const props = node?.properties ?? {};
  const required = new Set(node?.required ?? []);
  return Object.keys(props).map((name) => ({ name, required: required.has(name) }));
}

/*
 * ONE STATE VOCABULARY (2026-09-22): each map state is drawn by the shared
 * `SemanticStatus` — icon + word + tint, never colour alone. `filled` keeps its
 * own word: a key being present is not a verdict that it is right, and official
 * validation is the only thing on this screen that issues one.
 */
const STATE_SEMANTIC: Record<RecordMapState, SemanticState> = {
  filled: 'complete',
  inherited: 'inherited',
  needsReview: 'needsReview',
  missing: 'missing',
  notShown: 'notShownHere',
};

/**
 * WHAT A CHECK CAN CONTRIBUTE, AND WHEN IT MAY NOT.
 *
 * A check is client-only state from an explicit action, and the run it was
 * taken on can move under it — an autosave a keystroke later advances
 * `run.version` while the response in hand still names the old one. Marking a
 * row `Needs Review` from that would be this pane reporting a read of a
 * document that no longer exists. So the comparison is exact and the failure is
 * total: a mismatched version contributes NOTHING rather than contributing
 * stale rows.
 */
function currentCheck(
  run: ApiRunView | null,
  check: ApiRunCheckResponse | null | undefined,
): RecordMapCheck | null {
  if (run === null || check === null || check === undefined) return null;
  if (check.checked_run_version !== run.version) return null;
  return {
    runVersion: check.checked_run_version,
    errors: [...(check.draft?.errors ?? []), ...(check.official?.errors ?? [])],
  };
}

function StateBadge({ state }: { state: RecordMapState }) {
  return (
    <SemanticStatus
      state={STATE_SEMANTIC[state]}
      label={RECORD_MAP_STATE_LABEL[state]}
      size="sm"
      className="rm-state"
    />
  );
}

/**
 * One row: the human label, its state and — where one is honestly held — the
 * run's own value. The official path and what the schema says about it are
 * behind the row's `?`, never removed (`UX-014`'s rule: it is how a curator maps
 * a field to the official document).
 *
 * THE ROW'S PRESSABLE PART is a `<button>` ONLY when `onOpen` is supplied, which
 * the caller does only for the five paths the run editor renders an input for.
 * The `?` sits BESIDE that button, never inside it: a button inside a button is
 * invalid and unreachable by keyboard.
 */
function Row({
  row,
  onOpen,
  facts,
}: {
  row: RecordMapRow;
  onOpen?: () => void;
  facts: string[];
}) {
  const labelId = useId();
  const body = (
    <>
      <span className="rm-row-head">
        <span className="rm-row-label" id={labelId}>
          {row.label}
        </span>
        <StateBadge state={row.state} />
      </span>
      {row.value !== null && (
        <span className="rm-row-value">
          {row.value}
          {row.unit !== undefined && <span className="rm-row-unit"> {row.unit}</span>}
        </span>
      )}
      {/* The validator's own sentence, verbatim — the reason this row says
          "Needs Review" rather than an adjective this pane chose. */}
      {row.reviewNote !== null && <span className="rm-row-note">{row.reviewNote}</span>}
    </>
  );
  const tip = (
    <HelpTip
      subject={row.label}
      label={row.path.includes('.') ? 'Official Field Details' : 'Official Block Details'}
      describedBy={labelId}
    >
      {/* Spans, drawn as blocks by the panel: the tip is a `<span>` so it is valid
          anywhere, and a `<p>` inside it would not be. */}
      <span>
        Official {row.path.includes('.') ? 'field' : 'block'}:{' '}
        <code className="mono rm-row-path">{row.path}</code>
      </span>
      {facts.map((fact) => (
        <span key={fact}>{fact}</span>
      ))}
      {row.state === 'notShown' && <span className="rm-row-reason">{notShownReason(row.path)}</span>}
    </HelpTip>
  );
  return (
    <li className={`rm-row${onOpen ? ' rm-row-actionable' : ''}`} data-state={row.state}>
      <div className="rm-row-inner">
        {onOpen === undefined ? (
          <div className="rm-row-main">{body}</div>
        ) : (
          <button
            type="button"
            className="rm-row-main rm-row-button"
            /* The accessible name states the ACT, ahead of the visible text it
               then repeats — the same convention the compact run row uses. */
            aria-label={`Edit ${row.label}`}
            onClick={onOpen}
          >
            {body}
          </button>
        )}
        {tip}
      </div>
    </li>
  );
}

export function RunSchemaMirror({
  run,
  check,
  headerControl,
}: {
  run: ApiRunView | null;
  /**
   * A control that REPLACES the run name in the card's own header — the run picker
   * on the Proposals and Files views (review #277, I-3: one run choice per view, and
   * it lives inside the card it drives, not as a detached page-level select).
   */
  headerControl?: ReactNode;
  /**
   * The last Check Run result for THIS run, or `null`/omitted when the reader
   * has not run one. Used for one thing only — marking a row `Needs Review` —
   * and dropped entirely when its `checked_run_version` is not the run's
   * current `version`. See {@link currentCheck}.
   */
  check?: ApiRunCheckResponse | null;
}) {
  const [schema, setSchema] = useState<SchemaNode | null>(null);
  const [failed, setFailed] = useState(false);
  /* `useId`, not fixed ids (2026-09-22): the map is now mounted beside the Runs
     editor AND beside the focused capture views, and a hidden-but-mounted
     workspace keeps both in the DOM at once — a duplicate `id` would let
     `aria-labelledby` resolve to the other pane's heading. */
  const uid = useId();

  /*
   * THE SCHEMA IS THE ONLY THING THIS PANE FETCHES, and the run arrives as a
   * prop.
   *
   * It used to read `GET /runs?limit=1` itself, which made the Runs workspace
   * read the runs list TWICE on first paint —
   * `runs-live-refresh-integration.test.tsx` pins that at once and failed with
   * "expected [ …(2) ] to have a length of 1 but got 2". `RunsSection` already
   * holds the page, so it reports its run upward instead: one read, two
   * consumers, and the mirror cannot disagree with the run card about the same
   * run.
   */
  useEffect(() => {
    let cancelled = false;
    void api
      .getSchema()
      .then((body) => {
        if (!cancelled) setSchema((body.schema ?? null) as SchemaNode | null);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (failed) {
    return (
      <aside className="rsm" aria-labelledby={`${uid}-heading`}>
        <div className="rsm-head">
          <h3 className="rsm-heading" id={`${uid}-heading`}>
            Record Map
          </h3>
          {headerControl}
        </div>
        <p className="rsm-note">
          The schema could not be read, so nothing is shown rather than a structure
          from memory.
        </p>
      </aside>
    );
  }

  if (schema === null) {
    return (
      <aside className="rsm" aria-labelledby={`${uid}-heading`}>
        <div className="rsm-head">
          <h3 className="rsm-heading" id={`${uid}-heading`}>
            Record Map
          </h3>
          {headerControl}
        </div>
        <p className="rsm-note">Reading the official schema…</p>
      </aside>
    );
  }

  const scoped = currentCheck(run, check);
  const fieldRows = runFieldRows(run, scoped);
  const runBlocks = blockRows(
    RUN_BLOCKS.filter((block) => schema.properties?.[block] !== undefined),
    run,
  );
  const recordBlocks = blockRows(
    RECORD_BLOCKS.filter((block) => schema.properties?.[block] !== undefined),
    run,
  );

  /*
   * NEEDS ATTENTION IS FIELD ROWS ONLY, and the omission is deliberate. A BLOCK
   * row carries no value and no finding — `blockRows` returns `reviewNote:
   * null` for every one of them — so promoting a `missing` block here would be
   * promoting a row that says nothing a reader can act on. The two blocks this
   * pane can see (`context`, `timestamps`) are exactly the ones its five field
   * rows already decompose.
   */
  const attention = fieldRows.filter((row) => row.state === 'needsReview');
  const focusField = (path: string) => {
    /*
     * BY DATA ATTRIBUTE, not by id, and the precedent is this section's own:
     * `RunsSection` already brings a linked address into view with
     * `document.querySelector('[data-address=…]')`. The run editor publishes
     * `data-run-field-path` on each of its five controls; a card that is not
     * rendering them (a compact row renders none) simply yields no match and
     * this does nothing, which is the honest outcome.
     */
    const el = document.querySelector<HTMLElement>(
      `[data-run-field-path="${CSS.escape(path)}"]`,
    );
    if (el === null) return;
    el.focus();
    if (typeof el.scrollIntoView === 'function') el.scrollIntoView({ block: 'center' });
  };
  const editable = (row: RecordMapRow) =>
    row.editable ? () => focusField(row.path) : undefined;

  return (
    <aside className="rsm" aria-labelledby={`${uid}-heading`}>
      <div className="rsm-head">
        <h3 className="rsm-heading" id={`${uid}-heading`}>
          Record Map
        </h3>
        {/* What this pane reads and what it does not do — reference material a
            reader consults once, so it is behind the heading's `?`. */}
        <HelpTip subject="the Record Map">
          <span className="rsm-note">
            Read live from the vendored ISAAC v1.05 schema — the same document the
            official validator checks against. This pane reports what the run carries;
            it runs no validation of its own.
          </span>
        </HelpTip>
        {/* WHICH RUN THIS DESCRIBES, stated rather than assumed. The pane reads
            one run; leaving it unnamed beside a list of several was how a reader
            could take it for the record's own state. */}
        {headerControl ?? (
          <p className="rsm-subject">{run === null ? 'No run loaded yet' : run.label}</p>
        )}
      </div>

      {attention.length > 0 && (
        <section className="rsm-group" aria-labelledby={`${uid}-attention`}>
          <p className="rsm-group-title eyebrow" id={`${uid}-attention`}>
            {LABELS.recordMapNeedsAttention} · {attention.length}
          </p>
          <ul className="rm-rows">
            {attention.map((row) => (
              <Row
                key={row.path}
                row={row}
                onOpen={editable(row)}
                facts={fieldFacts(schema, row)}
              />
            ))}
          </ul>
        </section>
      )}

      <section className="rsm-group" aria-labelledby={`${uid}-thisrun`}>
        <p className="rsm-group-title eyebrow" id={`${uid}-thisrun`}>
          {LABELS.recordMapThisRun} · {RUN_FIELDS.length} fields
        </p>
        <ul className="rm-rows">
          {fieldRows.map((row) => (
            <Row key={row.path} row={row} onOpen={editable(row)} facts={fieldFacts(schema, row)} />
          ))}
        </ul>
      </section>

      <section className="rsm-group" aria-labelledby={`${uid}-inherited`}>
        <p className="rsm-group-title eyebrow" id={`${uid}-inherited`}>
          {LABELS.recordMapInherited}
        </p>
        <ul className="rm-rows">
          {recordBlocks.map((row) => (
            <Row key={row.path} row={row} facts={fieldFacts(schema, row)} />
          ))}
        </ul>
      </section>

      {/*
        THE EXHAUSTIVE STRUCTURE, AND THE DISCLOSURE, BEHIND ONE DISCLOSURE
        CONTROL — now the shared whole-row `Disclosure` (owner QA F4) rather than
        an 11px triangle. Its body is `hidden`, not unmounted, so every guard in
        this repository that reads the DOM still reaches the text inside.

        This is the pane's TECHNICAL listing, so the schema's own block and field
        names are shown here beside the human name — it is the place a curator
        comes to map the two.
      */}
      <Disclosure summary="Show full official schema" className="rsm-more">
        <p className="rsm-note">
          Every block the official schema declares, with its own field names. A field
          marked <code className="mono">*</code> is required by the schema.
        </p>
        {[
          { title: 'Filled per run', rows: runBlocks },
          { title: 'Shared by the record', rows: recordBlocks },
        ].map(({ title, rows }) => (
          <div className="rsm-group" key={title}>
            <p className="rsm-group-title eyebrow">{title}</p>
            <ul className="rsm-blocks">
              {rows.map((row) => {
                const fields = blockFields(schema.properties?.[row.path]);
                return (
                  <li className="rsm-block" key={row.path} data-state={row.state}>
                    <div className="rsm-block-head">
                      <span className="rsm-block-name">{recordMapBlockLabel(row.path)}</span>
                      <code className="mono rsm-path">{row.path}</code>
                      <StateBadge state={row.state} />
                    </div>
                    {fields.length > 0 && (
                      <p className="rsm-fields">
                        {fields.map((f) => (f.required ? `${f.name}*` : f.name)).join(' · ')}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
        <p className="rsm-draft">
          <strong>Draft grouping.</strong> &ldquo;Not Shown Here&rdquo; means this pane
          cannot see that block from the run list it reads — the spectrum, QC verdict and
          descriptors are answered through Complete Metadata, and this view does not
          claim a state it did not check. The schema structure above is exact. Which
          blocks belong to a run rather than to the whole experiment is a scientific
          decision still to be confirmed, so this split is a starting point for that
          conversation — not a rule the product enforces. Nothing here gates export or
          claims a record is complete; official validation decides that.
        </p>
      </Disclosure>
    </aside>
  );
}
