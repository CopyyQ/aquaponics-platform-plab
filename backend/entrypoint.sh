#!/bin/sh
set -e
alembic upgrade head
python scripts/sync_v1_project_scenarios.py
python -m scripts.seed
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
