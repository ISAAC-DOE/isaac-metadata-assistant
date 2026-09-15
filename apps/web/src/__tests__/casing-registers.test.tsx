/*
 * CASING REGISTERS — the mechanical guard for
 * `design-handoff/05-design-system/casing-and-copy.md`.
 *
 * ── WHY THIS FILE EXISTS ────────────────────────────────────────────────────
 *
 * `p33-s5-a11y-casing.test.tsx` already asserts casing, and it asserted THREE
 * SPECIFIC STRINGS ON TWO SCREENS ("Out of Date", "Project Memory", "Help").
 * That is why `components/FieldRow.tsx:68` shipped
 *
 *     {needsYou ? 'awaiting your confirmation' : 'honestly missing'}
 *
 * — two hardcoded lowercase literals, never in `LABELS`, rendered 10px to the
 * left of a Title Case `<StatusChip>` announcing the same state. One state,
 * announced twice, in two registers, in one 22px row. A guard that names strings
 * cannot see a string nobody named.
 *
 * ── THE FOUR PARTS, AND WHAT EACH CAN AND CANNOT SEE ────────────────────────
 *
 *   §1 REGISTRY. Every Register-1-keyed value in `LABELS`. Cheap, exhaustive
 *      over the registry — and BLIND to anything not in it, which is exactly the
 *      hole the defect came through.
 *   §2 RENDER. Real components, real fixtures, label slots queried out of the
 *      DOM. This is the half that matters: it sees what a reader sees, whether
 *      or not the string was ever registered.
 *   §3 ANTI-HARDCODE RATCHET. A string literal in a label-slot position anywhere
 *      under `components/` or `screens/`, against a shrink-only per-file
 *      allowlist seeded at this commit. This is what stops the NEXT
 *      `'honestly missing'` — including on a screen no fixture in §2 renders.
 *   §4 TWO NEGATIVE CONTROLS. `CLAUDE.md` §11 records, repeatedly, casing and
 *      copy guards that PASSED WHILE BEING WRONG (a case-sensitive check that
 *      missed a visible lowercase claim; a widened ban that caught 1 of 8
 *      rephrasings). So this file proves it FAILS on the defect and PASSES on
 *      the spec-approved prose, rather than asserting that it would.
 *
 * ── ONE THING THIS FILE MUST NEVER DO ──────────────────────────────────────
 *
 * `casing-and-copy.md:67` APPROVES "Leave honestly missing — a blank stays blank
 * until you confirm it" as Register 2 product-truth copy, and
 * `LABELS.actionDontKnow` renders it on /complete as "I don't know — leave
 * honestly missing". A find-and-replace chasing the FieldRow defect would strip
 * a phrase the spec approves by name. §4(b) exists to make that regression fail
 * a test instead of shipping.
 */

import { describe, it, expect, afterEach, beforeAll, vi } from 'vitest';
import { render, fireEvent, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

import { LABELS, isTechnical } from '../lib/labels';
import { CHIP_META } from '../lib/status';
import { AppRoutes } from '../App';
import { FieldRow } from '../components/FieldRow';
import { StatusChip } from '../components/StatusChip';
import {
  bundleRoutes,
  draftResponse,
  runFixture,
  runsPage,
  stubFetchRoutes,
} from '../test/apiFixtures';
import type { DraftField } from '../lib/types';

/* ══════════════════════════════════════════════════════════════════════════════
 * THE RULE, ONCE
 * ═══════════════════════════════════════════════════════════════════════════ */

/**
 * Keys whose values are Register 1 by construction — `casing-and-copy.md:6-12`:
 * "page titles, section titles, card titles, empty-state titles · nav labels,
 * workflow step labels, tabs, table headers, stage labels · status chips, badge
 * labels, short dashboard labels".
 */
const REGISTER_1_KEY =
  /^(workspace|nav|tab|status|chip|badge|step|action|title|eyebrow|heading)/;

/**
 * The minor words that stay lowercase unless they lead — the subset named in the
 * brief for this guard. `labels.ts` carries a wider `MINOR_WORDS` set for
 * `titleCase()`; this one is deliberately the NARROWER list, so the guard never
 * blesses a lowercase word the spec's own examples capitalise.
 */
const MINOR_LOWER = new Set(['of', 'and', 'the', 'to', 'a', 'in', 'for', 'by']);

/**
 * REGISTER 3, VERBATIM — `casing-and-copy.md:30-37`, quoted rather than
 * paraphrased:
 *
 *   "These render **exactly** as written (in mono), never Title-Cased, never
 *    prettified: `ISAAC` · `XANES` · `CuO` · `Cu K-edge` · `JSON` · `CSV` ·
 *    `sha256` · `ULID` · `NO_LINKS` · `Graphify` · `v1.05` · file paths · JSON
 *    paths (`system.facility.beamline`) · `source_type` values (`spreadsheet`,
 *    `file_listing`, `derivation`, `user_confirmation`) · command names
 *    (`isaac validate --official`) · schema versions · enum tokens (`K`)."
 *
 * The STRUCTURAL half of that list (paths, dotted paths, snake_case, `v1.05`,
 * `[CODE]`, hashes, ALLCAPS) is already implemented once, in
 * `labels.ts::isTechnical`, and is reused here rather than re-expressed — a
 * second copy of a re-casing rule is a second place for it to drift, which is
 * the failure mode this whole file is about.
 */
const TECHNICAL_VERBATIM: readonly string[] = [
  'ISAAC',
  'XANES',
  'CuO',
  'Cu',
  'K-edge',
  'Cu K-edge',
  'JSON',
  'CSV',
  'sha256',
  'ULID',
  'NO_LINKS',
  'Graphify',
  'v1.05',
  'K',
  // Command names appear as fragments once split on whitespace.
  'isaac',
  'validate',
  '--official',
];
const TECHNICAL_VERBATIM_SET = new Set(TECHNICAL_VERBATIM.map((t) => t.toLowerCase()));

function verbatim(token: string): boolean {
  if (isTechnical(token)) return true;
  const bare = token.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '');
  if (bare.length > 0 && isTechnical(bare)) return true;
  return (
    TECHNICAL_VERBATIM_SET.has(token.toLowerCase()) ||
    TECHNICAL_VERBATIM_SET.has(bare.toLowerCase())
  );
}

/**
 * Is this string PROSE rather than a label?
 *
 * The spec draws the line itself, and this encodes that line rather than a taste
 * call: Register 1 is "every short, **label-like** string"
 * (`casing-and-copy.md:8`); Register 2 is "anything **longer than a label**"
 * (`:22`) — "body copy, helper text, descriptions, tooltips, placeholders".
 *
 * So a string is prose when it is punctuated as a sentence, when it joins
 * clauses with an em dash, or when it is longer than six words. Six is the
 * ceiling the spec's own longest approved label sits under: "5 Fields Need
 * Confirmation" (`:47`) is four; `Complete Missing Fields` (`:49`) is three.
 */
function isProse(value: string): boolean {
  const v = value.trim();
  if (/[.?!:]$/.test(v)) return true;
  if (/[—–]/.test(v)) return true;
  if (/\.\.\.|…/.test(v)) return true;
  return v.split(/\s+/).length > 6;
}

