import pandas as pd
from geopy.geocoders import Nominatim
import time

# 1. 데이터 불러오기 (파일명과 인코딩 확인 필수!)
input_file = '부동산 매물 정리.csv'
df = pd.read_csv(input_file, encoding='utf-8')

# 2. 지오코더 설정 (무료 서비스)
geolocator = Nominatim(user_agent="my_incheon_app")


def get_coords(address):
    """주소를 받아 위도, 경도를 반환하는 함수"""
    if pd.isna(address) or address == "":
        return None, None
    try:
        # 검색 확률을 높이기 위해 주소 앞에 '인천 '을 붙여주면 더 정확합니다.
        location = geolocator.geocode(address)
        if location:
            return location.latitude, location.longitude
    except:
        pass

    # 무료 API 보호를 위해 1초 대기 (매우 중요!)
    time.sleep(1)
    return None, None


# 3. 새로운 컬럼 추가 (주소 컬럼 바로 옆에 위치시키기 위해 인덱스 활용)
print("🚀 좌표 변환 시작... (데이터 양에 따라 시간이 걸릴 수 있습니다)")

# 위도, 경도 값 계산
coords = df['주소'].apply(get_coords)
df['위도'], df['경도'] = zip(*coords)

# 4. 컬럼 순서 재배치 (선택 사항: 주소 바로 옆으로 이동)
# 주소 컬럼의 위치를 찾아서 그 뒤에 삽입합니다.
cols = df.columns.tolist()
addr_idx = cols.index('주소')
# 주소 뒤에 위도, 경도가 오도록 순서 변경
new_col_order = cols[:addr_idx + 1] + ['위도', '경도'] + [c for c in cols[addr_idx + 1:] if c not in ['위도', '경도']]
df = df[new_col_order]

# 5. 결과 저장
output_file = '매물양식_좌표추가.csv'
df.to_csv(output_file, index=False, encoding='utf-8')

print(f"✅ 완료! '{output_file}' 파일이 생성되었습니다.")