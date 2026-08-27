/**
 * WHO PRODUCED THESE FINDINGS — the one place this repository answers that question.
 *
 * ── WHY A MODULE AND NOT A LINE IN EACH RENDERER ─────────────────────────────
 *
 * `POST /api/experiments/{id}/validate` and `POST …/runs/{runId}/check` both return
 * an `errors` list that can come from THREE different producers:
 *
 *   1. the vendored official ISAAC schema (`isaac_records.official.validate_official`)
 *   2. the no-guessing draft validator
 *   3. ISAAC's own anchored-pattern exactness gate
 *
 * `export.py` folds (2) and (3) together and returns `official_report=None` for both,
 * so the wire cannot separate them from each other — but it CAN separate them from
 * (1), and until now it did not. `schema` was stamped unconditionally, and `dry_run`
 * does not discriminate: a dry-run PASS does require the official validator, while a
 * dry-run FAILURE may never have reached it. So every consumer had to reconstruct the
 * answer from an ordering rule it could only learn by reading `export.py`.
 *
 * FOUR SURFACES GOT IT WRONG AT ONCE, AND FIXING THEM ONE AT A TIME RECURRED FOUR
 * TIMES. The last attempt corrected three React renderers and left the claim standing
 * in both machine-readable contracts, in a fourth screen, and — on the sibling
 * `unavailable` flag — inside two of the files it had just rewritten. That is not
 * carelessness; it is what an unbounded remedy looks like. Two independent reviewers
 * converged on the same conclusion: the fix has to be a discriminator on the wire plus
 * ONE decision point in the client.
 *
 * This module is that decision point. `official_validator_ran` is read HERE AND
 * NOWHERE ELSE in the frontend — pinned by
 * `__tests__/official-attribution-discriminator.test.ts` — so a new consumer cannot
 * quietly re-derive the rule, and every attributing phrase this product renders is
 * defined below rather than retyped per screen.
 *
 * ── WHAT EACH SOURCE MEANS, AND WHAT MAY BE SAID OF IT ───────────────────────
 *
 * `CLAUDE.md` §1 makes the vendored schema upstream-owned — it is not ours to speak
 * for — and §12 states the rule outright: *"the gate is ISAAC's, not upstream's … no
 * surface may report an exactness refusal as an official-schema error."*
 *
 *   `official-schema`  `validate_official` examined the document these findings
 *                      describe. The official ISAAC schema MAY be named.
 *   `export-gate`      the export was refused BEFORE the official validator ran.
 *                      The findings are ISAAC's own — the no-guessing check, the
 *                      exactness gate, or both. The official schema MUST NOT be
 *                      named, and neither may one of ISAAC's two gates be singled
 *                      out: the wire does not say which.
 *   `no-verdict`       nothing ran, from any gate. Not a failure of anything.
 *   `unnamed`          the response carries no discriminator. Says nothing.
 *
 * NONE OF THESE IS A VERDICT. `export-gate` does not mean "the schema rejected it"
 * and `official-schema` does not mean "it failed" — the verdict is `ok`, which this
 * module never reads for that purpose and never modifies. §12's standing invariant
 * (a warning or an ISAAC-local gate must never turn a PASS into a FAIL) is untouched:
 * nothing here is an input to any pass/fail figure anywhere.
 */

/** Which producer the `errors` beside the verdict came from. */
export type OfficialFindingSource =
  | 'official-schema'
  | 'export-gate'
  | 'no-verdict'
  | 'unnamed';

/**
 * The fields of a verdict this module reads. Structural rather than tied to one
 * interface, because FOUR payload shapes carry the same four keys: the check
 * response's `official` block (`ApiRunCheckVerdict`), `/validate`'s top level and its
 * `runs[]` entries (`ApiValidateResult`), and any future sibling that adopts them.
 * Declaring the union of those types here would make the module depend on its
 * consumers.
 */
export interface OfficialVerdictLike {
  readonly ok?: boolean;
  readonly dry_run?: boolean;
  readonly unavailable?: boolean;
  readonly official_validator_ran?: boolean;
}

