# BuildWatch — Integration Progress

Last updated: 2026-07-13 (Task 11 added — finishing stages)

---

## Integration Tasks Status

### TASK 1 — YOLO11n + MWPI Pipeline ✅ DONE

**Goal:** Replace legacy YOLOv8 Celery task with YOLO11n + MWPI computation.

**What was implemented:**
- `backend/app/services/ai/detector.py` — Loads `buildwatch_best.pt`, runs YOLO11n, draws color-coded bounding boxes per class (foundation/column/wall)
- `backend/app/services/ai/progress.py` — `compute_mwpi()` applies the MWPI formula exactly as specified; `avg_confidence()` helper
- `backend/app/tasks/inference.py` — Full pipeline: download from MinIO → YOLO11n → MWPI → draw HUD overlay → upload annotated image → persist to DB → broadcast Redis event
- `backend/app/models/image.py` — `InferenceResult` has `mwpi_score` (Float) and `detected_classes` (JSON) columns
- `backend/app/config.py` — defaults: model path = `buildwatch_best.pt`, confidence = 0.25

**MWPI HUD overlay drawn on annotated images:**
- Semi-transparent dark box in top-left
- Progress bar colored by score (green ≥0.7, orange ≥0.4, red <0.4)
- Per-class contribution listed below the bar

---

### TASK 2 — Plan vs Actual Schedule ✅ DONE

**Goal:** Store a project schedule (planned MWPI at each week) and serve deviation comparisons.

**What was implemented:**
- `backend/app/models/schedule.py` — `ScheduleMilestone` ORM model (`project_id`, `week_number`, `planned_date`, `planned_mwpi`, `label`)
- `backend/app/schemas/schedule.py` — `MilestoneIn/Out`, `ComparisonEntry`, `ComparisonOut` Pydantic schemas
- `backend/app/routers/schedule.py` — 3 endpoints:
  - `POST /api/v1/projects/{id}/schedule` — replaces schedule atomically; validates non-decreasing MWPI
  - `GET /api/v1/projects/{id}/schedule` — returns milestones ordered by week
  - `GET /api/v1/projects/{id}/comparison` — matches each milestone to the latest inference result on/before that date, returns deviation + status
- `backend/app/main.py` — schedule router registered
- `backend/app/database.py` — `schedule` model imported in `create_tables()`
- `backend/app/models/__init__.py` — `ScheduleMilestone` exported
- `dashboard/src/services/api.js` — `getSchedule()`, `setSchedule()`, `getComparison()` added

**Deviation logic (MWPI units):**
- `>= 0` → ON SCHEDULE
- `>= -0.10` → SLIGHTLY BEHIND
- `< -0.10` → DELAYED
- No actual data yet → PENDING (future) or DELAYED (past with no data)

---

### TASK 3 — WebSocket Real-time Updates ✅ DONE

**Goal:** Dashboard auto-updates when Celery finishes processing an image.

**What was implemented:**
- `backend/app/main.py` — WebSocket endpoint at `ws://host/api/v1/ws/projects/{project_id}`
  - Subscribes to Redis channel `project:{project_id}:events`
  - Streams inference completion events to browser
  - Clean async task management with proper disconnect cleanup
- Celery `inference.py` — publishes event to Redis after each completed inference
- `dashboard/src/hooks/useProjectSocket.js` — React hook, exposes `{ connected: boolean }`
- Worker monitor also publishes `worker_presence` events to the same channel

---

### TASK 4 — Wire Dashboard to Live API ✅ DONE

**Goal:** Replace all `mockData.js` references with real API calls.

**What was implemented:**
- `dashboard/src/services/api.js` — full API service layer for all endpoints
- `dashboard/src/pages/Overview.jsx` — fully wired:
  - MWPI progress ring, confidence score, detected classes → real `getProgress()`
  - Live/offline WebSocket indicator
  - Planned vs Actual bars, variance sparkline, status badge → real `getComparison()`
  - Progress Over Time chart → real `getTimeline()` + comparison milestones
  - Comparison slider ("Planned Model vs Actual Site") → shows latest `annotated_image_url` from `liveProgress`, updates live via WebSocket
  - Caption below slider → real capture timestamp and MWPI
  - MWPI "Detection-based · No BIM plan set" amber badge when no schedule configured
  - Alerts panel → fetches real worker alerts from API
