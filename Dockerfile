##################################################
# Stage: uv
# From: ghcr.io/astral-sh/uv:python3.13-alpine
##################################################
FROM ghcr.io/astral-sh/uv:python3.13-alpine@sha256:d9b06918a738c5779ca55951dc6748afd54757d9d1be54e042b021c7b9309d57 AS uv

##################################################
# Stage: builder
# From: docker.io/python:3.13-alpine3.22
##################################################
FROM docker.io/python:3.13-alpine3.22@sha256:9ba6d8cbebf0fb6546ae71f2a1c14f6ffd2fdab83af7fa5669734ef30ad48844 AS builder

ARG BUILD_DEV="false"

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE="copy"

WORKDIR /app

COPY --from=uv /usr/local/bin/uv /usr/local/bin/uv

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
<<EOF
if [[ "${BUILD_DEV}" == "true" ]]; then
  uv sync --locked --no-install-project --no-editable
else
  uv sync --locked --no-install-project --no-editable --no-dev
fi
EOF

##################################################
# Stage: final
# From: docker.io/python:3.13-alpine3.22
##################################################
FROM docker.io/python:3.13-alpine3.22@sha256:9ba6d8cbebf0fb6546ae71f2a1c14f6ffd2fdab83af7fa5669734ef30ad48844 AS final

LABEL org.opencontainers.image.vendor="Ministry of Justice" \
      org.opencontainers.image.authors="GitHub Community <github-community@digital.justice.gov.uk>" \
      org.opencontainers.image.title="GitHub Community" \
      org.opencontainers.image.description="Passionate engineers delivering great services" \
      org.opencontainers.image.url="https://github.com/ministryofjustice/github-community"

ENV CONTAINER_USER="nonroot" \
    CONTAINER_UID="65532" \
    CONTAINER_GROUP="nonroot" \
    CONTAINER_GID="65532" \
    APP_HOME="/app" \
    PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1


RUN <<EOF
addgroup -g ${CONTAINER_GID} ${CONTAINER_GROUP}

adduser -D -H -u ${CONTAINER_UID} -G ${CONTAINER_GROUP} ${CONTAINER_USER}

install --directory --mode=0755 --owner="${CONTAINER_USER}" --group="${CONTAINER_GROUP}" "${APP_HOME}"
EOF

WORKDIR ${APP_HOME}
COPY --from=builder --chown=${CONTAINER_UID}:${CONTAINER_GID} /app/.venv /app/.venv
COPY --chown=${CONTAINER_UID}:${CONTAINER_GID} app app
COPY --chown=${CONTAINER_UID}:${CONTAINER_GID} migrations migrations

USER ${CONTAINER_UID}

ENTRYPOINT ["gunicorn", "--bind=0.0.0.0:4567", "app.run:app()"]