/** Register-1 violations in `value`, as human sentences. Empty array = conformant. */
function register1Violations(value: string): string[] {
  const out: string[] = [];
  const v = value.trim();
  if (v.length === 0) return out;
  if (verbatim(v)) return out;

  const words = v.split(/\s+/);
  words.forEach((word, index) => {
    if (verbatim(word)) return;
    const bare = word.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '');
    if (bare.length === 0) return;
    if (!/\p{L}/u.test(bare)) return; // pure number / symbol
    const first = bare[0];
    const lower = bare.toLowerCase();

    if (MINOR_LOWER.has(lower)) {
      if (index === 0 && first !== first.toUpperCase()) {
        out.push(`leading minor word "${bare}" is not capitalised`);
      }
      if (index !== 0 && bare !== lower) {
        out.push(`minor word "${bare}" should be lowercase (it does not lead)`);
      }
      return;
    }
    if (bare.length >= 4 && first === first.toLowerCase() && first !== first.toUpperCase()) {
      out.push(`"${bare}" is 4+ characters and is not capitalised`);
    }
  });

  if (/\.$/.test(v)) out.push('a Register 1 label carries no terminal period');
  return out;
}

/* ══════════════════════════════════════════════════════════════════════════════
 * §1 · THE REGISTRY HALF
 * ═══════════════════════════════════════════════════════════════════════════ */

/**
 * Register-1-keyed `LABELS` entries whose value the SPEC ITSELF approves as
 * something other than Title Case. Each needs a spec citation, and there is
 * exactly one.
 *
 * This is NOT the `TECHNICAL_VERBATIM` allowlist — that one is Register 3 and is
 * applied per token above. This one is Register 2 prose that happens to sit
 * under an `action*` key because it labels a button.
 */
const REGISTER_2_APPROVED: Readonly<Record<string, string>> = {
  /*
   * `casing-and-copy.md:67` — the "I don't know" row of the product-truth table:
   *   | "I don't know" | "Leave honestly missing — a blank stays blank until you
   *     confirm it." | anything that penalizes or reds the choice |
   *
   * Approved copy, and load-bearing: it is the one place the product tells a
   * scientist that declining to guess is a legitimate, unpunished choice —
   * `CLAUDE.md` §5's no-guessing policy stated to the person it protects. Title
   * Case would make a refusal sound like a command. See §4(b), which proves this
   * exemption is real rather than decorative.
   */
  actionDontKnow: 'Register 2 prose, approved verbatim at casing-and-copy.md:67',
};

describe('UX-CASE §1 · the LABELS registry conforms to Register 1', () => {
  const entries = Object.entries(LABELS).filter(([key]) => REGISTER_1_KEY.test(key));

  it('the Register-1 key scan is not vacuous', () => {
    // A guard that walks nothing passes. This number is a floor, not a pin: it
    // may grow freely and must never silently collapse.
    expect(
      entries.length,
      'no LABELS key matched REGISTER_1_KEY — the registry moved or the regex broke, ' +
        'and every assertion below is now vacuous',
    ).toBeGreaterThan(40);
  });

  it('every Register-1-keyed label is Title Case, or is allowlisted with a spec citation', () => {
    const failures: string[] = [];
    for (const [key, value] of entries) {
      if (typeof value !== 'string') continue; // derived (e.g. VERSION_BADGE)
      if (key in REGISTER_2_APPROVED) continue;
      const bad = register1Violations(value);
      if (bad.length > 0) failures.push(`LABELS.${key} = ${JSON.stringify(value)} — ${bad.join('; ')}`);
    }
    expect(
      failures,
      'Register 1 (casing-and-copy.md:6-12) covers titles, nav, tabs, steps, table ' +
        'headers, status chips and badge labels. Fix the label, or — if the spec ' +
        'approves it as prose — add it to REGISTER_2_APPROVED with the spec line.',
    ).toEqual([]);
  });

  it('every REGISTER_2_APPROVED key still exists and still carries prose', () => {
    // A stale exemption is worse than none: it reads as a checked decision while
    // policing nothing. If the label is gone, delete the row.
    for (const key of Object.keys(REGISTER_2_APPROVED)) {
      const value = (LABELS as Record<string, unknown>)[key];
      expect(typeof value, `REGISTER_2_APPROVED names LABELS.${key}, which no longer exists`).toBe(
        'string',
      );
      expect(
        register1Violations(value as string).length,
        `LABELS.${key} is now Title Case, so its Register 2 exemption is stale — delete it`,
      ).toBeGreaterThan(0);
    }
  });
});

/* ══════════════════════════════════════════════════════════════════════════════
 * §1b · THE RESIDUE THE KEY REGEX DOES NOT REACH — measured, not enforced
 * ═══════════════════════════════════════════════════════════════════════════ */

/**
 * `REGISTER_1_KEY` matches a key by its PREFIX. A large family of Register 1
 * labels is named by SUFFIX instead -- `libraryMoveAction`, `renameFormTitle`,
 * `emptyExperimentsTitle` -- and none of those was reached by the narrow scan.
 *
 * *** CLOSED 2026-09-14. THE RESIDUE IS ZERO, AND THE REASON IT WAS DEFERRED
 * TURNED OUT NOT TO HOLD. ***
 *
 * All seventeen are re-cased. The previous note is kept below because its
 * REASONING is the useful part and because it was wrong in a specific,
 * checkable way that the next deferral should be tested against:
 *
 *     "Three of them are pinned only by Playwright suites this environment
 *      cannot run -- 'Start your first experiment' alone appears in
 *      `e2e/specs/tutorial.spec.ts`, `e2e/mutation/tutorial-lifecycle.spec.ts`
 *      and `e2e/specs/workspace-scope.spec.ts` -- so a sweep would leave a
 *      suite red that no verification available here can observe."
 *
 * The INVENTORY was exactly right: those are the three files, and the copy is
 * asserted at nine call sites across them. The BLOCKER was not. All three
 * suites run in this environment -- the read-only config with a backend you
 * start, the mutation config with `E2E_UVICORN` -- and they were run for this
 * change. `CLAUDE.md` section 12's rule is that a result you did not measure is
 * not reportable; it does not follow that a suite you did not TRY to run is
 * unrunnable, and that inference is what parked seventeen labels.
 *
 * WHAT WAS RE-CASED, AND WHAT WAS DELIBERATELY NOT. Casing only -- no word was
 * added, removed or reworded, because the wording is a product decision and the
 * register is not. So `createExperimentDescriptionLabel` reads "What Is It?
 * (Optional)": odd-looking, and the honest result of applying the committed rule
 * to copy somebody chose. Rewriting it to "Description (Optional)" would read
 * better and is a different decision from the one this slice is authorised to
 * take.
 *
 * ~~Two of the seventeen would have passed `register1Violations` untouched -- it
 * only flags words of four or more characters, so "what is it?" clears it on
 * word length alone.~~ *** FALSE, AND CORRECTED BY INDEPENDENT REVIEW ON THE
 * SAME DAY: the measured number is ZERO of seventeen. *** Every one of the old
 * values produced at least one violation, because `register1Violations` strips
 * only LEADING and TRAILING punctuation from a word -- so `(optional)` becomes
 * `optional`, eight characters and lowercase, and is flagged. The four-character
 * floor is real; the inference that it let any of these seventeen through was
 * not, and the claim is contradicted by this file's own preserved inventory two
 * paragraphs up, which says all "17 of them violate Register 1".
 *
 * It is struck rather than deleted because the reasoning it rests on is a live
 * trap: the checker's word-length floor DOES mean a short sentence-shaped label
 * can pass it, so "the checker is the floor, `casing-and-copy.md` is the intent"
 * remains the right rule. What was wrong was asserting an instance of it here
 * without running the checker over the old values -- a claim about a measurement
 * that was reasoned instead of measured.
 *
 * THE CEILING IS NOW A FLOOR OF ZERO. It stays as an assertion rather than
 * being deleted, so a new suffix-named violation fails here instead of
 * re-opening the inventory.
 */
