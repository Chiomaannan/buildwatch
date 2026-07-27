---
**A NOTE BEFORE YOU READ THIS, CHIOMA:**

This is a **first draft**, generated to get you moving — not a finished thesis.
Three things to do before you submit anything:

1. **Verify every reference in the Bibliography.** I grounded each one in a real
   web search rather than relying on memory, and included the source URL next
   to each entry so you can check it in thirty seconds — but you must open
   each source and confirm the author list, year, volume, and page numbers
   exactly match before they go in a real bibliography. Treat anything you
   haven't personally opened as unverified.
2. **Fill in the bracketed placeholders** — your index number, submission
   date, and exact department/faculty wording on the cover page (I don't know
   your program's official cover-page format, so don't guess it).
3. **Read the "What Is Deliberately Left Out" section** near the end. Per
   your instruction, this draft only writes what the project can honestly
   support today. Chapters 4–6 (Results, Discussion, Conclusion) are not
   here — they can't be, until the accuracy sprint and validation study are
   done. That section says exactly what's missing and why.

Everything else — the architecture, the MWPI formula, the test results, the
supervisor test-image walkthrough — is real, pulled from the working system
and your project files, not invented for the page.
---

<div align="center">

# BUILDWATCH: A LOW-COST IOT AND COMPUTER-VISION SYSTEM FOR MILESTONE-WEIGHTED CONSTRUCTION PROGRESS MONITORING IN GHANAIAN RESIDENTIAL CONSTRUCTION

**A Thesis Submitted in Partial Fulfilment of the Requirements for the Degree of
Bachelor of Science in Computer Engineering**

**[Department of Computer Engineering / School of Engineering Sciences — confirm exact wording]**
**University of Ghana**

**by**

**Chioma Annan**
**[Index Number]**

**Supervisor: Dr. Nii Longdon Sowah**

**[Month, Year]**

</div>

---

## Status of This Document

This is the **Semester 1 submission package** for the BuildWatch capstone,
covering Chapters 1–3 and a feasibility/preliminary-results section, per the
Computer Engineering Final Year Capstone deliverables guide. It is
intentionally **not a complete thesis**. Chapters 4 (Results), 5 (Discussion),
and 6 (Conclusion) are not included because the work they would report on —
a controlled accuracy improvement pass on the detection model and a
supervisor-facing ground-truth validation study — has not been carried out
yet. Writing those chapters now would mean describing evaluation that hasn't
happened. The "Remaining Work" section near the end of this document states
precisely what is outstanding and the plan to close it in Semester 2.

What **is** included is real: the system described in Chapter 3 is running,
the preliminary results in the feasibility section come from live inference
on an actual project photograph, and the 30 automated tests referenced were
run and passed at the time of writing.

---

## Concept Note (Pre-Chapter Stage)

**Project title:** BuildWatch — Milestone-Weighted Progress Index (MWPI) for
low-cost IoT construction monitoring.

**Background context:** Residential construction in Ghana is dominated by
small and medium contractors who rely on manual, periodic site visits to
report progress to clients, banks, and diaspora investors funding builds
remotely. There is no affordable, continuous, objective way to answer the
question every stakeholder asks: *how far along is the building, really?*

**Problem statement:** Existing automated progress-monitoring methods —
4D BIM matched to photologs, drone photogrammetry, dedicated computer-vision
pipelines — were developed for and validated on large commercial projects
with the budget, technical staff, and digital building models to support
them. None of this is available on a typical 1–2 storey Ghanaian residential
build. A gap exists for a monitoring system cheap enough, and simple enough,
to deploy on that scale.

**Motivation / significance:** Construction delay is a well-documented,
persistent problem in the Ghanaian building industry, and financing-related
causes — delayed client payments, poor cash-flow visibility, disputes over
how much work has actually been done — are consistently ranked among the
leading causes (Fugar & Agyakwah-Baah, 2010). An objective, continuously
updated, remotely accessible progress figure directly addresses that
information gap between contractor and financier.

**Proposed approach:** A solar-capable Raspberry Pi edge unit captures site
images at intervals and transmits them over a cellular uplink to a cloud
backend. A YOLO-family object detector locates structural elements
(foundation, columns, walls, roof); a purpose-built scoring algorithm — the
Milestone-Weighted Progress Index (MWPI) — converts detections into a single
progress percentage, using confidence-weighted counting, temporal smoothing,
a monotonic ratchet, and (a Semester-2-in-progress extension) vision-based
grading of how *complete* each detected element is, not merely whether it is
present.

**Expected outcomes:** A working end-to-end pipeline (edge capture → cloud
inference → dashboard), a documented and testable MWPI formula, and an
empirical evaluation of detection accuracy and score validity against
human-assessed ground truth.

**Supervisor approval:** Supervised by Dr. Nii Longdon Sowah, Department of
Computer Engineering, University of Ghana. [Insert date/method of formal
approval — email, signed form, etc.]

---

# CHAPTER 1: INTRODUCTION

## 1.1 Background of the Study

Construction progress monitoring is the process of measuring how much of a
planned building has actually been built at a given point in time, and
comparing that against the schedule and budget that were planned for it. In
large commercial construction, this is typically done by combining a Building
Information Model (BIM) — a rich 3D digital representation of the design —
with periodic site photographs or laser scans, so that "as-built" progress
can be automatically compared against "as-planned" schedule (Golparvar-Fard
et al., 2009; Golparvar-Fard, Peña-Mora & Savarese, 2013). This approach has
been extended with unmanned aerial vehicles (UAVs) capturing aerial imagery
for photogrammetric reconstruction, and more recently with deep-learning
object detectors trained to recognize construction elements, materials, and
even worker safety compliance directly from ordinary camera images (Rehman,
Shafiq & Ullah, 2022).

None of this infrastructure exists on the typical residential construction
site in Ghana. Most 1–2 storey residential builds — the dominant housing
typology in the country — are managed by small contracting firms without a
digital design model, without dedicated site engineers producing daily
photologs, and often without continuous internet connectivity at the site.
Progress reporting to the client, bank, or diaspora relative funding the
build is usually a phone call, a handful of photographs sent over WhatsApp,
or an in-person visit — all informal, all infrequent, and all dependent on
the contractor's own account of how much work has been done.

