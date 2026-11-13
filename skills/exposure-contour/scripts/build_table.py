# -*- coding: utf-8 -*-
"""Standard tables (xlsx, single sheet, row 1 field codes, row 2 Chinese labels, data from row 3).

1. Standard data table v5.0 (D1, D7): basic info in A-D, points in F-L. Same format as
   ConcTour import/export. Origin bottom-left, metres; one pollutant per file.
   embed_image() puts the layout map below the basic-info block, proportionally scaled.
2. Point measurement time table v1.0 (one instrument walked point to point):
   point_id, x_m, y_m, start_time, end_time, duration_min, note.
3. Instrument-point mapping table v1.0 (several instruments at once):
   instrument_id, point_id, x_m, y_m, note.
Sheet labels stay in Chinese (user-facing).

Usage:
  python build_table.py --blank --out blank.xlsx
  python build_table.py --meta meta.json --points points.csv --out table.xlsx
  python build_table.py --kind time --points points.csv [--minutes USER_GIVEN] --out 點位量測時間表.xlsx
  python build_table.py --kind instrument --points points.csv --out 儀器點位對應表.xlsx
  python build_table.py --embed 標準資料表.xlsx --image 佈點圖.png [--title TEXT]
"""
import argparse, csv, json, sys
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

F = 'Arial'
H1 = PatternFill('solid', fgColor='1F4E79')
H2 = PatternFill('solid', fgColor='DDEBF7')
IN = PatternFill('solid', fgColor='FFF2CC')
OPT = PatternFill('solid', fgColor='F2F2F2')
_t = Side(style='thin', color='BFBFBF')
B = Border(left=_t, right=_t, top=_t, bottom=_t)

SHEET = '基本資料與量測濃度'
# (field_code, Chinese label, unit, required)
META = [
    ('site_name',   '場域名稱',        '',        True),
    ('survey_date', '量測日期',        'YYYY-MM-DD', True),
    ('field_x_m',   '場域 X 方向長度',  'm',       True),
    ('field_y_m',   '場域 Y 方向長度',  'm',       True),
    ('c_name',      '污染物名稱',      '',        True),
    ('c_unit',      '污染物單位',      '',        True),
    ('c_LOD',       '儀器偵測極限',    '同上單位', False),
]
REMARK_ROWS = 7                      # rows of merged remark cell
# (code, default Chinese label, width, required)
PT_COLS = [
    ('point_id', '測點編號', 14, True),
    ('x_m',      'X 座標',   11, True),
    ('y_m',      'Y 座標',   11, True),
    ('c1',       '量測1',    15, True),
    ('c2',       '量測2',    15, False),
    ('c3',       '量測n',    15, False),
    ('note',     '備註',     38, False),
]
PT_C0 = 6                            # first column of point block (F)


