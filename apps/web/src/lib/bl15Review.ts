/**
 * BL15-2 corpus review — the wire types and every derivation over them.
 *
 * ── THESE TYPES MIRROR COMMITTED `to_state()` METHODS AND NOTHING ELSE ──────
 *
 * Each interface below names the Python dataclass it mirrors. **No field here is
 * invented.** Where a field a surface would want does not exist, that is recorded
 * in the type's own comment rather than filled in — see `MEASUREMENT UNITS CARRY
 * NO SCIENTIFIC VALUE` below, which is the constraint that shapes this whole
 * module.
 *
 *   `Bl15ArchiveInventory`  <- `bl15/inventory.py`   `ArchiveInventory.to_state`
 *   `Bl15SourceRecordless`  --  there is no such type, deliberately: see below
 *   `Bl15Relationships`     <- `bl15/relate.py`      `Relationships.to_state`
 *   `Bl15MeasurementUnit`   <- `bl15/relate.py`      `MeasurementUnit.to_state`
 *   `Bl15SampleGroup`       <- `bl15/relate.py`      `SampleGroup.to_state`
 *   `Bl15Conflict`          <- `bl15/relate.py`      `Conflict.to_state`
 *   `Bl15Reading`           <- `bl15/relate.py`      `Reading.to_state`
 *   `Bl15MacroBlock`        <- `bl15/relate.py`      `MacroBlock.to_state`
 *   `Bl15ScanChild`         <- `bl15/relate.py`      `ScanChild.to_state`
 *   `Bl15SourceEvidence`    <- `bl15/evidence.py`    `SourceEvidence.to_state`
 *   `Bl15ConceptMapping`    <- `bl15/mapping.py`     `ConceptMapping.to_state`
 *   `Bl15MappingCoverage`   <- `bl15/mapping.py`     `coverage()`
 *
 * ── THE ONE THING NOT YET COMMITTED IS THE CONTAINER ───────────────────────
 *
 * `Bl15CorpusReview` groups those five payloads. ~~No route emits it yet — the archive
 * source kind is another slice's step 1, and `historical_import.SOURCE_KINDS` today
 * holds only `reference` and `synthetic_fixture`~~ — **all of that is false and closed
 * as of 2026-09-16.** `historical_import._corpus_review` serves this shape.
 *
 * ONE MEMBER IS BOUNDED AND THE BOUND IS WORTH KNOWING: `evidence` is NOT the whole
 * evidence set, which is ~500,000 items at the real corpus's cardinality. It is the six
 * concepts the five scientific columns read (`REVIEW_COLUMN_CONCEPTS` on the server),
 * for readings that name a measurement, capped at four DISTINCT literals per
 * measurement-and-concept — a cap on distinct literals rather than on count, so a
 * `disputed` cell can never be thinned into a `read` one. `evidence_readings_dropped`
 * carries what the cap removed. The container is therefore
 * the single shape here that is a proposal rather than a mirror, and it is
 * deliberately nothing but the union of the committed ones: every member is a
 * verbatim `to_state()` output, so a route can satisfy it by serialising objects it
 * already builds.
 *
 * ── MEASUREMENT UNITS CARRY NO SCIENTIFIC VALUE, AND THAT IS ENFORCED ──────
 *
 * `apps/api/tests/test_bl15_relate.py::test_nothing_in_the_output_carries_a_scientific_value`
 * pins `MeasurementUnit.to_state()`'s exact key set, and its docstring says why:
 * *"the tempting next step is to hang a parsed potential off a unit, and that would
 * put an unmapped value one step from a record with no registry between."*
 *
 * So a unit has no sample, medium, state, filter or potential. Those live in
 * `Bl15SourceEvidence`, keyed by `measurement_stem` + `concept`, and this module
 * joins them with `readingsByStem`. The join can yield **zero, one, or many**
 * readings per concept, and all three are real states the surface must tell apart —
 * many readings is how a disagreement looks before anything adjudicates it.
 */

/* ── mirrors of the committed contracts ─────────────────────────────────── */

/** `relate.Reading` — ONE source's account of a disputed subject, verbatim. */
export interface Bl15Reading {
  source_path: string;
  locator: string;
  value: string;
  source_type: string;
}

