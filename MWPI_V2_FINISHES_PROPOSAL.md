# Proposal: MWPI v2 Weights — Roof and Finishing Stages (Plastering & Painting)

**Project:** BuildWatch — IoT Construction Progress Monitoring
**Author:** Chioma Annan
**For review by:** Dr. Nii Longdon Sowah
**Date:** 12 July 2026
**Status:** Implemented 13 July 2026 (authorized by Chioma following Dr. Sowah's
request that MWPI track progress until the building is plastered and painted);
formal sign-off on the exact weights in §3 still requested
**Supersedes:** `MWPI_ROOF_WEIGHT_PROPOSAL.md` (11 July 2026) — the roof change
is folded into this combined proposal so the formula is revised once, not twice.

---

## 1. Motivation: two demonstrations of the same flaw

MWPI currently saturates at 100% when the *structure* is complete, not when
the *building* is complete.

**Case A — roof (11 July 2026, Spintex).** Live inference on a roofed
structure detected the roof at 0.79 confidence — the strongest detection in
the frame — yet it contributed exactly zero to the score, because roof carries
weight 0.00. Full details in the superseded roof proposal.

**Case B — finishes (supervisor test run, July 2026).** A test image of a
structurally complete building — roof on, walls up, but **unplastered and
unpainted** — displayed **100% completion** on the dashboard. No inspector,
quantity surveyor, or client would call that building finished: finishes and
services typically represent 20–35% of a residential building's contract
value.

Both cases are the same defect: the index's weight mass is exhausted before
construction actually ends. This proposal extends the milestone set so that
100% means *ready*, not *roofed*.

## 2. Proposed milestone set and sequencing assumptions

Two finishing milestones are added:

| Milestone      | Visual evidence                              | What it certifies |
|----------------|----------------------------------------------|-------------------|
| **plastering** | wall surfaces rendered smooth (block joints no longer visible) | plaster + **first-fix M&E complete** |
| **painting**   | wall surfaces carry a finish coat            | paint + **second-fix M&E complete** |

### 2.1 Why plaster and paint can stand in for plumbing and electricals

A camera can never observe pipework or wiring inside a wall. However,
standard construction sequencing makes finish state a reliable *proxy*:

1. **First fix precedes plastering.** Electrical conduits and plumbing pipes
   are chased into the blockwork *before* rendering — a plastered wall cannot
   physically conceal work that has not been done. Therefore:
   *plastered ⇒ first-fix plumbing and electrical complete.*
2. **Second fix precedes painting.** Sockets, switches, and fittings are
   installed after plastering and before the final decorative coat.
   Therefore: *painted ⇒ second-fix M&E complete.*

This first-fix / second-fix ordering is standard practice in building
construction (see e.g. Chudley & Greeno, *Building Construction Handbook*)
and is the normal sequence on Ghanaian residential sites.

**These are documented assumptions, not measurements.** They hold for
conventionally sequenced builds; a site that plasters before chasing conduits
(rework-prone but possible) would be over-credited. The thesis will state the
assumption explicitly, with the sequencing citation, and list it as a
limitation. In exchange, BuildWatch gains visibility into the ~20–35% of
project value that a structure-only index ignores — using only the camera it
already has.

### 2.2 Structural implications (added 14 July 2026)

Live testing exposed the mirror image of the finishes problem: on the test
image, the foundation earned **zero credit** (backfilled, hidden behind the
very walls standing on it) and the columns earned zero (detected below the
confidence threshold, embedded in the blockwork). The camera cannot
re-observe completed early stages — but each later stage *proves* the stages
that carry it. Two implications, applied top-down:

1. **Roof started ⇒ walls & columns complete (threshold); proportional
   below.** Roofing begins only after blockwork reaches the wall plate /
   ring beam, so once the roof latches at ≥ 0.2 (the wall-plate stage of the
   grading rubric) the wall–column frame carrying it is credited in full.
   Window and door openings in the blockwork are *not* incompleteness —
   frames and glazing are finishing work, and the surface dimension is
   already measured by the plastering/painting milestones. Below the 0.2
   threshold the lift is proportional (r(wall), r(column) ≥ r(roof)), since
   weak roof evidence should not prove a complete frame.
