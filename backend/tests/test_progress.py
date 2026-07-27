"""
Unit tests for MWPI v2 (app/services/ai/progress.py).

Pure-Python — no DB, no YOLO, no API keys. Run from backend/:
    python3 -m pytest tests/test_progress.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ai.progress import (  # noqa: E402
    MWPI_WEIGHTS,
    avg_confidence,
    compute_mwpi,
    ensure_v2_weights,
    merge_latched_ratios,
)


def det(cls: str, conf: float) -> dict:
    return {"class_name": cls, "class_id": 0, "confidence": conf, "bbox": [0, 0, 10, 10]}


# ── Soft counts ──────────────────────────────────────────────────────────

def test_soft_counts_are_confidence_sums():
    r = compute_mwpi(
        [det("wall", 0.5), det("wall", 0.45)],
        expected_components={"wall": 2},
    )
    assert r.soft_counts["wall"] == 0.95
    assert r.raw_ratios["wall"] == round(0.95 / 2, 4)
    assert r.class_contributions["wall"] == round(0.32 * 0.475, 4)


def test_detections_below_floor_ignored():
    r = compute_mwpi([det("column", 0.20)], expected_components={"column": 4})
    assert r.soft_counts == {}
    assert r.detected_counts == {}
    assert r.score == 0.0


def test_no_cliff_at_old_threshold():
    # v1 discarded a 0.39 detection entirely; v2 counts it as 0.39 of evidence.
    r = compute_mwpi([det("column", 0.39)], expected_components={"column": 4})
    assert r.soft_counts["column"] == 0.39
    assert r.raw_ratios["column"] == round(0.39 / 4, 4)


def test_ratio_capped_at_one():
    # Overdetection (7 confident columns, 4 expected) must not exceed full credit.
    r = compute_mwpi(
        [det("column", 0.9)] * 7,
        expected_components={"column": 4},
    )
    assert r.raw_ratios["column"] == 1.0
    assert r.class_contributions["column"] == 0.20


# ── Binary fallback (no plan) ────────────────────────────────────────────

def test_binary_fallback_needs_strong_detection():
    strong = compute_mwpi([det("foundation", 0.45)])
    weak = compute_mwpi([det("foundation", 0.35)])
    assert strong.raw_ratios["foundation"] == 1.0
    assert strong.class_contributions["foundation"] == 0.12
    assert weak.raw_ratios["foundation"] == 0.0
    assert "foundation" not in weak.class_contributions


# ── Ratchet (monotonicity) ───────────────────────────────────────────────

def test_ratchet_holds_occluded_class():
    # Columns latched at 0.6 previously; walls now hide them entirely.
    r = compute_mwpi(
        [det("wall", 0.8)],
        expected_components={"column": 10, "wall": 20},
        prior_ratios={"column": 0.6},
    )
    assert r.ratios["column"] == 0.6
    assert r.class_contributions["column"] == round(0.20 * 0.6, 4)
    # Columns at 0.6 also imply the foundation (substructure implication),
    # so both are credited above this frame's direct evidence.
    assert r.held_classes == ["column", "foundation"]
    assert "column" in r.detected_classes  # held classes still contribute


def test_mwpi_never_decreases_across_frames():
    expected = {"foundation": 2, "column": 10, "wall": 20}
    frames = [
        [det("foundation", 0.9), det("foundation", 0.85)],
        [det("foundation", 0.9), det("column", 0.8), det("column", 0.7)],
        # foundation backfilled + columns partially hidden by rising walls:
        [det("column", 0.6), det("wall", 0.7), det("wall", 0.65)],
        [det("wall", 0.7)] * 8,
        [],  # camera obstructed — nothing detected at all
    ]
    latched, history, scores = None, [], []
    for detections in frames:
        r = compute_mwpi(
            detections,
            expected_components=expected,
            prior_ratios=latched,
            ratio_history=history,
        )
        latched = merge_latched_ratios(latched, r.ratios)
        history.append(r.raw_ratios)
        scores.append(r.score)
    assert scores == sorted(scores), f"MWPI regressed: {scores}"
    assert scores[-1] == scores[-2]  # obstructed frame holds, doesn't drop


# ── Median smoothing (spike rejection) ───────────────────────────────────

def test_single_frame_spike_is_not_latched():
    # Two clean frames, then one spurious high-confidence wall.
    history = [{"wall": 0.0}, {"wall": 0.0}]
    r = compute_mwpi(
        [det("wall", 0.9)],
        expected_components={"wall": 2},
        ratio_history=history,
    )
    assert r.ratios["wall"] == 0.0  # median(0, 0, 0.45) = 0
    assert r.detected_counts["wall"] == 1  # still visible in counts/HUD


def test_confirmed_progress_latches_after_second_frame():
    history = [{"wall": 0.0}, {"wall": 0.45}]
    r = compute_mwpi(
        [det("wall", 0.9)],
        expected_components={"wall": 2},
        ratio_history=history,
    )
    assert r.ratios["wall"] == 0.45  # median(0, 0.45, 0.45)


# ── Weight-change invariance ─────────────────────────────────────────────

def test_latched_ratios_reweight_when_plan_uploaded():
    # Ratios are stored weight-free: uploading a plan mid-project re-scores
    # all latched progress under the new weights. A legacy structural-only
    # plan is scaled to make room for roof (0.16) + finishes (0.20).
    latched = {"foundation": 1.0, "column": 0.5}
    r = compute_mwpi(
        [],
        plan_weights={"foundation": 0.10, "column": 0.40, "wall": 0.50},
        prior_ratios=latched,
    )
    assert r.class_contributions["foundation"] == round(0.10 * 0.64, 4)
    assert r.class_contributions["column"] == round(0.40 * 0.64 * 0.5, 4)


def test_ensure_v2_weights_scales_legacy_plans():
    legacy = {"foundation": 0.10, "column": 0.40, "wall": 0.50}
    v2 = ensure_v2_weights(legacy)
    assert v2["roof"] == 0.16
    assert v2["plastering"] == 0.12
    assert v2["painting"] == 0.08
    assert v2["wall"] == round(0.50 * 0.64, 4)
    assert round(sum(v2.values()), 4) == 1.0
    # A plan missing only finishes keeps its structural ratios × 0.80.
    with_roof = {"foundation": 0.15, "column": 0.25, "wall": 0.40, "roof": 0.20}
    v2b = ensure_v2_weights(with_roof)
    assert v2b["roof"] == round(0.20 * 0.80, 4)
    assert round(sum(v2b.values()), 4) == 1.0
    # Already-complete weight dicts pass through untouched.
    assert ensure_v2_weights(MWPI_WEIGHTS) == MWPI_WEIGHTS


# ── Helpers ──────────────────────────────────────────────────────────────

def test_merge_latched_ratios_is_per_class_max():
    merged = merge_latched_ratios(
        {"wall": 0.5, "column": 0.9},
        {"wall": 0.7, "foundation": 1.0},
    )
    assert merged == {"wall": 0.7, "column": 0.9, "foundation": 1.0}
    assert merge_latched_ratios(None, {"wall": 0.3}) == {"wall": 0.3}


def test_avg_confidence():
    assert avg_confidence([]) is None
    assert avg_confidence([det("wall", 0.4), det("wall", 0.6)]) == 0.5


# ── Structural implications (roof ⇒ walls/columns ⇒ foundation) ──────────

def test_roofed_structure_earns_full_structural_credit():
    # The testrun case: strong wall + roof detections, foundation invisible
    # (backfilled), columns below the binary threshold. The roof proves the
    # wall–column system beneath it, and superstructure proves the
    # foundation → full structural credit (0.80), finishes still zero.
    r = compute_mwpi([det("wall", 0.55), det("roof", 0.79)])
    assert r.ratios["column"] == 1.0
    assert r.ratios["foundation"] == 1.0
    assert sorted(r.held_classes) == ["column", "foundation"]
    assert r.score == 0.80


def test_started_roof_implies_walls_and_columns_complete():
    # Roofing starts only after blockwork reaches the wall plate: a roof at
    # half stage (≥ ROOF_IMPLIES_STRUCTURE_AT) proves the wall–column frame
    # is finished — open window/door voids are finishing work, not missing
    # blockwork.
    r = compute_mwpi(
        [det("roof", 0.5)],
        expected_components={"roof": 1, "wall": 10, "column": 8},
    )
    assert r.raw_ratios["roof"] == 0.5
    assert r.ratios["wall"] == 1.0
    assert r.ratios["column"] == 1.0
    assert r.ratios["foundation"] == 1.0


def test_subthreshold_roof_lifts_proportionally():
    # Below the wall-plate stage (< 0.2) the roof evidence is too weak to
    # prove a complete frame — the lift stays proportional.
    r = compute_mwpi(
        [],
        prior_ratios={"roof": 0.15},
    )
    assert r.ratios["wall"] == 0.15
    assert r.ratios["column"] == 0.15
    assert r.ratios["foundation"] == 0.0  # 0.15 < FOUNDATION_IMPLIED_AT


def test_no_foundation_inference_below_threshold():
    # A sliver of wall evidence (latched 0.1 < 0.25) is not proof enough.
    r = compute_mwpi(
        [det("wall", 0.5)],
        expected_components={"wall": 5},
    )
    assert r.ratios["wall"] == 0.1
    assert r.ratios["foundation"] == 0.0
    assert "foundation" not in r.class_contributions


def test_foundation_inference_latches_permanently():
    # Once inferred, the merged latch keeps foundation at 1.0 even on a
    # later frame with no detections at all.
    first = compute_mwpi([det("column", 0.9)])
    assert first.ratios["foundation"] == 1.0
    latched = merge_latched_ratios(None, first.ratios)
    blank = compute_mwpi([], prior_ratios=latched)
    assert blank.ratios["foundation"] == 1.0


# ── Stage grading (completion fractions from the vision assessor) ────────

def test_stage_grade_scales_binary_ratio():
    # A bare truss frame detects as roof at high confidence, but graded 0.5
    # (frame erected, no cover) it earns only half the roof weight.
    r = compute_mwpi(
        [det("roof", 0.79)],
        stage_fractions={"roof": 0.5},
    )
    assert r.raw_ratios["roof"] == 0.5
    assert r.class_contributions["roof"] == round(0.16 * 0.5, 4)


def test_stage_grade_scales_plan_ratio():
    # Extent (soft count / expected) × state (grade): half the walls exist,
    # each at 80% of full height → 40% of total wall work done.
    r = compute_mwpi(
        [det("wall", 1.0)],
        expected_components={"wall": 2},
        stage_fractions={"wall": 0.8},
    )
    assert r.raw_ratios["wall"] == round(0.5 * 0.8, 4)


def test_stage_none_is_v2_behaviour():
    # Assessor disabled (no API key / mock mode): multiplier 1.0 everywhere.
    graded = compute_mwpi(STRUCTURE_DONE, stage_fractions=None)
    assert graded.score == 0.80


def test_stage_empty_dict_holds_ratchet():
    # Assessor errored mid-outage: {} zeroes structural raws so this frame
    # can't latch full credit; previously latched progress is held.
    r = compute_mwpi(
        STRUCTURE_DONE,
        stage_fractions={},
        prior_ratios={"roof": 0.5, "wall": 0.9},
    )
    assert r.raw_ratios["roof"] == 0.0
    assert r.ratios["roof"] == 0.5      # held, not advanced
    assert r.ratios["wall"] == 1.0      # implied by the held roof (≥ 0.2)
    assert "roof" in r.held_classes


def test_graded_roof_still_implies_complete_frame():
    # Roof graded 0.5 (trusses up) keeps only half the roof weight but still
    # proves the wall–column frame and foundation beneath it.
    r = compute_mwpi(
        [det("roof", 0.79)],
        stage_fractions={"roof": 0.5},
    )
    assert r.ratios["roof"] == 0.5
    assert r.ratios["wall"] == 1.0
    assert r.ratios["column"] == 1.0
    assert r.ratios["foundation"] == 1.0
    # = the supervisor-image shape: full structure except roof covering
    assert r.score == round(0.12 + 0.20 + 0.32 + 0.16 * 0.5, 4)  # 0.72


def test_finishing_uses_stage_scaled_wall_raw():
    # Plastering evidence is scaled by the graded wall raw ratio: walls at
    # 80% height, all visible ones plastered → plastering raw 0.8.
    r = compute_mwpi(
        [det("wall", 0.9)],
        stage_fractions={"wall": 0.8},
        finish_fractions={"plastering": 1.0, "painting": 0.0},
    )
    assert r.raw_ratios["wall"] == 0.8
    assert r.raw_ratios["plastering"] == 0.8


# ── Finishing stages (plastering / painting) ─────────────────────────────

STRUCTURE_DONE = [
    det("foundation", 1.0), det("column", 1.0),
    det("wall", 1.0), det("roof", 1.0),
]


def test_structural_completion_is_not_100_percent():
    # The supervisor's test case: roofed but unplastered/unpainted building
    # must NOT read 100%. Structural work caps at 0.80.
    r = compute_mwpi(STRUCTURE_DONE)
    assert r.score == 0.80
    assert "plastering" not in r.class_contributions
    assert "painting" not in r.class_contributions


def test_plastered_then_painted_reach_92_and_100_percent():
    plastered = compute_mwpi(
        STRUCTURE_DONE, finish_fractions={"plastering": 1.0, "painting": 0.0}
    )
    assert plastered.score == 0.92
    finished = compute_mwpi(
        STRUCTURE_DONE, finish_fractions={"plastering": 1.0, "painting": 1.0}
    )
    assert finished.score == 1.0


def test_finish_fraction_scales_with_wall_ratio():
    # Half the expected walls built, all of the visible ones plastered:
    # plastering progress against the whole building is 0.5 × 1.0.
    r = compute_mwpi(
        [det("wall", 1.0)],
        expected_components={"wall": 2},
        finish_fractions={"plastering": 1.0, "painting": 0.0},
    )
    assert r.raw_ratios["wall"] == 0.5
    assert r.raw_ratios["plastering"] == 0.5
    assert r.class_contributions["plastering"] == round(0.12 * 0.5, 4)


def test_painting_never_exceeds_plastering_nor_wall():
    # Ordering gate: a polluted latch (paint above plaster, plaster above
    # wall) is clamped back to the physical ordering.
    r = compute_mwpi(
        [],
        prior_ratios={"wall": 0.4, "plastering": 0.7, "painting": 0.9},
    )
    assert r.ratios["plastering"] == 0.4
    assert r.ratios["painting"] == 0.4
    assert r.ratios["wall"] == 0.4


def test_ratchet_holds_finish_progress_when_classifier_skips_a_frame():
    # finish_fractions=None (no walls visible / classifier failed) must not
    # regress previously latched finishing progress.
    r = compute_mwpi(
        [],
        prior_ratios={"wall": 0.8, "plastering": 0.6, "painting": 0.2},
        finish_fractions=None,
    )
    assert r.ratios["plastering"] == 0.6
    assert r.ratios["painting"] == 0.2
    assert "plastering" in r.held_classes


def test_v1_equivalence_when_stateless_and_confident():
    # With every milestone fully evidenced and no state, the weights
    # partition 1.0 exactly.
    r = compute_mwpi(
        STRUCTURE_DONE,
        finish_fractions={"plastering": 1.0, "painting": 1.0},
    )
    assert r.score == round(sum(MWPI_WEIGHTS.values()), 4)  # 1.0
