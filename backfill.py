"""
Manual backfill: insert historical OHLC for QQQ/QLD/TQQQ when remote
data source is missing or incomplete.

Usage:
  python3 backfill.py --ticker QQQ --date 2026-07-22 --open 690.00 --high 695.00 --low 685.00 --close 688.00

If --open/--high/--low are omitted, they default to --close (so the row
still works for the engine).

Multiple rows can be supplied via a CSV file:
  python3 backfill.py --csv path/to/rows.csv
where rows.csv has columns: date, ticker, open, high, low, close, volume
"""
from __future__ import annotations
import os
import sys
import argparse
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")


def backfill_one(ticker: str, date: str, open_: float, high: float, low: float, close: float, volume: int = 0):
    path = os.path.join(DATA_DIR, f"price_{ticker}.csv")
    if os.path.exists(path):
        df = pd.read_csv(path)
        df["date"] = pd.to_datetime(df["date"])
    else:
        df = pd.DataFrame(columns=["date", "open", "high", "low", "close", "prev_close", "volume", "change_pct"])
        df["date"] = pd.to_datetime(df["date"])
    rec_date = pd.to_datetime(date).normalize()
    df = df[df["date"].dt.normalize() != rec_date]
    # prev close = closest prior close we have (or 0 if none)
    prior = df[df["date"] < rec_date]
    prev_close = float(prior.iloc[-1]["close"]) if len(prior) else 0.0
    chg_pct = ((close / prev_close) - 1.0) * 100 if prev_close else 0.0
    new_row = {
        "date": date, "open": open_, "high": high, "low": low,
        "close": close, "prev_close": prev_close, "volume": volume, "change_pct": round(chg_pct, 2),
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df = df.sort_values("date").reset_index(drop=True)
    df.to_csv(path, index=False)
    print(f"  + {ticker} {date}  O={open_}  H={high}  L={low}  C={close}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ticker", choices=["QQQ", "QLD", "TQQQ"])
    p.add_argument("--date", help="YYYY-MM-DD")
    p.add_argument("--open",  type=float, default=None)
    p.add_argument("--high",  type=float, default=None)
    p.add_argument("--low",   type=float, default=None)
    p.add_argument("--close", type=float)
    p.add_argument("--volume", type=int, default=0)
    p.add_argument("--csv", help="CSV path with date, ticker, open, high, low, close, volume")
    args = p.parse_args()

    if args.csv:
        df = pd.read_csv(args.csv)
        for _, r in df.iterrows():
            backfill_one(
                ticker=r["ticker"], date=r["date"],
                open_=r.get("open", r["close"]), high_=r.get("high", r["close"]),
                low=r.get("low", r["close"]), close=r["close"],
                volume=int(r.get("volume", 0)),
            )
    else:
        if not (args.ticker and args.date and args.close):
            p.error("Provide --ticker --date --close (and optionally O/H/L) or use --csv")
        backfill_one(
            args.ticker, args.date,
            args.open or args.close, args.high or args.close,
            args.low  or args.close, args.close, args.volume,
        )


if __name__ == "__main__":
    main()
