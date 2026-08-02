# Identity-Observation Probe (TEMPORARY)

**Created:** 2026-08-01 · **Status:** TEMPORARY — this is a measurement instrument, not a feature,
and it is intended to be **deleted** in a follow-up PR once the observation has been recorded.
**Active by default in every environment**, behind a kill switch that can disable it without a code
deploy (§5). An earlier revision of this file said "disabled by default"; that described a design
that was deliberately inverted before shipping, and the inversion — a real weakening — is recorded
in §5 and in [`docs/identity-trust-contract.md`](identity-trust-contract.md) §8 rather than papered
over. **Because the window opens by itself, discipline is the only thing that keeps it short.**

> **If you are reading this more than a few weeks after the date above and the probe is still in the
> tree, that is the bug.** Go to [Removal plan](#removal-plan).

---

## 1. Why it exists

[`docs/identity-trust-contract.md`](identity-trust-contract.md) establishes, with commands anyone can
re-run, that:

- the backend reads **zero** identity headers (§1.1, §1.2);
- the Authentik proxy outpost fronting `/krish` is configured in `ISAAC-DOE/isaac-k8`, **a repository
  this working tree cannot see** (§1.6, §7);
- there is no trusted-proxy allowlist, no header-stripping middleware, and `ISAAC_UI_API_KEY` is unset
  in production, so **the moment one line of code reads an identity header, spoofing is live and
  unmitigated** (§1.5, §2).

Four of that document's open questions cannot be answered by reading code, because the answer is not
in this repository:

| Question | What the probe measures |
|---|---|
| **Q1** — which headers does the outpost inject? | which allowlisted candidates are `present` |
| **Q2** — which are actually forwarded by the ingress annotation? | same signal, observed at the pod |
| **Q3** — does the ingress strip a client-supplied copy? | `client_canary_survived` |
| **Q4** — can anything reach the pod bypassing the ingress? | **not measurable here** — see §6 |

**Q15** asks whether a presence-only probe may be temporarily enabled to answer Q1–Q3. This is that
probe. It ships **active**, with a kill switch rather than an enabler — see §5 for why that inversion
was chosen, and for the risk it accepts.

---

## 2. The contract

### Operation

```
POST {base}/api/runtime/identity/probe
```

Read-only. Changes no record, no workspace, no file, and no in-process state. Opens no connection.
**Published in `/api/openapi`, `/docs`, and Settings → API Docs — deliberately** (see §5). An earlier
revision of this line said "Not published"; that was reversed, because obscurity was never the control
here (the control is that the operation cannot emit a value) and an unadvertised diagnostic endpoint is
precisely the kind nobody remembers to delete.

### Request body

```json
{ "canary": "some-string-you-choose" }
```

- `canary` is optional; `{}` is a valid body, and so is omitting the body entirely.
- Bounded at **128 characters**. Longer returns `400 {"error": "canary_too_long", …}` and echoes
  nothing.
- Extra fields are rejected (`extra="forbid"`).
- The canary is never stored, never logged, and never echoed in a probe report.

### Response — frozen top-level keys

```json
{
  "status": "ok",
  "probe_contract_version": 1,
  "app_commit": "5bb25a8…",
  "generated_at": "2026-08-01T00:00:00Z",
  "edge_path_expectation": "…fixed constant…",
  "claims": [ … ],
  "limitations": [ … fixed constants … ]
}
```

`status` is one of `ok` · `disabled` · `error`. **All three shapes carry exactly these seven keys** —
the projection is built key-by-key from a frozen allowlist, so a field cannot be added to the payload
by an edit somewhere downstream.

### Response — frozen per-claim keys

```json
{
  "claim": "groups",
  "header": "X-authentik-groups",
  "present": true,
  "shape": "list",
  "consumed_by_isaac": false,
  "client_canary_survived": false
}
```

Both the top-level and the per-claim key sets are frozen. Freezing the *nested* set is not
belt-and-braces: it is the specific lesson of **G3** (`CLAUDE.md` §15), where only the top-level keys
of the database-reconnaissance response were frozen and five record-derived aggregates consequently
shipped inside a nested block without tripping a single contract test.

### The candidate allowlist — seven names, fixed at compile time

| `claim` | header | evidence for including it | PII-bearing |
|---|---|---|---|
| `username` | `X-authentik-username` | read by the ISAAC portal (`ISAAC-DOE/isaac-ai-ready-record`) | yes |
| `uid` | `X-authentik-uid` | Authentik proxy-outpost convention | yes |
| `email` | `X-authentik-email` | Authentik proxy-outpost convention | yes |
| `display_name` | `X-authentik-name` | Authentik proxy-outpost convention | yes |
| `groups` | `X-authentik-groups` | Authentik proxy-outpost convention | yes |
| `entitlements` | `X-authentik-entitlements` | Authentik proxy-outpost convention | yes |
| `edge_marker` | `X-Isaac-Edge` | bespoke marker read by the ISAAC portal | no |

This list is a **hypothesis under test**, not a claim about the deployment. A candidate reported
`absent` is a real observation.

It is a **projection, never a filter.** The handler calls `request.headers.getlist(name)` once per
entry and with no other name; nothing in the module iterates the request's header mapping. A filter
could leak the name of a header it rejected; a projection structurally cannot.

`consumed_by_isaac` is `false` for all seven. That is **data, not a guess** — it records the state
verified in trust-contract §1.2 (the backend reads exactly `authorization`, `If-None-Match`,
`If-Match`, `X-Filename`). Reading a header to report its presence is not consumption: nothing
branches on it, no record is stamped, no authorization decision uses it.

### `shape` — one of five

| shape | meaning |
|---|---|
| `absent` | the header did not arrive |
| `malformed` | present but empty, whitespace-only, containing a C0/C1/DEL control character, or not UTF-8 decodable |
| `duplicate` | the header arrived more than once |
| `list` | a single value joined by `,` or `\|` (Authentik has used both for `groups`) |
| `scalar` | anything else |

**Precedence, highest first: `malformed` > `duplicate` > `list` > `scalar`.** Published as a constant
(`identity_probe.SHAPE_PRECEDENCE`) and tested case-by-case, because every ordering here is a
judgement:

- **malformed wins** because an undecodable or control-bearing value means the *reading* is
  untrustworthy, which matters more than how many copies arrived.
- **duplicate outranks list** because two headers is a *transport* fact — something appended a second
  copy — whereas a separator is a *provider formatting* fact.

**`duplicate` alone does not prove the ingress appended anything.** A client can send two copies
itself, and under the §5 operating procedure it does. The shape reports only that more than one copy
arrived; attributing the second copy to the edge requires knowing what the caller sent, which is the
operator's knowledge and not this response's.

### `client_canary_survived`

`true` when the canary in the request body is byte-identical (`hmac.compare_digest`) to **any whole
value** of that header **or to any separator-delimited segment of one**. Every copy is compared, not
just the first, so a duplicate in which only one copy is the client's forgery is still detected. That
is the **append** case, and it is the most dangerous answer to Q3: the ingress added its own value but
left the forged one in place.

**The segment comparison is load-bearing, not thoroughness.** An intermediary that *coalesces* instead
of duplicating — joining the client's forged copy and the injected value into one header with `,` or
`|` — is the same append attack in a different shape, and joining on exactly those separators is what
Authentik does to `groups` and `entitlements`. Without the segment check the probe would report
`false` there, the operator would record "the ingress strips forged headers" as the answer to Q3, and
a later authorization slice would be built on a survival that actually happened. That is the wrong
answer in the unsafe direction, delivered with full confidence.

The result is a bare boolean — no position, no index, no count, and no indication of which of the two
comparisons matched. Detecting more does not disclose more.

**What `false` does and does not mean.** It means the canary was not found in either of those two
forms. A canary that arrived re-encoded, case-folded, quoted, or truncated is still reported `false`,
so `false` is "not found", never "provably removed".

### What can never appear, anywhere

In the response, in a log line, in an error, in test output — nothing below is ever **emitted**:

any header **value** or fragment of one; any username, email, uid, subject, display name, group name,
or entitlement name; any **hash, digest, fingerprint, length, or character count** of a value; any
token, cookie, session id, or `Authorization` header; any raw header mapping; any **non-allowlisted
header name**; any count of headers received (that number fingerprints the ingress configuration).

> **One deliberate exception to "nothing derived from a value", named rather than hidden:
> `client_canary_survived` is a containment oracle.** Nothing obliges the caller to have planted the
> string it compares, so an authenticated caller can *confirm by guessing* — one bit per request, per
> header — that their own `groups` header contains `admin`. **The oracle spans all seven candidates,
> not only `groups`**: a specific guessed username, email or uid can be confirmed the same way.
> `groups` is called out because it is the practical case — segment matching reduces the guess to one
> segment from a two-entry vocabulary this repository already publishes, whereas guessing a whole
> username is a much weaker attack.
>
> **It is bounded, and the bound is what makes the trade acceptable:** the disclosure is to an
> authenticated caller about **their own** headers; CORS sets `allow_credentials=False`, so no
> cross-origin page can make a victim's browser send its session and read the answer; and an in-cluster
> caller bypassing the edge supplies its own headers and learns nothing. The alternative — whole-value
> matching only — reports "the ingress strips forged headers" when it does not, which is a wrong answer
> in the unsafe direction on the probe's central question. Detection was chosen over the oracle-free
> variant, knowingly.

This is enforced mechanically, not by review. `identity_probe.assert_only_constant_strings` runs over
the built payload on the success path and requires **every string to be drawn from a closed set of
compile-time constants** — statuses, shapes, claim names, the seven header names, the fixed
`edge_path_expectation`, and the fixed `limitations` — with exactly two exemptions, `app_commit` and
`generated_at`, neither of which is request-derived and both of which are already published
unauthenticated on `GET /api/health`.

That is deliberately a **different and stronger** kind of check than `db_recon.scan_for_leaks`. A
substring scan proves that *specific known-bad text* is absent; it cannot prove that an unanticipated
derivative of a header is absent, because the scanner has to know what to look for. The
constant-universe check inverts the burden: nothing but known-good text may be present.

---

## 3. Why POST and not GET

**The canary must travel in the request body.**

`Dockerfile:50` starts uvicorn with default access logging, which writes the request line — **including
the query string** — to the pod's stdout. A canary passed as `?canary=…` would therefore be persisted
into container logs, which are a different retention and access domain than an HTTP response body.
The request body is not written to the access log.

A header would be worse still: the canary has to be sent *in* the candidate headers as the forgery
under test, so the body is the only channel that can carry the expected value without putting a second
copy somewhere that gets logged.

Consequence: `GET` on this path returns `405`, and there is a test that says so.

---

## 4. Why `consistent_with_previous_request` is deliberately omitted

An obvious third question is *"does the same caller get the same identity across requests?"* It is
**not implemented, on purpose.**

Answering it requires retaining a per-value fingerprint between requests and comparing a later request
against it. That artefact is a **cross-request correlation surface**:

- it is a stored, stable derivative of a person's identity claim;
- it makes the pod capable of **linking two requests to one human**, which nothing in this application
  can do today;
- it converts a stateless presence check into a miniature session store — with no retention policy, no
  owner, and no decision from Dean behind it.

Storing a *hash* instead of the value does not fix it. A hash of a low-entropy claim — a SLAC username
— is trivially reversible by enumeration, and a stable hash is exactly the correlation key the
objection is about.

**There is no substitute, and this file previously claimed there was.** It said the question "can be
answered with zero stored state: send two requests and compare the two responses by eye." **That is
false.** The response carries no identity — only presence, shape and a canary boolean — so two
responses from the same caller are identical *by construction*, and would stay identical if the
caller's identity changed completely between them. There is a test that proves exactly this
(`test_two_identical_requests_are_indistinguishable`), which is what makes the old claim impossible.

Comparing two responses by eye tells you whether the **header contract** is stable. **Identity
consistency is not answerable by this probe at all**, deliberately — it is a question about the
provider's configuration, and it belongs to Q5.

`identity_probe.py` says this in its module docstring, and `test_identity_probe.py` asserts the field
is absent from the payload — so a future slice that adds it has to delete a test that explains why it
should not.

---

## 5. The switch, and the risk it does not cover

### The switch

```
ISAAC_IDENTITY_PROBE=0     # also accepts false / no / off, case-insensitive
```

**It is a KILL SWITCH, default ON — not an enabler, default OFF.** This is a deliberate, recorded
inversion of what `docs/identity-trust-contract.md` §8 originally specified, and it is a real
weakening of that design rather than a technicality.

The reason: turning a default-OFF switch on means editing `isaac-k8`, which Dean owns, and the
instruction authorising this probe explicitly required no new secret and no infrastructure change. A
gate nobody is permitted to open does not produce a safer probe — it produces one that can never
observe anything, leaving the header contract unmeasured indefinitely. What the switch is kept for is
the property that is genuinely worth having: **it can be turned off without a code deploy.**

An unrecognised value — including the empty string — is treated as ON. A manifest typo must not
silently mute the probe, because a muted probe returns an empty `claims` list, which reads exactly
like the substantive finding "no identity header reaches the application": a wrong answer wearing the
costume of a real one.

Set falsy, the handler returns `status: "disabled"` with the same seven frozen keys, an empty
`claims` list, and **reads no header at all**: the switch is checked before any header is touched.

**"Reads nothing" is not "responds identically to everything."** The route still exists and FastAPI
still parses the body before the handler runs, so with the switch off an extra body field still returns
FastAPI's `422` and `GET` still returns `405`. An over-long canary returns `disabled` `200` rather than
`400`, because the switch is checked before the length bound. None of this discloses a header — the
disabled envelope is built from constants — but a reader should not expect the path to go dark.

This is trust-contract §8's "Safety requirements" bullet — **implemented with its polarity inverted.**
With `ISAAC_UI_API_KEY` unset in the hosted deployment, this switch is the only *deployment-level* gate
the probe has, and because it defaults ON it is **not gating anything until someone sets it.** State
that plainly rather than inheriting §8's "which is exactly why it defaults off", which described the
design that was not built. What actually carries the safety burden is therefore not this switch but the
three controls in the next section: the operation cannot emit a value, ISAAC consumes none of these
headers, and removal is a committed follow-up.

### The risk, stated not minimised

The probe is an **ingress-configuration oracle.** The set of candidates it reports `present` is
precisely the list of header names worth forging, for an attacker who can reach the pod's Service
directly and thereby bypass Authentik entirely (trust-contract §2). Presence is also itself a weak
claim about a person: `groups: true` on a deployment admitting only two groups narrows the caller.

**And since segment matching landed, it is also a containment oracle over all seven candidates** (§2):
an authenticated caller can confirm by guessing, one bit per request, that their own `groups` header
contains `admin` — against a published two-entry vocabulary — and equally a specific guessed username,
email or uid, though those are far weaker attacks for want of a short guess list. **That is now part of what shipping default-ON means**, and
it belongs in this paragraph rather than only in §2, because this is where the polarity trade is
argued. It does not change the verdict — the disclosure is own-headers-only and not cross-origin
readable — but it is a second reason the observation window should be short and the endpoint removed
rather than kept.

Additional mitigations already in place:

- **Deliberately IS in the published API contract.** An earlier revision hid the route with
  `include_in_schema=False`. That was reversed: it appears in `/api/openapi`, `/docs`, and the in-app
  Settings → API Docs screen. Hiding it would not have been a security control — obscurity never is,
  and the only real control here is that the operation cannot emit a value — while an unadvertised
  diagnostic endpoint is precisely the kind that is never removed. Visibility is what makes §7
  enforceable, and `CLAUDE.md`'s lifecycle rule forbids leaving an undocumented diagnostic endpoint in
  production.
- **Behind the API key when one is configured.** The probe is *not* on `ApiKeyAuthMiddleware`'s
  open-path list; only `GET {base}/api/health` and `OPTIONS` are. A test pins that.

### Intended operating procedure

1. Nothing to enable — the probe observes on the next image roll. **This is the cost of the
   inverted polarity: the window opens automatically, so it is your discipline, not a gate, that
   keeps it short.**
2. Issue **one** request with a canary planted in all seven candidate headers. **Choose the canary
   carefully — two ways to get a wrong answer:**
   - **Make it separator-free.** `_split_segments` splits the *header value*, never the canary, so a
     canary containing `,` or `|` can only ever match a whole value and the coalescing case goes
     undetected — the exact failure the segment matching exists to prevent.
   - **Make it distinctive and obviously non-real.** A canary that happens to equal a value the edge
     genuinely injects (`admin`, `researcher`, your own username) reports `survived: true` when nothing
     was forged. That fails in the alarm direction, so it is safe, but it is still a wrong answer to Q3.
   A random token such as `canary-7f3a9c` satisfies both.
3. Record the response verbatim in `docs/identity-trust-contract.md` as the answer to Q1–Q3.
4. Open the removal PR (§7) **immediately** — do not wait for the answers to be acted on.
5. If removal must be delayed for any reason, set `ISAAC_IDENTITY_PROBE=0` in the meantime. That
   needs no code deploy, which is the whole point of retaining the switch.

---

## 6. What this endpoint does NOT prove

**It proves nothing about in-cluster reachability, and it does not establish that any caller was
authenticated.**

`edge_path_expectation` is a fixed constant in every response saying exactly that. The reasons:

- `docs/deployment.md:32-34` — pod probes hit the container port **directly**, bypassing the ingress
  and its auth.
- Trust-contract §2 — **any workload in the cluster** that can reach the `metadata-assistant` Service
  does the same, and `ISAAC_UI_API_KEY` is unset in production.
- The pod binds `0.0.0.0`; uvicorn runs without `--proxy-headers` or `--forwarded-allow-ips`; there is
  no `TrustedHostMiddleware` and no header-stripping middleware anywhere.

So a response saying `present: true` means *this request carried that header*. It does **not** mean the
request came through Authentik, and it cannot answer **Q4**, which only Dean can.

Two more honest limits, also stated in every response's `limitations`:

- A candidate reported `absent` may be absent because the provider does not emit it, because the
  ingress `auth-response-headers` annotation does not forward it, or because this request never
  traversed the edge. **The probe cannot distinguish those three causes.**
- `client_canary_survived: false` does not prove the ingress strips forged headers on *every* path.
  `true` proves it does not strip them on *this* one.
- It is a **point-in-time** observation. The provider's header set and the ingress annotation live in
  `isaac-k8` and can change with no signal to this repository.

---

## 7. Removal plan

This probe is temporary. It should be removed in a dedicated follow-up PR as soon as the observation in
§5 has been made and recorded — or immediately, if the observation is never authorized.

**Trigger:** the Q1–Q3 answers are written into `docs/identity-trust-contract.md`, **or** Dean declines
Q15.

**Exactly what to delete:**

1. `apps/api/isaac_api/identity_probe.py` — delete the file.
2. `apps/api/tests/test_identity_probe.py` — delete the file.
3. `apps/api/isaac_api/routes.py`:
   - the `from . import identity_probe` line in the import block;
   - the whole `# --- 23. TEMPORARY identity-observation probe …` section at the end of the file:
     `_identity_log`, `_IDENTITY_PROBE_ENV`, `_IDENTITY_PROBE_FALSY`, `_identity_probe_enabled`,
     `IdentityProbeRequest`, and `post_identity_probe`.
4. `docs/identity-probe.md` — this file.
5. **Five pinned contracts MUST be reverted** — this is a mandatory step, not a footnote, because the
   probe is *published* in the API contract rather than hidden. Three in
   `apps/api/tests/test_about_and_openapi.py`: the operation count `37 -> 36`, the
   `("/api/runtime/identity/probe", "post")` row in `EXPECTED_RESPONSE_CODES`, and the
   `IdentityProbeRequest` entry in `EXPECTED_COMPONENT_SCHEMAS`. Two in the frontend, which mirrors the
   real generated document: delete the `POST /api/runtime/identity/probe` entry from
   `REAL_CONTRACT_DESCRIPTIONS` in `apps/web/src/test/apiFixtures.ts`, and in
   `apps/web/src/__tests__/settings-api.test.tsx` return the three pins to **21,270 characters / 36
   operations / 44 post-lead paragraphs**. Those exact numbers are recorded in that test's comment. If
   reverting the probe does not land on them precisely, something else was removed too.
6. **Regenerate the memory snapshot** — `apps/api/isaac_api/routes.py` is one of the 200 entries in the
   served-content manifest (`CLAUDE.md` §17). Adding the probe caused drift; removing it will too. Use
   the two-artifact command in §17, with `--detail-out`.
7. `docs/identity-trust-contract.md` §1.1 — return the permitted-set guard from its four-file form to
   the three-file doc set, and eventually to the original `0 matches` once this file goes too. §1.1
   states this in place; it is repeated here so the removal checklist is self-contained.
8. `CLAUDE.md` §11 — delete the line recording this live temporary endpoint.
9. The deployment switch `ISAAC_IDENTITY_PROBE`, **only if someone set it** to disable the probe. It
   is unset by default, so in the normal case there is nothing to clean up in `isaac-k8`. A stale env
   var pointing at a deleted route is harmless.

**Nothing beyond items 1–9 needs touching.** (An earlier revision of this file put the heading
"Nothing else needs touching" *above* five mandatory edits, so a reader who trusted the heading and
skimmed the numbered list would have left five contract pins wrong. The mandatory work is now numbered
with everything else.) In particular:

- **No frontend source change**, because no frontend code calls this route — only the test mirror of
  the generated contract is affected.
- **The truth path is untouched** by both the addition and the removal: no file under `src/`,
  `schema/`, or the validator/export/audit core was involved.

**What must NOT happen instead of removal:** promoting the probe into a permanent endpoint, or
extending it to return a value, a hash, a length, a header count, or a cross-request comparison. Every
one of those is refused for a reason recorded above, and the reasons do not expire when the probe's
usefulness does.
