# ISAAC Metadata Assistant — Extraction Design (XANES / characterization path)

**Status:** drafted 2026-07-06 · **Scope:** the MVP characterization / XANES path (see
`docs/proposal-v2.md` §7 and `docs/intake.md`). This document is the **Phase 2 design** for how
`/isaac-draft` turns the accepted artifacts into a draft envelope. It defines *who extracts what*,
*how each value is evidenced*, and *where each value lands* — deterministically, without guessing.
It does **not** implement extraction: the parsers land in Phase 3, seamed by the logic-free stubs in
`src/isaac_records/extract/`. The vendored official schema `schema/isaac_record_v1.json` (v1.05) is
the sole authority on record structure; every official path cited here was verified against it (see
§6).

This design stays inside the single XANES / characterization path (`record_type=evidence`,
`record_domain=characterization`) mirrored by `tests/fixtures/official/ex_situ_xanes_cuo2_record.json`
and `tests/fixtures/cuo_xanes_draft.json`. It introduces no new behavior in the truth path
(`official`, `export`, `draft_validator`, `audit`, `cli`); those remain unchanged.

---

## 1. Deterministic vs LLM-assisted split, per artifact type

The governing rule (from `docs/intake.md` §4): **a deterministic parser is preferred as the source
of any value it can supply.** A model is used only for artifacts that exist purely as pixels or prose.
When two artifacts carry the same value, the deterministic source wins and the model read becomes
corroborating (or is skipped).

| Artifact type (intake §2) | Example filename | Extractor | Pulls specifically |
|---|---|---|---|
| Excel metadata sheet `.xlsx` | `mock_campaign.xlsx` | **Deterministic** (openpyxl, Phase 3) | Campaign Info (facility, org, site, beamline, endstation, technique, proposal/session, experimenters, acquired/created UTC); Sample (name, formula, provenance, sample_form, mass fractions, pellet diameter); Configurations (environment, temperature_K, atmosphere, monochromator, spectrometer geometry, detector, incident-energy start/end, n_scans, qc_status) — read cell-by-cell with a sheet/cell locator. |
| Structured export `.csv` / `.json` | `mock_campaign.csv` | **Deterministic** (csv / json parse) | The same `section,field,value,unit,notes` rows as the `.xlsx`; the CSV is the byte-identical stand-in for the sheet. Pulls each `(section,field) → value[,unit]`. |
| Raw file listing `.txt` | `raw_scan_listing.txt` | **Deterministic** (line parse) | Archive root URI (`ssrl-archive://BL15-2/…`), the raw scan file set (→ scan count as corroboration), reduced-product path, notebook path. Provides asset **URIs** and the acquired-window hint only; it never invents a `sha256`. |
| Web-form screenshots `.png` / `.jpg` | `webform_sample_details.png`, `webform_session.png`, `webform_conditions.png` | **LLM-assisted (vision)** | Only what is legible on the form and not already supplied deterministically: session title (technique + beamline), sample fields, and conditions. The plain-text `webform_dump.txt` is the synthetic stand-in that lets the demo exercise this path deterministically. |
| Narrative / protocol PDF | `isaac_narrative.pdf` | **Deterministic text-layer extract where a real text layer exists; LLM-assisted for scanned/image pages** | Free-form context the structured sheets omit (qc rationale, assumptions, processing recipe prose). Text-layer runs local; image pages need a model. |
| Free-text notes | `notes.txt`, `webform_dump.txt` | **Read locally; interpret with the model** | Loose facts a curator typed (endstation, geometry, one-off qc notes). Reading the bytes is local; turning prose into typed fields is the model step. |

**Governance tie-in.** The three deterministic rows never touch a network or a model. The three
LLM-assisted rows are the only place artifact content would reach an external model — gated by the
`docs/intake.md` §3 red lines (free for synthetic data, explicit approval before any real file).

---

## 2. Per-artifact evidence-capture rules

**Evidence is captured at extraction time or the value is not finalized.** A value with no evidence
may only exist as `status: missing` (value `null`) or `status: needs_confirmation`. Every finalized
field carries at least one evidence entry whose `source_type` is one of the values
`models.py` / `draft_validator.py` already accept:
`document | spreadsheet | screenshot | web_form | file_listing | user_confirmation | derivation`.

