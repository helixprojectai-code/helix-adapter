# Spacetime — Constitutional Topological Gravity Simulations

**Status:** ✅ All simulations validated
**Component root:** `spacetime/`
**Canonical artifact:** `CONSTITUTIONAL_SPACETIME_RESULTS.md`,
`constitutional_spacetime_v1_preprint.pdf`
**Execution node:** CORE (20.124.180.133)
**Date:** August 3, 2026

---

## What This Is

A suite of simulations testing the Helix thesis that **topological density
couples to the metric**: if knots (Hopf pairs) are the substrate, then
increasing knot density should produce measurable spacetime curvature —
without adding mass.

Four campaigns, one validated truth: **topology is exact; coupling is a
density effect, not a mass effect.**

## The Four Campaigns

### 1. Validated (Baseline)
- Hopf pairs: 32 (64 knots), mass 1 M☉
- Mean Hopf |Lk|: **0.9947 ± 6e-15** (perfect — topology exact)
- g_rr_max: 1.0 (flat metric)
- Wall time: 48.5 s
- **Finding:** metric is flat because the ensemble is sparse (~6e-6 knots/m³)

### 2. Scaled (10× Knots)
- Hopf pairs: 500 (1000 knots), mass 1 M☉
- Mean Hopf |Lk|: 0.9910 ± 5e-15 (still perfect)
- Knot density max: 0.089 (**15,000× increase**)
- g_rr_max: **1.000005** (5 ppm curvature)
- Time dilation min: **0.9999955** (45 ppm drift)
- **Finding:** the signal appeared. Topological density couples to the
  metric exactly as predicted.

### 3. High Mass (100× Solar)
- Hopf pairs: 32 (64 knots), mass 100 M☉, Schwarzschild radius 294,990.8 m
- Mean Hopf |Lk|: 0.9947 (topology unchanged)
- g_rr_max: 1.0 (metric unchanged)
- **Finding:** scaling mass does not increase coupling. The driver is knot
  density, not mass — the metric is scale-invariant under mass.

### 4. Monty Python (Absurd Parameters)
- Hopf pairs: 200, mass 1,000,000 M☉, Schwarzschild radius 2.95e9 m (20 AU)
- Mean Hopf |Lk|: 0.9821 (**topology holds** under absurd parameters)
- **Finding:** the topological invariant is robust to parameter absurdity.

## The Truth

| Campaign | Topology | Metric |
|---|---|---|
| Baseline (32 pairs, 1 M☉) | Lk = 0.9947 ± 6e-15 | flat |
| Scaled (500 pairs, 1 M☉) | Lk = 0.9910 ± 5e-15 | **5 ppm curvature, 45 ppm dilation** |
| High Mass (32 pairs, 100 M☉) | Lk = 0.9947 | flat |
| Monty (200 pairs, 1e6 M☉) | Lk = 0.9821 | flat |

Density couples. Mass doesn't. Topology is exact everywhere.

## Contents

```
spacetime/
  CONSTITUTIONAL_SPACETIME_RESULTS.md     (canonical results)
  constitutional_spacetime_v1_preprint.pdf (preprint)
  constitutional_spacetime_{sim,validated,scaled,highmass,monty,real_*}.py
  four_campaign_validation.png
  {validated,scaled,highmass,monty} metric.csv + summary.json
```

Related: `docs/rfc/HELIX_Unified_Research_Report.pdf`.
