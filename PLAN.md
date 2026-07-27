# BuildWatch — Architectural Plan & Roadmap

Last updated: 2026-06-28

---

## ⚠️ RESUME HERE — Roof Model Retraining (left off 2026-06-28)

The roof class has been added to all backend code but the YOLO model has **not been retrained yet**. Docker is still running `MOCK_INFERENCE` mode. Before any other work, complete these steps:

**1. Open the Colab notebook**
`backend/buildwatch_best.pt.ipynb` — already updated for `ghana-construction v4`, nc=4, CLASS_NAMES = `["foundation", "column", "wall", "roof"]`

**2. Runtime → Change runtime type → T4 GPU**

**3. Run all cells top to bottom**
- Cell 7 (class distribution) — check roof has enough samples (flag if < 30)
- Experiments 1, 2, 3 each train ~30 min; all three weights auto-save to Google Drive
- Cell 12 (results table) — pick the best experiment by mAP@0.5

**4. Copy the winning `.pt` to the project**
```bash
cp ~/Downloads/<best_exp>.pt /Users/macbookpro/AIconstruction/backend/buildwatch_best.pt
```

**5. Rebuild and restart Docker**
```bash
cd /Users/macbookpro/AIconstruction
docker compose build --no-cache backend celery_worker
docker compose up -d --no-deps backend celery_worker
docker compose logs -f celery_worker   # confirm: "Loading YOLO11n model"
```

**6. Mark Task 8 as done in PROGRESS.md**

---

## System Overview

BuildWatch is a real-time IoT construction monitoring system. It captures site images on a Raspberry Pi, streams them to a FastAPI/Celery backend, runs YOLO11n inference to detect structural elements, and computes a novel **MWPI (Multi-class Weighted Progress Index)** score that reflects how far along a construction project is relative to the completed design.

The MWPI is the primary academic contribution of this capstone thesis.

---

## Current Architecture

```
Raspberry Pi (edge)
  └─ edge/main.py
       ├─ presence_check_job()  [every 10 min]  →  upload with capture_type=presence_check
       └─ progress_job()        [every 60 min]  →  upload with capture_type=progress
              │
              ▼ (HTTP multipart)
FastAPI backend
  ├─ POST /upload  →  MinIO raw-images bucket
  └─ dispatch Celery task
              │
              ▼
Celery Worker
  ├─ run_inference()         (progress images)
  │    └─ YOLO11n → MWPI → annotated image → PostgreSQL → Redis pub/sub
  └─ run_presence_check()   (presence_check images)
       └─ YOLO person count → WorkerPresenceReading → alerts → Redis pub/sub
              │
              ▼
React Dashboard
  ├─ Overview — MWPI ring, comparison slider, plan upload widget, alert panel
  ├─ Gallery  — grid of progress images only (presence_check filtered out)
  ├─ Analytics — MWPI trend chart, KPI cards
  └─ Alerts   — shift config, worker alert table
```

---

## MWPI Algorithm

### Formula

```
MWPI = Σ  weight(class) × min(1.0, detected_count(class) / expected_count(class))
       over classes in {foundation, column, wall}
```

### Weight sources (priority order)

| Priority | Source | When active |
|----------|---------|-------------|
| 1 | `ProjectPlan.plan_weights` (Claude-derived) | After building plan uploaded + analyzed |
| 2 | `project.bim_config` (manual) | If set via BIM config API |
| 3 | Hardcoded defaults | `foundation=0.20, column=0.30, wall=0.50` |

### Expected count sources (same priority order)

| Priority | Source |
|----------|--------|
| 1 | `ProjectPlan.expected_counts` (Claude-derived) |
| 2 | `project.bim_config.expected_components` |
| 3 | None (binary: detected or not, count = 1) |

### Plan-derived weights — implemented feature

When a contractor uploads a photo or render of the planned building:
1. Image stored in MinIO at `plans/{project_id}/{plan_id}.ext`
2. `analyze_plan` Celery task runs three-tier analysis:
   - **Tier 1**: Claude vision API (`claude-haiku-4-5-20251001`) — structural composition analysis → `{weights, expected_counts}`
   - **Tier 2**: YOLO11n on the plan image — bounding box area ratios as weight proxies
   - **Tier 3**: Hard defaults (`foundation=0.15, column=0.30, wall=0.55` / counts `2, 8, 16`)
3. Results stored in `ProjectPlan` row, picked up on next inference run
4. Frontend polls every 3s during analysis, shows visual weight bars + expected counts when done

---

## Known Limitations & Honest Assessment

### Why MWPI can over-report at early stages

The current YOLO model has 3 classes (`foundation`, `column`, `wall`). Once all 3 are visible at the site — even if only the ground floor is built — MWPI can reach 100% because `detected_count / expected_count` hits 1.0 for each class.

The plan-derived expected counts partially fix this: if the plan indicates 20 walls expected and the camera sees 4, wall contribution = 4/20 = 0.2 × weight. But this depends on the camera being able to count elements — which is not reliable with a single RGB camera due to occlusion.

### Occlusion problem

