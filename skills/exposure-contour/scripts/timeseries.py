# -*- coding: utf-8 -*-
"""Sensor time series -> representative concentration per point (D2).

Input: time in column 1, one sensor per remaining column (csv or first xlsx sheet).
  Time may be seconds or datetimes (converted to seconds from the first row).
--coords: point csv (point_id,x_m,y_m); point_id must match the sensor column names.

Usage:
  python timeseries.py log.csv --coords coords.csv --out points.csv            # automatic steady start
  python timeseries.py log.xlsx --coords coords.csv --background OUTDOOR_COL --subtract --out points.csv
  python timeseries.py log.csv --coords coords.csv --start SECONDS --end SECONDS --out points.csv
  python timeseries.py log.csv --coords coords.csv --window MINUTES --out points.csv   # last N minutes
  python timeseries.py log.csv --coords coords.csv --split 3 --out points.csv   # 3 sub-windows -> c1/c2/c3

Representative value = mean of the readings from the steady start to the end of the log.

Steady start (default, when neither --start nor --window is given): the earliest candidate
time t0 (1-min grid, or the log interval if longer) such that the window [t0, end] is at least
--min-len minutes long (default 10, at most half the log) and
  A. the spatial mean (mean of all sensors) has |slope| <= 0.5% of its mean per min over the
     window, i.e. no overall rise or fall;
  B. the spatial mean over the first --head minutes of the window (default 2) is within
     +-5% of the window mean, i.e. the window does not start on a rising or falling edge;
  C. no single sensor still trends: no sensor whose |slope| exceeds 0.5% of its own mean
     per min AND is more than 2 standard errors from zero (noise alone is not a trend).
If no t0 qualifies, the last --min-len minutes are used and the window is reported as NOT
steady. --start/--end or --window override the automatic choice.
Output csv feeds build_table.py --points.
"""
import argparse
import csv
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ecore as E  # noqa: E402,F401

SLOPE_PCT = 0.5     # criteria A and C: % of the mean per minute
HEAD_TOL = 0.05     # criterion B: head mean within +-5% of window mean
SIG = 2.0           # criterion C: slope must exceed 2 SE to count as a trend


def read_series(path):
    """Return (t seconds from first row, {sensor: values}, first timestamp or None)."""
    import pandas as pd
    if path.lower().endswith(('.xlsx', '.xls')):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path, encoding='utf-8-sig')
    df = df.dropna(axis=1, how='all')
    tcol = df.columns[0]
    t = df[tcol]
    t_first = None
    if not np.issubdtype(t.dtype, np.number):
        tt = pd.to_datetime(t, errors='coerce')
        t_first = tt.iloc[0] if pd.notna(tt.iloc[0]) else None
        t = (tt - tt.iloc[0]).dt.total_seconds()
    df = df.assign(**{tcol: t}).dropna(subset=[tcol])
    data = {str(c).strip(): pd.to_numeric(df[c], errors='coerce').to_numpy(float) for c in df.columns[1:]}
    return df[tcol].to_numpy(float), data, t_first


def _slope(t, y):
    """Slope per minute and its standard error (NaNs dropped)."""
    ok = ~np.isnan(y)
    t, y = t[ok], y[ok]
    if len(t) < 3 or np.ptp(t) == 0:
        return np.nan, np.nan
    b, a0 = np.polyfit(t, y, 1)
    res = y - (a0 + b * t)
    se = np.sqrt(np.sum(res ** 2) / (len(t) - 2) / np.sum((t - t.mean()) ** 2))
    return b * 60, se * 60


def find_steady_start(t, M, min_len_s, head_s):
    """M: sensors x time. Returns (t0 or None, per-candidate diagnostics)."""
    t_end = t.max()
    step = max(60.0, float(np.median(np.diff(t))) if len(t) > 1 else 60.0)
    mean_t = np.nanmean(M, axis=0)
    diag = []
    for t0 in np.arange(t.min(), t_end - min_len_s + 1e-9, step):
        w = t >= t0
        lvl = float(np.nanmean(mean_t[w]))
        s, _ = _slope(t[w], mean_t[w])
        a_ok = abs(s) <= abs(lvl) * SLOPE_PCT / 100
        h = w & (t < t0 + head_s)
        head_dev = (float(np.nanmean(mean_t[h])) - lvl) / lvl if lvl else 0.0
        b_ok = abs(head_dev) <= HEAD_TOL
        trending = []
        for k in range(M.shape[0]):
            mu = np.nanmean(M[k, w])
            sk, se = _slope(t[w], M[k, w])
            if mu and abs(sk) > abs(mu) * SLOPE_PCT / 100 and abs(sk) > SIG * se:
                trending.append((k, sk / mu * 100))
        ok = a_ok and b_ok and not trending
        diag.append(dict(t0=t0, slope_pct=s / lvl * 100 if lvl else 0.0, head_pct=head_dev * 100,
                         trending=trending, ok=ok))
        if ok:
            return t0, diag
    return None, diag


