/**
 * P36.6 / P36R S8 — pure, deterministic helpers for the Schema Reference
 * browser (Governance & Safety > Schema Reference).
 *
 * Every value these functions produce is derived directly from the JSON-Schema
 * document `GET /api/schema` returns (itself loaded server-side, verbatim, via
 * `isaac_records.official.schema_path`) — nothing here invents a field, a type,
 * a required flag, an allowed value, an example, or a rule. `required`/
 * `optional` is read off the ENCLOSING object's `required` array; conditional
 * rules are read off the schema's own `allOf`/`if`/`then` clauses; vocabulary
 * structure is read off the vocabulary file's own keys.
 *
 * Nothing here MUTATES the schema: the document is only walked, and the raw
 * `allOf` entry each rule carries is the very object the response contained
 * (kept by reference so the "source rule" disclosure can show it byte-for-byte
 * as the backend sent it).
 *
 * This is the reference plane (schema/vocabulary), not the truth-enforcement
 * core — it never validates, never gates export, and has no
 * propose/review/approve/edit affordance (that would be the portal Ontology
 * system, out of scope here).
 */

import type { JsonSchemaNode } from './types';

// --- field tree --------------------------------------------------------

export interface SchemaFieldNode {
  /** Dotted path from the record root, e.g. "context.electrochemistry.control_mode". */
  path: string;
  name: string;
  /** Honestly derived from the schema's own `type`/`const`/`oneOf` — "unspecified" when none is declared. */
  typeLabel: string;
  /** True iff the ENCLOSING object's `required` array names this field. */
  required: boolean;
  /** Nesting depth from the record root — a top-level field is 0. */
  depth: number;
  enumValues?: unknown[];
  description?: string;
  /** The schema's own `pattern`, when it constrains this field by regex. */
  pattern?: string;
  /** The schema's own `format` annotation, when declared. */
  format?: string;
  /** The schema's own `const`, when the field is pinned to a single value. */
  constValue?: unknown;
  /** The schema's own `examples`/`example`, when declared — never invented. */
  examples?: unknown[];
  /** Nested object/array-of-object properties, when the schema declares any. */
  children?: SchemaFieldNode[];
}

/** The declared type(s) of a node, honestly — `[]` when the schema declares none. */
function typesOf(node: JsonSchemaNode): string[] {
  if (Array.isArray(node.type)) return node.type;
  if (typeof node.type === 'string') return [node.type];
  if (node.const !== undefined) return [typeof node.const];
  if (Array.isArray(node.oneOf)) {
    const variants = node.oneOf.flatMap((o) => typesOf(o));
    return variants.length > 0 ? variants : ['oneOf'];
  }
  return [];
}

function formatTypeLabel(node: JsonSchemaNode): string {
  const types = typesOf(node);
  if (types.length === 0) return 'unspecified';
  if (types.includes('array')) {
    const itemTypes = node.items ? typesOf(node.items) : [];
    const itemLabel = itemTypes.length > 0 ? itemTypes.join(' | ') : 'object';
    return `array<${itemLabel}>`;
  }
  return types.join(' | ');
}

/** The schema's own `examples` (array) or `example` (single) — `undefined` when it declares neither. */
function readExamples(node: JsonSchemaNode): unknown[] | undefined {
  if (Array.isArray(node.examples)) return node.examples.length > 0 ? node.examples : undefined;
  if (node.example !== undefined) return [node.example];
  return undefined;
}

function readString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

function buildNode(
  name: string,
  path: string,
  node: JsonSchemaNode,
  required: boolean,
  depth: number,
): SchemaFieldNode {
  const types = typesOf(node);
  const isArray = types.includes('array');
  // For an array field, children come from `items` (array-of-object); for a
  // plain object field, children come from the node itself.
  const objectNode: JsonSchemaNode | undefined = isArray ? node.items : node;
  const childRequired = new Set(objectNode?.required ?? []);
  const children = objectNode?.properties
    ? Object.entries(objectNode.properties).map(([childName, childNode]) =>
        buildNode(childName, `${path}.${childName}`, childNode, childRequired.has(childName), depth + 1),
      )
    : undefined;
  return {
    path,
    name,
    typeLabel: formatTypeLabel(node),
    required,
    depth,
    enumValues: node.enum,
    description: node.description,
    pattern: readString(node.pattern),
    format: readString(node.format),
    constValue: node.const,
    examples: readExamples(node),
    children,
  };
}

