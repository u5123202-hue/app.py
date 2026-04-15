import streamlit as st
import pandas as pd
import numpy as np
import streamlit.components.v1 as components
import json
import os
import base64

st.cache_data.clear()

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

        # 필수 컬럼 결측 제거
        required_cols = ['주소', '보증금', '월세', '평수']
        existing_required_cols = [col for col in required_cols if col in df.columns]
        df = df.dropna(subset=existing_required_cols)

        # 일반 숫자 컬럼 처리
        numeric_cols = ['보증금', '월세', '관리비', '평수', '위도', '경도']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # 시간 컬럼 처리
        if '총_시간(분)' in df.columns:
             df['총_시간(분)'] = pd.to_numeric(df['총_시간(분)'], errors='coerce')
        else:
            df['총_시간(분)'] = np.nan

        # 기본 컬럼 보정
        if '관리비' not in df.columns:
            df['관리비'] = 0
        df['관리비'] = df['관리비'].fillna(0)

        if '위도' not in df.columns:
            df['위도'] = 37.375
        else:
            df['위도'] = df['위도'].fillna(37.375)

        if '경도' not in df.columns:
            df['경도'] = 126.632
        else:
            df['경도'] = df['경도'].fillna(126.632)

        if '향' not in df.columns:
            df['향'] = ''
        df['향'] = df['향'].fillna('')

        if '종류' not in df.columns:
            df['종류'] = '기타'
        df['종류'] = df['종류'].fillna('기타')

        if 'url 주소' not in df.columns:
            df['url 주소'] = ''
        df['url 주소'] = df['url 주소'].fillna('')

        # --- [가격 로직: 보증금/월세 개별 산정] ---
        # 1. 월세 + 관리비 합계 계산
        df['월세_관리비_합'] = df['월세'].fillna(0) + df['관리비'].fillna(0)

        # 2. 보증금 점수 계산 (낮을수록 고득점)
        min_dep = df['보증금'].min()
        max_dep = df['보증금'].max()
        if pd.notna(min_dep) and pd.notna(max_dep) and max_dep != min_dep:
            df['보증금점수'] = 10 - ((df['보증금'] - min_dep) / (max_dep - min_dep) * 10)
        else:
            df['보증금점수'] = 5.0

        # 3. 월세+관리비 점수 계산 (낮을수록 고득점)
        min_rent_sum = df['월세_관리비_합'].min()
        max_rent_sum = df['월세_관리비_합'].max()
        if pd.notna(min_rent_sum) and pd.notna(max_rent_sum) and max_rent_sum != min_rent_sum:
            df['월세점수'] = 10 - ((df['월세_관리비_합'] - min_rent_sum) / (max_rent_sum - min_rent_sum) * 10)
        else:
            df['월세점수'] = 5.0

        # 4. 최종 가격점수 통합 (월세 비중 70%, 보증금 비중 30%)
        df['가격점수'] = (df['월세점수'] * 0.7) + (df['보증금점수'] * 0.3)
        df['가격점수'] = df['가격점수'].clip(lower=0, upper=10)

        # 옵션 컬럼 및 시설점수
        option_cols = ['에어컨', '냉장고', '세탁기', '인덕션', '엘리베이터', '신발장', '옷장', '베란다', '싱크대']
        existing_option_cols = [col for col in option_cols if col in df.columns]

        if len(existing_option_cols) > 0:
            df['시설점수'] = df.apply(
                lambda row: (sum(1 for col in existing_option_cols if str(row.get(col)).strip().upper() in ['O', 'ㅇ', '1', '1.0']) / len(existing_option_cols)) * 10,
                axis=1
            )
        else:
            df['시설점수'] = 5.0

        # 크기점수
        target_max_size = 25.0
        min_s = df['평수'].min()
        if pd.notna(min_s) and target_max_size != min_s:
            df['크기점수'] = ((df['평수'].clip(upper=target_max_size) - min_s) / (target_max_size - min_s) * 10)
            df['크기점수'] = df['크기점수'].clip(lower=0, upper=10)
        else:
            df['크기점수'] = 5.0

        # 통학점수
        min_t = df['총_시간(분)'].min()
        max_t = df['총_시간(분)'].max()
        if pd.notna(min_t) and pd.notna(max_t) and max_t != min_t:
            df['통학점수'] = 10 - ((df['총_시간(분)'] - min_t) / (max_t - min_t) * 10)
            df['통학점수'] = df['통학점수'].clip(lower=0, upper=10)
        else:
            df['통학점수'] = 5.0

        return df, existing_option_cols

    except Exception as e:
        st.error(f"데이터 로드 에러: {e}")
        return pd.DataFrame(), []

