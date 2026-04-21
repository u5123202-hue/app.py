import streamlit as st
import pandas as pd
import numpy as np
import streamlit.components.v1 as components
import json
import os
import base64

# --- 0. 프리셋 관리 함수 ---
PRESET_FILE = "search_presets.json"

def load_presets():
    if os.path.exists(PRESET_FILE):
        with open(PRESET_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_preset(name, settings):
    presets = load_presets()
    presets[name] = settings
    with open(PRESET_FILE, "w", encoding="utf-8") as f:
        json.dump(presets, f, ensure_ascii=False, indent=4)

def delete_preset(name):
    presets = load_presets()
    if name in presets:
        del presets[name]
        with open(PRESET_FILE, "w", encoding="utf-8") as f:
            json.dump(presets, f, ensure_ascii=False, indent=4)

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="ROOMINU", layout="wide")
st.cache_data.clear()

# --- KAKAO MAP API KEY 설정 ---
KAKAO_API_KEY = "853a71f8261b3dccfd8c6b6e1879d3c4"

# --- 2. 데이터 로드 및 전처리 (기존 로직 유지) ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv('부동산 매물 정리.csv', encoding='utf-8')
        df.columns = df.columns.str.strip()
        # ... (중략: 기존 전처리 코드와 동일)
        required_cols = ['주소', '보증금', '월세', '평수']
        existing_required_cols = [col for col in required_cols if col in df.columns]
        df = df.dropna(subset=existing_required_cols)
        numeric_cols = ['보증금', '월세', '관리비', '평수', '위도', '경도']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        if '총_시간(분)' in df.columns:
             df['총_시간(분)'] = pd.to_numeric(df['총_시간(분)'], errors='coerce')
        else:
            df['총_시간(분)'] = np.nan
        if '관리비' not in df.columns: df['관리비'] = 0
        df['관리비'] = df['관리비'].fillna(0)
        if '위도' not in df.columns: df['위도'] = 37.375
        else: df['위도'] = df['위도'].fillna(37.375)
        if '경도' not in df.columns: df['경도'] = 126.632
        else: df['경도'] = df['경도'].fillna(126.632)
        if '향' not in df.columns: df['향'] = ''
        df['향'] = df['향'].fillna('')
        if '종류' not in df.columns: df['종류'] = '기타'
        df['종류'] = df['종류'].fillna('기타')
        if 'url 주소' not in df.columns: df['url 주소'] = ''
        df['url 주소'] = df['url 주소'].fillna('')
        df['월세_관리비_합'] = df['월세'].fillna(0) + df['관리비'].fillna(0)
        option_cols = ['에어컨', '냉장고', '세탁기', '인덕션', '엘리베이터', '신발장', '옷장', '베란다', '싱크대']
        existing_option_cols = [col for col in option_cols if col in df.columns]
        if len(existing_option_cols) > 0:
            df['시설점수'] = df.apply(lambda row: (sum(1 for col in existing_option_cols if str(row.get(col)).strip().upper() in ['O', 'ㅇ', '1', '1.0']) / len(existing_option_cols)) * 10, axis=1)
        else:
            df['시설점수'] = 5.0
        min_rent, max_rent = df['월세_관리비_합'].min(), df['월세_관리비_합'].max()
        rent_score = 10 - ((df['월세_관리비_합'] - min_rent) / (max_rent - min_rent) * 10) if max_rent != min_rent else 5.0
        min_dep, max_dep = df['보증금'].min(), df['보증금'].max()
        dep_score = 10 - ((df['보증금'] - min_dep) / (max_dep - min_dep) * 10) if max_dep != min_dep else 5.0
        df['가격점수'] = (rent_score * 0.7) + (dep_score * 0.3)
        target_max_size = 25.0
        min_s = df['평수'].min()
        df['크기점수'] = ((df['평수'].clip(upper=target_max_size) - min_s) / (target_max_size - min_s) * 10) if target_max_size != min_s else 5.0
        min_t, max_t = df['총_시간(분)'].min(), df['총_시간(분)'].max()
        df['통학점수'] = 10 - ((df['총_시간(분)'] - min_t) / (max_t - min_t) * 10) if max_t != min_t else 5.0
        return df, existing_option_cols
    except Exception as e:
        st.error(f"데이터 로드 에러: {e}")
        return pd.DataFrame(), []

