# 每日定投追踪 · QQQ / QLD / TQQQ

从 **2026-07-22** 开始的每日定投网站，每天自动更新。

## 定投规则

| 标的 | 每日金额 (CNY) | 倍数 |
|---|---|---|
| QQQ | 100 | 1× |
| QLD | 200 | 2× |
| TQQQ | 300 | 3× |
| **合计** | **600** | — |

买入价：当日**开盘价**（如开盘价缺失则用收盘价）
汇率：1 USD = 7.2 CNY
数据源：[腾讯财经 qt.gtimg.cn](https://qt.gtimg.cn/)（免费、公开、稳定）

## 文件结构

```
dca_site/
├── fetch_data.py     ← 拉 QQQ/QLD/TQQQ 当日 OHLCV
├── dca_engine.py     ← 计算每日买入、持仓、市值、P&L
├── build_site.py     ← 渲染 site/index.html (Chart.js)
├── update.py         ← 一键运行上面三个
├── backfill.py       ← 手动补录历史数据（CLI / CSV）
├── data/
│   ├── price_QQQ.csv    ← QQQ 历史 OHLC
│   ├── price_QLD.csv
│   ├── price_TQQQ.csv
│   ├── portfolio.csv    ← 每日账户快照
│   └── summary.json     ← 最新快照
└── site/
    ├── index.html     ← 静态网站
    └── data.json      ← 同 chart_data
```

## 一次性安装

```bash
# 安装依赖
pip install pandas --break-system-packages

# 首次运行：拉数据 + 算组合 + 出网站
python3 update.py

# 启动本地预览
cd site && python3 -m http.server 8000
# 浏览器打开 http://localhost:8000
```

## 每天自动更新（crontab）

美国东部时间 16:30（美股收盘后 30 分钟）跑一次：

```bash
# 编辑 crontab
crontab -e

# 加一行（注意时区！）
30 16 * * 1-5  cd /path/to/dca_site && /usr/bin/python3 update.py >> /path/to/dca_site/update.log 2>&1
```

注意：
- `1-5` = 周一到周五（美股交易日）
- 服务器时区要设为 `America/New_York`，否则改成对应的 UTC 时间
- 节假日美股不开盘——但腾讯 API 仍然会返回**最近一个交易日**的数据，我们的代码已经按"有数据才执行买入"处理
- 偶尔需要**手动**补录（如下面所说）

## 手动补录历史数据

腾讯 API 只能拿到**最近 1 个交易日**的数据。如果你想从 2026-07-22 完整开始，需要手动补 7-22、7-23 的价格（用券商、雪球、或财经网站查）。

```bash
# 单行
python3 backfill.py --ticker QQQ --date 2026-07-22 --open 695.10 --high 698.20 --low 690.50 --close 691.96

# 批量（CSV）
python3 backfill.py --csv backfill_start.csv
```

CSV 格式：
```csv
date,ticker,open,high,low,close,volume
2026-07-22,QQQ,695.10,698.20,690.50,691.96,42000000
2026-07-22,QLD,85.20,86.10,84.10,84.95,3800000
2026-07-22,TQQQ,67.00,68.50,65.20,66.30,55000000
```

补录后跑 `python3 update.py` 重新计算组合。

## 部署到 GitHub Pages（免费）

```bash
# 1. 在 GitHub 新建 repo
# 2. 把 site/ 目录的所有文件 push 到 gh-pages 分支
git checkout -b gh-pages
git add site/
git commit -m "Deploy DCA tracker"
git push origin gh-pages

# 3. 在 GitHub repo Settings → Pages → 选 gh-pages 分支
# 4. 访问 https://<user>.github.io/<repo>/
```

如果想要"每天自动部署"，加一个 GitHub Action（见 `.github/workflows/update.yml`）：

```yaml
name: Update DCA tracker
on:
  schedule:
    - cron: "30 21 * * 1-5"   # UTC 21:30 = ET 16:30（夏令时）
  workflow_dispatch:        # 手动触发
jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install pandas
      - run: python3 update.py
      - uses: actions/configure-pages@v4
      - uses: actions/upload-pages-artifact@v3
        with: { path: site/ }
      - id: deploy
      - uses: actions/deploy-pages@v4
```

## 重要假设

1. **每日开盘价买入**：实际定投可能用 VWAP 或收盘价，差异通常 < 0.1%
2. **汇率固定 7.2**：可以改为每日实时汇率（在 `dca_engine.py` 的 `CNY_PER_USD`）
3. **不含分红 / 杠杆 ETF 损耗 / 管理费**：实际长期会少 0.5-1pp/年
4. **美股 ETF 是 QQQ 等基础资产**：与 TQQQ 真实表现会有差异（杠杆 ETF 有波动率衰减）
5. **腾讯 API 是延迟报价**（15 分钟延迟），与真实收盘价可能有 0.05% 以内差异

## 调参

`dca_engine.py` 顶部：
```python
CNY_PER_USD = 7.2
DAILY_CNY = {"QQQ": 100, "QLD": 200, "TQQQ": 300}
START_DATE = "2026-07-22"
```

## 故障排查

- **腾讯 API 报错**：网络问题，重跑 `python3 fetch_data.py`
- **腾讯返回 200 但数字异常**：是节假日，返回的是**前一个交易日**的数据，正常
- **数据缺一天**：手动 backfill 后重跑 update
- **网站显示"已运行 1 个交易日"**：只有 7-24 的数据，需要补 7-22、7-23

---

**最后更新：见 `site/index.html` 顶部的"截至"日期**
