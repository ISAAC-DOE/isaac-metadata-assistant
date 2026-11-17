/**
 * The plain line for a validator message (2026-11-17, owner's plain-language pass).
 *
 * Copy only: the validator's exact text is kept (behind Details) and nothing here
 * decides validity. These pin the shapes the helper recognises, the glosses it is
 * allowed to give (top-level blocks only, each checked against the vendored schema),
 * and the two fallbacks.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  GENERIC_PLAIN_LINE,
  TOP_LEVEL_GLOSSES,
  describeSchemaMessage,
  plainSchemaMessage,
} from '../lib/plainSchemaMessage';

const SCHEMA = JSON.parse(
  readFileSync(join(__dirname, '..', '..', '..', '..', 'schema', 'isaac_record_v1.json'), 'utf8'),
) as { properties: Record<string, unknown> };

describe('plainSchemaMessage', () => {
  it('names a missing top-level block with its gloss', () => {
    expect(plainSchemaMessage("'descriptors' is a required property", '$')).toBe(
      'Missing: descriptors (the processed results).',
    );
  });

  it('names a missing nested property with no invented gloss', () => {
    expect(plainSchemaMessage("'qc' is a required property", 'measurement')).toBe('Missing: qc.');
    // `sample` has a gloss at the top level, and none when it is a nested key.
    expect(plainSchemaMessage("'sample' is a required property", 'links.0')).toBe(
      'Missing: sample.',
    );
  });

  it('reads additionalProperties, enum, type, pattern and length messages', () => {
    expect(
      plainSchemaMessage("Additional properties are not allowed ('foo', 'bar' were unexpected)"),
    ).toBe('Not part of the record format: foo, bar.');
    expect(plainSchemaMessage("'xyz' is not one of ['a', 'b']")).toBe(
      '“xyz” isn’t one of the allowed choices.',
    );
    expect(plainSchemaMessage("'abc' is not of type 'number'")).toBe('This should be a number.');
    expect(plainSchemaMessage("5 is not of type 'string', 'null'")).toBe(
      'This should be text or empty.',
    );
    expect(plainSchemaMessage("'abc' does not match '^[0-9]+$'")).toBe(
      '“abc” isn’t in the expected format.',
    );
    expect(plainSchemaMessage("'' is too short")).toBe('This is too short.');
  });

  it('falls back to the generic plain line for anything else', () => {
    expect(plainSchemaMessage('something entirely different')).toBe(GENERIC_PLAIN_LINE);
  });

  it('glosses only blocks the vendored schema actually declares at the top level', () => {
    for (const key of Object.keys(TOP_LEVEL_GLOSSES)) {
      expect(SCHEMA.properties, key).toHaveProperty(key);
    }
  });
});

describe('describeSchemaMessage', () => {
  it('keeps the exact validator text for Details whenever the plain line differs', () => {
    const view = describeSchemaMessage("'descriptors' is a required property", '$');
    expect(view.plain).toBe('Missing: descriptors (the processed results).');
    expect(view.raw).toBe("'descriptors' is a required property");
  });

  it('gives an unrecognised jsonschema shape the generic line, raw text kept', () => {
    const view = describeSchemaMessage('3 is less than the minimum of 5');
    expect(view.plain).toBe(GENERIC_PLAIN_LINE);
    expect(view.raw).toBe('3 is less than the minimum of 5');
  });

  it('shows a sentence ISAAC wrote as it is, with nothing hidden', () => {
    const view = describeSchemaMessage('system.instrument.name needs confirmation');
    expect(view).toEqual({ plain: 'system.instrument.name needs confirmation', raw: null });
  });
});
