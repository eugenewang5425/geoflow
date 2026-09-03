#!/usr/bin/env bash
set -euo pipefail
ROOT=/mnt/d/项目/云计算
cd "$ROOT"
export HADOOP_CONF_DIR="$ROOT/.runtime/conf/master"
. "$HADOOP_CONF_DIR/hadoop-env.sh"
export PATH="$JAVA_HOME/bin:$HADOOP_HOME/bin:$PATH"
echo '=== app log dir ==='
hdfs dfs -ls /geoflow/logs/application_1788463846024_0017/ 2>&1 | head -20
echo '=== failed container 000031 ==='
hdfs dfs -ls /geoflow/logs/application_1788463846024_0017/container_1788463846024_0017_01_000031/ 2>&1 | head -20
echo '=== stderr tail ==='
hdfs dfs -cat /geoflow/logs/application_1788463846024_0017/container_1788463846024_0017_01_000031/stderr 2>&1 | tail -30
echo '=== syslog grep ==='
hdfs dfs -cat /geoflow/logs/application_1788463846024_0017/container_1788463846024_0017_01_000031/syslog 2>&1 | grep -iE 'error|exception|abort|fatal|SIG|hs_err' | tail -20
echo '=== stdout tail ==='
hdfs dfs -cat /geoflow/logs/application_1788463846024_0017/container_1788463846024_0017_01_000031/stdout 2>&1 | tail -10
