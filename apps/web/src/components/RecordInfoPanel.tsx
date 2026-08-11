/*
 * RECORD INFO and RELATIONSHIPS — the two record-level surfaces the field
 * workbench never had a place for.
 *
 * BOTH ARE RECORD-LEVEL, AND THAT IS MEASURED RATHER THAN ASSUMED. Neither may
 * appear as a per-run control:
 *
 *   * `links` is classified at NEITHER level. `routes.py`'s
 *     `EXPERIMENT_OVERRIDABLE_ADDRESSES` names it in the fail-closed list of
 *     addresses "not overridable until somebody decides", beside `meta`,
 *     `pending`, `implicit` and `block_evidence`; `workspace.py`'s composition
 *     notes say links are "NOT inherited and NOT copied". `RUN_WRITABLE_FIELD_PATHS`
 *     is a closed set of five `context.*` / `timestamps.acquired_*` paths and
 *     contains nothing here.
 *   * `timestamps.created_utc` is on the same unclassified list
 *     (`docs/run-scope-decision-packet.md` §2 counts it among the seven), so it is
 *     not inherited either, and §3 settles what it is: a record-creation stamp.
 *   * the classification trio lives in the draft's `meta`, which
 *     `workspace.py` calls "the same for every run by construction".
 *
 * So these two sections are mounted ONCE, on the record screen, and `RunCard` /
 * `RunsSection` are not touched by this slice.
 *
 * EVERYTHING HERE IS READ-ONLY, AND THAT IS A FINDING RATHER THAN A CHOICE.
 * The workbench around it is read-only too (`FieldRow` renders values and
 * evidence; the only writes on this screen are run edits and an explicit answer
 * on the completion screen), so a read surface is consistent with its
 * neighbours. But for `links` specifically the reason is harder: NO API
 * OPERATION IN THIS BUILD WRITES A RECORD'S `links`. Measured, not inferred —
 * `routes._answers_to_apply_shape` forwards only `asset_sha256`, `series`,
 * `descriptor`, `descriptor_label` and `edge` and drops every other key;
 * `complete.apply_answers` / `apply_corrections` handle only those same kinds;
 * the run PATCH accepts five field paths; and the override route refuses
 * `links` by the comment quoted above. Adding or removing a link therefore needs
 * a backend route, and adding one is outside this slice — so the panel SAYS SO
 * rather than offering a control whose only outcome would be a refusal.
 *
 * NO STATE IS CARRIED BY COLOUR. Every state on both panels is a word first —
 * "Record stamp", "No target id", "Not a record id", "Not in this workspace" —
 * with a glyph beside it and no colour-only distinction; the type-scale and
 * italic treatments come from `fields.css`, which the rows reuse wholesale so
 * this surface inherits the existing responsive stacking at 640px instead of
 * inventing a second layout.
 *
 * THE LOOKUP TRAP THIS FILE REFUSES TO REPEAT. Every mapping from a state to
 * copy goes through `Map.get(...)` with an explicit fallback, never
 * `TABLE[key].label`. A direct index on an unmapped key renders
 * `undefined.label` and takes the screen down, and this repository has shipped
 * that twice.
 */

import './fields.css';
import './record-info.css';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ChevronDown,
  ChevronRight,
  CircleDashed,
  CircleHelp,
  CornerDownRight,
  ExternalLink,
  Lock,
  Network,
  TriangleAlert,
} from './icons';
import { api } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import { ROUTES } from '../lib/routes';
import {
  readLinks,
  recordInfoRows,
  resolveTarget,
  type LinkTerm,
  type LinkView,
  type RecordInfoRow,
  type RecordInfoSource,
} from '../lib/recordIdentity';
import type { ApiArtifactsResponse, ApiDraftGroup, ApiExperimentDetail } from '../lib/types';

/* ─────────────────────────── the section shell ────────────────────────────── */