/** The top-level record fields, required/optional per the schema's own root `required` array. */
export function buildSchemaFieldTree(schema: JsonSchemaNode): SchemaFieldNode[] {
  const required = new Set(schema.required ?? []);
  return Object.entries(schema.properties ?? {}).map(([name, node]) =>
    buildNode(name, name, node, required.has(name), 0),
  );
}

/**
 * Every field at every depth, in schema declaration order, parent immediately
 * before its own children. This is the master list the Fields view browses —
 * one row per field, never an expanded tree of everything at once.
 */
export function flattenFieldTree(nodes: SchemaFieldNode[]): SchemaFieldNode[] {
  const out: SchemaFieldNode[] = [];
  const walk = (list: SchemaFieldNode[]) => {
    for (const node of list) {
      out.push(node);
      if (node.children) walk(node.children);
    }
  };
  walk(nodes);
  return out;
}

function nodeMatches(node: SchemaFieldNode, query: string): boolean {
  const haystack = `${node.path} ${node.description ?? ''}`.toLowerCase();
  return haystack.includes(query);
}

/**
 * Deterministic client-side search: a case-insensitive substring match against
 * each field's dotted path (which includes its name) and its description. A
 * blank query returns the list unchanged; it never invents a match.
 */
export function filterFields(fields: SchemaFieldNode[], query: string): SchemaFieldNode[] {
  const q = query.trim().toLowerCase();
  if (!q) return fields;
  return fields.filter((node) => nodeMatches(node, q));
}

/** The exact field at `path`, or `undefined` — never a near-miss guess. */
export function findFieldByPath(
  fields: SchemaFieldNode[],
  path: string | null,
): SchemaFieldNode | undefined {
  if (!path) return undefined;
  return fields.find((node) => node.path === path);
}

/** The dotted path of the enclosing field, or `null` for a top-level field. */
export function parentPath(path: string): string | null {
  const cut = path.lastIndexOf('.');
  return cut === -1 ? null : path.slice(0, cut);
}

// --- conditional rules (allOf if/then) ----------------------------------

export interface SchemaConditionClause {
  path: string;
  kind: 'const' | 'enum' | 'present';
  value?: unknown;
  values?: unknown[];
}

export interface SchemaThenConstraint {
  path: string;
  type: string;
}

export interface SchemaRelationship {
  /** Stable within one schema document: scope + ordinal of the `allOf` entry. */
  id: string;
  /** Where in the record this `allOf` entry lives — "record" for the top level. */
  scope: string;
  conditions: SchemaConditionClause[];
  /** Dotted paths the `then` clause requires. */
  required: string[];
  /** Value constraints the `then` clause imposes beyond requiredness (e.g. "must be null"). */
  constraints: SchemaThenConstraint[];
  /** The `allOf` entry exactly as the schema declares it (kept by reference, never edited). */
  raw: unknown;
}

function extractConditions(ifNode: JsonSchemaNode | undefined, prefix: string): SchemaConditionClause[] {
  if (!ifNode) return [];
  const out: SchemaConditionClause[] = [];
  const props = ifNode.properties ?? {};
  for (const [key, child] of Object.entries(props)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (child.const !== undefined) {
      out.push({ path, kind: 'const', value: child.const });
    } else if (child.enum) {
      out.push({ path, kind: 'enum', values: child.enum });
    } else if (child.properties) {
      out.push(...extractConditions(child, path));
    }
    // A nested `required` inside an `if` property clause asserts presence of a
    // sub-field. Skip it when a more specific condition already covers that
    // sub-field (e.g. a const on it), so presence isn't stated redundantly.
    if (child.required?.length && child.const === undefined) {
      for (const req of child.required) {
        if (!child.properties?.[req]) {
          out.push({ path: `${path}.${req}`, kind: 'present' });
        }
      }
    }
  }
  for (const req of ifNode.required ?? []) {
    if (!props[req]) {
      out.push({ path: prefix ? `${prefix}.${req}` : req, kind: 'present' });
    }
  }
  return out;
}

