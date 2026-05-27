import webview

HTML = r"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8"/>
<title>Kirloskar — Throughput Tool v1.1</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Syne:wght@400;600;700;800&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root {
  --accent:#00d4aa; --accent2:#00b4d8; --warn:#ff4757; --gold:#ffd166;
  --accent-glow:rgba(0,212,170,0.15);
  --font-d:'Syne',sans-serif; --font-m:'DM Mono',monospace; --font-b:'Inter',sans-serif;
  --r8:8px; --r12:12px; --r16:16px; --tr:0.22s cubic-bezier(.4,0,.2,1);
}
[data-theme="dark"] {
  --bg:#080c18; --sb:#0d1224; --card:#111827; --card2:#161e30; --hover:#1c2740;
  --bdr:rgba(0,212,170,0.12); --bdr2:rgba(255,255,255,0.06);
  --t1:#e8f4f0; --t2:#8ba8a0; --t3:#4a6870;
  --sh:0 4px 24px rgba(0,0,0,.5); --shg:0 0 20px rgba(0,212,170,.15),0 4px 24px rgba(0,0,0,.4);
  --grid:rgba(255,255,255,.04); --topbar:rgba(13,18,36,.96);
}
[data-theme="light"] {
  --bg:#f0f4f8; --sb:#fff; --card:#fff; --card2:#f7fafb; --hover:#eef5f3;
  --bdr:rgba(0,0,0,.08); --bdr2:rgba(0,0,0,.05);
  --t1:#0f1923; --t2:#4b6870; --t3:#94aeb8;
  --sh:0 2px 12px rgba(0,0,0,.07); --shg:0 2px 16px rgba(0,180,170,.1),0 1px 4px rgba(0,0,0,.06);
  --grid:rgba(0,0,0,.04); --topbar:rgba(255,255,255,.97);
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden;font-family:var(--font-b);background:var(--bg);color:var(--t1);font-size:13px;-webkit-font-smoothing:antialiased}
.shell{display:flex;height:100vh;overflow:hidden}

