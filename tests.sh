#!/usr/bin/env bash
nosetests . --with-randomly --with-coverage --cover-package=ndb_audit --with-gae --gae-lib-root=$GAE_LIB_ROOT --processes=-1 --exclude-dir-file=./exclude_dirs.txt
