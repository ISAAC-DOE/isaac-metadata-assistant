import { useMemo, useState } from 'react';
import '../screens/bl15-review.css';
import { TriangleAlert } from './icons';
import {
  BL15_COLUMNS,
  BL15_COPY,
  BL15_FILTERS,
  BL15_STATUS_LABELS,
  BL15_UNIT_STATE_LABELS,
  BL15_UNIT_STATE_NOTES,
  conceptLabel,
  conflictKindLabel,
  sourceTypeLabel,
  statusLabel,
  type Bl15FilterId,
} from '../lib/bl15ReviewContent';
import {
  BL15_MAPPING_STATUSES,
  cellFor,
  conceptsWithStatus,
  conflictsByKind,
  corpusDigest,
  readingsByStem,
  unattachedByType,
  unitState,
  type Bl15Cell,
  type Bl15ColumnId,
  type Bl15Conflict,
  type Bl15CorpusReview,
  type Bl15MeasurementUnit,
  type Bl15SourceEvidence,
} from '../lib/bl15Review';

/**
 * BL15-2 LARGE-CORPUS REVIEW — `BL15R-012`.
 *
 * ── THE BANNED PATTERN, ONE LAYER DOWN ─────────────────────────────────────
 *
 * `HIST-004` bans `Upload -> Spinner -> Mysterious JSON`, and a flat table of
 * 1,192 source rows is its sibling: a scientist cannot audit 1,192 rows, so a
 * complete manifest they cannot read is the same as no manifest. **Nothing here
 * renders one.** The archive opens as a DIGEST — fifteen derived counts — and the
 * measurements are reached through their sample groups.
 *
 * It is also not available to render: `ArchiveInventory.to_state()` serialises
 * `entry_count` and omits `entries` entirely. `BL15_COPY.manifestNote` says so
 * rather than implying a list is one click away.
 *
 * ── EVERY NUMBER IS DERIVED, AND SAYS WHAT FROM ────────────────────────────
 *
 * `CLAUDE.md` §11 records four surfaces that shipped a number they had not derived
 * from what they claimed to describe. So `corpusDigest` computes each count from the
 * payload and carries the expression with it, and the expression is rendered under
 * disclosure beside the number.
 *
 * The one that matters most: the Sources column renders `unit.source_count`, which
 * the server computes **counting byte-identical copies once**. `scans.length + 1`
 * would be a different and wrong number — on the committed fixture, 4 where the
 * truth is 7.
 *
 * ── NO PROGRESS BAR, AND NO "READY" ────────────────────────────────────────
 *
 * The integration design §5 establishes that a candidate Run from this corpus
 * cannot be export-ready: `context.temperature_K` is required and the corpus states
 * no temperature anywhere, `record_type: evidence` requires `descriptors`, and
 * `assets[]` requires a `sha256` this build never computes. A progress indicator
 * would be an indicator that can never fill, so there is none, and the unit states
 * name what was OBSERVED (`Values read`, `Sources disagree`, `No values read`)
 * rather than how far along something is.
 *
 * Likewise no bar over "fields mapped": `deterministic` and `normalized` are 5 of 45
 * concepts, so a completion bar would read as 87% failure when it is mostly a
 * correct description of the schema's coverage. The five statuses are shown as five
 * first-class outcomes, each with the registry's own `reason`.
 *
 * ── PROGRESSIVE DISCLOSURE, SAME SHAPE AS DATA & PRIVACY ───────────────────
 *
 * Every explanatory block is a native `<details>` whose `<summary>` carries a
 * heading and nothing else — a topic, never a claim. That is the same rule and the
 * same reason as `SettingsPage.tsx`'s `PrivacyBody`: a summary that asserts
 * something, with its scope hidden, would overstate. Nothing is deleted or
 * shortened; every sentence stays in the DOM.
 *
 * **Any disclosure added here must be registered in `e2e/helpers/disclosures.ts`**,
 * or its contents leave every axe scan at every viewport while the baseline merely
 * fails to move. See `SETTINGS_CONCEPT_DISCLOSURES` for the precedent.
 */