| Artifact type | `source_type` | `source_file` | `locator` | `quote` |
|---|---|---|---|---|
| Excel `.xlsx` | `spreadsheet` | `examples/mock_campaign.xlsx` | `Sheet '<tab>', cell <A1>` (and/or `Sheet '<tab>', field=<name>`) | verbatim cell text, e.g. `"298 K"` |
| CSV / JSON export | `spreadsheet` | `examples/mock_campaign.csv` | `Sheet '<section>', field=<field>` (CSV rows carry `section,field`) | verbatim `value` cell |
| Raw file listing | `file_listing` | `examples/raw_scan_listing.txt` | `line <n>` and/or the archive path, e.g. `ssrl-archive://BL15-2/2099_run_000/raw/` | the listed path or line text |
| Web-form screenshot | `web_form` (or `screenshot` for a non-form capture) | `examples/webform_sample_details.png` | `<section> → <field>`, e.g. `Sample details → Chemical formula` | the model-read value, e.g. `"CuO2"` |
| Narrative / PDF | `document` | `examples/isaac_narrative.pdf` | `page <n>` or `page <n> → <section>` | verbatim sentence/phrase |
| Free-text notes | `document` (reading) / `screenshot` if captured as image | `examples/notes.txt` | `line <n>` or `<section> → <field>` | verbatim phrase |
| Follow-up answer | `user_confirmation` | — (no file) | — (no locator; use `question` + `answer` + `timestamp`) | — (the answer is in `answer`) |
| Derived value | `derivation` | — | — (no locator; use `rule`) | — (optional supporting `quote`) |

`source_type` values map cleanly onto the extractor set: deterministic rows emit `spreadsheet` /
`file_listing`; vision rows emit `web_form` / `screenshot`; text/PDF rows emit `document`;
`/isaac-complete` answers emit `user_confirmation`; and the two implicit inferences emit `derivation`.

---

## 3. Locator format per `source_type`

Locators must be concrete enough that a human can re-open the source and re-find the value.

| `source_type` | Locator convention | Example |
|---|---|---|
| `spreadsheet` | `Sheet '<tab>', cell <A1>` when the cell address is known; `Sheet '<tab>', field=<name>` when addressing by the label column (CSV/JSON, or a labelled sheet) | `Sheet 'Configurations', cell D14` · `Sheet 'Sample', field=formula` |
| `file_listing` | `line <n>` and/or the archive path being cited | `line 19` · `ssrl-archive://BL15-2/2099_run_000/raw/` |
| `web_form` | `<section> → <field>`, matching the form's on-screen grouping | `Sample details → Chemical formula` |
| `screenshot` | `<region/element> → <field>` (or `title bar` for a caption) | `Session title bar` |
| `document` / PDF | `page <n>` or `page <n> → <section>` | `page 2 → Methods` |
| `user_confirmation` | **no locator** — the evidence carries `question`, `answer`, `timestamp` | (`question`: "Which endstation?", `answer`: "XES") |
| `derivation` | **no locator** — the evidence carries the stated `rule` (and optional `quote`) | (`rule`: "absorbing element = metal in sample.material.formula (CuO2 → Cu)") |

These match the locators already used in `tests/fixtures/cuo_xanes_draft.json` (e.g.
`Sheet 'Campaign Info', cell B2`, `Session title bar`, `first scan mtime`).

---

## 4. Ambiguity and missing-value fallbacks

The extraction path never guesses, never fabricates a value, URI, or `sha256`, and never encodes
absence as a real value. Concretely:

- **Not found anywhere** → `status: missing`, `value: null`, no evidence. (`draft_validator`
  rejects a `missing` field that still carries a value.)
- **Conflicting sources** (two artifacts disagree) → `status: needs_confirmation`, value left as the
  as-read candidate but **not** finalized; cite **both** sources in `evidence[]` so the conflict is
  visible. Resolution is a `/isaac-complete` question, not a model tie-break.
- **Low-confidence model read** (blurry screenshot, ambiguous prose) → `status: needs_confirmation`
  with the model's read as the candidate and its `web_form`/`document` evidence attached.
- **Derived but unverifiable** → stays `needs_confirmation` (or `missing`), never `inferred`, unless a
  stated `derivation` rule exists (`draft_validator` requires a rule for `inferred`).
- **Never fabricate identifiers.** Asset URIs come only from the file listing / user; a `sha256` is
  **never** computed or invented at extraction time — it is a `user_confirmation` blocker (§8), and
  `draft_validator` refuses any asset without one.