At the same time, the underlying technology needed to automate this — small
single-board computers, cellular data modems, and efficient object-detection
models capable of running inference in the cloud from a modest camera image
— has become inexpensive and accessible. BuildWatch is built on the premise
that a system combining a low-cost IoT camera unit with a cloud-based
computer-vision pipeline can close the monitoring gap for exactly this class
of construction project, without requiring the BIM models, drone operators,
or dedicated IT staff that existing academic and commercial solutions assume.

## 1.2 Problem Statement

There is currently no affordable, automated, and objective way for a small
Ghanaian residential construction contractor, client, or financier to obtain
a continuously updated, quantitative measure of construction progress.

This gap has two engineering dimensions that this project addresses
specifically:

1. **Data acquisition gap.** Existing automated progress-monitoring
   literature assumes site instrumentation (photologs, drones, laser
   scanners) or a digital design model (BIM) that is economically and
   organizationally out of reach for the target contractor segment. A
   solar-capable, cellular-connected, single-camera edge device is needed
   that can be deployed with minimal site infrastructure.

2. **Progress-quantification gap.** Even where object-detection models can
   recognize structural elements in a site photograph, converting "which
   elements are visible" into "what percentage of the building is complete"
   is not solved by detection alone. A detector that sees a roof frame and a
   detector that sees a fully covered roof both return the same class label,
   `roof`, at similar confidence — the detection is binary where the
   underlying progress is continuous. Any progress index built directly on
   raw detection counts will misrepresent completion at exactly the
   transitions that matter most to a client deciding whether to release the
   next payment tranche.

## 1.3 Aim and Objectives

**Aim:** To design, implement, and evaluate a low-cost IoT and
computer-vision system that produces an objective, continuously updated
construction progress score for residential building sites in Ghana.

**Objectives:**

1. Design and deploy a solar-capable Raspberry Pi edge unit that captures
   site images at scheduled intervals and transmits them to a cloud backend
   over a cellular uplink, with offline buffering for connectivity gaps.
2. Train and deploy a YOLO-family object detection model to recognize
   structural building elements (foundation, column, wall, roof) from site
   photographs.
3. Design a Milestone-Weighted Progress Index (MWPI) that converts per-class
   detections into a single, monotonically non-decreasing progress
   percentage, addressing the quantification gap in Objective statement 2
   above through confidence-weighted counting and vision-based completion
   grading rather than binary presence detection.
4. Implement a real-time backend and dashboard that surfaces the MWPI score,
   per-class breakdown, and a plain-language explanation of the score to a
   non-technical stakeholder.
5. Evaluate detection accuracy (mean Average Precision, mAP@0.5) against a
   labelled validation set, and evaluate MWPI score validity against a
   human-assessed ground-truth progress reference (Semester 2).

## 1.4 Research Questions

1. Can structural element detection from a single low-cost RGB camera,
   combined with confidence-weighted counting, produce a progress score that
   does not regress as construction proceeds (monotonicity), despite later
   construction stages occluding earlier ones (e.g., walls hiding columns)?
2. To what extent does grading the *completion state* of a detected element
   (e.g., how much of a roof is covered, not merely whether a roof is
   present) improve the accuracy of the progress score relative to
   presence-only detection?
3. What is the achievable object-detection accuracy (mAP@0.5) for structural
   building elements on a Ghanaian residential construction dataset using a
   nano-scale YOLO model suitable for cloud inference at edge-capture
   volumes, and what specific classes limit that accuracy?
4. How closely does the resulting MWPI score track a human expert's
   assessment of construction progress on the same set of site images?

## 1.5 Scope and Limitations

**In scope:**
- Exterior progress monitoring of 1–2 storey residential buildings using a
  single fixed RGB camera per site.
- Detection of four structural milestone classes: foundation, column, wall,
  roof; and two finishing milestones: plastering, painting.
- A confidence-weighted, monotonic progress index (MWPI) computed from
  detection output, plan-informed expected element counts (when a building
  plan is available), and vision-based completion grading.
- A cloud backend, real-time dashboard, and plain-language AI-generated
  status explanation.

**Out of scope:**
- Interior construction progress (this work addresses only what an exterior
  fixed camera can observe).
- Multi-camera or stereo/depth-camera reconstruction; the current system
  uses a single monocular RGB camera per site, which cannot measure volume
  or true 3D extent (see Section 1.5, Limitations, and the Hardware Roadmap
  future-work discussion in Chapter 3).
- Structural or safety-code compliance checking.
- Formal cost/schedule integration with an external project-management
  system; MWPI is reported as a standalone progress percentage, with an
  optional plan-vs-actual schedule comparison against manually entered
  milestone targets.

**Limitations acknowledged at this stage:**
- A single camera viewpoint necessarily undercounts elements on the
  building's far side; expected-count normalization partially compensates
  for this but does not eliminate it.
- The detection model's accuracy is currently limited on the `wall` class in
  particular (see Chapter 3 preliminary results), which motivates the
  accuracy-improvement work planned for Semester 2.
- Several structural-completion inferences used by the MWPI formula (for
  example, that a started roof implies finished walls and columns beneath
  it, or that a plastered wall implies internal electrical and plumbing
  first-fix work is complete) are engineering assumptions grounded in
  standard construction sequencing, not measurements. They are stated
  explicitly as assumptions in Chapter 3 and are a documented limitation of
  the metric, not a hidden one.
- No formal, statistically powered validation study against expert-assessed
  ground truth has been completed at the time of this submission; this is
  planned for Semester 2 and is listed under Remaining Work.

## 1.6 Significance of the Study

