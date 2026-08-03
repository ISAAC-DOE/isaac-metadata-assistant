import { describe, it, expect } from 'vitest';

import {
  UNTAGGED_GROUP,
  apiBasePath,
  codeSamples,
  collectExamples,
  documentedErrorCodes,
  flattenOpenApi,
  groupEndpoints,
  isErrorCode,
  quickStartFacts,
  requestMediaTypes,
  resolveSchema,
  samplePath,
  stringify,
  tagDescriptions,
} from '../lib/apiDocsModel';
import type { ApiOpenApiResponse } from '../lib/types';
import { openApiFixture } from '../test/apiFixtures';

/**
 * The API tab's derivation layer, tested WITHOUT React.
 *
 * The load-bearing change this file guards is the grouping fix. The previous
 * helper inferred a group from the path segment after `/api/` and its docstring
 * asserted the backend assigned no OpenAPI `tags`; the backend now assigns 14 of
 * them, and their names are nothing like those segments. Grouping is therefore
 * derived from the document's own `tags`, ordered by the document's own
 * registration order, with an explicit untagged bucket. Several tests below fail
 * outright if grouping ever reverts to path-segment inference, because the group
 * names and their order are only obtainable from the `tags` array.
 */

const fixture = openApiFixture as unknown as ApiOpenApiResponse;

function doc(partial: Partial<ApiOpenApiResponse>): ApiOpenApiResponse {
  return { openapi: '3.1.0', paths: {}, ...partial };
}

describe('flattenOpenApi — grouping comes from the document’s real tags', () => {
  it('files each operation under its first declared tag, never a path segment', () => {
    const rows = flattenOpenApi(fixture);
    const byKey = new Map(rows.map((r) => [r.key, r]));

    expect(byKey.get('get /api/health')?.group).toBe('Health & Meta');
    expect(byKey.get('get /api/about')?.group).toBe('Health & Meta');
    expect(byKey.get('get /api/experiments/{id}')?.group).toBe('Experiments');
    expect(byKey.get('post /api/experiments/{id}/answers')?.group).toBe('Drafts & Answers');
    expect(byKey.get('post /api/uploads')?.group).toBe('Uploads');
    expect(byKey.get('post /api/validate/record')?.group).toBe('Validation');

    // The path-segment groups the old helper produced must appear nowhere.
    const groups = new Set(rows.map((r) => r.group));
    for (const stale of ['health', 'about', 'experiments', 'answers', 'uploads', 'validate']) {
      expect(groups.has(stale), `stale inferred group leaked: ${stale}`).toBe(false);
    }
  });

  it('orders groups by the document’s registration order, not alphabetically', () => {
    const rows = flattenOpenApi(fixture);
    const order: string[] = [];
    for (const row of rows) if (order[order.length - 1] !== row.group) order.push(row.group);

    // Registration order in the fixture is deliberately non-alphabetical, and a
    // registered tag carried by no operation creates no group.
    expect(order).toEqual([
      'Health & Meta',
      'Experiments',
      'Drafts & Answers',
      'Uploads',
      'Validation',
      UNTAGGED_GROUP,
    ]);
    expect(order.includes('Schema & Vocabulary')).toBe(false);
    expect([...order].sort()).not.toEqual(order);
  });

  it('sorts an unregistered tag after every registered one, and untagged last', () => {
    const rows = flattenOpenApi(fixture);
    const groups = rows.map((r) => r.group);
    expect(groups.indexOf('Validation')).toBeGreaterThan(groups.lastIndexOf('Uploads'));
    expect(groups.lastIndexOf(UNTAGGED_GROUP)).toBe(groups.length - 1);
    expect(rows[rows.length - 1].path).toBe('/api/search');
    expect(rows[rows.length - 1].tagged).toBe(false);
  });

  it('marks an untagged operation as untagged rather than guessing a name', () => {
    const rows = flattenOpenApi(
      doc({ paths: { '/api/zeta': { get: { summary: 'Z' } } }, tags: [{ name: 'Alpha' }] }),
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].group).toBe(UNTAGGED_GROUP);
    expect(rows[0].tagged).toBe(false);
  });

  it('ignores an empty tag list and an empty tag string', () => {
    const rows = flattenOpenApi(
      doc({ paths: { '/api/a': { get: { tags: [] } }, '/api/b': { get: { tags: [''] } } } }),
    );
    expect(rows.map((r) => r.group)).toEqual([UNTAGGED_GROUP, UNTAGGED_GROUP]);
  });

  it('derives the authentication requirement from a documented 401, not from the path', () => {
    const rows = flattenOpenApi(fixture);
    const auth = Object.fromEntries(rows.map((r) => [r.key, r.authRequired]));
    expect(auth['get /api/health']).toBe(false);
    expect(auth['get /api/about']).toBe(true);
    expect(auth['post /api/uploads']).toBe(true);
    expect(rows.filter((r) => r.authRequired)).toHaveLength(rows.length - 1);
  });

  it('sorts responses numerically, so 404 precedes 422 and 200 precedes 401', () => {
    const rows = flattenOpenApi(fixture);
    const answers = rows.find((r) => r.key === 'post /api/experiments/{id}/answers');
    expect(answers?.responses.map((r) => r.code)).toEqual(['200', '401', '404', '422']);
  });

  it('is deterministic: the same document yields an identical model', () => {
    expect(JSON.stringify(flattenOpenApi(fixture))).toBe(JSON.stringify(flattenOpenApi(fixture)));
  });
});