/**
 * `relate.Conflict`.
 *
 * `readings` may hold **three or more** and the contract says so in prose: for the
 * `29`-`32` group the macro, the internal declaration and the filename are three
 * sources. A surface built for exactly two would be wrong about the corpus's most
 * instructive case, so nothing here indexes `[0]` and `[1]`.
 *
 * `explanation` is written for a scientist by the server and is REQUIRED at
 * construction (`Conflict.__post_init__` raises without one). It is rendered
 * verbatim; this module never paraphrases it and never writes its own.
 */
export interface Bl15Conflict {
  kind: string;
  subject: string;
  readings: Bl15Reading[];
  unresolved_reason: string;
  explanation: string;
}

/** `relate.MacroBlock` — a macro declaring it is about to write a measurement. */
export interface Bl15MacroBlock {
  macro_path: string;
  block_index: number;
  declared_target: string;
  /** INTENT and FACT are both recorded because in this corpus they differ. */
  acquired: boolean;
}

/** `relate.ScanChild` — a `.dat` export. **Never a Run of its own.** */
export interface Bl15ScanChild {
  path: string;
  scan_index: number | null;
}

/** `relate.MeasurementUnit` — the candidate Run unit. Carries no scientific value. */
export interface Bl15MeasurementUnit {
  stem: string;
  acquisition_path: string;
  source_type: string;
  /** DERIVED server-side from `source_type`. `false` for alignment and standards. */
  run_candidate: boolean;
  legacy_number: number | null;
  /** The sample/electrode instance CANDIDATE. `needs_domain_review`, not a fact. */
  group_token: string | null;
  scan_dir: string | null;
  scans: Bl15ScanChild[];
  /** **Zero is legitimate** — two real measurements have none. */
  scan_count: number;
  duplicate_copies: string[];
  suppressed_duplicate_acquisitions: string[];
  declared_by: Bl15MacroBlock[];
  processed_products: string[];
  note_rows: Record<string, unknown>[];
  internal_declaration: string | null;
  conflicts: Bl15Conflict[];
  /**
   * Distinct supporting sources, **counting byte-identical copies ONCE**.
   *
   * RENDER THIS, never `scans.length + 1`. The server's own docstring: *"the same
   * bytes in two places is one witness, and a count that included them would
   * inflate a scientist's confidence for a filesystem reason."* On the committed
   * fixture the two differ 7 against 4 for a single unit.
   */
  source_count: number;
}

/**
 * `relate.SampleGroup`.
 *
 * `group_token` is `null` for the bucket holding measurements with no token at all —
 * `relate._groups` emits it and sorts it last, and
 * `test_a_stem_with_no_group_token_is_grouped_under_None_not_a_placeholder` pins that
 * it is not given a placeholder. The surface must name that bucket in words rather
 * than render an empty heading.
 */
export interface Bl15SampleGroup {
  group_token: string | null;
  stems: string[];
  measurement_count: number;
  legacy_low: number | null;
  legacy_high: number | null;
  /** A BROKEN range is the signal that the token does not mean what grouping assumes. */
  contiguous: boolean;
}

/** `relate.Relationships`. */
export interface Bl15Relationships {
  units: Bl15MeasurementUnit[];
  groups: Bl15SampleGroup[];
  corpus_conflicts: Bl15Conflict[];
  /** `{archive_path, source_type, reason}` — as load-bearing as `units`. */
  unattached: { archive_path: string; source_type: string; reason: string }[];
  /** Which inputs were supplied, so "no macro declared this" is distinguishable
   *  from "no macro was ever offered". */
  inputs_present: string[];
  unit_count: number;
  conflict_count: number;
}

/**
 * `inventory.ArchiveInventory.to_state`.
 *
 * **`entries` IS NOT ON THE WIRE.** `to_state()` serialises `entry_count` and omits
 * the per-file list entirely. So no client can render a complete file manifest, and
 * this surface does not pretend to: what it discloses instead is the complete
 * `refused` list and the complete `unattached` list, which is the "what was left
 * out" half that `Relationships`' own docstring calls as load-bearing as `units`.
 */