- `dashboard/src/pages/Gallery.jsx` — fully wired:
  - Fetches `GET /api/v1/images?project_id=…&status=completed` on load
  - Grid shows real images (presigned MinIO URLs), MWPI badges, detected class chips, real timestamps
  - Modal toggles between raw and annotated image view
  - Refresh button + auto-refresh after upload
  - Upload modal dispatches to `POST /api/v1/upload`
- `dashboard/src/pages/Analytics.jsx` — KPI cards, trajectory chart, weekly rate chart all wired to live API; zone bars remain on mock data (no zone model in API)
- `dashboard/src/App.jsx` — polls real active worker alert count every 30s for sidebar badge

**Notes:**
- `VITE_PROJECT_ID` is set in `dashboard/.env` to the test project UUID
- Zone-level data (zone heatmap, zone bars in Analytics) remain on mock data — no zone model exists in the backend

---

### TASK 5 — Worker Activity Monitoring ✅ DONE

**Goal:** Detect late starts, low presence, and early departures using the existing YOLO camera. Generate real-time alerts for the contractor.

**New DB models — `backend/app/models/worker.py`:**
- `WorkShift` — contractor-configurable working hours: `contracted_start`, `contracted_end`, `expected_headcount`, `late_start_grace_minutes`, `active`
- `WorkerPresenceReading` — one headcount snapshot per presence_check image: `worker_count`, `captured_at`, `shift_id`, `image_id`
- `WorkerAlert` — fired alert record: `alert_type`, `severity`, `message`, `worker_count`, `triggered_at`, `resolved`, `resolved_at`

**New Celery task — `backend/app/tasks/worker_monitor.py`:**
- `run_presence_check(image_id)` — dispatched when `metadata.capture_type == "presence_check"`
- Downloads image → counts persons (mock: random 0–6; real: COCO-pretrained YOLO11n `yolo11n.pt`)
- Stores `WorkerPresenceReading` linked to active shift
- Evaluates 3 alert conditions (deduplicated per calendar day, require 2 consecutive readings):

| Alert type | Condition | Severity |
|---|---|---|
| `LATE_START` | 0 workers detected after grace period past contracted start | warning |
| `LOW_PRESENCE` | worker count < 50% of expected headcount during contracted hours | critical |
| `EARLY_DEPARTURE` | 0 workers detected with >60 min remaining in shift | critical |

- Publishes `worker_presence` WebSocket event on completion

**New API router — `backend/app/routers/worker.py`:**
- `POST /api/v1/projects/{id}/shifts` — create/replace active shift (deactivates previous)
- `GET /api/v1/projects/{id}/shifts` — get currently active shift
- `GET /api/v1/projects/{id}/worker-alerts` — list alerts, filterable by `resolved`
- `PATCH /api/v1/worker-alerts/{id}/resolve` — resolve an alert
- `GET /api/v1/projects/{id}/presence` — list presence readings newest-first

**Frontend — `dashboard/src/pages/Alerts.jsx`** (fully rewritten):
- WorkShift config panel — set start/end time, expected headcount, grace period; saved via API
- Latest presence strip — shows most recent worker count and reading time
- Live alert table — fetches from `GET /worker-alerts`, sortable, resolve action wired to `PATCH` endpoint
- Empty state guides contractor to configure a shift first

---

### TASK 6 — Dual-Stream Image Capture + False Positive Reduction ✅ DONE

**Goal:** Separate progress captures (MWPI) from presence-check captures (worker monitoring). Prevent presence images from polluting Gallery and the comparison slider. Reduce alert false positives caused by workers being on break during a single snapshot.

**Presence-check image separation — `backend/app/routers/images.py`:**
- `GET /api/v1/images` — now filters out images where `metadata.capture_type == "presence_check"` using PostgreSQL `json_extract_path_text`. Gallery never shows presence images.
- `GET /api/v1/projects/{id}/progress` — joins back to `Image` table and applies same filter, so a presence-check snapshot cannot override the Overview comparison slider.