df, option_cols = load_data()
if df.empty: st.stop()

# --- 3. 사이드바 & 프리셋 UI ---
st.sidebar.header("📍 내 프리셋")

presets = load_presets()
preset_names = list(presets.keys())

# 프리셋 선택 및 불러오기
selected_preset_name = st.sidebar.selectbox("저장된 프리셋 불러오기", ["선택 안 함"] + preset_names)

if selected_preset_name != "선택 안 함":
    p_data = presets[selected_preset_name]
    # 세션 상태 업데이트 (UI 동기화)
    st.session_state['sel_types'] = p_data.get('types', [])
    st.session_state['max_dep'] = p_data.get('max_dep', 1000)
    st.session_state['max_bud'] = p_data.get('max_bud', 70)
    st.session_state['w_price'] = p_data.get('w_price', 5)
    st.session_state['w_opt'] = p_data.get('w_opt', 5)
    st.session_state['w_size'] = p_data.get('w_size', 5)
    st.session_state['w_commute'] = p_data.get('w_commute', 5)

st.sidebar.divider()
st.sidebar.header("검색 필터")

# 필터 위젯 (key 값을 session_state와 연결)
selected_types = st.sidebar.multiselect(
    "매물 종류",
    options=df['종류'].dropna().unique(),
    default=st.session_state.get('sel_types', list(df['종류'].dropna().unique())),
    key='sel_types'
)

with st.sidebar.expander("예산 및 가격 설정", expanded=False):
    max_deposit = st.slider("최대 보증금 (만원)", 0, 1000, st.session_state.get('max_dep', 1000), step=50, key='max_dep')
    max_budget = st.slider("희망 월세+관리비 예산 (만원)", 0, 150, st.session_state.get('max_bud', 70), step=5, key='max_bud')

with st.sidebar.expander("필수 옵션 선택", expanded=False):
    selected_options = []
    for opt in option_cols:
        if st.checkbox(opt, key=f"chk_{opt}"):
            selected_options.append(opt)

with st.sidebar.expander("방향 설정", expanded=False):
    available_directions = [d for d in df['향'].dropna().unique() if str(d).strip() != '' and str(d).strip().lower() != 'nan']
    selected_directions = st.multiselect("방향 선택", options=available_directions, default=available_directions)

st.sidebar.divider()

with st.sidebar.expander("항목별 중요도 설정", expanded=True):
    w_price = st.slider("가격 중요도", 0, 10, st.session_state.get('w_price', 5), key='w_price')
    w_option = st.slider("시설 중요도", 0, 10, st.session_state.get('w_opt', 5), key='w_opt')
    w_size = st.slider("크기 중요도", 0, 10, st.session_state.get('w_size', 5), key='w_size')
    w_commute = st.slider("통학 중요도", 0, 10, st.session_state.get('w_commute', 5), key='w_commute')

# --- 프리셋 저장/삭제 버튼 ---
st.sidebar.divider()
new_preset_name = st.sidebar.text_input("새 프리셋 이름", placeholder="예: 가성비 자취방")
col1, col2 = st.sidebar.columns(2)

if col1.button("💾 현재 설정 저장"):
    if new_preset_name:
        current_settings = {
            "types": selected_types,
            "max_dep": max_deposit,
            "max_bud": max_budget,
            "w_price": w_price,
            "w_opt": w_option,
            "w_size": w_size,
            "w_commute": w_commute
        }
        save_preset(new_preset_name, current_settings)
        st.sidebar.success(f"'{new_preset_name}' 저장 완료!")
        st.rerun()
    else:
        st.sidebar.warning("이름을 입력하세요.")

if col2.button("🗑️ 선택 프리셋 삭제"):
    if selected_preset_name != "선택 안 함":
        delete_preset(selected_preset_name)
        st.sidebar.info("삭제되었습니다.")
        st.rerun()

# --- 4. 필터링 및 계산 (기존 로직 유지) ---
budget_limit = max_budget * 10000
HIDDEN_FLEX_BUDGET = 50000
extended_budget_limit = budget_limit + HIDDEN_FLEX_BUDGET

