/**
 * THE GUARD THAT HAS TO STOP THE SIXTH CONSUMER, not re-pin today's five.
 *
 * ── WHAT KEPT RECURRING ──────────────────────────────────────────────────────
 *
 * `POST /api/experiments/{id}/validate` and `POST …/runs/{runId}/check` return an
 * `errors` list whose producer is one of three things: the vendored official ISAAC
 * schema, the no-guessing draft validator, or ISAAC's own anchored-pattern exactness
 * gate. `export.py` returns `official_report=None` for the last two, and until this
 * slice the wire carried nothing to distinguish them — so every consumer had to
 * remember an ordering rule it could only learn by reading `export.py`, and each one
 * re-derived it independently.
 *
 * FIXING THE RENDERERS WAS TRIED FOUR TIMES. The last attempt corrected `RunCard`,
 * `evidenceGraph` and `WorkflowProgressBanner`, and left the claim standing in
 * `ExportReadiness`, in `lib/experimentGraph.ts`, and in both machine-readable
 * contracts (two OpenAPI descriptions and the MCP `isaac_check_run` tool) — while a
 * guard that pinned the surfaces it knew about passed. **A list cannot notice an
 * omission from itself.**
 *
 * ── WHY `lib/experimentGraph.ts` SURVIVED EVERY SWEEP, WHICH IS THE LESSON ────
 *
 * It contains two NUL bytes (a `${kind}\0${source}\0${target}` dedup key), so `grep`
 * and `rg` WITHOUT `--text` drop every match in it and still exit 0. Three slices
 * searched for this defect and none of them could see the file. It carried the
 * plainest form of it — a note reading "Validation here is a DRY RUN against the
 * official ISAAC schema", emitted on `validate.dry_run && errors.length > 0`, which
 * is exactly the ambiguous case — plus an unconditional producer string and an edge
 * label saying the same thing.
 *
 * **So this file reads bytes and decodes them.** It never shells out to a text
 * search, and a NUL byte cannot hide a consumer from it.
 *
 * ── THE TWO INVARIANTS, AND WHAT EACH DOES NOT CATCH ─────────────────────────
 *
 * A. **The discriminator is READ IN ONE PLACE.** `official_validator_ran` may appear
 *    in `lib/officialAttribution.ts` (which derives from it) and in `lib/types.ts`
 *    (which declares it). Anywhere else is a consumer re-deriving the rule, which is
 *    the mechanism of every recurrence.
 *
 *    Does NOT catch: a consumer that calls `officialFindingSource` and then ignores
 *    the answer, or that branches on `dry_run` for a SOURCE claim without touching
 *    the new field. Invariant B is what covers the second; nothing here covers the
 *    first, and no static check can.
 *
 * B. **Attributing copy lives in ONE module.** In any file that consumes this payload
 *    — derived from the code, not listed — no string literal may both mention the
 *    official schema and attribute a finding or a verdict to it. The copy belongs in
 *    `lib/officialAttribution.ts`, where one edit fixes every surface at once.
 *
 *    Does NOT catch: a paraphrase that never says "official" ("the upstream schema
 *    rejected this", "v1.05 refused it"); an attribution built by concatenation at
 *    runtime; copy in a `.css` `content:` property or an `aria-label` composed from
 *    variables; a backend-sourced string rendered verbatim (the server-side guard
 *    `apps/api/tests/test_official_verdict_attribution.py` covers those); and any
 *    surface that consumes the payload without matching a consumer signal below.
 *
 * Neither invariant asserts anything about whether a claim is TRUE — only about where
 * it may be made. Truth is what `officialFindingSource` is for, and
 * `apps/api/tests/test_official_validator_ran_discriminator.py` is what measures it.
 *
 * ── THE SIXTH CONSUMER, WHICH THE FIRST VERSION OF THIS FILE DID NOT CATCH ────
 *
 * The signals below started as member accesses on the payload. That set finds every
 * file that READS the response — and the sixth surface does not read it. It reads
 * `ValidationResult`, a DIFFERENT type, two files away: `screens/ExportReadiness.tsx`
 * converts the payload with `lib/adapt.ts::toValidationResult` (which sets no
 * `schemaOk`, because it predates the split) and hands the result to
 * `components/VerdictCard.tsx`, which renders **"Invalid against official ISAAC
 * schema v1.05 — N errors. Export blocked."** from `ok` alone.
 *
 * Measured over HTTP: on an exported record whose written artifact was deleted out of
 * band, `POST /validate` answers `ok: false, dry_run: false,
 * official_validator_ran: false, unavailable: true` — and that card claimed the
 * upstream schema rejected a document `validate_official` never opened. It is §12's
 * named precedent, reached again by a route no payload-shaped guard could see.
 *
 * So `ValidationResult` is a consumer signal too. That pulls `VerdictCard` in, whose
 * attributions are LEGITIMATE when its producer sets `schemaOk` from a real schema
 * verdict — they are therefore in `ALLOWED`, and the entries say what makes them
 * legitimate. **What this guard still cannot check is that the precondition holds**:
 * that every producer of a `ValidationResult` either sets `schemaOk` faithfully or
 * declines to render the card. `ExportReadiness` does the second (`officialMaySpeak`)
 * and `__tests__/export-readiness-no-verdict.test.tsx` pins it — but that is a
 * behavioural test of one screen, not an invariant over all producers. A seventh
 * producer could still build a `ValidationResult` badly, and only a review would see
 * it. Recorded here rather than implied, because the whole lesson of this defect is
 * that a guard which does not name its blind spot gets read as covering it.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC = join(__dirname, '..');

/** The one module allowed to derive from the discriminator and to own the copy. */
const HELPER = 'lib/officialAttribution.ts';

