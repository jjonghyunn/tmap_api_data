"""
TMAP 대중교통 API - 서울 교통 허브 역 TOP10 분석
=================================================
전략: Free 플랜 10건/일 제한에 맞춰 효율적으로 운영
  - 호출당 count=10 → 최대 10개 경로 후보 수집
  - 도시 전체를 가로지르는 10개 핵심 쌍만 선별
  - 결과를 CSV에 누적 저장 → 며칠 실행하면 점점 정확해짐
  - 이미 조회한 쌍은 skip (일일 한도 낭비 방지)

사전 준비:
    pip install requests pandas
"""

import requests
import pandas as pd
from collections import Counter
import time
import os
from datetime import date

# ================================================================
# 설정
# ================================================================

API_KEY  = "input_yours"
API_URL  = "https://apis.openapi.sk.com/transit/routes"
HEADERS  = {
    "accept": "application/json",
    "content-type": "application/json",
    "appKey": API_KEY,
}

DAILY_LIMIT      = 10   # Free 플랜 일일 한도
ROUTES_PER_CALL  = 10   # 호출당 경로 후보 수 (최대 10)

# 누적 저장 파일
STATION_LOG = "station_log.csv"   # 날짜별 경유역 로그
ROUTE_LOG   = "route_log.csv"     # 날짜별 경로 요약 로그

# ================================================================
# 핵심 조합 10쌍 - 서울 전역을 대각선/가로/세로로 가로지르는 쌍
# 한 번에 가장 많은 허브 역을 통과할 가능성이 높은 조합
# WGS84 (경도, 위도)
# ================================================================

PAIRS = [
    # 이름,         출발(lon, lat),            도착(lon, lat)
    ("홍대→잠실",   (126.9236, 37.5571),  (127.1000, 37.5133)),  # 동서 횡단
    ("신림→왕십리", (126.9294, 37.4847),  (127.0373, 37.5613)),  # 남→북동
    ("서울역→건대", (126.9707, 37.5547),  (127.0700, 37.5402)),  # 서→동
    ("수서→공덕",   (127.1021, 37.4872),  (126.9517, 37.5442)),  # 동남→서북
    ("여의도→동대문",(126.9243, 37.5215), (127.0076, 37.5651)),  # 서→동북
    ("강남→홍대",   (127.0276, 37.4979),  (126.9236, 37.5571)),  # 남동→서북
    ("이태원→성수", (126.9944, 37.5345),  (127.0567, 37.5447)),  # 중앙→동
    ("신촌→잠실",   (126.9368, 37.5550),  (127.1000, 37.5133)),  # 서→동
    ("종로3가→신림",(126.9921, 37.5703),  (126.9294, 37.4847)),  # 북→남서
    ("수서→홍대",   (127.1021, 37.4872),  (126.9236, 37.5571)),  # 동남→서북 대각선
]

# ================================================================
# 유틸
# ================================================================

def clean_station_name(name: str) -> str:
    """'지하철2호선강남역(중)' → '강남역' 형태로 정리"""
    name = name.split("(")[0].strip()
    for prefix in [
        "지하철1호선","지하철2호선","지하철3호선","지하철4호선","지하철5호선",
        "지하철6호선","지하철7호선","지하철8호선","지하철9호선",
        "신분당선","경의중앙선","수인분당선","공항철도","경춘선","우이신설선",
        "서해선","경강선","김포골드라인","신림선",
    ]:
        name = name.replace(prefix, "")
    return name.strip()


def already_queried(pair_name: str) -> bool:
    """오늘 이미 조회한 쌍인지 확인"""
    if not os.path.exists(ROUTE_LOG):
        return False
    df = pd.read_csv(ROUTE_LOG, encoding="utf-8-sig")
    today = str(date.today())
    return not df[(df["쌍"] == pair_name) & (df["날짜"] == today)].empty