filtered_df = df.copy()
if selected_types:
    filtered_df = filtered_df[filtered_df['종류'].isin(selected_types)]

filtered_df = filtered_df[
    (filtered_df['월세_관리비_합'] <= extended_budget_limit) &
    (filtered_df['보증금'] <= max_deposit * 10000)
].copy()

if selected_directions:
    filtered_df = filtered_df[filtered_df['향'].isin(selected_directions)].copy()

for opt in selected_options:
    if opt in filtered_df.columns:
        filtered_df = filtered_df[filtered_df[opt].astype(str).str.strip().str.upper().isin(['1', '1.0', 'O', 'ㅇ'])]

total_w = w_price + w_option + w_size + w_commute
if total_w > 0:
    filtered_df['기본점수'] = ((filtered_df['가격점수'] * (w_price / total_w)) + (filtered_df['시설점수'] * (w_option / total_w)) + (filtered_df['크기점수'] * (w_size / total_w)) + (filtered_df['통학점수'] * (w_commute / total_w)))
else:
    filtered_df['기본점수'] = 0.0

filtered_df['예산초과금액'] = (filtered_df['월세_관리비_합'] - budget_limit).clip(lower=0)
over_amount_manwon = filtered_df['예산초과금액'] / 10000
filtered_df['예산패널티'] = (over_amount_manwon ** 2.0) * 0.05
filtered_df['최종점수'] = (filtered_df['기본점수'] - filtered_df['예산패널티']).round(1)
filtered_df['최종점수'] = filtered_df['최종점수'].clip(lower=0, upper=10)
filtered_df['추천태그'] = np.where(filtered_df['예산초과금액'] > 0, "예산을 조금 넘지만 조건이 매우 좋아요!", "")

result_df = filtered_df.sort_values('최종점수', ascending=False).reset_index(drop=True)

# --- 5. 카카오맵 & UI 출력 (기존 로직 유지) ---
# ... (중략: render_kakao_map, get_image_base64, header_html 등 기존 코드와 동일)

# (이하 렌더링 부분 생략 - 원본 코드의 하단부와 동일하게 유지하시면 됩니다.)
def render_kakao_map(data):
    if data.empty: center_lat, center_lng = 37.375, 126.632
    else: center_lat, center_lng = data['위도'].mean(), data['경도'].mean()
    marker_list = []
    for _, row in data.iterrows():
        extra_tag = f"<br><span style='color:#ff6600;font-weight:bold;'>{row['추천태그']}</span>" if row["추천태그"] else ""
        total_time_text = f"{int(row['총_시간(분)'])}분" if pd.notna(row.get('총_시간(분)', np.nan)) else "-"
        marker_list.append({"title": str(row['주소']), "lat": float(row['위도']), "lng": float(row['경도']), "content": f'<div style="padding:5px;font-size:12px;width:200px;color:black;"><b>{row["최종점수"]}점</b> | {row["종류"]}<br>월세+관리비: {int(row["월세_관리비_합"] / 10000)}만원<br>학교까지: {total_time_text}{extra_tag}</div>'})
    markers_json = json.dumps(marker_list, ensure_ascii=False)
    map_html = f"""<div id="map" style="width:100%;height:400px;border-radius:10px;background-color:#eee;"></div><script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_API_KEY}&libraries=services&autoload=false"></script><script>(function() {{ var checkInterval = setInterval(function() {{ if (window.kakao && window.kakao.maps && window.kakao.maps.load) {{ clearInterval(checkInterval); window.kakao.maps.load(function() {{ var container = document.getElementById('map'); var options = {{ center: new kakao.maps.LatLng({center_lat}, {center_lng}), level: 5 }}; var map = new kakao.maps.Map(container, options); var positions = {markers_json}; positions.forEach(function(pos) {{ var marker = new kakao.maps.Marker({{ map: map, position: new kakao.maps.LatLng(pos.lat, pos.lng) }}); var infowindow = new kakao.maps.InfoWindow({{ content: pos.content }}); kakao.maps.event.addListener(marker, 'mouseover', function() {{ infowindow.open(map, marker); }}); kakao.maps.event.addListener(marker, 'mouseout', function() {{ infowindow.close(); }}); }}); }}); }} }}, 100); }})();</script>"""
    return components.html(map_html, height=420)

