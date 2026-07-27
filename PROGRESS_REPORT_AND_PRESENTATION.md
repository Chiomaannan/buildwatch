# BuildWatch — Capstone Progress Report & Presentation

*Prepared following the Final Year Capstone Project Progress Report and Presentation Format (Parts A & B).*

---

# PART A — PROGRESS REPORT

## 1. Cover Page

| Item | Details |
|---|---|
| **Project Title** | BuildWatch: A Solar-Powered IoT and Computer Vision System for Remote Construction Progress Monitoring of Residential Buildings in Ghana |
| **Student Name** | Chioma Annan *(add student ID)* |
| **Department** | Department of Computer Engineering, School of Engineering Sciences |
| **Programme** | BSc Computer Engineering, University of Ghana |
| **Supervisor** | Dr. Nii Longdon Sowah |
| **Reporting Period** | *(adjust to departmental weeks, e.g. Week 1 – Week 8)* — June to mid-July 2026 |
| **Submission Date** | 15 July 2026 |

## 2. Executive Summary

Residential construction projects in Ghana are frequently financed by clients — including diaspora homeowners — who cannot visit their sites, leaving them exposed to delays, cost overruns, misreported progress, and material theft. BuildWatch addresses this with a solar-powered IoT camera unit (Raspberry Pi 4 + 4G) that autonomously photographs the site and an AI backend that converts each photo into an objective progress score: the **Milestone-Weighted Progress Index (MWPI)**, this project's original contribution.

The system is functionally complete end-to-end. A YOLO11n model (retrained July 2026 to five classes: foundation, column, wall, roof, worker) detects structural elements; the MWPI formula — now in its second major revision — converts detections into a monotonic, confidence-weighted score displayed on a real-time React dashboard alongside plan-vs-actual schedule tracking, worker presence alerts, AI-generated progress explanations, and building-plan-informed expectations. Live inference is operational (first real detection run: 11 July 2026, roof detected at 0.79 confidence).

Preliminary results: detection mAP@0.5 of 0.517; end-to-end inference in ~8 s per image; 23/23 unit tests passing; and MWPI v2 correctly scoring a structurally complete but unfinished building at 80% where the original formula erroneously read 100%.

Key challenges — a weak wall class (mAP 0.197), formula saturation flaws, and single-viewpoint visibility limits — have driven the main design revisions. Remaining work: a validation study against expert assessments, a model accuracy sprint, field deployment, and the final dissertation.

*(~240 words)*

## 3. Introduction / Background

Construction is one of Ghana's largest economic sectors, and 1–2 storey residential buildings dominate its output. A defining feature of this market is **remote financing**: many projects are funded by clients who live far from their sites — notably diaspora Ghanaians — and who depend entirely on phone calls, occasional photos from a foreman, or paid intermediaries to know what is happening with their money.

This information gap has well-known consequences: projects stall silently, funds are diverted, materials are stolen, and disputes arise because no objective record of progress exists. Conventional solutions (site visits, hired supervisors, drone surveys) are costly, intermittent, and still subjective.

Advances in edge computing and computer vision make a different approach feasible: a low-cost, autonomous camera unit that observes the site continuously and an AI pipeline that turns images into a **quantitative, auditable progress metric**. BuildWatch is such a system, designed specifically for the constraints of Ghanaian residential sites: no grid power (solar), no wired internet (4G), and no BIM models (a photo of the building plan substitutes).

**Target users/beneficiaries:** diaspora and remote homeowners; small/medium contractors (client trust and dispute protection); project financiers and mortgage providers requiring independent progress verification.

## 4. Problem Statement

| Question | Explanation |
|---|---|
| **What is the problem?** | Clients financing residential construction remotely have no objective, continuous, and trustworthy measure of physical progress on their sites. |
| **Who is affected?** | Diaspora homeowners, remote clients, small contractors (who cannot prove honest progress), and financiers who disburse funds against claimed milestones. |
| **Why does it matter?** | Progress misreporting enables fund diversion and theft; late discovery of delays multiplies cost; disputes lack evidence. Construction fraud against diaspora clients is a widely reported problem in Ghana. |
| **What gap exists?** | Existing progress-monitoring research assumes BIM models, laser scanning, or drone photogrammetry — infrastructure absent from Ghanaian residential sites. Consumer site cameras record video but do not *measure* progress. No existing solution produces an objective progress percentage from a low-cost fixed camera without BIM. |

