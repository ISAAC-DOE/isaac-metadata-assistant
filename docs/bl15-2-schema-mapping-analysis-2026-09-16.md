# BL15-2 corpus → official ISAAC v1.05 — mapping analysis

**Read the schema, not this document, as the authority** (`CLAUDE.md` §1). Every path below was
read out of `schema/isaac_record_v1.json` on 2026-09-16 by walking `properties`, not recalled;
every enum is quoted from the file. This is the analysis that tells the mapping registry
(`BL15R-010`) which mappings are **deterministic**, which need a **named normalisation**, which
need **Angel**, and which the schema **cannot express at all**. It decides nothing scientific.

**The headline result is better than expected, and it is a finding rather than a convenience: the
schema already contains the vocabulary this corpus needs, including — twice — the vocabulary for
saying that a value is NOT KNOWN.** That matters more than the positive mappings, because the
corpus's central gap is the potential reference basis, and §3 shows the schema anticipated exactly
that gap. So the mapping does not have to guess, and `CLAUDE.md` §5 is satisfiable without leaving
the field empty and uninformative.

## 1. Deterministic — the source states it and one named rule carries it across

| corpus concept | evidence | official path | note |
|---|---|---|---|
| technique | notes title *"HERFD acid base"*; `Ir_XAS.mac`'s `IrL3_xas` | `system.technique` = **`HERFD-XAS`** | The enum contains `HERFD-XAS` verbatim. `XAS` is also present and is the weaker reading; the notes name HERFD, so the stronger one is evidenced. |
| domain | the corpus is measured, not computed | `system.domain` = `experimental` | Enum is `['experimental','computational']`. Both `system.domain` and `system.technique` are already record-level writable (`CLAUDE.md` §11, 2026-08-27). |
| beamline / site | `readme.txt` header `2025-04_Sokaras`; the archive name | `system.facility.beamline`, `system.facility.site`, `system.facility.facility_name` | Free-text strings, no enum. **Do not mint an identifier the corpus does not state** — `bl152-users`/`bl152-staff` are Authentik groups and explicitly not ISAAC identifiers. |
| acquisition start | SPEC `#E` epoch + `#D` date, per acquisition | `timestamps.acquired_start_utc` | `#E` → ISO-8601 UTC is a named rule. **`#E` and `#D` are two statements and are not reconciled** — if they disagree both are read and the disagreement is a conflict. |
| energy grid, scan points | SPEC/`.dat` `#S` `gscan` literal, `#N`, `#L` | `measurement.series[].independent_variables[]` (`name: energy`, `unit: eV`) and `series[].channels[]` | `channels[].role` enum includes `primary_signal`, `quality_monitor`, `control_readback` — the `.dat` column set (`I1`, `I2`, `vortDT`, `spear`) spans all three, and **which column is the primary signal is a domain question** (§4). |
| replicate relationship | `03_…_060mV_filter10` and `04_…_060mV_filter10_again` | `links[].rel = replica_of`, `links[].basis = replicate_preparation` | Both values are in the enums verbatim. The `_again` token is the evidence. |
| same-sample relationship | the shared sample/electrode token (`_02_`) across a legacy-number range | `links[].rel = same_sample_as`, `basis = same_sample_id` | Deterministic **only** if the second token really is the sample instance — which is **domain question 1**. Until answered this is a candidate, not a mapping. |
| calibration reference | `readme.txt` *"calib with Pt Foil"*; the `alignment` acquisition | `links[].rel = calibration_of`, `basis = same_absorber_edge`; or `assets[].content_role = calibration_reference` | See §5 for why the `assets[]` route is blocked. |

## 2. Needs a named normalisation, and the rule is auditable

| concept | raw forms in the corpus | official path | the rule |
|---|---|---|---|
| potential magnitude | `060mV`, `850mV`, `1200mV`, `1p2V`, `1p8V`, `2400mV` | `context.electrochemistry.potential_setpoint_V` (number, volts) | `mV`→V by 1/1000; `p`→decimal point. Both are named rules; the literal is preserved beside the value. |
| control mode | notes: every XAS point is a **chronoamperometry** hold | `context.electrochemistry.control_mode` = `potentiostatic` | The enum has no `chronoamperometry`; `system.technique` does. **`allOf[3]` then makes `potential_setpoint_V` REQUIRED** — so this mapping and the row above it are one decision, not two. |
| filter | `filter10`, `f10`, `filter0`, and the typo **`ffilter35`** | **no schema field** — see §5 | `ffilter35` → 35 by the doubled-prefix rule, literal preserved. The normalisation is valid regardless of where the value lands. |

