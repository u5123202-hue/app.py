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

        min_rent = df['월세_관리비_합'].min()
        max_rent = df['월세_관리비_합'].max()
        if pd.notna(min_rent) and pd.notna(max_rent) and max_rent != min_rent:
            rent_score = 10 - ((df['월세_관리비_합'] - min_rent) / (max_rent - min_rent) * 10)
        else:
            rent_score = 5.0

        min_dep = df['보증금'].min()
        max_dep = df['보증금'].max()
        if pd.notna(min_dep) and pd.notna(max_dep) and max_dep != min_dep:
            dep_score = 10 - ((df['보증금'] - min_dep) / (max_dep - min_dep) * 10)
        else:
            dep_score = 5.0

        df['가격점수'] = (rent_score * 0.7) + (dep_score * 0.3)
        df['가격점수'] = df['가격점수'].clip(lower=0, upper=10)

        target_max_size = 25.0
        min_s = df['평수'].min()
        if pd.notna(min_s) and target_max_size != min_s:
            df['크기점수'] = ((df['평수'].clip(upper=target_max_size) - min_s) / (target_max_size - min_s) * 10)
            df['크기점수'] = df['크기점수'].clip(lower=0, upper=10)
        else:
            df['크기점수'] = 5.0

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


# --- 세션 상태 초기화 ---
if "presets" not in st.session_state:
    st.session_state.presets = {}

if "selected_types" not in st.session_state:
    st.session_state.selected_types = list(df['종류'].dropna().unique())

if "max_deposit" not in st.session_state:
    st.session_state.max_deposit = 1000

if "max_budget" not in st.session_state:
    st.session_state.max_budget = 70

if "desired_size" not in st.session_state:
    st.session_state.desired_size = 20

if "size_any" not in st.session_state:
    st.session_state.size_any = False

if "selected_directions" not in st.session_state:
    available_directions_init = [
        d for d in df['향'].dropna().unique()
        if str(d).strip() != '' and str(d).strip().lower() != 'nan'
    ]
    st.session_state.selected_directions = available_directions_init

if "w_price" not in st.session_state:
    st.session_state.w_price = 3
if "w_option" not in st.session_state:
    st.session_state.w_option = 3
if "w_size" not in st.session_state:
    st.session_state.w_size = 3
if "w_commute" not in st.session_state:
    st.session_state.w_commute = 3

for opt in option_cols:
    key = f"chk_{opt}"
    if key not in st.session_state:
        st.session_state[key] = False


# --- 프리셋 적용 로직 ---
if "pending_preset" in st.session_state:
    slot = st.session_state.pending_preset
    if slot in st.session_state.presets:
        preset = st.session_state.presets[slot]
        st.session_state.selected_types = preset["selected_types"]
        st.session_state.max_deposit = preset["max_deposit"]
        st.session_state.max_budget = preset["max_budget"]
        st.session_state.desired_size = preset.get("desired_size", 20)
        st.session_state.size_any = preset.get("size_any", False)
        st.session_state.selected_directions = preset["selected_directions"]
        st.session_state.w_price = preset.get("w_price", 3)
        st.session_state.w_option = preset.get("w_option", 3)
        st.session_state.w_size = preset.get("w_size", 3)
        st.session_state.w_commute = preset.get("w_commute", 3)

        for opt in option_cols:
            st.session_state[f"chk_{opt}"] = opt in preset["selected_options"]

    del st.session_state.pending_preset


def apply_preset(slot):
    if slot not in st.session_state.presets:
        return
    st.session_state.pending_preset = slot
    st.rerun()


# --- 경제성 비교 계산 함수 ---
def calculate_total_cost(row, months=12, commute_days_per_month=20):
    deposit = row.get('보증금', 0)
    monthly_rent = row.get('월세', 0)
    maintenance = row.get('관리비', 0)
    commute_min = row.get('총_시간(분)', 0)

    if pd.isna(deposit):
        deposit = 0
    if pd.isna(monthly_rent):
        monthly_rent = 0
    if pd.isna(maintenance):
        maintenance = 0
    if pd.isna(commute_min):
        commute_min = 0

    # 보증금 기회비용 = 보증금을 다른 곳에 투자했을 때 포기하는 이자수익
    deposit_opportunity_cost = deposit * (months / 12)

    # 고정 지출 = 월세 및 관리비 총액
    rent_total = monthly_rent * months
    maintenance_total = maintenance * months

    # 통학시간 비용 = 총 통학시간 x 시간가치
    commute_hours_total = (commute_min / 60) * commute_days_per_month * months
    commute_cost = commute_hours_total * 5160

    total_cost = deposit_opportunity_cost + rent_total + maintenance_total + commute_cost

    return {
        "보증금 기회비용": deposit_opportunity_cost,
        "월세 총액": rent_total,
        "관리비 총액": maintenance_total,
        "통학시간 비용": commute_cost,
        "총비용": total_cost
    }


