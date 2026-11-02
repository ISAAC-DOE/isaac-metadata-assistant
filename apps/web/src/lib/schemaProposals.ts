/*
 * SCHEMA PROPOSALS — the wire contract and the copy for the screen.
 *
 * ISAAC DRAFTS AND TRACKS A PROPOSAL; THE OWNERS OF THE STANDARD REVIEW IT IN THE ISAAC
 * PORTAL. Nothing here approves, applies or sends anything, and the status vocabulary
 * is the server's own two values — `pending` and `withdrawn`. `accepted` / `rejected`
 * are decisions made in the portal and are deliberately not a type here: a status this
 * build cannot establish is a status it must not display.
 *
 * The shapes mirror `apps/api/isaac_api/schema_proposals.py`, which mirrors the portal's
 * `vocabulary_proposals` table and `POST /portal/api/vocabulary/proposals`.
 */

/**
 * `add_term` and `add_category` are the upstream portal's two proposal types. `schema_change`
 * is ISAAC's own: a request for a new FIELD in the record schema, which the portal has NO
 * proposal type for — so it never has a portal payload, and its export is a labelled
 * change-request document for the standard's owners.
 */
export type SchemaProposalType = 'add_term' | 'add_category' | 'schema_change';
export type PortalProposalType = 'add_term' | 'add_category';
export type SchemaProposalStatus = 'pending' | 'withdrawn';

export interface ApiSchemaCategory {
  /** The dotted property path; the portal's category key. */
  key: string;
  label: string;
  description: string;
  terms: string[];
  /** `terms` is a list of allowed words; `other` is a mapping or unit grammar with no term list (portal only). */
  kind?: 'terms' | 'other';
}

export interface ApiSchemaSection {
  id: string;
  label: string;
  /** The top-level block this section is, or null for the record's root fields. */
  block: string | null;
  categories: ApiSchemaCategory[];
}

export interface ApiSchemaLimits {
  section_max: number;
  category_max: number;
  term_max: number;
  description_min: number;
  description_max: number;
  problem_max: number;
  examples_max: number;
  affected_records_estimate_max: number;
  flip_list_max: number;
  /** Schema change requests (absent from a server that predates them). */
  field_name_max?: number;
  unit_max?: number;
  example_max?: number;
  migration_max?: number;
  max_pending: number;
  max_withdrawn_kept: number;
  max_body_bytes: number;
  page_max: number;
}

export type SchemaSourceId = 'portal' | 'schema';

/** One labelled vocabulary source. Neither is the live portal and neither is "the" vocabulary. */
export interface ApiSchemaSource {
  id: SchemaSourceId;
  /** e.g. "Portal vocabulary (snapshot a1cb1c8)" or "Schema enums (vendored v1.05)". */
  label: string;
  detail: string;
  sha256: string;
  section_count: number;
  category_count: number;
  term_list_count: number;
  term_count: number;
  sections: ApiSchemaSection[];
  snapshot_commit?: string;
  derived_from?: string;
}

/** A section a proposal may name, with the portal term lists a new term may join. */
export interface ApiProposalSection {
  id: string;
  label: string;
  block: string | null;
  term_lists: string[];
}

/** One block of the vendored schema a new field could go in, as the server derived it. */
export interface ApiSchemaObjectPath {
  /** Dotted path; `''` is the record root. */
  path: string;
  section: string;
  /** Whether the schema accepts an undeclared key here TODAY (`additionalProperties` is not false). */
  open: boolean;
  /** The block's existing field names. */
  fields: string[];
}

export type SchemaChangeValueType = 'string' | 'number' | 'integer' | 'boolean' | 'object' | 'array';
export type SchemaChangeScope = 'core' | 'domain_profile';

export interface ApiSchemaChangeInfo {
  kinds: string[];
  value_types: SchemaChangeValueType[];
  scopes: SchemaChangeScope[];
  object_paths: ApiSchemaObjectPath[];
  /** The server's own sentence: the portal has no proposal type for a new field. */
  not_a_portal_proposal: string;
  upstream: { repository: string; process: string; drafts: string; ledger?: string; read_at_commit?: string };
}

