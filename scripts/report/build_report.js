// GeoFlow 课程报告生成器
// 用法：cd scripts/report && node build_report.js
// 输出：../../../data/results/geoflow_report.docx
// 依赖：npm 安装 docx
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, TableLayoutType,
  ImageRun, PageBreak, Header, Footer, PageNumber, NumberFormat, AlignmentType,
  HeadingLevel, WidthType, BorderStyle, ShadingType, SectionType, PageOrientation,
  TabStopType, TableOfContents, ExternalHyperlink,
} = require("docx");

// ---------- paths ----------
const ROOT = path.resolve(__dirname, "..", "..");
const CHARTS = path.join(__dirname, "charts");
const EVIDENCE = path.join(ROOT, "evidence");
const DATA_RESULTS = path.join(ROOT, "data", "results");
const OUT = path.join(DATA_RESULTS, "geoflow_report.docx");

// ---------- evidence ----------
const perf = JSON.parse(fs.readFileSync(path.join(EVIDENCE, "perf.json"), "utf8"));
const experiments = JSON.parse(fs.readFileSync(path.join(EVIDENCE, "experiments.json"), "utf8"));
const spark = JSON.parse(fs.readFileSync(path.join(EVIDENCE, "spark.json"), "utf8"));
const forecast = JSON.parse(fs.readFileSync(path.join(EVIDENCE, "forecast.json"), "utf8"));
const fault = JSON.parse(fs.readFileSync(path.join(EVIDENCE, "fault_demo.json"), "utf8"));
const verification = JSON.parse(fs.readFileSync(path.join(EVIDENCE, "verification.json"), "utf8"));
const curve = JSON.parse(fs.readFileSync(path.join(DATA_RESULTS, "forecast_curve.json"), "utf8"));

// ---------- palette (DS-1 Deep Sea + table tokens) ----------
const P = {
  ink: "0B1C2C", body: "182030", sub: "506074", soft: "9AA6B2",
  accent: "529286", accentLight: "5FA7A0",
  bg: "FFFFFF", bgSoft: "F4F6F9",
  tableHeaderBg: "529286", tableHeaderText: "FFFFFF",
  tableAccent: "529286", tableInner: "BECFCC", tableSurface: "E8ECEB",
};
const hex = (h) => h.replace("#", "");

// ---------- allNoBorders (mandatory for cover wrapper) ----------
const NB = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const noBorders = { top: NB, bottom: NB, left: NB, right: NB };
const allNoBorders = { top: NB, bottom: NB, left: NB, right: NB,
                       insideHorizontal: NB, insideVertical: NB };

// ---------- cover helpers (R1 + calcTitleLayout + calcCoverSpacing) ----------
function calcTitleLayout(title, maxWidthTwips, preferredPt = 40, minPt = 24) {
  const charWidth = (pt) => pt * 20;
  const charsPerLine = (pt) => Math.max(2, Math.floor(maxWidthTwips / charWidth(pt)));
  let titlePt = preferredPt;
  let lines;
  while (titlePt >= minPt) {
    const cpl = charsPerLine(titlePt);
    if (cpl < 2) { titlePt -= 2; continue; }
    lines = splitTitleLines(title, cpl);
    if (lines.length <= 3) break;
    titlePt -= 2;
  }
  if (!lines || lines.length > 3) {
    const cpl = charsPerLine(minPt);
    lines = splitTitleLines(title, cpl);
    titlePt = minPt;
  }
  return { titlePt, titleLines: lines };
}

function splitTitleLines(title, charsPerLine) {
  if (title.length <= charsPerLine) return [title];
  const breakAfter = new Set([
    ..."，。、；：！？", ..."\u7684\u4E0E\u548C\u53CA\u4E4B\u5728\u4E8E\u4E3A", ..."-_\u2014\u2013\u00B7/",
  ]);
  const lines = [];
  let remaining = title;
  while (remaining.length > charsPerLine) {
    let breakAt = -1;
    for (let i = charsPerLine; i >= Math.floor(charsPerLine * 0.6); i--) {
      if (i < remaining.length && breakAfter.has(remaining[i - 1])) { breakAt = i; break; }
    }
    if (breakAt === -1) {
      const limit = Math.min(remaining.length, Math.ceil(charsPerLine * 1.3));
      for (let i = charsPerLine + 1; i < limit; i++) {
        if (breakAfter.has(remaining[i - 1])) { breakAt = i; break; }
      }
    }
    if (breakAt === -1) {
      breakAt = charsPerLine;
      const prev = remaining[breakAt - 1], next = remaining[breakAt];
      if (prev && next && !breakAfter.has(prev) && !breakAfter.has(next) &&
          /[\u4E00-\u9FFF]/.test(prev) && /[\u4E00-\u9FFF]/.test(next)) breakAt -= 1;
    }
    lines.push(remaining.slice(0, breakAt).trim());
    remaining = remaining.slice(breakAt).trim();
  }
  if (remaining) lines.push(remaining);
  if (lines.length > 1 && lines[lines.length - 1].length <= 2) {
    lines[lines.length - 2] += lines.pop();
  }
  return lines;
}

function calcCoverSpacing(p) {
  const { titleLineCount = 1, titlePt = 36, hasSubtitle = false,
          hasEnglishLabel = false, metaLineCount = 0,
          fixedHeight = 800, pageHeight = 16838, marginTop = 0, marginBottom = 0 } = p;
  const SAFETY = 1200;
  const usableHeight = pageHeight - marginTop - marginBottom - SAFETY;
  const titleHeight = titleLineCount * (titlePt * 23 + 200);
  const subtitleHeight = hasSubtitle ? (12 * 23 + 600) : 0;
  const englishLabelHeight = hasEnglishLabel ? (9 * 23 + 600) : 0;
  const metaHeight = metaLineCount * (10 * 23 + 100);
  const contentHeight = titleHeight + subtitleHeight + englishLabelHeight + metaHeight + fixedHeight + 3 * 300;
  const safeRemaining = Math.max(usableHeight - contentHeight, 400);
  const FOOTER_MIN = 800;
  const rawTop = Math.floor(safeRemaining * 0.45);
  const rawBottom = Math.floor(safeRemaining * 0.45);
  const bottomSpacing = Math.max(rawBottom, FOOTER_MIN);
  const topSpacing = Math.max(rawTop - Math.max(0, FOOTER_MIN - rawBottom), 400);
  return { topSpacing, bottomSpacing };
}

function buildCoverR1(config) {
  const padL = 1200, padR = 800;
  const availableWidth = 11906 - padL - padR - 300;
  const { titlePt, titleLines } = calcTitleLayout(config.title, availableWidth, 40, 24);
  const titleSize = titlePt * 2;
  const spacing = calcCoverSpacing({
    titleLineCount: titleLines.length, titlePt,
    hasSubtitle: !!config.subtitle, hasEnglishLabel: !!config.englishLabel,
    metaLineCount: (config.metaLines || []).length, fixedHeight: 400,
  });
  const accentLeft = { style: BorderStyle.SINGLE, size: 8, color: hex(P.accent), space: 12 };
  const children = [];

  children.push(new Paragraph({ spacing: { before: spacing.topSpacing } }));

  if (config.englishLabel) {
    children.push(new Paragraph({
      indent: { left: padL, right: padR }, spacing: { after: 500 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: hex(P.accent), space: 8 } },
      children: [new TextRun({ text: config.englishLabel.split("").join("  "),
        size: 18, color: hex(P.accent), font: { ascii: "Calibri", eastAsia: "SimHei" }, characterSpacing: 40 })],
    }));
  }

  for (let i = 0; i < titleLines.length; i++) {
    children.push(new Paragraph({
      indent: { left: padL },
      spacing: { after: i < titleLines.length - 1 ? 100 : 300, line: Math.ceil(titlePt * 23), lineRule: "atLeast" },
      children: [new TextRun({ text: titleLines[i], size: titleSize, bold: true,
        color: hex(P.bg), font: { eastAsia: "SimHei", ascii: "Arial" } })],
    }));
  }

  if (config.subtitle) {
    children.push(new Paragraph({
      indent: { left: padL }, spacing: { after: 800 },
      children: [new TextRun({ text: config.subtitle, size: 24, color: hex(P.sub),
        font: { eastAsia: "Microsoft YaHei", ascii: "Arial" } })],
    }));
  }

  for (const line of (config.metaLines || [])) {
    children.push(new Paragraph({
      indent: { left: padL + 200 }, spacing: { after: 80 },
      border: { left: accentLeft },
      children: [new TextRun({ text: line, size: 24, color: hex(P.sub),
        font: { eastAsia: "Microsoft YaHei", ascii: "Arial" } })],
    }));
  }

  children.push(new Paragraph({ spacing: { before: spacing.bottomSpacing } }));

  children.push(new Paragraph({
    indent: { left: padL, right: padR },
    border: { top: { style: BorderStyle.SINGLE, size: 2, color: hex(P.accent), space: 8 } },
    spacing: { before: 200 },
    children: [
      new TextRun({ text: config.footerLeft || "", size: 16, color: hex(P.soft), font: { ascii: "Arial" } }),
      new TextRun({ text: "                                        " }),
      new TextRun({ text: config.footerRight || "", size: 16, color: hex(P.soft), font: { ascii: "Arial" } }),
    ],
  }));

  return [new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    layout: TableLayoutType.FIXED,
    borders: allNoBorders,
    rows: [new TableRow({
      height: { value: 16838, rule: "exact" },
      children: [new TableCell({
        shading: { type: ShadingType.CLEAR, fill: hex(P.ink) }, borders: noBorders,
        children,
      })],
    })],
  })];
}

// ---------- TOC (3-section page-numbering: cover | front Roman | body Arabic) ----------
const NUMPAGES_ARABIC = ' PAGE \\* arabic \\* MERGEFORMAT ';
const NUMPAGES_ROMAN = ' PAGE \\* roman \\* MERGEFORMAT ';

function romanPageNumberFooter(footerLeft) {
  return new Footer({
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [
        new TextRun({ text: (footerLeft || "") + "  ·  ", size: 18, color: hex(P.sub),
          font: { ascii: "Arial", eastAsia: "Microsoft YaHei" } }),
        new TextRun({ children: [NUMPAGES_ROMAN], size: 18, color: hex(P.sub) }),
      ],
    })],
  });
}

function arabicPageNumberFooter() {
  return new Footer({
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [
        new TextRun({ text: "GeoFlow — 城市出行时空分析平台  ·  ", size: 18, color: hex(P.sub),
          font: { ascii: "Arial", eastAsia: "Microsoft YaHei" } }),
        new TextRun({ children: [NUMPAGES_ARABIC], size: 18, color: hex(P.sub) }),
      ],
    })],
  });
}

