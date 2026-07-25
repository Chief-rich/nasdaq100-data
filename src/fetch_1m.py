"""
fetch_1m.py
===========
Fetch 1-minute bars for every configured instrument and APPEND them to a
growing on-disk store. Yahoo only serves the last ~30 days of 1m data, so each
run grabs what's currently available and merges it (de-duplicated) into
history.csv — over time the file accumulates far beyond Yahoo's 30-day window.

    ^NDX  (index, regular session only) -> data/ndx_1m/history.csv
    NQ=F  (futures, near 24h w/ globex)  -> data/nq_1m/history.csv

Run:
    python src/fetch_1m.py

A single instrument failing (e.g. Yahoo hiccup) is logged but does not abort
the others; the run only exits non-zero if EVERY instrument fails.
"""

from __future__ import annotations

import sys

import market_lib as m

DAYS = 30  # how far back to try each run (Yahoo's hard ceiling for 1m)

INSTRUMENTS = [
    {
        "ticker": "^NDX",
        "outdir": m.DATA_DIR / "ndx_1m",
        "source_url": "https://finance.yahoo.com/quote/%5ENDX/history/",
        "session": "US regular session (09:30-16:00 ET)",
    },
    {
        "ticker": "NQ=F",
        "outdir": m.DATA_DIR / "nq_1m",
        "source_url": "https://finance.yahoo.com/quote/NQ%3DF/history/",
        "session": "CME near-24h (globus/overnight included)",
    },
]


def run_one(cfg: dict, now_utc: str) -> int:
    m.log.info("=== 1m %s ===", cfg["ticker"])
    raw = m.download_1m(cfg["ticker"], days=DAYS)
    fresh = m.shape_1m(raw)
    store = cfg["outdir"] / "history.csv"
    merged = m.accumulate_1m(store, fresh)
    m.write_1m_outputs(merged, cfg["outdir"], cfg["ticker"], cfg["source_url"],
                       cfg["session"], now_utc)
    return len(merged)


def main() -> int:
    now_utc = m.now_utc_iso()
    failures = 0
    for cfg in INSTRUMENTS:
        try:
            run_one(cfg, now_utc)
        except Exception as exc:  # noqa: BLE001
            m.log.error("1m FAILED for %s: %s", cfg["ticker"], exc)
            failures += 1
    if failures == len(INSTRUMENTS):
        m.log.error("All 1m instruments failed")
        return 1
    if failures:
        m.log.warning("%d of %d 1m instruments failed (continuing)", failures, len(INSTRUMENTS))
    m.log.info("1m accumulation done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
