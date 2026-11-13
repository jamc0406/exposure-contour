# -*- coding: utf-8 -*-
"""Instrument logs -> points.csv for build_table.py.

walk : one instrument carried point to point. Log = time + one concentration column.
       Point times come from the point measurement time table (點位量測時間表: point_id, x_m, y_m,
       start_time, end_time, duration_min), or from --start/--dwell/--walk with a coordinate list
       in visiting order. Per point, end = end_time if filled, else start + duration_min, unless
       --minutes overrides both. Value = mean of readings in [start + skip, end).
       A point listed more than once (e.g. the fixed reference point before, during and after) is
       merged into one row: visits go to c1-c3 in time order (more than 3 -> c1 = mean of all), and
       the drift (drift.py: <= 10% acceptable, 10-30% note, > 30% re-measure) is written into that
       point's note and into the suggested remark (appended to --meta if given). A repeated point
       without coordinates is used for the drift only and is not mapped.
multi: several instruments logging at the same time (time + one column per instrument, columns
       named by instrument ID) plus the instrument-point mapping table (儀器點位對應表:
       instrument_id, point_id, x_m, y_m). Runs timeseries.py on the instrument columns (default:
       automatic steady start to the end of the log), then renames instruments to point IDs.

Both tables may be the standard xlsx (row 1 codes, row 2 Chinese labels) or a plain csv/xlsx with
either English codes or Chinese labels as headers. Coordinates are written to 0.1 m.

Usage:
  python logs_to_points.py walk  log.xlsx --times 點位量測時間表.xlsx --out points.csv [--skip SECONDS]
  python logs_to_points.py walk  log.xlsx --times 開始時間表.csv --coords 座標清單.csv --minutes MINUTES --out points.csv
  python logs_to_points.py walk  log.csv --coords 座標清單.csv --start "YYYY-MM-DD HH:MM:SS" --dwell SECONDS --walk SECONDS --out points.csv
  python logs_to_points.py multi log.xlsx --mapping 儀器點位對應表.xlsx --out points.csv [--window MINUTES | --start S --end S]
"""
import argparse
import csv
import datetime as dt
import os
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drift as D  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PID = ('point_id', '點位編號', '測點編號', '點位')
X = ('x_m', 'X 座標 (m)', 'X 座標', 'X (m)', 'X', 'x')
Y = ('y_m', 'Y 座標 (m)', 'Y 座標', 'Y (m)', 'Y', 'y')
INS = ('instrument_id', '儀器編號', 'instrument', '儀器', 'sensor')
START = ('start_time', '開始時間', 'start', '開始', '時間')
END = ('end_time', '結束時間', 'end', '結束')
DUR = ('duration_min', '測量時長 (分鐘)', '測量時長', '時長', 'duration')
ZH_LABELS = {'點位編號', '儀器編號', '開始時間'}


def r1(v):
    return float(round(float(v) * 10) / 10)


def pick(df, names, required=True):
    for n in df.columns:
        if str(n).strip() in names:
            return n
    if required:
        raise SystemExit(f'column not found, expected one of {names}; got {list(df.columns)}')
    return None


def read_table(path, sheet=None):
    """Read a csv/xlsx table; drop the Chinese label row of the standard two-header format."""
    if str(path).lower().endswith(('.xlsx', '.xls')):
        df = pd.read_excel(path, sheet_name=sheet if sheet is not None else 0)
    else:
        df = pd.read_csv(path, encoding='utf-8-sig')
    df = df.loc[:, [c for c in df.columns if not str(c).startswith('Unnamed')]]
    if len(df) and any(str(v).strip() in ZH_LABELS for v in df.iloc[0].values):
        df = df.iloc[1:]
    first = df.columns[0]
    return df[df[first].notna() & (df[first].astype(str).str.strip() != '')].reset_index(drop=True)


def blank(v):
    return v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() in ('', 'NaT', 'nan')


def to_ts(v, day):
    """Excel datetime / time / text -> Timestamp; time-only values take the log's date."""
    if isinstance(v, dt.time):
        return pd.Timestamp(dt.datetime.combine(day, v))
    if isinstance(v, (pd.Timestamp, dt.datetime)):
        return pd.Timestamp(v)
    s = str(v).strip()
    if len(s) <= 8 and ':' in s:
        return pd.Timestamp(f'{day} {s}')
    return pd.Timestamp(s)