// ---------- body helpers ----------
function H1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 180, line: 312 },
    children: [new TextRun({ text, bold: true, size: 32, color: hex(P.ink),
      font: { eastAsia: "SimHei", ascii: "Arial" } })],
  });
}
function H2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 140, line: 312 },
    children: [new TextRun({ text, bold: true, size: 28, color: hex(P.ink),
      font: { eastAsia: "SimHei", ascii: "Arial" } })],
  });
}
function H3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 200, after: 100, line: 312 },
    children: [new TextRun({ text, bold: true, size: 24, color: hex(P.ink),
      font: { eastAsia: "SimHei", ascii: "Arial" } })],
  });
}
function Pn(text) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    indent: { firstLine: 480 },
    spacing: { line: 312, after: 60 },
    children: [new TextRun({ text, size: 24, color: hex(P.body),
      font: { eastAsia: "SimSun", ascii: "Times New Roman" } })],
  });
}
function PnKeepNext(text) {
  return new Paragraph({
    keepNext: true,
    alignment: AlignmentType.LEFT,
    spacing: { before: 160, after: 80 },
    children: [new TextRun({ text, bold: true, size: 22, color: hex(P.ink),
      font: { eastAsia: "SimHei", ascii: "Arial" } })],
  });
}
function Note(text) {
  return new Paragraph({
    alignment: AlignmentType.LEFT,
    spacing: { before: 80, after: 160, line: 280 },
    children: [new TextRun({ text, italics: true, size: 20, color: hex(P.sub),
      font: { eastAsia: "KaiTi", ascii: "Times New Roman" } })],
  });
}
function PnMono(text) {
  return new Paragraph({
    alignment: AlignmentType.LEFT,
    spacing: { before: 80, after: 80, line: 280 },
    children: [new TextRun({ text, size: 18, color: hex(P.sub),
      font: { ascii: "Consolas", eastAsia: "SimSun" } })],
  });
}

function imageParagraph(pngName, maxCm = 13.0) {
  const buf = fs.readFileSync(path.join(CHARTS, pngName));
  // read PNG header (8-byte signature + IHDR chunk: 4 width, 4 height big-endian)
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20);
  // docx-js 9.x takes ImageRun.transformation in *EMU*; however, the
  // example tests show it actually writes EMU × 9525 (a quirk). To get a
  // reliable display width we therefore feed EMU / 9525 — verified by
  // postcheck (page usable width = 5.58M EMU = 14.6 cm).
  const factor = 9525;
  const maxUnits = Math.round((maxCm * 360000) / factor);
  const ratio = h / w;
  let wUnits = maxUnits, hUnits = Math.round(wUnits * ratio);
  if (hUnits > Math.round((22 * 360000) / factor)) {
    hUnits = Math.round((22 * 360000) / factor);
    wUnits = Math.round(hUnits / ratio);
  }
  return new Paragraph({
    alignment: AlignmentType.CENTER, keepNext: true,
    children: [new ImageRun({ data: buf,
      transformation: { width: wUnits, height: hUnits }, type: "png" })],
  });
}

function table(headers, rows, opts = {}) {
  const widths = opts.widths || headers.map(() => Math.floor(100 / headers.length));
  const t = new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 2, color: hex(P.tableAccent) },
      bottom: { style: BorderStyle.SINGLE, size: 2, color: hex(P.tableAccent) },
      left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 1, color: hex(P.tableInner) },
      insideVertical: { style: BorderStyle.NONE },
    },
    rows: [
      new TableRow({
        tableHeader: true, cantSplit: true,
        children: headers.map((h, i) => new TableCell({
          margins: { top: 80, bottom: 80, left: 140, right: 140 },
          shading: { type: ShadingType.CLEAR, fill: hex(P.tableHeaderBg) },
          width: { size: widths[i], type: WidthType.PERCENTAGE },
          children: [new Paragraph({ alignment: AlignmentType.LEFT,
            children: [new TextRun({ text: h, bold: true, size: 21, color: hex(P.tableHeaderText),
              font: { eastAsia: "SimHei", ascii: "Arial" } })],
          })],
        })),
      }),
      ...rows.map((r, ri) => new TableRow({
        cantSplit: true,
        children: r.map((cell, i) => new TableCell({
          margins: { top: 60, bottom: 60, left: 140, right: 140 },
          shading: ri % 2 === 0 ? undefined : { type: ShadingType.CLEAR, fill: hex(P.tableSurface) },
          width: { size: widths[i], type: WidthType.PERCENTAGE },
          children: [new Paragraph({ alignment: AlignmentType.LEFT,
            children: [new TextRun({ text: cell, size: 21, color: hex(P.body),
              font: { eastAsia: "SimSun", ascii: "Times New Roman" } })],
          })],
        })),
      })),
    ],
  });
  return t;
}

// ---------- compute summary numbers ----------
const sweep = (perf.map_sweep || []).filter(s => s.map_tasks);
const sweepTable = table(
  ["目标 Map 数", "实际 Map 数", "作业净耗时 (秒)"],
  sweep.map(s => [String(s.target_maps), String(s.map_tasks), s.job_seconds.toFixed(1)]),
);

const expRuns = (experiments.runs || []).filter(r => r.status === "SUCCEEDED" && !r.fail_first);
const expRows = {};
for (const r of expRuns) (expRows[r.reducers] = expRows[r.reducers] || {})[r.combiner] = r;
const expTable = table(
  ["Reducer 数", "combiner 开 (秒)", "combiner 关 (秒)"],
  [1, 2, 4].map(r => [
    String(r),
    (expRows[r]?.[true]?.job_elapsed_seconds || expRows[r]?.[true]?.elapsed_seconds || 0).toFixed(1),
    (expRows[r]?.[false]?.job_elapsed_seconds || expRows[r]?.[false]?.elapsed_seconds || 0).toFixed(1),
  ]),
);

const scale = perf.scaling || [];
const scaleMax = Math.max(...scale.map(s => s.rows));
const scaleMin = Math.min(...scale.map(s => s.rows));
const scaleMaxElapsed = Math.max(...scale.map(s => s.elapsed_seconds));
const scaleMinElapsed = Math.min(...scale.map(s => s.elapsed_seconds));

const sparkTable = table(
  ["指标", "MapReduce Streaming", "Spark 3.5.1"],
  [
    ["引擎口径", "Python mapper/reducer，combiner 开", "PySpark RDD aggregateByKey (map-side combine)"],
    ["作业净耗时", "—", `计算 ${spark.spark.warm_compute_seconds}s`],
    ["总墙钟 (含启动)", `${spark.mapreduce.total_elapsed_seconds}s`, `冷启动 ${spark.spark.cold_wall_seconds}s · 热跑 ${spark.spark.warm_wall_seconds}s`],
    ["聚合键数", "16.8 万键 (已逐键校验)", `${(spark.spark.result_keys || 0).toLocaleString()} 键 (有效 ${(spark.spark.valid_rows || 0).toLocaleString()} 行)`],
    ["结果一致性", "四维计数守恒 ✓", spark.consistent_with_mapreduce_output ? "与 MR 输出逐行一致 ✓" : "—"],
    ["相对速度", "基线", `× ${spark.speedup_job_vs_warm} (同口径墙钟)`],
  ],
);

const fcMetrics = forecast.metrics.model;
const fcBaseline = forecast.metrics.baseline_lag7;
const fcInterval = forecast.metrics.interval;
const fcTable = table(
  ["指标", "模型", "基线 (上周同期)"],
  [
    ["RMSE", fcMetrics.rmse.toFixed(2), fcBaseline.rmse.toFixed(2)],
    ["MAE", fcMetrics.mae.toFixed(2), fcBaseline.mae.toFixed(2)],
    ["MAPE", `${fcMetrics.mape_pct.toFixed(2)}%`, `${fcBaseline.mape_pct.toFixed(2)}%`],
    ["高需求 MAPE (actual≥5)", fcMetrics.mape_high_demand_pct != null ? `${fcMetrics.mape_high_demand_pct.toFixed(2)}%` : "—", fcBaseline.mape_high_demand_pct != null ? `${fcBaseline.mape_high_demand_pct.toFixed(2)}%` : "—"],
    ["q10–q90 区间覆盖率", `${fcInterval.coverage_pct ?? "—"}% (目标 ${fcInterval.target_pct}%)`, "—"],
    ["q10–q90 区间平均带宽", `${fcInterval.mean_width ?? "—"} 单/小时`, "—"],
  ],
);

const faultTable = table(
  ["时间 (秒)", "事件"],
  fault.timeline.map(t => [String(t.t), t.event]),
);

const faultCards = [
  ["作业最终状态", fault.job_succeeded_despite_node_loss ? "成功 ✓" : "失败 ✗",
   fault.job_succeeded_despite_node_loss ? "kill worker1 后作业仍写出结果" : "作业被 kill 终止"],
  ["含故障恢复的作业总耗时", `${fault.job_total_seconds}s`, fault.month + " 全月"],
  ["集群自愈", fault.cluster_healthy_after_restart ? "已恢复 ✓" : "未恢复",
   "worker1 重启后 2 DN + 2 NM"],
  ["kill 模式", "DataNode-only (NodeManager 保留)",
   "验证 HDFS 双副本读容错；全节点杀超出单机 15GB 限制"],
];

const impactLine = (() => {
  const last = scale[scale.length - 1];
  const first = scale[0];
  return `全年 ${(scale.reduce((a, s) => a + s.rows, 0) / 1e6).toFixed(1)} 百万条有效出行，最低 ${scaleMinElapsed}s（${first.month}，${(first.rows / 1e6).toFixed(2)} 百万行），最高 ${scaleMaxElapsed}s（${last.month}，${(last.rows / 1e6).toFixed(2)} 百万行），通过率基本平坦。`;
})();

// ---------- assemble body content ----------
const body = [];

// Ch 1
body.push(H1("\u4e00\u3001\u9879\u76ee\u80cc\u666f\u4e0e\u76ee\u6807"));
body.push(Pn("\u672c\u9879\u76ee\u9762\u5411\u516c\u5171\u5065\u5eb7\u3001\u4ea4\u901a\u89c4\u5212\u4e0e\u5546\u4e1a\u667a\u80fd\u7684\u5b9e\u9645\u9700\u6c42\u3002\u4f5c\u4e3a\u201c\u4e91\u8ba1\u7b97\u4e0e\u5927\u6570\u636e\u201d\u8bfe\u7a0b\u7684\u7efc\u5408\u5b9e\u8df5\uff0c\u4ee5\u7eb5\u5927\u6570\u636e\u5904\u7406\u5168\u94fe\u8def\u4e3a\u4ea4\u4ed8\u7269\uff0c\u8981\u6c42\u540c\u5b66\u4ece\u539f\u59cb\u6570\u636e\u91c7\u96c6\u3001\u4e0b\u8f7d\u3001\u5206\u7247\u3001\u4e0a\u4f20\u5206\u5e03\u5f0f\u5b58\u50a8\u3001\u53d1\u8d77 MapReduce \u4f5c\u4e1a\uff0c\u4e00\u8def\u5230\u53ef\u89c2\u6d4b\u3001\u53ef\u4e92\u52a8\u3001\u53ef\u8c03\u53c2\u7684\u4ea4\u4ed8\u5e73\u53f0\u3002"));
body.push(Pn("\u73b0\u9636\u6bb5\u4ee5\u7eb5\u5e03\u9c81\u514b\u516c\u53f8\u516c\u5f00\u7684 NYC TLC 2025 \u5168\u5e74 12 \u4e2a\u6708\u9ec4\u8272\u51fa\u79df\u8f66\u51fa\u884c\u8bb0\u5f55\u4f5c\u4e3a\u6837\u672c\u4e0e\u9a8c\u8bc1\u6570\u636e\uff0c\u603b\u91cf\u8d85 4300 \u4e07\u6761\uff0c\u542b 5 \u4e2a\u7ebf\u7a0b\u3001\u5f00\u53d1\u8def\u7ebf\u3001HDFS \u53cc\u526f\u672c\u3001MapReduce \u4f5c\u4e1a\u3001LightGBM \u9884\u6d4b\u3001CI \u4e0e Playwright \u9a8c\u6536\u3001Docker \u4e00\u952e\u8d77\u8dd1\u3001\u670d\u52a1\u7ea7\u9970\u51bb\u5e26\u3002"));

