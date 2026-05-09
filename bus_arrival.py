import requests
import urllib.parse
from typing import Optional

from config import PUBLIC_DATA_API_KEY as API_KEY
ROUTE_ID = '200000149'   # 서울 버스 API의 7790수원 노선 ID
BASE_URL = 'http://ws.bus.go.kr/api/rest'

# getArrInfoByRouteAll 테스트로 확인한 정류장별 arsId
ARS_IDS = {
    '효행초등학교정문': '55244',
    '아이파크정문':     '55250',
    '신명아파트':       '55246',
    '수원대입구':       '55744',
    '사당역9번출구앞':  '20253',
}

ALL_STOPS     = list(ARS_IDS.keys())
DEPART_STOPS  = ['효행초등학교정문', '아이파크정문', '신명아파트', '수원대입구']
ARRIVE_STOP   = '사당역9번출구앞'


def _fetch_all_arrivals() -> dict:
    """노선 전체 도착 정보를 한 번에 가져와 arsId → 도착 정보 dict 반환"""
    params = urllib.parse.urlencode({'busRouteId': ROUTE_ID, 'resultType': 'json'})
    url    = f'{BASE_URL}/arrive/getArrInfoByRouteAll?serviceKey={API_KEY}&{params}'
    r      = requests.get(url, timeout=10)
    r.raise_for_status()
    items  = r.json().get('msgBody', {}).get('itemList', [])
    return {item['arsId']: item for item in items}


def _parse_arrmsg(msg: str) -> Optional[int]:
    """'3분00초 후 [2번째 전]' → 3, '곧 도착' → 0, 그 외 → None"""
    if not msg:
        return None
    if '곧 도착' in msg:
        return 0
    if '분' in msg:
        try:
            return int(msg.split('분')[0].strip())
        except ValueError:
            pass
    return None


def get_arrival(stop_name: str) -> dict:
    ars_id = ARS_IDS.get(stop_name)
    if not ars_id:
        return {'stop': stop_name, 'error': f'알 수 없는 정류장: {stop_name}'}

    try:
        lookup = _fetch_all_arrivals()
        item   = lookup.get(ars_id)
        if not item:
            return {'stop': stop_name, 'next1_min': None, 'next2_min': None}

        msg1 = item.get('arrmsg1', '')
        msg2 = item.get('arrmsg2', '')
        return {
            'stop':      stop_name,
            'next1_min': _parse_arrmsg(msg1),
            'next2_min': _parse_arrmsg(msg2),
            'next1_msg': msg1,
            'next2_msg': msg2,
        }
    except Exception as e:
        return {'stop': stop_name, 'next1_min': None, 'next2_min': None, 'error': str(e)}


def get_all_arrivals() -> list:
    try:
        lookup  = _fetch_all_arrivals()
        results = []
        for stop in ALL_STOPS:
            ars_id = ARS_IDS[stop]
            item   = lookup.get(ars_id)
            if not item:
                results.append({'stop': stop, 'next1_min': None, 'next2_min': None})
                continue
            msg1 = item.get('arrmsg1', '')
            msg2 = item.get('arrmsg2', '')
            results.append({
                'stop':      stop,
                'next1_min': _parse_arrmsg(msg1),
                'next2_min': _parse_arrmsg(msg2),
                'next1_msg': msg1,
                'next2_msg': msg2,
            })
        return results
    except Exception as e:
        return [{'stop': s, 'next1_min': None, 'next2_min': None, 'error': str(e)} for s in ALL_STOPS]