export interface Bl15ArchiveInventory {
  root_label: string;
  entry_count: number;
  total_bytes: number;
  refused: { archive_path: string; reason: string; detail?: string }[];
  /** Set when the walk stopped early — the inventory itself is INCOMPLETE. */
  truncated_reason: string | null;
  duplicate_group_count: number;
}

/** `evidence.SourceEvidence.to_state` — every field, including the empty ones. */
export interface Bl15SourceEvidence {
  evidence_id: string;
  source_path: string;
  source_type: string;
  locator: string;
  /** **VERBATIM AND NEVER REPLACED.** `ffilter35` stays `ffilter35`. */
  raw_literal: string;
  concept: string;
  parser_id: string;
  determinism: string;
  scope: string;
  /** The cleaned reading, when a stored rule produced one. `null` otherwise. */
  normalized_value: unknown;
  unit: string | null;
  /** Which named rule produced `normalized_value`. Required when normalised. */
  normalization_rule: string | null;
  profile_id: string | null;
  profile_version: string | null;
  timestamp_utc: string | null;
  measurement_stem: string | null;
}

/** `mapping.ConceptMapping.to_state`. */
export interface Bl15ConceptMapping {
  concept: string;
  status: string;
  official_path: string | null;
  /** WHY this status, in a sentence a scientist reads. Rendered verbatim. */
  reason: string;
  rule: string | null;
  requires_siblings: string[];
  allowed_values: string[];
  candidate_homes: string[];
  proposable: boolean;
  /**
   * `DEC-41`'s placement level, 1-4 — WHERE this concept's information lands.
   *
   * **A PLACEMENT IS NOT A STATUS, and the two are served side by side precisely
   * because they answer different questions.** `status` says whether a value may
   * TRAVEL toward a candidate; this says whether the information has a HOME at all.
   * A `not_expressible` concept at level 4 is not a dead end — it lands in the
   * structured ISAAC Extended Context companion, which is the whole point of the
   * hierarchy.
   *
   * DERIVED ON THE SERVER from the paths the registry declares, never stated by a
   * registry row, so it cannot disagree with `official_path`. Optional here for the
   * reason every added mirror member is: a persisted session document written before
   * the server published it carries neither key.
   */
  placement_level?: number;
  /**
   * The level's own words. Rendered VERBATIM and never re-authored here.
   *
   * Both the number and the words are published because a bare integer on a screen
   * is a rank a reader has to look up — the server's own reasoning, kept.
   */
  placement_name?: string;
  /** Packet question ids touching this concept. */
  domain_questions?: string[];
  /**
   * The subset of `domain_questions` that are STILL OPEN.
   *
   * Separate from `domain_questions` because twelve of the twenty closed on
   * 2026-09-17: a surface reading the full list would keep telling a scientist to
   * wait for an answer that has already arrived.
   */
  unresolved_questions?: string[];
}

/**
 * `mapping.DomainQuestion.to_state()` — one packet question and its disposition.
 *
 * MIRRORED FROM THE SERVER'S ACTUAL OUTPUT, not from what a question "should" carry:
 * there is no `answer` member and no `closed_by`. What closed a question is in
 * `note`, which is prose a scientist reads, and `disposition` is the vocabulary.
 */
export interface Bl15DomainQuestion {
  question_id: string;
  subject: string;
  disposition: string;
  /** WHAT closed it, or what narrowed it. Rendered verbatim. */
  note: string;
  is_open: boolean;
}

/** `mapping.placement_coverage()` — how many concepts land at each level. */
export interface Bl15PlacementCoverage {
  '1': number;
  '2': number;
  '3': number;
  '4': number;
  open_domain_questions: number;
  concepts_with_an_open_question: number;
}

/** `mapping.coverage()` — counts per status plus the unexamined remainder. */
export interface Bl15MappingCoverage {
  deterministic: number;
  normalized: number;
  needs_domain_review: number;
  not_expressible: number;
  blocked_by_build: number;
  examined: number;
  not_examined: number;
  concepts_total: number;
}

