"""Generate 3 cross-year charts for the report: pandemic timeline, yearly totals,
6-year x 12-month heatmap.
"""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

ROOT = Path(r"D:\项目\云计算")
OUT = Path(r"C:\Users\eugen\AppData\Local\Temp\geoflow_charts")
OUT.mkdir(parents=True, exist_ok=True)
P = {"ink": "#2C3A4F", "body": "#566373", "soft": "#9AA6B2",
     "blue": "#4C7DD8", "teal": "#3D8F88", "amber": "#C7923B",
     "rose": "#B25B6B", "olive": "#849360", "bg": "#F4F6F9"}
plt.rcParams.update({"font.family": ["Microsoft YaHei", "SimHei"],
                     "font.size": 10, "axes.facecolor": P["bg"],
                     "figure.facecolor": "white", "axes.edgecolor": P["soft"],
                     "axes.linewidth": 0.8, "axes.grid": True,
                     "grid.color": "white", "grid.linewidth": 1,
                     "axes.axisbelow": True, "xtick.color": P["body"],
                     "ytick.color": P["body"],
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.unicode_minus": False})


def main():
    d = json.loads((ROOT / "data/long/year_aggregate.json").read_text())
    monthly = d["monthly_totals"]
    years = sorted(set(r["year"] for r in monthly))
    months = list(range(1, 13))
    colors = {2019: P["blue"], 2020: P["rose"], 2021: P["amber"],
              2022: P["teal"], 2023: P["olive"], 2024: P["body"]}

    # 1. Pandemic timeline
    fig, ax = plt.subplots(figsize=(7.2, 3.3))
    for y in years:
        ys = [r["trips"] / 1e6 for r in monthly if r["year"] == y]
        ax.plot(months, ys, marker="o", color=colors[y], label=str(y),
                linewidth=1.5, markersize=5)
    ax.set_xlabel("月份", color=P["ink"]); ax.set_ylabel("有效出行 (百万)", color=P["ink"])
    ax.set_xticks(months)
    ax.set_title("NYC 黄车 6 年月度趋势 · 2020 疫情下凹", color=P["ink"], fontweight="bold", pad=8)
    ax.legend(frameon=False, ncol=3, loc="upper right")
    ax.annotate("2020-04 封城", xy=(4, 0.226), xytext=(5, 1.2),
                arrowprops=dict(arrowstyle="->", color=P["rose"]), color=P["rose"], fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "fig_pandemic_timeline.png", dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote fig_pandemic_timeline.png")

    # 2. Yearly totals bar
    fig, ax = plt.subplots(figsize=(5.5, 3.3))
    y_data = {r["year"]: r["trips"] / 1e6 for r in d["yearly_totals"]}
    yrs = list(y_data.keys()); vals = list(y_data.values())
    bars = ax.bar([str(y) for y in yrs], vals,
                  color=[P["blue"] if y == 2019 else P["rose"] if y == 2020 else P["teal"] for y in yrs],
                  edgecolor="white")
    for b, v in zip(bars, vals): ax.text(b.get_x() + b.get_width()/2, v + 1, f"{v:.0f}", ha="center", color=P["ink"], fontweight="bold")
    ax.set_ylabel("有效出行 (百万)", color=P["ink"])
    ax.set_title("NYC 黄车 6 年年度总量", color=P["ink"], fontweight="bold", pad=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig_yearly_totals.png", dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote fig_yearly_totals.png")

    # 3. Year x month heatmap
    fig, ax = plt.subplots(figsize=(6.5, 3.3))
    monthly_by_year = {r["year"]: {} for r in monthly}
    for r in monthly:
        monthly_by_year[r["year"]][r["month"]] = r["trips"]
    m_arr = np.array([[monthly_by_year[y][m] / 1e6 for m in months] for y in years])
    im = ax.imshow(m_arr, cmap="RdYlGn", aspect="auto", vmin=0, vmax=8)
    ax.set_xticks(range(12)); ax.set_xticklabels([f"{m}月" for m in months])
    ax.set_yticks(range(len(years))); ax.set_yticklabels(years)
    ax.set_title("NYC 黄车 6 年 × 12 月热力图 (百万)", color=P["ink"], fontweight="bold", pad=8)
    for i in range(len(years)):
        for j in range(12):
            v = m_arr[i, j]
            color = "white" if v < 4.0 else "#1a1a1a"
            ax.text(j, i, f"{v:.1f}", ha="center", va="center", color=color, fontsize=8)
    fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    fig.tight_layout()
    fig.savefig(OUT / "fig_year_month_heatmap.png", dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote fig_year_month_heatmap.png")


if __name__ == "__main__":
    main()
