# BL15-2 historical import — domain questions for Angel

> **THIS PACKET IS PREPARED, NOT SENT.** Sending it is the project owner's act, and this
> repository cannot witness delivery. If a future session needs to know whether Angel has
> seen it, **only Krish can say** — the repository records the preparation, never the
> delivery. Do not read a later commit touching this file as evidence that it was sent,
> and do not record any question below as answered without a dated attribution.

**What this is.** The project owner supplied a real SSRL BL15-2 beamtime archive on
2026-09-16. It has been measured
([`docs/evidence/bl15-2-corpus-characterization-2026-09-16.md`](evidence/bl15-2-corpus-characterization-2026-09-16.md))
and walked against the official ISAAC v1.05 schema
([`docs/bl15-2-schema-mapping-analysis-2026-09-16.md`](bl15-2-schema-mapping-analysis-2026-09-16.md)).
Of the **45** concepts the corpus states, the registry (`apps/api/isaac_api/bl15/mapping.py`)
resolves **6** deterministically or by a named rule, finds **no official field at all** for
**24**, finds **1** blocked by this build, and leaves **14** needing a domain owner. **This
packet is those 14, and nothing else.**

**No measured or preparation value is quoted anywhere below** — no energy, no
concentration, no mass, no pH figure, no stage coordinate, and no verbatim note prose.
Every question cites a filename or a structure, because those are what the owner already
quoted in the authorizing brief. Nothing here asks Angel to look at a spectrum.

**One deliberate exception, named rather than left for a reader to find:** §1's reaction
question refers to the reaction class the beamtime studied, in paraphrase. It is not a
measured value, and the question is **unanswerable without it** — choosing between the
schema's `OER`, `water_splitting` and `surface_oxidation` requires knowing which reaction
was run. It is also addressed to the scientist who performed the work, so withholding
their own subject from them would buy nothing.

*(~~No scientific value is quoted anywhere below.~~ — the original wording, struck
2026-09-16 after an independent review found a flow rate in the sibling analysis document
under the same claim. "Scientific value" was too broad to be true and too vague to check;
the enumerated form above is both.)*

---

# ADDED 2026-09-23 — ONE NEW QUESTION, Q21, AND IT IS OPEN

**Q21. Which acquisition quantities are expected to VARY from scan to scan within one
measurement, and which are one value for the whole measurement?** The build must decide,
for every concept a scan states, whether two scans stating different values is normal (each
scan keeps its own reading) or a disagreement a scientist must resolve. Candidates:
counting time (`#T`), emission energy, the energy grid of a `gscan`, the `#S` scan command,
detector column names (`#L`), motor positions (`#P`), and the acquisition timestamp (`#D`).

