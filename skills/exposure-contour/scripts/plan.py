# -*- coding: utf-8 -*-
"""Planning: floor plan -> points and coordinate list (P1-P7).

Subcommands
  pdf2png    PDF plan -> PNG
  calibrate  scale calibration (P1) -> plan.json
  ruler      metre grid over the plan, to read equipment/obstacle/source coordinates
  count      initial point count and spacing from field size (P2)
  layout     uniform grid + chosen source points, every point >= 0.5 m from obstacle edges,
             coordinates to 0.1 m (P3, P4); writes the standard table with the layout map
             embedded below the basic info (the deliverable), a preview PNG and a coordinate
             CSV; optional field sheet, point measurement time table, instrument mapping table
  densify    round-2 densification by two rules, 0.5 m clearance, 0.1 m coordinates (P7)
  compare    hot-spot shift and peak change before/after, stop rule (P7)
  fieldsheet field sheet from a coordinate list (P6)

Origin (0, 0) = field bottom-left, X right, Y up, metres. Figure/sheet text stays Chinese.
"""
import argparse
import csv
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ecore as E  # noqa: E402

MAX_SPACING = 10.0     # max initial spacing (m)
NORM_SPACING = 0.15    # max normalised spacing (x diagonal)


# ─────────────────────────────── P1 ───────────────────────────────
def cmd_pdf2png(a):
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    doc = fitz.open(a.pdf)
    page = doc[a.page - 1]
    pix = page.get_pixmap(dpi=a.dpi)
    pix.save(a.out)
    print(f'Wrote {a.out} ({pix.width} x {pix.height} px, {a.dpi} dpi)')


def cmd_calibrate(a):
    from PIL import Image
    w, h = Image.open(a.image).size
    l, t, r, b = a.box if a.box else (0, 0, w, h)
    if not (0 <= l < r <= w and 0 <= t < b <= h):
        raise SystemExit(f'--box outside image ({w} x {h} px)')
    if a.field:
        fx, fy = a.field
    elif a.scale:
        px_len, m_len = a.scale
        mpp = m_len / px_len
        fx, fy = (r - l) * mpp, (b - t) * mpp
    else:
        raise SystemExit('give --field X Y (field size) or --scale PIXELS METRES (known length)')
    mppx, mppy = fx / (r - l), fy / (b - t)
    cal = dict(image=os.path.relpath(os.path.abspath(a.image), os.path.dirname(os.path.abspath(a.out))),
               image_size=[w, h], px_box=[l, t, r, b], field_x_m=round(fx, 3), field_y_m=round(fy, 3),
               m_per_px_x=mppx, m_per_px_y=mppy)
    E.save_json(cal, a.out)
    print(f'Field X {fx:.2f} m x Y {fy:.2f} m; scale X {mppx*1000:.1f} mm/px, Y {mppy*1000:.1f} mm/px')
    dev = abs(mppx - mppy) / max(mppx, mppy) * 100
    if dev > 3:
        print(f'⚠ X/Y scale differ by {dev:.1f}%: plan not to scale, box wrong, or field size wrong. Resolve.')
    print(f'Wrote {a.out}')


def _plan_axes(plt, cal, Lx, Ly, layout=None, alpha=1.0, figw=8.0):
    ar = Ly / Lx
    fig, ax = plt.subplots(figsize=(figw, max(3.0, min(14.0, figw * ar * 0.92 + 0.8))))
    if cal:
        img, ext = E.plan_image_cropped(cal)
        ax.imshow(img, extent=ext, origin='upper', alpha=alpha, zorder=0)
    draw_obstacles(ax, layout)
    ax.set_xlim(0, Lx); ax.set_ylim(0, Ly); ax.set_aspect('equal')
    ax.set_xlabel('X (m)'); ax.set_ylabel('Y (m)')
    for sp in ax.spines.values():
        sp.set_linewidth(1.2)
    return fig, ax