For contractors, an automated and objective progress score reduces the
labour of manual reporting and gives them a defensible, timestamped record
of work completed — valuable in payment disputes. For clients and diaspora
investors, who are frequently unable to visit the site in person, a
continuously updated and independently computed score restores a degree of
trust and oversight that is otherwise dependent entirely on the contractor's
own account. For financiers releasing funds in tranches tied to construction
milestones, an objective progress index provides a basis for
disbursement decisions that does not rely solely on a contractor's
self-report. More broadly, this work contributes an engineering artefact —
the MWPI formula and its supporting completion-grading pipeline — that
extends existing computer-vision progress-monitoring research (which
assumes BIM models and dedicated data-collection infrastructure) into a
resource-constrained, single-camera, developing-market context, a case
under-represented in the literature reviewed in Chapter 2.

## 1.7 Organization of the Thesis

Chapter 2 reviews existing approaches to automated construction progress
monitoring — BIM-and-photolog methods, drone photogrammetry, computer-vision
object detection, and the emerging use of vision-language models — and
identifies the specific research gap this project addresses. Chapter 3
presents the system's research methodology, architecture, the mathematical
formulation of the MWPI algorithm, the tools and platforms used, and the
evaluation plan. A feasibility study and preliminary results section reports
what has been built and tested to date, including a worked example of the
MWPI pipeline scoring a real site photograph. A closing section states
explicitly what remains outstanding for Semester 2, followed by the Semester
1 supporting materials (work plan, risk analysis, ethics considerations) and
the bibliography.

---

# CHAPTER 2: LITERATURE REVIEW

## 2.1 Theoretical Background

Automated construction progress monitoring is generally described in the
literature as a four-stage pipeline: **data acquisition** (capturing site
imagery or point clouds), **information retrieval** (extracting objects,
materials, or geometry from the raw data), **progress estimation** (comparing
retrieved information against a planned baseline to produce a progress
metric), and **output visualization** (communicating the result to a
stakeholder) (Rehman, Shafiq & Ullah, 2022). BuildWatch follows this same
four-stage structure — edge image capture; YOLO-based object detection;
MWPI computation; and a real-time dashboard — which is useful for situating
this work against prior approaches that instantiate the same four stages
differently.