def call_api(pair_name, start_coord, end_coord) -> list:
    payload = {
        "startX": str(start_coord[0]), "startY": str(start_coord[1]),
        "endX":   str(end_coord[0]),   "endY":   str(end_coord[1]),
        "count": ROUTES_PER_CALL, "lang": 0, "format": "json",
    }
    try:
        resp = requests.post(API_URL, headers=HEADERS, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json().get("metaData", {}).get("plan", {}).get("itineraries", [])
    except Exception as e:
        print(f"  [오류] {pair_name}: {e}")
        return []


def extract_info(pair_name, itineraries):
    """경유역 로그 + 경로 요약 추출"""
    today = str(date.today())
    station_rows = []
    route_rows   = []

    for itin in itineraries:
        total_time = round(itin.get("totalTime", 0) / 60, 1)
        transfer   = itin.get("transferCount", 0)
        fare       = itin.get("fare", {}).get("regular", {}).get("totalFare", 0)
        modes      = [l["mode"] for l in itin.get("legs", []) if l["mode"] != "WALK"]

        route_rows.append({
            "날짜": today, "쌍": pair_name,
            "소요시간(분)": total_time, "환승횟수": transfer,
            "요금(원)": fare, "이용수단": " → ".join(modes),
        })

        for leg in itin.get("legs", []):
            if leg.get("mode") not in ("BUS", "SUBWAY", "TRAIN", "EXPRESSBUS"):
                continue
            psl = leg.get("passStopList", {})
            # API 버전에 따라 키 이름이 stationList 또는 stations
            stop_list = psl.get("stationList") or psl.get("stations") or []
            for stop in stop_list:
                raw = stop.get("stationName", "")
                if raw:
                    station_rows.append({
                        "날짜": today, "쌍": pair_name,
                        "역명": clean_station_name(raw),
                        "mode": leg["mode"],
                    })

    return station_rows, route_rows


def append_csv(filepath, rows):
    df_new = pd.DataFrame(rows)
    if os.path.exists(filepath):
        df_new.to_csv(filepath, mode="a", header=False, index=False, encoding="utf-8-sig")
    else:
        df_new.to_csv(filepath, index=False, encoding="utf-8-sig")


# ================================================================
# 메인
# ================================================================

def run_today():
    """오늘 할당량 내에서 미조회 쌍만 호출"""
    called = 0
    print(f"[{date.today()}] 오늘 할당 {DAILY_LIMIT}건 내에서 실행\n")

    for pair_name, start_coord, end_coord in PAIRS:
        if called >= DAILY_LIMIT:
            print(f"오늘 한도({DAILY_LIMIT}건) 도달. 내일 다시 실행하세요.")
            break

        if already_queried(pair_name):
            print(f"  skip (오늘 이미 조회): {pair_name}")
            continue

        print(f"[{called+1}] {pair_name} 조회 중...", end=" ")
        itineraries = call_api(pair_name, start_coord, end_coord)
        called += 1

        if not itineraries:
            print("경로 없음")
            time.sleep(0.5)
            continue

        station_rows, route_rows = extract_info(pair_name, itineraries)
        append_csv(STATION_LOG, station_rows)
        append_csv(ROUTE_LOG,   route_rows)

        best = route_rows[0]
        print(f"{best['소요시간(분)']}분, 환승 {best['환승횟수']}회, {best['요금(원)']}원 "
              f"| 경유역 {len(station_rows)}개 수집")
        time.sleep(0.3)

    print(f"\n오늘 {called}건 호출 완료.")
    show_results()


def show_results():
    """누적 데이터 기준 TOP10 출력"""
    if not os.path.exists(STATION_LOG):
        print("아직 수집된 데이터 없음.")
        return

    try:
        s_df = pd.read_csv(STATION_LOG, encoding="utf-8-sig")
        r_df = pd.read_csv(ROUTE_LOG,   encoding="utf-8-sig") if os.path.exists(ROUTE_LOG) else pd.DataFrame()
    except pd.errors.EmptyDataError:
        print("경유역 데이터가 비어 있음 (passStopList 응답 없음). API 응답 구조를 확인하세요.")
        return

    if s_df.empty:
        print("경유역 데이터가 없습니다. API가 passStopList를 반환하지 않았을 수 있어요.")
        return

    total_routes   = len(r_df)
    total_stations = len(s_df)
    days_collected = s_df["날짜"].nunique() if total_stations > 0 else 0

    print(f"\n{'='*60}")
    print(f"  누적 데이터: {days_collected}일치, {total_routes}개 경로, {total_stations}개 경유역 기록")
    print(f"{'='*60}")

    # 서울 주요 환승역 목록 (2개 이상 노선 교차)
    MAJOR_HUBS = {
        "강남역", "신논현역", "역삼역", "교대역", "서초역",
        "사당역", "이수역", "동작역", "고속터미널역",
        "종로3가역", "을지로3가역", "을지로4가역", "충무로역",
        "서울역", "시청역", "광화문역",
        "홍대입구역", "합정역", "당산역", "영등포구청역",
        "신도림역", "구로디지털단지역",
        "여의도역", "국회의사당역",
        "잠실역", "삼성역", "선릉역", "역삼역", "강변역",
        "왕십리역", "성수역", "건대입구역",
        "신촌역", "이대역", "아현역",
        "공덕역", "마포역", "애오개역",
        "동대문역사문화공원역", "동대문역", "신설동역",
        "수서역", "복정역", "장지역",
        "노원역", "창동역", "도봉산역",
        "신분당선강남역", "양재역", "양재시민의숲역",
        "이태원역", "한강진역", "녹사평역",
        "신림역", "봉천역", "서울대입구역",
    }

    # ── 전체 TOP10
    counter = Counter(s_df["역명"].tolist())
    top10   = counter.most_common(10)
    hub_df  = pd.DataFrame(top10, columns=["역명", "경유횟수"])
    hub_df.index += 1
    print("\n  교통 허브 역 TOP 10 (경유 빈도 — 전체)")
    print(hub_df.to_string())

    # ── 주요 환승역만 필터링한 TOP10
    major_counts = {k: v for k, v in counter.items() if k in MAJOR_HUBS}
    if major_counts:
        major_df = pd.DataFrame(
            sorted(major_counts.items(), key=lambda x: -x[1])[:10],
            columns=["역명", "경유횟수"]
        )
        major_df.index += 1
        print("\n  주요 환승역 TOP 10 (환승역만 필터)")
        print(major_df.to_string())
    else:
        major_df = hub_df

    if not r_df.empty:
        # ── 오래 걸리는 구간
        print(f"\n{'='*60}")
        print("  소요시간 긴 구간 TOP5")
        print(r_df.groupby("쌍")["소요시간(분)"].mean().nlargest(5).round(1).to_string())

        # ── 빠른 구간
        print(f"\n{'='*60}")
        print("  소요시간 짧은 구간 TOP5")
        print(r_df.groupby("쌍")["소요시간(분)"].mean().nsmallest(5).round(1).to_string())

        # ── 환승 없는 구간
        no_tf = r_df[r_df["환승횟수"] == 0]["쌍"].value_counts()
        print(f"\n{'='*60}")
        print("  환승 없는 직통 경로가 있는 구간")
        print(no_tf.to_string() if not no_tf.empty else "  없음")

        # ── 수단별 비율
        mode_counts = {}
        for modes_str in r_df["이용수단"]:
            for m in str(modes_str).split(" → "):
                mode_counts[m] = mode_counts.get(m, 0) + 1
        print(f"\n{'='*60}")
        print("  이용 수단별 등장 횟수")
        for k, v in sorted(mode_counts.items(), key=lambda x: -x[1]):
            print(f"  {k:12s}: {v}회")

    # CSV 저장
    hub_df.to_csv("hub_stations_top10.csv", index=False, encoding="utf-8-sig")
    print(f"\n결과 저장 완료: hub_stations_top10.csv")


if __name__ == "__main__":
    run_today()