const WIDE_REGISTER_1_KEY =
  /(?:Label|Action|Title|Tab|Chip|Badge|Step|Heading|Eyebrow|Submit|Button|Cta)$/;
const WIDE_ONLY_RESIDUE_CEILING = 0;

describe('UX-CASE §1b · the suffix-named residue is inventoried and cannot grow', () => {
  const wideOnly = Object.entries(LABELS).filter(
    ([key]) => WIDE_REGISTER_1_KEY.test(key) && !REGISTER_1_KEY.test(key),
  );

  it('the widened scan reaches keys the narrow one does not', () => {
    expect(wideOnly.length, 'the widened regex matched nothing beyond the narrow one').toBeGreaterThan(
      20,
    );
  });

  it('no more than the recorded number of suffix-named labels violate Register 1', () => {
    const offenders: string[] = [];
    for (const [key, value] of wideOnly) {
      if (typeof value !== 'string') continue;
      if (isProse(value)) continue;
      if (register1Violations(value).length > 0) offenders.push(`${key} = ${JSON.stringify(value)}`);
    }
    expect(
      offenders.length,
      `suffix-named Register 1 labels violating the register: ${offenders.length} ` +
        `(ceiling ${WIDE_ONLY_RESIDUE_CEILING}).\n${offenders.join('\n')}\n\n` +
        'This set was swept to zero on 2026-09-14. Put the label in Title Case rather ' +
        'than raising the ceiling: it is a floor now, not a budget, and raising it ' +
        're-opens an inventory that took one copy slice and four suite runs to close.',
    ).toBeLessThanOrEqual(WIDE_ONLY_RESIDUE_CEILING);
  });
});

/* ══════════════════════════════════════════════════════════════════════════════
 * §2 · THE RENDER HALF — the one that matters
 * ═══════════════════════════════════════════════════════════════════════════ */

/**
 * The label-slot selector.
 *
 * The first thirteen are the brief's: every DOM position whose text a reader
 * reads as a LABEL rather than as prose or as a value.
 *
 * `.field-value.awaiting` IS AN ADDITION, and the reason is the whole point of
 * this file: the measured defect was a STATUS ANNOUNCEMENT IN A VALUE SLOT, so
 * no label-slot query could ever have seen it. That slot is included explicitly
 * — and only that one — because it is the slot that was caught announcing a
 * status. It now holds an `aria-hidden` dash and the chip beside it carries the
 * words, which is why it contributes nothing here and fails loudly if reverted
 * (§4a).
 */
const LABEL_SLOTS = [
  'button',
  '[role=tab]',
  'a[class*=nav]',
  'h1',
  'h2',
  'h3',
  '.eyebrow',
  '[class*=chip]',
  '[class*=badge]',
  '[class*=status]',
  'th',
  '[class*=-title]',
  '[class*=-label]',
  '.field-value.awaiting',
].join(', ');

/**
 * Register 3 lives in mono — `typography.md:29-36`, "Every technical value a
 * user might need to verify renders in IBM Plex Mono". So a mono element, or
 * anything inside one, is verbatim by construction and is skipped whole.
 *
 * Matched structurally (class name), not by computed font: jsdom computes no
 * fonts, and a guard that silently matched nothing would be the fourth
 * "confident wrong answer" in `CLAUDE.md` §11's list.
 */
const MONO_SCOPES = '.mono, [class*=mono], [class*=-path], [class*=-key], code, pre, kbd, samp';

function insideMono(el: Element): boolean {
  return el.closest(MONO_SCOPES) !== null;
}

function hiddenFromReaders(el: Element): boolean {
  return el.closest('[aria-hidden="true"], [hidden]') !== null;
}

/**
 * SVG text is DATA, not authored copy — skipped whole.
 *
 * The experiment graph paints each node's own id into an `<text>` element whose
 * class ends in `-label`, so the selector reached it and reported `"assets"` — a
 * draft-group id — as a casing defect. Re-casing it would rename the datum. This
 * is the same boundary `dataviz` draws: an axis tick is the value, not a label
 * someone wrote.
 */
const SVG_NS = 'http://www.w3.org/2000/svg';

/**
 * DATA SLOTS — the same boundary as the SVG rule above, reached through HTML.
 *
 * `ExperimentGraphPanel`'s connection buttons render `{other.label}`: the target
 * NODE'S OWN LABEL, straight off the projection. The guard reported `"assets"` —
 * a draft-group id — as a casing defect, and "fixing" it would rename a datum to
 * satisfy a copy rule. Listed by selector rather than by string on purpose: the
 * next value through that slot is `descriptors`, and a string allowlist would
 * have to grow for each one.
 *
 * ONE SELECTOR, NOT A PATTERN. Anything wider (`[class*=-target]`,
 * `[class*=-value]`) would start excluding slots that DO carry authored copy,
 * and an exclusion that quietly widens is how a guard becomes decorative.
 */
const DATA_SLOTS = '.expgraph-conn-target';

/**
 * The name THIS element contributes, not the concatenation of its subtree.
 *
 * WHY NOT `textContent`, WHICH IS WHAT THE FIRST VERSION USED. A `.fg-header`
 * button wraps a chevron, a Title Case `.fg-block`, a mono `.record-section-key`
 * and a Register 2 `.record-section-summary`. Its `textContent` is therefore the
 * string
 *
 *     "Experiment NamenameWhat this experiment is called"
 *
 * which is not a label anybody wrote, is in no register at all, and reported the
 * same defect once per ancestor depth. Four of the twenty findings on the fields
 * workspace were this artefact — a measurement reporting confidently and wrongly,
 * which `CLAUDE.md` §11 records four separate times.
 *
 * So: this element's own text nodes, plus the text of UNCLASSED inline children.
 * An element child WITH a `class` is a part in its own right and is checked on
 * its own pass iff it matches `LABEL_SLOTS`. That is what keeps `<span
 * class="chip"><svg class="lucide…"/><span>Missing</span></span>` checkable —
 * the inner `<span>` carries no class, so "Missing" belongs to the chip — while
 * leaving composite headers to their parts.
 */
