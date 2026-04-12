import streamlit as st
import pandas as pd
import numpy as np
import streamlit.components.v1 as components
import json
import os
import base64

st.set_page_config(page_title="ROOMINU", layout="wide")

KAKAO_API_KEY = "853a71f8261b3dccfd8c6b6e1879d3c4"

@st.cache_data
def load_data():
    try:
        df = pd.read_csv('부동산 매물 정리.csv', encoding='utf-8')
        df.columns = df.columns.str.strip()

        required_cols = ['주소', '보증금', '월세', '평수']
        existing_required_cols = [col for col in required_cols if col in df.columns]
        df = df.dropna(subset=existing_required_cols)

        numeric_cols = ['보증금', '월세', '관리비', '평수', '위도', '경도', '총_시간(분)']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

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

        df['월세_관리비_합'] = df['월세'].fillna(0) + df['관리비'].fillna(0)
        df['실질월세'] = df['월세_관리비_합'] + (df['보증금'].fillna(0) * 0.04 / 12)

        option_cols = ['에어컨', '냉장고', '세탁기', '인덕션', '엘리베이터', '신발장', '옷장', '베란다', '싱크대']
        existing_option_cols = [col for col in option_cols if col in df.columns]

        if len(existing_option_cols) > 0:
            df['시설점수'] = df.apply(
                lambda row: (
                    sum(
                        1 for col in existing_option_cols
                        if str(row.get(col)).strip().upper() in ['O', 'ㅇ', '1', '1.0']
                    ) / len(existing_option_cols)
                ) * 10,
                axis=1
            )
        else:
            df['시설점수'] = 5.0

        min_p = df['실질월세'].min()
        max_p = df['실질월세'].max()
        if pd.notna(min_p) and pd.notna(max_p) and max_p != min_p:
            df['가격점수'] = 10 - ((df['실질월세'] - min_p) / (max_p - min_p) * 10)
            df['가격점수'] = df['가격점수'].clip(lower=0, upper=10)
        else:
            df['가격점수'] = 5.0

        target_max_size = 25.0
        min_s = df['평수'].min()
        if pd.notna(min_s) and target_max_size != min_s:
            df['크기점수'] = ((df['평수'].clip(upper=target_max_size) - min_s) / (target_max_size - min_s) * 10)
            df['크기점수'] = df['크기점수'].clip(lower=0, upper=10)
        else:
            df['크기점수'] = 5.0

        if '총_시간(분)' in df.columns:
            min_t = df['총_시간(분)'].min()
            max_t = df['총_시간(분)'].max()

            if pd.notna(min_t) and pd.notna(max_t) and max_t != min_t:
                df['통학점수'] = 10 - ((df['총_시간(분)'] - min_t) / (max_t - min_t) * 10)
                df['통학점수'] = df['통학점수'].clip(lower=0, upper=10)
            else:
                df['통학점수'] = 5.0
        else:
            df['총_시간(분)'] = np.nan
            df['통학점수'] = 5.0

        return df, existing_option_cols

    except Exception as e:
        st.error(f"데이터 로드 에러: {e}")
        return pd.DataFrame(), []

df, option_cols = load_data()
if df.empty:
    st.stop()

st.sidebar.header("검색 필터")

selected_types = st.sidebar.multiselect(
    "매물 종류",
    options=df['종류'].dropna().unique(),
    default=list(df['종류'].dropna().unique())
)

with st.sidebar.expander("예산 및 가격 설정", expanded=False):
    max_deposit_val = int(df['보증금'].max() / 10000) if pd.notna(df['보증금'].max()) else 100
    max_deposit_val = max(max_deposit_val, 100)

    max_deposit = st.slider("최대 보증금 (만원)", 0, max_deposit_val, max_deposit_val, step=100)
    max_budget = st.slider("희망 월세+관리비 예산 (만원)", 0, 150, 70, step=5)

with st.sidebar.expander("필수 옵션 선택", expanded=False):
    st.write("선택한 옵션이 모두 있는 매물만 보여줍니다.")
    selected_options = []
    for opt in option_cols:
        if st.checkbox(opt, key=f"chk_{opt}"):
            selected_options.append(opt)

with st.sidebar.expander("방향 설정", expanded=False):
    available_directions = [
        d for d in df['향'].dropna().unique()
        if str(d).strip() != '' and str(d).strip().lower() != 'nan'
    ]
    if available_directions:
        selected_directions = st.multiselect(
            "원하는 방향을 선택하세요 (여러 개 선택 가능)",
            options=available_directions,
            default=available_directions
        )
    else:
        selected_directions = []

st.sidebar.divider()

