/*
 * NO FILE GIT TRACKS MAY HOLD A RAW NUL BYTE, WITH ONE NAMED EXEMPTION.
 *
 * ── THE MEASUREMENT THIS EXISTS FOR ─────────────────────────────────────────
 *
 * `grep` and `rg` classify a file containing a NUL byte as BINARY and skip it — silently,
 * exit code 0, no diagnostic — unless `-a` is passed. So a file with one NUL is invisible
 * to every sweep of the codebase that does not remember the flag.
 *
 * Measured on this branch's parent commit, over the 379 files under `apps/web/src`:
 * EXACTLY ONE held a NUL, and it was `components/RecordDescriptionPanel.tsx` — the only
 * file in the repository implementing the record-level capture surface. The consequence
 * was not hypothetical:
 *
 *     grep -rl  RecordDescriptionPanel apps/web/src   ->  2 files
 *     grep -ral RecordDescriptionPanel apps/web/src   ->  3 files   (the panel itself)
 *
 * A reader auditing whether a scientist can enter a facility or a sample value on the
 * record was therefore told the implementation did not exist. The bytes were a deliberate
 * separator in `rows.join(...)`, written as a raw byte instead of the escape
 * (backslash-u-0-0-0-0), which produces the identical string at runtime.
 *
 * THE FIRST RUN OF THIS GUARD FAILED ON ITS OWN DOC COMMENT, which had reproduced the
 * defect while describing it: an editor round-tripped that escape back into a raw byte.
 * That is recorded rather than tidied away — it is how easily the byte arrives, and it is
 * a live demonstration that the assertion below fires. It happened a SECOND time while
 * this file was being widened, in the shell heredoc writing it.
 *
 * ── WHY A TEST AND NOT A NOTE ───────────────────────────────────────────────
 *
 * `CLAUDE.md` §11 records this exact trap once already, in `lib/experimentGraph.ts`, and
 * records it as no longer live because that file was rewritten. It came back in a
 * different file. A note that says "remember `-a`" depends on the next author having read
 * it; this fails the moment the byte lands, and names the file.
 *
 * ── THE ASSERTION IS OVER BYTES, NOT OVER FILENAMES ─────────────────────────
 *
 * Stated the way `.venv`'s symlink guard learned to state itself — over the recorded
 * property rather than over a name — because the next one will not be in this file.
 *
 * ── SCOPE: EVERY TRACKED FILE. THE NARROWER SCOPE WAS WRONG ABOUT ITS OWN REASON ──
 *
 * This guard first scanned `apps/web/src` alone, and said so because widening it "would
 * sweep binary fixtures and generated artifacts that legitimately hold NULs" — PLURAL.
 * **That reason is measured false.** Over all 975 files `git ls-files` reports at this
 * head, exactly TWO hold a NUL:
 *
 *     docs/superpowers/plans/2026-07-27-phase-36v1-hosted-qa-fix-forward.md   (1 NUL)
 *     qa/validator-upload-package/isaac-validator-qa-files.zip                (918 NUL)
 *
 * (A third, `apps/web/src/components/RecordDescriptionPanel.tsx`, held 2 and was fixed by
 * the slice this guard shipped with. The zip figure is NUL BYTES; those bytes fall on 86
 * distinct lines, which is what a line-oriented count reports instead.)
 *
 * So the exemption list is not "binary fixtures and generated artifacts". It is ONE FILE,
 * and the narrow scope was hiding a real markdown offender in `docs/` — a plan document,
 * exactly the kind of file a reader greps — rather than sparing a crowd of legitimate
 * ones. A guard that needs one honest exemption is not the cries-wolf outcome
 * `CLAUDE.md` §11 records for the withdrawn home-directory-path assertion; a guard scoped
 * to a tenth of the repository on an unmeasured guess is nearer the failure that
 * withdrawal was actually about.
 *
 * THE DOCS FILE IS DELIBERATELY NOT EXEMPTED. It is a real offender, being fixed on its
 * own branch; exempting it would convert a finding into a permission. Until that branch
 * lands this assertion is expected to name that one path — which is the guard working,
 * not the guard misconfigured.
 *
 * THE EXEMPTION IS BY EXACT PATH, NOT BY EXTENSION, and the choice is load-bearing. A
 * `.zip` rule would silently exempt every archive a future author adds anywhere; an exact
 * path exempts the one file measured to need it, and fails loudly if that file is moved,
 * renamed, or joined by a second. A second test below asserts the exemption is still
 * LIVE — tracked, and still holding a NUL — so a dead exemption cannot sit here quietly
 * widening what this guard permits.
 *
 * This file lives under `apps/web/src` because that is where the slice that wrote it
 * owns code; what it asserts is repository-wide, and the location is not the scope.
 */
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