export function ImportCorpusReview({ review }: { review: Bl15CorpusReview }) {
  const digest = useMemo(() => corpusDigest(review), [review]);
  const index = useMemo(() => readingsByStem(review.evidence), [review.evidence]);
  const unattached = useMemo(() => unattachedByType(review.relationships), [review]);
  const byKind = useMemo(() => conflictsByKind(review.relationships), [review]);

  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<Bl15FilterId>('all');

  const states = useMemo(() => {
    const out = new Map<string, string>();
    for (const u of review.relationships.units) out.set(u.stem, unitState(u, index.get(u.stem)));
    return out;
  }, [review.relationships.units, index]);

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
          String(e.normalized_value ?? '').toLowerCase().includes(needle)
        )
          return true;
    return false;
  };

  const unitsByStem = useMemo(() => {
    const out = new Map<string, Bl15MeasurementUnit>();
    for (const u of review.relationships.units) out.set(u.stem, u);
    return out;
  }, [review.relationships.units]);

  const visibleTotal = review.relationships.units.filter(matches).length;

  return (
    <section className="bl15" aria-labelledby="bl15-heading">
      <h3 className="bl15-heading" id="bl15-heading">
        {review.inventory.root_label}
      </h3>

      {/* The archive walk stopping early makes every count below a FLOOR rather
          than a total, so it is stated before the digest, not after it. */}
      {review.inventory.truncated_reason && (
        <p className="bl15-warn" role="note">
          <TriangleAlert size={13} strokeWidth={2.2} aria-hidden="true" />
          <span>
            This archive walk stopped early ({review.inventory.truncated_reason}), so every
            count below describes only what it reached.
          </span>
        </p>
      )}

      <Digest digest={digest} note={BL15_COPY.manifestNote} />

      <Ceiling review={review} />

      <Groups
        review={review}
        index={index}
        states={states}
        unitsByStem={unitsByStem}
        matches={matches}
        visibleTotal={visibleTotal}
        query={query}
        setQuery={setQuery}
        filter={filter}
        setFilter={setFilter}
      />

      <Conflicts byKind={byKind} />

      <MappingReview review={review} />

      <LeftOut unattached={unattached} refused={review.inventory.refused} />
    </section>
  );
}

/* ── the digest ─────────────────────────────────────────────────────────── */

function Digest({
  digest,
  note,
}: {
  digest: ReturnType<typeof corpusDigest>;
  note: string;
}) {
  return (
    <div className="bl15-block">
      <h4 className="bl15-block-title">{BL15_COPY.digestTitle}</h4>
      <p className="bl15-lead">{BL15_COPY.digestLead}</p>
      <ul className="bl15-digest">
        {digest.map((row) => (
          <li key={row.id}>
            <details className="bl15-digest-row">
              <summary>
                <span className="bl15-digest-value">{row.value.toLocaleString('en-US')}</span>
                <span className="bl15-digest-label">{row.label}</span>
              </summary>
              {/* The expression, not a restatement of the label. A reader can
                  check the number against the payload with this alone. */}
              <p className="bl15-derived">
                Derived from <code>{row.derivedFrom}</code>.
              </p>
            </details>
          </li>
        ))}
      </ul>
      <p className="bl15-note" role="note">
        {note}
      </p>
    </div>
  );
}

/* ── the ceiling ────────────────────────────────────────────────────────── */

/**
 * The three schema requirements this corpus cannot satisfy.
 *
 * Rendered from `mapping.TEMPERATURE_ABSENT_REASON` and `ASSETS_BLOCKED_REASON`
 * rather than re-authored, per the coordinator's instruction and §15's
 * one-vocabulary rule. The `descriptors` requirement has no constant in the
 * registry — it is a schema `allOf` clause named in the integration design §5 — so
 * it is stated here as the one sentence this component authors, and it is marked as
 * such rather than passed off as the server's.
 */
function Ceiling({ review }: { review: Bl15CorpusReview }) {
  const { temperature_absent_reason: temp, assets_blocked_reason: assets } = review.mapping;
  return (
    <div className="bl15-block">
      <details className="bl15-disclosure">
        <summary>
          <h4 className="bl15-block-title">{BL15_COPY.ceilingTitle}</h4>
        </summary>
        <p className="bl15-lead">{BL15_COPY.ceilingLead}</p>
        <ol className="bl15-ceiling">
          <li>
            <h5>A required temperature no source states</h5>
            <p>{temp}</p>
          </li>
          <li>
            <h5>A required descriptor no historical source provides</h5>
            <p>
              An evidence record requires <code>descriptors</code>, and no source in this
              corpus provides one.
            </p>
          </li>
          <li>
            <h5>A required checksum this build never computes</h5>
            <p>{assets}</p>
          </li>
        </ol>
      </details>
    </div>
  );
}

