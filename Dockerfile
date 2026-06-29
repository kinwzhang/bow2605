FROM python:3.11-slim

# System deps: curl + ca-certs for uv installer
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (better layer caching)
COPY project_navigator/pyproject.toml project_navigator/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy project source
COPY project_navigator/ .

# Set env vars before any runtime steps
ENV FLASK_APP=backend.app:create_app \
    PNAV_DB_PATH=/data/project-navigator.db

# Ensure data directory exists in image (bind mount will overlay it at runtime)
RUN mkdir -p /data

EXPOSE 5000

# Seed uses --db to target the correct DB path from env var,
# skips gracefully if demo user already exists (idempotent).
# gunicorn runs with 2 workers.
CMD ["sh", "-c", "python scripts/seed.py --db $PNAV_DB_PATH 2>/dev/null; exec /app/.venv/bin/gunicorn -b 0.0.0.0:5000 -w 2 --preload --access-logfile - 'backend.app:create_app()'"]