interface ThenDetails {
  required: string[];
  constraints: SchemaThenConstraint[];
}

function extractThenDetails(thenNode: JsonSchemaNode | undefined, prefix: string): ThenDetails {
  if (!thenNode) return { required: [], constraints: [] };
  const required: string[] = (thenNode.required ?? []).map((r) => (prefix ? `${prefix}.${r}` : r));
  const constraints: SchemaThenConstraint[] = [];
  for (const [key, child] of Object.entries(thenNode.properties ?? {})) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (child.required?.length || child.properties) {
      const nested = extractThenDetails(child, path);
      required.push(...nested.required);
      constraints.push(...nested.constraints);
    } else if (child.type) {
      constraints.push({ path, type: Array.isArray(child.type) ? child.type.join(' | ') : child.type });
    }
  }
  return { required, constraints };
}

/**
 * Every `allOf` if/then relationship declared anywhere in the schema (the top
 * level plus every nested object), each labeled with the scope it lives under.
 * Purely structural — reads only `allOf`/`if`/`then`/`required`/`const`/`enum`
 * off the supplied schema; it never infers a relationship the schema itself
 * does not encode.
 */
export function extractRelationships(schema: JsonSchemaNode, path = ''): SchemaRelationship[] {
  const out: SchemaRelationship[] = [];
  (schema.allOf ?? []).forEach((entry, index) => {
    const conditions = extractConditions(entry.if, path);
    const { required, constraints } = extractThenDetails(entry.then, path);
    if (conditions.length || required.length || constraints.length) {
      const scope = path || 'record';
      out.push({ id: `${scope}#${index}`, scope, conditions, required, constraints, raw: entry });
    }
  });
  for (const [key, child] of Object.entries(schema.properties ?? {})) {
    out.push(...extractRelationships(child, path ? `${path}.${key}` : key));
  }
  if (schema.items) {
    out.push(...extractRelationships(schema.items, path ? `${path}[]` : '[]'));
  }
  return out;
}

export function formatConditionClause(c: SchemaConditionClause): string {
  if (c.kind === 'const') return `${c.path} = ${JSON.stringify(c.value)}`;
  if (c.kind === 'enum') return `${c.path} is one of ${(c.values ?? []).map((v) => JSON.stringify(v)).join(', ')}`;
  return `${c.path} is present`;
}

/** The rule's trigger clauses as readable text — one line per `if` clause. */
export function relationshipTriggers(r: SchemaRelationship): string[] {
  if (r.conditions.length === 0) return [`the ${r.scope} conditions are met`];
  return r.conditions.map(formatConditionClause);
}

/** The rule's consequences as readable text — one line per `then` obligation. */
export function relationshipOutcomes(r: SchemaRelationship): string[] {
  const out = [
    ...r.required.map((p) => `${p} is required`),
    ...r.constraints.map((c) => `${c.path} must be ${c.type}`),
  ];
  return out.length > 0 ? out : ['additional constraints apply'];
}

/** Every dotted field path the rule names, on either side, de-duplicated in declaration order. */
export function relationshipPaths(r: SchemaRelationship): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const p of [
    ...r.conditions.map((c) => c.path),
    ...r.required,
    ...r.constraints.map((c) => c.path),
  ]) {
    if (!seen.has(p)) {
      seen.add(p);
      out.push(p);
    }
  }
  return out;
}

/** True when `rulePath` is strictly nested INSIDE `fieldPath` (dotted paths). */
function isNestedUnder(rulePath: string, fieldPath: string): boolean {
  return rulePath.startsWith(`${fieldPath}.`);
}

/**
 * The conditional rules whose own clauses name this EXACT field path.
 *
 * Deliberately not an ancestor match: a rule that constrains
 * `context.electrochemistry.control_mode` says nothing about a sibling subtree
 * such as `context.electrochemistry.anolyte.notes`, and attributing it there
 * would put a claim on screen the schema never made.
 */