## 5. Project Aim and Objectives

| Element | Statement |
|---|---|
| **Aim** | To design and implement a solar-powered IoT and computer vision system that autonomously monitors and quantifies the construction progress of residential buildings in Ghana. |
| **Objective 1** | To review existing construction progress-monitoring systems and identify their limitations in the Ghanaian residential context. |
| **Objective 2** | To design and build a solar-powered edge–cloud architecture (Raspberry Pi camera unit + containerised backend) for autonomous site image capture and processing. |
| **Objective 3** | To train and evaluate a YOLO11n object detection model for Ghanaian residential structural elements (foundation, column, wall, roof) and site workers. |
| **Objective 4** | To develop the Milestone-Weighted Progress Index (MWPI) — a novel formula converting detections into a monotonic, plan-informed progress score — together with schedule deviation tracking and worker-presence alerting. |
| **Objective 5** | To develop a real-time web dashboard and evaluate the end-to-end system against expert human progress assessments. |

## 6. Scope of the Project

**Included:**
- **Technical scope:** one fixed-viewpoint solar-powered camera unit per site; edge preprocessing; cloud inference; MWPI computation; real-time dashboard.
- **Functional scope:** progress scoring (MWPI), plan-vs-actual schedule deviation, worker presence monitoring with alerts (late start / low presence / early departure), photo gallery with annotated detections, AI-generated plain-language progress explanations, building-plan upload for site-specific expectations.
- **User scope:** single-organisation use (contractor/client); multi-project dashboard.
- **Hardware/software scope:** Raspberry Pi 4 + Camera Module V2 + 4G modem prototype; Dockerised backend; React dashboard.
- **Geographical scope:** 1–2 storey residential buildings typical of the Ghanaian market.

**Excluded:** commercial manufacturing and large-scale deployment; interior progress monitoring (fixed exterior camera); multi-camera fusion; BIM/laser-scan integration; user authentication and billing (out of scope for this version); structural *quality* assessment (the system measures progress, not workmanship).

## 7. Literature Review / Related Works Progress

| Theme | Key Ideas Reviewed | Relevance to Project |
|---|---|---|
| Vision-based progress monitoring | Automated progress tracking via site imagery compared against 4D BIM models; material-appearance classification for operation-level tracking (Han & Golparvar-Fard) | Confirms feasibility of camera-based progress measurement; exposes the BIM dependency BuildWatch must remove |
| Computer vision in construction | Survey of CV applications in construction — safety, productivity, progress (Paneru & Jeelani, *Automation in Construction*) | Positions progress monitoring within the field; identifies occlusion and viewpoint as recurring challenges |
| Object detection | One-stage detectors (YOLO family) trading accuracy for speed; YOLO11n as current lightweight variant suitable for edge/CPU deployment | Justifies model choice for a low-cost, near-real-time pipeline |
| IoT edge architectures | Edge buffering and store-and-forward patterns for unreliable connectivity; solar power budgeting for remote sensing nodes | Informs the Pi edge agent design (SQLite buffer, retry/backoff upload over 4G) |
| Construction sequencing | Standard first-fix/second-fix M&E ordering relative to plastering and painting (Chudley & Greeno, *Building Construction Handbook*) | Grounds the MWPI v2 sequencing assumptions: plastered ⇒ first-fix done; painted ⇒ second-fix done |

**Identified gap:** existing automated progress-monitoring approaches presuppose BIM models, laser scans, or drone photogrammetry, and produce measurements unsuited to low-cost fixed cameras. No reviewed system computes an objective progress index for BIM-less residential sites from a single fixed camera — the gap MWPI addresses.

## 8. Methodology / Design Approach

The project follows the standard engineering process, executed iteratively:

**Problem Identification → Requirements Gathering → System Design → Implementation / Prototype Development → Testing and Evaluation → Final Documentation**

1. **Requirement analysis** — user needs of remote clients and contractors; site constraints (power, connectivity, no BIM).
2. **System design** — edge–cloud architecture; MWPI formula design; database and API design.
3. **Hardware/software selection** — Raspberry Pi 4 + Camera V2 + Huawei 4G modem; YOLO11n; FastAPI/Celery/PostgreSQL/Redis/MinIO in Docker; React dashboard.
4. **Prototype development** — iterative, task-based (11 integration tasks to date), with the formula revised in response to live-test evidence.
5. **Testing and evaluation** — unit tests on the MWPI engine (23 tests); live inference tests on real site photos; planned validation study against expert scores (Spearman ρ, MAE).
6. **Documentation** — dissertation, proposals for each formula revision (kept as auditable design records), and this progress report.