with st.sidebar.expander("항목별 중요도 설정", expanded=False):
    st.write("각 항목이 점수에 미치는 영향력을 조절하세요.")
    w_price = st.slider("가격 중요도", 0, 10, 5)
    w_option = st.slider("시설 중요도", 0, 10, 5)
    w_size = st.slider("크기 중요도", 0, 10, 5)
    w_commute = st.slider("통학 중요도", 0, 10, 5)

with st.sidebar.expander("예산 초과 패널티 설정", expanded=False):
    over_budget_penalty_weight = st.slider(
        "예산 초과 패널티 강도",
        min_value=0.0,
        max_value=5.0,
        value=1.0,
        step=0.1,
    )

budget_limit = max_budget * 10000
extended_budget_limit = budget_limit * 1.2

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
        filtered_df = filtered_df[
            filtered_df[opt].astype(str).str.strip().str.upper().isin(['1', '1.0', 'O', 'ㅇ'])
        ]

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

filtered_df['예산초과금액'] = (filtered_df['월세_관리비_합'] - budget_limit).clip(lower=0)
filtered_df['예산패널티'] = (filtered_df['예산초과금액'] / 100000) * over_budget_penalty_weight
filtered_df['최종점수'] = (filtered_df['기본점수'] - filtered_df['예산패널티']).round(1)
filtered_df['최종점수'] = filtered_df['최종점수'].clip(lower=0, upper=10)

filtered_df['추천태그'] = np.where(
    filtered_df['예산초과금액'] > 0,
    "예산을 조금 넘지만 조건이 매우 좋아요!",
    ""
)

result_df = filtered_df.sort_values('최종점수', ascending=False).reset_index(drop=True)

def render_kakao_map(data):
    if data.empty:
        center_lat, center_lng = 37.375, 126.632
    else:
        center_lat = data['위도'].mean()
        center_lng = data['경도'].mean()

    marker_list = []
    for _, row in data.iterrows():
        extra_tag = ""
        if pd.notna(row.get("추천태그", "")) and str(row.get("추천태그", "")).strip() != "":
            extra_tag = f"<br><span style='color:#ff6600;font-weight:bold;'>{row['추천태그']}</span>"

        total_time_text = "-"
        if pd.notna(row.get('총_시간(분)', np.nan)):
            total_time_text = f"{int(row['총_시간(분)'])}분"

        marker_list.append({
            "title": str(row['주소']),
            "lat": float(row['위도']),
            "lng": float(row['경도']),
            "content": f"""
                <div style="padding:5px;font-size:12px;width:200px;color:black;">
                    <b>{row["최종점수"]}점</b> | {row["종류"]}
                    <br>월세+관리비: {int(row["월세_관리비_합"] / 10000)}만원
                    <br>학교까지: {total_time_text}
                    {extra_tag}
                </div>
            """
        })

    markers_json = json.dumps(marker_list, ensure_ascii=False)

    map_html = f"""
    <head>
        <meta http-equiv="Content-Security-Policy" content="upgrade-insecure-requests">
    </head>
    <div id="map" style="width:100%;height:400px;border-radius:10px;background-color:#eee;"></div>
    <script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_API_KEY}&libraries=services&autoload=false"></script>
    <script>
        (function() {{
            var checkInterval = setInterval(function() {{
                if (window.kakao && window.kakao.maps && window.kakao.maps.load) {{
                    clearInterval(checkInterval);
                    window.kakao.maps.load(function() {{
                        var container = document.getElementById('map');
                        var options = {{
                            center: new kakao.maps.LatLng({center_lat}, {center_lng}),
                            level: 5
                        }};
                        var map = new kakao.maps.Map(container, options);
                        var positions = {markers_json};

                        positions.forEach(function(pos) {{
                            var marker = new kakao.maps.Marker({{
                                map: map,
                                position: new kakao.maps.LatLng(pos.lat, pos.lng)
                            }});

                            var infowindow = new kakao.maps.InfoWindow({{
                                content: pos.content
                            }});

                            kakao.maps.event.addListener(marker, 'mouseover', function() {{
                                infowindow.open(map, marker);
                            }});
                            kakao.maps.event.addListener(marker, 'mouseout', function() {{
                                infowindow.close();
                            }});
                        }});
                    }});
                }}
            }}, 100);
        }})();
    </script>
    """
    return components.html(map_html, height=420)

def get_image_base64(image_path):
    if not os.path.exists(image_path):
        return ""
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()

LOGO_FILE_PATH = "logo_transparent.png"
logo_base64 = get_image_base64(LOGO_FILE_PATH)

