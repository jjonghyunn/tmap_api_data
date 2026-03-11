"""
Seoul Major Transfer Hub Analysis
==================================
서울 주요 환승역(2개 이상 노선 교차) 간 경로를 조회해서
- 환승역들 사이의 소요시간 매트릭스
- 가장 빠른/느린 구간
- 직통 가능한 환승역 쌍
- 환승 없이 연결되는 허브 네트워크

전략: Free 10건/일 제한 → 하루 10쌍, 결과 누적 저장
      오늘 조회한 쌍은 다음 실행 시 skip

pip install requests pandas
"""

import requests
import pandas as pd
from collections import defaultdict
import time
import os
from datetime import date

# ================================================================
# Config
# ================================================================

API_KEY = "input_yours"
API_URL = "https://apis.openapi.sk.com/transit/routes"
HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
    "appKey": API_KEY,
}

DAILY_LIMIT     = 10
ROUTES_PER_CALL = 10

ROUTE_LOG = "major_route_log.csv"

# ================================================================
# Seoul Major Transfer Stations (2+ lines crossing)
# (lon, lat) WGS84
# ================================================================

MAJOR_STATIONS = {
    # 강남권
    "강남":         (127.0276, 37.4979),   # 2호선+신분당선
    "교대":         (127.0138, 37.4939),   # 2호선+3호선
    "고속터미널":   (127.0047, 37.5049),   # 3호선+7호선+9호선
    "사당":         (126.9814, 37.4765),   # 2호선+4호선
    # 도심
    "서울":         (126.9707, 37.5547),   # 1호선+4호선+경의중앙선+공항철도
    "시청":         (126.9772, 37.5658),   # 1호선+2호선
    "종로3가":      (126.9921, 37.5703),   # 1호선+3호선+5호선
    "동대문역사문화공원": (127.0076, 37.5651), # 2호선+4호선+5호선
    "충무로":       (126.9942, 37.5607),   # 3호선+4호선
    # 서울 서부
    "홍대입구":     (126.9236, 37.5571),   # 2호선+공항철도+경의중앙선
    "합정":         (126.9147, 37.5499),   # 2호선+6호선
    "공덕":         (126.9517, 37.5442),   # 5호선+6호선+경의중앙선+공항철도
    "신도림":       (126.8910, 37.5085),   # 1호선+2호선
    "당산":         (126.9012, 37.5340),   # 2호선+9호선
    # 서울 동부
    "왕십리":       (127.0373, 37.5613),   # 2호선+5호선+경의중앙선+수인분당선
    "건대입구":     (127.0700, 37.5402),   # 2호선+7호선
    "잠실":         (127.1000, 37.5133),   # 2호선+8호선
    "강변":         (127.0940, 37.5341),   # 2호선+경의중앙선(근처)
    # 서울 북부
    "노원":         (127.0561, 37.6547),   # 4호선+7호선
    "창동":         (127.0474, 37.6529),   # 1호선+4호선
}

# 조회할 쌍 목록 (도시 전역을 가로지르는 조합 우선)
# 총 20쌍 → 이틀에 걸쳐 완성
PAIRS = [
    # Day 1 - 동서 횡단 + 강남-도심
    ("홍대입구", "잠실"),
    ("신도림",   "왕십리"),
    ("서울",     "건대입구"),
    ("강남",     "종로3가"),
    ("사당",     "노원"),
    ("고속터미널","동대문역사문화공원"),
    ("합정",     "강변"),
    ("공덕",     "창동"),
    ("교대",     "홍대입구"),
    ("당산",     "잠실"),
    # Day 2 - 남북 종단 + 기타
    ("노원",     "강남"),
    ("창동",     "고속터미널"),
    ("잠실",     "홍대입구"),
    ("왕십리",   "사당"),
    ("서울",     "강남"),
    ("종로3가",  "신도림"),
    ("충무로",   "건대입구"),
    ("시청",     "왕십리"),
    ("강남",     "공덕"),
    ("노원",     "합정"),
]

# ================================================================
# Helpers
# ================================================================

def already_queried(pair_name: str) -> bool:
    if not os.path.exists(ROUTE_LOG):
        return False
    try:
        df = pd.read_csv(ROUTE_LOG, encoding="utf-8-sig")
        today = str(date.today())
        return not df[(df["쌍"] == pair_name) & (df["날짜"] == today)].empty
    except Exception:
        return False


