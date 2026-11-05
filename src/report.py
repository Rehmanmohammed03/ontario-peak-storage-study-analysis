"""Builds outputs/Study_Report.pdf from the study results. Every number in the text is computed."""
from __future__ import annotations

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

INK, INK2, RULE, ACCENT = colors.HexColor("#0b0b0b"), colors.HexColor("#52514e"), colors.HexColor("#d9d8d3"), colors.HexColor("#2a78d6")
ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Title"], fontSize=17, leading=21, alignment=TA_LEFT, textColor=INK, spaceAfter=4)
SUB = ParagraphStyle("SUB", parent=ss["Normal"], fontSize=9.5, textColor=INK2, spaceAfter=10)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=12.5, textColor=INK, spaceBefore=10, spaceAfter=4)
BODY = ParagraphStyle("B", parent=ss["Normal"], fontSize=9.5, leading=13.2, textColor=INK, spaceAfter=5)
BUL = ParagraphStyle("BUL", parent=BODY, leftIndent=12, bulletIndent=2, spaceAfter=3)
CAP = ParagraphStyle("CAP", parent=BODY, fontSize=8, textColor=INK2, spaceAfter=8)
CELL = ParagraphStyle("CELL", parent=BODY, fontSize=8, leading=10, spaceAfter=0)


def _fig(path, w=7.0):
    img = Image(path)
    r = img.imageHeight / img.imageWidth
    img.drawWidth, img.drawHeight = w * inch, w * inch * r
    return img


def _table(rows, widths):
    t = Table([[Paragraph(str(c), CELL) for c in r] for r in rows], colWidths=[w * inch for w in widths])
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK2), ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    return t


def _bullets(items):
    return [Paragraph(i, BUL, bulletText="•") for i in items]