export interface ApiSchemaVocabulary {
  schema_version: string;
  default_source: SchemaSourceId;
  sources: Record<SchemaSourceId, ApiSchemaSource>;
  proposal_sections: ApiProposalSection[];
  proposal_types: SchemaProposalType[];
  /** The types the portal itself defines. Absent from a server that predates schema change requests. */
  portal_proposal_types?: PortalProposalType[];
  /** Absent from a server that predates schema change requests; the screen then offers only the two portal types. */
  schema_change?: ApiSchemaChangeInfo;
  limits: ApiSchemaLimits;
  /**
   * The server's own term-shape rules, as patterns (`schema_proposal_rules.TERM_SHAPE_FOR_CLIENTS`),
   * so a "Propose this term" link is offered only for a term the server would accept. Absent from
   * an older server, and then no link is offered.
   */
  term_shape?: { term: string; snake_case: string; path_like: string };
  term_rule: string;
  review_note: string;
}

export interface ApiSchemaProposalGate0 {
  problem?: string;
  examples?: string;
  affected_records_estimate?: string;
  flip_list?: string;
}

/**
 * Where a new term came from when it was filed from a local import's drafts file
 * (`isaac bundle propose-terms --out`), which the page reads in the browser
 * (`lib/termDrafts.ts`). The server checks that `field_path` and `term` are the proposal's own
 * and refuses any other key; the citations and counts travel as `gate0` notes.
 */
export interface ApiSchemaProposalSourceInput {
  kind: 'local_import';
  format: 'isaac.term-proposal-drafts';
  bundle_id?: string;
  field_path: string;
  term: string;
  occurrences: number;
  runs?: number;
  citations_total: number;
}

/** The stored `source`, as the server returns it (each key present; unknown values null). */
export interface ApiSchemaProposalSource {
  kind: 'local_import';
  format: string | null;
  bundle_id: string | null;
  field_path: string | null;
  term: string | null;
  occurrences: number | null;
  runs: number | null;
  citations_total: number | null;
}

/** The `change` of a stored schema change request, as the server returns it. */
export interface ApiSchemaChange {
  kind: string | null;
  parent_path: string | null;
  field_name: string | null;
  path: string | null;
  value_type: SchemaChangeValueType | null;
  unit: string | null;
  required: boolean | null;
  example: string | null;
  scope: SchemaChangeScope | null;
  migration: string | null;
  parent_open_today: boolean | null;
}

export interface ApiSchemaProposal {
  id: string;
  proposal_type: SchemaProposalType;
  section: string;
  category: string;
  term: string | null;
  description: string;
  gate0: ApiSchemaProposalGate0 | null;
  status: SchemaProposalStatus;
  /** Always null unless a verified person made the request; no deployment of this build provides one. */
  proposed_by: string | null;
  attribution: 'verified' | 'unverified';
  proposed_at: string | null;
  withdrawn_at: string | null;
  schema_version: string | null;
  /** Only on a `schema_change`; `null` (or absent, from an older server) otherwise. */
  change?: ApiSchemaChange | null;
  /** Set when the proposal was filed from a local import's drafts file; absent from an older server. */
  source?: ApiSchemaProposalSource | null;
  sent_by_isaac: false;
}

export interface ApiSchemaPersistence {
  class: string;
  survives_restart: string;
  message: string;
}

/** Fields every proposal response carries so no screen has to remember them. */
export interface ApiSchemaEnvelope {
  persistence: ApiSchemaPersistence;
  review_note: string;
  attribution_note: string;
}

export interface ApiSchemaProposalResponse extends ApiSchemaEnvelope {
  proposal: ApiSchemaProposal;
  ignored_fields?: string[];
  /** How many of the oldest withdrawn proposals were removed to stay inside the kept-withdrawn bound. */
  withdrawn_removed?: number;
}

