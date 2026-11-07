# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.11.8 AS uv

FROM python:3.12-slim-bookworm AS python-base
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY README.md LICENSE NOTICE ./
COPY src ./src
COPY examples ./examples
COPY contracts/v1 ./contracts/v1
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN uv sync --frozen --no-dev --no-editable
RUN mkdir /data

# Default API and worker include pinned model code; prepare weights explicitly in a mounted cache.
FROM python-base AS api
EXPOSE 8000
ENTRYPOINT ["forecast-anything"]
CMD ["serve", "--db", "/data/state.db", "--host", "0.0.0.0", "--port", "8000"]

FROM api AS worker
CMD ["worker", "--db", "/data/state.db"]

# Compatibility aliases for existing Compose commands.
FROM api AS api-timestral
FROM worker AS worker-timestral

FROM node:24-bookworm-slim AS console-build
WORKDIR /app
COPY apps/console/package.json apps/console/package-lock.json ./
RUN npm ci --ignore-scripts
COPY apps/console ./
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.29-alpine AS console
COPY --from=console-build /app/dist /usr/share/nginx/html
EXPOSE 8080

FROM node:24-bookworm-slim AS agent
WORKDIR /app/apps/agent
COPY apps/agent/package.json apps/agent/package-lock.json ./
RUN npm ci --ignore-scripts
COPY apps/agent/agent ./agent
COPY apps/agent/src ./src
COPY apps/agent/tsconfig.json ./
COPY apps/agent/compose ./compose
# The registered tools use core HTTP only, so no sandbox template is needed.
# Keep the Docker socket out of both the build and the running agent container.
RUN NODE_ENV=development FORECAST_AGENT_SCRIPTED_MODEL=1 npm run build -- --skip-sandbox-prewarm
ENV NODE_ENV=production
USER node
EXPOSE 3000
ENTRYPOINT ["sh", "compose/start.sh"]
