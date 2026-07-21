"""
fetch_ndx.py
============
Fetch daily OHLC data for the Nasdaq-100 index (^NDX) from Yahoo Finance,
starting 2019-01-01, and write three output files:

    data/history.csv   full daily history (Date, Open, Close, High, Low, Volume, Adj Close)
    data/latest.json   snapshot of the most recent trading day
    data/meta.json     metadata about the dataset / source

Run:
    python src/fetch_ndx.py

The script exits non-zero if the download fails or the data does not pass
validation, so that a CI workflow fails loudly instead of committing bad files.

IMPORTANT: The one and only legal ticker for this project is `^NDX`
(Nasdaq-100 index). This is NOT QQQ and NOT plain `NDX`.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

# --------------------------------------------------------------------------- #
# Constants — these are intentionally hard-coded and validated at runtime so
# the ticker can never be silently changed by an env var or a caller.
# --------------------------------------------------------------------------- #
TICKER = "^NDX"
START_DATE = "2019-01-01"
SOURCE_NAME = "Yahoo Finance"
SOURCE_URL = "https://finance.yahoo.com/quote/%5ENDX/history/"

# Column requirements
REQUIRED_COLUMNS = ["Date", "Open", "Close"]
OPTIONAL_COLUMNS = ["High", "Low", "Volume", "Adj Close"]
OUTPUT_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

# Paths (relative to repo root, resolved from this file's location)
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
HISTORY_CSV = DATA_DIR / "history.csv"
HISTORY_JSON = DATA_DIR / "history.json"
RECENT_JSON = DATA_DIR / "recent_30d.json"
RECENT_DAYS = 30
LATEST_JSON = DATA_DIR / "latest.json"
META_JSON = DATA_DIR / "meta.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)
log = logging.getLogger("fetch_ndx")


class DataError(Exception):
    """Raised when downloaded data is missing, empty, or malformed."""


# --------------------------------------------------------------------------- #
# Download
# --------------------------------------------------------------------------- #
def download_history(ticker: str, start: str) -> pd.DataFrame:
    """Download daily history from Yahoo Finance and return a clean DataFrame."""
    if ticker != TICKER:
        raise DataError(f"Refusing to download: ticker must be {TICKER!r}, got {ticker!r}")

    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log.info("Downloading %s daily data from %s to %s (%s)", ticker, start, end, SOURCE_NAME)

    raw = yf.download(
        tickers=ticker,
        start=start,
        interval="1d",
        auto_adjust=False,   # keep a separate "Adj Close" column
        actions=False,
        progress=False,
        threads=False,
    )

    if raw is None or raw.empty:
        raise DataError(f"No data returned for {ticker!r}. Download failed or symbol is wrong.")

    # yfinance may return a MultiIndex column layout (one level per ticker).
    if isinstance(raw.columns, pd.MultiIndex):
        # Drop the ticker level, keep the OHLC level.
        raw.columns = raw.columns.get_level_values(0)

    df = raw.reset_index()

    # Normalise the date column name (yfinance uses "Date" or "Datetime").
    if "Date" not in df.columns:
        if "Datetime" in df.columns:
            df = df.rename(columns={"Datetime": "Date"})
        elif "index" in df.columns:
            df = df.rename(columns={"index": "Date"})
        else:
            raise DataError(f"Could not find a date column. Columns seen: {list(df.columns)}")

    return df


# --------------------------------------------------------------------------- #
# Shape / clean
# --------------------------------------------------------------------------- #
def shape_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Select known columns, dedupe, and sort ascending by Date."""
    # Verify the required columns actually exist before we go further.
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise DataError(
            f"Downloaded data is missing required column(s): {missing}. "
            f"Columns seen: {list(df.columns)}"
        )

    keep = [c for c in OUTPUT_COLUMNS if c in df.columns]
    df = df[keep].copy()

    # Normalise Date to a plain YYYY-MM-DD string (no time / tz component).
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")

    # Drop rows with no Open AND no Close — those carry no useful price info.
    df = df.dropna(subset=["Open", "Close"], how="all")

    # One row per trading day; keep the last occurrence if duplicated.
    df = df.drop_duplicates(subset=["Date"], keep="last")

    # Ascending by date.
    df = df.sort_values("Date").reset_index(drop=True)

    return df


# --------------------------------------------------------------------------- #
# Validate
# --------------------------------------------------------------------------- #
def validate(df: pd.DataFrame) -> None:
    """Fail hard if the data does not meet the project's guarantees."""
    if df.empty:
        raise DataError("Validation failed: dataframe is empty.")

    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            raise DataError(f"Validation failed: required column {col!r} is missing.")

    if df["Date"].duplicated().any():
        dups = df.loc[df["Date"].duplicated(), "Date"].tolist()
        raise DataError(f"Validation failed: duplicate dates found: {dups[:5]} ...")

    if not df["Date"].is_monotonic_increasing:
        raise DataError("Validation failed: dates are not sorted ascending.")

    # Open / Close must be parseable numbers and not entirely empty.
    for col in ("Open", "Close"):
        numeric = pd.to_numeric(df[col], errors="coerce")
        if numeric.notna().sum() == 0:
            raise DataError(f"Validation failed: column {col!r} has no numeric values.")

    log.info("Validation passed: %d rows, %s .. %s",
             len(df), df["Date"].iloc[0], df["Date"].iloc[-1])


