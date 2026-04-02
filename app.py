import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit.components.v1 as components  # HTML/JS 삽입용

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="인천대 자취방 최적화", page_icon="🏠", layout="wide")

# --- KAKAO MAP API KEY 설정 ---
# 실제 배포 시에는 st.secrets["kakao_api_key"] 등을 사용하세요.
KAKAO_API_KEY = "853a71f8261b3dccfd8c6b6e1879d3c4"


# --- 2. 데이터 로드 및 전처리 (기존과 동일) ---
@st.cache_data
def load_data():
    # 실제 환경에서는 데이터프레임에 '위도', '경도' 컬럼이 포함되어 있어야 지도가 정확합니다.
    # 만약 없다면 주소를 좌표로 바꾸는 Geocoding 과정이 필요하지만, 여기선 위/경도가 있다고 가정하거나 샘플을 사용합니다.
    df = pd.read_csv('부동산 매물 정리.csv', encoding='utf-8')
    df = df.dropna(subset=['주소', '보증금'])
    df['실질월세'] = df['월세'] + df.get('관리비', 0) + (df['보증금'] * 0.04 / 12)

    option_cols = ['에어컨', '냉장고', '세탁기', '인덕션', '엘리베이터', '신발장', '옷장', '베란다', '싱크대']
    df['시설점수'] = df.apply(lambda row: (sum(1 for col in option_cols if row.get(col) == 'O') / len(option_cols)) * 10,
                          axis=1)

    min_p, max_p = df['실질월세'].min(), df['실질월세'].max()
    df['가격점수'] = 10 - ((df['실질월세'] - min_p) / (max_p - min_p) * 10)

    target_max_size = 25.0
    min_s = df['평수'].min()
    df['크기점수'] = ((df['평수'] - min_s) / (target_max_size - min_s) * 10)

    # 지도 테스트용 임시 좌표 (데이터에 위도/경도가 없을 경우 대비)
    if '위도' not in df.columns:
        df['위도'] = 37.375  # 인천대 입구역 근처 기본값
        df['경도'] = 126.632

    return df


try:
    df = load_data()
except Exception as e:
    st.error(f"데이터 로드 실패: {e}")
    st.stop()

# --- 3. 사이드바 (기존과 동일) ---
st.sidebar.header("🔍 검색 필터")
selected_types = st.sidebar.multiselect("매물 종류", df['종류'].unique(), default=df['종류'].unique())
max_budget = st.sidebar.slider("💰 최대 예산 (월세+관리비, 만원)",
                               int(df['실질월세'].min() / 10000),
                               int(df['실질월세'].max() / 10000), 70)

st.sidebar.divider()
st.sidebar.header("⚖️ 항목별 중요도 (1~10)")
w_price = st.sidebar.slider("가격 중요도", 1, 10, 5)
w_option = st.sidebar.slider("시설 중요도", 1, 10, 5)
w_size = st.sidebar.slider("크기 중요도", 1, 10, 5)

# --- 4. 필터링 및 계산 (기존과 동일) ---
filtered_df = df[(df['종류'].isin(selected_types)) & (df['실질월세'] <= max_budget * 10000)].copy()
total_w = w_price + w_option + w_size
filtered_df['최종점수'] = ((filtered_df['가격점수'] * (w_price / total_w)) +
                       (filtered_df['시설점수'] * (w_option / total_w)) +
                       (filtered_df['크기점수'] * (w_size / total_w))).round(1)

result_df = filtered_df.sort_values('최종점수', ascending=False).reset_index(drop=True)


# --- 5. 카카오맵 렌더링 함수 ---
def render_kakao_map(data):
    # 지도 중심점을 데이터의 평균 위경도로 설정
    if not data.empty:
        center_lat = data['위도'].mean()
        center_lng = data['경도'].mean()
    else:
        center_lat, center_lng = 37.375, 126.632

    # 마커 데이터를 JS 배열로 변환
    markers_js = ""
    for i, row in data.iterrows():
        markers_js += f"""
        {{
            title: '{row['주소']}', 
            latlng: new kakao.maps.LatLng({row['위도']}, {row['경도']}),
            content: '<div style="padding:5px;font-size:12px;">{row['최종점수']}점<br>{row['종류']}</div>'
        }},"""

    map_html = f"""
    <div id="map" style="width:100%;height:400px;border-radius:10px;"></div>
    <script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_API_KEY}"></script>
    <script>
        var mapContainer = document.getElementById('map'),
            mapOption = {{ 
                center: new kakao.maps.LatLng({center_lat}, {center_lng}),
                level: 5 
            }};
        var map = new kakao.maps.Map(mapContainer, mapOption);
        var positions = [{markers_js}];

        for (var i = 0; i < positions.length; i ++) {{
            var marker = new kakao.maps.Marker({{
                map: map,
                position: positions[i].latlng,
                title: positions[i].title
            }});
            var infowindow = new kakao.maps.InfoWindow({{
                content: positions[i].content
            }});
            (function(marker, infowindow) {{
                kakao.maps.event.addListener(marker, 'mouseover', function() {{
                    infowindow.open(map, marker);
                }});
                kakao.maps.event.addListener(marker, 'mouseout', function() {{
                    infowindow.close();
                }});
            }})(marker, infowindow);
        }}
    </script>
    """
    return components.html(map_html, height=420)


# --- 6. 결과 화면 출력 ---
st.title("인천대 송도 자취방 추천 (10점 만점 척도) 🏠")

# 지도 먼저 표시
if not result_df.empty:
    st.subheader("📍 매물 위치 확인")
    render_kakao_map(result_df.head(10))  # 상위 10개만 지도에 표시

    st.divider()
    st.subheader("🏆 맞춤형 추천 매물 TOP 3")
    top_cols = st.columns(3)
    # ... (기존 TOP 3 출력 코드 동일)
    for i in range(min(3, len(result_df))):
        row = result_df.iloc[i]
        with top_cols[i]:
            st.metric(label=f"{i + 1}위 추천", value=f"{row['최종점수']} / 10")
            fig = go.Figure()
            fig.add_trace(go.Scatterpolar(r=[row['가격점수'], row['시설점수'], row['크기점수']], theta=['가격지수', '시설지수', '크기지수'],
                                          fill='toself', line_color='#00CC96'))
            fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 10])), showlegend=False, height=250,
                              margin=dict(l=40, r=40, t=20, b=20))
            st.plotly_chart(fig, use_container_width=True)
            st.info(f"📍 {row['주소']}")
            st.write(f"📏 {row['평수']}평 | 💸 {int(row['보증금'] / 10000)}/{int(row['월세'] / 10000)}")
            st.link_button("상세보기", row['url 주소'])

    st.divider()
    st.subheader("📋 전체 매물 분석 리스트")
    st.dataframe(result_df[['최종점수', '주소', '종류', '평수', '가격점수', '시설점수', '크기점수', 'url 주소']],
                 column_config={"url 주소": st.column_config.LinkColumn("링크")},
                 hide_index=True, use_container_width=True)
else:
    st.warning("조건에 맞는 매물이 없습니다.")
