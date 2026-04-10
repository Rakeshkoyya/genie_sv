# ─── Stage 1: dependency resolution ───────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system dependencies required for pycairo / xhtml2pdf
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    pkg-config \
    libcairo2-dev \
    libffi-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy lockfile and project metadata first for layer caching
COPY pyproject.toml uv.lock ./

# Install deps into a local venv (no project package itself yet)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source
COPY . .

# Install project package
RUN uv sync --frozen --no-dev

# ─── Stage 2: production image ────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Copy the installed venv and source from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app /app

# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# EXPOSE 8080
# for local we need to chnage this is 8000
EXPOSE 8000

# CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
# for local we need to chnage this is 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]