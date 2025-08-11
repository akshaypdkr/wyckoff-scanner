#!/usr/bin/env python3
"""
nse_wyckoff_scanner.py
- Scans NIFTY-500 symbols
- Uses yfinance to fetch OHLCV
- Detects simple Wyckoff-style "markup" candidates
- Writes data to data/markup_candidates.json and data/markup_stock_data.json
"""

import os
import time
import json
from datetime import datetime
import requests
import yfinance as yf
import pandas as pd

# ---------- CONFIG ----------
LOOKBACK_DAYS = 200
ACCUMULATION_RANGE = 30
BREAKOUT_THRESHOLD = 0.05      # 5% above accumulation high
VOLUME_MULTIPLIER = 1.5
USER_AGENT = "Mozilla/5.0 (compatible; WyckoffScanner/1.0)"
DATA_DIR = "data"

os.makedirs(DATA_DIR, exist_ok=True)

# ---------- HELPERS ----------
def get_nse_symbol_list():
    url = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500"
    headers = {"User-Agent": USER_AGENT}
    s = requests.Session()
    s.headers.update(headers)
    try:
        s.get("https://www.nseindia.com", timeout=10)  # get cookies
        r = s.get(url, timeout=10)
        data = r.json()
        symbols = [item["symbol"] + ".NS" for item in data.get("data", []) if item.get("symbol")]
        print(f"Fetched {len(symbols)} symbols from NSE.")
        return symbols
    except Exception as e:
        print("Warning: couldn't fetch NIFTY500 from NSE (blocked or offline). Using fallback list.", e)
        return ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "LT.NS"]

def detect_markup(df):
    try:
        if len(df) < ACCUMULATION_RANGE:
            return False
        recent = df[-ACCUMULATION_RANGE:]
        acc_high = recent["High"].max()
        last_close = df["Close"].iloc[-1]
        breakout = last_close > acc_high * (1 + BREAKOUT_THRESHOLD)
        avg_vol = recent["Volume"].mean()
        vol_breakout = df["Volume"].iloc[-1] > avg_vol * VOLUME_MULTIPLIER

        recent_10 = df[-10:]
        if len(recent_10) < 2:
            return breakout and vol_breakout
        higher_highs = all(recent_10["High"].iloc[i] >= recent_10["High"].iloc[i-1]
                           for i in range(1, len(recent_10)))
        higher_lows = all(recent_10["Low"].iloc[i] >= recent_10["Low"].iloc[i-1]
                          for i in range(1, len(recent_10)))
        return breakout and vol_breakout and (higher_highs or higher_lows)
    except Exception as e:
        print("detect_markup error:", e)
        return False

# ---------- MAIN ----------
def main():
    symbols = get_nse_symbol_list()
    markup_candidates = []
    markup_data = {}

    print(f"Scanning {len(symbols)} symbols (this may take several minutes)...")
    for i, sym in enumerate(symbols, 1):
        try:
            df = yf.download(sym, period=f"{LOOKBACK_DAYS}d", interval="1d", progress=False)
            if df.empty:
                print(f"[{i}/{len(symbols)}] No data for {sym}")
                continue
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            if detect_markup(df):
                name = sym.replace(".NS", "")
                markup_candidates.append(name)
                # convert to list of dicts; Date will be JSON serialised as string
                markup_data[name] = df.reset_index().to_dict(orient="records")
                print(f"[{i}/{len(symbols)}] MARKUP -> {name}")
            else:
                print(f"[{i}/{len(symbols)}] OK -> {sym}")
        except Exception as e:
            print(f"[{i}/{len(symbols)}] Error {sym}: {e}")
        time.sleep(0.2)

    summary = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total_scanned": len(symbols),
        "markup_count": len(markup_candidates),
        "markup_candidates": markup_candidates
    }

    with open(os.path.join(DATA_DIR, "markup_candidates.json"), "w") as f:
        json.dump(summary, f, indent=2)

    with open(os.path.join(DATA_DIR, "markup_stock_data.json"), "w") as f:
        json.dump(markup_data, f, indent=2, default=str)

    print("\nScan complete.")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
