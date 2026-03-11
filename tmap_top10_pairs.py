"""
Pair Selector — Smart Top-N Pair Picker
=========================================
MAJOR_STATIONS의 모든 조합(쌍) 중에서
API 호출 없이 좌표만으로 최적의 N개 쌍을 자동 선정합니다.

선정 기준 (그리디):
  1. 거리 점수  : 직선 거리가 길수록 경유 정류장이 많을 가능성 높음
  2. 방향 다양성: 이미 선택된 쌍과 진행 방향이 겹치면 패널티
     → 두 기준을 곱해서 매 라운드 가장 높은 쌍을 선택

출력: 선정된 쌍 목록 + 시각화 텍스트 테이블
      seoul_major_hubs.py의 PAIRS에 붙여넣을 수 있는 코드 블록도 출력
"""

import math
from itertools import combinations

# ================================================================
# 역 목록 (seoul_major_hubs.py 와 동일)
# ================================================================

MAJOR_STATIONS = {
    "강남":              (127.0276, 37.4979),
    "교대":              (127.0138, 37.4939),
    "고속터미널":        (127.0047, 37.5049),
    "사당":              (126.9814, 37.4765),
    "서울":              (126.9707, 37.5547),
    "시청":              (126.9772, 37.5658),
    "종로3가":           (126.9921, 37.5703),
    "동대문역사문화공원":(127.0076, 37.5651),
    "충무로":            (126.9942, 37.5607),
    "홍대입구":          (126.9236, 37.5571),
    "합정":              (126.9147, 37.5499),
    "공덕":              (126.9517, 37.5442),
    "신도림":            (126.8910, 37.5085),
    "당산":              (126.9012, 37.5340),
    "왕십리":            (127.0373, 37.5613),
    "건대입구":          (127.0700, 37.5402),
    "잠실":              (127.1000, 37.5133),
    "강변":              (127.0940, 37.5341),
    "노원":              (127.0561, 37.6547),
    "창동":              (127.0474, 37.6529),
}

# ================================================================
# 거리 / 방향 계산
# ================================================================

def haversine(lon1, lat1, lon2, lat2) -> float:
    """두 좌표 간 직선 거리 (km)"""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def angle(lon1, lat1, lon2, lat2) -> float:
    """출발→도착 방향각 (0~360도, 북=0)"""
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    return math.degrees(math.atan2(dlon, dlat)) % 360


def angle_diff(a1, a2) -> float:
    """두 방향각의 최소 차이 (0~180도)"""
    diff = abs(a1 - a2) % 360
    return min(diff, 360 - diff)

# ================================================================
# 그리디 쌍 선정
# ================================================================

def select_pairs(n: int = 10, verbose: bool = True) -> list:
    """
    모든 조합에서 거리 × 방향 다양성 기준으로 상위 n개 쌍 선정.
    Returns: [(start, end), ...]
    """
    stations = list(MAJOR_STATIONS.items())

    # 모든 후보 쌍 계산
    candidates = []
    for (s_name, s_coord), (e_name, e_coord) in combinations(stations, 2):
        dist = haversine(s_coord[0], s_coord[1], e_coord[0], e_coord[1])
        ang  = angle(s_coord[0], s_coord[1], e_coord[0], e_coord[1])
        candidates.append({
            "start": s_name, "end": e_name,
            "dist": dist, "angle": ang,
        })

    # 거리 정규화 (0~1)
    max_dist = max(c["dist"] for c in candidates)
    for c in candidates:
        c["dist_score"] = c["dist"] / max_dist

    selected       = []
    selected_angles = []

    for _ in range(n):
        best_score = -1
        best_cand  = None

        for c in candidates:
            if (c["start"], c["end"]) in [(s, e) for s, e in selected]:
                continue

            # 방향 다양성: 선택된 쌍들과 가장 가까운 방향각 차이
            if not selected_angles:
                diversity = 1.0  # 첫 번째는 패널티 없음
            else:
                min_diff  = min(angle_diff(c["angle"], a) for a in selected_angles)
                diversity = min_diff / 180  # 0~1 정규화

            score = c["dist_score"] * (0.4 + 0.6 * diversity)  # 거리 40% + 방향 60%

            if score > best_score:
                best_score = score
                best_cand  = c

        if best_cand:
            selected.append((best_cand["start"], best_cand["end"]))
            selected_angles.append(best_cand["angle"])

    if verbose:
        print_result(selected, candidates)

    return selected


def print_result(selected: list, candidates: list):
    cand_map = {(c["start"], c["end"]): c for c in candidates}

    print("=" * 65)
    print(f"  선정된 {len(selected)}개 쌍 (거리 + 방향 다양성 기준)")
    print("=" * 65)
    print(f"{'순위':>4}  {'쌍':<22}  {'거리(km)':>8}  {'방향각':>6}")
    print("-" * 65)

    for i, (s, e) in enumerate(selected, 1):
        c = cand_map.get((s, e), {})
        dist = c.get("dist", 0)
        ang  = c.get("angle", 0)
        compass = angle_to_compass(ang)
        print(f"  {i:2d}.  {s}→{e:<18}  {dist:>7.1f}km  {ang:>6.1f}° ({compass})")

    print()
    print("# ── seoul_major_hubs.py의 PAIRS에 붙여넣기 ──")
    print("PAIRS = [")
    for s, e in selected:
        print(f'    ("{s}", "{e}"),')
    print("]")


def angle_to_compass(ang: float) -> str:
    dirs = ["N","NE","E","SE","S","SW","W","NW"]
    return dirs[round(ang / 45) % 8]


# ================================================================
# 실행
# ================================================================

if __name__ == "__main__":
    print("MAJOR_STATIONS 총", len(MAJOR_STATIONS), "개역")
    total_combos = len(MAJOR_STATIONS) * (len(MAJOR_STATIONS) - 1) // 2
    print(f"전체 가능한 조합: {total_combos}개 → 상위 10개 선정\n")

    best_pairs = select_pairs(n=10)
