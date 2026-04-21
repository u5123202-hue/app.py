import streamlit as st
import pandas as pd
import numpy as np
import streamlit.components.v1 as components
import json
import os
import base64
import time

# --- 0. 프리셋 파일 관리 함수 ---
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
st.cache_data.clear()

# --- KAKAO MAP API KEY 설정 ---
KAKAO_API_KEY = "853a71f8261b3dccfd8c6b6e1879d3c4"

# --- 2. 데이터 로드 및 전처리 (원본 로직 유지) ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv('부동산 매물 정리.csv', encoding='utf-8')
        df.columns = df.columns.str.strip()
        required_cols = ['주소', '보증금', '월세', '평수']
        df = df.dropna(subset=[col for col in required_cols if col in df.columns])
        
        numeric_cols = ['보증금', '월세', '관리비', '평수', '위도', '경도', '총_시간(분)']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df['관리비'] = df['관리비'].fillna(0)
        df['위도'] = df['위도'].fillna(37.375)
        df['경도'] = df['경도'].fillna(126.632)
        df['향'] = df['향'].fillna('')
        df['종류'] = df['종류'].fillna('기타')
        df['url 주소'] = df['url 주소'].fillna('')
        df['월세_관리비_합'] = df['월세'].fillna(0) + df['관리비'].fillna(0)
        
        option_cols = ['에어컨', '냉장고', '세탁기', '인덕션', '엘리베이터', '신발장', '옷장', '베란다', '싱크대']
        existing_option_cols = [col for col in option_cols if col in df.columns]
        
        # 시설 점수 산출
        if existing_option_cols:
            df['시설점수'] = df[existing_option_cols].replace({'O':1, 'ㅇ':1, '1':1, '1.0':1}).fillna(0).mean(axis=1) * 10
        else:
            df['시설점수'] = 5.0

        # 가격/크기/통학 점수 (Min-Max Scaling)
        def get_score(series, invert=False):
            mi, ma = series.min(), series.max()
            if mi == ma: return 5.0
            score = (series - mi) / (ma - mi) * 10
            return 10 - score if invert else score

        df['가격점수'] = (get_score(df['월세_관리비_합'], True) * 0.7) + (get_score(df['보증금'], True) * 0.3)
        df['크기점수'] = get_score(df['평수'].clip(upper=25.0))
        df['통학점수'] = get_score(df['총_시간(분)'], True)
        
        return df, existing_option_cols
    except Exception as e:
        st.error(f"데이터 로드 에러: {e}")
        return pd.DataFrame(), []

df, option_cols = load_data()
if df.empty: st.stop()

# --- 3. 사이드바 및 프리셋 로직 ---
st.sidebar.header("📍 검색 프리셋")
presets = load_presets()
preset_names = ["선택 안 함"] + list(presets.keys())
selected_preset = st.sidebar.selectbox("저장된 필터 불러오기", preset_names)

# 프리셋 로드 시 세션 상태 업데이트
if selected_preset != "선택 안 함":
    p = presets[selected_preset]
    st.session_state['sel_types'] = p.get('types', [])
    st.session_state['max_dep'] = p.get('max_dep', 1000)
    st.session_state['max_bud'] = p.get('max_bud', 70)
    st.session_state['sel_opts'] = p.get('opts', [])
    st.session_state['sel_dirs'] = p.get('dirs', [])
    st.session_state['w_p'] = p.get('w_p', 5)
    st.session_state['w_o'] = p.get('w_o', 5)
    st.session_state['w_s'] = p.get('w_s', 5)
    st.session_state['w_c'] = p.get('w_c', 5)

st.sidebar.divider()
st.sidebar.header("검색 필터")

selected_types = st.sidebar.multiselect("매물 종류", options=df['종류'].unique(), key='sel_types')
max_deposit = st.sidebar.slider("최대 보증금 (만원)", 0, 1000, key='max_dep', step=50)
max_budget = st.sidebar.slider("희망 월세+관리비 (만원)", 0, 150, key='max_bud', step=5)

