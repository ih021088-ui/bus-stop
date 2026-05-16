import pandas as pd
import numpy as np
import glob
import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# ── 정류장 순번 매핑 ──────────────────────────────────────────────
STOP_SEQ = {
    5: '효행초등학교정문',
    6: '아이파크정문',
    7: '신명아파트',
    8: '수원대입구',
    32: '사당역9번출구앞',
}
PREV_SEQ = {5: 4, 6: 5, 7: 6, 8: 7}  # 탑승 역산용 이전 정류장
DEPART_HOURS = [13, 14, 15, 16, 17, 18]   # 하교 방향
ARRIVE_HOURS = [7, 8, 9, 10]              # 등교 방향

# ── 학사 주차 매핑 ────────────────────────────────────────────────
def build_week_map():
    entries = [
        # (시작일, 종료일, 학기구분, 주차)
        # 2025 1학기
        ('2025-03-04', '2025-03-07',  '2025_1', 1),
        ('2025-03-10', '2025-03-14',  '2025_1', 2),
        ('2025-03-17', '2025-03-21',  '2025_1', 3),
        ('2025-03-24', '2025-03-28',  '2025_1', 4),
        ('2025-03-31', '2025-04-04',  '2025_1', 5),
        ('2025-04-07', '2025-04-11',  '2025_1', 6),
        ('2025-04-14', '2025-04-18',  '2025_1', 7),
        ('2025-04-21', '2025-04-25',  '2025_1', 8),
        ('2025-04-28', '2025-05-02',  '2025_1', 9),
        ('2025-05-05', '2025-05-09',  '2025_1', 10),
        ('2025-05-12', '2025-05-16',  '2025_1', 11),
        ('2025-05-19', '2025-05-23',  '2025_1', 12),
        ('2025-05-26', '2025-05-30',  '2025_1', 13),
        ('2025-06-02', '2025-06-06',  '2025_1', 14),
        ('2025-06-09', '2025-06-13',  '2025_1', 15),
        ('2025-06-16', '2025-06-20',  '2025_1', 16),
        ('2025-06-23', '2025-06-27',  '2025_1', 17),
        # 2025 2학기
        ('2025-08-25', '2025-08-29',  '2025_2', 1),
        ('2025-09-01', '2025-09-05',  '2025_2', 2),
        ('2025-09-08', '2025-09-12',  '2025_2', 3),
        # 2026 1학기
        ('2026-03-04', '2026-03-06',  '2026_1', 1),
        ('2026-03-09', '2026-03-13',  '2026_1', 2),
        ('2026-03-16', '2026-03-20',  '2026_1', 3),
        ('2026-03-23', '2026-03-27',  '2026_1', 4),
        ('2026-03-30', '2026-04-03',  '2026_1', 5),
        ('2026-04-06', '2026-04-10',  '2026_1', 6),
        ('2026-04-13', '2026-04-17',  '2026_1', 7),
        ('2026-04-20', '2026-04-24',  '2026_1', 8),
        ('2026-04-27', '2026-05-01',  '2026_1', 9),
        ('2026-05-04', '2026-05-08',  '2026_1', 10),
        ('2026-05-11', '2026-05-15',  '2026_1', 11),
        ('2026-05-18', '2026-05-22',  '2026_1', 12),
        ('2026-05-25', '2026-05-29',  '2026_1', 13),
        ('2026-06-01', '2026-06-05',  '2026_1', 14),
        ('2026-06-08', '2026-06-12',  '2026_1', 15),
        ('2026-06-15', '2026-06-19',  '2026_1', 16),
    ]

    date_to_week = {}
    date_to_semester = {}
    for start, end, sem, week in entries:
        d = datetime.strptime(start, '%Y-%m-%d')
        end_d = datetime.strptime(end, '%Y-%m-%d')
        while d <= end_d:
            key = d.strftime('%Y_%m_%d')
            date_to_week[key] = week
            date_to_semester[key] = sem
            d += timedelta(days=1)
    return date_to_week, date_to_semester