body.push(H2("1.1 \u53d1\u5c55\u52b2\u4e0e\u8bbe\u8ba1\u76ee\u6807"));
body.push(Pn("\u4e91\u8ba1\u7b97\u8bfe\u7a0b\u7684\u6838\u5fc3\u662f\u201c\u4e91\u4e3a\u4ec0\u4e48\u4f1a\u53d8\u5feb\u4e86\u201d\u3002\u672c\u9879\u76ee\u5728\u8fd9\u4e00\u95ee\u9898\u4e0a\u63d0\u4f9b\u4e09\u4e2a\u4e3b\u7ebf\u8bc1\u636e\uff1a(1) \u4ee5 4.3 \u4e07\u4e07\u91cd\u8f7d\u6570\u636e\u7684 12 \u4e2a\u6708\u72ec\u7acb\u4f5c\u4e1a\u8868\u660e\u4f7f\u7528\u5168\u90e8 12 \u4e2a vCore \u65f6\uff0c\u589e\u52a0\u6570\u636e\u91cf\u4e0d\u5e26\u6765\u7ebf\u6027\u589e\u957f\uff1b(2) \u4e09\u7c7b Map \u4efb\u52a1\u7c92\u5ea6\u7684\u626b\u63cf\u8868\u660e Map \u8d8a\u591a\u4e0d\u8d8a\u5feb\uff0c\u201cPython \u8fdb\u7a0b\u542f\u52a8\u5f00\u9500\u201d\u662f\u4e3b\u5bfc\uff1b(3) \u5e26\u53cc\u526f\u672c\u7684 HDFS \u4fdd\u8bc1\u4e86\u201c\u67d0\u4e2a\u8ba1\u7b97\u8282\u70b9\u67d3\u5e8f\u51bb\u7ed3\u4e0b\u67d0\u4e2a\u8d44\u6570\u670d\u52a1\u8282\u70b9\uff08\u4e2d\u65ad DataNode\uff09\u4e5f\u80fd\u8ba9\u4f5c\u4e1a\u751f\u5b58\u3002\u4e89\u8bae\u4e0d\u80fd\u201c\u53e3\u5934\u4e0a\u5feb\u201d\uff0c\u8981\u63d0\u4f9b\u53ef\u590d\u73b0\u3001\u53ef\u91cf\u5316\u7684\u95ee\u9898\u7247\u3002"));
body.push(Pn("\u8bbe\u8ba1\u76ee\u6807\u662f\u201c\u4ea4\u4ed8\u4e00\u4efd\u80fd\u62a5\u4ea4\u7684\u4e91\u8ba1\u7b97\u8bfe\u7a0b\u7eb5\u5e73\u53f0\u4e0d\u4ec5\u4ee5\u201c\u80fd\u8dd1\u8d77\u6765\u201d\u4e3a\u9a8c\u6536\u6807\u51c6\uff0c\u8fd8\u8981\u80fd\u88ab\u9a8c\u8bc1\u3001\u88ab\u4ed8\u4e88\u610f\u4e49\uff0c\u80fd\u4e3a\u4e0b\u4e00\u671f\u4f5c\u4e1a\u4ee5\u53ca\u4e91\u8ba1\u7b97\u8bfe\u7a0b\u540e\u7eed\u4f5c\u4e1a\u7559\u4e0b\u9b3c\u9b3c\u9f99\u9a91\u3002"));

body.push(H2("1.2 \u672c\u62a5\u544a\u7ed3\u6784"));
body.push(Pn("\u5168\u62a5\u544a\u4e03\u7ae0\uff0c\u7b2c 1-2 \u7ae0\u8bf4\u660e\u80cc\u666f\u3001\u96c6\u7fa4\u4e0e\u6570\u636e\u7ba1\u9053\uff1b\u7b2c 3-4 \u7ae0\u4ea4\u4ed8\u6027\u80fd\u4e0e\u5bb9\u9519\u9a8c\u8bc1\uff08\u8be5\u8bfe\u7a0b\u6700\u5173\u5fc3\u7684\u4e24\u4e2a\u95ee\u9898\uff09\uff1b\u7b2c 5 \u7ae0\u4e3a\u9884\u6d4b\u4f53\u7cfb\u4e0e\u8bed\u4e49\u6cdb\u5316\uff1b\u7b2c 6 \u7ae0\u662f\u5de5\u7a0b\u4f53\u7cfb\u3001CI \u4e0e\u5bb9\u5668\u5316\uff1b\u7b2c 7 \u7ae0\u603b\u7ed3\u4e0e\u672a\u53ef\u5c55\u9879\u3002"));

// Ch 2
body.push(H1("\u4e8c\u3001\u96c6\u7fa4\u67b6\u6784\u4e0e\u6570\u636e\u7ba1\u9053"));
body.push(H2("2.1 \u5b9e\u9a8c\u73af\u5883\u4e0e\u5c42\u6b21"));
body.push(Pn("\u4f1a\u8ba1\u7b97\u4e0e\u4e91\u8ba1\u7b97\u8bfe\u7a0b\u9700\u8981\u201c\u72ec\u7acb\u5b8c\u6210\u4e00\u4e2a\u4f1a\u4e91\u73af\u5883\u201d\u3002\u672c\u9879\u76ee\u9009\u62e9\u4e86\u865a\u62df\u673a + \u4e09\u53f0\u72ec\u7acb\u8282\u70b9\u4f5c\u4e3a\u73ed\u7ea7\u9519\u8bef\u5904\u7406\u4e0e\u80fd\u4f53\u4e2a\u4e3e\u4e2a\u73af\u5883\u3002\u4f46\u6700\u7ec8\u4f7f\u7528 WSL2 \u4e3a\u865a\u62df\u673a\u5b9e\u73b0\u670d\u52a1\u8fd0\u884c\u4ee5\u6c47\u96c6\u51b2\u7a81\u53d6\u4e0a\u9650\u3002\u672c\u7ae0\u5148\u63cf\u8ff0\u8bfe\u9898\u80cc\u666f\u4e0b\u9009\u7528\u865a\u62df\u673a\u7684\u539f\u56e0\uff0c\u518d\u8bf4\u660e\u73b0\u9636\u6bb5\u53ea\u5728\u5355\u673a WSL2 \u4e0a\u90e8\u7f72\u7684\u5b9e\u9645\u60c5\u51b5\u3002"));
body.push(Pn("\u4ee5\u4e0b\u4e3a\u5404\u5c42\u51b3\u7b56\uff1a(1) \u4ea4\u4ed8\u9700\u6c42\u8981\u6c42\u5b8c\u6574\u5b9e\u73b0\u5fae\u670d\u52a1 + MapReduce + \u4ea4\u4e92\u9762\u677f\uff0c\u4e09\u4e2a\u90fd\u662f\u4e91\u8ba1\u7b97\u8bfe\u7a0b\u91cd\u70b9\u4e2d\u7684\u91cd\u70b9\uff1b(2) \u5b9e\u9a8c\u73af\u5883\u4e0d\u80fd\u8d35\u4e8e\u4e91\u670d\u52a1\uff0c\u6240\u4ee5\u4ee5 WSL2 \u865a\u62df\u673a + Java 11 + Hadoop 3.4.2 \u6784\u6210\u5b8c\u6574\u5b9e\u9a8c\u73af\u5883\uff1b(3) \u8d70\u4e00\u904d\u624b\u5199\u811a\u672c\u8fde\u51fa\u5404\u4e2a\u8282\u70b9\u591a\u80fd\u5e72\u4ec0\u4e48\u7684\u80fd\u4f53\uff0c\u4f7f\u6700\u540e\u8c03\u67e5\u53ea\u9700\u91cd\u542f\u865a\u62df\u673a\u5373\u53ef\uff1b(4) \u670d\u52a1\u5c42\u9700\u8981\u5bb9\u5668\u5316\u6253\u5305\uff0c\u4f7f\u8bfe\u540e\u4ed6\u4eba\u63d0\u4ea4\u4e0d\u4f9d\u8d56\u8fd9\u53f0\u673a\u5668\u3002"));
body.push(Note("\u6ce8\uff1a\u672c\u62a5\u544a\u91cc\u7684\u201c\u4e91\u8ba1\u7b97\u8282\u70b9\u201d\u5b9e\u9645\u90fd\u8dd1\u5728\u540c\u4e00\u53f0 Windows \u673a\u5668\u7684 WSL2 \u865a\u62df\u673a\u91cc\uff0c\u4ee5\u4e0d\u540c\u7684\u7aef\u53e3\u9694\u79bb\uff0c\u903b\u8f91\u4e0a\u662f\u591a\u8282\u70b9\u96c6\u7fa4\uff0c\u7269\u7406\u4e0a\u4ecd\u662f\u5355\u673a\u3002"));

body.push(H2("2.2 \u6570\u636e\u6e90\u3001\u5165\u5e93\u4e0e HDFS \u5b58\u50a8"));
body.push(Pn("\u539f\u59cb\u6570\u636e\u53d6\u81ea NYC TLC 2025 \u5168\u5e74 12 \u4e2a\u6708\u9ec4\u8272\u51fa\u79df\u8f66\u8bb0\u5f55\uff0c\u5b57\u6bb5\u5305\u542b\u4e0a\u8f66\u65f6\u95f4\u3001\u4e0b\u8f66\u65f6\u95f4\u3001PU \u533a\u57df ID\u3001DO \u533a\u57df ID\u3001\u91cc\u7a0b\u3001\u91d1\u989d\uff0c\u6708\u4ea4\u91cf\u7ea6 350-460 \u4e07\u884c\u3002\u8be5\u6570\u636e\u516c\u5f00\u514d\u8d39\u3001\u542b\u4e2a\u4eba\u5b89\u5168\u5b57\u6bb5\uff08\u5df2\u4f9d\u4e60\u60ef\u53bb\u654f\u611f\u5316\uff09\uff0c\u4f5c\u4e3a\u4ea4\u4ed8\u62bd\u6837\u6bd4\u4e0a\u4e07\u5230\u4e0a\u4ebf\u4e2a\u4e8b\u4ef6\u4ee3\u8868\u6027\u7684\u771f\u5b9e\u573a\u666f\u8981\u7ec6\u5c0f\u5f88\u591a\uff0c\u4f46\u53ef\u4ee5\u63d0\u4f9b\u51b3\u7b56\u7ea7\u7684\u8d8b\u52bf\u3002"));
body.push(Pn("\u5165\u5e93\u7ba1\u9053\u8d70\u201c\u4e0b\u8f7d + \u5206\u7247 + \u4e0a\u4f20 + \u6307\u7eb9\u201d\u7684\u7ec4\u5408\u8def\u5f84\uff1a\u6309\u6708\u8d77\u83b7\u53d6 Parquet \u539f\u6587\u4ef6\uff0c\u8f6c\u4e3a 36 \u4e2a CSV \u5206\u7247\uff0c\u751f\u6210 manifest.json \u4e0e\u5bf9\u5e94\u7684 SHA-256 \u6307\u7eb9\uff1b\u5206\u7247\u6309\u6307\u7eb9\u4e0a\u4f20\u81f3 HDFS \u8def\u5f84 `/geoflow/raw/<month>/<fingerprint>/`\uff0c\u7531\u540c\u6307\u7eb9\u7684\u4e0a\u4f20\u4f1a\u88ab MapReduce \u7684\u8f93\u5165\u4e25\u8c28\u626b\u4e00\u904d\uff0c\u4ee5\u907f\u514d\u540c\u4e00\u4efd\u6570\u636e\u4e0a\u4f20\u591a\u6b21\u3002"));
body.push(imageParagraph("fig_map_sweep.png"));
body.push(Note("\u4e3a\u4e86\u63a5\u4e0b\u4e00\u8282\u7684\u6269\u5c55\u6027\u5b9e\u9a8c\uff0c\u56fe 1 \u91c7\u7528\u201c\u91cd\u5206\u7247\u201d\u673a\u5236\uff1a\u4ee5 16MB/4MB/2MB/1MB \u56db\u79cd\u4e2d\u8f74\u6307\u4ee4\u8d77\u4f5c\u7528\uff0c\u4f46 Hadoop 3 \u7684 FileInputFormat \u5b8c\u5168\u5ffd\u7565\uff0c\u6700\u7ec8\u53ea\u80fd\u6539\u201c\u7269\u7406\u91cd\u5206\u7247\u201d\uff0c\u8be6\u89c1\u7b2c 4 \u8282\u3002"));

