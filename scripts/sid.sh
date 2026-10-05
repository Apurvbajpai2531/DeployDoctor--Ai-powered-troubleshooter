#!/usr/bin/env bash
# DEV ONLY: prints the session ID of the most recent real browser session.
# Needs the db container running and at least one saved analysis.
SID=$(docker exec deploydoctor-db psql -U deploy -d deploydoctor -tAc \
  "SELECT session_id FROM analyses WHERE session_id NOT LIKE 'test-session-%' ORDER BY created_at DESC LIMIT 1")
if [ -z "$SID" ]; then
  echo "No saved analysis found. Run one analysis in the browser first." >&2
  exit 1
fi
echo "$SID"
