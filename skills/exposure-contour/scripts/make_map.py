# -*- coding: utf-8 -*-
"""Concentration map from the standard table, plus reliability, statistics, hot zones, OEL zones.

Functions: M1 kriging map, M2 variogram comparison (advanced), M3 plan overlay,
  M4 obstacle mask, M5 OEL contour, M6 grid CSV, Q1 leave-one-out RRMSE / MAPE and the 3
  largest errors (>= 20% on either -> recommend adding points), Q2 point suggestions (>= 0.5 m
  from obstacles, 0.1 m coordinates), R1 statistics, R2 hot zones, R3 areas above OEL / action
  levels, R8 parameter record (results.json). No management advice or report is produced.

Usage:
  python make_map.py table.xlsx --out-dir out [--plan plan.json] [--layout layout.json]
                     [--oel USER_GIVEN] [--zones A,B] [--colormap Jet] [--labels]
  python make_map.py table.xlsx --colormap-preview --out-dir out   # five colour scales
  python make_map.py table.xlsx --compare-models --out-dir out     # advanced: variogram LOOCV

Defaults = ConcTour: ordinary kriging, linear variogram, slope 1, nugget 0, anisotropy 1,
120 cells long side, Jet, clipped at 0. Extrapolation not marked; only user obstacles hatched.
Figure text, warnings and results.json strings stay Chinese (user-facing).
"""
import argparse
import csv
import datetime as dt
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ecore as E  # noqa: E402

VERSION = 'exposure-contour 1.2'


# ---- plotting ----
def fig_size(Lx, Ly, w=8.0):
    ar = Ly / Lx
    return (w, max(3.2, min(13.0, w * ar * 0.86 + 1.0)))


def base_axes(plt, Lx, Ly, cal=None, plan_alpha=1.0, w=8.0):
    fig, ax = plt.subplots(figsize=fig_size(Lx, Ly, w))
    if cal:
        img, ext = E.plan_image_cropped(cal)
        ax.imshow(img, extent=ext, origin='upper', alpha=plan_alpha, zorder=0)
    ax.set_xlim(0, Lx); ax.set_ylim(0, Ly); ax.set_aspect('equal')
    ax.set_xlabel('X (m)'); ax.set_ylabel('Y (m)')
    for sp in ax.spines.values():
        sp.set_linewidth(1.3)
    return fig, ax


def draw_mask(ax, layout):
    from matplotlib.patches import Polygon
    if not layout:
        return
    for o in layout['obstacles']:
        ax.add_patch(Polygon(o['poly'], closed=True, facecolor='white', edgecolor='0.3',
                             hatch='////', lw=0.9, zorder=5))
        cx, cy = o['poly'].mean(0)
        ax.text(cx, cy, o['name'], ha='center', va='center', fontsize=8, zorder=6,
                bbox=dict(boxstyle='round,pad=0.15', fc='white', ec='none', alpha=0.85))


def draw_map(plt, gx, gy, Z, pts, meta, Lx, Ly, a, cal, layout, levels, cmap_name, title, out,
             oel=None, extra=None):
    alpha = a.map_alpha if a.map_alpha is not None else (0.6 if cal else 1.0)
    fig, ax = base_axes(plt, Lx, Ly, cal)
    GX, GY = np.meshgrid(gx, gy)
    cmap = E.get_cmap(cmap_name)
    cf = ax.contourf(GX, GY, Z, levels=levels, cmap=cmap, alpha=alpha, zorder=1, extend='neither')
    ax.contour(GX, GY, Z, levels=levels, colors='k', linewidths=0.35, alpha=0.45, zorder=2)
    if oel and not a.no_oel_line and Z.min() < oel < Z.max():
        cs = ax.contour(GX, GY, Z, levels=[oel], colors='#b91c1c', linewidths=2.6, zorder=4)
        ax.clabel(cs, fmt={oel: f'OEL {E.fmt(oel)}'}, fontsize=8)
    draw_mask(ax, layout)
    xs = [p['x'] for p in pts]; ys = [p['y'] for p in pts]
    ax.scatter(xs, ys, s=a.point_size, c='k', edgecolors='white', lw=0.6, zorder=7)
    if a.labels:
        for p in pts:
            ax.annotate(E.fmt(p['c']), (p['x'], p['y']), xytext=(0, 5), textcoords='offset points',
                        ha='center', fontsize=a.label_size, color=a.label_color, zorder=8)
    if extra:
        extra(ax)
    cb = plt.colorbar(cf, ax=ax, shrink=0.88, pad=0.025)
    cb.set_label(f"{meta.get('c_name', '')} ({meta.get('c_unit', '')})".strip(), fontsize=9)
    cb.ax.tick_params(labelsize=8)
    ax.set_title(title, fontsize=10.5)
    fig.savefig(out, dpi=a.dpi, bbox_inches='tight')
    plt.close(fig)