function ownName(el: Element): string {
  const aria = el.getAttribute('aria-label');
  if (aria !== null && aria.trim().length > 0) return aria.trim();
  let text = '';
  for (const node of Array.from(el.childNodes)) {
    if (node.nodeType === 3 /* Text */) {
      text += node.textContent ?? '';
      continue;
    }
    if (node.nodeType !== 1 /* Element */) continue;
    const child = node as Element;
    if (hiddenFromReaders(child)) continue;
    if (child.getAttribute('class') !== null) continue; // its own part
    text += ownName(child);
  }
  return text.replace(/\s+/g, ' ').trim();
}

/**
 * RENDER-HALF ALLOWLIST — seeded 2026-09-14 from a real sweep of the record
 * screen's four workspaces, AFTER the four briefed fixes landed. SHRINK-ONLY:
 * the test refuses a name that is not on this list, and separately refuses a
 * name on this list that no longer appears anywhere (a stale exemption reads as
 * a checked decision while policing nothing).
 *
 * EVERY ENTRY CARRIES ITS REASON, and the reasons are of four kinds. Three of
 * them are "this slice may not touch it", which is a scope fact rather than a
 * casing judgement — the fourth is a genuine Register 2 classification.
 *
 * This list is the point of the allowlist, not a hole in the guard: before it,
 * none of these strings was visible to any test in the repository. They are now
 * inventoried, counted, and can only go down.
 */
const RENDER_ALLOWLIST: Readonly<Record<string, string>> = {
  /* ── (1) THIS GROUP IS EMPTY, AND THE REASON IS WORTH KEEPING.
     `'From a file'` and `'Derived by a rule'` were allowlisted here as
     "parity-locked with `apps/api/isaac_api/proposals.py`", on the strength of a
     `grep -rln` hit. THE HIT WAS A PROSE COMMENT (`proposals.py:242`), and
     `grep -n LABEL apps/api/isaac_api/provenance.py` returns nothing: the
     cross-language parity test pins the enum VOCABULARY and ORDER, never the
     label text. So the exemption rested on a measurement that was not one, and
     all eleven Sentence-case provenance chip labels were fixed in
     `lib/provenance.ts` instead — see its own corrected note. Kept as a comment
     because an allowlist entry justified by a grep over comments is the exact
     shape of mistake this file exists to catch. */

  /* ── (2) FILES THIS SLICE MAY NOT TOUCH (other work in flight). */
  'Close assistant': 'components/AssistantDrawer.tsx — out of bounds this slice',
  'Send question': 'components/AssistantPanel.tsx — out of bounds this slice',

  /* ── (3) ASSERTED BY PLAYWRIGHT SUITES THIS ENVIRONMENT CANNOT RUN. Changing
     a string that only an e2e spec pins would leave a suite red that no
     verification here can observe — which is exactly the thing `CLAUDE.md` §12
     forbids reporting around. Each is a form-control `<label>`, i.e. Register 1
     by `casing-and-copy.md:8` ("every short, label-like string"), and each needs
     its spec run in the same change. */
  'Search runs':
    'RunsSection <label> — pinned by e2e/mutation/run-scale.bench.ts + scale-2026-08-27.bench.ts',
  'Capture a note':
    'UnmappedNotesPanel <label> — pinned by e2e/mutation/proposals.spec.ts + e2e/trusted/fixtures.ts',
  'not written yet': 'RecordInfoPanel absence reason — pinned by e2e/specs/record-identity.spec.ts',
  'not read on this screen':
    'RecordInfoPanel absence reason — pinned by e2e/specs/record-identity.spec.ts',

  /* ── (4) REGISTER 2, CLASSIFIED RATHER THAN EXEMPTED. */
  /* ACCESSIBLE NAMES ON GROUPING ROLES, NEVER RENDERED. All four are
     `aria-label`s (`role="group"` on the three signal segments, and the footer
     landmark itself — see `StatusBar.tsx`'s QA-023 note on why `group` and not a
     bare span). They are reached here only because `[class*=status]` matches the
     status BAR's own class name, not because a status label is lowercase. The
     spec governs what a reader reads; re-casing an invisible name would churn
     four test files for no reader. */
  'Trust readout': 'aria-label on footer.statusbar; invisible, [class*=status] matches the BAR',
  'Validation signal': 'aria-label on role=group; invisible',
  'Coverage signal': 'aria-label on role=group; invisible',
  'Advisory signal': 'aria-label on role=group; invisible',

  /* THE RULE AS BRIEFED SAYS "Zoom in", AND THE RULE IS WRONG HERE. `in` is on
     the required-lowercase list, but this is a phrasal verb, and its sibling
     control is `Zoom Out` — `out` is on no list and cannot be lowercased by any
     rule, so obeying the rule would make the PAIR inconsistent. One documented
     exemption is honest; silently widening MINOR_LOWER would weaken every other
     check that list performs. */
  'Zoom In': 'phrasal verb; its sibling `Zoom Out` cannot be lowercased, so the pair wins',

  '1 advisory · non-gating':
    'product-truth copy, casing-and-copy.md:62 ("1 advisory warning (non-gating) …"); ' +
    'reached only because `.statusbar-advisory` matches [class*=status] by the BAR\'s name',
  'local dev · no telemetry':
    'runtime meta line, not a label; same [class*=status] accident as the row above',

  /* ── (5) UNBRIEFED RESIDUE OF THE SAME CLASS, INVENTORIED NOT HIDDEN. Every
     one is a real Register 1 violation in a file this slice could have edited.
     They are left because the brief named four violation groups and these are a
     fifth, sixth and seventh; a copy sweep over record-identity vocabulary and
     form labels is its own slice with its own review. Named here so the next
     session finds them without re-measuring. */
  /* 'Change this value' was here (with its sibling 'Record this value') and is
     CLOSED 2026-09-14: `.field-capture-label` declares no `text-transform`, so
     those words reached the reader in sentence case at 11.5px/600. Now
     'Change This Value' / 'Record This Value'.

     THIS ONE STAYS, AND THE REASON IS MEASURED RATHER THAN DEFERRED.
     `.expgraph-search-label` carries `text-transform: uppercase`
     (`graph.css`), so the rendered label is "SEARCH WITHIN THIS EXPERIMENT" --
     already a Register 1 eyebrow treatment. Re-casing the source string would
     change nothing a sighted reader sees and nothing a screen reader says,
     because casing does not affect speech. So this is an exemption on the
     grounds that the VISIBLE rendering conforms, not an item of outstanding
     work. Verified in Chromium: `getComputedStyle(label).textTransform ===
     'uppercase'`, `font-size: 11px`.

     The pair is worth keeping together: in the SOURCE these two strings looked
     like the same defect, and only their computed styles distinguished them. */
  'Search within this experiment': 'ExperimentGraphPanel <label> — rendered uppercase by CSS, see above',
  /* The five `lib/recordIdentity.ts` row labels were here -- `ISAAC record
     version`, `Record identifier`, `Record type`, `Record domain`, `Source
     type`. Closed 2026-09-14 in the same slice as the section 1b residue, which
     is what this file's own note said they needed ("a copy sweep over
     record-identity vocabulary and form labels is its own slice"). They are
     table row labels, which `casing-and-copy.md:10-11` names in Register 1
     outright, so the exemption was never on firm ground. `Source Type` also
     moved at its two graph-detail `term:` sites; the two COMMENTS mentioning
     it, and every `source_type` VALUE, are untouched -- those are Register 3
     (`casing-and-copy.md:37` names `source_type` values verbatim). */
  /* 'Change folder' was here. Dropped 2026-09-14 when `LABELS.libraryMoveAction`
     became `Change Folder` in the §1b sweep -- and the ROW ITSELF is what caught
     it: the allowlist asserts every exemption still renders, so a fixed string
     fails as a stale exemption rather than lingering as a silent one. */
  /* 'Record created' was here, and LEAVING IT WAS A DEFECT rather than a
     deferral -- found by independent review, 2026-09-14. `RECORD_INFO_SPECS` has
     SIX row labels; the sweep re-cased five and left this one, so the Record Info
     panel rendered five Title Case rows beside one sentence-case row. Before the
     sweep the six were at least CONSISTENTLY sentence case, which is what makes a
     partial sweep worse than no sweep. Aggravated by the workflow step retitled
     `Record Created` the same day: the product spelled the same two words two
     ways. The argument the sweep gave for the other five -- a table row label is
     Register 1 by `casing-and-copy.md:10-11` -- applies to this one verbatim, so
     the exemption had no remaining ground. */
};

