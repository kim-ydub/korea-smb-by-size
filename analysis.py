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
HCOL_MAP = {
    f"경영_애로사항{i}코드": name
    for i, name in enumerate([
        "상권 쇠퇴", "동일업종 경쟁", "원재료비",
        "최저임금(인건비)", "보증금·월세", "부채상환",
        "인력관리", "판로개척(온라인)", "디지털 기술도입", "기타",
    ], start=1)
}

def cnt_hard(sub, n=5):
    cnt = {
        name: int((sub[col] == 1).sum())
        for col, name in HCOL_MAP.items()
        if col in sub.columns
    }
    ranked = sorted(cnt.items(), key=lambda x: -x[1])[:n]
    return {"labels": [r[0] for r in ranked], "values": [r[1] for r in ranked]}

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
            "hardship":    cnt_hard(sub, 5),
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

# ── 7. HTML 생성 ───────────────────────────────────────────────────────────────
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>2023 소상공인 대시보드 — 16세그먼트</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {
  --green-1:#1e261b; --green-2:#3a5630; --green-3:#587638;
  --green-4:#95a961; --green-5:#edf3a9;
  --neutral-900:#1a1a18; --neutral-700:#3d3d38; --neutral-500:#6b6b62;
  --neutral-300:#c4c4b8; --neutral-100:#f2f2ed; --neutral-0:#ffffff;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif;
     background:var(--neutral-100);color:var(--neutral-900);font-size:14px;line-height:1.6}
header{background:var(--green-1);color:var(--green-5);padding:20px 32px}
header h1{font-size:1.3rem;font-weight:700;color:var(--green-5);line-height:1.3}
header p{font-size:.78rem;opacity:.65;margin-top:4px}
.container{max-width:1200px;margin:0 auto;padding:20px 16px}
.section{background:var(--neutral-0);border-radius:12px;padding:22px 24px;
         margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,.07)}
.sec-title{font-size:1rem;font-weight:700;color:var(--neutral-900);margin-bottom:3px;line-height:1.3}
.sec-sub{font-size:.75rem;color:var(--neutral-500);margin-bottom:18px}

/* ── 히트맵 ── */
.heatmap{display:grid;grid-template-columns:108px repeat(4,1fr);gap:5px;margin-bottom:14px}
.hm-corner{}
.hm-col-hdr{text-align:center;padding:6px 4px 10px}
.hm-col-hdr .wk{font-size:.88rem;font-weight:700;color:var(--neutral-900)}
.hm-col-hdr .wlbl{font-size:.72rem;color:var(--neutral-700);display:block;margin-top:1px}
.hm-col-hdr .wref{font-size:.65rem;color:var(--neutral-300);display:block;margin-top:2px}
.hm-row-hdr{display:flex;flex-direction:column;align-items:flex-end;justify-content:center;
            padding-right:10px;text-align:right;gap:2px}
.hm-row-hdr .lk{font-size:.82rem;font-weight:700;color:var(--neutral-900)}
.hm-row-hdr .llbl{font-size:.66rem;color:var(--neutral-500);line-height:1.3}
.hm-cell{border-radius:8px;padding:10px 6px;text-align:center;cursor:pointer;
         transition:all .15s;border:2px solid transparent;min-height:72px;
         display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px}
.hm-cell:hover{transform:scale(1.04);box-shadow:0 2px 8px rgba(30,38,27,.18)}
.hm-cell.selected{border-color:var(--neutral-900)!important;
                  box-shadow:0 0 0 3px rgba(88,118,56,.4)}
.hm-cell.dim{opacity:.35}
.hm-cell.dim:hover{opacity:.65}
.hm-cell .rate{font-size:1.05rem;font-weight:700;line-height:1}
.hm-cell .cnt{font-size:.65rem;opacity:.75;margin-top:1px}
.hm-cell.empty{background:var(--neutral-100)!important;cursor:default}
.hm-cell.empty:hover{transform:none;box-shadow:none}

/* ── 범례 ── */
.legend{display:flex;align-items:center;gap:10px;font-size:.72rem;
        color:var(--neutral-500);flex-wrap:wrap;margin-top:4px}
.lg-item{display:flex;align-items:center;gap:4px}
.lg-box{width:22px;height:13px;border-radius:3px;flex-shrink:0}

/* ── 상세 카드 ── */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
       gap:10px;margin-bottom:22px}
.card{background:var(--neutral-100);border:1px solid var(--neutral-300);
      border-radius:10px;padding:14px 16px;text-align:center}
.card-label{font-size:.72rem;color:var(--neutral-500);margin-bottom:5px;line-height:1.3}
.card-value{font-size:1.3rem;font-weight:700;color:var(--green-3)}
.card-unit{font-size:.65rem;color:var(--neutral-500);margin-top:2px}

