"""Ontario Peak Demand & Storage Adequacy Study: runs every step and writes outputs/.

    python run_study.py            # download the IESO files, then run
    python run_study.py --offline  # use the local copies in data/ieso/
"""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np
import pandas as pd

from src import data, figures, netload, network, storage

YEAR = 2025
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
DOCS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")  # the website folder (Vercel / GitHub Pages)
REPO_URL = "https://github.com/Rehmanmohammed03/ontario-peak-storage-study-analysis"
SIZES = list(range(250, 6001, 250))      # MW of storage tested
DURATIONS = [2, 4, 8]                     # hours
RTE = 0.85                                # round-trip efficiency
EXTRA_SOLAR_GW = [0, 2.5, 5]              # solar sensitivity
NET_BATTERY_MW = 500                      # battery in the 39-bus study (~6.5% of 2035 test-system load)


def main(offline: bool):
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    res = {"year": YEAR}

    # 1. Data --------------------------------------------------------------------------
    res["downloaded_from_ieso"] = [] if offline else [os.path.basename(f) for f in data.download((YEAR,), refresh=True)]
    df = netload.build_hourly(YEAR)
    res["data"] = {"sources": df.attrs["sources"], "hours": len(df), "missing_hours": df.attrs["missing_hours"],
                   # whole days with no hourly data (a single unreported hour is not counted)
                   "missing_days": sorted(str(d) for d, n in pd.Series(1, index=pd.date_range(
                       f"{YEAR}-01-01", periods=8760, freq="h").difference(df.index)).groupby(lambda t: t.date()).sum().items()
                       if n >= 24),
                   "generators": df.attrs["generators"]}
    full_demand = data.load_demand(YEAR)["Ontario Demand"]
    res["demand_full_year"] = netload.peak_summary(full_demand)
    res["fuel_twh"] = {f: round(df[f].sum() / 1e6, 2) for f in ["NUCLEAR", "HYDRO", "GAS", "WIND", "SOLAR", "BIOFUEL"] if f in df}
    print(f"[data] {len(df)} hours, sources: {df.attrs['sources']}")

    # 2. Net load and peaks ------------------------------------------------------------
    hist = netload.historical_peaks()
    hist.to_csv(os.path.join(OUT, "historical_peaks.csv"))
    res["demand"] = netload.peak_summary(df["Ontario Demand"])
    res["net_load"] = netload.peak_summary(df["Net Load"])
    pk = df["Net Load"].idxmax()
    res["at_peak"] = {c: float(df.loc[pk, c]) for c in ["Ontario Demand", "WIND", "SOLAR", "Net Load"]}
    early, late = hist[hist.index <= 2012], hist[hist.index >= 2020]
    res["peak_hour_shift"] = {"early_years": [int(early.index.min()), int(early.index.max())],
                              "early_median_he": float(early.peak_hour_ending.median()),
                              "late_years": [int(late.index.min()), int(late.index.max())],
                              "late_median_he": float(late.peak_hour_ending.median())}
    print(f"[peak] {res['demand']['peak_mw']:.0f} MW demand, {res['net_load']['peak_mw']:.0f} MW net, at {pk}")

    # 3. Storage --------------------------------------------------------------------------
    sw = storage.sweep(df["Net Load"], SIZES, DURATIONS, RTE)
    sw.to_csv(os.path.join(OUT, "storage_sweep_2025.csv"), index=False)
    g35 = netload.growth_factor(2035, YEAR)
    net35 = df["Ontario Demand"] * g35 - df["WIND"] - df["SOLAR"]
    sw35 = storage.sweep(net35, SIZES, DURATIONS, RTE)
    sw35.to_csv(os.path.join(OUT, "storage_sweep_2035.csv"), index=False)

    def pick(s, h, p):
        r = s[(s.duration_h == h) & (s.power_mw == p)].iloc[0]
        return {"reduction_mw": float(r.reduction_mw), "capacity_value_pct": float(r.capacity_value_pct)}

    res["storage"] = {
        "rte": RTE,
        "full_value_limit_mw": {f"{h}h": storage.full_capacity_limit(sw, h) for h in DURATIONS},
        "full_value_limit_mw_2035": {f"{h}h": storage.full_capacity_limit(sw35, h) for h in DURATIONS},
        "examples_2025": {f"{h}h_{p}MW": pick(sw, h, p) for h in DURATIONS for p in (1000, 2000, 3000, 5000)},
        "examples_2035": {f"{h}h_{p}MW": pick(sw35, h, p) for h in DURATIONS for p in (1000, 2000, 3000, 5000)},
        "growth_factor_2035": g35,
        "net_peak_2035_mw": float(net35.max()),
    }
    shaved = storage.shave(df["Net Load"], 2000, 4, RTE)
    res["storage"]["shaved_2gw_4h_new_peak"] = float(shaved.max())
    res["storage"]["shaved_2gw_4h_new_peak_time"] = str(shaved.idxmax())

    # Solar sensitivity: more solar narrows the net peak, which changes what 4-hour storage is worth.
    sol = netload.profile_per_mw(df, "SOLAR")
    solar_rows = []
    for gw in EXTRA_SOLAR_GW:
        nl = df["Net Load"] - sol * gw * 1000
        s = storage.sweep(nl, [1000, 2000, 3000, 4000], [4], RTE)
        ps = netload.peak_summary(nl)
        solar_rows.append({"extra_solar_gw": gw, "net_peak_mw": ps["peak_mw"], "peak_he": ps["peak_hour_ending"],
                           "top100_median_he": ps["top_n_hour_ending_median"],
                           **{f"4h_{int(p/1000)}GW_value_pct": float(s[s.power_mw == p].capacity_value_pct.iloc[0])
                              for p in (1000, 2000, 3000, 4000)}})
    solar = pd.DataFrame(solar_rows)
    solar.to_csv(os.path.join(OUT, "solar_sensitivity.csv"), index=False)
    res["solar_sensitivity"] = solar.to_dict("records")
    res["solar_fleet_peak_avail_mw"] = float(df["SOLAR avail"].max()) if "SOLAR avail" in df else None
    print(f"[storage] 4h full-value limit {res['storage']['full_value_limit_mw']['4h']} MW")

    # 4. Network study ------------------------------------------------------------------
    scen = {"Base load": 1.0,
            "2030 growth": round(netload.growth_factor(2030, YEAR), 3),
            "2035 growth": round(g35, 3)}
    sites = network.site_battery(scen["2035 growth"], NET_BATTERY_MW)
    sites.to_csv(os.path.join(OUT, "battery_siting_2035.csv"), index=False)
    best = int(sites.iloc[0].pp_index)
    table = network.scenario_table(scen, best, NET_BATTERY_MW)
    table.to_csv(os.path.join(OUT, "n1_scenarios.csv"), index=False)
    res["network"] = {"scenarios": scen, "battery_mw": NET_BATTERY_MW, "best_bus": int(sites.iloc[0].bus),
                      "worst_bus": int(sites.iloc[-1].bus),
                      "sites": sites.head(5).to_dict("records"), "table": table.to_dict("records")}
    print(f"[network] best battery site: bus {sites.iloc[0].bus}")

    # 5. Figures and report --------------------------------------------------------------
    figs = {
        "hist": figures.historical_peaks(hist, OUT),
        "peakday": figures.peak_day(df, pk, OUT),
        "ldc": figures.duration_curve(df, OUT),
        "storage": figures.storage_curves(sw, OUT, "Storage on 2025 net load", "fig4_storage_2025.png"),
        "storage35": figures.storage_curves(sw35, OUT, "Storage on 2035 net load (APO reference growth)", "fig4b_storage_2035.png"),
        "shaved": figures.shaved_peak_day(df["Net Load"], shaved, "2 GW of 4-hour storage", OUT),
        "n1": figures.n1_bars(table, OUT),
    }
    res["runtime_s"] = round(time.time() - t0, 1)
    with open(os.path.join(OUT, "results.json"), "w") as f:
        json.dump(res, f, indent=2, default=str)

    from src import report
    pdf = report.build(res, hist, sw, sw35, solar, table, figs, os.path.join(OUT, "Study_Report.pdf"))
    print(f"[report] {pdf}  ({res['runtime_s']} s)")

    # 6. Interactive dashboard (docs/index.html, served by GitHub Pages) ------------------
    from src import dashboard
    grid = dashboard.storage_grid({str(YEAR): df["Net Load"], "2035": net35}, sol, SIZES, DURATIONS, RTE)
    grid.to_csv(os.path.join(OUT, "storage_grid.csv"), index=False)
    page = dashboard.build(res, df, hist, grid, table, g35, sol, DOCS, report_pdf=pdf, repo_url=REPO_URL)
    print(f"[dashboard] {page}  ({round(time.time() - t0, 1)} s total)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="skip the IESO download attempt")
    main(ap.parse_args().offline)