describe('tagDescriptions / groupEndpoints', () => {
  it('takes each group description from the document’s registered tags', () => {
    const descriptions = tagDescriptions(fixture);
    expect(descriptions['Health & Meta']).toMatch(/liveness, deployment identity/i);
    expect(descriptions['Uploads']).toMatch(/always refuses/i);
    // Registered with no description: absent, never a placeholder.
    expect(descriptions['Experiments']).toBeUndefined();
    // Never registered at all.
    expect(descriptions['Validation']).toBeUndefined();
  });

  it('carries each row’s index in the FLAT list so one cursor spans every group', () => {
    const rows = flattenOpenApi(fixture);
    const groups = groupEndpoints(rows, tagDescriptions(fixture));
    const flat = groups.flatMap((g) => g.rows.map((r) => r.index));
    expect(flat).toEqual(rows.map((_r, i) => i));
    expect(groups[0].description).toMatch(/liveness/i);
    expect(groups.find((g) => g.key === 'Experiments')?.description).toBeUndefined();
  });
});

describe('apiBasePath — relative only, never an origin', () => {
  it('reports the shared /api prefix', () => {
    expect(apiBasePath(fixture)).toBe('/api');
  });

  it('reports a deployment base path when every documented path carries one', () => {
    expect(
      apiBasePath(doc({ paths: { '/base/api/health': { get: {} }, '/base/api/about': { get: {} } } })),
    ).toBe('/base/api');
  });

  it('reports nothing rather than a base that would be wrong for some paths', () => {
    expect(apiBasePath(doc({ paths: { '/api/a': { get: {} }, '/other/api/b': { get: {} } } }))).toBeNull();
    expect(apiBasePath(doc({ paths: {} }))).toBeNull();
    expect(apiBasePath(doc({ paths: { '/health': { get: {} } } }))).toBeNull();
  });

  it('never yields an origin, a scheme, or a host', () => {
    const base = apiBasePath(fixture) ?? '';
    expect(base.startsWith('/')).toBe(true);
    expect(base).not.toMatch(/:\/\/|\.|:\d/);
  });
});