/* SIDEBAR */
.sb{width:218px;min-width:218px;background:var(--sb);border-right:1px solid var(--bdr);display:flex;flex-direction:column;transition:background var(--tr)}
[data-theme="dark"] .sb{box-shadow:2px 0 20px rgba(0,0,0,.4)}
.sb-logo{padding:20px 18px 14px;border-bottom:1px solid var(--bdr2)}
.logo{font-family:var(--font-d);font-size:22px;font-weight:800;color:var(--accent);letter-spacing:-.5px;line-height:1}
.logo span{color:var(--t1)}
.logo-sub{font-size:11px;color:var(--t3);margin-top:3px}
.sb-title-block{padding:14px 18px 8px}
.sb-title{font-family:var(--font-d);font-size:15px;font-weight:700;color:var(--t1);line-height:1.2}
.sb-ver{font-size:11px;color:var(--t3);margin-top:2px}
.nav{list-style:none;padding:6px 10px;flex:1}
.ni{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:var(--r8);cursor:pointer;color:var(--t2);font-size:13px;font-weight:500;transition:all var(--tr);position:relative;margin-bottom:2px}
.ni svg{width:16px;height:16px;flex-shrink:0;opacity:.7;transition:opacity var(--tr)}
.ni:hover{background:var(--hover);color:var(--t1)} .ni:hover svg{opacity:1}
.ni.active{background:var(--accent-glow);color:var(--accent);font-weight:600}
.ni.active svg{opacity:1;color:var(--accent)}
.ni.active::before{content:'';position:absolute;left:0;top:20%;bottom:20%;width:3px;background:var(--accent);border-radius:0 3px 3px 0}
[data-theme="dark"] .ni.active{box-shadow:inset 0 0 20px rgba(0,212,170,.06)}
.sb-foot{padding:12px 14px 16px;border-top:1px solid var(--bdr2)}
.conn-badge{display:flex;align-items:center;gap:6px;font-size:11px;font-weight:600;color:var(--accent);margin-bottom:6px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--accent);animation:pdot 2s ease-in-out infinite}
@keyframes pdot{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(.8)}}
.conn-info{font-family:var(--font-m);font-size:11px;color:var(--t2);line-height:1.8;margin-bottom:10px}
.btn-dc{width:100%;padding:7px;border-radius:var(--r8);border:1px solid var(--warn);background:rgba(255,71,87,.1);color:var(--warn);font-family:var(--font-b);font-size:12px;font-weight:600;cursor:pointer;transition:all var(--tr);letter-spacing:.3px}
.btn-dc:hover{background:var(--warn);color:#fff}

/* MAIN */
.main{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}
.topbar{height:52px;background:var(--topbar);border-bottom:1px solid var(--bdr);display:flex;align-items:center;justify-content:space-between;padding:0 20px;backdrop-filter:blur(12px);flex-shrink:0}
.live-ind{display:flex;align-items:center;gap:8px}
.live-dot{width:8px;height:8px;border-radius:50%;background:#22c55e;box-shadow:0 0 10px rgba(34,197,94,.6);animation:pdot 1.5s ease-in-out infinite}
.live-lbl{font-family:var(--font-d);font-weight:700;font-size:13px;color:var(--t1)}
.live-sub{font-size:12px;color:var(--t3);margin-left:4px}
.tbr{display:flex;align-items:center;gap:14px}
.lupd{font-family:var(--font-m);font-size:12px;color:var(--t2)}
.lupd strong{color:var(--t1);font-weight:500}
.thm-btn{width:34px;height:34px;border-radius:var(--r8);border:1px solid var(--bdr);background:var(--card);cursor:pointer;display:flex;align-items:center;justify-content:center;color:var(--t2);transition:all var(--tr);font-size:15px}
.thm-btn:hover{background:var(--hover);color:var(--accent);border-color:var(--accent)}

/* SCROLL */
.scroll{flex:1;overflow-y:auto;overflow-x:hidden;padding:16px 18px 24px;scroll-behavior:smooth}
.scroll::-webkit-scrollbar{width:5px}
.scroll::-webkit-scrollbar-thumb{background:var(--bdr);border-radius:99px}

/* CARDS */
.card{background:var(--card);border:1px solid var(--bdr);border-radius:var(--r16);box-shadow:var(--sh);transition:all var(--tr);overflow:hidden;animation:fsi .4s ease both}
[data-theme="dark"] .card{background:linear-gradient(135deg,var(--card) 0%,var(--card2) 100%)}
.card:hover{box-shadow:var(--shg);border-color:rgba(0,212,170,.22);transform:translateY(-1px)}
.ch{padding:14px 16px 0;display:flex;align-items:center;justify-content:space-between}
.ct{font-family:var(--font-d);font-size:13px;font-weight:700;color:var(--t1);letter-spacing:.1px}
.leg{display:flex;align-items:center;gap:6px;font-family:var(--font-m);font-size:11px;color:var(--t2)}
.ll{width:20px;height:2px;background:var(--accent);border-radius:2px}
.ll.warn{background:var(--warn)}

@keyframes fsi{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}

/* KPI */
.kpi-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:14px}
.kpi{background:var(--card);border:1px solid var(--bdr);border-radius:var(--r12);padding:14px 16px;box-shadow:var(--sh);transition:all var(--tr);position:relative;overflow:hidden;animation:fsi .4s ease both}
[data-theme="dark"] .kpi::after{content:'';position:absolute;inset:0;background:linear-gradient(135deg,rgba(0,212,170,.03) 0%,transparent 60%);pointer-events:none}
.kpi:hover{transform:translateY(-2px);box-shadow:var(--shg);border-color:rgba(0,212,170,.25)}
.kpi:nth-child(1){animation-delay:.02s}.kpi:nth-child(2){animation-delay:.05s}.kpi:nth-child(3){animation-delay:.08s}.kpi:nth-child(4){animation-delay:.11s}.kpi:nth-child(5){animation-delay:.14s}
.kpi-lbl{font-size:11px;color:var(--t3);font-weight:500;letter-spacing:.2px;margin-bottom:8px;display:flex;align-items:center;gap:8px}
.kpi-ico{width:28px;height:28px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:13px;flex-shrink:0}
.ic-t{background:rgba(0,212,170,.12);color:var(--accent)}
.ic-b{background:rgba(0,180,216,.12);color:var(--accent2)}
.ic-w{background:rgba(255,71,87,.12);color:var(--warn)}
.ic-g{background:rgba(255,209,102,.12);color:var(--gold)}
.kpi-val{font-family:var(--font-d);font-size:26px;font-weight:800;color:var(--t1);line-height:1;letter-spacing:-1px}
.kpi-unit{font-size:11px;color:var(--t3);margin-top:3px}

/* GRIDS */
.g2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}
.g31{display:grid;grid-template-columns:1fr 1fr 316px;gap:12px;margin-bottom:14px}
.g21{display:grid;grid-template-columns:1fr 376px;gap:12px;margin-bottom:14px}

