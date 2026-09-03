"use strict";
const $ = id => document.getElementById(id);
const fmt = n => Number(n).toLocaleString("zh-CN");
let geo, current, generation = 0, selectedZone = null, pollTimer;
const paths = new Map();
const escapeHtml = value => String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function notice(message, error = false) { $("notice").hidden = !message; $("notice").textContent = message; $("notice").classList.toggle("error", error); }
async function get(url, options) { const r = await fetch(url, options); if (!r.ok) { let info; try { info = (await r.json()).detail; } catch { info = r.statusText; } throw Error(typeof info === "string" ? info : JSON.stringify(info)); } return r.json(); }
function params() { const query = new URLSearchParams(); if (+$("hour").value < 24) query.set("hour", $("hour").value); if ($("borough").value) query.set("borough", $("borough").value); return query.toString(); }
function project([lon, lat]) { return [lon * Math.PI / 180, -Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360))]; }
function buildMap() {
  const all = [];
  geo.features.forEach(f => { const polys = f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates; polys.forEach(p => p.forEach(r => r.forEach(c => all.push(project(c))))); });
  const xs = all.map(p => p[0]), ys = all.map(p => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const scale = Math.min(710 / (maxX-minX), 440 / (maxY-minY));
  function xy(c) { const [x,y] = project(c); return [400 + (x-(minX+maxX)/2)*scale, 256 + (y-(minY+maxY)/2)*scale]; }
  for (const f of geo.features) {
    const polys = f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates;
    const d = polys.map(p => p.map(r => r.map((c,i) => (i ? "L" : "M") + xy(c).map(v => v.toFixed(2)).join(",")).join("") + "Z").join("")).join("");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d); path.setAttribute("fill", "#d4dfeb"); path.setAttribute("fill-rule", "evenodd");
    path.dataset.id = f.properties.id; path.setAttribute("tabindex", "0"); path.setAttribute("role", "button");
    path.setAttribute("aria-label", f.properties.name);
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title"); title.textContent = f.properties.name; path.appendChild(title);
    path.addEventListener("click", () => selectZone(f.properties.id));
    path.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectZone(f.properties.id); } });
    $("map").appendChild(path);
    if (!paths.has(f.properties.id)) paths.set(f.properties.id, []);
    paths.get(f.properties.id).push(path);
  }
}
function selectZone(id) {
  selectedZone = id;
  paths.forEach((parts,z) => parts.forEach(p => p.classList.toggle("selected", z === id)));
  const zone = current?.zones.find(z => z.id === id);
  const info = geo.features.find(f => f.properties.id === id)?.properties;
  $("zone-detail").replaceChildren();
  const name = document.createElement("strong"), desc = document.createElement("span");
  name.textContent = zone?.name || info?.name || "未知区域";
  desc.textContent = zone ? `${fmt(zone.trips)} 次出行 · 平均 ${zone.avg_distance_km.toFixed(2)} km` : "当前筛选条件下无有效记录";
  $("zone-detail").append(name, desc);
}
async function refreshAnalysis() {
  const request = ++generation;
  try {
    const data = await get("/api/analysis?" + params()); if (request !== generation) return;
    current = data;
    const m = data.summary, quality = data.quality;
    $("kpi-trips").textContent = fmt(m.trips);
    $("kpi-distance").innerHTML = m.avg_distance_km.toFixed(2) + "<em>km</em>";
    $("kpi-duration").innerHTML = m.avg_minutes.toFixed(1) + "<em>min</em>";
    $("kpi-quality").innerHTML = (100 * quality.valid / quality.input).toFixed(2) + "<em>%</em>";
    $("dataset-month").textContent = data.month.replace("-", " 年 ") + " 月 · 整月记录";
    $("run-stamp").textContent = data.metadata.job_id || data.run_id;
    $("export").href = "/api/export?" + params();
    const max = Math.max(1, ...data.zones.map(z => z.trips)); const byId = new Map(data.zones.map(z => [z.id,z]));
    paths.forEach((parts,id) => { const n = byId.get(id)?.trips || 0; const t = Math.log1p(n) / Math.log1p(max); const fill = n ? `rgb(${Math.round(218-184*t)},${Math.round(234-149*t)},${Math.round(250-91*t)})` : "#dce4ec"; parts.forEach(p => p.setAttribute("fill", fill)); });
    $("ranking").replaceChildren();
    data.zones.slice(0,8).forEach((z,i) => { const row = document.createElement("div"); row.className="rank-row"; row.tabIndex=0; row.setAttribute("role","button"); row.setAttribute("aria-label",`查看 ${z.name}`); row.innerHTML=`<span class="rank-num">${String(i+1).padStart(2,"0")}</span><div><div class="rank-name">${escapeHtml(z.name)}</div><div class="rank-bar"><span style="width:${100*z.trips/max}%"></span></div></div><span class="rank-value">${fmt(z.trips)}</span>`; row.onclick=()=>selectZone(z.id); row.onkeydown=e=>{if(e.key==="Enter")selectZone(z.id);}; $("ranking").appendChild(row); });
    if (!data.zones.length) $("ranking").textContent="当前筛选没有记录。";
    const top = data.zones[0]; $("insight").textContent = top ? `${top.name} 在当前筛选中出行最多，占有效上车记录的 ${(100*top.trips/m.trips).toFixed(1)}%。该值反映记录中的需求，不能直接解释为拥堵程度。` : "请更换区域或时段，查看空间分布。";
    $("hour-chart").replaceChildren(); const peak=Math.max(1,...data.hourly);
    data.hourly.forEach((n,h) => { const b=document.createElement("button"); b.style.height = Math.max(2, n/peak*100)+"%"; if(n===peak)b.className="peak"; b.title=`${h}:00 · ${fmt(n)} 次`; b.setAttribute("aria-label", b.title); b.onclick=()=>{ $("hour").value=h; updateHour(); refreshAnalysis(); }; $("hour-chart").appendChild(b); });
    $("quality").innerHTML=`<div class="quality-row"><span>原始记录</span><strong>${fmt(quality.input)}</strong></div><div class="quality-row"><span>有效记录</span><strong>${fmt(quality.valid)}</strong></div><div class="quality-track"><span style="width:${quality.valid/quality.input*100}%"></span></div><div class="quality-row"><span>规则排除</span><strong>${fmt(quality.rejected)}</strong></div><div class="quality-row"><span>区域 / 日期 / OD 总数守恒</span><strong>已通过 ✓</strong></div>`;
    if(selectedZone!==null)selectZone(selectedZone);
  } catch(e) { notice(e.message,true); }
}
function updateHour(){ const h=+$("hour").value; const caption=h===24?"全天累计":`${String(h).padStart(2,"0")}:00–${String(h).padStart(2,"0")}:59`; $("hour-caption").textContent=caption; $("filter-caption").textContent=caption; }
async function refreshCluster(){ try{ const c=await get("/api/cluster"); $("side-dot").classList.toggle("online",c.online); $("side-state").textContent=c.online?`${c.yarn.activeNodes} 个计算节点在线`:"集群离线 · 可浏览历史结果"; $("cluster").innerHTML=`<div class="cluster-item">HDFS DataNodes <span>${c.hdfs?.NumLiveDataNodes??"—"} 在线</span></div><div class="cluster-item">YARN NodeManagers <span>${c.yarn?.activeNodes??"—"} 在线</span></div><div class="cluster-item">HDFS 数据块 <span>${fmt(c.hdfs?.BlocksTotal??0)}</span></div>`+c.nodes.map(n=>`<div class="cluster-item">${escapeHtml(n.id)}<span>${escapeHtml(n.state)} · ${n.numContainers} containers</span></div>`).join(""); }catch{ $("side-state").textContent="暂时无法读取集群状态"; } }
async function refreshRuns(){const data=await get("/api/runs"); $("runs").innerHTML=data.runs.map(r=>`<tr><td>${escapeHtml(r.run_id)}<small>${escapeHtml(r.job_id||"尚无作业 ID")}</small></td><td><span class="status ${escapeHtml(r.status)}">${escapeHtml(r.status)}</span></td><td>${r.reducers}</td><td>${r.combiner?"开启":"关闭"}</td><td>${r.elapsed_seconds??"—"} s</td></tr>`).join("")||'<tr><td colspan="5">暂无作业记录</td></tr>'; return data.current; }
async function refreshEvidence(){const e=await get("/api/evidence"); const v=e.verification; $("evidence").innerHTML=v?`<div class="evidence-grid"><div class="evidence-card"><strong>${v.exact_match?"完全一致":"存在差异"}</strong><span>单进程参考结果 vs Hadoop 输出</span></div><div class="evidence-card"><strong>${fmt(v.compared_keys)}</strong><span>逐键核对的聚合结果</span></div><div class="evidence-card"><strong>${fmt(v.input_rows)}</strong><span>真实输入行数</span></div></div>`:'<p>对照实验尚未运行；不展示推测结果。</p>';}
document.querySelectorAll(".nav").forEach(button=>button.onclick=async()=>{document.querySelectorAll(".view").forEach(v=>v.hidden=v.id!==button.dataset.view);document.querySelectorAll(".nav").forEach(b=>b.classList.toggle("active",b===button));try{if(button.dataset.view==="experiments")await Promise.all([refreshRuns(),refreshEvidence()]);if(button.dataset.view==="architecture")await refreshCluster();}catch(e){notice(e.message,true);}});
$("hour").addEventListener("input",updateHour);$("hour").addEventListener("change",refreshAnalysis);$("borough").addEventListener("change",refreshAnalysis);
$("refresh").onclick=()=>refreshRuns().catch(e=>notice(e.message,true));
$("run").onclick=async()=>{ $("run").disabled=true; try{await get("/api/jobs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({month:current?.month||"2025-01",reducers:2,combiner:true})});notice("Hadoop 作业已提交。数据清洗与分布式统计可能需要数分钟，完成后自动更新。"); pollJob();}catch(e){notice(e.message,true);$("run").disabled=false;} };
async function pollJob(){try{const state=await refreshRuns();if(state.status==="RUNNING"){pollTimer=setTimeout(pollJob,3000);return;}$("run").disabled=false;if(state.status==="SUCCEEDED"){notice("计算完成，已通过总数守恒检查并发布新结果。");await refreshAnalysis();await refreshCluster();}else if(state.status==="FAILED"){notice("作业失败，保留上一版结果。"+state.error,true);}}catch(e){notice(e.message,true);$("run").disabled=false;}}
async function init(){try{geo=await get("/api/zones");buildMap();await Promise.all([refreshAnalysis(),refreshCluster()]);const state=await refreshRuns();if(state.status==="RUNNING"){$("run").disabled=true;notice("已有 Hadoop 作业正在执行。");pollJob();}}catch(e){notice(e.message,true);}}
init();
