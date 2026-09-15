/*
 * R1b · ONE upload claim, four sites — and the ban on the absolute form.
 *
 * WHY THIS FILE EXISTS. Four surfaces describe the same boundary to a reader:
 *
 *   - `screens/GovernancePage.tsx`   → Governance & Safety → Policy
 *   - `screens/LoadMaterials.tsx`    → the approval-gated on-ramp's warning line
 *   - `lib/settingsContent.ts`       → Settings → Data & Privacy →
 *                                      `no-real-experiment-data`
 *   - `lib/mcpConnectContent.ts`     → Settings → Connect Your Agent, the
 *                                      `no-upload` row of the refused-capability
 *                                      list
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
 * THE FOURTH ARRIVED LATE, AND IT ARRIVED FALSE. It shipped reading "File
 * ingestion is refused for this whole deployment, agent or not" — the same
 * deployment-wide claim the other three had already been corrected for — and it
 * passed this guard untouched, because it was not in `SITES` and because §3
 * bans the shapes that shipped ("no file is read/parsed/inspected") rather than
 * the claim, and "ingestion" is not one of them. A claim that escapes a ratchet
 * by synonym is not held by it. Adding the site is the fix; the wording change
 * alone would have left the next one free to drift the same way.
 *
 * WHAT IT ASSERTS, and why in this order:
 *
 *  §1 the file-reading controls REALLY EXIST in this build. The ban in §3 is
 *     only justified while they do. If a later slice genuinely removes both
 *     readers, §1 fails first and tells the next reader to revisit §3 rather
 *     than leaving a stale prohibition standing on nothing.
 *  §2 all four sites make the SAME claim — the refusal, the two readers by
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
 *
 * A SIXTH SITE, ADDED FOR I-2, AND ALSO DELIBERATELY KEPT OUT OF §§2–4.
 * `components/HelpPanel.tsx`'s "Where values come from" section shipped
 * *"file upload is refused, and the campaign-sheet CSV comparison is read-only
 * with no route that applies what it found"* — which NAMED ONE READER AND
 * OMITTED THE OTHER, while the panel's own correction comment claimed it "names
 * no file READER". That is the half-disclosure this whole file exists to stop,
 * arriving in the fix for a different false claim, with a comment vouching for
 * the property the copy did not have. And "file upload is refused" was
 * UNSCOPED, on a build whose Governance page mounts a button labelled "Upload
 * JSON File" one tab away (`components/RecordValidator.tsx:241`).
 *
 * IT IS NOT FORCED INTO `SITES`/`SHARED_CLAIM`, for the same reason the fifth
 * site is not: §2 additionally requires the two RETENTION bounds (in memory,
 * never stored; only the outcome, never the content), and those answer a
 * data-governance question that a section titled "Where values come from" does
 * not raise. Adding them would put ~25 more words on the surface the Impeccable
 * critique measured at 89% over length (`UX-021`). §6 pins the narrower, real
 * invariant instead: that section must name BOTH readers, and must not state the
 * refusal as anything other than a property of the upload ROUTE.
 *
 * A SEVENTH SITE, ADDED FOR THE DO-NOT-MERGE REVIEW, AND ALSO DELIBERATELY KEPT
 * OUT OF §§2–4. `lib/settingsContent.ts`'s `synthetic-data-only` concept — the
 * Settings → Data & Privacy card rendered by `screens/settings/SettingsPage.tsx`
 * — stated the refusal UNSCOPED in BOTH its `summary` and its `detail`:
 *
 *   summary  "Synthetic-only mode — file upload is refused outright, and the app
 *             cannot tell real data from synthetic."
 *   detail   "This deployment runs in synthetic-only mode: file upload is refused
 *             outright, and the records in this workspace are synthetic. …"
 *
 * That is the SAME claim class as the six above, on the SAME tab as its already-
 * pinned sibling `no-real-experiment-data`, which scopes correctly — so the
 * design intent existed and this one card missed it. It was invisible to this
 * file: `rg -acn "synthetic-data-only"` returned 0 here before §7.
 *
 * WHY IT IS NOT A FIFTH MEMBER OF `SITES`, and this is a correction to the
 * review's own prescription rather than a preference. §2 requires every `SITES`
 * member to name BOTH readers and to state the two RETENTION bounds. This card
 * is deliberately forbidden from restating them: `settingsContent.ts:280-289`
 * documents the de-duplication decision, and `db-recon-truthfulness.test.tsx`
 * §12 ("makes the capability statement on exactly one card", "states the full
 * capability paragraph exactly once across the tab") MECHANICALLY FAILS if it
 * does. Adding it to `SITES` would therefore force a copy change that another
 * committed guard forbids — a guard that mandates the defect, which is exactly
 * what that file's own :736-738 warns about. §7 pins the narrower, real
 * invariant instead, using the three bans that need no reader vocabulary.
 *
 * A FIFTH SITE, ADDED LATER, AND DELIBERATELY KEPT OUT OF §§2–4. Found by
 * review: `lib/transcriptCaptureContent.ts`'s `voiceAudioHandling` claimed
 * "This application declares no upload endpoint for it to reach" — false;
 * `POST /api/uploads` IS declared (`apps/api/isaac_api/routes.py`). That is a
 * DIFFERENT false-claim shape from the four above — an existence claim about
 * the upload ROUTE, not a reading claim about the validator or the CSV
 * preview — and the sentence is not about either reader at all, so forcing it
 * into `SITES`/`SHARED_CLAIM` would fail on correct copy rather than catch
 * anything. §5 below pins the narrower, real invariant it needs: no site may
 * claim the upload route does not exist; the true and stronger claim is that
 * the one route that exists refuses every request it gets.
 *
 * AN EIGHTH SITE, AND THE ONLY ONE THAT WAS IN NO LIST AT ALL.
 * `screens/settings/ConnectAnAgent.tsx`'s "Respect Read and Write Boundaries"
 * row — Settings → API Access → Connect an Agent — ended "and file upload is
 * refused outright", the refusal predicated of the APPLICATION.
 *
 * WHAT MAKES IT DIFFERENT FROM THE FIFTH, SIXTH AND SEVENTH, all of which were
 * "held by the vocabulary-free bans but kept out of §2": this one was held by
 * NOTHING. The guard that looks like it covers it — `SITES`' fourth member,
 * `mcpNoUploadRow` — reads `lib/mcpConnectContent.ts`, a DIFFERENT module for a
 * DIFFERENT surface whose name differs by one word ("Connect YOUR Agent", the
 * MCP tab, versus "Connect AN Agent", the HTTP guide). Two near-identical names
 * over two modules is how a whole surface stayed outside every list while
 * looking covered, and it is why this claim class has now been miscounted three
 * times on one branch — reported as two sites, then six, then seven.
 *
 * IT IS NOT FORCED INTO `SITES`/`SHARED_CLAIM`, for the seventh site's reason
 * and one of its own. §2 requires both readers and both retention bounds; this
 * is a table row in an operational contract, `UX-021` measured this product's
 * Settings/Help surfaces at 89% over length, and an external agent cannot reach
 * either reader (no agent tool does), so enumerating them here would add ~25
 * words this audience cannot act on. §8 pins the narrower, real invariant — the
 * refusal is scoped to the upload ROUTE — and the row IS a member of
 * `ALL_BAN_SURFACES`, so §3, §3b, §4b and §5 hold it unchanged.
 */

import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

import { describe, it, expect, afterEach } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { HelpPanel } from '../components/HelpPanel';
import { GovernancePage } from '../screens/GovernancePage';
import { LoadMaterials } from '../screens/LoadMaterials';
import { ConnectAnAgent, type ConnectAnAgentFacts } from '../screens/settings/ConnectAnAgent';
import { ConnectYourAgentPanel } from '../screens/settings/ConnectYourAgent';
import { settingsConcepts } from '../lib/settingsContent';
import { MCP_CAPABILITIES_REFUSED } from '../lib/mcpConnectContent';
import { CAPTURE_COPY } from '../lib/transcriptCaptureContent';
import { IMPORT_COPY } from '../lib/historicalImportContent';

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