`needs_confirmation` and `missing` are non-final statuses: only `verified` and `inferred` export.
Everything unresolved surfaces as a `/isaac-complete` question rather than a silent fill.

---

## 5. Extracted-value → draft-field mapping

Where each value the synthetic artifacts carry lands in the draft envelope. Scalars go to `fields[]`
(keyed by their official dotted path); structured data goes to `series[]`, `assets[]`,
`descriptors_outputs[]`, or `implicit[]`.

| Extracted value (synthetic source) | Draft destination |
|---|---|
| `facility_name` (CSV `Campaign Info`) | `fields["system.facility.facility_name"]` |
| `organization` | `fields["system.facility.organization"]` |
| `site` | `fields["system.facility.site"]` |
| `beamline` | `fields["system.facility.beamline"]` |
| `endstation` | `fields["system.facility.endstation"]` |
| `technique` (`HERFD-XAS`) | `fields["system.technique"]` (+ `fields["system.domain"]` = `experimental`, `inferred` by derivation) |
| `material_name` | `fields["sample.material.name"]` |
| `formula` (`CuO2`) | `fields["sample.material.formula"]` |
| `provenance` | `fields["sample.material.provenance"]` |
| `sample_form` (`pellet`) | `fields["sample.sample_form"]` |
| `CuO2_mass_fraction`, `sucrose_mass_fraction` | `fields["sample.composition.<key>"]` (open composition object) |
| `pellet_diameter_mm` | `fields["sample.geometry.pellet_diameter_mm"]` (open geometry object) |
| `environment` (`ex_situ`) | `fields["context.environment"]` |
| `temperature_K` (`298`) | `fields["context.temperature_K"]` |
| `atmosphere` (`air`) | `fields["context.thermodynamics.atmosphere"]` |
| `spectrometer_geometry` (`Von_Hamos`) | `fields["system.configuration.spectrometer_geometry"]` (open namespace) |
| `monochromator_crystal`, `detector_model` | `fields["system.configuration.<key>"]` (open namespace) |
| `proposal_id`, `session_id`, `n_scans` | `fields["system.configuration.<key>"]` (open namespace; no canonical slot) |
| `acquired_start_utc`, `acquired_end_utc`, `created_utc` | `fields["timestamps.<key>"]` (first-scan mtime also corroborates `acquired_start_utc` from the listing) |
| `lead_experimenter`, `co_experimenter` | `attribution.contributors[]` (name + role) |
| Incident-energy range (`8970–9000 eV`) + n points | `series[]` → `independent_variables[{name:"incident_energy", unit:"eV", values:[…]}]` |
| Reduced/averaged spectrum values | `series[]` → `channels[{role:"primary_signal", …}]` (+ `i0_monitor` as `auxiliary_signal`) |
| Raw scan archive (`ssrl-archive://…/raw.h5`) | `assets[]` entry (`content_role: raw_data_pointer`, `uri`, **sha256 via `user_confirmation`**) |
| Reduced product / notebook paths | `assets[]` entries (`reduction_product`, `processing_script`) |
| `qc_status` (`valid`) | `qc` block → `measurement.qc.status` (+ `qc.evidence` prose) |
| Inflection-point energy + uncertainty | `descriptors_outputs[]` → one descriptor (`xanes_inflection_point_energy`, `kind: absolute`, unit `eV`) |
| Absorbing element (`Cu`), edge (`K`) | `implicit[]` (no schema field — see §6/§7) |

---

## 6. Draft-field → official ISAAC JSON-path mapping (verified)

Draft `fields` **keys ARE** the official dotted JSON-paths by design, so this is a **confirmation**
table. Every non-open, non-implicit path below was resolved against `schema/isaac_record_v1.json` by
walking `properties` (verification output pasted in the commit/report). "Open-namespace" = allowed
but not an enumerated field (parent object has no `additionalProperties: false`).
"Implicit-sidecar-only" = **not a schema field at all**.

