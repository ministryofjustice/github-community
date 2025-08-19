#!/usr/bin/env bash

echo "Running 'uv sync --frozen'"
uv sync --frozen

echo "Running 'uv run pre-commit install'"
uv run pre-commit install