/** The container — the one shape here no route emits yet. See the header. */
export interface Bl15CorpusReview {
  inventory: Bl15ArchiveInventory;
  relationships: Bl15Relationships;
  evidence: Bl15SourceEvidence[];
  mapping: {
    coverage: Bl15MappingCoverage;
    concepts: Bl15ConceptMapping[];
    /** `mapping.TEMPERATURE_ABSENT_REASON`, served rather than re-authored. */
    temperature_absent_reason: string;
    /** `mapping.ASSETS_BLOCKED_REASON`. */
    assets_blocked_reason: string;
    /** `mapping.CYCLING_STATE_NO_FIELD_REASON`. */
    cycling_state_no_field_reason?: string;
    /**
     * `mapping.placement_coverage()` — `DEC-41` / `CTX-001`.
     *
     * Served BESIDE `coverage` and never folded into it, which is the server's own
     * decision and is preserved here rather than reinterpreted: a status count
     * answers "can a value travel" and a placement count answers "does the
     * information have a home". Both sum to the same 45 concepts and mean different
     * things, so a surface that added them would be double-counting.
     */
    placement?: Bl15PlacementCoverage;
    /** `level -> the level's own words`, from `mapping.PLACEMENT_NAMES`. */
    placement_levels?: Record<string, string>;
    /** All twenty packet questions, closed ones included. */
    domain_questions?: Bl15DomainQuestion[];
    /** The ids still open — eight of the twenty as of 2026-09-17. */
    open_domain_questions?: string[];
    /**
     * Concepts marked `needs_domain_review` with no packet question behind them.
     *
     * Named by the server rather than left to be subtracted, which is why it is
     * mirrored rather than derived here.
     */
    needs_review_without_a_question?: string[];
  };
}

/* ── the five mapping statuses, as the registry names them ───────────────── */

export const BL15_MAPPING_STATUSES = [
  'deterministic',
  'normalized',
  'needs_domain_review',
  'not_expressible',
  'blocked_by_build',
] as const;

export type Bl15MappingStatus = (typeof BL15_MAPPING_STATUSES)[number];

/* ── the concepts this surface's table columns read ──────────────────────── */

/**
 * The concept id behind each scientific column, from `bl15/evidence.py`.
 *
 * Named as constants rather than inlined so a concept rename in the contract
 * produces one failure here instead of a silently blank column. `state` reads
 * `cycling_state` first and falls back to `before_after_state`, because the registry
 * treats them as separate concepts and a unit may carry either.
 */
export const BL15_COLUMN_CONCEPTS = {
  sample: ['sample_name'],
  medium: ['electrolyte_or_medium'],
  state: ['cycling_state', 'before_after_state'],
  filter: ['filter'],
  potential: ['potential_magnitude'],
} as const;

export type Bl15ColumnId = keyof typeof BL15_COLUMN_CONCEPTS;

/* ── derivations ────────────────────────────────────────────────────────── */

/**
 * Evidence indexed `stem -> concept -> readings`.
 *
 * Evidence with a `null` `measurement_stem` is beamtime-scope (a README, a notes
 * header) and is deliberately NOT folded into any unit: attributing an
 * import-wide statement to one measurement would be this client inventing a
 * relationship that `relate` declined to make.
 */
export function readingsByStem(
  evidence: readonly Bl15SourceEvidence[],
): Map<string, Map<string, Bl15SourceEvidence[]>> {
  const out = new Map<string, Map<string, Bl15SourceEvidence[]>>();
  for (const e of evidence) {
    if (!e.measurement_stem) continue;
    let byConcept = out.get(e.measurement_stem);
    if (!byConcept) {
      byConcept = new Map();
      out.set(e.measurement_stem, byConcept);
    }
    const list = byConcept.get(e.concept);
    if (list) list.push(e);
    else byConcept.set(e.concept, [e]);
  }
  return out;
}

/** What one column holds for one unit. Three outcomes, all of them real. */
export type Bl15Cell =
  /** No source in this import states this concept for this measurement. */
  | { state: 'absent' }
  /** Exactly one source states it. */
  | { state: 'read'; evidence: Bl15SourceEvidence }
  /** Several sources state it and they do not agree — never adjudicated here. */
  | { state: 'disputed'; evidence: Bl15SourceEvidence[] };

