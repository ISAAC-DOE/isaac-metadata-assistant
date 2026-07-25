/**
 * P36.6 — pure, deterministic helpers for the Schema & Vocabulary browser.
 *
 * Every value these functions produce is derived directly from the JSON-Schema
 * document `GET /api/schema` returns (itself loaded server-side, verbatim, via
 * `isaac_records.official.schema_path`) — nothing here invents a field, a type,
 * a required flag, an allowed value, or a relationship. `required`/`optional`
 * is read off the ENCLOSING object's `required` array; relationships are read
 * off the schema's own `allOf`/`if`/`then` clauses.
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
  enumValues?: unknown[];
  description?: string;
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

function buildNode(name: string, path: string, node: JsonSchemaNode, required: boolean): SchemaFieldNode {
  const types = typesOf(node);
  const isArray = types.includes('array');
  // For an array field, children come from `items` (array-of-object); for a
  // plain object field, children come from the node itself.
  const objectNode: JsonSchemaNode | undefined = isArray ? node.items : node;
  const childRequired = new Set(objectNode?.required ?? []);
  const children = objectNode?.properties
    ? Object.entries(objectNode.properties).map(([childName, childNode]) =>
        buildNode(childName, `${path}.${childName}`, childNode, childRequired.has(childName)),
      )
    : undefined;
  return {
    path,
    name,
    typeLabel: formatTypeLabel(node),
    required,
    enumValues: node.enum,
    description: node.description,
    children,
  };
}

/** The top-level record fields, required/optional per the schema's own root `required` array. */
export function buildSchemaFieldTree(schema: JsonSchemaNode): SchemaFieldNode[] {
  const required = new Set(schema.required ?? []);
  return Object.entries(schema.properties ?? {}).map(([name, node]) =>
    buildNode(name, name, node, required.has(name)),
  );
}

function nodeMatches(node: SchemaFieldNode, query: string): boolean {
  const haystack = `${node.path} ${node.description ?? ''}`.toLowerCase();
  return haystack.includes(query);
}

/**
 * Deterministic client-side search: a case-insensitive substring match against
 * each field's dotted path (which includes its name) and its description. A
 * blank query returns the tree unchanged; a non-blank query returns a FLAT list
 * of every matching node at any depth (never invents a match).
 */
export function filterFieldTree(nodes: SchemaFieldNode[], query: string): SchemaFieldNode[] {
  const q = query.trim().toLowerCase();
  if (!q) return nodes;
  const matches: SchemaFieldNode[] = [];
  const walk = (list: SchemaFieldNode[]) => {
    for (const node of list) {
      if (nodeMatches(node, q)) matches.push(node);
      if (node.children) walk(node.children);
    }
  };
  walk(nodes);
  return matches;
}

// --- relationships (allOf if/then) --------------------------------------

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
  /** Where in the record this `allOf` entry lives — "record" for the top level. */
  scope: string;
  conditions: SchemaConditionClause[];
  /** Dotted paths the `then` clause requires. */
  required: string[];
  /** Value constraints the `then` clause imposes beyond requiredness (e.g. "must be null"). */
  constraints: SchemaThenConstraint[];
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
  for (const entry of schema.allOf ?? []) {
    const conditions = extractConditions(entry.if, path);
    const { required, constraints } = extractThenDetails(entry.then, path);
    if (conditions.length || required.length || constraints.length) {
      out.push({ scope: path || 'record', conditions, required, constraints });
    }
  }
  for (const [key, child] of Object.entries(schema.properties ?? {})) {
    out.push(...extractRelationships(child, path ? `${path}.${key}` : key));
  }
  if (schema.items) {
    out.push(...extractRelationships(schema.items, path ? `${path}[]` : '[]'));
  }
  return out;
}

function formatConditionClause(c: SchemaConditionClause): string {
  if (c.kind === 'const') return `${c.path} = ${JSON.stringify(c.value)}`;
  if (c.kind === 'enum') return `${c.path} is one of ${(c.values ?? []).map((v) => JSON.stringify(v)).join(', ')}`;
  return `${c.path} is present`;
}

/** A single readable sentence for one relationship, e.g. "If record_type =
 * "evidence", then descriptors is required." — built only from its own
 * structured conditions/required/constraints (no wording beyond the schema). */
export function formatRelationship(r: SchemaRelationship): string {
  const cond = r.conditions.length > 0 ? r.conditions.map(formatConditionClause).join(' and ') : `the ${r.scope} conditions are met`;
  const outcomes = [
    ...r.required.map((p) => `${p} is required`),
    ...r.constraints.map((c) => `${c.path} must be ${c.type}`),
  ];
  const outcomeText = outcomes.length > 0 ? outcomes.join('; ') : 'additional constraints apply';
  return `If ${cond}, then ${outcomeText}.`;
}