export interface ApiSchemaProposalList extends ApiSchemaEnvelope {
  proposals: ApiSchemaProposal[];
  total: number;
  limit: number;
  offset: number;
  next_offset: number | null;
  statuses: SchemaProposalStatus[];
  capacity: {
    pending: number;
    max_pending: number;
    max_withdrawn_kept: number;
    /** The server's own sentence about who shares the limit. */
    scope: string;
  };
}

export interface ApiSchemaPortalPayload extends ApiSchemaEnvelope {
  proposal_id: string;
  status: SchemaProposalStatus;
  portal: { method: string; path: string; rest_supported: boolean };
  /** The exact body of the portal's proposal endpoint. */
  body: Record<string, string | null>;
  sent_by_isaac: false;
  notes: string[];
}

/** The export of a schema change request: a document, NEVER a portal payload. */
export interface ApiSchemaChangeRequest extends ApiSchemaEnvelope {
  proposal_id: string;
  status: SchemaProposalStatus;
  format: string;
  format_version: string;
  is_portal_payload: false;
  markdown: string;
  document: Record<string, unknown>;
  filename_stem: string;
  upstream: ApiSchemaChangeInfo['upstream'];
  sent_by_isaac: false;
  notes: string[];
}

export interface SchemaChangeInput {
  kind: 'add_field';
  parent_path: string;
  field_name: string;
  value_type: SchemaChangeValueType;
  required: boolean;
  unit?: string;
  example?: string;
  scope?: SchemaChangeScope;
  migration?: string;
}

/** What the form sends. `gate0` is omitted entirely when no reviewer note was written. */
export interface SchemaProposalInput {
  proposal_type: SchemaProposalType;
  section: string;
  /** Not sent for a `schema_change`: the server sets it from the change's path. */
  category?: string;
  term?: string;
  description: string;
  gate0?: ApiSchemaProposalGate0;
  /** Only for a `schema_change`. */
  change?: SchemaChangeInput;
  /** Only for a new term filed from a local import's drafts file. */
  source?: ApiSchemaProposalSourceInput;
}

export interface SchemaFieldError {
  field: string | null;
  code: string;
  message: string;
}

/**
 * The per-field errors of a refused proposal, read from the server's own `errors` list
 * and never composed here: the sentences are the server's. Anything that is not a
 * well-formed list yields `[]`, which the caller reads as "no field-level answer" and
 * answers with the server's top-level message instead.
 */
export function schemaFieldErrors(err: unknown): SchemaFieldError[] {
  if (typeof err !== 'object' || err === null) return [];
  const body = (err as { body?: unknown }).body;
  if (typeof body !== 'object' || body === null) return [];
  const raw = (body as { errors?: unknown }).errors;
  if (!Array.isArray(raw)) return [];
  const out: SchemaFieldError[] = [];
  for (const entry of raw) {
    if (typeof entry !== 'object' || entry === null) continue;
    const { field, code, message } = entry as Record<string, unknown>;
    if (typeof code !== 'string' || typeof message !== 'string') continue;
    out.push({ field: typeof field === 'string' ? field : null, code, message });
  }
  return out;
}

/** The pretty-printed text the copy and download controls hand out: the portal body, nothing else. */
export function portalBodyText(payload: ApiSchemaPortalPayload): string {
  return JSON.stringify(payload.body, null, 2) + '\n';
}

export function portalBodyFilename(proposalId: string): string {
  return `isaac-schema-proposal-${proposalId}.json`;
}

/** A proposal's one-line name for a list row, built from its own fields. */
export function proposalHeadline(p: Pick<ApiSchemaProposal, 'proposal_type' | 'category' | 'term'>): string {
  if (p.proposal_type === 'add_term') return `Add the term ${p.term ?? ''} to ${p.category}`;
  if (p.proposal_type === 'schema_change') return `Add the field ${p.category} to the schema`;
  return `Add the category ${p.category}`;
}