A distinctive feature of the methodology is **evidence-driven formula revision**: each MWPI change was motivated by a documented failure case observed in live testing, written up as a formal proposal, and only then implemented — an audit trail that itself forms part of the thesis narrative.

## 9. System Design / Proposed Architecture

```
┌──────────────── SITE ────────────────┐
│  Raspberry Pi 4 (solar-powered)      │
│   ├─ Camera Module V2                │
│   ├─ Edge agent: capture →           │
│   │   blur/brightness check → CLAHE  │
│   │   → resize 640×640 → SQLite      │
│   │   buffer → HTTP upload w/ retry  │
│   └─ Huawei E3372h 4G modem          │
└──────────────────┬───────────────────┘
                   │ JPEG over 4G
┌──────────────────▼───────────────────┐
│  BACKEND (Docker Compose, 7 services)│
│   FastAPI API ── PostgreSQL (data)   │
│      │           MinIO (raw +        │
│      │            annotated images)  │
│      ▼           Redis (queue +      │
│   Celery worker   pub/sub)           │
│    ├─ YOLO11n detection (5 classes)  │
│    ├─ Finish classifier (wall crops  │
│    │   → Claude vision: unplastered/ │
│    │   plastered/painted)            │
│    ├─ MWPI v2 computation            │
│    ├─ Worker presence + alerts       │
│    └─ AI explanation generator       │
└──────────────────┬───────────────────┘
                   │ REST + WebSocket
┌──────────────────▼───────────────────┐
│  React Dashboard (Vite + Tailwind)   │
│   Projects · Overview · Analytics ·  │
│   Gallery · Alerts — live updates    │
└──────────────────────────────────────┘
```

| Component | Function |
|---|---|
| Edge camera unit | Autonomous dual-schedule capture: hourly *progress* photos and 10-minute *presence-check* photos; offline buffering for 4G dropouts |
| FastAPI backend | REST API, WebSocket event streaming, image intake |
| Celery worker | Asynchronous AI pipeline: detection → finish classification → MWPI → annotated overlay → persistence → broadcast |
| PostgreSQL | Projects, images, inference results, schedules, shifts, alerts, latched MWPI state |
| MinIO | S3-compatible storage for raw and annotated images |
| Redis | Task queue and real-time pub/sub |
| Dashboard | Multi-project monitoring UI with real-time MWPI, schedule comparison, gallery, and alert management |

**The MWPI algorithm (original contribution).** `MWPI = Σ w(c) × r(c)` over six milestone classes — foundation 0.12, column 0.20, wall 0.32, roof 0.16, plastering 0.12, painting 0.08 *(weights pending formal supervisor sign-off)*. Per-class completion ratios use **soft counts** (detections contribute their confidence above a 0.25 floor), are divided by **plan-derived expected counts** (extracted automatically from an uploaded building-plan image via vision AI), **median-smoothed** over 3 frames, and **latched monotonically** (a ratchet — construction progress is physically irreversible, while *detectability* is not: walls occlude columns, backfill hides foundations). **Structural implications** encode sequencing logic: a detected roof proves the walls and columns beneath it; any superstructure proves the foundation. Finishing stages are measured by a two-stage pipeline (YOLO wall crops classified as unplastered/plastered/painted) so that a structurally complete building reads 80%, plastered 92%, and **100% only when painted**.

## 10. Work Completed So Far