describe('contract-wide derivations', () => {
  const rows = flattenOpenApi(fixture);

  it('lists only request media types the contract declares', () => {
    expect(requestMediaTypes(rows)).toEqual(['application/json']);
    expect(requestMediaTypes([])).toEqual([]);
  });

  it('lists every documented failure status, ascending, and nothing below 400', () => {
    expect(documentedErrorCodes(rows)).toEqual(['401', '403', '404', '413', '422']);
    expect(isErrorCode('304')).toBe(false);
    expect(isErrorCode('400')).toBe(true);
    expect(isErrorCode('default')).toBe(false);
  });

  it('quickStartFacts reports only what the document states', () => {
    const facts = quickStartFacts(fixture, rows);
    expect(facts.basePath).toBe('/api');
    expect(facts.apiVersion).toBe('0.1.0');
    expect(facts.openApiVersion).toBe('3.1.0');
    expect(facts.operationCount).toBe(rows.length);
    expect(facts.authRequiredCount).toBe(rows.length - 1);
    expect(facts.contractLine).toBe(
      'OpenAPI 3.1.0 · ISAAC Metadata Assistant API · v0.1.0',
    );
  });

  it('proposes as a first request the read operation with no documented 401', () => {
    const facts = quickStartFacts(fixture, rows);
    expect(facts.firstRequest?.key).toBe('get /api/health');
    expect(facts.firstRequest?.authRequired).toBe(false);
  });

  it('falls back to the first read operation, then to nothing — never invents one', () => {
    const allGuarded = doc({
      paths: { '/api/a': { get: { responses: { '401': { description: 'x' } } } } },
    });
    expect(quickStartFacts(allGuarded, flattenOpenApi(allGuarded)).firstRequest?.path).toBe('/api/a');

    const writesOnly = doc({ paths: { '/api/a': { post: {} } } });
    expect(quickStartFacts(writesOnly, flattenOpenApi(writesOnly)).firstRequest).toBeNull();
  });
});

