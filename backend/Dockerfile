FROM python:3.11-slim

# System dependencies for OpenCV and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libpq-dev \
        gcc \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libpangocairo-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# MOCK_INFERENCE=true skips installing torch/ultralytics entirely — detector.py
# generates fake-but-plausible detections instead (see app/config.py). Set to
# false to install the real model weights and run live YOLO11n inference.
ARG MOCK_INFERENCE=true

# Install PyTorch (CPU) + ultralytics from the official PyTorch wheel index.
# CPU-only build is ~250 MB but has no CUDA dependency — fine for a server
# container that delegates GPU work to the edge device.
RUN if [ "$MOCK_INFERENCE" = "false" ]; then \
        pip install --no-cache-dir torch torchvision \
            --index-url https://download.pytorch.org/whl/cpu && \
        pip install --no-cache-dir ultralytics==8.3.0; \
    fi

# Install remaining dependencies (all small — fast download)
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout=300 --retries 5 -r requirements.txt

# Copy application source
COPY . .

# buildwatch_best.pt is mounted via volume — no pre-download needed at build time

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
