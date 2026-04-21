import streamlit as st
import pandas as pd
import numpy as np
import streamlit.components.v1 as components
import json
import base64
import time

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="ROOMINU", layout="wide")

# --- KAKAO MAP API KEY ---
KAKAO_API_KEY = "853a71f8261b3dccfd8c6b6e1879d3c4"

# --- 2. 데이터 로드 및 전처리 ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv('부동산 매물 정리.csv', encoding='utf-8')
        df.columns = df.columns.str.strip()
        
        # 숫자 데이터 변환 및 결측치 보정
        numeric_cols = ['보증금', '월세', '관리비', '평수', '위도', '경도', '총_시간(분)']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df['관리비'] = df['관리비'].fillna(0)
        df['위도'] = df['위도'].fillna(37.375)
        df['경도'] = df['경도'].fillna(126.632)
        df['월세_관리비_합'] = df['월세'].fillna(0) + df['관리비'].fillna(0)
        
        # 옵션 컬럼 리스트
        option_cols = ['에어컨', '냉장고', '세탁기', '인덕션', '엘리베이터', '신발장', '옷장', '베란다', '싱크대']
        existing_option_cols = [col for col in option_cols if col in df.columns]
        
        # 점수 정규화 함수 (0-10점)
        def min_max(s, inv=False):
            if s.empty or s.min() == s.max(): return 5.0
            res = (s - s.min()) / (s.max() - s.min()) * 10
            return 10 - res if inv else res

        # 기본 항목별 점수 미리 계산
        df['가격점수'] = (min_max(df['월세_관리비_합'], True) * 0.7) + (min_max(df['보증금'], True) * 0.3)
        df['시설점수'] = df[existing_option_cols].replace({'O':1,'ㅇ':1,'1':1,'1.0':1}).fillna(0).mean(axis=1)*10 if existing_option_cols else 5.0
        df['크기점수'] = min_max(df['평수'].clip(upper=25.0))
        df['통학점수'] = min_max(df['총_시간(분)'], True) if '총_시간(분)' in df.columns else 5.0
        
        return df, existing_option_cols
    except Exception as e:
        st.error(f"데이터 로드 중 오류가 발생했습니다: {e}")
        return pd.DataFrame(), []

df, option_cols = load_data()

# --- 3. 사이드바 필터 UI ---
st.sidebar.header("🔍 검색 필터")

selected_types = st.sidebar.multiselect("매물 종류", options=df['종류'].unique() if not df.empty else [])
max_deposit = st.sidebar.slider("최대 보증금 (만원)", 0, 2000, 1000, step=100)
max_budget = st.sidebar.slider("희망 월세+관리비 (만원)", 0, 150, 70, step=5)

st.sidebar.divider()
st.sidebar.subheader("⚖️ 항목별 중요도 가중치")
w_p = st.sidebar.slider("가격(월세/보증금)", 0, 10, 5)
w_o = st.sidebar.slider("옵션 시설", 0, 10, 5)
w_s = st.sidebar.slider("방 크기", 0, 10, 5)
w_c = st.sidebar.slider("통학 시간", 0, 10, 5)

# --- 4. 지역별 가중치 엔진 (이미지 기능 2 반영) ---
def apply_regional_weight(row):
    addr = str(row.get('주소', ''))
    if '송도' in addr: return 1.15  # 송도는 입지 가산점
    if '동춘' in addr: return 1.08
    if '원인재' in addr: return 1.05
    return 1.0

# --- 5. 필터링 및 점수 연산 (KeyError 방어) ---
filtered_df = df.copy()
filtered_df['최종점수'] = 0.0  # 정렬 에러 방지를 위한 초기화

