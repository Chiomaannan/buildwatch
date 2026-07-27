"""
progress.py — MWPI computation for BuildWatch (v2).

Milestone-Weighted Progress Index — plan-informed, confidence-weighted, monotonic
─────────────────────────────────────────────────────────────────────────────────
    MWPI_t = Σ_c  w(c) × r_t(c)

Per-class completion ratio pipeline (three stages):

  1. Soft counts (confidence weighting)
         ñ_t(c) = Σ p_i   for detections i of class c with p_i ≥ CONF_FLOOR
     Each detection contributes its confidence, not a hard 1. This removes the
     cliff at the old 0.40 threshold: a 0.39-confidence wall no longer counts
     for nothing while a 0.41 one counts fully, and low-confidence classes
     (e.g. wall, mAP 0.197) accumulate partial rather than inflated evidence.

  2. Raw ratio (plan-informed or binary fallback), stage-graded
         ρ_t(c) = min(1, ñ_t(c) / E(c)) × g_t(c)  when expected count E(c) known
         ρ_t(c) = g_t(c) if any p_i ≥ BINARY_CONF otherwise (binary fallback —
                                                   full weight needs strong evidence)
     g_t(c) is the stage-completion grade from the Claude-vision stage
     assessor (stage_assessor.py): how COMPLETE the visible elements of class
     c are, 0–1 (a bare roof truss frame grades ~0.5; a half-height wall
     ~0.5). Detection counts capture extent; the grade captures state — the
     product is the fraction of that class's total work actually done.
     stage_fractions=None (assessor disabled / mock mode) means g ≡ 1, which
     is exactly the pre-grading v2 behaviour.

     Finishing classes (plastering, painting) are not YOLO classes — their
     evidence is the fraction of visible walls a Claude-vision surface-state
     classifier labels plastered/painted (stage_assessor.py). Their raw
     ratio is that fraction scaled by the wall raw ratio:
         ρ_t(plastering) = ρ_t(wall) × frac_plastered
         ρ_t(painting)   = ρ_t(wall) × frac_painted
     so finishing progress is measured against the whole building, and the
     physical ordering  ρ(painting) ≤ ρ(plastering) ≤ ρ(wall)  holds by
     construction (the classifier counts painted walls as plastered too).
     A post-latch clamp re-enforces the ordering on latched values.

     Sequencing assumptions (documented in MWPI_V2_FINISHES_PROPOSAL.md):
     plastered ⇒ first-fix plumbing & electrical complete; painted ⇒
     second-fix M&E complete. First fix physically precedes rendering.

     Structural implications (each stage proves the stages that carry it):
       roof        ⇒ walls & columns — roofing starts only after blockwork
                     reaches the wall plate / ring beam, so once the roof
                     latches at ≥ ROOF_IMPLIES_STRUCTURE_AT (the wall-plate
                     stage) the wall–column frame that carries it is credited
                     in full; below that, r(wall)/r(column) are lifted to at
                     least r(roof) proportionally
       any of column/wall/roof latched ≥ FOUNDATION_IMPLIED_AT
                   ⇒ foundation complete — the substructure phase finishes
                     before blockwork rises, and a backfilled foundation is
                     invisible precisely because the building on it exists

  3. Smoothing + ratchet (monotonicity)
         r_t(c) = max( r_{t-1}(c), median(ρ_{t-k+1}(c), …, ρ_t(c)) )
     Construction progress is physically irreversible at capture timescale, but
     detected counts DROP as later elements occlude earlier ones (walls hide
     columns, backfill hides foundations). Latching each ratio at its historical
     max makes MWPI monotone non-decreasing by construction. The median over the
     last SMOOTH_WINDOW raw ratios stops a single spurious detection from
     permanently inflating the latch (one-frame confirmation delay, acceptable
     at ~2 captures/hour). Rework/demolition is handled by an explicit manual
     reset (POST /projects/{id}/reset-progress), not by un-latching.

State is stored as *ratios*, never contributions, so weights can change (e.g. a
plan is uploaded mid-project) and history re-weights correctly.

Class weights (v2 finishes proposal — do not change without supervisor approval):
    foundation  → 0.12   structural subtotal 0.80: a structurally complete
    column      → 0.20   but unplastered building reads 80%, plastered 92%,
    wall        → 0.32   and 100% only when painted
    roof        → 0.16
    plastering  → 0.12   render + implied first-fix plumbing & electrical
    painting    → 0.08   finish coat + implied second-fix M&E

MWPI range: 0.0 (nothing built) → 1.0 (building fully finished)
"""