def build(meta=None, points=None, out='標準資料表.xlsx', labels=None, blank_rows=300):
    meta = dict(meta or {})
    points = points or []
    labels = labels or {}
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET

    # -- header: row 1 codes, row 2 Chinese labels --
    left = [('field_code', '欄位代碼', 18), ('field_name', '欄位名稱', 22),
            ('value', '填寫內容', 30), ('unit', '單位', 14)]
    for i, (code, zh, w) in enumerate(left, 1):
        a = ws.cell(1, i, code); b = ws.cell(2, i, zh)
        a.font = Font(F, bold=True, size=9, color='FFFFFF'); a.fill = H1
        a.alignment = Alignment('center', 'center'); a.border = B
        b.font = Font(F, bold=True, size=10, color='1F4E79'); b.fill = H2
        b.alignment = Alignment('center', 'center'); b.border = B
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.column_dimensions['E'].width = 3          # spacer

    for j, (code, zh, w, req) in enumerate(PT_COLS):
        i = PT_C0 + j
        a = ws.cell(1, i, code); b = ws.cell(2, i, labels.get(code, zh))
        a.font = Font(F, bold=True, size=9, color='FFFFFF'); a.fill = H1
        a.alignment = Alignment('center', 'center'); a.border = B
        b.font = Font(F, bold=True, size=10, color='1F4E79'); b.fill = H2
        b.alignment = Alignment('center', 'center'); b.border = B
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 15
    ws.row_dimensions[2].height = 22

    # -- left: metadata --
    r = 3
    for code, zh, unit, req in META:
        ws.cell(r, 1, code).font = Font(F, size=9, color='808080')
        ws.cell(r, 1).alignment = Alignment('center', 'center')
        ws.cell(r, 2, zh).font = Font(F, size=10)
        v = ws.cell(r, 3, meta.get(code))
        v.fill = IN if req else OPT; v.font = Font(F, size=10)
        ws.cell(r, 4, unit).font = Font(F, size=9, color='808080')
        ws.cell(r, 4).alignment = Alignment('center', 'center')
        for cc in range(1, 5):
            ws.cell(r, cc).border = B
        ws.row_dimensions[r].height = 19
        r += 1
    # merged remark cell
    ws.cell(r, 1, 'remark').font = Font(F, size=9, color='808080')
    ws.cell(r, 1).alignment = Alignment('center', 'top')
    ws.cell(r, 2, '備註').font = Font(F, size=10)
    ws.cell(r, 2).alignment = Alignment('left', 'top')
    ws.merge_cells(start_row=r, start_column=3, end_row=r + REMARK_ROWS - 1, end_column=4)
    x = ws.cell(r, 3, meta.get('remark'))
    x.fill = OPT; x.font = Font(F, size=10)
    x.alignment = Alignment('left', 'top', wrap_text=True)
    for rr in range(r, r + REMARK_ROWS):
        for cc in range(1, 5):
            ws.cell(rr, cc).border = B
        ws.row_dimensions[rr].height = 19

    # -- right: points --
    n = max(len(points) + 20, blank_rows)
    for i, p in enumerate(points):
        for j, (code, _zh, _w, _req) in enumerate(PT_COLS):
            val = p.get(code)
            if val in ('', None):
                val = None
            elif code in ('x_m', 'y_m', 'c1', 'c2', 'c3'):
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    pass
            ws.cell(3 + i, PT_C0 + j, val)
    for rr in range(3, 3 + n):
        for j, (code, _zh, _w, req) in enumerate(PT_COLS):
            c = ws.cell(rr, PT_C0 + j)
            c.border = B; c.font = Font(F, size=10)
            c.fill = IN if req else OPT
            c.alignment = Alignment('center' if code != 'note' else 'left', 'center')

    ws.freeze_panes = 'A3'
    ws.sheet_view.showGridLines = False
    wb.save(out)
    return out


