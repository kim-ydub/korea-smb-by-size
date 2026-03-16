#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
소상공인 실태조사 2023 분석 스크립트
실행: python3 analysis.py
출력: index.html (Chart.js 기반, 데이터 인라인 삽입)
"""
import pandas as pd
import numpy as np
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
CSV  = os.path.join(BASE, "DATA", "2023_연간자료_등록기반_20260316_40039.csv")
OUT  = os.path.join(BASE, "index.html")

# ── 1. 데이터 로드 ────────────────────────────────────────────────────────────
print("CSV 로드 중 (EUC-KR)…")
df = pd.read_csv(CSV, encoding="euc-kr", low_memory=False)
print(f"  원본: {df.shape[0]:,}행 × {df.shape[1]}컬럼")

# 이상값 제거: 매출액 > 100억(=1,000,000만원)
df = df[df["경영_매출금액"] <= 1_000_000].copy()

# 요식업 (숙박·음식점업 I)
food = df[df["산업대분류코드"] == "I"].copy()
print(f"  요식업 표본: {len(food):,}행")

# ── 2. 전처리 ─────────────────────────────────────────────────────────────────
WORDER = ["1명(대표자만)", "2~3명", "4~9명", "10명 이상"]
SORDER = ["1~3명", "4명 이상"]
RORDER = ["~5천만", "5천~1억", "1억~2억", "2억 이상"]

def worker_grp(n):
    if n == 1:    return "1명(대표자만)"
    elif n <= 3:  return "2~3명"
    elif n <= 9:  return "4~9명"
    return "10명 이상"

def size_grp(n):
    return "1~3명" if n <= 3 else "4명 이상"

def rev_grp(v):
    if v < 5_000:   return "~5천만"
    elif v < 10_000: return "5천~1억"
    elif v < 20_000: return "1억~2억"
    return "2억 이상"

food["종사자규모"] = food["일반_합계종사자수"].apply(worker_grp)
food["소규모"]    = food["일반_합계종사자수"].apply(size_grp)

# 매출 > 0 (비율 계산용)
pos = food[food["경영_매출금액"] > 0].copy()
pos["매출구간"] = pos["경영_매출금액"].apply(rev_grp)

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

# ── 3. 분석 1: 세그먼트 규모 ─────────────────────────────────────────────────
total_w      = df["사업체수가중값"].sum()
food_w       = food["사업체수가중값"].sum()
food_small_w = food[food["일반_합계종사자수"] <= 3]["사업체수가중값"].sum()
wdist = food.groupby("종사자규모")["사업체수가중값"].sum().reindex(WORDER).fillna(0)

seg = {
    "cards": [
        {"label": "전체 소상공인",          "value": int(round(total_w)),      "unit": "개 (추정, 가중치 적용)"},
        {"label": "숙박·음식점업",           "value": int(round(food_w)),       "unit": "개 (추정, 가중치 적용)"},
        {"label": "요식업 소규모(1~3명)",    "value": int(round(food_small_w)), "unit": "개 (추정, 가중치 적용)"},
        {"label": "요식업 표본 수",          "value": len(food),                "unit": "개 (원시 표본)"},
        {"label": "요식업 소규모 표본",      "value": int((food["일반_합계종사자수"] <= 3).sum()), "unit": "개 (원시 표본)"},
    ],
    "worker_dist": {
        "labels":   WORDER,
        "weighted": [int(round(v)) for v in wdist.values],
        "raw":      [int(food[food["종사자규모"] == g].shape[0]) for g in WORDER],
    }
}

# ── 4. 분석 2: 비용구조 ───────────────────────────────────────────────────────
def agg_med(df_, grp_col, order):
    g = df_.groupby(grp_col)[RLBLS].median().reindex(order)
    out = {"labels": order, "datasets": {}}
    for c in RLBLS:
        out["datasets"][c] = [round(float(v), 1) if pd.notna(v) else 0 for v in g[c]]
    return out

cost = {
    "by_worker": agg_med(pos, "종사자규모", WORDER),
    "by_size":   agg_med(pos, "소규모",    SORDER),
    "by_rev":    agg_med(pos, "매출구간",  RORDER),
}

# ── 5. 분석 3: 생존 vs 위기 ───────────────────────────────────────────────────
DC = [f"경영_운영활동_디지털대응{i}코드" for i in range(1, 9)]
DC_exist = [c for c in DC if c in pos.columns]
NO_DIG = {0, 8, 54}  # 활동없음 코드 (CLAUDE.md: 8, 파일설계서: 54)

sm = pos[pos["일반_합계종사자수"] <= 3].copy()

if DC_exist:
    dig_mat = pd.DataFrame({
        c: sm[c].notna() & ~sm[c].fillna(-1).astype(int).isin(NO_DIG)
        for c in DC_exist
    })
    sm["디지털도입"] = dig_mat.any(axis=1).astype(int)
else:
    sm["디지털도입"] = 0

q25 = sm["영업이익률"].quantile(0.25)
q75 = sm["영업이익률"].quantile(0.75)
top = sm[sm["영업이익률"] >= q75]
bot = sm[sm["영업이익률"] <= q25]

def gstat(g):
    return {
        "n":          int(len(g)),
        "매출중앙":   int(g["경영_매출금액"].median()),
        "이익률":     round(float(g["영업이익률"].median()), 1),
        "원가율":     round(float(g["원가율"].median()), 1),
        "인건비율":   round(float(g["인건비율"].median()), 1),
        "임차료율":   round(float(g["임차료율"].median()), 1),
        "기타":       round(float(g["기타비용율"].median()), 1),
        "프랜차이즈": round(float((g["일반_프랜차이즈가맹점여부"] == 1).mean() * 100), 1),
        "임차":       round(float((g["경영_점유형태코드"] == 2).mean() * 100), 1),
        "디지털":     round(float(g["디지털도입"].mean() * 100), 1),
    }

HBINS = list(range(-100, 110, 10))
ha, _ = np.histogram(sm["영업이익률"].clip(-100, 100),  bins=HBINS)
ht, _ = np.histogram(top["영업이익률"].clip(-100, 100), bins=HBINS)
hb, _ = np.histogram(bot["영업이익률"].clip(-100, 100), bins=HBINS)

surv = {
    "q25": round(float(q25), 1),
    "q75": round(float(q75), 1),
    "top25": gstat(top),
    "bot25": gstat(bot),
    "all":   gstat(sm),
    "hist": {
        "labels": [f"{b}~{b+10}" for b in HBINS[:-1]],
        "all": ha.tolist(), "top": ht.tolist(), "bot": hb.tolist(),
    }
}

# ── 6. 분석 4: 애로사항 ───────────────────────────────────────────────────────
HMAP = {
    1: "상권 쇠퇴", 2: "동일업종 경쟁", 3: "원재료비",
    4: "최저임금(인건비)", 5: "보증금·월세", 6: "부채상환",
    7: "인력관리", 8: "판로개척(온라인)", 9: "디지털 기술도입", 10: "기타",
}
HC = [f"경영_애로사항{i}코드" for i in range(1, 11)]
HC_exist = [c for c in HC if c in food.columns]

def cnt_hard(sub, n=5):
    cnt = {}
    for c in HC_exist:
        for v in sub[c].dropna():
            k = int(v)
            if k in HMAP:
                cnt[HMAP[k]] = cnt.get(HMAP[k], 0) + 1
    ranked = sorted(cnt.items(), key=lambda x: -x[1])[:n]
    return {"labels": [r[0] for r in ranked], "values": [r[1] for r in ranked]}

fsm   = food[food["일반_합계종사자수"] <= 3]
flg   = food[food["일반_합계종사자수"] > 3]
sbot  = sm[sm["영업이익률"] <= q25]

hard = {
    "small":    cnt_hard(fsm),
    "large":    cnt_hard(flg),
    "food_all": cnt_hard(food),
    "bot25":    cnt_hard(sbot),
}

# ── 7. 분석 5: 폐업 의향 ─────────────────────────────────────────────────────
PMAP = {1: "계속운영", 2: "사업전환", 3: "폐업 후 취업", 4: "폐업·은퇴"}
pcnt = food["사업전환_운영계획코드"].value_counts().sort_index()
pwt  = {k: int(round(food[food["사업전환_운영계획코드"] == k]["사업체수가중값"].sum()))
        for k in pcnt.index}

cl  = sm[sm["사업전환_운영계획코드"].isin([3, 4])]
ctn = sm[sm["사업전환_운영계획코드"] == 1]

plan = {
    "labels":   [PMAP.get(int(k), str(k)) for k in pcnt.index],
    "counts":   pcnt.tolist(),
    "weighted": [pwt[k] for k in pcnt.index],
    "cmp": {
        "계속운영": gstat(ctn),
        "폐업의향": gstat(cl),
    },
    "closure_hard": cnt_hard(cl),
    "cont_hard":    cnt_hard(ctn),
}

# ── 8. JSON 직렬화 ────────────────────────────────────────────────────────────
DATA_JSON = json.dumps(
    {"seg": seg, "cost": cost, "surv": surv, "hard": hard, "plan": plan},
    ensure_ascii=False
)

# ── 9. HTML 생성 ──────────────────────────────────────────────────────────────
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>2023 소상공인 실태조사 대시보드</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif;background:#f0f2f5;color:#1e293b;font-size:14px}
header{background:#0f172a;color:#f8fafc;padding:20px 32px}
header h1{font-size:1.3rem;font-weight:700}
header p{font-size:0.78rem;opacity:.65;margin-top:4px}
.container{max-width:1200px;margin:0 auto;padding:20px 16px}
.section{background:#fff;border-radius:12px;padding:22px 24px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.sec-title{font-size:1rem;font-weight:700;color:#0f172a;margin-bottom:3px}
.sec-sub{font-size:.75rem;color:#94a3b8;margin-bottom:18px}
/* Cards */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-bottom:22px}
.card{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px;text-align:center}
.card-label{font-size:.72rem;color:#64748b;margin-bottom:5px;line-height:1.3}
.card-value{font-size:1.45rem;font-weight:700;color:#1e40af}
.card-unit{font-size:.68rem;color:#94a3b8;margin-top:2px}
/* Chart grid */
.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media(max-width:720px){.chart-grid{grid-template-columns:1fr}}
.chart-wrap{position:relative;height:260px}
.chart-wrap.tall{height:320px}
.chart-title{font-size:.8rem;font-weight:600;color:#374151;margin-bottom:8px}
/* Toggles */
.toggles{display:flex;gap:7px;margin-bottom:14px;flex-wrap:wrap}
.tbtn{padding:4px 13px;border:1px solid #cbd5e1;border-radius:20px;background:#fff;font-size:.75rem;cursor:pointer;transition:.12s;color:#475569}
.tbtn.active{background:#1e40af;color:#fff;border-color:#1e40af}
/* Table */
.cmp-table{width:100%;border-collapse:collapse;font-size:.8rem;margin-top:10px}
.cmp-table th{background:#f1f5f9;padding:7px 10px;text-align:left;font-weight:600;border-bottom:2px solid #e2e8f0}
.cmp-table td{padding:7px 10px;border-bottom:1px solid #f8fafc}
.cmp-table tr:last-child td{border:none}
.tr{text-align:right}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:.7rem;font-weight:700}
.b-blue{background:#dbeafe;color:#1e40af}
.b-red{background:#fee2e2;color:#dc2626}
.b-green{background:#d1fae5;color:#059669}
footer{text-align:center;font-size:.72rem;color:#94a3b8;padding:16px}
</style>
</head>
<body>
<header>
  <h1>2023 소상공인 실태조사 대시보드</h1>
  <p>숙박·음식점업(I) 영세 소상공인 분석 ｜ 출처: 중소벤처기업부·소상공인시장진흥공단 (국가승인통계 제142021호) ｜ 금액 단위: 만원</p>
</header>

<div class="container">

  <!-- ① 세그먼트 규모 -->
  <div class="section">
    <div class="sec-title">① 타겟 세그먼트 규모</div>
    <div class="sec-sub">가중치(사업체수가중값) 적용 추정치 | 전체 소상공인 대비 요식업·소규모 비중</div>
    <div id="seg-cards" class="cards"></div>
    <div class="chart-grid">
      <div>
        <div class="chart-title">요식업 종사자 규모별 분포 (추정 사업체 수)</div>
        <div class="chart-wrap"><canvas id="c-wdist"></canvas></div>
      </div>
      <div>
        <div class="chart-title">요식업 종사자 규모별 비율 (도넛)</div>
        <div class="chart-wrap"><canvas id="c-wpie"></canvas></div>
      </div>
    </div>
  </div>

  <!-- ② 비용구조 -->
  <div class="section">
    <div class="sec-title">② 비용구조 분석</div>
    <div class="sec-sub">매출 > 0인 표본 기준 각 비용 항목 중앙값(%) | 가중치 미적용</div>
    <div class="toggles" id="cost-tog">
      <button class="tbtn active" data-v="by_worker">종사자 규모별</button>
      <button class="tbtn" data-v="by_size">소규모 vs 대규모</button>
      <button class="tbtn" data-v="by_rev">매출 구간별</button>
    </div>
    <div class="chart-wrap tall"><canvas id="c-cost"></canvas></div>
  </div>

  <!-- ③ 수익성 분포 -->
  <div class="section">
    <div class="sec-title">③ 수익성 분포 — 잘 버티는 가게 vs 못 버티는 가게</div>
    <div class="sec-sub">요식업 소규모(1~3명) + 매출 > 0 기준 | 가중치 미적용</div>
    <div class="chart-grid">
      <div>
        <div class="chart-title">영업이익률 분포 히스토그램 (%)</div>
        <div class="chart-wrap tall"><canvas id="c-hist"></canvas></div>
      </div>
      <div>
        <div class="chart-title">상위 25% vs 하위 25% 특성 비교</div>
        <div id="surv-tbl"></div>
      </div>
    </div>
  </div>

  <!-- ④ 애로사항 -->
  <div class="section">
    <div class="sec-title">④ 경영 애로사항 Top 5</div>
    <div class="sec-sub">복수 응답 기준 응답 건수 | 가중치 미적용</div>
    <div class="toggles" id="hard-tog">
      <button class="tbtn active" data-v="small">소규모(1~3명)</button>
      <button class="tbtn" data-v="large">대규모(4명+)</button>
      <button class="tbtn" data-v="food_all">요식업 전체</button>
      <button class="tbtn" data-v="bot25">이익률 하위 25%</button>
    </div>
    <div class="chart-wrap"><canvas id="c-hard"></canvas></div>
  </div>

  <!-- ⑤ 사업전망 -->
  <div class="section">
    <div class="sec-title">⑤ 사업 전망 — 폐업 의향 분석</div>
    <div class="sec-sub">요식업 전체 운영계획 분포 (가중치 적용) | 하단 비교표: 요식업 소규모(1~3명) 기준</div>
    <div class="chart-grid">
      <div>
        <div class="chart-title">향후 운영 계획 분포 (추정 사업체 수)</div>
        <div class="chart-wrap"><canvas id="c-plan"></canvas></div>
      </div>
      <div>
        <div class="chart-title">폐업 의향 집단 주요 애로사항 Top 5</div>
        <div class="chart-wrap"><canvas id="c-cl-hard"></canvas></div>
      </div>
    </div>
    <div style="margin-top:18px">
      <div class="chart-title">계속운영 vs 폐업의향 — 재무·운영 특성 비교</div>
      <div id="plan-tbl"></div>
    </div>
  </div>

</div>
<footer>중소벤처기업부·소상공인시장진흥공단, 2023년 소상공인실태조사 ｜ 기준일: 2023.12.31 ｜ 표본 40,000개</footer>

<script>
const D = __DATA__;

// 유틸
const comma = n => Math.round(n).toLocaleString('ko-KR');
const pct   = v => (v == null ? '-' : v.toFixed(1) + '%');
const BLUES4 = ['#1e40af','#2563eb','#60a5fa','#bfdbfe'];
const COST_COLORS = {
  '원가율':'#3b82f6','인건비율':'#f59e0b','임차료율':'#10b981','기타비용율':'#a78bfa','영업이익률':'#f87171'
};

// ─── ① 세그먼트 ───────────────────────────────────────────────────────────────
D.seg.cards.forEach(c => {
  document.getElementById('seg-cards').innerHTML +=
    `<div class="card"><div class="card-label">${c.label}</div>` +
    `<div class="card-value">${comma(c.value)}</div>` +
    `<div class="card-unit">${c.unit}</div></div>`;
});

new Chart(document.getElementById('c-wdist'), {
  type: 'bar',
  data: {
    labels: D.seg.worker_dist.labels,
    datasets: [{
      label: '추정 사업체 수',
      data: D.seg.worker_dist.weighted,
      backgroundColor: BLUES4, borderRadius: 5,
    }]
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      y: { ticks: { callback: v => comma(v) } },
      x: { ticks: { font: { size: 11 } } }
    }
  }
});

new Chart(document.getElementById('c-wpie'), {
  type: 'doughnut',
  data: {
    labels: D.seg.worker_dist.labels,
    datasets: [{ data: D.seg.worker_dist.weighted, backgroundColor: BLUES4 }]
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: {
      legend: { position: 'bottom', labels: { font: { size: 11 } } },
      tooltip: { callbacks: { label: ctx => {
        const tot = ctx.dataset.data.reduce((a,b)=>a+b,0);
        return ` ${comma(ctx.parsed)} (${(ctx.parsed/tot*100).toFixed(1)}%)`;
      }}}
    }
  }
});

// ─── ② 비용구조 ───────────────────────────────────────────────────────────────
const COST_KEYS = ['원가율','인건비율','임차료율','기타비용율','영업이익률'];
let costChart = null;

function drawCost(view) {
  const d = D.cost[view];
  if (costChart) costChart.destroy();
  costChart = new Chart(document.getElementById('c-cost'), {
    type: 'bar',
    data: {
      labels: d.labels,
      datasets: COST_KEYS.map(k => ({
        label: k, data: d.datasets[k],
        backgroundColor: COST_COLORS[k], borderRadius: 3,
      }))
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { font: { size: 11 }, boxWidth: 12 } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}%` } }
      },
      scales: {
        x: { ticks: { font: { size: 11 } } },
        y: { title: { display: true, text: '비율 (%, 중앙값)' }, ticks: { callback: v => v+'%' } }
      }
    }
  });
}
drawCost('by_worker');
document.getElementById('cost-tog').addEventListener('click', e => {
  const b = e.target.closest('.tbtn'); if (!b) return;
  document.querySelectorAll('#cost-tog .tbtn').forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  drawCost(b.dataset.v);
});

// ─── ③ 수익성 ─────────────────────────────────────────────────────────────────
const h = D.surv.hist;
new Chart(document.getElementById('c-hist'), {
  type: 'bar',
  data: {
    labels: h.labels,
    datasets: [
      { label: '전체',                          data: h.all, backgroundColor: '#cbd5e180' },
      { label: `상위 25% (≥${D.surv.q75}%)`,   data: h.top, backgroundColor: '#10b981cc' },
      { label: `하위 25% (≤${D.surv.q25}%)`,   data: h.bot, backgroundColor: '#ef4444cc' },
    ]
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { position: 'bottom', labels: { font: { size: 10 }, boxWidth: 12 } } },
    scales: {
      x: { ticks: { font: { size: 9 }, maxRotation: 45 } },
      y: { title: { display: true, text: '사업체 수 (표본)' } }
    }
  }
});

// 비교 테이블
const T = D.surv.top25, B = D.surv.bot25;
const sRows = [
  ['표본 수',        comma(T.n)+'개',          comma(B.n)+'개'],
  ['영업이익률(중앙)', pct(T['이익률']),        pct(B['이익률'])],
  ['매출 중앙값',    comma(T['매출중앙'])+'만원', comma(B['매출중앙'])+'만원'],
  ['원가율',         pct(T['원가율']),          pct(B['원가율'])],
  ['인건비율',       pct(T['인건비율']),        pct(B['인건비율'])],
  ['임차료율',       pct(T['임차료율']),        pct(B['임차료율'])],
  ['기타비용율',     pct(T['기타']),            pct(B['기타'])],
  ['프랜차이즈 비율', pct(T['프랜차이즈']),    pct(B['프랜차이즈'])],
  ['임차 비율',      pct(T['임차']),            pct(B['임차'])],
  ['디지털 도입률',  pct(T['디지털']),          pct(B['디지털'])],
];
document.getElementById('surv-tbl').innerHTML =
  `<table class="cmp-table"><thead><tr>
    <th>항목</th>
    <th><span class="badge b-blue">상위 25%</span></th>
    <th><span class="badge b-red">하위 25%</span></th>
  </tr></thead><tbody>
    ${sRows.map(r=>`<tr><td>${r[0]}</td><td class="tr">${r[1]}</td><td class="tr">${r[2]}</td></tr>`).join('')}
  </tbody></table>`;

// ─── ④ 애로사항 ───────────────────────────────────────────────────────────────
let hardChart = null;
function drawHard(view) {
  const d = D.hard[view];
  if (hardChart) hardChart.destroy();
  hardChart = new Chart(document.getElementById('c-hard'), {
    type: 'bar',
    data: {
      labels: d.labels,
      datasets: [{ label: '응답 건수', data: d.values, backgroundColor: '#3b82f6', borderRadius: 4 }]
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { title: { display: true, text: '응답 건수' } },
        y: { ticks: { font: { size: 12 } } }
      }
    }
  });
}
drawHard('small');
document.getElementById('hard-tog').addEventListener('click', e => {
  const b = e.target.closest('.tbtn'); if (!b) return;
  document.querySelectorAll('#hard-tog .tbtn').forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  drawHard(b.dataset.v);
});

// ─── ⑤ 사업전망 ───────────────────────────────────────────────────────────────
new Chart(document.getElementById('c-plan'), {
  type: 'doughnut',
  data: {
    labels: D.plan.labels,
    datasets: [{ data: D.plan.weighted, backgroundColor: ['#10b981','#f59e0b','#f87171','#dc2626'] }]
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: {
      legend: { position: 'bottom', labels: { font: { size: 11 } } },
      tooltip: { callbacks: { label: ctx => {
        const tot = ctx.dataset.data.reduce((a,b)=>a+b,0);
        return ` ${comma(ctx.parsed)} (${(ctx.parsed/tot*100).toFixed(1)}%)`;
      }}}
    }
  }
});

const ch = D.plan.closure_hard;
new Chart(document.getElementById('c-cl-hard'), {
  type: 'bar',
  data: {
    labels: ch.labels,
    datasets: [{ label: '폐업의향 집단', data: ch.values, backgroundColor: '#ef4444', borderRadius: 4 }]
  },
  options: {
    indexAxis: 'y',
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: { x: { title: { display: true, text: '응답 건수' } }, y: { ticks: { font: { size: 11 } } } }
  }
});

// 비교 테이블
const CT = D.plan.cmp['계속운영'], CL = D.plan.cmp['폐업의향'];
const pRows = [
  ['표본 수',        comma(CT.n)+'개',             comma(CL.n)+'개'],
  ['영업이익률(중앙)', pct(CT['이익률']),           pct(CL['이익률'])],
  ['매출 중앙값',    comma(CT['매출중앙'])+'만원',   comma(CL['매출중앙'])+'만원'],
  ['원가율',         pct(CT['원가율']),             pct(CL['원가율'])],
  ['인건비율',       pct(CT['인건비율']),           pct(CL['인건비율'])],
  ['임차료율',       pct(CT['임차료율']),           pct(CL['임차료율'])],
  ['기타비용율',     pct(CT['기타']),               pct(CL['기타'])],
  ['프랜차이즈 비율', pct(CT['프랜차이즈']),        pct(CL['프랜차이즈'])],
  ['디지털 도입률',  pct(CT['디지털']),             pct(CL['디지털'])],
];
document.getElementById('plan-tbl').innerHTML =
  `<table class="cmp-table"><thead><tr>
    <th>항목</th>
    <th><span class="badge b-green">계속운영</span></th>
    <th><span class="badge b-red">폐업의향(폐업+은퇴)</span></th>
  </tr></thead><tbody>
    ${pRows.map(r=>`<tr><td>${r[0]}</td><td class="tr">${r[1]}</td><td class="tr">${r[2]}</td></tr>`).join('')}
  </tbody></table>`;
</script>
</body>
</html>"""

html = HTML_TEMPLATE.replace("__DATA__", DATA_JSON)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)

print(f"\n완료: {OUT}")
print(f"  요식업 소규모(1~3명) 표본: {len(sm):,}개")
print(f"  영업이익률 Q25={q25:.1f}%, Q75={q75:.1f}%")
