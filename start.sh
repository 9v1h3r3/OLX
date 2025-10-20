#!/bin/sh
# start.sh - keep the sender running; restart if script exits
set -e

# if COOKIE_JSON_CONTENT env var provided, write it into cookie.json (keeps secrets out of repo)
if [ -n "$COOKIE_JSON_CONTENT" ]; then
  echo "$COOKIE_JSON_CONTENT" > /app/cookie.json
  echo "cookie.json created from env var"
fi

# ensure chrome_profile dir exists and is writable
mkdir -p /app/chrome_profile
chmod 700 /app/chrome_profile || true

while true; do
  echo "Starting send_min.py at $(date)"
  python /app/send_min.py
  echo "send_min.py exited at $(date). Restarting after sleep..."
  sleep 10
done