import logging
from dataclasses import dataclass, field
from statistics import median
from typing import Any

logger = logging.getLogger(__name__)

MWPI_WEIGHTS: dict[str, float] = {
    "foundation": 0.12,
    "column":     0.20,
    "wall":       0.32,
    "roof":       0.16,
    "plastering": 0.12,
    "painting":   0.08,
}

# Classes measured by the surface-state classifier, not by YOLO detections.
FINISHING_CLASSES: tuple[str, ...] = ("plastering", "painting")

# YOLO-detected classes whose raw ratios are scaled by the stage grade.
STRUCTURAL_CLASSES: tuple[str, ...] = ("foundation", "column", "wall", "roof")

# Weight mass injected into plan-derived weights that predate the v2 scheme
# (see ensure_v2_weights). Kept in sync with MWPI_WEIGHTS.
_MISSING_CLASS_WEIGHTS: dict[str, float] = {
    "roof":       0.16,
    "plastering": 0.12,
    "painting":   0.08,
}

# Detections below this confidence are ignored entirely.
MWPI_CONF_FLOOR = 0.25
# Binary fallback (no expected count) awards full class weight, so it demands
# at least one detection this confident. Also the legacy v1 counting threshold.
MWPI_CONF_THRESHOLD = 0.4
# Raw ratios are median-filtered over this many frames before latching.
MWPI_SMOOTH_WINDOW = 3
# Latched superstructure ratio (column/wall/roof) at which the foundation is
# credited in full by sequencing implication. High enough that one spurious
# detection can't trigger it (raw ratios are already median-smoothed), low
# enough that real blockwork progress does.
FOUNDATION_IMPLIED_AT = 0.25
# Latched roof ratio at which the wall–column frame carrying it is credited
# in full. 0.2 is the rubric's "ring beam / wall plate" stage — the wall
# plate physically sits on completed blockwork, so a started roof proves
# finished walls and columns.
ROOF_IMPLIES_STRUCTURE_AT = 0.2


@dataclass
class MwpiResult:
    """Full output of one MWPI computation."""

    score: float                                        # Σ w(c) × r(c), in [0, 1]
    detected_classes: list[str]                         # classes with contribution > 0 (incl. held)
    class_contributions: dict[str, float]               # {class: w × r}
    detected_counts: dict[str, int]                     # integer counts at ≥ CONF_FLOOR (for display)
    soft_counts: dict[str, float] = field(default_factory=dict)   # ñ(c)
    raw_ratios: dict[str, float] = field(default_factory=dict)    # ρ_t(c), this frame only
    ratios: dict[str, float] = field(default_factory=dict)        # r_t(c), smoothed + latched (scored)
    held_classes: list[str] = field(default_factory=list)         # latched above current raw (occluded)


def ensure_v2_weights(weights: dict[str, float]) -> dict[str, float]:
    """
    Bring a plan-derived weight dict onto the v2 milestone set.

    Plans analyzed before the v2 finishes scheme carry only structural classes
    (possibly without roof). Rather than letting such a plan silently reopen
    the "100% at bare structure" flaw, scale its weights down and inject the
    fixed weights for the missing classes, preserving the plan's structural
    ratios. Weight dicts that already cover roof + finishes pass through.
    """
    missing = {c: w for c, w in _MISSING_CLASS_WEIGHTS.items() if c not in weights}
    if not missing:
        return weights
    scale = 1.0 - sum(missing.values())
    adjusted = {c: round(w * scale, 4) for c, w in weights.items()}
    adjusted.update(missing)
    return adjusted


