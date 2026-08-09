/*
 * C2 · ONE reset-refusal claim, two sites — and the ban on the categorical form.
 *
 * WHY THIS FILE EXISTS. Two surfaces describe the same refusal to a reader:
 *
 *   - `lib/labels.ts`          → the Reset Worked Example dialog's stale alert
 *                                (`resetStaleTitle` + `resetStaleBody`)
 *   - `lib/settingsContent.ts` → Settings → Governance → `reset-and-deletion`
 *
 * Nothing pinned them to each other, and one of them was wrong for a whole slice.
 * The dialog's copy was corrected to stop claiming "Nothing was reset" / "no
 * records were changed"; the settings screen kept "the server refuses and writes
 * nothing", which is the SAME claim in different words, on the surface a reader
 * goes to precisely when they want to know what this build can destroy.
 *
 * WHY THE CATEGORICAL FORM IS FALSE. `reset_to_canonical_seed` re-checks the
 * `plan_digest` PER RECORD, inside that record's own `record_lock`, immediately
 * before touching it. That is what stops a write that returned 200 from being
 * destroyed — but it means a stale plan detected mid-reset refuses AFTER the loop
 * has already restored the records it had reached.
 *
 * WHY THE CLAIM IS BANNED RATHER THAN QUALIFIED — A CHOICE, NOT A CONSTRAINT. This
 * comment used to say `DemoResetResponse` "carries no field that separates that
 * case", which reads as a fact about the contract and is not one: the server
 * computes exactly that boolean and simply does not serialize it. It is `mutated`
 * in `reset_to_canonical_seed` — set the moment an id is removed or
 * re-materialised, and already consulted there to decide whether the reported
 * figures may be echoed from the snapshot or must be measured from disk. THE
 * ALTERNATIVE WAS: add one field to `DemoResetResponse` and to `ApiDemoResetResult`,
 * serialize `mutated`, and let the dialog say "nothing was reset" only when the
 * server says so. That was not done — a destructive-path API field is a contract
 * this project would then have to keep true forever, and no screen needs it: the
 * stale branch RE-PREVIEWS, so the operator is shown re-measured figures rather than
 * a sentence about them. So the claim was dropped, not guessed. If a later slice
 * does add the field, this ban is the thing to revisit.
 *
 * (An earlier revision of this comment also offered "`previous_count` and
 * `final_count` are both 5" as evidence. That is no longer true and was the shallower
 * half of a real defect: a per-record abort now MEASURES both, including when it
 * aborted before mutating anything, because a per-record abort is reachable only
 * once a write has landed and the snapshot is therefore stale by construction.)
 *
 * WHAT IT ASSERTS, and why in this order:
 *
 *  §1 the per-record abort REALLY EXISTS in this build. The ban in §3 is only
 *     justified while it does. If a later slice removes it, §1 fails first and
 *     tells the next reader to revisit §3 rather than leaving a stale
 *     prohibition standing on nothing.
 *  §2 both sites make the SAME claim — refused, and why. Parity is the property
 *     that was missing; a site that states only half of it drifts again.
 *  §3 no site states the categorical "nothing was written / no records were
 *     changed / writes nothing".
 *  §4 the ban patterns are proven against the EXACT strings that shipped, so a
 *     pattern narrowed until it detects nothing fails here rather than going
 *     quiet. This is the control `upload-claim-parity.test.tsx` added after a
 *     guard shipped with its polarity inverted.
 *  §5 the dialog's RENDERED generic-error branch — a third site, written inline in
 *     JSX rather than in `LABELS`, which is exactly why §1–§4 could not see it and
 *     it kept the retired claim for a whole further slice.
 *
 * WHAT IT DELIBERATELY DOES NOT COVER.
 *
 *  · The AMBIGUOUS refusal in `ResetDemoDialog.tsx` also says "No records were
 *    changed", and it STAYS: an ambiguous record is refused before the mutation
 *    block, as is every other typed non-precondition refusal that reaches the
 *    `'refused'` branch (wrong confirmation phrase, not synthetic-only). The claim
 *    is true there. §5 covers the branch where it was NOT true.
 *  · Source COMMENTS in `ResetDemoDialog.tsx` made the same retired claim in two
 *    places (the pre-`resetDemo` comment and the `.catch`); both are corrected, and
 *    deliberately NOT pinned here. A comment guard would not be a user-facing
 *    guarantee and should not be presented as one — the header of this file quotes
 *    the banned phrase itself, which is exactly why a naive file scan cannot tell a
 *    claim from a prohibition against it.
 *  · The dialog's alert is checked through `LABELS`, the module it renders
 *    verbatim (`<strong>{LABELS.resetStaleTitle}.</strong> {LABELS.resetStaleBody}`).
 *    That the alert really renders those two strings is pinned by
 *    `reset-demo.test.tsx`, which drives the 412 through the real component; this
 *    file is about the WORDS, not the wiring, and duplicating a full dialog render
 *    here would only make the two tests fail together.
 *  · Backend-served copy is invisible to it. The OpenAPI `412` description makes
 *    the same claim and is pinned instead by
 *    `apps/api/tests/test_contract_description_parity.py`.
 */

