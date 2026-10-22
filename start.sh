#!/bin/bash
# TinyToolbox launcher. PORT env var (default 8095). Idempotent: exits if healthy.
cd "$(dirname "$0")"
PORT="${PORT:-8095}"
if curl -s -m 3 "http://127.0.0.1:${PORT}/api/health" | grep -q '"ok": *true'; then exit 0; fi
PID=$(ss -ltnp 2>/dev/null | grep ":${PORT}" | grep -o "pid=[0-9]*" | head -1 | cut -d= -f2)
[ -n "$PID" ] && kill $PID
exec python3 app.py >> server.log 2>&1
