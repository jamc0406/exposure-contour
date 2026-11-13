# 01 Planning: floor plan → measurement points

Functions P1–P7. Thresholds come from interim report ch. 5 §1.

Contents: 1 calibrate · 2 obstacles · 3 emission sources · 4 point count · 5 layout and deliverable · 6 checklist · 7 round 2

## 1. Calibrate the floor plan (P1)

1. PDF → PNG: `python scripts/plan.py pdf2png plan.pdf --page 1 --out plan.png`. DWG is not supported; ask for PDF/PNG. Flatten transparent PNGs onto white first (PIL `alpha_composite` on a white canvas).
2. Find the pixel box of the field outline (left, top, right, bottom). Look at the image, and where possible measure the outline and the drawn dimension lines from pixel rows/columns (dark-pixel counts per row/column). Perspective/3D views or unscaled sketches cannot be calibrated: ask for a top-down plan, or use `--field` without a background.
3. Scale: `--field X Y` (field size from the user) or `--scale PIXELS METRES` (known length on the plan).
4. `python scripts/plan.py calibrate --image plan.png --box L T R B --field X Y --out plan.json`
5. An X/Y scale mismatch > 3% must be resolved. Check the box against the drawn dimension lines. If the box matches them exactly, the drawing itself is not to scale; X and Y are calibrated separately, so coordinates follow the stated field size. Tell the user the background will look slightly stretched and that coordinates are authoritative.
6. `python scripts/plan.py ruler --plan plan.json --out ruler.png`, and use it to read coordinates.

## 2. Obstacles: judge first, then confirm

Do not ask the user to list obstacles from scratch. Zoom into the calibrated plan (crop into quadrants, enlarge 4–6×, read coordinates against `ruler.png`) and identify common non-standable structures yourself:

- stairs (dense parallel treads, often split by a landing line), lift shafts, pits
- equipment bodies and their bases: dryers, tanks, motors, roll stands, cabinets
- front/end stations attached to machines
- floor rails, conveyors, trenches, foundations
- walls, partitions, storage racks
- narrow gaps nobody can enter (e.g. between a machine and a rail)

Usually not obstacles: overhead ducts or stacks drawn in oblique view, ceiling-hung units (fans, blowers, hoods mounted overhead), dimension and annotation lines, column/grid lines (points stay off column intersections). When an item could be either floor-standing or ceiling-hung, state your guess and ask explicitly.

Write obstacles to `layout.json` in metres, origin bottom-left, with Chinese names (they appear on figures):

```json
{"obstacles": [{"name": "烘乾機A", "rect": [9.5, 18.3, 27.9, 22.5]},
               {"name": "L形隔間", "polygon": [[0, 10], [4, 10], [4, 14], [0, 14]]}],
 "sources":   [{"name": "塗布頭", "type": "開放液面", "x": 8.5, "y": 20.0}]}
```

Show the layout map with a table (name, why you judged it, X/Y range) plus what you deliberately did not mark, and ask the user to confirm, correct or add. Only obstacles the user has confirmed are kept; areas the user says are not standable are added as obstacles.

## 3. Emission sources: ask, in order to add points

Ask where likely sources are, by four priority types:
- **equipment joints**: flanges, valves, sampling or charging ports
- **open liquid surfaces**: coating heads, tanks, dip baths, solvent or waste drums
- **operator positions**: mixing, cleaning, drum change
- **poorly ventilated dead zones**: corners, behind equipment or doors

Point out plan features that look like candidates and ask whether they are. Tell the user they can **mark sources directly on the plan** (circles or arrows on the image, sent back); read the marks against `ruler.png` and confirm the coordinates back.

- Sources are for adding points where useful. **Not every source needs its own point.** Let the user decide; a source already near a grid point, or a minor one, may be covered by the grid or left for round 2.
- `plan.py layout` adds a point for every entry in `sources` (or pulls a grid point within 1/3 spacing onto it), so list only the sources the user chose.
- If the user does not know yet, proceed with the grid; round-1 hot spots drive densification.
- Never invent sources.

## 4. Point count (P2)

```bash
python scripts/plan.py count --field X Y [--minutes USER_GIVEN]
```

n = max[ area / (0.15 × diagonal)², area / 100 ], rounded up. Term 1 keeps normalised spacing ≤ 0.15 × diagonal; term 2 caps spacing at 10 m. They cross at diagonal 66.7 m (~2,000 m²).

| Field (m) | Area (m²) | Points | Spacing (m) | Controlled by |
|---|---|---|---|---|
| 20 × 10 | 200 | 18 | 3.3 | normalised spacing |
| 20 × 20 | 400 | 23 | 4.2 | normalised spacing |
| 30 × 20 | 600 | 21 | 5.3 | normalised spacing |
| 40 × 25 | 1,000 | 20 | 7.1 | normalised spacing |
| 50 × 40 | 2,000 | 22 | 9.5 | normalised spacing |
| 60 × 40 | 2,400 | 24 | 10.0 | 10 m cap |
| 80 × 50 | 4,000 | 40 | 10.0 | 10 m cap |

Round 1 is a screening grid to find hot zones. `count` prints a measuring-time estimate only when the user has given a dwell time per point (`--minutes`); never assume one. If points are dropped (obstacles, user request) and the total falls below the formula, `layout` warns: tell the user and offer points elsewhere.

