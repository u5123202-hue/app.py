import streamlit as st
import pandas as pd
import streamlit.components.v1 as components  # HTML 삽입을 위해 필요

# 1. 페이지 설정
st.set_page_config(page_title="ROOM IN U", page_icon="🏠", layout="wide")


# 2. 데이터 불러오기 함수
@st.cache_data
def load_data():
    file_path = '부동산 매물 정리.csv'
    try:
        df = pd.read_csv(file_path, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(file_path, encoding='cp949')

    # 숫자 변환 및 전처리 (문자열 섞임 방지)
    for col in ['위도', '경도', '보증금', '월세']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce')

    return df


# 3. 카카오맵 표시 함수 (핵심 추가 부분!)
def st_kakao_map(df, center_lat=37.375, center_lng=126.632):
    # --- 중요: 본인의 JavaScript 키를 여기에 넣으세요 ---
    KAKAO_JS_KEY = "853a71f8261b3dccfd8c6b6e1879d3c4"

    # 지도에 표시할 마커 데이터 생성
    marker_data = []
    for _, row in df.iterrows():
        if pd.notna(row['위도']) and pd.notna(row['경도']):
            marker_data.append(f"{{lat: {row['위도']}, lng: {row['경도']}, title: '{row['주소']}'}}")

    markers_js = ",".join(marker_data)

    # HTML/JS 코드 작성
    kakao_html = f"""
    <div id="map" style="width:100%;height:500px;border-radius:10px;"></div>
    <script type="text/javascript" src="//dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_JS_KEY}"></script>
    <script>
        var container = document.getElementById('map');
        var options = {{
            center: new kakao.maps.LatLng({center_lat}, {center_lng}),
            level: 4
        }};
        var map = new kakao.maps.Map(container, options);

        var positions = [{markers_js}];

        positions.forEach(function (pos) {{
            var marker = new kakao.maps.Marker({{
                map: map,
                position: new kakao.maps.LatLng(pos.lat, pos.lng),
                title: pos.title
            }});
        }});
    </script>
    """
    components.html(kakao_html, height=520)


# --- 메인 로직 ---
try:
    df = load_data()

    # 4. 사이드바 필터
    st.sidebar.header("🔍 검색 조건")
    all_types = df['종류'].unique().tolist()
    selected_types = st.sidebar.multiselect("방 종류 선택", all_types, default=all_types)

    max_dep_limit = int(df['보증금'].max() / 10000) if not df.empty else 1000
    max_deposit = st.sidebar.slider("💰 최대 보증금 (만원)", 0, max_dep_limit, max_dep_limit)

    filtered_df = df[
        (df['종류'].isin(selected_types)) &
        (df['보증금'] <= max_deposit * 10000)
        ]

    # 5. 화면 구성
    st.title("🏠 ROOM IN U")
    st.subheader("인천대 송도캠퍼스 자취방 추천 시스템")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("#### 📍 카카오맵 위치 확인")
        if not filtered_df.empty:
            # 기존 st.map 대신 우리가 만든 카카오맵 함수 호출!
            st_kakao_map(filtered_df)
        else:
            st.warning("조건에 맞는 매물이 없습니다.")

    with col2:
        st.markdown("#### 📊 요약 정보")
        st.metric("선택된 매물", f"{len(filtered_df)} 개")
        if not filtered_df.empty:
            avg_rent = int(filtered_df['월세'].mean() / 10000)
            st.metric("평균 월세", f"{avg_rent} 만원")
            st.write("---")
            st.write("**최근 추천 매물**")
            st.write(filtered_df[['주소', '월세']].head(5))

    st.divider()
    st.markdown("#### 📋 상세 매물 리스트")
    st.dataframe(filtered_df, use_container_width=True)

except Exception as e:
    st.error(f"오류가 발생했습니다: {e}")
