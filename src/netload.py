"""Net load and peak analysis on IESO data."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data

# 2026 Annual Planning Outlook, reference scenario: net annual energy demand grows at about
# 2.1% a year (152 TWh in 2026 to 250 TWh in 2050). Used here only as a uniform growth factor.
APO_REF_CAGR = 0.021


def build_hourly(year: int) -> pd.DataFrame:
    """One row per hour: demand, generation by fuel, and net load (demand minus wind and solar)."""
    dem = data.load_demand(year)
    gen = data.load_generation_by_fuel(year)
    df = dem.join(gen, how="inner")
    for c in ["WIND", "SOLAR"]:
        if c not in df:
            df[c] = 0.0
    df["Net Load"] = df["Ontario Demand"] - df["WIND"] - df["SOLAR"]
    df.attrs["sources"] = [dem.attrs["source"], gen.attrs["source"]]
    df.attrs["generators"] = gen.attrs["generators"]
    df.attrs["missing_hours"] = len(dem) - len(df)
    return df


def peak_summary(s: pd.Series, top_n=100) -> dict:
    """Key facts about the peak of an hourly MW series."""
    t = s.idxmax()
    top = s.nlargest(top_n)
    return {
        "peak_mw": float(s.max()),
        "peak_time": t,
        "peak_hour_ending": t.hour + 1,
        "top_n": top_n,
        "top_n_summer_share": float(top.index.month.isin([6, 7, 8, 9]).mean()),
        "top_n_hour_ending_median": float(np.median(top.index.hour + 1)),
        "hours_within_5pct": int((s >= 0.95 * s.max()).sum()),
        "hours_within_10pct": int((s >= 0.90 * s.max()).sum()),
        "energy_twh": float(s.sum() / 1e6),
        "load_factor": float(s.mean() / s.max()),
    }


def historical_peaks() -> pd.DataFrame:
    """Annual Ontario Demand peak, energy and timing for every year in data/ieso/demand."""
    rows = []
    for y in data.demand_years():
        d = data.load_demand(y)["Ontario Demand"]
        t = d.idxmax()
        rows.append({
            "year": y, "peak_mw": d.max(), "energy_twh": d.sum() / 1e6,
            "peak_date": t.date(), "peak_hour_ending": t.hour + 1,
            "season": "Summer" if t.month in (5, 6, 7, 8, 9) else "Winter",
        })
    return pd.DataFrame(rows).set_index("year")


def growth_factor(target_year: int, base_year: int) -> float:
    return (1 + APO_REF_CAGR) ** (target_year - base_year)


def profile_per_mw(df: pd.DataFrame, fuel: str) -> pd.Series:
    """Hourly output per MW of fleet capacity (0..1), using the fleet's maximum available capacity."""
    cap = df[f"{fuel} avail"].max() if f"{fuel} avail" in df else df[fuel].max()
    return (df[fuel] / cap).clip(0, 1)
