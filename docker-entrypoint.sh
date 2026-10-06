#!/bin/sh
# Container entrypoint: apply database migrations, then start the web server.
set -eu

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "[entrypoint] applying database migrations"
  attempt=1
  until alembic upgrade head; do
    if [ "$attempt" -ge 10 ]; then
      echo "[entrypoint] migrations failed after ${attempt} attempts; exiting" >&2
      exit 1
    fi
    echo "[entrypoint] migration attempt ${attempt} failed; retrying in 3s" >&2
    attempt=$((attempt + 1))
    sleep 3
  done
fi

echo "[entrypoint] starting gunicorn on port ${PORT:-8000}"
exec gunicorn app.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers "${WEB_CONCURRENCY:-2}" \
  --bind "0.0.0.0:${PORT:-8000}" \
  --timeout 120 \
  --graceful-timeout 30 \
  --keep-alive 5 \
  --worker-tmp-dir /dev/shm \
  --error-logfile -
