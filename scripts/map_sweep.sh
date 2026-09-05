#!/usr/bin/env bash
# Map-task granularity experiment: run the streaming job on a pre-sharded copy
# of the month (data/exp/<K>maps/, K balanced files) so that the map task count
# is determined by the file layout, not by hints Hadoop ignores.
# Usage: map_sweep.sh <K> <run_id>   (K files must already exist locally)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export HADOOP_CONF_DIR="$ROOT/.runtime/conf/master"
source "$HADOOP_CONF_DIR/hadoop-env.sh"
export PATH="$JAVA_HOME/bin:$HADOOP_HOME/bin:$PATH"
KMAPS="${1:?K}" RUN="${2:?run id}" MONTH="${3:-2025-01}"
EXP="/geoflow/exp/$RUN"
OUT="/geoflow/results/$RUN"

hdfs dfs -mkdir -p "$EXP"
for f in "$ROOT/data/exp/$KMAPS/"part-*.csv; do
  hdfs dfs -put -f "$f" "$EXP/"
done

START="$(date +%s.%N)"
hadoop jar "$HADOOP_HOME/share/hadoop/tools/lib/hadoop-streaming-3.4.2.jar" \
  -D "mapreduce.job.name=GeoFlow-sweep-$RUN" \
  -D "mapreduce.job.reduces=2" \
  -D mapreduce.input.fileinputformat.split.maxsize=16777216 \
  -files "$ROOT/jobs/mapper.py,$ROOT/jobs/reducer.py" \
  -input "$EXP" \
  -output "$OUT" \
  -mapper 'python3 mapper.py' \
  -reducer 'python3 reducer.py' \
  -combiner 'python3 reducer.py' \
  -cmdenv "GEOFLOW_MONTH=$MONTH" 2>&1 | tee "$ROOT/data/runs/$RUN/hadoop.log"
END="$(date +%s.%N)"
hdfs dfs -test -e "$OUT/_SUCCESS"
hdfs dfs -rm -r -skipTrash "$EXP" >/dev/null
echo "JOB_SECONDS=$(echo "$END - $START" | bc)"