/**
 * THE ONE DERIVATION. The order of the branches is load-bearing, and every one of
 * them exists because of something measured rather than something imagined.
 *
 * 1. `unavailable` FIRST. It is the strongest and earliest claim, and it is the
 *    branch the previous slice got wrong: `_validate_unit`'s materialised-unreadable
 *    return carries `dry_run: false` — meaning NO DRY RUN HAPPENED, returned
 *    *because* the written record could not be read — so a `dry_run`-first reading
 *    named the official schema for a check that never ran. It also carries
 *    `official_validator_ran: false`, so branch 3 would answer `export-gate`, which
 *    is likewise wrong: the export gate did not refuse it either. Nothing ran.
 *
 * 2–3. THE DISCRIMINATOR, which is the whole point. Tested against `true`/`false`
 *    explicitly rather than for truthiness, so an absent field falls through to the
 *    legacy branches instead of silently reading as `export-gate`.
 *
 * 4–6. LEGACY FALLBACKS, for a response predating the field — a cached body, a pod
 *    mid-rollout, a hand-written fixture. Each is sound on its own terms:
 *      · `dry_run === false` (and not `unavailable`) is only returned by the branch
 *        that calls `validate_official` directly, so the source is known.
 *      · `ok === true` is only reachable through `export.py`'s single `ok=True`
 *        return, which sits AFTER `validate_official` has run and passed. A pass is
 *        therefore unreachable without the official schema having said yes.
 *      · anything else — a dry-run failure with no flag — is genuinely unknown, and
 *        `unnamed` says so instead of guessing. This is the case the whole defect
 *        lived in, and it is now the case that only a pre-field response can reach.
 */
export function officialFindingSource(
  verdict: OfficialVerdictLike | null | undefined,
): OfficialFindingSource {
  if (!verdict) return 'unnamed';
  if (verdict.unavailable === true) return 'no-verdict';
  if (verdict.official_validator_ran === true) return 'official-schema';
  if (verdict.official_validator_ran === false) return 'export-gate';
  if (verdict.dry_run === false) return 'official-schema';
  if (verdict.ok === true) return 'official-schema';
  return 'unnamed';
}

/**
 * `true` only when the official ISAAC schema may be named as the source of the
 * findings beside this verdict. A convenience over {@link officialFindingSource} for
 * a caller that needs the boolean and not the reason — expressed in terms of it, so
 * the two can never disagree.
 */
export function mayNameOfficialSchema(
  verdict: OfficialVerdictLike | null | undefined,
): boolean {
  return officialFindingSource(verdict) === 'official-schema';
}

/**
 * WHICH DOCUMENT was checked — a DIFFERENT QUESTION from which validator produced the
 * findings, and conflating the two is the original defect in miniature.
 *
 * `dry_run` answers the document question and only that. It is kept here beside the
 * source derivation precisely so a reader can see that they are separate: a candidate
 * record can be checked by the official schema (`dry_run: true`,
 * `official_validator_ran: true`) and a written record can be checked by nothing at
 * all (`dry_run: false`, `unavailable: true`). `null` means the response does not say.
 */
export type OfficialCheckedDocument = 'written-record' | 'candidate-record' | null;

export function officialCheckedDocument(
  verdict: OfficialVerdictLike | null | undefined,
): OfficialCheckedDocument {
  // A no-verdict unit read NOTHING. `dry_run: false` there is not a claim about a
  // written record; it is returned because that record could not be opened.
  if (!verdict || verdict.unavailable === true) return null;
  if (verdict.dry_run === true) return 'candidate-record';
  if (verdict.dry_run === false) return 'written-record';
  return null;
}

/*
 * ── THE COPY ────────────────────────────────────────────────────────────────────
 *
 * EVERY PHRASE IN THIS PRODUCT THAT ATTRIBUTES A FINDING TO A VALIDATOR IS DEFINED
 * HERE, and the guard test enforces that. The register is the one four surfaces
 * already converged on over three corrections — "no verdict … not a schema failure",
 * "candidate record", "source not named" — rather than a fifth phrasing of the same
 * idea. Reusing it is not tidiness: a client that has to branch on prose is the state
 * these surfaces were in.
 *
 * WHAT `export-gate` COPY MAY NOT SAY. It may not name the official schema, and it
 * may not name ONE of ISAAC's two gates either — `export.py` folds the no-guessing
 * findings and the exactness findings into a single list, so "this is an exactness
 * refusal" would be the same defect one level finer. It names both as candidates and
 * claims neither. It also may not say "source not named", which is what the surfaces
 * said before this field existed: the source IS named now — it is ISAAC's export
 * gate, and saying so is the improvement the discriminator buys.
 */

