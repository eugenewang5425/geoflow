#!/usr/bin/env bash
cd '/mnt/d/项目/云计算' || exit 1
echo '=== nm-logs on tmpfs (worker2) ==='
ls -la .runtime/posix/worker2/nm-logs/ 2>/dev/null | head -30
echo '=== Sep app container 000031 ==='
ls -la .runtime/posix/worker2/nm-logs/application_1788463846024_0017/container_1788463846024_0017_01_000031/ 2>/dev/null
echo '=== syslog tail ==='
tail -50 .runtime/posix/worker2/nm-logs/application_1788463846024_0017/container_1788463846024_0017_01_000031/syslog 2>/dev/null
echo '=== stderr ==='
cat .runtime/posix/worker2/nm-logs/application_1788463846024_0017/container_1788463846024_0017_01_000031/stderr 2>/dev/null | tail -30
echo '=== hs_err in container dir ==='
ls .runtime/posix/worker2/nm-logal/usercache/eugen/appcache/application_1788463846024_0017/container_1788463846024_0017_01_000031/ 2>/dev/null
find .runtime/posix/worker2/nm-local -name 'hs_err*' 2>/dev/null | head -5