/**
 * The same collapsible card `FieldGroup` uses, down to the class names, because
 * these sections sit in the same column as the draft blocks and a second visual
 * language there would read as a different kind of content.
 *
 * Collapsed by default, like every draft block on this screen: progressive
 * disclosure, and a scientist who never asks about record identity never pays a
 * screenful for it. The body is only MOUNTED when open, which is also what keeps
 * the link-target lookup from issuing a request nobody asked for.
 */
function Section({
  id,
  title,
  sublabel,
  summary,
  children,
}: {
  id: string;
  title: string;
  sublabel: string;
  summary: string;
  children: React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);
  const Chevron = expanded ? ChevronDown : ChevronRight;
  const bodyId = `${id}-body`;
  return (
    <section className="field-group" aria-label={`${title} (${sublabel})`}>
      <button
        type="button"
        className="fg-header"
        aria-expanded={expanded}
        aria-controls={expanded ? bodyId : undefined}
        onClick={() => setExpanded((open) => !open)}
      >
        <Chevron className="fg-chevron" size={16} strokeWidth={2} aria-hidden="true" />
        <span className="fg-block">{title}</span>
        {/* Not `.fg-sublabel` / `.fg-summary`: those two paint a colour that is
            already below the contrast threshold on this screen, and reusing them
            would have grown the measured `color-contrast` count by four. See the
            rule's own comment in `record-info.css`. */}
        <span className="record-section-key">{sublabel}</span>
        <span className="record-section-summary">{summary}</span>
      </button>
      {expanded && (
        <div className="fg-body" id={bodyId}>
          {children}
        </div>
      )}
    </section>
  );
}

/* ───────────────────────────── record info ────────────────────────────────── */

/**
 * The italic stand-in shown where there is no value, per state.
 *
 * Each one is a claim, and they are different claims on purpose: "not written
 * yet" is about the exporter, "not read on this screen" is about this client,
 * and "not carried by the exported record" is about a file that exists. Reading
 * goes through `.get`, with the fallback stating the honest thing — that this
 * build has no wording for the state it was handed.
 */
const ABSENT_TEXT = new Map<RecordInfoSource, string>([
  ['written_at_export', 'not written yet'],
  ['not_read_here', 'not read on this screen'],
  ['missing_from_record', 'not carried by the exported record'],
  ['no_single_value', 'no single value for this experiment'],
]);

const ABSENT_FALLBACK = 'not shown, and this build does not describe why';

function RecordInfoRowView({ row }: { row: RecordInfoRow }) {
  const absent = ABSENT_TEXT.get(row.source) ?? ABSENT_FALLBACK;
  return (
    <div className="field-row" data-record-info-path={row.path}>
      <div className="field-label-col">
        <div className="field-label">{row.label}</div>
        <div className="field-path">{row.path}</div>
      </div>
      <div className="field-value-col">
        <div className="field-value-row">
          {row.value === null ? (
            <span className="field-value awaiting">{absent}</span>
          ) : (
            <span className="field-value">{row.value}</span>
          )}
          {row.stamp && (
            <span className="record-info-tag">
              <Lock size={12} strokeWidth={2} aria-hidden="true" />
              Record stamp
            </span>
          )}
        </div>
        <p className="field-helper">{row.note}</p>
        {row.description !== '' && (
          <p className="field-helper record-info-schema">
            The official schema describes this as: “{row.description}”
          </p>
        )}
      </div>
    </div>
  );
}

