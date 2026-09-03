#!/usr/bin/env bash
cd '/mnt/d/项目/云计算' || exit 1
for i in $(seq 1 90); do
  app=$(ls -t .runtime/posix/worker2/nm-local/usercache/eugen/appcache 2>/dev/null | head -1)
  if [ -n "$app" ]; then
    ls .runtime/posix/worker2/nm-local/usercache/eugen/appcache/$app/ 2>/dev/null | head -1 >/dev/null
    f=$(find .runtime/posix/worker2/nm-local/usercache/eugen/appcache/$app -name launch_container.sh 2>/dev/null | head -1)
    if [ -n "$f" ]; then
      echo "FOUND $f"
      grep -o 'TieredStopAtLevel=[0-9]*' "$f" | head -2
      grep -o '-Xmx[0-9]*m' "$f" | head -2
      exit 0
    fi
    echo "[$(date +%H:%M:%S)] app=$app waiting for launch script..."
  else
    echo "[$(date +%H:%M:%S)] no app yet"
  fi
  sleep 4
done
echo "NOT FOUND"
