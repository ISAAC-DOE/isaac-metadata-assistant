/**
 * The API tab's derivation layer (P36V PR3 slice C).
 *
 * Everything the API surface states about this API is computed HERE, from the
 * document `GET /api/openapi` returns, so no fact on the screen can be authored
 * by hand and drift from the running app. There is deliberately no second,
 * hand-maintained endpoint catalog anywhere in the client.
 *
 * What changed in slice C, and why it had to:
 *
 *   The previous grouping helper inferred a group from the path segment after
 *   `/api/` and its docstring asserted that "this backend does not assign
 *   OpenAPI `tags`". That was TRUE when it was written and is now FALSE: every
 *   operation carries a registered tag, and the 14 real tag names
 *   (`Health & Meta`, `Experiments`, `Drafts & Answers`, `Validation`,
 *   `Evidence`, `Export & Artifacts`, `Project Memory`, `Graph`, `Search`,
 *   `Assistant`, `Demo`, `Ingestion`, `Uploads`, `Schema & Vocabulary`) do not
 *   match the segments that helper produced (`health`, `about`, `openapi`,
 *   `memory`, `graph`, `runtime`, `validate`, …). Segment inference also split
 *   one group across two names (`/api/memory/*` vs `/api/graph/*` are both
 *   Project Memory work) and merged unrelated ones. Grouping now uses the
 *   document's own `tags`, ordered by the document's own registration order,
 *   with each group's description taken from the top-level `tags` array.
 *
 *   The fallback is explicit rather than inferred: an operation the document
 *   leaves untagged is placed in a single {@link UNTAGGED_GROUP} bucket sorted
 *   last. No group name is ever guessed from a path again.
 *
 * Nothing here reads the network, the clock, the locale, or `Math.random`: same
 * document in, same model out.
 */

import type {
  ApiOpenApiResponse,
  OpenApiMediaType,
  OpenApiMethod,
  OpenApiParameter,
  OpenApiRequestBody,
} from './types';

/** Where an operation with no `tags` is filed. Never inferred from its path. */
export const UNTAGGED_GROUP = 'Other Operations';

/** Environment variable names the generated samples read from. Deliberately
 *  spelled with `CREDENTIAL`: the client copy never prints the deployment's own
 *  variable name, and never a host literal. */
export const SAMPLE_BASE_ENV = 'ISAAC_BASE_URL';
export const SAMPLE_CREDENTIAL_ENV = 'ISAAC_API_CREDENTIAL';
export const SAMPLE_BODY_ENV = 'ISAAC_REQUEST_BODY';

export interface ApiResponseEntry {
  code: string;
  description?: string;
  content?: Record<string, OpenApiMediaType>;
}

export interface ApiEndpoint {
  /** Stable identity for selection: "get /api/health". */
  key: string;
  method: OpenApiMethod;
  path: string;
  /** The operation's first declared tag, or {@link UNTAGGED_GROUP}. */
  group: string;
  /** False only when the document declared no tag for this operation. */
  tagged: boolean;
  summary?: string;
  description?: string;
  parameters: OpenApiParameter[];
  requestBody?: OpenApiRequestBody;
  /** Every documented response, ascending by code. */
  responses: ApiResponseEntry[];
  /**
   * Derived, not assumed: the contract documents a `401` for this operation, so
   * a caller must present a credential when the deployment enables
   * authentication. An operation with no documented `401` stays reachable
   * without one. This is read off the document — never inferred from the path.
   */
  authRequired: boolean;
}

const METHOD_ORDER: OpenApiMethod[] = ['get', 'post', 'put', 'delete'];

/** Numeric status codes sort numerically; a non-numeric key (`default`) sorts
 *  after them, by name, so ordering is total and stable. */
function compareCodes(a: string, b: string): number {
  const na = Number(a);
  const nb = Number(b);
  const aNum = Number.isFinite(na);
  const bNum = Number.isFinite(nb);
  if (aNum && bNum) return na - nb;
  if (aNum) return -1;
  if (bNum) return 1;
  return a.localeCompare(b);
}

/** True for a documented response that reports a failure (>= 400). */
export function isErrorCode(code: string): boolean {
  const n = Number(code);
  return Number.isFinite(n) && n >= 400;
}

/** The registration order of the document's top-level `tags`, so groups appear
 *  in the order the API declares them rather than alphabetically. A tag used by
 *  an operation but absent from that array still renders — it sorts after every
 *  registered tag, by name — and the untagged bucket sorts last of all. */
