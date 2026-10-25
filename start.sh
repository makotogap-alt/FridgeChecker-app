#!/bin/sh
set -eu
python migrate.py
exec gunicorn app:app