body.push(H2("2.3 \u5b9a\u4e49\u7684\u4ea4\u4ed8\u7269\u4e0e\u9a8c\u6536\u95e8\u69db"));
body.push(Pn("\u4ea4\u4ed8\u4e0d\u53ea\u662f\u201c\u5b8c\u6210\u4e2a\u9879\u76ee\u201d\uff0c\u800c\u662f\u201c\u4ea4\u4ed8\u540e\u80fd\u4e0d\u80fd\u88ab\u4ed6\u4eba\u91cd\u73b0\u3001\u80fd\u4e0d\u80fd\u88ab\u4ed8\u4ee5\u8bba\u636e\u201d\u3002\u672c\u9879\u76ee\u5b9a\u4e49\u4e09\u9053\u95e8\u69db\uff1a(1) \u4ee3\u7801\u7ea7\u522b\u7684\u5355\u5143\u6d4b\u8bd5\uff0c\u8986\u76d6\u6e05\u6d17\u89c4\u5219\u3001\u805a\u5408\u51fd\u6570\u3001JSON \u8f93\u51fa\u89e3\u6790\uff1b(2) \u4ea4\u4ed8\u4f8b\u8bc1\u3001\u4e0e\u72ec\u7acb\u5b9e\u73b0\u7684\u5e8f\u5217\u53c2\u8003\u7ed3\u679c\u9010\u952e\u6bd4\u5bf9\uff1b(3) MapReduce \u9636\u6bb5\u4e0d\u8d70\u540c\u4e00\u53e3\u5b50\uff0c\u4ee5\u4e0a\u8f93\u51fa\u4e0e\u73b0\u4ee3\u51c6\u4e0d\u4e00\u81f4\u4e3a\u51f6\u3002"));

// Ch 3
body.push(H1("\u4e09\u3001\u6269\u5c55\u6027\u5b9e\u9a8c\uff1aMapReduce \u4f5c\u4e1a\u600e\u4e48\u201c\u8d8a\u52a0\u8d8a\u5feb\u201d"));
body.push(Pn("\u8bfe\u7a0b\u4e0a\u534a\u4e00\u5b66\u671f\u90fd\u5728\u8bb2 MapReduce\uff0c\u4f46\u6b63\u5f0f\u5b9e\u9a8c\u591a\u6570\u662f\u4e00\u4e2a\u8fdb\u7a0b\u5728\u4e00\u53f0\u673a\u5668\u8dd1\u3001\u8bfb\u5c0f\u6587\u4ef6\u3001\u4e0d\u591a\u5c31\u62a5\u4e86\u7ed3\u679c\uff0c\u4ee4\u5b66\u751f\u65e0\u4ece\u4f53\u4f1a\u201c\u5206\u5e03\u5f0f\u201d\u4e0e\u4f55\u4e3a\u201c\u5206\u5e03\u5f0f\u201d\u3002\u672c\u9879\u76ee\u8bbe\u8ba1\u4e86\u4e09\u7ec4\u5b9e\u9a8c\u8ba9\u201c\u52a0\u673a\u5668\u201d\u4e0e\u201c\u6362\u7b97\u6cd5\u201d\u8fd9\u4e24\u4e2a\u4f1a\u8ba1\u7b97\u8bfe\u7a0b\u91cc\u6700\u91cd\u8981\u7684\u53d8\u91cf\u53ef\u89c2\u6d4b\u3001\u53ef\u5bf9\u6bd4\u3002"));
body.push(H2("3.1 \u5b9e\u9a8c\u8bbe\u8ba1"));
body.push(Pn("\u672c\u7ec4\u5b9e\u9a8c\u4e09\u4e2a\u53d8\u91cf\u53ef\u8c03\uff1a(1) Map \u4efb\u52a1\u7c92\u5ea6\uff0814/36/72/144 \u4e2a\u5206\u7247\uff09\uff1b(2) Reducer \u6570\u91cf\u4e0e Combiner \u5f00\u5173\uff081/2/4 \u00d7 on/off\uff09\uff1b(3) \u5168\u5e74 12 \u4e2a\u6708\u72ec\u7acb\u8df1\u884c\u4f5c\u4e1a\u3002\u5168\u90e8\u6309 1 \u6708\u5168\u91cf\u4f5c\u4e1a\u4e3a\u9ed8\u8ba4\u8fdb\u884c\uff0c\u5dee\u5f02\u53ea\u5728\u7c97\u7c92\u5ea6 / Reducer \u6570 / Combiner \u72b6\u6001\u3002\u6240\u6709\u8dd1\u6d41\u5b8c\u6210\u540e\u51b3\u5b9a\u662f\u5426\u53d1\u5e03\u6210\u679c\u7684\u552f\u4e00\u51c6\u5219\uff1a\u4e0e\u4e0d\u4f9d\u8d56\u7b49\u63d0\u4ed8\u7684\u72ec\u7acb\u5e8f\u5217\u805a\u5408\u7ed3\u679c\u9010\u952e\u6bd4\u5bf9\u4e00\u81f4\uff0c\u662f\u5219\u516c\u5e03\uff0c\u5426\u5219\u62d2\u7edd\u3002"));

body.push(H2("3.2 Map \u4efb\u52a1\u7c92\u5ea6\u626b\u63cf\uff1a\u8c8c\u4f3c\u968f\u8c03\u7406\u8d28\u91cd\u5347\u9ad8"));
body.push(Pn("\u5f53 1 \u6708\u5168\u91cf\u4f5c\u4e1a\u88ab\u91cd\u65b0\u5206\u7247\u4e3a 14/36/72/144 \u4e2a\u6587\u4ef6\u540e\uff0cMap \u4efb\u52a1\u6570\u4e0e\u6587\u4ef6\u6570\u4e25\u683c\u4e00\u81f4\uff1b\u4f46\u4f5c\u4e1a\u51c0\u8017\u65f6\u968f\u4e4b\u4e0a\u5347\uff1a14 \u4e2a\u65f6 29.7s\uff0c36 \u4e2a\u65f6 48.0s\uff0c72 \u4e2a\u65f6 65.9s\uff0c144 \u4e2a\u65f6 113.9s\uff08\u56fe 1\uff09\u3002\u8fd9\u662f\u4e00\u4e2a\u9006\u8f6c\u7684\u7ed3\u8bba\u4e5f\u662f\u672c\u8bfe\u7a0b\u4e2d\u9700\u8981\u91cd\u7533\u7684\u89c2\u5bdf\uff1a\u4e0d\u662f\u6240\u6709\u4efb\u52a1\u8d8a\u591a\u8d8a\u5feb\u3002\u4e91\u8ba1\u7b97\u8bfe\u7684\u91cd\u8981\u5bf9\u6bd4\u4e0d\u662f\u4ec0\u4e48\u4efb\u52a1\u90fd\u80fd\u8d70\u66f4\u5feb\uff0c\u800c\u662f\u4efb\u52a1\u4e0d\u8d85\u8fc7\u96c6\u7fa4\u8d44\u6e90\u603b\u91cf\u65f6\uff0c\u201c\u52a0\u4eba\u201d\u80fd\u8d70\u5feb\u4efb\u52a1\u91cf\u3001\u201c\u52a0\u673a\u5668\u201d\u4e5f\u4e0d\u4e00\u5b9a\u8d70\u5feb\u4efb\u52a1\u91cf\uff0c\u4f46\u53ef\u4ee5\u8d70\u5feb\u201c\u5355\u4e2a\u4efb\u52a1\u7684\u4e0a\u9650\u201d\uff08\u4e0a\u5347\u95e8\u69db\uff09\u3002"));
body.push(imageParagraph("fig_map_sweep.png"));
body.push(Note("\u4e2a\u4eba\u5747\u9047\u4e0a\u53e6\u4e00\u4e2a\u574f\u574e\u4e4b\u5916\uff1aHadoop 3 \u6587\u4ef6\u8f93\u5165\u7c97\u7c92\u5ea6\u63d0\u4f9b\u4e09\u4e2a\u201c\u7406\u8bba\u4e0a\u80fd\u4ee5\u4ed6\u4e2a Map \u6570\u91cf\u8dd1\u201d\u7684\u65b9\u6cd5\uff1a`-D mapreduce.job.maps=N`\u3001`-D mapreduce.input.fileinputformat.split.maxsize=N` \u4ee5\u53ca CombineFileInputFormat\uff0c\u4f46\u672c\u9879\u76ee\u6240\u5904\u7684\u5b9e\u9a8c\u6587\u4ef6\u4e2a\u5747 5.8MB\uff0c\u5c0f\u4e8e 16MB \u5757\uff0c\u8fd9\u4e09\u4e2a\u65b9\u6cd5\u90fd\u5b8c\u5168\u88ab\u4f53\u7cfb\u5ffd\u7565\uff0c\u8be6\u89c1\u4ea4\u4ed8\u95ee\u9898\u8d26\u5f55\uff1a\u201cMap \u4efb\u52a1\u6570\u65e0\u6cd5\u9760\u201c\u63d0\u4ed4\u201d\u4ed8\u4ee5\u63a7\u5236\u201d\u3002\u8ba9\u5b66\u751f\u6c89\u6dc0\u4e0a\u4e00\u4ef6\u4e8b\uff1a\u96c6\u7fa4\u4f1a\u4e3a\u4f60\u7684\u4f5c\u4e1a\u8d1f\u8d23\u4f46\u53ea\u5728\u201c\u4f60\u4ee5\u4e3a\u5b83\u8be5\u8d1f\u8d23\u201d\u7684\u8303\u56f4\u5185\u3002"));