def write(rows, out):
    with open(out, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['point_id', 'x_m', 'y_m', 'c1', 'c2', 'c3', 'note'])
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in w.fieldnames})
    print('Wrote', out, f'({len(rows)} points)')


def walk(a):
    log = read_table(a.log, a.log_sheet)
    tcol = log.columns[0]; ccol = a.column or log.columns[1]
    t = pd.to_datetime(log[tcol]); c = pd.to_numeric(log[ccol], errors='coerce')
    day = t.iloc[0].date()
    if a.minutes:
        a.dwell = a.minutes * 60
    xy = {}
    if a.coords:
        cr = read_table(a.coords)
        xy = {str(r[pick(cr, PID)]).strip(): (float(r[pick(cr, X)]), float(r[pick(cr, Y)])) for _, r in cr.iterrows()}
    sch = []
    if a.times:
        s = read_table(a.times, a.times_sheet)
        cp, cs = pick(s, PID), pick(s, START)
        ce, cd = pick(s, END, False), pick(s, DUR, False)
        cx, cy = pick(s, X, False), pick(s, Y, False)
        for _, r in s.iterrows():
            p = str(r[cp]).strip()
            if blank(r[cs]):
                print(f'⚠ {p}: no start time, skipped'); continue
            if cx is not None and not blank(r[cx]) and not blank(r[cy]):
                x, y = float(r[cx]), float(r[cy])
            elif p in xy:
                x, y = xy[p]
            else:
                x = y = None   # allowed only for a repeated reference point (checked below)
            s0 = to_ts(r[cs], day)
            e = None if ce is None or blank(r[ce]) else to_ts(r[ce], day)
            d = None if cd is None or blank(r[cd]) else float(r[cd])
            if a.dwell:
                s1, how = s0 + pd.Timedelta(seconds=a.dwell), f'開始後 {a.dwell/60:g} 分鐘'
            elif e is not None:
                s1, how = e, '開始至結束時間'
                if d is not None and abs((e - s0).total_seconds() / 60 - d) > 0.1:
                    print(f'⚠ {p}: end time and duration disagree ({(e - s0).total_seconds()/60:.1f} vs {d:g} min); used end time')
            elif d is not None:
                s1, how = s0 + pd.Timedelta(minutes=d), f'開始後 {d:g} 分鐘'
            else:
                raise SystemExit(f'{p}: give end_time or duration_min in the table, or --minutes')
            sch.append((p, x, y, s0, s1, how))
    else:
        if not (a.coords and a.start and a.dwell):
            raise SystemExit('give --times (point measurement time table), or --coords (visiting order) with --start and --dwell [--walk]')
        t0 = pd.Timestamp(a.start); step = a.dwell + (a.walk or 0)
        for i, (p, (x, y)) in enumerate(xy.items()):
            sch.append((p, x, y, t0 + pd.Timedelta(seconds=i * step),
                        t0 + pd.Timedelta(seconds=i * step + a.dwell), f'開始後 {a.dwell/60:g} 分鐘'))
    srt = sorted(sch, key=lambda q: q[3])
    for q0, q1 in zip(srt, srt[1:]):
        if q0[4] > q1[3]:
            print(f'⚠ {q0[0]}: averaging window ends {q0[4]:%H:%M:%S}, after {q1[0]} starts {q1[3]:%H:%M:%S}; shorten the duration')
    dts = np.diff(t.values).astype('timedelta64[ms]').astype(float) / 1000
    step_s = float(np.median(dts)) if len(dts) else 0
    if t.iloc[0] > srt[0][3] or t.iloc[-1] < srt[-1][3]:
        print(f'⚠ log covers {t.iloc[0]:%H:%M:%S}–{t.iloc[-1]:%H:%M:%S} but points run {srt[0][3]:%H:%M:%S}–{srt[-1][4]:%H:%M:%S}: check the instrument clock and date')
    visits = {}   # point_id -> list of (start, end, how, mean, n, cv); time-table order kept
    meta_xy = {}
    for p, x, y, s0, s1, how in sch:
        sel = (t >= s0 + pd.Timedelta(seconds=a.skip)) & (t < s1)
        v = c[sel].dropna()
        expect = int(round(((s1 - s0).total_seconds() - a.skip) / step_s)) if step_s else 0
        meta_xy.setdefault(p, (x, y))
        if len(v) == 0:
            visits.setdefault(p, []).append((s0, s1, how, None, 0, None))
            print(f'⚠ {p}: no readings in {s0:%H:%M:%S}–{s1:%H:%M:%S}'); continue
        mu = float(v.mean()); sd = float(v.std(ddof=1)) if len(v) > 1 else 0.0
        if len(v) < expect:
            print(f'⚠ {p}: {len(v)} readings, expected ~{expect}')
        visits.setdefault(p, []).append((s0, s1, how, mu, len(v), 100 * sd / mu if mu else None))

    rows, drift_lines, worst = [], [], None
    for p, vs in visits.items():
        x, y = meta_xy[p]
        good = sorted([q for q in vs if q[3] is not None], key=lambda q: q[0])
        if len(vs) == 1:
            if x is None:
                raise SystemExit(f'no coordinates for {p}: fill X/Y in the time table or give --coords')
            s0, s1, how, mu, n, cv = vs[0]
            if mu is None:
                rows.append(dict(point_id=p, x_m=r1(x), y_m=r1(y), note='時段內無讀值，未量測')); continue
            note = f'{s0:%H:%M:%S}–{s1:%H:%M:%S}（{how}）共 {n} 筆平均' + (f'；CV={cv:.1f}%' if cv is not None else '')
            rows.append(dict(point_id=p, x_m=r1(x), y_m=r1(y), c1=round(mu, 4), note=note))
            continue
        # same point measured at different times -> drift (manual v5, ch. 8.5)
        if len(good) < 2:
            print(f'⚠ {p}: measured {len(vs)} times but only {len(good)} visit(s) with readings; no drift computed')
            note = '重複量測，但有效讀值不足兩次，無法計算漂移'
        else:
            text, r = D.remark_text([q[3] for q in good], [f'{q[0]:%H:%M}' for q in good], point=f'{p} ',
                                    accept=a.accept, retest=a.retest)
            note = text
            drift_lines.append(text)
            if worst is None or r['rate_pct'] > worst[1]['rate_pct']:
                worst = (p, r)
            flag = {'ok': '', 'note': '（需記錄於備註）', 'retest': '（建議重測）'}[r['level']]
            print(f'Drift at {p}: {r["rate_pct"]:.1f}% -> {r["level"]}{flag}')
        if x is None:
            print(f'  {p} has no coordinates: used for drift only, not mapped')
            continue
        rec = dict(point_id=p, x_m=r1(x), y_m=r1(y), note=note)
        if len(good) <= 3:
            for k, q in zip(('c1', 'c2', 'c3'), good):
                rec[k] = round(q[3], 4)
        elif good:
            rec['c1'] = round(float(np.mean([q[3] for q in good])), 4)
            rec['note'] = note + f'；量測1＝{len(good)} 次平均'
        rows.append(rec)

    print(f'{len(log)} log rows, interval ~{step_s:g} s, {len(sch)} time-table rows, {len(rows)} points'
          + (f', first {a.skip:g} s of each point dropped' if a.skip else ''))
    remark = '單機逐點量測，每點取量測時段內' + (f'（去除前 {a.skip:g} 秒）' if a.skip else '') + '讀值平均'
    if drift_lines:
        remark += '；' + '；'.join(drift_lines)
    else:
        print('No point was measured more than once: no drift computed. '
              'Manual v5 asks for a fixed reference point read before, during and after.')
    print('Suggested remark: ' + remark)
    if a.meta:
        import json
        with open(a.meta, encoding='utf-8') as f:
            meta = json.load(f)
        old = str(meta.get('remark') or '').strip()
        meta['remark'] = (old + ('' if old.endswith(('。', '；')) else '；') if old else '') + remark
        with open(a.meta, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print('Remark appended to', a.meta)
    write(rows, a.out)


def multi(a):
    m = read_table(a.mapping, a.mapping_sheet)
    ins, pid, x, y = pick(m, INS), pick(m, PID), pick(m, X), pick(m, Y)
    mp = {str(r[ins]).strip(): (str(r[pid]).strip(), float(r[x]), float(r[y])) for _, r in m.iterrows()}
    log_cols = [str(cn).strip() for cn in read_table(a.log, a.log_sheet).columns[1:]]
    missing = [k for k in mp if k not in log_cols]
    unmapped = [k for k in log_cols if k not in mp]
    if unmapped:
        print('⚠ log columns without a mapping row (skipped): ' + ', '.join(unmapped))
    tmp = tempfile.mkdtemp()
    cf = os.path.join(tmp, 'coords.csv'); of = os.path.join(tmp, 'ts.csv')
    with open(cf, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f); w.writerow(['point_id', 'x_m', 'y_m'])
        for k, (p, xx, yy) in mp.items():
            if k not in missing:
                w.writerow([k, xx, yy])
    cmd = [sys.executable, os.path.join(HERE, 'timeseries.py'), a.log, '--coords', cf, '--out', of]
    for o in ('window', 'start', 'end', 'split', 'max_slope', 'min_len', 'head'):
        if getattr(a, o) is not None:
            cmd += ['--' + o.replace('_', '-'), str(getattr(a, o))]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout, r.stderr, sep='')
    if r.returncode:
        raise SystemExit('timeseries.py failed')
    rows = []
    for t in csv.DictReader(open(of, encoding='utf-8-sig')):
        if t['point_id'] not in mp:
            continue
        p, xx, yy = mp[t['point_id']]
        t.update(point_id=p, x_m=r1(xx), y_m=r1(yy), note=f"儀器 {t['point_id']}；{t.get('note', '')}".rstrip('；'))
        rows.append(t)
    for k in missing:
        p, xx, yy = mp[k]
        rows.append(dict(point_id=p, x_m=r1(xx), y_m=r1(yy), note=f'儀器 {k} 無紀錄，未量測'))
        print(f'⚠ instrument {k} (point {p}) has no column in the log: left blank')
    rows.sort(key=lambda q: q['point_id'])
    write(rows, a.out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    w = sp.add_parser('walk', help='one instrument, point to point')
    w.add_argument('log'); w.add_argument('--log-sheet'); w.add_argument('--column')
    w.add_argument('--times', '--schedule', dest='times', help='point measurement time table (點位量測時間表)')
    w.add_argument('--times-sheet', '--schedule-sheet', dest='times_sheet')
    w.add_argument('--coords', help='point_id,x_m,y_m: coordinates for a table without X/Y, or the visiting order')
    w.add_argument('--start', help='no table: start time of the first point')
    w.add_argument('--dwell', type=float, help='seconds averaged per point')
    w.add_argument('--minutes', type=float, help='minutes averaged after each start (overrides the table)')
    w.add_argument('--walk', type=float, help='no table: walking seconds between points')
    w.add_argument('--skip', type=float, default=0, help='seconds dropped at the start of each point (response time)')
    w.add_argument('--meta', help='meta.json for build_table.py: the remark (incl. drift) is appended to it')
    w.add_argument('--accept', type=float, default=D.ACCEPT, help='drift acceptable up to this %% (default 10)')
    w.add_argument('--retest', type=float, default=D.RETEST, help='re-measure above this drift %% (default 30)')
    w.add_argument('--out', required=True)
    m = sp.add_parser('multi', help='several instruments at the same time')
    m.add_argument('log'); m.add_argument('--log-sheet')
    m.add_argument('--mapping', required=True, help='instrument-point mapping table (儀器點位對應表)')
    m.add_argument('--mapping-sheet')
    m.add_argument('--out', required=True)
    for o in ('--window', '--start', '--end', '--split', '--max-slope', '--min-len', '--head'):
        m.add_argument(o, help='passed to timeseries.py')
    a = ap.parse_args()
    walk(a) if a.cmd == 'walk' else multi(a)


if __name__ == '__main__':
    main()