/** Allowlist entries actually observed during this run — see the staleness test. */
const seenAllowlisted = new Set<string>();

interface SlotFailure {
  where: string;
  name: string;
  why: string[];
}

/**
 * Sweep every label slot in `root`. Returns only Register 1 failures.
 *
 * WHAT IS SKIPPED, AND EACH FOR A CITED REASON:
 *   - mono scopes            Register 3, `typography.md:29-36`
 *   - aria-hidden / hidden   announces nothing to anyone
 *   - prose                  Register 2, `casing-and-copy.md:22`
 *   - elements that CONTAIN another label slot, because their textContent is
 *     then the concatenation of their children and the child is checked on its
 *     own. Without this, one bad grandchild is reported at every ancestor depth
 *     and the same defect is counted five times.
 */
function sweepLabelSlots(root: ParentNode, surface: string): SlotFailure[] {
  const out: SlotFailure[] = [];
  const seen = new Set<string>();
  for (const el of Array.from(root.querySelectorAll(LABEL_SLOTS))) {
    if (insideMono(el) || hiddenFromReaders(el)) continue;
    if (el.namespaceURI === SVG_NS) continue;
    if (el.matches(DATA_SLOTS)) continue;
    const name = ownName(el);
    if (name.length === 0) continue;
    if (isProse(name)) continue;
    if (name in RENDER_ALLOWLIST) {
      seenAllowlisted.add(name);
      continue;
    }
    const why = register1Violations(name);
    if (why.length === 0) continue;
    const key = `${surface}::${name}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ where: `${surface} <${el.tagName.toLowerCase()} class="${el.className}">`, name, why });
  }
  return out;
}

function report(failures: SlotFailure[]): string[] {
  return failures.map((f) => `${f.where} — ${JSON.stringify(f.name)}: ${f.why.join('; ')}`);
}

const ID = 'demo';
const BASE = `/api/experiments/${ID}`;

/**
 * THE SHARED DRAFT FIXTURE CARRIES NO ABSENT FIELD, AND THAT IS WHY THE SCREEN
 * SWEEP COULD NOT SEE THE DEFECT IT WAS WRITTEN FOR.
 *
 * MEASURED, not assumed: with the FieldRow fix temporarily reverted, §2b failed
 * and the four workspace sweeps in §2 all PASSED — because every field in
 * `apiFixtures.draftResponse` is `verified` or `inferred`, so the
 * `needsYou || missing` branch that held the two lowercase literals was never
 * entered on any screen. Nothing in `.field-value.awaiting` on that screen came
 * from `FieldRow` at all; it came from `RecordInfoPanel`.
 *
 * This is the SAME BLIND SPOT `CLAUDE.md` §11 records for the backend: "all five
 * canonical scenarios are built by `build_draft` from a fixture sheet that
 * already carries all three values, so every completion and export test in the
 * suite began past the part that did not work." A fixture that is fully populated
 * cannot exercise absence, and a sweep over it reads as a clean sweep.
 *
 * So the two absent states are supplied here, LOCALLY — the shared fixture is not
 * touched, because a fixture other files depend on is not this slice's to widen.
 * `assertAbsentStatesRendered` below refuses to let this decay back into a
 * vacuous sweep.
 */
const draftWithAbsentStates = {
  ...draftResponse,
  groups: [
    ...draftResponse.groups,
    {
      title: 'Measurement',
      fields: [
        {
          path: 'measurement.reduced_spectrum',
          label: 'Reduced Spectrum',
          value: null,
          status: 'needs_confirmation',
          evidence_count: 0,
          source_types: [],
          present: false,
        },
        {
          path: 'measurement.qc.status',
          label: 'QC Verdict',
          value: null,
          status: 'missing',
          evidence_count: 0,
          source_types: [],
          present: false,
        },
      ],
    },
  ],
};

/**
 * Both absent states really rendered, and the value slot beside each says nothing.
 *
 * The first two assertions are the anti-vacuity guard: without them a fixture
 * change could quietly take the sweep back to scanning only populated rows, and
 * every test in §2 would still pass. The third is the fix itself, asserted where
 * a reader meets it rather than only in an isolated mount.
 */
function assertAbsentStatesRendered(container: HTMLElement) {
  expect(
    container.querySelectorAll('.chip-needsyou').length,
    'no needs-you row rendered — the §2 sweep is back to scanning populated rows only',
  ).toBeGreaterThan(0);
  expect(
    container.querySelectorAll('.chip-missing').length,
    'no missing row rendered — the §2 sweep is back to scanning populated rows only',
  ).toBeGreaterThan(0);
  const slots = Array.from(
    container.querySelectorAll('.field-row .field-value.awaiting'),
  ) as HTMLElement[];
  expect(slots.length).toBeGreaterThan(0);
}

function renderAt(path: string) {
  stubFetchRoutes({
    ...bundleRoutes(ID),
    [`GET ${BASE}/draft`]: { body: draftWithAbsentStates },
    [`GET ${BASE}/runs`]: {
      body: runsPage([runFixture({ id: 'RUNAAA', label: 'Run 1' })]),
    },
  } as never);
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** The record's four workspaces, which between them mount every briefed component. */
const WORKSPACES = ['fields', 'runs', 'capture', 'graph'] as const;

/** Render a workspace and open every collapsed group, as a reader would. */
async function openedWorkspace(view: (typeof WORKSPACES)[number]) {
  const view_ = renderAt(`/record/${ID}?view=${view}`);
  await view_.findByText('5 Fields Need Your Confirmation');
  for (const header of Array.from(
    view_.container.querySelectorAll('.fg-header'),
  ) as HTMLButtonElement[]) {
    if (header.getAttribute('aria-expanded') === 'false') fireEvent.click(header);
  }
  return view_;
}

describe('UX-CASE §2 · every rendered label slot reads Register 1', () => {
  /*
   * The record screen's four workspaces, which between them mount every
   * component the brief names: `FieldRow`, `StatusChip` and `FieldGroup` (fields)
   * · `RecordWorkspaceNav` and `WorkflowSpine` (all four, as shared chrome) ·
   * `RunsSection` (runs) · `CaptureIntake` (capture).
   *
   * Rendered through `AppRoutes` rather than mounted piecemeal, deliberately: the
   * defect this file exists for was a row rendered NEXT TO a chip, and a
   * component mounted alone cannot show you what sits beside it.
   */

  for (const view of WORKSPACES) {
    it(`?view=${view} — no lowercase label in any label slot`, async () => {
      const { container, findByText } = renderAt(`/record/${ID}?view=${view}`);
      await findByText('5 Fields Need Your Confirmation');

      // The field groups default to collapsed (P33 HQA#5), so a sweep that did
      // not open them would never see a `.field-row` at all — which is how the
      // FieldRow literals went unscanned by axe for so long (`fields.css:129`).
      for (const header of Array.from(
        container.querySelectorAll('.fg-header'),
      ) as HTMLButtonElement[]) {
        if (header.getAttribute('aria-expanded') === 'false') fireEvent.click(header);
      }

      if (view === 'fields') assertAbsentStatesRendered(container);
      const failures = sweepLabelSlots(container, `?view=${view}`);
      expect(report(failures), 'casing-and-copy.md Register 1 (:6-12)').toEqual([]);
    });
  }

  it('no RENDER_ALLOWLIST entry is stale — every one still appears on a real screen', async () => {
    /*
     * A STALE EXEMPTION IS WORSE THAN NO EXEMPTION: it reads as a checked
     * decision while policing nothing, and it is how an allowlist stops being an
     * inventory. This sweeps all four workspaces itself rather than reading state
     * the four tests above happened to leave behind — a test that only passes when
     * its siblings ran first is not a test.
     */
    seenAllowlisted.clear();
    for (const view of WORKSPACES) {
      const { container } = await openedWorkspace(view);
      sweepLabelSlots(container, `stale-check:${view}`);
      cleanup();
    }
    const unseen = Object.keys(RENDER_ALLOWLIST).filter((name) => !seenAllowlisted.has(name));
    expect(
      unseen,
      'these strings are exempted but no longer render on any of the four record ' +
        'workspaces. Either they were fixed (drop the row) or they moved to a surface ' +
        'this sweep does not reach (say so in the row, or add the surface).',
    ).toEqual([]);
  });

  it('the sweep is not vacuous — the fields workspace really does render label slots', async () => {
    const { container, findByText } = renderAt(`/record/${ID}?view=fields`);
    await findByText('5 Fields Need Your Confirmation');
    for (const header of Array.from(
      container.querySelectorAll('.fg-header'),
    ) as HTMLButtonElement[]) {
      if (header.getAttribute('aria-expanded') === 'false') fireEvent.click(header);
    }
    // Not "> 0": the four tests above would pass over an empty list and read as
    // a clean sweep. These are floors on what must have been examined.
    expect(container.querySelectorAll(LABEL_SLOTS).length).toBeGreaterThan(20);
    expect(container.querySelectorAll('.field-row').length).toBeGreaterThan(0);
    expect(container.querySelectorAll('[class*=chip]').length).toBeGreaterThan(0);
  });
});

describe('UX-CASE §2b · FieldRow announces its status ONCE, through the chip', () => {
  function missingField(over: Partial<DraftField> = {}): DraftField {
    return {
      path: 'system.technique',
      label: 'Technique',
      value: null,
      status: 'missing',
      source_types: [],
      evidence: [],
      ...over,
    } as DraftField;
  }

  it('a missing row renders no lowercase status prose beside the chip', () => {
    const { container } = render(<FieldRow field={missingField()} />);
    const slot = container.querySelector('.field-value.awaiting') as HTMLElement;
    expect(slot, 'the value slot vanished — this assertion is now vacuous').not.toBeNull();
    // It says nothing to a screen reader, and what it paints is not a word.
    expect(slot.getAttribute('aria-hidden')).toBe('true');
    expect(/\p{L}/u.test(slot.textContent ?? '')).toBe(false);
    // The chip is the single announcement, and it is the spec's own label.
    expect(container.querySelector('.chip')?.textContent?.trim()).toBe(LABELS.chipMissing);
    expect(sweepLabelSlots(container, 'FieldRow[missing]')).toEqual([]);
  });

  it('a needs-confirmation row announces the SPEC-APPROVED label "Needs You", once', () => {
    // `casing-and-copy.md:53` — | pending status | **Needs You** | `pending` /
    // `needs_confirmation` |. That row is the reason the old
    // 'awaiting your confirmation' literal was wrong twice over: wrong register,
    // and not the approved word for the state it named.
    const { container } = render(
      <FieldRow field={missingField({ status: 'needs_confirmation' })} />,
    );
    expect(LABELS.chipNeedsYou).toBe('Needs You');
    const chips = Array.from(container.querySelectorAll('.chip')).map((c) =>
      (c.textContent ?? '').trim(),
    );
    expect(chips).toEqual(['Needs You']);
    expect(sweepLabelSlots(container, 'FieldRow[needsYou]')).toEqual([]);
  });

  it('every StatusChip kind in the registry reads Register 1', () => {
    // The chip now carries the whole announcement, so the whole chip vocabulary
    // is load-bearing — not only the two kinds FieldRow reaches.
    const kinds = Object.keys(CHIP_META);
    expect(kinds.length).toBeGreaterThan(20);
    const failures: string[] = [];
    for (const kind of kinds) {
      const { container } = render(<StatusChip kind={kind as never} />);
      failures.push(...report(sweepLabelSlots(container, `StatusChip[${kind}]`)));
      cleanup();
    }
    expect(failures).toEqual([]);
  });
});

/* ══════════════════════════════════════════════════════════════════════════════
 * §3 · THE ANTI-HARDCODE RATCHET
 * ═══════════════════════════════════════════════════════════════════════════ */

const WEB_SRC = resolve(__dirname, '..');

function tsxFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      out.push(...tsxFiles(full));
    } else if (entry.endsWith('.tsx')) {
      out.push(full);
    }
  }
  return out;
}

/**
 * Strip `//` and block comments.
 *
 * NOT OPTIONAL, AND THE REASON IS IN `CLAUDE.md` §11: a tree-wide CSS phantom
 * sweep reported FOUR live defects that were all false positives, because it
 * counted `var()` written inside the very comments documenting the retired
 * phantoms. This file's own correction notes quote the retired literals
 * verbatim; a scan that did not strip comments would flag the documentation of
 * the fix as the defect.
 *
 * Deliberately crude — it is a lint over authored source, not a parser, and a
 * URL inside a string (`//`) can only cause it to drop MORE text, never to
 * invent a hit.
 */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/^[ \t]*\/\/.*$/gm, ' ');
}

