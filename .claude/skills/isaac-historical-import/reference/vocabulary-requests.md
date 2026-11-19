# A word that is not on the list (Step 7)

Read this when the scientist gives a real value that a field's closed list lacks, and keeps their own word.

1. Say that the list has no such value. Show the list. Never pick the nearest value for them.
2. If they keep their word, run the answer once with `--as-said`:
   `<isaac> bundle decide <bundle> --question <Q> --decision correct --value "<their exact word>" --as-said --by "<name>"`
   - It records NO decision and NO value. It keeps their word as a vocabulary request in their name.
   - It exits 0 and the reply starts with that (`vocabulary_request_kept`, `decision_recorded: false`).
   - Never pass a word they did not say. Without `--as-said`, an off-list value keeps nothing.
   - `--note` holds only their own words about the term, or is left out.
3. Say what happens to the field meanwhile:
   - Where an earlier decision gives the field an allowed value, the record keeps exporting it. The reply names it
     ("the record keeps `surface_oxidation` meanwhile"): ask whether that is acceptable until the term exists.
   - Where none is held, the field stays missing (`bundle validate` lists it under `pending_vocabulary`) until the
     vocabulary has the term or they give an allowed value.
4. A later answer that settles an open request says "This answers your request for 'oxidation' (vr-…); it is no longer
   drafted". Say that too.

## Drafting the term for the vocabulary owners

`<isaac> bundle propose-terms <bundle> --out <bundle>-notes/terms.json` (it prints values and sends nothing).

- Say which terms come only from my readings (`by_origin.ai_reading`). Draft one only if they want it.
- A word that names an existing term is not drafted: "use `RHE` (an existing term)". Ask whether to answer `RHE`.
- A close term is drafted with `check_existing`: its description must say why none of those fits.
- A term with a space is not drafted ("N term(s) need a one-word form (ask)"). Ask for a one-word form and record
  that; never rewrite it yourself.
- A draft marked `answered: true` is not offered: they have since given an allowed value.
- A draft counts only requests still open. `earlier_requests_answered_note` says which earlier request was answered
  since: say that sentence.
- They write each description themselves, on the Schema Proposals page (Propose a Change → Load drafts from a local
  import). Never in the file, never by you.
- Saving a proposal there sends the term, its counts and its file-name citations to the ISAAC server that page uses.
  Say so before they save. Nothing is sent before that.
- After more answers, `--merge` updates the same file and keeps every description in it. A description of a term
  answered since is kept only in case they ask for the word again: it is not to be filed.