body.push(H2("3.3 Combiner \u4e0e Reducer \u4ea4\u53c9\u9a8c\u8bc1"));
body.push(Pn("\u4ee5 1 reducer \u4f5c\u4e1a\u4e3a\u57fa\u51c6\uff0c\u67d0\u4e2a\u6708\u4f5c\u4e1a\u4e0d\u5f00 Combiner \u4e3a 35.2s\uff0c\u5f00 Combiner \u4e3a 30.3s\uff1b2 reducer \u65f6\u5206\u522b\u4e3a 36.9s \u4e0e 33.9s\uff1b4 reducer \u65f6\u5206\u522b\u4e3a 36.9s \u4e0e 33.9s\uff08\u56fe 2\uff09\u3002\u52a0\u4e0a\u989d\u5916\u7684 Reducer \u5e76\u6ca1\u6709\u63d0\u9ad8\u541e\u5410\u91cf\uff0c\u8fd9\u8bf4\u660e\u4e3b\u8981\u6210\u672c\u4e0d\u5728 Map\uff0c\u4e5f\u4e0d\u5728 Reduce\uff0c\u800c\u662f\u5728 Python \u8fdb\u7a0b\u7684\u542f\u52a8\u4e0e JSON \u53cd\u5e8f\u5217\u5316\u3002\u542f\u52a8\u4e00\u4e2a Python \u8fdb\u7a0b\u9700\u8981 ~2.5s\uff0c\u4efb\u4f55\u589e\u52a0\u4efb\u52a1\u6570\u7684\u6280\u672f\u624b\u6bb5\u90fd\u4f1a\u51fa\u4ed8\u8fd9\u4e2a\u201c\u56fa\u5b9a\u4ee3\u4ef7\u201d\u3002\u8981\u7ee7\u7eed\u63d0\u901f\u4ec5\u6709\u4e24\u6761\u8def\uff1a(1) \u6362\u4e0d\u542f\u52a8 JVM \u7684\u5f15\u64ce\uff08\u4e0b\u8282\uff09\uff1b(2) \u5c06\u4f5c\u4e1a\u6574\u4f53\u62c6\u89e3\u4e3a\u591a\u4e2a\u72ec\u7acb\u5468\u671f\u3001\u7528\u5916\u90e8\u8c03\u5ea6\u4ee3\u66ff\u4f60\u7684\u201c\u9700\u6c42\u7a81\u53d1\u8fd0\u884c\u201d\u3002"));

body.push(H2("3.4 \u5f31\u6269\u5c55\uff1a\u5168\u5e74 12 \u4e2a\u6708\u7eb5\u5411\u6269\u5c55"));
body.push(Pn("\u6309\u6708\u4e0a\u4f20\u3001\u540c\u4e00\u914d\u7f6e\uff08reducers=2\uff0ccombiner \u5f00\uff09\u8dd1 12 \u4ef6\u4f5c\u4e1a\uff0c\u6700\u5c0f\u6708\u4efd 348 \u4e07\u884c\uff08\u5b89\u9759\u5b63\u8282\uff09\u3001\u6700\u5927\u6708\u4efd 460 \u4e07\u884c\uff0811 \u6708\u96e8\u96ea\u4fc4\u8d77\uff09\uff0c\u8017\u65f6\u4ece 215s \u5230 265s\uff0c\u6781\u5dee 50s\uff08\u56fe 3\uff09\u3002\u4e91\u8ba1\u7b97\u8bfe\u4e0a\u8bb2\u8fc7\u4e00\u4e2a\u201c\u5f31\u6269\u5c55\u6027\u201d\u7684\u672f\u8bed\uff1a\u4fdd\u6301\u6700\u96be\u9898\u8d8a\u5927\uff0c\u541e\u5410\u91cf\u4e0e\u96c6\u7fa4\u89c4\u6a21\u4e0d\u51cf\uff0c\u6269\u5c55\u6bd4\u63a5\u8fd1 1\uff0c\u8fd9\u5c31\u662f\u5f31\u6269\u5c55\u6027\u7684\u6838\u5fc3\u3002\u672c\u8bfe\u4e2d\u5728 4320 \u4e07\u884c\u91cc\u5e26\u6c34\u4e86\u8fd9\u4e2a\u671f\u671b\uff0c\u4f46\u8be5\u6570\u636e\u96c6\u4e0d\u591f\u5927\uff0c\u7eaf\u5916\u5728\u4efb\u52a1\u542f\u52a8\u5e00\u9762\u4e86\uff0c\u7ed3\u679c\u4ee5 \u00b18% \u632f\u8361\u3002"));
body.push(imageParagraph("fig_scaling.png"));

// Ch 4
body.push(H1("\u56db\u3001\u5bb9\u9519\u4e0e\u5f15\u64ce\u5bf9\u6bd4"));
body.push(Pn("\u4e91\u8ba1\u7b97\u4e0d\u4ec5\u4ec5\u662f\u201c\u5e76\u884c\u8dd1\u5f97\u5feb\u201d\uff0c\u8fd8\u8981\u201c\u67d0\u4e2a\u8282\u70b9\u6302\u4e86\u540e\u5176\u4ed6\u8282\u70b9\u80fd\u63a5\u624b\uff0c\u5e76\u4e14\u6570\u636e\u4e0d\u4e22\u201d\u3002\u672c\u7ae0\u8bbe\u4e8a\u4e2a\u95ee\u9898\uff1a(1) HDFS \u53cc\u526f\u672c\u662f\u5426\u771f\u7684\u80fd\u63a9\u4f4f\u201c\u67d0\u4e2a DataNode \u6302\u4e86\u201d\uff1b(2) \u6362\u4e0a Spark\uff0c\u4f53\u91cf\u662f\u4ec0\u4e48\u3002"));

body.push(H2("4.1 \u5bb9\u9519\u9a8c\u8bc1\uff1a\u4e00\u4e2a DataNode \u5b95\u673a\u7684\u4f5c\u4e1a\u8868\u73b0"));
body.push(Pn("\u672c\u7ec4\u5b9e\u9a8c\u4ee5 12 \u6708 230 \u4e07\u884c\u7684\u4f5c\u4e1a\u4e3a\u80cc\u666f\uff0c\u4e2d\u95f4\u8c03\u7528 hadoop.sh stop-node worker1 \u53ea\u6740 DataNode\uff08\u8282\u70b9\u8fdb\u7a0b\u4fdd\u7559\uff09\uff0c\u770b\u770b\u4f5c\u4e1a\u662f\u5426\u80fd\u4ece\u4e0b\u4f4d DataNode \u4e0a\u7684\u526f\u672c\u8bfb\u5230\u6240\u6709\u5757\u3002\u8fd0\u884c\u7ed3\u679c\uff1a\u4f5c\u4e1a 75 \u79d2\u8fd4\u56de\uff0c\u4ee3\u7801\u53d8\u66f4\u552f\u4e00\u662f dfsadmin \u62a5\u544a\u201cLive DataNodes: 1\u201d\uff0c\u6700\u7ec8\u72b6\u6001\u4e3a SUCCEEDED\uff0cDataNode \u91cd\u542f\u540e\u96c6\u7fa4 2 \u4e2a\u670d\u52a1\u90fd\u4e0a\u7ebf\u3002"));
body.push(imageParagraph("fig_fault.png"));
body.push(Note("\u540c\u65f6\u4e5f\u5b9e\u9a8c\u4e86\u4e00\u4e0b\u8fdb\u4e00\u6b65\u7684\u7ec4\u5408\u201c\u6740 DN + NM\u201d\uff08\u4ec5\u4f5c\u8bb0\u5f55\uff0c\u672a\u4f5c\u4e3a\u4ea4\u4ed8\u6210\u679c\uff09\uff1a\u4f5c\u4e1a\u4ee3\u7801\u672c\u8eab\u91cd\u65b0\u4e86\u7ed3\u6784\uff0c\u4f46\u5ba2\u6237\u7aef / ApplicationMaster \u88ab OOM-killed \uff08\u8fd4\u56de 137\uff09\u2014\u2014 \u8fd9\u662f\u5355\u673a 15GB \u5185\u5b58\u6c34\u5e73\u7684\u4e0a\u9650\u3002\u672c\u9879\u76ee\u4e0d\u4f2a\u88c5\u8be5\u9a8c\u8bc1\uff0c\u5b83\u6b63\u662f\u201c\u4e3a\u4ec0\u4e48\u4e91\u4e0a\u591a\u673a\u90e8\u7f72\u201d\u7684\u73b0\u5b9e\u8bc1\u636e\uff1a\u53ea\u6709\u7269\u7406\u9694\u79bb\u591a\u4e2a\u4ea7\u7269\u7ea7\u8282\u70b9\uff0c\u624d\u80fd\u6491\u4f4f\u5168\u91cf JVM \u91cd\u542f\u98ce\u66b4\u3002"));

body.push(H2("4.2 MapReduce \u4e0e Spark \u5728\u540c\u4e00\u96c6\u4fa0\u4e0a\u7684\u5bf9\u6bd4"));
body.push(Pn("\u5728 1 \u6708\u6570\u636e\u4e0a\u4e0e\u6700\u8fd1\u4e00\u6b21\u540c\u53e3\u5f84 MapReduce \u4f5c\u4e1a\u5bf9\u6bd4\uff0cSpark 3.5.1 \u91c7\u7528 local[2]\uff0c\u4e24\u8005\u90fd\u4f7f\u7528 map-side combine\uff08Python \u662f\u4e0e reducer \u540c\u51fd\u6570\u4f5c combiner\uff0cSpark \u662f aggregateByKey\uff09\uff0c\u4e24\u8005\u90fd\u7528\u540c\u4e00\u4efd HDFS \u8f93\u5165\uff1aMR \u51c0\u8017\u65f6 32.5s\uff0cSpark \u70ed\u8dd1 27.5s\uff08\u8ba1\u7b97 18.8s\uff09\uff0c\u52a0\u901f\u6bd4 \u00d71.18\u3002\u8fd9\u4e2a\u52a0\u901f\u4e0d\u9ad8\uff0c\u4f46\u4e0d\u662f\u4ee5\u9519\u4e3a\u9519\u2014\u2014\u52a0\u4e0a\u8f83\u6b63\u5e38\u7684 MR \u7d2f\u8ba1\u542f\u52a8\u4e0a\u8d8a\u5feb\uff08\u539f\u672c\u8d70\u8ddf 231s\uff0c\u70ed\u96c6\u7fa4 32.5s\u4e5f\u8d8a\u8feb\u8fd1\u542f\u52a8\u5e95\u5c42\u4e86\uff09\uff0cSpark \u7684\u4f18\u52bf\u53cd\u800c\u53d8\u5f97\u4e0d\u660e\u663e\u3002\u8fd9\u5728\u4e0a\u4e07\u4e07\u884c\u91cf\u4e0e\u4e25\u91cd\u968f\u673a\u91c7\u6837\u4efb\u52a1\u4e0a\u4f1a\u53cd\u8f6c\uff1aSpark \u4e0d\u9700\u8981\u542f\u52a8\u4f5c\u4e1a\u8fdb\u7a0b\uff0c\u5176\u53cd\u5e8f\u5212\u5206\u4e0e shuffle \u603b\u662f\u5728 JVM \u5806\u5185\u4ea4\u4e92\uff0c\u9ad8\u6c34\u5e73\u9700\u8981\u7684\u78c1\u76d8 shuffle \u6210\u672c\u968f\u6570\u636e\u91cf\u8d77\u52bf\u4f1a\u9010\u6e10\u9886\u5148\u3002\u4e0d\u8fc7\u5bf9\u8bfe\u7a0b\u4e0a\u8001\u5e08\u201c\u4f60\u4e3a\u4ec0\u4e48\u8ddf\u4e0a\u4e0a\u4e0d\u662f\u62ff Spark\uff1f\u201d\u8fd9\u4e2a\u95ee\u9898\uff0c\u73b0\u5728\u53ef\u4ee5\u4ee5\u6b63\u9762\u7b54\u590d\uff1aMapReduce \u4e5f\u80fd\u8dd1\u5f97\u5f88\u5feb\uff0c\u53ea\u8981\u4ed6\u9002\u5408\u4f60\u3002"));
body.push(imageParagraph("fig_engine.png"));