# ── 시험기간 날짜 집합 ────────────────────────────────────────────
def build_exam_sets():
    def date_range(start, end):
        s, e = datetime.strptime(start, '%Y-%m-%d'), datetime.strptime(end, '%Y-%m-%d')
        dates = set()
        d = s
        while d <= e:
            dates.add(d.strftime('%Y_%m_%d'))
            d += timedelta(days=1)
        return dates

    midterm = date_range('2025-04-16', '2025-04-30') | date_range('2026-04-16', '2026-04-30')
    final   = date_range('2025-06-04', '2025-06-17') | date_range('2026-06-08', '2026-06-19')
    return midterm, final

# ── 공휴일 (수동 입력) ────────────────────────────────────────────
HOLIDAYS = {
    '2025_03_01',  # 삼일절
    '2025_05_05',  # 어린이날
    '2025_05_06',  # 어린이날 대체공휴일
    '2025_06_06',  # 현충일
    '2026_03_01',  # 삼일절
    '2026_05_05',  # 어린이날
}

# ── 포화 임계값 ───────────────────────────────────────────────────
CAP_1FLOOR = 45
CAP_2FLOOR = 70

# ── 단일 파일 파싱 ────────────────────────────────────────────────
def parse_file(filepath, week_map, semester_map, midterm_set, final_set):
    df = pd.read_excel(filepath)
    date_str = os.path.basename(filepath).replace('.xlsx', '')

    # 컬럼명 정규화 (파일마다 약간 다를 수 있음)
    cols = list(df.columns)
    seq_col = cols[2]   # 순번

    # 날짜 피처
    dt = datetime.strptime(date_str, '%Y_%m_%d')
    weekday   = dt.weekday()                            # 0=월 ~ 4=금
    week_num  = week_map.get(date_str, -1)
    semester  = semester_map.get(date_str, 'unknown')
    is_exam_mid  = int(date_str in midterm_set)
    is_exam_fin  = int(date_str in final_set)
    is_exam      = int(is_exam_mid or is_exam_fin)
    is_holiday   = int(date_str in HOLIDAYS)

    # 시험 직전 주 (중간고사 기준: 2025 7주차, 2026 7주차 / 기말: 2025 13주차)
    pre_exam_weeks = {('2025_1', 6), ('2026_1', 6), ('2025_1', 13), ('2026_1', 13)}
    is_pre_exam = int((semester, week_num) in pre_exam_weeks)

    # 학기 구분 (1학기=1, 2학기=2)
    sem_num = int(semester.split('_')[1]) if semester != 'unknown' else -1

    rows = []

    # ── 하교 방향: 수원대 4개 정류장 13~18시 ─────────────────────
    seq_vals = dict(zip(df[seq_col], df.to_dict('records')))

    for seq, stop_name in STOP_SEQ.items():
        if seq == 32:
            continue
        if seq not in seq_vals:
            continue

        prev_seq = PREV_SEQ[seq]
        if prev_seq not in seq_vals:
            continue

        curr_row = seq_vals[seq]
        prev_row = seq_vals[prev_seq]

        for hour in DEPART_HOURS:
            curr_val = curr_row.get(hour, 0) or 0
            prev_val = prev_row.get(hour, 0) or 0
            boardings = max(0, curr_val - prev_val)

            is_sat_1f = int(curr_val >= CAP_1FLOOR * 0.95)
            is_sat_2f = int(curr_val >= CAP_2FLOOR * 0.95)

            rows.append({
                'date': date_str,
                'stop': stop_name,
                'seq': seq,
                'direction': 'depart',   # 하교
                'hour': hour,
                'boardings': boardings,
                'weekday': weekday,
                'week_num': week_num,
                'semester': semester,
                'sem_num': sem_num,
                'is_exam': is_exam,
                'is_exam_mid': is_exam_mid,
                'is_exam_fin': is_exam_fin,
                'is_pre_exam': is_pre_exam,
                'is_holiday': is_holiday,
                'is_sat_1floor': is_sat_1f,
                'is_sat_2floor': is_sat_2f,
            })

    # ── 등교 방향: 사당역9번출구앞 7~10시 ────────────────────────
    if 32 in seq_vals:
        sadang_row = seq_vals[32]
        for hour in ARRIVE_HOURS:
            val = sadang_row.get(hour, 0) or 0

            is_sat_1f = int(val >= CAP_1FLOOR * 0.95)
            is_sat_2f = int(val >= CAP_2FLOOR * 0.95)

            rows.append({
                'date': date_str,
                'stop': '사당역9번출구앞',
                'seq': 32,
                'direction': 'arrive',   # 등교
                'hour': hour,
                'boardings': val,
                'weekday': weekday,
                'week_num': week_num,
                'semester': semester,
                'sem_num': sem_num,
                'is_exam': is_exam,
                'is_exam_mid': is_exam_mid,
                'is_exam_fin': is_exam_fin,
                'is_pre_exam': is_pre_exam,
                'is_holiday': is_holiday,
                'is_sat_1floor': is_sat_1f,
                'is_sat_2floor': is_sat_2f,
            })

    return rows