export function RecordInfoPanel({
  detail,
  groups,
  artifacts,
}: {
  detail: ApiExperimentDetail;
  groups: readonly ApiDraftGroup[];
  artifacts: ApiArtifactsResponse;
}) {
  const rows = recordInfoRows({ detail, groups, artifacts });
  // A state phrase, not a score. A completion percentage here would be a number
  // about how much of a record exists, computed by a panel that can only see
  // part of it — see CLAUDE.md §5.
  const summary =
    artifacts.record !== null
      ? 'read from the exported record'
      : 'written when this record is exported';

  return (
    <Section
      id="record-info"
      title="Record Info"
      sublabel="record"
      summary={summary}
    >
      <p className="record-info-note">
        These values identify and classify the record itself. None of them is a measurement,
        and none of them is entered on this screen — each row says where its value comes
        from.
      </p>
      {rows.map((row) => (
        <RecordInfoRowView key={row.path} row={row} />
      ))}
    </Section>
  );
}

/* ─────────────────────────────── links ────────────────────────────────────── */

/** One enum member of a link — the stored token, and whether the schema knows it. */
function LinkTermView({ term, kind }: { term: LinkTerm; kind: 'relation' | 'basis' }) {
  if (term.token === null) {
    return (
      <span className="link-term missing">
        <CircleDashed size={12} strokeWidth={2} aria-hidden="true" />
        No {kind}. The official schema requires one.
      </span>
    );
  }
  return (
    <span className="link-term">
      <span className="link-term-text">{term.text}</span>
      <span className="link-term-token">{term.token}</span>
      {!term.known && (
        <span className="link-term-unknown">
          <CircleHelp size={12} strokeWidth={2} aria-hidden="true" />
          Not one of the {kind === 'relation' ? 'eight relations' : 'twelve bases'} the
          official schema lists.
        </span>
      )}
    </span>
  );
}

/**
 * What a well-formed target points at.
 *
 * Mounted per link and ONLY for a well-formed target, so a record with no links,
 * or with links this build cannot read, issues no request at all. It reads the
 * workspace's experiment list through the existing `GET /api/experiments` — no
 * route was added for it.
 *
 * The three outcomes are three different sentences on purpose. "Not in this
 * workspace" is not "missing" and is not "invalid": the list searched excludes
 * the per-run records a fan-out export writes, and excludes everything held
 * outside this workspace entirely, so the copy names the set that was searched
 * rather than making a claim about the target's existence.
 */
function TargetResolution({ id }: { id: string }) {
  const experiments = useFetch(() => api.listExperiments(), []);
  if (experiments.status === 'loading') {
    return (
      <p className="link-resolution">
        <CircleHelp size={12} strokeWidth={2} aria-hidden="true" />
        Looking this identifier up in the workspace…
      </p>
    );
  }
  const resolution = resolveTarget(
    id,
    experiments.status === 'data' ? experiments.data : null,
  );
  if (resolution.state === 'resolved') {
    return (
      <p className="link-resolution">
        <CornerDownRight size={12} strokeWidth={2} aria-hidden="true" />
        Points at{' '}
        <Link to={ROUTES.record(resolution.experimentId)} className="link-resolution-link">
          {resolution.title}
          <ExternalLink size={12} strokeWidth={2} aria-hidden="true" />
        </Link>{' '}
        in this workspace.
      </p>
    );
  }
  if (resolution.state === 'not_in_workspace') {
    return (
      <p className="link-resolution">
        <CircleHelp size={12} strokeWidth={2} aria-hidden="true" />
        Not in this workspace’s experiment list. That list does not include the records
        exported per run, and never includes a record held elsewhere — so this app cannot
        say whether the target exists, only that it did not find it here.
      </p>
    );
  }
  return (
    <p className="link-resolution">
      <CircleHelp size={12} strokeWidth={2} aria-hidden="true" />
      This app could not read the workspace’s experiment list, so it cannot say what this
      points at.
    </p>
  );
}

