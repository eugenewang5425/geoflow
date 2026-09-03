"""Generate isolated, loopback-only Hadoop configs for a two-worker WSL lab."""
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement, indent

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
HADOOP = RUNTIME / "hadoop-3.4.2"


def xml(path, properties):
    root = Element("configuration")
    for key, value in properties.items():
        prop = SubElement(root, "property")
        SubElement(prop, "name").text = key
        SubElement(prop, "value").text = str(value)
    indent(root)
    ElementTree(root).write(path, encoding="UTF-8", xml_declaration=True)


def main():
    for node in ("master", "worker1", "worker2"):
        conf = RUNTIME / "conf" / node
        conf.mkdir(parents=True, exist_ok=True)
        state = RUNTIME / "state" / node
        state.mkdir(parents=True, exist_ok=True)
        index = 2 if node == "worker2" else 1
        xml(conf / "core-site.xml", {
            "fs.defaultFS": "hdfs://127.0.0.1:19000",
            "hadoop.tmp.dir": state / "tmp",
            # NodeManager loads core-site/yarn-site, but not mapred-site, during ShuffleHandler init.
            "mapreduce.shuffle.port": 19562 + (index - 1)*10,
        })
        xml(conf / "hdfs-site.xml", {
            "dfs.namenode.name.dir": RUNTIME / "state" / "master" / "name",
            "dfs.namenode.rpc-address": "127.0.0.1:19000",
            "dfs.namenode.http-address": "127.0.0.1:19870",
            "dfs.datanode.data.dir": state / "datanode",
            "dfs.datanode.address": f"127.0.0.1:{19866 + (index - 1)*10}",
            "dfs.datanode.ipc.address": f"127.0.0.1:{19867 + (index - 1)*10}",
            "dfs.datanode.http.address": f"127.0.0.1:{19864 + (index - 1)*10}",
            "dfs.datanode.hostname": "127.0.0.1",
            "dfs.namenode.datanode.registration.ip-hostname-check": "false",
            "dfs.replication": 2,
            "dfs.blocksize": 16777216,
            "dfs.namenode.safemode.min.datanodes": 2,
        })
        cp = ",".join(str(HADOOP / "share" / "hadoop" / p) for p in (
            "common/*", "common/lib/*", "hdfs/*", "hdfs/lib/*", "yarn/*", "yarn/lib/*",
            "mapreduce/*", "mapreduce/lib/*"))
        xml(conf / "yarn-site.xml", {
            "yarn.resourcemanager.hostname": "127.0.0.1",
            "yarn.resourcemanager.bind-host": "127.0.0.1",
            "yarn.resourcemanager.address": "127.0.0.1:18032",
            "yarn.resourcemanager.scheduler.address": "127.0.0.1:18030",
            "yarn.resourcemanager.resource-tracker.address": "127.0.0.1:18031",
            "yarn.resourcemanager.admin.address": "127.0.0.1:18033",
            "yarn.resourcemanager.webapp.address": "127.0.0.1:18088",
            "yarn.nodemanager.hostname": "127.0.0.1",
            "yarn.nodemanager.bind-host": "127.0.0.1",
            "yarn.nodemanager.address": f"127.0.0.1:{18041 + (index - 1)*10}",
            "yarn.nodemanager.webapp.address": f"127.0.0.1:{18042 + (index - 1)*10}",
            "yarn.nodemanager.localizer.address": f"127.0.0.1:{18044 + (index - 1)*10}",
            "yarn.nodemanager.local-dirs": RUNTIME / "posix" / node / "nm-local",
            "yarn.nodemanager.log-dirs": RUNTIME / "posix" / node / "nm-logs",
            "yarn.nodemanager.aux-services": "mapreduce_shuffle",
            "yarn.nodemanager.resource.memory-mb": 3072,
            "yarn.nodemanager.resource.cpu-vcores": 3,
            "yarn.scheduler.minimum-allocation-mb": 256,
            "yarn.scheduler.maximum-allocation-mb": 3072,
            "yarn.nodemanager.vmem-check-enabled": "false",
            "yarn.nodemanager.env-whitelist": "JAVA_HOME,HADOOP_COMMON_HOME,HADOOP_HDFS_HOME,"
                "HADOOP_CONF_DIR,HADOOP_YARN_HOME,HADOOP_MAPRED_HOME,PATH,LANG,TZ",
            "yarn.application.classpath": cp,
            "yarn.log-aggregation-enable": "true",
            "yarn.nodemanager.remote-app-log-dir": "/geoflow/logs",
        })
        xml(conf / "mapred-site.xml", {
            "mapreduce.framework.name": "yarn",
            # ShuffleHandler resolves mapreduce.shuffle.port from mapred-site (JobConf), not core-site/yarn-site.
            "mapreduce.shuffle.port": 19562 + (index - 1) * 10,
            "mapreduce.application.classpath": cp,
            "mapreduce.map.memory.mb": 512,
            "mapreduce.map.java.opts": "-Xmx384m",
            "mapreduce.reduce.memory.mb": 768,
            "mapreduce.reduce.java.opts": "-Xmx512m",
            "yarn.app.mapreduce.am.resource.mb": 768,
            "yarn.app.mapreduce.am.command-opts": "-Xmx512m",
            "mapreduce.map.maxattempts": 2,
            "mapreduce.map.speculative": "false",
            "mapreduce.reduce.speculative": "false",
            "mapreduce.jobhistory.address": "127.0.0.1:11020",
            "mapreduce.jobhistory.webapp.address": "127.0.0.1:19888",
        })
        xml(conf / "capacity-scheduler.xml", {
            "yarn.scheduler.capacity.root.queues": "default",
            "yarn.scheduler.capacity.root.default.capacity": 100,
            "yarn.scheduler.capacity.root.default.maximum-capacity": 100,
            "yarn.scheduler.capacity.root.default.state": "RUNNING",
            "yarn.scheduler.capacity.root.default.acl_submit_applications": "*",
            "yarn.scheduler.capacity.maximum-am-resource-percent": 0.4,
            "yarn.scheduler.capacity.resource-calculator":
                "org.apache.hadoop.yarn.util.resource.DefaultResourceCalculator",
        })
        original = HADOOP / "etc" / "hadoop" / "log4j.properties"
        (conf / "log4j.properties").write_bytes(original.read_bytes())
        (conf / "hadoop-env.sh").write_text(
            f'export JAVA_HOME="{RUNTIME}/java11"\n'
            f'export HADOOP_HOME="{HADOOP}"\n'
            f'export HADOOP_COMMON_HOME="{HADOOP}"\n'
            f'export HADOOP_HDFS_HOME="{HADOOP}"\n'
            f'export HADOOP_YARN_HOME="{HADOOP}"\n'
            f'export HADOOP_MAPRED_HOME="{HADOOP}"\n'
            'export HADOOP_HEAPSIZE_MAX=512\n'
            'export LANG=C.UTF-8\n', encoding="utf-8")
        (conf / "yarn-env.sh").write_text(
            f'export YARN_NODEMANAGER_OPTS="-Dmapreduce.shuffle.port={19562 + (index - 1)*10}"\n',
            encoding="utf-8")
    print(f"Configured two workers under {RUNTIME}")


if __name__ == "__main__":
    main()