*→ A list, per quantity: "varies per scan" or "one per measurement". **Until it is answered
the build treats every one of them as one per measurement except four it can justify
structurally** — each scan export's own file index (`acquisition_target`), the several
columns a `#L` line lists (`detector_column`), the several motors a `#P` line lists
(`motor_position`), and the tokens of a file's name (`unknown_token`)* — `bl15.mapping.
RULE_CARDINALITY` v2. *The first version also declared counting time, emission energy, the
energy grid and the scan command per scan; an independent review on 2026-09-23 measured
that a macro's planned value and the header's recorded value for the SAME, only scan then
read as variation instead of a conflict, and those four were reverted pending this answer.*

*(Numbered in THIS packet's sequence, Q1–Q20 before it. The Dean packets use their own
numbering, and their `Q21` is a different question.)*

---

# RECONCILED 2026-09-22 — ANGEL ANSWERED FIVE MORE, AND WITHDREW `DEC-43`'S 298 K

**Read this section first; the 2026-09-17 reconciliation below is preserved unedited as the
state it described.** Of that section's eight remaining Angel questions, **five now have a
disposition and three (Q6, Q7, Q8) are still open.** None of the five closed by writing a
value: each closed with a *rule about what happens when a source is silent or sources
disagree*, and the build now implements each rule.

| source | what it is | what a reader can verify |
|---|---|---|
| **Angel, relayed by the project owner 2026-09-22** | domain-owner answers A–F, below | **nothing in-repo.** An owner relay of a domain owner's words — the evidentiary class `DEC-47` records. No transcript is committed; only Krish can confirm the relay, and only Angel the content. Every registry row it moved carries this attribution (`bl15/mapping.py`'s `ANGEL_2026_09_22`) |
| **Temperature-convention research, 2026-09-22** | the check Angel asked for ("look at published work / NIST") | [`docs/evidence/temperature-convention-research-2026-09-22.md`](evidence/temperature-convention-research-2026-09-22.md) — secondary sources, retrieval disclosed in the note itself |

## The six answers, as the build now implements them

| | Angel's answer (paraphrased) | What the build does |
|---|---|---|
| **A** | Missing data stays missing; the user updates it later. | Nothing is defaulted, derived or proposed for an unstated field. This is the rule that closes Q9 and the QC half of Q14. |
| **B** | Do not assume 298 K; "room temperature" could be 293 K; check the literature. | **`DEC-43` is SUPERSEDED** (struck, not deleted, in `bl15/nominal.py`, the mapping registry and the decision register). No temperature is inserted or proposed automatically. The words "room temperature"/"RT" are kept **verbatim** as a new `temperature_statement` concept at placement level 4 and never converted to a number. A numeric **nominal** value may only come from a reviewed, versioned profile rule that names its convention (NTP-style 293.15 K or SATP-style 298.15 K), labelled nominal/inferred, never measured, and requiring confirmation. **No such rule is enabled.** |
| **C** | `vortDT` is generally the HERFD Vortex channel; in dual-element work `vortDT`/`vortDT2` may belong to different elements and one can be empty. | **Q11 → conditionally resolved.** A per-Run, evidence-based selector (`bl15/signals.py`) suggests a primary channel only when exactly one candidate channel carries live signal and one element is established; otherwise it leaves the Run unresolved and says why. The domain note is never a tie-breaker. The liveness thresholds are measured and recorded with their basis. A dual-element mapping is representable and can be confirmed as a reviewed rule. The selection never writes a record field. |
| **D** | Does not recall whether the two File-32 acquisitions are two conditions or a typo. | **Q16 → domain owner does not know; conflict permanently preserved.** Both acquisitions keep distinct durable identities (source path + content digest, never the legacy number alone), become distinct Runs, and are re-found by identity on a re-run even if their labels collide. A resolution choosing one is **refused** (`resolution_forbidden`). The notes' support for one reading is shown as evidence, not truth. |
| **E** | Asked ISAAC to brainstorm source precedence. | **Q15 → policy adopted, with a non-authoritative recommendation.** No universal hierarchy. Every disagreement carries four layers — *Source fact · Normalized reading · Suggested resolution · Scientist-confirmed resolution*. ISAAC may suggest a resolution only from independent evidence (a repeated pattern across ≥3 contiguous units, the final notes, the neighbouring sequence), labelled non-authoritative; a macro and a header that agree count once. A scientist's confirmation is recorded as a reviewed rule; for a record field it still goes forward as a **proposal**, whose acceptance keeps its `409 human_actor_required` gate. |
| **F** | Does not know what "QC" would mean here. | **Q14 → intentionally left missing.** `measurement.qc.status` is never written from notes. Every free-text `Notes` cell is kept verbatim as a **Data Quality Note** bound to its file number, and can be captured as a run note; nothing parses it. |

## Question-by-question, for the five that moved

| Q | Was (2026-09-17) | Now (2026-09-22) |
|---|---|---|
| **Q9** | PARTIAL — still needs Angel for the JK samples | **INTENTIONALLY LEFT MISSING** (answer A). Where a source names RHE it is preserved verbatim as evidence; no `rhe_basis` member is written or proposed for any group |
| **Q11** | NARROWED — still needs Angel | **CONDITIONALLY RESOLVED** (answer C) — a per-Run selector, not a fixed column |
| **Q14** | STILL NEEDS ANGEL | **INTENTIONALLY LEFT MISSING** (answer F) — Data Quality Notes instead of a QC verdict |
| **Q15** | STILL NEEDS ANGEL | **POLICY ADOPTED WITH A NON-AUTHORITATIVE RECOMMENDATION** (answer E). `DEC-42` (a document disagreeing with itself) is unchanged and separate |
| **Q16** | NARROWED — still needs Angel | **DOMAIN OWNER DOES NOT KNOW — CONFLICT PERMANENTLY PRESERVED** (answer D) |

**Still open, and NOT addressed by the 2026-09-22 reply: Q6 (environment member), Q7
(reaction member), Q8 (JK cell type).** Per answer A, each field stays missing until Angel or
a scientist supplies it. Silence on them is not assent.

## Counts — re-measured, not reduced

The registry grew rather than shrank, because answers B and the operator correction each
introduced a concept that had been folded into another one:

| | 2026-09-17 | 2026-09-22 |
|---|---:|---:|
| concepts in the registry (`bl15/mapping.py`) | 45 | **47** (`temperature_statement`, `contributor_statement` added) |
| `needs_domain_review` rows | 15 | **17** — the two new concepts are placement questions nobody has answered, so they are counted, not hidden |
| open domain questions | 8 | **3** (Q6, Q7, Q8) |

A closed question does **not** move its registry row to `deterministic`: none of the five
answers made a value derivable. Re-derive with `apps/api/tests/test_bl15_mapping.py` and
`test_bl15_placement_hierarchy.py`, which pin these figures.

## The operator is provenance, not a convention

A correction the owner made alongside Angel's answers: the profile formerly called
`ssrl_bl152_angel` described a **filename convention**, not a person. It is now
`ssrl_bl152_herfd_echem_naming` ("SSRL BL15-2 HERFD electrochemistry filename convention
v1"), with `ssrl_bl152_angel` kept as an alias so persisted sessions still resolve. People a
notes file names on a labelled line (`Operator:`, `Measured by:`, `Run by:`, `Performed by:`,
`Prepared by:`, `Contributor(s):` — rule `bl15.notes.contributor_statement.v1`) are recorded as
**provenance** on the units their section covers — never as the basis for choosing how to read a file. The full model is
[`docs/historical-import-semantics-2026-09-22.md`](historical-import-semantics-2026-09-22.md).

---

# RECONCILED 2026-09-17 — 12 OF THE 20 QUESTIONS BELOW ARE CLOSED

**Read this section instead of §1 for what is still being asked.** §1 is preserved
unedited underneath, because a question that turned out to be answerable is evidence
about how the corpus reads, and deleting it would hide that.

**Three things closed these twelve**, and each is attributed because the evidentiary
classes are different:

| source | what it is | what a reader can verify |
|---|---|---|
| **Angel, relayed by the project owner 2026-09-17** | domain-owner confirmation of the filename convention | **nothing in-repo.** An owner instruction relayed in-session, the same class `CLAUDE.md` §15 records for Dean's answers. Only Krish can confirm it was given |
| **The beamtime document** | `250411 BL 15 IrOx NP HERFD acid base.docx`, read in full on 2026-09-17 — 639 extracted lines, 14 tables | the file itself; extraction is `zipfile` + the WordprocessingML namespace, no dependency |
| **Project-owner decision** | `ISAAC_PRODUCT_DECISIONS.md` §B4 | the register row |

**A correction to this packet's own preamble, first.** It says *"leaves **14** needing a
domain owner. This packet is those 14, and nothing else."* **There are twenty numbered
questions below, and the registry today has fifteen `needs_domain_review` rows.** Neither
figure matched the body even when written: several questions (Q15, Q16, Q17) are about
CONFLICTS and CLASSIFICATION rather than about a registry row, so they never corresponded
to one. The honest statement is: **20 questions, 15 registry rows, and they are different
sets.**

## What Angel confirmed

The filename convention, in full:

```text
runNo_sample/electrodeNo_sampleName_loading_electrolyte_gas_condition_pH_flowRate_filter_Potential
```

**This is a vocabulary for the Angel-style BL15-2 profile, not a positional grammar and
not a universal convention.** The parser stays profile-based and tolerant: filenames still
omit tokens, reorder them, spell potentials two ways and contain at least one typo. What
changed is that the MEANINGS are now domain-confirmed for this profile.

## Question-by-question

| Q | Subject | Disposition |
|---|---|---|
| **Q1** | second token = sample/electrode instance | **ANSWERED BY ANGEL.** Explicitly confirmed. Stop asking |
| **Q2** | Experiment-level vs Run-level | **RESOLVED BY PRODUCT DECISION** (`DEC-40`): inheritance + explicit Run overrides, never duplication |
| **Q3** | `sample.material.name` per stem | **ANSWERED BY DOCUMENT.** Every sample section names its electrode label and medium; the material itself is stated in the opening scope |
| **Q4** | `sample.material.provenance` | **ANSWERED BY DOCUMENT.** The JK samples name their preparer; Samples 7–8 give a full deposition recipe |
| **Q5** | `acid`/`base` → electrolyte name + concentration | **ANSWERED BY DOCUMENT**, with a conflict resolved by `DEC-42`: each sample section names its own electrolyte, and the broad *"in ALL experiments…"* sentence is contradicted by the document's own acid sample AND by Samples 7–8. Sample-specific evidence wins; the broad claim is preserved as a superseded shared-context candidate |
| **Q6** | `context.environment` | **PARTIAL.** The dry/`AsIs` acquisitions are stated as such by the document. The member for the electrochemical acquisitions **STILL NEEDS ANGEL** — one word |
| **Q7** | `context.electrochemistry.reaction` | **NARROWED — STILL NEEDS ANGEL.** The document names the reaction studied, in prose; three enum members remain compatible and choosing between them is a scientific call |
| **Q8** | `cell_type` per group | **PARTIAL.** Samples 7–8 are explicitly a flow cell. The JK cell's enum member **STILL NEEDS ANGEL** |
| **Q9** | reference basis | **PARTIAL, and this is the one the corpus most clearly cannot settle.** Samples 7–8 name RHE explicitly, with a measured offset against a reference RHE. Every JK table row says only *"vs reference"* and the equipment list says only *"Reference electrode"*. **STILL NEEDS ANGEL** for the JK samples |
| **Q10** | where the `E-chem Procedure` rows go | **RESOLVED BY PRODUCT DECISION** (`DEC-41`): the baseline-plus-extended-context hierarchy places them. Whether the `Notes` column should drive QC state is Q14 and is separate |
| **Q11** | primary `.dat` channel | **NARROWED — STILL NEEDS ANGEL.** The document names the normalisation pairs it used, which rules out most columns but does not identify one of the several vortex-derived columns as THE HERFD signal |
| **Q12** | expand the scan-grid literal into values? | **RESOLVED BY EXISTING RULE.** Expanding a segmented grid into a value series is this repository computing a scientific quantity, which `CLAUDE.md` §5 forbids. The literal is preserved as extended context. **No longer an Angel question** |
| **Q13** | element / absorption edge | **RESOLVED.** "Is the schema really silent" was answered by measurement — the walk covers all declared paths and there is no native field. `DEC-41` now gives them a structured home, so the question is closed rather than merely unanswerable |
| **Q14** | is `qc.status` derivable from the notes? | **STILL NEEDS ANGEL.** The document's `Notes` column contains real quality judgements; whether they may drive a QC state automatically is exactly the question |
| **Q15** | source precedence when three sources disagree | **STILL NEEDS ANGEL** |
| **Q16** | duplicate legacy number `32` | **NARROWED BY THE DOCUMENT — see below.** **STILL NEEDS ANGEL**, but a much smaller question |
| **Q17** | standards / alignment → Runs? | **RESOLVED BY PRODUCT DECISION.** The build already treats them as units that are not run candidates, which is the behaviour this question was asking about |
| **Q18** | loading vs thickness | **ANSWERED BY DOCUMENT: they are TWO concepts.** The thin-film samples state a deposition time and a thickness; the nanoparticle samples state a weight loading. Placement is `DEC-41` |
| **Q19** | `system.configuration` vs `series[].conditions` | **RESOLVED BY PRODUCT DECISION** (`DEC-41`'s hierarchy) |
| **Q20** | which fields are intentionally custom Run conditions | **RESOLVED BY PRODUCT DECISION** (`DEC-41`) |

## File 32 — the stale wording is retired

~~"Two duplicate 32 files."~~ **They are not duplicates**, and that phrasing is withdrawn
wherever it appears. The corpus holds two distinct acquisitions:

```text
32_03_JK2_base_after1400Cycling_filter20_1500mV
32_03_JK2_base_after1500Cycling_filter20_1500mV
```

**The beamtime document's Sample 3 table settles which one the final log describes.** Its
step 10 carries File Number **32** and records the condition as **after 1500 mV cycling**, at a
potential matching the `1500mV` token already present in both filenames.

**And the absence is stronger than that one table.** The string `1400` occurs **zero times in the
whole document**. That is not because the document names a single cycling voltage — the same
sample's earlier steps record a *different, lower* cycling voltage — so **1400 specifically
appears nowhere**, while the value in the surviving filename does. `after1500Cycling` matches the
final log; `after1400Cycling` matches nothing in it.

*Disclosure boundary applied here, per the characterization document's §0: the two filenames are
reproduced because the authorizing brief quoted them verbatim, and the `1500` figure is one of
their own tokens. The document's procedure prose and the other cycling value are **withheld** —
they are note text and an instrument value not otherwise disclosed, which §0 places outside what
may be reproduced. The structural fact is stated instead, and it is the whole of the evidence.*

**That narrows the question; it does not answer it.** What remains for Angel:

1. Was `runNo = 32` **deliberately reused** for two acquisitions under different cycling
   conditions?
2. Or is the `after1400Cycling` file an **earlier or mislabelled** source superseded by the
   final log?
3. Is `runNo` **normally unique**, or may it legitimately repeat when conditions differ?

**Until Angel answers, both acquisitions and the disagreement are preserved. Neither is
overwritten, and neither is preferred.** Note that (3) is the question that decides whether
the legacy number may ever be a stable scientist-facing identifier.

## The remaining Angel set — eight, of which five were predicted

**Q6** (environment member) · **Q7** (reaction member) · **Q8** (JK cell type) ·
**Q9** (JK reference electrode/scale) · **Q11** (primary HERFD channel) ·
**Q14** (QC from free-text notes) · **Q15** (source precedence) · **Q16** (runNo 32 reuse).

Every one is a scientific judgement the corpus does not state. **None is a mapping
question any more** — the mapping policy is settled by `DEC-41`.

---

---

## 0. How to answer, and why the questions are shaped this way

**Almost every question below is "which named option", not "what should we do".** That is
deliberate: the official schema turns out to carry closed enums for nearly all of these, so
an answer is **one word**, it is auditable afterwards, and it cannot be misread. Where a
question has no enum, it says so.

**"I don't know" and "leave it out" are complete answers** and are what the no-guessing rule
(`CLAUDE.md` §5) expects when a source does not state something. Two of the schema's own
enums exist for exactly that, which is the subject of §3.1.

**What an answer moves, concretely:** one row of the mapping registry, from
`needs_domain_review` to `deterministic` or `normalized`. It does **not** make a record
exportable — see §2 for three reasons unrelated to anything Angel can decide.

---

## 1. The questions

### Sample identity and structure

**Q1. Does the second numeric token always mean the sample/electrode instance?**
`03_01_JK3_acid_…` through `10_01_JK3_acid_…` all carry `01`; `11_02_JK2_base_…` through
`22_02_…` all carry `02`. Measured over all 94 acquisitions the second token yields **10
groups with contiguous, non-overlapping legacy-number ranges** (8/12/13/13/12/11/12/5/4
measurements, plus 2 files with no group token at all — legacy 1 and 2).
*→ If yes, it maps to `sample.sample_id`. **This question was nearly dropped and was
deliberately kept**: the ranges being contiguous is strong corroboration of the notes' own
`Sample N … File Number` sections, and corroboration is not proof — a different meaning
could produce contiguous ranges too.*

**Q2. Which naming concepts are Experiment-level and which are Run-level?**
Within group `01`, eight acquisitions share `01_JK3_acid` and differ only in cycling state
and potential. So `sample name`, `sample/electrode number` and `electrolyte` look
Experiment-level while `potential`, `filter` and `cycling state` look Run-level — but the
`AsIs`/`NoElectrolyte` acquisitions in group `07` break that for `electrolyte`.
*→ No enum. A list per concept is the useful form.*

**Q3. Which `sample.material.name` does each sample stem correspond to?**
The filenames carry `JK3`, `JK2`, `JK1`, `JK1C`, `IrO2`, `IrTiO2`. `sample.material.name` is
a free-text string, so the question is whether these stems ARE the material name, whether
they are internal sample codes with a material name behind them, or both.
*→ No enum.*

**Q4. What is `sample.material.provenance` for these samples, if the notes' preparation
section is not it?** The notes carry a preparation section; whether it is provenance in the
schema's sense is a judgement.
*→ No enum. "Nothing in this corpus states it" is a complete answer.*

### Electrochemistry

**Q5. `acid` / `base` → electrolyte: which `name`, and is `concentration_M` answerable?**
`context.electrochemistry.electrolyte` requires **BOTH** `name` (string) and
`concentration_M` (number) — so `acid` alone satisfies neither. The notes state a
concentration for Sample 1's medium, and separately contain a broad sentence beginning
*"In ALL experiments we used …"* — naming one alkaline electrolyte and a concentration —
sitting **above** the acid sample's own section, which its own preparation section
contradicts.
*→ Two sub-answers: the `name` per sample group, and whether the concentration may be taken
from the broad sentence at all. **If not, say so** — the field then stays absent and the
conflict is preserved rather than resolved.*

**Q6. `context.environment` — which member, and does it differ per group?**
Enum: **`operando` · `in_situ` · `ex_situ` · `in_silico`**. XAS under applied potential in an
electrochemical cell is defensibly either of the first two; `71_07_IrTiO2_0p5nm_AsIs_NoElectrolyte`
is plainly a different one.
*→ One word, possibly two (one for the electrochemical acquisitions, one for the `AsIs`/dry
ones).*

**Q7. `context.electrochemistry.reaction` — which member?**
Enum includes **`OER` · `water_splitting` · `surface_oxidation`** (15 members in all). The
notes name water oxidation and the oxidation state of the catalyst; three members fit and the
corpus does not choose.
*→ One word.*

**Q8. `cell_type` — is it per sample group rather than per beamtime?**
Enum includes **`three_electrode` · `flow_cell`** (10 members). The notes describe a
three-electrode arrangement for the `JK` samples and a flowing configuration for the
`IrTiO2` ones, which would make this a per-group fact rather than a beamtime one.
*→ Confirm per-group or per-beamtime, plus the member for each.*

**Q9. For the later `IrTiO2`/`IrO2` samples the notes DO name RHE — is
`reported_as_RHE` the right `rhe_basis`, and does it cover the whole group or only the
acquisitions the notes name?**
Group `07` (`71_07_IrTiO2_0p5nm_AsIs_NoElectrolyte`, `79_07_IrTiO2_0p5nm_filter0_2000mV`).
`context.electrochemistry.potential_vs_RHE.rhe_basis`'s enum includes **`measured_direct` ·
`derived_calibrated` · `reported_as_RHE` · `derived_nominal`**.
*→ **This is the narrowed remnant of a question that was mostly DROPPED — see §3.1.** For
every other group the schema answers it and Angel need not.*

**Q10. `context.electrochemistry.notes` — do the notes' `E-chem Procedure` rows belong
there?** The notes' flattened table carries `Step / File Number / E-chem Procedure / Notes`
columns per sample.
*→ Yes/no, plus whether the `Notes` column is `measurement.qc.notes` instead.*

### Instrument and acquisition

**Q11. Which `.dat` column is the `primary_signal`?**
The scan exports carry **39** columns; the observed names include `I1`, `I2`, `vortDT` and
`spear`. `measurement.series[].channels[].role`'s enum is **`primary_signal` ·
`measured_response` · `simulated_observable` · `derived_signal` · `auxiliary_signal` ·
`control_readback` · `quality_monitor`**, and the column set plainly spans several of them.
*→ One column name per role, or at minimum which column is the HERFD signal.*

**Q12. Is the `#S gscan` literal the `independent_variables[].values` the schema wants, or a
recipe for producing them?** `Ir_XAS.mac` carries `XAS_MAIN_GRID` as a segmented literal
(start/stop/step triples) rather than as a list of energies, and the per-scan `#S` line
repeats a `gscan` invocation.
*→ No enum. The question is whether a segmented grid may be expanded into values, which
would be this repository computing a scientific quantity.*