## 5. Layout and the deliverable (P3–P6)

```bash
python scripts/plan.py layout --plan plan.json --layout layout.json --out-dir out \
    --site SITE --pollutant POLLUTANT --unit UNIT [--minutes USER_GIVEN] \
    [--drop ID ...] [--time-table] [--instrument-table] [--fieldsheet] [--clear 0.5]
```

- Square grid, points at cell centres.
- **Every point is ≥ 0.5 m from every obstacle edge** (`--clear`). A grid point inside an obstacle or its 0.5 m band moves to the nearest allowed spot within half a spacing, else it is dropped and listed. Points in narrow gaps are dropped automatically, because no spot there can keep 0.5 m from both sides.
- **Coordinates are given to 0.1 m.** That is what anyone can pace or tape on site; extra digits only suggest false accuracy.
- Numbering starts bottom-left: by Y from the bottom, then X left to right (P01, P02 …). Moved points can reorder IDs within a row band; state the direction when delivering.
- `--drop` removes points the user rejects; the rest are renumbered.
- `--n` sets the count, `--spacing` the spacing; without a plan use `--field X Y`.

Outputs:

| File | Use |
|---|---|
| `佈點_佈點圖.png` | show in the chat for confirmation |
| `佈點_標準資料表.xlsx` | **the deliverable**: coordinates pre-filled, layout map embedded below the basic info |
| `佈點_座標清單.csv` | working file (coordinates for other steps); not delivered unless asked |
| `佈點_點位量測時間表.xlsx` | with `--time-table`: one instrument walked point to point (see 02) |
| `佈點_儀器點位對應表.xlsx` | with `--instrument-table`: several instruments at once (see 02) |
| `佈點_現場記錄表.xlsx` | with `--fieldsheet`: printable A4 sheet |

Flow: show the PNG with the obstacle table and the source question, then revise until the user confirms. Deliver only the standard table, plus the time table or mapping table when the measurement mode calls for it. One file is easier to carry on site and keeps the map with the coordinates.

**Map in the table.** The basic info sits in columns A–D and the points in F onward. The map goes in A–D, starting two rows below the last used row or merged range there (the remark cell is merged over several rows). It is **scaled proportionally**: one factor for width and height, capped at 90% of the A–D width, with the aspect ratio locked so it stays proportional if resized in Excel. It is never stretched and never covers the info block or the point table. Before delivering, render the sheet (LibreOffice → PDF → PNG) and check. To embed into an existing table:
`python scripts/build_table.py --embed table.xlsx --image map.png --title "佈點圖（…）"`.

## 6. Pre-measurement checklist

- [ ] Field size and origin (bottom-left) confirmed; plan orientation matches site
- [ ] Obstacles confirmed by the user; every point ≥ 0.5 m from obstacle edges
- [ ] Sources the user chose have points (not required for every source)
- [ ] Uniform height 1.5 m (breathing zone); exceptions noted
- [ ] Measurement mode settled: one instrument → time table; several instruments → mapping table
- [ ] One fixed reference point read before, during and after, listed in the point measurement time table on every visit so `logs_to_points.py walk` computes the drift by itself (04_quality.md Q3)
- [ ] Whole field measured under one operating state; times recorded
- [ ] Instrument calibrated, LOD known (`c_LOD`)
- [ ] Same dwell time per point; record once readings stabilise

## 7. Round 2: densification and stop rule (P7)

When the map's RRMSE or MAPE is ≥ 20% (04_quality.md), add points in this order:
1. the cross around the highest point, which pins the peak's position and height;
2. gradient midpoints;
3. the map's coverage suggestions (`make_map.py`, sparse uncertain areas).

```bash
python scripts/plan.py densify --table round1.xlsx --plan plan.json --layout layout.json --out-dir out
```

- Rule 1: 4 points in a cross at spacing / 2 around the highest point.
- Rule 2: midpoint between neighbours whose difference exceeds the field SD (neighbour = distance ≤ 1.5 × median nearest-neighbour distance).
- Every new point keeps ≥ 0.5 m from obstacles and is rounded to 0.1 m. A point that would have to move more than 2 m is dropped and reported, because the area itself is not reachable. Tell the user rather than relocating it somewhere unrelated.
- Points outside the field or within 1/4 spacing of existing points are skipped.

Outputs: `第二階_加密點座標.csv` (coordinates and the rule behind each point), `第二階_補點建議圖.png` and `第二階_加密現場記錄表.xlsx`. The figure shows the plan and hatched obstacles with **two marker shapes only**: existing points as blue circles (P…) and suggested points as red diamonds (Q…), each labelled, with a legend giving both counts. It has no concentration colour scale on purpose: it is for finding the spots on site, and the concentrations are already on the map. `make_map.py`'s coverage suggestions (`_補點建議.png`) are drawn the same way.

Merge into one table (points of all rounds, notes saying which round), re-map, and report RRMSE, MAPE and the 3 largest errors next to the previous round. Optionally:

```bash
python scripts/plan.py compare --before round1.xlsx --after merged.xlsx --spacing ROUND1_SPACING
```

The stop rule is a hot-spot shift ≤ spacing / 2 and a map peak change ≤ 10%, together with RRMSE and MAPE both below 20%.
