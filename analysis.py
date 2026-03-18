#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
소상공인 실태조사 2023 — 7섹션 음식점업 대시보드
실행: python3 analysis.py → index.html 갱신
필터: 산업대분류코드==I AND 산업중분류코드==56 (음식점업)
"""
import pandas as pd
import numpy as np
import json, os, re as _re

BASE = os.path.dirname(os.path.abspath(__file__))
CSV  = os.path.join(BASE, "DATA", "2023_연간자료_등록기반_20260316_40039.csv")
OUT  = os.path.join(BASE, "index.html")

# ── 1. 데이터 로드 ──────────────────────────────────────────────────────────
print("CSV 로드 중…")
df = pd.read_csv(CSV, encoding="euc-kr", low_memory=False)
print(f"  원본: {df.shape[0]:,}행 × {df.shape[1]}컬럼")

df = df[df["경영_매출금액"] <= 10_000].copy()   # 이상값 제거 (>100억)

# 음식점업 필터 (숙박·음식점업 I 중 음식점업 56)
rest = df[(df["산업대분류코드"] == "I") & (df["산업중분류코드"] == 56)].copy()
print(f"  음식점업(중분류56): {len(rest):,}행")

# 매출 > 0 인 행만 비용구조 분석에 사용
pos = rest[rest["경영_매출금액"] > 0].copy()

# ── 2. 파생 컬럼 ────────────────────────────────────────────────────────────
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

# 종사자규모 — pd.cut 벡터화 (경계값: 이하 기준 right=True)
pos["종사자규모"] = pd.cut(
    pos["일반_합계종사자수"].clip(upper=9),
    bins=[0, 1, 3, 9], labels=["1인", "2~3인", "4~9인"], right=True,
).astype(str)
SIZE_ORDER = ["1인", "2~3인", "4~9인"]

# 고용형태 — np.select 벡터화 (axis=1 apply 제거)
long_col  = "일반_근로계약기간_1년이상_종사자수"
short_col = "일반_근로계약기간_3개월미만_종사자수"
_lt = pos[long_col].fillna(0)
_st = pos[short_col].fillna(0)
pos["고용형태"] = np.select(
    [(_lt == 0) & (_st == 0), _lt >= _st],
    ["해당없음", "장기중심"],
    default="단기중심",
)
EMP_ORDER = ["장기중심", "단기중심", "해당없음"]

# 프랜차이즈
pos["프랜차이즈"] = pos["일반_프랜차이즈가맹점여부"].map({1: "프랜차이즈", 2: "독립"}).fillna("독립")
FRAN_ORDER = ["프랜차이즈", "독립"]

# 연령대 — 실제 코드값: 20,30,40,50,60,70,80
AGE_MAP = {30: "30대", 40: "40대", 50: "50대", 60: "60대", 70: "70대+"}
pos["연령대"] = pos["대표자연령대코드"].map(AGE_MAP)
AGE_ORDER = ["30대", "40대", "50대", "60대", "70대+"]

# 운영연수 — pd.cut 벡터화
pos["운영연수"] = (2023 - pos["일반_창업인수승계_연도"]).clip(lower=0)
pos["운영연수구간"] = pd.cut(
    pos["운영연수"],
    bins=[0, 2, 5, 10, 20, float("inf")],
    labels=["~2년", "3~5년", "6~10년", "11~20년", "21년+"],
    right=True,
)
TENURE_ORDER = ["~2년", "3~5년", "6~10년", "11~20년", "21년+"]

# 창업횟수 — pd.cut 벡터화
pos["창업횟수구간"] = pd.cut(
    pos["일반_창업횟수"],
    bins=[0, 1, 2, float("inf")],
    labels=["1회", "2회", "3회+"],
    right=True,
)
STARTUP_ORDER = ["1회", "2회", "3회+"]

# 지역 — np.select 벡터화
METRO_CODES  = {11, 23, 31}
MAJOR_CITIES = {21, 22, 24, 25, 26}
def region_label(code):
    """시도코드 → 지역 레이블 (시도별 집계에서 재사용)"""
    if pd.isna(code): return "기타"
    code = int(code)
    if code in METRO_CODES:  return "수도권"
    if code in MAJOR_CITIES: return "광역시"
    return "기타"
_codes = pos["행정구역시도코드"].fillna(-1).astype(int)
pos["지역"] = np.select(
    [_codes.isin(METRO_CODES), _codes.isin(MAJOR_CITIES)],
    ["수도권", "광역시"],
    default="기타",
)
REGION_ORDER = ["수도권", "광역시", "기타"]

# 매출구간 — pd.cut 벡터화 (경계값 하위 구간 포함, right=True)
pos["매출구간"] = pd.cut(
    pos["경영_매출금액"],
    bins=[0, 36, 72, 120, float("inf")],
    labels=["L1", "L2", "L3", "L4"],
    right=True,
).astype(str)
REV_ORDER  = ["L1", "L2", "L3", "L4"]
REV_LABELS = {"L1": "~3,600만", "L2": "3,600~7,200만", "L3": "7,200만~1.2억", "L4": "1.2억+"}

# ── 3. 공통 집계 함수 ────────────────────────────────────────────────────────
CLOSURE_COL    = "사업전환_운영계획코드"
CLOSURE_LABELS = {1: "계속운영", 2: "사업전환", 3: "폐업후취업", 4: "폐업·은퇴"}

HCOL_MAP = {
    f"경영_애로사항{i}코드": name
    for i, name in enumerate([
        "상권 쇠퇴", "동일업종 경쟁", "원재료비",
        "최저임금(인건비)", "보증금·월세", "부채상환",
        "인력관리", "판로개척(온라인)", "디지털 기술도입",
    ], start=1)
}
# 실제 존재하는 컬럼만 1회 필터링 (cnt_hard 내부 루프마다 체크 불필요)
HCOLS = {col: name for col, name in HCOL_MAP.items() if col in pos.columns}

def cnt_hard(sub):
    n = len(sub)
    if n == 0: return None
    cnt = {name: int((sub[col] == 1).sum()) for col, name in HCOLS.items()}
    ranked = sorted(cnt.items(), key=lambda x: -x[1])
    return {
        "labels": [r[0] for r in ranked],
        "rates":  [round(r[1] / n * 100, 1) for r in ranked],
        "counts": [r[1] for r in ranked],
    }

def seg_stats(sub, min_n=5):
    """서브셋 → 핵심 지표 딕셔너리. min_n 미만이면 수치 지표를 None으로 반환."""
    n = len(sub)
    empty = {
        "n": n, "weighted": 0, "profit_rate": None, "cost": None,
        "hardship": None, "closure_pct": None, "closure_dist": None,
        "revenue_median": None, "monthly_revenue": None,
        "monthly_profit": None, "neg_pct": None, "rent_rate": None,
    }
    if n < min_n:
        return empty

    weighted = int(round(sub["사업체수가중값"].sum()))

    closure_pct  = None
    closure_dist = None
    if CLOSURE_COL in sub.columns:
        closure_pct  = round(float(sub[CLOSURE_COL].isin([3, 4]).mean() * 100), 1)
        closure_dist = {
            lbl: round(float((sub[CLOSURE_COL] == code).sum() / n * 100), 1)
            for code, lbl in CLOSURE_LABELS.items()
        }

    cost            = {k: round(float(sub[k].median()), 1) for k in RLBLS}
    revenue_annual  = int(round(sub["경영_매출금액"].median() * 100))   # 만원/년
    monthly_revenue = int(round(revenue_annual / 12))                   # 만원/월
    monthly_profit  = int(round(float(sub["경영_영업이익"].median()) * 100 / 12))
    neg_pct         = round(float((sub["경영_영업이익"] < 0).mean() * 100), 1)
    rent_rate       = cost["임차료율"]  # 편의 단축키 (cost와 동일값)

    return {
        "n":               n,
        "weighted":        weighted,
        "profit_rate":     round(float(sub["영업이익률"].median()), 1),
        "cost":            cost,
        "hardship":        cnt_hard(sub),
        "closure_pct":     closure_pct,
        "closure_dist":    closure_dist,
        "revenue_median":  revenue_annual,
        "monthly_revenue": monthly_revenue,
        "monthly_profit":  monthly_profit,
        "neg_pct":         neg_pct,
        "rent_rate":       rent_rate,
    }

def group_stats(sub, col, order, min_n=5):
    return {key: seg_stats(sub[sub[col] == key], min_n=min_n) for key in order}

# ── 4. 섹션 1: 산업 개요 ────────────────────────────────────────────────────
print("\n섹션 1: 산업 개요 집계…")
overall = seg_stats(pos)
overall["total_rest_n"] = len(rest)

rev_dist = []
for k in REV_ORDER:
    s = pos[pos["매출구간"] == k]
    rev_dist.append({
        "key": k, "label": REV_LABELS[k],
        "n": len(s), "pct": round(len(s) / len(pos) * 100, 1),
        "weighted": int(round(s["사업체수가중값"].sum())),
    })

size_dist = []
for k in SIZE_ORDER:
    s = pos[pos["종사자규모"] == k]
    size_dist.append({
        "label": k, "n": len(s),
        "pct": round(len(s) / len(pos) * 100, 1),
        "weighted": int(round(s["사업체수가중값"].sum())),
    })

closure_dist_all = {}
if CLOSURE_COL in pos.columns:
    total_c = len(pos)
    for code, lbl in CLOSURE_LABELS.items():
        cnt = int((pos[CLOSURE_COL] == code).sum())
        closure_dist_all[lbl] = {"n": cnt, "pct": round(cnt / total_c * 100, 1)}

# 영업이익률 구간 분포
PR_DIST_BINS   = [-np.inf, 0, 10, 20, 30, 40, np.inf]
PR_DIST_LABELS = ["0% 미만", "0~10%", "10~20%", "20~30%", "30~40%", "40%+"]
pos["이익률구간"] = pd.cut(pos["영업이익률"], bins=PR_DIST_BINS, labels=PR_DIST_LABELS, right=True)
pr_dist = [
    {"label": lbl, "n": int((pos["이익률구간"] == lbl).sum()),
     "pct": round(float((pos["이익률구간"] == lbl).mean() * 100), 1),
     "weighted": int(round(pos.loc[pos["이익률구간"] == lbl, "사업체수가중값"].sum()))}
    for lbl in PR_DIST_LABELS
]

# 월 영업이익 구간 분포 (만원 = 백만원 × 100 ÷ 12)
pos["월영업이익_만원"] = pos["경영_영업이익"] * 100 / 12
MP_DIST_BINS   = [-np.inf, 0, 100, 200, 300, 500, np.inf]
MP_DIST_LABELS = ["0만 미만", "0~100만", "100~200만", "200~300만", "300~500만", "500만+"]
pos["월이익구간"] = pd.cut(pos["월영업이익_만원"], bins=MP_DIST_BINS, labels=MP_DIST_LABELS, right=True)
mp_dist = [
    {"label": lbl, "n": int((pos["월이익구간"] == lbl).sum()),
     "pct": round(float((pos["월이익구간"] == lbl).mean() * 100), 1),
     "weighted": int(round(pos.loc[pos["월이익구간"] == lbl, "사업체수가중값"].sum()))}
    for lbl in MP_DIST_LABELS
]

sec1 = {
    "overview":     overall,
    "rev_dist":     rev_dist,
    "pr_dist":      pr_dist,
    "mp_dist":      mp_dist,
    "size_dist":    size_dist,
    "closure_dist": closure_dist_all,
    "hardship":     cnt_hard(pos),
}

# ── 5. 섹션 2: 비용구조 ─────────────────────────────────────────────────────
print("섹션 2: 비용구조 집계…")

by_size_rev = {}
for sz in SIZE_ORDER:
    by_size_rev[sz] = {}
    sub_sz = pos[pos["종사자규모"] == sz]
    for rk in REV_ORDER:
        by_size_rev[sz][rk] = seg_stats(sub_sz[sub_sz["매출구간"] == rk])

sec2 = {
    "size_order":  SIZE_ORDER,
    "rev_order":   REV_ORDER,
    "rev_labels":  REV_LABELS,
    "by_size":     group_stats(pos, "종사자규모", SIZE_ORDER),
    "by_revenue":  {k: {"label": REV_LABELS[k], **seg_stats(pos[pos["매출구간"] == k])} for k in REV_ORDER},
    "by_size_rev": by_size_rev,
}

# ── 6. 섹션 3: 규모×고용형태 ────────────────────────────────────────────────
print("섹션 3: 규모×고용형태 집계…")

cells_se = {}
for sz in SIZE_ORDER:
    for em in EMP_ORDER:
        cells_se[f"{sz}x{em}"] = seg_stats(pos[(pos["종사자규모"] == sz) & (pos["고용형태"] == em)])

sec3 = {
    "size_order": SIZE_ORDER,
    "emp_order":  EMP_ORDER,
    "by_size":    group_stats(pos, "종사자규모", SIZE_ORDER),
    "by_emp":     group_stats(pos, "고용형태",   EMP_ORDER),
    "cells":      cells_se,
}

# ── 7. 섹션 4: 프랜차이즈×고용형태 ─────────────────────────────────────────
print("섹션 4: 프랜차이즈×고용형태 집계…")

cells_fe = {}
for fr in FRAN_ORDER:
    for em in EMP_ORDER:
        cells_fe[f"{fr}x{em}"] = seg_stats(
            pos[(pos["프랜차이즈"] == fr) & (pos["고용형태"] == em)],
            min_n=15,   # n<15 셀은 수치 None 처리 (신뢰도 부족)
        )

sec4 = {
    "fran_order": FRAN_ORDER,
    "emp_order":  EMP_ORDER,
    "by_fran":    group_stats(pos, "프랜차이즈", FRAN_ORDER),
    "by_emp":     group_stats(pos, "고용형태",   EMP_ORDER),
    "cells":      cells_fe,
}

# ── 8. 섹션 5: 연령대 ───────────────────────────────────────────────────────
print("섹션 5: 연령대 집계…")

age_valid = [a for a in AGE_ORDER if (pos["연령대"] == a).sum() >= 5]
by_age    = group_stats(pos, "연령대", age_valid)

# 디지털/배달 추가 지표 (연령대별)
for age in age_valid:
    sub_age = pos[pos["연령대"] == age]
    extra = {}
    # 배달앱·온라인 매출 실적
    dcol = "경영_전자상거래_매출실적여부"
    if dcol in sub_age.columns:
        extra["delivery_pct"] = round(float((sub_age[dcol] == 1).mean() * 100), 1)
    # 디지털 기술 도입 의향 (1=있음)
    icol = "경영_운영활동_디지털기술유형도입의향여부"
    if icol in sub_age.columns:
        extra["digital_intent"] = round(float((sub_age[icol] == 1).mean() * 100), 1)
    # 디지털 도입 없음 (디지털대응8코드==1: 활동사항 없음)
    ncol = "경영_운영활동_디지털대응8코드"
    if ncol in sub_age.columns:
        extra["digital_none"] = round(float((sub_age[ncol] == 1).mean() * 100), 1)
    by_age[age].update(extra)

sec5 = {"age_order": age_valid, "by_age": by_age}

# ── 9. 섹션 6: 창업경험×운영연수 ────────────────────────────────────────────
print("섹션 6: 창업경험×운영연수 집계…")

cells_st = {}
for su in STARTUP_ORDER:
    for te in TENURE_ORDER:
        cells_st[f"{su}x{te}"] = seg_stats(
            pos[(pos["창업횟수구간"] == su) & (pos["운영연수구간"] == te)]
        )

# 운영연수구간 × 고용형태 교차 집계 (min_n=10)
tenure_emp_cells = {}
for te in TENURE_ORDER:
    for em in EMP_ORDER:
        tenure_emp_cells[f"{te}x{em}"] = seg_stats(
            pos[(pos["운영연수구간"] == te) & (pos["고용형태"] == em)],
            min_n=10,
        )

sec6 = {
    "startup_order":      STARTUP_ORDER,
    "tenure_order":       TENURE_ORDER,
    "emp_order":          EMP_ORDER,
    "by_startup":         group_stats(pos, "창업횟수구간", STARTUP_ORDER),
    "by_tenure":          group_stats(pos, "운영연수구간", TENURE_ORDER),
    "cells":              cells_st,
    "tenure_emp_cells":   tenure_emp_cells,
}

# ── 10. 섹션 7: 지역분석 ────────────────────────────────────────────────────
print("섹션 7: 지역 집계…")

# 시도별 집계 (n<20 제외)
CITY_MAP = {
    11: "서울", 21: "부산", 22: "대구", 23: "인천",
    24: "광주", 25: "대전", 26: "울산", 29: "세종",
    31: "경기", 32: "강원", 33: "충북", 34: "충남",
    35: "전북", 36: "전남", 37: "경북", 38: "경남", 39: "제주",
}

by_city    = {}
city_order = []
code_col   = pos["행정구역시도코드"].fillna(-1).astype(int)
for code in sorted(CITY_MAP):
    city = CITY_MAP[code]
    sub  = pos[code_col == code]
    stats = seg_stats(sub, min_n=20)
    if stats["profit_rate"] is not None:   # n >= 20 통과
        stats["is_metro"]    = code in METRO_CODES
        stats["region_type"] = region_label(code)
        by_city[city]        = stats
        city_order.append(city)

sec7 = {
    "region_order": REGION_ORDER,
    "by_region":    group_stats(pos, "지역", REGION_ORDER),
    "city_order":   city_order,
    "by_city":      by_city,
}

# ── 11. 요약 출력 ────────────────────────────────────────────────────────────
print(f"\n전체 표본: {len(pos):,}행")
print("\n연령대별 영업이익률 중앙값:")
for age in age_valid:
    s  = sec5["by_age"][age]
    pr = f"{s['profit_rate']:+.1f}%" if s["profit_rate"] is not None else "N/A"
    print(f"  {age}: {pr}  (n={s['n']})")

print("\n종사자규모별 영업이익률 중앙값:")
for sz in SIZE_ORDER:
    s  = sec2["by_size"][sz]
    pr = f"{s['profit_rate']:+.1f}%" if s["profit_rate"] is not None else "N/A"
    print(f"  {sz}: {pr}  (n={s['n']})")

print("\n지역별 영업이익률 중앙값:")
for rg in REGION_ORDER:
    s  = sec7["by_region"][rg]
    pr = f"{s['profit_rate']:+.1f}%" if s["profit_rate"] is not None else "N/A"
    print(f"  {rg}: {pr}  (n={s['n']})")

# ── 12. JSON 직렬화 ──────────────────────────────────────────────────────────
DATA_JSON = json.dumps({
    "sec1": sec1, "sec2": sec2, "sec3": sec3, "sec4": sec4,
    "sec5": sec5, "sec6": sec6, "sec7": sec7,
}, ensure_ascii=False)

# ── 13. index.html에 데이터 주입 ────────────────────────────────────────────
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
