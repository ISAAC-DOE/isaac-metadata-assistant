# SYNTHETIC. A `MERGE/`-style processed two-column spectrum.

`63_06_ZZ1_f10.txt` reproduces what the real `MERGE/` entries are: **two
whitespace-separated numbers per line and no header whatsoever**. Its values are
invented (energies 1000–1031, nowhere near any real absorption edge).

It cannot carry a "this is synthetic" first line, because a comment line would
destroy the property the fixture exists to pin — that the classifier recognises a
file whose every line is two numbers and which has no header at all. Its name and
this README are the disclosure.

Two things the real `MERGE/` names do, which this fixture's own name reproduces:
the filter is spelled `f10` where the acquisition spells it `filter10`, and a
leading number is present but the sample/electrode token may not be (the real
`63_06.txt` carries two numbers and nothing else).

A `MERGE` entry is a **candidate processed artifact**. Nothing in this package
makes one an official ISAAC reduced spectrum.
