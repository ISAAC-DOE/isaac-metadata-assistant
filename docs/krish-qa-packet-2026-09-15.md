# Manual QA — 2026-09-15 session

**Short on purpose.** Everything that could be verified from this environment already was, with
the evidence linked. What is below is only what genuinely needs you, either because it needs your
credentials or because no tool here can drive it.

Each item says **why it needs a human**, so you can skip any you do not care about without
wondering what you are giving up.

---

## 1. Hosted sign-in and release SHA — 5 minutes

`/krish` sits behind an Authentik edge this environment cannot authenticate to, and an agent must
not enter credentials. **Nothing about the hosted rollout of this session's work is verified.**

- Sign in to `/krish`.
- Open `/krish/api/health` and read `commit`.
- Confirm it matches the merge commit in this session's final report.

**Until you do this, the honest status of every image from this session is `HOSTED QA PENDING`.**

---

## 2. The browser tab icon — 10 seconds

This is the one item where I got close and could not finish. Verified here: all four icon links
are present, resolve `200` with correct content types, carry the header tile's exact colour
(`rgb(44,106,176)`) and the **identical path geometry** as the rendered header glyph, and resolve
correctly under both `/` and `/krish/` builds.

**What I cannot do:** screenshot browser chrome. The tab strip is not part of the page.

- Look at the tab. Confirm the ISAAC mark, not a generic document icon.
- Click between two or three screens and confirm it does not get replaced.

---

## 3. Real microphone — 2 minutes

No automated test can hold a real microphone, and the OS recording indicator is not observable
from a page.

- Capture → Open Recorder → **Start**, **Pause**, **Resume**, **Stop**.
- Confirm the elapsed clock excludes the paused time.
- **Confirm the OS microphone indicator goes out when you stop**, and again after you navigate
  away mid-recording.

---

## 4. 200% browser zoom — 5 minutes

**No CDP method, flag or API can drive true browser zoom.** This is not automatable at all, and
never has been here.

At `Cmd +` twice (200%), look for clipped text or an unreachable control on: **My Experiments**,
a record's **Runs**, **Capture**, **Historical Import**, **Statistics**, **Settings**.

---

## 5. A genuinely narrow screen — 5 minutes

`resize_window` reports success while the rendered viewport does not follow, so narrow widths were
exercised through a same-origin iframe. That is a good proxy and it is not a real device.

On a phone, or a real browser window dragged narrow:

- the Historical Import stepper should become **vertical** with a continuous connecting line;
- the file list rows should stack rather than squeeze;
- nothing should scroll sideways.

---

## 6. New in this session — worth two minutes of your own eyes

These are the things you asked for. All are verified functionally; what a human adds is taste.

| what | where | what to look for |
|---|---|---|
| file selection for an import | Historical Import → start an import → Sources | drop zone + `Choose Files`, a row per file with size and type, `×` to remove, and **`Local only — not sent to ISAAC` on every row** |
| proposal creation | a record → Experiment Data | `New Proposal`, reachable on a record with no notes |
| Statistics back in the sidebar | left nav | four destinations: My Experiments, Historical Import, Statistics, Settings |
| Governance moved | Settings → Data & Privacy | `Governance & Safety` reachable from there; the Validator still one click from where it is offered |
| **Settings under Advanced** | Settings | seven tabs in two groups — `Overview · Data & Privacy · About · Help & Tutorial`, then a faint divider, the word `ADVANCED`, then `API Access · Endpoint Explorer · Connect Your Agent`. Two things worth your taste specifically: does `ADVANCED` read as a **group marker** rather than as part of "API Access"; and at a narrow width the row wraps so the marker can start its own line — tell me if that reads as clutter |
| **Add a whole import to a record** | Historical Import → open a session that has **two or more** sendable candidates | one `Add This Import to a Record` control above the candidate list, a record picker, and a run box. Three things to try: send **without** naming a run (it should refuse the *whole* thing and say why, not send half); then name the run and send (it should report `N sent · N already there · N could not be sent · N candidates`, with the reason for each one it would not send); then press it **again** (everything should read `already there`, and nothing new created) |

**Why the import control only appears with two or more candidates:** with exactly one, that
candidate's own `Send to Review` form already *is* the whole batch, and two controls for one act is
the thing that makes a reader wonder which is the real one. If you would rather see it always, say
so — it is one line.

---

## What is NOT waiting on you

Stated so this list does not look longer than it is:

- **Proposal acceptance** answers `409 human_actor_required` in every default deployment, because
  no trusted authentication boundary exists. That is a configuration fact and no amount of
  application work closes it — it needs Hao/SLAC, not you.
- **Voice→text** needs an approved provider (Dean's D1–D9, deferred). The recorder, pause/resume
  and playback all work; transcription refuses honestly.
- **Real file ingestion** stays disabled by design. The staging panel deliberately sends nothing;
  enabling real byte ingestion is a governance decision, not missing code.
- **A `.mac` or spreadsheet parser** cannot be written until a representative BL15-2 file exists.
  Designing one against zero examples is forbidden, and this repository holds no such file.
- **Nothing on this list is blocking the Add-to-Record step.** It is built and works against the
  synthetic sources today; a real `.mac` file would give it more to find, not make it work.

---

## One thing I could not check, and it is not in the table above

**Two prose findings on the import panel are declined rather than fixed, and one of them is your
call.** Impeccable's in-browser detector flags the panel's lead as sitting in an 86-character-wide
column. The only thing that clears it is a narrower column — and your recorded direction is *don't
cap prose narrow*, so I left it and shortened the sentence instead. It is the same measure question
as nineteen other prose blocks on that screen, so it is a **screen-wide type decision**, not this
panel's. If you want prose capped to a reading measure app-wide, that is a single change with an
accessibility round-trip, and it needs you to say so.
