#!/usr/bin/env bash
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/logs/session-start.log"
note() { echo "[keepalive $(date '+%F %T')] $*" >> "$LOG"; }
fail() { note "FAILED: $*"; touch "$ROOT/.runtime/session-failed"; exit 1; }

# Wait until Start-GeoFlow.ps1 has prepared markers and configuration.
while [ -f "$ROOT/.runtime/session-active" ] && [ ! -f "$ROOT/.runtime/session-start" ]; do sleep 1; done
[ -f "$ROOT/.runtime/session-active" ] || exit 0
[ -f "$ROOT/.runtime/session-start" ] || fail "session-start marker missing"

# YARN needs a real POSIX workspace, not the DrvFs 9p mount.
if ! mountpoint -q "$ROOT/.runtime/posix"; then
  note "tmpfs POSIX workspace missing; trying to mount"
  # Start-GeoFlow.ps1 mounts as root before releasing the session; this is a fallback.
  sudo -n mount -t tmpfs -o size=2G,mode=0755 geoflow-yarn "$ROOT/.runtime/posix" 2>/dev/null || true
fi
mountpoint -q "$ROOT/.runtime/posix" || fail "tmpfs POSIX workspace not mounted"

# Up to three attempts; start() itself is idempotent and cleans leftovers first.
attempt=0
ready=0
while [ "$attempt" -lt 3 ]; do
  attempt=$((attempt+1))
  note "cluster start attempt $attempt/3"
  if bash "$ROOT/scripts/hadoop.sh" start >> "$LOG" 2>&1; then
    ready=1
    break
  fi
  note "attempt $attempt failed; retrying in 10s"
  sleep 10
done
[ "$ready" = 1 ] || fail "cluster did not become healthy after $attempt attempts"
touch "$ROOT/.runtime/session-ready"
note "cluster is ready; monitoring"

# Monitor: restart on degradation, but never fight a crashing cluster.
degraded=0
while [ -f "$ROOT/.runtime/session-active" ]; do
  if bash "$ROOT/scripts/hadoop.sh" status >/dev/null 2>&1; then
    degraded=0
  else
    degraded=$((degraded+1))
    note "cluster degraded (count=$degraded); attempting recovery"
    if [ "$degraded" -le 3 ]; then
      bash "$ROOT/scripts/hadoop.sh" start >> "$LOG" 2>&1 || note "recovery attempt failed"
    fi
  fi
  sleep 30
done
bash "$ROOT/scripts/hadoop.sh" stop > "$ROOT/logs/session-stop.log" 2>&1 || true
note "session ended; cluster stopped"

