#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export JAVA_HOME="$ROOT/.runtime/java11"
export PATH="$JAVA_HOME/bin:$PATH"
export HADOOP_CONF_DIR="$ROOT/.runtime/conf/master"
MONTH="${1:?month}" GLOB="${2:?hdfs glob}"
exec "$ROOT/.runtime/spark-3.5.1-bin-hadoop3/bin/spark-submit" \
  --master "${SPARK_MASTER:-local[2]}" \
  --driver-memory 2g \
  "$ROOT/scripts/spark_od.py" "$MONTH" "$GLOB"