**Q13. `element` and the absorption edge — does the schema really have nowhere for them, or
are we looking in the wrong place?** `readme.txt` states the element for the whole beamtime
and `Ir_XAS.mac`'s `def IrL3_xas` names the edge. The registry currently finds **no official
field** for either, and `CLAUDE.md` §5 already treats absorbing element and edge as
implicit/sidecar-only for the XANES path.
*→ Confirm "nowhere native" or name the path.*

**Q14. `measurement.qc.status` — is it derivable from the notes at all?**
Enum: **`valid` · `compromised` · `failed` · `pending`**. The notes' `Notes` column carries
free-text remarks per file number.
*→ If the remarks cannot be classified without reading the spectra, say so: the field then
stays absent and the remarks are preserved as source evidence.*

### Conflicts the corpus produced, which only a person can rule on

**Q15. For the `29`–`32` family, three sources disagree. Which reading is authoritative —
or should none of them be chosen?**
Measured: **four consecutive files** in group `03` each declare `beforeCycling` on their own
internal `#F` line while their filenames read `after1500Cycling`; and the macro that declared
them names a third variant (`beforeCycling` for 29, `after1400Cycling` for 30 and 31). Four
files making the identical substitution is a **systematic rename after acquisition**, not a
typo. The same shape appears in the `44`–`46` family, where a macro declared
`…filter20_1500mV` and the acquired file reads `…filter35_newSpots_1200mV`.
*→ Three options: the filename, the header, the macro, or **"preserve all three and choose
none"**, which is what the reconstruction does today. Note a plausible-sounding "trust the
header, it is closer to the instrument" rule would be **wrong** for these four if the rename
was the correction.*