/** A short noun phrase for the producer. Used where a label, not a sentence, fits. */
export const OFFICIAL_SOURCE_LABEL: Record<OfficialFindingSource, string> = {
  'official-schema': 'Official ISAAC schema check',
  'export-gate': 'ISAAC export-gate check — not the official schema',
  'no-verdict': 'No verdict — not a schema failure',
  unnamed: 'Check finding — source not named',
};

/**
 * A heading for a list of findings, given how many there are. `count` is interpolated
 * by the caller's own pluralisation so this module owns the CLAIM and not the
 * grammar; `null` asks for the claim alone.
 */
export function officialFindingsHeading(source: OfficialFindingSource): string {
  switch (source) {
    case 'official-schema':
      return 'Official ISAAC schema findings';
    case 'export-gate':
      return 'ISAAC export-gate findings — the official schema did not run';
    case 'no-verdict':
      return 'What the check reported — no verdict, and not a schema failure';
    case 'unnamed':
      return 'Findings — source not named';
  }
}

/** A full sentence introducing a list of findings. Ends in a colon. */
export function officialFindingsCaption(source: OfficialFindingSource): string {
  switch (source) {
    case 'official-schema':
      return 'The official ISAAC schema reported these findings:';
    case 'export-gate':
      return (
        'ISAAC’s own export gate refused this record before the official ISAAC ' +
        'schema was reached, so these findings are not the schema’s. They come from ' +
        'the no-guessing checks, from ISAAC’s anchored-pattern exactness gate, or ' +
        'from both — this check does not record which:'
      );
    case 'no-verdict':
      return 'No verdict could be produced — this is not a schema failure.';
    case 'unnamed':
      // M1 IS PRESERVED HERE, and it is the branch where it still bites. A caption
      // that names TWO of the three possible producers is an attribution by
      // elimination: a reader meeting an unfamiliar finding concludes it must be the
      // third. `export.py` runs `check_exactness` on the assembled record BETWEEN the
      // no-guessing report and `validate_official` and folds a refusal into
      // `draft_report`, so ISAAC's own gate really is a third source arriving in this
      // list. All three are named and none is claimed. Where the server sends the
      // discriminator this branch is unreachable — but a legacy response must not
      // silently lose the property the discriminator makes unnecessary.
      return (
        'This check does not record which findings came from the no-guessing ' +
        'checks, which from ISAAC’s own anchored-pattern exactness gate, and which ' +
        'from the official ISAAC schema, so none is claimed:'
      );
  }
}

/**
 * The sentence for a CLEAN result, which is the one place the asymmetry bites.
 *
 * A PASS on a candidate record clears THREE gates — the no-guessing check, ISAAC's
 * exactness gate, and the official schema — because `export.py` runs `check_exactness`
 * on the assembled record between the other two. A pass on a WRITTEN record clears
 * only the official schema: `_validate_unit`'s materialised branch calls
 * `validate_official` alone and `check_exactness` never runs there. One shared
 * sentence could only ever be wrong for one of the two, which is why this takes the
 * document as well as the source.
 */
export function officialCleanSentence(
  source: OfficialFindingSource,
  document: OfficialCheckedDocument,
): string {
  if (source !== 'official-schema') {
    return 'Nothing blocking was found. The server did not say which checks ran.';
  }
  if (document === 'candidate-record') {
    return (
      'Nothing blocking was found: the no-guessing checks, ISAAC’s own ' +
      'anchored-pattern exactness gate and the official ISAAC schema all passed on a ' +
      'candidate record. Nothing was written.'
    );
  }
  if (document === 'written-record') {
    return 'The official ISAAC schema found nothing blocking, on the record already written.';
  }
  return (
    'Nothing blocking was found and the official ISAAC schema passed. The server did ' +
    'not say which document was checked.'
  );
}