if not filtered_df.empty:
    # 필터 적용
    if selected_types:
        filtered_df = filtered_df[filtered_df['종류'].isin(selected_types)]
    
    budget_limit = max_budget * 10000
    filtered_df = filtered_df[
        (filtered_df['보증금'] <= max_deposit * 10000) & 
        (filtered_df['월세_관리비_합'] <= budget_limit + 50000) # 5만원 오차 허용
    ].copy()

    # 가중치 점수 계산
    total_w = w_p + w_o + w_s + w_c
    if total_w > 0 and not filtered_df.empty:
        filtered_df['기본점수'] = (
            (filtered_df['가격점수'] * w_p) + 
            (filtered_df['시설점수'] * w_o) + 
            (filtered_df['크기점수'] * w_s) + 
            (filtered_df['통학점수'] * w_c)
        ) / total_w
        
        # 지역별 가중치 및 패널티 적용
        filtered_df['지역가중치'] = filtered_df.apply(apply_regional_weight, axis=1)
        over_budget_manwon = (filtered_df['월세_관리비_합'] - budget_limit).clip(lower=0) / 10000
        penalty = (over_budget_manwon ** 2) * 0.05
        
        filtered_df['최종점수'] = (filtered_df['기본점수'] * filtered_df['지역가중치'] - penalty).clip(0, 10).round(1)

# 최종 결과 정렬
result_df = filtered_df.sort_values('최종점수', ascending=False).reset_index(drop=True)

# --- 6. 지도 렌더링 함수 ---
def render_map(data):
    if data.empty: return
    center_lat = data['위도'].mean()
    center_lng = data['경도'].mean()
    
    marker_list = []
    for _, row in data.iterrows():
        marker_list.append({
            "lat": float(row['위도']), "lng": float(row['경도']),
            "content": f'<div style="padding:5px;font-size:12px;color:black;"><b>{row["최종점수"]}점</b><br>{int(row["월세_관리비_합"]/10000)}만</div>'
        })
    
    markers_json = json.dumps(marker_list, ensure_ascii=False)
    map_id = f"map_{int(time.time())}"
    
    map_html = f"""
    <div id="{map_id}" style="width:100%;height:400px;border-radius:12px;background:#f8f9fa;"></div>
    <script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_API_KEY}&libraries=services&autoload=false"></script>
    <script>
        (function() {{
            var checkInterval = setInterval(function() {{
                if (window.kakao && window.kakao.maps) {{
                    clearInterval(checkInterval);
                    window.kakao.maps.load(function() {{
                        var container = document.getElementById('{map_id}');
                        var map = new kakao.maps.Map(container, {{
                            center: new kakao.maps.LatLng({center_lat}, {center_lng}),
                            level: 5
                        }});
                        var positions = {markers_json};
                        positions.forEach(function(pos) {{
                            var marker = new kakao.maps.Marker({{ map: map, position: new kakao.maps.LatLng(pos.lat, pos.lng) }});
                            var iw = new kakao.maps.InfoWindow({{ content: pos.content }});
                            kakao.maps.event.addListener(marker, 'mouseover', function() {{ iw.open(map, marker); }});
                            kakao.maps.event.addListener(marker, 'mouseout', function() {{ iw.close(); }});
                        }});
                    }});
                }}
            }}, 100);
        }})();
    </script>
    """
    components.html(map_html, height=420)

# --- 7. 결과 출력 화면 ---
st.title("🏠 ROOMINU")
st.markdown("---")

if not result_df.empty and result_df['최종점수'].max() > 0:
    st.subheader("📍 매물 위치 분석")
    render_map(result_df)
    
    st.divider()
    
    st.subheader("📊 추천 매물 리스트")
    # 보여줄 컬럼 선별
    cols_to_show = ['최종점수', '주소', '종류', '평수', '월세_관리비_합', 'url 주소']
    st.dataframe(
        result_df[cols_to_show],
        column_config={
            "최종점수": st.column_config.NumberColumn("점수", format="%.1f ⭐"),
            "url 주소": st.column_config.LinkColumn("네이버 링크"),
            "월세_관리비_합": st.column_config.NumberColumn("월세+관리비(원)")
        },
        hide_index=True,
        use_container_width=True
    )
else:
    st.warning("조건에 부합하는 매물이 없습니다. 필터 범위를 넓혀보세요.")
