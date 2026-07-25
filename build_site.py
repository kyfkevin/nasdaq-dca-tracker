"""
Render the static site (index.html + assets) from data/portfolio.csv.

Sections:
  1. Header / latest snapshot card
  2. Three key metric cards
  3. P&L curve (Chart.js) — line of cumulative invested vs market value over time
  4. Daily return bar (Chart.js) — daily P&L %
  5. Monthly breakdown table — selectable per month
  6. Per-ticker price cards (today's open/close)
  7. Footer

All Chinese, finance-style cards, mobile responsive.
"""
from __future__ import annotations
import os
import json
from datetime import datetime, date
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
SITE_DIR = os.path.join(ROOT, "site")
os.makedirs(SITE_DIR, exist_ok=True)


def load_data():
    pf_path = os.path.join(DATA_DIR, "portfolio.csv")
    if not os.path.exists(pf_path):
        raise SystemExit("portfolio.csv not found -- run dca_engine.py first")
    pf = pd.read_csv(pf_path)
    pf["date"] = pd.to_datetime(pf["date"]).dt.date
    pf = pf.sort_values("date").reset_index(drop=True)
    # load latest close per ticker
    last = pf.iloc[-1]
    closes = {
        "QQQ":  float(last["QQQ_close"]),
        "QLD":  float(last["QLD_close"]),
        "TQQQ": float(last["TQQQ_close"]),
    }
    opens = {
        "QQQ":  float(last["QQQ_open"]),
        "QLD":  float(last["QLD_open"]),
        "TQQQ": float(last["TQQQ_open"]),
    }
    return pf, opens, closes, last


def fmt_money(v: float) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    sign = "+" if v >= 0 else ""
    return f"¥{sign}{v:,.2f}"


def fmt_pct(v: float) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v*100:.2f}%"