**Windowed alert logic — `backend/app/tasks/worker_monitor.py`:**
- `_consecutive_low_readings(db, project_id, condition_fn, n=2)` helper added
- All three alert types now require 2 consecutive readings satisfying the condition before firing
- At a 10-minute capture interval, this means the problem must persist ~20 minutes — genuine absence, not a break

**Edge agent dual-schedule — `edge/main.py`:**
- Two independent capture jobs:
  - `presence_check_job()` — runs every `PRESENCE_INTERVAL` seconds (default 600 = 10 min), tags `capture_type: presence_check`
  - `progress_job()` — runs every `PROGRESS_INTERVAL` seconds (default 3600 = 1 hour), tags `capture_type: progress`
- Shared `_capture_and_enqueue(capture_type)` helper injects the tag into upload metadata
- New env vars: `PRESENCE_INTERVAL`, `PROGRESS_INTERVAL` (replace old `CAPTURE_INTERVAL`)
- `edge/buildwatch-edge.service` — systemd service file for auto-start on boot and crash recovery

---

### TASK 7 — Plan-Informed MWPI via Building Plan Upload ✅ DONE

**Goal:** Eliminate the "100% too early" MWPI problem without manually entering expected counts. Contractor uploads a photo or render of the planned building; AI automatically extracts site-specific weights and expected element counts; MWPI becomes genuinely proportional.

**Academic contribution:** MWPI weights are no longer hardcoded constants. They are derived from the specific building's design, making the metric site-adaptive. The formula becomes:

```
MWPI = Σ plan_weight(class) × min(1.0, detected_count / expected_count)
```

Where both `plan_weight` and `expected_count` are extracted automatically from the uploaded plan image via Claude vision API.

**New DB model — `backend/app/models/plan.py`:**
- `ProjectPlan` — stores plan image MinIO path, Claude-derived `plan_weights`, `expected_counts`, `analysis_status`, `analysis_notes`

**New Celery task — `backend/app/tasks/plan_analyzer.py`:**
- `analyze_plan(plan_id)` — three-tier analysis strategy:
  1. **Claude vision API** (primary) — sends plan image to `claude-haiku-4-5`, extracts weights and counts from the structural composition of the building
  2. **YOLO area analysis** (fallback) — runs `buildwatch_best.pt` on plan image, computes per-class bounding box area ratios as weights
  3. **Hard defaults** (last resort) — `foundation=0.15, column=0.30, wall=0.55` / counts `2, 8, 16`
- Stores results on `ProjectPlan` record, sets `analysis_status = "completed"`

**New API router — `backend/app/routers/plan.py`:**
- `POST /api/v1/projects/{id}/plan` — accepts plan image, stores in MinIO `plans/` prefix, deactivates old plan, queues `analyze_plan` task
- `GET /api/v1/projects/{id}/plan` — returns current plan with status, weights, expected counts, presigned image URL

**Updated `compute_mwpi()` — `backend/app/services/ai/progress.py`:**
- Accepts new `plan_weights` parameter; when provided, overrides the hardcoded `MWPI_WEIGHTS` dict
- When `expected_components` (from plan analysis) is also provided, MWPI is fully plan-informed

**Updated inference pipeline — `backend/app/tasks/inference.py`:**
- On each inference run, looks up the project's latest completed `ProjectPlan`
- Passes `plan_weights` and `expected_counts` to `compute_mwpi()`
- Falls back to legacy `project.bim_config` if no plan uploaded
- Falls back to binary detection if neither exists

**Frontend — `dashboard/src/pages/Overview.jsx`:**
- New "Building Plan" card below the comparison slider
- Upload button → file picker → POST to `/plan` endpoint
- Spinner with polling (every 3s) while Claude analyzes
- On completion: shows plan thumbnail + visual weight bars per class with expected counts
- "Replace" button to upload a new plan at any time

**Config and infrastructure:**
- `backend/app/config.py` — `anthropic_api_key` setting (empty = fallback to YOLO/defaults)
- `backend/requirements.txt` — `anthropic==0.40.0` added
- `docker-compose.yml` — `ANTHROPIC_API_KEY` passed to both `backend` and `celery_worker`
- `.env` — `ANTHROPIC_API_KEY=` placeholder added

---

### TASK 8 — Roof Class Model Preparation ⏳ TRAINING PENDING