def draw_obstacles(ax, layout, label=True):
    from matplotlib.patches import Polygon
    if not layout:
        return
    for o in layout['obstacles']:
        ax.add_patch(Polygon(o['poly'], closed=True, facecolor='0.85', edgecolor='0.35',
                             hatch='////', lw=0.8, alpha=0.9, zorder=3))
        if label:
            cx, cy = o['poly'].mean(0)
            ax.text(cx, cy, o['name'], ha='center', va='center', fontsize=8, color='0.15', zorder=4,
                    bbox=dict(boxstyle='round,pad=0.15', fc='white', ec='none', alpha=0.7))


def cmd_ruler(a):
    plt = E.setup_matplotlib()
    cal = E.load_plan(a.plan)
    Lx, Ly = cal['field_x_m'], cal['field_y_m']
    layout = E.load_layout(a.layout) if a.layout else None
    fig, ax = _plan_axes(plt, cal, Lx, Ly, layout, figw=a.width)
    step = a.step or E.nice_step(0, max(Lx, Ly), 12)
    for v in np.arange(0, Lx + 1e-9, step):
        ax.axvline(v, color='#d62728', lw=0.5, alpha=0.7)
    for v in np.arange(0, Ly + 1e-9, step):
        ax.axhline(v, color='#d62728', lw=0.5, alpha=0.7)
    ax.set_xticks(np.arange(0, Lx + 1e-9, step)); ax.set_yticks(np.arange(0, Ly + 1e-9, step))
    ax.tick_params(labelsize=7)
    ax.set_title(f'座標格線（每格 {E.fmt(step)} m，原點左下角）', fontsize=10)
    fig.savefig(a.out, dpi=170, bbox_inches='tight')
    print(f'Wrote {a.out} (grid step {E.fmt(step)} m)')


# ─────────────────────────────── P2 ───────────────────────────────
def initial_count(Lx, Ly):
    """n = max[A / (0.15 x diagonal)^2, A / 100]."""
    A = Lx * Ly; diag = math.hypot(Lx, Ly)
    n1 = A / (NORM_SPACING * diag) ** 2
    n2 = A / MAX_SPACING ** 2
    n = max(n1, n2)
    n = int(math.ceil(n - 1e-6))
    return dict(n=max(n, 4), spacing=math.sqrt(A / max(n, 4)), area=A, diag=diag,
                control='正規化間距（0.15 × 對角線）' if n1 >= n2 else '間距上限 10 m')


def cmd_count(a):
    Lx, Ly = a.field
    r = initial_count(Lx, Ly)
    print(f'Field {E.fmt(Lx)} x {E.fmt(Ly)} m, area {E.fmt(r["area"])} m², diagonal {r["diag"]:.1f} m')
    print(f'Initial points {r["n"]}, spacing ~{r["spacing"]:.1f} m (controlled by: {r["control"]})')
    if a.minutes:
        t = r['n'] * a.minutes
        print(f'{a.minutes:g} min per point -> ~{t:.0f} min measuring (excl. walking and reference re-reads)')


# ─────────────────────────────── P3–P5 ───────────────────────────────
def grid_points(Lx, Ly, n_target):
    """Square grid, equal X/Y spacing, points at cell centres."""
    s = math.sqrt(Lx * Ly / n_target)
    nx = max(1, round(Lx / s)); ny = max(1, round(Ly / s))
    # count >= target, X/Y spacing as equal as possible; mild penalty for extra points
    best = None
    for dx in (-1, 0, 1, 2):
        for dy in (-1, 0, 1, 2):
            ax_, ay_ = max(1, nx + dx), max(1, ny + dy)
            if ax_ * ay_ < n_target:
                continue
            sx, sy = Lx / ax_, Ly / ay_
            score = abs(sx - sy) / s + 0.8 * (ax_ * ay_ - n_target) / n_target
            if best is None or score < best[0]:
                best = (score, ax_, ay_)
    _, nx, ny = best
    sx, sy = Lx / nx, Ly / ny
    xs = (np.arange(nx) + 0.5) * sx; ys = (np.arange(ny) + 0.5) * sy
    return [(float(x), float(y)) for y in ys for x in xs], sx, sy


