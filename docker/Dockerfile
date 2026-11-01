# ==============================================================================
# Stage 1: Builder — install dependencies
# ==============================================================================
FROM python:3.12-slim AS builder

WORKDIR /build

# Install system deps for building
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install .

# ==============================================================================
# Stage 2: Runtime — slim final image
# ==============================================================================
FROM python:3.12-slim AS runtime

# Install runtime-only system deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 libmagic1 curl && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1001 appuser && \
    useradd --uid 1001 --gid appuser --shell /bin/bash --create-home appuser

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Copy entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create uploads directory
RUN mkdir -p /app/uploads && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/healthz || exit 1

ENTRYPOINT ["/entrypoint.sh"]
