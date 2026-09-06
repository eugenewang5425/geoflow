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


## 2025 全年扩展（数据 + 可视化 + 3D + 预测）

- **数据**：12 个月 TLC 黄色出租车（2025-01..12，约 4,300 万行原始记录），每月独立
  MapReduce 作业；Mapper 增加 `T|day|zone|hour` 日粒度维度（供时序预测），
  结果分流到 `data/runs/<run_id>/daily.tsv`，不撑大结果 JSON。
- **天气特征**：`scripts/fetch_weather.py` 从 Open-Meteo 历史归档 API 获取
  Central Park 2025 逐小时气象（气温/降水/降雪/风/湿度/云量/能见度 + 日级聚合），
  原始数据与 SHA-256 记录在 `data/raw/weather_2025_manifest.json`。
- **年度合并**：`scripts/merge_year.py` 将所有月结果合并为 `data/results/year.json`
  （月×小时热力、星期×小时、区域×月矩阵、月度曲线）与 `od_year.json`
  （TOP OD、桑基、机场进出），API：`/api/year`、`/api/od`。
- **可视化**：年度热力图、月度趋势、工作日节律；OD 桑基图 + 行政区 OD 矩阵 +
  机场进出（JFK/LGA/EWR）；**3D**（echarts-gl）：分区柱体城市投影、
  区域×小时 3D 矩阵、星期×小时 3D 曲面——`web/vendor/` 本地化，离线可用。
- **需求预测**：`scripts/forecast.py`（LightGBM + 天气 + 日历 + 滞后特征；
  1-10 月训练、11 月验证、12 月测试，时间严格外推；基线 = 上周同期）。
  输出 `evidence/forecast.json`（指标、特征重要性、天气影响）与
  `data/results/forecast*.json`（区域级预测/误差、榜首区域曲线），
  API：`/api/forecast`、`/api/forecast-curve`。

```powershell
.venv\Scripts\python.exe scripts/fetch_weather.py    # 天气（已下载可不重复）
.venv\Scripts\python.exe -m geoflow run --month 2025-10 --reducers 2   # 月度作业（每 月一个）
.venv\Scripts\python.exe scripts/merge_year.py       # 年度合并
.venv\Scripts\python.exe scripts/forecast.py         # 需求预测（LightGBM）
.venv\Scripts\python.exe scripts/verify_result.py    # 最新月独立逐键验证
```

> 天气数据来源：Open-Meteo（CC-BY 4.0 署名要求，非商业免费使用）。
> 预测口径：单步回测；滞后特征使用观测值；模型为梯度提升而非时序状态空间模型。

## 文档

- `docs/background.md`：项目背景（前期 VMware 三节点集群实验 → 本项目）
- `evidence/`：对照实验与精确验证的实测数据
- `data/runs/<run_id>/`：每次作业的 driver/hadoop 日志、HDFS fsck、History 服务 JSON

## 2026-09 工程扩展（CI · E2E · 性能实验 · 容错演示 · 引擎对比 · 实时回放 · 容器化）

### 性能实验矩阵（「实验与作业」页全部可视化）

- **Map 任务粒度扫描**：把月份重分片为 14/36/72/144 个平衡文件 →
  29.7 / 48.0 / 65.9 / 113.9 s。重要教训：Hadoop 3 FileInputFormat 对
  小于块大小(16MB)的文件**忽略** `mapreduce.job.maps` 与 `split.maxsize`
  提示（streaming 的 `-inputformat CombineFileInputFormat` 亦被忽略），
  物理重分片才是唯一可靠旋钮（`scripts/perf_experiments.py` + `map_sweep.sh`）。
- **弱扩展**：12 个月独立作业（348 万→460 万行）耗时 215–265s 基本平坦。
- **Combiner 开关 × reducers(1/2/4)**：`scripts/experiments.py` 全矩阵，
  逐键精确比对。
- **容错演示**：`scripts/fault_demo.py` 作业运行中终止 worker1 的
  DataNode → map 改读 worker2 副本，作业 75s 成功、集群自愈。
  （若连 NodeManager 一起杀，AM 重启的全量 JVM 风暴会击穿单机 15GB
  内存——这正是真多机部署要解决的问题，已如实记录在证据里。）
- **引擎对比**：`scripts/spark_compare.py`（Spark 3.5.1 local[2]，同一
  聚合同一 HDFS 输入）：MR 净耗时 32.5s vs Spark 热跑 27.5s（×1.18，
  暖集群口径；旧记录的 ×7.93 是冷/暖混比的错误口径），有效行
  3,288,166 与 MR 输出逐行一致。

### 实时回放（「实时回放」页签）

`/api/live/meta|frame`：12 月 430 万出行按原始时间戳建分钟索引，逐分钟
回放到分区热力地图（×60/×360/×900 变速、暂停、TOP 区域榜）。事件结构
与 Kafka 消费者一致，替换事件源即成真·流式。

### 节点检测台（「系统架构」页）

DataNode / NodeManager 实时指标（状态、容器、vCore、内存、HDFS 磁盘、
心跳）+ 集群整体与单节点启停控制（`hadoop.sh start|stop-node`），可现场
演示单点故障与副本容错。

### CI + E2E + Docker

- `.github/workflows/ci.yml`：push 自动 ruff + pytest + Playwright E2E；
- `scripts/e2e_check.py`：无头 Chromium 走 7 个页签，断言关键元素与
  未捕获 JS 错误（WebGL 缺失时断言 2D 降级路径）；
- `Dockerfile` + `compose.yml`：`docker compose up --build` 一键拉起
  服务层（Hadoop 集群仍设计在宿主 WSL2，经 ./data 卷共享结果）。

### 预测扩展

- **分位数区间**：q10/q90 LightGBM，12 月测试窗覆盖率 84%（目标 80%），
  预测曲线图带置信带；
- **邻域滞后特征消融**：几何邻接(≤800m)邻居同小时滞后均值 → RMSE
  19.4 vs 19.1（无增益，与自身滞后冗余），主模型不采用——负结果如实
  记录于 `evidence/forecast.json`。

```powershell
.venv\Scripts\python.exe scripts/perf_experiments.py   # Map 扫描 + 弱扩展
.venv\Scripts\python.exe scripts/fault_demo.py         # 容错演示
.venv\Scripts\python.exe scripts/spark_compare.py      # MR vs Spark
.venv\Scripts\python.exe scripts/e2e_check.py          # 浏览器 E2E（需 playwright）
docker compose up --build                               # 服务层容器化
```
