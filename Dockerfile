# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8000

WORKDIR /app

# Install runtime deps first for better Docker layer caching
COPY requirements-service.txt ./
RUN pip install --no-cache-dir -r requirements-service.txt

# Copy app code
COPY . .

# Create non-root user and take ownership
RUN useradd -m -u 10001 appuser \
 && mkdir -p /app/build/uploads /app/build/api-outputs \
 && chown -R appuser:appuser /app

USER appuser

VOLUME ["/app/build"]

EXPOSE 8000

# Healthcheck using stdlib only (no curl)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys;\n\ntry:\n    r=urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)\n    sys.exit(0 if r.getcode()==200 else 1)\nexcept Exception:\n    sys.exit(1)"]

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