header_html = f"""
<div style="
    background: linear-gradient(90deg, #1E90FF, #00BFFF);
    padding: 20px 30px;
    border-radius: 15px;
    color: white;
    margin-bottom: 25px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    display: flex;
    justify-content: space-between;
    align-items: center;
">
    <div>
        <h1 style="margin: 0; font-size: 50px; font-weight: 900; letter-spacing: -1px;">
            ROOMINU
        </h1>
        <p style="margin: 5px 0 0 0; font-size: 15px; opacity: 0.8;">
            데이터 기반으로 분석한 나만의 맞춤형 자취방을 찾아보세요.
        </p>
    </div>
    {"" if logo_base64 == "" else f'<img src="data:image/png;base64,{logo_base64}" style="max-height: 120px; width: auto;"/>'}
</div>
"""
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

            tag_html = ""
            if pd.notna(row['추천태그']) and str(row['추천태그']).strip() != "":
                tag_html = f"""
                <div style="
                    background-color:#FFF3CD;
                    color:#856404;
                    border-radius:8px;
                    padding:8px 10px;
                    font-size:13px;
                    font-weight:bold;
                    margin-bottom:12px;
                    text-align:center;
                ">
                    {row['추천태그']}
                </div>
                """

            total_time_text = "-"
            if pd.notna(row.get('총_시간(분)', np.nan)):
                total_time_text = f"{int(row['총_시간(분)'])}분"

            card_html = f"""
            <div style="
                background-color: #FFFFFF;
                border: 1px solid #E6E6E6;
                border-top: 4px solid #FFC107;
                border-radius: 15px;
                padding: 20px;
                text-align: center;
                box-shadow: 0 4px 8px rgba(0,0,0,0.05);
                margin-bottom: 10px;
                min-height: 320px;
                font-family: Arial, sans-serif;
            ">
                <div style="color: #FFC107; font-size: 14px; font-weight: bold; margin-bottom: 8px;">
                    {i + 1}위 추천
                </div>

                <div style="color: {score_color}; font-size: 32px; font-weight: 900; margin-bottom: 15px;">
                    {row['최종점수']} <span style="font-size: 16px; font-weight: normal; color: #888;">/ 10점</span>
                </div>

                {tag_html}

                <div style="background-color: #F0F2F6; border-radius: 10px; padding: 12px; margin-bottom: 15px;">
                    <div style="color: #666; font-size: 12px; margin-bottom: 4px;">주소</div>
                    <div style="color: #31333F; font-size: 15px; word-break: keep-all;">{row['주소']}</div>
                </div>

                <div style="display: flex; justify-content: space-around; background-color: #F0F2F6; border-radius: 10px; padding: 12px; margin-bottom: 12px;">
                    <div style="color: #31333F; font-size: 15px;"><b>{row['평수']}</b>평</div>
                    <div style="color: #31333F; font-size: 15px;"><b>{int(row['보증금'] / 10000)}/{int(row['월세'] / 10000)}</b>만</div>
                </div>

                <div style="font-size:13px; color:#666;">
                    월세+관리비: <b>{int(row['월세_관리비_합'] / 10000)}만원</b><br>
                    예산 초과액: <b>{int(row['예산초과금액'] / 10000)}만원</b><br>
                    학교까지 총 시간: <b>{total_time_text}</b>
                </div>
            </div>
            """

            components.html(card_html, height=360)

            if str(row['url 주소']).strip() != "":
                st.link_button("네이버 부동산 상세보기", row['url 주소'], use_container_width=True)

    st.divider()
    st.subheader("전체 매물 분석 리스트")

    display_cols = [
        '주소', '종류', '평수', '총_시간(분)', '통학점수',
        '월세_관리비_합', '예산초과금액',
        '가격점수', '시설점수', '크기점수', 'url 주소'
    ]
    display_cols = [col for col in display_cols if col in result_df.columns]

    display_df = result_df[display_cols].copy()
    if '총_시간(분)' in display_df.columns:
        display_df['총_시간(분)'] = display_df['총_시간(분)'].apply(
            lambda x: f"{int(x)}분" if pd.notna(x) else "-"
        )

    st.dataframe(
        display_df,
        column_config={
            "url 주소": st.column_config.LinkColumn("링크"),
            "총_시간(분)": "학교까지시간",
            "월세_관리비_합": st.column_config.NumberColumn("월세+관리비", format="%d"),
            "예산초과금액": st.column_config.NumberColumn("예산 초과금액", format="%d"),
            "통학점수": st.column_config.NumberColumn("통학점수", format="%.1f"),
            "가격점수": st.column_config.NumberColumn("가격점수", format="%.1f"),
            "시설점수": st.column_config.NumberColumn("시설점수", format="%.1f"),
            "크기점수": st.column_config.NumberColumn("크기점수", format="%.1f"),
        },
        hide_index=True,
        use_container_width=True
    )
else:
    st.warning("조건에 맞는 매물이 없습니다. 옵션을 조절해 보세요.")