/** The one module allowed to DECLARE the field. Declaring is not deriving. */
const CONTRACT = 'lib/types.ts';

const DISCRIMINATOR = 'official_validator_ran';

/**
 * What makes a file a consumer of this payload. Deliberately structural: a member
 * access on the `official` verdict block, a read of `dry_run`, or a call into the
 * shared module. A file matching any of these renders or reasons about findings whose
 * producer is the thing under guard.
 */
const CONSUMER_SIGNALS: RegExp[] = [
  /\.official\??\.(errors|ok|unavailable|dry_run|official_validator_ran)\b/,
  /\.dry_run\b/,
  /\bofficialFindingSource\b/,
  /\bofficialCheckedDocument\b/,
  // THE SIXTH CONSUMER'S SIGNAL — the adapted type, not the payload. See the header
  // note: `ExportReadiness` -> `adapt.toValidationResult` -> `VerdictCard` reached the
  // official-schema claim without any file in that chain touching a payload key, so
  // the four signals above could not see it.
  /\bValidationResult\b/,
];

/**
 * Words that turn a mention of the official schema into an ATTRIBUTION of findings.
 * "The official ISAAC schema requires a descriptor" is a statement about the schema;
 * "Official ISAAC schema errors" is a claim about who produced something.
 */
const ATTRIBUTION_MARKERS = [
  'error',
  'finding',
  'reported',
  'reject',
  'does not pass',
  'did not pass',
  'passed',
  'all pass',
  'verdict',
  'invalid against',
  'valid against',
];

/**
 * Exact literals that mention the official schema and an attribution marker and are
 * NEVER a claim about who produced a finding. Keyed by file so an entry cannot leak
 * to another surface, and each carries its reason.
 *
 * THIS LIST RATCHETS PER COPY UNIT, which is the pattern this repository already
 * uses for honesty guards. Adding an entry is a visible diff line that has to be
 * justified; that is the point, and it is why there is no wildcard.
 */
