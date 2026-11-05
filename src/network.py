"""N-1 contingency analysis on the IEEE 39-bus test system (pandapower).

Ontario's detailed transmission model is not public, so this uses the standard IEEE 39-bus
(New England) test system as a stand-in. Loads are scaled up by the APO reference growth rate
to represent future peak years, every line and transformer is taken out one at a time (N-1),
and the study records thermal overloads (>100% of rating) and voltages outside 0.95-1.05 p.u.
at load buses. A battery is then sited by testing every load bus, and the best site is reported.
"""
from __future__ import annotations

import copy
import warnings

import numpy as np
import pandas as pd
import pandapower as pp
import pandapower.networks as pn

warnings.filterwarnings("ignore")
V_MIN, V_MAX, LOADING_MAX = 0.95, 1.05, 100.0


def base_network(load_factor: float = 1.0):
    """IEEE 39-bus with loads and generator dispatch scaled by load_factor."""
    net = pn.case39()
    net.load["p_mw"] *= load_factor
    net.load["q_mvar"] *= load_factor
    net.gen["p_mw"] = np.minimum(net.gen["p_mw"] * load_factor, net.gen["max_p_mw"])
    return net


def _pq_buses(net) -> list[int]:
    gen_buses = set(net.gen.bus) | set(net.ext_grid.bus)
    return [b for b in net.bus.index if b not in gen_buses]


def _check(net, pq) -> dict:
    """Run a load flow and return the worst thermal and voltage results."""
    try:
        pp.runpp(net, numba=False)
    except Exception:
        return {"converged": False}
    lines = net.res_line.loading_percent.fillna(0)
    trafos = net.res_trafo.loading_percent.fillna(0)
    vm = net.res_bus.loc[pq, "vm_pu"].dropna()
    over = [("line", i, v) for i, v in lines.items() if v > LOADING_MAX]
    over += [("trafo", i, v) for i, v in trafos.items() if v > LOADING_MAX]
    vlow = [(b, v) for b, v in vm.items() if v < V_MIN]
    vhigh = [(b, v) for b, v in vm.items() if v > V_MAX]
    return {
        "converged": True,
        "max_loading": float(max(lines.max(), trafos.max())),
        "min_v": float(vm.min()),
        "overloads": over,
        "low_v": vlow,
        "high_v": vhigh,
        "slack_mw": float(net.res_ext_grid.p_mw.sum()),
    }


def n_minus_1(net) -> pd.DataFrame:
    """Outage every in-service line and transformer in turn. One row per contingency."""
    pq = _pq_buses(net)
    rows = []
    base = _check(copy.deepcopy(net), pq)
    rows.append({"element": "base case", **_summ(base)})
    gen_buses = set(net.gen.bus) | set(net.ext_grid.bus)
    for kind, table in [("line", "line"), ("trafo", "trafo")]:
        for i in net[table].index:
            # A generator step-up transformer outage is a loss-of-generation event, which needs
            # a redispatch model rather than a branch outage, so those are left out here.
            if kind == "trafo" and (net.trafo.at[i, "lv_bus"] in gen_buses or net.trafo.at[i, "hv_bus"] in gen_buses):
                continue
            n = copy.deepcopy(net)
            n[table].at[i, "in_service"] = False
            r = _check(n, pq)
            a = net[table].at[i, "from_bus" if kind == "line" else "hv_bus"] + 1  # IEEE numbering
            b = net[table].at[i, "to_bus" if kind == "line" else "lv_bus"] + 1
            name = f"{kind} {a}-{b}"
            rows.append({"element": name, **_summ(r)})
    return pd.DataFrame(rows)