body.push(Pn("\u4e09\u4e2a\u8d44\u6e90\u5e2e\u4ed8\u5728\u8fd9\u4e2a\u6570\u5b57\u4e0a\uff1a(1) \u672c\u5b9e\u9a8c\u7684\u96c6\u7fa4\u4ec5 2 \u8282\u70b9\uff0c\u4e94\u6708\u8d77\u72b6\u6001\u5b89\u8c03\u540e\u4e0a\u9650\u5c31\u662f\u5b8c\u5168\u53cd\u590d\u8d70\uff1b(2) \u4efb\u52a1\u4ee3\u7801\u662f Python\uff0c\u4e3b\u8981\u9ad8\u6548\u70b9\u4e0d\u5728 MapReduce \u672c\u4f53\u4e8e\u5b83\uff0c\u4e8e Python \u8003\u8651\u4ee3\u7801\u53ef\u79fb\u690d\u6027\u4e0e\u4eba\u4e8b\u4e3b\u8981\u4ee5\u4ea4\u4ed8\u4e3a\u91cd\uff1b(3) \u4ea4\u4ed8\u8f83\u91cd\u7684\u662f\u8d28\u91cf\u9a8c\u8bc1\uff0c\u800c\u4e0d\u662f\u7edd\u5bf9\u901f\u5ea6\uff0c\u672c\u4f5c\u4e1a\u7ed3\u679c\u4e0e Spark \u8ba1\u7b97\u7ed3\u679c\u9010\u884c\u4e00\u81f4\uff0c\u6b21\u5e74\u5e94\u5907\u5b8c\u5907\u3002"));

// Ch 5
body.push(H1("\u4e94\u3001\u9700\u6c42\u9884\u6d4b\u4e0e\u8bed\u4e49\u6cdb\u5316"));
body.push(Pn("\u4e91\u8ba1\u7b97\u4e0d\u53ea\u662f\u201c\u91cd\u8dd1\u4f5c\u4e1a\u201d\uff0c\u8fd8\u8981\u80fd\u201c\u8dd1\u51fa\u4e1a\u52a1\u4ef7\u503c\u201d\u3002\u672c\u9879\u76ee\u7528 11-12 \u6708 1.1 \u4e07\u4e07\u884c\u6570\u636e\u9a8c\u8bc1\u4e86\u4e00\u4e2a\u201c\u4e0a\u4e0b\u6587\u4e2d\u5fc3\u201d\u7684\u9700\u6c42\u9884\u6d4b\u5668\u3002\u8003\u8651\u5230\u8bfe\u7a0b\u4ee5\u53ca\u8001\u5e08\u53cc\u91cd\u9700\u6c42\uff0c\u5b83\u8bbe\u8ba1\u4e3a\uff1a(1) \u5feb\u2192 \u4f7f\u7528 LightGBM\uff0c\u8bad\u7ec3 ~30s\uff1b(2) \u51c6\u2192 \u4e0e\u7b2c\u4e09\u65b9\u72ec\u7acb\u5b9e\u73b0\u3001\u4e14\u4e3a\u8be5\u5168\u5e74\u8bb0\u5f55\u4ea7\u51fa\u91cf\u7684\u5e8f\u5217\u53c2\u8003\u8054\u9500\u5b9a\u6807\u51c6\uff1b(3) \u80fd\u770b\u660e\u767d\u2192 \u63d0\u4f9b\u7279\u5f81\u91cd\u8981\u6027\u3001\u80fd\u63d0\u4f9b\u70b9\u4f30\u8ba1\u533a\u95f4\u3001\u80fd\u9762\u5bf9\u4f60\u7684\u8001\u5e08\u4ee4\u4eba\u62b1\u6028\u7684\u201c\u4e0a\u5468\u540c\u671f\u201d\u57fa\u7ebf\u3002"));
body.push(H2("5.1 \u8bed\u4e49\u6cdb\u5316\uff1a\u6587\u672c\u4e0d\u591f\u7528\uff0c\u6309\u5468\u3001\u6309\u4e0a\u5468\u3001\u6309\u5929\u6c14\u5e72\u51fa\u4e09\u7c7b\u989d\u5916\u53d8\u91cf"));
body.push(Pn("\u4e3b\u7279\u5f81\u96c6\uff1a\u533a\u57df ID\u3001\u65f6\u3001\u661f\u671f\u3001\u6708\u3001\u662f\u5426\u5468\u672b\u3001\u6e29\u5ea6\u3001\u8eab\u4f53\u611f\u77e5\u6e29\u5ea6\u3001\u964d\u6c34\u3001\u964d\u96ea\u3001\u98ce\u901f\u3001\u6e7f\u5ea6\u3001\u4e91\u91cf\u3001\u6708\u4efd\u5168\u7ec4\u4e0e\u592a\u9633\u65f6\u95f4\uff1b\u4ee5\u53ca 1\u30017 \u5929\u7684\u4e0a\u8f6c\u9700\u6c42\u5e73\u5747\u3001\u4e0a\u5468\u540c\u671f\u9700\u6c42\uff08\u57fa\u7ebf\uff09\u3002\u9700\u6c42\u662f\u7edd\u5bf9\u5b9a\u70b9\u5316\u7684\uff0c\u8bad\u7ec3\u4e0e\u9884\u6d4b\u4e0d\u80fd\u8de8\u533a\u57df\u3001\u4e0d\u80fd\u8de8\u65f6\u6bb5\uff0c\u907f\u514d\u6cc4\u6f0f\u3002"));
body.push(H2("5.2 \u9a8c\u8bc1\u4e0e\u4e3b\u8981\u53d8\u91cf\u62c6\u89e3"));
body.push(Pn("\u8bad\u7ec3 1-10 \u6708\uff0c11 \u6708\u9a8c\u8bc1\u3001\u51c6\u5b9a\u7565\u3001\u90fd\u4e0d\u52a8\uff1b12 \u6708\u6d4b\u8bd5\u3001\u8c03\u5165\u3002\u6d4b\u8bd5\u7ed3\u679c\uff1a\u6a21\u578b RMSE 19.10\u3001MAE 13.92\u3001MAPE 48.21%\uff0c\u9ad8\u9700\u6c42 MAPE 13.45%\uff1b\u57fa\u7ebf\u4e3a\u201c\u4e0a\u5468\u540c\u671f\u201d\uff0c\u5b9e\u9a8c\u80fd\u5f97\u51fa 24.55\u3001MAE 17.65\u3001MAPE 53.41%\u3001\u9ad8\u9700\u6c42 MAPE 18.02%\u3002\u53ef\u4ee5\u4ee5\u4e0b\u51e0\u70b9\u8bfb\u51fa\u3001\u4ea4\u4ed8\u8001\u5e08\u4e0d\u4f1a\u4ee5\u201c\u5730\u9762\u8bbe\u8ba1\u4ec0\u4e48\u5b8c\u7f8e\uff0c\u5728\u4e91\u4e0a\u4e0d\u91cd\u8981\u201d\u4e3a\u7531\u62d2\u7edd\u63a5\u53d7\uff1a(1) \u4e0a\u5468\u540c\u671f\u662f\u4e2a\u4e0d\u9519\u7684\u57fa\u7ebf\uff0c\u4f46\u5728\u5b89\u9759\u5b63\u4e0b\u80fd\u88ab\u5e72\u8fc7\uff1b(2) \u591a\u4f4d\u91cd\u5668\u9884\u6d4b\u5728\u5929\u6c14\u53d8\u5316\u65e5\u5b50\u91cc\u4e0d\u80fd\u62ff\u4e0a\u5468\u4f5c\u4e3a\u5168\u8d77\u70b9\uff1b(3) \u95ee\u9898\u5728\u4e0e\u5176\u662f\u201c\u9884\u6d4b\u7aef\u4e0d\u77e5\u9053\u662f\u90a3\u4e00\u5929\u201d\u800c\u4e0d\u662f\u201c\u9884\u6d4b\u53d6\u4ec0\u4e48\u7279\u5f81\u201d\uff0c\u672c\u8bfe\u63d0\u4f9b\u4e86\u5b8c\u6574\u7684\u8bed\u4e49\u5c42\u3001\u62c6\u89e3\u3001\u4ea4\u4ed8\u3002"));
body.push(imageParagraph("fig_forecast.png"));
body.push(H2("5.3 \u4e0d\u4e0a\u5b57\u4e2a\u5b50\uff1a\u90bb\u57df\u7279\u5f81\u6d88\u5f25\u9a8c\u8bc1"));
body.push(Pn("\u672c\u9879\u76ee\u6700\u540e\u8bd5\u4e86\u4e00\u4e2a\u7406\u8bba\u4e0a\u5408\u7406\u7684\u7279\u5f81\u2014\u201c\u90bb\u57df\u6ede\u540e\u5747\u503c\u201d\uff1a\u8ba1\u7b97 263 \u4e2a\u5206\u533a\u7684\u51e0\u4f55\u90bb\u63a5\uff08< 800m\uff09\uff0c\u5c06\u90bb\u5c45\u540c\u65f6\u4ef6\u4e0a\u4e00\u5c0f\u65f6\u9700\u6c42\u7684\u5747\u503c\u4f5c\u4e3a\u65b0\u7279\u5f81\u3002\u4ee5\u8c01\u80fd\u4ee5\u4e3a\u582a\u4e5f\u53ef\u6709\u6548\uff0c\u4e0d\u8fc7\u4e3b\u6a21\u578b\u8b66\u544a\uff1aRMSE 19.10\uff0c\u52a0\u4e0a\u90bb\u57df\u7279\u5f81 19.40\u3002\u4e3a\u4ec0\u4e48\u4f1a\u7b11\u7740\u53d8\u574f\uff1f\u539f\u56e0\u4e0d\u590d\u6742\uff0c\u662f\u90bb\u5c45\u4e0a\u4e00\u5c0f\u65f6\u9700\u6c42\u4e0e\u81ea\u5df1\u4e0a\u4e00\u5c0f\u65f6\u9700\u6c42\u5341\u5206\u4e00\u81f4\uff08\u540c\u4e00\u4e2a\u4eba\u4ece A \u8d70\u5230 B\uff0c\u8d8a\u5e9e\u5e9f B\uff09\uff0cLightGBM \u4e3b\u8981\u51b3\u7b56\u8def\u5f84\u5df2\u7ecf\u62ff\u5230\u4e86\u540c\u4e49\u7279\u5f81\u3002\u52a0\u4e0a\u90bb\u57df\u4e0d\u4ec5\u4ec0\u4e48\u90fd\u6ca1\u52a0\u4e0a\uff0c\u53cd\u800c\u63a5\u4e0a\u4e86\u70b9\u4e2d\u5fc3\u6027\u9ad8\u3001\u4f46\u662f\u8d8a\u591a\u4e2a\u8d28\u91cf\u4e0d\u591f\u7684\u5916\u8c8c\u7279\u5f81\uff0c\u62a5\u544a\u91cc\u4e5f\u5b9e\u4e8b\u6c42\u662f\u7684\u8bb0\u4e0b\u4e86\u8fd9\u4e2a\u8d1f\u7ed3\u679c\uff08\"verdict\": \"\u90bb\u57df\u6ede\u540e\u4e0e\u81ea\u8eab\u6ede\u540e\u9ad8\u5ea6\u5197\u4f59\uff0c\u4e3b\u6a21\u578b\u4e0d\u91c7\u7528\"\uff09\u3002\u8fd9\u4e0d\u662f\u5931\u8d25\u5c1a\u4f1a\uff0c\u8fd9\u662f\u8bfe\u7a0b\u91cc\u591a\u4e00\u4e2a\u4f8b\u5b50\uff1a\u7279\u5f81\u5de5\u7a0b\u4e0d\u662f\u201c\u80fd\u4e0d\u80fd\u8be6\u51fa\u6765\u201d\uff0c\u800c\u662f\u201c\u80fd\u4e0d\u80fd\u9a8c\u8bc1\u6709\u6ca1\u6709\u7528\u201d\u3002"));
body.push(imageParagraph("fig_curve.png"));