const ALLOWED: { file: string; literal: string; why: string }[] = [
  {
    file: 'lib/evidenceGraph.ts',
    literal:
      'one finding of the run check (POST /api/experiments/{id}/runs/{runId}/check) — its `blockers`, `draft.errors` and `official.errors` lists',
    why:
      'A node PRODUCER string: it names the OPERATION and the three response keys a ' +
      'finding can arrive under. It attributes the finding to the request, not to a ' +
      'validator — which is the distinction the whole defect turns on, so the string ' +
      'that draws it explicitly must be allowed to say `official.errors`.',
  },
  // ── components/VerdictCard.tsx ────────────────────────────────────────────────
  //
  // `VerdictCard` renders `ValidationResult`, not this payload, and it is the ONE
  // surface whose whole job is to state the hard gate's verdict. Its attributions are
  // legitimate BECAUSE it branches on `schemaOk` — the official schema's own verdict,
  // kept beside `ok` exactly as `CLAUDE.md` §12 requires — and on `exactnessErrors`,
  // ISAAC's own gate, listed separately and named as ISAAC's. `RecordValidator` sets
  // both from `POST /api/validate/record`'s `schema_ok` / `exactness_errors`.
  //
  // WHAT THE EXEMPTION DOES NOT COVER, and the entries are worded so a reader sees it:
  // whether a PRODUCER of `ValidationResult` filled `schemaOk` faithfully. That is the
  // precondition, it is not statically checkable here, and it is exactly what failed
  // for `ExportReadiness` (see the header note). Do not read these entries as saying
  // the card is always right — only that its wording belongs to it.
  {
    file: 'components/VerdictCard.tsx',
    literal: 'Invalid against official ISAAC schema v1.05 — error. Export blocked.',
    why:
      "The `!schemaOk` branch, and `schemaOk` IS the vendored schema's own verdict — " +
      'this is the one place in the product where naming the official schema as the ' +
      'refuser is the accurate statement rather than an inference. Its truth depends ' +
      'entirely on the producer having set `schemaOk` from a real schema verdict, ' +
      'which this guard cannot check and which `ExportReadiness` got wrong once.',
  },
  {
    file: 'components/VerdictCard.tsx',
    literal: 'Valid against official ISAAC schema v1.05, and refused by ISAAC —',
    why:
      'The `schemaOk && exactnessErrors.length > 0` branch. It says the schema ' +
      'ACCEPTED the record and ISAAC refused it anyway, which is the §12 distinction ' +
      'stated in the strongest available form — the opposite of the conflation this ' +
      'guard exists to prevent, and therefore something no rule here should forbid.',
  },
  {
    file: 'components/VerdictCard.tsx',
    literal:
      'Refused — and not by the official ISAAC schema, whose verdict on this record is',
    why:
      'The third branch, for a refusal this client cannot explain. It exists so that ' +
      'an unexplained refusal says so rather than blaming upstream by default, and it ' +
      'reports the schema verdict it was actually given. It must never be reached ' +
      'with a fabricated `schemaOk: true`, which is why `ExportReadiness` declines to ' +
      'render this card at all rather than passing one.',
  },
  {
    file: 'components/VerdictCard.tsx',
    literal: 'Valid against official ISAAC schema v1.05.',
    why:
      'The PASS claim, rendered only when the producer reported a pass. A pass is ' +
      'unreachable without the official validator having run and said yes — ' +
      '`export.py` has one `ok=True` return and it sits after `validate_official` — ' +
      'so naming the schema on this branch is sound for every producer in the product.',
  },
  {
    file: 'components/VerdictCard.tsx',
    literal:
      'The official ISAAC schema accepts this record as written. ISAAC refuses it anyway, under a gate of its own, and blocks export. This is not an upstream schema error.',
    why:
      "The exactness detail card's body. Every clause here separates ISAAC's gate " +
      'from the vendored schema and says outright that this is not an upstream error, ' +
      'which is the §12 rule quoted back verbatim. Forbidding it would forbid the ' +
      'clearest statement of the very distinction being guarded.',
  },
  {
    file: 'components/VerdictCard.tsx',
    literal:
      'ISAAC also refuses these values under a gate of its own. They are listed apart from the schema errors above because the official schema accepts them.',
    why:
      'The heading note above the exactness list, on the mixed branch where BOTH ' +
      'gates found something. It attributes each list to its own gate and explains ' +
      'why they are rendered apart, which is the separation `CLAUDE.md` §12 says a ' +
      'future session must not collapse back together.',
  },
];

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      if (name === '__tests__' || name === 'test' || name === 'node_modules') continue;
      walk(full, out);
      continue;
    }
    if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name)) out.push(full);
  }
  return out;
}

/** Bytes in, text out. Never a text search: see the NUL-byte note above. */
function read(file: string): string {
  return readFileSync(file).toString('utf8');
}

/**
 * Comments out. Crude but conservative — it only ever removes text, so it cannot
 * invent a violation; it can only miss one that hides inside a string containing
 * `//`, which every literal checked below would still be caught by if it did not.
 */
function stripComments(text: string): string {
  let out = '';
  for (let i = 0; i < text.length; ) {
    if (text.startsWith('//', i)) {
      const j = text.indexOf('\n', i);
      i = j < 0 ? text.length : j;
    } else if (text.startsWith('/*', i)) {
      const j = text.indexOf('*/', i + 2);
      i = j < 0 ? text.length : j + 2;
    } else {
      out += text[i];
      i += 1;
    }
  }
  return out;
}

