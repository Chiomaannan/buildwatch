# Proposal: Adding a Roof Weight to the MWPI Formula

**Project:** BuildWatch — IoT Construction Progress Monitoring
**Author:** Chioma Annan
**For review by:** Dr. Nii Longdon Sowah
**Date:** 11 July 2026
**Status:** SUPERSEDED by `MWPI_V2_FINISHES_PROPOSAL.md` (12 July 2026), which
folds this roof change into a combined roof + finishing-stages proposal.
Retained for reference; do not review separately.

---

## 1. Current formula

MWPI is a weighted sum of per-class completion ratios:

```
MWPI_t = Σ_c  w(c) × r_t(c)
```

with base class weights:

| Class      | Weight | Notes                                     |
|------------|--------|-------------------------------------------|
| foundation | 0.20   |                                            |
| column     | 0.30   |                                            |
| wall       | 0.50   |                                            |
| roof       | 0.00   | Detected but unweighted (reserved)         |

When a building plan is uploaded, `plan_analyzer.py` derives site-specific
weights and expected element counts, which override the base weights. The plan
analyzer currently emits **no roof entry at all**.

## 2. The problem, demonstrated on real data

On 11 July 2026 the retrained YOLO11n model (v2, nc=5) ran live inference on a
photo of the Spintex house — a build with roof, walls, and columns visibly in
place. Detections:

| Class  | Detections | Confidences        |
|--------|-----------|---------------------|
| roof   | 1         | **0.793** (strongest detection in the frame) |
| wall   | 3         | 0.545, 0.415, 0.345 |
| column | 2         | 0.282, 0.276        |

Plan-informed scoring used weights `{foundation: 0.15, column: 0.25,
wall: 0.60}` with expected counts `{foundation: 2, column: 6, wall: 10}`,
producing **MWPI = 0.359** — far below what a human inspector would assign to
a roofed structure.

The decisive evidence of late-stage progress — the roof, detected with the
highest confidence in the entire frame — contributed **exactly zero** to the
score. MWPI is structurally blind to the final phase of construction: two
sites, one at wall stage and one fully roofed, can receive identical scores.

## 3. Why this matters now

When the roof weight was reserved at 0.00, the model had no trained roof
class, so any nonzero weight would have been unmeasurable. That constraint no
longer holds: the v2 model (trained July 2026) includes a dedicated `roof`
class and detected it at 0.79 confidence on first live inference. The
measurement capability now exists; the formula has not caught up.

## 4. Proposed change

### 4.1 Base weights (primary proposal)

| Class      | Current | Proposed | Rationale |
|------------|---------|----------|-----------|
| foundation | 0.20    | 0.15     | Earliest milestone; typically occluded by later work anyway (ratchet preserves its credit) |
| column     | 0.30    | 0.25     | Intermediate structural milestone |
| wall       | 0.50    | 0.40     | Largest single phase, but no longer the terminal one |
| roof       | 0.00    | **0.20** | Terminal structural milestone; marks weathertight/lockup stage |

Weights remain a partition of 1.0. The 0.20 roof weight reflects roofing's
share of the structural timeline in typical Ghanaian residential construction
(roughly 15–25% of the superstructure phase), and gives the index a
meaningful gradient in the late stage of a build.

*Alternative (minimal-disruption) option:* scale existing weights by 0.85 and
assign roof the remainder — foundation 0.17, column 0.255, wall 0.425,
roof 0.15. This preserves the current relative ratios exactly, at the cost of
less round numbers and a weaker late-stage signal. The primary proposal is
recommended.

### 4.2 Plan analyzer

`plan_analyzer.py` must be updated to emit a `roof` weight and expected count
(typically 1, or the number of roof sections identifiable on the plan).
Without this, plan-informed projects — the intended primary mode — would
continue to ignore roofs even after the base weights change.

### 4.3 Out of scope here, flagged for a follow-up discussion

The Spintex case also exposed a second, independent depressor: plan-derived
expected counts describe the *whole building* (10 wall sections), while a
single fixed camera sees one façade (3 sections visible). Per-class ratios
are therefore capped well below 1.0 regardless of actual completion. A
per-viewpoint visibility factor on expected counts is the natural fix, but it
is a separate change and should be evaluated separately.

## 5. Backward compatibility and safety

- MWPI state is stored as per-class *ratios*, never weighted contributions,
  so historical data re-weights correctly under the new weights — no
  migration is required (this was a deliberate design property of MWPI v2).
- The monotonic ratchet is unaffected; scores remain non-decreasing.
- The Spintex project's latched state was reset on 11 July 2026 (it contained
  ratios accumulated during mock-inference testing), so all evidence going
  forward is from real model output.

## 6. Validation plan

1. Freeze a validation set of site photos spanning early, mid, and late
   construction stages, each with a human-assigned reference progress score.
2. Compute MWPI under current and proposed weights on identical detections.
3. Report correlation with the human reference (Spearman ρ) for both weight
   sets, with particular attention to late-stage (roofed) images where the
   current formula is known to saturate.
4. Adopt the proposed weights only if late-stage discrimination improves
   without degrading early/mid-stage agreement.

## 7. Decision requested

Approval to:
1. Change the base MWPI weights per §4.1 (primary proposal).
2. Update the plan analyzer to emit roof weights/expected counts (§4.2).

No code changes to the formula will be made until this is signed off.