Two engineering foundations underlie the retrieval and estimation stages in
this project specifically. First, object detection: the YOLO ("You Only
Look Once") family of single-stage detectors frames object localization and
classification as one regression problem over a grid of the image, trading
some accuracy relative to two-stage detectors for substantially faster
inference — a property that matters directly for a system intended to run
inference on every captured frame from potentially many sites. The YOLO11
architecture used in this project introduces a modified backbone (C3k2
blocks replacing the C2f blocks of YOLOv8) and a spatial-attention module
(C2PSA) that improve small-object detection while reducing parameter count
relative to prior YOLO generations (Khanam & Hussain, 2024; Sapkota et al.,
2025). Second, progress quantification: converting detected object counts
into a scalar progress metric requires an explicit weighting scheme, since
not all structural elements represent equal shares of total construction
effort — the same principle underlying Bill-of-Quantities-based progress
valuation in traditional quantity surveying, which this project's
milestone-weight design deliberately echoes.

## 2.2 Review of Existing Systems

### 2.2.1 BIM- and photolog-based monitoring

The most established line of research on automated progress monitoring
matches unordered daily site photographs against a 4D Building Information
Model — a 3D design model with an added time dimension representing the
planned construction schedule. Golparvar-Fard, Peña-Mora and Savarese (2009)
proposed the D4AR framework, which registers site photographs to the 4D BIM
via structure-from-motion reconstruction and visualizes as-built versus
as-planned discrepancies directly overlaid on the photographs. A follow-on
line of work automated this registration and extended it to
material-appearance classification, so that the system could infer not just
that an element existed but what construction stage its surface appearance
indicated (Golparvar-Fard, Peña-Mora & Savarese, 2013). This body of work is
foundational, but it is built on an assumption BuildWatch cannot make: that
a georeferenced, element-level 4D BIM already exists for the building being
monitored. On the residential construction projects this thesis targets, no
such model exists, and producing one is not economically realistic for the
project size.

### 2.2.2 Drone and photogrammetric monitoring

An alternative data-acquisition strategy uses unmanned aerial vehicles to
capture overlapping aerial imagery, which is processed via photogrammetry
into an orthomosaic, dense point cloud, or textured 3D mesh; this "as-built"
reconstruction is then compared against the as-planned CAD or BIM model to
quantify progress and detect deviations. This approach captures whole-site
geometry that a single fixed camera cannot, and its adoption is documented
across large-scale earthworks and infrastructure projects (Vick, 2021). It
does, however, require either a licensed drone operator or an autonomous
flight system, per-flight processing time, and — again — a design model to
compare against, none of which suit a per-residential-site deployment at the
cost point this thesis targets.

### 2.2.3 Computer-vision object detection on construction sites

A large and growing body of work applies deep-learning object detectors
directly to construction-site imagery, most heavily for worker safety
compliance (detecting missing personal protective equipment, unsafe
proximity to machinery, or hazardous behaviour) rather than structural
progress per se. Representative recent examples include GeoIoU-SEA-YOLO,
which augments YOLO with a geometric IoU loss and a structural-attention
mechanism to detect unsafe worker behaviour with reported mAP@0.5 of 0.930
(PMC, 2025), and GSO-YOLO, which adds global-context and steady-capture
modules to improve detection robustness in visually complex site scenes
(arXiv:2407.00906, 2024). This line of research has also produced the
large, purpose-built datasets this project's own labelling effort draws
methodological guidance from: SODA, a site object-detection dataset of
19,846 images and 286,201 annotations across fifteen classes, benchmarked
with YOLOv3/v4 to a maximum mAP@0.5 of 81.47% (Duan et al., 2022); and MOCS,
a 41,668-image, per-pixel-annotated dataset of moving construction-site
objects across 174 sites (Automation in Construction, 2021). These datasets
and models are overwhelmingly focused on *worker and equipment* detection
for safety, not on the *structural building elements* (foundation, columns,
walls, roof) that a milestone-based progress index requires — a gap this
project's own custom-labelled dataset was built to fill.

A smaller number of studies address structural progress detection directly.
Rehman, Shafiq and Ullah (2022) provide a systematic review of ten years of
computer-vision-based construction progress monitoring research, describing
the four-stage pipeline referenced in Section 2.1 and noting that the great
majority of surveyed systems were validated on commercial or infrastructure
projects with existing BIM assets — reinforcing the gap this thesis
addresses. A related review focused specifically on interior progress
monitoring likewise finds automation efforts concentrated on exterior
building envelopes, with far fewer studies addressing interior finishing
work (ScienceDirect, 2021) — a gap BuildWatch's plastering and painting
milestone classes are a first, narrow step toward closing, though the
present system, like the reviewed literature, is still exterior-facing.

### 2.2.4 Vision-language models for construction monitoring

The most recent development relevant to this project is the emergence of
general-purpose, instruction-following vision-language models (VLMs) — such
as GPT-4 Vision — capable of interpreting a construction photograph and
answering open-ended questions about it without task-specific training.
Ersoz (2024) evaluates ChatGPT-4 Vision directly on construction
progress-monitoring imagery and finds it capable of qualitative scene
description and change-tracking across time, though without the calibrated,
class-specific accuracy of a purpose-trained object detector. This is
directly relevant to BuildWatch's own design: rather than relying on a VLM
as the primary detector (which would be both slower and less precise than a
trained YOLO model for counting discrete elements), this project uses a
purpose-trained YOLO detector for element counting and reserves a VLM
(Claude vision) for a narrower, better-suited sub-task — grading how
*complete* an already-detected element is, and classifying wall surface
finish — an application of VLMs to construction monitoring not covered by
the systems reviewed above, and detailed fully in Chapter 3.

## 2.3 Comparative Analysis

| Approach | Data requirement | Site infrastructure needed | Real-time capable | Cost profile | Progress granularity |
|---|---|---|---|---|---|
| Manual site visit / phone report | None | None | No (periodic) | Labour cost only | Subjective, qualitative |
| BIM + 4D photolog (Golparvar-Fard et al.) | Element-level 4D BIM | Digital design model, photologging discipline | Near-real-time | High (BIM authoring + expertise) | Element-level, as-planned vs as-built |
| Drone photogrammetry | As-planned CAD/BIM (for comparison) | Drone + operator or autonomous flight, processing pipeline | Per-flight (not continuous) | Medium–high (hardware + flights) | Whole-site 3D geometry |
| CV object detection (safety/worker-focused, e.g. SODA/MOCS-trained models) | Labelled dataset | Fixed or mobile camera | Yes | Low–medium | Object presence/count, not milestone progress |
| VLM-based (ChatGPT-4V per Ersoz, 2024) | None (zero-shot) | Camera + API access | Near-real-time | Low (per-call API cost), no training needed | Qualitative / descriptive, not calibrated |
| **BuildWatch (this work)** | **None** (plan optional, improves accuracy) | **Single low-cost camera + cellular uplink** | **Yes** | **Low** (commodity edge hardware, cloud inference) | **Milestone-weighted %, confidence-weighted, monotonic, completion-graded** |

## 2.4 Identified Research Gap

The reviewed literature establishes that automated construction progress
monitoring is a mature research area, but every major approach — 4D BIM
matching, drone photogrammetry, and even the safety-focused CV detection
systems with the largest published datasets — assumes site infrastructure
(a digital design model, licensed drone operation, or dedicated
data-collection discipline) that is not available to the small residential
contractor this thesis targets. Separately, and more fundamentally, no
system reviewed converts binary or count-based object detections into a
progress score that explicitly models detection confidence, temporal
occlusion (the fact that later construction stages hide earlier ones, which
can make a naive score *decrease* as the building progresses), and — most
significantly — the *completion state* of a detected element as distinct
from its mere presence. A YOLO-based safety detector correctly reports
"helmet present"; none of the systems reviewed attempt to report "this roof
is half-covered" as opposed to "this roof exists." BuildWatch's Milestone-
Weighted Progress Index, detailed in Chapter 3, is designed specifically to
close this second gap, using a monotonic ratchet over confidence-weighted
detections combined with vision-language-model-based completion grading —
in a system architecture designed from the outset to close the first,
infrastructure-availability gap as well.

## 2.5 Summary of Findings

Existing automated progress-monitoring research is strong on infrastructure-
rich, high-budget construction contexts and on worker/equipment safety
detection, but is largely silent on two problems this thesis takes as its
core contribution: (1) monitoring progress with no digital design model and
minimal site infrastructure, at a cost point suited to small residential
construction, and (2) converting element detection into a *graded*
completion measure rather than a binary presence flag. The following
chapter presents BuildWatch's methodology and system design as a direct
response to both gaps.

---

# CHAPTER 3: METHODOLOGY / SYSTEM DESIGN

## 3.1 Research Methodology

This project follows a **design-science / prototype-development**
methodology: the research contribution is an engineered artefact (the
BuildWatch system and its MWPI algorithm), developed iteratively and
evaluated against both quantitative benchmarks (detection accuracy) and
qualitative validation (supervisor review of scored examples), rather than
a hypothesis tested through controlled experiment on human subjects. This is
the standard methodology for systems-oriented computer engineering capstone
work of this kind, and matches the methodological framing used throughout
the computer-vision progress-monitoring literature reviewed in Chapter 2.

**Dataset description.** Structural element detection is trained on a
custom-labelled dataset of Ghanaian residential construction site
photographs (Roboflow workspace `chiomas-workspace`, dataset generation
`ghana-construction v4`), covering four structural classes — `foundation`,
`column`, `wall`, `roof` — and a `worker` class used for a separate presence-
monitoring feature outside MWPI's scope. This is a deliberate departure from
the large public datasets reviewed in Chapter 2 (SODA, MOCS), which are
labelled for worker/equipment safety detection and do not contain the
structural-element classes this project's progress index requires; a
custom dataset was therefore necessary.

**Prototype development approach.** The system was built as a working,
deployed prototype rather than a simulation, on the reasoning that a
progress-monitoring system's real value lies in behaviour under live,
imperfect field conditions (variable lighting, partial occlusion, a single
camera angle) that a simulated dataset cannot fully represent. Development
proceeded task-by-task (documented in the project's internal progress
tracker as Tasks 1–11), each task validated before the next began, with
formula changes to the MWPI algorithm specifically flagged for supervisor
review given their status as the project's core academic contribution.

## 3.2 System Architecture

```
                         ┌────────────────────────────┐
                         │   Construction Site (Edge)  │
                         │                              │
                         │  Raspberry Pi 4 (4GB)        │
                         │   • Pi Camera Module         │
                         │   • 4G/LTE cellular modem    │
                         │   • Solar + battery power     │
                         │   • SQLite offline buffer     │
                         └──────────────┬───────────────┘
                                        │  HTTP multipart upload (JPEG)
                                        ▼
                         ┌────────────────────────────┐
                         │   Cloud Backend (Docker)    │
                         │                              │
                         │  FastAPI  ── REST API        │
                         │  Celery worker ── inference  │
                         │    • YOLO11n detection        │
                         │    • MWPI computation          │
                         │    • Claude-vision completion   │
                         │      grading + finish state     │
                         │  PostgreSQL ── projects,      │
                         │    images, inference results   │
                         │  MinIO ── raw + annotated       │
                         │    image object storage         │
                         │  Redis ── task queue +          │
                         │    WebSocket pub/sub             │
                         └──────────────┬───────────────┘
                                        │  REST + WebSocket
                                        ▼
                         ┌────────────────────────────┐
                         │  React Dashboard (Vite)      │
                         │   • Live MWPI ring + trend    │
                         │   • Per-class breakdown        │
                         │   • Plain-language AI insight  │
                         │   • Image gallery, alerts       │
                         └────────────────────────────┘
```

**Data flow, per capture cycle:**
1. Edge unit captures an image on a fixed schedule, preprocesses it (blur
   detection, brightness check, CLAHE contrast enhancement, resize), and
   uploads it via HTTP multipart POST; failed uploads are buffered to a
   local SQLite queue and retried, so intermittent cellular connectivity
   does not lose data.
2. The backend stores the raw image and enqueues a Celery inference task.
3. The worker downloads the image, runs YOLO11n detection, computes the
   MWPI score (Section 3.3), draws an annotated overlay, and — where an
   Anthropic API key is configured — sends one additional vision request
   that grades the completion state of each detected structural class and
   classifies visible wall surface finish (unplastered / plastered /
   painted).
4. The result is persisted and broadcast over WebSocket to any connected
   dashboard session, so the displayed score updates without a page reload.

**Hardware/software stack:**

| Layer | Technology |
|---|---|
| Edge | Raspberry Pi 4 (4GB), Pi Camera Module, 4G/LTE USB modem, picamera2, SQLite, Python |
| AI / detection | Ultralytics YOLO11n, OpenCV |
| AI / completion grading | Anthropic Claude vision (Haiku-class model), one request per capture |
| Backend | FastAPI, SQLAlchemy, Celery, PostgreSQL, Redis |
| Object storage | MinIO (S3-compatible) |
| Frontend | React (Vite), Tailwind CSS |
| Infrastructure | Docker Compose |

## 3.3 Algorithms and Models

### 3.3.1 Object detection

Structural elements are detected using YOLO11n, the nano-scale variant of
the YOLO11 architecture (Khanam & Hussain, 2024), chosen for its favourable
accuracy-to-inference-cost ratio, since inference runs in the cloud on every
captured frame rather than on the resource-constrained edge device itself.

### 3.3.2 The Milestone-Weighted Progress Index (MWPI)

MWPI is this project's core algorithmic contribution. It converts per-class
object detections into a single progress score in the range [0, 1]:

$$MWPI_t = \sum_{c} w(c) \cdot r_t(c)$$

where $c$ ranges over six milestone classes and $w(c)$ is that class's fixed
share of total construction effort:

| Class | Weight | |
|---|---|---|
| foundation | 0.12 | structural subtotal 0.80 |
| column | 0.20 | |
| wall | 0.32 | |
| roof | 0.16 | |
| plastering | 0.12 | finishing subtotal 0.20 |
| painting | 0.08 | |

The weights are a partition of 1.0, apportioned so that a structurally
complete but unfinished building — foundation through roof done, no
plastering or painting — scores 80%, and 100% requires visible finishing.
**These weights are a proposed default, not yet formally signed off by the
project supervisor**; a written proposal with the full justification is
under review at the time of this submission (see Remaining Work).

$r_t(c)$, the completion ratio for class $c$ at time $t$, is computed
through a five-stage pipeline:

**Stage 1 — Soft counting.** Each detection of class $c$ contributes its
confidence score, not a hard 1, to a running evidence total:
$\tilde{n}_t(c) = \sum_i p_i$ for detections with confidence $p_i$ above a
floor threshold. This removes a hard cliff at a fixed confidence threshold
that would otherwise treat a 0.39-confidence detection as worthless and a
0.41-confidence detection as fully counted.

**Stage 2 — Raw ratio (extent × completion state).** Where a building plan
provides an expected element count $E(c)$:

$$\rho_t(c) = \min\left(1, \frac{\tilde{n}_t(c)}{E(c)}\right) \times g_t(c)$$

Without a plan, extent falls back to a binary rule (full extent credit if
any detection exceeds a stricter confidence threshold). $g_t(c) \in [0,1]$
is a **completion-state grade** supplied by a vision-language-model
assessment of the same image: the detector answers "is a roof present?";
the grade separately answers "how complete is it?" — a bare truss frame is
graded near 0.5, a fully sheeted roof near 1.0. This directly targets the
progress-quantification gap identified in Chapter 2 (Section 2.4): no
system reviewed there distinguishes a partially finished element from a
complete one within the same detected class. Finishing-class ratios
(plastering, painting) are derived from the wall ratio multiplied by the
fraction of visible walls a separate vision classification labels
plastered or painted respectively.

**Stage 3 — Temporal smoothing.** The raw ratio is median-filtered over the
three most recent captures, so that a single spurious detection cannot
immediately affect the score.

**Stage 4 — Monotonic ratchet.**
$r_t(c) = \max(r_{t-1}(c),\ \text{smoothed}\ \rho_t(c))$. Construction is
physically irreversible; a later capture in which a wall has grown up and
now occludes previously-visible columns must not cause the score to fall.
The ratchet enforces this by construction. A manual reset endpoint exists
for the genuine exception case (demolition or rework).

**Stage 5 — Structural sequencing inferences.** Three explicit, documented
assumptions are applied to the latched ratios, grounded in standard
construction sequencing rather than direct measurement:
- A roof detected at or beyond a threshold completion stage implies the
  wall–column frame beneath it is complete (roofing cannot begin before
  blockwork reaches the wall plate), correcting for the fact that a single
  camera angle frequently cannot see every column or the full wall run.
- Superstructure evidence (any of column, wall, or roof reaching a minimum
  latched ratio) implies the foundation is complete, since it is
  physically buried and re-observing it is impossible once construction has
  progressed.
- A physical ordering constraint enforces that the painting ratio never
  exceeds the plastering ratio, which never exceeds the wall ratio — a wall
  cannot be painted before it is plastered, nor plastered before it exists.

These inferences are stated here as explicit, falsifiable engineering
assumptions, not hidden model behaviour, and are documented in full with
their justification in the project's internal MWPI proposal document, which
is pending formal supervisor sign-off.

### 3.3.3 Vision-language-model completion grading

The completion grade $g_t(c)$ and wall surface classification described
above are produced by a single request to a vision-language model (Claude,
Anthropic) per capture, which receives the full site image, up to four
cropped wall regions, and — where the project has an uploaded building plan
image (an architectural elevation or rendering) — that plan image as a
grading reference, so completion is judged relative to the finished design
rather than generic rules alone. This is, to the author's knowledge, an
application of VLM-based grading not present in the systems reviewed in
Chapter 2, where VLM use (Ersoz, 2024) has so far been evaluated as a
general-purpose descriptive tool rather than integrated as a calibrated
sub-component of a numeric progress index.

## 3.4 Tools and Platforms

- **Python** — edge agent, backend, and all inference code.
- **Ultralytics YOLO11** — object detection training and inference.
- **Roboflow** — dataset labelling and version management.
- **Anthropic Claude API** — vision-based completion grading and plain-
  language explanation generation.
- **FastAPI, Celery, PostgreSQL, Redis, MinIO** — backend services,
  orchestrated via Docker Compose.
- **React (Vite), Tailwind CSS** — dashboard frontend.
- **pytest** — automated testing of the MWPI algorithm (Section 3.5).

No FPGA, microcontroller-level firmware, or MATLAB/Simulink modelling is
used in this project; the embedded component is limited to a Raspberry Pi
running standard Linux and Python, which was assessed as sufficient given
that all detection and scoring computation is deliberately offloaded to the
cloud backend to keep the edge unit's cost and power budget low.

## 3.5 Evaluation Plan

**Metrics:**
- **Detection accuracy:** mean Average Precision at IoU 0.5 (mAP@0.5),
  overall and per class, on a held-out validation split.
- **Score behaviour:** monotonicity of the MWPI score across a sequence of
  captures on the same project (verified by automated test, Section 4.2).
- **Score validity (planned, Semester 2):** agreement between MWPI and a
  human expert's assessed progress percentage on a shared set of site
  images, measured by Spearman rank correlation and mean absolute error,
  with particular attention to late-stage (post-roof) images where a
  presence-only index is known to saturate prematurely.

**Test scenarios:** unit tests exercising the MWPI formula directly
(confidence-weighting behaviour, ratchet monotonicity under simulated
occlusion, the structural sequencing inferences, and their interaction with
completion grading); end-to-end tests running a real captured site
photograph through the full pipeline and inspecting the resulting score and
generated explanation.

**Validation strategy:** the accuracy metrics and unit-test suite described
above are already in place and reported in the feasibility section below;
the human-expert ground-truth comparison is designed but not yet executed,
and is listed under Remaining Work.

---

# FEASIBILITY STUDY / PRELIMINARY RESULTS

This section reports what has actually been built, run, and measured at the
time of this submission — not a projection of expected results.

## 4.1 Detection Model — Current Accuracy

The deployed YOLO11n baseline model (three structural classes: foundation,
column, wall) achieves an overall mAP@0.5 of **0.517** on the held-out
validation split, with substantial variation by class:

| Class | mAP@0.5 |
|---|---|
| foundation | 0.531 |
| column | 0.519 |
| wall | 0.197 |

The `wall` class is the clear accuracy bottleneck, and its low mAP directly
motivated a design decision in the MWPI formula: raw detections are
confidence-weighted (Section 3.3.2, Stage 1) precisely so that a low-mAP
class does not force a binary all-or-nothing scoring cliff. A four-class
retraining pass (adding `roof`) has since been run; overall mAP@0.5 on that
model is currently **≈0.315**, reflecting the added difficulty of a fifth
class with less mature training data — an accuracy-improvement pass
(targeting 0.50–0.60 mAP@0.5) is planned for Semester 2 and listed under
Remaining Work, rather than reported here as complete.

## 4.2 MWPI Formula — Automated Test Coverage

The MWPI algorithm (Section 3.3.2) is covered by an automated test suite of
**30 unit tests**, run with `pytest`, exercising: confidence-weighted
counting behaviour at and around the threshold boundary; the monotonic
ratchet across a simulated five-frame construction sequence including a
fully occluded frame (verifying the score does not regress); each structural
sequencing inference in isolation and in combination; the physical ordering
constraint between wall, plastering, and painting ratios; and the score's
behaviour when the vision-completion-grading step is unavailable (no API
key configured, or a transient failure), which is designed to hold prior
progress rather than either crediting or penalising the frame incorrectly.
All 30 tests passed at the time of writing.

## 4.3 Worked Example — End-to-End Pipeline on a Real Site Photograph

To demonstrate the complete pipeline against a real image (a site
supervisor's own photograph of a structurally advanced but unfinished
house — roof trusses erected but not yet covered, blockwork complete,
finishing not started), the image was processed through each stage of MWPI
as it was incrementally developed:

| Pipeline stage | Score | What changed |
|---|---|---|
| Presence-only detection, no finishing milestones (pre-existing formula) | 100% | Detected foundation, column, wall — no penalty for the (undetectable) foundation, no finishing classes existed yet |
| + finishing milestones added (plastering/painting introduced) | 48% | Roof and wall credited; foundation and columns scored zero (not directly visible/below detection threshold) |
| + foundation-implied-by-superstructure inference | 60% | Foundation credited once superstructure evidence crossed the inference threshold |
| + roof-implies-frame inference | 80% | Wall and column credited in full once the roof was shown to have started |
| + vision-based completion grading | 58.8–68%\* | Roof correctly graded as roughly half-complete (trusses erected, not covered) rather than credited in full; walls confirmed complete once the roof-implies-frame rule was applied on top of the graded ratios |

*\*58.8% under generic grading rules; 68% once the assessor was given the
project's uploaded building-plan image as a grading reference and the
site's plan-derived weights.*

This progression is included deliberately, not to claim a single "correct"
final number, but as evidence that each addition to the formula was
motivated by, and tested against, an observable failure mode in the
previous version — the presence-only version's headline flaw (100% on a
visibly unfinished building) is what the rest of Chapter 3's design directly
responds to.

