# -*- coding: utf-8 -*-
"""exposure-contour shared library.

Table I/O, value rules, QAQC, kriging, grid, statistics, LOOCV metrics,
colour scales, plan calibration, obstacle mask. Defaults match ConcTour
(linear variogram, slope 1, nugget 0, 120 cells long side, Jet, outliers Q3+3xIQR),
so the same data gives the same result in both. User-facing strings stay Chinese.
"""
from __future__ import annotations

import json
import math
import os
import warnings

import numpy as np

warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

# ---- constants ----
SHEET = '基本資料與量測濃度'
META_FIELDS = [  # (code, Chinese label, unit, required)
    ('site_name', '場域名稱', '', True),
    ('survey_date', '量測日期', 'YYYY-MM-DD', True),
    ('field_x_m', '場域 X 方向長度', 'm', True),
    ('field_y_m', '場域 Y 方向長度', 'm', True),
    ('c_name', '污染物名稱', '', True),
    ('c_unit', '污染物單位', '', True),
    ('c_LOD', '儀器偵測極限', '同上單位', False),
]
REQ_META = [c for c, _, _, r in META_FIELDS if r]
PT_COLS = ['point_id', 'x_m', 'y_m', 'c1', 'c2', 'c3', 'note']
GRID_N = 120            # long-side cells (ConcTour default)
OUTLIER_K = 3.0         # outlier threshold Q3 + K x IQR
BAD_TEXT = {'n/a', 'na', 'nd', '無', '—', '-', '--', 'null', 'none', '未測'}


def num(v):
    """To float; blank, text, NaN -> None."""
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip()
        if v == '':
            return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


# ---- fonts ----
def setup_matplotlib():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    want = ['Noto Sans CJK TC', 'Noto Sans CJK JP', 'Noto Sans CJK SC', 'Microsoft JhengHei',
            'PingFang TC', 'Heiti TC', 'Arial Unicode MS', 'WenQuanYi Zen Hei',
            'Droid Sans Fallback', 'SimHei']
    have = {f.name for f in font_manager.fontManager.ttflist}
    found = [f for f in want if f in have]
    plt.rcParams['font.sans-serif'] = found + ['DejaVu Sans']
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['axes.unicode_minus'] = False
    if not found:
        print('⚠ no CJK font found; Chinese on figures may show as boxes. Install Noto Sans CJK and rerun.')
    return plt


# ---- colour scales ----
# Same five as ConcTour; Jet uses the Plotly definition. Notes below are user-facing.
COLORSCALES = {
    'Jet': [(0, '#000083'), (0.125, '#003caa'), (0.375, '#05ffff'),
            (0.625, '#ffff00'), (0.875, '#fa0000'), (1, '#800000')],
    'Viridis': 'viridis',
    'RdYlGn_r': [(0, '#006837'), (0.1, '#1a9850'), (0.2, '#66bd63'), (0.3, '#a6d96a'),
                 (0.4, '#d9ef8b'), (0.5, '#ffffbf'), (0.6, '#fee08b'), (0.7, '#fdae61'),
                 (0.8, '#f46d43'), (0.9, '#d73027'), (1, '#a50026')],
    'Hot_r': [(0, '#ffffff'), (0.4, '#ffd200'), (0.7, '#e60000'), (1, '#000000')],
    'Plasma': 'plasma',
}
COLORSCALE_NOTE = {
    'Jet': '藍→青→黃→紅，傳統等值線圖慣用，ConcTour 預設',
    'Viridis': '紫→綠→黃，色盲友善、黑白列印仍可分辨深淺',
    'RdYlGn_r': '綠→黃→紅，直覺對應「安全→注意→危險」，適合管理簡報',
    'Hot_r': '白→黃→紅→黑，低濃度區接近白色，疊平面圖時底圖較清楚',
    'Plasma': '藍紫→橘→黃，色盲友善、對比強',
}


