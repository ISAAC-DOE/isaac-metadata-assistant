/*
 * R1b · ONE upload claim, three sites — and the ban on the absolute form.
 *
 * WHY THIS FILE EXISTS. Three surfaces describe the same boundary to a reader:
 *
 *   - `screens/GovernancePage.tsx`   → Governance & Safety → Policy
 *   - `screens/LoadMaterials.tsx`    → the approval-gated on-ramp's warning line
 *   - `lib/settingsContent.ts`       → Settings → Data & Privacy →
 *                                      `no-real-experiment-data`
 *
 * Nothing pinned them to each other, and they drifted. `settingsContent.ts` was
 * corrected to say that file UPLOAD is refused with nothing parsed, *while* the
 * CSV preview and the record validator do read what you paste or pick. The other
 * two kept the older, absolute sentence — "every file upload is refused
 * outright, whatever it contains, and no file is read, parsed, or inspected" —
 * which is FALSE of this build, and false on the very page that mounts the
 * validator one tab away (`GovernancePage.tsx`'s `validator` tab renders
 * `components/RecordValidator.tsx`, which calls `file.text()`).
 *
 * WHAT IT ASSERTS, and why in this order:
 *
 *  §1 the file-reading controls REALLY EXIST in this build. The ban in §3 is
 *     only justified while they do. If a later slice genuinely removes both
 *     readers, §1 fails first and tells the next reader to revisit §3 rather
 *     than leaving a stale prohibition standing on nothing.
 *  §2 all three sites make the SAME claim — the refusal, the two readers by
 *     name, in-memory-not-stored, outcome-not-content. Parity is the property
 *     that was missing; a site that states half of it is a site that will drift
 *     again.
 *  §3 no site states the absolute "no file is read/parsed/inspected".
 *  §4 the guard is proven on the exact string that shipped, so a pattern
 *     narrowed until it detects nothing fails here rather than going quiet.
 *
 * WHAT IT CANNOT CATCH, stated plainly. It is a parity ratchet over four claim
 * shapes, not a detector for "is this paragraph true". A novel phrasing that
 * implies the app never reads a file — "your files never leave your machine",
 * "nothing you pick is opened" — satisfies every pattern here. A human reviewer
 * remains the backstop for newly written data claims. It also reads
 * `apps/web/src` only: backend-served copy (`routes.py`'s refusal reason, the
 * OpenAPI descriptions the Endpoint Explorer renders) is invisible to it.
 */

import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect, afterEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { GovernancePage } from '../screens/GovernancePage';
import { LoadMaterials } from '../screens/LoadMaterials';
import { settingsConcepts } from '../lib/settingsContent';

afterEach(cleanup);

// --- locating and reading the real sources -----------------------------------

/** Deliberately NOT `import.meta.url`: under jsdom that is an http URL, not a
 *  file one. Duplicated from the sibling guards rather than exported, so no file
 *  can silently change another's scan. */
function locateSrcDir(): string {
  const candidates = [join(process.cwd(), 'src'), join(process.cwd(), 'apps', 'web', 'src')];
  const found = candidates.find((dir) => existsSync(join(dir, 'main.tsx')));
  if (found === undefined) throw new Error(`cannot locate apps/web/src from ${process.cwd()}`);
  return found;
}

const SRC_DIR = locateSrcDir();

/** Strip comments — so the prose EXPLAINING a retired claim is never counted as
 *  the claim — then collapse whitespace, because JSX wraps a sentence across
 *  lines and a clause matched in the DOM would otherwise go unmatched here. */