function tagRanks(schema: ApiOpenApiResponse): Map<string, number> {
  const ranks = new Map<string, number>();
  (schema.tags ?? []).forEach((tag, index) => {
    if (tag?.name && !ranks.has(tag.name)) ranks.set(tag.name, index);
  });
  return ranks;
}

const UNREGISTERED_RANK = 1_000_000;
const UNTAGGED_RANK = 2_000_000;

/** Group descriptions, straight from the document's top-level `tags`. A tag with
 *  no description is simply not described — no placeholder is invented. */
export function tagDescriptions(schema: ApiOpenApiResponse): Record<string, string> {
  const out: Record<string, string> = {};
  for (const tag of schema.tags ?? []) {
    if (tag?.name && tag.description) out[tag.name] = tag.description;
  }
  return out;
}

export function flattenOpenApi(schema: ApiOpenApiResponse): ApiEndpoint[] {
  const ranks = tagRanks(schema);
  const rows: ApiEndpoint[] = [];
  for (const [path, item] of Object.entries(schema.paths ?? {})) {
    for (const method of METHOD_ORDER) {
      const op = item?.[method];
      if (!op) continue;
      const tag = op.tags?.find((t) => typeof t === 'string' && t.length > 0);
      const responses: ApiResponseEntry[] = Object.entries(op.responses ?? {})
        .map(([code, res]) => ({ code, description: res?.description, content: res?.content }))
        .sort((a, b) => compareCodes(a.code, b.code));
      rows.push({
        key: `${method} ${path}`,
        method,
        path,
        group: tag ?? UNTAGGED_GROUP,
        tagged: tag !== undefined,
        summary: op.summary,
        description: op.description,
        parameters: op.parameters ?? [],
        requestBody: op.requestBody,
        responses,
        authRequired: responses.some((r) => r.code === '401'),
      });
    }
  }
  rows.sort((a, b) => {
    const ra = a.tagged ? (ranks.get(a.group) ?? UNREGISTERED_RANK) : UNTAGGED_RANK;
    const rb = b.tagged ? (ranks.get(b.group) ?? UNREGISTERED_RANK) : UNTAGGED_RANK;
    return (
      ra - rb ||
      a.group.localeCompare(b.group) ||
      a.path.localeCompare(b.path) ||
      a.method.localeCompare(b.method)
    );
  });
  return rows;
}

export interface ApiEndpointGroup {
  key: string;
  /** From the document's top-level `tags`; absent when the tag has none. */
  description?: string;
  rows: { row: ApiEndpoint; index: number }[];
}

/** Consecutive runs of one group, carrying each row's index in the FLAT filtered
 *  list so the roving cursor spans the whole list, not each group. */
export function groupEndpoints(
  rows: ApiEndpoint[],
  descriptions: Record<string, string> = {},
): ApiEndpointGroup[] {
  const groups: ApiEndpointGroup[] = [];
  rows.forEach((row, index) => {
    const last = groups[groups.length - 1];
    if (last && last.key === row.group) last.rows.push({ row, index });
    else
      groups.push({
        key: row.group,
        description: descriptions[row.group],
        rows: [{ row, index }],
      });
  });
  return groups;
}

/**
 * The one base path every documented path shares, ending at its `/api` segment
 * — `/api` for a local run, `/<base>/api` where the deployment sets a base path.
 * Returns `null` when the document's paths do not share one, which the UI states
 * instead of printing a base path that would be wrong for some operations.
 *
 * Only ever a RELATIVE path: an origin is never derived, displayed, or assumed.
 */
export function apiBasePath(schema: ApiOpenApiResponse): string | null {
  const paths = Object.keys(schema.paths ?? {});
  if (paths.length === 0) return null;
  // The FIRST `/api` segment (lazy), so `/base/api/...` yields `/base/api` and a
  // path that happens to contain a later `api` segment cannot extend the base.
  const match = /^(\/(?:[^/]+\/)*?api)(?:\/|$)/.exec(paths[0]);
  const candidate = match?.[1];
  if (!candidate) return null;
  const shared = paths.every((p) => p === candidate || p.startsWith(`${candidate}/`));
  return shared ? candidate : null;
}

/** Request media types the contract actually declares, deduplicated and sorted.
 *  An empty list means no operation declares a request body. */
export function requestMediaTypes(rows: ApiEndpoint[]): string[] {
  const seen = new Set<string>();
  for (const row of rows) {
    for (const mediaType of Object.keys(row.requestBody?.content ?? {})) seen.add(mediaType);
  }
  return Array.from(seen).sort();
}

