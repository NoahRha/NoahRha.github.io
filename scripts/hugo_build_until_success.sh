#!/usr/bin/env bash
set -u

ROOT_DIR="${1:-$(pwd)}"
RETRY_SECONDS="${HUGO_RETRY_SECONDS:-300}"
MAX_ATTEMPTS="${HUGO_MAX_ATTEMPTS:-0}"
LOG_FILE="${HUGO_RETRY_LOG:-$ROOT_DIR/tmp/hugo-build-until-success.log}"

mkdir -p "$(dirname "$LOG_FILE")"
cd "$ROOT_DIR" || exit 2

attempt=1
while true; do
  timestamp="$(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "[$timestamp] hugo build attempt $attempt" | tee -a "$LOG_FILE"

  if hugo --minify 2>&1 | tee -a "$LOG_FILE"; then
    timestamp="$(date '+%Y-%m-%d %H:%M:%S %Z')"
    echo "[$timestamp] hugo build succeeded on attempt $attempt" | tee -a "$LOG_FILE"
    exit 0
  fi

  timestamp="$(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "[$timestamp] hugo build failed on attempt $attempt" | tee -a "$LOG_FILE"

  if [[ "$MAX_ATTEMPTS" -gt 0 && "$attempt" -ge "$MAX_ATTEMPTS" ]]; then
    echo "Reached HUGO_MAX_ATTEMPTS=$MAX_ATTEMPTS; stopping." | tee -a "$LOG_FILE"
    exit 1
  fi

  echo "Waiting ${RETRY_SECONDS}s before retry..." | tee -a "$LOG_FILE"
  sleep "$RETRY_SECONDS"
  attempt=$((attempt + 1))
done
