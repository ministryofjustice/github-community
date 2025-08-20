.PHONY: container-build container-test container-scan database-create-migration database-start database-stop flask-run test test-reports uv-pre-commit-install uv-activate uv-sync

SHELL := /bin/bash

CONTAINER_IMAGE_NAME     ?= ministryofjustice/github-community
CONTAINER_IMAGE_TAG      ?= local
CONTAINER_NAME           ?= github-community

container-build:
	@echo "Building container image $(CONTAINER_IMAGE_NAME):$(CONTAINER_IMAGE_TAG)"
	docker build --platform linux/amd64 --file Dockerfile --tag $(CONTAINER_IMAGE_NAME):$(CONTAINER_IMAGE_TAG) .

container-test: container-build
	@echo "Testing container image $(CONTAINER_IMAGE_NAME):$(CONTAINER_IMAGE_TAG)"
	container-structure-test test --platform linux/amd64 --config test/container-structure-test.yml --image $(CONTAINER_IMAGE_NAME):$(CONTAINER_IMAGE_TAG)

container-scan: container-test
	@echo "Scanning container image $(CONTAINER_IMAGE_NAME):$(CONTAINER_IMAGE_TAG) for vulnerabilities"
	trivy image --platform linux/amd64 --severity HIGH,CRITICAL $(CONTAINER_IMAGE_NAME):$(CONTAINER_IMAGE_TAG)

container-start: container-build database-start
	@echo "Starting container"
	CONTAINER_IMAGE_NAME=$(CONTAINER_IMAGE_NAME) CONTAINER_IMAGE_TAG=$(CONTAINER_IMAGE_TAG) docker compose --file=contrib/docker-compose.yaml up app --detach

container-stop:
	@echo "Stopping container"
	CONTAINER_IMAGE_NAME=$(CONTAINER_IMAGE_NAME) CONTAINER_IMAGE_TAG=$(CONTAINER_IMAGE_TAG) docker compose --file=contrib/docker-compose.yaml down app --remove-orphans

container-restart: container-stop container-start

database-create-migration:
	@echo "Creating database migration"
	alembic revision --message 'project_name_description'

database-start:
	@echo "Starting PostgreSQL"
	docker compose --file contrib/docker-compose.yaml up database --detach

database-stop:
	@echo "Stopping PostgreSQL"
	docker compose --file contrib/docker-compose.yaml down --remove-orphans

flask-run: database-start
	@echo "Starting Flask application"
	flask --app app.app --debug run

test:
	@echo "Running pytest"
	coverage run -m pytest

test-reports:
	@echo "Generating test reports"
	coverage report --omit=./test/** --sort=cover --show-missing --skip-empty

uv-pre-commit-install: uv-sync
	@echo "Installing pre-commit hooks"
	uv run pre-commit install

uv-pre-commit-update:
	@echo "Updating pre-commit hooks"
	uv run pre-commit autoupdate --freeze

uv-activate: uv-sync
	@echo "Activating virtual environment"
	source .venv/bin/activate

uv-sync:
	@echo "Synchronising uv dependencies"
	uv sync --locked
