"""
Render the static site (index.html + assets) from data/portfolio.csv.

Sections:
  1. Header / latest snapshot card
  2. Three global KPI cards
  3. Per-ETF KPI cards (QQQ / QLD / TQQQ each: value / invested / return)
  4. P&L curve (Chart.js) — line of cumulative invested vs market value over time
  5. Daily P&L bar (Chart.js) — daily P&L amount / %
  6. Calendar view — month-at-a-glance heatmap, click date for details
  7. Per-ticker price cards (today's open/close)
  8. Footer
"""
from __future__ import annotations
import os
import json
import calendar
from datetime import datetime, date
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
SITE_DIR = os.path.join(ROOT, "site")
os.makedirs(SITE_DIR, exist_ok=True)

CNY_PER_USD = 7.2
DAILY_CNY = {"QQQ": 100.0, "QLD": 200.0, "TQQQ": 300.0}


def load_data():
    pf_path = os.path.join(DATA_DIR, "portfolio.csv")
    if not os.path.exists(pf_path):
        raise SystemExit("portfolio.csv not found -- run dca_engine.py first")
    pf = pd.read_csv(pf_path)
    pf["date"] = pd.to_datetime(pf["date"]).dt.date
    pf = pf.sort_values("date").reset_index(drop=True)
    last = pf.iloc[-1]
    closes = {n: float(last[f"{n}_close"]) for n in ("QQQ", "QLD", "TQQQ")}
    opens  = {n: float(last[f"{n}_open"])  for n in ("QQQ", "QLD", "TQQQ")}
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


def per_etf_kpis(pf: pd.DataFrame, last, closes: dict) -> list[dict]:
    """For each ETF, compute: invested (CNY), value (CNY at today close), return ratio."""
    kpis = []
    cum_days = len(pf)
    for n in ("QQQ", "QLD", "TQQQ"):
        invested_cny = DAILY_CNY[n] * cum_days
        shares = float(last[f"shares_{n}"])
        price_now = closes[n]
        value_cny = shares * price_now * CNY_PER_USD
        pnl_cny = value_cny - invested_cny
        return_ratio = pnl_cny / invested_cny if invested_cny else 0.0
        kpis.append({
            "ticker": n,
            "shares": shares,
            "price": price_now,
            "invested_cny": invested_cny,
            "value_cny":    value_cny,
            "pnl_cny":      pnl_cny,
            "return_ratio": return_ratio,
        })
    return kpis