LOGO_FILE_PATH = "logo_transparent.png"
def get_image_base64(p):
    if not os.path.exists(p): return ""
    with open(p, "rb") as f: return base64.b64encode(f.read()).decode()
logo_base64 = get_image_base64(LOGO_FILE_PATH)

header_html = f"""<div style="background: linear-gradient(90deg, #1E90FF, #00BFFF); padding: 20px 30px; border-radius: 15px; color: white; margin-bottom: 25px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); display: flex; justify-content: space-between; align-items: center;"><div><h1 style="margin: 0; font-size: 50px; font-weight: 900; letter-spacing: -1px;">ROOMINU</h1><p style="margin: 5px 0 0 0; font-size: 15px; opacity: 0.8;">데이터 기반으로 분석한 나만의 맞춤형 자취방을 찾아보세요.</p></div>{" " if logo_base64 == "" else f'<img src="data:image/png;base64,{logo_base64}" style="max-height: 120px; width: auto;"/>'}</div>"""
st.markdown(header_html, unsafe_allow_html=True)

if not result_df.empty:
    st.subheader("매물 위치 확인")
    render_kakao_map(result_df)
    st.divider()
    st.subheader("맞춤형 추천 매물 TOP 3")
    top_cols = st.columns(3)
    for i in range(min(3, len(result_df))):
        row = result_df.iloc[i]
        with top_cols[i]:
            score_color = "#00B36B" if i == 0 else "#31333F"
            tag_html = f'<div style="background-color:#FFF3CD; color:#856404; border-radius:8px; padding:8px 10px; font-size:13px; font-weight:bold; margin-bottom:12px; text-align:center;">{row["추천태그"]}</div>' if row["추천태그"] else ""
            total_time_text = f"{int(row['총_시간(분)'])}분" if pd.notna(row.get('총_시간(분)', np.nan)) else "-"
            card_html = f"""<div style="background-color: #FFFFFF; border: 1px solid #E6E6E6; border-top: 4px solid #FFC107; border-radius: 15px; padding: 20px; text-align: center; box-shadow: 0 4px 8px rgba(0,0,0,0.05); margin-bottom: 10px; min-height: 320px; font-family: Arial, sans-serif;"><div style="color: #FFC107; font-size: 14px; font-weight: bold; margin-bottom: 8px;">{i + 1}위 추천</div><div style="color: {score_color}; font-size: 32px; font-weight: 900; margin-bottom: 15px;">{row['최종점수']} <span style="font-size: 16px; font-weight: normal; color: #888;">/ 10점</span></div>{tag_html}<div style="background-color: #F0F2F6; border-radius: 10px; padding: 12px; margin-bottom: 15px;"><div style="color: #666; font-size: 12px; margin-bottom: 4px;">주소</div><div style="color: #31333F; font-size: 15px; word-break: keep-all;">{row['주소']}</div></div><div style="display: flex; justify-content: space-around; background-color: #F0F2F6; border-radius: 10px; padding: 12px; margin-bottom: 12px;"><div style="color: #31333F; font-size: 15px;"><b>{row['평수']}</b>평</div><div style="color: #31333F; font-size: 15px;"><b>{int(row['보증금'] / 10000)}/{int(row['월세'] / 10000)}</b>만</div></div><div style="font-size:13px; color:#666;">월세+관리비: <b>{int(row['월세_관리비_합'] / 10000)}만원</b><br>예산 초과액: <b>{int(row['예산초과금액'] / 10000)}만원</b><br>학교까지 총 시간: <b>{total_time_text}</b></div></div>"""
            components.html(card_html, height=360)
            if str(row['url 주소']).strip() != "": st.link_button("네이버 부동산 상세보기", row['url 주소'], use_container_width=True)
    st.divider()
    st.subheader("전체 매물 리스트")
    display_df = result_df[['최종점수', '주소', '종류', '평수', '총_시간(분)', '월세_관리비_합', '가격점수', '시설점수', '크기점수', 'url 주소']].copy()
    st.dataframe(display_df, hide_index=True, use_container_width=True)
else:
    st.warning("조건에 맞는 매물이 없습니다. 옵션을 조절해 보세요.")
