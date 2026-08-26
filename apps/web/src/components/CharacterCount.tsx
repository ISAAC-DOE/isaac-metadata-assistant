/*
 * THE REMAINING-CHARACTERS LINE, and it is a safety control rather than a nicety.
 *
 * It exists because `maxLength` on an input does not warn: a pasted paragraph is
 * silently cut at the limit, and the reader's next act is to submit text that is
 * missing its end and be told nothing. Every form that would otherwise carry
 * `maxLength` carries this instead, plus a refusal that names the field, the limit
 * and the overage and sends nothing (D5, `ExperimentsHome`).
 *
 * HOISTED HERE WHEN THE SECOND CONSUMER APPEARED, not copied. It lived privately in
 * `ExperimentsHome` while the create form was the only surface with a length cap; the
 * rename form has the same two caps on the same two fields, and a second definition
 * would have been a second answer to "how is a length limit communicated" — free to
 * drift in wording, in the colour rule, and in whether the text says what the colour
 * says. One definition, two callers.
 *
 * THE COLOUR IS NEVER THE ONLY SIGNAL. Over the limit the line takes the failure
 * colour AND says so in words, so a reader who cannot distinguish it still learns the
 * same thing. That is why the over-limit branch is a sentence and not a red number.
 */
export function CharacterCount({
  id,
  length,
  limit,
}: {
  id: string;
  length: number;
  limit: number;
}) {
  const over = length - limit;
  return (
    <span
      className="create-experiment-hint create-experiment-count"
      id={id}
      data-over={over > 0 ? 'true' : undefined}
    >
      {over > 0
        ? `${length} characters — ${over} over the ${limit}-character limit. Nothing has been cut; shorten it to create the experiment.`
        : `${length} of ${limit} characters`}
    </span>
  );
}

/** The two caps `CreateExperimentRequest` and `RenameExperimentRequest` both declare.
 *
 *  They are the SAME two numbers on purpose: a title a reader can create must be a
 *  title they can rename to, and a note they can write must be a note they can
 *  correct. The backend asserts the equality too
 *  (`test_rename_an_experiment.py::test_the_length_caps_are_the_same_two_the_create_path_uses`),
 *  because a client-side pair that agreed by coincidence would drift silently. */
export const TITLE_MAX_LENGTH = 200;
export const DESCRIPTION_MAX_LENGTH = 1000;