def _clock(t_first, s):
    if t_first is None:
        return f'{s:.0f} s'
    import pandas as pd
    return (t_first + pd.Timedelta(seconds=float(s))).strftime('%H:%M:%S')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('series')
    ap.add_argument('--coords', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--background', nargs='*', default=[], help='background (outdoor) sensor columns')
    ap.add_argument('--subtract', action='store_true', help='subtract background at each time (default off)')
    ap.add_argument('--start', type=float, help='window start (s); overrides the automatic steady start')
    ap.add_argument('--end', type=float, help='window end (s)')
    ap.add_argument('--window', type=float, help='use the last N minutes instead of the automatic steady start')
    ap.add_argument('--min-len', type=float, default=10, help='shortest averaging window for the automatic start (min)')
    ap.add_argument('--head', type=float, default=2, help='minutes at the window start checked for a rising/falling edge')
    ap.add_argument('--max-slope', type=float, help='final steadiness threshold (unit/min); default 0.5%% of the mean')
    ap.add_argument('--split', type=int, default=1, choices=[1, 2, 3], help='split window into N parts -> c1..c3')
    a = ap.parse_args()

    t, data, t_first = read_series(a.series)
    with open(a.coords, encoding='utf-8-sig') as f:
        coords = {r['point_id'].strip(): r for r in csv.DictReader(f)}
    sensors = [k for k in data if k in coords and k not in a.background]
    missing = [k for k in data if k not in coords and k not in a.background]
    if not sensors:
        raise SystemExit('no sensor column matches a point_id in the coords file; check naming.')
    if missing:
        print(f'⚠ columns without coordinates, skipped: {", ".join(missing)}')
    nocol = [k for k in coords if k not in data]
    if nocol:
        print(f'⚠ in coords but not in log: {", ".join(nocol)}')

    bg = None
    if a.background:
        bg = np.nanmean(np.vstack([data[b] for b in a.background if b in data]), axis=0)
    Y = {s: data[s] - (bg if (a.subtract and bg is not None) else 0) for s in sensors}

    t1 = a.end if a.end is not None else t.max()
    if a.start is not None:
        t0, mode = a.start, 'manual'
    elif a.window is not None:
        t0, mode = t1 - a.window * 60, 'last'
    else:
        upto = t <= t1
        min_len = min(a.min_len * 60, (t1 - t.min()) / 2)
        M = np.vstack([Y[s][upto] for s in sensors])
        t0, diag = find_steady_start(t[upto], M, min_len, a.head * 60)
        mode = 'auto'
        if t0 is None:
            t0, mode = t1 - min_len, 'auto_failed'
        rejected = [d for d in diag if not d['ok']]
        if rejected:
            last = rejected[-1]
            why = []
            if abs(last['head_pct']) > HEAD_TOL * 100:
                why.append(f"starts on an edge (first {a.head:g} min {last['head_pct']:+.1f}% vs window mean)")
            if last['trending']:
                why.append('still trending: ' + ', '.join(f'{sensors[k]} {p:+.2f}%/min' for k, p in last['trending'][:5]))
            if not why:
                why.append(f"spatial-mean slope {last['slope_pct']:+.2f}%/min")
            print(f"Latest rejected start {_clock(t_first, last['t0'])}: " + '; '.join(why))

    sel = (t >= t0) & (t <= t1)
    if sel.sum() < 5:
        raise SystemExit(f'too few rows in window {t0:.0f}-{t1:.0f} s ({sel.sum()})')
    M = np.vstack([Y[s][sel] for s in sensors])
    mean_t = np.nanmean(M, axis=0)
    slope, _ = _slope(t[sel], mean_t)
    level = float(np.nanmean(mean_t))
    thr = a.max_slope if a.max_slope is not None else abs(level) * SLOPE_PCT / 100
    steady = abs(slope) <= thr and mode != 'auto_failed'

    parts = np.array_split(np.where(sel)[0], a.split)
    rows = []
    for s in sensors:
        y = Y[s]
        vals = [float(np.nanmean(y[idx])) for idx in parts]
        yw = y[sel]
        sd = float(np.nanstd(yw, ddof=1)); mu = float(np.nanmean(yw))
        note = f'SD={sd:.3g}，時間CV={100*sd/mu:.1f}%' if mu else ''
        nneg = int((yw < 0).sum()); nnan = int(np.isnan(yw).sum())
        if nneg or nnan:
            note += f'；窗口內負值 {nneg}、缺值 {nnan}'
        r = dict(point_id=s, x_m=coords[s]['x_m'], y_m=coords[s]['y_m'], note=note)
        for k, v in zip(('c1', 'c2', 'c3'), vals):
            r[k] = round(v, 4)
        rows.append(r)
    with open(a.out, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['point_id', 'x_m', 'y_m', 'c1', 'c2', 'c3', 'note'])
        w.writeheader(); w.writerows(rows)

    win = f'{_clock(t_first, t0)}–{_clock(t_first, t1)}'
    label = {'auto': 'automatic steady start', 'auto_failed': 'NO steady start found, last minutes used',
             'last': f'last {a.window} min (user choice)', 'manual': 'user-given start/end'}[mode]
    print(f'{len(t)} rows, interval ~{np.median(np.diff(t)):.0f} s, length {t.max():.0f} s')
    print(f'Window {win} ({t0:.0f}-{t1:.0f} s, {sel.sum()} rows), {len(sensors)} points, {label}'
          + (f', split into {a.split} -> c1-c{a.split}' if a.split > 1 else ''))
    if bg is not None:
        print(f'Background ({", ".join(a.background)}) window mean {np.nanmean(bg[sel]):.4g}'
              + (', subtracted' if a.subtract else ', not subtracted'))
    print(f'Spatial-mean slope {slope:+.4g} /min (threshold ±{thr:.3g}) -> '
          + ('quasi-steady' if steady else 'NOT steady; tell the user and suggest a longer log or another window'))
    how = {'auto': '穩定後 ', 'auto_failed': '最後 ', 'last': '最後 ', 'manual': ''}[mode]
    print(f'Suggested remark (paste as is): 代表值＝{how}{win} 平均（{sel.sum()} 筆）'
          + ('，穩定起點依時間趨勢自動判定' if mode == 'auto' else '')
          + ('，未達穩定' if not steady else '')
          + ('，已扣背景' if a.subtract else '，未扣背景') + f'；穩態斜率 {slope:+.3g}/min')
    print('Wrote', a.out)


if __name__ == '__main__':
    main()