df, option_cols = load_data()
if df.empty:
    st.stop()

# --- 3. 사이드바 ---
st.sidebar.header("검색 필터")

selected_types = st.sidebar.multiselect(
    "매물 종류",
    options=df['종류'].dropna().unique(),
    default=list(df['종류'].dropna().unique())
)

with st.sidebar.expander("예산 및 가격 설정", expanded=True):
    # [수정] 보증금 슬라이더: 0~1000만원, 1000 선택 시 무제한
    max_deposit_val = st.slider("최대 보증금 (만원)", 0, 1000, 1000, step=50, help="1000만원을 선택하면 보증금 제한 없이 모든 매물을 보여줍니다.")
    if max_deposit_val >= 1000:
        st.caption("현재: **보증금 무제한**")
    else:
        st.caption(f"현재: **{max_deposit_val}만원 이하**")

    max_budget = st.slider("희망 월세+관리비 예산 (만원)", 0, 150, 70, step=5)

with st.sidebar.expander("필수 옵션 선택", expanded=False):
    selected_options = [opt for opt in option_cols if st.checkbox(opt, key=f"chk_{opt}")]

with st.sidebar.expander("방향 설정", expanded=False):
    available_directions = [d for d in df['향'].dropna().unique() if str(d).strip() not in ['', 'nan', 'NaN']]
    selected_directions = st.multiselect("원하는 방향", options=available_directions, default=available_directions)

st.sidebar.divider()

with st.sidebar.expander("항목별 중요도 설정", expanded=False):
    w_price = st.slider("가격 중요도", 0, 10, 5)
    w_option = st.slider("시설 중요도", 0, 10, 5)
    w_size = st.slider("크기 중요도", 0, 10, 5)
    w_commute = st.slider("통학 중요도", 0, 10, 5)

with st.sidebar.expander("예산 초과 패널티 설정", expanded=False):
    over_budget_penalty_weight = st.slider("패널티 강도", 0.0, 5.0, 1.0, 0.1)

# --- 4. 필터링 및 계산 ---
budget_limit = max_budget * 10000
extended_budget_limit = budget_limit * 1.2

filtered_df = df.copy()

if selected_types:
    filtered_df = filtered_df[filtered_df['종류'].isin(selected_types)]

# [수정] 보증금 필터링 적용 (1000 미만일 때만 작동)
if max_deposit_val < 1000:
    filtered_df = filtered_df[filtered_df['보증금'] <= max_deposit_val * 10000]

filtered_df = filtered_df[filtered_df['월세_관리비_합'] <= extended_budget_limit].copy()

if selected_directions:
    filtered_df = filtered_df[filtered_df['향'].isin(selected_directions)].copy()

for opt in selected_options:
    filtered_df = filtered_df[filtered_df[opt].astype(str).str.strip().str.upper().isin(['1', '1.0', 'O', 'ㅇ'])]

# 최종 점수 계산
total_w = w_price + w_option + w_size + w_commute
if total_w > 0:
    filtered_df['기본점수'] = ((filtered_df['가격점수'] * (w_price / total_w)) + 
                             (filtered_df['시설점수'] * (w_option / total_w)) + 
                             (filtered_df['크기점수'] * (w_size / total_w)) + 
                             (filtered_df['통학점수'] * (w_commute / total_w)))
else:
    filtered_df['기본점수'] = 0.0

filtered_df['예산초과금액'] = (filtered_df['월세_관리비_합'] - budget_limit).clip(lower=0)
filtered_df['예산패널티'] = (filtered_df['예산초과금액'] / 100000) * over_budget_penalty_weight
filtered_df['최종점수'] = (filtered_df['기본점수'] - filtered_df['예산패널티']).round(1).clip(lower=0, upper=10)

filtered_df['추천태그'] = np.where(filtered_df['예산초과금액'] > 0, "예산을 조금 넘지만 조건이 매우 좋아요!", "")
result_df = filtered_df.sort_values('최종점수', ascending=False).reset_index(drop=True)