/** The kind of proposal, in words, for a list row's meta line. */
export const PROPOSAL_KIND_LABEL: Record<SchemaProposalType, string> = {
  add_term: 'new term',
  add_category: 'new list',
  schema_change: 'schema change request (not a portal proposal)',
};

export const VALUE_TYPE_LABEL: Record<SchemaChangeValueType, string> = {
  string: 'Text',
  number: 'Number',
  integer: 'Whole number',
  boolean: 'Yes / no',
  object: 'A group of fields',
  array: 'A list',
};

export function changeRequestMarkdownFilename(stem: string): string {
  return `${stem}.md`;
}

export function changeRequestJsonFilename(stem: string): string {
  return `${stem}.json`;
}

/** The text the JSON download hands out: the server's `document`, nothing rebuilt. */
export function changeRequestJsonText(request: ApiSchemaChangeRequest): string {
  return JSON.stringify(request.document, null, 2) + '\n';
}

/* ---------------------------------------------------------------------------
 * PROPOSE FROM WHERE THE GAP IS FOUND.
 *
 * A screen that shows a scientist a value outside a fixed list links to the Propose
 * form with the list and the value filled in. The link is offered ONLY when the list is
 * a real PORTAL term list (`proposal_sections[].term_lists`), because a new term is
 * checked against the portal's list and the portal refuses one for any other: a schema
 * enum the portal has no list for, or a free-text field, gets no link. Nothing here
 * decides whether the value is a good term; the form and the server do.
 * ------------------------------------------------------------------------- */

/** Where a "Propose this term" link was followed from. Only these are named on the form. */
export const PROPOSE_SOURCES = {
  validator: 'the Validator',
  ingestion_proposal: 'a proposed value from a file',
  run_override: 'a run’s own value',
} as const;
export type ProposeSource = keyof typeof PROPOSE_SOURCES;

export function isProposeSource(v: string | null): v is ProposeSource {
  return v !== null && Object.prototype.hasOwnProperty.call(PROPOSE_SOURCES, v);
}

/** The category key a field path is listed under: array indices and `[]` dropped. */
export function categoryKeyOf(path: string): string {
  return path
    .replace(/\[\]/g, '')
    .split('.')
    .filter((seg) => seg !== '' && !/^\d+$/.test(seg))
    .join('.');
}

/**
 * The portal section whose term list is `category`, or null (no portal list, or the key is
 * in more than one section). Read from the server's own `proposal_sections`.
 */
export function portalSectionFor(vocabulary: ApiSchemaVocabulary, category: string): string | null {
  const found = vocabulary.proposal_sections.filter((s) => s.term_lists.includes(category));
  return found.length === 1 ? found[0].id : null;
}

/** The portal's terms for `category` in `section`, or null. */
export function portalTermsFor(vocabulary: ApiSchemaVocabulary, section: string, category: string): string[] | null {
  const sec = vocabulary.sources.portal.sections.find((s) => s.id === section);
  const cat = sec?.categories.find((c) => c.key === category && c.kind !== 'other');
  return cat ? cat.terms : null;
}

/**
 * The server's comparison form for a duplicate term (`schema_proposal_rules._separator_free`):
 * case-folded, with spaces, `_`, `-`, `/` and `.` removed. `in situ`, `In-Situ` and `in_situ`
 * are one term to the server, which refuses the first two as `term_already_exists`.
 */
export function separatorFree(text: string): string {
  return text.toLowerCase().replace(/[\s_\-/.]+/g, '');
}

/**
 * Whether the server's own shape rules accept `term` for a list holding `existing`: one word
 * (the served `term` pattern), nothing path-like, and lowercase-with-underscores when every
 * existing term is. Read from the vocabulary's `term_shape`; without it, nothing is accepted.
 */
export function termShapeAccepts(vocabulary: ApiSchemaVocabulary, term: string, existing: string[]): boolean {
  const shape = vocabulary.term_shape;
  if (!shape) return false;
  try {
    if (term.length > vocabulary.limits.term_max) return false;
    if (!new RegExp(shape.term).test(term) || new RegExp(shape.path_like).test(term)) return false;
    const snake = new RegExp(shape.snake_case);
    if (existing.length > 0 && existing.every((t) => snake.test(t)) && !snake.test(term)) return false;
    return true;
  } catch {
    return false; // a pattern this browser cannot compile: offer nothing rather than guess
  }
}

