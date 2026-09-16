# Hosted observation, 2026-09-16 — the deployment is current, and the Settings defect is in it

**Why this exists.** The project owner reported that the hosted Settings screen *"is still js a
wall of text"* and added *"i know u were doing locally cause its not logged in but now it is"*.
That is two claims, and they have different fixes: either the hosted image is **stale** (so the
fix exists and was never rolled out) or the hosted image is **current** (so the fix does not
exist). This document settles which.

**Answer: the deployment is CURRENT, and the defect is in the current code.** A redeploy would
change nothing. The fix is real work, and it is tracked as the Settings density slice.

## How this was observed, and the boundary it respects

Read **read-only, from a browser tab the project owner had already signed in to**, exactly as the
2026-09-13 precedent (`docs/evidence/hosted-observation-2026-09-13.md`). **No credential was
entered by an agent**, no form was submitted, no state was mutated, and no database connection was
opened by anything — these are `GET`s of two already-built pages plus one health route.

`CLAUDE.md` §11 and `docs/krish-manual-verification-checklist.md` both record `/krish` as sitting
behind an Authentik edge that *"this environment cannot authenticate to"*, and every prior session
recorded `HOSTED QA PENDING (Krish)` on that ground. **That remains exactly true of
authentication** — an agent still cannot sign in, and must not. What has changed is only that an
*already-authenticated* tab is readable, which is a different fact and is the one this document
rests on.

**A correction to the URL recorded in my own first attempt:** the host is
`isaac.slac.stanford.edu`, not `ai-isaac.slac.stanford.edu` (the latter is `NXDOMAIN`).

## 1. The deployment is current

`GET https://isaac.slac.stanford.edu/krish/api/health`:

```
"status":"ok", "mode":"synthetic-only",
"commit":"108ba4e44c1a4e7de98c1cdadea805a949dc6c49"
```

Cross-checked locally: `git rev-parse origin/main` → `108ba4e4…`, and
`git rev-list -n1 v0.0.243` → `108ba4e4…`. **Hosted commit == `main` == the newest release tag.**

Unchanged and re-confirmed on the wire, so nothing here may be read as a scope change:
`mode: synthetic-only`; `database.record_display: "closed"` (gate **G2** still closed);
`database.contains_production_derived_records: true`; `mcp.posture: "unmounted"` with `D1`…
`DEFERRED 2026-08-12`.

## 2. The Settings defect, measured on the surface the owner opened

`GET /krish/settings?tab=privacy`, viewport 1510×828. Method:
`document.documentElement.scrollHeight`; prose = `innerText` of every non-empty `<p>`/`<li>`.
**Every `<details>` on every surface below was CLOSED**, so these are *visible* characters.

| surface | scrollHeight | viewport | visible prose chars | paragraphs > 400 chars | longest |
|---|---:|---:|---:|---:|---:|
| **`settings?tab=privacy`** | **2066** | 828 | **9681** | **9 of 14** | **1469** |
| `settings?tab=about` | 828 | 828 | 903 | 0 | 286 |
| `settings?tab=overview` | 1364 | 828 | 427 | 0 | 184 |
| `governance?tab=policy` | 828 | 828 | 1426 | 1 | 542 |

Also on the privacy tab: **12** `.settings-points > li > h3` concepts, **all expanded**, with only
4 `<details>` in the whole document (all closed, holding secondary text).

**So the wall of text is essentially ONE tab.** 2.5 viewports of continuously-scrolling prose with
no disclosure, on a screen whose siblings each fit in one viewport.

## 3. A correction to my own analysis, recorded because it nearly misdirected the fix

Before measuring the rendered page I estimated density by counting string literals ≥60 characters
in the source with comments stripped. That gave `GovernancePage.tsx` **6,104** characters over
4 `<p>` tags with zero disclosures, and I briefed the implementing slice that Governance → Policy
*"should"* get the same treatment.

**That was wrong.** The source count swept in copy belonging to that file's *other* tabs
(`validator`, `schema`), which never render together. Rendered, Governance → Policy is **1,426
characters and fits in one viewport.** The retraction was sent to the implementing slice before it
edited anything.

This is the failure mode `CLAUDE.md` §11 records repeatedly — **a source grep standing in for a
rendered measurement** — and the consequence here would have been a risky restructuring of
honesty-critical governance copy to fix a surface that did not need it. It is recorded rather than
quietly corrected because the near-miss is the useful part.

## 4. What this does NOT establish

- **It is not a hosted QA pass.** Four `GET`s are not the 6-check packet in
  `docs/krish-qa-packet-2026-09-15.md`; every check in that packet that needs a human still needs
  one, and `HOSTED QA PENDING (Krish)` stands for image `v0.0.243` as a whole.
- **It does not reopen gate G2 or G3.** `record_display` reads `closed`; nothing per-record was
  requested or displayed.
- **It says nothing about narrow widths or 200% zoom.** `CLAUDE.md` §11 records that
  `resize_window` reports success while the rendered viewport does not follow, and that no CDP
  method can drive a genuine 200%-zoom check. Both human gates remain OPEN.
- **It does not mean hosted is generally verifiable.** It is readable **while the owner is signed
  in**, in a tab they authenticated. The honest form of the claim is *"read read-only from an
  already-authenticated tab"*, never *"this environment can reach /krish"*.
