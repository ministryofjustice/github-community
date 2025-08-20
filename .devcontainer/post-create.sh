#!/usr/bin/env bash

echo "Running 'uv-sync'"
make uv-sync

echo "Running 'uv-pre-commit-install'"
make uv-pre-commit-install

echo "Running 'database-start'"
make database-start