/**
 * The sentence for a screen whose subject is the EXPORT GATE rather than a findings
 * list — Export Readiness. Same rule, different framing.
 *
 * THE REFUSAL KEEPS ITS FULL FORCE ON EVERY BRANCH. What varies is the ATTRIBUTION,
 * never whether export is gated: withholding an attribution the payload does not
 * support must never read as softening the refusal, which is the failure mode a
 * reader would rightly suspect. `export-gate` therefore states the gate first and
 * only then declines to name which of ISAAC's two gates refused.
 */
export function officialExportBlockedSentence(
  source: OfficialFindingSource,
  document: OfficialCheckedDocument,
): string {
  const tail = ' Resolve these in the draft, then return.';
  const separately =
    ' The Standalone Validator on Governance & Safety reports the schema verdict and ' +
    'ISAAC’s exactness findings separately.';
  switch (source) {
    case 'official-schema':
      return (
        (document === 'written-record'
          ? 'The record already written does not pass the official ISAAC schema, so ' +
            'export stays gated. Nothing was written.'
          : 'A candidate record assembled from this draft does not pass the official ' +
            'ISAAC schema, so export stays gated. Nothing was written.') + tail
      );
    case 'export-gate':
      return (
        'Export stays gated and nothing was written. ISAAC’s own export gate refused ' +
        'this record before the official ISAAC schema was reached, so these findings ' +
        'are not the schema’s — they come from the no-guessing checks, from ISAAC’s ' +
        'anchored-pattern exactness gate, or from both, and this check does not record ' +
        'which.' +
        separately +
        tail
      );
    case 'no-verdict':
      return (
        'Export stays gated and nothing was written. No verdict could be produced at ' +
        'all — this is not a schema failure.' + tail
      );
    case 'unnamed':
      // All THREE candidate producers named, none claimed — see the M1 note on
      // `officialFindingsCaption`'s `unnamed` branch. Naming two of three is an
      // attribution by elimination, which is the same §12 violation made quietly.
      return (
        'Export stays gated and nothing was written. This check does not record which ' +
        'findings came from the no-guessing checks, which from ISAAC’s own ' +
        'anchored-pattern exactness gate, and which from the official ISAAC schema, ' +
        'so none is claimed.' +
        separately +
        tail
      );
  }
}

/**
 * A standing NOTE for a surface that renders many findings under one banner — the
 * Project Memory experiment graph. `null` where there is nothing true to add: a
 * `no-verdict` payload has no producer and no document to describe, and an `unnamed`
 * one is the state the whole defect lived in, so a note asserting anything there
 * would be the defect again.
 *
 * IT LIVES HERE AND NOT IN THE GRAPH MODULE ON PURPOSE. That module was the fifth
 * consumer of this payload and the last to be found, because it CONTAINED two literal
 * NUL bytes and a repo-wide `rg` sweep therefore dropped every hit in it without
 * saying so. ~~"because it contains NUL bytes and every `grep`/`rg` sweep silently
 * skipped it"~~ — PAST TENSE SINCE `7a66127`, which rewrote the separator as the
 * escape `\u0000`; `lib/experimentGraph.ts` now holds ZERO NUL bytes and the runtime
 * string is unchanged. Two precisions carried over from the re-measurement recorded
 * in that file: the silent drop is a property of a DIRECTORY sweep (an explicitly
 * named file gets a visible `binary file matches` notice instead, and `rg -c` /
 * `grep -c` were correct all along), and the reason the file was lost is that a
 * repo-wide sweep is a directory sweep.
 *
 * THE ARGUMENT FOR THIS MODULE DOES NOT REST ON THE NUL BYTES and outlives their
 * removal: copy kept next to its renderer is copy that can be missed; copy kept here
 * is copy the guard can see.
 */
export function officialFindingsNote(source: OfficialFindingSource): string | null {
  switch (source) {
    case 'official-schema':
      return (
        'These findings are the vendored official ISAAC schema’s own. Where the ' +
        'record has not been exported they describe a candidate record assembled in ' +
        'memory — nothing has been written.'
      );
    case 'export-gate':
      return (
        'These findings are ISAAC’s own: the export was refused before the official ' +
        'ISAAC schema was reached, by the no-guessing checks, by ISAAC’s ' +
        'anchored-pattern exactness gate, or by both. This response does not record ' +
        'which, and the official schema did not produce them.'
      );
    case 'no-verdict':
    case 'unnamed':
      return null;
  }
}

