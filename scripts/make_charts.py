"""Generate all charts needed by the GeoFlow course report (local YaHei)."""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

ROOT = Path(r"D:\项目\云计算")
OUT = Path(r"C:\Users\eugen\AppData\Local\Temp\geoflow_charts")
OUT.mkdir(parents=True, exist_ok=True)
EVI = ROOT / "evidence"

P = {
    "ink": "#2C3A4F", "body": "#566373", "soft": "#9AA6B2",
    "blue": "#4C7DD8", "teal": "#3D8F88", "amber": "#C7923B",
    "rose": "#B25B6B", "olive": "#849360", "bg": "#F4F6F9",
}
plt.rcParams.update({
    "font.family": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
    "font.size": 10,
    "axes.facecolor": P["bg"],
    "figure.facecolor": "white",
    "axes.edgecolor": P["soft"],
    "axes.linewidth": 0.8,
    "axes.grid": True, "grid.color": "white", "grid.linewidth": 1,
    "axes.axisbelow": True,
    "xtick.color": P["body"], "ytick.color": P["body"],
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.unicode_minus": False,
})


def save(fig, name):
    p = OUT / f"{name}.png"
    fig.savefig(p, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", p)


# --- Figure 1: Map-task granularity sweep ---
sweep = json.loads((EVI / "perf.json").read_text())["map_sweep"]
fig, ax = plt.subplots(figsize=(5.6, 3.2))
xs = [s["map_tasks"] for s in sweep if s.get("map_tasks")]
ys = [s["job_seconds"] for s in sweep if s.get("job_tasks" if False else "job_seconds") and s.get("map_tasks")]
bars = ax.bar([str(x) + " maps" for x in xs], ys, color=P["blue"], width=0.55, edgecolor="white")
for b, v in zip(bars, ys): ax.text(b.get_x() + b.get_width()/2, v + 0.4, f"{v:.1f}", ha="center", color=P["ink"], fontweight="bold")
ax.set_xlabel("Map 任务数 (每个文件 < 16MB 块)", color=P["ink"])
ax.set_ylabel("作业净耗时 (秒)", color=P["ink"])
ax.set_title("扩展性 · Map 任务粒度（2025-01 全月）", color=P["ink"], fontweight="bold", pad=8)
ax.set_ylim(0, max(ys) * 1.2)
save(fig, "fig_map_sweep")

# --- Figure 2: Combiner × reducers (experiments.json) ---
exps = json.loads((EVI / "experiments.json").read_text())["runs"]
data = {}
for r in exps:
    if r.get("status") != "SUCCEEDED" or r.get("fail_first"): continue
    data.setdefault(r["reducers"], {})[r["combiner"]] = r.get("job_elapsed_seconds") or r.get("elapsed_seconds")
reds = sorted(data)
fig, ax = plt.subplots(figsize=(5.6, 3.2))
x = np.arange(len(reds))
w = 0.35
b1 = ax.bar(x - w/2, [data[r][True] for r in reds], w, color=P["teal"], label="combiner 开", edgecolor="white")
b2 = ax.bar(x + w/2, [data[r][False] for r in reds], w, color=P["amber"], label="combiner 关", edgecolor="white")
for bars in (b1, b2):
    for b in bars: ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.5, f"{b.get_height():.1f}", ha="center", color=P["ink"])
ax.set_xticks(x); ax.set_xticklabels([f"{r} reducer" for r in reds])
ax.set_xlabel("Reduce 任务数", color=P["ink"]); ax.set_ylabel("作业净耗时 (秒)", color=P["ink"])
ax.set_title("扩展性 · Combiner 开关对比", color=P["ink"], fontweight="bold", pad=8)
ax.legend(frameon=False)
save(fig, "fig_combiner")

# --- Figure 3: Weak scaling (12 months) ---
scaling = json.loads((EVI / "perf.json").read_text())["scaling"]
fig, ax1 = plt.subplots(figsize=(5.8, 3.2))
months = [s["month"][5:] + "月" for s in scaling]
rows = [s["rows"]/1e6 for s in scaling]
elapsed = [s["elapsed_seconds"] for s in scaling]
ax1.bar(months, rows, color=P["blue"], alpha=0.4, label="有效出行 (百万)", edgecolor="white")
ax1.set_ylabel("有效出行 (百万)", color=P["blue"]); ax1.tick_params(axis="y", colors=P["blue"])
ax2 = ax1.twinx()
ax2.plot(months, elapsed, color=P["rose"], marker="o", linewidth=2, label="总耗时 (秒)")
ax2.set_ylabel("总耗时 (秒)", color=P["rose"]); ax2.tick_params(axis="y", colors=P["rose"])
ax2.spines["right"].set_visible(True)
ax1.set_title("弱扩展 · 12 个月独立作业", color=P["ink"], fontweight="bold", pad=8)
save(fig, "fig_scaling")