/** Every failure status the whole contract documents, ascending. */
export function documentedErrorCodes(rows: ApiEndpoint[]): string[] {
  const seen = new Set<string>();
  for (const row of rows) {
    for (const res of row.responses) if (isErrorCode(res.code)) seen.add(res.code);
  }
  return Array.from(seen).sort(compareCodes);
}

export interface QuickStartFacts {
  /** Relative, or null when the paths share no single base. */
  basePath: string | null;
  apiVersion: string | null;
  openApiVersion: string;
  title: string | null;
  /** `OpenAPI <v> · <title> · v<version>` — the contract's own identity line. */
  contractLine: string;
  operationCount: number;
  /** How many operations document a `401`. */
  authRequiredCount: number;
  requestMediaTypes: string[];
  errorCodes: string[];
  /**
   * A first request that is safe to suggest: the first read operation the
   * contract documents NO `401` for, so it works before a credential exists.
   * Falls back to the first read operation, then to nothing — never invented.
   */
  firstRequest: ApiEndpoint | null;
}

export function quickStartFacts(schema: ApiOpenApiResponse, rows: ApiEndpoint[]): QuickStartFacts {
  const gets = rows.filter((r) => r.method === 'get');
  return {
    basePath: apiBasePath(schema),
    apiVersion: schema.info?.version ?? null,
    openApiVersion: schema.openapi,
    title: schema.info?.title ?? null,
    contractLine: [
      `OpenAPI ${schema.openapi}`,
      schema.info?.title,
      schema.info?.version ? `v${schema.info.version}` : null,
    ]
      .filter(Boolean)
      .join(' · '),
    operationCount: rows.length,
    authRequiredCount: rows.filter((r) => r.authRequired).length,
    requestMediaTypes: requestMediaTypes(rows),
    errorCodes: documentedErrorCodes(rows),
    firstRequest: gets.find((r) => !r.authRequired) ?? gets[0] ?? null,
  };
}

// --- generated code samples --------------------------------------------------

export type SampleId = 'curl' | 'python' | 'javascript';

export interface CodeSample {
  id: SampleId;
  /** Tab label and part of the copy button's accessible name. */
  label: string;
  code: string;
}

/** The declared request media type, or null when the operation declares no
 *  request body. Never defaulted to JSON. */
function declaredMediaType(row: ApiEndpoint): string | null {
  const keys = Object.keys(row.requestBody?.content ?? {});
  return keys.length > 0 ? keys[0] : null;
}

/** Required header parameters, as the contract declares them. A header the
 *  document marks optional is left out of the sample and shown in the
 *  parameters table instead — its declared `required` flag is not overridden. */
function requiredHeaders(row: ApiEndpoint): OpenApiParameter[] {
  return row.parameters.filter((p) => p.in === 'header' && p.required === true);
}

/**
 * The request target: the path EXACTLY as the contract lists it (already
 * complete, base path included), plus every REQUIRED query parameter as a
 * `name={name}` placeholder. Optional parameters are never filled in with a
 * made-up value, and `{name}` is the contract's own placeholder syntax.
 */
export function samplePath(row: ApiEndpoint): string {
  const required = row.parameters.filter((p) => p.in === 'query' && p.required === true);
  if (required.length === 0) return row.path;
  return `${row.path}?${required.map((p) => `${p.name}={${p.name}}`).join('&')}`;
}

/** Emitted for a non-GET operation the contract declares no `requestBody` for.
 *  Deliberately does not assert whether a body is expected: seven operations are
 *  in this state and the document does not distinguish "reads a raw body,
 *  described in prose" from "takes no body at all". */
const NO_BODY_SCHEMA_NOTE =
  'The contract declares no request-body schema for this operation — see Purpose.';

/**
 * cURL / Python / JavaScript for one operation, generated from that operation's
 * own contract: its method, its path, its required parameters, its declared
 * request media type, and whether it documents a `401`. Nothing is added that
 * the contract does not state — no SDK, no client library, no invented body, no
 * host literal, and no header the operation does not require.
 */