/**
 * THE SIXTH CONSUMER, and it reached the claim through a shape none of the guards
 * could see — so the copy for it lives here with the rest rather than in the screen.
 *
 * WHAT WAS MEASURED, over HTTP, on an exported record whose written artifact was
 * deleted out of band (`routes.post_validate`'s `record is None` branch):
 *
 *     {"ok": false, "schema": "ISAAC v1.05", "dry_run": false,
 *      "official_validator_ran": false, "unavailable": true,
 *      "errors": [{"path": "$", "message": "Validation could not be completed."}]}
 *
 * `ExportReadiness` converts that with `adapt.toValidationResult`, which sets no
 * `schemaOk`, so `VerdictCard` reads `schemaOk = ok = false` and renders **"Invalid
 * against official ISAAC schema v1.05 — 1 error. Export blocked."** — the exact
 * sentence `CLAUDE.md` §12 records as having shipped once already, about a document
 * `validate_official` never opened. It is not reachable through the payload's own
 * keys, but through a DIFFERENT type (`ValidationResult`) two files away, which is why
 * neither the renderer sweep nor the payload-shaped guard found it.
 *
 * `VerdictCard`'s three existing branches cannot express this. `schemaOk: false` says
 * the schema refused; `schemaOk: true` says — in its own words — that "the official
 * ISAAC schema … verdict on this record is PASS". Both are claims about a verdict that
 * does not exist. So the screen renders THIS instead of that card, and the refusal
 * keeps its full force: what is withheld is the attribution, never the fact that
 * something is wrong.
 */
export function officialNoVerdictOnWrittenRecordSentence(
  source: OfficialFindingSource,
): string {
  if (source === 'no-verdict') {
    return (
      'No verdict could be produced for this record. The official ISAAC schema did ' +
      'not examine it — this is not a schema failure, and nothing here says the ' +
      'record is invalid. The artifacts section reports why the written record could ' +
      'not be read.'
    );
  }
  return (
    'The official ISAAC schema did not produce this result, so no schema verdict is ' +
    'claimed for this record. Read it as "not checked", not as "rejected".'
  );
}

/**
 * The DOCUMENT row of a details pane — the graph modules' `Dry run` line.
 *
 * IT TAKES THE SOURCE AS WELL AS THE DOCUMENT, AND THAT IS A CORRECTION. An earlier
 * revision of this module keyed this row off `officialCheckedDocument` alone, which
 * returns `null` for TWO different states — "no verdict could be produced" and "the
 * response does not say" — and so rendered one string for both. Both graph modules
 * carried a local table whose own comment read *"the two are deliberately worded
 * differently, because … a reader who confuses them draws the wrong conclusion about
 * their own record"*, above code that had just stopped wording them differently.
 * `evidenceGraph`'s own test had asserted the distinction since before this slice.
 *
 * They are different claims. "No verdict could be produced" says a check was attempted
 * and reached nothing; "the server did not say" says this client cannot tell. A
 * scientist reading the first knows something is wrong with their artifact; a
 * scientist reading the second knows only that this build is looking at an older
 * response.
 */
export function officialDocumentDetailValue(
  source: OfficialFindingSource,
  document: OfficialCheckedDocument,
): string {
  if (document === 'candidate-record') {
    return 'yes — an in-memory candidate record, nothing written';
  }
  if (document === 'written-record') return 'no — the record already written was checked';
  if (source === 'no-verdict') return 'neither — no verdict could be produced';
  return 'the server did not say';
}

/** Which document was checked, as a sentence. `null` when nothing may be claimed. */
export function officialDocumentSentence(document: OfficialCheckedDocument): string | null {
  if (document === 'candidate-record') {
    return 'Checked an in-memory candidate record — nothing was written.';
  }
  if (document === 'written-record') return 'Checked the written official record.';
  return null;
}