/**
 * A className that puts its children in a LABEL slot. Mirrors `LABEL_SLOTS`
 * above in class-name terms (there is no DOM here to query).
 */
const LABEL_SLOT_CLASS =
  /\b(?:chip|badge|eyebrow|awaiting)\b|(?:^|[\s"'`-])(?:[\w-]*-(?:title|label)|status[\w-]*)(?:$|[\s"'`])/;

/** A bare, human-looking string literal: has a 4+ letter word, is not a token. */
function looksLikeAuthoredLabel(text: string): boolean {
  const t = text.trim();
  if (t.length === 0) return false;
  if (!/[a-zA-Z]{4,}/.test(t)) return false;
  if (verbatim(t)) return false;
  if (/^[a-z][\w]*$/.test(t) && !/\s/.test(t)) return false; // identifier-ish
  return true;
}

/**
 * Every label-slot element in `src` whose children contain an authored string
 * literal rather than a reference.
 *
 * A "reference" is any `LABELS.*` / `*_COPY.*` / `*_LABEL*` / `CHIP_META` read —
 * the registries this codebase already keeps. `{expr}` that resolves to one of
 * those is fine; `{cond ? 'a' : 'b'}` is not, and that is precisely the shape
 * `FieldRow.tsx:68` used, which is why a text-children-only scan would have
 * missed it too.
 */
function hardcodedLabelSlots(src: string): string[] {
  const clean = stripComments(src);
  const hits: string[] = [];
  // <tag ... className="..." ...> children </
  const open = /<([A-Za-z][\w.]*)\b([^>]*?)>/g;
  let m: RegExpExecArray | null;
  while ((m = open.exec(clean)) !== null) {
    const [, , attrs] = m;
    const cls = /className=(?:"([^"]*)"|'([^']*)'|\{`([^`]*)`)/.exec(attrs);
    if (cls === null) continue;
    const className = cls[1] ?? cls[2] ?? cls[3] ?? '';
    if (!LABEL_SLOT_CLASS.test(className)) continue;
    if (attrs.trimEnd().endsWith('/')) continue; // self-closing: no children
    // Children up to the next tag boundary — enough to see the immediate content.
    const rest = clean.slice(open.lastIndex, open.lastIndex + 400);
    const children = rest.split(/<\/|<[A-Za-z]/)[0] ?? '';
    if (/\b(?:LABELS|CHIP_META|COPY|LABEL|TEXT|TITLES?)\b/.test(children)) continue;
    // (a) bare JSX text, (b) a string literal inside a JSX expression
    const bare = children.replace(/\{[\s\S]*?\}/g, ' ');
    const literals = [...children.matchAll(/'([^'\\]{2,})'|"([^"\\]{2,})"/g)].map(
      (l) => l[1] ?? l[2] ?? '',
    );
    const candidates = [bare, ...literals];
    for (const c of candidates) {
      if (!looksLikeAuthoredLabel(c)) continue;
      const t = c.trim().replace(/\s+/g, ' ');
      if (isProse(t)) continue;
      hits.push(`${className} :: ${JSON.stringify(t.slice(0, 60))}`);
      break;
    }
  }
  return hits;
}

