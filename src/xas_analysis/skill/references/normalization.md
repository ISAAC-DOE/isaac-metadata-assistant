> **Default since 2026-11-11: constrained background** (`bg_decreasing`: c0, c3 >= 0, falling and
> non-negative). The free Victoreen pair (c0, c3 of either sign) nearly cancelled and acted as a
> rising ramp under the post-edge in every campaign (median +4 to +18 % of the step), making edge
> steps 4-14 % too small, by an amount that varied per spectrum. Constrained, HERFD backgrounds come
> out flat at the pre-edge level (c3 at its bound), which agrees with a model-free relative
> normalization of difference spectra to ~0.1 %. Use `bg_decreasing: false` only to reproduce
> earlier results; `victoreen_linear` keeps the free form.

# Normalization (normalize block)

Default `model: victoreen` (mback_xrs): raw = bg + A * mu_McMaster, bg = c0 + c3 (E/E_edge)^-3,
the McMaster unit step locked at the tabulated edge; objective = pre-edge LSQ + post-edge LSQ
+ non-negativity above the edge + post-edge area (weights 10 / 3 / 0.8 / 1). The XANES region
between the windows is not fitted. Output norm = (raw - bg) / A.

Alternatives: `victoreen_linear` (adds (E/E_edge - 1); most robust to curved backgrounds and
short windows, noisier), `poly` (mback, background continuous at the edge, nth [1, 1]).
Never Nth 1/2 (edge-jump noise 4 %, collapses with short windows) and never the legacy
mback_v4 background (independent post polynomial: A_edge unidentified).

Windows: `range: [pre_lo, pre_hi, post_lo, post_hi]`. Default rule (recipe init): pre up to
E_edge - 5..10 eV, post from E_edge + 60 eV to 10 eV before the scan end. Do not start the
post window inside near-edge oscillations (Ir L3: ~11265 eV raised A by 8-21 %).

Uncertainty to report (Ir L3, measured):
- noise: A 1.7 %, white line 3.5-4.4 % (Monte Carlo from per-point errors)
- window choice: A spread 9-15 % (max-min over 11 windows) at normal loading, 16-20 % at
  ~1 % Ir loading; this is the dominant systematic at low loading
- vs Athena: same shape; scale ours/Athena 1.00 (full loading) to 1.13 (~1 % loading)

Zero counts are data: HERFD pre-edges are nearly background-free and read 0 (heavy filters:
the whole pre-edge). Only points no scan covers are dropped (n_kept = 0).

White-line height from max(norm) on noisy data reads high (peak picking): +0.25-0.35 at
signal/noise 20, +0.6-1.0 at 10. Use a smoothed or fitted peak when comparing heights.

## Tender fluorescence (S K, BL4-3): background options
Total/SCA fluorescence below ~3 keV differs from HERFD in two ways, both seen in the
Nov-2025 S K data:
- the pre-edge falls monotonically and steeply (scatter leaking into the Ka window, shrinking
  as E moves away; up to 2x over 50 eV), then a resonant-Raman foot rises ~25 eV before the edge;
- the post-edge IF/I0 RISES with E while the cross-section falls ~30 % (I0 chamber efficiency,
  thick-dilute fluorescence): a multiplicative factor on the step, not an additive background.
Plain Victoreen then bends its background up (c3 < 0), misses the pre-edge (normalized
pre-edge -0.05) and takes part of the step. Model the rise physically. A thin gas I0 counts ~ mu_gas(E) ~ E^-3, so IF/I0 rises as
F = (E/E_edge)^p for the WHOLE signal (p: N2 3.0, He 3.1; more with windows/path); a thick
sample adds a self-absorption factor on the step (IF ~ mu_S / (mu_tot(E) + mu_tot(E_f))):

    normalize: {model: victoreen, bg_decreasing: true, pre_tail: true,
                response_power: 3.0, step_slope: 1,
                range: [pre_lo, <before the foot>, post_lo, post_hi]}

