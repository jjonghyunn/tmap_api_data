"""
Train Congestion Heatmap Builder
==================================
통계성 열차 혼잡도 API 조회 후
  - 날짜_시간.csv  : 원본 로그 (long format, 누적)
  - heatmap_YYYYMMDD_HHMM.csv : 역 × 시간대 pivot (히트맵용)
  - heatmap_YYYYMMDD_HHMM.png : 히트맵 이미지 (seaborn)

pip install requests pandas matplotlib seaborn

TODO: API 스펙 확인 후 call_api() 내부 채우기
"""

import requests
import pandas as pd
import os
from datetime import datetime

# ================================================================
# Config
# ================================================================

API_KEY = "input_yours"
HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
    "appKey": API_KEY,
}

# 조회할 역 목록 (stationID는 API 스펙 확인 후 채우기)
# 형식: { 역명: stationID }
STATIONS = {
    "강남":              "TODO",
    "홍대입구":          "TODO",
    "잠실":              "TODO",
    "서울":              "TODO",
    "사당":              "TODO",
    "노원":              "TODO",
    "왕십리":            "TODO",
    "신도림":            "TODO",
    "고속터미널":        "TODO",
    "동대문역사문화공원": "TODO",
}

# 조회할 시간대 (0~23시)
HOURS = list(range(6, 24))  # 06시~23시

# ================================================================
# API 호출 (스펙 확인 후 채우기)
# ================================================================

def call_api(station_id: str, hour: int) -> int | None:
    """
    TODO: 통계성 열차 혼잡도 API 스펙 확인 후 구현
    - API URL, 파라미터명, 응답 필드명 채우기
    - 현재는 placeholder 상태

    Returns: 혼잡도 수치 (int) or None
    """
    # ── 아래를 실제 API 스펙으로 교체 ──
    # url = "https://apis.openapi.sk.com/..."
    # payload = { "stationId": station_id, "hour": hour, ... }
    # resp = requests.post(url, headers=HEADERS, json=payload, timeout=10)
    # resp.raise_for_status()
    # return resp.json().get("congestionLevel")
    raise NotImplementedError("API 스펙 확인 후 구현 필요")


# ================================================================
# 수집 → CSV 저장
# ================================================================

def collect_and_save():
    now       = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M")
    raw_path  = f"{timestamp}.csv"          # 원본 로그
    heat_path = f"heatmap_{timestamp}.csv"  # 히트맵용 pivot

    print(f"[{timestamp}] 혼잡도 수집 시작\n")

    rows = []
    for station_name, station_id in STATIONS.items():
        if station_id == "TODO":
            print(f"  skip (stationID 미설정): {station_name}")
            continue

        for hour in HOURS:
            try:
                level = call_api(station_id, hour)
                rows.append({
                    "timestamp": timestamp,
                    "station":   station_name,
                    "hour":      hour,
                    "congestion": level,
                })
                print(f"  {station_name} {hour:02d}시 → {level}")
            except NotImplementedError:
                print("API 미구현. call_api() 를 먼저 채우세요.")
                return
            except Exception as e:
                print(f"  [ERROR] {station_name} {hour:02d}시: {e}")
                rows.append({
                    "timestamp": timestamp,
                    "station":   station_name,
                    "hour":      hour,
                    "congestion": None,
                })

    if not rows:
        print("수집된 데이터 없음.")
        return

    # ── 원본 long format CSV (누적)
    df = pd.DataFrame(rows)
    if os.path.exists(raw_path):
        df.to_csv(raw_path, mode="a", header=False, index=False, encoding="utf-8-sig")
    else:
        df.to_csv(raw_path, index=False, encoding="utf-8-sig")
    print(f"\n원본 저장: {raw_path}")

    # ── Pivot → 히트맵용 CSV
    #    rows=역명, cols=시간대, values=혼잡도
    pivot = df.pivot_table(
        index="station",
        columns="hour",
        values="congestion",
        aggfunc="mean",
    )
    pivot.columns = [f"{h:02d}시" for h in pivot.columns]
    pivot.index.name = "역명"
    pivot.to_csv(heat_path, encoding="utf-8-sig")
    print(f"히트맵 CSV 저장: {heat_path}")

    draw_heatmap(pivot, timestamp)


# ================================================================
# 히트맵 이미지
# ================================================================

def draw_heatmap(pivot: pd.DataFrame, timestamp: str):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm
        import seaborn as sns

        # 한글 폰트 설정 (Windows)
        font_path = "C:/Windows/Fonts/malgun.ttf"
        if os.path.exists(font_path):
            fm.fontManager.addfont(font_path)
            plt.rcParams["font.family"] = "Malgun Gothic"
        plt.rcParams["axes.unicode_minus"] = False

        fig, ax = plt.subplots(figsize=(16, 6))
        sns.heatmap(
            pivot,
            annot=True, fmt=".0f",
            cmap="RdYlGn_r",          # 초록(여유) → 빨강(혼잡)
            linewidths=0.5,
            ax=ax,
            cbar_kws={"label": "혼잡도 지수"},
        )
        ax.set_title(f"서울 주요 환승역 시간대별 혼잡도 ({timestamp})", fontsize=14, pad=12)
        ax.set_xlabel("시간대")
        ax.set_ylabel("역명")

        img_path = f"heatmap_{timestamp}.png"
        plt.tight_layout()
        plt.savefig(img_path, dpi=150)
        plt.close()
        print(f"히트맵 이미지 저장: {img_path}")

    except ImportError:
        print("seaborn/matplotlib 없음 → 이미지 생략 (pip install seaborn matplotlib)")


# ================================================================
# 누적 데이터로 히트맵만 다시 그리기
# ================================================================

def rebuild_heatmap_from_log(csv_path: str):
    """기존 원본 CSV로 히트맵 재생성"""
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    pivot = df.pivot_table(
        index="station", columns="hour", values="congestion", aggfunc="mean"
    )
    pivot.columns = [f"{h:02d}시" for h in pivot.columns]
    pivot.index.name = "역명"

    ts = csv_path.replace(".csv", "")
    heat_path = f"heatmap_{ts}.csv"
    pivot.to_csv(heat_path, encoding="utf-8-sig")
    print(f"재생성: {heat_path}")
    draw_heatmap(pivot, ts)


# ================================================================
# Entry
# ================================================================

if __name__ == "__main__":
    collect_and_save()
