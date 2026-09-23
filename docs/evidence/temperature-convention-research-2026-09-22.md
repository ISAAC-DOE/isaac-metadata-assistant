# Room-temperature conventions — targeted research, 2026-09-22

**Why this exists.** Angel (domain owner) reconsidered `DEC-43`'s nominal 298 K for the BL15-2
profile: leaving missing data empty may be safest, 293 K may be more common as "RT", and he asked
that published work / NIST be double-checked. This note records what was checked, at what quality,
and the product consequence. It is research, not a decision; the decision is recorded in
`ISAAC_PRODUCT_DECISIONS.md`.

## Distinct concepts that must not be conflated

| Concept | Value | Authority | Retrieval quality this session |
|---|---|---|---|
| **Standard temperature (STP, IUPAC)** | 273.15 K (0 °C), 10⁵ Pa | IUPAC Gold Book, "STP" (S06036) and "standard conditions for gases" (S05910) | Gold Book pages returned **HTTP 403** to the fetcher; value confirmed through search-result extracts of those pages. **Primary page not read directly.** |
| **Standard ambient temperature and pressure (SATP)** | 298.15 K (25 °C), 100 kPa | IUPAC recommendation (thermodynamic reference state; Green Book usage) | Secondary sources only (search extracts). A *reference state for tabulating thermodynamic data*, **not** a statement about any laboratory's temperature. |
| **Normal temperature and pressure (NTP, as used by NIST)** | 293.15 K (20 °C), 101.325 kPa | NIST usage, widely cited | Secondary sources only; **no NIST primary page retrieved**. |
| **Standard reference temperature for dimensional metrology (ISO 1)** | 20 °C | ISO 1; history in NIST *J. Res.* 112(1), 2007 | PDF located on nvlpubs.nist.gov but not machine-readable in this environment. |
| **"Room temperature"** | no single authoritative number | Dictionaries: ~20 °C / 293 K (OED "conventionally taken as about 20 °C"), 20–22 °C (American Heritage); pharmacopeias give ranges (USP controlled room temperature 20–25 °C; Ph. Eur. 15–25 °C); physical-chemistry calculations variously assume 20 °C, 25 °C or 300 K | Secondary (encyclopedic summary of cited primaries). |

## Conclusion

- **Both 293 K and 298 K are real conventions, and they answer different questions.** 298.15 K is
  a thermodynamic *standard ambient* reference state; 293.15 K is the NIST/ISO-style *normal/reference*
  temperature and the dictionary sense of "room temperature". Neither is evidence of what an
  unrecorded experiment's temperature was.
- Angel's instinct that "RT" more commonly means ~293 K is consistent with the dictionary and
  NIST/ISO usage; the earlier 298 K choice is consistent with SATP. **The research does not license
  picking either as a fill value.**

## Product consequence (binding regardless of the research outcome, per the owner)

1. Corpus states no temperature → `context.temperature_K` stays **missing**, displayed as
   `Temperature ○ Not recorded`. No automatic insert, **no automatic proposal**.
2. A source that literally says "room temperature" / "RT" is preserved **verbatim** in provenance /
   Extended Context. It is not converted.
3. A numeric nominal value may be **offered** only when (i) a reviewed profile rule explicitly
   permits it **and names which convention it adopts** (e.g. 293.15 K NTP-style vs 298.15 K
   SATP-style), (ii) the UI labels it nominal/inferred, (iii) the scientist must confirm it, and
   (iv) it is never labelled measured. No such rule is enabled by default.
4. `DEC-43` is **superseded**, not deleted.

## Sources consulted

- IUPAC Gold Book — STP: https://goldbook.iupac.org/terms/view/S06036 (403 to fetcher)
- IUPAC Gold Book — standard conditions for gases: https://goldbook.iupac.org/terms/view/S05910 (403 to fetcher)
- Standard temperature and pressure (encyclopedic summary citing IUPAC/NIST): https://en.wikipedia.org/wiki/Standard_temperature_and_pressure
- Room temperature (encyclopedic summary citing OED, American Heritage, USP, Ph. Eur.): https://en.wikipedia.org/wiki/Room_temperature
- NIST J. Res. 112(1) 2007, history of the 20 °C reference temperature: https://nvlpubs.nist.gov/nistpubs/jres/112/1/V112.N01.A01.pdf
