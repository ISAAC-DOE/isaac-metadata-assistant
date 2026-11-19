# Start times and the instrument clock (Step 7)

Read this when the question `stated_utc_start_times` or `clock_time_zone` is listed, or a record warns "start time left out".

## One answer for every group's start time (`stated_utc_start_times`)

A SPEC file states in its header when the file was created: `#E` (a UTC epoch) and `#D` (the same instant as a
local clock time with no zone). Each scan then writes its own `#D`, a little later. When these disagree in two or
more groups, this one question asks once, for every group.

- `#E` is the file's creation, not the first scan's start. The question says the largest gap to the first scan.
- Ask: "Use each file's creation time as the record's start? The first scan started at most N s later."
- On their yes: `<isaac> bundle decide <bundle> --question <Q> --decision confirm --by "<name>"` (no `--value`;
  `--only group:<id>` for one group). Each run gets its own instant.
- Say that which instant a record's start should be (file creation or first scan) is still open for the protocol review.
- The reply says which groups it did not reach and why (`not_reached`): no `#E` line, `#E` readings that disagree, a
  first scan more than 10 minutes late, a group of two runs, or a file started more than once. Answer those one by one.
- A file started more than once has several `#E` lines ("its file was started N times"). Its question asks which is the start.
- A `#D` reading is a local time with no zone and can never be recorded. A per-group start-time question lists the UTC
  instants the bundle holds (`utc_readings`): show them, ask which is the start, record `correct --value <that instant>`.
- A record whose runs were given different starts carries none and says so.
- The Local Imports page does not show this question yet; it asks per group.

## The instrument clock's time zone (`clock_time_zone`)

SSRL EXAFS Data Collector headers (beamline 4-3 style) write the start as a local clock time with no zone. Those start
times have no value until the scientist states the zone the instrument clock was set to.

- **Suggest no zone.** No file states one, and the facility's location is not evidence about the clock.
- Record: `<isaac> bundle decide <bundle> --question <Q> --decision set_clock_time_zone --value <IANA name> --by "<name>"`
  (Area/Location, or `UTC`). An offset (`-08:00`) or an abbreviation (`PST`) is refused: ask for the zone name.
- Then each start time is shown converted to UTC and needs its own `confirm` (a bulk confirm is allowed).
- A time in the daylight-saving change hour gets no value: ask for the UTC start and record
  `correct --value YYYY-MM-DDTHH:MM:SSZ`.
- If the zone is changed later, every start confirmed under the old one must be confirmed again; `decide` says how many.
- "I don't know": `--question <Q> --decision defer` (no `--value`). Every record of those runs then goes out without
  its start time and says so ("start time left out: instrument clock zone deferred"). Tell them before they export.
- Once a zone is recorded, `defer` is refused. To change the zone, state it again.
