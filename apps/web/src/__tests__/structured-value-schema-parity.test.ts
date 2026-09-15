/**
 * THE SERIES ENTRY FORM REQUIRES WHAT THE OFFICIAL SCHEMA REQUIRES, and this
 * test is what keeps the two in step.
 *
 * `StructuredValueEntry` validates a hand-entered `measurement.series` before it
 * is confirmed. It used to require only "a list of objects", which is how
 * `[{"energy_eV": 8979, "mu": 0.412}]` was accepted over HTTP on a record
 * created through the product: the pending count fell 3 → 1, the question read
 * as answered, and export then refused with `series has no series_id — cannot
 * key its evidence`. A scientist could answer everything and hold a record that
 * could not be exported.
 *
 * `CLAUDE.md` §1 makes `schema/isaac_record_v1.json` the authority on required
 * fields, so the fix must not be a second opinion about what is required. The
 * component names the keys (it cannot read a file at runtime) and this test
 * reads the VENDORED SCHEMA and asserts the two agree — so a schema refresh
 * either moves both or fails here, and neither can drift silently.
 */
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import { SERIES_REQUIRED_KEYS, seriesShapeError } from '../components/StructuredValueEntry';

/** The repo root, from `apps/web/src/__tests__`. */
const REPO_ROOT = resolve(__dirname, '..', '..', '..', '..');

interface JsonSchemaNode {
  properties?: Record<string, JsonSchemaNode>;
  items?: JsonSchemaNode;
  required?: string[];
  [key: string]: unknown;
}

/** Every `series` property node in the schema, wherever it is nested. */
function seriesItemNodes(node: unknown, found: JsonSchemaNode[] = []): JsonSchemaNode[] {
  if (Array.isArray(node)) {
    for (const child of node) seriesItemNodes(child, found);
    return found;
  }
  if (node !== null && typeof node === 'object') {
    const obj = node as JsonSchemaNode;
    const series = obj.properties?.series;
    if (series?.items !== undefined) found.push(series.items);
    for (const value of Object.values(obj)) seriesItemNodes(value, found);
  }
  return found;
}