/**
 * Read one column for one unit.
 *
 * `disputed` fires only on genuinely DIFFERENT literals: two sources stating the
 * same thing corroborate rather than disagree, and calling that a dispute would put
 * a warning on the corpus's best-evidenced values.
 */
export function cellFor(
  byConcept: Map<string, Bl15SourceEvidence[]> | undefined,
  column: Bl15ColumnId,
): Bl15Cell {
  if (!byConcept) return { state: 'absent' };
  for (const concept of BL15_COLUMN_CONCEPTS[column]) {
    const hits = byConcept.get(concept);
    if (!hits || hits.length === 0) continue;
    const distinct = new Set(hits.map((h) => h.raw_literal));
    if (hits.length > 1 && distinct.size > 1) return { state: 'disputed', evidence: hits };
    return { state: 'read', evidence: hits[0] };
  }
  return { state: 'absent' };
}

/**
 * The review state of one unit.
 *
 * **THERE IS NO `ready` STATE, AND ITS ABSENCE IS THE POINT.** The integration
 * design's §5 is that a candidate Run from this corpus *cannot be export-ready* —
 * `context.temperature_K` is required and the corpus states no temperature,
 * `record_type: evidence` requires `descriptors`, and `assets[]` requires a `sha256`
 * this build never computes. A bucket labelled "Ready" would be read as
 * export-ready, so the states below name what was OBSERVED rather than how far
 * along something is.
 */
export type Bl15UnitState =
  /** Not a run candidate: alignment or a standard/reference. Never offered as a Run. */
  | 'reference'
  /** At least one conflict touches it. */
  | 'conflict'
  /** A run candidate no source in this import states any mapped value for. */
  | 'no_values'
  /** A run candidate with values read and nothing disagreeing. */
  | 'values_read';

export function unitState(
  unit: Bl15MeasurementUnit,
  byConcept: Map<string, Bl15SourceEvidence[]> | undefined,
): Bl15UnitState {
  if (!unit.run_candidate) return 'reference';
  if (unit.conflicts.length > 0) return 'conflict';
  const anyValue = (Object.keys(BL15_COLUMN_CONCEPTS) as Bl15ColumnId[]).some(
    (c) => cellFor(byConcept, c).state !== 'absent',
  );
  return anyValue ? 'values_read' : 'no_values';
}

/** One line of the digest: a label, a number, and where the number came from. */
export interface Bl15DigestRow {
  id: string;
  label: string;
  value: number;
  /** The payload expression this was derived from. Rendered under disclosure. */
  derivedFrom: string;
}

/**
 * The corpus digest — **every number derived from the payload, none a literal.**
 *
 * `HIST-004` bans `Upload -> Spinner -> Mysterious JSON`, and a 1,192-row table is
 * its sibling: a manifest a scientist cannot audit is the same as no manifest. So
 * the first thing shown is this, and the complete `refused` and `unattached` lists
 * sit behind disclosure.
 *
 * `derivedFrom` exists because `CLAUDE.md` §11 records four surfaces that shipped a
 * number they had not derived from what they claimed to describe. Stating the
 * expression beside the number makes each one checkable by a reader.
 */