**Q16. Two distinct acquisitions carry legacy number `32`. Is one a re-acquisition of the
other, a mislabel, or two different measurements — and does the legacy number identify a
MEASUREMENT or a FILE?**
`32_03_JK2_base_after1400Cycling_filter20_1500mV` and
`32_03_JK2_base_after1500Cycling_filter20_1500mV`; their `#E` epochs are ~25 minutes apart.
Across the corpus there are **91 distinct legacy numbers over 94 acquisitions, range 1–91
with no gaps**, and exactly one number carried by more than one file.
*→ This decides whether the legacy number may be a stable scientist-facing identifier at
all.*

**Q17. Which of `01_IrO2_oldPellet_f35`, `IrO2_5wpc_pellet_transmission` and `alignment`
should become Runs?** These are the reference/standard/alignment acquisitions. They are also
the two measurements with **zero scan children** plus the one extensionless alignment file.
*→ **Only the "become a Run" half of this question is live.** The "or a referenced asset"
half is closed by a build boundary, not by Angel — see §2.1.*

### Loading, thickness, and the extension namespace

**Q18. How should loading and thickness be represented — and are they one concept or two?**
`71_07_IrTiO2_0p5nm_…` and `..._2nm_…` look like overlayer thicknesses; `IrO2_5wpc_…` and
`..._0p2wtpc_…` look like weight loadings. **Two different physical quantities sharing one
filename slot**, and the schema has a natural home for neither (`sample.composition` is an
object, `sample.geometry` exists, and there is no thickness field).
*→ Name a path, or confirm this is a schema request rather than a mapping.*