def relocate(x, y, layout, Lx, Ly, rmax, step=None):
    """Move a point out of an obstacle to the nearest standable spot (<= rmax)."""
    if not E.in_obstacle(layout, np.array([x]), np.array([y]))[0]:
        return x, y, 0.0
    step = step or rmax / 8
    for r in np.arange(step, rmax + 1e-9, step):
        ang = np.linspace(0, 2 * np.pi, 24, endpoint=False)
        cx = np.clip(x + r * np.cos(ang), 0, Lx); cy = np.clip(y + r * np.sin(ang), 0, Ly)
        ok = ~E.in_obstacle(layout, cx, cy)
        if ok.any():
            i = np.argmax(ok)
            return float(cx[i]), float(cy[i]), float(r)
    return None


def number_points(pts, prefix):
    """Number from bottom-left, X first, then Y."""
    order = sorted(range(len(pts)), key=lambda i: (round(pts[i]['y'], 3), round(pts[i]['x'], 3)))
    w = max(2, len(str(len(pts))))
    for k, i in enumerate(order, 1):
        pts[i]['point_id'] = f'{prefix}{k:0{w}d}'
    return [pts[i] for i in order]


def write_points_csv(pts, path):
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['point_id', 'x_m', 'y_m', 'c1', 'c2', 'c3', 'note'])
        for p in pts:
            w.writerow([p['point_id'], E.round_coord(p['x']), E.round_coord(p['y']), '', '', '', p.get('note', '')])


def plot_points(plt, pts, Lx, Ly, cal, layout, title, out, extra=None):
    fig, ax = _plan_axes(plt, cal, Lx, Ly, layout, alpha=0.75 if cal else 1.0)
    if not cal:
        ax.grid(True, color='0.9', lw=0.5)
    for s in (layout or {}).get('sources', []):
        ax.scatter(s['x'], s['y'], marker='*', s=160, c='#ff7f0e', edgecolors='k', lw=0.6, zorder=6)
    fs = 8 if len(pts) <= 40 else 6.5
    for p in pts:
        new = p.get('stage') == 2
        ax.scatter(p['x'], p['y'], s=46 if not new else 52, zorder=7,
                   c='#d62728' if new else '#1f4e79', marker='D' if new else 'o',
                   edgecolors='white', lw=0.8)
        ax.annotate(p['point_id'], (p['x'], p['y']), xytext=(4, 4), textcoords='offset points',
                    fontsize=fs, zorder=8, color='k',
                    bbox=dict(boxstyle='round,pad=0.12', fc='white', ec='none', alpha=0.75))
    if extra:
        extra(ax)
    ax.set_title(title, fontsize=10)
    fig.savefig(out, dpi=180, bbox_inches='tight')
    plt.close(fig)


