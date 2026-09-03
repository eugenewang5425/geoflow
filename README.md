# GeoFlow — 城市出行时空大数据分析平台（Hadoop）

基于 Hadoop 3.4.2（HDFS + YARN + MapReduce Streaming）的分布式时空大数据课程项目。
数据源：纽约市出租车与轿车管理局（TLC）2025 年 1 月黄色出租车出行记录，347.5 万条。

## 架构

- `geoflow/`：Python 平台层（数据导入 / 作业提交 / 结果发布校验 / FastAPI 服务）
- `jobs/`：Hadoop Streaming Python Mapper / Reducer（纯标准库，可同时用作 Combiner）
- `scripts/`：集群管理（启动 / 停止 / 状态 / 自愈会话）、数据校验、实验矩阵
- `web/`：前端可视化（SVG 地图 + 排行 + 小时分布 + 数据质量面板）
- `data/`：原始数据、输入分片（35×10 万行 CSV）、每次作业的运行记录与 HDFS 校验结果
- `.runtime/`：本地隔离的 Java 11 与 Hadoop 发行版、节点配置与状态（不随仓库提交）

> 说明：本集群运行在单台主机 WSL2 内，包含 1 个 NameNode、2 个 DataNode、
> 1 个 ResourceManager、2 个 NodeManager，全部服务通过回环地址上的独立端口隔离，
> 属于"单机多节点"实验形态；逻辑拓扑与三节点虚拟机集群一一对应。

## 快速开始

```powershell
uv sync                          # Python 依赖（FastAPI/pyarrow/shapely 等）
python scripts/download_runtime.py   # 下载并校验 Java 11 + Hadoop 3.4.2（约 400 MB）
wsl -d Ubuntu-24.04 -- bash scripts/hadoop.sh install
.Start-GeoFlow.ps1              # 启动集群（自愈会话）+ API + Web
# 浏览器打开 http://127.0.0.1:8765
```

作业与验证：

```powershell
.venv\Scripts\python.exe -m geoflow ingest   # 下载 TLC 数据并切分（已含 2025-01）
.venv\Scripts\python.exe -m geoflow run --month 2025-01 --reducers 2
.venv\Scripts\python.exe scripts/verify_result.py    # 独立聚合精确比对
.venv\Scripts\python.exe scripts/experiments.py      # 实验矩阵（reducers×combiner×容错）
```

停止：`.Stop-GeoFlow.ps1`（保留数据与 HDFS 元数据）。

## 关键机制

- **数据分片与指纹**：CSV 分片经 manifest（含 SHA-256）上传至 HDFS，按内容指纹建目录
  `/geoflow/raw/<month>/<fingerprint>`，避免重复上传；
- **整数定点聚合**：距离/时长/金额以 milli-miles / 秒 / 分 的整数相加，Combiner 与
  Reducer 使用同一函数，求和严格可结合，任意组合下与顺序参考结果逐键一致；
- **守恒校验**：区域×小时、日期、OD 三组键的总数相等，且与输入行数严格对账，
  不一致拒绝发布结果；
- **容错实验**：`--fail-first` 令首个 map 任务第一次尝试失败，验证 YARN 重试与
  "任务失败不出错、不影响结果"的行为；
- **独立验证**：`verify_result.py` 用不依赖 reducer/combiner 的纯顺序聚合，
  与 Hadoop 输出逐键精确比对，结果写入 `evidence/verification.json`。

## 文档

- `docs/background.md`：项目背景（前期 VMware 三节点集群实验 → 本项目）
- `evidence/`：对照实验与精确验证的实测数据
- `data/runs/<run_id>/`：每次作业的 driver/hadoop 日志、HDFS fsck、History 服务 JSON