# ── 기상청 ASOS 일 관측자료 조회 (수원 관측소 119번) ──────────────
ASOS_URL  = 'http://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList'
ASOS_STN  = 119   # 수원 지상관측소

def _parse_weather_row(r):
    """ASOS 응답 한 행 → (date_key, dict) or None"""
    dt = r.get('tm', '')              # 'YYYY-MM-DD'
    if not dt or len(dt) < 10:
        return None
    temp   = float(r.get('avgTa') or 15.0)
    precip = float(r.get('sumRn') or 0.0)
    key    = dt[:10].replace('-', '_')
    return key, {
        'temp_avg':  round(temp,   1),
        'precip_mm': round(precip, 1),
        'is_rainy':  int(precip >= 0.5),
        'is_cold':   int(temp    <  5.0),
        'is_hot':    int(temp    > 28.0),
    }

def _fetch_weather_kma(start_dt, end_dt, api_key):
    """기상청 ASOS API → {date_key: weather_dict}"""
    params = {
        'serviceKey': api_key,
        'pageNo':    1,
        'numOfRows': 999,
        'dataType':  'JSON',
        'dataCd':    'ASOS',
        'dateCd':    'DAY',
        'startDt':   start_dt.replace('-', ''),   # YYYYMMDD
        'endDt':     end_dt.replace('-', ''),
        'stnIds':    ASOS_STN,
    }
    resp = requests.get(ASOS_URL, params=params, timeout=30)
    resp.raise_for_status()
    body = resp.json()['response']['body']
    items = body.get('items', {}).get('item', [])
    result = {}
    for row in items:
        parsed = _parse_weather_row(row)
        if parsed:
            result[parsed[0]] = parsed[1]
    return result

