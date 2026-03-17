#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
소상공인 실태조사 2023 — 16세그먼트 대시보드
실행: python3 analysis.py → index.html 생성
세그먼트: 종사자 S1~S4 × 매출 L1~L4 (단위: 백만원)
"""
import pandas as pd
import numpy as np
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
CSV  = os.path.join(BASE, "DATA", "2023_연간자료_등록기반_20260316_40039.csv")
OUT  = os.path.join(BASE, "index.html")

# ── 1. 데이터 로드 ─────────────────────────────────────────────────────────────
print("CSV 로드 중…")
df = pd.read_csv(CSV, encoding="euc-kr", low_memory=False)
print(f"  원본: {df.shape[0]:,}행 × {df.shape[1]}컬럼")

df   = df[df["경영_매출금액"] <= 10_000].copy()   # 이상값 제거 (>100억)
food = df[df["산업대분류코드"] == "I"].copy()       # 요식업 필터
print(f"  요식업: {len(food):,}행")

# ── 2. 전처리 ──────────────────────────────────────────────────────────────────
pos = food[food["경영_매출금액"] > 0].copy()

RATIOS = {
    "원가율":     "경영_영업비용_매출원가",
    "인건비율":   "경영_영업비용_급여총액",
    "임차료율":   "경영_영업비용_임차료",
    "기타비용율": "경영_영업비용_기타금액",
    "영업이익률": "경영_영업이익",
}
for lbl, col in RATIOS.items():
    pos[lbl] = (pos[col] / pos["경영_매출금액"] * 100).round(2)
RLBLS = list(RATIOS.keys())

# ── 3. 애로사항 집계 ───────────────────────────────────────────────────────────
# 각 컬럼이 1/NaN 플래그 구조 → 컬럼별 1의 개수 카운트
# "기타" 제외 9개 항목만 사용
HCOL_MAP = {
    f"경영_애로사항{i}코드": name
    for i, name in enumerate([
        "상권 쇠퇴", "동일업종 경쟁", "원재료비",
        "최저임금(인건비)", "보증금·월세", "부채상환",
        "인력관리", "판로개척(온라인)", "디지털 기술도입",
    ], start=1)
}

def cnt_hard(sub):
    """9개 항목 전체를 비율(%)로 반환. 원본 건수(counts)도 함께 저장."""
    n = len(sub)
    cnt = {
        name: int((sub[col] == 1).sum())
        for col, name in HCOL_MAP.items()
        if col in sub.columns
    }
    ranked = sorted(cnt.items(), key=lambda x: -x[1])   # 비율 내림차순
    return {
        "labels": [r[0] for r in ranked],
        "rates":  [round(r[1] / n * 100, 1) for r in ranked],
        "counts": [r[1] for r in ranked],
    }

# ── 4. 세그먼트 정의 ───────────────────────────────────────────────────────────
def wfilt(lo, hi=None):
    """종사자 수 필터"""
    if hi is None:
        return lambda df: df["일반_합계종사자수"] >= lo
    if lo == hi:
        return lambda df: df["일반_합계종사자수"] == lo
    return lambda df: df["일반_합계종사자수"].between(lo, hi)

def lfilt(lo=None, hi=None):
    """매출 구간 필터 (단위: 백만원, lo 포함 hi 미포함)"""
    if lo is None:
        return lambda df: df["경영_매출금액"] < hi
    if hi is None:
        return lambda df: df["경영_매출금액"] >= lo
    return lambda df: (df["경영_매출금액"] >= lo) & (df["경영_매출금액"] < hi)

# (key, 필터함수, 표시 레이블)
WDEF = [
    ("S1", wfilt(1, 1),   "1명"),
    ("S2", wfilt(2, 3),   "2~3명"),
    ("S3", wfilt(4, 9),   "4~9명"),
    ("S4", wfilt(10),     "10명+"),
]
LDEF = [
    ("L4", lfilt(120),       "1.2억+"),
    ("L3", lfilt(72,  120),  "7,200만~1.2억"),
    ("L2", lfilt(36,  72),   "3,600만~7,200만"),
    ("L1", lfilt(hi=36),     "~3,600만"),
]

# ── 5. 16세그먼트 계산 ─────────────────────────────────────────────────────────
MIN_N = 5  # 통계적으로 의미 있는 최소 표본 수

segs = {}
for wk, wfn, _ in WDEF:
    for lk, lfn, _ in LDEF:
        key = f"{wk}x{lk}"
        sub = pos[wfn(pos) & lfn(pos)]
        n   = len(sub)

        if n < MIN_N:
            segs[key] = {
                "n": n, "weighted": 0, "profit_rate": None,
                "cost": None, "hardship": None, "closure_pct": None, "매출중앙": None,
            }
            continue

        closure_col = "사업전환_운영계획코드"
        closure_pct = (
            round(float(sub[closure_col].isin([3, 4]).mean() * 100), 1)
            if closure_col in sub.columns else None
        )

        segs[key] = {
            "n":           n,
            "weighted":    int(round(sub["사업체수가중값"].sum())),
            "profit_rate": round(float(sub["영업이익률"].median()), 1),
            "cost":        {k: round(float(sub[k].median()), 1) for k in RLBLS},
            "hardship":    cnt_hard(sub),
            "closure_pct": closure_pct,
            "매출중앙":    int(sub["경영_매출금액"].median()),
        }

# 결과 요약 출력
print("\n16세그먼트 요약 (영업이익률 중앙값):")
header = "       " + "  ".join(f"{wk:>12}" for wk, *_ in WDEF)
print(header)
for lk, _, llbl in LDEF:
    row = f"{lk}({llbl[:6]})"
    for wk, *_ in WDEF:
        s  = segs[f"{wk}x{lk}"]
        pr = f"{s['profit_rate']:+.1f}%  n={s['n']}" if s["profit_rate"] is not None else "  N/A      "
        row += f"  {pr:>12}"
    print(row)

# ── 6. JSON 직렬화 ─────────────────────────────────────────────────────────────
DATA_JSON = json.dumps({
    "grid": {
        "workers":       [w for w, *_ in WDEF],
        "worker_labels": {w: l for w, _, l in WDEF},
        "levels":        [l for l, *_ in LDEF],
        "level_labels":  {l: lbl for l, _, lbl in LDEF},
        "segments":      segs,
    }
}, ensure_ascii=False)

# ── 7. index.html에 데이터 주입 ────────────────────────────────────────────────
# index.html의 UI 코드는 그대로 유지하고 `const D = {...};` 라인만 교체한다.
import re as _re

with open(OUT, encoding="utf-8") as f:
    html = f.read()

html = _re.sub(
    r"const D = \{.*?\};",
    f"const D = {DATA_JSON};",
    html,
    flags=_re.DOTALL,
)

with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)

print(f"\n완료: {OUT}")