def _summ(r: dict) -> dict:
    if not r["converged"]:
        return {"converged": False, "max_loading": np.nan, "min_v": np.nan,
                "n_overloads": 0, "n_low_v": 0, "worst_overload": np.nan, "violation": True}
    worst = max([v for *_, v in r["overloads"]], default=np.nan)
    n_ov, n_lv = len(r["overloads"]), len(r["low_v"])
    return {"converged": True, "max_loading": r["max_loading"], "min_v": r["min_v"],
            "n_overloads": n_ov, "n_low_v": n_lv, "worst_overload": worst,
            "violation": bool(n_ov or n_lv)}


def severity(res: pd.DataFrame) -> float:
    """One number for how bad a set of contingency results is (MW-free, for ranking sites).

    Sum of overload above 100% plus 1000 x voltage shortfall below 0.95 p.u., plus a large
    penalty for each case that fails to solve.
    """
    s = (res["max_loading"].fillna(0) - LOADING_MAX).clip(lower=0).sum()
    s += 1000 * (V_MIN - res["min_v"].fillna(V_MIN)).clip(lower=0).sum()
    s += 500 * (~res["converged"]).sum()
    return float(s)


def add_battery(net, bus: int, p_mw: float):
    """Battery discharging p_mw at the peak hour (modelled as a static generator at unity PF)."""
    pp.create_sgen(net, bus, p_mw=p_mw, q_mvar=0.0, name="BESS")
    return net


def site_battery(load_factor: float, p_mw: float) -> pd.DataFrame:
    """Try the battery at every load bus and rank sites by N-1 severity. bus = IEEE number."""
    rows = []
    net0 = base_network(load_factor)
    for b in sorted(net0.load.bus.unique()):
        net = add_battery(base_network(load_factor), int(b), p_mw)
        res = n_minus_1(net)
        rows.append({"bus": int(b) + 1, "pp_index": int(b), "severity": severity(res),
                     "n_violating_contingencies": int(res.violation.sum()),
                     "worst_loading": float(res.max_loading.max())})
    return pd.DataFrame(rows).sort_values(["severity", "n_violating_contingencies"]).reset_index(drop=True)


def scenario_table(load_factors: dict, battery_bus: int | None, p_mw: float,
                   dispatch_steps=(0.0, 0.25, 0.5, 0.75, 1.0)) -> pd.DataFrame:
    """N-1 summary for each scenario, with and without the battery.

    With the battery, the operator picks the discharge level (0-100% of rating) that gives the
    fewest problems, since a battery is only discharged as hard as the grid needs.
    """
    rows = []
    for label, lf in load_factors.items():
        options = [("none", 0.0)]
        if battery_bus is not None:
            options.append(("battery", None))
        for kind, _ in options:
            if kind == "none":
                trials = [(0.0, n_minus_1(base_network(lf)))]
            else:
                trials = []
                for f in dispatch_steps:
                    net = base_network(lf)
                    if f > 0:
                        add_battery(net, battery_bus, p_mw * f)
                    trials.append((p_mw * f, n_minus_1(net)))
            def score(t):
                c = t[1][t[1].element != "base case"]
                return (severity(c), int(c.violation.sum()))
            dispatch, res = min(trials, key=score)
            cont = res[res.element != "base case"]
            rows.append({
                "scenario": label, "load_factor": lf,
                "battery": "none" if kind == "none" else f"{p_mw:.0f} MW at bus {battery_bus + 1}",
                "dispatch_mw": dispatch,
                "system_load_mw": float(base_network(lf).load.p_mw.sum()),
                "contingencies": len(cont),
                "violating": int(cont.violation.sum()),
                "overload_cases": int((cont.n_overloads > 0).sum()),
                "low_voltage_cases": int((cont.n_low_v > 0).sum()),
                "unsolved": int((~cont.converged).sum()),
                "worst_loading_pct": float(cont.max_loading.max()),
                "lowest_v_pu": float(cont.min_v.min()),
                "worst_contingency": cont.sort_values("max_loading", ascending=False).element.iloc[0],
                "severity": severity(cont),
            })
    return pd.DataFrame(rows)
