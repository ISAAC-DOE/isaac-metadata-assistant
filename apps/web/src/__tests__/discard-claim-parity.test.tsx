/*
 * ONE DISCARD CLAIM, FIVE CONTROLS — and the ban on the deletion form.
 *
 * WHY THIS FILE EXISTS. Five Discard controls, across four panels, all tell a scientist
 * the same thing about the same boundary: what is being cleared is an input on screen
 * that was never sent, and nothing the record holds is touched. Nothing pinned them to
 * each other, and copy that is not pinned drifts — `upload-claim-parity.test.tsx` is the
 * same shape for the same reason, and its own fourth site "arrived late, and it arrived
 * false".
 *
 * WHY THE DRIFT WOULD BE WORSE HERE THAN A WRONG WORD. This application HAS NO DELETION.
 * `apps/api/isaac_api/routes.py:8618-8620` (at commit `8994525`; ~~`8155-8158`~~ was
 * wrong and pointed into the run-answers handler — corrected 2026-08-27, and the
 * anchor to search on is the phrase `NOTHING CAPTURED IS EVER`) states it as a
 * governing rule — "there is no
 * DELETE here, and there will not be one. Dismissal is a state" — and
 * `transcript_capture.py:129-159` records two retention states that were deliberately NOT
 * offered because "both are deletion guarantees, and there is no deletion anywhere in the
 * notes model to build one on. Offering a control that quietly did nothing would be worse
 * than offering none." A Discard control whose copy said it removed, deleted or erased
 * anything from the record would BE that control, arriving through the copy instead of
 * through the API.
 *
 * WHAT IT ASSERTS, and why in this order:
 *
 *  §1 THE ABSENCE IS REAL. No DELETE reaches the notes API from this build, and the
 *     component behind every Discard cannot make a request at all. The ban in §3 is only
 *     justified while both hold; if a later slice genuinely adds a deletion, §1 fails
 *     first and tells the next reader to revisit §3 rather than leaving a prohibition
 *     standing on nothing.
 *  §2 PARITY. Every authored control states the two halves — what is cleared, and what is
 *     untouched. A site that states one half is a site that will drift again.
 *  §3 THE BAN. No control claims a deletion, an irreversibility, or a restore.
 *  §4 THE NEGATIVE CONTROL. Each detector is run against a string that SHOULD trip it, so
 *     a pattern narrowed until it detects nothing fails here rather than going quiet.
 *     `upload-claim-parity.test.tsx`'s first version passed an INVERTED disclosure; that
 *     is the failure this section exists to make impossible.
 *  §5 THE COPY IS WHAT THE READER MEETS. The authored strings are rendered on a real
 *     panel, so a module full of correct sentences that no screen uses cannot pass.
 *
 * WHAT IT CANNOT CATCH, stated plainly. It is a shape ratchet over authored strings, not
 * a detector for "is this paragraph true". A novel phrasing that implies a deletion —
 * "this takes it off the record", "the note will no longer exist" — trips no pattern here.
 * Nor does an affirmation about a subject the detector's fixed phrase list does not name
 * ("everything here has been captured"). A human reviewer remains the backstop for newly
 * written claims. It also reads `apps/web/src` only: backend-served copy is invisible to
 * it.
 *
 * ONE HOLE WAS FOUND IN REVIEW AND CLOSED RATHER THAN DOCUMENTED, and the sequence is
 * worth keeping. §2's required claim is SENTENCE-scoped, and a reviewer defeated it with
 * a single sentence that satisfies it while asserting its opposite — "What you typed has
 * already been captured, and nothing on the record changes." Every §3 ban passed that
 * string too. `affirmsTheStagedThingReached` is the answer; §4 pins both the bypass and
 * the negated form that must NOT trip it, because a detector that banned the negated form
 * would ban all five shipped bodies.
 */

import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect, afterEach, vi } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { UnmappedNotesPanel } from '../components/UnmappedNotesPanel';
import { DISCARD_COPY, DISCARD_COPY_ENTRIES, type DiscardCopy } from '../lib/discardContent';
import { noteFixture, notesPage, stubFetchRoutes } from '../test/apiFixtures';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** Deliberately NOT `import.meta.url`: under jsdom that is an http URL, not a file one.
 *  Duplicated from the sibling guards rather than exported, so no file can silently
 *  change another's scan. */