def cmd_layout(a):
    plt = E.setup_matplotlib()
    cal = E.load_plan(a.plan) if a.plan else None
    if a.field:
        Lx, Ly = a.field
    elif cal:
        Lx, Ly = cal['field_x_m'], cal['field_y_m']
    else:
        raise SystemExit('give --field X Y or --plan plan.json')
    layout = E.load_layout(a.layout) if a.layout else None
    cnt = initial_count(Lx, Ly)
    n_target = a.n or (round(Lx * Ly / a.spacing ** 2) if a.spacing else cnt['n'])
    grid, sx, sy = grid_points(Lx, Ly, n_target)
    s = math.sqrt(sx * sy)
    pts, log = [], []
    for (x, y) in grid:
        r = E.place_point(x, y, layout, Lx, Ly, clear=a.clear, rmax=s / 2)
        if r is None:
            log.append(f'格點 ({x:.1f}, {y:.1f}) 在障礙物或其 {a.clear:g} m 範圍內，半個間距內找不到可站位置，已刪除')
            continue
        nx_, ny_, moved = r
        p = dict(x=nx_, y=ny_, note='')
        if moved > 0.15:      # rounding to 0.1 m alone moves at most ~0.07 m
            p['note'] = f'原格點位於障礙物或其 {a.clear:g} m 範圍內，已移 {moved:.1f} m'
        pts.append(p)
    # sources the user chose to add points for (not every source needs one)
    for src in (layout or {}).get('sources', []):
        r = E.place_point(float(src['x']), float(src['y']), layout, Lx, Ly, clear=a.clear, rmax=2.0)
        if r is None:
            log.append(f"逸散點 {src.get('name', '')} 2 m 內找不到離障礙物 {a.clear:g} m 的位置，未加點")
            continue
        sx_, sy_, _ = r
        tag = f"逸散點：{src.get('name', '')}（{src.get('type', '')}）"
        d = [math.hypot(p['x'] - sx_, p['y'] - sy_) for p in pts]
        if pts and min(d) <= s / 3:
            p = pts[int(np.argmin(d))]
            p['x'], p['y'] = sx_, sy_
            p['note'] = (p['note'] + '；' if p['note'] else '') + tag + '，格點移至此'
        else:
            pts.append(dict(x=sx_, y=sy_, note=tag + '，加設'))
    pts = number_points(pts, a.prefix)
    if a.drop:
        pts = number_points([p for p in pts if p['point_id'] not in set(a.drop)], a.prefix)
    os.makedirs(a.out_dir, exist_ok=True)
    base = os.path.join(a.out_dir, a.name)
    write_points_csv(pts, base + '_座標清單.csv')
    title = (f'佈點 {len(pts)} 點（間距約 X {sx:.1f} m、Y {sy:.1f} m；離障礙物 ≥ {a.clear:g} m）'
             f'　編號由左下角起，先 X 後 Y')
    plot_points(plt, pts, Lx, Ly, cal, layout, title, base + '_佈點圖.png')
    # the deliverable: standard table with coordinates and the layout map embedded
    import build_table
    remark = f'初步佈點 {len(pts)} 點（{cnt["control"]}），間距約 {s:.1f} m，離障礙物邊界 ≥ {a.clear:g} m；量測高度 1.5 m'
    if a.minutes:
        remark += f'；每點量測 {a.minutes:g} 分鐘'
    meta = dict(site_name=a.site or '', field_x_m=round(Lx, 2), field_y_m=round(Ly, 2),
                c_name=a.pollutant or '', c_unit=a.unit or '', remark=remark)
    rows = [dict(point_id=p['point_id'], x_m=E.round_coord(p['x']), y_m=E.round_coord(p['y']), note=p['note'])
            for p in pts]
    xlsx = base + '_標準資料表.xlsx'
    build_table.build(meta, rows, xlsx)
    build_table.embed_image(xlsx, base + '_佈點圖.png',
                            f'佈點圖（{len(pts)} 點；編號由左下角起，先 X 後 Y；斜線為障礙物）')
    written = [xlsx, base + '_佈點圖.png', base + '_座標清單.csv']
    if a.fieldsheet:
        make_fieldsheet(pts, base + '_現場記錄表.xlsx', dict(meta, minutes=a.minutes))
        written.append(base + '_現場記錄表.xlsx')
    if a.time_table:
        build_table.build_simple('time', rows, base + '_點位量測時間表.xlsx', minutes=a.minutes, meta=meta)
        written.append(base + '_點位量測時間表.xlsx')
    if a.instrument_table:
        build_table.build_simple('instrument', rows, base + '_儀器點位對應表.xlsx', meta=meta)
        written.append(base + '_儀器點位對應表.xlsx')
    # clearance check against the true obstacles
    if layout:
        dd = E.obstacle_distance(layout, np.array([p['x'] for p in pts]), np.array([p['y'] for p in pts]))
        for p, d in zip(pts, dd):
            if d < a.clear - 1e-6:
                print(f"⚠ {p['point_id']} only {d:.2f} m from an obstacle")
    print(f'Field {E.fmt(Lx)} x {E.fmt(Ly)} m; formula {cnt["n"]} points ({cnt["control"]})')
    print(f'Laid out {len(pts)} points, spacing X {sx:.2f} m, Y {sy:.2f} m, clearance >= {a.clear:g} m')
    if len(pts) < cnt['n']:
        print(f'⚠ {len(pts)} points is below the formula minimum {cnt["n"]}: tell the user, offer points elsewhere')
    for m in log:
        print('⚠', m)
    moved = [p for p in pts if '已移' in p['note']]
    if moved:
        print(f'{len(moved)} points moved for clearance: ' + ', '.join(p['point_id'] for p in moved))
    for f in written:
        print('Wrote', f)
    print('Deliver after confirmation: ' + os.path.basename(xlsx) + ' (map embedded). Show the PNG for confirmation.')