2. **Superstructure ⇒ foundation (threshold).** The substructure phase
   completes before blockwork rises, so once any of column/wall/roof latches
   at ≥ 0.25, foundation is credited in full. The 0.25 trigger prevents a
   single noisy detection from claiming the credit (ratios are
   median-smoothed before latching); once crossed, foundation latches at 1.0
   permanently, consistent with the monotonic ratchet.

This is the same sequencing-inference methodology as §2.1, applied downward
instead of upward. A side benefit: the roof implication partially offsets the
single-viewpoint visibility depressor (§5.3) — a fully visible roof restores
wall/column credit that per-façade expected counts had capped.

### 2.3 Stage-graded ratios (added 16 July 2026)

Detection is binary within a class: a bare roof truss frame and a fully
covered roof both detect as `roof` at high confidence, so the test image
earned the full roof weight while visibly unfinished. Detection counts
measure **extent** (how many elements exist); a second signal must measure
**state** (how complete each visible element is).

A per-capture Claude-vision **stage assessor** (merged into the same request
as the wall-surface classification — no added API cost) grades each
structural class 0–1 against a rubric, e.g. roof: 0.2 ring beam only, 0.5
trusses erected, 0.8 partially sheeted, 1.0 covered; wall: average visible
height as a fraction of full storey height, judged against door/window
lintel datums. When the project has an uploaded building plan (architectural
plan, elevation, or 3D render), that image is sent alongside the site photo
and grading is performed **relative to the finished design** — the assessor
compares the roof shape, wall extents, and storeys the design calls for
against what has actually been built.

The raw ratio becomes `extent × state`:  ρ(c) = detection ratio × grade(c).
The grade applies to visible-element state only (extent stays with the
detection ratio) to avoid double-penalising. Failure handling preserves the
index's honesty: if the assessor errors, that frame contributes no new
structural evidence and the ratchet holds — a transient outage can never
latch full credit for a half-built element. Deployments without an API key
degrade to ungraded (extent-only) scoring.

Alternatives documented as future work: geometric measurement (pixel datums,
fragile from one uncalibrated monocular camera) and YOLO sub-stage classes
(roof_frame/roof_covered — needs relabelling + retraining).

### 2.4 Physical ordering constraint (optional refinement)

Since plaster is applied to walls and paint to plaster, the ratios can be
gated: `r(plastering) ≤ r(wall)` and `r(painting) ≤ r(plastering)`. This
prevents a misclassification from crediting paint on a site with no walls.
Recommended, but severable from the weight decision.

## 3. Proposed weights

The structural weights are those of the superseded roof proposal
(foundation 0.15 / column 0.25 / wall 0.40 / roof 0.20), scaled by **0.80**
to release a 0.20 mass for finishes — so the structural *ratios* already
reviewed are preserved exactly.

| Class      | Current | Proposed | Rationale |
|------------|---------|----------|-----------|
| foundation | 0.20    | **0.12** | Earliest milestone (ratchet preserves credit under occlusion) |
| column     | 0.30    | **0.20** | Intermediate structural milestone |
| wall       | 0.50    | **0.32** | Largest single phase |
| roof       | 0.00    | **0.16** | Terminal structural milestone — weathertight/lockup stage |
| plastering | —       | **0.12** | Render + implied first-fix plumbing & electrical |
| painting   | —       | **0.08** | Finish coat + implied second-fix M&E |

Weights remain a partition of 1.0. Structural work totals **0.80** and
finishes **0.20**, consistent with the 20–35% share finishes and services
hold in typical residential bills of quantities (the conservative end is
chosen because interior finishes are not observable — §5.1).

**Behavioural consequence:** a structurally complete but unplastered building
now reads **80%**, plastered-but-unpainted **92%**, and **100% only when
painted** — which is the supervisor's stated requirement.

*Alternative:* finishes at 0.25 (plastering 0.15, painting 0.10, structural
scaled by 0.75) if a stronger finishing signal is preferred. The primary
proposal is recommended.