| Task | Description | Status | Evidence / Output |
|---|---|---|---|
| Literature review | Related works in vision-based progress monitoring, YOLO detection, IoT edge design, construction sequencing | Completed (refresh ongoing) | Dissertation draft chapter; citations in design proposals |
| Requirements analysis | User and system requirements from Ghanaian residential context | Completed | CONTEXT.md; scope definition |
| System architecture | Full edge–cloud design, database schema, API design | Completed | Architecture diagram; 7-service docker-compose; ERD |
| Dataset & model v1 | Labelled Ghanaian construction dataset (Roboflow); YOLO11n trained, 3 classes | Completed | mAP@0.5 = 0.517; training notebook |
| Dataset & model v2 | Slab class removed; roof + worker classes added (nc=5); retrained | Completed (July 2026) | `buildwatch_best.pt` v2; live detections |
| Inference pipeline | Download → YOLO11n → MWPI → annotated overlay → store → broadcast | Completed | Celery task; annotated images with HUD |
| MWPI v1 → v2 | Binary → plan-informed → confidence-weighted monotonic index | Completed | `progress.py`; 2 formal proposals; 23 unit tests |
| MWPI v2 finishes | Plastering/painting milestones; roof weight; structural implications | Completed (weights sign-off pending) | Proposal doc; supervisor test image now reads 80% |
| Plan-informed expectations | Building-plan photo upload → AI-extracted weights & expected counts | Completed | Plan analyzer task; dashboard plan card |
| Schedule tracking | Planned vs actual MWPI per week, deviation status | Completed | Schedule API + Overview charts |
| Worker monitoring | Presence counting via model's own `worker` class; 3 alert types with false-positive suppression | Completed | Alerts page; alert records |
| Real-time dashboard | Multi-project React UI, WebSocket live updates, gallery, analytics | Completed | Dashboard screenshots |
| AI explanations | Plain-language progress summaries per image (vision LLM) | Completed | InsightCard on dashboard |
| Edge agent | Dual-schedule capture, preprocessing, offline buffer, systemd service | Completed (field deployment pending) | `edge/` module |
| Validation study | Expert ground-truth comparison (Spearman ρ, MAE) | Ongoing | Validation-set freeze in progress |

## 11. Preliminary Implementation / Prototype

| Module | Current Status |
|---|---|
| Edge capture agent (Pi) | Completed — bench-tested; field deployment pending |
| Image intake + storage (API, MinIO) | Completed |
| YOLO11n detection (5 classes) | Completed — live inference operational since 11 July 2026 |
| MWPI v2 engine (soft counts, ratchet, implications, finishes) | Completed — 23/23 unit tests passing |
| Finish classifier (plastered/painted) | Completed — two-stage vision pipeline |
| Plan analyzer (weights from plan photo) | Completed |
| Schedule / deviation tracking | Completed |
| Worker presence + alerts | Completed |
| Real-time dashboard (5 pages) | Completed |
| AI explanation generator | Completed |
| Validation & evaluation module | Ongoing |
| Authentication | Excluded (out of scope) |

Evidence to attach: dashboard screenshots (Overview ring + comparison slider, Gallery with annotated detections, Alerts), an annotated site photo showing bounding boxes + MWPI HUD, the training notebook results, and the test suite output.

## 12. Preliminary Results / Findings

| Metric / Test | Preliminary Result |
|---|---|
| Detection accuracy (mAP@0.5, model v1 baseline) | **0.517** overall — foundation 0.531, column 0.519, wall 0.197 |
| First live inference (Spintex site, 11 Jul 2026) | Roof detected at **0.79** confidence; walls and columns detected correctly |
| End-to-end pipeline latency | **~7.9 s** per image (upload → detection → MWPI → dashboard event) |
| MWPI correctness — supervisor test image | v1 formula: **100%** (flaw — building unplastered/unpainted); v2 finishes: **80%** — exactly the structural ceiling, as designed |
| MWPI unit tests | **23/23 passing** (soft counts, ratchet monotonicity, ordering gates, structural implications, weight-change invariance) |
| Alert false-positive suppression | Alerts require 2 consecutive low readings (~20 min persistence) — single-snapshot breaks no longer trigger alerts |
| Dashboard real-time update | Sub-second via WebSocket after inference completes |
| Edge resilience | Offline SQLite buffering with retry/backoff verified on bench |

**Key finding for the thesis:** the live tests exposed — and the formula revisions fixed — three systematic failure modes of naive detection-based progress scoring: (1) *saturation* (100% at bare structure), (2) *non-monotonicity* (score dropping as later work occludes earlier work), and (3) *invisibility of completed early stages* (backfilled foundations score zero). The documented journey of the supervisor's test image (100% → 48% → 60% → 80%) is direct evidence of each fix.

## 13. Challenges Encountered