/* ── sample groups and the measurements table ───────────────────────────── */

function Groups({
  review,
  index,
  states,
  unitsByStem,
  matches,
  visibleTotal,
  query,
  setQuery,
  filter,
  setFilter,
}: {
  review: Bl15CorpusReview;
  index: Map<string, Map<string, Bl15SourceEvidence[]>>;
  states: Map<string, string>;
  unitsByStem: Map<string, Bl15MeasurementUnit>;
  matches: (u: Bl15MeasurementUnit) => boolean;
  visibleTotal: number;
  query: string;
  setQuery: (v: string) => void;
  filter: Bl15FilterId;
  setFilter: (v: Bl15FilterId) => void;
}) {
  return (
    <div className="bl15-block">
      <h4 className="bl15-block-title">{BL15_COPY.groupsTitle}</h4>
      <p className="bl15-lead">{BL15_COPY.groupsLead}</p>

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
                name="bl15-filter"
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
          const units = group.stems
            .map((s) => unitsByStem.get(s))
            .filter((u): u is Bl15MeasurementUnit => !!u)
            .filter(matches);
          if (units.length === 0) return null;
          const token = group.group_token;
          return (
            <div className="bl15-group" key={token ?? '__none__'}>
              <div className="bl15-group-head">
                <h5 className="bl15-group-title">
                  {token === null ? BL15_COPY.ungroupedLabel : `Sample ${token}`}
                </h5>
                <span className="bl15-group-meta">
                  {units.length === group.measurement_count
                    ? `${group.measurement_count} measurements`
                    : `${units.length} of ${group.measurement_count} measurements`}
                  {group.legacy_low !== null && group.legacy_high !== null
                    ? ` · legacy ${group.legacy_low}–${group.legacy_high}`
                    : ''}
                </span>
              </div>
              {/* Contiguity is corroboration, never proof — and a BROKEN range is
                  the signal the grouping token may not mean the sample. Both are
                  stated; neither is silent. */}
              <p className="bl15-group-note" role="note">
                {token === null
                  ? BL15_COPY.ungroupedNote
                  : group.contiguous
                    ? BL15_COPY.contiguousNote
                    : BL15_COPY.brokenNote}
              </p>
              <UnitsTable units={units} index={index} states={states} />
            </div>
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
}: {
  units: Bl15MeasurementUnit[];
  index: Map<string, Map<string, Bl15SourceEvidence[]>>;
  states: Map<string, string>;
}) {
  return (
    <table className="bl15-table">
      <thead>
        <tr>
          {BL15_COLUMNS.map((c) => (
            <th
              key={c.id}
              scope="col"
              title={c.id === 'sources' ? BL15_COPY.sourcesColumnNote : undefined}
            >
              {c.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {units.map((u) => {
          const byConcept = index.get(u.stem);
          const state = states.get(u.stem) ?? 'no_values';
          return [
            <tr key={u.stem} className={`bl15-row bl15-row-${state}`}>
              <th scope="row" className="bl15-legacy">
                {u.legacy_number ?? '—'}
                <span className="bl15-stem">{u.stem}</span>
              </th>
              {(['sample', 'medium', 'state', 'filter', 'potential'] as Bl15ColumnId[]).map(
                (col) => (
                  <td key={col}>
                    <CellView cell={cellFor(byConcept, col)} />
                  </td>
                ),
              )}
              <td className="bl15-num">{u.scan_count}</td>
              {/* `source_count`, NOT `scans.length + 1` — the server counts
                  byte-identical copies once and this renders that number. */}
              <td className="bl15-num">{u.source_count}</td>
              <td>
                <span
                  className={`bl15-state bl15-state-${state}`}
                  title={BL15_UNIT_STATE_NOTES[state]}
                >
                  {BL15_UNIT_STATE_LABELS[state] ?? state}
                </span>
              </td>
            </tr>,
            /* PROVENANCE ONE CLICK AWAY, and the summary is the measurement's own
               stem — a topic, never a claim about it. A spanning row keeps the
               drawer inside the table it describes rather than in a panel a reader
               has to correlate by eye. */
            <tr key={`${u.stem}-evidence`} className="bl15-evidence-row">
              <td colSpan={BL15_COLUMNS.length}>
                <details className="bl15-unit-disclosure">
                  <summary>
                    <span className="bl15-unit-summary">{u.stem}</span>
                  </summary>
                  <Bl15EvidenceDrawer unit={u} byConcept={byConcept} />
                </details>
              </td>
            </tr>,
          ];
        })}
      </tbody>
    </table>
  );
}

/**
 * One table cell. Three outcomes, and they are NOT interchangeable.
 *
 * `absent` says no source states it — which is different from a blank cell, and is
 * why it renders a word. `disputed` never shows a winner: `unresolved_reason` is
 * always `sources_disagree`, so the cell names the disagreement and the drawer
 * carries every reading.
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
  const shown = normalized === null || normalized === undefined ? e.raw_literal : String(normalized);
  const differs = shown !== e.raw_literal;
  return (
    <span className="bl15-value">
      {shown}
      {e.unit ? <span className="bl15-unit"> {e.unit}</span> : null}
      {/* THE LITERAL IS NEVER REPLACED. When a rule produced a cleaner reading the
          raw text stays beside it with the rule that produced it — `ffilter35` is
          the case this exists for. */}
      {differs && (
        <span className="bl15-raw">
          {BL15_COPY.rawLabel} <code>{e.raw_literal}</code>
          {e.normalization_rule ? ` · ${BL15_COPY.ruleLabel} ${e.normalization_rule}` : ''}
        </span>
      )}
    </span>
  );
}

/* ── conflicts ──────────────────────────────────────────────────────────── */

/**
 * Conflicts, grouped by kind and **never showing a chosen winner**.
 *
 * Every `Conflict.explanation` is rendered verbatim — it is written for a scientist
 * by `bl15/relate.py` and is required at construction. This component neither
 * paraphrases it nor supplies its own.
 *
 * The readings list is a `<ul>` over `readings`, with no assumption of two: a
 * three-source disagreement is the corpus's most instructive case and renders as
 * three rows here.
 */
function Conflicts({ byKind }: { byKind: ReturnType<typeof conflictsByKind> }) {
  const total = byKind.reduce((n, g) => n + g.conflicts.length, 0);
  if (total === 0) return null;
  return (
    <div className="bl15-block bl15-block-alert">
      <h4 className="bl15-block-title">
        <TriangleAlert size={14} strokeWidth={2.2} aria-hidden="true" />
        {BL15_COPY.conflictsTitle}
        <span className="bl15-count">{total}</span>
      </h4>
      <p className="bl15-lead">{BL15_COPY.conflictsLead}</p>
      {byKind.map((group) => (
        <div className="bl15-conflict-kind" key={group.kind}>
          <h5 className="bl15-conflict-kind-title">
            {conflictKindLabel(group.kind)}
            <span className="bl15-count">{group.conflicts.length}</span>
          </h5>
          <ul className="bl15-conflict-list">
            {group.conflicts.map(({ conflict, stem }, i) => (
              <li key={`${conflict.kind}-${conflict.subject}-${i}`}>
                <ConflictView conflict={conflict} stem={stem} />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function ConflictView({ conflict, stem }: { conflict: Bl15Conflict; stem: string | null }) {
  return (
    <div className="bl15-conflict">
      <p className="bl15-conflict-subject">
        <span className="bl15-conflict-label">{conflict.subject}</span>
        {stem && <span className="bl15-conflict-stem">{stem}</span>}
      </p>
      {/* The server's own sentence, verbatim. */}
      <p className="bl15-conflict-explanation">{conflict.explanation}</p>
      <ul className="bl15-readings">
        {conflict.readings.map((r, i) => (
          <li key={`${r.source_path}-${r.locator}-${i}`}>
            <span className="bl15-reading-value">{r.value}</span>
            <span className="bl15-reading-source">
              {r.source_path}
              <span className="bl15-reading-locator">{r.locator}</span>
              <span className="bl15-reading-type">{sourceTypeLabel(r.source_type)}</span>
            </span>
          </li>
        ))}
      </ul>
      {/* Stated, not implied: nothing chose between these. */}
      <p className="bl15-conflict-unresolved">
        Unresolved — <code>{conflict.unresolved_reason}</code>. No source is preferred here.
      </p>
    </div>
  );
}

/* ── mapping review ────────────────────────────────────────────────────── */

/**
 * The registry's five statuses, **as five outcomes and not as a progress bar**.
 *
 * `coverage()` measures 1 deterministic + 4 normalized + 15 needs_domain_review +
 * 24 not_expressible + 1 blocked_by_build = 45 (~~2 / 4 / 14~~ — corrected 2026-09-16
 * when `acquisition_method` moved to `needs_domain_review`; this transcription was
 * missed by that commit's own sweep). A bar over "fields mapped" would render 5/45 as
 * 89% failure when 24 of those are a correct description of the official schema's
 * coverage and 15 are a question for a domain owner.
 *
 * ── A CONTRACT LIMIT, STATED RATHER THAN WORKED AROUND ─────────────────────
 *
 * This section groups the REGISTRY by status, which is corpus-level. It cannot
 * group per-measurement CANDIDATES by status, because `SemanticCandidate.to_state()`
 * carries no `concept` and no `status` — only `target_field_path`, which is `null`
 * for every `not_expressible` concept and so cannot distinguish them. Joining a
 * candidate to its registry status needs a field the contract does not have, and
 * inventing one is forbidden.
 */
function MappingReview({ review }: { review: Bl15CorpusReview }) {
  const { coverage, concepts } = review.mapping;
  return (
    <div className="bl15-block">
      <h4 className="bl15-block-title">{BL15_COPY.mappingTitle}</h4>
      <p className="bl15-lead">{BL15_COPY.mappingLead}</p>
      <ul className="bl15-status-list">
        {BL15_MAPPING_STATUSES.map((status) => {
          const rows = conceptsWithStatus(concepts, status);
          const count = coverage[status] ?? rows.length;
          return (
            <li key={status}>
              <details className="bl15-disclosure">
                <summary>
                  <h5 className="bl15-status-title">
                    {BL15_STATUS_LABELS[status] ?? statusLabel(status)}
                    <span className="bl15-count">
                      {count} of {coverage.concepts_total}
                    </span>
                  </h5>
                </summary>
                <ul className="bl15-concepts">
                  {rows.map((c) => (
                    <li key={c.concept}>
                      <p className="bl15-concept-head">
                        <span className="bl15-concept-name">{conceptLabel(c.concept)}</span>
                        {c.official_path && <code className="bl15-path">{c.official_path}</code>}
                        {c.rule && <span className="bl15-rule">rule: {c.rule}</span>}
                      </p>
                      {/* The registry's own sentence, verbatim. */}
                      <p className="bl15-concept-reason">{c.reason}</p>
                      {/* `DEC-41` — WHERE THE INFORMATION LANDS, which is a
                          different question from whether a value may travel.
                          Without this line a scientist reading `not_expressible`
                          has no way to tell "the schema has no place for this" from
                          "this is kept, in the companion" — and the second is what
                          the hierarchy actually decided for all twelve of them.

                          BOTH THE WORDS AND THE NUMBER, because a bare rank is
                          something a reader has to look up. The words are the
                          server's `placement_name`, rendered verbatim: no label is
                          re-authored here, and nothing on this line is a schema path
                          or a module path. */}
                      {c.placement_name && (
                        <p className="bl15-concept-extra">
                          Where this information lands: {c.placement_name} (level{' '}
                          {c.placement_level}).
                        </p>
                      )}
                      {/* THE OPEN SUBSET, NEVER THE WHOLE LIST. Twelve of the twenty
                          packet questions closed on 2026-09-17, so showing
                          `domain_questions` here would tell a scientist to wait for
                          an answer that has arrived. */}
                      {c.unresolved_questions && c.unresolved_questions.length > 0 && (
                        <p className="bl15-concept-extra">
                          Still waiting on a domain answer:{' '}
                          {c.unresolved_questions.join(', ')}.
                        </p>
                      )}
                      {c.allowed_values.length > 0 && (
                        <p className="bl15-concept-extra">
                          The schema allows: {c.allowed_values.join(', ')}.
                        </p>
                      )}
                      {c.requires_siblings.length > 0 && (
                        <p className="bl15-concept-extra">
                          Satisfying this is not sufficient on its own — the schema also
                          requires {c.requires_siblings.join(', ')}.
                        </p>
                      )}
                      {c.candidate_homes.length > 0 && (
                        <p className="bl15-concept-extra">
                          Candidate home, named and not applied:{' '}
                          {c.candidate_homes.join(', ')}.
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </details>
            </li>
          );
        })}
      </ul>
      {coverage.not_examined > 0 && (
        <p className="bl15-note" role="note">
          {coverage.not_examined} concept
          {coverage.not_examined === 1 ? '' : 's'} in this corpus&rsquo;s vocabulary have not
          been examined by the registry at all.
        </p>
      )}
    </div>
  );
}

/* ── what was left out ─────────────────────────────────────────────────── */

/**
 * The complete `unattached` and `refused` lists.
 *
 * `Relationships.unattached`'s own docstring calls it *"as load-bearing as
 * `units`"* — a reconstruction reporting only what it assembled would leave a
 * scientist unable to see what it left out, which is `HIST-004`'s banned pattern one
 * layer down. Each group keeps the SERVER's reason rather than a label from here.
 */
function LeftOut({
  unattached,
  refused,
}: {
  unattached: ReturnType<typeof unattachedByType>;
  refused: Bl15CorpusReview['inventory']['refused'];
}) {
  if (unattached.length === 0 && refused.length === 0) return null;
  return (
    <div className="bl15-block">
      <details className="bl15-disclosure">
        <summary>
          <h4 className="bl15-block-title">{BL15_COPY.leftOutTitle}</h4>
        </summary>
        {unattached.map((g) => (
          <div className="bl15-leftout" key={g.source_type}>
            <h5 className="bl15-leftout-title">
              {sourceTypeLabel(g.source_type)}
              <span className="bl15-count">{g.paths.length}</span>
            </h5>
            {/* The server's reason, verbatim — a README is unattached because it
                belongs to the whole import, which is a different fact from a
                processed product naming no measurement. */}
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
      </details>
    </div>
  );
}

/* ── the evidence drawer, exported for the unit detail ──────────────────── */

/**
 * Per-field provenance for ONE measurement, scientist-readable and never raw JSON.
 *
 * Each row is *filename + what it says*, from `Reading`/`SourceEvidence`'s
 * `source_path`, `locator` and the literal. The reference basis is shown when a
 * source states one (`potential_reference_basis`); it is not defaulted, because a
 * potential without its reference is not a measurement a scientist can use and a
 * guessed basis would be worse than a missing one.
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
  return (
    <div className="bl15-evidence">
      <h5 className="bl15-evidence-title">{BL15_COPY.evidenceTitle}</h5>
      {concepts.length === 0 ? (
        <p className="bl15-absent">
          No source in this import states a mapped value for this measurement.
        </p>
      ) : (
        <ul className="bl15-evidence-list">
          {concepts.map((concept) => {
            const hits = byConcept?.get(concept) ?? [];
            return (
              <li key={concept}>
                <p className="bl15-evidence-concept">{conceptLabel(concept)}</p>
                {concept === 'potential_magnitude' && basis && (
                  <p className="bl15-evidence-basis">
                    Reference basis: {basis.raw_literal}
                  </p>
                )}
                <ul className="bl15-evidence-sources">
                  {hits.map((e) => (
                    <li key={e.evidence_id}>
                      <span className="bl15-evidence-file">{e.source_path}</span>
                      <span className="bl15-evidence-says">
                        says <strong>{e.raw_literal}</strong>
                        {e.normalized_value !== null && e.normalized_value !== undefined
                          ? ` · ${BL15_COPY.normalizedLabel} ${String(e.normalized_value)}${
                              e.unit ? ` ${e.unit}` : ''
                            }`
                          : ''}
                      </span>
                      <span className="bl15-evidence-where">
                        {e.locator} · {sourceTypeLabel(e.source_type)}
                      </span>
                    </li>
                  ))}
                </ul>
              </li>
            );
          })}
        </ul>
      )}
      {/* Structural provenance a unit DOES carry, kept beside the values so a
          scientist can see the measurement's whole warrant in one place. */}
      <p className="bl15-evidence-structure">
        {unit.source_count} distinct source{unit.source_count === 1 ? '' : 's'} support this
        measurement, counting byte-identical copies once.
        {unit.duplicate_copies.length + unit.suppressed_duplicate_acquisitions.length > 0
          ? ` ${
              unit.duplicate_copies.length + unit.suppressed_duplicate_acquisitions.length
            } byte-identical cop${
              unit.duplicate_copies.length + unit.suppressed_duplicate_acquisitions.length === 1
                ? 'y is'
                : 'ies are'
            } kept but not counted as extra witnesses.`
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