/*
 * A comment-stripping source reader was here. It is deliberately GONE: the two
 * page-level sites are checked by RENDERING them (see `policyTabText` below), not
 * by scanning their source, because a source scan of `GovernancePage.tsx` matches
 * `/validator/i` on its `import { RecordValidator }` line and would pass without a
 * word of copy saying so. Rendering is the stronger check, so the reader it
 * replaced is removed rather than left dangling for a future edit to reach for.
 */

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
 * The Settings → Data & Privacy synthetic-only MODE card, heading + summary +
 * detail. Read off the content module exactly as `noRealDataDetail` is, and for
 * the same reason: the claim is authored there, and `settings-page.test.tsx`
 * already proves every concept `detail` is rendered on the tab under its own
 * heading, so re-mounting the page here would duplicate that proof rather than
 * add one. BOTH `summary` and `detail` are read, because both shipped the
 * unscoped claim and a guard over one of them would have missed the other.
 */
function syntheticModeCard(): string {
  const found = settingsConcepts(SETTINGS_FACTS).find((c) => c.id === 'synthetic-data-only');
  if (!found) throw new Error('no such concept: synthetic-data-only');
  return `${found.heading} ${found.summary} ${found.detail}`;
}

/**
 * The four sites, as the text a reader actually meets.
 *
 * The first two are RENDERED, not source-scanned. A source scan of
 * `GovernancePage.tsx` matches `/validator/i` on its `import { RecordValidator }`
 * line, so the "names the validator" assertion would pass without a word of copy
 * saying so — a vacuous guard is worse than none. Rendering also proves the copy
 * is on the surface the reader is looking at rather than merely present in the
 * module.
 */
/* UX-021 — `MemoryRouter` IS REQUIRED here. `HelpPanel` renders a real `<Link>` to
 * Settings -> Help & Tutorial, and `Link` reads router context, so a bare render throws
 * `Cannot destructure property 'basename' of useContext(...) as it is null` and takes every
 * test in the file down with it. Wrapping is the right fix rather than downgrading the
 * `<Link>`: in production this panel is mounted inside `TopBar`, inside the router, so the
 * HARNESS was what did not match reality. */
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

/**
 * The Connect Your Agent tab's refused-capability row, as the reader meets it.
 *
 * Read off the content module the way `noRealDataDetail` is — the claim is
 * authored there and the row is the unit that makes it, so scanning the whole
 * panel would let a neighbouring paragraph supply half the claim and count as
 * parity. A site has to state the whole thing WHERE IT STATES THE REFUSAL, or a
 * reader of the capability table gets the half-truth on its own.
 *
 * It still RENDERS the panel and asserts the row is on the surface, because the
 * failure mode a constant-read misses is copy that exists in the module and is
 * not shown. `getByText` throws when it is not found, so the render is a real
 * assertion rather than a decoration.
 */
function mcpNoUploadRow(): string {
  const row = MCP_CAPABILITIES_REFUSED.find((c) => c.id === 'no-upload');
  if (!row) throw new Error('no such refused capability: no-upload');
  render(<ConnectYourAgentPanel onOpenExplorer={() => {}} />);
  screen.getByText(row.detail);
  return `${row.action} ${row.detail}`;
}

/**
 * Facts for the Connect an Agent guide. They feed only "Send Structured
 * Requests" and "Handle Errors", neither of which this file bans anything in,
 * so they are HARNESS INPUT and not an assertion about the contract — do not
 * read them as a claim that these are the media types or statuses the real
 * document declares (`settings-page.test.tsx` derives those from it).
 */
const CONNECT_GUIDE_FACTS: ConnectAnAgentFacts = {
  requestMediaTypes: ['application/json'],
  errorCodes: ['401', '422'],
};

/**
 * The EIGHTH site: Settings → API Access → Connect an Agent, whose "Respect
 * Read and Write Boundaries" row stated the upload refusal UNSCOPED.
 *
 * RENDERED, not source-scanned, and the whole guide rather than the one row.
 * Rendering is this file's stated preference (see `policyTabText`) because it
 * proves the copy is on the surface a reader meets. The whole guide because the
 * row is one of eight authored in the same array literal: a sibling row is the
 * cheapest place for this claim class to reappear, and a scan of one row would
 * not see it. The eight `body` strings are the component's own local constant,
 * so there is no module to read them off the way `mcpNoUploadRow` does.
 */
function connectAnAgentGuideEl(): Element {
  const { container } = render(
    <ConnectAnAgent
      facts={CONNECT_GUIDE_FACTS}
      open
      onOpenChange={() => {}}
      summaryId="upload-claim-parity-connect-summary"
      onOpenExplorer={() => {}}
    />,
  );
  const guide = container.querySelector('details.api-connect');
  if (guide === null) throw new Error('the Connect an Agent guide is not rendered');
  // The row that makes the claim, asserted to be ON the surface rather than
  // merely present in the module — the failure mode a constant-read misses.
  // `getByRole` throws when absent, so this is a real assertion.
  screen.getByRole('heading', { name: 'Respect Read and Write Boundaries', level: 4 });
  return guide;
}

function connectAnAgentGuide(): string {
  return connectAnAgentGuideEl().textContent ?? '';
}

const SITES: [string, () => string][] = [
  ['Governance → Policy', policyTabText],
  ['the Load Materials on-ramp warning', loadMaterialsWarnText],
  ['Settings → Data & Privacy → no-real-experiment-data', noRealDataDetail],
  ['Settings → Connect Your Agent → the no-upload capability row', mcpNoUploadRow],
];

/**
 * Every surface any VOCABULARY-FREE ban in this file runs over: the four
 * `SITES` plus the two that are deliberately not `SITES` members (§5's capture
 * disclosure, §7's Settings mode card). §2's `SHARED_CLAIM` deliberately does
 * NOT use this list — it requires reader vocabulary those two have no business
 * carrying, which is the whole reason they are separate.
 *
 * ONE list rather than a per-section literal, because the measured failure mode
 * in this file is a ban that was widened at one call site and not at another:
 * §5 shipped as `ALL_FIVE` while §3 and §3b still looped over `SITES`, so the
 * capture disclosure was outside two bans that would have held it.
 */
/**
 * EVERY authored string the Historical Import surface renders, joined as ONE
 * ban surface. **The EIGHTH site, added 2026-09-13 with the destination itself.**
 *
 * WHY IT IS HERE AT ALL. That surface exists to say what this build does and does
 * not do with files a scientist points at — which is exactly the claim class this
 * file was written for, and exactly the class that has shipped false four times.
 * Adding the site with the feature, rather than after a review catches it, is the
 * lesson §26's fourth site taught: it "arrived late, and it arrived false",
 * passing this guard untouched because nobody had widened the list.
 *
 * WHY IT IS NOT A MEMBER OF `SITES`, for the reason the fifth, sixth and seventh
 * are not. §2's `SHARED_CLAIM` requires READER VOCABULARY — the validator, the
 * campaign-sheet preview, the in-memory bound — and this surface has no business
 * carrying any of it: it is not about those two controls, it is about an import
 * source. Forcing it into `SITES` would fail on correct copy, which is the
 * failure direction a ratchet may not have.
 *
 * WHAT IT DOES JOIN is every VOCABULARY-FREE ban: §3 (no absolute "no file is
 * read"), §3b (no reader-noun denial), §5 (no "the route does not exist") and §7.
 * The strings are read from the module rather than rendered, which is why the
 * module exists.
 */
function historicalImportCopy(): string {
  return Object.values(IMPORT_COPY)
    .filter((value): value is string => typeof value === 'string')
    .join(' ');
}

