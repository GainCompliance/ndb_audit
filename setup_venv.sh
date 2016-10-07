#!/usr/bin/env bash
# assumes virtualenv is already installed
virtualenv ./venv
source ./venv/bin/activate
pip install -U -r ./requirements-dev.txt # dev goes to the venv