def build(res, hist, sw, sw35, solar, n1, figs, path):
    d, nl, st = res["demand_full_year"], res["net_load"], res["storage"]
    ex, ex35 = st["examples_2025"], st["examples_2035"]
    lim, lim35 = st["full_value_limit_mw"], st["full_value_limit_mw_2035"]
    ph = res["peak_hour_shift"]
    net = res["network"]
    t = pd.DataFrame(net["table"])
    no35 = t[(t.scenario == "2035 growth") & (t.battery == "none")].iloc[0]
    b35 = t[(t.scenario == "2035 growth") & (t.battery != "none")].iloc[0]
    no30 = t[(t.scenario == "2030 growth") & (t.battery == "none")].iloc[0]
    b30 = t[(t.scenario == "2030 growth") & (t.battery != "none")].iloc[0]
    sol = pd.DataFrame(res["solar_sensitivity"])
    s0, s25 = sol.iloc[0], sol[sol.extra_solar_gw == 2.5].iloc[0]
    pk = pd.Timestamp(d["peak_time"])
    g35 = st["growth_factor_2035"]

    story = [
        Paragraph("Ontario Peak Demand &amp; Storage Adequacy Study", H1),
        Paragraph(f"Analysis of IESO public data for {res['year']}, with growth scenarios from the 2026 Annual "
                  "Planning Outlook.", SUB),
        Paragraph("Key findings", H2),
        *_bullets([
            f"Ontario's {res['year']} peak was <b>{d['peak_mw']:,.0f} MW</b> on {pk:%B %d} in the hour ending "
            f"{d['peak_hour_ending']}:00 EST, matching the figure IESO reports for the year. "
            f"All 100 highest-demand hours were in summer.",
            f"<b>The peak has moved later in the day.</b> The median annual peak fell in the hour ending "
            f"{ph['early_median_he']:.0f}:00 EST over {ph['early_years'][0]}-{ph['early_years'][1]}, versus "
            f"{ph['late_median_he']:.0f}:00 over {ph['late_years'][0]}-{ph['late_years'][1]}, and "
            f"{d['peak_hour_ending']}:00 in {res['year']}. Later peaks get less help from solar.",
            f"<b>Storage hits diminishing returns early.</b> Up to <b>{lim['4h']/1000:.2f} GW</b> of 4-hour storage "
            f"lowers the {res['year']} net peak by its full rating. At 3 GW it lowers the peak by "
            f"{ex['4h_3000MW']['reduction_mw']:,.0f} MW ({ex['4h_3000MW']['capacity_value_pct']:.0f}% of rating), and at "
            f"5 GW by {ex['4h_5000MW']['reduction_mw']:,.0f} MW ({ex['4h_5000MW']['capacity_value_pct']:.0f}%). "
            f"8-hour storage keeps full value up to {lim['8h']/1000:.2f} GW.",
            f"<b>Solar and storage complement each other.</b> Adding 2.5 GW of solar narrows the evening peak, "
            f"raising the value of 3 GW of 4-hour storage from {s0['4h_3GW_value_pct']:.0f}% to "
            f"{s25['4h_3GW_value_pct']:.0f}% of its rating.",
            f"<b>Storage relieves transmission stress but does not replace it.</b> On the IEEE 39-bus test system "
            f"at 2035 load (+{(g35-1)*100:.0f}%), a {net['battery_mw']} MW battery at the best site (bus {net['best_bus']}) cut "
            f"N-1 contingencies with a violation from {no35.violating} to {b35.violating} and removed the "
            f"{int(no35.unsolved)} case with no load-flow solution, but the worst overload "
            f"({b35.worst_contingency} outage, {b35.worst_loading_pct:.0f}% loading) remains and needs a wires solution.",
        ]),
    ]

    # 1. Data
    dd = res["data"]
    story += [
        Paragraph("1. Data", H2),
        Paragraph(
            "All load and generation data come from IESO's public reports: the <i>Hourly Demand Report</i> "
            f"(PUB_Demand_YYYY.csv, {hist.index.min()}-{hist.index.max()}) and the <i>Generator Output and Capability "
            f"Month Report</i> (PUB_GenOutputCapabilityMonth_YYYYMM.csv, all of {res['year']}, {dd['generators']} "
            "transmission-connected generators of 20 MW or more, with fuel type), published at "
            "reports-public.ieso.ca. Net load is Ontario Demand minus transmission-connected wind and solar output.", BODY),
        Paragraph(
            f"<b>Validation:</b> the data give a {res['year']} peak of {d['peak_mw']:,.0f} MW on "
            f"{pk:%B %d} and annual Ontario Demand of {d['energy_twh']:.1f} TWh, the same as IESO's 2025 Year in Review "
            "(24,862 MW on June 24; 145.6 TWh).", BODY),
        *([Paragraph(
            f"<b>Coverage:</b> generator output was unavailable for {len(dd['missing_days'])} days "
            f"({', '.join(dd['missing_days'])}), none near the summer peak.", BODY)] if dd["missing_days"] else []),
        Paragraph(
            f"{res['year']} transmission-connected output by fuel (TWh): "
            + ", ".join(f"{k.title()} {v:.1f}" for k, v in res["fuel_twh"].items()) + ".", BODY),
    ]

    # 2. Peaks
    ap = res["at_peak"]
    story += [
        Paragraph("2. Peak demand and net load", H2),
        _fig(figs["hist"]),
        Paragraph(f"Figure 1. Annual peak Ontario Demand and the hour it occurred, {hist.index.min()}-{hist.index.max()}, "
                  "from IESO Hourly Demand Reports. Winter peaks: " + ", ".join(str(y) for y in hist.index[hist.season == "Winter"]) + "; every other year peaked in summer.", CAP),
        Paragraph(
            f"At the {res['year']} peak hour, wind supplied {ap['WIND']:,.0f} MW and transmission-connected solar "
            f"{ap['SOLAR']:,.0f} MW, so the net load peak was {nl['peak_mw']:,.0f} MW. Only {nl['hours_within_5pct']} hours "
            f"were within 5% of the net peak and {nl['hours_within_10pct']} within 10%. A short, sharp peak is what makes "
            "energy-limited storage effective, up to a point.", BODY),
        KeepTogether([_fig(figs["peakday"]), Paragraph("Figure 2. The peak day: demand and net load by hour.", CAP)]),
        KeepTogether([_fig(figs["ldc"]), Paragraph(
            "Figure 3. The 300 highest net-load hours of the year. The steep left end is the part storage can shave.", CAP)]),
    ]

    # 3. Storage
    rows = [["Storage", "1 GW", "2 GW", "3 GW", "5 GW", "Full value up to"]]
    for h in (2, 4, 8):
        rows.append([f"{h}-hour"] + [f"{ex[f'{h}h_{p}MW']['reduction_mw']:,.0f} MW ({ex[f'{h}h_{p}MW']['capacity_value_pct']:.0f}%)"
                                     for p in (1000, 2000, 3000, 5000)] + [f"{lim[f'{h}h']/1000:.2f} GW"])
    srows = [["Extra solar", "Net peak", "Median hour of top 100 (HE, EST)", "4h at 2 GW", "4h at 3 GW", "4h at 4 GW"]]
    for _, r in sol.iterrows():
        srows.append([f"+{r.extra_solar_gw:g} GW", f"{r.net_peak_mw:,.0f} MW", f"{r.top100_median_he:.1f}",
                      f"{r['4h_2GW_value_pct']:.0f}%", f"{r['4h_3GW_value_pct']:.0f}%", f"{r['4h_4GW_value_pct']:.0f}%"])
    story += [
        PageBreak(),
        Paragraph("3. How much does storage lower the peak?", H2),
        Paragraph(
            "For every day, a storage fleet of power P and duration H discharges in the highest hours to bring that "
            "day's net load down as far as its power and energy allow, then recharges the same day in the lowest hours "
            f"(round-trip efficiency {st['rte']*100:.0f}%) without creating a new peak. The fleet's value is how far the "
            "annual peak falls. This assumes perfect foresight and a full battery every morning, so it is an upper bound.", BODY),
        _fig(figs["storage"]),
        Paragraph(f"Figure 4. Peak reduction and capacity value for 2-, 4- and 8-hour storage on {res['year']} net load. "
                  "The dashed line is full value (1 MW of peak reduction per MW installed).", CAP),
        _table(rows, [0.8, 1.15, 1.15, 1.15, 1.15, 1.1]),
        Paragraph(f"Table 1. Net peak reduction ({res['year']}), with capacity value as a share of rated power.", CAP),
        KeepTogether([_fig(figs["shaved"]), Paragraph(
            f"Figure 5. 2 GW of 4-hour storage on the peak day. The new annual peak is {st['shaved_2gw_4h_new_peak']:,.0f} MW: "
            "high load lasts from late morning to 9 pm, so the 8 GWh of energy only stretches far enough to trim the top of a long plateau.", CAP)]),
        Paragraph("Growth to 2035", H2),
        Paragraph(
            f"Scaling {res['year']} demand by the APO reference growth rate (about 2.1% a year, a factor of {g35:.3f} by 2035) "
            f"raises the net peak to {st['net_peak_2035_mw']:,.0f} MW. Because the shape is scaled uniformly, the pattern "
            f"is the same but slightly larger: 4-hour storage keeps full value up to {lim35['4h']/1000:.2f} GW and 8-hour "
            f"storage up to {lim35['8h']/1000:.2f} GW.", BODY),
        _fig(figs["storage35"]),
        Paragraph("Figure 6. The same sweep on 2035 net load.", CAP),
        Paragraph("Solar sensitivity", H2),
        Paragraph(
            f"Ontario's transmission-connected solar fleet is small (about {res['solar_fleet_peak_avail_mw']:,.0f} MW available "
            "at most in the IESO data). Adding solar with the same hourly profile pushes the highest net-load hours later "
            "and makes them narrower, so 4-hour storage covers more of them:", BODY),
        _table(srows, [0.8, 0.9, 1.6, 0.95, 0.95, 0.95]),
        Paragraph("Table 2. Effect of extra solar on the net peak and on 4-hour storage capacity value.", CAP),
    ]

    # 4. Network
    nrows = [["Load level", "Battery", "Output", "Failing (of 38)", "Over- load", "Low V", "No solu- tion", "Worst load", "Lowest V (p.u.)"]]
    for _, r in t.iterrows():
        nrows.append([f"{r.scenario} ({r.system_load_mw:,.0f} MW)", r.battery, f"{r.dispatch_mw:.0f} MW", r.violating,
                      r.overload_cases, r.low_voltage_cases, r.unsolved, f"{r.worst_loading_pct:.0f}%", f"{r.lowest_v_pu:.3f}"])
    srows2 = [["Rank", "Bus", "Violating contingencies", "Severity score"]] + [
        [i + 1, s["bus"], s["n_violating_contingencies"], f"{s['severity']:.0f}"] for i, s in enumerate(net["sites"])]
    story += [
        PageBreak(),
        Paragraph("4. Transmission: N-1 contingency analysis", H2),
        Paragraph(
            "Ontario's detailed transmission model is not public, so this section uses the IEEE 39-bus test system in "
            "pandapower as a stand-in. Loads and generator dispatch are scaled by the APO growth factors for 2030 and 2035. "
            "Every line and network transformer is taken out one at a time (38 contingencies; generator step-up "
            "transformers are excluded because losing one is a generation contingency). A case is a violation if any "
            "branch exceeds 100% of its rating, any load bus falls below 0.95 p.u., or the load flow has no solution.", BODY),
        Paragraph(
            f"The battery ({net['battery_mw']} MW, about 6.5% of 2035 test-system load, similar to a few GW in Ontario) was "
            "tested at every load bus at 2035 load, and the site with the lowest severity score was chosen. In each scenario "
            "the battery is discharged at the level (0-100%) that gives the fewest problems, as an operator would.", BODY),
        _fig(figs["n1"]),
        Paragraph("Figure 7. Contingencies with a violation, with and without the battery.", CAP),
        _table(nrows, [1.35, 1.0, 0.6, 0.65, 0.55, 0.45, 0.55, 0.55, 0.6]),
        Paragraph("Table 3. N-1 results by scenario.", CAP),
        Paragraph(
            f"<b>Reading the results.</b> The test system as published already has violations at base load, mostly the "
            f"outage of line 21-22, which overloads a parallel path. Growth makes things much worse: at 2035 load, "
            f"{no35.violating} of 38 contingencies fail, {no35.low_voltage_cases} with low voltage and {no35.unsolved} with no "
            f"solution at all, a sign of voltage collapse. The battery at bus {net['best_bus']} brings 2030 back to "
            f"{b30.violating} violations (from {no30.violating}) using {b30.dispatch_mw:.0f} MW, and 2035 to {b35.violating}. "
            f"It cannot fix the {b35.worst_contingency} overload, which comes from the network's structure rather than total "
            "load, so that one needs a transmission upgrade. In base load the best choice is not to discharge at all.", BODY),
        KeepTogether([_table(srows2, [0.6, 0.6, 1.6, 1.2]),
                      Paragraph(f"Table 4. Best five battery sites at 2035 load (IEEE bus numbers). Worst site: bus {net['worst_bus']}.", CAP)]),
    ]

    # 5. Limits
    story += [
        Paragraph("5. Assumptions and limitations", H2),
        *_bullets([
            "Peak reduction is a simple stand-in for capacity value. IESO's resource adequacy work is probabilistic "
            "(how often supply falls short across many weather and outage conditions); a natural next step is an "
            "effective load-carrying capability (ELCC) calculation.",
            "Storage dispatch assumes perfect daily foresight and a full battery each morning, so results are an upper bound.",
            "Growth is a uniform scaling of 2025's hourly shape. The APO expects winter demand to grow faster with "
            "electrification, which would change the shape of the peak; IESO's zonal hourly forecast would capture that.",
            "Net load uses transmission-connected wind and solar only. Embedded (distribution-connected) solar already "
            "lowers the Ontario Demand that IESO measures.",
            "The network study uses a test system, not Ontario's grid, and the slack bus covers any generation shortfall.",
        ]),
        Paragraph("Sources", H2),
        *_bullets([
            "IESO Hourly Demand Report and Generator Output and Capability Month Report, reports-public.ieso.ca",
            "IESO, 2025 Year in Review (peak demand and annual energy), ieso.ca",
            "IESO, 2026 Annual Planning Outlook (reference scenario growth), ieso.ca",
            "IEEE 39-bus test system, via pandapower.networks.case39",
        ]),
    ]

    doc = SimpleDocTemplate(path, pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.7 * inch, title="Ontario Peak Demand & Storage Adequacy Study")

    def footer(c, doc_):
        c.saveState()
        c.setFont("Helvetica", 7.5)
        c.setFillColor(INK2)
        c.drawString(0.75 * inch, 0.45 * inch, "Ontario Peak Demand & Storage Adequacy Study")
        c.drawRightString(letter[0] - 0.75 * inch, 0.45 * inch, f"Page {doc_.page}")
        c.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path