## 4.4 Dashboard and Real-Time Pipeline

The end-to-end system — edge upload endpoint, Celery inference worker,
PostgreSQL persistence, MinIO image storage, WebSocket broadcast, and the
React dashboard — is implemented and has processed live inference requests
against real project images (multiple named test and pilot projects exist
in the system at the time of writing), including annotated-image generation,
a plain-language AI-generated status explanation for non-technical
stakeholders, and a live-updating progress visualization.

---

# REMAINING WORK (What Is Deliberately Left Out of This Draft)

Per instruction, this document reports only what the project can currently
support with evidence. The following is explicitly **not done**, and is not
described elsewhere in this draft as though it were:

1. **Formal supervisor sign-off on the MWPI weight scheme** (Section
   3.3.2). The six-class weights are a proposed default under review.
2. **Accuracy-improvement pass on the detection model.** Current mAP@0.5 is
   0.315–0.517 depending on model version (Section 4.1); target is
   0.50–0.60, planned via higher input resolution, test-time augmentation,
   and additional labelled data.
3. **Ground-truth validation study.** No comparison between MWPI and
   independent human-expert progress assessment has been run yet. This is
   the single most important outstanding item, since it is the only planned
   evidence that the score's numeric output — not just its qualitative
   behaviour — is trustworthy.