def embed_image(xlsx, png, title='', max_h_px=None):
    """Put an image (layout map) below the basic-info block in columns A-D without covering text.

    Starts two rows below the last used row / merged range in A-D (the remark cell is merged over
    several rows). Scaled proportionally: one factor for width and height = min(90% of the A-D
    width / image width, max_h_px / image height); aspect ratio locked so it stays proportional
    if resized in Excel. Point data (F onward) is never covered.
    """
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.drawing.spreadsheet_drawing import OneCellAnchor, AnchorMarker
    from openpyxl.drawing.xdr import XDRPositiveSize2D
    from openpyxl.drawing.picture import PictureFrame, PictureLocking
    from openpyxl.drawing.fill import Blip
    from openpyxl.drawing.geometry import PresetGeometry2D
    from openpyxl.utils.units import pixels_to_EMU
    wb = openpyxl.load_workbook(xlsx); ws = wb.worksheets[0]
    last = 0
    for r in range(1, ws.max_row + 1):
        if any(ws.cell(r, k).value not in (None, '') for k in range(1, 5)):
            last = r
    for m in ws.merged_cells.ranges:
        if m.min_col <= 4:
            last = max(last, m.max_row)
    tr = last + 2
    if title:
        ws.merge_cells(start_row=tr, start_column=1, end_row=tr, end_column=4)
        ws.cell(tr, 1, title).font = Font(F, bold=True, size=11)
        ws.cell(tr, 1).alignment = Alignment('left', 'center', wrap_text=True)
        ws.row_dimensions[tr].height = 32
        tr += 1
    max_w = 0.9 * sum((ws.column_dimensions[get_column_letter(k)].width or 8.43) * 7 + 5 for k in range(1, 5))
    img = XLImage(png); w0, h0 = img.width, img.height
    f = min(max_w / w0, (max_h_px / h0) if max_h_px else 1e9)
    w, h = round(w0 * f), round(h0 * f)
    pic = PictureFrame()
    pic.nvPicPr.cNvPr.id = 1; pic.nvPicPr.cNvPr.name = pic.nvPicPr.cNvPr.descr = '佈點圖'
    pic.nvPicPr.cNvPicPr.picLocks = PictureLocking(noChangeAspect=True)
    pic.blipFill.blip = Blip(); pic.blipFill.blip.embed = 'rId1'
    pic.spPr.prstGeom = PresetGeometry2D(prst='rect'); pic.spPr.ln = None
    an = OneCellAnchor(_from=AnchorMarker(col=0, row=tr - 1),
                       ext=XDRPositiveSize2D(pixels_to_EMU(w), pixels_to_EMU(h)))
    an.pic = pic
    img.anchor = an; img.width, img.height = w, h
    ws.add_image(img)
    wb.save(xlsx)
    return dict(row=tr, width_px=w, height_px=h)


# ---- simple standard tables (time table, instrument mapping) ----
TIME_SHEET = '點位量測時間表'
TIME_COLS = [            # (code, Chinese label, width, required)
    ('point_id',     '點位編號',       12, True),
    ('x_m',          'X 座標 (m)',     11, True),
    ('y_m',          'Y 座標 (m)',     11, True),
    ('start_time',   '開始時間',       20, True),
    ('end_time',     '結束時間',       20, False),
    ('duration_min', '測量時長 (分鐘)', 15, False),
    ('note',         '備註',           36, False),
]
INST_SHEET = '儀器點位對應表'
INST_COLS = [
    ('instrument_id', '儀器編號',   16, True),
    ('point_id',      '點位編號',   12, True),
    ('x_m',           'X 座標 (m)', 11, True),
    ('y_m',           'Y 座標 (m)', 11, True),
    ('note',          '備註',       36, False),
]
TABLE_NOTES = {
    'time': ['填寫說明：一台儀器逐點量測時使用。每點填開始時間；結束時間與測量時長擇一填寫即可',
             '（兩者都填時以結束時間為準）。時間可寫 09:00:00 或 2026-11-11 09:00:00；只寫時刻時，日期取儀器紀錄的日期。',
             '代表濃度＝儀器紀錄中 [開始時間, 結束時間) 或 [開始時間, 開始時間＋測量時長) 內讀值的平均。',
             '同一點在不同時間重複量測（如固定參考點於量測前、中、後）時，每次各填一列；Skill 會自動計算漂移並寫入備註',
             '（10% 以下可接受；10%–30% 記錄於備註，判讀以相對高低為主；超過 30% 建議重新量測）。'],
    'instrument': ['填寫說明：多台儀器同時量測時使用。每台儀器一列，儀器編號須與儀器紀錄檔的欄名完全相同；',
                   '點位編號與座標對應標準資料表。沒有放置儀器的點位不必列出。'],
}


