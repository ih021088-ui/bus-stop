import pandas as pd
import numpy as np
import glob
import os
from datetime import datetime, timedelta

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
    final   = date_range('2025-06-04', '2025-06-17')
    return midterm, final

# ── 공휴일 (수동 입력) ────────────────────────────────────────────
HOLIDAYS = {
    '2025_03_01',  # 삼일절
    '2025_05_05',  # 어린이날
    '2025_05_06',  # 어린이날 대체공휴일
    '2025_06_06',  # 현충일
    '2026_03_01',  # 삼일절
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
    name_col = cols[3]  # 정류장명

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
    pre_exam_weeks = {('2025_1', 6), ('2026_1', 6), ('2025_1', 13)}
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

    # lag feature: 같은 정류장, 같은 방향, 같은 시간대 전날 탑승 수
    df = df.sort_values(['stop', 'direction', 'hour', 'date']).reset_index(drop=True)
    df['boardings_lag1'] = df.groupby(['stop', 'direction', 'hour'])['boardings'].shift(1)

    # 날씨 데이터 merge
    weather_path = os.path.join(os.path.dirname(data_dir) if data_dir != '.' else '.', 'weather.csv')
    if not os.path.exists(weather_path):
        weather_path = './weather.csv'
    if os.path.exists(weather_path):
        weather = pd.read_csv(weather_path)
        weather_cols = ['date', 'temp_avg', 'precip_mm', 'is_rainy', 'is_cold', 'is_hot']
        df = df.merge(weather[weather_cols], on='date', how='left')
    else:
        print('[경고] weather.csv 없음 — 날씨 피처가 NaN으로 채워집니다. collect_weather.py 먼저 실행하세요.')
        for col in ['temp_avg', 'precip_mm', 'is_rainy', 'is_cold', 'is_hot']:
            df[col] = float('nan')

    return df


if __name__ == '__main__':
    df = build_dataset('./해커톤데이터2')
    print(f'총 샘플 수: {len(df)}')
    print(f'컬럼: {list(df.columns)}')
    print()
    print(df.groupby(['direction', 'stop'])['boardings'].describe().round(1))
    df.to_csv('./preprocessed.csv', index=False, encoding='utf-8-sig')
    print('\n preprocessed.csv 저장 완료')