# --- Figure 4: Fault demo timeline ---
fault = json.loads((EVI / "fault_demo.json").read_text())
fig, ax = plt.subplots(figsize=(6.0, 2.6))
events = []
for t in fault["timeline"]:
    if "submitted" in t["event"]: events.append((t["t"], "提交作业", P["blue"]))
    elif "killed" in t["event"]: events.append((t["t"], "kill worker1 DN", P["rose"]))
    elif "during outage" in t["event"]: events.append((t["t"], "dfsadmin: 1 DN", P["amber"]))
    elif "finished" in t["event"]: events.append((t["t"], t["event"].split("job ")[-1], P["teal"]))
    elif "restarted" in t["event"]: events.append((t["t"], "重启 worker1", P["olive"]))
    elif "healthy" in t["event"]: events.append((t["t"], "集群自愈 ✓", P["teal"]))
for t, name, color in events:
    ax.scatter(t, 0, s=140, color=color, zorder=3, edgecolor="white", linewidth=1.5)
    ax.annotate(name, (t, 0), xytext=(0, 12 if events.index((t, name, color)) % 2 == 0 else -18),
                textcoords="offset points", ha="center", fontsize=8, color=P["ink"])
ax.axhline(0, color=P["soft"], linewidth=1)
ax.set_xlim(-5, max(e[0] for e in events) + 10); ax.set_ylim(-1, 1.4)
ax.set_yticks([]); ax.set_xlabel("时间 (秒)", color=P["ink"])
ax.set_title("容错演示 · 单点故障下作业存活时间线", color=P["ink"], fontweight="bold", pad=8)
save(fig, "fig_fault")

# --- Figure 5: MR vs Spark ---
sp = json.loads((EVI / "spark.json").read_text())
mr = sp["mapreduce"]; sk = sp["spark"]
fig, ax = plt.subplots(figsize=(5.4, 3.2))
labels = ["MR 总墙钟", "MR 净耗时", "Spark 冷启动", "Spark 热跑", "Spark 计算"]
vals = [mr["total_elapsed_seconds"], mr["job_elapsed_seconds"], sk["cold_wall_seconds"], sk["warm_wall_seconds"], sk["warm_compute_seconds"]]
colors = [P["body"], P["blue"], P["amber"], P["teal"], P["rose"]]
bars = ax.bar(labels, vals, color=colors, edgecolor="white")
for b, v in zip(bars, vals): ax.text(b.get_x() + b.get_width()/2, v + 2, f"{v:.1f}s", ha="center", color=P["ink"], fontweight="bold")
ax.set_ylabel("秒", color=P["ink"])
ax.set_title("引擎对比 · MapReduce vs Spark 3.5.1 (2025-01 全月)", color=P["ink"], fontweight="bold", pad=8)
plt.setp(ax.get_xticklabels(), rotation=15, ha="right", color=P["ink"])
save(fig, "fig_engine")

# --- Figure 6: Forecast feature importance + neighbor ablation ---
fc = json.loads((EVI / "forecast.json").read_text())
imp = list(fc["weather_effect"]["feature_importance"].items())[:10]
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 3.2), gridspec_kw={"width_ratios": [2, 1]})
labels = [k for k, _ in imp][::-1]; values = [v for _, v in imp][::-1]
ax1.barh(labels, values, color=P["blue"], edgecolor="white")
ax1.set_xlabel("LightGBM 增益", color=P["ink"]); ax1.set_title("Top 10 特征重要性", color=P["ink"], fontweight="bold", pad=8)
ab = fc["metrics"]["neighbor_ablation"]
ax2.bar(["基础特征", "+邻域滞后"], [ab["rmse_baseline_features"], ab["rmse_with_neighbor_feature"]], color=[P["blue"], P["amber"]], edgecolor="white")
for i, v in enumerate([ab["rmse_baseline_features"], ab["rmse_with_neighbor_feature"]]):
    ax2.text(i, v + 0.05, f"{v:.1f}", ha="center", color=P["ink"], fontweight="bold")
ax2.set_ylim(18, 20); ax2.set_ylabel("RMSE")
ax2.set_title("邻域特征消融（无增益）", color=P["ink"], fontweight="bold", pad=8)
plt.tight_layout(); save(fig, "fig_forecast")

# --- Figure 7: Predicted vs actual scatter + q10/q90 band on top zone ---
curve = json.loads((ROOT / "data/results/forecast_curve.json").read_text())
xs = [np.datetime64(p[0]) for p in curve["points"]]; act = [p[1] for p in curve["points"]]
pred = [p[2] for p in curve["points"]]
has_q = len(curve["points"][0]) >= 5
fig, ax = plt.subplots(figsize=(6.4, 3.2))
ax.plot(xs, act, color=P["body"], linewidth=1, label="实际")
ax.plot(xs, pred, color=P["blue"], linewidth=1.2, label="预测")
if has_q:
    q10 = [p[3] for p in curve["points"]]; q90 = [p[4] for p in curve["points"]]
    ax.fill_between(xs, q10, q90, color=P["blue"], alpha=0.15, label="q10–q90 区间")
ax.legend(frameon=False)
ax.set_ylabel("逐小时出行量", color=P["ink"])
ax.set_title(f"榜首区域预测 · {curve['name']}（12 月前 4 天）", color=P["ink"], fontweight="bold", pad=8)
save(fig, "fig_curve")

# --- Figure 8: Data flow architecture (the SVG already in repo; PNG render is large) ---
print("done")