def sanity_check_against_existing(new_df: pd.DataFrame) -> None:
    """
    Soft guard: if a previous history.csv exists, warn (do not fail) when the
    new row count drops sharply — that usually signals a partial/broken fetch.
    """
    if not HISTORY_CSV.exists():
        return
    try:
        old = pd.read_csv(HISTORY_CSV)
    except Exception as exc:  # noqa: BLE001 - best-effort guard only
        log.warning("Could not read existing history.csv for sanity check: %s", exc)
        return

    if len(old) > 100 and len(new_df) < len(old) * 0.8:
        raise DataError(
            f"Validation failed: new row count ({len(new_df)}) dropped more than "
            f"20% below existing ({len(old)}). Aborting to avoid overwriting good data."
        )


# --------------------------------------------------------------------------- #
# Write outputs
# --------------------------------------------------------------------------- #
def write_history(df: pd.DataFrame) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(HISTORY_CSV, index=False, encoding="utf-8")
    log.info("Wrote %s (%d rows)", HISTORY_CSV.relative_to(REPO_ROOT), len(df))


def write_latest(df: pd.DataFrame, now_utc: str) -> None:
    last = df.iloc[-1]
    payload = {
        "ticker": TICKER,
        "source": SOURCE_NAME,
        "last_trading_date": str(last["Date"]),
        "open": _to_float(last["Open"]),
        "close": _to_float(last["Close"]),
        "updated_at_utc": now_utc,
    }
    LATEST_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log.info("Wrote %s (last_trading_date=%s)", LATEST_JSON.relative_to(REPO_ROOT), payload["last_trading_date"])


def _records(df: pd.DataFrame) -> list[dict]:
    """Turn a DataFrame into a list of one dict per trading day (AI-friendly)."""
    price_cols = [c for c in ("Open", "Close", "High", "Low", "Adj Close") if c in df.columns]
    records = []
    for _, row in df.iterrows():
        rec: dict = {"Date": str(row["Date"])}
        for c in price_cols:
            rec[c] = _to_float(row[c])
        if "Volume" in df.columns:
            try:
                rec["Volume"] = int(row["Volume"])
            except (TypeError, ValueError):
                rec["Volume"] = None
        records.append(rec)
    return records


def _write_json_window(path: Path, df: pd.DataFrame, now_utc: str, extra: dict | None = None) -> None:
    """Write a self-describing JSON: ticker/source/fields metadata + data array."""
    payload = {
        "ticker": TICKER,
        "source": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "last_updated_utc": now_utc,
        "row_count": int(len(df)),
        "fields": list(df.columns),
    }
    if extra:
        payload.update(extra)
    payload["data"] = _records(df)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log.info("Wrote %s (%d records)", path.relative_to(REPO_ROOT), payload["row_count"])


def write_history_json(df: pd.DataFrame, now_utc: str) -> None:
    """Full history as a self-describing JSON — the AI-friendly format."""
    _write_json_window(HISTORY_JSON, df, now_utc, extra={"start_date": START_DATE})


def write_recent_json(df: pd.DataFrame, now_utc: str) -> None:
    """Last RECENT_DAYS trading days — a small, token-cheap window for AI tools."""
    window = df.tail(RECENT_DAYS)
    extra = {
        "window": f"last {RECENT_DAYS} trading days",
        "date_range": [str(window["Date"].iloc[0]), str(window["Date"].iloc[-1])],
    }
    _write_json_window(RECENT_JSON, window, now_utc, extra=extra)


def write_meta(df: pd.DataFrame, now_utc: str) -> None:
    payload = {
        "ticker": TICKER,
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "start_date": START_DATE,
        "last_updated_utc": now_utc,
        "row_count": int(len(df)),
        "fields": list(df.columns),
    }
    META_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log.info("Wrote %s (row_count=%d)", META_JSON.relative_to(REPO_ROOT), payload["row_count"])


def _to_float(value) -> float | None:
    try:
        f = float(value)
        return round(f, 2)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    try:
        raw = download_history(TICKER, START_DATE)
        df = shape_frame(raw)
        validate(df)
        sanity_check_against_existing(df)

        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        write_history(df)
        write_history_json(df, now_utc)
        write_recent_json(df, now_utc)
        write_latest(df, now_utc)
        write_meta(df, now_utc)

        log.info("Done. Ticker=%s, rows=%d", TICKER, len(df))
        return 0
    except DataError as exc:
        log.error("DATA ERROR: %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001 - top-level guard for CI
        log.exception("UNEXPECTED ERROR: %s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
