# -*- coding: utf-8 -*-
"""Data validation (D5, D6; seven checks + coverage).

Usage:
  python validate_table.py table.xlsx [--layout layout.json] [--repeat mean|1|2|3|max]
                                      [--zero keep|exclude] [--json out.json]
Exit code 1 if any must-fix item, else 0.

Checks
  1 text in numeric cell     -> must fix
  2 negative value           -> must fix
  3 zero                     -> warn (real zero vs not measured; kept, --zero exclude)
  4 coordinates outside field-> must fix
  5 duplicate point ID       -> must fix
  6 note <LOD                -> warn (LOD/sqrt2; >1/3 of points must be reported)
  7 blank (not measured)     -> warn (excluded); blank without reason -> must fix
  Also: required metadata, high outliers (Q3+3xIQR, flagged not dropped), hull coverage, valid count,
        and with --layout: points inside a confirmed obstacle -> warn (coordinates are kept as
        given; ask the user: coordinate error, instrument on the machine/platform, or obstacle
        drawn larger than it really is?)
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ecore as E  # noqa: E402


def hull_coverage(x, y, Lx, Ly):
    if len(x) < 3:
        return 0.0
    try:
        from scipy.spatial import ConvexHull
        return float(ConvexHull(np.c_[x, y]).volume / (Lx * Ly))
    except Exception:
        return float('nan')


def check(path, repeat='mean', zero='keep', field=None, layout=None):
    meta, rows, labels = E.read_table(path)
    err, warn, info = [], [], []
    for k in E.REQ_META:
        if k not in meta:
            (err if k in ('field_x_m', 'field_y_m') else warn).append(f'metadata missing: {k}')
    fx, fy = (field if field else (E.num(meta.get('field_x_m')), E.num(meta.get('field_y_m'))))
    res = E.derive_points(meta, rows, repeat=repeat, zero=zero, field=(fx, fy) if fx and fy else None)
    # 1 text
    for r in rows:
        for k in ('x_m', 'y_m', 'c1', 'c2', 'c3'):
            v = r.get(k)
            if isinstance(v, str) and v.strip() and E.num(v) is None:
                hint = 'leave blank if not measured and give reason in note' if v.strip().lower() in E.BAD_TEXT else 'use a plain number (no unit/comma)'
                err.append(f'[1] row {r["row"]} {k} has text "{v}": {hint}')
    for d in res['rows']:
        loc = f'row {d["row"]} {d["point_id"]}'
        st = d['status']
        if st == 'neg':
            err.append(f'[2] {loc} negative value {d["c"]}')
        elif st in ('zero', 'zero_excl'):
            warn.append(f'[3] {loc} value 0: confirm real reading vs not measured (blank)'
                        + ('; currently kept' if st == 'zero' else '; currently excluded'))
        elif st == 'oob':
            err.append(f'[4] {loc} ({d["x"]}, {d["y"]}) outside field 0-{fx} x 0-{fy} m')
        elif st == 'missing':
            if d['note'].strip():
                warn.append(f'[7] {loc} not measured (note: {d["note"][:20]}), excluded')
            else:
                err.append(f'[7] {loc} blank with no reason in note')
        elif st == 'invalid' and (d['x'] is None or d['y'] is None):
            err.append(f'{loc} coordinate blank or non-numeric')
        if d.get('lod'):
            warn.append(f'[6] {loc} <LOD, substituted LOD/√2 = {d["c"]:.4g}')
    if any(E.is_lod_note(r.get('note')) for r in rows) and not E.num(meta.get('c_LOD')):
        err.append('[6] <LOD in notes but c_LOD is empty')
    # 5 duplicate IDs
    ids = [str(r.get('point_id')).strip() for r in rows if r.get('point_id') not in (None, '')]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        err.append(f'[5] duplicate point IDs: {", ".join(dup[:10])}')
    # duplicate coordinates (different IDs)
    seen = {}
    for d in res['included']:
        seen.setdefault((round(d['x'], 3), round(d['y'], 3)), []).append(d['point_id'])
    for k, v in seen.items():
        if len(v) > 1:
            warn.append(f'duplicate coordinates: {", ".join(v)} at ({k[0]}, {k[1]}), averaged when mapping')
    # high outliers
    for d in res['rows']:
        if d['status'] in ('high', 'highdrop'):
            warn.append(f'high outlier: {d["point_id"]} = {d["c"]:.4g} (Q3+3xIQR = {res["outlier_threshold"]:.4g})'
                        f', {"dropped by user" if d["status"] == "highdrop" else "kept by default"}. '
                        'Ask user: near a source? repeat reproduced? neighbours high? temporary task?')
    warn.extend(res['notes'])
    inc = res['included']
    for hit in E.points_in_obstacles(layout, inc):
        warn.append(f'point {hit["point_id"]} ({hit["x"]:g}, {hit["y"]:g}) lies inside obstacle "{hit["obstacle"]}" '
                    '(edge included). Ask user: coordinate error, instrument on the machine/platform, '
                    'or obstacle drawn larger than it is? Never move the point yourself.')
    n = len(inc)
    if n < 4:
        err.append(f'only {n} valid points; need at least 4')
    cov = None
    if n >= 3 and fx and fy:
        x = np.array([d['x'] for d in inc]); y = np.array([d['y'] for d in inc])
        cov = hull_coverage(x, y, fx, fy)
        info.append(f'convex hull covers {cov*100:.0f}% of field')
        if cov < 0.6:
            warn.append(f'convex hull covers only {cov*100:.0f}%; outside is extrapolated, less reliable')
        if np.ptp(x) == 0 or np.ptp(y) == 0:
            err.append('points must spread in both X and Y')
    cnt = res['counts']
    info.insert(0, f'{len(res["rows"])} rows, {n} valid points'
                + (f' (incl. {cnt.get("zero", 0)} zeros)' if cnt.get('zero') else ''))
    return dict(meta=meta, err=err, warn=warn, info=info, coverage=cov, result=res, labels=labels)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('table')
    ap.add_argument('--repeat', default='mean')
    ap.add_argument('--zero', default='keep', choices=['keep', 'exclude'])
    ap.add_argument('--field', type=float, nargs=2)
    ap.add_argument('--layout', help='layout.json: warn about points inside confirmed obstacles')
    ap.add_argument('--json')
    a = ap.parse_args()
    r = check(a.table, a.repeat, a.zero, a.field, E.load_layout(a.layout) if a.layout else None)
    for s in r['info']:
        print('・', s)
    for s in r['warn']:
        print('⚠', s)
    for s in r['err']:
        print('✗', s)
    print('✓ passed' if not r['err'] else f'✗ {len(r["err"])} must-fix item(s)')
    if a.json:
        E.save_json(dict(errors=r['err'], warnings=r['warn'], info=r['info'], coverage=r['coverage']), a.json)
    return 1 if r['err'] else 0


if __name__ == '__main__':
    sys.exit(main())