/* ── 차트 ── */
.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media(max-width:720px){.chart-grid{grid-template-columns:1fr}}
.chart-wrap{position:relative;height:240px}
.chart-title{font-size:.8rem;font-weight:600;color:var(--neutral-700);margin-bottom:8px}

/* ── 참고 노트 ── */
.dim-note{margin-top:14px;padding:10px 14px;background:#fef3c7;
          border:1px solid #fde68a;border-radius:8px;font-size:.78rem;
          color:#92400e;display:none}
footer{text-align:center;font-size:.72rem;color:var(--neutral-500);padding:16px}
</style>
</head>
<body>

<header>
  <h1>2023 소상공인 실태조사 — 16세그먼트 대시보드</h1>
  <p>숙박·음식점업(I) | 종사자 S1~S4 × 매출 L1~L4 | 중소벤처기업부·소상공인시장진흥공단 | 금액 단위: 백만원</p>
</header>

<div class="container">

  <!-- ── 히트맵 ── -->
  <div class="section">
    <div class="sec-title">세그먼트 히트맵 — 영업이익률 중앙값 (%)</div>
    <div class="sec-sub">셀 클릭 시 하단 상세 패널 업데이트 | S3·S4는 핵심 타겟 외 참고용 (opacity 낮춤) | 매출 > 0 + 최소 표본 5개 이상</div>
    <div id="heatmap" class="heatmap"></div>
    <div class="legend">
      <span>영업이익률:</span>
      <div class="lg-item"><div class="lg-box" style="background:#edf3a9;border:1px solid #c4c4b8"></div><span>~10%</span></div>
      <div class="lg-item"><div class="lg-box" style="background:#95a961"></div><span>10~20%</span></div>
      <div class="lg-item"><div class="lg-box" style="background:#587638"></div><span>20~30%</span></div>
      <div class="lg-item"><div class="lg-box" style="background:#3a5630"></div><span>30~40%</span></div>
      <div class="lg-item"><div class="lg-box" style="background:#1e261b"></div><span>40%+</span></div>
    </div>
  </div>

  <!-- ── 상세 패널 ── -->
  <div class="section">
    <div class="sec-title" id="detail-title">— 세그먼트를 선택하세요</div>
    <div class="sec-sub">비용 항목 중앙값 | 가중치 적용 추정치 병기 | 가중치 미적용 표본 기준</div>
    <div id="detail-cards" class="cards"></div>
    <div class="chart-grid">
      <div>
        <div class="chart-title">비용 구조 (중앙값, %)</div>
        <div class="chart-wrap"><canvas id="c-cost"></canvas></div>
      </div>
      <div>
        <div class="chart-title">경영 애로사항 Top 5</div>
        <div class="chart-wrap"><canvas id="c-hard"></canvas></div>
      </div>
    </div>
    <div id="dim-note" class="dim-note">
      ⚠ S3·S4는 핵심 타겟(소규모 1~3명) 외 참고용 세그먼트입니다.
    </div>
  </div>

</div>
<footer>중소벤처기업부·소상공인시장진흥공단, 2023년 소상공인실태조사 ｜ 기준일: 2023.12.31 ｜ 표본 40,000개</footer>

<script>
const D = __DATA__;

Chart.defaults.font.family = "'Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif";
Chart.defaults.color = '#6b6b62';

const comma = n => (n == null ? '-' : Math.round(n).toLocaleString('ko-KR'));
const pct   = v => (v == null ? '-' : v.toFixed(1) + '%');

// ── 색상 매핑 ─────────────────────────────────────────────────────────────────
const G_BG   = ['#edf3a9','#95a961','#587638','#3a5630','#1e261b'];
const G_TEXT = ['#1e261b','#1e261b','#ffffff','#ffffff','#ffffff'];

function rateColor(r) {
  if (r == null) return { bg:'#f2f2ed', text:'#c4c4b8' };
  const i = r < 10 ? 0 : r < 20 ? 1 : r < 30 ? 2 : r < 40 ? 3 : 4;
  return { bg: G_BG[i], text: G_TEXT[i] };
}

// ── 히트맵 빌드 ───────────────────────────────────────────────────────────────
function buildHeatmap() {
  const { levels, workers, worker_labels: wl, level_labels: ll, segments: segs } = D.grid;
  let h = '';

  // 헤더 행 (코너 + S1~S4)
  h += '<div></div>';
  workers.forEach((w, i) => {
    const ref = i >= 2 ? `<span class="wref">(참고용)</span>` : '';
    h += `<div class="hm-col-hdr">
      <span class="wk">${w}</span>
      <span class="wlbl">${wl[w]}</span>
      ${ref}
    </div>`;
  });

  // 데이터 행 (L4→L1 순, 위=고매출)
  levels.forEach(l => {
    h += `<div class="hm-row-hdr">
      <span class="lk">${l}</span>
      <span class="llbl">${ll[l]}</span>
    </div>`;

    workers.forEach((w, i) => {
      const key = `${w}x${l}`;
      const seg = segs[key];
      const dim = i >= 2 ? ' dim' : '';

      if (!seg || seg.profit_rate == null) {
        h += `<div class="hm-cell empty${dim}">
          <span style="font-size:.68rem;color:var(--neutral-300)">—</span>
        </div>`;
        return;
      }

      const { bg, text } = rateColor(seg.profit_rate);
      h += `<div id="cell-${w}-${l}" class="hm-cell${dim}"
        style="background:${bg};color:${text}"
        onclick="selectCell('${key}','${w}','${l}')">
        <span class="rate">${seg.profit_rate.toFixed(1)}%</span>
        <span class="cnt">n=${seg.n}</span>
      </div>`;
    });
  });

  document.getElementById('heatmap').innerHTML = h;
}

// ── 셀 선택 & 상세 업데이트 ──────────────────────────────────────────────────
let costChart = null, hardChart = null;

function selectCell(key, w, l) {
  // 선택 표시
  document.querySelectorAll('.hm-cell.selected').forEach(el => el.classList.remove('selected'));
  const cell = document.getElementById(`cell-${w}-${l}`);
  if (cell) cell.classList.add('selected');

  const seg  = D.grid.segments[key];
  const wlbl = D.grid.worker_labels[w];
  const llbl = D.grid.level_labels[l];
  const isDim = w === 'S3' || w === 'S4';

  // 제목 & 참고 노트
  document.getElementById('detail-title').textContent =
    `${w} × ${l} 상세 — ${wlbl} / ${llbl}`;
  document.getElementById('dim-note').style.display = isDim ? 'block' : 'none';

  // 카드
  const cards = [
    { label: '표본 수',        value: comma(seg.n),            unit: '개' },
    { label: '추정 사업체 수', value: comma(seg.weighted),     unit: '개 (가중치)' },
    { label: '영업이익률',     value: pct(seg.profit_rate),    unit: '중앙값' },
    { label: '매출 중앙값',    value: seg.매출중앙 != null ? comma(seg.매출중앙)+'백만' : '-', unit: '' },
    { label: '폐업 의향',      value: pct(seg.closure_pct),    unit: '폐업+은퇴' },
  ];
  document.getElementById('detail-cards').innerHTML = cards.map(c =>
    `<div class="card">
      <div class="card-label">${c.label}</div>
      <div class="card-value">${c.value}</div>
      <div class="card-unit">${c.unit}</div>
    </div>`
  ).join('');

  // 비용 구조 차트
  if (costChart) costChart.destroy();
  const costKeys = ['원가율','인건비율','임차료율','기타비용율','영업이익률'];
  const costBg   = ['#587638','#95a961','#3a5630','#c4c4b8','#1e261b'];
  const costVals = seg.cost ? costKeys.map(k => seg.cost[k] ?? 0) : Array(5).fill(0);
  costChart = new Chart(document.getElementById('c-cost'), {
    type: 'bar',
    data: {
      labels: costKeys,
      datasets: [{ data: costVals, backgroundColor: costBg, borderRadius: 4 }]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => ` ${ctx.parsed.x.toFixed(1)}%` } }
      },
      scales: {
        x: { grid: { color:'#f2f2ed' },
             ticks: { callback: v => v+'%', font: { size:10 } },
             title: { display:true, text:'% (중앙값)', color:'#6b6b62', font:{ size:10 } } },
        y: { grid: { display:false }, ticks: { font:{ size:11 } } }
      }
    }
  });

  // 애로사항 차트
  if (hardChart) hardChart.destroy();
  const hd = seg.hardship || { labels:[], values:[] };
  hardChart = new Chart(document.getElementById('c-hard'), {
    type: 'bar',
    data: {
      labels: hd.labels,
      datasets: [{ data: hd.values, backgroundColor: '#587638', borderRadius: 4 }]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color:'#f2f2ed' },
             ticks: { font:{ size:10 } },
             title: { display:true, text:'응답 건수', color:'#6b6b62', font:{ size:10 } } },
        y: { grid: { display:false }, ticks: { font:{ size:11 } } }
      }
    }
  });
}

// ── 초기화 ────────────────────────────────────────────────────────────────────
buildHeatmap();
selectCell('S1xL2', 'S1', 'L2');   // 기본 선택: S1 × L2
</script>
</body>
</html>"""

html = HTML_TEMPLATE.replace("__DATA__", DATA_JSON)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)

print(f"\n완료: {OUT}")