function locateSrcDir(): string {
  const candidates = [join(process.cwd(), 'src'), join(process.cwd(), 'apps', 'web', 'src')];
  const found = candidates.find((dir) => existsSync(join(dir, 'main.tsx')));
  if (found === undefined) throw new Error(`cannot locate apps/web/src from ${process.cwd()}`);
  return found;
}

const SRC_DIR = locateSrcDir();

function rawSource(path: string): string {
  return readFileSync(join(SRC_DIR, path), 'utf8');
}

/** Every authored sentence of one control, as one string to scan. */
function proseOf(copy: DiscardCopy): string {
  return [copy.trigger, copy.body, copy.commit, copy.keep, copy.announcement].join(' ');
}

// ─────────────────────────────────────────────────────────────────────────────
// The detectors. Each is exercised in §4 against a string that must trip it.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * A claim that something is REMOVED from where it is stored.
 *
 * `discard` and `clear` are deliberately absent from this list: "Discard" is the control's
 * own name, and "clears the box" is a true statement about a text input. The verbs banned
 * here are the ones that assert an effect on STORED content.
 */
const DELETION_VERBS =
  /\b(delete[sd]?|deleting|deletion|eras(?:e|es|ed|ing)|remov(?:e|es|ed|ing)|removal|wipe[sd]?|purge[sd]?|destroy(?:s|ed)?)\b/i;

/** Stakes that belong to persisted content, borrowed for input that was never sent. */
const OVERSTATED_STAKES = /\b(permanently|permanent|forever|irreversib\w*|cannot be undone)\b/i;

/** A promise this control cannot keep. Nothing here can put the input back. */
const RESTORE_PROMISE =
  /\b(restore[sd]?|restoring|recover(?:ed|able)?|undo|undone|bring(?:s)? (?:it )?back|get (?:it )?back)\b/i;

/** The two halves every control must state: what is cleared, and what is untouched. */
const CLEARS_AN_INPUT = /\b(clear[s]?|empty)\b/i;
const NAMES_THE_INPUT = /\b(box|boxes|question|answer|decision|transcript|note)\b/i;
const WHAT_STAYS = /\b(stays?|unchanged|untouched|still|unaffected|as (?:they|it) (?:are|is))\b/i;

/**
 * DOES THE COPY STATE THAT WHAT IS BEING CLEARED NEVER REACHED THE RECORD?
 *
 * Sentence-scoped rather than a single regex over the whole prose, because the two
 * halves have to be in the SAME claim: a paragraph containing "not" somewhere and
 * "stored" somewhere else can say the opposite of this. Split on sentence ends and on
 * the em dash, which is the panel's own clause separator throughout.
 *
 * IT IS SENTENCE-SCOPED, NOT CLAUSE-SCOPED, and the difference is a hole rather than a
 * quibble \u2014 see `affirmsTheStagedThingReached` below, which is the half that closes it.
 */
const NEGATION = /\b(not|nothing|never|none|no)\b/i;
const REACHED_THE_RECORD =
  /\b(sent|asked|captured|recorded|read|stored|confirm(?:ed)?|written|applied)\b/i;

/** Sentence ends and the em dash \u2014 the panel's own clause separator throughout. */
function clausesOf(prose: string): string[] {
  return prose.split(/(?<=[.!?])\s+|\u2014/);
}

function statesItNeverReachedTheRecord(prose: string): boolean {
  return clausesOf(prose).some(
    (clause) => NEGATION.test(clause) && REACHED_THE_RECORD.test(clause),
  );
}

