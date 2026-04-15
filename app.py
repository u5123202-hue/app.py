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

        # 숫자형 변환
        numeric_cols = ['보증금', '월세', '관리비', '평수', '위도', '경도']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        if '총_시간(분)' in df.columns:
             df['총_시간(분)'] = pd.to_numeric(df['총_시간(분)'], errors='coerce')
        else:
            df['총_시간(분)'] = np.nan

        # 결측치 보정
        df['관리비'] = df['관리비'].fillna(0)
        df['위도'] = df['위도'].fillna(37.375)
        df['경도'] = df['경도'].fillna(126.632)
        df['향'] = df['향'].fillna('')
        df['종류'] = df['종류'].fillna('기타')
        df['url 주소'] = df['url 주소'].fillna('')

        # --- 가격 점수 로직 ---
        df['월세_관리비_합'] = df['월세'].fillna(0) + df['관리비'].fillna(0)

        # 보증금 점수 (낮을수록 고득점)
        min_dep = df['보증금'].min()
        max_dep = df['보증금'].max()
        if pd.notna(min_dep) and pd.notna(max_dep) and max_dep != min_dep:
            df['보증금점수'] = 10 - ((df['보증금'] - min_dep) / (max_dep - min_dep) * 10)
        else:
            df['보증금점수'] = 5.0

        # 월세 점수 (낮을수록 고득점)
        min_rent_sum = df['월세_관리비_합'].min()
        max_rent_sum = df['월세_관리비_합'].max()
        if pd.notna(min_rent_sum) and pd.notna(max_rent_sum) and max_rent_sum != min_rent_sum:
            df['월세점수'] = 10 - ((df['월세_관리비_합'] - min_rent_sum) / (max_rent_sum - min_rent_sum) * 10)
        else:
            df['월세점수'] = 5.0

        # 가격점수 (월세 70% + 보증금 30%)
        df['가격점수'] = (df['월세점수'] * 0.7) + (df['보증금점수'] * 0.3)
        df['가격점수'] = df['가격점수'].clip(lower=0, upper=10)

        # 시설 점수
        option_cols = ['에어컨', '냉장고', '세탁기', '인덕션', '엘리베이터', '신발장', '옷장', '베란다', '싱크대']
        existing_option_cols = [col for col in option_cols if col in df.columns]
        if len(existing_option_cols) > 0:
            df['시설점수'] = df.apply(lambda row: (sum(1 for col in existing_option_cols if str(row.get(col)).strip().upper() in ['O', 'ㅇ', '1', '1.0']) / len(existing_option_cols)) * 10, axis=1)
        else:
            df['시설점수'] = 5.0

        # 크기 점수
        target_max_size = 25.0
        min_s = df['평수'].min()
        if pd.notna(min_s) and target_max_size != min_s:
            df['크기점수'] = ((df['평수'].clip(upper=target_max_size) - min_s) / (target_max_size - min_s) * 10)
        else:
            df['크기점수'] = 5.0

        # 통학 점수
        min_t = df['총_시간(분)'].min()
        max_t = df['총_시간(분)'].max()
        if pd.notna(min_t) and pd.notna(max_t) and max_t != min_t:
            df['통학점수'] = 10 - ((df['총_시간(분)'] - min_t) / (max_t - min_t) * 10)
        else:
            df['통학점수'] = 5.0

        return df, existing_option_cols

    except Exception as e:
        st.error(f"데이터 로드 에러: {e}")
        return pd.DataFrame(), []

df, option_cols = load_data()
if df.empty: st.stop()

# --- 3. 사이드바 ---
st.sidebar.header("검색 필터")

selected_types = st.sidebar.multiselect("매물 종류", options=df['종류'].dropna().unique(), default=list(df['종류'].dropna().unique()))

with st.sidebar.expander("예산 및 가격 설정", expanded=True):
    # 보증금 슬라이더 (0~1000만원)
    max_deposit_guide = st.slider("희망 보증금 (만원)", 0, 1000, 1000, step=50)
    max_budget_guide = st.slider("희망 월세+관리비 (만원)", 0, 150, 70, step=5)

    if max_deposit_guide >= 1000:
        st.caption("현재: **보증금 제한 없음**")
    else:
        st.caption(f"현재: **{max_deposit_guide}만원** (최대 {int(max_deposit_guide * 1.2)}만원까지 고려)")

with st.sidebar.expander("필수 옵션", expanded=False):
    selected_options = [opt for opt in option_cols if st.checkbox(opt, key=f"chk_{opt}")]

with st.sidebar.expander("항목별 중요도", expanded=False):
    w_price = st.slider("가격 중요도", 0, 10, 5)
    w_option = st.slider("시설 중요도", 0, 10, 5)
    w_size = st.slider("크기 중요도", 0, 10, 5)
    w_commute = st.slider("통학 중요도", 0, 10, 5)

over_budget_penalty_weight = st.sidebar.number_input("예산 초과 패널티 강도", 0.0, 5.0, 1.0, 0.1)

# --- 4. 필터링 및 점수 계산 ---
# 사용자가 선택한 기준값
deposit_limit = max_deposit_guide * 10000
rent_limit = max_budget_guide * 10000

# 필터링용 여유값 (1.2배)
extended_deposit_limit = deposit_limit * 1.2
extended_rent_limit = rent_limit * 1.2

filtered_df = df.copy()

if selected_types:
    filtered_df = filtered_df[filtered_df['종류'].isin(selected_types)]