export function rulesNamingField(
  rules: SchemaRelationship[],
  fieldPath: string,
): SchemaRelationship[] {
  return rules.filter((r) => relationshipPaths(r).some((p) => p === fieldPath));
}

/**
 * The conditional rules that do NOT name this field itself but do constrain a
 * field nested inside it — real, weaker signal for a container field such as
 * `context.electrochemistry`, kept separate so the two are never conflated.
 */
export function rulesNestedUnderField(
  rules: SchemaRelationship[],
  fieldPath: string,
): SchemaRelationship[] {
  return rules.filter((r) => {
    const paths = relationshipPaths(r);
    return !paths.some((p) => p === fieldPath) && paths.some((p) => isNestedUnder(p, fieldPath));
  });
}

/** Case-insensitive substring search over a rule's scope, paths, triggers, and outcomes. */
export function filterRelationships(
  rules: SchemaRelationship[],
  query: string,
): SchemaRelationship[] {
  const q = query.trim().toLowerCase();
  if (!q) return rules;
  return rules.filter((r) => {
    const haystack = [r.scope, ...relationshipPaths(r), ...relationshipTriggers(r), ...relationshipOutcomes(r)]
      .join(' ')
      .toLowerCase();
    return haystack.includes(q);
  });
}

/** A single readable sentence for one rule, e.g. "If record_type =
 * "evidence", then descriptors is required." — built only from its own
 * structured conditions/required/constraints (no wording beyond the schema). */
export function formatRelationship(r: SchemaRelationship): string {
  return `If ${relationshipTriggers(r).join(' and ')}, then ${relationshipOutcomes(r).join('; ')}.`;
}

// --- vocabulary -----------------------------------------------------------

export type VocabularyNode =
  | { kind: 'terms'; label: string; path: string; terms: string[] }
  | { kind: 'group'; label: string; path: string; children: VocabularyNode[] }
  | { kind: 'scalar'; label: string; path: string; value: string };

export interface VocabularyFile {
  /** The vocabulary file's stem, e.g. "descriptor_class". */
  name: string;
  /** The file's own `field` key, when it declares one. */
  field?: string;
  /** The file's own provenance `note`, verbatim. */
  note?: string;
  /** The file's own `source` URL, verbatim. */
  source?: string;
  nodes: VocabularyNode[];
  /** Terms + scalar entries the file declares — counted, never estimated. */
  entryCount: number;
  /** Set only when the file is not a JSON object; rendered read-only, unmodified. */
  raw?: unknown;
}

function toVocabularyNode(label: string, value: unknown, path: string): VocabularyNode {
  if (Array.isArray(value)) {
    return { kind: 'terms', label, path, terms: value.map((t) => String(t)) };
  }
  if (value && typeof value === 'object') {
    return {
      kind: 'group',
      label,
      path,
      children: Object.entries(value as Record<string, unknown>).map(([k, v]) =>
        toVocabularyNode(k, v, `${path}.${k}`),
      ),
    };
  }
  return { kind: 'scalar', label, path, value: String(value) };
}

/** Terms + scalar entries under these nodes. */
export function countVocabularyEntries(nodes: VocabularyNode[]): number {
  let total = 0;
  for (const node of nodes) {
    if (node.kind === 'terms') total += node.terms.length;
    else if (node.kind === 'scalar') total += 1;
    else total += countVocabularyEntries(node.children);
  }
  return total;
}

/**
 * One vocabulary file's own structure — `field`/`note`/`source` lifted out as
 * provenance, every other key walked into browsable groups of terms. Nothing
 * is renamed, reordered, or summarized.
 */
export function buildVocabularyFile(name: string, data: unknown): VocabularyFile {
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    return { name, nodes: [], entryCount: 0, raw: data };
  }
  const obj = data as Record<string, unknown>;
  const nodes = Object.entries(obj)
    .filter(([key]) => key !== 'note' && key !== 'source' && key !== 'field')
    .map(([key, value]) => toVocabularyNode(key, value, key));
  return {
    name,
    field: readString(obj.field),
    note: readString(obj.note),
    source: readString(obj.source),
    nodes,
    entryCount: countVocabularyEntries(nodes),
  };
}