const ALL_BAN_SURFACES: [string, () => string][] = [
  ...SITES,
  ['transcript capture: voiceAudioHandling', captureVoiceAudioHandling],
  ['Settings → Data & Privacy → synthetic-data-only', syntheticModeCard],
  ['Settings → API Access → Connect an Agent (the guide)', connectAnAgentGuide],
  ['Historical Import: every authored string', historicalImportCopy],
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

  /*
   * EXHAUSTIVENESS, which the pair above does not establish.
   *
   * `components/HelpPanel.tsx` tells the reader that EXACTLY TWO components
   * accept a file, and that claim was backed only by a command written into a
   * comment — a command the commit that wrote it INVALIDATED, because the
   * comment quoting `type="file"` became one of its own hits (5 files at
   * `97c44c84`, 7 at HEAD). A count in prose goes stale silently; this does not.
   *
   * COMMENTS ARE STRIPPED FIRST, which is the whole reason this can be exact
   * where the `rg` command could not: prose ABOUT the attribute cannot join the
   * set, so no file needs excluding by name. The strip is deliberately crude
   * (line comments and block comments), and that is safe in this direction — it
   * can only ever REMOVE candidates, so a stripper that missed a comment would
   * make this test FAIL rather than pass, which is the failure direction a
   * guard is allowed to have.
   */
  it('EXACTLY these two non-test files declare a file input — no third control', () => {
    const ATTRIBUTE = 'type="file"';
    function walk(dir: string): string[] {
      const out: string[] = [];
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = join(dir, entry.name);
        if (entry.isDirectory()) {
          if (entry.name !== '__tests__' && entry.name !== 'test') out.push(...walk(full));
        } else if (/\.tsx?$/.test(entry.name) && !entry.name.endsWith('.d.ts')) {
          out.push(full);
        }
      }
      return out;
    }
    const stripComments = (src: string) =>
      src.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/^\s*\/\/.*$/gm, ' ');

    const declaring = walk(SRC_DIR)
      .filter((full) => stripComments(readFileSync(full, 'utf8')).includes(ATTRIBUTE))
      .map((full) => relative(SRC_DIR, full).split(sep).join('/'))
      .sort();

    expect(
      declaring,
      'the set of components that accept a user-chosen file has changed. ' +
        'components/HelpPanel.tsx tells the reader there are exactly two and names ' +
        'them, and __tests__/help-claim-parity.test.tsx requires that section to name ' +
        'BOTH readers — so a third control means that copy is now a half-disclosure, ' +
        'and a removed one means the §3 ban rests on nothing (see §1 above).',
    ).toEqual(['components/CsvReconcilePanel.tsx', 'components/RecordValidator.tsx']);

    // The two names the copy uses are exactly the two paths asserted above, so
    // the prose and the count cannot drift apart.
    expect(FILE_READING_CONTROLS.map(([, path]) => path).sort()).toEqual(declaring);
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
 * because their contexts differ, and forcing four identical paragraphs would be
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

describe('R1b §2 · all four sites state the same claim', () => {
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

/*
 * §3b — POLARITY. Found by negative control while integrating this slice, and the
 * finding is recorded because the guard as first written did not survive it.
 *
 * The control inverted the disclosure to `No review tool reads a file you paste or
 * pick` and ALL 35 assertions still passed. §2 only requires each site to MENTION
 * the validator, the CSV preview, the in-memory bound and the outcome-only bound —
 * a negation keeps every one of those words. §3 bans four specific sentences that
 * shipped, and the inverted sentence is not one of them. So the four topics were
 * pinned and the CLAIM'S DIRECTION was not: the guard could not tell "these two do
 * read" from "these two do not read", which is the entire difference between the
 * true wording and the false one.
 *
 * Two additions, because either alone is defeatable:
 *
 * The fix is ONE tight pattern plus a regression fixture, and the two rejected
 * alternatives are worth recording because both are tempting and both are wrong:
 *
 *   A greedy `[^.]{0,60}` window between the negator and the reader noun produces
 *   FALSE POSITIVES on the correct copy. `settingsContent` reads "…with no file
 *   parsed at all, while the CSV preview and the record validator do read what you
 *   paste or pick" — the `no` attaches to the refused UPLOAD, and a window that
 *   crosses the comma reads it as attaching to the readers. So the window is
 *   `[^.,]` — a negator only counts when it governs the same clause.
 *
 *   Requiring an AFFIRMATIVE reader sentence (name a reader, say it reads, contain
 *   no negator) was tried and abandoned. Correct copy pairs the two polarities in
 *   one sentence on purpose — "Two review tools DO READ a file you paste or pick,
 *   and NEITHER adds it to the workspace" — so the negator test excluded the very
 *   sentence it was meant to find, failing all three sites. Detecting polarity in
 *   English needs a parser, and a guard that misfires on true copy is worse than
 *   the gap it closes: it trains the next reader to weaken it.
 *
 * So the structural half is a FIXTURE, not a parser: §4b pins the exact inverted
 * sentence the control used and asserts the pattern rejects it. Deterministic, and
 * it cannot rot into vacuity the way a topic-mention check did.
 */
const NEGATED_READER: [string, RegExp][] = [
  [
    'a negator governing the reader nouns in the same clause',
    /\b(no|neither|none of|not one)\b[^.,]{0,30}\b(review tool|validator|preview|reconciliation)\b[^.,]{0,30}\b(read|reads|parse|parses|inspect|inspects|open|opens)\b/i,
  ],
  [
    'a reader noun denied in the same clause',
    /\b(review tool|validator|csv preview|campaign sheet)\b[^.,]{0,30}\b(never|does not|do not|doesn't|don't|cannot|can't)\b[^.,]{0,20}\b(read|reads|parse|parses|inspect|inspects|open|opens)\b/i,
  ],
];

/** The exact sentence the integration negative control substituted, which the
 *  first version of this guard passed. Kept verbatim as a fixture. */
const INVERTED_DISCLOSURE =
  'No review tool reads a file you paste or pick, and neither adds it to the workspace: ' +
  'the Validator on the next tab, and campaign-sheet CSV reconciliation on a record’s ' +
  'evidence trail. Each checks the text in memory and discards it, and records only the ' +
  'outcome — never the content.';

describe('R1b §3 · no site claims the absolute "no file is read"', () => {
  // `ALL_BAN_SURFACES`, not `SITES`: this ban needs no reader vocabulary, so the
  // capture disclosure and the Settings mode card were outside it for no reason
  // other than that nobody widened the loop when they were added.
  for (const [site, text] of ALL_BAN_SURFACES) {
    it.each(ABSOLUTE_NO_READ)(`${site} never claims %s`, (_what, pattern) => {
      expect(text()).not.toMatch(pattern);
    });
  }
});

describe('R1b §3b · no site denies that the two review tools read', () => {
  for (const [site, text] of ALL_BAN_SURFACES) {
    it.each(NEGATED_READER)(`${site} never states %s`, (_what, pattern) => {
      expect(text()).not.toMatch(pattern);
    });
  }
});

describe('R1b §4b · the polarity pattern is proven on the string that defeated §2', () => {
  it('rejects the inverted disclosure', () => {
    const caught = NEGATED_READER.filter(([, p]) => p.test(INVERTED_DISCLOSURE)).map(
      ([label]) => label
    );
    expect(
      caught,
      'the inverted disclosure ("No review tool reads…") is not caught. This exact ' +
        'sentence passed all 35 assertions of the first version of this guard, because ' +
        '§2 checks only that the validator and the CSV preview are MENTIONED and a ' +
        'negation mentions them just as well. If this assertion fails, the guard has ' +
        'regressed to pinning topics instead of the claim.'
    ).not.toHaveLength(0);
  });

  // One test PER SITE, not one loop over all of them. `policyTabText` renders, and
  // `cleanup` runs between tests rather than between calls — looping renders the
  // second site on top of the first, and the by-role query then matches two
  // tabpanels. That is a harness artefact, not a copy defect, and it is easy to
  // misread as one.
  for (const [site, text] of ALL_BAN_SURFACES) {
    it(`does NOT fire on the correct copy of ${site}`, () => {
      // Hoisted: `text()` RENDERS, and `.filter` would call it once per pattern —
      // two renders in one test, which the by-role query reports as an ambiguous
      // match rather than as the copy defect it is not.
      const rendered = text();
      const fired = NEGATED_READER.filter(([, p]) => p.test(rendered)).map(([label]) => label);
      expect(
        fired,
        `${site} is correct copy and must not trip the polarity pattern. A false ` +
          `positive here is worse than the gap it closes: it teaches the next reader ` +
          `to weaken the guard rather than fix the copy.`
      ).toEqual([]);
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

// --- §5 no site anywhere claims the upload ROUTE does not exist -------------
//
// `lib/transcriptCaptureContent.ts`'s `voiceAudioHandling` is about audio, not
// about the validator or the CSV preview, so it does not belong in `SITES`/
// `SHARED_CLAIM` above (§2 requires naming both readers, which an
// audio-privacy sentence has no business doing) — see the file header. The
// false shape it shipped was an EXISTENCE claim about the upload route
// ("declares no upload endpoint for it to reach"), not a reading claim, so it
// needs its own ban and its own polarity proof rather than reuse of §3/§3b,
// which are about a different sentence entirely.
//
// THE BAN ITSELF NEEDS NO READER VOCABULARY, so unlike the claim-parity check
// above it is not scoped to one site. It runs over all FIVE surfaces that
// discuss the upload path (the original four `SITES` plus the capture site),
// AND over every string value `CAPTURE_COPY` currently holds, so a future key
// making the same mistake is caught without anyone remembering to list it.
//
// PATTERN HISTORY: the first version of this ban shipped with two patterns
// that missed 7 of 8 plausible phrasings an independent review tried against
// it — including a one-word edit ("route" for "endpoint") of the very
// sentence it was written to catch. The widened set below was re-measured
// against the same eight phrasings; see the probe at the bottom of this
// section, which is a real test and fails if any of the eight goes uncaught.

/**
 * The shape of `CAPTURE_COPY`, MEASURED on 2026-09-12 by running the assertion
 * below with sentinel zeroes and reading the reported values: 79 keys, of which
 * 75 are strings the ban's loop reads and 4 are string-RETURNING FUNCTIONS it
 * skips. Pinned because that skip makes the sweep shrinkable without any test
 * failing — convert one key to a function and it silently leaves the ban.
 */
/*
 * 79 -> 92 (strings 75 -> 88), 2026-09-13: the intake chooser's thirteen keys.
 *
 * THE RATCHET DID ITS JOB AND THAT IS WHY THE NUMBER MOVED RATHER THAN THE LOOP.
 * The new keys are CLAIM-BEARING copy about what this build can and cannot do
 * with files and audio, which is precisely the class this sweep exists for — so
 * they belong INSIDE the ban, and the correct response to the failure was to
 * admit them and let the bans judge them, not to exempt them.
 */
/*
 * 92 -> 95 (strings 88 -> 91), 2026-09-14: the FOURTH intake route's three keys
 * (`intakeRunTitle`, `intakeRunBody`, `intakeRunAction`).
 *
 * THE RATCHET DID ITS JOB A SECOND TIME, in exactly the way the 2026-09-13 note
 * above describes, and the response is the same one: admit the keys and let the
 * bans judge them. `intakeRunBody` is claim-bearing — it says this route is the
 * one where the scientist enters a value directly rather than ISAAC proposing
 * one, and that nothing there needs confirmation afterwards. That is a statement
 * about what the build does, so it belongs INSIDE the ban, not exempted from it.
 * All three pass the bans as written; none asserts that any route or endpoint
 * does not exist.
 */
/*
 * 101/97/4, up from 95/91/4 on 2026-09-14: six keys for the MCP route drawer in
 * the voice section (`mcpRoute*`). The ratchet caught the change, which is what
 * it is for — a copy addition to this panel must be a decision, not a drift.
 */
const CAPTURE_COPY_KEY_COUNTS = { total: 101, strings: 97, functions: 4 };

function captureVoiceAudioHandling(): string {
  return CAPTURE_COPY.voiceAudioHandling;
}

/**
 * Four shapes of "the upload route does not exist / cannot receive
 * anything", covering declarative ("X declares no route"), existential
 * ("there is no route"), passive ("no route is declared"), and capability
 * ("nothing can receive an upload") phrasings. None of the four needs the
 * word "upload" to precede "endpoint/route/api" — `(upload\s+)?` is optional
 * throughout, and endpoint/route/api all take an optional plural `s?`.
 */
const ABSOLUTE_NO_ENDPOINT: [string, RegExp][] = [
  [
    'declares/has/exposes no (upload) endpoint/route/api',
    /\b(declares|declared|has|exposes|expose)\s+no\s+(upload\s+)?(endpoint|route|api)s?\b/i,
  ],
  [
    'there is/are no (upload) endpoint/route/api',
    /\bthere\s+(is|are)\s+no\s+(upload\s+)?(endpoint|route|api)s?\b/i,
  ],
  [
    'no (upload) endpoint/route/api is/are declared/exposed',
    /\bno\s+(upload\s+)?(endpoint|route|api)s?\s+(is|are)\s+(declared|exposed)\b/i,
  ],
  [
    'nothing/no-X can receive or accept an upload',
    /\b(nothing|no\s+\S+)\b[^.,]{0,40}\b(receive|receives|accept|accepts)\b[^.,]{0,30}\bupload\b/i,
  ],
];

/** The exact sentence that shipped, before this slice's first correction.
 *  Kept verbatim as the primary polarity fixture. */
const RETIRED_CAPTURE_ABSOLUTE =
  'Audio stays in this tab’s memory. It is never uploaded, never written to ' +
  'disk, and is discarded when you clear it, leave this record, or reload the ' +
  'page. This application declares no upload endpoint for it to reach.';

/**
 * Eight plausible future phrasings of the same false existence claim, used
 * by an independent review to show the first pattern set caught only one of
 * them. Re-measured here on every change to `ABSOLUTE_NO_ENDPOINT` — this is
 * the "re-run the probe yourself" requirement, not a one-time note.
 */
const PLAUSIBLE_NO_ENDPOINT_PHRASINGS = [
  'There is no endpoint here that accepts an upload.',
  'This application exposes no route that accepts a file.',
  'Nothing in this build can receive an upload.',
  'No upload API is declared.',
  'This application declares no endpoint for uploads.',
  'The application has no upload endpoints.',
  'There is no upload route for it to reach.',
  'This application declares no upload route.',
];

function noEndpointClaims(text: string): string[] {
  return ABSOLUTE_NO_ENDPOINT.filter(([, pattern]) => pattern.test(text)).map(([label]) => label);
}

describe('R1b §5 · no upload-claim site, and no CAPTURE_COPY string, claims the route does not exist', () => {
  it('flags the retired sentence as an absolute no-endpoint claim', () => {
    expect(
      noEndpointClaims(RETIRED_CAPTURE_ABSOLUTE),
      'the retired sentence ("This application declares no upload endpoint for ' +
        'it to reach") shipped false — POST /api/uploads is declared — and this ' +
        'assertion is the polarity proof: if it fails, the pattern set below has ' +
        'gone quiet and would not have caught the defect it was written for.',
    ).not.toHaveLength(0);
  });

  it('the eight-phrasing probe: every plausible future false phrasing is caught', () => {
    const missed = PLAUSIBLE_NO_ENDPOINT_PHRASINGS.filter((s) => noEndpointClaims(s).length === 0);
    expect(
      missed,
      'one or more plausible false phrasings of "the upload route does not ' +
        'exist" is not caught by ABSOLUTE_NO_ENDPOINT. Widen the pattern set — ' +
        'do not narrow this list to make the test pass.',
    ).toEqual([]);
  });

  it('the corrected capture copy does not trip any pattern', () => {
    expect(noEndpointClaims(captureVoiceAudioHandling()), captureVoiceAudioHandling()).toEqual([]);
  });

  // SIX, not five: the `synthetic-data-only` Settings card is a seventh
  // upload-claim site (see the file header) and this ban needs no reader
  // vocabulary, so it costs nothing to run over it and closes it by the same
  // mechanism. `ALL_BAN_SURFACES` is the one list every vocabulary-free ban in
  // this file runs over, so a future site added to it is covered by §3, §3b,
  // §5 and §7 at once rather than by whichever the author remembered.
  describe('applies to every upload-claim surface, not just the capture site', () => {
    for (const [site, text] of ALL_BAN_SURFACES) {
      it(`${site} does not claim the route does not exist`, () => {
        // Hoisted to ONE call: `text()` renders for three of the five sites,
        // and `cleanup` runs between TESTS, not between calls — a second call
        // in the same test (e.g. as a would-be assertion message) renders the
        // site twice with no cleanup in between, which trips `getByRole`/
        // `getByText`'s "multiple elements found" as a false failure. Same
        // harness artefact §4b already documents for `policyTabText`.
        const rendered = text();
        expect(noEndpointClaims(rendered), rendered).toEqual([]);
      });
    }
  });

  /*
   * THE COUNT IS PINNED, because the `continue` makes this sweep silently
   * shrinkable. Converting one key from a string to a string-returning function
   * — a refactor nobody would think of as a copy change — removes it from the
   * scan with no test failing, and the sweep keeps reporting `[]`. So the two
   * numbers are asserted: how many keys exist, and how many this loop actually
   * reads. If either moves, the diff has to say why.
   *
   * The FUNCTION count is asserted too, not just the string count: if it were
   * only the strings, adding a key AND converting one would net to zero.
   */
  it('the sweep reads a pinned number of CAPTURE_COPY keys, so it cannot shrink silently', () => {
    const entries = Object.entries(CAPTURE_COPY);
    const strings = entries.filter(([, v]) => typeof v === 'string');
    const functions = entries.filter(([, v]) => typeof v === 'function');
    expect(
      { total: entries.length, scanned: strings.length, notScanned: functions.length },
      'a CAPTURE_COPY key was added, removed, or changed between a string and a ' +
        'function. The loop below reads typeof === "string" values ONLY, so a ' +
        'conversion silently removes a key from the ban. Update these numbers in the ' +
        'same change, and if a converted key still makes a copy claim, give it its ' +
        'own assertion.',
    ).toEqual({ total: entries.length, scanned: strings.length, notScanned: functions.length });
    expect(entries.length).toBe(CAPTURE_COPY_KEY_COUNTS.total);
    expect(strings.length).toBe(CAPTURE_COPY_KEY_COUNTS.strings);
    expect(functions.length).toBe(CAPTURE_COPY_KEY_COUNTS.functions);
    // ...and every key is one or the other, so no third kind is going unscanned
    // and uncounted.
    expect(strings.length + functions.length).toBe(entries.length);
  });

  it('no string value anywhere in CAPTURE_COPY claims the route does not exist', () => {
    const offenders: string[] = [];
    for (const [key, value] of Object.entries(CAPTURE_COPY)) {
      if (typeof value !== 'string') continue; // functions (e.g. summaryStored) are excluded — see below
      if (noEndpointClaims(value).length > 0) offenders.push(key);
    }
    expect(
      offenders,
      'a CAPTURE_COPY string other than voiceAudioHandling now claims the ' +
        'upload route does not exist. Note: string-returning FUNCTIONS in ' +
        'CAPTURE_COPY (summaryStored, runTargetsRun, etc.) are not scanned by ' +
        'this loop, because it iterates typeof === "string" values only — a ' +
        'future key of that shape needs its own assertion.',
    ).toEqual([]);
  });
});

/**
 * §5b — the affirmative claim, pinned TOLERANTLY (per `SHARED_CLAIM`'s own
 * rule at :222, "What is pinned is the CLAIM, not the sentence"). The ban
 * above is satisfied by deleting the sentence outright, so an affirmative
 * pin is still needed to keep the reassurance from being silently dropped —
 * but a literal-phrase pin (`/upload route/i` + `/refuses every request/i`)
 * would fail a truthful reword like "its single upload endpoint declines all
 * requests", which the independent review used as its own example. Only the
 * capture site makes this specific two-part claim (no multipart form
 * anywhere; the one route refuses everything), so — unlike the ban above —
 * this is scoped to that one site rather than run over all five.
 */
const CAPTURE_AFFIRMATIVE_CLAIM: [string, RegExp][] = [
  [
    'no multipart form exists anywhere in this application',
    /\bno\s+multipart\s+form\b[^.,]{0,40}\b(anywhere|declared|exists)\b/i,
  ],
  [
    'the one upload route/endpoint refuses or declines every/all requests',
    /\bupload\s+(route|endpoint)\b[^.,]{0,60}\b(refuses|refused|reject(s)?|declin(es|ed)|den(ies|ied))\b[^.,]{0,30}\b(every|all|any)\b[^.,]{0,20}\brequests?\b/i,
  ],
];

describe('R1b §5b · the capture site states the affirmative claim, tolerant of wording', () => {
  it.each(CAPTURE_AFFIRMATIVE_CLAIM)('states %s', (_what, pattern) => {
    expect(captureVoiceAudioHandling()).toMatch(pattern);
  });

  it('a truthful reword still satisfies the tolerant pattern (regression fixture)', () => {
    const reword =
      'Audio stays in this tab’s memory. This application declares no multipart ' +
      'form anywhere, and its single upload endpoint declines all requests, so ' +
      'nothing in this capture path has anywhere to send it.';
    for (const [, pattern] of CAPTURE_AFFIRMATIVE_CLAIM) {
      expect(reword).toMatch(pattern);
    }
    // ...and the reword must still pass the ban above.
    expect(noEndpointClaims(reword)).toEqual([]);
  });
});

// --- §6 the Help popover's "Where values come from" section ------------------
//
// See the file header for why this is a SIXTH site with its own narrow ban
// rather than a fifth member of `SITES`. Two invariants, each polarity-proven on
// the exact sentence that shipped at `43544c6c`:
//
//   6a — the section names BOTH file-reading controls. Naming one is worse than
//        naming neither: the reader is told the exhaustive-sounding truth about
//        the control that changes nothing, and nothing at all about the control
//        with the word "Upload" on its face.
//   6b — every upload refusal in the section is predicated of the upload ROUTE
//        (or endpoint, or path), never of the application. `CLAUDE.md` §11
//        records the refusal claim as true of `POST /api/uploads` ONLY, and
//        records this claim class shipping false three times before, each time
//        repaired by SCOPING it rather than deleting it.
//
// SCOPED TO ONE SECTION, ON PURPOSE, and the boundary is worth stating because
// it was examined rather than assumed. The popover's "Synthetic workspace"
// section says "uploads are disabled", which §6b would flag — and it is
// DELIBERATELY out of scope. That sentence's subject is the WORKSPACE, it is
// qualified in the same breath ("this deployment is configured for
// synthetic-only operation ... What the app enforces is that mode, not the
// contents of what it is handed"), and the identical requirement is imposed on
// three surfaces at once by `__tests__/db-recon-truthfulness.test.tsx:427,593`
// — including two this slice did not own. Changing it on one surface would
// break the cross-surface parity that guard exists to hold. It is named here as
// examined-and-left, not overlooked.

/** Just the one section, located by its own heading — so a neighbouring
 *  section cannot supply half of the claim and count as compliance. Same
 *  technique `db-recon-truthfulness.test.tsx`'s `helpSyntheticSection` uses. */
function helpValuesSectionEl(): Element {
  const view = render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <HelpPanel />
    </MemoryRouter>,
  );
  fireEvent.click(view.getByRole('button', { name: 'Help' }));
  const section = [...view.container.querySelectorAll('.help-section')].find(
    (el) => el.querySelector('h3')?.textContent === 'Where values come from',
  );
  expect(section, 'no "Where values come from" section in the Help popover').toBeTruthy();
  return section!;
}

/** The same section flattened. §6a asks "is this named ANYWHERE in the section",
 *  which is a whole-section question and is correct over `textContent`. §6b asks
 *  a PER-SENTENCE question and is NOT — see `unscopedUploadRefusalsInBlocks`. */
function helpValuesSection(): string {
  return helpValuesSectionEl().textContent ?? '';
}

/** Both file-reading controls, as the claim must name them. */
const BOTH_READERS_NAMED: [string, RegExp][] = [
  ['the record validator', /validator/i],
  ['the campaign-sheet CSV comparison', /(csv|campaign[- ]sheet)/i],
];

/**
 * Every sentence that refuses an upload WITHOUT scoping the refusal to the
 * route. Empty is the pass.
 *
 * Sentence-split rather than clause-split: the scoping noun and the refusal verb
 * are the SAME predicate ("the upload route refuses every request"), so a
 * comma-level window would separate them and flag correct copy. `(?<=\.)\s+`
 * requires whitespace after the period, so a version number like `v1.05` cannot
 * split a sentence in two — the `[^.]`-as-sentence-proxy hazard `QA-010` records.
 */
function unscopedUploadRefusals(text: string): string[] {
  return text
    .split(/(?<=\.)\s+/)
    .map((t) => t.trim())
    .filter(
      (t) =>
        /\bupload/i.test(t) &&
        /\b(refus\w+|disabled|blocked|declin\w+|reject\w+)\b/i.test(t) &&
        !/\bupload\s+(route|endpoint|path)\b/i.test(t) &&
        !/POST\s+\/api\/uploads/i.test(t),
    );
}

/** `components/HelpPanel.tsx:221-227` at `43544c6c`, verbatim — the sentence
 *  that named one reader and left the refusal unscoped. */
const RETIRED_HELP_VALUES_SENTENCE =
  'A value gets into a record because a person put it there — typed into a record or run ' +
  'field, or given as an answer to one of the questions above. No control here reads one of ' +
  'your files and fills a field from it: file upload is refused, and the campaign-sheet CSV ' +
  'comparison is read-only with no route that applies what it found.';

describe('R1b §6a · the Help "Where values come from" section names BOTH readers', () => {
  it.each(BOTH_READERS_NAMED)('names %s', (_what, pattern) => {
    expect(helpValuesSection()).toMatch(pattern);
  });

  it('POLARITY: the sentence that shipped names only one of the two', () => {
    const named = BOTH_READERS_NAMED.filter(([, p]) => p.test(RETIRED_HELP_VALUES_SENTENCE)).map(
      ([label]) => label,
    );
    expect(
      named,
      'the retired sentence is expected to name exactly ONE reader (the CSV comparison). ' +
        'If it now reads as naming both, this fixture has been edited and the polarity ' +
        'proof is worthless.',
    ).toEqual(['the campaign-sheet CSV comparison']);
  });
});

/*
 * THE SAME BAN, RUN PER BLOCK ELEMENT — and this is a VACUITY FIX, not a
 * tightening. Measured by an independent review and reproduced here in §6c.
 *
 * `unscopedUploadRefusals` splits on `/(?<=\.)\s+/`, which requires WHITESPACE
 * after the period. JSX emits no text node between sibling elements, so
 * `section.textContent` glues the last sentence of one `<p>` to the first of the
 * next — "…apply nothing to a record.Dictating into Cap…" — and a whole new
 * paragraph is absorbed into the preceding chunk, INHERITING ITS EXEMPTION. The
 * shipped section's first `<p>` ends "The upload route refuses every request,
 * and only two controls read a file you pick…", so anything appended after it
 * carries that `\bupload\s+route\b` exemption for free.
 *
 * CONSEQUENCE, stated plainly because it is Task 1's failure mode one element
 * away: if this section grew a new `<p>` reading "Uploads are disabled in this
 * build.", the whole-section form of this guard would have stayed GREEN.
 *
 * The fix is to take the corpus from the section's BLOCK children and split
 * within each, so a paragraph boundary is at least as strong a separator as a
 * period. `h3,p,li` rather than `*`: those are the blocks this popover authors
 * copy in, and a wildcard would also collect wrapper `<div>`s whose
 * `textContent` is the same glued string the bug is made of.
 *
 * The selector is a PARAMETER with that exact string as its default, added for
 * §8 (the Connect an Agent guide authors its row headings as `h4`). Defaulted
 * rather than widened for everyone, so §6b's and §6c's corpus is byte-for-byte
 * what it was — widening it globally would silently change what §6c's polarity
 * fixtures are measuring, which is the shrink-without-failing hazard §5's
 * key-count pin exists for.
 */
function unscopedUploadRefusalsInBlocks(root: Element, selector = 'h3,p,li'): string[] {
  const blocks = [...root.querySelectorAll(selector)];
  // A section with no block children would make this vacuous in a second way,
  // so the absence is a failure rather than a pass.
  expect(blocks.length, 'the section has no h3/p/li blocks to scan').toBeGreaterThan(0);
  return blocks.flatMap((b) => unscopedUploadRefusals(b.textContent ?? ''));
}

describe('R1b §6b · no upload refusal in that section is left unscoped', () => {
  it('the shipped section scopes every refusal to the upload route', () => {
    expect(
      unscopedUploadRefusalsInBlocks(helpValuesSectionEl()),
      'an upload refusal in the Help popover is predicated of the application rather ' +
        'than of the upload route. CLAUDE.md §11: the refusal claim is true of ' +
        'POST /api/uploads ONLY, and this build ships a button labelled "Upload JSON ' +
        'File" (components/RecordValidator.tsx:241) that reads a file and POSTs its ' +
        'contents.',
    ).toEqual([]);
  });

  it('POLARITY: the sentence that shipped IS flagged', () => {
    const flagged = unscopedUploadRefusals(RETIRED_HELP_VALUES_SENTENCE);
    expect(
      flagged,
      'the exact sentence that shipped is not flagged, so this ban would not have ' +
        'caught the defect it was written for.',
    ).not.toHaveLength(0);
  });

  it.each([
    ['the bare absolute', 'File upload is refused.'],
    ['the app-wide form', 'This application refuses every file upload.'],
    ['the passive form', 'Uploads are blocked in this build.'],
    ['the deployment-wide form', 'File ingestion and upload are disabled for this deployment.'],
  ])('POLARITY: %s is flagged too', (_what, sentence) => {
    expect(unscopedUploadRefusals(sentence)).not.toHaveLength(0);
  });

  it.each([
    ['the route form', 'The upload route refuses every request it gets.'],
    ['the endpoint form', 'Its single upload endpoint declines all requests.'],
    ['the path form', 'The upload path is blocked; nothing it receives is read.'],
    ['the named-route form', 'POST /api/uploads is refused unconditionally.'],
  ])('and the scoped %s is NOT flagged', (_what, sentence) => {
    expect(
      unscopedUploadRefusals(sentence),
      'a correctly scoped refusal must stay sayable. A guard that fires on true copy ' +
        'teaches the next reader to weaken it (§3b).',
    ).toEqual([]);
  });
});

// --- §6c the vacuity is PROVEN, in both directions --------------------------
//
// A vacuity fix that cannot demonstrate the previously-escaping input is not a
// fix, it is a preference. The fixture below is the shipped section's own shape:
// a first `<p>` that ends on a correctly-scoped refusal (so it carries the
// `upload route` exemption), and a second `<p>` carrying a bare unscoped one.

/** The false sentence Task 1's defect would have looked like on this surface. */
const UNSCOPED_IN_A_NEW_PARAGRAPH = 'Uploads are disabled in this build.';

function twoParagraphSection(second: string): Element {
  const section = document.createElement('section');
  section.className = 'help-section';
  const h3 = document.createElement('h3');
  h3.textContent = 'Where values come from';
  const p1 = document.createElement('p');
  p1.textContent =
    'No control here reads one of your files and fills a field from it. The upload route ' +
    'refuses every request, and only two controls read a file you pick.';
  const p2 = document.createElement('p');
  p2.textContent = second;
  section.append(h3, p1, p2);
  document.body.append(section);
  return section;
}

describe('R1b §6c · the paragraph-boundary escape, measured both ways', () => {
  it('the whole-section (textContent) form MISSES it — this is the defect', () => {
    const section = twoParagraphSection(UNSCOPED_IN_A_NEW_PARAGRAPH);
    // The glue itself, asserted rather than assumed: no whitespace between the
    // two paragraphs' text, so the sentence splitter cannot separate them.
    expect(section.textContent).toContain('file you pick.Uploads are disabled');
    expect(
      unscopedUploadRefusals(section.textContent ?? ''),
      'if this now FIRES, the paragraph-boundary escape has been closed by some ' +
        'other means and §6b no longer needs the block-aware corpus. Re-derive ' +
        'before deleting anything: the escape is a property of `(?<=\\.)\\s+` ' +
        'meeting JSX, not of this fixture.',
    ).toEqual([]);
  });

  it('the block-aware form CATCHES it — this is the fix', () => {
    const section = twoParagraphSection(UNSCOPED_IN_A_NEW_PARAGRAPH);
    expect(unscopedUploadRefusalsInBlocks(section)).toEqual([UNSCOPED_IN_A_NEW_PARAGRAPH]);
  });

  it('and the block-aware form still leaves a correctly scoped paragraph alone', () => {
    // The other direction, per §3b: a guard that fires on true copy teaches the
    // next reader to weaken it.
    const section = twoParagraphSection('The upload route refuses every request it gets.');
    expect(unscopedUploadRefusalsInBlocks(section)).toEqual([]);
  });

  it('the same escape appended INSIDE the first paragraph is caught either way', () => {
    // The control the review used to isolate the cause: identical sentence,
    // identical copy, only the element boundary differs. If this failed, the
    // finding would be about the sentence rather than about the boundary.
    const section = twoParagraphSection('Dictating into Capture does not write a field.');
    const p1 = section.querySelector('p')!;
    p1.textContent = `${p1.textContent} ${UNSCOPED_IN_A_NEW_PARAGRAPH}`;
    // The flattened form DOES fire here — but note what it returns: the glue
    // swallows the FOLLOWING paragraph into the flagged chunk too, so even when
    // the whole-section form catches something it reports a span that is not a
    // sentence. The block-aware form returns the sentence itself.
    const flattened = unscopedUploadRefusals(section.textContent ?? '');
    expect(flattened).toHaveLength(1);
    expect(flattened[0]).toContain(UNSCOPED_IN_A_NEW_PARAGRAPH);
    expect(flattened[0]).toContain('Dictating into Capture');
    expect(unscopedUploadRefusalsInBlocks(section)).toEqual([UNSCOPED_IN_A_NEW_PARAGRAPH]);
  });
});

// --- §7 the SEVENTH site: Settings → Data & Privacy → synthetic-data-only ---
//
// See the file header for why this is not a fifth member of `SITES`. The bans in
// §3, §3b and §5 need no reader vocabulary, so they run over `ALL_BAN_SURFACES`
// and cover this card unchanged; §2's four-part claim deliberately does not.
//
// WHY THE UNSCOPED-REFUSAL BAN IS *NOT* ALSO RUN OVER `ALL_BAN_SURFACES`, and
// this is MEASURED rather than assumed, because widening it is the obvious next
// edit and it is the wrong one. Running `unscopedUploadRefusals` over all
// ~~six~~ SEVEN surfaces flags FOUR of them:
//
//   Governance → Policy                      2 sentences
//   the Load Materials on-ramp warning        1
//   Settings → no-real-experiment-data        2
//   Settings → Connect Your Agent no-upload   1
//   transcript capture: voiceAudioHandling    0
//   Settings → synthetic-data-only            0
//   Settings → Connect an Agent (the guide)   0   ← added with §8
//
// "six" is struck rather than replaced because a stale enumeration in THIS file
// is the defect it exists to catch, and §15 of `CLAUDE.md` records that class
// being published four times. The seventh entry is 0 for the same reason the
// fifth and sixth are: §8 scopes its refusal to the upload ROUTE. THE TABLE IS
// ALSO A TEST NOW — §8c re-measures this exact split on every run, so the next
// surface added to `ALL_BAN_SURFACES` cannot make this comment quietly wrong.
//
// All four are the `SITES` members, and all four are CORRECT COPY: they scope
// the refusal by stating the whole four-part claim in the same breath ("...and
// the refused request is never read, parsed, or inspected", "...while the CSV
// preview and the record validator do read what you paste or pick"). That is a
// DIFFERENT, stronger scoping mechanism than attaching `route` to the noun, and
// §2 is what holds it. So this ban belongs exactly to the surfaces that do NOT
// state the four-part claim — §6b's Help section and §7's card — and widening it
// would fire on true copy, which §3b records as worse than the gap it closes.
// If a future slice wants one ban over everything, the predicate has to accept
// either scoping mechanism; a wider window is not that.

/** `lib/settingsContent.ts:298,301` at `9a1a3d07`, verbatim — BOTH halves, and
 *  both were unscoped. Kept as the polarity fixtures. */
const RETIRED_SETTINGS_MODE_SUMMARY =
  'Synthetic-only mode — file upload is refused outright, and the app cannot tell real ' +
  'data from synthetic.';

const RETIRED_SETTINGS_MODE_DETAIL_OPENING =
  'This deployment runs in synthetic-only mode: file upload is refused outright, and the ' +
  'records in this workspace are synthetic.';

describe('R1b §7 · the Settings synthetic-only MODE card scopes its refusal', () => {
  it('scopes every upload refusal to the route, in both summary and detail', () => {
    expect(
      unscopedUploadRefusals(syntheticModeCard()),
      'the Settings → Data & Privacy synthetic-only card refuses an upload without ' +
        'scoping the refusal to the upload ROUTE. CLAUDE.md §11 records that claim as ' +
        'true of POST /api/uploads ONLY, and this build ships two controls that read a ' +
        'user-picked file (§1) — one of them, the Validator, reachable from the same ' +
        'Settings shell this card sits in.',
    ).toEqual([]);
  });

  it('POLARITY: the summary that shipped IS flagged', () => {
    expect(
      unscopedUploadRefusals(RETIRED_SETTINGS_MODE_SUMMARY),
      'the exact summary that shipped is not flagged, so this ban would not have ' +
        'caught the defect it was written for.',
    ).toEqual([RETIRED_SETTINGS_MODE_SUMMARY]);
  });

  it('POLARITY: the detail opening that shipped IS flagged', () => {
    expect(unscopedUploadRefusals(RETIRED_SETTINGS_MODE_DETAIL_OPENING)).toEqual([
      RETIRED_SETTINGS_MODE_DETAIL_OPENING,
    ]);
  });

  it('the card is inside ALL_BAN_SURFACES, so §3, §3b and §5 hold it too', () => {
    // The gap that let this card ship unscoped was not a missing pattern — every
    // pattern needed already existed — it was that no list named the card. This
    // asserts the membership rather than the patterns, because membership is
    // what was missing.
    expect(ALL_BAN_SURFACES.map(([site]) => site)).toContain(
      'Settings → Data & Privacy → synthetic-data-only',
    );
  });

  it('and the sibling card on the same tab is the one that states the claim in full', () => {
    // The de-duplication split this card sits on, asserted so that a future
    // slice cannot "fix" §7 by copying the four-part claim onto this card —
    // which `db-recon-truthfulness.test.tsx` §12 would then fail.
    expect(SITES.map(([site]) => site)).toContain(
      'Settings → Data & Privacy → no-real-experiment-data',
    );
    expect(SITES.map(([site]) => site)).not.toContain(
      'Settings → Data & Privacy → synthetic-data-only',
    );
  });
});

// --- §8 the EIGHTH site: Settings → API Access → Connect an Agent -----------
//
// See the file header for why this is not a fifth member of `SITES`. It IS a
// member of `ALL_BAN_SURFACES`, so §3, §3b, §5 and §4b hold it unchanged — and
// unlike §6b's Help section and §7's mode card, it was in NO list at all. The
// guard that looked like it covered it, `mcpNoUploadRow`, reads a DIFFERENT
// module (`lib/mcpConnectContent.ts`), so this surface was not "weaker but
// covered"; it was uncovered, which is why §8b's second direction matters.
//
// WHY THE UNSCOPED-REFUSAL BAN RUNS HERE AND STILL NOT OVER `ALL_BAN_SURFACES`.
// §7's enumeration is the reason, and it is re-measured in §8c below rather
// than inherited: the four `SITES` members state the whole four-part claim in
// the same breath, which is a different and stronger scoping mechanism than
// attaching `route` to the noun, and a widened loop would fire on their correct
// copy. This guide does NOT state the four-part claim and is forbidden from
// growing into it — `UX-021` measured this product's Settings/Help surfaces at
// 89% over length and the row is a row in an operational contract — so it
// belongs exactly where §6b's and §7's surfaces do: held by the narrow ban.
//
// The audience argument was weighed and is NOT a reason to leave it unscoped.
// An external agent genuinely cannot reach `RecordValidator` or
// `CsvReconcilePanel` (no agent tool does), so for a machine integrator the
// unscoped claim had no counterexample. But this renders on a Settings screen a
// human reads, the surrounding sentence is about what the API refuses, and a
// reader of it had no way to learn that two in-app controls read a file they
// pick. Scoping costs +2 words / +16 characters (measured: "file upload is
// refused outright", 5 words / 31 chars → "the upload route refuses every
// request outright", 7 / 47) and removes the app-wide reading; enumerating the
// readers here would cost ~25 words for a fact this audience cannot act on.

/** `screens/settings/ConnectAnAgent.tsx:102` at `31a220af`, verbatim — the
 *  clause was "and file upload is refused outright", predicated of the
 *  application. Kept as the polarity fixture. */
const RETIRED_CONNECT_AGENT_BOUNDARIES =
  "Read operations are safe to repeat. Writes change a record and require explicit user " +
  "intent — an agent should never write on someone's behalf unless that person asked for " +
  "that specific change. Several writes also require the record's current ETag, so a blind " +
  'overwrite is refused rather than applied, and file upload is refused outright.';

/**
 * The SENTENCE `unscopedUploadRefusals` returns for the fixture above, not the
 * clause. Written out because the first version of §8 expected the clause ("and
 * file upload is refused outright.") and went red: the splitter is
 * sentence-level by design (see its note — the scoping noun and the refusal verb
 * are one predicate, so a comma-level window would flag correct copy). Asserting
 * the exact span rather than `not.toHaveLength(0)` is what makes the polarity
 * proof specific: a pattern that started matching something ELSE in the fixture
 * would fail here instead of reading as a pass.
 */
const RETIRED_CONNECT_AGENT_FLAGGED_SENTENCE =
  "Several writes also require the record's current ETag, so a blind overwrite is " +
  'refused rather than applied, and file upload is refused outright.';

/** Every block the guide authors copy in. `h4` is the row heading level here,
 *  which the §6b default (`h3,p,li`) does not collect — see the note on
 *  `unscopedUploadRefusalsInBlocks`. */
const CONNECT_GUIDE_BLOCKS = 'h3,h4,p,li';

describe('R1b §8 · the Connect an Agent guide scopes every upload refusal', () => {
  it('no row, and no paragraph of the guide, refuses an upload unscoped', () => {
    expect(
      unscopedUploadRefusalsInBlocks(connectAnAgentGuideEl(), CONNECT_GUIDE_BLOCKS),
      'a row of the Connect an Agent guide refuses an upload without scoping the ' +
        'refusal to the upload ROUTE. CLAUDE.md §11 records that claim as true of ' +
        'POST /api/uploads ONLY, and this build ships two controls that read a ' +
        'user-picked file (§1) — components/RecordValidator.tsx:245 and ' +
        'components/CsvReconcilePanel.tsx:226. Scope it the way ' +
        'lib/transcriptCaptureContent.ts:261 does; do not delete the claim, and do ' +
        'not enumerate the two readers here (UX-021).',
    ).toEqual([]);
  });

  it('POLARITY: the clause that shipped IS flagged', () => {
    expect(
      unscopedUploadRefusals(RETIRED_CONNECT_AGENT_BOUNDARIES),
      'the exact row that shipped is not flagged, so this ban would not have caught ' +
        'the defect it was written for.',
    ).toEqual([RETIRED_CONNECT_AGENT_FLAGGED_SENTENCE]);
  });

  it('POLARITY: the retired clause is caught THROUGH the rendered-guide path too', () => {
    // §8's first test reads the DOM; this one proves the DOM path — not merely
    // the bare-string predicate — would have gone red on the shipped copy. The
    // guide's rows are one array literal, so the substitution is done on the
    // rendered node: same corpus, same selector, same splitter.
    const guide = connectAnAgentGuideEl();
    const row = [...guide.querySelectorAll('section.api-connect-section')].find(
      (el) => el.querySelector('h4')?.textContent === 'Respect Read and Write Boundaries',
    );
    expect(row, 'no "Respect Read and Write Boundaries" row in the guide').toBeTruthy();
    const p = row!.querySelector('p');
    expect(p, 'that row authors no paragraph').toBeTruthy();
    p!.textContent = RETIRED_CONNECT_AGENT_BOUNDARIES;
    expect(
      unscopedUploadRefusalsInBlocks(guide, CONNECT_GUIDE_BLOCKS),
      'reintroducing the shipped clause into the rendered guide does NOT trip this ' +
        'ban, so §8 is vacuous: it would pass whether the copy were true or false.',
    ).toEqual([RETIRED_CONNECT_AGENT_FLAGGED_SENTENCE]);
  });

  it('THE GAP WAS REAL: the pre-existing guard could not see this surface', () => {
    // The claim this slice rests on, asserted rather than argued. `SITES`'
    // fourth member is named "Connect Your Agent" and reads
    // `lib/mcpConnectContent.ts`; the guide is "Connect an Agent" in
    // `screens/settings/ConnectAnAgent.tsx`. Near-identical names, different
    // modules — which is how a whole surface stayed outside every list while
    // looking covered.
    expect(SITES.map(([site]) => site)).not.toContain(
      'Settings → API Access → Connect an Agent (the guide)',
    );
    expect(rawSource('lib/mcpConnectContent.ts')).not.toMatch(
      /the upload route refuses every request outright/,
    );
    // And the surface IS in the one list every vocabulary-free ban loops over,
    // which is the membership that was missing (§7 records the same shape).
    expect(ALL_BAN_SURFACES.map(([site]) => site)).toContain(
      'Settings → API Access → Connect an Agent (the guide)',
    );
  });

  it('the scoped replacement is the in-repo form, not a newly coined one', () => {
    // §3b's lesson: a guard that fires on true copy teaches the next reader to
    // weaken it. The inverse also holds — a correction that coins its own
    // phrasing is a seventh wording for one claim. This pins that the guide now
    // uses the same words two other modules already use.
    const shared = /the upload route refuses every request outright/;
    expect(connectAnAgentGuide()).toMatch(shared);
    expect(rawSource('lib/transcriptCaptureContent.ts')).toMatch(
      /upload route refuses every request outright/,
    );
    expect(rawSource('lib/settingsContent.ts')).toMatch(shared);
  });
});

// --- §8c the §7 enumeration, RE-MEASURED at seven surfaces ------------------
//
// §7's comment records a measured table over SIX surfaces and concludes the
// unscoped ban must not be widened to all of them. Adding a seventh member to
// `ALL_BAN_SURFACES` makes that table stale, and a stale enumeration in this
// file is the exact defect `CLAUDE.md` §15 records being published four times.
// So the table is a TEST rather than a comment: it fails if the split moves,
// instead of quietly describing a tree that has changed.
describe('R1b §8c · which surfaces the unscoped ban would fire on, measured', () => {
  it('fires on exactly the four SITES members, and on none of the other three', () => {
    // `cleanup()` BETWEEN accessors, not between tests. Four of the seven
    // render, and `afterEach` is too late: two mounted surfaces in one document
    // trip `screen.getByRole`/`getByText`'s "multiple elements found" as a
    // false failure, which is the harness artefact §4b documents for
    // `policyTabText` and the reason it loops one-test-per-site.
    const firing: string[] = [];
    for (const [site, text] of ALL_BAN_SURFACES) {
      const rendered = text();
      cleanup();
      if (unscopedUploadRefusals(rendered).length > 0) firing.push(site);
    }
    expect(
      firing,
      'the set of surfaces the unscoped-refusal ban fires on has moved. If a SITES ' +
        'member left the set, check it still states the four-part claim (§2). If a ' +
        'NON-SITES member entered it, that surface has shipped an unscoped refusal ' +
        'and needs scoping, not a narrower ban: §3b records that widening the loop ' +
        'to fire on the four correct-copy SITES is worse than the gap it closes.',
    ).toEqual(SITES.map(([site]) => site));
  });
});
