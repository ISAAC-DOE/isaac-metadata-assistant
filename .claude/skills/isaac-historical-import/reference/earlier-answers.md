# Earlier answers (opt-in, this computer only)

Read this when a question shows `earlier_answers`, or before you ask whether to remember answers.

ISAAC can remember what a scientist confirmed on earlier beamtimes and show it beside the same question on a new one.
It is off until they agree. Nothing is ever filled in from it.

**Asking.** Ask once, when `<isaac> answer-memory status` says `enabled: false` and `file_exists: false`:
"Shall I remember the answers you confirm, for your future beamtimes, on this computer only? Next time I'd show them
as suggestions."

- Yes: `<isaac> answer-memory on --by "<name>"`. No: nothing, and do not ask again.
- If it was turned off before (`file_exists: true`), do not ask: they chose.
- From then on every answer recorded with `--by` is remembered at that moment. Never "I don't know", a reject, my
  readings, a dry run or a preview.
- Answers recorded before it was on: only on their yes, `<isaac> answer-memory learn <bundle> --by "<name>"`.
- They can see it (`<isaac> answer-memory list`), stop it (`<isaac> answer-memory off`) or forget answers
  (`<isaac> answer-memory forget --entry <id>`, `--beamtime <folder name>`, `--all`).

**Using a hint.** A matching question gains `earlier_answers` and one `earlier_answers_statement`.

- Say it as last time's answer, never as this beamtime's: "On SYN_2100-01 you said the ZZ1 sample is a pellet: same here?"
- Record it only on their yes, as their own answer: the question's `answer_command` with
  `--decision correct --value <that exact value> --from-earlier-answer <entry_id>`
  (the clock zone: `--decision set_clock_time_zone --value <it> --from-earlier-answer <entry_id>`).
- `disagrees: true`: read every value back with who and when, and ask which applies. Never pick one.
- Hints appear only for the same scope: a sample fact for the same sample name and the same confirmed group or
  organization; a beamline fact for the same confirmed facility and beamline. So answer the facility, the beamline and
  who produced the data first.
