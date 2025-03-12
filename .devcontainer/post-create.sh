#!/usr/bin/env bash

# Install Pipenv
python3 -m pip install --no-cache-dir pipenv

# Install Dependencies
pipenv install --system --deploy --ignore-pipfile