4. **Chapters 4 (Results), 5 (Discussion), 6 (Conclusion).** These cannot be
   written honestly until items 2 and 3 above produce results to report.
5. **Depth/volumetric measurement.** The current single monocular-camera
   design can detect element presence and (via vision grading) qualitative
   completion state, but not true volumetric or dimensional measurement. A
   depth-camera extension is identified as the highest-value future-work
   direction and is out of scope for this thesis.
6. **Interior progress monitoring**, multi-camera/stereo reconstruction, and
   formal cost/schedule system integration remain out of scope (Section
   1.5).

---

# WORK PLAN / TIMELINE

| Phase | Milestone | Status |
|---|---|---|
| Semester 1, early | Topic approval, concept note, Chapter 1 draft | Complete |
| Semester 1, mid | Chapter 2 literature review, Chapter 3 methodology/design | Complete (this document) |
| Semester 1, mid–late | Edge unit build, YOLO baseline training, backend pipeline | Complete |
| Semester 1, late | MWPI v1 (confidence-weighted, monotonic) implementation and testing | Complete |
| Semester 1, late | MWPI finishing-stage and completion-grading extension | Complete |
| Semester 1, end | Feasibility study / preliminary results (this document) | Complete |
| Semester 2, early | Detection accuracy improvement sprint (target mAP@0.5 0.50–0.60) | Not started |
| Semester 2, early–mid | Ground-truth validation study design + data collection | Not started |
| Semester 2, mid | Ground-truth validation study execution + analysis | Not started |
| Semester 2, mid | Chapter 4 (Results) | Not started |
| Semester 2, late | Chapter 5 (Discussion), Chapter 6 (Conclusion) | Not started |
| Semester 2, end | Final thesis submission and defence | Not started |