def get_cmap(name='Jet'):
    import matplotlib
    from matplotlib.colors import LinearSegmentedColormap
    spec = COLORSCALES.get(name)
    if spec is None:
        raise SystemExit(f'unknown colormap {name}; available: {", ".join(COLORSCALES)}')
    if isinstance(spec, str):
        return matplotlib.colormaps[spec]
    return LinearSegmentedColormap.from_list(name, spec)


# ---- standard table ----
def read_table(path):
    """Read standard table v5.0 (single sheet). Returns (meta, rows, labels).

    rows: list of dicts keyed by PT_COLS plus 'row' (Excel row).
    labels: c1-c3 row-2 labels, for the report.
    Also accepts csv (point_id,x_m,y_m,c1[,c2,c3,note]) and the old two-sheet xlsx.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == '.csv':
        import csv
        with open(path, encoding='utf-8-sig') as f:
            rd = list(csv.DictReader(f))
        rows = []
        for i, r in enumerate(rd):
            d = {k: (r.get(k) if r.get(k) not in ('',) else None) for k in PT_COLS}
            d['row'] = i + 2
            if d['point_id'] is not None or d['x_m'] is not None:
                rows.append(d)
        return {}, rows, {}
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[SHEET] if SHEET in wb.sheetnames else wb.worksheets[0]
    head = [str(c.value).strip() if c.value is not None else '' for c in ws[1]]
    head2 = [c.value for c in ws[2]] if ws.max_row >= 2 else []
    col = {h: i for i, h in enumerate(head) if h}
    meta, rows, labels = {}, [], {}
    for k in ('c1', 'c2', 'c3'):
        if k in col and col[k] < len(head2) and head2[col[k]]:
            labels[k] = str(head2[col[k]])
    for r_i, row in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
        if 'field_code' in col and 'value' in col:
            k = row[col['field_code']] if col['field_code'] < len(row) else None
            if isinstance(k, str) and k.strip():
                v = row[col['value']] if col['value'] < len(row) else None
                if v is not None and str(v).strip() != '':
                    meta[k.strip()] = v
        if 'point_id' in col:
            d = {k: (row[col[k]] if k in col and col[k] < len(row) else None) for k in PT_COLS}
            if any(d[k] not in (None, '') for k in ('point_id', 'x_m', 'y_m', 'c1')):
                d['row'] = r_i
                rows.append(d)
    # old two-sheet format: points on sheet 2
    if not rows and len(wb.worksheets) > 1:
        ws2 = wb.worksheets[1]
        h = [str(c.value).strip() if c.value is not None else '' for c in ws2[1]]
        c2 = {x: i for i, x in enumerate(h) if x}
        for r_i, row in enumerate(ws2.iter_rows(min_row=3, values_only=True), start=3):
            d = {k: (row[c2[k]] if k in c2 else None) for k in PT_COLS}
            if any(d[k] not in (None, '') for k in ('point_id', 'x_m', 'y_m')):
                d['row'] = r_i
                rows.append(d)
    if 'remark' not in meta:
        # remark is a merged cell, value in column C
        for r_i in range(3, min(ws.max_row, 40) + 1):
            if ws.cell(r_i, 1).value == 'remark' and ws.cell(r_i, 3).value:
                meta['remark'] = ws.cell(r_i, 3).value
    return meta, rows, labels


def field_dims(meta, override=None):
    if override:
        return float(override[0]), float(override[1])
    fx, fy = num(meta.get('field_x_m')), num(meta.get('field_y_m'))
    if not fx or not fy:
        raise SystemExit('table lacks field_x_m / field_y_m; fill them or pass --field X Y.')
    return fx, fy


def is_lod_note(note):
    return isinstance(note, str) and ('lod' in note.lower()) and ('<' in note or '＜' in note or '低於' in note)


def derive_points(meta, rows, repeat='mean', zero='keep', drop=(), field=None):
    """Turn each row into one value (ConcTour rules) and classify for QAQC.

    repeat: mean (default)/1/2/3/max. zero: keep (default, warn)/exclude.
    drop: outlier IDs the user chose to exclude.
    Returns dict(included, rows (each with status), counts, lod_n, notes).
    status: ok / high (kept) / highdrop (user-dropped) / zero / zero_excl /
            neg / oob / invalid / missing / dup_coord (averaged)
    """
    lod = num(meta.get('c_LOD'))
    fx, fy = field if field else (num(meta.get('field_x_m')), num(meta.get('field_y_m')))
    drop = {str(d).strip() for d in drop}
    out, notes = [], []
    lod_n = 0
    for r in rows:
        pid = str(r.get('point_id')).strip() if r.get('point_id') not in (None, '') else f"R{r.get('row')}"
        x, y = num(r.get('x_m')), num(r.get('y_m'))
        reps = [num(r.get(k)) for k in ('c1', 'c2', 'c3')]
        txt = [r.get(k) for k in ('c1', 'c2', 'c3')]
        note = r.get('note') if isinstance(r.get('note'), str) else ''
        d = dict(point_id=pid, x=x, y=y, reps=reps, note=note, row=r.get('row'), lod=False)
        if x is None or y is None:
            d['status'] = 'invalid'; out.append(d); continue
        if any(t not in (None, '') and num(t) is None for t in txt):
            d['status'] = 'invalid'; d['why'] = '濃度欄含文字'; out.append(d); continue
        vals = [v for v in reps if v is not None]
        c = None
        if repeat == 'mean':
            c = sum(vals) / len(vals) if vals else None
        elif repeat == 'max':
            c = max(vals) if vals else None
        else:
            c = reps[int(repeat) - 1]
        if c is None and is_lod_note(note) and lod:
            c = lod / math.sqrt(2); d['lod'] = True; lod_n += 1
        d['c'] = c
        if c is None:
            d['status'] = 'missing'
        elif c < 0:
            d['status'] = 'neg'
        elif fx and fy and not (0 <= x <= fx and 0 <= y <= fy):
            d['status'] = 'oob'
        elif c == 0:
            d['status'] = 'zero' if zero == 'keep' else 'zero_excl'
        else:
            d['status'] = 'ok'
        out.append(d)
    # outlier threshold from ok points only (as ConcTour; unaffected by user drops)
    ok = [d for d in out if d['status'] in ('ok', 'zero')]
    thr = None
    if len(ok) >= 5:
        cs = np.sort([d['c'] for d in ok])
        q1, q3 = np.percentile(cs, 25), np.percentile(cs, 75)
        if q3 - q1 > 0:
            thr = q3 + OUTLIER_K * (q3 - q1)
            for d in ok:
                if d['c'] > thr:
                    d['status'] = 'highdrop' if d['point_id'] in drop else 'high'
    included = [d for d in out if d['status'] in ('ok', 'zero', 'high')]
    counts = {}
    for d in out:
        counts[d['status']] = counts.get(d['status'], 0) + 1
    n_valid = len(included)
    if lod_n and n_valid and lod_n > n_valid / 3:
        notes.append(f'低於偵測極限之測點 {lod_n} 點，超過有效測點三分之一，報告中須敘明以 LOD/√2 代入。')
    return dict(included=included, rows=out, counts=counts, lod_n=lod_n,
                outlier_threshold=thr, notes=notes, repeat=repeat, zero=zero)


STATUS_ZH = {
    'ok': '納入', 'high': '可疑高值（納入）', 'highdrop': '可疑高值（使用者排除）',
    'zero': '濃度為 0（納入，請確認）', 'zero_excl': '濃度為 0（排除）', 'neg': '負值（排除）',
    'oob': '座標超出場域（排除）', 'invalid': '座標或濃度非數值（排除）', 'missing': '未量測（排除）',
}


def xyz(included):
    """x, y, z; duplicate coordinates averaged (avoids singular matrix, as ConcTour)."""
    acc = {}
    for d in included:
        k = (round(d['x'], 6), round(d['y'], 6))
        acc.setdefault(k, []).append(d['c'])
    x = np.array([k[0] for k in acc], float)
    y = np.array([k[1] for k in acc], float)
    z = np.array([float(np.mean(v)) for v in acc.values()], float)
    return x, y, z


# ---- kriging ----
def vgm(model, h, psill=1.0, rng=np.nan, nug=0.0):
    """Theoretical variogram (practical-range definition)."""
    h = np.asarray(h, float)
    if model == 'linear':
        g = nug + psill * h
    elif model == 'spherical':
        r = np.minimum(h / rng, 1.0)
        g = nug + psill * (1.5 * r - 0.5 * r ** 3)
    elif model == 'exponential':
        g = nug + psill * (1 - np.exp(-3 * h / rng))
    elif model == 'gaussian':
        g = nug + psill * (1 - np.exp(-3 * (h / rng) ** 2))
    else:
        raise ValueError(model)
    return np.where(h > 0, g, 0.0)


def _cdist(A, B):
    return np.sqrt(((A[:, None, :] - B[None, :, :]) ** 2).sum(-1))


def krige(x, y, z, qx, qy, model='linear', params=None, return_var=False, chunk=20000):
    """Ordinary kriging. Default linear, slope 1, nugget 0 (ConcTour/Surfer default).

    qx, qy: query points (same shape). Returns estimates (and relative kriging variance).
    """
    params = params or dict(psill=1.0, range=np.nan, nugget=0.0)
    P = np.c_[x, y]
    n = len(x)
    A = np.ones((n + 1, n + 1))
    A[:n, :n] = vgm(model, _cdist(P, P), params['psill'], params['range'], params['nugget'])
    A[n, n] = 0.0
    try:
        Ainv = np.linalg.inv(A)
    except np.linalg.LinAlgError:
        Ainv = np.linalg.pinv(A)
    Q = np.c_[np.ravel(qx), np.ravel(qy)]
    est = np.empty(len(Q)); var = np.empty(len(Q)) if return_var else None
    for s in range(0, len(Q), chunk):
        q = Q[s:s + chunk]
        B = np.ones((len(q), n + 1))
        B[:, :n] = vgm(model, _cdist(q, P), params['psill'], params['range'], params['nugget'])
        W = B @ Ainv.T
        est[s:s + chunk] = W[:, :n] @ z
        if return_var:
            var[s:s + chunk] = np.einsum('ij,ij->i', W, B)
    est = est.reshape(np.shape(qx))
    if return_var:
        return est, np.maximum(var, 0).reshape(np.shape(qx))
    return est


def grid_axes(Lx, Ly, g=GRID_N):
    """ConcTour grid: g cells on long side, short side by aspect (>= 10), whole field."""
    g = int(min(500, max(20, round(g))))
    if Lx >= Ly:
        nx, ny = g, max(10, round(g * Ly / Lx))
    else:
        ny, nx = g, max(10, round(g * Lx / Ly))
    return np.linspace(0, Lx, nx), np.linspace(0, Ly, ny)


def krige_grid(x, y, z, Lx, Ly, g=GRID_N, model='linear', params=None, return_var=False):
    gx, gy = grid_axes(Lx, Ly, g)
    GX, GY = np.meshgrid(gx, gy)
    r = krige(x, y, z, GX, GY, model, params, return_var)
    if return_var:
        Z, V = r
        return gx, gy, np.clip(Z, 0, None), V
    return gx, gy, np.clip(r, 0, None)   # no negatives


# -- advanced: variogram model comparison (check only, not default) --
def experimental_variogram(x, y, z, nlags=12):
    P = np.c_[x, y]
    D = _cdist(P, P)
    iu = np.triu_indices(len(x), 1)
    h = D[iu]; g = 0.5 * (z[iu[0]] - z[iu[1]]) ** 2
    edges = np.linspace(0, h.max() / 2, nlags + 1)
    idx = np.digitize(h, edges) - 1
    out = [(h[idx == k].mean(), g[idx == k].mean(), int((idx == k).sum()))
           for k in range(nlags) if (idx == k).sum() >= 5]
    if len(out) < 3:
        return None
    a = np.array(out)
    return a[:, 0], a[:, 1], a[:, 2].astype(int)


def fit_variogram(x, y, z, model, nug_ratio_max=0.25):
    from scipy.optimize import least_squares
    ev = experimental_variogram(x, y, z)
    if ev is None:
        return None
    hh, gg, _ = ev
    var = float(np.var(z, ddof=1))
    if model == 'linear':
        r = least_squares(lambda p: p[1] + p[0] * hh - gg,
                          [max(gg.max() / max(hh.max(), 1e-9), 1e-12), 0.0],
                          bounds=([0, 0], [np.inf, nug_ratio_max * var + 1e-12]))
        return dict(psill=float(r.x[0]), range=np.nan, nugget=float(r.x[1]))
    r = least_squares(lambda p: vgm(model, hh, p[0], p[1], p[2]) - gg,
                      [max(gg.max(), 1e-12), max(hh.max() / 2, 1e-9), 0.0],
                      bounds=([1e-12, max(hh.min(), 1e-9), 0], [np.inf, hh.max() * 3, nug_ratio_max * var + 1e-12]))
    return dict(psill=float(r.x[0]), range=float(r.x[1]), nugget=float(r.x[2]))


def spherical_range(x, y, z):
    """Fitted spherical range (interim-report method); None on failure."""
    p = fit_variogram(x, y, z, 'spherical')
    return None if p is None else p['range']


# ---- validation metrics ----
def loocv(x, y, z, model='linear', params=None):
    pred = np.empty(len(z))
    for i in range(len(z)):
        m = np.ones(len(z), bool); m[i] = False
        try:
            pred[i] = krige(x[m], y[m], z[m], np.array([x[i]]), np.array([y[i]]), model, params)[0]
        except Exception:
            pred[i] = np.nan
    return pred


ADD_POINTS_PCT = 20.0   # RRMSE or MAPE at or above this -> recommend adding points


def metrics(obs, pred, ids=None, top=3):
    """Leave-one-out accuracy: RRMSE and MAPE (headline), RMSE, MAE, the largest absolute errors.

    RRMSE = RMSE / mean(measured) x 100%: absolute misses count in full, so big misses around
            the hot zone show up.
    MAPE  = mean(|pred - obs| / obs) x 100% over obs > 0: typical relative error; a miss at the
            highest point weighs little, a miss at a low point weighs a lot.
    verdict: >= ADD_POINTS_PCT on either -> '建議補點', otherwise '視情況補充'.
    """
    obs = np.asarray(obs, float); pred = np.asarray(pred, float)
    ids = list(ids) if ids is not None else [str(i + 1) for i in range(len(obs))]
    ok = np.isfinite(pred)
    o, p = obs[ok], pred[ok]; ii = [i for i, k in zip(ids, ok) if k]
    e = p - o
    rmse = float(np.sqrt((e ** 2).mean())) if len(e) else float('nan')
    mae = float(np.abs(e).mean()) if len(e) else float('nan')
    rrmse = float(100 * rmse / o.mean()) if len(o) and o.mean() > 0 else float('nan')
    pos = o > 0
    mape = float(100 * np.mean(np.abs(e[pos]) / o[pos])) if pos.any() else float('nan')
    order = np.argsort(-np.abs(e))[:top]
    worst = [dict(point_id=ii[k], obs=float(o[k]), pred=float(p[k]), error=float(e[k]),
                  error_pct=float(100 * abs(e[k]) / o[k]) if o[k] > 0 else None) for k in order]
    finite = [v for v in (rrmse, mape) if math.isfinite(v)]
    verdict = ('建議補點' if finite and max(finite) >= ADD_POINTS_PCT else '視情況補充') if finite else ''
    return dict(RRMSE_pct=rrmse, MAPE_pct=mape, RMSE=rmse, MAE=mae, n=int(len(o)),
                largest_errors=worst, verdict=verdict, threshold_pct=ADD_POINTS_PCT)


def nnd(x, y):
    """Mean nearest-neighbour spacing (m)."""
    P = np.c_[x, y]
    D = _cdist(P, P); np.fill_diagonal(D, np.inf)
    return float(D.min(1).mean())


# ---- statistics ----
def stats(z, oel=None):
    """Same definitions as ConcTour, plus CV and skewness.

    GM/GSD from values > 0 only; noted when zeros present.
    """
    z = np.asarray(z, float); n = len(z)
    if n == 0:
        return {}
    pos = z[z > 0]
    sd = float(z.std(ddof=1)) if n > 1 else float('nan')
    mean = float(z.mean())
    s = dict(n=n, min=float(z.min()), max=float(z.max()), mean=mean, median=float(np.median(z)),
             sd=sd, cv_pct=100 * sd / mean if mean > 0 else float('nan'))
    if len(pos):
        lg = np.log(pos)
        s['gm'] = float(np.exp(lg.mean()))
        s['gsd'] = float(np.exp(lg.std(ddof=1))) if len(pos) > 1 else float('nan')
    s['n_zero'] = int((z == 0).sum())
    if n > 2 and sd > 0:
        s['skew'] = float((n / ((n - 1) * (n - 2))) * (((z - mean) / sd) ** 3).sum())
    if oel:
        s['n_over_oel'] = int((z > oel).sum())
    return s


def fmt(v, dec=None):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return '–'
    if dec is not None:
        return f'{v:.{dec}f}'
    a = abs(v)
    if a >= 1000:
        return f'{v:,.0f}'
    if a >= 100:
        return f'{v:.1f}'.rstrip('0').rstrip('.')
    if a >= 1:
        return f'{v:.2f}'.rstrip('0').rstrip('.')
    return f'{v:.2g}'


def nice_step(lo, hi, target=10):
    raw = (hi - lo) / target
    if raw <= 0:
        return 1.0
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return float(m * mag)
    return float(10 * mag)


def levels_for(lo, hi, target=10):
    step = nice_step(lo, hi, target)
    a = math.floor(lo / step) * step
    b = math.ceil(hi / step) * step
    if b <= a:
        b = a + step
    return np.arange(a, b + step * 0.5, step)


# ---- plan and obstacles ----
def load_json(path):
    if not path:
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_plan(path):
    """Read plan.json (from plan.py calibrate). dict or None."""
    cal = load_json(path)
    if cal and not os.path.isabs(cal['image']):
        cal['image'] = os.path.join(os.path.dirname(os.path.abspath(path)), cal['image'])
    return cal


def plan_image_cropped(cal):
    """Crop plan to field (origin bottom-left); returns image array and extent."""
    from PIL import Image
    im = Image.open(cal['image']).convert('RGBA')
    l, t, r, b = cal['px_box']
    im = im.crop((int(round(l)), int(round(t)), int(round(r)), int(round(b))))
    return np.asarray(im), (0, cal['field_x_m'], 0, cal['field_y_m'])


def load_layout(path):
    """Read layout.json (obstacles, predicted sources).

    {"obstacles": [{"name": "反應槽", "rect": [x0, y0, x1, y1]},
                   {"name": "牆角", "polygon": [[x, y], ...]}],
     "sources":   [{"name": "加料口", "type": "設備接口", "x": 3.2, "y": 5.1}]}
    Metres, origin bottom-left.
    """
    d = load_json(path) or {}
    obs = []
    for o in d.get('obstacles', []):
        if 'rect' in o:
            x0, y0, x1, y1 = o['rect']
            poly = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
        else:
            poly = o['polygon']
        obs.append(dict(name=o.get('name', '障礙區'), poly=np.asarray(poly, float)))
    return dict(obstacles=obs, sources=d.get('sources', []))


def in_obstacle(layout, px, py):
    """Boolean array: which points fall inside any obstacle."""
    from matplotlib.path import Path
    px = np.asarray(px, float); py = np.asarray(py, float)
    m = np.zeros(px.shape, bool)
    if not layout:
        return m
    pts = np.c_[px.ravel(), py.ravel()]
    for o in layout['obstacles']:
        m |= Path(o['poly']).contains_points(pts, radius=1e-9).reshape(px.shape)
    return m


CLEARANCE_M = 0.5      # every point keeps this distance from obstacle edges
COORD_STEP = 0.1       # coordinates are given to 0.1 m (what can be paced or taped on site)


def obstacle_distance(layout, px, py):
    """Distance (m) from each point to the nearest obstacle edge; 0 inside an obstacle; inf if none."""
    px = np.asarray(px, float); py = np.asarray(py, float)
    d = np.full(px.shape, np.inf)
    if not layout or not layout.get('obstacles'):
        return d
    for o in layout['obstacles']:
        P = o['poly']; Q = np.roll(P, -1, axis=0)
        for (x0, y0), (x1, y1) in zip(P, Q):
            dx, dy = x1 - x0, y1 - y0
            L2 = dx * dx + dy * dy or 1e-12
            t = np.clip(((px - x0) * dx + (py - y0) * dy) / L2, 0, 1)
            d = np.minimum(d, np.hypot(px - (x0 + t * dx), py - (y0 + t * dy)))
    d[in_obstacle(layout, px, py)] = 0.0
    return d


def distance_to_each(layout, x, y):
    """[(name, distance m)] from (x, y) to every obstacle edge (0 inside) and every source point."""
    out = []
    for o in (layout or {}).get('obstacles', []):
        d = float(obstacle_distance(dict(obstacles=[o]), np.array([x]), np.array([y]))[0])
        out.append((o['name'], d))
    for s in (layout or {}).get('sources', []):
        out.append((s.get('name', ''), float(math.hypot(float(s['x']) - x, float(s['y']) - y))))
    return out


def points_in_obstacles(layout, pts):
    """Measured points lying inside (or on the edge of) a confirmed obstacle.
    pts: dicts with point_id, x, y. Returns [dict(point_id, x, y, obstacle)]."""
    hits = []
    for p in pts:
        for name, d in distance_to_each(dict(obstacles=(layout or {}).get('obstacles', [])), p['x'], p['y']):
            if d <= 1e-9:
                hits.append(dict(point_id=p['point_id'], x=p['x'], y=p['y'], obstacle=name))
    return hits


def round_coord(v):
    return float(round(round(v / COORD_STEP) * COORD_STEP, 1))


def place_point(x, y, layout, Lx, Ly, clear=CLEARANCE_M, rmax=2.0):
    """Nearest spot on the 0.1 m lattice that is inside the field and >= clear from every
    obstacle edge, within rmax of (x, y). Returns (x, y, moved_m) or None if there is none."""
    k = max(1, int(math.ceil(rmax / COORD_STEP)) + 1)
    off = np.arange(-k, k + 1) * COORD_STEP
    OX, OY = np.meshgrid(off, off)
    cx = np.round(round_coord(x) + OX.ravel(), 1); cy = np.round(round_coord(y) + OY.ravel(), 1)
    mv = np.hypot(cx - x, cy - y)
    ok = (mv <= rmax + 1e-9) & (cx >= 0) & (cx <= Lx) & (cy >= 0) & (cy <= Ly)
    if layout and layout.get('obstacles'):
        ok &= obstacle_distance(layout, cx, cy) >= clear - 1e-9
    if not ok.any():
        return None
    i = int(np.argmin(np.where(ok, mv, np.inf)))
    return float(cx[i]), float(cy[i]), float(mv[i])


def save_json(obj, path):
    def conv(o):
        if isinstance(o, (np.floating,)):
            return None if not np.isfinite(o) else float(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, float) and not math.isfinite(o):
            return None
        raise TypeError(type(o))
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=conv)
