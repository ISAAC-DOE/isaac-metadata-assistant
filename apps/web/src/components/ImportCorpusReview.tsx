import { Fragment, useId, useMemo, useState } from 'react';
import '../screens/bl15-review.css';
import { TriangleAlert } from './icons';
import { Disclosure } from './Disclosure';
import { HelpTip } from './HelpTip';
import { SemanticStatus } from './SemanticStatus';
import { ImportCandidateRow } from './ImportCandidateRow';
import { SignalSelection } from './ImportRules';
import {
  BL15_COLUMNS,
  BL15_COPY,
  BL15_FILTERS,
  BL15_STATUS_LABELS,
  BL15_UNIT_STATE_LABELS,
  BL15_UNIT_STATE_NOTES,
  conceptLabel,
  sourceTypeLabel,
  statusLabel,
  type Bl15FilterId,
} from '../lib/bl15ReviewContent';
import {
  BL15_MAPPING_STATUSES,
  cellFor,
  conceptsWithStatus,
  corpusDigest,
  normalizedText,
  readingsByStem,
  unattachedByType,
  unitState,
  type Bl15Cell,
  type Bl15ColumnId,
  type Bl15CorpusReview,
  type Bl15MeasurementUnit,
  type Bl15SourceEvidence,
} from '../lib/bl15Review';
import { IMPORT_STAGE_COPY } from '../lib/historicalImportContent';
import {
  BASIS_LABELS,
  BUCKET_ORDER,
  candidateBucket,
  SCOPE_LABELS,
  shortConventionName,
  signalState,
  unitCandidates,
} from '../lib/importStages';
import type { ProposalDestinations } from '../lib/importDestinations';
import type {
  ApiImportApplicability,
  ApiImportCandidate,
  ApiImportProfile,
  ApiImportUnitRow,
} from '../lib/types';

const COPY = IMPORT_STAGE_COPY;
type ActFn = (name: string, run: () => Promise<unknown>) => Promise<void>;

/**
 * BL15-2 LARGE-CORPUS REVIEW — `BL15R-012`, REBUILT AS STAGE PIECES (owner QA H1,
 * 2026-09-22).
 *
 * This component used to render the whole review at once: the digest, the ceiling,
 * every sample group's table, every conflict, the mapping registry, the extended
 * context and the left-out lists, one after the other — the bulk of a 43,994 px page
 * for a five-measurement archive. It is now two pieces the stage flow places:
 *
 *   * {@link CorpusReadOverview} — WHAT ISAAC READ: the counts, the naming
 *     conventions in force, temperature, the HERFD signal summary, the Data Quality
 *     Notes, and the four reference blocks behind disclosures;
 *   * {@link ArchiveRuns} — RUNS & CANDIDATES: the measurements by sample group, each
 *     one opening to its values, candidates, signal selection, notes and sources.
 *
 * Conflicts moved to their own stage (`ImportConflicts`), where each is shown source by
 * source with the four layers the server keeps apart.
 *
 * ── WHAT DID NOT CHANGE ─────────────────────────────────────────────────────
 *
 * The banned pattern is still banned: no flat file manifest (it is not on the wire —
 * `ArchiveInventory.to_state()` omits `entries`). Every count is still derived and
 * says what from. `source_count` is still the server's (byte-identical copies counted
 * once), never `scans.length + 1`. Unit states still name what was OBSERVED — there is
 * no unit state called Ready, because a Run from this corpus cannot be export-ready.
 */

/* ── what ISAAC read ─────────────────────────────────────────────────────── */

/*
 * WHAT THE READ FOUND, not a second copy of the session header: the header already
 * counts measurements, sample groups and conflicts — and its conflict count includes
 * the field disagreements, so a second, smaller "conflicts" number here read as a
 * contradiction. Every count, with its expression, stays one press away below.
 */
const HIGHLIGHT_IDS = ['sources', 'measurements', 'unattached', 'refused'];