def format_won(value):
    return f"{int(value):,}원"


def format_manwon(value):
    return f"{int(value / 10000):,}만원"


# --- 3. 사이드바 ---
st.sidebar.header("검색 필터")

selected_types = st.sidebar.multiselect(
    "매물 종류",
    options=df['종류'].dropna().unique(),
    key="selected_types"
)

with st.sidebar.expander("예산 및 가격 설정", expanded=False):
    max_deposit = st.slider("최대 보증금 (만원)", 0, 1000, step=50, key="max_deposit")
    max_budget = st.slider("희망 월세+관리비 예산 (만원)", 0, 150, step=5, key="max_budget")

with st.sidebar.expander("희망 평수 설정", expanded=False):
    size_any = st.checkbox("평수 상관없음", key="size_any")
    desired_size = st.slider(
        "희망 평수 (구간 선택)",
        0, 30, step=1,
        key="desired_size",
        disabled=size_any,
        help="""선택한 값을 기준으로 ±5평 범위를 추천합니다.
    
    예시:
    - 5 → 0~10평
    - 10 → 5~15평
    - 15 → 10~20평
    """
    )

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
            key="selected_directions"
        )
    else:
        selected_directions = []

st.sidebar.divider()
st.sidebar.subheader("맞춤 필터 저장 및 불러오기")

preset_name_input = st.sidebar.text_input("새 필터 저장 이름 (선택)", placeholder="예: 내 취향 옵션")

if st.sidebar.button("현재 설정 저장", use_container_width=True):
    preset_name = preset_name_input.strip()
    if not preset_name:
        preset_num = len(st.session_state.presets) + 1
        preset_name = f"내 필터 {preset_num}"

    st.session_state.presets[preset_name] = {
        "selected_types": selected_types,
        "max_deposit": max_deposit,
        "max_budget": max_budget,
        "desired_size": desired_size,
        "size_any": size_any,
        "selected_options": selected_options,
        "selected_directions": selected_directions,
        "w_price": st.session_state.w_price,
        "w_option": st.session_state.w_option,
        "w_size": st.session_state.w_size,
        "w_commute": st.session_state.w_commute
    }

    st.sidebar.success(f"'{preset_name}' 저장 완료")
    st.rerun()

if st.session_state.presets:
    st.markdown("""
        <style>
        button[kind="tertiary"] {
            text-decoration: underline !important;
            font-size: 13px !important;
            color: #888888 !important;
            padding-top: 5px !important;
            background: none !important;
            border: none !important;
            box-shadow: none !important;
        }
        button[kind="tertiary"]:hover {
            color: #ff4b4b !important;
        }
        </style>
    """, unsafe_allow_html=True)

    with st.sidebar.expander("저장된 필터 목록 열기", expanded=False):
        for preset_name in list(st.session_state.presets.keys()):
            col1, col2 = st.columns([4, 1])
            with col1:
                if st.button(f"{preset_name} 적용", key=f"apply_{preset_name}", use_container_width=True):
                    apply_preset(preset_name)
            with col2:
                if st.button("삭제", key=f"del_{preset_name}", type="tertiary"):
                    del st.session_state.presets[preset_name]
                    st.rerun()


# --- 4. 필터링 및 계산 ---
budget_limit = max_budget * 10000
HIDDEN_FLEX_BUDGET = 50000
extended_budget_limit = budget_limit + HIDDEN_FLEX_BUDGET

filtered_df = df.copy()

if selected_types:
    filtered_df = filtered_df[filtered_df['종류'].isin(selected_types)]

filtered_df = filtered_df[
    (filtered_df['월세_관리비_합'] <= extended_budget_limit) &
    (filtered_df['보증금'] <= max_deposit * 10000)
]

if not size_any:
    min_size = max(0, desired_size - 5)
    max_size = desired_size + 5

    filtered_df = filtered_df[
        (filtered_df['평수'] >= min_size) &
        (filtered_df['평수'] <= max_size)
    ]

if selected_directions:
    filtered_df = filtered_df[filtered_df['향'].isin(selected_directions)]

for opt in selected_options:
    if opt in filtered_df.columns:
        filtered_df = filtered_df[
            filtered_df[opt].astype(str).str.strip().str.upper().isin(['1', '1.0', 'O', 'ㅇ'])
        ]