| Draft key ( = official path) | Exists in schema? |
|---|---|
| `sample.material.name` | yes |
| `sample.material.formula` | yes |
| `sample.material.provenance` | yes |
| `sample.sample_form` | yes |
| `sample.composition.<key>` | yes — **open** object (`sample.composition`, "open by design") |
| `sample.geometry.pellet_diameter_mm` | yes — **open** object (`sample.geometry`, only `geometric_area_cm2` enumerated) |
| `system.domain` | yes |
| `system.technique` | yes (enum incl. `XAS`, `HERFD-XAS`, …) |
| `system.facility.facility_name` | yes |
| `system.facility.organization` | yes |
| `system.facility.beamline` | yes |
| `system.facility.site` | yes |
| `system.facility.endstation` | yes |
| `system.configuration.<key>` (spectrometer_geometry, monochromator_crystal, detector_model, proposal_id, session_id, n_scans) | **open-namespace** — `system.configuration` is THE designated open extension namespace |
| `context.environment` | yes (enum: operando / in_situ / ex_situ / in_silico) |
| `context.temperature_K` | yes |
| `context.thermodynamics.atmosphere` | yes |
| `timestamps.acquired_start_utc` / `acquired_end_utc` / `created_utc` | yes |
| `measurement.series` / `measurement.qc.status` / `measurement.qc.evidence` | yes (structured blocks) |
| `assets[]` (`asset_id`, `content_role`, `uri`, `sha256`) | yes |
| `descriptors.outputs[]` | yes |
| `links[]` | yes |
| `attribution.contributors[]` | yes |
| `absorbing_element` | **implicit-sidecar-only** — no schema field (`sample.material` is `additionalProperties: false`) |
| `edge` | **implicit-sidecar-only** — no schema field |

The schema-walk confirms `sample.material.absorbing_element` and `sample.material.edge` do **not**
resolve (`sample.material` is a closed object), which is exactly why they must live in `implicit[]`
and never as invented record fields (`test_implicit_inferences_stay_out_of_record` enforces this).

---

## 7. Implicit values in the sidecar, not the record

**Absorbing element** and **edge** are the two facts a XANES scientist expects, yet the official
schema has **no field for either** — confirmed in §6 (both fail to resolve against a closed
`sample.material`). Inventing `sample.material.absorbing_element` would violate
`additionalProperties: false` and export would refuse it.

So they are handled as *implicit inferences*: derived deterministically from
`sample.material.formula` + `system.technique` (e.g. `CuO2` + an XAS technique → absorber `Cu`;
incident-energy window `8970–9000 eV` matching the Cu K-edge (~8979 eV) → edge `K`) and recorded
**only** in the draft `implicit[]` block, each with a `derivation` rule as evidence (see
`tests/fixtures/cuo_xanes_draft.json` → `implicit[]`).

On export, `export.build_sidecar` already writes each `implicit[]` entry to the evidence sidecar
under an `implicit:<about>` key (`implicit:absorbing_element`, `implicit:edge`) carrying `{value,
evidence}`, and `transform` copies structured blocks but **never** emits `implicit[]` into the
official record. This design phase changes none of that code — it only describes it. The net effect:
the two inferences stay fully auditable in `records/<ULID>.evidence.json` without ever entering the
official record, and the sidecar's `implicit:` keys are (by construction) the only sidecar keys that
are **not** literal record JSON-paths (`test_sidecar_dotted_paths_resolve_in_record` skips the
namespaced keys).

---

## 8. What `/isaac-complete` should ask, derived from validators

Questions come **only** from the two validators — never from vague model judgment. For the XANES
path (`record_type=evidence`, `record_domain=characterization`) the concrete question set is:

**(a) From draft no-guessing gaps (`draft_validator.validate_draft`):**

1. Any field left `needs_confirmation` or `missing` that a valid record needs → ask for the value
   and its source (becomes `verified` with `user_confirmation` evidence). *(rule: finalized fields
   need observed/confirmed evidence.)*
2. Any conflicting field (two disagreeing sources) → ask which is correct. *(rule: no silent
   tie-break.)*
3. **Raw-data `uri` + `sha256`** for every asset → asset without `sha256` blocks the draft. *(rule:
   `assets[i]` requires a sha256; never fabricated.)*
4. **Inflection-point descriptor value + its uncertainty** → a descriptor value may not be null.
   *(rule: descriptor value must not be null.)*
5. **Absorbing element / edge derivation** confirmation if the formula/energy inference is
   uncertain → each `implicit[]` entry must cite a source. *(rule: every inference cites a source.)*

**(b) From official conditional requirements (`official.validate_official`, walking the schema's
required blocks + `allOf` for evidence ⇒ characterization):**