export function CorpusReadOverview({
  review,
  profiles,
  units,
}: {
  review: Bl15CorpusReview;
  profiles: ApiImportProfile[];
  units: ApiImportUnitRow[];
}) {
  const digest = useMemo(() => corpusDigest(review), [review]);
  const unattached = useMemo(() => unattachedByType(review.relationships), [review]);
  const highlights = digest.filter((row) => HIGHLIGHT_IDS.includes(row.id));

  return (
    <section className="bl15" aria-labelledby="bl15-heading">
      <h4 className="bl15-heading" id="bl15-heading">
        {review.inventory.root_label}
      </h4>

      {/* The archive walk stopping early makes every count below a FLOOR rather
          than a total, so it is stated before the counts, not after them. */}
      {review.inventory.truncated_reason && (
        <p className="bl15-warn" role="note">
          <TriangleAlert size={13} strokeWidth={2.2} aria-hidden="true" />
          <span>
            This archive walk stopped early ({review.inventory.truncated_reason}), so every
            count below describes only what it reached.
          </span>
        </p>
      )}

      <dl className="bl15-highlights">
        {highlights.map((row) => (
          <div className="bl15-highlight" key={row.id}>
            <dt>{row.label}</dt>
            <dd>{row.value.toLocaleString('en-US')}</dd>
          </div>
        ))}
      </dl>

      <Disclosure className="bl15-more" summary={COPY.allCounts}>
        <p className="bl15-lead">{BL15_COPY.digestLead}</p>
        <ul className="bl15-digest">
          {digest.map((row) => (
            <li key={row.id}>
              <span className="bl15-digest-value">{row.value.toLocaleString('en-US')}</span>
              <span className="bl15-digest-label">{row.label}</span>
              {/* The expression, not a restatement of the label. A reader can check
                  the number against the payload with this alone. */}
              <span className="bl15-derived">
                Derived from <code>{row.derivedFrom}</code>.
              </span>
            </li>
          ))}
        </ul>
        <p className="bl15-note" role="note">
          {BL15_COPY.manifestNote}
        </p>
      </Disclosure>

      <Conventions review={review} profiles={profiles} units={units} />
      <Temperature review={review} />
      <SignalSummary review={review} />
      <QualityNotes review={review} />
      {review.beamtime_contributors && review.beamtime_contributors.length > 0 && (
        <div className="bl15-fact">
          <div className="hi-stage-sub-head">
            <h5 className="bl15-fact-title">{COPY.peopleTitle}</h5>
            <HelpTip subject={COPY.peopleTitle}>{COPY.peopleHelp}</HelpTip>
          </div>
          <p className="bl15-fact-body">
            {review.beamtime_contributors.map((p) => p.name).join(', ')}
          </p>
        </div>
      )}

      <div className="bl15-reference">
        <Disclosure className="bl15-more" summary={COPY.mapping}>
          <MappingReview review={review} />
        </Disclosure>
        <Disclosure className="bl15-more" summary={COPY.ceiling}>
          <Ceiling review={review} />
        </Disclosure>
        {review.extended_context && (
          <Disclosure
            className="bl15-more"
            summary={COPY.extended}
            meta={review.extended_context.available.toLocaleString('en-US')}
          >
            <ExtendedContextReview extended={review.extended_context} />
          </Disclosure>
        )}
        {(unattached.length > 0 || review.inventory.refused.length > 0) && (
          <Disclosure className="bl15-more" summary={COPY.leftOut}>
            <LeftOut unattached={unattached} refused={review.inventory.refused} />
          </Disclosure>
        )}
      </div>
    </section>
  );
}

/**
 * WHICH CONVENTION READ WHICH SOURCES — never who ran them. The counts come from the
 * server's `profile_applicability`; an ambiguous tie and a stale binding are states,
 * so they are shown, never tucked into a tip.
 */
function Conventions({
  review,
  profiles,
  units,
}: {
  review: Bl15CorpusReview;
  profiles: ApiImportProfile[];
  units: ApiImportUnitRow[];
}) {
  const applicability = review.profile_applicability;
  if (!applicability) return null;
  const nameOf = (id: string) => {
    const p = profiles.find((profile) => profile.profile_id === id);
    return p ? shortConventionName(p.display_name) : id;
  };
  const counts = Object.entries(applicability.convention_counts).filter(([id]) => id !== 'ambiguous');
  const stale = units.filter(
    (u) => (u.applicability as ApiImportApplicability | undefined)?.stale_bindings?.length,
  ).length;
  return (
    <div className="bl15-fact">
      <div className="hi-stage-sub-head">
        <h5 className="bl15-fact-title">{COPY.conventionsTitle}</h5>
        <HelpTip subject={COPY.conventionsTitle}>{COPY.conventionsHelp}</HelpTip>
      </div>
      <ul className="bl15-fact-list">
        {counts.map(([id, n]) => (
          <li key={id}>
            <span className="bl15-fact-strong">{nameOf(id)}</span>
            <span className="hi-sub">
              read {n} source{n === 1 ? '' : 's'}
            </span>
          </li>
        ))}
      </ul>
      {applicability.ambiguous_sources > 0 && (
        <p className="bl15-fact-body">
          <SemanticStatus state="needsReview" label={COPY.stateLabels.ambiguous} size="sm" />{' '}
          {applicability.ambiguous_sources} source
          {applicability.ambiguous_sources === 1 ? ' is' : 's are'} matched by two conventions
          equally. Each was read under both, and nothing was chosen.
        </p>
      )}
      {stale > 0 && (
        <p className="bl15-fact-body">
          <SemanticStatus state="needsReview" label={COPY.stateLabels.stale} size="sm" /> {stale}{' '}
          measurement{stale === 1 ? '' : 's'} match a rule written for a convention version that is
          no longer registered, so that rule does not apply.
        </p>
      )}
    </div>
  );
}

