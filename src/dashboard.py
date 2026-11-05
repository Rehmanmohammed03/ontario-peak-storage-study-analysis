"""Builds the interactive dashboard (docs/index.html) for GitHub Pages.

The page is one self-contained HTML file: the study results are embedded as JSON and the
charts are drawn in the browser, so it needs no server. Rerunning run_study.py rebuilds it.
"""
from __future__ import annotations

import json
import os
import shutil

import numpy as np
import pandas as pd

from . import netload, storage

SOLAR_STEPS_GW = [0, 1, 2, 3, 4, 5]


def storage_grid(scenarios: dict, solar_profile: pd.Series, sizes, durations, rte) -> pd.DataFrame:
    """Peak reduction for every (scenario, extra solar, duration, size) combination.

    Same method as storage.sweep, but faster: days are checked from the highest original peak
    down, and the search stops once a day's original peak is below the worst shaved peak found
    so far (shaving can only lower a day's peak, so later days cannot change the answer).
    """
    rows = []
    for name, net in scenarios.items():
        for gw in SOLAR_STEPS_GW:
            s = net - solar_profile * gw * 1000
            days = sorted((g.to_numpy(float) for _, g in s.groupby(s.index.date)), key=lambda a: -a.max())
            base = days[0].max()
            for h in durations:
                for p in sizes:
                    worst = 0.0
                    for a in days:
                        if a.max() <= worst:
                            break
                        worst = max(worst, storage.shave_day(a, p, p * h, rte)[1])
                    rows.append({"scenario": name, "solar_gw": gw, "duration_h": h, "power_mw": p,
                                 "base_peak_mw": base, "new_peak_mw": worst, "reduction_mw": base - worst})
    return pd.DataFrame(rows)


def build(res: dict, df: pd.DataFrame, hist: pd.DataFrame, grid: pd.DataFrame, n1: pd.DataFrame,
          growth_2035: float, solar_profile: pd.Series, out_dir: str, report_pdf: str | None = None,
          repo_url: str | None = None) -> str:
    os.makedirs(out_dir, exist_ok=True)
    pk = pd.Timestamp(res["demand_full_year"]["peak_time"])
    day = df.loc[str(pk.date())]
    payload = {
        "year": res["year"],
        "rte": res["storage"]["rte"],
        "growth2035": growth_2035,
        "peak": {"mw": res["demand_full_year"]["peak_mw"], "date": f"{pk:%B %d, %Y}",
                 "he": res["demand_full_year"]["peak_hour_ending"], "energy_twh": res["demand_full_year"]["energy_twh"],
                 "net_mw": res["net_load"]["peak_mw"], "wind_at_peak": res["at_peak"]["WIND"],
                 "solar_at_peak": res["at_peak"]["SOLAR"], "hours_within_5pct": res["net_load"]["hours_within_5pct"]},
        "peakDay": {"date": f"{pk:%B %d, %Y}",
                    "demand": day["Ontario Demand"].round(1).tolist(), "wind": day["WIND"].round(1).tolist(),
                    "solar": day["SOLAR"].round(1).tolist(), "solarPerMW": solar_profile.loc[str(pk.date())].round(4).tolist()},
        "grid": grid[["scenario", "solar_gw", "duration_h", "power_mw", "base_peak_mw", "new_peak_mw", "reduction_mw"]]
                .round(1).to_dict("list"),
        "history": {"year": hist.index.tolist(), "peak": hist.peak_mw.tolist(), "he": hist.peak_hour_ending.tolist(),
                    "season": hist.season.tolist(), "date": [str(d) for d in hist.peak_date]},
        "n1": n1[["scenario", "battery", "dispatch_mw", "system_load_mw", "violating", "overload_cases",
                  "low_voltage_cases", "unsolved", "worst_loading_pct", "lowest_v_pu", "worst_contingency"]]
              .round(3).to_dict("records"),
        "network": {k: res["network"][k] for k in ("battery_mw", "best_bus")},
        "data": res["data"],
        "fuel": res["fuel_twh"],
        "phShift": res["peak_hour_shift"],
        "report": bool(report_pdf),
        "repo": repo_url,
    }
    if report_pdf:
        shutil.copy(report_pdf, os.path.join(out_dir, "Study_Report.pdf"))
    with open(os.path.join(os.path.dirname(__file__), "dashboard_template.html"), encoding="utf-8") as f:
        html = f.read()
    html = html.replace("/*__DATA__*/null", json.dumps(payload, default=str, separators=(",", ":")))
    path = os.path.join(out_dir, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