# 옵션 선택 (Checkbox 그룹화)
selected_options = []
with st.sidebar.expander("필수 옵션", expanded=False):
    for opt in option_cols:
        if st.checkbox(opt, key=f"opt_{opt}", value=(opt in st.session_state.get('sel_opts', []))):
            selected_options.append(opt)

available_directions = [d for d in df['향'].unique() if str(d).strip()]
selected_directions = st.sidebar.multiselect("방향 설정", options=available_directions, key='sel_dirs')

with st.sidebar.expander("중요도 설정", expanded=False):
    w_price = st.slider("가격 중요도", 0, 10, key='w_p')
    w_option = st.slider("시설 중요도", 0, 10, key='w_o')
    w_size = st.slider("크기 중요도", 0, 10, key='w_s')
    w_commute = st.slider("통학 중요도", 0, 10, key='w_c')

# 프리셋 저장
st.sidebar.divider()
new_preset_name = st.sidebar.text_input("현재 설정 저장 이름")
if st.sidebar.button("💾 프리셋 저장"):
    if new_preset_name:
        save_preset(new_preset_name, {
            "types": selected_types, "max_dep": max_deposit, "max_bud": max_budget,
            "opts": selected_options, "dirs": selected_directions,
            "w_p": w_price, "w_o": w_option, "w_s": w_size, "w_c": w_commute
        })
        st.success(f"'{new_preset_name}' 저장 완료!")
        st.rerun()

# --- 4. 필터링 및 계산 ---
budget_limit = max_budget * 10000
HIDDEN_FLEX = 50000
filtered_df = df.copy()

if selected_types: filtered_df = filtered_df[filtered_df['종류'].isin(selected_types)]
filtered_df = filtered_df[(filtered_df['보증금'] <= max_deposit * 10000) & (filtered_df['월세_관리비_합'] <= budget_limit + HIDDEN_FLEX)]
if selected_directions: filtered_df = filtered_df[filtered_df['향'].isin(selected_directions)]
for opt in selected_options:
    filtered_df = filtered_df[filtered_df[opt].astype(str).str.upper().isin(['1', '1.0', 'O', 'ㅇ'])]

# 최종 점수 계산
total_w = w_price + w_option + w_size + w_commute
if total_w > 0:
    filtered_df['기본점수'] = (filtered_df['가격점수']*w_price + filtered_df['시설점수']*w_option + filtered_df['크기점수']*w_size + filtered_df['통학점수']*w_commute) / total_w
    filtered_df['예산패널티'] = ((filtered_df['월세_관리비_합'] - budget_limit).clip(lower=0) / 10000)**2 * 0.05
    filtered_df['최종점수'] = (filtered_df['기본점수'] - filtered_df['예산패널티']).clip(0, 10).round(1)
    filtered_df['추천태그'] = np.where(filtered_df['월세_관리비_합'] > budget_limit, "예산 초과지만 조건 우수", "")

result_df = filtered_df.sort_values('최종점수', ascending=False).reset_index(drop=True)

# --- 5. 지도 렌더링 (ID 중복 해결 버전) ---
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
    # 💥 핵심: 지도가 안 보이지 않도록 매번 고유한 ID를 부여합니다.
    unique_map_id = f"map_{int(time.time() * 1000)}"
    
    map_html = f"""
    <div id="{unique_map_id}" style="width:100%;height:400px;border-radius:10px;background-color:#eee;"></div>
    <script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_API_KEY}&libraries=services&autoload=false"></script>
    <script>
        (function() {{
            var checkKakao = setInterval(function() {{
                if (window.kakao && window.kakao.maps) {{
                    clearInterval(checkKakao);
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

# --- 6. 결과 출력 (기존 로직 유지) ---
st.markdown("<h1>ROOMINU</h1>", unsafe_allow_html=True) # 헤더 생략 (기존 코드의 디자인 사용 가능)

if not result_df.empty:
    st.subheader("매물 위치 확인")
    render_kakao_map(result_df)
    
    st.divider()
    st.subheader("추천 매물 리스트")
    st.dataframe(result_df[['최종점수', '주소', '종류', '평수', '월세_관리비_합', 'url 주소']], use_container_width=True)
else:
    st.warning("조건에 맞는 매물이 없습니다.")
