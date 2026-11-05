"""Load IESO public data.

Two IESO public reports are used:
  * Hourly Demand Report  (PUB_Demand_<year>.csv): Ontario Demand and Market Demand, MW, each hour.
  * Generator Output Capability Month Report (PUB_GenOutputCapabilityMonth_<yyyymm>.csv):
    hourly output of every transmission-connected generator of 20 MW or more, with its fuel type.

The loader first tries to download each file from IESO's public reports site. If that fails
(no internet, site down), it uses the local copy in data/ieso/. Every result is traceable
to an IESO file name.
"""
from __future__ import annotations

import glob
import os
import urllib.request

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "ieso")
IESO_BASE = "https://reports-public.ieso.ca/public"
HOURS = [f"Hour {i}" for i in range(1, 25)]


def _fetch(url: str, dest: str, refresh: bool) -> bool:
    """Download url to dest. Returns True if a fresh copy was saved."""
    if os.path.exists(dest) and not refresh:
        return False
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ontario-storage-study"})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
        if len(body) < 1000:
            return False
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(body)
        return True
    except Exception:
        return False


def download(years=(2025,), demand_years=range(2003, 2026), refresh=False) -> list[str]:
    """Download the IESO report files into data/ieso/. Returns the files that were downloaded.

    demand_years: Hourly Demand Reports to fetch. years: years of monthly generator reports.
    Files that cannot be downloaded keep their existing local copy.
    """
    got = []
    for y in demand_years:
        dest = os.path.join(DATA, "demand", f"PUB_Demand_{y}.csv")
        if _fetch(f"{IESO_BASE}/Demand/PUB_Demand_{y}.csv", dest, refresh):
            got.append(dest)
    for y in years:
        for m in range(1, 13):
            name = f"PUB_GenOutputCapabilityMonth_{y}{m:02d}.csv"
            dest = os.path.join(DATA, "generation", name)
            if _fetch(f"{IESO_BASE}/GenOutputCapabilityMonth/{name}", dest, refresh):
                got.append(dest)
    return got


def _stamp(date: pd.Series, hour: pd.Series) -> pd.DatetimeIndex:
    """IESO hours are 'hour ending' in Eastern Standard Time (1..24). Return hour-beginning stamps."""
    return pd.to_datetime(date) + pd.to_timedelta(hour.astype(int) - 1, unit="h")


def load_demand(year: int) -> pd.DataFrame:
    """Hourly Ontario Demand and Market Demand (MW) for one year."""
    f = os.path.join(DATA, "demand", f"PUB_Demand_{year}.csv")
    d = pd.read_csv(f, skiprows=3)
    d.columns = [c.strip() for c in d.columns]
    d.index = _stamp(d["Date"], d["Hour"])
    d = d[["Ontario Demand", "Market Demand"]].astype(float)
    d.attrs["source"] = os.path.basename(f)
    return d


def demand_years() -> list[int]:
    fs = glob.glob(os.path.join(DATA, "demand", "PUB_Demand_*.csv"))
    return sorted(int(os.path.basename(f)[11:15]) for f in fs)


def load_generation_by_fuel(year: int) -> pd.DataFrame:
    """Hourly output (MW) summed by fuel type, plus solar and wind available capacity."""
    fs = sorted(glob.glob(os.path.join(DATA, "generation", f"PUB_GenOutputCapabilityMonth_{year}*.csv")))
    if len(fs) != 12:
        raise FileNotFoundError(f"Expected 12 monthly generator files for {year}, found {len(fs)}")
    # Rows end with a trailing comma, so index_col=False keeps the columns aligned.
    raw = pd.concat([pd.read_csv(f, skiprows=3, index_col=False) for f in fs], ignore_index=True)
    raw[HOURS] = raw[HOURS].apply(pd.to_numeric, errors="coerce")  # blanks = not reported
    out = {}
    for meas, tag in [("Output", ""), ("Available Capacity", " avail")]:
        sub = raw[raw["Measurement"] == meas]
        g = sub.groupby(["Delivery Date", "Fuel Type"])[HOURS].sum(min_count=1)
        long = g.stack().rename("MW").reset_index()
        long.columns = ["date", "fuel", "hour", "MW"]
        long["hour"] = long["hour"].str.replace("Hour ", "").astype(int)
        wide = long.pivot_table(index=["date", "hour"], columns="fuel", values="MW", aggfunc="sum")
        wide.columns = [c + tag for c in wide.columns]
        out[meas] = wide
    gen = out["Output"].join(out["Available Capacity"])
    gen.index = _stamp(pd.Series(gen.index.get_level_values(0)), pd.Series(gen.index.get_level_values(1)))
    gen = gen.sort_index().fillna(0.0)
    gen.attrs["source"] = f"{len(fs)} x PUB_GenOutputCapabilityMonth_{year}MM.csv"
    gen.attrs["generators"] = raw["Generator"].nunique()
    return gen
