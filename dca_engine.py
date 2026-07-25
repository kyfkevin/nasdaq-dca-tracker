"""
DCA engine: apply daily purchases and compute portfolio metrics.

Config (CNY per day):
  QQQ:  100
  QLD:  200
  TQQQ: 300
  Total: 600 CNY / day

For each trading day (i.e. day with a recorded close), the engine
  - converts the day's CNY contribution to USD at the recorded close
    (assumption: $1 = 7.2 CNY; user can change via env)
  - buys fractional shares at the OPEN price (or the close if OPEN
    missing); we use OPEN per the spec "参考当天的开盘价买入"
  - accumulates shares
  - marks the day's portfolio to the close (intraday P&L not modelled)

Outputs:
  data/portfolio.csv     -- one row per trading day
  data/summary.json      -- latest snapshot for the front page
"""
from __future__ import annotations
import os
import json
import math
import argparse
from datetime import datetime, date
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")

CNY_PER_USD = 7.2            # ← user can edit
DAILY_CNY = {                # ← user spec
    "QQQ":  100.0,
    "QLD":  200.0,
    "TQQQ": 300.0,
}
START_DATE = "2026-07-22"   # ← user spec


def _read_price(ticker: str) -> pd.DataFrame:
    path = os.path.join(DATA_DIR, f"price_{ticker}.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(f"price CSV missing: {path} -- run fetch_data.py first")
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values("date").reset_index(drop=True)
    return df


def build_portfolio() -> pd.DataFrame:
    """
    Walk trading days from START_DATE onward, applying the daily
    contribution at the OPEN price, then mark to CLOSE for EOD value.
    """
    prices = {n: _read_price(n) for n in ("QQQ", "QLD", "TQQQ")}
    # build a union of all trading days >= START_DATE
    all_dates = sorted({d for n, df in prices.items() for d in df["date"]})
    start = datetime.strptime(START_DATE, "%Y-%m-%d").date()
    all_dates = [d for d in all_dates if d >= start]
    if not all_dates:
        raise SystemExit(f"No trading data on/after {START_DATE}. Run fetch_data.py first.")

    shares = {"QQQ": 0.0, "QLD": 0.0, "TQQQ": 0.0}
    rows = []
    cum_cny_invested = 0.0
    cum_cny_dividends = 0.0
    cum_shares_bought = {n: 0.0 for n in shares}

    for d in all_dates:
        day_record = {"date": d.isoformat()}
        for n, df in prices.items():
            row = df[df["date"] == d]
            if row.empty:
                # market closed this day (e.g. holiday); skip
                continue
            row = row.iloc[0]
            # Buy at open. If open is missing/zero, fall back to close.
            op  = float(row["open"])
            cls = float(row["close"])
            if not op or op <= 0 or math.isnan(op):
                op = cls
            cny_today = DAILY_CNY[n]
            usd_today = cny_today / CNY_PER_USD
            sh_bought = usd_today / op
            shares[n] += sh_bought
            cum_shares_bought[n] += sh_bought
            cum_cny_invested += cny_today
            day_record[f"{n}_open"]   = op
            day_record[f"{n}_close"]  = cls
            day_record[f"{n}_bought"] = round(sh_bought, 6)
            day_record[f"{n}_shares"] = round(shares[n], 6)
        # EOD value (USD)
        v_QQQ  = shares["QQQ"]  * day_record.get("QQQ_close",  0.0)
        v_QLD  = shares["QLD"]  * day_record.get("QLD_close",  0.0)
        v_TQQQ = shares["TQQQ"] * day_record.get("TQQQ_close", 0.0)
        total_usd = v_QQQ + v_QLD + v_TQQQ
        total_cny = total_usd * CNY_PER_USD
        # net P&L (CNY)
        pnl_cny = total_cny - cum_cny_invested
        # P&L ratio = (total / invested) - 1
        pnl_ratio = pnl_cny / cum_cny_invested if cum_cny_invested else 0.0
        day_record.update({
            "cum_cny_invested":  round(cum_cny_invested, 2),
            "cum_cny_dividends":  round(cum_cny_dividends, 2),
            "total_cny_value":    round(total_cny, 2),
            "pnl_cny":            round(pnl_cny, 2),
            "pnl_ratio":          round(pnl_ratio, 6),
            "shares_QQQ":  round(shares["QQQ"],  6),
            "shares_QLD":  round(shares["QLD"],  6),
            "shares_TQQQ": round(shares["TQQQ"], 6),
        })
        rows.append(day_record)

    df = pd.DataFrame(rows)
    df = df.fillna(0)
    return df


def save_outputs(df: pd.DataFrame):
    portfolio_path = os.path.join(DATA_DIR, "portfolio.csv")
    df.to_csv(portfolio_path, index=False)
    # latest snapshot
    if df.empty:
        return
    last = df.iloc[-1].to_dict()
    # convert dates back to strings for JSON
    summary = {
        "as_of":              last["date"],
        "cum_cny_invested":   last["cum_cny_invested"],
        "total_cny_value":     last["total_cny_value"],
        "pnl_cny":            last["pnl_cny"],
        "pnl_ratio":          last["pnl_ratio"],
        "shares": {k: last[f"shares_{k}"] for k in ("QQQ", "QLD", "TQQQ")},
        "last_close": {k: last.get(f"{k}_close", 0.0) for k in ("QQQ", "QLD", "TQQQ")},
        "days_so_far":        len(df),
    }
    with open(os.path.join(DATA_DIR, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"Wrote {portfolio_path} ({len(df)} rows)")
    print(f"Latest: invested ¥{summary['cum_cny_invested']:,.2f}  value ¥{summary['total_cny_value']:,.2f}  P&L ¥{summary['pnl_cny']:+,.2f}  ({summary['pnl_ratio']*100:+.2f}%)")


def main():
    df = build_portfolio()
    save_outputs(df)


if __name__ == "__main__":
    main()
