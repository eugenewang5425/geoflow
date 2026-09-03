#!/usr/bin/env bash
export JAVA_HOME=/mnt/d/项目/云计算/.runtime/java11
export HADOOP_HOME=/mnt/d/项目/云计算/.runtime/hadoop-3.4.2
export HADOOP_CONF_DIR=/mnt/d/项目/云计算/.runtime/conf/worker2
export HADOOP_PID_DIR=/mnt/d/项目/云计算/.runtime/pids/worker2
export HADOOP_LOG_DIR=/tmp/nm2test
export YARN_PID_DIR=$HADOOP_PID_DIR
export YARN_LOG_DIR=/tmp/nm2test
export PATH=$JAVA_HOME/bin:$HADOOP_HOME/bin:$PATH
export LANG=C.UTF-8
pkill -9 -f "$HADOOP_HOME" 2>/dev/null; sleep 1
rm -f $HADOOP_PID_DIR/*.pid
mountpoint -q /mnt/d/项目/云计算/.runtime/posix && echo "POSIX: mounted" || echo "POSIX: NOT mounted"
grep -o 'mapreduce.shuffle.port</name><value>[^<]*' $HADOOP_CONF_DIR/core-site.xml || true
echo "===== starting worker2 NM ====="
yarn --daemon start nodemanager
sleep 20
echo "===== PORTS ====="
ss -tlnp 2>/dev/null | grep -E "13562|19562|19572|1805" | cut -c1-110
echo "===== NM2 LOG TAIL ====="
tail -6 /tmp/nm2test/hadoop-eugen-nodemanager-WW.log 2>/dev/null | cut -c1-150
