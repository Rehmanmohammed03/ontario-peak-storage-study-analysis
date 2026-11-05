# Ontario Peak Demand & Storage Adequacy Study

How much does battery storage actually lower Ontario's peak demand, where does adding more
stop helping, and what does load growth do to the transmission system?

The study uses IESO's own public data (hourly demand 2003–2025 and hourly output of every
transmission-connected generator in 2025) and growth assumptions from IESO's 2026 Annual
Planning Outlook. One command runs everything and writes a PDF study report.

## Run it

```bash
pip install -r requirements.txt
python run_study.py            # downloads the IESO files from reports-public.ieso.ca, then runs
python run_study.py --offline  # uses the local copies in data/ieso/
```

Takes about four minutes. It also writes an interactive dashboard to `docs/index.html`
(open it in a browser, or publish it with GitHub Pages: Settings → Pages → Deploy from a branch →
`main` / `docs`). Results go to `outputs/`:

| File | What it is |
|---|---|
| `Study_Report.pdf` | the full study, generated from the results |
| `results.json` | every headline number |
| `storage_sweep_2025.csv`, `storage_sweep_2035.csv` | peak reduction for 2/4/8-hour storage, 0.25–6 GW |
| `solar_sensitivity.csv` | extra solar vs. storage value |
| `n1_scenarios.csv`, `battery_siting_2035.csv` | N-1 contingency results and battery siting |
| `historical_peaks.csv`, `fig*.png` | annual peaks and the report figures |
| `storage_grid.csv` | every storage size × duration × extra-solar case behind the dashboard |

## What it does

1. **Data** (`src/data.py`): reads IESO's Hourly Demand Report and Generator Output and Capability
   Month Report, and sums generator output by fuel type.
2. **Net load and peaks** (`src/netload.py`): net load = Ontario Demand − wind − solar. Annual peaks,
   peak timing since 2003, how many hours sit near the peak.
3. **Storage** (`src/storage.py`): for each day, discharges a battery fleet to shave the peak as far
   as its power and energy allow, then recharges in the lowest hours without making a new peak.
   Sweeps fleet size and duration and reports the drop in the annual peak.
4. **Transmission** (`src/network.py`): IEEE 39-bus test system in pandapower, scaled to 2030 and
   2035 load. Runs N-1 (every line and network transformer out in turn), checks thermal and voltage
   limits, tests a battery at every load bus and picks the best site.
5. **Report** (`src/figures.py`, `src/report.py`): figures and a PDF written from the results.
6. **Dashboard** (`src/dashboard.py`, `src/dashboard_template.html`): an interactive page where you
   pick a storage fleet and see its effect, built from the same results.

## Results (2025 data)

- 2025 peak: **24,862 MW on June 24**, hour ending 19:00 EST, matching IESO's 2025 Year in Review.
  Net peak after wind and solar: 24,216 MW.
- The annual peak has moved later: median hour ending 16:00 EST in 2003–2012, 17:00 in 2020–2025.
- **4-hour storage lowers the peak by its full rating only up to about 1.5 GW.** 3 GW lowers it by
  1,968 MW (66%), 5 GW by 2,617 MW (52%). 8-hour storage keeps full value up to 2.75 GW.
- 2.5 GW more solar raises the value of 3 GW of 4-hour storage from 66% to 95%.
- On the 39-bus test system at 2035 load, a 500 MW battery at the best bus cuts failing N-1
  contingencies from 38 to 21 and removes the one case with no load-flow solution, but the worst
  overload (line 21–22 outage) needs a transmission fix.

## Data sources and limits

- Demand and generator data are IESO public report files (`PUB_Demand_YYYY.csv`,
  `PUB_GenOutputCapabilityMonth_YYYYMM.csv`) in `data/ieso/`. `python run_study.py` downloads every
  file from reports-public.ieso.ca; `--offline` uses the local copies.
- Peak reduction is a simple stand-in for capacity value; IESO's adequacy work is probabilistic.
  Storage dispatch assumes perfect daily foresight, so results are an upper bound.
- 2035 load scales 2025's hourly shape by the APO reference growth rate (about 2.1%/yr); it does not
  capture the faster winter growth the APO expects.
- The network study uses a public test system, not Ontario's grid.
