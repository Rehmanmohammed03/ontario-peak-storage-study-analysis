"""Peak shaving with energy-limited storage.

For every day, the battery discharges during the highest hours to bring that day's load down
to the lowest possible level T, limited by its power P (MW) and energy E (MWh). It recharges
the same day in the lowest-load hours, needing E_used / efficiency, without creating a new
peak above T. This is an upper bound on what storage can do: it assumes perfect foresight of
each day's load and a full battery every morning.

The annual result is the new annual peak, so the capacity value of a fleet is
(old annual peak - new annual peak).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _fill_level(load: np.ndarray, mask: np.ndarray, energy: float, p: float) -> float:
    """Water-fill level V so that sum(clip(V - load, 0, p)) over masked hours == energy."""
    lo, hi = load[mask].min(), load[mask].max() + p
    for _ in range(60):
        v = 0.5 * (lo + hi)
        if np.clip(v - load[mask], 0, p).sum() < energy:
            lo = v
        else:
            hi = v
    return hi


def shave_day(load: np.ndarray, p: float, e: float, rte: float) -> tuple[np.ndarray, float]:
    """Return (new hourly load, daily peak) after the best discharge/recharge for one day."""
    peak = load.max()
    if p <= 0 or e <= 0:
        return load.copy(), peak

    def schedule(t):
        dis = np.clip(load - t, 0, p)
        if dis.sum() > e + 1e-6:
            return None
        idle = dis == 0
        need = dis.sum() / rte
        if need > 0:
            if idle.sum() == 0:
                return None
            v = _fill_level(load, idle, need, p)
            ch = np.where(idle, np.clip(v - load, 0, p), 0.0)
            if ch.sum() < need - 1e-3:
                return None
        else:
            ch = np.zeros_like(load)
        new = load - dis + ch
        return new if new.max() <= t + 1e-3 else None

    lo, hi = max(peak - p, load.min()), peak  # hi is always feasible (no discharge)
    best = load.copy()
    for _ in range(50):
        t = 0.5 * (lo + hi)
        s = schedule(t)
        if s is None:
            lo = t
        else:
            hi, best = t, s
    return best, best.max()


def shave(series: pd.Series, p_mw: float, hours: float, rte: float = 0.85) -> pd.Series:
    """Apply daily peak shaving to an hourly series. Returns the new hourly series."""
    out = series.copy()
    for _, idx in series.groupby(series.index.date).groups.items():
        day = series.loc[idx].to_numpy(dtype=float)
        new, _ = shave_day(day, p_mw, p_mw * hours, rte)
        out.loc[idx] = new
    return out


def sweep(series: pd.Series, sizes_mw, durations_h, rte: float = 0.85) -> pd.DataFrame:
    """Annual peak reduction for every (power, duration) pair.

    Only the days whose peak could end up as the annual peak matter, so days whose original
    peak is below (annual peak - largest battery) are skipped; their peak can never be higher
    than the shaved annual peak. This keeps the sweep fast without changing the answer.
    """
    base = series.max()
    daily_peak = series.groupby(series.index.date).max()
    rows = []
    for h in durations_h:
        for p in sizes_mw:
            cand = daily_peak[daily_peak > base - p - 1].index
            worst = 0.0
            for d in cand:
                day = series[series.index.date == d].to_numpy(dtype=float)
                _, pk = shave_day(day, p, p * h, rte)
                worst = max(worst, pk)
            others = daily_peak.drop(cand).max() if len(cand) < len(daily_peak) else 0.0
            new_peak = max(worst, others)
            rows.append({"duration_h": h, "power_mw": p, "new_peak_mw": new_peak,
                         "reduction_mw": base - new_peak, "capacity_value_pct": 100 * (base - new_peak) / p})
    out = pd.DataFrame(rows)
    out["marginal_mw_per_mw"] = (
        out.groupby("duration_h")["reduction_mw"].diff()
        / out.groupby("duration_h")["power_mw"].diff()
    )
    return out


def full_capacity_limit(df: pd.DataFrame, duration_h: float, threshold_pct=95.0) -> float:
    """Largest battery size in the sweep that still delivers >= threshold% of its rating."""
    s = df[(df.duration_h == duration_h) & (df.capacity_value_pct >= threshold_pct)]
    return float(s.power_mw.max()) if len(s) else 0.0