/**
 * Whether a "Propose this term" link fits: the field is a portal term list, the value is a
 * non-empty string that list does not already hold — not even as a spelling the server would
 * refuse as the same term (`in situ` for `in_situ`) — and it has the shape the server accepts
 * (`cathodic corrosion`, with its space, does not). Each of these is a proposal the server
 * would refuse, so none is offered a link: such a value is a correction to choose on the
 * surface that showed it, or a term to write by hand on the form.
 */
export function canProposeTerm(vocabulary: ApiSchemaVocabulary, category: string, term: unknown): term is string {
  if (typeof term !== 'string' || term.trim() === '') return false;
  const section = portalSectionFor(vocabulary, category);
  if (section === null) return false;
  const terms = portalTermsFor(vocabulary, section, category);
  if (terms === null) return false;
  const wanted = separatorFree(term);
  if (terms.some((t) => separatorFree(t) === wanted)) return false;
  return termShapeAccepts(vocabulary, term, terms);
}

/** The Propose form, opened on this list with this term. The section is looked up there. */
export function proposeTermHref(
  base: string,
  opts: { category: string; term: string; from: ProposeSource },
): string {
  const q = new URLSearchParams({ tab: 'propose', category: opts.category, term: opts.term, from: opts.from });
  return `${base}?${q.toString()}`;
}

export const STATUS_LABEL: Record<SchemaProposalStatus, string> = {
  pending: 'Pending',
  withdrawn: 'Withdrawn',
};

export const SCHEMA_PROPOSALS_COPY = {
  title: 'Schema Proposals',
  lead: 'Is a term, a list or a field you need missing from the ISAAC standard? Propose it here.',
  /*
   * THE ONE SENTENCE on where a proposal goes from here: functional guidance, in the page lead, once and
   * nowhere else on the screen (`schema-proposals.test.tsx` counts occurrences). It claims nothing this page
   * does not do: the person sends a proposal to the portal; this page keeps the draft. The server's own
   * `review_note` is deliberately not rendered a second time.
   */
  boundary: "Save a proposal here, then send it to the ISAAC portal, where the standard's owners decide.",
  savedNotice: 'Saved as a draft. Copy or download it to send it to the ISAAC portal.',
  /** The page's three parts: the form's heading, the list's heading, and the folded vocabulary's summary. */
  proposeTitle: 'Propose a Change',
  proposalsTitle: 'Proposals',
  browseTitle: 'Look Up an Existing List',
  /* Browse, in one line: the path a person takes through it (section, then list, then its terms). */
  browseLead: 'Choose a section, then one of its lists, to see the terms it allows.',
  /*
   * THE KIND CHOOSER. Each option's title is its accessible name and its hint is its description, so the
   * hint says what the kind is for in one line and the title stays short. The third is offered only when
   * the server describes `schema_change`.
   */
  kindTerm: 'A term in an existing list',
  kindTermHint: 'One word a list lacks, for example a technique.',
  kindList: 'A new list of allowed terms',
  kindListHint: 'A field that should take a fixed set of words.',
  kindField: 'A new field in the ISAAC schema',
  kindFieldHint: 'A change to the schema itself.',
  /* What the third kind produces, said once under the cards when it is chosen. */
  schemaChangeLead: "You get a change-request document for the standard's owners, not a portal proposal.",
  schemaChangeSaved: "Saved as a draft. Copy or download the change request to share it with the standard's owners.",
  readyLead: 'Propose one to open it in the form, with the description left to you. Nothing is sent until you save.',
  /** The one hint beside Save, for a plain proposal and for one opened from a local draft alike. */
  saveHint: 'Saves a draft. You send it from Proposals.',
  localImportFiledFrom: 'From a local import’s drafts file',
} as const;