**Q19. `system.configuration` — do the filter index, the emission energy and the
`readme.txt` spectrometer/monochromator values belong there, or in
`measurement.series[].conditions`? BOTH HALVES OF THE SITUATION MATTER AND ARE STATED
TOGETHER:**

- **The schema names that namespace itself**, describing `system.configuration` as *"THE
  designated open extension namespace: instrument/station/beamline-specific configuration
  that does not generalize across facilities (slits, pass energies, GC columns, channel IDs,
  logbook fields…)"*. A vortex slit width and a filter index are precisely that, so there IS
  a natural home.
- **AND it is not settled and not writable today.** `CLAUDE.md` §15 records the six
  `system.configuration.*` fields as **`unclassified`, verified**, with Angel's
  classification **separately outstanding**, and **no write route in this build accepts
  them**. `measurement.series[].conditions` — *"Operating conditions specific to this series
  when they differ from context"* — is the schema-legal alternative for the per-measurement
  ones.

*→ Answer the placement question (`system.configuration` vs `series[].conditions`) **without
pre-empting the six-field classification**, which is its own outstanding item. A slice must
not treat either half as settled.*

**Q20. Which historical fields are intentionally custom Run conditions — i.e. things you
want carried as beamline-specific conditions rather than mapped to a general field?**
Candidates from the corpus: `filter` / `ffilter35`, emission energy, `newSpots`, `step05`,
`dry`, `NoElectrolyte`, the `_again` repeat marker.
*→ A list. Anything not on it stays as source evidence with no official path, which is a
first-class outcome and not a gap.*