/** Temperature: `Not recorded` when no source states one; a source's words, verbatim, when one does. */
function Temperature({ review }: { review: Bl15CorpusReview }) {
  const t = review.temperature;
  if (!t) return null;
  return (
    <div className="bl15-fact">
      <div className="hi-stage-sub-head">
        <h5 className="bl15-fact-title">{COPY.temperatureTitle}</h5>
        {t.status === 'not_recorded' ? (
          <SemanticStatus state="missing" label={COPY.stateLabels.notRecorded} size="sm" />
        ) : (
          <SemanticStatus state="inherited" label={COPY.stateLabels.stated} size="sm" />
        )}
      </div>
      {t.status === 'stated_in_source' ? (
        <>
          <ul className="bl15-fact-list">
            {t.statements.map((statement, index) => (
              <li key={index}>
                <q className="bl15-quote">{statement.raw_literal}</q>
                {statement.source_path && <span className="hi-sub">{statement.source_path}</span>}
              </li>
            ))}
          </ul>
          <p className="hi-sub">{COPY.temperatureStated}</p>
        </>
      ) : (
        /* THE POLICY SENTENCE IS SHOWN ONLY WHEN NO SOURCE STATES A TEMPERATURE: it
           begins "this corpus states no temperature anywhere", which would contradict
           a verbatim statement shown directly above it. */
        <Disclosure className="bl15-more" summary={COPY.temperatureWhy}>
          <p className="bl15-concept-reason">{t.policy}</p>
        </Disclosure>
      )}
    </div>
  );
}

function SignalSummary({ review }: { review: Bl15CorpusReview }) {
  const signal = review.herfd_signal;
  if (!signal) return null;
  const statuses = Object.entries(signal.by_status);
  const words: Record<string, string> = {
    proposed: 'suggested',
    unresolved: 'not resolved',
    confirmed: 'confirmed',
    needs_review: 'need review',
  };
  return (
    <div className="bl15-fact">
      <div className="hi-stage-sub-head">
        <h5 className="bl15-fact-title">{COPY.signalTitle}</h5>
        <HelpTip subject={COPY.signalTitle}>{COPY.signalHelp}</HelpTip>
      </div>
      <p className="bl15-fact-body">
        {statuses.length === 0
          ? 'No run carries a candidate Vortex channel.'
          : statuses.map(([status, n]) => `${n} ${words[status] ?? status}`).join(' · ')}
      </p>
      {signal.element_evidence.length > 0 && (
        <p className="hi-sub">
          Element{signal.element_evidence.length === 1 ? '' : 's'} stated:{' '}
          {signal.element_evidence
            .map((e) => `${e.element}${e.edge ? ` ${e.edge}` : ''} (${e.source_path})`)
            .join('; ')}
        </p>
      )}
    </div>
  );
}