# ─────────────────────────────── P6 ───────────────────────────────
def make_fieldsheet(pts, out, meta=None, n_ref=3):
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    meta = meta or {}
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = '現場記錄表'
    F = 'Arial'; t = Side(style='thin', color='808080'); B = Border(left=t, right=t, top=t, bottom=t)
    H = PatternFill('solid', fgColor='DDEBF7')
    ws.merge_cells('A1:I1')
    ws['A1'] = '直讀式儀器濃度分佈量測　現場記錄表'
    ws['A1'].font = Font(F, bold=True, size=14); ws['A1'].alignment = Alignment('center')
    info = [('場域名稱', meta.get('site_name', '')), ('量測日期', ''), ('污染物／單位',
            f"{meta.get('c_name', '')} {meta.get('c_unit', '')}".strip()),
            ('儀器型號／序號', ''), ('最近校正日期', ''), ('量測高度', '1.5 m（呼吸帶）'),
            ('作業狀態', ''), ('量測人員', ''),
            ('每點停留時間', f"{meta['minutes']:g} 分鐘" if meta.get('minutes') else '　　分鐘')]
    r = 3
    for i in range(0, len(info), 3):
        for j, (k, v) in enumerate(info[i:i + 3]):
            c0 = 1 + j * 3
            ws.cell(r, c0, k).font = Font(F, bold=True, size=10); ws.cell(r, c0).fill = H
            ws.merge_cells(start_row=r, start_column=c0 + 1, end_row=r, end_column=c0 + 2)
            ws.cell(r, c0 + 1, v).font = Font(F, size=10)
            for cc in range(c0, c0 + 3):
                ws.cell(r, cc).border = B
        ws.row_dimensions[r].height = 20
        r += 1
    r += 1
    ws.cell(r, 1, '固定參考點（量測前、中、後各讀一次，用來檢查時間漂移）').font = Font(F, bold=True, size=11)
    r += 1
    for j, h in enumerate(['參考點位置', '量測前 時間', '量測前 讀值', '量測中 時間', '量測中 讀值',
                           '量測後 時間', '量測後 讀值', '備註']):
        c = ws.cell(r, 1 + j, h); c.font = Font(F, bold=True, size=9); c.fill = H; c.border = B
        c.alignment = Alignment('center', 'center', wrap_text=True)
    ws.row_dimensions[r].height = 28
    r += 1
    for j in range(8):
        ws.cell(r, 1 + j).border = B
    ws.row_dimensions[r].height = 22
    r += 2
    heads = ['測點編號', 'X (m)', 'Y (m)', '時間', '讀值 1', '讀值 2', '讀值 3', '作業狀態／備註', '完成']
    for j, h in enumerate(heads):
        c = ws.cell(r, 1 + j, h); c.font = Font(F, bold=True, size=10); c.fill = H; c.border = B
        c.alignment = Alignment('center', 'center')
    ws.print_title_rows = f'{r}:{r}'
    r += 1
    for p in pts:
        vals = [p['point_id'], round(p['x'], 1), round(p['y'], 1), '', '', '', '', p.get('note', '')[:30], '☐']
        for j, v in enumerate(vals):
            c = ws.cell(r, 1 + j, v); c.border = B; c.font = Font(F, size=10)
            c.alignment = Alignment('center' if j != 7 else 'left', 'center', wrap_text=(j == 7))
        ws.row_dimensions[r].height = 24
        r += 1
    r += 1
    ws.cell(r, 1, '填寫提醒：未量測者讀值留空並於備註說明原因；讀值低於偵測極限寫「<LOD」；'
            '只填數字，不寫單位。').font = Font(F, size=9, color='595959')
    for j, w in enumerate([11, 8, 8, 9, 10, 10, 10, 26, 6]):
        ws.column_dimensions[openpyxl.utils.get_column_letter(1 + j)].width = w
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.orientation = 'portrait'
    ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = ws.page_margins.right = 0.4
    wb.save(out)