**Goal:** Add `roof` as a 4th detection class (nc=4) to the YOLO11n model. Backend already updated; model weights need to be retrained in Colab before Docker can be switched to real inference.

**What was implemented (2026-06-28):**

- `backend/buildwatch_best.pt.ipynb` — Colab training notebook updated:
  - Dataset changed from two-dataset merge (DS1 v2 + DS2 v3) to single dataset: `ghana-construction v4` (Roboflow workspace `chiomas-workspace`)
  - `CLASS_NAMES = ["foundation", "column", "wall", "roof"]` (nc=4)
  - `DS_VERSION = 4` — new version with roof annotations
  - Old merge logic removed; replaced with single download + data.yaml patch cell
  - All `MERGED_DIR` references updated to `dataset.location`
  - MWPI weight for roof set to `0.00` in notebook config (pending supervisor approval)

- `backend/app/services/ai/detector.py`:
  - Docstring updated: nc=3 → nc=4, classes now include `roof (3)`
  - `_CLASS_COLORS` dict: `"roof": (30, 60, 200)` added (terracotta)
  - `_MOCK_CLASSES`: `(3, "roof")` added

- `backend/app/tasks/inference.py`:
  - `_draw_mwpi_overlay()` `class_colors` dict: `"roof": (30, 60, 200)` added (was missing — would have rendered roof with a grey dot)

- `backend/app/services/ai/progress.py`:
  - Docstring updated: nc=3 → nc=4, roof noted as detected but not yet weighted

- `docker-compose.yml`:
  - `MOCK_INFERENCE` build arg changed to `"false"` for both `backend` and `celery_worker`
  - `MOCK_INFERENCE=false` env var set on `celery_worker`
  - **Do not run `docker compose build` until `buildwatch_best.pt` (nc=4) is in place**

**What still needs to happen:**
1. Run the Colab notebook (all cells, T4 GPU) — ~30 min per experiment, 3 experiments total
2. Pick best experiment weights from Google Drive (`exp1_best.pt`, `exp2_best.pt`, or `exp3_best.pt`)
3. Copy winner to `backend/buildwatch_best.pt`
4. Run `docker compose build --no-cache backend celery_worker && docker compose up -d --no-deps backend celery_worker`
5. Confirm logs show `Loading YOLO11n model: buildwatch_best.pt` and `YOLO11n: N detection(s)` (not `MOCK_INFERENCE`)

**MWPI impact:** Roof detections will appear in bounding box overlays and `yolo_detections` JSON but will not affect MWPI score (weight = 0.00) until supervisor approves a weight assignment.

---

## Summary

| Task | Description | Status |
|------|-------------|--------|
| 1 | YOLO11n + MWPI inference pipeline | ✅ Done |
| 2 | Plan vs Actual schedule backend | ✅ Done |
| 3 | WebSocket real-time updates | ✅ Done |
| 4 | Wire dashboard to live API | ✅ Done |
| 5 | Worker Activity Monitoring (alerts) | ✅ Done |
| 6 | Dual-stream capture + false positive reduction | ✅ Done |
| 7 | Plan-informed MWPI via building plan upload | ✅ Done |
| 8 | Roof class — backend prepared, model retraining pending | ⏳ Training pending |
| 9 | Multi-project dashboard + UI polish (info overlays, image fix, mock fallbacks) | ✅ Done |
| 10 | MWPI v2 — soft counts + median smoothing + monotonic ratchet | ✅ Done |
| 11 | Finishing stages (plastering/painting) + roof weight — 100% only when painted | ✅ Done (formula sign-off pending) |

---

### TASK 11 — Finishing Stages: Plastering & Painting (MWPI v2 finishes) ✅ DONE

**Goal:** Fix the "100% at bare structure" flaw Dr. Sowah demonstrated with a test
image (roofed but unplastered building read 100%). Implements
`MWPI_V2_FINISHES_PROPOSAL.md`: structural work caps at **80%**, plastered reads
**92%**, and **100% requires painting**. Sequencing assumptions: plastered ⇒
first-fix plumbing & electrical done; painted ⇒ second-fix M&E done.

**Weights — `backend/app/services/ai/progress.py`:** foundation 0.12 / column 0.20
/ wall 0.32 / roof 0.16 / plastering 0.12 / painting 0.08 (roof proposal weights
× 0.80 + 0.20 finishing mass). Awaiting Dr. Sowah's formal sign-off on the
combined proposal; Chioma authorized implementation 2026-07-13.