w_price = st.session_state.w_price
w_option = st.session_state.w_option
w_size = st.session_state.w_size
w_commute = st.session_state.w_commute

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
over_amount_manwon = filtered_df['예산초과금액'] / 10000
filtered_df['예산패널티'] = (over_amount_manwon ** 2.0) * 0.05

filtered_df['최종점수'] = (filtered_df['기본점수'] - filtered_df['예산패널티']).round(1)
filtered_df['최종점수'] = filtered_df['최종점수'].clip(lower=0, upper=10)

filtered_df['추천태그'] = np.where(
    filtered_df['예산초과금액'] > 0,
    "예산을 조금 넘지만 조건이 매우 좋아요!",
    ""
)

result_df = filtered_df.sort_values('최종점수', ascending=False).reset_index(drop=True)


# --- 5. 카카오맵 렌더링 함수 ---
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

    <div id="map" style="width:100%;height:500px;border-radius:10px;background-color:#eee;"></div>

    <script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_API_KEY}&libraries=services,clusterer&autoload=false"></script>

    <script>
        (function() {{
            var checkInterval = setInterval(function() {{
                if (window.kakao && window.kakao.maps && window.kakao.maps.load) {{
                    clearInterval(checkInterval);

                    window.kakao.maps.load(function() {{
                        var container = document.getElementById('map');

                        var options = {{
                            center: new kakao.maps.LatLng({center_lat}, {center_lng}),
                            level: 6
                        }};

                        var map = new kakao.maps.Map(container, options);

                        var clusterer = new kakao.maps.MarkerClusterer({{
                            map: map,
                            averageCenter: true,
                            minLevel: 2,
                            gridSize: 35,
                            disableClickZoom: false
                        }});

                        var positions = {markers_json};
                        var markers = [];

                        positions.forEach(function(pos) {{
                            var marker = new kakao.maps.Marker({{
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

                            markers.push(marker);
                        }});

                        clusterer.addMarkers(markers);
                    }});
                }}
            }}, 100);
        }})();
    </script>
    """

    return components.html(map_html, height=520)


def get_image_base64(image_path):
    if not os.path.exists(image_path):
        return ""
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()


LOGO_FILE_PATH = "logo_transparent.png"
logo_base64 = get_image_base64(LOGO_FILE_PATH)


# --- 6. 결과 화면 출력 ---
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
    st.subheader("매물 위치 확인 및 추천 기준 설정")

    map_col, weight_col = st.columns([2.2, 1])

    with map_col:
        render_kakao_map(result_df)

    with weight_col:
        st.markdown("""
        <div style="
            background-color:#F8F9FA;
            border:1px solid #E6E6E6;
            border-radius:12px;
            padding:16px;
            margin-bottom:10px;
        ">
            <h4 style="margin-top:0; margin-bottom:8px;">항목별 중요도 설정</h4>
            <p style="font-size:13px; color:#666; margin-bottom:0;">
                각 항목이 추천 점수에 미치는 영향력을 조절하세요.
            </p>
        </div>
        """, unsafe_allow_html=True)

        st.slider("가격 중요도", 1, 5, key="w_price")
        st.slider("시설 중요도", 1, 5, key="w_option")
        st.slider("크기 중요도", 1, 5, key="w_size")
        st.slider("통학 중요도", 1, 5, key="w_commute")

        total_weight_now = (
            st.session_state.w_price +
            st.session_state.w_option +
            st.session_state.w_size +
            st.session_state.w_commute
        )

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
                    학교까지 총 시간: <b>{total_time_text}</b>
                </div>
            </div>
            """

            components.html(card_html, height=360)

            if str(row['url 주소']).strip() != "":
                st.link_button("네이버 부동산 상세보기", row['url 주소'], use_container_width=True)

    # --- 7. 전체 매물 리스트 + 1vs1 매물 경제성 비교 기능 ---
    st.divider()
    st.subheader("전체 매물 리스트")

    st.markdown("""
    <div style="
        background-color:#F8F9FA;
        border:1px solid #E6E6E6;
        border-radius:12px;
        padding:16px;
        margin-bottom:12px;
    ">
        <h4 style="margin-top:0; margin-bottom:8px;">1vs1 매물 경제성 비교</h4>
        <p style="font-size:13px; color:#666; margin-bottom:0;">
            아래 전체 매물 리스트에서 비교할 매물 2개를 체크한 뒤, 비교하기 버튼을 누르세요.
        </p>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("비교 조건 설정", expanded=False):
        col_a, col_b = st.columns(2)

        with col_a:
            compare_months = st.number_input("희망 거주기간(개월)", min_value=1, max_value=60, value=12)

        with col_b:
            commute_days = st.number_input("월 통학일수", min_value=1, max_value=31, value=20)

    display_cols = [
        '선택', '최종점수', '주소', '종류', '평수', '보증금', '월세', '관리비',
        '총_시간(분)', '통학점수', '월세_관리비_합', '예산초과금액',
        '가격점수', '시설점수', '크기점수', 'url 주소'
    ]

    compare_table_df = result_df.copy()
    compare_table_df.insert(0, '선택', False)

    existing_display_cols = [col for col in display_cols if col in compare_table_df.columns]
    display_df = compare_table_df[existing_display_cols].copy()

    edited_df = st.data_editor(
        display_df,
        column_config={
            "선택": st.column_config.CheckboxColumn(
                "비교 선택",
                help="비교할 매물 2개만 선택하세요.",
                default=False
            ),
            "최종점수": st.column_config.NumberColumn("총 점수", format="%.1f"),
            "url 주소": st.column_config.LinkColumn("링크"),
            "총_시간(분)": st.column_config.NumberColumn("학교까지시간(분)", format="%d"),
            "월세_관리비_합": st.column_config.NumberColumn("월세+관리비", format="%d"),
            "예산초과금액": st.column_config.NumberColumn("예산 초과금액", format="%d"),
            "통학점수": st.column_config.NumberColumn("통학점수", format="%.1f"),
            "가격점수": st.column_config.NumberColumn("가격점수", format="%.1f"),
            "시설점수": st.column_config.NumberColumn("시설점수", format="%.1f"),
            "크기점수": st.column_config.NumberColumn("크기점수", format="%.1f"),
            "보증금": st.column_config.NumberColumn("보증금", format="%d"),
            "월세": st.column_config.NumberColumn("월세", format="%d"),
            "관리비": st.column_config.NumberColumn("관리비", format="%d"),
        },
        disabled=[col for col in existing_display_cols if col != '선택'],
        hide_index=True,
        use_container_width=True,
        height=420,
        key="compare_data_editor"
    )

    selected_rows = edited_df[edited_df['선택'] == True]

    selected_count = len(selected_rows)
    st.caption(f"현재 선택된 매물: {selected_count}개 / 2개")

    if st.button("선택한 2개 매물 비교하기", use_container_width=True):
        if selected_count != 2:
            st.warning("비교할 매물을 정확히 2개만 선택해주세요.")
        else:
            selected_indices = selected_rows.index.tolist()
            row_a = result_df.loc[selected_indices[0]]
            row_b = result_df.loc[selected_indices[1]]

            cost_a = calculate_total_cost(
                row_a,
                months=compare_months,
                commute_days_per_month=commute_days
            )

            cost_b = calculate_total_cost(
                row_b,
                months=compare_months,
                commute_days_per_month=commute_days
            )

            if cost_a["총비용"] < cost_b["총비용"]:
                winner = "A"
                loser = "B"
                winner_row = row_a
                loser_row = row_b
            else:
                winner = "B"
                loser = "A"
                winner_row = row_b
                loser_row = row_a

            diff = abs(cost_a["총비용"] - cost_b["총비용"])
            diff_rate = diff / max(cost_a["총비용"], cost_b["총비용"]) * 100 if max(cost_a["총비용"], cost_b["총비용"]) > 0 else 0

            st.markdown("""
            <div style="
                background-color:#F8F9FA;
                border:2px solid #1E90FF;
                border-radius:16px;
                padding:22px;
                margin-top:15px;
                margin-bottom:20px;
                box-shadow:0 4px 8px rgba(0,0,0,0.08);
            ">
                <h3 style="margin-top:0; color:#1E90FF;">1vs1 경제성 비교 결과</h3>
                <p style="color:#555; margin-bottom:0;">
                    보증금 기회비용, 월세, 관리비, 통학시간 비용을 모두 반영한 실질 총비용 비교입니다.
                </p>
            </div>
            """, unsafe_allow_html=True)

            summary_col1, summary_col2, summary_col3 = st.columns(3)
            with summary_col1:
                st.metric("매물 A 총비용", format_won(cost_a["총비용"]))
            with summary_col2:
                st.metric("매물 B 총비용", format_won(cost_b["총비용"]))
            with summary_col3:
                st.metric("총비용 차이", format_won(diff), f"{diff_rate:.1f}%")

            result_compare = pd.DataFrame({
                "항목": [
                    "주소", "평수", "보증금", "월세", "관리비", "통학시간",
                    "보증금 기회비용", "월세 총액", "관리비 총액", "통학시간 비용", "총비용"
                ],
                "매물 A": [
                    row_a["주소"],
                    f"{row_a['평수']}평",
                    format_won(row_a["보증금"]),
                    format_won(row_a["월세"]),
                    format_won(row_a["관리비"]),
                    f"{int(row_a['총_시간(분)'])}분" if pd.notna(row_a["총_시간(분)"]) else "-",
                    format_won(cost_a["보증금 기회비용"]),
                    format_won(cost_a["월세 총액"]),
                    format_won(cost_a["관리비 총액"]),
                    format_won(cost_a["통학시간 비용"]),
                    format_won(cost_a["총비용"])
                ],
                "매물 B": [
                    row_b["주소"],
                    f"{row_b['평수']}평",
                    format_won(row_b["보증금"]),
                    format_won(row_b["월세"]),
                    format_won(row_b["관리비"]),
                    f"{int(row_b['총_시간(분)'])}분" if pd.notna(row_b["총_시간(분)"]) else "-",
                    format_won(cost_b["보증금 기회비용"]),
                    format_won(cost_b["월세 총액"]),
                    format_won(cost_b["관리비 총액"]),
                    format_won(cost_b["통학시간 비용"]),
                    format_won(cost_b["총비용"])
                ]
            })

            st.dataframe(result_compare, hide_index=True, use_container_width=True)

            st.success(
                f"추천 결과: 매물 {winner}가 더 경제적입니다. "
                f"매물 {loser}보다 실질 총비용이 약 {format_won(diff)} 낮고, "
                f"비율로는 약 {diff_rate:.1f}% 차이입니다."
            )

            st.info(
                f"해석: '{winner_row['주소']}' 매물은 월세, 보증금 기회비용, 관리비, 통학시간 비용을 모두 합산했을 때 "
                f"'{loser_row['주소']}' 매물보다 경제성이 더 높습니다."
            )



            link_col1, link_col2 = st.columns(2)
            with link_col1:
                if str(row_a['url 주소']).strip() != "":
                    st.link_button("매물 A 상세보기", row_a['url 주소'], use_container_width=True)
            with link_col2:
                if str(row_b['url 주소']).strip() != "":
                    st.link_button("매물 B 상세보기", row_b['url 주소'], use_container_width=True)

    st.divider()

else:
    st.warning("조건에 맞는 매물이 없습니다. 필터 조건을 완화해보세요.")


# --- 8. 동네별 최고의 매물 ---
st.subheader("동네별 최고의 매물 (지역별 1위)")

target_areas = ["송도동", "동춘동", "연수동", "청학동", "옥련동", "선학동"]
area_cols = st.columns(6)

for i, area in enumerate(target_areas):
    area_best = result_df[result_df['주소'].str.contains(area, na=False)].head(1) if not result_df.empty else pd.DataFrame()

    with area_cols[i]:
        if not area_best.empty:
            b_row = area_best.iloc[0]
            total_time_b = f"{int(b_row['총_시간(분)'])}분" if pd.notna(b_row.get('총_시간(분)')) else "-"

            area_card_html = f"""
            <div style="
                background-color:#f8f9fa;
                border:2px solid #1E90FF;
                border-radius:12px;
                padding:15px;
                text-align:center;
                box-shadow:0 2px 4px rgba(0,0,0,0.1);
                height:250px;
                box-sizing:border-box;
                overflow:hidden;
                font-family:Arial, sans-serif;
            ">
                <div style="
                    background-color:#1E90FF;
                    color:white;
                    border-radius:20px;
                    padding:6px 12px;
                    display:inline-block;
                    font-size:14px;
                    font-weight:bold;
                    margin-bottom:12px;
                ">
                    {area} 지역 1위
                </div>

                <div style="
                    font-size:24px;
                    font-weight:800;
                    color:#1E90FF;
                    margin-bottom:8px;
                ">
                    {b_row['최종점수']}점
                </div>

                <div style="
                    font-size:13px;
                    color:#333;
                    margin-bottom:12px;
                    height:42px;
                    overflow:hidden;
                    line-height:1.4;
                ">
                    {b_row['주소']}
                </div>

                <div style="
                    font-size:13px;
                    color:#666;
                    line-height:1.7;
                ">
                    가격: <b>{int(b_row['보증금'] / 10000)}/{int(b_row['월세'] / 10000)}</b><br>
                    시간: <b>{total_time_b}</b><br>
                    크기: <b>{b_row['평수']}평</b>
                </div>
            </div>
            """

            components.html(area_card_html, height=270)

            if str(b_row['url 주소']).strip() != "":
                st.link_button(
                    f"{area} 매물 상세보기",
                    b_row['url 주소'],
                    use_container_width=True
                )
        else:
            st.info(f"{area} 지역 조건 만족 매물 없음")