# 보증금 필터 (1000만원 미만 선택 시 1.2배까지 허용)
if max_deposit_guide < 1000:
    filtered_df = filtered_df[filtered_df['보증금'] <= extended_deposit_limit]

# 월세 필터 (1.2배까지 허용)
filtered_df = filtered_df[filtered_df['월세_관리비_합'] <= extended_rent_limit].copy()

for opt in selected_options:
    filtered_df = filtered_df[filtered_df[opt].astype(str).str.strip().str.upper().isin(['1', '1.0', 'O', 'ㅇ'])]

# 점수 계산
total_w = w_price + w_option + w_size + w_commute
if total_w > 0:
    filtered_df['기본점수'] = (
        (filtered_df['가격점수'] * (w_price / total_w)) +
        (filtered_df['시설점수'] * (w_option / total_w)) +
        (filtered_df['크기점수'] * (w_size / total_w)) +
        (filtered_df['통학점수'] * (w_commute / total_w))
    )
else:
    filtered_df['기본점수'] = 0.0

# 예산 초과 패널티 (보증금 + 월세 모두 고려)
filtered_df['보증금초과'] = (filtered_df['보증금'] - deposit_limit).clip(lower=0)
filtered_df['월세초과'] = (filtered_df['월세_관리비_합'] - rent_limit).clip(lower=0)

# 보증금은 단위가 크므로 100만원당 패널티, 월세는 10만원당 패널티 부여
filtered_df['예산패널티'] = ((filtered_df['보증금초과'] / 1000000) + (filtered_df['월세초과'] / 100000)) * over_budget_penalty_weight

filtered_df['최종점수'] = (filtered_df['기본점수'] - filtered_df['예산패널티']).round(1).clip(lower=0, upper=10)

# 태그 생성
def get_tag(row):
    tags = []
    if row['보증금초과'] > 0 or row['월세초과'] > 0:
        tags.append("예산 초과나 조건 우수")
    return " | ".join(tags)

filtered_df['추천태그'] = filtered_df.apply(get_tag, axis=1)
result_df = filtered_df.sort_values('최종점수', ascending=False).reset_index(drop=True)

# --- 5. 카카오맵 렌더링 ---
def render_kakao_map(data):
    center_lat, center_lng = (data['위도'].mean(), data['경도'].mean()) if not data.empty else (37.375, 126.632)
    marker_list = []
    for _, row in data.iterrows():
        marker_list.append({
            "lat": float(row['위도']), "lng": float(row['경도']),
            "content": f'<div style="padding:5px;font-size:12px;width:180px;color:black;"><b>{row["최종점수"]}점</b> | {row["종류"]}<br>{int(row["보증금"]/10000)}/{int(row["월세_관리비_합"]/10000)}</div>'
        })
    markers_json = json.dumps(marker_list, ensure_ascii=False)
    map_html = f"""
    <div id="map" style="width:100%;height:400px;border-radius:15px;background:#eee;"></div>
    <script src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_API_KEY}&libraries=services&autoload=false"></script>
    <script>
        window.kakao.maps.load(() => {{
            const map = new kakao.maps.Map(document.getElementById('map'), {{ center: new kakao.maps.LatLng({center_lat}, {center_lng}), level: 5 }});
            {markers_json}.forEach(pos => {{
                const m = new kakao.maps.Marker({{ map, position: new kakao.maps.LatLng(pos.lat, pos.lng) }});
                const iw = new kakao.maps.InfoWindow({{ content: pos.content }});
                kakao.maps.event.addListener(m, 'mouseover', () => iw.open(map, m));
                kakao.maps.event.addListener(m, 'mouseout', () => iw.close());
            }});
        }});
    </script>
    """
    components.html(map_html, height=420)

# --- 6. 결과 출력 ---
st.markdown(f'<div style="background:linear-gradient(90deg,#1E90FF,#00BFFF);padding:20px;border-radius:15px;color:white;text-align:center;"><h1>ROOMINU</h1><p>예산의 1.2배까지 꼼꼼하게 분석합니다</p></div>', unsafe_allow_html=True)

if not result_df.empty:
    st.subheader("📍 매물 위치 분석")
    render_kakao_map(result_df)

    st.divider()
    st.subheader("🏆 나에게 딱 맞는 매물 TOP 3")
    cols = st.columns(3)
    for i in range(min(3, len(result_df))):
        row = result_df.iloc[i]
        with cols[i]:
            st.markdown(f"""
            <div style="border:1px solid #ddd; border-radius:15px; padding:15px; text-align:center; background:white;">
                <h3 style="color:#1E90FF; margin:0;">{i+1}순위</h3>
                <h2 style="margin:10px 0;">{row['최종점수']}점</h2>
                <p><b>{row['주소']}</b></p>
                <p style="font-size:14px; color:#666;">보증금 {int(row['보증금']/10000)} / 월세+관 {int(row['월세_관리비_합']/10000)}</p>
                <p style="color:orange; font-size:12px;">{row['추천태그']}</p>
            </div>
            """, unsafe_allow_html=True)
            if row['url 주소']: st.link_button("상세보기", row['url 주소'], use_container_width=True)

    st.divider()
    st.subheader("📋 전체 매물 분석 리스트")
    st.dataframe(result_df[['최종점수', '주소', '종류', '보증금', '월세_관리비_합', '평수', '추천태그']], use_container_width=True)
else:
    st.warning("조건에 맞는 매물이 없습니다. 필터를 조금 더 넓게 조정해보세요!")