function renderedCopy(path: string): string {
  return readFileSync(join(SRC_DIR, path), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/(^|[^:'"`\\])\/\/[^\n]*/g, '$1')
    .replace(/\s+/g, ' ');
}

/** The raw source, comments included — for the §1 capability proof, which is
 *  about what the code DOES, not about what any copy says. */
function rawSource(path: string): string {
  return readFileSync(join(SRC_DIR, path), 'utf8');
}

const SETTINGS_FACTS = {
  dataRegime: 'synthetic-only',
  persistence: 'ephemeral',
  recordSchemaVersion: '1.05',
};

function noRealDataDetail(): string {
  const found = settingsConcepts(SETTINGS_FACTS).find((c) => c.id === 'no-real-experiment-data');
  if (!found) throw new Error('no such concept: no-real-experiment-data');
  return `${found.heading} ${found.summary} ${found.detail}`;
}

/**
 * The three sites, as the text a reader actually meets.
 *
 * The first two are RENDERED, not source-scanned. A source scan of
 * `GovernancePage.tsx` matches `/validator/i` on its `import { RecordValidator }`
 * line, so the "names the validator" assertion would pass without a word of copy
 * saying so — a vacuous guard is worse than none. Rendering also proves the copy
 * is on the surface the reader is looking at rather than merely present in the
 * module.
 */
function policyTabText(): string {
  render(
    <MemoryRouter
      initialEntries={['/governance']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <GovernancePage />
    </MemoryRouter>,
  );
  return screen.getByRole('tabpanel').textContent ?? '';
}

function loadMaterialsWarnText(): string {
  const { container } = render(
    <MemoryRouter
      initialEntries={['/load']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <LoadMaterials />
    </MemoryRouter>,
  );
  const warn = container.querySelector('.onramp-warn');
  if (warn === null) throw new Error('the on-ramp governance warning is not rendered');
  return warn.textContent ?? '';
}

const SITES: [string, () => string][] = [
  ['Governance → Policy', policyTabText],
  ['the Load Materials on-ramp warning', loadMaterialsWarnText],
  ['Settings → Data & Privacy → no-real-experiment-data', noRealDataDetail],
];

// --- §1 the readers this ban is justified by ---------------------------------

/**
 * The two controls that DO read a user-chosen file. Each is proven by the read
 * call itself, not by a comment about it — `Blob.text()` with a `FileReader`
 * fallback, reached from an `<input type="file">` change handler.
 */
const FILE_READING_CONTROLS: [string, string][] = [
  ['the standalone record validator', 'components/RecordValidator.tsx'],
  ['the campaign-sheet reconciliation preview', 'components/CsvReconcilePanel.tsx'],
];

describe('R1b §1 · the file-reading controls exist, so the absolute claim is false', () => {
  it.each(FILE_READING_CONTROLS)('%s reads the chosen file', (_what, path) => {
    const src = rawSource(path);
    // The read itself.
    expect(src).toMatch(/file\.text\(\)/);
    expect(src).toMatch(/new FileReader\(\)/);
    // ...reached from a real file picker, so a user can actually get there.
    expect(src).toMatch(/type="file"/);
  });

  it('the Governance page mounts one of them one tab away from its own policy copy', () => {
    const src = rawSource('screens/GovernancePage.tsx');
    expect(src).toMatch(/<RecordValidator\s*\/>/);
  });
});

// --- §2 the shared claim -----------------------------------------------------

/**
 * The four parts of the one claim. Every site must state ALL of them: a site
 * that states the refusal without the readers is the exact half-truth this file
 * exists to stop, and a site that names the readers without the in-memory bound
 * over-discloses in the other direction (it sounds like the file is kept).
 *
 * The patterns are deliberately tolerant of wording — the sites read differently
 * because their contexts differ, and forcing three identical paragraphs would be
 * worse copy for no extra truth. What is pinned is the CLAIM, not the sentence.
 */
const SHARED_CLAIM: [string, RegExp][] = [
  ['file upload is refused outright', /file upload is refused outright/i],
  ['the record validator is named as a reader', /validator/i],
  ['the CSV/campaign-sheet preview is named as a reader', /(csv|campaign sheet)/i],
  [
    'what those two do read is read in memory and not stored',
    /in memory[^.]{0,80}(never stored|discard)|(never stored|discard)[^.]{0,80}in memory/i,
  ],
  [
    'only the outcome is recorded, never the content',
    /(only|just)[^.]{0,40}outcome[^.]{0,60}never[^.]{0,20}content/i,
  ],
];

describe('R1b §2 · all three sites state the same claim', () => {
  for (const [site, text] of SITES) {
    describe(site, () => {
      it.each(SHARED_CLAIM)('states %s', (_what, pattern) => {
        expect(text()).toMatch(pattern);
      });
    });
  }
});

// --- §3 the absolute form is banned -----------------------------------------

/**
 * The shapes that assert nothing anywhere reads a file. Each is an ABSOLUTE:
 * scoped forms — "the refused upload is never read", "no file is parsed at all"
 * as a clause on the upload refusal — are the correct wording and must pass.
 *
 * `parsed at all` is excluded from the first pattern on purpose:
 * `settingsContent.ts` says "file upload is refused outright, with no file
 * parsed at all", where the subject is unambiguously the refused upload. The
 * pattern targets the unrestricted claim about reading, which is the one that
 * shipped false.
 */
const ABSOLUTE_NO_READ: [string, RegExp][] = [
  ['no file is read/inspected anywhere', /\bno file is (ever )?(read|inspected)\b/i],
  ['no file is read, parsed, or inspected', /\bno file is read, parsed,? (or|and) inspected\b/i],
  ['nothing is read, parsed, or inspected', /\bnothing is (ever )?read, parsed,? (or|and) inspected\b/i],
  ['no file you choose is ever opened or read', /\bno file (you|a user) (choose|chooses|picks?) is (ever )?(opened|read)\b/i],
];

describe('R1b §3 · no site claims the absolute "no file is read"', () => {
  for (const [site, text] of SITES) {
    it.each(ABSOLUTE_NO_READ)(`${site} never claims %s`, (_what, pattern) => {
      expect(text()).not.toMatch(pattern);
    });
  }
});

// --- §4 the guard is proven on the string that shipped ----------------------

/** `screens/GovernancePage.tsx` and `screens/LoadMaterials.tsx` at `b595a50` —
 *  the same absolute sentence in both, word for word in its load-bearing half. */
const RETIRED_GOVERNANCE_ABSOLUTE =
  'Nothing is uploaded to a model or index without that approval: every file upload is ' +
  'refused outright, whatever it contains, and no file is read, parsed, or inspected.';

const RETIRED_LOAD_MATERIALS_ABSOLUTE =
  'Every file upload is refused outright, whatever it contains — no file is read, parsed, ' +
  'or inspected. Keeping real or private artifacts out is the operator’s responsibility, ' +
  'not a check this software performs.';

function absoluteClaims(text: string): string[] {
  return ABSOLUTE_NO_READ.filter(([, pattern]) => pattern.test(text)).map(([label]) => label);
}

function missingClaims(text: string): string[] {
  return SHARED_CLAIM.filter(([, pattern]) => !pattern.test(text)).map(([label]) => label);
}

describe('R1b §4 · the guard rejects the exact strings that shipped', () => {
  it.each([
    ['the Governance → Policy sentence', RETIRED_GOVERNANCE_ABSOLUTE],
    ['the Load Materials warning', RETIRED_LOAD_MATERIALS_ABSOLUTE],
  ])('flags %s as an absolute no-read claim', (_what, retired) => {
    expect(absoluteClaims(retired).length).toBeGreaterThan(0);
  });

  it.each([
    ['the Governance → Policy sentence', RETIRED_GOVERNANCE_ABSOLUTE],
    ['the Load Materials warning', RETIRED_LOAD_MATERIALS_ABSOLUTE],
  ])('flags %s as missing most of the shared claim', (_what, retired) => {
    // Both retired strings state the refusal and nothing else about the readers.
    expect(missingClaims(retired)).toContain('the record validator is named as a reader');
    expect(missingClaims(retired)).toContain(
      'what those two do read is read in memory and not stored',
    );
  });

  it('leaves the correctly scoped wording alone', () => {
    for (const scoped of [
      // `settingsContent.ts`'s corrected formulation, which is the model.
      'file upload is refused outright, with no file parsed at all, while the CSV preview and ' +
        'the record validator do read what you paste or pick — in memory, never stored, and ' +
        'logged only as an outcome, never as content.',
      // A refusal scoped to the upload path, which is true and must stay sayable.
      'every file upload is refused outright, whatever it contains, and the refused upload is ' +
        'never read, parsed, or inspected.',
    ]) {
      expect(absoluteClaims(scoped), scoped).toEqual([]);
    }
  });
});
