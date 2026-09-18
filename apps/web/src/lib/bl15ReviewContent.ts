/**
 * BL15-2 corpus review — the copy this surface authors, and ONLY that.
 *
 * ── WHAT IS NOT HERE, AND MUST NEVER BE ────────────────────────────────────
 *
 * Every sentence that EXPLAINS a server decision is rendered from the payload,
 * never from this file:
 *
 *   · `Conflict.explanation`      — written for a scientist by `bl15/relate.py`
 *   · `ConceptMapping.reason`     — why a concept has the status it has
 *   · `unattached[].reason`       — why a source attached to no measurement
 *   · `TEMPERATURE_ABSENT_REASON` / `ASSETS_BLOCKED_REASON`
 *
 * `HistoricalImport.tsx`'s own header records the rule this follows — *"ONE
 * VOCABULARY, AND IT IS THE SERVER'S … A second copy in the browser would be free
 * to drift from the operation that enforces it"*. So what remains below is column
 * headings, category names and screen furniture: text with no claim in it that the
 * server is also making.
 */

/** Screen furniture for the corpus review block. */
export const BL15_COPY = {
  digestTitle: 'What This Archive Contains',
  digestLead:
    'Counted from the archive itself. Every number below is derived from this import; open a row to see the expression it came from.',
  /**
   * The manifest sentence, and it states an ABSENCE rather than offering a link.
   *
   * `ArchiveInventory.to_state()` serialises `entry_count` and omits `entries`, so
   * no per-file list reaches the browser and this surface must not imply one is a
   * click away. What it can show completely, it does.
   */
  manifestNote:
    'A complete file-by-file list is not part of this report. What is listed in full is what was left out: every source attached to no measurement, and every source the archive walk refused.',
  groupsTitle: 'Measurements by Sample',
  groupsLead:
    'Grouped by the second filename token. Whether that token always means the sample or electrode instance is an open question for a domain owner, not something this import established.',
  ungroupedLabel: 'No sample token',
  ungroupedNote:
    'These measurements carry no second numeric token, so no sample grouping can be read from their names.',
  contiguousNote:
    'Legacy numbers form an unbroken run with no other group inside it — corroboration for the grouping, not proof of it.',
  brokenNote:
    'Legacy numbers interleave with another group. That is the signal that the token may not mean the sample instance.',
  /* Both of these were hardcoded at the call site until
     `casing-registers.test.tsx` §3 caught them — every other title on this
     surface already came from here, so the two literals were an inconsistency
     rather than a deliberate register choice. */
  leftOutTitle: 'What This Import Left Out',
  refusedTitle: 'Refused by the Archive Walk',
  conflictsTitle: 'Where Sources Disagree',
  conflictsLead:
    'Nothing here has been adjudicated. Every reading each source gave is kept, and no source is preferred.',
  mappingTitle: 'What the Official Schema Can Take',
  mappingLead:
    'Each concept this corpus states, and what the official ISAAC schema can do with it. All five outcomes below are final answers, not stages.',
  ceilingTitle: 'What Cannot Be Finished Here',
  ceilingLead:
    'Three requirements of the official schema that no source in this corpus can satisfy. This is stated up front because it does not change with review.',
  /*
   * `CTX-004` — the `DEC-41` level-4 block on the corpus review.
   *
   * IT NAMES THE LEVEL, and that is the point of the parenthetical rather than
   * decoration: `MappingReview` directly above renders "Where this information
   * lands: ISAAC Extended Context (level 4)" on each concept, so a reader who has
   * just met that phrase meets the SAME two words again over the block that says how
   * much landed there. Dropping "(level 4)" would break the only link between the two.
   *
   * IT IS TITLE CASE like every sibling in this object, and it deliberately does NOT
   * say "additional metadata", "extra fields" or "other values": each of those would
   * imply a field, and a level-4 entry is defined by the schema having none.
   */
  extendedContextTitle: 'Extended Context (Level 4)',
  extendedContextLead:
    'Statements this archive made that the official ISAAC record has no field for. ' +
    'Each one keeps the source’s own words, which source they came from, and where ' +
    'in it.',
  extendedContextNoneLeftOut:
    'Every level-4 statement this reading found is in the companion. Nothing was ' +
    'left out.',
  evidenceTitle: 'Supporting sources',
  searchLabel: 'Search measurements',
  searchPlaceholder: 'Legacy number, sample, filename…',
  filterLabel: 'Show',
  noMatches: 'No measurement in this import matches that search and filter.',
  disputedCell: 'sources disagree',
  absentCell: 'not stated',
  rawLabel: 'as written',
  normalizedLabel: 'read as',
  ruleLabel: 'rule',
  sourcesColumnNote:
    'Distinct supporting sources, counting byte-identical copies once.',
} as const;

