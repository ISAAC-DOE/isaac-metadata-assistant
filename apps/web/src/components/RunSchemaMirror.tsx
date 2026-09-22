import { useEffect, useId, useState } from 'react';

import { api } from '../lib/api';
import { RUN_FIELDS } from '../lib/runFields';
import {
  RECORD_MAP_STATE_LABEL,
  blockRows,
  runFieldRows,
  type RecordMapCheck,
  type RecordMapRow,
  type RecordMapState,
} from '../lib/recordMap';
import { Check, CircleAlert, CircleDashed, CornerDownRight, EyeOff } from './icons';
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
}

function blockFields(node: SchemaNode | undefined): { name: string; required: boolean }[] {
  const props = node?.properties ?? {};
  const required = new Set(node?.required ?? []);
  return Object.keys(props).map((name) => ({ name, required: required.has(name) }));
}

/*
 * A SHAPE PER STATE, BESIDE THE WORD — never the colour on its own.
 *
 * `CornerDownRight` for `inherited` is this app's existing inheritance idiom
 * (`icons.tsx` already maps it to `inferred`/`evCandidate`); `EyeOff` for
 * `notShown` is the same glyph the evidence chips use for "could not be read",
 * which is precisely what that state means here. None of the five is a verdict
 * mark: `Check` says a value is present, not that it is right.
 */
const STATE_ICON: Record<RecordMapState, typeof Check> = {
  filled: Check,
  inherited: CornerDownRight,
  needsReview: CircleAlert,
  missing: CircleDashed,
  notShown: EyeOff,
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
  const Icon = STATE_ICON[state];
  return (
    <span className={`rm-state rm-state-${state}`}>
      <Icon size={13} strokeWidth={2.2} aria-hidden="true" />
      {RECORD_MAP_STATE_LABEL[state]}
    </span>
  );
}

/**
 * One row.
 *
 * A row is a `<button>` ONLY when `onOpen` is supplied, which the caller does
 * only for the five paths the run editor renders an input for. Everything else
 * is a plain `<div>`: not focusable, no pointer cursor, no hover lift. A row
 * that looks pressable and is not is the defect this split exists to avoid.
 */
function Row({ row, onOpen }: { row: RecordMapRow; onOpen?: () => void }) {
  const body = (
    <>
      <span className="rm-row-head">
        <span className="rm-row-label">{row.label}</span>
        <StateBadge state={row.state} />
      </span>
      {/* THE PATH IS NEVER REMOVED, only demoted — `UX-014`'s rule, and it is
          how a curator maps a field to the official document. */}
      <code className="mono rm-row-path">{row.path}</code>
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
  if (onOpen === undefined) {
    return (
      <li className="rm-row" data-state={row.state}>
        <div className="rm-row-inner">{body}</div>
      </li>
    );
  }
  return (
    <li className="rm-row rm-row-actionable" data-state={row.state}>
      <button
        type="button"
        className="rm-row-inner rm-row-button"
        /* The accessible name states the ACT, ahead of the visible text it
           then repeats — the same convention the compact run row uses. */
        aria-label={`Edit ${row.label}`}
        onClick={onOpen}
      >
        {body}
      </button>
    </li>
  );
}

export function RunSchemaMirror({
  run,
  check,
}: {
  run: ApiRunView | null;
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
        <h3 className="rsm-heading" id={`${uid}-heading`}>
          Record Map
        </h3>
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
        <h3 className="rsm-heading" id={`${uid}-heading`}>
          Record Map
        </h3>
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
        {/* WHICH RUN THIS DESCRIBES, stated rather than assumed. The pane reads
            one run; leaving it unnamed beside a list of several was how a reader
            could take it for the record's own state. */}
        <p className="rsm-subject">
          {run === null ? 'No run loaded yet' : run.label}
        </p>
      </div>
      <p className="rsm-note">
        Read live from the vendored ISAAC v1.05 schema — the same document{' '}
        <code className="mono">isaac validate --official</code> checks against. This pane
        reports what the run carries; it runs no validation of its own.
      </p>

      {attention.length > 0 && (
        <section className="rsm-group" aria-labelledby={`${uid}-attention`}>
          <p className="rsm-group-title eyebrow" id={`${uid}-attention`}>
            {LABELS.recordMapNeedsAttention} · {attention.length}
          </p>
          <ul className="rm-rows">
            {attention.map((row) => (
              <Row key={row.path} row={row} onOpen={editable(row)} />
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
            <Row key={row.path} row={row} onOpen={editable(row)} />
          ))}
        </ul>
      </section>

      <section className="rsm-group" aria-labelledby={`${uid}-inherited`}>
        <p className="rsm-group-title eyebrow" id={`${uid}-inherited`}>
          {LABELS.recordMapInherited}
        </p>
        <ul className="rm-rows">
          {recordBlocks.map((row) => (
            <Row key={row.path} row={row} />
          ))}
        </ul>
      </section>

      {/*
        THE EXHAUSTIVE STRUCTURE, AND THE DISCLOSURE, BEHIND ONE DISCLOSURE
        CONTROL.

        Neither is deleted and neither is softened. What changed is that the
        block-by-block leaf listing — which is reference material a reader
        consults, not state they scan — no longer sits between them and the
        state above, and the draft-grouping paragraph no longer opens as nine
        lines of grey prose under a wall of identical cards.

        A native `<details>`: no JS, keyboard-operable by default, and its
        contents are reachable by `querySelectorAll` (and therefore by every
        guard in this repository that reads the DOM) whether it is open or shut.
      */}
      <details className="rsm-more">
        <summary className="rsm-more-summary">Show full official schema</summary>
        <div className="rsm-more-body">
          <p className="rsm-note">
            Every block the official schema declares, with its own field names. A field
            marked <code className="mono">*</code> is required by the schema.
          </p>
          {[
            { title: 'Filled per run', blocks: RUN_BLOCKS, rows: runBlocks },
            { title: 'Shared by the record', blocks: RECORD_BLOCKS, rows: recordBlocks },
          ].map(({ title, rows }) => (
            <div className="rsm-group" key={title}>
              <p className="rsm-group-title eyebrow">{title}</p>
              <ul className="rsm-blocks">
                {rows.map((row) => {
                  const fields = blockFields(schema.properties?.[row.path]);
                  return (
                    <li className="rsm-block" key={row.path} data-state={row.state}>
                      <div className="rsm-block-head">
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
        </div>
      </details>
    </aside>
  );
}