## 3. The reference basis — where the schema does the honest thing for us

**This is the most important row in the document.** A filename says `850mV` and says **nothing**
about what it is measured against. The notes say *"vs reference"* for the JK samples — naming no
reference — and mention **RHE** only for the later TiO2/IrO2 samples. So for most of this corpus
the basis is genuinely unknown, and §5 of `CLAUDE.md` forbids inventing one.

The schema has vocabulary for exactly this:

- `context.electrochemistry.potential_scale` — enum `['RHE','SHE','Ag/AgCl','SCE','Hg/HgO','Hg/HgSO4']`. **Every member is a specific claim.** There is no "unknown" member, so the honest action is to **leave this field absent**, not to pick one.
- `context.electrochemistry.potential_vs_RHE.rhe_basis` — enum
  `['measured_direct','derived_calibrated','reported_as_RHE','derived_nominal','in_silico_setpoint','not_convertible_no_pH','not_convertible_no_reference_offset','not_reported','not_applicable']`.
  **The last four are the vocabulary for absence**, and two of them describe this corpus exactly:
  **`not_reported`** where the source names no basis at all, and
  **`not_convertible_no_reference_offset`** where a reference is mentioned but its offset is not.
  Note `rhe_basis` is **required within** the `potential_vs_RHE` object, and `value_V` is nullable
  (`['number','null']`) — so the schema permits *"no RHE value, and here is why"* as a complete,
  valid statement. That is the shape to use.

**Consequence for the registry, stated so a later slice does not soften it:** the magnitude and the
basis are two mappings with two different outcomes. Emitting a `potential_setpoint_V` without a
`potential_scale` is not an incomplete mapping — it is the **correct** one, and the registry must
be able to say so rather than reporting it as a gap to be filled.

The same asymmetry applies to pH: `context.electrochemistry.pH` is a number and
`pH_basis` is `['measured','nominal','buffered_assumed']`. The notes state a pH for the TiO2
samples — a **nominal** figure quoted beside a NaOH concentration, not a measurement — so the
basis is evidenced as `nominal` for those and **absent** everywhere else.

## 4. Needs Angel — and the schema makes each of these a *choice between named options*, which is the useful form of the question

Stated as "which enum member" rather than "what should we do", because that is answerable in one
word and is auditable afterwards.

| question | the schema's options | what the corpus says |
|---|---|---|
| `acid` / `base` → electrolyte | `context.electrochemistry.electrolyte` requires **BOTH** `name` (string) and `concentration_M` (number) | The filename says only `acid`/`base`. The notes name an acid with its concentration for Sample 1, and an alkaline electrolyte with its concentration — but that second sentence is the **contradicted broad claim** (*"In ALL experiments…"*, sitting above `Sample 1 JK3 in acid`). So the name is inferable per sample and the concentration is inferable **only from the disputed sentence**. *(Values withheld: this document reproduces filenames, which the owner disclosed, and not measured or preparation values.)* `acid`/`base` alone satisfies neither required field. |
| environment | `['operando','in_situ','ex_situ','in_silico']` | XAS under applied potential in an electrochemical cell. `operando` and `in_situ` are both defensible; the `AsIs`/`dry`/`NoElectrolyte` acquisitions are plainly a different one. |
| reaction | 15 members incl. `OER`, `water_splitting`, `surface_oxidation` | The notes say *"water oxidation"* and *"oxidation state of Iridium catalyst"*. Three members fit; the corpus does not choose. |
| cell type | 10 members incl. `three_electrode`, `flow_cell` | The notes describe a three-electrode cell for the JK samples and a flow cell (~10 ml/min) for TiO2 — so this is **per sample group**, not per beamtime. |
| primary signal channel | `channels[].role` enum7 | The `.dat` files carry 39 columns. Which is the HERFD signal is a domain fact. |
| `temperature_K` | **required** whenever `context` is present, and no enum | **The corpus states no temperature anywhere.** Not in `readme.txt`, not in the notes, not in any header. So a candidate carrying a `context` block is incomplete by the schema's own rule, and **298 must not be defaulted in**. This is a genuine blocker to surface, not a gap to close. |
| loading / thickness | `sample.composition` (object), `sample.geometry` — **no thickness field** | `0p5nm`, `2nm` are Ir overlayer thicknesses; `5wpc`/`0p2wtpc` are weight loadings. Two different quantities sharing one filename slot, and the schema has a natural home for neither. |
| standards → Run or asset? | — | `01_IrO2_oldPellet_f35`, `IrO2_5wpc_pellet_transmission`, `alignment`. |