export function codeSamples(row: ApiEndpoint): CodeSample[] {
  const path = samplePath(row);
  const method = row.method.toUpperCase();
  const mediaType = declaredMediaType(row);
  const headers = requiredHeaders(row);
  const hasBody = row.requestBody !== undefined;
  const bodyless = !hasBody && row.method !== 'get';

  // --- cURL ---
  const curlParts: string[] = [
    row.method === 'get'
      ? `curl "$${SAMPLE_BASE_ENV}${path}"`
      : `curl -X ${method} "$${SAMPLE_BASE_ENV}${path}"`,
  ];
  if (row.authRequired) curlParts.push(`-H "Authorization: Bearer $${SAMPLE_CREDENTIAL_ENV}"`);
  if (mediaType) curlParts.push(`-H "Content-Type: ${mediaType}"`);
  for (const h of headers) curlParts.push(`-H "${h.name}: {${h.name}}"`);
  if (hasBody) curlParts.push(`--data "$${SAMPLE_BODY_ENV}"`);
  const curl = [...(bodyless ? [`# ${NO_BODY_SCHEMA_NOTE}`] : []), curlParts.join(' \\\n  ')].join(
    '\n',
  );

  // --- Python (standard library only) ---
  const py: string[] = [];
  if (bodyless) py.push(`# ${NO_BODY_SCHEMA_NOTE}`);
  py.push('import json', 'import os', 'import urllib.request', '');
  py.push(`url = os.environ["${SAMPLE_BASE_ENV}"] + "${path}"`);
  if (hasBody) py.push(`body = os.environ["${SAMPLE_BODY_ENV}"].encode()`);
  py.push(
    `request = urllib.request.Request(url, ${hasBody ? 'data=body, ' : ''}method="${method}")`,
  );
  if (row.authRequired) {
    py.push(
      `request.add_header("Authorization", "Bearer " + os.environ["${SAMPLE_CREDENTIAL_ENV}"])`,
    );
  }
  if (mediaType) py.push(`request.add_header("Content-Type", "${mediaType}")`);
  for (const h of headers) py.push(`request.add_header("${h.name}", "{${h.name}}")`);
  py.push(
    'with urllib.request.urlopen(request) as response:',
    '    print(json.dumps(json.load(response), indent=2))',
  );

  // --- JavaScript (global fetch, no library) ---
  const js: string[] = [];
  if (bodyless) js.push(`// ${NO_BODY_SCHEMA_NOTE}`);
  js.push(`const url = process.env.${SAMPLE_BASE_ENV} + "${path}";`);
  const jsHeaders: string[] = [];
  if (row.authRequired) {
    jsHeaders.push(
      '    Authorization: "Bearer " + process.env.' + SAMPLE_CREDENTIAL_ENV + ',',
    );
  }
  if (mediaType) jsHeaders.push(`    "Content-Type": "${mediaType}",`);
  for (const h of headers) jsHeaders.push(`    "${h.name}": "{${h.name}}",`);
  js.push('const response = await fetch(url, {');
  js.push(`  method: "${method}",`);
  if (jsHeaders.length > 0) js.push('  headers: {', ...jsHeaders, '  },');
  if (hasBody) js.push(`  body: process.env.${SAMPLE_BODY_ENV},`);
  js.push('});');
  js.push('if (!response.ok) throw new Error("Request failed: " + response.status);');
  js.push('const data = await response.json();');

  return [
    { id: 'curl', label: 'cURL', code: curl },
    { id: 'python', label: 'Python', code: py.join('\n') },
    { id: 'javascript', label: 'JavaScript', code: js.join('\n') },
  ];
}

// --- schema/example rendering helpers (pure) ---------------------------------

/** Resolve a local `#/components/schemas/<Name>` reference ONE level, and only
 *  when the named schema is really present. Anything else is returned verbatim —
 *  a missing target is never replaced with an invented shape. */
export function resolveSchema(
  value: unknown,
  schema: ApiOpenApiResponse,
): { value: unknown; resolvedFrom: string | null } {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const ref = (value as { $ref?: unknown }).$ref;
    if (typeof ref === 'string') {
      const match = /^#\/components\/schemas\/(.+)$/.exec(ref);
      const target = match ? schema.components?.schemas?.[match[1]] : undefined;
      if (match && target !== undefined) return { value: target, resolvedFrom: match[1] };
    }
  }
  return { value, resolvedFrom: null };
}

export function collectExamples(media?: OpenApiMediaType): { name: string; value: unknown }[] {
  if (!media) return [];
  const out: { name: string; value: unknown }[] = [];
  if (media.example !== undefined) out.push({ name: 'example', value: media.example });
  for (const [name, entry] of Object.entries(media.examples ?? {})) {
    out.push({ name, value: entry?.value });
  }
  return out;
}

export function stringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2) ?? String(value);
  } catch {
    // A cyclic or non-serializable fragment is reported honestly, never faked.
    return 'This fragment could not be displayed as JSON.';
  }
}