function QualityNotes({ review }: { review: Bl15CorpusReview }) {
  const notes = review.data_quality_notes;
  if (!notes) return null;
  return (
    <div className="bl15-fact">
      <div className="hi-stage-sub-head">
        <h5 className="bl15-fact-title">{notes.label}</h5>
      </div>
      <p className="bl15-fact-body">
        {notes.bound_to_a_measurement === 0
          ? 'No note is bound to a measurement.'
          : `${notes.bound_to_a_measurement.toLocaleString('en-US')} bound to a measurement.`}{' '}
        {COPY.qualityNote}
      </p>
      {notes.unbound.length > 0 && (
        <ul className="bl15-fact-list">
          {notes.unbound.map((n, index) => (
            <li key={index}>
              <q className="bl15-quote">{n.text}</q>
              <span className="hi-sub">not bound to a measurement · {n.source_path}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ── runs & candidates ───────────────────────────────────────────────────── */

export function ArchiveRuns({
  review,
  units,
  profiles,
  candidatesById,
  filenameOf,
  importId,
  busy,
  onAct,
  destinations,
}: {
  review: Bl15CorpusReview;
  units: ApiImportUnitRow[];
  profiles: ApiImportProfile[];
  candidatesById: ReadonlyMap<string, ApiImportCandidate>;
  filenameOf: (sourceId: string) => string;
  importId: string;
  busy: string | null;
  onAct: ActFn;
  destinations: ProposalDestinations;
}) {
  const index = useMemo(() => readingsByStem(review.evidence), [review.evidence]);
  const rowsByStem = useMemo(() => new Map(units.map((u) => [u.stem, u])), [units]);
  const unitsByStem = useMemo(() => {
    const out = new Map<string, Bl15MeasurementUnit>();
    for (const u of review.relationships.units) out.set(u.stem, u);
    return out;
  }, [review.relationships.units]);
  const states = useMemo(() => {
    const out = new Map<string, string>();
    for (const u of review.relationships.units) out.set(u.stem, unitState(u, index.get(u.stem)));
    return out;
  }, [review.relationships.units, index]);

  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<Bl15FilterId>('all');
  const needle = query.trim().toLowerCase();
  const matches = (u: Bl15MeasurementUnit): boolean => {
    if (filter !== 'all' && states.get(u.stem) !== filter) return false;
    if (!needle) return true;
    if (u.stem.toLowerCase().includes(needle)) return true;
    if (String(u.legacy_number ?? '').includes(needle)) return true;
    if ((u.group_token ?? '').toLowerCase().includes(needle)) return true;
    const byConcept = index.get(u.stem);
    if (!byConcept) return false;
    for (const list of byConcept.values())
      for (const e of list)
        if (
          e.raw_literal.toLowerCase().includes(needle) ||
          normalizedText(e.normalized_value).toLowerCase().includes(needle)
        )
          return true;
    return false;
  };
  const visibleTotal = review.relationships.units.filter(matches).length;
  const nameOf = (id: string) => {
    const p = profiles.find((profile) => profile.profile_id === id);
    return p ? shortConventionName(p.display_name) : id;
  };
  const filterName = useId();

  return (
    <div className="bl15-runs">
      <div className="bl15-controls">
        <label className="bl15-field">
          <span className="bl15-field-label">{BL15_COPY.searchLabel}</span>
          <input
            className="bl15-input"
            type="search"
            value={query}
            placeholder={BL15_COPY.searchPlaceholder}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <fieldset className="bl15-filters">
          <legend className="bl15-field-label">{BL15_COPY.filterLabel}</legend>
          {BL15_FILTERS.map((f) => (
            <label key={f.id} className="bl15-chip">
              <input
                type="radio"
                name={filterName}
                value={f.id}
                checked={filter === f.id}
                onChange={() => setFilter(f.id)}
              />
              <span>{f.label}</span>
            </label>
          ))}
        </fieldset>
      </div>

      {visibleTotal === 0 ? (
        <p className="bl15-empty">{BL15_COPY.noMatches}</p>
      ) : (
        review.relationships.groups.map((group) => {
          const groupUnits = group.stems
            .map((s) => unitsByStem.get(s))
            .filter((u): u is Bl15MeasurementUnit => !!u)
            .filter(matches);
          if (groupUnits.length === 0) return null;
          const token = group.group_token;
          const conventions = new Set(
            groupUnits.flatMap(
              (u) => ((rowsByStem.get(u.stem)?.applicability as ApiImportApplicability | undefined)?.profile_ids ?? []),
            ),
          );
          const bases = new Set(
            groupUnits
              .map((u) => (rowsByStem.get(u.stem)?.applicability as ApiImportApplicability | undefined)?.basis)
              .filter(Boolean),
          );
          return (
            <section className="bl15-group" key={token ?? '__none__'}>
              <div className="bl15-group-head">
                <h4 className="bl15-group-title">
                  {token === null ? BL15_COPY.ungroupedLabel : `Sample ${token}`}
                </h4>
                <span className="bl15-group-meta">
                  {groupUnits.length === group.measurement_count
                    ? `${group.measurement_count} measurements`
                    : `${groupUnits.length} of ${group.measurement_count} measurements`}
                  {group.legacy_low !== null && group.legacy_high !== null
                    ? ` · legacy ${group.legacy_low}–${group.legacy_high}`
                    : ''}
                </span>
                {token !== null && group.contiguous && (
                  <HelpTip subject={`the grouping of sample ${token}`}>{BL15_COPY.contiguousNote}</HelpTip>
                )}
              </div>
              {conventions.size > 0 && (
                <p className="bl15-group-convention">
                  {[...conventions].map(nameOf).join(' + ')}
                  {bases.size === 1 ? ` · ${BASIS_LABELS[[...bases][0] as string] ?? ''}` : ''}
                </p>
              )}
              {/* A BROKEN RANGE IS AN UNCERTAINTY, so it stays on the surface; a
                  contiguous one is corroboration and sits behind the `?` above. */}
              {(token === null || !group.contiguous) && (
                <p className="bl15-group-note" role="note">
                  {token === null ? BL15_COPY.ungroupedNote : BL15_COPY.brokenNote}
                </p>
              )}
              <UnitsTable
                units={groupUnits}
                index={index}
                states={states}
                rowsByStem={rowsByStem}
                candidatesById={candidatesById}
                filenameOf={filenameOf}
                profiles={profiles}
                importId={importId}
                busy={busy}
                onAct={onAct}
                destinations={destinations}
              />
            </section>
          );
        })
      )}
    </div>
  );
}

function UnitsTable({
  units,
  index,
  states,
  rowsByStem,
  candidatesById,
  filenameOf,
  profiles,
  importId,
  busy,
  onAct,
  destinations,
}: {
  units: Bl15MeasurementUnit[];
  index: Map<string, Map<string, Bl15SourceEvidence[]>>;
  states: Map<string, string>;
  rowsByStem: Map<string, ApiImportUnitRow>;
  candidatesById: ReadonlyMap<string, ApiImportCandidate>;
  filenameOf: (sourceId: string) => string;
  profiles: ApiImportProfile[];
  importId: string;
  busy: string | null;
  onAct: ActFn;
  destinations: ProposalDestinations;
}) {
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const baseId = useId();
  const toggle = (stem: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(stem)) next.delete(stem);
      else next.add(stem);
      return next;
    });

  return (
    <table className="bl15-table">
      <thead>
        <tr>
          {BL15_COLUMNS.map((c) => (
            <th key={c.id} scope="col">
              {c.label}
              {c.id === 'sources' && <span className="sr-only"> ({BL15_COPY.sourcesColumnNote})</span>}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {units.map((u, i) => {
          const byConcept = index.get(u.stem);
          const state = states.get(u.stem) ?? 'no_values';
          const detailId = `${baseId}-unit-${i}`;
          const isOpen = open.has(u.stem);
          const row = rowsByStem.get(u.stem);
          return (
            <Fragment key={u.stem}>
              <tr className={`bl15-row bl15-row-${state}${isOpen ? ' is-open' : ''}`}>
                <th scope="row" className="bl15-legacy" data-label={BL15_COLUMNS[0].label}>
                  {/* THE WHOLE LEGACY CELL IS THE TOGGLE — a real button with
                      `aria-expanded`, the disclosure pattern the owner asked for,
                      in place of an 11px triangle on a spanning row. */}
                  <button
                    type="button"
                    className="bl15-unit-toggle"
                    aria-expanded={isOpen}
                    aria-controls={detailId}
                    onClick={() => toggle(u.stem)}
                  >
                    <span className="bl15-legacy-number">{u.legacy_number ?? '—'}</span>
                    <span className="bl15-stem">{u.stem}</span>
                  </button>
                </th>
                {(['sample', 'medium', 'state', 'filter', 'potential'] as Bl15ColumnId[]).map((col, ci) => (
                  <td key={col} data-label={BL15_COLUMNS[ci + 1].label}>
                    <CellView cell={cellFor(byConcept, col)} />
                  </td>
                ))}
                <td className="bl15-num" data-label={BL15_COLUMNS[6].label}>
                  {u.scan_count}
                </td>
                {/* `source_count`, NOT `scans.length + 1` — the server counts
                    byte-identical copies once and this renders that number. */}
                <td className="bl15-num" data-label={BL15_COLUMNS[7].label}>
                  {u.source_count}
                </td>
                <td data-label={BL15_COLUMNS[8].label}>
                  {state === 'conflict' ? (
                    <SemanticStatus state="conflict" label={BL15_UNIT_STATE_LABELS.conflict} size="sm" />
                  ) : (
                    <span className={`bl15-state bl15-state-${state}`}>
                      {BL15_UNIT_STATE_LABELS[state] ?? state}
                    </span>
                  )}
                  <span className="sr-only"> — {BL15_UNIT_STATE_NOTES[state]}</span>
                </td>
              </tr>
              <tr className="bl15-evidence-row" id={detailId} hidden={!isOpen}>
                <td colSpan={BL15_COLUMNS.length}>
                  <RunDetail
                    unit={u}
                    row={row}
                    byConcept={byConcept}
                    candidatesById={candidatesById}
                    filenameOf={filenameOf}
                    profiles={profiles}
                    importId={importId}
                    busy={busy}
                    onAct={onAct}
                    destinations={destinations}
                  />
                </td>
              </tr>
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}

/**
 * ONE MEASUREMENT, OPENED: its candidates by state, the convention that read it, its
 * HERFD signal, the notes' remarks about it and the people they name, and — one press
 * further — every source behind every value.
 */
function RunDetail({
  unit,
  row,
  byConcept,
  candidatesById,
  filenameOf,
  profiles,
  importId,
  busy,
  onAct,
  destinations,
}: {
  unit: Bl15MeasurementUnit;
  row: ApiImportUnitRow | undefined;
  byConcept: Map<string, Bl15SourceEvidence[]> | undefined;
  candidatesById: ReadonlyMap<string, ApiImportCandidate>;
  filenameOf: (sourceId: string) => string;
  profiles: ApiImportProfile[];
  importId: string;
  busy: string | null;
  onAct: ActFn;
  destinations: ProposalDestinations;
}) {
  const candidates = row ? unitCandidates(row, candidatesById).filter((c) => c.kind === 'field') : [];
  const applies = row?.applicability as ApiImportApplicability | undefined;
  const selection = row?.signal_selection ?? null;
  const notes = row?.data_quality_notes ?? [];
  const people = row?.contributors ?? [];
  const nameOf = (id: string) => {
    const p = profiles.find((profile) => profile.profile_id === id);
    return p ? shortConventionName(p.display_name) : id;
  };
  const sorted = [...candidates].sort(
    (a, b) => BUCKET_ORDER.indexOf(candidateBucket(a)) - BUCKET_ORDER.indexOf(candidateBucket(b)),
  );

  return (
    <div className="bl15-run">
      {row?.legacy_number_shared && (
        <p className="bl15-run-flag" role="note">
          <SemanticStatus state="conflict" label={COPY.stateLabels.conflict} size="sm" /> {COPY.sharedLegacy}
        </p>
      )}

      {applies && applies.profile_ids && applies.profile_ids.length > 0 && (
        <p className="bl15-run-line">
          <span className="bl15-run-key">{COPY.fields.convention}</span>
          <span>
            {applies.profile_ids.map(nameOf).join(' + ')} · {SCOPE_LABELS[applies.scope] ?? applies.scope} ·{' '}
            {BASIS_LABELS[applies.basis] ?? applies.basis}
          </span>
        </p>
      )}
      {applies?.ambiguity && (
        <p className="bl15-run-line">
          <SemanticStatus state="needsReview" label={COPY.stateLabels.ambiguous} size="sm" /> {applies.ambiguity}
        </p>
      )}
      {applies && applies.stale_bindings && applies.stale_bindings.length > 0 && (
        <p className="bl15-run-line">
          <SemanticStatus state="needsReview" label={COPY.stateLabels.stale} size="sm" /> A rule written for
          another version of its convention matches this measurement and does not apply.
        </p>
      )}

      {candidates.length > 0 && (
        <ul className="hi-cands">
          {sorted.map((c) => (
            <ImportCandidateRow key={c.candidate_id} candidate={c} filenameOf={filenameOf} />
          ))}
        </ul>
      )}

      {selection && row && (
        <div className="bl15-run-block">
          <h5 className="bl15-fact-title">{COPY.signalTitle}</h5>
          <SignalSelection
            unit={row}
            selection={selection}
            importId={importId}
            busy={busy}
            onAct={onAct}
            destinations={destinations}
            state={signalState(selection)}
          />
        </div>
      )}

      {notes.length > 0 && (
        <div className="bl15-run-block">
          <h5 className="bl15-fact-title">{COPY.qualityTitle}</h5>
          <ul className="bl15-fact-list">
            {notes.map((n, i) => (
              <li key={i}>
                <q className="bl15-quote">{n.text}</q>
                <span className="hi-sub">
                  {n.source_path}
                  {n.file_number !== null ? ` · file ${n.file_number}` : ''}
                </span>
              </li>
            ))}
          </ul>
          <p className="hi-sub">{COPY.qualityNote}</p>
        </div>
      )}

      {people.length > 0 && (
        <div className="bl15-run-line">
          <span className="bl15-run-key">{COPY.peopleTitle}</span>
          <span>{people.map((p) => p.name).join(', ')}</span>
          <HelpTip subject={`the people named for ${unit.stem}`}>{COPY.peopleHelp}</HelpTip>
        </div>
      )}

      <Disclosure className="bl15-more" summary={COPY.whereFrom}>
        <Bl15EvidenceDrawer unit={unit} byConcept={byConcept} />
      </Disclosure>
    </div>
  );
}

/**
 * One table cell. Three outcomes, and they are NOT interchangeable.
 *
 * `absent` says no source states it — which is different from a blank cell, and is
 * why it renders a word. `disputed` never shows a winner. A normalised reading keeps
 * its literal beside it; the rule that produced it is in the measurement's sources,
 * one press away, rather than several paragraphs inside a table cell.
 */
function CellView({ cell }: { cell: Bl15Cell }) {
  if (cell.state === 'absent') return <span className="bl15-absent">{BL15_COPY.absentCell}</span>;
  if (cell.state === 'disputed') {
    return (
      <span className="bl15-disputed">
        {cell.evidence.length} {BL15_COPY.disputedCell}
      </span>
    );
  }
  const e = cell.evidence;
  const normalized = e.normalized_value;
  const shown = normalized === null || normalized === undefined ? e.raw_literal : normalizedText(normalized);
  const differs = shown !== e.raw_literal;
  return (
    <span className="bl15-value">
      {shown}
      {e.unit ? <span className="bl15-unit"> {e.unit}</span> : null}
      {/* THE LITERAL IS NEVER REPLACED. When a rule produced a cleaner reading the
          raw text stays beside it — `ffilter35` is the case this exists for. */}
      {differs && (
        <span className="bl15-raw">
          {BL15_COPY.rawLabel} <code>{e.raw_literal}</code>
        </span>
      )}
    </span>
  );
}

/* ── the reference blocks, each behind a disclosure in the overview ─────── */

function ExtendedContextReview({
  extended,
}: {
  extended: NonNullable<Bl15CorpusReview['extended_context']>;
}) {
  const { dropped, thinned, unplaceable, ceiling } = extended;
  const anyCost = dropped > 0 || thinned > 0 || unplaceable > 0;
  return (
    <div className="bl15-block">
      <p className="bl15-lead">{BL15_COPY.extendedContextLead}</p>
      {/* THE SERVER'S OWN SENTENCE, VERBATIM — the artifact's definition of itself. */}
      <p className="bl15-concept-reason">{extended.not_official}</p>
      {anyCost ? (
        <ul className="bl15-ceiling">
          {dropped > 0 && (
            <li>
              <h5>
                {dropped.toLocaleString('en-US')} not carried — this reading reached its limit of{' '}
                {ceiling.toLocaleString('en-US')}
              </h5>
              <p>
                Statements past that limit are not in the companion. They are not shown here
                either: they were not kept, so nothing can say what they said without inventing
                it.
              </p>
            </li>
          )}
          {thinned > 0 && (
            <li>
              <h5>{thinned.toLocaleString('en-US')} repeated inside a single source</h5>
              <p>
                The same value stated more than once in one file. The first mention kept its
                location; the later ones did not. No statement was lost, and two sources that
                disagree are never merged — they are different entries.
              </p>
            </li>
          )}
          {unplaceable > 0 && (
            <li>
              <h5>{unplaceable.toLocaleString('en-US')} this build could not record</h5>
              <p>
                This build could not turn these into companion entries. That is a limit of the
                software rather than of the archive, so re-importing would not change it. They
                are still in this reading&apos;s other counts.
              </p>
            </li>
          )}
        </ul>
      ) : (
        <p className="bl15-concept-reason">{BL15_COPY.extendedContextNoneLeftOut}</p>
      )}
    </div>
  );
}

/**
 * The three schema requirements this corpus cannot satisfy, in the registry's own
 * sentences (`mapping.TEMPERATURE_ABSENT_REASON`, `ASSETS_BLOCKED_REASON`). The
 * `descriptors` requirement has no constant in the registry, so it is the one
 * sentence this component authors.
 */
function Ceiling({ review }: { review: Bl15CorpusReview }) {
  /* The registry's own temperature sentence, verbatim. It is true both of a corpus
     that states no temperature and of one that states one only in words (corrected
     server-side 2026-09-22), so it needs no second wording here. */
  const { temperature_absent_reason: temp, assets_blocked_reason: assets } = review.mapping;
  return (
    <div className="bl15-block">
      <p className="bl15-lead">{BL15_COPY.ceilingLead}</p>
      <ol className="bl15-ceiling">
        <li>
          <h5>A required temperature no source states as a number</h5>
          <p>{temp}</p>
        </li>
        <li>
          <h5>A required descriptor no historical source provides</h5>
          <p>
            An evidence record requires <code>descriptors</code>, and no source in this corpus
            provides one.
          </p>
        </li>
        <li>
          <h5>A required checksum this build never computes</h5>
          <p>{assets}</p>
        </li>
      </ol>
    </div>
  );
}

/**
 * The registry's five statuses, **as five outcomes and not as a progress bar**. A bar
 * over "fields mapped" would render 5/47 as ~90% failure when most of those are a
 * correct description of the official schema's coverage.
 */
function MappingReview({ review }: { review: Bl15CorpusReview }) {
  const { coverage, concepts, domain_questions: domainQuestions } = review.mapping;
  /* `question_id` -> the server's own `subject`, so an open question is named rather
     than numbered; the id is kept in parentheses as the traceable handle. */
  const questionSubjects = new Map((domainQuestions ?? []).map((q) => [q.question_id, q.subject]));
  const nameQuestion = (id: string) => {
    const subject = questionSubjects.get(id);
    return subject ? `${subject} (${id})` : id;
  };
  return (
    <div className="bl15-block">
      <p className="bl15-lead">{BL15_COPY.mappingLead}</p>
      <ul className="bl15-status-list">
        {BL15_MAPPING_STATUSES.map((status) => {
          const rows = conceptsWithStatus(concepts, status);
          const count = coverage[status] ?? rows.length;
          return (
            <li key={status}>
              <Disclosure
                className="bl15-status"
                summary={BL15_STATUS_LABELS[status] ?? statusLabel(status)}
                meta={`${count} of ${coverage.concepts_total}`}
              >
                <ul className="bl15-concepts">
                  {rows.map((c) => (
                    <li key={c.concept}>
                      <p className="bl15-concept-head">
                        <span className="bl15-concept-name">{conceptLabel(c.concept)}</span>
                        {c.official_path && <code className="bl15-path">{c.official_path}</code>}
                      </p>
                      {/* The registry's own sentence, verbatim. */}
                      <p className="bl15-concept-reason">{c.reason}</p>
                      {c.placement_name && (
                        <p className="bl15-concept-extra">
                          Where this information lands: {c.placement_name} (level{' '}
                          {c.placement_level}).
                        </p>
                      )}
                      {c.unresolved_questions && c.unresolved_questions.length > 0 && (
                        <p className="bl15-concept-open">
                          <span className="bl15-concept-open-lead">Still waiting on a domain answer:</span>{' '}
                          {c.unresolved_questions.map(nameQuestion).join('; ')}.
                        </p>
                      )}
                      {c.allowed_values.length > 0 && (
                        <p className="bl15-concept-extra">The schema allows: {c.allowed_values.join(', ')}.</p>
                      )}
                      {c.requires_siblings.length > 0 && (
                        <p className="bl15-concept-extra">
                          Satisfying this is not sufficient on its own — the schema also requires{' '}
                          {c.requires_siblings.join(', ')}.
                        </p>
                      )}
                      {c.candidate_homes.length > 0 && (
                        <p className="bl15-concept-extra">
                          Candidate home, named and not applied: {c.candidate_homes.join(', ')}.
                        </p>
                      )}
                      {c.rule && <p className="bl15-concept-extra">Rule: {c.rule}</p>}
                    </li>
                  ))}
                </ul>
              </Disclosure>
            </li>
          );
        })}
      </ul>
      {coverage.not_examined > 0 && (
        <p className="bl15-note" role="note">
          {coverage.not_examined} concept{coverage.not_examined === 1 ? '' : 's'} in this
          corpus&rsquo;s vocabulary have not been examined by the registry at all.
        </p>
      )}
    </div>
  );
}

/**
 * The complete `unattached` and `refused` lists — as load-bearing as `units`, per
 * `Relationships.unattached`'s own docstring. Each group keeps the SERVER's reason.
 */
function LeftOut({
  unattached,
  refused,
}: {
  unattached: ReturnType<typeof unattachedByType>;
  refused: Bl15CorpusReview['inventory']['refused'];
}) {
  return (
    <div className="bl15-block">
      {unattached.map((g) => (
        <div className="bl15-leftout" key={g.source_type}>
          <h5 className="bl15-leftout-title">
            {sourceTypeLabel(g.source_type)}
            <span className="bl15-count">{g.paths.length}</span>
          </h5>
          <p className="bl15-leftout-reason">{g.reason}</p>
          <ul className="bl15-paths">
            {g.paths.map((p) => (
              <li key={p}>
                <code>{p}</code>
              </li>
            ))}
          </ul>
        </div>
      ))}
      {refused.length > 0 && (
        <div className="bl15-leftout">
          <h5 className="bl15-leftout-title">
            {BL15_COPY.refusedTitle}
            <span className="bl15-count">{refused.length}</span>
          </h5>
          <ul className="bl15-paths">
            {refused.map((r) => (
              <li key={r.archive_path}>
                <code>{r.archive_path}</code>
                <span className="bl15-refused-reason">
                  {r.reason}
                  {r.detail ? ` — ${r.detail}` : ''}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/**
 * Per-field provenance for ONE measurement, scientist-readable and never raw JSON.
 *
 * Each row is *filename + what it says*. The reference basis is shown when a source
 * states one; it is not defaulted. The named rule that normalised a reading is here,
 * beside it, rather than inside a table cell.
 */
export function Bl15EvidenceDrawer({
  unit,
  byConcept,
}: {
  unit: Bl15MeasurementUnit;
  byConcept: Map<string, Bl15SourceEvidence[]> | undefined;
}) {
  const concepts = byConcept ? [...byConcept.keys()].sort() : [];
  const basis = byConcept?.get('potential_reference_basis')?.[0];
  const copies = unit.duplicate_copies.length + unit.suppressed_duplicate_acquisitions.length;
  return (
    <div className="bl15-evidence">
      <h5 className="bl15-evidence-title">{BL15_COPY.evidenceTitle}</h5>
      {concepts.length === 0 ? (
        <p className="bl15-absent">No source in this import states a mapped value for this measurement.</p>
      ) : (
        <ul className="bl15-evidence-list">
          {concepts.map((concept) => {
            const hits = byConcept?.get(concept) ?? [];
            return (
              <li key={concept}>
                <p className="bl15-evidence-concept">{conceptLabel(concept)}</p>
                {concept === 'potential_magnitude' && basis && (
                  <p className="bl15-evidence-basis">Reference basis: {basis.raw_literal}</p>
                )}
                <ul className="bl15-evidence-sources">
                  {hits.map((e) => (
                    <li key={e.evidence_id}>
                      <span className="bl15-evidence-file">{e.source_path}</span>
                      <span className="bl15-evidence-says">
                        says <strong>{e.raw_literal}</strong>
                        {e.normalized_value !== null && e.normalized_value !== undefined
                          ? ` · ${BL15_COPY.normalizedLabel} ${normalizedText(e.normalized_value)}${e.unit ? ` ${e.unit}` : ''}`
                          : ''}
                      </span>
                      <span className="bl15-evidence-where">
                        {e.locator} · {sourceTypeLabel(e.source_type)}
                      </span>
                      {e.normalization_rule && (
                        <span className="bl15-evidence-rule">
                          {BL15_COPY.ruleLabel}: {e.normalization_rule}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </li>
            );
          })}
        </ul>
      )}
      <p className="bl15-evidence-structure">
        {unit.source_count} distinct source{unit.source_count === 1 ? '' : 's'} support this
        measurement, counting byte-identical copies once.
        {copies > 0
          ? ` ${copies} byte-identical cop${copies === 1 ? 'y is' : 'ies are'} kept but not counted as extra witnesses.`
          : ''}
      </p>
      {unit.internal_declaration && (
        <p className="bl15-evidence-structure">
          The acquisition file declares itself <code>{unit.internal_declaration}</code>.
        </p>
      )}
      {unit.declared_by.length > 0 && (
        <ul className="bl15-evidence-macros">
          {unit.declared_by.map((b) => (
            <li key={`${b.macro_path}-${b.block_index}`}>
              <code>{b.macro_path}</code> declared this at block {b.block_index}
              {b.acquired ? '' : ' — and no acquisition of that name exists'}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