## 5. The schema cannot express it — and one of these is a hard build boundary

- **`filter`, `emission energy`, and the `readme.txt` spectrometer/monochromator values have no
  schema field.** The schema names their home itself: `system.configuration` is described in the
  file as *"THE designated open extension namespace: instrument/station/beamline-specific
  configuration that does not generalize across facilities (slits, pass energies, GC columns,
  channel IDs, logbook fields…)"*. A spectrometer slit width and a filter index are precisely that.
  **Two cautions, and they pull in opposite directions, so state both:** the namespace is open by
  the schema's own words, *and* `CLAUDE.md` §15 records the six `system.configuration.*` fields as
  `unclassified, verified` with Angel's classification **outstanding** and no write route
  accepting them. So the registry may record `system.configuration` as the **candidate** home and
  must not treat the mapping as settled or as writable today.
  `measurement.series[].conditions` — *"Operating conditions specific to this series when they
  differ from context"* — is the alternative for the per-measurement ones (filter, emission
  energy), and is schema-legal.
- **Cycling state (`beforeCycling`, `after1500Cycling`, `after1stCycling`) has no field.** It is
  the single most important experimental variable in this corpus and the schema has no place for
  it. Candidate homes: `series[].conditions`, or `timestamps.revision_note`/`measurement.qc.notes`
  as prose. **Do not invent a path.** This is the strongest argument in the corpus for a schema
  request, and a schema request is upstream's decision, not ours (`CLAUDE.md` §1).
- **`assets[]` IS BLOCKED, and the reason is mechanical.** `assets[]` requires `asset_id`,
  `content_role`, `uri` **and `sha256`** — all four. The enum has the perfect roles for this corpus
  (`raw_data_pointer` for the SPEC/`.dat` files, `reduction_product` for `MERGE/`,
  `calibration_reference` for the Pt foil). But `historical_import` states that **"No digest is
  ever computed, not even for a file it does read"** (`HIST-001`, ledger). So **no historical source
  can become an official `assets[]` entry in this build** — not for want of a mapping, but because
  a required field would have to be fabricated. That is the correct outcome and it must be reported
  as a named boundary rather than discovered late by a failing export.
- **Legacy run/file number has no field.** It is the corpus's own identifier, not ISAAC's. Keep it
  as source evidence and as the scientist-facing label; do not force it into `record_id`
  (server-minted) or `sample.sample_id` (a sample, not a measurement).

## 6. What follows for the registry

1. Every row above becomes a registry entry with an explicit `mapping_status`:
   `deterministic` · `normalized` · `needs_domain_review` · `not_expressible` · `blocked_by_build`.
   **All five are first-class outcomes.** A registry that only recorded successes would tell a
   scientist nothing about the 40% of this corpus the schema has no home for.
2. **`not_expressible` and `needs_domain_review` must NOT fall back to `system.configuration`
   by default.** That would convert "the schema has nowhere for this" into "we put it in the
   extension namespace", which is a decision disguised as a default.
3. Nothing in §4 may be resolved by this repository. `docs/bl15-2-domain-questions-2026-09-16.md`
   is the packet; it is **prepared, not sent**, and only Krish can say whether it was delivered.
4. A candidate Run assembled from this corpus **cannot be export-complete**, and that is correct:
   `context.temperature_K` is required and unstated, `record_type: evidence` requires `descriptors`
   (`allOf[0]`) which no historical source provides, and `assets[]` is blocked per §5. The
   reconstruction must therefore produce a **reviewable candidate**, never a record that claims to
   be ready — which is what `historical_import` already does by minting proposals rather than
   writing values.
