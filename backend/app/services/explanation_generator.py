"""
explanation_generator.py — Generate plain-English MWPI explanations via Claude.
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_CLASSES_IN_ORDER = ["foundation", "column", "wall", "roof", "plastering", "painting"]
# Finishing stages are measured as a fraction of wall progress, not counted
# elements — their status line is derived from contribution/weight instead.
_FINISHING_CLASSES = ("plastering", "painting")


def generate_explanation(
    mwpi_score: float,
    component_contributions: dict,
    plan_weights: dict,
    expected_counts: dict,
    detected_counts: dict,
    avg_confidence: float,
    planned_mwpi: Optional[float],
    schedule_deviation: Optional[float],
    schedule_status: Optional[str],
    week_number: Optional[int],
    project_name: str,
    class_ratios: Optional[dict] = None,
    held_classes: Optional[list] = None,
) -> str:
    """
    Call Claude to produce a plain-English site-supervisor summary of the MWPI score.
    Falls back to a template string if the API call fails.

    class_ratios are the SCORED (latched + implication-adjusted) completion
    ratios — the authoritative per-class status. Raw detection counts are
    only supporting context: a class can be complete while under-detected
    (occluded columns, backfilled foundation) because the ratchet and the
    structural implications (roof proves walls/columns/foundation) credit it.
    held_classes lists classes credited above this frame's direct evidence.
    """
    ratios = class_ratios or {}
    held = set(held_classes or [])

    detection_summary = []
    for cls in _CLASSES_IN_ORDER:
        detected = detected_counts.get(cls, 0)
        expected = expected_counts.get(cls) if expected_counts else None
        contribution = component_contributions.get(cls, 0.0)
        weight = plan_weights.get(cls, 0.0)
        ratio = ratios.get(cls)
        if ratio is None:  # legacy caller without ratios — derive from contribution
            ratio = contribution / weight if weight else 0.0

        if cls in _FINISHING_CLASSES:
            status = (
                f"~{round(ratio * 100)}% complete (from wall surface analysis)"
                if ratio > 0
                else "not started or not visible"
            )
        else:
            status = f"{round(ratio * 100)}% complete"
            if cls in held:
                status += (
                    " — credited by construction logic (proven by the stages "
                    "built on top of it) even though this photo shows less"
                )
            if expected:
                status += f"; visible in this photo: {detected}/{expected}"

        detection_summary.append(
            {
                "class": cls,
                "status": status,
                "contribution_pct": round(contribution * 100, 1),
                "max_possible_pct": round(weight * 100, 1),
            }
        )

    if planned_mwpi is not None and schedule_deviation is not None:
        schedule_context = (
            f"Project schedule context:\n"
            f"- Current week: {week_number}\n"
            f"- Planned MWPI target this week: {round(planned_mwpi * 100, 1)}%\n"
            f"- Actual MWPI: {round(mwpi_score * 100, 1)}%\n"
            f"- Deviation: {round(schedule_deviation * 100, 1)} percentage points\n"
            f"- Status: {schedule_status}"
        )
    else:
        schedule_context = "No project schedule has been set — schedule comparison unavailable."

    prompt = f"""You are a construction progress analyst for BuildWatch, a system that monitors \
residential building sites in Ghana using an AI camera. A YOLO11 model has just analysed \
a site image and computed a Milestone-Weighted Progress Index (MWPI) score.

Your job is to write a SHORT, plain-English explanation (3–5 sentences maximum) that tells \
the homeowner or investor:
1. What structural elements the camera can currently see and how complete each phase looks
2. Why the MWPI score is what it is (which classes are contributing and which aren't yet)
3. Whether the project is on track or behind schedule (if schedule data is available)

Rules:
- Write for a non-technical Ghanaian homeowner or diaspora investor, not an engineer
- The "status" field is the TRUTH about each phase — never contradict it. The \
"visible in this photo" counts only say what one camera angle shows; a phase at \
100% with fewer elements visible is still complete (e.g. columns fully up even if \
the photo only shows two of them — the roof could not be on otherwise, and the \
foundation is buried under the finished walls). Explain such cases with that \
natural logic instead of calling the phase "partial"
- Be specific about what was detected and what wasn't — don't be vague
- If something is at 0% contribution, say it hasn't started or isn't visible yet
- Keep it to 3–5 sentences, no bullet points, no headings
- Do not mention "MWPI", "confidence scores", "weights", or any technical terms
- Use natural construction language: "ground floor", "columns are up", "walls are rising", \
"roof frame not yet started", "foundation is complete", "walls have been plastered", \
"painting is underway"
- The building is only 100% complete when plastered AND painted — a roofed but \
unplastered structure is around 80%. If plastering or painting shows progress, mention \
what that implies (plastering means internal pipes and wiring are in the walls; painting \
means fittings like sockets and switches are done)
- Sound like a knowledgeable site supervisor giving a quick status update
- Do not start with "The" — vary the sentence opener

Project: {project_name}
Current overall progress: {round(mwpi_score * 100, 1)}%
Average AI detection confidence: {round((avg_confidence or 0) * 100, 1)}%

Per-class breakdown:
{json.dumps(detection_summary, indent=2)}

{schedule_context}

Write the explanation now (3–5 sentences, plain English, no bullet points):"""

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()

    except Exception as e:
        logger.warning(f"[explanation_generator] Claude API call failed: {e}")
        return _fallback_explanation(mwpi_score, component_contributions, schedule_status)


def _fallback_explanation(
    mwpi_score: float,
    component_contributions: dict,
    schedule_status: Optional[str],
) -> str:
    pct = round(mwpi_score * 100)
    active = [k for k, v in component_contributions.items() if v > 0]
    inactive = [k for k in _CLASSES_IN_ORDER if k not in active]

    parts = []
    if active:
        parts.append(f"{', '.join(active).capitalize()} elements are visible on site.")
    if inactive:
        parts.append(f"{', '.join(inactive).capitalize()} phases have not started yet.")
    parts.append(f"Overall build progress is at {pct}%.")

    if schedule_status == "DELAYED":
        parts.append("The project is running behind the planned schedule.")
    elif schedule_status == "ON_SCHEDULE":
        parts.append("Progress is on track with the planned schedule.")

    return " ".join(parts)