const LITERAL = /'((?:[^'\\\n]|\\.)*)'|"((?:[^"\\\n]|\\.)*)"|`((?:[^`\\]|\\.)*)`/gs;

/**
 * The literals of a file, with `${…}` interpolations REMOVED.
 *
 * Removing them matters: a template that calls `officialFindingsHeading(source)` is
 * routing through the helper, which is the compliant thing to do, and leaving the
 * expression text in would flag it for containing the word "official". What remains
 * is the copy the file itself wrote.
 */
function literals(code: string): string[] {
  const out: string[] = [];
  for (const match of code.matchAll(LITERAL)) {
    const raw = match[1] ?? match[2] ?? match[3] ?? '';
    out.push(raw.replace(/\$\{[^}]*\}/g, '').replace(/\s+/g, ' ').trim());
  }
  return out;
}

const FILES = walk(SRC).map((full) => ({
  rel: relative(SRC, full).split(/[\\/]/).join('/'),
  code: stripComments(read(full)),
}));

const CONSUMERS = FILES.filter(
  (f) => f.rel !== CONTRACT && CONSUMER_SIGNALS.some((p) => p.test(f.code)),
);

describe('the derivation itself', () => {
  it('finds the surfaces this defect was measured on', () => {
    // A DERIVATION CAN GO SILENT AS EASILY AS A LIST CAN GO STALE — a renamed field,
    // a restructured directory, a changed extension. These are a FLOOR, not the set:
    // the set is whatever the code says. Without this, every assertion below could
    // pass over an empty array.
    const rels = CONSUMERS.map((f) => f.rel);
    for (const expected of [
      'components/RunCard.tsx',
      'components/RunFindings.tsx',
      'components/ValidateReview.tsx',
      'screens/ExportReadiness.tsx',
      'lib/evidenceGraph.ts',
      // The fifth consumer, found by a byte-level scan after three text sweeps
      // missed it. If this ever drops out of the derived set, the reason is far more
      // likely to be that the scan broke than that the file stopped consuming.
      'lib/experimentGraph.ts',
      // The SIXTH, reached through `ValidationResult` rather than through the payload
      // — see the header note. It is on the floor so the `ValidationResult` signal
      // cannot be dropped without a failing test saying which surface it lost.
      'components/VerdictCard.tsx',
      // NOT NAMED BY ANY PRIOR SWEEP, and it needs no fix: it merges `blockers`,
      // `draft.errors` and `official.errors` into one list under source-neutral
      // headings and attributes nothing to any validator. It is on the floor because
      // "makes no claim today" is a property that can change in one commit, and this
      // is the guard that would then have something to say about it.
      'components/RunCompare.tsx',
    ]) {
      expect(rels, `the consumer derivation lost ${expected}`).toContain(expected);
    }
  });

  it('reads files the way a NUL byte cannot defeat', () => {
    const graph = FILES.find((f) => f.rel === 'lib/experimentGraph.ts');
    expect(graph, 'lib/experimentGraph.ts was not read at all').toBeTruthy();
    // The premise of the whole file, asserted rather than asserted-about: this source
    // really does contain NUL bytes, and this test really does see its content.
    expect(readFileSync(join(SRC, 'lib/experimentGraph.ts')).includes(0)).toBe(true);
    expect(graph!.code).toContain('officialFindingSource');
  });

  it('scans more than a handful of files', () => {
    // A `walk` that silently returned two files would make invariant B vacuous.
    expect(FILES.length).toBeGreaterThan(100);
  });
});

describe('A — the discriminator is read in exactly one place', () => {
  it(`only ${HELPER} derives from ${DISCRIMINATOR}`, () => {
    const offenders = FILES.filter(
      (f) => f.rel !== HELPER && f.rel !== CONTRACT && f.code.includes(DISCRIMINATOR),
    ).map((f) => f.rel);
    expect(
      offenders,
      `${offenders.join(', ')} reads \`${DISCRIMINATOR}\` directly. Call ` +
        '`officialFindingSource` instead. Every consumer that re-derived this rule ' +
        'for itself got it wrong at least once, which is why the rule has one home ' +
        `(${HELPER}) and the field has one reader.`,
    ).toEqual([]);
  });

  it(`${HELPER} does derive from it, and ${CONTRACT} does declare it`, () => {
    // The negative control for the assertion above: it would also pass if the field
    // had been deleted everywhere, or renamed, or never shipped.
    const helper = FILES.find((f) => f.rel === HELPER);
    const contract = FILES.find((f) => f.rel === CONTRACT);
    expect(helper?.code).toContain(`verdict.${DISCRIMINATOR} === true`);
    expect(helper?.code).toContain(`verdict.${DISCRIMINATOR} === false`);
    expect(contract?.code).toContain(`${DISCRIMINATOR}?: boolean`);
  });
});