---

## 2. Boundaries, stated as boundaries rather than as questions

**These are NOT questions.** Asking them would spend Angel's attention on things no answer
can move, which is why they are separated out.

### 2.1 `assets[]` is unreachable in this build

`assets[]` requires `asset_id`, `content_role`, `uri` **and `sha256`** — all four. The enum
has exactly the right roles for this corpus (`raw_data_pointer` for the SPEC and `.dat`
files, `reduction_product` for `MERGE/`, `calibration_reference` for the calibration foil).
But `historical_import` states that **no digest is ever computed, not even for a file it does
read**. So **no historical source can become an official `assets[]` entry in this build** —
not for want of a mapping, but because a required field would have to be fabricated.

*Consequence: Q17 has only one live half.* Whether the standards become **Runs** is Angel's;
whether they become **referenced assets** is closed regardless of his answer.

### 2.2 `context.temperature_K` is required and the corpus states no temperature anywhere

`context`'s own `required` list is `["environment", "temperature_K"]`. Measured: **no
temperature appears in `readme.txt`, in the notes, or in any SPEC or `.dat` header.** So a
candidate carrying a `context` block is incomplete by the schema's own rule.

**298 must not be defaulted in.** This is a blocker to surface to a scientist, not a gap to
close, and it is one of three reasons a candidate Run from this corpus cannot be
export-complete no matter what Angel answers (the others being `record_type: evidence`
requiring `descriptors`, which no historical source provides, and §2.1).

