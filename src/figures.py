"""Figures for the study report (matplotlib, PNG)."""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Reference categorical palette, first three slots (validated as a set, light mode).
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "axes.titlesize": 10, "axes.titleweight": "bold", "axes.titlecolor": INK, "axes.titlelocation": "left",
    "legend.frameon": False, "figure.dpi": 200,
})


def _save(fig, out, name):
    p = os.path.join(out, name)
    fig.tight_layout()
    fig.savefig(p, facecolor="white")
    plt.close(fig)
    return p


def historical_peaks(hist: pd.DataFrame, out: str) -> str:
    fig, ax = plt.subplots(1, 2, figsize=(7.2, 2.6))
    ax[0].plot(hist.index, hist.peak_mw / 1000, color=C1, lw=2, marker="o", ms=4)
    ax[0].set_title("Annual peak Ontario Demand")
    ax[0].set_ylabel("GW")
    ax[1].plot(hist.index, hist.peak_hour_ending, color=C2, lw=2, marker="o", ms=4)
    ax[1].set_title("Hour of the annual peak")
    ax[1].set_ylabel("Hour ending (EST)")
    ax[1].set_ylim(13, 20)
    for a in ax:
        a.set_xticks([y for y in hist.index if y % 4 == 1])
    return _save(fig, out, "fig1_historical_peaks.png")


def peak_day(df: pd.DataFrame, peak_time, out: str) -> str:
    day = df.loc[str(peak_time.date())]
    h = day.index.hour + 1
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    ax.plot(h, day["Ontario Demand"] / 1000, color=C1, lw=2, label="Ontario Demand")
    ax.plot(h, day["Net Load"] / 1000, color=C2, lw=2, label="Net load (minus wind and solar)")
    ax.set_title(f"Peak day, {peak_time:%B %d, %Y}")
    ax.set_xlabel("Hour ending (EST)")
    ax.set_ylabel("GW")
    ax.set_xticks(range(1, 25, 2))
    ax.legend(loc="upper left")
    return _save(fig, out, "fig2_peak_day.png")


def duration_curve(df: pd.DataFrame, out: str) -> str:
    s = df["Net Load"].sort_values(ascending=False).reset_index(drop=True).iloc[:300]
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    ax.plot(s.index + 1, s / 1000, color=C1, lw=2)
    ax.axhline(s.iloc[0] * 0.95 / 1000, color=INK2, lw=0.8, ls="--")
    ax.text(300, s.iloc[0] * 0.95 / 1000 + 0.08, "95% of peak", ha="right", color=INK2, fontsize=8)
    ax.set_title("Top 300 hours of 2025 net load (load duration curve)")
    ax.set_xlabel("Hours, highest to lowest")
    ax.set_ylabel("GW")
    return _save(fig, out, "fig3_duration_curve.png")


def storage_curves(sweep: pd.DataFrame, out: str, title: str, name: str) -> str:
    fig, ax = plt.subplots(1, 2, figsize=(7.2, 2.8))
    for (h, g), c in zip(sweep.groupby("duration_h"), [C3, C1, C2]):
        ax[0].plot(g.power_mw / 1000, g.reduction_mw / 1000, color=c, lw=2, label=f"{h:g}-hour")
        ax[1].plot(g.power_mw / 1000, g.capacity_value_pct, color=c, lw=2, label=f"{h:g}-hour")
    mx = sweep.power_mw.max() / 1000
    ax[0].plot([0, mx], [0, mx], color=INK2, lw=0.8, ls="--")
    ax[0].text(mx * 0.62, mx * 0.72, "1 MW per MW", color=INK2, fontsize=8, rotation=0)
    ax[0].set_title("Peak reduction")
    ax[0].set_xlabel("Storage installed (GW)")
    ax[0].set_ylabel("Net peak reduction (GW)")
    ax[1].set_title("Capacity value")
    ax[1].set_xlabel("Storage installed (GW)")
    ax[1].set_ylabel("% of rated power")
    ax[1].set_ylim(0, 105)
    ax[1].legend(loc="lower left")
    fig.suptitle(title, x=0.01, ha="left", fontsize=10, fontweight="bold", color=INK)
    return _save(fig, out, name)


def shaved_peak_day(orig: pd.Series, shaved: pd.Series, label: str, out: str) -> str:
    d = str(orig.idxmax().date())
    o, s = orig.loc[d], shaved.loc[d]
    h = o.index.hour + 1
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    ax.plot(h, o / 1000, color=C1, lw=2, label="Net load")
    ax.plot(h, s / 1000, color=C2, lw=2, label=f"With {label}")
    ax.set_title(f"How storage reshapes the peak day ({d})")
    ax.set_xlabel("Hour ending (EST)")
    ax.set_ylabel("GW")
    ax.set_xticks(range(1, 25, 2))
    ax.legend(loc="upper left")
    return _save(fig, out, "fig5_shaved_peak_day.png")


def n1_bars(table: pd.DataFrame, out: str) -> str:
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    labels = table.scenario.unique()
    x = range(len(labels))
    w = 0.38
    no = table[table.battery == "none"].set_index("scenario").loc[labels]
    yes = table[table.battery != "none"].set_index("scenario").reindex(labels)
    ax.bar([i - w / 2 - 0.01 for i in x], no.violating, w, color=C1, label="No battery")
    ax.bar([i + w / 2 + 0.01 for i in x], yes.violating, w, color=C2, label=yes.battery.dropna().iloc[0])
    for i, (a, b) in enumerate(zip(no.violating, yes.violating)):
        ax.text(i - w / 2, a + 0.5, f"{a}", ha="center", fontsize=8, color=INK)
        ax.text(i + w / 2, b + 0.5, f"{b}", ha="center", fontsize=8, color=INK)
    ax.set_xticks(list(x), [f"{l}\n({no.loc[l, 'system_load_mw']:.0f} MW)" for l in labels])
    ax.set_ylabel("Contingencies with a violation")
    ax.set_title(f"IEEE 39-bus N-1 results ({int(no.contingencies.iloc[0])} contingencies per scenario)")
    ax.legend(loc="upper left")
    return _save(fig, out, "fig6_n1_results.png")