describe('codeSamples — generated from the operation’s own contract', () => {
  const rows = flattenOpenApi(fixture);
  const row = (key: string) => {
    const found = rows.find((r) => r.key === key);
    if (!found) throw new Error(`fixture has no ${key}`);
    return found;
  };

  it('offers exactly cURL, Python and JavaScript', () => {
    expect(codeSamples(row('get /api/health')).map((s) => s.id)).toEqual([
      'curl',
      'python',
      'javascript',
    ]);
    expect(codeSamples(row('get /api/health')).map((s) => s.label)).toEqual([
      'cURL',
      'Python',
      'JavaScript',
    ]);
  });

  it('uses the real method and the real path, and no host literal anywhere', () => {
    for (const sample of codeSamples(row('post /api/experiments/{id}/answers'))) {
      expect(sample.code).toContain('/api/experiments/{id}/answers');
      expect(sample.code).toContain('ISAAC_BASE_URL');
      expect(sample.code).toMatch(/POST/);
      expect(sample.code).not.toMatch(/https?:\/\//);
      expect(sample.code.toLowerCase()).not.toContain('localhost');
      expect(sample.code).not.toContain('127.0.0.1');
    }
  });

  it('omits -X for a read and includes the method for a write', () => {
    const [readCurl] = codeSamples(row('get /api/health'));
    const [writeCurl] = codeSamples(row('post /api/uploads'));
    expect(readCurl.code.startsWith('curl "$ISAAC_BASE_URL/api/health"')).toBe(true);
    expect(readCurl.code).not.toContain('-X');
    expect(writeCurl.code).toContain('curl -X POST "$ISAAC_BASE_URL/api/uploads"');
  });

  it('sends the credential header only where the contract documents a 401', () => {
    const guarded = codeSamples(row('get /api/about'));
    const open = codeSamples(row('get /api/health'));
    for (const sample of guarded) expect(sample.code).toContain('Authorization');
    for (const sample of open) expect(sample.code).not.toContain('Authorization');
    // The credential is always read from the environment, never inlined, and the
    // deployment's own variable name is never printed.
    for (const sample of guarded) {
      expect(sample.code).toContain('ISAAC_API_CREDENTIAL');
      expect(sample.code.toLowerCase()).not.toContain('api_key');
      expect(sample.code.toLowerCase()).not.toContain('apikey');
    }
  });

  it('declares a Content-Type only where the contract declares a request body', () => {
    const withBody = codeSamples(row('post /api/experiments/{id}/answers'));
    const withoutBody = codeSamples(row('post /api/validate/record'));
    for (const sample of withBody) expect(sample.code).toContain('application/json');
    for (const sample of withoutBody) {
      expect(sample.code).not.toContain('Content-Type');
      expect(sample.code).not.toContain('ISAAC_REQUEST_BODY');
      // ...and it SAYS why, rather than silently omitting the body.
      expect(sample.code).toContain('declares no request-body schema for this operation');
    }
  });

  it('reads the request body from the environment instead of inventing one', () => {
    const [curl, python, js] = codeSamples(row('post /api/experiments/{id}/answers'));
    expect(curl.code).toContain('--data "$ISAAC_REQUEST_BODY"');
    expect(python.code).toContain('os.environ["ISAAC_REQUEST_BODY"]');
    expect(js.code).toContain('process.env.ISAAC_REQUEST_BODY');
    // The fixture's own example value is never smuggled in as a real payload.
    expect(curl.code).not.toContain('CuO2_merged.xdi');
  });

  it('appends required query parameters as the contract’s own placeholder, and omits optional ones', () => {
    expect(samplePath(row('get /api/search'))).toBe('/api/search?q={q}');
    for (const sample of codeSamples(row('get /api/search'))) {
      expect(sample.code).toContain('/api/search?q={q}');
      expect(sample.code).not.toContain('limit=');
    }
  });

  it('sends a header parameter only when the contract declares it required', () => {
    const declaredOptional = codeSamples(row('post /api/experiments/{id}/answers'));
    for (const sample of declaredOptional) expect(sample.code).not.toContain('If-Match');

    const required = flattenOpenApi(
      doc({
        paths: {
          '/api/thing': {
            post: {
              tags: ['T'],
              parameters: [{ name: 'If-Match', in: 'header', required: true }],
            },
          },
        },
      }),
    )[0];
    const [curl, python, js] = codeSamples(required);
    expect(curl.code).toContain('-H "If-Match: {If-Match}"');
    expect(python.code).toContain('request.add_header("If-Match", "{If-Match}")');
    expect(js.code).toContain('"If-Match": "{If-Match}",');
  });

  it('uses the standard library only — no SDK, no client package, no import of one', () => {
    for (const key of ['get /api/health', 'post /api/experiments/{id}/answers']) {
      const [, python, js] = codeSamples(row(key));
      expect(python.code).toContain('import urllib.request');
      expect(python.code).not.toMatch(/import requests|isaac_client|pip install/);
      expect(js.code).toContain('await fetch(url');
      expect(js.code).not.toMatch(/require\(|from ['"]@|axios|npm install/);
    }
  });

  it('is deterministic', () => {
    const a = JSON.stringify(codeSamples(row('post /api/experiments/{id}/answers')));
    const b = JSON.stringify(codeSamples(row('post /api/experiments/{id}/answers')));
    expect(a).toBe(b);
  });
});

describe('schema/example helpers', () => {
  it('resolves a local $ref one level and names what it resolved', () => {
    const out = resolveSchema({ $ref: '#/components/schemas/SyntheticFixtureError' }, fixture);
    expect(out.resolvedFrom).toBe('SyntheticFixtureError');
    expect(out.value).toMatchObject({ title: 'SyntheticFixtureError' });
  });

  it('returns an unresolvable $ref verbatim instead of inventing a shape', () => {
    const ref = { $ref: '#/components/schemas/SyntheticFixtureAbsentTarget' };
    const out = resolveSchema(ref, fixture);
    expect(out.resolvedFrom).toBeNull();
    expect(out.value).toBe(ref);
  });

  it('collects an inline example and named examples, in that order', () => {
    expect(
      collectExamples({ example: 1, examples: { second: { value: 2 } } }).map((e) => e.name),
    ).toEqual(['example', 'second']);
    expect(collectExamples(undefined)).toEqual([]);
  });

  it('reports a non-serializable fragment honestly rather than faking JSON', () => {
    const cyclic: Record<string, unknown> = {};
    cyclic.self = cyclic;
    expect(stringify(cyclic)).toBe('This fragment could not be displayed as JSON.');
  });
});
