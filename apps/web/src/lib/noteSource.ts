/**
 * THE NOTE-SOURCE VOCABULARY, IN PRODUCT WORDS — one map for the two panels that
 * show where a note came from (Unmapped Notes, and the quote on an ingestion
 * proposal). Moved here out of `UnmappedNotesPanel` rather than copied, so the two
 * cannot drift (owner QA P1, 2026-09-22).
 *
 * An unknown source is shown VERBATIM: a token this build has not been taught is
 * still a fact, and a generic word in its place would lose the only specific part.
 */
export const NOTE_SOURCE_LABELS: Readonly<Record<string, string>> = {
  typed_note: 'Typed here',
  transcript: 'From a transcript',
  csv_column: 'An unrecognised CSV column',
  file_listing_line: 'A line of a file listing',
  extraction_residue: 'A label the extractor would not guess at',
  historical_source_line: 'Read from a historical source file',
};

export function noteSourceLabel(source: string): string {
  return NOTE_SOURCE_LABELS[source] ?? source;
}
