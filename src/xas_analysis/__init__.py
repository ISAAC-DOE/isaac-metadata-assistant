"""xas-analysis: X-ray absorption reduction (Python port of the AI-ISAAC MATLAB XAS pipeline).

Stages (MATLAB reference in reference/matlab/):
  io.spec           parse_spec.m, read_xas_scans.m
  calib             find_inflection_point.m, align_and_resample.m
  average           average_scans.m
  pipeline          reduce_xas_v2.m  (SPEC -> aligned + averaged *_raw files)
  physics.mcmaster  McMaster.m + element.mat
  model.mback       mback_v4.m       (hard-XAS component-fit normalization)
  model.soft_pvii   sxas_core.py     (soft-XAS Pearson-VII + FEFF mu0 engine, BL8-2 C K)
"""
__version__ = "0.1.0.dev0"