export function corpusDigest(review: Bl15CorpusReview): Bl15DigestRow[] {
  const { inventory: inv, relationships: rel } = review;
  const units = rel.units;
  const macroPaths = new Set<string>();
  let declarations = 0;
  let scans = 0;
  let processed = 0;
  let noteRows = 0;
  let copies = 0;
  for (const u of units) {
    scans += u.scan_count;
    processed += u.processed_products.length;
    noteRows += u.note_rows.length;
    copies += u.duplicate_copies.length + u.suppressed_duplicate_acquisitions.length;
    for (const b of u.declared_by) {
      macroPaths.add(b.macro_path);
      declarations += 1;
    }
  }
  const candidates = units.filter((u) => u.run_candidate).length;

  const rows: Bl15DigestRow[] = [
    {
      id: 'sources',
      label: 'Sources found in the archive',
      value: inv.entry_count,
      derivedFrom: 'inventory.entry_count',
    },
    {
      id: 'measurements',
      label: 'Measurements reconstructed',
      value: rel.unit_count,
      derivedFrom: 'relationships.unit_count',
    },
    {
      id: 'candidates',
      label: 'Of those, offerable as Runs',
      value: candidates,
      derivedFrom: 'count of units where run_candidate is true',
    },
    {
      id: 'reference',
      label: 'Alignment and standards (never offered as Runs)',
      value: units.length - candidates,
      derivedFrom: 'count of units where run_candidate is false',
    },
    {
      id: 'groups',
      label: 'Sample groups',
      value: rel.groups.length,
      derivedFrom: 'relationships.groups.length',
    },
    {
      id: 'scans',
      label: 'Scan exports attached to a measurement',
      value: scans,
      derivedFrom: 'sum of units[].scan_count',
    },
    {
      id: 'macros',
      label: 'Macros that declared a measurement',
      value: macroPaths.size,
      derivedFrom: 'distinct units[].declared_by[].macro_path',
    },
    {
      id: 'declarations',
      label: 'Measurements those macros declared',
      value: declarations,
      derivedFrom: 'count of units[].declared_by[] entries',
    },
    {
      id: 'processed',
      label: 'Processed products',
      value: processed,
      derivedFrom: 'sum of units[].processed_products.length',
    },
    {
      id: 'notes',
      label: 'Human note rows cited',
      value: noteRows,
      derivedFrom: 'sum of units[].note_rows.length',
    },
    {
      id: 'duplicates',
      label: 'Duplicate-content groups',
      value: inv.duplicate_group_count,
      derivedFrom: 'inventory.duplicate_group_count',
    },
    {
      id: 'copies',
      label: 'Byte-identical copies kept but not counted as witnesses',
      value: copies,
      derivedFrom:
        'sum of units[].duplicate_copies.length + suppressed_duplicate_acquisitions.length',
    },
    {
      id: 'conflicts',
      label: 'Disagreements between sources',
      value: rel.conflict_count,
      derivedFrom: 'relationships.conflict_count',
    },
    {
      id: 'unattached',
      label: 'Sources attached to no measurement',
      value: rel.unattached.length,
      derivedFrom: 'relationships.unattached.length',
    },
    {
      id: 'refused',
      label: 'Sources the archive walk refused',
      value: inv.refused.length,
      derivedFrom: 'inventory.refused.length',
    },
  ];
  return rows;
}

/** Conflicts by kind, across units AND the corpus-level ones. Sorted, stable. */
export function conflictsByKind(
  rel: Bl15Relationships,
): { kind: string; conflicts: { conflict: Bl15Conflict; stem: string | null }[] }[] {
  const out = new Map<string, { conflict: Bl15Conflict; stem: string | null }[]>();
  const push = (conflict: Bl15Conflict, stem: string | null) => {
    const list = out.get(conflict.kind);
    if (list) list.push({ conflict, stem });
    else out.set(conflict.kind, [{ conflict, stem }]);
  };
  for (const u of rel.units) for (const c of u.conflicts) push(c, u.stem);
  for (const c of rel.corpus_conflicts) push(c, null);
  return [...out.entries()]
    .map(([kind, conflicts]) => ({ kind, conflicts }))
    .sort((a, b) => a.kind.localeCompare(b.kind));
}

/** Unattached sources grouped by `source_type`, each keeping the server's reason. */
export function unattachedByType(
  rel: Bl15Relationships,
): { source_type: string; reason: string; paths: string[] }[] {
  const out = new Map<string, { reason: string; paths: string[] }>();
  for (const u of rel.unattached) {
    const hit = out.get(u.source_type);
    if (hit) hit.paths.push(u.archive_path);
    else out.set(u.source_type, { reason: u.reason, paths: [u.archive_path] });
  }
  return [...out.entries()]
    .map(([source_type, v]) => ({ source_type, ...v }))
    .sort((a, b) => a.source_type.localeCompare(b.source_type));
}

/** Registry entries for one status, in concept order. */
export function conceptsWithStatus(
  concepts: readonly Bl15ConceptMapping[],
  status: string,
): Bl15ConceptMapping[] {
  return concepts
    .filter((c) => c.status === status)
    .sort((a, b) => a.concept.localeCompare(b.concept));
}
