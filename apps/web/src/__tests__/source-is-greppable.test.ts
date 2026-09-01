/*
 * NO SOURCE FILE UNDER `apps/web/src` MAY HOLD A RAW NUL BYTE.
 *
 * ── THE MEASUREMENT THIS EXISTS FOR, TAKEN AT THIS HEAD ─────────────────────
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
 * `'\0'` separator in `rows.join(...)` — perfectly good code, written as a raw byte
 * instead of the escape (backslash-u-0-0-0-0), which produces the identical string at
 * runtime.
 *
 * THE FIRST RUN OF THIS GUARD FAILED ON ITS OWN DOC COMMENT, which had reproduced the
 * defect while describing it: an editor round-tripped that escape back into a raw byte.
 * That is recorded rather than tidied away — it is how easily the byte arrives, and it is
 * a live demonstration that the assertion below fires.
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
 * SCOPE IS DELIBERATELY NARROW: `apps/web/src` only, which is what this slice owns.
 * Widening it to the repository would sweep binary fixtures and generated artifacts that
 * legitimately hold NULs, and a guard that needs exemptions on day one is the
 * cries-wolf-then-gets-suppressed outcome `CLAUDE.md` §11 records for the withdrawn
 * home-directory-path assertion.
 */
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join, relative } from 'node:path';

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

function everyFileUnder(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...everyFileUnder(full));
    else out.push(full);
  }
  return out;
}

describe('the frontend source is greppable without -a', () => {
  it('holds no raw NUL byte in any file under apps/web/src', () => {
    const files = everyFileUnder(SRC);
    // THE SWEEP REALLY RAN. A walker that silently returned nothing would pass the
    // assertion below and prove exactly nothing.
    expect(files.length).toBeGreaterThan(300);

    const offenders = files
      .map((path) => ({ path, nuls: countNuls(path) }))
      .filter((row) => row.nuls > 0)
      .map((row) => `${relative(SRC, row.path)} (${row.nuls} NUL)`);

    expect(
      offenders,
      'a raw NUL byte makes a file invisible to `grep -r` and `rg`; write the escape ' +
        "`'\\u0000'` instead, which is the identical string at runtime",
    ).toEqual([]);
  });
});

function countNuls(path: string): number {
  const bytes = readFileSync(path);
  let count = 0;
  for (const byte of bytes) if (byte === 0) count += 1;
  return count;
}