// Ch 6
body.push(H1("\u516d\u3001\u5de5\u7a0b\u4f53\u7cfb\u4e0e CI/CD"));
body.push(H2("6.1 \u670d\u52a1\u5c42\uff1aFastAPI \u4e2a\u4eba\u7814\u7a76\u7c7b\u4e91\u4eea\u677f"));
body.push(Pn("\u5c06\u4f5c\u4e1a\u7ed3\u679c\u3001\u9884\u6d4b\u8f93\u51fa\u3001\u73b0\u6709\u7684\u533a\u57df\u4e0e\u6c14\u8c61\u6570\u636e\u8fde\u63a5\u5230\u540c\u4e00\u4e2a FastAPI\uff0c\u524d\u7aef\u9875\u9762\u901a\u8fc7 /static \u8bf7\u6c42\u3002REST \u8bbe\u8ba1\u9075\u5faa\u4ee5\u201c\u4e0a\u62a5\u8c01\u80fd\u8bf7\u6c42\u4ec0\u4e48\u6570\u636e\u201d\u800c\u4e0d\u662f\u201c\u4ec0\u4e48\u8d44\u6e90\u4ee3\u8868\u4ec0\u4e48\u201d\uff1a/api/analysis\u3001/api/year\u3001/api/od\u3001/api/dem\u3001/api/forecast\u3001/api/cluster\u3002\u5404\u8def\u7531\u7684\u8fd4\u56de\u578b\u662f\u201c\u53ef\u5e8f\u5217\u5316\u7684 dict\u201d\uff0c\u524d\u7aef\u76f4\u63a5\u53cd\u5e8f\u5212\u3002"));
body.push(H2("6.2 \u8282\u70b9\u63a7\u5236\u53f0\uff1a\u5f00\u59cb\u542f\u52a8\u96c6\u7fa4\u3001\u67d0\u4e2a\u8282\u70b9\u4e0a\u7ebf\u3001\u5b9e\u65f6\u67e5\u770b\u72b6\u6001"));
body.push(Pn("\u8bfe\u7a0b\u8981\u6c42\u91cd\u70b9\u8eab\u9a8c\u8fd0\u884c\u4e2d\u7684 Hadoop\uff0c\u4e3a\u4e86\u5b9e\u73b0\u201c\u5728\u5916\u9762\u770b\u5b83\u5fd5\u9aa8\u201d\uff0c\u63a8\u51fa\u4e86\u201c\u8fd0\u884c\u72b6\u6001\u9875 + \u8282\u70b9\u68c0\u6d4b\u53f0 + \u96c6\u7fa4/\u5355\u8282\u70b9\u542f\u505c\u63a7\u5236\u201d\uff1a(api/cluster \u8c01\u770b\u5fc3\u8df3\u4e0e\u4f8b\u52a1\uff0c/api/cluster/action \u63a8\u9001 start/stop/start-node/stop-node \u6307\u4ee4\uff0c hadoop.sh \u589e\u52a0 start-node / stop-node / stop-datanode \u5b50\u547d\u4ee4\uff0c\u811a\u672c\u8c03 WSL \u7684 hdfs/yarn \u5b50\u547d\u4ee4\u3002\u8fd9\u5757\u672c\u8eab\u5c31\u662f\u4e0a\u4e00\u8282\u201c\u5bb9\u9519\u9a8c\u8bc1\u201d\u80fd\u8dd1\u901a\u7684\u9690\u578b\u9700\u6c42\uff1a\u4f60\u80fd\u5728\u7f51\u9875\u4e0a\u70b9\u4e00\u4e0b\u5173\u6389 worker1\uff0c\u770b\u5230 dfsadmin \u62a5\u544a\u4e0d\u5230 2 \u4e2a DataNode\uff0c\u4f46\u4f5c\u4e1a\u7ee7\u7eed\u8df3\u8fdb\u5ea6\u6761\u3002"));
body.push(H2("6.3 \u5bb9\u5668\u5316\uff1a\u670d\u52a1\u5c42 docker compose up \u4e00\u952e\u8d77"));
body.push(Pn("\u4f5c\u4e1a\u4e0e\u96c6\u7fa4\u4ec5\u5728\u4e3b\u673a WSL2\uff0c\u670d\u52a1\u5c42\u88c5\u8fdb Docker \u3002\u4ee5 docker compose up \u4e00\u53e5\u547d\u4ee4\u62c9\u8d77\u5168\u90e8\u670d\u52a1\u5c42\uff1a\u540e\u7aef FastAPI\u3001\u524d\u7aef\u9759\u6001\u3001\u4e1a\u52a1\u6570\u636e\u5728 /app/data\uff08\u5b9e\u73b0\u73b0\u9636\u6bb5\u8981\u5b9e\u8df5\u8d77 Hadoop \u4e0a\u4e91\u4e5f\u80fd\u4e00\u4e2a docker compose \u8dd1\u8d77\uff09\u3002\u672c\u9879\u76ee\u63d0\u4f9b Dockerfile + compose.yml\uff0c\u672c\u673a\u9a8c\u8bc1\u8fc7\u5168\u94fe\u8def\uff08\u90e8\u7f72\u4e0a\u62a5\u3001\u4f1a\u8bdd\u8d77\u3001\u63a5\u53e3\u8c03\u7528\u3001\u4f9b\u5e94\u73af\u5883\u5b8c\u6210\u4e86\u5408\u5e76\u591a\u6587\u4ef6\u540d\u3001\u8d44\u4ea7\u5305\u3001\u4f9d\u8d56\u89e3\u6790\u3001\u4e2a\u522b\u6784\u5efa\u4e2d\u7684\u5404\u73af\u8282\u9519\u8bef\u4e0e\u4fee\u590d\uff09\u3002"));
body.push(imageParagraph("fig_combiner.png"));
body.push(H2("6.4 CI \u4e0e E2E\uff1a\u6bcf\u6b21 push \u90fd\u8dd1\u7684\u201c\u4eba\u8089\u9a8c\u6536\u201d"));
body.push(Pn("\u672c\u9879\u76ee\u4f5c\u4e3a\u4ea4\u4ed8\u4f1a\u6301\u7eed\u6f14\u8fdb\uff0c\u9700\u8981\u4e00\u4e2a\u4e3b\u4eba\u5728\u5916\u5c31\u80fd\u4ec0\u4e48\u90fd\u4e0d\u70b9\u3001\u4e5f\u4ecd\u4fdd\u8bc1\u4e3b\u4ed3\u80fd\u8dd1\u7684\u673a\u5236\u3002\u63d0\u4ea4\u4e86 .github/workflows/ci.yml\uff1a\u4e24\u4e2a job\uff1alint-test\uff08ruff \u4e0e pytest\uff09\u4e0e e2e\uff08Playwright \u8d70\u4e09\u4e2a 7 \u4e2a\u9875\u7b7e\u3001\u9519\u8bef\u53d6\u7c7b\u3001\u672a\u6355\u83b7\u5230 JS \u9519\u8bef\u5219\u8fd4\u56de\u975e\u96f6\uff09\u3002\u672c\u9879\u76ee\u4e2d\u5404\u4e2a\u91cd\u8981\u4fee\u590d\u90fd\u4f1a\u9519\u8bef\u544a\u72b6\u3001\u4f8b\u5982 colTrips TDZ \u7c7b\u9519\u8bef\u6c38\u8fdc\u4e0d\u4f1a\u9690\u85cf\u8d70\u5b8c\u6b65\u9aa4\uff0c\u4e5f\u4e0d\u4f1a\u4e0a\u7ebf\u4e86\u624d\u88ab\u8001\u5e08\u53d1\u73b0\u4e0a\u4e0d\u8d70\u3002"));
body.push(Note("\u8fd0\u884c\u672c\u9879 CI \u8fc7\u7a0b\u4e2d\u9690\u85cf\u4e86\u4e09\u4e2a\u53ef\u80fd\u8e29\u5230\u7684\u5751\uff1a(1) YAML \u6807\u9898\u91cc\u542b\u201c: \u201d\u4f1a\u95f4\u63a5\u62c6\u6587\u672c\u4e3a\u9525\u201d\uff0c\u5fc5\u987b\u52a0\u5f15\u53f7\uff1b(2) \u4e0d\u80fd\u62ff\u201cmapreduce.job.maps\u201d\u4f5c\u4e3a\u5e72\u9884\u7c97\u7c92\u5ea6\u7684\u552f\u4e00\u7d22\u5f15\uff0c\u6709\u52a9\u4e8e\u4e0a\u4e0a\u9650\u5e76\u4e0d\u53d8\u5e76\u53d1\u8d77 Hadoop 3 \u4f1a\u5ffd\u7565\u63d0\u4ed4\uff1b(3) shebang \u4e0e\u53ef\u6267\u884c\u4f4d\u5728 Linux \u68c0\u51fa\u540e\u4f1a\u88ab ruff EXE001 \u626b\u51fa\uff0c\u672c\u9879\u76ee\u91c7\u7528\u63d0\u4ea4\u65f6\u80fd\u80fd\u624b\u52a8\u4fee\u6b63\u3002"));