6. `record_type` / `record_domain` / `source_type` (top-level required) — usually from `meta`,
   confirmed if absent.
7. **evidence ⇒ `descriptors` required** (`allOf`): the record must carry `descriptors.outputs[]` →
   ask for the inflection-point descriptor if none exists (overlaps 4).
8. **`sample` requires `material` + `sample_form`** → ask for `formula`/`name` and physical form if
   missing.
9. **`system` requires `domain` + `technique`** → ask for the technique (and confirm domain =
   experimental) if missing; endstation/spectrometer geometry are asked here as the beamline
   specifics that populate `system.facility.endstation` and `system.configuration.*`.
10. **`context` requires `environment` + `temperature_K`** → ask for environment (ex_situ/in_situ/…)
    and the sample temperature if missing.
11. **`measurement` requires `series` + `qc`**, and `qc` requires `status` → ask for the
    energy/absorption series and the **qc status** (valid/compromised/failed/pending), plus qc
    evidence when status ≠ valid.
12. **`assets[]` require `asset_id` + `content_role` + `uri` + `sha256`** → the sha256/uri blocker
    (overlaps 3).

Each question maps to a specific validator rule, so the assistant asks exactly the blockers and
nothing more. (Note: the `performance`+electrochemistry `allOf` branches — `galvanostatic ⇒
current_setpoint_mA_cm2`, `potentiostatic ⇒ potential_setpoint_V` — are **out of scope** for the
characterization path and are not asked here.)

---

## 9. Synthetic fixture naming reconciliation (before Phase 3)

The Phase 1 generator (`scripts/make_synthetic_examples.py`, committed copies in
`tests/fixtures/synthetic/`) produces:
`mock_campaign.csv` (and `mock_campaign.xlsx` at runtime once `openpyxl` is available),
`raw_scan_listing.txt`, `webform_dump.txt`.

The hand-written `tests/fixtures/cuo_xanes_draft.json` cites **different illustrative** filenames in
its `source_file`s: `campaign_metadata.xlsx`, `webform_sample_details.png`, `webform_session.png`,
`webform_conditions.png` (only `raw_scan_listing.txt` already matches).

**Recommendation — adopt the generator's names as the single canonical scheme** for Phase 3, so
extraction tests and the draft fixture reference the same artifacts:

| Concept | Canonical (generator) name | Notes |
|---|---|---|
| Campaign metadata sheet | `mock_campaign.xlsx` (deterministic `.csv` twin `mock_campaign.csv`) | replaces `campaign_metadata.xlsx` |
| Web-form capture(s) | `webform_dump.txt` (synthetic text stand-in for the `.png` screenshots) | replaces the three `webform_*.png` names; if separate section screenshots are wanted in Phase 3, name them `webform_dump.txt` sections or `webform_<section>.png` consistently on the generator side |
| Raw scan listing | `raw_scan_listing.txt` | already consistent |

**On `cuo_xanes_draft.json`:** **do not change it in this phase.** Keep it as a standalone
evidence-illustration fixture (its illustrative `.png`/`.xlsx` names document what real
screenshot/spreadsheet evidence looks like, which the text-only synthetic set cannot show). The
recommended Phase-3 action is to **realign its `source_file` names** to the canonical set *at the
point* Phase-3 extraction runs against the generator output — either by regenerating the draft from
the real extractor, or by a one-line rename pass — so the committed draft and the committed synthetic
inputs finally agree. Until then the mismatch is cosmetic (the draft validator checks evidence
*shape*, not that `source_file` exists on disk).

---

## 10. Cross-references

- **Intake / handling constraints:** `docs/intake.md` (accepted types, local-vs-model, red lines).
- **Architecture / field mapping context:** `docs/proposal-v2.md` §3 (draft → record) and §7 (XANES MVP).
- **Record authority:** `schema/isaac_record_v1.json` (v1.05) — verified in §6.
- **Draft envelope + no-guessing rules:** `src/isaac_records/models.py`, `draft_validator.py`.
- **Export / sidecar behavior described (unchanged):** `src/isaac_records/export.py` (`transform`, `build_sidecar`).
- **Phase-2 interface seam (this design's stubs):** `src/isaac_records/extract/__init__.py`.
- **Golden targets:** `tests/fixtures/official/ex_situ_xanes_cuo2_record.json`, `tests/fixtures/cuo_xanes_draft.json`.