/**
 * DOES THE COPY AFFIRM THE OPPOSITE \u2014 that the very thing being cleared DID reach the
 * record? THIS DETECTOR IS A REVIEW FIX, AND THE STRING THAT FORCED IT IS RECORDED.
 *
 * `statesItNeverReachedTheRecord` requires a negation and a transmission verb in one
 * SENTENCE. An independent reviewer defeated exactly that with a sentence that contains
 * both and asserts the opposite:
 *
 *     "What you typed has already been captured, and nothing on the record changes."
 *
 * "captured" and "nothing" sit in one sentence, so the required-claim check passed it;
 * no banned verb, stake or restore promise appears, so \u00a73 passed it too. That is the
 * INVERTED DISCLOSURE failure `upload-claim-parity.test.tsx` shipped once, reproduced
 * against this guard. Tightening the sentence split to commas does not fix it \u2014 it
 * breaks `guidedAnswer`, whose true claim legitimately spans a comma ("\u2026only when you
 * confirm it, so this one has not").
 *
 * So the required claim keeps its shape and this runs BESIDE it: a clause may not assert
 * that the STAGED THING \u2014 "this", "it", "your note", "what you typed" \u2014 has been
 * sent/captured/recorded/stored, unless a negation governs the assertion by appearing
 * earlier in the same clause. That exception is what keeps "Nothing in it has been read
 * or stored" (true, required) apart from "your note was captured" (false, banned).
 *
 * ~~"earlier in the same CLAUSE"~~ WAS TOO WIDE, AND A SECOND INDEPENDENT REVIEWER WALKED
 * STRAIGHT BACK THROUGH IT. The exception says a negation must GOVERN the assertion; the
 * first implementation accepted a negation anywhere earlier in the sentence, including in
 * a different independent clause that governs nothing. The string that defeated it:
 *
 *     "Nothing else on this record changes: what you typed has already been captured"
 *
 * "Nothing" sits before the affirmation, so the detector stood down \u2014 while the sentence
 * asserts exactly what this detector exists to ban, and every \u00a73 ban and the required-claim
 * check pass it too. It is the SAME inverted disclosure as the string above, wearing the
 * fix as a disguise, which is the worse of the two failures because the guard now reads as
 * having been hardened.
 *
 * The lookback is therefore bounded at the nearest preceding `,`, `;` or `:` \u2014 the
 * sub-clause the assertion actually lives in. That is safe for the shipped copy for a
 * measured reason rather than a hopeful one: the only two bodies that rely on the
 * exception at all are `transcriptUnsent` ("Nothing in it has been read or stored") and
 * `conflictDecision` ("None of it has been recorded"), and in both the negation is the
 * first word of its own sub-clause. Note the asymmetry with the sentence above: narrowing
 * the SPLIT to commas would break `guidedAnswer`; narrowing this LOOKBACK to commas does
 * not, because the two do different jobs.
 *
 * WHAT IT STILL CANNOT DO, stated rather than implied. The subject list is a fixed set of
 * phrases, so an affirmation about a subject it does not name ("everything here has been
 * captured") passes; and no regex can decide whether a paragraph is TRUE. A human
 * reviewer is still the backstop for newly written claims \u2014 this narrows the gap, it does
 * not close it.
 */
const AFFIRMS_THE_STAGED_THING_REACHED = new RegExp(
  '\\b(?:this|it|your (?:note|answer|transcript|decision|text|value|reason)|' +
    'what you (?:typed|wrote|entered)|the (?:box|text))\\b' + // the staged thing
    '(?:\\s+\\w+){0,3}\\s+' + // a short gap
    '\\b(?:has|have|had|was|were|is|are)\\b' + // an AFFIRMING auxiliary
    '(?:\\s+(?:already|now|indeed|been))*\\s+' + // \u2026and no negation may sit here
    '\\b(?:sent|captured|recorded|stored|written|applied|confirmed|read)\\b',
  'i',
);

function affirmsTheStagedThingReached(prose: string): boolean {
  return clausesOf(prose).some((clause) => {
    // EVERY match, not just the first: a clause may carry a negated affirmation and an
    // un-negated one, and stopping at the first would let the second through.
    const scan = new RegExp(AFFIRMS_THE_STAGED_THING_REACHED.source, 'ig');
    let hit: RegExpExecArray | null;
    while ((hit = scan.exec(clause)) !== null) {
      const before = clause.slice(0, hit.index);
      // A negation GOVERNS the assertion only from inside its own sub-clause. See the
      // note above for the string that defeated the un-bounded version.
      const boundary = Math.max(
        before.lastIndexOf(','),
        before.lastIndexOf(';'),
        before.lastIndexOf(':'),
      );
      if (!NEGATION.test(before.slice(boundary + 1))) return true;
    }
    return false;
  });
}

