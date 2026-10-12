#!/usr/bin/env python3
"""生成智维展示网页（自包含单文件 HTML，数据内嵌，双击即可打开）.

用法:
    python build_demo_page.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_DATA = ROOT / "evidence" / "day5" / "demo-cases.json"
DEFAULT_OUT = ROOT / "app" / "zhiwei-demo.html"

HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>智维 ZHIWEI · AI 工业设备智能运维 Agent</title>
<style>
  :root{
    --bg:#0b1220; --panel:#121b2e; --panel2:#16213a; --line:#243350;
    --text:#e8eefc; --muted:#93a4c4; --cyan:#38d9d9; --green:#3ddc97;
    --amber:#ffc857; --red:#ff6b6b; --violet:#9d8cff;
  }
  *{box-sizing:border-box}
  body{margin:0;background:radial-gradient(1200px 600px at 20% -10%,#16233d 0%,var(--bg) 60%);color:var(--text);
       font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif;line-height:1.6}
  header{padding:38px 28px 22px;border-bottom:1px solid var(--line)}
  .wrap{max-width:1180px;margin:0 auto}
  h1{margin:0;font-size:30px;letter-spacing:.5px}
  h1 span{color:var(--cyan)}
  .sub{color:var(--muted);margin-top:8px;font-size:14px}
  .chips{margin-top:16px;display:flex;gap:10px;flex-wrap:wrap}
  .chip{border:1px solid var(--line);background:var(--panel);padding:6px 12px;border-radius:999px;font-size:13px;color:var(--muted)}
  .chip b{color:var(--text);font-weight:600}
  main{padding:26px 28px 60px}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-bottom:26px}
  .stat{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}
  .stat .k{color:var(--muted);font-size:13px}
  .stat .v{font-size:26px;font-weight:700;margin-top:6px}
  .stat .v small{font-size:14px;color:var(--muted);font-weight:400}
  .case{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:20px;margin-bottom:20px}
  .case-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
  .case-title{font-size:19px;font-weight:700}
  .badge{font-size:12px;padding:3px 10px;border-radius:999px;border:1px solid}
  .b-normal{color:var(--green);border-color:#2b6b52;background:#122a22}
  .b-warning{color:var(--amber);border-color:#7a6428;background:#2a2413}
  .b-critical{color:var(--red);border-color:#7a3636;background:#2a1616}
  .b-ok{color:var(--green);border-color:#2b6b52;background:#122a22}
  .b-bad{color:var(--red);border-color:#7a3636;background:#2a1616}
  .goal{color:var(--muted);font-size:14px;margin:10px 0 4px}
  .meta{display:flex;gap:18px;flex-wrap:wrap;color:var(--muted);font-size:13px;margin:10px 0 16px}
  .meta code{color:var(--cyan);background:#0e1a2e;padding:2px 6px;border-radius:6px}
  .health{display:flex;align-items:center;gap:12px;margin:6px 0 18px}
  .bar{flex:1;height:12px;background:#0d1526;border:1px solid var(--line);border-radius:999px;overflow:hidden;position:relative}
  .bar i{display:block;height:100%;background:linear-gradient(90deg,#ff6b6b,#ffc857,#3ddc97)}
  .score{font-variant-numeric:tabular-nums;font-weight:700;font-size:17px}
  .cols{display:grid;grid-template-columns:1.15fr .85fr;gap:18px}
  @media(max-width:900px){.cols{grid-template-columns:1fr}}
  .box{background:var(--panel2);border:1px solid var(--line);border-radius:14px;padding:16px}
  .box h3{margin:0 0 12px;font-size:15px;color:var(--muted);font-weight:600;letter-spacing:.4px}
  ul.tl{list-style:none;margin:0;padding:0}
  ul.tl li{position:relative;padding:0 0 16px 26px;border-left:2px solid var(--line);margin-left:8px}
  ul.tl li:last-child{border-left-color:transparent;padding-bottom:0}
  ul.tl li::before{content:"";position:absolute;left:-7px;top:5px;width:12px;height:12px;border-radius:50%;
                   background:var(--muted);box-shadow:0 0 0 3px #0f1728}
  ul.tl li.ok::before{background:var(--green)}
  ul.tl li.warn::before{background:var(--amber)}
  ul.tl li.bad::before{background:var(--red)}
  ul.tl li.info::before{background:var(--cyan)}
  .step{font-weight:600}
  .step small{color:var(--muted);font-weight:400;margin-left:8px}
  .detail{color:var(--muted);font-size:13px;margin-top:2px;word-break:break-word}
  .kv{font-size:13px;color:var(--muted);margin:6px 0}
  .kv b{color:var(--text)}
  .verdict{margin-top:14px;padding:12px 14px;border-radius:10px;background:#0e1a2e;border:1px solid var(--line);font-size:14px}
  .note{color:var(--muted);font-size:13px;margin-top:10px}
  footer{color:var(--muted);font-size:13px;border-top:1px solid var(--line);padding:20px 28px;text-align:center}
  .pipe{display:flex;gap:8px;flex-wrap:wrap;justify-content:center;margin-top:10px}
  .pipe span{border:1px solid var(--line);border-radius:8px;padding:4px 10px;background:var(--panel)}
</style>
</head>
<body>
<header>
  <div class="wrap">
    <h1>智维 <span>ZHIWEI</span> · AI 工业设备智能运维 Agent</h1>
    <div class="sub" id="sub"></div>
    <div class="chips" id="chips"></div>
  </div>
</header>
<main class="wrap">
  <div class="cards" id="stats"></div>
  <div id="cases"></div>
</main>
<footer>
  <div>执行底座 Agnes Harness (AGH) · 模型 Agnes 3.0 Flash · 工具经 MCP 调用</div>
  <div class="pipe">
    <span>数据读取</span><span>异常检测</span><span>故障诊断</span>
    <span>维修方案</span><span>模拟维修</span><span>维修后验证</span><span>失败重规划</span>
  </div>
</footer>
<script>
const DATA = __DATA__;
const STATE_CLASS = {ok:'ok',normal:'ok',healthy:'ok',success:'ok',simulated:'info',
  anomaly:'warn',warning:'warn',partial:'warn',planned:'info',diagnosed:'info',replanned:'warn',
  failed:'bad',error:'bad',repaired:'ok',recovered:'ok'};
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function sevBadge(sev){return '<span class="badge b-'+esc(sev)+'">'+esc(sev)+'</span>';}
function renderSummary(){
  document.getElementById('sub').textContent =
    DATA.asset + ' · 执行底座 ' + DATA.runtime + ' · 模型 ' + DATA.model;
  document.getElementById('chips').innerHTML =
    '<div class="chip">测试案例 <b>'+DATA.summary.total+'</b></div>'+
    '<div class="chip">通过 <b>'+DATA.summary.passed+'</b></div>'+
    '<div class="chip">通过率 <b>'+(DATA.summary.accuracy*100).toFixed(0)+'%</b></div>'+
    '<div class="chip">生成时间 <b>'+esc(DATA.generated_at)+'</b></div>';
  const cards = DATA.cases.map(c=>{
    const h=c.health||{};
    return '<div class="stat"><div class="k">'+esc(c.name)+'</div>'+
           '<div class="v">'+esc(c.status)+' <small>'+(c.attempts||0)+' 次维修</small></div>'+
           '<div class="k">健康度 '+(h.before!=null?h.before:'-')+' → '+(h.after!=null?h.after:'-')+'</div></div>';
  }).join('');
  document.getElementById('stats').innerHTML = cards;
}
function renderTimeline(tl){
  return '<ul class="tl">'+(tl||[]).map(s=>{
    const cls = STATE_CLASS[s.status]||'info';
    const d = s.detail==null?'':(typeof s.detail==='string'?s.detail:JSON.stringify(s.detail));
    return '<li class="'+cls+'"><div class="step">'+esc(s.step)+'<small>'+esc(s.status)+'</small></div>'+
           (d?'<div class="detail">'+esc(d)+'</div>':'')+'</li>';
  }).join('')+'</ul>';
}
function renderCases(){
  document.getElementById('cases').innerHTML = DATA.cases.map(c=>{
    const h=c.health||{};
    const pct = (h.after!=null? h.after : 0);
    const extra = c.misdiagnosis
      ? '<div class="kv">误判为：<b>'+esc(c.misdiagnosis.name)+'</b>（真实故障：<b>'+esc(c.true_fault_name)+'</b>）</div>'
      : '';
    const replan = c.replan ? '<div class="kv">重新规划：'+esc(c.replan)+'</div>' : '';
    return '<section class="case">'+
      '<div class="case-head"><div class="case-title">'+esc(c.id)+' · '+esc(c.name)+'</div>'+
        sevBadge(c.severity)+
        '<span class="badge '+(c.pass?'b-ok':'b-bad')+'">'+(c.pass?'PASS':'FAIL')+'</span></div>'+
      '<div class="goal">'+esc(c.goal)+'</div>'+
      '<div class="meta"><div>数据集 <code>'+esc(c.dataset)+'</code></div>'+
        '<div>维修次数 <b>'+esc(c.attempts)+'</b></div>'+
        '<div>状态 <b>'+esc(c.status)+'</b></div></div>'+
      '<div class="health"><div class="score">健康度 '+(h.before!=null?h.before:'-')+'</div>'+
        '<div class="bar"><i style="width:'+pct+'%"></i></div>'+
        '<div class="score">'+(h.after!=null?h.after:'-')+'</div></div>'+
      extra + replan +
      '<div class="cols">'+
        '<div class="box"><h3>AGENT 执行时间线</h3>'+renderTimeline(c.timeline)+'</div>'+
        '<div class="box"><h3>结论</h3><div class="verdict">'+esc(c.verdict)+'</div>'+
          '<div class="note">'+esc(c.note||'')+'</div></div>'+
      '</div></section>';
  }).join('');
}
renderSummary(); renderCases();
</script>
</body>
</html>
"""


def main() -> int:
    data_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATA
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    if not data_path.exists():
        raise SystemExit(f"缺少数据文件：{data_path}（先运行 tools/run_demo_cases.py）")

    payload = json.loads(data_path.read_text(encoding="utf-8"))
    payload.setdefault("generated_at", datetime.now().isoformat(timespec="seconds"))
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(HTML.replace("__DATA__", blob), encoding="utf-8")
    print(f"[ok] 展示页已生成: {out_path}  ({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())