def cmd_fieldsheet(a):
    with open(a.points, encoding='utf-8-sig') as f:
        pts = [dict(point_id=r['point_id'], x=float(r['x_m']), y=float(r['y_m']), note=r.get('note', ''))
               for r in csv.DictReader(f)]
    make_fieldsheet(pts, a.out, dict(site_name=a.site or '', c_name=a.pollutant or '', c_unit=a.unit or ''))
    print('Wrote', a.out)


# ─────────────────────────────── P7 ───────────────────────────────
def densify_points(x, y, z, ids, spacing, Lx, Ly, layout=None, clear=E.CLEARANCE_M, max_move=2.0):
    """Two densification rules (interim report ch.5 s.1).

    Rule 1: cross of 4 points at spacing/2 around the highest point.
    Rule 2: midpoint between neighbours whose difference > field SD.
    """
    sd = float(np.std(z, ddof=1))
    new = []
    i = int(np.argmax(z)); h = spacing / 2
    for dx, dy in ((h, 0), (-h, 0), (0, h), (0, -h)):
        new.append(dict(x=x[i] + dx, y=y[i] + dy, rule=1, note=f'規則一：最高點 {ids[i]} 周圍十字補點'))
    P = np.c_[x, y]
    D = np.sqrt(((P[:, None] - P[None]) ** 2).sum(-1))
    nn = np.sort(np.where(D > 0, D, np.inf), 1)[:, 0]
    tol = 1.5 * np.median(nn)    # 「相鄰」＝距離不超過最近鄰中位數的 1.5 倍
    for a_ in range(len(x)):
        for b_ in range(a_ + 1, len(x)):
            if D[a_, b_] <= tol and abs(z[a_] - z[b_]) > sd:
                new.append(dict(x=(x[a_] + x[b_]) / 2, y=(y[a_] + y[b_]) / 2, rule=2,
                                note=f'規則二：{ids[a_]}–{ids[b_]} 濃度差 {abs(z[a_]-z[b_]):.3g} > 標準差 {sd:.3g}'))
    kept, dropped = [], []
    for p in new:
        if not (0 <= p['x'] <= Lx and 0 <= p['y'] <= Ly):
            dropped.append((p, '超出場域')); continue
        r = E.place_point(p['x'], p['y'], layout, Lx, Ly, clear=clear, rmax=max_move)
        if r is None:
            dropped.append((p, f'障礙物 {clear:g} m 範圍內，{max_move:g} m 內無可站位置')); continue
        if r[2] > 0.15:
            p['note'] += f'（為離障礙物 ≥ {clear:g} m 移 {r[2]:.1f} m）'
        p['x'], p['y'] = r[0], r[1]
        d_old = np.hypot(x - p['x'], y - p['y']).min()
        d_new = min([math.hypot(q['x'] - p['x'], q['y'] - p['y']) for q in kept] or [np.inf])
        if min(d_old, d_new) < spacing / 4:
            dropped.append((p, '與既有測點過近')); continue
        kept.append(p)
    return kept, dropped, sd


