# -*- coding: utf-8 -*-
"""Reference-point drift check (Q3), thresholds as in the technical manual v5, chapter 8.5.

When points cannot be measured simultaneously, read one fixed reference point
before, during and after, to judge whether the concentration changed during the survey.
logs_to_points.py walk calls judge() automatically for every point that appears more than
once in the point measurement time table.

Usage:
  python drift.py --readings BEFORE MID AFTER [--times T1 T2 T3] [--accept 10] [--retest 30]

Verdict:
  drift (%) = (max - min) / mean x 100%
  <= 10%      : acceptable, treat all points as one period
  10% .. 30%  : record in the note (備註), interpret relative highs and lows
  > 30%       : re-measure, shorten the total measuring time, or measure in separate periods
"""
import argparse

ACCEPT = 10.0   # % : at or below -> acceptable
RETEST = 30.0   # % : above -> re-measure

VERDICT_ZH = {
    'ok': '可接受，全部測點視為同一時段',
    'note': '記錄於備註，判讀時以相對高低為主',
    'retest': '建議重新量測、縮短總量測時間，或分時段量測',
}


def judge(readings, accept=ACCEPT, retest=RETEST):
    """Return drift %, first-to-last change, level (ok/note/retest) and the Chinese verdict."""
    lo, hi = min(readings), max(readings)
    mean = sum(readings) / len(readings)
    rate = (hi - lo) / mean * 100 if mean else float('nan')
    trend = readings[-1] - readings[0]
    if rate <= accept:
        level = 'ok'
    elif rate <= retest:
        level = 'note'
    else:
        level = 'retest'
    return dict(rate_pct=rate, trend=trend, level=level, verdict=VERDICT_ZH[level])


def remark_text(readings, times=(), point='固定參考點', accept=ACCEPT, retest=RETEST):
    """One sentence for the note / remark, in Chinese."""
    r = judge(readings, accept, retest)
    seq = '、'.join(f'{t} {v:.4g}' if t else f'{v:.4g}' for t, v in
                   zip(list(times) + [''] * len(readings), readings))
    return f'{point}重複量測 {len(readings)} 次：{seq}；漂移 {r["rate_pct"]:.1f}%，{r["verdict"]}', r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--readings', type=float, nargs='+', required=True, help='reference readings in time order')
    ap.add_argument('--times', nargs='*', default=[])
    ap.add_argument('--accept', type=float, default=ACCEPT, help='acceptable up to this drift %% (default 10)')
    ap.add_argument('--retest', type=float, default=RETEST, help='re-measure above this drift %% (default 30)')
    a = ap.parse_args()
    if len(a.readings) < 2:
        raise SystemExit('need at least two readings (before and after)')
    text, r = remark_text(a.readings, a.times, accept=a.accept, retest=a.retest)
    print(f'Drift {r["rate_pct"]:.1f}% (acceptable <= {a.accept:g}%, re-measure > {a.retest:g}%), '
          f'first-to-last change {r["trend"]:+.4g}')
    print(f'Verdict: {r["level"]}')
    print(f'Suggested remark (paste as is): {text}')


if __name__ == '__main__':
    main()
