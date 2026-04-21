import streamlit as st
import pandas as pd
import numpy as np
import streamlit.components.v1 as components
import json
import os
import base64
import time

# --- 0. 프리셋 관리 함수 ---
PRESET_FILE = "room_presets.json"

def load_presets():
    if os.path.exists(PRESET_FILE):
        try:
            with open(PRESET_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return {}
    return {}

def save_preset(name, settings):
    presets = load_presets()
    presets[name] = settings
    with open(PRESET_FILE, "w", encoding="utf-8") as f:
        json.dump(presets, f, ensure_ascii=False, indent=4)

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="ROOMINU", layout="wide")

# --- KAKAO MAP API KEY 설정 ---
KAKAO_API_KEY = "853a71f8261b3dccfd8c6b6e1879d3c4"

# --- 2. 데이터 로드 및 전처리 ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv('부동산 매물 정리.csv', encoding='utf-8')
        df.columns = df.columns.str.strip()
        
        # 필수 컬럼 처리
        numeric_cols = ['보증금', '월세', '관리비', '평수', '위도', '경도', '총_시간(분)']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df['관리비'] = df['관리비'].fillna(0)
        df['위도'] = df['위도'].fillna(37.375)
        df['경도'] = df['경도'].fillna(126.632)
        df['종류'] = df['종류'].fillna('기타')
        df['월세_관리비_합'] = df['월세'].fillna(0) + df['관리비'].fillna(0)
        
        # 옵션 컬럼
        option_cols = ['에어컨', '냉장고', '세탁기', '인덕션', '엘리베이터', '신발장', '옷장', '베란다', '싱크대']
        existing_option_cols = [col for col in option_cols if col in df.columns]
        
        # 기본 점수 미리 계산
        def min_max(s, inv=False):
            if s.min() == s.max(): return 5.0
            res = (s - s.min()) / (s.max() - s.min()) * 10
            return 10 - res if inv else res

        df['가격점수'] = (min_max(df['월세_관리비_합'], True) * 0.7) + (min_max(df['보증금'], True) * 0.3)
        df['시설점수'] = df[existing_option_cols].replace({'O':1,'ㅇ':1,'1':1,'1.0':1}).fillna(0).mean(axis=1)*10 if existing_option_cols else 5.0
        df['크기점수'] = min_max(df['평수'].clip(upper=25.0))
        df['통학점수'] = min_max(df['총_시간(분)'], True) if '총_시간(분)' in df.columns else 5.0
        
        return df, existing_option_cols
    except Exception as e:
        st.error(f"데이터 로드 에러: {e}")
        return pd.DataFrame(), []

df, option_cols = load_data()

# --- 3. 프리셋 로직 (사이드바 최상단) ---
presets = load_presets()
st.sidebar.header("📍 검색 프리셋")
preset_names = ["선택 안 함"] + list(presets.keys())
selected_preset = st.sidebar.selectbox("저장된 설정 불러오기", preset_names)

# 프리셋 로드 시 세션 상태 업데이트 (KeyError 방지를 위해 기본값 설정)
if selected_preset != "선택 안 함":
    p = presets[selected_preset]
    st.session_state['sel_types'] = p.get('types', [])
    st.session_state['max_dep'] = p.get('max_dep', 1000)
    st.session_state['max_bud'] = p.get('max_bud', 70)
    st.session_state['w_p'] = p.get('w_p', 5)
    st.session_state['w_o'] = p.get('w_o', 5)
    st.session_state['w_s'] = p.get('w_s', 5)
    st.session_state['w_c'] = p.get('w_c', 5)

# --- 4. 검색 필터 UI ---
st.sidebar.divider()
selected_types = st.sidebar.multiselect("매물 종류", options=df['종류'].unique(), key='sel_types')
max_deposit = st.sidebar.slider("최대 보증금 (만원)", 0, 1000, key='max_dep', step=50)
max_budget = st.sidebar.slider("희망 예산 (월세+관리비)", 0, 150, key='max_bud', step=5)

with st.sidebar.expander("중요도 설정"):
    w_p = st.slider("가격", 0, 10, key='w_p')
    w_o = st.slider("시설", 0, 10, key='w_o')
    w_s = st.slider("크기", 0, 10, key='w_s')
    w_c = st.slider("통학", 0, 10, key='w_c')