import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect } from 'vitest';

import { LABELS } from '../lib/labels';
import { settingsConcepts } from '../lib/settingsContent';

// --- locating the real sources -----------------------------------------------

/** Deliberately NOT `import.meta.url`: under jsdom that is an http URL, not a file
 *  one. Duplicated from `upload-claim-parity.test.tsx` rather than exported, so no
 *  file can silently change another's scan. */
function locateSrcDir(): string {
  const candidates = [join(process.cwd(), 'src'), join(process.cwd(), 'apps', 'web', 'src')];
  const found = candidates.find((dir) => existsSync(join(dir, 'main.tsx')));
  if (found === undefined) throw new Error(`cannot locate apps/web/src from ${process.cwd()}`);
  return found;
}

const SRC_DIR = locateSrcDir();
/** `apps/web/src` -> repo root. Derived from the located dir rather than from
 *  `process.cwd()`, which differs between a root run and an `apps/web` run. */
const REPO_ROOT = join(SRC_DIR, '..', '..', '..');

const SETTINGS_FACTS = {
  dataRegime: 'synthetic-only',
  persistence: 'ephemeral',
  recordSchemaVersion: '1.05',
};

function resetDialogAlertText(): string {
  return `${LABELS.resetStaleTitle}. ${LABELS.resetStaleBody}`;
}

function resetAndDeletionText(): string {
  const found = settingsConcepts(SETTINGS_FACTS).find((c) => c.id === 'reset-and-deletion');
  if (!found) throw new Error('no such concept: reset-and-deletion');
  return `${found.heading} ${found.summary} ${found.detail}`;
}

const SITES: [string, () => string][] = [
  ['the Reset Worked Example stale alert', resetDialogAlertText],
  ['Settings → Governance → reset-and-deletion', resetAndDeletionText],
];

// --- §1 the per-record abort this ban is justified by -------------------------

