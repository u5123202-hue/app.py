import streamlit as st
import pandas as pd
import numpy as np
import streamlit.components.v1 as components
import json
import os
import base64
import time

# --- 0. 프리셋 관리 함수 ---
PRESET_FILE = "search_presets.json"

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

# --- 2. 데이터 로드 (원본 로직 유지) ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv('부동산 매물 정리.csv', encoding='utf-8')
        df.columns = df.columns.str.strip()
        # 필수 컬럼 결측 제거 및 숫자 변환
        for col in ['보증금', '월세', '관리비', '평수', '위도', '경도', '총_시간(분)']:
            if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df['관리비'] = df['관리비'].fillna(0)
        df['위도'] = df['위도'].fillna(37.375)
        df['경도'] = df['경도'].fillna(126.632)
        df['향'] = df['향'].fillna('')
        df['종류'] = df['종류'].fillna('기타')
        df['url 주소'] = df['url 주소'].fillna('')
        df['월세_관리비_합'] = df['월세'].fillna(0) + df['관리비'].fillna(0)
        
        option_cols = ['에어컨', '냉장고', '세탁기', '인덕션', '엘리베이터', '신발장', '옷장', '베란다', '싱크대']
        existing_option_cols = [col for col in option_cols if col in df.columns]
        
        # 기본 점수 산출 로직
        df['시설점수'] = (df[existing_option_cols].replace({'O':1, 'ㅇ':1, '1':1, '1.0':1}).fillna(0).mean(axis=1) * 10) if existing_option_cols else 5.0
        
        def min_max_score(series, invert=False):
            mi, ma = series.min(), series.max()
            if mi == ma: return series.apply(lambda x: 5.0)
            res = (series - mi) / (ma - mi) * 10
            return 10 - res if invert else res

        df['가격점수'] = (min_max_score(df['월세_관리비_합'], True) * 0.7) + (min_max_score(df['보증금'], True) * 0.3)
        df['크기점수'] = min_max_score(df['평수'].clip(upper=25.0))
        df['통학점수'] = min_max_score(df['총_시간(분)'], True)
        
        return df, existing_option_cols
    except Exception as e:
        st.error(f"데이터 로드 에러: {e}")
        return pd.DataFrame(), []

df, option_cols = load_data()

# --- 3. 프리셋 적용 로직 ---
presets = load_presets()
st.sidebar.header("📍 프리셋 설정")
selected_preset_name = st.sidebar.selectbox("저장된 프리셋 불러오기", ["선택 안 함"] + list(presets.keys()))

# 프리셋 선택 시 세션 상태 업데이트
if selected_preset_name != "선택 안 함" and 'last_preset' not in st.session_state or st.session_state.get('last_preset') != selected_preset_name:
    p = presets[selected_preset_name]
    st.session_state['sel_types'] = p.get('types')
    st.session_state['max_dep'] = p.get('max_dep')
    st.session_state['max_bud'] = p.get('max_bud')
    st.session_state['w_price'] = p.get('w_price')
    st.session_state['w_opt'] = p.get('w_opt')
    st.session_state['w_size'] = p.get('w_size')
    st.session_state['w_commute'] = p.get('w_commute')
    st.session_state['last_preset'] = selected_preset_name
    st.rerun()

# --- 4. 사이드바 필터 ---
st.sidebar.divider()
selected_types = st.sidebar.multiselect("매물 종류", options=df['종류'].unique(), default=st.session_state.get('sel_types', list(df['종류'].unique())), key='sel_types')
max_deposit = st.sidebar.slider("최대 보증금 (만원)", 0, 1000, st.session_state.get('max_dep', 1000), 50, key='max_dep')
max_budget = st.sidebar.slider("희망 예산 (월세+관리비)", 0, 150, st.session_state.get('max_bud', 70), 5, key='max_bud')

with st.sidebar.expander("중요도 설정"):
    w_price = st.slider("가격", 0, 10, st.session_state.get('w_price', 5), key='w_price')
    w_option = st.slider("시설", 0, 10, st.session_state.get('w_opt', 5), key='w_opt')
    w_size = st.slider("크기", 0, 10, st.session_state.get('w_size', 5), key='w_size')
    w_commute = st.slider("통학", 0, 10, st.session_state.get('w_commute', 5), key='w_commute')

# 프리셋 저장 UI
new_name = st.sidebar.text_input("새 프리셋 이름 저장")
if st.sidebar.button("💾 설정 저장"):
    if new_name:
        save_preset(new_name, {
            "types": selected_types, "max_dep": max_deposit, "max_bud": max_budget,
            "w_price": w_price, "w_opt": w_option, "w_size": w_size, "w_commute": w_commute
        })
        st.rerun()

# --- 5. 데이터 계산 ---
budget_limit = max_budget * 10000
filtered_df = df[ (df['종류'].isin(selected_types)) & (df['보증금'] <= max_deposit * 10000) & (df['월세_관리비_합'] <= budget_limit + 50000) ].copy()

total_w = w_price + w_option + w_size + w_commute
if total_w > 0:
    filtered_df['최종점수'] = (
        (filtered_df['가격점수'] * w_price + filtered_df['시설점수'] * w_option + 
         filtered_df['크기점수'] * w_size + filtered_df['통학점수'] * w_commute) / total_w
    ).round(1)
else: filtered_df['최종점수'] = 0.0

result_df = filtered_df.sort_values('최종점수', ascending=False).reset_index(drop=True)

# --- 6. 지도 렌더링 함수 (안정성 강화) ---
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
    map_id = f"map_{int(time.time())}" # 매번 새로운 ID 부여하여 강제 갱신
    
    map_html = f"""
    <div id="{map_id}" style="width:100%;height:400px;border-radius:10px;"></div>
    <script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_API_KEY}&libraries=services&autoload=false"></script>
    <script>
        (function() {{
            var interval = setInterval(function() {{
                if (window.kakao && window.kakao.maps) {{
                    clearInterval(interval);
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

# --- 7. 메인 화면 ---
st.title("ROOMINU - 맞춤형 자취방 찾기")
if not result_df.empty:
    st.subheader("매물 위치 확인")
    render_kakao_map(result_df)
    
    # TOP 3 카드 및 리스트 출력 (생략된 기존 UI 코드 그대로 붙여넣으시면 됩니다)
    st.dataframe(result_df[['최종점수', '주소', '종류', '평수', '월세_관리비_합', 'url 주소']], hide_index=True)
else:
    st.warning("조건에 맞는 매물이 없습니다.")
