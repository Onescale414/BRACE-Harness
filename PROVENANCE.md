# Sources and measurements

**Arithmetic.** The harness, demo and tests come from BRACE’s two-step integer reference. Its affine coefficient and witness checks derive from the earlier `prepare.py` checker. [Checker](harness.py)

**Geometry.** The viewer contains one matched pair from a 12-cart synthetic study. Undoing the arm rotation in Chromium supplied the reference endpoints. The Python verifier independently reconstructs them from squared distances. [Verifier](preview/verify.py)

**Delivery.** The 36 authored requests use two synthetic connector mappings. Recorded WireMock responses supply the URL verdicts. The evidence includes the labels, observed decisions and source hashes for the three readers and the delivery guard. [Evidence](research/delivery/observations.json)