| Challenge | Effect on Project | Mitigation |
|---|---|---|
| Weak `wall` class (mAP 0.197) | Wall detections at low confidence depress MWPI | Soft-count formulation credits partial confidence; accuracy sprint (relabelling + augmentation) planned; roof→wall structural implication partially compensates |
| MWPI saturation flaw (100% at bare structure) | Score misrepresented completion; found by supervisor's test | Redesigned formula: finishing milestones added — 100% now requires painting (v2 finishes, implemented) |
| Occlusion / non-monotonicity | Score could *decrease* as building progressed | Monotonic ratchet + median smoothing + structural implications (implemented, unit-tested) |
| Single fixed viewpoint vs whole-building expected counts | Per-class ratios capped below 1.0 (camera sees one façade) | Roof implication partially offsets; per-viewpoint visibility factor designed as follow-up |
| Dataset quality (slab class ambiguity) | Confused labels reduced model quality | Slab class removed; dataset relabelled; worker class added; model retrained (v2) |
| Mock-data contamination of test state | Early latched scores mixed simulated and real evidence | Progress-reset endpoint added; state reset before validation runs |
| Intermittent 4G connectivity at sites | Risk of losing captures | Edge SQLite buffering with retry/backoff |
| Time constraints (~4 weeks to submission) | Limits scope of retraining and field trials | Two-stage finish classification chosen over retraining (no new dataset needed); prioritised work plan (§16) |

## 14. Changes Made to Original Plan

1. **MWPI formula evolution (core change).** Binary detection → plan-informed ratios → v2 (confidence-weighted soft counts, median smoothing, monotonic ratchet) → v2-finishes (six milestones including plastering/painting, structural sequencing implications). *Justification:* each revision fixed a failure mode demonstrated on real imagery; the evolution strengthens the academic contribution. Each change is documented in a formal proposal; final weights await supervisor sign-off.
2. **Dataset classes revised: slab removed, worker added (nc=3 → 5).** *Justification:* slab annotations were ambiguous and degraded training; a dedicated worker class lets one model serve both progress and presence monitoring — removing a second COCO model from the pipeline (faster, lighter, more relevant to site imagery).
3. **Building-plan photo upload replaced manual BIM configuration.** *Justification:* target sites have no BIM; AI extraction of expected counts from a plan photo makes plan-informed scoring practical for real users.
4. **Finishing stages measured by two-stage classification instead of YOLO retraining.** *Justification:* feasible within the remaining timeline (no new labelled dataset); dedicated detector classes documented as future work.
5. **Dual-stream capture added (progress vs presence-check photos).** *Justification:* prevents presence snapshots from polluting progress records and reduces alert false positives.

## 15. Work Remaining

| Remaining Task | Expected Output |
|---|---|
| Formal supervisor sign-off on MWPI v2 weights | Approved weight set recorded in dissertation |
| Validation study vs expert assessments | Spearman ρ / MAE tables; finish-classifier confusion matrix |
| Model accuracy sprint (focus: wall class) | Retrained model, target mAP@0.5 ≈ 0.55 |
| Per-viewpoint visibility factor | Corrected expected counts; updated proposal |
| Field deployment of edge unit on live site | Multi-day autonomous capture log; solar/4G performance data |
| WhatsApp progress digest + time-lapse generation | Weekly client-facing summary; time-lapse video from gallery |
| Final dissertation | Completed capstone document |
| Final presentation + demo video | Defense slides; recorded end-to-end demonstration |

## 16. Updated Work Plan / Timeline

| Activity | Wk 1 (15–21 Jul) | Wk 2 (22–28 Jul) | Wk 3 (29 Jul–4 Aug) | Wk 4 (5–11 Aug) | Wk 5 (12–18 Aug) |
|---|---|---|---|---|---|
| Weights sign-off + validation-set freeze | ✅ | | | | |
| Accuracy sprint (relabel, retrain, evaluate) | ✅ | ✅ | | | |
| Validation study (expert scores, ρ/MAE) | | ✅ | ✅ | | |
| Visibility factor implementation | | ✅ | ✅ | | |
| Field deployment + WhatsApp digest/time-lapse | | | ✅ | ✅ | |
| Dissertation writing | ✅ | ✅ | ✅ | ✅ | |
| Final slides, demo video, defense rehearsal | | | | ✅ | ✅ |

