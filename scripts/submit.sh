#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export HADOOP_CONF_DIR="$ROOT/.runtime/conf/master"
source "$HADOOP_CONF_DIR/hadoop-env.sh"
export PATH="$JAVA_HOME/bin:$HADOOP_HOME/bin:$PATH"
MONTH="${1:?month}" RUN="${2:?run id}" REDUCERS="${3:-2}" COMBINE="${4:-1}" FAIL="${5:-0}"
[[ "$MONTH" =~ ^20[0-9]{2}-(0[1-9]|1[0-2])$ ]]
[[ "$RUN" =~ ^[a-zA-Z0-9_-]+$ ]]
[[ "$REDUCERS" =~ ^[1-8]$ ]]
INPUT="$ROOT/data/input/$MONTH"
FINGERPRINT="$(sha256sum "$INPUT/manifest.json" | cut -d' ' -f1)"
HDFS_IN="/geoflow/raw/$MONTH/$FINGERPRINT"
HDFS_OUT="/geoflow/results/$RUN"
LOCAL_OUT="$ROOT/data/runs/$RUN"
mkdir -p "$LOCAL_OUT"
if ! hdfs dfs -test -e "$HDFS_IN/_READY"; then
  hdfs dfs -mkdir -p "$HDFS_IN"
  # No wildcard uploads of manifests, partial files or earlier datasets.
  while IFS= read -r name; do
    hdfs dfs -put -f "$INPUT/$name" "$HDFS_IN/$name"
  done < <(python3 -c 'import json,sys; print("\n".join(s["name"] for s in json.load(open(sys.argv[1]))["shards"]))' "$INPUT/manifest.json")
  hdfs dfs -touchz "$HDFS_IN/_READY"
fi
EXTRA=()
if [ "$COMBINE" = 1 ]; then EXTRA=(-combiner 'python3 reducer.py'); fi
hadoop jar "$HADOOP_HOME/share/hadoop/tools/lib/hadoop-streaming-3.4.2.jar" \
  -D "mapreduce.job.name=GeoFlow-$RUN" \
  -D "mapreduce.job.reduces=$REDUCERS" \
  -D mapreduce.input.fileinputformat.split.maxsize=16777216 \
  -files "$ROOT/jobs/mapper.py,$ROOT/jobs/reducer.py" \
  -input "$HDFS_IN/part-*.csv" \
  -output "$HDFS_OUT" \
  -mapper 'python3 mapper.py' \
  -reducer 'python3 reducer.py' \
  "${EXTRA[@]}" \
  -cmdenv "GEOFLOW_MONTH=$MONTH" \
  -cmdenv "GEOFLOW_FAIL_FIRST=$FAIL" 2>&1 | tee "$LOCAL_OUT/hadoop.log"
hdfs dfs -test -e "$HDFS_OUT/_SUCCESS"
hdfs dfs -cat "$HDFS_OUT/part-*" > "$LOCAL_OUT/output.tsv"
hdfs fsck "$HDFS_IN" -files -blocks -locations > "$LOCAL_OUT/fsck.txt" 2>&1
printf '%s\n' "$HDFS_IN" > "$LOCAL_OUT/hdfs-input.txt"
printf '%s\n' "$HDFS_OUT" > "$LOCAL_OUT/hdfs-output.txt"
