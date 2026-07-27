# BuildWatch — Project Context

## What This Is

BuildWatch is a final-year Computer Engineering capstone project at the **University of Ghana**, supervised by **Dr. Nii Longdon Sowah**. It is a solar-powered IoT system for monitoring construction progress on 1–2 storey residential buildings typical of the Ghanaian market.

**Three core value propositions for Ghanaian contractors:**
1. Detect project delays and cost overruns early
2. Client/investor reporting and trust
3. Protection against material theft

---

## System Architecture

```
Raspberry Pi 4 (site)
  └─ Camera Module V2
  └─ Huawei E3372h-320 4G modem
  └─ Edge agent (picamera2, SQLite buffer, HTTP upload)
        │  4G  │  JPEG upload
        ▼
FastAPI Backend (Docker)
  └─ PostgreSQL — projects, images, inference results
  └─ MinIO — raw + annotated image storage
  └─ Redis — Celery task queue + WebSocket pub/sub
  └─ Celery worker — YOLO11n inference + MWPI computation
  └─ Flower — Celery monitoring UI
        │
        ▼
React Dashboard (Vite + Tailwind + Recharts)
  └─ Overview, Analytics, Gallery, Alerts pages
  └─ WebSocket connection for real-time updates
```

---

## The MWPI Algorithm (Original Academic Contribution)

**Milestone-Weighted Progress Index** — the core thesis contribution. Do not modify weights without supervisor approval.

| Class       | Weight | Status         |
|-------------|--------|----------------|
| foundation  | 0.20   | Trained (nc=0) |
| column      | 0.30   | Trained (nc=1) |
| wall        | 0.50   | Trained (nc=2) |
| slab        | 0.00   | Reserved       |
| roof        | 0.00   | Reserved       |

**Formula (Plan-Informed):**
```
MWPI = Σ weight(class) × min(1.0, detected_count / expected_count)
```
- `detected_count` = YOLO bounding boxes for that class with confidence ≥ 0.4
- `expected_count` = `project.bim_config.expected_components[class]` (building plan)
- If a class has no BIM plan entry: `ratio = 1.0` (binary fallback)

**Example:** Plan says 20 columns. YOLO detects 10 → column contributes `0.30 × 0.50 = 0.15`

**Range:** 0.0 (nothing built) → 1.0 (all milestone targets met per plan)

**Thesis note:** This evolved from the binary version (any detection = full weight). The plan-informed version contextualises detection counts against the building specification. Update the dissertation formula section.

**Plan vs Actual deviation thresholds:**
- `deviation >= 0` → ON SCHEDULE
- `deviation >= -0.10` → SLIGHTLY BEHIND
- `deviation < -0.10` → DELAYED

---

## AI Model

- **Architecture:** YOLO11n
- **Weights file:** `buildwatch_best.pt` (in Google Drive, mounted into Docker)
- **Best mAP@0.5:** 0.517 (Experiment 1 baseline)
  - foundation: 0.531, column: 0.519, wall: 0.197
- **Inference confidence threshold:** 0.25 (model load), 0.4 (MWPI counting)
- **Export formats:** PyTorch weights (`.pt`), NCNN (for Raspberry Pi CPU)
- **MWPI confidence threshold:** 0.4 minimum for a class to count

---

## Technology Stack

| Layer         | Technology                                      |
|---------------|-------------------------------------------------|
| Edge          | Raspberry Pi 4 4GB, picamera2, SQLite, Python   |
| Backend       | FastAPI, SQLAlchemy, PostgreSQL, Redis, Celery  |
| Storage       | MinIO (S3-compatible, two buckets: raw/annotated)|
| AI            | ultralytics YOLO11n, OpenCV                     |
| Frontend      | React (Vite), Tailwind CSS, Recharts, lucide-react |
| Infrastructure| Docker Compose (7 services)                     |

---

## Key File Locations

