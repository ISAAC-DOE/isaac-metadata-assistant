/**
 * BACKTICK MARKUP, RENDERED RATHER THAN PRINTED.
 *
 * Text written for a terminal or a docstring marks commands and identifiers the way
 * Markdown does — `isaac bundle decide`, `persistence`. Rendered as plain text the reader
 * sees the backticks themselves. A pair of backticks becomes an inline `<code>`, and
 * NOTHING ELSE CHANGES: no word is added or dropped, the span's text is exactly what sat
 * between the backticks, and an unpaired backtick is left as it is rather than guessed at.
 *
 * First written for the API reference (`screens/settings/ApiDocs.tsx`, 2026-10-12); shared
 * since 2026-11-01 so Local Imports and Schema Proposals, whose copy and bundle sentences
 * carry the same markup, render it the same way.
 */
export function InlineCode({ text }: { text: string }) {
  const parts = text.split(/`([^`\n]+)`/);
  if (parts.length === 1) return <>{text}</>;
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <code className="mono inline-code" key={i}>
            {part}
          </code>
        ) : (
          part
        ),
      )}
    </>
  );
}