/**
 * Case-insensitive substring search over group labels and terms. A group whose
 * own label matches is kept whole; otherwise only its matching descendants
 * survive. A blank query returns the nodes unchanged.
 */
export function filterVocabularyNodes(nodes: VocabularyNode[], query: string): VocabularyNode[] {
  const q = query.trim().toLowerCase();
  if (!q) return nodes;
  const keep = (node: VocabularyNode): VocabularyNode | null => {
    const labelHit = node.label.toLowerCase().includes(q);
    if (node.kind === 'terms') {
      if (labelHit) return node;
      const terms = node.terms.filter((t) => t.toLowerCase().includes(q));
      return terms.length > 0 ? { ...node, terms } : null;
    }
    if (node.kind === 'scalar') {
      return labelHit || node.value.toLowerCase().includes(q) ? node : null;
    }
    if (labelHit) return node;
    const children = node.children.map(keep).filter((c): c is VocabularyNode => c !== null);
    return children.length > 0 ? { ...node, children } : null;
  };
  return nodes.map(keep).filter((n): n is VocabularyNode => n !== null);
}

/**
 * A slug specific enough to license the claim "N schema fields cite <slug>".
 *
 * Vocabulary files are auto-globbed by the backend, so any file could arrive
 * with a generic source (".../wiki/Units"), and a bare English word appearing
 * in a schema description is NOT evidence that the description is citing that
 * file. Only a compound token — two or more `-`/`_`-joined parts, the shape a
 * wiki page slug actually has — is treated as citable. Anything less generates
 * no claim at all: silence is honest, a fabricated citation is not.
 */
const CITABLE_SLUG = /^[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)+$/;

/**
 * The last PATH segment of the vocabulary file's own `source` URL — e.g.
 * ".../wiki/Controlled-Vocabulary" → "Controlled-Vocabulary". This is the token
 * the SCHEMA's own field descriptions cite when they defer to that vocabulary,
 * which is what makes the two documents linkable without hard-coding either.
 *
 * A query string or fragment is stripped BEFORE the last segment is taken, so
 * ".../wiki/Controlled-Vocabulary#classes" still yields the page slug rather
 * than "classes". `null` when the source declares no segment specific enough to
 * cite (see `CITABLE_SLUG`) — the caller then renders nothing.
 */
export function vocabularySourceSlug(source: string | undefined): string | null {
  if (!source) return null;
  const withoutQuery = source.split(/[#?]/)[0];
  const segments = withoutQuery.split('/').filter(Boolean);
  const last = segments[segments.length - 1];
  if (!last || last.length < 3) return null;
  return CITABLE_SLUG.test(last) ? last : null;
}

/** Regex-safe form of an arbitrary slug. */
function escapeForRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Schema fields whose OWN description cites `slug` as a DISTINCT token.
 *
 * Nothing is inferred: a field appears here only because the schema text names
 * the vocabulary source. The match is bounded by non-alphanumerics on both
 * sides, so a slug buried inside a longer word ("units" inside "subunits") is
 * not read as a citation.
 */
export function fieldsCitingVocabulary(
  fields: SchemaFieldNode[],
  slug: string | null,
): SchemaFieldNode[] {
  if (!slug) return [];
  const token = new RegExp(`(^|[^A-Za-z0-9])${escapeForRegExp(slug)}([^A-Za-z0-9]|$)`, 'i');
  return fields.filter((f) => token.test(f.description ?? ''));
}

/**
 * True when EVERY citing field is constrained by a regex and enumerates no
 * values inline — i.e. the schema genuinely delegates the token list to the
 * vocabulary file rather than carrying it. Checked, never assumed.
 */
export function citationsArePatternOnly(fields: SchemaFieldNode[]): boolean {
  return (
    fields.length > 0 &&
    fields.every((f) => !!f.pattern && (!f.enumValues || f.enumValues.length === 0))
  );
}