**Measurement — `backend/app/services/ai/finish_classifier.py` (new):** YOLO wall
crops (top 6 by confidence, padded) are sent in ONE Claude Haiku vision request
that labels each `unplastered | plastered | painted`. No new dataset, no retrain.
Raw finishing ratio = wall raw ratio × fraction of visible walls
plastered/painted, so ρ(paint) ≤ ρ(plaster) ≤ ρ(wall) holds by construction; a
post-latch clamp re-enforces the ordering. Classifier failure/no-walls returns
None → ratchet holds prior finishing progress.

**Plumbing:**
- `inference.py` — classifier wired in after detection (real path); the Claude
  mock path (`_claude_site_inference`) now estimates plastering/painting
  fractions directly in its JSON; HUD colors for the two new classes.
- `plan_analyzer.py` — emits roof weight + expected count (Claude prompt + YOLO
  fallback + defaults now 4 structural classes). Finishing weights are injected
  at scoring time by `progress.ensure_v2_weights`, which also scales legacy
  structural-only plans (× 0.64 / × 0.80) so old plans can't reopen the flaw.
- `explanation_generator.py` — finishing classes in the summary with
  "% complete from wall surface analysis"; prompt explains the 80/92/100 rule
  and the first-fix/second-fix implication in homeowner language.
- Dashboard — `MWPISegmentRing` rebuilt with the six v2 segments (stale slab
  segment removed), `Overview` breakdown/plan panels + `Gallery` work labels +
  `mockData.MWPI_WEIGHTS` updated.

**Structural implications (added 2026-07-14, `progress.py` step 3b; proposal
§2.2):** each stage proves the stages that carry it. (1) Roof ⇒ walls &
columns — r(wall) and r(column) lifted to at least r(roof), proportional.
(2) Superstructure ⇒ foundation — any of column/wall/roof latched ≥
`FOUNDATION_IMPLIED_AT` (0.25) credits foundation at 1.0 permanently.
Motivated by live testing: backfilled foundations and blockwork-embedded
columns are invisible/low-confidence precisely because the building exists.
Implications run before the plaster/paint ordering gate so the lifted wall
ratio is the cap. Supervisor test image: 48% → 60% → **80%** — the exact
structural ceiling; only plastering (12%) and painting (8%) remain.

**Stage-graded ratios (added 2026-07-16, proposal §2.3):** detection counts
measure extent; a per-capture Claude-vision **stage assessor**
(`backend/app/services/ai/stage_assessor.py`, replaces finish_classifier.py)
measures state — grades each structural class 0–1 (roof: 0.5 = trusses no
cover; wall: fraction of storey height vs lintel datums) and classifies wall
surface state in ONE Haiku call (no added cost). Raw ratio = extent × grade
(`stage_fractions` param in compute_mwpi). When the project has an uploaded
plan image (3D render/elevation), it is sent alongside the site photo and
grading is relative to the finished design (`plan_image=yes` in worker log).
Failure semantics: no API key → ungraded v2 behaviour; assessor error → `{}`
= no structural evidence that frame, ratchet holds (an outage can't latch a
half-built element at full credit). Mock path unchanged (fractions baked in).
Supervisor image journey: 100% (v1) → 48% → 60% → 80% → 58.8% → **68%**
(graded: foundation 1.0, column 1.0, wall 1.0, roof 0.5, walls unplastered;
plan-informed weights). Future work: geometric measurement, YOLO sub-stage
classes.

