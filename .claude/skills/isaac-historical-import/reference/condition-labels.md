# Condition labels (Step 7, the "values to confirm" message)

Read this before you send the "values to confirm" message.

Grouping keeps records apart by electrode, filter and cycling history. Without these labels such records can export
with the same body. ISAAC proposes each label from the readings the grouping used. Each is a `condition_label`
question at experiment scope. Nothing is written until the scientist answers.

Most take one call: `<isaac> bundle decide <bundle> --question <Q> --decision confirm --by "<name>"`.

| Label | Proposed as | Their own wording |
|---|---|---|
| **Sample id** (`sample.sample_id`) | one id per electrode: `<folder>:<sample>-<electrode>` | `--decision correct --value "{sample}-e{electrode}"` (also `{beamtime}`) |
| **Filter** | `filter<n>`, the count a file name or the scan header states; `filter0` is no filter | `--value "{filter} filters"` |
| **History** | one question per file-name token (`beforeCycling`, `after1500Cycling`), split into words | `--decision correct --value "<their sentence>"` |
| **Tag** | one tag for the beamtime, from the folder name | `--decision correct --value <tag>` |
| **Follows** | for one sample under equal conditions, each later stage follows the one before | confirm or reject only |

Rules:

- **Sample id.** One id names one physical object, on every record of it. Two electrodes never get one id (refused).
  One electrode's own id: add `--only group:<id>`.
- **Filter.** Never invent a material such as "Al". If they type a value the files contradict, it is recorded and the
  reply names the contradiction: say it.
- **History.** Never say what the number means (mV or cycles). Ask, and record their sentence.
- **Follows.** Read every pair back. A chain ISAAC could not order is listed with its reason (`not_proposed`); two
  stages that share a run number are held, because the files do not say which came first. The link is written only
  when both records carry the same sample id.
- **Electrode position** (asked only when the files do not settle which file-name number is the electrode): ask
  "which file-name number is the electrode or physical sample?". Record `--decision correct --value <position>`, or
  `reject` if no number is. ISAAC never assumes it.

Groups ISAAC proposed nothing for:

- They are in `not_proposed`, with the reason and the readings. Reasons: the files' readings disagree; one number sits
  beside two sample names; a position was said not to be a counter.
- Answer one with `--only group:<id> --decision correct --value <value>`, or leave it. Several groups, one value:
  give `--only` once per group.
- A group takes a sample id that other runs hold only when the scientist says it is the same physical sample: add
  `--same-sample`, after saying that back. If the reply holds it because the two file names share no sample word, read
  the reason back and add `--names-differ-ok` only on their confirmation. Two different parsed sample names are never joined.
- After a bulk confirm the reply says "N group(s) still have no <label>: <files>", and a follow-up question keeps asking them.

How answers behave here:

- Without `--only`, an answer never changes an earlier one: it writes only runs with no answer, and names the groups
  it left (`kept`). To change a group, answer it with `--only group:<id>`.
- `reject` records that the label is not written.
- `<isaac> bundle show <bundle> question <Q>` lists every group of a label question.
- A disagreement question on one of these readings (filter, cycling token, electrode number) says which label
  question writes the field. Settle the disagreement there; the label question then proposes the value.
- Adding a label changes a record's body, so a record exported before gets a new id on the next export.
- `validate` warns when a ready record lacks a label ISAAC could not propose, and when two ready records carry one
  sample id and every condition the same.
