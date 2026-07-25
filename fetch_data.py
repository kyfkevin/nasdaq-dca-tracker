"""
Fetch QQQ / QLD / TQQQ daily OHLC from Tencent Finance.

Output: data/price_<TICKER>.csv with columns:
  date, open, high, low, close, prev_close, volume, change_pct
"""
from __future__ import annotations
import os
import sys
import time
import argparse
from datetime import datetime
import urllib.request
import urllib.error
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Map our internal ticker to Tencent's qt.gtimg.cn symbol
TICKERS = {
    "QQQ":  "usQQQ",
    "QLD":  "usQLD",
    "TQQQ": "usTQQQ",
}


def _split_payline(line: str):
    if not line.startswith("v_"):
        return None
    body = line.split("=", 1)[1].strip().strip('";\n ')
    return body.split("~")


def fetch_one(symbol: str) -> dict | None:
    url = f"https://qt.gtimg.cn/q={symbol}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read().decode("gbk", errors="ignore")
    except urllib.error.URLError as e:
        print(f"  ! {symbol} network error: {e}")
        return None
    parts = _split_payline(raw)
    if not parts or len(parts) < 35:
        print(f"  ! {symbol} malformed response: {raw[:80]!r}")
        return None
    try:
        cur      = float(parts[3])
        prev     = float(parts[4])
        op       = float(parts[5])
        vol      = int(float(parts[6] or "0"))
        ts       = parts[30]
        chg_pct  = float(parts[32]) if parts[32] else 0.0
        hi52     = float(parts[33]) if parts[33] else 0.0
        lo52     = float(parts[34]) if parts[34] else 0.0
        date_str = ts.split(" ")[0] if " " in ts else ts
        return {
            "date":       date_str,
            "open":       op,
            "high":       hi52,
            "low":        lo52,
            "close":      cur,
            "prev_close": prev,
            "volume":     vol,
            "change_pct": chg_pct,
        }
    except (ValueError, IndexError) as e:
        print(f"  ! {symbol} parse error: {e}; raw[:120]={raw[:120]!r}")
        return None


def fetch_all() -> dict[str, dict]:
    out = {}
    for name, sym in TICKERS.items():
        data = fetch_one(sym)
        if data:
            out[name] = data
        time.sleep(0.3)
    return out


def append_to_csv(records: dict[str, dict]):
    for name, rec in records.items():
        path = os.path.join(DATA_DIR, f"price_{name}.csv")
        if os.path.exists(path):
            df = pd.read_csv(path)
            df["date"] = pd.to_datetime(df["date"])
        else:
            df = pd.DataFrame(columns=["date", "open", "high", "low", "close",
                                        "prev_close", "volume", "change_pct"])
            df["date"] = pd.to_datetime(df["date"])
        rec_date = pd.to_datetime(rec["date"]).normalize()
        # overwrite today's row if it exists (intraday update)
        df = df[df["date"].dt.normalize() != rec_date]
        new_row = {
            "date":       rec["date"],
            "open":       rec["open"],
            "high":       rec["high"],
            "low":        rec["low"],
            "close":      rec["close"],
            "prev_close": rec["prev_close"],
            "volume":     rec["volume"],
            "change_pct": rec["change_pct"],
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df = df.sort_values("date").reset_index(drop=True)
        df.to_csv(path, index=False)
        print(f"  + {name}: {rec['date']}  open={rec['open']}  close={rec['close']}  ({rec['change_pct']:+.2f}%)")


def main():
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Fetching from qt.gtimg.cn ...")
    recs = fetch_all()
    if not recs:
        print("No data fetched; aborting.")
        sys.exit(1)
    append_to_csv(recs)
    print("Done.")


if __name__ == "__main__":
    main()