describe('B — attributing copy lives in exactly one module', () => {
  it('no consumer of this payload writes its own official-schema attribution', () => {
    const offences: string[] = [];
    for (const file of CONSUMERS) {
      if (file.rel === HELPER) continue;
      for (const literal of literals(file.code)) {
        const low = literal.toLowerCase();
        if (!low.includes('official')) continue;
        if (!ATTRIBUTION_MARKERS.some((m) => low.includes(m))) continue;
        if (ALLOWED.some((a) => a.file === file.rel && a.literal === literal)) continue;
        offences.push(`${file.rel}: ${JSON.stringify(literal)}`);
      }
    }
    expect(
      offences,
      'These attribute a finding or a verdict to the official ISAAC schema from ' +
        `outside ${HELPER}:\n  ${offences.join('\n  ')}\n\n` +
        'CLAUDE.md §1 makes the vendored schema not ours to speak for and §12 forbids ' +
        'reporting an ISAAC gate refusal as an official-schema error. Take the wording ' +
        `from ${HELPER} (officialFindingsHeading / officialFindingsCaption / ` +
        'officialCleanSentence / officialExportBlockedSentence / officialFindingsNote / ' +
        'OFFICIAL_SOURCE_LABEL). If the string genuinely makes no claim about who ' +
        'produced a finding, add it to ALLOWED with a reason.',
    ).toEqual([]);
  });

  it('the helper actually carries such copy, keyed by the four sources', () => {
    // Negative control: invariant B also passes if the product says nothing at all.
    const helper = FILES.find((f) => f.rel === HELPER)!;
    const claims = literals(helper.code).filter((l) => {
      const low = l.toLowerCase();
      return low.includes('official') && ATTRIBUTION_MARKERS.some((m) => low.includes(m));
    });
    expect(claims.length).toBeGreaterThan(3);
    for (const source of ['official-schema', 'export-gate', 'no-verdict', 'unnamed']) {
      expect(helper.code).toContain(source);
    }
  });

  it('every ALLOWED entry still matches a literal in the file it names', () => {
    // A stale exemption is worse than a dead one: the next string to land on that
    // text inherits a permission nobody granted it.
    for (const entry of ALLOWED) {
      const file = FILES.find((f) => f.rel === entry.file);
      expect(file, `ALLOWED names ${entry.file}, which no longer exists`).toBeTruthy();
      expect(
        literals(file!.code),
        `ALLOWED holds a literal no longer present in ${entry.file}. Delete it.`,
      ).toContain(entry.literal);
      expect(entry.why.split(/\s+/).length).toBeGreaterThan(15);
    }
  });
});

describe('the withdrawn claims, which outlived the defect they described', () => {
  it('no consumer still says the wire carries no discriminator', () => {
    // These sentences were TRUE and are not. A future reader who believes one will
    // rebuild the ordering rule, so the sentences are guarded in comments as well as
    // in code — which is why this test reads the RAW file rather than `code`.
    const offences: string[] = [];
    for (const full of walk(SRC)) {
      const rel = relative(SRC, full).split(/[\\/]/).join('/');
      const raw = read(full);
      for (const phrase of [
        'no discriminator on the wire',
        'nothing on the payload to branch on',
        'the wire carries no discriminator',
      ]) {
        // A quoted, struck-through correction is the established way this repository
        // records a withdrawn claim, so `~~` immediately before the phrase is fine.
        const index = raw.toLowerCase().indexOf(phrase);
        if (index < 0) continue;
        const before = raw.slice(Math.max(0, index - 40), index);
        if (before.includes('~~') || before.includes('used to') || before.includes('~~"')) {
          continue;
        }
        offences.push(`${rel}: ${phrase}`);
      }
    }
    expect(
      offences,
      'These assert as standing fact something this slice made false. Strike the ' +
        'sentence in place (~~…~~) rather than deleting it, so a reader who remembers ' +
        `it sees that it was discharged:\n  ${offences.join('\n  ')}`,
    ).toEqual([]);
  });
});