A single camera mounted on the site cannot see behind completed walls. Walls, columns, and foundations built in interior zones or on the far side of the building are simply invisible. This means:
- `detected_count` is always a lower bound
- MWPI is always an underestimate of reality (which is safe for progress reporting but means expected counts must account for the camera's field of view, not total building counts)

---

## Hardware Roadmap

### Phase 1 — Current (RGB camera, single angle)
- Raspberry Pi + Pi Camera Module 3
- 10-minute presence captures, 60-minute progress captures
- Best suited for open-frame construction stages (foundation, columns before walls close)

### Phase 2 — Recommended upgrade (Depth camera)
**This is the strongest available hardware academic contribution.**

A depth camera (Intel RealSense D435i or similar) adds a Z-axis to every pixel. This enables:
- **Volume estimation** — measure concrete poured (m³) per structural zone
- **Height measurement** — detect whether a wall has reached design height without occlusion
- **Spatial progress** — not just "is a wall present" but "how complete is this wall"

This changes MWPI from a binary-detection index to a volumetric completion ratio — a substantial academic advancement over the current work.

**Thesis framing:** "This work establishes the MWPI detection-based baseline. A depth camera extension would transform MWPI into a volumetric metric, which we identify as the highest-value direction for future work."

### Phase 3 — Multi-camera network (research scope)
- Fixed cameras at 4 corners + overhead
- Stereo reconstruction of the full build envelope
- Allows accurate counting of interior elements
- Out of scope for this thesis; recommend as future work

---

## YOLO Model Roadmap

### Current model (`buildwatch_best.pt`)
- YOLO11n, nc=3: `foundation`, `column`, `wall` — **deployed but being replaced**
- Trained on a small dataset
- `wall` class mAP@0.5 = 0.197 (low — false negatives likely)
- Binary presence detection only

### In-progress retraining (nc=4)
- Dataset: `ghana-construction v4` (Roboflow, workspace `chiomas-workspace`)
- Classes: `["foundation", "column", "wall", "roof"]`
- Notebook: `backend/buildwatch_best.pt.ipynb` (updated 2026-06-28)
- Roof MWPI weight: 0.00 until supervisor approves an assignment
- **Status: training not yet run — see resume block at top of this file**

### Recommended retraining direction

**Stage-based classes** — instead of 3 element types, train on construction stages:

| Class | Description | MWPI weight |
|-------|-------------|-------------|
| `foundation_laid` | Foundation poured and cured | 0.15 |
| `column_erected` | Column(s) standing | 0.20 |
| `slab_poured` | Floor slab complete per level | 0.25 |
| `wall_raised` | Wall panels at design height | 0.25 |
| `roof_on` | Roof structure installed | 0.15 |

This makes the MWPI score naturally increase as construction stages progress, eliminating the "100% too early" problem without needing expected element counts.

**Training data needed:** ~200 labeled images per stage, collected from actual Ghanaian residential construction sites. Could be a collaboration with the construction companies that partner with KNUST or UG Engineering departments.

---

## WPI Metric (Weighted Progress Index)

An alternative formulation that adds time-weighting to the MWPI:

```
WPI = MWPI × (1 - time_overrun_penalty)

where:
  time_overrun_penalty = max(0, (actual_days - planned_days) / planned_days)
```

This allows a project that is structurally complete (MWPI = 1.0) but behind schedule to have a WPI < 1.0, giving a single number that captures both physical and temporal progress.

**Note:** WPI is not yet implemented. It depends on `ScheduleMilestone` data being populated and may require supervisor discussion before inclusion in the thesis.

---

## Pending Features (not yet implemented)

### Authentication
No endpoints are currently protected. For a real deployment:
- JWT-based auth on all API endpoints
- Project-level access control (contractor sees only their projects)
- Not in scope for the thesis submission but needed before any real-world use

### Push notifications
When a `WorkerAlert` fires, the supervisor/contractor should receive a notification. Options:
- FCM push notifications via Firebase (requires mobile app)
- SMS via Twilio/Africa's Talking (most practical for Ghanaian contractors)
- Email via SendGrid
- Not implemented — identified as a low-priority extension

### Zone-level progress
The Analytics page has a zone heatmap UI but it runs on mock data. Implementing this would require:
- Adding a `Zone` model and assigning bounding box regions to zones
- Running MWPI per zone after each inference
- Significant additional work — leave as future work

---

## Deployment Checklist

Before the supervisor demo or submission:

- [ ] Set `ANTHROPIC_API_KEY` in `.env` — get key from console.anthropic.com
- [ ] Set `VITE_PROJECT_ID` in `dashboard/.env` — run `POST /api/v1/projects` to create project, copy UUID
- [ ] Verify `buildwatch_best.pt` is mounted in Docker: check `docker-compose.yml` volume under `celery_worker`
- [ ] Upload building plan image via Overview page — triggers Claude analysis
- [ ] Upload `POST /api/v1/projects/{id}/schedule` with milestone data
- [ ] Set working shift via Alerts page (start time, end time, expected headcount)
- [ ] Verify edge agent `.env` on Raspberry Pi: `BACKEND_URL`, `PROJECT_ID`, `ANTHROPIC_API_KEY`
- [ ] Enable systemd service: `sudo systemctl enable buildwatch-edge && sudo systemctl start buildwatch-edge`
- [ ] Run `docker compose up -d` and verify all 7 services healthy

---

## Thesis Documentation Notes

### What to present as academic contributions

1. **MWPI formula** — novel multi-class weighted index, grounded in standard construction element classification; adaptive weights when plan is uploaded
2. **Plan-derived weight extraction** — automatic extraction of site-specific weights from a building plan image via computer vision + LLM; removes manual configuration burden
3. **Dual-stream edge capture** — separating presence-check captures from progress captures at the edge, eliminating UI pollution and reducing alert false positives
4. **Consecutive-reading alert gate** — simple but principled approach to false positive reduction in IoT alert systems

### What to flag as limitations (be honest with Dr. Sowah)

- YOLO model wall class accuracy is low (mAP 0.197) — larger training set needed
- Single RGB camera cannot count occluded elements — depth camera is the principled fix
- Plan analysis accuracy depends on plan image quality — 3D renders give better results than 2D floor plans
- System currently has no authentication — not production-ready
