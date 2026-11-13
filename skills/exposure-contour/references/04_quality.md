# 04 Quality

Functions Q1–Q3. `make_map.py` computes Q1 and Q2; `drift.py` handles Q3.

## Q1 Map reliability: RRMSE and MAPE (leave-one-out)

Each point is removed once and predicted from all the others with the same settings. Report two numbers:

| Metric | Definition | Plain meaning |
|---|---|---|
| **RRMSE** | RMSE ÷ mean of measured values × 100% | absolute misses count in full, so large misses around the hot zone show up |
| **MAPE** | mean(\|predicted − measured\| ÷ measured) × 100%, over measured > 0 | the typical relative error at a point |

Always give both numbers and **the 3 points with the largest absolute errors** (measured, predicted, error, error as % of measured). `make_map.py` prints them and stores them in `results.json → quality.loocv` (`RRMSE_pct`, `MAPE_pct`, `largest_errors`, `verdict`).

**Decision rule**
- RRMSE or MAPE **≥ 20%** → recommend adding points (01_planning.md §7: cross around the highest point first, then gradients, then coverage suggestions).
- Both **< 20%** → extra points are optional. They are still worth it when the hot zone sits close to an OEL/action level, a decision depends on a boundary, or the user needs a finer map.

Why both metrics and the list:
- MAPE divides each error by that point's measured value. A miss at the highest point therefore weighs little (0.42 ppm at 0.98 ppm counts as 43%), while a miss at a low point weighs a lot (0.55 ppm at 0.38 ppm counts as 145%). It is not dominated by the peak, but it inflates errors at low-concentration points.
- RRMSE uses absolute errors, so the misses around the hot zone count in full. It tells whether the big concentration differences are captured, which matters most for exposure management.
- The largest error is often not the highest point itself but a low point next to it: when the low point is left out, kriging carries the peak over to it. In the test case the worst point was P01 (0.38 ppm, predicted 0.93), just below the peak, in every round. The list makes that visible.
- Points added in smooth, mid-level areas predict each other well and pull both averages down without fixing the hot zone. In the test case, adding 4 gradient points instead of 4 points around the peak gave almost the same MAPE (24% vs 23%) but a much worse RRMSE (31% vs 22%), and the peak was predicted exactly as before.

Explain in plain Chinese, e.g. (illustrative numbers only) 「每點輪流拿掉、用其餘點推估：RRMSE 22%、MAPE 23%，任一項達 20% 以上，建議補點；誤差最大的是 P01（實測 0.38、推估 0.68），在最高點 P03 正下方，中間隔著烘乾機。」 After extra points are measured, re-map and give RRMSE, MAPE and the 3 largest errors next to the previous round.

## Q2 Point suggestions

Extra points where kriging variance (uncertainty) is highest. Excluded: positions within 0.5 m of an obstacle (so suggestions never land in narrow gaps or against equipment), closer than half a spacing or 1 m to walls, or near existing points. Suggestions are at least one spacing apart and rounded to 0.1 m. Default 4 (`--suggest`), drawn on `_補點建議.png` as red diamonds (建議1…) next to the existing points as blue circles, without a concentration colour scale; fewer are returned when the field has no more allowed spots.

Division of labour with densification (01_planning.md §7):
- densify rules target **hot spots and steep gradients**, to pin the peak's location and height; they come first when RRMSE or MAPE ≥ 20%;
- Q2 suggestions target **sparse, uncertain areas**, to improve coverage.

Give both with priorities; the user decides based on manpower.

## Q3 Reference-point drift

When points cannot be measured simultaneously, read one fixed reference point before, during and after. If the point is listed more than once in the point measurement time table, `logs_to_points.py walk` computes the drift by itself and writes it into the note (02_data_table.md). For readings the user simply tells you:

```bash
python scripts/drift.py --readings BEFORE MID AFTER [--times T1 T2 T3]
```

Drift (%) = (max − min) / mean × 100% (technical manual v5, ch. 8.5):

| Drift | Action |
|---|---|
| ≤ 10% | acceptable, treat all points as one period |
| 10%–30% | record in the note (`remark`) and tell the user; interpret relative highs and lows |
| > 30% | recommend re-measuring, shortening the total measuring time, or measuring in separate periods |

Copy the printed remark suggestion into the table.

## Sanity check before every delivery

- Map maximum close to the measured maximum (auto-warning if > 10% lower)
- Hot zone matches known sources / the user's description; if not, suspect coordinates or numbering direction first
- Large single-colour areas (data nearly constant, or an error)
- Chinese text renders correctly
- The layout map embedded in the standard table sits below the info block, proportional, covering no text
