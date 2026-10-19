import { Fragment } from 'react';

/**
 * A FILENAME OR STEM THAT WRAPS AT ITS OWN SEPARATORS (2026-10-18, QA `C-29`).
 *
 * At 1024px a long stem — `05_02_ZZ2_base_after500Cycling_filter20_800mV_001.dat` —
 * broke mid-token (`after500Cyc|ling`), because the only rule that let it wrap at all
 * was `overflow-wrap: anywhere`. This inserts a `<wbr>` after each `_`, `/` and `-`, and
 * after a `.` that is not a decimal point, so a line breaks between the pieces a scientist reads, and the CSS fallback
 * (still `anywhere`) is reached only by a single piece longer than its cell.
 *
 * USED SPARINGLY, ON PURPOSE: only where a name is the cell's content and is on screen
 * by default (a measurement's stem, a conflict's readings and subject, a source's name).
 * Each `<wbr>` is a DOM node, and the first version put one in every locator inside every
 * candidate's detail — 8,630 of them on the example archive, which took an axe scan of the
 * opened Runs stage past a minute. Detail lists keep the CSS wrapping.
 *
 * The TEXT IS UNCHANGED: `<wbr>` adds no character to `textContent`, so a copy, a
 * search, a screen reader and every test reading the text get the exact string.
 */
export function Breakable({ text: raw }: { text: string | null | undefined }) {
  /* A missing locator renders nothing rather than throwing (a reading may carry none). */
  const text = raw === null || raw === undefined ? '' : String(raw);
  const pieces = text.split(/(?<=[_/\-])|(?<=\.)(?!\d)/);
  if (pieces.length < 2) return <>{text}</>;
  return (
    <>
      {pieces.map((piece, index) => (
        <Fragment key={index}>
          {piece}
          {index < pieces.length - 1 && <wbr />}
        </Fragment>
      ))}
    </>
  );
}