def call_api(start_name, end_name) -> list:
    s = MAJOR_STATIONS[start_name]
    e = MAJOR_STATIONS[end_name]
    payload = {
        "startX": str(s[0]), "startY": str(s[1]),
        "endX":   str(e[0]), "endY":   str(e[1]),
        "count": ROUTES_PER_CALL, "lang": 0, "format": "json",
    }
    try:
        resp = requests.post(API_URL, headers=HEADERS, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json().get("metaData", {}).get("plan", {}).get("itineraries", [])
    except Exception as ex:
        print(f"  [ERROR] {start_name}→{end_name}: {ex}")
        return []


def parse_itineraries(pair_name, start_name, end_name, itineraries):
    today = str(date.today())
    rows = []
    for itin in itineraries:
        total_min  = round(itin.get("totalTime", 0) / 60, 1)
        transfer   = itin.get("transferCount", 0)
        fare       = itin.get("fare", {}).get("regular", {}).get("totalFare", 0)
        walk_m     = itin.get("totalWalkDistance", 0)
        legs       = itin.get("legs", [])
        modes      = [l["mode"] for l in legs if l["mode"] != "WALK"]
        lines      = [l.get("route", "") for l in legs if l["mode"] != "WALK"]
        rows.append({
            "날짜":       today,
            "쌍":         pair_name,
            "출발":       start_name,
            "도착":       end_name,
            "소요시간(분)": total_min,
            "환승횟수":   transfer,
            "요금(원)":   fare,
            "도보(m)":    walk_m,
            "수단":       " → ".join(modes),
            "노선":       " → ".join(l for l in lines if l),
        })
    return rows


def append_csv(filepath, rows):
    if not rows:
        return
    df_new = pd.DataFrame(rows)
    if os.path.exists(filepath):
        df_new.to_csv(filepath, mode="a", header=False, index=False, encoding="utf-8-sig")
    else:
        df_new.to_csv(filepath, index=False, encoding="utf-8-sig")

# ================================================================
# Main
# ================================================================

def run_today():
    called = 0
    print(f"[{date.today()}] Seoul Major Hub Analysis — 일일 {DAILY_LIMIT}건 한도\n")

    for start_name, end_name in PAIRS:
        if called >= DAILY_LIMIT:
            print(f"\n오늘 한도 {DAILY_LIMIT}건 도달. 내일 다시 실행하세요.")
            break

        pair_name = f"{start_name}→{end_name}"
        if already_queried(pair_name):
            print(f"  skip (오늘 조회 완료): {pair_name}")
            continue

        print(f"[{called+1:02d}] {pair_name:20s}", end=" ... ")
        itineraries = call_api(start_name, end_name)
        called += 1

        if not itineraries:
            print("no route")
            time.sleep(0.3)
            continue

        rows = parse_itineraries(pair_name, start_name, end_name, itineraries)
        append_csv(ROUTE_LOG, rows)

        best = rows[0]
        print(f"{best['소요시간(분)']}분 | 환승 {best['환승횟수']}회 | {best['요금(원)']}원 | {best['수단']}")
        time.sleep(0.3)

    print(f"\n오늘 {called}건 호출 완료.\n")
    show_results()


def show_results():
    if not os.path.exists(ROUTE_LOG):
        print("데이터 없음.")
        return
    try:
        df = pd.read_csv(ROUTE_LOG, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        print("데이터 없음.")
        return
    if df.empty:
        return

    days  = df["날짜"].nunique()
    pairs = df["쌍"].nunique()
    print(f"누적 데이터: {days}일 / {pairs}개 구간 / {len(df)}개 경로 후보\n")

    # 구간별 최단 시간 (best route 기준)
    best_df = df.groupby("쌍").agg(
        출발=("출발","first"),
        도착=("도착","first"),
        최단시간=("소요시간(분)","min"),
        최소환승=("환승횟수","min"),
        요금=("요금(원)","min"),
    ).reset_index().sort_values("최단시간")

    print("=" * 65)
    print("  구간별 최단 소요시간 (빠른 순)")
    print("=" * 65)
    print(best_df[["쌍","최단시간","최소환승","요금"]].to_string(index=False))

    print("\n" + "=" * 65)
    print("  직통(환승 0회) 가능한 구간")
    print("=" * 65)
    direct = best_df[best_df["최소환승"] == 0][["쌍","최단시간","요금"]]
    print(direct.to_string(index=False) if not direct.empty else "  없음")

    print("\n" + "=" * 65)
    print("  소요시간 TOP5 (오래 걸리는 구간)")
    print("=" * 65)
    print(best_df.nlargest(5, "최단시간")[["쌍","최단시간","최소환승"]].to_string(index=False))

    print("\n" + "=" * 65)
    print("  수단 조합별 등장 횟수")
    print("=" * 65)
    mode_cnt = df["수단"].value_counts()
    print(mode_cnt.to_string())

    # 노선별 등장 횟수
    line_counter = defaultdict(int)
    for row in df["노선"].dropna():
        for seg in str(row).split(" → "):
            seg = seg.strip()
            if seg:
                line_counter[seg] += 1
    line_df = pd.DataFrame(sorted(line_counter.items(), key=lambda x: -x[1])[:15],
                           columns=["노선", "등장횟수"])
    print("\n" + "=" * 65)
    print("  자주 등장하는 노선 TOP 15")
    print("=" * 65)
    print(line_df.to_string(index=False))

    best_df.to_csv("major_hub_summary.csv", index=False, encoding="utf-8-sig")
    print("\n저장 완료: major_hub_summary.csv")


if __name__ == "__main__":
    run_today()