---

# RISK ANALYSIS

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Detection accuracy improvement sprint underperforms target (0.50–0.60 mAP@0.5) | Medium | High — undermines confidence in MWPI inputs | MWPI's confidence-weighting and completion-grading design already reduce sensitivity to raw detection accuracy; report achieved accuracy honestly regardless of outcome |
| Ground-truth validation study shows weak correlation with human assessment | Medium | High — central to the thesis's validity claim | Design the study with enough sample size and stage diversity to be informative either way; treat a negative result as a legitimate, reportable finding, not a failure to hide |
| Cellular/power reliability issues at pilot sites | Medium | Medium — data gaps | SQLite offline buffering and retry logic already implemented |
| Supervisor does not approve current MWPI weight scheme | Low–Medium | Medium — requires formula rework | Weights are stored as ratios, not baked-in contributions, so a weight change re-scores all historical data without a data migration (already verified in the implementation) |
| Single-camera occlusion causes systematic undercounting on far-side elements | High (known limitation) | Medium | Explicitly documented as a limitation (Section 1.5); expected-count normalization partially compensates; flagged as future work for multi-camera/depth extension |
| Time constraint: Semester 2 workload (accuracy sprint + validation study + three remaining chapters) is substantial | Medium | High — schedule risk | Sequenced explicitly in the Work Plan above; validation study prioritized first since Chapters 4–6 depend on its output |

