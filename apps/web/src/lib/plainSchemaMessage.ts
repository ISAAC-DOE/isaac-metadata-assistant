/**
 * PLAIN WORDS FOR A VALIDATOR MESSAGE (2026-11-17, owner: "pages … that read like an
 * engineer wrote it").
 *
 * The official schema check reports in jsonschema's own phrasing —
 * `'descriptors' is a required property`, `Additional properties are not allowed
 * ('x' was unexpected)`. Those strings are exact and stay on the page, behind a
 * Details disclosure; this turns the common ones into one plain line to lead with.
 *
 * COPY ONLY. Nothing here decides validity: the message is the validator's, the
 * verdict is the validator's, and a message this does not recognise falls back to a
 * generic plain line rather than a guess at what it means.
 *
 * The glosses are for TOP-LEVEL record blocks only, each read from that block's own
 * properties in `schema/isaac_record_v1.json` (for example `descriptors` holds
 * `outputs[]` of derived values with `generated_by`; `measurement` requires `series`
 * and `qc`). A nested property is named as it is, with no gloss invented for it.
 */

/** Top-level blocks of the official record, glossed from the schema's own contents. */
export const TOP_LEVEL_GLOSSES: Readonly<Record<string, string>> = Object.freeze({
  isaac_record_version: 'the record format version',
  record_id: 'the record’s id',
  record_type: 'the kind of record',
  record_domain: 'the scientific domain',
  source_type: 'where the data came from',
  timestamps: 'when it was created and measured',
  sample: 'the material and its form',
  system: 'the technique, facility and instrument',
  context: 'the environment and temperature',
  measurement: 'the measured data and its quality check',
  links: 'links to other records',
  assets: 'the data files the record points to',
  descriptors: 'the processed results',
  attribution: 'who uploaded and contributed',
});

/** The line used when a message is not one of the shapes below. */
export const GENERIC_PLAIN_LINE = 'This value doesn’t match the record rules.';

const TYPE_WORDS: Readonly<Record<string, string>> = {
  string: 'text',
  number: 'a number',
  integer: 'a whole number',
  boolean: 'yes or no',
  object: 'a group of fields',
  array: 'a list',
  null: 'empty',
};

/** True when `path` addresses the record itself rather than something inside it. */
function isRoot(path: string | undefined): boolean {
  if (path === undefined) return true;
  const p = path.trim();
  return p === '' || p === '$' || p === 'record';
}

function named(prop: string, path: string | undefined): string {
  const gloss = isRoot(path) ? TOP_LEVEL_GLOSSES[prop] : undefined;
  return gloss ? `${prop} (${gloss})` : prop;
}

/** `'a', 'b'` → `['a', 'b']`; tolerant of either quote style. */
function quotedNames(list: string): string[] {
  return Array.from(list.matchAll(/['"]([^'"]+)['"]/g), (m) => m[1]);
}

function truncate(value: string, max = 40): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

/**
 * One plain line for a validator message, or the generic line when the shape is not
 * recognised. `path` is the error's location (`$` for the record itself) and is used
 * only to decide whether a top-level gloss applies.
 */
export function plainSchemaMessage(message: string, path?: string): string {
  const m = message.trim();

  // required — `'descriptors' is a required property`
  const required = /^'?([^'\s]+)'? is a required property$/.exec(m);
  if (required) return `Missing: ${named(required[1], path)}.`;
  // A bare "is a required property" names nothing; say only that something is missing.
  if (/^is a required property$/.test(m)) return 'Something required is missing here.';

  // additionalProperties — `Additional properties are not allowed ('x', 'y' were unexpected)`
  const extra = /^Additional properties are not allowed \((.+) (?:was|were) unexpected\)$/.exec(m);
  if (extra) {
    const names = quotedNames(extra[1]);
    if (names.length > 0) {
      return `Not part of the record format: ${names.join(', ')}.`;
    }
    return 'This holds a field the record format does not have.';
  }

  // enum — `'xyz' is not one of ['a', 'b']`
  const enumMatch = /^(.+) is not one of \[.*\]$/.exec(m);
  if (enumMatch) {
    const value = enumMatch[1].replace(/^['"]|['"]$/g, '');
    return `“${truncate(value)}” isn’t one of the allowed choices.`;
  }

  // type — `'abc' is not of type 'number'` / `5 is not of type 'string', 'null'`
  const typeMatch = /^.+ is not of type (.+)$/.exec(m);
  if (typeMatch) {
    const words = quotedNames(typeMatch[1]).map((t) => TYPE_WORDS[t] ?? t);
    if (words.length > 0) return `This should be ${words.join(' or ')}.`;
  }

  // minLength / maxLength — `'' is too short`
  if (/ is too short$/.test(m)) return 'This is too short.';
  if (/ is too long$/.test(m)) return 'This is too long.';

  // pattern — `'abc' does not match '^[0-9]+$'`
  const pattern = /^(.+) does not match '.*'$/.exec(m);
  if (pattern) {
    const value = pattern[1].replace(/^['"]|['"]$/g, '');
    return `“${truncate(value)}” isn’t in the expected format.`;
  }

  return GENERIC_PLAIN_LINE;
}

/**
 * jsonschema's other message tails — shapes this file has no plain line for, but which
 * are still the validator's phrasing rather than a sentence ISAAC wrote. These get the
 * generic line, with the exact text behind Details.
 */
const JSONSCHEMA_TAILS: readonly RegExp[] = [
  / is (?:less|greater) than(?: or equal to)? /,
  / is not a multiple of /,
  / is not a '[^']+'$/,
  / is not valid under any of the given schemas$/,
  / is valid under each of /,
  / should be non-empty$/,
  / does not have enough properties$/,
  / has too many properties$/,
  / has non-unique elements$/,
  / is a dependency of /,
  / is not allowed for /,
  / was expected$/,
  /^None is not /,
];

export interface SchemaMessageView {
  /** The line to lead with. */
  plain: string;
  /** The validator's exact text, for a Details disclosure — `null` when `plain` IS it. */
  raw: string | null;
}

/**
 * The plain line and, when it differs, the exact text to keep behind Details.
 *
 * A message in none of jsonschema's shapes is a sentence ISAAC's own checks wrote
 * ("system.instrument.name needs confirmation") and is shown as it is: replacing it
 * with the generic line would hide what it says.
 */
export function describeSchemaMessage(message: string, path?: string): SchemaMessageView {
  const plain = plainSchemaMessage(message, path);
  if (plain !== GENERIC_PLAIN_LINE) return { plain, raw: message };
  const m = message.trim();
  if (JSONSCHEMA_TAILS.some((re) => re.test(m))) return { plain, raw: message };
  return { plain: message, raw: null };
}