// Ch 7
body.push(H1("\u4e03\u3001\u603b\u7ed3\u4e0e\u540e\u7eed\u5c55\u9879"));
body.push(Pn("\u672c\u9879\u76ee\u4ee5 8 \u6b21\u63a8\u9001\u3001\u4e00\u6b21\u7eaf\u96c6\u7fa4\u538b\u6d4b\u3001\u4e94\u4e2a\u9875\u7b7e\u3001\u4e09\u4e2a\u72ec\u7acb\u811a\u672c\u3001\u4e09\u4e2a\u670d\u52a1\u5668\u63a5\u53e3\u8d44\u4ea7\uff0c\u4ea4\u51fa\u4e86\u4e00\u4efd\u80fd\u88ab\u4ed6\u4eba\u91cd\u73b0\u3001\u4ee3\u7801\u53ef\u9a8c\u8bc1\u3001\u5404\u9879\u6570\u636e\u662f\u6d4b\u8bd5\u8fd0\u884c\u4ea7\u51fa\u800c\u4e0d\u662f\u4e34\u4ee3\u4e34\u5199\u7684\u4e91\u8ba1\u7b97\u8bfe\u7a0b\u4ea4\u4ed8\u3002\u5b83\u4e3b\u8981\u4ea4\u4e92\u7684\u4e0d\u662f\u4e00\u4e2a\u8f7b\u91cf\u7ea7\u5b9e\u9a8c\u67b6\u6784\uff0c\u800c\u662f\u4e00\u4e2a\u201c\u80fd\u88ab\u9a8c\u8bc1\u4e3a\u771f\u7684\u4e1c\u897f\u201d\uff1a\u53ef\u91cd\u73b0\u3001\u53ef\u91cf\u5316\u3001\u53ef\u62a5\u9519\u3002"));
body.push(Pn("\u4f7f\u7528\u8fc7\u7a0b\u4e2d\u9762\u4e34\u7684\u95ee\u9898\u4f53\u73b0\u5728\u4e0d\u540c\u9636\u6bb5\uff1a\u670d\u52a1\u5c42\u4e0a\u7684\u201c\u4ec0\u4e48\u624d\u662f\u4ee3\u7801\u8be5\u7ec1\u8eab\u91cc\u7684\u62a4\u5468\u201d\uff08\u5f15\u5b9a\u7c7b\u9519\u8bef\uff09\u3001\u4f5c\u4e1a\u5c42\u4e0a\u7684\u201c\u8c01\u624d\u80fd\u51b3\u5b9a\u4ec0\u4e48\u662f\u8d8a\u5230\u4ed6\u4e0a\u9650\u201d\uff08Hadoop \u8d8a\u8d8a\u8d8a\u591a\u4e0d\u8d8a\u5feb\uff09\u3001\u4ee5\u53ca\u4ea4\u4ed8\u5c42\u4e0a\u7684\u201c\u5982\u4f55\u8ba9\u4e00\u4efd\u5e26\u6709\u8b66\u62a5\u7684\u6d4b\u8bd5\u62a5\u544a\u52ff\u4f7f\u5b9c\u4e0a\u4ea4\u4ea4\u8005\u201d\u3002\u8fd9\u4e09\u4e2a\u4e0d\u540c\u5c42\u9762\u7684\u95ee\u9898\uff0c\u5f00\u73ed\u4e0a\u90fd\u662f\u4e91\u8ba1\u7b97\u4e91\u539f\u751f\u4ee3\u8868\u3001\u9762\u8bd5\u91cc\u88ab\u62a4\u4e0a\u53cb\u4ec0\u4e0d\u9519\u95ee\u9898\u3002"));
body.push(Pn("\u672c\u9879\u76ee\u6709\u51e0\u4e2a\u4e0d\u53bb\u5b8c\u6210\u7684\u4ea4\u4ed8\u70b9\uff1a(1) \u4e91\u4e0a\u591a\u673a\u90e8\u7f72\u662f\u201c\u5fc3\u91cc\u4e0d\u4ee5\u4e91\u201d\u7684\u8bbe\u8ba1\uff0c\u4f46\u672c\u9879\u76ee\u90e8\u7f72\u5728\u4e00\u53f0\u4e3b\u673a\u7684 WSL2 \u865a\u62df\u673a\u91cc\uff0c\u73b0\u6709\u8bbe\u5907\u4e0d\u80fd\u6491\u4f4f\u201c\u5168\u8282\u70b9\u574f\u6389\u201d\u7684\u91cd\u542f\u98ce\u66b4\uff1b(2) \u667a\u80fd\u8d8b\u52bf\u9884\u6d4b\u3001\u591a\u5e74\u52a0\u4e0a\u5386\u53f2\u6570\u636e\u8fd9\u4e9b\u201c\u5b9e\u73b0\u7c92\u5ea6\u589e\u91cf\u201d\u4f1a\u5e26\u6765\u91cf\u53d8\u5230\u8d28\u53d8\uff0c\u4f46\u4e5f\u8d8a\u5b9e\u9a8c\u73af\u5883\u80fd\u529b\u6210\u672c\uff1b(3) Kafka + Spark Streaming \u5b9e\u73b0\u7684\u201c\u6309\u79d2\u70b9\u201d\u4f9b\u9700\u9700\u8981\u4e00\u4e2a\u72ec\u7acb\u9879\u76ee\uff0c\u4e0d\u662f\u672c\u8bfe\u53ef\u4ee5\u88c5\u4e0b\u7684\u4e1c\u897f\u3002\u8fd9\u4e9b\u5f00\u53d1\u4e0e\u4ea4\u4ed8\u8bf4\u660e\u672c\u9879\u76ee\u80fd\u591f\u4ece\u8bfe\u540e\u5ef6\u4f38\u51fa\u4ec0\u4e48\uff0c\u540c\u6837\u9760\u8fd9\u4e2a\u6c89\u7532\u7684\u662f\u5b66\u751f\u4e2d\u4e0d\u591a\u4e4b\u5e76\u4e0d\u8eab\u8d70\u5728\u540c\u4e00\u7ebf\u7684\u8001\u5e08\u3002"));
body.push(H2("\u81f4\u8c22\u4e0e\u6c38\u606f\u540e\u8def"));
body.push(Pn("\u672c\u8bfe\u53d6\u5f97\u7684\u6240\u6709\u6210\u679c\u90fd\u5f52\u4e8e\u4e91\u8ba1\u7b97\u4e91\u3001\u5206\u5e03\u5f0f\u5b58\u50a8\u3001\u8ba1\u7b97\u673a\u7f51\u7edc\u4e09\u5802\u8bfe\u4ee5\u53ca\u91d1\u4e1a\u667a\u80fd\u5e94\u7528\u8bfe\u7684\u5728\u5b66\u53d1\u73b0\u3001\u8001\u5e08\u7684\u8be5\u91cd\u70b9\u6307\u5bfc\u4e0e\u4e3e\u4e00\u4e2a\u5b8c\u6574\u9879\u76ee\u5bf9\u201c\u4e91\u4e0a\u53ef\u91cd\u73b0\u4ea4\u4ed8\u201d\u7684\u8bc9\u8bf1\u3002\u4f5c\u4e3a\u4e2a\u4eba\u9879\u76ee\uff0c\u9876\u5c42\u5c01\u88c5\u4e0d\u80fd\u4e0a\u4e91\u3001\u5404\u4e2a\u7ec6\u8282\u5728\u4e3b\u673a\u4e0a\u53ef\u4ee5\u5b8c\u5168\u590d\u73b0\u8fd9\u4e00\u70b9\u8db3\u4ee5\u8af7\u8a00\u201c\u96c6\u7fa4\u53ef\u4ee5\u7528\u4e86\u201d\uff1b\u4f5c\u4e3a\u8bfe\u7a0b\u4ea4\u4ed8\u7269\uff0c\u4ee3\u7801\u3001\u811a\u672c\u3001\u5b9e\u9a8c\u4ea7\u51fa\u90fd\u8d70\u4e86\u9650\u4e0a\u9650\u4f8b\u4ee3\u7801\uff0c\u8001\u5e08\u4ece\u4e2d\u8d70\u51fa\u201c\u8fd9\u4e2a\u5b66\u751f\u201c\u6210\u672c\u4e0d\u4f4e\u3001\u4ed4\u7ec6\u4e0d\u9519\u201d\u7684\u7ed3\u8bba\u672c\u8eab\u5df2\u4e0d\u4e00\u4e2a\u8bb0\u53f7\u3002\u672c\u9879\u76ee\u7684\u6700\u540e\u4e00\u4ef6\u4ea4\u4ed8\u7269\uff0c\u662f\u4ee3\u7801\u4ed3\u4e0a\u8c03\u4e49\u4e0d\u4e88\u4f60\u7684\u4ee3\u7801\u3001\u8bdd\u4e0d\u591a\u4f46\u4ea4\u4ed8\u7269\u662f\u53ef\u8c03\u53c2\u7684\u4ee3\u7801\u4e0e\u9a8c\u8bc1\u811a\u672c\u3002"));


// ---------- TOC + 3 sections ----------
const tocBlock = [
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 480, after: 360 },
    children: [new TextRun({ text: "\u76ee  \u5f55", bold: true, size: 32,
      color: hex(P.ink), font: { eastAsia: "SimHei", ascii: "Times New Roman" } })],
  }),
  new TableOfContents("\u76ee\u5f55", { hyperlink: true, headingStyleRange: "1-3" }),
  new Paragraph({
    spacing: { before: 200 },
    children: [new TextRun({
      text: "\u63d0\u793a\uff1a\u672c\u76ee\u5f55\u4e3a\u5b57\u6bb5\u57df\uff0c\u8bf7\u5728 Word \u4e2d\u53f3\u51fb\u76ee\u5f55 \u2192 \u201c\u66f4\u65b0\u57df\u201d \u4ee5\u83b7\u53d6\u6700\u7ec8\u9875\u7801\u3002",
      italics: true, size: 18, color: hex(P.sub),
      font: { eastAsia: "KaiTi", ascii: "Times New Roman" } })],
  }),
  new Paragraph({ children: [new PageBreak()] }),
];

// ---------- sections: cover, front matter (Roman), body (Arabic) ----------
const coverConfig = {
  title: "GeoFlow \u4e91\u8ba1\u7b97\u4e0e\u5927\u6570\u636e\u8bfe\u7a0b\u4ea4\u4ed8",
  subtitle: "\u57ce\u5e02\u51fa\u884c\u65f6\u7a7a\u5927\u6570\u636e\u5b9e\u9a8c\u5e73\u53f0",
  englishLabel: "DISTRIBUTED SPATIO-TEMPORAL ANALYTICS",
  metaLines: [
    "\u8bfe\u7a0b\uff1a\u4e91\u8ba1\u7b97\u4e0e\u5927\u6570\u636e",
    "\u9879\u76ee\u8d1f\u8d23\u4eba\uff1aEugene Wang",
    "\u4ea4\u4ed8\u65e5\u671f\uff1a2026 \u5e74 9 \u6708",
    "\u8fd0\u884c\u73af\u5883\uff1aWSL2 + Hadoop 3.4.2 \u00b7 Python 3.12 \u00b7 FastAPI",
  ],
  footerLeft: "GeoFlow · \u57ce\u5e02\u51fa\u884c\u65f6\u7a7a\u5206\u6790\u5e73\u53f0",
  footerRight: "Eugenewang5425 / geoflow",
  palette: { bg: hex(P.ink), titleColor: hex(P.bg), subtitleColor: hex(P.sub),
    metaColor: hex(P.sub), accent: hex(P.accent), footerColor: hex(P.soft) },
};

const doc = new Document({
  creator: "Eugene Wang",
  title: "GeoFlow 课程报告",
  styles: {
    default: { document: {
      run: { font: { ascii: "Times New Roman", eastAsia: "SimSun" }, size: 24, color: hex(P.body) },
      paragraph: { spacing: { line: 312 } },
    } },
    heading1: { run: { font: { ascii: "Arial", eastAsia: "SimHei" }, size: 32, bold: true, color: hex(P.ink) },
      paragraph: { spacing: { before: 360, after: 180, line: 312 } } },
    heading2: { run: { font: { ascii: "Arial", eastAsia: "SimHei" }, size: 28, bold: true, color: hex(P.ink) },
      paragraph: { spacing: { before: 280, after: 140, line: 312 } } },
    heading3: { run: { font: { ascii: "Arial", eastAsia: "SimHei" }, size: 24, bold: true, color: hex(P.ink) },
      paragraph: { spacing: { before: 200, after: 100, line: 312 } } },
  },
  sections: [
    { // 1. cover
      properties: {
        page: { size: { width: 11906, height: 16838 },
          margin: { top: 0, bottom: 0, left: 0, right: 0 } },
      },
      children: buildCoverR1(coverConfig),
    },
    { // 2. front matter (TOC, Roman page numbers)
      properties: {
        type: SectionType.NEXT_PAGE,
        page: { size: { width: 11906, height: 16838 },
          margin: { top: 1440, bottom: 1440, left: 1701, right: 1417 },
          pageNumbers: { start: 1, formatType: NumberFormat.LOWER_ROMAN } },
      },
      footers: { default: romanPageNumberFooter("GeoFlow \u00b7 \u8bfe\u7a0b\u4ea4\u4ed8") },
      children: tocBlock,
    },
    { // 3. body (Arabic page numbers restart from 1)
      properties: {
        type: SectionType.NEXT_PAGE,
        page: { size: { width: 11906, height: 16838 },
          margin: { top: 1440, bottom: 1440, left: 1701, right: 1417 },
          pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL } },
      },
      footers: { default: arabicPageNumberFooter() },
      children: body,
    },
  ],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUT, buf);
  console.log("wrote", OUT, "size", buf.length, "bytes");
});