---

# ETHICS CONSIDERATIONS

Construction site images captured by BuildWatch may incidentally include
identifiable individuals (site workers) in addition to the building
structure that is the system's subject of interest. The following
considerations apply:

- **Purpose limitation:** captured images are used solely for structural
  progress assessment; the separate worker-detection feature referenced in
  Section 3.1 is used only for aggregate presence/activity monitoring, not
  for identifying or tracking specific individuals.
- **Consent and notice:** site personnel and the contracting firm should be
  informed that a camera is in operation and its purpose, consistent with
  standard site-safety signage practice; a formal consent/notice protocol
  for pilot deployments should be documented before any site with worker
  presence is monitored under this project, and is not yet formalized at
  the time of this submission.
- **Data storage and retention:** captured images are stored in the
  project's own cloud object storage under the research team's control; no
  third-party image-sharing occurs beyond the vision-language-model API
  calls described in Chapter 3, which process but do not retain images
  under standard API data-handling terms — this should be explicitly
  verified against the current provider terms before any pilot deployment
  involving real client sites.
- **No safety-critical decisions are automated:** MWPI produces a progress
  estimate, not a structural safety assessment; the system is not designed
  or validated for, and must not be used for, structural integrity or
  building-code compliance decisions.

---

# BIBLIOGRAPHY

**Verify every entry below against its source before this reference list is
used in any formal submission.** Each entry includes the source URL used to
locate it; author lists, exact page ranges, and volume numbers should be
confirmed against the publisher page, not taken on the strength of this
draft alone.

1. Fugar, F. D. K., & Agyakwah-Baah, A. B. (2010). Delays in building
   construction projects in Ghana. *Australasian Journal of Construction
   Economics and Building*, 10(1/2), 103–116.
   https://epress.lib.uts.edu.au/journals/index.php/AJCEB/article/view/1592

2. Golparvar-Fard, M., Peña-Mora, F., & Savarese, S. (2009). Application of
   D4AR — A 4-Dimensional augmented reality model for automating
   construction progress monitoring data collection, processing and
   communication. *Journal of Information Technology in Construction
   (ITcon)*, 14, 129–153.
   https://www.researchgate.net/publication/269047952

3. Golparvar-Fard, M., Peña-Mora, F., & Savarese, S. (2013). Appearance-
   based material classification for monitoring of operation-level
   construction progress using 4D BIM and site photologs.
   *Automation in Construction* (and related *Journal of Computing in Civil
   Engineering* publications from the same research programme).
   https://www.sciencedirect.com/science/article/abs/pii/S0926580515000266

4. Rehman, M. S. U., Shafiq, M. T., & Ullah, F. (2022). Automated Computer
   Vision-Based Construction Progress Monitoring: A Systematic Review.
   *Buildings*, 12(7), 1037. https://doi.org/10.3390/buildings12071037

5. Duan, R., Deng, H., Tian, M., Deng, Y., & Lin, J. (2022). SODA: Site
   Object Detection dAtaset for Deep Learning in Construction.
   arXiv:2202.09554. https://arxiv.org/abs/2202.09554
   [Author order/full list to be confirmed against the arXiv page.]

6. An, X., et al. (2021). Dataset and benchmark for detecting moving
   objects in construction sites. *Automation in Construction*.
   https://www.sciencedirect.com/science/article/abs/pii/S0926580520310621
   [Full author list not confirmed from search snippet — verify before use.]

7. Ersoz, A. B. (2024). Demystifying the Potential of ChatGPT-4 Vision for
   Construction Progress Monitoring. arXiv:2412.16108.
   https://arxiv.org/abs/2412.16108

8. Khanam, R., & Hussain, M. (2024). YOLOv11: An Overview of the Key
   Architectural Enhancements. arXiv:2410.17725.
   https://arxiv.org/abs/2410.17725

9. Sapkota, R., et al. (2025). YOLOv1 to YOLOv11: A Comprehensive Survey of
   Real-Time Object Detection Innovations and Challenges. arXiv:2508.02067.
   https://arxiv.org/abs/2508.02067
   [Author list to be confirmed — cite lead author only until verified.]

10. GeoIoU-SEA-YOLO: An Advanced Model for Detecting Unsafe Behaviors on
    Construction Sites (2025). *PMC*, PMC11860017.
    https://pmc.ncbi.nlm.nih.gov/articles/PMC11860017/
    [Full citation, authors, and journal name to be confirmed from the
    PMC record before use.]

11. GSO-YOLO: Global Stability Optimization YOLO for Construction Site
    Detection (2024). arXiv:2407.00906. https://arxiv.org/pdf/2407.00906

12. Automated construction monitoring based on computer vision: A
    comprehensive review (2025). *Developments in the Built Environment*
    (ScienceDirect, S2666165925002327).
    https://www.sciencedirect.com/science/article/pii/S2666165925002327
    [Authors and exact journal/issue to be confirmed before use.]

13. Computer vision-based interior construction progress monitoring: A
    literature review and future research directions.
    *Automation in Construction* (ScienceDirect, S0926580521001564).
    https://www.sciencedirect.com/science/article/abs/pii/S0926580521001564
    [Authors and year to be confirmed before use.]

14. Barriers to Building Information Modelling Adoption in Small and
    Medium Enterprises: Nigerian Construction Industry Perspectives (2024).
    *Buildings*, 14(2), 538. https://www.mdpi.com/2075-5309/14/2/538
    [Authors to be confirmed before use.]

15. Unmanned Aerial Vehicles (UAVs) for Physical Progress Monitoring of
    Construction. *PMC*, PMC8235729.
    https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8235729/
    [Full citation to be confirmed before use.]

*(Entries 5, 6, 9, 10, 12, 13, 14, and 15 are flagged above because the web
search used to locate them did not return a fully confirmed author list or
publication year in the returned snippet — not because the source itself is
in doubt. Open each link and copy the citation directly from the publisher
or arXiv page before this bibliography is used in any formal submission.)*