### 2.3 Cycling state has no schema field at all — and that is a SCHEMA REQUEST, not a classification

`beforeCycling`, `after1200mVCycling`, `after1500Cycling`, `after1stCycling` appear across
most of the 94 acquisitions and are **the corpus's single most important experimental
variable**: within group `01`, eight acquisitions differ from one another essentially by
this and the potential. The official schema has **no field for it**. Candidate homes are
`measurement.series[].conditions`, or prose in `timestamps.revision_note` /
`measurement.qc.notes`.

**No path may be invented** (`CLAUDE.md` §5), and requesting one is **upstream's decision,
not ours** (`CLAUDE.md` §1) — so this is not Angel's classification call. It is recorded here
as **the strongest argument this corpus produces for a schema request**, stated separately
from the questions so it is not mistaken for one.

---

## 3. Candidate questions DROPPED, because deterministic evidence already answers them

The authorizing brief offered eight candidate questions as a starting point. **Three of them
are answered by the corpus or by the schema and have been dropped or narrowed**, and a
further eight obvious-looking questions were checked and dropped for the same reason. Listing
them is part of the ask: a packet that asked all of them would waste the reader's attention
and would imply the repository had not looked.

### 3.1 The flagship drop — "when only a potential magnitude is encoded, what reference basis may be assumed?"

