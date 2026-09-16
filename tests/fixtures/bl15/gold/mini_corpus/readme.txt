# SYNTHETIC FIXTURE -- NOT INSTRUMENT OUTPUT. Every value below is invented.
# 2099-01_SYNTHETIC
#
# REWRITTEN 2026-09-16. The first version used bare `label value` lines
# (`element Xx`, `beamsize 1 x 1 um at 1215 eV`) and `read_shared_readme`
# produced ZERO evidence from it — one `unrecognized_prose_block` skip over the
# whole file. So the gold standard's `readme_inheritance` expectation was
# UNMEETABLE by any reader in this build, and nothing confronted it with a real
# reading: the harness test builds its observation from the expectation itself.
#
# The fixture was the thing that was wrong, and independent review said so. The
# reader's grammar was validated against the real archive's file; this fixture's
# was not validated against anything. Changing the reader would mean authoring a
# second readme grammar with no real-corpus warrant, which §5 forbids; changing
# the gold standard would lower an expectation to match a fixture defect. So the
# format below is the one `tests/fixtures/bl15/notes/readme.txt` declares the
# real archive uses: a bare element line, then `<Label>:` sections with indented
# continuations, and one label carrying a `@` before its colon.

Xx

Beamsize @1215eV:
	1 um vert (#1) m1u 1 m1d 1
	1 um horz (#2) m2u 1 m2d 1

Spectrometer:
	1.0mm synslit
	1215eV XxL3M5
	5x Si 000 00000,

Monochromator: calib with Synthetic Foil in front of I2, #1, 1215.0
