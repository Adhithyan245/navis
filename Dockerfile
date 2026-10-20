# ── Build stage ────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# curl is needed by the HEALTHCHECK below (and the compose healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN addgroup --system navis && adduser --system --group navis

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code (.dockerignore keeps .env, apps/web and
# api_legacy out of the image) plus the knowledge base that
# relocation_plan / essentials_checklist read at runtime.
COPY apps/ ./apps/
COPY knowledge/ ./knowledge/

# Ownership
RUN chown -R navis:navis /app
USER navis

# Expose port
EXPOSE 8100

# Production defaults (override at deploy time).
#   PORT                 port to listen on (Cloud Run sets 8080; Render: 8100)
#   WEB_CONCURRENCY      uvicorn worker processes per container
#   FORWARDED_ALLOW_IPS  proxy IPs/CIDRs trusted for X-Forwarded-For, so rate
#                        limits see real client IPs
ENV ENV=production     DEBUG=false     PORT=8100     WEB_CONCURRENCY=1     FORWARDED_ALLOW_IPS=127.0.0.1     PYTHONUNBUFFERED=1

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3     CMD curl -fs "http://localhost:${PORT}/health" || exit 1

# Graceful shutdown: uvicorn handles SIGTERM natively. With several workers or
# instances, set REDIS_URL (shared cache + rate limits) and
# ACCOUNTS_DATABASE_URL (Postgres) so state isn't per process / on local disk.
CMD ["sh", "-c", "exec uvicorn apps.api.main:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY} --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS}\" --timeout-graceful-shutdown 30 --no-server-header --access-log"]
