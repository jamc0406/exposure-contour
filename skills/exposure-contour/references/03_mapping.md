# 03 Mapping, statistics, hot zones and OEL areas

Functions M1–M6, R1–R3. The workflow ends here: it marks where concentrations are above the OEL or action levels. It does not draft management advice or a report.

## Defaults (do not change)

| Item | Setting | Why |
|---|---|---|
| Interpolation | ordinary kriging | chosen in the interim report over spline, IDW, universal kriging |
| Variogram | linear, slope 1, nugget 0, anisotropy 1 | no parameters to estimate; with nugget 0 weights are independent of slope, stable with few points; surface passes through points, peaks not smoothed away |
| Grid | whole field, 120 cells on long side, short side by aspect ratio (≥ 10) | same as ConcTour |
| Lower bound | negatives clipped to 0 | |
| Colour scale | Jet (Plotly definition) | same as ConcTour |
| Extrapolation | **not marked** | project decision |
| Duplicate coordinates | averaged | avoids a singular matrix |

Grids from this skill and ConcTour differ by < 1e-6 (ConcTour rounds to 6 decimals), so users can cross-check in ConcTour.

**Never write your own interpolation code.** Always call `scripts/make_map.py`.

## Command

```bash
python scripts/make_map.py table.xlsx --out-dir out \
    [--plan plan.json] [--layout layout.json] [--oel USER_GIVEN] [--labels] [--colormap Jet]
```

| Option | Meaning |
|---|---|
| `--plan` | plan overlay (M3); map opacity defaults to 0.6 with a plan, `--map-alpha` to adjust |
| `--layout` | hatched obstacle mask (M4); hot zones name nearby equipment; warns when a measured point lies inside an obstacle |
| `--oel` | OEL or action value: bold red contour (M5, `--no-oel-line` to hide), points above OEL, area ≥ OEL, OEL zone map |
| `--zones A,B` | custom zone thresholds from the user (replaces 0.5×OEL, OEL) |
| `--suggest 4`, `--clear 0.5` | number of point suggestions; their distance to obstacles |
| `--labels` | print values at points; `--label-size`, `--label-color`, `--point-size` |
| `--repeat` | mean / 1 / 2 / 3 / max |
| `--zero exclude` | after the user confirms zeros were not measured |
| `--drop`, `--drop-reason` | outliers the user chose to exclude, and why |
| `--grid` | long-side cells, default 120 |
| `--title` | default "site pollutant" |

Outputs: `_分佈圖.png`, `_網格.csv` (x_m, y_m, concentration, in_obstacle), `_補點建議.png`, `_OEL分區.png` (with OEL/zones), `_results.json` (all parameters and results; table + this file reproduce the map).

## Statistics, hot zones, OEL areas (R1–R3)

- **Statistics** on measured values: n, min, max, mean, median, SD, GM, GSD, CV, skewness, points above OEL. Same definitions as ConcTour; with zeros present GM/GSD use values > 0 only.
- **Hot zones**: connected area where the map ≥ min + 80% × range; up to 5, with peak, location, area, nearby obstacles/sources (needs layout.json) and the matching measured point. Nearby equipment is ranked by the distance from the peak to the obstacle's **edge** (not its centre), so a long machine whose end is close is listed first; `results.json → hotspots → near_m` gives the distances. Name the closest one when describing the hot zone. Hot zone near no known equipment → unknown source, dead zone, or a coordinate/numbering error; re-check coordinates first. Hot zone carried by a single point → peak position uncertain; see the densification order in 01 §7.
- **OEL areas** (only when the user gives an OEL or action value): zones < 50% OEL, 50–100% OEL, ≥ OEL (or custom `--zones`), area and share of each, obstacles excluded; `results.json → over_oel` holds the area ≥ OEL, its share and the number of points above the OEL. Report these as facts; do not add advice.

## Colour scales (only when the user asks)

Make the preview, show it, let the user pick:

```bash
python scripts/make_map.py table.xlsx --colormap-preview --out-dir out
```

| # | Scale | Notes |
|---|---|---|
| 1 | Jet | blue→cyan→yellow→red; classic contour look; ConcTour default |
| 2 | Viridis | purple→green→yellow; colour-blind safe, survives greyscale print |
| 3 | RdYlGn_r | green→yellow→red; reads as safe→caution→danger, good for management slides |
| 4 | Hot_r | white→yellow→red→black; low areas near white, plan shows through |
| 5 | Plasma | blue-purple→orange→yellow; colour-blind safe, high contrast |

If not asked, use Jet without asking.

## Plan overlay and obstacles (M3, M4)

1. Calibration and `layout.json` as in 01_planning.md.
2. Obstacles are hatched white and show no concentration; zone and hot-zone areas exclude them.
3. Kriging still uses all points as a continuous surface; concentrations across barriers may really be discontinuous (stated in the report limits).
4. If plan size and table size differ by > 5%, the table wins and a warning is printed; recheck calibration.
5. A measured point inside a confirmed obstacle (edge included) is warned about by `validate_table.py --layout` and `make_map.py --layout`; the masked area would hide it. Ask the user which it is: a coordinate error, an instrument on the machine or a platform, or an obstacle drawn larger than it really is. User coordinates are never moved. If the user gives the real dimensions, use them; if they only say it is smaller than drawn, pull in just the edges that hold the points, so the points sit on or just outside them (0.1 m), and tell the user these edges are estimates.

## Advanced: variogram comparison (M2)

For users or researchers asking whether another model is better:

```bash
python scripts/make_map.py table.xlsx --compare-models --out-dir out
```

Leave-one-out RRMSE / MAPE comparison of fixed linear (default), spherical, exponential, gaussian, fitted linear. Flags two failures:
- **degenerate**: near-constant output, no spatial information;
- **bull's-eye**: fitted range below mean point spacing, isolated rings around points.

Reference only; **the official map keeps the default.** The interim report found fitted models (esp. gaussian) go near-singular and blow up where points are dense, which users rarely notice.

## Tell the user when delivering

Settings (one line if default), grid and cell size, excluded points and reasons, RRMSE and MAPE with the 3 largest errors and the verdict (04_quality.md), hot zones and nearby equipment, and, with an OEL, the area ≥ OEL and its share. Limitations: interpolation from limited points, visual reference only, **not a basis for statutory workplace monitoring or TWA/STEL assessment**; one height, one period, one pollutant; concentrations across barriers may be discontinuous (obstacles are masked); for indoor, relatively steady fields.

Data security: if the user worries about leaks, replace site names with codes and strip company/process labels from plans. If no cloud is allowed, use ConcTour offline. For users not on Claude, give `references/prompt_for_llm.md` (Chinese, for pasting into ChatGPT/Gemini).