def draw_suggestions(plt, pts, sug, Lx, Ly, cal, layout, title, out, dpi):
    """Point-suggestion figure: plan, hatched obstacles, existing points (circles, IDs) and suggested
    points (diamonds, 建議1..k). No concentration colour scale: the figure is for finding spots on site."""
    from matplotlib.lines import Line2D
    fig, ax = base_axes(plt, Lx, Ly, cal, plan_alpha=0.75 if cal else 1.0)
    draw_mask(ax, layout)
    fs = 8 if len(pts) <= 40 else 6.5
    for p in pts:
        ax.scatter(p['x'], p['y'], s=46, c='#1f4e79', marker='o', edgecolors='white', lw=0.8, zorder=7)
        ax.annotate(p['point_id'], (p['x'], p['y']), xytext=(4, 4), textcoords='offset points', fontsize=fs,
                    zorder=8, bbox=dict(boxstyle='round,pad=0.12', fc='white', ec='none', alpha=0.75))
    for k, s in enumerate(sug, 1):
        ax.scatter(s['x'], s['y'], s=52, c='#d62728', marker='D', edgecolors='white', lw=0.8, zorder=9)
        ax.annotate(f'建議{k}', (s['x'], s['y']), xytext=(4, 4), textcoords='offset points', fontsize=fs,
                    color='#d62728', zorder=9, bbox=dict(boxstyle='round,pad=0.12', fc='white', ec='none', alpha=0.8))
    h = [Line2D([], [], marker='o', ls='', color='#1f4e79', mec='white', ms=7, label=f'原有測點（{len(pts)} 點）'),
         Line2D([], [], marker='D', ls='', color='#d62728', mec='white', ms=7, label=f'建議補點（{len(sug)} 點）')]
    ax.legend(handles=h, loc='upper center', bbox_to_anchor=(0.5, -0.09), ncol=2, fontsize=9, frameon=False)
    ax.set_title(title, fontsize=10.5)
    fig.savefig(out, dpi=dpi, bbox_inches='tight')
    plt.close(fig)


# ---- analysis ----
def suggest_points(x, y, gx, gy, V, layout, spacing, k=4, clear=E.CLEARANCE_M):
    """Q2: points at max kriging variance, >= clear from obstacle edges (so never in narrow gaps
    or against equipment), away from walls and existing points, >= one spacing apart; 0.1 m."""
    GX, GY = np.meshgrid(gx, gy)
    v = V.copy()
    v[E.obstacle_distance(layout, GX, GY) < clear] = -1
    m = min(spacing / 2, 1.0)            # wall margin
    v[(GX < m) | (GX > gx[-1] - m) | (GY < m) | (GY > gy[-1] - m)] = -1
    order = np.argsort(v.ravel())[::-1]
    picks = []
    Lx, Ly = float(gx[-1]), float(gy[-1])
    for idx in order:
        if len(picks) >= k or v.ravel()[idx] <= 0:
            break
        px, py = GX.ravel()[idx], GY.ravel()[idx]
        if np.hypot(x - px, y - py).min() < spacing * 0.75:
            continue
        if any(math.hypot(px - q[0], py - q[1]) < spacing for q in picks):
            continue
        r = E.place_point(px, py, layout, Lx, Ly, clear=clear, rmax=0.3)   # round to 0.1 m, keep clearance
        if r is None:
            continue
        picks.append((r[0], r[1], float(v.ravel()[idx])))
    vmax = float(V.max()) or 1.0
    return [dict(x=p[0], y=p[1], rel_uncertainty=round(math.sqrt(p[2] / vmax), 2)) for p in picks]


