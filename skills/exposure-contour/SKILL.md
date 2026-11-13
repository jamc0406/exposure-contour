---
name: "exposure-contour"
description: "Full workflow for workplace hazardous-substance concentration distribution maps (濃度分佈圖) - plan measurement points from a floor plan (obstacles judged from the plan, 0.5 m clearance, 0.1 m coordinates), deliver the standard data table with the layout map embedded, the point measurement time table and the instrument-point mapping table, turn direct-reading or sensor logs into the standard table, validate, krige and overlay on the floor plan, check reliability with RRMSE and MAPE and suggest extra points, and mark hot zones and areas above the OEL. Use whenever the user mentions 濃度分佈圖/分布圖, exposure or concentration maps, contour maps, sampling point layout, 佈點, 測點座標, 補點, multi-point direct-reading measurements, sensor or instrument logs, 點位量測時間表, 儀器點位對應表, 標準資料表, ConcTour, OEL areas, or has a floor plan and readings to map."
---

# Workplace concentration maps (exposure-contour)

One skill covers the job from **floor plan → point layout → instrument logs → standard table → map → reliability check → hot zones and areas above the OEL**. It stops there: it does not draft management advice or a report.

All computation runs through `scripts/`. **Never write your own interpolation code**: results must match ConcTour and the interim report. Defaults match ConcTour: ordinary kriging, linear variogram, slope 1, nugget 0, 120 cells on the long side, Jet colour scale.

## Before starting

1. Packages (usually preinstalled): `pip install numpy scipy matplotlib openpyxl pandas pillow pymupdf`
2. Coordinates: origin (0, 0) at the **bottom-left corner** of the field, X right, Y up, metres, **given to 0.1 m**.
3. Work on copies of the user's files; show images directly in the chat; deliver files with the file tool.
4. **Reply to the user in Traditional Chinese**, in plain language, with units. Figures and tables are already in Chinese.

## Where to start

| User has | Stage | Read |
|---|---|---|
| Floor plan, no measurements yet | 1 Planning | `references/01_planning.md` |
| Instrument log, one instrument walked point to point | 2 Data (time table) | `references/02_data_table.md` |
| Instrument log, several instruments at once | 2 Data (mapping table) | `references/02_data_table.md` |
| Readings in any other format | 2 Data | `references/02_data_table.md` |
| Completed standard table | 4 Mapping | `references/03_mapping.md` |
| Asks how reliable the map is / whether to add points | Quality, round 2 | `references/04_quality.md`, `references/01_planning.md` §7 |
| Wants a prompt for ChatGPT/Gemini | Hand over as-is (Chinese) | `references/prompt_for_llm.md` |

Read the matching reference before each stage; it holds the steps, thresholds and commands.

## Stages

1. **Planning** (`plan.py`)
   - Calibrate the plan with `pdf2png`, `calibrate` and `ruler`.
   - **Judge the obstacles yourself** (stairs, equipment bodies and bases, machine front/end stations, rails, narrow gaps) and confirm them with the user, together with what you deliberately did not mark (ceiling-hung fans, overhead ducts, annotation lines).
   - **Ask for likely emission sources** to add points. The user may mark them directly on the plan. Not every source needs its own point; the user decides.
   - Run `count`, then `layout`: every point ≥ 0.5 m from obstacle edges, coordinates to 0.1 m.
   - Show the layout PNG and revise until the user confirms.
   - Deliver **only the standard table with the layout map embedded** below the basic info (proportional, never covering text). Add the time table or the mapping table when the measurement mode needs it.
2. **Data** (`logs_to_points.py`, `timeseries.py`, `build_table.py`): any source → standard table v5.0.
   - One instrument: point measurement time table (start time + end time or duration per point) → mean of each point's window. A point listed more than once (the fixed reference point) gets its **drift computed automatically and written into the note**: ≤ 10% acceptable, 10–30% note it and read relative highs/lows, > 30% re-measure.
   - Several instruments: instrument-point mapping table → mean from the **automatically detected steady start** to the end of the log (not a fixed "last 10 minutes"). Tell the user the chosen start and why the minute before it failed; they may move it.
   - IDs without coordinates: read the coordinates off the plan.
3. **Validation** (`validate_table.py`, with `--layout` whenever a layout exists): 7 checks, outliers, hull coverage, and points lying inside confirmed obstacles. Fix every "must fix" item first. A point inside an obstacle is never moved: ask the user whether the coordinate is wrong, the instrument stood on the machine or a platform, or the obstacle is drawn larger than it is (`references/03_mapping.md`, Plan overlay and obstacles).
4. **Mapping and quality** (`make_map.py`, `drift.py`)
   - Map with optional plan overlay, hatched obstacles and red OEL line; grid CSV.
   - **RRMSE and MAPE** from leave-one-out, plus the 3 largest errors. If either is ≥ 20%, recommend adding points; if both are < 20%, adding points is optional.
   - Point suggestions that keep 0.5 m from obstacles.
   - Statistics, hot zones (nearby equipment ranked by distance to its edge), area ≥ OEL, `results.json`.
