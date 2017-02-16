#!/usr/bin/env bash
nosetests . --with-coverage --cover-package=ndb_audit --cover-html --cover-html-dir=./cover-html --with-gae --gae-lib-root=$GAE_LIB_ROOT --processes=-1