/** Column headings for the measurements table. */
export const BL15_COLUMNS = [
  { id: 'legacy', label: 'Legacy #' },
  { id: 'sample', label: 'Sample' },
  { id: 'medium', label: 'Medium' },
  { id: 'state', label: 'State' },
  { id: 'filter', label: 'Filter' },
  { id: 'potential', label: 'Potential' },
  { id: 'scans', label: 'Scans' },
  { id: 'sources', label: 'Sources' },
  { id: 'status', label: 'Status' },
] as const;

/**
 * The four unit states, in scientist words.
 *
 * **There is deliberately no "Ready".** The integration design §5 establishes that a
 * candidate Run from this corpus cannot be export-ready, so a bucket named "Ready"
 * would be read as a promise the build cannot keep. Each label below names what was
 * observed instead of how far along something is.
 */
export const BL15_UNIT_STATE_LABELS: Record<string, string> = {
  values_read: 'Values read',
  conflict: 'Sources disagree',
  no_values: 'No values read',
  reference: 'Alignment or standard',
};

/** What each unit state means, one line each. */
export const BL15_UNIT_STATE_NOTES: Record<string, string> = {
  values_read:
    'Every value shown was read from a source in this import, and nothing disagreed.',
  conflict: 'At least two sources give different accounts of this measurement.',
  no_values:
    'No source in this import states any of the values this table shows for it.',
  reference:
    'A real acquisition, and not a sample measurement. It keeps its scans and its conflicts and is never offered as a Run.',
};

/** Filter choices over the table. `all` first; the rest follow the state order. */
export const BL15_FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'values_read', label: 'Values read' },
  { id: 'conflict', label: 'Sources disagree' },
  { id: 'no_values', label: 'No values read' },
  { id: 'reference', label: 'Alignment or standard' },
] as const;

export type Bl15FilterId = (typeof BL15_FILTERS)[number]['id'];

/** The five registry statuses, in scientist words. Titles only — reasons come from the payload. */
export const BL15_STATUS_LABELS: Record<string, string> = {
  deterministic: 'Taken as written',
  normalized: 'Carried across by a named rule',
  needs_domain_review: 'Needs a domain owner to choose',
  not_expressible: 'The schema has no field for it',
  blocked_by_build: 'The schema has a field this build cannot reach',
};

/** Conflict kinds, in scientist words. The EXPLANATION always comes from the server. */
export const BL15_CONFLICT_KIND_LABELS: Record<string, string> = {
  internal_declaration_vs_filename: 'The file’s own header disagrees with its name',
  duplicate_legacy_number: 'Two files claim the same legacy number',
  macro_declared_never_acquired: 'A macro declared a measurement that was never acquired',
  acquired_never_declared: 'A measurement exists that no macro declared',
  note_vs_filesystem: 'A human note disagrees with the files',
};

/** Source types, in scientist words. */
export const BL15_SOURCE_TYPE_LABELS: Record<string, string> = {
  spec_acquisition: 'Acquisition file',
  scan_export: 'Scan export',
  macro: 'Macro',
  acquisition_method_macro: 'Acquisition-method macro',
  motor_snapshot_macro: 'Instrument-state snapshot',
  processed_spectrum: 'Processed spectrum',
  detector_product: 'Detector product',
  shared_readme: 'Beamtime README',
  beamtime_notes: 'Beamtime notes',
  alignment: 'Alignment',
  standard_or_reference: 'Standard or reference',
  unknown: 'Not classified',
};

/** Concepts, in scientist words. Falls back to the raw id when absent. */
export const BL15_CONCEPT_LABELS: Record<string, string> = {
  sample_name: 'Sample name',
  sample_or_electrode_number: 'Sample or electrode number',
  electrolyte_or_medium: 'Electrolyte or medium',
  cycling_state: 'Cycling state',
  before_after_state: 'Before / after state',
  filter: 'Filter',
  potential_magnitude: 'Potential',
  potential_reference_basis: 'Potential reference basis',
  new_spot: 'New spot',
  legacy_run_or_file_number: 'Legacy run or file number',
  acquisition_timestamp: 'Acquisition timestamp',
  beamtime_purpose: 'Beamtime purpose',
};

/** Humanise an unknown id without inventing words: underscores to spaces. */
export function bl15Humanize(id: string): string {
  if (!/^[a-z][a-z0-9]*(_[a-z0-9]+)*$/.test(id)) return id;
  return id
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

export const conceptLabel = (id: string): string =>
  BL15_CONCEPT_LABELS[id] ?? bl15Humanize(id);
export const sourceTypeLabel = (id: string): string =>
  BL15_SOURCE_TYPE_LABELS[id] ?? bl15Humanize(id);
export const conflictKindLabel = (id: string): string =>
  BL15_CONFLICT_KIND_LABELS[id] ?? bl15Humanize(id);
export const statusLabel = (id: string): string =>
  BL15_STATUS_LABELS[id] ?? bl15Humanize(id);
