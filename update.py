"""
One-shot update: pull latest prices, recompute portfolio, regenerate site.
Intended to be invoked by cron daily (or manually).

Crontab example (run at 16:30 ET on US trading days, i.e. after market close):
  30 16 * * 1-5  cd /path/to/dca_site && python3 update.py >> update.log 2>&1
"""
import os
import sys
import subprocess
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))


def run(cmd):
    print(f"\n$ {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=HERE)
    if res.returncode != 0:
        print(f"!! command failed with exit {res.returncode}")
        sys.exit(res.returncode)


def main():
    print(f"=== {__file__} started at {__import__('datetime').datetime.now():%Y-%m-%d %H:%M:%S} ===")
    try:
        run([sys.executable, "fetch_data.py"])
        run([sys.executable, "dca_engine.py"])
        run([sys.executable, "build_site.py"])
    except Exception as e:
        print(f"!! error: {e}")
        traceback.print_exc()
        sys.exit(1)
    print("=== update completed ===")


if __name__ == "__main__":
    main()