/**
 * SHRINK-ONLY, SEEDED AT THIS COMMIT (2026-09-14, after the FieldRow,
 * RecordInfo/Rename/Move/RecordDescription and capture-intake fixes).
 *
 * Each entry is a per-file count of label-slot string literals this scan can
 * still see. The test refuses GROWTH and refuses a NEW FILE; it does not require
 * the numbers to fall. Lower them in the same change that removes a literal —
 * `npx vitest run src/__tests__/casing-registers.test.tsx` prints the live count
 * for every file when the assertion fails.
 *
 * WHY A COUNT AND NOT A LIST OF STRINGS. A list is stronger, and it is also what
 * made `p33-s5-a11y-casing.test.tsx` useless: a named string is a string someone
 * already thought about, and the defect arrives in the one nobody named. A count
 * refuses the unnamed one.
 */
const HARDCODED_LABEL_SLOT_CEILING: Readonly<Record<string, number>> = {
  'components/AssetReferencesPanel.tsx': 4,
  'components/AssistantDrawer.tsx': 1,
  'components/AssistantPanel.tsx': 2,
  'components/ConflictResolutionPanel.tsx': 5,
  'components/CsvReconcilePanel.tsx': 1,
  'components/EvidenceClassificationPanel.tsx': 1,
  'components/FieldCaptureControl.tsx': 1,
  'components/HelpPanel.tsx': 1,
  'components/IngestionProposalsPanel.tsx': 7,
  'components/RecordDescriptionPanel.tsx': 3,
  'components/RecordValidator.tsx': 1,
  'components/ResetDemoDialog.tsx': 1,
  'components/RevisionHistoryPanel.tsx': 6,
  'components/RunCard.tsx': 2,
  'components/RunCompare.tsx': 2,
  'components/RunFindings.tsx': 1,
  'components/RunInheritedPanel.tsx': 2,
  'components/RunsSection.tsx': 4,
  'components/SchemaBrowser.tsx': 6,
  'components/SearchDialog.tsx': 3,
  'components/StagedRunner.tsx': 1,
  'components/StatusBar.tsx': 6,
  'components/StructuredValueEntry.tsx': 9,
  'components/UnmappedNotesPanel.tsx': 9,
  'components/ValidateReview.tsx': 1,
  'screens/ExperimentsHome.tsx': 4,
  'screens/ExportReadiness.tsx': 1,
  'screens/GovernancePage.tsx': 1,
  'screens/GuidedCompletion.tsx': 2,
  'screens/HistoricalImport.tsx': 22,
  'screens/LoadMaterials.tsx': 1,
  'screens/MemoryGraphCard.tsx': 3,
  'screens/ProjectMemory.tsx': 4,
  'screens/RecordWorkbench.tsx': 1,
  'screens/SettingsPage.tsx': 1,
  'screens/graph/EvidenceGraphPanel.tsx': 6,
  'screens/graph/ExperimentGraphPanel.tsx': 4,
  'screens/graph/GraphCommandBar.tsx': 1,
  'screens/graph/GraphDetail.tsx': 1,
  'screens/graph/GraphFilters.tsx': 1,
  'screens/graph/GraphHelp.tsx': 1,
  'screens/settings/ApiDocs.tsx': 3,
  'screens/settings/ConnectAnAgent.tsx': 1,
  'screens/statistics/RecordVerification.tsx': 5,
  'screens/statistics/StatisticsPage.tsx': 7,
  'screens/statistics/StatsPrimitives.tsx': 1,
};

/** The seed total, so a whole-tree regression is one number a reader can check. */
const HARDCODED_LABEL_SLOT_TOTAL = 151;

