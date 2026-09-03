#!/usr/bin/env bash
cd '/mnt/d/项目/云计算' || exit 1
for i in $(seq 1 200); do
  ts=$(date +%H:%M:%S)
  d=$(df -P .runtime/posix 2>/dev/null | awk 'NR==2{print $3"/"$2}')
  w1=$(du -s .runtime/posix/worker1/nm-local 2>/dev/null | awk '{print $1}')
  w2=$(du -s .runtime/posix/worker2/nm-local 2>/dev/null | awk '{print $1}')
  c1=$(ls .runtime/posix/worker1/nm-local/usercache/eugen/appcache 2>/dev/null | wc -l)
  c2=$(ls .runtime/posix/worker2/nm-local/usercache/eugen/appcache 2>/dev/null | wc -l)
  echo "$ts tmpfs=$d w1=${w1}k w2=${w2}k apps=$c1/$c2"
  sleep 3
done
