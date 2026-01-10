import streamlit as st
import pandas as pd
from datetime import datetime
import os
import altair as alt
from io import BytesIO

# ======================
# 기본 설정
# ======================
st.set_page_config(
    page_title="환경미화 소모품 관리",
    layout="wide"
)

st.title("📱 환경미화 소모품 스마트 장부")

DATA_FILE = "logs.csv"
ADMIN_PASSWORD = "1234"  # 나중에 변경 권장

# ======================
# 데이터 불러오기
# ======================
if os.path.exists(DATA_FILE):
    df = pd.read_csv(DATA_FILE)
else:
    df = pd.DataFrame(columns=["시간", "수령자", "품목", "수량"])

df["시간"] = pd.to_datetime(df["시간"], errors="coerce")

# ======================
# 사이드바 메뉴
# ======================
menu = st.sidebar.radio(
    "메뉴",
    ["📤 지급 기록", "📊 통계", "⚙️ 관리자"]
)

# ======================
# 1. 지급 기록
# ======================
if menu == "📤 지급 기록":
    st.subheader("소모품 지급")

    with st.form("issue_form", clear_on_submit=True):
        person = st.selectbox(
            "수령자",
            ["김순영", "노나경", "최점순", "이순옥", "박선옥"]
        )

        item = st.selectbox(
            "품목",
            ["핸드타올", "점보롤", "락스", "박리제", "쓰레기봉투(50L)", "물비누"]
        )

        qty = st.number_input("수량", min_value=1, value=1)

        submit = st.form_submit_button("지급 기록")

        if submit:
            new_row = {
                "시간": datetime.now(),
                "수령자": person,
                "품목": item,
                "수량": qty
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            df.to_csv(DATA_FILE, index=False)
            st.success("기록되었습니다.")

    st.divider()

    df_sorted = df.dropna(subset=["시간"]).sort_values("시간", ascending=False)
    st.dataframe(df_sorted, use_container_width=True)

# ======================
# 2. 통계
# ======================
elif menu == "📊 통계":
    st.subheader("월별 · 품목별 소모 통계")

    if df.empty:
        st.info("아직 기록이 없습니다.")
    else:
        df["월"] = df["시간"].dt.to_period("M").astype(str)

        month = st.selectbox(
            "월 선택",
            sorted(df["월"].unique())
        )

        filtered = df[df["월"] == month]
        stats = filtered.groupby("품목")["수량"].sum().reset_index()

        chart = alt.Chart(stats).mark_bar().encode(
            x=alt.X("수량", title="총 소모량"),
            y=alt.Y("품목", sort="-x"),
            tooltip=["품목", "수량"]
        )

        st.altair_chart(chart, use_container_width=True)
        st.dataframe(stats, use_container_width=True)

# ======================
# 3. 관리자
# ======================
elif menu == "⚙️ 관리자":
    st.subheader("관리자 영역")

    password = st.text_input("비밀번호", type="password")

    if password == ADMIN_PASSWORD:
        st.success("관리자 인증 완료")

        st.subheader("기록 삭제")

        if len(df) == 0:
            st.info("삭제할 데이터가 없습니다.")
        else:
            idx = st.number_input(
                "삭제할 행 번호 (0부터 시작)",
                min_value=0,
                max_value=len(df) - 1,
                step=1
            )

            if st.button("삭제"):
                df = df.drop(df.index[int(idx)]).reset_index(drop=True)
                df.to_csv(DATA_FILE, index=False)
                st.success("삭제되었습니다.")

        st.subheader("엑셀 다운로드")

        buffer = BytesIO()
        df.to_excel(buffer, index=False)
        buffer.seek(0)

        st.download_button(
            "📥 엑셀로 다운로드",
            data=buffer,
            file_name="소모품_지급_내역.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    else:
        st.warning("관리자 비밀번호를 입력하세요.")