5. **Round 2** (`plan.py densify`, then re-map): when either metric is ≥ 20%, add the cross around the highest point first, then gradient midpoints, then coverage suggestions. Merge the new points into one table and compare RRMSE and MAPE with the previous round.
   - Both suggestion figures (`第二階_補點建議圖.png` from `densify`, `_補點建議.png` from `make_map.py`) show only two marker shapes, existing points as blue circles and suggested points as red diamonds, with no concentration colour scale: they are for finding the spots on site.

## Hard rules

1. **Never invent data.** No coordinates → no map; never assume an even grid. Ask about field size, origin and numbering direction when not visible. Obstacles you judge from the plan must be confirmed by the user; never invent emission sources. Record estimated fields in `remark` and tell the user.
2. **Not measured = blank, not 0.** 0 is a valid reading. Zeros are kept by default and flagged for the user to confirm; use `--zero exclude` only after the user confirms they were not measured.
3. **Never auto-drop high outliers.** List them and let the user judge (near a source? reproduced? neighbours high? temporary task?). If dropped, use `--drop` with `--drop-reason`.
4. **Do not change map parameters.** `--compare-models` is for reference only; the official map uses the default.
5. **Do not mark extrapolation areas.** Only mask obstacles the user has confirmed.
6. **Colour scale defaults to Jet.** If the user asks about colours, run `--colormap-preview`, show the five examples, and let them choose.
7. **The OEL line is optional.** Draw it and give the area ≥ OEL only when the user gives an OEL or action value. Report it as a fact, without management advice.
8. **Keep every point ≥ 0.5 m from obstacle edges** (layout, densification, suggestions) and **give coordinates to 0.1 m**: that is what can be paced or taped on site. User-supplied coordinates are kept as given.
9. **State the limits.** This is not a substitute for statutory workplace monitoring or TWA/STEL assessment; it covers one height, one period and one pollutant.
10. **Example values never reach the user's files or replies.** Commands in this skill use placeholders (`USER_GIVEN`, `SITE`, `X Y`, `SECONDS`); numbers that remain in the references (the point-count table, the sample explanation in 04) are illustrations, never values for this job. Pass an option only with a value the user stated in this conversation:
    - `--minutes`: only when the user gave a dwell time per point. Otherwise leave it out, and do not quote a dwell time or a total measuring time in the reply.
    - The measurement height 1.5 m (breathing zone) that `plan.py layout` writes into `remark` is the method's default, not an example: keep it unless the user gives another height.
    - Before delivering any file, read back its `remark` and every filled cell, and remove anything that came from an example rather than from the user, their plan or data, or a method default.

## Command cheat sheet

```bash
S=scripts
python $S/plan.py calibrate --image plan.png --box L T R B --field X Y --out plan.json
python $S/plan.py ruler --plan plan.json --out ruler.png
python $S/plan.py layout --plan plan.json --layout layout.json --out-dir out --site NAME --pollutant POLLUTANT --unit UNIT \
       [--minutes USER_GIVEN] [--drop ID ...] [--time-table] [--instrument-table] [--fieldsheet]
python $S/build_table.py --kind time|instrument --points out/佈點_座標清單.csv [--minutes USER_GIVEN] --out TABLE.xlsx
python $S/build_table.py --embed table.xlsx --image map.png --title "佈點圖（…）"
python $S/logs_to_points.py walk  log.xlsx --times 點位量測時間表.xlsx --out points.csv [--minutes USER_GIVEN] [--skip USER_GIVEN] [--meta meta.json]
python $S/logs_to_points.py multi log.xlsx --mapping 儀器點位對應表.xlsx --out points.csv   # automatic steady start
python $S/timeseries.py log.csv --coords coords.csv --out points.csv
python $S/build_table.py --meta meta.json --points points.csv --out table.xlsx
python $S/validate_table.py table.xlsx --layout layout.json
python $S/make_map.py table.xlsx --out-dir out --plan plan.json --layout layout.json [--oel USER_GIVEN] [--labels]
python $S/make_map.py table.xlsx --colormap-preview --out-dir out
python $S/plan.py densify --table round1.xlsx --plan plan.json --layout layout.json --out-dir out
python $S/drift.py --readings BEFORE MID AFTER          # ≤10% ok, 10–30% note, >30% re-measure
```

Every script has `--help`.

## Tell the user when delivering

- **Planning:** the layout PNG for confirmation, a table of the obstacles you judged (with reasons) plus what you did not mark, and the source question. After confirmation, deliver only the standard table, plus the time or mapping table if needed. Give the numbering direction and say which points were moved or dropped for clearance.
- **Data:** the data source and number of readings, the drift of every repeated point and its verdict, how each point's value was derived (time window per point and skipped seconds; or the detected steady start, why the minute before it failed, and the averaging window), points with missing or short data, LOD substitution, zeros, flagged outliers.
- **Reliability:** RRMSE and MAPE, the 3 largest errors, and the verdict (≥ 20% on either → recommend adding points, with the prioritised list; both < 20% → optional).
- **Results:** where the hot zones are and what equipment is nearby; with an OEL, the area ≥ OEL, its share and the number of points above it.
- **Limits:** the limits above.