Data / F, then bg = c0 + c3 x^-3 + a exp(-(E - pre_lo)/tau) (all >= 0: falls, stays >= 0) and
step = A (1 + k1 u) mu_McMaster, u = E/E_edge - 1, k1 = self-absorption (~ +1.2 for diluted
sugar pellets at S K, ~ 0 for thin films). In this frame the step falls with E like mu_S x SA.
DEGENERACY: the data cannot split the rise between F and the step (p free runs to its bound
at the same residual); fix p from the I0 physics. The normalized XANES barely depends on it
(< 0.5 % for p 2.8-3.3). Do not put the rise on the step alone (a linear step factor leaves
a bowed residual; an empirical quadratic step factor works numerically, but makes the step grow
with E, which mu cannot do). `step_factor_base` (empirical) and `post_poly` (additive rise) remain
as options.

Other edges in range: per-sample `normalize: {extra_edges: [[Mo, L3]], exclude_eV: [...]}` adds
a McMaster step (free amplitude >= 0; an L3 step carries the L2 jump at the tabulated ratio)
and removes its white lines from the windows. In fluorescence the amplitude reflects the
emission overlap with the detector window (Mo La 2293 eV in the S Ka window), not composition.
Additive post-edge rise (`post_poly: n`, 0 at the edge) is available; at S K it is not
distinguishable from the multiplicative factor. `model: athena` (pre line, post quadratic,
flattened) is available for comparison; its quadratic is unstable on short post windows.

## Self-absorption (fluorescence): explicit, optional, always next to the uncorrected file
`<name>_avg_nrm` is NEVER self-absorption corrected (it is the as-measured extraction; the
step-slope factor 1 + k1 u changes it by < 0.2 % below E_edge + 4 eV). A sample-level block

    self_absorption:
      composition: [{formula: Na2S2O3, wt: 0.05}, {formula: C12H22O11, wt: 0.95}]   # mass fractions
      phi_in_deg: 45        # incidence angle to the surface
      theta_out_deg: 45     # exit angle to the detector
      E_fluo_keV: 2.308     # optional (default absorber K-alpha1)

writes `<name>_avg_sac` [E, s, mu] in addition, with the inputs and diagnostics in
reduce_diag.json. Method (model/self_absorption.py, thick limit, Troger 1992 / Haskel FLUO):
  n(E) = (IF/I0 / F - bg) / A = K mu_a / (mu_a + alpha),  mu_a = D0 s(E),
  alpha = mu_rest(E) + g mu_tot(E_f),  g = sin(phi)/sin(theta),  D0 = absorber K jump (McMaster),
  s = alpha n / (D0 (K - n)), K by least squares of s onto the McMaster unit step (post window).
Diagnostics: alpha/D0 (dilution), max n/K (saturation at the white line), residual step slope
after correction (~ 0 if the model also explains the post-edge rise).
Refused (warning, no file) when the measured contrast max(n)/n_post exceeds the thick-limit
maximum 1 + alpha/D0: the sample is not thick for that composition (powder finer than the
absorption length, thin film, or diluted). Thin films need a thickness-dependent correction
(not implemented). S K Nov 2025: Na2S2O3 5 wt% WL 2.55 -> 2.93, CoSO4 0.5 wt% 4.14 -> 4.24;
elemental S refused (1.70 > 1.24); dry MOF as pure CoTHT would be refused (2.71 > 1.97).

## HERFD with a short pre-edge (BL6-2 2018/2019 Pt L3: scans start 24 eV below the edge)
With only ~5 pre-edge points the free Victoreen background is set by its extrapolation: it rose
to ~14 % of the step at 11800 eV, differently per spectrum, and shifted difference spectra by up to
0.03-0.05 (Nature Mater. 2025 Fig. 2b set). A HERFD background is flat and small: use
`bg_decreasing: true`. Check difference spectra against a model-free relative normalization (raw
IF/I0 minus the pre-edge level, each scaled to the reference over a common post-edge window,
glitch excluded): with the constraint they agree to 0.0016 rms (free Victoreen 0.010, -0.4 V 0.023).
Athena per-spectrum flattened normalization differs from the model-free reference by up to
~0.035 in Fig. 2b; the difference-spectrum magnitudes between 0 and -0.6 V are normalization-limited.
