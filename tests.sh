#!/usr/bin/env bash
source ./venv/bin/activate
export GAE_LIB_ROOT=/Users/jason/dev/google_appengine/ # change me to point to your appengine root
rm -rf ./cover-html/
nosetests . --with-coverage --cover-package=ndb_audit --cover-html --cover-html-dir=./cover-html --with-gae --gae-lib-root=$GAE_LIB_ROOT --processes=-1 --exclude-dir-file=./exclude_dirs.txt
