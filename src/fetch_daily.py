"""
fetch_daily.py
==============
Fetch daily OHLC (2019-01-01 -> today) for every configured instrument and
write the standard output set (history.csv/json, recent_30d.json, latest.json,
meta.json).

    ^NDX  (Nasdaq-100 index)          -> data/          (repo root, unchanged URLs)
    NQ=F  (E-mini Nasdaq-100 futures) -> data/nq_daily/

Run:
    python src/fetch_daily.py

Exits non-zero if any instrument fails validation, so CI fails loudly.
"""

from __future__ import annotations

import sys

import market_lib as m

START_DATE = "2019-01-01"

# ticker is hard-coded per instrument and validated at download time so it can
# never be silently swapped by an env var or caller.
INSTRUMENTS = [
    {
        "ticker": "^NDX",
        "outdir": m.DATA_DIR,  # repo root data/ — keeps existing ^NDX file URLs
        "source_url": "https://finance.yahoo.com/quote/%5ENDX/history/",
        "note": "Nasdaq-100 index (NOT QQQ, NOT plain NDX)",
    },
    {
        "ticker": "NQ=F",
        "outdir": m.DATA_DIR / "nq_daily",
        "source_url": "https://finance.yahoo.com/quote/NQ%3DF/history/",
        "note": "E-mini Nasdaq-100 futures, continuous front-month",
    },
]


def run_one(cfg: dict, now_utc: str) -> None:
    m.log.info("=== DAILY %s (%s) ===", cfg["ticker"], cfg["note"])
    raw = m.download_daily(cfg["ticker"], START_DATE)
    df = m.shape_daily(raw)
    m.validate_daily(df)
    m.write_daily_outputs(df, cfg["outdir"], cfg["ticker"], cfg["source_url"],
                          START_DATE, now_utc)


def main() -> int:
    now_utc = m.now_utc_iso()
    failures = 0
    for cfg in INSTRUMENTS:
        try:
            run_one(cfg, now_utc)
        except m.DataError as exc:
            m.log.error("DATA ERROR for %s: %s", cfg["ticker"], exc)
            failures += 1
        except Exception as exc:  # noqa: BLE001
            m.log.exception("UNEXPECTED ERROR for %s: %s", cfg["ticker"], exc)
            failures += 1
    if failures:
        m.log.error("%d instrument(s) failed", failures)
        return 1
    m.log.info("All daily instruments done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