### Backend
```
backend/app/
├── config.py                  — Settings (model path, MinIO, Redis URLs)
├── database.py                — SQLAlchemy engine + session
├── main.py                    — FastAPI app, CORS, WebSocket endpoint
├── models/
│   ├── image.py               — Image + InferenceResult ORM models
│   └── project.py             — Project ORM model
├── routers/
│   ├── images.py              — GET /images, GET /progress, GET /timeline
│   ├── projects.py            — CRUD /projects
│   └── upload.py              — POST /upload (triggers Celery)
├── services/
│   ├── ai/
│   │   ├── detector.py        — YOLO11n inference, bounding box drawing
│   │   └── progress.py        — MWPI formula, avg_confidence helper
│   └── minio_client.py        — MinIO upload/download/presigned URLs
└── tasks/
    ├── celery_app.py          — Celery configuration
    └── inference.py           — Main pipeline task (download→detect→MWPI→store→broadcast)
```

### Frontend (dashboard/)
```
src/
├── services/api.js            — API service layer (fetch wrappers)
├── hooks/useProjectSocket.js  — WebSocket hook with connected state
├── data/mockData.js           — Mock data (still used by Analytics, Gallery, Alerts)
├── pages/
│   ├── Overview.jsx           — WIRED to live API + WebSocket
│   ├── Analytics.jsx          — Still on mock data
│   ├── Gallery.jsx            — Still on mock data
│   └── Alerts.jsx             — Still on mock data
└── components/ui/             — ProgressRing, GaugeArc, Sparkline, CountUp, Modal
```

### Infrastructure
```
docker-compose.yml             — 7 services: postgres, redis, minio, createbuckets, api, worker, flower
.env / .env.example            — Backend env vars
dashboard/.env                 — VITE_API_URL, VITE_WS_URL, VITE_PROJECT_ID (needs PROJECT_ID filled in)
```

---

## API Endpoints (Implemented)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/projects` | Create project |
| GET | `/api/v1/projects` | List projects |
| GET/PATCH/DELETE | `/api/v1/projects/{id}` | Manage project |
| POST | `/api/v1/upload` | Receive image from Pi, queue Celery task |
| GET | `/api/v1/images` | List images (filterable by project/device/status) |
| GET | `/api/v1/images/{id}` | Full image detail + inference result + presigned URLs |
| GET | `/api/v1/images/{id}/status` | Lightweight status poll |
| GET | `/api/v1/projects/{id}/progress` | Latest MWPI snapshot |
| GET | `/api/v1/projects/{id}/timeline` | Time-series MWPI data |
| WS | `/api/v1/ws/projects/{id}` | Real-time inference events |

---

## WebSocket Event Format

Published by Celery → Redis → forwarded to browser on every completed inference:

```json
{
  "event": "new_inference",
  "project_id": "...",
  "image_id": "...",
  "mwpi_score": 0.65,
  "detected_classes": ["foundation", "column"],
  "avg_confidence": 0.82,
  "annotated_image_url": "https://...",
  "timestamp": "2026-06-22T10:30:00Z"
}
```

---

## Key Constraints

- YOLO class names are exactly: `["foundation", "column", "wall"]` (nc=3)
- MWPI confidence threshold: 0.4 (do not change without supervisor approval)
- Pi uploads JPEG images, max 20MB
- MinIO handles all image storage — no local disk
- All services run in Docker — do not break docker-compose setup
- Frontend uses `import.meta.env.VITE_API_URL` for backend URL
- No authentication — out of scope for this version
- MWPI weights and formula are academic contributions — flag any changes for review

---

## Edge Agent Behaviour

- Captures images via picamera2
- Preprocessing: blur detection → brightness check → CLAHE enhancement → resize 640×640
- Buffers to SQLite for offline resilience (4G can drop)
- Uploads via multipart HTTP POST to `/api/v1/upload` with retry/backoff

---

## Docker Services

| Service | Description |
|---------|-------------|
| `postgres` | PostgreSQL database |
| `redis` | Task queue + WebSocket pub/sub |
| `minio` | Object storage (raw + annotated images) |
| `createbuckets` | One-shot bucket init |
| `api` | FastAPI + WebSocket server |
| `worker` | Celery inference worker |
| `flower` | Celery monitoring dashboard |
