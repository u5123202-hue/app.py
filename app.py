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
        df['향'] = df.get('향', '').fillna('')
        df['종류'] = df.get('종류', '기타').fillna('기타')
        df['url 주소'] = df.get('url 주소', '').fillna('')
        df['월세_관리비_합'] = df['월세'].fillna(0) + df['관리비'].fillna(0)
        option_cols = ['에어컨', '냉장고', '세탁기', '인덕션', '엘리베이터', '신발장', '옷장', '베란다', '싱크대']
        existing_option_cols = [col for col in option_cols if col in df.columns]
        if len(existing_option_cols) > 0:
            df['시설점수'] = df[existing_option_cols].replace({'O':1,'ㅇ':1,'1':1,'1.0':1}).fillna(0).mean(axis=1)*10
        else: df['시설점수'] = 5.0
        
        # 점수 계산 (가격, 크기, 통학)
        def min_max(s, inv=False):
            if s.empty or s.min() == s.max(): return 5.0
            res = (s - s.min()) / (s.max() - s.min()) * 10
            return 10 - res if inv else res
            
        df['가격점수'] = (min_max(df['월세_관리비_합'], True) * 0.7) + (min_max(df['보증금'], True) * 0.3)
        df['크기점수'] = min_max(df['평수'].clip(upper=25.0))
        df['통학점수'] = min_max(df['총_시간(분)'], True) if '총_시간(분)' in df.columns else 5.0
        return df, existing_option_cols
    except Exception as e:
        st.error(f"데이터 로드 에러: {e}")
        return pd.DataFrame(), []

df, option_cols = load_data()
if df.empty: st.stop()

# --- 3. 사이드바 ---
st.sidebar.header("검색 필터")
selected_types = st.sidebar.multiselect("매물 종류", options=df['종류'].unique(), default=list(df['종류'].unique()))
max_deposit = st.sidebar.slider("최대 보증금 (만원)", 0, 1000, 1000, step=50)
max_budget = st.sidebar.slider("희망 월세+관리비 (만원)", 0, 150, 70, step=5)
w_price = st.sidebar.slider("가격 중요도", 0, 10, 5)
w_option = st.sidebar.slider("시설 중요도", 0, 10, 5)
w_size = st.sidebar.slider("크기 중요도", 0, 10, 5)
w_commute = st.sidebar.slider("통학 중요도", 0, 10, 5)

# --- 4. 필터링 및 점수 계산 ---
budget_limit = max_budget * 10000
filtered_df = df.copy()
if selected_types: filtered_df = filtered_df[filtered_df['종류'].isin(selected_types)]
filtered_df = filtered_df[(filtered_df['월세_관리비_합'] <= budget_limit + 50000) & (filtered_df['보증금'] <= max_deposit * 10000)].copy()

total_w = w_price + w_option + w_size + w_commute
if total_w > 0:
    filtered_df['기본점수'] = ((filtered_df['가격점수']*w_price)+(filtered_df['시설점수']*w_option)+(filtered_df['크기점수']*w_size)+(filtered_df['통학점수']*w_commute))/total_w
else: filtered_df['기본점수'] = 0.0

# 지역별 가중치 및 최종 점수
def get_reg_w(addr):
    addr = str(addr)
    if '송도' in addr: return 1.15
    if '동춘' in addr: return 1.08
    if '원인재' in addr: return 1.05
    return 1.0

filtered_df['최종점수'] = (filtered_df['기본점수'] * filtered_df['주소'].apply(get_reg_w)).round(1).clip(0,10)
result_df = filtered_df.sort_values('최종점수', ascending=False).reset_index(drop=True)

# ✨ [핵심 기능] 동네별 최고 매물 추출 ✨
def get_best_by_area(df, area_name):
    area_df = df[df['주소'].str.contains(area_name, na=False)]
    return area_df.sort_values('최종점수', ascending=False).head(1)

best_songdo = get_best_by_area(result_df, '송도')
best_dongchun = get_best_by_area(result_df, '동춘')
best_woninjae = get_best_by_area(result_df, '연수동')

# --- 5. 카카오맵 & UI ---
def render_kakao_map(data):
    if data.empty: center = [37.375, 126.632]
    else: center = [data['위도'].mean(), data['경도'].mean()]
    marker_list = [{"lat": float(r['위도']), "lng": float(r['경도']), "content": f'<div style="padding:5px;font-size:12px;color:black;"><b>{r["최종점수"]}점</b><br>{r["주소"][:10]}...</div>'} for _, r in data.iterrows()]
    map_html = f"""<div id="map" style="width:100%;height:400px;border-radius:10px;"></div>
    <script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_API_KEY}&libraries=services&autoload=false"></script>
    <script>window.kakao?window.kakao.maps.load(()=>{{var m=new kakao.maps.Map(document.getElementById('map'),{{center:new kakao.maps.LatLng({center[0]},{center[1]}),level:5}});{json.dumps(marker_list)}.forEach(p=>{{var mk=new kakao.maps.Marker({{map:m,position:new kakao.maps.LatLng(p.lat,p.lng)}});var iw=new kakao.maps.InfoWindow({{content:p.content}});kakao.maps.event.addListener(mk,'mouseover',()=>iw.open(m,mk));kakao.maps.event.addListener(mk,'mouseout',()=>iw.close());}})}}):null;</script>"""
    components.html(map_html, height=420)

st.title("🏠 ROOMINU")
st.markdown("### 🏆 동네별 최고의 매물 추천")

# 지역별 베스트 카드 출력
best_cols = st.columns(3)
areas = [("📍 송도 베스트", best_songdo), ("📍 동춘 베스트", best_dongchun), ("📍 연수동 베스트", best_woninjae)]

for i, (title, b_df) in enumerate(areas):
    with best_cols[i]:
        if not b_df.empty:
            row = b_df.iloc[0]
            st.success(f"**{title}**")
            st.metric("최종 점수", f"{row['최종점수']} / 10")
            st.markdown(f"**{row['주소']}**")
            st.caption(f"{row['종류']} | {row['평수']}평 | {int(row['보증금']/10000)}/{int(row['월세']/10000)}")
            if row['url 주소']: st.link_button("매물 보기", row['url 주소'], use_container_width=True)
        else:
            st.info(f"{title}\n\n해당 지역 매물 없음")

st.divider()
if not result_df.empty:
    st.subheader("📍 전체 매물 위치 분석")
    render_kakao_map(result_df)
    st.divider()
    st.subheader("📋 전체 순위 리스트")
    st.dataframe(result_df[['최종점수', '주소', '종류', '평수', '월세_관리비_합', 'url 주소']], use_container_width=True, hide_index=True)
else:
    st.warning("조건에 맞는 매물이 없습니다.")
