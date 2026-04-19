# B5 BFF (GET-only, read-only) — minimal local-demo image.
#
# Not hardened for production. Goal: `docker compose up` brings
# the frontend and the BFF up locally for a demo session.
#
# Assumptions:
#   - /app/bundles is populated by a read-only bind mount from
#     the host's `bundles/` directory (see docker-compose.yml).
#   - the runtime never writes to the filesystem.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r /app/backend/requirements.txt

COPY backend /app/backend

# Bundle root defaults to the mounted /app/bundles directory.
# Compose sets this explicitly; keep it here so the image also
# works standalone when someone bind-mounts a bundle root.
ENV B5_BUNDLES_ROOT=/app/bundles

EXPOSE 8001

# Run a non-root user — cheap extra safety; no functional change.
RUN useradd --create-home --uid 10001 b5 && chown -R b5:b5 /app
USER b5

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8001"]