/* CHART WRAP */
.cw{padding:10px 14px 14px;position:relative}
canvas{display:block;width:100%!important}

/* ANOMALY TABLE */
.ah{padding:14px 16px 0;display:flex;align-items:center;gap:8px;margin-bottom:10px}
.aw-ico{color:var(--warn);font-size:14px}
.tw{padding:0 0 6px;overflow-y:auto;max-height:200px}
.tw::-webkit-scrollbar{width:3px}
.tw::-webkit-scrollbar-thumb{background:var(--bdr);border-radius:99px}
.et{width:100%;border-collapse:collapse;font-family:var(--font-m);font-size:11px}
.et thead tr{border-bottom:1px solid var(--bdr)}
.et th{padding:6px 14px;text-align:left;font-size:10px;font-weight:600;letter-spacing:.8px;text-transform:uppercase;color:var(--t3);font-family:var(--font-b)}
.et td{padding:7px 14px;color:var(--t2);border-bottom:1px solid var(--bdr2);transition:color var(--tr)}
.et tbody tr:hover td{color:var(--t1);background:var(--hover)}
.et tbody tr:last-child td{border-bottom:none}
.badge{display:inline-block;padding:2px 7px;border-radius:99px;font-size:10px;font-weight:600;font-family:var(--font-b)}
.badge.spike{background:rgba(255,71,87,.12);color:var(--warn)}
.badge.threshold{background:rgba(255,209,102,.15);color:var(--gold)}
.badge.critical{background:rgba(255,71,87,.25);color:#ff8fa3}

/* STATUS */
.sc{padding:14px 16px}
.st{font-family:var(--font-d);font-size:13px;font-weight:700;color:var(--t1);margin-bottom:12px}
.srows{display:flex;flex-direction:column;gap:8px;margin-bottom:14px}
.sr{display:flex;align-items:center;justify-content:space-between;font-size:12px}
.sk{display:flex;align-items:center;gap:6px;color:var(--t3)}
.sk svg{width:13px;height:13px;color:var(--accent);opacity:.7}
.sv{font-family:var(--font-m);font-size:12px;color:var(--t1);font-weight:500}
.sig-wrap{height:56px;position:relative;background:var(--card2);border-radius:var(--r8);overflow:hidden;border:1px solid var(--bdr2)}

/* HEATMAP */
.hm-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:3px;padding:10px 14px 14px}
.hm-cell{aspect-ratio:1;border-radius:4px;transition:all .4s ease;cursor:crosshair;position:relative}
.hm-cell:hover::after{content:attr(data-v);position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-family:var(--font-m);font-size:9px;color:rgba(255,255,255,.9);font-weight:600;pointer-events:none}
.hm-leg{display:flex;align-items:center;gap:8px;padding:0 14px 10px;font-family:var(--font-m);font-size:10px;color:var(--t3)}
.hm-bar{flex:1;height:6px;border-radius:99px;background:linear-gradient(90deg,#1a3a6e 0%,#0ea5e9 30%,#22c55e 55%,#f59e0b 75%,#ef4444 100%)}
* {scrollbar-width:thin;scrollbar-color:var(--bdr) transparent}
</style>
</head>
<body>
<div class="shell">

<!-- SIDEBAR -->
<aside class="sb">
  <div class="sb-logo">
    <div class="logo"><span>k</span>irlokar</div>
    <div class="logo-sub">Oil Engines</div>
  </div>
  <div class="sb-title-block">
    <div class="sb-title">Throughput</div>
    <div class="sb-ver">Tool v1.1</div>
  </div>
  <nav><ul class="nav">
    <li class="ni active" onclick="setNav(this)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>Dashboard</li>
    <li class="ni" onclick="setNav(this)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg>Live Monitor</li>
    <li class="ni" onclick="setNav(this)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>Latency</li>
    <li class="ni" onclick="setNav(this)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>Analysis</li>
    <li class="ni" onclick="setNav(this)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>Reports</li>
    <li class="ni" onclick="setNav(this)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>Data Export</li>
    <li class="ni" onclick="setNav(this)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/></svg>Settings</li>
  </ul></nav>
  <div class="sb-foot">
    <div class="conn-badge"><div class="dot"></div><span>Connected</span></div>
    <div class="conn-info">COM5<br>115200 bps<br>00:12:45</div>
    <button class="btn-dc">Disconnect</button>
  </div>
</aside>

<!-- MAIN -->
<main class="main">
  <header class="topbar">
    <div class="live-ind">
      <div class="live-dot"></div>
      <span class="live-lbl">Live Monitoring</span>
      <span class="live-sub">Receiving data...</span>
    </div>
    <div class="tbr">
      <div class="lupd">Last Update: <strong>12:45:30 PM</strong></div>
      <button class="thm-btn" onclick="toggleTheme()" id="thm-btn">🌙</button>
      <div style="font-size:11px;color:var(--t3);font-family:var(--font-m)">v1.1</div>
    </div>
  </header>

  <div class="scroll">

    <!-- KPI ROW -->
    <div class="kpi-grid">
      <div class="kpi">
        <div class="kpi-lbl"><div class="kpi-ico ic-t">⟳</div>Current Throughput</div>
        <div class="kpi-val">492.6</div><div class="kpi-unit">frames/sec</div>
      </div>
      <div class="kpi">
        <div class="kpi-lbl"><div class="kpi-ico ic-b">⇌</div>Average Throughput</div>
        <div class="kpi-val">487.3</div><div class="kpi-unit">frames/sec</div>
      </div>
      <div class="kpi">
        <div class="kpi-lbl"><div class="kpi-ico ic-b">◔</div>Max Latency</div>
        <div class="kpi-val">2,350</div><div class="kpi-unit">μs</div>
      </div>
      <div class="kpi">
        <div class="kpi-lbl"><div class="kpi-ico ic-w">⚠</div>Anomalies Detected</div>
        <div class="kpi-val">12</div><div class="kpi-unit">events</div>
      </div>
      <div class="kpi">
        <div class="kpi-lbl"><div class="kpi-ico ic-t">≡</div>Total Frames</div>
        <div class="kpi-val" style="font-size:20px">145,672</div><div class="kpi-unit">frames</div>
      </div>
    </div>

    <!-- ROW 2 -->
    <div class="g2">
      <div class="card">
        <div class="ch"><span class="ct">Throughput (Frames per Second)</span><div class="leg"><div class="ll"></div>Throughput</div></div>
        <div class="cw"><canvas id="c-tp" height="120"></canvas></div>
      </div>
      <div class="card">
        <div class="ch"><span class="ct">Latency Trend (μs)</span><div class="leg"><div class="ll"></div>Latency (μs)</div></div>
        <div class="cw"><canvas id="c-lt" height="120"></canvas></div>
      </div>
    </div>

    <!-- ROW 3 -->
    <div class="g31">
      <div class="card">
        <div class="ch"><span class="ct">Latency Distribution</span></div>
        <div class="cw"><canvas id="c-dist" height="132"></canvas></div>
      </div>
      <div class="card">
        <div class="ch" style="margin-bottom:4px"><span class="ct">Anomaly Heatmap (Latency)</span></div>
        <div class="hm-leg"><span>0</span><div class="hm-bar"></div><span>100</span></div>
        <div class="hm-grid" id="hm"></div>
      </div>
      <div class="card">
        <div class="ah"><span class="aw-ico">⚠</span><span class="ct">Anomaly Events</span></div>
        <div class="tw"><table class="et">
          <thead><tr><th>Time</th><th>Latency (μs)</th><th>Type</th></tr></thead>
          <tbody id="etb"></tbody>
        </table></div>
      </div>
    </div>

    <!-- ROW 4 -->
    <div class="g21">
      <div class="card">
        <div class="ch"><span class="ct">Frame Rate Trend (Rolling Average)</span><div class="leg"><div class="ll"></div>Rolling Avg (10s)</div></div>
        <div class="cw"><canvas id="c-ra" height="100"></canvas></div>
      </div>
      <div class="card">
        <div class="sc">
          <div class="st">System &amp; Communication Status</div>
          <div class="srows">
            <div class="sr"><div class="sk"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="10" rx="2"/><circle cx="8" cy="12" r="1.5" fill="currentColor"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/><circle cx="16" cy="12" r="1.5" fill="currentColor"/></svg>Serial Port</div><div class="sv">COM5</div></div>
            <div class="sr"><div class="sk"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>Baud Rate</div><div class="sv">115200 bps</div></div>
            <div class="sr"><div class="sk"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>Data Rate</div><div class="sv">500 frames/sec</div></div>
            <div class="sr"><div class="sk"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>Protocol</div><div class="sv">Binary</div></div>
            <div class="sr"><div class="sk"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>Status</div><div class="sv">Receiving</div></div>
          </div>
          <div class="sig-wrap"><canvas id="c-sig" style="width:100%;height:56px"></canvas></div>
        </div>
      </div>
    </div>

  </div><!-- /scroll -->
</main>
</div>

<script>
/* ── STATIC DATA ── */
const TP = [350,370,410,430,400,460,480,510,490,470,500,520,540,510,480,460,490,510,530,500,470,450,480,500,520,540,510,480,460,490,510,530,550,520,490,470,500,480,510,530,500,470,450,490,510,520,500,480,510,530,500,470,490,510,520,500,480,510,490,470];
const LAT = [900,1100,1300,800,900,2200,1000,1100,900,800,1000,2800,1200,900,800,1100,900,2100,1000,800,900,1100,1000,900,800,2300,1000,1100,900,800,900,1100,3100,900,800,1000,1100,900,800,2200,1000,900,1100,900,800,1000,2400,900,800,1000,1100,900,2000,800,1000,1100,900,800,2300,1000,900];
const DIST_V = [250, 3800, 2600, 1700, 750, 220];
const DIST_L = ['0–500','500–1000','1000–1500','1500–2000','2000–2500','2500+'];
const HMAP = [[5,8,12,15,10,6],[10,25,40,50,35,18],[15,45,80,95,72,30],[12,42,85,100,68,25],[8,22,38,45,30,14],[4,7,10,12,8,5]];
const EVENTS = [
  {t:'12:45:18',l:2315,ty:'Spike'},{t:'12:45:12',l:2102,ty:'Spike'},
  {t:'12:44:58',l:2453,ty:'Spike'},{t:'12:44:31',l:2005,ty:'Threshold'},
  {t:'12:44:10',l:2250,ty:'Spike'},{t:'12:43:55',l:2189,ty:'Spike'},
  {t:'12:43:22',l:2601,ty:'Spike'},{t:'12:43:01',l:2088,ty:'Threshold'},
  {t:'12:42:47',l:3100,ty:'Critical'},{t:'12:42:15',l:2344,ty:'Spike'},
  {t:'12:41:58',l:2012,ty:'Threshold'},{t:'12:41:30',l:2890,ty:'Spike'},
];
const XLABELS = ['12:40:00','12:41:00','12:42:00','12:43:00','12:44:00','12:45:00'];

/* ── THEME ── */
let theme = 'dark';
function toggleTheme() {
  theme = theme==='dark'?'light':'dark';
  document.documentElement.setAttribute('data-theme',theme);
  document.getElementById('thm-btn').textContent = theme==='dark'?'🌙':'☀️';
  drawAll();
}

/* ── NAV ── */
function setNav(el){document.querySelectorAll('.ni').forEach(n=>n.classList.remove('active'));el.classList.add('active')}

/* ── COLOR HELPERS ── */
function C(){
  const d=theme==='dark';
  return {
    accent:'#00d4aa', accent2:'#00b4d8', warn:'#ff4757',
    grid: d?'rgba(255,255,255,.04)':'rgba(0,0,0,.04)',
    txt:  d?'rgba(232,244,240,.5)':'rgba(15,25,35,.4)',
    fill: d?'rgba(0,212,170,.08)':'rgba(0,212,170,.07)',
    fillW:d?'rgba(255,71,87,.07)':'rgba(255,71,87,.05)',
    bg:   d?'#111827':'#ffffff',
  };
}

/* ── CANVAS INIT ── */
function initC(id, hpx) {
  const el=document.getElementById(id); if(!el)return null;
  const dpr=window.devicePixelRatio||1;
  const W=el.parentElement.getBoundingClientRect().width-28;
  const H=hpx||120;
  el.width=W*dpr; el.height=H*dpr;
  el.style.width=W+'px'; el.style.height=H+'px';
  const ctx=el.getContext('2d'); ctx.scale(dpr,dpr);
  return {ctx,W,H};
}

/* ── SHARED DRAW UTILS ── */
function grid(ctx,W,H,steps,c,padB){
  const pb=padB||14;
  ctx.strokeStyle=c.grid; ctx.lineWidth=1;
  for(let i=0;i<=steps;i++){const y=8+(H-pb-8)*(i/steps);ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(W,y);ctx.stroke()}
}
function yLabels(ctx,W,H,min,max,steps,c,padB){
  const pb=padB||14;
  ctx.fillStyle=c.txt; ctx.font='10px DM Mono,monospace'; ctx.textAlign='right';
  for(let i=0;i<=steps;i++){const v=max-(max-min)*i/steps; const y=8+(H-pb-8)*(i/steps);
    ctx.fillText(v>=1000?(v/1000).toFixed(0)+'K':Math.round(v),34,y+3)}
}
function pts(data,W,H,min,max,pL,padB){
  const pb=padB||14; const n=data.length;
  return data.map((v,i)=>({x:pL+(W-pL)*(i/(n-1)),y:8+(H-pb-8)*(1-(v-min)/(max-min))}));
}
function line(ctx,pts,color,glow,lw){
  if(pts.length<2)return;
  ctx.save();
  if(glow&&theme==='dark'){ctx.shadowColor=color;ctx.shadowBlur=8}
  ctx.strokeStyle=color; ctx.lineWidth=lw||1.8; ctx.lineJoin='round'; ctx.lineCap='round';
  ctx.beginPath(); ctx.moveTo(pts[0].x,pts[0].y);
  for(let i=1;i<pts.length;i++){const cx=(pts[i-1].x+pts[i].x)/2;ctx.bezierCurveTo(cx,pts[i-1].y,cx,pts[i].y,pts[i].x,pts[i].y)}
  ctx.stroke(); ctx.restore();
}
function fill(ctx,pts,W,H,color,padB){
  const pb=padB||14;
  if(pts.length<2)return; ctx.save(); ctx.beginPath();
  ctx.moveTo(pts[0].x,pts[0].y);
  for(let i=1;i<pts.length;i++){const cx=(pts[i-1].x+pts[i].x)/2;ctx.bezierCurveTo(cx,pts[i-1].y,cx,pts[i].y,pts[i].x,pts[i].y)}
  ctx.lineTo(pts[pts.length-1].x,H-pb); ctx.lineTo(pts[0].x,H-pb); ctx.closePath();
  const g=ctx.createLinearGradient(0,8,0,H-pb); g.addColorStop(0,color); g.addColorStop(1,'rgba(0,0,0,0)');
  ctx.fillStyle=g; ctx.fill(); ctx.restore();
}
function xLabels(ctx,W,H,pL,labels,padB){
  const pb=padB||14;
  ctx.fillStyle=C().txt; ctx.font='10px DM Mono,monospace'; ctx.textAlign='center';
  labels.forEach((l,i)=>{const x=pL+(W-pL)*(i/(labels.length-1));ctx.fillText(l,x,H-2)});
}

/* ── SPECIFIC CHARTS ── */
function drawTP(){
  const cv=initC('c-tp',120); if(!cv)return; const {ctx,W,H}=cv; const c=C(); ctx.clearRect(0,0,W,H);
  grid(ctx,W,H,4,c); yLabels(ctx,W,H,0,800,4,c);
  const p=pts(TP,W,H,0,800,38); fill(ctx,p,W,H,c.fill); line(ctx,p,c.accent,true);
  xLabels(ctx,W,H,38,XLABELS);
}

function drawLT(){
  const cv=initC('c-lt',120); if(!cv)return; const {ctx,W,H}=cv; const c=C(); ctx.clearRect(0,0,W,H);
  grid(ctx,W,H,4,c); yLabels(ctx,W,H,0,4000,4,c);
  // threshold line
  const ty=8+(H-14-8)*(1-2000/4000);
  ctx.save(); ctx.strokeStyle='rgba(255,71,87,.55)'; ctx.lineWidth=1; ctx.setLineDash([4,4]);
  ctx.beginPath(); ctx.moveTo(38,ty); ctx.lineTo(W,ty); ctx.stroke(); ctx.setLineDash([]);
  ctx.fillStyle='rgba(255,71,87,.7)'; ctx.font='10px DM Mono,monospace'; ctx.textAlign='right';
  ctx.fillText('Threshold: 2000 μs',W-2,ty-4); ctx.restore();
  const p=pts(LAT,W,H,0,4000,38); fill(ctx,p,W,H,c.fillW); line(ctx,p,c.accent2,true);
  // spike dots
  p.forEach((pt,i)=>{if(LAT[i]>2000){ctx.save();ctx.fillStyle='#ff4757';if(theme==='dark'){ctx.shadowColor='#ff4757';ctx.shadowBlur=10}ctx.beginPath();ctx.arc(pt.x,pt.y,4,0,Math.PI*2);ctx.fill();ctx.restore()}});
  xLabels(ctx,W,H,38,XLABELS);
}

function drawDist(){
  const cv=initC('c-dist',132); if(!cv)return; const {ctx,W,H}=cv; const c=C(); ctx.clearRect(0,0,W,H);
  const pL=38, pB=22;
  const cW=W-pL-8, cH=H-pB-8, maxV=Math.max(...DIST_V);
  grid(ctx,W,H,4,c,pB); yLabels(ctx,W,H,0,maxV,4,c,pB);
  const bW=(cW/DIST_V.length)*.64, gap=(cW/DIST_V.length)*.36;
  DIST_V.forEach((v,i)=>{
    const x=pL+(cW/DIST_V.length)*i+gap/2, bH=(v/maxV)*cH, y=8+cH-bH;
    ctx.save(); if(theme==='dark'){ctx.shadowColor=c.accent;ctx.shadowBlur=6}
    const g=ctx.createLinearGradient(0,y,0,y+bH); g.addColorStop(0,c.accent); g.addColorStop(1,'rgba(0,212,170,.2)');
    ctx.fillStyle=g; const r=Math.min(4,bW/2);
    ctx.beginPath(); ctx.moveTo(x+r,y); ctx.lineTo(x+bW-r,y); ctx.quadraticCurveTo(x+bW,y,x+bW,y+r);
    ctx.lineTo(x+bW,y+bH); ctx.lineTo(x,y+bH); ctx.lineTo(x,y+r); ctx.quadraticCurveTo(x,y,x+r,y); ctx.closePath(); ctx.fill(); ctx.restore();
    ctx.fillStyle=c.txt; ctx.font='9px DM Mono,monospace'; ctx.textAlign='center';
    ctx.fillText(DIST_L[i],x+bW/2,H-5);
  });
}

function drawRA(){
  const cv=initC('c-ra',100); if(!cv)return; const {ctx,W,H}=cv; const c=C(); ctx.clearRect(0,0,W,H);
  const ra=TP.map((v,i)=>{const s=Math.max(0,i-9);return TP.slice(s,i+1).reduce((a,b)=>a+b,0)/(i-s+1)});
  grid(ctx,W,H,4,c); yLabels(ctx,W,H,0,800,4,c);
  const p=pts(ra,W,H,0,800,38); fill(ctx,p,W,H,c.fill); line(ctx,p,c.accent,true);
  xLabels(ctx,W,H,38,XLABELS);
}

function drawSig(){
  const el=document.getElementById('c-sig'); if(!el)return;
  const dpr=window.devicePixelRatio||1, W=el.parentElement.clientWidth, H=56;
  el.width=W*dpr; el.height=H*dpr; el.style.width=W+'px'; el.style.height=H+'px';
  const ctx=el.getContext('2d'); ctx.scale(dpr,dpr); const c=C(); ctx.clearRect(0,0,W,H);
  const pat=[1,1,0,0,1,1,1,0,1,0,1,1,0,0,1,1,0,1,0,1];
  const sw=W/pat.length;
  ctx.save(); ctx.strokeStyle=c.accent; ctx.lineWidth=1.5;
  if(theme==='dark'){ctx.shadowColor=c.accent;ctx.shadowBlur=5}
  ctx.beginPath(); ctx.moveTo(0,pat[0]?H*.25:H*.75);
  pat.forEach((v,i)=>{const x=sw*i,nx=sw*(i+1),y=v?H*.25:H*.75;ctx.lineTo(x,y);ctx.lineTo(nx,y)});
  ctx.stroke(); ctx.restore();
  ctx.fillStyle=c.txt; ctx.font='9px DM Mono,monospace'; ctx.textAlign='right';
  ctx.fillText('1',W-4,H*.25+3); ctx.fillText('0',W-4,H*.75+3);
}

/* ── HEATMAP ── */
function drawHM(){
  const g=document.getElementById('hm'); if(!g)return; g.innerHTML='';
  HMAP.forEach(row=>row.forEach(v=>{
    const c=document.createElement('div'); c.className='hm-cell'; c.setAttribute('data-v',v);
    const pct=v/100;
    const r=pct<.2?26:pct<.4?14:pct<.6?34:pct<.8?245:239;
    const gv=pct<.2?58:pct<.4?165:pct<.6?197:pct<.8?158:68;
    const b=pct<.2?110:pct<.4?233:pct<.6?94:pct<.8?11:68;
    const a=.2+pct*.7;
    c.style.background=`rgba(${r},${gv},${b},${a})`;
    g.appendChild(c);
  }));
}

/* ── ANOMALY TABLE ── */
function drawET(){
  const tb=document.getElementById('etb'); if(!tb)return; tb.innerHTML='';
  EVENTS.forEach(e=>{
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${e.t}</td><td>${e.l.toLocaleString()}</td><td><span class="badge ${e.ty.toLowerCase()}">${e.ty}</span></td>`;
    tb.appendChild(tr);
  });
}

/* ── DRAW ALL ── */
function drawAll(){
  drawTP(); drawLT(); drawDist(); drawRA(); drawSig(); drawHM(); drawET();
}

window.addEventListener('load',()=>{
  drawAll();
  const ro=new ResizeObserver(()=>drawAll());
  ro.observe(document.querySelector('.scroll'));
});
</script>
</body>
</html>"""

def main():
    window = webview.create_window(
        title="Kirloskar Oil Engines — Throughput Tool v2.1",
        html=HTML,
        width=1440,
        height=900,
        min_size=(1100, 700),
        resizable=True,
        background_color="#080c18"
    )
    webview.start()

if __name__ == "__main__":
    main()