def _fetch_weather_openmeteo(start_dt, end_dt):
    """Open-Meteo 역사 API fallback → {date_key: weather_dict}"""
    url = (
        'https://archive-api.open-meteo.com/v1/archive'
        f'?latitude=37.25&longitude=126.97'
        f'&start_date={start_dt}&end_date={end_dt}'
        '&daily=temperature_2m_mean,precipitation_sum'
        '&timezone=Asia%2FSeoul'
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()['daily']
    result = {}
    for d, temp, precip in zip(
        data['time'],
        data['temperature_2m_mean'],
        data['precipitation_sum'],
    ):
        temp   = float(temp   or 15.0)
        precip = float(precip or 0.0)
        result[d.replace('-', '_')] = {
            'temp_avg':  round(temp,   1),
            'precip_mm': round(precip, 1),
            'is_rainy':  int(precip >= 0.5),
            'is_cold':   int(temp    <  5.0),
            'is_hot':    int(temp    > 28.0),
        }
    return result

def fetch_weather(date_keys):
    """YYYY_MM_DD 날짜 목록 → {date_key: weather_dict}
    기상청 ASOS API 우선, 실패 시 Open-Meteo fallback.
    """
    api_key = os.environ.get('PUBLIC_DATA_API_KEY', '')

    valid  = sorted(d.replace('_', '-') for d in date_keys if len(d) == 10)
    if not valid:
        return {}
    start_dt, end_dt = valid[0], valid[-1]

    if api_key:
        try:
            result = _fetch_weather_kma(start_dt, end_dt, api_key)
            if result:
                print(f'  기상청 ASOS: {len(result)}일 조회 완료')
                return result
            print('  [경고] 기상청 ASOS 응답 비어 있음 → Open-Meteo fallback')
        except Exception as e:
            print(f'  [경고] 기상청 ASOS 실패: {e} → Open-Meteo fallback')
    else:
        print('  [경고] PUBLIC_DATA_API_KEY 없음 → Open-Meteo fallback')

    try:
        result = _fetch_weather_openmeteo(start_dt, end_dt)
        print(f'  Open-Meteo: {len(result)}일 조회 완료')
        return result
    except Exception as e:
        print(f'  [경고] Open-Meteo도 실패: {e} → 기본값 사용')
        return {}


# ── 전체 파일 처리 ────────────────────────────────────────────────
def build_dataset(data_dir='./해커톤데이터2'):
    week_map, semester_map = build_week_map()
    midterm_set, final_set = build_exam_sets()

    files = sorted(glob.glob(os.path.join(data_dir, '*.xlsx')))
    all_rows = []
    for f in files:
        rows = parse_file(f, week_map, semester_map, midterm_set, final_set)
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)

    df = df.sort_values(['stop', 'direction', 'hour', 'date']).reset_index(drop=True)

    # lag 계산은 휴일 행을 제외하고 수행 (서버의 _prev_weekday와 일치)
    df_work = df[df['is_holiday'] == 0].copy()
    grp = df_work.groupby(['stop', 'direction', 'hour'])['boardings']
    # lag1: 직전 운행일 (shift(1))
    df_work['boardings_lag1']  = grp.shift(1)
    # lag7: 약 1주 전 같은 요일 (운행일 기준 shift(5))
    df_work['boardings_lag7']  = grp.shift(5)
    # roll3: 직전 3 운행일 평균
    df_work['boardings_roll3'] = grp.transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())

    df = df.merge(
        df_work[['date', 'stop', 'direction', 'hour',
                 'boardings_lag1', 'boardings_lag7', 'boardings_roll3']],
        on=['date', 'stop', 'direction', 'hour'],
        how='left',
    )

    # ── 날씨 컬럼 추가 (Open-Meteo 역사 API) ──────────────────────
    print('날씨 데이터 조회 중...')
    weather = fetch_weather(df['date'].unique().tolist())
    WEATHER_DEFAULTS = {'temp_avg': 15.0, 'precip_mm': 0.0, 'is_rainy': 0, 'is_cold': 0, 'is_hot': 0}
    for col, default in WEATHER_DEFAULTS.items():
        df[col] = df['date'].map(lambda d, c=col: weather.get(d, {}).get(c, default))

    return df


if __name__ == '__main__':
    df = build_dataset('./해커톤데이터2')
    print(f'총 샘플 수: {len(df)}')
    print(f'컬럼: {list(df.columns)}')
    print()
    print(df.groupby(['direction', 'stop'])['boardings'].describe().round(1))
    df.to_csv('./preprocessed.csv', index=False, encoding='utf-8-sig')
    print('\n preprocessed.csv 저장 완료')
