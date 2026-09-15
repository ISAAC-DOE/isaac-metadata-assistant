# Choosing files for a Historical Import without sending one — browser proof, 2026-09-15

**What the owner asked for.** *"The product owner explicitly wants a familiar file-selection
interface… Implement the complete scientist-facing file staging/upload UI now"* — with the
governance boundary preserved, and with the existing guards **reconciled, not deleted**.

**What this proves.** That the shipped panel gives a scientist the file UX, and that it sends
nothing — by observation of every transport, not by reading the code.

## The decline this reverses

`HistoricalImport.tsx` recorded that a previous session **built this and reverted it**:

> *"A `Choose Files…` button is an upload affordance whatever it does underneath — a scientist who
> picked twelve files would reasonably believe twelve files had been uploaded. Recording their
> names while they believe that is worse than asking them to type."*

That argument was **not overruled**; its objection was **answered**. Every staged row reads
`Local only — not sent to ISAAC`, in the open — a privacy state, so it is not tucked into a
tooltip.

## Why no new capability was needed

`POST /api/imports/{id}/sources` already accepts `kind: "reference"` with `filename`,
`reference`, `media_type`, `size_bytes` and `sha256`; stores them verbatim; **fetches nothing**;
and records `parse_state: "no_content_path"`. A browser supplies `File.name`, `File.size` and
`File.type` **as part of the selection** — no read involved. So: no route added, no capability
added, no governance boundary moved. `POST /api/uploads` remains an unconditional 403 and nothing
here calls it.

## Measured in real Chromium, against a real backend

Every transport was instrumented **before** the picker was touched (`window.fetch` and
`XMLHttpRequest.prototype.open` wrapped to record URL, method and body).

| act | requests observed |
|---|---|
| choosing two real files (`scan_0012.mac`, `run_log.xlsx`) | **`[]` — none** |
| computing a checksum on one | **`[]` — none** |
| `Record as source` | `POST /api/imports/{id}/sources` + a `GET` refresh |

The POST body was inspected: it carries `kind`, `filename`, `reference`, `media_type`,
`size_bytes`, `sha256`. **A probe for the file's actual content in any request body returned
`false`.**

Rendered rows, read out of the DOM:

```
scan_0012.mac   37 bytes · text/plain                  Local only — not sent to ISAAC
run_log.xlsx    4.0 KB · application/vnd.ms-excel      Local only — not sent to ISAAC
```

Each row offers `Compute checksum`, `Record as source`, and a remove control with the accessible
name `Remove <filename> from this list`.

## The checksum is real, and it is still not "verified"

The browser computed `7d0c1a9202b93185…`. Recomputed independently with
`shasum -a 256` over the same bytes: **`7d0c1a9202b93185…` — identical.** So it is a genuine
digest and not a placeholder.

**It is nonetheless never called verified**, and that distinction is the route's own: `sha256` is
checked for SHAPE only and is *"never computed"* server-side, and no surface may describe it as
verified, checked or matched. A digest computed in the reader's tab is still the caller's claim
about bytes the server never saw. The copy says *"computed in your browser"*; a test bans
`verified`, `checked against`, `matches the file` and `confirmed` from the rendered output.

**The checksum is opt-in per file**, because it is the only thing here that reads a file. Two
reasons: computing on selection would make the panel's own default claim false for every row, and
`file.arrayBuffer()` reads the WHOLE file — silently pulling a raw beamline dataset into the tab
for a digest nobody asked for is a performance defect dressed as provenance.

## Server state afterwards

```
sources: 1
  filename    : scan_0012.mac
  kind        : reference
  media_type  : text/plain
  size_bytes  : 37
  sha256      : 7d0c1a9202b9318510509c718574a58d054fe6051621aa161bcee0100b1470a6
  parse_state : no_content_path
```

`no_content_path` is the honest state: ISAAC has not opened the file, so the entry cannot
contribute a parsed statement, and the panel's disclosure says exactly that.

## The guards, reconciled rather than deleted

| guard | before | after |
|---|---|---|
| `historical-import.test.tsx` §1 | the screen renders **no** file input | the picker **exists**, the disclosure is on screen and outside any `<details>`, and no upload machinery is declared |
| `upload-claim-parity.test.tsx` census | **exactly two** named files declare a file input | **exactly three** named, with the third asserted to reach bytes *and* to have no API client, no `fetch`, no `XMLHttpRequest`, no `FormData` |
| `HelpPanel` copy + `help-claim-parity` | *"only two controls read a file you pick"* | three named, **and** the third asserted to state that it sends nothing |

§1's subject moved from *"the affordance cannot exist"* to *"the affordance exists and cannot do
harm"* — a **stronger** claim: the old assertion passed on a build with no feature; the new one
cannot pass on a build that lies about one. No guard was deleted and no polarity was inverted.

## What this does NOT claim

* **No file's CONTENT ever reaches ISAAC**, so this is not an ingestion path and no parser runs on
  a staged file. `parse_state: no_content_path` is on every such entry.
* **Nothing about real BL15-2 data.** No corpus exists here, and `§5` forbids designing a parser
  against zero examples.
* **Nothing hosted.** `/krish` sits behind an Authentik edge this environment cannot authenticate
  to; hosted QA remains `PENDING (Krish)`.
* **Nothing about narrow widths or 200% zoom** — no CDP method drives true zoom, and
  `resize_window` does not move the rendered viewport.
