# syntax=docker/dockerfile:1.6
FROM python:3.11-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy source FIRST so pyproject's `setuptools.packages.find where=["src"]`
# can resolve packages during editable install. Layer cache will still
# kick in unless src/ contents change, which is fine for our dev loop.
COPY pyproject.toml ./
COPY src ./src

RUN pip install --upgrade pip && pip install -e ".[dev]"

# Remaining app artifacts
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts

EXPOSE 8000

# Default CMD is API; worker overrides in compose
CMD ["uvicorn", "cloude_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