/**
 * FOUR OF THE FIVE MAY SAY "this was never sent". THE FIFTH MUST NOT, and that is the
 * whole reason it is a separate entry rather than a shared string.
 *
 * ~~"FIVE OF THE SIX … THE SIXTH"~~ — CORRECTED 2026-08-27. There are FIVE controls,
 * not six — `expect(DISCARD_COPY_ENTRIES).toHaveLength(5)` is asserted in §2 of this
 * same file — and the filter below removes one, leaving FOUR. The "six" was the RULE
 * count from `lib/discardContent.ts` leaking into a sentence about controls: two
 * different enumerations of two different things, one sentence apart.
 *
 * Once Finalize succeeds, every segment of the transcript is stored with the record as
 * Unmapped Notes (`routes.py:9936-9954`, the `EVERY SEGMENT IS STORED` loop, at commit
 * `8994525`; ~~`9483-9494`~~ named neither the loop nor the served sentence). A Discard
 * offered from that moment on clears a box whose words ARE on the record, so it is held
 * to the OPPOSITE requirement — it must say so — asserted by name below rather than by
 * this predicate.
 */
const NEVER_SENT_CONTROLS = DISCARD_COPY_ENTRIES.filter(
  ([name]) => name !== 'transcriptAfterFinalize',
);

// ═══════════════════════════════════════════════════════════════════════════════
// §1 — the absence the ban rests on is real
// ═══════════════════════════════════════════════════════════════════════════════

