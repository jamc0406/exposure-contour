# 02 Standard tables and data cleaning

Functions D1–D7. Three standard tables:

| Table | When | Template |
|---|---|---|
| 標準資料表 v5.0 (standard data table) | always; shared with ConcTour | `assets/blank_template_v5.0.xlsx` |
| 點位量測時間表 v1.0 (point measurement time table) | one instrument carried point to point | `assets/blank_time_table_v1.0.xlsx` |
| 儀器點位對應表 v1.0 (instrument-point mapping table) | several instruments logging at once | `assets/blank_instrument_table_v1.0.xlsx` |

All three: row 1 English codes (used by code), row 2 Chinese labels, data from row 3. Coordinates in metres to 0.1 m, origin bottom-left.

## Format

One sheet named `基本資料與量測濃度`. Row 1 English codes (fixed, used by code), row 2 Chinese labels (editable, e.g. c1 → 「量測1_0826」), data from row 3. Two blocks, column E blank.

**Origin (0, 0) = bottom-left corner**, X right, Y up, metres. **One pollutant per file.**

### Metadata (columns A–D)

| field_code | Meaning | Unit | Required |
|---|---|---|---|
| `site_name` | site name | — | ✔ |
| `survey_date` | date | YYYY-MM-DD | ✔ |
| `field_x_m` | field length in X | m | ✔ |
| `field_y_m` | field length in Y | m | ✔ |
| `c_name` | pollutant | — | ✔ |
| `c_unit` | unit | — | ✔ |
| `c_LOD` | instrument LOD | same as c_unit | optional |
| `remark` | merged note cell | — | optional: height, how values were derived, estimated fields, drift |

### Points (columns F–L)

`point_id`, `x_m`, `y_m`, `c1` (required), `c2`, `c3`, `note`. One row per point.
**c1/c2/c3 are repeat measurements of the same pollutant, not three pollutants.**

## Build and validate

```bash
python scripts/build_table.py --blank --out blank.xlsx
python scripts/build_table.py --meta meta.json --points points.csv --out table.xlsx \
    [--labels '{"c1":"LABEL1","c2":"LABEL2"}']
python scripts/validate_table.py table.xlsx [--layout layout.json]
```

`meta.json` keys = field codes above; `points.csv` columns `point_id,x_m,y_m,c1,c2,c3,note`. After `plan.py layout`, use the pre-filled table (it already holds the layout map).

## Point measurement time table (one instrument, point to point)

Sheet `點位量測時間表`:

| code | Chinese label | Required | Meaning |
|---|---|---|---|
| `point_id` | 點位編號 | ✔ | as in the standard table |
| `x_m`, `y_m` | X／Y 座標 (m) | ✔ | pre-filled by `plan.py layout --time-table` |
| `start_time` | 開始時間 | ✔ | arrival at the point; `09:00:00` or `2026-11-11 09:00:00` (time only → date of the log) |
| `end_time` | 結束時間 | either | end of the reading |
| `duration_min` | 測量時長 (分鐘) | either | minutes averaged after the start; pre-filled with `--minutes` |
| `note` | 備註 | | |

Per point the value is the mean of the log readings in [start, end), where end = `end_time` if filled, else start + `duration_min`. If both are filled and disagree, the end time is used and a warning is printed. `--minutes N` on the command line overrides the table for every point. Readings while walking between points are excluded.

```bash
python scripts/build_table.py --kind time --points 佈點_座標清單.csv [--minutes USER_GIVEN] --out 點位量測時間表.xlsx
python scripts/logs_to_points.py walk log.xlsx --times 點位量測時間表.xlsx --out points.csv [--skip SECONDS] [--meta meta.json]
```

**Repeated points → drift, automatically (manual v5, ch. 8.5).** When the same point appears more than once in the time table (typically the fixed reference point read before, during and after), `walk` merges it into one row, puts the visits in c1–c3 in time order (more than 3 visits → c1 = mean of all, listed in the note), computes the drift with `drift.py` and writes it into that point's `note` and into the suggested remark; with `--meta` the remark is appended to meta.json so `build_table.py` puts it in the table's `remark`. A repeated point with no coordinates (e.g. `REF` without X/Y) is used for the drift only and not mapped. Thresholds: ≤ 10% acceptable, 10–30% record in the note and interpret relative highs and lows, > 30% recommend re-measuring (`--accept` / `--retest` to change). Always tell the user the drift and the verdict; if no point was repeated, say that no drift could be computed.

- A start-time list without X/Y (any csv/xlsx with 點位編號 and 開始時間 columns) works with `--coords 佈點_座標清單.csv`.
- No table at all: `--coords` (visiting order) `--start "YYYY-MM-DD HH:MM:SS" --dwell SECONDS --walk SECONDS` generates the times (values from the user).
- If neither times nor schedule exist, ask: never guess which readings belong to which point.
- Ask whether the first seconds of each point should be dropped for instrument response time (`--skip`), and record the choice in `remark`.
- Warnings to act on: averaging window running past the next point's start (duration too long), fewer readings than expected, log not covering the schedule (instrument clock or date offset; ask the user to confirm the clock).

## Instrument-point mapping table (several instruments at once)

Sheet `儀器點位對應表`:

| code | Chinese label | Required | Meaning |
|---|---|---|---|
| `instrument_id` | 儀器編號 | ✔ | must equal the column name in the instrument log |
| `point_id` | 點位編號 | ✔ | as in the standard table |
| `x_m`, `y_m` | X／Y 座標 (m) | ✔ | pre-filled by `plan.py layout --instrument-table` |
| `note` | 備註 | | |

Instrument IDs usually differ from point IDs and are not in the same order; never assume they are.