def main():
    pf, opens, closes, last = load_data()
    if pf.empty:
        raise SystemExit("portfolio is empty")

    # ---- chart data ----
    labels  = [d.isoformat() for d in pf["date"]]
    cum_in  = pf["cum_cny_invested"].astype(float).tolist()
    val     = pf["total_cny_value"].astype(float).tolist()
    pnl     = pf["pnl_cny"].astype(float).tolist()
    pnl_pct = pf["pnl_ratio"].astype(float).tolist()
    daily_ret = [0.0]
    for i in range(1, len(val)):
        prev = val[i-1] if val[i-1] else 1.0
        daily_ret.append(val[i] / prev - 1.0)

    pf["month"] = pd.to_datetime(pf["date"]).dt.strftime("%Y-%m")
    months = sorted(pf["month"].unique())
    # build per-month nested data for the calendar
    cal_data = {}
    for m in months:
        cal_data[m] = {}
        for _, row in pf.iterrows():
            d = row["date"].isoformat()
            if not d.startswith(m):
                continue
            cal_data[m][d] = {
                "invested": float(row["cum_cny_invested"]),
                "value":    float(row["total_cny_value"]),
                "pnl":      float(row["pnl_cny"]),
                "pnl_pct":  float(row["pnl_ratio"]),
                "shares": {
                    "QQQ":  float(row["shares_QQQ"]),
                    "QLD":  float(row["shares_QLD"]),
                    "TQQQ": float(row["shares_TQQQ"]),
                },
                "bought_today": float(row["QQQ_bought"] + row["QLD_bought"] + row["TQQQ_bought"]),
            }

    chart_data = {
        "labels": labels,
        "cum_invested": cum_in,
        "value": val,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "daily_return": daily_ret,
        "months": [{"value": m, "label": m} for m in months],
        "calendar": cal_data,
    }

    # ---- per-ETF kpis ----
    kpis = per_etf_kpis(pf, last, closes)
    today_cny_invested = float(last["cum_cny_invested"])
    today_cny_value    = float(last["total_cny_value"])
    today_pnl_cny      = float(last["pnl_cny"])
    today_pnl_ratio    = float(last["pnl_ratio"])
    days_so_far        = len(pf)
    avg_daily_cny      = today_cny_invested / days_so_far if days_so_far else 0.0

    # ---- render ----
    html = render_html(chart_data, opens, closes, last, kpis,
                       today_cny_invested, today_cny_value,
                       today_pnl_cny, today_pnl_ratio,
                       days_so_far, avg_daily_cny, pf)

    out = os.path.join(SITE_DIR, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  + site/index.html ({len(html)/1024:.1f} KB)")

    out2 = os.path.join(SITE_DIR, "data.json")
    with open(out2, "w", encoding="utf-8") as f:
        json.dump({
            "chart": chart_data,
            "kpis": kpis,
            "latest": {
                "date": last["date"].isoformat() if hasattr(last["date"], "isoformat") else str(last["date"]),
                "opens": opens,
                "closes": closes,
                "cum_cny_invested": today_cny_invested,
                "total_cny_value":   today_cny_value,
                "pnl_cny":           today_pnl_cny,
                "pnl_ratio":         today_pnl_ratio,
                "shares": {n: float(last[f"shares_{n}"]) for n in ("QQQ", "QLD", "TQQQ")},
            }
        }, f, ensure_ascii=False, indent=2)
    print(f"  + site/data.json")


def render_html(chart_data, opens, closes, last, kpis,
                cum_invested, total_value, pnl_cny, pnl_ratio,
                days_so_far, avg_daily_cny, pf) -> str:
    today = last["date"].isoformat() if hasattr(last["date"], "isoformat") else str(last["date"])
    color_pnl = "#2f6f5e" if pnl_cny >= 0 else "#b06367"

    # ---- per-ETF KPI cards ----
    per_etf_html = ""
    for k in kpis:
        c = "#2f6f5e" if k["pnl_cny"] >= 0 else "#b06367"
        badge = {"QQQ": "q", "QLD": "l", "TQQQ": "t"}[k["ticker"]]
        per_etf_html += f"""
    <div class="kpi kpi-etf" data-ticker="{k['ticker']}">
      <div class="lbl"><span class="badge {badge}">{k['ticker']}</span> · 账户价值</div>
      <div class="val">¥{k['value_cny']:,.2f}</div>
      <div class="sub">{k['shares']:.6f} 股 × ${k['price']:.2f}</div>
    </div>
    <div class="kpi kpi-etf" data-ticker="{k['ticker']}">
      <div class="lbl"><span class="badge {badge}">{k['ticker']}</span> · 累计投入</div>
      <div class="val">¥{k['invested_cny']:,.2f}</div>
      <div class="sub">¥{DAILY_CNY[k['ticker']]:.0f}/日 × {days_so_far} 天</div>
    </div>
    <div class="kpi kpi-etf" data-ticker="{k['ticker']}">
      <div class="lbl"><span class="badge {badge}">{k['ticker']}</span> · 累计收益率</div>
      <div class="val" style="color: {c};">{fmt_pct(k['return_ratio'])}</div>
      <div class="sub" style="color: {c};">{fmt_money(k['pnl_cny'])}</div>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>每日定投追踪 · QQQ/QLD/TQQQ</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
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
    .section-title {{ font-size: 13px; color: var(--text-mute); font-weight: 500;
      text-transform: uppercase; letter-spacing: 0.08em; margin: 20px 0 10px; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 12px; }}
    .kpi {{ background: var(--surface); border: 1px solid var(--line); border-radius: 14px;
      padding: 16px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.03); }}
    .kpi .lbl {{ font-size: 11.5px; color: var(--text-mute); text-transform: uppercase;
      letter-spacing: 0.08em; margin-bottom: 4px; display: flex; align-items: center; gap: 6px; }}
    .kpi .val {{ font-size: 24px; font-weight: 600; line-height: 1.2; }}
    .kpi .sub {{ font-size: 12.5px; color: var(--text-mute); margin-top: 4px; }}
    .kpi.q {{ border-top: 3px solid var(--q); }}
    .kpi.l {{ border-top: 3px solid var(--l); }}
    .kpi.t {{ border-top: 3px solid var(--t); }}
    .kpi-etf-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 20px; }}
    .kpi-etf {{ border-top: 3px solid var(--q); }}
    .kpi-etf[data-ticker="QLD"] {{ border-top-color: var(--l); }}
    .kpi-etf[data-ticker="TQQQ"] {{ border-top-color: var(--t); }}
    .price-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }}
    .price {{ background: var(--surface); border: 1px solid var(--line); border-radius: 14px;
      padding: 16px 18px; border-top: 3px solid var(--q); }}
    .price.ql {{ border-top-color: var(--l); }}
    .price.tq {{ border-top-color: var(--t); }}
    .price .name {{ font-size: 14px; color: var(--text-soft); font-weight: 600; letter-spacing: 0.04em; }}
    .price .px {{ font-size: 22px; font-weight: 600; margin: 4px 0 2px; }}
    .price .detail {{ display: flex; gap: 14px; font-size: 12.5px; color: var(--text-mute); flex-wrap: wrap; }}
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

    /* ---------- calendar ---------- */
    .cal-nav {{ display: flex; align-items: center; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }}
    .cal-nav .cal-month {{ font-size: 18px; font-weight: 600; min-width: 130px; text-align: center; }}
    .cal-nav button {{ background: var(--bg); border: 1px solid var(--line);
      padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 14px; color: var(--text); }}
    .cal-nav button:hover {{ background: #f0eadb; }}
    .cal-nav button:disabled {{ opacity: 0.3; cursor: not-allowed; }}
    .cal-table {{ width: 100%; border-collapse: separate; border-spacing: 4px; table-layout: fixed; }}
    .cal-table th {{ background: transparent; color: var(--text-mute);
      font-size: 11.5px; text-align: center; padding: 4px 0; font-weight: 500; letter-spacing: 0.04em; }}
    .cal-table td {{ background: #faf7ed; border-radius: 8px; padding: 6px 8px;
      vertical-align: top; height: 78px; position: relative; border: 1px solid transparent;
      cursor: default; transition: all 0.15s; }}
    .cal-table td.has-data {{ cursor: pointer; }}
    .cal-table td.has-data:hover {{ border-color: var(--primary); transform: translateY(-1px); box-shadow: 0 2px 6px rgba(0,0,0,0.08); }}
    .cal-table td.has-data.selected {{ border-color: var(--primary); border-width: 2px; background: #fff; }}
    .cal-table td.empty {{ background: transparent; }}
    .cal-day-num {{ font-size: 12px; color: var(--text-mute); font-weight: 500; margin-bottom: 2px; }}
    .cal-day-pct {{ font-size: 14px; font-weight: 600; line-height: 1.2; }}
    .cal-day-amt {{ font-size: 11px; color: var(--text-mute); margin-top: 1px; }}
    .cal-table td.pos {{ background: #e8f1ec; }}
    .cal-table td.neg {{ background: #f5e8e9; }}
    .cal-table td.pos .cal-day-pct {{ color: #1f5b48; }}
    .cal-table td.neg .cal-day-pct {{ color: #8c3a3f; }}
    .cal-detail {{ margin-top: 20px; padding: 16px 18px; background: #faf7ed;
      border-radius: 10px; border: 1px solid var(--line); }}
    .cal-detail h3 {{ margin: 0 0 10px; font-size: 15px; }}
    .cal-detail .detail-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
    .cal-detail .detail-item {{ padding: 8px 0; }}
    .cal-detail .detail-item .lbl {{ font-size: 11px; color: var(--text-mute);
      text-transform: uppercase; letter-spacing: 0.06em; }}
    .cal-detail .detail-item .val {{ font-size: 17px; font-weight: 600; }}

    @media (max-width: 800px) {{
      .kpi-grid {{ grid-template-columns: 1fr 1fr; }}
      .kpi-etf-grid {{ grid-template-columns: 1fr; }}
      .price-grid {{ grid-template-columns: 1fr; }}
      .cal-table td {{ height: 60px; padding: 4px 5px; }}
      .cal-day-pct {{ font-size: 12px; }}
      .cal-day-amt {{ font-size: 10px; }}
      .cal-detail .detail-grid {{ grid-template-columns: 1fr 1fr; }}
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

  <div class="section-title">📊 组合整体</div>
  <div class="kpi-grid">
    <div class="kpi">
      <div class="lbl">累计投入</div>
      <div class="val">¥{cum_invested:,.2f}</div>
      <div class="sub">日均 ¥{avg_daily_cny:,.2f}</div>
    </div>
    <div class="kpi">
      <div class="lbl">当前市值</div>
      <div class="val" style="color: {color_pnl};">¥{total_value:,.2f}</div>
      <div class="sub">按 1 USD = 7.2 CNY 折算</div>
    </div>
    <div class="kpi">
      <div class="lbl">累计盈亏</div>
      <div class="val" style="color: {color_pnl};">{fmt_money(pnl_cny)}</div>
      <div class="sub">{fmt_pct(pnl_ratio)}</div>
    </div>
    <div class="kpi">
      <div class="lbl">日均盈亏</div>
      <div class="val" style="color: {color_pnl};">{fmt_money(pnl_cny / days_so_far if days_so_far else 0)}</div>
      <div class="sub">{days_so_far} 个交易日</div>
    </div>
  </div>

  <div class="section-title">💼 各 ETF 单独账户</div>
  <div class="kpi-etf-grid">
{per_etf_html}
  </div>

  <div class="price-grid">
    <div class="price">
      <div class="name"><span class="badge q">QQQ</span> · Invesco QQQ Trust</div>
      <div class="px">${closes['QQQ']:.2f}</div>
      <div class="detail">
        <div>开 <b>${opens['QQQ']:.2f}</b></div>
        <div>收 <b>${closes['QQQ']:.2f}</b></div>
        <div>持有 <b>{last['shares_QQQ']:.4f}</b> 股</div>
      </div>
    </div>
    <div class="price ql">
      <div class="name"><span class="badge l">QLD</span> · ProShares Ultra QQQ (2×)</div>
      <div class="px">${closes['QLD']:.2f}</div>
      <div class="detail">
        <div>开 <b>${opens['QLD']:.2f}</b></div>
        <div>收 <b>${closes['QLD']:.2f}</b></div>
        <div>持有 <b>{last['shares_QLD']:.4f}</b> 股</div>
      </div>
    </div>
    <div class="price tq">
      <div class="name"><span class="badge t">TQQQ</span> · ProShares UltraPro QQQ (3×)</div>
      <div class="px">${closes['TQQQ']:.2f}</div>
      <div class="detail">
        <div>开 <b>${opens['TQQQ']:.2f}</b></div>
        <div>收 <b>${closes['TQQQ']:.2f}</b></div>
        <div>持有 <b>{last['shares_TQQQ']:.4f}</b> 股</div>
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
    <h2>📅 每月每日明细 <span class="hint">（日历视图 · 点击日期查看详情）</span></h2>
    <div class="cal-nav">
      <button id="cal-prev">‹</button>
      <div class="cal-month" id="cal-month">2026-07</div>
      <button id="cal-next">›</button>
      <label style="margin-left: 16px;">色彩：
        <select id="cal-mode">
          <option value="pct">按收益率 (%)</option>
          <option value="amount">按金额 (¥)</option>
        </select>
      </label>
    </div>
    <table class="cal-table" id="cal-table">
      <thead>
        <tr>
          <th>一</th><th>二</th><th>三</th><th>四</th><th>五</th><th>六</th><th>日</th>
        </tr>
      </thead>
      <tbody id="cal-body"></tbody>
    </table>
    <div class="cal-detail" id="cal-detail" style="display:none;"></div>
  </div>

  <div class="footer">
    起始 2026-07-22 · 数据源：腾讯财经 qt.gtimg.cn（免费公开）· 汇率 1 USD = 7.2 CNY · 不含管理费 / 税务 / 交易费<br/>
    本页面不构成投资建议。数据每交易日 16:30 ET 后自动更新。
  </div>
</div>

<script>
  // ---------- embed data ----------
  const DATA = {json.dumps(chart_data, ensure_ascii=False)};
  const KPIS = {json.dumps(kpis, ensure_ascii=False)};

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

  document.getElementById('curve-scale').addEventListener('change', e => {{
    const sc = e.target.value;
    const chart = Chart.getChart('curveChart');
    chart.options.scales.y.type = sc;
    chart.update();
  }});

  // ---------- 2. daily P&L bar ----------
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
    const mode = e.target.value;
    if (mode === 'pct') {{
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

  // ---------- 3. calendar view ----------
  const MONTHS_CN = ['一月','二月','三月','四月','五月','六月','七月','八月','九月','十月','十一月','十二月'];
  let calMonthIdx = DATA.months.length - 1;  // start at latest month
  let calMode = 'pct';
  let selectedDate = null;

  function renderCal() {{
    const monthStr = DATA.months[calMonthIdx].value;
    document.getElementById('cal-month').textContent = monthStr;
    const [y, m] = monthStr.split('-').map(Number);
    const firstDay = new Date(y, m - 1, 1);
    const lastDay  = new Date(y, m, 0);
    const daysInMonth = lastDay.getDate();
    // Monday = 0, Sunday = 6 (display Mon first)
    const startOffset = (firstDay.getDay() + 6) % 7;  // convert Sun(0) -> 6
    const tbody = document.getElementById('cal-body');
    tbody.innerHTML = '';
    let row = document.createElement('tr');
    for (let i = 0; i < startOffset; i++) {{
      const cell = document.createElement('td');
      cell.className = 'empty';
      row.appendChild(cell);
    }}
    for (let d = 1; d <= daysInMonth; d++) {{
      if (row.children.length === 7) {{
        tbody.appendChild(row);
        row = document.createElement('tr');
      }}
      const cell = document.createElement('td');
      const dateStr = `${{y}}-${{String(m).padStart(2, '0')}}-${{String(d).padStart(2, '0')}}`;
      const rec = DATA.calendar[monthStr] && DATA.calendar[monthStr][dateStr];
      cell.innerHTML = `<div class="cal-day-num">${{d}}</div>`;
      if (rec) {{
        cell.classList.add('has-data');
        const v = calMode === 'pct' ? rec.pnl_pct : rec.pnl;
        cell.classList.add(v >= 0 ? 'pos' : 'neg');
        const pctTxt = (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%';
        const amtTxt = fmtYP(rec.pnl);
        cell.innerHTML += `<div class="cal-day-pct">${{pctTxt}}</div><div class="cal-day-amt">${{amtTxt}}</div>`;
        cell.dataset.date = dateStr;
        if (dateStr === selectedDate) cell.classList.add('selected');
        cell.addEventListener('click', () => showDetail(dateStr, rec));
      }}
      row.appendChild(cell);
    }}
    while (row.children.length < 7) {{
      const cell = document.createElement('td');
      cell.className = 'empty';
      row.appendChild(cell);
    }}
    tbody.appendChild(row);

    document.getElementById('cal-prev').disabled = calMonthIdx === 0;
    document.getElementById('cal-next').disabled = calMonthIdx === DATA.months.length - 1;
  }}

  function showDetail(date, rec) {{
    selectedDate = date;
    const cumPct = rec.pnl_pct;
    const c = cumPct >= 0 ? '#1f5b48' : '#8c3a3f';
    const html = `
      <h3>${{date}} 的持仓明细 <span style="font-size: 12px; color: var(--text-mute); font-weight: 400;">点击其他日期切换</span></h3>
      <div class="detail-grid">
        <div class="detail-item">
          <div class="lbl">累计投入</div>
          <div class="val">¥${{rec.invested.toLocaleString('en-US', {{minimumFractionDigits: 2}})}}</div>
        </div>
        <div class="detail-item">
          <div class="lbl">账户市值</div>
          <div class="val">¥${{rec.value.toLocaleString('en-US', {{minimumFractionDigits: 2}})}}</div>
        </div>
        <div class="detail-item">
          <div class="lbl">累计盈亏</div>
          <div class="val" style="color: ${{c}};">${{fmtYP(rec.pnl)}}</div>
        </div>
        <div class="detail-item">
          <div class="lbl">累计收益率</div>
          <div class="val" style="color: ${{c}};">${{fmtP(cumPct)}}</div>
        </div>
      </div>
      <div class="detail-grid" style="margin-top: 12px; border-top: 1px solid var(--line); padding-top: 12px;">
        <div class="detail-item">
          <div class="lbl"><span class="badge q">QQQ</span> 持有</div>
          <div class="val">${{rec.shares.QQQ.toFixed(6)}} 股</div>
        </div>
        <div class="detail-item">
          <div class="lbl"><span class="badge l">QLD</span> 持有</div>
          <div class="val">${{rec.shares.QLD.toFixed(6)}} 股</div>
        </div>
        <div class="detail-item">
          <div class="lbl"><span class="badge t">TQQQ</span> 持有</div>
          <div class="val">${{rec.shares.TQQQ.toFixed(6)}} 股</div>
        </div>
        <div class="detail-item">
          <div class="lbl">当日新买入</div>
          <div class="val">${{rec.bought_today.toFixed(6)}} 股</div>
        </div>
      </div>
    `;
    document.getElementById('cal-detail').innerHTML = html;
    document.getElementById('cal-detail').style.display = 'block';
    // refresh selection highlight
    renderCal();
  }}

  document.getElementById('cal-prev').addEventListener('click', () => {{
    if (calMonthIdx > 0) {{ calMonthIdx--; renderCal(); }}
  }});
  document.getElementById('cal-next').addEventListener('click', () => {{
    if (calMonthIdx < DATA.months.length - 1) {{ calMonthIdx++; renderCal(); }}
  }});
  document.getElementById('cal-mode').addEventListener('change', e => {{
    calMode = e.target.value;
    renderCal();
  }});

  // auto-select latest day in current month
  renderCal();
  (function autoSelect() {{
    const monthStr = DATA.months[calMonthIdx].value;
    const days = Object.keys(DATA.calendar[monthStr] || {{}}).sort();
    if (days.length > 0) showDetail(days[days.length - 1], DATA.calendar[monthStr][days[days.length - 1]]);
  }})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