# 프리셋 저장 버튼
save_name = st.sidebar.text_input("현재 설정 저장 이름")
if st.sidebar.button("💾 프리셋 저장"):
    if save_name:
        save_preset(save_name, {
            "types": selected_types, "max_dep": max_deposit, "max_bud": max_budget,
            "w_p": w_p, "w_o": w_o, "w_s": w_s, "w_c": w_c
        })
        st.rerun()

# --- 5. 필터링 및 점수 계산 ---
# 최종 점수 컬럼 초기화 (KeyError 방지)
filtered_df = df.copy()
filtered_df['최종점수'] = 0.0

if selected_types:
    filtered_df = filtered_df[filtered_df['종류'].isin(selected_types)]

budget_limit = max_budget * 10000
HIDDEN_FLEX = 50000
filtered_df = filtered_df[
    (filtered_df['보증금'] <= max_deposit * 10000) & 
    (filtered_df['월세_관리비_합'] <= budget_limit + HIDDEN_FLEX)
].copy()

# 최종 점수 계산 로직
total_w = w_p + w_o + w_s + w_c
if total_w > 0 and not filtered_df.empty:
    filtered_df['기본점수'] = (
        (filtered_df['가격점수'] * w_p) + (filtered_df['시설점수'] * w_o) + 
        (filtered_df['크기점수'] * w_s) + (filtered_df['통학점수'] * w_c)
    ) / total_w
    
    over_amount = (filtered_df['월세_관리비_합'] - budget_limit).clip(lower=0) / 10000
    penalty = (over_amount ** 2) * 0.05
    filtered_df['최종점수'] = (filtered_df['기본점수'] - penalty).clip(0, 10).round(1)

result_df = filtered_df.sort_values('최종점수', ascending=False).reset_index(drop=True)

# --- 6. 지도 렌더링 함수 (지도가 안보이는 문제 해결) ---
def render_kakao_map(data):
    center_lat = data['위도'].mean() if not data.empty else 37.375
    center_lng = data['경도'].mean() if not data.empty else 126.632
    
    marker_list = []
    for _, row in data.iterrows():
        marker_list.append({
            "lat": float(row['위도']), "lng": float(row['경도']),
            "content": f'<div style="padding:5px;font-size:12px;color:black;"><b>{row["최종점수"]}점</b><br>{int(row["월세_관리비_합"]/10000)}만원</div>'
        })
    
    markers_json = json.dumps(marker_list, ensure_ascii=False)
    unique_map_id = f"map_{int(time.time() * 1000)}" # 고유 ID 생성
    
    map_html = f"""
    <div id="{unique_map_id}" style="width:100%;height:400px;border-radius:10px;background-color:#eee;"></div>
    <script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_API_KEY}&libraries=services&autoload=false"></script>
    <script>
        (function() {{
            var interval = setInterval(function() {{
                if (window.kakao && window.kakao.maps) {{
                    clearInterval(interval);
                    window.kakao.maps.load(function() {{
                        var container = document.getElementById('{unique_map_id}');
                        var map = new kakao.maps.Map(container, {{
                            center: new kakao.maps.LatLng({center_lat}, {center_lng}),
                            level: 5
                        }});
                        var positions = {markers_json};
                        positions.forEach(function(pos) {{
                            var marker = new kakao.maps.Marker({{ map: map, position: new kakao.maps.LatLng(pos.lat, pos.lng) }});
                            var infowindow = new kakao.maps.InfoWindow({{ content: pos.content }});
                            kakao.maps.event.addListener(marker, 'mouseover', function() {{ infowindow.open(map, marker); }});
                            kakao.maps.event.addListener(marker, 'mouseout', function() {{ infowindow.close(); }});
                        }});
                    }});
                }}
            }}, 100);
        }})();
    </script>
    """
    components.html(map_html, height=420)

# --- 7. 메인 화면 출력 ---
st.title("ROOMINU")
if not result_df.empty:
    st.subheader("매물 위치 확인")
    render_kakao_map(result_df)
    
    st.divider()
    st.subheader("추천 매물 리스트")
    st.dataframe(result_df[['최종점수', '주소', '종류', '평수', '월세_관리비_합', 'url 주소']], hide_index=True, use_container_width=True)
else:
    st.warning("조건에 맞는 매물이 없습니다.")