**The schema answers this, and its answer is: none, and here is the vocabulary for saying
so.**

- `context.electrochemistry.potential_scale`'s six members (`RHE`, `SHE`, `Ag/AgCl`, `SCE`,
  `Hg/HgO`, `Hg/HgSO4`) are **each a specific claim, and there is no "unknown" member** — so
  the honest action on an unstated basis is to **leave the field absent**, not to pick one.
- `context.electrochemistry.potential_vs_RHE.rhe_basis` carries **`not_reported`** and
  **`not_convertible_no_reference_offset`** verbatim, and `value_V` is nullable. So *"no RHE
  value, and here is why"* is a **complete, valid record**.

**The schema anticipated exactly this corpus's central gap**, which is worth saying plainly:
a magnitude with no scale is the **correct** mapping here, not an incomplete one. What
survives as a real question is only the narrower Q9 — the group whose notes DO name RHE.

### 3.2 The other dropped candidates, each with what answers it

| Dropped question | What answers it |
|---|---|
| Is this XAS or HERFD-XAS? | The notes title names HERFD and `system.technique`'s enum contains **`HERFD-XAS` verbatim**; `Ir_XAS.mac` defines `IrL3_xas`. Deterministic. |
| Experimental or computational? | `system.domain`'s enum has two members and the corpus is measured, not computed. Deterministic. |
| Does one `.mac` correspond to one Run? | **No, measured:** 156 `newfile` declarations across 60 macro files, up to 8 in one, and 4 declaring none. One-macro-one-Run would have produced 60 Runs for 95 declared measurements and made four non-measurements into measurements. |
| Does one `.dat` correspond to one Run? | **No, measured:** 908 `.dat` files under 94 measurement units, 0–233 each. One-scan-one-Run would invent ~814 measurements nobody performed. |
| Is the copy inside each `*_dir` a second independent source? | **No, measured:** it is **byte-identical** to its root acquisition file — 96 duplicate-content groups over 193 files. Both are kept; neither counts as a second witness. |
| Which acquisition does a `*_dir` belong to? | **Measured:** all **94** `*_dir` directories have a matching root stem, **zero orphans**. |
| Is `ffilter35` a different kind of filter? | **No** — a doubled prefix. The literal is preserved verbatim and the normalised reading (filter 35) sits beside it with its rule named. A normalisation, not a domain call. |
| What is the acquisition timestamp? | SPEC `#E` (Unix epoch) per acquisition, plus `#D`. Deterministic by a named rule — **and the two are not reconciled**: if `#E` and `#D` disagree, both are read and the disagreement is a conflict. |
| What are the counting time, scan count, emission energy and filter for a measurement? | `Ir_XAS.mac` documents a four-argument signature and the `run*.mac` files call it, so these are **read** from the macro text rather than judged. (Which `.dat` COLUMN is the signal is a different question and is Q11.) |
| Can the extension tell a macro from an acquisition? | **No, measured:** `run29` has no extension and is a macro; `alignment` and `IrO2_5wpc_pellet_transmission` have no extension and are SPEC acquisitions. Classification is content-led (first line). |

---

## 4. What happens to each answer

Each answer moves one row of `apps/api/isaac_api/bl15/mapping.py` from
`needs_domain_review` to `deterministic` or `normalized`, and the change is visible in the
evaluation harness's mapping-coverage breakdown
(`apps/api/isaac_api/bl15/evaluate.py`). Three things that do **not** change:

1. **No answer makes a record exportable.** See §2.2.
2. **`needs_domain_review` is a first-class outcome, not a backlog.** The harness excludes it
   from every pass/fail ratio, precisely so that an unanswered question never reads as a
   defect and never creates pressure to guess.
3. **Nothing is written into a record from an answer.** The reconstruction produces
   **reviewable candidates** that a scientist accepts or rejects; deterministic ISAAC
   validation remains the only authority on validity (`CLAUDE.md` §1).

**If an answer is "I don't know" or "leave it out", that is recorded as the answer** and the
field stays absent — which the schema supports and which §5's no-guessing rule requires.
