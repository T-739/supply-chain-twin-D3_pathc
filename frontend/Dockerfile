# B5 frontend — minimal local-demo image.
#
# Two-stage: build the Next.js production bundle once, then run
# `next start` in a smaller runtime. Not hardened for
# production. Matches the install/run steps in
# frontend/README.md.
#
# The BFF base URL defaults to `http://backend:8001`, which is
# the compose service name. Override with `B5_BFF_BASE_URL` to
# point at a BFF elsewhere.

# ---------- build stage ----------
FROM node:20-slim AS build

WORKDIR /app

# Install deps first for cache hits on source-only edits.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

# Copy the rest of the frontend source.
COPY frontend/ ./

# next.config.js reads `B5_BFF_BASE_URL` at server startup, not
# at build time, so we do NOT bake a value in here. The runtime
# stage sets it.
RUN npm run build

# ---------- runtime stage ----------
FROM node:20-slim AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

# Copy the built app and its production dependencies.
COPY --from=build /app /app

# Compose overrides this; keeping a reasonable default lets the
# image stand alone if someone runs it with `--network host`.
ENV B5_BFF_BASE_URL=http://backend:8001

EXPOSE 3000

RUN useradd --create-home --uid 10002 b5 && chown -R b5:b5 /app
USER b5

# next.config.js rewrites /api/bff/* to ${B5_BFF_BASE_URL}/*, so
# the browser never issues a cross-origin call against the BFF.
CMD ["npx", "next", "start", "-H", "0.0.0.0", "-p", "3000"]
