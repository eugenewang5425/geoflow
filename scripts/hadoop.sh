#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export JAVA_HOME="$ROOT/.runtime/java11"
export HADOOP_HOME="$ROOT/.runtime/hadoop-3.4.2"
export HADOOP_COMMON_HOME="$HADOOP_HOME" HADOOP_HDFS_HOME="$HADOOP_HOME"
export HADOOP_YARN_HOME="$HADOOP_HOME" HADOOP_MAPRED_HOME="$HADOOP_HOME"
export PATH="$JAVA_HOME/bin:$HADOOP_HOME/bin:$PATH"
export LANG=C.UTF-8

node_env() {
  export HADOOP_CONF_DIR="$ROOT/.runtime/conf/$1"
  export HADOOP_PID_DIR="$ROOT/.runtime/pids/$1"
  export HADOOP_LOG_DIR="$ROOT/logs/hadoop/$1"
  export YARN_PID_DIR="$HADOOP_PID_DIR" YARN_LOG_DIR="$HADOOP_LOG_DIR"
  mkdir -p "$HADOOP_PID_DIR" "$HADOOP_LOG_DIR"
}

# Settle every daemon of this installation, then purge stale pid files so that
# "yarn --daemon start" never skips a node just because a dead pid file remains.
clean() {
  bash "$0" stop >/dev/null 2>&1 || true
  sleep 2
  rm -rf "$ROOT/.runtime/pids"
  pkill -9 -f "$HADOOP_HOME" >/dev/null 2>&1 || true
  sleep 1
}

# Exit 0 only when both DataNodes and both NodeManagers are registered.
healthy() {
  local dns nm
  dns="$(hdfs dfsadmin -report 2>/dev/null | sed -n 's/^Live datanodes (\([-0-9]*\)).*/\1/p')"
  nm="$(yarn node -list 2>/dev/null | sed -n 's/^Total Nodes:\([0-9][0-9]*\)$/\1/p')"
  [ "$dns" = "2" ] && [ "$nm" = "2" ]
}

node_env master
case "${1-status}" in
  install)
    mkdir -p "$ROOT/.runtime/java11"
    if [ ! -x "$JAVA_HOME/bin/java" ]; then
      tar -xzf "$ROOT/.runtime/downloads/java11.tar.gz" --strip-components=1 -C "$JAVA_HOME"
    fi
    if [ ! -x "$HADOOP_HOME/bin/hadoop" ]; then
      tar -xzf "$ROOT/.runtime/downloads/hadoop-3.4.2-lean.tar.gz" -C "$ROOT/.runtime"
    fi
    python3 "$ROOT/scripts/configure_hadoop.py"
    hadoop version
    ;;
  start)
    test -f "$HADOOP_CONF_DIR/core-site.xml"
    clean
    if [ ! -d "$ROOT/.runtime/state/master/name/current" ]; then
      hdfs namenode -format -nonInteractive geoflow-lab
    fi
    hdfs --daemon start namenode
    yarn --daemon start resourcemanager
    for worker in worker1 worker2; do
      node_env "$worker"
      hdfs --daemon start datanode
      yarn --daemon start nodemanager
    done
    node_env master
    hdfs dfsadmin -safemode wait
    mapred --daemon start historyserver
    for wait_step in $(seq 1 30); do
      healthy && break
      sleep 2
    done
    if healthy; then
      echo "Cluster healthy: 2 DataNodes, 2 NodeManagers"
      yarn node -list
    else
      echo "Cluster NOT healthy after 60s:" >&2
      hdfs dfsadmin -report | tail -5 >&2
      yarn node -list >&2
      exit 1
    fi
    ;;
  stop)
    mapred --daemon stop historyserver
    for worker in worker1 worker2; do
      node_env "$worker"
      yarn --daemon stop nodemanager
      hdfs --daemon stop datanode
    done
    node_env master
    yarn --daemon stop resourcemanager
    hdfs --daemon stop namenode
    ;;
  status)
    if healthy; then
      echo "GeoFlow cluster online"
      yarn node -list
    else
      echo "GeoFlow cluster DEGRADED (expected 2 DataNodes + 2 NodeManagers)" >&2
      hdfs dfsadmin -report | tail -5 >&2
      yarn node -list >&2
      exit 1
    fi
    ;;
  dfs) shift; hdfs dfs "$@" ;;
  fsck) shift; hdfs fsck "$@" ;;
  yarn) shift; yarn "$@" ;;
  *) echo "Usage: bash scripts/hadoop.sh install|start|stop|status|dfs|fsck|yarn"; exit 2 ;;
esac