**Roof-started ⇒ walls/columns complete (2026-07-17, Chioma's call):**
window/door openings are NOT wall incompleteness (frames/glazing are
finishing work; the surface dimension is plastering's job). Roofing begins
only after blockwork reaches the wall plate, so roof latched ≥
`ROOF_IMPLIES_STRUCTURE_AT` (0.2, the rubric's wall-plate stage) credits
wall AND column at 1.0; below 0.2 the lift stays proportional. Enforced in
BOTH layers so the issue can't recur: the formula (progress.py step 3b
threshold branch) and the assessor prompt (explicit RULE: roofing visible ⇒
grade wall exactly 1.0, openings/gables never deducted) — verified live:
Claude now grades wall 1.0 on the supervisor image.

**Tests:** `backend/tests/test_progress.py` — 29 passing (16 new): 80%
structural cap, 92%/100% plastered/painted, wall-ratio scaling, ordering gate
clamp, ratchet hold on classifier skip, legacy-plan weight normalization,
roof implication (full + proportional), foundation implication (trigger,
threshold, permanent latch), stage grading (binary × grade, plan × grade,
None = v2 compat, {} = hold, graded implications, finishing interplay).

**No migration needed:** MWPI state stores ratios (not contributions), so
history re-weights correctly under the new weights. Latched scores can only
drop *visually* in the sense that a structure-complete project now shows 80%
instead of 100% — expected and intended.

---

### TASK 10 — MWPI v2: Confidence-Weighted, Monotonic Progress Index ✅ DONE

**Goal:** Fix the two biggest theoretical flaws in the MWPI formula ahead of the thesis write-up: (1) hard 0.40 confidence cliff (a 0.39 detection counted for nothing, a 0.41 counted fully — bad for the low-mAP wall class), and (2) non-monotonicity (detected counts drop as walls occlude columns and backfill hides foundations, so the score could go *down* while the building goes up).

**Formula changes — `backend/app/services/ai/progress.py` (rewritten):**
- **Soft counts:** ñ(c) = Σ confidence for detections ≥ 0.25 floor; ratio ρ(c) = min(1, ñ(c)/E(c)). Binary fallback (no plan) still requires one detection ≥ 0.40 before awarding full weight.
- **Median smoothing:** raw ratios are median-filtered over the last 3 frames (`MWPI_SMOOTH_WINDOW`) so a single spurious detection cannot latch (≈ one-frame confirmation delay at ~2 captures/hour).
- **Ratchet:** r_t(c) = max(r_{t−1}(c), smoothed ρ_t(c)) — MWPI is monotone non-decreasing by construction. State stores *ratios*, not contributions, so a plan uploaded mid-project re-weights all latched progress correctly.
- `compute_mwpi()` now returns an `MwpiResult` dataclass (score, contributions, counts, soft counts, raw + latched ratios, `held_classes` for occluded-but-latched classes).

**Persistence:**
- `Project.mwpi_state` JSON — `{"latched_ratios": {...}, "updated_at", "reset_at"}`; updated under `SELECT … FOR UPDATE` with per-class max-merge (race-safe).
- `InferenceResult.class_ratios_raw` / `class_ratios` JSON — per-frame raw and latched ratios (feeds the smoothing window; also the dataset for the planned validation/ablation study).
- `database.create_tables()` now runs idempotent `ALTER TABLE … ADD COLUMN IF NOT EXISTS` migrations (no Alembic in this project).

**API:** `POST /api/v1/projects/{id}/reset-progress` clears the ratchet (rework/demolition escape hatch). `reset_at` fences pre-reset frames out of the median window so old ratios can't re-latch.

**HUD:** annotated-image overlay now appends `held` to classes carried by the ratchet while occluded.

**Tests:** `backend/tests/test_progress.py` — 13 unit tests (pure Python, no stack needed): soft-count math, floor/cliff behaviour, binary fallback, ratchet monotonicity across a simulated 5-frame build sequence (including a fully obstructed frame), spike rejection, weight-change invariance. All passing.

---

### TASK 9 — Multi-Project Dashboard + UI Polish ✅ DONE

**Goal:** Extend the BuildWatch dashboard to manage multiple construction sites from one interface, add informational overlays on KPI cards, fix image display, and clean up the MWPI card layout. All changes are frontend-only; backend and data remain unchanged.

**Multi-project support — new files:**

- `dashboard/src/data/mockData.js` — `MOCK_PROJECTS` array added with 3 fully-populated projects:
  - `site-001` Adjei Residence (East Legon, MWPI 61%, 4 active alerts, AI confidence 86%)
  - `site-002` Mensah Villa (Tema, MWPI 34%, 3 active alerts, AI confidence 78%)
  - `site-003` Owusu Duplex (Kumasi, MWPI 88%, 0 alerts, AI confidence 93%)
  - Each project carries: device telemetry, 14-week MWPI history, 12 gallery images, 6-phase schedule, alerts array

- `dashboard/src/context/ProjectContext.jsx` — React Context + `ProjectProvider` + `useProject()` hook; `selectedProjectId` state with `MOCK_PROJECTS[0]` as default

- `dashboard/src/components/ProjectSwitcher.jsx` — header dropdown listing all projects with MWPI colour pills (green ≥70%, amber ≥40%, red <40%) and status dots; closes on outside click

- `dashboard/src/pages/ProjectsPage.jsx` — "All Projects" card grid with ProgressRing, alert count, last photo date, "View Dashboard →" per card; "New Project" modal with 5 fields and success toast (UI only)

**Updated files:**

- `dashboard/src/main.jsx` — wrapped `<App>` in `<ProjectProvider>`
- `dashboard/src/App.jsx` — default page changed to `'projects'`; `ProjectsPage` case added to router; `onProjectSelect` callback wired to Header
- `dashboard/src/components/Sidebar.jsx` — "All Projects" nav item always visible at top; per-project section header and nav items shown when inside a project; alert badge reads from `selectedProject.alerts`
- `dashboard/src/components/Header.jsx` — renders `ProjectSwitcher`; solar % reads from `selectedProject.device`
- `dashboard/src/components/GradientCard.jsx` — `info` prop added; tapping ⓘ button toggles an info overlay inside the card (Info/X icon, `useState`)
- `dashboard/src/components/InsightCard.jsx` — same ⓘ info overlay pattern as GradientCard

**Overview page — `dashboard/src/pages/Overview.jsx`:**
- Removed "Class Contributions" breakdown bars section (was next to the MWPI ring)
- ComparisonSlider images changed from `objectFit: 'cover'` to `objectFit: 'contain'` — full plan/site image now visible
- 4 KPI cards now show contextual info on tap:
  - MWPI Score → formula explanation and class weights
  - Schedule Variance → deviation from planned MWPI at current week
  - AI Confidence → model confidence description
  - Schedule → phase timeline summary
- All derived values (MWPI, history, alerts, schedule, images) fall back to `selectedProject` when API is unreachable

**Gallery page — `dashboard/src/pages/Gallery.jsx`:**
- Images are now a computed derived value (not state) when no live API — eliminates async timing bug where `PROJECT_ID` set but backend unreachable resulted in 0 photos shown
- API failure (connection refused) now falls back to `selectedProject.images` (12 mock photos per project)
- Fixed `GALLERY_IMAGES` undefined reference in timelapse player
- `SiteThumbnail` accepts `fit` prop; lightbox modal uses `fit="contain"`

**Alerts page — `dashboard/src/pages/Alerts.jsx`:**
- API failure now falls back to `selectedProject.alerts` instead of silently setting empty array
- Status filter tabs (All / Active / Resolved) added
- Alert list handles both API format and mock format field names

**Analytics page — `dashboard/src/pages/Analytics.jsx`:**
- Trajectory chart falls back to `selectedProject.progress.history` when API unreachable

**Root cause fixed across all pages:** `VITE_PROJECT_ID` is set in `.env`, so all API-conditional branches hit the live path. When the backend is not running, individual `.catch(() => [])` calls were swallowing errors and returning empty data. Fixed by catching at the outer `try` block and falling back to `selectedProject` mock data on connection failure.

---

## Known Issues / Limitations

- `buildwatch_best.pt` must be mounted into the Docker worker container (verify volume mounts in `docker-compose.yml`)
- `wall` class has low mAP@0.5 (0.197) — detections may be unreliable at low confidence; MWPI threshold of 0.4 partially mitigates this
- MWPI reads 100% when all 3 classes detected and no building plan uploaded — upload a plan to get proportional scoring
- Person detection is mocked (`MOCK_INFERENCE=true`) — `_count_persons_real()` loads `yolo11n.pt` which is not in the current Docker image
- Plan analysis falls back to hard defaults when `ANTHROPIC_API_KEY` is not set — set the key in `.env` for accurate weight extraction
- Zone-level dashboard data (heatmap, Analytics zone bars) remains on mock data — no zone model in backend
- No authentication on any endpoint — out of scope for this version
- Single RGB camera has inherent occlusion limitations for element counting — see PLAN.md for hardware roadmap