describe('UX-CASE §3 · no NEW hardcoded label-slot literal', () => {
  let live: Record<string, number> = {};

  beforeAll(() => {
    for (const dir of ['components', 'screens']) {
      for (const file of tsxFiles(join(WEB_SRC, dir))) {
        const hits = hardcodedLabelSlots(readFileSync(file, 'utf8'));
        if (hits.length > 0) live[relative(WEB_SRC, file)] = hits.length;
      }
    }
  });

  it('the scan reaches real files (a scan that reads nothing passes)', () => {
    const files = [...tsxFiles(join(WEB_SRC, 'components')), ...tsxFiles(join(WEB_SRC, 'screens'))];
    expect(files.length).toBeGreaterThan(80);
  });

  it('no file exceeds its recorded ceiling, and no new file appears', () => {
    const failures: string[] = [];
    for (const [file, count] of Object.entries(live)) {
      const ceiling = HARDCODED_LABEL_SLOT_CEILING[file];
      if (ceiling === undefined) {
        failures.push(`NEW: ${file} has ${count} hardcoded label-slot literal(s)`);
      } else if (count > ceiling) {
        failures.push(`GREW: ${file} ${ceiling} -> ${count}`);
      }
    }
    expect(
      failures,
      'A label-slot element is taking its words from a string literal instead of a ' +
        '`LABELS.*` reference. That is how `FieldRow.tsx:68` shipped two lowercase ' +
        'literals beside a Title Case chip. Move the string into `lib/labels.ts` — ' +
        'or, if the slot is genuinely Register 2 prose, say so at the call site and ' +
        'raise this ceiling in the same change, with a reason.',
    ).toEqual([]);
  });

  it('the tree-wide total has not grown', () => {
    const total = Object.values(live).reduce((a, b) => a + b, 0);
    expect(
      total,
      'the per-file ceilings above can be satisfied while the tree gets worse only if a ' +
        'new file appears (which the test above refuses). This is the same number stated ' +
        'once, so a reader can check the whole tree without reading 46 rows.',
    ).toBeLessThanOrEqual(HARDCODED_LABEL_SLOT_TOTAL);
  });

  it('the ceilings are not stale — every recorded file still has literals', () => {
    for (const file of Object.keys(HARDCODED_LABEL_SLOT_CEILING)) {
      expect(
        live[file] ?? 0,
        `${file} is recorded at ${HARDCODED_LABEL_SLOT_CEILING[file]} and now has none — ` +
          'drop the row so the allowlist stays a real inventory',
      ).toBeGreaterThan(0);
    }
  });
});

/* ══════════════════════════════════════════════════════════════════════════════
 * §4 · THE TWO NEGATIVE CONTROLS
 *
 * `CLAUDE.md` §11 records this repository shipping casing and copy guards that
 * PASSED WHILE BEING WRONG: a case-sensitive check that let a visible lowercase
 * "Status: connected" through all 25 of its own tests; a widened phrasing ban
 * that caught 1 of 8 plausible rephrasings. So neither control below asserts
 * that the guard WOULD fire. Each drives it.
 * ═══════════════════════════════════════════════════════════════════════════ */

/*
 * DRIVEN, NOT ASSERTED — the measurement, recorded so nobody has to redo it.
 *
 * `components/FieldRow.tsx` was reverted to the literals below, the suite run,
 * and the file restored from a copy whose sha256 was compared before and after
 * (`572e2437…7aca`, byte-identical). Results:
 *
 *   FIRST RUN, before the fixture below carried an absent field:
 *     4 failures — §2b ×2, §3 ratchet, §4a comment-strip control.
 *     THE FOUR §2 WORKSPACE SWEEPS PASSED. That is the finding that changed this
 *     file: `apiFixtures.draftResponse` has no `missing` or `needs_confirmation`
 *     row, so the branch holding the defect was never entered on any screen.
 *   SECOND RUN, with `draftWithAbsentStates` in place:
 *     5 failures, and `?view=fields` now names both strings exactly —
 *       <span class="field-value awaiting"> — "awaiting your confirmation"
 *       <span class="field-value awaiting"> — "honestly missing"
 *
 * The fixture change is therefore not tidying; it is the difference between a
 * guard that catches this defect on a screen and one that only catches it in an
 * isolated mount.
 */
describe('UX-CASE §4a · the guard FAILS on the defect it was written for', () => {
  it('the retired literals, rendered in the status slot, are caught', () => {
    // The exact markup of `FieldRow.tsx:68` before the fix — reconstructed here
    // so the control survives the component being refactored.
    const { container } = render(
      <div className="field-value-row">
        <span className="field-value awaiting">honestly missing</span>
        <span className="chip chip-missing">
          <span>Missing</span>
        </span>
      </div>,
    );
    const failures = sweepLabelSlots(container, 'NEGATIVE CONTROL a');
    expect(
      failures.length,
      'the render half did not catch a lowercase status announcement in the slot the ' +
        'measured defect used — §2 is decorative',
    ).toBe(1);
    expect(failures[0].name).toBe('honestly missing');
    expect(failures[0].why.join(' ')).toMatch(/not capitalised/);
  });

  it('the sibling literal is caught too', () => {
    const { container } = render(
      <span className="field-value awaiting">awaiting your confirmation</span>,
    );
    expect(sweepLabelSlots(container, 'NEGATIVE CONTROL a2')).toHaveLength(1);
  });

  it('the source ratchet catches the same defect as a LITERAL, not only as a render', () => {
    // Verbatim `FieldRow.tsx:68`, as source. This is the half that works on a
    // screen no fixture renders.
    const reverted = [
      '<span className="field-value awaiting">',
      "  {needsYou ? 'awaiting your confirmation' : 'honestly missing'}",
      '</span>',
    ].join('\n');
    const hits = hardcodedLabelSlots(reverted);
    expect(hits.length, 'the §3 ratchet cannot see the shape the defect actually had').toBe(1);
    expect(hits[0]).toMatch(/awaiting your confirmation|honestly missing/);
  });

  it('and it is not fooled by the correction comment that QUOTES those literals', () => {
    // `components/FieldRow.tsx` now documents what it removed, quoting both
    // strings. A scan that did not strip comments would report the fix as the
    // defect — `CLAUDE.md` §11's CSS-phantom false-positive, exactly.
    const src = readFileSync(join(WEB_SRC, 'components/FieldRow.tsx'), 'utf8');
    expect(src, 'the correction note stopped quoting what it retired').toContain('honestly missing');
    expect(hardcodedLabelSlots(src)).toEqual([]);
  });
});

describe('UX-CASE §4b · the guard PASSES the spec-approved prose', () => {
  /*
   * WITHOUT THIS CONTROL, a later "casing fix" chasing the word "honestly"
   * would strip a phrase `casing-and-copy.md:67` approves by name, and
   * `CLAUDE.md` §11 records an assessment calling that sentence the single best
   * thing in the product.
   */
  const APPROVED = "I don't know — leave honestly missing";

  it('LABELS.actionDontKnow still IS the approved sentence', () => {
    expect(LABELS.actionDontKnow).toBe(APPROVED);
  });

  it('rendered on a button, it passes every part of this guard', () => {
    const { container } = render(
      <button type="button" className="guided-dontknow">
        {LABELS.actionDontKnow}
      </button>,
    );
    expect(
      sweepLabelSlots(container, 'NEGATIVE CONTROL b'),
      'the approved Register 2 prose was flagged as a casing defect — a later "fix" ' +
        'would now delete it',
    ).toEqual([]);
  });

  it('and it is prose by the spec\'s own boundary, not by an exemption', () => {
    // The exemption in §1 exists because the REGISTRY half has no layout to judge
    // from. The RENDER half needs no exemption at all: the sentence is punctuated
    // and em-dashed, so `casing-and-copy.md:22` ("anything longer than a label")
    // classifies it without anyone listing it.
    expect(isProse(APPROVED)).toBe(true);
    expect(register1Violations(APPROVED).length).toBeGreaterThan(0);
  });

  it('the /complete screen still shows it, in the register the spec approves', async () => {
    const { findByRole } = renderAt(`/record/${ID}/complete`);
    const button = await findByRole('button', { name: APPROVED });
    expect(button).toBeInTheDocument();
  });
});
