"""
7790 버스 실시간 잔여석 수집기 (GBIS v2 API)

핵심 로직:
  - 버스가 정류장 X에 접근 중일 때 remainSeat 기록 (탑승 전)
  - 같은 버스가 다음 정류장 X+1에 접근 중일 때 → 이미 X를 통과한 것
  - 탑승 인원(X) = remainSeat_접근X - remainSeat_접근X+1

하교 정류장 순서: 효행초등학교정문 → 아이파크정문 → 신명아파트 → 수원대입구
"""

import requests
import pandas as pd
import time
import os
from datetime import datetime
from urllib.parse import unquote

API_KEY  = unquote(os.environ.get(
    'PUBLIC_DATA_API_KEY',
    'J1NNfn5UJ4zegGKBELL2lGTySAkSdNuFdugnZ0Pf5/e2OsLWJOSJOEeSiQObz15Ns1opof3iEqWhwbhTAg5U4A=='
))
API_URL  = 'https://apis.data.go.kr/6410000/busarrivalservice/v2/getBusArrivalListv2'
ROUTE_ID = 200000149
OUTPUT   = './seat_log.csv'
INTERVAL = 10

CAPACITY = {0: 45, 1: 45, 2: 70}

# 하교 방향 정류장 순서
STOP_ORDER = [
    ('효행초등학교정문', '233002245'),
    ('아이파크정문',     '233002371'),
    ('신명아파트',       '233002255'),
    ('수원대입구',       '233003021'),
]
NEXT_STOP = {
    '효행초등학교정문': '아이파크정문',
    '아이파크정문':     '신명아파트',
    '신명아파트':       '수원대입구',
}


def fetch_7790(station_id: str) -> dict | None:
    try:
        r = requests.get(API_URL, params={'serviceKey': API_KEY, 'stationId': station_id}, timeout=10)
        r.raise_for_status()
        items = r.json()['response']['msgBody']['busArrivalList']
        if isinstance(items, dict):
            items = [items]
        for item in items:
            if item.get('routeId') == ROUTE_ID and item.get('vehId1'):
                low = item.get('lowPlate1', 0)
                low = int(low) if str(low).lstrip('-').isdigit() else 0
                rem = item.get('remainSeatCnt1', -1)
                rem = int(rem) if str(rem).lstrip('-').isdigit() else -1
                cap = CAPACITY.get(low, 45)
                return {
                    'vehId':      str(item['vehId1']),
                    'plateNo':    str(item.get('plateNo1', '')).strip(),
                    'busType':    low,
                    'capacity':   cap,
                    'remainSeat': rem,
                    'passengers': cap - rem if rem >= 0 else -1,
                    'predictMin': item.get('predictTime1', ''),
                }
    except Exception as e:
        print(f"  API 오류 ({station_id}): {e}")
    return None


def save(rows: list):
    if not rows:
        return
    df = pd.DataFrame(rows)
    write_header = not os.path.exists(OUTPUT)
    df.to_csv(OUTPUT, mode='a', header=write_header, index=False)


def main():
    print(f"[{datetime.now():%H:%M:%S}] 수집 시작 (간격: {INTERVAL}초)")
    print(f"저장 파일: {OUTPUT}\n")

    # (vehId, stop_name) → remainSeat: 해당 정류장 접근 시 잔여석 (탑승 전)
    approaching = {}

    while True:
        now  = datetime.now()
        rows = []

        for stop_name, station_id in STOP_ORDER:
            bus = fetch_7790(station_id)
            if bus is None or bus['remainSeat'] < 0:
                continue

            vid = bus['vehId']
            key = (vid, stop_name)

            # 이 버스를 이 정류장에서 처음 봤을 때 → 접근 중 (탑승 전) 기록
            if key not in approaching:
                approaching[key] = bus['remainSeat']

            # 이 버스가 이전 정류장을 이미 통과했는지 확인
            prev_stop = next(
                (s for s, n in NEXT_STOP.items() if n == stop_name), None
            )
            prev_key = (vid, prev_stop) if prev_stop else None
            boardings = None

            if prev_key and prev_key in approaching:
                # 버스가 prev_stop을 통과해서 현재 stop에 접근 중
                # → prev_stop에서의 탑승 인원 = 이전 잔여석 - 현재 잔여석
                boardings = approaching[prev_key] - bus['remainSeat']
                boardings = max(0, boardings)

                row = {
                    'timestamp':       now.strftime('%Y-%m-%d %H:%M:%S'),
                    'date':            now.strftime('%Y-%m-%d'),
                    'hour':            now.hour,
                    'weekday':         now.weekday(),
                    'stop':            prev_stop,
                    'vehId':           vid,
                    'plateNo':         bus['plateNo'],
                    'busType':         bus['busType'],
                    'capacity':        bus['capacity'],
                    'remainSeat_before': approaching[prev_key],
                    'remainSeat_after':  bus['remainSeat'],
                    'boardings':       boardings,
                }
                rows.append(row)

                bus_label = f"{'2층' if bus['busType']==2 else '1층'}({bus['capacity']}석)"
                print(f"  ✅ [{now:%H:%M:%S}] {bus['plateNo']} {bus_label} | "
                      f"{prev_stop} 탑승: {boardings}명 "
                      f"(잔여 {approaching[prev_key]}→{bus['remainSeat']}석)")

                # 이전 정류장 기록 정리
                del approaching[prev_key]

        save(rows)
        time.sleep(INTERVAL)


if __name__ == '__main__':
    main()