describe('the series form and the official schema require the same keys', () => {
  const schema = JSON.parse(
    readFileSync(join(REPO_ROOT, 'schema', 'isaac_record_v1.json'), 'utf8'),
  ) as JsonSchemaNode;
  const nodes = seriesItemNodes(schema);

  it('is not vacuous — the schema really declares required series keys', () => {
    expect(nodes.length, 'no `series` items node found in the vendored schema').toBeGreaterThan(0);
    expect(
      nodes[0].required,
      'the schema\'s series item declares no `required` list; this guard has nothing to compare',
    ).toBeDefined();
  });

  it('MUTATION-GUARDED: every key the form requires is one the schema requires', () => {
    /*
     * MUTATION: emptying `SERIES_REQUIRED_KEYS` makes the payload test below RED;
     * adding a key the schema does not require makes THIS one red.
     *
     * A SUBSET, NOT AN EQUALITY, and the asymmetry is the point. The form gates
     * on `series_id` alone while the schema requires three — see
     * `SERIES_REQUIRED_KEYS` for why (the other two are enforced by official
     * validation at export, which names them precisely, and requiring them here
     * turned 13 unrelated tests red). What must hold is that the form never
     * invents a requirement of its own: the schema is the authority
     * (`CLAUDE.md` §1), so anything this form demands has to appear in the
     * schema's own `required` list.
     */
    const fromSchema = new Set(nodes[0].required ?? []);
    const invented = [...SERIES_REQUIRED_KEYS].filter((k) => !fromSchema.has(k));
    expect(
      invented,
      'the series entry form requires a key `schema/isaac_record_v1.json` does not. ' +
        'The schema decides what a record must carry; this form may only enforce a ' +
        'subset of it, never add to it.',
    ).toEqual([]);
    // …and it is not vacuously a subset: it demands at least one real key.
    expect(SERIES_REQUIRED_KEYS.length).toBeGreaterThan(0);
  });

  it('the keys it does NOT gate on are still the schema\'s, and still caught at export', () => {
    /*
     * Recorded so the narrowing is visible rather than implied: the two keys this
     * form lets through are schema-required, and the walk that measured this also
     * measured official validation refusing them at export.
     */
    const ungated = (nodes[0].required ?? []).filter(
      (k) => !([...SERIES_REQUIRED_KEYS] as string[]).includes(k),
    );
    expect(ungated.sort()).toEqual(['channels', 'independent_variables']);
  });

  it('rejects the exact payload that was accepted and then refused at export', () => {
    const wasAccepted = [
      { energy_eV: 8979.0, mu: 0.412 },
      { energy_eV: 8984.0, mu: 0.981 },
    ];
    const problem = seriesShapeError(wasAccepted);
    expect(problem, 'the payload that produced two export errors is still accepted').not.toBeNull();
    expect(problem).toContain('series_id');
    // …and it says WHY, rather than only naming a key.
    expect(problem).toContain('cannot be exported');
  });

  it('accepts a series that carries every required key', () => {
    /*
     * The negative control: a guard that rejected everything would pass the test
     * above while making the form unusable.
     */
    const complete = [
      {
        series_id: 'averaged_spectrum',
        independent_variables: [{ name: 'energy', unit: 'eV', values: [8979, 8984] }],
        channels: [{ name: 'mu', values: [0.412, 0.981] }],
      },
    ];
    expect(seriesShapeError(complete)).toBeNull();
  });

  it('accepts a series carrying only the gated key — the narrowing, asserted', () => {
    /*
     * The other half of the narrowing: a series with `series_id` and nothing
     * else passes THIS form. That is deliberate, and it is what keeps the 13
     * unrelated tests honest rather than padded. Export still refuses it, which
     * is where the remaining two keys are enforced.
     */
    expect(seriesShapeError([{ series_id: 'averaged_spectrum' }])).toBeNull();
  });
});

describe('the conditions slot the series form points scientists at', () => {
  /*
   * The form tells a scientist that conditions the five questions do not ask
   * about belong in each series' `conditions` object, with their own keys. That
   * is a claim about the OFFICIAL SCHEMA, so it is checked against the schema
   * rather than trusted.
   *
   * If a future refresh closes the object — declares `properties` and
   * `additionalProperties: false` — the claim becomes false and this fails,
   * which is the point: the hint would then be telling scientists to write
   * something export would refuse.
   */
  const schema = JSON.parse(
    readFileSync(join(REPO_ROOT, 'schema', 'isaac_record_v1.json'), 'utf8'),
  ) as JsonSchemaNode;
  const items = seriesItemNodes(schema)[0];

  it('MUTATION-GUARDED: `conditions` exists and accepts arbitrary keys', () => {
    const conditions = items.properties?.conditions as JsonSchemaNode | undefined;
    expect(conditions, '`series[].conditions` is gone from the schema').toBeDefined();
    expect(conditions!.type).toBe('object');
    /*
     * BOTH HALVES MATTER. A declared `properties` list would mean only those
     * keys are meant; `additionalProperties: false` would mean a scientist's own
     * key is refused outright. Today neither is present, which is what makes
     * "your own keys" true.
     */
    expect(
      conditions!.properties,
      'the schema now declares specific condition properties — the form\'s "your own keys" hint needs revisiting',
    ).toBeUndefined();
    expect(
      (conditions as Record<string, unknown>).additionalProperties,
      'the schema now closes `conditions` — a scientist\'s own key would be refused at export',
    ).not.toBe(false);
  });

  it('is not vacuous — the schema describes the slot as operating conditions', () => {
    const conditions = items.properties?.conditions as JsonSchemaNode | undefined;
    expect(String((conditions as Record<string, unknown>).description ?? '')).toMatch(
      /conditions/i,
    );
  });
});