def compute_mwpi(
    detections: list[dict[str, Any]],
    conf_floor: float = MWPI_CONF_FLOOR,
    binary_conf_threshold: float = MWPI_CONF_THRESHOLD,
    expected_components: dict[str, int] | None = None,
    plan_weights: dict[str, float] | None = None,
    prior_ratios: dict[str, float] | None = None,
    ratio_history: list[dict[str, float]] | None = None,
    finish_fractions: dict[str, float] | None = None,
    stage_fractions: dict[str, float] | None = None,
) -> MwpiResult:
    """
    Compute confidence-weighted, monotonic MWPI from YOLO11n detections.

    Args:
        detections:            list of {class_name, confidence, bbox, ...}
        conf_floor:            minimum confidence for a detection to contribute
        binary_conf_threshold: minimum confidence to trigger the binary fallback
        expected_components:   expected element counts from plan analysis,
                               e.g. {"column": 8, "wall": 20, "foundation": 2}
        plan_weights:          site-specific class weights from plan analysis
                               (overrides MWPI_WEIGHTS when provided; legacy
                               structural-only plans are normalized via
                               ensure_v2_weights)
        prior_ratios:          latched ratios from previous frames
                               (Project.mwpi_state["latched_ratios"]); the
                               ratchet — omit for stateless v1 behaviour
        ratio_history:         raw ratio dicts of the most recent previous
                               frames, oldest → newest (only the last
                               MWPI_SMOOTH_WINDOW − 1 are used)
        finish_fractions:      surface-state classifier output — fraction of
                               visible walls plastered / painted this frame,
                               e.g. {"plastering": 0.66, "painting": 0.33}
                               (painted walls count as plastered too). None
                               when the classifier didn't run (no walls, no
                               API key, error) — the ratchet then holds any
                               previously latched finishing progress.
        stage_fractions:       stage-completion grades from the stage
                               assessor — how complete the visible elements
                               of each structural class are, e.g.
                               {"roof": 0.5, "wall": 0.9, ...}. Multiplied
                               into structural raw ratios. None = assessor
                               disabled/mock (multiplier 1.0, v2 behaviour);
                               a dict missing a class means no assessment
                               evidence for it this frame (raw 0, ratchet
                               holds — pass {} after an assessor failure so
                               a transient outage can't latch full credit).
    """
    weights = ensure_v2_weights(plan_weights) if plan_weights else MWPI_WEIGHTS

    # ── 1. Counts: soft (evidence) + integer (display) + binary trigger ──
    soft: dict[str, float] = {cls: 0.0 for cls in weights}
    counts: dict[str, int] = {}
    binary_hit: dict[str, bool] = {cls: False for cls in weights}

    for d in detections:
        conf = d.get("confidence", 0.0)
        cls = d.get("class_name", "").lower()
        if cls not in weights or cls in FINISHING_CLASSES or conf < conf_floor:
            continue
        soft[cls] += conf
        counts[cls] = counts.get(cls, 0) + 1
        if conf >= binary_conf_threshold:
            binary_hit[cls] = True

    # ── 2. Raw per-class ratios (dense: every weighted class gets a value) ──
    # Counts capture extent (how many elements exist); the stage grade
    # captures state (how complete each visible element is). Their product
    # is the fraction of the class's total work actually done.
    raw_ratios: dict[str, float] = {}
    for cls in weights:
        if cls in FINISHING_CLASSES:
            continue  # needs the wall ratio — computed below
        expected = (expected_components or {}).get(cls)
        if expected and expected > 0:
            base = min(1.0, soft[cls] / expected)
        else:
            base = 1.0 if binary_hit[cls] else 0.0
        if stage_fractions is not None and cls in STRUCTURAL_CLASSES:
            base *= max(0.0, min(1.0, stage_fractions.get(cls, 0.0)))
        raw_ratios[cls] = round(base, 4)

    # Finishing evidence is relative to *visible* walls; scaling by the wall
    # raw ratio expresses it against the whole building and guarantees
    # ρ(finish) ≤ ρ(wall) per frame.
    wall_raw = raw_ratios.get("wall", 0.0)
    for cls in FINISHING_CLASSES:
        if cls not in weights:
            continue
        frac = max(0.0, min(1.0, (finish_fractions or {}).get(cls, 0.0)))
        raw_ratios[cls] = round(min(1.0, wall_raw * frac), 4)

    # ── 3. Median smoothing, then ratchet ──
    ratios: dict[str, float] = {}
    window = (ratio_history or [])[-(MWPI_SMOOTH_WINDOW - 1):]
    for cls in weights:
        smoothed = median([h.get(cls, 0.0) for h in window] + [raw_ratios[cls]])
        latched = max((prior_ratios or {}).get(cls, 0.0), smoothed)
        ratios[cls] = round(min(1.0, latched), 4)

    # ── 3b. Structural implications ──
    # Applied top-down so each lift can feed the next. All lifts are max()
    # of monotone non-decreasing latches, so monotonicity is preserved.
    #
    # Roof ⇒ walls & columns: roofing starts only after blockwork reaches
    # the wall plate / ring beam, so a started roof (≥ the wall-plate stage)
    # proves the wall–column frame beneath it is complete. Below the
    # threshold, the lift is proportional. Both branches are monotone: the
    # roof latch is non-decreasing, and once the threshold is crossed it
    # stays crossed.
    roof_latched = ratios.get("roof", 0.0)
    for cls in ("wall", "column"):
        if cls in ratios:
            if roof_latched >= ROOF_IMPLIES_STRUCTURE_AT:
                ratios[cls] = 1.0
            else:
                ratios[cls] = max(ratios[cls], roof_latched)

    # Superstructure ⇒ foundation: standing superstructure proves the
    # foundation exists even when the camera can't see it (backfilled /
    # hidden behind the walls themselves). The latched trigger is monotone,
    # so once crossed it stays crossed and foundation stays latched at 1.0.
    if "foundation" in ratios:
        superstructure = max(
            ratios.get(cls, 0.0) for cls in ("column", "wall", "roof")
        )
        if superstructure >= FOUNDATION_IMPLIED_AT:
            ratios["foundation"] = 1.0

    # ── 3c. Physical ordering gate on latched values ──
    # Plaster is applied to walls, paint to plaster. Raw ratios satisfy this
    # by construction; the clamp re-enforces it after smoothing + latching
    # (e.g. against a latch polluted by a past misclassification), using the
    # implication-lifted wall ratio as the cap. min() of non-decreasing
    # latches is non-decreasing, so monotonicity is preserved.
    if "plastering" in ratios and "wall" in ratios:
        ratios["plastering"] = min(ratios["plastering"], ratios["wall"])
    if "painting" in ratios and "plastering" in ratios:
        ratios["painting"] = min(ratios["painting"], ratios["plastering"])

    # Held = credited above this frame's direct evidence (occluded classes
    # carried by the ratchet, or foundation credited by implication).
    held = [cls for cls in weights if ratios[cls] > raw_ratios[cls] + 1e-9]

    # ── 4. Weighted sum ──
    class_contributions: dict[str, float] = {}
    score = 0.0
    for cls, weight in weights.items():
        contribution = round(weight * ratios[cls], 4)
        if contribution > 0:
            class_contributions[cls] = contribution
            score += contribution

    return MwpiResult(
        score=round(min(1.0, score), 4),
        detected_classes=sorted(class_contributions.keys()),
        class_contributions=class_contributions,
        detected_counts=counts,
        soft_counts={cls: round(v, 4) for cls, v in soft.items() if v > 0},
        raw_ratios=raw_ratios,
        ratios=ratios,
        held_classes=sorted(held),
    )


def merge_latched_ratios(
    existing: dict[str, float] | None,
    new: dict[str, float],
) -> dict[str, float]:
    """
    Per-class max-merge of latched ratio dicts. Used when persisting project
    state so concurrent workers can never regress a latch (max is commutative
    and idempotent — a lost read costs nothing).
    """
    merged = dict(existing or {})
    for cls, ratio in new.items():
        merged[cls] = round(max(merged.get(cls, 0.0), ratio), 4)
    return merged


def avg_confidence(detections: list[dict[str, Any]]) -> float | None:
    """Return mean confidence across all detections, or None if empty."""
    if not detections:
        return None
    return round(sum(d.get("confidence", 0) for d in detections) / len(detections), 3)
