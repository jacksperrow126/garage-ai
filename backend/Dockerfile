# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system deps only if something needs them — keep the layer tiny
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Hatch needs the `app/` package present to build the wheel, so copy
# pyproject.toml + app together before `pip install .`. Any app-code
# change invalidates the dep layer; for a tiny service this is fine.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

# Cloud Run listens on $PORT. Uvicorn binds to it directly.
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