describe('C2 §1 · a refusal really can follow a mutation, so the absolute claim is false', () => {
  const workspaceSrc = readFileSync(
    join(REPO_ROOT, 'apps', 'api', 'isaac_api', 'workspace.py'),
    'utf8',
  );

  it('the reset rebuilds ONE record’s plan row from disk', () => {
    expect(workspaceSrc).toMatch(/def _current_plan_row\(/);
  });

  it('and consults it inside the mutation loops, refusing with the existing reason', () => {
    // Both loops, so a slice that guards only one is caught.
    expect(workspaceSrc.match(/if check_rows and _row_changed\(/g) ?? []).toHaveLength(2);
    // Both loops also record WHERE the refusal came from. See the next assertion.
    expect(
      workspaceSrc.match(
        /refusal = "plan_digest_stale"\n\s+refused = True\n\s+row_abort = True\n\s+break/g,
      ) ?? [],
    ).toHaveLength(2);
  });

  it('so a refusal can arrive with records already mutated — which is the whole point', () => {
    // THE line that makes the categorical claim false, and it keys on the ORIGIN of
    // the refusal rather than on whether it managed to mutate anything first. It
    // read `if refused and not mutated:` for a slice, which was wrong in a way that
    // looked conservative: an abort on the FIRST id has mutated nothing, and yet its
    // snapshot is stale BY CONSTRUCTION, because the only way to reach a per-record
    // abort at all is for a write to have already landed in the window. `row_abort`
    // is what sends that case to the measured arm.
    expect(workspaceSrc).toMatch(/if refused and not mutated and not row_abort:/);
  });
});

// --- §2 the shared claim ------------------------------------------------------

/**
 * The two parts of the one claim. Both sites must state BOTH: a site that says
 * only "refused" leaves the reader without a reason, and a site that says only
 * "something changed" reads like a warning about their data rather than an
 * account of what the server did.
 *
 * Deliberately tolerant of wording — the two sites read differently on purpose
 * (one is an in-the-moment alert, the other is reference prose).
 */
const CLAIM_PARTS: [string, RegExp][] = [
  ['the server refused', /refus(e|ed|es)/i],
  ['because the workspace/walkthrough moved', /(this workspace changed|moved in between)/i],
];

describe('C2 §2 · both sites state the same refusal, with its reason', () => {
  it.each(SITES)('%s states the whole claim', (_where, text) => {
    const body = text();
    for (const [what, pattern] of CLAIM_PARTS) {
      expect(body, `missing: ${what}`).toMatch(pattern);
    }
  });

  it.each(SITES)('%s states it in the reader’s terms, never in HTTP', (_where, text) => {
    expect(text()).not.toMatch(/\b412\b|\b428\b|precondition|plan_digest|HTTP/);
  });
});

// --- §3 the ban ---------------------------------------------------------------

/**
 * The categorical no-mutation claims, in TWO lists that are validated
 * differently — a distinction §4's control forced rather than one chosen up
 * front. The first draft of this file put all four patterns in one list and
 * asserted every one of them fires on copy that really shipped; `wrote nothing`
 * failed, because it never shipped. That is the control working, so the fix is to
 * say which patterns are evidence and which are prophylaxis, not to quietly drop
 * the assertion.
 */

/** Forms that REALLY SHIPPED in one of the two sites. §4 proves each still fires
 *  on the exact sentence it retired. */
const RETIRED_FORMS: [string, RegExp][] = [
  ['nothing was reset/written/changed/removed', /nothing was (reset|written|changed|removed)/i],
  ['no records were changed', /no records were changed/i],
  ['writes nothing', /writes nothing/i],
];

/** Near neighbours that were never written here, banned because they state the
 *  same unverifiable thing and are the obvious next phrasing. Each carries its own
 *  example so it is still proven to detect something — a prophylactic pattern with
 *  no example is indistinguishable from a typo. */
const PARAPHRASES: [string, RegExp, string][] = [
  ['wrote nothing', /wrote nothing/i, 'the reset was refused and wrote nothing.'],
  ['changed nothing', /changed nothing/i, 'the reset was refused and changed nothing.'],
  [
    'no records were removed',
    /no records were removed/i,
    'the reset was refused, so no records were removed.',
  ],
];

const BANNED: [string, RegExp][] = [
  ...RETIRED_FORMS,
  ...PARAPHRASES.map(([what, pattern]) => [what, pattern] as [string, RegExp]),
];

describe('C2 §3 · no site claims the reset changed nothing', () => {
  it.each(SITES)('%s makes no categorical no-mutation claim', (_where, text) => {
    const body = text();
    for (const [what, pattern] of BANNED) {
      expect(body, `states the banned claim: ${what}`).not.toMatch(pattern);
    }
  });
});

// --- §4 the guard is proven on the strings that shipped -----------------------

/**
 * THE CONTROL. Every pattern in §3 must FIRE on the exact sentence it retired.
 * Without this, narrowing a pattern until it matches nothing would turn §3 green
 * and silent — which is how a guard ships with its polarity inverted.
 */
const RETIRED: [string, string][] = [
  ['the dialog title', 'Nothing was reset — this workspace changed'],
  [
    'the dialog body',
    'Something in this workspace changed after this window opened, so the reset was ' +
      'refused and no records were changed. The figures below have been refreshed. ' +
      'Please read them again and confirm again if you still want to reset.',
  ],
  [
    'the settings detail',
    'is checked against the figures you were shown — if the walkthrough moved in ' +
      'between, the server refuses and writes nothing.',
  ],
  [
    'the settings source comment',
    'so a reset authorised against figures that have since moved writes nothing',
  ],
];

describe('C2 §4 · the ban really detects the copy it retired', () => {
  it.each(RETIRED)('%s is caught by at least one banned pattern', (_what, retired) => {
    const hits = BANNED.filter(([, pattern]) => pattern.test(retired));
    expect(hits.length, `no banned pattern matches: ${retired}`).toBeGreaterThan(0);
  });

  it('every RETIRED_FORMS pattern fires on copy that really shipped', () => {
    for (const [what, pattern] of RETIRED_FORMS) {
      const fires = RETIRED.some(([, retired]) => pattern.test(retired));
      expect(fires, `dead pattern, matches none of the retired copy: ${what}`).toBe(true);
    }
  });

  it('every PARAPHRASES pattern fires on its own example, and is honestly labelled', () => {
    for (const [what, pattern, example] of PARAPHRASES) {
      expect(pattern.test(example), `dead prophylactic pattern: ${what}`).toBe(true);
      // If a paraphrase ever DOES ship and is retired, it belongs in
      // RETIRED_FORMS — this keeps the two lists from blurring into one.
      const alsoShipped = RETIRED.some(([, retired]) => pattern.test(retired));
      expect(alsoShipped, `${what} shipped after all — move it to RETIRED_FORMS`).toBe(false);
    }
  });
});

// --- §5 the RENDERED generic-error branch -------------------------------------

/**
 * The third reader-facing surface, and the one §1–§4 could not see: they read
 * `LABELS` and `settingsContent`, and this sentence is written inline in the
 * component's JSX. It shipped as "The reset could not be completed. No records were
 * changed." — which the dialog cannot know. That branch is reached from `.catch`,
 * so it covers a network failure AND any status this client does not model,
 * including a 500 raised inside the mutation loop with records already restored.
 *
 * Read from source rather than by rendering, for the reason the header gives: this
 * file is about the WORDS. `reset-demo.test.tsx` drives the component. The extractor
 * is proven on the retired sentence below, so a regex narrowed until it selects
 * nothing fails here instead of going quiet — the same control as §4.
 */
const DIALOG_SRC = readFileSync(
  join(SRC_DIR, 'components', 'ResetDemoDialog.tsx'),
  'utf8',
);

/** The JSX body of one `{executeState === '<state>' && ( … )}` branch. */
function executeStateBranch(state: string): string {
  const pattern = new RegExp(
    `\\{executeState === '${state}' && \\(([\\s\\S]*?)\\n\\s*\\)\\}`,
  );
  const found = DIALOG_SRC.match(pattern);
  if (found === null) throw new Error(`no rendered branch for executeState '${state}'`);
  return found[1];
}

describe('C2 §5 · the dialog’s generic-error branch claims no outcome it cannot see', () => {
  it('the branch is really located, and really carries prose', () => {
    // The control. Without it, a regex that stopped matching would leave the ban
    // below scanning an empty string and passing forever.
    expect(executeStateBranch('error')).toMatch(/The reset could not be completed/);
  });

  it('and states no categorical no-mutation claim', () => {
    const body = executeStateBranch('error');
    for (const [what, pattern] of BANNED) {
      expect(body, `states the banned claim: ${what}`).not.toMatch(pattern);
    }
  });

  it('while the TYPED refusal branch keeps it, because there it is true', () => {
    // Not an oversight and not inconsistency: `'refused'` is only ever set for a
    // typed refusal that is decided BEFORE the mutation block. Asserted so that a
    // future sweep does not "fix" a true sentence into a vaguer one.
    expect(executeStateBranch('refused')).toMatch(/No records were changed/);
  });
});