## 4. Implementation

### 4.1 Formula (no algorithm change)

MWPI v2 already supports this with zero changes to its machinery:
`MWPI_t = Σ_c w(c) × r_t(c)` simply gains two terms. Soft counts, median
smoothing, and the monotonic ratchet apply to the new classes unchanged, and
because state is stored as per-class **ratios** (never weighted
contributions), historical data re-weights correctly under the new weights —
**no data migration is required**. Partial finish states (e.g. one façade
plastered, three bare) are handled naturally as fractional ratios rather than
a binary flag.

### 4.2 Measurement — two-stage detection (recommended for this cycle)

Rather than retraining YOLO with new classes, wall **surface state** is
classified downstream of detection:

1. YOLO11n detects `wall` regions (existing capability, unchanged).
2. Detected wall crops are sent to the Claude vision API — already integrated
   in this codebase (`plan_analyzer.py`, `explanation_generator.py`) — which
   labels each crop `unplastered | plastered | painted`.
3. Per-frame finishing ratios:
   `ρ(plastering) = (plastered + painted walls) / walls detected`,
   `ρ(painting) = painted walls / walls detected`
   (a painted wall is by definition also plastered), then smoothed and
   latched exactly as for structural classes.

The distinction is visually strong — exposed block joints vs. smooth render
vs. a colour coat — and requires **no new labelled dataset and no retraining**,
which matters with ~4 weeks to submission.

### 4.3 Future work: dedicated detector classes

Adding `wall_plastered` / `wall_painted` classes to the YOLO model (bundled
with the planned accuracy sprint) would remove the vision-API dependency and
per-image latency/cost. Flagged as future work in the thesis, not this cycle.

### 4.4 Plan analyzer

`plan_analyzer.py` must be updated to emit weights and expected counts for
`roof` (carried over from the superseded proposal) and for
`plastering`/`painting` (expected counts inherit from `wall`). Without this,
plan-informed projects — the intended primary mode — would ignore the new
milestones even after the base weights change.

## 5. Limitations, stated openly

1. **Exterior visibility only.** A fixed external camera observes exterior
   finish; interior plastering/painting is invisible. MWPI is therefore an
   *exterior-observable* progress index — stated in the thesis, and one
   reason the conservative 0.20 finishing mass was chosen.
2. **Proxy risk.** The first-fix/second-fix inference (§2.1) fails on
   unconventionally sequenced sites. Documented assumption + limitation.
3. **Single-viewpoint expected counts.** Plan-derived counts cover the whole
   building while one camera sees one façade, capping ratios below 1.0. This
   pre-existing issue (roof proposal §4.3) equally affects finishing ratios;
   the per-viewpoint visibility factor remains a separate follow-up.

## 6. Validation plan

Extends the roof proposal's plan to cover the finishing regime:

1. Freeze a validation set spanning early, mid, **structural-complete,
   plastered, and painted** stages, each with a human-assigned reference
   progress score (this feeds the weekly expert ground-truth study already
   underway).
2. Compute MWPI under current and proposed weights on identical detections.
3. Report Spearman ρ and MAE against the human reference for both weight
   sets, with particular attention to the late-stage region where the current
   formula saturates at 1.0 (the supervisor's test image becomes the first
   validation case).
4. Separately report the surface-state classifier's accuracy on wall crops
   (confusion matrix over unplastered/plastered/painted).
5. Adopt the proposed weights only if late-stage discrimination improves
   without degrading early/mid-stage agreement.

## 7. Decision requested

Approval to:
1. Adopt the six-class base weights per §3 (includes the roof weight,
   superseding the 11 July proposal).
2. Implement two-stage surface-state classification for plastering/painting
   per §4.2, with the ordering gate per §2.4, the structural implications
   per §2.2, and stage-graded ratios per §2.3.
3. Update the plan analyzer per §4.4.
4. Record the sequencing assumptions of §2.1 and §2.2 as documented
   methodology assumptions in the thesis (finish state implies M&E fix
   stages; superstructure implies substructure).

No code changes to the formula will be made until this is signed off.
