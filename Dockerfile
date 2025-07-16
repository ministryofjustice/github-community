FROM python:3.14.0b4-alpine3.22@sha256:de292948e75ecd646ed26f416cf2c4f7a8aae28527de1d7927522aad2d2f1db2

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

SHELL ["/bin/bash", "-e", "-u", "-o", "pipefail", "-c"]

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

WORKDIR ${APP_DIRECTORY}

COPY Pipfile Pipfile
COPY Pipfile.lock Pipfile.lock
COPY app app

RUN <<EOF
python3 -m pip install --no-cache-dir pipenv
pipenv install --system --deploy --ignore-pipfile
EOF

EXPOSE 4567

USER ${CONTAINER_UID}

ENTRYPOINT ["gunicorn", "--bind=0.0.0.0:4567", "app.run:app()"]