```bash
python scripts/build_table.py --kind instrument --points 佈點_座標清單.csv --out 儀器點位對應表.xlsx
python scripts/logs_to_points.py multi log.xlsx --mapping 儀器點位對應表.xlsx --out points.csv \
    [--window MINUTES | --start S --end S] [--min-len 10] [--head 2]
```

The log has time in column 1 and one column per instrument. The script runs `timeseries.py` (steady-state window, below) on the mapped columns and renames instruments to point IDs; the instrument goes into `note`. Log columns without a mapping row are listed and skipped. A mapping row without a log column means the instrument failed: that point is left blank with the reason.

Then, for either mode:

```bash
python scripts/build_table.py --meta meta.json --points points.csv --out table.xlsx
python scripts/validate_table.py table.xlsx [--layout layout.json]
```

## Filling rules

1. Not measured: leave blank, give the reason in `note`. Never 0, N/A, ND, —, 無. A 0 drags the map down.
2. Below LOD: blank, `note` = `<LOD`, fill `c_LOD`. Substituted with LOD/√2; if more than 1/3 of points, tell the user.
3. Numbers only: no units, commas, symbols.
4. No merged cells, blank rows or subtotal rows.

## Repeats

- One round → c1 only.
- Several rounds → c1, c2, c3 in time order; put the date/time in the row-2 label. Map default is the mean (`--repeat mean`); `1`/`2`/`3`/`max` (conservative) available.
- More than three rounds → keep the three most representative, save the rest separately, explain in `remark`.
- A continuous sensor log is not three repeats; see below.

## Sensor time series (D2)

Time in column 1, one sensor per column. With instrument IDs as column names use `logs_to_points.py multi` with the mapping table (above); `timeseries.py` directly needs column names equal to `point_id` in a coordinate csv.

```bash
python scripts/timeseries.py log.csv --coords coords.csv --out points.csv \
    [--background OUTDOOR_COL --subtract] [--start S --end S | --window MINUTES] [--split 3]
```

- **Default: representative value = mean from the steady start to the end of the log.** The start is found from the data, not fixed at "the last 10 minutes": sensors often rise, overshoot and settle, and how long that takes differs between sites. The script takes the earliest start t0 (1-min steps) whose window [t0, end] is at least `--min-len` minutes (default 10, at most half the log) and passes all three checks:
  - A. the spatial mean (all sensors averaged) has |slope| ≤ 0.5% of its mean per minute: no overall rise or fall;
  - B. the spatial mean over the first `--head` minutes (default 2) is within ±5% of the window mean: the window does not begin on a rising or falling edge;
  - C. no sensor still trends: none has |slope| > 0.5% of its own mean per minute that is also > 2 standard errors (random noise alone does not count).
- Tell the user the start the script chose and why the minute before it failed (it prints the latest rejected start and the reason, e.g. which sensor was still falling), and let them move it. If no start passes, the script uses the last `--min-len` minutes, reports NOT steady and writes 「未達穩定」 into the remark suggestion: tell the user and suggest a longer log.
- `--start/--end` (seconds from the first row) or `--window MINUTES` (last N minutes) override the automatic start; use them only when the user asks.
- Background subtraction only if the user agrees; record it in `remark`.
- `--split 3` puts three sub-window means into c1–c3 to show temporal variation.
- Copy the printed remark suggestion into `remark`.

## IDs without coordinates (D3)

**No coordinates, no map. Never assume an even grid.**

1. Ask for the layout sketch or floor plan.
2. Calibrate as in 01_planning.md, overlay `ruler`, read each point's coordinates, and have the user confirm the list.
3. Confirm numbering direction (start corner, row-first or column-first). With a known source, check the hot zone sits near it (D4); a hot zone far from the source usually means reversed numbering.

## Common sources

| Source | Watch for |
|---|---|
| Typed-up handwritten sheets | merged cells, units inside values ("12.5 ppm"), subtotal rows → pure numbers, unit to c_unit |
| Instrument exports, one instrument | point measurement time table → `logs_to_points.py walk` |
| Instrument exports, several instruments | instrument-point mapping table → `logs_to_points.py multi` |
| Digitised contour plots (WebPlotDigitizer) | axes in metres? convert pixels via scale; which corner is the origin |
| Tables from others | background already subtracted? ppm vs mg/m³? ask and record in `remark` |

## Seven checks (D6, `validate_table.py`)

| Check | Action |
|---|---|
| Text in numeric cells | must fix: number, or blank per rules |
| Negative value | must fix: check calibration; else treat as not measured |
| Zero | warn: confirm real zero vs not measured; kept by default, `--zero exclude` if the user says so |
| Coordinates outside field | must fix |
| Duplicate point IDs | must fix |
| `<LOD` in note | LOD/√2; missing `c_LOD` is a must-fix |
| Blank (not measured) | excluded; blank without a reason is a must-fix |

Also reported: high outliers (Q3 + 3×IQR, flagged not dropped), convex-hull coverage, duplicate coordinates, fewer than 4 valid points. With `--layout layout.json` (whenever a layout exists): points inside a confirmed obstacle. These are not must-fix items, because user coordinates are kept as given, but ask the user before mapping (see 03_mapping.md, Plan overlay and obstacles).

**High outliers are never auto-dropped.** The user judges: near a known source? repeat reproduced? neighbours also high? temporary task at the time? High values are usually the hot spots being sought. If dropped: `make_map.py --drop ID --drop-reason "…"`; the reason goes into results.json and is stated to the user.

## When delivering, state three things

Data source and number of readings; how each point's value was derived (time window per point and any skipped seconds, or the steady window and slope); background, unit conversion, LOD; points with missing or short data; which fields are missing or estimated.