def hotspots(gx, gy, Z, valid, pts, layout, spacing, frac=0.8):
    """R2: hot zone = connected area with map >= min + 80% x range."""
    from scipy import ndimage
    zmin, zmax = float(Z[valid].min()), float(Z[valid].max())
    thr = zmin + frac * (zmax - zmin)
    lab, n = ndimage.label((Z >= thr) & valid)
    cell = (gx[1] - gx[0]) * (gy[1] - gy[0])
    out = []
    for k in range(1, n + 1):
        m = lab == k
        j, i = np.unravel_index(np.argmax(np.where(m, Z, -np.inf)), Z.shape)
        GX, GY = np.meshgrid(gx, gy)
        h = dict(peak=float(Z[j, i]), x=float(gx[i]), y=float(gy[j]), area_m2=float(m.sum() * cell),
                 cx=float(GX[m].mean()), cy=float(GY[m].mean()))
        # distance to the obstacle EDGE (a long machine whose edge is close counts as near), and to sources
        near = sorted((d, nm) for nm, d in E.distance_to_each(layout, h['x'], h['y']))
        near = [(d, nm) for d, nm in near if d <= 1.5 * spacing][:3]
        h['near'] = [nm for d, nm in near]
        h['near_m'] = [round(d, 1) for d, nm in near]
        top = max(pts, key=lambda p: p['c'] if math.hypot(p['x'] - h['x'], p['y'] - h['y']) <= 1.5 * spacing else -1)
        if math.hypot(top['x'] - h['x'], top['y'] - h['y']) <= 1.5 * spacing:
            h['point'] = top['point_id']
        out.append(h)
    out.sort(key=lambda h: -h['peak'])
    return dict(threshold=thr, regions=out[:5])


def zoning(Z, valid, cell, thresholds, oel):
    edges = [-np.inf] + list(thresholds) + [np.inf]
    names = []
    if oel and list(thresholds) == [0.5 * oel, oel]:
        names = ['< 50% OEL', '50%–100% OEL', '≥ OEL']
    else:
        names = [f'< {E.fmt(thresholds[0])}'] + \
                [f'{E.fmt(a)}–{E.fmt(b)}' for a, b in zip(thresholds[:-1], thresholds[1:])] + \
                [f'≥ {E.fmt(thresholds[-1])}']
    tot = valid.sum()
    zs = []
    for k in range(len(edges) - 1):
        m = valid & (Z >= edges[k]) & (Z < edges[k + 1])
        zs.append(dict(zone=names[k], area_m2=float(m.sum() * cell), pct=float(100 * m.sum() / tot)))
    return zs


def model_compare(x, y, z):
    """M2: variogram LOOCV comparison (advanced; default map unchanged)."""
    rows = [dict(model='linear（固定，預設）', params=dict(psill=1.0, nugget=0.0),
                 **E.metrics(z, E.loocv(x, y, z)))]
    for m in ('spherical', 'exponential', 'gaussian', 'linear'):
        p = E.fit_variogram(x, y, z, m)
        if p is None:
            rows.append(dict(model=m + '（擬合）', params=None, RRMSE_pct=float('nan'), MAPE_pct=float('nan'), note='實驗變異圖組數不足'))
            continue
        pred = E.loocv(x, y, z, m, p)
        r = dict(model=m + '（擬合）', params=p, **E.metrics(z, pred))
        nn = E.nnd(x, y)
        if m != 'linear' and p['range'] < nn:
            r['note'] = f'變程 {p["range"]:.2f} m 小於平均測點間距 {nn:.2f} m，圖面會呈牛眼狀'
        if not np.all(np.isfinite(pred)) or (np.ptp(pred) < 1e-9):
            r['note'] = '退化（輸出近似常數場）'
        rows.append(r)
    return rows