*(Align week numbers/dates to the department's official schedule.)*

## 17. Expected Final Deliverables

1. Final dissertation (with MWPI formal specification and validation results)
2. Working prototype — solar edge unit + backend + dashboard
3. Source code repository (edge, backend, dashboard)
4. Labelled Ghanaian construction dataset (Roboflow) + trained model weights
5. Test results — unit tests, model metrics, validation study
6. Design-decision audit trail (MWPI proposals)
7. User manual (contractor/client setup guide)
8. Demonstration video (site photo → live dashboard update)
9. Final presentation slides and poster

## 18. Conclusion

BuildWatch has progressed from concept to a **functionally complete, live end-to-end system**: an autonomous solar-powered camera unit, a five-class detection model running real inference, a novel and now twice-revised progress index (MWPI), and a real-time multi-project dashboard with schedule tracking, worker alerts, and AI explanations. The most significant progress this period is scientific as much as technical: live testing exposed three systematic failure modes of detection-based progress scoring, and each was analysed, formally proposed, fixed, and unit-tested — turning the MWPI from a simple weighted sum into a defensible academic contribution. The project is on track for completion; the remaining month focuses on validation against expert ground truth, a model accuracy sprint, field deployment, and the final dissertation.

## 19. References (IEEE style — expand as needed)

[1] J. Redmon, S. Divvala, R. Girshick, and A. Farhadi, "You Only Look Once: Unified, Real-Time Object Detection," in *Proc. IEEE Conf. Computer Vision and Pattern Recognition (CVPR)*, 2016, pp. 779–788.
[2] Ultralytics, "YOLO11 Documentation," 2024. [Online]. Available: https://docs.ultralytics.com
[3] S. Paneru and I. Jeelani, "Computer vision applications in construction: Current state, opportunities & challenges," *Automation in Construction*, vol. 132, 2021.
[4] K. K. Han and M. Golparvar-Fard, "Appearance-based material classification for monitoring of operation-level construction progress using 4D BIM and site photologs," *Automation in Construction*, vol. 53, pp. 44–57, 2015.
[5] R. Chudley and R. Greeno, *Building Construction Handbook*, 12th ed. Abingdon, UK: Routledge, 2020.

## 20. Appendices

- A. System architecture and data-flow diagrams
- B. Dashboard screenshots (Overview, Gallery, Alerts, Analytics, Projects)
- C. Annotated inference samples (bounding boxes + MWPI HUD)
- D. MWPI formal specification and proposals (roof; v2 finishes)
- E. Model training results (per-class metrics, training curves)
- F. Unit test listing and output (23 tests)
- G. Database schema
- H. Supervisor meeting log
- I. Dataset samples (Roboflow export)

---
---

# PART B — PROGRESS PRESENTATION (slide-by-slide)

**Target: 15–17 slides. Flow: Problem → Aim → Design → Work Completed → Evidence → Challenges → Remaining Work → Deliverables.**

### Slide 1 — Title
BuildWatch: A Solar-Powered IoT and Computer Vision System for Remote Construction Progress Monitoring in Ghana
Chioma Annan · Dept. of Computer Engineering, University of Ghana · Supervisor: Dr. Nii Longdon Sowah · July 2026

### Slide 2 — Outline
Background → Problem → Aim & Objectives → Scope → Related Works → Methodology → Architecture → Work Completed → Live Demo Evidence → Preliminary Results → Challenges → Remaining Work & Timeline → Deliverables → Conclusion

### Slide 3 — Background / Motivation
- Many Ghanaian residential projects are financed remotely (esp. diaspora homeowners)
- Clients rely on phone calls and a foreman's photos — no objective record
- Consequences: silent delays, fund diversion, material theft, disputes
- **One strong visual:** photo of a typical site + the question *"How complete is this building — and can you prove it?"*

### Slide 4 — Problem Statement
- **Current situation:** progress-monitoring research assumes BIM/laser scans/drones — absent on Ghanaian residential sites
- **Problem:** remote clients cannot objectively verify physical progress
- **Consequence:** overpayment against false claims, late delay discovery, disputes without evidence
- **Project response:** a low-cost autonomous camera + AI index (MWPI) that turns site photos into an auditable progress percentage

### Slide 5 — Aim and Objectives
Aim + the 5 objectives from §5 in a clean table. (Optionally tick-mark objectives 1–4 as substantially achieved.)

### Slide 6 — Scope
| Included | Excluded |
|---|---|
| Prototype edge unit + cloud backend + dashboard | Commercial deployment |
| Progress scoring, schedule deviation, worker alerts | Interior monitoring (exterior camera) |
| Plan-photo-informed expectations | BIM/laser-scan integration |
| 1–2 storey Ghanaian residential buildings | Authentication/billing; workmanship quality |

### Slide 7 — Related Works Summary
3–5 rows: BIM-based progress tracking (Han & Golparvar-Fard) — accurate but needs BIM · CV-in-construction surveys (Paneru & Jeelani) — occlusion/viewpoint challenges · YOLO one-stage detectors — speed/cost fit for edge · Construction sequencing handbooks — grounds MWPI's inference rules.
**Gap:** no system measures progress objectively from one fixed camera on a BIM-less site → MWPI.

### Slide 8 — Methodology
Process diagram: Requirements → Design → Implementation (11 integration tasks) → Testing → Evaluation → Documentation.
**Highlight the project's signature loop:** *live failure case → formal proposal → implementation → unit tests* (three cycles completed).

### Slide 9 — System Architecture
The architecture diagram from §9 (edge → backend → dashboard). Walk one image through the pipeline: capture → 4G upload → YOLO11n → finish classifier → MWPI → dashboard updates in real time.

### Slide 10 — The MWPI (core contribution)
- `MWPI = Σ w(c) × r(c)` over 6 milestones: foundation 0.12 / column 0.20 / wall 0.32 / roof 0.16 / plastering 0.12 / painting 0.08
- Soft counts (confidence-weighted) ÷ plan-derived expected counts
- Median smoothing + monotonic ratchet (progress can't go backwards)
- Structural implications: roof ⇒ walls/columns; superstructure ⇒ foundation
- **Punchline:** structure = 80%, plastered = 92%, **100% only when painted**

### Slide 11 — Work Completed
Condensed table from §10 — every subsystem Completed except the validation study (Ongoing). Evidence column: screenshots, model weights, 23 passing tests, live inference log.

### Slide 12 — Prototype / Implementation Evidence
2×2 screenshot grid: Overview (MWPI ring + plan-vs-actual) · Gallery (annotated detections) · Alerts (worker presence) · an annotated site photo with bounding boxes + MWPI HUD. Offer a **live demo** if the panel permits.

### Slide 13 — Preliminary Results
- mAP@0.5 = 0.517 (foundation 0.531 · column 0.519 · wall 0.197)
- Live inference: roof at 0.79 confidence; ~8 s photo-to-dashboard
- 23/23 MWPI unit tests passing
- **Star exhibit — one chart:** supervisor's test image under successive formulas: 100% (v1, wrong) → 48% → 60% → **80% (v2, exactly the structural ceiling)**

### Slide 14 — Challenges & Mitigation
4 rows from §13: weak wall class → soft counts + accuracy sprint · formula saturation → finishing milestones (fixed) · occlusion/non-monotonicity → ratchet + implications (fixed) · single viewpoint → visibility factor (planned).

### Slide 15 — Remaining Work & Timeline
Gantt from §16: sign-off + validation study, accuracy sprint, field deployment, WhatsApp digest/time-lapse, dissertation, defense — 5 weeks.

### Slide 16 — Expected Deliverables + Conclusion
Deliverables list (§17). Conclusion: end-to-end system is live; MWPI is a defensible, evidence-hardened contribution; remaining month = validation + polish + writing.

### Slide 17 — Questions
**Thank You. Questions and Suggestions.**

---

## Quick Submission Checklist (self-check)

| Item | Status |
|---|---|
| Cover page complete | ☑ (add student ID + official reporting weeks) |
| Executive summary 150–250 words | ☑ (~240) |
| Problem statement clear | ☑ |
| Aim/objectives aligned | ☑ |
| Scope defined | ☑ |
| Related works + gap | ☑ (expand citations for final report) |
| Methodology explained | ☑ |
| Architecture diagram | ☑ (replace ASCII with drawn diagram for submission) |
| Work completed w/ evidence | ☑ (attach screenshots) |
| Preliminary results | ☑ |
| Challenges + mitigation | ☑ |
| Remaining work + realistic timeline | ☑ |
| References formatted (IEEE) | ☑ (verify & expand) |
| Appendices listed | ☑ |
