FROM public.ecr.aws/docker/library/python:3.12.9-slim@sha256:aaa3f8cb64dd64e5f8cb6e58346bdcfa410a108324b0f28f1a7cc5964355b211

LABEL org.opencontainers.image.vendor="Ministry of Justice" \
  org.opencontainers.image.authors="GitHub Community <github-community@digital.justice.gov.uk>" \
  org.opencontainers.image.title="GitHub Community" \
  org.opencontainers.image.description="Passionate engineers delivering great services" \
  org.opencontainers.image.url="https://github.com/ministryofjustice/github-community"

ENV APP_DIRECTORY="/app" \
  CONTAINER_GID="1000" \
  CONTAINER_GROUP="nonroot" \
  CONTAINER_UID="1000" \
  CONTAINER_USER="nonroot" \
  PYTHONDONTWRITEBYTECODE="1" \
  PYTHONUNBUFFERED="1"

# Set options for safe shell execution
SHELL ["/bin/bash", "-e", "-u", "-o", "pipefail", "-c"]

# Setup the application directory
RUN <<EOF
groupadd \
  --gid ${CONTAINER_GID} \
  ${CONTAINER_GROUP}

useradd \
  --uid ${CONTAINER_UID} \
  --gid ${CONTAINER_GROUP} \
  --create-home \
  --shell /bin/bash \
  ${CONTAINER_USER}

install --directory --owner "${CONTAINER_USER}" --group "${CONTAINER_GROUP}" --mode 0755 "${APP_DIRECTORY}"
EOF

# Migrate files to the application directory
WORKDIR ${APP_DIRECTORY}
COPY Pipfile Pipfile
COPY Pipfile.lock Pipfile.lock
COPY app app
COPY migrations migrations

# Ensure nonroot user and group can read and write to the application directory
RUN chown -R "${CONTAINER_USER}:${CONTAINER_GROUP}" "${APP_DIRECTORY}" \
  && chmod -R u+rwX,g+rX,o+rX "${APP_DIRECTORY}"

# Install pipenv and dependencies
RUN <<EOF
python3 -m pip install --no-cache-dir pipenv
pipenv install --system --deploy --ignore-pipfile
EOF

EXPOSE 4567

# Switch to nonroot user
USER ${CONTAINER_UID}

ENTRYPOINT ["gunicorn", "--bind=0.0.0.0:4567", "app.run:app()"]