function LinkTargetView({ link }: { link: LinkView }) {
  if (link.target.state === 'absent') {
    return (
      <div className="link-target">
        <span className="link-target-state">
          <CircleDashed size={12} strokeWidth={2} aria-hidden="true" />
          No target id
        </span>
        <p className="field-helper">
          This link is incomplete: the official schema requires a <code>target</code>, and
          nothing here supplies one. No identifier is invented to fill it.
        </p>
      </div>
    );
  }
  if (link.target.state === 'malformed') {
    return (
      <div className="link-target">
        <span className="link-target-state">
          <TriangleAlert size={12} strokeWidth={2} aria-hidden="true" />
          Not a record id
        </span>
        <span className="field-value">{link.target.text}</span>
        <p className="field-helper">
          A link target is another record’s identifier, and the official schema declares it
          as <code>^[0-9A-Z]{'{26}'}$</code> — 26 characters, digits and capital letters
          only. This value does not have that shape, and it is shown exactly as stored.
        </p>
      </div>
    );
  }
  return (
    <div className="link-target">
      <span className="field-value">{link.target.id}</span>
      <TargetResolution id={link.target.id} />
    </div>
  );
}

function LinkItem({ link }: { link: LinkView }) {
  return (
    <li className="link-item">
      <div className="link-item-head">
        <span className="link-item-index">Link {link.index + 1}</span>
        {!link.complete && (
          <span className="link-item-incomplete">
            <TriangleAlert size={12} strokeWidth={2} aria-hidden="true" />
            Incomplete
          </span>
        )}
      </div>
      <dl className="link-fields">
        <dt>Relation</dt>
        <dd>
          <LinkTermView term={link.rel} kind="relation" />
        </dd>
        <dt>Target</dt>
        <dd>
          <LinkTargetView link={link} />
        </dd>
        <dt>Basis</dt>
        <dd>
          <LinkTermView term={link.basis} kind="basis" />
        </dd>
        {link.notes !== null && (
          <>
            <dt>Notes</dt>
            <dd>{link.notes}</dd>
          </>
        )}
      </dl>
    </li>
  );
}

/**
 * The authoring disclosure.
 *
 * It is shown in every state, including the one where links exist, because the
 * question "how do I add one" is asked from both. It states the measured fact
 * and the one exception, and it is deliberately not a disabled button: a control
 * whose only outcome is a refusal teaches a reader to distrust the controls that
 * work.
 */
function LinksAuthoringNote() {
  return (
    <p className="record-info-note record-info-note-quiet">
      <Lock size={12} strokeWidth={2} aria-hidden="true" />
      Relationships cannot be added or removed in this build: no operation in this API
      writes a record’s <code>links</code>. The only links ISAAC writes are automatic — when
      two runs of one experiment record the same <code>sample.sample_id</code>, the export
      links their records with <code>same_sample_as</code> on the basis{' '}
      <code>same_sample_id</code>.
    </p>
  );
}

export function RecordLinksPanel({ artifacts }: { artifacts: ApiArtifactsResponse }) {
  const record = artifacts.record;
  const links = readLinks(record);
  const summary =
    record === null
      ? 'written into the official record at export'
      : links.length === 1
        ? '1 relationship'
        : `${links.length} relationships`;

  return (
    <Section id="record-links" title="Relationships" sublabel="links" summary={summary}>
      <p className="record-info-note">
        A relationship declares how this record stands to another ISAAC record — what it was
        derived from, what it replicates, what it is a calibration of. The official schema
        requires all three of a relation, a target record identifier and a basis on every
        one of them.
      </p>
      {record === null ? (
        <p className="record-info-note record-info-note-quiet">
          <Network size={12} strokeWidth={2} aria-hidden="true" />
          This screen reads relationships out of the exported record. This experiment has no
          readable exported record, so there are none to show — which is not the same as the
          record declaring none.
        </p>
      ) : links.length === 0 ? (
        <p className="record-info-note record-info-note-quiet">
          <Network size={12} strokeWidth={2} aria-hidden="true" />
          The exported record declares no relationship to another record.
        </p>
      ) : (
        <ol className="link-list">
          {links.map((link) => (
            <LinkItem key={link.index} link={link} />
          ))}
        </ol>
      )}
      <LinksAuthoringNote />
    </Section>
  );
}