# --- 5. 카카오맵 렌더링 ---
def render_kakao_map(data):
    center_lat, center_lng = (data['위도'].mean(), data['경도'].mean()) if not data.empty else (37.375, 126.632)
    marker_list = []
    for _, row in data.iterrows():
        total_time = f"{int(row['총_시간(분)'])}분" if pd.notna(row.get('총_시간(분)')) else "-"
        marker_list.append({
            "lat": float(row['위도']), "lng": float(row['경도']),
            "content": f'<div style="padding:5px;font-size:12px;width:200px;color:black;"><b>{row["최종점수"]}점</b> | {row["종류"]}<br>월세+관리비: {int(row["월세_관리비_합"]/10000)}만원<br>학교까지: {total_time}</div>'
        })
    markers_json = json.dumps(marker_list, ensure_ascii=False)
    map_html = f"""
    <div id="map" style="width:100%;height:400px;border-radius:10px;"></div>
    <script src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_API_KEY}&libraries=services&autoload=false"></script>
    <script>
        window.kakao.maps.load(() => {{
            const container = document.getElementById('map');
            const map = new kakao.maps.Map(container, {{ center: new kakao.maps.LatLng({center_lat}, {center_lng}), level: 5 }});
            const positions = {markers_json};
            positions.forEach(pos => {{
                const marker = new kakao.maps.Marker({{ map, position: new kakao.maps.LatLng(pos.lat, pos.lng) }});
                const infowindow = new kakao.maps.InfoWindow({{ content: pos.content }});
                kakao.maps.event.addListener(marker, 'mouseover', () => infowindow.open(map, marker));
                kakao.maps.event.addListener(marker, 'mouseout', () => infowindow.close());
            }});
        }});
    </script>
    """
    return components.html(map_html, height=420)

# --- 6. 화면 출력 ---
LOGO_FILE_PATH = "logo_transparent.png"
logo_base64 = ""
if os.path.exists(LOGO_FILE_PATH):
    with open(LOGO_FILE_PATH, "rb") as f: logo_base64 = base64.b64encode(f.read()).decode()

header_html = f"""
<div style="background: linear-gradient(90deg, #1E90FF, #00BFFF); padding: 20px 30px; border-radius: 15px; color: white; margin-bottom: 25px; display: flex; justify-content: space-between; align-items: center;">
    <div><h1 style="margin: 0; font-size: 50px; font-weight: 900;">ROOMINU</h1><p style="margin: 5px 0 0 0; opacity: 0.8;">데이터 기반 맞춤형 자취방 분석</p></div>
    {f'<img src="data:image/png;base64,{logo_base64}" style="max-height: 100px;"/>' if logo_base64 else ""}
</div>
"""
st.markdown(header_html, unsafe_allow_html=True)

if not result_df.empty:
    st.subheader("매물 위치 확인")
    render_kakao_map(result_df)
    
    st.divider()
    st.subheader("맞춤형 추천 TOP 3")
    top_cols = st.columns(3)
    for i in range(min(3, len(result_df))):
        row = result_df.iloc[i]
        with top_cols[i]:
            card_html = f"""
            <div style="background:white; border:1px solid #E6E6E6; border-top:4px solid #FFC107; border-radius:15px; padding:20px; text-align:center;">
                <div style="color:#FFC107; font-weight:bold;">{i+1}위 추천</div>
                <div style="font-size:32px; font-weight:900;">{row['최종점수']} <span style="font-size:16px; color:#888;">/ 10</span></div>
                <div style="background:#F0F2F6; border-radius:10px; padding:10px; margin:10px 0;">{row['주소']}</div>
                <div style="display:flex; justify-content:space-around; font-weight:bold;"><span>{row['평수']}평</span><span>{int(row['보증금']/10000)}/{int(row['월세']/10000)}</span></div>
            </div>
            """
            components.html(card_html, height=300)
            if row['url 주소']: st.link_button("상세보기", row['url 주소'], use_container_width=True)

    st.divider()
    st.subheader("전체 매물 리스트")
    st.dataframe(result_df[['주소', '종류', '평수', '보증금', '월세_관리비_합', '최종점수', 'url 주소']], use_container_width=True)
else:
    st.warning("조건에 맞는 매물이 없습니다. 필터를 조절해 보세요.")