describe('§1 the deletion this copy must not claim does not exist', () => {
  it('the ONE DELETE this client declares is a tutorial session, and reaches no record content', () => {
    /*
     * NOT "there is no DELETE" — there is exactly one, and stating the stronger claim
     * would have been the same kind of error this file exists to catch. `git grep` it:
     * `api.disposeTutorialSession` sends `DELETE /tutorial/sessions/{id}`, and a
     * worked-example session is temporary, synthetic, and never persisted as a normal
     * experiment (`PostgresOrdinaryStore.refuse_if_not_persistable`).
     *
     * What matters for §3 is that no note, record, run, conflict, asset or answer has a
     * DELETE, so no Discard control could truthfully claim one even if it wanted to.
     */
    const api = rawSource('lib/api.ts');
    const deletePaths = [...api.matchAll(/const path = `([^`]+)`;\s*\n\s*const res = await request\(path, \{ method: 'DELETE' \}\)/g)]
      .map((m) => m[1]);
    const deleteCount = [...api.matchAll(/method:\s*'DELETE'/g)].length;
    expect(deleteCount).toBe(1);
    expect(deletePaths).toEqual(['/tutorial/sessions/${enc(sessionId)}']);
  });

  it('the component behind every Discard cannot issue a request of any kind', () => {
    const source = rawSource('components/DiscardStaged.tsx');
    expect(source).not.toMatch(/from '\.\.\/lib\/api'/);
    expect(source).not.toMatch(/\bfetch\s*\(/);
    expect(source).not.toMatch(/XMLHttpRequest|sendBeacon/);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// §2 — parity: every control states both halves
// ═══════════════════════════════════════════════════════════════════════════════

describe('§2 every Discard control makes the same two-part claim', () => {
  it('there are five of them, and the catalogue is what the panels import', () => {
    // Guards against a control being added to a panel with copy written inline —
    // the way `upload-claim-parity`'s fourth site escaped its own ratchet.
    expect(DISCARD_COPY_ENTRIES).toHaveLength(5);
    for (const file of [
      'components/TranscriptCapturePanel.tsx',
      'components/GuidedPrompt.tsx',
      'components/ConflictResolutionPanel.tsx',
      'components/UnmappedNotesPanel.tsx',
    ]) {
      const source = rawSource(file);
      expect(source).toMatch(/DISCARD_COPY/);
      // The panel renders the shared control rather than a hand-rolled one.
      expect(source).toMatch(/<DiscardStaged/);
    }
  });

  /*
   * THE ASSISTANT COMPOSER IS PINNED AS **ABSENT**, deliberately, because "we decided not
   * to" is exactly the kind of decision that gets quietly reversed by the next slice
   * reading the gap as an oversight. One was written and withdrawn: announcing its
   * outcome needs a live region, and `AssistantPanel` is under two committed invariants
   * that forbid a second one (`assistant-a11y.test.tsx`'s P34.5 single-polite-region, and
   * `graph-semantic-zoom.test.tsx`'s document-wide `role="status"` count on Project
   * Memory, which mounts this panel). The reasoning lives in `lib/discardContent.ts`.
   *
   * If a future slice DOES add one, this test fails and sends the author to that note
   * first — which is the point.
   */
  it('the Assistant panel deliberately has NO Discard, and the reason is recorded', () => {
    const panel = rawSource('components/AssistantPanel.tsx');
    expect(panel).not.toMatch(/<DiscardStaged/);
    expect(panel).not.toMatch(/DISCARD_COPY/);
    // The panel's existing explicit discard is still there and still covers the two
    // states it always covered.
    expect(panel).toMatch(/Clear Conversation/);
    expect(panel).toMatch(/clearSession\(experimentId\)/);
    // And the decision is written down where the next author will look.
    const content = rawSource('lib/discardContent.ts');
    expect(content).toMatch(/THE ASSISTANT COMPOSER HAS NO ENTRY HERE/);
  });

  it.each(DISCARD_COPY_ENTRIES)('%s says what is cleared and names it', (_name, copy) => {
    expect(proseOf(copy)).toMatch(CLEARS_AN_INPUT);
    expect(proseOf(copy)).toMatch(NAMES_THE_INPUT);
  });

  it.each(NEVER_SENT_CONTROLS)('%s says it never reached the record', (_name, copy) => {
    expect(statesItNeverReachedTheRecord(proseOf(copy))).toBe(true);
  });

  it.each(NEVER_SENT_CONTROLS)(
    '%s does not ALSO affirm the opposite in some other clause',
    (_name, copy) => {
      // The half that catches an inverted disclosure the check above would pass. See
      // `affirmsTheStagedThingReached` for the exact string that forced it to exist.
      expect(affirmsTheStagedThingReached(proseOf(copy))).toBe(false);
    },
  );

  it.each(DISCARD_COPY_ENTRIES)('%s says what is left untouched', (_name, copy) => {
    expect(proseOf(copy)).toMatch(WHAT_STAYS);
  });

  it('the control is named "Discard", consistently, at every trigger', () => {
    for (const [, copy] of DISCARD_COPY_ENTRIES) {
      expect(copy.trigger.startsWith('Discard ')).toBe(true);
      expect(copy.commit).toBe('Discard');
      expect(copy.keep).toBe('Keep it');
    }
  });

  /*
   * ONE STRING, TWO STATES OF THE SAME CARD. `ConflictRow` renders the identical form for
   * an undecided conflict and for one being REVISED (`conflict.resolution !== null` — the
   * primary button reads "Record a Revised Decision", a `RecordedDecision` block sits
   * below it and the header chip reads "decided"). The first version of this copy said
   * "The conflict stays open" and "the conflict is still open", which is false on the
   * second card and contradicted by its own chip. Unlike the transcript, this one is NOT
   * split in two: what is true of both states — that discarding moves the standing
   * nowhere — is also what the reader needs, so one truthful string serves both.
   */
  it('the conflict control asserts neither state of the card it is reused on', () => {
    const prose = proseOf(DISCARD_COPY.conflictDecision);
    expect(prose).not.toMatch(/\b(still|stays)\s+open\b/i);
    expect(prose).not.toMatch(/\bunresolved\b/i);
    expect(prose).not.toMatch(/\b(decided|resolved)\b/i);
    // …and it does say the thing that IS true of both.
    expect(prose).toMatch(/keeps the standing it already has/);
  });

  it('the transcript control keeps BOTH bodies, because after Finalize the words are on the record', () => {
    // The unsent body may say nothing was stored. The post-finalize body may NOT, and
    // must say the opposite — the notes are stored and stay.
    expect(DISCARD_COPY.transcriptUnsent.body).toMatch(/has been read or stored/);
    expect(DISCARD_COPY.transcriptAfterFinalize.body).toMatch(
      /already stored with this record as\s+notes and stays there/,
    );
    expect(DISCARD_COPY.transcriptAfterFinalize.announcement).toMatch(
      /notes you finalized are still stored/,
    );
    // …and it must not claim the finalized transcript was unsent.
    expect(DISCARD_COPY.transcriptAfterFinalize.body).not.toMatch(/nothing has been sent/i);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// §3 — the ban
// ═══════════════════════════════════════════════════════════════════════════════

describe('§3 no Discard control claims a deletion, an irreversibility, or a restore', () => {
  it.each(DISCARD_COPY_ENTRIES)('%s claims no deletion of stored content', (_name, copy) => {
    expect(proseOf(copy)).not.toMatch(DELETION_VERBS);
  });

  it.each(DISCARD_COPY_ENTRIES)('%s does not overstate the stakes', (_name, copy) => {
    expect(proseOf(copy)).not.toMatch(OVERSTATED_STAKES);
  });

  it.each(DISCARD_COPY_ENTRIES)('%s promises no restore it cannot perform', (_name, copy) => {
    expect(proseOf(copy)).not.toMatch(RESTORE_PROMISE);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// §4 — the negative control: every detector is proven to detect
// ═══════════════════════════════════════════════════════════════════════════════

describe('§4 the guards have the polarity they claim', () => {
  /*
   * THIS SECTION IS NOT CEREMONY. `upload-claim-parity.test.tsx`'s first version
   * "passed an INVERTED disclosure" — the guard was green over copy that said the
   * opposite of what it was written to require. A `not.toMatch` against a pattern that
   * matches nothing is green forever, and reads as evidence of honesty.
   *
   * Each string below is a sentence a well-meaning author might actually write, and
   * each MUST trip its detector.
   */

  it.each([
    ['This permanently deletes the note from the record.', DELETION_VERBS],
    ['Discarding removes the transcript from this experiment.', DELETION_VERBS],
    ['Your answer will be erased.', DELETION_VERBS],
    ['This wipes the staged decision.', DELETION_VERBS],
  ])('the deletion detector trips on %s', (bad, pattern) => {
    expect(bad).toMatch(pattern);
  });

  it.each([
    ['This cannot be undone.', OVERSTATED_STAKES],
    ['The question is discarded permanently.', OVERSTATED_STAKES],
    ['Gone forever.', OVERSTATED_STAKES],
  ])('the overstatement detector trips on %s', (bad, pattern) => {
    expect(bad).toMatch(pattern);
  });

  it.each([
    ['You can restore this later.', RESTORE_PROMISE],
    ['Press Undo to bring it back.', RESTORE_PROMISE],
    ['The discarded text is recoverable from the panel.', RESTORE_PROMISE],
  ])('the restore detector trips on %s', (bad, pattern) => {
    expect(bad).toMatch(pattern);
  });

  it('the parity detectors are not vacuous either', () => {
    // A control whose copy said only "Discard" would satisfy nothing.
    const empty: DiscardCopy = {
      trigger: 'Discard it',
      body: 'Are you sure?',
      commit: 'Discard',
      keep: 'Keep it',
      announcement: 'Done.',
    };
    expect(statesItNeverReachedTheRecord(proseOf(empty))).toBe(false);
    expect(proseOf(empty)).not.toMatch(WHAT_STAYS);
    expect(proseOf(empty)).not.toMatch(CLEARS_AN_INPUT);
  });

  it('the "never reached the record" check is SENTENCE-scoped, not a whole-prose keyword hunt', () => {
    /*
     * The failure this shape exists to prevent: copy that contains a negation in one
     * sentence and a transmission verb in another, and therefore satisfies a naive
     * whole-string check while saying the opposite of the required claim.
     */
    const split: DiscardCopy = {
      trigger: 'Discard this note',
      body: 'Your note was captured. There is not much else to say.',
      commit: 'Discard',
      keep: 'Keep it',
      announcement: 'Done.',
    };
    // A naive whole-prose check passes it…
    expect(NEGATION.test(proseOf(split))).toBe(true);
    expect(REACHED_THE_RECORD.test(proseOf(split))).toBe(true);
    // …and the sentence-scoped one does not.
    expect(statesItNeverReachedTheRecord(proseOf(split))).toBe(false);
  });

  it('an INVERTED disclosure inside ONE sentence is caught — the bypass a reviewer found', () => {
    /*
     * The exact string an independent reviewer used to defeat the sentence-scoped check.
     * Every §3 ban passes it, and `statesItNeverReachedTheRecord` passes it too, because
     * "nothing" and "captured" are in the same sentence — while the sentence asserts that
     * what the reader typed WAS captured. This is the `upload-claim-parity` inverted
     * disclosure, reproduced against this guard.
     */
    const inverted: DiscardCopy = {
      ...DISCARD_COPY.noteCapture,
      body:
        'This clears the box you are typing in. What you typed has already been ' +
        'captured, and nothing on the record changes.',
    };
    // The three §3 bans do not see it…
    expect(proseOf(inverted)).not.toMatch(DELETION_VERBS);
    expect(proseOf(inverted)).not.toMatch(OVERSTATED_STAKES);
    expect(proseOf(inverted)).not.toMatch(RESTORE_PROMISE);
    // …nor does the required-claim check, which is the whole problem…
    expect(statesItNeverReachedTheRecord(proseOf(inverted))).toBe(true);
    // …and the affirmation detector does.
    expect(affirmsTheStagedThingReached(proseOf(inverted))).toBe(true);
  });

  it('a NEGATION-SHIELDED inversion is caught too — the bypass a SECOND reviewer found', () => {
    /*
     * The fix above closed one hole and opened a narrower one, and this is it. The
     * detector's exception is that a negation which GOVERNS the assertion makes it the
     * required claim; the first implementation read that as "a negation anywhere earlier
     * in the sentence", which a different independent clause satisfies while governing
     * nothing:
     *
     *     "Nothing else on this record changes: what you typed has already been captured"
     *
     * Every §3 ban passes it. `statesItNeverReachedTheRecord` passes it — "Nothing" and
     * "captured" are one sentence. And the un-bounded lookback passed it too, so the
     * guard read as hardened while admitting the same inverted disclosure it had just
     * been hardened against. The lookback now stops at the nearest `,`, `;` or `:`.
     */
    const shielded: DiscardCopy = {
      ...DISCARD_COPY.noteCapture,
      body:
        'This clears the note box. Nothing else on this record changes: what you ' +
        'typed has already been captured, and the notes it holds stay as they are.',
    };
    expect(proseOf(shielded)).not.toMatch(DELETION_VERBS);
    expect(proseOf(shielded)).not.toMatch(OVERSTATED_STAKES);
    expect(proseOf(shielded)).not.toMatch(RESTORE_PROMISE);
    expect(statesItNeverReachedTheRecord(proseOf(shielded))).toBe(true);
    // …and the only detector left standing must catch it.
    expect(affirmsTheStagedThingReached(proseOf(shielded))).toBe(true);
  });

  it('…and the narrowed lookback does not ban the two shipped bodies that rely on it', () => {
    // The exception is load-bearing for exactly two controls, and narrowing it must not
    // reach either. Asserted by name rather than through the parametrised sweep, so a
    // future narrowing that DID reach them names which one it broke.
    expect(
      affirmsTheStagedThingReached(proseOf(DISCARD_COPY.transcriptUnsent)),
    ).toBe(false);
    expect(
      affirmsTheStagedThingReached(proseOf(DISCARD_COPY.conflictDecision)),
    ).toBe(false);
  });

  it.each([
    'Your note was captured, though not confirmed.',
    'This has been recorded on the run.',
    'The text is already stored with this record.',
  ])('the affirmation detector trips on %s', (bad) => {
    expect(affirmsTheStagedThingReached(bad)).toBe(true);
  });

  it('…and does NOT trip on a negated affirmation, which is the required claim', () => {
    // The exception is load-bearing: every shipped body states its claim in exactly this
    // shape, so a detector without it would ban the copy it exists to protect.
    expect(affirmsTheStagedThingReached('Nothing in it has been read or stored.')).toBe(
      false,
    );
    expect(affirmsTheStagedThingReached('None of it has been recorded.')).toBe(false);
  });

  it('the ban would fire on a real control, not merely on a synthetic string', () => {
    // The exact shape a future slice is most likely to write: correct in every other
    // respect, and one verb wrong.
    const drifted: DiscardCopy = {
      ...DISCARD_COPY.noteCapture,
      body: DISCARD_COPY.noteCapture.body.replace('clears the box', 'deletes the box'),
    };
    expect(proseOf(drifted)).toMatch(DELETION_VERBS);
    // …and the shipped one does not, which is the pair that makes this meaningful.
    expect(proseOf(DISCARD_COPY.noteCapture)).not.toMatch(DELETION_VERBS);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// §5 — the copy is what a reader actually meets
// ═══════════════════════════════════════════════════════════════════════════════

describe('§5 the authored sentence reaches the screen', () => {
  it('the note capture control renders its trigger and its body verbatim', async () => {
    stubFetchRoutes({
      [`GET /api/experiments/demo/notes`]: { body: notesPage([noteFixture({ id: 'N-1' })]) },
    });
    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <UnmappedNotesPanel experimentId="demo" />
      </MemoryRouter>,
    );
    const box = await screen.findByLabelText('Capture a note');
    fireEvent.change(box, { target: { value: 'something worth keeping' } });

    const copy = DISCARD_COPY.noteCapture;
    fireEvent.click(screen.getByRole('button', { name: copy.trigger }));
    // Rendered, not merely present in a module — a source scan would pass on the import.
    expect(screen.getByText(copy.body)).toBeInTheDocument();
  });
});