def build_simple(kind, points=None, out=None, minutes=None, blank_rows=200, meta=None):
    """Write the point measurement time table (kind='time') or the instrument-point mapping
    table (kind='instrument'), pre-filled from points (point_id, x_m/x, y_m/y)."""
    cols, sheet = (TIME_COLS, TIME_SHEET) if kind == 'time' else (INST_COLS, INST_SHEET)
    out = out or f'{sheet}.xlsx'
    points = points or []
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = sheet
    for j, (code, zh, w, req) in enumerate(cols, 1):
        a = ws.cell(1, j, code); b = ws.cell(2, j, zh)
        a.font = Font(F, bold=True, size=9, color='FFFFFF'); a.fill = H1
        a.alignment = Alignment('center', 'center'); a.border = B
        b.font = Font(F, bold=True, size=10, color='1F4E79'); b.fill = H2
        b.alignment = Alignment('center', 'center', wrap_text=True); b.border = B
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.row_dimensions[1].height = 15; ws.row_dimensions[2].height = 30
    n = max(len(points) + 10, blank_rows)
    for i in range(n):
        p = points[i] if i < len(points) else {}
        for j, (code, _zh, _w, req) in enumerate(cols, 1):
            v = p.get(code)
            if v in (None, '') and code in ('x_m', 'y_m'):
                v = p.get(code[0])
            if v in (None, '') and code == 'duration_min' and minutes and i < len(points):
                v = minutes
            if code in ('x_m', 'y_m', 'duration_min') and v not in (None, ''):
                try:
                    v = round(float(v), 1) if code != 'duration_min' else float(v)
                except (TypeError, ValueError):
                    pass
            c = ws.cell(3 + i, j, None if v == '' else v)
            c.border = B; c.font = Font(F, size=10); c.fill = IN if req else OPT
            c.alignment = Alignment('left' if code == 'note' else 'center', 'center')
            if code in ('start_time', 'end_time'):
                c.number_format = 'hh:mm:ss'
    # instructions to the right
    c0 = len(cols) + 2
    ws.column_dimensions[get_column_letter(c0)].width = 70
    for k, line in enumerate(TABLE_NOTES[kind]):
        cell = ws.cell(1 + k, c0, line); cell.font = Font(F, size=9, color='595959')
    if meta and meta.get('site_name'):
        ws.cell(len(TABLE_NOTES[kind]) + 2, c0, f"場域：{meta.get('site_name')}　污染物：{meta.get('c_name', '')}"
                f"（{meta.get('c_unit', '')}）").font = Font(F, size=9, color='595959')
    ws.freeze_panes = 'A3'; ws.sheet_view.showGridLines = False
    wb.save(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--blank', action='store_true')
    ap.add_argument('--meta')
    ap.add_argument('--points')
    ap.add_argument('--labels', help='JSON overriding c1/c2/c3 labels, e.g. {"c1":"量測1_0826"}')
    ap.add_argument('--out')
    ap.add_argument('--kind', choices=['data', 'time', 'instrument'], default='data',
                    help='data = standard data table v5.0; time = point measurement time table; '
                         'instrument = instrument-point mapping table')
    ap.add_argument('--minutes', type=float, help='time table: pre-fill duration_min')
    ap.add_argument('--embed', help='existing standard table to embed an image into')
    ap.add_argument('--image'); ap.add_argument('--title', default='')
    a = ap.parse_args()
    if a.embed:
        r = embed_image(a.embed, a.image, a.title)
        print(f"Embedded {a.image} into {a.embed} at row {r['row']} ({r['width_px']} x {r['height_px']} px)")
        return
    if a.kind != 'data':
        pts = []
        if a.points and not a.blank:
            with open(a.points, encoding='utf-8-sig', newline='') as f:
                pts = list(csv.DictReader(f))
        out = build_simple(a.kind, pts, a.out, a.minutes)
        print(f'Wrote {out} ({len(pts)} points)')
        return
    if not a.out:
        raise SystemExit('--out is required')

    meta, points, labels = {}, [], {}
    if a.labels:
        labels = json.loads(a.labels)
    if not a.blank:
        if a.meta:
            with open(a.meta, encoding='utf-8') as f:
                meta = json.load(f)
        if a.points:
            with open(a.points, encoding='utf-8-sig', newline='') as f:
                points = list(csv.DictReader(f))
        if not points:
            print('warning: no points given, writing a blank template', file=sys.stderr)

    build(meta, points, a.out, labels)
    print(f'Wrote {a.out} ({len(points)} points)')


if __name__ == '__main__':
    main()