/** Locate `apps/web/src`. Deliberately not `import.meta.url`: under jsdom that is an
 *  http URL, not a file one — the same reasoning `tutorial-anchors.test.tsx` records,
 *  duplicated rather than shared for the same reason it gives. */
function locateSrcDir(): string {
  const candidates = [join(process.cwd(), 'src'), join(process.cwd(), 'apps', 'web', 'src')];
  const found = candidates.find((dir) => existsSync(join(dir, 'main.tsx')));
  if (found === undefined) throw new Error(`cannot locate apps/web/src from ${process.cwd()}`);
  return found;
}

const SRC = locateSrcDir();
/** `<repo>/apps/web/src` -> `<repo>`. Derived from the located directory, not guessed. */
const REPO_ROOT = join(SRC, '..', '..', '..');

/** The byte, written as an escape. Never as itself — that is the defect this file guards. */
const NUL = '\u0000';

/**
 * THE ONE FILE PERMITTED TO HOLD A NUL, BY EXACT REPO-RELATIVE PATH.
 *
 * A genuine binary: the packaged fixture bundle the Validator upload QA walkthrough hands
 * a tester. Nothing greps a zip, and its 918 NUL bytes are its content rather than a typo
 * in prose.
 */
const EXEMPT_BY_EXACT_PATH: readonly string[] = [
  'qa/validator-upload-package/isaac-validator-qa-files.zip',
];

/** Every path `git ls-files` reports, NUL-delimited so a path with a newline survives. */
function everyTrackedPath(): string[] {
  const out = execFileSync('git', ['ls-files', '-z'], {
    cwd: REPO_ROOT,
    maxBuffer: 64 * 1024 * 1024,
  });
  return out
    .toString('utf8')
    .split(NUL)
    .filter((rel) => rel !== '');
}

/** NUL bytes in a file, counted through Buffer.indexOf so a large artifact is cheap. */
function countNuls(abs: string): number {
  const bytes = readFileSync(abs);
  let count = 0;
  for (let at = bytes.indexOf(0); at !== -1; at = bytes.indexOf(0, at + 1)) count += 1;
  return count;
}

describe('the repository is greppable without -a', () => {
  it('holds no raw NUL byte in any tracked file, outside one named exemption', () => {
    const tracked = everyTrackedPath();

    // THE SWEEP REALLY RAN. A `git` call that returned nothing — a broken invocation, a
    // wrong cwd — would pass the assertion below and prove exactly nothing. A floor AND
    // two landmarks, because a floor alone is satisfied by any large wrong list.
    expect(tracked.length).toBeGreaterThan(500);
    expect(tracked).toContain('apps/web/src/main.tsx');
    expect(tracked).toContain('CLAUDE.md');

    const offenders = tracked
      // A tracked path can be absent from the working tree mid-operation (a checkout, a
      // rebase). Skipping it is not a hole: it has no bytes here to judge.
      .filter((rel) => {
        const abs = join(REPO_ROOT, rel);
        return existsSync(abs) && statSync(abs).isFile();
      })
      .filter((rel) => !EXEMPT_BY_EXACT_PATH.includes(rel))
      .map((rel) => ({ rel, nuls: countNuls(join(REPO_ROOT, rel)) }))
      .filter((row) => row.nuls > 0)
      .map((row) => `${row.rel} (${row.nuls} NUL)`);

    expect(
      offenders,
      'a raw NUL byte makes a file invisible to `grep -r` and `rg`; in source write the ' +
        'escape (backslash-u-0-0-0-0), which is the identical string at runtime, and in ' +
        'prose name the codepoint instead of embedding it',
    ).toEqual([]);
  });

  it('keeps the exemption list live, so a dead entry cannot quietly widen it', () => {
    const tracked = new Set(everyTrackedPath());
    for (const rel of EXEMPT_BY_EXACT_PATH) {
      expect(
        [...tracked],
        `${rel} is exempted but no longer tracked — delete the exemption`,
      ).toContain(rel);
      expect(
        countNuls(join(REPO_ROOT, rel)),
        `${rel} is exempted but holds no NUL — delete the exemption`,
      ).toBeGreaterThan(0);
    }
    // AND THE EXEMPTION IS ONE FILE. Stated as a number so widening it is a visible edit
    // to this line rather than an unremarked extra array entry.
    expect(EXEMPT_BY_EXACT_PATH).toHaveLength(1);
  });
});