def colormap_preview(plt, gx, gy, Z, pts, meta, Lx, Ly, levels, out):
    names = list(E.COLORSCALES)
    ncol = 3 if Lx >= Ly else 5
    nrow = math.ceil(len(names) / ncol)
    w = 4.2 if Lx >= Ly else 2.6
    fig, axs = plt.subplots(nrow, ncol, figsize=(w * ncol, w * nrow * min(2.2, max(0.55, Ly / Lx)) + 0.6))
    axs = np.atleast_1d(axs).ravel()
    GX, GY = np.meshgrid(gx, gy)
    for ax, nm in zip(axs, names):
        cf = ax.contourf(GX, GY, Z, levels=levels, cmap=E.get_cmap(nm))
        ax.contour(GX, GY, Z, levels=levels, colors='k', linewidths=0.3, alpha=0.4)
        ax.scatter([p['x'] for p in pts], [p['y'] for p in pts], s=8, c='k')
        ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(f'{names.index(nm) + 1}. {nm}\n{E.COLORSCALE_NOTE[nm]}', fontsize=8.5)
    for ax in axs[len(names):]:
        ax.axis('off')
    fig.suptitle('色階選項（同一份資料）', fontsize=12)
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches='tight')
    plt.close(fig)


# ---- main ----
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('table')
    ap.add_argument('--out-dir', default='.')
    ap.add_argument('--name', help='output prefix (default: table file name)')
    ap.add_argument('--plan', help='plan.json from plan.py calibrate')
    ap.add_argument('--layout', help='layout.json (obstacles, sources)')
    ap.add_argument('--field', type=float, nargs=2, help='override field size X Y (m)')
    ap.add_argument('--repeat', default='mean', help='repeat mode: mean/1/2/3/max')
    ap.add_argument('--zero', default='keep', choices=['keep', 'exclude'])
    ap.add_argument('--drop', nargs='*', default=[], help='outlier IDs the user chose to drop')
    ap.add_argument('--drop-reason', default='')
    ap.add_argument('--oel', type=float, help='OEL or action value (same unit)')
    ap.add_argument('--no-oel-line', action='store_true', help='hide OEL contour')
    ap.add_argument('--zones', help='custom zone thresholds, e.g. 50,100')
    ap.add_argument('--colormap', default='Jet', choices=list(E.COLORSCALES))
    ap.add_argument('--colormap-preview', action='store_true')
    ap.add_argument('--grid', type=int, default=E.GRID_N, help='long-side cells (default 120)')
    ap.add_argument('--levels', type=int, default=10, help='approx. number of colour levels')
    ap.add_argument('--map-alpha', type=float, help='map opacity 0-1 (0.6 with a plan)')
    ap.add_argument('--labels', action='store_true', help='print values at points')
    ap.add_argument('--label-size', type=float, default=8)
    ap.add_argument('--label-color', default='black')
    ap.add_argument('--point-size', type=float, default=22)
    ap.add_argument('--title')
    ap.add_argument('--dpi', type=int, default=200)
    ap.add_argument('--compare-models', action='store_true')
    ap.add_argument('--suggest', type=int, default=4, help='number of point suggestions')
    ap.add_argument('--clear', type=float, default=E.CLEARANCE_M, help='suggestions keep this distance from obstacles (m)')
    a = ap.parse_args()

    plt = E.setup_matplotlib()
    meta, rows, labels = E.read_table(a.table)
    Lx, Ly = E.field_dims(meta, a.field)
    cal = E.load_plan(a.plan) if a.plan else None
    if cal and (abs(cal['field_x_m'] - Lx) > 0.05 * Lx or abs(cal['field_y_m'] - Ly) > 0.05 * Ly):
        print(f"⚠ plan size {cal['field_x_m']}x{cal['field_y_m']} m differs from table {Lx}x{Ly} m; using table")
        cal = dict(cal, field_x_m=Lx, field_y_m=Ly)
    layout = E.load_layout(a.layout) if a.layout else None
    res = E.derive_points(meta, rows, repeat=a.repeat, zero=a.zero, drop=a.drop, field=(Lx, Ly))
    pts = res['included']
    if len(pts) < 4:
        raise SystemExit(f'only {len(pts)} valid points; need 4. Run validate_table.py first.')
    x, y, z = E.xyz(pts)
    name = a.name or os.path.splitext(os.path.basename(a.table))[0]
    os.makedirs(a.out_dir, exist_ok=True)
    base = os.path.join(a.out_dir, name)

    gx, gy, Z, V = E.krige_grid(x, y, z, Lx, Ly, a.grid, return_var=True)
    GX, GY = np.meshgrid(gx, gy)
    masked = E.in_obstacle(layout, GX, GY)
    valid = ~masked
    cell = (gx[1] - gx[0]) * (gy[1] - gy[0])
    zlo, zhi = float(min(Z[valid].min(), z.min())), float(max(Z[valid].max(), z.max()))
    levels = E.levels_for(zlo, zhi, a.levels)
    title = a.title or f"{str(meta.get('site_name', '')).splitlines()[0]}　{meta.get('c_name', '')}".strip()
    warnings_ = list(res['notes'])
    for hit in E.points_in_obstacles(layout, pts):
        warnings_.append(f"測點 {hit['point_id']} ({hit['x']:g}, {hit['y']:g}) 落在障礙物「{hit['obstacle']}」範圍內（含邊上）："
                         "請使用者確認是座標有誤、儀器放在機台或平台上，還是圖上障礙物範圍大於實際")

    if a.colormap_preview:
        colormap_preview(plt, gx, gy, Z, pts, meta, Lx, Ly, levels, base + '_色階範例.png')
        print('Wrote', base + '_色階範例.png')
        print('Colour scales (show user): ' + '；'.join(f'{i+1}. {k}：{v}' for i, (k, v) in enumerate(E.COLORSCALE_NOTE.items())))
        return

    # M1/M3/M4/M5
    draw_map(plt, gx, gy, Z, pts, meta, Lx, Ly, a, cal, layout, levels, a.colormap, title,
             base + '_分佈圖.png', oel=a.oel)

    # M6 grid CSV (as ConcTour: raw coords, clipped at 0; obstacle flag)
    with open(base + '_網格.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['x_m', 'y_m', 'concentration', 'in_obstacle'])
        for j in range(len(gy)):
            for i in range(len(gx)):
                w.writerow([round(gx[i], 4), round(gy[j], 4), round(float(Z[j, i]), 6), int(masked[j, i])])

    # Q1 LOOCV
    pred = E.loocv(x, y, z)
    q = E.metrics(z, pred, [p['point_id'] for p in pts])
    spacing = E.nnd(x, y)
    rng = E.spherical_range(x, y, z)
    # Q2 point suggestions
    sug = suggest_points(x, y, gx, gy, V, layout, spacing, a.suggest, a.clear)

    if sug:
        draw_suggestions(plt, pts, sug, Lx, Ly, cal, layout, title + '　補點建議', base + '_補點建議.png', a.dpi)

    # R1 statistics
    st = E.stats([p['c'] for p in pts], a.oel)
    # R2 hot zones
    hs = hotspots(gx, gy, Z, valid, pts, layout, spacing)
    # R3 areas above OEL / action levels (no advice)
    zones = None
    thr = [float(v) for v in a.zones.split(',')] if a.zones else ([0.5 * a.oel, a.oel] if a.oel else None)
    if thr:
        zones = zoning(Z, valid, cell, thr, a.oel)
        from matplotlib.colors import BoundaryNorm, ListedColormap
        cols = ['#2ca02c', '#ffdd57', '#d62728'] if len(thr) == 2 else \
            list(plt.get_cmap('RdYlGn_r')(np.linspace(0.1, 0.9, len(thr) + 1)))
        fig, ax = base_axes(plt, Lx, Ly, cal)
        bnd = [min(zlo, thr[0]) - 1] + thr + [max(zhi, thr[-1]) + 1]
        ax.contourf(GX, GY, Z, levels=bnd, colors=cols, alpha=0.55 if cal else 0.85, zorder=1)
        ax.contour(GX, GY, Z, levels=thr, colors='k', linewidths=1.2, zorder=2)
        draw_mask(ax, layout)
        ax.scatter(x, y, s=14, c='k', zorder=6)
        from matplotlib.patches import Patch
        ax.legend(handles=[Patch(fc=c, ec='k', label=f"{zz['zone']}　{zz['pct']:.0f}%") for c, zz in zip(cols, zones)],
                  loc='upper left', bbox_to_anchor=(1.01, 1), fontsize=8, frameon=False, title='OEL 分區（面積比）',
                  title_fontsize=9)
        ax.set_title(title + '　OEL 分區', fontsize=10.5)
        fig.savefig(base + '_OEL分區.png', dpi=a.dpi, bbox_inches='tight')
        plt.close(fig)

    # M2 advanced
    mc = None
    if a.compare_models:
        mc = model_compare(x, y, z)

    # map peak vs measured max
    zmax_map = float(Z[valid].max())
    if zmax_map < 0.9 * z.max():
        warnings_.append(f'圖面最高值 {E.fmt(zmax_map)} 低於實測最高值 {E.fmt(float(z.max()))}（網格未落在測點上或測點位於障礙區）')
    if res['counts'].get('zero'):
        warnings_.append(f"有 {res['counts']['zero']} 點濃度為 0 並納入計算；GM／GSD 只以大於 0 的值計算")
    if q['verdict'] == '建議補點':
        warnings_.append(f"留一交叉驗證 RRMSE {q['RRMSE_pct']:.1f}%、MAPE {q['MAPE_pct']:.1f}%，"
                         f"至少一項 ≥ {E.ADD_POINTS_PCT:g}%：建議補點（最高點周圍十字點優先，再補濃度梯度，最後補空白區）")

    excluded = [dict(point_id=d['point_id'], status=E.STATUS_ZH.get(d['status'], d['status']), value=d.get('c'))
                for d in res['rows'] if d['status'] not in ('ok', 'zero', 'high')]
    results = dict(
        tool=VERSION, created=dt.datetime.now().isoformat(timespec='seconds'),
        source=dict(table=os.path.basename(a.table), site=meta.get('site_name'), date=str(meta.get('survey_date', '')),
                    pollutant=meta.get('c_name'), unit=meta.get('c_unit'), lod=meta.get('c_LOD'),
                    remark=meta.get('remark'), column_labels=labels),
        field=dict(x_m=Lx, y_m=Ly, area_m2=Lx * Ly, plan=bool(cal), obstacles=[o['name'] for o in (layout or {}).get('obstacles', [])]),
        processing=dict(repeat=a.repeat, zero=a.zero, lod_substitution='LOD/√2', lod_points=res['lod_n'],
                        outlier_rule='Q3+3×IQR，標示不剔除', outlier_threshold=res['outlier_threshold'],
                        user_dropped=a.drop, drop_reason=a.drop_reason,
                        flagged_high=[d['point_id'] for d in res['rows'] if d['status'] == 'high'],
                        excluded=excluded, n_rows=len(res['rows']), n_used=len(pts)),
        method=dict(interpolation='普通克利金', variogram='linear', slope=1.0, nugget=0.0, anisotropy=1.0,
                    grid=[len(gx), len(gy)], grid_cell_m=[float(gx[1] - gx[0]), float(gy[1] - gy[0])],
                    lower_bound=0, colormap=a.colormap, levels=[float(v) for v in levels],
                    extrapolation_marked=False, obstacle_mask=bool(layout and layout['obstacles'])),
        stats=st,
        map=dict(min=float(Z[valid].min()), max=zmax_map, mean=float(Z[valid].mean())),
        quality=dict(loocv=q, clearance_m=a.clear, mean_spacing_m=spacing, spherical_range_m=rng,
                     spacing_range_ratio=(spacing / rng) if rng else None,
                     loocv_points=[dict(point_id=d['point_id'], obs=float(o), pred=float(p_))
                                   for d, o, p_ in zip(pts, z, pred)] if len(pts) == len(z) else None,
                     suggestions=sug),
        hotspots=hs, oel=a.oel, zones=zones,
        over_oel=(dict(area_m2=next(zz['area_m2'] for zz in zones if zz['zone'].startswith('≥')),
                       pct=next(zz['pct'] for zz in zones if zz['zone'].startswith('≥')),
                       points=st.get('n_over_oel')) if (zones and a.oel) else None), model_compare=mc, warnings=warnings_,
        outputs=[os.path.basename(base + s) for s in ('_分佈圖.png', '_網格.csv') ] +
                ([os.path.basename(base + '_補點建議.png')] if sug else []) +
                ([os.path.basename(base + '_OEL分區.png')] if zones else []),
    )
    E.save_json(results, base + '_results.json')

    # summary
    print(f"{title}: valid points {len(pts)}/{len(res['rows'])}, grid {len(gx)}x{len(gy)}")
    print(f"Measured min {E.fmt(st['min'])}, max {E.fmt(st['max'])}, mean {E.fmt(st['mean'])}, "
          f"GM {E.fmt(st.get('gm'))}, GSD {E.fmt(st.get('gsd'), 2)}, CV {E.fmt(st['cv_pct'], 1)}%")
    print(f"Leave-one-out: RRMSE {q['RRMSE_pct']:.1f}%, MAPE {q['MAPE_pct']:.1f}% -> {q['verdict']} "
          f"(threshold {E.ADD_POINTS_PCT:g}%); mean spacing {spacing:.2f} m")
    print('  3 largest absolute errors: ' + '; '.join(
        f"{w['point_id']} measured {E.fmt(w['obs'])}, predicted {E.fmt(w['pred'])}, error {w['error']:+.3g}"
        + (f" ({w['error_pct']:.0f}%)" if w['error_pct'] is not None else '') for w in q['largest_errors']))
    for k, h in enumerate(hs['regions'][:3], 1):
        print(f"Hot zone {k}: peak {E.fmt(h['peak'])} at ({h['x']:.1f}, {h['y']:.1f}), area {h['area_m2']:.1f} m²"
              + (f", near {', '.join(f'{n} ({d:g} m)' for n, d in zip(h['near'], h['near_m']))}" if h['near'] else '') + (f", point {h['point']}" if h.get('point') else ''))
    if zones:
        print('Zones: ' + '; '.join(f"{zz['zone']} {zz['pct']:.0f}% ({zz['area_m2']:.1f} m²)" for zz in zones))
    if a.oel:
        print(f"Points above OEL {E.fmt(a.oel)}: {st.get('n_over_oel', 0)} of {len(pts)}")
    if sug:
        print('Suggested points: ' + '; '.join(f"({s['x']}, {s['y']})" for s in sug))
    if mc:
        print('Variogram comparison (LOOCV):')
        for r in mc:
            print(f"  {r['model']:<18s} RRMSE {r.get('RRMSE_pct', float('nan')):.1f}%  MAPE {r.get('MAPE_pct', float('nan')):.1f}%"
                  + (f"  ⚠ {r['note']}" if r.get('note') else ''))
    for w_ in warnings_:
        print('⚠', w_)
    print('Wrote: ' + ', '.join(results['outputs'] + [os.path.basename(base + '_results.json')]))


if __name__ == '__main__':
    main()