def main():
    pf, opens, closes, last = load_data()
    if pf.empty:
        raise SystemExit("portfolio is empty")

    # Build chart data
    labels  = [d.isoformat() for d in pf["date"]]
    cum_in  = pf["cum_cny_invested"].astype(float).tolist()
    val     = pf["total_cny_value"].astype(float).tolist()
    pnl     = pf["pnl_cny"].astype(float).tolist()
    pnl_pct = pf["pnl_ratio"].astype(float).tolist()
    # daily return is total_today / total_yesterday - 1
    daily_ret = [0.0]
    for i in range(1, len(val)):
        prev = val[i-1] if val[i-1] else 1.0
        daily_ret.append(val[i] / prev - 1.0)

    # monthly aggregation
    pf["month"] = pd.to_datetime(pf["date"]).dt.strftime("%Y-%m")
    months = sorted(pf["month"].unique())

    # JSON for the front-end JS
    chart_data = {
        "labels": labels,
        "cum_invested": cum_in,
        "value": val,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "daily_return": daily_ret,
        "months": [{"value": m, "label": m} for m in months],
    }

    # KPI numbers
    today_cny_invested = float(last["cum_cny_invested"])
    today_cny_value     = float(last["total_cny_value"])
    today_pnl_cny       = float(last["pnl_cny"])
    today_pnl_ratio     = float(last["pnl_ratio"])
    days_so_far         = len(pf)
    avg_daily_cny       = today_cny_invested / days_so_far if days_so_far else 0.0

    # Generate HTML
    html = render_html(chart_data, opens, closes, last,
                      today_cny_invested, today_cny_value,
                      today_pnl_cny, today_pnl_ratio,
                      days_so_far, avg_daily_cny, pf)

    out = os.path.join(SITE_DIR, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  + site/index.html ({len(html)/1024:.1f} KB)")
    # also copy data as JSON for the page
    out2 = os.path.join(SITE_DIR, "data.json")
    with open(out2, "w", encoding="utf-8") as f:
        json.dump({
            "chart": chart_data,
            "latest": {
                "date": last["date"].isoformat() if hasattr(last["date"], "isoformat") else str(last["date"]),
                "opens": opens,
                "closes": closes,
                "cum_cny_invested": today_cny_invested,
                "total_cny_value":   today_cny_value,
                "pnl_cny":           today_pnl_cny,
                "pnl_ratio":         today_pnl_ratio,
                "shares": {
                    "QQQ":  float(last["shares_QQQ"]),
                    "QLD":  float(last["shares_QLD"]),
                    "TQQQ": float(last["shares_TQQQ"]),
                },
            }
        }, f, ensure_ascii=False, indent=2)
    print(f"  + site/data.json")


def render_html(chart_data, opens, closes, last,
                cum_invested, total_value, pnl_cny, pnl_ratio,
                days_so_far, avg_daily_cny, pf) -> str:
    today = last["date"].isoformat() if hasattr(last["date"], "isoformat") else str(last["date"])
    color_pnl = "#2f6f5e" if pnl_cny >= 0 else "#b06367"

    # build per-month subtable for the default month
    pf_disp = pf.copy()
    pf_disp["date"] = pd.to_datetime(pf_disp["date"]).dt.strftime("%Y-%m-%d")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>每日定投追踪 · QQQ/QLD/TQQQ</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
  <style>
    :root {{
      --bg: #f6f4ee;
      --surface: #ffffff;
      --line: #e9e3d6;
      --line-soft: #f0eadb;
      --text: #14171e;
      --text-soft: #3a4256;
      --text-mute: #7c7a72;
      --primary: #2f6f5e;
      --accent: #c97b3f;
      --q: #1f77b4;  /* QQQ blue */
      --l: #d62728;  /* QLD red */
      --t: #2ca02c;  /* TQQQ green */
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; background: var(--bg); color: var(--text);
      font-family: 'Outfit', -apple-system, 'PingFang SC', sans-serif;
      font-size: 14px; line-height: 1.6; -webkit-font-smoothing: antialiased; }}
    body {{ background: radial-gradient(ellipse 800px 600px at 90% -10%, rgba(47,111,94,0.05), transparent 60%), var(--bg); }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 28px 24px 80px; }}
    .header {{ display: flex; align-items: center; justify-content: space-between;
      padding-bottom: 14px; margin-bottom: 24px; border-bottom: 1px solid var(--line);
      flex-wrap: wrap; gap: 12px; }}
    .header h1 {{ font-size: 22px; margin: 0; font-weight: 600; letter-spacing: -0.01em; }}
    .header .meta {{ color: var(--text-mute); font-size: 12.5px; }}
    .header .pill {{ background: rgba(47,111,94,0.10); color: var(--primary);
      padding: 3px 10px; border-radius: 100px; font-size: 12px; font-weight: 500; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }}
    .kpi {{ background: var(--surface); border: 1px solid var(--line); border-radius: 14px;
      padding: 16px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.03); }}
    .kpi .lbl {{ font-size: 11.5px; color: var(--text-mute); text-transform: uppercase;
      letter-spacing: 0.08em; margin-bottom: 4px; }}
    .kpi .val {{ font-size: 24px; font-weight: 600; line-height: 1.2; }}
    .kpi .sub {{ font-size: 12.5px; color: var(--text-mute); margin-top: 4px; }}
    .price-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }}
    .price {{ background: var(--surface); border: 1px solid var(--line); border-radius: 14px;
      padding: 16px 18px; border-top: 3px solid var(--q); }}
    .price.ql {{ border-top-color: var(--l); }}
    .price.tq {{ border-top-color: var(--t); }}
    .price .name {{ font-size: 14px; color: var(--text-soft); font-weight: 600; letter-spacing: 0.04em; }}
    .price .px {{ font-size: 22px; font-weight: 600; margin: 4px 0 2px; }}
    .price .detail {{ display: flex; gap: 14px; font-size: 12.5px; color: var(--text-mute); }}
    .price .detail b {{ color: var(--text-soft); font-weight: 500; }}
    .section {{ background: var(--surface); border: 1px solid var(--line); border-radius: 14px;
      padding: 20px 22px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.03); }}
    .section h2 {{ font-size: 16px; font-weight: 600; margin: 0 0 12px;
      display: flex; align-items: center; gap: 8px; }}
    .section h2 .hint {{ font-size: 12px; color: var(--text-mute); font-weight: 400; }}
    .chart-wrap {{ position: relative; height: 320px; }}
    .chart-wrap.small {{ height: 220px; }}
    .ctrl-row {{ display: flex; gap: 10px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }}
    .ctrl-row label {{ font-size: 13px; color: var(--text-soft); }}
    .ctrl-row select, .ctrl-row input {{ background: var(--bg); border: 1px solid var(--line);
      padding: 5px 10px; border-radius: 6px; font-size: 13px; color: var(--text); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 7px 10px; text-align: right; border-bottom: 1px solid var(--line-soft); }}
    th {{ background: #f4eedf; color: var(--text); font-weight: 600; font-size: 12px; letter-spacing: 0.04em; text-align: center; }}
    th:first-child, td:first-child {{ text-align: left; }}
    td.pos {{ color: #2f6f5e; }}
    td.neg {{ color: #b06367; }}
    tr:hover td {{ background: #faf6ea; }}
    .footer {{ margin-top: 36px; padding-top: 14px; border-top: 1px solid var(--line);
      color: var(--text-mute); font-size: 12px; text-align: center; line-height: 1.7; }}
    .badge {{ display: inline-block; padding: 1px 7px; border-radius: 4px; font-size: 11px; font-weight: 500; }}
    .badge.q {{ background: rgba(31,119,180,0.12); color: #1f6da4; }}
    .badge.l {{ background: rgba(214,39,40,0.12); color: #b0202f; }}
    .badge.t {{ background: rgba(44,160,44,0.12); color: #208020; }}
    @media (max-width: 800px) {{
      .kpi-grid {{ grid-template-columns: 1fr 1fr; }}
      .price-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
<div class="wrap">

  <div class="header">
    <div>
      <h1>每日定投追踪 <span class="pill">自动更新</span></h1>
      <div class="meta">起始 <b>2026-07-22</b> · 每日 ¥100 QQQ + ¥200 QLD + ¥300 TQQQ · 数据源：腾讯财经 / qt.gtimg.cn</div>
    </div>
    <div class="meta">
      截至 <b id="asof">{today}</b> · 已运行 <b id="days">{days_so_far}</b> 个交易日<br/>
      <span style="font-size: 11.5px;">每日 16:30 ET 后自动更新</span>
    </div>
  </div>

  <div class="kpi-grid">
    <div class="kpi">
      <div class="lbl">累计投入</div>
      <div class="val" id="kpi-invested">¥{cum_invested:,.2f}</div>
      <div class="sub">日均 ¥{avg_daily_cny:,.2f}</div>
    </div>
    <div class="kpi">
      <div class="lbl">当前市值</div>
      <div class="val" id="kpi-value" style="color: {color_pnl};">¥{total_value:,.2f}</div>
      <div class="sub">按 1 USD = 7.2 CNY 折算</div>
    </div>
    <div class="kpi">
      <div class="lbl">累计盈亏</div>
      <div class="val" id="kpi-pnl" style="color: {color_pnl};">{fmt_money(pnl_cny)}</div>
      <div class="sub" id="kpi-pnl-pct">{fmt_pct(pnl_ratio)}</div>
    </div>
    <div class="kpi">
      <div class="lbl">盈亏比</div>
      <div class="val" id="kpi-ratio" style="color: {color_pnl};">{fmt_pct(pnl_ratio)}</div>
      <div class="sub">累计盈亏 / 累计投入</div>
    </div>
  </div>

  <div class="price-grid">
    <div class="price">
      <div class="name"><span class="badge q">QQQ</span> · Invesco QQQ Trust</div>
      <div class="px" id="q-close">${closes['QQQ']:.2f}</div>
      <div class="detail">
        <div>开 <b>${opens['QQQ']:.2f}</b></div>
        <div>收 <b>${closes['QQQ']:.2f}</b></div>
        <div>持有 <b id="q-shares">{last['shares_QQQ']:.4f}</b> 股</div>
      </div>
    </div>
    <div class="price ql">
      <div class="name"><span class="badge l">QLD</span> · ProShares Ultra QQQ (2×)</div>
      <div class="px" id="l-close">${closes['QLD']:.2f}</div>
      <div class="detail">
        <div>开 <b>${opens['QLD']:.2f}</b></div>
        <div>收 <b>${closes['QLD']:.2f}</b></div>
        <div>持有 <b id="l-shares">{last['shares_QLD']:.4f}</b> 股</div>
      </div>
    </div>
    <div class="price tq">
      <div class="name"><span class="badge t">TQQQ</span> · ProShares UltraPro QQQ (3×)</div>
      <div class="px" id="t-close">${closes['TQQQ']:.2f}</div>
      <div class="detail">
        <div>开 <b>${opens['TQQQ']:.2f}</b></div>
        <div>收 <b>${closes['TQQQ']:.2f}</b></div>
        <div>持有 <b id="t-shares">{last['shares_TQQQ']:.4f}</b> 股</div>
      </div>
    </div>
  </div>

  <div class="section">
    <h2>📈 累计投入 vs 账户市值 <span class="hint">（对数刻度可选）</span></h2>
    <div class="ctrl-row">
      <label>Y 轴：<select id="curve-scale">
        <option value="linear">线性</option>
        <option value="logarithmic">对数</option>
      </select></label>
    </div>
    <div class="chart-wrap"><canvas id="curveChart"></canvas></div>
  </div>

  <div class="section">
    <h2>📊 每日收益 <span class="hint">（柱状：每日盈亏金额 / % 切换）</span></h2>
    <div class="ctrl-row">
      <label>显示：<select id="daily-mode">
        <option value="amount">每日盈亏金额 (¥)</option>
        <option value="pct">每日盈亏比率 (%)</option>
      </select></label>
    </div>
    <div class="chart-wrap small"><canvas id="dailyChart"></canvas></div>
  </div>

  <div class="section">
    <h2>📅 每月每日明细 <span class="hint">（选择月份查看每日收益）</span></h2>
    <div class="ctrl-row">
      <label>选择月份：<select id="month-select"></select></label>
      <label>显示：<select id="month-mode">
        <option value="pct">每日收益率 (%)</option>
        <option value="amount">每日盈亏金额 (¥)</option>
      </select></label>
    </div>
    <div class="chart-wrap small"><canvas id="monthlyChart"></canvas></div>
    <div id="month-table-wrap" style="margin-top: 16px; overflow-x: auto;"></div>
  </div>

  <div class="footer">
    起始 2026-07-22 · 数据源：腾讯财经 qt.gtimg.cn（免费公开）· 汇率 1 USD = 7.2 CNY · 不含管理费 / 税务 / 交易费<br/>
    本页面不构成投资建议。数据每交易日 16:30 ET 后自动更新。
  </div>
</div>

<script>
  // ---------- embed data ----------
  const DATA = {json.dumps(chart_data, ensure_ascii=False)};
  const LATEST = {{
    "shares": {{
      "QQQ":  {float(last['shares_QQQ']):.6f},
      "QLD":  {float(last['shares_QLD']):.6f},
      "TQQQ": {float(last['shares_TQQQ']):.6f},
    }}
  }};

  // ---------- helpers ----------
  const fmtY  = v => "¥" + v.toLocaleString("en-US", {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
  const fmtYP = v => (v >= 0 ? "+" : "") + v.toLocaleString("en-US", {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
  const fmtP  = v => (v >= 0 ? "+" : "") + (v * 100).toFixed(2) + "%";
  const color = v => v >= 0 ? "rgba(47,111,94,0.85)" : "rgba(176,99,103,0.85)";

  // ---------- 1. cumulative curve ----------
  const ctx1 = document.getElementById('curveChart').getContext('2d');
  new Chart(ctx1, {{
    type: 'line',
    data: {{
      labels: DATA.labels,
      datasets: [
        {{
          label: '累计投入 (¥)',
          data: DATA.cum_invested,
          borderColor: '#7c7a72',
          backgroundColor: 'rgba(124,122,114,0.08)',
          borderWidth: 2, borderDash: [6, 4], tension: 0.15, pointRadius: 0, fill: false,
        }},
        {{
          label: '账户市值 (¥)',
          data: DATA.value,
          borderColor: '#2f6f5e',
          backgroundColor: 'rgba(47,111,94,0.10)',
          borderWidth: 2.4, tension: 0.18, pointRadius: 0, fill: true,
        }},
      ],
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      interaction: {{ mode: 'index', intersect: false }},
      scales: {{
        y: {{ ticks: {{ callback: v => "¥" + v.toLocaleString() }} }},
        x: {{ ticks: {{ maxRotation: 0, autoSkipPadding: 16 }} }},
      }},
      plugins: {{
        tooltip: {{
          callbacks: {{
            title: ctx => ctx[0].label,
            label: ctx => ctx.dataset.label + ": " + fmtY(ctx.parsed.y),
          }},
        }},
        legend: {{ position: 'top', align: 'end' }},
      }},
    }},
  }});

  // Y-axis scale toggle
  document.getElementById('curve-scale').addEventListener('change', e => {{
    const sc = e.target.value;
    const chart = Chart.getChart('curveChart');
    chart.options.scales.y.type = sc;
    chart.update();
  }});

  // ---------- 2. daily P&L bar ----------
  let dailyMode = 'amount';
  const ctx2 = document.getElementById('dailyChart').getContext('2d');
  const dailyChart = new Chart(ctx2, {{
    type: 'bar',
    data: {{
      labels: DATA.labels,
      datasets: [{{
        label: '每日盈亏 (¥)',
        data: DATA.pnl,
        backgroundColor: DATA.pnl.map(color),
        borderColor: DATA.pnl.map(color),
        borderWidth: 1,
      }}],
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      scales: {{
        y: {{ ticks: {{ callback: v => fmtYP(v) }} }},
        x: {{ ticks: {{ maxRotation: 0, autoSkipPadding: 16 }} }},
      }},
      plugins: {{
        tooltip: {{
          callbacks: {{
            title: ctx => ctx[0].label,
            label: ctx => fmtYP(ctx.parsed.y),
          }},
        }},
        legend: {{ display: false }},
      }},
    }},
  }});

  document.getElementById('daily-mode').addEventListener('change', e => {{
    dailyMode = e.target.value;
    if (dailyMode === 'pct') {{
      dailyChart.data.datasets[0].label = '每日盈亏比率';
      dailyChart.data.datasets[0].data = DATA.daily_return;
      dailyChart.data.datasets[0].backgroundColor = DATA.daily_return.map(color);
      dailyChart.data.datasets[0].borderColor = DATA.daily_return.map(color);
      dailyChart.options.scales.y.ticks.callback = v => (v * 100).toFixed(2) + '%';
      dailyChart.options.plugins.tooltip.callbacks.label = ctx => fmtP(ctx.parsed.y);
    }} else {{
      dailyChart.data.datasets[0].label = '每日盈亏 (¥)';
      dailyChart.data.datasets[0].data = DATA.pnl;
      dailyChart.data.datasets[0].backgroundColor = DATA.pnl.map(color);
      dailyChart.data.datasets[0].borderColor = DATA.pnl.map(color);
      dailyChart.options.scales.y.ticks.callback = v => fmtYP(v);
      dailyChart.options.plugins.tooltip.callbacks.label = ctx => fmtYP(ctx.parsed.y);
    }}
    dailyChart.update();
  }});

  // ---------- 3. monthly breakdown ----------
  const monthSelect = document.getElementById('month-select');
  DATA.months.forEach(m => {{
    const o = document.createElement('option');
    o.value = m.value;
    o.textContent = m.label;
    if (m.value === DATA.months[DATA.months.length - 1].value) o.selected = true;
    monthSelect.appendChild(o);
  }});

  const ctx3 = document.getElementById('monthlyChart').getContext('2d');
  const monthlyChart = new Chart(ctx3, {{
    type: 'bar',
    data: {{ labels: [], datasets: [{{ data: [], backgroundColor: [] }}] }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      scales: {{ y: {{ ticks: {{ callback: v => (v * 100).toFixed(2) + '%' }} }} }},
      plugins: {{ legend: {{ display: false }} }},
    }},
  }});

  let monthMode = 'pct';

  function renderMonth() {{
    const month = monthSelect.value;
    if (!month) return;
    const idx = DATA.labels.findIndex(d => d.startsWith(month));
    if (idx < 0) return;
    // collect this month's rows
    const dates = [], vals = [], colors = [];
    const isPct = monthMode === 'pct';
    let i = idx;
    while (i < DATA.labels.length && DATA.labels[i].startsWith(month)) {{
      const d = DATA.labels[i];
      const v = isPct ? DATA.daily_return[i] : DATA.pnl[i];
      dates.push(d.substring(5));  // MM-DD
      vals.push(v);
      colors.push(color(v));
      i++;
    }}
    monthlyChart.data.labels = dates;
    monthlyChart.data.datasets[0].data = vals;
    monthlyChart.data.datasets[0].backgroundColor = colors;
    monthlyChart.data.datasets[0].label = isPct ? '每日盈亏比率' : '每日盈亏金额';
    monthlyChart.options.plugins.tooltip.callbacks = {{
      label: ctx => isPct ? fmtP(ctx.parsed.y) : fmtYP(ctx.parsed.y),
    }};
    monthlyChart.options.scales.y.ticks.callback = v => isPct ? (v * 100).toFixed(2) + '%' : fmtYP(v);
    monthlyChart.update();

    // table
    let html = '<table><thead><tr><th>日期</th><th>当日投入</th><th>累计投入</th><th>账户市值</th><th>当日盈亏 (¥)</th><th>累计盈亏 (¥)</th><th>累计盈亏 %</th></tr></thead><tbody>';
    i = idx;
    while (i < DATA.labels.length && DATA.labels[i].startsWith(month)) {{
      const d = DATA.labels[i];
      const dpnl = DATA.pnl[i];
      const cumPnl = dpnl;  // DATA.pnl is already cumulative
      const cumIn = DATA.cum_invested[i];
      const val = DATA.value[i];
      const cumPct = (val - cumIn) / cumIn;
      html += `<tr>
        <td>${{d}}</td>
        <td>¥600.00</td>
        <td>¥${{cumIn.toLocaleString('en-US', {{minimumFractionDigits: 2}})}}</td>
        <td>¥${{val.toLocaleString('en-US', {{minimumFractionDigits: 2}})}}</td>
        <td class="${{dpnl >= 0 ? 'pos' : 'neg'}}">${{fmtYP(dpnl)}}</td>
        <td class="${{cumPnl >= 0 ? 'pos' : 'neg'}}">${{fmtYP(cumPnl)}}</td>
        <td class="${{cumPct >= 0 ? 'pos' : 'neg'}}">${{fmtP(cumPct)}}</td>
      </tr>`;
      i++;
    }}
    html += '</tbody></table>';
    document.getElementById('month-table-wrap').innerHTML = html;
  }}

  monthSelect.addEventListener('change', renderMonth);
  document.getElementById('month-mode').addEventListener('change', e => {{
    monthMode = e.target.value;
    renderMonth();
  }});
  renderMonth();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
