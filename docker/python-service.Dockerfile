# syntax=docker/dockerfile:1
# One Dockerfile for every Python service of the uv workspace (D15).
#
#   docker build -f docker/python-service.Dockerfile \
#     --build-arg PACKAGE=socialsignal-migrations \
#     --build-arg SERVICE_DIR=services/migrations .
#
# Only the service's own directory and the shared packages are copied, so a
# change in another service does not rebuild this image or change its tag.

ARG PYTHON_IMAGE=python:3.12.14-slim-trixie
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.21

FROM ${UV_IMAGE} AS uv

# ---------------------------------------------------------------- build ---
FROM ${PYTHON_IMAGE} AS build
ARG PACKAGE
ARG SERVICE_DIR
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src

# 1. Third-party dependencies only, straight from the lock file. This layer
#    is reused from the cache until uv.lock changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-workspace --package "$PACKAGE"

# 2. The service and the shared packages, installed non-editable so the
#    virtualenv is self-contained and is all the final image needs.
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY ${SERVICE_DIR} ./${SERVICE_DIR}
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package "$PACKAGE"

# -------------------------------------------------------------- runtime ---
FROM ${PYTHON_IMAGE}
RUN useradd --system --uid 10001 --user-group --no-create-home \
      --shell /usr/sbin/nologin app
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
# Numeric user, so Kubernetes can verify runAsNonRoot.
USER 10001:10001
# The command (python -m <module>) is set per component in the Helm chart.
