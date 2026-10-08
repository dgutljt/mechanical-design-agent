# Reproducible v0.2 two-plane shaft analysis

This case uses 5.5 kW at 960 rpm, a 600 mm simply supported span, a -1000 N signed point load at 200 mm in plane 1 (+y), a -1000 N signed point load at 400 mm in plane 2 (+z), and 40 MPa allowable shear stress. The [input](input.json) is the existing Native adapter request; [expected results](expected_results.json) record the reviewed outputs.

Run from the repository root with Python 3.12 or later and the source package available:

```powershell
python examples/v0.2-two-plane-shaft-analysis/run_demo.py --verify
```

The command calls the existing adapter, which uses the calculators, three Reviewer gates, Verified Handoff, and Registry. It checks the canonical numbers, workflow ID, all Reviewer statuses, exact handoff lineage, and both critical station contexts. It writes no artifacts and needs no LLM session.

The independent peak of each plane is 133333.33333333334 N·mm. Combining those separate maxima would give 188561.80831641267 N·mm, which is **wrong** because the peaks occur at different stations. The verified resultant combines signed components at the **same station**: 149071.198499986 N·mm (149.071198499986 N·m) at both 200 and 400 mm. The reviewed theoretical minimum strength diameter is 27.24261631262692 mm, not a production diameter.

For the physical convention, +x runs from support A to B. The plane 1 scalar component equals `M_z`; the plane 2 scalar component equals `-M_y`. Thus a positive plane 2 scalar component must not be labeled positive `M_y`.