def cmd_densify(a):
    plt = E.setup_matplotlib()
    meta, rows, _ = E.read_table(a.table)
    Lx, Ly = E.field_dims(meta, a.field)
    res = E.derive_points(meta, rows, repeat=a.repeat, field=(Lx, Ly))
    inc = res['included']
    x = np.array([d['x'] for d in inc]); y = np.array([d['y'] for d in inc])
    z = np.array([d['c'] for d in inc]); ids = [d['point_id'] for d in inc]
    s = a.spacing or E.nnd(x, y)
    layout = E.load_layout(a.layout) if a.layout else None
    cal = E.load_plan(a.plan) if a.plan else None
    kept, dropped, sd = densify_points(x, y, z, ids, s, Lx, Ly, layout, clear=a.clear)
    w = max(2, len(str(len(inc) + len(kept))))
    for k, p in enumerate(kept, 1):
        p['point_id'] = f'{a.prefix}{k:0{w}d}'; p['stage'] = 2
    os.makedirs(a.out_dir, exist_ok=True)
    base = os.path.join(a.out_dir, a.name)
    write_points_csv(kept, base + '_加密點座標.csv')
    old = [dict(point_id=i, x=xx, y=yy, stage=1) for i, xx, yy in zip(ids, x, y)]

    def legend(ax):
        from matplotlib.lines import Line2D
        h = [Line2D([], [], marker='o', ls='', color='#1f4e79', mec='white', ms=7, label=f'原有測點（{len(old)} 點）'),
             Line2D([], [], marker='D', ls='', color='#d62728', mec='white', ms=7, label=f'建議補點（{len(kept)} 點）')]
        ax.legend(handles=h, loc='upper center', bbox_to_anchor=(0.5, -0.09), ncol=2, fontsize=9, frameon=False)
    # Two marker shapes only, no concentration colour scale: the figure is for finding the spots on site.
    title = '　'.join(v for v in (meta.get('site_name', ''), meta.get('c_name', '')) if v)
    plot_points(plt, old + kept, Lx, Ly, cal, layout,
                (title + '　' if title else '') + f'第二階補點建議（{len(kept)} 點）', base + '_補點建議圖.png',
                extra=legend)
    if kept:
        make_fieldsheet(kept, base + '_加密現場記錄表.xlsx',
                        dict(site_name=meta.get('site_name', ''), c_name=meta.get('c_name', ''),
                             c_unit=meta.get('c_unit', '')))
    print(f'Round 1: {len(inc)} valid points, spacing ~{s:.2f} m, SD {sd:.4g}')
    print(f'Suggest {len(kept)} new points (rule 1: {sum(p["rule"]==1 for p in kept)}, rule 2: {sum(p["rule"]==2 for p in kept)})')
    for p in kept:
        print(f"  {p['point_id']}  ({p['x']:.1f}, {p['y']:.1f})  {p['note']}")
    if dropped:
        print(f'Skipped {len(dropped)}: ' + '; '.join(f"({p['x']:.1f},{p['y']:.1f}) {why}" for p, why in dropped[:8]))
    print('Wrote', base + '_加密點座標.csv, ' + base + '_補點建議圖.png')


