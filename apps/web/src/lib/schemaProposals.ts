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

export type SchemaProposalType = 'add_term' | 'add_category';
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

export interface ApiSchemaVocabulary {
  schema_version: string;
  default_source: SchemaSourceId;
  sources: Record<SchemaSourceId, ApiSchemaSource>;
  proposal_sections: ApiProposalSection[];
  proposal_types: SchemaProposalType[];
  limits: ApiSchemaLimits;
  term_rule: string;
  review_note: string;
}

export interface ApiSchemaProposalGate0 {
  problem?: string;
  examples?: string;
  affected_records_estimate?: string;
  flip_list?: string;
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

/** What the form sends. `gate0` is omitted entirely when no reviewer note was written. */
export interface SchemaProposalInput {
  proposal_type: SchemaProposalType;
  section: string;
  category: string;
  term?: string;
  description: string;
  gate0?: ApiSchemaProposalGate0;
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
  return p.proposal_type === 'add_term'
    ? `Add the term ${p.term ?? ''} to ${p.category}`
    : `Add the category ${p.category}`;
}

export const STATUS_LABEL: Record<SchemaProposalStatus, string> = {
  pending: 'Pending',
  withdrawn: 'Withdrawn',
};

export const SCHEMA_PROPOSALS_COPY = {
  title: 'Schema Proposals',
  lead: 'Is a word you need missing from the ISAAC vocabulary? Draft a proposal here.',
  /*
   * THE ONE STATEMENT of what ISAAC does and does not do with a proposal. It appears once, in the
   * page lead, and nowhere else on the screen (`schema-proposals.test.tsx` counts occurrences).
   * The server's own `review_note` is deliberately not rendered a second time.
   */
  boundary:
    'ISAAC only keeps your draft and the text to send: it does not approve, apply or send anything, ' +
    'and the standard\'s owners decide in the ISAAC portal.',
  savedNotice:
    'Saved as a draft on this server \u2014 not sent anywhere. Drafts here are temporary; copy or ' +
    'download the portal payload to send it.',
  tabBrowse: 'Browse the Vocabulary',
  tabPropose: 'Propose a Change',
  tabProposals: 'Proposals',
  browseLead:
    'Two lists, side by side, because they are not the same list: the ISAAC portal\'s vocabulary ' +
    '(a copy taken at one point in time) and the fixed value lists in the record schema this build ' +
    'validates against. They overlap only in part, and neither is the live portal.',
  proposeLead:
    'Say what is missing and where it is used. A reviewer writes the definition from your description.',
  unverifiedAuthor:
    'Author not recorded: who is using this server is not verified, so nobody is named on a proposal.',
} as const;