def cmd_compare(a):
    """Stop rule: hot-spot shift <= spacing/2 and map peak change <= 10%."""
    out = []
    for path in (a.before, a.after):
        meta, rows, _ = E.read_table(path)
        Lx, Ly = E.field_dims(meta, a.field)
        inc = E.derive_points(meta, rows, field=(Lx, Ly))['included']
        x, y, z = E.xyz(inc)
        gx, gy, Z = E.krige_grid(x, y, z, Lx, Ly)
        j, i = np.unravel_index(np.argmax(Z), Z.shape)
        out.append(dict(n=len(z), peak=float(Z[j, i]), px=float(gx[i]), py=float(gy[j]), s=E.nnd(x, y)))
    b, f = out
    s = a.spacing or b['s']
    shift = math.hypot(f['px'] - b['px'], f['py'] - b['py'])
    dpk = abs(f['peak'] - b['peak']) / b['peak'] * 100 if b['peak'] else float('nan')
    print(f"Before {b['n']} points: hot spot ({b['px']:.1f}, {b['py']:.1f}), map peak {E.fmt(b['peak'])}")
    print(f"After {f['n']} points: hot spot ({f['px']:.1f}, {f['py']:.1f}), map peak {E.fmt(f['peak'])}")
    print(f'Hot-spot shift {shift:.2f} m (limit spacing/2 = {s/2:.2f} m); peak change {dpk:.1f}% (limit 10%)')
    if shift <= s / 2 and dpk <= 10:
        print('✓ stable: stop densifying.')
    else:
        print('✗ hot spot or peak still changing: densify again around the new hot spot.')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)

    p = sp.add_parser('pdf2png'); p.add_argument('pdf'); p.add_argument('--page', type=int, default=1)
    p.add_argument('--dpi', type=int, default=200); p.add_argument('--out', required=True)

    p = sp.add_parser('calibrate'); p.add_argument('--image', required=True)
    p.add_argument('--box', type=float, nargs=4, metavar=('左', '上', '右', '下'),
                   help='field outline pixel box (default whole image)')
    p.add_argument('--field', type=float, nargs=2, metavar=('X', 'Y'), help='field size (m)')
    p.add_argument('--scale', type=float, nargs=2, metavar=('PIXELS', 'METRES'), help='a known length on the plan')
    p.add_argument('--out', default='plan.json')

    p = sp.add_parser('ruler'); p.add_argument('--plan', required=True); p.add_argument('--layout')
    p.add_argument('--step', type=float); p.add_argument('--width', type=float, default=10)
    p.add_argument('--out', required=True)

    p = sp.add_parser('count'); p.add_argument('--field', type=float, nargs=2, required=True)
    p.add_argument('--minutes', type=float, help='minutes per point, for effort estimate')

    for name in ('layout', 'densify'):
        p = sp.add_parser(name)
        p.add_argument('--plan'); p.add_argument('--layout', help='layout.json (obstacles, sources)')
        p.add_argument('--field', type=float, nargs=2)
        p.add_argument('--out-dir', default='.'); p.add_argument('--name', default='佈點' if name == 'layout' else '第二階')
        p.add_argument('--clear', type=float, default=E.CLEARANCE_M, help='min distance to obstacle edges (m)')
        if name == 'layout':
            p.add_argument('--n', type=int, help='point count (default formula)')
            p.add_argument('--spacing', type=float, help='spacing m')
            p.add_argument('--prefix', default='P')
            p.add_argument('--site'); p.add_argument('--pollutant'); p.add_argument('--unit')
            p.add_argument('--minutes', type=float, help='dwell time per point (min), written to remark/tables')
            p.add_argument('--drop', nargs='*', default=[], help='point IDs the user rejects; rest renumbered')
            p.add_argument('--fieldsheet', action='store_true', help='also write the A4 field sheet')
            p.add_argument('--time-table', action='store_true', help='also write the point measurement time table')
            p.add_argument('--instrument-table', action='store_true', help='also write the instrument-point mapping table')
        else:
            p.add_argument('--table', required=True, help='round-1 standard table')
            p.add_argument('--spacing', type=float, help='round-1 spacing (default mean NN distance)')
            p.add_argument('--prefix', default='Q')
            p.add_argument('--repeat', default='mean')

    p = sp.add_parser('compare'); p.add_argument('--before', required=True); p.add_argument('--after', required=True)
    p.add_argument('--spacing', type=float); p.add_argument('--field', type=float, nargs=2)

    p = sp.add_parser('fieldsheet'); p.add_argument('--points', required=True); p.add_argument('--out', required=True)
    p.add_argument('--site'); p.add_argument('--pollutant'); p.add_argument('--unit')

    a = ap.parse_args()
    globals()['cmd_' + a.cmd](a)


if __name__ == '__main__':
    main()
